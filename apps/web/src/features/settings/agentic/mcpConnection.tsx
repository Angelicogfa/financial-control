import { useState } from "react";

/** Returns the same-origin MCP Streamable HTTP endpoint URL. */
export function mcpEndpoint(): string {
  return `${window.location.origin}/api/v1/mcp`;
}

/** Formats the ready-to-paste MCP client configuration JSON for a given key. */
export function mcpClientConfig(key: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        "financial-control": {
          type: "http",
          url: mcpEndpoint(),
          headers: { Authorization: `Bearer ${key}` },
        },
      },
    },
    null,
    2,
  );
}

export function CopyButton({ value, label }: Readonly<{ value: string; label?: string }>) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="app-secondary-button"
      onClick={() => {
        void navigator.clipboard?.writeText(value);
        setCopied(true);
      }}
    >
      {copied ? "Copiado" : (label ?? "Copiar")}
    </button>
  );
}

/** Displays the MCP endpoint, Authorization header, and optional one-time client config snippet. */
export function McpConnection({ apiKey }: Readonly<{ apiKey?: string }>) {
  const endpoint = mcpEndpoint();
  const sampleKey = apiKey ?? "fck_…";

  return (
    <div className="app-mcp-connection">
      {apiKey && (
        <div className="app-mcp-row">
          <span className="app-mcp-label">Chave</span>
          <code className="app-mcp-value">{apiKey}</code>
          <CopyButton value={apiKey} />
        </div>
      )}
      <div className="app-mcp-row">
        <span className="app-mcp-label">Endereço MCP</span>
        <code className="app-mcp-value">{endpoint}</code>
        <CopyButton value={endpoint} />
      </div>
      <div className="app-mcp-row">
        <span className="app-mcp-label">Cabeçalho</span>
        <code className="app-mcp-value">Authorization: Bearer {sampleKey}</code>
      </div>
      <div className="app-mcp-config">
        <div className="app-mcp-row">
          <span className="app-mcp-label">Configuração do cliente MCP</span>
          <CopyButton value={mcpClientConfig(sampleKey)} label="Copiar JSON" />
        </div>
        <pre className="app-mcp-snippet">{mcpClientConfig(sampleKey)}</pre>
      </div>
    </div>
  );
}
