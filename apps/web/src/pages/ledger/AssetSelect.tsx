import { useEffect, useRef } from "react";

import { api } from "../../api/endpoints";
import { Combobox } from "../../components/Combobox";
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
    <Combobox<number | "">
      id={id}
      value={value}
      disabled={disabled}
      required
      loading={assets.loading}
      placeholder="Escolha o ativo"
      options={items.map((a) => ({ value: a.id, label: `${a.ticker} — ${a.name}` }))}
      onChange={(next) => onChange(items.find((a) => a.id === next) ?? null)}
    />
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
    <Combobox<number | "">
      id={id}
      value={value ?? ""}
      disabled={disabled}
      onChange={(next) => onChange(next === "" ? null : next)}
      options={[
        { value: "", label: "Conta padrão" },
        ...(accounts.data ?? [])
          .filter((a: AccountDTO) => a.is_active !== false || a.id === value)
          .map((a) => ({ value: a.id, label: a.name })),
      ]}
    />
  );
}
