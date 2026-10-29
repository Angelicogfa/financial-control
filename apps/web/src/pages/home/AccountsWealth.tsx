/** Wealth by custody account, each split into Bolsa and Internacional (Phase 40.2). */

import { api } from "../../api/endpoints";
import type { AccountWealthDTO, MarketGroupDTO, WealthByAccountDTO } from "../../api/types";
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

/** A money cell: the value and, under it, its rise or fall over the invested amount. */
function MoneyCell({ value, change, strong = false }: Readonly<{ value: number; change?: number | null; strong?: boolean }>) {
  return (
    <td className="app-numeric">
      <span className="wealth-cell">
        {strong ? <strong>{brl(value)}</strong> : <span>{brl(value)}</span>}
        <Change value={change} />
      </span>
    </td>
  );
}

function GroupCell({ group }: Readonly<{ group: MarketGroupDTO | undefined }>) {
  if (!group || (group.value_brl <= 0 && group.invested_brl <= 0)) {
    return (
      <td className="app-numeric app-muted" aria-label="Sem posição">
        —
      </td>
    );
  }
  return <MoneyCell value={group.value_brl} change={group.change} />;
}

function byKey(groups: MarketGroupDTO[], key: string): MarketGroupDTO | undefined {
  return groups.find((g) => g.key === key);
}

/** The conclusion of the table in one sentence. */
export function wealthSummary(body: WealthByAccountDTO): string {
  const largest = body.accounts[0];
  const abroad = byKey(body.groups, "INTERNATIONAL");
  const abroadShare = abroad && body.total_value_brl > 0 ? abroad.value_brl / body.total_value_brl : 0;
  const accounts = plural(body.accounts.length, "conta", "contas");
  return `${largest.name} concentra ${pct(largest.share, 0)} do patrimônio, em ${accounts}; ${pct(abroadShare, 0)} está no Internacional.`;
}

function sameName(account: AccountWealthDTO): boolean {
  return !account.institution || account.institution.trim().toLowerCase() === account.name.trim().toLowerCase();
}

export function AccountsWealth() {
  const data = useApi("home-by-account", () => api.portfolio.byAccount());
  if (data.error) return <ErrorBanner error={data.error} onRetry={data.reload} />;
  if (data.loading && !data.data) return <Loading lines={3} />;
  const body = data.data;
  if (!body || body.accounts.length === 0) return null;
  const invested = body.accounts.reduce((sum, a) => sum + a.invested_brl, 0);
  const pnl = body.accounts.reduce((sum, a) => sum + a.pnl_brl, 0);
  const totalChange = invested > 0 ? pnl / invested : null;
  const b3 = byKey(body.groups, "B3");
  const abroad = byKey(body.groups, "INTERNATIONAL");

  return (
    <Section title="Patrimônio por conta" subtitle={wealthSummary(body)}>
      <div className="app-table-wrap">
        <table className="app-table wealth-table" aria-label="Patrimônio por conta">
          <thead>
            <tr>
              <th scope="col">Conta</th>
              <th scope="col" className="app-numeric">
                Bolsa
              </th>
              <th scope="col" className="app-numeric">
                Internacional
              </th>
              <th scope="col" className="app-numeric">
                Total
              </th>
              <th scope="col" className="wealth-share-head">
                Peso no patrimônio
              </th>
            </tr>
          </thead>
          <tbody>
            {body.accounts.map((account) => (
              <tr key={account.account_id}>
                <th scope="row" className="wealth-account">
                  <span className="app-cell-main">
                    <strong>{account.name}</strong>
                    {!sameName(account) && <small>{account.institution}</small>}
                  </span>
                </th>
                <GroupCell group={byKey(account.groups, "B3")} />
                <GroupCell group={byKey(account.groups, "INTERNATIONAL")} />
                <MoneyCell value={account.value_brl} change={account.change} strong />
                <td className="wealth-share">
                  <span className="wealth-share-inner">
                    <span className="wealth-share-bar" aria-hidden="true">
                      <span style={{ width: `${Math.round(account.share * 100)}%` }} />
                    </span>
                    <span className="wealth-share-value">{pct(account.share, 1)}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Todas as contas</th>
              {b3 && b3.value_brl > 0 ? <MoneyCell value={b3.value_brl} change={b3.change} strong /> : <td className="app-numeric">—</td>}
              {abroad && abroad.value_brl > 0 ? (
                <MoneyCell value={abroad.value_brl} change={abroad.change} strong />
              ) : (
                <td className="app-numeric">—</td>
              )}
              <MoneyCell value={body.total_value_brl} change={totalChange} strong />
              <td className="wealth-share">
                <span className="wealth-share-inner">
                  <span className="wealth-share-bar" aria-hidden="true">
                    <span style={{ width: "100%" }} />
                  </span>
                  <span className="wealth-share-value">100%</span>
                </span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="app-meta">
        Bolsa reúne Caixa, Ações e Real Estate; Internacional, os ativos no exterior. Alta e queda são o resultado consolidado
        (preço, vendas e proventos) sobre o valor investido.
      </p>
    </Section>
  );
}
