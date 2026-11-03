/** Routes of the app by user task (Phase 48.R3): pt-BR addresses in the web, English in the
 *  API. The redirects of the old navigation were removed in Phase 48.R9. */

import { Navigate, Route, Routes } from "react-router-dom";

import { InstrumentRoute } from "../features/instrument/InstrumentRoute";
import { IncomePage } from "../features/portfolio/IncomePage";
import { ReconciliationPage } from "../features/portfolio/ReconciliationPage";
import { MonthlyReportPage } from "../features/portfolio/MonthlyReportPage";
import { TaxPage } from "../features/portfolio/TaxPage";
import { GoalsPage } from "../features/planning/GoalsPage";
import { IncomeForecastPage } from "../features/planning/IncomeForecastPage";
import { WatchlistPage } from "../features/watchlist/WatchlistPage";
import { AssetFormPage } from "../features/asset/AssetFormPage";
import { ContributePage } from "../features/contribute/ContributePage";
import { DisclosuresPage } from "../features/disclosures/DisclosuresPage";
import { HealthPage } from "../features/health/HealthPage";
import { HomePage } from "../features/home/HomePage";
import { EarningFormPage } from "../features/ledger/EarningFormPage";
import { EventFormPage } from "../features/ledger/EventFormPage";
import { ImportPage } from "../features/ledger/ImportPage";
import { LedgerPage } from "../features/ledger/LedgerPage";
import { TradeFormPage } from "../features/ledger/TradeFormPage";
import { NotFoundPage } from "./NotFoundPage";
import { PerformancePage } from "../features/performance/PerformancePage";
import { PortfolioPage } from "../features/portfolio/PortfolioPage";
import { RecommendationPage } from "../features/recommendation/RecommendationPage";
import { MiningPage } from "../features/research/MiningPage";
import { ResearchPage } from "../features/research/ResearchPage";
import { AccountsPage } from "../features/settings/AccountsPage";
import { AgenticPage } from "../features/settings/agentic/AgenticPage";
import { AgentKeyFormPage } from "../features/settings/agentic/AgentKeyFormPage";
import { MarketDataPage } from "../features/settings/MarketDataPage";
import { StrategyPage } from "../features/settings/StrategyPage";
import { CompareStudiesPage } from "../features/simulation/CompareStudiesPage";
import { NewStudyPage } from "../features/simulation/NewStudyPage";
import { QualityPage } from "../features/simulation/QualityPage";
import { StudiesPage } from "../features/simulation/StudiesPage";
import { StudyPage } from "../features/simulation/StudyPage";
import { AssetComparePage } from "../features/tools/AssetComparePage";
import { FixedIncomeComparePage } from "../features/tools/FixedIncomeComparePage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/inicio" replace />} />
      <Route path="/inicio" element={<HomePage />} />

      <Route path="/carteira" element={<PortfolioPage />} />
      <Route path="/carteira/rentabilidade" element={<PerformancePage />} />
      <Route path="/carteira/proventos" element={<IncomePage />} />
      <Route path="/carteira/raio-x" element={<HealthPage />} />
      <Route path="/carteira/conferir" element={<ReconciliationPage />} />
      <Route path="/carteira/imposto" element={<TaxPage />} />
      <Route path="/carteira/relatorio" element={<MonthlyReportPage />} />
      <Route path="/carteira/novo-ativo" element={<AssetFormPage />} />

      <Route path="/ativo/:ticker" element={<InstrumentRoute />} />
      <Route path="/ativo/:ticker/editar" element={<InstrumentRoute edit />} />

      <Route path="/explorar" element={<ResearchPage />} />
      <Route path="/explorar/garimpo" element={<MiningPage />} />
      <Route path="/explorar/comparar" element={<AssetComparePage />} />
      <Route path="/explorar/fatos-relevantes" element={<DisclosuresPage />} />

      <Route path="/acompanhar" element={<WatchlistPage />} />

      <Route path="/aportar" element={<ContributePage />} />
      <Route path="/aportar/:planId" element={<ContributePage />} />

      <Route path="/planejar" element={<StudiesPage />} />
      <Route path="/planejar/estudos/novo" element={<NewStudyPage />} />
      <Route path="/planejar/estudos/comparar" element={<CompareStudiesPage />} />
      <Route path="/planejar/estudos/:studyId" element={<StudyPage />} />
      <Route path="/planejar/qualidade" element={<QualityPage />} />
      <Route path="/planejar/renda-fixa" element={<FixedIncomeComparePage />} />
      <Route path="/planejar/modelo" element={<RecommendationPage />} />
      <Route path="/planejar/metas" element={<GoalsPage />} />
      <Route path="/planejar/renda-futura" element={<IncomeForecastPage />} />

      <Route path="/lancamentos" element={<LedgerPage />} />
      <Route path="/lancamentos/importar" element={<ImportPage />} />
      <Route path="/lancamentos/negociacoes/nova" element={<TradeFormPage />} />
      <Route path="/lancamentos/negociacoes/:id/editar" element={<TradeFormPage />} />
      <Route path="/lancamentos/proventos/novo" element={<EarningFormPage />} />
      <Route path="/lancamentos/proventos/:id/editar" element={<EarningFormPage />} />
      <Route path="/lancamentos/eventos/novo" element={<EventFormPage />} />

      <Route path="/configuracoes/estrategia" element={<StrategyPage />} />
      <Route path="/configuracoes/contas" element={<AccountsPage />} />
      <Route path="/configuracoes/dados-de-mercado" element={<MarketDataPage />} />
      <Route path="/configuracoes/acesso-agentico" element={<AgenticPage />} />
      <Route path="/configuracoes/acesso-agentico/nova" element={<AgentKeyFormPage />} />
      <Route path="/configuracoes/acesso-agentico/:keyId" element={<AgentKeyFormPage />} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
