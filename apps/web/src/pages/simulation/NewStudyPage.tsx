/** Novo estudo: what you want to know, the premises once, then review and run (Phase 41.4). */

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { StudyRequest } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { Section } from "../../components/Section";
import { Spinner } from "../../components/States";
import { parseDecimal } from "../../utils/format";
import { clearStored, useStoredState } from "../../utils/storedState";
import { QUESTIONS } from "./shared";

type Question = StudyRequest["question"] & string;
type Benchmark = NonNullable<StudyRequest["benchmarks"]>[number];

export interface StudyForm {
  question: Question;
  label: string;
  monthly: string;
  horizonYears: string;
  wealthGoal: string;
  correctByIpca: boolean;
  pastStart: string;
  policyMode: "CURRENT" | "AS_OF";
  answersMode: "TODAY" | "DATED";
  benchmarks: Benchmark[];
  rebalance: boolean;
  includeScreener: boolean;
  fixedWeight: boolean;
  weightPct: string;
  ruptureStress: boolean;
}

export const INITIAL_STUDY: StudyForm = {
  question: "COMPLETE",
  label: "",
  monthly: "1.000,00",
  horizonYears: "15",
  wealthGoal: "",
  correctByIpca: true,
  pastStart: "2012-01-01",
  policyMode: "CURRENT",
  answersMode: "TODAY",
  benchmarks: ["CDI", "IBOV", "IFIX", "SP500_BRL"],
  rebalance: false,
  includeScreener: true,
  fixedWeight: false,
  weightPct: "5",
  ruptureStress: false,
};

const BENCHMARKS: Array<[Benchmark, string]> = [
  ["CDI", "CDI"],
  ["IBOV", "Ibovespa"],
  ["IFIX", "IFIX"],
  ["SP500_BRL", "S&P 500 (R$)"],
];

const STORE_KEY = "simulation:new-study";

/** The API request, or the first problem to fix in the form. */
export function toStudyRequest(form: StudyForm): StudyRequest | string {
  const label = form.label.trim();
  if (!label) return "Dê um nome ao estudo.";
  const monthly = parseDecimal(form.monthly);
  if (monthly === null || monthly <= 0) return "Informe um aporte mensal maior que zero.";
  const years = Number.parseInt(form.horizonYears, 10);
  if (!Number.isFinite(years) || years < 1 || years > 30) return "Informe um horizonte de 1 a 30 anos.";
  const goal = parseDecimal(form.wealthGoal);
  const weight = parseDecimal(form.weightPct);
  return {
    label,
    question: form.question,
    monthly_contribution: monthly,
    horizon_years: years,
    wealth_goal: goal !== null && goal > 0 ? goal : null,
    correct_by_ipca: form.correctByIpca,
    past_start: form.pastStart || null,
    policy_mode: form.policyMode,
    answers_mode: form.answersMode,
    benchmarks: form.benchmarks.length ? form.benchmarks : ["CDI"],
    rebalance: form.rebalance,
    include_screener: form.includeScreener,
    weight_mode: form.fixedWeight ? "FIXED" : "NEXT_CONTRIBUTION",
    fixed_weight: weight !== null && weight > 0 ? weight / 100 : 0.05,
    rupture_stress: form.ruptureStress,
  };
}

/** What will be computed, in order, for the review step. */
export function reviewItems(form: StudyForm): Array<{ title: string; text: string; time: string }> {
  const chapters = QUESTIONS.find((q) => q.key === form.question)?.chapters ?? [];
  const items: Array<{ title: string; text: string; time: string }> = [];
  if (chapters.includes("De onde viemos")) {
    items.push({
      title: "De onde viemos",
      text: `suas regras de ${form.pastStart.slice(0, 4)} a hoje com ${form.monthly}/mês, comparadas com o mesmo fluxo nas referências, mais o teste de robustez (crises, choques e variantes de regra).`,
      time: "~20 s",
    });
  }
  if (chapters.includes("Para onde vamos")) {
    items.push({
      title: "Para onde vamos",
      text: `milhares de futuros possíveis em ${form.horizonYears} anos${form.wealthGoal ? ", a chance de chegar à meta" : ""} e o selo de confiança da última calibração.`,
      time: "~15 s",
    });
  }
  if (chapters.includes("O que pode melhorar")) {
    items.push({
      title: "O que pode melhorar",
      text: `até 20 candidatos da observação${form.includeScreener ? " e do screener" : ""}, cada um posto nas mesmas premissas do capítulo anterior.`,
      time: "~30 s, depois do anterior",
    });
  }
  return items;
}

const STEPS = ["O que você quer saber", "Premissas", "Revisar e rodar"];

export function NewStudyPage() {
  const navigate = useNavigate();
  const [form, setForm] = useStoredState<StudyForm>(STORE_KEY, INITIAL_STUDY);
  const [step, setStep] = useStoredState(`${STORE_KEY}:step`, 0);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (change: Partial<StudyForm>) => setForm((f) => ({ ...f, ...change }));
  const chosen = QUESTIONS.find((q) => q.key === form.question) ?? QUESTIONS[0];
  const hasPast = chosen.chapters.includes("De onde viemos");
  const hasImprove = chosen.chapters.includes("O que pode melhorar");

  const next = (event?: FormEvent) => {
    event?.preventDefault();
    if (step === 1) {
      const checked = toStudyRequest(form);
      if (typeof checked === "string") {
        setError(checked);
        return;
      }
    }
    setError(null);
    setStep((s) => Math.min(s + 1, 2));
  };

  const run = async () => {
    const body = toStudyRequest(form);
    if (typeof body === "string") {
      setError(body);
      setStep(1);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const study = await api.studies.create(body);
      clearStored(STORE_KEY);
      clearStored(`${STORE_KEY}:step`);
      navigate(`/tools/simulation/${study.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page">
      <PageHeader title="Novo estudo" subtitle="Três passos. As premissas valem para todos os capítulos do estudo." />
      <div className="app-page-stack">
        <ol className="app-steps" aria-label="Etapas do estudo">
          {STEPS.map((label, i) => (
            <li key={label} className={`app-step${i < step ? " is-done" : ""}`} aria-current={i === step ? "step" : undefined}>
              <b>{i + 1}</b>
              {label}
            </li>
          ))}
        </ol>
        {error && (
          <p className="app-error-banner" role="alert">
            {error}
          </p>
        )}

        {step === 0 && (
          <Section title="O que você quer saber?" subtitle="Cada pergunta define os capítulos do estudo.">
            <fieldset className="study-questions">
              <legend className="app-visually-hidden">Pergunta do estudo</legend>
              {QUESTIONS.map((q) => (
                <label key={q.key} className={`study-question${form.question === q.key ? " is-selected" : ""}`}>
                  <input type="radio" name="study-question" value={q.key} checked={form.question === q.key} onChange={() => set({ question: q.key })} />
                  <span className="study-question-body">
                    <strong>{q.label}</strong>
                    <span className="app-muted">{q.hint}</span>
                    <span className="study-chips">
                      {q.chapters.map((c) => (
                        <span key={c} className="study-chip">
                          {c}
                        </span>
                      ))}
                    </span>
                  </span>
                </label>
              ))}
            </fieldset>
            <div className="app-form-actions">
              <button type="button" className="app-primary-button" onClick={() => next()}>
                Premissas →
              </button>
            </div>
          </Section>
        )}

        {step === 1 && (
          <form onSubmit={next} aria-label="Premissas do estudo">
            <Section title="Premissas" subtitle="Definidas uma vez: o capítulo dos candidatos usa exatamente as premissas da projeção.">
              <fieldset className="app-field-grid">
                <legend>Você e a sua meta</legend>
                <div className="app-field">
                  <label htmlFor="study-label">Nome do estudo</label>
                  <input id="study-label" value={form.label} maxLength={120} placeholder="Ex.: Aposentadoria 2040" onChange={(e) => set({ label: e.target.value })} />
                </div>
                <div className="app-field">
                  <label htmlFor="study-monthly">Aporte mensal (R$)</label>
                  <input id="study-monthly" inputMode="decimal" value={form.monthly} onChange={(e) => set({ monthly: e.target.value })} />
                </div>
                <div className="app-field">
                  <label htmlFor="study-years">Horizonte (anos)</label>
                  <input id="study-years" inputMode="numeric" value={form.horizonYears} onChange={(e) => set({ horizonYears: e.target.value })} />
                </div>
                <div className="app-field">
                  <label htmlFor="study-goal">Meta de patrimônio (R$, opcional)</label>
                  <input id="study-goal" inputMode="decimal" value={form.wealthGoal} onChange={(e) => set({ wealthGoal: e.target.value })} />
                </div>
              </fieldset>
              <label className="app-check">
                <input type="checkbox" checked={form.correctByIpca} onChange={(e) => set({ correctByIpca: e.target.checked })} />
                Reajustar o aporte pelo IPCA todo ano
              </label>

              {hasPast && (
                <fieldset className="app-field-grid">
                  <legend>O passado (De onde viemos)</legend>
                  <div className="app-field">
                    <label htmlFor="study-start">Desde</label>
                    <input id="study-start" type="date" value={form.pastStart} onChange={(e) => set({ pastStart: e.target.value })} />
                  </div>
                  <div className="app-field">
                    <label htmlFor="study-policy">Regras aplicadas</label>
                    <select id="study-policy" value={form.policyMode} onChange={(e) => set({ policyMode: e.target.value as StudyForm["policyMode"] })}>
                      <option value="CURRENT">As de hoje, no período inteiro</option>
                      <option value="AS_OF">As vigentes em cada data</option>
                    </select>
                  </div>
                  <div className="app-field">
                    <label htmlFor="study-answers">Checklist no passado</label>
                    <select id="study-answers" value={form.answersMode} onChange={(e) => set({ answersMode: e.target.value as StudyForm["answersMode"] })}>
                      <option value="TODAY">As respostas de hoje valem no período inteiro</option>
                      <option value="DATED">Cada resposta vale a partir da data em que foi dada</option>
                    </select>
                  </div>
                </fieldset>
              )}
              {hasPast && form.answersMode === "TODAY" && (
                <p className="app-warning-banner" role="note">
                  Suas respostas do checklist são recentes. Para o passado, as de hoje valem no período inteiro, e o capítulo avisa
                  que isso usa uma informação que não existia na época. Sem isso, quase todo aporte iria para o Caixa.
                </p>
              )}

              <details className="app-disclosure">
                <summary>Avançado: referências, bandas{hasImprove ? ", candidatos" : ""} e estresse</summary>
                <div className="app-disclosure-body">
                  <fieldset className="app-check-row">
                    <legend>Referências</legend>
                    {BENCHMARKS.map(([key, label]) => (
                      <label key={key} className="app-check">
                        <input
                          type="checkbox"
                          checked={form.benchmarks.includes(key)}
                          onChange={(e) =>
                            set({ benchmarks: e.target.checked ? [...form.benchmarks, key] : form.benchmarks.filter((b) => b !== key) })
                          }
                        />
                        {label}
                      </label>
                    ))}
                  </fieldset>
                  <label className="app-check">
                    <input type="checkbox" checked={form.rebalance} onChange={(e) => set({ rebalance: e.target.checked })} />
                    Rebalancear as classes acima da banda
                  </label>
                  {hasImprove && (
                    <>
                      <label className="app-check">
                        <input type="checkbox" checked={form.includeScreener} onChange={(e) => set({ includeScreener: e.target.checked })} />
                        Incluir os mais negociados do screener
                      </label>
                      <label className="app-check">
                        <input type="checkbox" checked={form.fixedWeight} onChange={(e) => set({ fixedWeight: e.target.checked })} />
                        Usar um peso fixo para o candidato
                      </label>
                      {form.fixedWeight && (
                        <div className="app-field">
                          <label htmlFor="study-weight">Peso do candidato na carteira (%)</label>
                          <input id="study-weight" inputMode="decimal" value={form.weightPct} onChange={(e) => set({ weightPct: e.target.value })} />
                        </div>
                      )}
                      <label className="app-check">
                        <input type="checkbox" checked={form.ruptureStress} onChange={(e) => set({ ruptureStress: e.target.checked })} />
                        Ruptura em estresse (perda de 90% em vez de 55%)
                      </label>
                    </>
                  )}
                </div>
              </details>
              <div className="app-form-actions">
                <button type="button" className="app-secondary-button" onClick={() => setStep(0)}>
                  ← Passo anterior
                </button>
                <button type="submit" className="app-primary-button">
                  Revisar →
                </button>
              </div>
            </Section>
          </form>
        )}

        {step === 2 && (
          <Section title="O que vai ser calculado" subtitle={`${form.label} · ${chosen.label}`}>
            <ol className="study-review">
              {reviewItems(form).map((item) => (
                <li key={item.title}>
                  <strong>{item.title}</strong>: {item.text} <span className="app-muted">{item.time}</span>
                </li>
              ))}
            </ol>
            <div className="app-form-actions">
              <button type="button" className="app-secondary-button" onClick={() => setStep(1)} disabled={saving}>
                ← Premissas
              </button>
              <button type="button" className="app-primary-button" onClick={() => void run()} disabled={saving}>
                {saving && <Spinner size="sm" />}
                <span>{saving ? "Enviando…" : "Rodar estudo"}</span>
              </button>
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
