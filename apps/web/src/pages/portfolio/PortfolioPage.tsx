import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { ArcaClass, PortfolioReportResponseDTO, ValuedPositionDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Async, Empty } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { brl, money, points, quantity } from "../../utils/format";
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

type ClassTab = "ALL" | ArcaClass;
const TABS: TabSpec<ClassTab>[] = [
  { key: "ALL", label: "Todas" },
  ...ARCA_CLASSES.map((c) => ({ key: c as ClassTab, label: ARCA_LABELS[c] })),
];

function isPosition(p: ValuedPositionDTO): boolean {
  return p.quantity > 0 || p.invested_value_brl > 0 || p.ledger_status === "INVALID";
}

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
    <section className="app-card app-card-padded">
      <h2 className="app-card-heading">Composição de {ARCA_LABELS[arcaClass]}</h2>
      <p className="app-card-hint">Peso de cada ativo dentro da classe; o traço é o peso alvo pela estratégia da classe.</p>
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
    </section>
  );
}

export function PortfolioPage() {
  const [tab, setTab] = useTab(TABS, "ALL");
  const [accountId, setAccountId] = useState<number | undefined>(undefined);
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
                onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : undefined)}
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
              {tab !== "ALL" && <Composition report={data} arcaClass={tab} />}
              <PositionsTable report={data} onlyClass={tab} />
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
