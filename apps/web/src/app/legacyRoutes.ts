/** Where every address of the old navigation lives now (Phase 48.R3).
 *
 *  The rebuild never breaks a link: a bookmark, a link inside a page not yet rewritten or an
 *  agent answer pointing to `/portfolio` lands on `/carteira`, filters included. The asset
 *  page by id (`/asset/:id`) needs the ticker, so it is resolved by `LegacyAssetRedirect`.
 *  Remove these rules in Phase 48.R9, two phases after the last page moves. */

type Rule = [RegExp, (match: RegExpMatchArray, params: URLSearchParams) => string];

const RULES: Rule[] = [
  [/^\/$/, () => "/inicio"],
  [/^\/home$/, () => "/inicio"],
  [/^\/performance$/, () => "/carteira/rentabilidade"],
  [/^\/health$/, () => "/carteira/raio-x"],
  [/^\/portfolio$/, () => "/carteira"],
  [/^\/asset\/new$/, () => "/carteira/novo-ativo"],
  [/^\/disclosures$/, () => "/explorar/fatos-relevantes"],
  [/^\/research\/mining$/, () => "/explorar/garimpo"],
  [
    /^\/research$/,
    (_m, params) => {
      if (params.get("tab") !== "watchlist") return "/explorar";
      params.delete("tab");
      return "/acompanhar";
    },
  ],
  [/^\/tools\/compare$/, () => "/explorar/comparar"],
  [/^\/recommendation$/, () => "/planejar/modelo"],
  [/^\/contribute$/, () => "/aportar"],
  [/^\/contribute\/([^/]+)$/, (m) => `/aportar/${m[1]}`],
  [/^\/ledger$/, () => "/lancamentos"],
  [/^\/ledger\/import$/, () => "/lancamentos/importar"],
  [/^\/ledger\/trades\/new$/, () => "/lancamentos/negociacoes/nova"],
  [/^\/ledger\/trades\/([^/]+)\/edit$/, (m) => `/lancamentos/negociacoes/${m[1]}/editar`],
  [/^\/ledger\/earnings\/new$/, () => "/lancamentos/proventos/novo"],
  [/^\/ledger\/earnings\/([^/]+)\/edit$/, (m) => `/lancamentos/proventos/${m[1]}/editar`],
  [/^\/ledger\/events\/new$/, () => "/lancamentos/eventos/novo"],
  [/^\/tools\/fixed-income$/, () => "/planejar/renda-fixa"],
  [/^\/tools\/simulation$/, () => "/planejar"],
  [/^\/tools\/simulation\/new$/, () => "/planejar/estudos/novo"],
  [/^\/tools\/simulation\/compare$/, () => "/planejar/estudos/comparar"],
  [/^\/tools\/simulation\/quality$/, () => "/planejar/qualidade"],
  [/^\/tools\/simulation\/([^/]+)$/, (m) => `/planejar/estudos/${m[1]}`],
  [/^\/settings\/strategy$/, () => "/configuracoes/estrategia"],
  [/^\/settings\/accounts$/, () => "/configuracoes/contas"],
  [/^\/settings\/market-data$/, () => "/configuracoes/dados-de-mercado"],
  [/^\/settings\/agentic$/, () => "/configuracoes/acesso-agentico"],
  [/^\/settings\/agentic\/new$/, () => "/configuracoes/acesso-agentico/nova"],
  [/^\/settings\/agentic\/([^/]+)$/, (m) => `/configuracoes/acesso-agentico/${m[1]}`],
];

/** The new address of an old one, query string kept; null when `pathname` is not old. */
export function legacyTarget(pathname: string, search = ""): string | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  for (const [pattern, target] of RULES) {
    const match = path.match(pattern);
    if (!match) continue;
    const params = new URLSearchParams(search);
    const to = target(match, params);
    const query = params.toString();
    return query ? `${to}?${query}` : to;
  }
  return null;
}

/** Old paths the router must catch (React Router patterns), one per rule above. */
export const LEGACY_PATTERNS = [
  "/",
  "/home",
  "/performance",
  "/health",
  "/portfolio",
  "/asset/new",
  "/disclosures",
  "/research",
  "/research/mining",
  "/recommendation",
  "/contribute",
  "/contribute/:planId",
  "/ledger",
  "/ledger/import",
  "/ledger/trades/new",
  "/ledger/trades/:id/edit",
  "/ledger/earnings/new",
  "/ledger/earnings/:id/edit",
  "/ledger/events/new",
  "/tools/fixed-income",
  "/tools/compare",
  "/tools/simulation",
  "/tools/simulation/new",
  "/tools/simulation/compare",
  "/tools/simulation/quality",
  "/tools/simulation/:studyId",
  "/settings/strategy",
  "/settings/accounts",
  "/settings/market-data",
  "/settings/agentic",
  "/settings/agentic/new",
  "/settings/agentic/:keyId",
] as const;
