import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type {
  ConcentrationBreakdownDTO,
  HealthCheckDTO,
  HealthPillarDTO,
  HealthStatus,
  HealthUnit,
  PortfolioHealthDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section, type Tone } from "../../components/Section";
import { Async } from "../../components/States";
import { brl, day, num, pct, plural } from "../../utils/format";
import { ARCA_LABELS } from "../../utils/labels";
import { BarList } from "../../viz/BarList";

export const STATUS_LABELS: Record<HealthStatus, string> = {
  OK: "Ok",
  WARNING: "Atenção",
  CRITICAL: "Crítico",
  INSUFFICIENT_DATA: "Dados insuficientes",
};

export const STATUS_TONES: Record<HealthStatus, string> = {
  OK: "success",
  WARNING: "warning",
  CRITICAL: "danger",
  INSUFFICIENT_DATA: "neutral",
};

const DIMENSION_LABELS: Record<string, string> = {
  ASSET: "Por ativo",
  SECTOR: "Por setor (renda variável, sem ETFs)",
  ISSUER: "Por emissor",
  CLASS: "Por quadrante",
};

/** A check value in its unit (fractions follow ADR 0006). */
export function formatHealthValue(value: number | null | undefined, unit: HealthUnit | undefined): string {
  if (value === null || value === undefined) return "—";
  switch (unit ?? "FRACTION") {
    case "FRACTION":
      return pct(value, 1);
    case "BRL":
      return brl(value);
    case "MONTHS":
      return `${num(value, 1)} meses`;
    case "DAYS":
      return `${num(value, 0)} dias`;
    case "COUNT":
      return num(value, 1);
    default:
      return num(value, 2);
  }
}

function limitsText(check: HealthCheckDTO): string | null {
  const parts: string[] = [];
  if (check.warning_threshold !== null && check.warning_threshold !== undefined) {
    parts.push(`atenção ${formatHealthValue(check.warning_threshold, check.unit)}`);
  }
  if (check.critical_threshold !== null && check.critical_threshold !== undefined) {
    parts.push(`crítico ${formatHealthValue(check.critical_threshold, check.unit)}`);
  }
  return parts.length ? `Limites: ${parts.join(" · ")}` : null;
}

function CheckRow({ check }: Readonly<{ check: HealthCheckDTO }>) {
  const limits = limitsText(check);
  const insufficient = check.status === "INSUFFICIENT_DATA";
  return (
    <li className="health-check">
      <div className="health-check-head">
        <Badge tone={STATUS_TONES[check.status]}>{STATUS_LABELS[check.status]}</Badge>
        <strong>{check.title}</strong>
        {!insufficient && <span className="health-check-value">{formatHealthValue(check.value, check.unit)}</span>}
      </div>
      <p className="health-check-text">{check.explanation}</p>
      {check.suspicious && (
        <p className="health-check-suspicious" role="note">
          <Badge tone="warning">Dado suspeito</Badge> {check.suspicious}
        </p>
      )}
      {(check.items ?? []).length > 0 && (
        <ul className="health-check-items">
          {(check.items ?? []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {check.action && <p className="health-check-action">{check.action}</p>}
      <p className="app-muted health-check-meta">
        {[
          limits,
          insufficient && check.min_observations
            ? `Janela mínima: ${check.min_observations} (há ${check.observations ?? 0})`
            : null,
        ]
          .filter(Boolean)
          .join(" — ")}
      </p>
    </li>
  );
}

function PillarCard({ pillar }: Readonly<{ pillar: HealthPillarDTO }>) {
  return (
    <Section
      label={pillar.title}
      title={pillar.title}
      subtitle={plural(pillar.checks.length, "checagem", "checagens")}
      actions={<Badge tone={STATUS_TONES[pillar.status]}>{STATUS_LABELS[pillar.status]}</Badge>}
    >
      <ul className="health-checks">
        {pillar.checks.map((check) => (
          <CheckRow key={check.key} check={check} />
        ))}
      </ul>
    </Section>
  );
}

function labelFor(dimension: string, key: string): string {
  if (dimension === "CLASS") return ARCA_LABELS[key as keyof typeof ARCA_LABELS] ?? key;
  return key;
}

function ConcentrationBars({ breakdown }: Readonly<{ breakdown: ConcentrationBreakdownDTO }>) {
  const entries = Object.entries(breakdown.weights).slice(0, 8);
  return (
    <div>
      <h3 className="health-subheading">
        {DIMENSION_LABELS[breakdown.dimension] ?? breakdown.dimension}
        <span className="app-muted">
          {" "}
          · HHI {num(breakdown.hhi, 3)} · {num(breakdown.effective_count, 1)} efetivos
        </span>
      </h3>
      <BarList
        label={DIMENSION_LABELS[breakdown.dimension] ?? breakdown.dimension}
        bars={entries.map(([key, weight]) => ({
          id: key,
          label: labelFor(breakdown.dimension, key),
          share: weight,
          value: pct(weight, 1),
        }))}
      />
    </div>
  );
}

function Details({ data }: Readonly<{ data: PortfolioHealthDTO }>) {
  const diversification = data.diversification;
  const performance = data.performance;
  const liquidity = data.liquidity;
  return (
    <div className="app-page-stack">
      {(data.concentration ?? []).length > 0 && (
        <details className="app-card app-card-padded" open>
          <summary>Concentração em detalhe</summary>
          <div className="health-grid">
            {(data.concentration ?? []).map((b) => (
              <ConcentrationBars key={b.dimension} breakdown={b} />
            ))}
          </div>
          {(data.institutions ?? []).length > 0 && (
            <div className="app-table-wrap">
              <table className="app-table">
                <caption className="health-subheading">Exposição por instituição (FGC)</caption>
                <thead>
                  <tr>
                    <th>Instituição</th>
                    <th className="app-numeric">Valor</th>
                    <th className="app-numeric">Uso do limite</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.institutions ?? []).map((i) => (
                    <tr key={i.issuer}>
                      <td>{i.issuer}</td>
                      <td className="app-numeric">{brl(i.value_brl)}</td>
                      <td className={`app-numeric${i.usage > 1 ? " app-negative" : ""}`}>{pct(i.usage, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </details>
      )}

      {diversification && (diversification.by_asset ?? []).length > 0 && (
        <details className="app-card app-card-padded">
          <summary>Contribuição ao risco</summary>
          <p className="app-card-hint">
            Decomposição de Euler da volatilidade ({pct(diversification.volatility, 1)} a.a.) com covariância
            encolhida por Ledoit-Wolf (intensidade {num(diversification.shrinkage, 2)}) em{" "}
            {diversification.observations} pregões. Renda fixa segue o CDI.
          </p>
          <BarList
            label="Risco por quadrante"
            bars={(diversification.by_class ?? []).map((s) => ({
              id: s.label,
              label: ARCA_LABELS[s.label as keyof typeof ARCA_LABELS] ?? s.label,
              share: s.risk_share,
              value: pct(s.risk_share, 1),
              note: `${pct(s.weight, 1)} do peso`,
              second: s.weight,
            }))}
          />
          <BarList
            label="Risco por ativo"
            bars={(diversification.by_asset ?? []).slice(0, 10).map((s) => ({
              id: s.label,
              label: s.label,
              share: s.risk_share,
              value: pct(s.risk_share, 1),
              note: `${pct(s.weight, 1)} do peso`,
              second: s.weight,
            }))}
          />
          {(diversification.excluded ?? []).length > 0 && (
            <p className="app-muted">Sem histórico suficiente: {(diversification.excluded ?? []).join(", ")}.</p>
          )}
        </details>
      )}

      {performance && (performance.rolling ?? []).length > 0 && (
        <details className="app-card app-card-padded">
          <summary>Janela móvel de 12 meses</summary>
          <div className="app-table-wrap">
            <table className="app-table">
              <thead>
                <tr>
                  <th>Fim da janela</th>
                  <th className="app-numeric">Retorno</th>
                  <th className="app-numeric">Sharpe</th>
                </tr>
              </thead>
              <tbody>
                {(performance.rolling ?? []).map((p) => (
                  <tr key={p.end}>
                    <td>{day(p.end)}</td>
                    <td className="app-numeric">{pct(p.cumulative_return, 1, true)}</td>
                    <td className="app-numeric">{num(p.sharpe, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {performance && Object.keys(performance.class_returns ?? {}).length > 0 && (
        <details className="app-card app-card-padded">
          <summary>Retorno por quadrante (TWR aproximado)</summary>
          <p className="app-card-hint">
            Calculado a partir do valor e do custo de cada quadrante nos retratos diários; vendas com lucro entram
            no retorno do dia e proventos ficam de fora.
          </p>
          <ul>
            {Object.entries(performance.class_returns ?? {}).map(([key, value]) => (
              <li key={key}>
                {ARCA_LABELS[key as keyof typeof ARCA_LABELS] ?? key}: {pct(value, 1, true)}
              </li>
            ))}
          </ul>
        </details>
      )}

      {(data.quality ?? []).length > 0 && (
        <details className="app-card app-card-padded">
          <summary>Qualidade por ativo</summary>
          <div className="app-table-wrap">
            <table className="app-table">
              <thead>
                <tr>
                  <th>Ativo</th>
                  <th className="app-numeric">Peso</th>
                  <th className="app-numeric">Checklist</th>
                  <th className="app-numeric">F-score</th>
                  <th className="app-numeric">Z''-score</th>
                </tr>
              </thead>
              <tbody>
                {(data.quality ?? []).map((q) => (
                  <tr key={q.ticker}>
                    <td>
                      {q.ticker} {q.stale && <Badge tone="warning">Vencido</Badge>}
                    </td>
                    <td className="app-numeric">{pct(q.weight, 1)}</td>
                    <td className="app-numeric">{num(q.checklist_ratio, 2)}</td>
                    <td className="app-numeric">{q.f_score ?? "—"}</td>
                    <td className="app-numeric">{num(q.z_score, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {liquidity && ((liquidity.maturities_12m ?? []).length > 0 || (liquidity.bracket_lots ?? []).length > 0) && (
        <details className="app-card app-card-padded">
          <summary>Vencimentos e faixas de IR</summary>
          {(liquidity.maturities_12m ?? []).length > 0 && (
            <ul>
              {(liquidity.maturities_12m ?? []).map((m) => (
                <li key={`${m.ticker}-${m.maturity_date}`}>
                  {m.ticker}: vence em {day(m.maturity_date)} ({brl(m.value_brl)})
                </li>
              ))}
            </ul>
          )}
          {(liquidity.bracket_lots ?? []).length > 0 && (
            <ul>
              {(liquidity.bracket_lots ?? []).map((lot) => (
                <li key={`${lot.ticker}-${lot.start_date}`}>
                  {lot.ticker} (compra de {day(lot.start_date)}): IR cai de {pct(lot.current_rate, 1)} para{" "}
                  {pct(lot.next_rate, 1)} em {day(lot.next_bracket_date)}; esperar economiza{" "}
                  {brl(lot.tax_saving_by_waiting)}
                </li>
              ))}
            </ul>
          )}
        </details>
      )}
    </div>
  );
}

/** The diagnosis in words: what is worst, where, and how much is still unmeasured. */
export function healthStory(data: PortfolioHealthDTO): { tone: Tone; text: string } {
  const checks = data.pillars.flatMap((p) => p.checks.map((c) => ({ check: c, pillar: p.title })));
  const of = (status: HealthStatus) => checks.filter((c) => c.check.status === status);
  const critical = of("CRITICAL");
  const warning = of("WARNING");
  const unmeasured = of("INSUFFICIENT_DATA").length;
  const where = (items: typeof checks) =>
    items
      .slice(0, 3)
      .map((c) => `${c.check.title} (${c.pillar})`)
      .join(", ");
  const tail = unmeasured > 0 ? ` ${plural(unmeasured, "checagem ainda não tem", "checagens ainda não têm")} dados suficientes.` : "";
  const base = `A carteira de ${brl(data.total_value_brl)} em ${day(data.as_of_date)}`;
  if (critical.length > 0) {
    return {
      tone: "negative",
      text: `${base} tem ${plural(critical.length, "ponto crítico", "pontos críticos")}: ${where(critical)}. Resolva estes antes dos demais.${tail}`,
    };
  }
  if (warning.length > 0) {
    return {
      tone: "caution",
      text: `${base} não tem pontos críticos, mas ${plural(warning.length, "checagem pede", "checagens pedem")} atenção: ${where(warning)}.${tail}`,
    };
  }
  return { tone: "positive", text: `${base} está dentro de todos os limites medidos.${tail}` };
}

function Summary({ data }: Readonly<{ data: PortfolioHealthDTO }>) {
  const checks = data.pillars.flatMap((p) => p.checks);
  const count = (status: HealthStatus) => checks.filter((c) => c.status === status).length;
  const story = healthStory(data);
  return (
    <>
      <Lead tone={story.tone}>
        <p>{story.text}</p>
      </Lead>
      <KpiGrid
        label="Checagens por situação"
        items={[
          { label: "Críticas", value: num(count("CRITICAL"), 0), tone: count("CRITICAL") ? "negative" : "neutral" },
          { label: "Em atenção", value: num(count("WARNING"), 0), tone: count("WARNING") ? "caution" : "neutral" },
          { label: "Ok", value: num(count("OK"), 0), tone: "positive" },
          { label: "Sem dados suficientes", value: num(count("INSUFFICIENT_DATA"), 0), note: "Entram quando houver histórico." },
        ]}
      />
    </>
  );
}

const HEALTH_NOTES = [
  "Os pilares aparecem do pior para o melhor; não há média que esconda um crítico.",
  "Cada checagem compara um número da carteira com os limites de atenção e crítico definidos na Estratégia.",
  "Métricas de risco e desempenho exigem uma janela mínima de pregões; antes disso ficam como “dados insuficientes”.",
];

export function HealthPage() {
  const health = useApi("portfolio-health", () => api.portfolio.health());
  return (
    <div className="app-page">
      <PageHeader
        title="Saúde da carteira"
        subtitle="Sete pilares: aderência à política, concentração, diversificação, risco, desempenho, qualidade e liquidez."
      />
      <Async state={health} lines={8}>
        {(data) => (
          <div className="app-page-stack">
            <Summary data={data} />
            {data.pillars.map((pillar) => (
              <PillarCard key={pillar.pillar} pillar={pillar} />
            ))}
            <Details data={data} />
            <Notes items={HEALTH_NOTES} />
            <p className="app-meta">
              Os limites ficam na <Link to="/settings/strategy">Estratégia</Link>.
            </p>
          </div>
        )}
      </Async>
    </div>
  );
}
