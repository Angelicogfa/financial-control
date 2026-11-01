/** The worker jobs the user can run by hand, with their labels and the screen of each. */

export interface ManualJob {
  name: string;
  action: string;
  hint: string;
}

export const JOB_LABELS: Record<string, string> = {
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
  refresh_asset_lenses: "Lentes e portões da recomendação",
  backtest_recommendation: "Teste no passado da recomendação",
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  REQUESTED: "Pedida",
  RUNNING: "Rodando",
  SUCCESS: "Concluída",
  FAILED: "Falhou",
  SKIPPED: "Pulada",
};

/** Jobs that can be run by hand (the API accepts only these). Each screen shows its own: the
 *  market data page only the ones that fetch data, the others where their result is read. */
export const MANUAL_JOBS: ManualJob[] = [
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
      "Recalcula, mês a mês e só com o que se sabia em cada mês, os sinais de valor, qualidade, melhora dos resultados, momentum, renda e risco de todas as ações líquidas. " +
      "Roda sozinho uma vez por semana, depois dos balanços e do histórico.",
  },
  {
    name: "refresh_asset_lenses",
    action: "Rodar as lentes e os portões da recomendação",
    hint:
      "Calcula as lentes de cada ativo (Cerrado, qualidade, valuation, melhora, momentum, renda, risco e projeção), os portões, a matriz de decisão pelo AHP e os pesos-alvo de cada classe. " +
      "Roda sozinha uma vez por semana, uma hora depois do garimpo; rode o garimpo antes.",
  },
  {
    name: "backtest_recommendation",
    action: "Rodar o teste no passado da recomendação",
    hint:
      "Refaz a recomendação a cada trimestre do passado, só com o que se sabia, e a compara com pesos iguais; mede também as rodadas guardadas. " +
      "Roda sozinho uma vez por semana, depois das lentes; rode as lentes antes.",
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
export const JOB_POLL_MS = 5000;

export const JOB_TONES: Record<string, string> = {
  SUCCESS: "success",
  FAILED: "danger",
  REQUESTED: "info",
  RUNNING: "info",
  SKIPPED: "neutral",
};

/** The ones that fetch data from outside (the market data page keeps only these). */
export const MARKET_DATA_JOBS = [
  "sync_simulation_history",
  "sync_cvm_documents",
  "sync_cvm_statements",
  "sync_cvm_event_history",
  "sync_mining_universe",
];

export function manualJobs(names: readonly string[]): ManualJob[] {
  return names.map((name) => MANUAL_JOBS.find((job) => job.name === name)).filter((job): job is ManualJob => !!job);
}
