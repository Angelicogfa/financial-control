/** Menu by operation context (ADR 0005) in the sections of ADR 0007. */

import type { IconProps } from "./icons";
import {
  BankIcon,
  BotIcon,
  ColumnsIcon,
  BriefcaseIcon,
  DatabaseIcon,
  HistoryIcon,
  HomeIcon,
  ListIcon,
  PlusCircleIcon,
  PulseIcon,
  ScaleIcon,
  SearchIcon,
  SlidersIcon,
  TrendIcon,
} from "./icons";
import type { JSX } from "react";

export interface NavItem {
  to: string;
  label: string;
  icon: (props: IconProps) => JSX.Element;
  /** Shows the number of pending alerts next to the item. */
  showsAlertCount?: boolean;
  /** Shows the number of unresolved worker request errors next to the item. */
  showsWorkerErrorCount?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: "Visão geral",
    items: [
      { to: "/home", label: "Início", icon: HomeIcon, showsAlertCount: true },
      { to: "/performance", label: "Desempenho", icon: TrendIcon },
      { to: "/health", label: "Saúde da carteira", icon: PulseIcon },
    ],
  },
  {
    label: "Operação",
    items: [
      { to: "/portfolio", label: "Carteira", icon: BriefcaseIcon },
      { to: "/research", label: "Pesquisar", icon: SearchIcon },
      { to: "/contribute", label: "Aportar", icon: PlusCircleIcon },
      { to: "/ledger", label: "Lançamentos", icon: ListIcon },
    ],
  },
  {
    label: "Ferramentas",
    items: [
      { to: "/tools/compare", label: "Comparar ativos", icon: ColumnsIcon },
      { to: "/tools/fixed-income", label: "Comparar renda fixa", icon: ScaleIcon },
      { to: "/tools/simulation", label: "Simular carteira", icon: HistoryIcon },
    ],
  },
  {
    label: "Configuração",
    items: [
      { to: "/settings/strategy", label: "Estratégia", icon: SlidersIcon },
      { to: "/settings/accounts", label: "Contas", icon: BankIcon },
      {
        to: "/settings/market-data",
        label: "Dados de mercado",
        icon: DatabaseIcon,
        showsWorkerErrorCount: true,
      },
      { to: "/settings/agentic", label: "Acesso agêntico", icon: BotIcon },
    ],
  },
];

const PAGE_TITLES: Array<{ test: (path: string) => boolean; title: string }> = [
  { test: (p) => p === "/home", title: "Início" },
  { test: (p) => p.startsWith("/performance"), title: "Desempenho" },
  { test: (p) => p.startsWith("/health"), title: "Saúde da carteira" },
  { test: (p) => p === "/asset/new", title: "Novo ativo" },
  { test: (p) => p.startsWith("/asset/"), title: "Ativo" },
  { test: (p) => p.startsWith("/portfolio"), title: "Carteira" },
  { test: (p) => p.startsWith("/research"), title: "Pesquisar" },
  { test: (p) => p.startsWith("/contribute"), title: "Aportar" },
  { test: (p) => p === "/ledger/import", title: "Importar extrato B3" },
  { test: (p) => p.startsWith("/ledger"), title: "Lançamentos" },
  { test: (p) => p.startsWith("/tools/fixed-income"), title: "Comparar renda fixa" },
  { test: (p) => p.startsWith("/tools/compare"), title: "Comparar ativos" },
  { test: (p) => p.startsWith("/tools/simulation"), title: "Simular carteira" },
  { test: (p) => p.startsWith("/settings/strategy"), title: "Estratégia" },
  { test: (p) => p.startsWith("/settings/accounts"), title: "Contas" },
  { test: (p) => p.startsWith("/settings/market-data"), title: "Dados de mercado" },
  { test: (p) => p === "/settings/agentic/new", title: "Nova chave MCP" },
  { test: (p) => p.startsWith("/settings/agentic"), title: "Acesso agêntico" },
];

export function pageTitleFor(pathname: string): string {
  return PAGE_TITLES.find((entry) => entry.test(pathname))?.title ?? "Página não encontrada";
}

/** Same breakpoint as `@media (max-width: 900px)` in theme.css. */
export const DESKTOP_QUERY = "(min-width: 901px)";
