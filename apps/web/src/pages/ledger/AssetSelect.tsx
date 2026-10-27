import { api } from "../../api/endpoints";
import type { AccountDTO, AssetResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";

/** Asset picker for ledger forms (active and archived assets). */
export function AssetSelect({
  id,
  value,
  onChange,
  disabled,
  filter,
}: Readonly<{
  id: string;
  value: number | "";
  onChange: (asset: AssetResponseDTO | null) => void;
  disabled?: boolean;
  filter?: (asset: AssetResponseDTO) => boolean;
}>) {
  const assets = useApi("form-assets", () => api.assets.list(false));
  const items = (assets.data?.items ?? []).filter(filter ?? (() => true));
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
