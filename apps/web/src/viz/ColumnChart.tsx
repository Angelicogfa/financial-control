import { useId, useState } from "react";

/** Vertical columns per period (earnings per month, revenue per year). The hovered value is
 *  read in text below; the largest and the last are labeled on the chart. */

const WIDTH = 720;
const HEIGHT = 180;
const PAD = { top: 18, right: 12, bottom: 24, left: 12 };

export interface Column {
  label: string;
  value: number;
}

export function ColumnChart({
  title,
  columns,
  hint,
  format,
}: Readonly<{ title: string; columns: Column[]; hint: string; format: (value: number) => string }>) {
  const titleId = useId();
  const [active, setActive] = useState<number | null>(null);
  if (columns.length === 0) return null;

  const max = Math.max(...columns.map((c) => Math.abs(c.value)), 1);
  const slot = (WIDTH - PAD.left - PAD.right) / columns.length;
  const barWidth = Math.max(4, slot * 0.6);
  const usableY = HEIGHT - PAD.top - PAD.bottom;
  const largest = columns.reduce((best, c, i) => (Math.abs(c.value) > Math.abs(columns[best].value) ? i : best), 0);

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
        <line
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={HEIGHT - PAD.bottom}
          y2={HEIGHT - PAD.bottom}
          className="viz-grade"
        />
        {columns.map((column, i) => {
          const height = (Math.abs(column.value) / max) * usableY;
          const cx = PAD.left + slot * i + slot / 2;
          const showLabel = i === largest || i === columns.length - 1;
          return (
            <g key={`${column.label}-${i}`} onMouseEnter={() => setActive(i)}>
              <rect x={cx - slot / 2} y={PAD.top} width={slot} height={usableY} fill="transparent" />
              <rect
                x={cx - barWidth / 2}
                y={HEIGHT - PAD.bottom - height}
                width={barWidth}
                height={height}
                rx={2}
                className={`viz-column${column.value < 0 ? " is-negative" : ""}`}
              />
              {showLabel && column.value !== 0 && (
                <text x={cx} y={HEIGHT - PAD.bottom - height - 4} className="viz-direct-label" textAnchor="middle">
                  {format(column.value)}
                </text>
              )}
              {(i === 0 || i === columns.length - 1 || columns.length <= 12) && (
                <text x={cx} y={HEIGHT - 6} className="viz-tick" textAnchor="middle">
                  {column.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="viz-tooltip" role="status">
        {active !== null ? (
          <span>
            <strong>{columns[active].label}</strong>: {format(columns[active].value)}
          </span>
        ) : (
          <span className="app-muted">{hint}</span>
        )}
      </div>
    </div>
  );
}
