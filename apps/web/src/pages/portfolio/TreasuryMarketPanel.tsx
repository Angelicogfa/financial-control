import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { ErrorBanner } from "../../components/States";
import { brl, pct } from "../../utils/format";
import { MARKET_STATUS_LABELS, MARKET_STATUS_TONES } from "../asset/MarketTab";

/** Treasury bonds at market next to the curve, with the early-sale signal of each one. */
export function TreasuryMarketPanel() {
  const market = useApi("portfolio-treasury-market", () => api.portfolio.treasuryMarket());
  if (market.error) return <ErrorBanner error={market.error} onRetry={market.reload} />;
  const items = market.data ?? [];
  if (items.length === 0) return null;
  return (
    <section className="app-card app-card-padded" aria-label="Tesouro a mercado">
      <h2 className="app-card-heading">Tesouro Direto a mercado</h2>
      <p className="app-card-hint">
        O valor da carteira usa a curva (taxa da compra); o mercado é o preço de resgate do dia. Abra o título para ver o
        histórico e o detalhe de cada compra.
      </p>
      <div className="app-table-wrap">
        <table className="app-table">
          <thead>
            <tr>
              <th>Título</th>
              <th className="app-numeric">Curva</th>
              <th className="app-numeric">Mercado</th>
              <th className="app-numeric">Diferença</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.ticker}>
                <td>
                  {item.asset_id ? (
                    <Link className="app-link" to={`/asset/${item.asset_id}?tab=market`}>
                      {item.name}
                    </Link>
                  ) : (
                    item.name
                  )}
                </td>
                <td className="app-numeric">{brl(item.curve_value)}</td>
                <td className="app-numeric">{brl(item.market_value)}</td>
                <td className="app-numeric">
                  <Signed value={item.premium}>
                    {brl(item.premium)} ({pct(item.premium_pct, 2, true)})
                  </Signed>
                </td>
                <td>
                  <Badge tone={MARKET_STATUS_TONES[item.status]}>{MARKET_STATUS_LABELS[item.status]}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
