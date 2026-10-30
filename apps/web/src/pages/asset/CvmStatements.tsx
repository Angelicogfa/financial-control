/** "Balanços entregues à CVM" (Phase 42.2): what was known after each DFP/ITR delivery, with the
 *  delivery date, and today's indicators from the last delivered statement. */

import { api } from "../../api/endpoints";
import type { AssetStatementsDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { KpiGrid, Notes, Section, type KpiSpec } from "../../components/Section";
import { Async, Empty } from "../../components/States";
import { brl, brlCompact, day, num, pct } from "../../utils/format";

const cell = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : brlCompact(value);

function kpis(data: AssetStatementsDTO): KpiSpec[] {
  const v = data.valuation;
  if (!v) return [];
  const multiple = (x: number | null | undefined) => (x === null || x === undefined ? "—" : num(x, 1));
  const earningsYield = v.earnings_yield ?? null;
  return [
    {
      label: "P/L",
      value: earningsYield && earningsYield > 0 ? num(1 / earningsYield, 1) : "—",
      note: earningsYield !== null ? `lucro rende ${pct(earningsYield, 1)} do valor` : undefined,
    },
    { label: "P/VP", value: multiple(v.price_to_book) },
    { label: "EV/EBITDA", value: multiple(v.ev_to_ebitda) },
    { label: "Dividendos pagos / valor", value: v.dividend_yield === null || v.dividend_yield === undefined ? "—" : pct(v.dividend_yield, 1) },
  ];
}

export function CvmStatements({ assetId }: Readonly<{ assetId: number }>) {
  const state = useApi(`asset-statements-${assetId}`, () => api.assets.statements(assetId));
  return (
    <Async state={state}>
      {(data) => {
        if (data.status === "NOT_A_COMPANY") return null;
        if (data.status !== "OK")
          return (
            <Section title="Balanços entregues à CVM">
              <Empty title="Balanços ainda não carregados" hint={(data.notes ?? []).join(" ")} />
            </Section>
          );
        const latest = data.deliveries?.[0];
        const financial = data.template === "FINANCIAL";
        return (
          <Section
            title="Balanços entregues à CVM"
            subtitle={
              latest
                ? `Último: ${latest.doc_type} de ${day(latest.reference_date)}, entregue em ${day(latest.delivered_on)}.`
                : undefined
            }
          >
            {data.valuation && (
              <KpiGrid
                items={kpis(data)}
                label={`Indicadores ao preço de ${brl(data.valuation.price)}`}
              />
            )}
            <div className="app-table-wrap">
              <table className="app-table" aria-label="Balanços entregues à CVM">
                <thead>
                  <tr>
                    <th>Referência</th>
                    <th>Entregue em</th>
                    {!financial && <th className="app-numeric">Receita 12m</th>}
                    {!financial && <th className="app-numeric">EBITDA 12m</th>}
                    <th className="app-numeric">Lucro 12m</th>
                    <th className="app-numeric">Dividendos 12m</th>
                    <th className="app-numeric">Patrimônio</th>
                    {!financial && <th className="app-numeric">Dívida líquida</th>}
                  </tr>
                </thead>
                <tbody>
                  {(data.deliveries ?? []).map((d) => (
                    <tr key={`${d.doc_type}-${d.reference_date}-${d.version}`}>
                      <td>
                        {d.doc_type} {day(d.reference_date)}
                        {d.version > 1 && <span className="app-muted"> · versão {d.version}</span>}
                      </td>
                      <td>{day(d.delivered_on)}</td>
                      {!financial && <td className="app-numeric">{cell(d.revenue)}</td>}
                      {!financial && <td className="app-numeric">{cell(d.ebitda)}</td>}
                      <td className="app-numeric">{cell(d.net_income)}</td>
                      <td className="app-numeric">{cell(d.dividends_paid)}</td>
                      <td className="app-numeric">{cell(d.equity)}</td>
                      {!financial && <td className="app-numeric">{cell(d.net_debt)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Notes items={data.notes ?? []} />
          </Section>
        );
      }}
    </Async>
  );
}
