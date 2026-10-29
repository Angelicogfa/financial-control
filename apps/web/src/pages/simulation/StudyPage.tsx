/** One study: the conclusion, then each chapter with its "quanto confiar" seal (Phase 41.5). */

import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { StudyActionDTO, StudyChapterDTO, StudyDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Lead, Notes } from "../../components/Section";
import { Async, Empty, Spinner } from "../../components/States";
import { dateTime } from "../../utils/format";
import { compareLink } from "../tools/AssetComparePage";
import { isStudyActive, premisesLine, SealBox, StudyStatusBadge } from "./shared";
import { CandidatesTab, PastTab, ProjectionTab, RobustnessTab, SelectedRun } from "./views";

const POLL_MS = 4000;

const PREMISE_LABELS: Record<string, string> = {
  monthly_contribution: "Aporte mensal",
  horizon_years: "Horizonte (anos)",
  wealth_goal: "Meta de patrimônio",
  correct_by_ipca: "Reajuste pelo IPCA",
  past_start: "Passado desde",
  policy_mode: "Regras",
  answers_mode: "Checklist no passado",
  benchmarks: "Referências",
  rebalance: "Rebalanceamento",
  include_screener: "Candidatos do screener",
  weight_mode: "Peso dos candidatos",
  fixed_weight: "Peso fixo",
  rupture_stress: "Ruptura em estresse",
};

const VALUE_LABELS: Record<string, string> = {
  CURRENT: "as de hoje",
  AS_OF: "as vigentes em cada data",
  TODAY: "respostas de hoje no período inteiro",
  DATED: "cada resposta a partir da sua data",
  NEXT_CONTRIBUTION: "a parte do próximo aporte",
  FIXED: "peso fixo",
};

function premiseValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return "—";
  return VALUE_LABELS[String(value)] ?? String(value);
}

function NextSteps({ study, actions }: Readonly<{ study: StudyDTO; actions: StudyActionDTO[] }>) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const vary = async (action: StudyActionDTO) => {
    setBusy(action.label);
    setError(null);
    try {
      const created = await api.studies.variation(study.id, { changes: action.changes ?? {} });
      navigate(`/tools/simulation/${created.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="app-button-row" aria-label="Próximos passos">
      {actions.map((action, i) => {
        const className = i === 0 ? "app-primary-button" : "app-secondary-button";
        if (action.kind === "VARIATION") {
          return (
            <button key={action.label} type="button" className={className} disabled={busy !== null} onClick={() => void vary(action)}>
              {busy === action.label && <Spinner size="sm" />}
              <span>{action.label}</span>
            </button>
          );
        }
        if (action.kind === "COMPARE_ASSET" && action.ticker) {
          return (
            <Link key={action.label} className={className} to={compareLink(action.ticker)}>
              {action.label}
            </Link>
          );
        }
        if (action.kind === "SET_GOAL") {
          return (
            <Link key={action.label} className={className} to="/tools/simulation/new">
              {action.label}
            </Link>
          );
        }
        return (
          <Link key={action.label} className={className} to="/contribute">
            {action.label}
          </Link>
        );
      })}
      {error && <span className="app-negative">{error}</span>}
    </div>
  );
}

const NEXT_CHAPTER: Record<string, string> = {
  PAST: "Este capítulo mostra o que as regras teriam feito; o próximo projeta as mesmas regras para frente.",
  FUTURE: "O capítulo dos candidatos usa estas mesmas premissas para testar cada ativo.",
};

function ChapterBody({ chapter, onStatus }: Readonly<{ chapter: StudyChapterDTO; onStatus: () => void }>) {
  if (chapter.run_id == null) {
    return <Empty title="Este capítulo não rodou" hint="Veja o motivo nas notas do estudo." />;
  }
  return (
    <SelectedRun runId={chapter.run_id} onStatus={onStatus}>
      {(detail) => {
        if (chapter.key === "PAST") {
          return (
            <div className="app-page-stack">
              <PastTab detail={detail} />
              <SealBox title="Quanto isso depende de sorte?" seal={chapter.seal}>
                {detail.status === "DONE" && (
                  <details className="study-seal-detail">
                    <summary>Ver crises, choques e as variantes de regra</summary>
                    <RobustnessTab run={detail} />
                  </details>
                )}
              </SealBox>
            </div>
          );
        }
        if (chapter.key === "FUTURE") {
          return (
            <div className="app-page-stack">
              <ProjectionTab run={detail} />
              <SealBox title="Quanto confiar nestas chances?" seal={chapter.seal}>
                <Link to="/tools/simulation/quality">Como medimos (qualidade dos modelos) →</Link>
              </SealBox>
            </div>
          );
        }
        return (
          <div className="app-page-stack">
            <CandidatesTab run={detail} />
            <SealBox title="Quanto confiar nestas chances?" seal={chapter.seal} />
          </div>
        );
      }}
    </SelectedRun>
  );
}

function StudyView({ study, reload }: Readonly<{ study: StudyDTO; reload: () => void }>) {
  const navigate = useNavigate();
  const [working, setWorking] = useState<"refresh" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const versions = useApi(`study-versions-${study.id}-${study.status}`, () => api.studies.versions(study.id));

  const refresh = async () => {
    setWorking("refresh");
    setError(null);
    try {
      const created = await api.studies.refresh(study.id);
      navigate(`/tools/simulation/${created.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setWorking(null);
    }
  };
  const remove = async () => {
    if (!window.confirm(`Excluir "${study.label}"? O estudo e os resultados somem e não há como recuperar.`)) return;
    setWorking("delete");
    try {
      await api.studies.remove(study.id);
      navigate("/tools/simulation");
    } catch (err) {
      setError(errorMessage(err));
      setWorking(null);
    }
  };
  const compareWith = study.variation_of ?? versions.data?.filter((v) => v.id !== study.id).at(-1)?.id ?? null;

  return (
    <div className="study-layout">
      <nav className="study-index" aria-label="Capítulos do estudo">
        <span className="app-eyebrow">Neste estudo</span>
        <a href="#conclusao">Conclusão</a>
        {study.chapters.map((c) => (
          <a key={c.key} href={`#cap-${c.key.toLowerCase()}`}>
            {c.number} · {c.title}{" "}
            <span className="app-muted">{c.status === "DONE" ? "✓" : c.status ? "…" : "—"}</span>
          </a>
        ))}
        <a href="#premissas">Premissas e versões</a>
        <div className="study-index-actions">
          <button type="button" className="app-link-button" onClick={() => void refresh()} disabled={working !== null || isStudyActive(study.status)}>
            {working === "refresh" ? "Atualizando…" : "Atualizar com os dados de hoje"}
          </button>
          {compareWith !== null && (
            <Link to={`/tools/simulation/compare?a=${compareWith}&b=${study.id}`}>Comparar com {study.variation_of ? "o original" : "a versão anterior"}</Link>
          )}
          <button type="button" className="app-link-button" onClick={() => window.print()}>
            Imprimir / PDF
          </button>
          <button type="button" className="app-link-button app-negative" onClick={() => void remove()} disabled={working !== null}>
            {working === "delete" ? "Excluindo…" : "Excluir estudo"}
          </button>
        </div>
      </nav>

      <div className="study-main">
        {error && (
          <p className="app-error-banner" role="alert">
            {error}
          </p>
        )}
        <section id="conclusao" className="app-section study-conclusion" aria-label="Conclusão do estudo">
          <span className="app-eyebrow">Conclusão</span>
          {study.conclusion ? (
            <>
              <p className="study-conclusion-text">{study.conclusion}</p>
              <NextSteps study={study} actions={study.actions ?? []} />
            </>
          ) : isStudyActive(study.status) ? (
            <p className="app-muted">
              <Spinner size="sm" /> Os capítulos estão rodando; a conclusão aparece quando terminarem. Pode sair e voltar.
            </p>
          ) : (
            <p className="app-muted">Nenhum capítulo terminou, então não há conclusão.</p>
          )}
        </section>
        {(study.notes ?? []).length > 0 && <Notes items={study.notes ?? []} title="Avisos do estudo" tone="caution" />}

        {study.chapters.map((chapter) => (
          <section key={chapter.key} id={`cap-${chapter.key.toLowerCase()}`} className="app-section study-chapter" aria-label={`Capítulo ${chapter.number}, ${chapter.title}`}>
            <header className="study-chapter-head">
              <span className="app-eyebrow">
                Capítulo {chapter.number} · {chapter.title}
              </span>
              <h2 className="study-chapter-question">{chapter.question}</h2>
            </header>
            <ChapterBody chapter={chapter} onStatus={reload} />
            {(chapter.notes ?? []).length > 0 && (
              <Notes items={chapter.notes ?? []} title="Premissa deste capítulo" tone="caution" />
            )}
            {NEXT_CHAPTER[chapter.key] && study.chapters.some((c) => c.number === chapter.number + 1) && (
              <p className="app-meta">→ {NEXT_CHAPTER[chapter.key]}</p>
            )}
          </section>
        ))}

        <section id="premissas" className="app-section study-premises" aria-label="Premissas e versões">
          <div>
            <h2 className="app-section-title">Premissas</h2>
            <dl className="study-premise-list">
              {Object.entries(study.premises).map(([key, value]) => (
                <div key={key}>
                  <dt>{PREMISE_LABELS[key] ?? key}</dt>
                  <dd>{premiseValue(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <h2 className="app-section-title">Versões</h2>
            <Async state={versions}>
              {(items) => (
                <ol className="study-versions">
                  {items.map((v) => (
                    <li key={v.id}>
                      {v.id === study.id ? (
                        <strong>Versão {v.version} (em exibição)</strong>
                      ) : (
                        <Link to={`/tools/simulation/${v.id}`}>Versão {v.version}</Link>
                      )}{" "}
                      · {dateTime(v.created_at)}
                      {v.goal_probability != null && ` · chance da meta ${Math.round(v.goal_probability * 100)}%`}
                    </li>
                  ))}
                </ol>
              )}
            </Async>
          </div>
        </section>
      </div>
    </div>
  );
}

export function StudyPage() {
  const { studyId } = useParams();
  const id = Number(studyId);
  const [tick, setTick] = useState(0);
  const state = useApi(`study-${id}-${tick}`, () => api.studies.get(id));
  const active = state.data ? isStudyActive(state.data.status) : false;

  useEffect(() => {
    if (!active) return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [active, tick]);

  return (
    <div className="app-page">
      <Async state={state} lines={8}>
        {(study) => (
          <>
            <PageHeader
              title={study.label}
              subtitle={
                <span>
                  {study.question_label} · versão {study.version} de {dateTime(study.created_at)} · {premisesLine(study.premises)}
                </span>
              }
              actions={
                <>
                  {study.variation_of && <Badge tone="neutral">Variação</Badge>}
                  <StudyStatusBadge status={study.status} />
                </>
              }
            />
            {study.status === "FAILED" && (
              <Lead tone="negative">
                <p>Nenhum capítulo deste estudo terminou. Veja os avisos e tente atualizar com os dados de hoje.</p>
              </Lead>
            )}
            <StudyView study={study} reload={() => setTick((t) => t + 1)} />
          </>
        )}
      </Async>
    </div>
  );
}
