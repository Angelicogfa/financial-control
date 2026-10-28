# Otimização da Composição de Ativos dentro do ARCA — Proposta e Teste de Estresse

*Status: proposta para revisão, nenhuma linha de código. Data: 2026-10-28. Fase proposta: 34 (ver [IMPLEMENTATION_PLAN.md](../todo/IMPLEMENTATION_PLAN.md)). Depende da Fase 33 (simulação, camada bayesiana, candidatos e validação) e ganha insumos com a Fase 28 e a extensão proposta dos dados da CVM (seção 7).*

Este documento propõe uma ferramenta que, **mantendo as proporções ARCA da política**, procura entre os ativos disponíveis a composição que melhor atende a um objetivo de retorno: **valorização**, **dividendos** ou **misto**. A seção 8 ataca a própria proposta, porque otimizar carteira com histórico curto é um dos jeitos mais conhecidos de produzir um resultado que parece ótimo e falha no futuro.

## 1. Pergunta que a ferramenta responde

"Dentro de cada classe da minha política (Ações, Real Estate, Internacional e, opcionalmente, Caixa), quais ativos e em que pesos maximizariam o objetivo que escolhi, respeitando as metas e bandas ARCA, as minhas regras de elegibilidade e limites de concentração? Quanto melhor isso seria que a composição de hoje, que dividir igualmente e que o meu aporte pelo Cerrado, e com que confiança?"

A resposta é uma **proposta de composição para estudo**: pesos por ativo com intervalo, a melhora esperada com a probabilidade de ser real, e o caminho para chegar lá (só com aportes ou com vendas e IR). **Não é ordem de compra nem recomendação de investimento** (CVM). Nada altera a política sozinho: a única ação possível é o usuário, por conta própria, copiar a proposta para os pesos manuais de uma classe (decisão 9).

**O que muda em relação ao que já existe:**
- O aporte (`plan_contribution`) decide *para onde vai o próximo dinheiro* dentro da classe, pelo Cerrado, peso manual ou pesos iguais (`IntraClassStrategy`). Ele não procura a melhor composição.
- Os candidatos (33.7) medem o efeito de **um** ativo novo por vez. Esta fase escolhe o **conjunto** e os pesos.
- A simulação (33.4 e 33.5) testa regras e projeta a carteira. Esta fase usa as trajetórias dela para avaliar cada composição possível.

## 2. Escopo e restrições fixas

1. **Proporções ARCA:** a soma dos pesos de cada classe é a meta da política, dentro da banda. A otimização é **dentro de cada classe**, nunca entre classes: a alocação entre classes é decisão da política, não do otimizador.
2. **Universo** (decisão 3):
   - os ativos da carteira e da watchlist;
   - opcionalmente, o catálogo da B3 filtrado pelo screener (liquidez, tamanho, tipo e classe);
   - um teto por classe (proposta: 15 depois da pré-seleção), porque cada ativo a mais é uma comparação a mais (risco R16 da simulação).
3. **Elegibilidade:** os mesmos filtros do aporte real, para que a proposta nunca inclua o que o aporte recusaria:
   - checklist e elegibilidade da política, com respostas vencidas tratadas como na Fase 25;
   - sem dado suspeito (Fase 25), ou com a marca visível;
   - veredito de valuation;
   - volume mínimo;
   - pelo menos 36 meses de histórico mensal.
4. **Cerrado** (decisão 2), três modos:
   - **exigido:** só entram ativos com análise do Cerrado respondida e elegível;
   - **ponderado:** a nota do Cerrado entra como prior (seção 4.3) e como penalidade suave, e ativos sem análise entram com prior neutro e a marca "sem análise";
   - **ignorado:** só métricas e histórico.
5. **Concentração:** valores padrão alinhados à Saúde da carteira (Fase 29), editáveis:
   - peso máximo por ativo (proposta: 15% da carteira e 40% da classe);
   - número mínimo de ativos por classe (proposta: 4 em Ações, 4 em Real Estate, 2 em Internacional);
   - peso máximo por setor e por emissor.
6. **Operação real:** lotes inteiros na B3 (fracionário só no exterior), emolumentos e IR em vendas (isenção de R$ 20 mil por mês em ações, 20% em FIIs).
7. **Caixa** (decisão 4): fica fora da v1. A renda fixa já tem motor próprio (curvas, IR regressivo, comparador da Fase 24) e não se encaixa no modelo de retorno por fator; entra depois, como escolha entre títulos pelo comparador.

## 3. Objetivos

Todos os objetivos são avaliados **sobre as trajetórias futuras** da simulação (camadas B e D), nunca sobre a média histórica. Todos têm uma **restrição de risco** declarada: CVaR 95% de 12 meses da carteira não pior que o da composição atual ou que um limite informado (decisão 6).

| Objetivo | O que maximiza | Métricas que pesam na pré-seleção (4.1) |
|---|---|---|
| **Valorização** | Crescimento logarítmico esperado do **preço**, com os proventos fora; equivale ao critério de Kelly sobre o ganho de capital e já pune volatilidade | ROE e sua estabilidade, crescimento de lucro e receita, margens, margem de segurança do valuation (Graham, P/L, EV/EBITDA, P/VP), qualidade (Piotroski, Z'') |
| **Dividendos** | Renda passiva real esperada em N anos (DY normalizado da Fase 25 × valor projetado), menos uma penalidade pela chance de corte de proventos | DY normalizado (mediana de 3 a 5 anos), payout sustentável, consistência dos pagamentos, dívida/EBITDA, para FIIs o P/VP e o rendimento contra a NTN-B |
| **Misto** | Retorno total (preço + proventos reinvestidos) ou, em alternativa, a **chance de atingir a meta** de patrimônio e renda da aba Futuro (33.5) | União das duas listas, com os pesos λ (renda) e 1 − λ (valorização) declarados |

O misto tem duas formas (decisão 1): λ fixo entre renda e valorização, ou a chance de meta. A segunda é a mais coerente com a ferramenta, porque reaproveita as metas que o usuário já informa.

## 4. Método

### 4.1 Pré-seleção por métricas (filtro, não decisão)
- Em cada classe e setor, cada métrica é transformada em escore z robusto (mediana e MAD, com corte nos extremos), com o sinal do "melhor" de cada indicador, como no comparador da Fase 27.
- O escore do objetivo é a média ponderada das métricas da tabela acima, com pesos declarados e versionados.
- Os K melhores de cada classe seguem para a otimização. Os ativos que o usuário já tem entram sempre, para que a comparação com a carteira atual seja justa.
- A pré-seleção é **explicável**: cada ativo mostra as métricas que o colocaram na lista.

### 4.2 Modelo de retorno de cada ativo
Reaproveita a camada D (33.7), seção 5.2 do desenho da simulação:
- `r_ativo = α + β · r_classe + ε`, com as trajetórias de `r_classe` vindas da camada B, já com os cenários de juros e a mistura calibrada (33.6);
- α com prior hierárquico centrado em zero e fortemente encolhido, e β com prior centrado em 1;
- ε sorteado em blocos do próprio resíduo;
- evento de ruptura com a probabilidade da decisão 9 da simulação (zona do Z''-score);
- proventos: o DY normalizado com a sua variabilidade histórica, para separar valorização de renda.

### 4.3 Onde as métricas e o Cerrado entram no modelo
O histórico de preços sozinho é curto demais para separar bons de maus ativos (seção 8, P1). As métricas fundamentalistas entram de duas formas, sempre com peso declarado:
- **como prior do α:** um ativo com escore fundamentalista melhor recebe um prior de α levemente positivo (e o pior, levemente negativo), com intensidade calibrada no walk-forward (4.6). Se a calibração não achar relação entre o escore e o retorno seguinte, a intensidade vai a zero e o modelo diz isso;
- **como restrição:** dividendos exigem payout sustentável e ausência de corte recente; valorização exige margem de segurança mínima, se o usuário pedir.

No modo "ponderado", a nota do Cerrado entra como mais uma métrica do prior.

### 4.4 Otimização sobre cenários
- **Formulação:** maximizar a média do objetivo sobre S trajetórias (aproximação por média amostral), sujeito a:
  - soma de cada classe igual à meta;
  - limites de peso por ativo, setor e emissor;
  - CVaR 95% de 12 meses abaixo do limite, na formulação linear de Rockafellar e Uryasev (2000);
  - custo de transação e de IR quando o ponto de partida é a carteira atual (4.7).
- **Solver:** valorização (log) e dividendos são côncavos nos pesos, e o CVaR é linear. Proposta: `scipy.optimize` (HiGHS para a parte linear e SLSQP ou trust-constr para a côncava), uma dependência com wheels prontos para a imagem slim e sem compilador (decisão 8). A alternativa só com numpy é o gradiente projetado no simplex com o CVaR como penalidade.
- **Número mínimo de ativos:** a cardinalidade exata é combinatória. A proposta é resolver com a pré-seleção de K ativos e um peso mínimo por ativo escolhido, arredondar para lotes inteiros e checar de novo as restrições.

### 4.5 Robustez: reamostragem bayesiana
Um otimizador aplicado a estimativas com erro tende a escolher justamente os ativos cujo erro foi favorável. Michaud (1989) chamou os otimizadores de média-variância de "maximizadores de erro". A mitigação:
- **Reamostragem (Michaud, 1998, na versão bayesiana):** repetir a otimização para B sorteios dos parâmetros da posterior (33.6 e 33.7) e tirar a média dos pesos. O resultado é menos concentrado e mais estável.
- **Estabilidade:** para cada ativo, a fração dos sorteios em que ele entra e o intervalo de 90% do seu peso. Um ativo que entra em menos da metade dos sorteios aparece como "instável".
- **P(melhora):** a distribuição de (objetivo da proposta − objetivo da referência), com a probabilidade de ser positiva e o intervalo de credibilidade, como na 33.6.

### 4.6 Validação fora da amostra contra referências simples
DeMiguel, Garlappi e Uppal (2009) mostraram que dividir igualmente (1/N) é difícil de vencer fora da amostra com séries do tamanho que temos. Por isso a proposta só é apresentada como melhor se vencer as referências no passado, sem olhar o futuro:
- **Walk-forward:** em cada origem, otimizar só com os dados e as métricas disponíveis até ali (point-in-time, seção 7) e medir o objetivo nos 12 a 36 meses seguintes.
- **Referências:** pesos iguais na classe, a composição atual, o aporte pelo Cerrado (`plan_contribution`) e o índice da classe.
- **Portões (33.8):** Deflated Sharpe, PBO e a probabilidade a posteriori de superar a referência. Toda configuração testada (objetivo, K, limites, modo do Cerrado) entra na contagem de tentativas.
- **Resultado nulo é válido:** se o otimizador não vence o 1/N fora da amostra, a tela diz "não há evidência de que otimizar melhore a composição neste universo" e mostra a proposta apenas como exercício, com o selo.

### 4.7 Ponto de partida e plano de transição
Três modos (decisão 7):
- **carteira-alvo do zero:** a composição ótima, sem custo de chegar lá;
- **só com aportes:** a proposta vira um alvo, e o aporte mensal é direcionado aos ativos abaixo do peso proposto. A tela mostra em quantos meses a carteira chega perto do alvo, sem vender nada nem pagar IR;
- **com vendas:** inclui o IR e os custos de vender o que sai, pela regra real (isenção de R$ 20 mil por mês em ações, prejuízo não compensado no conservador), e mostra se a melhora esperada paga o custo da troca.

## 5. Saídas e tela

Nova aba **Composição** em Ferramentas › Simular carteira, com o guia de abas atualizado.

**Por classe**, uma tabela com uma linha por ativo:
- peso atual e peso proposto, com intervalo de 90%;
- frequência com que o ativo entra nos sorteios;
- métricas que o selecionaram;
- nota do Cerrado (ou "sem análise");
- marcas: dado suspeito, histórico curto, fato relevante recente (Fase 28);
- link para o detalhe do ativo, o checklist e o comparador.

**Na carteira inteira:**
- distribuição do objetivo da proposta contra a atual, os pesos iguais e o aporte pelo Cerrado, com P(melhora) e intervalo;
- CVaR, queda máxima, concentração (HHI e número efetivo) e renda passiva;
- o resultado do walk-forward contra as referências, com a contagem de tentativas e o selo "simulação, não recomendação".

**Plano de transição:** aportes sugeridos mês a mês até o alvo, ou as vendas com o IR estimado.

**API e MCP:** `POST /simulations/compositions` (roda no worker, como as demais simulações), `GET /simulations/{id}/composition`, e as operações `simulation.optimize` e `simulation.composition`.

## 6. Encaixe no código

- **Domínio:**
  - `domain/simulation/composition.py`: pré-seleção, escores e otimizador;
  - `domain/simulation/assets.py`: modelo de ativo da 33.7, reaproveitado;
  - `domain/simulation/validation.py`: a validação da 33.8, reaproveitada.
- **Execução:** novo tipo `COMPOSITION` em `simulation_runs`, com os parâmetros congelados no pedido (universo, objetivo, modo do Cerrado, limites, ponto de partida), mais o `data_hash` e o `ENGINE_VERSION`. Sem tabela nova.
- **Reaproveitamento:**
  - o screener (Fase 16), o checklist e a elegibilidade (Fases 10, 11 e 25), o valuation e o DY normalizado (Fase 25), o comparador (Fase 27);
  - as métricas de concentração e risco (Fase 29);
  - o IR das vendas (Fase 24 e 33.2);
  - as trajetórias e a camada bayesiana (33.5 a 33.7).

## 7. Insumos da CVM

A Fase 28 traz os fatos relevantes (IPE). Para esta proposta, os dados abertos da CVM valem mais por outro motivo: dão **histórico point-in-time** dos fundamentos, que hoje é o elo mais fraco (risco R1 da simulação: só se sabe quando um demonstrativo foi gravado aqui, não quando foi publicado).

| Insumo (dados abertos da CVM) | Uso nesta fase | Situação |
|---|---|---|
| IPE: fatos relevantes e comunicados | Marca de evento recente (emissão, recompra, reestruturação, mudança de controle); exclusão opcional na janela do evento | Fase 28 |
| Cadastro de companhias (com situação e data de cancelamento) | Universo histórico com as empresas que saíram da bolsa: reduz o viés de sobrevivência (R2) no walk-forward | Fase 28.1 (mapa ticker → CNPJ); estender para guardar o cancelamento |
| DFP e ITR (balanço, DRE e DFC, com data de entrega) | Fundamentos históricos com a data em que foram conhecidos: escores point-in-time para o walk-forward, Piotroski e Z'' calculáveis (hoje em "dados insuficientes" na Fase 29), payout e dívida históricos | Proposta de extensão (28.x) |
| Informe mensal de FII | Rendimento distribuído, patrimônio e cotistas por mês: o objetivo Dividendos para FIIs, que a Fase 28 deixa de fora (28.5) | A confirmar no portal; extensão futura |

**Ordem sugerida:**
1. Fase 28 (fatos relevantes e o mapa ticker → CNPJ).
2. Extensão 28.x (DFP e ITR point-in-time, informe de FII).
3. Fase 34, cujas etapas 34.1 e 34.2 podem começar antes, com os dados de hoje e a marca de que os escores não são point-in-time.

## 8. Teste de estresse da proposta

| # | Risco | Como quebra | Mitigação na proposta | Risco residual |
|---|---|---|---|---|
| P1 | **Maximização do erro** | O otimizador escolhe os ativos com o erro de estimativa mais favorável e concentra nos "melhores" do passado | α encolhido (4.2); reamostragem bayesiana com a média dos pesos (4.5); limites de concentração; walk-forward contra o 1/N (4.6) | Médio: é o risco central; a tela mostra a estabilidade de cada peso |
| P2 | **Overfitting de configuração** | Testar objetivos, K, limites e modos até achar o que "funciona" | Contagem de tentativas, Deflated Sharpe e PBO (33.8); janela reservada dos últimos 3 anos | Médio: depende de respeitar a janela |
| P3 | **Maldição do vencedor** | Com 200 ativos, os 10 melhores são os mais sortudos | Teto K por classe; prior hierárquico; P(melhora) com intervalo; ativos atuais sempre na comparação | Médio |
| P4 | **Look-ahead nos fundamentos** | Usar o ROE de 2023 para escolher em 2022 | Escores point-in-time pela data de entrega (seção 7); até lá, disponibilidade em exercício + 90 dias e o selo "não point-in-time" | Alto até a extensão da CVM |
| P5 | **Viés de sobrevivência** | O catálogo só tem quem sobreviveu, e o passado parece melhor | Cadastro da CVM com cancelamentos (seção 7); evento de ruptura; universo padrão só com carteira e watchlist | Médio |
| P6 | **Armadilha de dividendos** | DY alto porque o preço caiu ou porque houve um provento extraordinário | DY normalizado (mediana de 3 a 5 anos, marca de extraordinário da Fase 25); payout sustentável; chance de corte no objetivo | Baixo a médio |
| P7 | **Dado ruim** | Indicador fora de escala promove um ativo | Exclusão por dado suspeito (Fase 25) ou marca visível; escores robustos (mediana, MAD, corte nos extremos) | Baixo |
| P8 | **Custos de trocar** | A proposta só vence sem IR e corretagem | Modo "com vendas" com o IR real; modo "só com aportes" sem venda; comparação sempre líquida | Baixo |
| P9 | **Liquidez e lotes** | Peso de 0,7% num FII com R$ 50 mil de volume diário | Volume mínimo; lotes inteiros; peso mínimo por ativo escolhido | Baixo |
| P10 | **Concentração escondida** | Cinco ativos do mesmo setor ou do mesmo grupo econômico | Limites por setor e emissor; correlação na covariância dos resíduos; métricas da Fase 29 na saída | Baixo |
| P11 | **Prior fundamentalista arbitrário** | As métricas "boas" não predizem retorno neste mercado | Intensidade do prior calibrada no walk-forward e levada a zero quando não há relação (4.3), sempre visível | Médio |
| P12 | **Interpretação como recomendação** | "Comprar estes 8 ativos" | Nome "proposta para estudo"; selo; nenhum botão de compra; aplicar como peso manual só por ação explícita do usuário (decisão 9) | Médio: é comportamental |
| P13 | **Custo computacional** | B sorteios × S trajetórias × walk-forward | Pré-seleção K; trajetórias da camada B reaproveitadas; solver convexo; execução no worker com limite de tempo | Baixo |

## 9. Entregas em etapas (Fase 34)

| Etapa | Entrega | Critério de aceite |
|---|---|---|
| 34.0 | Decisões da seção 10 tomadas e esta proposta aprovada | Revisão do usuário |
| 34.1 | Universo e filtros (elegibilidade, Cerrado em três modos, dado suspeito, liquidez, histórico) | Ninguém que o aporte real recusaria entra |
| 34.2 | Escores por objetivo (z robusto por classe e setor, pesos versionados, explicação por ativo) | Testes com métricas sintéticas; ativo com dado suspeito fora |
| 34.3 | Modelo de retorno de ativo (depende da 33.7) com proventos separados da valorização | Ativo de ruído não ganha α relevante |
| 34.4 | Otimizador sobre cenários com metas ARCA, limites e CVaR; lotes inteiros | Verdades conhecidas: ativos iguais dão pesos iguais; sem risco, vale o maior retorno dentro dos limites |
| 34.5 | Reamostragem bayesiana, estabilidade e P(melhora) | Com ruído puro, os pesos médios ficam perto do 1/N e a P(melhora) perto de 50% |
| 34.6 | Walk-forward contra o 1/N, a carteira atual e o Cerrado, com os portões da 33.8 | Teste com ruído dá o resultado nulo; tentativas contadas |
| 34.7 | Plano de transição (só aportes e com vendas e IR) | IR das vendas conferido à mão |
| 34.8 | Aba Composição, MCP e guia de abas atualizado | Testes de UI e integração; `docker compose build` |
| 34.9 | Insumos da CVM point-in-time (depois da Fase 28 e da extensão 28.x) | Escores do walk-forward sem look-ahead (teste com o demonstrativo publicado depois da origem) |

## 10. Decisões que precisam ser tomadas antes de implementar

1. **Misto:** λ fixo entre renda e valorização (qual valor padrão?) ou a chance de meta da aba Futuro (recomendado)?
2. **Cerrado:** modo padrão exigido, ponderado (recomendado) ou ignorado?
3. **Universo:** só carteira e watchlist (recomendado na v1, menos viés) ou também o catálogo filtrado? Qual K por classe (proposta: 15)?
4. **Caixa:** fora na v1 (recomendado) ou já com a escolha entre títulos?
5. **Limites de concentração padrão:** 15% da carteira e 40% da classe por ativo, mínimo de 4/4/2 ativos por classe, limite por setor? Ou os limites da Saúde da carteira?
6. **Restrição de risco:** CVaR de 12 meses não pior que o da carteira atual (recomendado) ou um limite fixo?
7. **Ponto de partida padrão:** só com aportes (recomendado: sem IR e sem venda), carteira-alvo do zero ou com vendas?
8. **Dependência:** aceitar o `scipy` na imagem do backend (recomendado; wheels prontos) ou ficar só com numpy (gradiente projetado, CVaR como penalidade)?
9. **Aplicação:** a proposta é só leitura, ou o usuário pode copiá-la, com confirmação explícita, para os pesos manuais (`MANUAL_WEIGHT`) de uma classe na política (nova versão, como toda mudança de política)?
10. **Ordem:** esperar a Fase 28 e a extensão da CVM, ou começar pelas etapas 34.1 e 34.2 com o selo "não point-in-time"?

## 11. Referências

- Markowitz, H. (1952). Portfolio Selection. *Journal of Finance* 7(1), 77–91.
- Michaud, R. (1989). The Markowitz Optimization Enigma: Is "Optimized" Optimal? *Financial Analysts Journal* 45(1), 31–42.
- Michaud, R. (1998). *Efficient Asset Management: A Practical Guide to Stock Portfolio Optimization and Asset Allocation*. Harvard Business School Press.
- DeMiguel, V.; Garlappi, L.; Uppal, R. (2009). Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy? *Review of Financial Studies* 22(5), 1915–1953.
- Rockafellar, R. T.; Uryasev, S. (2000). Optimization of Conditional Value-at-Risk. *Journal of Risk* 2(3), 21–41.
- Kelly, J. L. (1956). A New Interpretation of Information Rate. *Bell System Technical Journal* 35(4), 917–926.
- Piotroski, J. (2000). Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers. *Journal of Accounting Research* 38, 1–41.
- Jorion, P. (1986). Bayes-Stein Estimation for Portfolio Analysis. *JFQA* 21(3), 279–292 (já usado na 33.6).
- Portal de dados abertos da CVM: https://dados.cvm.gov.br (IPE, cadastro, DFP/ITR; informe mensal de FII a confirmar).
- Desenho da simulação: [PORTFOLIO_SIMULATION_DESIGN.md](PORTFOLIO_SIMULATION_DESIGN.md) (camadas B e D, seções 5 e 6, riscos R1 a R21).
