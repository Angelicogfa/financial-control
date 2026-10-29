/** Two studies side by side, chapter by chapter, with what differs highlighted (Phase 41.6). */

import { useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { StudyComparisonRowDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { PageHeader } from "../../components/PageHeader";
import { Lead, Section } from "../../components/Section";
import { Async, Empty } from "../../components/States";

const CHAPTERS: Array<[StudyComparisonRowDTO["chapter"], string]> = [
  ["PAST", "Capítulo 1 · De onde viemos"],
  ["FUTURE", "Capítulo 2 · Para onde vamos"],
  ["IMPROVE", "Capítulo 3 · O que pode melhorar"],
];

function show(value: unknown): string {
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined) return "—";
  return String(value);
}

export function CompareStudiesPage() {
  const [params, setParams] = useSearchParams();
  const a = Number(params.get("a")) || null;
  const b = Number(params.get("b")) || null;
  const studies = useApi("compare-studies-list", () => api.studies.list(100));
  const comparison = useApi(`compare-${a}-${b}`, () => (a && b ? api.studies.compare(a, b) : Promise.resolve(null)));
  const pick = (key: "a" | "b", value: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  return (
    <div className="app-page">
      <PageHeader title="Comparar estudos" subtitle="Capítulo por capítulo, com a diferença destacada. Só muda o que difere nas premissas." />
      <div className="app-page-stack">
        <div className="app-field-grid">
          {(["a", "b"] as const).map((key) => (
            <div key={key} className="app-field">
              <label htmlFor={`compare-${key}`}>Estudo {key.toUpperCase()}</label>
              <select id={`compare-${key}`} value={(key === "a" ? a : b) ?? ""} onChange={(e) => pick(key, e.target.value)}>
                <option value="">Escolha um estudo</option>
                {(studies.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label} (versão {s.version})
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
        {!a || !b ? (
          <Empty title="Escolha dois estudos" hint="Uma variação já abre comparada com o original." />
        ) : (
          <Async state={comparison} lines={6}>
            {(data) =>
              data && (
                <div className="app-page-stack">
                  <Lead>
                    <p>{data.headline}</p>
                  </Lead>
                  {(data.differences ?? []).length > 0 && (
                    <p className="app-meta">
                      Diferença nas premissas:{" "}
                      {(data.differences ?? []).map((d) => `${d.label.toLowerCase()} ${show(d.a)} → ${show(d.b)}`).join(" · ")}. Todo o
                      resto é igual.
                    </p>
                  )}
                  <Section title="Comparação por capítulo">
                    <div className="app-table-wrap">
                      <table className="app-table" aria-label="Comparação dos estudos">
                        <thead>
                          <tr>
                            <th>Indicador</th>
                            <th className="app-numeric">A · {data.a.label}</th>
                            <th className="app-numeric">B · {data.b.label}</th>
                            <th className="app-numeric">Diferença</th>
                          </tr>
                        </thead>
                        <tbody>
                          {CHAPTERS.map(([chapter, title]) => {
                            const rows = (data.rows ?? []).filter((r) => r.chapter === chapter);
                            if (rows.length === 0) return null;
                            return [
                              <tr key={`${chapter}-head`} className="app-table-group">
                                <th colSpan={4} scope="colgroup">
                                  {title}
                                </th>
                              </tr>,
                              ...rows.map((r) => (
                                <tr key={`${chapter}-${r.label}`}>
                                  <td>{r.label}</td>
                                  <td className="app-numeric">{r.a}</td>
                                  <td className="app-numeric">{r.b}</td>
                                  <td className={`app-numeric${r.tone === "positive" ? " app-positive" : r.tone === "negative" ? " app-negative" : ""}`}>
                                    {r.difference}
                                  </td>
                                </tr>
                              )),
                            ];
                          })}
                        </tbody>
                      </table>
                    </div>
                  </Section>
                </div>
              )
            }
          </Async>
        )}
      </div>
    </div>
  );
}
