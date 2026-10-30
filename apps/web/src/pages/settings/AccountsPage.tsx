import { useState, type FormEvent } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { AccountDTO, AccountKind } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Combobox, codeOptions } from "../../components/Combobox";
import { PageHeader } from "../../components/PageHeader";
import { IconButton } from "../../components/RowActions";
import { Async, Spinner } from "../../components/States";
import { EditIcon } from "../../layout/icons";
import { ACCOUNT_KIND_LABELS } from "../../utils/labels";

interface Draft {
  name: string;
  institution: string;
  kind: AccountKind;
  active: boolean;
}

const EMPTY: Draft = { name: "", institution: "", kind: "BROKER", active: true };

export function AccountsPage() {
  const accounts = useApi("accounts", () => api.accounts.list());
  const [editing, setEditing] = useState<AccountDTO | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const startEdit = (account: AccountDTO) => {
    setEditing(account);
    setDraft({
      name: account.name,
      institution: account.institution ?? "",
      kind: account.kind ?? "BROKER",
      active: account.is_active !== false,
    });
  };

  const reset = () => {
    setEditing(null);
    setDraft(EMPTY);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const body = {
      name: draft.name.trim(),
      institution: draft.institution.trim() || null,
      kind: draft.kind,
      is_active: draft.active,
    };
    try {
      if (editing) await api.accounts.update(editing.id, body);
      else await api.accounts.create(body);
      reset();
      accounts.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app-page">
      <PageHeader title="Contas" subtitle="Corretoras, bancos e exchanges onde ficam seus ativos. Todo lançamento pertence a uma." />
      <div className="app-page-stack">
        <form className="app-card app-card-padded" onSubmit={submit} aria-busy={saving}>
          <h2 className="app-card-heading">{editing ? `Editar ${editing.name}` : "Nova conta"}</h2>
          {error && <p className="app-error-banner">{error}</p>}
          <div className="app-field-grid">
            <div className="app-field">
              <label htmlFor="account-name">Nome</label>
              <input id="account-name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} required disabled={saving} />
            </div>
            <div className="app-field">
              <label htmlFor="account-institution">Instituição</label>
              <input
                id="account-institution"
                value={draft.institution}
                onChange={(e) => setDraft({ ...draft, institution: e.target.value })}
                disabled={saving}
              />
            </div>
            <div className="app-field">
              <label htmlFor="account-kind">Tipo</label>
              <Combobox
                id="account-kind"
                value={draft.kind}
                onChange={(kind) => setDraft({ ...draft, kind })}
                disabled={saving}
                options={codeOptions(Object.keys(ACCOUNT_KIND_LABELS) as AccountKind[], ACCOUNT_KIND_LABELS)}
              />
            </div>
            <label className="app-check">
              <input type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} disabled={saving} />
              Ativa
            </label>
          </div>
          <div className="app-form-actions">
            <button type="submit" className="app-primary-button" disabled={saving}>
              {saving && <Spinner size="sm" />}
              <span>{saving ? "Salvando…" : editing ? "Salvar" : "Adicionar conta"}</span>
            </button>
            {editing && (
              <button type="button" className="app-secondary-button" onClick={reset} disabled={saving}>
                Cancelar
              </button>
            )}
          </div>
        </form>

        <Async state={accounts}>
          {(list) => (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Conta</th>
                    <th>Instituição</th>
                    <th>Tipo</th>
                    <th>Situação</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.map((account) => (
                    <tr key={account.id}>
                      <td>{account.name}</td>
                      <td>{account.institution ?? "—"}</td>
                      <td>{ACCOUNT_KIND_LABELS[account.kind ?? "OTHER"]}</td>
                      <td>
                        <Badge tone={account.is_active === false ? "neutral" : "success"}>
                          {account.is_active === false ? "Inativa" : "Ativa"}
                        </Badge>
                      </td>
                      <td className="app-row-actions">
                        <IconButton label="Editar" icon={<EditIcon />} onClick={() => startEdit(account)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </div>
    </div>
  );
}
