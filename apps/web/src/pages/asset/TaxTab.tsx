import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { AssetTaxStatusDTO, TaxRegimeInfoDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Async, Empty } from "../../components/States";
import { brl, day, pct } from "../../utils/format";
import { TAX_REGIME_LABELS } from "../../utils/labels";

function bracketLabel(upTo: number | null | undefined, previous: number | null | undefined): string {
  if (upTo === null || upTo === undefined) return previous === null || previous === undefined ? "Qualquer prazo" : `Acima de ${previous} dias`;
  return previous === null || previous === undefined ? `Até ${upTo} dias` : `${previous + 1} a ${upTo} dias`;
}

function Regimes({ regimes }: Readonly<{ regimes: TaxRegimeInfoDTO[] }>) {
  return (
    <section className="app-card app-card-padded">
      <h2 className="app-card-heading">Regime tributário</h2>
      <dl className="app-definition-list">
        {regimes
          .filter((r) => r.regime !== "IOF_REGRESSIVE")
          .map((r) => (
            <div key={r.regime} style={{ display: "contents" }}>
              <dt>{TAX_REGIME_LABELS[r.regime]}</dt>
              <dd>
                {r.brackets.length > 1 ? "Regressivo" : pct(r.current_rate, 1)}
                <div className="app-muted">{r.description}</div>
                <div className="app-muted">
                  {r.legal_basis} · vigente desde {day(r.valid_from)}
                </div>
              </dd>
            </div>
          ))}
      </dl>
    </section>
  );
}

function FixedIncomeStatus({ status, assetId }: Readonly<{ status: AssetTaxStatusDTO; assetId: number }>) {
  const regressive = status.regimes.find((r) => r.regime === "FIXED_INCOME_REGRESSIVE");
  return (
    <div className="app-page-stack">
      <div className="app-split">
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Tributação</h2>
          {status.lots.length === 0 ? (
            <p className="app-muted">Sem saldo aplicado.</p>
          ) : (
            <dl className="app-definition-list">
              <dt>Valor bruto</dt>
              <dd>{brl(status.gross_value)}</dd>
              <dt>IOF ainda devido</dt>
              <dd>{brl(status.iof_due)}</dd>
              <dt>IR estimado se resgatar hoje</dt>
              <dd>{status.tax_exempt ? "Isento" : brl(status.income_tax_due)}</dd>
              <dt>Valor líquido hoje</dt>
              <dd>{brl(status.net_value)}</dd>
              <dt>Próxima queda de faixa</dt>
              <dd>{status.next_bracket_date ? day(status.next_bracket_date) : "—"}</dd>
              {status.tax_saving_by_waiting > 0 && (
                <>
                  <dt>IR economizado esperando</dt>
                  <dd>{brl(status.tax_saving_by_waiting)}</dd>
                </>
              )}
            </dl>
          )}
          <p style={{ marginTop: "var(--space-3)" }}>
            <Link className="app-link" to={`/tools/fixed-income?asset=${assetId}`}>
              Comparar com outro título
            </Link>
          </p>
        </section>
        {regressive && !status.tax_exempt ? (
          <section className="app-card app-card-padded">
            <h2 className="app-card-heading">Tabela regressiva</h2>
            <dl className="app-definition-list">
              {regressive.brackets.map((b, index) => (
                <div key={b.up_to_days ?? "open"} style={{ display: "contents" }}>
                  <dt>{bracketLabel(b.up_to_days, index > 0 ? regressive.brackets[index - 1].up_to_days : null)}</dt>
                  <dd>{pct(b.rate, 1)}</dd>
                </div>
              ))}
            </dl>
            <p className="app-muted">IR sobre o rendimento, pela data de cada aplicação. {regressive.legal_basis}.</p>
          </section>
        ) : (
          <Regimes regimes={status.regimes} />
        )}
      </div>
      {status.lots.length > 0 && (
        <section>
          <h2 className="app-card-heading">Por aplicação</h2>
          <div className="app-table-wrap">
            <table className="app-table">
              <thead>
                <tr>
                  <th>Aplicação</th>
                  <th className="app-numeric">Dias</th>
                  <th className="app-numeric">Principal</th>
                  <th className="app-numeric">Rendimento</th>
                  <th className="app-numeric">Alíquota</th>
                  <th className="app-numeric">IOF</th>
                  <th className="app-numeric">IR hoje</th>
                  <th>Próxima faixa</th>
                  <th className="app-numeric">IR na próxima faixa</th>
                  <th className="app-numeric">Ganho de esperar</th>
                </tr>
              </thead>
              <tbody>
                {status.lots.map((lot) => (
                  <tr key={`${lot.start_date}-${lot.principal}`}>
                    <td>{day(lot.start_date)}</td>
                    <td className="app-numeric">{lot.holding_days}</td>
                    <td className="app-numeric">{brl(lot.principal)}</td>
                    <td className="app-numeric">{brl(lot.gross_yield)}</td>
                    <td className="app-numeric">{pct(lot.income_tax_rate, 1)}</td>
                    <td className="app-numeric">
                      {brl(lot.iof_due)}
                      {lot.iof_free_date && <div className="app-muted">zera em {day(lot.iof_free_date)}</div>}
                    </td>
                    <td className="app-numeric">{brl(lot.income_tax_due)}</td>
                    <td>
                      {lot.next_bracket_date ? (
                        <>
                          {day(lot.next_bracket_date)} <Badge tone="info">{pct(lot.next_income_tax_rate, 1)}</Badge>
                          <div className="app-muted">em {lot.days_to_next_bracket} dias</div>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="app-numeric">
                      {lot.tax_at_next_bracket === null || lot.tax_at_next_bracket === undefined ? "—" : brl(lot.tax_at_next_bracket)}
                    </td>
                    <td className="app-numeric">
                      {lot.net_gain_by_waiting === null || lot.net_gain_by_waiting === undefined ? "—" : brl(lot.net_gain_by_waiting)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="app-muted">
            A projeção até a próxima faixa usa o CDI e o IPCA anuais atuais; o ganho de esperar soma o rendimento do
            período e a queda da alíquota.
          </p>
        </section>
      )}
    </div>
  );
}

export function TaxTab({ assetId }: Readonly<{ assetId: number }>) {
  const status = useApi(`asset-tax-${assetId}`, () => api.tax.assetStatus(assetId));
  return (
    <Async state={status}>
      {(data) =>
        data.is_fixed_income ? (
          <FixedIncomeStatus status={data} assetId={assetId} />
        ) : data.regimes.length === 0 ? (
          <Empty title="Sem regra tributária para este tipo de ativo" />
        ) : (
          <div className="app-page-stack">
            <Regimes regimes={data.regimes} />
            <p className="app-muted">
              O imposto de renda variável é apurado na venda ou no pagamento do provento, fora da posição.
            </p>
          </div>
        )
      }
    </Async>
  );
}
