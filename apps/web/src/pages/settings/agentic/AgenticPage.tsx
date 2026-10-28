import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api } from "../../../api/endpoints";
import { errorMessage } from "../../../api/http";
import type { AgentKeyCreatedDTO, AgentKeyDTO } from "../../../api/types";
import { PageHeader } from "../../../components/PageHeader";
import { IconButton, IconLink } from "../../../components/RowActions";
import { Loading } from "../../../components/States";
import { BanIcon, EditIcon, PlusIcon } from "../../../layout/icons";
import { ExpiryBadge } from "./KeyExpiry";
import { McpConnection } from "./mcpConnection";

/**
 * Lists the user's personal MCP keys and shows how to connect an MCP client.
 * A newly created key is displayed once from `location.state.created` and cleared from history.
 */
export function AgenticPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [keys, setKeys] = useState<AgentKeyDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingRevoke, setConfirmingRevoke] = useState<AgentKeyDTO | null>(null);
  const [createdKey, setCreatedKey] = useState<AgentKeyCreatedDTO | null>(
    () => (location.state as { created?: AgentKeyCreatedDTO } | null)?.created ?? null,
  );

  const loadKeys = useCallback(async () => {
    setError(null);
    try {
      setKeys(await api.agents.list());
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void loadKeys();
  }, [loadKeys]);

  useEffect(() => {
    if (createdKey) {
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleRevoke(item: AgentKeyDTO) {
    setConfirmingRevoke(null);
    try {
      await api.agents.revoke(item.id);
      if (createdKey?.id === item.id) setCreatedKey(null);
      await loadKeys();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="app-page app-page-stack">
      <PageHeader
        title="Acesso agêntico (MCP)"
        subtitle="Crie chaves pessoais para conectar assistentes (Claude, Cursor, Antigravity) ao servidor MCP da aplicação com escopo controlado."
        actions={
          <button
            type="button"
            className="app-primary-button"
            onClick={() => navigate("/settings/agentic/new")}
          >
            <PlusIcon width={16} height={16} aria-hidden="true" /> Nova chave MCP
          </button>
        }
      />

      {error && (
        <div className="app-error-banner" role="alert">
          <span>{error}</span>
        </div>
      )}

      {createdKey && (
        <div className="app-card app-card-padded app-key-created" role="region" aria-label="Chave recém-criada">
          <p style={{ margin: 0, fontWeight: 600 }}>
            Guarde esta chave agora — ela não será mostrada novamente
          </p>
          <p className="app-muted" style={{ margin: "4px 0 12px", fontSize: "var(--text-sm)" }}>
            O servidor armazena apenas o resumo criptográfico (SHA-256). Copie a chave ou o JSON abaixo para o seu cliente MCP.
          </p>
          <McpConnection apiKey={createdKey.key} />
        </div>
      )}

      {!createdKey && (
        <details className="app-card app-card-padded app-mcp-details">
          <summary>Como conectar um agente MCP</summary>
          <p className="app-muted" style={{ fontSize: "var(--text-sm)" }}>
            Aponte seu cliente MCP (Streamable HTTP) para o endereço abaixo enviando a chave pessoal no cabeçalho{" "}
            <code>Authorization</code>.
          </p>
          <McpConnection />
        </details>
      )}

      {confirmingRevoke && (
        <div className="app-card app-card-padded" role="dialog" aria-label="Confirmar revogação">
          <p style={{ margin: "0 0 var(--space-2)", fontWeight: 600 }}>
            Revogar a chave &ldquo;{confirmingRevoke.name}&rdquo;?
          </p>
          <p className="app-muted" style={{ margin: "0 0 var(--space-3)", fontSize: "var(--text-sm)" }}>
            Qualquer cliente MCP conectado com o prefixo <code>{confirmingRevoke.prefix}…</code> perderá o acesso imediatamente.
          </p>
          <div className="app-button-row">
            <button
              type="button"
              className="app-danger-button"
              onClick={() => void handleRevoke(confirmingRevoke)}
            >
              Confirmar revogação
            </button>
            <button
              type="button"
              className="app-secondary-button"
              onClick={() => setConfirmingRevoke(null)}
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div className="app-table-wrap">
        <table className="app-table">
          <thead>
            <tr>
              <th>Nome</th>
              <th>Prefixo</th>
              <th>Escopo permitido</th>
              <th>Validade</th>
              <th>Último uso</th>
              <th aria-label="Ações" />
            </tr>
          </thead>
          <tbody>
            {keys === null && (
              <tr>
                <td colSpan={6}>
                  <Loading lines={2} />
                </td>
              </tr>
            )}
            {keys?.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link to={`/settings/agentic/${item.id}`}>{item.name}</Link>
                </td>
                <td className="app-muted">
                  <code>{item.prefix}…</code>
                </td>
                <td className="app-muted">
                  {item.contexts.length === 0 && item.operations.length === 0 ? (
                    "Nenhum"
                  ) : (
                    <code>{[...item.contexts, ...item.operations].join(", ")}</code>
                  )}
                </td>
                <td>
                  <ExpiryBadge expiresAt={item.expires_at} />
                </td>
                <td className="app-muted">
                  {item.last_used_at
                    ? new Date(item.last_used_at).toLocaleString("pt-BR")
                    : "Nunca utilizada"}
                </td>
                <td className="app-row-actions">
                  <IconLink to={`/settings/agentic/${item.id}`} label="Editar" icon={<EditIcon />} />
                  <IconButton label="Revogar" icon={<BanIcon />} danger onClick={() => setConfirmingRevoke(item)} />
                </td>
              </tr>
            ))}
            {keys?.length === 0 && (
              <tr>
                <td colSpan={6} className="app-muted" style={{ textAlign: "center", padding: "var(--space-5)" }}>
                  Nenhuma chave MCP ativa. Crie uma chave para liberar ferramentas ao seu agente.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
