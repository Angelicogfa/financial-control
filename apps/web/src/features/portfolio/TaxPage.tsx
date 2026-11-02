/** Carteira › Imposto (Phase 48.R7): the monthly income tax on stock exchange gains, computed
 *  from the ledger — exemption of R$ 20 thousand in ações, losses per category, the DARF to pay
 *  and the annual assessment abroad. An estimate: the investor still files with the Receita. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { TaxCategoryMonthDTO, TaxMonthDTO } from "../../api/types";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Section } from "../../components/Section";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { brl, day, monthLabel, pct, quantity } from "../../utils/format";

export const CATEGORY_LABELS: Record<string, string> = {
  COMMON: "Operações comuns (ações, ETF, BDR)",
  DAY_TRADE: "Day trade",
  FII: "Fundos imobiliários",
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** What the DARF of the month asks for, in one word. */
export function darfStatus(m: TaxMonthDTO, today: string): { label: string; tone: string } {
  if (m.paid_on) return { label: `Pago em ${day(m.paid_on)}`, tone: "success" };
  if (m.darf_brl <= 0) {
    return m.carried_darf_out_brl > 0
      ? { label: "Abaixo de R$ 10: acumula", tone: "neutral" }
      : { label: "Nada a pagar", tone: "neutral" };
  }
  return today > m.due_date ? { label: "Vencido", tone: "danger" } : { label: "A pagar", tone: "warning" };
}

function lastLosses(months: TaxMonthDTO[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const m of months) for (const c of m.categories) out[c.category] = c.loss_out_brl;
  return out;
}

function CategoryRows({ categories }: Readonly<{ categories: TaxCategoryMonthDTO[] }>) {
  return (
    <table className="app-table" aria-label="Categorias do mês">
      <thead>
        <tr>
          <th>Categoria</th>
          <th className="app-numeric">Vendas</th>
          <th className="app-numeric">Resultado</th>
          <th className="app-numeric">Isento</th>
          <th className="app-numeric">Prejuízo usado</th>
          <th className="app-numeric">Base</th>
          <th className="app-numeric">IR</th>
          <th className="app-numeric">Prejuízo a compensar</th>
        </tr>
      </thead>
      <tbody>
        {categories.map((c) => (
          <tr key={c.category}>
            <td>{CATEGORY_LABELS[c.category] ?? c.category}</td>
            <td className="app-numeric">{brl(c.sales_brl)}</td>
            <td className="app-numeric">{brl(c.result_brl)}</td>
            <td className="app-numeric">{brl(c.exempt_gain_brl)}</td>
            <td className="app-numeric">{brl(c.loss_used_brl)}</td>
            <td className="app-numeric">{brl(c.taxable_brl)}</td>
            <td className="app-numeric">
              {brl(c.tax_brl)} <span className="app-muted">({pct(c.rate, 0)})</span>
            </td>
            <td className="app-numeric">{brl(c.loss_out_brl)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MonthDetail({ month }: Readonly<{ month: string }>) {
  const detail = useQuery({ queryKey: ["tax-month", month], queryFn: () => api.tax.month(month) });
  if (detail.isPending) return <Loading lines={3} />;
  if (detail.isError) return <ErrorBanner error={detail.error} />;
  const m = detail.data;
  return (
    <Section
      title={`Vendas de ${monthLabel(m.month)}`}
      subtitle={
        m.exempt
          ? `Vendas de ações de ${brl(m.stock_sales_brl)}: lucro de ações isento (até R$ 20 mil no mês).`
          : `Vendas de ações de ${brl(m.stock_sales_brl)}: acima de R$ 20 mil, o lucro de ações é tributado.`
      }
    >
      <div className="app-table-wrap">
        <CategoryRows categories={m.categories} />
      </div>
      <div className="app-table-wrap">
        <table className="app-table" aria-label="Vendas do mês">
          <thead>
            <tr>
              <th>Dia</th>
              <th>Ativo</th>
              <th className="app-numeric">Quantidade</th>
              <th className="app-numeric">Venda</th>
              <th className="app-numeric">Custo médio</th>
              <th className="app-numeric">Resultado</th>
              <th>Tipo</th>
            </tr>
          </thead>
          <tbody>
            {(m.sales ?? []).map((s, i) => (
              <tr key={`${s.asset_id}-${s.on}-${i}`}>
                <td>{day(s.on)}</td>
                <td>{s.ticker}</td>
                <td className="app-numeric">{quantity(s.quantity)}</td>
                <td className="app-numeric">{brl(s.sale_value_brl)}</td>
                <td className="app-numeric">{brl(s.cost_brl)}</td>
                <td className="app-numeric">{brl(s.gain_brl)}</td>
                <td>{s.day_trade ? "Day trade" : CATEGORY_LABELS[s.category] ?? s.category}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

export function TaxPage() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const thisYear = new Date().getFullYear();
  const year = Number(params.get("ano")) || thisYear;
  const opened = params.get("mes");
  const today = todayIso();
  const tax = useQuery({ queryKey: ["tax-year", year], queryFn: () => api.tax.monthly(year) });
  const pay = useMutation({
    mutationFn: ({ month, paidOn }: { month: string; paidOn: string | null }) => api.tax.markDarfPaid(month, paidOn),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["tax-year"] });
      void client.invalidateQueries({ queryKey: ["tax-month"] });
    },
  });
  const open = (month: string | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (month) next.set("mes", month);
        else next.delete("mes");
        return next;
      },
      { replace: true },
    );
  const chooseYear = (value: number) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("ano", String(value));
        next.delete("mes");
        return next;
      },
      { replace: true },
    );

  return (
    <div className="app-page">
      <PageHeader
        title="Imposto"
        subtitle="IR sobre a renda variável, calculado do livro: isenção, prejuízo a compensar e o DARF de cada mês."
        actions={
          <label className="app-field">
            <span>Ano</span>
            <select value={year} onChange={(e) => chooseYear(Number(e.target.value))}>
              {Array.from({ length: 6 }, (_, i) => thisYear - i).map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </label>
        }
      />
      {tax.isPending ? (
        <Loading lines={4} />
      ) : tax.isError ? (
        <ErrorBanner error={tax.error} onRetry={() => void tax.refetch()} />
      ) : (
        <div className="app-page-stack">
          <Lead tone={tax.data.open_darf_brl > 0 ? "caution" : "neutral"}>
            <p>
              {tax.data.open_darf_brl > 0
                ? `Há ${brl(tax.data.open_darf_brl)} em DARF de ${year} ainda não marcados como pagos.`
                : `Nenhum DARF de ${year} em aberto.`}{" "}
              Estimativa a partir dos lançamentos: confira no programa da Receita antes de pagar.
            </p>
          </Lead>
          <KpiGrid
            label="Imposto do ano"
            items={[
              { label: "IR apurado", value: brl(tax.data.tax_brl) },
              { label: "DARF do ano", value: brl(tax.data.darf_brl) },
              { label: "Em aberto", value: brl(tax.data.open_darf_brl), tone: tax.data.open_darf_brl > 0 ? "caution" : "neutral" },
              ...Object.entries(lastLosses(tax.data.months)).map(([category, value]) => ({
                label: `Prejuízo a compensar · ${CATEGORY_LABELS[category]?.split(" (")[0] ?? category}`,
                value: brl(value),
              })),
            ]}
          />
          {(tax.data.issues ?? []).length > 0 && (
            <div className="app-error-banner" role="alert">
              {(tax.data.issues ?? []).map((i) => `${i.ticker} em ${day(i.on)}: ${i.message}`).join(" ")}
            </div>
          )}
          {tax.data.months.length === 0 ? (
            <Empty title={`Nenhuma venda de renda variável em ${year}`} hint="As vendas lançadas aparecem aqui com o imposto de cada mês." />
          ) : (
            <Section title="Mês a mês" subtitle="DARF código 6015, com vencimento no último dia útil do mês seguinte.">
              <div className="app-table-wrap">
                <table className="app-table" aria-label="Apuração mensal">
                  <thead>
                    <tr>
                      <th>Mês</th>
                      <th className="app-numeric">Vendas de ações</th>
                      <th className="app-numeric">IR</th>
                      <th className="app-numeric">IRRF</th>
                      <th className="app-numeric">DARF</th>
                      <th>Vencimento</th>
                      <th>Situação</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {tax.data.months.map((m) => {
                      const status = darfStatus(m, today);
                      return (
                        <tr key={m.month}>
                          <td>{monthLabel(m.month)}</td>
                          <td className="app-numeric">
                            {brl(m.stock_sales_brl)} {m.exempt && m.stock_sales_brl > 0 && <Badge tone="success">isento</Badge>}
                          </td>
                          <td className="app-numeric">{brl(m.tax_brl)}</td>
                          <td className="app-numeric">{brl(m.withheld_brl)}</td>
                          <td className="app-numeric">{brl(m.darf_brl)}</td>
                          <td>{m.darf_brl > 0 ? day(m.due_date) : "—"}</td>
                          <td>
                            <Badge tone={status.tone}>{status.label}</Badge>
                          </td>
                          <td className="app-button-row">
                            <button type="button" className="app-secondary-button" onClick={() => open(opened === m.month ? null : m.month)}>
                              {opened === m.month ? "Fechar" : "Ver vendas"}
                            </button>
                            {m.darf_brl > 0 && (
                              <button
                                type="button"
                                className="app-secondary-button"
                                disabled={pay.isPending}
                                onClick={() => pay.mutate({ month: m.month, paidOn: m.paid_on ? null : today })}
                              >
                                {m.paid_on ? "Desmarcar pagamento" : "Marcar como pago"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <ErrorBanner error={pay.error} />
            </Section>
          )}
          {opened && <MonthDetail month={opened} />}
          {tax.data.foreign && (
            <Section title="Exterior (anual)" subtitle="Lei 14.754/2023: 15% sobre o ganho do ano, pago na declaração anual.">
              <KpiGrid
                label="Exterior no ano"
                items={[
                  { label: "Vendas", value: brl(tax.data.foreign.sales_brl) },
                  { label: "Resultado", value: brl(tax.data.foreign.result_brl) },
                  { label: "Base", value: brl(tax.data.foreign.taxable_brl) },
                  { label: "IR do ano", value: brl(tax.data.foreign.tax_brl) },
                  { label: "Prejuízo a compensar", value: brl(tax.data.foreign.loss_out_brl) },
                ]}
              />
            </Section>
          )}
        </div>
      )}
    </div>
  );
}
