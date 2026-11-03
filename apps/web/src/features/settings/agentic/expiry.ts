import type { KeyExpiryDays } from "../../../api/types";

/** Accepted validity durations in days for personal MCP keys. */
export const EXPIRY_OPTIONS: KeyExpiryDays[] = [30, 90, 180, 365];
export const DEFAULT_EXPIRY: KeyExpiryDays = 90;

/** Days before expiration at which the badge switches to warning. */
export const EXPIRING_SOON_DAYS = 14;

const DAY_MS = 24 * 60 * 60 * 1000;

export type ExpiryState = "expired" | "soon" | "ok";

/** Whole days left until expiration, rounded up. Zero or negative means expired. */
export function daysLeft(expiresAt: string, now: number = Date.now()): number {
  return Math.ceil((new Date(expiresAt).getTime() - now) / DAY_MS);
}

export function expiryState(expiresAt: string, now: number = Date.now()): ExpiryState {
  const remaining = daysLeft(expiresAt, now);
  if (new Date(expiresAt).getTime() <= now) return "expired";
  return remaining <= EXPIRING_SOON_DAYS ? "soon" : "ok";
}
