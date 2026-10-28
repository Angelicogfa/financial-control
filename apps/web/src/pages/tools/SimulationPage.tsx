import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  BacktestRequest,
  BacktestSummaryDTO,
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
import { brl, day, dateTime, daysAgo, parseDecimal, pct, today } from "../../utils/format";
import { ARCA_LABELS } from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { TrendChart, type TrendSeries } from "../../viz/TrendChart";

type Benchmark = NonNullable<BacktestRequest["benchmarks"]>[number];
type TabKey = "past" | "robustness";

const TABS: TabSpec<TabKey>[] = [
  { key: "past", label: "Passado" },
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

function RunList({
  runs,
  selected,
  onSelect,
}: Readonly<{ runs: SimulationRunDTO[]; selected: number | null; onSelect: (id: number) => void }>) {
  if (runs.length === 0) return <Empty title="Nenhuma simulação ainda" hint="Preencha o formulário e clique em Simular." />;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Simulações">
        <thead>
          <tr>
            <th>Simulação</th>
            <th>Período</th>
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
              <td>
                {day(String(run.params?.start ?? ""))} a {day(String(run.params?.end ?? ""))}
              </td>
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

// --- page -------------------------------------------------------------------------------------

function SelectedRun({ runId, tab, onStatus }: Readonly<{ runId: number; tab: TabKey; onStatus: () => void }>) {
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
      {(detail) => (tab === "past" ? <PastTab detail={detail} /> : <RobustnessTab run={detail} />)}
    </Async>
  );
}

export function SimulationPage() {
  const [tab, setTab] = useTab(TABS, "past");
  const [params, setParams] = useSearchParams();
  const runs = useApi("simulation-runs", () => api.simulations.list());
  const selected = Number(params.get("run")) || runs.data?.[0]?.id || null;
  const select = (id: number) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("run", String(id));
        return next;
      },
      { replace: true },
    );

  return (
    <div className="app-page">
      <PageHeader
        title="Simular carteira"
        subtitle="As suas regras de aporte reaplicadas no passado. Simulação, não recomendação: o resultado descreve o histórico."
      />
      <div className="app-page-stack">
        <BacktestForm
          onSubmitted={(run) => {
            select(run.id);
            runs.reload();
          }}
        />
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Simulações</h2>
          <Async state={runs}>{(items) => <RunList runs={items} selected={selected} onSelect={select} />}</Async>
        </section>
        {selected !== null && (
          <>
            <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Visões da simulação" />
            <SelectedRun key={`${selected}-${tab}`} runId={selected} tab={tab} onStatus={runs.reload} />
          </>
        )}
      </div>
    </div>
  );
}
