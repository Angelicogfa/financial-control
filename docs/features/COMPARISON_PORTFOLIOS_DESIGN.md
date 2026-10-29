# Carteiras de Comparação com o Seu Fluxo de Aportes — Proposta e Teste de Estresse

*Status: proposta para revisão, nenhuma linha de código. Data: 2026-10-29. Fase proposta: 36 (ver [IMPLEMENTATION_PLAN.md](../todo/IMPLEMENTATION_PLAN.md)). Reaproveita o motor da Fase 33. A Fase 34 (otimização da composição) vira uma das estratégias, e os dados da CVM (Fase 28 e extensão) dão os fundamentos com data de publicação.*

A ferramenta cria **N carteiras de comparação**. Cada uma segue uma estratégia de regras fixas sobre a base de ativos e recebe **os mesmos aportes e resgates que você fez, nas mesmas datas e nos mesmos valores**. Todas são acompanhadas dia a dia contra a sua carteira real. O histórico delas é também um conjunto de dados para os modelos da Fase 33 entenderem o que explica cada comportamento. A seção 8 ataca a proposta, porque comparar muitas estratégias de uma vez é um dos jeitos mais fáceis de achar uma "vencedora" que só teve sorte.

## 1. Perguntas que a ferramenta responde

1. "Se, com o mesmo dinheiro e nas mesmas datas, eu tivesse seguido a estratégia X, onde eu estaria hoje?"
2. "A minha carteira vence o acaso? Em que posição ela fica entre 200 carteiras sorteadas com as mesmas regras ARCA e o mesmo fluxo?"
3. "A diferença para cada estratégia vem da divisão entre classes ou da escolha dos ativos dentro delas?"
4. "Que estratégias vão melhor em que regime de mercado, e isso se repete?" (insumo para a 33.9).

**Não é recomendação.** Nada muda a política nem dispara compras. As carteiras de comparação não existem na corretora: são registros simulados, com o selo "simulação, não recomendação".

## 2. Conceitos

- **Carteira de comparação:** uma estratégia, um universo de ativos, regras de execução e o fluxo espelhado. Tem identidade própria e um histórico diário guardado.
- **Estratégia:** uma regra determinística que, em cada data, decide em que ativos e com que pesos aplicar o dinheiro, usando só o que se sabia naquela data. A regra fica **congelada e versionada**: mudar um parâmetro cria uma carteira nova, e o histórico da antiga não é reescrito (risco S10).
- **Fluxo espelhado:** a sequência de entradas e saídas de dinheiro da sua carteira, tirada dos lançamentos (seção 3).
- **Modos** (seção 5):
  - **prospectivo**, que começa na data de criação e é o registro oficial;
  - **retroativo**, reconstruído desde o seu primeiro aporte e sempre rotulado como tal.

## 3. Fluxo espelhado

- **Origem:** o fluxo líquido diário que os retratos já calculam (`net_flow`, Fase 6): compras menos o valor recebido nas vendas, por dia. Proventos não são fluxo externo: cada carteira recebe os proventos dos próprios ativos.
- **Alcance** (decisão 3): todo o fluxo da carteira ou só o da parte ARCA (sem a reserva de emergência e os ativos de finalidade "outra"). A recomendação é só ARCA, porque a reserva não segue a política.
- **Entrada:** no dia do aporte, a estratégia aplica o valor ao preço de fechamento daquele dia, em lotes inteiros na B3 (fracionário no exterior), com emolumentos. A sobra fica em caixa rendendo o CDI e é registrada como caixa ocioso.
- **Saída:** num resgate líquido, a carteira vende primeiro o que a estratégia manda e, na falta de regra, proporcionalmente aos pesos. Paga o IR pela regra real (isenção de R$ 20 mil por mês em ações, 20% em FIIs).
- **Proventos** (decisão 6): creditados em caixa e reinvestidos no próximo aporte (padrão), ou acumulados à parte para a métrica de renda passiva.

## 4. Estratégias do catálogo inicial

Todas respeitam as metas e bandas ARCA da política, menos as marcadas "fora do ARCA", que servem de referência. Cada estratégia tem um universo (decisão 2) e uma reconstituição periódica dos ativos escolhidos (proposta: trimestral). Os pesos são corrigidos só com aportes, salvo quando a estratégia diz que rebalanceia.

| Chave | O que faz | Para que serve |
|---|---|---|
| `POLICY_EQUAL` | Metas ARCA; pesos iguais dentro da classe; universo carteira + watchlist | Isolar o efeito do Cerrado na sua escolha |
| `POLICY_BROAD` | As suas regras de aporte (Cerrado e elegibilidade) num universo maior (screener) | Saber se o universo restrito está custando retorno |
| `INDEX_ARCA` | ETFs de índice por classe (BOVA11, XFIX11, IVVB11 e Tesouro Selic) nos pesos ARCA | A carteira passiva com a mesma política |
| `DIVIDENDS` | Os K maiores DY normalizados (Fase 25) com payout sustentável, por classe | O foco em renda |
| `VALUE` | Margem de segurança do valuation (Graham, P/L, P/VP) | O foco em preço descontado |
| `QUALITY` | ROE estável, margem, dívida baixa e, quando houver, Piotroski e Z'' | O foco em qualidade |
| `LOW_VOL` | Os menos voláteis por classe (36 meses) | O foco em risco baixo |
| `OPTIMIZED` | A composição da Fase 34, refeita na reconstituição | Testar o otimizador fora da amostra, no tempo real |
| `RANDOM` ×M | M carteiras sorteadas no universo elegível, respeitando o ARCA, com sementes fixas | **Controle:** a distribuição do acaso contra a qual medir as demais |
| `CDI`, `SIXTY_FORTY` (fora do ARCA) | 100% CDI; 60% Ibovespa e 40% CDI | Referências clássicas |

As estratégias são peças de uma interface só (`decide(data, visão point-in-time, carteira) → pesos-alvo`), de modo que acrescentar uma nova não mexe no motor.

## 5. Modos e o problema da retrospectiva

- **Prospectivo:** a carteira nasce na data de criação, com o patrimônio de partida igual ao da sua carteira naquele dia (ou zero, decisão 4), e daí para frente recebe o seu fluxo. Ninguém escolheu a regra conhecendo o resultado: é o único registro que vale como evidência.
- **Retroativo:** a carteira é reconstruída desde o seu primeiro aporte, para ter histórico logo. É útil, mas tem dois vieses que ficam rotulados na tela:
  - as regras foram escolhidas hoje, sabendo o que aconteceu;
  - até a extensão da CVM, os fundamentos de hoje não são os da época (risco R1 da simulação).
- **Separação visível:** as duas partes da curva aparecem em cores diferentes, e as métricas de evidência (seção 6) usam só a parte prospectiva.

## 6. Comparação e tela

Nova tela **Comparar carteiras** (Visão geral ou Ferramentas, decisão 9):
- **curva de patrimônio:** a sua carteira contra as N carteiras, com a faixa das carteiras aleatórias (5% a 95%);
- **tabela por carteira:**
  - TWR (Dietz modificado, Fase 32) e TIR sobre o mesmo fluxo, que é a comparação justa;
  - volatilidade, queda máxima, renda passiva e custos e IR pagos;
  - caixa ocioso e número de ativos;
- **posição da sua carteira:** o percentil dela na distribuição das aleatórias e das estratégias, com o intervalo de credibilidade (33.6). Por exemplo, "melhor que 62% das 200 carteiras sorteadas (intervalo de 54% a 70%)";
- **diferença acumulada:** "com o mesmo dinheiro, a estratégia X estaria R$ 1.240 acima (ou abaixo)";
- **atribuição (Brinson):** quanto da diferença veio da divisão entre classes e quanto da escolha dentro delas. Contra as estratégias que respeitam o ARCA, a parte da divisão é quase nula por construção, e isso isola a seleção;
- **por regime:** o desempenho relativo em alta e queda do Ibovespa, juros subindo e caindo (com o laboratório da 33.9, o regime estimado);
- **detalhe de cada carteira:** posições atuais, operações feitas e o que entrou e saiu em cada reconstituição.

**API e MCP:**
- `GET /comparison-portfolios`, `POST /comparison-portfolios` (cria uma carteira), `GET /comparison-portfolios/{id}` e `GET /comparison-portfolios/comparison`;
- operações `comparison.list`, `comparison.create`, `comparison.get` e `comparison.compare`.

## 7. Insumo para os modelos

- **Painel diário exportável:** data × carteira × medidas (valor, fluxo, retorno, pesos por classe, exposição a fatores, métricas móveis), mais as características da estratégia.
- **Usos:**
  - o laboratório de ML (33.9): quais características de estratégia explicam o desempenho relativo, e em que regime;
  - a calibração do prior do α na Fase 34: se os escores fundamentalistas predizem retorno, isso aparece no registro prospectivo das estratégias `VALUE`, `QUALITY` e `DIVIDENDS` contra as aleatórias;
  - a comparação bayesiana: P(estratégia > sua carteira) com intervalo, por janela e no total;
  - a consulta pelo agente (MCP), para análises conversadas.

## 8. Teste de estresse da proposta

| # | Risco | Como quebra | Mitigação na proposta | Risco residual |
|---|---|---|---|---|
| S1 | **Comparações múltiplas** | Com 15 estratégias, alguma vence por sorte | Carteiras aleatórias como distribuição nula; Deflated Sharpe e PBO (33.8) sobre o conjunto; contagem de estratégias criadas, inclusive as desativadas | Médio |
| S2 | **Retrospectiva** | Regras escolhidas hoje parecem ótimas no passado | Modo retroativo rotulado; evidência só da parte prospectiva; regras congeladas na criação | Médio: o prospectivo leva anos para acumular |
| S3 | **Look-ahead nos fundamentos** | O escore de 2024 usa o balanço de 2025 | Escores point-in-time pela data de entrega (CVM); até lá, exercício + 90 dias e o selo | Alto no retroativo até a extensão da CVM |
| S4 | **Sobrevivência** | O universo amplo só tem quem sobreviveu | Cadastro da CVM com cancelamentos; evento de ruptura no retroativo; no prospectivo o risco some, porque quem sair da bolsa sai também da carteira | Médio no retroativo, baixo no prospectivo |
| S5 | **Fluxo não comparável** | A sua carteira tem renda fixa e reserva, a de comparação não | Espelhar só o fluxo ARCA (decisão 3); comparar por TIR e TWR, nunca só pelo saldo | Baixo |
| S6 | **Execução irreal** | Aporte de R$ 100 não compra um lote de R$ 40 em várias ações; preço de fechamento × o seu preço de compra | Lotes inteiros e sobra em CDI, registrada; mínimo de ativos ajustado ao tamanho do aporte; o seu fluxo, não um fluxo ideal | Médio para aportes pequenos |
| S7 | **Custos e IR** | Uma estratégia de giro alto só vence sem custo | Mesmas regras de custo e IR do backtest; custo e IR na tabela | Baixo |
| S8 | **Dado ruim** | Um preço fora de escala move a curva (o caso do XPML11) | `price_sanity` (Fase 32); dado suspeito marcado | Baixo |
| S9 | **Custo de dados e de cálculo** | N carteiras × universo amplo × preços diários, com provedores gratuitos | Teto do universo; carga semanal de histórico do catálogo (33.1) estendida; o retroativo é calculado uma vez e guardado; atualização diária só do dia novo | Médio, ligado ao TD-06 |
| S10 | **Mudança de regra** | Ajustar a estratégia depois de ver o resultado | Regra congelada; mudar cria nova versão e nova carteira; a anterior fica, com o histórico intacto | Baixo |
| S11 | **Interpretação** | "A estratégia X ganhou 3 meses seguidos; vou trocar tudo" | Intervalos e P(melhor) em vez de ranking seco; tempo mínimo de registro prospectivo antes de mostrar o veredito; selo | Médio: é comportamental |
| S12 | **Proventos** | Somar dividendo e usar preço ajustado conta o provento duas vezes | Uma regra só: preço bruto para quantidade e valor, proventos datados como caixa (como o risco R7 da simulação) | Baixo, com teste |

## 9. Encaixe no código

- **Domínio:** `domain/comparison/`
  - `strategies.py`: interface e catálogo da seção 4;
  - `engine.py`: execução por eventos do fluxo real e valorização diária, reaproveitando os lotes, custos, IR e `PointInTimeView` do motor de backtest (33.2) em vez de duplicá-los;
  - `metrics.py`: TWR, TIR, atribuição, percentil e comparação bayesiana, reaproveitando `analytics.py`, `risk_metrics.py` e a 33.6.
- **Dados** (migração sequencial):
  - `comparison_portfolios`: definição, estratégia, parâmetros, versão, modo, criação e status;
  - `comparison_snapshots`: valor diário, fluxo, caixa, por classe e posições;
  - `comparison_trades`: operações simuladas, para o detalhe e a auditoria.
- **Worker:** rotina diária `update_comparison_portfolios` depois de `record_daily_snapshot`. Ela aplica o fluxo novo do dia, reconstitui as carteiras quando é a data e grava os retratos. O retroativo roda uma vez na criação, na fila das simulações, com limite de tempo.

## 10. Entregas em etapas (Fase 36)

| Etapa | Entrega | Critério de aceite |
|---|---|---|
| 36.0 | Decisões da seção 11 tomadas e esta proposta aprovada | Revisão do usuário |
| 36.1 | Fluxo espelhado a partir dos lançamentos (alcance ARCA ou total) | O fluxo reconstruído bate com o `net_flow` dos retratos |
| 36.2 | Motor por eventos com valorização diária, lotes, custos, IR e proventos | Verdade conhecida: a estratégia que replica a sua carteira reproduz a sua curva, a menos de custos e arredondamento de lotes |
| 36.3 | Interface de estratégia e o catálogo da seção 4 (sem `OPTIMIZED`) | Cada estratégia testada com uma visão point-in-time sintética; nenhuma lê o futuro |
| 36.4 | Persistência, modos prospectivo e retroativo e a rotina diária do worker | O histórico não muda quando a regra muda (nova versão) |
| 36.5 | Carteiras aleatórias e a posição da sua carteira na distribuição | Com uma carteira aleatória no lugar da sua, o percentil fica perto de 50% |
| 36.6 | Métricas, atribuição de Brinson e comparação bayesiana | Atribuição conferida à mão num caso de duas classes |
| 36.7 | Tela Comparar carteiras, MCP e painel exportável | Testes de UI e integração; `docker compose build` |
| 36.8 | Estratégia `OPTIMIZED` (depois da Fase 34) e escores point-in-time (depois da extensão da CVM) | Sem look-ahead nos fundamentos |

## 11. Decisões que precisam ser tomadas antes de implementar

1. **Estratégias iniciais:** o catálogo da seção 4 inteiro ou um subconjunto (recomendado começar com `POLICY_EQUAL`, `INDEX_ARCA`, `DIVIDENDS`, `VALUE`, `RANDOM` e `CDI`)? Quantas aleatórias (proposta: 200)?
2. **Universo:** carteira + watchlist, o catálogo filtrado pelo screener ou os dois, conforme a estratégia (recomendado)? Qual teto?
3. **Alcance do fluxo:** só a parte ARCA (recomendado) ou a carteira toda?
4. **Patrimônio de partida no prospectivo:** igual ao da sua carteira no dia da criação (recomendado, aplicado como um aporte inicial) ou zero?
5. **Retroativo:** calcular desde o seu primeiro aporte (recomendado, rotulado) ou só prospectivo?
6. **Proventos:** reinvestidos no próximo aporte (recomendado) ou acumulados à parte?
7. **Reconstituição:** trimestral (recomendado), semestral ou só nos aportes?
8. **Rebalanceamento:** só com aportes (recomendado, igual ao seu jeito de operar) ou também por banda, com IR?
9. **Onde fica a tela:** Visão geral (ao lado do Desempenho, recomendado) ou Ferramentas?
10. **Tempo mínimo de registro prospectivo** antes de mostrar o veredito "melhor ou pior que a sua carteira" (proposta: 12 meses), com as métricas visíveis desde o primeiro dia.

## 12. Relação com as outras fases

- **Fase 33:** reaproveita o motor de backtest (lotes, custos, IR, visão point-in-time), a camada bayesiana (intervalos, P(melhor)), a validação (33.8) e alimenta o laboratório (33.9).
- **Fase 34:** a composição otimizada entra como a estratégia `OPTIMIZED`, e o registro prospectivo é o melhor teste dela.
- **Fase 28 e extensão da CVM:** os fundamentos com data de publicação tiram o look-ahead do modo retroativo, e o cadastro com cancelamentos reduz o viés de sobrevivência.

## 13. Referências

- Brinson, G.; Hood, L.; Beebower, G. (1986). Determinants of Portfolio Performance. *Financial Analysts Journal* 42(4), 39–44.
- Dietz, P. (1966). *Pension Funds: Measuring Investment Performance*. Free Press (Dietz modificado, já usado na Fase 32).
- Bailey, D.; López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management* 40(5), 94–107.
- Burns, P. (2006). Random Portfolios for Evaluating Trading Strategies. Working paper, SSRN (carteiras aleatórias com as mesmas restrições como distribuição nula).
- Desenhos relacionados: [PORTFOLIO_SIMULATION_DESIGN.md](PORTFOLIO_SIMULATION_DESIGN.md) e [ASSET_COMPOSITION_OPTIMIZATION_DESIGN.md](ASSET_COMPOSITION_OPTIMIZATION_DESIGN.md).
