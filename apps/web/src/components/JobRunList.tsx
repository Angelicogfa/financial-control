/** "Rodar agora": buttons that ask the worker to run a job now, with the last run of each.
 *  Each screen lists the jobs whose result it shows (the market data page, the fetch jobs). */

import { useEffect, useState } from "react";

import { api } from "../api/endpoints";
import { errorMessage } from "../api/http";
import { JOB_LABELS, JOB_POLL_MS, JOB_STATUS_LABELS, JOB_TONES, type ManualJob } from "../api/jobs";
import { useApi } from "../api/useApi";
import { dateTime } from "../utils/format";
import { Badge } from "./Badge";
import { Spinner } from "./States";

export function JobRunList({ jobs, onChange }: Readonly<{ jobs: ManualJob[]; onChange?: () => void }>) {
  const runs = useApi("job-runs", () => api.market.jobs());
  const [requesting, setRequesting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastRun = (name: string) => runs.data?.find((j) => j.job_name === name);
  const active = (name: string) => ["REQUESTED", "RUNNING"].includes(lastRun(name)?.status ?? "");
  const anyActive = jobs.some((j) => active(j.name));
  const [wasActive, setWasActive] = useState(false);

  // Follow a manual run until the worker finishes it; the screen reloads its data on a request
  // and when the run ends.
  useEffect(() => {
    if (anyActive) {
      setWasActive(true);
      const timer = setTimeout(() => runs.reload(), JOB_POLL_MS);
      return () => clearTimeout(timer);
    }
    if (wasActive) {
      setWasActive(false);
      onChange?.();
    }
    return undefined;
  }, [anyActive, runs, wasActive, onChange]);

  const request = async (name: string) => {
    setRequesting(name);
    setError(null);
    try {
      await api.market.requestJob(name);
      runs.reload();
      onChange?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRequesting(null);
    }
  };

  return (
    <div aria-label="Rodar agora">
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      <ul className="app-run-list">
        {jobs.map((job) => {
          const run = lastRun(job.name);
          const status = run?.status;
          const running = active(job.name);
          return (
            <li key={job.name} className="app-run-item">
              <div className="app-run-text">
                <strong>{JOB_LABELS[job.name] ?? job.name}</strong>
                <p className="app-card-hint">{job.hint}</p>
                {running ? (
                  <span className="app-run-status" role="status">
                    {status === "REQUESTED" ? "Pedido registrado; o worker começa em até 15 segundos." : "Rodando…"}
                  </span>
                ) : (
                  run && (
                    <span className="app-run-status">
                      Última vez: {dateTime(run.finished_at ?? run.started_at)}{" "}
                      <Badge tone={JOB_TONES[run.status] ?? "neutral"}>{JOB_STATUS_LABELS[run.status] ?? run.status}</Badge>
                    </span>
                  )
                )}
              </div>
              <button
                type="button"
                className="app-secondary-button"
                disabled={running || requesting !== null}
                onClick={() => request(job.name)}
              >
                {(running || requesting === job.name) && <Spinner size="sm" />}
                <span>{job.action}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
