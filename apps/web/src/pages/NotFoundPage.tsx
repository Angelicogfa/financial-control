import { Link } from "react-router-dom";

import { Empty } from "../components/States";

export function NotFoundPage() {
  return (
    <div className="app-page app-page-narrow">
      <Empty title="Página não encontrada" hint="O endereço não corresponde a nenhuma tela do app.">
        <Link className="app-primary-button" to="/home">
          Ir para o início
        </Link>
      </Empty>
    </div>
  );
}
