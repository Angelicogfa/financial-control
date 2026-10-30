/** Number, money and date formatting (pt-BR). Fractions follow ADR 0006: 0.12 = 12%. */

const brlFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const compactFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

function finite(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const number = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(number) ? number : null;
}

export function brl(value: number | string | null | undefined): string {
  const number = finite(value);
  return number === null ? "—" : brlFormatter.format(number);
}

/** R$ 56,3 mil — for headlines and indicators. */
export function brlCompact(value: number | null | undefined): string {
  const number = finite(value);
  return number === null ? "—" : compactFormatter.format(number);
}

export function money(value: number | string | null | undefined, currency = "BRL"): string {
  const number = finite(value);
  if (number === null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(number);
}

/** A fraction as a percentage: 0.1234 -> "12,3%". */
export function pct(fraction: number | null | undefined, digits = 1, signed = false): string {
  const number = finite(fraction);
  if (number === null) return "—";
  return points(number * 100, digits, signed);
}

/** A value already in percentage points: 12.34 -> "12,3%". */
export function points(value: number | null | undefined, digits = 1, signed = false): string {
  const number = finite(value);
  if (number === null) return "—";
  const sign = signed && number > 0 ? "+" : "";
  return `${sign}${number.toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

export function num(value: number | string | null | undefined, digits = 2): string {
  const number = finite(value);
  if (number === null) return "—";
  return number.toLocaleString("pt-BR", { maximumFractionDigits: digits });
}

/** "1 modelo passou" / "3 modelos passaram": the count with the right noun, never "modelo(s)". */
export function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString("pt-BR")} ${count === 1 ? one : many}`;
}

export function quantity(value: number | string | null | undefined): string {
  const number = finite(value);
  if (number === null) return "—";
  return number.toLocaleString("pt-BR", { maximumFractionDigits: 8 });
}

/** "2026-03-01" -> "01/03/2026" (date-only strings are not shifted by the time zone). */
export function day(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : value;
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** "2026-03" -> "mar/26" */
export function monthLabel(key: string): string {
  const [y, m] = key.split("-");
  const names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const index = Number(m) - 1;
  return names[index] ? `${names[index]}/${y.slice(2)}` : key;
}

export function today(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

/** Parse a number typed with a Brazilian comma ("1.234,56" or "12,5"). */
export function parseDecimal(text: string): number | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  // "1.200.000" (two or more groups of three) is thousands; a single dot stays a decimal point.
  const thousands = /^-?\d{1,3}(\.\d{3}){2,}$/.test(trimmed);
  const normalized =
    trimmed.includes(",") || thousands ? trimmed.replace(/\./g, "").replace(",", ".") : trimmed;
  const number = Number(normalized);
  return Number.isFinite(number) ? number : null;
}
