# Plano de Implementação em Fases — Financial Control

> Este documento é a **fonte oficial de acompanhamento do projeto**. Cada fase possui entregáveis claros, critérios de aceite, testes de unidade obrigatórios e testes de integração ao final da implementação.
>
> **Legenda de Status:**
> - `[x]` Implementado e validado
> - `[~]` Em andamento
> - `[ ]` Pendente

---

## Resumo Geral de Progresso

| Fase | Escopo | Status | Progresso |
|---|---|---|---|
| **Fase 0** | Planejamento Sistêmico, Governança (`AGENTS.md`, Rules) e Documentação Base | `[x]` Concluída | 100% |
| **Fase 1** | Fundação do Monorepo, Docker Compose (volumes isolados), Ports/Entities, `UnitOfWork`, Repositories e Alembic (`script_00001`) | `[x]` Concluída | 100% |
| **Fase 2** | Domínio Puro (`apps/packages/core`): Posições, Renda Fixa Calculada, Proventos, Consolidação, ARCA e Cerrado Opcional | `[x]` Concluída | 100% |
| **Fase 3** | Provedores de Mercado (`brapi`, `yfinance`, `BCB SGS` CDI/IPCA), Cache Redis e Motor Estatístico/Benchmarks | `[x]` Concluída | 100% |
| **Fase 4** | Backend API (`apps/api` Controllers $\rightarrow$ Handlers $\rightarrow$ Services $\rightarrow$ UoW) e Worker (`apps/worker`) + Testes de Integração | `[x]` Concluída | 100% |
| **Fase 5** | Frontend Web (`apps/web` React + TypeScript): Menu Hambúrguer, Cards Evolução/Projeção e Tabelas Paginadas | `[x]` Concluída | 100% |
| **Fase 6** | Validação End-to-End no Docker Compose, CI/CD GitHub Actions e Publicação no GitHub Privado | `[x]` Concluída (CI sem execução: TD-10) | 100% |
| **Fase 7** | Fundação de Correção: Git, rede de testes de regressão, convenções de unidades (ADR 0006) | `[x]` Concluída | 100% |
| **Fase 8** | Correção dos Motores de Cálculo (CDI, câmbio, renda fixa, analytics, integridade do livro) | `[x]` Concluída | 100% |
| **Fase 9** | Configuração, Segurança, Infraestrutura Docker, Worker e CI | `[x]` Concluída | 100% |
| **Fase 10** | Domínio do Framework Operacional: Política de Investimento, Contas, Ciclo de Vida do Ativo e ARCA com Bandas | `[x]` Concluída | 100% |
| **Fase 11** | Módulo Fundamentalista: Histórico, Screener, Watchlist, Checklists e Valuation por Tipo | `[x]` Implementado | 100% |
| **Fase 12** | Operação: Aporte Executável, Alertas, Importação B3 e Eventos Corporativos | `[x]` Implementado | 100% |
| **Fase 13** | Frontend no Modelo de Referência (ADR 0005 e ADR 0007) | `[x]` Implementado | 100% |
| **Fase 14** | Validação Operacional 100% | `[x]` Implementado | 100% |
| **Fase 15** | Refatoração Estrutural por Módulos (`apps/packages/*`, `apps/worker`, `fincontrol_api`) | `[x]` Concluída | 100% |
| **Fase 16** | Pesquisa e Importação Integradas (Cadastro Único de Ativos) | `[x]` Concluída | 100% |
| **Fase 17** | Arquitetura Unificada de Backend em Camadas por Domínio em `apps/api` (ADR 0009) | `[x]` Concluída | 100% |
| **Fase 18** | Configuração Agêntica e Servidor MCP Pessoal (`/settings/agentic`, `/api/v1/mcp`) | `[x]` Concluída | 100% |
| **Fase 19** | Notificações de Erros de Requisição do Worker (Badge no menu e Log detalhado em Dados de Mercado) | `[x]` Concluída | 100% |
| **Fase 20** | Correções do Worker: brapi e Snapshots Retroativos | `[x]` Implementado | 100% |
| **Fase 21** | Correção do Câmbio nos Formulários de Lançamento | `[x]` Implementado | 100% |
| **Fase 22** | Importação B3: Tesouro Direto, CDB e Fracionário com Dígito | `[x]` Implementado | 100% |
| **Fase 23** | Importação B3: Ignorar Linhas e Vendas sem Saldo | `[x]` Implementado | 100% |
| **Fase 24** | Tributação Regressiva por Ativo e Comparador Tributado × Isento | `[x]` Implementado | 100% |
| **Fase 25** | Confiabilidade do Checklist e Sanidade dos Dados Fundamentalistas | `[x]` Implementado | 100% |
| **Fase 26** | Tesouro a Mercado, Agenda de Proventos e Alertas Internos | `[x]` Implementado | 100% |
| **Fase 27** | Comparador de Ativos | `[x]` Implementado | 100% |
| **Fase 28** | Fatos Relevantes pelos Dados Abertos da CVM | `[x]` Implementado | 100% |
| **Fase 29** | Estatísticas e Saúde da Carteira | `[x]` Implementado | 100% |
| **Fase 30** | Tesouro: Rendimento Pró-Rata por Compra | `[x]` Implementado | 100% |
| **Fase 31** | Melhorias de Interface: Início, Ajudas, Ações e Pesquisa | `[x]` Implementado | 100% |
| **Fase 32** | Legibilidade da Saúde da Carteira e da Estratégia | `[x]` Implementado | 100% |
| **Fase 33** | Simulação de Carteira: Backtesting, Machine Learning e Inferência Bayesiana | `[x]` Implementado | 100% |
| **Fase 34** | Otimização da Composição de Ativos dentro do ARCA | `[ ]` Proposta (aguarda decisões da seção 10 do desenho) | 0% |
| **Fase 35** | Paginação das Tabelas de Pesquisa | `[x]` Implementado | 100% |
| **Fase 36** | Carteiras de Comparação com o Seu Fluxo de Aportes | `[ ]` Proposta (aguarda decisões da seção 11 do desenho) | 0% |
| **Fase 37** | Leitura Empresarial: Narrativa e Padrão Visual | `[x]` Concluída | 100% |
| **Fase 38** | Cotações Persistidas: o Worker Atualiza, as Telas Leem do Banco | `[x]` Concluída | 100% |
| **Fase 39** | Todo Dado Exibido Sai de Tabela Própria | `[x]` Concluída | 100% |
| **Fase 40** | Fatos Relevantes, Patrimônio por Conta, Navegação e Exclusão de Simulações | `[x]` Concluída | 100% |
| **Fase 41** | Simular Carteira: Nova Experiência em Estudos e Capítulos | `[x]` Concluída | 100% |
| **Fase 42** | Previsão Probabilística do Preço dos Ativos (Bayesiana, com Dados da CVM) | `[~]` Em andamento (42.0 a 42.3 feitas; antes das Fases 34 e 36) | 50% |
| **Fase 43** | Garimpo: Achados no Catálogo Inteiro | `[~]` Em andamento (43.0 e 43.1 feitas) | 25% |

> **Roadmap 2026-10-27:** as fases 24–29 seguem as prioridades definidas a partir da [análise de mercado](../research/MARKET_ANALYSIS.md) (seções 6 e 7). Restrição comum: nenhum custo novo (só fontes públicas gratuitas e a infraestrutura atual) e alertas apenas dentro do sistema, sem canal externo.

> **Auditoria 2026-10-24:** a revisão sistêmica (seção *Registro de Achados* abaixo) mostrou que parte das fases 1–6 marcadas como concluídas contém defeitos de cálculo e divergências entre documentação e código (ex.: 6.1 descreve Dockerfiles multi-stage que não existem; 5.x e a rota de Detalhe do Ativo não foram implementadas no frontend). As fases 7–14 corrigem esses pontos; os status das fases anteriores permanecem como histórico.

---

## Fase 0 — Planejamento Sistêmico, Governança e Documentação Base (`[x]` Concluída)

### Itens Implementados
- `[x]` **0.1** Definição das 9 regras mandatórias do projeto em [AGENTS.md](../../AGENTS.md), [CLAUDE.md](../../CLAUDE.md), [GEMINI.md](../../GEMINI.md) e [.agents/rules/project-rules.md](../../.agents/rules/project-rules.md) (incluindo isolamento estrito `Controllers -> Handlers -> Services -> UnitOfWork -> Repositories` e validação via `docker compose build` por fase).
- `[x]` **0.2** Arquitetura sistêmica e UI/UX documentadas em [docs/architecture/OVERVIEW.md](../architecture/OVERVIEW.md) e [docs/architecture/FRONTEND_UI_UX.md](../architecture/FRONTEND_UI_UX.md).
- `[x]` **0.3** ADRs iniciais documentados em `docs/architecture/adr/` (`0001` a `0004`).
- `[x]` **0.4** Especificação das features em `docs/features/` e registro de débitos técnicos em `docs/tech-debt/TECH_DEBT.md`.
- `[x]` **0.5** Configuração base da raiz do workspace (`pyproject.toml`, `.python-version`, `.gitignore`, `.env.example`).

---

## Fase 1 — Fundação do Monorepo, Infraestrutura Docker, Ports, UnitOfWork e Persistência (`[x]` Concluída)

**Objetivo:** Estruturar os pacotes do workspace `uv`, definir entidades imutáveis de domínio e contratos abstratos (`AbstractRepository` e `AbstractUnitOfWork`), configurar SQLAlchemy 2.0 + mappers + `SqlAlchemyUnitOfWork`, criar o sistema de migrations Alembic no formato `script_#####` e configurar o `docker-compose.yml` com volumes nomeados isolados.

### Itens Implementados
- `[x]` **1.1** Criar estrutura de pacotes `apps/packages/core`, `apps/packages/persistence`, `apps/api`, `apps/worker` e `apps/web`.
- `[x]` **1.2** Implementar Entidades Imutáveis de Domínio (`entities.py`), Primitivas Padronizadas de Paginação (`pagination.py`) e Contratos/Ports (`AbstractRepository` em `ports/repositories.py` e `AbstractUnitOfWork` em `ports/unit_of_work.py`).
- `[x]` **1.3** Implementar modelos SQLAlchemy 2.0 (`models.py`) e mapeadores bidirecionais (`mappers.py`) em `apps/packages/persistence` (código 100% em inglês):
  - `AssetModel` (`assets`) $\leftrightarrow$ `AssetEntity`
  - `FixedIncomeTermModel` (`fixed_income_terms`) $\leftrightarrow$ `FixedIncomeTermEntity`
  - `TransactionModel` (`transactions`) $\leftrightarrow$ `TransactionEntity`
  - `EarningModel` (`earnings`) $\leftrightarrow$ `EarningEntity`
  - `ArcaTargetModel` (`arca_targets`) $\leftrightarrow$ `ArcaTargetEntity`
  - `MarketSeriesModel` (`market_series`) $\leftrightarrow$ `MarketSeriesPoint`
  - `PortfolioSnapshotModel` (`portfolio_snapshots`) $\leftrightarrow$ `PortfolioSnapshotEntity`
- `[x]` **1.4** Configurar Alembic em `apps/packages/persistence/migrations/` com `file_template = script_%%(slug)s` e criar a migration inicial `script_00001_initial_schema.py` (com seed das 4 metas ARCA padrão de 25%).
- `[x]` **1.5** Implementar Repositórios SQLAlchemy concretos (`repositories.py`) com paginação, ordenação e filtros padronizados, sem chamadas diretas a `commit()`, e `SqlAlchemyUnitOfWork` (`unit_of_work.py`) gerenciando atomicidade transacional.
- `[x]` **1.6** Criar `docker-compose.yml` com serviços `postgres`, `redis`, `migrate`, `api`, `worker`, `web` e volumes isolados `fincontrol_pgdata` e `fincontrol_redisdata`.
- `[x]` **1.7** **Testes de Unidade (Fase 1):** 6 testes unitários passando (`test_domain_entities.py` e `test_unit_of_work.py`).
- `[x]` **1.8** **Testes de Integração e Build Docker (Fase 1):** 2 testes de integração passando (`test_phase1_integration.py`) validando `upgrade head` / `downgrade base` da migration `script_00001`, paginação/ordenação/filtros via `SqlAlchemyUnitOfWork` e build Docker do serviço `migrate`.

---

## Fase 2 — Domínio Puro (`apps/packages/core`): Posições, Renda Fixa, Proventos, Consolidação, ARCA e Cerrado (`[x]` Concluída)

**Objetivo:** Implementar todas as regras financeiras e de carteira em Python puro (`apps/packages/core`), totalmente independentes de framework web ou banco.

### Itens Implementados
- `[x]` **2.1** Enumerações e entidades de domínio (`ArcaClass`, `AssetType`, `Market`, `TransactionKind`, `EarningKind`, `FixedIncomeIndexer`, `IntraClassStrategy`) e modelos normalizados de mercado (`Quote`, `PricePoint`, `Fundamentals`).
- `[x]` **2.2** Motor de Posições (`portfolio/positions.py`): cálculo de quantidade aberta, preço médio ponderado, custo investido e lucro/prejuízo realizado em vendas (com proteção contra venda a descoberto `InsufficientQuantityError`).
- `[x]` **2.3** Calculadora de Renda Fixa (`portfolio/fixed_income.py`):
  - Acumulação por `% do CDI` (com série diária ou taxa anual equivalente), `IPCA + taxa prefixada`, `Prefixado` e `SELIC`.
  - Cálculo de dias corridos/úteis, IOF regressivo (primeiros 29 dias) e tabela regressiva de IR (22,5%, 20%, 17,5%, 15%), respeitando isenção (`LCI`, `LCA`, `CRI`, `CRA`).
  - Retorno de valor bruto atual, imposto estimado, valor líquido atual, rendimento líquido até o momento e projeção líquida para os próximos 12 meses.
- `[x]` **2.4** Motor de Proventos e Consolidação (`portfolio/consolidation.py`):
  - Agregação de proventos (`DIVIDEND`, `JCP`, `FII_YIELD`, `FIXED_INCOME_COUPON`, `RESTITUTION`) por ativo, classe ARCA e competência mensal.
  - Cálculo de *Yield on Cost* (YoC), estimativa de rendimento até a data (`estimated_yield_to_date_brl`) e projeção de 12 meses (`projected_12m_yield_brl`) adaptadas por `AssetType`.
  - Consolidação de Ganho/Perda Total: `unrealized_pnl + realized_pnl + received_earnings`.
- `[x]` **2.5** Motor ARCA (`arca/allocation.py`): cálculo de alocação atual vs meta, desvios em pontos percentuais, gap financeiro em R$ e distribuição de aporte Nível 1 (sem vendas).
- `[x]` **2.6** Motor do Diagrama do Cerrado Opcional (`cerrado/questions.py`, `cerrado/scoring.py`):
  - Questionários por `AssetType` com regras automáticas baseadas em fundamentos e override manual.
  - Suporte às 3 estratégias intra-classe (`CERRADO`, `MANUAL_WEIGHT`, `EQUAL_WEIGHT`) para que o usuário possa usar ou desativar o Cerrado livremente (`use_cerrado=False`).
  - Conversão do aporte em quantidades inteiras (B3) ou fracionárias (EUA, Cripto, Renda Fixa) com redistribuição de sobras (`plan_contribution`).
- `[x]` **2.7** Módulo de Valuation (`valuation.py`): Preço Justo de Graham, Preço Teto de Bazin (6%), Margem de Segurança e *Earnings Yield*.
- `[x]` **2.8** **Testes de Unidade (Fase 2):** Suite `apps/packages/core/tests/test_phase2_domain.py` validando todos os motores de domínio puro em memória.
- `[x]` **2.9** **Testes de Integração e Build Docker (Fase 2):** Suite `apps/packages/persistence/tests/test_phase2_integration.py` validando `SqlAlchemyUnitOfWork` + `consolidate_portfolio` + `plan_contribution` ponta a ponta sobre o banco migrado com `script_00001` e build Docker validado.

---

## Fase 3 — Provedores de Mercado (`brapi`, `yfinance`, `BCB`), Cache Redis e Analytics (`[x]` Concluída)

**Objetivo:** Conectar o domínio aos dados reais de mercado e indicadores macroeconômicos com cache resiliente e calcular métricas estatísticas e comparativos com benchmarks.

### Itens Implementados
- `[x]` **3.1** Implementar `BrapiProvider` (`market/brapi.py`: cotações, histórico e módulos fundamentalistas para `STOCK_BR`, `FII`, `ETF_BR`, `BDR`).
- `[x]` **3.2** Implementar `YFinanceProvider` (`market/yfinance_provider.py`: ativos internacionais, cripto, câmbio `USDBRL=X`, índices `^BVSP`, `IFIX.SA`, `^GSPC` e fallback automático para B3 `.SA`).
- `[x]` **3.3** Implementar `BcbSgsProvider` (`market/bcb.py`: séries históricas do Banco Central: CDI diário `12`, SELIC `11`, IPCA mensal `433`, com fallback para taxa configurada quando offline).
- `[x]` **3.4** Implementar `CachedMarketGateway` (`market/gateway.py`) com `RedisCache` e `InMemoryCache` (`market/cache.py`), roteamento automático por `Market` e status de frescor da cotação (`LIVE`, `CACHED`, `FALLBACK`, `MANUAL`).
- `[x]` **3.5** Implementar Motor de Estatística e Risco (`analytics.py`):
  - Retorno simples/log, retorno acumulado, **TWR** (*Time-Weighted Return*) e **CAGR**.
  - Volatilidade anualizada, **Sharpe**, **Sortino**, **Max Drawdown** (série e máximo), **Calmar**.
  - **VaR** e **CVaR** (95% histórico e paramétrico).
  - **Beta**, **Alpha de Jensen** e **Matriz de Correlação** contra **IBOV**, **IFIX**, **S&P 500**, **CDI** e **IPCA** (ganho real).
- `[x]` **3.6** **Testes de Unidade (Fase 3):** Suite `apps/packages/core/tests/test_phase3_market_and_analytics.py` validando provedores com `httpx.MockTransport` / mocks determinísticos e todas as métricas estatísticas.
- `[x]` **3.7** **Testes de Integração e Build Docker (Fase 3):** Suite `apps/packages/persistence/tests/test_phase3_integration.py` validando `CachedMarketGateway` + `SqlAlchemyUnitOfWork` (`uow.market_series`, `uow.snapshots`) + `analytics.py` e build Docker validado.

---

## Fase 4 — Backend API (`apps/api`) e Worker (`apps/worker`) (`[x]` Concluída)

**Objetivo:** Expor todas as capacidades via REST API em FastAPI e automatizar a atualização de cotações, séries do BCB e snapshots diários no worker, respeitando o isolamento estrito `Controllers -> Handlers -> Services -> UnitOfWork -> Repositories`.

### Itens Implementados
- `[x]` **4.1** Estruturar `apps/api` (`config.py`, `dependencies.py`, `main.py`, tratamento padronizado de erros, CORS, `/api/v1/health`).
- `[x]` **4.2** Endpoints e Handlers de Ativos e Renda Fixa (`/api/v1/assets`, `/api/v1/assets/{id}/cerrado`, termos de renda fixa, configuração do Cerrado opcional / peso manual e paginação padronizada).
- `[x]` **4.3** Endpoints e Handlers de Transações (`/api/v1/transactions` com validação anti-venda a descoberto) e Proventos (`/api/v1/earnings`).
- `[x]` **4.4** Endpoints, Handlers e `PortfolioApplicationService` de Carteira, ARCA e Consolidação:
  - `GET /api/v1/portfolio` (posições valorizadas, valor investido, estimativa de rendimento por tipo, projeção 12m, proventos, alocação ARCA).
  - `GET /api/v1/portfolio/consolidated` (consolidação de ganhos/perdas realizados, não realizados e proventos por ativo, classe e período).
  - `POST /api/v1/portfolio/contribution` (simulador de aporte em 2 níveis com suporte a Cerrado ligado/desligado).
- `[x]` **4.5** Endpoints de Análise e Benchmarks:
  - `GET /api/v1/assets/{id}/analysis` (histórico, fundamentos, valuation Graham/Bazin, métricas de risco vs benchmark, questionário Cerrado).
  - `GET /api/v1/portfolio/analytics` (TWR, Sharpe, Sortino, Drawdown, VaR, correlação e curva comparativa contra **IBOV, IFIX, S&P 500, CDI e IPCA**).
  - `GET/PUT /api/v1/settings/arca-targets`.
- `[x]` **4.6** Implementar `apps/worker` (`jobs.py` e `scheduler.py` para aquecimento de cotações, sincronização CDI/SELIC/IPCA/IBOV/IFIX/S&P500 e gravação de `PORTFOLIO_SNAPSHOTS` via `SqlAlchemyUnitOfWork`).
- `[x]` **4.7** **Testes de Unidade (Fase 4):** Suite `apps/api/tests/test_api_unit.py` (incluindo verificação estática da Regra #8 de isolamento das controllers) e `apps/worker/tests/test_worker_jobs.py`.
- `[x]` **4.8** **Testes de Integração e Build Docker (Fase 4):** Suite `apps/api/tests/test_api_integration.py` (`TestClient` exercitando todos os endpoints REST + banco + migration `script_00001`) e build Docker validado (`financial-control-migrate`, `financial-control-api`, `financial-control-worker`).

---

## Fase 5 — Frontend Web (`apps/web` React + TypeScript) (`[x]` Concluída)

**Objetivo:** Construir a interface web responsiva para gestão completa da carteira com paleta Azul, Branco e Cinza, menu hambúrguer sem barra de atalhos no header, cards com evolução e projeção 12m, e paginação/ordenação/filtros padronizados.

### Itens Implementados
- `[x]` **5.1** Scaffold `apps/web` (`package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/styles/theme.css`, `src/types/api.ts`, `src/utils/formatters.ts`, `src/services/apiClient.ts`).
- `[x]` **5.2** **Dashboard**: cards executivos (`EvolutionProjectionCard.tsx` com Capital Investido, Patrimônio Atual, Estimativa de Rendimento, Ganho/Perda Consolidado e Proventos + projeção 12 meses), alocação ARCA (Atual vs Meta) e comparativo com **CDI, IPCA, IBOV, IFIX e S&P 500**.
- `[x]` **5.3** **Carteira e Consolidação**: tabela padronizada (`StandardDataTable.tsx`) com filtro textual, filtro por classe ARCA, ordenação por coluna e paginação server-side exibindo quantidade, PM, valor investido, valor atual, estimativa de rendimento até o momento (adaptada ao tipo do ativo), proventos, lucro realizado e resultado consolidado; modal de cadastro de ativo (incluindo parâmetros de Renda Fixa CDI/IPCA+/Pré).
- `[x]` **5.4** **Lançamentos e Proventos**: registro e listagem paginada e filtrável de compras, vendas e recebimento de dividendos/JCP/rendimentos de FII.
- `[x]` **5.5** **Detalhe do Ativo e Cerrado Opcional**: visualização e configuração do Diagrama do Cerrado (com chave para ativar/desativar ou definir peso manual).
- `[x]` **5.6** **Simulador de Aporte**: input de valor do aporte, seletor de estratégia intra-classe (`CERRADO`, `MANUAL_WEIGHT`, `EQUAL_WEIGHT`), tabela de compras recomendadas e resumo ARCA antes/depois.
- `[x]` **5.7** **Análises e Configurações**: métricas de risco/retorno (TWR, CAGR, Volatilidade, Sharpe, Sortino, Max Drawdown, VaR, CVaR), comparativos com benchmarks e metas ARCA.
- `[x]` **5.8** **Testes de Unidade, Integração e Build Docker Frontend (Fase 5):** Testes Vitest + Testing Library (`src/test/App.test.tsx`: 4/4 passando), `npm run build` (`tsc && vite build`) e imagem Docker `financial-control-web` validada via `docker compose build`.

---

## Fase 6 — Docker Compose End-to-End, CI/CD e GitHub (`[x]` Concluída)

**Objetivo:** Validar toda a solução rodando em containers com volumes isolados, configurar pipeline de integração contínua e publicar no repositório GitHub privado.

### Itens Implementados
- `[x]` **6.1** Dockerfiles multi-stage (`apps/api/Dockerfile`, `apps/worker/Dockerfile`, `apps/web/Dockerfile` com `apps/web/nginx.conf` fazendo proxy para `/api`) e `.dockerignore`.
- `[x]` **6.2** Pipeline `.github/workflows/ci.yml` executando lint (`ruff`, `tsc`), testes de unidade, testes de integração (com validação das migrations `script_#####`) e `docker compose build`.
- `[x]` **6.3** **Teste de Integração End-to-End (Fase 6):** `docker compose up --build -d` validado com execução automática do `migrate` (`script_00001`), sincronização real do `worker` com o BCB SGS (CDI, SELIC, IPCA) e benchmarks, healthcheck da API (`:8000` e proxy `:8080`), resposta `200 OK` do frontend e persistência de dados nos volumes isolados `fincontrol_pgdata` e `fincontrol_redisdata` após `docker compose restart`.

- `[x]` **6.4** Repositório privado `Angelicogfa/financial-control` no GitHub com commits semânticos em inglês e PRs mesclados na `main`. Os jobs do Actions não iniciam por falta de crédito da conta (TD-10); cada PR é validado localmente.

---

## Registro de Achados da Auditoria Sistêmica (2026-10-24)

Cada item das fases 7–14 referencia um ou mais IDs abaixo. Um achado só é encerrado quando o item correspondente tiver teste de regressão passando.

### Críticos — valores exibidos incorretos
| ID | Achado | Local |
|---|---|---|
| **C-01** | Série diária do CDI tratada como fração quando o valor é ≤ 0,05 (CDI < ~13,4% a.a.), inflando a curva em ~100x nesses dias | `portfolio/fixed_income.py` (`_compound_factor`) |
| **C-02** | Custo, lucro realizado e proventos em USD convertidos pelo câmbio atual; `total_cost_brl` calculado e ignorado; ganho cambial some | `portfolio/consolidation.py` |
| **C-03** | Analytics usa retornos do IBOV como "PORTFOLIO" quando há < 2 snapshots | `services/portfolio_service.py` |
| **C-04** | Venda de renda fixa abate o valor de mercado da venda do principal (deveria abater o principal proporcional) | `portfolio/fixed_income.py` |

### Importantes — cálculo, contrato e robustez
| ID | Achado |
|---|---|
| **I-01** | IPCA+ usa taxa anual fixa em vez da série mensal 433; SELIC usa série do CDI; dias úteis sem feriados; projeção 12m com datas fixas 2026→2027 |
| **I-02** | Escalas inferidas por heurística: `contracted_rate` (`> 5`, `> 1`), `as_fraction` (`> 1,5`), `debtToEquity` (`> 5`) |
| **I-03** | Worker sincroniza apenas 365 dias de CDI/SELIC/IPCA; títulos anteriores perdem acumulação sem aviso |
| **I-04** | Excluir um BUY não revalida vendas posteriores; um livro inválido faz `GET /portfolio` inteiro retornar 400; não existe edição de lançamentos |
| **I-05** | `LookupError` (inclui `KeyError`) mapeado para 404 e qualquer `ValueError` para 400, mascarando bugs internos |
| **I-06** | Frontend engole erros da API e exibe carteira vazia (R$ 0) |
| **I-07** | Regra de aporte duplicada no frontend (`computeLocalContributionPlan`); simulação sem debounce; cada request consulta provedores ativo a ativo sequencialmente |
| **I-08** | Variáveis do `.env` não lidas: `QUOTE_CACHE_TTL`, `FUNDAMENTALS_CACHE_TTL`, `HISTORY_CACHE_TTL`, `RISK_FREE_RATE`, `DEFAULT_ANNUAL_IPCA`, `QUOTE_REFRESH_MINUTES`, `SNAPSHOT_CRON_*`, `BCB_SGS_BASE_URL`, `TZ` |
| **I-09** | TWR ignora proventos; `net_flow` só conta lançamentos do próprio dia; Beta/correlação alinhados pela cauda do array e não por data |
| **I-10** | Regra de liquidez do Cerrado compara volume em quantidade com limite em R$ |
| **I-11** | Premissas de projeção fixas no código (8%, 10%, 8,5%, 82,5%) |

### ARCA
| ID | Achado |
|---|---|
| **A-01** | Sem banda de tolerância por classe |
| **A-02** | Exposição acoplada ao tipo (ex.: `IVVB11` cai em Ações BR, `IMAB11` em Ações BR) |
| **A-03** | Sem forma de excluir a reserva de emergência da classe Caixa |
| **A-04** | Sobra de arredondamento não redistribuída entre classes; override `MANUAL_WEIGHT` usa pesos-alvo calculados em vez de `custom_class_weight` |

### Fundamentalista
| ID | Achado |
|---|---|
| **F-01** | Sem universo de ativos, screener ou watchlist: análise só existe para ativos já cadastrados |
| **F-02** | Fundamentos pontuais (TTM) usados em perguntas históricas ("ROE historicamente > 5%") |
| **F-03** | Regras não setoriais: ETF responde checklist de empresa, Dív./EBITDA aplicado a bancos, Graham aplicado a FII |
| **F-04** | Score frágil (1 resposta "sim" = APTO); respostas sem data, origem histórica ou versão do checklist |
| **F-05** | Endpoint `/assets/{id}/analysis` sem tela correspondente |

### Dados e desempenho
| ID | Achado |
|---|---|
| **D-01** | `ticker` único global; sem contas/corretoras; dois CDBs exigem tickers inventados |
| **D-02** | Valores monetários em `Float` nos snapshots |
| **D-03** | Sem importação da B3; eventos corporativos manuais (TD-03) |
| **D-04** | Paginação sem critério de desempate (páginas instáveis) |
| **D-05** | Cotações/fundamentos buscados sequencialmente por request |

### Operação, segurança e processo
| ID | Achado |
|---|---|
| **O-01** | Dockerfiles não multi-stage, executando como root; imagens de API e worker com código uma da outra; API sem healthcheck |
| **O-02** | Build do web usa `npm install` sem copiar `package-lock.json` |
| **O-03** | Postgres e Redis expostos no host com credenciais padrão; Redis sem senha; API sem autenticação (TD-01) |
| **O-04** | Pasta não versionada em Git; CI usa `uv` "latest" e não sobe a stack |
| **O-05** | 28 testes Python e 4 no frontend; nenhum cobre os achados acima |
| **O-06** | `App.tsx` monolítico (~1.700 linhas, 30+ `useState`), sem router, sem biblioteca de gráficos |
| **O-07** | Documentação diverge da implementação |

---

## Princípios de Execução das Fases 7–14

1. **Teste vermelho primeiro:** todo achado `C-*`/`I-*` começa com um teste que reproduz o defeito; a correção só é aceita com o teste verde.
2. **Regras do `AGENTS.md` valem integralmente:** código em inglês, unit tests por componente, integração ao final de cada fase (`uv run pytest`), `docker compose build` por fase, migrations `script_#####`.
3. **Commit por item** (Conventional Commits em inglês) a partir da Fase 7.
4. **Sem premissa no código:** toda constante de negócio vem da `InvestmentPolicy` ou de settings (ADR 0005).
5. **Dados derivados são recalculáveis:** snapshots e séries podem ser reconstruídos por job de backfill; correções de cálculo terminam com o reprocessamento.

---

## Fase 7 — Fundação de Correção (`[x]` Concluída)

**Objetivo:** criar a rede de segurança para refatorar sem regressão.

- `[x]` **7.1** (O-04) `git init`, `.gitattributes` (LF), commit baseline do estado atual e branch `main`; trabalho da fase na branch `fix/phase-7-foundation`. O push para o GitHub (item 6.4) só ocorre com confirmação explícita do usuário.
- `[x]` **7.2** (O-05) Testes de caracterização que reproduzem C-01..C-04, I-01..I-05, I-09, I-10, A-04 (marcados `xfail(strict=True, raises=...)` até a correção, para que a correção os "desmarque"): `apps/packages/core/tests/test_audit_characterization.py`, `apps/api/tests/test_audit_characterization_api.py`, `apps/worker/tests/test_audit_characterization_worker.py` (23 casos).
- `[x]` **7.3** (I-02) **ADR 0006 — Convenções de unidades:** taxas sempre como fração decimal (`0.065` = 6,5%); percentual de indexador como multiplicador (`1.10` = 110% do CDI); séries do BCB armazenadas com unidade explícita; dinheiro em `Decimal`/`Numeric` em persistência e fronteiras de API; `float` apenas em estatística.
- `[x]` **7.4** Carteira de referência (ação BR, FII, ETF internacional em USD, cripto, CDB CDI, LCI, Tesouro IPCA+) em `apps/packages/core/tests/golden/reference_portfolio.json`, exposta pelas fixtures de `apps/packages/core/tests/conftest.py`. Os valores esperados (`reference_portfolio_expected.csv`, 53 linhas) são gerados por `build_reference_golden.py`, cálculo independente só com a biblioteca padrão (substitui a planilha); 18 linhas afetadas por C-01, C-02 e I-01 estão em `xfail` estrito.
- `[x]` **7.5** Cobertura no CI com `pytest-cov` e piso inicial (`apps/packages/core` ≥ 85%, hoje 87% só com testes em memória após `test_market_gateway_and_cache.py`), elevado ao final da Fase 14.

**Aceite:** baseline commitado; suíte roda com os `xfail` listados; ADR 0006 aceito.

**Validação (2026-10-24):** `uv run pytest` → 84 passed, 41 xfailed; `ruff check` limpo; `docker compose build` dos serviços `migrate`, `api`, `worker` e `web` concluído.

---

## Fase 8 — Correção dos Motores de Cálculo (`[x]` Concluída)

**Objetivo:** todos os números exibidos corretos e auditáveis.

### Séries e unidades
- `[x]` **8.1** (C-01, I-02) `market_series` ganha coluna `unit` (`PERCENT_PER_DAY`, `PERCENT_PER_MONTH`, `PRICE`, `INDEX_POINTS`) — migration `script_00002_market_series_unit.py` marcando CDI/SELIC/IPCA existentes. `BcbSgsProvider` devolve pontos com unidade; o domínio converte explicitamente para fração. Remover toda heurística de escala de `_compound_factor`.
- `[x]` **8.2** (I-02) `contracted_rate` com semântica fixa por indexador (ADR 0006): validação de faixa na API (CDI/SELIC: 0,5–3,0; PRE/IPCA: 0–0,5) e migration `script_00003_normalize_contracted_rate.py` convertendo dados existentes. Remover `as_fraction` genérico: cada adaptador de provedor declara a unidade de cada campo.
- `[x]` **8.3** (I-03) Sincronização BCB incremental desde a menor data entre `issue_date` de renda fixa e primeira transação (com teto de 10 anos), detecção de lacunas e reprocessamento. Endpoint de status de frescor por série. Implementado com `date_range()` no repositório e `GET /api/v1/market/series-status` (último ponto, defasagem e dias úteis faltantes).

### Renda fixa
- `[x]` **8.4** (C-04) Venda de renda fixa: FIFO por lote, abatendo o principal proporcional ao valor bruto do lote (`principal × valor_vendido / valor_bruto_lote`); IR/IOF da venda e lucro realizado de RF calculados por lote.
- `[x]` **8.5** (I-01) IPCA+ pela série mensal 433 com pró-rata do mês corrente (último IPCA conhecido ou projeção da política); SELIC pela série 11; calendário de feriados nacionais (fixos + móveis via Páscoa) em `apps/packages/core/calendar.py`; projeção 12m relativa a `as_of_date`. Convenção: IPCA do mês aplicado pró-rata por dias úteis do mês; mês sem índice usa a taxa anual de fallback e reduz `curve_coverage`. Projeção = variação do valor líquido em 252 dias úteis (ou até o vencimento), incluindo a mudança de faixa do IR.

### Consolidação e câmbio
- `[x]` **8.6** (C-02) Custo em BRL pelo câmbio de cada compra (`total_cost_brl`), lucro realizado em BRL pelo câmbio da venda, valor atual pelo câmbio atual; novo campo `fx_pnl_brl` separando efeito câmbio de efeito preço. Proventos em moeda estrangeira ganham `fx_rate` (migration `script_00004_earnings_fx_rate.py`, default 1 para BRL e câmbio histórico do dia para USD via backfill). Lançamentos e proventos de ativos em moeda estrangeira passam a exigir câmbio (`400 FX_RATE_REQUIRED`).
- `[x]` **8.7** (I-11) Projeções 12m lidas da `ValuationPolicy` (Fase 10) — até lá, de settings; resposta da API inclui as premissas usadas. Premissas em `ProjectionAssumptions`, devolvidas em `projection_assumptions` (desde a Fase 10 vivem na `ValuationPolicy`; as variáveis `PROJECTION_*` foram removidas).

### Analytics
- `[x]` **8.8** (C-03) Remover o fallback para IBOV. Sem histórico suficiente, a API devolve `status: "INSUFFICIENT_HISTORY"` com `available_points`; a UI mostra estado vazio explicativo.
- `[x]` **8.9** (C-03, I-09) Job de **backfill de snapshots** que reconstrói a série diária desde a primeira transação usando histórico de preços, câmbio histórico e curva de RF; snapshots só em dias úteis B3. `backfill_snapshots_job` roda na inicialização do worker; o snapshot diário só roda em dias úteis.
- `[x]` **8.10** (I-09) TWR com proventos como retorno (`r_t = (V_t − V_{t−1} − CF_t + D_t) / V_{t−1}`); `net_flow` derivado do livro entre snapshots consecutivos; Beta, Alpha e correlação com junção por data (interseção de calendários).
- `[x]` **8.11** (I-10) Liquidez = volume médio × preço (volume financeiro).

### Integridade e contrato
- `[x]` **8.12** (I-04) Validação do livro inteiro em criação, edição e exclusão de lançamentos (simula o livro resultante antes de persistir). Novo `PUT /transactions/{id}` e `PUT /earnings/{id}`. Exclusões/edições que quebram o livro retornam `409 LEDGER_CONFLICT`.
- `[x]` **8.13** (I-04) Consolidação tolerante: ativo com livro inválido aparece com `ledger_status: "INVALID"` e mensagem, sem derrubar a carteira.
- `[x]` **8.14** (I-05) Hierarquia de exceções de domínio (`DomainError`, `NotFoundError`, `ValidationError`, `ConflictError`) em `apps/packages/core/errors.py`; handlers mapeiam só essas; demais exceções viram 500 com `request_id` e log.
- `[x]` **8.15** (A-04) Override `MANUAL_WEIGHT` usa `custom_class_weight`; sobra de arredondamento redistribuída entre classes por ordem de déficit.
- `[x]` **8.16** (D-02, D-04) Colunas monetárias de `portfolio_snapshots` para `Numeric(20, 2)` (`script_00005_snapshot_numeric.py`); `id` como desempate em toda ordenação paginada. O domínio mantém `float` nos snapshots (série estatística derivada, exceção registrada na ADR 0006); o repositório arredonda para centavos.
- `[x]` **8.17** Reprocessamento: comando `uv run python -m fincontrol_worker.rebuild` que ressincroniza séries e reconstrói snapshots após as correções. Também reprecifica lançamentos e proventos em USD gravados com `fx_rate = 1` usando o USD/BRL histórico. **Ação pendente na base real:** rodar `docker compose run --rm worker python -m fincontrol_worker.rebuild` após aplicar as migrations.

**Aceite:** todos os `xfail` da 7.2 passam; carteira de referência (7.4) bate com a planilha golden em ±R$ 0,01; integração + `docker compose build` verdes.

**Validação (2026-10-24):** os 23 testes de caracterização e as 53 linhas da carteira de referência passam sem `xfail`; `uv run pytest` → 202 passed (cobertura: `apps/packages/core` 88,6% só com testes em memória, backend total 93%); `npm test` 7/7 e `npm run build`; migrations `script_00002`–`script_00005` aplicadas com dados legados e revertidas em PostgreSQL 16 descartável; `docker compose build` dos 4 serviços concluído.

**Testes ajustados durante a fase (expectativas que codificavam defeitos):** `total_invested_brl` da fase 2 (17200 → 17000, C-02); projeção da caracterização I-01 (IR de 15% fixo → faixa regressiva no horizonte); dados do teste de beta I-09 (movimento de 50% em 03/01 → 0%, para manter beta 1 com composição por intervalo); taxas contratadas dos testes antigos convertidas para a escala da ADR 0006.

---

## Fase 9 — Configuração, Segurança, Infraestrutura e CI (`[x]` Concluída)

- `[x]` **9.1** (I-08) Pacote `apps/packages/config` (`fincontrol_config`) com `pydantic-settings` compartilhado por API e worker; nomes idênticos ao `.env.example`; teste que falha se existir variável no `.env.example` sem campo correspondente (e vice-versa). Também corrigiu `BCB_SGS_BASE_URL` (o valor antigo gerava URL inválida) e trouxe `fincontrol_core.market.factory` para montar o gateway igual na API e no worker.
- `[x]` **9.2** (O-01) Dockerfiles multi-stage (builder com `uv sync --frozen`, runtime slim), usuário não-root, imagem da API só com `core`+`persistence`+`config`+`api`, imagem do worker só com o que usa; `HEALTHCHECK` em API e web. `uv` 0.12.7 fixado no builder; uid 10001 no runtime; a imagem do worker não contém `fincontrol_api` e vice-versa.
- `[x]` **9.3** (O-02) Web: copiar `package-lock.json` e usar `npm ci`.
- `[x]` **9.4** (O-03) Postgres e Redis sem portas publicadas por padrão (acesso de desenvolvimento pelo `docker-compose.yml`, vinculado a `127.0.0.1`; a produção é o `docker-compose.prod.yml`); Redis com `requirepass`; `.env.example` com placeholders `change-me`. Nomes de volume (`PGDATA_VOLUME`, `REDISDATA_VOLUME`) e arquivo de env dos apps (`APP_ENV_FILE`) são configuráveis para rodar uma segunda stack isolada; `container_name` fixo removido.
- `[x]` **9.5** (O-03, TD-01) Autenticação single-user: credencial definida no `.env` (hash Argon2), login emite JWT em cookie `httpOnly`/`SameSite=Strict`; todas as rotas exceto `/health` protegidas. Estrutura preparada para `users` futuramente. `/ready` também fica aberto. CLI `python -m fincontrol_api hash-password|new-secret` imprime linhas prontas (com aspas simples, por causa do `$` do Argon2). Placeholders `change-me` contam como não configurado (503 `AUTH_NOT_CONFIGURED`). Web ganhou tela de login e volta para ela em qualquer 401.
- `[x]` **9.6** Observabilidade: logs estruturados JSON com `request_id`; `/health` (liveness) e `/ready` (DB, Redis, migrations em `head`). `/ready` responde 503 sem banco ou fora do `head` e `degraded` quando só o cache cai; respostas 500 trazem o `request_id`.
- `[x]` **9.7** Worker: agenda e fuso lidos de settings; lock distribuído no Redis por job; retries com backoff; tabela `job_runs` (`script_00006_job_runs.py`) com início, fim, status e contagens — base do indicador de frescor da UI. Endpoint `GET /api/v1/market/job-runs`. Novo job `ensure_series_coverage` (no intervalo das cotações) completa o histórico do BCB assim que entra uma posição mais antiga — falha revelada pelo smoke.
- `[x]` **9.8** (D-05, I-07) Busca de cotações/fundamentos em lote e concorrente (`httpx.AsyncClient` ou pool de threads limitado), com timeout global por request; API lê preferencialmente do cache aquecido pelo worker. Implementado com pool de threads limitado (`MARKET_FETCH_WORKERS`) e prazo global (`MARKET_FETCH_TIMEOUT_SECONDS`).
- `[x]` **9.9** (O-04) CI: versão de `uv` fixada, `uv sync --frozen`, `npm ci`, ESLint + `tsc --noEmit`, cobertura, e job de *smoke* que sobe a stack com `docker compose up -d --wait` e valida `/ready` e a página web. **Ajuste:** sem minutos do GitHub Actions, o portão de qualidade é local — `scripts/check.sh` (`--fast` sem Docker, `--smoke` com teste ponta a ponta isolado em `scripts/smoke.sh`) e hook de pre-push via `scripts/install-hooks.sh`. O `ci.yml` só chama o mesmo script, para quando houver minutos.

**Aceite:** stack sobe do zero com `cp .env.example .env && docker compose up -d --wait`; nenhuma porta de banco exposta; rotas exigem login; portão de qualidade local (`scripts/check.sh --smoke`) verde.

**Validação (2026-10-24):** `scripts/check.sh --smoke` → ruff e formatação limpos; `apps/packages/core` 88,3% de cobertura só com testes em memória; 230 testes de backend (cobertura total 94%); web com ESLint sem avisos, `tsc`, 10 testes e build; imagens buildadas; stack isolada `fincontrol-smoke` subiu do zero com `/ready` = ready (migrations em `script_00006`, cache Redis), 401 sem sessão, login, cadastro de CDB e compra, cabeçalhos de segurança, containers sem root, Redis exigindo senha e apenas a porta do web publicada. A stack em uso e os volumes `fincontrol_pgdata`/`fincontrol_redisdata` não foram tocados.

**Ação pendente na base real (antes de subir esta versão):** o `.env` em uso precisa das novas variáveis — `REDIS_PASSWORD` (e `REDIS_URL` com `:senha@`), `AUTH_PASSWORD_HASH`, `AUTH_JWT_SECRET` e as demais listadas em `.env.example`. Manter `POSTGRES_PASSWORD` igual ao usado na criação do volume.

---

## Fase 10 — Domínio do Framework Operacional (`[x]` Concluída)

**Objetivo:** implementar a ADR 0005 no backend.

- `[x]` **10.1** Agregado `InvestmentPolicy` (`ArcaPolicy`, `EligibilityPolicy`, `ValuationPolicy`) em `apps/packages/core/policy/`; tabela `investment_policy` versionada (`script_00007_investment_policy.py`) migrando `arca_targets`; endpoints `GET/PUT /api/v1/policy` com validação (metas somam 100%, bandas ≥ 0). Tabela `investment_policies` é append-only (cada alteração cria uma versão); `GET /api/v1/policy/versions` lista o histórico. `/settings/arca-targets` virou fachada que cria nova versão mantendo bandas e demais regras. As premissas de projeção saíram do `.env` (`PROJECTION_*` removidas) e passaram para `ValuationPolicy`.
- `[x]` **10.2** (A-01) Bandas de tolerância por classe; `compute_allocation` devolve `band_status` (`WITHIN`, `BELOW`, `ABOVE`); aporte prioriza classes abaixo da banda. `distribute_with_bands` leva as classes abaixo da banda até a meta antes de distribuir o restante pelas metas.
- `[x]` **10.3** (A-02) Campo `exposure_class` separado de `asset_type`/mercado de listagem; sugestão automática para ETFs conhecidos (lista curada em `apps/packages/core/catalog/etf_exposure.py`) e confirmação no cadastro. **Desvio:** não foi criada coluna `exposure_class`; o próprio `arca_class` é a classe de exposição e uma segunda coluna duplicaria a informação. O problema (padrão pelo local de listagem) foi resolvido com o catálogo e `GET /api/v1/assets/classification`, usado no cadastro quando a classe não é informada. A confirmação visual fica para a Fase 13.
- `[x]` **10.4** (A-03) Campo `purpose` (`ARCA`, `EMERGENCY_RESERVE`, `OTHER`); apenas `ARCA` entra na alocação e no aporte; reserva aparece separada no Início e na Carteira. Migration `script_00008_asset_purpose.py`; relatório traz `value_by_purpose_brl` (patrimônio total inclui a reserva; alocação e aporte só o ARCA).
- `[x]` **10.5** (D-01) Entidade `accounts` (corretora/banco/custódia) e `account_id` em transações e proventos (`script_00008_accounts.py`, conta "Principal" para dados existentes); unicidade de `ticker` apenas para ativos negociados em bolsa; renda fixa identificada por código gerado + emissor + vencimento. Migration renumerada para `script_00009_accounts.py`. Endpoints `/api/v1/accounts`; `account_id` em lançamentos, proventos e no filtro de `/portfolio`. **Desvio:** a unicidade de `ticker` continua valendo para todos, mas renda fixa e caixa podem omitir o ticker e recebem código gerado (`CDB-BANCOINTER-20270115`, `-2`…), o que resolve os tickers inventados.
- `[x]` **10.6** Ciclo de vida `WATCHLIST → ELIGIBLE → HELD → REVIEW → ARCHIVED` calculado por `AssetLifecycleService` a partir da política, da posição e da avaliação fundamentalista; exposto em todas as respostas de ativo. Regras em `fincontrol_core.policy.lifecycle`; elegibilidade opcional por padrão (ativo nunca avaliado é elegível, ADR 0002) com `require_evaluation`, `min_score` e `min_coverage_pct` na política. Só `ELIGIBLE` e `HELD` recebem aporte; livro inválido aparece como `REVIEW`.

**Aceite:** carteira de referência consolidada com bandas, exposição, reserva separada e status de ciclo de vida corretos; testes de unidade e integração verdes.

**Validação (2026-10-25):** `scripts/check.sh --smoke` → 279 testes de backend (cobertura total 94%, `apps/packages/core` 88,5% só em memória), web com ESLint, `tsc`, 10 testes e build; stack isolada do zero com `/ready` = ready em `script_00009`. Migrations `script_00007`–`script_00009` aplicadas e revertidas em PostgreSQL 16 descartável com dados legados (metas ARCA personalizadas viraram a versão 1 da política; lançamentos e proventos foram para a conta Principal; sequência de `accounts` correta). O primeiro smoke revelou um import circular (`policy` ↔ `consolidation`) que a suíte não pegava; corrigido e coberto por `test_import_graph.py`, que importa cada módulo com o cache limpo.

---

## Fase 11 — Módulo Fundamentalista (`[x]` Implementado)

- `[x]` **11.1** (F-02) Tabela `fundamental_snapshots` por ticker (data de referência, período `ANNUAL`/`TTM`, métricas em JSON) — `script_00010_fundamental_snapshots.py`; adaptadores de demonstrativos anuais brapi (`incomeStatementHistory`, `balanceSheetHistory`, `cashflowHistory`) e Yahoo (`income_stmt`, `balance_sheet`, `cashflow`) com fallback e cache no gateway; job semanal `refresh_fundamentals` para carteira + watchlist.
- `[x]` **11.2** (F-02) `HistoricalMetrics`: ROE médio, CAGR de receita e lucro, anos com lucro, regularidade de proventos e payout médio na janela de 5 anos; regras históricas exigem ao menos 3 exercícios e caem para os indicadores TTM com evidência explícita.
- `[x]` **11.3** (F-03) Checklist v2 por perfil (`STOCK`, `BANK`, `FII_BRICK`, `FII_PAPER`, `ETF`, `INTL_STOCK`, `CRYPTO`, `FIXED_INCOME`), perfil padrão por tipo e escolha manual no ativo; respostas `YES`/`NO`/`NA`; respostas automáticas com evidência textual.
- `[x]` **11.4** (F-04) Tabelas `checklist_answers` (append-only: valor, origem, evidência, `answered_at`, versão) e `checklist_evaluations` (histórico do score) — `script_00011_checklist_answers.py`, migrando `assets.cerrado_answers` (com downgrade); `normalized_score` (−1 a 1) e `coverage_pct` sobre perguntas aplicáveis; avaliação registrada ao responder e semanalmente pelo job `record_checklist_evaluations` (só quando o resultado muda); rota `PUT /assets/{id}/checklist` (a rota `/cerrado` fica como alias obsoleto até a Fase 13).
- `[x]` **11.5** (F-03) Valuation por perfil: ações (Graham, Bazin, P/L, EV/EBITDA), bancos (Bazin, P/VP justificado por ROE/custo de capital, P/VP), FII (P/VP, DY e spread sobre o juro real de referência NTN-B), internacionais (Graham, P/L, EV/EBITDA); ETF, cripto e renda fixa marcados como não aplicáveis; limites, juro real de referência e margem de segurança mínima na `ValuationPolicy`.
- `[x]` **11.6** (F-01) `instrument_catalog` (`script_00012_instrument_catalog.py`) sincronizado em dias úteis via `GET /quote/list` da brapi (paginado; fundos separados em FII e ETF), preservando o catálogo anterior se a fonte falhar.
- `[x]` **11.7** (F-01) `GET /api/v1/research/screener`: filtros de catálogo (tipo, classe ARCA, setor, texto, liquidez, valor de mercado, excluir cadastrados) e de indicadores (P/L, P/VP, DY, ROE) buscados só para até 120 candidatos (cache do gateway); atalho `below_band` para as classes abaixo da banda; cada resultado traz veredito de valuation e status de ciclo de vida quando cadastrado.
- `[x]` **11.8** (F-01) Watchlist: `GET/POST/DELETE /api/v1/research/watchlist` — cria o ativo a partir do catálogo (ou com tipo informado), lista ativos sem posição com checklist e valuation, impede remover ativo com posição (409) e apaga de vez quem nunca teve lançamentos.
- `[x]` **11.9** (F-05) `GET /api/v1/assets/{id}/analysis` reformulado: posição, fundamentos atuais, histórico anual e métricas históricas, valuation por perfil, checklist com evidências, histórico do score e das respostas, risco vs benchmark da classe.

**Aceite:** `apps/api/tests/test_research_flow.py` com respostas gravadas da brapi: catálogo → screener → watchlist → demonstrativos → checklist BANK → análise → elegível → recebe aporte → remoção. **Validação:** `scripts/check.sh --smoke` verde (ver notas da fase).

---

## Fase 12 — Operação: Aporte, Alertas, Importação e Eventos (`[x]` Implementado)

- `[x]` **12.1** (I-07) Aporte persistido em `contribution_plans` (`DRAFT`, `CONFIRMED`, `DISCARDED`) — `script_00013_contribution_plans.py`; a sugestão é gravada como foi exibida; `POST /api/v1/contributions/{id}/confirm` cria um `BUY` por execução (a própria sugestão ou o executado de fato, com preço, quantidade, taxas e câmbio editáveis), validando o livro como qualquer lançamento; só rascunhos mudam de estado (409 nos demais); nível 2 continua só com ativos `ELIGIBLE`/`HELD`.
- `[x]` **12.2** Motor de alertas (`fincontrol_core/alerts.py`): livro inválido, classe fora da banda, ativo em `REVIEW`, preço abaixo do justo (elegível ou em carteira), cotação em fallback, série desatualizada, retrato diário ausente e rotina com falha; chave estável por condição e rota da tela de ação; `GET /api/v1/alerts`, dispensa por N dias ou até a condição mudar (`alert_dismissals`, `script_00015_alert_dismissals.py`).
- `[x]` **12.3** (D-03) Importação B3 (Área do Investidor, `.xlsx` ou `.csv`): Negociação (compras/vendas, fracionário normalizado) e Movimentação (dividendo, JCP com bruto/IR a partir do líquido, rendimento, desdobro, grupamento, bonificação); pré-visualização com status por linha (`NEW`, `DUPLICATE`, `UNKNOWN_ASSET`, `IGNORED`, `INVALID`); deduplicação por hash de conteúdo + ocorrência (`import_hash` único em lançamentos, proventos e eventos); cadastro de tickers desconhecidos pelo catálogo ou pela convenção de código; gravação atômica após validar cada livro. O `.xlsx` exportado pela B3 declara `<dimension ref="A1"/>`: o leitor chama `reset_dimensions()` para ler todas as linhas (correção 2026-10-25).
- `[x]` **12.4** (D-03, TD-03) `corporate_events` (`script_00014_corporate_events.py`): desdobramento, grupamento e bonificação com custo atribuído aplicados por data no motor de posições, na validação do livro e no ciclo de vida; backfill de retratos expressa a quantidade nos termos da data final (cotações históricas ajustadas); fator dos eventos importados calculado pela posição do dia anterior; CRUD `/api/v1/corporate-events` revalidando o livro.

**Aceite:** `apps/api/tests/test_operations_flow.py` — importa as planilhas de exemplo (`apps/api/tests/fixtures/b3_*.csv`), vê alertas (banda, série), dispensa e restaura, confirma um aporte e verifica posições, alocação e o alerta da classe resolvido, sem lançamentos manuais. **Validação:** `scripts/check.sh --smoke` verde e migrações `script_00013`–`script_00015` validadas em Postgres descartável.

---

## Fase 13 — Frontend no Modelo de Referência (`[x]` Implementado)

**Objetivo:** reescrever `apps/web` seguindo a ADR 0007 — shell, menu e conteúdo interno no padrão do web do `dynamic-research`, **home como tela de analytics** e telas de operação apenas com o domínio da operação (gráficos só quando específicos da operação).

- `[x]` **13.1** (O-06) Fundação: `react-router-dom` 6, estrutura `src/layout`, `src/pages/<contexto>`, `src/viz`, `src/api`, `src/components`; tokens de espaço/tipografia e papéis `--app-*` claro e escuro; ícones SVG em linha; `App.tsx` só com o portão de sessão e as rotas; tipos gerados do OpenAPI (`scripts/gen_web_types.py`).
- `[x]` **13.2** (I-06, I-07) `request<T>()` que propaga erros (`ApiError`, servidor fora do ar, 422 resumido, sessão expirada) e `useApi(key, load)`; estados padronizados de carregando/erro/vazio; nenhuma regra de negócio no cliente (o cálculo local de aporte foi removido).
- `[x]` **13.3** Shell: sidebar com Visão geral, Operação e Configuração, contador de alertas, rodapé com usuário, tema e sair; topbar com título da rota; gaveta abaixo de 900 px; 404; login fora do shell.
- `[x]` **13.4** Início em atos: manchete gerada, indicadores com variação e minilinha, alocação × meta com banda, alertas com dispensa, base 100 carteira × CDI × Ibovespa e proventos por mês. Backend: `GET /portfolio/snapshots` e curva CDI no analytics.
- `[x]` **13.5** Desempenho: base 100 por período, risco e retorno, referências, drawdown, resultado por classe ao lado da referência da classe; "histórico insuficiente" explícito.
- `[x]` **13.6** Carteira por classe ARCA, filtro por conta, composição da classe.
- `[x]` **13.7** Detalhe do ativo (`/asset/:id`) com abas Resumo, Fundamentos, Valuation, Checklist (edição com evidência e histórico da nota), Proventos e Lançamentos; formulário de ativo com contrato de renda fixa.
- `[x]` **13.8** Pesquisar: screener com filtros e "classes abaixo da banda", observar candidato, aba Em observação.
- `[x]` **13.9** Aportar em etapas com antes × depois por classe, execuções editáveis e planos salvos. Backend: execução de ativo estrangeiro sem câmbio é lida em BRL e convertida; `by_class_allocated_brl` passa a ser o que cada classe recebe de fato (com redistribuição).
- `[x]` **13.10** Lançamentos: compras/vendas, proventos e eventos com filtros, edição e exclusão validadas; importação B3 com pré-visualização. Backend: `GET /transactions/{id}` e `GET /earnings/{id}`; watchlist sem caixa e renda fixa.
- `[x]` **13.11** Configuração: Estratégia (metas, bandas, divisão, elegibilidade, valuation, projeções, versões), Contas e Dados de mercado.
- `[x]` **13.12** 45 testes Vitest + Testing Library (cliente, visualizações, história da home e todas as páginas contra API falsa); ESLint sem avisos; `tsc` e build verdes; verificação visual contra API local com dados de exemplo.
- `[x]` **13.13** `docs/architecture/FRONTEND_UI_UX.md` reescrito para a ADR 0007.

**Aceite:** todas as rotas funcionam contra a API real (verificado em API local isolada com os extratos de exemplo importados); home só com analytics e operações só com seu domínio; `npm run lint && npm test && npm run build` verdes dentro de `scripts/check.sh --smoke`.

---

## Fase 14 — Validação Operacional 100% (`[x]` Implementado)

- `[x]` **14.1** `uv run python -m fincontrol_worker.seed_demo` (também `docker compose exec worker python -m fincontrol_worker.seed_demo`): carteira no estilo da referência (ações, FIIs de tijolo e papel, ETF, ETF americano, CDB, LCI, Tesouro IPCA+, reserva) com aportes mensais, venda parcial, proventos, séries e retratos diários de 2 anos; determinístico e offline; recusa banco com ativos.
- `[x]` **14.2** E2E Playwright (`scripts/e2e.sh`, `apps/web/e2e`) contra stack Docker isolada (`fincontrol-e2e`, volumes `fincontrol_e2e_*`, porta 18090, credenciais geradas): login → estratégia → importação B3 (Negociação e Movimentação) → observar ticker → cadastrar ativo → aportar e confirmar → Carteira, Início e Desempenho → editar e excluir lançamento → `docker compose restart` → persistência verificada.
- `[x]` **14.3** Recuperação: falhas de provedor lembradas por `MARKET_MISS_CACHE_TTL` (telas respondem na hora em vez de esperar o timeout), cotação em fallback sinalizada, alertas de frescor, todas as rotas das telas respondendo com provedores fora (`apps/api/tests/test_outage.py`, `apps/packages/core/tests/test_market_outage.py`); Redis indisponível cai para cache em memória (`test_redis_cache_falls_back_to_memory_when_unavailable`); cache de fuso do yfinance em pasta gravável nos containers.
- `[x]` **14.4** Documentação revista: `OVERVIEW.md` (política, rotinas do worker, modelo de dados até `script_00015`, fluxos de pesquisa, aporte, importação e alertas), `FEATURES_SPEC.md` por contexto, `FRONTEND_UI_UX.md` (ADR 0007), ADRs 0002/0005/0006 atualizadas, `TECH_DEBT.md` (TD-01 e TD-03 encerrados; TD-02 e TD-04 mantidos; TD-05 a TD-08 registrados).
- `[x]` **14.5** Pisos de cobertura no portão: `apps/packages/core` ≥ 90% (atual 96%), API + worker ≥ 80% (atual 96%), frontend ≥ 70% (atual 88% das linhas).
- `[x]` **14.6** Encerramento: cada achado com item e teste (tabela abaixo); `scripts/check.sh --e2e` verde; `docker compose build` e subida completa da stack validados. Push para o GitHub aguarda confirmação do usuário (6.4).

### Rastreabilidade dos achados

| Achado | Itens | Testes de regressão |
|---|---|---|
| C-01 | 8.1, 8.2 | `test_audit_characterization.py`, golden `test_reference_portfolio_golden.py` |
| C-02 | 8.4, 8.10 | `test_audit_characterization.py`, `test_ledger.py`, `test_ledger_api.py` |
| C-03 | 8.8 | `test_analytics_api.py`, `test_audit_characterization_api.py` |
| C-04 | 8.3 | `test_audit_characterization.py` |
| I-01 | 8.2, 8.5 | `test_audit_characterization.py`, `test_calendar_and_units.py` |
| I-02 | 8.11 | `test_audit_characterization.py`, `test_audit_characterization_api.py` |
| I-03 | 8.9 | `test_audit_characterization_worker.py`, `test_worker_backfill.py` |
| I-04 | 8.6, 8.7 | `test_ledger.py`, `test_ledger_api.py`, `test_corporate_events.py` |
| I-05 | 9.x | `test_error_handling.py`, `test_audit_characterization_api.py` |
| I-06 | 13.2 | `apps/web/src/test/http.test.ts`, `overview.test.tsx` (erro em vez de R$ 0) |
| I-07 | 13.2, 9.x | `test_market_batch.py`; o cliente não tem regra de aporte (`operations.test.tsx` usa a API) |
| I-08 | 9.1 | `test_settings.py` |
| I-09 | 8.8, 8.9 | `test_analytics_alignment.py`, `test_analytics_api.py`, `test_audit_characterization_worker.py` |
| I-10 | 8.11 | `test_audit_characterization.py` |
| I-11 | 10.2 | `test_consolidation_engine.py`, `test_policy_api.py` |
| A-01 | 10.3 | `test_arca_bands.py` |
| A-02 | 10.7 | `test_etf_exposure.py` |
| A-03 | 10.4 | `test_lifecycle.py`, `test_phase10_acceptance.py`, `test_seed_demo.py` |
| A-04 | 8.12, 13.9 | `test_audit_characterization.py`, `test_contribution_plans.py` |
| F-01 | 11.6–11.8 | `test_research_screener.py`, `test_research_flow.py` |
| F-02 | 11.1, 11.2 | `test_fundamentals_history.py`, `test_checklist_v2.py` |
| F-03 | 11.3, 11.5 | `test_checklist_v2.py`, `test_valuation_by_profile.py` |
| F-04 | 11.4 | `test_checklist_v2.py`, `test_phase11_persistence.py`, `test_checklist_api.py` |
| F-05 | 11.9, 13.7 | `test_research_flow.py`, `operations.test.tsx` (detalhe do ativo) |
| D-01 | 10.5 | `test_accounts_api.py`, `test_codes.py` |
| D-02 | 8.16 | `test_phase8_migrations.py` |
| D-03 | 12.3, 12.4 | `test_b3_import.py`, `test_b3_import_api.py`, `test_corporate_events.py`, `test_operations_flow.py` |
| D-04 | 9.x | `test_phase12_persistence.py::test_pagination_is_stable_when_sort_values_tie` |
| D-05 | 9.x | `test_market_batch.py`, `test_market_outage.py` |
| O-01, O-02, O-03 | 9.x | `scripts/smoke.sh` (não-root, healthchecks, Redis com senha, só o web publica porta, build por lockfile) |
| O-04 | 7.x, 14.6 | Git com Conventional Commits; portão local `scripts/check.sh` |
| O-05 | 7–14 | 395 testes Python, 45 do frontend e 2 E2E |
| O-06 | 13.1–13.12 | `apps/web/src/test/*.test.tsx` |
| O-07 | 14.4 | revisão desta fase |

**Definição de "100% operacional":** a stack sobe do zero com um comando; o usuário consegue executar o ciclo completo Estratégia → Pesquisar → Aportar → Lançamentos → Carteira/Desempenho sem editar banco ou arquivos; todos os valores da carteira de referência batem com a planilha golden; falhas externas aparecem como avisos e nunca como números falsos.

### Dependências entre fases
`7 → 8 → 10 → 11 → 12 → 14`, com `9` em paralelo a `8` (arquivos distintos) e `13` iniciando após o contrato de API da Fase 10 (13.1–13.3 podem começar logo após a Fase 8).

---

## Fase 15 — Refatoração Estrutural por Módulos (`[x]` Implementado)

**Objetivo:** organizar o backend no padrão estrutural do projeto de referência (`dynamic-research/apps/api`), com controllers, use cases, services, repositórios e infraestrutura segmentados por feature, e todo o código da solução dentro de `apps/`.

- `[x]` **15.1** API em `fincontrol_api/core/` (config, `security` com o login single-user, deps, middleware, `http_errors`) + `composition.py` (única escolha da `SqlAlchemyUnitOfWork`, do gateway de mercado e da sonda do banco) + `modules/<feature>/` (`router`, `schemas`, `use_cases`, `dependencies`, `serializers`, `service`) para system, auth, accounts, assets, ledger, portfolio, contributions, policy, research, market, alerts e shared. O documento OpenAPI ficou idêntico byte a byte ao anterior (sem mudança de contrato nem de tipos do frontend). CLI: `python -m fincontrol_api hash-password`.
- `[x]` **15.2** Persistence em `core/` (db, `unit_of_work`, health) + `models/`, `repositories/` e `mappers/` com um módulo por feature; models se referenciam só em anotações (`TYPE_CHECKING`), resolvidos pelo registro do SQLAlchemy.
- `[x]` **15.3** `packages/` movido para `apps/packages/{config,core,persistence}` (continua compartilhado entre API e worker como membros do workspace `uv`); Dockerfiles, `working_dir` do `migrate`, `scripts/check.sh`, caminhos do pytest e documentação atualizados.
- `[x]` **15.4** Teste de camadas cobre todos os `modules/*/router.py` (nada de SQLAlchemy, persistence ou `uow_factory`) e garante que só `composition.py` referencia a `SqlAlchemyUnitOfWork`; teste de importação a frio de todos os módulos sem ciclos.
- `[x]` **15.5** Sincronizado com `origin/main` (correção da importação `.xlsx` da B3, `reset_dimensions()`), aplicada em `modules/ledger/use_cases/b3_import.py`.

**Validação (2026-10-25):** `scripts/check.sh --smoke` → ruff e formatação limpos; 409 testes de backend com cobertura de 96,5% (API + worker), `apps/packages/core` acima do piso de 90%; 45 testes do frontend; build das imagens `migrate`, `api`, `worker` e `web` pelos dois arquivos de compose; smoke isolado `ready` em `script_00015`.

---

## Fase 16 — Pesquisa e Importação Integradas (`[x]` Implementado)

**Objetivo:** todo ativo novo entra pelo mesmo caminho da Pesquisa, com o quadrante ARCA confirmado pelo usuário, venha ele do screener, da lista de observação ou da importação da B3.

- `[x]` **16.1** `modules/research/service.py`: `register_researched_asset` (catálogo da B3 → tipo → quadrante ARCA escolhido ou sugerido) é o único cadastro de ativo novo da Pesquisa e da importação B3; `STATEMENT_TYPES` passou para `fincontrol_core.fundamentals.history`, compartilhado com o worker.
- `[x]` **16.2** Pesquisa: `POST /api/v1/research/watchlist` aceita `arca_class`; `PUT /api/v1/research/watchlist/{asset_id}/classification` reclassifica. Na tela, "Observar" pede o quadrante com a sugestão marcada; a lista de observação ganhou a coluna "Classe ARCA" editável e o formulário por código, a escolha do quadrante.
- `[x]` **16.3** Importação B3: a pré-visualização devolve o quadrante sugerido de cada ticker novo; o commit aceita `new_assets` (JSON com `ticker`, `asset_type`, `arca_class`) além de `create_tickers`; um ticker de tipo desconhecido passa a ser cadastrável escolhendo o tipo na tela; `created_assets` lista só os ativos criados naquele commit.
- `[x]` **16.4** Demonstrativos anuais buscados logo após o cadastro (observação e importação) por `StatementRefresher` em `BackgroundTasks` da API, sem atrasar a resposta; falha de provedor só é registrada em log e fica para a rotina semanal do worker.
- `[x]` **16.5** Testes: `test_research_service.py` (cadastro, sugestão, falha de provedor, tipos sem demonstrativo), `test_research_flow.py` (quadrante escolhido, demonstrativos gravados, reclassificação, 404/422), `test_b3_import_api.py` (escolhas por ticker, tipo desconhecido, `new_assets` inválido) e `operations.test.tsx` (escolha e cancelamento no screener, reclassificação, tipo e quadrante na importação).
- `[x]` **16.6** Documentação: ADR 0008 (módulos por feature, `apps/packages` e cadastro único de ativo), README (menus, importação, CI), `OVERVIEW.md` (estrutura do backend, fluxos 4.4 e 4.5), `FRONTEND_UI_UX.md` (telas e `ArcaClassSelect`), `FEATURES_SPEC.md`, `AGENTS.md` e débitos TD-09 a TD-11.

**Validação (2026-10-26):** `scripts/check.sh --smoke` → ruff e formatação limpos; cobertura de 96,1% em `apps/packages/core` e 96,7% em API + worker; 46 testes do frontend; build das quatro imagens pelos dois arquivos de compose; smoke isolado `ready`.

---

## Fase 17 — Arquitetura Unificada de Backend em Camadas por Domínio em `apps/api` (`[x]` Implementado)

**Objetivo:** unificar todo o código do backend exclusivamente sob `apps/api/`, eliminando subpacotes aninhados (`apps/packages/*`, `apps/worker`, `apps/api/src/fincontrol_api`), organizando o código em camadas por domínio (`controllers/{domain}`, `domain/{domain}`, `infra/data/repositories/{domain}`) com separação clara de `requests` e `responses`, resolvendo o ciclo de vida do worker e preservando 100% de paridade com o contrato OpenAPI.

- `[x]` **17.1** Unificação do backend em `apps/api/`: pastas `apps/packages/`, `apps/worker/` e `apps/api/src/fincontrol_api` eliminadas; workspace `uv` simplificado com `members = ["apps/api"]`.
- `[x]` **17.2** Camada de Apresentação em `controllers/`: organizado por domínio (`auth`, `accounts`, `assets`, `ledger`, `portfolio`, `contributions`, `policy`, `research`, `market`, `alerts`, `system`, `shared`) contendo `router.py`, `dependencies.py`, `serializers.py` e separação estrita de subpacotes `requests/` e `responses/`.
- `[x]` **17.3** Camada de Domínio Puro em `domain/`: organizado por domínio contendo `entities/`, `services/` (regras e cálculos como ARCA, Cerrado e Fixed Income) e `repositories/` (portas abstratas).
- `[x]` **17.4** Camada de Infraestrutura Concreta em `infra/`: `data/db.py`, `health.py`, `models/`, `mappers/`, `unit_of_work/`, `repositories/` e `migrations/` (Alembic `script_#####`); `cache/` (Redis) e `providers/` (gateways BRAPI, B3, Tesouro).
- `[x]` **17.5** Fundações transversais em `core/`: `settings.py`, `logging.py`, `middleware.py`, `http_errors.py`, `security.py`, `errors.py` e `helpers/`.
- `[x]` **17.6** Worker assíncrono em `worker/`: `scheduler.py`, `runner.py`, `jobs.py`, `rebuild.py`, `seed_demo.py` usando as mesmas camadas da API; resolução de dependência circular de importação a frio e desativação do healthcheck HTTP no Compose para o worker.
- `[x]` **17.7** Dockerfile e Compose: um único `apps/api/Dockerfile` multiuso para `api`, `migrate` e `worker`; `docker-compose.yml` e `docker-compose.prod.yml` atualizados.
- `[x]` **17.8** Testes e Validação: consolidação da suite de testes em `apps/api/tests/` (414 testes de backend passando), 46 testes de frontend passando (`npm test`), build do frontend Vite concluído, lint/formatação ruff 100% limpos e contrato OpenAPI idêntico.
- `[x]` **17.9** Documentação: ADR 0009 criado; `AGENTS.md`, `GEMINI.md`, `.agents/rules/project-rules.md`, `README.md` e `IMPLEMENTATION_PLAN.md` atualizados.

---

## Fase 18 — Configuração Agêntica e Servidor MCP Pessoal (`[x]` Implementado)

**Objetivo:** expor uma seção de configuração agêntica (`/settings/agentic`) para gerenciamento de chaves pessoais (`fck_...`) e disponibilizar todas as operações das telas da aplicação via protocolo MCP (Streamable HTTP) em `/api/v1/mcp`, seguindo o padrão arquitetural de `dynamic-research` adaptado ao modelo single-user pessoal.

- `[x]` **18.1** Persistência e Domínio de Chaves Agênticas: `AgentGrant`, `AgentApiKeyEntity`, `AbstractAgentKeyRepository`, `AgentApiKeyModel` (`agent_api_keys`), `SqlAlchemyAgentKeyRepository` integrado à `SqlAlchemyUnitOfWork` (`uow.agent_keys`) e migration Alembic `script_00016_agent_api_keys.py`.
- `[x]` **18.2** Catálogo de Operações e Escopo: `domain/agentic/services/catalog.py` mapeando as 38 operações das telas em 12 contextos (`portfolio`, `assets`, `contributions`, `ledger.trades`, `ledger.earnings`, `ledger.events`, `ledger.imports`, `research`, `policy`, `accounts`, `alerts`, `market`), com verificação de escopo (`reaches`, `validate_grant`).
- `[x]` **18.3** Casos de Uso e Rotas REST: `AgentKeyHandler` (`domain/agentic/services/use_cases.py`) com geração de chave `fck_<token>`, resumo SHA-256, comparação em tempo constante (`hmac.compare_digest`), controle de concorrência otimista (`revision`) e rotas `/api/v1/agents/keys` (`controllers/agentic/router.py`).
- `[x]` **18.4** Servidor MCP ASGI (`infra/mcp/server.py`): `McpPort` montado em `/api/v1/mcp` com `StreamableHTTPSessionManager`, verificação de `Origin` contra DNS rebinding, autenticação Bearer `fck_...`, `tools/list` filtrado pelo escopo da chave, `tools/call` com validação Pydantic, `idempotency_key` em comandos e saída estruturada.
- `[x]` **18.5** Interface Web (`apps/web/src/pages/settings/agentic/`): `AgenticPage`, `AgentKeyFormPage`, `ScopePicker`, `KeyExpiry`, `McpConnection` e rotas `/settings/agentic`, `/settings/agentic/new`, `/settings/agentic/:keyId` no menu Configuração.
- `[x]` **18.6** Testes e Validação: `apps/api/tests/test_agentic_mcp.py` (migrations, catálogo, CRUD REST, protocolo MCP `tools/list`, `tools/call` e `idempotency_key`), testes unitários e de página no frontend (`apps/web/src/test/settings.test.tsx`), build Vite e `docker compose build`.

---

## Fase 19 — Notificações de Erros de Requisição do Worker (`[x]` Implementado)

**Objetivo:** sinalizar falhas de requisição aos provedores externos (`brapi`, `yfinance`, `BCB SGS`) ocorridas durante a execução das rotinas em segundo plano do worker, exibindo uma badge com contagem de erros pendentes no menu **"Dados de mercado"** (`/settings/market-data`) e um log detalhado em tabela com os dados da requisição e da falha obtida.

- `[x]` **19.1** Domínio e Persistência: entidade imutável `WorkerRequestErrorEntity` (`domain/shared/entities.py`), contrato `AbstractWorkerErrorRepository` (`domain/shared/repositories.py`) exposto como `uow.worker_errors` em `AbstractUnitOfWork`, modelo `WorkerRequestErrorModel` (`worker_request_errors`), repositório `SqlAlchemyWorkerErrorRepository` (`infra/data/repositories/jobs.py`) e migration Alembic `script_00017_worker_request_errors.py`.
- `[x]` **19.2** Rastreamento de Erros de Requisição nos Provedores e Worker: `WorkerErrorRecorder` com `ContextVar` (`infra/providers/error_tracker.py`) propagado inclusive para pools de threads (`infra/providers/batch.py`), instrumentação de falhas HTTP/exceções em `BrapiProvider`, `YFinanceProvider` e `BcbSgsProvider` (preservando os fallbacks resilientes da aplicação) e persistência automática das falhas capturadas em `worker/runner.py` (`run_job`).
- `[x]` **19.3** Casos de Uso, Rotas REST e Catálogo MCP: `MarketDataHandler` (`domain/market/services/use_cases.py`) e rotas `GET /api/v1/market/worker-errors`, `DELETE /api/v1/market/worker-errors/{error_id}` e `DELETE /api/v1/market/worker-errors` (`controllers/market/router.py`), além das operações correspondentes no catálogo MCP (`domain/agentic/services/catalog.py`).
- `[x]` **19.4** Interface Web (`apps/web`): flag `showsWorkerErrorCount` no item "Dados de mercado" (`src/layout/navigation.ts`), badge de notificações não resolvidas na sidebar (`src/layout/AppShell.tsx`) sincronizada por evento customizado (`fincontrol:worker-errors-changed`), e tabela detalhada na tela `MarketDataPage.tsx` exibindo horário, rotina, provedor, operação/alvo, URL requisitada, status HTTP, tipo/detalhe do erro e ações para dispensar individualmente ou limpar todas as notificações.
- `[x]` **19.5** Testes e Validação: testes unitários e de integração no backend (`test_worker_runner.py`, `test_market_api.py`), testes de UI no frontend (`overview.test.tsx`, `settings.test.tsx`), regeneração de tipos OpenAPI (`scripts/gen_web_types.py`), lint/typecheck limpos e build Docker validado.




## Fase 20 — Correções do Worker: brapi e Snapshots Retroativos (`[x]` Implementado)

- `[x]` **20.1** `BrapiProvider.get_fundamentals` deixa de pedir o módulo `summaryDetail` (removido pela brapi, causava HTTP 400 `INVALID_MODULES` em todo ciclo de `warm_portfolio_quotes`); P/L, DY e DPS passam a vir de `priceEarnings`/`defaultKeyStatistics` (`trailingPE`, `dividendYield`/`yield`, DPS = DY × preço).
- `[x]` **20.2** Invalidação de snapshots por mudança no ledger: `invalidate_snapshots_from` (`domain/portfolio/services/snapshots.py`) apaga, via UoW, os snapshots com data ≥ à menor data afetada ao criar/editar/excluir transação, provento (`payment_date`) ou evento corporativo (`ex_date`), na importação B3 e na confirmação de aportes. O worker agenda `backfill_snapshots` a cada `quote_refresh_minutes` e o snapshot diário roda o backfill antes (`backfill_and_record_snapshot_job`) para não duplicar `net_flow`.
- `[x]` **20.3** Testes: `test_snapshot_invalidation.py`, `test_worker_runner.py` e testes de provider brapi atualizados.

---

## Fase 21 — Correção do Câmbio nos Formulários de Lançamento (`[x]` Implementado)

- `[x]` **21.1** `AssetSelect` ganha `onResolve`, chamado sempre que o valor selecionado ou a lista de ativos carregada muda; os formulários de negociação e de provento derivam a moeda do ativo daí, então o campo de câmbio aparece logo na abertura para ativos em USD (edição e `?asset=` pré-selecionado), preservando o `fx_rate` gravado.
- `[x]` **21.2** Prévia em reais ao lado do câmbio: total `(quantidade × preço + taxas) × câmbio` na negociação e líquido `(bruto − IR) × câmbio` no provento, com a mesma regra de `total_brl`/`net_amount_brl` da API.
- `[x]` **21.3** Testes de UI em `operations.test.tsx`: criação com ativo USD pré-selecionado, edição de negociação e de provento USD (valor salvo e envio do `fx_rate`) e ativo BRL sem o campo.
- `[x]` **20.4** Notificações do worker: `BcbSgsProvider` tolera `BCB_SGS_BASE_URL` com o sufixo legado `/bcdata.sgs` (gerava `.../bcdata.sgs/bcdata.sgs.N` e HTTP 404); `BrapiProvider` respeita o plano com `BRAPI_MAX_HISTORY_RANGE` (padrão `3mo`, ranges maiores vão direto ao Yahoo sem HTTP 400) e `BRAPI_MAX_CONCURRENCY` (padrão `1`, semáforo que evita HTTP 429). Testes em `test_provider_limits.py`.

---

## Fase 22 — Importação B3: Tesouro Direto, CDB e Fracionário com Dígito (`[x]` Implementado)

**Objetivo:** a Movimentação da B3 é o único extrato com Tesouro Direto e títulos bancários (eles nunca chegam à Negociação); trazê-los para o livro sem lançamento manual e corrigir tickers fracionários cujo código do emissor tem dígito.

- `[x]` **22.1** `FRACTIONAL_SUFFIX` aceita dígitos no código do emissor: `B3SA3F` → `B3SA3` (antes as compras fracionárias de B3 ficavam num ativo `B3SA3F`).
- `[x]` **22.2** Movimentação: `Compra`/`Venda`/`Vencimento` de "Tesouro …" e `APLICAÇÃO`/`RESGATE ANTECIPADO`/`Resgate`/`Vencimento` de CDB, LCI, LCA, CRI e CRA viram negociações; `Juros`/`Rendimento`/`Amortização` do Tesouro viram `FIXED_INCOME_COUPON`. `FixedIncomeRef` identifica o título (tipo, indexador, ano de vencimento, juros semestrais) ou o emissor e o código B3 da aplicação; o hash continua independente do ativo escolhido.
- `[x]` **22.3** `resolve_fixed_income` (`domain/ledger/services/b3_import.py`) aponta cada linha para o ativo cadastrado: ticker igual ao código B3; título do Tesouro pelo nome ou por tipo + ano de vencimento + juros semestrais; título bancário por tipo + emissor (**um ativo por emissor**, todas as aplicações juntas). Dois ativos candidatos → linha `INVALID`; nenhum → chave do grupo (`TESOURO_IPCA-2032`, `CDB-ITAUUNIBANCO`) reportada como ativo não cadastrado.
- `[x]` **22.4** Cadastro na importação: `UnknownTickerDTO.fixed_income_term` sugere tipo, indexador, emissor, primeira data do extrato e vencimento do catálogo do Tesouro; `ImportNewAssetRequest` aceita `name` e `fixed_income_term` com a taxa contratada (obrigatória, `FIXED_INCOME_TERM_REQUIRED`), o código do ativo segue `generated_asset_code`.
- `[x]` **22.5** Resgates maiores que o saldo (aplicação anterior ao período do extrato) ficam `INVALID` na pré-visualização e no commit, sem bloquear o restante do arquivo.
- `[x]` **22.6** Tela de importação: taxa, indexador, emissão, vencimento, liquidez e nome por título/emissor; o item só fica marcável com a taxa preenchida.
- `[x]` **22.7** Testes: `test_b3_import.py` (fracionário, Tesouro, CDB/LCA, resolução, ambiguidade), `test_b3_import_api.py` (pré-visualização, cadastro com termos, resgate sem saldo, reimportação sem duplicar, B3SA3F) e `operations.test.tsx` (termos do CDB e envio no commit).

---

## Fase 23 — Importação B3: Ignorar Linhas e Vendas sem Saldo (`[x]` Implementado)

**Objetivo:** um extrato que cobre só um período (ou um ativo que mudou de código, como TIET11 → AESB3) traz vendas sem a compra correspondente; antes uma única linha assim abortava a importação inteira com `LEDGER_CONFLICT`.

- `[x]` **23.1** Vendas de qualquer ativo maiores que o saldo (livro + compras do próprio extrato) ficam `INVALID` na pré-visualização e no commit, com o motivo, sem bloquear o restante do arquivo (generaliza o 22.5).
- `[x]` **23.2** `skip_lines` (números das linhas do extrato) em `POST /imports/b3/preview`, `POST /imports/b3/commit` e nas ferramentas MCP `ledger.imports.preview`/`ledger.imports.commit`: as linhas ficam `IGNORED` ("Ignorada por você") e a validação de saldo é refeita sem elas; entrada inválida → 400 `INVALID_SKIP_LINES`. Ticker sem nenhuma linha restante não é cadastrado no commit.
- `[x]` **23.3** Tela de importação: coluna "Importar" com caixa por linha nova ou de ativo não cadastrado; desmarcar refaz a pré-visualização mantendo as escolhas de cadastro.
- `[x]` **23.4** Testes: `test_b3_import.py` (`mark_skipped`), `test_b3_import_api.py` (venda sem saldo inválida e sem cadastro do ativo, linhas ignoradas na pré-visualização e no commit, `INVALID_SKIP_LINES`) e `operations.test.tsx` (desmarcar linha reenvia `skip_lines`).

---

## Fase 24 — Tributação Regressiva por Ativo e Comparador Tributado × Isento (`[x]` Implementado)

**Objetivo:** mostrar, por ativo e por aplicação, quanto imposto sai no resgate hoje e quanto se economiza esperando a próxima faixa, e comparar títulos tributados e isentos pelo valor líquido — com as alíquotas guardadas como dados com vigência, sem custo novo (só legislação pública). Regras verificadas em out/2026: a MP 1.303/2025 caducou em 08/10/2025 (sem alíquota única de 17,5%; LCI/LCA/CRI/CRA/debêntures incentivadas seguem isentas); JCP com 17,5% retidos desde 01/01/2026 pela LC 224/2025 (não pela Lei 15.270/2025, que trata dos dividendos acima de R$ 50 mil/mês).

- `[x]` **24.1** Tabela de alíquotas com vigência: `domain/tax` (`TaxRule`, `TaxBracket`, `TaxRuleBook` — sem sobreposição por regime; datas anteriores ao primeiro registro usam o primeiro) com regimes de renda fixa regressiva, isentos, IOF, ações, ETFs/BDRs, FII (ganho e rendimentos), dividendos, JCP, exterior e cripto; registro embutido `DEFAULT_TAX_RULES` e tabela `tax_rules` (migration `script_00019_tax_rules.py`, semeada com os mesmos registros) exposta como `uow.tax_rules`. `regressive_ir_rate`/`regressive_iof_rate` e o motor de renda fixa (`value_fixed_income_position`, `consolidate_portfolio`) leem a regra vigente na data do resgate/avaliação; o relatório da carteira usa os registros do banco. Resultados atuais inalterados (golden e caracterização passam).
- `[x]` **24.2** Situação tributária por lote (`domain/tax/services/status.py`): `replay_lots` exposto pelo motor; por aplicação, alíquota atual, IOF devido e data em que zera, data e dias até a próxima faixa (descartada quando cai depois do vencimento), IR estimado hoje × na próxima faixa (projeção pelas taxas anuais), IR economizado e ganho líquido de esperar; para renda variável, os regimes informativos do tipo com alíquota vigente e base legal.
- `[x]` **24.3** Comparador (`domain/tax/services/comparator.py`): indexadores `CDI_PERCENT`, `CDI_SPREAD`, `IPCA_SPREAD` e `PRE`; cenários `LOW`/`BASE`/`HIGH` das premissas da política (`ProjectionAssumptions.projected_cdi_rate`, `projected_ipca_rate`, `scenario_rate_shift`; vazio usa o CDI/IPCA de mercado) ou informados; IR/IOF sobre o ganho acumulado; valor e taxa líquidos anualizados em 252 dias úteis no vencimento e na janela comum (menor prazo, resgate bloqueado por carência sinalizado); taxa equivalente por faixa; ponto de empate em dias (a partir de quando o vencedor fica à frente até o fim da janela).
- `[x]` **24.4** `TaxHandler` (`domain/tax/services/use_cases.py`) e rotas `GET /api/v1/tax/rules`, `GET /api/v1/tax/assets/{asset_id}/status` e `POST /api/v1/tax/fixed-income/compare` (ofertas à mão ou por `asset_id`, completadas pelo cadastro); operações MCP `assets.tax_status`, `tools.fixed_income_compare` e `tools.tax_rules` (contexto `tools`) e instruções do servidor MCP.
- `[x]` **24.5** Interface web: aba **Tributação** no detalhe do ativo (`TaxTab.tsx`: faixa, próxima queda, IR estimado por aplicação, tabela regressiva ou regimes da renda variável) com atalho para o comparador; página **Comparar renda fixa** (`/tools/fixed-income`, seção "Ferramentas" do menu) com títulos à mão ou da carteira, cenários, janela comum, taxas equivalentes e empate; premissas do comparador na tela Estratégia; tipos regenerados (`scripts/gen_web_types.py`).
- `[x]` **24.6** Testes: `test_tax_rules.py` (fronteiras 180/181, 360/361, 720/721; IOF 29/30; isentos; vigência do JCP e dos dividendos; mudança legal como novo registro), `test_tax_status.py`, `test_fixed_income_comparator.py` (fórmulas por indexador, IR sobre o ganho acumulado, equivalências, janela/carência, empate em 721 dias, cenários), `test_tax_api.py` (migration e semente, rotas, novo registro mudando a avaliação, MCP) e `tax.test.tsx` (aba e comparador).

**Validação (2026-10-27):** `scripts/check.sh` → ruff e formatação limpos; suíte de backend com cobertura de 97,0%; 71 testes do frontend, lint, typecheck e build Vite; `docker compose build` das imagens `migrate`, `api`, `worker` e `web`.

---

## Fase 25 — Confiabilidade do Checklist e Sanidade dos Dados Fundamentalistas (`[x]` Implementado)

**Objetivo:** impedir que a sugestão de aporte siga uma tese vencida ou um dado de provedor errado.

- `[x]` **25.1** Validade das respostas manuais: `EligibilityPolicy.answer_validity_months` (padrão 12), `review_on_expired_answers` (padrão sim) e `drop_expired_answers` (padrão não). `evaluate(..., freshness=AnswerFreshness)` marca cada resposta manual vencida (`stale_reason`) e conta `stale`; com a opção, a resposta sai da nota (o histórico append-only a mantém). Resposta vencida torna o ativo inelegível, então quem tem posição vai para `REVIEW` (alerta `ASSET_IN_REVIEW`) e para de receber aportes. A validade vale na consolidação, no aporte, na pesquisa, na watchlist, no comparador e na rotina do worker que grava as avaliações; a Saúde da carteira passou a usar o mesmo vencimento (o limite próprio `checklist_max_age_months` foi removido).
- `[x]` **25.2** Reabertura: `fundamental_snapshots.first_seen_at` (migration `script_00022_fundamentals_first_seen.py`, preenchida com `fetched_at`) guarda quando cada demonstrativo foi gravado pela primeira vez; respostas manuais anteriores ao demonstrativo anual mais novo ficam `NEW_STATEMENT`. A atualização semanal não mexe na data.
- `[x]` **25.3** Sanidade no gateway (`domain/market/services/fundamentals_sanity.py`): faixas plausíveis por indicador e tipo (P/L, P/VP, DY, ROE, margem, dívida, crescimento; FII com P/VP 0,1–5) e, para ativos da B3, comparação brapi × Yahoo com divergência acima de 30% em P/L, P/VP, DY e ROE. As marcas ficam em `Fundamentals.suspicious` (com o motivo), seguem no cache e chegam ao valuation (`suspicious_inputs`, nota "dado suspeito" no método) — parte do TD-06.
- `[x]` **25.4** Bazin com proventos normalizados: mediana dos proventos pagos nos últimos 3 a 5 anos fiscais, por ação de hoje (valor de mercado ÷ preço); `extraordinary_dividends` quando os 12 meses passam de 1,5× a mediana. Sem 3 anos de demonstrativos, segue o provento dos 12 meses (com a nota).
- `[x]` **25.5** `PRICE_BELOW_CEILING` não dispara quando o valuation usa dado suspeito; alertas internos novos `SUSPICIOUS_DATA` (ativo com posição, elegível ou em revisão com indicador marcado) e `CHECKLIST_EXPIRED` (respostas vencidas ou reabertas). A Saúde da carteira ganhou a checagem "Peso com dado suspeito".
- `[x]` **25.6** Testes: `tests/test_checklist_reliability.py` (motivos de vencimento, nota com e sem as vencidas, elegibilidade, demonstrativo mais novo, faixas, divergência, gateway, Bazin normalizado, alertas, migration, `first_seen_at` preservado, reabertura de ponta a ponta com `REVIEW` e alerta, política), ajustes em `test_research_flow.py` e `test_health_engine.py`; `src/test/reliability.test.tsx` (selos no checklist e no valuation) e `settings.test.tsx` (opções da política).

## Fase 26 — Tesouro a Mercado, Agenda de Proventos e Alertas Internos (`[x]` Implementado)

**Objetivo:** corrigir o peso do quadrante Caixa e antecipar renda e eventos, com alertas apenas dentro do sistema (sem canal externo por ora).

- `[x]` **26.1** Marcação a mercado do Tesouro Direto (TD-02) e oportunidade de venda antecipada.
  - Série diária por título em `market_series` (`TD:<família>:<vencimento>` com o PU de venda e `…:R` com a taxa de venda em % a.a., unidade nova `PERCENT_PER_YEAR`); a família separa títulos de mesmo vencimento (IPCA+ × IPCA+ com juros semestrais). Rotina `sync_treasury_prices` no worker (dias úteis e na partida): busca o histórico em `PrecoTaxaTesouroDireto.csv` do Tesouro Transparente (`TESOURO_HISTORY_CSV_URL`) desde um ano antes da primeira compra quando falta série ou há buraco, e soma o ponto do dia pelo catálogo diário.
  - Motor `domain/portfolio/services/mark_to_market.py`: por compra (lotes por quantidade, FIFO), valor na curva × quantidade × PU de venda, diferença, IR/IOF e líquido vendendo hoje, rentabilidade ao ano realizada vendendo hoje × a entregue pela curva, valor líquido segurando até o vencimento e taxa de reinvestimento de empate (bruta, tributada, até o vencimento). Sinais: ganho sobre a curva acima de `early_sale_min_excess_rate` com prêmio, ou CDI projetado acima do empate por `early_sale_min_reinvest_spread` (padrões 1 p.p. e 0,5 p.p., na política). Status `OPPORTUNITY`, `NEUTRAL`, `BELOW_CURVE` ou `NO_MARKET_DATA`; histórico curva × mercado (até 120 pontos) para ver os momentos de ganho. Validado com o PU oficial de 28/10/2026 (Prefixado 2029 comprado a 13,75%: curva R$ 1.857,02 × mercado R$ 1.815,96). Títulos com juros semestrais: comparação com o vencimento aproximada (sem os cupons).
  - Rotas `GET /api/v1/portfolio/treasury-market` e `/treasury-market/{asset_id}` (com histórico), operação MCP `portfolio.treasury_market`, aba "Mercado" no detalhe do título e painel "Tesouro Direto a mercado" na Carteira.
- `[x]` **26.2** `ValuationPolicy.treasury_mark_to_market`: com a opção ligada, `consolidate_portfolio` valoriza o Tesouro pelo PU de venda do dia (IR e IOF com as alíquotas efetivas da curva), o que muda o peso do quadrante no ARCA e no aporte; checkbox na Estratégia. A opção vem ligada por padrão (o patrimônio da Home soma o Tesouro a mercado); políticas já gravadas mantêm o valor salvo. Os retratos diários seguem pela curva.
- `[x]` **26.3** Agenda de proventos anunciados pela página de empresas listadas da B3 (`infra/providers/b3_listed.py`, gratuita; o recurso de dividendos da brapi exige plano pago): dividendos, JCP e rendimentos de FII com data com, data ex (dia útil seguinte), pagamento e valor por cota, filtrados pela classe do ticker (ISIN ON/PN/units/cotas). `domain/portfolio/services/earnings_agenda.py` estima bruto, IR retido (JCP 17,5%; dividendos 10% acima de R$ 50 mil por empresa e mês) e líquido com a quantidade na data com. Rota `GET /api/v1/portfolio/earnings-agenda`, operação MCP `portfolio.earnings_agenda` e cartão "Proventos anunciados" no Início. TD-08: a importação da B3 usa a data com declarada para a data ex de desdobramentos, grupamentos e bonificações (crédito até 45 dias depois) e preenche a data ex dos proventos importados.
- `[x]` **26.4** Alertas internos `EARNING_COM_DATE` (data com em até 7 dias, carteira e watchlist), `FIXED_INCOME_MATURITY` (vencimento em até 30 dias), `TAX_BRACKET_SOON` (lote que muda de faixa de IR dentro da janela da política de saúde) e `EARLY_SALE_OPPORTUNITY` (Tesouro com status `OPPORTUNITY`). Checklist vencido e dado suspeito ficam para a Fase 25, que cria esses sinais.
- `[x]` **26.5** Testes: `tests/test_treasury_market.py` (famílias e símbolos, CSV histórico, provider, motor com o caso real, oportunidade, neutro, sem preço, FIFO, histórico, consolidação a mercado, rotina do worker, rotas, opção da política, MCP), `tests/test_earnings_agenda.py` (ISIN, parser e URLs da B3, agenda, datas ex, alertas, importação com data ex declarada, rota e MCP), `src/test/treasury.test.tsx` e `settings.test.tsx`.

## Fase 27 — Comparador de Ativos (`[x]` Implementado)

**Objetivo:** comparar até 5 ativos do mesmo perfil lado a lado, usando os dados já armazenados.

- `[x]` **27.1** Caso de uso `ResearchHandler.compare` (`domain/research/services/use_cases.py`) monta a comparação a partir dos demonstrativos anuais, indicadores atuais do provedor, valuation e checklist; aceita ativos cadastrados ou do catálogo B3 (`UNKNOWN_INSTRUMENT` para os demais, `INVALID_COMPARISON_SIZE` fora de 2–5) e busca sob demanda os demonstrativos de empresas que ainda não os têm (`statements_missing`, gravados pelo `AbstractFundamentalsRepository`).
- `[x]` **27.2** Motor puro `domain/research/services/comparison.py`: 18 indicadores em cinco grupos (valuation, endividamento, eficiência, rentabilidade, crescimento), com direção (menor/maior é melhor), destaque do melhor por linha (`best`; P/L, P/VP e EV/EBITDA só competem quando positivos) e avisos ao misturar perfis (ação × FII × ETF…), moedas ou ativos sem indicadores. A tela escolhe grupos e indicadores; a API aceita `indicators`.
- `[x]` **27.3** Histórico anual (receita, lucro, ROE e DY) em gráfico com seletor; DY anual estimado pelos proventos pagos sobre o valor de mercado no último pregão do ano (número de ações de hoje). Veredito de valuation e nota do checklist por ativo no topo da tabela.
- `[x]` **27.4** Rota `GET /api/v1/research/compare?tickers=A,B&indicators=...`, operação MCP `research.compare` e tela `/tools/compare` (menu Ferramentas · Comparar ativos); link "Comparar" na Pesquisa (resultados e watchlist), na Carteira e no detalhe do ativo.
- `[x]` **27.5** Testes: `tests/test_asset_comparison.py` (normalização, seleção, melhor por linha, indicadores dos demonstrativos, DY anual, avisos, rota, catálogo com busca sob demanda, MCP) e `src/test/compare.test.tsx`.
- `[x]` **27.6** Busca de ativos na tela de comparação: cartão "Buscar ativos" com nome ou código, setor e classe ARCA (mesmos filtros do Screener, via `GET /research/screener` e `/research/sectors`); cada resultado tem "Adicionar", desabilitado quando o ativo já está na comparação ou o limite de 5 foi atingido. Testes em `src/test/compare.test.tsx`.

## Fase 28 — Fatos Relevantes pelos Dados Abertos da CVM (`[x]` Implementado)

**Objetivo:** trazer fatos relevantes, comunicados e avisos aos acionistas dos ativos da carteira e da watchlist, sem custo.

- `[x]` **28.1** Provider CVM (`infra/providers/cvm.py`, `CVM_OPEN_DATA_BASE_URL`): baixa `CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_AAAA.zip` (documentos eventuais) e, para o mapa ticker → CNPJ, o arquivo `fca_cia_aberta_valor_mobiliario_AAAA.csv` de `CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_AAAA.zip` (coluna `Codigo_Negociacao`; o cadastro de companhias não traz o ticker). CSVs com `;` em latin-1, conferidos contra os arquivos reais de 2026. Parsers puros (`parse_ipe`, `parse_fca_tickers`, o FCA mais novo vence para um ticker repetido); falha de rede, HTTP de erro ou página no lugar do ZIP vão para o log de requisições do worker (Fase 19) e devolvem lista vazia. O gateway expõe `get_cvm_documents` e `get_cvm_issuer_tickers`.
- `[x]` **28.2** Migração `script_00024_cvm_documents`: `cvm_documents` (protocolo único, versão, CNPJ, companhia, código CVM, categoria, tipo, espécie, assunto, datas de referência e entrega, link, `first_seen_at`, `read_at`) e `cvm_issuer_tickers` (ticker → CNPJ). Deduplicação pelo protocolo: uma versão nova substitui os campos sem perder a marca de lido. Repositórios `uow.cvm_documents` e `uow.cvm_issuers`.
- `[x]` **28.3** Rotina diária `sync_cvm_documents` (`CVM_SYNC_CRON_HOUR`, padrão 7h; também com disparo manual em Dados de mercado, MCP `market.request_job` e `python -m worker.run_now sync_cvm_documents`): atualiza o mapa com o FCA dos últimos 3 anos (falha mantém o mapa gravado), acha o CNPJ das ações brasileiras ativas (carteira e watchlist; fracionário `F` vira o código principal), baixa o IPE do ano (e do anterior na primeira carga e em janeiro) e grava só os documentos dessas companhias. Detalhes da execução: companhias, mapeadas, sem CNPJ, documentos e novos.
- `[x]` **28.4** Rotas `GET /api/v1/disclosures` (filtros `asset_id`, `category`, `unread`, `limit`; contagem por categoria, não lidos, tickers sem CNPJ) e `POST /api/v1/disclosures/read` (por ids ou todos, de um ativo ou de todas as companhias); MCP `disclosures.list` e `disclosures.mark_read` (contexto "Comunicados da CVM"). Tela: aba "Comunicados" no detalhe do ativo e cartão "Fatos relevantes e comunicados (CVM)" no Início, com filtro por categoria, só os não lidos, link para o documento na CVM, marcar como lido e marcar todos. Alerta interno `RELEVANT_FACT` para fato relevante não lido entregue nos últimos 7 dias, que leva à aba do ativo e some ao marcar como lido.
- `[x]` **28.5** Limitação documentada na tela e na API: FIIs e ETFs não são companhias abertas e não publicam no IPE; a aba de um FII explica isso. A cobertura de FIIs (informe mensal e fatos relevantes de fundos) fica para uma etapa futura, junto da extensão da CVM das Fases 34 e 35.
- `[x]` **28.6** Testes: `tests/test_cvm_disclosures.py` (parsers com ZIP de exemplo em latin-1, provider com falhas, mapa com o mais novo, sincronização idempotente com versão nova preservando a leitura, mapa que falha, feed com filtros e marcação, alerta até a leitura, rotina do worker e MCP), ajuste em `tests/test_worker_runner.py` e `src/test/disclosures.test.tsx`.

## Fase 29 — Estatísticas e Saúde da Carteira (`[x]` Implementado)

**Objetivo:** transformar as métricas existentes em diagnóstico, nos sete pilares de [MARKET_ANALYSIS.md §7.3](../research/MARKET_ANALYSIS.md): cada checagem retorna ok/atenção/crítico, explicação e ação sugerida, com limites na política versionada.

- `[x]` **29.1** Concentração (`domain/portfolio/services/health.py` + `diversification.py`): maior ativo e cinco maiores (Tesouro e caixa fora), HHI e número efetivo por ativo, setor (renda variável sem ETFs), emissor (raiz do ticker ou emissor do título) e quadrante; exposição por instituição contra o limite do FGC (CDB, LCI, LCA e caixinhas), com aviso para título sem emissor.
- `[x]` **29.2** Diversificação de risco: covariância anualizada com encolhimento de Ledoit-Wolf sobre a correlação (vols amostrais preservadas; ativos tipo CDI sem risco), índice de Choueifaty, contribuição ao risco por ativo e quadrante (Euler) e pares com correlação acima do limite. Renda fixa segue o CDI diário; ativos internacionais usam o retorno na própria moeda.
- `[x]` **29.3** Risco e desempenho (`risk_metrics.py`): volatilidade, queda atual e duração, Ulcer Index, VaR/CVaR, estresse histórico (pior janela de 21 pregões e maior queda com os pesos atuais em 2 anos de preços), tracking error e Information Ratio contra o benchmark da política (IBOV, IFIX, S&P 500 e CDI nos pesos-alvo ARCA), Omega sobre o CDI, retorno e Sharpe em 12 meses móveis, consistência mensal contra o CDI e TWR aproximado por classe a partir dos retratos (TD-07 parcial: fluxo = variação do custo da classe; proventos por classe ficam de fora).
- `[x]` **29.4** Qualidade: nota média ponderada do checklist (saldo sobre perguntas aplicáveis), peso com respostas manuais mais antigas que a validade da política, Piotroski F-score e Altman Z''-score (`domain/assets/services/scores.py`) quando os demonstrativos tiverem as linhas necessárias — os provedores atuais não as trazem, então a checagem fica em "dados insuficientes". O selo de dado suspeito depende da Fase 25.
- `[x]` **29.5** Liquidez, renda e tributos: reserva em meses (custo mensal na política), % com liquidez até D+2, vencimentos em 12 meses, proventos de 12 meses, % da renda fixa isenta e lotes que mudam de faixa de IR na janela da política (Fase 24).
- `[x]` **29.6** Rigor estatístico: janela mínima por métrica (`min_observations` na política, 20 pregões para queda, 21 para estresse, 252 para a janela móvel, 6 meses para consistência) com estado `INSUFFICIENT_DATA` e intervalo de confiança de 95% por bootstrap (semente fixa) para Sharpe e CAGR.
- `[x]` **29.7** Tela `/health` (menu Visão geral · Saúde da carteira) com o pilar em pior estado primeiro e resumo sem média; limites em `HealthPolicy` (política versionada, coluna `health` pela migration `script_00021_policy_health_limits.py`) editáveis na Estratégia; rota `GET /api/v1/portfolio/health` e operação MCP `portfolio.health`.
- `[x]` **29.8** Testes: `tests/test_health_metrics.py` (séries sintéticas: pesos iguais, ativo único, ativos independentes com razão √n, Ledoit-Wolf, bootstrap determinístico, F-score/Z''), `tests/test_health_engine.py` (pilares, limites, ordenação, montador de entradas), `tests/test_portfolio_health_api.py` (rota, política, MCP, migration) e `src/test/health.test.tsx` / `settings.test.tsx`.

## Fase 30 — Tesouro: Rendimento Pró-Rata por Compra (`[x]` Implementado)

**Objetivo:** o rendimento dos títulos do Tesouro aparece automaticamente, proporcional ao tempo desde cada compra. A data de emissão gravada no cadastro (preenchida com a data do cadastro pela tela de Pesquisa ou com a primeira data do extrato B3) cortava o rendimento das compras anteriores a ela.

- `[x]` **30.1** Motor de renda fixa (`domain/portfolio/services/fixed_income.py`): todo lote começa na data da compra (`transactions.trade_date`, não a data de registro `created_at`); `issue_date` passa a ser só informativo (`earliest_fixed_income_start` também usa as compras).
- `[x]` **30.2** Taxa por compra no Tesouro Prefixado e IPCA+: `domain/portfolio/services/treasury_rates.py` (`implied_purchase_rate`) resolve a taxa que reproduz o PU pago para LTN, NTN-F (cupom de 10% a.a.), NTN-B Principal e NTN-B (cupom de 6% a.a.). No IPCA+, o PU é dividido pelo VNA (`vna_on`: R$ 1.000 em 15/07/2000, atualizado todo dia 15 pelo IPCA do mês anterior, pró-rata em dias úteis entre dias 15; meses ainda não publicados usam a projeção anual). A taxa fica no lote (`FixedIncomeLot.rate`) e é usada na curva, nos resgates FIFO, na projeção de 12 meses e na situação tributária por lote. `contracted_rate` é o fallback: Tesouro Selic, lacuna no histórico do IPCA, PU sem taxa plausível ou sem vencimento. O IPCA passa a ser sincronizado pelo worker e carregado nas curvas sempre desde 07/2000. Conferido com o BCB: VNA de R$ 4.195,02 em 15/01/2024 e 7,17% para um IPCA+ 2029 comprado em 03/12/2024 (catálogo: 7,15%).
- `[x]` **30.3** `fixed_income_terms.issue_date` opcional e nova coluna `semiannual_coupons` (migration `script_00020_fixed_income_issue_date_optional.py`, com preenchimento pelo nome "Juros Semestrais"); API, importação B3 (sem inferir a data de emissão pelo extrato e com a marca de juros semestrais da referência) e operações MCP aceitam os campos.
- `[x]` **30.4** Interface web: "Data de emissão (opcional)" informativa no cadastro e na importação (sem padrão "hoje" e sem obrigatoriedade); cadastro pela Pesquisa sem data de emissão; opção "Paga juros semestrais" para títulos do Tesouro (marcada pelo catálogo) e aviso de que o Prefixado rende pela taxa implícita no PU; tipos regenerados.
- `[x]` **30.5** Testes: `test_treasury_rates.py` (VNA na base, no dia 15, pró-rata e com lacuna; taxa recuperada para LTN, NTN-F, NTN-B Principal e NTN-B; casos sem taxa), `test_fixed_income_engine.py` (taxa implícita, lotes com taxas diferentes, valor de face no vencimento, resgate parcial mantendo a taxa, fallback com juros semestrais, data de emissão sem efeito), `test_treasury_pro_rata_api.py` (rotas, carteira e migration 00020), `test_b3_import_api.py` e `operations.test.tsx`.


## Fase 31 — Melhorias de Interface: Início, Ajudas, Ações e Pesquisa (`[x]` Implementado)

**Objetivo:** reduzir ruído visual e espaço perdido nas telas mais usadas e ampliar os filtros do screener.

- `[x]` **31.1** Início: patrimônio com o valor completo (sem abreviação); a Evolução fica logo abaixo de "Atual × meta" na coluna principal, com os alertas ao lado (`home-layout`), sem o vão causado pela altura do painel de alertas.
- `[x]` **31.2** "Proventos por mês" sai do Início e vai para Desempenho (com o yield on cost).
- `[x]` **31.3** Textos auxiliares: `.app-card-hint` ganha espaço próprio quando não vem logo após um título (antes a margem negativa o colava nos campos); o texto do Comparar ativos vira ajuda `?` (`Hint`).
- `[x]` **31.4** Ações de tabela com ícone (`components/RowActions.tsx`: `IconLink` e `IconButton`, rótulo como nome acessível e dica): editar/excluir em Lançamentos e no ativo, editar conta, editar/revogar chave MCP e remover da observação.
- `[x]` **31.5** Screener: filtros por classe ARCA (chips) e por setor; nova rota `GET /api/v1/research/sectors` (`catalog_sectors` no domínio) com os setores do catálogo B3.
- `[x]` **31.6** Testes: `test_research_screener.py` (setores distintos e ordenados), `test_research_flow.py` (rota), `operations.test.tsx` (filtros enviados), `overview.test.tsx` (valor completo e proventos em Desempenho) e `rowActions.test.tsx`.

## Fase 32 — Legibilidade da Saúde da Carteira e da Estratégia (`[x]` Implementado)

**Objetivo:** corrigir problemas de leitura apontados no uso da Saúde da carteira e da Estratégia, e investigar números implausíveis vistos nas mesmas telas.

- `[x]` **32.1** Seções recolhíveis (`<details>` com `.app-card`, ex.: "Janela móvel de 12 meses", "Contribuição ao risco", "Retorno por quadrante" em `/health`): a tabela fica colada ao `<summary>`. Dar espaço entre o resumo aberto e o conteúdo (regra única no tema, ex.: `details[open] > summary { margin-bottom }`), valendo para todas as telas. Feito: `details > summary` e `details[open] > summary { margin-bottom }` no tema, para todas as seções recolhíveis.
- `[x]` **32.2** Textos longos em uma única linha: as explicações das checagens da Saúde ocupam a largura toda do card. Limitar a largura de leitura dos parágrafos (~80 caracteres) e quebrar enumerações em lista (ex.: "Por quadrante: Real Estate 15% do peso e 100% do risco; …" vira uma linha por quadrante). Feito: a checagem ganhou `items` (API e tela), usado nos quadrantes fora da banda, no risco por quadrante e nos pares correlacionados, mostrados um por linha; explicação, ação, itens e notas com largura de leitura de 80 caracteres.
- `[x]` **32.3** Estratégia › Valuation: a opção "Pesar o Tesouro Direto pelo preço de mercado (em vez da curva) na carteira e no aporte" é uma escolha geral da política (não pertence a nenhum campo), mas aparece solta como mais uma célula da grade. Movê-la para baixo da grade, em linha própria, junto com os dois campos do Tesouro (ganho mínimo da venda e folga do CDI), com ajuda `?` explicando o efeito. Feito: bloco "Tesouro Direto" abaixo da grade do Valuation, com a opção em linha própria, a ajuda fora do rótulo e os dois campos do Tesouro.
- `[x]` **32.4** Investigar números implausíveis da Saúde da carteira (vistos em 28/10/2026): retorno de **-156,7%** na janela móvel de 12 meses (abaixo de -100%), volatilidade da carteira de **1160% a.a.** e XPML11 com 100% do risco tendo 1,5% do peso. Suspeita: série de preços com salto (ticker trocado, evento corporativo não aplicado ou preço em escala errada) ou janela com fluxo distorcendo o TWR. Conferir a série do XPML11 e o cálculo da janela móvel; marcar a métrica como suspeita quando sair da faixa possível. **Causas encontradas** (dados reais de 28/10/2026): (1) o Yahoo tinha o XPML11 a R$ 1,07 de 14 a 16/01/2026 entre fechamentos perto de R$ 110 (−99% e depois +10.198% num dia), o que dava volatilidade de 591% e 100% do risco a 0,8% do peso; (2) o TWR dos retratos dividia o resultado do dia só pelo valor da véspera, e em 21/10/2025 uma compra de R$ 2.729,98 sobre R$ 32,12 de carteira, com R$ 133 de diferença entre o preço de compra e o fechamento, virou um dia de −416% (−157% em 04/09/2024), o que levava a janela de 12 meses a −394%, a volatilidade a 300% e o TWR de Ações a −149%. **Correções:** `domain/market/services/price_sanity.py` descarta o trecho curto (até 5 pontos) que salta mais de 3× e volta para perto do último preço bom (nível que não volta, como desdobramento não aplicado ou queda real, fica), aplicado aos históricos da Saúde e às séries da simulação (`_price_series`); `dated_time_weighted_returns(..., purchases_at_start=True)` (Dietz modificado, compras no início do dia) nos retratos do Desempenho e da Saúde e no TWR por classe, com o fluxo no fim do período mantido no backtest, onde o aporte vem depois da variação do mês; dias da carteira com retorno abaixo de −95% ficam fora; a checagem ganhou `suspicious`, e as que usam uma série com dado descartado mostram o selo "Dado suspeito" com o que foi tirado. Com os retratos reais, a volatilidade cai de 300% para 24,4% a.a. e a janela de 12 meses de −394% para +0,5%, sem dia descartado. Testes: `tests/test_health_data_sanity.py`, ajustes em `test_health_engine.py`, `src/test/health.test.tsx`.
- `[x]` **32.5** Padronizar o tamanho das caixas de seleção: em Estratégia (Elegibilidade e Valuation) cada checkbox sai de um tamanho — "Resposta vencida coloca o ativo em revisão" fica menor e "Pesar o Tesouro Direto…" quase some. Causa provável: `.app-check` é `inline-flex` e o `input` (16 px no tema) encolhe quando o texto quebra em várias linhas. Fixar o controle (`flex: none` / `flex-shrink: 0` em `.app-check input`), alinhar ao topo do texto quando houver quebra, usar a mesma fonte dos rótulos dos campos e não misturar checkbox como célula da grade de campos (linha própria abaixo da grade, como em 32.3). Feito: `.app-check` alinha ao topo, usa a fonte dos rótulos e o controle tem `flex: none`; as opções da Elegibilidade e do Tesouro foram para `.app-check-row`, fora das grades (teste em `src/test/settings.test.tsx`).

## Fase 33 — Simulação de Carteira: Backtesting, Machine Learning e Inferência Bayesiana (`[x]` Implementado)

**Objetivo:** responder "onde eu estaria seguindo a minha estratégia desde X", "qual a faixa provável do patrimônio e da renda em N anos", "que ativos que ainda não tenho melhorariam a carteira nos cenários futuros" e "as probabilidades da simulação costumam se confirmar?", e testar se algum modelo de machine learning acrescenta informação útil fora da amostra. É simulação, nunca recomendação: nada da ferramenta altera a política ou dispara aportes. Desenho completo e teste de estresse (21 riscos) em [PORTFOLIO_SIMULATION_DESIGN.md](../features/PORTFOLIO_SIMULATION_DESIGN.md).

- `[x]` **33.0** Decisões tomadas (seções 10.1 a 10.4 do desenho, com fundamentação na literatura): universo inclui o catálogo (com selo de sobrevivência e ruptura), histórico do Yahoo, ML só de regime e risco, meta de patrimônio e renda, regras atuais aplicadas ao passado, 5.000 trajetórias/120 s, até 20 candidatos, prior Bayes-Stein para prêmios conservadores sobre o CDI, ruptura pela zona do Z''-score (perda central de 55%), calibração semanal só avisando; PyMC como oráculo de testes e no laboratório, fórmulas fechadas no caminho principal.
- `[x]` **33.1** Carga de séries históricas point-in-time com relatório de cobertura. `YFinanceProvider.get_full_history` (`auto_adjust=False`: fechamento ajustado só por desdobramentos e "Adj Close" com proventos) e `CachedMarketGateway.get_full_history`; rotina semanal `sync_simulation_history` no worker grava em `market_series` `SIM:TR:<ticker>` (retorno total), `SIM:PX:<ticker>` (lotes), `SIM:IDX:IBOV` e `SIM:IDX:SP500TR`, `SIM:FX:USDBRL` e completa o CDI desde 2005, sempre recarregando o histórico inteiro de cada ativo (o Yahoo reescala o ajuste a cada provento). Universo: ativos com preço de mercado da carteira e da watchlist mais os `SIMULATION_CATALOG_TOP` (padrão 50) mais negociados do catálogo. `domain/simulation/data.py`: `coverage_report` (meses cobertos, maior intervalo, OK/PARTIAL/MISSING) e `build_market_history`, só do banco (ativos em USD convertidos pelo dólar do dia; chaves `CDI`, `IBOV`, `IFIX`, `SP500_BRL`). Rota `GET /api/v1/simulations/coverage` e operação MCP `simulation.coverage`. Limite: o Yahoo não tem histórico do IFIX; vale a série `IFIX` já gravada (até 10 anos). Testes em `tests/test_simulation_data.py`.
- `[x]` **33.2** Backtest da estratégia (camada A). `domain/simulation/market.py` (séries point-in-time com `LookAheadError`, fins de mês úteis, índice de taxa diária) e `domain/simulation/engine.py`: aporte mensal pelas regras reais de `consolidate_portfolio` + `plan_contribution`, caixa rendendo o CDI, emolumentos, correção pelo IPCA, entrada do ativo pela primeira data de preço; rebalanceamento opcional (`rebalance`) que vende o excesso das classes acima da banda até a meta, pelo custo médio, com o IR do tipo do ativo (`sale_tax_rate` pelas regras vigentes; ações isentas até R$ 20 mil de vendas no mês; prejuízo não é compensado, conservador); política fixa ou a versão vigente em cada data (`policy_versions`, `policy_on`); respostas manuais do checklist valendo a partir do `answered_at` (`answers_on`); selo `survivorship_bias` quando entram ativos do catálogo. Saídas: TWR, TIR, volatilidade, queda máxima, custos, IR e número de vendas; referências com o mesmo fluxo. Testes: `tests/test_simulation_backtest.py` e `tests/test_simulation_rebalance.py` (anuidade, 100% CDI, pesos-alvo, lotes inteiros, custos, IPCA, look-ahead, IR do rebalanceamento conferido à mão, isenção de ações, política por data, checklist histórico, selo de sobrevivência).
- `[x]` **33.3** Execução assíncrona no worker, persistência e reprodutibilidade. Migração `script_00023` (`simulation_runs`: tipo, status PENDING/RUNNING/DONE/FAILED/TIMEOUT, parâmetros JSON, `params_hash`, `data_hash`, `code_version`, semente, erro, `reused_from`, datas; `simulation_results`: uma linha por série com resumo e pontos mensais), porta `domain/simulation/repositories` e `uow.simulations`. `domain/simulation/runs.py`: `BacktestParams` (período, aportes, IPCA, taxas, rebalanceamento, universo `REGISTERED` ou `REGISTERED_AND_CATALOG`, política `CURRENT` ou `AS_OF`, referências CDI/IBOV/IFIX/SP500_BRL), entradas lidas do banco (ativos com o histórico de respostas do checklist, ativo sintético `CAIXA-CDI` na classe Caixa, versões da política, regras de IR) e `data_hash` sobre todas elas; uma rodada com os mesmos parâmetros, dados e `ENGINE_VERSION` reaproveita o resultado guardado. Limite de tempo (`SIMULATION_TIMEOUT_SECONDS`, 120 s) verificado a cada mês pelo motor (`SimulationTimeout`). Worker: `run_pending_simulations` consulta a fila a cada `SIMULATION_POLL_SECONDS` (15 s) e só registra execução em `job_runs` quando há rodada pendente. Rotas `POST /api/v1/simulations/backtests` (202), `GET /api/v1/simulations` e `GET /api/v1/simulations/{id}`; operações MCP `simulation.backtest`, `simulation.get` e `simulation.list`. Testes em `tests/test_simulation_runs.py`.
- `[x]` **33.4** Telas Passado e Robustez. `domain/simulation/robustness.py`: crises históricas fixas (2008, 2015–16, Joesley Day, Covid, alta de juros de 2021–22) medidas em cada série pelo retorno mensal sem os aportes e pela queda dentro da janela (só conta quando a série já existia antes do início); choques sintéticos de primeira ordem sobre a alocação final (ações −30%, CDI +5 p.p., IPCA de 12%, dólar +40%, FIIs −20%); variantes das regras (bandas 0, 5, 10 e 20 p.p., com e sem rebalanceamento) rodadas no mesmo job quando `variants=true`, guardadas como `variant:*`, com a distribuição de todas (mínimo, mediana, máximo), os últimos 36 meses reservados para validação, a contagem de tentativas da rodada e de todas as rodadas calculadas (risco R3) e avisos de amostra (R4). `ENGINE_VERSION` 33.4.0. Rota `GET /api/v1/simulations/{id}/robustness` e operação MCP `simulation.robustness`. Tela `/tools/simulation` (menu Ferramentas › Simular carteira): formulário, lista de rodadas com atualização automática enquanto estão na fila, aba Passado (patrimônio da estratégia e das referências, resumo, alocação final, selo de sobrevivência, dados de reprodutibilidade) e aba Robustez. Testes: `tests/test_simulation_robustness.py` e `src/test/simulation.test.tsx`.
- `[x]` **33.5** Simulação prospectiva (camada B). `domain/simulation/scenarios.py`: bootstrap em blocos estacionário (Politis & Romano, blocos médios de 12 meses) sobre os retornos mensais conjuntos das classes (IBOV, IFIX, S&P 500 em reais), tomados como **excesso sobre o CDI do mês** e somados ao CDI do cenário, para que o prêmio venha do histórico e o nível dos juros das premissas; Caixa rende o CDI × multiplicador, líquido do IR da renda fixa. Cenários de juros pelo `default_scenarios` do comparador (base, queda e alta: CDI ± `scenario_rate_shift`, IPCA ± metade), todos com a mesma semente (números aleatórios comuns). Fluxo mensal: aporte constante em R$ de hoje (mais crescimento real opcional) nas classes mais abaixo da meta, rebalanceamento opcional pela banda com IR sobre o ganho vendido (ações 15%, FIIs 20%, exterior 15%) e emolumentos. Saídas em R$ de hoje, por cenário: percentis 5/25/50/75/95 do patrimônio e da renda passiva mensal ano a ano, patrimônio líquido do IR de vender tudo, probabilidade das metas de patrimônio (líquido) e de renda com o erro de Monte Carlo, tempo até cada meta, queda máxima da estratégia, premissas por classe (prêmio sobre o CDI, volatilidade, retorno no cenário, DY) e avisos (amostra curta, série que limita a janela, horizonte maior que a amostra). Ponto de partida congelado no pedido: valor por classe e DY dos últimos 12 meses do relatório da carteira (sem posição: 5% em ações, 1,5% no exterior e o DY padrão de FIIs da política), CDI/IPCA das premissas ou do mercado; o worker não chama provedores. A renda do Caixa conta só o rendimento real. Tipo `PROJECTION` em `simulation_runs` (sem migração), despacho por tipo em `execute_next_run`, `ENGINE_VERSION` 33.5.0. Rotas `POST /api/v1/simulations/projections`, `GET /api/v1/simulations/{id}/projection` e `GET /api/v1/simulations?kind=`; MCP `simulation.project` e `simulation.projection`. Aba Futuro em `/tools/simulation` com formulário, leque de percentis (`TrendChart` ganhou faixas), metas, tabela de percentis e premissas. Desvios do desenho: o DY é o dos últimos 12 meses da carteira, não o normalizado da Fase 25; o Vasicek, o regime (camada C) e o intervalo de credibilidade da probabilidade (33.6) ficam para depois. Testes: `tests/test_simulation_projection.py` (fórmula fechada do valor futuro, caixa rendendo a inflação mantém o valor real, bootstrap sem reinício repete o histórico, tamanho médio dos blocos, semente, alocação pelo déficit, IR do rebalanceamento, metas, rotas, worker, reaproveitamento, MCP) e `src/test/simulation.test.tsx`.
- `[x]` **33.5.1** Disparo manual da carga de histórico (antes ela só rodava no agendamento semanal, e sem ela toda simulação falhava por falta de série). `job_runs` ganhou o status `REQUESTED` (sem migração): `POST /api/v1/market/job-runs/{job}/request` (202) e a operação MCP `market.request_job` gravam o pedido, só para as rotinas de `MANUAL_JOBS` (hoje `sync_simulation_history`; as demais dão `JOB_NOT_MANUAL`), e um pedido que ainda espera é devolvido em vez de duplicado. O worker confere os pedidos no intervalo da fila de simulações (15 s) com `run_requested`, e a linha do pedido vira a execução, com o mesmo lock da rotina agendada (se ela estiver rodando, o pedido fica `SKIPPED`), novas tentativas e registro de erros. Para rodar já e esperar: `python -m worker.run_now sync_simulation_history` no contêiner do worker. Tela Dados de mercado: bloco "Rodar agora" com o botão "Carregar o histórico da simulação", acompanhamento até terminar e rótulos em português para os status; a falha de simulação por falta de histórico aponta para essa tela. Testes: `tests/test_manual_jobs.py` e `src/test/settings.test.tsx`.
- `[x]` **33.6** Camada bayesiana e aba Confiança. `domain/simulation/bayes.py` (só numpy, fórmulas fechadas): peso de Bayes-Stein (Jorion) convertido no peso do prior em meses equivalentes (teto de 600), prior normal-inverso-Wishart sobre a média e a covariância do **log do excesso** mensal sobre o CDI (o alvo da decisão 8 é um prêmio geométrico: CDI + 3% em ações e exterior, CDI + 2% em FIIs; covariância do prior no Ledoit-Wolf de `diversification.py`, ν0 = K + 2), posterior conjugada, sorteio de (μ, Σ) pela inversa de Wishart (Bartlett), quantis da Beta por integração numérica e pesos de stacking (ponto fixo do EM, que maximiza o log score da mistura). `domain/simulation/generators.py`: bootstrap em blocos, bootstrap bayesiano (pesos de Dirichlet nos meses, um vetor por trajetória) e normal bayesiana (parâmetros sorteados por trajetória), misturados pelos pesos; as trajetórias são sorteadas uma vez e servem aos três cenários de juros. `domain/simulation/calibration.py`: em cada fim de mês com 60 meses antes, cada gerador refeito só com o passado prevê 12 meses da carteira-modelo (metas da política); PIT, cobertura do intervalo de 90% com posterior Beta sobre n efetivo = n/12 (janelas sobrepostas), Brier de perder 10% e de bater o CDI, log score (núcleo gaussiano); status calibrado, mal calibrado (90% fora do intervalo) ou inconclusivo (menos de 8 janelas efetivas ou intervalo com mais de 35 p.p.); a combinação é pontuada como os demais. Tipo `CALIBRATION` na fila do worker, enfileirado ao fim de cada carga de histórico (semanal ou manual), por `POST /api/v1/simulations/calibrations` ou MCP `simulation.calibrate`; leitura por `GET /api/v1/simulations/calibration` e `simulation.calibration`. A projeção (`generator=STACKED`, padrão) usa os pesos da última calibração das mesmas classes, ou pesos iguais com aviso; também aceita um gerador só. Toda probabilidade da aba Futuro sai com intervalo de 90% (Beta(k + 1, n − k + 1) das trajetórias, alargado para cobrir a chance de cada gerador), mais as chances de perder 10% em 12 meses e de bater o CDI, o prêmio a posteriori por classe, o peso do prior e o aviso quando o prior pesa mais que os dados (R15). Tela: aba Confiança (geradores, cobertura com intervalo, status, PIT, Brier, log score, pesos, histograma do PIT e previsto × realizado, botão Recalcular) e um guia em todas as abas com a pergunta, o método e quando usar Passado, Futuro, Robustez e Confiança. `ENGINE_VERSION` 33.6.0. Desvios do desenho: o PyMC não entrou como oráculo (PyTensor compila modelos e exigiria compilador no Windows e na imagem slim); o oráculo é a integração numérica em grade da posterior normal-gama 1-D; as visões Black-Litterman das premissas da política e o gerador condicionado ao regime (33.9) ficam para depois; os pesos do stacking são estimados com todas as origens, então a linha da combinação na calibração é um pouco otimista (avisado na tela). Testes: `tests/test_simulation_bayes.py` (prior sem dados, amostra enorme, oráculo numérico, momentos dos sorteios, Bayes-Stein, Beta, stacking, geradores, intervalos, dados do próprio modelo calibram, salto de volatilidade fica mal calibrado, sem look-ahead, histórico curto inconclusivo, worker, rotas, MCP) e `src/test/simulation.test.tsx`.
- `[x]` **33.7** Ativos candidatos (camada D). Seleção no pedido (`select_candidates`): a watchlist e, se pedido, o screener por volume (excluindo o que já está registrado), com os filtros do aporte real (sem dado suspeito, elegibilidade; os de fora podem entrar marcados), teto de 20 e o motivo de cada excluído; o ponto de partida e as taxas ficam congelados como na projeção, e a contagem de ativos por classe da carteira define a parte do candidato. `domain/simulation/candidates.py`: modelo de fator sobre o excesso mensal ao CDI (`r = α + β·r_classe + ε`, OLS com 36 meses ou mais), τ da classe por Bayes empírico com todos os ativos com histórico (var(α̂) menos o ruído médio; 3% a.a. com menos de 3 ativos), posterior normal-normal do α (para 0) e do β (para 1, desvio 0,5), resíduos em blocos do próprio ativo, sorteio de α e β por trajetória e ruptura pela zona (decisão 9; ETF sem ruptura; perda de 55% ou 90% em estresse). Efeitos nas mesmas trajetórias da camada B, com e sem o candidato (números aleatórios comuns): Δ patrimônio final mediano e P(melhora) com intervalo Beta, Δ chance de meta, Δ CVaR de 12 meses, Δ queda mediana, Δ índice de diversificação (Choueifaty) e Δ DY da carteira; estabilidade do ranking (fração de 100 reamostragens das trajetórias em que fica entre os 5 primeiros). Tipo `CANDIDATES` no worker (`ENGINE_VERSION` 33.7.0); `project(..., keep_paths=True)` devolve o resultado por trajetória. Rotas `POST /api/v1/simulations/candidates` e `GET /api/v1/simulations/{id}/candidates`; MCP `simulation.find_candidates` e `simulation.candidates`. Aba Candidatos ("para investigar", sem compra), com link para o comparador e os excluídos. Simplificações: a parte do candidato é a de um ativo a mais na classe (ou um peso fixo), não o `plan_contribution` exato; a zona do Z'' fica "sem dado" até haver demonstrativos completos (Fase 34.9/CVM); só o cenário base de juros. Testes: `tests/test_simulation_candidates.py` (OLS conhecido, α alto com histórico longo reconhecido e com 36 meses encolhido, τ de ruído perto de zero, ruptura, ranking estável e instável, P(melhora) de ruído perto de 50%, filtros, worker, rotas, MCP) e `src/test/candidates.test.tsx`.
- `[x]` **33.8** Validação estatística (`domain/simulation/validation.py`, só numpy): walk-forward de janela crescente com purga (o rótulo de cada observação de treino termina antes do teste) e intervalo de embargo entre janelas de teste; Sharpe deflacionado de Bailey e López de Prado (máximo esperado de N tentativas de ruído pela aproximação com a constante de Euler, conferido por Monte Carlo, e o Sharpe probabilístico com assimetria e curtose); PBO por CSCV (blocos contíguos, todas as metades como dentro e fora da amostra, logit do posto relativo fora da amostra da melhor dentro); portão bayesiano por bootstrap bayesiano da diferença média contra a referência (passa com 95% ou mais); `validate_configurations` exige os três (Sharpe deflacionado significativo, PBO abaixo de 50% e portão). Aplicado na Robustez: as variantes de regra, em retornos mensais sem aportes e acima do CDI, julgadas contra a regra atual com todas as tentativas já feitas na conta (`trials_total`); a aba mostra o veredito, o Sharpe contra o máximo esperado do acaso, o PBO e a chance de superar a regra atual. A mesma validação é o portão do laboratório (33.9). Testes: `tests/test_simulation_validation.py` (ruído dá PBO perto de 50% e Sharpe deflacionado sem significância, sinal real passa, mais tentativas deflacionam o mesmo Sharpe, purga sem sobreposição, rota da Robustez) e `src/test/simulation.test.tsx`.
- `[x]` **33.9** Laboratório de ML, só regime e risco (decisão 3), em numpy, sem dependência nova (`domain/simulation/ml/`): HMM gaussiano de 2 e 3 estados (Baum-Welch com forward-backward escalado; estado 0 = o pior regime; filtro bayesiano P(regime | passado)), mistura gaussiana de 2 componentes (EM), EWMA com λ 0,85 e 0,94 e GARCH(1,1) com alvo de variância e (α, β) por máxima verossimilhança em grade. Todos preveem a densidade do retorno do mês seguinte (excesso sobre o CDI da carteira-modelo, as metas da política), refeitos a cada 12 meses e filtrados mês a mês só com o passado, contra a referência normal com média e variância do histórico; o ganho é o log score do modelo menos o da referência. Portões (seção 7.2), todos exigidos: chance de superar a referência ≥ 95% (bootstrap bayesiano), Sharpe deflacionado ≥ 95% com todas as tentativas do laboratório contadas, CSCV com o modelo escolhido perdendo para a referência fora da amostra em menos de 20% das divisões e estabilidade com a primeira previsão deslocada 12 meses para trás e para frente. Tipo `LAB` (`ENGINE_VERSION` 33.9.0), tentativas acumuladas pelas linhas de modelo das rodadas calculadas (reaproveitamento não conta); `POST /api/v1/simulations/lab`, `GET /api/v1/simulations/lab`, MCP `simulation.run_lab` e `simulation.lab`; aba Laboratório com o veredito, os portões por modelo e a probabilidade do regime de estresse mês a mês. Desvios do desenho: (1) o PBO do conjunto aparece mas não barra: com modelos parecidos que superam todos a referência, escolher o melhor deles não acrescenta nada e o PBO fica perto de 50% mesmo assim; o portão usa a probabilidade de perda da mesma CSCV; (2) sem scikit-learn, hmmlearn ou arch (modelos simples demais para justificar a dependência); (3) nenhum modelo aprovado ainda alimenta a camada B: a ligação (bootstrap condicionado ao regime) fica para quando um modelo passar com os dados reais. Testes: `tests/test_simulation_lab.py` (HMM recupera 2 regimes e filtra, mistura e GARCH recuperam os parâmetros, referência normal, ruído não aprova nada, regimes nítidos aprovam o HMM, mais tentativas sobem a régua, histórico curto falha, worker com tentativas sem contar reaproveitamento, MCP) e `src/test/lab.test.tsx`.
- `[x]` **33.10** MCP completo (`simulation.coverage|backtest|get|list|robustness|project|projection|calibrate|calibration|find_candidates|candidates|run_lab|lab` e `market.request_job` para as cargas), documentação (`OVERVIEW.md` com as rotinas do worker, as tabelas até `script_00024` e as seções 4.7 Simulação e 4.8 Comunicados da CVM; `README.md` com o primeiro uso da simulação; status e desvios no topo do desenho; handoff final), teste de integração de ponta a ponta `tests/test_simulation_end_to_end.py` (carga do histórico por um provedor simulado → calibração enfileirada sozinha → backtest com variantes e validação, projeção com os pesos calibrados, candidatos e laboratório, todos pelo worker e lidos pela API) e teste de UI das seis abas com o guia e o estado vazio (`src/test/simulation.test.tsx`); `docker compose build` validado.

## Fase 34 — Otimização da Composição de Ativos dentro do ARCA (`[ ]` Proposta)

**Objetivo:** mantendo as proporções ARCA da política, procurar entre os ativos disponíveis (carteira, watchlist e, opcionalmente, o catálogo filtrado), com base nas métricas de cada um e, à escolha, na análise do Cerrado, a composição dentro de cada classe que melhor atende a um objetivo de retorno: **valorização**, **dividendos** ou **misto**. O resultado é uma proposta para estudo, comparada com a carteira atual, com pesos iguais e com o aporte pelo Cerrado, nunca uma ordem de compra; nada muda a política sozinho. Desenho completo e teste de estresse (13 riscos) em [ASSET_COMPOSITION_OPTIMIZATION_DESIGN.md](../features/ASSET_COMPOSITION_OPTIMIZATION_DESIGN.md).

**Depende de:** Fase 33 (trajetórias da camada B, camada bayesiana da 33.6, modelo de ativo da 33.7 e validação da 33.8). **Ganha insumos com:** Fase 28 (fatos relevantes e mapa ticker → CNPJ) e uma extensão dos dados abertos da CVM: DFP/ITR com data de entrega para escores point-in-time, cadastro com cancelamentos contra o viés de sobrevivência e, a confirmar, o informe mensal de FII para o objetivo Dividendos.

- `[ ]` **34.0** Decisões da seção 10 do desenho: forma do objetivo misto, modo do Cerrado, universo e teto por classe, Caixa dentro ou fora, limites de concentração, restrição de risco, ponto de partida, `scipy`, aplicação como peso manual e ordem em relação à CVM.
- `[ ]` **34.1** Universo e filtros: os mesmos do aporte real (elegibilidade, checklist e respostas vencidas, sem dado suspeito, liquidez, 36 meses de histórico) e o Cerrado em três modos (exigido, ponderado, ignorado).
- `[ ]` **34.2** Escores por objetivo: z robusto por classe e setor, pesos das métricas versionados por objetivo (valorização, dividendos, misto) e pré-seleção dos K melhores por classe, com a explicação por ativo.
- `[ ]` **34.3** Modelo de retorno de cada ativo (reaproveita a 33.7), com proventos separados da valorização e o prior do α calibrado pelos escores.
- `[ ]` **34.4** Otimizador sobre cenários dentro de cada classe: metas ARCA, limites por ativo, setor e emissor, CVaR de 12 meses e lotes inteiros.
- `[ ]` **34.5** Reamostragem bayesiana dos pesos, estabilidade por ativo e P(melhora) com intervalo de credibilidade.
- `[ ]` **34.6** Walk-forward contra pesos iguais, a carteira atual e o aporte pelo Cerrado, com os portões da 33.8 e a contagem de tentativas; "otimizar não melhora" é um resultado válido.
- `[ ]` **34.7** Plano de transição: só com aportes (sem venda) ou com vendas, IR e custos.
- `[ ]` **34.8** Aba Composição em Simular carteira, MCP `simulation.optimize` e `simulation.composition`, guia de abas atualizado, testes de UI e integração, `docker compose build`.
- `[ ]` **34.9** Escores point-in-time com os dados da CVM (depois da Fase 28 e da extensão), sem look-ahead nos fundamentos.

## Fase 35 — Paginação das Tabelas de Pesquisa (`[x]` Implementado)

**Objetivo:** toda tela de pesquisa que mostra o resultado em tabela passa a paginar, com a mesma barra de paginação do outro sistema web (itens por página 5/10/50/100, recarregar junto da contagem, faixa "1–10 de 23", "Página 1 de 3" e botões de primeira, anterior, próxima e última página). A barra aparece sempre, mesmo com uma página só, porque é nela que mora a escolha de itens por página.

- `[x]` **35.1** Componente `components/Pagination.tsx` e utilitários `utils/pagination.ts` (`pageCount`, `clampPage`, `paginate`, `usePagination`, `usePagedRows`); estilos `.app-pagination*` no tema. Uma nova busca (filtros diferentes) e uma troca de tamanho voltam à primeira página; repetir a mesma busca (recarregar, observar um ativo, cadastrar um título) mantém a página.
- `[x]` **35.2** Lançamentos: compras e vendas e proventos paginados pela API (`page`/`page_size`, a contagem vem de `meta.total_items`; uma página esvaziada por exclusão volta à última que ainda tem linhas). Some o aviso "Mostrando 50 de N; use os filtros". Eventos corporativos paginados na tela.
- `[x]` **35.3** Pesquisar (screener, Tesouro Direto e observação), busca do comparador de ativos e busca de títulos do Tesouro no cadastro de ativo, paginados na tela (o screener e a busca do comparador passaram para a API na 35.4). Testes em `src/test/pagination.test.tsx`.
- `[x]` **35.4** Screener paginado pela API: `GET /api/v1/research/screener` e a operação MCP `research.screener` aceitam `page` (o `limit` vira o tamanho da página, até 100) e devolvem `total`, `page` e `page_size`. Busca só com filtros do catálogo pagina todos os candidatos (os 2.415 do catálogo inteiro, por exemplo) e carrega indicadores só da página; com filtros fundamentalistas, pagina o que passou na janela varrida (`scan_limit`, segue o aviso de truncado). A tela Pesquisar e a busca do comparador pedem uma página por vez (`pages/research/useScreenerSearch.ts`); antes só os 100 primeiros chegavam. Testes: `tests/test_research_screener.py`, `tests/test_research_flow.py` e `src/test/pagination.test.tsx`.

## Fase 36 — Carteiras de Comparação com o Seu Fluxo de Aportes (`[ ]` Proposta)

**Objetivo:** criar N carteiras de comparação, cada uma com uma estratégia de regras fixas sobre a base de ativos, que recebem **os mesmos aportes e resgates da carteira real, nas mesmas datas e valores**, e acompanhá-las dia a dia contra ela. Responde se a carteira vence o acaso (carteiras aleatórias com as mesmas regras ARCA), quanto a diferença vem da divisão entre classes ou da escolha dos ativos (Brinson) e que estratégias vão melhor em que regime, e gera um painel de dados para os modelos da Fase 33. Simulação, não recomendação: nada muda a política nem dispara compras. Desenho completo e teste de estresse (12 riscos) em [COMPARISON_PORTFOLIOS_DESIGN.md](../features/COMPARISON_PORTFOLIOS_DESIGN.md).

**Depende de:** Fase 33 (motor de backtest com lotes, custos, IR e visão point-in-time; camada bayesiana; validação da 33.8; laboratório da 33.9). **Ganha insumos com:** a Fase 34 (a composição otimizada vira a estratégia `OPTIMIZED`) e a Fase 28 com a extensão da CVM (fundamentos com data de publicação e cadastro com cancelamentos, que tiram o look-ahead e reduzem o viés de sobrevivência do modo retroativo).

- `[ ]` **36.0** Decisões da seção 11 do desenho: estratégias iniciais e número de carteiras aleatórias, universo, alcance do fluxo (só ARCA ou tudo), patrimônio de partida, modo retroativo, proventos, reconstituição, rebalanceamento, local da tela e tempo mínimo de registro antes do veredito.
- `[ ]` **36.1** Fluxo espelhado a partir dos lançamentos (o `net_flow` dos retratos), com o alcance escolhido.
- `[ ]` **36.2** Motor por eventos do fluxo real com valorização diária, lotes inteiros, custos, IR nas vendas e proventos datados, reaproveitando o motor da 33.2.
- `[ ]` **36.3** Interface de estratégia e o catálogo inicial (`POLICY_EQUAL`, `POLICY_BROAD`, `INDEX_ARCA`, `DIVIDENDS`, `VALUE`, `QUALITY`, `LOW_VOL`, `CDI`, `SIXTY_FORTY`), sem leitura do futuro.
- `[ ]` **36.4** Persistência (`comparison_portfolios`, `comparison_snapshots`, `comparison_trades`, migração sequencial), modos prospectivo e retroativo (rotulado) e a rotina diária `update_comparison_portfolios` no worker; mudar a regra cria uma nova versão.
- `[ ]` **36.5** Carteiras aleatórias com sementes fixas e a posição da carteira real na distribuição delas.
- `[ ]` **36.6** Métricas (TWR com Dietz modificado, TIR sobre o mesmo fluxo, risco, renda, custos), atribuição de Brinson e P(estratégia > carteira real) com intervalo.
- `[ ]` **36.7** Tela Comparar carteiras, MCP (`comparison.list|create|get|compare`), painel diário exportável, testes de UI e integração, `docker compose build`.
- `[ ]` **36.8** Estratégia `OPTIMIZED` (depois da Fase 34) e escores point-in-time (depois da extensão da CVM).

## Fase 37 — Leitura Empresarial: Narrativa e Padrão Visual (`[x]` Concluída)

**Objetivo:** cada tela de resultado conta a conclusão antes dos números, com um padrão visual único: resumo em texto (o que o resultado diz), indicadores que o sustentam, gráfico, detalhe e, no fim, "Como ler este resultado" (premissas e limites da amostra). Nada de avisos espremidos em colunas, blocos colados, texto de gráfico que cresce com a tela ou "(s)" no lugar do plural.

- `[x]` **37.1** Base visual: `components/Section.tsx` (`Section`, `Lead`, `KpiGrid`, `Notes`, `Segmented`), tokens de ritmo vertical (`--block-gap`), espaço entre blocos irmãos fora de pilhas, `fieldset` sem moldura do navegador com legenda em sobrelinha, filtros com largura do conteúdo, títulos de página maiores, linha selecionada nas tabelas de histórico; `plural()` no front (`utils/format.ts`) e no domínio (`domain/shared/text.py`) nas mensagens de saúde, alertas e candidatos.
- `[x]` **37.2** Gráficos desenhados na largura real do contêiner (`viz/useChartWidth.ts`): o texto mantém 11 px em qualquer tela; escala com números redondos, eixo de datas com até 5 marcas, rótulo final em duas linhas (nome e valor curto) sem sobreposição e valor completo na leitura do ponto.
- `[x]` **37.3** Simular carteira: a pergunta da aba como cabeçalho, formulários que recolhem quando já há resultados, e em cada aba resumo + indicadores + gráfico + detalhe + notas. Passado compara com o mesmo fluxo no CDI e avisa quando quase tudo terminou em Caixa (ativos fora da elegibilidade nas datas simuladas); Futuro com mediana, faixa de 90% e chance da meta; Candidatos com o mais promissor e os excluídos agrupados por motivo; Robustez, Confiança e Laboratório com o veredito em texto.
- `[x]` **37.4** Ativo: gráfico de preço com 6 meses, 1, 2 e 5 anos e todo o histórico (`GET /api/v1/assets/{id}/prices`, MCP `assets.prices`, até 500 pontos, sem os erros pontuais de cotação), variação, máxima e mínima do período; resumo da posição em texto na aba Resumo.
- `[x]` **37.5** Comunicados da CVM: filtro na largura do conteúdo, espaço entre os cartões do Início e documentos entregues há mais de 30 dias chegando já lidos (migração `script_00025` para a primeira carga).
- `[x]` **37.6** Padrão aplicado às demais telas: Saúde (pior checagem e pilar no resumo, contagem por situação, pilares como seções), Desempenho (retorno, distância do CDI e queda máxima, indicadores do período), Carteira (valor, resultado e a classe mais fora da banda; resumo por classe em cada aba), Aportar (como funciona e para onde vai o dinheiro do plano), Estratégia (regras em vigor num parágrafo) e Pesquisar (quantos passaram pelos filtros); plural no lugar de "(s)".
- `[x]` **37.7** Início: o cartão Patrimônio separa Bolsa (Caixa, Ações e Real Estate) de Internacional, com o peso, o valor e a alta ou queda de cada um sobre o investido.
- `[x]` **37.8** Início: os demais cartões trazem a composição do número (resultado em valorização, vendas e proventos; rentabilidade contra CDI e Ibovespa; média mensal e último mês de proventos; peso da reserva), alinhados no pé do cartão.

## Fase 38 — Cotações Persistidas: o Worker Atualiza, as Telas Leem do Banco (`[x]` Concluída)

**Objetivo:** nenhuma tela espera um provedor de mercado. Com 2.424 ativos cadastrados (lista de observação inflada por um agente), o relatório levava de 50 a 120 s e os alertas 200 s, porque cada requisição cotava todos os ativos ao vivo e o cache do Redis (5 min) expirava antes de o worker terminar a passada (de 24 a 50 min). Agora o worker grava as cotações no banco e as telas só leem.

- `[x]` **38.1** Tabela `market_data` (migração `script_00026`): última cotação e últimos fundamentos por ticker, cada parte com a hora da busca; repositório `market_data` na Unit of Work; `transactions.traded_asset_ids()` separa posições da observação.
- `[x]` **38.2** Worker: `warm_portfolio_quotes` grava as cotações dos ativos com lançamento a cada 5 min (também na partida do worker e sob pedido) e `refresh_watchlist_quotes` as da observação a cada 60 min; fundamentos só quando têm mais de 24 h; uma falha do provedor mantém o valor anterior.
- `[x]` **38.3** Leitura pelo banco (`infra/providers/stored.py`) no relatório, ciclo de vida/elegibilidade, saúde, alertas, observação e candidatos; só um ticker nunca gravado vai ao provedor, uma vez. Comparador e screener do catálogo continuam ao vivo (tickers fora do cadastro).
- `[x]` **38.4** `GET /api/v1/market/quotes/status` e MCP `market.quote_status` (idade das cotações das posições, quantas defasadas além de 30 min); `warm_portfolio_quotes` entra nos jobs sob pedido (`POST /market/job-runs/warm_portfolio_quotes/request`, MCP `market.request_job`).
- `[x]` **38.5** Início: "Cotações de HH:MM" com as posições defasadas e o botão "Atualizar", que pede a rotina ao worker e recarrega quando chegam cotações novas.
- `[x]` **38.6** Câmbio USD/BRL gravado com as posições (`USDBRL=X` em `market_data`) e fundamentos de um ativo (checklist e análise) lidos do banco.

## Fase 39 — Todo Dado Exibido Sai de Tabela Própria (`[x]` Concluída)

**Regra (pedido do usuário):** todo dado mostrado na aplicação tem tabela de persistência, para carregamento rápido, auditoria (de onde veio, quando e o que mudou) e acesso sem depender do provedor. O worker é o único que fala com os provedores; as telas leem do banco. O que ainda sai do provedor ou do Redis:

- `[x]` **39.1** Auditoria das cotações: `market_quote_history` (migração `script_00027`) guarda o último preço de cada ticker por dia, com provedor, situação e hora, a cada gravação em `market_data`; `GET /api/v1/market/quotes/{ticker}/history` e MCP `market.quote_history`.
- `[x]` **39.2** Histórico diário de preço em `asset_price_history` (chave ticker + dia): a rotina `sync_price_history` (dias úteis após o catálogo, na partida e sob pedido) carrega o histórico inteiro uma vez e depois o último mês; gráfico do ativo, risco da análise, saúde e comparador leem da tabela.
- `[x]` **39.3** Proventos declarados em `market_data`: a rotina `refresh_distributions` (a cada `DISTRIBUTIONS_REFRESH_HOURS`, na partida e sob pedido) grava o que a B3 publica, sem apagar o que já estava quando o provedor responde vazio; agenda do Início, importação B3 e MCP leem do banco.
- `[x]` **39.4** CDI e IPCA anuais calculados das séries de `market_series` (mesma conta do provedor, `domain/market/services/macro.py`) no relatório, na análise, na saúde, nos impostos e na simulação; o BCB só é chamado sem séries.
- `[x]` **39.5** Indicadores do catálogo em `market_data` pela rotina `refresh_catalog_fundamentals` (dias úteis, uma hora após o catálogo); screener e comparador leem do banco e gravam o que buscarem de um ticker nunca visto.
- `[x]` **39.6** Títulos do Tesouro na busca da Pesquisa já liam de `treasury_catalog` (o provedor só preenche a tabela vazia, uma vez).
- `[x]` **39.7** Câmbio na confirmação de aporte lido de `market_data` (`USDBRL=X`, atualizado com as posições a cada 5 min).
- `[x]` **39.8** Proteção das buscas ao vivo que restam (ticker nunca gravado): no máximo 25 por requisição e nunca para ativo arquivado.

## Fase 40 — Fatos Relevantes, Patrimônio por Conta, Navegação e Exclusão de Simulações (`[x]` Concluída)

**Objetivo (pedido do usuário):** tirar do Início o que tem tela própria, mostrar onde está o dinheiro, navegar com trilha e voltar sem perder nada, e poder excluir simulações.

- `[x]` **40.1** Página Fatos relevantes (`/disclosures`), no menu logo abaixo de Saúde da carteira, com as notas de leitura; o Início deixa de ter o cartão e o alerta de fato relevante sem ativo leva à página.
- `[x]` **40.2** Início: "Patrimônio por conta" com cada conta em Bolsa (Caixa, Ações e Real Estate) e Internacional, valor, peso e alta ou queda sobre o investido (`GET /api/v1/portfolio/by-account`, MCP `portfolio.by_account`, regra única em `domain/portfolio/services/market_split.py`).
- `[x]` **40.3** Breadcrumb em todas as páginas, na barra do topo, com "Voltar": as seções ficam sob o Início e uma página de detalhe (ativo, plano de aporte, lançamento) fica sob a página de onde foi aberta; cada link volta ao endereço que a página tinha. Filtros, a última busca do screener e a rolagem voltam com a página (`utils/storedState.ts`, sessão do navegador).
- `[x]` **40.4** Excluir simulação: exclusão lógica (`simulation_runs.deleted_at`, migração `script_00028`) que tira a rodada de toda lista, consulta, reaproveitamento e fila, sem rota de recuperação; botão na lista de cada aba e MCP `simulation.delete`.
- `[x]` **40.5** O ativo sugerido no plano de aporte abre a página do ativo; o "Voltar" retorna ao plano com as quantidades, preços, data e conta digitados.

## Fase 41 — Simular Carteira: Nova Experiência em Estudos e Capítulos (`[x]` Concluída)

**Objetivo:** trocar as seis abas independentes por estudos que contam uma história: premissas definidas uma vez, capítulos De onde viemos (passado + robustez), Para onde vamos (futuro + confiança) e O que pode melhorar (candidatos sobre a mesma projeção), conclusão com próximos passos, e resultados guardados, comparáveis e refeitos com os dados de hoje. Desenho: [SIMULATION_EXPERIENCE_DESIGN.md](../features/SIMULATION_EXPERIENCE_DESIGN.md).

- `[x]` **41.0** Decisões da seção 8 aprovadas como recomendadas (estudo com capítulos, estudo completo como padrão, quatro níveis do selo, respostas de hoje no passado com aviso, Laboratório nos bastidores, todas as versões guardadas, último estudo no Início) e mock aprovado.
- `[x]` **41.1** Laboratório: cada modelo guarda o acerto acumulado mês a mês sobre a regra simples e o gráfico mostra o modelo escolhido na tabela (o aprovado por padrão), dizendo se passou; o regime de estresse só aparece com o HMM; veredito e colunas em linguagem de decisão, com o termo técnico na dica.
- `[x]` **41.2** Estudo no backend: `simulation_studies` e rodadas com `study_id`/`chapter` (migração `script_00029`, que converte cada rodada existente num estudo de um capítulo); `/api/v1/studies` (criar, listar, obter, versões, atualizar, variação, comparar, excluir) e MCP `study.*`; o backtest ganha `answers_mode` (respostas de hoje no período inteiro).
- `[x]` **41.3** Conclusão, resumos de capítulo e selos "Quanto confiar" (robustez pelas variantes contra o CDI e pior crise; confiança pela cobertura da faixa de 90% do gerador combinado) como funções puras em `domain/simulation/studies.py`.
- `[x]` **41.4** Lista de estudos com o principal em destaque e o assistente em 3 passos (pergunta, premissas, revisão).
- `[x]` **41.5** Página do estudo: conclusão com próximos passos (variação, comparador, Aportar), índice, capítulos com os resultados e os selos, premissas e versões.
- `[x]` **41.6** Comparar estudos capítulo por capítulo, versões com a chance da meta, cartão do último estudo no Início e versão para impressão/PDF.
- `[x]` **41.7** "Qualidade dos modelos" (`/tools/simulation/quality`) com confiança e Laboratório; as seis abas, os três formulários e as listas de rodadas foram removidos.
- `[x]` **41.8** Migração das rodadas atuais, testes de unidade, de UI e de integração e `docker compose build`. De quebra: `parseDecimal` passou a ler "1.200.000" como milhar, e os candidatos do screener voltaram a gravar os indicadores (chamada sem Unit of Work desde a 39.5).

## Fase 42 — Previsão Probabilística do Preço dos Ativos (`[~]` Em andamento)

**Objetivo:** a faixa provável do preço de cada ativo em 3, 6, 12 e 24 meses e a chance de passar de valores que importam (preço de hoje, preço médio, preço teto, queda de 20%), com a confiança medida. São três camadas bayesianas, cada uma só entra se melhorar a previsão fora da amostra: A, mercado e classe (reaproveita o modelo dos candidatos da Fase 33); B, fundamentos da CVM com data de entrega (DFP/ITR); C, eventos da CVM (IPE) por estudo de eventos hierárquico. Desenho: [ASSET_PRICE_FORECAST_DESIGN.md](../features/ASSET_PRICE_FORECAST_DESIGN.md). Feita antes das Fases 34 e 36, a pedido; a 42.2 destrava 34.9 e 36.8.

- `[x]` **42.0** Decisões da seção 10 do desenho: horizontes 3/6/12/24 meses; preço com o retorno total ao lado; universo de estimação carteira + watchlist + catálogo mais líquido; CVM desde 2010; só exibe com selo ≥ "Use com cautela"; sem LLM nos PDFs; alerta criado e desligado; antes das Fases 34 e 36.
- `[x]` **42.1** Camada A por ativo (`domain/forecast`): excesso sobre o CDI = α + β·classe + ε, com α encolhido pela dispersão da classe e β puxado para 1, nos caminhos da mistura calibrada; o preço desconta os proventos (diferença TR − PX). Tabelas `asset_forecasts` e `forecast_calibrations` (migração `script_00030`); jobs `refresh_asset_forecasts` (diário) e `calibrate_forecasts` (semanal, origem móvel: cobertura das faixas de 50% e 90%, PIT, Brier de bater o CDI), também manuais; `GET /assets/{id}/forecast` e `GET /market/forecast-quality`; MCP `assets.forecast` e `market.forecast_quality`; aba "Probabilidades" com resumo, chances (hoje, preço médio, preço justo, queda de 20%), faixa por horizonte, calculadora de preço, "o que pesou" e selo; oculta enquanto o selo estiver abaixo de "Use com cautela".
  - `[x]` Previsão sob pedido, só do ativo: botão "Calcular só para este ativo" na aba e `POST /assets/{id}/forecast` (MCP `assets.forecast_refresh`). O pedido aceita a partir de 12 meses de histórico e mostra a previsão mesmo com selo baixo, com avisos de confiança ("Leia com cautela"); o ativo pedido segue acompanhado no cálculo diário. "Rodar agora" em Dados de mercado virou uma lista com descrição, última execução e botão de cada rotina.
- `[x]` **42.2** DFP/ITR point-in-time: tabelas `cvm_statements` (métricas de cada balanço e versão, com a data de entrega) e `cvm_statement_loads` (migração `script_00031`); leitura dos ZIPs anuais da CVM por streaming, filtrada pelas empresas com código de negociação; três modelos de plano de contas (empresa, banco, seguradora), contas livres de depreciação e dividendos pagos achadas pelo nome, escala mil/unidade e quantidade de ações informada em milhares corrigidas; últimos 12 meses reconstruídos do acumulado do ITR com a última DFP; job `sync_cvm_statements` (diário: confere os dois últimos anos pelo Last-Modified e traz o histórico desde 2010 alguns arquivos por vez, também manual); `domain/forecast/valuation_pit.py` (P/L, P/VP, EV/EBITDA, dividendos/valor com o balanço conhecido na data); `GET /assets/{id}/statements`, MCP `assets.statements` e a seção "Balanços entregues à CVM" na aba Fundamentos.
- `[x]` **42.3** Camada B (`domain/forecast/valuation_model.py`): a cada mês, quatro rendimentos (lucro, patrimônio, EBITDA/EV e dividendos sobre o valor) com o último balanço entregue e o preço do mês; o valor de mercado desfaz o ajuste de desdobramentos e bonificações do Yahoo (série `SIM:SPLIT:`, guardada pelo histórico da simulação). z de valuation = média do z frente ao próprio passado e do z frente ao setor (centro do setor puxado para o mercado), limitado a ±3. γ por Fama-MacBeth com erro alargado pela sobreposição das janelas de 12 meses, prior cético N(0; 0,2% ao mês por z) e γ por setor puxado para o global. Portão por origem móvel anual: só entra se reduzir o erro fora da amostra no total e na maioria dos anos e se o sinal tiver ≥ 90% de confiança; senão γ = 0 e a nota diz que não foi usado. Na previsão, o α é encolhido para γ·z (antes, para zero) e "O que pesou → Valuation" mostra essa parte. Tabela `forecast_models` (migração `script_00032`); job semanal `estimate_forecast_models` (também manual); `GET /market/forecast-quality` e o MCP `market.forecast_quality` trazem o resultado do portão.
- `[ ]` **42.4** IPE histórico, taxonomia de eventos e estudo de eventos hierárquico.
- `[ ]` **42.5** Camada C: efeito dos eventos recentes, com portões e "o que pesou".
- `[ ]` **42.6** Negociações de administradores (VLMO), se houver o conjunto estruturado.
- `[ ]` **42.7** Integração com os estudos, alerta opcional, testes de UI e integração, `docker compose build`.

## Fase 43 — Garimpo: Achados no Catálogo Inteiro (`[~]` Em andamento)

**Objetivo:** procurar, em todas as ações líquidas com balanço na CVM, empresas que ninguém está olhando e que os dados dizem merecer um olhar (valor, qualidade, melhora dos fundamentos, momentum e, depois, eventos e administradores), com pesos bayesianos, portões fora da amostra, PBO, custos e um placar dos achados contra a classe e o acaso. Um achado vira candidato só quando você o segue. Desenho: [ASSET_MINING_DESIGN.md](../features/ASSET_MINING_DESIGN.md).

- `[x]` **43.0** Decisões da seção 9 do desenho, aprovadas com as recomendações: liquidez acima de R$ 1 milhão por dia, até 10 achados por semana, sinais de valor, qualidade, melhora e momentum, antes de 42.4–42.7, alerta criado e desligado.
- `[x]` **43.1** Universo (`domain/mining/universe.py`): ações brasileiras do catálogo com CNPJ no mapa da CVM e volume médio diário acima do piso (`MINING_MIN_DAILY_VOLUME`; o volume da última sessão enquanto o indicador não existe), uma classe por empresa (a mais líquida). Job `sync_mining_universe` (dias úteis, também manual): recarrega o histórico longo (retorno total, preço e desdobramentos) dos papéis com histórico de mais de uma semana, os mais antigos primeiro, `MINING_HISTORY_BATCH` por vez; a gravação é a mesma do histórico da simulação (`store_long_history`). `GET /research/mining/universe` e MCP `research.mining_universe` mostram o universo e a cobertura.
- `[ ]` **43.2** Sinais point-in-time e `mining_signals`.
- `[ ]` **43.3** Pesos bayesianos, portões, PBO e custos.
- `[ ]` **43.4** Achados semanais, `mining_findings`, página "Garimpo", "Seguir" e MCP.
- `[ ]` **43.5** Placar dos achados contra a classe e o acaso.
- `[ ]` **43.6** Eventos e administradores como sinais (depois de 42.4–42.6).


## Fase 43 — Campos de Seleção com Busca (`[x]` Concluída)

**Objetivo:** todo campo de escolha única filtra as opções enquanto se digita e só aceita um valor da lista; e os seletores de ativo enxergam o catálogo inteiro, não só os 200 primeiros tickers.

- `[x]` **43.1** `GET /assets` lido página a página no cliente (`api.assets.list`): a API serve no máximo 200 por página, e os seletores paravam no 200º ticker.
- `[x]` **43.2** Componente `Combobox` (filtro sem acento nem caixa, todas as palavras em qualquer ordem; setas, Enter, Escape; texto sem correspondência volta à escolha atual; opção vazia como placeholder; lista limitada a 100 itens com aviso para refinar; lista em posição fixa para não ser cortada em tabelas). Substitui todos os `<select>` de escolha única.
- `[x]` **43.3** Página do estudo: espaço entre o resumo e o corpo, sem margem dobrada entre os cartões, índice lateral fixo ao rolar em telas largas.
- `[x]` **43.4** Testes de unidade do `Combobox` e da leitura paginada, testes de UI e e2e ajustados, `docker compose build web`.
