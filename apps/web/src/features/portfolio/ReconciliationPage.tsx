/** Carteira › Conferir (Phase 48.R5, REFACTORING_PLAN §3.5): the ledger against the B3
 *  Posição statement, per ticker and account. The check never writes to the ledger: each
 *  difference links to the trade that would fix it, prefilled, or is marked as explained. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { ReconciliationDTO, ReconciliationLineDTO, ReconciliationSummaryDTO } from "../../api/types";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Section } from "../../components/Section";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { day, quantity } from "../../utils/format";
import { instrumentPath } from "../instrument/paths";

const STATUS: Record<ReconciliationLineDTO["status"], { label: string; tone: string }> = {
  MATCH: { label: "Confere", tone: "success" },
  DIVERGENT: { label: "Quantidade diferente", tone: "danger" },
  ONLY_B3: { label: "Só na B3", tone: "warning" },
  ONLY_LEDGER: { label: "Só no livro", tone: "warning" },
  NOT_COMPARED: { label: "Não comparado", tone: "neutral" },
};

const ISSUES = new Set<ReconciliationLineDTO["status"]>(["DIVERGENT", "ONLY_B3", "ONLY_LEDGER"]);

/** The trade that would bring the ledger to the statement, prefilled; null when none would. */
export function fixLink(line: ReconciliationLineDTO, referenceDate: string): string | null {
  if (!ISSUES.has(line.status)) return null;
  if (line.asset_id === null || line.asset_id === undefined) {
    return line.ticker ? instrumentPath(line.ticker) : null;
  }
  const params = new URLSearchParams({
    asset: String(line.asset_id),
    kind: line.difference > 0 ? "BUY" : "SELL",
    quantity: String(Math.abs(line.difference)),
    date: referenceDate,
  });
  if (line.account_id) params.set("account", String(line.account_id));
  return `/lancamentos/negociacoes/nova?${params.toString()}`;
}

function daysSince(dateText: string): number {
  const [y, m, d] = dateText.split("-").map(Number);
  const then = Date.UTC(y, m - 1, d);
  const now = new Date();
  return Math.floor((Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) - then) / 86_400_000);
}

function LastCheck({ last }: Readonly<{ last: ReconciliationSummaryDTO | undefined }>) {
  if (!last) {
    return (
      <Lead tone="caution">
        <p>A posição ainda não foi conferida contra a B3. Envie o extrato de Posição da Área do Investidor.</p>
      </Lead>
    );
  }
  const age = daysSince(last.reference_date);
  const open = last.counts.open_issues;
  return (
    <Lead tone={open > 0 ? "negative" : age > 35 ? "caution" : "positive"}>
      <p>
        Última conferência com data-base de <strong>{day(last.reference_date)}</strong> (há {age} dia(s)):{" "}
        {open > 0 ? `${open} diferença(s) em aberto.` : "tudo confere ou foi explicado."}
      </p>
    </Lead>
  );
}

function Lines({
  result,
  onResolve,
  resolving,
}: Readonly<{
  result: ReconciliationDTO;
  onResolve?: (line: ReconciliationLineDTO) => void;
  resolving?: number | null;
}>) {
  const ordered = [...result.lines].sort(
    (a, b) => Number(ISSUES.has(b.status)) - Number(ISSUES.has(a.status)) || (a.ticker ?? "").localeCompare(b.ticker ?? ""),
  );
  if (ordered.length === 0) return <p className="app-muted">O extrato e o livro não têm posições na data.</p>;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Linhas da conferência">
        <thead>
          <tr>
            <th>Ativo</th>
            <th>Instituição</th>
            <th className="app-numeric">B3</th>
            <th className="app-numeric">Livro</th>
            <th className="app-numeric">Diferença</th>
            <th>Situação</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {ordered.map((line, index) => {
            const link = fixLink(line, result.reference_date);
            const resolved = line.resolution === "RESOLVED";
            return (
              <tr key={line.id ?? `${line.ticker}-${line.account_id}-${index}`}>
                <td>
                  {line.ticker ? (
                    <Link className="app-link" to={instrumentPath(line.ticker)}>
                      {line.ticker}
                    </Link>
                  ) : (
                    line.product
                  )}
                  {line.note && <div className="app-muted">{line.note}</div>}
                </td>
                <td>{line.institution ?? "—"}</td>
                <td className="app-numeric">{quantity(line.b3_quantity)}</td>
                <td className="app-numeric">{line.status === "NOT_COMPARED" ? "—" : quantity(line.ledger_quantity)}</td>
                <td className="app-numeric">{line.status === "NOT_COMPARED" ? "—" : quantity(line.difference)}</td>
                <td>
                  <Badge tone={resolved ? "neutral" : STATUS[line.status].tone}>
                    {resolved ? "Explicado" : STATUS[line.status].label}
                  </Badge>
                  {resolved && line.resolution_note && <div className="app-muted">{line.resolution_note}</div>}
                </td>
                <td className="app-button-row">
                  {link && !resolved && (
                    <Link className="app-secondary-button" to={link}>
                      {line.asset_id ? "Lançar diferença" : "Abrir ativo"}
                    </Link>
                  )}
                  {onResolve && line.id && ISSUES.has(line.status) && (
                    <button
                      type="button"
                      className="app-secondary-button"
                      disabled={resolving === line.id}
                      onClick={() => onResolve(line)}
                    >
                      {resolved ? "Reabrir" : "Marcar como explicado"}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Counts({ result }: Readonly<{ result: ReconciliationDTO }>) {
  const c = result.counts;
  return (
    <KpiGrid
      label="Resultado da conferência"
      items={[
        { label: "Conferem", value: c.match, tone: "positive" },
        { label: "Diferentes", value: c.divergent, tone: c.divergent ? "negative" : "neutral" },
        { label: "Só na B3", value: c.only_b3, tone: c.only_b3 ? "caution" : "neutral" },
        { label: "Só no livro", value: c.only_ledger, tone: c.only_ledger ? "caution" : "neutral" },
        { label: "Não comparados", value: c.not_compared, note: "Tesouro e renda fixa, sem código" },
      ]}
    />
  );
}

export function ReconciliationPage() {
  const client = useQueryClient();
  const history = useQuery({ queryKey: ["reconciliations"], queryFn: () => api.reconciliation.list() });
  const [file, setFile] = useState<File | null>(null);
  const [referenceDate, setReferenceDate] = useState("");
  const [preview, setPreview] = useState<ReconciliationDTO | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  const check = useMutation({
    mutationFn: () => api.reconciliation.preview(file as File, referenceDate || undefined),
    onSuccess: (result) => setPreview(result),
  });
  const save = useMutation({
    mutationFn: () => api.reconciliation.commit(file as File, referenceDate || undefined),
    onSuccess: (saved) => {
      setPreview(null);
      setOpenId(saved.id ?? null);
      client.setQueryData(["reconciliation", saved.id], saved);
      void client.invalidateQueries({ queryKey: ["reconciliations"] });
    },
  });
  const opened = useQuery({
    queryKey: ["reconciliation", openId],
    queryFn: () => api.reconciliation.get(openId as number),
    enabled: openId !== null,
  });
  const resolve = useMutation({
    mutationFn: (line: ReconciliationLineDTO) =>
      api.reconciliation.resolve(openId as number, line.id as number, {
        resolution: line.resolution === "RESOLVED" ? "OPEN" : "RESOLVED",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["reconciliation", openId] });
      void client.invalidateQueries({ queryKey: ["reconciliations"] });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (file) check.mutate();
  };

  return (
    <div className="app-page">
      <PageHeader
        title="Conferir posição"
        subtitle="O livro contra o extrato de Posição da B3, por ativo e conta. A conferência nunca altera os lançamentos."
      />
      <div className="app-page-stack">
        {history.isPending ? <Loading lines={2} /> : <LastCheck last={history.data?.[0]} />}
        <ErrorBanner error={history.error} onRetry={() => void history.refetch()} />

        <Section
          title="Novo extrato"
          subtitle="Na Área do Investidor da B3: Extratos › Posição › escolha a data › Baixar em Excel."
        >
          <form className="app-filter-bar" onSubmit={submit}>
            <label className="app-field">
              <span>Extrato de Posição (.xlsx ou .csv)</span>
              <input
                type="file"
                accept=".xlsx,.csv"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setPreview(null);
                }}
              />
            </label>
            <label className="app-field">
              <span>Data-base</span>
              <input type="date" value={referenceDate} onChange={(event) => setReferenceDate(event.target.value)} />
            </label>
            <button type="submit" className="app-primary-button" disabled={!file || check.isPending}>
              {check.isPending ? "Conferindo…" : "Conferir"}
            </button>
          </form>
          <p className="app-muted">Sem data-base, vale a do nome do arquivo da B3 (posicao-AAAA-MM-DD.xlsx).</p>
          <ErrorBanner error={check.error ?? save.error} />
        </Section>

        {preview && (
          <Section
            title={`Prévia com data-base de ${day(preview.reference_date)}`}
            subtitle="Ainda não gravada. Corrija o livro pelos links ou grave a conferência como está."
            actions={
              <button type="button" className="app-primary-button" disabled={save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? "Gravando…" : "Gravar conferência"}
              </button>
            }
          >
            <Counts result={preview} />
            <Lines result={preview} />
          </Section>
        )}

        {openId !== null && opened.data && (
          <Section title={`Conferência de ${day(opened.data.reference_date)}`} subtitle={opened.data.file_name}>
            <Counts result={opened.data} />
            <Lines result={opened.data} onResolve={(line) => resolve.mutate(line)} resolving={resolve.isPending ? resolve.variables?.id : null} />
            <ErrorBanner error={resolve.error} />
          </Section>
        )}

        <Section title="Conferências gravadas">
          {history.data && history.data.length > 0 ? (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Data-base</th>
                    <th>Arquivo</th>
                    <th className="app-numeric">Conferem</th>
                    <th className="app-numeric">Em aberto</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {history.data.map((r) => (
                    <tr key={r.id}>
                      <td>{day(r.reference_date)}</td>
                      <td>{r.file_name}</td>
                      <td className="app-numeric">{r.counts.match}</td>
                      <td className="app-numeric">{r.counts.open_issues}</td>
                      <td>
                        <button type="button" className="app-secondary-button" onClick={() => setOpenId(r.id)}>
                          Ver linhas
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Nenhuma conferência gravada" />
          )}
        </Section>
      </div>
    </div>
  );
}
