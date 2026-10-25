import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api, type ScreenerFilters } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { AssetType, ScreenerItemDTO, ScreenerResponseDTO, WatchlistItemDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty, ErrorBanner, Loading } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brlCompact, dateTime, num, pct, parseDecimal, points } from "../../utils/format";
import {
  ARCA_LABELS,
  ASSET_TYPE_LABELS,
  LIFECYCLE_LABELS,
  LIFECYCLE_TONES,
  PROFILE_LABELS,
  RECOMMENDATION_LABELS,
  VERDICT_LABELS,
  VERDICT_TONES,
} from "../../utils/labels";

type TabKey = "screener" | "watchlist";
const TABS: TabSpec<TabKey>[] = [
  { key: "screener", label: "Screener" },
  { key: "watchlist", label: "Em observação" },
];

const SCREEN_TYPES: AssetType[] = ["STOCK_BR", "FII", "ETF_BR", "BDR"];

interface ScreenForm {
  q: string;
  types: AssetType[];
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

function ResultsTable({
  result,
  onFollow,
  following,
}: Readonly<{ result: ScreenerResponseDTO; onFollow: (item: ScreenerItemDTO) => void; following: string | null }>) {
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
                    {item.sector ? ` · ${item.sector}` : ""}
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
                  <button
                    type="button"
                    className="app-secondary-button"
                    disabled={following === item.ticker}
                    onClick={() => onFollow(item)}
                  >
                    Observar
                  </button>
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

  const follow = async (item: ScreenerItemDTO) => {
    setFollowing(item.ticker);
    setNotice(null);
    try {
      const added = await api.research.follow({ ticker: item.ticker, asset_type: item.asset_type, name: item.name });
      setNotice(`${added.ticker} está em observação.`);
      await run();
    } catch (err) {
      setNotice(errorMessage(err));
    } finally {
      setFollowing(null);
    }
  };

  const toggleType = (type: AssetType) =>
    set("types", form.types.includes(type) ? form.types.filter((t) => t !== type) : [...form.types, type]);

  return (
    <div className="app-page-stack">
      <form className="app-card app-card-padded" onSubmit={run}>
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="screen-q">Nome ou código</label>
            <input id="screen-q" value={form.q} onChange={(e) => set("q", e.target.value)} placeholder="Ex.: banco, ITUB" />
          </div>
          <div className="app-field">
            <label htmlFor="screen-volume">Volume diário mínimo (R$)</label>
            <input id="screen-volume" inputMode="decimal" value={form.minVolume} onChange={(e) => set("minVolume", e.target.value)} placeholder="1000000" />
          </div>
          <div className="app-field">
            <label htmlFor="screen-pe">P/L máximo</label>
            <input id="screen-pe" inputMode="decimal" value={form.maxPe} onChange={(e) => set("maxPe", e.target.value)} />
          </div>
          <div className="app-field">
            <label htmlFor="screen-pb">P/VP máximo</label>
            <input id="screen-pb" inputMode="decimal" value={form.maxPb} onChange={(e) => set("maxPb", e.target.value)} />
          </div>
          <div className="app-field">
            <label htmlFor="screen-dy">DY mínimo (%)</label>
            <input id="screen-dy" inputMode="decimal" value={form.minDy} onChange={(e) => set("minDy", e.target.value)} />
          </div>
          <div className="app-field">
            <label htmlFor="screen-roe">ROE mínimo (%)</label>
            <input id="screen-roe" inputMode="decimal" value={form.minRoe} onChange={(e) => set("minRoe", e.target.value)} />
          </div>
        </div>
        <div className="app-filter-bar" style={{ marginTop: "var(--space-3)", marginBottom: 0 }}>
          <div className="app-chip-group" role="group" aria-label="Tipos">
            {SCREEN_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                className="app-chip"
                aria-pressed={form.types.includes(type)}
                onClick={() => toggleType(type)}
              >
                {ASSET_TYPE_LABELS[type]}
              </button>
            ))}
          </div>
          <label className="app-check">
            <input type="checkbox" checked={form.belowBand} onChange={(e) => set("belowBand", e.target.checked)} />
            Só classes abaixo da banda
          </label>
          <label className="app-check">
            <input
              type="checkbox"
              checked={form.excludeRegistered}
              onChange={(e) => set("excludeRegistered", e.target.checked)}
            />
            Esconder já cadastrados
          </label>
          <button type="submit" className="app-primary-button" disabled={loading} style={{ marginLeft: "auto" }}>
            {loading ? "Buscando…" : "Buscar"}
          </button>
        </div>
      </form>
      {notice && <p className="app-info-banner">{notice}</p>}
      <ErrorBanner error={error} onRetry={() => void run()} />
      {loading && !result && <Loading lines={5} />}
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
            <ResultsTable result={result} onFollow={(item) => void follow(item)} following={following} />
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

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await api.research.follow({ ticker: ticker.trim(), asset_type: assetType || null });
      setTicker("");
      watchlist.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const remove = async (item: WatchlistItemDTO) => {
    if (!window.confirm(`Parar de observar ${item.ticker}?`)) return;
    setError(null);
    try {
      await api.research.unfollow(item.asset_id);
      watchlist.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="app-page-stack">
      <form className="app-filter-bar" onSubmit={add}>
        <div className="app-field">
          <label htmlFor="watch-ticker">Observar código</label>
          <input id="watch-ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="Ex.: BBAS3" />
        </div>
        <div className="app-field">
          <label htmlFor="watch-type">Tipo</label>
          <select id="watch-type" value={assetType} onChange={(e) => setAssetType(e.target.value as AssetType | "")}>
            <option value="">Pelo catálogo da B3</option>
            {SCREEN_TYPES.map((type) => (
              <option key={type} value={type}>
                {ASSET_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="app-primary-button" disabled={!ticker.trim()}>
          Adicionar
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
                            {item.name} · {PROFILE_LABELS[item.checklist_profile]}
                          </small>
                        </span>
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
                        <button type="button" className="app-link-button" onClick={() => void remove(item)}>
                          Remover
                        </button>
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
        subtitle="Encontre ativos no catálogo da B3, observe-os e analise antes de comprar."
      />
      <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Pesquisa" />
      {tab === "screener" ? <Screener /> : <Watchlist />}
    </div>
  );
}
