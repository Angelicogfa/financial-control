import type {
  AssetContributionOrderDTO,
  ClassContributionRationaleDTO,
  IntraClassStrategy,
  SavedContributionPlanDTO,
} from "../../api/types";
import { Notes, Section } from "../../components/Section";
import { brl, num, points } from "../../utils/format";
import { ARCA_LABELS, STRATEGY_LABELS } from "../../utils/labels";

/** The fixed rules behind every plan, in the order the engine applies them. */
const METHOD_STEPS = [
  "Classes: as que estão abaixo da banda recebem primeiro, até voltar à meta; o resto vai para as classes na proporção do que falta para a meta de cada uma. Nada é vendido.",
  "Ativos: dentro de cada classe entram só os elegíveis (lançamentos válidos, finalidade ARCA e aprovados pela Estratégia). O peso alvo de cada um vem da divisão escolhida para a classe, e o dinheiro vai primeiro para quem está mais abaixo desse peso.",
  "Arredondamento: compram-se unidades inteiras; as sobras compram mais unidades nas classes mais distantes da meta.",
];

const METHOD_NOTES = [
  "São regras fixas, não uma otimização: o aporte não compara valuation, múltiplos, retorno histórico, risco nem correlação entre os ativos.",
  "Entre dois ativos da mesma classe decidem só a divisão da classe (nota do checklist, peso manual ou peso igual) e a distância de cada um até o seu peso alvo.",
];

/** The first-level rule that decided what one class receives, in words. */
export function classReasonText(r: ClassContributionRationaleDTO): string {
  const now = `${points(r.current_pct)} contra a meta de ${points(r.target_pct, 0)}`;
  switch (r.reason) {
    case "REFILL_BELOW_BAND":
      return `Abaixo da banda (${now}, tolerância de ${points(r.band_pct, 0)}): recompõe primeiro; faltavam ${brl(r.deficit_brl)} para a meta.`;
    case "BELOW_BAND_PRIORITY":
      return `Fica de fora (${now}): as classes abaixo da banda precisavam de mais que o aporte inteiro.`;
    case "BELOW_TARGET":
      return `Dentro da banda e abaixo da meta (${now}): recebe na proporção do que falta, ${brl(r.deficit_brl)}.`;
    case "ABOVE_TARGET":
      return `Na meta ou acima (${now}): não recebe.`;
    case "NO_ELIGIBLE_ASSETS":
      return `Receberia ${brl(r.first_level_brl)}, mas não tem ativo elegível: o valor passou para as outras classes.`;
  }
}

function weightBasis(o: AssetContributionOrderDTO, strategy: IntraClassStrategy | null | undefined): string {
  const target = points(o.intra_class_target_weight_pct);
  if (strategy === "CERRADO") return `Nota ${o.cerrado_score} no checklist → peso alvo ${target}`;
  if (strategy === "MANUAL_WEIGHT") return `Peso manual → alvo ${target}`;
  if (strategy === "EQUAL_WEIGHT") return `Peso igual → alvo ${target}`;
  return `Peso alvo ${target}`;
}

/** Why one asset got (or did not get) a purchase; empty for plans saved before the rationale. */
export function orderReasonText(o: AssetContributionOrderDTO, strategy?: IntraClassStrategy | null): string {
  const leftover = o.leftover_amount_brl ?? 0;
  switch (o.reason) {
    case "BOUGHT": {
      const ownSpent = o.executed_amount_brl - leftover;
      let text = `Abaixo do peso alvo: reservados ${brl(o.allocated_amount_brl)}.`;
      if (o.allocated_amount_brl - ownSpent >= 0.01) {
        text += ` ${brl(o.allocated_amount_brl - ownSpent)} não compram mais uma unidade.`;
      }
      if (leftover >= 0.01) text += ` Mais ${brl(leftover)} vindos das sobras de outros ativos.`;
      return text;
    }
    case "LEFTOVER_FILL":
      return `Já estava no peso alvo; compra só com as sobras de outros ativos (${brl(leftover)}).`;
    case "PRICE_ABOVE_BUDGET":
      return `Reservados ${brl(o.allocated_amount_brl)}, mas uma unidade custa ${num(o.unit_price_brl)}: o valor foi para outros ativos.`;
    case "ABOVE_TARGET":
      return "Já está no peso alvo ou acima: não recebe neste aporte.";
    case "ZERO_WEIGHT":
      return strategy === "CERRADO"
        ? "Nota zero no checklist: sem peso na classe."
        : strategy === "MANUAL_WEIGHT"
          ? "Sem peso manual: não recebe."
          : "Sem peso na classe: não recebe.";
    case "NO_PRICE":
      return "Sem cotação: não dá para calcular a quantidade.";
    default:
      return "";
  }
}

/** Weight basis line under each asset: strategy, current weight and target inside the class. */
export function orderWeightText(o: AssetContributionOrderDTO, strategy?: IntraClassStrategy | null): string {
  const basis = weightBasis(o, strategy);
  return o.reason ? `${basis} · hoje ${points(o.class_current_weight_pct ?? 0)}` : basis;
}

export function strategyByClass(saved: SavedContributionPlanDTO): Map<string, IntraClassStrategy | null | undefined> {
  return new Map((saved.plan.class_rationale ?? []).map((r) => [r.arca_class, r.strategy]));
}

export function PlanRationale({ saved }: Readonly<{ saved: SavedContributionPlanDTO }>) {
  const rationale = saved.plan.class_rationale ?? [];
  return (
    <Section
      title="Como chegamos nesta sugestão"
      subtitle="As regras aplicadas e o que cada uma decidiu. O motivo de cada ativo está na tabela de ativos."
      label="Justificativa do aporte"
    >
      <ol className="contribute-method">
        {METHOD_STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {rationale.length === 0 ? (
        <p className="app-muted">Plano salvo antes da justificativa: a regra de cada classe não foi registrada.</p>
      ) : (
        <div className="app-table-wrap">
          <table className="app-table" aria-label="Regra aplicada a cada classe">
            <thead>
              <tr>
                <th>Classe</th>
                <th>Regra aplicada</th>
                <th className="app-numeric">Pela regra</th>
                <th className="app-numeric">Recebeu</th>
                <th>Divisão entre os ativos</th>
              </tr>
            </thead>
            <tbody>
              {rationale.map((r) => (
                <tr key={r.arca_class}>
                  <td>{ARCA_LABELS[r.arca_class]}</td>
                  <td>{classReasonText(r)}</td>
                  <td className="app-numeric">{brl(r.first_level_brl)}</td>
                  <td className="app-numeric">{brl(r.received_brl)}</td>
                  <td>
                    <span className="app-cell-main">
                      {r.strategy ? STRATEGY_LABELS[r.strategy] : "—"}
                      <small>
                        {r.strategy_overridden ? "Escolhida neste aporte" : "Da Estratégia"} ·{" "}
                        {r.eligible_assets === 1 ? "1 ativo elegível" : `${r.eligible_assets} ativos elegíveis`}
                      </small>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Notes items={METHOD_NOTES} title="O que o cálculo não faz" label="Limites do cálculo" />
    </Section>
  );
}
