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
| **Fase 6** | Validação End-to-End no Docker Compose, CI/CD GitHub Actions e Publicação no GitHub Privado | `[~]` Em andamento | 95% |
| **Fase 7** | Fundação de Correção: Git, rede de testes de regressão, convenções de unidades (ADR 0006) | `[x]` Concluída | 100% |
| **Fase 8** | Correção dos Motores de Cálculo (CDI, câmbio, renda fixa, analytics, integridade do livro) | `[x]` Concluída | 100% |
| **Fase 9** | Configuração, Segurança, Infraestrutura Docker, Worker e CI | `[x]` Concluída | 100% |
| **Fase 10** | Domínio do Framework Operacional: Política de Investimento, Contas, Ciclo de Vida do Ativo e ARCA com Bandas | `[x]` Concluída | 100% |
| **Fase 11** | Módulo Fundamentalista: Histórico, Screener, Watchlist, Checklists e Valuation por Tipo | `[x]` Implementado | 100% |
| **Fase 12** | Operação: Aporte Executável, Alertas, Importação B3 e Eventos Corporativos | `[x]` Implementado | 100% |
| **Fase 13** | Frontend no Modelo de Referência (ADR 0005 e ADR 0007) | `[x]` Implementado | 100% |
| **Fase 15** | Refatoração Estrutural por Módulos (`apps/packages/*`, `apps/worker`, `fincontrol_api`) | `[x]` Concluída | 100% |
| **Fase 16** | Pesquisa e Importação Integradas (Cadastro Único de Ativos) | `[x]` Concluída | 100% |
| **Fase 17** | Arquitetura Unificada de Backend em Camadas por Domínio em `apps/api` (ADR 0009) | `[x]` Concluída | 100% |
| **Fase 18** | Configuração Agêntica e Servidor MCP Pessoal (`/settings/agentic`, `/api/v1/mcp`) | `[x]` Concluída | 100% |
| **Fase 19** | Notificações de Erros de Requisição do Worker (Badge no menu e Log detalhado em Dados de Mercado) | `[x]` Concluída | 100% |
| **Fase 22** | Importação B3: Tesouro Direto, CDB e Fracionário com Dígito | `[x]` Implementado | 100% |
| **Fase 24** | Tributação Regressiva por Ativo e Comparador Tributado × Isento | `[x]` Implementado | 100% |

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

## Fase 6 — Docker Compose End-to-End, CI/CD e GitHub (`[~]` Em andamento)

**Objetivo:** Validar toda a solução rodando em containers com volumes isolados, configurar pipeline de integração contínua e publicar no repositório GitHub privado.

### Itens Implementados
- `[x]` **6.1** Dockerfiles multi-stage (`apps/api/Dockerfile`, `apps/worker/Dockerfile`, `apps/web/Dockerfile` com `apps/web/nginx.conf` fazendo proxy para `/api`) e `.dockerignore`.
- `[x]` **6.2** Pipeline `.github/workflows/ci.yml` executando lint (`ruff`, `tsc`), testes de unidade, testes de integração (com validação das migrations `script_#####`) e `docker compose build`.
- `[x]` **6.3** **Teste de Integração End-to-End (Fase 6):** `docker compose up --build -d` validado com execução automática do `migrate` (`script_00001`), sincronização real do `worker` com o BCB SGS (CDI, SELIC, IPCA) e benchmarks, healthcheck da API (`:8000` e proxy `:8080`), resposta `200 OK` do frontend e persistência de dados nos volumes isolados `fincontrol_pgdata` e `fincontrol_redisdata` após `docker compose restart`.

### Item Pendente
- `[ ]` **6.4** Criar repositório privado `Angelicogfa/financial-control` no GitHub, realizar commits semânticos em inglês e fazer push.

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

## Fase 24 — Tributação Regressiva por Ativo e Comparador Tributado × Isento (`[x]` Implementado)

**Objetivo:** mostrar, por ativo e por aplicação, quanto imposto sai no resgate hoje e quanto se economiza esperando a próxima faixa, e comparar títulos tributados e isentos pelo valor líquido — com as alíquotas guardadas como dados com vigência, sem custo novo (só legislação pública). Regras verificadas em out/2026: a MP 1.303/2025 caducou em 08/10/2025 (sem alíquota única de 17,5%; LCI/LCA/CRI/CRA/debêntures incentivadas seguem isentas); JCP com 17,5% retidos desde 01/01/2026 pela LC 224/2025 (não pela Lei 15.270/2025, que trata dos dividendos acima de R$ 50 mil/mês).

- `[x]` **24.1** Tabela de alíquotas com vigência: `domain/tax` (`TaxRule`, `TaxBracket`, `TaxRuleBook` — sem sobreposição por regime; datas anteriores ao primeiro registro usam o primeiro) com regimes de renda fixa regressiva, isentos, IOF, ações, ETFs/BDRs, FII (ganho e rendimentos), dividendos, JCP, exterior e cripto; registro embutido `DEFAULT_TAX_RULES` e tabela `tax_rules` (migration `script_00019_tax_rules.py`, semeada com os mesmos registros) exposta como `uow.tax_rules`. `regressive_ir_rate`/`regressive_iof_rate` e o motor de renda fixa (`value_fixed_income_position`, `consolidate_portfolio`) leem a regra vigente na data do resgate/avaliação; o relatório da carteira usa os registros do banco. Resultados atuais inalterados (golden e caracterização passam).
- `[x]` **24.2** Situação tributária por lote (`domain/tax/services/status.py`): `replay_lots` exposto pelo motor; por aplicação, alíquota atual, IOF devido e data em que zera, data e dias até a próxima faixa (descartada quando cai depois do vencimento), IR estimado hoje × na próxima faixa (projeção pelas taxas anuais), IR economizado e ganho líquido de esperar; para renda variável, os regimes informativos do tipo com alíquota vigente e base legal.
- `[x]` **24.3** Comparador (`domain/tax/services/comparator.py`): indexadores `CDI_PERCENT`, `CDI_SPREAD`, `IPCA_SPREAD` e `PRE`; cenários `LOW`/`BASE`/`HIGH` das premissas da política (`ProjectionAssumptions.projected_cdi_rate`, `projected_ipca_rate`, `scenario_rate_shift`; vazio usa o CDI/IPCA de mercado) ou informados; IR/IOF sobre o ganho acumulado; valor e taxa líquidos anualizados em 252 dias úteis no vencimento e na janela comum (menor prazo, resgate bloqueado por carência sinalizado); taxa equivalente por faixa; ponto de empate em dias (a partir de quando o vencedor fica à frente até o fim da janela).
- `[x]` **24.4** `TaxHandler` (`domain/tax/services/use_cases.py`) e rotas `GET /api/v1/tax/rules`, `GET /api/v1/tax/assets/{asset_id}/status` e `POST /api/v1/tax/fixed-income/compare` (ofertas à mão ou por `asset_id`, completadas pelo cadastro); operações MCP `assets.tax_status`, `tools.fixed_income_compare` e `tools.tax_rules` (contexto `tools`) e instruções do servidor MCP.
- `[x]` **24.5** Interface web: aba **Tributação** no detalhe do ativo (`TaxTab.tsx`: faixa, próxima queda, IR estimado por aplicação, tabela regressiva ou regimes da renda variável) com atalho para o comparador; página **Comparar renda fixa** (`/tools/fixed-income`, seção "Ferramentas" do menu) com títulos à mão ou da carteira, cenários, janela comum, taxas equivalentes e empate; premissas do comparador na tela Estratégia; tipos regenerados (`scripts/gen_web_types.py`).
- `[x]` **24.6** Testes: `test_tax_rules.py` (fronteiras 180/181, 360/361, 720/721; IOF 29/30; isentos; vigência do JCP e dos dividendos; mudança legal como novo registro), `test_tax_status.py`, `test_fixed_income_comparator.py` (fórmulas por indexador, IR sobre o ganho acumulado, equivalências, janela/carência, empate em 721 dias, cenários), `test_tax_api.py` (migration e semente, rotas, novo registro mudando a avaliação, MCP) e `tax.test.tsx` (aba e comparador).

**Validação (2026-10-27):** `scripts/check.sh` → ruff e formatação limpos; suíte de backend com cobertura de 97,0%; 71 testes do frontend, lint, typecheck e build Vite; `docker compose build` das imagens `migrate`, `api`, `worker` e `web`.
