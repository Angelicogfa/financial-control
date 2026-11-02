/** Routes of the app by user task (Phase 48.R3): pt-BR addresses in the web, English in the
 *  API. Every old address redirects to its new place (`legacyRoutes.ts`). */

import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { InstrumentRoute, LegacyAssetRedirect } from "../features/instrument/InstrumentRoute";
import { IncomePage } from "../features/portfolio/IncomePage";
import { ReconciliationPage } from "../features/portfolio/ReconciliationPage";
import { WatchlistPage } from "../features/watchlist/WatchlistPage";
import { AssetFormPage } from "../pages/asset/AssetFormPage";
import { ContributePage } from "../pages/contribute/ContributePage";
import { DisclosuresPage } from "../pages/disclosures/DisclosuresPage";
import { HealthPage } from "../pages/health/HealthPage";
import { HomePage } from "../pages/home/HomePage";
import { EarningFormPage } from "../pages/ledger/EarningFormPage";
import { EventFormPage } from "../pages/ledger/EventFormPage";
import { ImportPage } from "../pages/ledger/ImportPage";
import { LedgerPage } from "../pages/ledger/LedgerPage";
import { TradeFormPage } from "../pages/ledger/TradeFormPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PerformancePage } from "../pages/performance/PerformancePage";
import { PortfolioPage } from "../pages/portfolio/PortfolioPage";
import { RecommendationPage } from "../pages/recommendation/RecommendationPage";
import { MiningPage } from "../pages/research/MiningPage";
import { ResearchPage } from "../pages/research/ResearchPage";
import { AccountsPage } from "../pages/settings/AccountsPage";
import { AgenticPage } from "../pages/settings/agentic/AgenticPage";
import { AgentKeyFormPage } from "../pages/settings/agentic/AgentKeyFormPage";
import { MarketDataPage } from "../pages/settings/MarketDataPage";
import { StrategyPage } from "../pages/settings/StrategyPage";
import { CompareStudiesPage } from "../pages/simulation/CompareStudiesPage";
import { NewStudyPage } from "../pages/simulation/NewStudyPage";
import { QualityPage } from "../pages/simulation/QualityPage";
import { StudiesPage } from "../pages/simulation/StudiesPage";
import { StudyPage } from "../pages/simulation/StudyPage";
import { AssetComparePage } from "../pages/tools/AssetComparePage";
import { FixedIncomeComparePage } from "../pages/tools/FixedIncomeComparePage";
import { LEGACY_PATTERNS, legacyTarget } from "./legacyRoutes";

function LegacyRedirect() {
  const location = useLocation();
  const to = legacyTarget(location.pathname, location.search);
  return to ? <Navigate to={to} replace state={location.state} /> : <NotFoundPage />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/inicio" element={<HomePage />} />

      <Route path="/carteira" element={<PortfolioPage />} />
      <Route path="/carteira/rentabilidade" element={<PerformancePage />} />
      <Route path="/carteira/proventos" element={<IncomePage />} />
      <Route path="/carteira/raio-x" element={<HealthPage />} />
      <Route path="/carteira/conferir" element={<ReconciliationPage />} />
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

      {/* Old navigation (until Phase 48.R9); the asset by id needs its ticker first. */}
      <Route path="/asset/:id" element={<LegacyAssetRedirect />} />
      <Route path="/asset/:id/edit" element={<LegacyAssetRedirect edit />} />
      {LEGACY_PATTERNS.map((pattern) => (
        <Route key={pattern} path={pattern} element={<LegacyRedirect />} />
      ))}

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
