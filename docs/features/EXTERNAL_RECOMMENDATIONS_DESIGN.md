# Recomendações Externas: Engenharia Reversa (Fase 47, proposta)

> **Status:** proposta, aguardando as decisões da seção 10.
> **Depende de:** Fase 45 (lentes, portões, matriz, placar ao vivo, validação dos pesos).

## 1. A pergunta

"Uma casa de análise (ou um relatório, um amigo, um fundo) sugeriu estes ativos. **Por que eles?** Que padrão a fonte segue, e esse padrão funciona?"

É o caminho inverso da recomendação. A hierarquia da Fase 45 parte dos dados e chega aos ativos. Aqui se parte dos ativos de outra fonte e se volta aos dados que os explicam, com o mesmo vocabulário: lentes, portões, setores e pesos.

O resultado é **um estudo**, não uma ordem:
- o que os ativos sugeridos têm em comum, lente por lente, contra os que a fonte poderia ter escolhido e não escolheu;
- que pesos de lente reproduzem a escolha da fonte (os "pesos implícitos"), com a incerteza;
- onde a fonte concorda e discorda da recomendação de vocês;
- com várias listas da mesma fonte ao longo do tempo, se o padrão é estável e se as escolhas dela renderam depois.

"A fonte não segue nada que os dados expliquem" é um resultado válido: ela pode usar informação qualitativa que a ferramenta não tem.

## 2. O que já existe e é reaproveitado

| Peça | Uso aqui |
|---|---|
| Lentes L0 a L7 da rodada semanal (`asset_lenses`), para carteira, watchlist e catálogo líquido | O perfil de cada ativo sugerido na data |
| Painel mensal point-in-time do Garimpo (seis sinais, desde o início do histórico) | Refazer as lentes de uma data passada, como no teste no passado (45.6) |
| Portões (`asset_gates`) | Quais sugestões a ferramenta recusaria e por quê |
| Matriz de decisão e construção (45.3, 45.4) | Onde cada sugestão ficaria no ranking de vocês e se seria escolhida |
| "Por que A e não B?" (45.5) | A sugestão contra o ativo de vocês mais próximo |
| Placar ao vivo (45.8a) | Cada fonte vira uma carteira de comparação a partir da data da lista |
| Validação dos pesos (45.7) | O portão fora da amostra, se um dia os pesos de uma fonte forem usados |

## 3. Entrada

Uma **lista** tem:
- a **fonte** (nome livre, por exemplo "Casa X — carteira de dividendos"), que agrupa as listas ao longo do tempo;
- a **data** da recomendação (hoje, ou uma data passada);
- os **tickers**, colados como texto (separados por vírgula, espaço ou linha);
- **pesos**, opcionais (quando a fonte informa a alocação);
- uma nota livre (o link ou o resumo da tese, só para referência).

A classe ARCA de cada ticker é inferida do cadastro ou do catálogo. Um ticker sem dados aparece como "sem dados", sem travar o resto.

## 4. A análise de uma lista

Tudo é calculado **na data da lista** (seção 6), contra um **universo de comparação**: os ativos que a fonte poderia ter escolhido, que são os aptos da mesma classe naquela data (decisão 2).

### 4.1 Cobertura e portões
- Quantos tickers têm lentes, de que classes, e quais ficaram de fora (sem histórico, fora do catálogo).
- Quais **não passariam nos portões** de vocês, e por quê (liquidez, histórico curto, recuperação judicial, dado suspeito). Uma fonte que sugere ativos ilíquidos já diz algo sobre o seu padrão.

### 4.2 Perfil por lente
Para cada lente, o **percentil médio** das sugestões dentro do universo da classe (50% = indiferente) e a chance de esse desvio não ser acaso, por permutação: sortear listas do mesmo tamanho no mesmo universo e ver com que frequência a média sai tão alta.

Exemplo de leitura: "As sugestões estão no percentil 78 de Valuation (99% de chance de não ser acaso) e no 71 de Renda (93%). Momentum é indiferente (52%)."

### 4.3 Setores e grupos
A distribuição por setor contra a do universo (setores sobre e sub-representados) e a concentração por grupo de correlação.

### 4.4 Estilo
Qual "regra simples" melhor separa as sugestões do resto do universo, medida pela AUC (a chance de uma sugestão ter nota maior que um não sugerido, sorteados ao acaso):
- cada lente sozinha (estilo puro: valor, qualidade, renda, momentum, baixo risco);
- cada objetivo de vocês (Valorização, Dividendos, Misto), com os pesos do AHP.

Exemplo: "A lista se parece mais com o objetivo Dividendos (AUC 0,81) do que com Valorização (0,58)."

### 4.5 Pesos implícitos
Uma **regressão logística bayesiana**: sugerido (1) contra não sugerido (0), sobre as lentes normalizadas. O prior é centrado nos pesos do AHP do objetivo da classe e encolhe forte, porque 5 a 10 ativos são pouca evidência. O resultado:
- o peso implícito de cada lente, com o intervalo de 90%;
- a AUC dentro da amostra e a de deixar-um-de-fora (a honesta);
- a frase: "a escolha desta fonte é reproduzida por estes pesos com AUC fora da amostra de 0,74"; ou "os dados não explicam a escolha (AUC 0,55): a fonte usa algo que a ferramenta não vê".

### 4.6 Concordância com a recomendação
- A posição de cada sugestão na matriz de vocês e se a construção a escolheria.
- A interseção entre as escolhas das duas.
- Para cada sugestão fora das escolhas de vocês: "Por que A e não B", com o ativo de vocês mais parecido, lente por lente.

## 5. Aprender: várias listas da mesma fonte

Uma lista só diz pouco. Com várias, da mesma fonte, ao longo do tempo:
- **Pesos implícitos agrupados:** todas as listas da fonte num modelo só, cada uma contra o seu universo da data. Os pesos ficam mais firmes, e o intervalo diz o quanto.
- **Estabilidade:** os pesos implícitos de cada lista contra os agrupados. Mudam muito? A fonte mudou de estilo em algum momento?
- **Rotatividade:** o quanto cada lista troca da anterior.
- **Desempenho:** cada lista vira uma carteira de comparação no placar ao vivo, a partir da data dela, com o seu fluxo ARCA ou com um aporte único (decisão 5). Para datas passadas, o desempenho depois da data já existe nos dados e vem rotulado como retroativo. A pergunta final, se as escolhas da fonte batem as de vocês, usa o mesmo veredito do placar (12 meses de registro).
- **Uso pela recomendação** (decisão 4): na v1, só estudo e placar. Depois, os pesos implícitos de uma fonte podem virar um candidato a pesos de lente, que só valeria se passasse o mesmo portão fora da amostra da 45.7, nunca automaticamente.

## 6. Datas no passado

- **Com rodada guardada até a data:** usam-se as lentes, os portões e a matriz da rodada mais recente até aquele dia.
- **Antes da primeira rodada** (outubro de 2026): as seis lentes do painel mensal (Qualidade, Valuation, Melhora, Momentum, Renda e Risco) são refeitas no mês da data, como no teste no passado. O Cerrado e a projeção ficam de fora, porque não têm histórico, e o estudo diz isso. Nesse caso os portões são os que dá para refazer: histórico mínimo e recuperação judicial.
- **Real Estate e Internacional:** as lentes do painel cobrem ações. Para FIIs e ativos de fora, o estudo usa só as lentes que existem, e diz quando são poucas para concluir.

## 7. Riscos

| Risco | Tratamento |
|---|---|
| Poucos ativos (5 a 10 por lista) | Prior forte, intervalos sempre visíveis, AUC deixa-um-de-fora; o veredito por fonte usa todas as listas juntas |
| Informação que a ferramenta não tem (tese qualitativa, conversa com a empresa) | "Os dados não explicam" é resultado válido, com a AUC perto de 0,5 |
| Look-ahead numa data passada | Só o que se sabia na data: rodada guardada ou painel point-in-time |
| Sobrevivência | O catálogo de hoje não tem quem saiu da bolsa; para datas antigas, o universo de comparação fica menor, e o estudo avisa |
| Copiar a fonte sem prova | Nada entra no aporte; os pesos de uma fonte só seriam candidatos pelo portão da 45.7 |
| Dupla contagem | Uma lente de "consenso externo" não entra na v1 |
| Fonte que lucra com a recomendação (pump) | O placar mede o depois; o estudo mostra liquidez e portões reprovados |

## 8. Encaixe no código

- **Domínio:** `domain/external/`
  - `lists.py`: entrada, normalização dos tickers e classes;
  - `profile.py`: perfil por lente com permutação, setores, estilo (AUC);
  - `implied.py`: regressão logística bayesiana (por lista e agrupada por fonte), deixa-um-de-fora;
  - `agreement.py`: posição na matriz, interseção e "A e não B";
  - `history.py`: lentes da data (rodada guardada ou painel refeito).
- **Dados** (migração sequencial): `external_sources` (fonte), `external_lists` (data, nota, resultado guardado) e `external_list_items` (ticker, peso, classe).
- **Placar:** cada lista entra como estratégia `EXTERNAL` do placar ao vivo (45.8a), uma por fonte.
- **API e MCP:** `GET/POST /recommendation/external`, `GET /recommendation/external/{id}`; operações `external.create`, `external.list`, `external.get`.
- **Tela:** aba "Externas" na Recomendação (decisão 6): colar a lista, ver o estudo da lista e o da fonte.

## 9. Entregas em etapas (Fase 47)

| Etapa | Entrega | Critério de aceite |
|---|---|---|
| 47.0 | Decisões da seção 10 | Revisão do usuário |
| 47.1 | Entrada, persistência, lentes da data (rodada ou painel refeito), cobertura e portões | Uma lista com ticker inexistente não trava; data passada sem look-ahead |
| 47.2 | Perfil por lente com permutação, setores e estilo (AUC) | Lista sorteada ao acaso: percentis perto de 50% e AUC perto de 0,5 |
| 47.3 | Pesos implícitos (por lista e por fonte) e concordância com a recomendação | Lista feita pela própria hierarquia: os pesos implícitos voltam perto dos do AHP |
| 47.4 | A fonte no placar ao vivo, estabilidade e rotatividade | Retroativo rotulado; veredito só com 12 meses |
| 47.5 | Tela, MCP, testes de UI e integração, `docker compose build` | |

## 10. Decisões

1. **Entrada:** fonte, data, tickers colados e pesos opcionais. Está bom assim, ou quer importar de arquivo (CSV ou PDF do relatório)? *Recomendado: colar texto na v1.*
2. **Universo de comparação:** os aptos da mesma classe na data (recomendado: compara com o que a fonte de fato poderia escolher, entre ativos líquidos), ou o catálogo inteiro (inclui ilíquidos e torna qualquer escolha "especial")?
3. **Modelo dos pesos implícitos:** regressão logística bayesiana com prior nos pesos do AHP (recomendado: dá intervalo e encolhe com poucos ativos), ou um AHP "inverso" que busca os pesos que põem as sugestões no topo do ranking (mais fácil de ler, sem intervalo)?
4. **O que o aprendizado alimenta:** só o estudo e o placar (recomendado na v1); ou também um candidato a pesos de lente pelo portão da 45.7; ou uma lente nova de "consenso externo"?
5. **Placar:** cada fonte entra no placar ao vivo. Com que dinheiro: o seu fluxo ARCA a partir da data da lista (recomendado: comparável com a sua carteira e a recomendação), ou um aporte único na data? E com que pesos: os informados pela fonte quando houver, senão iguais (recomendado)?
6. **Tela:** aba "Externas" na Recomendação (recomendado: o estudo usa a mesma matriz e o mesmo vocabulário), ou uma tela própria em Ferramentas?
7. **Datas passadas:** refazer as lentes do painel para datas anteriores à primeira rodada (recomendado: permite estudar o histórico de uma fonte), ou aceitar só datas a partir da primeira rodada guardada?
