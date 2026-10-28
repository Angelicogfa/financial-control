# Simulação de Carteira: Backtesting e Machine Learning — Desenho e Teste de Estresse

*Status: desenho em revisão, nenhuma linha de código. Data: 2026-10-28. Fase proposta: 33 (ver [IMPLEMENTATION_PLAN.md](../todo/IMPLEMENTATION_PLAN.md)).*

Este documento descreve a ferramenta e, na seção 6, ataca o próprio desenho: cada premissa é testada contra o que pode dar errado com os dados, a estatística e o uso. A implementação só começa depois que as decisões da seção 8 forem tomadas.

## 1. Perguntas que a ferramenta responde

1. **Passado:** "se eu tivesse seguido a minha estratégia (ARCA, bandas, divisão interna, aportes mensais) desde a data X, onde eu estaria?", comparado com aportar o mesmo valor em CDI, Ibovespa, IPCA+ e numa carteira 60/40.
2. **Futuro (incerteza):** "com o aporte e a alocação de hoje, qual a faixa provável do patrimônio e da renda passiva em N anos, e com que chance chego à meta?" Aqui não existe um número único: a resposta é uma distribuição.
3. **Robustez:** "o resultado da minha estratégia depende de um período sortudo? Como ela se comporta em 2008, 2015-16, 2020 e 2022? Mudar a banda de 5 para 10 p.p. muda algo de verdade?"
4. **Machine learning (laboratório):** "algum modelo consegue informação útil (regime de mercado, risco à frente) melhor que regras simples?" O padrão é responder "não há evidência", até o contrário ser demonstrado fora da amostra.

**Fica de fora, de propósito:** previsão de preço de ativo para gerar ordem de compra, otimização automática que mude a política sozinha e qualquer coisa apresentada como recomendação de investimento.

## 2. Arquitetura em três camadas

| Camada | O que faz | Determinístico? | Depende de |
|---|---|---|---|
| **A. Backtest da estratégia** | Repete mês a mês as regras atuais (ou uma versão da política) sobre o histórico real | Sim | Séries de preço, CDI, IPCA, PU do Tesouro, política |
| **B. Simulação prospectiva** | Gera milhares de trajetórias futuras por bootstrap em blocos e cenários de juros | Sim, com semente fixa | Retornos históricos por classe, premissas da política |
| **C. Laboratório de ML** | Modelos de regime e de risco, sempre contra referências simples e em validação walk-forward | Sim, com semente | Camadas A e B, mais as features |

As camadas se empilham. A camada B usa os retornos que a A mostra como plausíveis, e a C só alimenta a B, como regime e covariância condicionais, quando passa nos portões estatísticos da seção 5. Nada da C entra no aporte real.

### 2.1 Encaixe no código (ADR 0009)
- **`domain/simulation/`** (puro, numpy):
  - `engine.py`: motor de eventos mensal do backtest;
  - `scenarios.py`: bootstrap em blocos estacionário e choques de juros;
  - `metrics.py`: reaproveita `analytics.py`, `risk_metrics.py` e `diversification.py`;
  - `validation.py`: walk-forward, CSCV/PBO e Deflated Sharpe;
  - `ml/`: modelos de regime e de risco, com interfaces mínimas.
- **`infra/data/`:** tabelas `simulation_runs` (parâmetros, hash dos dados, versão do código, status) e `simulation_results` (séries agregadas, métricas, percentis), em migration sequencial.
- **Worker:** as simulações rodam como tarefa assíncrona. A API cria o pedido e o worker executa com limite de tempo e de memória; a tela acompanha o status. É o mesmo problema do TD-09 (fila durável) e pode resolvê-lo.
- **API e MCP:** `POST /simulations`, `GET /simulations/{id}`, `GET /simulations` e as operações `simulation.run` e `simulation.get`.
- **Web:** página "Simular carteira" em Ferramentas, com abas Passado, Futuro, Robustez e Laboratório.
- **Reaproveitamento:**
  - `consolidate_portfolio` e `plan_contribution` (o backtest chama as mesmas regras de aporte em vez de reimplementar);
  - o motor de renda fixa e de IR (`fixed_income.py`, `tax/`);
  - `ArcaPolicy` e as versões da política;
  - as séries de `market_series`.

## 3. Camada A: backtest da estratégia

### 3.1 Motor
Passo mensal, no último dia útil do mês, com os eventos na ordem:
1. Atualizar os preços.
2. Creditar proventos e cupons.
3. Aplicar os eventos corporativos.
4. Aportar o valor do mês com `plan_contribution`, usando a política vigente naquela data.
5. Rebalancear, se a regra simulada mandar.
6. Pagar custos e IR.
7. Registrar o retrato.

As regras de cada simulação são parâmetros:
- aporte mensal (fixo ou corrigido pelo IPCA);
- data de início;
- universo de ativos;
- política (a atual, uma versão antiga ou uma variante: metas, bandas, divisão interna);
- tratamento de proventos (reinvestir ou acumular no caixa);
- custos (corretagem, emolumentos B3 de 0,03%, spread do Tesouro);
- impostos (IR em vendas com a isenção de R$ 20 mil/mês em ações, regressivo na renda fixa).

Saídas:
- curva do patrimônio e do investido, TWR e TIR;
- volatilidade, drawdown, Sharpe e Sortino, com os intervalos por bootstrap que já existem;
- tempo fora da banda, número de operações e custo total;
- as mesmas métricas para as referências com o mesmo fluxo de aportes, que é a comparação justa.

### 3.2 Universo de ativos e o problema central (point-in-time)
O backtest só vale se, em cada data, ele enxergar apenas o que se sabia naquele dia.

| Dado | Situação hoje | Tratamento |
|---|---|---|
| Preços de ações e FIIs | Yahoo traz anos de histórico, com o "Close" ajustado por proventos e desdobramentos; a brapi gratuita, só 3 meses | Guardar o preço ajustado (retorno total) para o desempenho e o bruto para quantidade e lote; registrar a fonte |
| Índices (IBOV, IFIX, S&P 500) | Gravados, com no máximo 10 anos | Estender sob demanda até o início da simulação |
| CDI, SELIC e IPCA | BCB SGS completo | Pronto |
| Tesouro | PU diário desde 2002 (Fase 26) | Pronto |
| Demonstrativos anuais | Guardados com a data do exercício; `first_seen_at` só vale de agora em diante | Disponibilidade assumida em data do exercício + 90 dias (prazo da DFP), com teste de sensibilidade a +120 dias |
| Checklist | Histórico append-only com `answered_at` | Usar a resposta vigente em cada data; antes da primeira resposta, o ativo segue a regra de elegibilidade "sem avaliação" |
| Política | Versões com `created_at` | Escolher entre a versão vigente em cada data e uma política fixa |
| Catálogo B3 | Só os ativos listados hoje | **Viés de sobrevivência**: ver o risco R2 na seção 6 |

## 4. Camada B: simulação prospectiva

- **Gerador:** bootstrap em blocos estacionário (Politis & Romano), com blocos médios de 6 a 12 meses, sobre os retornos mensais conjuntos das classes ARCA: IBOV para Ações, IFIX para Real Estate, S&P 500 em reais para Internacional e o CDI para Caixa. Ativos individuais não entram, porque o histórico de cada um é curto demais. Os blocos preservam a correlação entre classes e a persistência de volatilidade.
- **Juros:** cenários de CDI e IPCA pelas premissas da política (projetado ± variação), aplicados no Caixa e na renda fixa. Opcionalmente, um modelo de Vasicek calibrado na SELIC.
- **Fluxo:** aporte mensal com crescimento, rebalanceamento pelas bandas e IR na saída. A conta de renda passiva usa o DY normalizado da Fase 25.
- **Saídas:**
  - percentis 5, 25, 50, 75 e 95 do patrimônio e da renda;
  - probabilidade de atingir a meta;
  - pior queda esperada;
  - tempo até a independência financeira (F15).
- **Tamanho:** 5.000 trajetórias × 360 meses × 4 classes ≈ 7,2 milhões de passos, alguns segundos vetorizado em numpy. O limite fica na configuração do worker.

## 5. Camada C: laboratório de machine learning

### 5.1 Onde ML tem chance de ajudar (por ordem de plausibilidade)
1. **Regime de mercado:** modelo oculto de Markov (HMM, 2 ou 3 estados) ou mistura gaussiana sobre retorno e volatilidade mensais das classes. Serve para condicionar o bootstrap ("se estivermos num regime de estresse, as trajetórias começam assim") e para explicar períodos.
2. **Risco à frente:** volatilidade e covariância condicionais, como EWMA ou GARCH(1,1) por classe. A covariância com encolhimento de Ledoit-Wolf já existe e é a referência a superar.
3. **Previsão de retorno por classe:** gradient boosting ou regressão regularizada com features macro (juros reais, inclinação da curva, momentum de 12 meses, valuation agregado). É a aplicação mais sujeita a ilusão e entra só como experimento comparado com a média histórica e com "retorno zero acima do CDI".

### 5.2 Portões para um modelo sair do laboratório
Um modelo só pode alimentar a camada B se, fora da amostra, passar em todos:
- validação walk-forward com purga e embargo (sem sobreposição entre treino e teste);
- melhora sobre as referências simples nas métricas certas: log-likelihood ou QLIKE para risco, e para retorno, o erro de previsão e a utilidade econômica da alocação resultante;
- **Deflated Sharpe Ratio** acima de zero com 95% de confiança, considerando o número de tentativas registradas;
- **Probabilidade de overfitting do backtest (PBO, via CSCV)** abaixo de 20%;
- estabilidade: o resultado não some com a data de corte deslocada em ±12 meses.

Cada tentativa (modelo, features, hiperparâmetros) fica registrada em `simulation_runs`, porque o número de tentativas é parte do teste. O sistema conta as tentativas automaticamente; não é possível escolher o melhor de 200 testes em silêncio.

### 5.3 Dependências
Primeiro scikit-learn (mistura gaussiana, gradient boosting, regressão regularizada), depois hmmlearn e arch, se os portões justificarem. Nada de deep learning: com cerca de 240 observações mensais por classe, uma rede neural só decora o passado. Todas são bibliotecas sem custo, e as imagens Docker crescem um pouco (scikit-learn ~30 MB), o que precisa ser medido no `docker compose build`.

## 6. Teste de estresse do desenho

Cada risco tem a forma como quebraria o resultado, a mitigação desenhada e o que ainda sobra.

| # | Risco | Como quebra | Mitigação no desenho | Risco residual |
|---|---|---|---|---|
| R1 | **Look-ahead** (usar no passado o que só se soube depois) | Demonstrativo de 2021 usado em jan/2021; checklist respondido hoje aplicado em 2019; preço ajustado por um desdobramento futuro mudando a quantidade | Tabela de disponibilidade por dado (3.2); preço ajustado só para retorno, bruto para quantidade; checklist e política vigentes na data; teste automático "nenhum dado com data de disponibilidade > data simulada" | Médio: a data de publicação real dos demonstrativos não é conhecida; usar 90 dias e mostrar a sensibilidade |
| R2 | **Viés de sobrevivência** | O universo é o catálogo de hoje: as empresas que quebraram ou saíram da bolsa (OIBR, Americanas, Gol) não existem, e o passado parece melhor | Camada A roda por padrão só com os ativos que **você teve ou observou** (o ledger e a watchlist têm datas) e com os índices, que já carregam as empresas mortas; universo amplo "catálogo atual" fica marcado como enviesado | Alto para universo amplo; baixo para o padrão. A CVM tem o cadastro com datas de cancelamento (liga com a Fase 28) |
| R3 | **Overfitting / data snooping** | Testar 50 combinações de banda e meta e escolher a melhor; a "melhor estratégia" é ruído | Contagem obrigatória de tentativas; Deflated Sharpe e PBO; tela mostra a distribuição dos resultados de todas as variantes, não só a melhor; janela de validação reservada (os últimos 3 anos ficam fora da escolha) | Médio: depende do usuário respeitar a janela reservada; o sistema avisa quando ela é usada para escolher |
| R4 | **Amostra pequena e não estacionária** | Brasil tem cerca de 20 anos de dados limpos, com poucos ciclos; regime de juros de 2003 não é o de 2026 | Bootstrap em blocos com períodos ponderáveis; cenários de juros explícitos em vez de só histórico; intervalos de confiança em tudo; aviso de "dados insuficientes" com janela mínima (como na Fase 29) | Alto e irredutível: é limitação do mundo, não do código. A tela precisa dizer isso |
| R5 | **Custos e impostos ignorados** | Rebalancear todo mês parece ótimo sem corretagem, emolumentos e IR; a vantagem some na vida real | Custos e IR por padrão ligados; regra de isenção de R$ 20 mil, regressivo da renda fixa e come-cotas não se aplica; comparação sempre líquida | Baixo, depois de implementado; a apuração mensal exata é o TD-04/F1 |
| R6 | **Liquidez e lotes** | Simular compra de 0,37 ação, ou de um FII sem negócios | Lotes inteiros na B3 (o aporte real já faz), fracionário só no exterior; filtro de volume mínimo do screener; resíduo vai para o caixa | Baixo |
| R7 | **Proventos e eventos** | Somar dividendo e também usar preço ajustado conta o dividendo duas vezes | Uma regra só: preço ajustado = retorno total, sem crédito separado; ou preço bruto + proventos do ledger/B3. Teste dourado compara os dois caminhos num ativo conhecido | Baixo, com o teste |
| R8 | **Câmbio** | Ativo internacional em USD sem conversão, ou com o câmbio de hoje | Converter com a série USDBRL do dia; referência S&P 500 em reais | Baixo |
| R9 | **Interpretação errada** | "92% de chance de atingir a meta" lido como promessa; o usuário muda a carteira por um backtest | Texto sempre como faixa e premissa; percentis em vez de média; selo "simulação, não recomendação" (CVM: o sistema não faz recomendação de investimento); nenhuma ação automática a partir da simulação | Médio: é comportamental |
| R10 | **ML que parece funcionar** | Vazamento de feature (uma média móvel que usa o mês seguinte), escalonamento com dados do futuro, seleção de modelo no teste | Pipeline que ajusta escalas só no treino; walk-forward com purga; portões da 5.2; teste de "rótulos embaralhados" que precisa dar resultado nulo | Médio |
| R11 | **Custo computacional** | 5.000 trajetórias × variantes × walk-forward travam o worker e a API | Execução assíncrona no worker com limite de tempo e trajetórias; cache por hash de parâmetros e dados; numpy vetorizado; ML só sob pedido | Baixo |
| R12 | **Reprodutibilidade** | Rodar de novo dá outro número e ninguém sabe por quê | Semente fixa, hash dos dados de entrada, versão do código e da política gravados em cada execução; mesma entrada = mesmo resultado (teste) | Baixo |
| R13 | **Dados faltando** | Histórico do Yahoo com buracos ou sem um ativo; série de índice parando | Relatório de cobertura antes de rodar; ativos sem dado suficiente ficam fora com aviso, nunca são preenchidos com zero; mínimo de cobertura configurável | Baixo |
| R14 | **Dependência de provedores gratuitos** | Yahoo muda a API ou bloqueia; brapi limita | Séries gravadas localmente (o backtest não chama a internet durante a execução); uma rotina de carga separada, com erros no log do worker (Fase 19) | Médio, igual ao resto do sistema (TD-06) |

### 6.1 Cenários de estresse que o motor precisa atravessar
- **Crises históricas** com os pesos atuais e com a estratégia completa:
  - 2008 (set/2008–fev/2009);
  - recessão de 2015–16;
  - Joesley Day (mai/2017);
  - Covid (fev–mar/2020);
  - alta de juros de 2021–22.
- **Choques sintéticos:**
  - −30% em Ações num mês;
  - CDI +5 p.p. por 12 meses;
  - IPCA de 12% a.a.;
  - câmbio +40%;
  - FIIs −20% com DY constante.
- **Entradas extremas:** aporte zero, aporte cem vezes o patrimônio, meta de 100% numa classe, banda 0 e 50 p.p., carteira só de renda fixa, ativo sem histórico.

### 6.2 Testes de verdade conhecida (antes de qualquer resultado real)
- Retorno constante de 1% ao mês dá a fórmula fechada do valor futuro com aportes.
- Carteira 100% CDI reproduz a curva do CDI acumulado, já gravada.
- Rebalanceamento com retornos iguais entre as classes dá peso constante e custo zero.
- Bootstrap com bloco do tamanho da série devolve exatamente o histórico.
- O detector de vazamento acha uma feature plantada com o retorno do mês seguinte.
- Dados aleatórios (ruído) dão PBO próximo de 50% e Deflated Sharpe sem significância.

## 7. Entregas em etapas (Fase 33)

| Etapa | Entrega | Critério de aceite |
|---|---|---|
| 33.0 | Decisões da seção 8 tomadas e este documento aprovado | Revisão do usuário |
| 33.1 | Carga de séries históricas (preços ajustados e brutos, índices estendidos, câmbio) com relatório de cobertura | Cobertura medida para a carteira real |
| 33.2 | Motor do backtest (camada A) com custos, IR, eventos e política por data | Testes de verdade conhecida (6.2) e de look-ahead passando |
| 33.3 | Execução assíncrona, persistência e reprodutibilidade (`simulation_runs`) | Mesma entrada, mesmo resultado; limite de tempo respeitado |
| 33.4 | Tela Passado e Robustez, com crises históricas e variantes contadas | Distribuição das variantes visível; aviso de amostra |
| 33.5 | Camada B (bootstrap em blocos + cenários de juros) e tela Futuro | Percentis e probabilidade de meta com premissas explícitas |
| 33.6 | Validação estatística (walk-forward, Deflated Sharpe, PBO) | Teste com ruído dá o resultado nulo esperado |
| 33.7 | Laboratório de ML (regime e risco primeiro) com portões | Nenhum modelo entra na camada B sem passar nos portões |
| 33.8 | MCP, documentação e testes de integração e UI | Suíte completa e `docker compose build` |

Cada etapa é um PR. A 33.7 pode terminar com a conclusão "nenhum modelo passou", e esse é um resultado válido, registrado.

## 8. Decisões que precisam ser tomadas antes de implementar

1. **Universo do backtest:** só os ativos que você teve ou observou (recomendado, menos viés) ou também o catálogo atual, marcado como enviesado?
2. **Fonte do histórico longo:** aceitar o Yahoo como fonte de preços ajustados de 10 a 20 anos (gratuito, com buracos) ou limitar o backtest ao período em que há dados gravados?
3. **Escopo do ML:** começar só por regime e risco (recomendado) ou incluir já a previsão de retorno por classe como experimento?
4. **Horizonte e meta da simulação prospectiva:** meta de patrimônio, de renda passiva mensal ou as duas? A partir da F15 (independência financeira)?
5. **Política no passado:** a versão vigente em cada data (realista, mas a política só existe desde 2026) ou a política atual aplicada ao passado inteiro (mais útil, e precisa ser rotulada assim)?
6. **Orçamento de execução:** trajetórias e tempo máximo por simulação no worker (proposta: 5.000 trajetórias e 120 s).
