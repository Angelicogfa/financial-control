import { useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type ScreenerFilters } from "../../api/endpoints";
import type {
  ArcaClass,
  AssetComparisonDTO,
  ComparedAssetDTO,
  ComparisonRowDTO,
  IndicatorGroup,
  IndicatorUnit,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Hint } from "../../components/Hint";
import { MultiSelect } from "../../components/MultiSelect";
import { PageHeader } from "../../components/PageHeader";
import { Pagination } from "../../components/Pagination";
import { Async, Empty, ErrorBanner, Spinner } from "../../components/States";
import { brlCompact, money, num, pct } from "../../utils/format";
import {
  ARCA_CLASSES,
  ARCA_LABELS,
  PROFILE_LABELS,
  RECOMMENDATION_LABELS,
  VERDICT_LABELS,
  VERDICT_TONES,
} from "../../utils/labels";
import { TrendChart } from "../../viz/TrendChart";
import { useScreenerSearch, type ScreenerSearch } from "../research/useScreenerSearch";
import { useStoredState } from "../../utils/storedState";

export const MAX_COMPARED = 5;

const HISTORY_METRICS = [
  { key: "revenue", label: "Receita", unit: "MONEY" },
  { key: "net_income", label: "Lucro líquido", unit: "MONEY" },
  { key: "roe", label: "ROE", unit: "FRACTION" },
  { key: "dividend_yield", label: "DY", unit: "FRACTION" },
] as const;
type HistoryKey = (typeof HISTORY_METRICS)[number]["key"];

const SERIES_COLORS = [
  "var(--viz-serie-1)",
  "var(--viz-serie-2)",
  "var(--viz-serie-3)",
  "var(--viz-serie-4)",
  "var(--app-text-subtle)",
];

/** Tickers from `?tickers=A,B` (upper-case, unique, at most five). */
export function parseTickers(raw: string | null): string[] {
  const out: string[] = [];
  for (const part of (raw ?? "").split(",")) {
    const ticker = part.trim().toUpperCase();
    if (ticker && !out.includes(ticker)) out.push(ticker);
  }
  return out.slice(0, MAX_COMPARED);
}

/** Link to the comparator starting with `tickers`. */
export function compareLink(...tickers: string[]): string {
  return `/tools/compare?tickers=${encodeURIComponent(tickers.join(","))}`;
}

export function formatIndicator(value: number | null | undefined, unit: IndicatorUnit): string {
  if (value === null || value === undefined) return "—";
  return unit === "FRACTION" ? pct(value, 1) : num(value, 2);
}

function TickerPicker({ tickers, onChange }: Readonly<{ tickers: string[]; onChange: (next: string[]) => void }>) {
  const [draft, setDraft] = useState("");
  const full = tickers.length >= MAX_COMPARED;
  const add = (event: FormEvent) => {
    event.preventDefault();
    const next = parseTickers([...tickers, draft].join(","));
    onChange(next);
    setDraft("");
  };
  return (
    <form className="app-card app-card-padded" onSubmit={add} aria-label="Ativos comparados">
      <div className="app-button-row">
        {tickers.map((t) => (
          <span key={t} className="compare-chip">
            {t}
            <button
              type="button"
              className="app-icon-button"
              aria-label={`Remover ${t}`}
              onClick={() => onChange(tickers.filter((x) => x !== t))}
            >
              ×
            </button>
          </span>
        ))}
        <label className="app-sr-only" htmlFor="compare-ticker">
          Ticker para comparar
        </label>
        <input
          id="compare-ticker"
          value={draft}
          placeholder={full ? "Limite de 5 ativos" : "Ex.: WEGE3"}
          disabled={full}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="app-secondary-button" disabled={full || !draft.trim()}>
          Adicionar
        </button>
        <Hint about="Ativos comparados">De 2 a 5 ativos, cadastrados ou do catálogo da B3. Compare ativos do mesmo perfil.</Hint>
      </div>
    </form>
  );
}

export interface SearchForm {
  q: string;
  sector: string;
  arcaClasses: ArcaClass[];
}

const EMPTY_SEARCH: SearchForm = { q: "", sector: "", arcaClasses: [] };

/** Screener filters for the comparator search: name or code, sector and ARCA class. */
export function searchFilters(form: SearchForm): ScreenerFilters {
  return {
    q: form.q.trim() || undefined,
    sector: form.sector ? [form.sector] : undefined,
    arca_class: form.arcaClasses.length ? form.arcaClasses : undefined,
  };
}

function SearchResults({
  search,
  tickers,
  onAdd,
}: Readonly<{ search: ScreenerSearch; tickers: string[]; onAdd: (ticker: string) => void }>) {
  const rows = search.result?.results ?? [];
  if (search.pagination.total === 0) {
    return <Empty title="Nenhum ativo com esses critérios" hint="Afrouxe os filtros ou mude o setor." />;
  }
  const full = tickers.length >= MAX_COMPARED;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Resultados da busca">
        <thead>
          <tr>
            <th>Ativo</th>
            <th>Classe</th>
            <th className="app-numeric">Preço</th>
            <th className="app-numeric">P/L</th>
            <th className="app-numeric">DY</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => {
            const added = tickers.includes(item.ticker);
            return (
              <tr key={item.ticker}>
                <td>
                  <span className="app-cell-main">
                    <strong>{item.ticker}</strong>
                    <small>
                      {item.name}
                      {item.sector ? ` · ${item.sector}` : ""}
                    </small>
                  </span>
                </td>
                <td>{ARCA_LABELS[item.arca_class]}</td>
                <td className="app-numeric">{num(item.close)}</td>
                <td className="app-numeric">{num(item.price_to_earnings, 1)}</td>
                <td className="app-numeric">{pct(item.dividend_yield)}</td>
                <td className="app-row-actions">
                  <button
                    type="button"
                    className="app-secondary-button"
                    aria-label={`Adicionar ${item.ticker}`}
                    disabled={added || full}
                    onClick={() => onAdd(item.ticker)}
                  >
                    {added ? "Adicionado" : "Adicionar"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Pagination {...search.pagination} onRefresh={() => void search.refresh()} refreshing={search.loading} />
    </div>
  );
}

/** Finds candidates in the B3 catalog by name, sector and ARCA class, like the screener. */
function AssetSearch({ tickers, onAdd }: Readonly<{ tickers: string[]; onAdd: (ticker: string) => void }>) {
  const [form, setForm] = useStoredState<SearchForm>("compare:search-form", EMPTY_SEARCH);
  const search = useScreenerSearch();
  const { result, error, loading } = search;
  const sectors = useApi("research-sectors", () => api.research.sectors());
  const set = <K extends keyof SearchForm>(key: K, value: SearchForm[K]) => setForm((f) => ({ ...f, [key]: value }));

  const run = async (event: FormEvent) => {
    event.preventDefault();
    await search.search(searchFilters(form));
  };

  return (
    <section className="app-card app-card-padded">
      <h2 className="app-card-heading">Buscar ativos</h2>
      <form onSubmit={run} aria-busy={loading} aria-label="Buscar ativos para comparar">
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="compare-q">Nome ou código</label>
            <input
              id="compare-q"
              value={form.q}
              onChange={(e) => set("q", e.target.value)}
              placeholder="Ex.: banco, ITUB"
              disabled={loading}
            />
          </div>
          <div className="app-field">
            <label htmlFor="compare-sector">Setor</label>
            <select id="compare-sector" value={form.sector} onChange={(e) => set("sector", e.target.value)} disabled={loading}>
              <option value="">Todos</option>
              {(sectors.data ?? []).map((sector) => (
                <option key={sector} value={sector}>
                  {sector}
                </option>
              ))}
            </select>
          </div>
          <div className="app-field">
            <label htmlFor="compare-arca">Classe ARCA</label>
            <MultiSelect
              id="compare-arca"
              options={ARCA_CLASSES.map((arca) => ({ value: arca, label: ARCA_LABELS[arca] }))}
              value={form.arcaClasses}
              onChange={(arcaClasses) => set("arcaClasses", arcaClasses)}
              disabled={loading}
            />
          </div>
        </div>
        <div className="app-button-row" style={{ marginTop: "var(--space-3)" }}>
          <button type="submit" className="app-primary-button" disabled={loading}>
            {loading && <Spinner size="sm" />}
            <span>{loading ? "Buscando…" : "Buscar"}</span>
          </button>
          <button type="button" className="app-link-button" disabled={loading} onClick={() => setForm(EMPTY_SEARCH)}>
            Limpar filtros
          </button>
        </div>
      </form>
      <ErrorBanner error={error} />
      {result && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <SearchResults search={search} tickers={tickers} onAdd={onAdd} />
        </div>
      )}
    </section>
  );
}

function AssetSummary({ assets }: Readonly<{ assets: ComparedAssetDTO[] }>) {
  return (
    <>
      <tr>
        <td>Perfil</td>
        {assets.map((a) => (
          <td key={a.ticker}>{PROFILE_LABELS[a.profile] ?? a.profile}</td>
        ))}
      </tr>
      <tr>
        <td>Preço</td>
        {assets.map((a) => (
          <td key={a.ticker} className="app-numeric">
            {money(a.price, a.currency ?? "BRL")}
          </td>
        ))}
      </tr>
      <tr>
        <td>Valuation</td>
        {assets.map((a) => (
          <td key={a.ticker}>
            <Badge tone={VERDICT_TONES[a.valuation_verdict ?? ""]}>
              {VERDICT_LABELS[a.valuation_verdict ?? ""] ?? a.valuation_verdict ?? "—"}
            </Badge>
          </td>
        ))}
      </tr>
      <tr>
        <td>Checklist</td>
        {assets.map((a) => (
          <td key={a.ticker}>
            {a.checklist_score ?? "—"}/{a.checklist_max_score ?? "—"}{" "}
            <span className="app-muted">
              {RECOMMENDATION_LABELS[a.checklist_recommendation ?? ""] ?? a.checklist_recommendation ?? ""}
            </span>
          </td>
        ))}
      </tr>
    </>
  );
}

function IndicatorRow({ row, assets }: Readonly<{ row: ComparisonRowDTO; assets: ComparedAssetDTO[] }>) {
  return (
    <tr>
      <td>
        {row.label}
        <small className="app-muted"> ({row.better === "LOWER" ? "menor é melhor" : "maior é melhor"})</small>
      </td>
      {assets.map((a) => {
        const best = row.best.includes(a.ticker);
        return (
          <td key={a.ticker} className={`app-numeric${best ? " compare-best" : ""}`}>
            {best ? <strong>{formatIndicator(row.values[a.ticker], row.unit)}</strong> : formatIndicator(row.values[a.ticker], row.unit)}
            {best && <span className="compare-best-mark"> ▲ melhor</span>}
          </td>
        );
      })}
    </tr>
  );
}

function History({ data }: Readonly<{ data: AssetComparisonDTO }>) {
  const [metric, setMetric] = useState<HistoryKey>("revenue");
  const spec = HISTORY_METRICS.find((m) => m.key === metric) ?? HISTORY_METRICS[0];
  const years = [...new Set(data.history.flatMap((h) => (h.points ?? []).map((p) => p.year)))].sort();
  const series = data.history.map((h, i) => ({
    key: h.ticker,
    label: h.ticker,
    color: SERIES_COLORS[i % SERIES_COLORS.length],
    values: years.map((y) => {
      const point = (h.points ?? []).find((p) => p.year === y);
      const value = point?.[metric];
      if (value === null || value === undefined) return null;
      return spec.unit === "FRACTION" ? value * 100 : value;
    }),
  }));
  return (
    <section className="app-card app-card-padded">
      <div className="health-pillar-head">
        <h2 className="app-card-heading">Histórico anual</h2>
        <div className="app-segmented" role="group" aria-label="Indicador do histórico">
          {HISTORY_METRICS.map((m) => (
            <button key={m.key} type="button" aria-pressed={metric === m.key} onClick={() => setMetric(m.key)}>
              {m.label}
            </button>
          ))}
        </div>
      </div>
      {years.length >= 2 ? (
        <TrendChart
          title={`${spec.label} por ano`}
          labels={years.map(String)}
          hint="Passe o mouse para ler cada ano."
          format={(v) => (spec.unit === "FRACTION" ? `${num(v, 1)}%` : brlCompact(v))}
          series={series}
        />
      ) : (
        <Empty title="Sem histórico anual suficiente" hint="Os demonstrativos anuais aparecem quando houver dois anos ou mais." />
      )}
      {spec.key === "dividend_yield" && (
        <p className="app-card-hint">
          DY anual estimado: proventos pagos sobre o valor de mercado no último pregão do ano, com o número de ações de
          hoje.
        </p>
      )}
    </section>
  );
}

function Comparison({ data }: Readonly<{ data: AssetComparisonDTO }>) {
  const groups = data.groups ?? [];
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hiddenGroups, setHiddenGroups] = useState<Set<IndicatorGroup>>(new Set());
  const toggle = <T,>(set: Set<T>, value: T) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  };
  const visible = data.rows.filter((r) => !hidden.has(r.key) && !hiddenGroups.has(r.group));
  return (
    <div className="app-page-stack">
      {(data.warnings ?? []).map((w) => (
        <div key={w} className="app-info-banner" role="note">
          {w}
        </div>
      ))}
      <details className="app-card app-card-padded">
        <summary>Escolher indicadores</summary>
        <div className="health-grid">
          {groups.map((g) => (
            <fieldset key={g.group}>
              <legend>
                <label className="app-check">
                  <input
                    type="checkbox"
                    checked={!hiddenGroups.has(g.group)}
                    onChange={() => setHiddenGroups((s) => toggle(s, g.group))}
                  />
                  {g.label}
                </label>
              </legend>
              {(data.indicators ?? [])
                .filter((i) => i.group === g.group)
                .map((i) => (
                  <label key={i.key} className="app-check">
                    <input
                      type="checkbox"
                      checked={!hidden.has(i.key)}
                      disabled={hiddenGroups.has(g.group)}
                      onChange={() => setHidden((s) => toggle(s, i.key))}
                    />
                    {i.label}
                  </label>
                ))}
            </fieldset>
          ))}
        </div>
      </details>
      <div className="app-table-wrap">
        <table className="app-table">
          <thead>
            <tr>
              <th>Indicador</th>
              {data.assets.map((a) => (
                <th key={a.ticker} className="app-numeric">
                  {a.asset_id ? (
                    <Link className="app-link" to={`/asset/${a.asset_id}`}>
                      {a.ticker}
                    </Link>
                  ) : (
                    a.ticker
                  )}
                  <small className="app-muted"> {a.name}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <AssetSummary assets={data.assets} />
            {groups.map((g) => {
              const rows = visible.filter((r) => r.group === g.group);
              if (rows.length === 0) return null;
              return [
                <tr key={`group-${g.group}`} className="app-table-group">
                  <td colSpan={data.assets.length + 1}>{g.label}</td>
                </tr>,
                ...rows.map((row) => <IndicatorRow key={row.key} row={row} assets={data.assets} />),
              ];
            })}
          </tbody>
        </table>
      </div>
      <History data={data} />
    </div>
  );
}

export function AssetComparePage() {
  const [params, setParams] = useSearchParams();
  const tickers = useMemo(() => parseTickers(params.get("tickers")), [params]);
  const ready = tickers.length >= 2;
  const comparison = useApi(`compare-${tickers.join(",")}`, () =>
    ready ? api.research.compare(tickers) : Promise.resolve(null),
  );
  const change = (next: string[]) =>
    setParams(
      (current) => {
        const updated = new URLSearchParams(current);
        if (next.length) updated.set("tickers", next.join(","));
        else updated.delete("tickers");
        return updated;
      },
      { replace: true },
    );

  return (
    <div className="app-page">
      <PageHeader
        title="Comparar ativos"
        subtitle="Até 5 ativos lado a lado: valuation, endividamento, eficiência, rentabilidade e crescimento."
      />
      <div className="app-page-stack">
        <TickerPicker tickers={tickers} onChange={change} />
        <AssetSearch tickers={tickers} onAdd={(ticker) => change(parseTickers([...tickers, ticker].join(",")))} />
        {ready ? (
          <Async state={comparison} lines={8}>
            {(data) => <Comparison data={data} />}
          </Async>
        ) : (
          <Empty title="Escolha ao menos dois ativos" hint="Adicione tickers, busque por setor e classe ARCA ou use “Comparar” na Pesquisa, na Carteira ou no ativo." />
        )}
      </div>
    </div>
  );
}
