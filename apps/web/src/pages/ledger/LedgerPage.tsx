import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, type LedgerFilters } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { PageMetaDTO } from "../../api/types";
import { useApi, type ApiState } from "../../api/useApi";
import { PageHeader } from "../../components/PageHeader";
import { Pagination } from "../../components/Pagination";
import { IconButton, IconLink } from "../../components/RowActions";
import { Async, Empty } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brl, day, num, quantity } from "../../utils/format";
import { EARNING_LABELS, EVENT_LABELS, TRADE_LABELS } from "../../utils/labels";
import { clampPage, usePagedRows, usePagination, type PaginationState } from "../../utils/pagination";
import { EditIcon, TrashIcon } from "../../layout/icons";

type TabKey = "trades" | "earnings" | "events";
const TABS: TabSpec<TabKey>[] = [
  { key: "trades", label: "Compras e vendas" },
  { key: "earnings", label: "Proventos" },
  { key: "events", label: "Eventos corporativos" },
];

function Filters({
  filters,
  onChange,
}: Readonly<{ filters: LedgerFilters; onChange: (filters: LedgerFilters) => void }>) {
  const assets = useApi("ledger-assets", () => api.assets.list(false));
  const accounts = useApi("accounts", () => api.accounts.list());
  return (
    <div className="app-filter-bar">
      <div className="app-field">
        <label htmlFor="ledger-asset">Ativo</label>
        <select
          id="ledger-asset"
          value={filters.asset_id ?? ""}
          onChange={(e) => onChange({ ...filters, asset_id: e.target.value ? Number(e.target.value) : undefined })}
        >
          <option value="">Todos</option>
          {(assets.data?.items ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.ticker}
            </option>
          ))}
        </select>
      </div>
      <div className="app-field">
        <label htmlFor="ledger-account">Conta</label>
        <select
          id="ledger-account"
          value={filters.account_id ?? ""}
          onChange={(e) => onChange({ ...filters, account_id: e.target.value ? Number(e.target.value) : undefined })}
        >
          <option value="">Todas</option>
          {(accounts.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>
      <div className="app-field">
        <label htmlFor="ledger-from">De</label>
        <input
          id="ledger-from"
          type="date"
          value={filters.date_from ?? ""}
          onChange={(e) => onChange({ ...filters, date_from: e.target.value || undefined })}
        />
      </div>
      <div className="app-field">
        <label htmlFor="ledger-to">Até</label>
        <input
          id="ledger-to"
          type="date"
          value={filters.date_to ?? ""}
          onChange={(e) => onChange({ ...filters, date_to: e.target.value || undefined })}
        />
      </div>
    </div>
  );
}

function useRemove(reload: () => void) {
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<number | null>(null);

  const remove = async (id: number, label: string, action: () => Promise<void>) => {
    if (!window.confirm(`Excluir ${label}?`)) return;
    setError(null);
    setRemovingId(id);
    try {
      await action();
      reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRemovingId(null);
    }
  };
  return { error, remove, removingId };
}

/**
 * One page of a ledger list, paged by the API. A new filter starts on the first page; a page
 * left empty by a removal moves back to the last page that still has rows.
 */
function useLedgerPage<T>(
  name: string,
  filters: LedgerFilters,
  load: (filters: LedgerFilters) => Promise<{ items: T[]; meta: PageMetaDTO }>,
): { state: ApiState<{ items: T[]; meta: PageMetaDTO }>; pager: PaginationState } {
  const pager = usePagination(JSON.stringify(filters));
  const query = { ...filters, page: pager.page + 1, page_size: pager.pageSize };
  const state = useApi(`${name}-${JSON.stringify(query)}`, () => load(query));
  const { data } = state;
  const { page, pageSize, setPage } = pager;
  useEffect(() => {
    if (data && data.items.length === 0 && data.meta.total_items > 0) {
      setPage(clampPage(page, data.meta.total_items, pageSize));
    }
  }, [data, page, pageSize, setPage]);
  return { state, pager };
}

function LedgerPagination({
  pager,
  state,
  total,
}: Readonly<{ pager: PaginationState; state: ApiState<unknown>; total: number }>) {
  return (
    <Pagination
      page={pager.page}
      pageSize={pager.pageSize}
      total={total}
      onChange={pager.setPage}
      onPageSizeChange={pager.setPageSize}
      onRefresh={state.reload}
      refreshing={state.loading}
    />
  );
}

function Trades({ filters }: Readonly<{ filters: LedgerFilters }>) {
  const { state: trades, pager } = useLedgerPage("trades", filters, api.ledger.trades);
  const { error, remove, removingId } = useRemove(trades.reload);
  return (
    <>
      {error && <p className="app-error-banner">{error}</p>}
      <Async state={trades} lines={5}>
        {(page) =>
          page.meta.total_items === 0 ? (
            <Empty title="Nenhuma compra ou venda" hint="Registre uma operação ou importe o extrato da B3." />
          ) : (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Ativo</th>
                    <th>Operação</th>
                    <th className="app-numeric">Quantidade</th>
                    <th className="app-numeric">Preço</th>
                    <th className="app-numeric">Taxas</th>
                    <th className="app-numeric">Total (R$)</th>
                    <th>Observação</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((t) => (
                    <tr key={t.id}>
                      <td>{day(t.trade_date)}</td>
                      <td>
                        <Link className="app-link" to={`/asset/${t.asset_id}`}>
                          {t.ticker ?? t.asset_id}
                        </Link>
                      </td>
                      <td>{TRADE_LABELS[t.kind]}</td>
                      <td className="app-numeric">{quantity(t.quantity)}</td>
                      <td className="app-numeric">{num(t.unit_price, 6)}</td>
                      <td className="app-numeric">{num(t.fees)}</td>
                      <td className="app-numeric">{brl(t.total_brl)}</td>
                      <td className="app-cell-wrap app-muted">{t.notes}</td>
                      <td className="app-row-actions">
                        <IconLink to={`/ledger/trades/${t.id}/edit`} label="Editar" icon={<EditIcon />} />
                        <IconButton
                          label="Excluir"
                          busyLabel="Excluindo…"
                          icon={<TrashIcon />}
                          danger
                          busy={removingId === t.id}
                          onClick={() =>
                            void remove(t.id, `a operação de ${t.ticker ?? ""} em ${day(t.trade_date)}`, () => api.ledger.deleteTrade(t.id))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <LedgerPagination pager={pager} state={trades} total={page.meta.total_items} />
            </div>
          )
        }
      </Async>
    </>
  );
}

function Earnings({ filters }: Readonly<{ filters: LedgerFilters }>) {
  const { state: earnings, pager } = useLedgerPage("earnings", filters, api.ledger.earnings);
  const { error, remove, removingId } = useRemove(earnings.reload);
  return (
    <>
      {error && <p className="app-error-banner">{error}</p>}
      <Async state={earnings} lines={5}>
        {(page) =>
          page.meta.total_items === 0 ? (
            <Empty title="Nenhum provento" hint="Registre um provento ou importe a Movimentação da B3." />
          ) : (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Pagamento</th>
                    <th>Ativo</th>
                    <th>Tipo</th>
                    <th className="app-numeric">Bruto</th>
                    <th className="app-numeric">IR</th>
                    <th className="app-numeric">Líquido (R$)</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((e) => (
                    <tr key={e.id}>
                      <td>{day(e.payment_date)}</td>
                      <td>
                        <Link className="app-link" to={`/asset/${e.asset_id}`}>
                          {e.ticker ?? e.asset_id}
                        </Link>
                      </td>
                      <td>{EARNING_LABELS[e.kind]}</td>
                      <td className="app-numeric">{num(e.gross_amount)}</td>
                      <td className="app-numeric">{num(e.withholding_tax)}</td>
                      <td className="app-numeric">{brl(e.net_amount_brl ?? e.net_amount)}</td>
                      <td className="app-row-actions">
                        <IconLink to={`/ledger/earnings/${e.id}/edit`} label="Editar" icon={<EditIcon />} />
                        <IconButton
                          label="Excluir"
                          busyLabel="Excluindo…"
                          icon={<TrashIcon />}
                          danger
                          busy={removingId === e.id}
                          onClick={() => void remove(e.id, `o provento de ${e.ticker ?? ""}`, () => api.ledger.deleteEarning(e.id))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <LedgerPagination pager={pager} state={earnings} total={page.meta.total_items} />
            </div>
          )
        }
      </Async>
    </>
  );
}

function Events({ filters }: Readonly<{ filters: LedgerFilters }>) {
  const events = useApi(`events-${filters.asset_id ?? "all"}`, () => api.ledger.events(filters.asset_id));
  const { error, remove, removingId } = useRemove(events.reload);
  const paged = usePagedRows(events.data ?? [], String(filters.asset_id ?? "all"));
  return (
    <>
      {error && <p className="app-error-banner">{error}</p>}
      <Async state={events} lines={3}>
        {(list) =>
          list.length === 0 ? (
            <Empty title="Nenhum evento corporativo" hint="Desdobramentos, grupamentos e bonificações ajustam as posições." />
          ) : (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Data ex</th>
                    <th>Ativo</th>
                    <th>Evento</th>
                    <th className="app-numeric">Fator</th>
                    <th className="app-numeric">Custo atribuído</th>
                    <th>Origem</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {paged.rows.map((e) => (
                    <tr key={e.id}>
                      <td>{day(e.ex_date)}</td>
                      <td>{e.ticker}</td>
                      <td>{EVENT_LABELS[e.kind]}</td>
                      <td className="app-numeric">{num(e.factor, 6)}</td>
                      <td className="app-numeric">{e.kind === "BONUS" ? num(e.unit_cost) : "—"}</td>
                      <td>{e.imported ? "Extrato B3" : "Manual"}</td>
                      <td className="app-row-actions">
                        <IconButton
                          label="Excluir"
                          busyLabel="Excluindo…"
                          icon={<TrashIcon />}
                          danger
                          busy={removingId === e.id}
                          onClick={() => void remove(e.id, `o evento de ${e.ticker ?? ""}`, () => api.ledger.deleteEvent(e.id))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination {...paged.pagination} onRefresh={events.reload} refreshing={events.loading} />
            </div>
          )
        }
      </Async>
    </>
  );
}

const NEW_LINKS: Record<TabKey, { to: string; label: string }> = {
  trades: { to: "/ledger/trades/new", label: "Nova operação" },
  earnings: { to: "/ledger/earnings/new", label: "Novo provento" },
  events: { to: "/ledger/events/new", label: "Novo evento" },
};

export function LedgerPage() {
  const [tab, setTab] = useTab(TABS, "trades");
  const [filters, setFilters] = useState<LedgerFilters>({});
  return (
    <div className="app-page">
      <PageHeader
        title="Lançamentos"
        subtitle="Compras, vendas, proventos e eventos que formam as posições."
        actions={
          <>
            <Link className="app-secondary-button" to="/ledger/import">
              Importar extrato B3
            </Link>
            <Link className="app-primary-button" to={NEW_LINKS[tab].to}>
              {NEW_LINKS[tab].label}
            </Link>
          </>
        }
      />
      <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Tipo de lançamento" />
      <Filters filters={filters} onChange={setFilters} />
      {tab === "trades" && <Trades filters={filters} />}
      {tab === "earnings" && <Earnings filters={filters} />}
      {tab === "events" && <Events filters={filters} />}
    </div>
  );
}
