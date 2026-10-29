import { useEffect, useRef, useState } from "react";

/** The pixel width of the chart container, so the SVG is drawn at 1:1 and its text keeps
 *  the type scale (a fixed viewBox stretched to a wide screen doubles the font size).
 *  Without ResizeObserver (tests, old browsers) it stays at `fallback`. */
export function useChartWidth<T extends HTMLElement>(fallback = 720, min = 320) {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver((entries) => {
      const measured = Math.round(entries[0]?.contentRect.width ?? 0);
      if (measured > 0) setWidth(Math.max(min, measured));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [min]);

  return [ref, width] as const;
}

/** Round tick values ("1, 2, 5 x 10^n") covering [low, high]. */
export function niceTicks(low: number, high: number, count = 4): number[] {
  if (!Number.isFinite(low) || !Number.isFinite(high)) return [];
  if (high === low) return [low];
  const raw = (high - low) / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = Math.ceil(low / step) * step; v <= high + step * 1e-9; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/** Vertical positions for end labels: in value order, at least `gap` apart, inside [top, bottom]. */
export function spreadLabels(wanted: number[], gap: number, top: number, bottom: number): number[] {
  const order = wanted.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const placed: number[] = [];
  order.forEach(({ y }, k) => {
    placed[k] = Math.max(y, top, k > 0 ? placed[k - 1] + gap : -Infinity);
  });
  const overflow = (placed[placed.length - 1] ?? 0) - bottom;
  if (overflow > 0) {
    for (let k = placed.length - 1; k >= 0; k -= 1) {
      const limit = k === placed.length - 1 ? bottom : placed[k + 1] - gap;
      placed[k] = Math.max(top, Math.min(placed[k], limit));
    }
  }
  const result: number[] = new Array(wanted.length);
  order.forEach(({ i }, k) => {
    result[i] = placed[k];
  });
  return result;
}
