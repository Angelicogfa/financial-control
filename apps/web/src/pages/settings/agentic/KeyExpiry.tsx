import { useState } from "react";

import type { KeyExpiryDays } from "../../../api/types";
import { daysLeft, DEFAULT_EXPIRY, EXPIRY_OPTIONS, expiryState } from "./expiry";

const BADGE_CLASS = {
  expired: " app-badge-danger",
  soon: " app-badge-warning",
  ok: "",
} as const;

/** Displays remaining days until expiration with semantic badge color. */
export function ExpiryBadge({ expiresAt }: Readonly<{ expiresAt: string }>) {
  const state = expiryState(expiresAt);
  const formattedDate = new Date(expiresAt).toLocaleDateString("pt-BR");
  const remaining = daysLeft(expiresAt);

  return (
    <span className={`app-badge${BADGE_CLASS[state]}`} title={`Vence em ${formattedDate}`}>
      {state === "expired"
        ? "Expirada"
        : remaining === 1
          ? "Vence em 1 dia"
          : `Vence em ${remaining} dias`}
    </span>
  );
}

/** Validity duration selector for a newly created key. */
export function ExpirySelect({
  id,
  value,
  onChange,
}: Readonly<{
  id: string;
  value: KeyExpiryDays;
  onChange: (days: KeyExpiryDays) => void;
}>) {
  return (
    <div className="app-field">
      <label htmlFor={id}>Validade da chave</label>
      <select id={id} value={value} onChange={(e) => onChange(Number(e.target.value) as KeyExpiryDays)}>
        {EXPIRY_OPTIONS.map((days) => (
          <option key={days} value={days}>
            {days} dias
          </option>
        ))}
      </select>
    </div>
  );
}

/** Panel displaying current key expiration and allowing validity renewal. */
export function RenewPanel({
  expiresAt,
  onRenew,
}: Readonly<{
  expiresAt: string;
  onRenew: (days: KeyExpiryDays) => Promise<void>;
}>) {
  const [days, setDays] = useState<KeyExpiryDays>(DEFAULT_EXPIRY);
  const [renewing, setRenewing] = useState(false);
  const formattedDate = new Date(expiresAt).toLocaleDateString("pt-BR");
  const isExpired = expiryState(expiresAt) === "expired";

  async function handleRenew() {
    setRenewing(true);
    try {
      await onRenew(days);
    } finally {
      setRenewing(false);
    }
  }

  return (
    <section className="app-card app-card-padded app-key-renew" aria-label="Validade da chave">
      <p className="app-key-use-title">
        Validade da chave <ExpiryBadge expiresAt={expiresAt} />
      </p>
      <p
        className={isExpired ? undefined : "app-muted"}
        style={{
          margin: "var(--space-1) 0 var(--space-3)",
          color: isExpired ? "var(--app-danger-text)" : undefined,
        }}
      >
        {isExpired ? `Expirou em ${formattedDate}` : `Válida até ${formattedDate}`}
      </p>
      <div className="app-key-renew-row">
        <label htmlFor="key-renew-days">Renovar por</label>
        <select
          id="key-renew-days"
          value={days}
          onChange={(e) => setDays(Number(e.target.value) as KeyExpiryDays)}
        >
          {EXPIRY_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option} dias
            </option>
          ))}
        </select>
        <button type="button" className="app-secondary-button" disabled={renewing} onClick={() => void handleRenew()}>
          {renewing ? "Renovando…" : "Renovar validade"}
        </button>
      </div>
    </section>
  );
}
