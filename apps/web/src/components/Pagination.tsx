import type { ReactNode } from "react";

import { pageCount, PAGE_SIZE_OPTIONS } from "../utils/pagination";
import { Combobox, codeOptions } from "./Combobox";

export interface PaginationProps {
  /** Current page, zero-based. */
  page: number;
  /** Rows per page. */
  pageSize: number;
  /** How many rows exist in total, not on this page. */
  total: number;
  onChange: (page: number) => void;
  /** Runs the same search again. Required: every paged table offers to reload. */
  onRefresh: () => void;
  /** While reloading: the button spins and is disabled. */
  refreshing?: boolean;
  /** Without it the size selector is hidden and the table keeps the caller's size. */
  onPageSizeChange?: (pageSize: number) => void;
  pageSizeOptions?: number[];
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 8a5 5 0 1 1-1.5-3.55" />
        <path d="M13 2.5v3h-3" />
      </g>
    </svg>
  );
}

function Chevron({ direction, double }: Readonly<{ direction: "left" | "right"; double?: boolean }>) {
  // One path, mirrored by a transform: "‹" and "›" are the same drawing.
  const flip = direction === "right" ? "scale(-1 1) translate(-16 0)" : undefined;
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
      <g transform={flip} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d={double ? "M9.5 3.5 5 8l4.5 4.5" : "M10 3.5 5.5 8l4.5 4.5"} />
        {double && <path d="M13.5 3.5 9 8l4.5 4.5" />}
      </g>
    </svg>
  );
}

const STEP_LABELS = {
  first: "Primeira página",
  previous: "Página anterior",
  next: "Próxima página",
  last: "Última página",
} as const;

/**
 * Navigation between the pages of a table. It shows ALWAYS, even with a single page: the
 * page-size choice lives there, and a bar that hides when the rows are few hides exactly the
 * control that changes how many appear.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onChange,
  onRefresh,
  refreshing = false,
  onPageSizeChange,
  pageSizeOptions = PAGE_SIZE_OPTIONS,
}: Readonly<PaginationProps>) {
  const first = page * pageSize;
  const last = Math.min(first + pageSize, total);
  const pages = pageCount(total, pageSize);
  const lastPage = pages - 1;

  // A size from outside the catalog still has to show as selected, or the select shows a
  // number that is not the one in effect.
  const options = pageSizeOptions.includes(pageSize)
    ? pageSizeOptions
    : [...pageSizeOptions, pageSize].sort((a, b) => a - b);

  const steps: { key: keyof typeof STEP_LABELS; to: number; icon: ReactNode; disabled: boolean }[] = [
    { key: "first", to: 0, icon: <Chevron direction="left" double />, disabled: page === 0 },
    { key: "previous", to: page - 1, icon: <Chevron direction="left" />, disabled: page === 0 },
    { key: "next", to: page + 1, icon: <Chevron direction="right" />, disabled: page >= lastPage },
    { key: "last", to: lastPage, icon: <Chevron direction="right" double />, disabled: page >= lastPage },
  ];
  const stepButton = (step: (typeof steps)[number]) => (
    <button
      key={step.key}
      type="button"
      className="app-pagination-icon"
      aria-label={STEP_LABELS[step.key]}
      title={STEP_LABELS[step.key]}
      disabled={step.disabled}
      onClick={() => onChange(step.to)}
    >
      {step.icon}
    </button>
  );

  return (
    <nav className="app-pagination" aria-label="Paginação">
      {onPageSizeChange && (
        <label className="app-pagination-size">
          Itens por página
          <Combobox value={pageSize} onChange={onPageSizeChange} options={codeOptions(options)} />
        </label>
      )}

      <span className="app-pagination-summary">
        <button
          type="button"
          className={["app-pagination-icon", refreshing && "app-pagination-refreshing"].filter(Boolean).join(" ")}
          aria-label="Recarregar"
          title="Recarregar"
          disabled={refreshing}
          onClick={onRefresh}
        >
          <RefreshIcon />
        </button>
        <span className="app-pagination-range" aria-live="polite">
          {total === 0 ? "Nenhum registro" : `${first + 1}–${last} de ${total}`}
        </span>
      </span>

      <span className="app-pagination-buttons">
        {steps.slice(0, 2).map(stepButton)}
        <span className="app-pagination-page">
          Página {page + 1} de {pages}
        </span>
        {steps.slice(2).map(stepButton)}
      </span>
    </nav>
  );
}
