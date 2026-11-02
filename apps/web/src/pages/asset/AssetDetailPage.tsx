import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { AssetAnalysisResponseDTO, IndicatorRatingDTO, InstrumentViewDTO } from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge, Signed } from "../../components/Badge";
import { Hint } from "../../components/Hint";
import { PageHeader } from "../../components/PageHeader";
import { Lead } from "../../components/Section";
import { IconLink } from "../../components/RowActions";
import { EditIcon } from "../../layout/icons";
import { Async, Empty } from "../../components/States";
import { DisclosureFeed } from "../disclosures/DisclosureFeed";
import { brl, brlCompact, day, money, num, pct, points, quantity } from "../../utils/format";
import {
  ARCA_LABELS,
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
import {
  Chapter,
  ChapterIndex,
  CHAPTER_TITLES,
  LensBars,
  lensHighlights,
  useOpenChapters,
  type ChapterKey,
} from "../../features/instrument/chapters";
import { instrumentPath, QuoteAge } from "../../features/instrument/paths";
import { Thesis, thesisLead, useAssetNotes } from "../../features/instrument/Thesis";

const BENCHMARK_LABELS: Record<string, string> = {
  IBOV: "Ibovespa",
  IFIX: "IFIX",
  SP500: "S&P 500",
  CDI: "CDI",
  IPCA: "IPCA",
};

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

function isHeld(analysis: AssetAnalysisResponseDTO): boolean {
  const p = analysis.position;
  return Boolean(p && (p.quantity > 0 || p.invested_value_brl > 0));
}

/** Chapter "Na minha carteira": the position, or the price of an asset under observation. */
function PositionSummary({ analysis }: Readonly<{ analysis: AssetAnalysisResponseDTO }>) {
  const p = analysis.position;
  const held = isHeld(analysis);
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
      <section className="app-card app-card-padded">
        <h3 className="app-card-heading">Posição</h3>
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
    </div>
  );
}

/** Chapter "Preço": the chart of a chosen period and the risk of the last 12 months. */
function PriceAndRisk({ analysis }: Readonly<{ analysis: AssetAnalysisResponseDTO }>) {
  const prices = analysis.price_history as Array<{ date?: string; close?: number }>;
  const risk = analysis.risk_return;
  return (
    <div className="app-page-stack">
      {prices.length >= 2 && (
        <PriceHistory
          assetId={analysis.asset.id}
          ticker={analysis.asset.ticker}
          currency={analysis.asset.currency || "BRL"}
          fallback={prices}
        />
      )}
      <section className="app-card app-card-padded">
        <h3 className="app-card-heading">Risco em 12 meses</h3>
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

const RATING_LABELS: Record<IndicatorRatingDTO["status"], string> = {
  GOOD: "Bom",
  CAUTION: "Atenção",
  BAD: "Ruim",
  SUSPICIOUS: "Confira o dado",
};
const RATING_TONES: Record<IndicatorRatingDTO["status"], string> = {
  GOOD: "success",
  CAUTION: "warning",
  BAD: "danger",
  SUSPICIOUS: "neutral",
};

/** The value, whether it is good by the strategy's references, and against what. */
function Rated({ value, rating }: Readonly<{ value: ReactNode; rating?: IndicatorRatingDTO }>) {
  return (
    <dd>
      <span className="app-rated">
        {value}
        {rating && <Badge tone={RATING_TONES[rating.status]}>{RATING_LABELS[rating.status]}</Badge>}
      </span>
      {rating && <span className="app-rating-reference">{rating.reference}</span>}
    </dd>
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
  const ratings = analysis.indicator_ratings ?? {};
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
                  <Rated
                    value={typeof f[key] === "number" ? format(f[key] as number) : "—"}
                    rating={typeof f[key] === "number" ? ratings[key] : undefined}
                  />
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
              <Rated value={pct(m.roe_average)} rating={ratings.roe_average} />
              <Term label="CAGR da receita" hint={HISTORY_HINTS.revenueCagr} />
              <Rated value={pct(m.revenue_cagr, 1, true)} rating={ratings.revenue_cagr} />
              <Term label="CAGR do lucro" hint={HISTORY_HINTS.earningsCagr} />
              <Rated value={pct(m.earnings_cagr, 1, true)} rating={ratings.earnings_cagr} />
              <Term label="Anos com lucro" hint={HISTORY_HINTS.profitableYears} />
              <Rated value={`${m.profitable_years} de ${m.years}`} rating={ratings.profitable_years} />
              <Term label="Anos com proventos" hint={HISTORY_HINTS.dividendYears} />
              <Rated value={`${m.dividend_years} de ${m.years}`} rating={ratings.dividend_years} />
              <Term label="Payout médio" hint={HISTORY_HINTS.payout} />
              <Rated value={pct(m.payout_average)} rating={ratings.payout_average} />
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

function forecastLead(view: InstrumentViewDTO | undefined): string | undefined {
  const forecast = view?.forecast;
  if (!forecast) return undefined;
  const year = forecast.bands?.find((b) => b.months === 12);
  if (forecast.status === "OK" && year) {
    return `Em 12 meses, a faixa provável vai de ${money(year.p5)} a ${money(year.p95)} (mediana ${money(year.p50)}); chance de subir de ${pct(year.up_probability, 0)}.`;
  }
  if (forecast.status === "LOW_CONFIDENCE") return "A previsão fica oculta até a calibração subir para “Use com cautela”.";
  if (forecast.status === "INSUFFICIENT_HISTORY") return "Ainda não há histórico de preço suficiente para a previsão.";
  return "A previsão deste ativo ainda não foi calculada.";
}

function valuationLead(analysis: AssetAnalysisResponseDTO): ReactNode {
  const v = analysis.valuation;
  if (!v.applicable) return "O valuation não se aplica a este tipo de ativo; os detalhes dizem por quê.";
  const verdict = VERDICT_LABELS[v.verdict] ?? v.verdict;
  return (
    <>
      <Badge tone={VERDICT_TONES[v.verdict]}>{verdict}</Badge>
      {v.fair_value ? ` Preço justo ${money(v.fair_value, analysis.asset.currency || "BRL")}` : ""}
      {v.margin !== null && v.margin !== undefined ? `, margem de ${pct(v.margin, 1, true)}.` : v.fair_value ? "." : ""}
    </>
  );
}

function checklistLead(analysis: AssetAnalysisResponseDTO): string {
  const c = analysis.checklist;
  if (c.answered === 0) return "O checklist do Cerrado ainda não foi respondido.";
  const pending = c.pending > 0 ? `; faltam ${c.pending} pergunta(s)` : "";
  return `Nota ${num(c.score, 0)} de ${num(c.max_score, 0)} no perfil ${PROFILE_LABELS[c.profile] ?? c.profile}${pending}.`;
}

function resultsLead(analysis: AssetAnalysisResponseDTO): string {
  const f = (analysis.fundamentals ?? {}) as Record<string, number | null | undefined>;
  const parts = [
    typeof f.price_to_earnings === "number" ? `P/L ${num(f.price_to_earnings, 1)}` : null,
    typeof f.price_to_book === "number" ? `P/VP ${num(f.price_to_book, 2)}` : null,
    typeof f.return_on_equity === "number" ? `ROE ${pct(f.return_on_equity, 1)}` : null,
    typeof f.dividend_yield === "number" ? `DY ${pct(f.dividend_yield, 1)}` : null,
  ].filter(Boolean);
  return parts.length ? `${parts.join(" · ")}.` : "Sem indicadores guardados deste ativo.";
}

/** The page of a registered asset as chapters (Phase 48.R4). `view` is the instrument read
 *  model (lenses, forecast band, quote age); `assetId` alone still works without it. */
export function AssetDetailPage({
  assetId: given,
  view,
}: Readonly<{ assetId?: number; view?: InstrumentViewDTO }> = {}) {
  const { id } = useParams();
  const assetId = given ?? Number(id);
  const [checklistSaved, setChecklistSaved] = useState(false);
  const analysis = useApi(`asset-${assetId}`, () => api.assets.analysis(assetId));
  const chapters = useOpenChapters(["preco"]);
  const notes = useAssetNotes(assetId);

  return (
    <div className="app-page">
      <Async state={analysis} lines={6}>
        {(data) => {
          const status = data.position?.lifecycle_status;
          const held = isHeld(data);
          const ticker = data.asset.ticker;
          const treasury = data.asset.asset_type === "TREASURY";
          const highlights = lensHighlights(view?.lenses);
          const holdingTitle = held ? CHAPTER_TITLES.carteira : "Em observação";
          const index: Array<{ key: ChapterKey; title?: string }> = [
            { key: "resumo" },
            { key: "carteira", title: holdingTitle },
            { key: "preco" },
            { key: "checklist" },
            { key: "valuation" },
            { key: "resultados" },
            { key: "proventos" },
            { key: "previsao" },
            { key: "noticias" },
            { key: "tese" },
            { key: "imposto" },
          ];
          const risk = data.risk_return;
          return (
            <>
              <PageHeader
                title={
                  <>
                    {ticker} <span className="app-muted">· {data.asset.name}</span>
                  </>
                }
                subtitle={
                  <span className="app-button-row">
                    <Badge>{ASSET_TYPE_LABELS[data.asset.asset_type]}</Badge>
                    {data.asset.arca_class && <Badge>{ARCA_LABELS[data.asset.arca_class]}</Badge>}
                    {status && <Badge tone={LIFECYCLE_TONES[status]}>{LIFECYCLE_LABELS[status]}</Badge>}
                    {!data.asset.is_active && <Badge>Arquivado</Badge>}
                    {view?.quote && <QuoteAge quote={view.quote} />}
                  </span>
                }
                actions={
                  <>
                    <Link className="app-secondary-button" to={compareLink(ticker)}>
                      Comparar
                    </Link>
                    <Link className="app-secondary-button" to={`${instrumentPath(ticker)}/editar`}>
                      Editar ativo
                    </Link>
                    <Link className="app-secondary-button" to="/aportar">
                      Aportar
                    </Link>
                    <Link className="app-primary-button" to={`/lancamentos/negociacoes/nova?asset=${assetId}`}>
                      Registrar compra
                    </Link>
                  </>
                }
              />
              <div className="app-chapters">
                <ChapterIndex chapters={index} />
                <div className="app-chapters-body">
                  <Chapter
                    id="resumo"
                    lead={
                      <>
                        <p>{highlights.strong ?? "As lentes da recomendação ainda não foram calculadas para este ativo."}</p>
                        {highlights.weak && <p>{highlights.weak}</p>}
                      </>
                    }
                  >
                    {view?.lenses && <LensBars lenses={view.lenses} />}
                  </Chapter>

                  <Chapter id="carteira" title={holdingTitle}>
                    <PositionSummary analysis={data} />
                  </Chapter>

                  <Chapter
                    id="preco"
                    lead={
                      risk.observations >= 2
                        ? `Em 12 meses, ${pct(risk.cumulative_return, 1, true)} com volatilidade de ${pct(risk.annualized_volatility, 1)} ao ano.`
                        : "Sem histórico de preços suficiente para medir o risco."
                    }
                    open={chapters.isOpen("preco")}
                    onToggle={() => chapters.toggle("preco")}
                  >
                    <PriceAndRisk analysis={data} />
                    {treasury && <MarketTab assetId={assetId} />}
                  </Chapter>

                  <Chapter
                    id="checklist"
                    lead={checklistLead(data)}
                    open={chapters.isOpen("checklist")}
                    onToggle={() => chapters.toggle("checklist")}
                  >
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
                  </Chapter>

                  <Chapter
                    id="valuation"
                    lead={valuationLead(data)}
                    open={chapters.isOpen("valuation")}
                    onToggle={() => chapters.toggle("valuation")}
                  >
                    <Valuation analysis={data} />
                  </Chapter>

                  <Chapter
                    id="resultados"
                    lead={resultsLead(data)}
                    open={chapters.isOpen("resultados")}
                    onToggle={() => chapters.toggle("resultados")}
                  >
                    <Fundamentals analysis={data} />
                  </Chapter>

                  <Chapter
                    id="proventos"
                    lead={
                      held && data.position && data.position.received_earnings_brl > 0
                        ? `Você já recebeu ${brl(data.position.received_earnings_brl)} em proventos deste ativo.`
                        : "Histórico de proventos por ano e os próximos anunciados."
                    }
                    open={chapters.isOpen("proventos")}
                    onToggle={() => chapters.toggle("proventos")}
                  >
                    <Earnings assetId={assetId} />
                  </Chapter>

                  <Chapter
                    id="previsao"
                    lead={forecastLead(view) ?? "Faixa provável do preço em 3, 6, 12 e 24 meses."}
                    open={chapters.isOpen("previsao")}
                    onToggle={() => chapters.toggle("previsao")}
                  >
                    <ForecastTab assetId={assetId} />
                  </Chapter>

                  <Chapter
                    id="noticias"
                    lead="Comunicados à CVM e a reação típica de cada tipo de fato."
                    open={chapters.isOpen("noticias")}
                    onToggle={() => chapters.toggle("noticias")}
                  >
                    <DisclosureFeed assetId={assetId} title="Comunicados à CVM" />
                  </Chapter>

                  <Chapter
                    id="tese"
                    lead={thesisLead(notes.data)}
                    open={chapters.isOpen("tese")}
                    onToggle={() => chapters.toggle("tese")}
                  >
                    <Thesis assetId={assetId} />
                  </Chapter>

                  <Chapter
                    id="imposto"
                    lead={held ? "Situação tributária, compras, vendas e proventos lançados." : "Sem posição: nada a tributar."}
                    open={chapters.isOpen("imposto")}
                    onToggle={() => chapters.toggle("imposto")}
                  >
                    <TaxTab assetId={assetId} />
                    <Ledger assetId={assetId} />
                  </Chapter>
                </div>
              </div>
            </>
          );
        }}
      </Async>
    </div>
  );
}
