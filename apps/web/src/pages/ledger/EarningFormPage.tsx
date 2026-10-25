import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { EarningKind, EarningResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { PageHeader } from "../../components/PageHeader";
import { Async } from "../../components/States";
import { parseDecimal, today } from "../../utils/format";
import { EARNING_KINDS, EARNING_LABELS } from "../../utils/labels";
import { AccountSelect, AssetSelect } from "./AssetSelect";

function EarningForm({ earning }: Readonly<{ earning: EarningResponseDTO | null }>) {
  const navigate = useNavigate();
  const decimal = (v: number | undefined | null) => (v === undefined || v === null ? "" : String(v).replace(".", ","));
  const [assetId, setAssetId] = useState<number | "">(earning?.asset_id ?? "");
  const [currency, setCurrency] = useState("BRL");
  const [kind, setKind] = useState<EarningKind>(earning?.kind ?? "DIVIDEND");
  const [paymentDate, setPaymentDate] = useState(earning?.payment_date ?? today());
  const [gross, setGross] = useState(decimal(earning?.gross_amount));
  const [tax, setTax] = useState(earning ? decimal(earning.withholding_tax) : "0");
  const [fx, setFx] = useState(earning ? decimal(earning.fx_rate) : "1");
  const [accountId, setAccountId] = useState<number | null>(earning?.account_id ?? null);
  const [notes, setNotes] = useState(earning?.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const grossValue = parseDecimal(gross);
    if (assetId === "" || !grossValue) {
      setError("Preencha ativo e valor bruto.");
      return;
    }
    const body = {
      kind,
      payment_date: paymentDate,
      gross_amount: grossValue,
      withholding_tax: parseDecimal(tax) ?? 0,
      fx_rate: parseDecimal(fx) ?? 1,
      notes: notes.trim() || null,
      account_id: accountId,
    };
    setSaving(true);
    setError(null);
    try {
      if (earning) await api.ledger.updateEarning(earning.id, body);
      else await api.ledger.createEarning({ ...body, asset_id: assetId });
      navigate("/ledger?tab=earnings");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="app-card app-card-padded" onSubmit={submit}>
      {error && <p className="app-error-banner" role="alert">{error}</p>}
      <div className="app-field-grid">
        <div className="app-field">
          <label htmlFor="earning-asset">Ativo</label>
          <AssetSelect
            id="earning-asset"
            value={assetId}
            disabled={earning !== null}
            onChange={(a) => {
              setAssetId(a?.id ?? "");
              setCurrency(a?.currency ?? "BRL");
            }}
          />
        </div>
        <div className="app-field">
          <label htmlFor="earning-kind">Tipo</label>
          <select id="earning-kind" value={kind} onChange={(e) => setKind(e.target.value as EarningKind)}>
            {EARNING_KINDS.map((k) => (
              <option key={k} value={k}>
                {EARNING_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
        <div className="app-field">
          <label htmlFor="earning-date">Pagamento</label>
          <input id="earning-date" type="date" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} required />
        </div>
        <div className="app-field">
          <label htmlFor="earning-gross">Valor bruto ({currency})</label>
          <input id="earning-gross" inputMode="decimal" value={gross} onChange={(e) => setGross(e.target.value)} required />
        </div>
        <div className="app-field">
          <label htmlFor="earning-tax">IR retido</label>
          <input id="earning-tax" inputMode="decimal" value={tax} onChange={(e) => setTax(e.target.value)} />
          {kind === "JCP" && <small>JCP tem 15% retidos na fonte.</small>}
        </div>
        {currency !== "BRL" && (
          <div className="app-field">
            <label htmlFor="earning-fx">Câmbio do pagamento</label>
            <input id="earning-fx" inputMode="decimal" value={fx} onChange={(e) => setFx(e.target.value)} required />
          </div>
        )}
        <div className="app-field">
          <label htmlFor="earning-account">Conta</label>
          <AccountSelect id="earning-account" value={accountId} onChange={setAccountId} />
        </div>
      </div>
      <div className="app-field" style={{ marginTop: "var(--space-3)" }}>
        <label htmlFor="earning-notes">Observação</label>
        <input id="earning-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      <div className="app-form-actions">
        <button type="submit" className="app-primary-button" disabled={saving}>
          {saving ? "Salvando…" : "Salvar"}
        </button>
        <button type="button" className="app-secondary-button" onClick={() => navigate(-1)}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

export function EarningFormPage() {
  const { id } = useParams();
  const earning = useApi(`earning-${id ?? "new"}`, () => (id ? api.ledger.earning(Number(id)) : Promise.resolve(null)));
  return (
    <div className="app-page" style={{ maxWidth: 860 }}>
      <PageHeader title={id ? "Editar provento" : "Novo provento"} />
      {id ? <Async state={earning}>{(data) => <EarningForm earning={data} />}</Async> : <EarningForm earning={null} />}
    </div>
  );
}
