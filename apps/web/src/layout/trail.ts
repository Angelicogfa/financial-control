/** Breadcrumb trail (Phase 40.3): where each page sits and the way the user came to it.
 *
 *  Section pages sit under Início. A detail page (an asset, a contribution plan, a ledger form)
 *  hangs from the page it was opened from, so Início › Aportar › Plano de aporte › Ativo leads
 *  back exactly there. Every crumb links to the address the page last had, query string
 *  included, so a page comes back with the filters it had. */

export interface TrailEntry {
  path: string;
  search: string;
}

export interface Crumb {
  label: string;
  /** Link of an ancestor; null for the current page. */
  to: string | null;
}

export type NavigationKind = "PUSH" | "POP" | "REPLACE";

interface RouteSpec {
  test: (path: string) => boolean;
  label: string;
  parent: (path: string) => string | null;
  /** Hangs from the page it was opened from, when there is one. */
  detail?: boolean;
}

const HOME = "/home";
const under = (parent: string) => () => parent;

const ROUTES: RouteSpec[] = [
  { test: (p) => p === HOME, label: "Início", parent: () => null },
  { test: (p) => p.startsWith("/performance"), label: "Desempenho", parent: under(HOME) },
  { test: (p) => p.startsWith("/health"), label: "Saúde da carteira", parent: under(HOME) },
  { test: (p) => p.startsWith("/disclosures"), label: "Fatos relevantes", parent: under(HOME) },
  { test: (p) => p === "/asset/new", label: "Novo ativo", parent: under("/portfolio"), detail: true },
  {
    test: (p) => /^\/asset\/[^/]+\/edit$/.test(p),
    label: "Editar ativo",
    parent: (p) => p.replace(/\/edit$/, ""),
  },
  { test: (p) => p.startsWith("/asset/"), label: "Ativo", parent: under("/portfolio"), detail: true },
  { test: (p) => p.startsWith("/portfolio"), label: "Carteira", parent: under(HOME) },
  { test: (p) => p.startsWith("/research"), label: "Pesquisar", parent: under(HOME) },
  { test: (p) => /^\/contribute\/.+/.test(p), label: "Plano de aporte", parent: under("/contribute"), detail: true },
  { test: (p) => p.startsWith("/contribute"), label: "Aportar", parent: under(HOME) },
  { test: (p) => p === "/ledger/import", label: "Importar extrato B3", parent: under("/ledger") },
  { test: (p) => p.startsWith("/ledger/trades/"), label: "Negociação", parent: under("/ledger"), detail: true },
  { test: (p) => p.startsWith("/ledger/earnings/"), label: "Provento", parent: under("/ledger"), detail: true },
  { test: (p) => p.startsWith("/ledger/events/"), label: "Evento corporativo", parent: under("/ledger"), detail: true },
  { test: (p) => p.startsWith("/ledger"), label: "Lançamentos", parent: under(HOME) },
  { test: (p) => p.startsWith("/tools/fixed-income"), label: "Comparar renda fixa", parent: under(HOME) },
  { test: (p) => p.startsWith("/tools/compare"), label: "Comparar ativos", parent: under(HOME) },
  { test: (p) => p === "/tools/simulation/new", label: "Novo estudo", parent: under("/tools/simulation") },
  { test: (p) => p === "/tools/simulation/compare", label: "Comparar estudos", parent: under("/tools/simulation") },
  { test: (p) => p === "/tools/simulation/quality", label: "Qualidade dos modelos", parent: under("/tools/simulation") },
  { test: (p) => /^\/tools\/simulation\/\d+$/.test(p), label: "Estudo", parent: under("/tools/simulation") },
  { test: (p) => p.startsWith("/tools/simulation"), label: "Simular carteira", parent: under(HOME) },
  { test: (p) => p.startsWith("/settings/strategy"), label: "Estratégia", parent: under(HOME) },
  { test: (p) => p.startsWith("/settings/accounts"), label: "Contas", parent: under(HOME) },
  { test: (p) => p.startsWith("/settings/market-data"), label: "Dados de mercado", parent: under(HOME) },
  { test: (p) => p === "/settings/agentic/new", label: "Nova chave MCP", parent: under("/settings/agentic") },
  { test: (p) => p.startsWith("/settings/agentic/"), label: "Chave MCP", parent: under("/settings/agentic") },
  { test: (p) => p.startsWith("/settings/agentic"), label: "Acesso agêntico", parent: under(HOME) },
];

const NOT_FOUND: RouteSpec = { test: () => true, label: "Página não encontrada", parent: under(HOME) };
const MAX_TRAIL = 20;
const MAX_CRUMBS = 6;

function spec(path: string): RouteSpec {
  return ROUTES.find((r) => r.test(path)) ?? NOT_FOUND;
}

export function pageLabel(path: string): string {
  return spec(path).label;
}

/** The trail after a navigation: going to a page already in it goes back up to it. */
export function nextTrail(trail: TrailEntry[], entry: TrailEntry, kind: NavigationKind): TrailEntry[] {
  const last = trail[trail.length - 1];
  if (kind === "REPLACE" || (last && last.path === entry.path)) {
    return [...trail.slice(0, -1), entry];
  }
  const earlier = trail.map((t) => t.path).lastIndexOf(entry.path);
  const kept = earlier >= 0 ? trail.slice(0, earlier) : trail;
  return [...kept, entry].slice(-MAX_TRAIL);
}

function href(entry: TrailEntry): string {
  return `${entry.path}${entry.search}`;
}

/** The address a page last had in the trail (with its filters), or the bare path. */
function lastAddress(path: string, trail: TrailEntry[]): string {
  const seen = [...trail].reverse().find((t) => t.path === path);
  return seen ? href(seen) : path;
}

function chain(path: string, trail: TrailEntry[]): Crumb[] {
  const crumbs: Crumb[] = [];
  let parent = spec(path).parent(path);
  while (parent !== null && crumbs.length < MAX_CRUMBS) {
    crumbs.unshift({ label: pageLabel(parent), to: lastAddress(parent, trail) });
    parent = spec(parent).parent(parent);
  }
  return crumbs;
}

/** Crumbs of the last page in the trail: its ancestors as links, itself as the current one. */
export function crumbsFor(trail: TrailEntry[]): Crumb[] {
  const current = trail[trail.length - 1];
  if (!current) return [];
  const before = trail.slice(0, -1);
  const from = before[before.length - 1];
  let ancestors: Crumb[];
  if (spec(current.path).detail && from && from.path !== current.path) {
    // Opened from another page: hang from it, keeping that page's own way up.
    ancestors = [
      ...crumbsFor(before).map((c) => (c.to === null ? { ...c, to: href(from) } : c)),
    ];
  } else {
    ancestors = chain(current.path, trail);
  }
  return [...ancestors.slice(-(MAX_CRUMBS - 1)), { label: pageLabel(current.path), to: null }];
}

/** Where "Voltar" goes when the browser has no earlier page of this app. */
export function parentAddress(trail: TrailEntry[]): string | null {
  const crumbs = crumbsFor(trail);
  return crumbs.length > 1 ? crumbs[crumbs.length - 2].to : null;
}
