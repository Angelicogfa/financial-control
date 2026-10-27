/** Contracted-rate conversion between the form (percent) and the API scale (ADR 0006). */

import type { FixedIncomeIndexer, TreasuryBondDTO } from "../api/types";
import { points } from "./format";

/** Default percentage shown in the form for each indexer. */
export const DEFAULT_RATE_PERCENT: Record<FixedIncomeIndexer, string> = {
  CDI: "110",
  SELIC: "100",
  IPCA: "6",
  PRE: "12",
};

/**
 * Convert the percentage typed by the user into the API value:
 * CDI/SELIC 110 -> 1.10 (multiplier) and PRE/IPCA 6.5 -> 0.065 (annual fraction).
 * Both cases divide by 100; the meaning of the result depends on the indexer.
 */
export function percentToContractedRate(percent: number): number {
  return Math.round((percent / 100) * 1_000_000) / 1_000_000;
}

/** Inverse of `percentToContractedRate`, for displaying stored terms. */
export function contractedRateToPercent(rate: number | string): number {
  return Math.round(Number(rate) * 100 * 10_000) / 10_000;
}

/** Format a Brapi Treasury rate (buyRate/sellRate) according to its rateType/indexer. */
export function formatTreasuryRate(
  bond: Pick<TreasuryBondDTO, "indexer" | "raw_indexer" | "rate_type">,
  rate: number | null | undefined,
): string {
  if (rate === null || rate === undefined) return "—";
  const formatted = points(rate, 2);
  if (bond.rate_type === "spreadOverSelic" || bond.indexer === "SELIC") {
    return `SELIC + ${formatted} a.a.`;
  }
  if (bond.rate_type === "realAnnualRateOverIgpm" || bond.raw_indexer === "igpm") {
    return `IGP-M + ${formatted} a.a.`;
  }
  if (bond.rate_type === "realAnnualRateOverIpca" || bond.indexer === "IPCA") {
    return `IPCA + ${formatted} a.a.`;
  }
  return `${formatted} a.a.`;
}

