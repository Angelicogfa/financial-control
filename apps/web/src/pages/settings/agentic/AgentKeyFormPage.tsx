import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../../../api/endpoints";
import { errorMessage } from "../../../api/http";
import type { AgentKeyDTO, GrantOptionsDTO, KeyExpiryDays } from "../../../api/types";
import { PageHeader } from "../../../components/PageHeader";
import { ChevronDownIcon, ChevronRightIcon } from "../../../layout/icons";
import { DEFAULT_EXPIRY } from "./expiry";
import { ExpirySelect, RenewPanel } from "./KeyExpiry";
import { McpConnection } from "./mcpConnection";
import { scopeSize, type Scope } from "./scope";
import { ScopePicker } from "./ScopePicker";

/**
 * Form screen for creating or editing a personal MCP key.
 * All keys belong exclusively to the authenticated user (single-owner model).
 */
export function AgentKeyFormPage() {
  const navigate = useNavigate();
  const { keyId } = useParams<{ keyId: string }>();
  const numericKeyId = keyId ? Number(keyId) : null;
  const isEditing = numericKeyId !== null && Number.isFinite(numericKeyId);

  const [options, setOptions] = useState<GrantOptionsDTO | null>(null);
  const [detail, setDetail] = useState<AgentKeyDTO | null>(null);
  const [name, setName] = useState("");
  const [scope, setScope] = useState<Scope>({ contexts: [], operations: [] });
  const [scopeOpen, setScopeOpen] = useState(!isEditing);
  const [validity, setValidity] = useState<KeyExpiryDays>(DEFAULT_EXPIRY);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function populate(keyData: AgentKeyDTO) {
    setDetail(keyData);
    setName(keyData.name);
    setScope({ contexts: keyData.contexts, operations: keyData.operations });
  }

  useEffect(() => {
    let active = true;
    api.agents
      .options()
      .then((opts) => {
        if (active) setOptions(opts);
      })
      .catch((err) => {
        if (active) setError(errorMessage(err));
      });

    if (isEditing && numericKeyId !== null) {
      api.agents
        .get(numericKeyId)
        .then((keyData) => {
          if (active) populate(keyData);
        })
        .catch((err) => {
          if (active) setError(errorMessage(err));
        });
    }
    return () => {
      active = false;
    };
  }, [isEditing, numericKeyId]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (scope.contexts.length === 0 && scope.operations.length === 0) {
      setError("Selecione ao menos um contexto ou operação para esta chave.");
      setScopeOpen(true);
      return;
    }

    setSaving(true);
    try {
      if (isEditing && numericKeyId !== null && detail) {
        const updated = await api.agents.update(numericKeyId, {
          name: name.trim(),
          contexts: scope.contexts,
          operations: scope.operations,
          expected_revision: detail.revision,
        });
        populate(updated);
        setNotice("Alterações salvas. Clientes MCP já conectados usarão o novo escopo nas próximas chamadas.");
        return;
      }

      const created = await api.agents.create({
        name: name.trim(),
        contexts: scope.contexts,
        operations: scope.operations,
        expires_in_days: validity,
      });
      navigate("/settings/agentic", { state: { created } });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleRenew(days: KeyExpiryDays) {
    if (!isEditing || numericKeyId === null) return;
    setError(null);
    setNotice(null);
    try {
      const renewed = await api.agents.renew(numericKeyId, days);
      setDetail((current) =>
        current
          ? { ...current, expires_at: renewed.expires_at, revision: renewed.revision }
          : renewed,
      );
      const formattedDate = new Date(renewed.expires_at).toLocaleDateString("pt-BR");
      setNotice(`Validade renovada até ${formattedDate}.`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const totalOperations = options ? scopeSize(options.contexts, scope) : 0;
  const title = isEditing ? (detail?.name ?? "Carregando…") : "Nova chave MCP";
  const isLoaded = Boolean(options) && (!isEditing || Boolean(detail));

  return (
    <div className="app-page app-page-stack">
      <PageHeader
        title={title}
        subtitle={
          isEditing
            ? "Ajuste o nome, renove a validade ou altere o recorte de operações permitidas para esta chave pessoal."
            : "A chave criada permite que um agente MCP execute exatamente as operações selecionadas abaixo em seu nome."
        }
      />

      <div className="app-card app-card-padded">
        <p className="app-key-use-title">Conexão MCP pessoal</p>
        <p className="app-muted app-key-use-body">
          Esta chave é exclusiva do seu usuário e autentica chamadas ao servidor MCP integrado da aplicação.
        </p>
        <McpConnection />
      </div>

      {error && (
        <div className="app-error-banner" role="alert">
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <p className="app-info-banner" role="status">
          {notice}
        </p>
      )}

      {detail && <RenewPanel expiresAt={detail.expires_at} onRenew={handleRenew} />}

      <div className="app-card app-card-padded">
        <form onSubmit={(e) => void handleSubmit(e)} className="app-page-stack">
          <div className="app-field-grid">
            <div className="app-field">
              <label htmlFor="key-name">Nome da chave</label>
              <input
                id="key-name"
                required
                autoFocus
                maxLength={128}
                placeholder="Ex.: Claude Desktop, Cursor, Antigravity"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            {!isEditing && (
              <ExpirySelect id="key-validity" value={validity} onChange={setValidity} />
            )}
          </div>

          <section className="app-collapsible">
            <button
              type="button"
              className="app-collapsible-head"
              aria-expanded={scopeOpen}
              aria-controls="key-scope"
              onClick={() => setScopeOpen((current) => !current)}
            >
              {scopeOpen ? (
                <ChevronDownIcon width={16} height={16} aria-hidden="true" />
              ) : (
                <ChevronRightIcon width={16} height={16} aria-hidden="true" />
              )}
              <span className="app-collapsible-title">Escopo de ferramentas MCP</span>
              <span className={`app-badge${totalOperations > 0 ? " app-badge-success" : ""}`}>
                {totalOperations > 0
                  ? `${totalOperations} ${totalOperations === 1 ? "operação liberada" : "operações liberadas"}`
                  : "Nenhuma operação selecionada"}
              </span>
            </button>

            {scopeOpen && (
              <div id="key-scope" className="app-collapsible-body">
                {!isLoaded && !error && <p className="app-muted">Carregando catálogo de operações…</p>}
                {options && isLoaded && (
                  <ScopePicker
                    contexts={options.contexts}
                    value={scope}
                    onChange={setScope}
                  />
                )}
              </div>
            )}
          </section>

          <div className="app-form-actions">
            <button
              type="submit"
              className="app-primary-button"
              disabled={saving || !isLoaded}
            >
              {saving ? "Salvando…" : isEditing ? "Salvar alterações" : "Criar chave MCP"}
            </button>
            <button
              type="button"
              className="app-secondary-button"
              onClick={() => navigate("/settings/agentic")}
            >
              Cancelar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
