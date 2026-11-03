/** Planejar › Metas (Phase 48.R8): where the investor wants to get, how far it is and how much
 *  to contribute per month to get there. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { GoalDTO, GoalKind } from "../../api/types";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Section } from "../../components/Section";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { brl, day, parseDecimal, pct } from "../../utils/format";

export const STATUS: Record<GoalDTO["status"], { label: string; tone: string }> = {
  REACHED: { label: "Atingida", tone: "success" },
  ON_TRACK: { label: "No caminho", tone: "success" },
  OFF_TRACK: { label: "Fora do caminho", tone: "warning" },
  MISSED: { label: "Prazo vencido", tone: "danger" },
};

/** The sentence under each goal: what it takes from now on. */
export function goalLead(g: GoalDTO): string {
  if (g.status === "REACHED") return "Meta atingida.";
  if (g.status === "MISSED") return "O prazo passou sem atingir a meta; ajuste a data ou o valor.";
  const years = Math.floor(g.months_left / 12);
  const months = g.months_left % 12;
  const when = [years ? `${years} ano(s)` : "", months ? `${months} mês(es)` : ""].filter(Boolean).join(" e ") || "menos de um mês";
  const pace =
    g.status === "ON_TRACK"
      ? `com ${brl(g.monthly_contribution_brl)} por mês chega a ${brl(g.projected_wealth_brl)}`
      : `faltam ${brl(g.required_monthly_brl)} por mês (hoje: ${brl(g.monthly_contribution_brl)})`;
  return `Em ${when}, ${pace}.`;
}

function GoalForm() {
  const client = useQueryClient();
  const [kind, setKind] = useState<GoalKind>("WEALTH");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [date, setDate] = useState("");
  const [monthly, setMonthly] = useState("");
  const [annualReturn, setAnnualReturn] = useState("6");
  const [incomeYield, setIncomeYield] = useState("6");
  const [invalid, setInvalid] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (body: Parameters<typeof api.goals.create>[0]) => api.goals.create(body),
    onSuccess: () => {
      setName("");
      setTarget("");
      setMonthly("");
      void client.invalidateQueries({ queryKey: ["goals"] });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = parseDecimal(target);
    const contribution = parseDecimal(monthly || "0");
    const ret = parseDecimal(annualReturn);
    const yld = parseDecimal(incomeYield);
    if (!name.trim() || value === null || value <= 0 || !date || contribution === null || ret === null || yld === null) {
      setInvalid("Preencha o nome, o valor, a data e as premissas.");
      return;
    }
    setInvalid(null);
    create.mutate({
      kind,
      name: name.trim(),
      target_brl: value,
      target_date: date,
      monthly_contribution_brl: contribution,
      annual_return: ret / 100,
      income_yield: yld / 100,
    });
  };
  return (
    <form className="app-filter-bar" onSubmit={submit} aria-label="Nova meta">
      <label className="app-field">
        <span>Tipo</span>
        <select value={kind} onChange={(e) => setKind(e.target.value as GoalKind)}>
          <option value="WEALTH">Patrimônio</option>
          <option value="PASSIVE_INCOME">Renda passiva por mês</option>
        </select>
      </label>
      <label className="app-field">
        <span>Nome</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Independência financeira" />
      </label>
      <label className="app-field">
        <span>{kind === "WEALTH" ? "Patrimônio (R$)" : "Renda por mês (R$)"}</span>
        <input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} />
      </label>
      <label className="app-field">
        <span>Até</span>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label className="app-field">
        <span>Aporte mensal (R$)</span>
        <input inputMode="decimal" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
      </label>
      <label className="app-field">
        <span>Retorno real (% a.a.)</span>
        <input inputMode="decimal" value={annualReturn} onChange={(e) => setAnnualReturn(e.target.value)} />
      </label>
      {kind === "PASSIVE_INCOME" && (
        <label className="app-field">
          <span>Yield da renda (% a.a.)</span>
          <input inputMode="decimal" value={incomeYield} onChange={(e) => setIncomeYield(e.target.value)} />
        </label>
      )}
      <button type="submit" className="app-primary-button" disabled={create.isPending}>
        Criar meta
      </button>
      {invalid && (
        <p className="app-error-banner" role="alert">
          {invalid}
        </p>
      )}
      <ErrorBanner error={create.error} />
    </form>
  );
}

export function GoalsPage() {
  const client = useQueryClient();
  const goals = useQuery({ queryKey: ["goals"], queryFn: () => api.goals.list() });
  const remove = useMutation({
    mutationFn: (id: number) => api.goals.remove(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["goals"] }),
  });
  return (
    <div className="app-page">
      <PageHeader
        title="Metas"
        subtitle="Patrimônio ou renda passiva por mês até uma data: quanto já tem, para onde vai e quanto aportar."
      />
      <div className="app-page-stack">
        <Section title="Nova meta" subtitle="O retorno é real (acima da inflação); a renda passiva usa o yield para saber o patrimônio necessário.">
          <GoalForm />
        </Section>
        {goals.isPending ? (
          <Loading lines={3} />
        ) : goals.isError ? (
          <ErrorBanner error={goals.error} onRetry={() => void goals.refetch()} />
        ) : goals.data.length === 0 ? (
          <Empty title="Nenhuma meta criada" hint="Ex.: R$ 1 milhão até 2036, ou R$ 5 mil por mês de renda passiva." />
        ) : (
          <ul className="app-thesis-list" aria-label="Metas">
            {goals.data.map((g) => (
              <li key={g.id} className="app-card app-card-padded">
                <div className="app-button-row">
                  <strong>{g.name}</strong>
                  <Badge tone={STATUS[g.status].tone}>{STATUS[g.status].label}</Badge>
                  <span className="app-muted">
                    {g.kind === "WEALTH" ? `${brl(g.target_brl)} até ${day(g.target_date)}` : `${brl(g.target_brl)} por mês até ${day(g.target_date)}`}
                  </span>
                  <button type="button" className="app-secondary-button" aria-label={`Apagar a meta ${g.name}`} onClick={() => remove.mutate(g.id)}>
                    Apagar
                  </button>
                </div>
                <div
                  className="app-lens-track app-goal-track"
                  role="progressbar"
                  aria-label={`Progresso de ${g.name}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(g.progress * 100)}
                >
                  <span className="app-lens-fill" style={{ width: `${Math.round(g.progress * 100)}%` }} />
                </div>
                <p>
                  {g.kind === "WEALTH"
                    ? `${brl(g.current_brl)} de ${brl(g.target_brl)} (${pct(g.progress, 0)}).`
                    : `${brl(g.current_brl)} por mês de ${brl(g.target_brl)} (${pct(g.progress, 0)}); pede ${brl(g.target_wealth_brl)} de patrimônio.`}{" "}
                  {goalLead(g)}
                </p>
              </li>
            ))}
          </ul>
        )}
        <ErrorBanner error={remove.error} />
        <p className="app-muted">
          O aporte mensal das metas aparece como sugestão em <Link to="/aportar">Aportar</Link>.
        </p>
      </div>
    </div>
  );
}
