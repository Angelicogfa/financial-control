/** Wealth by custody account, each split into Bolsa and Internacional (Phase 40.2). */

import { api } from "../../api/endpoints";
import type { AccountWealthDTO, MarketGroupDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Section } from "../../components/Section";
import { ErrorBanner, Loading } from "../../components/States";
import { brl, pct, plural } from "../../utils/format";

function Change({ value }: Readonly<{ value: number | null | undefined }>) {
  if (value === null || value === undefined) return null;
  const up = value >= 0;
  return (
    <span className={`home-delta ${up ? "is-up" : "is-down"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {up ? "alta" : "queda"} de {pct(Math.abs(value), 1)}
    </span>
  );
}

function GroupCell({ group }: Readonly<{ group: MarketGroupDTO | undefined }>) {
  if (!group || (group.value_brl <= 0 && group.invested_brl <= 0)) {
    return <td className="app-numeric app-muted">—</td>;
  }
  return (
    <td className="app-numeric">
      <span className="app-cell-main">
        <span>{brl(group.value_brl)}</span>
        <small>
          <Change value={group.change} />
        </small>
      </span>
    </td>
  );
}

function byKey(account: AccountWealthDTO, key: string): MarketGroupDTO | undefined {
  return account.groups.find((g) => g.key === key);
}

export function AccountsWealth() {
  const data = useApi("home-by-account", () => api.portfolio.byAccount());
  if (data.error) return <ErrorBanner error={data.error} onRetry={data.reload} />;
  if (data.loading && !data.data) return <Loading lines={3} />;
  const body = data.data;
  if (!body || body.accounts.length === 0) return null;
  const largest = body.accounts[0];
  return (
    <Section
      title="Patrimônio por conta"
      subtitle={`${plural(body.accounts.length, "conta", "contas")} com posição · a maior é ${largest.name}, com ${pct(largest.share, 0)} do total. Bolsa reúne Caixa, Ações e Real Estate; a variação é o resultado sobre o investido.`}
    >
      <div className="app-table-wrap">
        <table className="app-table" aria-label="Patrimônio por conta">
          <thead>
            <tr>
              <th>Conta</th>
              <th className="app-numeric">Bolsa</th>
              <th className="app-numeric">Internacional</th>
              <th className="app-numeric">Total</th>
              <th className="app-numeric">Peso</th>
            </tr>
          </thead>
          <tbody>
            {body.accounts.map((account) => (
              <tr key={account.account_id}>
                <td>
                  <span className="app-cell-main">
                    <strong>{account.name}</strong>
                    {account.institution && <small>{account.institution}</small>}
                  </span>
                </td>
                <GroupCell group={byKey(account, "B3")} />
                <GroupCell group={byKey(account, "INTERNATIONAL")} />
                <td className="app-numeric">
                  <span className="app-cell-main">
                    <strong>{brl(account.value_brl)}</strong>
                    <small>
                      <Change value={account.change} />
                    </small>
                  </span>
                </td>
                <td className="app-numeric">{pct(account.share, 1)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Todas as contas</th>
              {["B3", "INTERNATIONAL"].map((key) => {
                const group = body.groups.find((g) => g.key === key);
                return (
                  <td key={key} className="app-numeric">
                    {group ? brl(group.value_brl) : "—"}
                  </td>
                );
              })}
              <td className="app-numeric">
                <strong>{brl(body.total_value_brl)}</strong>
              </td>
              <td className="app-numeric">100%</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Section>
  );
}
