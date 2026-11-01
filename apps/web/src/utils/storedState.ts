/** Page state that survives leaving the page and coming back (Phase 40.3).
 *
 *  Filters, the last search and unsaved edits live in sessionStorage under a key, so the
 *  breadcrumb, "Voltar" and the browser back button return to the page as it was. Storage
 *  may be unavailable (private window, blocked site data): the state then just starts fresh. */

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const PREFIX = "fincontrol:page:";

export function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: unknown): void {
  try {
    if (value === undefined) window.sessionStorage.removeItem(PREFIX + key);
    else window.sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // storage unavailable: the page simply starts fresh next time
  }
}

export function clearStored(key: string): void {
  writeStored(key, undefined);
}

/** `useState` whose value is kept for the session under `key` (JSON values only). */
export function useStoredState<T>(key: string, initial: T): [T, (next: T | ((current: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readStored(key, initial));
  const set = useCallback(
    (next: T | ((current: T) => T)) => {
      setValue((current) => {
        const resolved = typeof next === "function" ? (next as (c: T) => T)(current) : next;
        writeStored(key, resolved);
        return resolved;
      });
    },
    [key],
  );
  return [value, set];
}

/** Navigation state of a page opened from the menu: it starts clean (see `useFreshEntry`). */
export const FRESH_ENTRY = { fresh: true } as const;

/** Clear every stored value whose key starts with `prefix`. */
export function clearStoredPrefix(prefix: string): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const key = window.sessionStorage.key(i);
      if (key?.startsWith(PREFIX + prefix)) keys.push(key);
    }
    for (const key of keys) window.sessionStorage.removeItem(key);
  } catch {
    // storage unavailable: nothing was kept
  }
}

/**
 * A page opened from the menu starts without the state it kept; coming back to it (the trail,
 * "Voltar", the browser's back button) finds it as it was. The menu link carries `FRESH_ENTRY`:
 * the page clears its keys before they are read and then drops the mark from the history, so
 * going back to this entry later restores what was done after it. Returns a value to key the
 * page's content with, so a new entry from the menu remounts it even when it was already open.
 */
export function useFreshEntry(prefix: string): number {
  const location = useLocation();
  const navigate = useNavigate();
  const fresh = (location.state as { fresh?: boolean } | null)?.fresh === true;
  const handled = useRef<string | null>(null);
  const entries = useRef(0);
  if (fresh && handled.current !== location.key) {
    clearStoredPrefix(prefix);
    handled.current = location.key;
    entries.current += 1;
  }
  useEffect(() => {
    if (fresh) navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: null });
  }, [fresh, location.pathname, location.search, location.hash, navigate]);
  return entries.current;
}
