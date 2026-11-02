/** Menu by user task (Phase 48.R3, REFACTORING_PLAN §3.1): seven destinations, each answering
 *  one question, plus the settings. A destination with more than one screen shows its
 *  sections as tabs under the topbar. */

import type { IconProps } from "./icons";
import {
  BankIcon,
  BotIcon,
  BriefcaseIcon,
  CompassIcon,
  DatabaseIcon,
  EyeIcon,
  HistoryIcon,
  HomeIcon,
  ListIcon,
  PlusCircleIcon,
  SlidersIcon,
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

export interface DestinationSection {
  to: string;
  label: string;
}

export interface Destination extends NavItem {
  question: string;
  sections: DestinationSection[];
}

export const DESTINATIONS: Destination[] = [
  {
    to: "/inicio",
    label: "Início",
    icon: HomeIcon,
    question: "Como estou?",
    showsAlertCount: true,
    sections: [],
  },
  {
    to: "/carteira",
    label: "Carteira",
    icon: BriefcaseIcon,
    question: "Está tudo certo?",
    sections: [
      { to: "/carteira", label: "Posições" },
      { to: "/carteira/rentabilidade", label: "Rentabilidade" },
      { to: "/carteira/raio-x", label: "Raio-X" },
    ],
  },
  {
    to: "/explorar",
    label: "Explorar",
    icon: CompassIcon,
    question: "O que existe por aí?",
    sections: [
      { to: "/explorar", label: "Screener e Tesouro" },
      { to: "/explorar/garimpo", label: "Garimpo" },
      { to: "/explorar/comparar", label: "Comparar" },
      { to: "/explorar/fatos-relevantes", label: "Fatos relevantes" },
    ],
  },
  {
    to: "/acompanhar",
    label: "Acompanhar",
    icon: EyeIcon,
    question: "O que estou vigiando?",
    sections: [],
  },
  {
    to: "/aportar",
    label: "Aportar",
    icon: PlusCircleIcon,
    question: "O que faço com o dinheiro?",
    sections: [],
  },
  {
    to: "/planejar",
    label: "Planejar",
    icon: HistoryIcon,
    question: "Para onde vou?",
    sections: [
      { to: "/planejar", label: "Simulações" },
      { to: "/planejar/renda-fixa", label: "Comparar renda fixa" },
      { to: "/planejar/modelo", label: "Modelo" },
      { to: "/planejar/qualidade", label: "Qualidade das previsões" },
    ],
  },
  {
    to: "/lancamentos",
    label: "Lançamentos",
    icon: ListIcon,
    question: "O que eu fiz?",
    sections: [
      { to: "/lancamentos", label: "Movimentações" },
      { to: "/lancamentos/importar", label: "Importar extrato" },
    ],
  },
];

export const SETTINGS: NavSection = {
  label: "Configurações",
  items: [
    { to: "/configuracoes/estrategia", label: "Estratégia", icon: SlidersIcon },
    { to: "/configuracoes/contas", label: "Contas", icon: BankIcon },
    {
      to: "/configuracoes/dados-de-mercado",
      label: "Dados de mercado",
      icon: DatabaseIcon,
      showsWorkerErrorCount: true,
    },
    { to: "/configuracoes/acesso-agentico", label: "Acesso agêntico", icon: BotIcon },
  ],
};

export const NAV_SECTIONS: NavSection[] = [{ label: "Operação", items: DESTINATIONS }, SETTINGS];

function under(path: string, to: string): boolean {
  return path === to || path.startsWith(`${to}/`);
}

/** The destination a path belongs to (the asset page sits under Explorar). */
export function destinationOf(path: string): Destination | null {
  if (path.startsWith("/ativo/") || path.startsWith("/asset/")) return DESTINATIONS.find((d) => d.to === "/explorar") ?? null;
  return DESTINATIONS.find((d) => under(path, d.to)) ?? null;
}

/** The section tab a path lights: the longest section address it sits under. */
export function activeSection(path: string, destination: Destination): DestinationSection | null {
  const matching = destination.sections.filter((s) => under(path, s.to));
  return matching.sort((a, b) => b.to.length - a.to.length)[0] ?? null;
}

/** Same breakpoint as `@media (max-width: 900px)` in theme.css. */
export const DESKTOP_QUERY = "(min-width: 901px)";
