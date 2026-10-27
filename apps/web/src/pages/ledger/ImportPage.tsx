import { Fragment, useState } from "react";
import { Link } from "react-router-dom";

import { api, type ImportNewAssetRequest } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  ArcaClass,
  AssetType,
  FixedIncomeIndexer,
  FixedIncomeLiquidity,
  ImportCommitDTO,
  ImportFixedIncomeTermDTO,
  ImportPreviewDTO,
} from "../../api/types";
import { ArcaClassSelect } from "../../components/ArcaClassSelect";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Spinner } from "../../components/States";
import { day, num, parseDecimal, quantity } from "../../utils/format";
import {
  ASSET_TYPES,
  ASSET_TYPE_LABELS,
  EARNING_LABELS,
  EVENT_LABELS,
  INDEXERS,
  INDEXER_HINTS,
  LIQUIDITY_LABELS,
  TRADE_LABELS,
} from "../../utils/labels";
import { percentToContractedRate } from "../../utils/rates";
import { AccountSelect } from "./AssetSelect";

const STATUS: Record<string, { label: string; tone: string }> = {
  NEW: { label: "Novo", tone: "success" },
  DUPLICATE: { label: "Já importado", tone: "neutral" },
  UNKNOWN_ASSET: { label: "Ativo não cadastrado", tone: "warning" },
  IGNORED: { label: "Ignorado", tone: "neutral" },
  INVALID: { label: "Inválido", tone: "danger" },
};

/** Lines that would be imported, and so can be left out by the user. */
const SKIPPABLE = new Set(["NEW", "UNKNOWN_ASSET"]);

function describe(line: ImportPreviewDTO["lines"][number]): string {
  if (line.trade_kind) return TRADE_LABELS[line.trade_kind as "BUY" | "SELL"];
  if (line.earning_kind) return EARNING_LABELS[line.earning_kind as keyof typeof EARNING_LABELS] ?? line.description;
  if (line.event_kind) return EVENT_LABELS[line.event_kind as keyof typeof EVENT_LABELS] ?? line.description;
  return line.description;
}

/**
 * Terms of a Treasury bond or bank security: B3 statements never carry the contracted rate,
 * so it is typed here (the rest comes suggested by the preview).
 */
interface TermChoice {
  base: ImportFixedIncomeTermDTO;
  name: string;
  indexer: FixedIncomeIndexer;
  ratePercent: string;
  issueDate: string;
  maturityDate: string;
  liquidity: FixedIncomeLiquidity;
}

/** How an unknown ticker is registered with the import (the same registration as the research flow). */
interface NewAssetChoice {
  selected: boolean;
  asset_type: AssetType | "";
  arca_class: ArcaClass | "";
  suggested: ArcaClass | null;
  term: TermChoice | null;
}

function initialChoices(preview: ImportPreviewDTO): Record<string, NewAssetChoice> {
  return Object.fromEntries(
    preview.unknown_tickers.map((u) => {
      const base = u.fixed_income_term ?? null;
      return [
        u.ticker,
        {
          selected: Boolean(u.asset_type) && !base,
          asset_type: u.asset_type ?? "",
          arca_class: u.arca_class ?? "",
          suggested: u.arca_class ?? null,
          term: base && {
            base,
            name: u.name ?? u.ticker,
            indexer: base.indexer,
            ratePercent: "",
            issueDate: base.issue_date ?? "",
            maturityDate: base.maturity_date ?? "",
            liquidity: base.liquidity ?? "AT_MATURITY",
          },
        },
      ];
    }),
  );
}

/** A choice can be registered once its type (and, for fixed income, rate and issue date) is known. */
function ready(choice: NewAssetChoice): boolean {
  if (!choice.asset_type) return false;
  if (!choice.term) return true;
  return parseDecimal(choice.term.ratePercent) !== null && Boolean(choice.term.issueDate) && Boolean(choice.term.name.trim());
}

function toNewAssets(choices: Record<string, NewAssetChoice>): ImportNewAssetRequest[] {
  return Object.entries(choices)
    .filter(([, c]) => c.selected && ready(c))
    .map(([ticker, c]) => {
      const request: ImportNewAssetRequest = { ticker, asset_type: c.asset_type || null, arca_class: c.arca_class || null };
      if (!c.term) return request;
      const { base, name, indexer, ratePercent, issueDate, maturityDate, liquidity } = c.term;
      return {
        ...request,
        name: name.trim(),
        fixed_income_term: {
          instrument_kind: base.instrument_kind,
          indexer,
          contracted_rate: percentToContractedRate(parseDecimal(ratePercent) as number),
          issue_date: issueDate,
          maturity_date: maturityDate || null,
          tax_exempt: base.tax_exempt ?? false,
          liquidity,
          issuer: base.issuer ?? null,
        },
      };
    });
}

/** B3 statement import: preview what each line becomes, then apply the new lines at once. */
export function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewDTO | null>(null);
  const [choices, setChoices] = useState<Record<string, NewAssetChoice>>({});
  const [skipped, setSkipped] = useState<number[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [result, setResult] = useState<ImportCommitDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [busy, setBusy] = useState(false);

  /** `keepChoices` keeps what was typed for the tickers still unknown (when only the skipped lines changed). */
  const runPreview = async (chosen: File, skip: number[] = [], keepChoices = false) => {
    setPreviewing(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.ledger.previewImport(chosen, skip);
      setPreview(data);
      setSkipped(skip);
      setChoices((current) => {
        const fresh = initialChoices(data);
        if (!keepChoices) return fresh;
        return Object.fromEntries(Object.entries(fresh).map(([ticker, choice]) => [ticker, current[ticker] ?? choice]));
      });
    } catch (err) {
      setPreview(null);
      setError(errorMessage(err));
    } finally {
      setPreviewing(false);
    }
  };

  const commit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.ledger.commitImport(file, accountId, toNewAssets(choices), skipped));
      setPreview(await api.ledger.previewImport(file, skipped));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  /** Skipping a purchase can leave a later sell without position, so the preview is asked again. */
  const toggleLine = (lineNo: number, include: boolean) => {
    if (!file) return;
    const next = include ? skipped.filter((n) => n !== lineNo) : [...skipped, lineNo].sort((a, b) => a - b);
    void runPreview(file, next, true);
  };

  const choose = (ticker: string, change: Partial<NewAssetChoice>) =>
    setChoices((current) => ({ ...current, [ticker]: { ...current[ticker], ...change } }));

  /** Typing the terms selects the security as soon as they are complete. */
  const chooseTerm = (ticker: string, change: Partial<TermChoice>) =>
    setChoices((current) => {
      const previous = current[ticker];
      if (!previous.term) return current;
      const next = { ...previous, term: { ...previous.term, ...change } };
      return { ...current, [ticker]: { ...next, selected: ready(next) && (previous.selected || !ready(previous)) } };
    });

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
    .filter(([, c]) => c.selected && ready(c))
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
            <strong>Extratos › Movimentação</strong> (proventos, eventos, Tesouro Direto e CDB/LCI/LCA). Importar o mesmo
            arquivo de novo não duplica nada.
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
                disabled={busy || previewing}
                onChange={(e) => {
                  const chosen = e.target.files?.[0] ?? null;
                  setFile(chosen);
                  if (chosen) void runPreview(chosen);
                }}
              />
            </div>
            <div className="app-field">
              <label htmlFor="import-account">Conta dos lançamentos</label>
              <AccountSelect id="import-account" value={accountId} onChange={setAccountId} disabled={busy || previewing} />
            </div>
          </div>
        </section>

        {previewing && (
          <div className="app-busy-overlay" role="status" aria-live="polite">
            <Spinner size="sm" />
            <span>Analisando extrato da B3…</span>
          </div>
        )}

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
                  confira o tipo e o quadrante ARCA; os demonstrativos são buscados logo depois. Títulos do Tesouro e
                  CDBs (um ativo por emissor) precisam da taxa contratada, que a B3 não informa.
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
                        const term = choice.term;
                        return (
                          <Fragment key={u.ticker}>
                            <tr>
                              <td>
                                <label className="app-check">
                                  <input
                                    type="checkbox"
                                    checked={choice.selected}
                                    disabled={busy || previewing || !ready(choice)}
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
                                  disabled={busy || previewing || Boolean(term)}
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
                                  disabled={busy || previewing || !choice.asset_type}
                                  onChange={(value) => choose(u.ticker, { arca_class: value })}
                                />
                              </td>
                            </tr>
                            {term && (
                              <tr>
                                <td colSpan={3}>
                                  <div className="app-field-grid">
                                    <div className="app-field">
                                      <label htmlFor={`name-${u.ticker}`}>Nome</label>
                                      <input
                                        id={`name-${u.ticker}`}
                                        value={term.name}
                                        disabled={busy || previewing}
                                        onChange={(e) => chooseTerm(u.ticker, { name: e.target.value })}
                                      />
                                    </div>
                                    <div className="app-field">
                                      <label htmlFor={`indexer-${u.ticker}`}>Indexador</label>
                                      <select
                                        id={`indexer-${u.ticker}`}
                                        value={term.indexer}
                                        disabled={busy || previewing}
                                        onChange={(e) => chooseTerm(u.ticker, { indexer: e.target.value as FixedIncomeIndexer })}
                                      >
                                        {INDEXERS.map((indexer) => (
                                          <option key={indexer} value={indexer}>
                                            {indexer}
                                          </option>
                                        ))}
                                      </select>
                                    </div>
                                    <div className="app-field">
                                      <label htmlFor={`rate-${u.ticker}`}>Taxa contratada</label>
                                      <input
                                        id={`rate-${u.ticker}`}
                                        inputMode="decimal"
                                        placeholder={INDEXER_HINTS[term.indexer]}
                                        value={term.ratePercent}
                                        disabled={busy || previewing}
                                        onChange={(e) => chooseTerm(u.ticker, { ratePercent: e.target.value })}
                                      />
                                    </div>
                                    <div className="app-field">
                                      <label htmlFor={`issue-${u.ticker}`}>Data de emissão</label>
                                      <input
                                        id={`issue-${u.ticker}`}
                                        type="date"
                                        value={term.issueDate}
                                        disabled={busy || previewing}
                                        onChange={(e) => chooseTerm(u.ticker, { issueDate: e.target.value })}
                                      />
                                    </div>
                                    <div className="app-field">
                                      <label htmlFor={`maturity-${u.ticker}`}>Vencimento</label>
                                      <input
                                        id={`maturity-${u.ticker}`}
                                        type="date"
                                        value={term.maturityDate}
                                        disabled={busy || previewing}
                                        onChange={(e) => chooseTerm(u.ticker, { maturityDate: e.target.value })}
                                      />
                                    </div>
                                    <div className="app-field">
                                      <label htmlFor={`liquidity-${u.ticker}`}>Liquidez</label>
                                      <select
                                        id={`liquidity-${u.ticker}`}
                                        value={term.liquidity}
                                        disabled={busy || previewing}
                                        onChange={(e) => chooseTerm(u.ticker, { liquidity: e.target.value as FixedIncomeLiquidity })}
                                      >
                                        {(Object.keys(LIQUIDITY_LABELS) as FixedIncomeLiquidity[]).map((liquidity) => (
                                          <option key={liquidity} value={liquidity}>
                                            {LIQUIDITY_LABELS[liquidity]}
                                          </option>
                                        ))}
                                      </select>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
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
                disabled={busy || previewing || newLines + fromUnknown === 0}
                onClick={() => void commit()}
              >
                {busy && <Spinner size="sm" />}
                <span>{busy ? "Importando…" : `Importar ${newLines + fromUnknown} linha(s)`}</span>
              </button>
              <span className="app-muted">
                Desmarque as linhas que não quer importar. Vendas sem a compra correspondente aparecem como inválidas e
                ficam de fora.
              </span>
            </div>

            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Importar</th>
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
                      <td>
                        {(SKIPPABLE.has(line.status) || skipped.includes(line.line_no)) && (
                          <input
                            type="checkbox"
                            aria-label={`Importar linha ${line.line_no}`}
                            checked={!skipped.includes(line.line_no)}
                            disabled={busy || previewing}
                            onChange={(e) => toggleLine(line.line_no, e.target.checked)}
                          />
                        )}
                      </td>
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
