import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { ArcaClass, PortfolioReportResponseDTO, ValuedPositionDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section, type Tone } from "../../components/Section";
import { Async, Empty } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brl, money, plural, points, quantity } from "../../utils/format";
import {
  ARCA_CLASSES,
  ARCA_LABELS,
  FRESHNESS_LABELS,
  LIFECYCLE_LABELS,
  LIFECYCLE_TONES,
  RECOMMENDATION_LABELS,
} from "../../utils/labels";
import { BarList } from "../../viz/BarList";
import { compareLink } from "../tools/AssetComparePage";
import { TreasuryMarketPanel } from "./TreasuryMarketPanel";
import { useStoredState } from "../../utils/storedState";

type ClassTab = "ALL" | ArcaClass;
const TABS: TabSpec<ClassTab>[] = [
  { key: "ALL", label: "Todas" },
  ...ARCA_CLASSES.map((c) => ({ key: c as ClassTab, label: ARCA_LABELS[c] })),
];

function isPosition(p: ValuedPositionDTO): boolean {
  return p.quantity > 0 || p.invested_value_brl > 0 || p.ledger_status === "INVALID";
}

/** The portfolio in words: size, result and the class furthest from its target. */
export function portfolioStory(report: PortfolioReportResponseDTO, onlyClass: ClassTab): { tone: Tone; text: string } {
  const held = report.positions.filter(isPosition);
  if (onlyClass !== "ALL") {
    const a = report.allocations.find((x) => x.arca_class === onlyClass);
    const count = held.filter((p) => p.arca_class === onlyClass).length;
    if (!a) return { tone: "neutral", text: `Nenhuma posição em ${ARCA_LABELS[onlyClass]}.` };
    const band =
      a.band_status === "BELOW" ? " Está abaixo da banda: recebe os próximos aportes." : a.band_status === "ABOVE" ? " Está acima da banda: fica fora dos próximos aportes." : " Está dentro da banda.";
    return {
      tone: a.band_status === "WITHIN" || !a.band_status ? "neutral" : "caution",
      text: `${a.label} soma ${brl(a.current_value)} em ${plural(count, "ativo", "ativos")}, ${points(a.current_pct)} da carteira para uma meta de ${points(a.target_pct, 0)}.${band}`,
    };
  }
  const off = report.allocations
    .filter((a) => a.band_status === "BELOW" || a.band_status === "ABOVE")
    .sort((x, y) => Math.abs(y.deviation_pct) - Math.abs(x.deviation_pct));
  const result = report.total_consolidated_pnl_brl;
  let text = `A carteira vale ${brl(report.total_current_value_brl)} em ${plural(held.length, "posição", "posições")}, com resultado consolidado de ${brl(result)} (${points(report.total_consolidated_return_pct, 1, true)}).`;
  if (off.length > 0) {
    const worst = off[0];
    text += ` ${worst.label} está ${worst.band_status === "BELOW" ? "abaixo" : "acima"} da banda: ${points(worst.current_pct)} contra a meta de ${points(worst.target_pct, 0)}.`;
  } else {
    text += " Todas as classes estão dentro da banda.";
  }
  return { tone: off.length > 0 ? "caution" : result >= 0 ? "positive" : "negative", text };
}

function PortfolioSummary({ report, onlyClass }: Readonly<{ report: PortfolioReportResponseDTO; onlyClass: ClassTab }>) {
  const story = portfolioStory(report, onlyClass);
  return (
    <>
      <Lead tone={story.tone}>
        <p>{story.text}</p>
      </Lead>
      {onlyClass === "ALL" && (
        <KpiGrid
          label="Indicadores da carteira"
          items={[
            { label: "Valor atual", value: brl(report.total_current_value_brl), note: `Investido ${brl(report.total_invested_brl)}` },
            {
              label: "Resultado consolidado",
              value: brl(report.total_consolidated_pnl_brl),
              tone: report.total_consolidated_pnl_brl >= 0 ? "positive" : "negative",
              note: points(report.total_consolidated_return_pct, 1, true),
            },
            { label: "Proventos em 12 meses", value: brl(report.total_earnings_12m_brl) },
            { label: "IR estimado", value: brl(report.total_estimated_tax_brl), note: "Se vendesse tudo hoje" },
          ]}
        />
      )}
    </>
  );
}

const PORTFOLIO_NOTES = [
  "O resultado consolidado soma a variação do preço, as vendas realizadas e os proventos recebidos.",
  "Peso atual / alvo é o peso do ativo dentro da própria classe; a meta da classe fica na linha do grupo.",
  "Preços com selo vieram do cache ou de uma fonte alternativa, e não da cotação do dia.",
];

function checklistCell(p: ValuedPositionDTO) {
  const evaluation = p.cerrado_evaluation;
  if (!evaluation.use_cerrado) return <span className="app-muted">Desligado</span>;
  if (evaluation.answered === 0) return <span className="app-muted">Sem respostas</span>;
  return (
    <span title={`${evaluation.answered} de ${evaluation.applicable} respondidas`}>
      {evaluation.score > 0 ? "+" : ""}
      {evaluation.score} · {RECOMMENDATION_LABELS[evaluation.recommendation] ?? evaluation.recommendation}
    </span>
  );
}

function PositionRow({ p }: Readonly<{ p: ValuedPositionDTO }>) {
  const invalid = p.ledger_status === "INVALID";
  return (
    <tr>
      <td>
        <span className="app-cell-main">
          <Link className="app-link" to={`/asset/${p.asset_id}`}>
            {p.ticker}
          </Link>
          <small>
            {p.name} ·{" "}
            <Link className="app-link" to={compareLink(p.ticker)}>
              Comparar
            </Link>
          </small>
        </span>
      </td>
      <td className="app-numeric">{invalid ? "—" : quantity(p.quantity)}</td>
      <td className="app-numeric">{invalid ? "—" : money(p.average_price, p.currency)}</td>
      <td className="app-numeric">
        {money(p.current_unit_price, p.currency)}{" "}
        {!["LIVE", "CACHED"].includes(p.price_freshness) && (
          <Badge tone={p.price_freshness === "FALLBACK" ? "warning" : "neutral"}>
            {FRESHNESS_LABELS[p.price_freshness]}
          </Badge>
        )}
      </td>
      <td className="app-numeric">{brl(p.current_value_brl)}</td>
      <td className="app-numeric">
        <Signed value={p.consolidated_pnl_brl}>{points(p.consolidated_return_pct, 1, true)}</Signed>
      </td>
      <td className="app-numeric">
        {points(p.class_current_weight_pct, 1)} <span className="app-muted">/ {points(p.class_target_weight_pct, 1)}</span>
      </td>
      <td>
        {invalid ? (
          <Badge tone="danger">Livro inválido</Badge>
        ) : p.lifecycle_status ? (
          <Badge tone={LIFECYCLE_TONES[p.lifecycle_status]}>{LIFECYCLE_LABELS[p.lifecycle_status]}</Badge>
        ) : null}
      </td>
      <td>{checklistCell(p)}</td>
    </tr>
  );
}

function PositionsTable({ report, onlyClass }: Readonly<{ report: PortfolioReportResponseDTO; onlyClass: ClassTab }>) {
  const groups = report.allocations
    .filter((a) => onlyClass === "ALL" || a.arca_class === onlyClass)
    .map((a) => ({ allocation: a, positions: report.positions.filter((p) => p.arca_class === a.arca_class && isPosition(p)) }));
  return (
    <div className="app-table-wrap">
      <table className="app-table">
        <thead>
          <tr>
            <th>Ativo</th>
            <th className="app-numeric">Quantidade</th>
            <th className="app-numeric">Preço médio</th>
            <th className="app-numeric">Preço atual</th>
            <th className="app-numeric">Valor</th>
            <th className="app-numeric">Resultado</th>
            <th className="app-numeric">Peso atual / alvo</th>
            <th>Situação</th>
            <th>Checklist</th>
          </tr>
        </thead>
        <tbody>
          {groups.map(({ allocation, positions }) => [
            <tr key={`${allocation.arca_class}-head`} className="app-table-group">
              <td colSpan={9}>
                {allocation.label} · {brl(allocation.current_value)} · {points(allocation.current_pct)} da carteira (meta{" "}
                {points(allocation.target_pct, 0)})
              </td>
            </tr>,
            ...(positions.length === 0
              ? [
                  <tr key={`${allocation.arca_class}-empty`}>
                    <td colSpan={9} className="app-muted">
                      Nenhuma posição nesta classe.
                    </td>
                  </tr>,
                ]
              : positions.map((p) => <PositionRow key={p.asset_id} p={p} />)),
          ])}
        </tbody>
      </table>
    </div>
  );
}

function Composition({ report, arcaClass }: Readonly<{ report: PortfolioReportResponseDTO; arcaClass: ArcaClass }>) {
  const positions = report.positions.filter((p) => p.arca_class === arcaClass && isPosition(p));
  if (positions.length === 0) return null;
  const scale = Math.max(...positions.map((p) => Math.max(p.class_current_weight_pct, p.class_target_weight_pct)), 1) * 1.1;
  return (
    <Section
      title={`Composição de ${ARCA_LABELS[arcaClass]}`}
      subtitle="Peso de cada ativo dentro da classe; o traço é o peso alvo pela estratégia da classe."
    >
      <BarList
        label={`Peso dos ativos em ${ARCA_LABELS[arcaClass]}`}
        bars={positions.map((p) => ({
          id: String(p.asset_id),
          label: p.ticker,
          share: p.class_current_weight_pct / scale,
          goal: p.class_target_weight_pct / scale,
          value: `${points(p.class_current_weight_pct)} · alvo ${points(p.class_target_weight_pct)}`,
        }))}
      />
    </Section>
  );
}

export function PortfolioPage() {
  const [tab, setTab] = useTab(TABS, "ALL");
  const [storedAccount, setAccountId] = useStoredState<number | null>("portfolio:account", null);
  const accountId = storedAccount ?? undefined;
  const accounts = useApi("accounts", () => api.accounts.list());
  const report = useApi(`portfolio-${accountId ?? "all"}`, () => api.portfolio.report(accountId));

  return (
    <div className="app-page">
      <PageHeader
        title="Carteira"
        subtitle="Posições por classe ARCA, com o peso de cada ativo e a situação na política."
        actions={
          <>
            <label className="app-check" htmlFor="portfolio-account">
              <span className="app-muted">Conta</span>
              <select
                id="portfolio-account"
                value={accountId ?? ""}
                onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Todas</option>
                {(accounts.data ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <Link className="app-primary-button" to="/asset/new">
              Novo ativo
            </Link>
          </>
        }
      />
      <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Classes ARCA" />
      <Async state={report} lines={6}>
        {(data) =>
          data.positions.some(isPosition) ? (
            <div className="app-page-stack">
              <PortfolioSummary report={data} onlyClass={tab} />
              {tab !== "ALL" && <Composition report={data} arcaClass={tab} />}
              <PositionsTable report={data} onlyClass={tab} />
              {(tab === "ALL" || tab === "CAIXA") && <TreasuryMarketPanel />}
              <Notes items={PORTFOLIO_NOTES} />
            </div>
          ) : (
            <Empty title="Nenhuma posição ainda" hint="Registre compras em Lançamentos ou importe o extrato da B3.">
              <Link className="app-primary-button" to="/ledger/import">
                Importar extrato
              </Link>
              <Link className="app-secondary-button" to="/asset/new">
                Cadastrar ativo
              </Link>
            </Empty>
          )
        }
      </Async>
    </div>
  );
}
