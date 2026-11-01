/** The full optimizer of a class (Phase 45.8b), next to the construction: its weights with the
 *  90% range over the draws and how often each asset entered. A reference until it beats the
 *  construction in the walk-forward test; then its weights decide the contribution. */

import type { BacktestDTO, OptimizedDTO } from "../../api/types";
import { Badge } from "../../components/Badge";
import { KpiGrid, Lead, Notes } from "../../components/Section";
import { num, pct } from "../../utils/format";

export function Optimized({ optimized, inUse }: Readonly<{ optimized: OptimizedDTO | null | undefined; inUse: boolean }>) {
  if (optimized == null) return <p className="app-muted">Esta rodada é anterior ao otimizador.</p>;
  if (optimized.status !== "OK")
    return <p className="app-muted">O otimizador não teve candidatos nesta classe.</p>;
  const assets = optimized.assets ?? [];
  return (
    <div className="app-page-stack">
      <p>
        {inUse ? (
          <Badge tone="success">Em uso: decide o aporte</Badge>
        ) : (
          <Badge tone="neutral">Referência</Badge>
        )}{" "}
        {inUse
          ? "Venceu a construção no teste no passado: os pesos-alvo são estes."
          : "Ainda não venceu a construção no teste no passado: o aporte segue a construção."}
      </p>
      <KpiGrid
        label="Otimizador e construção"
        items={[
          {
            label: "Utilidade",
            value: num(optimized.utility, 3),
            note: `construção: ${num(optimized.construction_utility, 3)}`,
            tone: (optimized.utility ?? 0) >= (optimized.construction_utility ?? 0) ? "positive" : "caution",
          },
          {
            label: "CVaR de 12 meses",
            value: pct(optimized.cvar, 1),
            note: `construção ${pct(optimized.construction_cvar, 1)}; atual ${pct(optimized.current_cvar, 1)}`,
          },
          { label: "Sorteios", value: String(optimized.draws), note: "média dos pesos" },
        ]}
      />
      <div className="app-table-wrap">
        <table className="app-table" aria-label="Otimizador">
          <thead>
            <tr>
              <th>Ativo</th>
              <th className="app-numeric">Pela construção</th>
              <th className="app-numeric">Pelo otimizador</th>
              <th className="app-numeric">Faixa de 90%</th>
              <th className="app-numeric">Entra nos sorteios</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((a) => (
              <tr key={a.ticker}>
                <td>
                  <strong>{a.ticker}</strong>
                </td>
                <td className="app-numeric">{(a.construction_weight ?? 0) > 0 ? pct(a.construction_weight, 1) : "—"}</td>
                <td className="app-numeric">{pct(a.weight, 1)}</td>
                <td className="app-numeric">
                  {pct(a.low, 0)} a {pct(a.high, 0)}
                </td>
                <td className="app-numeric">{pct(a.frequency, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(optimized.notes ?? []).length > 0 && <Notes items={optimized.notes ?? []} tone="caution" />}
    </div>
  );
}

/** The optimizer's verdict in the walk-forward test (Phase 45.8b). */
export function OptimizerVerdict({ data }: Readonly<{ data: BacktestDTO }>) {
  if (data.optimizer_status == null || data.optimizer_status === "NOT_RUN") return null;
  return (
    <div className="app-page-stack">
      <p>
        <strong>Otimizador contra a construção</strong>
      </p>
      <Lead tone={data.optimizer_passed ? "positive" : "caution"}>
        <p>
          {data.optimizer_passed ? <Badge tone="success">Passou</Badge> : <Badge tone="warning">Não passou</Badge>}{" "}
          {data.optimizer_reason}
        </p>
      </Lead>
      {data.optimizer_status === "OK" && (
        <KpiGrid
          label="Otimizador no passado"
          items={[
            { label: "Otimizador sobre a classe", value: pct(data.optimizer_annual, 1, true), note: "ao ano" },
            {
              label: "Diferença para a construção",
              value: pct(data.optimizer_difference_annual, 1, true),
              note: `${pct(data.optimizer_probability, 0)} de chance de ser positiva`,
              tone: (data.optimizer_difference_annual ?? 0) > 0 ? "positive" : "caution",
            },
            {
              label: "Meses que ganhou",
              value: pct(data.optimizer_hit_rate, 0),
              note: `${data.optimizer_months} meses`,
            },
          ]}
        />
      )}
    </div>
  );
}
