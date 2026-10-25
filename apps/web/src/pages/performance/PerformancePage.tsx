import { useState } from "react";

import { api } from "../../api/endpoints";
import type { PortfolioAnalyticsResponseDTO, PortfolioReportResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Signed } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty } from "../../components/States";
import { brl, daysAgo, num, pct, points } from "../../utils/format";
import { TrendChart } from "../../viz/TrendChart";
import { alignCurves, curveReturn } from "../home/story";

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

function Content({
  analytics,
  report,
}: Readonly<{ analytics: PortfolioAnalyticsResponseDTO; report: PortfolioReportResponseDTO | null }>) {
  const aligned = alignCurves(analytics.curves, SERIES);
  const portfolio = analytics.curves.PORTFOLIO ?? [];
  const drawdown = analytics.summary.drawdown_curve;
  const drawdownLabels =
    portfolio.length === drawdown.length + 1
      ? portfolio.slice(1).map((p) => dayLabel(String(p.date)))
      : drawdown.map((_, i) => String(i + 1));
  const insufficient = analytics.status !== "OK";

  return (
    <div className="app-page-stack">
      {insufficient && (
        <div className="app-info-banner">
          Histórico insuficiente para medir a carteira ({analytics.available_points ?? 0} retrato(s) diário(s) no
          período). As referências aparecem abaixo; a carteira entra quando houver ao menos três retratos.
        </div>
      )}
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Base 100</h2>
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
      </section>

      {!insufficient && (
        <div className="app-split">
          <section>
            <h2 className="app-card-heading">Risco e retorno</h2>
            <RiskTable analytics={analytics} />
          </section>
          <section>
            <h2 className="app-card-heading">Contra as referências</h2>
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
          </section>
        </div>
      )}

      {!insufficient && drawdown.length >= 2 && (
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Quedas a partir do topo</h2>
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
        </section>
      )}

      {report && (
        <section>
          <h2 className="app-card-heading">Por classe</h2>
          <p className="app-card-hint">
            Resultado consolidado de cada classe desde o primeiro lançamento, ao lado do retorno da referência da classe
            no período escolhido.
          </p>
          <ClassTable report={report} analytics={analytics} />
        </section>
      )}
    </div>
  );
}

export function PerformancePage() {
  const [period, setPeriod] = useState<PeriodKey>("12m");
  const days = PERIODS.find((p) => p.key === period)?.days ?? 365;
  const since = daysAgo(days);
  const analytics = useApi(`performance-${since}`, () => api.portfolio.analytics(since));
  const report = useApi("performance-report", () => api.portfolio.report());

  return (
    <div className="app-page">
      <PageHeader
        title="Desempenho"
        subtitle="Rentabilidade da carteira no tempo, risco e comparação com as referências."
        actions={
          <div className="app-segmented" role="group" aria-label="Período">
            {PERIODS.map((p) => (
              <button key={p.key} type="button" aria-pressed={period === p.key} onClick={() => setPeriod(p.key)}>
                {p.label}
              </button>
            ))}
          </div>
        }
      />
      <Async state={analytics} lines={6}>
        {(data) => <Content analytics={data} report={report.data} />}
      </Async>
    </div>
  );
}
