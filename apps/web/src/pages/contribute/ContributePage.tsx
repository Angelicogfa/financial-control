import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  AssetContributionOrderDTO,
  ClassAllocationDTO,
  IntraClassStrategy,
  SavedContributionPlanDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Combobox, codeOptions } from "../../components/Combobox";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section } from "../../components/Section";
import { Async, Empty, Spinner } from "../../components/States";
import { brl, dateTime, num, parseDecimal, plural, points, quantity, today } from "../../utils/format";
import { ARCA_LABELS, PLAN_STATUS_LABELS, STRATEGY_LABELS } from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { clearStored, useStoredState } from "../../utils/storedState";
import { orderReasonText, orderWeightText, PlanRationale, strategyByClass } from "./Rationale";

const STEPS = ["Valor", "Classes", "Ativos", "Confirmar"];

/** Where the money goes, in words: the classes that receive it, the buys and what is left over. */
export function planStory(saved: SavedContributionPlanDTO): string {
  const plan = saved.plan;
  const byClass = Object.entries(plan.by_class_allocated_brl)
    .filter(([, value]) => value > 0.009)
    .sort(([, a], [, b]) => b - a)
    .map(([key, value]) => `${brl(value)} para ${ARCA_LABELS[key as keyof typeof ARCA_LABELS] ?? key}`);
  const buys = plan.orders.filter((o) => o.recommended_quantity > 0).length;
  let text = `Dos ${brl(plan.contribution_amount_brl)} do aporte, `;
  text += byClass.length > 0 ? `${byClass.join(", ")}, em ${plural(buys, "compra sugerida", "compras sugeridas")}.` : "nenhum valor encontrou destino.";
  if (plan.unallocated_cash_brl > 0.009) text += ` ${brl(plan.unallocated_cash_brl)} ficam sem destino.`;
  return text;
}

const PLAN_NOTES = [
  "Quantidades são arredondadas para unidades inteiras; o que não compra uma unidade fica sem destino.",
  "Ajuste quantidade e preço ao que foi executado na corretora antes de confirmar.",
];

function Steps({ current }: Readonly<{ current: number }>) {
  return (
    <ol className="app-steps" aria-label="Etapas do aporte">
      {STEPS.map((label, i) => (
        <li
          key={label}
          className={`app-step${i < current ? " is-done" : ""}`}
          aria-current={i === current ? "step" : undefined}
        >
          <b>{i + 1}</b>
          {label}
        </li>
      ))}
    </ol>
  );
}

function AmountStep() {
  const navigate = useNavigate();
  const [amount, setAmount] = useState("");
  const [strategy, setStrategy] = useState<IntraClassStrategy | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const plans = useApi("contribution-plans", () => api.contributions.list());

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = parseDecimal(amount);
    if (value === null || value <= 0) {
      setError("Informe um valor maior que zero.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const plan = await api.contributions.draft({ amount_brl: value, strategy_override: strategy || null });
      navigate(`/contribute/${plan.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-page-stack">
      <Steps current={0} />
      <Lead eyebrow="Como funciona">
        <p>
          Informe o valor e o sistema divide o aporte pelas classes ARCA mais distantes da meta, sugerindo os ativos e as
          quantidades. Nada é registrado até você confirmar as compras.
        </p>
      </Lead>
      <form className="app-card app-card-padded" onSubmit={submit} aria-busy={busy}>
        {error && <p className="app-error-banner">{error}</p>}
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="contribution-amount">Quanto vai aportar (R$)</label>
            <input
              id="contribution-amount"
              inputMode="decimal"
              value={amount}
              disabled={busy}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="2.000,00"
              required
            />
          </div>
          <div className="app-field">
            <label htmlFor="contribution-strategy">Divisão dentro de cada classe</label>
            <Combobox<IntraClassStrategy | "">
              id="contribution-strategy"
              value={strategy}
              disabled={busy}
              onChange={setStrategy}
              options={[
                { value: "", label: "Como definido na estratégia" },
                ...codeOptions(Object.keys(STRATEGY_LABELS) as IntraClassStrategy[], STRATEGY_LABELS),
              ]}
            />
          </div>
          <button type="submit" className="app-primary-button" disabled={busy}>
            {busy && <Spinner size="sm" />}
            <span>{busy ? "Calculando…" : "Sugerir distribuição"}</span>
          </button>
        </div>
        <p className="app-card-hint">
          O dinheiro vai primeiro para as classes abaixo da banda e, dentro delas, só para ativos elegíveis.
        </p>
      </form>

      <Section title="Planos salvos">
        <Async state={plans}>
          {(list) =>
            list.length === 0 ? (
              <p className="app-muted">Nenhum plano ainda.</p>
            ) : (
              <div className="app-table-wrap">
                <table className="app-table">
                  <thead>
                    <tr>
                      <th>Plano</th>
                      <th>Criado em</th>
                      <th className="app-numeric">Valor</th>
                      <th className="app-numeric">Executado</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((plan) => (
                      <tr key={plan.id}>
                        <td>
                          <Link className="app-link" to={`/contribute/${plan.id}`}>
                            #{plan.id}
                          </Link>
                        </td>
                        <td>{dateTime(plan.created_at)}</td>
                        <td className="app-numeric">{brl(plan.plan.contribution_amount_brl)}</td>
                        <td className="app-numeric">{brl(plan.plan.executed_total_brl)}</td>
                        <td>
                          <Badge tone={plan.status === "CONFIRMED" ? "success" : plan.status === "DRAFT" ? "info" : "neutral"}>
                            {PLAN_STATUS_LABELS[plan.status]}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Async>
      </Section>
    </div>
  );
}

function ClassesStep({
  saved,
  current,
}: Readonly<{ saved: SavedContributionPlanDTO; current: ClassAllocationDTO[] | null }>) {
  const projected = saved.plan.projected_allocations;
  const before = new Map((current ?? []).map((a) => [a.arca_class, a.current_pct]));
  const scale = Math.max(10, ...projected.map((a) => Math.max(a.current_pct, a.target_pct, before.get(a.arca_class) ?? 0))) * 1.1;
  return (
    <Section title="Distribuição por classe" subtitle="Barra azul: peso hoje. Barra laranja: peso depois do aporte. Traço: meta.">
      <BarList
        label="Peso de cada classe antes e depois do aporte"
        bars={projected.map((a) => ({
          id: a.arca_class,
          label: ARCA_LABELS[a.arca_class],
          note: `Recebe ${brl(saved.plan.by_class_allocated_brl[a.arca_class] ?? 0)}`,
          share: (before.get(a.arca_class) ?? 0) / scale,
          second: a.current_pct / scale,
          goal: a.target_pct / scale,
          value: `${points(before.get(a.arca_class) ?? 0)} → ${points(a.current_pct)} · meta ${points(a.target_pct, 0)}`,
        }))}
      />
      {saved.plan.unallocated_cash_brl > 0.009 && (
        <p className="app-warning-banner" style={{ marginTop: "var(--space-3)" }}>
          {brl(saved.plan.unallocated_cash_brl)} ficam sem destino: a classe que precisa de aporte não tem ativo elegível ou
          o valor não compra uma unidade. Cadastre ou pesquise ativos para ela.
        </p>
      )}
    </Section>
  );
}

interface ExecutionDraft {
  include: boolean;
  quantity: string;
  price: string;
  fees: string;
}

function initialExecutions(orders: AssetContributionOrderDTO[]): Record<number, ExecutionDraft> {
  return Object.fromEntries(
    orders.map((o) => [
      o.asset_id,
      {
        include: o.recommended_quantity > 0,
        quantity: String(o.recommended_quantity).replace(".", ","),
        price: String(o.unit_price_brl).replace(".", ","),
        fees: "0",
      },
    ]),
  );
}

function DraftPlan({ saved, onChange }: Readonly<{ saved: SavedContributionPlanDTO; onChange: () => void }>) {
  const navigate = useNavigate();
  const report = useApi("contribution-current", () => api.portfolio.report());
  const accounts = useApi("accounts", () => api.accounts.list());
  const draftKey = `contribute:${saved.id}`;
  const [executions, setExecutions] = useStoredState(`${draftKey}:executions`, initialExecutions(saved.plan.orders));
  const [tradeDate, setTradeDate] = useStoredState(`${draftKey}:date`, today());
  const [accountId, setAccountId] = useStoredState<number | null>(`${draftKey}:account`, null);
  const forgetDraft = () => {
    for (const part of ["executions", "date", "account"]) clearStored(`${draftKey}:${part}`);
  };
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const orders = saved.plan.orders;
  const strategies = strategyByClass(saved);
  const update =(id: number, change: Partial<ExecutionDraft>) =>
    setExecutions((all) => ({ ...all, [id]: { ...all[id], ...change } }));

  const chosen = orders.filter((o) => executions[o.asset_id]?.include);
  // By default only the assets the plan buys are listed; one ticked by hand stays visible.
  const [onlyRecommended, setOnlyRecommended] = useState(true);
  const visible = onlyRecommended
    ? orders.filter((o) => o.recommended_quantity > 0 || executions[o.asset_id]?.include)
    : orders;
  const total = chosen.reduce((sum, o) => {
    const e = executions[o.asset_id];
    return sum + (parseDecimal(e.quantity) ?? 0) * (parseDecimal(e.price) ?? 0) + (parseDecimal(e.fees) ?? 0);
  }, 0);

  const confirm = async () => {
    setError(null);
    const payload = chosen.map((o) => {
      const e = executions[o.asset_id];
      return {
        asset_id: o.asset_id,
        quantity: parseDecimal(e.quantity) ?? 0,
        unit_price: parseDecimal(e.price) ?? 0,
        fees: parseDecimal(e.fees) ?? 0,
      };
    });
    if (payload.length === 0 || payload.some((p) => p.quantity <= 0)) {
      setError("Escolha ao menos um ativo com quantidade maior que zero.");
      return;
    }
    setBusy(true);
    try {
      await api.contributions.confirm(saved.id, { trade_date: tradeDate, account_id: accountId, executions: payload });
      forgetDraft();
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!window.confirm("Descartar este plano?")) return;
    setDiscarding(true);
    try {
      await api.contributions.discard(saved.id);
      forgetDraft();
      navigate("/contribute");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDiscarding(false);
    }
  };

  return (
    <div className="app-page-stack">
      <Steps current={chosen.length > 0 ? 2 : 1} />
      <Lead tone={saved.plan.unallocated_cash_brl > 0.009 ? "caution" : "neutral"}>
        <p>{planStory(saved)}</p>
      </Lead>
      <KpiGrid
        label="Indicadores do plano"
        items={[
          { label: "Aporte", value: brl(saved.plan.contribution_amount_brl) },
          { label: "Compras escolhidas", value: brl(total), note: plural(chosen.length, "ativo", "ativos") },
          {
            label: "Sem destino",
            value: brl(saved.plan.unallocated_cash_brl),
            tone: saved.plan.unallocated_cash_brl > 0.009 ? "caution" : "neutral",
          },
        ]}
      />
      <ClassesStep saved={saved} current={report.data?.allocations ?? null} />
      <PlanRationale saved={saved} />

      <Section
        title="Ativos"
        subtitle="Ajuste quantidade e preço ao que executar na corretora. Ativos em dólar aparecem em R$, ao câmbio do dia."
      >
        {orders.length === 0 ? (
          <Empty title="Nenhum ativo elegível nas classes que recebem o aporte" />
        ) : (
          <>
            <label className="app-check" style={{ marginBottom: "var(--space-3)" }}>
              <input type="checkbox" checked={onlyRecommended} onChange={(ev) => setOnlyRecommended(ev.target.checked)} />
              <span>
                Só os recomendados para comprar ({visible.length} de {orders.length})
              </span>
            </label>
            {visible.length === 0 ? (
              <Empty
                title="O plano não sugere compra em nenhum ativo"
                hint="Desmarque o filtro para escolher entre todos os ativos elegíveis."
              />
            ) : (
              <div className="app-table-wrap">
                <table className="app-table">
                  <thead>
                    <tr>
                      <th>Comprar</th>
                      <th>Ativo</th>
                      <th>Classe</th>
                      <th className="app-numeric">Sugerido</th>
                      <th>Por quê</th>
                      <th>Quantidade</th>
                      <th>Preço (R$)</th>
                      <th>Taxas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((o) => {
                      const e = executions[o.asset_id];
                      const strategy = strategies.get(o.arca_class);
                      return (
                        <tr key={o.asset_id}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Comprar ${o.ticker}`}
                              checked={e.include}
                              disabled={busy || discarding}
                              onChange={(ev) => update(o.asset_id, { include: ev.target.checked })}
                            />
                          </td>
                          <td>
                            <span className="app-cell-main">
                              <Link className="app-link" to={`/asset/${o.asset_id}`}>
                                <strong>{o.ticker}</strong>
                              </Link>
                              <small>{orderWeightText(o, strategy)}</small>
                            </span>
                          </td>
                          <td>{ARCA_LABELS[o.arca_class]}</td>
                          <td className="app-numeric">
                            {quantity(o.recommended_quantity)} × {num(o.unit_price_brl)} = {brl(o.executed_amount_brl)}
                          </td>
                          <td className="contribute-reason">{orderReasonText(o, strategy) || "—"}</td>
                          <td>
                            <input
                              aria-label={`Quantidade de ${o.ticker}`}
                              inputMode="decimal"
                              value={e.quantity}
                              size={8}
                              disabled={busy || discarding || !e.include}
                              onChange={(ev) => update(o.asset_id, { quantity: ev.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              aria-label={`Preço de ${o.ticker}`}
                              inputMode="decimal"
                              value={e.price}
                              size={8}
                              disabled={busy || discarding || !e.include}
                              onChange={(ev) => update(o.asset_id, { price: ev.target.value })}
                            />
                          </td>
                          <td>
                            <input
                              aria-label={`Taxas de ${o.ticker}`}
                              inputMode="decimal"
                              value={e.fees}
                              size={6}
                              disabled={busy || discarding || !e.include}
                              onChange={(ev) => update(o.asset_id, { fees: ev.target.value })}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Section>

      <Section title="Confirmar">
        {error && <p className="app-error-banner">{error}</p>}
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="contribution-date">Data das compras</label>
            <input
              id="contribution-date"
              type="date"
              value={tradeDate}
              disabled={busy || discarding}
              onChange={(e) => setTradeDate(e.target.value)}
            />
          </div>
          <div className="app-field">
            <label htmlFor="contribution-account">Conta</label>
            <Combobox<number | "">
              id="contribution-account"
              value={accountId ?? ""}
              disabled={busy || discarding}
              onChange={(v) => setAccountId(v === "" ? null : v)}
              options={[
                { value: "", label: "Conta padrão" },
                ...(accounts.data ?? []).filter((a) => a.is_active !== false).map((a) => ({ value: a.id, label: a.name })),
              ]}
            />
          </div>
          <div>
            <span className="app-muted">Total das compras</span>
            <div className="home-kpi-value" style={{ fontSize: "var(--text-title)" }}>
              {brl(total)}
            </div>
          </div>
        </div>
        <div className="app-form-actions">
          <button type="button" className="app-primary-button" onClick={() => void confirm()} disabled={busy || discarding}>
            {busy && <Spinner size="sm" />}
            <span>{busy ? "Registrando…" : `Confirmar ${plural(chosen.length, "compra", "compras")}`}</span>
          </button>
          <button type="button" className="app-danger-button" onClick={() => void discard()} disabled={busy || discarding}>
            {discarding && <Spinner size="sm" />}
            <span>{discarding ? "Descartando…" : "Descartar plano"}</span>
          </button>
        </div>
      </Section>
      <Notes items={PLAN_NOTES} />
    </div>
  );
}

function ClosedPlan({ saved }: Readonly<{ saved: SavedContributionPlanDTO }>) {
  return (
    <div className="app-page-stack">
      <div className={saved.status === "CONFIRMED" ? "app-success-banner" : "app-info-banner"}>
        {saved.status === "CONFIRMED"
          ? `Plano confirmado em ${dateTime(saved.confirmed_at)}: ${plural(saved.transaction_ids?.length ?? 0, "compra registrada", "compras registradas")}.`
          : `Plano descartado em ${dateTime(saved.discarded_at)}.`}
        <span className="app-button-row">
          {saved.status === "CONFIRMED" && (
            <Link className="app-secondary-button" to="/ledger">
              Ver lançamentos
            </Link>
          )}
          <Link className="app-primary-button" to="/contribute">
            Novo aporte
          </Link>
        </span>
      </div>
      <ClassesStep saved={saved} current={null} />
      <PlanRationale saved={saved} />
    </div>
  );
}

export function ContributePage() {
  const { planId } = useParams();
  const plan = useApi(`contribution-${planId ?? "new"}`, () =>
    planId ? api.contributions.get(Number(planId)) : Promise.resolve(null),
  );
  return (
    <div className="app-page">
      <PageHeader
        title="Aportar"
        subtitle="Distribua um novo aporte pela estratégia ARCA e registre as compras de uma vez."
      />
      {planId === undefined ? (
        <AmountStep />
      ) : (
        <Async state={plan} lines={6}>
          {(saved) =>
            saved === null ? null : saved.status === "DRAFT" ? (
              <DraftPlan key={saved.id} saved={saved} onChange={plan.reload} />
            ) : (
              <ClosedPlan saved={saved} />
            )
          }
        </Async>
      )}
    </div>
  );
}
