/** Loading, error and empty states shared by every screen: no screen shows "R$ 0" when the
 *  API is down, it says so and offers to try again (findings I-06, I-07). */

import type { ReactNode } from "react";

import { errorMessage } from "../api/http";

export function Loading({ lines = 3, label = "Carregando" }: Readonly<{ lines?: number; label?: string }>) {
  return (
    <div className="app-skeleton" role="status" aria-live="polite">
      <span className="app-sr-only">{label}…</span>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorBanner({ error, onRetry }: Readonly<{ error: unknown; onRetry?: () => void }>) {
  if (!error) return null;
  return (
    <div className="app-error-banner" role="alert">
      <span>{errorMessage(error)}</span>
      {onRetry && (
        <button type="button" className="app-secondary-button" onClick={onRetry}>
          Tentar de novo
        </button>
      )}
    </div>
  );
}

export function Empty({
  title,
  hint,
  children,
}: Readonly<{ title: string; hint?: ReactNode; children?: ReactNode }>) {
  return (
    <div className="app-empty">
      <strong>{title}</strong>
      {hint && <span>{hint}</span>}
      {children && <div className="app-button-row">{children}</div>}
    </div>
  );
}

/** Renders the loading/error states, or the content once data arrived. */
export function Async<T>({
  state,
  children,
  lines,
}: Readonly<{
  state: { data: T | null; error: unknown; loading: boolean; reload: () => void };
  children: (data: T) => ReactNode;
  lines?: number;
}>) {
  if (state.error) return <ErrorBanner error={state.error} onRetry={state.reload} />;
  if (state.loading && state.data === null) return <Loading lines={lines} />;
  if (state.data === null) return null;
  return <>{children(state.data)}</>;
}
