# CLAUDE.md

Please read and strictly follow all rules, architectural boundaries, and workflows defined in [AGENTS.md](./AGENTS.md).

## Quick Reminders for Claude
1. **Code in English, replies in Portuguese**: All identifiers, database columns, routes, tests, and code comments must be in English. Every message to the user (answers, summaries, questions, progress updates) must be in **Portuguese (pt-BR)**.
2. **Unit Tests Required**: Every domain rule, service, handler, Unit of Work, repository, and UI component requires unit tests.
3. **Integration Tests Per Step**: Execute integration tests at the end of each implementation milestone (`uv run pytest`).
4. **Environment & Docker**: Never commit `.env`. Keep `.env.example` updated. Run via `docker compose` with isolated named volumes (`fincontrol_pgdata`, `fincontrol_redisdata`).
5. **Migrations**: Always use Alembic in `packages/persistence/migrations/versions/` with sequential filenames `script_#####_<description>.py` and revision IDs `script_#####`.
6. **Strict Backend Layering**: Controllers/Routers MUST only call Handlers/Services and NEVER manipulate database sessions, ORM models, or repositories directly. All persistence access goes through `Services/Handlers -> UnitOfWork -> Repositories` returning pure Domain Entities.
7. **Progress Tracking**: Keep [docs/todo/IMPLEMENTATION_PLAN.md](./docs/todo/IMPLEMENTATION_PLAN.md) updated as tasks move from pending (`[ ]`) to implemented (`[x]`).
8. **Docker Build Validation Per Phase**: Every completed or in-progress phase must validate all implemented projects via `docker compose build`.
