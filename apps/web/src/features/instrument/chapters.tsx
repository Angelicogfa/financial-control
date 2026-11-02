/** The asset page as a story in chapters (Phase 48.R4, REFACTORING_PLAN §3.3).
 *
 *  Each chapter opens with its conclusion in one sentence; "Ver detalhes" mounts the table that
 *  used to be a whole tab, so the page loads only what the reader opens. */

import { useEffect, useId, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import type { InstrumentLensesDTO } from "../../api/types";
import { pct } from "../../utils/format";

export type ChapterKey =
  | "resumo"
  | "carteira"
  | "preco"
  | "checklist"
  | "valuation"
  | "resultados"
  | "proventos"
  | "previsao"
  | "noticias"
  | "imposto";

export const CHAPTER_TITLES: Record<ChapterKey, string> = {
  resumo: "Em resumo",
  carteira: "Na minha carteira",
  preco: "Preço",
  checklist: "Vale a pena?",
  valuation: "Está barato?",
  resultados: "Resultados",
  proventos: "Proventos",
  previsao: "O que pode acontecer",
  noticias: "Notícias e eventos",
  imposto: "Imposto e lançamentos",
};

/** `?tab=` of the old asset page (links, bookmarks, agent answers) -> the chapter it became. */
const TAB_TO_CHAPTER: Record<string, ChapterKey> = {
  summary: "preco",
  market: "preco",
  fundamentals: "resultados",
  valuation: "valuation",
  forecast: "previsao",
  checklist: "checklist",
  tax: "imposto",
  earnings: "proventos",
  ledger: "imposto",
  disclosures: "noticias",
};

export function chapterFromQuery(params: URLSearchParams): ChapterKey | null {
  const named = params.get("capitulo");
  if (named && named in CHAPTER_TITLES) return named as ChapterKey;
  const tab = params.get("tab");
  return tab ? (TAB_TO_CHAPTER[tab] ?? null) : null;
}

/** Chapters open by default plus the one the address asks for (scrolled into view). */
export function useOpenChapters(defaults: ChapterKey[]) {
  const [params] = useSearchParams();
  const asked = chapterFromQuery(params);
  const [open, setOpen] = useState<Set<ChapterKey>>(() => new Set(asked ? [...defaults, asked] : defaults));
  useEffect(() => {
    if (!asked) return;
    const element = document.getElementById(`capitulo-${asked}`);
    if (element && typeof element.scrollIntoView === "function") element.scrollIntoView({ block: "start" });
  }, [asked]);
  const toggle = (key: ChapterKey) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return { isOpen: (key: ChapterKey) => open.has(key), toggle };
}

export function Chapter({
  id,
  title,
  lead,
  open,
  onToggle,
  children,
}: Readonly<{
  id: ChapterKey;
  /** The question of the chapter; the lead answers it. */
  title?: string;
  lead?: ReactNode;
  /** Without `onToggle` the content is always shown. */
  open?: boolean;
  onToggle?: () => void;
  children?: ReactNode;
}>) {
  const headingId = useId();
  const bodyId = useId();
  const heading = title ?? CHAPTER_TITLES[id];
  const collapsible = onToggle !== undefined;
  const showing = !collapsible || open;
  return (
    <section id={`capitulo-${id}`} className="app-chapter" aria-labelledby={headingId}>
      <div className="app-chapter-head">
        <h2 id={headingId} className="app-chapter-title">
          {heading}
        </h2>
        {collapsible && children && (
          <button
            type="button"
            className="app-secondary-button app-chapter-toggle"
            aria-expanded={open}
            aria-controls={bodyId}
            aria-label={`${open ? "Ocultar" : "Ver"} detalhes: ${heading}`}
            onClick={onToggle}
          >
            {open ? "Ocultar detalhes" : "Ver detalhes"}
          </button>
        )}
      </div>
      {lead && <div className="app-chapter-lead">{lead}</div>}
      {showing && children && (
        <div id={bodyId} className="app-chapter-body">
          {children}
        </div>
      )}
    </section>
  );
}

export function ChapterIndex({ chapters }: Readonly<{ chapters: Array<{ key: ChapterKey; title?: string }> }>) {
  return (
    <nav className="app-chapter-index" aria-label="Capítulos">
      <ol>
        {chapters.map((c) => (
          <li key={c.key}>
            <a href={`#capitulo-${c.key}`}>{c.title ?? CHAPTER_TITLES[c.key]}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export const LENS_LABELS: Record<string, string> = {
  CERRADO: "Cerrado",
  QUALITY: "Qualidade",
  VALUATION: "Valuation",
  IMPROVEMENT: "Melhora",
  MOMENTUM: "Momentum",
  INCOME: "Renda",
  RISK: "Risco",
  PROJECTION: "Projeção",
};

/** Strongest and weakest lens with data, for the two sentences of "Em resumo". */
export function lensHighlights(lenses: InstrumentLensesDTO | null | undefined): { strong?: string; weak?: string } {
  const scored = (lenses?.items ?? []).filter((l) => l.normalized !== null && l.normalized !== undefined);
  if (scored.length === 0) return {};
  const sorted = [...scored].sort((a, b) => (b.normalized ?? 0) - (a.normalized ?? 0));
  const label = (lens: string) => LENS_LABELS[lens] ?? lens;
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];
  return {
    strong: `Ponto forte: ${label(best.lens)} (${pct(best.normalized, 0)} da escala)${best.note ? ` — ${best.note}` : ""}.`,
    weak:
      sorted.length > 1
        ? `Ponto fraco: ${label(worst.lens)} (${pct(worst.normalized, 0)} da escala)${worst.note ? ` — ${worst.note}` : ""}.`
        : undefined,
  };
}

/** The "snowflake" of the project: one bar per lens, 0 to 100% of the scale. */
export function LensBars({ lenses }: Readonly<{ lenses: InstrumentLensesDTO }>) {
  return (
    <ul className="app-lens-bars" aria-label={`Lentes da recomendação em ${lenses.as_of}`}>
      {lenses.items.map((l) => (
        <li key={l.lens}>
          <span className="app-lens-name">{LENS_LABELS[l.lens] ?? l.lens}</span>
          <span className="app-lens-track" aria-hidden="true">
            <span className="app-lens-fill" style={{ width: `${Math.round((l.normalized ?? 0) * 100)}%` }} />
          </span>
          <span className="app-lens-value">
            {l.normalized === null || l.normalized === undefined ? "sem dado" : pct(l.normalized, 0)}
          </span>
        </li>
      ))}
    </ul>
  );
}
