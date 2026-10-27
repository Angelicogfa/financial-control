import { useState } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  AnswerValue,
  AssetAnalysisResponseDTO,
  ChecklistProfile,
  EvaluatedAnswerDTO,
} from "../../api/types";
import { Badge } from "../../components/Badge";
import { Spinner } from "../../components/States";
import { dateTime, points } from "../../utils/format";
import { ANSWER_LABELS, PROFILE_LABELS, PROFILES, RECOMMENDATION_LABELS } from "../../utils/labels";
import { Sparkline } from "../../viz/Sparkline";

interface Draft {
  value: AnswerValue | null;
  evidence: string;
}

function initialDrafts(answers: EvaluatedAnswerDTO[]): Record<string, Draft> {
  return Object.fromEntries(
    answers.map((a) => [
      a.question_id,
      { value: a.source === "MANUAL" ? a.value : null, evidence: a.source === "MANUAL" ? (a.evidence ?? "") : "" },
    ]),
  );
}

/** Checklist v2: manual answers (YES/NO/NA with evidence) override automatic ones, which
 *  show the evidence computed from the statements (items 11.3, 11.4). */
export function ChecklistTab({
  analysis,
  onSaved,
}: Readonly<{ analysis: AssetAnalysisResponseDTO; onSaved: () => void }>) {
  const { asset, checklist } = analysis;
  const [profile, setProfile] = useState<ChecklistProfile>(asset.checklist_profile);
  const [enabled, setEnabled] = useState(asset.use_cerrado);
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => initialDrafts(checklist.answers));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const profileChanged = profile !== asset.checklist_profile;

  const setAnswer = (id: string, value: AnswerValue | null) =>
    setDrafts((current) => ({ ...current, [id]: { ...current[id], value } }));
  const setEvidence = (id: string, evidence: string) =>
    setDrafts((current) => ({ ...current, [id]: { ...current[id], evidence } }));

  const save = async () => {
    setSaving(true);
    setMessage(null);
    const answers = Object.fromEntries(
      Object.entries(drafts)
        .filter(([, d]) => d.value !== null)
        .map(([id, d]) => [id, d.value]),
    );
    const evidence = Object.fromEntries(
      Object.entries(drafts)
        .filter(([, d]) => d.value !== null && d.evidence.trim())
        .map(([id, d]) => [id, d.evidence.trim()]),
    );
    try {
      await api.assets.checklist(asset.id, {
        use_cerrado: enabled,
        checklist_profile: profile,
        cerrado_answers: answers,
        evidence,
      });
      onSaved();
    } catch (err) {
      setMessage({ ok: false, text: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  const history = analysis.checklist_history ?? [];

  return (
    <div className="app-page-stack">
      <section className="app-card app-card-padded">
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="checklist-profile">Perfil do checklist</label>
            <select
              id="checklist-profile"
              value={profile}
              disabled={saving}
              onChange={(e) => setProfile(e.target.value as ChecklistProfile)}
            >
              {PROFILES.map((p) => (
                <option key={p} value={p}>
                  {PROFILE_LABELS[p]}
                </option>
              ))}
            </select>
          </div>
          <label className="app-check">
            <input type="checkbox" checked={enabled} disabled={saving} onChange={(e) => setEnabled(e.target.checked)} />
            Usar o checklist na elegibilidade e nos pesos
          </label>
          <div>
            <strong>
              Nota {checklist.score > 0 ? "+" : ""}
              {checklist.score}
            </strong>{" "}
            <span className="app-muted">
              · cobertura {points(checklist.coverage_pct, 0)} · {checklist.applicable} aplicáveis ·{" "}
              {RECOMMENDATION_LABELS[checklist.recommendation] ?? checklist.recommendation}
            </span>
          </div>
        </div>
        {profileChanged && (
          <p className="app-info-banner" style={{ marginTop: "var(--space-3)" }}>
            Salve para ver as perguntas do perfil {PROFILE_LABELS[profile]}.
          </p>
        )}
      </section>

      <ul className="app-checklist" aria-label="Perguntas do checklist">
        {checklist.answers.map((answer) => {
          const draft = drafts[answer.question_id] ?? { value: null, evidence: "" };
          const effective = draft.value ?? (answer.source === "AUTO" ? answer.value : null);
          return (
            <li key={answer.question_id} className="app-checklist-item">
              <div>
                <div>{answer.text}</div>
                <small>
                  {answer.category}
                  {draft.value === null && answer.source === "AUTO" && answer.evidence
                    ? ` · automática: ${answer.evidence}`
                    : answer.hint
                      ? ` · ${answer.hint}`
                      : ""}
                </small>
              </div>
              <div className="app-segmented" role="group" aria-label={answer.text}>
                {(["YES", "NO", "NA"] as AnswerValue[]).map((value) => (
                  <button
                    key={value}
                    type="button"
                    disabled={saving}
                    aria-pressed={effective === value}
                    onClick={() => setAnswer(answer.question_id, draft.value === value ? null : value)}
                    title={draft.value === value ? "Clique de novo para limpar" : undefined}
                  >
                    {ANSWER_LABELS[value]}
                    {effective === value && draft.value === null && answer.source === "AUTO" ? " (auto)" : ""}
                  </button>
                ))}
              </div>
              {draft.value !== null && (
                <input
                  type="text"
                  aria-label={`Evidência: ${answer.text}`}
                  placeholder="Evidência (fonte, número, data) — opcional"
                  value={draft.evidence}
                  disabled={saving}
                  onChange={(e) => setEvidence(answer.question_id, e.target.value)}
                />
              )}
            </li>
          );
        })}
      </ul>

      {message && <p className={message.ok ? "app-success-banner" : "app-error-banner"}>{message.text}</p>}
      <div className="app-button-row">
        <button type="button" className="app-primary-button" onClick={() => void save()} disabled={saving}>
          {saving && <Spinner size="sm" />}
          {saving ? "Salvando…" : "Salvar checklist"}
        </button>
      </div>

      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Histórico da nota</h2>
        {history.length === 0 ? (
          <p className="app-muted">Ainda sem avaliações registradas.</p>
        ) : (
          <>
            <Sparkline values={history.map((h) => h.score)} />
            <div className="app-table-wrap" style={{ marginTop: "var(--space-3)" }}>
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Quando</th>
                    <th>Perfil</th>
                    <th className="app-numeric">Nota</th>
                    <th className="app-numeric">Cobertura</th>
                    <th>Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {[...history].reverse().map((h) => (
                    <tr key={h.evaluated_at}>
                      <td>{dateTime(h.evaluated_at)}</td>
                      <td>{PROFILE_LABELS[h.profile]}</td>
                      <td className="app-numeric">{h.score}</td>
                      <td className="app-numeric">{points(h.coverage_pct, 0)}</td>
                      <td>
                        <Badge tone={h.recommendation === "APTO" ? "success" : "neutral"}>
                          {RECOMMENDATION_LABELS[h.recommendation] ?? h.recommendation}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
