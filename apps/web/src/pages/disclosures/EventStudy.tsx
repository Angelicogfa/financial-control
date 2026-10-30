/** What usually happens to the price after each kind of CVM event (Phase 42.4). */

import { api } from "../../api/endpoints";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Section } from "../../components/Section";
import { Async } from "../../components/States";
import { day, num, pct } from "../../utils/format";

export function EventStudy() {
  const state = useApi("event-study", () => api.disclosures.eventStudy());
  return (
    <Async state={state}>
      {(data) =>
        data.status !== "OK" ? null : (
          <Section
            title="O que costuma acontecer depois"
            subtitle={`Retorno além do esperado pelo mercado após cada tipo de evento, em ${data.events} eventos de todas as empresas líquidas desde 2010 (estudo de ${day(data.as_of)}).`}
          >
            <div className="app-table-wrap">
              <table className="app-table" aria-label="Estudo de eventos">
                <thead>
                  <tr>
                    <th>Tipo de evento</th>
                    <th className="app-numeric">Eventos</th>
                    <th className="app-numeric">1 pregão</th>
                    <th className="app-numeric">5 pregões</th>
                    <th className="app-numeric">20 pregões</th>
                    <th className="app-numeric">Volatilidade depois</th>
                    <th>Na previsão</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.classes ?? []).map((c) => (
                    <tr key={c.event_class}>
                      <td>{c.label}</td>
                      <td className="app-numeric">{c.events}</td>
                      {[1, 5, 20].map((h) => {
                        const found = (c.horizons ?? []).find((x) => x.horizon === h);
                        return (
                          <td key={h} className="app-numeric">
                            {found ? (
                              <>
                                {pct(found.effect, 1, true)}
                                {found.sign_probability >= 0.9 && <Badge tone="info">claro</Badge>}
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                        );
                      })}
                      <td className="app-numeric">
                        {c.volatility_ratio === null || c.volatility_ratio === undefined ? "—" : `${num(c.volatility_ratio, 2)}×`}
                      </td>
                      <td>
                        {c.passed ? <Badge tone="success">entra</Badge> : <Badge tone="neutral">não entra</Badge>}
                        {c.gate_reason && <div className="app-muted">{c.gate_reason}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="app-card-hint">
              Os efeitos são puxados para zero quando há poucos eventos ou muita variação; “claro” marca os que têm 90% de
              confiança no sentido. {data.confounded} eventos perto da entrega de balanço ficaram de fora. Só entra na
              previsão de preço o tipo cujo efeito em 20 pregões, estimado a cada ano com os anos anteriores, previu melhor que
              zero no total e na maioria dos anos, e com o sentido claro depois de descontar o número de tipos testados
              {data.sign_threshold ? ` (${pct(data.sign_threshold, 1)} de confiança)` : ""}.
            </p>
          </Section>
        )
      }
    </Async>
  );
}
