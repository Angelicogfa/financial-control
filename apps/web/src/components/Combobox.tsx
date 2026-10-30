import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";

import { ChevronDownIcon } from "../layout/icons";

export type ComboboxValue = string | number;

export interface ComboboxOption<T extends ComboboxValue> {
  value: T;
  label: string;
}

/** Options for a list of codes, each shown by its label (codes without a label show as themselves). */
export function codeOptions<T extends ComboboxValue>(
  codes: readonly T[],
  labels?: Partial<Record<T, string>>,
): ComboboxOption<T>[] {
  return codes.map((code) => ({ value: code, label: labels?.[code] ?? String(code) }));
}

/** Most options drawn at once; typing narrows the rest, so long catalogs stay responsive. */
export const MAX_RENDERED_OPTIONS = 100;

/** Lowercase without accents, so "acao" finds "Ação" and "itub" finds "ITUB4". */
export function normalizeSearch(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/** Options whose label holds every typed word, in any order ("teva ipca" finds "… TEVA … IPCA …"). */
export function filterOptions<T extends ComboboxValue>(options: ComboboxOption<T>[], query: string): ComboboxOption<T>[] {
  const words = normalizeSearch(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return options;
  return options.filter((option) => {
    const label = normalizeSearch(option.label);
    return words.every((word) => label.includes(word));
  });
}

/**
 * The option a typed text settles on when the field loses focus: the one whose label it
 * spells out, or the only one left by the filter; an empty text settles on the empty-value
 * option when there is one. Anything else settles on nothing, and the field goes back to
 * the current choice: a value outside the list is never accepted.
 */
export function resolveTyped<T extends ComboboxValue>(
  options: ComboboxOption<T>[],
  query: string,
): ComboboxOption<T> | null {
  const typed = normalizeSearch(query);
  if (typed === "") return options.find((o) => o.value === "") ?? null;
  const exact = options.find((o) => normalizeSearch(o.label) === typed);
  if (exact) return exact;
  const matches = filterOptions(options, query);
  return matches.length === 1 ? matches[0] : null;
}

/** Fixed-position style that keeps the list under (or above) the field, even inside scrolled tables. */
function panelPosition(anchor: HTMLElement): CSSProperties {
  const rect = anchor.getBoundingClientRect();
  const below = window.innerHeight - rect.bottom;
  const above = rect.top;
  const openUp = below < 220 && above > below;
  const room = Math.max(120, (openUp ? above : below) - 12);
  return {
    position: "fixed",
    left: rect.left,
    minWidth: rect.width,
    maxWidth: Math.max(rect.width, window.innerWidth - rect.left - 8),
    maxHeight: Math.min(320, room),
    ...(openUp ? { bottom: window.innerHeight - rect.top + 4 } : { top: rect.bottom + 4 }),
  };
}

/**
 * Select-like field that filters its options as the user types and only ever takes one of
 * them. Pair it with `<label htmlFor={id}>` (or pass `label`). An option whose value is ""
 * is the empty choice: the field then shows its label as the placeholder, and clearing the
 * text picks it. Arrows move through the list, Enter picks, Escape gives up the typing.
 */
export function Combobox<T extends ComboboxValue>({
  id,
  value,
  options,
  onChange,
  disabled = false,
  required = false,
  label,
  placeholder,
  loading = false,
  className,
}: Readonly<{
  id?: string;
  value: T;
  options: ComboboxOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  required?: boolean;
  /** Accessible name when there is no visible <label for>. */
  label?: string;
  /** Text shown while nothing is chosen; defaults to the empty option's label. */
  placeholder?: string;
  /** Shows "Carregando…" while the options are still on their way. */
  loading?: boolean;
  className?: string;
}>) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  /** What the user typed; null while the field just shows the current choice. */
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [panelStyle, setPanelStyle] = useState<CSSProperties>({});

  const selected = options.find((o) => o.value === value) ?? null;
  const emptyOption = options.find((o) => o.value === "");
  const shownLabel = selected && selected.value !== "" ? selected.label : "";
  const matches = query === null ? options : filterOptions(options, query);
  const visible = matches.slice(0, MAX_RENDERED_OPTIONS);
  const longest = options.reduce((size, o) => Math.max(size, o.label.length), (placeholder ?? "").length);

  const close = useCallback(() => {
    setOpen(false);
    setQuery(null);
  }, []);

  const openList = () => {
    if (disabled) return;
    const index = options.findIndex((o) => o.value === value);
    setActive(Math.max(0, Math.min(index, MAX_RENDERED_OPTIONS - 1)));
    setOpen(true);
  };

  const commit = (option: ComboboxOption<T>) => {
    close();
    if (option.value !== value) onChange(option.value);
  };

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;
    const anchor = rootRef.current;
    const place = () => setPanelStyle(panelPosition(anchor));
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const item = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    item?.scrollIntoView?.({ block: "nearest" });
  }, [open, active]);

  const onBlur = () => {
    if (query !== null) {
      const typed = resolveTyped(options, query);
      if (typed) {
        commit(typed);
        return;
      }
    }
    close();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openList();
        else setActive((i) => Math.min(i + 1, visible.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        if (open) setActive((i) => Math.max(i - 1, 0));
        break;
      case "Home":
      case "End":
        if (!open) break;
        e.preventDefault();
        setActive(e.key === "Home" ? 0 : visible.length - 1);
        break;
      case "Enter":
        if (!open) break;
        // An open list owns Enter: it picks the highlighted option and never submits the form.
        e.preventDefault();
        if (visible[active]) commit(visible[active]);
        break;
      case "Escape":
        if (!open && query === null) break;
        e.preventDefault();
        e.stopPropagation();
        close();
        break;
    }
  };

  const activeOption = open ? visible[active] : undefined;
  const optionId = (index: number) => `${listId}-option-${index}`;

  return (
    <div className={["app-combobox", className].filter(Boolean).join(" ")} ref={rootRef}>
      <input
        ref={inputRef}
        id={id}
        type="text"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeOption ? optionId(active) : undefined}
        autoComplete="off"
        spellCheck={false}
        size={Math.min(Math.max(longest, 4), 40) + 2}
        value={query ?? shownLabel}
        placeholder={loading ? "Carregando…" : placeholder ?? emptyOption?.label}
        disabled={disabled}
        required={required}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onClick={() => (open ? undefined : openList())}
        onKeyDown={onKeyDown}
        onBlur={onBlur}
      />
      <span
        className="app-combobox-chevron"
        aria-hidden="true"
        onMouseDown={(e) => {
          // Keeps the focus in the field: the chevron only toggles the list.
          e.preventDefault();
          if (disabled) return;
          inputRef.current?.focus();
          if (open) close();
          else openList();
        }}
        // Inside a wrapping <label>, a click would also reach the field and reopen the list.
        onClick={(e) => e.preventDefault()}
      >
        <ChevronDownIcon width={16} height={16} />
      </span>
      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          className="app-combobox-panel"
          style={panelStyle}
          // A click on the list must not blur the field before the option is picked.
          onMouseDown={(e) => e.preventDefault()}
          // Same for a wrapping <label>: picking an option must not click the field again.
          onClick={(e) => e.preventDefault()}
        >
          {visible.map((option, index) => (
            <li
              key={String(option.value)}
              id={optionId(index)}
              data-index={index}
              role="option"
              aria-selected={option.value === value}
              className={index === active ? "app-combobox-option is-active" : "app-combobox-option"}
              onMouseEnter={() => setActive(index)}
              onClick={() => commit(option)}
            >
              {option.label}
            </li>
          ))}
          {matches.length === 0 && <li className="app-combobox-empty">{loading ? "Carregando…" : "Nenhuma opção encontrada"}</li>}
          {matches.length > visible.length && (
            <li className="app-combobox-empty">
              Mostrando {visible.length} de {matches.length}. Digite para refinar.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
