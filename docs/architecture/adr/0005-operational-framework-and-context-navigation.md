# ADR 0005 — Framework Operacional, Política de Investimento e Navegação por Contexto de Operação

- **Status:** Aceito
- **Data:** 2026-10-24
- **Substitui parcialmente:** ADR 0002 (Cerrado deixa de ser "opcional isolado" e passa a ser um dos modelos de checklist do módulo fundamentalista) e a seção 4 de `docs/architecture/FRONTEND_UI_UX.md` (hierarquia de navegação).

## Contexto
A ferramenta combina duas metodologias:
- **ARCA** — segmentação macro do portfólio (Ações, Real Estate, Caixa, Ativos Internacionais);
- **Análise Fundamentalista** — identificação e seleção de ativos (indicadores, histórico, valuation e checklists como o Diagrama do Cerrado).

A primeira proposta de layout separava o menu por metodologia ("ARCA" e "Fundamentalista"). Isso obriga o usuário a pensar em *qual método* está usando, quando o que ele quer fazer é uma *operação* (pesquisar um ativo, decidir um aporte, registrar uma compra, acompanhar a carteira). As metodologias são lentes que atravessam todas as operações, não destinos de navegação.

## Decisão

### 1. Ciclo operacional como espinha dorsal do produto
O produto é organizado pelo ciclo de operação do investidor; cada etapa aplica as duas metodologias:

| Etapa (menu) | Pergunta do usuário | Lente ARCA | Lente Fundamentalista |
|---|---|---|---|
| **Início** | "O que preciso fazer agora?" | Classes fora da banda de tolerância | Ativos que perderam elegibilidade, preço abaixo do teto |
| **Carteira** | "Como está o que eu tenho?" | Posições agrupadas por classe, peso atual vs alvo | Status de elegibilidade, score e margem de segurança por linha |
| **Pesquisar** | "O que vale a pena ter?" | Destaca classes abaixo da meta e filtra candidatos por classe | Screener, watchlist, histórico de fundamentos, valuation, checklists |
| **Aportar** | "Onde coloco meu dinheiro?" | Nível 1: distribuição entre classes por déficit | Nível 2: só ativos elegíveis, ponderados pela estratégia intra-classe |
| **Lançamentos** | "O que aconteceu?" | — | — (registro de ordens, proventos, eventos corporativos e importação B3) |
| **Desempenho** | "Está funcionando?" | Retorno por classe vs benchmark da classe | Retorno dos ativos vs tese (score no momento da compra) |
| **Estratégia** | "Quais são minhas regras?" | Metas, bandas de tolerância, finalidade (reserva) | Critérios de elegibilidade, checklists, premissas de valuation |

### 2. Política de Investimento como agregado de domínio
As regras das duas metodologias passam a viver num único agregado `InvestmentPolicy` (configurado em **Estratégia**):
- `ArcaPolicy`: meta por classe, banda de tolerância (p.p.), estratégia intra-classe;
- `EligibilityPolicy`: critérios fundamentalistas por tipo de ativo (checklist ativo, cobertura mínima de respostas, score mínimo, filtros quantitativos);
- `ValuationPolicy`: yield exigido do Bazin, aplicabilidade do Graham, premissas de projeção 12m por classe.

Todo motor (aporte, alertas, desempenho) recebe a política explicitamente; nenhum número de premissa fica escrito no código.

### 3. Ciclo de vida do ativo
Cada ativo tem um status operacional derivado da política e da posição:
`WATCHLIST` (candidato, sem posição) → `ELIGIBLE` (aprovado pela política) → `HELD` (com posição) → `REVIEW` (posição aberta mas reprovado pela política) → `ARCHIVED`.
Somente `ELIGIBLE`/`HELD` elegíveis recebem aporte. `REVIEW` gera alerta, nunca venda automática.

### 4. Navegação
- Desktop: trilho lateral persistente e recolhível com os 7 contextos acima (substitui o menu hambúrguer como navegação principal).
- Mobile (< 768px): o mesmo trilho vira drawer acionado pelo botão de menu.
- Detalhe do ativo é uma rota única (`/assets/:id`) acessível de Carteira, Pesquisar, Aportar e Início; o conteúdo se adapta ao status (candidato vs posição).
- Ações globais na topbar: `+ Lançamento` e indicador de frescor dos dados (cotações, BCB, último snapshot).

## Consequências
- **Positivas:** o usuário opera por intenção; as duas metodologias aparecem juntas em cada decisão (ex.: aporte só vai para ativo elegível na classe com déficit); regras ficam auditáveis e versionáveis num único lugar.
- **Negativas:** exige refatorar o frontend em rotas/feature-modules e introduzir novas entidades (`investment_policy`, `fundamental_snapshots`, `checklist_answers`, `accounts`, `alerts`, `contribution_plans`).
