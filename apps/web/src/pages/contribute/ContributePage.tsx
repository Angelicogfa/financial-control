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
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty } from "../../components/States";
import { brl, dateTime, num, parseDecimal, points, quantity, today } from "../../utils/format";
import { ARCA_LABELS, PLAN_STATUS_LABELS, STRATEGY_LABELS } from "../../utils/labels";
import { BarList } from "../../viz/BarList";

const STEPS = ["Valor", "Classes", "Ativos", "Confirmar"];

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
      <form className="app-card app-card-padded" onSubmit={submit}>
        {error && <p className="app-error-banner">{error}</p>}
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="contribution-amount">Quanto vai aportar (R$)</label>
            <input
              id="contribution-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="2.000,00"
              required
            />
          </div>
          <div className="app-field">
            <label htmlFor="contribution-strategy">Divisão dentro de cada classe</label>
            <select
              id="contribution-strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as IntraClassStrategy | "")}
            >
              <option value="">Como definido na estratégia</option>
              {(Object.keys(STRATEGY_LABELS) as IntraClassStrategy[]).map((s) => (
                <option key={s} value={s}>
                  {STRATEGY_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="app-primary-button" disabled={busy}>
            {busy ? "Calculando…" : "Sugerir distribuição"}
          </button>
        </div>
        <p className="app-card-hint" style={{ margin: "var(--space-3) 0 0" }}>
          O dinheiro vai primeiro para as classes abaixo da banda e, dentro delas, só para ativos elegíveis.
        </p>
      </form>

      <section>
        <h2 className="app-card-heading">Planos salvos</h2>
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
      </section>
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
    <section className="app-card app-card-padded">
      <h2 className="app-card-heading">Distribuição por classe</h2>
      <p className="app-card-hint">Barra azul: peso hoje. Barra laranja: peso depois do aporte. Traço: meta.</p>
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
    </section>
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
  const [executions, setExecutions] = useState(() => initialExecutions(saved.plan.orders));
  const [tradeDate, setTradeDate] = useState(today());
  const [accountId, setAccountId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const orders = saved.plan.orders;
  const update = (id: number, change: Partial<ExecutionDraft>) =>
    setExecutions((all) => ({ ...all, [id]: { ...all[id], ...change } }));

  const chosen = orders.filter((o) => executions[o.asset_id]?.include);
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
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!window.confirm("Descartar este plano?")) return;
    try {
      await api.contributions.discard(saved.id);
      navigate("/contribute");
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div className="app-page-stack">
      <Steps current={chosen.length > 0 ? 2 : 1} />
      <ClassesStep saved={saved} current={report.data?.allocations ?? null} />

      <section>
        <h2 className="app-card-heading">Ativos</h2>
        <p className="app-card-hint">
          Ajuste quantidade e preço para o que executar de fato na corretora. Preços de ativos em dólar ficam em R$ aqui;
          a conversão usa o câmbio do dia.
        </p>
        {orders.length === 0 ? (
          <Empty title="Nenhum ativo elegível nas classes que recebem o aporte" />
        ) : (
          <div className="app-table-wrap">
            <table className="app-table">
              <thead>
                <tr>
                  <th>Comprar</th>
                  <th>Ativo</th>
                  <th>Classe</th>
                  <th className="app-numeric">Sugerido</th>
                  <th>Quantidade</th>
                  <th>Preço (R$)</th>
                  <th>Taxas</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => {
                  const e = executions[o.asset_id];
                  return (
                    <tr key={o.asset_id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Comprar ${o.ticker}`}
                          checked={e.include}
                          onChange={(ev) => update(o.asset_id, { include: ev.target.checked })}
                        />
                      </td>
                      <td>
                        <span className="app-cell-main">
                          <strong>{o.ticker}</strong>
                          <small>Peso alvo {points(o.intra_class_target_weight_pct)} na classe</small>
                        </span>
                      </td>
                      <td>{ARCA_LABELS[o.arca_class]}</td>
                      <td className="app-numeric">
                        {quantity(o.recommended_quantity)} × {num(o.unit_price_brl)} = {brl(o.executed_amount_brl)}
                      </td>
                      <td>
                        <input
                          aria-label={`Quantidade de ${o.ticker}`}
                          inputMode="decimal"
                          value={e.quantity}
                          size={8}
                          disabled={!e.include}
                          onChange={(ev) => update(o.asset_id, { quantity: ev.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Preço de ${o.ticker}`}
                          inputMode="decimal"
                          value={e.price}
                          size={8}
                          disabled={!e.include}
                          onChange={(ev) => update(o.asset_id, { price: ev.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Taxas de ${o.ticker}`}
                          inputMode="decimal"
                          value={e.fees}
                          size={6}
                          disabled={!e.include}
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
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Confirmar</h2>
        {error && <p className="app-error-banner">{error}</p>}
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="contribution-date">Data das compras</label>
            <input id="contribution-date" type="date" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} />
          </div>
          <div className="app-field">
            <label htmlFor="contribution-account">Conta</label>
            <select
              id="contribution-account"
              value={accountId ?? ""}
              onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Conta padrão</option>
              {(accounts.data ?? []).filter((a) => a.is_active !== false).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <span className="app-muted">Total das compras</span>
            <div className="home-kpi-value" style={{ fontSize: "var(--text-title)" }}>
              {brl(total)}
            </div>
          </div>
        </div>
        <div className="app-form-actions">
          <button type="button" className="app-primary-button" onClick={() => void confirm()} disabled={busy}>
            {busy ? "Registrando…" : `Confirmar ${chosen.length} compra(s)`}
          </button>
          <button type="button" className="app-danger-button" onClick={() => void discard()}>
            Descartar plano
          </button>
        </div>
      </section>
    </div>
  );
}

function ClosedPlan({ saved }: Readonly<{ saved: SavedContributionPlanDTO }>) {
  return (
    <div className="app-page-stack">
      <div className={saved.status === "CONFIRMED" ? "app-success-banner" : "app-info-banner"}>
        {saved.status === "CONFIRMED"
          ? `Plano confirmado em ${dateTime(saved.confirmed_at)}: ${saved.transaction_ids?.length ?? 0} compra(s) registradas.`
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
