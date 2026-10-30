import { useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { TransactionKind, TransactionResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { PageHeader } from "../../components/PageHeader";
import { Combobox, codeOptions } from "../../components/Combobox";
import { Async, Spinner } from "../../components/States";
import { brl, parseDecimal, today } from "../../utils/format";
import { TRADE_LABELS } from "../../utils/labels";
import { AccountSelect, AssetSelect } from "./AssetSelect";

/** Same rule as the API's `total_brl`: (quantity × price + fees) × FX, null while incomplete. */
function brlTotal(qty: number | null, price: number | null, fees: number, fx: number | null): number | null {
  if (qty === null || price === null || fx === null) return null;
  return Math.round((qty * price + fees) * fx * 100) / 100;
}

function TradeForm({ trade, presetAsset }: Readonly<{ trade: TransactionResponseDTO | null; presetAsset: number | null }>) {
  const navigate = useNavigate();
  const [assetId, setAssetId] = useState<number | "">(trade?.asset_id ?? presetAsset ?? "");
  const [currency, setCurrency] = useState("BRL");
  const [kind, setKind] = useState<TransactionKind>(trade?.kind ?? "BUY");
  const [tradeDate, setTradeDate] = useState(trade?.trade_date ?? today());
  const [qty, setQty] = useState(trade ? String(trade.quantity).replace(".", ",") : "");
  const [price, setPrice] = useState(trade ? String(trade.unit_price).replace(".", ",") : "");
  const [fees, setFees] = useState(trade ? String(trade.fees).replace(".", ",") : "0");
  const [fx, setFx] = useState(trade ? String(trade.fx_rate).replace(".", ",") : "1");
  const [accountId, setAccountId] = useState<number | null>(trade?.account_id ?? null);
  const [notes, setNotes] = useState(trade?.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const totalBrl = brlTotal(parseDecimal(qty), parseDecimal(price), parseDecimal(fees) ?? 0, parseDecimal(fx));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const values = { quantity: parseDecimal(qty), unit_price: parseDecimal(price), fees: parseDecimal(fees) ?? 0, fx_rate: parseDecimal(fx) ?? 1 };
    if (assetId === "" || !values.quantity || values.unit_price === null) {
      setError("Preencha ativo, quantidade e preço.");
      return;
    }
    const body = {
      kind,
      trade_date: tradeDate,
      quantity: values.quantity,
      unit_price: values.unit_price,
      fees: values.fees,
      fx_rate: values.fx_rate,
      notes: notes.trim() || null,
      account_id: accountId,
    };
    setSaving(true);
    setError(null);
    try {
      if (trade) await api.ledger.updateTrade(trade.id, body);
      else await api.ledger.createTrade({ ...body, asset_id: assetId });
      navigate("/ledger");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="app-card app-card-padded" onSubmit={submit} aria-busy={saving}>
      {error && <p className="app-error-banner" role="alert">{error}</p>}
      <div className="app-field-grid">
        <div className="app-field">
          <label htmlFor="trade-asset">Ativo</label>
          <AssetSelect
            id="trade-asset"
            value={assetId}
            disabled={saving || trade !== null}
            onChange={(a) => {
              setAssetId(a?.id ?? "");
              setCurrency(a?.currency ?? "BRL");
            }}
            onResolve={(a) => setCurrency(a?.currency ?? "BRL")}
          />
        </div>
        <div className="app-field">
          <label htmlFor="trade-kind">Operação</label>
          <Combobox
            id="trade-kind"
            value={kind}
            onChange={setKind}
            disabled={saving}
            options={codeOptions(Object.keys(TRADE_LABELS) as TransactionKind[], TRADE_LABELS)}
          />
        </div>
        <div className="app-field">
          <label htmlFor="trade-date">Data</label>
          <input id="trade-date" type="date" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} required disabled={saving} />
        </div>
        <div className="app-field">
          <label htmlFor="trade-qty">Quantidade</label>
          <input id="trade-qty" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} required disabled={saving} />
        </div>
        <div className="app-field">
          <label htmlFor="trade-price">Preço unitário ({currency})</label>
          <input id="trade-price" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} required disabled={saving} />
        </div>
        <div className="app-field">
          <label htmlFor="trade-fees">Taxas</label>
          <input id="trade-fees" inputMode="decimal" value={fees} onChange={(e) => setFees(e.target.value)} disabled={saving} />
        </div>
        {currency !== "BRL" && (
          <div className="app-field">
            <label htmlFor="trade-fx">Câmbio {currency}/BRL do dia</label>
            <input id="trade-fx" inputMode="decimal" value={fx} onChange={(e) => setFx(e.target.value)} required disabled={saving} />
            <output htmlFor="trade-qty trade-price trade-fees trade-fx" className="app-muted">
              Total em reais: {brl(totalBrl)}
            </output>
          </div>
        )}
        <div className="app-field">
          <label htmlFor="trade-account">Conta</label>
          <AccountSelect id="trade-account" value={accountId} onChange={setAccountId} disabled={saving} />
        </div>
      </div>
      <div className="app-field" style={{ marginTop: "var(--space-3)" }}>
        <label htmlFor="trade-notes">Observação</label>
        <input id="trade-notes" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={saving} />
      </div>
      <div className="app-form-actions">
        <button type="submit" className="app-primary-button" disabled={saving}>
          {saving && <Spinner size="sm" />}
          <span>{saving ? "Salvando…" : "Salvar"}</span>
        </button>
        <button type="button" className="app-secondary-button" onClick={() => navigate(-1)} disabled={saving}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

export function TradeFormPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const preset = params.get("asset");
  const trade = useApi(`trade-${id ?? "new"}`, () => (id ? api.ledger.trade(Number(id)) : Promise.resolve(null)));
  return (
    <div className="app-page" style={{ maxWidth: 860 }}>
      <PageHeader
        title={id ? "Editar operação" : "Nova operação"}
        subtitle="Toda mudança revalida o histórico do ativo: uma venda nunca pode passar do que havia."
      />
      {id ? (
        <Async state={trade}>{(data) => <TradeForm trade={data} presetAsset={null} />}</Async>
      ) : (
        <TradeForm trade={null} presetAsset={preset ? Number(preset) : null} />
      )}
    </div>
  );
}
