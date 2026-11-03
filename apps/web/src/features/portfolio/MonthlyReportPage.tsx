/** Carteira › Relatório (Phase 48.R9): one month of the portfolio on one page — what it was
 *  worth, what came in and out, what it earned and paid, and how far the goals are. "Salvar em
 *  PDF" prints the page; the browser saves it as a PDF, with the menu and the buttons left out. */

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { ArcaClass, MonthlyReportDTO } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section } from "../../components/Section";
import { ErrorBanner, Loading } from "../../components/States";
import { brl, day, pct, today } from "../../utils/format";
import { ARCA_LABELS } from "../../utils/labels";
import { STATUS } from "../planning/GoalsPage";

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

/** "outubro de 2026" */
export function monthTitle(month: string): string {
  const [y, m] = month.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} de ${y}`;
}

/** The month before today's, the last one already closed (YYYY-MM). */
export function lastClosedMonth(on: string = today()): string {
  const [y, m] = on.split("-").map(Number);
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
}

const TRADE_KIND: Record<string, string> = { BUY: "Compra", SELL: "Venda" };

/** The first sentence of the report: what the month did to the wealth. */
export function reportLead(r: MonthlyReportDTO): string {
  if (r.end_date === null) return "Não há retrato da carteira neste mês para medir o resultado.";
  const ret = r.month_return === null ? "" : ` (${pct(r.month_return, 2, true)} no mês)`;
  const flow =
    r.net_flow_brl > 0
      ? `, com ${brl(r.net_flow_brl)} de aportes líquidos`
      : r.net_flow_brl < 0
        ? `, com ${brl(-r.net_flow_brl)} de resgates líquidos`
        : "";
  const result = r.result_brl >= 0 ? `ganhou ${brl(r.result_brl)}` : `perdeu ${brl(-r.result_brl)}`;
  return `A carteira foi de ${brl(r.start_value_brl)} para ${brl(r.end_value_brl)}${flow}; descontados os aportes, ${result}${ret}.`;
}

function Report({ report }: Readonly<{ report: MonthlyReportDTO }>) {
  return (
    <div className="app-page-stack app-report">
      <Lead tone={report.end_date === null ? "neutral" : report.result_brl >= 0 ? "positive" : "negative"}>
        <p>{reportLead(report)}</p>
      </Lead>
      <KpiGrid
        label="O mês em números"
        items={[
          { label: "Patrimônio no início", value: brl(report.start_value_brl), note: report.start_date ? day(report.start_date) : undefined },
          { label: "Patrimônio no fim", value: brl(report.end_value_brl), note: report.end_date ? day(report.end_date) : undefined },
          { label: "Compras", value: brl(report.bought_brl) },
          { label: "Vendas", value: brl(report.sold_brl) },
          { label: "Proventos recebidos", value: brl(report.income_brl) },
          {
            label: "Resultado do mês",
            value: brl(report.result_brl),
            tone: report.result_brl >= 0 ? "positive" : "negative",
            note: report.month_return === null ? undefined : `${pct(report.month_return, 2, true)} (TWR, com proventos)`,
          },
        ]}
      />
      {report.allocation.length > 0 && (
        <Section title="Alocação no fim do mês">
          <div className="app-table-wrap">
            <table className="app-table" aria-label="Alocação no fim do mês">
              <thead>
                <tr>
                  <th>Classe</th>
                  <th className="app-numeric">Valor</th>
                  <th className="app-numeric">Peso</th>
                  <th className="app-numeric">Meta</th>
                </tr>
              </thead>
              <tbody>
                {report.allocation.map((c) => (
                  <tr key={c.arca_class}>
                    <td>{ARCA_LABELS[c.arca_class as ArcaClass] ?? c.arca_class}</td>
                    <td className="app-numeric">{brl(c.value_brl)}</td>
                    <td className="app-numeric">{pct(c.current_pct)}</td>
                    <td className="app-numeric">{c.target_pct === null ? "—" : pct(c.target_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
      <Section title="Negociações" subtitle={report.trades.length ? undefined : "Nenhuma compra ou venda no mês."}>
        {report.trades.length > 0 && (
          <div className="app-table-wrap">
            <table className="app-table" aria-label="Negociações do mês">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Ativo</th>
                  <th>Tipo</th>
                  <th className="app-numeric">Quantidade</th>
                  <th className="app-numeric">Valor</th>
                </tr>
              </thead>
              <tbody>
                {report.trades.map((t, i) => (
                  <tr key={`${t.trade_date}-${t.ticker}-${i}`}>
                    <td>{day(t.trade_date)}</td>
                    <td>{t.ticker}</td>
                    <td>{TRADE_KIND[t.kind] ?? t.kind}</td>
                    <td className="app-numeric">{t.quantity.toLocaleString("pt-BR")}</td>
                    <td className="app-numeric">{brl(t.value_brl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title="Proventos recebidos" subtitle={report.earnings.length ? undefined : "Nenhum provento pago no mês."}>
        {report.earnings.length > 0 && (
          <div className="app-table-wrap">
            <table className="app-table" aria-label="Proventos do mês">
              <thead>
                <tr>
                  <th>Pagamento</th>
                  <th>Ativo</th>
                  <th className="app-numeric">Líquido</th>
                </tr>
              </thead>
              <tbody>
                {report.earnings.map((e, i) => (
                  <tr key={`${e.payment_date}-${e.ticker}-${i}`}>
                    <td>{day(e.payment_date)}</td>
                    <td>{e.ticker}</td>
                    <td className="app-numeric">{brl(e.net_brl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title="Imposto do mês">
        <p>
          {report.tax === null
            ? "Sem vendas tributáveis no mês."
            : report.tax.darf_brl > 0
              ? `DARF de ${brl(report.tax.darf_brl)} com vencimento em ${day(report.tax.due_date)}${report.tax.paid_on ? `, pago em ${day(report.tax.paid_on)}` : ", ainda não marcado como pago"}.`
              : report.tax.exempt
                ? `Vendas de ações de ${brl(report.tax.stock_sales_brl)}, dentro da isenção de R$ 20 mil: sem DARF.`
                : "Nenhum DARF a pagar neste mês."}
        </p>
      </Section>
      {report.goals.length > 0 && (
        <Section title="Metas">
          <ul className="app-report-list" aria-label="Metas no fim do mês">
            {report.goals.map((g) => (
              <li key={g.name}>
                <strong>{g.name}</strong>: {pct(g.progress, 0)} do caminho, {STATUS[g.status as keyof typeof STATUS]?.label.toLowerCase() ?? g.status}
                {g.required_monthly_brl > 0 ? `; pede ${brl(g.required_monthly_brl)} por mês` : ""}.
              </li>
            ))}
          </ul>
        </Section>
      )}
      {report.data_gaps.length > 0 && <Notes items={report.data_gaps} label="Lacunas dos dados" />}
    </div>
  );
}

export function MonthlyReportPage() {
  const [params, setParams] = useSearchParams();
  const month = /^\d{4}-\d{2}$/.test(params.get("mes") ?? "") ? (params.get("mes") as string) : lastClosedMonth();
  const report = useQuery({ queryKey: ["monthly-report", month], queryFn: () => api.portfolio.monthlyReport(month) });
  return (
    <div className="app-page">
      <PageHeader
        title={`Relatório de ${monthTitle(month)}`}
        subtitle="Patrimônio, aportes, resultado, proventos, negociações, imposto e metas de um mês."
        actions={
          <div className="app-button-row">
            <label className="app-check" htmlFor="report-month">
              <span className="app-muted">Mês</span>
              <input
                id="report-month"
                type="month"
                value={month}
                max={today().slice(0, 7)}
                onChange={(e) => e.target.value && setParams({ mes: e.target.value }, { replace: true })}
              />
            </label>
            <button type="button" className="app-primary-button" onClick={() => window.print()} disabled={!report.data}>
              Salvar em PDF
            </button>
          </div>
        }
      />
      {report.isPending ? (
        <Loading lines={6} label="Montando o relatório" />
      ) : report.isError ? (
        <ErrorBanner error={report.error} onRetry={() => void report.refetch()} />
      ) : (
        <Report report={report.data} />
      )}
    </div>
  );
}
