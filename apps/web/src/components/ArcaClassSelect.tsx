import type { ArcaClass } from "../api/types";
import { ARCA_CLASSES, ARCA_LABELS } from "../utils/labels";

/** Picks an ARCA quadrant; the suggested one is marked so the user sees what was proposed. */
export function ArcaClassSelect({
  id,
  value,
  onChange,
  suggested,
  emptyLabel,
  disabled,
  label,
}: Readonly<{
  id?: string;
  value: ArcaClass | "";
  onChange: (value: ArcaClass | "") => void;
  suggested?: ArcaClass | null;
  /** When set, an empty option with this text is offered (e.g. "use the suggestion"). */
  emptyLabel?: string;
  disabled?: boolean;
  /** Accessible name when there is no visible <label for>. */
  label?: string;
}>) {
  return (
    <select
      id={id}
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as ArcaClass | "")}
    >
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {ARCA_CLASSES.map((arca) => (
        <option key={arca} value={arca}>
          {ARCA_LABELS[arca]}
          {arca === suggested ? " (sugerida)" : ""}
        </option>
      ))}
    </select>
  );
}
