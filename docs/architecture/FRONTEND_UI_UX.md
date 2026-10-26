# Frontend — Estrutura, Navegação e Design System (`apps/web`)

> Implementa a ADR 0005 (contextos de operação) e a ADR 0007 (shell de referência, home analítica, telas de operação só com o domínio). Modelo visual: o web do projeto `dynamic-research`.

---

## 1. Princípios

1. **A home responde "como estou?"; cada operação responde "o que faço agora?".** Indicadores gerais moram só na home (Início) e em Desempenho; telas de operação mostram apenas o seu domínio.
2. **Gráfico só quando é da operação**: antes/depois por classe no Aportar, composição da classe na Carteira, preço, lucro anual e proventos no detalhe do ativo.
3. **Nenhuma regra de negócio no frontend.** O cálculo (alocação, aporte, checklist, valuation, alertas) é do backend; o cliente formata e apresenta.
4. **Erro nunca vira zero.** Toda chamada propaga a mensagem da API (ou "servidor fora do ar") com "Tentar de novo".
5. **Tipos gerados**: `apps/web/src/api/types.ts` vem do OpenAPI da API (`uv run python scripts/gen_web_types.py`); nenhuma forma do backend é redeclarada à mão.

## 2. Shell e navegação

- **Sidebar fixa de 248 px** com marca, seções em caixa alta, itens com ícone SVG em linha, contador de alertas no Início e rodapé com usuário, troca de tema e sair. Abaixo de 900 px vira **gaveta** (fundo escurecido, fecha ao navegar e com Esc). O botão da topbar recolhe o menu no desktop.
- **Topbar de 48 px** com o título da página derivado da rota.
- **Conteúdo** com margem lateral `clamp(16px, 3vw, 48px)` e largura máxima de 1180 px; tabelas rolam na horizontal dentro do cartão, a página nunca.
- **Login fora do shell**; sessão expirada (401) volta ao login com aviso.

| Seção | Item | Rota |
|---|---|---|
| Visão geral | Início (analytics) | `/home` (`/` redireciona) |
| | Desempenho | `/performance` |
| Operação | Carteira | `/portfolio`, `/asset/new`, `/asset/:id`, `/asset/:id/edit` |
| | Pesquisar | `/research` (`?tab=watchlist`) |
| | Aportar | `/contribute`, `/contribute/:planId` |
| | Lançamentos | `/ledger` (`?tab=earnings|events`), `/ledger/trades/new`, `/ledger/trades/:id/edit`, `/ledger/earnings/new`, `/ledger/earnings/:id/edit`, `/ledger/events/new`, `/ledger/import` |
| Configuração | Estratégia | `/settings/strategy` |
| | Contas | `/settings/accounts` |
| | Dados de mercado | `/settings/market-data` |

URL desconhecida mostra **404**. O detalhe do ativo usa `/asset/` (singular) porque o nginx serve o bundle em `/assets/`. Abas ficam em `?tab=` para que links e "voltar" as preservem.

## 3. Telas

- **Início** (atos): manchete gerada dos números (patrimônio e variação sem aportes, classe mais abaixo da banda, alertas) → indicadores com variação e minilinha (patrimônio, resultado consolidado, rentabilidade 12 m vs CDI, proventos 12 m, reserva) → alocação ARCA atual × meta com banda + "o que precisa de atenção" (alertas com dispensa por 7 dias) → evolução base 100 (carteira, CDI, Ibovespa) e proventos por mês.
- **Desempenho**: período (6 m, 12 m, 24 m, tudo), base 100 de carteira e referências, risco e retorno (TWR, CAGR, volatilidade, Sharpe, Sortino, queda máxima, VaR/CVaR), comparação com referências, drawdown e resultado por classe ao lado da referência da classe. "Histórico insuficiente" explícito.
- **Carteira**: posições agrupadas por classe (linha de grupo com valor e peso × meta), peso atual/alvo na classe, situação no ciclo de vida, nota do checklist, preço sem cotação sinalizado; filtro por conta; aba por classe mostra a composição.
- **Detalhe do ativo**: Resumo (posição, risco, preço 12 m), Fundamentos (indicadores atuais, métricas históricas, lucro anual, demonstrativos), Valuation (veredito, métodos por perfil), Checklist (perfil, Sim/Não/Não se aplica com evidência, respostas automáticas com a evidência calculada, histórico da nota), Proventos e Lançamentos.
- **Pesquisar**: screener do catálogo B3 (texto, tipos, liquidez, P/L, P/VP, DY, ROE, "só classes abaixo da banda", esconder cadastrados) com veredito de valuation e "Observar", que pede o quadrante ARCA com a sugestão marcada ("(sugerida)") antes de confirmar; aba Em observação com classe ARCA editável na própria linha, situação, checklist, valuation e margem, e o formulário por código com tipo e quadrante (vazio = sugerido).
- **Aportar**: etapas Valor → Classes (antes × depois × meta) → Ativos (quantidade, preço e taxas editáveis) → Confirmar (data e conta); planos salvos com situação.
- **Lançamentos**: compras e vendas, proventos e eventos corporativos com filtros por ativo, conta e período; exclusão mostra a recusa do livro quando houver; importação B3 com pré-visualização por linha, tabela dos tickers desconhecidos (marcar, tipo e quadrante ARCA; trocar o tipo recalcula a sugestão; tipo desconhecido fica desmarcado até ser escolhido) e gravação tudo-ou-nada.
- **Estratégia** (metas devem somar 100%, bandas, divisão interna, elegibilidade, valuation e projeções em %; salvar cria versão), **Contas** e **Dados de mercado** (frescor das séries e última execução de cada rotina do worker).

## 4. Design system

- **Tokens** (`src/styles/theme.css`): espaço `--space-0..6` (2/4/8/12/16/24/32 px), tipo `--text-micro..hero` (11/12/14/16/20/30 px), papéis `--app-*` (superfície, borda, texto, primário, sucesso, aviso, perigo) e paleta de visualização `--viz-*`.
- **Tema escuro** redefine só os papéis em `:root[data-theme="dark"]`; `index.html` aplica a escolha salva ou a do sistema antes da primeira pintura.
- **Componentes**: `PageHeader`, `Async`/`Loading`/`ErrorBanner`/`Empty`, `Badge`/`Signed`, `Tabs` (`useTab`), `ArcaClassSelect` (quadrante ARCA com a sugestão marcada), classes `.app-card`, `.app-table`, `.app-field-grid`, `.app-steps`, `.app-checklist`, `.home-kpi`.
- **Visualizações SVG próprias** (`src/viz`): `Sparkline` (decorativa), `TrendChart` (linhas com rótulo na ponta, lacunas, linha de base e leitura do ponto em texto), `BarList` (valor em texto, meta, banda e segunda barra antes/depois), `ColumnChart`. Todo gráfico tem `<title>` com a conclusão; a cor nunca é a única forma de ler o número.
- **Formatação** pt-BR em `src/utils/format.ts`; frações seguem a ADR 0006 (`pct(0.12)` → "12,0%"; campos `_pct` da API já vêm em pontos percentuais → `points`). Rótulos dos enums em `src/utils/labels.ts`.

## 5. Dados

- `src/api/http.ts`: `request<T>()` com cookie de sessão, `ApiError` (status, código, mensagem), evento de sessão expirada, mensagem de servidor fora do ar e validação 422 resumida.
- `src/api/endpoints.ts`: chamadas tipadas por contexto (`api.portfolio`, `api.research`, `api.contributions`, `api.ledger`, `api.policy`, …). `ImportNewAssetRequest` é declarado ali à mão porque viaja como JSON dentro do campo multipart `new_assets` e por isso não está entre os schemas gerados (`types.ts` vem de `scripts/gen_web_types.py`).
- `src/api/useApi.ts`: `useApi(key, load)` com `data`, `error`, `loading` e `reload`; trocar a `key` recarrega.

## 6. Qualidade

`npm run lint` (zero avisos), `npx tsc --noEmit`, `npm test` (Vitest + Testing Library: cliente HTTP, visualizações, história da home e cada página contra uma API falsa em `src/test/mockApi.ts`) e `npm run build`, todos dentro de `scripts/check.sh`.
