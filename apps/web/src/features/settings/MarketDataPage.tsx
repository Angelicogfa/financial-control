import { useState } from "react";

import { api } from "../../api/endpoints";
import { JOB_LABELS, JOB_STATUS_LABELS, JOB_TONES, MARKET_DATA_JOBS, manualJobs } from "../../api/jobs";
import { useScreenData } from "../../api/query";
import { Badge } from "../../components/Badge";
import { JobRunList } from "../../components/JobRunList";
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty, Spinner } from "../../components/States";
import { dateTime, day, num } from "../../utils/format";

const UNIT_LABELS: Record<string, string> = {
  PERCENT_PER_DAY: "% ao dia",
  PERCENT_PER_MONTH: "% ao mês",
  PRICE: "Preço",
  INDEX_POINTS: "Pontos",
  RATIO: "Razão",
};


const OPERATION_LABELS: Record<string, string> = {
  quote: "Cotação",
  history: "Histórico",
  fundamentals: "Fundamentos",
  statements: "Demonstrativos",
  series: "Série macro",
  catalog: "Catálogo B3",
};


function notifyWorkerErrorsChanged() {
  window.dispatchEvent(new CustomEvent("fincontrol:worker-errors-changed"));
}

export function MarketDataPage() {
  const [includeResolved, setIncludeResolved] = useState(false);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [resolvingAll, setResolvingAll] = useState(false);
  const series = useScreenData("series-status", () => api.market.series());
  const jobs = useScreenData("job-runs", () => api.market.jobs());
  const workerErrors = useScreenData(`worker-errors:${includeResolved}`, () =>
    api.market.workerErrors(includeResolved),
  );

  const reloading = series.loading || jobs.loading || workerErrors.loading;

  const handleResolveOne = async (errorId: number) => {
    setResolvingId(errorId);
    try {
      await api.market.resolveWorkerError(errorId);
      workerErrors.reload();
      notifyWorkerErrorsChanged();
    } finally {
      setResolvingId(null);
    }
  };

  const handleResolveAll = async () => {
    setResolvingAll(true);
    try {
      await api.market.resolveAllWorkerErrors();
      workerErrors.reload();
      notifyWorkerErrorsChanged();
    } finally {
      setResolvingAll(false);
    }
  };

  return (
    <div className="app-page">
      <PageHeader
        title="Dados de mercado"
        subtitle="Frescor das séries usadas nos cálculos e a última execução de cada rotina do worker."
        actions={
          <button
            type="button"
            className="app-secondary-button"
            disabled={reloading}
            onClick={() => {
              series.reload();
              jobs.reload();
              workerErrors.reload();
              notifyWorkerErrorsChanged();
            }}
          >
            {reloading && <Spinner size="sm" />}
            <span>{reloading ? "Atualizando…" : "Atualizar"}</span>
          </button>
        }
      />
      <div className="app-page-stack">
        <section>
          <div className="app-button-row" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
            <div className="app-button-row" style={{ gap: "var(--space-2)" }}>
              <h2 className="app-card-heading" style={{ margin: 0 }}>
                Notificações de erros do worker
              </h2>
              {workerErrors.data && workerErrors.data.unresolved_count > 0 && (
                <Badge tone="danger">{`${workerErrors.data.unresolved_count} pendente(s)`}</Badge>
              )}
            </div>
            <div className="app-button-row">
              <label className="app-check">
                <input
                  type="checkbox"
                  checked={includeResolved}
                  onChange={(event) => setIncludeResolved(event.target.checked)}
                />
                <span>Mostrar resolvidos</span>
              </label>
              {workerErrors.data && workerErrors.data.unresolved_count > 0 && (
                <button type="button" className="app-secondary-button" disabled={resolvingAll} onClick={handleResolveAll}>
                  {resolvingAll && <Spinner size="sm" />}
                  <span>{resolvingAll ? "Limpando…" : "Limpar notificações"}</span>
                </button>
              )}
            </div>
          </div>
          <Async state={workerErrors}>
            {(report) =>
              report.errors.length === 0 ? (
                <Empty
                  title="Nenhum erro de requisição pendente"
                  hint="Falhas de comunicação do worker com provedores externos (Brapi, Yahoo Finance, BCB) aparecem aqui com o log detalhado."
                />
              ) : (
                <div className="app-table-wrap">
                  <table className="app-table">
                    <thead>
                      <tr>
                        <th>Quando</th>
                        <th>Rotina</th>
                        <th>Provedor</th>
                        <th>Operação / Alvo</th>
                        <th>Requisição feita</th>
                        <th>Status</th>
                        <th>Resultado do erro</th>
                        <th className="app-numeric">Ação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.errors.map((err) => (
                        <tr key={err.id}>
                          <td>{dateTime(err.occurred_at)}</td>
                          <td>{JOB_LABELS[err.job_name] ?? err.job_name}</td>
                          <td>
                            <Badge tone="neutral">{err.provider}</Badge>
                          </td>
                          <td>
                            <div className="app-cell-main">
                              <span>{err.target}</span>
                              <small>{OPERATION_LABELS[err.operation] ?? err.operation}</small>
                            </div>
                          </td>
                          <td className="app-cell-wrap">
                            <div className="app-cell-url">
                              <code title={err.request_url}>{err.request_url}</code>
                            </div>
                          </td>
                          <td className="app-cell-status">
                            <Badge tone={err.resolved_at ? "neutral" : "danger"}>
                              {err.status_code ? `HTTP ${err.status_code}` : err.error_type}
                            </Badge>
                          </td>
                          <td className="app-cell-wrap app-muted">
                            <div className="app-cell-error" title={err.error_detail}>
                              {err.error_detail}
                            </div>
                          </td>
                          <td className="app-numeric">
                            {err.resolved_at ? (
                              <span className="app-muted">Resolvido</span>
                            ) : (
                              <button
                                type="button"
                                className="app-link-button"
                                disabled={resolvingId === err.id}
                                onClick={() => void handleResolveOne(err.id)}
                              >
                                {resolvingId === err.id && <Spinner size="sm" />}
                                <span>{resolvingId === err.id ? "Dispensando…" : "Dispensar"}</span>
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            }
          </Async>
        </section>
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
        <section className="app-card app-card-padded" aria-label="Buscar dados agora">
          <h2 className="app-card-heading">Buscar dados agora</h2>
          <p className="app-card-hint">
            Aqui ficam só as rotinas que buscam dados fora (Yahoo, CVM). As que processam esses dados rodam na tela de
            cada assunto: o garimpo no Garimpo, as lentes e o teste no passado em Recomendação, a previsão de preço em
            Qualidade dos modelos.
          </p>
          <JobRunList jobs={manualJobs(MARKET_DATA_JOBS)} onChange={jobs.reload} />
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
                            <Badge tone={JOB_TONES[job.status] ?? "neutral"}>{JOB_STATUS_LABELS[job.status] ?? job.status}</Badge>
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
