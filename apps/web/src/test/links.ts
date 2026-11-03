/** Internal links of the app read from its sources (Phase 48.R9): with the redirects of the
 *  old navigation gone, a link to a path the router does not know would be a dead end. */

const sources = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../test/**", "!../api/**"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const routesSource = import.meta.glob<string>("../app/AppRoutes.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
});

export interface InternalLink {
  file: string;
  path: string;
}

/** Every `path="..."` of `AppRoutes`. */
export function appRoutePaths(): string[] {
  const text = Object.values(routesSource)[0] ?? "";
  return [...text.matchAll(/<Route path="([^"]+)"/g)].map((m) => m[1]).filter((p) => p !== "*");
}

// A link: `to="/x"`, `to={"/x"}`, `` to={`/x/${id}`} ``, `navigate("/x")`, `to: "/x"`, ...
const LINK = /(?:\bto=\{?|\bnavigate\(|\bto:\s*|\broute:\s*|\bhref=\{?)\s*(["'`])(\/[^"'`]*)\1/g;

/** Literal internal links of the sources, with `${...}` read as one path segment. */
export function internalLinks(): InternalLink[] {
  const links: InternalLink[] = [];
  for (const [file, text] of Object.entries(sources)) {
    for (const match of text.matchAll(LINK)) {
      const raw = match[2].replace(/\$\{[^}]*\}/g, "1");
      const path = raw.split(/[?#]/)[0] || "/";
      if (path.startsWith("/api/")) continue;
      links.push({ file, path });
    }
  }
  return links;
}
