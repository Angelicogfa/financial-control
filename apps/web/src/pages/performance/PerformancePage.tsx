import { useState } from "react";

import { api } from "../../api/endpoints";
import type { PortfolioAnalyticsResponseDTO, PortfolioReportResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Signed } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section, Segmented, type Tone } from "../../components/Section";
import { Async, Empty } from "../../components/States";
import { brl, brlCompact, daysAgo, monthLabel, num, pct, plural, points } from "../../utils/format";
import { ColumnChart } from "../../viz/ColumnChart";
import { TrendChart } from "../../viz/TrendChart";
import { alignCurves, curveReturn, lastMonths } from "../home/story";

const PERIODS = [
  { key: "6m", label: "6 meses", days: 182 },
  { key: "12m", label: "12 meses", days: 365 },
  { key: "24m", label: "24 meses", days: 730 },
  { key: "all", label: "Tudo", days: 365 * 30 },
] as const;
type PeriodKey = (typeof PERIODS)[number]["key"];

const SERIES = ["PORTFOLIO", "CDI", "IBOV", "IFIX", "SP500"];
const LABELS: Record<string, string> = {
  PORTFOLIO: "Carteira",
  CDI: "CDI",
  IBOV: "Ibovespa",
  IFIX: "IFIX",
  SP500: "S&P 500",
};
const COLORS: Record<string, string> = {
  PORTFOLIO: "var(--viz-serie-1)",
  CDI: "var(--viz-serie-2)",
  IBOV: "var(--viz-serie-3)",
  IFIX: "var(--viz-serie-4)",
  SP500: "var(--app-text-subtle)",
};
/** The reference each ARCA class is compared with. */
const CLASS_BENCHMARK: Record<string, string> = {
  ACOES: "IBOV",
  REAL_ESTATE: "IFIX",
  CAIXA: "CDI",
  ATIVOS_INTERNACIONAIS: "SP500",
};

/** The period in words: return, the gap to the CDI and the worst fall. */
export function performanceStory(analytics: PortfolioAnalyticsResponseDTO, period: string): { tone: Tone; text: string } {
  const s = analytics.summary;
  const cdi = s.benchmarks.find((b) => b.benchmark === "CDI");
  const best = [...s.benchmarks].sort((a, b) => (b.benchmark_return ?? 0) - (a.benchmark_return ?? 0))[0];
  const excess = cdi?.excess_return ?? null;
  let text = `Em ${period}, a carteira rendeu ${pct(s.cumulative_return, 1, true)}`;
  if (excess !== null) text += `, ${pct(Math.abs(excess), 1)} ${excess >= 0 ? "acima" : "abaixo"} do CDI`;
  text += `, com queda máxima de ${pct(s.max_drawdown, 1)}.`;
  if (best && best.benchmark !== "CDI") {
    text += ` A referência mais forte foi ${LABELS[best.benchmark] ?? best.benchmark} (${pct(best.benchmark_return, 1, true)}).`;
  }
  const tone: Tone = excess === null ? "neutral" : excess >= 0 ? "positive" : "negative";
  return { tone, text };
}

const PERFORMANCE_NOTES = [
  "O retorno é ponderado pelo tempo (TWR): aportes e resgates não inflam nem reduzem o resultado.",
  "Volatilidade, VaR e CVaR vêm dos retornos diários do período; períodos curtos dão números instáveis.",
  "O resultado por classe é consolidado desde o primeiro lançamento; a referência ao lado é só do período escolhido.",
];

function dayLabel(iso: string): string {
  return iso.split("-").reverse().join("/");
}

function RiskTable({ analytics }: Readonly<{ analytics: PortfolioAnalyticsResponseDTO }>) {
  const s = analytics.summary;
  const rows: Array<[string, string, string]> = [
    ["Retorno acumulado", pct(s.cumulative_return, 2, true), "Ponderado pelo tempo (TWR), sem efeito dos aportes."],
    ["Retorno anualizado (CAGR)", pct(s.cagr, 2, true), ""],
    ["Retorno real (acima do IPCA)", pct(s.real_return_vs_ipca, 2, true), ""],
    ["Volatilidade anual", pct(s.annualized_volatility, 2), "Oscilação dos retornos diários, anualizada."],
    ["Índice de Sharpe", num(s.sharpe_ratio, 2), "Retorno acima do CDI por unidade de risco."],
    ["Índice de Sortino", num(s.sortino_ratio, 2), "Como o Sharpe, contando só as quedas."],
    ["Queda máxima", pct(s.max_drawdown, 2), "Maior queda do topo ao fundo no período."],
    ["VaR 95% (histórico)", pct(s.var_95_historical, 2), "Perda diária superada em 5% dos dias."],
    ["CVaR 95%", pct(s.cvar_95, 2), "Perda média nos 5% piores dias."],
  ];
  return (
    <div className="app-table-wrap">
      <table className="app-table">
        <thead>
          <tr>
            <th>Indicador</th>
            <th className="app-numeric">Valor</th>
            <th>O que mede</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, value, help]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="app-numeric">{value}</td>
              <td className="app-cell-wrap app-muted">{help}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClassTable({
  report,
  analytics,
}: Readonly<{ report: PortfolioReportResponseDTO; analytics: PortfolioAnalyticsResponseDTO }>) {
  return (
    <div className="app-table-wrap">
      <table className="app-table">
        <thead>
          <tr>
            <th>Classe</th>
            <th className="app-numeric">Investido</th>
            <th className="app-numeric">Resultado consolidado</th>
            <th>Referência</th>
            <th className="app-numeric">Referência no período</th>
          </tr>
        </thead>
        <tbody>
          {report.allocations.map((a) => {
            const benchmark = CLASS_BENCHMARK[a.arca_class];
            const result = a.invested_value > 0 ? a.consolidated_pnl / a.invested_value : null;
            return (
              <tr key={a.arca_class}>
                <td>{a.label}</td>
                <td className="app-numeric">{brl(a.invested_value)}</td>
                <td className="app-numeric">
                  <Signed value={result}>{result === null ? "—" : pct(result, 1, true)}</Signed>
                </td>
                <td>{LABELS[benchmark]}</td>
                <td className="app-numeric">{pct(curveReturn(analytics.curves[benchmark]), 1, true)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EarningsByMonth({ report }: Readonly<{ report: PortfolioReportResponseDTO }>) {
  const months = lastMonths(report.earnings_by_month);
  const total12 = months.reduce((sum, [, v]) => sum + v, 0);
  return (
    <Section
      title="Proventos por mês"
      subtitle={`Últimos 12 meses: ${brl(total12)} líquidos · yield on cost ${points(report.portfolio_yield_on_cost_pct, 1)}.`}
    >
      {total12 > 0 ? (
        <ColumnChart
          title={`Proventos recebidos por mês, total de ${brl(total12)} em 12 meses`}
          columns={months.map(([key, value]) => ({ label: monthLabel(key), value }))}
          hint="Passe o mouse para ver o mês."
          format={brlCompact}
        />
      ) : (
        <p className="app-muted">Nenhum provento nos últimos 12 meses.</p>
      )}
    </Section>
  );
}

function Content({
  analytics,
  report,
  period,
}: Readonly<{ analytics: PortfolioAnalyticsResponseDTO; report: PortfolioReportResponseDTO | null; period: string }>) {
  const aligned = alignCurves(analytics.curves, SERIES);
  const portfolio = analytics.curves.PORTFOLIO ?? [];
  const drawdown = analytics.summary.drawdown_curve;
  const drawdownLabels =
    portfolio.length === drawdown.length + 1
      ? portfolio.slice(1).map((p) => dayLabel(String(p.date)))
      : drawdown.map((_, i) => String(i + 1));
  const insufficient = analytics.status !== "OK";
  const story = performanceStory(analytics, period);
  const s = analytics.summary;

  return (
    <div className="app-page-stack">
      {insufficient ? (
        <Lead tone="caution">
          <p>
            Histórico insuficiente para medir a carteira (
            {plural(analytics.available_points ?? 0, "retrato diário", "retratos diários")} no período). As referências
            aparecem abaixo; a carteira entra quando houver ao menos três retratos.
          </p>
        </Lead>
      ) : (
        <>
          <Lead tone={story.tone}>
            <p>{story.text}</p>
          </Lead>
          <KpiGrid
            label="Indicadores do período"
            items={[
              {
                label: "Retorno (TWR)",
                value: pct(s.cumulative_return, 1, true),
                tone: (s.cumulative_return ?? 0) >= 0 ? "positive" : "negative",
              },
              { label: "Acima do IPCA", value: pct(s.real_return_vs_ipca, 1, true), note: "Retorno real" },
              { label: "Volatilidade anual", value: pct(s.annualized_volatility, 1) },
              { label: "Queda máxima", value: pct(s.max_drawdown, 1), tone: "negative" },
              { label: "Sharpe", value: num(s.sharpe_ratio, 2), note: "Retorno acima do CDI por risco" },
            ]}
          />
        </>
      )}
      <Section title="Carteira e referências" subtitle="Base 100 no início do período.">
        {aligned.labels.length >= 2 ? (
          <TrendChart
            title="Carteira e referências em base 100 no período"
            labels={aligned.labels.map(dayLabel)}
            baseline={100}
            hint="Passe o mouse para ler cada dia."
            series={Object.entries(aligned.series).map(([key, values]) => ({
              key,
              label: LABELS[key] ?? key,
              color: COLORS[key] ?? "var(--viz-serie-4)",
              values,
            }))}
          />
        ) : (
          <Empty title="Sem séries no período" hint="Sincronize os dados de mercado em Configuração." />
        )}
      </Section>

      {!insufficient && (
        <div className="app-split">
          <Section title="Risco e retorno">
            <RiskTable analytics={analytics} />
          </Section>
          <Section title="Contra as referências" subtitle="Excesso é o retorno da carteira menos o da referência.">
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Referência</th>
                    <th className="app-numeric">Retorno</th>
                    <th className="app-numeric">Excesso</th>
                    <th className="app-numeric">Beta</th>
                    <th className="app-numeric">Correlação</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.summary.benchmarks.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="app-table-empty">
                        Sem referências no período.
                      </td>
                    </tr>
                  ) : (
                    analytics.summary.benchmarks.map((b) => (
                      <tr key={b.benchmark}>
                        <td>{LABELS[b.benchmark] ?? b.benchmark}</td>
                        <td className="app-numeric">{pct(b.benchmark_return, 1, true)}</td>
                        <td className="app-numeric">
                          <Signed value={b.excess_return}>{pct(b.excess_return, 1, true)}</Signed>
                        </td>
                        <td className="app-numeric">{num(b.beta, 2)}</td>
                        <td className="app-numeric">{num(b.correlation, 2)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Section>
        </div>
      )}

      {!insufficient && drawdown.length >= 2 && (
        <Section title="Quedas a partir do topo" subtitle="Distância de cada dia até o maior valor já atingido.">
          <TrendChart
            title={`Drawdown da carteira; pior queda de ${pct(analytics.summary.max_drawdown, 1)}`}
            labels={drawdownLabels}
            baseline={0}
            hint="Distância do maior valor já atingido."
            format={(v) => points(v, 1)}
            series={[
              { key: "dd", label: "Queda", color: "var(--viz-negative)", values: drawdown.map((v) => v * 100) },
            ]}
          />
        </Section>
      )}

      {report && (
        <Section title="Por classe" subtitle="Resultado de cada classe ao lado da referência da classe no período.">
          <ClassTable report={report} analytics={analytics} />
        </Section>
      )}

      {report && <EarningsByMonth report={report} />}
      <Notes items={PERFORMANCE_NOTES} />
    </div>
  );
}

export function PerformancePage() {
  const [period, setPeriod] = useState<PeriodKey>("12m");
  const days = PERIODS.find((p) => p.key === period)?.days ?? 365;
  const since = daysAgo(days);
  const periodText = period === "all" ? "todo o histórico" : (PERIODS.find((p) => p.key === period)?.label ?? "");
  const analytics = useApi(`performance-${since}`, () => api.portfolio.analytics(since));
  const report = useApi("performance-report", () => api.portfolio.report());

  return (
    <div className="app-page">
      <PageHeader
        title="Desempenho"
        subtitle="Rentabilidade da carteira no tempo, risco e comparação com as referências."
        actions={
          <Segmented
            options={PERIODS.map((p) => [p.key, p.label] as [PeriodKey, string])}
            value={period}
            onChange={setPeriod}
            label="Período"
          />
        }
      />
      <Async state={analytics} lines={6}>
        {(data) => <Content analytics={data} report={report.data} period={periodText} />}
      </Async>
    </div>
  );
}
