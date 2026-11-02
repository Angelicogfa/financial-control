/** Carteira › Proventos (Phase 48.R5): what the portfolio paid and what is already declared. */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Section } from "../../components/Section";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { DeclaredEarnings } from "../../pages/home/DeclaredEarnings";
import { brl, monthLabel, pct } from "../../utils/format";
import { ColumnChart } from "../../viz/ColumnChart";
import { instrumentPath } from "../instrument/paths";

function change(now: number, before: number): string | null {
  if (before <= 0) return null;
  return pct(now / before - 1, 1, true);
}

export function IncomePage() {
  const income = useQuery({ queryKey: ["portfolio-income", 24], queryFn: () => api.portfolio.income(24) });

  return (
    <div className="app-page">
      <PageHeader
        title="Proventos"
        subtitle="O que a carteira pagou, líquido de IR e em reais, e o que já foi anunciado."
      />
      {income.isPending ? (
        <Loading lines={4} />
      ) : income.isError ? (
        <ErrorBanner error={income.error} onRetry={() => void income.refetch()} />
      ) : income.data.total_brl <= 0 ? (
        <Empty
          title="Nenhum provento recebido ainda"
          hint="Os dividendos, JCP e rendimentos lançados (ou importados do extrato da B3) aparecem aqui."
        >
          <Link className="app-secondary-button" to="/lancamentos/importar">
            Importar extrato
          </Link>
        </Empty>
      ) : (
        <div className="app-page-stack">
          <KpiGrid
            label="Proventos recebidos"
            items={[
              {
                label: "Últimos 12 meses",
                value: brl(income.data.last_12m_brl),
                note: change(income.data.last_12m_brl, income.data.previous_12m_brl)
                  ? `${change(income.data.last_12m_brl, income.data.previous_12m_brl)} sobre os 12 anteriores`
                  : undefined,
              },
              {
                label: "Yield on cost",
                value: income.data.yield_on_cost === null || income.data.yield_on_cost === undefined ? "—" : pct(income.data.yield_on_cost, 1),
                note: "12 meses sobre o custo dos ativos que pagaram",
              },
              { label: "Média por mês", value: brl(income.data.last_12m_brl / 12) },
              { label: "Desde o início", value: brl(income.data.total_brl) },
            ]}
          />
          <Section title="Por mês" subtitle="Líquido recebido em cada mês dos últimos 24.">
            <ColumnChart
              title="Proventos líquidos recebidos por mês"
              hint="Passe o mouse para ler o valor de cada mês."
              format={brl}
              columns={income.data.months.map((m) => ({ label: monthLabel(m.month), value: m.net_brl }))}
            />
          </Section>
          <Section title="Quem pagou" subtitle="Últimos 12 meses, do maior para o menor.">
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Ativo</th>
                    <th className="app-numeric">Recebido</th>
                    <th className="app-numeric">Yield on cost</th>
                  </tr>
                </thead>
                <tbody>
                  {income.data.assets.map((a) => (
                    <tr key={a.asset_id}>
                      <td>
                        <Link className="app-link" to={instrumentPath(a.ticker)}>
                          {a.ticker}
                        </Link>
                      </td>
                      <td className="app-numeric">{brl(a.last_12m_brl)}</td>
                      <td className="app-numeric">
                        {a.yield_on_cost === null || a.yield_on_cost === undefined ? "—" : pct(a.yield_on_cost, 1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </div>
      )}
      <Section title="Anunciados" subtitle="Proventos declarados e ainda não pagos.">
        <DeclaredEarnings />
      </Section>
    </div>
  );
}
