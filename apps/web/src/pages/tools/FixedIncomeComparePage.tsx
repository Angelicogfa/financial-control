import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  AssetResponseDTO,
  FixedIncomeComparisonDTO,
  FixedIncomeOfferRequest,
  OfferIndexer,
  OfferProjectionDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Spinner } from "../../components/States";
import { brl, day, parseDecimal, pct } from "../../utils/format";
import { OFFER_INDEXER_HINTS, OFFER_INDEXER_LABELS, SCENARIO_LABELS } from "../../utils/labels";
import { percentToContractedRate } from "../../utils/rates";

const OFFER_INDEXERS = Object.keys(OFFER_INDEXER_LABELS) as OfferIndexer[];
const MAX_OFFERS = 6;

interface OfferRow {
  key: number;
  assetId: number | "";
  label: string;
  indexer: OfferIndexer;
  rate: string;
  termDays: string;
  graceDays: string;
  taxExempt: boolean;
}

let nextKey = 0;
function emptyRow(overrides: Partial<OfferRow> = {}): OfferRow {
  nextKey += 1;
  return {
    key: nextKey,
    assetId: "",
    label: "",
    indexer: "CDI_PERCENT",
    rate: "",
    termDays: "720",
    graceDays: "",
    taxExempt: false,
    ...overrides,
  };
}

/** Build the API offer: a portfolio asset travels by id, a typed offer with its terms (ADR 0006). */
export function toOfferRequest(row: OfferRow): FixedIncomeOfferRequest {
  if (row.assetId !== "") return { asset_id: row.assetId, label: row.label.trim() || null };
  const rate = parseDecimal(row.rate);
  const term = parseDecimal(row.termDays);
  const grace = parseDecimal(row.graceDays);
  return {
    label: row.label.trim() || null,
    indexer: row.indexer,
    rate: rate === null ? null : percentToContractedRate(rate),
    term_days: term === null ? null : Math.round(term),
    grace_days: grace === null ? null : Math.round(grace),
    tax_exempt: row.taxExempt,
  };
}

function OfferFields({
  row,
  index,
  assets,
  disabled,
  onChange,
  onRemove,
}: Readonly<{
  row: OfferRow;
  index: number;
  assets: AssetResponseDTO[];
  disabled: boolean;
  onChange: (change: Partial<OfferRow>) => void;
  onRemove?: () => void;
}>) {
  const id = (name: string) => `offer-${row.key}-${name}`;
  const fromPortfolio = row.assetId !== "";
  return (
    <fieldset className="app-card app-card-padded" disabled={disabled}>
      <legend className="app-card-heading">Título {index + 1}</legend>
      <div className="app-field-grid">
        <div className="app-field">
          <label htmlFor={id("asset")}>Origem</label>
          <select
            id={id("asset")}
            value={row.assetId}
            onChange={(e) => onChange({ assetId: e.target.value === "" ? "" : Number(e.target.value) })}
          >
            <option value="">Informar à mão</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.ticker} — {a.name}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <label htmlFor={id("label")}>Nome</label>
          <input id={id("label")} value={row.label} onChange={(e) => onChange({ label: e.target.value })} placeholder={`Título ${index + 1}`} />
        </div>
        {!fromPortfolio && (
          <>
            <div className="app-field">
              <label htmlFor={id("indexer")}>Indexador</label>
              <select id={id("indexer")} value={row.indexer} onChange={(e) => onChange({ indexer: e.target.value as OfferIndexer })}>
                {OFFER_INDEXERS.map((k) => (
                  <option key={k} value={k}>
                    {OFFER_INDEXER_LABELS[k]}
                  </option>
                ))}
              </select>
            </div>
            <div className="app-field">
              <label htmlFor={id("rate")}>Taxa</label>
              <input
                id={id("rate")}
                inputMode="decimal"
                value={row.rate}
                onChange={(e) => onChange({ rate: e.target.value })}
                placeholder={OFFER_INDEXER_HINTS[row.indexer]}
                required
              />
            </div>
            <div className="app-field">
              <label htmlFor={id("term")}>Prazo (dias corridos)</label>
              <input id={id("term")} inputMode="numeric" value={row.termDays} onChange={(e) => onChange({ termDays: e.target.value })} required />
            </div>
            <div className="app-field">
              <label htmlFor={id("grace")}>Carência (dias)</label>
              <input id={id("grace")} inputMode="numeric" value={row.graceDays} onChange={(e) => onChange({ graceDays: e.target.value })} placeholder="0 = liquidez diária" />
            </div>
            <div className="app-field">
              <label className="app-check">
                <input type="checkbox" checked={row.taxExempt} onChange={(e) => onChange({ taxExempt: e.target.checked })} />
                Isento de IR (LCI, LCA, CRI, CRA, debênture incentivada)
              </label>
            </div>
          </>
        )}
      </div>
      {fromPortfolio && <p className="app-card-hint">Indexador, taxa, vencimento e isenção vêm do cadastro do ativo; o prazo conta a partir de hoje.</p>}
      {onRemove && (
        <div className="app-form-actions">
          <button type="button" className="app-secondary-button" onClick={onRemove}>
            Remover título
          </button>
        </div>
      )}
    </fieldset>
  );
}

function Results({ result }: Readonly<{ result: FixedIncomeComparisonDTO }>) {
  const names = result.scenarios.map((s) => s.name);
  const [scenario, setScenario] = useState(names.includes("BASE") ? "BASE" : names[0]);
  const projections = result.projections.filter((p) => p.scenario === scenario);
  const best = result.best_by_scenario[scenario];
  const current = result.scenarios.find((s) => s.name === scenario);
  const breakEvens = result.break_evens.filter((b) => b.scenario === scenario);
  const offerOf = (label: string) => result.offers.find((o) => o.label === label);

  return (
    <div className="app-page-stack">
      <section className="app-card app-card-padded">
        <h2 className="app-card-heading">Cenário</h2>
        <div className="app-button-row" role="group" aria-label="Cenários">
          {result.scenarios.map((s) => (
            <button
              key={s.name}
              type="button"
              className={s.name === scenario ? "app-primary-button" : "app-secondary-button"}
              aria-pressed={s.name === scenario}
              onClick={() => setScenario(s.name)}
            >
              {SCENARIO_LABELS[s.name] ?? s.name}
            </button>
          ))}
        </div>
        {current && (
          <p className="app-muted">
            CDI {pct(current.annual_cdi_rate, 2)} a.a. · IPCA {pct(current.annual_ipca_rate, 2)} a.a. · aplicação de{" "}
            {brl(result.principal)} em {day(result.as_of_date)}
          </p>
        )}
      </section>

      <section>
        <h2 className="app-card-heading">No vencimento de cada título</h2>
        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Título</th>
                <th className="app-numeric">Taxa bruta a.a.</th>
                <th className="app-numeric">Prazo</th>
                <th className="app-numeric">Bruto</th>
                <th className="app-numeric">IR</th>
                <th className="app-numeric">Líquido</th>
                <th className="app-numeric">Taxa líquida a.a.</th>
              </tr>
            </thead>
            <tbody>
              {projections.map((p) => (
                <tr key={p.label}>
                  <td>
                    {p.label} {offerOf(p.label)?.tax_exempt && <Badge tone="success">Isento</Badge>}
                  </td>
                  <td className="app-numeric">{pct(p.gross_annual_rate, 2)}</td>
                  <td className="app-numeric">{p.at_maturity.days} dias</td>
                  <td className="app-numeric">{brl(p.at_maturity.gross_value)}</td>
                  <td className="app-numeric">
                    {brl(p.at_maturity.income_tax + p.at_maturity.iof)}
                    <div className="app-muted">{pct(p.at_maturity.income_tax_rate, 1)}</div>
                  </td>
                  <td className="app-numeric">{brl(p.at_maturity.net_value)}</td>
                  <td className="app-numeric">{pct(p.at_maturity.net_annual_rate, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="app-card-heading">Na janela comum de {result.common_window_days} dias</h2>
        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Título</th>
                <th className="app-numeric">Líquido</th>
                <th className="app-numeric">Taxa líquida a.a.</th>
                <th>Resgate</th>
              </tr>
            </thead>
            <tbody>
              {projections.map((p) => (
                <tr key={p.label}>
                  <td>
                    {p.label} {p.label === best && <Badge tone="success">Melhor</Badge>}
                  </td>
                  <td className="app-numeric">{brl(p.at_common_window.net_value)}</td>
                  <td className="app-numeric">{pct(p.at_common_window.net_annual_rate, 2)}</td>
                  <td>{p.at_common_window.redeemable ? "Disponível" : <Badge tone="warning">Em carência</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {breakEvens.length > 0 && (
          <ul aria-label="Ponto de empate">
            {breakEvens.map((b) => (
              <li key={`${b.first}-${b.second}`}>
                {b.winner === null || b.winner === undefined
                  ? `${b.first} × ${b.second}: sem prazo comum de resgate para comparar.`
                  : b.always_ahead
                    ? `${b.winner} rende mais que ${b.winner === b.first ? b.second : b.first} em qualquer prazo da janela.`
                    : `${b.winner} passa a render mais que ${b.winner === b.first ? b.second : b.first} a partir de ${b.break_even_days} dias.`}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="app-card-heading">Taxa equivalente por faixa de IR</h2>
        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Título</th>
                {projections[0]?.equivalent_rates.map((r, i, all) => (
                  <th key={r.up_to_days ?? "open"} className="app-numeric">
                    {r.up_to_days === null || r.up_to_days === undefined ? `> ${all[i - 1]?.up_to_days} dias` : `até ${r.up_to_days} dias`} ({pct(r.income_tax_rate, 1)})
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {projections.map((p: OfferProjectionDTO) => {
                const exempt = offerOf(p.label)?.tax_exempt;
                return (
                  <tr key={p.label}>
                    <td>
                      {p.label}
                      <div className="app-muted">{exempt ? "equivale a um tributado de" : "equivale a um isento de"}</div>
                    </td>
                    {p.equivalent_rates.map((r) => (
                      <td key={r.up_to_days ?? "open"} className="app-numeric">
                        {pct(exempt ? r.taxed_equivalent_rate : r.exempt_equivalent_rate, 2)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="app-muted">
          Equivalência pela convenção de mercado (isento = tributado × (1 − alíquota)); o valor líquido acima aplica o IR
          sobre o ganho acumulado no resgate.
        </p>
      </section>
    </div>
  );
}

export function FixedIncomeComparePage() {
  const [params] = useSearchParams();
  const preset = Number(params.get("asset"));
  const assets = useApi("compare-assets", () => api.assets.list(true));
  const fixedIncome = (assets.data?.items ?? []).filter((a) => a.fixed_income_term);
  const [rows, setRows] = useState<OfferRow[]>(() => [
    emptyRow(preset ? { assetId: preset } : { rate: "110" }),
    emptyRow({ rate: "90", taxExempt: true }),
  ]);
  const [principal, setPrincipal] = useState("10000");
  const [result, setResult] = useState<FixedIncomeComparisonDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const update = (key: number, change: Partial<OfferRow>) =>
    setRows((all) => all.map((r) => (r.key === key ? { ...r, ...change } : r)));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      setResult(
        await api.tax.compare({
          offers: rows.map(toOfferRequest),
          principal: parseDecimal(principal) ?? 10000,
        }),
      );
    } catch (err) {
      setResult(null);
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page">
      <PageHeader
        title="Comparar renda fixa"
        subtitle="Tributado × isento: valor e taxa líquidos, taxa equivalente por faixa e ponto de empate."
      />
      <form className="app-page-stack" onSubmit={submit} aria-busy={saving}>
        {error && (
          <p className="app-error-banner" role="alert">
            {error}
          </p>
        )}
        <section className="app-card app-card-padded">
          <div className="app-field">
            <label htmlFor="compare-principal">Valor aplicado (R$)</label>
            <input id="compare-principal" inputMode="decimal" value={principal} onChange={(e) => setPrincipal(e.target.value)} disabled={saving} />
          </div>
        </section>
        {rows.map((row, index) => (
          <OfferFields
            key={row.key}
            row={row}
            index={index}
            assets={fixedIncome}
            disabled={saving}
            onChange={(change) => update(row.key, change)}
            onRemove={rows.length > 2 ? () => setRows((all) => all.filter((r) => r.key !== row.key)) : undefined}
          />
        ))}
        <div className="app-form-actions">
          <button type="submit" className="app-primary-button" disabled={saving}>
            {saving && <Spinner size="sm" />}
            <span>{saving ? "Comparando…" : "Comparar"}</span>
          </button>
          {rows.length < MAX_OFFERS && (
            <button type="button" className="app-secondary-button" onClick={() => setRows((all) => [...all, emptyRow()])} disabled={saving}>
              Adicionar título
            </button>
          )}
        </div>
      </form>
      {result && <Results key={JSON.stringify(result.scenarios)} result={result} />}
    </div>
  );
}
