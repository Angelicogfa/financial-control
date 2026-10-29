import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  BacktestRequest,
  BacktestSummaryDTO,
  CalibrationDTO,
  CandidatesDTO,
  CandidatesRequest,
  LabDTO,
  EventOutcomeDTO,
  GeneratorCalibrationDTO,
  GoalOutcomeDTO,
  PercentilesDTO,
  ProjectionDTO,
  ProjectionRequest,
  RobustnessDTO,
  SimulationResultDTO,
  SimulationRunDetailDTO,
  SimulationRunDTO,
  SimulationStatus,
  VariantValidationDTO,
  WindowOutcomeDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { IconButton } from "../../components/RowActions";
import { KpiGrid, Lead, Notes, Section, Segmented, type KpiSpec, type Tone } from "../../components/Section";
import { Async, Empty, Spinner } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brl, brlCompact, day, dateTime, daysAgo, num, parseDecimal, pct, plural, points, today } from "../../utils/format";
import { ARCA_LABELS } from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { ColumnChart } from "../../viz/ColumnChart";
import { TrashIcon } from "../../layout/icons";
import { compareLink } from "./AssetComparePage";
import { TrendChart, type TrendSeries } from "../../viz/TrendChart";

type Benchmark = NonNullable<BacktestRequest["benchmarks"]>[number];
type TabKey = "past" | "future" | "candidates" | "robustness" | "confidence" | "lab";

const TABS: TabSpec<TabKey>[] = [
  { key: "past", label: "Passado" },
  { key: "future", label: "Futuro" },
  { key: "candidates", label: "Candidatos" },
  { key: "robustness", label: "Robustez" },
  { key: "confidence", label: "Confiança" },
  { key: "lab", label: "Laboratório" },
];

/** What sets each view apart: the question, how it is computed and when to use it. */
export const TAB_GUIDE: Record<TabKey, { question: string; method: string; use: string; from: string }> = {
  past: {
    question: "Onde eu estaria se tivesse seguido a minha estratégia desde uma data?",
    method:
      "Reaplica mês a mês as suas regras reais de aporte (metas e bandas ARCA, checklist, política) sobre os preços " +
      "históricos, com custos e IR, e compara com CDI e índices recebendo os mesmos aportes nas mesmas datas.",
    use: "Para conferir se as regras teriam funcionado. Descreve o que aconteceu; não diz nada sobre o futuro.",
    from: "Período escolhido no passado e as regras de hoje (ou as vigentes em cada data)",
  },
  future: {
    question: "Qual a faixa provável do patrimônio e da renda daqui a N anos, e com que chance chego à meta?",
    method:
      "Parte da carteira de hoje e gera milhares de futuros possíveis: sorteia trechos do histórico e parâmetros " +
      "incertos (o prêmio de cada classe sobre o CDI) e soma aos juros de três cenários (queda, premissa e alta).",
    use: "Para planejar aportes e metas. Mostra faixas e chances com intervalo, nunca um número único.",
    from: "A carteira e as premissas de hoje, projetadas para frente",
  },
  candidates: {
    question: "Que ativos que eu ainda não tenho melhorariam a carteira, e com que chance a melhora é real?",
    method:
      "Cada ativo da watchlist (e, se pedido, do screener) que passa nos filtros do aporte real é modelado contra a " +
      "sua classe, com o passado dele encolhido para não premiar sorte, e posto na carteira de hoje nas mesmas " +
      "trajetórias do Futuro, com e sem ele.",
    use: "Para escolher o que investigar a seguir. É uma lista para estudo, nunca uma ordem de compra.",
    from: "A carteira de hoje, a watchlist e o screener",
  },
  robustness: {
    question: "O resultado do Passado depende de um período sortudo ou de uma escolha de regra?",
    method:
      "Mede a simulação do Passado selecionada dentro de crises conhecidas, aplica choques à alocação final e repete " +
      "o cálculo com outras bandas e com e sem rebalanceamento, mostrando todas as variantes.",
    use: "Para não escolher uma regra por sorte. Usa a mesma simulação da aba Passado.",
    from: "A simulação do Passado selecionada",
  },
  confidence: {
    question: "As chances que a aba Futuro mostra costumam se confirmar?",
    method:
      "Em cada mês do passado, cada gerador de cenários prevê os 12 meses seguintes usando só os dados até ali; a " +
      "previsão é comparada com o que aconteceu (cobertura, PIT, Brier, log score) e define os pesos da combinação.",
    use: "Para saber quanto confiar nas probabilidades do Futuro. Roda sozinha toda semana.",
    from: "Todo o histórico guardado, mês a mês",
  },
  lab: {
    question: "Algum modelo de regime ou de risco prevê o mês seguinte melhor que uma regra simples?",
    method:
      "Modelos de regime (HMM, mistura gaussiana) e de risco (EWMA, GARCH) preveem o retorno do mês seguinte, " +
      "sempre só com o passado, contra a média e a volatilidade históricas; só passa quem vence com folga, " +
      "descontado o número de tentativas e estável quando a data de corte muda.",
    use: "Para saber se vale condicionar a simulação a regimes. 'Nenhum modelo passou' é um resultado válido.",
    from: "O histórico da carteira-modelo, mês a mês",
  },
};

function TabGuide({ tab }: Readonly<{ tab: TabKey }>) {
  const guide = TAB_GUIDE[tab];
  return (
    <section className="app-card app-card-padded app-guide" aria-label="Sobre esta aba">
      <span className="app-eyebrow">A pergunta desta aba</span>
      <h2 className="app-guide-question">{guide.question}</h2>
      <p className="app-guide-method">{guide.method}</p>
      <dl className="app-guide-facts">
        <div>
          <dt>Parte de:</dt>
          <dd>{guide.from}</dd>
        </div>
        <div>
          <dt>Quando usar:</dt>
          <dd>{guide.use}</dd>
        </div>
      </dl>
      <details>
        <summary>Comparar as seis abas</summary>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Comparação das abas">
            <thead>
              <tr>
                <th>Aba</th>
                <th>Pergunta</th>
                <th>Parte de</th>
                <th>Quando usar</th>
              </tr>
            </thead>
            <tbody>
              {TABS.map((t) => (
                <tr key={t.key} aria-current={t.key === tab ? "true" : undefined}>
                  <td>{t.label}</td>
                  <td className="app-cell-wrap">{TAB_GUIDE[t.key].question}</td>
                  <td className="app-cell-wrap">{TAB_GUIDE[t.key].from}</td>
                  <td className="app-cell-wrap">{TAB_GUIDE[t.key].use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

/** A form that folds once there are results, so the result leads the page. */
function FormCard({
  title,
  hint,
  open,
  children,
}: Readonly<{ title: string; hint?: string; open: boolean; children: ReactNode }>) {
  return (
    <details className="app-card app-disclosure" open={open}>
      <summary>
        {title}
        {hint && <small>{hint}</small>}
      </summary>
      <div className="app-disclosure-body">{children}</div>
    </details>
  );
}

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

function BacktestForm({
  onSubmitted,
  open = true,
}: Readonly<{ onSubmitted: (run: SimulationRunDTO) => void; open?: boolean }>) {
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
    <FormCard title="Nova simulação" hint="Período, aporte, regras e referências" open={open}>
      <form onSubmit={submit} aria-busy={saving} aria-label="Nova simulação">
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
          <legend>Regras</legend>
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
          <legend>Comparar com o mesmo fluxo de aportes em</legend>
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
    </FormCard>
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
  onDeleted,
  describe = backtestPeriod,
  describeLabel = "Período",
}: Readonly<{
  runs: SimulationRunDTO[];
  selected: number | null;
  onSelect: (id: number) => void;
  /** After a run is deleted for good (Phase 40.4). */
  onDeleted: (id: number) => void;
  describe?: (run: SimulationRunDTO) => string;
  describeLabel?: string;
}>) {
  const [deleting, setDeleting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const remove = async (run: SimulationRunDTO) => {
    const name = run.label || `Simulação #${run.id}`;
    if (!window.confirm(`Excluir "${name}"? A simulação e o resultado somem e não há como recuperar.`)) return;
    setDeleting(run.id);
    setError(null);
    try {
      await api.simulations.remove(run.id);
      onDeleted(run.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeleting(null);
    }
  };
  if (runs.length === 0) return <Empty title="Nenhuma simulação ainda" hint="Preencha o formulário e clique em Simular." />;
  return (
    <div className="app-table-wrap">
      {error && <p className="app-error-banner">{error}</p>}
      <table className="app-table" aria-label="Simulações">
        <thead>
          <tr>
            <th>Simulação</th>
            <th>{describeLabel}</th>
            <th>Status</th>
            <th>Pedida em</th>
            <th aria-label="Ações" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} aria-selected={run.id === selected}>
              <td>
                <button
                  type="button"
                  className="app-link-button"
                  aria-current={run.id === selected ? "true" : undefined}
                  onClick={() => onSelect(run.id)}
                >
                  {run.label || `Simulação #${run.id}`}
                </button>
                {run.id === selected && <span className="app-muted"> · em exibição</span>}
              </td>
              <td>{describe(run)}</td>
              <td>
                <StatusBadge status={run.status} />
              </td>
              <td>{dateTime(run.created_at)}</td>
              <td className="app-row-actions">
                <IconButton
                  label={`Excluir ${run.label || `simulação #${run.id}`}`}
                  busyLabel="Excluindo…"
                  icon={<TrashIcon />}
                  danger
                  busy={deleting === run.id}
                  onClick={() => void remove(run)}
                />
              </td>
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
      {run.error?.includes("InsufficientHistory") && (
        <>
          {" "}
          <Link className="app-link" to="/settings/market-data">
            Carregar o histórico em Dados de mercado
          </Link>
        </>
      )}
    </p>
  );
}

/** What the past says, in words: where the money ended against the same flow in the CDI. */
export function pastStory(series: SimulationResultDTO[]): { tone: Tone; lines: string[]; cashShare: number } {
  const strategy = series.find((r) => r.key === "strategy");
  const points = strategy?.points ?? [];
  const last = points[points.length - 1];
  if (!strategy || !last) return { tone: "neutral", lines: [], cashShare: 0 };
  const s = strategy.summary;
  const cdi = series.find((r) => r.key === "benchmark:CDI");
  const cashShare = last.market_value > 0 ? ((last.by_class?.CAIXA ?? 0) + last.cash) / last.market_value : 0;
  const lines = [
    `De ${day(points[0].day)} a ${day(last.day)}, com ${brl(s.contributed)} aportados no total, a estratégia ` +
      `chegou a ${brl(s.final_value)}` +
      (cdi
        ? `, ${brl(Math.abs(s.final_value - cdi.summary.final_value))} ${
            s.final_value >= cdi.summary.final_value ? "acima" : "abaixo"
          } do mesmo fluxo aplicado no CDI.`
        : "."),
  ];
  const others = series.filter((r) => r.key !== "strategy");
  const best = [...others].sort((a, b) => b.summary.final_value - a.summary.final_value)[0];
  const facts = [`TIR de ${pct(s.money_weighted_return, 2)} a.a.`, `queda máxima de ${pct(s.max_drawdown, 1)}`];
  if (best && best.summary.final_value > s.final_value) {
    facts.push(`a melhor referência foi ${best.label} (${brlCompact(best.summary.final_value)})`);
  }
  lines.push(`${facts.join(", ").replace(/^./, (c) => c.toUpperCase())}.`);
  if (cashShare > 0.9) {
    lines.push(
      `${pct(cashShare, 0)} do patrimônio terminou em Caixa: os aportes quase não foram para ações, FIIs ou ` +
        "exterior. Isso costuma acontecer quando os ativos não passam na elegibilidade nas datas simuladas; " +
        "um checklist respondido há pouco só vale a partir da data da resposta.",
    );
  }
  const tone: Tone = cashShare > 0.9 ? "caution" : cdi ? (s.final_value >= cdi.summary.final_value ? "positive" : "negative") : "neutral";
  return { tone, lines, cashShare };
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
    { key: "contributed", label: "Investido", color: "var(--app-text-subtle)", values: points.map((p) => p.contributed) },
  ];
  const last = points[points.length - 1];
  const story = pastStory(series);
  const s = strategy.summary;
  const kpis: KpiSpec[] = [
    { label: "Patrimônio final", value: brlCompact(s.final_value), note: `${brlCompact(s.contributed)} aportados` },
    {
      label: "Ganho",
      value: brlCompact(s.gain),
      tone: s.gain >= 0 ? "positive" : "negative",
      note: `${pct(s.contributed > 0 ? s.gain / s.contributed : 0, 1, true)} sobre o aportado`,
    },
    { label: "TIR dos aportes", value: `${pct(s.money_weighted_return, 2)} a.a.`, note: `TWR ${pct(s.annual_twr, 2)} a.a.` },
    { label: "Queda máxima", value: pct(s.max_drawdown, 1), note: `volatilidade ${pct(s.volatility, 1)} a.a.` },
    { label: "Custos e IR", value: brlCompact(s.fees + (s.taxes ?? 0)), note: plural(s.trades, "operação", "operações") },
  ];
  const notes = [
    ...(strategy.survivorship_bias
      ? [
          "Inclui ativos do catálogo atual da B3: só as empresas que sobreviveram até hoje aparecem, e o passado " +
            "parece melhor do que foi (viés de sobrevivência).",
        ]
      : []),
    ...(unavailable.length > 0 ? [`Sem preço no período, ficaram de fora: ${unavailable.join(", ")}.`] : []),
    "Todas as linhas recebem os mesmos aportes nas mesmas datas; a diferença é só onde o dinheiro foi aplicado.",
    "Descreve o que teria acontecido com as regras escolhidas; não diz nada sobre o futuro.",
  ];
  return (
    <div className="app-page-stack">
      <Lead tone={story.tone}>
        {story.lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </Lead>
      <KpiGrid items={kpis} label="Indicadores da estratégia" />
      <Section title="Patrimônio com o mesmo fluxo de aportes" subtitle="Mês a mês, estratégia e referências.">
        <TrendChart
          title="Patrimônio da estratégia e das referências mês a mês"
          labels={labels}
          series={lines}
          hint="Passe o mouse para ler o patrimônio de cada linha no mês."
          format={(v) => brl(v)}
          compact={brlCompact}
        />
      </Section>
      <Section title="Estratégia contra as referências" subtitle="As mesmas métricas para cada destino do mesmo fluxo de aportes.">
        <SummaryTable results={series} />
      </Section>
      <Section title="Onde o dinheiro terminou" subtitle={`Alocação por classe em ${day(last.day)}.`}>
        <BarList
          label="Alocação final por classe"
          bars={Object.entries(last.by_class ?? {}).map(([cls, value]) => ({
            id: cls,
            label: ARCA_LABELS[cls as keyof typeof ARCA_LABELS] ?? cls,
            share: last.market_value > 0 ? value / last.market_value : 0,
            value: `${brl(value)} · ${pct(last.market_value > 0 ? value / last.market_value : 0, 0)}`,
          }))}
        />
      </Section>
      <Notes items={notes} tone={strategy.survivorship_bias ? "caution" : "neutral"} />
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
  const worst = crises
    .map((c) => ({ c, o: c.outcomes?.strategy }))
    .filter((x) => x.o?.covered)
    .sort((a, b) => (a.o?.return_rate ?? 0) - (b.o?.return_rate ?? 0))[0];
  const spread = variants.length > 1 ? (data.annual_twr_distribution.maximum ?? 0) - (data.annual_twr_distribution.minimum ?? 0) : null;
  return (
    <div className="app-page-stack">
      <Lead tone={data.validation ? (data.validation.passed ? "positive" : "neutral") : "neutral"}>
        <p>
          {worst
            ? `A pior crise dentro do período foi ${worst.c.label}, com ${pct(worst.o?.return_rate, 1, true)} para a estratégia e queda máxima de ${pct(worst.o?.max_drawdown, 1)}.`
            : "Nenhuma crise histórica conhecida cai dentro do período simulado."}
        </p>
        <p>
          {spread !== null
            ? `As ${variants.length} variantes de regra ficaram entre ${pct(data.annual_twr_distribution.minimum, 2)} e ${pct(data.annual_twr_distribution.maximum, 2)} a.a. (${pct(spread, 2)} de diferença). `
            : ""}
          {data.validation
            ? data.validation.passed
              ? "A melhor variante passou nos testes contra a sorte."
              : "Não há evidência de que a melhor variante seja melhor por mérito, e não por sorte."
            : ""}
        </p>
      </Lead>

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
      <Notes items={warnings} label="Avisos de amostra" tone="neutral" />
      {data.validation && <VariantValidation validation={data.validation} />}
    </div>
  );
}

/** Phase 33.8: the best rule variant against the luck of the trials. */
function VariantValidation({ validation }: Readonly<{ validation: VariantValidationDTO }>) {
  return (
    <section className="app-card app-card-padded" aria-label="Validação estatística">
      <div className="health-pillar-head">
        <h2 className="app-card-heading">Validação estatística da melhor variante</h2>
        <Badge tone={validation.passed ? "success" : "warning"}>
          {validation.passed ? "Passou nos três testes" : "Sem evidência"}
        </Badge>
      </div>
      <p>{validation.verdict}</p>
      <dl className="simulation-validation">
        <div>
          <dt>Melhor variante</dt>
          <dd>{validation.best_label}</dd>
        </div>
        <div>
          <dt>Sharpe a.a. (sobre o CDI)</dt>
          <dd>
            {num(validation.best_sharpe_annual, 2)}{" "}
            <span className="app-muted">contra {num(validation.expected_max_sharpe_annual, 2)} esperado do acaso</span>
          </dd>
        </div>
        <div>
          <dt>Sharpe deflacionado</dt>
          <dd>
            {pct(validation.deflated_probability, 0)} <span className="app-muted">({validation.trials} tentativas, ≥ 95% para passar)</span>
          </dd>
        </div>
        <div>
          <dt>Probabilidade de ajuste ao ruído (PBO)</dt>
          <dd>
            {validation.pbo == null ? "—" : pct(validation.pbo, 0)}{" "}
            <span className="app-muted">(abaixo de 50% para passar; {validation.pbo_combinations} divisões)</span>
          </dd>
        </div>
        <div>
          <dt>Chance de superar a regra atual</dt>
          <dd>
            {validation.gate_probability == null ? "—" : pct(validation.gate_probability, 0)}{" "}
            <span className="app-muted">(≥ 95% para passar)</span>
          </dd>
        </div>
      </dl>
      <p className="app-card-hint">
        Todas as variantes testadas até hoje entram na conta: quanto mais tentativas, maior o Sharpe que o acaso sozinho
        produziria. Retornos mensais sem os aportes, acima do CDI, em {validation.observations} meses.
      </p>
    </section>
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
  generator: NonNullable<ProjectionRequest["generator"]>;
  label: string;
}

const GENERATOR_OPTIONS: Array<[NonNullable<ProjectionRequest["generator"]>, string]> = [
  ["STACKED", "Combinação calibrada (recomendado)"],
  ["BOOTSTRAP", "Só o bootstrap em blocos"],
  ["BAYESIAN_BOOTSTRAP", "Só o bootstrap bayesiano"],
  ["BAYESIAN_NORMAL", "Só a normal bayesiana"],
];

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
  generator: "STACKED",
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
    generator: form.generator,
    label: form.label.trim() || null,
  };
}

function projectionHorizon(run: SimulationRunDTO): string {
  const years = Number(run.params?.horizon_years ?? 0);
  return `${years} ${years === 1 ? "ano" : "anos"} · ${brl(Number(run.params?.monthly_contribution ?? 0))}/mês`;
}

function ProjectionForm({
  onSubmitted,
  open = true,
}: Readonly<{ onSubmitted: (run: SimulationRunDTO) => void; open?: boolean }>) {
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
    <FormCard title="Nova projeção" hint="Horizonte, aporte, metas e juros" open={open}>
      <form onSubmit={submit} aria-busy={saving} aria-label="Nova projeção">
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
            <label htmlFor="proj-generator">Gerador de cenários</label>
            <select
              id="proj-generator"
              value={form.generator}
              onChange={(e) => set({ generator: e.target.value as ProjectionFormState["generator"] })}
            >
              {GENERATOR_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="app-field">
            <label htmlFor="proj-label">Nome (opcional)</label>
            <input id="proj-label" value={form.label} maxLength={120} onChange={(e) => set({ label: e.target.value })} />
          </div>
        </fieldset>
        <fieldset className="app-field-grid" disabled={saving}>
          <legend>Ponto de partida</legend>
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
            <legend>Valor inicial por classe (R$)</legend>
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
    </FormCard>
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

const GENERATOR_NAMES: Record<string, string> = {
  BOOTSTRAP: "Bootstrap em blocos",
  BAYESIAN_BOOTSTRAP: "Bootstrap bayesiano",
  BAYESIAN_NORMAL: "Normal bayesiana",
  STACKED: "Combinação",
};

/** How the interval was built: the disagreement between generators, if any. */
function ChanceDetail({ chance }: Readonly<{ chance: { by_generator?: Record<string, number> } }>) {
  const shares = Object.entries(chance.by_generator ?? {});
  if (shares.length < 2) return null;
  return (
    <p className="app-muted">
      Por gerador: {shares.map(([g, p]) => `${GENERATOR_NAMES[g] ?? g} ${pct(p, 0)}`).join(" · ")}. O intervalo de 90%
      cobre essa divergência, o número finito de trajetórias e a incerteza dos parâmetros.
    </p>
  );
}

function EventList({ events }: Readonly<{ events: EventOutcomeDTO[] }>) {
  if (events.length === 0) return null;
  return (
    <section className="app-card app-card-padded">
      <h2 className="app-card-heading">Outras chances da estratégia</h2>
      <ul aria-label="Outras chances">
        {events.map((e) => (
          <li key={e.key}>
            {e.label}: <strong>{pct(e.probability, 0)}</strong> ({pct(e.low, 0)} a {pct(e.high, 0)})
          </li>
        ))}
      </ul>
    </section>
  );
}

function GoalLine({ title, goal, money }: Readonly<{ title: string; goal: GoalOutcomeDTO; money: string }>) {
  return (
    <div className="app-card app-card-padded">
      <h3 className="app-card-heading">
        {title}: {money}
      </h3>
      <p>
        <strong>{pct(goal.probability, 0)}</strong> de chance de chegar lá no horizonte{" "}
        <span>
          ({pct(goal.low, 0)} a {pct(goal.high, 0)})
        </span>
      </p>
      <ChanceDetail chance={goal} />
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
  const horizon = yearsLabel(current.horizon_months);
  const kpis: KpiSpec[] = [
    {
      label: `Patrimônio em ${horizon} (mediana)`,
      value: brlCompact(current.final_wealth.p50),
      note: `em R$ de hoje; ${brlCompact(current.contributed)} aportados`,
    },
    {
      label: "Faixa de 90%",
      value: `${brlCompact(current.final_wealth.p5)} a ${brlCompact(current.final_wealth.p95)}`,
      note: "5% das trajetórias ficam abaixo",
    },
    { label: "Renda passiva mensal (mediana)", value: brlCompact(current.final_income.p50), note: "ao fim do horizonte" },
    ...(current.wealth_goal
      ? [
          {
            label: "Chance da meta de patrimônio",
            value: pct(current.wealth_goal.probability, 0),
            note: `${pct(current.wealth_goal.low, 0)} a ${pct(current.wealth_goal.high, 0)} · meta ${brlCompact(current.wealth_goal.target)}`,
            tone: (current.wealth_goal.probability >= 0.7 ? "positive" : current.wealth_goal.probability < 0.4 ? "negative" : "caution") as Tone,
          },
        ]
      : []),
    { label: "Pior queda (5% dos casos)", value: pct(current.max_drawdown.p5, 1), note: "queda máxima no caminho" },
  ];

  return (
    <div className="app-page-stack">
      <Lead>
        <p>
          No cenário {current.label.toLowerCase()}, a carteira chega a <strong>{brlCompact(current.final_wealth.p50)}</strong>{" "}
          em {horizon} na mediana, em reais de hoje, com 90% das trajetórias entre {brlCompact(current.final_wealth.p5)} e{" "}
          {brlCompact(current.final_wealth.p95)}.
        </p>
        <p>
          {current.wealth_goal
            ? `A chance de chegar à meta de ${brlCompact(current.wealth_goal.target)} é de ${pct(current.wealth_goal.probability, 0)} (entre ${pct(current.wealth_goal.low, 0)} e ${pct(current.wealth_goal.high, 0)}). `
            : ""}
          Faixas, não promessa: o futuro pode ter prêmios menores e crises mais longas que o histórico amostrado.
        </p>
      </Lead>
      <KpiGrid items={kpis} label="Indicadores da projeção" />

      <Section
        title="Cenário de juros"
        subtitle="Os três cenários usam as mesmas trajetórias de prêmio; muda só o CDI e o IPCA."
        actions={
          <Segmented
            options={scenarios.map((s) => [s.key, s.label] as [string, string])}
            value={key ?? ""}
            onChange={setKey}
            label="Cenários de juros"
          />
        }
      >
        <p className="app-muted">
          CDI {pct(current.scenario.annual_cdi_rate, 2)} a.a. · IPCA {pct(current.scenario.annual_ipca_rate, 2)} a.a. ·{" "}
          {current.paths} trajetórias de {yearsLabel(current.horizon_months)}
        </p>
        {(current.generators ?? []).length > 0 && (
          <p className="app-muted">
            Geradores:{" "}
            {(current.generators ?? []).map((g) => `${g.label} ${pct(g.weight, 0)}`).join(" · ")}
            {data.calibration_run ? ` (pesos da calibração #${data.calibration_run})` : ""}.
            {current.prior_months != null &&
              ` O prior conservador pesa o equivalente a ${num(current.prior_months, 0)} meses de dados.`}
          </p>
        )}
      </Section>

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

      <EventList events={current.events ?? []} />

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Patrimônio em R$ de hoje</h2>
        <TrendChart
          title="Faixas prováveis do patrimônio ano a ano"
          labels={labels}
          series={[
            { key: "p50", label: "Mediana", color: "var(--viz-serie-1)", values: pointsList.map((p) => p.wealth.p50) },
            { key: "contributed", label: "Investido", color: "var(--app-text-subtle)", values: pointsList.map((p) => p.contributed) },
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
          format={(v) => brl(v)}
          compact={brlCompact}
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
                <th className="app-numeric">Prêmio histórico sobre o CDI a.a.</th>
                <th className="app-numeric">Alvo do prior</th>
                <th className="app-numeric">Prêmio a posteriori</th>
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
                  <td className="app-numeric">{p.prior_excess_annual == null ? "—" : pct(p.prior_excess_annual, 1, true)}</td>
                  <td className="app-numeric">
                    {p.posterior_excess_annual == null ? "—" : pct(p.posterior_excess_annual, 1, true)}
                  </td>
                  <td className="app-numeric">{p.arca_class === "CAIXA" ? "—" : pct(p.volatility, 1)}</td>
                  <td className="app-numeric">{pct(p.expected_annual, 1)}</td>
                  <td className="app-numeric">{pct(p.income_yield, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="app-card-hint">
          A renda do Caixa conta só o rendimento acima da inflação. O prêmio a posteriori é o histórico puxado para o alvo
          conservador (CDI + 3% em ações, CDI + 2% em FIIs) na medida em que os dados não o sustentam; a normal bayesiana
          sorteia os prêmios em torno dele em cada trajetória.
        </p>
      </section>
      <Notes items={(data.warnings ?? [])} label="Avisos da projeção" tone="neutral" />
      <Reproducibility run={run} />
    </div>
  );
}

function ProjectionTab({ run }: Readonly<{ run: SimulationRunDetailDTO }>) {
  const state = useApi(`simulation-projection-${run.id}-${run.status}`, () => api.simulations.projection(run.id));
  if (run.status !== "DONE") return <RunProblem run={run} />;
  return <Async state={state}>{(data) => <ProjectionView data={data} run={run} />}</Async>;
}

// --- confidence -------------------------------------------------------------------------------

const CALIBRATION_STATUS: Record<GeneratorCalibrationDTO["status"], { label: string; tone: string }> = {
  CALIBRATED: { label: "Calibrado", tone: "success" },
  MISCALIBRATED: { label: "Mal calibrado", tone: "danger" },
  INCONCLUSIVE: { label: "Inconclusivo", tone: "warning" },
};

export function CalibrationView({ data }: Readonly<{ data: CalibrationDTO }>) {
  const generators = data.generators ?? [];
  const stacked = generators.find((g) => g.key === "STACKED");
  const origins = data.origins ?? [];
  const calibrated = generators.filter((g) => g.key !== "STACKED" && g.status === "CALIBRATED").length;
  const total = generators.filter((g) => g.key !== "STACKED").length;
  return (
    <div className="app-page-stack">
      <Lead tone={stacked?.status === "CALIBRATED" ? "positive" : stacked?.status === "MISCALIBRATED" ? "negative" : "caution"}>
        <p>
          {stacked
            ? `O intervalo de 90% da combinação conteve o realizado em ${pct(stacked.coverage, 0)} das ${data.windows} previsões de 12 meses (o esperado é 90%): ${CALIBRATION_STATUS[stacked.status].label.toLowerCase()}.`
            : `${data.windows} previsões de 12 meses comparadas com o realizado.`}
        </p>
        <p>
          {`${plural(calibrated, "gerador calibrado", "geradores calibrados")} de ${total}. `}
          {stacked?.status === "INCONCLUSIVE"
            ? "Com cerca de " + num(data.effective_windows, 0) + " janelas independentes, o histórico ainda não separa um gerador bom de um ruim; use as chances do Futuro com folga."
            : "As chances do Futuro herdam essa calibração."}
        </p>
      </Lead>
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Geradores de cenário</h2>
        <p className="app-card-hint">
          {data.windows} previsões de 12 meses, de {day(data.first_origin)} a {day(data.last_origin)} (cerca de{" "}
          {num(data.effective_windows, 0)} janelas independentes). Um intervalo de 90% bem calibrado contém o realizado em
          cerca de 90% das vezes.
        </p>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Calibração dos geradores">
            <thead>
              <tr>
                <th>Gerador</th>
                <th className="app-numeric">Peso na combinação</th>
                <th className="app-numeric">Cobertura do intervalo de 90%</th>
                <th>Situação</th>
                <th className="app-numeric">PIT médio</th>
                <th className="app-numeric">Brier: perder 10%</th>
                <th className="app-numeric">Brier: bater o CDI</th>
                <th className="app-numeric">Log score</th>
              </tr>
            </thead>
            <tbody>
              {generators.map((g) => (
                <tr key={g.key}>
                  <td>{g.label}</td>
                  <td className="app-numeric">{g.key === "STACKED" ? "—" : pct(g.weight, 0)}</td>
                  <td className="app-numeric">
                    {pct(g.coverage, 0)}
                    <div className="app-muted">
                      {pct(g.coverage_low, 0)} a {pct(g.coverage_high, 0)}
                    </div>
                  </td>
                  <td>
                    <Badge tone={CALIBRATION_STATUS[g.status].tone}>{CALIBRATION_STATUS[g.status].label}</Badge>
                  </td>
                  <td className="app-numeric">{num(g.mean_pit, 2)}</td>
                  <td className="app-numeric">{num(g.brier_loss, 3)}</td>
                  <td className="app-numeric">{num(g.brier_beat_cdi, 3)}</td>
                  <td className="app-numeric">{num(g.log_score, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="app-card-hint">
          PIT médio perto de 0,5 = sem viés; Brier menor e log score maior = melhor. O intervalo da cobertura leva em
          conta que as janelas se sobrepõem; quando ele é largo demais, a situação é inconclusiva, e isso é um resultado,
          não um erro.
        </p>
      </section>
      {stacked && (
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Onde o realizado caiu na previsão da combinação</h2>
          <ColumnChart
            title="Histograma do PIT da combinação"
            columns={(stacked.pit_histogram ?? []).map((value, i) => ({ label: `${i * 10}–${i * 10 + 10}%`, value }))}
            hint="Colunas parecidas = bem calibrado. Concentração nas pontas = intervalos estreitos demais; no meio = largos demais."
            format={(v) => `${v} janelas`}
          />
        </section>
      )}
      {origins.length > 1 && (
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Previsto contra realizado (12 meses)</h2>
          <TrendChart
            title="Retorno de 12 meses previsto pela combinação e realizado, por origem"
            labels={origins.map((o) => day(o.origin))}
            series={[
              {
                key: "realized",
                label: "Realizado",
                color: "var(--viz-serie-2)",
                values: origins.map((o) => o.realized),
              },
              {
                key: "p50",
                label: "Mediana prevista",
                color: "var(--viz-serie-1)",
                values: origins.map((o) => o.forecasts?.STACKED?.p50 ?? null),
              },
            ]}
            bands={[
              {
                key: "p5-p95",
                color: "var(--viz-serie-1)",
                low: origins.map((o) => o.forecasts?.STACKED?.p5 ?? 0),
                high: origins.map((o) => o.forecasts?.STACKED?.p95 ?? 0),
              },
            ]}
            hint="Faixa: intervalo de 90% previsto em cada origem; linha: o que aconteceu nos 12 meses seguintes."
            format={(v) => pct(v, 0)}
          />
        </section>
      )}
      <Notes items={(data.warnings ?? [])} label="Avisos da calibração" tone="neutral" />
    </div>
  );
}

function ConfidencePanel() {
  const [tick, setTick] = useState(0);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = useApi(`simulation-calibration-${tick}`, () => api.simulations.calibration());
  const pending = state.data?.pending_run_id ?? null;

  useEffect(() => {
    if (pending === null) return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [pending, tick]);

  const recalibrate = async () => {
    setRequesting(true);
    setError(null);
    try {
      await api.simulations.submitCalibration();
      setTick((t) => t + 1);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRequesting(false);
    }
  };

  return (
    <>
      <Section
        title="Calibração"
        subtitle={
          pending !== null
            ? "Na fila do worker; a página atualiza sozinha."
            : state.data?.finished_at
              ? `Calculada em ${dateTime(state.data.finished_at)}. Roda sozinha toda semana e após cada carga do histórico.`
              : "Roda sozinha toda semana e após cada carga do histórico."
        }
        actions={
          <button
            type="button"
            className="app-primary-button"
            disabled={requesting || pending !== null}
            onClick={recalibrate}
          >
            {(requesting || pending !== null) && <Spinner size="sm" />}
            <span>Recalcular agora</span>
          </button>
        }
      >
        {error && (
          <p className="app-error-banner" role="alert">
            {error}
          </p>
        )}
      </Section>
      <Async state={state}>
        {(data) =>
          data.run_id === null || data.run_id === undefined ? (
            <Empty
              title="Ainda não há calibração"
              hint="Ela roda depois de cada carga do histórico; clique em Recalcular agora para rodar já."
            />
          ) : (
            <CalibrationView data={data} />
          )
        }
      </Async>
    </>
  );
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
function useSelected(param: string, runs: SimulationRunDTO[] | null | undefined): [number | null, (id: number | null) => void] {
  const [params, setParams] = useSearchParams();
  const selected = Number(params.get(param)) || runs?.[0]?.id || null;
  /** `null` drops the choice (after a delete), so the newest run shows. */
  const select = (id: number | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (id === null) next.delete(param);
        else next.set(param, String(id));
        return next;
      },
      { replace: true },
    );
  return [selected, select];
}

function BacktestPanel({ tab }: Readonly<{ tab: "past" | "robustness" }>) {
  const runs = useApi("simulation-runs", () => api.simulations.list(20, "BACKTEST"));
  const [selected, select] = useSelected("run", runs.data);
  return (
    <>
      <BacktestForm
        open={(runs.data ?? []).length === 0}
        onSubmitted={(run) => {
          select(run.id);
          runs.reload();
        }}
      />
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Simulações do passado</h2>
        <p className="app-card-hint">Escolha uma linha para ver o resultado abaixo.</p>
        <Async state={runs}>{(items) => <RunList runs={items} selected={selected} onSelect={select} onDeleted={(id) => {
              if (id === selected) select(null);
              runs.reload();
            }} />}</Async>
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
        open={(runs.data ?? []).length === 0}
        onSubmitted={(run) => {
          select(run.id);
          runs.reload();
        }}
      />
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Projeções</h2>
        <p className="app-card-hint">Escolha uma linha para ver o resultado abaixo.</p>
        <Async state={runs}>
          {(items) => (
            <RunList runs={items} selected={selected} onSelect={select} onDeleted={(id) => {
              if (id === selected) select(null);
              runs.reload();
            }} describe={projectionHorizon} describeLabel="Horizonte" />
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

// --- laboratory -------------------------------------------------------------------------------

export function LabView({ data }: Readonly<{ data: LabDTO }>) {
  const models = data.models ?? [];
  const regime = data.regime ?? [];
  const approved = data.approved ?? [];
  return (
    <div className="app-page-stack">
      <section className="app-card app-card-padded" aria-label="Veredito do laboratório">
        <div className="health-pillar-head">
          <h2 className="app-card-heading">Veredito</h2>
          <Badge tone={approved.length ? "success" : "neutral"}>
            {approved.length
              ? plural(approved.length, "modelo passou", "modelos passaram")
              : "Nenhum modelo passou"}
          </Badge>
        </div>
        <p className="app-lead-text">{data.verdict}</p>
        <p className="app-muted">
          Previsões de {day(data.first_forecast)} a {day(data.last_forecast)} · {data.trials} tentativas registradas · PBO do
          conjunto {data.pbo == null ? "—" : pct(data.pbo, 0)} · escolhido perde para a referência em{" "}
          {data.loss_probability == null ? "—" : pct(data.loss_probability, 0)} das divisões
        </p>
      </section>
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Modelos</h2>
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Modelos do laboratório">
            <thead>
              <tr>
                <th>Modelo</th>
                <th className="app-numeric">Ganho de log score por mês</th>
                <th className="app-numeric">Chance de superar a referência</th>
                <th className="app-numeric">Sharpe deflacionado</th>
                <th>Estável</th>
                <th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.key}>
                  <td>{m.label}</td>
                  <td className="app-numeric">{num(m.mean_gain, 4)}</td>
                  <td className="app-numeric">{pct(m.gate_probability, 0)}</td>
                  <td className="app-numeric">{pct(m.deflated_probability, 0)}</td>
                  <td>{m.stable ? "Sim" : "Não"}</td>
                  <td>
                    <Badge tone={m.passed ? "success" : "warning"}>{m.passed ? "Passou" : "Não passou"}</Badge>
                    {(m.reasons ?? []).length > 0 && <div className="app-muted">{(m.reasons ?? []).join("; ")}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="app-card-hint">
          Ganho positivo = a densidade prevista pelo modelo explica melhor o mês seguinte que a normal com a média e a
          volatilidade históricas. Para passar: chance de superar de 95% ou mais, Sharpe deflacionado de 95% ou mais,
          escolhido perdendo fora da amostra em menos de 20% das divisões e resultado estável com o corte deslocado.
        </p>
      </section>
      {regime.length > 1 && (
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Probabilidade do regime de estresse (HMM de 2 estados)</h2>
          <TrendChart
            title="Probabilidade do regime de estresse mês a mês"
            labels={regime.map((p) => day(p.month))}
            series={[
              {
                key: "stress",
                label: "Estresse",
                color: "var(--viz-serie-2)",
                values: regime.map((p) => p.stress_probability),
              },
            ]}
            hint="Probabilidade filtrada: usa só os meses até cada data. Descreve o passado; não é previsão de queda."
            format={(v) => pct(v, 0)}
          />
        </section>
      )}
      <Notes items={(data.warnings ?? [])} label="Avisos do laboratório" tone="neutral" />
    </div>
  );
}

function LabPanel() {
  const [tick, setTick] = useState(0);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = useApi(`simulation-lab-${tick}`, () => api.simulations.lab());
  const pending = state.data?.pending_run_id ?? null;

  useEffect(() => {
    if (pending === null) return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [pending, tick]);

  const run = async () => {
    setRequesting(true);
    setError(null);
    try {
      await api.simulations.submitLab();
      setTick((t) => t + 1);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRequesting(false);
    }
  };

  return (
    <>
      <Section
        title="Laboratório de ML"
        subtitle={
          pending !== null
            ? "Na fila do worker; a página atualiza sozinha."
            : state.data?.finished_at
              ? `Última rodada em ${dateTime(state.data.finished_at)}. Leva alguns segundos.`
              : "Leva alguns segundos."
        }
        actions={
          <button type="button" className="app-primary-button" disabled={requesting || pending !== null} onClick={run}>
            {(requesting || pending !== null) && <Spinner size="sm" />}
            <span>Rodar o laboratório</span>
          </button>
        }
      >
        {error && (
          <p className="app-error-banner" role="alert">
            {error}
          </p>
        )}
      </Section>
      <Async state={state}>
        {(data) =>
          data.run_id === null || data.run_id === undefined ? (
            <Empty title="O laboratório ainda não rodou" hint="Clique em Rodar o laboratório (leva alguns segundos)." />
          ) : (
            <LabView data={data} />
          )
        }
      </Async>
    </>
  );
}

// --- candidates -------------------------------------------------------------------------------

interface CandidatesFormState {
  horizonYears: string;
  monthly: string;
  wealthGoal: string;
  includeScreener: boolean;
  minVolume: string;
  includeIneligible: boolean;
  fixedWeight: boolean;
  weightPct: string;
  ruptureStress: boolean;
  label: string;
}

const INITIAL_CANDIDATES: CandidatesFormState = {
  horizonYears: "5",
  monthly: "1000",
  wealthGoal: "",
  includeScreener: true,
  minVolume: "1000000",
  includeIneligible: false,
  fixedWeight: false,
  weightPct: "5",
  ruptureStress: false,
  label: "",
};

/** The API request from the form; null when the horizon is invalid. */
export function toCandidatesRequest(form: CandidatesFormState): CandidatesRequest | null {
  const years = Number.parseInt(form.horizonYears, 10);
  if (!Number.isFinite(years) || years < 1 || years > 30) return null;
  const goal = parseDecimal(form.wealthGoal);
  const weight = percentInput(form.weightPct);
  return {
    horizon_years: years,
    monthly_contribution: Math.max(parseDecimal(form.monthly) ?? 0, 0),
    wealth_goal: goal !== null && goal > 0 ? goal : null,
    include_screener: form.includeScreener,
    screener_min_volume: Math.max(parseDecimal(form.minVolume) ?? 0, 0),
    include_ineligible: form.includeIneligible,
    weight_mode: form.fixedWeight ? "FIXED" : "NEXT_CONTRIBUTION",
    fixed_weight: weight !== null && weight > 0 ? weight : 0.05,
    rupture_stress: form.ruptureStress,
    label: form.label.trim() || null,
  };
}

function CandidatesForm({
  onSubmitted,
  open = true,
}: Readonly<{ onSubmitted: (run: SimulationRunDTO) => void; open?: boolean }>) {
  const [form, setForm] = useState<CandidatesFormState>(INITIAL_CANDIDATES);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (change: Partial<CandidatesFormState>) => setForm((f) => ({ ...f, ...change }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = toCandidatesRequest(form);
    if (!body) {
      setError("Informe um horizonte de 1 a 30 anos.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onSubmitted(await api.simulations.submitCandidates(body));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormCard title="Avaliar candidatos" hint="Horizonte, aporte e de onde vêm os candidatos" open={open}>
      <form onSubmit={submit} aria-busy={saving} aria-label="Nova avaliação de candidatos">
        <p className="app-card-hint">
          Entram a watchlist e, se marcado, os mais negociados do screener, com os filtros do aporte real (até 20). Cada um é
          posto na carteira de hoje.
        </p>
        {error && (
          <p className="app-error-banner" role="alert">
            {error}
          </p>
        )}
        <fieldset className="app-field-grid" disabled={saving}>
          <div className="app-field">
            <label htmlFor="cand-years">Horizonte (anos)</label>
            <input id="cand-years" inputMode="numeric" value={form.horizonYears} onChange={(e) => set({ horizonYears: e.target.value })} />
          </div>
          <div className="app-field">
            <label htmlFor="cand-monthly">Aporte mensal (R$)</label>
            <input id="cand-monthly" inputMode="decimal" value={form.monthly} onChange={(e) => set({ monthly: e.target.value })} />
          </div>
          <div className="app-field">
            <label htmlFor="cand-goal">Meta de patrimônio (R$, opcional)</label>
            <input id="cand-goal" inputMode="decimal" value={form.wealthGoal} onChange={(e) => set({ wealthGoal: e.target.value })} />
          </div>
          <div className="app-field">
            <label htmlFor="cand-volume">Volume mínimo no screener (R$/dia)</label>
            <input id="cand-volume" inputMode="decimal" value={form.minVolume} onChange={(e) => set({ minVolume: e.target.value })} />
          </div>
          {form.fixedWeight && (
            <div className="app-field">
              <label htmlFor="cand-weight">Peso do candidato na carteira (%)</label>
              <input id="cand-weight" inputMode="decimal" value={form.weightPct} onChange={(e) => set({ weightPct: e.target.value })} />
            </div>
          )}
          <div className="app-field">
            <label htmlFor="cand-label">Nome (opcional)</label>
            <input id="cand-label" value={form.label} maxLength={120} onChange={(e) => set({ label: e.target.value })} />
          </div>
        </fieldset>
        <div className="app-check-row">
          <label className="app-check">
            <input type="checkbox" checked={form.includeScreener} onChange={(e) => set({ includeScreener: e.target.checked })} />
            Incluir os mais negociados do screener
          </label>
          <label className="app-check">
            <input type="checkbox" checked={form.includeIneligible} onChange={(e) => set({ includeIneligible: e.target.checked })} />
            Incluir os fora da elegibilidade (marcados)
          </label>
          <label className="app-check">
            <input type="checkbox" checked={form.fixedWeight} onChange={(e) => set({ fixedWeight: e.target.checked })} />
            Usar um peso fixo (em vez da parte que o próximo aporte daria)
          </label>
          <label className="app-check">
            <input type="checkbox" checked={form.ruptureStress} onChange={(e) => set({ ruptureStress: e.target.checked })} />
            Ruptura em estresse (perda de 90% em vez de 55%)
          </label>
        </div>
        <div className="app-form-actions">
          <button type="submit" className="app-primary-button" disabled={saving}>
            {saving && <Spinner size="sm" />}
            <span>Avaliar candidatos</span>
          </button>
        </div>
      </form>
    </FormCard>
  );
}

function signedBrl(value: number): string {
  return `${value > 0 ? "+" : ""}${brl(value)}`;
}

export function CandidatesView({ data, run }: Readonly<{ data: CandidatesDTO; run: SimulationRunDTO }>) {
  if (data.status !== "DONE") return <Empty title="Os candidatos aparecem quando a avaliação terminar" />;
  const candidates = data.candidates ?? [];
  const excluded = data.excluded ?? [];
  const base = data.base;
  const top = candidates[0];
  const byReason = excluded.reduce<Record<string, string[]>>((groups, e) => {
    (groups[e.reason] ??= []).push(e.ticker);
    return groups;
  }, {});
  return (
    <div className="app-page-stack">
      <Lead tone={top && top.effect.p_improve >= 0.7 ? "positive" : "neutral"}>
        <p>
          {top
            ? `Entre ${plural(data.evaluated ?? candidates.length, "candidato avaliado", "candidatos avaliados")}, ${top.ticker} é o mais promissor: ${pct(top.effect.p_improve, 0)} de chance de melhorar o patrimônio final (${pct(top.effect.p_improve_low, 0)} a ${pct(top.effect.p_improve_high, 0)}), ${signedBrl(top.effect.delta_final_wealth)} na mediana.`
            : "Nenhum candidato tinha histórico suficiente para a avaliação."}
        </p>
        {excluded.length > 0 && (
          <p>
            {`${plural(excluded.length, "ativo ficou", "ativos ficaram")} de fora; o motivo de cada um está no fim da página.`}
          </p>
        )}
      </Lead>
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Candidatos para investigar</h2>
        <p className="app-card-hint">
          {data.evaluated} de {data.tested} avaliados em {yearsLabel(data.horizon_months ?? 0)}, {data.paths} trajetórias.
          {base
            ? ` Carteira de hoje: patrimônio mediano de ${brl(base.final_net_wealth_p50)}, CVaR de 12 meses de ${pct(base.cvar_12m, 1)}${
                base.goal_probability != null ? `, chance de meta de ${pct(base.goal_probability, 0)}` : ""
              }.`
            : ""}
        </p>
        {candidates.length === 0 ? (
          <Empty title="Nenhum candidato com histórico suficiente" hint="Veja os excluídos abaixo." />
        ) : (
          <div className="app-table-wrap">
            <table className="app-table" aria-label="Candidatos">
              <thead>
                <tr>
                  <th className="app-numeric">#</th>
                  <th>Ativo</th>
                  <th className="app-numeric">Chance de a melhora ser real</th>
                  <th className="app-numeric">Patrimônio final</th>
                  <th className="app-numeric">Chance de meta</th>
                  <th className="app-numeric">CVaR 12 meses</th>
                  <th className="app-numeric">Diversificação</th>
                  <th className="app-numeric">Renda (DY)</th>
                  <th className="app-numeric">Entre os 5 primeiros</th>
                  <th className="app-numeric">α a.a. (histórico → encolhido)</th>
                  <th className="app-numeric">β</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.ticker}>
                    <td className="app-numeric">{c.effect.rank}</td>
                    <td>
                      <Link className="app-link" to={compareLink(c.ticker)}>
                        {c.ticker}
                      </Link>
                      <div className="app-muted">
                        {ARCA_LABELS[c.arca_class as keyof typeof ARCA_LABELS] ?? c.arca_class} ·{" "}
                        {c.source === "WATCHLIST" ? "watchlist" : "screener"} · {pct(c.effect.weight, 1)} da carteira
                        {c.eligible === false ? " · fora da elegibilidade" : ""}
                        {c.suspicious ? " · dado suspeito" : ""}
                      </div>
                    </td>
                    <td className="app-numeric">
                      <strong>{pct(c.effect.p_improve, 0)}</strong>
                      <div className="app-muted">
                        {pct(c.effect.p_improve_low, 0)} a {pct(c.effect.p_improve_high, 0)}
                      </div>
                    </td>
                    <td className="app-numeric">
                      <Signed value={c.effect.delta_final_wealth}>{signedBrl(c.effect.delta_final_wealth)}</Signed>
                    </td>
                    <td className="app-numeric">
                      {c.effect.delta_goal_probability == null ? "—" : points(c.effect.delta_goal_probability * 100, 1, true) + " p.p."}
                    </td>
                    <td className="app-numeric">
                      <Signed value={c.effect.delta_cvar_12m}>{points(c.effect.delta_cvar_12m * 100, 2, true)} p.p.</Signed>
                    </td>
                    <td className="app-numeric">{num(c.effect.delta_diversification, 3)}</td>
                    <td className="app-numeric">{points(c.effect.delta_income_yield * 100, 2, true)} p.p.</td>
                    <td className="app-numeric">{pct(c.effect.top_k_share, 0)}</td>
                    <td className="app-numeric">
                      {pct(c.fit.alpha_annual, 1, true)} → {pct(c.fit.alpha_post_annual, 1, true)}
                      <div className="app-muted">{c.fit.months} meses</div>
                    </td>
                    <td className="app-numeric">
                      {num(c.fit.beta, 2)} → {num(c.fit.beta_post, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="app-card-hint">
          Melhora = patrimônio final maior nas mesmas trajetórias com o candidato. Variações positivas de CVaR significam
          perdas menores na cauda. "Entre os 5 primeiros" mede se a posição no ranking resiste a outro sorteio das trajetórias.
        </p>
      </section>
      {excluded.length > 0 && (
        <Section
          title="Fora da avaliação"
          subtitle="Os filtros são os mesmos do aporte real; marque “Incluir os fora da elegibilidade” para avaliá-los mesmo assim."
        >
          <dl className="app-tag-groups" aria-label="Candidatos excluídos">
            {Object.entries(byReason).map(([reason, tickers]) => (
              <div key={reason}>
                <dt>
                  {reason} ({tickers.length})
                </dt>
                <dd>
                  {tickers.map((t) => (
                    <span key={t} className="app-tag">
                      {t}
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </Section>
      )}
      <Notes items={(data.warnings ?? [])} label="Avisos dos candidatos" tone="neutral" />
      <Reproducibility run={run} />
    </div>
  );
}

function CandidatesTab({ run }: Readonly<{ run: SimulationRunDetailDTO }>) {
  const state = useApi(`simulation-candidates-${run.id}-${run.status}`, () => api.simulations.candidates(run.id));
  if (run.status !== "DONE") return <RunProblem run={run} />;
  return <Async state={state}>{(data) => <CandidatesView data={data} run={run} />}</Async>;
}

function candidatesDescription(run: SimulationRunDTO): string {
  const count = Array.isArray(run.params?.candidates) ? (run.params?.candidates as unknown[]).length : 0;
  return plural(count, "candidato", "candidatos");
}

function CandidatesPanel() {
  const runs = useApi("simulation-candidate-runs", () => api.simulations.list(20, "CANDIDATES"));
  const [selected, select] = useSelected("candidates", runs.data);
  return (
    <>
      <CandidatesForm
        open={(runs.data ?? []).length === 0}
        onSubmitted={(run) => {
          select(run.id);
          runs.reload();
        }}
      />
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Avaliações</h2>
        <p className="app-card-hint">Escolha uma linha para ver o resultado abaixo.</p>
        <Async state={runs}>
          {(items) => (
            <RunList runs={items} selected={selected} onSelect={select} onDeleted={(id) => {
              if (id === selected) select(null);
              runs.reload();
            }} describe={candidatesDescription} describeLabel="Candidatos" />
          )}
        </Async>
      </section>
      {selected !== null && (
        <SelectedRun key={selected} runId={selected} onStatus={runs.reload}>
          {(detail) => <CandidatesTab run={detail} />}
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
        <TabGuide tab={tab} />
        {tab === "future" && <FuturePanel />}
        {tab === "confidence" && <ConfidencePanel />}
        {tab === "candidates" && <CandidatesPanel />}
        {tab === "lab" && <LabPanel />}
        {(tab === "past" || tab === "robustness") && <BacktestPanel tab={tab} />}
      </div>
    </div>
  );
}
