/** Top Sticky Header and Off-Canvas Hamburger Drawer (without any secondary quick-nav bar). */

import React from "react";

export type AppViewId =
  | "dashboard"
  | "portfolio"
  | "contribution"
  | "earnings"
  | "transactions"
  | "analytics";

export interface NavItem {
  id: AppViewId;
  label: string;
  group: string;
  badge?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard Executivo", group: "Visão Geral", badge: "ARCA" },
  { id: "portfolio", label: "Carteira & Renda Fixa", group: "Visão Geral", badge: "Ativos" },
  {
    id: "contribution",
    label: "Simulador de Aporte (2 Níveis)",
    group: "Visão Geral",
    badge: "Aportar",
  },
  {
    id: "earnings",
    label: "Proventos & Consolidação P/L",
    group: "Movimentações & Renda",
    badge: "MVP",
  },
  {
    id: "transactions",
    label: "Lançamentos (Compras/Vendas)",
    group: "Movimentações & Renda",
  },
  {
    id: "analytics",
    label: "Risco, Benchmarks & Metas ARCA",
    group: "Inteligência & Governança",
  },
];

interface HamburgerDrawerProps {
  activeView: AppViewId;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onLogout?: () => void;
  onSelectView: (view: AppViewId) => void;
}

export const HamburgerDrawer: React.FC<HamburgerDrawerProps> = ({
  activeView,
  isOpen,
  onToggle,
  onClose,
  onLogout,
  onSelectView,
}) => {
  const activeItem = NAV_ITEMS.find((i) => i.id === activeView) ?? NAV_ITEMS[0];
  const groups = Array.from(new Set(NAV_ITEMS.map((i) => i.group)));

  const handleSelect = (view: AppViewId) => {
    onSelectView(view);
    onClose();
  };

  return (
    <>
      <header className="top-header">
        <div className="header-left">
          <button
            type="button"
            className="hamburger-btn"
            aria-label="Abrir menu de navegação"
            aria-expanded={isOpen}
            onClick={onToggle}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <div className="brand-group">
            <div className="brand-logo">FC</div>
            <span className="brand-name">Financial Control</span>
            <span className="brand-crumb">/</span>
            <span className="current-view-badge">{activeItem.label}</span>
          </div>
        </div>

        <div className="header-right">
          <span className="macro-pill mono">
            <span className="live-dot" />
            CDI 10,75% a.a. • IPCA 4,50% • USD R$ 5,15
          </span>
          {onLogout && (
            <button type="button" className="btn btn-ghost" onClick={onLogout}>
              Sair
            </button>
          )}
        </div>
      </header>

      <div
        className={`drawer-backdrop ${isOpen ? "open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={`hamburger-drawer ${isOpen ? "open" : ""}`}
        aria-label="Menu Principal"
      >
        <div className="drawer-top">
          <div className="brand-group">
            <div className="brand-logo">FC</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>Financial Control</div>
              <div style={{ fontSize: "0.73rem", color: "#94a3b8" }}>
                Metodologia ARCA &amp; Cerrado Opcional
              </div>
            </div>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            aria-label="Fechar menu"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <nav className="drawer-body">
          {groups.map((group) => (
            <div key={group}>
              <div className="drawer-group-title">{group}</div>
              {NAV_ITEMS.filter((item) => item.group === group).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`drawer-link ${activeView === item.id ? "active" : ""}`}
                  onClick={() => handleSelect(item.id)}
                >
                  <span>{item.label}</span>
                  {item.badge && <span className="drawer-badge">{item.badge}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
};
