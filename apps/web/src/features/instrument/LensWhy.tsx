/** "Por quê" of a contribution line (Phase 48.R6): the lenses of the asset, its strongest and
 *  weakest points, loaded only when asked (and cached with the instrument page). */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/endpoints";
import { ErrorBanner, Loading } from "../../components/States";
import { LensBars, lensHighlights } from "./chapters";
import { instrumentQueryKey } from "./paths";

function Lenses({ ticker }: Readonly<{ ticker: string }>) {
  const view = useQuery({
    queryKey: instrumentQueryKey(ticker),
    queryFn: ({ signal }) => api.instruments.get(ticker, signal),
  });
  if (view.isPending) return <Loading lines={2} label={`Lentes de ${ticker}`} />;
  if (view.isError) return <ErrorBanner error={view.error} />;
  const lenses = view.data.lenses;
  if (!lenses) return <p className="app-muted">As lentes deste ativo ainda não foram calculadas.</p>;
  const { strong, weak } = lensHighlights(lenses);
  return (
    <div>
      {strong && <p>{strong}</p>}
      {weak && <p>{weak}</p>}
      <LensBars lenses={lenses} />
    </div>
  );
}

export function LensWhy({ ticker }: Readonly<{ ticker: string }>) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app-lens-why">
      <button
        type="button"
        className="app-link-button"
        aria-expanded={open}
        aria-label={`${open ? "Ocultar" : "Ver"} as lentes de ${ticker}`}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Ocultar lentes" : "Ver lentes"}
      </button>
      {open && <Lenses ticker={ticker} />}
    </div>
  );
}
