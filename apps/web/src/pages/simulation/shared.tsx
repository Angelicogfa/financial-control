/** Pieces shared by the study screens (Phase 41): seal, status and the premises in words. */

import type { StudyDTO, StudySealDTO, StudySummaryDTO } from "../../api/types";
import { Badge } from "../../components/Badge";
import { brl, day } from "../../utils/format";

export type StudyStatus = StudyDTO["status"];

const STATUS: Record<StudyStatus, { label: string; tone: string }> = {
  PENDING: { label: "Na fila", tone: "info" },
  RUNNING: { label: "Rodando", tone: "info" },
  DONE: { label: "Pronto", tone: "success" },
  PARTIAL: { label: "Parcial", tone: "warning" },
  FAILED: { label: "Falhou", tone: "danger" },
};

export function isStudyActive(status: StudyStatus): boolean {
  return status === "PENDING" || status === "RUNNING";
}

export function StudyStatusBadge({ status }: Readonly<{ status: StudyStatus }>) {
  return <Badge tone={STATUS[status].tone}>{STATUS[status].label}</Badge>;
}

export const QUESTIONS: Array<{ key: "COMPLETE" | "PAST" | "GOAL" | "IMPROVE"; label: string; chapters: string[]; hint: string }> = [
  {
    key: "COMPLETE",
    label: "Estudo completo",
    chapters: ["De onde viemos", "Para onde vamos", "O que pode melhorar"],
    hint: "Minhas regras funcionaram, vou chegar à meta e o que acrescentar. Recomendado.",
  },
  { key: "PAST", label: "Minhas regras teriam funcionado?", chapters: ["De onde viemos"], hint: "Só o passado, com a robustez." },
  { key: "GOAL", label: "Vou chegar à minha meta?", chapters: ["Para onde vamos"], hint: "Só o futuro, com a confiança das chances." },
  {
    key: "IMPROVE",
    label: "O que acrescentar à carteira?",
    chapters: ["Para onde vamos", "O que pode melhorar"],
    hint: "O futuro e os candidatos sobre as mesmas trajetórias.",
  },
];

/** "●●●○ Confiável": the four-level seal, with its reason. */
export function SealBox({ title, seal, children }: Readonly<{ title: string; seal: StudySealDTO | null | undefined; children?: React.ReactNode }>) {
  if (!seal) return null;
  const dots = "●".repeat(seal.level) + "○".repeat(4 - seal.level);
  return (
    <aside className="study-seal" aria-label={title}>
      <div className="study-seal-head">
        <span className="app-eyebrow">{title}</span>
        {seal.level > 0 && (
          <span className="study-seal-dots" aria-label={`Confiança ${seal.level} de 4`}>
            {dots}
          </span>
        )}
        <strong>{seal.label}</strong>
      </div>
      <p className="study-seal-text">{seal.text}</p>
      {children}
    </aside>
  );
}

/** The premises as one line: "R$ 1.500,00/mês reajustado pelo IPCA · 15 anos · meta R$ 1,2 mi". */
export function premisesLine(premises: Record<string, unknown>): string {
  const parts: string[] = [];
  const monthly = Number(premises.monthly_contribution ?? 0);
  if (monthly > 0) parts.push(`${brl(monthly)}/mês${premises.correct_by_ipca ? " reajustado pelo IPCA" : ""}`);
  if (premises.horizon_years) parts.push(`${premises.horizon_years} anos`);
  if (premises.wealth_goal) parts.push(`meta ${brl(Number(premises.wealth_goal))}`);
  if (premises.past_start) parts.push(`passado desde ${day(String(premises.past_start))}`);
  return parts.join(" · ");
}

export function goalText(study: Pick<StudySummaryDTO, "goal_probability" | "goal_target">): string | null {
  if (study.goal_probability == null) return null;
  return `${Math.round(study.goal_probability * 100)}%`;
}

/** A change of probability in percentage points: "+6 p.p.". */
export function ppText(change: number): string {
  const value = Math.round(change * 100);
  return `${value > 0 ? "+" : ""}${value} p.p.`;
}
