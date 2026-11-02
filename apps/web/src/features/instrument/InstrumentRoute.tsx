/** `/ativo/:ticker` (Phase 48.R3): one address for any asset, registered or not.
 *
 *  A registered asset opens its current detail page; any other ticker or Tesouro bond opens a
 *  summary of what the database has, with "Acompanhar" to register it. Phase 48.R4 replaces
 *  both with the page in chapters. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { ApiError } from "../../api/http";
import type { AssetType, InstrumentViewDTO } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { AssetDetailPage } from "../../pages/asset/AssetDetailPage";
import { AssetFormPage } from "../../pages/asset/AssetFormPage";
import { ASSET_TYPE_LABELS } from "../../utils/labels";
import { dateTime, money, num, pct } from "../../utils/format";

export const instrumentQueryKey = (key: string) => ["instrument", key.toUpperCase()] as const;

export function instrumentPath(key: string): string {
  return `/ativo/${encodeURIComponent(key)}`;
}

const QUOTE_SOURCE: Record<string, string> = {
  STORED_QUOTE: "cotação guardada",
  CATALOG_CLOSE: "fechamento do catálogo da B3",
  TREASURY_PRICE: "preço do Tesouro",
  MANUAL: "preço manual",
};

function typeLabel(type: string | null | undefined): string | null {
  if (!type) return null;
  return ASSET_TYPE_LABELS[type as AssetType] ?? type;
}

function NotFound({ ticker }: Readonly<{ ticker: string }>) {
  return (
    <div className="app-page app-page-narrow">
      <Empty
        title={`Não encontramos ${ticker}`}
        hint="O código não está no catálogo da B3, no Tesouro Direto nem entre os seus ativos."
      >
        <Link className="app-primary-button" to="/explorar">
          Ir para Explorar
        </Link>
      </Empty>
    </div>
  );
}

function useInstrument(ticker: string) {
  return useQuery({
    queryKey: instrumentQueryKey(ticker),
    queryFn: ({ signal }) => api.instruments.get(ticker, signal),
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
  });
}

export function InstrumentRoute({ edit = false }: Readonly<{ edit?: boolean }>) {
  const { ticker = "" } = useParams();
  const instrument = useInstrument(ticker);

  if (instrument.isPending) {
    return (
      <div className="app-page">
        <Loading lines={4} label={`Abrindo ${ticker}`} />
      </div>
    );
  }
  if (instrument.isError) {
    const error = instrument.error;
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) {
      return <NotFound ticker={ticker} />;
    }
    return (
      <div className="app-page">
        <ErrorBanner error={error} onRetry={() => void instrument.refetch()} />
      </div>
    );
  }
  const view = instrument.data;
  const assetId = view.tracking?.asset_id;
  if (edit) {
    return assetId ? <AssetFormPage assetId={assetId} /> : <Navigate to={instrumentPath(view.key)} replace />;
  }
  if (assetId) return <AssetDetailPage assetId={assetId} />;
  return <InstrumentSummary view={view} />;
}

/** The summary of an asset that is not registered: only what the database already has. */
export function InstrumentSummary({ view }: Readonly<{ view: InstrumentViewDTO }>) {
  const client = useQueryClient();
  const follow = useMutation({
    mutationFn: () =>
      api.research.follow({
        ticker: view.ticker,
        name: view.name,
        asset_type: (view.asset_type as AssetType | null) ?? null,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: instrumentQueryKey(view.key) }),
  });
  const quote = view.quote;
  const gaps = view.data_gaps ?? [];
  const subtitle = [typeLabel(view.asset_type), view.sector].filter(Boolean).join(" · ");
  const canFollow = view.kind === "LISTED";

  return (
    <div className="app-page">
      <PageHeader
        title={`${view.ticker} · ${view.name}`}
        subtitle={subtitle || undefined}
        actions={
          <>
            {canFollow && (
              <button
                type="button"
                className="app-primary-button"
                disabled={follow.isPending}
                onClick={() => follow.mutate()}
              >
                {follow.isPending ? "Acompanhando…" : "Acompanhar"}
              </button>
            )}
            {canFollow && (
              <Link className="app-secondary-button" to={`/explorar/comparar?tickers=${encodeURIComponent(view.ticker)}`}>
                Comparar
              </Link>
            )}
          </>
        }
      />
      <ErrorBanner error={follow.error} />

      <section className="app-card" aria-label="Preço">
        {quote ? (
          <p>
            <strong>{money(quote.price, quote.currency)}</strong>
            {quote.change_pct !== null && quote.change_pct !== undefined && (
              <> ({pct(quote.change_pct, 2, true)} no dia)</>
            )}{" "}
            — {QUOTE_SOURCE[quote.source] ?? quote.source}
            {quote.as_of && <>, {dateTime(quote.as_of)}</>}
          </p>
        ) : (
          <p>Sem preço guardado.</p>
        )}
      </section>

      {view.indicators && (
        <section className="app-card" aria-label="Indicadores">
          <dl className="app-kv">
            <dt>P/L</dt>
            <dd>{num(view.indicators.price_to_earnings)}</dd>
            <dt>P/VP</dt>
            <dd>{num(view.indicators.price_to_book)}</dd>
            <dt>Dividend yield</dt>
            <dd>{pct(view.indicators.dividend_yield)}</dd>
            <dt>ROE</dt>
            <dd>{pct(view.indicators.return_on_equity)}</dd>
          </dl>
        </section>
      )}

      {view.treasury && (
        <section className="app-card" aria-label="Título do Tesouro">
          <p>
            Vence em {view.treasury.maturity_date}; taxa de compra{" "}
            {view.treasury.buy_rate !== null && view.treasury.buy_rate !== undefined
              ? `${num(view.treasury.buy_rate)}% a.a.`
              : "não publicada"}
            .
          </p>
        </section>
      )}

      {gaps.length > 0 && (
        <section className="app-card" aria-label="O que ainda falta">
          <ul>
            {gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
