import { useState } from "react";

import { api } from "../../api/endpoints";
import type { AssetPriceHistoryDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Signed } from "../../components/Badge";
import { Section, Segmented } from "../../components/Section";
import { ErrorBanner, Loading } from "../../components/States";
import { day, money, pct } from "../../utils/format";
import { TrendChart } from "../../viz/TrendChart";

type Range = AssetPriceHistoryDTO["range"];

export const PRICE_RANGES: Array<[Range, string]> = [
  ["6mo", "6 meses"],
  ["1y", "1 ano"],
  ["2y", "2 anos"],
  ["5y", "5 anos"],
  ["max", "Tudo"],
];

const RANGE_PHRASES: Record<Range, string> = {
  "6mo": "Em 6 meses",
  "1y": "Em 12 meses",
  "2y": "Em 2 anos",
  "5y": "Em 5 anos",
  max: "Em todo o histórico",
};

/** The asset's closes over a chosen period, with the change, the high and the low. The
 *  one-year series of the analysis is shown while the period loads or when the API fails. */
export function PriceHistory({
  assetId,
  ticker,
  currency,
  fallback,
}: Readonly<{
  assetId: number;
  ticker: string;
  currency: string;
  fallback: Array<{ date?: string; close?: number }>;
}>) {
  const [range, setRange] = useState<Range>("1y");
  const state = useApi(`asset-prices-${assetId}-${range}`, () => api.assets.prices(assetId, range));
  const data = state.data;
  const fromFallback = !data && range === "1y" && fallback.length >= 2;
  const points = data
    ? data.points.map((p) => ({ date: p.date, close: p.close as number | null }))
    : fromFallback
      ? fallback.map((p) => ({ date: p.date ?? "", close: typeof p.close === "number" ? p.close : null }))
      : [];
  const price = (v: number) => money(v, currency);

  return (
    <Section
      title="Preço"
      subtitle={
        data && data.change != null ? (
          <>
            {RANGE_PHRASES[range]}, {ticker}{" "}
            <Signed value={data.change}>
              {data.change >= 0 ? "subiu" : "caiu"} {pct(Math.abs(data.change), 1)}
            </Signed>
            .
          </>
        ) : (
          "Fechamento diário; escolha o período."
        )
      }
      actions={<Segmented options={PRICE_RANGES} value={range} onChange={setRange} label="Período do gráfico de preço" />}
    >
      {state.loading && !data && !fromFallback ? (
        <Loading lines={4} label="Carregando o preço" />
      ) : state.error && !fromFallback ? (
        <ErrorBanner error={state.error} onRetry={state.reload} />
      ) : points.length < 2 ? (
        <p className="app-muted">Sem histórico de preços neste período.</p>
      ) : (
        <>
          <TrendChart
            title={`Preço de ${ticker}: ${PRICE_RANGES.find(([k]) => k === range)?.[1]}`}
            labels={points.map((p) => day(p.date))}
            hint="Passe o mouse para ler o fechamento de cada dia."
            format={price}
            series={[{ key: "close", label: ticker, color: "var(--viz-serie-1)", values: points.map((p) => p.close) }]}
          />
          {data && (data.high || data.low) && (
            <div className="price-summary" aria-label="Resumo do período">
              {data.high && (
                <span>
                  Máxima <strong>{price(data.high.price)}</strong> em {day(data.high.date)}
                </span>
              )}
              {data.low && (
                <span>
                  Mínima <strong>{price(data.low.price)}</strong> em {day(data.low.date)}
                </span>
              )}
              {(data.dropped_spikes ?? 0) > 0 && (
                <span>Cotações isoladas erradas do provedor foram removidas.</span>
              )}
            </div>
          )}
        </>
      )}
    </Section>
  );
}
