const WIDTH = 120;
const HEIGHT = 32;
const PAD = 3;

/** The small line of an indicator: only the shape of the series. Decorative — the number
 *  and the change next to it say the same in text. */
export function Sparkline({ values, domain }: Readonly<{ values: number[]; domain?: [number, number] }>) {
  if (values.length < 2) return null;
  const [low, high] = domain ?? [Math.min(...values), Math.max(...values)];
  const span = high - low || 1;
  const x = (i: number) => PAD + ((WIDTH - 2 * PAD) * i) / (values.length - 1);
  const y = (value: number) => HEIGHT - PAD - ((HEIGHT - 2 * PAD) * (value - low)) / span;
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values[values.length - 1];

  return (
    <svg className="viz-sparkline" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true" focusable="false">
      <path d={path} fill="none" stroke="var(--viz-serie-1)" strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={x(values.length - 1)} cy={y(last)} r={2.5} fill="var(--viz-serie-1)" />
    </svg>
  );
}
