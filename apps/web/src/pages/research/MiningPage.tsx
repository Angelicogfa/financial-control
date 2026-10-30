/** Garimpo (Phase 43): findings in the whole catalog of liquid stocks, why each one appeared,
 *  whether the gate trusts them, and the record of the past ones. Following a finding sends it
 *  to the watchlist (and from there to the candidates of the simulation). */

import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { MiningFindingDTO, MiningOverviewDTO, MiningWhyDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section } from "../../components/Section";
import { Async, Empty, Spinner } from "../../components/States";
import { day, num, pct } from "../../utils/format";

const SIGNAL_LABELS: Record<string, string> = {
  VALUE: "Valor",
  QUALITY: "Qualidade",
  IMPROVEMENT: "Melhora",
  MOMENTUM: "Momentum",
};
const SIGNALS = ["VALUE", "QUALITY", "IMPROVEMENT", "MOMENTUM"];

function Follow({ finding, onDone }: Readonly<{ finding: MiningFindingDTO; onDone: () => void }>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A registered asset is reached through its ticker; only the others can be followed.
  if (finding.asset_id) return null;
  const follow = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.research.follow({ ticker: finding.ticker, asset_type: "STOCK_BR", name: finding.company || finding.ticker });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className="app-secondary-button" disabled={busy} onClick={follow}>
        {busy && <Spinner size="sm" />}
        <span>Seguir</span>
      </button>
      {error && (
        <span className="app-muted" role="alert">
          {error}
        </span>
      )}
    </>
  );
}

function Findings({ data, onFollowed }: Readonly<{ data: MiningOverviewDTO; onFollowed: () => void }>) {
  const findings = data.findings ?? [];
  if (findings.length === 0) return <Empty title="Nenhum achado nesta semana" hint="Faltam empresas com sinais no último mês." />;
  // The last column only holds "Seguir", for the findings not registered yet.
  const followable = findings.some((f) => !f.asset_id);
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label={data.trusted ? "Achados da semana" : "Ranking em observação"}>
        <thead>
          <tr>
            <th className="app-numeric">#</th>
            <th>Ativo</th>
            <th>Por que apareceu</th>
            {SIGNALS.map((s) => (
              <th key={s} className="app-numeric">
                {SIGNAL_LABELS[s]}
              </th>
            ))}
            <th className="app-numeric">Esperado ao ano</th>
            {followable && <th />}
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <tr key={f.ticker}>
              <td className="app-numeric">{f.rank}</td>
              <td className="app-cell-wrap">
                {f.asset_id ? (
                  <Link className="app-link" to={`/asset/${f.asset_id}`}>
                    {f.ticker}
                  </Link>
                ) : (
                  <strong>{f.ticker}</strong>
                )}
                <div className="app-muted">{[f.company, f.sector].filter(Boolean).join(" · ")}</div>
              </td>
              <td className="app-cell-wrap">{f.reason}</td>
              {SIGNALS.map((s) => (
                <td key={s} className="app-numeric">
                  {f.signals?.[s] === undefined ? "—" : num(f.signals[s], 1)}
                </td>
              ))}
              <td className="app-numeric">{pct(f.score_annual, 1, true)}</td>
              {followable && (
                <td className="app-row-actions">
                  <Follow finding={f} onDone={onFollowed} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Record({ data }: Readonly<{ data: MiningOverviewDTO }>) {
  const lines = data.record ?? [];
  if (lines.length === 0)
    return <p className="app-muted">O placar começa quando os primeiros achados completarem 3 meses.</p>;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Placar dos achados">
        <thead>
          <tr>
            <th>Lista</th>
            <th className="app-numeric">Meses depois</th>
            <th className="app-numeric">Semanas</th>
            <th className="app-numeric">Bateram o universo</th>
            <th className="app-numeric">Diferença ao ano</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => (
            <tr key={`${l.trusted}-${l.horizon}`}>
              <td>{l.trusted ? "Achados" : "Ranking em observação"}</td>
              <td className="app-numeric">{l.horizon}</td>
              <td className="app-numeric">{l.runs}</td>
              <td className="app-numeric">
                {pct(l.beat_share, 0)} <span className="app-muted">({pct(l.beat_low, 0)} a {pct(l.beat_high, 0)})</span>
              </td>
              <td className="app-numeric">{pct(l.mean_excess_annual, 1, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Why() {
  const [ticker, setTicker] = useState("");
  const [result, setResult] = useState<MiningWhyDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ticker.trim()) return;
    setError(null);
    try {
      setResult(await api.research.miningWhy(ticker.trim().toUpperCase()));
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <div className="app-page-stack">
      <form className="app-button-row" onSubmit={ask}>
        <div className="app-field">
          <label htmlFor="mining-why">Ticker</label>
          <input id="mining-why" value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="ex.: WEGE3" />
        </div>
        <button type="submit" className="app-secondary-button">
          Ver
        </button>
      </form>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div role="status">
          <p>
            <strong>{result.ticker}</strong>:{" "}
            {result.status === "FOUND"
              ? `está entre os achados (posição ${result.rank} de ${result.ranked}).`
              : result.status === "RANKED"
                ? `posição ${result.rank} de ${result.ranked}; esperado ${pct(result.score_annual, 1, true)} ao ano, contra ${pct(result.cutoff_annual, 1, true)} do último achado.`
                : "fora do ranking desta semana."}
          </p>
          <Notes items={result.reasons ?? []} title="O que pesou" />
        </div>
      )}
    </div>
  );
}

export function MiningPage() {
  const state = useApi("mining", () => api.research.mining());
  return (
    <div className="app-page">
      <PageHeader
        title="Garimpo"
        subtitle="Achados nas ações líquidas de todo o catálogo: o que os dados dizem merecer um olhar, e por quê."
      />
      <Async state={state}>
        {(data) => {
          if (data.status === "NOT_RUN") return <Empty title="O garimpo ainda não rodou" hint={data.reason} />;
          const weights = data.weights ?? [];
          return (
            <div className="app-page-stack">
              <Lead tone={data.trusted ? "positive" : "caution"}>
                <p>
                  {data.trusted ? (
                    <>
                      <Badge tone="success">Achados</Badge> {data.reason}
                    </>
                  ) : (
                    <>
                      <Badge tone="warning">Ranking em observação</Badge> {data.reason} A lista abaixo mostra o
                      ranking da semana, mas ainda não são achados confiáveis.
                    </>
                  )}
                </p>
              </Lead>
              <KpiGrid
                label="Resultado fora da amostra"
                items={[
                  {
                    label: "Achados sobre o universo",
                    value: pct(data.oos_excess_annual, 1, true),
                    note: `ao ano, depois de ${pct(data.cost_annual, 1)} de custos`,
                    tone: (data.oos_excess_annual ?? 0) > 0 ? "positive" : "caution",
                  },
                  { label: "Confiança", value: pct(data.oos_probability, 0), note: `${data.oos_months} meses fora da amostra` },
                  { label: "Meses que ganharam", value: pct(data.oos_hit_rate, 0) },
                  {
                    label: "Chance de perder do universo",
                    value:
                      data.loss_probability === null || data.loss_probability === undefined
                        ? "—"
                        : pct(data.loss_probability, 0),
                    note: `${data.variants} variantes testadas${
                      data.pbo === null || data.pbo === undefined ? "" : `; PBO ${pct(data.pbo, 0)}`
                    }`,
                    tone:
                      data.loss_probability !== null && data.loss_probability !== undefined && data.loss_probability > 0.25
                        ? "negative"
                        : "neutral",
                  },
                ]}
              />
              <Section
                title={data.trusted ? "Achados da semana" : "Ranking da semana (em observação)"}
                subtitle={data.found_on ? `Rodado em ${day(data.found_on)}, com os sinais de ${day(data.month)}.` : undefined}
              >
                <Findings data={data} onFollowed={state.reload} />
              </Section>
              <Section title="Peso de cada sinal" subtitle="Retorno a mais ao ano por desvio do sinal, medido no passado.">
                <dl className="app-definition-list">
                  {weights.map((w) => (
                    <div key={w.signal} style={{ display: "contents" }}>
                      <dt>{SIGNAL_LABELS[w.signal]}</dt>
                      <dd>
                        {pct(w.estimate_annual_per_z, 1, true)}{" "}
                        {w.used ? (
                          <Badge tone="success">usado</Badge>
                        ) : (
                          <Badge>não usado ({pct(w.sign_probability, 0)} de confiança no sentido)</Badge>
                        )}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Section>
              <Section title="Placar" subtitle="Como foram os achados passados frente ao universo inteiro.">
                <Record data={data} />
              </Section>
              <Section title="Por que um ativo não apareceu?">
                <Why />
              </Section>
              <Notes
                items={[
                  "Os sinais usam só o que se sabia em cada mês: balanços pela data de entrega à CVM e preços até o mês.",
                  "Achados são probabilidades um pouco melhores que a média, não recomendações; o placar mostra quantos acertaram.",
                  "Seguir um achado o coloca na watchlist; de lá, os candidatos da simulação medem o efeito na sua carteira.",
                ]}
              />
            </div>
          );
        }}
      </Async>
    </div>
  );
}
