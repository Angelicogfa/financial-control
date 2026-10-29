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
  NewsIcon,
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
      { to: "/disclosures", label: "Fatos relevantes", icon: NewsIcon },
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

/** Same breakpoint as `@media (max-width: 900px)` in theme.css. */
export const DESKTOP_QUERY = "(min-width: 901px)";
