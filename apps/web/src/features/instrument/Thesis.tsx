/** Chapter "Minha tese" of the asset page (Phase 48.R6): why the asset is held or watched,
 *  and when to look at it again. The Início raises an alert on the review date. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../../api/endpoints";
import { Badge } from "../../components/Badge";
import { ErrorBanner, Loading } from "../../components/States";
import { day } from "../../utils/format";

export const notesKey = (assetId: number) => ["asset-notes", assetId] as const;

export function useAssetNotes(assetId: number) {
  return useQuery({ queryKey: notesKey(assetId), queryFn: () => api.watch.assetNotes(assetId) });
}

export function thesisLead(notes: { review_at?: string | null; due: boolean }[] | undefined): string {
  if (!notes || notes.length === 0) return "Ainda sem tese: escreva por que acompanha este ativo e quando revisar.";
  const due = notes.filter((n) => n.due).length;
  if (due > 0) return `${due} nota(s) pedem revisão.`;
  const next = notes.map((n) => n.review_at).filter(Boolean).sort()[0];
  return next ? `${notes.length} nota(s); a próxima revisão é em ${day(next)}.` : `${notes.length} nota(s), sem data de revisão.`;
}

export function Thesis({ assetId }: Readonly<{ assetId: number }>) {
  const client = useQueryClient();
  const notes = useAssetNotes(assetId);
  const [text, setText] = useState("");
  const [reviewAt, setReviewAt] = useState("");
  const refresh = () => {
    void client.invalidateQueries({ queryKey: notesKey(assetId) });
    void client.invalidateQueries({ queryKey: ["notes"] });
  };
  const create = useMutation({
    mutationFn: () => api.watch.createNote(assetId, { text: text.trim(), review_at: reviewAt || null }),
    onSuccess: () => {
      setText("");
      setReviewAt("");
      refresh();
    },
  });
  const remove = useMutation({ mutationFn: (noteId: number) => api.watch.deleteNote(assetId, noteId), onSuccess: refresh });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim()) create.mutate();
  };

  return (
    <div className="app-page-stack">
      <form className="app-page-stack" onSubmit={submit} aria-label="Nova nota da tese">
        <label className="app-field">
          <span>Nota da tese</span>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
        </label>
        <div className="app-filter-bar">
          <label className="app-field">
            <span>Revisar em</span>
            <input type="date" value={reviewAt} onChange={(e) => setReviewAt(e.target.value)} />
          </label>
          <button type="submit" className="app-primary-button" disabled={!text.trim() || create.isPending}>
            Guardar nota
          </button>
        </div>
        <ErrorBanner error={create.error ?? remove.error} />
      </form>
      {notes.isPending ? (
        <Loading lines={2} />
      ) : notes.isError ? (
        <ErrorBanner error={notes.error} onRetry={() => void notes.refetch()} />
      ) : (
        <ul className="app-thesis-list" aria-label="Notas da tese">
          {notes.data.map((note) => (
            <li key={note.id} className="app-card app-card-padded">
              <div className="app-button-row">
                <span className="app-muted">{day(note.written_on)}</span>
                {note.review_at && (
                  <Badge tone={note.due ? "warning" : "neutral"}>
                    {note.due ? "Revisar agora" : `Revisar em ${day(note.review_at)}`}
                  </Badge>
                )}
                <button
                  type="button"
                  className="app-secondary-button"
                  aria-label={`Apagar a nota de ${day(note.written_on)}`}
                  onClick={() => remove.mutate(note.id)}
                >
                  Apagar
                </button>
              </div>
              <p>{note.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
