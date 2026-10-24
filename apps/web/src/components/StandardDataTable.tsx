/** Standardized DataTable with search, dropdown filters, column sorting, and full pagination controls. */

import React, { useMemo, useState } from "react";
import { paginateAndSortItems } from "../utils/formatters";

export interface StandardColumn<T> {
  key: keyof T & string;
  header: string;
  sortable?: boolean;
  align?: "left" | "right" | "center";
  render?: (item: T) => React.ReactNode;
}

export interface StandardFilterOption {
  value: string;
  label: string;
}

export interface StandardFilterDef<T> {
  key: keyof T & string;
  label: string;
  options: StandardFilterOption[];
}

interface StandardDataTableProps<T extends Record<string, unknown>> {
  tableId: string;
  data: T[];
  columns: StandardColumn<T>[];
  searchableKeys?: (keyof T)[];
  searchPlaceholder?: string;
  filters?: StandardFilterDef<T>[];
  defaultSortBy: keyof T & string;
  defaultSortOrder?: "asc" | "desc";
  defaultPageSize?: number;
  rowKey: (item: T) => string | number;
  emptyMessage?: string;
}

export function StandardDataTable<T extends Record<string, unknown>>({
  tableId,
  data,
  columns,
  searchableKeys = [],
  searchPlaceholder = "Buscar por ticker ou nome...",
  filters = [],
  defaultSortBy,
  defaultSortOrder = "asc",
  defaultPageSize = 10,
  rowKey,
  emptyMessage = "Nenhum registro encontrado para os filtros aplicados.",
}: StandardDataTableProps<T>): React.ReactElement {
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(defaultPageSize);
  const [sortBy, setSortBy] = useState<string>(defaultSortBy);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">(defaultSortOrder);
  const [search, setSearch] = useState<string>("");
  const [activeFilters, setActiveFilters] = useState<Record<string, string>>({});

  const paginated = useMemo(
    () =>
      paginateAndSortItems(
        data,
        {
          page,
          pageSize,
          sortBy,
          sortOrder,
          search,
          filters: activeFilters,
        },
        searchableKeys,
      ),
    [data, page, pageSize, sortBy, sortOrder, search, activeFilters, searchableKeys],
  );

  const handleSortClick = (colKey: string) => {
    if (sortBy === colKey) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(colKey);
      setSortOrder("asc");
    }
    setPage(1);
  };

  const handleFilterChange = (key: string, val: string) => {
    setActiveFilters((prev) => ({ ...prev, [key]: val }));
    setPage(1);
  };

  const handleClearFilters = () => {
    setSearch("");
    setActiveFilters({});
    setPage(1);
  };

  const { meta, items } = paginated;
  const startItem = meta.total_items === 0 ? 0 : (meta.page - 1) * meta.page_size + 1;
  const endItem = Math.min(meta.page * meta.page_size, meta.total_items);

  const pageNumbers = useMemo(() => {
    const pages: number[] = [];
    for (let i = 1; i <= meta.total_pages; i += 1) {
      pages.push(i);
    }
    return pages;
  }, [meta.total_pages]);

  return (
    <div className="std-table-wrapper" data-testid={`table-${tableId}`}>
      <div className="std-table-toolbar">
        <div className="std-toolbar-filters">
          <input
            type="search"
            className="std-input"
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />

          {filters.map((f) => (
            <select
              key={f.key}
              className="std-select"
              aria-label={f.label}
              value={activeFilters[f.key] ?? "ALL"}
              onChange={(e) => handleFilterChange(f.key, e.target.value)}
            >
              <option value="ALL">{f.label}: Todos</option>
              {f.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ))}

          {(search || Object.values(activeFilters).some((v) => v && v !== "ALL")) && (
            <button
              type="button"
              className="btn btn-outline"
              onClick={handleClearFilters}
            >
              Limpar filtros
            </button>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <label
            htmlFor={`${tableId}-page-size`}
            style={{ fontSize: "0.78rem", color: "#475569", fontWeight: 600 }}
          >
            Itens por página:
          </label>
          <select
            id={`${tableId}-page-size`}
            className="std-select"
            aria-label="Itens por página"
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
          >
            <option value={5}>5 / pág</option>
            <option value={10}>10 / pág</option>
            <option value={25}>25 / pág</option>
            <option value={50}>50 / pág</option>
            <option value={100}>100 / pág</option>
          </select>
        </div>
      </div>

      <div className="std-table-scroll">
        <table className="std-table">
          <thead>
            <tr>
              {columns.map((col) => {
                const isSorted = sortBy === col.key;
                const arrow = isSorted ? (sortOrder === "asc" ? " ▲" : " ▼") : " ↕";
                return (
                  <th
                    key={col.key}
                    className={col.sortable ? "sortable" : ""}
                    style={{ textAlign: col.align ?? "left" }}
                    onClick={col.sortable ? () => handleSortClick(col.key) : undefined}
                  >
                    {col.header}
                    {col.sortable && <span aria-hidden="true">{arrow}</span>}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  style={{ textAlign: "center", padding: "28px", color: "#64748b" }}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={rowKey(item)}>
                  {columns.map((col) => (
                    <td key={col.key} style={{ textAlign: col.align ?? "left" }}>
                      {col.render ? col.render(item) : String(item[col.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="std-table-footer">
        <div>
          Exibindo <strong>{startItem}</strong>–<strong>{endItem}</strong> de{" "}
          <strong>{meta.total_items}</strong> registros (Página {meta.page} de{" "}
          {meta.total_pages})
        </div>

        <div className="std-pagination-controls">
          <button
            type="button"
            className="std-page-btn"
            disabled={!meta.has_prev}
            onClick={() => setPage(1)}
          >
            « Primeira
          </button>
          <button
            type="button"
            className="std-page-btn"
            disabled={!meta.has_prev}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ‹ Anterior
          </button>

          {pageNumbers.map((num) => (
            <button
              key={num}
              type="button"
              className={`std-page-btn ${meta.page === num ? "active" : ""}`}
              onClick={() => setPage(num)}
            >
              {num}
            </button>
          ))}

          <button
            type="button"
            className="std-page-btn"
            disabled={!meta.has_next}
            onClick={() => setPage((p) => Math.min(meta.total_pages, p + 1))}
          >
            Próxima ›
          </button>
          <button
            type="button"
            className="std-page-btn"
            disabled={!meta.has_next}
            onClick={() => setPage(meta.total_pages)}
          >
            Última »
          </button>
        </div>
      </div>
    </div>
  );
}
