import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { fetchSession, logout, type AuthState } from "./api/auth";
import { UNAUTHORIZED_EVENT } from "./api/http";
import { AppShell } from "./layout/AppShell";
import { AssetDetailPage } from "./pages/asset/AssetDetailPage";
import { AssetFormPage } from "./pages/asset/AssetFormPage";
import { ContributePage } from "./pages/contribute/ContributePage";
import { HomePage } from "./pages/home/HomePage";
import { EarningFormPage } from "./pages/ledger/EarningFormPage";
import { EventFormPage } from "./pages/ledger/EventFormPage";
import { ImportPage } from "./pages/ledger/ImportPage";
import { LedgerPage } from "./pages/ledger/LedgerPage";
import { TradeFormPage } from "./pages/ledger/TradeFormPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PerformancePage } from "./pages/performance/PerformancePage";
import { PortfolioPage } from "./pages/portfolio/PortfolioPage";
import { ResearchPage } from "./pages/research/ResearchPage";
import { AccountsPage } from "./pages/settings/AccountsPage";
import { AgenticPage } from "./pages/settings/agentic/AgenticPage";
import { AgentKeyFormPage } from "./pages/settings/agentic/AgentKeyFormPage";
import { MarketDataPage } from "./pages/settings/MarketDataPage";
import { FixedIncomeComparePage } from "./pages/tools/FixedIncomeComparePage";
import { StrategyPage } from "./pages/settings/StrategyPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/performance" element={<PerformancePage />} />
      <Route path="/portfolio" element={<PortfolioPage />} />
      <Route path="/asset/new" element={<AssetFormPage />} />
      <Route path="/asset/:id" element={<AssetDetailPage />} />
      <Route path="/asset/:id/edit" element={<AssetFormPage />} />
      <Route path="/research" element={<ResearchPage />} />
      <Route path="/contribute" element={<ContributePage />} />
      <Route path="/contribute/:planId" element={<ContributePage />} />
      <Route path="/ledger" element={<LedgerPage />} />
      <Route path="/ledger/import" element={<ImportPage />} />
      <Route path="/ledger/trades/new" element={<TradeFormPage />} />
      <Route path="/ledger/trades/:id/edit" element={<TradeFormPage />} />
      <Route path="/ledger/earnings/new" element={<EarningFormPage />} />
      <Route path="/ledger/earnings/:id/edit" element={<EarningFormPage />} />
      <Route path="/ledger/events/new" element={<EventFormPage />} />
      <Route path="/tools/fixed-income" element={<FixedIncomeComparePage />} />
      <Route path="/settings/strategy" element={<StrategyPage />} />
      <Route path="/settings/accounts" element={<AccountsPage />} />
      <Route path="/settings/market-data" element={<MarketDataPage />} />
      <Route path="/settings/agentic" element={<AgenticPage />} />
      <Route path="/settings/agentic/new" element={<AgentKeyFormPage />} />
      <Route path="/settings/agentic/:keyId" element={<AgentKeyFormPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

/** Session gate: the login stays outside the shell; an expired session returns to it. */
export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "checking" });

  useEffect(() => {
    let active = true;
    fetchSession().then((state) => {
      if (active) setAuth(state);
    });
    const onUnauthorized = () =>
      setAuth({ status: "anonymous", reason: "Sua sessão expirou. Entre novamente." });
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => {
      active = false;
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    };
  }, []);

  const handleLogout = useCallback(async () => {
    await logout();
    setAuth({ status: "anonymous" });
  }, []);

  if (auth.status === "checking") {
    return (
      <div className="login-canvas" role="status">
        Carregando…
      </div>
    );
  }
  if (auth.status === "anonymous") {
    return (
      <LoginPage notice={auth.reason} onLoggedIn={(username) => setAuth({ status: "authenticated", username })} />
    );
  }
  return (
    <BrowserRouter>
      <AppShell username={auth.username} onLogout={() => void handleLogout()}>
        <AppRoutes />
      </AppShell>
    </BrowserRouter>
  );
}
