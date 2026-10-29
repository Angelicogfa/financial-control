/** Home card: the latest simulation study and its goal chance (Phase 41.6). */

import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { useApi } from "../../api/useApi";
import { Section } from "../../components/Section";
import { dateTime } from "../../utils/format";
import { ppText } from "../simulation/shared";

export function LatestStudy() {
  const studies = useApi("home-latest-study", () => api.studies.list(10));
  const study = (studies.data ?? []).find((s) => s.status === "DONE" || s.status === "PARTIAL");
  if (!study) return null;
  return (
    <Section
      title={`Último estudo · ${study.label}`}
      subtitle={dateTime(study.created_at)}
      actions={<Link to={`/tools/simulation/${study.id}`}>Abrir o estudo →</Link>}
      label="Último estudo"
    >
      {study.goal_probability != null ? (
        <p className="study-home-goal">
          <strong className="study-goal-value">{Math.round(study.goal_probability * 100)}%</strong>
          <span>de chance de chegar à meta</span>
          {study.goal_change != null && (
            <span className={`home-delta ${study.goal_change >= 0 ? "is-up" : "is-down"}`}>
              <span aria-hidden="true">{study.goal_change >= 0 ? "▲" : "▼"}</span> {ppText(study.goal_change)} desde a versão anterior
            </span>
          )}
        </p>
      ) : null}
      {study.headline && <p className="app-muted">{study.headline}</p>}
    </Section>
  );
}
