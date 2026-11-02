/** Address and small shared pieces of the instrument page (Phase 48.R4). */

import type { InstrumentQuoteDTO } from "../../api/types";
import { Badge } from "../../components/Badge";
import { dateTime } from "../../utils/format";

/** One address for any asset: the ticker (or Tesouro symbol), never the registration id. */
export function instrumentPath(key: string): string {
  return `/ativo/${encodeURIComponent(key)}`;
}

export const instrumentQueryKey = (key: string) => ["instrument", key.toUpperCase()] as const;

export const QUOTE_SOURCE: Record<string, string> = {
  STORED_QUOTE: "cotação guardada",
  CATALOG_CLOSE: "fechamento do catálogo da B3",
  TREASURY_PRICE: "preço do Tesouro",
  MANUAL: "preço manual",
};

/** Where the price came from and when (rule "erro nunca vira zero", ADR 0007). */
export function QuoteAge({ quote }: Readonly<{ quote: InstrumentQuoteDTO }>) {
  const source = QUOTE_SOURCE[quote.source] ?? quote.source;
  return <Badge>{quote.as_of ? `${source} · ${dateTime(quote.as_of)}` : source}</Badge>;
}
