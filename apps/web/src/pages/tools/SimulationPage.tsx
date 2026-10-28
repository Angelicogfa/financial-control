import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  BacktestRequest,
  BacktestSummaryDTO,
  GoalOutcomeDTO,
  PercentilesDTO,
  ProjectionDTO,
  ProjectionRequest,
  RobustnessDTO,
  SimulationResultDTO,
  SimulationRunDetailDTO,
  SimulationRunDTO,
  SimulationStatus,
  WindowOutcomeDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty, Spinner } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brl, brlCompact, day, dateTime, daysAgo, num, parseDecimal, pct, points, today } from "../../utils/format";
import { ARCA_LABELS } from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { TrendChart, type TrendSeries } from "../../viz/TrendChart";

type Benchmark = NonNullable<BacktestRequest["benchmarks"]>[number];
type TabKey = "past" | "future" | "robustness";

const TABS: TabSpec<TabKey>[] = [
  { key: "past", label: "Passado" },
  { key: "future", label: "Futuro" },
  { key: "robustness", label: "Robustez" },
];

export const BENCHMARK_LABELS: Record<Benchmark, string> = {
  CDI: "CDI",
  IBOV: "Ibovespa",
  IFIX: "IFIX",
  SP500_BRL: "S&P 500 (R$)",
};

const STATUS_LABELS: Record<SimulationStatus, { label: string; tone: string }> = {
  PENDING: { label: "Na fila", tone: "info" },
  RUNNING: { label: "Rodando", tone: "info" },
  DONE: { label: "Concluída", tone: "success" },
  FAILED: { label: "Falhou", tone: "danger" },
  TIMEOUT: { label: "Tempo esgotado", tone: "warning" },
};

const SERIES_COLORS = ["var(--viz-serie-1)", "var(--viz-serie-2)", "var(--viz-serie-3)", "var(--viz-serie-4)"];
const POLL_MS = 3000;

export function isActive(status: SimulationStatus): boolean {
  return status === "PENDING" || status === "RUNNING";
}

function StatusBadge({ status }: Readonly<{ status: SimulationStatus }>) {
  const spec = STATUS_LABELS[status];
  return <Badge tone={spec.tone}>{spec.label}</Badge>;
}

// --- form -----------------------------------------------------------------------------------

interface FormState {
  start: string;
  end: string;
  monthly: string;
  initial: string;
  correctByIpca: boolean;
  rebalance: boolean;
  universe: NonNullable<BacktestRequest["universe"]>;
  policyMode: NonNullable<BacktestRequest["policy_mode"]>;
  benchmarks: Benchmark[];
  variants: boolean;
  label: string;
}

const INITIAL_FORM: FormState = {
  start: "2010-01-01",
  end: daysAgo(1),
  monthly: "1000",
  initial: "0",
  correctByIpca: true,
  rebalance: false,
  universe: "REGISTERED",
  policyMode: "CURRENT",
  benchmarks: ["CDI", "IBOV"],
  variants: true,
  label: "",
};

/** The API request from the form; null when a number is missing. */
export function toBacktestRequest(form: FormState): BacktestRequest | null {
  const monthly = parseDecimal(form.monthly);
  const initial = parseDecimal(form.initial) ?? 0;
  if (monthly === null || monthly <= 0) return null;
  return {
    start: form.start,
    end: form.end,
    monthly_contribution: monthly,
    initial_contribution: initial,
    correct_by_ipca: form.correctByIpca,
    rebalance: form.rebalance,
    universe: form.universe,
    policy_mode: form.policyMode,
    benchmarks: form.benchmarks,
    variants: form.variants,
    label: form.label.trim() || null,
  };
}

function BacktestForm({ onSubmitted }: Readonly<{ onSubmitted: (run: SimulationRunDTO) => void }>) {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (change: Partial<FormState>) => setForm((f) => ({ ...f, ...change }));
  const toggleBenchmark = (key: Benchmark) =>
    set({ benchmarks: form.benchmarks.includes(key) ? form.benchmarks.filter((b) => b !== key) : [...form.benchmarks, key] });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = toBacktestRequest(form);
    if (!body) {
      setError("Informe um aporte mensal maior que zero.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onSubmitted(await api.simulations.submitBacktest(body));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="app-card app-card-padded" onSubmit={submit} aria-busy={saving} aria-label="Nova simulação">
      <h2 className="app-card-heading">Nova simulação</h2>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      <fieldset className="app-field-grid" disabled={saving}>
        <div className="app-field">
          <label htmlFor="sim-start">Início</label>
          <input id="sim-start" type="date" value={form.start} max={today()} onChange={(e) => set({ start: e.target.value })} required />
        </div>
        <div className="app-field">
          <label htmlFor="sim-end">Fim</label>
          <input id="sim-end" type="date" value={form.end} max={today()} onChange={(e) => set({ end: e.target.value })} required />
        </div>
        <div className="app-field">
          <label htmlFor="sim-monthly">Aporte mensal (R$)</label>
          <input id="sim-monthly" inputMode="decimal" value={form.monthly} onChange={(e) => set({ monthly: e.target.value })} required />
        </div>
        <div className="app-field">
          <label htmlFor="sim-initial">Aporte inicial (R$)</label>
          <input id="sim-initial" inputMode="decimal" value={form.initial} onChange={(e) => set({ initial: e.target.value })} />
        </div>
        <div className="app-field">
          <label htmlFor="sim-universe">Ativos</label>
          <select id="sim-universe" value={form.universe} onChange={(e) => set({ universe: e.target.value as FormState["universe"] })}>
            <option value="REGISTERED">Carteira e watchlist</option>
            <option value="REGISTERED_AND_CATALOG">Carteira, watchlist e mais negociados da B3 (viés de sobrevivência)</option>
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="sim-policy">Política</label>
          <select id="sim-policy" value={form.policyMode} onChange={(e) => set({ policyMode: e.target.value as FormState["policyMode"] })}>
            <option value="CURRENT">Regras atuais em todo o período</option>
            <option value="AS_OF">Versão vigente em cada data</option>
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="sim-label">Nome (opcional)</label>
          <input id="sim-label" value={form.label} maxLength={120} onChange={(e) => set({ label: e.target.value })} />
        </div>
      </fieldset>
      <fieldset className="app-field-grid" disabled={saving}>
        <legend className="app-card-hint">Regras</legend>
        <label className="app-check">
          <input type="checkbox" checked={form.correctByIpca} onChange={(e) => set({ correctByIpca: e.target.checked })} />
          Corrigir o aporte pelo IPCA
        </label>
        <label className="app-check">
          <input type="checkbox" checked={form.rebalance} onChange={(e) => set({ rebalance: e.target.checked })} />
          Rebalancear vendendo o excesso (com IR)
        </label>
        <label className="app-check">
          <input type="checkbox" checked={form.variants} onChange={(e) => set({ variants: e.target.checked })} />
          Testar variantes de banda e rebalanceamento
        </label>
      </fieldset>
      <fieldset className="app-field-grid" disabled={saving}>
        <legend className="app-card-hint">Comparar com o mesmo fluxo de aportes em</legend>
        {(Object.keys(BENCHMARK_LABELS) as Benchmark[]).map((key) => (
          <label key={key} className="app-check">
            <input type="checkbox" checked={form.benchmarks.includes(key)} onChange={() => toggleBenchmark(key)} />
            {BENCHMARK_LABELS[key]}
          </label>
        ))}
      </fieldset>
      <div className="app-form-actions">
        <button type="submit" className="app-primary-button" disabled={saving}>
          {saving && <Spinner size="sm" />}
          <span>{saving ? "Enviando…" : "Simular"}</span>
        </button>
      </div>
    </form>
  );
}

// --- runs list --------------------------------------------------------------------------------

function backtestPeriod(run: SimulationRunDTO): string {
  return `${day(String(run.params?.start ?? ""))} a ${day(String(run.params?.end ?? ""))}`;
}

function RunList({
  runs,
  selected,
  onSelect,
  describe = backtestPeriod,
  describeLabel = "Período",
}: Readonly<{
  runs: SimulationRunDTO[];
  selected: number | null;
  onSelect: (id: number) => void;
  describe?: (run: SimulationRunDTO) => string;
  describeLabel?: string;
}>) {
  if (runs.length === 0) return <Empty title="Nenhuma simulação ainda" hint="Preencha o formulário e clique em Simular." />;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Simulações">
        <thead>
          <tr>
            <th>Simulação</th>
            <th>{describeLabel}</th>
            <th>Status</th>
            <th>Pedida em</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} aria-selected={run.id === selected}>
              <td>
                <button type="button" className="app-link-button" onClick={() => onSelect(run.id)}>
                  {run.label || `Simulação #${run.id}`}
                </button>
              </td>
              <td>{describe(run)}</td>
              <td>
                <StatusBadge status={run.status} />
              </td>
              <td>{dateTime(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- past -------------------------------------------------------------------------------------

export function seriesOf(results: SimulationResultDTO[]): SimulationResultDTO[] {
  return results.filter((r) => !r.key.startsWith("variant:"));
}

function SummaryTable({ results }: Readonly<{ results: SimulationResultDTO[] }>) {
  const rows: Array<[string, (s: BacktestSummaryDTO) => string]> = [
    ["Valor final", (s) => brl(s.final_value)],
    ["Investido", (s) => brl(s.contributed)],
    ["Ganho", (s) => brl(s.gain)],
    ["TIR a.a. (dos aportes)", (s) => pct(s.money_weighted_return, 2)],
    ["Rentabilidade a.a. (TWR)", (s) => pct(s.annual_twr, 2)],
    ["Volatilidade a.a.", (s) => pct(s.volatility, 1)],
    ["Queda máxima", (s) => pct(s.max_drawdown, 1)],
    ["Custos", (s) => brl(s.fees)],
    ["IR pago", (s) => brl(s.taxes)],
    ["Operações", (s) => String(s.trades)],
  ];
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Resumo">
        <thead>
          <tr>
            <th>Métrica</th>
            {results.map((r) => (
              <th key={r.key} className="app-numeric">
                {r.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td>{label}</td>
              {results.map((r) => (
                <td key={r.key} className="app-numeric">
                  {value(r.summary)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Reproducibility({ run }: Readonly<{ run: SimulationRunDTO }>) {
  return (
    <p className="app-muted">
      Motor {run.code_version} · semente {run.seed} · dados {run.data_hash?.slice(0, 12) ?? "—"} · parâmetros{" "}
      {run.params_hash.slice(0, 12)}
      {run.reused_from ? ` · resultado reaproveitado da simulação #${run.reused_from} (mesmos dados e regras)` : ""}
    </p>
  );
}

function RunProblem({ run }: Readonly<{ run: SimulationRunDTO }>) {
  if (isActive(run.status)) {
    return (
      <p className="app-muted" role="status">
        <Spinner size="sm" /> {run.status === "PENDING" ? "Na fila do worker…" : "Rodando…"} A página atualiza sozinha.
      </p>
    );
  }
  return (
    <p className="app-error-banner" role="alert">
      {run.status === "TIMEOUT" ? "A simulação passou do tempo limite." : "A simulação falhou."} {run.error}
    </p>
  );
}

function PastTab({ detail }: Readonly<{ detail: SimulationRunDetailDTO }>) {
  if (detail.status !== "DONE") return <RunProblem run={detail} />;
  const series = seriesOf(detail.results ?? []);
  const strategy = series.find((r) => r.key === "strategy");
  const points = strategy?.points ?? [];
  if (!strategy || points.length < 2) {
    return <Empty title="Sem pontos suficientes" hint="O período não tem dois fins de mês com preço." />;
  }
  const unavailable = strategy.unavailable ?? [];
  const labels = points.map((p) => day(p.day));
  const lines: TrendSeries[] = [
    ...series.map((r, i) => ({
      key: r.key,
      label: r.label,
      color: SERIES_COLORS[i % SERIES_COLORS.length],
      values: (r.points ?? []).map((p) => p.market_value),
    })),
    { key: "contributed", label: "Investido", color: "var(--app-muted, #888)", values: points.map((p) => p.contributed) },
  ];
  const last = points[points.length - 1];
  return (
    <div className="app-page-stack">
      {strategy.survivorship_bias && (
        <p className="app-warning-banner" role="note">
          Inclui ativos do catálogo atual da B3: só as empresas que sobreviveram até hoje aparecem, e o passado parece melhor
          do que foi (viés de sobrevivência).
        </p>
      )}
      {unavailable.length > 0 && (
        <p className="app-muted">Sem preço no período (ficaram de fora): {unavailable.join(", ")}.</p>
      )}
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Patrimônio com o mesmo fluxo de aportes</h2>
        <TrendChart
          title="Patrimônio da estratégia e das referências mês a mês"
          labels={labels}
          series={lines}
          hint="Todas as linhas recebem os mesmos aportes nas mesmas datas; a diferença é só onde o dinheiro foi aplicado."
          format={(v) => brl(v)}
        />
      </section>
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Resumo</h2>
        <SummaryTable results={series} />
        <BarList
          label="Alocação final por classe"
          bars={Object.entries(last.by_class ?? {}).map(([cls, value]) => ({
            id: cls,
            label: ARCA_LABELS[cls as keyof typeof ARCA_LABELS] ?? cls,
            share: last.market_value > 0 ? value / last.market_value : 0,
            value: brl(value),
          }))}
        />
      </section>
      <Reproducibility run={detail} />
    </div>
  );
}

// --- robustness -------------------------------------------------------------------------------

function Outcome({ outcome }: Readonly<{ outcome: WindowOutcomeDTO | undefined }>) {
  if (!outcome?.covered) return <span className="app-muted">fora do período</span>;
  return (
    <>
      <Signed value={outcome.return_rate}>{pct(outcome.return_rate, 1, true)}</Signed>
      <div className="app-muted">queda máx. {pct(outcome.max_drawdown, 1)}</div>
    </>
  );
}

export function RobustnessView({ data }: Readonly<{ data: RobustnessDTO }>) {
  if (data.status !== "DONE") return <Empty title="A robustez aparece quando a simulação terminar" />;
  const { series = [], crises = [], shocks = [], variants = [], warnings = [] } = data;
  const twr = variants.map((v) => v.summary.annual_twr);
  const top = Math.max(...twr.map((v) => Math.abs(v)), 0.0001);
  return (
    <div className="app-page-stack">
      <ul className="app-warning-banner" aria-label="Avisos de amostra">
        {warnings.map((w) => (
          <li key={w}>{w}</li>
        ))}
      </ul>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Crises históricas</h2>
        <p className="app-card-hint">Rentabilidade dentro da janela, sem contar os aportes, e a maior queda nela.</p>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Crises históricas">
            <thead>
              <tr>
                <th>Crise</th>
                {series.map((s) => (
                  <th key={s.key} className="app-numeric">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {crises.map((c) => (
                <tr key={c.key}>
                  <td>
                    {c.label}
                    <div className="app-muted">
                      {day(c.start)} a {day(c.end)}
                    </div>
                  </td>
                  {series.map((s) => (
                    <td key={s.key} className="app-numeric">
                      <Outcome outcome={c.outcomes?.[s.key]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Choques sobre a alocação final</h2>
        <p className="app-card-hint">Efeito imediato de primeira ordem; não inclui reações em cadeia entre as classes.</p>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Choques sintéticos">
            <thead>
              <tr>
                <th>Choque</th>
                <th className="app-numeric">Antes</th>
                <th className="app-numeric">Depois</th>
                <th className="app-numeric">Variação</th>
              </tr>
            </thead>
            <tbody>
              {shocks.map((s) => (
                <tr key={s.key}>
                  <td>
                    {s.label}
                    {s.note && <div className="app-muted">{s.note}</div>}
                  </td>
                  <td className="app-numeric">{brl(s.before)}</td>
                  <td className="app-numeric">{brl(s.after)}</td>
                  <td className="app-numeric">
                    <Signed value={s.change}>
                      {brl(s.change)} ({pct(s.change_rate, 1, true)})
                    </Signed>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Variantes das regras</h2>
        {variants.length === 0 ? (
          <Empty title="Esta simulação não testou variantes" hint="Rode de novo marcando “Testar variantes de banda e rebalanceamento”." />
        ) : (
          <>
            <p>
              {data.trials_in_run} variantes nesta simulação · {data.trials_total} testadas ao todo. Rentabilidade a.a. entre{" "}
              {pct(data.annual_twr_distribution.minimum, 2)} e {pct(data.annual_twr_distribution.maximum, 2)} (mediana{" "}
              {pct(data.annual_twr_distribution.median, 2)}).
            </p>
            <p className="app-card-hint">
              Todas as variantes aparecem, não só a melhor: escolher a melhor entre muitas tentativas é ajustar ao ruído. Quanto
              mais tentativas, maior a chance de a melhor ser sorte.
            </p>
            <BarList
              label="Rentabilidade a.a. de cada variante"
              bars={variants.map((v) => ({
                id: v.key,
                label: v.label,
                share: Math.abs(v.summary.annual_twr) / top,
                tone: v.summary.annual_twr < 0 ? "is-negative" : undefined,
                value: pct(v.summary.annual_twr, 2),
              }))}
            />
            <div className="app-table-wrap">
              <table className="app-table" aria-label="Variantes">
                <thead>
                  <tr>
                    <th>Variante</th>
                    <th className="app-numeric">Valor final</th>
                    <th className="app-numeric">Queda máxima</th>
                    <th className="app-numeric">IR + custos</th>
                    <th className="app-numeric">Até {data.holdout_start ? day(data.holdout_start) : "—"}</th>
                    <th className="app-numeric">Janela reservada</th>
                  </tr>
                </thead>
                <tbody>
                  {variants.map((v) => (
                    <tr key={v.key}>
                      <td>{v.label}</td>
                      <td className="app-numeric">{brl(v.summary.final_value)}</td>
                      <td className="app-numeric">{pct(v.summary.max_drawdown, 1)}</td>
                      <td className="app-numeric">{brl((v.summary.taxes ?? 0) + v.summary.fees)}</td>
                      <td className="app-numeric">
                        <Outcome outcome={v.selection} />
                      </td>
                      <td className="app-numeric">
                        <Outcome outcome={v.holdout} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="app-card-hint">
              Os últimos 36 meses ficam reservados para validar: escolha uma regra olhando só o período anterior e use a janela
              reservada para conferir se a vantagem se mantém.
            </p>
          </>
        )}
      </section>
    </div>
  );
}

function RobustnessTab({ run }: Readonly<{ run: SimulationRunDTO }>) {
  const state = useApi(`simulation-robustness-${run.id}-${run.status}`, () => api.simulations.robustness(run.id));
  if (run.status !== "DONE") return <RunProblem run={run} />;
  return <Async state={state}>{(data) => <RobustnessView data={data} />}</Async>;
}

// --- future -----------------------------------------------------------------------------------

type ClassKey = keyof NonNullable<ProjectionRequest["initial_by_class"]>;
const CLASS_KEYS: ClassKey[] = ["ACOES", "REAL_ESTATE", "ATIVOS_INTERNACIONAIS", "CAIXA"];

interface ProjectionFormState {
  horizonYears: string;
  monthly: string;
  realGrowth: string;
  wealthGoal: string;
  incomeGoal: string;
  rebalance: boolean;
  fromPortfolio: boolean;
  initial: Record<ClassKey, string>;
  cdi: string;
  ipca: string;
  label: string;
}

const INITIAL_PROJECTION: ProjectionFormState = {
  horizonYears: "20",
  monthly: "1000",
  realGrowth: "0",
  wealthGoal: "",
  incomeGoal: "",
  rebalance: false,
  fromPortfolio: true,
  initial: { ACOES: "0", REAL_ESTATE: "0", ATIVOS_INTERNACIONAIS: "0", CAIXA: "0" },
  cdi: "",
  ipca: "",
  label: "",
};

/** A percentage typed by the user ("10,5") as a fraction; null when empty. */
function percentInput(text: string): number | null {
  const value = parseDecimal(text);
  return value === null ? null : value / 100;
}

/** The API request from the form; null when the horizon or the contribution is invalid. */
export function toProjectionRequest(form: ProjectionFormState): ProjectionRequest | null {
  const years = Number.parseInt(form.horizonYears, 10);
  const monthly = parseDecimal(form.monthly);
  if (!Number.isFinite(years) || years < 1 || years > 50 || monthly === null || monthly < 0) return null;
  const positive = (text: string) => {
    const value = parseDecimal(text);
    return value !== null && value > 0 ? value : null;
  };
  return {
    horizon_years: years,
    monthly_contribution: monthly,
    contribution_real_growth: percentInput(form.realGrowth) ?? 0,
    wealth_goal: positive(form.wealthGoal),
    income_goal: positive(form.incomeGoal),
    rebalance: form.rebalance,
    initial_by_class: form.fromPortfolio
      ? null
      : Object.fromEntries(CLASS_KEYS.map((k) => [k, Math.max(parseDecimal(form.initial[k]) ?? 0, 0)])),
    cdi_rate: percentInput(form.cdi),
    ipca_rate: percentInput(form.ipca),
    label: form.label.trim() || null,
  };
}

function projectionHorizon(run: SimulationRunDTO): string {
  const years = Number(run.params?.horizon_years ?? 0);
  return `${years} ${years === 1 ? "ano" : "anos"} · ${brl(Number(run.params?.monthly_contribution ?? 0))}/mês`;
}

function ProjectionForm({ onSubmitted }: Readonly<{ onSubmitted: (run: SimulationRunDTO) => void }>) {
  const [form, setForm] = useState<ProjectionFormState>(INITIAL_PROJECTION);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (change: Partial<ProjectionFormState>) => setForm((f) => ({ ...f, ...change }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = toProjectionRequest(form);
    if (!body) {
      setError("Informe um horizonte de 1 a 50 anos e um aporte mensal (zero é permitido).");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onSubmitted(await api.simulations.submitProjection(body));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="app-card app-card-padded" onSubmit={submit} aria-busy={saving} aria-label="Nova projeção">
      <h2 className="app-card-heading">Nova projeção</h2>
      <p className="app-card-hint">Valores em R$ de hoje: o aporte acompanha a inflação de cada cenário.</p>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      <fieldset className="app-field-grid" disabled={saving}>
        <div className="app-field">
          <label htmlFor="proj-years">Horizonte (anos)</label>
          <input id="proj-years" inputMode="numeric" value={form.horizonYears} onChange={(e) => set({ horizonYears: e.target.value })} required />
        </div>
        <div className="app-field">
          <label htmlFor="proj-monthly">Aporte mensal (R$)</label>
          <input id="proj-monthly" inputMode="decimal" value={form.monthly} onChange={(e) => set({ monthly: e.target.value })} required />
        </div>
        <div className="app-field">
          <label htmlFor="proj-growth">Crescimento real do aporte (% a.a.)</label>
          <input id="proj-growth" inputMode="decimal" value={form.realGrowth} onChange={(e) => set({ realGrowth: e.target.value })} />
        </div>
        <div className="app-field">
          <label htmlFor="proj-wealth-goal">Meta de patrimônio (R$)</label>
          <input id="proj-wealth-goal" inputMode="decimal" value={form.wealthGoal} onChange={(e) => set({ wealthGoal: e.target.value })} />
        </div>
        <div className="app-field">
          <label htmlFor="proj-income-goal">Meta de renda passiva (R$/mês)</label>
          <input id="proj-income-goal" inputMode="decimal" value={form.incomeGoal} onChange={(e) => set({ incomeGoal: e.target.value })} />
        </div>
        <div className="app-field">
          <label htmlFor="proj-cdi">CDI (% a.a., vazio = premissa)</label>
          <input id="proj-cdi" inputMode="decimal" value={form.cdi} onChange={(e) => set({ cdi: e.target.value })} />
        </div>
        <div className="app-field">
          <label htmlFor="proj-ipca">IPCA (% a.a., vazio = premissa)</label>
          <input id="proj-ipca" inputMode="decimal" value={form.ipca} onChange={(e) => set({ ipca: e.target.value })} />
        </div>
        <div className="app-field">
          <label htmlFor="proj-label">Nome (opcional)</label>
          <input id="proj-label" value={form.label} maxLength={120} onChange={(e) => set({ label: e.target.value })} />
        </div>
      </fieldset>
      <fieldset className="app-field-grid" disabled={saving}>
        <legend className="app-card-hint">Ponto de partida</legend>
        <label className="app-check">
          <input type="checkbox" checked={form.fromPortfolio} onChange={(e) => set({ fromPortfolio: e.target.checked })} />
          Partir da carteira de hoje
        </label>
        <label className="app-check">
          <input type="checkbox" checked={form.rebalance} onChange={(e) => set({ rebalance: e.target.checked })} />
          Rebalancear vendendo o excesso (com IR)
        </label>
      </fieldset>
      {!form.fromPortfolio && (
        <fieldset className="app-field-grid" disabled={saving}>
          <legend className="app-card-hint">Valor inicial por classe (R$)</legend>
          {CLASS_KEYS.map((k) => (
            <div className="app-field" key={k}>
              <label htmlFor={`proj-initial-${k}`}>{ARCA_LABELS[k]}</label>
              <input
                id={`proj-initial-${k}`}
                inputMode="decimal"
                value={form.initial[k]}
                onChange={(e) => set({ initial: { ...form.initial, [k]: e.target.value } })}
              />
            </div>
          ))}
        </fieldset>
      )}
      <div className="app-form-actions">
        <button type="submit" className="app-primary-button" disabled={saving}>
          {saving && <Spinner size="sm" />}
          <span>{saving ? "Enviando…" : "Projetar"}</span>
        </button>
      </div>
    </form>
  );
}

const PERCENTILE_COLUMNS: Array<[keyof PercentilesDTO, string]> = [
  ["p5", "5% (pessimista)"],
  ["p25", "25%"],
  ["p50", "Mediana"],
  ["p75", "75%"],
  ["p95", "95% (otimista)"],
];

function yearsLabel(months: number): string {
  if (months === 0) return "Hoje";
  const years = months / 12;
  return Number.isInteger(years) ? `${years} ${years === 1 ? "ano" : "anos"}` : `${months} meses`;
}

function GoalLine({ title, goal, money }: Readonly<{ title: string; goal: GoalOutcomeDTO; money: string }>) {
  return (
    <div className="app-card app-card-padded">
      <h3 className="app-card-heading">
        {title}: {money}
      </h3>
      <p>
        <strong>{pct(goal.probability, 0)}</strong> das trajetórias chegam lá no horizonte{" "}
        <span className="app-muted">(erro da simulação ± {points(goal.standard_error * 100, 1)} p.p.)</span>
      </p>
      {goal.months ? (
        <p className="app-muted">
          Quando chegam: em {yearsLabel(Math.round(goal.months.p50))} na mediana, entre {yearsLabel(Math.round(goal.months.p25))} e{" "}
          {yearsLabel(Math.round(goal.months.p75))} na metade central.
        </p>
      ) : (
        <p className="app-muted">Nenhuma trajetória chega à meta no horizonte.</p>
      )}
    </div>
  );
}

export function ProjectionView({ data, run }: Readonly<{ data: ProjectionDTO; run: SimulationRunDTO }>) {
  const scenarios = data.scenarios ?? [];
  const [key, setKey] = useState(scenarios.find((s) => s.scenario.name === "BASE")?.key ?? scenarios[0]?.key);
  const current = scenarios.find((s) => s.key === key);
  if (data.status !== "DONE" || !current) return <Empty title="A projeção aparece quando a simulação terminar" />;
  const pointsList = current.points ?? [];
  const labels = pointsList.map((p) => yearsLabel(p.month));
  const premises = current.premises ?? [];
  const block = Number(run.params?.mean_block_months ?? 0);

  return (
    <div className="app-page-stack">
      <ul className="app-warning-banner" aria-label="Avisos da projeção">
        {(data.warnings ?? []).map((w) => (
          <li key={w}>{w}</li>
        ))}
      </ul>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Cenário de juros</h2>
        <div className="app-button-row" role="group" aria-label="Cenários de juros">
          {scenarios.map((s) => (
            <button
              key={s.key}
              type="button"
              className={s.key === key ? "app-primary-button" : "app-secondary-button"}
              aria-pressed={s.key === key}
              onClick={() => setKey(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
        <p className="app-muted">
          CDI {pct(current.scenario.annual_cdi_rate, 2)} a.a. · IPCA {pct(current.scenario.annual_ipca_rate, 2)} a.a. ·{" "}
          {current.paths} trajetórias de {yearsLabel(current.horizon_months)}
        </p>
      </section>

      {(current.wealth_goal || current.income_goal) && (
        <div className="app-page-stack">
          {current.wealth_goal && (
            <GoalLine title="Meta de patrimônio (líquido de IR)" goal={current.wealth_goal} money={brl(current.wealth_goal.target)} />
          )}
          {current.income_goal && (
            <GoalLine title="Meta de renda passiva" goal={current.income_goal} money={`${brl(current.income_goal.target)}/mês`} />
          )}
        </div>
      )}

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Patrimônio em R$ de hoje</h2>
        <TrendChart
          title="Faixas prováveis do patrimônio ano a ano"
          labels={labels}
          series={[
            { key: "p50", label: "Mediana", color: "var(--viz-serie-1)", values: pointsList.map((p) => p.wealth.p50) },
            { key: "contributed", label: "Investido", color: "var(--app-muted, #888)", values: pointsList.map((p) => p.contributed) },
          ]}
          bands={[
            {
              key: "p5-p95",
              color: "var(--viz-serie-1)",
              low: pointsList.map((p) => p.wealth.p5),
              high: pointsList.map((p) => p.wealth.p95),
            },
            {
              key: "p25-p75",
              color: "var(--viz-serie-1)",
              low: pointsList.map((p) => p.wealth.p25),
              high: pointsList.map((p) => p.wealth.p75),
            },
          ]}
          hint="Faixa clara: 90% das trajetórias; faixa escura: a metade central. A linha é a mediana."
          format={(v) => brlCompact(v)}
        />
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Ao fim de {yearsLabel(current.horizon_months)}</h2>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Percentis ao fim do horizonte">
            <thead>
              <tr>
                <th>Medida</th>
                {PERCENTILE_COLUMNS.map(([k, label]) => (
                  <th key={k} className="app-numeric">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["Patrimônio", current.final_wealth, brl],
                  ["Patrimônio líquido de IR (vendendo tudo)", current.final_net_wealth, brl],
                  ["Renda passiva mensal", current.final_income, brl],
                  ["Queda máxima da estratégia", current.max_drawdown, (v: number) => pct(v, 1)],
                ] as Array<[string, PercentilesDTO, (v: number) => string]>
              ).map(([label, values, fmt]) => (
                <tr key={label}>
                  <td>{label}</td>
                  {PERCENTILE_COLUMNS.map(([k]) => (
                    <td key={k} className="app-numeric">
                      {fmt(values[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="app-muted">
          Investido no período: {brl(current.contributed)} · custos medianos {brl(current.fees)} · IR mediano de
          rebalanceamento {brl(current.taxes)}. Na queda máxima, 5% é o pior caso.
        </p>
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Premissas por classe</h2>
        <p className="app-card-hint">
          Prêmio e volatilidade medidos de {day(data.sample_start)} a {day(data.sample_end)} ({data.sample_months} meses), sorteados
          em blocos de {num(block, 0)} meses em média e somados ao CDI do cenário.
        </p>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Premissas por classe">
            <thead>
              <tr>
                <th>Classe</th>
                <th>Referência</th>
                <th className="app-numeric">Meta</th>
                <th className="app-numeric">Prêmio sobre o CDI a.a.</th>
                <th className="app-numeric">Volatilidade a.a.</th>
                <th className="app-numeric">Retorno no cenário a.a.</th>
                <th className="app-numeric">Renda (DY)</th>
              </tr>
            </thead>
            <tbody>
              {premises.map((p) => (
                <tr key={p.arca_class}>
                  <td>{ARCA_LABELS[p.arca_class as keyof typeof ARCA_LABELS] ?? p.arca_class}</td>
                  <td>{p.arca_class === "CAIXA" ? "CDI líquido de IR" : p.proxy}</td>
                  <td className="app-numeric">{points(data.targets?.[p.arca_class], 0)}</td>
                  <td className="app-numeric">{p.arca_class === "CAIXA" ? "—" : pct(p.excess_annual, 1, true)}</td>
                  <td className="app-numeric">{p.arca_class === "CAIXA" ? "—" : pct(p.volatility, 1)}</td>
                  <td className="app-numeric">{pct(p.expected_annual, 1)}</td>
                  <td className="app-numeric">{pct(p.income_yield, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="app-card-hint">
          A renda do Caixa conta só o rendimento acima da inflação. A probabilidade de meta tem só o erro da simulação; a
          incerteza dos próprios prêmios entra na camada bayesiana.
        </p>
      </section>
      <Reproducibility run={run} />
    </div>
  );
}

function ProjectionTab({ run }: Readonly<{ run: SimulationRunDetailDTO }>) {
  const state = useApi(`simulation-projection-${run.id}-${run.status}`, () => api.simulations.projection(run.id));
  if (run.status !== "DONE") return <RunProblem run={run} />;
  return <Async state={state}>{(data) => <ProjectionView data={data} run={run} />}</Async>;
}

// --- page -------------------------------------------------------------------------------------

function SelectedRun({
  runId,
  onStatus,
  children,
}: Readonly<{ runId: number; onStatus: () => void; children: (detail: SimulationRunDetailDTO) => ReactNode }>) {
  const [tick, setTick] = useState(0);
  const state = useApi(`simulation-${runId}-${tick}`, () => api.simulations.get(runId));
  const status = state.data?.status;

  useEffect(() => {
    if (!status || !isActive(status)) return undefined;
    const timer = setTimeout(() => {
      setTick((t) => t + 1);
      onStatus();
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [status, tick, onStatus]);

  return (
    <Async state={state} lines={6}>
      {children}
    </Async>
  );
}

/** The run chosen in the URL (`param`), or the newest one. */
function useSelected(param: string, runs: SimulationRunDTO[] | null | undefined): [number | null, (id: number) => void] {
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get(param)) || runs?.[0]?.id || null;
  const select = (id: number) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(param, String(id));
        return next;
      },
      { replace: true },
    );
  return [selected, select];
}

function BacktestPanel({ tab }: Readonly<{ tab: TabKey }>) {
  const runs = useApi("simulation-runs", () => api.simulations.list(20, "BACKTEST"));
  const [selected, select] = useSelected("run", runs.data);
  return (
    <>
      <BacktestForm
        onSubmitted={(run) => {
          select(run.id);
          runs.reload();
        }}
      />
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Simulações do passado</h2>
        <Async state={runs}>{(items) => <RunList runs={items} selected={selected} onSelect={select} />}</Async>
      </section>
      {selected !== null && (
        <SelectedRun key={`${selected}-${tab}`} runId={selected} onStatus={runs.reload}>
          {(detail) => (tab === "past" ? <PastTab detail={detail} /> : <RobustnessTab run={detail} />)}
        </SelectedRun>
      )}
    </>
  );
}

function FuturePanel() {
  const runs = useApi("simulation-projection-runs", () => api.simulations.list(20, "PROJECTION"));
  const [selected, select] = useSelected("projection", runs.data);
  return (
    <>
      <ProjectionForm
        onSubmitted={(run) => {
          select(run.id);
          runs.reload();
        }}
      />
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Projeções</h2>
        <Async state={runs}>
          {(items) => (
            <RunList runs={items} selected={selected} onSelect={select} describe={projectionHorizon} describeLabel="Horizonte" />
          )}
        </Async>
      </section>
      {selected !== null && (
        <SelectedRun key={selected} runId={selected} onStatus={runs.reload}>
          {(detail) => <ProjectionTab run={detail} />}
        </SelectedRun>
      )}
    </>
  );
}

export function SimulationPage() {
  const [tab, setTab] = useTab(TABS, "past");
  return (
    <div className="app-page">
      <PageHeader
        title="Simular carteira"
        subtitle="As suas regras de aporte no passado e as faixas prováveis do futuro. Simulação, não recomendação."
      />
      <div className="app-page-stack">
        <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Visões da simulação" />
        {tab === "future" ? <FuturePanel /> : <BacktestPanel tab={tab} />}
      </div>
    </div>
  );
}
