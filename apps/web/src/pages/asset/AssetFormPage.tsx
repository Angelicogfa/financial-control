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
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Hint } from "../../components/Hint";
import { PageHeader } from "../../components/PageHeader";
import { Async } from "../../components/States";
import { parseDecimal, today } from "../../utils/format";
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
import { DEFAULT_RATE_PERCENT, contractedRateToPercent, percentToContractedRate } from "../../utils/rates";

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
  issueDate: today(),
  maturityDate: "",
  taxExempt: false,
  liquidity: "AT_MATURITY",
  issuer: "",
};

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
          issueDate: term.issue_date,
          maturityDate: term.maturity_date ?? "",
          taxExempt: term.tax_exempt ?? false,
          liquidity: term.liquidity ?? "AT_MATURITY",
          issuer: term.issuer ?? "",
        }
      : {}),
  };
}

const CODE_GENERATED: AssetType[] = ["FIXED_INCOME", "TREASURY", "CASH"];

function AssetForm({ asset }: Readonly<{ asset: AssetResponseDTO | null }>) {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>(() => (asset ? fromAsset(asset) : EMPTY));
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fixedIncome = FIXED_INCOME_TYPES.includes(form.assetType);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));

  // ARCA class suggested by the instrument's exposure (ETF catalog) or by its type.
  useEffect(() => {
    if (asset || !form.ticker.trim() || CODE_GENERATED.includes(form.assetType)) {
      setSuggestion(null);
      return;
    }
    const timer = window.setTimeout(() => {
      api.assets
        .classify(form.ticker.trim(), form.assetType)
        .then((s) => setSuggestion(`${ARCA_LABELS[s.arca_class]} — ${s.reason}`))
        .catch(() => setSuggestion(null));
    }, 400);
    return () => window.clearTimeout(timer);
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
            issue_date: form.issueDate,
            maturity_date: form.maturityDate || null,
            tax_exempt: form.taxExempt,
            liquidity: form.liquidity,
            issuer: form.issuer.trim() || null,
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
    try {
      await api.assets.archive(asset.id);
      navigate("/portfolio");
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <form className="app-card app-card-padded" onSubmit={submit}>
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
            placeholder={CODE_GENERATED.includes(form.assetType) ? "Gerado automaticamente" : "Ex.: WEGE3"}
            onChange={(e) => set("ticker", e.target.value.toUpperCase())}
            required={!CODE_GENERATED.includes(form.assetType)}
          />
        </div>
        <div className="app-field">
          <label htmlFor="asset-name">Nome</label>
          <input id="asset-name" value={form.name} onChange={(e) => set("name", e.target.value)} required />
        </div>
        <div className="app-field">
          <span className="app-field-label">
            <label htmlFor="asset-class">Classe ARCA</label>
            {suggestion && !form.arcaClass && <Hint about="Classe ARCA">{`Sugestão: ${suggestion}`}</Hint>}
          </span>
          <select
            id="asset-class"
            value={form.arcaClass}
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
            </div>
            <div className="app-field">
              <label htmlFor="fi-issue">Aplicação</label>
              <input
                id="fi-issue"
                type="date"
                value={form.issueDate}
                onChange={(e) => set("issueDate", e.target.value)}
                required
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
        <button type="submit" className="app-primary-button" disabled={saving}>
          {saving ? "Salvando…" : asset ? "Salvar alterações" : "Cadastrar ativo"}
        </button>
        <button type="button" className="app-secondary-button" onClick={() => navigate(-1)}>
          Cancelar
        </button>
        {asset?.is_active && (
          <button type="button" className="app-danger-button" onClick={() => void archive()}>
            Arquivar
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
