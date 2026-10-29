/** Building blocks of a report page: a titled section, the lead sentence that tells what the
 *  numbers mean, the indicators that back it and the notes on how far the result can be read.
 *  Order on a result page: lead -> indicators -> chart -> detail -> notes. */

import { useState, type ReactNode } from "react";

export function Section({
  title,
  subtitle,
  actions,
  children,
  label,
  className = "",
}: Readonly<{
  title: ReactNode;
  subtitle?: ReactNode;
  /** Badges, links or buttons on the right of the title. */
  actions?: ReactNode;
  children?: ReactNode;
  label?: string;
  className?: string;
}>) {
  return (
    <section className={`app-section ${className}`.trim()} aria-label={label}>
      <header className="app-section-head">
        <div className="app-section-titles">
          <h2 className="app-section-title">{title}</h2>
          {subtitle && <p className="app-section-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="app-section-actions">{actions}</div>}
      </header>
      {children !== undefined && children !== null && children !== false && (
        <div className="app-section-body">{children}</div>
      )}
    </section>
  );
}

export type Tone = "neutral" | "positive" | "negative" | "caution";

/** The conclusion in one or two sentences, before any number. */
export function Lead({
  eyebrow = "Em resumo",
  tone = "neutral",
  children,
}: Readonly<{ eyebrow?: string; tone?: Tone; children: ReactNode }>) {
  return (
    <div className={`app-lead is-${tone}`} role="note" aria-label={eyebrow}>
      <span className="app-eyebrow">{eyebrow}</span>
      <div className="app-lead-text">{children}</div>
    </div>
  );
}

export interface KpiSpec {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: Tone;
}

export function KpiGrid({ items, label = "Indicadores" }: Readonly<{ items: KpiSpec[]; label?: string }>) {
  return (
    <dl className="app-kpis" aria-label={label}>
      {items.map((kpi) => (
        <div key={kpi.label} className={`app-kpi is-${kpi.tone ?? "neutral"}`}>
          <dt className="app-kpi-label">{kpi.label}</dt>
          <dd className="app-kpi-value">{kpi.value}</dd>
          {kpi.note && <dd className="app-kpi-note">{kpi.note}</dd>}
        </div>
      ))}
    </dl>
  );
}

const NOTES_VISIBLE = 3;

/** How far the result can be read: premises and sample limits, stacked one per line.
 *  `caution` is for what changes the conclusion; the rest are neutral reading notes. */
export function Notes({
  items,
  title = "Como ler este resultado",
  tone = "neutral",
  label,
}: Readonly<{ items: string[]; title?: string; tone?: "neutral" | "caution"; label?: string }>) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  const shown = open ? items : items.slice(0, NOTES_VISIBLE);
  const hidden = items.length - shown.length;
  return (
    <aside className={`app-notes is-${tone}`} aria-label={label ?? title}>
      <h3 className="app-notes-title">{title}</h3>
      <ul className="app-notes-list">
        {shown.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {items.length > NOTES_VISIBLE && (
        <button type="button" className="app-link-button" onClick={() => setOpen((o) => !o)}>
          {open ? "Mostrar menos" : `Mostrar mais ${hidden}`}
        </button>
      )}
    </aside>
  );
}

/** A segmented control for a small set of exclusive options (periods, scenarios). */
export function Segmented<K extends string>({
  options,
  value,
  onChange,
  label,
}: Readonly<{ options: Array<[K, string]>; value: K; onChange: (key: K) => void; label: string }>) {
  return (
    <div className="app-segmented" role="group" aria-label={label}>
      {options.map(([key, text]) => (
        <button key={key} type="button" aria-pressed={key === value} onClick={() => onChange(key)}>
          {text}
        </button>
      ))}
    </div>
  );
}
