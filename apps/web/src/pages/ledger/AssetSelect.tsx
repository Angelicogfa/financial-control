import { useEffect, useRef } from "react";

import { api } from "../../api/endpoints";
import type { AccountDTO, AssetResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";

/**
 * Asset picker for ledger forms (active and archived assets). `onResolve` receives the
 * selected asset whenever the value or the loaded list changes, so a form opened with an
 * asset already chosen (editing, or `?asset=` preset) learns its currency without a change.
 */
export function AssetSelect({
  id,
  value,
  onChange,
  onResolve,
  disabled,
  filter,
}: Readonly<{
  id: string;
  value: number | "";
  onChange: (asset: AssetResponseDTO | null) => void;
  onResolve?: (asset: AssetResponseDTO | null) => void;
  disabled?: boolean;
  filter?: (asset: AssetResponseDTO) => boolean;
}>) {
  const assets = useApi("form-assets", () => api.assets.list(false));
  const items = (assets.data?.items ?? []).filter(filter ?? (() => true));
  const resolve = useRef(onResolve);
  resolve.current = onResolve;
  const loaded = assets.data;
  useEffect(() => {
    if (!loaded) return;
    resolve.current?.(loaded.items.find((a) => a.id === value) ?? null);
  }, [loaded, value]);
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      required
      onChange={(e) => onChange(items.find((a) => a.id === Number(e.target.value)) ?? null)}
    >
      <option value="">{assets.loading ? "Carregando…" : "Escolha o ativo"}</option>
      {items.map((a) => (
        <option key={a.id} value={a.id}>
          {a.ticker} — {a.name}
        </option>
      ))}
    </select>
  );
}

export function AccountSelect({
  id,
  value,
  disabled,
  onChange,
}: Readonly<{ id: string; value: number | null; disabled?: boolean; onChange: (id: number | null) => void }>) {
  const accounts = useApi("accounts", () => api.accounts.list());
  return (
    <select id={id} value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">Conta padrão</option>
      {(accounts.data ?? []).filter((a: AccountDTO) => a.is_active !== false || a.id === value).map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </select>
  );
}
