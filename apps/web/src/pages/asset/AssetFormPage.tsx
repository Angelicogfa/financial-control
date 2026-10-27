import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  ArcaClass,
  AssetPurpose,
  AssetResponseDTO,
  AssetType,
  ChecklistProfile,
  FixedIncomeIndexer,
  FixedIncomeInstrumentKind,
  FixedIncomeLiquidity,
  TreasuryBondDTO,
  TreasurySearchResponseDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Hint } from "../../components/Hint";
import { PageHeader } from "../../components/PageHeader";
import { Async, Spinner } from "../../components/States";
import { brl, day, parseDecimal } from "../../utils/format";
import {
  ARCA_CLASSES,
  ARCA_LABELS,
  ASSET_TYPE_LABELS,
  ASSET_TYPES,
  FIXED_INCOME_TYPES,
  INDEXER_HINTS,
  INDEXERS,
  INSTRUMENT_KINDS,
  INSTRUMENT_LABELS,
  LIQUIDITY_LABELS,
  PROFILE_LABELS,
  PROFILES,
  PURPOSE_LABELS,
} from "../../utils/labels";
import {
  DEFAULT_RATE_PERCENT,
  contractedRateToPercent,
  formatTreasuryRate,
  percentToContractedRate,
} from "../../utils/rates";

interface FormState {
  ticker: string;
  name: string;
  assetType: AssetType;
  arcaClass: ArcaClass | "";
  purpose: AssetPurpose;
  manualPrice: string;
  profile: ChecklistProfile | "";
  notes: string;
  active: boolean;
  instrumentKind: FixedIncomeInstrumentKind;
  indexer: FixedIncomeIndexer;
  ratePercent: string;
  issueDate: string;
  maturityDate: string;
  taxExempt: boolean;
  liquidity: FixedIncomeLiquidity;
  issuer: string;
  semiannualCoupons: boolean;
}

const EMPTY: FormState = {
  ticker: "",
  name: "",
  assetType: "STOCK_BR",
  arcaClass: "",
  purpose: "ARCA",
  manualPrice: "",
  profile: "",
  notes: "",
  active: true,
  instrumentKind: "CDB",
  indexer: "CDI",
  ratePercent: DEFAULT_RATE_PERCENT.CDI,
  issueDate: "",
  maturityDate: "",
  taxExempt: false,
  liquidity: "AT_MATURITY",
  issuer: "",
  semiannualCoupons: false,
};

const TREASURY_KINDS: FixedIncomeInstrumentKind[] = ["TESOURO_SELIC", "TESOURO_IPCA", "TESOURO_PRE"];

/** Tesouro Prefixado and IPCA+: each purchase accrues at the rate implied by the price paid. */
const PRICE_IMPLIED_KINDS: FixedIncomeInstrumentKind[] = ["TESOURO_PRE", "TESOURO_IPCA"];

function fromAsset(asset: AssetResponseDTO): FormState {
  const term = asset.fixed_income_term;
  return {
    ...EMPTY,
    ticker: asset.ticker,
    name: asset.name,
    assetType: asset.asset_type,
    arcaClass: asset.arca_class,
    purpose: asset.purpose ?? "ARCA",
    manualPrice: asset.manual_price ?? "",
    profile: asset.checklist_profile,
    notes: asset.notes ?? "",
    active: asset.is_active,
    ...(term
      ? {
          instrumentKind: term.instrument_kind,
          indexer: term.indexer,
          ratePercent: String(contractedRateToPercent(term.contracted_rate)).replace(".", ","),
          issueDate: term.issue_date ?? "",
          maturityDate: term.maturity_date ?? "",
          taxExempt: term.tax_exempt ?? false,
          liquidity: term.liquidity ?? "AT_MATURITY",
          issuer: term.issuer ?? "",
          semiannualCoupons: term.semiannual_coupons ?? false,
        }
      : {}),
  };
}

const CODE_GENERATED: AssetType[] = ["FIXED_INCOME", "TREASURY", "CASH"];

function TreasuryPicker({ onSelect }: Readonly<{ onSelect: (bond: TreasuryBondDTO) => void }>) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<TreasurySearchResponseDTO | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.research.treasury({ q: query.trim() || undefined }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <fieldset className="app-fieldset">
      <legend>Buscar título do Tesouro Direto (Tesouro Transparente)</legend>
      <div className="app-filter-bar" style={{ marginBottom: 0 }}>
        <div className="app-field" style={{ flex: 1 }}>
          <label htmlFor="treasury-search">Título ou vencimento</label>
          <input
            id="treasury-search"
            value={query}
            disabled={loading}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ex.: Selic, IPCA, 2031"
          />
        </div>
        <button
          type="button"
          className="app-secondary-button"
          disabled={loading}
          onClick={() => void search()}
        >
          {loading && <Spinner size="sm" />}
          {loading ? "Buscando…" : "Buscar títulos"}
        </button>
      </div>
      {error && <p className="app-error-banner">{error}</p>}
      {result?.unavailable_reason && <p className="app-info-banner">{result.unavailable_reason}</p>}
      {result && !result.unavailable_reason && result.results.length === 0 && (
        <p className="app-muted">Nenhum título do Tesouro Direto encontrado para esse filtro.</p>
      )}
      {result && result.results.length > 0 && (
        <div className="app-table-wrap" style={{ marginTop: "var(--space-2)" }}>
          <table className="app-table">
            <thead>
              <tr>
                <th>Título</th>
                <th>Indexador</th>
                <th>Vencimento</th>
                <th className="app-numeric">Taxa compra</th>
                <th className="app-numeric">PU compra</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {result.results.map((bond) => (
                <tr key={bond.symbol}>
                  <td>
                    <span className="app-cell-main">
                      <strong>{bond.name}</strong>
                      <small>{bond.symbol}</small>
                    </span>
                  </td>
                  <td>{bond.indexer}</td>
                  <td>{day(bond.maturity_date)}</td>
                  <td className="app-numeric">{formatTreasuryRate(bond, bond.buy_rate ?? bond.sell_rate)}</td>
                  <td className="app-numeric">{brl(bond.buy_price ?? bond.base_price)}</td>
                  <td className="app-row-actions">
                    <button
                      type="button"
                      className="app-secondary-button"
                      onClick={() => onSelect(bond)}
                    >
                      Usar título
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </fieldset>
  );
}

function AssetForm({ asset }: Readonly<{ asset: AssetResponseDTO | null }>) {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(() => (asset ? fromAsset(asset) : EMPTY));
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const fixedIncome = FIXED_INCOME_TYPES.includes(form.assetType);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));

  const applyTreasuryBond = (bond: TreasuryBondDTO) => {
    setForm((f) => ({
      ...f,
      name: bond.name,
      instrumentKind: bond.instrument_kind,
      indexer: bond.indexer,
      ratePercent: String(bond.contracted_rate_percent).replace(".", ","),
      maturityDate: bond.maturity_date,
      liquidity: bond.liquidity,
      issuer: f.issuer.trim() || "Tesouro Nacional",
      semiannualCoupons: bond.coupon_type === "semestral",
    }));
  };

  // ARCA class suggested by the instrument's exposure (ETF catalog) or by its type.
  useEffect(() => {
    if (asset || !form.ticker.trim() || CODE_GENERATED.includes(form.assetType)) {
      setSuggestion(null);
      setClassifying(false);
      return;
    }
    setClassifying(true);
    const timer = window.setTimeout(() => {
      api.assets
        .classify(form.ticker.trim(), form.assetType)
        .then((s) => setSuggestion(`${ARCA_LABELS[s.arca_class]} — ${s.reason}`))
        .catch(() => setSuggestion(null))
        .finally(() => setClassifying(false));
    }, 400);
    return () => {
      window.clearTimeout(timer);
      setClassifying(false);
    };
  }, [asset, form.ticker, form.assetType]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const rate = parseDecimal(form.ratePercent);
    if (fixedIncome && rate === null) {
      setError("Informe a taxa contratada.");
      return;
    }
    const price = form.manualPrice ? parseDecimal(String(form.manualPrice)) : null;
    const body = {
      name: form.name.trim(),
      asset_type: form.assetType,
      arca_class: form.arcaClass || null,
      purpose: form.purpose,
      manual_price: price,
      checklist_profile: form.profile || null,
      notes: form.notes.trim() || null,
      fixed_income_term: fixedIncome
        ? {
            instrument_kind: form.instrumentKind,
            indexer: form.indexer,
            contracted_rate: percentToContractedRate(rate as number),
            issue_date: form.issueDate || null,
            maturity_date: form.maturityDate || null,
            tax_exempt: form.taxExempt,
            liquidity: form.liquidity,
            issuer: form.issuer.trim() || null,
            semiannual_coupons: TREASURY_KINDS.includes(form.instrumentKind) && form.semiannualCoupons,
          }
        : null,
    };
    setSaving(true);
    try {
      const saved = asset
        ? await api.assets.update(asset.id, { ...body, ticker: form.ticker.trim() || null, is_active: form.active })
        : await api.assets.create({ ...body, ticker: form.ticker.trim() || null });
      navigate(`/asset/${saved.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const archive = async () => {
    if (!asset || !window.confirm(`Arquivar ${asset.ticker}? Ele sai da carteira e do aporte.`)) return;
    setArchiving(true);
    setError(null);
    try {
      await api.assets.archive(asset.id);
      navigate("/portfolio");
    } catch (err) {
      setError(errorMessage(err));
      setArchiving(false);
    }
  };

  return (
    <form className="app-card app-card-padded" onSubmit={submit} aria-busy={saving || archiving}>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      <div className="app-field-grid">
        <div className="app-field">
          <label htmlFor="asset-type">Tipo</label>
          <select
            id="asset-type"
            value={form.assetType}
            disabled={saving || archiving}
            onChange={(e) => set("assetType", e.target.value as AssetType)}
          >
            {ASSET_TYPES.map((t) => (
              <option key={t} value={t}>
                {ASSET_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="asset-ticker">Código</label>
          <input
            id="asset-ticker"
            value={form.ticker}
            disabled={saving || archiving}
            placeholder={CODE_GENERATED.includes(form.assetType) ? "Gerado automaticamente" : "Ex.: WEGE3"}
            onChange={(e) => set("ticker", e.target.value.toUpperCase())}
            required={!CODE_GENERATED.includes(form.assetType)}
          />
        </div>
        <div className="app-field">
          <label htmlFor="asset-name">Nome</label>
          <input
            id="asset-name"
            value={form.name}
            disabled={saving || archiving}
            onChange={(e) => set("name", e.target.value)}
            required
          />
        </div>
        <div className="app-field">
          <span className="app-field-label">
            <label htmlFor="asset-class">Classe ARCA</label>
            {classifying && (
              <output className="app-field-busy">
                <Spinner size="sm" label="Consultando sugestão…" />
              </output>
            )}
            {suggestion && !form.arcaClass && !classifying && (
              <Hint about="Classe ARCA">{`Sugestão: ${suggestion}`}</Hint>
            )}
          </span>
          <select
            id="asset-class"
            value={form.arcaClass}
            disabled={saving || archiving}
            onChange={(e) => set("arcaClass", e.target.value as ArcaClass | "")}
          >
            <option value="">Automática</option>
            {ARCA_CLASSES.map((c) => (
              <option key={c} value={c}>
                {ARCA_LABELS[c]}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="asset-purpose">Objetivo</label>
          <select
            id="asset-purpose"
            value={form.purpose}
            onChange={(e) => set("purpose", e.target.value as AssetPurpose)}
          >
            {(Object.keys(PURPOSE_LABELS) as AssetPurpose[]).map((p) => (
              <option key={p} value={p}>
                {PURPOSE_LABELS[p]}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="asset-profile">Perfil do checklist</label>
          <select
            id="asset-profile"
            value={form.profile}
            onChange={(e) => set("profile", e.target.value as ChecklistProfile | "")}
          >
            <option value="">Padrão do tipo</option>
            {PROFILES.map((p) => (
              <option key={p} value={p}>
                {PROFILE_LABELS[p]}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <span className="app-field-label">
            <label htmlFor="asset-price">Preço manual</label>
            <Hint about="Preço manual">Informe apenas para ativos sem cotação automática de mercado.</Hint>
          </span>
          <input
            id="asset-price"
            inputMode="decimal"
            value={form.manualPrice}
            placeholder="Só sem cotação de mercado"
            onChange={(e) => set("manualPrice", e.target.value)}
          />
        </div>
      </div>

      {form.assetType === "TREASURY" && <TreasuryPicker onSelect={applyTreasuryBond} />}

      {fixedIncome && (
        <fieldset className="app-fieldset">
          <legend>Contrato de renda fixa</legend>
          <div className="app-field-grid">
            <div className="app-field">
              <label htmlFor="fi-kind">Instrumento</label>
              <select
                id="fi-kind"
                value={form.instrumentKind}
                onChange={(e) => set("instrumentKind", e.target.value as FixedIncomeInstrumentKind)}
              >
                {INSTRUMENT_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {INSTRUMENT_LABELS[k]}
                  </option>
                ))}
              </select>
            </div>
            <div className="app-field">
              <label htmlFor="fi-indexer">Indexador</label>
              <select
                id="fi-indexer"
                value={form.indexer}
                onChange={(e) => {
                  const indexer = e.target.value as FixedIncomeIndexer;
                  setForm((f) => ({ ...f, indexer, ratePercent: DEFAULT_RATE_PERCENT[indexer] }));
                }}
              >
                {INDEXERS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </div>
            <div className="app-field">
              <span className="app-field-label">
                <label htmlFor="fi-rate">Taxa (%)</label>
                <Hint about="Taxa">{INDEXER_HINTS[form.indexer]}</Hint>
              </span>
              <input
                id="fi-rate"
                inputMode="decimal"
                value={form.ratePercent}
                onChange={(e) => set("ratePercent", e.target.value)}
                required
              />
              {PRICE_IMPLIED_KINDS.includes(form.instrumentKind) && (
                <span className="app-muted">
                  Referência: cada compra rende pela taxa implícita no preço (PU) pago.
                </span>
              )}
            </div>
            <div className="app-field">
              <span className="app-field-label">
                <label htmlFor="fi-issue">Data de emissão (opcional)</label>
                <Hint about="Data de emissão">
                  Apenas informativa. O rendimento de cada compra é calculado a partir da data da compra informada no lançamento.
                </Hint>
              </span>
              <input
                id="fi-issue"
                type="date"
                value={form.issueDate}
                onChange={(e) => set("issueDate", e.target.value)}
              />
            </div>
            <div className="app-field">
              <label htmlFor="fi-maturity">Vencimento</label>
              <input
                id="fi-maturity"
                type="date"
                value={form.maturityDate}
                onChange={(e) => set("maturityDate", e.target.value)}
              />
            </div>
            <div className="app-field">
              <label htmlFor="fi-liquidity">Liquidez</label>
              <select
                id="fi-liquidity"
                value={form.liquidity}
                onChange={(e) => set("liquidity", e.target.value as FixedIncomeLiquidity)}
              >
                {(Object.keys(LIQUIDITY_LABELS) as FixedIncomeLiquidity[]).map((l) => (
                  <option key={l} value={l}>
                    {LIQUIDITY_LABELS[l]}
                  </option>
                ))}
              </select>
            </div>
            <div className="app-field">
              <label htmlFor="fi-issuer">Emissor</label>
              <input id="fi-issuer" value={form.issuer} onChange={(e) => set("issuer", e.target.value)} />
            </div>
            <label className="app-check">
              <input
                type="checkbox"
                checked={form.taxExempt}
                onChange={(e) => set("taxExempt", e.target.checked)}
              />
              Isento de IR
            </label>
            {TREASURY_KINDS.includes(form.instrumentKind) && (
              <label className="app-check">
                <input
                  type="checkbox"
                  checked={form.semiannualCoupons}
                  onChange={(e) => set("semiannualCoupons", e.target.checked)}
                />
                Paga juros semestrais
              </label>
            )}
          </div>
        </fieldset>
      )}

      <div className="app-field" style={{ marginTop: "var(--space-3)" }}>
        <label htmlFor="asset-notes">Anotações</label>
        <textarea id="asset-notes" rows={3} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
      </div>
      {asset && (
        <label className="app-check" style={{ marginTop: "var(--space-3)" }}>
          <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} />
          Ativo (desmarque para arquivar)
        </label>
      )}

      <div className="app-form-actions">
        <button type="submit" className="app-primary-button" disabled={saving || archiving}>
          {saving && <Spinner size="sm" />}
          {saving ? "Salvando…" : asset ? "Salvar alterações" : "Cadastrar ativo"}
        </button>
        <button
          type="button"
          className="app-secondary-button"
          disabled={saving || archiving}
          onClick={() => navigate(-1)}
        >
          Cancelar
        </button>
        {asset?.is_active && (
          <button
            type="button"
            className="app-danger-button"
            disabled={saving || archiving}
            onClick={() => void archive()}
          >
            {archiving && <Spinner size="sm" />}
            {archiving ? "Arquivando…" : "Arquivar"}
          </button>
        )}
      </div>
    </form>
  );
}

export function AssetFormPage() {
  const { id } = useParams();
  const editing = id !== undefined;
  const asset = useApi(`asset-form-${id ?? "new"}`, () =>
    editing ? api.assets.get(Number(id)) : Promise.resolve(null),
  );
  return (
    <div className="app-page" style={{ maxWidth: 860 }}>
      <PageHeader
        title={editing ? "Editar ativo" : "Novo ativo"}
        subtitle="O ativo entra na carteira quando houver uma compra; sem posição, fica em observação."
      />
      {editing ? (
        <Async state={asset}>{(data) => <AssetForm asset={data} />}</Async>
      ) : (
        <AssetForm asset={null} />
      )}
    </div>
  );
}
