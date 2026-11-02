/** Acompanhar (Phase 48.R6): what the investor watches — the list, the alert rules on any
 *  ticker, and the theses with their review dates. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/endpoints";
import type { AlertRuleDTO, RuleMetric, RuleOperator } from "../../api/types";
import { Badge } from "../../components/Badge";
import { PageHeader } from "../../components/PageHeader";
import { Section } from "../../components/Section";
import { Empty, ErrorBanner, Loading } from "../../components/States";
import { Tabs, useTab, type TabSpec } from "../../components/Tabs";
import { Watchlist } from "../../pages/research/ResearchPage";
import { day, money, num, parseDecimal, pct } from "../../utils/format";
import { instrumentPath } from "../instrument/paths";

type TabKey = "list" | "alerts" | "theses";
const TABS: TabSpec<TabKey>[] = [
  { key: "list", label: "Lista" },
  { key: "alerts", label: "Alertas" },
  { key: "theses", label: "Teses" },
];

export const METRICS: Array<[RuleMetric, string]> = [
  ["PRICE", "Preço (R$)"],
  ["DIVIDEND_YIELD", "Dividend yield (%)"],
  ["PRICE_TO_EARNINGS", "P/L"],
  ["PRICE_TO_BOOK", "P/VP"],
];

/** The typed limit as the API wants it: dividend yield is typed in % and sent as a fraction. */
export function thresholdFor(metric: RuleMetric, typed: string): number | null {
  const value = parseDecimal(typed);
  if (value === null || value < 0) return null;
  return metric === "DIVIDEND_YIELD" ? value / 100 : value;
}

function valueText(rule: AlertRuleDTO): string {
  const v = rule.current_value;
  if (v === null || v === undefined) return "sem dado";
  if (rule.metric === "DIVIDEND_YIELD") return pct(v, 2);
  if (rule.metric === "PRICE") return money(v);
  return num(v, 2);
}

function RuleForm() {
  const client = useQueryClient();
  const [ticker, setTicker] = useState("");
  const [metric, setMetric] = useState<RuleMetric>("PRICE");
  const [operator, setOperator] = useState<RuleOperator>("BELOW");
  const [limit, setLimit] = useState("");
  const [note, setNote] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (threshold: number) =>
      api.watch.createRule({ ticker: ticker.trim(), metric, operator, threshold, note: note.trim() || null }),
    onSuccess: () => {
      setTicker("");
      setLimit("");
      setNote("");
      void client.invalidateQueries({ queryKey: ["alert-rules"] });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const threshold = thresholdFor(metric, limit);
    if (!ticker.trim() || threshold === null) {
      setInvalid("Informe o código e um limite válido.");
      return;
    }
    setInvalid(null);
    create.mutate(threshold);
  };
  return (
    <form className="app-filter-bar" onSubmit={submit} aria-label="Nova regra de alerta">
      <label className="app-field">
        <span>Código</span>
        <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="PETR4" />
      </label>
      <label className="app-field">
        <span>Indicador</span>
        <select value={metric} onChange={(e) => setMetric(e.target.value as RuleMetric)}>
          {METRICS.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="app-field">
        <span>Condição</span>
        <select value={operator} onChange={(e) => setOperator(e.target.value as RuleOperator)}>
          <option value="BELOW">abaixo de</option>
          <option value="ABOVE">acima de</option>
        </select>
      </label>
      <label className="app-field">
        <span>Limite</span>
        <input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} />
      </label>
      <label className="app-field">
        <span>Nota</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="opcional" />
      </label>
      <button type="submit" className="app-primary-button" disabled={create.isPending}>
        Criar regra
      </button>
      {invalid && <p className="app-error-banner" role="alert">{invalid}</p>}
      <ErrorBanner error={create.error} />
    </form>
  );
}

function Rules() {
  const client = useQueryClient();
  const rules = useQuery({ queryKey: ["alert-rules"], queryFn: () => api.watch.rules() });
  const refresh = () => void client.invalidateQueries({ queryKey: ["alert-rules"] });
  const toggle = useMutation({
    mutationFn: (rule: AlertRuleDTO) => api.watch.updateRule(rule.id, { is_active: !rule.is_active }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: number) => api.watch.deleteRule(id), onSuccess: refresh });
  return (
    <div className="app-page-stack">
      <Section title="Nova regra" subtitle="Vale para qualquer ticker do catálogo; ao disparar, vira um alerta no Início.">
        <RuleForm />
      </Section>
      <Section title="Regras">
        {rules.isPending ? (
          <Loading lines={3} />
        ) : rules.isError ? (
          <ErrorBanner error={rules.error} onRetry={() => void rules.refetch()} />
        ) : rules.data.length === 0 ? (
          <Empty title="Nenhuma regra criada" hint="Ex.: avise quando PETR4 ficar abaixo de R$ 30." />
        ) : (
          <div className="app-table-wrap">
            <table className="app-table" aria-label="Regras de alerta">
              <thead>
                <tr>
                  <th>Regra</th>
                  <th className="app-numeric">Agora</th>
                  <th>Situação</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rules.data.map((rule) => (
                  <tr key={rule.id}>
                    <td>
                      <Link className="app-link" to={instrumentPath(rule.ticker)}>
                        {rule.description}
                      </Link>
                      {rule.note && <div className="app-muted">{rule.note}</div>}
                    </td>
                    <td className="app-numeric">{valueText(rule)}</td>
                    <td>
                      {!rule.is_active ? (
                        <Badge>Pausada</Badge>
                      ) : rule.triggered ? (
                        <Badge tone="warning">Disparou</Badge>
                      ) : (
                        <Badge tone="success">Aguardando</Badge>
                      )}
                    </td>
                    <td className="app-button-row">
                      <button type="button" className="app-secondary-button" onClick={() => toggle.mutate(rule)}>
                        {rule.is_active ? "Pausar" : "Ativar"}
                      </button>
                      <button
                        type="button"
                        className="app-secondary-button"
                        aria-label={`Apagar a regra ${rule.description}`}
                        onClick={() => remove.mutate(rule.id)}
                      >
                        Apagar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ErrorBanner error={toggle.error ?? remove.error} />
      </Section>
    </div>
  );
}

function Theses() {
  const notes = useQuery({ queryKey: ["notes"], queryFn: () => api.watch.notes() });
  if (notes.isPending) return <Loading lines={3} />;
  if (notes.isError) return <ErrorBanner error={notes.error} onRetry={() => void notes.refetch()} />;
  if (notes.data.length === 0) {
    return <Empty title="Nenhuma tese escrita" hint="Escreva a tese no capítulo “Minha tese” da página de cada ativo." />;
  }
  return (
    <ul className="app-thesis-list" aria-label="Teses">
      {notes.data.map((note) => (
        <li key={note.id} className="app-card app-card-padded">
          <div className="app-button-row">
            <Link className="app-link" to={`${instrumentPath(note.ticker ?? "")}?capitulo=tese`}>
              <strong>{note.ticker}</strong>
            </Link>
            <span className="app-muted">escrita em {day(note.written_on)}</span>
            {note.review_at && (
              <Badge tone={note.due ? "warning" : "neutral"}>
                {note.due ? `Revisar (desde ${day(note.review_at)})` : `Revisar em ${day(note.review_at)}`}
              </Badge>
            )}
          </div>
          <p>{note.text}</p>
        </li>
      ))}
    </ul>
  );
}

export function WatchlistPage() {
  const [tab, setTab] = useTab(TABS, "list");
  return (
    <div className="app-page">
      <PageHeader
        title="Acompanhar"
        subtitle="Os ativos que você observa, os alertas que você definiu e as teses que pedem revisão."
      />
      <Tabs tabs={TABS} active={tab} onSelect={setTab} label="Acompanhar" />
      {tab === "list" && <Watchlist />}
      {tab === "alerts" && <Rules />}
      {tab === "theses" && <Theses />}
    </div>
  );
}
