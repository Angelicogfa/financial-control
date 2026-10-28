import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { AgendaStatus, EarningKind } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { brl, day, monthLabel, num } from "../../utils/format";
import { EARNING_LABELS } from "../../utils/labels";

export const AGENDA_STATUS_LABELS: Record<AgendaStatus, string> = {
  UPCOMING: "Antes da data com",
  AWAITING_PAYMENT: "Direito garantido",
};

const MAX_ROWS = 8;

/** Declared future income (B3 agenda): what is already announced for the next months. */
export function DeclaredEarnings() {
  const agenda = useApi("home-earnings-agenda", () => api.portfolio.earningsAgenda());
  if (agenda.error) return <ErrorBanner error={agenda.error} onRetry={agenda.reload} />;
  if (agenda.loading && !agenda.data) return <Loading lines={3} />;
  const data = agenda.data;
  if (!data) return null;
  const items = data.items ?? [];
  const months = Object.entries(data.declared_by_month ?? {});
  return (
    <section className="app-card app-card-padded" aria-label="Proventos anunciados">
      <div className="health-pillar-head">
        <h2 className="app-card-heading">Proventos anunciados</h2>
        <strong>{brl(data.declared_net_brl)}</strong>
      </div>
      <p className="app-card-hint">
        Renda já declarada pelas empresas e fundos (agenda da B3), líquida do IR retido estimado
        {months.length ? `: ${months.map(([m, v]) => `${monthLabel(m)} ${brl(v)}`).join(" · ")}` : ""}.
      </p>
      {items.length === 0 ? (
        <Empty title="Nenhum provento anunciado" hint="A agenda cobre ações, BDRs e FIIs da carteira e da watchlist." />
      ) : (
        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Ativo</th>
                <th>Tipo</th>
                <th>Data com</th>
                <th>Pagamento</th>
                <th className="app-numeric">Por cota</th>
                <th className="app-numeric">Líquido estimado</th>
              </tr>
            </thead>
            <tbody>
              {items.slice(0, MAX_ROWS).map((item) => (
                <tr key={`${item.ticker}-${item.kind}-${item.com_date}-${item.payment_date}`}>
                  <td>
                    {item.asset_id ? (
                      <Link className="app-link" to={`/asset/${item.asset_id}`}>
                        {item.ticker}
                      </Link>
                    ) : (
                      item.ticker
                    )}{" "}
                    {!item.held && <Badge>Watchlist</Badge>}
                  </td>
                  <td>{EARNING_LABELS[item.kind as EarningKind] ?? item.label}</td>
                  <td>
                    {day(item.com_date)} <small className="app-muted">{AGENDA_STATUS_LABELS[item.status]}</small>
                  </td>
                  <td>{day(item.payment_date)}</td>
                  <td className="app-numeric">{num(item.rate, 4)}</td>
                  <td className="app-numeric">{item.net_amount === null || item.net_amount === undefined ? "—" : brl(item.net_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {items.length > MAX_ROWS && <p className="app-muted">E mais {items.length - MAX_ROWS} anúncio(s).</p>}
    </section>
  );
}
