# Financial Control

Ferramenta pessoal de gestão de carteira de investimentos que une duas metodologias:

- **ARCA** (Ações, Real Estate, Caixa, Ativos internacionais) para segmentar a carteira, com metas, bandas de tolerância e aportes que corrigem o desvio sem vender nada;
- **Análise fundamentalista** para escolher os ativos de cada classe: checklist do Diagrama do Cerrado por perfil de instrumento, histórico de 5 anos de demonstrativos e valuation por tipo (Graham, Bazin, P/L, EV/EBITDA, P/VP, spread de FIIs).

As duas vivem numa **política de investimento versionada** e aparecem dentro de cada operação do dia a dia:

| Menu | O que faz |
|---|---|
| **Início** | Analytics: patrimônio, resultado, rentabilidade contra o CDI, proventos, alocação × meta, alertas e evolução |
| **Desempenho** | Rentabilidade ponderada pelo tempo, risco (volatilidade, Sharpe, drawdown, VaR) e comparação com CDI, Ibovespa, IFIX e S&P 500 |
| **Carteira** | Posições por classe ARCA, peso atual × alvo, situação de cada ativo na política |
| **Pesquisar** | Screener do catálogo da B3 e lista de observação; ao observar um ativo você escolhe o quadrante ARCA (a sugestão vem marcada) e pode reclassificá-lo depois |
| **Aportar** | Sugestão de aporte em dois níveis (classes → ativos elegíveis), revisão e confirmação que registra as compras |
| **Lançamentos** | Compras, vendas, proventos e eventos corporativos; importação dos extratos da B3, que cadastra os ativos novos pelo mesmo caminho da Pesquisa |
| **Configuração** | Estratégia (metas, elegibilidade, valuation), contas e frescor dos dados de mercado |

Renda fixa (CDB, LCI/LCA, CRI/CRA, debêntures, Tesouro Direto) é calculada pela curva contratada (CDI, SELIC, IPCA+ ou prefixado), com IR regressivo, IOF e feriados.

## Arquitetura

Monorepo com workspace `uv` (Python 3.12) e frontend React:

```text
apps/
  api/          Backend unificado (FastAPI, Persistência, Domínio e Worker)
    controllers/  camada HTTP: router, serializers, requests/ e responses/ por domínio
    domain/       domínio puro: entities/, services/ (ARCA, Cerrado, renda fixa) e repositories/
    infra/        infraestrutura: data/{db, models, mappers, uow, repos, migrations}, cache, providers
    core/         infraestrutura HTTP, segurança, logging, middlewares e utilitários
    worker/       APScheduler: séries do BCB, cotações, retratos diários, demonstrativos, catálogo B3
  web/          React 18 + Vite, servido por nginx
docs/           arquitetura, ADRs, funcionalidades, débitos técnicos e plano
scripts/        portão de qualidade, smoke test e E2E
```

Serviços do Docker Compose: `postgres` (16), `redis` (7), `migrate` (Alembic), `api`, `worker` e `web`. Os dados ficam nos volumes nomeados `fincontrol_pgdata` e `fincontrol_redisdata`, que sobrevivem a rebuilds e a `docker compose down` (sem `-v`).

Cotações e fundamentos vêm da [brapi.dev](https://brapi.dev) e do Yahoo Finance; CDI, SELIC e IPCA, do Banco Central (SGS). Quando um provedor falha, a tela mostra o dado de reserva sinalizado e um alerta, nunca um número inventado.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) com Docker Compose v2 (Docker Desktop no Windows/macOS).
- [uv](https://docs.astral.sh/uv/) — para gerar o hash da senha e rodar testes/scripts.
- Node.js 22 — só para desenvolver o frontend fora do Docker.

## Subindo o ambiente

### 1. Clonar e instalar as dependências Python

```bash
git clone <url-do-repositorio> financial-control
cd financial-control
uv sync --all-packages
```

### 2. Criar o `.env`

```bash
cp .env.example .env
```

Troque **todos** os valores `change-me-*` e mantenha as credenciais coerentes entre si:

| Variável | O que colocar |
|---|---|
| `POSTGRES_PASSWORD` | uma senha forte para o banco |
| `DATABASE_URL` | `postgresql+psycopg://fincontrol:<POSTGRES_PASSWORD>@postgres:5432/fincontrol` |
| `REDIS_PASSWORD` | uma senha forte para o Redis |
| `REDIS_URL` | `redis://:<REDIS_PASSWORD>@redis:6379/0` |
| `AUTH_USERNAME` | o seu usuário de login |
| `AUTH_PASSWORD_HASH` | o hash da sua senha, **entre aspas simples** (comando abaixo) |
| `AUTH_JWT_SECRET` | um segredo aleatório (comando abaixo) |
| `BRAPI_TOKEN` | opcional, mas recomendado: sem token a brapi recusa a maioria dos tickers e o Yahoo vira a fonte |

Gerar o hash da senha de login (pede a senha duas vezes, sem ecoar, e imprime a linha pronta, já entre aspas simples):

```bash
uv run python -m fincontrol_api hash-password
```

Cole a linha `AUTH_PASSWORD_HASH='$argon2id$...'` inteira no `.env`. O valor precisa começar com `$argon2id$`: sem as aspas simples, os `$` são expandidos e o hash se perde, e a tela de login avisa que a autenticação não está configurada. Com a stack no ar, dá para gerar o hash dentro do container: `docker compose exec api python -m fincontrol_api hash-password`.

Gerar o segredo do JWT:

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

O `.env` **nunca** vai para o Git (está no `.gitignore`). As demais variáveis já vêm com valores padrão e estão comentadas no `.env.example`.

### 3. Subir a stack

**Produção** — só o web é publicado; banco, cache e API ficam na rede interna:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**Desenvolvimento** — a mesma stack, publicando também Postgres (`127.0.0.1:55432`), Redis (`127.0.0.1:56379`) e API (`127.0.0.1:8000`) apenas na máquina local:

```bash
docker compose up -d --build
```

Os dois arquivos usam os mesmos volumes: trocar de um para o outro não perde dados. O serviço `migrate` aplica as migrations do banco antes de a API subir.

### 4. Conferir e acessar

```bash
docker compose -f docker-compose.prod.yml ps -a
```

(Na stack de desenvolvimento, sem o `-f docker-compose.prod.yml`.) Os serviços devem aparecer como `healthy`, e o `migrate` como `exited (0)`, pois ele só roda uma vez. Abra **http://localhost:8080** (ou a porta de `WEB_PORT`) e entre com o usuário e a senha do passo 2. A saúde da API também pode ser vista em `http://localhost:8080/api/v1/ready`.

### 5. Primeiros passos no app

1. **Configuração › Estratégia:** defina as metas ARCA (somando 100%), as bandas e os critérios de elegibilidade.
2. **Configuração › Contas:** cadastre suas corretoras e bancos.
3. **Lançamentos › Importar extrato B3:** na [Área do Investidor da B3](https://www.investidor.b3.com.br), exporte *Extratos › Negociação* (compras e vendas) e *Extratos › Movimentação* (proventos e eventos) e importe os dois arquivos. Importar o mesmo arquivo de novo não duplica nada. Para cada ativo que ainda não está cadastrado, a pré-visualização mostra o tipo e o quadrante ARCA sugeridos: confira, ajuste se preciso e marque os que devem entrar; os demonstrativos deles são buscados logo depois.
4. Renda fixa e caixa: **Carteira › Novo ativo**, informando o contrato (indexador, taxa, aplicação e vencimento).
5. **Aportar:** informe o valor, revise a distribuição e confirme as compras executadas.

O worker sincroniza séries, cotações, catálogo da B3, demonstrativos e os comunicados da CVM sozinho; o andamento aparece em **Configuração › Dados de mercado**, onde também dá para rodar já a carga do histórico da simulação e a dos comunicados.

**Simular carteira** (Ferramentas): antes do primeiro uso, rode a carga do histórico em Dados de mercado (alguns minutos); a calibração entra na fila sozinha ao fim. As abas respondem perguntas diferentes, e cada uma explica a sua no topo: Passado (as suas regras no histórico), Futuro (faixas prováveis e chance de meta), Candidatos (ativos para investigar), Robustez (crises, variantes e a validação estatística), Confiança (se as chances costumam se confirmar) e Laboratório (modelos de regime e risco com portões). É simulação, não recomendação.

### Dados de demonstração (opcional)

Para explorar o app sem os seus dados, use um banco **vazio** (por exemplo uma stack isolada com outros volumes). O comando recusa rodar em um banco que já tenha ativos:

```bash
docker compose exec worker python -m fincontrol_worker.seed_demo
```

Ele cria uma carteira com dois anos de histórico (aportes mensais, proventos, renda fixa, reserva e retratos diários).

## Operação

Parar sem perder dados:

```bash
docker compose -f docker-compose.prod.yml down
```

Atualizar para uma nova versão do código (as migrations rodam sozinhas):

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Backup do banco (faça antes de cada atualização):

```bash
docker compose -f docker-compose.prod.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > fincontrol_$(date +%Y%m%d_%H%M%S).dump
```

Restaurar um backup:

```bash
docker compose -f docker-compose.prod.yml exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < arquivo.dump
```

Logs (JSON, com `request_id` por requisição):

```bash
docker compose -f docker-compose.prod.yml logs -f api worker
```

> **Cuidado:** `docker compose down -v` apaga os volumes, ou seja, **todos os seus dados**.

## Desenvolvimento

Com a stack de desenvolvimento no ar (`docker compose up -d`), o frontend pode rodar com recarga automática contra a API publicada em `127.0.0.1:8000`:

```bash
cd apps/web
npm ci
npm run dev
```

O app fica em http://localhost:5173.

Para depurar a API fora do Docker, rode-a com recarga automática contra o Postgres e o Redis da stack de desenvolvimento. Variáveis de ambiente têm prioridade sobre o `.env`, então basta trocar o host `postgres`/`redis` pelas portas publicadas em `127.0.0.1` (use as senhas do seu `.env`) e usar outra porta, já que a `8000` é da API do container:

```bash
DATABASE_URL="postgresql+psycopg://fincontrol:<POSTGRES_PASSWORD>@127.0.0.1:55432/fincontrol" REDIS_URL="redis://:<REDIS_PASSWORD>@127.0.0.1:56379/0" uv run uvicorn fincontrol_api.main:app --reload --port 8001
```

E aponte o frontend para ela:

```bash
cd apps/web
VITE_API_PROXY_TARGET=http://localhost:8001 npm run dev
```

Depois de mudar um DTO da API, regenere os tipos do frontend:

```bash
uv run python scripts/gen_web_types.py
```

### Testes e portão de qualidade

O workflow `.github/workflows/ci.yml` roda o mesmo portão no GitHub, mas hoje os jobs não chegam a iniciar (a conta está sem crédito de Actions). Enquanto isso, o portão roda localmente e é ele que valida cada PR:

| Comando | O que roda |
|---|---|
| `scripts/check.sh --fast` | lint, testes Python e web com pisos de cobertura, build do frontend |
| `scripts/check.sh` | o anterior + `docker compose build` dos dois arquivos |
| `scripts/check.sh --smoke` | o anterior + stack isolada no Docker (migrations, login, lançamento, segurança) |
| `scripts/check.sh --e2e` | o anterior + jornada completa no navegador (Playwright) e persistência após reinício |

Smoke e E2E sobem stacks **isoladas** (outro nome de projeto, outros volumes e portas, credenciais geradas) e nunca tocam na sua stack nem nos seus volumes. Para o E2E, instale o navegador uma vez: `cd apps/web && npx playwright install chromium`.

`scripts/install-hooks.sh` instala um hook de `pre-push` que roda o modo `--fast`.

### Convenções

As regras do projeto estão em [`AGENTS.md`](AGENTS.md): código, commits e banco em inglês; testes de unidade obrigatórios; migrations Alembic sequenciais (`script_#####`); camadas estritas no backend; unidades numéricas pela [ADR 0006](docs/architecture/adr/0006-units-and-numeric-conventions.md).

## Documentação

- [Visão de arquitetura](docs/architecture/OVERVIEW.md)
- [Frontend e design system](docs/architecture/FRONTEND_UI_UX.md)
- [Funcionalidades](docs/features/FEATURES_SPEC.md)
- [Decisões de arquitetura (ADRs)](docs/architecture/adr/)
- [Débitos técnicos](docs/tech-debt/TECH_DEBT.md)
- [Plano de implementação](docs/todo/IMPLEMENTATION_PLAN.md)
- Desenhos: [simulação de carteira](docs/features/PORTFOLIO_SIMULATION_DESIGN.md), [otimização da composição (proposta)](docs/features/ASSET_COMPOSITION_OPTIMIZATION_DESIGN.md) e [carteiras de comparação (proposta)](docs/features/COMPARISON_PORTFOLIOS_DESIGN.md)
