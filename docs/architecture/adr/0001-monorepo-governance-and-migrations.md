# ADR 0001 — Estrutura Monorepo, Regras de Engenharia e Migrations `script_#####`

- **Status:** Aceito
- **Data:** 2026-10-24

## Contexto
O projeto precisa reunir API (`FastAPI`), Worker de sincronização (`APScheduler`), regras de domínio compartilhadas, camada de persistência relacional (`SQLAlchemy` + `Alembic`) e SPA (`React` + `TypeScript`) no mesmo repositório, mantendo governança rigorosa para evolução assistida por agentes de IA (Gemini / Claude) e desenvolvedores.

## Decisão
1. Adotar um **monorepo** gerenciado por **uv workspaces** para Python (`packages/core`, `packages/persistence`, `apps/api`, `apps/worker`) e **npm/Vite** para o frontend (`apps/web`).
2. Padronizar todo o **código-fonte em inglês** (identificadores, rotas, tabelas, colunas, commits e comentários).
3. Exigir **testes de unidade obrigatórios** para qualquer regra ou componente e **testes de integração ao final de cada etapa de implementação**.
4. Isolar configurações sensíveis em arquivo `.env` não versionado (com `.env.example` versionado).
5. Executar toda a infraestrutura via **Docker Compose** com **volumes nomeados isolados** (`fincontrol_pgdata` e `fincontrol_redisdata`) para evitar perda de dados.
6. Gerenciar o versionamento do banco exclusivamente via **Alembic**, utilizando o padrão sequencial `script_#####_<descricao>.py` (ex.: `script_00001_initial_schema.py`) tanto no nome do arquivo quanto no `revision` ID.

## Consequências
- **Positivas:** Reuso total da lógica financeira entre API e Worker; zero risco de perda acidental do banco em rebuilds de containers; histórico de schema previsível e auditável; agentes de IA seguem o mesmo contrato via `AGENTS.md`, `CLAUDE.md` e `GEMINI.md`.
- **Negativas:** Exige disciplina para criar uma migration `script_#####` a cada alteração de modelo.
