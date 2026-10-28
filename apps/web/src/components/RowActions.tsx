import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Spinner } from "./States";

/**
 * Compact table-row actions: an icon carries the action, the label is the accessible
 * name and the hover tooltip, so tables keep their columns narrow.
 */

export function IconLink({ to, label, icon }: Readonly<{ to: string; label: string; icon: ReactNode }>) {
  return (
    <Link className="app-icon-button" to={to} aria-label={label} title={label}>
      {icon}
    </Link>
  );
}

export function IconButton({
  label,
  icon,
  onClick,
  busy = false,
  busyLabel,
  disabled = false,
  danger = false,
}: Readonly<{
  label: string;
  icon: ReactNode;
  onClick: () => void;
  busy?: boolean;
  /** Accessible name while the action runs, e.g. "Excluindo…". */
  busyLabel?: string;
  disabled?: boolean;
  danger?: boolean;
}>) {
  const name = busy && busyLabel ? busyLabel : label;
  return (
    <button
      type="button"
      className={`app-icon-button${danger ? " is-danger" : ""}`}
      aria-label={name}
      title={name}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      onClick={onClick}
    >
      {busy ? <Spinner size="sm" label={name} /> : icon}
    </button>
  );
}
