import { useState, type FormEvent } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { ArcaClass, IntraClassStrategy, PolicyDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Hint } from "../../components/Hint";
import { PageHeader } from "../../components/PageHeader";
import { Async, Spinner } from "../../components/States";
import { dateTime, parseDecimal } from "../../utils/format";
import { ARCA_CLASSES, ARCA_LABELS, STRATEGY_LABELS } from "../../utils/labels";

/** Fields edited as percentages but stored as fractions (ADR 0006). */
const VALUATION_FIELDS: Array<{ key: string; label: string; percent: boolean; hint: string }> = [
  { key: "bazin_required_yield", label: "Yield exigido (Bazin)", percent: true, hint: "Dividendo mínimo para o preço teto." },
  { key: "graham_multiplier", label: "Multiplicador de Graham", percent: false, hint: "22,5 = P/L 15 × P/VP 1,5." },
  { key: "max_price_to_earnings", label: "P/L máximo", percent: false, hint: "Ações." },
  { key: "max_ev_to_ebitda", label: "EV/EBITDA máximo", percent: false, hint: "Ações." },
  { key: "max_price_to_book_bank", label: "P/VP máximo de bancos", percent: false, hint: "" },
  { key: "bank_cost_of_equity", label: "Custo de capital de bancos", percent: true, hint: "Para o P/VP justificado." },
  { key: "max_price_to_book_fii", label: "P/VP máximo de FIIs", percent: false, hint: "" },
  { key: "reference_real_yield", label: "Juro real de referência (NTN-B)", percent: true, hint: "Base do spread dos FIIs." },
  { key: "min_fii_spread", label: "Spread mínimo de FIIs", percent: true, hint: "DY acima do juro real." },
  { key: "min_margin_of_safety", label: "Margem de segurança", percent: true, hint: "Para considerar descontado." },
];

const PROJECTION_FIELDS: Array<{ key: string; label: string; percent: boolean }> = [
  { key: "equity_capital_growth_rate", label: "Valorização anual de ações", percent: true },
  { key: "fund_capital_growth_rate", label: "Valorização anual de fundos", percent: true },
  { key: "real_estate_default_yield_rate", label: "Yield padrão de FIIs", percent: true },
  { key: "cash_cdi_multiplier", label: "Caixa rende (% do CDI)", percent: true },
  { key: "cash_income_tax_rate", label: "IR do caixa", percent: true },
  { key: "projected_cdi_rate", label: "CDI projetado no comparador (vazio = mercado)", percent: true },
  { key: "projected_ipca_rate", label: "IPCA projetado no comparador (vazio = mercado)", percent: true },
  { key: "scenario_rate_shift", label: "Variação dos cenários de juros", percent: true },
];

interface ClassRow {
  target: string;
  band: string;
  strategy: IntraClassStrategy;
}

const toText = (value: number | undefined, percent: boolean) =>
  value === undefined || value === null ? "" : String(Math.round((percent ? value * 100 : value) * 10000) / 10000).replace(".", ",");

function StrategyForm({ policy, onSaved }: Readonly<{ policy: PolicyDTO; onSaved: () => void }>) {
  const [classes, setClasses] = useState<Record<ArcaClass, ClassRow>>(() =>
    Object.fromEntries(
      ARCA_CLASSES.map((c) => {
        const row = policy.arca.find((a) => a.arca_class === c);
        return [
          c,
          {
            target: toText(row?.target_pct ?? 0, false),
            band: toText(row?.band_pct ?? 5, false),
            strategy: row?.intra_class_strategy ?? "CERRADO",
          },
        ];
      }),
    ) as Record<ArcaClass, ClassRow>,
  );
  const eligibility = policy.eligibility ?? {};
  const [requireEvaluation, setRequireEvaluation] = useState(eligibility.require_evaluation ?? false);
  const [minScore, setMinScore] = useState(String(eligibility.min_score ?? 1));
  const [minCoverage, setMinCoverage] = useState(String(eligibility.min_coverage_pct ?? 0));
  const valuation = (policy.valuation ?? {}) as Record<string, number | undefined>;
  const projections = (policy.valuation?.projections ?? {}) as Record<string, number | undefined>;
  const [valuationText, setValuationText] = useState<Record<string, string>>(() =>
    Object.fromEntries(VALUATION_FIELDS.map((f) => [f.key, toText(valuation[f.key], f.percent)])),
  );
  const [projectionText, setProjectionText] = useState<Record<string, string>>(() =>
    Object.fromEntries(PROJECTION_FIELDS.map((f) => [f.key, toText(projections[f.key], f.percent)])),
  );
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const total = ARCA_CLASSES.reduce((sum, c) => sum + (parseDecimal(classes[c].target) ?? 0), 0);
  const totalOk = Math.abs(total - 100) < 0.01;
  const setClass = (c: ArcaClass, change: Partial<ClassRow>) =>
    setClasses((all) => ({ ...all, [c]: { ...all[c], ...change } }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!totalOk) {
      setMessage({ ok: false, text: "As metas das classes precisam somar 100%." });
      return;
    }
    const read = (fields: Array<{ key: string; percent: boolean }>, text: Record<string, string>) =>
      Object.fromEntries(
        fields
          .map((f) => [f.key, parseDecimal(text[f.key])] as const)
          .filter(([, v]) => v !== null)
          .map(([key, v]) => [key, fields.find((f) => f.key === key)?.percent ? (v as number) / 100 : v]),
      );
    setSaving(true);
    setMessage(null);
    try {
      await api.policy.save({
        arca: ARCA_CLASSES.map((c) => ({
          arca_class: c,
          target_pct: parseDecimal(classes[c].target) ?? 0,
          band_pct: parseDecimal(classes[c].band) ?? 0,
          intra_class_strategy: classes[c].strategy,
        })),
        eligibility: {
          require_evaluation: requireEvaluation,
          min_score: Math.round(parseDecimal(minScore) ?? 0),
          min_coverage_pct: parseDecimal(minCoverage) ?? 0,
        },
        valuation: { ...read(VALUATION_FIELDS, valuationText), projections: read(PROJECTION_FIELDS, projectionText) },
      });
      onSaved();
    } catch (err) {
      setMessage({ ok: false, text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="app-page-stack" onSubmit={submit} aria-busy={saving}>
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Alocação ARCA</h2>
        <p className="app-card-hint">
          Meta de cada classe, banda de tolerância (pontos percentuais) e como o aporte se divide dentro dela.
        </p>
        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Classe</th>
                <th>Meta (%)</th>
                <th>Banda (± p.p.)</th>
                <th>Divisão interna</th>
              </tr>
            </thead>
            <tbody>
              {ARCA_CLASSES.map((c) => (
                <tr key={c}>
                  <td>{ARCA_LABELS[c]}</td>
                  <td>
                    <input
                      aria-label={`Meta de ${ARCA_LABELS[c]}`}
                      inputMode="decimal"
                      size={6}
                      value={classes[c].target}
                      disabled={saving}
                      onChange={(e) => setClass(c, { target: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`Banda de ${ARCA_LABELS[c]}`}
                      inputMode="decimal"
                      size={6}
                      value={classes[c].band}
                      disabled={saving}
                      onChange={(e) => setClass(c, { band: e.target.value })}
                    />
                  </td>
                  <td>
                    <select
                      aria-label={`Divisão interna de ${ARCA_LABELS[c]}`}
                      value={classes[c].strategy}
                      disabled={saving}
                      onChange={(e) => setClass(c, { strategy: e.target.value as IntraClassStrategy })}
                    >
                      {(Object.keys(STRATEGY_LABELS) as IntraClassStrategy[]).map((s) => (
                        <option key={s} value={s}>
                          {STRATEGY_LABELS[s]}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
              <tr>
                <td>
                  <strong>Total</strong>
                </td>
                <td colSpan={3} className={totalOk ? "app-positive" : "app-negative"}>
                  {total.toLocaleString("pt-BR")}%{totalOk ? "" : " — precisa somar 100%"}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Elegibilidade (fundamentalista)</h2>
        <p className="app-card-hint">Quando um ativo pode receber aportes.</p>
        <div className="app-field-grid">
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="policy-min-score">Nota mínima do checklist</label>
              <Hint about="Nota mínima do checklist">Sim = +1, Não = −1.</Hint>
            </span>
            <input id="policy-min-score" inputMode="numeric" value={minScore} disabled={saving} onChange={(e) => setMinScore(e.target.value)} />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="policy-coverage">Cobertura mínima (%)</label>
              <Hint about="Cobertura mínima">Parte das perguntas aplicáveis respondida.</Hint>
            </span>
            <input id="policy-coverage" inputMode="decimal" value={minCoverage} disabled={saving} onChange={(e) => setMinCoverage(e.target.value)} />
          </div>
          <label className="app-check">
            <input type="checkbox" checked={requireEvaluation} disabled={saving} onChange={(e) => setRequireEvaluation(e.target.checked)} />
            Exigir checklist respondido para aportar
          </label>
        </div>
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Valuation</h2>
        <div className="app-field-grid">
          {VALUATION_FIELDS.map((f) => (
            <div key={f.key} className="app-field">
              <span className="app-field-label">
                <label htmlFor={`valuation-${f.key}`}>
                  {f.label}
                  {f.percent ? " (%)" : ""}
                </label>
                {f.hint && <Hint about={f.label}>{f.hint}</Hint>}
              </span>
              <input
                id={`valuation-${f.key}`}
                inputMode="decimal"
                value={valuationText[f.key]}
                disabled={saving}
                onChange={(e) => setValuationText((all) => ({ ...all, [f.key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </section>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Premissas de projeção (12 meses)</h2>
        <div className="app-field-grid">
          {PROJECTION_FIELDS.map((f) => (
            <div key={f.key} className="app-field">
              <label htmlFor={`projection-${f.key}`}>{f.label} (%)</label>
              <input
                id={`projection-${f.key}`}
                inputMode="decimal"
                value={projectionText[f.key]}
                disabled={saving}
                onChange={(e) => setProjectionText((all) => ({ ...all, [f.key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </section>

      {message && <p className={message.ok ? "app-success-banner" : "app-error-banner"}>{message.text}</p>}
      <div className="app-button-row">
        <button type="submit" className="app-primary-button" disabled={saving}>
          {saving && <Spinner size="sm" />}
          <span>{saving ? "Salvando…" : "Salvar nova versão"}</span>
        </button>
        <span className="app-muted">
          Versão atual: {policy.version ?? "padrão"}
          {policy.created_at ? ` de ${dateTime(policy.created_at)}` : ""}. Salvar cria uma nova versão; as anteriores ficam no
          histórico.
        </span>
      </div>
    </form>
  );
}

export function StrategyPage() {
  const [saved, setSaved] = useState(false);
  const policy = useApi("policy", () => api.policy.current());
  const versions = useApi("policy-versions", () => api.policy.versions());
  return (
    <div className="app-page">
      <PageHeader
        title="Estratégia"
        subtitle="As regras que a carteira, a pesquisa e o aporte seguem: ARCA, elegibilidade e valuation."
      />
      {saved && (
        <p className="app-success-banner" role="status" style={{ marginBottom: "var(--space-4)" }}>
          Nova versão da estratégia salva.
        </p>
      )}
      <Async state={policy} lines={8}>
        {(data) => (
          <StrategyForm
            key={data.version ?? 0}
            policy={data}
            onSaved={() => {
              setSaved(true);
              policy.reload();
              versions.reload();
            }}
          />
        )}
      </Async>
      <details className="app-card app-card-padded" style={{ marginTop: "var(--space-4)" }}>
        <summary>Versões anteriores</summary>
        <Async state={versions}>
          {(list) => (
            <ul>
              {list.map((v) => (
                <li key={v.version ?? 0}>
                  Versão {v.version} — {dateTime(v.created_at)} —{" "}
                  {v.arca.map((a) => `${ARCA_LABELS[a.arca_class]} ${a.target_pct}%`).join(", ")}
                </li>
              ))}
            </ul>
          )}
        </Async>
      </details>
    </div>
  );
}
