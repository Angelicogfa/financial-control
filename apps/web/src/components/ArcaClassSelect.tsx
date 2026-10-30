import type { ArcaClass } from "../api/types";
import { Combobox } from "./Combobox";
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
    <Combobox<ArcaClass | "">
      id={id}
      label={label}
      value={value}
      disabled={disabled}
      onChange={onChange}
      options={[
        ...(emptyLabel === undefined ? [] : [{ value: "" as const, label: emptyLabel }]),
        ...ARCA_CLASSES.map((arca) => ({
          value: arca,
          label: `${ARCA_LABELS[arca]}${arca === suggested ? " (sugerida)" : ""}`,
        })),
      ]}
    />
  );
}
