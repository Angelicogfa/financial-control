/** Global search (Phase 48.R3): Ctrl+K or "/" on any screen finds a ticker, a name, a Tesouro
 *  bond or an action ("aportar", "importar extrato"), and opens it with Enter. */

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { SearchHitDTO } from "../../api/types";
import { SearchIcon } from "../../layout/icons";
import { DESTINATIONS, SETTINGS } from "../../layout/navigation";
import { instrumentPath } from "../instrument/paths";
import { money } from "../../utils/format";

export const SEARCH_DEBOUNCE_MS = 200;
const RESULT_LIMIT = 8;

export interface QuickAction {
  label: string;
  to: string;
  keywords: string;
}

const ALL_ACTIONS: QuickAction[] = [
  { label: "Aportar", to: "/aportar", keywords: "aporte aplicar investir dinheiro" },
  { label: "Importar extrato B3", to: "/lancamentos/importar", keywords: "importar extrato b3 planilha" },
  { label: "Nova compra ou venda", to: "/lancamentos/negociacoes/nova", keywords: "nova compra venda negociacao" },
  { label: "Novo provento", to: "/lancamentos/proventos/novo", keywords: "novo provento dividendo jcp" },
  { label: "Novo ativo", to: "/carteira/novo-ativo", keywords: "novo ativo cadastrar caixa renda fixa" },
  ...DESTINATIONS.map((d) => ({ label: d.label, to: d.to, keywords: d.question })),
  ...DESTINATIONS.flatMap((d) => d.sections.filter((s) => s.to !== d.to).map((s) => ({ label: `${d.label} › ${s.label}`, to: s.to, keywords: "" }))),
  ...SETTINGS.items.map((i) => ({ label: `Configurações › ${i.label}`, to: i.to, keywords: "configuracoes" })),
];

/** One option per address: a quick action wins over the destination it opens. */
export const QUICK_ACTIONS: QuickAction[] = ALL_ACTIONS.filter(
  (action, index) => ALL_ACTIONS.findIndex((other) => other.to === action.to) === index,
);

function fold(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export function matchActions(query: string, limit = 4): QuickAction[] {
  const q = fold(query);
  if (!q) return [];
  return QUICK_ACTIONS.filter((a) => fold(`${a.label} ${a.keywords}`).split(/\s+/).some((w) => w.startsWith(q)) || fold(a.label).includes(q)).slice(0, limit);
}

export function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

type Option = { kind: "action"; action: QuickAction } | { kind: "hit"; hit: SearchHitDTO };

function optionTo(option: Option): string {
  return option.kind === "action" ? option.action.to : instrumentPath(option.hit.key);
}

/** The topbar button plus the dialog; the shortcut works on every screen. */
export function GlobalSearch() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const shortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
      if (shortcut || (event.key === "/" && !typing(event.target))) {
        event.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <button type="button" className="app-search-trigger" onClick={() => setOpen(true)} aria-keyshortcuts="Control+K /">
        <SearchIcon width={15} height={15} />
        <span>Buscar ativo ou ação</span>
        <kbd aria-hidden="true">Ctrl K</kbd>
      </button>
      {open && <SearchDialog onClose={() => setOpen(false)} />}
    </>
  );
}

export function SearchDialog({ onClose }: Readonly<{ onClose: () => void }>) {
  const navigate = useNavigate();
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const query = useDebounced(text.trim(), SEARCH_DEBOUNCE_MS);

  useEffect(() => input.current?.focus(), []);

  const results = useQuery({
    queryKey: ["search", query],
    queryFn: ({ signal }) => api.search(query, RESULT_LIMIT, signal),
    enabled: query.length > 0,
    staleTime: 30_000,
  });

  const options: Option[] = useMemo(() => {
    const actions = matchActions(text).map((action) => ({ kind: "action" as const, action }));
    const hits = query && results.data ? results.data.hits.map((hit) => ({ kind: "hit" as const, hit })) : [];
    return [...hits, ...actions];
  }, [text, query, results.data]);

  useEffect(() => setActive(0), [options.length, query]);

  const choose = useCallback(
    (option: Option | undefined) => {
      if (!option) return;
      onClose();
      navigate(optionTo(option));
    },
    [navigate, onClose],
  );

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => (options.length ? (i + 1) % options.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (options.length ? (i - 1 + options.length) % options.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(options[active]);
    }
  };

  const searching = query.length > 0 && results.isFetching;
  const nothing = query.length > 0 && !results.isFetching && options.length === 0;

  return (
    <div className="app-search-backdrop" onMouseDown={onClose}>
      <div
        className="app-search-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Busca global"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="app-search-field">
          <SearchIcon width={16} height={16} />
          <input
            ref={input}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Ticker, nome, título do Tesouro ou ação"
            aria-label="Buscar ativo ou ação"
            role="combobox"
            aria-expanded={options.length > 0}
            aria-controls={listId}
            aria-activedescendant={options.length ? `${listId}-${active}` : undefined}
            autoComplete="off"
          />
        </div>
        <ul id={listId} role="listbox" aria-label="Resultados" className="app-search-results">
          {options.map((option, index) => (
            <li
              key={optionTo(option)}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? "is-active" : undefined}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(option)}
            >
              {option.kind === "hit" ? (
                <>
                  <strong>{option.hit.ticker}</strong>
                  <span>{option.hit.name}</span>
                  <span className="app-search-meta">
                    {option.hit.holds_position ? "Na carteira" : option.hit.tracked_asset_id ? "Acompanhando" : ""}
                    {option.hit.close ? ` ${money(option.hit.close)}` : ""}
                  </span>
                </>
              ) : (
                <>
                  <strong>{option.action.label}</strong>
                  <span className="app-search-meta">Ir para</span>
                </>
              )}
            </li>
          ))}
        </ul>
        {searching && <p className="app-search-status" role="status">Buscando…</p>}
        {nothing && <p className="app-search-status">Nada encontrado para “{query}”.</p>}
        {results.isError && <p className="app-search-status" role="alert">A busca falhou; tente de novo.</p>}
      </div>
    </div>
  );
}
