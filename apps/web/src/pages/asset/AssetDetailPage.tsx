import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { AssetAnalysisResponseDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { Hint } from "../../components/Hint";
import { PageHeader } from "../../components/PageHeader";
import { Lead } from "../../components/Section";
import { IconLink } from "../../components/RowActions";
import { EditIcon } from "../../layout/icons";
import { Async, Empty } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { DisclosureFeed } from "../disclosures/DisclosureFeed";
import { brl, brlCompact, day, money, num, pct, points, quantity } from "../../utils/format";
import {
  ASSET_TYPE_LABELS,
  EARNING_LABELS,
  EVENT_LABELS,
  LIFECYCLE_LABELS,
  LIFECYCLE_TONES,
  PROFILE_LABELS,
  TRADE_LABELS,
  VERDICT_LABELS,
  VERDICT_TONES,
} from "../../utils/labels";
import { ColumnChart } from "../../viz/ColumnChart";
import { ChecklistTab } from "./ChecklistTab";
import { CvmStatements } from "./CvmStatements";
import { ForecastTab } from "./ForecastTab";
import { MarketTab } from "./MarketTab";
import { PriceHistory } from "./PriceHistory";
import { TaxTab } from "./TaxTab";
import { compareLink } from "../tools/AssetComparePage";

const BENCHMARK_LABELS: Record<string, string> = {
  IBOV: "Ibovespa",
  IFIX: "IFIX",
  SP500: "S&P 500",
  CDI: "CDI",
  IPCA: "IPCA",
};

type TabKey =
  | "summary"
  | "market"
  | "fundamentals"
  | "valuation"
  | "forecast"
  | "checklist"
  | "tax"
  | "earnings"
  | "ledger"
  | "disclosures";
const TABS: TabSpec<TabKey>[] = [
  { key: "summary", label: "Resumo" },
  { key: "fundamentals", label: "Fundamentos" },
  { key: "valuation", label: "Valuation" },
  { key: "forecast", label: "Probabilidades" },
  { key: "checklist", label: "Checklist" },
  { key: "tax", label: "Tributação" },
  { key: "earnings", label: "Proventos" },
  { key: "ledger", label: "Lançamentos" },
  { key: "disclosures", label: "Comunicados" },
];
/** Treasury bonds also show the curve versus the redemption price (Phase 26). */
const TREASURY_TABS: TabSpec<TabKey>[] = [TABS[0], { key: "market", label: "Mercado" }, ...TABS.slice(1)];

/**
 * The price of an asset without a position: the report's or the valuation's price when there is
 * one, else the last stored close (dated, since it may be a few days old).
 */
function currentQuote(analysis: AssetAnalysisResponseDTO): { price: number; date?: string } | null {
  const known = analysis.position?.current_unit_price || analysis.valuation.price;
  if (known) return { price: known };
  const prices = analysis.price_history as Array<{ date?: string; close?: number }>;
  const last = [...prices].reverse().find((point) => typeof point.close === "number" && point.close > 0);
  return last?.close ? { price: last.close, date: last.date } : null;
}

function Summary({ analysis }: Readonly<{ analysis: AssetAnalysisResponseDTO }>) {
  const p = analysis.position;
  const prices = analysis.price_history as Array<{ date?: string; close?: number }>;
  const risk = analysis.risk_return;
  const held = Boolean(p && (p.quantity > 0 || p.invested_value_brl > 0));
  const quote = held ? null : currentQuote(analysis);
  return (
    <div className="app-page-stack">
      {held && p && (
        <Lead tone={p.consolidated_pnl_brl > 0 ? "positive" : p.consolidated_pnl_brl < 0 ? "negative" : "neutral"}>
          <p>
            A posição vale <strong>{brl(p.current_value_brl)}</strong>, com resultado de{" "}
            <Signed value={p.consolidated_pnl_brl}>
              {brl(p.consolidated_pnl_brl)} ({points(p.consolidated_return_pct, 1, true)})
            </Signed>{" "}
            sobre {brl(p.invested_value_brl)} investidos
            {p.received_earnings_brl > 0 ? `; recebeu ${brl(p.received_earnings_brl)} em proventos` : ""}.
          </p>
          <p>
            Pesa {points(p.class_current_weight_pct)} da classe, para uma meta de {points(p.class_target_weight_pct)}.
          </p>
        </Lead>
      )}
      <div className="app-split">
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Posição</h2>
          {held && p ? (
            <dl className="app-definition-list">
              <dt>Quantidade</dt>
              <dd>{quantity(p.quantity)}</dd>
              <dt>Preço médio</dt>
              <dd>{money(p.average_price, p.currency)}</dd>
              <dt>Preço atual</dt>
              <dd>{money(p.current_unit_price, p.currency)}</dd>
              <dt>Valor atual</dt>
              <dd>{brl(p.current_value_brl)}</dd>
              <dt>Investido</dt>
              <dd>{brl(p.invested_value_brl)}</dd>
              <dt>Resultado consolidado</dt>
              <dd>
                <Signed value={p.consolidated_pnl_brl}>
                  {brl(p.consolidated_pnl_brl)} ({points(p.consolidated_return_pct, 1, true)})
                </Signed>
              </dd>
              <dt>Proventos recebidos</dt>
              <dd>{brl(p.received_earnings_brl)}</dd>
              <dt>Peso na classe</dt>
              <dd>
                {points(p.class_current_weight_pct)} (alvo {points(p.class_target_weight_pct)})
              </dd>
            </dl>
          ) : (
            <>
              {quote && (
                <dl className="app-definition-list">
                  <dt>Preço atual</dt>
                  <dd>
                    {money(quote.price, p?.currency || analysis.asset.currency || "BRL")}
                    {quote.date && <span className="app-muted"> · fechamento de {day(quote.date)}</span>}
                  </dd>
                </dl>
              )}
              <p className="app-muted" style={quote ? { marginTop: "var(--space-3)" } : undefined}>
                Sem posição: o ativo está em observação.
              </p>
            </>
          )}
        </section>
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Risco em 12 meses</h2>
          {risk.observations < 2 ? (
            <p className="app-muted">Sem histórico de preços suficiente.</p>
          ) : (
            <dl className="app-definition-list">
              <dt>Retorno do preço</dt>
              <dd>{pct(risk.cumulative_return, 1, true)}</dd>
              <dt>Volatilidade anual</dt>
              <dd>{pct(risk.annualized_volatility, 1)}</dd>
              <dt>Queda máxima</dt>
              <dd>{pct(risk.max_drawdown, 1)}</dd>
              {risk.benchmarks.map((b) => (
                <div key={b.benchmark} style={{ display: "contents" }}>
                  <dt>{BENCHMARK_LABELS[b.benchmark] ?? b.benchmark} no período</dt>
                  <dd>
                    {pct(b.benchmark_return, 1, true)}
                    {b.beta !== null && b.beta !== undefined && <span className="app-muted"> · beta {num(b.beta, 2)}</span>}
                  </dd>
                </div>
              ))}
              {!risk.benchmarks.some((b) => b.benchmark === analysis.benchmark) && (
                <>
                  <dt>{BENCHMARK_LABELS[analysis.benchmark] ?? analysis.benchmark}</dt>
                  <dd className="app-muted">Sem série no período</dd>
                </>
              )}
            </dl>
          )}
        </section>
      </div>
      {prices.length >= 2 && (
        <PriceHistory
          assetId={analysis.asset.id}
          ticker={analysis.asset.ticker}
          currency={analysis.asset.currency || "BRL"}
          fallback={prices}
        />
      )}
    </div>
  );
}

const INDICATORS: Array<[string, string, (v: number) => string, string]> = [
  [
    "price_to_earnings",
    "P/L",
    (v) => num(v, 2),
    "Preço dividido pelo lucro por ação: quantos anos do lucro atual pagariam o preço da ação. Quanto menor, mais barata a ação em relação ao que lucra.",
  ],
  [
    "price_to_book",
    "P/VP",
    (v) => num(v, 2),
    "Preço dividido pelo valor patrimonial por ação. Abaixo de 1, a bolsa paga menos que o patrimônio contábil da empresa.",
  ],
  [
    "dividend_yield",
    "Dividend yield",
    (v) => pct(v),
    "Proventos pagos por ação nos últimos 12 meses divididos pelo preço atual: o retorno em dinheiro de quem comprasse hoje.",
  ],
  [
    "return_on_equity",
    "ROE",
    (v) => pct(v),
    "Retorno sobre o patrimônio: lucro líquido dividido pelo patrimônio líquido. Mostra quanto a empresa lucra com o capital dos sócios.",
  ],
  [
    "profit_margin",
    "Margem líquida",
    (v) => pct(v),
    "Lucro líquido dividido pela receita: quanto de cada real vendido sobra como lucro.",
  ],
  [
    "net_debt_to_ebitda",
    "Dív. líq./EBITDA",
    (v) => num(v, 2),
    "Dívida líquida (dívida menos caixa) dividida pelo EBITDA: quantos anos da geração de caixa operacional quitariam a dívida. Negativo indica mais caixa que dívida.",
  ],
  [
    "earnings_per_share",
    "LPA",
    (v) => num(v, 2),
    "Lucro por ação: lucro líquido dos últimos 12 meses dividido pelo número de ações.",
  ],
  [
    "book_value_per_share",
    "VPA",
    (v) => num(v, 2),
    "Valor patrimonial por ação: patrimônio líquido dividido pelo número de ações.",
  ],
  [
    "market_cap",
    "Valor de mercado",
    (v) => brlCompact(v),
    "Preço da ação multiplicado pelo total de ações: quanto a bolsa avalia a empresa inteira hoje.",
  ],
  [
    "avg_daily_volume",
    "Volume financeiro médio",
    (v) => brlCompact(v),
    "Valor médio negociado por pregão nos dias recentes. Quanto maior, mais fácil comprar e vender sem mexer no preço (liquidez).",
  ],
];

const HISTORY_HINTS = {
  period: "Exercícios anuais armazenados usados nos cálculos abaixo (até os últimos 5 anos).",
  roe: "Média do ROE (lucro líquido ÷ patrimônio líquido) de cada ano do período.",
  revenueCagr: "Crescimento anual composto da receita entre o primeiro e o último ano do período.",
  earningsCagr:
    "Crescimento anual composto do lucro líquido entre o primeiro e o último ano. Fica em branco quando um dos dois anos teve prejuízo.",
  profitableYears: "Em quantos anos do período a empresa teve lucro líquido positivo.",
  dividendYears: "Em quantos anos do período a empresa pagou dividendos ou JCP.",
  payout: "Média, ano a ano, da parcela do lucro líquido distribuída como proventos.",
};

/** A definition-list term with its help marker beside it. */
function Term({ label, hint }: Readonly<{ label: string; hint: string }>) {
  return (
    <dt>
      {label}
      <Hint about={label}>{hint}</Hint>
    </dt>
  );
}

const STATEMENT_COLUMNS: Array<[string, string]> = [
  ["revenue", "Receita"],
  ["net_income", "Lucro líquido"],
  ["ebitda", "EBITDA"],
  ["equity", "Patrimônio"],
  ["total_debt", "Dívida"],
  ["cash", "Caixa"],
  ["dividends_paid", "Proventos pagos"],
];

function Fundamentals({ analysis }: Readonly<{ analysis: AssetAnalysisResponseDTO }>) {
  const f = (analysis.fundamentals ?? {}) as Record<string, unknown>;
  const m = analysis.historical_metrics;
  const history = analysis.fundamental_history ?? [];
  return (
    <div className="app-page-stack">
      <div className="app-split">
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Indicadores atuais</h2>
          {analysis.fundamentals ? (
            <dl className="app-definition-list">
              {INDICATORS.map(([key, label, format, hint]) => (
                <div key={key} style={{ display: "contents" }}>
                  <Term label={label} hint={hint} />
                  <dd>{typeof f[key] === "number" ? format(f[key] as number) : "—"}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="app-muted">O provedor não retornou indicadores para este ativo.</p>
          )}
        </section>
        <section className="app-card app-card-padded">
          <h2 className="app-card-heading">Histórico</h2>
          {m && m.years > 0 ? (
            <dl className="app-definition-list">
              <Term label="Período" hint={HISTORY_HINTS.period} />
              <dd>
                {m.years} anos ({m.first_year}–{m.last_year})
              </dd>
              <Term label="ROE médio" hint={HISTORY_HINTS.roe} />
              <dd>{pct(m.roe_average)}</dd>
              <Term label="CAGR da receita" hint={HISTORY_HINTS.revenueCagr} />
              <dd>{pct(m.revenue_cagr, 1, true)}</dd>
              <Term label="CAGR do lucro" hint={HISTORY_HINTS.earningsCagr} />
              <dd>{pct(m.earnings_cagr, 1, true)}</dd>
              <Term label="Anos com lucro" hint={HISTORY_HINTS.profitableYears} />
              <dd>
                {m.profitable_years} de {m.years}
              </dd>
              <Term label="Anos com proventos" hint={HISTORY_HINTS.dividendYears} />
              <dd>
                {m.dividend_years} de {m.years}
              </dd>
              <Term label="Payout médio" hint={HISTORY_HINTS.payout} />
              <dd>{pct(m.payout_average)}</dd>
            </dl>
          ) : (
            <p className="app-muted">
              Sem demonstrativos anuais armazenados. O worker os busca semanalmente para ações.
            </p>
          )}
        </section>
      </div>
      {history.length > 0 && (
        <>
          <section className="app-card app-card-padded">
            <h2 className="app-card-heading">Lucro líquido por ano</h2>
            <ColumnChart
              title={`Lucro líquido anual de ${analysis.asset.ticker}`}
              columns={history.map((s) => ({
                label: s.reference_date.slice(0, 4),
                value: Number(s.metrics.net_income ?? 0),
              }))}
              hint="Passe o mouse para ler o ano."
              format={brlCompact}
            />
          </section>
          <div className="app-table-wrap">
            <table className="app-table">
              <thead>
                <tr>
                  <th>Ano</th>
                  {STATEMENT_COLUMNS.map(([key, label]) => (
                    <th key={key} className="app-numeric">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().map((s) => (
                  <tr key={s.reference_date}>
                    <td>{s.reference_date.slice(0, 4)}</td>
                    {STATEMENT_COLUMNS.map(([key]) => (
                      <td key={key} className="app-numeric">
                        {s.metrics[key] === null || s.metrics[key] === undefined ? "—" : brlCompact(s.metrics[key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {analysis.asset.asset_type === "STOCK_BR" && <CvmStatements assetId={analysis.asset.id} />}
    </div>
  );
}

/** Reasons the provider data was flagged (field -> pt-BR text). */
function suspiciousReasons(analysis: AssetAnalysisResponseDTO): Record<string, string> {
  const raw = (analysis.fundamentals ?? {}) as { suspicious?: Record<string, string> };
  return raw.suspicious ?? {};
}

function Valuation({ analysis }: Readonly<{ analysis: AssetAnalysisResponseDTO }>) {
  const v = analysis.valuation;
  if (!v.applicable) {
    return <Empty title="Valuation não se aplica" hint={v.reason} />;
  }
  const currency = analysis.asset.currency;
  return (
    <div className="app-page-stack">
      <section className="app-card app-card-padded">
        <div className="app-button-row">
          <Badge tone={VERDICT_TONES[v.verdict]}>{VERDICT_LABELS[v.verdict] ?? v.verdict}</Badge>
          <span>
            Preço {money(v.price, currency)} · valor estimado {money(v.fair_value, currency)}
            {v.margin !== null && v.margin !== undefined && <> · margem {pct(v.margin, 1, true)}</>}
          </span>
        </div>
        <p className="app-card-hint">
          Perfil {PROFILE_LABELS[v.profile]}. Os preços justos se combinam pela mediana; múltiplos passam ou não nos
          limites da estratégia.
        </p>
        {(v.suspicious_inputs ?? []).length > 0 && (
          <p className="app-info-banner" role="note">
            <Badge tone="warning">Dado suspeito</Badge>{" "}
            {(v.suspicious_inputs ?? [])
              .map((field) => suspiciousReasons(analysis)[field] ?? field)
              .join(" ")}{" "}
            Confira antes de usar o veredito; o alerta de preço abaixo do teto fica suspenso.
          </p>
        )}
        {v.extraordinary_dividends && (
          <p className="app-muted">
            Os proventos dos últimos 12 meses estão bem acima da mediana dos últimos anos; o Bazin usa a mediana.
          </p>
        )}
      </section>
      <div className="app-table-wrap">
        <table className="app-table">
          <thead>
            <tr>
              <th>Método</th>
              <th className="app-numeric">Valor</th>
              <th className="app-numeric">Limite</th>
              <th className="app-numeric">Margem</th>
              <th>Resultado</th>
              <th>Observação</th>
            </tr>
          </thead>
          <tbody>
            {v.methods.map((method) => {
              const asYield = method.kind === "YIELD";
              const format = (x: number | null | undefined) =>
                x === null || x === undefined ? "—" : method.kind === "PRICE" ? money(x, currency) : asYield ? pct(x) : num(x, 2);
              return (
                <tr key={method.method}>
                  <td>{method.label}</td>
                  <td className="app-numeric">{format(method.value)}</td>
                  <td className="app-numeric">{method.kind === "PRICE" ? "—" : format(method.threshold)}</td>
                  <td className="app-numeric">{method.margin === null || method.margin === undefined ? "—" : pct(method.margin, 1, true)}</td>
                  <td>
                    {method.passes === null || method.passes === undefined ? (
                      <span className="app-muted">—</span>
                    ) : (
                      <Badge tone={method.passes ? "success" : "danger"}>{method.passes ? "Passa" : "Não passa"}</Badge>
                    )}
                  </td>
                  <td className="app-cell-wrap app-muted">{method.note}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Earnings({ assetId }: Readonly<{ assetId: number }>) {
  const earnings = useApi(`asset-earnings-${assetId}`, () => api.ledger.earnings({ asset_id: assetId, page_size: 200 }));
  return (
    <Async state={earnings}>
      {(page) => {
        if (page.items.length === 0) return <Empty title="Nenhum provento registrado" />;
        const byYear = new Map<string, number>();
        page.items.forEach((e) => {
          const year = e.payment_date.slice(0, 4);
          byYear.set(year, (byYear.get(year) ?? 0) + (e.net_amount_brl ?? e.net_amount));
        });
        const years = [...byYear.entries()].sort(([a], [b]) => a.localeCompare(b));
        return (
          <div className="app-page-stack">
            <section className="app-card app-card-padded">
              <h2 className="app-card-heading">Proventos por ano</h2>
              <ColumnChart
                title="Proventos líquidos recebidos por ano"
                columns={years.map(([label, value]) => ({ label, value }))}
                hint="Passe o mouse para ler o ano."
                format={brlCompact}
              />
            </section>
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Pagamento</th>
                    <th>Tipo</th>
                    <th className="app-numeric">Bruto</th>
                    <th className="app-numeric">Líquido (R$)</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((e) => (
                    <tr key={e.id}>
                      <td>{day(e.payment_date)}</td>
                      <td>{EARNING_LABELS[e.kind]}</td>
                      <td className="app-numeric">{num(e.gross_amount)}</td>
                      <td className="app-numeric">{brl(e.net_amount_brl ?? e.net_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      }}
    </Async>
  );
}

function Ledger({ assetId }: Readonly<{ assetId: number }>) {
  const trades = useApi(`asset-trades-${assetId}`, () => api.ledger.trades({ asset_id: assetId, page_size: 200 }));
  const events = useApi(`asset-events-${assetId}`, () => api.ledger.events(assetId));
  return (
    <div className="app-page-stack">
      <Async state={trades}>
        {(page) =>
          page.items.length === 0 ? (
            <Empty title="Nenhuma compra ou venda" />
          ) : (
            <div className="app-table-wrap">
              <table className="app-table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Operação</th>
                    <th className="app-numeric">Quantidade</th>
                    <th className="app-numeric">Preço</th>
                    <th className="app-numeric">Total (R$)</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((t) => (
                    <tr key={t.id}>
                      <td>{day(t.trade_date)}</td>
                      <td>{TRADE_LABELS[t.kind]}</td>
                      <td className="app-numeric">{quantity(t.quantity)}</td>
                      <td className="app-numeric">{num(t.unit_price)}</td>
                      <td className="app-numeric">{brl(t.total_brl)}</td>
                      <td className="app-row-actions">
                        <IconLink to={`/ledger/trades/${t.id}/edit`} label="Editar" icon={<EditIcon />} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Async>
      <Async state={events}>
        {(list) =>
          list.length === 0 ? null : (
            <section>
              <h2 className="app-card-heading">Eventos corporativos</h2>
              <div className="app-table-wrap">
                <table className="app-table">
                  <thead>
                    <tr>
                      <th>Data ex</th>
                      <th>Evento</th>
                      <th className="app-numeric">Fator</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((e) => (
                      <tr key={e.id}>
                        <td>{day(e.ex_date)}</td>
                        <td>{EVENT_LABELS[e.kind]}</td>
                        <td className="app-numeric">{num(e.factor, 6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )
        }
      </Async>
    </div>
  );
}

export function AssetDetailPage() {
  const { id } = useParams();
  const assetId = Number(id);
  const [tab, setTab] = useTab(TREASURY_TABS, "summary");
  const [checklistSaved, setChecklistSaved] = useState(false);
  const analysis = useApi(`asset-${assetId}`, () => api.assets.analysis(assetId));

  return (
    <div className="app-page">
      <Async state={analysis} lines={6}>
        {(data) => {
          const status = data.position?.lifecycle_status;
          return (
            <>
              <PageHeader
                title={
                  <>
                    {data.asset.ticker} <span className="app-muted">· {data.asset.name}</span>
                  </>
                }
                subtitle={
                  <span className="app-button-row">
                    <Badge>{ASSET_TYPE_LABELS[data.asset.asset_type]}</Badge>
                    {status && <Badge tone={LIFECYCLE_TONES[status]}>{LIFECYCLE_LABELS[status]}</Badge>}
                    {!data.asset.is_active && <Badge>Arquivado</Badge>}
                    <Badge tone={VERDICT_TONES[data.valuation.verdict]}>
                      {VERDICT_LABELS[data.valuation.verdict] ?? data.valuation.verdict}
                    </Badge>
                  </span>
                }
                actions={
                  <>
                    <Link className="app-secondary-button" to={compareLink(data.asset.ticker)}>
                      Comparar
                    </Link>
                    <Link className="app-secondary-button" to={`/asset/${assetId}/edit`}>
                      Editar ativo
                    </Link>
                    <Link className="app-primary-button" to={`/ledger/trades/new?asset=${assetId}`}>
                      Registrar compra
                    </Link>
                  </>
                }
              />
              <Tabs
                tabs={data.asset.asset_type === "TREASURY" ? TREASURY_TABS : TABS}
                active={tab}
                onSelect={setTab}
                label="Seções do ativo"
              />
              {tab === "summary" && <Summary analysis={data} />}
              {tab === "fundamentals" && <Fundamentals analysis={data} />}
              {tab === "valuation" && <Valuation analysis={data} />}
              {tab === "forecast" && <ForecastTab assetId={assetId} />}
              {tab === "checklist" && (
                <>
                  {checklistSaved && (
                    <p className="app-success-banner" role="status" style={{ marginBottom: "var(--space-3)" }}>
                      Checklist salvo.
                    </p>
                  )}
                  <ChecklistTab
                    key={`${data.asset.checklist_profile}-${(data.checklist_history ?? []).length}`}
                    analysis={data}
                    onSaved={() => {
                      setChecklistSaved(true);
                      analysis.reload();
                    }}
                  />
                </>
              )}
              {tab === "market" && data.asset.asset_type === "TREASURY" && <MarketTab assetId={assetId} />}
              {tab === "tax" && <TaxTab assetId={assetId} />}
              {tab === "earnings" && <Earnings assetId={assetId} />}
              {tab === "ledger" && <Ledger assetId={assetId} />}
              {tab === "disclosures" && <DisclosureFeed assetId={assetId} title="Comunicados à CVM" />}
            </>
          );
        }}
      </Async>
    </div>
  );
}
