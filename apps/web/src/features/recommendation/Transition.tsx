/** How to reach a class's targets (Phase 34.7): contributions only, or selling with the real
 *  income tax. A study: nothing is saved and no order is given. It only loads when asked, because
 *  it rebuilds the portfolio. */

import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../../api/endpoints";
import type { ArcaClass, TransitionDTO } from "../../api/types";
import { KpiGrid, Lead, Notes } from "../../components/Section";
import { ErrorBanner, Loading } from "../../components/States";
import { brl, parseDecimal, pct } from "../../utils/format";

/** The sentence of the contributions path. */
export function contributionLead(t: TransitionDTO): string {
  if (t.months === 0) return "A classe já está perto dos pesos-alvo: não há o que mudar.";
  if (t.months == null) {
    return (t.monthly_brl ?? 0) > 0
      ? `Com ${brl(t.monthly_brl)} por mês, a classe não chega perto dos pesos-alvo em 20 anos.`
      : "Informe quanto do aporte mensal vai para esta classe para ver o prazo.";
  }
  const time = t.months === 1 ? "1 mês" : `${t.months} meses`;
  return `Só com aportes de ${brl(t.monthly_brl)} por mês, a classe chega perto dos pesos-alvo em ${time}, sem vender nada nem pagar IR.`;
}

/** The sentence of the sales path. */
export function salesLead(t: TransitionDTO): string {
  if ((t.sales ?? []).length === 0) return "Nada a vender: nenhum ativo passa do peso-alvo em uma unidade inteira.";
  const cost = `Vender ${brl(t.sold_brl)} custaria ${brl(t.cost_brl)} (${brl(t.tax_brl)} de IR e ${brl(t.fees_brl)} de custos)`;
  if (t.payback_months == null) return `${cost}, e a melhora esperada não paga esse custo.`;
  const payback = `${t.payback_months.toLocaleString("pt-BR")} meses`;
  return t.pays_off
    ? `${cost}, pagos pela melhora esperada em ${payback}.`
    : `${cost}, e a melhora esperada levaria ${payback} para pagar: mais que o horizonte de ${t.payback_horizon_months} meses.`;
}

function Result({ data }: Readonly<{ data: TransitionDTO }>) {
  if (data.status !== "OK") return <p className="app-muted">Esta classe ainda não tem rodada recente da recomendação.</p>;
  const sales = data.sales ?? [];
  return (
    <div className="app-page-stack">
      <Lead>
        <p>{contributionLead(data)}</p>
        <p>{salesLead(data)}</p>
      </Lead>
      <KpiGrid
        label="Transição da classe"
        items={[
          { label: "Fora do lugar", value: pct(data.distance, 0), note: "da classe, hoje" },
          { label: "Só com aportes", value: data.months == null ? "—" : `${data.months} meses`, note: `até ${pct(data.tolerance, 0)} fora do lugar` },
          { label: "IR se vender tudo agora", value: brl(data.tax_brl) },
          ...(data.split_months != null
            ? [{ label: `IR em ${data.split_months} meses`, value: brl(data.split_tax_brl), note: "vendas de ações divididas para ficar na isenção" }]
            : []),
          { label: "Melhora esperada", value: brl(data.expected_gain_year_brl), note: "ao ano, com as vendas" },
        ]}
      />
      <div className="app-table-wrap">
        <table className="app-table" aria-label="Pesos atuais e alvos">
          <thead>
            <tr>
              <th>Ativo</th>
              <th className="app-numeric">Peso atual</th>
              <th className="app-numeric">Peso-alvo</th>
              <th className="app-numeric">Próximo aporte</th>
              <th className="app-numeric">Compra com as vendas</th>
            </tr>
          </thead>
          <tbody>
            {(data.lines ?? []).map((l) => (
              <tr key={l.ticker}>
                <td>{l.ticker}</td>
                <td className="app-numeric">{pct(l.current_weight)}</td>
                <td className="app-numeric">{pct(l.target_weight)}</td>
                <td className="app-numeric">{brl(l.next_contribution_brl)}</td>
                <td className="app-numeric">{brl(l.buy_brl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sales.length > 0 && (
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Vendas do estudo">
            <thead>
              <tr>
                <th>Ativo</th>
                <th className="app-numeric">Quantidade</th>
                <th className="app-numeric">Valor</th>
                <th className="app-numeric">Custo</th>
                <th className="app-numeric">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {sales.map((s) => (
                <tr key={s.ticker}>
                  <td>{s.ticker}</td>
                  <td className="app-numeric">{s.quantity.toLocaleString("pt-BR")}</td>
                  <td className="app-numeric">{brl(s.value_brl)}</td>
                  <td className="app-numeric">{brl(s.cost_brl)}</td>
                  <td className="app-numeric">{brl(s.gain_brl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Notes
        items={[
          "É um estudo: nada é gravado e nenhuma ordem é dada; não é recomendação de investimento.",
          "Os alvos são os mesmos que o aporte segue, já puxados para os seus pesos atuais pela confiança.",
          "O IR segue a apuração real: isenção de R$ 20 mil em ações, prejuízo acumulado e vendas já feitas no mês, aos preços de hoje.",
          "A melhora esperada usa a premissa de retorno da matriz, que não foi validada; os prazos não contam a valorização dos ativos.",
        ]}
      />
    </div>
  );
}

export function Transition({ arcaClass }: Readonly<{ arcaClass: ArcaClass | string }>) {
  const [typed, setTyped] = useState("");
  const [monthly, setMonthly] = useState<number | null>(null);
  const [invalid, setInvalid] = useState(false);
  const query = useQuery({
    queryKey: ["recommendation-transition", arcaClass, monthly],
    queryFn: () => api.recommendation.transition(arcaClass, monthly ?? 0),
    enabled: monthly !== null,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = parseDecimal(typed || "0");
    setInvalid(value === null || value < 0);
    if (value !== null && value >= 0) setMonthly(value);
  };
  return (
    <div className="app-page-stack">
      <form className="app-filter-bar" onSubmit={submit} aria-label="Como chegar aos pesos-alvo">
        <label className="app-field">
          <span>Aporte mensal nesta classe (R$)</span>
          <input inputMode="decimal" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </label>
        <button type="submit" className="app-secondary-button" disabled={query.isFetching}>
          Ver o caminho
        </button>
      </form>
      {invalid && (
        <p className="app-error-banner" role="alert">
          Informe um valor em reais, zero ou maior.
        </p>
      )}
      {monthly !== null &&
        (query.isPending ? (
          <Loading lines={4} label="Calculando a transição" />
        ) : query.isError ? (
          <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <Result data={query.data} />
        ))}
    </div>
  );
}
