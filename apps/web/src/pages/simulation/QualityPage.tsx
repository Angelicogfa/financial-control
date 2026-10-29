/** Qualidade dos modelos: the backstage of the "quanto confiar" seals (Phase 41.7). */

import { PageHeader } from "../../components/PageHeader";
import { Lead } from "../../components/Section";
import { ConfidencePanel, LabPanel } from "./views";

export function QualityPage() {
  return (
    <div className="app-page">
      <PageHeader
        title="Qualidade dos modelos"
        subtitle="Bastidores dos selos 'Quanto confiar'. Roda sozinho toda semana; dá para pedir de novo aqui."
      />
      <div className="app-page-stack">
        <Lead eyebrow="Para que serve">
          <p>
            Aqui se mede se as chances que os estudos mostram costumam se confirmar e se algum modelo de regime ou de risco prevê
            o mês seguinte melhor que uma regra simples. Os estudos usam o resultado no selo de confiança de cada capítulo.
          </p>
        </Lead>
        <ConfidencePanel />
        <LabPanel />
      </div>
    </div>
  );
}
