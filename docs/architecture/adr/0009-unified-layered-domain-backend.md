# ADR 0009 — Arquitetura Unificada de Backend em Camadas por Domínio em `apps/api`

- **Status:** Aceito
- **Data:** 2026-10-26
- **Substitui/Evolui:** ADR 0008 (módulos e apps/packages)
- **Mantém:** ADR 0004 (camadas Controller → Handler/Service → UnitOfWork → Repository) e ADR 0001 (governança do monorepo e migrations Alembic `script_#####`).

## Contexto

Anteriormente (ADR 0008), o código do backend estava fragmentado em múltiplos pacotes do workspace `uv`:
- `apps/packages/config`
- `apps/packages/core`
- `apps/packages/persistence`
- `apps/worker`
- `apps/api/src/fincontrol_api`

Essa dispersão criava caminhos longos de importação, redundância de arquivos `pyproject.toml` e Dockerfiles separados para API, Worker e Migrações. Além disso, a segmentação das entidades e camadas nos domínios precisava de uma padronização simétrica e intuitiva, com separação explícita entre DTOs de entrada (`requests`) e saída (`responses`), interfaces abstratas de domínio (`domain/{domain}/repositories`) e implementações concretas de persistência (`infra/data/repositories`).

O usuário solicitou uma refatoração estrutural completa para unificar o backend em `apps/api`, eliminando o aninhamento `apps/api/src/fincontrol_api`, extinguindo `apps/packages` e `apps/worker`, e estabelecendo uma hierarquia uniforme orientada a domínios.

## Decisão

### 1. Unificação Completa em `apps/api/`

Todo o backend reside exclusivamente dentro de `apps/api/`. As pastas `apps/packages/`, `apps/worker/` e `apps/api/src/` foram completamente removidas.

A estrutura de diretórios foi reorganizada da seguinte forma:

```text
apps/api/
├── main.py                       # App factory: inicialização do FastAPI, CORS, middlewares e registro de routers
├── composition.py                # Raiz de composição: escolha das implementações concretas (SqlAlchemyUnitOfWork, MarketGateway)
├── cli.py                        # Entrypoint CLI (hash-password, import-b3, etc.)
├── alembic.ini                   # Configuração das migrações Alembic
├── Dockerfile                    # Dockerfile unificado para api, worker e migrate
├── pyproject.toml                # Definição única de dependências do backend
│
├── controllers/                  # Camada de Apresentação HTTP (FastAPI)
│   ├── shared/                   # DTOs, schemas e serializers compartilhados
│   │   ├── requests/             # DTOs compartilhados de entrada
│   │   └── responses/            # DTOs compartilhados de saída
│   └── {domain}/                 # Subpastas por domínio (auth, accounts, assets, ledger, portfolio, contributions, policy, research, market, alerts, system)
│       ├── router.py             # FastAPI APIRouter (apenas validação e delegação a handlers/services)
│       ├── dependencies.py       # FastAPI Depends() providers
│       ├── serializers.py        # Mapeamento Entidade de Domínio -> Response DTO
│       ├── requests/             # Pydantic schemas para requisições HTTP (entrada)
│       └── responses/            # Pydantic schemas para respostas HTTP (saída)
│
├── domain/                       # Camada de Domínio Puro (Regras de Negócio, Cálculo e Portas Abstratas)
│   ├── shared/                   # Entidades, enums, paginação e contratos base compartilhados
│   │   ├── entities/
│   │   ├── enums/
│   │   ├── repositories.py       # Interfaces abstratas base
│   │   └── unit_of_work.py       # Interface abstrata AbstractUnitOfWork
│   └── {domain}/                 # Subpastas por domínio
│       ├── entities/             # Dataclasses puras de entidades e Value Objects
│       ├── services/             # Regras de negócio, cálculos (ARCA, Cerrado, etc.) e serviços de domínio
│       └── repositories/         # Interfaces abstratas dos repositórios do domínio
│
├── infra/                        # Camada de Infraestrutura e Persistência Concreta
│   ├── data/
│   │   ├── db.py                 # SQLAlchemy engine, session factory e base declarativa
│   │   ├── health.py             # Sonda de saúde do banco de dados (readiness probe)
│   │   ├── models/               # SQLAlchemy ORM models segmentados por domínio
│   │   ├── mappers/              # Conversores bidirecionais ORM Model <-> Domain Entity
│   │   ├── unit_of_work/         # Implementação concreta SqlAlchemyUnitOfWork
│   │   ├── repositories/         # Implementações concretas SQLAlchemy dos repositórios
│   │   └── migrations/           # Migrações Alembic (script_#####) e env.py
│   ├── cache/                    # Implementação de cache Redis / in-memory
│   └── providers/                # Gateways de terceiros (BRAPI, B3, Tesouro Direto)
│
├── core/                         # Infraestrutura e Fundações Transversais da Aplicação
│   ├── settings.py               # Pydantic Settings (lê .env)
│   ├── logging.py                # Configuração estruturada de logs
│   ├── middleware.py             # Middlewares HTTP (request ID, timing, CORS)
│   ├── http_errors.py            # Mapeamento centralizado de exceções de domínio para respostas HTTP
│   ├── security.py               # Autenticação JWT, Argon2 hashing, verificação de credenciais
│   ├── errors.py                 # Exceções base de domínio e infraestrutura
│   └── helpers/                  # Utilitários puros (paginação, serialização)
│
├── worker/                       # Serviço Assíncrono e Scheduler de Tarefas
│   ├── scheduler.py              # APScheduler runner e configuração de triggers cron
│   ├── runner.py                 # Executor genérico de jobs com retry e logging estruturado
│   ├── jobs.py                   # Implementação das tarefas periódicas (cotações, snapshots, demonstrativos)
│   ├── rebuild.py                # Reconstrução de histórico de patrimônio
│   └── seed_demo.py              # Script de semeadura de dados para demonstração
│
└── tests/                        # Suite consolidada de testes de backend (unitários e integração)
```

### 2. Separação Estrita de `requests` e `responses`

- Os contratos de entrada (`requests`) e saída (`responses`) foram organizados em pacotes dedicados sob cada controller.
- Para evitar redefinição redundante de classes Pydantic (que em Pydantic v2 causa incompatibilidades de validação de tipo em tempo de execução), modelos referenciados por respostas foram centralizados em `requests` e importados em `responses`, mantendo a semântica clara e sem duplicação de definições de classe.

### 3. Dockerfile Unificado e Compose Simplificado

- Uma única imagem Docker (`apps/api/Dockerfile`) é construída para a API, para as migrações (`migrate`) e para o agendador (`worker`).
- No `docker-compose.prod.yml` e `docker-compose.yml`:
  - `api`: executa `uvicorn main:app --host 0.0.0.0 --port 8000`.
  - `migrate`: executa `alembic upgrade head`.
  - `worker`: executa `python -m worker.scheduler` com `healthcheck: disable: true` (pois o worker não expõe servidor HTTP, evitando falsos reinícios pelo Docker Compose).

### 4. Preservação Total dos Contratos e Regras Arquiteturais

- O contrato da API (OpenAPI schema) foi rigorosamente preservado, garantindo 100% de compatibilidade sem qualquer quebra no frontend TypeScript (`apps/web`).
- Todas as regras do monorepo (Regra #8: Isolamento em camadas `Controllers -> Handlers/Services -> UnitOfWork -> Repositories`) continuam estritamente cumpridas. Controllers nunca acessam SQLAlchemy ou repositories diretamente.

## Consequências

- **Manutenibilidade:** Eliminação de 4 subpacotes dispersos; o workspace Python possui um único `pyproject.toml` claro e consistente.
- **Rastreabilidade:** Navegação direta por domínio em `controllers/{domain}`, `domain/{domain}` e `infra/data/repositories/{domain}`.
- **Performance de Build:** Redução no tempo de build do Docker Compose, já que `api`, `migrate` e `worker` compartilham o mesmo estágio de cache de imagem.
- **Resiliência do Worker:** Eliminação de dependências circulares de import a frio e configuração adequada do container do worker no Compose.
