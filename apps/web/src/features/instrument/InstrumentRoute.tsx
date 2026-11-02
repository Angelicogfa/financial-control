/** `/ativo/:ticker` (Phase 48.R3): one address for any asset, registered or not.
 *
 *  A registered asset opens its current detail page; any other ticker or Tesouro bond opens a
 *  summary of what the database has, with "Acompanhar" to register it. Both are told in
 *  chapters (Phase 48.R4). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { ApiError } from "../../api/http";
import type { ArcaClass, AssetType, InstrumentViewDTO } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { AssetDetailPage } from "../../pages/asset/AssetDetailPage";
import { AssetFormPage } from "../../pages/asset/AssetFormPage";
import { PriceHistory } from "../../pages/asset/PriceHistory";
import { ARCA_LABELS, ASSET_TYPE_LABELS } from "../../utils/labels";
import { dateTime, day, money, num, pct } from "../../utils/format";
import { Chapter, ChapterIndex, LensBars, lensHighlights, useOpenChapters, type ChapterKey } from "./chapters";
import { instrumentPath, instrumentQueryKey, QUOTE_SOURCE, QuoteAge } from "./paths";

export { instrumentPath };

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
  if (assetId) return <AssetDetailPage assetId={assetId} view={view} />;
  return <InstrumentSummary view={view} />;
}

/** Any ticker or Tesouro bond that is not registered, as chapters with only what the database
 *  already has (Phase 48.R4). "Acompanhar" registers it and the full page takes over. */
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
  const chapters = useOpenChapters(["preco"]);
  const quote = view.quote;
  const gaps = view.data_gaps ?? [];
  const subtitle = [typeLabel(view.asset_type), view.sector].filter(Boolean).join(" · ");
  const listed = view.kind === "LISTED";
  const highlights = lensHighlights(view.lenses);
  const arca = view.lenses?.arca_class as ArcaClass | null | undefined;
  const year = view.forecast?.bands?.find((b) => b.months === 12);
  const indicators = view.indicators;
  const index: Array<{ key: ChapterKey; title?: string }> = [
    { key: "resumo" },
    { key: "carteira", title: "Como entraria" },
    { key: "preco" },
    ...(listed ? [{ key: "resultados" as const }, { key: "previsao" as const }] : []),
  ];

  return (
    <div className="app-page">
      <PageHeader
        title={`${view.ticker} · ${view.name}`}
        subtitle={
          <span className="app-button-row">
            {subtitle && <span>{subtitle}</span>}
            {quote && <QuoteAge quote={quote} />}
          </span>
        }
        actions={
          <>
            {listed && (
              <button
                type="button"
                className="app-primary-button"
                disabled={follow.isPending}
                onClick={() => follow.mutate()}
              >
                {follow.isPending ? "Acompanhando…" : "Acompanhar"}
              </button>
            )}
            {listed && (
              <Link className="app-secondary-button" to={`/explorar/comparar?tickers=${encodeURIComponent(view.ticker)}`}>
                Comparar
              </Link>
            )}
          </>
        }
      />
      <ErrorBanner error={follow.error} />

      <div className="app-chapters">
        <ChapterIndex chapters={index} />
        <div className="app-chapters-body">
          <Chapter
            id="resumo"
            lead={
              <>
                <p>
                  {quote ? (
                    <>
                      <strong>{money(quote.price, quote.currency)}</strong>
                      {quote.change_pct !== null && quote.change_pct !== undefined && (
                        <> ({pct(quote.change_pct, 2, true)} no dia)</>
                      )}{" "}
                      — {QUOTE_SOURCE[quote.source] ?? quote.source}
                      {quote.as_of && <>, {dateTime(quote.as_of)}</>}.
                    </>
                  ) : (
                    "Sem preço guardado."
                  )}
                </p>
                {listed && <p>{highlights.strong ?? "As lentes da recomendação ainda não foram calculadas para este ativo."}</p>}
                {highlights.weak && <p>{highlights.weak}</p>}
              </>
            }
          >
            {view.lenses && <LensBars lenses={view.lenses} />}
          </Chapter>

          <Chapter
            id="carteira"
            title="Como entraria"
            lead={
              listed ? (
                <p>
                  {arca
                    ? `Entraria em ${ARCA_LABELS[arca] ?? arca}. `
                    : "A classe ARCA é sugerida ao acompanhar o ativo. "}
                  Acompanhe para responder o checklist, ver o valuation e recebê-lo nas sugestões de aporte.
                </p>
              ) : (
                <p>Títulos do Tesouro entram na carteira pelo cadastro de um novo ativo de renda fixa.</p>
              )
            }
          >
            {!listed && (
              <Link className="app-secondary-button" to="/carteira/novo-ativo">
                Cadastrar título
              </Link>
            )}
          </Chapter>

          <Chapter id="preco" open={chapters.isOpen("preco")} onToggle={() => chapters.toggle("preco")}>
            {listed ? (
              <PriceHistory instrumentKey={view.key} ticker={view.ticker} currency={quote?.currency ?? "BRL"} fallback={[]} />
            ) : view.treasury ? (
              <dl className="app-definition-list">
                <dt>Vencimento</dt>
                <dd>{day(view.treasury.maturity_date)}</dd>
                <dt>Taxa de compra</dt>
                <dd>
                  {view.treasury.buy_rate !== null && view.treasury.buy_rate !== undefined
                    ? `${num(view.treasury.buy_rate)}% a.a.`
                    : "não publicada"}
                </dd>
                <dt>Preço de compra</dt>
                <dd>{view.treasury.buy_price ? money(view.treasury.buy_price) : "—"}</dd>
              </dl>
            ) : null}
          </Chapter>

          {listed && (
            <Chapter
              id="resultados"
              lead={
                indicators
                  ? [
                      indicators.price_to_earnings !== null && indicators.price_to_earnings !== undefined
                        ? `P/L ${num(indicators.price_to_earnings, 1)}`
                        : null,
                      indicators.price_to_book !== null && indicators.price_to_book !== undefined
                        ? `P/VP ${num(indicators.price_to_book, 2)}`
                        : null,
                      indicators.return_on_equity !== null && indicators.return_on_equity !== undefined
                        ? `ROE ${pct(indicators.return_on_equity, 1)}`
                        : null,
                      indicators.dividend_yield !== null && indicators.dividend_yield !== undefined
                        ? `DY ${pct(indicators.dividend_yield, 1)}`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Sem indicadores guardados."
                  : "Os indicadores deste ativo ainda não foram buscados."
              }
            />
          )}

          {listed && (
            <Chapter
              id="previsao"
              lead={
                view.forecast?.status === "OK" && year
                  ? `Em 12 meses, a faixa provável vai de ${money(year.p5)} a ${money(year.p95)} (mediana ${money(year.p50)}).`
                  : "A previsão deste ativo ainda não foi calculada com confiança suficiente."
              }
            />
          )}

          {gaps.length > 0 && (
            <section className="app-card app-card-padded" aria-label="O que ainda falta">
              <ul>
                {gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/** `/asset/:id` and `/asset/:id/edit` of the old navigation: find the ticker and move on,
 *  query kept (an old `?tab=` opens its chapter). Until Phase 48.R9. */
export function LegacyAssetRedirect({ edit = false }: Readonly<{ edit?: boolean }>) {
  const { id = "" } = useParams();
  const location = useLocation();
  const asset = useQuery({
    queryKey: ["asset-ticker", id],
    queryFn: ({ signal }) => api.assets.get(Number(id), signal),
    retry: false,
  });
  if (asset.isPending) {
    return (
      <div className="app-page">
        <Loading lines={4} />
      </div>
    );
  }
  if (asset.isError) return <NotFound ticker={`o ativo ${id}`} />;
  const to = `${instrumentPath(asset.data.ticker)}${edit ? "/editar" : ""}${location.search}`;
  return <Navigate to={to} replace state={location.state} />;
}
