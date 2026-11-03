/** Price forecast quality (Phase 42): how often the bands held in the past, whether valuation
 *  entered, and the jobs that recompute it (they used to sit on the market data page). */

import { api } from "../../api/endpoints";
import { manualJobs } from "../../api/jobs";
import { useScreenData } from "../../api/query";
import { JobRunList } from "../../components/JobRunList";
import { KpiGrid, Section } from "../../components/Section";
import { Async, Empty } from "../../components/States";
import { day, num, pct } from "../../utils/format";
import { SealBox } from "./shared";

export const FORECAST_JOBS = ["refresh_asset_forecasts", "estimate_forecast_models", "calibrate_forecasts"];

export function ForecastQualityPanel() {
  const state = useScreenData("forecast-quality", () => api.market.forecastQuality());
  return (
    <Section
      title="Previsão de preço dos ativos"
      subtitle="Quantas vezes as faixas da aba Probabilidades se confirmaram no passado, e as rotinas que a recalculam."
    >
      <Async state={state}>
        {(data) =>
          data.status !== "OK" ? (
            <Empty title="A calibração ainda não rodou" hint="Ela roda toda semana; dá para pedir agora abaixo." />
          ) : (
            <div className="app-page-stack">
              <KpiGrid
                label="Calibração da previsão"
                items={[
                  { label: "Faixa de 90% confirmada", value: pct(data.coverage_90, 0), note: "o ideal é perto de 90%" },
                  { label: "Faixa de 50% confirmada", value: pct(data.coverage_50, 0), note: "o ideal é perto de 50%" },
                  {
                    label: "Janelas medidas",
                    value: num(data.windows ?? 0, 0),
                    note: `${data.assets ?? 0} ativos, ${day(data.first_origin)} a ${day(data.last_origin)}`,
                  },
                  {
                    label: "Valuation na previsão",
                    value: data.valuation ? (data.valuation.passed ? "Usado" : "Não usado") : "—",
                    note: data.valuation?.reason ?? "ainda não medido",
                  },
                ]}
              />
              {data.seal && <SealBox title="Quanto confiar" seal={data.seal} />}
            </div>
          )
        }
      </Async>
      <JobRunList jobs={manualJobs(FORECAST_JOBS)} onChange={state.reload} />
    </Section>
  );
}
