# Simulação de Carteira: Backtesting, Machine Learning e Inferência Bayesiana — Desenho e Teste de Estresse

*Status: desenho em revisão, nenhuma linha de código. Data: 2026-10-28 (revisão 2: ativos candidatos e lógica bayesiana). Fase proposta: 33 (ver [IMPLEMENTATION_PLAN.md](../todo/IMPLEMENTATION_PLAN.md)).*

Este documento descreve a ferramenta e, na seção 8, ataca o próprio desenho: cada premissa é testada contra o que pode dar errado com os dados, a estatística e o uso. As decisões da seção 10 foram tomadas em 2026-10-28 (10.1 a 10.4).

## 1. Perguntas que a ferramenta responde

1. **Passado:** "se eu tivesse seguido a minha estratégia (ARCA, bandas, divisão interna, aportes mensais) desde a data X, onde eu estaria?", comparado com aportar o mesmo valor em CDI, Ibovespa, IPCA+ e numa carteira 60/40.
2. **Futuro (incerteza):** "com o aporte e a alocação de hoje, qual a faixa provável do patrimônio e da renda passiva em N anos, e com que chance chego à meta?" Aqui não existe um número único: a resposta é uma distribuição.
3. **Robustez:** "o resultado da minha estratégia depende de um período sortudo? Como ela se comporta em 2008, 2015-16, 2020 e 2022? Mudar a banda de 5 para 10 p.p. muda algo de verdade?"
4. **Candidatos:** "que ativos que eu ainda não tenho, pelo histórico deles projetado nos cenários futuros e nas tendências de mercado, melhorariam a minha carteira em risco, diversificação, renda ou chance de atingir a meta?" A resposta é uma lista de candidatos para investigar, com a probabilidade de a melhora ser real, nunca uma ordem de compra.
5. **Confiança nas probabilidades:** "quando a simulação diz 80% de chance, isso costuma se confirmar?" A lógica bayesiana carrega a incerteza dos próprios parâmetros e mede, no passado, se as probabilidades previstas bateram com o que aconteceu (calibração).
6. **Machine learning (laboratório):** "algum modelo consegue informação útil (regime de mercado, risco à frente) melhor que regras simples?" O padrão é responder "não há evidência", até o contrário ser demonstrado fora da amostra.

**Fica de fora, de propósito:** previsão de preço de ativo para gerar ordem de compra, otimização automática que mude a política sozinha e qualquer coisa apresentada como recomendação de investimento.

## 2. Arquitetura em camadas

| Camada | O que faz | Determinístico? | Depende de |
|---|---|---|---|
| **A. Backtest da estratégia** | Repete mês a mês as regras atuais (ou uma versão da política) sobre o histórico real | Sim | Séries de preço, CDI, IPCA, PU do Tesouro, política |
| **B. Simulação prospectiva** | Gera milhares de trajetórias futuras por bootstrap em blocos e cenários de juros | Sim, com semente fixa | Retornos históricos por classe, premissas da política |
| **Bayes (transversal)** | Distribuição dos parâmetros em vez de um valor só; encolhimento dos candidatos; calibração e combinação dos geradores de cenário | Sim, com semente | Camadas A e B, priors versionados |
| **D. Candidatos** | Projeta ativos fora da carteira nos cenários de B e mede o efeito marginal de incluí-los | Sim, com semente | Watchlist, screener, histórico do ativo, camada B |
| **C. Laboratório de ML** | Modelos de regime e de risco, sempre contra referências simples e em validação walk-forward | Sim, com semente | Camadas A e B, mais as features |

As camadas se empilham:
- A camada B usa os retornos que a A mostra como plausíveis.
- A camada bayesiana envolve B, sorteando os parâmetros antes das trajetórias e combinando os geradores pelos pesos que a calibração dá.
- A camada D reaproveita as trajetórias de B para os candidatos.
- A camada C só alimenta B, com regime e covariância condicionais, quando passa nos portões da seção 7.

Nada de nenhuma camada entra no aporte real.

### 2.1 Encaixe no código (ADR 0009)
- **`domain/simulation/`** (puro, numpy):
  - `engine.py`: motor de eventos mensal do backtest;
  - `scenarios.py`: bootstrap em blocos estacionário e choques de juros;
  - `bayes.py`: posteriors conjugadas (normal-inverso-Wishart, normal hierárquica) e sorteio de parâmetros;
  - `calibration.py`: previsões walk-forward, PIT, cobertura, Brier e log score; pesos de combinação dos geradores;
  - `candidates.py`: modelo de fator por candidato, projeção e efeito marginal;
  - `metrics.py`: reaproveita `analytics.py`, `risk_metrics.py` e `diversification.py`;
  - `validation.py`: walk-forward, CSCV/PBO e Deflated Sharpe;
  - `ml/`: modelos de regime e de risco, com interfaces mínimas.
- **`infra/data/`:** tabelas `simulation_runs` (parâmetros, priors, hash dos dados, versão do código, status) e `simulation_results` (séries agregadas, métricas, percentis, intervalos de credibilidade), em migration sequencial.
- **Worker:** as simulações rodam como tarefa assíncrona. A API cria o pedido e o worker executa com limite de tempo e de memória; a tela acompanha o status. A calibração roda numa rotina semanal com resultado em cache. É o mesmo problema do TD-09 (fila durável) e pode resolvê-lo.
- **API e MCP:** `POST /simulations`, `GET /simulations/{id}`, `GET /simulations`, `GET /simulations/calibration` e as operações `simulation.run`, `simulation.get` e `simulation.calibration`.
- **Web:** página "Simular carteira" em Ferramentas, com abas Passado, Futuro, Candidatos, Robustez, Confiança (calibração) e Laboratório.
- **Reaproveitamento:**
  - `consolidate_portfolio` e `plan_contribution` (o backtest e o "e se" dos candidatos chamam as mesmas regras de aporte em vez de reimplementar);
  - o screener, a watchlist, o checklist, o valuation e as marcas de dado suspeito (Fases 11, 25 e 27) para escolher os candidatos;
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
| Catálogo B3 | Só os ativos listados hoje | **Viés de sobrevivência**: ver o risco R2 na seção 8 |

## 4. Camada B: simulação prospectiva

- **Gerador:** bootstrap em blocos estacionário (Politis & Romano), com blocos médios de 6 a 12 meses, sobre os retornos mensais conjuntos das classes ARCA: IBOV para Ações, IFIX para Real Estate, S&P 500 em reais para Internacional e o CDI para Caixa. Os blocos preservam a correlação entre classes e a persistência de volatilidade. Ativos individuais entram só pela camada D, com um modelo de fator sobre essas classes.
- **Juros:** cenários de CDI e IPCA pelas premissas da política (projetado ± variação), aplicados no Caixa e na renda fixa. Opcionalmente, um modelo de Vasicek calibrado na SELIC.
- **Tendências de mercado:** entram por três vias explícitas, nunca pela extrapolação do preço recente:
  - o regime atual (camada C, se aprovada), que condiciona o começo das trajetórias;
  - os cenários de juros;
  - o prior da camada bayesiana (seção 6), que pode incorporar uma visão de mercado com peso declarado, à maneira de Black-Litterman.
- **Fluxo:** aporte mensal com crescimento, rebalanceamento pelas bandas e IR na saída. A conta de renda passiva usa o DY normalizado da Fase 25.
- **Saídas:**
  - percentis 5, 25, 50, 75 e 95 do patrimônio e da renda;
  - probabilidade de atingir a meta, com intervalo de credibilidade (seção 6.3);
  - pior queda esperada;
  - tempo até a independência financeira (F15).
- **Tamanho:** 5.000 trajetórias × 360 meses × 4 classes ≈ 7,2 milhões de passos, alguns segundos vetorizado em numpy. O limite fica na configuração do worker.

## 5. Camada D: ativos candidatos (o que ainda não está na carteira)

### 5.1 De onde vêm os candidatos
Em ordem de preferência:
1. A watchlist.
2. Os resultados do screener com os filtros da Pesquisa: liquidez mínima, valuation, classe abaixo da banda.
3. Ativos escolhidos à mão no comparador (Fase 27).

Antes da simulação, cada candidato passa pelos mesmos filtros do aporte real:
- tipo e quadrante ARCA;
- checklist e elegibilidade da política;
- veredito de valuation;
- **sem dado suspeito** (Fase 25), ou com a marca visível;
- volume mínimo;
- histórico mínimo de 36 meses de retornos mensais.

O número de candidatos por execução tem um teto (proposta: 20), porque cada candidato a mais é uma comparação a mais (risco R16).

### 5.2 Como o histórico do candidato vira futuro
Usar o histórico do próprio ativo como se fosse o futuro seria extrapolar sorte. O candidato é modelado contra a sua classe:

`r_ativo = α + β · r_classe + ε`

- **β** (sensibilidade à classe) é estimado no histórico, com prior centrado em 1 (seção 6.2).
- **α** (o "a mais" do ativo) recebe um prior hierárquico centrado em zero e é fortemente encolhido: um ativo que subiu muito nos últimos anos não leva essa tendência inteira para o futuro.
- **ε** (o idiossincrático) é sorteado em blocos do próprio resíduo histórico, o que preserva caudas e volatilidade próprias.
- **r_classe** vem das trajetórias da camada B, que já carregam os cenários de juros, o regime e a variabilidade futura.
- **Evento de ruptura:** com uma probabilidade pequena e declarada, uma queda de 60% a 90% (Americanas 2023, OIBR), porque o histórico de quem sobreviveu não mostra esse risco.

### 5.3 O que é medido
Para cada candidato, a carteira de hoje recebe o candidato no peso que o próximo aporte daria a ele pela política (`plan_contribution` com o candidato elegível). Opcionalmente, recebe um peso fixo informado. Contra a carteira sem o candidato, mede-se:
- Δ índice de diversificação (Choueifaty) e Δ contribuição ao risco por quadrante;
- Δ CVaR 95% e Δ pior queda nas trajetórias;
- Δ renda passiva projetada (DY normalizado);
- Δ probabilidade de atingir a meta.

Cada Δ sai como distribuição. A tela mostra a **probabilidade a posteriori de a melhora ser real** (P(Δ > 0)), a mediana e o intervalo de credibilidade. Mostra também a **estabilidade do ranking** (a chance de o candidato aparecer entre os cinco primeiros quando o sorteio muda) e os candidatos que pioram a carteira, não só os melhores.

### 5.4 O que a tela diz
A lista se chama "candidatos para investigar". Cada linha leva ao detalhe do ativo, ao checklist e ao comparador. Não há botão de compra, e o aporte real continua sendo o do simulador de aporte, com a política.

## 6. Lógica bayesiana: incerteza dos parâmetros e validação dos cenários

### 6.1 Incerteza dos parâmetros
O bootstrap da camada B trata o passado como se fosse a distribuição verdadeira. A camada bayesiana reconhece que médias e covariâncias das classes são estimativas com erro:
- **Prior normal-inverso-Wishart** sobre a média e a covariância mensais das quatro classes. A média do prior vem das premissas de projeção da política (já versionadas) ou de um prêmio de longo prazo conservador. A covariância do prior vem do Ledoit-Wolf já existente, e o peso do prior é declarado em "meses equivalentes de dados".
- **Posterior conjugada** em fórmula fechada, sem MCMC.
- **Em cada trajetória**, os parâmetros são sorteados da posterior antes de gerar os retornos. Os intervalos ficam mais largos, que é o tamanho honesto da incerteza.
- **Bootstrap bayesiano (Rubin):** os blocos históricos recebem pesos de Dirichlet em vez de pesos iguais. Isso dá a incerteza do próprio gerador por reamostragem.

### 6.2 Encolhimento dos candidatos (modelo hierárquico)
- α de cada candidato segue `N(0, τ²_classe)`, com τ da classe estimado por Bayes empírico a partir dos ativos da mesma classe com histórico.
- O posterior de α encolhe para zero na proporção do ruído do ativo: histórico curto ou volátil leva a quase nenhum α.
- β segue `N(1, σ²_β)`, encolhendo betas extremos estimados com poucos dados.
- O resultado alimenta o sorteio do 5.2, de modo que um candidato só aparece como melhora se o efeito sobreviver ao encolhimento.

### 6.3 Probabilidades com intervalo
Toda probabilidade da tela (atingir a meta, perder mais de 10% em 12 meses, bater o CDI, a melhora do candidato) sai com um intervalo de credibilidade de 90%, que combina:
- o sorteio de parâmetros (6.1);
- o número finito de trajetórias (Beta(k + 1, n − k + 1) sobre as trajetórias favoráveis);
- a incerteza entre geradores (6.4).

"Chance de 74% (64% a 82%)" é mais honesto que "74%".

### 6.4 Validação dos cenários: calibração no passado
Para saber se as probabilidades merecem confiança, a simulação é testada contra o que aconteceu:
1. **Previsões walk-forward:** em cada origem passada (mensal, de 2008 em diante), o gerador usa só os dados até ali e produz a distribuição dos 12 meses seguintes de cada classe e da carteira-modelo.
2. **Comparação com o realizado:**
   - **PIT** (posição do realizado na distribuição prevista; uniforme = bem calibrado);
   - **cobertura** (o intervalo de 90% conteve o realizado em cerca de 90% das vezes?);
   - **Brier** para eventos (perda > 10%, bater o CDI);
   - **log score preditivo**.
3. **Inferência sobre a calibração:** a cobertura observada (k acertos em n janelas) vira uma posterior Beta-binomial, com n efetivo corrigido pela sobreposição das janelas. Se o intervalo de 90% dessa posterior não inclui a cobertura nominal, o gerador é marcado como **mal calibrado** e a tela avisa.
4. **Combinação bayesiana dos geradores:** bootstrap simples, bootstrap bayesiano, normal bayesiana e, se aprovado, bootstrap condicionado ao regime. Recebem pesos por *stacking* do log score preditivo fora da amostra, uma combinação bayesiana robusta a modelos errados. O gerador da camada B é essa mistura, e os pesos ficam visíveis na aba Confiança.
5. **Resultado inconclusivo é válido:** com cerca de 18 anos de origens anuais independentes, a calibração pode não distinguir bom de ruim. A tela diz isso em vez de esconder.

### 6.5 Portão bayesiano no laboratório de ML
Além do Deflated Sharpe e do PBO (7.2), um modelo só passa se a probabilidade a posteriori de superar a referência simples for de pelo menos 95%. Essa probabilidade é a da diferença de log score fora da amostra, estimada por bootstrap bayesiano.

### 6.6 Implementação e o papel do PyMC
**Decisão: modelo híbrido.** As peças bayesianas do caminho principal têm solução fechada:
- normal-inverso-Wishart para média e covariância;
- Bayes-Stein para as médias;
- normal-normal com Bayes empírico para o α dos candidatos;
- Beta-binomial para a cobertura.

Essas peças ficam em numpy, com testes de verdade conhecida (8.2). O **PyMC** entra em dois papéis:
1. **Oráculo nos testes** (dependência só de desenvolvimento): os mesmos dados passam pelas fórmulas fechadas e por um modelo PyMC equivalente, e as médias e variâncias da posterior precisam coincidir dentro do erro de amostragem. É isso que protege contra erro na escrita da lógica, sem levar o PyMC para a execução.
2. **Laboratório** (grupo opcional de dependências): modelos sem solução fechada, onde amostrar é o único caminho. Exemplos: retornos com caudas pesadas (t de Student), volatilidade estocástica, HMM bayesiano, hierarquia com τ totalmente bayesiano. Aí o PyMC reduz o risco: o amostrador NUTS e os diagnósticos (R-hat, ESS, divergências, via ArviZ) já estão prontos e testados.

**Por que não usar o PyMC no caminho principal:**
- Em modelos conjugados, o MCMC aproxima o que a fórmula dá exato, com erro de amostragem e tempo de execução.
- Ele acrescenta modos de falha que precisam de vigilância: não convergência e divergências.
- Os resultados podem variar entre versões.
- O PyTensor compila o modelo (C ou Numba), e a documentação recomenda instalar pelo conda-forge, enquanto as nossas imagens usam uv/pip em base slim. Seria preciso um compilador ou o Numba na imagem do worker, com o custo de tamanho e de build medido no `docker compose build` antes de aceitar.
- O PyMC não elimina a lógica que pode estar errada: ela migra da álgebra para a especificação do modelo (priors, parametrização), que também precisa de testes.

Os priors são parâmetros versionados da simulação, gravados em `simulation_runs`.

## 7. Camada C: laboratório de machine learning

### 7.1 Onde ML tem chance de ajudar (por ordem de plausibilidade)
1. **Regime de mercado:** modelo oculto de Markov (HMM, 2 ou 3 estados) ou mistura gaussiana sobre retorno e volatilidade mensais das classes. O HMM já é bayesiano no filtro (probabilidade de cada regime dado o histórico). Serve para condicionar o bootstrap ("se estivermos num regime de estresse, as trajetórias começam assim") e para explicar períodos.
2. **Risco à frente:** volatilidade e covariância condicionais, como EWMA ou GARCH(1,1) por classe. A covariância com encolhimento de Ledoit-Wolf já existe e é a referência a superar.
3. **Previsão de retorno por classe:** gradient boosting ou regressão regularizada com features macro (juros reais, inclinação da curva, momentum de 12 meses, valuation agregado). É a aplicação mais sujeita a ilusão e entra só como experimento comparado com a média histórica e com "retorno zero acima do CDI".

### 7.2 Portões para um modelo sair do laboratório
Um modelo só pode alimentar a camada B se, fora da amostra, passar em todos:
- validação walk-forward com purga e embargo (sem sobreposição entre treino e teste);
- melhora sobre as referências simples nas métricas certas: log-likelihood ou QLIKE para risco, e para retorno, o erro de previsão e a utilidade econômica da alocação resultante;
- **Deflated Sharpe Ratio** acima de zero com 95% de confiança, considerando o número de tentativas registradas;
- **Probabilidade de overfitting do backtest (PBO, via CSCV)** abaixo de 20%;
- **probabilidade a posteriori de superar a referência** de pelo menos 95% (6.5);
- estabilidade: o resultado não some com a data de corte deslocada em ±12 meses.

Cada tentativa (modelo, features, hiperparâmetros) fica registrada em `simulation_runs`, porque o número de tentativas é parte do teste. O sistema conta as tentativas automaticamente; não é possível escolher o melhor de 200 testes em silêncio.

### 7.3 Dependências
Primeiro scikit-learn (mistura gaussiana, gradient boosting, regressão regularizada), depois hmmlearn e arch, se os portões justificarem. Nada de deep learning: com cerca de 240 observações mensais por classe, uma rede neural só decora o passado. Todas são bibliotecas sem custo, e as imagens Docker crescem um pouco (scikit-learn ~30 MB), o que precisa ser medido no `docker compose build`. A camada bayesiana não acrescenta dependência: usa numpy, e scipy já vem como dependência do pandas.

## 8. Teste de estresse do desenho

Cada risco tem a forma como quebraria o resultado, a mitigação desenhada e o que ainda sobra.

| # | Risco | Como quebra | Mitigação no desenho | Risco residual |
|---|---|---|---|---|
| R1 | **Look-ahead** (usar no passado o que só se soube depois) | Demonstrativo de 2021 usado em jan/2021; checklist respondido hoje aplicado em 2019; preço ajustado por um desdobramento futuro mudando a quantidade | Tabela de disponibilidade por dado (3.2); preço ajustado só para retorno, bruto para quantidade; checklist e política vigentes na data; teste automático "nenhum dado com data de disponibilidade > data simulada" | Médio: a data de publicação real dos demonstrativos não é conhecida; usar 90 dias e mostrar a sensibilidade |
| R2 | **Viés de sobrevivência** | O universo é o catálogo de hoje: as empresas que quebraram ou saíram da bolsa (OIBR, Americanas, Gol) não existem, e o passado parece melhor | Camada A roda por padrão só com os ativos que **você teve ou observou** (o ledger e a watchlist têm datas) e com os índices, que já carregam as empresas mortas; universo amplo "catálogo atual" fica marcado como enviesado; candidatos (D) nunca entram no backtest, só na projeção, com o evento de ruptura | Alto para universo amplo; baixo para o padrão. A CVM tem o cadastro com datas de cancelamento (liga com a Fase 28) |
| R3 | **Overfitting / data snooping** | Testar 50 combinações de banda e meta e escolher a melhor; a "melhor estratégia" é ruído | Contagem obrigatória de tentativas; Deflated Sharpe e PBO; tela mostra a distribuição dos resultados de todas as variantes, não só a melhor; janela de validação reservada (os últimos 3 anos ficam fora da escolha) | Médio: depende do usuário respeitar a janela reservada; o sistema avisa quando ela é usada para escolher |
| R4 | **Amostra pequena e não estacionária** | Brasil tem cerca de 20 anos de dados limpos, com poucos ciclos; regime de juros de 2003 não é o de 2026 | Bootstrap em blocos com períodos ponderáveis; cenários de juros explícitos em vez de só histórico; incerteza de parâmetros na posterior (6.1); intervalos em tudo; aviso de "dados insuficientes" com janela mínima (como na Fase 29) | Alto e irredutível: é limitação do mundo, não do código. A tela precisa dizer isso |
| R5 | **Custos e impostos ignorados** | Rebalancear todo mês parece ótimo sem corretagem, emolumentos e IR; a vantagem some na vida real | Custos e IR por padrão ligados; regra de isenção de R$ 20 mil e regressivo da renda fixa; comparação sempre líquida | Baixo, depois de implementado; a apuração mensal exata é o TD-04/F1 |
| R6 | **Liquidez e lotes** | Simular compra de 0,37 ação, ou de um FII sem negócios | Lotes inteiros na B3 (o aporte real já faz), fracionário só no exterior; filtro de volume mínimo do screener; resíduo vai para o caixa | Baixo |
| R7 | **Proventos e eventos** | Somar dividendo e também usar preço ajustado conta o dividendo duas vezes | Uma regra só: preço ajustado = retorno total, sem crédito separado; ou preço bruto + proventos do ledger/B3. Teste dourado compara os dois caminhos num ativo conhecido | Baixo, com o teste |
| R8 | **Câmbio** | Ativo internacional em USD sem conversão, ou com o câmbio de hoje | Converter com a série USDBRL do dia; referência S&P 500 em reais | Baixo |
| R9 | **Interpretação errada** | "92% de chance de atingir a meta" lido como promessa; o usuário muda a carteira por um backtest ou compra o primeiro candidato | Texto sempre como faixa e premissa; percentis e intervalos de credibilidade em vez de ponto; selo "simulação, não recomendação" (CVM: o sistema não faz recomendação de investimento); candidatos como "para investigar", sem botão de compra; nenhuma ação automática | Médio: é comportamental |
| R10 | **ML que parece funcionar** | Vazamento de feature (uma média móvel que usa o mês seguinte), escalonamento com dados do futuro, seleção de modelo no teste | Pipeline que ajusta escalas só no treino; walk-forward com purga; portões da 7.2; teste de "rótulos embaralhados" que precisa dar resultado nulo | Médio |
| R11 | **Custo computacional** | 5.000 trajetórias × variantes × candidatos × walk-forward travam o worker e a API | Execução assíncrona no worker com limite de tempo e trajetórias; trajetórias de B reaproveitadas pelos candidatos (D não regera a classe); calibração semanal em cache; numpy vetorizado e posteriors em fórmula fechada; ML só sob pedido | Baixo |
| R12 | **Reprodutibilidade** | Rodar de novo dá outro número e ninguém sabe por quê | Semente fixa, hash dos dados de entrada, priors, versão do código e da política gravados em cada execução; mesma entrada = mesmo resultado (teste) | Baixo |
| R13 | **Dados faltando** | Histórico do Yahoo com buracos ou sem um ativo; série de índice parando | Relatório de cobertura antes de rodar; ativos sem dado suficiente ficam fora com aviso, nunca são preenchidos com zero; mínimo de cobertura configurável | Baixo |
| R14 | **Dependência de provedores gratuitos** | Yahoo muda a API ou bloqueia; brapi limita | Séries gravadas localmente (a simulação não chama a internet durante a execução); uma rotina de carga separada, com erros no log do worker (Fase 19) | Médio, igual ao resto do sistema (TD-06) |
| R15 | **Prior arbitrário dominando** | Um prior otimista (retorno de ações de 15% a.a.) produz a "chance de 95%" que o usuário quer ver | Três priors lado a lado (vago, da política, conservador); peso do prior em meses equivalentes, sempre visível; aviso quando o prior pesa mais que os dados; priors versionados e gravados na execução | Médio: a escolha continua sendo do usuário, mas fica explícita |
| R16 | **Maldição do vencedor nos candidatos** | Simular 200 ações e mostrar as 5 melhores: são as mais sortudas do histórico, e o efeito some no futuro | Teto de candidatos por execução; α encolhido por modelo hierárquico (6.2); probabilidade de melhora com intervalo; estabilidade do ranking; contagem de candidatos testados no mês, com aviso | Médio |
| R17 | **Candidato com histórico curto ou de sobrevivente** | IPO recente com dois anos de alta; candidato que só existe porque não quebrou | Mínimo de 36 meses; histórico curto leva a mais encolhimento (o prior domina); evento de ruptura com probabilidade declarada; candidatos nunca entram no backtest histórico | Médio |
| R18 | **Tendência extrapolada** | Momentum dos últimos anos projetado para frente; reversão (como a de 2009) pega a carteira no pior momento | Tendências só via regime, juros e prior declarado (4); α encolhido; cenário de reversão de momentum no estresse (8.1) | Médio |
| R19 | **Calibração sem dados suficientes** | Com janelas sobrepostas, 200 previsões mensais parecem muitas, mas são só cerca de 18 anos independentes; a calibração "passa" por acaso | n efetivo corrigido pela sobreposição; posterior Beta-binomial da cobertura com intervalo; estado "calibração inconclusiva" exibido | Alto e irredutível, como R4 |
| R20 | **Probabilidade bayesiana lida como frequência garantida** | "P(melhora) = 92%" lido como certeza de lucro | Texto padronizado: "credibilidade dado o modelo e os dados até hoje"; a aba Confiança mostra se as probabilidades do passado se confirmaram | Médio: comportamental |
| R21 | **Dado ruim entrando no candidato** | Indicador fora de escala ou divergente (Fase 25) faz o candidato passar no valuation | Candidatos com `suspicious` ficam fora por padrão ou entram marcados; o filtro usa o mesmo veredito do aporte real | Baixo |

### 8.1 Cenários de estresse que o motor precisa atravessar
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
- **Candidatos:**
  - ruptura de um candidato (−80% em um mês);
  - crise setorial que atinge todos os candidatos do mesmo setor;
  - reversão de momentum (os vencedores dos últimos 3 anos perdem 40%).
- **Bayes:** prior otimista contra dados ruins; prior vago com 24 meses de dados; dados gerados por um processo diferente do modelo (caudas pesadas, mudança de regime no meio).
- **Entradas extremas:** aporte zero, aporte cem vezes o patrimônio, meta de 100% numa classe, banda 0 e 50 p.p., carteira só de renda fixa, ativo sem histórico.

### 8.2 Testes de verdade conhecida (antes de qualquer resultado real)
- Retorno constante de 1% ao mês dá a fórmula fechada do valor futuro com aportes.
- Carteira 100% CDI reproduz a curva do CDI acumulado, já gravada.
- Rebalanceamento com retornos iguais entre as classes dá peso constante e custo zero.
- Bootstrap com bloco do tamanho da série devolve exatamente o histórico.
- O detector de vazamento acha uma feature plantada com o retorno do mês seguinte.
- Dados aleatórios (ruído) dão PBO próximo de 50% e Deflated Sharpe sem significância.
- Posterior conjugada:
  - com amostra enorme, se aproxima da média amostral;
  - sem dados, devolve o prior.
- Dados gerados pelo próprio modelo dão PIT uniforme e cobertura nominal na calibração.
- Candidatos de ruído puro (α = 0 e β = 1 verdadeiros) dão P(melhora) perto do efeito de diversificação apenas, com ranking instável entre sorteios.
- Um candidato sintético com α verdadeiro alto e histórico longo é reconhecido; o mesmo α com 36 meses de histórico é encolhido.

## 9. Entregas em etapas (Fase 33)

| Etapa | Entrega | Critério de aceite |
|---|---|---|
| 33.0 | Decisões da seção 10 tomadas e este documento aprovado | Revisão do usuário |
| 33.1 | Carga de séries históricas (preços ajustados e brutos, índices estendidos, câmbio) com relatório de cobertura | Cobertura medida para a carteira real |
| 33.2 | Motor do backtest (camada A) com custos, IR, eventos e política por data | Testes de verdade conhecida (8.2) e de look-ahead passando |
| 33.3 | Execução assíncrona, persistência e reprodutibilidade (`simulation_runs`) | Mesma entrada, mesmo resultado; limite de tempo respeitado |
| 33.4 | Tela Passado e Robustez, com crises históricas e variantes contadas | Distribuição das variantes visível; aviso de amostra |
| 33.5 | Camada B (bootstrap em blocos + cenários de juros) e tela Futuro | Percentis e probabilidade de meta com premissas explícitas |
| 33.6 | Camada bayesiana: posterior dos parâmetros, intervalos de credibilidade, calibração walk-forward e combinação dos geradores; aba Confiança | Testes de verdade conhecida bayesianos; calibração com dado do próprio modelo dá cobertura nominal |
| 33.7 | Camada D: candidatos (filtros, modelo de fator hierárquico, efeito marginal, estabilidade do ranking); aba Candidatos | Candidatos de ruído não aparecem como melhora robusta; teto e contagem de candidatos respeitados |
| 33.8 | Validação estatística (walk-forward, Deflated Sharpe, PBO, portão bayesiano) | Teste com ruído dá o resultado nulo esperado |
| 33.9 | Laboratório de ML (regime e risco primeiro) com portões | Nenhum modelo entra na camada B sem passar nos portões |
| 33.10 | MCP, documentação e testes de integração e UI | Suíte completa e `docker compose build` |

Cada etapa é um PR. A 33.9 pode terminar com a conclusão "nenhum modelo passou", e esse é um resultado válido, registrado.

## 10. Decisões que precisam ser tomadas antes de implementar

1. **Universo do backtest:** só os ativos que você teve ou observou (recomendado, menos viés) ou também o catálogo atual, marcado como enviesado?
2. **Fonte do histórico longo:** aceitar o Yahoo como fonte de preços ajustados de 10 a 20 anos (gratuito, com buracos) ou limitar o backtest ao período em que há dados gravados?
3. **Escopo do ML:** começar só por regime e risco (recomendado) ou incluir já a previsão de retorno por classe como experimento?
4. **Horizonte e meta da simulação prospectiva:** meta de patrimônio, de renda passiva mensal ou as duas? A partir da F15 (independência financeira)?
5. **Política no passado:** a versão vigente em cada data (realista, mas a política só existe desde 2026) ou a política atual aplicada ao passado inteiro (mais útil, e precisa ser rotulada assim)?
6. **Orçamento de execução:** trajetórias e tempo máximo por simulação no worker (proposta: 5.000 trajetórias e 120 s).
7. **Fonte dos candidatos:** só a watchlist, a watchlist mais o screener com os filtros da Pesquisa (recomendado), ou também a lista livre do comparador? Qual o teto por execução (proposta: 20)?
8. **Prior padrão da camada bayesiana:** o das premissas de projeção da política (recomendado, já versionado), um conservador (prêmio de ações sobre o CDI de 3% a.a.) ou o vago? Quanto peso, em meses equivalentes (proposta: 60)?
9. **Evento de ruptura dos candidatos:** probabilidade anual e tamanho da queda (proposta: 1% ao ano, queda de 70%), ou desligado?
10. **Calibração:** com que frequência recalcular (proposta: semanal) e o que fazer quando um gerador estiver mal calibrado: só avisar (recomendado) ou tirá-lo da mistura?

### 10.1 Decisões tomadas (2026-10-28)
| # | Decisão | Fundamento |
|---|---|---|
| 1 | **Universo: inclui o catálogo atual**, além dos ativos que você teve ou observou | Escolha do usuário. Como o catálogo só tem sobreviventes, o resultado com o catálogo leva o selo "universo com viés de sobrevivência", entra o evento de ruptura (decisão 9) e a comparação com o universo "teve/observou" fica sempre ao lado |
| 2 | **Yahoo** como fonte do histórico longo (preço ajustado) | Escolha do usuário; relatório de cobertura e nada de preencher buracos (R13) |
| 3 | **ML: só regime e risco** | Recomendação seguida |
| 4 | **Meta: patrimônio e renda passiva mensal** | Escolha do usuário |
| 5 | **Política no passado: as regras atuais aplicadas ao histórico inteiro**, com a política vigente em cada data como opção | Ver 10.2 |
| 6 | **Orçamento: 5.000 trajetórias e 120 s** por simulação | Recomendação seguida |
| 7 | **Candidatos: watchlist + screener com os filtros da Pesquisa, até 20 por execução** | Recomendação seguida |
| 8 | **Prior: média das classes encolhida por Bayes-Stein para um alvo de prêmios conservadores sobre o CDI**, com a intensidade dada pelos dados; premissas da política como "visões" à la Black-Litterman, com confiança declarada | Ver 10.3 |
| 9 | **Ruptura: probabilidade anual pela qualidade de crédito (zona do Z''-score); perda central de 55%, estresse em 90%** | Ver 10.4 |
| 10 | **Calibração semanal, só avisando** quando um gerador estiver mal calibrado | Recomendação seguida |

### 10.2 Política no passado (decisão 5)
- **Regra como objeto do teste.** O protocolo de Arnott, Harvey e Markowitz (2019) e o trabalho de Bailey, Borwein, López de Prado e Zhu sobre overfitting de backtest tratam a estratégia como uma regra fixa, especificada antes, e testada no histórico inteiro. Aplicar as regras atuais em todo o período é isso. A política vigente em cada data não serve como padrão por dois motivos: a política só existe desde 2026, e as mudanças dela são decisões discricionárias, não uma regra.
- **Viés de retrospectiva.** As regras atuais foram escolhidas por quem já conhecia o passado. Por isso o backtest com elas é **descritivo**, não uma validação. Os últimos 3 anos ficam reservados (R3), e toda variante de regra testada entra na contagem de tentativas (PBO, Deflated Sharpe).
- **Opção:** a política vigente em cada data continua disponível, para comparar o que você de fato decidiu com a regra fixa.

### 10.3 Prior das médias (decisão 8)
- **Por que encolher:** a média amostral é um estimador ruim para a média esperada; o resultado de Stein mostra que ela é inadmissível. Jorion (1986) propôs o estimador Bayes-Stein, o bayesiano mais usado nessa literatura. Ele puxa as médias para um alvo comum, com intensidade calculada pelos próprios dados: `w = (N + 2) / ((N + 2) + T·(μ̂ − μ₀)ᵀ Σ⁻¹ (μ̂ − μ₀))`. Isso substitui o peso fixo de 60 meses proposto antes. O peso efetivo, em meses equivalentes, continua visível (R15).
- **O alvo (μ₀):** prêmios conservadores sobre o CDI projetado, por classe. A referência é o Global Investment Returns Yearbook (Dimson, Marsh e Staunton):
  - prêmio histórico das ações mundiais sobre títulos de curto prazo de cerca de 4,2–4,3% a.a.;
  - prêmio esperado estimado pelos autores entre 3% e 3,5%.

  Proposta: Ações Brasil e Internacional (em reais) a **CDI + 3% a.a.**, Real Estate (FIIs) a **CDI + 2% a.a.** e Caixa ao **CDI**. Prêmios maiores para o Brasil, como o prêmio de risco-país de Damodaran (perto de 3,7% em jan/2023), ficam como sensibilidade, e não como alvo, porque o histórico recente do Ibovespa contra o CDI não os sustenta.
- **Covariância:** prior centrado no Ledoit-Wolf que já existe.
- **Visões:** as premissas de projeção da política entram como visões à la Black-Litterman, com a confiança declarada. Sem visão, o resultado é só o encolhimento.

### 10.4 Evento de ruptura (decisão 9)
- **Perda:** Shumway (1997) mostrou que os retornos de saída de bolsa por mau desempenho faltavam na base CRSP e eram grandes. Shumway e Warther (1999) estimaram em **−55%** a correção adequada no Nasdaq. Na falência, o acionista costuma perder quase tudo. Proposta: perda central de 55%, com sensibilidade em 90%.
- **Probabilidade:** pela qualidade de crédito, como o próprio Altman recomenda hoje: associar o escore a uma nota de crédito equivalente e usar a taxa histórica de default dessa nota. A média histórica de default anual da S&P para grau especulativo foi de 4,91% (1981–2004), e a de grau de investimento fica perto de zero. Proposta:
  - Z''-score em zona de estresse: **5% ao ano**;
  - zona cinza: **1% ao ano**;
  - zona segura: **0,2% ao ano**;
  - sem demonstrativos para calcular o escore (a maioria hoje, ver Fase 29): **1% ao ano**;
  - FIIs (sem alavancagem relevante): **0,5% ao ano**.

  Os valores são parâmetros da simulação, gravados em cada execução.

### 10.5 Referências
- Arnott, R.; Harvey, C.; Markowitz, H. (2019). A Backtesting Protocol in the Era of Machine Learning. *Journal of Financial Data Science* 1(1), 64–74. https://papers.ssrn.com/abstract=3275654
- Bailey, D.; Borwein, J.; López de Prado, M.; Zhu, Q. The Probability of Backtest Overfitting. *Journal of Computational Finance*. https://papers.ssrn.com/abstract=2326253
- Jorion, P. (1986). Bayes-Stein Estimation for Portfolio Analysis. *Journal of Financial and Quantitative Analysis* 21(3), 279–292. https://ideas.repec.org/a/cup/jfinqa/v21y1986i03p279-292_01.html
- Black, F.; Litterman, R. Modelo de equilíbrio com visões (resumo da formulação): https://www.mathworks.com/help/finance/black-litterman-portfolio-optimization.html
- Dimson, E.; Marsh, P.; Staunton, M. Global Investment Returns Yearbook (prêmio de risco das ações). https://www.london.edu/news/keeping-faith-with-stocks
- Damodaran, A. Prêmio de risco-país (slides, jan/2023). https://pages.stern.nyu.edu/~adamodar/podcasts/valUGspr23/session5slides.pdf
- Shumway, T. (1997). The Delisting Bias in CRSP Data. *Journal of Finance* 52(1), 327–340. https://ideas.repec.org/a/bla/jfinan/v52y1997i1p327-40.html
- Shumway, T.; Warther, V. (1999). The Delisting Bias in CRSP's Nasdaq Data and Its Implications for the Size Effect. https://academicnewsletter.sufe.edu.cn/info/361673
- S&P Global Ratings. Annual Global Corporate Default and Rating Transition Study. https://www.spglobal.com/ratings/en/research/articles/230425-default-transition-and-recovery-2022-annual-global-corporate-default-and-rating-transition-study-12702145 ; média de grau especulativo 1981–2004: https://investmentexecutive.com/?p=289769
- Altman, E. Z-score e nota de crédito equivalente (entrevista ao CFA Institute). https://rpc.cfainstitute.org/blogs/enterprising-investor/2016/the-altman-z-score-after-50-years-use-and-misuse
- PyMC: instalação recomendada e backends. https://pymc.readthedocs.io/en/latest/installation.html ; PyTensor (C, JAX, Numba): https://pypi.org/project/pytensor
