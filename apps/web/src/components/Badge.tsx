import type { ReactNode } from "react";

export type Tone = "success" | "warning" | "danger" | "info" | "neutral" | string;

export function Badge({ tone = "neutral", children }: Readonly<{ tone?: Tone; children: ReactNode }>) {
  const className = tone === "neutral" ? "app-badge" : `app-badge app-badge-${tone}`;
  return <span className={className}>{children}</span>;
}

/** Signed value colored by direction (text says the sign too). */
export function Signed({ value, children }: Readonly<{ value: number | null | undefined; children: ReactNode }>) {
  const tone = value === null || value === undefined || value === 0 ? "" : value > 0 ? "app-positive" : "app-negative";
  return <span className={tone}>{children}</span>;
}
