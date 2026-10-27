import { useCallback, useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { api } from "../api/endpoints";
import { CloseIcon, LogoutIcon, MenuIcon, MoonIcon, SunIcon } from "./icons";
import { DESKTOP_QUERY, NAV_SECTIONS, pageTitleFor } from "./navigation";
import { applyTheme, currentTheme, type Theme } from "./theme";

function matchesDesktop(): boolean {
  return typeof window.matchMedia === "function" ? window.matchMedia(DESKTOP_QUERY).matches : true;
}

/** Shell of the reference app: fixed sidebar with sections, topbar with the page title and
 *  a drawer below 900px (ADR 0007). */
export function AppShell({
  username,
  onLogout,
  children,
}: Readonly<{ username: string; onLogout: () => void; children: ReactNode }>) {
  const location = useLocation();
  const [desktop, setDesktop] = useState(matchesDesktop);
  const [menuOpen, setMenuOpen] = useState(matchesDesktop);
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const [alertCount, setAlertCount] = useState(0);
  const [workerErrorCount, setWorkerErrorCount] = useState(0);

  const refreshWorkerErrorCount = useCallback(() => {
    api.market
      .workerErrors()
      .then((result) => setWorkerErrorCount(result.unresolved_count))
      .catch(() => setWorkerErrorCount(0));
  }, []);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(DESKTOP_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      setDesktop(event.matches);
      setMenuOpen(event.matches);
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  // The alert and worker error counts refresh on navigation; failing just hides the number.
  useEffect(() => {
    api.alerts
      .list()
      .then((result) => setAlertCount(result.alerts.length))
      .catch(() => setAlertCount(0));
    refreshWorkerErrorCount();
  }, [location.pathname, refreshWorkerErrorCount]);

  useEffect(() => {
    const onChanged = () => refreshWorkerErrorCount();
    window.addEventListener("fincontrol:worker-errors-changed", onChanged);
    return () => window.removeEventListener("fincontrol:worker-errors-changed", onChanged);
  }, [refreshWorkerErrorCount]);

  const overlay = !desktop && menuOpen;
  useEffect(() => {
    if (!overlay) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overlay]);

  const closeIfOverlay = useCallback(() => {
    if (!desktop) setMenuOpen(false);
  }, [desktop]);

  const toggleTheme = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  };

  return (
    <div className="app-shell">
      {overlay && <div className="app-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />}

      <aside id="app-sidebar" className={`app-sidebar${menuOpen ? " is-open" : ""}`} aria-label="Menu principal">
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true">
            FC
          </span>
          <div className="app-brand-text">
            <span className="app-brand-title">Financial Control</span>
            <span className="app-brand-subtitle">ARCA · fundamentalista</span>
          </div>
          {overlay && (
            <button
              type="button"
              className="app-icon-button app-drawer-close"
              onClick={() => setMenuOpen(false)}
              aria-label="Fechar menu"
              title="Fechar menu"
              style={{ marginLeft: "auto" }}
            >
              <CloseIcon width={16} height={16} />
            </button>
          )}
        </div>

        <nav className="app-nav">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="app-nav-section">
              <p className="app-nav-section-label">{section.label}</p>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={closeIfOverlay}
                  className={({ isActive }) => `app-nav-item${isActive ? " active" : ""}`}
                >
                  <item.icon width={17} height={17} />
                  {item.label}
                  {item.showsAlertCount && alertCount > 0 && (
                    <span className="app-nav-count" aria-label={`${alertCount} alertas`}>
                      {alertCount}
                    </span>
                  )}
                  {item.showsWorkerErrorCount && workerErrorCount > 0 && (
                    <span
                      className="app-nav-count"
                      aria-label={`${workerErrorCount} erros do worker`}
                    >
                      {workerErrorCount}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="app-sidebar-footer">
          <span className="app-avatar" aria-hidden="true">
            {(username || "?").slice(0, 2)}
          </span>
          <div className="app-user-info">
            <div className="app-user-name">{username || "—"}</div>
            <div className="app-user-role">Investidor</div>
          </div>
          <button
            type="button"
            className="app-icon-button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}
            title={theme === "dark" ? "Tema claro" : "Tema escuro"}
          >
            {theme === "dark" ? <SunIcon width={16} height={16} /> : <MoonIcon width={16} height={16} />}
          </button>
          <button type="button" className="app-icon-button" onClick={onLogout} aria-label="Sair" title="Sair">
            <LogoutIcon width={16} height={16} />
          </button>
        </div>
      </aside>

      <div className="app-content">
        <header className="app-topbar">
          <button
            type="button"
            className="app-icon-button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label={menuOpen ? "Recolher menu" : "Abrir menu"}
            aria-expanded={menuOpen}
            aria-controls="app-sidebar"
          >
            <MenuIcon width={17} height={17} />
          </button>
          <span className="app-topbar-title">{pageTitleFor(location.pathname)}</span>
        </header>
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
