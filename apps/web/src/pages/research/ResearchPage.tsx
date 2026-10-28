import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api, type ScreenerFilters } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  ArcaClass,
  AssetType,
  FixedIncomeIndexer,
  ScreenerItemDTO,
  ScreenerResponseDTO,
  TreasuryBondDTO,
  TreasurySearchResponseDTO,
  WatchlistItemDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { IconButton } from "../../components/RowActions";
import { TrashIcon } from "../../layout/icons";
import { ArcaClassSelect } from "../../components/ArcaClassSelect";
import { Hint } from "../../components/Hint";
import { MultiSelect } from "../../components/MultiSelect";
import { Async, Empty, ErrorBanner, Loading, Spinner } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brl, brlCompact, dateTime, day, num, pct, parseDecimal, points } from "../../utils/format";
import {
  ARCA_CLASSES,
  ARCA_LABELS,
  ASSET_TYPE_LABELS,
  LIFECYCLE_LABELS,
  LIFECYCLE_TONES,
  PROFILE_LABELS,
  RECOMMENDATION_LABELS,
  VERDICT_LABELS,
  VERDICT_TONES,
} from "../../utils/labels";
import { formatTreasuryRate, percentToContractedRate } from "../../utils/rates";
import { compareLink } from "../tools/AssetComparePage";

type TabKey = "screener" | "treasury" | "watchlist";
const TABS: TabSpec<TabKey>[] = [
  { key: "screener", label: "Screener" },
  { key: "treasury", label: "Tesouro Direto" },
  { key: "watchlist", label: "Em observação" },
];

const SCREEN_TYPES: AssetType[] = ["STOCK_BR", "FII", "ETF_BR", "BDR"];

interface ScreenForm {
  q: string;
  types: AssetType[];
  arcaClasses: ArcaClass[];
  sector: string;
  minVolume: string;
  maxPe: string;
  maxPb: string;
  minDy: string;
  minRoe: string;
  belowBand: boolean;
  excludeRegistered: boolean;
}

const EMPTY_FORM: ScreenForm = {
  q: "",
  types: [],
  arcaClasses: [],
  sector: "",
  minVolume: "",
  maxPe: "",
  maxPb: "",
  minDy: "",
  minRoe: "",
  belowBand: false,
  excludeRegistered: false,
};

function toFilters(form: ScreenForm): ScreenerFilters {
  const percent = (text: string) => {
    const value = parseDecimal(text);
    return value === null ? undefined : value / 100;
  };
  const number = (text: string) => parseDecimal(text) ?? undefined;
  return {
    q: form.q.trim() || undefined,
    asset_type: form.types.length ? form.types : undefined,
    arca_class: form.arcaClasses.length ? form.arcaClasses : undefined,
    sector: form.sector ? [form.sector] : undefined,
    min_volume_brl: number(form.minVolume),
    max_pe: number(form.maxPe),
    max_pb: number(form.maxPb),
    min_dy: percent(form.minDy),
    min_roe: percent(form.minRoe),
    below_band: form.belowBand || undefined,
    exclude_registered: form.excludeRegistered || undefined,
    limit: 50,
  };
}

type FollowHandler = (item: ScreenerItemDTO, arcaClass: ArcaClass) => void;

/** "Observar" asks for the ARCA quadrant first, with the suggested one preselected. */
function FollowAction({ item, onFollow, busy }: Readonly<{ item: ScreenerItemDTO; onFollow: FollowHandler; busy: boolean }>) {
  const [arcaClass, setArcaClass] = useState<ArcaClass | null>(null);
  if (arcaClass === null) {
    return (
      <button type="button" className="app-secondary-button" disabled={busy} onClick={() => setArcaClass(item.arca_class)}>
        {busy && <Spinner size="sm" />}
        <span>{busy ? "Observando…" : "Observar"}</span>
      </button>
    );
  }
  return (
    <span className="app-button-row">
      <ArcaClassSelect
        label={`Classe ARCA de ${item.ticker}`}
        value={arcaClass}
        suggested={item.arca_class}
        disabled={busy}
        onChange={(value) => value && setArcaClass(value)}
      />
      <button type="button" className="app-primary-button" disabled={busy} onClick={() => onFollow(item, arcaClass)}>
        {busy && <Spinner size="sm" />}
        <span>{busy ? "Salvando…" : "Confirmar"}</span>
      </button>
      <button type="button" className="app-link-button" disabled={busy} onClick={() => setArcaClass(null)}>
        Cancelar
      </button>
    </span>
  );
}

function ResultsTable({
  result,
  onFollow,
  following,
}: Readonly<{ result: ScreenerResponseDTO; onFollow: FollowHandler; following: string | null }>) {
  if (result.results.length === 0) {
    return <Empty title="Nenhum ativo com esses critérios" hint="Afrouxe os filtros ou mude o tipo." />;
  }
  return (
    <div className="app-table-wrap">
      <table className="app-table">
        <thead>
          <tr>
            <th>Ativo</th>
            <th>Classe</th>
            <th className="app-numeric">Preço</th>
            <th className="app-numeric">Volume</th>
            <th className="app-numeric">P/L</th>
            <th className="app-numeric">P/VP</th>
            <th className="app-numeric">DY</th>
            <th className="app-numeric">ROE</th>
            <th>Valuation</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {result.results.map((item) => (
            <tr key={item.ticker}>
              <td>
                <span className="app-cell-main">
                  {item.asset_id ? (
                    <Link className="app-link" to={`/asset/${item.asset_id}`}>
                      {item.ticker}
                    </Link>
                  ) : (
                    <strong>{item.ticker}</strong>
                  )}
                  <small>
                    {item.name}
                    {item.sector ? ` · ${item.sector}` : ""} ·{" "}
                    <Link className="app-link" to={compareLink(item.ticker)}>
                      Comparar
                    </Link>
                  </small>
                </span>
              </td>
              <td>{ARCA_LABELS[item.arca_class]}</td>
              <td className="app-numeric">{num(item.close)}</td>
              <td className="app-numeric">{brlCompact(item.volume_brl)}</td>
              <td className="app-numeric">{num(item.price_to_earnings, 1)}</td>
              <td className="app-numeric">{num(item.price_to_book, 2)}</td>
              <td className="app-numeric">{pct(item.dividend_yield)}</td>
              <td className="app-numeric">{pct(item.return_on_equity)}</td>
              <td>
                {item.valuation_verdict && (
                  <Badge tone={VERDICT_TONES[item.valuation_verdict]}>
                    {VERDICT_LABELS[item.valuation_verdict] ?? item.valuation_verdict}
                  </Badge>
                )}
              </td>
              <td className="app-row-actions">
                {item.lifecycle_status ? (
                  <Badge tone={LIFECYCLE_TONES[item.lifecycle_status]}>{LIFECYCLE_LABELS[item.lifecycle_status]}</Badge>
                ) : (
                  <FollowAction item={item} onFollow={onFollow} busy={following === item.ticker} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Screener() {
  const [form, setForm] = useState<ScreenForm>(EMPTY_FORM);
  const [result, setResult] = useState<ScreenerResponseDTO | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [following, setFollowing] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const set = <K extends keyof ScreenForm>(key: K, value: ScreenForm[K]) => setForm((f) => ({ ...f, [key]: value }));

  const run = async (event?: FormEvent) => {
    event?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(await api.research.screener(toFilters(form)));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  const follow = async (item: ScreenerItemDTO, arcaClass: ArcaClass) => {
    setFollowing(item.ticker);
    setNotice(null);
    try {
      const added = await api.research.follow({
        ticker: item.ticker,
        asset_type: item.asset_type,
        name: item.name,
        arca_class: arcaClass,
      });
      setNotice(`${added.ticker} está em observação em ${ARCA_LABELS[added.arca_class]}.`);
      await run();
    } catch (err) {
      setNotice(errorMessage(err));
    } finally {
      setFollowing(null);
    }
  };

  const sectors = useApi("research-sectors", () => api.research.sectors());

  return (
    <div className="app-page-stack">
      <form className="app-card app-card-padded" onSubmit={run} aria-busy={loading}>
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="screen-q">Nome ou código</label>
            <input id="screen-q" value={form.q} onChange={(e) => set("q", e.target.value)} placeholder="Ex.: banco, ITUB" disabled={loading} />
          </div>
          <div className="app-field">
            <label htmlFor="screen-sector">Setor</label>
            <select id="screen-sector" value={form.sector} onChange={(e) => set("sector", e.target.value)} disabled={loading}>
              <option value="">Todos</option>
              {(sectors.data ?? []).map((sector) => (
                <option key={sector} value={sector}>
                  {sector}
                </option>
              ))}
            </select>
          </div>
          <div className="app-field">
            <label htmlFor="screen-types">Tipo</label>
            <MultiSelect
              id="screen-types"
              options={SCREEN_TYPES.map((type) => ({ value: type, label: ASSET_TYPE_LABELS[type] }))}
              value={form.types}
              onChange={(types) => set("types", types)}
              disabled={loading}
            />
          </div>
          <div className="app-field">
            <label htmlFor="screen-arca">Classe ARCA</label>
            <MultiSelect
              id="screen-arca"
              options={ARCA_CLASSES.map((arca) => ({ value: arca, label: ARCA_LABELS[arca] }))}
              value={form.arcaClasses}
              onChange={(arcaClasses) => set("arcaClasses", arcaClasses)}
              disabled={loading}
            />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="screen-volume">Volume diário mínimo (R$)</label>
              <Hint about="Volume diário mínimo">Média diária negociada para filtrar liquidez.</Hint>
            </span>
            <input id="screen-volume" inputMode="decimal" value={form.minVolume} onChange={(e) => set("minVolume", e.target.value)} placeholder="1000000" disabled={loading} />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="screen-pe">P/L máximo</label>
              <Hint about="P/L máximo">Preço sobre Lucro. Relação entre o valor de mercado e o lucro anual.</Hint>
            </span>
            <input id="screen-pe" inputMode="decimal" value={form.maxPe} onChange={(e) => set("maxPe", e.target.value)} disabled={loading} />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="screen-pb">P/VP máximo</label>
              <Hint about="P/VP máximo">Preço sobre Valor Patrimonial por ação.</Hint>
            </span>
            <input id="screen-pb" inputMode="decimal" value={form.maxPb} onChange={(e) => set("maxPb", e.target.value)} disabled={loading} />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="screen-dy">DY mínimo (%)</label>
              <Hint about="DY mínimo">Dividend Yield anual distribuído nos últimos 12 meses.</Hint>
            </span>
            <input id="screen-dy" inputMode="decimal" value={form.minDy} onChange={(e) => set("minDy", e.target.value)} disabled={loading} />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="screen-roe">ROE mínimo (%)</label>
              <Hint about="ROE mínimo">Retorno sobre o patrimônio líquido.</Hint>
            </span>
            <input id="screen-roe" inputMode="decimal" value={form.minRoe} onChange={(e) => set("minRoe", e.target.value)} disabled={loading} />
          </div>
        </div>
        <div className="app-filter-bar" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
          <label className="app-check">
            <input type="checkbox" checked={form.belowBand} disabled={loading} onChange={(e) => set("belowBand", e.target.checked)} />
            Só classes abaixo da banda
          </label>
          <label className="app-check">
            <input
              type="checkbox"
              checked={form.excludeRegistered}
              disabled={loading}
              onChange={(e) => set("excludeRegistered", e.target.checked)}
            />
            Esconder já cadastrados
          </label>
          <button type="submit" className="app-primary-button" disabled={loading} style={{ marginLeft: "auto" }}>
            {loading && <Spinner size="sm" />}
            <span>{loading ? "Buscando…" : "Buscar"}</span>
          </button>
        </div>
      </form>
      {notice && <p className="app-info-banner">{notice}</p>}
      <ErrorBanner error={error} onRetry={() => void run()} />
      {loading && !result && <Loading lines={5} />}
      {loading && result && (
        <div className="app-busy-overlay" role="status" aria-live="polite">
          <Spinner size="sm" />
          <span>Atualizando candidatos do screener…</span>
        </div>
      )}
      {result && (
        <>
          <p className="app-muted" style={{ margin: 0 }}>
            {result.results.length} resultado(s) de {result.candidates} candidato(s) no catálogo de {result.catalog_size}{" "}
            ativos{result.catalog_updated_at ? ` (atualizado em ${dateTime(result.catalog_updated_at)})` : ""}.
            {result.truncated && " Os indicadores foram buscados só para os mais líquidos: refine os filtros para ver outros."}
            {result.arca_classes && result.arca_classes.length > 0 &&
              ` Classes abaixo da banda: ${result.arca_classes.map((c) => ARCA_LABELS[c]).join(", ")}.`}
          </p>
          {result.catalog_size === 0 ? (
            <Empty
              title="Catálogo vazio"
              hint="O worker sincroniza a lista de ativos da B3 em dias úteis; confira em Dados de mercado."
            />
          ) : (
            <ResultsTable result={result} onFollow={(item, arca) => void follow(item, arca)} following={following} />
          )}
        </>
      )}
      {!result && !loading && !error && (
        <Empty title="Encontre candidatos" hint="Combine filtros e clique em Buscar. Observe um ativo para analisá-lo." />
      )}
    </div>
  );
}

function Watchlist() {
  const watchlist = useApi("watchlist", () => api.research.watchlist());
  const [error, setError] = useState<string | null>(null);
  const [ticker, setTicker] = useState("");
  const [assetType, setAssetType] = useState<AssetType | "">("");
  const [arcaClass, setArcaClass] = useState<ArcaClass | "">("");
  const [adding, setAdding] = useState(false);
  const [reclassifyingId, setReclassifyingId] = useState<number | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setAdding(true);
    setError(null);
    try {
      await api.research.follow({ ticker: ticker.trim(), asset_type: assetType || null, arca_class: arcaClass || null });
      setTicker("");
      setArcaClass("");
      watchlist.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAdding(false);
    }
  };

  const reclassify = async (item: WatchlistItemDTO, value: ArcaClass) => {
    setReclassifyingId(item.asset_id);
    setError(null);
    try {
      await api.research.classify(item.asset_id, value);
      watchlist.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setReclassifyingId(null);
    }
  };

  const remove = async (item: WatchlistItemDTO) => {
    if (!window.confirm(`Parar de observar ${item.ticker}?`)) return;
    setRemovingId(item.asset_id);
    setError(null);
    try {
      await api.research.unfollow(item.asset_id);
      watchlist.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="app-page-stack">
      <form className="app-filter-bar" onSubmit={add} aria-busy={adding}>
        <div className="app-field">
          <label htmlFor="watch-ticker">Observar código</label>
          <input
            id="watch-ticker"
            value={ticker}
            disabled={adding}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="Ex.: BBAS3"
          />
        </div>
        <div className="app-field">
          <label htmlFor="watch-type">Tipo</label>
          <select
            id="watch-type"
            value={assetType}
            disabled={adding}
            onChange={(e) => setAssetType(e.target.value as AssetType | "")}
          >
            <option value="">Pelo catálogo da B3</option>
            {SCREEN_TYPES.map((type) => (
              <option key={type} value={type}>
                {ASSET_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="watch-arca">Classe ARCA</label>
          <ArcaClassSelect id="watch-arca" value={arcaClass} disabled={adding} onChange={setArcaClass} emptyLabel="Sugerida pelo tipo" />
        </div>
        <button type="submit" className="app-primary-button" disabled={adding || !ticker.trim()}>
          {adding && <Spinner size="sm" />}
          <span>{adding ? "Adicionando…" : "Adicionar"}</span>
        </button>
      </form>
      {error && <p className="app-error-banner">{error}</p>}
      <Async state={watchlist} lines={4}>
        {(items) =>
          items.length === 0 ? (
            <Empty title="Nada em observação" hint="Use o screener ou informe um código acima." />
          ) : (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th>Classe ARCA</th>
                    <th>Situação</th>
                    <th className="app-numeric">Preço</th>
                    <th>Checklist</th>
                    <th>Valuation</th>
                    <th className="app-numeric">Margem</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.asset_id}>
                      <td>
                        <span className="app-cell-main">
                          <Link className="app-link" to={`/asset/${item.asset_id}`}>
                            {item.ticker}
                          </Link>
                          <small>
                            {item.name} · {PROFILE_LABELS[item.checklist_profile]} ·{" "}
                            <Link className="app-link" to={compareLink(item.ticker)}>
                              Comparar
                            </Link>
                          </small>
                        </span>
                      </td>
                      <td>
                        <ArcaClassSelect
                          label={`Classe ARCA de ${item.ticker}`}
                          value={item.arca_class}
                          disabled={reclassifyingId === item.asset_id}
                          onChange={(value) => value && void reclassify(item, value)}
                        />
                      </td>
                      <td>
                        <Badge tone={LIFECYCLE_TONES[item.lifecycle_status]}>{LIFECYCLE_LABELS[item.lifecycle_status]}</Badge>
                      </td>
                      <td className="app-numeric">{num(item.price)}</td>
                      <td>
                        {item.checklist_score > 0 ? "+" : ""}
                        {item.checklist_score} ·{" "}
                        {RECOMMENDATION_LABELS[item.checklist_recommendation] ?? item.checklist_recommendation}{" "}
                        <span className="app-muted">({points(item.checklist_coverage_pct, 0)} respondido)</span>
                      </td>
                      <td>
                        <Badge tone={VERDICT_TONES[item.valuation_verdict]}>
                          {VERDICT_LABELS[item.valuation_verdict] ?? item.valuation_verdict}
                        </Badge>
                      </td>
                      <td className="app-numeric">{item.margin === null || item.margin === undefined ? "—" : pct(item.margin, 1, true)}</td>
                      <td className="app-row-actions">
                        <IconButton
                          label="Remover"
                          busyLabel="Removendo…"
                          icon={<TrashIcon />}
                          danger
                          busy={removingId === item.asset_id}
                          onClick={() => void remove(item)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Async>
    </div>
  );
}

export function ResearchPage() {
  const [tab, setTab] = useTab(TABS, "screener");
  return (
    <div className="app-page">
      <PageHeader
        title="Pesquisar"
        subtitle="Encontre ativos no catálogo da B3, títulos do Tesouro Direto e acompanhe candidatos antes de comprar."
      />
      <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Pesquisa" />
      {tab === "screener" && <Screener />}
      {tab === "treasury" && <TreasuryScreener />}
      {tab === "watchlist" && <Watchlist />}
    </div>
  );
}

function TreasuryScreener() {
  const [q, setQ] = useState("");
  const [indexer, setIndexer] = useState<FixedIncomeIndexer | "">("");
  const [couponType, setCouponType] = useState<"" | "zero" | "semestral">("");
  const [result, setResult] = useState<TreasurySearchResponseDTO | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [registering, setRegistering] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const run = async (event?: FormEvent) => {
    event?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(
        await api.research.treasury({
          q: q.trim() || undefined,
          indexer: indexer || undefined,
          coupon_type: couponType || undefined,
        }),
      );
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  const registerBond = async (bond: TreasuryBondDTO) => {
    setRegistering(bond.symbol);
    setNotice(null);
    try {
      const created = await api.assets.create({
        name: bond.name,
        asset_type: "TREASURY",
        arca_class: "CAIXA",
        purpose: "ARCA",
        fixed_income_term: {
          instrument_kind: bond.instrument_kind,
          indexer: bond.indexer,
          contracted_rate: percentToContractedRate(bond.contracted_rate_percent),
          maturity_date: bond.maturity_date,
          tax_exempt: false,
          liquidity: bond.liquidity,
          issuer: "Tesouro Nacional",
          semiannual_coupons: bond.coupon_type === "semestral",
        },
      });
      setNotice(`${created.name} (${created.ticker}) cadastrado com sucesso.`);
      await run();
    } catch (err) {
      setNotice(errorMessage(err));
    } finally {
      setRegistering(null);
    }
  };

  return (
    <div className="app-page-stack">
      <form className="app-card app-card-padded" onSubmit={run} aria-busy={loading}>
        <div className="app-filter-bar" style={{ marginBottom: 0 }}>
          <div className="app-field" style={{ flex: 1 }}>
            <label htmlFor="treasury-q">Título ou vencimento</label>
            <input
              id="treasury-q"
              value={q}
              disabled={loading}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ex.: Selic, IPCA, 2031"
            />
          </div>
          <div className="app-field">
            <label htmlFor="treasury-indexer">Indexador</label>
            <select
              id="treasury-indexer"
              value={indexer}
              disabled={loading}
              onChange={(e) => setIndexer(e.target.value as FixedIncomeIndexer | "")}
            >
              <option value="">Todos</option>
              <option value="SELIC">SELIC</option>
              <option value="IPCA">IPCA</option>
              <option value="PRE">PRE</option>
            </select>
          </div>
          <div className="app-field">
            <label htmlFor="treasury-coupon">Cupom</label>
            <select
              id="treasury-coupon"
              value={couponType}
              disabled={loading}
              onChange={(e) => setCouponType(e.target.value as "" | "zero" | "semestral")}
            >
              <option value="">Todos</option>
              <option value="zero">Sem cupom</option>
              <option value="semestral">Juros semestrais</option>
            </select>
          </div>
          <button type="submit" className="app-primary-button" disabled={loading}>
            {loading && <Spinner size="sm" />}
            <span>{loading ? "Buscando…" : "Buscar"}</span>
          </button>
        </div>
      </form>
      {notice && <p className="app-info-banner">{notice}</p>}
      <ErrorBanner error={error} onRetry={() => void run()} />
      {loading && !result && <Loading lines={4} />}
      {loading && result && (
        <div className="app-busy-overlay" role="status" aria-live="polite">
          <Spinner size="sm" />
          <span>Atualizando títulos do Tesouro Direto…</span>
        </div>
      )}
      {result?.unavailable_reason && <p className="app-info-banner">{result.unavailable_reason}</p>}
      {result && !result.unavailable_reason && (
        <>
          <p className="app-muted" style={{ margin: 0 }}>
            {result.results.length} título(s) encontrado(s) no catálogo do Tesouro Transparente
            {result.catalog_size ? ` (${result.catalog_size} títulos vigentes)` : ""}
            {result.catalog_updated_at ? ` · atualizado em ${dateTime(result.catalog_updated_at)}` : ""}.
          </p>
          {result.results.length === 0 ? (
            <Empty title="Nenhum título encontrado" hint="Ajuste o filtro de indexador, cupom ou texto." />
          ) : (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Título</th>
                    <th>Indexador</th>
                    <th>Vencimento</th>
                    <th className="app-numeric">Taxa compra</th>
                    <th className="app-numeric">Taxa venda</th>
                    <th className="app-numeric">PU compra</th>
                    <th className="app-numeric">PU venda / base</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((bond) => (
                    <tr key={bond.symbol}>
                      <td>
                        <span className="app-cell-main">
                          {bond.asset_id ? (
                            <Link className="app-link" to={`/asset/${bond.asset_id}`}>
                              {bond.name}
                            </Link>
                          ) : (
                            <strong>{bond.name}</strong>
                          )}
                          <small>
                            {bond.symbol}
                            {bond.coupon_type === "semestral" ? " · Juros semestrais" : ""}
                          </small>
                        </span>
                      </td>
                      <td>{bond.indexer}</td>
                      <td>{day(bond.maturity_date)}</td>
                      <td className="app-numeric">{formatTreasuryRate(bond, bond.buy_rate)}</td>
                      <td className="app-numeric">{formatTreasuryRate(bond, bond.sell_rate)}</td>
                      <td className="app-numeric">{brl(bond.buy_price)}</td>
                      <td className="app-numeric">{brl(bond.sell_price ?? bond.base_price)}</td>
                      <td className="app-row-actions">
                        {bond.asset_id ? (
                          <Link className="app-link" to={`/asset/${bond.asset_id}`}>
                            Cadastrado
                          </Link>
                        ) : (
                          <button
                            type="button"
                            className="app-secondary-button"
                            disabled={registering === bond.symbol}
                            onClick={() => void registerBond(bond)}
                          >
                            {registering === bond.symbol && <Spinner size="sm" />}
                            <span>{registering === bond.symbol ? "Cadastrando…" : "Cadastrar"}</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {!result && !loading && !error && (
        <Empty
          title="Consulte títulos do Tesouro Direto"
          hint="Filtre por indexador ou vencimento e clique em Buscar para consultar taxas e preços sincronizados do Tesouro Transparente."
        />
      )}
    </div>
  );
}
