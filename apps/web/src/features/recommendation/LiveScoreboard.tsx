/** Placar ao vivo (Phase 45.8a): your ARCA money, on the same dates, under each strategy. The
 *  part rebuilt from the past is labelled; the verdict waits for 12 months of record. */

import { api } from "../../api/endpoints";
import type { LiveBoardDTO, LiveLineDTO, LiveRankDTO } from "../../api/types";
import { useScreenData } from "../../api/query";
import { Badge } from "../../components/Badge";
import { KpiGrid, Lead, Notes } from "../../components/Section";
import { Async, Empty } from "../../components/States";
import { brl, brlCompact, day, pct } from "../../utils/format";
import { TrendChart, type TrendSeries } from "../../viz/TrendChart";

const CHART_LINES: Array<[string, string]> = [
  ["RECOMMENDATION", "var(--viz-serie-2)"],
  ["INDEX_ARCA", "var(--viz-serie-3)"],
  ["CDI", "var(--viz-serie-4)"],
];

function rankText(rank: LiveRankDTO, what: string): string {
  return (
    `${what}, a sua carteira bateu ${pct(rank.share, 0)} das ${rank.portfolios} carteiras aleatórias ` +
    `(intervalo de ${pct(rank.low, 0)} a ${pct(rank.high, 0)}), pela TIR sobre o mesmo dinheiro.`
  );
}

function verdict(data: LiveBoardDTO): string {
  const since = day(data.prospective_since);
  if (!data.verdict_ready)
    return (
      `Registro daqui para frente desde ${since}: ${data.prospective_months} de 12 meses. ` +
      "Até completar 12 meses, o placar mostra as medidas, sem veredito; o que veio antes foi refeito do passado."
    );
  const rec = (data.lines ?? []).find((l) => l.key === "RECOMMENDATION");
  const mine = rec?.yours_prospective?.irr;
  const theirs = rec?.prospective?.irr;
  if (rec == null || mine == null || theirs == null)
    return `Registro daqui para frente desde ${since}: ${data.prospective_months} meses.`;
  const ahead = theirs > mine;
  return (
    `Desde ${since}, a recomendação ${ahead ? "está à frente" : "está atrás"} da sua carteira: ` +
    `TIR de ${pct(theirs, 1)} contra ${pct(mine, 1)} ao ano, com o mesmo dinheiro.`
  );
}

function Lines({ lines }: Readonly<{ lines: LiveLineDTO[] }>) {
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Placar ao vivo">
        <thead>
          <tr>
            <th>Estratégia</th>
            <th>Desde</th>
            <th className="app-numeric">TIR ao ano</th>
            <th className="app-numeric">Sua TIR no período</th>
            <th className="app-numeric">Valor hoje</th>
            <th className="app-numeric">Diferença para a sua</th>
            <th className="app-numeric">Queda máxima</th>
            <th className="app-numeric">Custos e IR</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.key}>
              <td>
                <strong>{line.label}</strong>{" "}
                {line.retroactive && <Badge tone="neutral">retroativo</Badge>}
              </td>
              <td>{day(line.started)}</td>
              <td className="app-numeric">{pct(line.whole.irr, 1, true)}</td>
              <td className="app-numeric">{pct(line.yours.irr, 1, true)}</td>
              <td className="app-numeric">{brl(line.whole.final_value)}</td>
              <td className={`app-numeric ${line.difference >= 0 ? "is-positive" : "is-negative"}`}>
                {line.difference >= 0 ? "+" : ""}
                {brl(line.difference)}
              </td>
              <td className="app-numeric">{pct(line.whole.max_drawdown, 1)}</td>
              <td className="app-numeric">{brl(line.whole.fees + line.whole.taxes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Curve({ data }: Readonly<{ data: LiveBoardDTO }>) {
  const curve = data.curve ?? [];
  if (curve.length < 2) return null;
  const labels = curve.map((p) => day(p.day));
  const names = Object.fromEntries((data.lines ?? []).map((l) => [l.key, l.label]));
  const series: TrendSeries[] = [
    { key: "YOURS", label: "Sua carteira", color: "var(--viz-serie-1)", values: curve.map((p) => p.yours) },
    ...CHART_LINES.filter(([key]) => key in names).map(([key, color]) => ({
      key,
      label: names[key],
      color,
      values: curve.map((p) => (p.values ?? {})[key] ?? null),
    })),
  ];
  const banded = curve.every((p) => p.random_low != null && p.random_high != null);
  return (
    <TrendChart
      title="Valor da sua carteira e das estratégias com o mesmo dinheiro, mês a mês"
      labels={labels}
      series={series}
      bands={
        banded
          ? [
              {
                key: "random",
                color: "var(--viz-serie-1)",
                low: curve.map((p) => p.random_low ?? 0),
                high: curve.map((p) => p.random_high ?? 0),
              },
            ]
          : []
      }
      hint="Faixa: 90% das carteiras aleatórias. Todas recebem o seu dinheiro ARCA nas mesmas datas."
      format={brl}
      compact={brlCompact}
    />
  );
}

export function LiveScoreboard() {
  const state = useScreenData("recommendation-live", () => api.recommendation.live());
  return (
    <Async state={state}>
      {(data) => {
        if (data.status !== "OK" || data.yours == null)
          return (
            <Empty
              title="O placar ao vivo ainda não rodou"
              hint="Ele roda todo dia útil depois do retrato da carteira; dá para pedir agora na aba Rodadas."
            />
          );
        const randoms = data.randoms;
        return (
          <div className="app-page-stack">
            <Lead tone={data.verdict_ready ? "positive" : "neutral"}>
              <p>{verdict(data)}</p>
              {randoms?.rank != null && <p>{rankText(randoms.rank, "Desde o seu primeiro aporte")}</p>}
              {data.verdict_ready && randoms?.rank_prospective != null && (
                <p>{rankText(randoms.rank_prospective, "Daqui para frente")}</p>
              )}
            </Lead>
            <KpiGrid
              label="Sua carteira ARCA"
              items={[
                { label: "Valor hoje", value: brl(data.yours.final_value), note: "pelas séries com proventos" },
                { label: "Dinheiro aplicado", value: brl(data.yours.contributed), note: "compras menos vendas" },
                { label: "TIR ao ano", value: pct(data.yours.irr, 1, true), note: "sobre o seu fluxo" },
                {
                  label: "Aleatórias (TIR)",
                  value: randoms?.irr_mid != null ? pct(randoms.irr_mid, 1, true) : "—",
                  note:
                    randoms?.irr_low != null
                      ? `mediana; 90% entre ${pct(randoms.irr_low, 1)} e ${pct(randoms.irr_high, 1)}`
                      : "ainda sem carteiras",
                },
              ]}
            />
            <Curve data={data} />
            <Lines lines={data.lines ?? []} />
            <Notes
              items={[
                "Todas as carteiras recebem só o seu dinheiro ARCA (sem a reserva de emergência), nas datas em que você comprou ou vendeu; nenhuma vende para rebalancear.",
                "A recomendação começa na primeira rodada guardada, com o seu patrimônio ARCA daquele dia; as outras são refeitas desde o seu primeiro aporte e vêm marcadas como retroativas.",
                "Os valores usam as séries com proventos reinvestidos; uma classe sem ativo escolhido (e a renda fixa) rende o CDI.",
                "A regra antiga reparte cada classe pela nota do Cerrado que valia em cada trimestre; sem nenhuma análise na classe, ela fica no CDI.",
              ]}
            />
          </div>
        );
      }}
    </Async>
  );
}
