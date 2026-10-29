import { useState } from "react";

/** Page sizes offered by every paged table. */
export const PAGE_SIZE_OPTIONS = [5, 10, 50, 100];

/** How many rows a table shows before the user chooses. */
export const DEFAULT_PAGE_SIZE = 10;

/** Number of pages for `total` rows; an empty list still has one page. */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

/** The last valid zero-based page for `total` rows. */
export function clampPage(page: number, total: number, pageSize: number): number {
  return Math.min(Math.max(0, page), pageCount(total, pageSize) - 1);
}

/** The rows of one page of a list already in memory (zero-based `page`, clamped). */
export function paginate<T>(items: readonly T[], page: number, pageSize: number): T[] {
  const start = clampPage(page, items.length, pageSize) * pageSize;
  return items.slice(start, start + pageSize);
}

export interface PaginationState {
  /** Current page, zero-based. */
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  /** Changing the size goes back to the first page: the old page may no longer exist. */
  setPageSize: (pageSize: number) => void;
}

/**
 * Page and page size of a table. `resetKey` names the search being paged (its filters): when
 * it changes, the table goes back to the first page.
 */
export function usePagination(resetKey = "", initialPageSize = DEFAULT_PAGE_SIZE): PaginationState {
  // The page belongs to the search it was chosen in: a new search starts on the first page
  // in the same render, without a request for a page of the old one.
  const [state, setState] = useState({ key: resetKey, page: 0 });
  const [pageSize, setSize] = useState(initialPageSize);
  const page = state.key === resetKey ? state.page : 0;

  const setPage = (next: number) => setState({ key: resetKey, page: next });
  const setPageSize = (size: number) => {
    setSize(size);
    setState({ key: resetKey, page: 0 });
  };
  return { page, pageSize, setPage, setPageSize };
}

/** One page of a list already in memory, with what the pagination bar needs to drive it. */
export interface PagedRows<T> {
  rows: T[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    onChange: (page: number) => void;
    onPageSizeChange: (pageSize: number) => void;
  };
}

/**
 * Pages a list the API returns whole (a search result, the watchlist). The page is clamped to
 * the list, so removing the last row of the last page shows the page before it.
 */
export function usePagedRows<T>(items: readonly T[], resetKey = ""): PagedRows<T> {
  const pager = usePagination(resetKey);
  const page = clampPage(pager.page, items.length, pager.pageSize);
  return {
    rows: paginate(items, page, pager.pageSize),
    pagination: {
      page,
      pageSize: pager.pageSize,
      total: items.length,
      onChange: pager.setPage,
      onPageSizeChange: pager.setPageSize,
    },
  };
}
