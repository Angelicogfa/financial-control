# ADR 0007 — Estrutura do Frontend: Shell de Referência, Home Analítica e Telas de Operação

- **Status:** Aceito
- **Data:** 2026-10-25
- **Complementa:** ADR 0005 (contextos de operação) e substitui a seção de layout de `docs/architecture/FRONTEND_UI_UX.md`.
- **Referência:** módulo `apps/web` do projeto `dynamic-research` (shell, menu, conteúdo interno, home e visualizações).

## Contexto
O frontend atual é um `App.tsx` monolítico, sem rotas, com menu hambúrguer e indicadores misturados em todas as telas. A ADR 0005 definiu a navegação por contexto de operação. Faltava fixar **como** cada tela se organiza. O usuário pediu que a estrutura siga o web do `dynamic-research`, com a home sendo a tela de analytics e as telas de operação contendo apenas o domínio da operação.

## Decisão

### 1. Shell (igual ao de referência)
- **Sidebar fixa** (248 px, superfície branca, borda à direita, `position: sticky`) com: marca no topo, **seções com rótulo em caixa alta**, itens com ícone SVG em linha, grupos que abrem e fecham (aberto quando a rota atual é de um filho) e rodapé com o usuário (sair) e a versão.
- **Topbar** de 48 px com o botão que recolhe o menu e o **título da página atual**, derivado da rota.
- **Conteúdo** com margem lateral fluida (`clamp`), largura total e sem rolagem horizontal da página.
- **Celular (< 900 px):** o menu vira gaveta sobreposta com fundo escurecido; fecha ao navegar e com Esc.
- **Rotas próprias** para cada operação e para cada formulário que sai do contexto da lista (`/x`, `/x/new`, `/x/:id`); URL desconhecida autenticada mostra **404**, não a home; `/` redireciona para `/home`.

### 2. Menu por contexto (ADR 0005, em seções)
| Seção | Itens |
|---|---|
| **Visão geral** | Início (analytics) · Desempenho |
| **Operação** | Carteira · Pesquisar · Aportar · Lançamentos |
| **Configuração** | Estratégia · Contas · Dados de mercado |

### 3. Home = analytics
A home conta a situação em **atos**, como a de referência:
1. **Cabeçalho-manchete**: saudação e uma frase-resumo gerada dos números (ex.: "Patrimônio de R$ 56 mil, +2,1% no mês; Real Estate está abaixo da banda.").
2. **Indicadores**: patrimônio, resultado consolidado, TWR 12m vs CDI, proventos 12m, caixa de reserva — cada um com variação e minilinha (sparkline).
3. **Alocação**: ARCA atual × meta com banda (barras com marca de meta) e o que exige atenção (alertas).
4. **Evolução**: curva base 100 da carteira contra benchmarks e proventos por mês.

### 4. Telas de operação = só o domínio
Carteira, Pesquisar, Aportar, Lançamentos, Estratégia, Contas e Dados de mercado **não repetem indicadores gerais**. Cada uma mostra apenas o que a operação precisa, e **gráficos só quando são da operação**: antes/depois por classe no Aportar, histórico de fundamentos e preço no detalhe do ativo, proventos do ativo, composição da classe na Carteira.

### 5. Visualizações próprias em SVG
Como na referência, gráficos são componentes SVG pequenos e acessíveis (`Sparkline`, `TrendChart`, `BarList`, `StackedBar`), com `<title>` descritivo, valor em texto ao lado (a barra nunca é a única forma de ler o número) e paleta `--viz-*`. Não se adota biblioteca de gráficos.

### 6. Dados e estado
`react-router-dom` para rotas; cliente HTTP tipado que **propaga erros** (fim do "R$ 0" quando a API cai) e um hook `useApi` com carregando/erro/recarregar. Regras de negócio permanecem no backend (o cálculo local de aporte é removido).

### 7. Tema
Tokens de espaço e tipografia da referência (`--space-0..6`, `--text-micro..hero`), paleta azul/cinza/branco com papéis semânticos (`--app-*`) e modo escuro por `data-theme`.

## Consequências
- **Positivas:** navegação previsível e com links; a home responde "como estou?" e as operações respondem "o que faço agora?" sem ruído; menos dependências (sem biblioteca de gráficos ou de estado).
- **Negativas:** reescrita completa do `apps/web`; os gráficos SVG exigem testes próprios.
