import { useCallback, useEffect, useState } from "react";
import { BrowserRouter } from "react-router-dom";

import { fetchSession, logout, type AuthState } from "./api/auth";
import { UNAUTHORIZED_EVENT } from "./api/http";
import { AppShell } from "./layout/AppShell";
import { AppProviders } from "./app/AppProviders";
import { AppRoutes } from "./app/AppRoutes";
import { LoginPage } from "./pages/LoginPage";

export { AppRoutes };

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
    <AppProviders>
      <BrowserRouter>
        <AppShell username={auth.username} onLogout={() => void handleLogout()}>
          <AppRoutes />
        </AppShell>
      </BrowserRouter>
    </AppProviders>
  );
}
