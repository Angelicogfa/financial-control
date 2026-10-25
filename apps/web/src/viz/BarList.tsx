import type { ReactNode } from "react";

/** Horizontal bars: label, the bar against a 0–1 scale and the value in text — the bar is
 *  never the only way to read the number. Optional target mark, tolerance band and a second
 *  thin bar (before × after). */
export interface Bar {
  id: string;
  label: ReactNode;
  /** 0 to 1: bar width. */
  share: number;
  value: ReactNode;
  note?: ReactNode;
  tone?: string;
  /** 0 to 1: target mark. */
  goal?: number;
  /** [from, to] in 0–1: tolerance band drawn behind the bar. */
  band?: [number, number];
  /** 0 to 1: a second bar under the first (e.g. after the contribution). */
  second?: number;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));
const percent = (value: number) => `${Math.round(clamp(value) * 1000) / 10}%`;

export function BarList({ bars, label }: Readonly<{ bars: Bar[]; label: string }>) {
  return (
    <ul className="viz-bars" aria-label={label}>
      {bars.map((bar) => (
        <li key={bar.id} className="viz-bar">
          <span className="viz-bar-label">
            {bar.label}
            {bar.note && <small>{bar.note}</small>}
          </span>
          <span className="viz-bar-track" aria-hidden="true">
            {bar.band && (
              <span
                className="viz-bar-band"
                style={{ left: percent(bar.band[0]), width: percent(bar.band[1] - bar.band[0]) }}
              />
            )}
            <span
              className={`viz-bar-fill${bar.tone ? ` ${bar.tone}` : ""}${bar.second !== undefined ? " is-thin" : ""}`}
              style={{ width: percent(bar.share) }}
            />
            {bar.second !== undefined && (
              <span className="viz-bar-fill is-thin is-second is-after" style={{ width: percent(bar.second) }} />
            )}
            {bar.goal !== undefined && <span className="viz-bar-goal" style={{ left: percent(bar.goal) }} />}
          </span>
          <span className="viz-bar-value">{bar.value}</span>
        </li>
      ))}
    </ul>
  );
}
