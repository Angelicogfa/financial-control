# Hierarquia de Recomendação: Inventário e Reestruturação

> Proposta para revisão (2026-10-30; revisada no mesmo dia com o Cerrado como peso, o AHP e a diversificação por setor). Nenhuma linha de código. As fases novas estão pausadas até esta hierarquia ser aprovada.

## 1. A pergunta

O motor de recomendação deve responder, de forma analítica e auditável:

> "Com o dinheiro deste mês, dentro da política, quais ativos comprar e quanto de cada, e por quê?"

Para isso, cada decisão precisa ser rastreável até três coisas:

- os dados do ativo;
- as análises do passado;
- as projeções do futuro.

A resposta tem de vir de uma cadeia única de decisões, em que cada etapa recebe a saída da anterior e deixa registrado o que decidiu.

## 2. Inventário: o que já existe

O sistema já tem muitas peças analíticas. O problema não é falta de análise. É que as peças não estão ligadas ao aporte.

| # | Mecanismo | Onde | O que produz | Escala | Entra no aporte hoje? |
|---|---|---|---|---|---|
| M1 | Política e alvos ARCA, com bandas | `policy/services/policy.py`, `allocation.py` | % alvo por classe, faixa de tolerância | % | **Sim**: nível 1 |
| M2 | Distribuição por déficit, sem venda | `allocation.distribute_with_bands`, `distribute_by_targets` | R$ por classe e por ativo | R$ | **Sim**: níveis 1 e 2 |
| M3 | Ciclo de vida (WATCHLIST → ELIGIBLE → HELD → REVIEW → ARCHIVED) | `policy/services/lifecycle.py` | quem pode receber aporte | binário | **Sim**: filtro |
| M4 | Checklist do Cerrado (66 perguntas, perfis, validade das respostas) | `assets/services/cerrado.py`, `questions.py` | nota = SIM − NÃO, cobertura, recomendação APTO/REVISAR | contagem inteira | **Sim**: elegibilidade (nota e cobertura mínimas) e peso dentro da classe |
| M5 | Estratégia dentro da classe: Cerrado, manual ou igual | `cerrado.resolve_intra_class_weights` | peso-alvo de cada ativo | fração | **Sim**: o único critério de escolha entre ativos |
| M6 | Valuation por perfil (Graham, Bazin, P/L, EV/EBITDA, P/VP justificado, FII × NTN-B) | `assets/services/valuation.py` | preço justo, margem de segurança, veredito DESCONTADO/JUSTO/CARO | enum + R$ | **Não**. Só alerta de "abaixo do teto" e filtro dos candidatos da simulação |
| M7 | Leitura dos indicadores ("bom ou não", com as referências da política) | `assets/services/ratings.py` | BOM/ATENÇÃO/RUIM/SUSPEITO por indicador | enum | **Não**: só exibição |
| M8 | Piotroski F e Altman Z'' | `assets/services/scores.py` | qualidade contábil, zona de risco | 0–9, contínuo | **Não**: só na Saúde |
| M9 | Saúde da carteira (7 pilares: política, concentração, diversificação, risco, desempenho, qualidade, liquidez) | `portfolio/services/health.py` | ok/atenção/crítico por verificação | enum | **Não**: diagnóstico |
| M10 | Métricas de risco (volatilidade, drawdown, β, correlação) | `portfolio/services/risk_metrics.py`, `diversification.py` | números da carteira | contínuo | **Não** |
| M11 | Pesquisa (screener) e Comparador (melhor valor por linha) | `research/services/screener.py`, `comparison.py` | filtros e "melhor da linha" | filtros | **Não**: ferramenta manual |
| M12 | Simulação: backtest, projeção, robustez, Laboratório (walk-forward purgado, Sharpe deflacionado, PBO, portão bayesiano) | `simulation/*` | trajetórias, selos de confiança, validação | probabilidades | **Não**: estuda as regras, não decide o aporte |
| M13 | Candidatos (33.7): α/β bayesiano frente à classe, efeito marginal na carteira com P(melhora) | `simulation/candidates.py` | lista "a investigar" | Δ patrimônio, P | **Não**: capítulo 3 dos estudos |
| M14 | Previsão de preço (42): camada A (mercado/classe), B (valuation PIT da CVM, com portão) e C (eventos, com portão) | `forecast/*` | faixa de preço, P(subir), P(cair 20%), "o que pesou" | probabilidades | **Não** |
| M15 | Garimpo (43): sinais VALOR, QUALIDADE, MELHORA e MOMENTUM, pesos por Fama-MacBeth, portão CSCV, placar | `mining/*` | 10 achados por semana | escore z | **Não**: vira watchlist se você seguir |
| M16 | Alertas | `alerts/services/evaluator.py` | avisos acionáveis | evento | **Não** |

**Como o aporte decide hoje** (`consolidation.plan_contribution`):

1. Divide o valor entre as classes ARCA (M1 + M2), primeiro as classes abaixo da banda.
2. Dentro da classe, considera só os ativos já cadastrados, com lançamentos válidos, finalidade ARCA e situação ELIGIBLE ou HELD (M3, que depende de M4).
3. Dá a cada ativo um peso-alvo pela estratégia da classe (M5). No Cerrado, o peso é proporcional à nota SIM − NÃO; um ativo sem Cerrado recebe a média dos outros.
4. O dinheiro vai para quem está mais abaixo do peso-alvo (M2). As sobras dos lotes inteiros vão para a classe mais abaixo do alvo.

Ou seja, "A é melhor que B" significa hoje apenas que A tem mais respostas SIM líquidas no checklist, ou que você deu a A um peso manual maior. M6 a M15 não participam.

## 3. Diagnóstico: por que reestruturar

1. **Peças soltas.** Dez mecanismos analíticos produzem opiniões sobre os ativos e nenhum chega ao aporte. Cada tela tem a sua verdade, e elas podem se contradizer: o checklist aprova, o valuation diz "caro", a previsão dá 70% de chance de cair, e o aporte compra.
2. **O único critério de escolha não é quantitativo.**
   - A nota do Cerrado é uma contagem de respostas, todas com o mesmo peso. Uma pergunta sobre governança vale o mesmo que uma sobre dívida.
   - Respostas manuais não têm data no passado. Por isso não dá para testar se a nota previu algo; é o achado do backtest "100% em Caixa".
3. **Escalas incompatíveis.** Contagem inteira, enum (DESCONTADO/CARO), BOM/RUIM, z-score, probabilidade, R$. Sem uma escala comum, não há como combinar.
4. **O mesmo sinal calculado duas vezes.** O z de valuation aparece na camada B da previsão e no sinal VALOR do Garimpo; o veredito de valuation filtra candidatos, mas não o aporte. Combinar sem um registro único conta duas vezes a mesma evidência.
5. **Sem validação do todo.** Mecanismos isolados têm portões fora da amostra (B, C, Garimpo), mas a regra que de fato gasta o seu dinheiro nunca foi comparada com referências simples: pesos iguais, só o Cerrado, o índice.
6. **Trilha de auditoria só da regra, não das evidências.**
   - Desde a Fase 44 (justificativa do aporte), o plano guarda a regra que decidiu cada valor: banda, déficit, divisão interna e o motivo de cada ativo.
   - Não guarda as evidências, porque o aporte não usa nenhuma. Não dá para responder, meses depois, "por que A e não B em março" com os dados que existiam em março.
   - O registro de decisão da Fase 45 estende essa justificativa com as lentes, os portões e a nota.
7. **Sem retorno.** Só o Garimpo tem placar. As recomendações do aporte não são medidas depois.
8. **Universo estreito.** O aporte só olha os ativos já cadastrados e elegíveis. Os melhores candidatos (M13, M15) ficam em outras telas.

## 4. A hierarquia proposta

Um funil de sete níveis. Cada nível:

- tem **uma** responsabilidade;
- recebe a saída do anterior;
- grava a sua decisão com o motivo.

Nada pula nível, e nenhum nível refaz o trabalho de outro.

```
N0  Política e objetivo            (o que você quer: alvos ARCA, objetivo por classe, limites)
 │
N1  Alocação entre classes ARCA    (quanto vai para cada classe: regra da política, sem previsão)
 │
N2  Universo da classe             (de onde podem sair os ativos: carteira + watchlist + catálogo)
 │
N3  Portões eliminatórios          (só o objetivo e grave: dado errado, liquidez, ruína)
 │
N4  Evidências por lente           (Cerrado com penalidade + lentes medidas: escores comparáveis)
 │
N5  Combinação em retorno esperado (AHP: pesos por comparação par a par, matriz de decisão)
 │
N6  Construção dos pesos           (quanto de cada um: tetos por ativo, setor e grupo)
 │
N7  Execução do aporte             (o dinheiro deste mês, por déficit, sem venda, lotes)
 │
 └─ Registro, explicação e placar  (atravessa todos os níveis)
```

### N0 — Política e objetivo (existe: M1; amplia)

A política versionada passa a declarar também:

- o **objetivo de cada classe**: valorização, dividendos ou misto, como na Fase 34;
- os **limites**: peso máximo por ativo, por setor e por emissor; CVaR máximo da classe;
- a **lista de lentes ativas e os seus pesos**, quando declarados (ver N5).

Mudar qualquer item cria uma versão nova, como hoje.

### N1 — Alocação entre classes (existe: M1 + M2; mantém)

Fica como está: alvos ARCA, bandas e déficit. A recomendação **não** muda a proporção entre classes por causa de previsões. Esse é o papel da política, e um ajuste tático aqui seria exatamente o tipo de aposta que a ferramenta deve evitar sem evidência forte. (Decisão 10.1.)

### N2 — Universo da classe (parcial; amplia)

Hoje o universo são os ativos cadastrados e elegíveis. Na proposta, ele se divide em três camadas, sempre marcadas:

- **Carteira:** já tem posição.
- **Watchlist:** você cadastrou ou seguiu um achado do Garimpo.
- **Catálogo filtrado:** o universo líquido do Garimpo, com balanço na CVM.

As três camadas concorrem no aporte em pé de igualdade (decisão 10.4). Um ativo do catálogo:

- passa pelos mesmos portões;
- quase sempre chega sem análise do Cerrado, com L0 = 0 e o destaque correspondente;
- se for sugerido, aparece no plano marcado como **"novo, fora da carteira e da watchlist"**;
- é cadastrado automaticamente (na watchlist) quando o plano é confirmado.

O custo de olhar o catálogo inteiro fica no worker: a tela lê o resultado gravado.

### N3 — Portões eliminatórios (existe espalhado: M3, M4, M6, M7, M8; consolida)

São regras binárias, cada uma com o motivo gravado. Não dão nota. Eliminam.

| Portão | Fonte | Elimina quando |
|---|---|---|
| Lançamentos válidos e finalidade ARCA | M3 | inconsistência no extrato, ativo fora da ARCA |
| Dado confiável | M7 (SUSPEITO), qualidade do provedor | indicador fora da faixa plausível ou divergente |
| Liquidez | catálogo, Garimpo | volume médio abaixo do piso da política |
| Histórico mínimo | simulação, previsão | menos de N meses de preço, para as lentes que precisam |
| Risco de ruína | M8 (Altman em zona de estresse), eventos (recuperação judicial) | sinal de insolvência |
| Situação de revisão | M3 | ativo em REVIEW: não recebe até ser revisto |

O Cerrado **não é portão**. Filtrar por ele impediria descobrir um ativo que ainda não foi analisado. Ele entra como peso, na lente L0 de N4. Um ativo sem análise é penalizado a ponto de favorecer os analisados, mas continua concorrendo. Se ficar bem colocado mesmo com a penalidade, recebe o aviso "analise o Cerrado". Depois de analisado, a rodada seguinte o reclassifica: ele sobe, cai ou sai da lista pela própria nota. (Decisão 10.2.)

Os portões ficam só para o que é **objetivo e grave**: dado errado, falta de liquidez, falta de histórico, risco de ruína, extrato inconsistente.

### N4 — Evidências por lente (existe: M4, M6, M8, M10, M14, M15; padroniza)

Cada lente responde a uma pergunta e devolve, para cada ativo:

- **escore padronizado**: z robusto dentro da classe e do setor, limitado a ±3;
- **confiança** do escore: dados disponíveis, idade do balanço;
- **explicação** em uma frase;
- **histórico point-in-time**, para o escore poder ser testado no passado.

| Lente | Pergunta | Insumos que já existem |
|---|---|---|
| L0 Cerrado | O que a sua análise qualitativa diz? | nota do checklist em escala de 0 a 10 e cobertura (M4) |
| L1 Qualidade | A empresa é boa e estável? | ROE, margem, alavancagem, estabilidade (sinal QUALIDADE do Garimpo), Piotroski, perguntas automáticas do Cerrado |
| L2 Valuation | Está barata frente ao próprio passado, ao setor e ao preço justo? | z de valuation PIT (42.3), margem de segurança Graham/Bazin/P/VP justificado (M6) |
| L3 Melhora | Os fundamentos estão melhorando? | sinal MELHORA do Garimpo |
| L4 Momentum | O mercado está confirmando? | sinal MOMENTUM do Garimpo |
| L5 Renda | Paga e vai continuar pagando? | DY normalizado, regularidade, payout (M6, M7) |
| L6 Risco | Quanto pode doer? | volatilidade, β, drawdown, P(cair 20%) e CVaR da previsão (M10, M14) |
| L7 Projeção | O que o modelo espera dos próximos 12 meses? | retorno esperado e P(bater o CDI) da previsão, camadas A e C, sem a B (M14) |
| L8 Diversificação | Melhora a carteira como um todo? | correlação com a carteira, efeito marginal dos candidatos (M13) |

**Como a L0 (Cerrado) trata quem não foi analisado** (decidido em 2026-10-30). A nota fica em uma escala absoluta de **0 a 10**, igual para todos os ativos. Ela não é comparada com os outros ativos, então não muda quando a lista muda.

- Nota cheia: (SIM − NÃO) / aplicáveis vai de [−1, 1] para [0, 10], ou seja, **5 × (normalizada + 1)**.
- Na matriz de decisão, entra dividida por 10.

| Situação | Nota da L0 (0 a 10) | Destaque na tela |
|---|---|---|
| Analisado, respostas em dia | a nota cheia | — |
| Analisado em parte | nota cheia × cobertura (o que falta conta como 0) | "complete a análise: a nota pode subir" |
| Respostas vencidas | a parte vencida perde valor de forma linear até 0 em 12 meses após o vencimento | "reveja o Cerrado: a nota pode mudar" |
| **Sem análise** | **0** | **"Faça a análise do Cerrado: a nota deste ativo pode melhorar e ele pode ser reclassificado"**, com a posição que teria se a L0 fosse 5 (neutra) e se fosse 10 |
| Cerrado desativado para o ativo | a lente sai e os pesos das outras são reescalados | "sem Cerrado por opção" |

Um ativo sem análise **pode receber aporte**. A nota 0 só o deixa passar quando os outros sinais são fortes, e o destaque aparece no plano de aporte, na matriz e na página do ativo.

Uma nota muito baixa do Cerrado pesa contra o ativo, mas não o elimina. Os casos graves de verdade (insolvência, recuperação judicial) já são portões de N3.

**Regra contra a dupla contagem.** Cada sinal mora em **uma** lente. A previsão da Fase 42 tem três camadas:

- **A:** mercado, classe e o desempenho próprio do ativo;
- **B:** valuation dos balanços da CVM, que puxa o retorno esperado de ações baratas para cima e o de caras para baixo;
- **C:** eventos recentes.

O valuation já é a lente L2. Se a L7 usasse a previsão completa, um ativo barato ganharia pontos duas vezes pelo mesmo motivo. Por isso a L7 usa **as camadas A e C, sem a B**, e o valuation fica inteiro na L2 (decisão 10.5). Os eventos não aparecem em nenhuma outra lente, então ficam na L7. Todos os sinais saem de um **registro único point-in-time**, o mesmo para Garimpo, previsão e aporte: hoje cada um monta o seu painel.

### N5 — Combinação (não existe; novo)

As lentes viram uma nota final. A estrutura é a do **AHP** (Analytic Hierarchy Process):

- objetivo da classe;
- critérios, que são as lentes;
- subcritérios, que são os sinais de cada lente;
- alternativas, que são os ativos que passaram por N3.

O peso global de um sinal é o peso da lente vezes o peso do sinal dentro dela.

Os pesos se definem de duas formas, usadas em sequência:

1. **Pesos declarados por objetivo, pelo AHP clássico.**
   - Você compara as lentes de duas em duas, na escala de Saaty de 1 a 9 ("Qualidade é moderadamente mais importante que Momentum"). Depois faz o mesmo com os sinais dentro de cada lente.
   - O autovetor principal de cada matriz dá os pesos. A **razão de consistência** (CR) mede a coerência dos julgamentos: acima de 0,10, a tela aponta os pares que mais se contradizem e pede revisão.
   - As matrizes, os pesos e o CR ficam versionados na política.
   - A política já vem com as **matrizes pré-configuradas** de cada objetivo (abaixo). Você pode editá-las; a edição cria uma versão nova da política.
   - Os **ativos não são comparados de dois em dois.** Eles entram pelos valores medidos das lentes: o julgamento fica só onde não há dado, que é a importância de cada critério.
2. **Pesos validados pelos dados.** Como no Garimpo: regressão do retorno dos 12 meses seguintes, frente à classe, sobre as lentes (Fama-MacBeth), com prior cético centrado nos pesos declarados. O peso estimado só substitui o declarado se passar no portão fora da amostra, depois de custos, contado o número de tentativas. Senão, a tela diz: "os dados não justificaram mudar os seus pesos".

**Matrizes pré-configuradas** (decidido em 2026-10-30). Os julgamentos seguem a lógica de cada objetivo:

- **Valorização:** qualidade, valuation e melhora puxam o resultado, e o Cerrado tem o mesmo peso deles; renda quase não conta.
- **Dividendos:** renda domina; qualidade, valuation e risco a sustentam, porque dividendo de empresa ruim ou cara não se mantém; momentum quase não conta.
- **Misto:** qualidade à frente, depois valuation; Cerrado e renda empatados.

A projeção (L7, camadas A e C) tem peso baixo em todos: ela mostra o que se espera, mas é a lente mais incerta. A diversificação (L8) não entra na nota, porque já está nas regras de setor e grupo de N6.

Cada célula diz quanto a lente da linha é mais importante que a da coluna (escala de Saaty: 1 igual, 3 moderado, 5 forte, 7 muito forte, 9 extremo).

*Valorização* (CR = 0,008):

| | L0 | L1 | L2 | L3 | L4 | L5 | L6 | L7 | Peso |
|---|---|---|---|---|---|---|---|---|---|
| **L0 Cerrado** | 1 | 1 | 1 | 1 | 2 | 5 | 1 | 2 | **16,0%** |
| **L1 Qualidade** | 1 | 1 | 1 | 1 | 2 | 7 | 2 | 2 | **18,1%** |
| **L2 Valuation** | 1 | 1 | 1 | 1 | 2 | 7 | 2 | 2 | **18,1%** |
| **L3 Melhora** | 1 | 1 | 1 | 1 | 2 | 5 | 1 | 2 | **16,0%** |
| **L4 Momentum** | 1/2 | 1/2 | 1/2 | 1/2 | 1 | 3 | 1 | 1 | **8,9%** |
| **L5 Renda** | 1/5 | 1/7 | 1/7 | 1/5 | 1/3 | 1 | 1/4 | 1/3 | **2,9%** |
| **L6 Risco** | 1 | 1/2 | 1/2 | 1 | 1 | 4 | 1 | 1 | **11,2%** |
| **L7 Projeção** | 1/2 | 1/2 | 1/2 | 1/2 | 1 | 3 | 1 | 1 | **8,9%** |

*Dividendos* (CR = 0,003):

| | L0 | L1 | L2 | L3 | L4 | L5 | L6 | L7 | Peso |
|---|---|---|---|---|---|---|---|---|---|
| **L0 Cerrado** | 1 | 1 | 1 | 2 | 5 | 1/2 | 1 | 2 | **13,8%** |
| **L1 Qualidade** | 1 | 1 | 1 | 3 | 6 | 1/2 | 1 | 3 | **15,7%** |
| **L2 Valuation** | 1 | 1 | 1 | 2 | 5 | 1/2 | 1 | 2 | **13,8%** |
| **L3 Melhora** | 1/2 | 1/3 | 1/2 | 1 | 2 | 1/4 | 1/2 | 1 | **6,4%** |
| **L4 Momentum** | 1/5 | 1/6 | 1/5 | 1/2 | 1 | 1/9 | 1/5 | 1/2 | **2,9%** |
| **L5 Renda** | 2 | 2 | 2 | 4 | 9 | 1 | 2 | 4 | **27,2%** |
| **L6 Risco** | 1 | 1 | 1 | 2 | 5 | 1/2 | 1 | 2 | **13,8%** |
| **L7 Projeção** | 1/2 | 1/3 | 1/2 | 1 | 2 | 1/4 | 1/2 | 1 | **6,4%** |

*Misto* (CR = 0,011):

| | L0 | L1 | L2 | L3 | L4 | L5 | L6 | L7 | Peso |
|---|---|---|---|---|---|---|---|---|---|
| **L0 Cerrado** | 1 | 1/2 | 1 | 2 | 2 | 1 | 1 | 2 | **13,4%** |
| **L1 Qualidade** | 2 | 1 | 1 | 3 | 4 | 2 | 2 | 4 | **23,6%** |
| **L2 Valuation** | 1 | 1 | 1 | 2 | 3 | 1 | 2 | 3 | **17,7%** |
| **L3 Melhora** | 1/2 | 1/3 | 1/2 | 1 | 2 | 1/2 | 1 | 2 | **9,1%** |
| **L4 Momentum** | 1/2 | 1/4 | 1/3 | 1/2 | 1 | 1/2 | 1/2 | 1 | **5,8%** |
| **L5 Renda** | 1 | 1/2 | 1 | 2 | 2 | 1 | 1 | 2 | **13,4%** |
| **L6 Risco** | 1 | 1/2 | 1/2 | 1 | 2 | 1 | 1 | 2 | **11,2%** |
| **L7 Projeção** | 1/2 | 1/4 | 1/3 | 1/2 | 1 | 1/2 | 1/2 | 1 | **5,8%** |

Dentro de cada lente, os sinais começam com pesos iguais (matriz toda de 1), editáveis da mesma forma.

**Normalização.** Cada sinal é normalizado contra o **universo inteiro da classe e do setor**, e não só contra os ativos do mês. O motivo: a normalização do AHP pela soma das alternativas muda a ordem quando um ativo entra ou sai da lista (inversão de ordem). Usamos z robusto limitado a ±3, transformado para [0, 1] para a leitura da matriz.

**Matriz de decisão.** Esta é a forma de ler e auditar o processo:

- linhas = ativos;
- colunas = lentes, com o peso no cabeçalho;
- cada célula mostra o valor normalizado e a contribuição para a nota (valor × peso);
- a última coluna é a nota final.

"A e não B" é a diferença das duas linhas, célula a célula, ordenada pelo que mais pesou. A tela abre cada lente para mostrar os sinais dela.

**AHP Gaussiano, só como referência.** Nele, o peso de cada critério vem da dispersão dos ativos (desvio dividido pela média). Ele mostra o critério que mais **diferencia** os ativos, não o que mais **acerta** o retorno. Além disso, é instável com escores de média perto de zero e muda os pesos a cada lista. Por isso aparece só como um ranking alternativo na tela ("se os pesos viessem só da dispersão"), para comparação, e não decide.

A nota final é convertida em **retorno esperado acima da classe**, em % ao ano, com intervalo. É a moeda comum de que N6 precisa, e é o que o usuário entende.

### N6 — Construção dos pesos (desenhado na Fase 34; reaproveita)

Entre os aprovados em N3, ordenados por N5, os pesos-alvo da classe saem de:

- **forma simples, para começar:** os K melhores, peso proporcional ao retorno esperado positivo e limitado pelos tetos de ativo, setor e emissor da política. O **K é dinâmico** (decisão 10.6):
  - os ativos entram um a um, na ordem da seleção que alterna setores;
  - cada novo ativo só entra se o **ganho de diversificação** compensar a **perda de nota**;
  - a conta usa a utilidade da classe U = retorno esperado − λ × risco. O risco é a volatilidade (ou o CVaR) da classe, calculada com as correlações dos retornos. λ é a aversão a risco declarada na política;
  - um ativo pouco correlacionado com os já escolhidos reduz o risco o bastante para valer a nota um pouco menor. Um ativo que anda junto com os outros não reduz, e a seleção para;
  - **limites práticos:** K mínimo (por exemplo, 3, para nunca concentrar em um ou dois nomes), K máximo (por exemplo, 12) e **lote mínimo de aporte** por ativo. Um aporte pequeno não se pulveriza em lotes que não valem a corretagem e o acompanhamento;
  - a tela mostra a curva de cada classe: com K = 3, 4, 5 e assim por diante, quanto a nota caiu e o risco diminuiu, e onde a seleção parou e por quê;
- **forma completa, a Fase 34:** otimização sobre os cenários da simulação, com restrição de CVaR, lotes inteiros e reamostragem bayesiana para a estabilidade.

Em ambas, o resultado é **puxado para o peso atual** (encolhimento), para não girar a carteira por diferenças pequenas e incertas. A força do puxão depende da confiança da nota. (Decisão 10.6.)

**Diversificação por setor.** O setor não torna uma ação melhor ou pior, então não entra na nota. Ele decide como as ações se combinam, e por isso é uma regra de construção, declarada na política:

- **Dois níveis de agrupamento:**
  - o **setor da B3** (setor econômico e subsetor, já no catálogo), para os tetos e para a tela;
  - **grupos por correlação dos retornos**, calculados dos históricos guardados. Setores com rótulos diferentes podem andar juntos: infra, saneamento e energia são regulados e sensíveis a juros. O mesmo vale para os FIIs: tijolo, papel, logística, shopping e lajes.
- **Tetos:** peso máximo por setor e por grupo (por exemplo, 25% da classe) e no máximo K ações por setor.
- **Seleção que alterna setores.**
  - Escolhe a melhor nota; a próxima é a melhor de um setor ainda não coberto.
  - Uma ação de setor já coberto só passa à frente se a diferença de nota for maior que a margem declarada (por exemplo, 0,5 desvio).
  - Tudo isso dentro dos tetos.
- **Registro e tela:**
  - o número efetivo de setores e de grupos da classe, antes e depois do aporte;
  - o motivo de cada ação pulada: "Tecnologia já está no teto" ou "mesmo grupo de Saneamento, nota só 0,2 maior".

As lentes de N4 já comparam cada indicador dentro do setor. Por isso a nota não favorece sempre os bancos (P/L baixo) ou as elétricas (DY alto). E a L8 mede a correlação com a carteira, que completa os tetos.

### N7 — Execução do aporte (existe: M2; mantém)

Igual a hoje: o dinheiro vai para quem está mais abaixo do novo peso-alvo, sem venda, em lotes inteiros, com as sobras redistribuídas. Só muda a origem do peso-alvo, que passa a ser N6 em vez de M5. A Recomendação **substitui** as estratégias Cerrado, Manual e Igual em todas as classes (decisão 10.8).

### Transversal — Registro, explicação e placar (não existe; novo)

- **Registro da decisão** (`recommendation_runs`, `recommendation_items`). Cada execução grava:
  - a versão da política e o hash dos dados;
  - por ativo: resultado de cada portão com o motivo, escore de cada lente com a explicação, nota final, retorno esperado, peso-alvo, peso atual e valor sugerido.

  O plano de aporte confirmado aponta para o seu registro. Responde "por que A e não B" com os dados daquela data.
- **Explicação na tela.** Para cada ativo:
  - "passou nos portões X, Y; foi o 2º da classe por Qualidade (+1,4) e Valuation (+0,9); a Projeção pesou contra (−0,3)";
  - "A e não B": a diferença lente a lente.
- **Placar.** Como o do Garimpo (43.5): cada recomendação passada é medida contra a classe e contra as referências (pesos iguais, só o Cerrado) em 3, 6 e 12 meses. As **carteiras de comparação da Fase 36** passam a ser este placar ao vivo, com o seu fluxo real de aportes.
- **Validação do todo.** Backtest walk-forward da hierarquia inteira (N3 a N7) contra pesos iguais, só o Cerrado e a carteira atual, com Sharpe deflacionado e PBO do Laboratório. Por isso todos os insumos precisam ser point-in-time. "A hierarquia não melhora" é um resultado válido, e a tela diz isso.

## 5. O que muda em cada peça existente

| Peça | Papel novo |
|---|---|
| Cerrado (M4) | Lente L0 com penalidade para quem não foi analisado, não é mais filtro de entrada. As perguntas automáticas também alimentam a L1. Um ativo bem colocado sem análise gera o aviso "analise o Cerrado" |
| Estratégias Cerrado, Manual e Igual (M5) | **Deixam de ser opções do aporte** (decisão 10.8). A política perde o campo de estratégia por classe e o peso manual por ativo; os planos já confirmados guardam a estratégia que usaram. Cerrado e Igual continuam calculados só como **referências internas** do placar e do backtest ("o que a regra antiga teria sugerido") |
| Valuation (M6) e leitura dos indicadores (M7) | L2 e L5; o SUSPEITO vira portão |
| Piotroski/Altman (M8) | L1; Altman em estresse vira portão |
| Saúde (M9) | Continua como diagnóstico. Os limites de concentração (ativo, setor, grupo) passam a ser restrições em N6, para a recomendação não piorar a saúde |
| Ciclo de vida (M3) | Deixa de depender do Cerrado. ELIGIBLE passa a significar "passou nos portões de N3"; o Cerrado só muda a nota |
| Previsão (M14) | L6 e L7, com a regra de dupla contagem |
| Garimpo (M15) | Os sinais vão para o registro único (L1 a L4). Os achados viram a camada "catálogo" de N2 |
| Candidatos (M13) | L8: o efeito marginal na carteira |
| Fase 34 | Vira N6 completo |
| Fase 36 | Vira o placar ao vivo |
| Fases 42.6, 42.7 e 43.6 | Novos insumos de lentes; entram depois do esqueleto |

## 6. Ordem de construção sugerida

Primeiro o esqueleto auditável, com o que já existe; depois a sofisticação.

| Etapa | Entrega |
|---|---|
| R.0 | Decisões da seção 10 |
| R.1 | Registro único de sinais point-in-time (unifica os painéis do Garimpo, da previsão e do valuation) e as lentes L0 (Cerrado com penalidade) a L7 padronizadas, com escore, confiança e explicação |
| R.2 | Portões N3 consolidados em uma função, com motivo por ativo |
| R.3 | Combinação N5 pelo AHP clássico (matrizes par a par, razão de consistência), matriz de decisão e AHP Gaussiano como referência; retorno esperado acima da classe |
| R.4 | Construção simples N6 (K melhores, tetos por ativo, setor e grupo, seleção que alterna setores, encolhimento para o peso atual) calculada e mostrada ao lado do aporte atual, sem trocar ainda a origem do peso-alvo |
| R.5 | Registro da decisão (`recommendation_runs`/`items`), tela "Por que estes ativos" e "A e não B", MCP |
| R.6 | Backtest walk-forward da hierarquia contra as referências (Cerrado e Igual) e placar das recomendações; depois de você ver o resultado, a troca: a Recomendação passa a ser a origem do peso-alvo do aporte (N7) e substitui Cerrado, Manual e Igual |
| R.7 | Pesos das lentes validados pelos dados (N5, forma 2) |
| R.8 | Otimização completa (Fase 34) e placar ao vivo (Fase 36) |

## 7. Riscos

| Risco | Tratamento |
|---|---|
| Sobreajuste: muitas lentes, pesos e tetos ajustados no passado | Pesos declarados primeiro; dados só mudam com portão fora da amostra, contadas as tentativas (PBO, Sharpe deflacionado) |
| Dupla contagem da mesma evidência | Registro único de sinais e regra de uma lente por sinal (10.5) |
| Look-ahead no backtest | Só sinais point-in-time; a L0 (Cerrado manual) não tem histórico de respostas e sai do backtest, com aviso; as perguntas automáticas entram pela L1 (10.3) |
| Girar demais a carteira | Encolhimento para o peso atual, sem venda, aporte por déficit |
| Caixa-preta | Toda nota se decompõe em lentes, e toda lente em sinais com frase |
| Concentração em um setor "barato" | Indicadores comparados dentro do setor em N4; tetos de setor, grupo e emissor e seleção que alterna setores em N6 |
| Julgamentos incoerentes nos pesos do AHP | Razão de consistência ≤ 0,10, com os pares mais contraditórios apontados; ranking do AHP Gaussiano ao lado, como referência |
| Ativo bom esquecido por não ter análise | Cerrado como peso, não filtro; aviso "analise o Cerrado" quando um não analisado fica entre os K melhores |

## 8. O que não muda

- Sem venda automática; REVIEW só chama atenção.
- Proporção ARCA definida por você.
- A recomendação é uma proposta auditável; nada vira ordem sem a sua confirmação.

## 9. Fases pausadas

A pedido, ficam pausadas até a aprovação desta hierarquia:

- 42.6 e 42.7;
- 43.6;
- as propostas 34 e 36.

A 42.5 (PR #56) já estava em andamento e é concluída.

## 10. Decisões

Respondidas em 2026-10-30 (✔). As que restam ficam marcadas como pendentes.

1. ✔ **N1:** a proporção entre classes continua só da política, sem ajuste tático.
2. ✔ **Cerrado:** é peso (lente L0), nunca filtro. Nota de 0 a 10; quem não tem análise recebe **0**. Pode receber aporte, com o destaque de que a análise pode melhorar a nota e reclassificar o ativo.
3. ✔ **Backtest com o Cerrado manual:** a L0 sai do backtest e os pesos das outras lentes são reescalados. As perguntas automáticas, recalculadas com os balanços de cada data, continuam valendo pela L1. O backtest avisa que o Cerrado manual não foi testado. No aporte de verdade, a L0 entra normalmente.
4. ✔ **Universo:** o aporte pode comprar da carteira, da watchlist **e do catálogo**. Os ativos do catálogo passam pelos mesmos portões, vêm marcados como "novos" e entram na watchlist quando o plano é confirmado.
5. ✔ **Dupla contagem:** a L7 usa a previsão com as camadas A e C, sem a B; o valuation fica inteiro na L2.
6. ✔ **Construção:** começa simples (seleção que alterna setores, tetos, encolhimento para o peso atual). O **K é dinâmico**: cada ativo só entra se o ganho de diversificação compensar a queda de nota, com K mínimo, K máximo e lote mínimo de aporte. A otimização completa (Fase 34) vem depois.
7. ✔ **Pesos das lentes:** AHP clássico com as matrizes pré-configuradas da seção N5 (editáveis e versionadas); AHP Gaussiano só como referência.
8. ✔ **Convivência:** a Recomendação **substitui** Cerrado, Manual e Igual em todas as classes, de uma vez. As regras antigas continuam calculadas só como referências internas do placar e do backtest. Como a troca é única, o placar das recomendações (R.6) e o backtest da hierarquia contra essas referências entram antes da troca no aporte. A troca acontece depois de você ver o resultado.
9. ✔ **Setores:** teto de 25% da classe por setor e por grupo, até 2 ações por setor, margem de 0,5 desvio de nota para repetir um setor já coberto.
10. ✔ **Grupos por correlação:** sim, além do setor da B3, recalculados a cada trimestre e mostrados na tela.
11. **Valores do K dinâmico** (pendente): λ (aversão a risco), K mínimo, K máximo e lote mínimo por classe. *Recomendação: definir na 44.4 com a curva real de cada classe à vista.*
