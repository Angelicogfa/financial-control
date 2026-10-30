/** "Probabilidades" tab (Phase 42.1): the probable price range of the asset at 3, 6, 12 and
 *  24 months, the chances that matter (above today's price, the average paid and the fair
 *  value; a 20% fall) and what weighed on them. A distribution, never a target price.
 *  The user can compute it now for this asset alone: from 12 months of history, with a warning. */

import { useState } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type { AssetForecastDTO, ForecastEventDTO, ForecastHorizonDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { KpiGrid, Lead, Notes, Section, Segmented, type KpiSpec } from "../../components/Section";
import { Async, Empty, Spinner } from "../../components/States";
import { brl, day, parseDecimal, pct } from "../../utils/format";
import { TrendChart, type TrendSeries } from "../../viz/TrendChart";
import { SealBox } from "../simulation/shared";

/** Levels of `price_quantiles`: 1% to 99% (the API's QUANTILE_LEVELS). */
const LEVELS = Array.from({ length: 99 }, (_, i) => (i + 1) / 100);

/** P(price > `price`) read from the quantile grid, as the API computes it. */
export function chanceAbove(grid: number[], price: number): number | null {
  if (grid.length !== LEVELS.length) return null;
  if (price <= grid[0]) return 0.995;
  if (price >= grid[grid.length - 1]) return 0.005;
  const i = grid.findIndex((v) => v >= price);
  const span = grid[i] - grid[i - 1];
  const level = span > 0 ? LEVELS[i - 1] + ((price - grid[i - 1]) / span) * (LEVELS[i] - LEVELS[i - 1]) : LEVELS[i];
  return 1 - level;
}

/** Months of history the API accepts when the user asks for one asset. */
const REQUESTED_MIN_MONTHS = 12;

function RefreshButton({
  assetId,
  onDone,
  primary = false,
  label = "Calcular só para este ativo",
}: Readonly<{ assetId: number; onDone: () => void; primary?: boolean; label?: string }>) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      await api.assets.refreshForecast(assetId);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  };
  return (
    <>
      <button
        type="button"
        className={primary ? "app-primary-button" : "app-secondary-button"}
        disabled={running}
        onClick={run}
      >
        {running && <Spinner size="sm" />}
        <span>{running ? "Calculando…" : label}</span>
      </button>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

const REFERENCE_COLORS: Record<string, string> = {
  NOW: "var(--app-text-subtle)",
  AVERAGE: "var(--viz-serie-2)",
  FAIR: "var(--viz-serie-3)",
};

function FanChart({ forecast }: Readonly<{ forecast: AssetForecastDTO }>) {
  const horizons = forecast.horizons ?? [];
  const now = forecast.price_now ?? 0;
  const labels = ["Hoje", ...horizons.map((h) => `${h.months} meses`)];
  const at = (pick: (h: ForecastHorizonDTO) => number) => [now, ...horizons.map(pick)];
  const references = (horizons[0]?.thresholds ?? []).filter((t) => t.key in REFERENCE_COLORS);
  const series: TrendSeries[] = [
    { key: "p50", label: "Mediana", color: "var(--viz-serie-1)", values: at((h) => h.p50) },
    ...references.map((t) => ({
      key: t.key,
      label: t.key === "NOW" ? "Preço de hoje" : t.key === "AVERAGE" ? "Seu preço médio" : "Preço justo",
      color: REFERENCE_COLORS[t.key],
      values: labels.map(() => t.price),
    })),
  ];
  return (
    <TrendChart
      title={`Faixa provável do preço de ${forecast.ticker} nos próximos 24 meses`}
      labels={labels}
      series={series}
      bands={[
        { key: "p5-p95", color: "var(--viz-serie-1)", low: at((h) => h.p5), high: at((h) => h.p95) },
        { key: "p25-p75", color: "var(--viz-serie-1)", low: at((h) => h.p25), high: at((h) => h.p75) },
      ]}
      hint="Faixa clara: 90% dos cenários; faixa escura: metade deles; linha: a mediana."
      format={brl}
    />
  );
}

function Calculator({ horizon }: Readonly<{ horizon: ForecastHorizonDTO }>) {
  const [text, setText] = useState("");
  const price = parseDecimal(text);
  const chance = price !== null && price > 0 ? chanceAbove(horizon.price_quantiles ?? [], price) : null;
  return (
    <div className="app-page-stack">
      <div className="app-field">
        <label htmlFor="forecast-price">Preço (R$)</label>
        <input
          id="forecast-price"
          inputMode="decimal"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={horizon.p50.toFixed(2).replace(".", ",")}
        />
      </div>
      <p role="status" className="app-muted">
        {chance === null
          ? "Digite um preço para ver a chance de o ativo estar acima dele."
          : `Chance de estar acima de ${brl(price)} em ${horizon.months} meses: ${pct(chance, 0)}.`}
      </p>
    </div>
  );
}

function Forecast({ forecast, onRefreshed }: Readonly<{ forecast: AssetForecastDTO; onRefreshed: () => void }>) {
  const horizons = forecast.horizons ?? [];
  const [months, setMonths] = useState(12);
  const horizon = horizons.find((h) => h.months === months) ?? horizons[horizons.length - 1];
  if (!horizon) return <Empty title="Previsão sem horizontes" />;
  const threshold = (key: string) => horizon.thresholds?.find((t) => t.key === key);
  const fair = threshold("FAIR");
  const average = threshold("AVERAGE");
  const kpis: KpiSpec[] = [
    {
      label: "Chance de subir",
      value: pct(horizon.up.value, 0),
      note: `entre ${pct(horizon.up.low, 0)} e ${pct(horizon.up.high, 0)}`,
      tone: horizon.up.value >= 0.5 ? "positive" : "caution",
    },
    {
      label: "Chance de cair 20% ou mais",
      value: pct(horizon.fall_20.value, 0),
      note: `abaixo de ${brl((forecast.price_now ?? 0) * 0.8)}`,
      tone: horizon.fall_20.value >= 0.2 ? "negative" : "neutral",
    },
    {
      label: "Preço mediano",
      value: brl(horizon.p50),
      note: `retorno total mediano de ${pct(horizon.total_return_p50, 1, true)}`,
    },
  ];
  if (fair) kpis.push({ label: "Acima do preço justo", value: pct(fair.probability, 0), note: brl(fair.price) });
  else if (average) kpis.push({ label: "Acima do seu preço médio", value: pct(average.probability, 0), note: brl(average.price) });

  const notes = [
    "É uma distribuição de preços possíveis, não um preço-alvo: em 1 a cada 10 vezes o preço sai da faixa de 90%.",
    `O modelo usa ${forecast.months_used ?? "—"} meses de histórico, a sensibilidade do ativo à sua classe (beta ${
      forecast.beta?.toFixed(2) ?? "—"
    }) e um excesso próprio puxado para a média da classe.`,
    `O preço desconta os proventos (cerca de ${pct(forecast.dividend_yield_annual, 1)} ao ano); o retorno total os inclui.`,
    ...(forecast.warnings ?? []),
  ];

  const cautions = forecast.cautions ?? [];
  return (
    <div className="app-page-stack">
      <Lead tone={cautions.length > 0 ? "caution" : horizon.up.value >= 0.5 ? "positive" : "caution"}>
        <p>{forecast.lead}</p>
      </Lead>
      <Notes items={cautions} title="Leia com cautela" tone="caution" />
      <Section
        title="Faixa provável do preço"
        subtitle={`Calculada em ${day(forecast.as_of)} a partir de ${brl(forecast.price_now)}${
          forecast.requested ? ", a seu pedido" : ""
        }.`}
        actions={
          <Segmented
            label="Horizonte"
            options={horizons.map((h) => [String(h.months), `${h.months} meses`] as [string, string])}
            value={String(horizon.months)}
            onChange={(key) => setMonths(Number(key))}
          />
        }
      >
        <KpiGrid items={kpis} label={`Chances em ${horizon.months} meses`} />
        <FanChart forecast={forecast} />
      </Section>
      <div className="app-table-wrap">
        <table className="app-table" aria-label={`Chances em ${horizon.months} meses`}>
          <thead>
            <tr>
              <th>Em {horizon.months} meses ({day(horizon.target_date)})</th>
              <th className="app-numeric">Preço</th>
              <th className="app-numeric">Chance</th>
            </tr>
          </thead>
          <tbody>
            {(horizon.thresholds ?? []).map((t) => (
              <tr key={t.key}>
                <td>{t.label}</td>
                <td className="app-numeric">{brl(t.price)}</td>
                <td className="app-numeric">{pct(t.probability, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Section title="E se o preço for…" subtitle={`Chance de passar de um preço em ${horizon.months} meses.`}>
        <Calculator key={horizon.months} horizon={horizon} />
      </Section>
      <Section title="O que pesou" subtitle="Contribuição de cada parte ao retorno esperado ao ano.">
        <dl className="app-definition-list">
          {(forecast.drivers ?? []).map((d) => (
            <div key={d.key} style={{ display: "contents" }}>
              <dt>{d.label}</dt>
              <dd>
                {d.annual === null || d.annual === undefined ? "—" : pct(d.annual, 1, true)}
                {d.note && <div className="app-muted">{d.note}</div>}
              </dd>
            </div>
          ))}
        </dl>
        <RecentEvents events={forecast.recent_events ?? []} />
      </Section>
      <SealBox title="Quanto confiar" seal={forecast.seal} />
      <Notes items={notes} />
      <div className="app-button-row">
        <RefreshButton assetId={forecast.asset_id} onDone={onRefreshed} label="Recalcular agora" />
      </div>
    </div>
  );
}

/** CVM events of the last 20 trading days (Phase 42.5): only the kinds that passed the
 *  out-of-sample test move the forecast; the others are listed as "sem efeito comprovado". */
function RecentEvents({ events }: Readonly<{ events: ForecastEventDTO[] }>) {
  if (events.length === 0) return null;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Eventos recentes da CVM">
        <thead>
          <tr>
            <th>Evento recente</th>
            <th className="app-numeric">Entrega</th>
            <th className="app-numeric">Efeito que falta</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={`${e.event_date}-${e.event_class}`}>
              <td>
                {e.label}
                <div className="app-muted">{e.note}</div>
              </td>
              <td className="app-numeric">{day(e.event_date)}</td>
              <td className="app-numeric">{e.used ? pct(e.effect, 1, true) : "sem efeito comprovado"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ForecastTab({ assetId }: Readonly<{ assetId: number }>) {
  const state = useApi(`asset-forecast-${assetId}`, () => api.assets.forecast(assetId));
  return (
    <Async state={state}>
      {(forecast) => {
        if (forecast.status === "OK") return <Forecast forecast={forecast} onRefreshed={state.reload} />;
        const refresh = <RefreshButton assetId={assetId} onDone={state.reload} primary />;
        if (forecast.status === "NOT_COMPUTED")
          return (
            <Empty
              title="Previsão ainda não calculada"
              hint="O worker calcula a previsão todo dia útil; dá para calcular agora só para este ativo."
            >
              {refresh}
            </Empty>
          );
        const short = forecast.status === "INSUFFICIENT_HISTORY";
        const canAsk = !short || (!forecast.requested && (forecast.months_used ?? 0) >= REQUESTED_MIN_MONTHS);
        return (
          <div className="app-page-stack">
            <Empty
              title={short ? "Histórico insuficiente" : "Previsão oculta por baixa confiança"}
              hint={
                short
                  ? (forecast.warnings ?? []).join(" ")
                  : "As faixas ainda não se confirmaram bem no passado. Dá para ver a previsão deste ativo mesmo assim, com aviso de confiança."
              }
            >
              {canAsk && refresh}
            </Empty>
            <SealBox title="Quanto confiar" seal={forecast.seal} />
          </div>
        );
      }}
    </Async>
  );
}
