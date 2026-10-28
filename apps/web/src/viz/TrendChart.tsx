import { useId, useState } from "react";

/** Lines over time, one per series, labeled at the end, with the value of the hovered
 *  point read in text below the chart. Missing points (null) break the line. Optional bands
 *  shade the area between two value lists (e.g. a percentile fan) behind the lines. */

const WIDTH = 720;
const HEIGHT = 220;
const PAD = { top: 14, right: 130, bottom: 26, left: 52 };

export interface TrendSeries {
  key: string;
  label: string;
  color: string;
  values: Array<number | null>;
}

export interface TrendBand {
  key: string;
  color: string;
  low: number[];
  high: number[];
}

export function TrendChart({
  title,
  labels,
  series,
  hint,
  format = (v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 1 }),
  baseline,
  bands = [],
}: Readonly<{
  /** What the chart concludes, for screen readers (<title>). */
  title: string;
  labels: string[];
  series: TrendSeries[];
  hint: string;
  format?: (value: number) => string;
  /** A reference line (e.g. 100 on a base-100 chart). */
  baseline?: number;
  /** Shaded areas between `low` and `high`, drawn under the lines. */
  bands?: TrendBand[];
}>) {
  const titleId = useId();
  const [active, setActive] = useState<number | null>(null);
  const known = [
    ...series.flatMap((s) => s.values.filter((v): v is number => v !== null)),
    ...bands.flatMap((b) => [...b.low, ...b.high]),
  ];
  if (labels.length < 2 || known.length === 0) return null;

  const rawLow = Math.min(...known, baseline ?? Infinity);
  const rawHigh = Math.max(...known, baseline ?? -Infinity);
  const padding = (rawHigh - rawLow) * 0.08 || Math.abs(rawHigh) * 0.05 || 1;
  const low = rawLow - padding;
  const high = rawHigh + padding;
  const usableX = WIDTH - PAD.left - PAD.right;
  const usableY = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (usableX * i) / (labels.length - 1);
  const y = (value: number) => PAD.top + usableY - ((value - low) / (high - low)) * usableY;
  const last = labels.length - 1;

  const pathOf = (values: Array<number | null>) => {
    let started = false;
    return values
      .map((v, i) => {
        if (v === null) {
          started = false;
          return "";
        }
        const command = started ? "L" : "M";
        started = true;
        return `${command}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      })
      .join(" ");
  };

  const ends = series
    .map((s) => {
      const index = s.values.map((v, i) => (v === null ? -1 : i)).reduce((a, b) => Math.max(a, b), -1);
      return { s, index, value: index >= 0 ? (s.values[index] as number) : null };
    })
    .filter((e) => e.value !== null)
    .sort((a, b) => (b.value as number) - (a.value as number));

  return (
    <div className="viz-grafico">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="viz-svg"
        role="img"
        aria-labelledby={titleId}
        onMouseLeave={() => setActive(null)}
      >
        <title id={titleId}>{title}</title>
        {[low + (high - low) * 0.1, (low + high) / 2, high - (high - low) * 0.1].map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} className="viz-grade" />
            <text x={PAD.left - 8} y={y(tick) + 4} className="viz-tick" textAnchor="end">
              {format(tick)}
            </text>
          </g>
        ))}
        {baseline !== undefined && (
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(baseline)} y2={y(baseline)} className="viz-base" />
        )}
        {bands.map((b) => (
          <path
            key={b.key}
            d={`${b.high.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} ${b.low
              .map((v, i) => `L${x(i).toFixed(1)},${y(v).toFixed(1)}`)
              .reverse()
              .join(" ")} Z`}
            fill={b.color}
            fillOpacity={0.18}
            stroke="none"
          />
        ))}
        {series.map((s) => (
          <path
            key={s.key}
            d={pathOf(s.values)}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}
        {ends.map((end, i) => {
          const natural = y(end.value as number) + 4;
          const above = i > 0 ? y(ends[i - 1].value as number) + 4 : -Infinity;
          return (
            <g key={end.s.key}>
              <circle
                cx={x(end.index)}
                cy={y(end.value as number)}
                r={4}
                fill={end.s.color}
                stroke="var(--viz-surface)"
                strokeWidth={2}
              />
              <text x={WIDTH - PAD.right + 12} y={Math.max(natural, above + 14)} className="viz-direct-label">
                {end.s.label} {format(end.value as number)}
              </text>
            </g>
          );
        })}
        {labels.map((label, i) => (
          <rect
            key={`${label}-${i}`}
            x={x(i) - usableX / (labels.length - 1) / 2}
            y={PAD.top}
            width={usableX / (labels.length - 1)}
            height={usableY}
            fill="transparent"
            onMouseEnter={() => setActive(i)}
          />
        ))}
        {active !== null && (
          <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={HEIGHT - PAD.bottom} className="viz-cursor" />
        )}
        <text x={PAD.left} y={HEIGHT - 6} className="viz-tick">
          {labels[0]}
        </text>
        <text x={x(last)} y={HEIGHT - 6} className="viz-tick" textAnchor="end">
          {labels[last]}
        </text>
      </svg>
      <div className="viz-tooltip" role="status">
        {active !== null ? (
          <>
            <strong>{labels[active]}</strong>
            {series.map((s) => (
              <span key={s.key} className="viz-legend-item">
                <span className="viz-legend-key" style={{ background: s.color }} aria-hidden="true" />
                {s.label}: {s.values[active] === null ? "—" : format(s.values[active] as number)}
              </span>
            ))}
          </>
        ) : (
          <span className="app-muted">{hint}</span>
        )}
      </div>
    </div>
  );
}
