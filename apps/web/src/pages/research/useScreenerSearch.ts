import { useRef, useState } from "react";

import { api, type ScreenerFilters } from "../../api/endpoints";
import type { ScreenerResponseDTO } from "../../api/types";
import { clampPage, DEFAULT_PAGE_SIZE } from "../../utils/pagination";

export interface ScreenerSearch {
  result: ScreenerResponseDTO | null;
  error: unknown;
  loading: boolean;
  /** A new search: starts on the first page. */
  search: (filters: ScreenerFilters) => Promise<void>;
  /** The same search and page again (after following an asset, or on "Recarregar"). */
  refresh: () => Promise<void>;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    onChange: (page: number) => void;
    onPageSizeChange: (pageSize: number) => void;
  };
}

/**
 * A screener search paged by the API: each page asks for its own rows, so every match of the
 * catalog can be reached, not only the first API page.
 */
export function useScreenerSearch(): ScreenerSearch {
  const [result, setResult] = useState<ScreenerResponseDTO | null>(null);
  const [filters, setFilters] = useState<ScreenerFilters | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  // Only the latest request shows: a slow page must not replace the one clicked after it.
  const latest = useRef(0);

  const load = async (next: ScreenerFilters, nextPage: number, size: number) => {
    const request = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      let target = nextPage;
      let reply = await api.research.screener({ ...next, page: target + 1, limit: size });
      const total = reply.total ?? reply.results.length;
      // A page emptied since the last load (an asset followed and hidden) moves back.
      if (reply.results.length === 0 && total > 0 && target > 0) {
        target = clampPage(target, total, size);
        reply = await api.research.screener({ ...next, page: target + 1, limit: size });
      }
      if (request !== latest.current) return;
      setResult(reply);
      setFilters(next);
      setPage(target);
      setPageSize(size);
    } catch (err) {
      if (request === latest.current) setError(err);
    } finally {
      if (request === latest.current) setLoading(false);
    }
  };

  return {
    result,
    error,
    loading,
    search: (next) => load(next, 0, pageSize),
    refresh: async () => {
      if (filters) await load(filters, page, pageSize);
    },
    pagination: {
      page,
      pageSize,
      total: result ? (result.total ?? result.results.length) : 0,
      onChange: (next) => {
        if (filters) void load(filters, next, pageSize);
      },
      onPageSizeChange: (size) => {
        if (filters) void load(filters, 0, size);
      },
    },
  };
}
