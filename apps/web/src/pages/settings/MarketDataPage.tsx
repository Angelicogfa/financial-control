import { api } from "../../api/endpoints";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty } from "../../components/States";
import { dateTime, day, num } from "../../utils/format";

const UNIT_LABELS: Record<string, string> = {
  PERCENT_PER_DAY: "% ao dia",
  PERCENT_PER_MONTH: "% ao mês",
  PRICE: "Preço",
  INDEX_POINTS: "Pontos",
};

const JOB_LABELS: Record<string, string> = {
  sync_bcb_and_benchmarks: "Séries BCB e índices",
  ensure_series_coverage: "Cobertura das séries",
  warm_portfolio_quotes: "Cotações da carteira",
  record_daily_snapshot: "Retrato diário",
  backfill_snapshots: "Histórico de retratos",
  refresh_fundamentals: "Demonstrativos anuais",
  record_checklist_evaluations: "Reavaliação dos checklists",
  sync_instrument_catalog: "Catálogo de ativos B3",
};

const JOB_TONES: Record<string, string> = { SUCCESS: "success", FAILED: "danger", RUNNING: "info", SKIPPED: "neutral" };

export function MarketDataPage() {
  const series = useApi("series-status", () => api.market.series());
  const jobs = useApi("job-runs", () => api.market.jobs());
  return (
    <div className="app-page">
      <PageHeader
        title="Dados de mercado"
        subtitle="Frescor das séries usadas nos cálculos e a última execução de cada rotina do worker."
        actions={
          <button
            type="button"
            className="app-secondary-button"
            onClick={() => {
              series.reload();
              jobs.reload();
            }}
          >
            Atualizar
          </button>
        }
      />
      <div className="app-page-stack">
        <section>
          <h2 className="app-card-heading">Séries</h2>
          <Async state={series}>
            {(list) => (
              <div className="app-table-wrap">
                <table className="app-table">
                  <thead>
                    <tr>
                      <th>Série</th>
                      <th>Unidade</th>
                      <th>Desde</th>
                      <th>Último ponto</th>
                      <th className="app-numeric">Pontos</th>
                      <th className="app-numeric">Dias úteis faltando</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((s) => (
                      <tr key={s.symbol}>
                        <td>{s.symbol}</td>
                        <td>{s.unit ? UNIT_LABELS[s.unit] : "—"}</td>
                        <td>{day(s.first_date)}</td>
                        <td>{day(s.last_date)}</td>
                        <td className="app-numeric">{num(s.points, 0)}</td>
                        <td className="app-numeric">{num(s.missing_business_days, 0)}</td>
                        <td>
                          <Badge tone={s.stale ? "warning" : "success"}>{s.stale ? "Desatualizada" : "Em dia"}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </section>
        <section>
          <h2 className="app-card-heading">Rotinas do worker</h2>
          <Async state={jobs}>
            {(list) =>
              list.length === 0 ? (
                <Empty title="Nenhuma execução registrada" hint="O worker registra cada rotina assim que roda." />
              ) : (
                <div className="app-table-wrap">
                  <table className="app-table">
                    <thead>
                      <tr>
                        <th>Rotina</th>
                        <th>Situação</th>
                        <th>Início</th>
                        <th>Fim</th>
                        <th className="app-numeric">Tentativas</th>
                        <th>Erro</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((job) => (
                        <tr key={job.job_name}>
                          <td>{JOB_LABELS[job.job_name] ?? job.job_name}</td>
                          <td>
                            <Badge tone={JOB_TONES[job.status] ?? "neutral"}>{job.status}</Badge>
                          </td>
                          <td>{dateTime(job.started_at)}</td>
                          <td>{dateTime(job.finished_at)}</td>
                          <td className="app-numeric">{job.attempts}</td>
                          <td className="app-cell-wrap app-muted">{job.error ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            }
          </Async>
        </section>
      </div>
    </div>
  );
}
