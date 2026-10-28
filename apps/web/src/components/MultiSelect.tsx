import { useEffect, useId, useRef, useState } from "react";

import { ChevronDownIcon } from "../layout/icons";

export interface MultiSelectOption<T extends string> {
  value: T;
  label: string;
}

/** Trigger text: the placeholder when nothing is picked, the labels while they fit, else a count. */
export function multiSelectSummary<T extends string>(
  options: MultiSelectOption<T>[],
  value: T[],
  placeholder: string,
): string {
  const picked = options.filter((o) => value.includes(o.value));
  if (picked.length === 0) return placeholder;
  if (picked.length <= 2) return picked.map((o) => o.label).join(", ");
  return `${picked.length} selecionados`;
}

/**
 * Select-like field that picks several options: the trigger opens a list of checkboxes.
 * Pair it with `<label htmlFor={id}>`; Escape or a click outside closes the list.
 */
export function MultiSelect<T extends string>({
  id,
  options,
  value,
  onChange,
  placeholder = "Todos",
  disabled = false,
}: Readonly<{
  id: string;
  options: MultiSelectOption<T>[];
  value: T[];
  onChange: (value: T[]) => void;
  placeholder?: string;
  disabled?: boolean;
}>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const toggle = (option: T) =>
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);

  return (
    <div className="app-multiselect" ref={rootRef}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className="app-multiselect-trigger"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={panelId}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        <span className={value.length === 0 ? "app-multiselect-placeholder" : undefined}>
          {multiSelectSummary(options, value, placeholder)}
        </span>
        <ChevronDownIcon width={16} height={16} />
      </button>
      {open && (
        <div id={panelId} className="app-multiselect-panel" role="group" aria-labelledby={id}>
          {options.map((option) => (
            <label key={option.value} className="app-check app-multiselect-option">
              <input type="checkbox" checked={value.includes(option.value)} onChange={() => toggle(option.value)} />
              {option.label}
            </label>
          ))}
          {value.length > 0 && (
            <button type="button" className="app-link-button app-multiselect-clear" onClick={() => onChange([])}>
              Limpar seleção
            </button>
          )}
        </div>
      )}
    </div>
  );
}
