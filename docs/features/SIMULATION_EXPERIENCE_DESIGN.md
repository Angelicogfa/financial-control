# Simular carteira — nova experiência: do estudo à conclusão

> **Status:** proposta para decisão (Fase 41). Nada implementado.
> **Escopo:** experiência, dinâmica e organização da ferramenta Simular carteira. Os motores de cálculo da Fase 33 (backtest, projeção, candidatos, robustez, calibração e laboratório) continuam os mesmos; muda como são pedidos, encadeados, explicados e guardados.

## 1. O que confunde hoje

| # | Problema | Onde aparece |
|---|---|---|
| P1 | **Seis abas no mesmo nível para coisas de natureza diferente.** Passado, Futuro e Candidatos respondem perguntas suas; Robustez, Confiança e Laboratório verificam se essas respostas merecem confiança. Na tela, todas parecem ferramentas independentes. | Barra de abas |
| P2 | **Dependências escondidas.** A Robustez mede "a simulação do Passado selecionada", mas a escolha fica num parâmetro da URL e não aparece na aba. A Confiança alimenta o Futuro só por uma linha de texto ("pesos da calibração #N"). Os Candidatos usam as trajetórias do Futuro, mas com um formulário próprio, em que aporte e horizonte são digitados de novo e podem divergir. | Robustez, Confiança, Candidatos |
| P3 | **Premissas repetidas e desencontradas.** Aporte mensal, horizonte e meta são digitados em três formulários; nada garante que o Futuro e os Candidatos olhem para a mesma situação. | Formulários |
| P4 | **O Laboratório contradiz a si mesmo.** O veredito diz "1 modelo passou" e a tabela marca quem passou, mas o gráfico abaixo é sempre o regime de estresse do HMM de 2 estados, qualquer que seja o aprovado. Quando o aprovado é outro, por exemplo um GARCH, o gráfico mostra um modelo que não passou, sem avisar. | Laboratório |
| P5 | **Vocabulário de pesquisa na frente do usuário.** "Ganho de log score", "PBO", "Sharpe deflacionado", "PIT", "Brier" aparecem como títulos de colunas, sem tradução para a decisão que importam. | Confiança, Laboratório |
| P6 | **Não há fio narrativo.** Cada aba termina em si mesma. Ninguém diz por onde começar, o que a conclusão significa para a carteira ou qual é o próximo passo (aportar, estudar um ativo, rever a meta). | Página inteira |
| P7 | **Resultados presos à aba.** Cada aba tem sua lista de rodadas e não dá para:<br>• ver numa página só o que se sabe hoje sobre a carteira;<br>• comparar duas situações (aporte de R$ 1.000 × R$ 1.500);<br>• acompanhar como a chance da meta mudou com o tempo;<br>• levar o resultado para fora (impresso, PDF). | Listas de rodadas |
| P8 | **Um resultado pode enganar.** A estratégia termina 100% em Caixa no Passado porque as respostas do checklist só valem a partir da data em que foram dadas, e a tela só avisa no resumo. | Passado |

## 2. Princípios da proposta

1. **Uma pergunta por vez, uma resposta por capítulo.** O usuário começa por uma pergunta dele, não por uma técnica.
2. **Premissas uma vez só.** Aporte, horizonte, meta, período e regras são definidos no início e valem para tudo o que depende deles.
3. **A verificação mora junto da afirmação.** A Robustez aparece dentro do resultado do Passado ("quanto isso depende de sorte"), e a Confiança dentro do Futuro ("quanto confiar nestas chances"). Deixam de ser abas.
4. **Toda tela conta a mesma história:** conclusão → números que a sustentam → gráfico → quanto confiar → detalhe → como ler. É o padrão da Fase 37, aplicado de ponta a ponta.
5. **Pesquisa fica nos bastidores.** O Laboratório é controle de qualidade dos modelos, não pergunta do usuário. Sai do fluxo principal e mostra só o que de fato está em uso.
6. **Todo resultado é guardado, nomeado, comparável e pode ser refeito com os dados de hoje.**

## 3. A unidade nova: o **Estudo**

Um estudo é **uma pergunta + um conjunto de premissas + os capítulos que respondem**. Ele substitui as rodadas soltas de cada aba.

```
Estudo "Aposentadoria 2040"  (criado em 29/10/2026, refeito em 05/11/2026)
├─ Premissas ............ aporte R$ 1.500/mês · horizonte 15 anos · meta R$ 1,2 mi · passado desde 2012 · regras de hoje
├─ Cap. 1  De onde viemos ........... backtest + robustez        (o que as regras teriam feito)
├─ Cap. 2  Para onde vamos .......... projeção + confiança       (faixa provável e chance da meta)
├─ Cap. 3  O que pode melhorar ...... candidatos (mesma projeção do cap. 2)
└─ Conclusão e próximos passos ...... síntese em texto + ações
```

O usuário escolhe que capítulos quer; os que dependem de outro puxam o anterior sozinhos. Os Candidatos, por exemplo, sempre rodam sobre a projeção do mesmo estudo.

### 3.1 O que cada capítulo mostra

| Capítulo | Pergunta (título da seção) | Conclusão em uma frase (exemplo) | "Quanto confiar" embutido |
|---|---|---|---|
| **1. De onde viemos** | "Se eu tivesse seguido minhas regras desde 2012, onde estaria?" | "Seguindo suas regras você teria R$ 412 mil, R$ 38 mil acima do mesmo fluxo no CDI; o melhor resultado foi do S&P 500." | **Robustez:** "O resultado se manteve em 9 das 12 variantes de regra; na pior crise (2020) a carteira caiu 24%." |
| **2. Para onde vamos** | "Vou chegar à minha meta?" | "A chance de chegar a R$ 1,2 mi em 2040 é de 64% (entre 57% e 71%). No cenário mediano você chega a R$ 1,31 mi." | **Confiança:** "Quando o modelo disse 90%, aconteceu em 87% das vezes nos últimos 10 anos: as chances são confiáveis, um pouco otimistas." |
| **3. O que pode melhorar** | "Que ativo acrescentar aumentaria a minha chance?" | "Incluir TAEE11 no próximo aporte eleva a chance da meta de 64% para 66%; a melhora é real com 71% de probabilidade." | Mesmo selo do capítulo 2 (as trajetórias são as mesmas) e o aviso de "lista para estudo, não ordem de compra". |
| **Conclusão** | "O que isso quer dizer para mim?" | 3 a 5 frases ligando os capítulos (ver 3.3). | — |

### 3.2 Anatomia de um capítulo (padrão único)

```
┌─ Capítulo 2 · Para onde vamos ─────────────────────────────────────────────┐
│ EM RESUMO  A chance de chegar a R$ 1,2 mi em 2040 é de 64% (57% a 71%).    │
│                                                                             │
│ [Chance da meta 64%] [Mediana R$ 1,31 mi] [Pior 5% R$ 0,78 mi] [Renda/mês] │
│                                                                             │
│  ▁▂▃▅▆▇  gráfico em leque: faixa de 90%, 50% e mediana até 2040             │
│                                                                             │
│ QUANTO CONFIAR  ●●●○  Chances confiáveis, um pouco otimistas                │
│   Quando dissemos 90%, aconteceu em 87% · calibrado em 03/11 · ver detalhe  │
│                                                                             │
│ ▸ Cenários de juros (queda · premissa · alta)                               │
│ ▸ Detalhe por ano                                                           │
│ ▸ Detalhes técnicos (motor, semente, dados usados)                          │
│                                                                             │
│ COMO LER  • Faixas, não promessas  • Premissas de hoje  • …                 │
│                                                                             │
│ → Este resultado alimenta o Capítulo 3 (O que pode melhorar)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

O selo "Quanto confiar" tem sempre quatro níveis com frase fixa, para que se leia igual em todo capítulo:

| Nível | Frase | Critério (capítulo 1: robustez · capítulo 2: confiança) |
|---|---|---|
| ●●●● | Muito confiável | variantes concordam ≥ 90% · cobertura dentro de ±3 p.p. |
| ●●●○ | Confiável | ≥ 70% · ±6 p.p. |
| ●●○○ | Use com cautela | ≥ 50% · ±10 p.p. |
| ●○○○ | Pouco confiável | abaixo disso, ou amostra curta |

### 3.3 A conclusão do estudo

O texto é montado a partir dos capítulos, sem números novos, e sempre termina em ações:

> Suas regras teriam funcionado: R$ 38 mil acima do CDI desde 2012, e o resultado não dependeu de um período sortudo. Daqui para frente, a chance de chegar à meta é de 64%, com chances confiáveis. Para subir essa chance, o candidato mais promissor é TAEE11 (+2 p.p.); aumentar o aporte para R$ 1.800 teria efeito parecido.
>
> **Próximos passos:** [Estudar TAEE11 no comparador] · [Simular aporte de R$ 1.800] · [Ir para Aportar]

"Simular aporte de R$ 1.800" cria uma **variação** do estudo: as mesmas premissas com um valor alterado, já pronta para comparar (ver 4.2).

## 4. Dinâmica de uso

### 4.1 Jornada

```
Simular carteira (lista de estudos)
   │  cartões: nome · pergunta · conclusão em 1 linha · chance da meta · data · situação
   │  [Novo estudo]   [Comparar estudos]
   ▼
Novo estudo — assistente em 3 passos
   1. O que você quer saber?
      ○ Minhas regras teriam funcionado?          → capítulo 1
      ○ Vou chegar à minha meta?                  → capítulo 2
      ○ O que acrescentar à carteira?             → capítulos 2 e 3
      ● Estudo completo (recomendado)             → capítulos 1, 2 e 3
   2. Premissas (uma vez): aporte mensal · reajuste pelo IPCA · horizonte · meta ·
      período do passado · regras (as de hoje / as vigentes em cada data) ·
      ativos sem checklist no passado (decisão pendente, seção 8)
      ▸ Avançado: referências, bandas, universo, peso dos candidatos, estresse
   3. Revisar: o que será calculado, em que ordem e o tempo estimado → [Rodar estudo]
   ▼
Página do estudo
   • índice lateral com os capítulos e o estado de cada um (na fila · rodando · pronto)
   • os capítulos aparecem conforme ficam prontos; dá para sair e voltar
   • conclusão no topo assim que o último capítulo termina
```

### 4.2 Como os resultados ficam acessíveis

| Necessidade | Como fica |
|---|---|
| Achar de novo | Lista de estudos com nome, pergunta, conclusão e chance da meta; busca por nome; os excluídos somem de vez (Fase 40.4). |
| Refazer com os dados de hoje | Botão **Atualizar estudo**: as mesmas premissas com o histórico e a carteira de hoje. Cria uma versão nova e guarda a anterior. |
| Acompanhar no tempo | Linha do tempo do estudo: chance da meta e patrimônio mediano a cada versão ("subiu de 58% para 64% desde março"). |
| Comparar situações | **Variação** (copiar o estudo mudando uma premissa) e **Comparar**: dois estudos lado a lado, capítulo por capítulo, com a diferença destacada. |
| Ver sem entrar na ferramenta | Cartão no Início: "Último estudo: chance da meta 64% (↑6 p.p.) · Aposentadoria 2040". |
| Levar para fora | Versão para impressão/PDF do estudo, com premissas, capítulos, conclusão e detalhes técnicos. |
| Agente (MCP) | `study.create`, `study.get`, `study.list`, `study.refresh`, `study.compare`, que devolvem a mesma conclusão em texto. |
| Reproduzir | "Detalhes técnicos" em cada capítulo: motor, semente, dados usados e hash; o refazer usa os mesmos. |

### 4.3 O Laboratório nos bastidores

O Laboratório passa a ser **"Qualidade dos modelos"**, acessível pelo rodapé de cada selo "Quanto confiar" e por Dados de mercado. Mudanças:

1. **O gráfico mostra o modelo escolhido na tabela.** Por padrão é o que passou; sem aprovado, é a referência simples. O título diz qual modelo está na tela e se ele passou. Isso corrige o P4.
2. **O veredito vem traduzido.** "Nenhum modelo de regime prevê o mês seguinte melhor que a média histórica; a simulação continua sem regimes." Ou: "O GARCH previu melhor a volatilidade; ele passa a ser usado no Futuro a partir de hoje" (decisão 41.0-7).
3. **As colunas ficam em linguagem de decisão**, com o termo técnico como dica:

| Hoje | Proposto |
|---|---|
| Ganho de log score por mês | Acerto a mais que a regra simples |
| Chance de superar a referência | Chance de ser melhor de verdade |
| Sharpe deflacionado | Continua melhor depois de descontar as tentativas? |
| PBO | Chance de o vencedor ser sorte |
| Cobertura / PIT / Brier (Confiança) | "Quando dissemos 90%, aconteceu em X%" |

## 5. Do que existe hoje para o proposto

| Hoje | Proposto |
|---|---|
| Aba Passado | Capítulo 1, com a Robustez dentro |
| Aba Robustez | Seção "Quanto isso depende de sorte?" do capítulo 1 (crises, choques, variantes) |
| Aba Futuro | Capítulo 2, com a Confiança dentro |
| Aba Confiança | Selo "Quanto confiar" do capítulo 2 + detalhe em "Qualidade dos modelos" |
| Aba Candidatos | Capítulo 3, sempre sobre a projeção do capítulo 2 do mesmo estudo |
| Aba Laboratório | "Qualidade dos modelos" (bastidores), com o gráfico ligado à tabela |
| Rodadas soltas por aba | Estudos (com versões e variações); as rodadas atuais viram estudos de um capítulo na migração |
| Três formulários | Assistente com premissas únicas + "Avançado" |

## 6. Encaixe técnico

- **Backend.**
  - Nova tabela `simulation_studies`: nome, pergunta, premissas em JSON, versão, estudo de origem (para variações e versões), `deleted_at`. As rodadas (`simulation_runs`) ganham `study_id` e `chapter`.
  - Um caso de uso cria as rodadas encadeadas. A dos candidatos herda os parâmetros da projeção do mesmo estudo.
  - A conclusão é uma função pura que lê os resultados dos capítulos e monta o texto, os selos e as ações. Testável sem banco.
- **Worker:** nada muda no motor. A fila só respeita a ordem dos capítulos (o 3 espera o 2).
- **Front.**
  - Rotas `/tools/simulation` (estudos), `/tools/simulation/new` (assistente), `/tools/simulation/:studyId` (estudo) e `/tools/simulation/compare?a=&b=`.
  - Os componentes de capítulo reaproveitam os de hoje (gráficos, tabelas, resumos da Fase 37) em vez de reescrevê-los.
  - O breadcrumb da Fase 40.3 já cobre a navegação: Início › Simular carteira › Aposentadoria 2040 › Comparar.
- **Migração:** cada rodada existente vira um estudo de um capítulo, com nome e premissas lidos da rodada. Nada se perde.

## 7. Entregas em etapas (Fase 41)

| Item | Entrega |
|---|---|
| 41.0 | Decisões da seção 8. |
| 41.1 | **Correção imediata do Laboratório:** o gráfico segue o modelo da tabela, com veredito e colunas traduzidos. Independe do resto e pode sair antes. |
| 41.2 | Estudo no backend: tabela, migração, casos de uso (criar, listar, obter, versão, variação, excluir), encadeamento dos capítulos, MCP. |
| 41.3 | Conclusão e selos "Quanto confiar" como funções puras, com testes dos textos e dos limites. |
| 41.4 | Lista de estudos e assistente em 3 passos. |
| 41.5 | Página do estudo: capítulos 1 a 3, índice, estados, conclusão e próximos passos. |
| 41.6 | Comparar estudos, linha do tempo, cartão no Início e versão para impressão. |
| 41.7 | "Qualidade dos modelos" nos bastidores; as abas antigas são removidas. |
| 41.8 | Migração das rodadas atuais, testes de UI e integração, `docker compose build`. |

## 8. Decisões para você

1. **Estrutura:** aprova o "Estudo com capítulos" no lugar das seis abas? Alternativa mínima: manter as abas, mas embutir Robustez no Passado e Confiança no Futuro, unificar premissas e corrigir o Laboratório.
2. **Pergunta padrão do assistente:** "Estudo completo" (recomendado) ou "Vou chegar à minha meta?".
3. **Selo "Quanto confiar":** os quatro níveis e limites da seção 3.2 estão bons?
4. **Ativos sem checklist no passado (P8):**
   - a) aplicar as respostas de hoje ao histórico inteiro, com aviso;
   - b) tratar "não avaliado" como elegível só no backtest;
   - c) manter.

   No novo assistente, isso vira uma premissa visível do capítulo 1.
5. **Laboratório:** só bastidores (recomendado) ou continuar visível no menu da ferramenta?
6. **Versões:** "Atualizar estudo" guarda todas as versões (recomendado, alimenta a linha do tempo) ou substitui a anterior?
7. **Modelo aprovado no Laboratório:** passa a ser usado automaticamente no Futuro, com aviso na conclusão, ou só com a sua confirmação?
8. **Cartão no Início:** mostrar o último estudo (recomendado) ou um estudo marcado como "principal"?
9. **Ordem:** fazer a 41.1 (correção do Laboratório) já, antes das decisões, e o resto depois (recomendado)?
