/** Simular carteira: the studies, newest first, with the main one up top (Phase 41.4). */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { StudySummaryDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { PageHeader } from "../../components/PageHeader";
import { Lead } from "../../components/Section";
import { Async, Empty } from "../../components/States";
import { dateTime, plural } from "../../utils/format";
import { goalText, isStudyActive, ppText, StudyStatusBadge } from "./shared";

const POLL_MS = 4000;

function Highlight({ study }: Readonly<{ study: StudySummaryDTO }>) {
  const goal = goalText(study);
  return (
    <section className="app-section study-highlight" aria-label="Estudo principal">
      <div className="study-highlight-body">
        <span className="app-eyebrow">
          Último estudo · versão {study.version} · {dateTime(study.created_at)}
        </span>
        <h2 className="study-highlight-title">{study.label}</h2>
        {study.headline ? <p className="study-highlight-text">{study.headline}</p> : <p className="app-muted">Os capítulos ainda estão rodando.</p>}
        <div className="app-button-row">
          <Link className="app-primary-button" to={`/tools/simulation/${study.id}`}>
            Abrir estudo
          </Link>
        </div>
      </div>
      {goal && (
        <div className="study-highlight-goal">
          <span className="app-muted">Chance da meta</span>
          <strong className="study-goal-value">{goal}</strong>
          {study.goal_change != null && (
            <span className={`home-delta ${study.goal_change >= 0 ? "is-up" : "is-down"}`}>
              <span aria-hidden="true">{study.goal_change >= 0 ? "▲" : "▼"}</span> {ppText(study.goal_change)} desde a versão anterior
            </span>
          )}
        </div>
      )}
    </section>
  );
}

function StudyCard({ study }: Readonly<{ study: StudySummaryDTO }>) {
  const goal = goalText(study);
  const running = isStudyActive(study.status);
  return (
    <article className="study-card">
      <div className="study-card-head">
        <span className="study-chip">{study.variation_of ? "Variação" : study.question_label}</span>
        <StudyStatusBadge status={study.status} />
      </div>
      <h3 className="study-card-title">
        <Link to={`/tools/simulation/${study.id}`}>{study.label}</Link>
      </h3>
      {running ? (
        <>
          <div className="study-progress" role="progressbar" aria-valuemin={0} aria-valuemax={study.chapters_total} aria-valuenow={study.chapters_done} aria-label="Capítulos prontos">
            <div style={{ width: `${(study.chapters_done / Math.max(study.chapters_total, 1)) * 100}%` }} />
          </div>
          <p className="app-muted">
            {plural(study.chapters_done, "capítulo pronto", "capítulos prontos")} de {study.chapters_total}. Pode sair: os capítulos
            aparecem conforme ficam prontos.
          </p>
        </>
      ) : (
        <p className="study-card-text">{study.headline ?? "Sem resultado para mostrar."}</p>
      )}
      <div className="study-card-foot">
        {goal ? (
          <span>
            <strong>{goal}</strong> <span className="app-muted">chance da meta</span>
          </span>
        ) : (
          <span className="app-muted">{dateTime(study.created_at)}</span>
        )}
        <Link to={`/tools/simulation/${study.id}`}>Abrir →</Link>
      </div>
    </article>
  );
}

export function StudiesPage() {
  const [tick, setTick] = useState(0);
  const studies = useApi(`studies-${tick}`, () => api.studies.list());
  const running = (studies.data ?? []).some((s) => isStudyActive(s.status));

  useEffect(() => {
    if (!running) return undefined;
    const timer = setTimeout(() => setTick((t) => t + 1), POLL_MS);
    return () => clearTimeout(timer);
  }, [running, tick]);

  return (
    <div className="app-page">
      <PageHeader
        title="Simular carteira"
        subtitle="Cada estudo responde uma pergunta sua com as mesmas premissas do começo ao fim: de onde a carteira veio, para onde vai e o que pode melhorar."
        actions={
          <>
            <Link className="app-secondary-button" to="/tools/simulation/quality">
              Qualidade dos modelos
            </Link>
            <Link className="app-secondary-button" to="/tools/simulation/compare">
              Comparar estudos
            </Link>
            <Link className="app-primary-button" to="/tools/simulation/new">
              + Novo estudo
            </Link>
          </>
        }
      />
      <Async state={studies} lines={6}>
        {(items) =>
          items.length === 0 ? (
            <div className="app-page-stack">
              <Lead eyebrow="Como funciona">
                <p>
                  Escolha uma pergunta (por exemplo "Vou chegar à minha meta?"), informe o aporte e a meta uma vez e o estudo
                  responde em capítulos: o que suas regras teriam feito, a faixa provável do futuro e que ativo pode melhorar a
                  chance, cada um com o quanto dá para confiar.
                </p>
              </Lead>
              <Empty title="Nenhum estudo ainda" hint="Comece pelo estudo completo.">
                <Link className="app-primary-button" to="/tools/simulation/new">
                  Criar o primeiro estudo
                </Link>
              </Empty>
            </div>
          ) : (
            <div className="app-page-stack">
              <Highlight study={items[0]} />
              <h2 className="app-section-title">Todos os estudos</h2>
              <div className="study-grid">
                {items.map((s) => (
                  <StudyCard key={s.id} study={s} />
                ))}
              </div>
              <p className="app-meta">
                Cada estudo guarda as versões: "Atualizar" refaz com os dados de hoje e mantém a anterior. Estudos excluídos somem
                de vez.
              </p>
            </div>
          )
        }
      </Async>
    </div>
  );
}
