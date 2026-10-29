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
import { brl, brlCompact, daysAgo, pct, points } from "../../utils/format";
import { SEVERITY_TONES } from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { Sparkline } from "../../viz/Sparkline";
import { TrendChart } from "../../viz/TrendChart";
import { alignCurves, curveReturn, headline, lastMonths, patrimonyChange, type Change } from "./story";
import { DisclosureFeed } from "../disclosures/DisclosureFeed";
import { DeclaredEarnings } from "./DeclaredEarnings";

function Indicator({
  label,
  value,
  note,
  trend,
}: Readonly<{ label: string; value: string; note?: ReactNode; trend?: ReactNode }>) {
  return (
    <div className="home-kpi">
      <span className="home-kpi-label">{label}</span>
      <strong className="home-kpi-value" title={value}>
        {value}
      </strong>
      {note && <span className="home-kpi-note">{note}</span>}
      {trend}
    </div>
  );
}

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
}: Readonly<{
  report: PortfolioReportResponseDTO;
  snapshots: SnapshotPointDTO[];
  analytics: PortfolioAnalyticsResponseDTO | null;
}>) {
  const change = patrimonyChange(snapshots, report.total_current_value_brl);
  const twr = analytics?.status === "OK" ? curveReturn(analytics.curves.PORTFOLIO) : null;
  const cdi = curveReturn(analytics?.curves.CDI);
  const reserve = report.value_by_purpose_brl?.EMERGENCY_RESERVE ?? 0;
  const months = lastMonths(report.earnings_by_month);

  return (
    <section className="home-act" aria-labelledby="act-figures">
      <div className="home-act-head">
        <h2 id="act-figures" className="home-act-title">
          Indicadores
        </h2>
        <span className="app-muted">Posição em {report.as_of_date.split("-").reverse().join("/")}</span>
      </div>
      <div className="home-kpis">
        <Indicator
          label="Patrimônio"
          value={brl(report.total_current_value_brl)}
          note={<Delta change={change} />}
          trend={<Sparkline values={snapshots.map((s) => s.market_value)} />}
        />
        <Indicator
          label="Resultado consolidado"
          value={brlCompact(report.total_consolidated_pnl_brl)}
          note={`${points(report.total_consolidated_return_pct, 1, true)} sobre o investido`}
          trend={<Sparkline values={snapshots.map((s) => s.consolidated_pnl)} />}
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
        />
        <Indicator
          label="Proventos 12 meses"
          value={brlCompact(report.total_earnings_12m_brl)}
          note={`Yield on cost ${points(report.portfolio_yield_on_cost_pct, 1)}`}
          trend={<Sparkline values={months.map(([, v]) => v)} />}
        />
        {reserve > 0 && <Indicator label="Reserva de emergência" value={brlCompact(reserve)} note="Fora da ARCA" />}
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
        <>
          <KpiAct report={report.data} snapshots={snapshots.data ?? []} analytics={analytics.data} />
          <AllocationAct
            report={report.data}
            analytics={analytics.data}
            analyticsFailed={Boolean(analytics.error)}
            alerts={alerts.error ? [] : alerts.data?.alerts ?? null}
            onAlertsChange={alerts.reload}
          />
          <DeclaredEarnings />
          <DisclosureFeed limit={8} />
        </>
      )}
      <ErrorBanner error={alerts.error} onRetry={alerts.reload} />
    </div>
  );
}
