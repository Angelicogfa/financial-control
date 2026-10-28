# Passagem de contexto — Fase 33 (Simulação de Carteira)

*Gravado em 2026-10-28 para retomar a implementação em outra sessão ou conta. Leia este arquivo, depois o [desenho](../features/PORTFOLIO_SIMULATION_DESIGN.md) e a seção da Fase 33 do [plano](IMPLEMENTATION_PLAN.md).*

## Como retomar
1. Abra a worktree `C:\Repositorios\financial-control\.claude\worktrees\feature-simulation` (branch `feature/simulation`). Se ela não existir mais, recrie a partir da branch:
   ```bash
   git worktree add .claude/worktrees/feature-simulation feature/simulation
   ```
2. Peça à nova sessão: "Leia `docs/todo/HANDOFF_FASE_33.md` e siga com a próxima etapa."
3. Antes de codar, rode `uv run pytest` em `apps/api` para confirmar a base verde.

## Estado do repositório
- **`main`** (`ae7d40c`): Fases 25, 26, 27, 29 e o desenho inicial da 33 já mergeados (PRs #17, #19, #21, #23).
- **`feature/simulation`**, à frente da `main` com 33.1 a 33.5 (enviada ao `origin` até a 33.4, ainda sem PR). Os primeiros commits:
  - `a82dae3`: desenho revisado (ativos candidatos e lógica bayesiana);
  - `4ff2c70`: motor do backtest (33.2, primeira parte) e decisões provisórias;
  - `7cc630b`: decisões finais com fundamentação e avaliação do PyMC.
- A branch `claude/fase-33-candidatos-bayes` (outra worktree) tem só o commit do desenho já trazido para cá e pode ser descartada.

## O que a Fase 33 é
Ferramenta de simulação: backtest da estratégia ARCA (camada A), projeção por bootstrap em blocos com cenários de juros (B), camada bayesiana (incerteza de parâmetros, intervalos, calibração walk-forward), ativos candidatos fora da carteira (D) e laboratório de ML com portões (C). É simulação, nunca recomendação: nada altera a política nem dispara aportes. O detalhe está no desenho, seções 1 a 9, e o teste de estresse com 21 riscos na seção 8.

## Decisões tomadas (desenho, seções 10.1 a 10.4)
1. Universo inclui o **catálogo atual**, com selo de viés de sobrevivência, evento de ruptura e comparação ao lado com os ativos que o usuário teve ou observou.
2. Histórico longo: **Yahoo** (preço ajustado), com relatório de cobertura e sem preencher buracos.
3. ML: **só regime e risco**.
4. Meta: **patrimônio e renda passiva mensal**.
5. Política no passado: **regras atuais aplicadas ao histórico inteiro**, rotuladas como descritivas, com os últimos 3 anos reservados; a política vigente em cada data fica como opção.
6. Orçamento: **5.000 trajetórias e 120 s**.
7. Candidatos: **watchlist + screener**, até **20** por execução.
8. Prior: **Bayes-Stein (Jorion 1986)** para alvos de CDI + 3% (ações BR e internacional), CDI + 2% (FIIs) e CDI (caixa), com a intensidade dada pelos dados; premissas da política como visões Black-Litterman.
9. Ruptura: probabilidade anual pela **zona do Z''-score** (estresse 5%, cinza 1%, segura 0,2%, sem dado 1%, FII 0,5%); perda central de **55%**, estresse em 90%.
10. Calibração **semanal**, só avisando.
- **PyMC:** fórmulas fechadas em numpy no caminho principal. O PyMC entra como **oráculo nos testes** (dependência de desenvolvimento) e no **laboratório**, para modelos sem solução fechada.

## O que já está implementado
- `apps/api/domain/simulation/market.py`:
  - `PriceSeries`, `MarketHistory`;
  - `PointInTimeView`, que levanta `LookAheadError` ao pedir dado posterior ao dia simulado;
  - `month_ends` (último dia útil do mês) e `accumulate_rate_index` (índice a partir do CDI diário).
- `apps/api/domain/simulation/engine.py`:
  - `run_backtest`: aporte mensal pelas regras reais (`consolidate_portfolio` + `plan_contribution`), caixa rendendo o CDI, emolumentos, correção opcional pelo IPCA, ativo entrando na primeira data de preço; saídas TWR, TIR (`money_weighted_return`), volatilidade e queda máxima;
  - `run_benchmark`: o mesmo fluxo de aportes num único índice.
- `apps/api/tests/test_simulation_backtest.py`: 13 testes de verdade conhecida e de look-ahead, todos passando. A suíte completa do backend também passou.

## Próximos passos
1. ~~33.1~~ concluída (ver o plano): séries `SIM:*` no `market_series`, rotina semanal `sync_simulation_history`, `coverage_report` e `build_market_history` em `domain/simulation/data.py`, rota `GET /api/v1/simulations/coverage`. Para ter dados reais, rode a rotina uma vez (ela não roda na partida do worker): botão "Carregar o histórico da simulação" em Configuração › Dados de mercado, operação MCP `market.request_job` ou `python -m worker.run_now sync_simulation_history` no contêiner do worker (33.5.1).
2. ~~33.2~~ concluída: rebalanceamento com IR, política por data, checklist histórico e selo de sobrevivência (ver o plano).
3. ~~33.3~~ concluída: `simulation_runs`/`simulation_results` (migração `script_00023`), `domain/simulation/runs.py` (parâmetros, entradas do banco, `data_hash`, reaproveitamento por parâmetros + dados + `ENGINE_VERSION`), limite de tempo de 120 s, job `run_pending_simulations` no worker (fila a cada 15 s), rotas `POST /api/v1/simulations/backtests`, `GET /api/v1/simulations[/{id}]` e MCP `simulation.backtest|get|list`. Limitação conhecida: uma rodada que fica em RUNNING porque o worker caiu no meio não é retomada sozinha.
4. ~~33.4~~ concluída: `domain/simulation/robustness.py` (crises, choques, variantes contadas, janela reservada de 36 meses, avisos de amostra), rota `GET /api/v1/simulations/{id}/robustness`, MCP `simulation.robustness` e a tela `/tools/simulation` com as abas Passado e Robustez.
5. ~~33.5~~ concluída: `domain/simulation/scenarios.py` (bootstrap estacionário do excesso sobre o CDI, cenários de juros, aporte, rebalanceamento com IR, percentis, metas), tipo `PROJECTION` com ponto de partida congelado no pedido, rotas `POST /api/v1/simulations/projections` e `GET /api/v1/simulations/{id}/projection`, MCP `simulation.project|projection` e a aba Futuro.
6. ~~33.6~~ concluída: `bayes.py` (Bayes-Stein, normal-inverso-Wishart sobre o log do excesso, sorteios, Beta, stacking), `generators.py` (bootstrap, bootstrap bayesiano, normal bayesiana e a mistura), `calibration.py` (walk-forward, PIT, cobertura com Beta, Brier, log score, status), tipo `CALIBRATION` enfileirado após cada carga de histórico, intervalos de 90% em toda chance do Futuro, aba Confiança e o guia das quatro abas. PyMC não entrou (oráculo numérico no lugar).
7. **Próxima: 33.7** (ativos candidatos, camada D) e as demais, na ordem da tabela da seção 9 do desenho.

## Convenções e preferências do usuário
- Respostas em **português**; código, commits e identificadores em inglês (ver `AGENTS.md`).
- Testes de unidade obrigatórios. Ao fim de cada etapa: `uv run pytest`, `npm test`, `npm run lint` e `npm run build` em `apps/web`, e `docker compose --env-file .env.example build` (o worktree não tem `.env`).
- Migrations Alembic sequenciais `script_#####` (a última na `main` é `script_00022`; nesta branch, `script_00023`).
- Tipos do front gerados: `uv run python scripts/gen_web_types.py`.
- Atualizar `docs/todo/IMPLEMENTATION_PLAN.md` a cada etapa.
- **Publicação:** o usuário usa a skill `triade-git` (PR, merge, pull). O **CI do GitHub não roda** porque a cobrança do Actions está bloqueada (TD-10). O usuário já autorizou mergear com a validação local nos PRs anteriores, mas a skill pede confirmação a cada PR.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; o corpo do PR termina com `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Pendências fora da Fase 33
- Fase 28 (fatos relevantes da CVM) e Fase 32 (legibilidade da Saúde e da Estratégia) seguem pendentes no plano.
- Dado para conferir: a compra do Tesouro IPCA+ com Juros Semestrais 2037 em 16/10/2026 tem PU 4.614,72, implausível (provável quantidade arredondada pelo extrato, 0,06 em vez de cerca de 0,064).
