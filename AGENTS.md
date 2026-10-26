# AGENTS.md — Financial Control Rules & Guidelines

This file serves as the primary authoritative guide for AI coding agents (Gemini / Antigravity, Claude Code, Cursor, etc.) operating inside the `financial-control` monorepo. Every contribution MUST strictly adhere to the rules and architecture defined below.

---

## 1. Mandatory Project Rules (Non-Negotiable)

1. **Code in English (`código em ingles`)**
   - All source code identifiers (variables, functions, classes, modules, database tables, columns, API routes, JSON keys, enum values, git commit messages, and code comments/docstrings) MUST be written in **English**.
   - User-facing UI labels (in `apps/web`) and project documentation (`docs/`) may be in Portuguese (pt-BR), matching the domain vocabulary (e.g., *ARCA*, *Diagrama do Cerrado*, *FIIs*, *Tesouro Direto*, *Proventos*).
   - **Agent replies in Portuguese (`respostas em português`):** every message the agent writes to the user (answers, summaries, questions, explanations, progress updates) MUST be in **Portuguese (pt-BR)**. This applies to conversation only; code, commits and identifiers stay in English as above.

2. **Mandatory Unit Tests (`testes de unidade obrigatorios`)**
   - Every domain rule, calculation, service, handler, Unit of Work, repository method, and UI utility/component MUST have accompanying unit tests.
   - No feature or bugfix is considered complete without unit tests covering happy paths, edge cases, and error conditions.
   - Domain (`apps/packages/core`) tests must run purely in-memory with zero network or database dependencies.

3. **Integration Tests After Each Implementation (`testes de integração ao final de cada implementação`)**
   - At the end of every implementation step or phase, integration tests MUST be executed and pass before advancing to the next item.
   - Backend integration tests verify Controllers/Routers + Handlers + Services + UnitOfWork + SQLAlchemy Repositories + Alembic schema + cache/provider adapters working together.
   - Frontend/E2E integration verifies contract compatibility with the backend API.

4. **Isolated Environment Variables in Unversioned `.env` (`variaveis de ambientes isoladas em arquivo .env não versionado`)**
   - All secrets, credentials, connection strings, and environment-specific settings MUST be loaded from environment variables via `.env`.
   - `.env` MUST NEVER be committed to Git (`.gitignore` enforced).
   - `.env.example` MUST be kept up-to-date with safe placeholder values whenever a new variable is introduced.

5. **Docker Compose Runtime (`ambiente deve rodar em docker-compose`)**
   - The entire stack (`postgres`, `redis`, `migrate`, `api`, `worker`, `web`) MUST build and run via Docker Compose:
     - **Production:** `docker-compose.prod.yml` (`docker compose -f docker-compose.prod.yml up -d --build`) is the canonical runtime contract: only `web` publishes a port.
     - **Development:** `docker-compose.yml` (`docker compose up -d --build`) extends the production services and publishes Postgres, Redis and the API on `127.0.0.1` only.
   - Local host execution (`uv run`, `npm run dev`) is supported for fast feedback.

6. **Isolated Named Volumes for Data Persistence (`volume mapeado de forma isolado a fim de evitar perder dados`)**
   - Stateful services (`postgres` and `redis`) MUST use dedicated, explicitly named Docker volumes (`fincontrol_pgdata`, `fincontrol_redisdata`) mapped outside container ephemeral filesystems so that container rebuilds or `docker compose down` (without `-v`) never lose user data.

7. **Alembic Migrations with `script_#####` Naming (`utilizar migrations (alembic) para controle de versionamento sempre no formato script_#####`)**
   - All database schema changes MUST be managed through **Alembic** in `apps/packages/persistence/migrations/versions/`.
   - Every migration file and revision ID MUST follow the sequential naming convention:
     - `script_00001_initial_schema.py` (revision = `"script_00001"`)
     - `script_00002_<short_description>.py` (revision = `"script_00002"`)
   - Direct `Base.metadata.create_all()` is forbidden in production/Docker startup; the `migrate` service runs `alembic upgrade head`.

8. **Strict Backend Layering: Controllers $\rightarrow$ Handlers / Services $\rightarrow$ UnitOfWork $\rightarrow$ Repositories (`isolamento de camadas no backend`)**
   - **Controllers / FastAPI Routers** MUST ONLY parse/validate HTTP requests, invoke an Application **Handler** or **Service**, and serialize the HTTP response.
   - **Controllers MUST NEVER**:
     - Access `Session` / database connections directly;
     - Instantiate or call `Repository` classes directly;
     - Manipulate SQLAlchemy ORM models or execute queries directly;
     - Contain business calculations.
   - **Handlers (Command / Query Handlers)** coordinate a single use case (validating input commands/queries, opening a `UnitOfWork` transaction boundary, delegating domain/application orchestration to **Services**, and committing via `uow.commit()`).
   - **Services (Application & Domain Services)** encapsulate reusable business workflows and coordinate domain calculations (`apps/packages/core`) with abstract ports (`UnitOfWork`, `MarketDataGateway`).
   - **Unit of Work (`AbstractUnitOfWork` / `SqlAlchemyUnitOfWork`)** manages atomic transaction boundaries (`__enter__`, `__exit__`, `commit()`, `rollback()`) and exposes all repositories (`uow.assets`, `uow.transactions`, `uow.earnings`, `uow.arca_targets`, `uow.market_series`, `uow.snapshots`).
   - **Repositories (`AbstractRepository` / SQLAlchemy Repositories)** encapsulate all persistence queries, pagination, sorting, filtering, and mapping between ORM models and pure Domain Entities/DTOs. Repositories NEVER call `session.commit()` — transaction completion is exclusively owned by the `UnitOfWork`.

9. **Docker Build Validation Per Phase (`validar cada fase buildando os projetos feitos pelo docker`)**
   - To validate any completed or in-progress phase, every implemented project/service (`migrate`, `api`, `worker`, `web`) MUST be successfully built via Docker (`docker compose build`).
   - A phase is only considered validated when its unit tests, integration tests, AND Docker image build succeed without errors.

---

## 2. Backend Layered Architecture Flow

```text
HTTP Request (FastAPI Controller / Router)
   │  (DTO / Command / Query)
   ▼
CommandHandler / QueryHandler
   │  (opens `with uow:` boundary, orchestrates Service + Domain)
   ▼
Application / Domain Service  ──► Pure Domain Engine (`apps/packages/core`)
   │
   ▼
UnitOfWork (`AbstractUnitOfWork` / `SqlAlchemyUnitOfWork`)
   │  (`uow.assets`, `uow.transactions`, `uow.earnings`, ... + `uow.commit()`)
   ▼
Repositories (`apps/packages/persistence`)
   │  (maps ORM Models ◄──► Domain Entities)
   ▼
PostgreSQL / Redis
```

---

## 3. Monorepo Structure

```text
financial-control/
├── AGENTS.md                 # Canonical instructions for AI agents
├── CLAUDE.md                 # Pointer/entry for Claude Code
├── GEMINI.md                 # Pointer/entry for Gemini / Antigravity
├── .agents/rules/            # Granular workspace rules
├── apps/
│   ├── api/                  # FastAPI Controllers -> Handlers -> Services -> UoW
│   ├── worker/               # APScheduler Jobs -> Handlers/Services -> UoW
│   └── web/                  # React + Vite + TypeScript SPA
├── apps/packages/
│   ├── core/                 # Pure domain entities, ports (Repos & UoW interfaces), engines
│   └── persistence/          # SQLAlchemy 2.0 ORM, Concrete Repositories, SqlAlchemyUnitOfWork, Alembic (`script_#####`)
├── docs/
│   ├── architecture/         # System design, C4, UI/UX, domain & data models
│   │   └── adr/              # Architecture Decision Records
│   ├── features/             # Feature specifications
│   ├── todo/                 # Phased implementation plan & status tracker
│   └── tech-debt/            # Technical debt register
├── docker-compose.yml          # development (extends prod, loopback ports)
├── docker-compose.prod.yml     # production (only web published)
├── pyproject.toml            # Root uv workspace configuration
└── .env.example              # Template for .env (never commit .env)
```
