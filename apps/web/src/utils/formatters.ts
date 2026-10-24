/** Formatting utilities and standardized client-side pagination/sorting engine. */

import type { ArcaClass, AssetType, EarningKind, PaginatedResponse } from "../types/api";

export const ARCA_CLASS_LABELS: Record<ArcaClass, string> = {
  ACOES: "Ações Brasil",
  REAL_ESTATE: "Real Estate (FIIs/REITs)",
  CAIXA: "Caixa & Renda Fixa",
  ATIVOS_INTERNACIONAIS: "Ativos Internacionais",
};

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  STOCK_BR: "Ação B3",
  ETF_BR: "ETF B3",
  FII: "Fundo Imobiliário (FII)",
  BDR: "BDR",
  STOCK_INTL: "Stock (EUA)",
  ETF_INTL: "ETF Internacional",
  REIT: "REIT (EUA)",
  CRYPTO: "Criptoativo",
  FIXED_INCOME: "Renda Fixa Privada",
  TREASURY: "Tesouro Direto",
  CASH: "Caixa / Liquidez Diária",
};

export const EARNING_KIND_LABELS: Record<EarningKind, string> = {
  DIVIDEND: "Dividendo",
  JCP: "JCP",
  FII_YIELD: "Rendimento FII",
  FIXED_INCOME_COUPON: "Cupom Renda Fixa",
  RESTITUTION: "Restituição de Capital",
};

export function formatCurrencyBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value || 0);
}

export function formatPercent(value: number, decimals = 2, showSign = false): string {
  const num = Number.isFinite(value) ? value : 0;
  const sign = showSign && num > 0 ? "+" : "";
  return `${sign}${num.toFixed(decimals).replace(".", ",")}%`;
}

export function formatQuantity(value: number): string {
  if (Number.isInteger(value)) {
    return value.toLocaleString("pt-BR");
  }
  return value.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

export interface TableQueryState {
  page: number;
  pageSize: number;
  sortBy: string;
  sortOrder: "asc" | "desc";
  search: string;
  filters: Record<string, string>;
}

/**
 * Standardized pagination, sorting, and filtering helper so that both client-side
 * and server-backed tables share identical behavior and metadata.
 */
export function paginateAndSortItems<T extends Record<string, unknown>>(
  items: T[],
  query: TableQueryState,
  searchableKeys: (keyof T)[] = [],
): PaginatedResponse<T> {
  const normalizedSearch = query.search.trim().toLowerCase();

  const filtered = items.filter((item) => {
    for (const [filterKey, filterVal] of Object.entries(query.filters)) {
      if (!filterVal || filterVal === "ALL") continue;
      if (String(item[filterKey] ?? "") !== filterVal) {
        return false;
      }
    }
    if (!normalizedSearch || searchableKeys.length === 0) {
      return true;
    }
    return searchableKeys.some((k) =>
      String(item[k] ?? "")
        .toLowerCase()
        .includes(normalizedSearch),
    );
  });

  const sorted = [...filtered].sort((a, b) => {
    const valA = a[query.sortBy];
    const valB = b[query.sortBy];
    let cmp = 0;
    if (typeof valA === "number" && typeof valB === "number") {
      cmp = valA - valB;
    } else {
      cmp = String(valA ?? "").localeCompare(String(valB ?? ""), "pt-BR", {
        numeric: true,
      });
    }
    return query.sortOrder === "desc" ? -cmp : cmp;
  });

  const totalItems = sorted.length;
  const pageSize = Math.max(1, query.pageSize);
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(Math.max(1, query.page), totalPages);
  const start = (safePage - 1) * pageSize;
  const pageItems = sorted.slice(start, start + pageSize);

  return {
    items: pageItems,
    meta: {
      page: safePage,
      page_size: pageSize,
      total_items: totalItems,
      total_pages: totalPages,
      has_prev: safePage > 1,
      has_next: safePage < totalPages,
      sort_by: query.sortBy,
      sort_order: query.sortOrder,
    },
  };
}
