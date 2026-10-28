import { api } from "../../api/endpoints";
import type { MarketStatus, SaleSignal, TreasuryMarketDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { Async, Empty } from "../../components/States";
import { brl, day, num, pct, points } from "../../utils/format";
import { TrendChart } from "../../viz/TrendChart";

export const MARKET_STATUS_LABELS: Record<MarketStatus, string> = {
  OPPORTUNITY: "Venda antecipada pode compensar",
  NEUTRAL: "Acima da curva, sem sinal de venda",
  BELOW_CURVE: "Abaixo da curva",
  NO_MARKET_DATA: "Sem preço de mercado",
};

export const MARKET_STATUS_TONES: Record<MarketStatus, string> = {
  OPPORTUNITY: "success",
  NEUTRAL: "info",
  BELOW_CURVE: "warning",
  NO_MARKET_DATA: "neutral",
};

const SIGNAL_LABELS: Record<SaleSignal, string> = {
  EXCESS_RETURN: "Rende mais que a curva",
  REINVESTMENT: "CDI supera o empate",
};

function MarketSummary({ data }: Readonly<{ data: TreasuryMarketDTO }>) {
  return (
    <section className="app-card app-card-padded">
      <div className="health-pillar-head">
        <h2 className="app-card-heading">Curva × mercado</h2>
        <Badge tone={MARKET_STATUS_TONES[data.status]}>{MARKET_STATUS_LABELS[data.status]}</Badge>
      </div>
      <p>{data.explanation}</p>
      <dl className="app-definition-list">
        <dt>Valor na curva</dt>
        <dd>{brl(data.curve_value)}</dd>
        <dt>Valor a mercado</dt>
        <dd>
          {brl(data.market_value)}
          {data.market_price ? (
            <span className="app-muted">
              {" "}
              · {num(data.quantity, 4)} × {brl(data.market_price)} em {day(data.price_date)}
            </span>
          ) : null}
        </dd>
        <dt>Mercado − curva</dt>
        <dd>
          <Signed value={data.premium}>
            {brl(data.premium)} ({pct(data.premium_pct, 2, true)})
          </Signed>
        </dd>
        <dt>Taxa de venda hoje</dt>
        <dd>{data.market_rate === null || data.market_rate === undefined ? "—" : points(data.market_rate, 2)} a.a.</dd>
        <dt>Líquido vendendo hoje</dt>
        <dd>{brl(data.net_sale_value)}</dd>
        <dt>CDI projetado (referência)</dt>
        <dd>{pct(data.reference_rate, 2)} a.a.</dd>
      </dl>
      {data.stale_price && (
        <p className="app-info-banner" role="note">
          O último preço do Tesouro é de {day(data.price_date)}; o worker atualiza todo dia útil.
        </p>
      )}
      {data.approximate && (
        <p className="app-muted">
          Título com juros semestrais: a comparação com o vencimento não inclui os cupons e é aproximada.
        </p>
      )}
    </section>
  );
}

function Lots({ data }: Readonly<{ data: TreasuryMarketDTO }>) {
  const lots = data.lots ?? [];
  if (lots.length === 0) return null;
  return (
    <section>
      <h2 className="app-card-heading">Por compra</h2>
      <p className="app-card-hint">
        Rentabilidade ao ano desde a compra: o que a curva entregou e o que a venda de hoje entregaria. A taxa de empate
        é quanto o dinheiro precisaria render (bruto, tributado) até o vencimento para igualar segurar o título.
      </p>
      <div className="app-table-wrap">
        <table className="app-table">
          <thead>
            <tr>
              <th>Compra</th>
              <th className="app-numeric">Quantidade</th>
              <th className="app-numeric">Curva</th>
              <th className="app-numeric">Mercado</th>
              <th className="app-numeric">Diferença</th>
              <th className="app-numeric">Curva a.a.</th>
              <th className="app-numeric">Venda a.a.</th>
              <th className="app-numeric">Líquido na venda</th>
              <th className="app-numeric">Empate a.a.</th>
              <th>Sinal</th>
            </tr>
          </thead>
          <tbody>
            {lots.map((lot) => (
              <tr key={lot.start_date}>
                <td>
                  {day(lot.start_date)}
                  <small className="app-muted"> · taxa {pct(lot.purchase_rate, 2)}</small>
                </td>
                <td className="app-numeric">{num(lot.quantity, 4)}</td>
                <td className="app-numeric">{brl(lot.curve_value)}</td>
                <td className="app-numeric">{brl(lot.market_value)}</td>
                <td className="app-numeric">
                  <Signed value={lot.premium}>{brl(lot.premium)}</Signed>
                </td>
                <td className="app-numeric">{pct(lot.curve_annual_rate, 2)}</td>
                <td className="app-numeric">{pct(lot.market_annual_rate, 2)}</td>
                <td className="app-numeric">
                  {brl(lot.net_sale_value)}
                  <small className="app-muted"> IR {brl(lot.income_tax_on_sale)}</small>
                </td>
                <td className="app-numeric">{pct(lot.breakeven_rate, 2)}</td>
                <td>
                  {(lot.signals ?? []).length === 0
                    ? "—"
                    : (lot.signals ?? []).map((s) => (
                        <Badge key={s} tone="success">
                          {SIGNAL_LABELS[s]}
                        </Badge>
                      ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function History({ data }: Readonly<{ data: TreasuryMarketDTO }>) {
  const history = data.history ?? [];
  if (history.length < 2) {
    return (
      <Empty
        title="Sem histórico de preços ainda"
        hint="O worker grava o preço de resgate de cada dia útil e busca o histórico do Tesouro Transparente."
      />
    );
  }
  const labels = history.map((p) => day(p.day));
  return (
    <section className="app-card app-card-padded">
      <h2 className="app-card-heading">Momentos de marcação a mercado</h2>
      <TrendChart
        title="Valor na curva e a mercado desde a primeira compra"
        labels={labels}
        hint="Quando a linha de mercado passa acima da curva, a venda antecipada antecipa rendimento."
        format={(v) => brl(v)}
        series={[
          { key: "curve", label: "Curva", color: "var(--viz-serie-2)", values: history.map((p) => p.curve_value) },
          { key: "market", label: "Mercado", color: "var(--viz-serie-1)", values: history.map((p) => p.market_value) },
        ]}
      />
      <TrendChart
        title="Mercado − curva"
        labels={labels}
        baseline={0}
        hint="Acima de zero: prêmio sobre a curva."
        format={(v) => brl(v)}
        series={[{ key: "premium", label: "Diferença", color: "var(--viz-serie-3)", values: history.map((p) => p.premium) }]}
      />
    </section>
  );
}

export function MarketTab({ assetId }: Readonly<{ assetId: number }>) {
  const market = useApi(`treasury-market-${assetId}`, () => api.portfolio.treasuryMarketDetail(assetId));
  return (
    <Async state={market} lines={6}>
      {(data) => (
        <div className="app-page-stack">
          <MarketSummary data={data} />
          <Lots data={data} />
          <History data={data} />
        </div>
      )}
    </Async>
  );
}
