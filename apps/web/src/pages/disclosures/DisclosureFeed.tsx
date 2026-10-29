import { useState } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { CvmDocumentDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { day } from "../../utils/format";

/** The categories of most interest first; the others come from what the companies filed. */
export const MAIN_CATEGORIES = ["Fato Relevante", "Comunicado ao Mercado", "Aviso aos Acionistas"];

const CATEGORY_TONES: Record<string, string> = {
  "Fato Relevante": "danger",
  "Comunicado ao Mercado": "info",
  "Aviso aos Acionistas": "warning",
};

function DocumentRow({
  doc,
  onRead,
  busy,
}: Readonly<{ doc: CvmDocumentDTO; onRead: (id: number) => void; busy: boolean }>) {
  return (
    <li className={`disclosure-item${doc.read ? " is-read" : ""}`}>
      <div className="disclosure-head">
        <Badge tone={CATEGORY_TONES[doc.category] ?? "neutral"}>{doc.category}</Badge>
        <strong>{(doc.tickers ?? []).join(", ") || doc.company_name}</strong>
        <span className="app-muted">entregue em {day(doc.delivery_date)}</span>
        {!doc.read && <Badge tone="info">Novo</Badge>}
      </div>
      <p className="disclosure-subject">{doc.subject || [doc.doc_type, doc.species].filter(Boolean).join(" · ")}</p>
      <div className="app-button-row">
        {doc.link && (
          <a className="app-link" href={doc.link} target="_blank" rel="noreferrer noopener">
            Abrir o documento na CVM
          </a>
        )}
        {!doc.read && (
          <button type="button" className="app-link-button" disabled={busy} onClick={() => onRead(doc.id)}>
            Marcar como lido
          </button>
        )}
      </div>
    </li>
  );
}

/** Relevant facts and notices filed with the CVM (IPE) by the followed companies (Phase 28). */
export function DisclosureFeed({
  assetId,
  limit = 30,
  title = "Fatos relevantes e comunicados (CVM)",
}: Readonly<{ assetId?: number; limit?: number; title?: string }>) {
  const [category, setCategory] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const feed = useApi(`disclosures-${assetId ?? "all"}-${category}-${unreadOnly}-${limit}`, () =>
    api.disclosures.feed({ assetId, category: category || undefined, unread: unreadOnly, limit }),
  );

  const markRead = async (body: { ids?: number[]; all?: boolean }) => {
    setBusy(true);
    setError(null);
    try {
      await api.disclosures.markRead({ ...body, asset_id: assetId ?? null });
      feed.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (feed.error) return <ErrorBanner error={feed.error} onRetry={feed.reload} />;
  if (feed.loading && !feed.data) return <Loading lines={3} />;
  const data = feed.data;
  if (!data) return null;
  const items = data.items ?? [];
  const counts = data.category_counts ?? {};
  const unread = data.unread_count ?? 0;
  const categories = [...MAIN_CATEGORIES, ...Object.keys(counts).filter((c) => !MAIN_CATEGORIES.includes(c)).sort()];

  return (
    <section className="app-card app-card-padded" aria-label={title}>
      <div className="health-pillar-head">
        <h2 className="app-card-heading">{title}</h2>
        {unread > 0 && <Badge tone="info">{unread} não lido(s)</Badge>}
      </div>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      <div className="app-field-grid">
        <div className="app-field">
          <label htmlFor={`disclosure-category-${assetId ?? "all"}`}>Categoria</label>
          <select
            id={`disclosure-category-${assetId ?? "all"}`}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Todas</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
                {counts[c] ? ` (${counts[c]})` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="app-check-row">
        <label className="app-check">
          <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
          Só os não lidos
        </label>
      </div>
      {items.length === 0 ? (
        <Empty
          title="Nenhum documento"
          hint={
            data.companies === 0
              ? "Não há ações brasileiras na carteira ou na watchlist."
              : "A rotina diária traz os documentos entregues à CVM; rode-a já em Dados de mercado."
          }
        />
      ) : (
        <>
          <ul className="disclosure-list" aria-label="Documentos da CVM">
            {items.map((doc) => (
              <DocumentRow key={doc.id} doc={doc} busy={busy} onRead={(id) => markRead({ ids: [id] })} />
            ))}
          </ul>
          {unread > 0 && (
            <div className="app-form-actions">
              <button type="button" className="app-secondary-button" disabled={busy} onClick={() => markRead({ all: true })}>
                Marcar todos como lidos
              </button>
            </div>
          )}
        </>
      )}
      {(data.unmapped ?? []).length > 0 && (
        <p className="app-muted">
          Sem CNPJ no cadastro da CVM ainda: {(data.unmapped ?? []).join(", ")}.
        </p>
      )}
      {data.note && <p className="app-card-hint">{data.note}</p>}
    </section>
  );
}
