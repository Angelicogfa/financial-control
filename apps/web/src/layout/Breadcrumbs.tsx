/** Breadcrumb in the topbar with a back button (Phase 40.3). */

import { useEffect, useRef } from "react";
import { Link, useLocation, useNavigate, useNavigationType } from "react-router-dom";

import { readStored, writeStored } from "../utils/storedState";
import { ChevronRightIcon } from "./icons";
import { crumbsFor, nextTrail, parentAddress, type NavigationKind, type TrailEntry } from "./trail";

const TRAIL_KEY = "trail";
const SCROLL_KEY = "scroll";

function inBrowser(): boolean {
  return typeof window.scrollTo === "function" && !navigator.userAgent.includes("jsdom");
}

/** Back to where the page was scrolled, once its data has made it tall enough. */
function restoreScroll(y: number): () => void {
  let tries = 0;
  let timer: number | undefined;
  const tick = () => {
    const tallEnough = document.documentElement.scrollHeight >= y + window.innerHeight;
    if (tallEnough || tries >= 40) {
      window.scrollTo(0, y);
      return;
    }
    tries += 1;
    timer = window.setTimeout(tick, 50);
  };
  tick();
  return () => window.clearTimeout(timer);
}

export function Breadcrumbs() {
  const location = useLocation();
  const kind = useNavigationType() as NavigationKind;
  const navigate = useNavigate();
  const trail = useRef<TrailEntry[] | null>(null);
  const seenKey = useRef<string | null>(null);

  // The trail moves once per navigation (render-time so the first paint already shows it).
  if (trail.current === null) trail.current = readStored<TrailEntry[]>(TRAIL_KEY, []);
  if (seenKey.current !== location.key) {
    trail.current = nextTrail(
      trail.current,
      { path: location.pathname, search: location.search },
      seenKey.current === null && trail.current.length === 0 ? "PUSH" : kind,
    );
    seenKey.current = location.key;
    writeStored(TRAIL_KEY, trail.current);
  }

  // Scroll: remembered when leaving a page, restored when coming back with "Voltar"/back.
  useEffect(() => {
    if (!inBrowser()) return undefined;
    const key = location.key;
    const cancel =
      kind === "POP"
        ? restoreScroll(readStored<Record<string, number>>(SCROLL_KEY, {})[key] ?? 0)
        : (window.scrollTo(0, 0), () => undefined);
    return () => {
      cancel();
      const positions = readStored<Record<string, number>>(SCROLL_KEY, {});
      positions[key] = window.scrollY;
      writeStored(SCROLL_KEY, positions);
    };
  }, [location.key, kind]);

  const crumbs = crumbsFor(trail.current);
  const parent = parentAddress(trail.current);
  const historyIndex = (window.history.state as { idx?: number } | null)?.idx ?? 0;
  const back = () => {
    if (historyIndex > 0) navigate(-1);
    else if (parent) navigate(parent);
  };

  return (
    <nav className="app-breadcrumb" aria-label="Trilha de navegação">
      {(historyIndex > 0 || parent) && crumbs.length > 1 && (
        <button type="button" className="app-breadcrumb-back" onClick={back} title="Voltar à página anterior">
          <span aria-hidden="true">←</span> Voltar
        </button>
      )}
      <ol>
        {crumbs.map((crumb, i) => (
          <li key={`${crumb.label}-${i}`}>
            {i > 0 && <ChevronRightIcon width={12} height={12} />}
            {crumb.to === null ? (
              <span className="app-topbar-title" aria-current="page">
                {crumb.label}
              </span>
            ) : (
              <Link to={crumb.to}>{crumb.label}</Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
