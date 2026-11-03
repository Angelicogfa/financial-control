/** Planejar › Renda futura (Phase 48.R8): the passive income of the portfolio as it is now —
 *  what is already declared and what the last 12 months suggest, month by month. */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Section, Segmented } from "../../components/Section";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { brl, monthLabel } from "../../utils/format";
import { ColumnChart } from "../../viz/ColumnChart";
import { instrumentPath } from "../instrument/paths";

type Horizon = "12" | "24" | "36";
const HORIZONS: Array<[Horizon, string]> = [
  ["12", "12 meses"],
  ["24", "24 meses"],
  ["36", "36 meses"],
];

export function IncomeForecastPage() {
  const [months, setMonths] = useState<Horizon>("12");
  const forecast = useQuery({
    queryKey: ["income-forecast", months],
    queryFn: () => api.portfolio.incomeForecast(Number(months) as 12 | 24 | 36),
  });
  return (
    <div className="app-page">
      <PageHeader
        title="Renda futura"
        subtitle="Proventos já anunciados e a estimativa pelo que cada ativo pagou nos últimos 12 meses, na quantidade de hoje."
        actions={<Segmented options={HORIZONS} value={months} onChange={setMonths} label="Horizonte da renda futura" />}
      />
      {forecast.isPending ? (
        <Loading lines={4} />
      ) : forecast.isError ? (
        <ErrorBanner error={forecast.error} onRetry={() => void forecast.refetch()} />
      ) : forecast.data.next_12m_brl <= 0 ? (
        <Empty
          title="Ainda não há renda para projetar"
          hint="A estimativa parte dos proventos recebidos nos últimos 12 meses e dos anunciados para os ativos que você tem."
        >
          <Link className="app-secondary-button" to="/carteira/proventos">
            Ver proventos recebidos
          </Link>
        </Empty>
      ) : (
        <div className="app-page-stack">
          <KpiGrid
            label="Renda futura"
            items={[
              { label: "Próximos 12 meses", value: brl(forecast.data.next_12m_brl) },
              { label: "Média por mês", value: brl(forecast.data.next_12m_brl / 12) },
              { label: "Já anunciado", value: brl(forecast.data.declared_brl), note: "proventos declarados ainda não pagos" },
            ]}
          />
          <Section title="Mês a mês" subtitle="Sem crescimento: é a renda da carteira como ela está hoje.">
            <ColumnChart
              title="Renda passiva prevista por mês"
              hint="Passe o mouse para ler o valor de cada mês."
              format={brl}
              columns={forecast.data.months.map((m) => ({ label: monthLabel(m.month), value: m.total_brl }))}
            />
            <div className="app-table-wrap">
              <table className="app-table" aria-label="Renda prevista por mês">
                <thead>
                  <tr>
                    <th>Mês</th>
                    <th className="app-numeric">Anunciado</th>
                    <th className="app-numeric">Estimado</th>
                    <th className="app-numeric">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.data.months.map((m) => (
                    <tr key={m.month}>
                      <td>{monthLabel(m.month)}</td>
                      <td className="app-numeric">{brl(m.declared_brl)}</td>
                      <td className="app-numeric">{brl(m.estimated_brl)}</td>
                      <td className="app-numeric">{brl(m.total_brl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
          <Section title="De onde vem" subtitle="Próximos 12 meses por ativo.">
            <div className="app-table-wrap">
              <table className="app-table" aria-label="Renda prevista por ativo">
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th className="app-numeric">12 meses</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.data.assets.map((a) => (
                    <tr key={a.asset_id}>
                      <td>
                        <Link className="app-link" to={instrumentPath(a.ticker)}>
                          {a.ticker}
                        </Link>
                      </td>
                      <td className="app-numeric">{brl(a.next_12m_brl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </div>
      )}
    </div>
  );
}
