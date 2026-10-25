import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { ImportCommitDTO, ImportPreviewDTO } from "../../api/types";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { day, num, quantity } from "../../utils/format";
import { ASSET_TYPE_LABELS, EARNING_LABELS, EVENT_LABELS, TRADE_LABELS } from "../../utils/labels";
import { AccountSelect } from "./AssetSelect";

const STATUS: Record<string, { label: string; tone: string }> = {
  NEW: { label: "Novo", tone: "success" },
  DUPLICATE: { label: "Já importado", tone: "neutral" },
  UNKNOWN_ASSET: { label: "Ativo não cadastrado", tone: "warning" },
  IGNORED: { label: "Ignorado", tone: "neutral" },
  INVALID: { label: "Inválido", tone: "danger" },
};

function describe(line: ImportPreviewDTO["lines"][number]): string {
  if (line.trade_kind) return TRADE_LABELS[line.trade_kind as "BUY" | "SELL"];
  if (line.earning_kind) return EARNING_LABELS[line.earning_kind as keyof typeof EARNING_LABELS] ?? line.description;
  if (line.event_kind) return EVENT_LABELS[line.event_kind as keyof typeof EVENT_LABELS] ?? line.description;
  return line.description;
}

/** B3 statement import: preview what each line becomes, then apply the new lines at once. */
export function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewDTO | null>(null);
  const [create, setCreate] = useState<string[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [result, setResult] = useState<ImportCommitDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runPreview = async (chosen: File) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.ledger.previewImport(chosen);
      setPreview(data);
      setCreate(data.unknown_tickers.filter((u) => u.asset_type).map((u) => u.ticker));
    } catch (err) {
      setPreview(null);
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.ledger.commitImport(file, accountId, create));
      setPreview(await api.ledger.previewImport(file));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const newLines = preview?.counts.NEW ?? 0;
  const fromUnknown = preview
    ? preview.lines.filter((l) => l.status === "UNKNOWN_ASSET" && l.ticker && create.includes(l.ticker)).length
    : 0;

  return (
    <div className="app-page">
      <PageHeader
        title="Importar extrato B3"
        subtitle={
          <>
            Na Área do Investidor da B3, exporte <strong>Extratos › Negociação</strong> (compras e vendas) e{" "}
            <strong>Extratos › Movimentação</strong> (proventos e eventos). Importar o mesmo arquivo de novo não duplica nada.
          </>
        }
        actions={
          <Link className="app-secondary-button" to="/ledger">
            Voltar
          </Link>
        }
      />
      <div className="app-page-stack">
        <section className="app-card app-card-padded">
          <div className="app-field-grid">
            <div className="app-field">
              <label htmlFor="import-file">Arquivo (.xlsx ou .csv)</label>
              <input
                id="import-file"
                type="file"
                accept=".xlsx,.csv"
                onChange={(e) => {
                  const chosen = e.target.files?.[0] ?? null;
                  setFile(chosen);
                  if (chosen) void runPreview(chosen);
                }}
              />
            </div>
            <div className="app-field">
              <label htmlFor="import-account">Conta dos lançamentos</label>
              <AccountSelect id="import-account" value={accountId} onChange={setAccountId} />
            </div>
          </div>
        </section>

        {error && <p className="app-error-banner" role="alert">{error}</p>}
        {result && (
          <p className="app-success-banner" role="status">
            Importado: {result.created.TRADE ?? 0} operação(ões), {result.created.EARNING ?? 0} provento(s) e{" "}
            {result.created.EVENT ?? 0} evento(s)
            {(result.created_assets ?? []).length > 0 && `; ativos cadastrados: ${(result.created_assets ?? []).join(", ")}`}.
          </p>
        )}

        {preview && (
          <>
            <div className="app-button-row">
              <Badge tone="info">{preview.kind === "NEGOTIATION" ? "Negociação" : "Movimentação"}</Badge>
              {Object.entries(preview.counts).map(([status, count]) => (
                <Badge key={status} tone={STATUS[status]?.tone}>
                  {STATUS[status]?.label ?? status}: {count}
                </Badge>
              ))}
            </div>

            {preview.unknown_tickers.length > 0 && (
              <section className="app-card app-card-padded">
                <h2 className="app-card-heading">Ativos que ainda não estão cadastrados</h2>
                <p className="app-card-hint">Marque os que devem ser cadastrados junto com a importação.</p>
                <div className="app-chip-group">
                  {preview.unknown_tickers.map((u) => (
                    <label key={u.ticker} className="app-check" style={{ marginRight: "var(--space-4)" }}>
                      <input
                        type="checkbox"
                        checked={create.includes(u.ticker)}
                        disabled={!u.asset_type}
                        onChange={(e) =>
                          setCreate((current) =>
                            e.target.checked ? [...current, u.ticker] : current.filter((t) => t !== u.ticker),
                          )
                        }
                      />
                      {u.ticker}
                      <span className="app-muted">
                        {u.asset_type ? ASSET_TYPE_LABELS[u.asset_type] : "tipo desconhecido — cadastre antes"}
                      </span>
                    </label>
                  ))}
                </div>
              </section>
            )}

            <div className="app-button-row">
              <button
                type="button"
                className="app-primary-button"
                disabled={busy || newLines + fromUnknown === 0}
                onClick={() => void commit()}
              >
                {busy ? "Importando…" : `Importar ${newLines + fromUnknown} linha(s)`}
              </button>
              <span className="app-muted">Tudo ou nada: se uma venda ficar sem posição, nada é gravado.</span>
            </div>

            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Linha</th>
                    <th>Data</th>
                    <th>Ativo</th>
                    <th>Lançamento</th>
                    <th className="app-numeric">Quantidade</th>
                    <th className="app-numeric">Preço</th>
                    <th className="app-numeric">Valor</th>
                    <th>Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.lines.map((line) => (
                    <tr key={line.line_no}>
                      <td>{line.line_no}</td>
                      <td>{day(line.entry_date)}</td>
                      <td>{line.ticker ?? "—"}</td>
                      <td>{describe(line)}</td>
                      <td className="app-numeric">{quantity(line.quantity)}</td>
                      <td className="app-numeric">{num(line.unit_price)}</td>
                      <td className="app-numeric">{num(line.amount)}</td>
                      <td>
                        <Badge tone={STATUS[line.status]?.tone}>{STATUS[line.status]?.label ?? line.status}</Badge>
                        {line.note && <span className="app-muted"> {line.note}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
