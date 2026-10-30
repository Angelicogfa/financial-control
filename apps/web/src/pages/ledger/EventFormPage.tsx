import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { CorporateEventKind } from "../../api/types";
import { Hint } from "../../components/Hint";
import { Combobox, codeOptions } from "../../components/Combobox";
import { PageHeader } from "../../components/PageHeader";
import { Spinner } from "../../components/States";
import { parseDecimal, today } from "../../utils/format";
import { EVENT_KINDS, EVENT_LABELS, FIXED_INCOME_TYPES } from "../../utils/labels";
import { AssetSelect } from "./AssetSelect";

const FACTOR_HINTS: Record<CorporateEventKind, string> = {
  SPLIT: "Ações depois ÷ antes. Desdobramento 1:2 → 2.",
  REVERSE_SPLIT: "Ações depois ÷ antes. Grupamento 10:1 → 0,1.",
  BONUS: "1 + bonificação. 10% → 1,1.",
};

export function EventFormPage() {
  const navigate = useNavigate();
  const [assetId, setAssetId] = useState<number | "">("");
  const [kind, setKind] = useState<CorporateEventKind>("SPLIT");
  const [exDate, setExDate] = useState(today());
  const [factor, setFactor] = useState("");
  const [unitCost, setUnitCost] = useState("0");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const factorValue = parseDecimal(factor);
    if (assetId === "" || !factorValue) {
      setError("Escolha o ativo e informe o fator.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.ledger.createEvent({
        asset_id: assetId,
        kind,
        ex_date: exDate,
        factor: factorValue,
        unit_cost: kind === "BONUS" ? (parseDecimal(unitCost) ?? 0) : 0,
        notes: notes.trim() || null,
      });
      navigate("/ledger?tab=events");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page" style={{ maxWidth: 860 }}>
      <PageHeader
        title="Novo evento corporativo"
        subtitle="A quantidade muda a partir da data ex; o custo total só muda na bonificação."
      />
      <form className="app-card app-card-padded" onSubmit={submit} aria-busy={saving}>
        {error && <p className="app-error-banner" role="alert">{error}</p>}
        <div className="app-field-grid">
          <div className="app-field">
            <label htmlFor="event-asset">Ativo</label>
            <AssetSelect
              id="event-asset"
              value={assetId}
              disabled={saving}
              onChange={(a) => setAssetId(a?.id ?? "")}
              filter={(a) => !FIXED_INCOME_TYPES.includes(a.asset_type) && a.asset_type !== "CASH"}
            />
          </div>
          <div className="app-field">
            <label htmlFor="event-kind">Evento</label>
            <Combobox id="event-kind" value={kind} onChange={setKind} disabled={saving} options={codeOptions(EVENT_KINDS, EVENT_LABELS)} />
          </div>
          <div className="app-field">
            <label htmlFor="event-date">Data ex</label>
            <input id="event-date" type="date" value={exDate} onChange={(e) => setExDate(e.target.value)} required disabled={saving} />
          </div>
          <div className="app-field">
            <span className="app-field-label">
              <label htmlFor="event-factor">Fator</label>
              <Hint about="Fator">{FACTOR_HINTS[kind]}</Hint>
            </span>
            <input id="event-factor" inputMode="decimal" value={factor} onChange={(e) => setFactor(e.target.value)} required disabled={saving} />
          </div>
          {kind === "BONUS" && (
            <div className="app-field">
              <span className="app-field-label">
                <label htmlFor="event-cost">Custo atribuído por ação (R$)</label>
                <Hint about="Custo atribuído por ação">Informado pela empresa no fato relevante.</Hint>
              </span>
              <input id="event-cost" inputMode="decimal" value={unitCost} onChange={(e) => setUnitCost(e.target.value)} disabled={saving} />
            </div>
          )}
        </div>
        <div className="app-field" style={{ marginTop: "var(--space-3)" }}>
          <label htmlFor="event-notes">Observação</label>
          <input id="event-notes" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={saving} />
        </div>
        <div className="app-form-actions">
          <button type="submit" className="app-primary-button" disabled={saving}>
            {saving && <Spinner size="sm" />}
            <span>{saving ? "Salvando…" : "Salvar evento"}</span>
          </button>
          <button type="button" className="app-secondary-button" onClick={() => navigate(-1)} disabled={saving}>
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}
