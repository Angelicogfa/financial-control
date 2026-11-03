import { Notes } from "../../components/Section";
import { PageHeader } from "../../components/PageHeader";
import { DisclosureFeed } from "./DisclosureFeed";
import { EventStudy } from "./EventStudy";

const NOTES = [
  "Os documentos vêm do IPE da CVM, atualizado uma vez por dia, e cobrem as ações brasileiras da carteira e da lista de observação (FIIs e ETFs não publicam no IPE).",
  "Um documento entregue mais de 30 dias antes de chegar aqui entra já lido.",
  "Marcar como lido tira o alerta de fato relevante do Início.",
  "O tipo de evento vem de palavras-chave no assunto do documento; o PDF não é lido.",
];

/** Relevant facts and notices of the followed companies, out of the Home (Phase 40.1). */
export function DisclosuresPage() {
  return (
    <div className="app-page">
      <PageHeader
        title="Fatos relevantes"
        subtitle="Fatos relevantes e comunicados que as empresas da carteira e da observação entregaram à CVM."
      />
      <div className="app-page-stack">
        <DisclosureFeed limit={100} title="Comunicados à CVM" />
        <EventStudy />
        <Notes items={NOTES} />
      </div>
    </div>
  );
}
