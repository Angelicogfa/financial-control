import { PageHeader } from "../../components/PageHeader";
import { Watchlist } from "../../pages/research/ResearchPage";

/** Acompanhar (Phase 48.R3): the assets under observation, before buying them. */
export function WatchlistPage() {
  return (
    <div className="app-page">
      <PageHeader
        title="Acompanhar"
        subtitle="Os ativos que você observa antes de comprar: classe, situação no checklist e quando entram no aporte."
      />
      <Watchlist />
    </div>
  );
}
