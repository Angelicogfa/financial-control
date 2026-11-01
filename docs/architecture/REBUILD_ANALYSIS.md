# Análise de Reconstrução — Financial Control frente ao Mercado

*Data: 2026-11-01. Base analisada: `main` em `be66147` (Fases 1–46, 39 migrations, 41 tabelas).*
*Documento irmão: [REFACTORING_PLAN.md](./REFACTORING_PLAN.md) (plano sistêmico e de experiência).*

> **Premissa inegociável:** a base de dados atual (`fincontrol_pgdata`) é preservada e continua sendo a fonte da operação. Nenhuma tabela é recriada, renomeada ou apagada; toda mudança de schema é **aditiva** (`script_00040` em diante). O código que já lê e grava esses dados é reaproveitado, não reescrito.

---

## 1. Resumo executivo

| Pergunta | Resposta |
|---|---|
| Dá para reutilizar o código como está? | **Não por completo.** Os motores de cálculo, a persistência, o worker e os provedores (≈ 75–80% do backend) ficam. A **camada de aplicação** precisa ser unificada e o **frontend** precisa de uma nova arquitetura de informação. |
| É preciso reescrever do zero? | **Não.** Reescrever jogaria fora ~37 mil linhas de domínio testado (126 arquivos de teste, golden tests de carteira de referência) sem ganho para o usuário. |
| O que mais afasta a ferramenta do mercado? | A **experiência**, não o cálculo. Faltam: busca global por ticker, página do ativo que funcione para *qualquer* ativo (não só cadastrado), uma carteira-hub com abas (como Status Invest e Investidor10), conciliação de posição com a B3, IR mensal/DARF e metas. |
| Estratégia recomendada | **Strangler incremental:** novo shell e novas rotas convivem com as atuais; cada tela antiga é substituída e redirecionada; a API ganha endpoints *por ticker* que compõem os serviços existentes. |

---

## 2. Benchmark de mercado

### 2.1 Quem é referência em quê

| Produto | Força principal | O que vale copiar |
|---|---|---|
| **Status Invest** | Dados fundamentalistas gratuitos e carteira | Carteira com abas *Patrimônio, Proventos, Metas, Subcarteiras, Composição, Rentabilidade*; página do ativo com indicadores agrupados em valuation, endividamento, eficiência, rentabilidade e crescimento; histórico de proventos por janela |
| **Investidor10** | Carteira + análise + IRPF num lugar só | Menu da carteira *Resumo, Lançamentos, Proventos, Gráficos, Metas, Análise, Meu DARF/IRPF*; rastreador → página do ativo → comparador de até 5 ativos; agenda e radar de dividendos |
| **Kinvo** | Consolidação e rentabilidade | Separação clara de *ganho de capital × proventos*; múltiplas carteiras por objetivo; metas; cobertura FGC; relatório em PDF; projeção da carteira |
| **Gorila** | Consolidação multi-instituição e simplicidade | Histórico de movimentações acima da distribuição; comparação com índices a um clique ("Ir para gráficos") |
| **Simply Wall St** | Análise visual | Relatório do ativo em capítulos fixos (*Visão geral → Valuation → Crescimento futuro → Desempenho passado → Saúde financeira → Dividendos → Gestão → Acionistas*) e o **Snowflake**, um resumo visual de 5 eixos por checagens aprovadas |
| **Sharesight** | Desempenho e imposto | Relatório de desempenho que separa *ganho de capital, proventos e câmbio* em qualquer período; multi-período; **renda futura** (proventos anunciados + projeção de 3 anos); relatórios de alocação e imposto |
| **Morningstar Portfolio X-Ray** | Raio-X da carteira | Olhar *através* dos fundos/ETFs: sobreposição de ações, exposição por setor e região, style box, múltiplos médios da carteira |
| **Snowball Analytics** | Dividendos | Calendário de dividendos, *yield on cost*, nota de dividendo própria |
| **myProfit / Investidor10 DARF** | Imposto | Apuração mensal por categoria (swing, day trade, FII), compensação de prejuízo, emissão de DARF |

Padrões de UX recorrentes em 2026: **divulgação progressiva** (começar simples e aprofundar sob demanda), dashboard que **guia a decisão** com uma ação principal por tela, transparência sobre "o que está acontecendo, por quê e o que significa para você", e navegação organizada por **tarefa do usuário**, não por módulo interno.

### 2.2 Matriz de funcionalidades

Legenda: ✅ tem · 🟡 parcial · ❌ não tem.

| Funcionalidade | Mercado | Financial Control hoje |
|---|---|---|
| Busca global por ticker/nome em qualquer tela | Todos | ❌ busca só dentro do screener |
| Página do ativo para **qualquer** ativo (cadastrado ou não) | Todos | ❌ `/asset/:id` exige cadastro (precisa "Observar" antes) |
| Página do ativo em capítulos com resumo visual | Simply Wall St, Status Invest | 🟡 9 abas técnicas; as lentes da Fase 45 já dão o "snowflake", mas não aparecem no ativo |
| "Na minha carteira" dentro da página do ativo | Investidor10, Status Invest | ✅ resumo, proventos, lançamentos, tributação |
| Carteira-hub com abas (patrimônio, rentabilidade, proventos, composição) | Status Invest, Investidor10 | 🟡 espalhado em Carteira, Desempenho, Saúde e Início |
| Conciliação de posição com a B3 / corretora | Kinvo, Gorila (via integração) | ❌ importa Negociação e Movimentação, não confere contra o extrato de **Posição** |
| Integração automática B3 / Open Finance | Kinvo, Gorila, Investidor10 | ❌ por desenho (planilha); API B3 exige licença de instituição |
| Rentabilidade com ganho de capital × proventos × câmbio | Sharesight, Kinvo | 🟡 consolidado separa realizado, não realizado e proventos; câmbio não é isolado |
| Rentabilidade multi-período / por ativo / atribuição | Sharesight | 🟡 TWR da carteira; por classe aproximado (TD-07) |
| Raio-X: setor, sobreposição de ETF, concentração | Morningstar | 🟡 `etf_exposure` e diversificação existem dentro de Saúde |
| Agenda de proventos | Investidor10, Snowball, Sharesight | ✅ agenda declarada |
| Renda futura projetada (12–36 meses) | Sharesight, Snowball | ❌ |
| Metas (patrimônio, renda passiva) | Status Invest, Kinvo, Investidor10 | ❌ (só dentro de estudos de simulação) |
| Subcarteiras por objetivo | Status Invest, Kinvo | 🟡 contas de custódia e `purpose` (ARCA / reserva), sem subcarteira livre |
| IR mensal, compensação de prejuízo, DARF | myProfit, Investidor10 | ❌ (TD-04) |
| Informe para IRPF (bens e direitos) | Investidor10, myProfit | ❌ |
| Comparador de até 5 ativos | Investidor10, AUVP | ✅ |
| Screener / rankings | Todos | ✅ screener + garimpo |
| Fatos relevantes | Status Invest | ✅ CVM, com estudo de eventos |
| Alertas de preço definidos pelo usuário | Investidor10, apps de corretora | ❌ (só alertas calculados) |
| Tese / anotações por ativo | Simply Wall St (narratives) | 🟡 evidência no checklist; sem diário de tese |
| Relatório mensal exportável (PDF) | Kinvo, Sharesight | ❌ |
| Aporte que rebalanceia por método | Diagrama do Cerrado | ✅ **à frente**: ARCA + Cerrado + lentes + justificativa |
| Simulação, backtest, previsão probabilística | Raro em varejo | ✅ **à frente** |
| Operação por agente (MCP) | Gorila AI (pago) | ✅ **à frente** |

**Leitura:** o Financial Control já é mais profundo que o mercado em *decidir* (aporte, recomendação, simulação). Fica atrás em *encontrar* (busca, ativo não cadastrado), *conferir* (conciliação, IR) e *contar a história* (carteira-hub, página do ativo em capítulos).

---

## 3. Diagnóstico da experiência atual

### 3.1 Navegação por módulo, não por tarefa
O menu tem **18 itens em 4 seções** (`layout/navigation.ts`). Quatro deles respondem à mesma pergunta, "como está minha carteira?" (Início, Desempenho, Saúde, Carteira), e três à pergunta "onde ponho o dinheiro?" (Recomendação, Aportar, Garimpo). O usuário precisa saber em que módulo a informação mora.

### 3.2 A história se quebra entre telas
- Do screener para o detalhe exige cadastrar o ativo como `WATCHLIST` — pesquisar vira um ato de escrita.
- A Recomendação (6 abas, 864 linhas) e o Aportar (547 linhas) contam a mesma decisão em duas telas.
- Saúde da carteira (7 pilares) e Desempenho mostram risco e retorno com cortes diferentes do mesmo dado.
- Não existe "voltar à pergunta": depois de aportar, nada mostra a carteira conferida contra a corretora.

### 3.3 Densidade sem hierarquia
As páginas maiores (`simulation/views.tsx` 1.369 linhas, `RecommendationPage` 864, `ResearchPage` 776, `AssetDetailPage` 704) mostram tudo de uma vez. Falta a camada de resumo que o mercado usa antes do detalhe (o *Snowflake*, o cartão de veredito).

### 3.4 Sem controle de posição verificável
A posição é calculada do livro (lançamentos + eventos). Não há como confirmar que ela bate com o extrato de **Posição** da B3 por ativo e por conta, que é o que o investidor faz à mão todo mês.

---

## 4. Diagnóstico do código

### 4.1 Tamanho por camada (linhas, sem testes nem migrations)

| Camada | Linhas | Estado |
|---|---|---|
| `apps/api/domain` | 36.640 | motores puros sólidos; serviços de aplicação misturados com DTO de apresentação |
| `apps/api/infra` | 9.087 | repositórios, provedores, MCP — bom |
| `apps/api/controllers` | 6.967 | finos, conforme a regra |
| `apps/api/worker` | 2.713 | dois papéis (ingestão/processamento), bom |
| `apps/api/core` | 730 | bom |
| `apps/api/tests` | 24.624 | 126 arquivos, inclui golden e caracterização — **ativo valioso** |
| `apps/web/src/pages` | 14.423 | páginas grandes, uma por módulo |
| `apps/web/src` (resto) | 6.497 + 2.847 (`types.ts` gerado) | componentes, viz SVG, cliente HTTP — reaproveitáveis |

### 4.2 O que se reutiliza como está

| Bloco | Onde | Por quê |
|---|---|---|
| **Schema e dados** | `infra/data/models`, 39 migrations, 41 tabelas | premissa; já modela ativo, livro, eventos, política versionada, séries, catálogo, CVM, previsões, lentes |
| **Motores de cálculo** | `domain/portfolio/services/{consolidation,fixed_income,mark_to_market,analytics,curves}`, `domain/ledger`, `domain/tax`, `domain/policy`, `domain/assets/services/{cerrado,valuation,classic_valuation,history}` | puros, cobertos por golden tests e caracterização |
| **Motores analíticos** | `domain/recommendation`, `domain/simulation`, `domain/forecast`, `domain/mining`, `domain/comparison`, `domain/disclosures` | diferencial frente ao mercado |
| **Unit of Work e repositórios** | `infra/data/unit_of_work`, `infra/data/repositories` | já devolvem entidades de domínio |
| **Worker e provedores** | `worker/`, `infra/providers/{brapi,yahoo,bcb,tesouro,stored}` | Fase 38/39: telas leem do banco; nada muda |
| **MCP** | `infra/mcp`, `domain/agentic/services/catalog.py` | continua sendo outro "cliente" da mesma aplicação |
| **Frontend base** | `api/http.ts`, `api/types.ts` (gerado), `viz/*`, `components/*`, `utils/format.ts`, tokens de `theme.css` | sem regra de negócio; servem ao novo shell |

### 4.3 O que precisa ser unificado

| Problema | Evidência | Unificação |
|---|---|---|
| **Domínio importa a apresentação** | 25 módulos em `domain/**/services` importam `controllers.*` (DTOs de request/response); ex.: `domain/ledger/services/use_cases/b3_import.py` importa `controllers.ledger.responses` | Use cases recebem comandos e devolvem *read models* de domínio (dataclasses); a serialização para DTO volta ao controller. Regra garantida por teste de arquitetura (contrato de imports) |
| **Domínio importa infraestrutura** | 10 módulos de `domain` importam `infra.*` | Dependência por porta (`domain/shared/repositories.py`, gateways) injetada pela `composition.py` |
| **Ativo identificado por `id` de cadastro** | `AssetUseCases.get_analysis(asset_id)`; catálogo, `market_data`, `asset_price_history`, fundamentos e CVM são por **ticker** | Um *read model* `InstrumentView` por ticker que compõe catálogo + mercado + fundamentos + lentes + previsão + posição (se houver). `asset_id` vira detalhe interno |
| **Quatro "comparar" diferentes** | `research/services/comparison.py` (ativos), `domain/comparison` (carteiras de comparação, Fase 36), `recommendation.compare` (A × B por lente), `study.compare` (estudos) | Nomes de domínio distintos e uma entrada de UX única "Comparar" com o modo escolhido pelo contexto |
| **Saúde × Desempenho × Início** | `portfolio/services/health.py` (1.660 linhas), `analytics.py`, `story.ts` da home | `health.py` dividido por pilar; Desempenho e Saúde viram abas de um hub da carteira que leem o mesmo snapshot |
| **Recomendação × Aportar** | duas páginas para a mesma decisão | A recomendação é o "porquê" dentro do Aportar; a página própria vira "Modelo" no laboratório |
| **Documentação desatualizada** | `OVERVIEW.md` §2.1 descreve `apps/api/src/fincontrol_api/modules` e `apps/packages`, removidos na Fase 17 | Atualizar junto com a Fase R1 |

### 4.4 O que precisa ser reconstruído

| Bloco | Por quê | Reaproveita |
|---|---|---|
| **Shell e arquitetura de informação** do web | navegação por módulo; sem busca global | `AppShell`, `Breadcrumbs`, `trail.ts`, `icons.tsx` |
| **Página do ativo** | presa a `asset_id`; abas técnicas sem capítulo de resumo | `ChecklistTab`, `ForecastTab`, `TaxTab`, `CvmStatements`, `PriceHistory`, `MarketTab` como seções |
| **Hub da carteira** | hoje em 4 telas | `PortfolioPage`, `PerformancePage`, `HealthPage`, `TreasuryMarketPanel`, `AccountsWealth` como abas |
| **Camada de dados do web** | `useApi` sem cache compartilhado; um hub com abas recarrega o mesmo dado | `http.ts` e `types.ts`; troca de `useApi` por cache por chave (TanStack Query ou cache próprio equivalente) |

### 4.5 Conclusão técnica

| Área | Reuso | Unificar | Reconstruir |
|---|---|---|---|
| Banco de dados | 100% | — | — |
| Motores de domínio | ~95% | divisão de `health.py` | — |
| Serviços de aplicação (use cases) | lógica ~90% | fronteira DTO/infra nos 25+10 módulos | — |
| Controllers / API | 100% das rotas atuais | — | novas rotas por ticker, busca, conciliação, IR, metas |
| Worker / provedores / MCP | 100% | — | novos jobs para os novos read models |
| Frontend: componentes, viz, cliente | ~85% | — | — |
| Frontend: páginas | ~50% como seções | — | shell, IA, página do ativo, hub da carteira, Aportar |

---

## 5. Experiência-alvo (resumo)

O detalhamento está em [REFACTORING_PLAN.md §3](./REFACTORING_PLAN.md#3-experiência-alvo). Em uma frase: **uma história em seis atos que o usuário percorre sem saber onde cada dado mora** —

1. **Como estou?** (Início: patrimônio, resultado, o que mudou desde a última visita)
2. **Está tudo certo?** (Carteira › Conferir: posição × B3, dados velhos, alertas)
3. **O que merece atenção?** (fora da banda, tese vencida, fato relevante, IR do mês)
4. **O que existe por aí?** (Explorar + busca global → qualquer ativo, na carteira ou não)
5. **O que faço com o dinheiro?** (Aportar com o porquê da recomendação)
6. **Para onde vou?** (Planejar: metas, renda futura, simulação)

E toda página de ativo conta a mesma história curta: *o que é → como está → vale a pena? → está barato? → o que pode acontecer → na minha carteira (ou: como entraria nela)*.

---

## 6. Riscos

| Risco | Mitigação |
|---|---|
| Regressão de cálculo durante a unificação | golden tests (`test_reference_portfolio_golden.py`) e caracterização (`test_audit_characterization*.py`) rodam a cada fase; diff do OpenAPI tem de ser zero na Fase R1 |
| Perda de dados | migrations só aditivas; `pg_dump` antes de cada fase; teste de migração sobre cópia restaurada da base real |
| Dois frontends convivendo por muito tempo | cada fase entrega rotas novas **e** redireciona as antigas; a Fase R9 remove o legado com prazo |
| Escopo de IR crescer demais | primeiro apuração mensal e compensação (ações, FII, exterior anual); DARF e informe IRPF depois |
| Integração automática com a B3 | fora do escopo: a API da B3 é licenciada a instituições. A conciliação usa o extrato de **Posição** exportado da Área do Investidor |

---

## 7. Fontes

- Investidor10 — [Gerenciador de carteira](https://investidor10.com.br/conteudo/gerenciador-de-carteira-de-investimentos-investidor10-como-funciona-e-quais-recursos-oferece-121429/), [Plataforma e IRPF](https://investidor10.com.br/conteudo/investidor10-o-que-e-a-plataforma-como-funciona-e-quais-recursos-oferece-aos-investidores-120727/), [Comparador de ativos](https://investidor10.com.br/conteudo/comparador-de-ativos-122067/), [Rastreador](https://investidor10.com.br/conteudo/como-encontrar-acoes-e-fiis-com-o-rastreador-de-ativos-do-investidor10-121695/), [Ferramentas de controle 2026](https://investidor10.com.br/conteudo/as-30-melhores-ferramentas-e-apps-para-controle-de-investimentos-em-2024-103624/)
- Status Invest — [Carteira de investimentos](https://statusinvest.com.br/produtos/carteira-de-investimentos), [iDinheiro: Status Invest](https://www.idinheiro.com.br/investimentos/status-invest/)
- Kinvo — [Renova Invest: análise 2026](https://renovainvest.com.br/?p=19889), [Clube do Valor: apps](https://clubedovalor.com.br/blog/aplicativo-de-investimento-descubra-o-melhor-app-do-mercado/), [Kinvo ou Gorila](https://fintech.com.br/blog/financas-pessoais/kinvo-ou-gorila/)
- Gorila — [Experiência de análise no Íon](https://gorila.com.br/blog/experiencia-de-analise-de-portfolios-ion)
- Simply Wall St — [Como funciona o Snowflake](https://support.simplywall.st/hc/en-us/articles/360001740916-How-does-the-Snowflake-work), [Relatório de exemplo](https://simplywall.st/stocks/us/software/nyse-snow/snowflake)
- Sharesight — [Desempenho](https://www.sharesight.com/uk/investment-portfolio-performance), [Dividendos](https://www.sharesight.com/dividend-tracker), [Relatórios](https://help.sharesight.com/nz/reports)
- Morningstar — [Portfolio X-Ray](https://www.morningstar.com/help-center/portfolio/xray), [Lendo o X-Ray](https://www.morningstar.co.uk/uk/news/131918/reading-the-x-ray-tool.aspx)
- Snowball — [Review 2026](https://wealthypot.com/portfolio-trackers/snowball-analytics/); comparativos [Benzinga](https://www.benzinga.com/money/best-portfolio-tracker), [Capitally](https://www.mycapitally.com/blog/best-portfolio-tracker-for-the-modern-diy-investor)
- B3 / Open Finance — [APIs da Área do Investidor](https://b3.com.br/pt_br/produtos-e-servicos/central-depositaria/canal-com-investidores/integracoes-da-area-do-investidor-apis/), [Genial: consolidação no Brasil](https://www.genialinvestimentos.com.br/artigos/consolidacao-carteira-investimentos-brasil/)
- IR — [Compensação de prejuízo 2026](https://www.nsctotal.com.br/noticias/compensacao-prejuizo-bolsa-regras-calculo-imposto-de-renda-2026), [Gorila: compensar prejuízo](https://gorila.com.br/blog/compensar-prejuizo-em-acoes/)
- UX — [Eleken: fintech UX](https://www.eleken.co/blog-posts/fintech-ux-best-practices), [Lollypop: investment dashboard](https://lollypop.design/blog/2026/may/investment-dashboard-ux-design-guide/?p=25057), [Onething: padrões 2026](https://www.onething.design/post/top-10-fintech-ux-design-practices-2026), [UXPin: divulgação progressiva](https://www.uxpin.com/studio/blog/what-is-progressive-disclosure/)

> Nota de método: a maior parte do material sobre concorrentes é do próprio fornecedor ou de blogs comparativos; recursos e planos devem ser conferidos no produto. Complementa, sem substituir, [docs/research/MARKET_ANALYSIS.md](../research/MARKET_ANALYSIS.md) (2026-10-27).
