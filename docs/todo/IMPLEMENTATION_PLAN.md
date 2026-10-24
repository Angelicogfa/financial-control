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
| **Fase 2** | Domínio Puro (`packages/core`): Posições, Renda Fixa Calculada, Proventos, Consolidação, ARCA e Cerrado Opcional | `[x]` Concluída | 100% |
| **Fase 3** | Provedores de Mercado (`brapi`, `yfinance`, `BCB SGS` CDI/IPCA), Cache Redis e Motor Estatístico/Benchmarks | `[x]` Concluída | 100% |
| **Fase 4** | Backend API (`apps/api` Controllers $\rightarrow$ Handlers $\rightarrow$ Services $\rightarrow$ UoW) e Worker (`apps/worker`) + Testes de Integração | `[x]` Concluída | 100% |
| **Fase 5** | Frontend Web (`apps/web` React + TypeScript): Menu Hambúrguer, Cards Evolução/Projeção e Tabelas Paginadas | `[x]` Concluída | 100% |
| **Fase 6** | Validação End-to-End no Docker Compose, CI/CD GitHub Actions e Publicação no GitHub Privado | `[~]` Em andamento | 95% |
| **Fase 7** | Fundação de Correção: Git, rede de testes de regressão, convenções de unidades (ADR 0006) | `[x]` Concluída | 100% |
| **Fase 8** | Correção dos Motores de Cálculo (CDI, câmbio, renda fixa, analytics, integridade do livro) | `[x]` Concluída | 100% |
| **Fase 9** | Configuração, Segurança, Infraestrutura Docker, Worker e CI | `[ ]` Pendente | 0% |
| **Fase 10** | Domínio do Framework Operacional: Política de Investimento, Contas, Ciclo de Vida do Ativo e ARCA com Bandas | `[ ]` Pendente | 0% |
| **Fase 11** | Módulo Fundamentalista: Histórico, Screener, Watchlist, Checklists e Valuation por Tipo | `[ ]` Pendente | 0% |
| **Fase 12** | Operação: Aporte Executável, Alertas, Importação B3 e Eventos Corporativos | `[ ]` Pendente | 0% |
| **Fase 13** | Frontend por Contexto de Operação (ADR 0005) | `[ ]` Pendente | 0% |
| **Fase 14** | Validação Operacional 100% (E2E, documentação e aceite) | `[ ]` Pendente | 0% |

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
- `[x]` **1.1** Criar estrutura de pacotes `packages/core`, `packages/persistence`, `apps/api`, `apps/worker` e `apps/web`.
- `[x]` **1.2** Implementar Entidades Imutáveis de Domínio (`entities.py`), Primitivas Padronizadas de Paginação (`pagination.py`) e Contratos/Ports (`AbstractRepository` em `ports/repositories.py` e `AbstractUnitOfWork` em `ports/unit_of_work.py`).
- `[x]` **1.3** Implementar modelos SQLAlchemy 2.0 (`models.py`) e mapeadores bidirecionais (`mappers.py`) em `packages/persistence` (código 100% em inglês):
  - `AssetModel` (`assets`) $\leftrightarrow$ `AssetEntity`
  - `FixedIncomeTermModel` (`fixed_income_terms`) $\leftrightarrow$ `FixedIncomeTermEntity`
  - `TransactionModel` (`transactions`) $\leftrightarrow$ `TransactionEntity`
  - `EarningModel` (`earnings`) $\leftrightarrow$ `EarningEntity`
  - `ArcaTargetModel` (`arca_targets`) $\leftrightarrow$ `ArcaTargetEntity`
  - `MarketSeriesModel` (`market_series`) $\leftrightarrow$ `MarketSeriesPoint`
  - `PortfolioSnapshotModel` (`portfolio_snapshots`) $\leftrightarrow$ `PortfolioSnapshotEntity`
- `[x]` **1.4** Configurar Alembic em `packages/persistence/migrations/` com `file_template = script_%%(slug)s` e criar a migration inicial `script_00001_initial_schema.py` (com seed das 4 metas ARCA padrão de 25%).
- `[x]` **1.5** Implementar Repositórios SQLAlchemy concretos (`repositories.py`) com paginação, ordenação e filtros padronizados, sem chamadas diretas a `commit()`, e `SqlAlchemyUnitOfWork` (`unit_of_work.py`) gerenciando atomicidade transacional.
- `[x]` **1.6** Criar `docker-compose.yml` com serviços `postgres`, `redis`, `migrate`, `api`, `worker`, `web` e volumes isolados `fincontrol_pgdata` e `fincontrol_redisdata`.
- `[x]` **1.7** **Testes de Unidade (Fase 1):** 6 testes unitários passando (`test_domain_entities.py` e `test_unit_of_work.py`).
- `[x]` **1.8** **Testes de Integração e Build Docker (Fase 1):** 2 testes de integração passando (`test_phase1_integration.py`) validando `upgrade head` / `downgrade base` da migration `script_00001`, paginação/ordenação/filtros via `SqlAlchemyUnitOfWork` e build Docker do serviço `migrate`.

---

## Fase 2 — Domínio Puro (`packages/core`): Posições, Renda Fixa, Proventos, Consolidação, ARCA e Cerrado (`[x]` Concluída)

**Objetivo:** Implementar todas as regras financeiras e de carteira em Python puro (`packages/core`), totalmente independentes de framework web ou banco.

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
- `[x]` **2.8** **Testes de Unidade (Fase 2):** Suite `packages/core/tests/test_phase2_domain.py` validando todos os motores de domínio puro em memória.
- `[x]` **2.9** **Testes de Integração e Build Docker (Fase 2):** Suite `packages/persistence/tests/test_phase2_integration.py` validando `SqlAlchemyUnitOfWork` + `consolidate_portfolio` + `plan_contribution` ponta a ponta sobre o banco migrado com `script_00001` e build Docker validado.

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
- `[x]` **3.6** **Testes de Unidade (Fase 3):** Suite `packages/core/tests/test_phase3_market_and_analytics.py` validando provedores com `httpx.MockTransport` / mocks determinísticos e todas as métricas estatísticas.
- `[x]` **3.7** **Testes de Integração e Build Docker (Fase 3):** Suite `packages/persistence/tests/test_phase3_integration.py` validando `CachedMarketGateway` + `SqlAlchemyUnitOfWork` (`uow.market_series`, `uow.snapshots`) + `analytics.py` e build Docker validado.

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
- `[x]` **7.2** (O-05) Testes de caracterização que reproduzem C-01..C-04, I-01..I-05, I-09, I-10, A-04 (marcados `xfail(strict=True, raises=...)` até a correção, para que a correção os "desmarque"): `packages/core/tests/test_audit_characterization.py`, `apps/api/tests/test_audit_characterization_api.py`, `apps/worker/tests/test_audit_characterization_worker.py` (23 casos).
- `[x]` **7.3** (I-02) **ADR 0006 — Convenções de unidades:** taxas sempre como fração decimal (`0.065` = 6,5%); percentual de indexador como multiplicador (`1.10` = 110% do CDI); séries do BCB armazenadas com unidade explícita; dinheiro em `Decimal`/`Numeric` em persistência e fronteiras de API; `float` apenas em estatística.
- `[x]` **7.4** Carteira de referência (ação BR, FII, ETF internacional em USD, cripto, CDB CDI, LCI, Tesouro IPCA+) em `packages/core/tests/golden/reference_portfolio.json`, exposta pelas fixtures de `packages/core/tests/conftest.py`. Os valores esperados (`reference_portfolio_expected.csv`, 53 linhas) são gerados por `build_reference_golden.py`, cálculo independente só com a biblioteca padrão (substitui a planilha); 18 linhas afetadas por C-01, C-02 e I-01 estão em `xfail` estrito.
- `[x]` **7.5** Cobertura no CI com `pytest-cov` e piso inicial (`packages/core` ≥ 85%, hoje 87% só com testes em memória após `test_market_gateway_and_cache.py`), elevado ao final da Fase 14.

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
- `[x]` **8.5** (I-01) IPCA+ pela série mensal 433 com pró-rata do mês corrente (último IPCA conhecido ou projeção da política); SELIC pela série 11; calendário de feriados nacionais (fixos + móveis via Páscoa) em `packages/core/calendar.py`; projeção 12m relativa a `as_of_date`. Convenção: IPCA do mês aplicado pró-rata por dias úteis do mês; mês sem índice usa a taxa anual de fallback e reduz `curve_coverage`. Projeção = variação do valor líquido em 252 dias úteis (ou até o vencimento), incluindo a mudança de faixa do IR.

### Consolidação e câmbio
- `[x]` **8.6** (C-02) Custo em BRL pelo câmbio de cada compra (`total_cost_brl`), lucro realizado em BRL pelo câmbio da venda, valor atual pelo câmbio atual; novo campo `fx_pnl_brl` separando efeito câmbio de efeito preço. Proventos em moeda estrangeira ganham `fx_rate` (migration `script_00004_earnings_fx_rate.py`, default 1 para BRL e câmbio histórico do dia para USD via backfill). Lançamentos e proventos de ativos em moeda estrangeira passam a exigir câmbio (`400 FX_RATE_REQUIRED`).
- `[x]` **8.7** (I-11) Projeções 12m lidas da `ValuationPolicy` (Fase 10) — até lá, de settings; resposta da API inclui as premissas usadas. Premissas em `ProjectionAssumptions`, configuráveis por `PROJECTION_*` no `.env` e devolvidas em `projection_assumptions`.

### Analytics
- `[x]` **8.8** (C-03) Remover o fallback para IBOV. Sem histórico suficiente, a API devolve `status: "INSUFFICIENT_HISTORY"` com `available_points`; a UI mostra estado vazio explicativo.
- `[x]` **8.9** (C-03, I-09) Job de **backfill de snapshots** que reconstrói a série diária desde a primeira transação usando histórico de preços, câmbio histórico e curva de RF; snapshots só em dias úteis B3. `backfill_snapshots_job` roda na inicialização do worker; o snapshot diário só roda em dias úteis.
- `[x]` **8.10** (I-09) TWR com proventos como retorno (`r_t = (V_t − V_{t−1} − CF_t + D_t) / V_{t−1}`); `net_flow` derivado do livro entre snapshots consecutivos; Beta, Alpha e correlação com junção por data (interseção de calendários).
- `[x]` **8.11** (I-10) Liquidez = volume médio × preço (volume financeiro).

### Integridade e contrato
- `[x]` **8.12** (I-04) Validação do livro inteiro em criação, edição e exclusão de lançamentos (simula o livro resultante antes de persistir). Novo `PUT /transactions/{id}` e `PUT /earnings/{id}`. Exclusões/edições que quebram o livro retornam `409 LEDGER_CONFLICT`.
- `[x]` **8.13** (I-04) Consolidação tolerante: ativo com livro inválido aparece com `ledger_status: "INVALID"` e mensagem, sem derrubar a carteira.
- `[x]` **8.14** (I-05) Hierarquia de exceções de domínio (`DomainError`, `NotFoundError`, `ValidationError`, `ConflictError`) em `packages/core/errors.py`; handlers mapeiam só essas; demais exceções viram 500 com `request_id` e log.
- `[x]` **8.15** (A-04) Override `MANUAL_WEIGHT` usa `custom_class_weight`; sobra de arredondamento redistribuída entre classes por ordem de déficit.
- `[x]` **8.16** (D-02, D-04) Colunas monetárias de `portfolio_snapshots` para `Numeric(20, 2)` (`script_00005_snapshot_numeric.py`); `id` como desempate em toda ordenação paginada. O domínio mantém `float` nos snapshots (série estatística derivada, exceção registrada na ADR 0006); o repositório arredonda para centavos.
- `[x]` **8.17** Reprocessamento: comando `uv run python -m fincontrol_worker.rebuild` que ressincroniza séries e reconstrói snapshots após as correções. Também reprecifica lançamentos e proventos em USD gravados com `fx_rate = 1` usando o USD/BRL histórico. **Ação pendente na base real:** rodar `docker compose run --rm worker python -m fincontrol_worker.rebuild` após aplicar as migrations.

**Aceite:** todos os `xfail` da 7.2 passam; carteira de referência (7.4) bate com a planilha golden em ±R$ 0,01; integração + `docker compose build` verdes.

**Validação (2026-10-24):** os 23 testes de caracterização e as 53 linhas da carteira de referência passam sem `xfail`; `uv run pytest` → 202 passed (cobertura: `packages/core` 88,6% só com testes em memória, backend total 93%); `npm test` 7/7 e `npm run build`; migrations `script_00002`–`script_00005` aplicadas com dados legados e revertidas em PostgreSQL 16 descartável; `docker compose build` dos 4 serviços concluído.

**Testes ajustados durante a fase (expectativas que codificavam defeitos):** `total_invested_brl` da fase 2 (17200 → 17000, C-02); projeção da caracterização I-01 (IR de 15% fixo → faixa regressiva no horizonte); dados do teste de beta I-09 (movimento de 50% em 03/01 → 0%, para manter beta 1 com composição por intervalo); taxas contratadas dos testes antigos convertidas para a escala da ADR 0006.

---

## Fase 9 — Configuração, Segurança, Infraestrutura e CI (`[ ]` Pendente)

- `[ ]` **9.1** (I-08) Pacote `packages/config` (`fincontrol_config`) com `pydantic-settings` compartilhado por API e worker; nomes idênticos ao `.env.example`; teste que falha se existir variável no `.env.example` sem campo correspondente (e vice-versa).
- `[ ]` **9.2** (O-01) Dockerfiles multi-stage (builder com `uv sync --frozen`, runtime slim), usuário não-root, imagem da API só com `core`+`persistence`+`config`+`api`, imagem do worker só com o que usa; `HEALTHCHECK` em API e web.
- `[ ]` **9.3** (O-02) Web: copiar `package-lock.json` e usar `npm ci`.
- `[ ]` **9.4** (O-03) Postgres e Redis sem portas publicadas por padrão (acesso de desenvolvimento via `docker-compose.dev.yml`, vinculado a `127.0.0.1`); Redis com `requirepass`; `.env.example` com placeholders `change-me`.
- `[ ]` **9.5** (O-03, TD-01) Autenticação single-user: credencial definida no `.env` (hash Argon2), login emite JWT em cookie `httpOnly`/`SameSite=Strict`; todas as rotas exceto `/health` protegidas. Estrutura preparada para `users` futuramente.
- `[ ]` **9.6** Observabilidade: logs estruturados JSON com `request_id`; `/health` (liveness) e `/ready` (DB, Redis, migrations em `head`).
- `[ ]` **9.7** Worker: agenda e fuso lidos de settings; lock distribuído no Redis por job; retries com backoff; tabela `job_runs` (`script_00006_job_runs.py`) com início, fim, status e contagens — base do indicador de frescor da UI.
- `[ ]` **9.8** (D-05, I-07) Busca de cotações/fundamentos em lote e concorrente (`httpx.AsyncClient` ou pool de threads limitado), com timeout global por request; API lê preferencialmente do cache aquecido pelo worker.
- `[ ]` **9.9** (O-04) CI: versão de `uv` fixada, `uv sync --frozen`, `npm ci`, ESLint + `tsc --noEmit`, cobertura, e job de *smoke* que sobe a stack com `docker compose up -d --wait` e valida `/ready` e a página web.

**Aceite:** stack sobe do zero com `cp .env.example .env && docker compose up -d --wait`; nenhuma porta de banco exposta; rotas exigem login; CI verde.

---

## Fase 10 — Domínio do Framework Operacional (`[ ]` Pendente)

**Objetivo:** implementar a ADR 0005 no backend.

- `[ ]` **10.1** Agregado `InvestmentPolicy` (`ArcaPolicy`, `EligibilityPolicy`, `ValuationPolicy`) em `packages/core/policy/`; tabela `investment_policy` versionada (`script_00007_investment_policy.py`) migrando `arca_targets`; endpoints `GET/PUT /api/v1/policy` com validação (metas somam 100%, bandas ≥ 0).
- `[ ]` **10.2** (A-01) Bandas de tolerância por classe; `compute_allocation` devolve `band_status` (`WITHIN`, `BELOW`, `ABOVE`); aporte prioriza classes abaixo da banda.
- `[ ]` **10.3** (A-02) Campo `exposure_class` separado de `asset_type`/mercado de listagem; sugestão automática para ETFs conhecidos (lista curada em `packages/core/catalog/etf_exposure.py`) e confirmação no cadastro.
- `[ ]` **10.4** (A-03) Campo `purpose` (`ARCA`, `EMERGENCY_RESERVE`, `OTHER`); apenas `ARCA` entra na alocação e no aporte; reserva aparece separada no Início e na Carteira.
- `[ ]` **10.5** (D-01) Entidade `accounts` (corretora/banco/custódia) e `account_id` em transações e proventos (`script_00008_accounts.py`, conta "Principal" para dados existentes); unicidade de `ticker` apenas para ativos negociados em bolsa; renda fixa identificada por código gerado + emissor + vencimento.
- `[ ]` **10.6** Ciclo de vida `WATCHLIST → ELIGIBLE → HELD → REVIEW → ARCHIVED` calculado por `AssetLifecycleService` a partir da política, da posição e da avaliação fundamentalista; exposto em todas as respostas de ativo.

**Aceite:** carteira de referência consolidada com bandas, exposição, reserva separada e status de ciclo de vida corretos; testes de unidade e integração verdes.

---

## Fase 11 — Módulo Fundamentalista (`[ ]` Pendente)

- `[ ]` **11.1** (F-02) Tabela `fundamental_snapshots` (ativo, data de referência, período `ANNUAL`/`TTM`, métricas normalizadas em fração) — `script_00009_fundamental_snapshots.py`; adaptadores brapi/yfinance para demonstrativos anuais; job semanal de atualização para carteira + watchlist.
- `[ ]` **11.2** (F-02) Métricas históricas derivadas: ROE médio 5a, CAGR de receita e lucro 5a, anos com lucro, regularidade de proventos, payout médio.
- `[ ]` **11.3** (F-03) Checklists versionados por tipo e setor (`STOCK`, `BANK`, `FII_BRICK`, `FII_PAPER`, `ETF`, `INTL_STOCK`, `CRYPTO`, `FIXED_INCOME`), com perguntas `N/A` quando não aplicáveis; Cerrado como modelo padrão; ETFs com checklist próprio (taxa, índice, liquidez, tracking).
- `[ ]` **11.4** (F-04) Tabela `checklist_answers` (pergunta, valor, origem `MANUAL`/`AUTO`, evidência, `answered_at`, versão) — `script_00010_checklist_answers.py`, migrando `cerrado_answers`; score normalizado (`score / respondidas`) e elegibilidade exigindo cobertura mínima da política.
- `[ ]` **11.5** (F-03) Valuation por tipo: ações não financeiras (Graham, Bazin, P/L, EV/EBITDA), bancos (Bazin, P/VP, ROE), FII (P/VP, DY vs NTN-B, Bazin), ETF/cripto sem preço justo; yield do Bazin e aplicabilidade vindos da `ValuationPolicy`.
- `[ ]` **11.6** (F-01) Catálogo de instrumentos `instrument_catalog` sincronizado diariamente (lista de ativos B3 via brapi; cadastro manual para internacionais), com campos básicos (setor, preço, volume financeiro, valor de mercado).
- `[ ]` **11.7** (F-01) Screener `GET /api/v1/research/screener` com filtros por classe ARCA, setor, liquidez, indicadores e status de elegibilidade; métricas profundas calculadas sob demanda para a watchlist (respeitando limites do plano gratuito da brapi, com cache).
- `[ ]` **11.8** (F-01) Watchlist: `POST /api/v1/research/watchlist` cria ativo com status `WATCHLIST` sem posição; promoção para `ELIGIBLE` ao passar na política.
- `[ ]` **11.9** (F-05) `GET /api/v1/assets/{id}/analysis` reformulado: posição (se houver), histórico de fundamentos, valuation, checklist com evidências, risco vs benchmark alinhado por data, histórico do score.

**Aceite:** pesquisar um ticker não cadastrado → analisar → adicionar à watchlist → torna-se elegível → aparece no aporte; testes com fixtures de provedores gravadas.

---

## Fase 12 — Operação: Aporte, Alertas, Importação e Eventos (`[ ]` Pendente)

- `[ ]` **12.1** (I-07) Aporte persistido como `contribution_plans` (`DRAFT`, `CONFIRMED`, `DISCARDED`) — `script_00011_contribution_plans.py`; nível 2 só com ativos elegíveis; confirmação gera os lançamentos com preço/quantidade executados editáveis pelo usuário.
- `[ ]` **12.2** Motor de alertas (`packages/core/alerts.py`): classe fora da banda, ativo em `REVIEW`, preço abaixo do teto, cotação em fallback, série BCB desatualizada, livro inválido, snapshot ausente; endpoint `GET /api/v1/alerts` e dispensa por usuário.
- `[ ]` **12.3** (D-03) Importação B3 (Área do Investidor: planilhas de Negociação e Movimentação) com pré-visualização, deduplicação por hash e mapeamento de ativos desconhecidos para cadastro/watchlist.
- `[ ]` **12.4** (D-03, TD-03) Entidade `corporate_events` (desdobramento, grupamento, bonificação com custo atribuído) — `script_00012_corporate_events.py`; motor de posições aplica fatores por data; importação de eventos da Movimentação B3.

**Aceite:** importar extrato B3 de exemplo, confirmar um aporte e ver posições, alocação e alertas atualizados sem lançamentos manuais.

---

## Fase 13 — Frontend por Contexto de Operação (`[ ]` Pendente)

**Objetivo:** implementar a navegação e as telas da ADR 0005.

- `[ ]` **13.1** (O-06) Fundação: `react-router`, TanStack Query (cache, loading, erros), biblioteca de gráficos (Recharts), `react-hook-form` + `zod`, ESLint; estrutura `src/features/<contexto>/`, `src/shared/`; `App.tsx` reduzido a layout + rotas.
- `[ ]` **13.2** (I-06) Cliente HTTP tipado que propaga erros; componentes padronizados de erro, vazio e carregamento; indicador global de frescor dos dados (a partir de `job_runs`); remoção de `computeLocalContributionPlan`.
- `[ ]` **13.3** Shell: trilho lateral persistente com **Início, Carteira, Pesquisar, Aportar, Lançamentos, Desempenho, Estratégia**; drawer no mobile; topbar com macro (CDI, IPCA, USD, IBOV), frescor e `+ Lançamento`; login.
- `[ ]` **13.4** **Início:** KPIs (patrimônio, resultado total, TWR vs CDI, proventos 12m), ARCA atual vs meta com bandas, reserva de emergência separada, card do próximo aporte, lista de alertas acionáveis.
- `[ ]` **13.5** **Carteira:** posições agrupadas por classe ARCA com peso atual/alvo, status de ciclo de vida, score e margem de segurança por linha; filtro por conta; consolidação de ganho/perda (preço, câmbio, proventos, realizado).
- `[ ]` **13.6** **Detalhe do ativo** (`/assets/:id`): cabeçalho com preço/posição/status; abas Resumo, Fundamentos (gráficos históricos), Valuation, Checklist (com evidência e histórico do score), Proventos, Lançamentos.
- `[ ]` **13.7** **Pesquisar:** screener com filtros e atalho "classes abaixo da meta", watchlist, comparação lado a lado de até 4 ativos.
- `[ ]` **13.8** **Aportar:** fluxo em 4 passos (valor → distribuição por classe → ativos elegíveis e quantidades → revisar e confirmar lançamentos), com debounce e antes/depois por classe.
- `[ ]` **13.9** **Lançamentos:** livro único (ordens, proventos, eventos corporativos) com edição, exclusão validada, filtros server-side, importação B3.
- `[ ]` **13.10** **Desempenho:** curva base 100 vs benchmarks, retorno por classe vs benchmark da classe, risco (volatilidade, drawdown, VaR), proventos por mês; estado "histórico insuficiente" explícito.
- `[ ]` **13.11** **Estratégia:** metas e bandas ARCA, finalidade dos ativos, critérios de elegibilidade e checklists por tipo, premissas de valuation/projeção, contas.
- `[ ]` **13.12** Testes: Vitest + Testing Library por componente/página com MSW mockando a API; acessibilidade básica (axe) nas páginas principais.
- `[ ]` **13.13** Atualizar `docs/architecture/FRONTEND_UI_UX.md` para a nova navegação, mantendo a paleta Azul/Branco/Cinza.

**Aceite:** todas as rotas funcionam contra a API real; nenhuma regra de negócio no frontend; `npm run lint && npm test && npm run build` verdes.

---

## Fase 14 — Validação Operacional 100% (`[ ]` Pendente)

- `[ ]` **14.1** Script de dados de demonstração (`uv run python -m fincontrol_worker.seed_demo`) com a carteira de referência e 2 anos de histórico.
- `[ ]` **14.2** E2E com Playwright contra `docker compose up` cobrindo a jornada: login → definir estratégia → importar B3 → pesquisar e adicionar à watchlist → aportar e confirmar → ver Carteira, Início e Desempenho atualizados → editar/excluir lançamento → reiniciar containers e confirmar persistência.
- `[ ]` **14.3** Teste de recuperação: provedores externos offline (cotação em fallback, alertas de frescor, nenhuma tela quebrada); Redis offline (cache em memória).
- `[ ]` **14.4** (O-07) Revisão da documentação: `OVERVIEW.md`, `FEATURES_SPEC.md`, `FRONTEND_UI_UX.md`, ADRs 0002/0005/0006, `TECH_DEBT.md` (encerrar TD-01 e TD-03; manter TD-02 e TD-04) e este plano com status reais.
- `[ ]` **14.5** Piso de cobertura final: `packages/core` ≥ 90%, API/worker ≥ 80%, frontend ≥ 70%.
- `[ ]` **14.6** Encerramento: todos os achados da auditoria com item e teste correspondentes; `docker compose build` e CI verdes; push para o GitHub mediante confirmação do usuário (6.4).

**Definição de "100% operacional":** a stack sobe do zero com um comando; o usuário consegue executar o ciclo completo Estratégia → Pesquisar → Aportar → Lançamentos → Carteira/Desempenho sem editar banco ou arquivos; todos os valores da carteira de referência batem com a planilha golden; falhas externas aparecem como avisos e nunca como números falsos.

### Dependências entre fases
`7 → 8 → 10 → 11 → 12 → 14`, com `9` em paralelo a `8` (arquivos distintos) e `13` iniciando após o contrato de API da Fase 10 (13.1–13.3 podem começar logo após a Fase 8).


