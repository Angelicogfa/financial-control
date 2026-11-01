/** Recomendação (Phase 45.5): why these assets. For each ARCA class, the weekly run's chosen
 *  assets with their target weights and reasons, the dynamic-K curve, the AHP decision matrix,
 *  who the gates left out, "A and not B" and the contribution next to the current rule.
 *  Nothing here changes the contribution yet: the switch is Phase 45.6. */

import { useState } from "react";

import { api } from "../../api/endpoints";
import { errorMessage } from "../../api/http";
import type {
  ClassMatrixDTO,
  ContributionComparisonDTO,
  MatrixBoardDTO,
  RowComparisonDTO,
} from "../../api/types";
import { useApi } from "../../api/useApi";
import { Badge } from "../../components/Badge";
import { Combobox } from "../../components/Combobox";
import { manualJobs } from "../../api/jobs";
import { JobRunList } from "../../components/JobRunList";
import { PageHeader } from "../../components/PageHeader";
import { KpiGrid, Lead, Notes, Section, Segmented } from "../../components/Section";
import { Async, Empty, Spinner } from "../../components/States";
import { brl, day, num, parseDecimal, pct, quantity } from "../../utils/format";

export const CLASS_LABELS: Record<string, string> = {
  ACOES: "Ações",
  REAL_ESTATE: "Real Estate",
  ATIVOS_INTERNACIONAIS: "Internacional",
  CAIXA: "Caixa",
};

const SOURCE_LABELS: Record<string, string> = {
  PORTFOLIO: "carteira",
  WATCHLIST: "watchlist",
  CATALOG: "catálogo",
};

const LENS_SHORT: Record<string, string> = {
  CERRADO: "Cerrado",
  QUALITY: "Qualid.",
  VALUATION: "Valuat.",
  IMPROVEMENT: "Melhora",
  MOMENTUM: "Moment.",
  INCOME: "Renda",
  RISK: "Risco",
  PROJECTION: "Projeção",
};

const NOT_ANALYZED = "NOT_ANALYZED";

function Source({ source }: Readonly<{ source: string }>) {
  return <Badge tone={source === "CATALOG" ? "info" : "neutral"}>{SOURCE_LABELS[source] ?? source}</Badge>;
}

function leadText(m: ClassMatrixDTO): string {
  const c = m.construction;
  const chosen = (c?.selected ?? []).map((s) => s.ticker);
  const names = chosen.length > 0 ? `: ${chosen.join(", ")}` : "";
  return (
    `Em ${CLASS_LABELS[m.arca_class] ?? m.arca_class} (objetivo ${m.objective_label}), ` +
    `${(m.rows ?? []).length} ativos passaram nos portões e a recomendação escolheu ${c?.k ?? 0}${names}. ` +
    (c?.stop_reason ?? "")
  );
}

function Chosen({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  const selected = matrix.construction?.selected ?? [];
  if (selected.length === 0) return <Empty title="Nenhum ativo escolhido" hint={matrix.construction?.stop_reason} />;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Escolhidos e pesos-alvo">
        <thead>
          <tr>
            <th>Ativo</th>
            <th>Setor · grupo</th>
            <th className="app-numeric">Peso-alvo</th>
            <th className="app-numeric">Nota</th>
            <th className="app-numeric">Esperado ao ano</th>
            <th>Por que entrou</th>
          </tr>
        </thead>
        <tbody>
          {selected.map((s) => (
            <tr key={s.ticker}>
              <td>
                <strong>{s.ticker}</strong>
              </td>
              <td className="app-cell-wrap">
                {s.sector}
                {s.group !== s.ticker && <div className="app-muted">anda junto com {s.group}</div>}
              </td>
              <td className="app-numeric">{pct(s.weight, 1)}</td>
              <td className="app-numeric">{num(s.score, 2)}</td>
              <td className="app-numeric">{pct(s.expected, 1, true)}</td>
              <td className="app-cell-wrap">{s.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Curve({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  const c = matrix.construction;
  const curve = c?.curve ?? [];
  if (!c || curve.length === 0) return null;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Curva do K">
        <thead>
          <tr>
            <th className="app-numeric">K</th>
            <th>Entraria</th>
            <th className="app-numeric">Esperado ao ano</th>
            <th className="app-numeric">Risco ao ano</th>
            <th className="app-numeric">Utilidade</th>
          </tr>
        </thead>
        <tbody>
          {curve.map((p) => (
            <tr key={p.k} className={p.k > c.k ? "app-muted" : undefined}>
              <td className="app-numeric">{p.k}</td>
              <td>
                {p.added} {p.k > c.k && <Badge tone="warning">recusado</Badge>}
              </td>
              <td className="app-numeric">{pct(p.expected, 2, true)}</td>
              <td className="app-numeric">{pct(p.risk, 1)}</td>
              <td className="app-numeric">{pct(p.utility, 2, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecisionMatrix({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  const weights = matrix.weights ?? [];
  const rows = matrix.rows ?? [];
  if (rows.length === 0) return <Empty title="Nenhum ativo passou nos portões" />;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Matriz de decisão">
        <thead>
          <tr>
            <th className="app-numeric">#</th>
            <th>Ativo</th>
            <th className="app-numeric">Nota</th>
            <th className="app-numeric">Esperado ao ano</th>
            {weights.map((w) => (
              <th key={w.lens} className="app-numeric" title={w.label}>
                {LENS_SHORT[w.lens] ?? w.label}
                <div className="app-muted">{pct(w.weight, 0)}</div>
              </th>
            ))}
            <th className="app-numeric">Gaussiano</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const cells = Object.fromEntries((r.cells ?? []).map((c) => [c.lens, c]));
            return (
              <tr key={r.ticker}>
                <td className="app-numeric">{r.rank}</td>
                <td className="app-cell-wrap">
                  <strong>{r.ticker}</strong> <Source source={r.source} />
                  {(r.flags ?? []).includes(NOT_ANALYZED) && (
                    <div className="app-muted">Faça a análise do Cerrado: a nota pode subir.</div>
                  )}
                </td>
                <td className="app-numeric">{num(r.score, 2)}</td>
                <td className="app-numeric">
                  {pct(r.expected, 1, true)}
                  <div className="app-muted">
                    {pct(r.expected_low, 1, true)} a {pct(r.expected_high, 1, true)}
                  </div>
                </td>
                {weights.map((w) => (
                  <td key={w.lens} className="app-numeric">
                    {cells[w.lens] ? num(cells[w.lens].value, 2) : "—"}
                  </td>
                ))}
                <td className="app-numeric">{r.gaussian_rank}º</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Weights({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Pesos das lentes">
        <thead>
          <tr>
            <th>Lente</th>
            <th className="app-numeric">Peso (AHP)</th>
            <th className="app-numeric">Referência (AHP Gaussiano)</th>
          </tr>
        </thead>
        <tbody>
          {(matrix.weights ?? []).map((w) => (
            <tr key={w.lens}>
              <td>{w.label}</td>
              <td className="app-numeric">{pct(w.weight, 1)}</td>
              <td className="app-numeric">{pct(w.gaussian_weight, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Excluded({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  const excluded = matrix.excluded ?? [];
  if (excluded.length === 0) return <p className="app-muted">Nenhum ativo desta classe foi tirado pelos portões.</p>;
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label="Fora pelos portões">
        <thead>
          <tr>
            <th>Ativo</th>
            <th>Motivo</th>
          </tr>
        </thead>
        <tbody>
          {excluded.map((e) => (
            <tr key={e.ticker}>
              <td>
                <strong>{e.ticker}</strong> <Source source={e.source} />
              </td>
              <td className="app-cell-wrap">{(e.reasons ?? []).join(" ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AandB({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  const tickers = (matrix.rows ?? []).map((r) => r.ticker);
  const options = [{ value: "", label: "Escolha um ativo" }, ...tickers.map((t) => ({ value: t, label: t }))];
  const [a, setA] = useState(tickers[0] ?? "");
  const [b, setB] = useState(tickers[1] ?? "");
  const [result, setResult] = useState<RowComparisonDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (tickers.length < 2) return <p className="app-muted">É preciso pelo menos dois ativos aptos na classe.</p>;
  const compare = async () => {
    if (!a || !b) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.recommendation.compare(a, b));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="app-page-stack">
      <div className="app-button-row">
        <Combobox label="Ativo A" value={a} options={options} onChange={setA} />
        <Combobox label="Ativo B" value={b} options={options} onChange={setB} />
        <button type="button" className="app-secondary-button" disabled={busy || !a || !b} onClick={compare}>
          {busy && <Spinner size="sm" />}
          <span>Comparar</span>
        </button>
      </div>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      {result && result.status !== "OK" && <p role="status">{result.reason || "Sem rodada da recomendação."}</p>}
      {result && result.status === "OK" && result.a && result.b && (
        <div role="status" className="app-page-stack">
          <p>
            <strong>{result.a.ticker}</strong> tem nota {num(result.a.score, 2)} ({result.a.rank}º) e{" "}
            <strong>{result.b.ticker}</strong>, {num(result.b.score, 2)} ({result.b.rank}º). O que mais pesou:
          </p>
          <div className="app-table-wrap">
            <table className="app-table" aria-label="A e não B">
              <thead>
                <tr>
                  <th>Lente</th>
                  <th className="app-numeric">{result.a.ticker}</th>
                  <th className="app-numeric">{result.b.ticker}</th>
                  <th className="app-numeric">Peso</th>
                  <th className="app-numeric">Diferença na nota</th>
                </tr>
              </thead>
              <tbody>
                {(result.differences ?? []).map((d) => (
                  <tr key={d.lens}>
                    <td>{d.label}</td>
                    <td className="app-numeric">{num(d.a, 2)}</td>
                    <td className="app-numeric">{num(d.b, 2)}</td>
                    <td className="app-numeric">{pct(d.weight, 0)}</td>
                    <td className="app-numeric">{num(d.difference, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function SideBySide({ arcaClass }: Readonly<{ arcaClass: string }>) {
  const [amount, setAmount] = useState("1000");
  const [result, setResult] = useState<ContributionComparisonDTO | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = parseDecimal(amount);
    if (!value || value <= 0) {
      setError("Informe um valor maior que zero.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await api.recommendation.contribution(value));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const line = result?.classes?.find((c) => c.arca_class === arcaClass);
  return (
    <div className="app-page-stack">
      <form className="app-button-row" onSubmit={run}>
        <div className="app-field">
          <label htmlFor="recommendation-amount">Valor do aporte (R$)</label>
          <input
            id="recommendation-amount"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <button type="submit" className="app-secondary-button" disabled={busy}>
          {busy && <Spinner size="sm" />}
          <span>Comparar com a regra antiga</span>
        </button>
      </form>
      {error && (
        <p className="app-error-banner" role="alert">
          {error}
        </p>
      )}
      {result && !line && <p role="status">Sem rodada da recomendação para comparar.</p>}
      {line && (
        <div role="status" className="app-page-stack">
          <p>
            Pela regra ARCA, a fatia desta classe é {brl(line.budget)} nas duas formas; o que outras classes sem
            ativo passam adiante entra nas compras.{" "}
            {line.covered
              ? "O aporte segue os pesos-alvo da recomendação, puxados para os seus pesos atuais."
              : line.note}
          </p>
          <div className="app-split">
            <OrderTable title="Regra antiga" orders={line.current_orders ?? []} />
            {line.covered && (
              <OrderTable
                title="Aporte (recomendação)"
                orders={line.recommended_orders ?? []}
                leftover={line.recommended_leftover}
                showReason
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function OrderTable({
  title,
  orders,
  leftover,
  showReason = false,
}: Readonly<{
  title: string;
  orders: NonNullable<ContributionComparisonDTO["classes"]>[number]["current_orders"];
  leftover?: number;
  showReason?: boolean;
}>) {
  const list = orders ?? [];
  return (
    <div className="app-table-wrap">
      <table className="app-table" aria-label={title}>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Ativo</th>
            <th className="app-numeric">Quantidade</th>
            <th className="app-numeric">Valor</th>
          </tr>
        </thead>
        <tbody>
          {list.length === 0 && (
            <tr>
              <td colSpan={3} className="app-muted">
                Nenhuma compra.
              </td>
            </tr>
          )}
          {list.map((o) => (
            <tr key={o.ticker}>
              <td className="app-cell-wrap">
                <strong>{o.ticker}</strong> {o.new && <Badge tone="info">novo</Badge>}
                {showReason && o.reason && <div className="app-muted">{o.reason}</div>}
              </td>
              <td className="app-numeric">{quantity(o.quantity)}</td>
              <td className="app-numeric">{brl(o.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {leftover !== undefined && leftover > 0 && <p className="app-muted">Sobra sem compra: {brl(leftover)}.</p>}
    </div>
  );
}

/** Phase 45.6: the hierarchy tested in the past against equal weights, and the scoreboard of
 *  the stored runs. The switch of the contribution waits for the user's approval of this. */
function PastTest() {
  const state = useApi("recommendation-backtest", () => api.recommendation.backtest());
  return (
    <Async state={state}>
      {(data) => {
        if (data.status === "NOT_COMPUTED")
          return (
            <Empty
              title="O teste no passado ainda não rodou"
              hint="Ele roda toda semana depois das lentes; dá para pedir agora em Rodar agora, no fim desta tela."
            />
          );
        const scoreboard = data.scoreboard ?? [];
        return (
          <div className="app-page-stack">
            <Lead tone={data.passed ? "positive" : "caution"}>
              <p>
                {data.passed ? <Badge tone="success">Passou</Badge> : <Badge tone="warning">Não passou</Badge>} {data.reason}
              </p>
            </Lead>
            {data.status === "OK" && (
              <KpiGrid
                label="Resultado no passado"
                items={[
                  {
                    label: "Recomendação sobre a classe",
                    value: pct(data.strategy_annual, 1, true),
                    note: "ao ano, média mensal",
                  },
                  { label: "Pesos iguais sobre a classe", value: pct(data.equal_annual, 1, true), note: "entre os aptos" },
                  {
                    label: "Diferença",
                    value: pct(data.difference_annual, 1, true),
                    note: `${pct(data.probability, 0)} de chance de ser positiva`,
                    tone: (data.difference_annual ?? 0) > 0 ? "positive" : "caution",
                  },
                  {
                    label: "Meses que ganhou",
                    value: pct(data.hit_rate, 0),
                    note: `${data.months} meses, ${data.rebalances} trimestres, K médio ${num(data.average_k, 1)}`,
                  },
                ]}
              />
            )}
            {(data.years ?? []).length > 0 && (
              <div className="app-table-wrap">
                <table className="app-table" aria-label="Teste no passado por ano">
                  <thead>
                    <tr>
                      <th>Ano</th>
                      <th className="app-numeric">Meses</th>
                      <th className="app-numeric">Recomendação</th>
                      <th className="app-numeric">Pesos iguais</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.years ?? []).map((y) => (
                      <tr key={y.year}>
                        <td>{y.year}</td>
                        <td className="app-numeric">{y.months}</td>
                        <td className="app-numeric">{pct(y.strategy, 1, true)}</td>
                        <td className="app-numeric">{pct(y.equal, 1, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p>
              <strong>Placar das rodadas</strong>
            </p>
            {scoreboard.length === 0 ? (
              <p className="app-muted">O placar começa quando a primeira rodada completar um mês.</p>
            ) : (
              <div className="app-table-wrap">
                <table className="app-table" aria-label="Placar das rodadas">
                  <thead>
                    <tr>
                      <th className="app-numeric">Meses depois</th>
                      <th className="app-numeric">Rodadas</th>
                      <th className="app-numeric">Bateu pesos iguais</th>
                      <th className="app-numeric">Diferença média</th>
                      <th className="app-numeric">Diferença para a regra do Cerrado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scoreboard.map((line) => (
                      <tr key={line.horizon}>
                        <td className="app-numeric">{line.horizon}</td>
                        <td className="app-numeric">{line.runs}</td>
                        <td className="app-numeric">
                          {pct(line.beat_equal, 0)}{" "}
                          <span className="app-muted">
                            ({pct(line.beat_equal_low, 0)} a {pct(line.beat_equal_high, 0)})
                          </span>
                        </td>
                        <td className="app-numeric">{pct(line.vs_equal, 1, true)}</td>
                        <td className="app-numeric">
                          {line.vs_cerrado === null || line.vs_cerrado === undefined
                            ? "—"
                            : `${pct(line.vs_cerrado, 1, true)} (${line.cerrado_runs})`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Notes items={data.notes ?? []} title="O que este teste não cobre" />
          </div>
        );
      }}
    </Async>
  );
}

function Runs() {
  const state = useApi("recommendation-runs", () => api.recommendation.runs());
  return (
    <Async state={state}>
      {(runs) =>
        runs.length === 0 ? (
          <p className="app-muted">Nenhuma rodada ainda.</p>
        ) : (
          <div className="app-table-wrap">
            <table className="app-table" aria-label="Rodadas">
              <thead>
                <tr>
                  <th>Data</th>
                  <th className="app-numeric">Política</th>
                  <th className="app-numeric">Avaliados</th>
                  <th className="app-numeric">Aptos</th>
                  <th>Escolhidos</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.as_of}>
                    <td>{day(r.as_of)}</td>
                    <td className="app-numeric">{r.policy_version ? `v${r.policy_version}` : "padrão"}</td>
                    <td className="app-numeric">{r.assets}</td>
                    <td className="app-numeric">{r.eligible}</td>
                    <td className="app-cell-wrap">
                      {Object.entries(r.selected ?? {})
                        .map(([cls, tickers]) => `${CLASS_LABELS[cls] ?? cls}: ${tickers.join(", ")}`)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </Async>
  );
}

function ClassView({ matrix }: Readonly<{ matrix: ClassMatrixDTO }>) {
  const c = matrix.construction;
  return (
    <div className="app-page-stack">
      <Lead>
        <p>{leadText(matrix)}</p>
      </Lead>
      <KpiGrid
        items={[
          { label: "Aptos", value: String((matrix.rows ?? []).length), note: `${(matrix.excluded ?? []).length} fora pelos portões` },
          { label: "Escolhidos", value: String(c?.k ?? 0), note: "K dinâmico" },
          { label: "Confiança", value: pct(c?.confidence, 0), note: "puxa os alvos para os pesos atuais" },
          {
            label: "Consistência do AHP",
            value: num(matrix.consistency_ratio, 3),
            note: "aceita até 0,100",
            tone: matrix.consistency_ratio <= 0.1 ? "positive" : "negative",
          },
        ]}
      />
      <Section title="Escolhidos e pesos-alvo" subtitle="Antes de puxar para os seus pesos atuais.">
        <Chosen matrix={matrix} />
        {(c?.notes ?? []).length > 0 && <Notes items={c?.notes ?? []} title="Tetos" tone="caution" />}
      </Section>
      <Section title="Onde o K parou" subtitle="Cada passo: o melhor ativo que a regra de setores permitia.">
        <Curve matrix={matrix} />
      </Section>
      <Section title="Matriz de decisão" subtitle="Cada lente de 0 a 1 (maior é melhor), já puxada para 0,5 pela confiança.">
        <DecisionMatrix matrix={matrix} />
      </Section>
      <Section title="Pesos das lentes" subtitle={`Objetivo ${matrix.objective_label}, pela matriz AHP da política.`}>
        <Weights matrix={matrix} />
      </Section>
      <Section title="Fora pelos portões">
        <Excluded matrix={matrix} />
      </Section>
      <Section title="Por que A e não B?">
        <AandB key={matrix.arca_class} matrix={matrix} />
      </Section>
      <Section title="Aporte lado a lado" subtitle="O aporte (pela recomendação) ao lado da regra antiga da Estratégia; nada é gravado.">
        <SideBySide arcaClass={matrix.arca_class} />
      </Section>
    </div>
  );
}

function Board({ data }: Readonly<{ data: MatrixBoardDTO }>) {
  const classes = data.classes ?? [];
  const [chosen, setChosen] = useState(classes[0]?.arca_class ?? "");
  const matrix = classes.find((m) => m.arca_class === chosen) ?? classes[0];
  if (!matrix) return <Empty title="Nenhuma classe com ativos" />;
  return (
    <div className="app-page-stack">
      <p className="app-muted">
        Rodada de {day(data.as_of)}. <Badge tone="success">Decide o aporte</Badge>
      </p>
      {classes.length > 1 && (
        <Segmented
          label="Classe ARCA"
          options={classes.map((m) => [m.arca_class, CLASS_LABELS[m.arca_class] ?? m.arca_class])}
          value={matrix.arca_class}
          onChange={setChosen}
        />
      )}
      <ClassView key={matrix.arca_class} matrix={matrix} />
    </div>
  );
}

export function RecommendationPage() {
  const state = useApi("recommendation-matrix", () => api.recommendation.matrix());
  return (
    <div className="app-page">
      <PageHeader
        title="Recomendação"
        subtitle="Por que estes ativos: portões, lentes, matriz de decisão pelo AHP e pesos-alvo de cada classe."
      />
      <Async state={state}>
        {(data) =>
          data.status !== "OK" ? (
            <Empty
              title="A recomendação ainda não rodou"
              hint="Ela roda toda semana depois do garimpo; dá para pedir agora em Rodar agora, no fim desta tela."
            />
          ) : (
            <Board data={data} />
          )
        }
      </Async>
      <Section
        title="Teste no passado e placar"
        subtitle="A hierarquia refeita a cada trimestre do passado, só com o que se sabia, contra pesos iguais; e como foram as rodadas guardadas."
      >
        <PastTest />
      </Section>
      <Section title="Rodadas" subtitle="Histórico das rodadas semanais e a versão da política que cada uma aplicou.">
        <Runs />
      </Section>
      <Section
        title="Rodar agora"
        subtitle="Rodam sozinhas toda semana, nesta ordem, depois do garimpo; o garimpo fica na tela Garimpo."
      >
        <JobRunList jobs={manualJobs(["refresh_asset_lenses", "backtest_recommendation"])} onChange={state.reload} />
      </Section>
      <Notes
        items={[
          "Os portões só tiram o que é objetivo e grave; o Cerrado é uma lente com peso, e quem não foi analisado tem nota 0.",
          "O retorno esperado acima da classe usa a escala declarada na política (nota 1 = +6% ao ano); ela ainda não foi calibrada pelo backtest.",
          "Desde a troca, o aporte segue os pesos-alvo desta tela nas classes cobertas; sem rodada recente (mais de 14 dias), volta à regra da Estratégia.",
        ]}
      />
    </div>
  );
}
