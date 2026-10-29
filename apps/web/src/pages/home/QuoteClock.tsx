/** When the stored quotes were fetched, with a button that asks the worker for fresh ones (Phase 38).
 *  Screens read quotes from the database; the worker refreshes the holdings every few minutes. */

import { useEffect, useRef, useState } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import { useApi } from "../../api/useApi";
import { Spinner } from "../../components/States";
import { plural } from "../../utils/format";

const POLL_MS = 4000;
const POLL_LIMIT = 15;

function clock(iso: string): string {
  const at = new Date(iso);
  const sameDay = at.toDateString() === new Date().toDateString();
  return at.toLocaleString("pt-BR", sameDay ? { timeStyle: "short" } : { dateStyle: "short", timeStyle: "short" });
}

export function QuoteClock({ onRefreshed }: Readonly<{ onRefreshed: () => void }>) {
  const status = useApi("quote-status", () => api.market.quoteStatus());
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const refresh = async () => {
    setError(null);
    setWaiting(true);
    const before = status.data?.newest_at ?? null;
    try {
      await api.market.requestJob("warm_portfolio_quotes");
    } catch (err) {
      setError(errorMessage(err));
      setWaiting(false);
      return;
    }
    // The worker serves the request within seconds; wait for newer quotes, then reload.
    let tries = 0;
    const poll = async () => {
      tries += 1;
      try {
        const now = await api.market.quoteStatus();
        if ((now.newest_at ?? null) !== before || tries >= POLL_LIMIT) {
          setWaiting(false);
          status.reload();
          onRefreshed();
          return;
        }
      } catch {
        // keep waiting; the next poll tries again
      }
      timer.current = window.setTimeout(() => void poll(), POLL_MS);
    };
    timer.current = window.setTimeout(() => void poll(), POLL_MS);
  };

  const data = status.data;
  if (!data || data.holdings === 0) return null;
  return (
    <span className="home-quote-clock" role="status">
      <span className="app-muted">
        {data.oldest_at ? `Cotações de ${clock(data.oldest_at)}` : "Cotações ainda não atualizadas"}
        {data.stale > 0 &&
          ` · ${plural(data.stale, "posição", "posições")} sem atualização há mais de ${data.stale_minutes} min`}
      </span>
      <button type="button" className="app-link-button" onClick={() => void refresh()} disabled={waiting}>
        {waiting && <Spinner size="sm" />}
        <span>{waiting ? "Atualizando…" : "Atualizar"}</span>
      </button>
      {error && <span className="app-negative">{error}</span>}
    </span>
  );
}
