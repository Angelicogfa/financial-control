import { useEffect, useState } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
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

const JOB_LABELS: Record<string, string> = {
  sync_bcb_and_benchmarks: "Séries BCB e índices",
  ensure_series_coverage: "Cobertura das séries",
  warm_portfolio_quotes: "Cotações da carteira",
  record_daily_snapshot: "Retrato diário",
  backfill_snapshots: "Histórico de retratos",
  refresh_fundamentals: "Demonstrativos anuais",
  record_checklist_evaluations: "Reavaliação dos checklists",
  sync_instrument_catalog: "Catálogo de ativos B3",
  sync_simulation_history: "Histórico longo da simulação",
  sync_cvm_documents: "Comunicados da CVM",
  sync_cvm_statements: "Balanços da CVM (DFP e ITR)",
  sync_cvm_event_history: "Histórico de comunicados da CVM",
  run_pending_simulations: "Simulações na fila",
  refresh_asset_forecasts: "Previsão de preço dos ativos",
  calibrate_forecasts: "Calibração da previsão de preço",
  estimate_forecast_models: "Valuation na previsão de preço",
  sync_mining_universe: "Histórico do garimpo",
  run_mining: "Garimpo",
};

const JOB_STATUS_LABELS: Record<string, string> = {
  REQUESTED: "Pedida",
  RUNNING: "Rodando",
  SUCCESS: "Concluída",
  FAILED: "Falhou",
  SKIPPED: "Pulada",
};

/** Jobs that can be run by hand (the API accepts only these). */
export const MANUAL_JOBS: Array<{ name: string; action: string; hint: string }> = [
  {
    name: "sync_simulation_history",
    action: "Carregar o histórico da simulação",
    hint:
      "Baixa do Yahoo o histórico longo dos ativos, do Ibovespa, do S&P 500 e do dólar que a simulação de carteira usa. " +
      "Roda sozinha uma vez por semana; use aqui para não esperar. Pode levar alguns minutos.",
  },
  {
    name: "sync_cvm_documents",
    action: "Carregar os comunicados da CVM",
    hint:
      "Baixa da CVM os fatos relevantes, comunicados e avisos das ações da carteira e da watchlist. " +
      "Roda sozinha todo dia; use aqui para ver já os documentos de hoje.",
  },
  {
    name: "sync_cvm_statements",
    action: "Carregar os balanços da CVM",
    hint:
      "Baixa da CVM os balanços anuais e trimestrais (DFP e ITR) das empresas listadas, com a data em que cada um foi entregue. " +
      "Roda sozinha todo dia: confere os dois últimos anos e traz o histórico desde 2010 aos poucos (alguns arquivos por vez).",
  },
  {
    name: "sync_cvm_event_history",
    action: "Carregar o histórico de comunicados",
    hint:
      "Baixa os comunicados da CVM de todas as empresas listadas desde 2010 e classifica cada fato relevante por tipo de evento, para medir o que costuma acontecer com o preço depois. " +
      "Roda sozinha todo dia, alguns anos por vez; os antigos entram como lidos.",
  },
  {
    name: "sync_mining_universe",
    action: "Carregar o histórico do garimpo",
    hint:
      "Baixa o histórico longo de preço (com desdobramentos) das ações líquidas de todo o catálogo, que o garimpo usa para medir os sinais. " +
      "Roda sozinha todo dia útil, alguns papéis por vez, até cobrir o universo; depois mantém cada um com até uma semana.",
  },
  {
    name: "run_mining",
    action: "Rodar o garimpo",
    hint:
      "Recalcula, mês a mês e só com o que se sabia em cada mês, os sinais de valor, qualidade, melhora dos resultados e momentum de todas as ações líquidas. " +
      "Roda sozinho uma vez por semana, depois dos balanços e do histórico.",
  },
  {
    name: "refresh_asset_forecasts",
    action: "Recalcular a previsão de preço",
    hint:
      "Recalcula a faixa provável de preço de cada ativo em 3, 6, 12 e 24 meses a partir do histórico guardado. " +
      "Roda sozinha todo dia útil; para um ativo só, use a aba Probabilidades do ativo.",
  },
  {
    name: "estimate_forecast_models",
    action: "Medir o valuation na previsão",
    hint:
      "Mede, com os balanços entregues à CVM, quanto estar barata ou cara frente ao histórico e ao setor disse sobre os 12 meses seguintes, " +
      "e só usa na previsão se isso melhorou as previsões do passado. Roda sozinha uma vez por semana; depois, recalcule a previsão.",
  },
  {
    name: "calibrate_forecasts",
    action: "Calibrar a previsão de preço",
    hint:
      "Refaz as previsões do passado e mede quantas vezes as faixas se confirmaram; é isso que decide o selo de confiança. " +
      "Roda sozinha uma vez por semana. Pode levar alguns minutos.",
  },
];
const JOB_POLL_MS = 5000;

const OPERATION_LABELS: Record<string, string> = {
  quote: "Cotação",
  history: "Histórico",
  fundamentals: "Fundamentos",
  statements: "Demonstrativos",
  series: "Série macro",
  catalog: "Catálogo B3",
};

const JOB_TONES: Record<string, string> = {
  SUCCESS: "success",
  FAILED: "danger",
  REQUESTED: "info",
  RUNNING: "info",
  SKIPPED: "neutral",
};

function notifyWorkerErrorsChanged() {
  window.dispatchEvent(new CustomEvent("fincontrol:worker-errors-changed"));
}

export function MarketDataPage() {
  const [includeResolved, setIncludeResolved] = useState(false);
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [resolvingAll, setResolvingAll] = useState(false);
  const series = useApi("series-status", () => api.market.series());
  const jobs = useApi("job-runs", () => api.market.jobs());
  const workerErrors = useApi(`worker-errors:${includeResolved}`, () =>
    api.market.workerErrors(includeResolved),
  );

  const reloading = series.loading || jobs.loading || workerErrors.loading;
  const [requesting, setRequesting] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const lastRun = (name: string) => jobs.data?.find((j) => j.job_name === name);
  const statusOf = (name: string) => lastRun(name)?.status;
  const anyActive = MANUAL_JOBS.some((j) => ["REQUESTED", "RUNNING"].includes(statusOf(j.name) ?? ""));

  // Follow a manual run until the worker finishes it.
  useEffect(() => {
    if (!anyActive) return undefined;
    const timer = setTimeout(() => jobs.reload(), JOB_POLL_MS);
    return () => clearTimeout(timer);
  }, [anyActive, jobs]);

  const handleRequest = async (name: string) => {
    setRequesting(name);
    setRequestError(null);
    try {
      await api.market.requestJob(name);
      jobs.reload();
    } catch (err) {
      setRequestError(errorMessage(err));
    } finally {
      setRequesting(null);
    }
  };

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
        <section className="app-card app-card-padded" aria-label="Rodar agora">
          <h2 className="app-card-heading">Rodar agora</h2>
          {requestError && (
            <p className="app-error-banner" role="alert">
              {requestError}
            </p>
          )}
          <ul className="app-run-list">
            {MANUAL_JOBS.map((job) => {
              const run = lastRun(job.name);
              const status = run?.status;
              const active = status === "REQUESTED" || status === "RUNNING";
              return (
                <li key={job.name} className="app-run-item">
                  <div className="app-run-text">
                    <strong>{JOB_LABELS[job.name] ?? job.name}</strong>
                    <p className="app-card-hint">{job.hint}</p>
                    {active ? (
                      <span className="app-run-status" role="status">
                        {status === "REQUESTED" ? "Pedido registrado; o worker começa em até 15 segundos." : "Rodando…"}
                      </span>
                    ) : (
                      run && (
                        <span className="app-run-status">
                          Última vez: {dateTime(run.finished_at ?? run.started_at)}{" "}
                          <Badge tone={JOB_TONES[run.status] ?? "neutral"}>{JOB_STATUS_LABELS[run.status] ?? run.status}</Badge>
                        </span>
                      )
                    )}
                  </div>
                  <button
                    type="button"
                    className="app-secondary-button"
                    disabled={active || requesting !== null}
                    onClick={() => handleRequest(job.name)}
                  >
                    {(active || requesting === job.name) && <Spinner size="sm" />}
                    <span>{job.action}</span>
                  </button>
                </li>
              );
            })}
          </ul>
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
