/** The home's story, the pure part: the headline built from the numbers, changes over the
 *  snapshot window and the aligned base-100 curves (ADR 0007). */

import type {
  AlertDTO,
  ClassAllocationDTO,
  PortfolioReportResponseDTO,
  SnapshotPointDTO,
} from "../../api/types";
import { brlCompact, pct, points } from "../../utils/format";

export interface Change {
  /** Fraction (0.021 = +2,1%). */
  value: number;
  days: number;
}

/** Change of the patrimony since the snapshot closest to `days` ago, net of contributions. */
export function patrimonyChange(
  snapshots: SnapshotPointDTO[],
  currentValue: number,
  days = 30,
  today = new Date(),
): Change | null {
  if (snapshots.length === 0) return null;
  const target = new Date(today);
  target.setDate(target.getDate() - days);
  const targetKey = target.toISOString().slice(0, 10);
  const base = [...snapshots].reverse().find((s) => s.snapshot_date <= targetKey) ?? snapshots[0];
  if (base.market_value <= 0) return null;
  const flows = snapshots
    .filter((s) => s.snapshot_date > base.snapshot_date)
    .reduce((sum, s) => sum + s.net_flow, 0);
  // Calendar days between the two dates (no time of day, no time zone).
  const todayKey = today.toISOString().slice(0, 10);
  const elapsed = Math.round((Date.parse(todayKey) - Date.parse(base.snapshot_date)) / 86_400_000);
  if (elapsed <= 0) return null;
  return { value: (currentValue - flows) / base.market_value - 1, days: elapsed };
}

export function belowBand(allocations: ClassAllocationDTO[]): ClassAllocationDTO[] {
  return allocations
    .filter((a) => a.band_status === "BELOW")
    .sort((a, b) => a.current_pct - a.target_pct - (b.current_pct - b.target_pct));
}

export function headline(
  report: PortfolioReportResponseDTO,
  change: Change | null,
  alerts: AlertDTO[],
): string[] {
  const holds = report.positions.some((p) => p.quantity > 0 || p.current_value_brl > 0);
  if (!holds) {
    return ["Sua carteira ainda está vazia: cadastre ativos ou importe o extrato da B3 em Lançamentos."];
  }
  const sentences: string[] = [];
  const value = brlCompact(report.total_current_value_brl);
  if (change && Math.abs(change.value) >= 0.0005) {
    sentences.push(
      `Patrimônio de ${value}, ${pct(change.value, 1, true)} em ${change.days} dias (sem contar aportes).`,
    );
  } else {
    sentences.push(`Patrimônio de ${value}.`);
  }
  const [worst] = belowBand(report.allocations);
  if (worst) {
    sentences.push(
      `${worst.label} está abaixo da banda: ${points(worst.current_pct)} contra meta de ${points(worst.target_pct, 0)}.`,
    );
  } else if (report.allocations.some((a) => a.band_status === "ABOVE")) {
    sentences.push("Nenhuma classe abaixo da banda; há classe acima, então segure os aportes nela.");
  } else {
    sentences.push("Todas as classes estão dentro das bandas.");
  }
  const urgent = alerts.filter((a) => a.severity !== "INFO").length;
  if (urgent > 0) sentences.push(urgent === 1 ? "Há 1 alerta pedindo atenção." : `Há ${urgent} alertas pedindo atenção.`);
  return sentences;
}

export interface AlignedCurves {
  labels: string[];
  series: Record<string, Array<number | null>>;
}

/** Base-100 curves on a shared date axis; dates a series lacks are gaps (null). */
export function alignCurves(
  curves: Record<string, Array<Record<string, unknown>>>,
  keys: string[],
): AlignedCurves {
  const present = keys.filter((k) => (curves[k]?.length ?? 0) >= 2);
  const byKey = Object.fromEntries(
    present.map((k) => [k, new Map(curves[k].map((p) => [String(p.date), Number(p.value)]))]),
  );
  const labels = [...new Set(present.flatMap((k) => curves[k].map((p) => String(p.date))))].sort();
  const series = Object.fromEntries(
    present.map((k) => [k, labels.map((d) => (byKey[k].has(d) ? (byKey[k].get(d) as number) : null))]),
  );
  return { labels, series };
}

/** Fractional return of a base-100 curve (last point). */
export function curveReturn(curve: Array<Record<string, unknown>> | undefined): number | null {
  if (!curve || curve.length < 2) return null;
  return Number(curve[curve.length - 1].value) / Number(curve[0].value) - 1;
}

/** The last `count` months of an earnings map, oldest first, filling missing months. */
export function lastMonths(earnings: Record<string, number>, count = 12, today = new Date()): Array<[string, number]> {
  const months: Array<[string, number]> = [];
  for (let i = count - 1; i >= 0; i -= 1) {
    const date = new Date(today.getFullYear(), today.getMonth() - i, 1);
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    months.push([key, earnings[key] ?? 0]);
  }
  return months;
}
