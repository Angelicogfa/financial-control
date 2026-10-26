import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type ImportNewAssetRequest } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { ArcaClass, AssetType, ImportCommitDTO, ImportPreviewDTO } from "../../api/types";
import { ArcaClassSelect } from "../../components/ArcaClassSelect";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { day, num, quantity } from "../../utils/format";
import { ASSET_TYPES, ASSET_TYPE_LABELS, EARNING_LABELS, EVENT_LABELS, TRADE_LABELS } from "../../utils/labels";
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

/** How an unknown ticker is registered with the import (the same registration as the research flow). */
interface NewAssetChoice {
  selected: boolean;
  asset_type: AssetType | "";
  arca_class: ArcaClass | "";
  suggested: ArcaClass | null;
}

function initialChoices(preview: ImportPreviewDTO): Record<string, NewAssetChoice> {
  return Object.fromEntries(
    preview.unknown_tickers.map((u) => [
      u.ticker,
      {
        selected: Boolean(u.asset_type),
        asset_type: u.asset_type ?? "",
        arca_class: u.arca_class ?? "",
        suggested: u.arca_class ?? null,
      },
    ]),
  );
}

function toNewAssets(choices: Record<string, NewAssetChoice>): ImportNewAssetRequest[] {
  return Object.entries(choices)
    .filter(([, c]) => c.selected && c.asset_type)
    .map(([ticker, c]) => ({ ticker, asset_type: c.asset_type || null, arca_class: c.arca_class || null }));
}

/** B3 statement import: preview what each line becomes, then apply the new lines at once. */
export function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewDTO | null>(null);
  const [choices, setChoices] = useState<Record<string, NewAssetChoice>>({});
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
      setChoices(initialChoices(data));
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
      setResult(await api.ledger.commitImport(file, accountId, toNewAssets(choices)));
      setPreview(await api.ledger.previewImport(file));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const choose = (ticker: string, change: Partial<NewAssetChoice>) =>
    setChoices((current) => ({ ...current, [ticker]: { ...current[ticker], ...change } }));

  /** A new type changes the suggested quadrant: ask the API, as the asset form does. */
  const chooseType = async (ticker: string, assetType: AssetType | "") => {
    choose(ticker, { asset_type: assetType, selected: Boolean(assetType) });
    if (!assetType) return;
    try {
      const suggestion = await api.assets.classify(ticker, assetType);
      choose(ticker, { arca_class: suggestion.arca_class, suggested: suggestion.arca_class });
    } catch {
      // Keep the current quadrant; the backend falls back to its own suggestion.
    }
  };

  const create = Object.entries(choices)
    .filter(([, c]) => c.selected && c.asset_type)
    .map(([ticker]) => ticker);
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
                <p className="app-card-hint">
                  Marque os que devem ser cadastrados junto com a importação. Cada um entra como um ativo pesquisado:
                  confira o tipo e o quadrante ARCA; os demonstrativos são buscados logo depois.
                </p>
                <div className="app-table-wrap">
                  <table className="app-table">
                    <thead>
                      <tr>
                        <th>Cadastrar</th>
                        <th>Tipo</th>
                        <th>Classe ARCA</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.unknown_tickers.map((u) => {
                        const choice = choices[u.ticker];
                        if (!choice) return null;
                        return (
                          <tr key={u.ticker}>
                            <td>
                              <label className="app-check">
                                <input
                                  type="checkbox"
                                  checked={choice.selected}
                                  disabled={!choice.asset_type}
                                  onChange={(e) => choose(u.ticker, { selected: e.target.checked })}
                                />
                                {u.ticker}
                                {u.name && <span className="app-muted"> {u.name}</span>}
                              </label>
                            </td>
                            <td>
                              <select
                                aria-label={`Tipo de ${u.ticker}`}
                                value={choice.asset_type}
                                onChange={(e) => void chooseType(u.ticker, e.target.value as AssetType | "")}
                              >
                                <option value="">Escolha o tipo</option>
                                {ASSET_TYPES.map((type) => (
                                  <option key={type} value={type}>
                                    {ASSET_TYPE_LABELS[type]}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <ArcaClassSelect
                                label={`Classe ARCA de ${u.ticker}`}
                                value={choice.arca_class}
                                suggested={choice.suggested}
                                emptyLabel="Sugerida pelo tipo"
                                disabled={!choice.asset_type}
                                onChange={(value) => choose(u.ticker, { arca_class: value })}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
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
