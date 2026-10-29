import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  AlertDTO,
  PortfolioAnalyticsResponseDTO,
  PortfolioReportResponseDTO,
  SnapshotPointDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { ErrorBanner, Loading } from "../../components/States";
import { brl, brlCompact, daysAgo, monthLabel, pct, points } from "../../utils/format";
import { SEVERITY_TONES } from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { Sparkline } from "../../viz/Sparkline";
import { TrendChart } from "../../viz/TrendChart";
import {
  alignCurves,
  curveReturn,
  headline,
  lastMonths,
  marketSplit,
  patrimonyChange,
  type Change,
  type MarketSplit,
} from "./story";
import { AccountsWealth } from "./AccountsWealth";
import { DeclaredEarnings } from "./DeclaredEarnings";
import { LatestStudy } from "./LatestStudy";
import { QuoteClock } from "./QuoteClock";

function Indicator({
  label,
  value,
  note,
  trend,
  detail,
}: Readonly<{ label: string; value: string; note?: ReactNode; trend?: ReactNode; detail?: ReactNode }>) {
  return (
    <div className="home-kpi">
      <span className="home-kpi-label">{label}</span>
      <strong className="home-kpi-value" title={value}>
        {value}
      </strong>
      {note && <span className="home-kpi-note">{note}</span>}
      {trend}
      {detail}
    </div>
  );
}

/** Bolsa (Caixa, Ações, Real Estate) and Internacional under the total, each with its rise or fall. */
function SplitList({ groups }: Readonly<{ groups: MarketSplit[] }>) {
  const shown = groups.filter((g) => g.value > 0 || g.invested > 0);
  if (shown.length === 0) return null;
  return (
    <dl className="home-split" aria-label="Patrimônio por mercado">
      {shown.map((g) => {
        const up = (g.change ?? 0) >= 0;
        return (
          <div key={g.key} className="home-split-row">
            <dt>
              {g.label} <span className="app-muted">{pct(g.share, 0)}</span>
            </dt>
            <dd>
              <span className="home-split-value">{brl(g.value)}</span>
              {g.change !== null && (
                <span
                  className={`home-delta ${up ? "is-up" : "is-down"}`}
                  title={`Resultado consolidado de ${brl(g.pnl)} sobre ${brl(g.invested)} investidos`}
                >
                  <span aria-hidden="true">{up ? "▲" : "▼"}</span> {up ? "alta" : "queda"} de {pct(Math.abs(g.change), 1)} sobre o investido
                </span>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

interface DetailRow {
  label: string;
  value: string;
  tone?: "up" | "down";
}

/** Supporting figures under an indicator: what the headline number is made of. */
function DetailList({ rows, label }: Readonly<{ rows: DetailRow[]; label: string }>) {
  if (rows.length === 0) return null;
  return (
    <dl className="home-split" aria-label={label}>
      {rows.map((row) => (
        <div key={row.label} className="home-split-row">
          <dt>{row.label}</dt>
          <dd className={row.tone ? `home-delta is-${row.tone}` : undefined}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

const signedTone = (value: number | null | undefined): DetailRow["tone"] =>
  value === null || value === undefined || value === 0 ? undefined : value > 0 ? "up" : "down";

function Delta({ change }: Readonly<{ change: Change | null }>) {
  if (!change) return null;
  const up = change.value >= 0;
  return (
    <span className={`home-delta ${up ? "is-up" : "is-down"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {pct(Math.abs(change.value))} em {change.days} dias
    </span>
  );
}

const CURVE_COLORS: Record<string, string> = {
  PORTFOLIO: "var(--viz-serie-1)",
  CDI: "var(--viz-serie-2)",
  IBOV: "var(--viz-serie-3)",
};
const CURVE_LABELS: Record<string, string> = { PORTFOLIO: "Carteira", CDI: "CDI", IBOV: "Ibovespa" };

function KpiAct({
  report,
  snapshots,
  analytics,
  onQuotesRefreshed,
}: Readonly<{
  report: PortfolioReportResponseDTO;
  snapshots: SnapshotPointDTO[];
  analytics: PortfolioAnalyticsResponseDTO | null;
  onQuotesRefreshed: () => void;
}>) {
  const change = patrimonyChange(snapshots, report.total_current_value_brl);
  const twr = analytics?.status === "OK" ? curveReturn(analytics.curves.PORTFOLIO) : null;
  const cdi = curveReturn(analytics?.curves.CDI);
  const reserve = report.value_by_purpose_brl?.EMERGENCY_RESERVE ?? 0;
  const months = lastMonths(report.earnings_by_month);
  const ibov = curveReturn(analytics?.curves.IBOV);
  const lastMonth = months.length > 0 ? months[months.length - 1] : null;
  const total = report.total_current_value_brl;
  const resultRows: DetailRow[] = [
    { label: "Valorização", value: brl(report.total_unrealized_pnl_brl), tone: signedTone(report.total_unrealized_pnl_brl) },
    { label: "Vendas realizadas", value: brl(report.total_realized_pnl_brl), tone: signedTone(report.total_realized_pnl_brl) },
    { label: "Proventos recebidos", value: brl(report.total_received_earnings_brl), tone: signedTone(report.total_received_earnings_brl) },
  ];
  const returnRows: DetailRow[] =
    twr === null
      ? []
      : [
          ...(cdi === null ? [] : [{ label: "Contra o CDI", value: pct(twr - cdi, 1, true), tone: signedTone(twr - cdi) }]),
          ...(ibov === null ? [] : [{ label: "Contra o Ibovespa", value: pct(twr - ibov, 1, true), tone: signedTone(twr - ibov) }]),
        ];
  const earningsRows: DetailRow[] = [
    { label: "Média por mês", value: brl(report.total_earnings_12m_brl / 12) },
    ...(lastMonth ? [{ label: `Último mês (${monthLabel(lastMonth[0])})`, value: brl(lastMonth[1]) }] : []),
  ];

  return (
    <section className="home-act" aria-labelledby="act-figures">
      <div className="home-act-head">
        <h2 id="act-figures" className="home-act-title">
          Indicadores
        </h2>
        <span className="home-act-meta">
          <span className="app-muted">Posição em {report.as_of_date.split("-").reverse().join("/")}</span>
          <QuoteClock onRefreshed={onQuotesRefreshed} />
        </span>
      </div>
      <div className="home-kpis">
        <Indicator
          label="Patrimônio"
          value={brl(report.total_current_value_brl)}
          note={<Delta change={change} />}
          trend={<Sparkline values={snapshots.map((s) => s.market_value)} />}
          detail={<SplitList groups={marketSplit(report.allocations)} />}
        />
        <Indicator
          label="Resultado consolidado"
          value={brlCompact(report.total_consolidated_pnl_brl)}
          note={`${points(report.total_consolidated_return_pct, 1, true)} sobre o investido`}
          trend={<Sparkline values={snapshots.map((s) => s.consolidated_pnl)} />}
          detail={<DetailList label="Composição do resultado" rows={resultRows} />}
        />
        <Indicator
          label="Rentabilidade 12 meses"
          value={twr === null ? "—" : pct(twr, 1, true)}
          note={
            twr === null
              ? "Histórico insuficiente"
              : cdi === null
                ? "Taxa ponderada pelo tempo"
                : `CDI no período: ${pct(cdi, 1)}`
          }
          detail={<DetailList label="Rentabilidade contra as referências" rows={returnRows} />}
        />
        <Indicator
          label="Proventos 12 meses"
          value={brlCompact(report.total_earnings_12m_brl)}
          note={`Yield on cost ${points(report.portfolio_yield_on_cost_pct, 1)}`}
          trend={<Sparkline values={months.map(([, v]) => v)} />}
          detail={<DetailList label="Proventos por mês" rows={earningsRows} />}
        />
        {reserve > 0 && (
          <Indicator
            label="Reserva de emergência"
            value={brlCompact(reserve)}
            note="Fora da ARCA"
            detail={
              <DetailList
                label="Peso da reserva"
                rows={[{ label: "Do patrimônio", value: pct(total > 0 ? reserve / total : 0, 1) }]}
              />
            }
          />
        )}
      </div>
    </section>
  );
}

function AlertsPanel({ alerts, onChange }: Readonly<{ alerts: AlertDTO[]; onChange: () => void }>) {
  const [error, setError] = useState<string | null>(null);
  const dismiss = async (key: string) => {
    setError(null);
    try {
      await api.alerts.dismiss({ key, days: 7 });
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <div className="home-panel">
      <h3 className="home-panel-title">O que precisa de atenção</h3>
      <p className="home-panel-hint">Alertas da carteira e dos dados; dispensar esconde por 7 dias.</p>
      {error && <p className="app-error-banner">{error}</p>}
      {alerts.length === 0 ? (
        <p className="app-muted">Nada pendente.</p>
      ) : (
        <ul className="home-alerts">
          {alerts.slice(0, 6).map((alert) => (
            <li key={alert.key} className="home-alert">
              <Badge tone={SEVERITY_TONES[alert.severity] ?? "neutral"}>
                {alert.severity === "CRITICAL" ? "Crítico" : alert.severity === "WARNING" ? "Atenção" : "Info"}
              </Badge>
              <div>
                <p>{alert.route ? <Link className="app-link" to={alert.route}>{alert.title}</Link> : alert.title}</p>
                <small>{alert.detail}</small>
              </div>
              <button type="button" className="app-link-button" onClick={() => void dismiss(alert.key)}>
                Dispensar
              </button>
            </li>
          ))}
        </ul>
      )}
      {alerts.length > 6 && <p className="app-muted">e mais {alerts.length - 6}.</p>}
    </div>
  );
}

function AllocationPanel({ report }: Readonly<{ report: PortfolioReportResponseDTO }>) {
  const scale = Math.max(
    10,
    ...report.allocations.map((a) => Math.max(a.current_pct, a.target_pct + (a.band_pct ?? 0))),
  ) * 1.1;
  return (
    <div className="home-panel">
      <h3 className="home-panel-title">Atual × meta</h3>
      <p className="home-panel-hint">A faixa clara é a banda de tolerância; o traço, a meta.</p>
      <BarList
        label="Peso atual de cada classe contra a meta"
        bars={report.allocations.map((a) => ({
          id: a.arca_class,
          label: a.label,
          note: brl(a.current_value),
          share: a.current_pct / scale,
          goal: a.target_pct / scale,
          band: [
            Math.max(0, a.target_pct - (a.band_pct ?? 0)) / scale,
            (a.target_pct + (a.band_pct ?? 0)) / scale,
          ],
          tone: a.band_status === "BELOW" ? "is-low" : a.band_status === "ABOVE" ? "is-mid" : undefined,
          value: `${points(a.current_pct)} · meta ${points(a.target_pct, 0)}`,
        }))}
      />
    </div>
  );
}

function EvolutionPanel({
  analytics,
  failed,
}: Readonly<{ analytics: PortfolioAnalyticsResponseDTO | null; failed: boolean }>) {
  const aligned = analytics ? alignCurves(analytics.curves, ["PORTFOLIO", "CDI", "IBOV"]) : null;
  return (
    <section className="home-panel" aria-labelledby="act-evolution">
      <div className="home-panel-head">
        <h2 id="act-evolution" className="home-panel-title">
          Evolução: carteira × referências (base 100)
        </h2>
        <Link className="app-link" to="/performance">
          Ver desempenho
        </Link>
      </div>
      <p className="home-panel-hint">12 meses; a carteira usa a rentabilidade ponderada pelo tempo.</p>
      {!analytics ? (
        failed ? (
          <p className="app-muted">Não foi possível carregar o histórico agora.</p>
        ) : (
          <Loading />
        )
      ) : analytics.status !== "OK" || !aligned || aligned.labels.length < 2 ? (
        <p className="app-muted">
          Histórico insuficiente: o gráfico aparece depois de alguns retratos diários da carteira.
        </p>
      ) : (
        <TrendChart
          title="Evolução da carteira contra CDI e Ibovespa em base 100"
          labels={aligned.labels.map((d) => d.split("-").reverse().join("/"))}
          baseline={100}
          hint="Passe o mouse para ver cada dia."
          series={Object.entries(aligned.series).map(([key, values]) => ({
            key,
            label: CURVE_LABELS[key] ?? key,
            color: CURVE_COLORS[key] ?? "var(--viz-serie-4)",
            values,
          }))}
        />
      )}
    </section>
  );
}

/** Allocation and evolution stacked in the main column, alerts beside them: no gap under a short panel. */
function AllocationAct({
  report,
  analytics,
  analyticsFailed,
  alerts,
  onAlertsChange,
}: Readonly<{
  report: PortfolioReportResponseDTO;
  analytics: PortfolioAnalyticsResponseDTO | null;
  analyticsFailed: boolean;
  alerts: AlertDTO[] | null;
  onAlertsChange: () => void;
}>) {
  return (
    <section className="home-act" aria-labelledby="act-allocation">
      <div className="home-act-head">
        <h2 id="act-allocation" className="home-act-title">
          Alocação ARCA
        </h2>
        <Link className="app-link" to="/contribute">
          Aportar
        </Link>
      </div>
      <div className="home-layout">
        <div className="home-stack">
          <AllocationPanel report={report} />
          <EvolutionPanel analytics={analytics} failed={analyticsFailed} />
        </div>
        {alerts ? <AlertsPanel alerts={alerts} onChange={onAlertsChange} /> : <div className="home-panel"><Loading /></div>}
      </div>
    </section>
  );
}

/** Home = analytics (ADR 0007): headline, indicators, allocation and evolution with alerts beside. */
export function HomePage() {
  const since = daysAgo(365);
  const report = useApi("home-report", () => api.portfolio.report());
  const snapshots = useApi(`home-snapshots-${since}`, () => api.portfolio.snapshots(since));
  const analytics = useApi(`home-analytics-${since}`, () => api.portfolio.analytics(since));
  const alerts = useApi("home-alerts", () => api.alerts.list());

  const alertList = alerts.data?.alerts ?? [];
  const story =
    report.data !== null
      ? headline(report.data, patrimonyChange(snapshots.data ?? [], report.data.total_current_value_brl), alertList)
      : [];

  return (
    <div className="app-page">
      <PageHeader
        title="Como está a carteira"
        subtitle={<span className="home-headline">{story.length > 0 ? story.join(" ") : "Carregando os números…"}</span>}
      />
      <ErrorBanner error={report.error} onRetry={report.reload} />
      {report.loading && !report.data && <Loading lines={4} />}
      {report.data && (
        <div className="app-page-stack">
          <KpiAct
            report={report.data}
            snapshots={snapshots.data ?? []}
            analytics={analytics.data}
            onQuotesRefreshed={report.reload}
          />
          <AccountsWealth />
          <AllocationAct
            report={report.data}
            analytics={analytics.data}
            analyticsFailed={Boolean(analytics.error)}
            alerts={alerts.error ? [] : alerts.data?.alerts ?? null}
            onAlertsChange={alerts.reload}
          />
          <LatestStudy />
          <DeclaredEarnings />
        </div>
      )}
      <ErrorBanner error={alerts.error} onRetry={alerts.reload} />
    </div>
  );
}
