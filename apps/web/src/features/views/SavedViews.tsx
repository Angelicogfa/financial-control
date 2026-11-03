/** Saved views of a screen (Phase 48.R9): the filters in use kept under a name in the
 *  database, so they come back on another day or another device. Saving under an existing
 *  name replaces its filters. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/endpoints";
import type { SavedViewDTO, ViewScope } from "../../api/types";
import { ErrorBanner } from "../../components/States";

export const savedViewsKey = (scope: ViewScope) => ["saved-views", scope] as const;

export function SavedViews<F extends object>({
  scope,
  filters,
  onApply,
}: Readonly<{ scope: ViewScope; filters: F; onApply: (filters: F) => void }>) {
  const client = useQueryClient();
  const views = useQuery({ queryKey: savedViewsKey(scope), queryFn: () => api.savedViews.list(scope) });
  const [selected, setSelected] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const refresh = () => void client.invalidateQueries({ queryKey: savedViewsKey(scope) });
  const save = useMutation({
    mutationFn: () => api.savedViews.save({ scope, name: name.trim(), filters: filters as Record<string, unknown> }),
    onSuccess: (view: SavedViewDTO) => {
      setSelected(view.id);
      setNotice(`Visão “${view.name}” salva.`);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.savedViews.remove(id),
    onSuccess: () => {
      setSelected(null);
      setName("");
      setNotice("Visão apagada.");
      refresh();
    },
  });

  const apply = (id: number | null) => {
    setSelected(id);
    setNotice(null);
    const view = views.data?.find((v) => v.id === id);
    if (!view) return;
    setName(view.name);
    onApply(view.filters as F);
  };

  return (
    <div className="app-filter-bar app-saved-views" role="group" aria-label="Visões salvas">
      <label className="app-field">
        <span>Visão salva</span>
        <select value={selected ?? ""} onChange={(e) => apply(e.target.value ? Number(e.target.value) : null)}>
          <option value="">{views.data?.length ? "Escolha uma visão" : "Nenhuma visão salva"}</option>
          {views.data?.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      <label className="app-field">
        <span>Nome da visão</span>
        <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="Ex.: FIIs baratos" />
      </label>
      <button
        type="button"
        className="app-secondary-button"
        disabled={!name.trim() || save.isPending}
        onClick={() => save.mutate()}
      >
        Salvar visão
      </button>
      {selected !== null && (
        <button
          type="button"
          className="app-secondary-button"
          disabled={remove.isPending}
          onClick={() => remove.mutate(selected)}
        >
          Apagar visão
        </button>
      )}
      {notice && (
        <span className="app-muted" role="status">
          {notice}
        </span>
      )}
      <ErrorBanner error={save.error ?? remove.error} />
    </div>
  );
}
