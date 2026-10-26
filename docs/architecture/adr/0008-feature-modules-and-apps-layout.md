# ADR 0008 — Backend em Módulos por Feature e Todo o Código em `apps/`

- **Status:** Aceito
- **Data:** 2026-10-26
- **Complementa:** ADR 0004 (camadas Controller → Handler/Service → UnitOfWork → Repository, que continuam valendo) e ADR 0001 (monorepo com workspace `uv`).
- **Referência:** `dynamic-research/apps/api` (`app/core/`, `app/composition.py`, `app/modules/<área>/<feature>/`).

## Contexto
A API era plana: um `controllers.py` com todas as rotas (704 linhas), um `schemas.py` único (830), `handlers/` por assunto e um serviço solto. O persistence tinha um `repositories.py` (1.120 linhas) e um `models.py` únicos. Cada feature nova crescia arquivos compartilhados. O usuário pediu que a API seguisse o padrão estrutural do projeto de referência, com controllers, services, repositórios e infraestrutura segmentados, e que todo o código da solução ficasse em `apps/`.

## Decisão

### 1. API em `core/` + `composition.py` + `modules/<feature>/`
- `fincontrol_api/core/`: infraestrutura HTTP — `config`, `security` (login single-user, Argon2 + JWT), `deps` (paginação, `UoWFactory`), `middleware` (request id, log de acesso, CORS) e `http_errors` (erro de domínio → status HTTP).
- `fincontrol_api/composition.py`: **raiz de composição**, o único lugar que escolhe as implementações concretas (`SqlAlchemyUnitOfWork`, gateway de mercado, sonda do banco).
- `fincontrol_api/modules/<feature>/`: `router.py` (controllers), `schemas.py` (DTOs), `use_cases.py` (handlers), `dependencies.py` (providers do FastAPI), `serializers.py` (entidade → DTO) e `service.py` quando há serviço de aplicação. Features: `system`, `auth`, `accounts`, `assets`, `ledger` (com `use_cases/` por agregado), `portfolio`, `contributions`, `policy`, `research`, `market`, `alerts` e `shared`.
- O `main.py` só monta o app: middleware, tradutores de erro e os routers na ordem do OpenAPI.

### 2. Persistence segmentado, mas compartilhado
- `fincontrol_persistence/core/` (engine e sessão, `SqlAlchemyUnitOfWork`, saúde do banco) + `models/`, `repositories/` e `mappers/` com um módulo por feature.
- Ao contrário da referência, os repositórios **não** foram para dentro dos módulos da API: o worker grava séries, retratos, demonstrativos e execuções pela mesma Unit of Work. Pôr o persistence na API obrigaria o worker a importar FastAPI e os routers.
- Os models se referenciam só em anotações (`TYPE_CHECKING`); o SQLAlchemy resolve pelo registro de classes, sem import circular.

### 3. Todo o código em `apps/`
- `packages/` virou `apps/packages/{config,core,persistence}`: continuam pacotes do workspace `uv`, compartilhados por `apps/api` e `apps/worker`.

### 4. Um só cadastro de ativo novo
- `modules/research/service.py::register_researched_asset` é o caminho de qualquer ativo novo vindo da Pesquisa ou da importação B3: catálogo da B3 → tipo → quadrante ARCA escolhido pelo usuário (ou sugerido). Os demonstrativos anuais são buscados logo depois (`StatementRefresher`, em `BackgroundTasks`).

## Consequências
- Feature nova ganha a própria pasta em `modules/` em vez de crescer um arquivo compartilhado; o import de um módulo mostra de quem ele depende.
- O contrato HTTP não mudou: o documento OpenAPI gerado depois da divisão é idêntico byte a byte ao anterior, então os tipos do frontend não mudaram.
- Testes de arquitetura: todo `modules/*/router.py` fica livre de SQLAlchemy, persistence e `uow_factory`; só `composition.py` referencia a `SqlAlchemyUnitOfWork`; todo módulo importa sozinho, a frio, sem ciclo (`test_import_graph.py`).
- O CLI de senha passou a ser `python -m fincontrol_api hash-password`.
- Caminhos absolutos mudaram (`apps/packages/...`): Dockerfiles, `working_dir` do `migrate`, `scripts/check.sh`, caminhos do pytest e as regras dos agentes.
