/** Page state that survives leaving the page and coming back (Phase 40.3).
 *
 *  Filters, the last search and unsaved edits live in sessionStorage under a key, so the
 *  breadcrumb, "Voltar" and the browser back button return to the page as it was. Storage
 *  may be unavailable (private window, blocked site data): the state then just starts fresh. */

import { useCallback, useState } from "react";

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
