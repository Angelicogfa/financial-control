# Garimpo: achados no catálogo inteiro (Fase 43)

## 1. O problema

Hoje a ferramenta começa no que você já segue:
- o screener filtra o que você pede;
- os candidatos (Fase 33.7) medem o efeito, na carteira, do que já está na watchlist;
- a previsão (Fase 42) olha a carteira, a watchlist e as ações mais negociadas.

Falta um processo que procure, **no catálogo inteiro**, empresas que ninguém está olhando e que os dados dizem merecer um olhar. O garimpo é esse processo: ele **acha**, explica por que achou e mede quantas vezes acertou. A decisão continua sua: um achado vira candidato só quando você o segue.

## 2. O que é realista esperar

Os sinais usados têm décadas de evidência (valor, qualidade, melhora dos fundamentos, recompras, compra por administradores), mas:
- os prêmios são pequenos e encolhem depois de publicados (estudos estimam perto de um terço);
- o Brasil tem de 300 a 400 ações com liquidez, e o histórico com balanços point-in-time começa em 2010;
- testar muitos sinais sempre acha "ouros" que são sorte.

Por isso o garimpo:
- usa poucos sinais, todos com base econômica;
- encolhe cada um de forma bayesiana;
- só usa os que passaram fora da amostra (os mesmos portões e o PBO do Laboratório);
- **registra cada achado com data e mede o placar**. Um mês sem achados é um resultado válido.

## 3. Universo

- Todas as ações da B3 com balanço na CVM (Fase 42.2) e liquidez mínima: volume médio diário acima de um piso, por exemplo R$ 1 milhão.
- O histórico de preço do universo inteiro passa a ser carregado pelo worker, estendendo a carga da simulação (Fase 33.1) do "top 50" para o universo do garimpo, com os desdobramentos (42.3).
- Bancos e seguradoras entram só com os sinais que fazem sentido para eles.

## 4. Sinais (todos com a informação da data)

| Sinal | Medida | Base |
|---|---|---|
| Valor | z de valuation da 42.3: rendimentos de lucro, patrimônio, EBITDA/EV e dividendos frente ao próprio histórico e ao setor | Valor (Fama-French) |
| Qualidade | ROE e margem estáveis, dívida líquida/EBITDA baixa, lucro em caixa (fluxo operacional ≥ lucro) | Qualidade, F-score de Piotroski |
| Melhora | Aceleração do lucro e da margem dos últimos 12 meses entre ITRs, dívida caindo | Revisões e momentum de fundamentos |
| Momentum de preço | Retorno de 12 meses menos o último mês, frente à classe | Momentum (Jegadeesh-Titman) |
| Eventos (42.4–42.5) | Recompras, dividendos extraordinários, fatos relevantes com efeito comprovado | Estudo de eventos |
| Administradores (42.6) | Compra líquida nos últimos 3 meses, se o conjunto estruturado existir | Insider trading legal |

Cada sinal vira um z (frente ao setor e ao próprio passado, como na 42.3) e entra num escore combinado com pesos estimados, não escolhidos à mão:
- regressão bayesiana dos retornos de 12 meses sobre os sinais;
- prior cético N(0; pequeno);
- agrupamento parcial por setor;
- um sinal que não passa no portão fica com peso zero.

## 5. Portões contra a sorte

- **Origem móvel anual**, como na 42.3: os pesos de cada ano usam só o que se sabia; a carteira dos achados daquele ano é medida no ano seguinte.
- **Comparação justa:** o retorno dos achados é medido contra a classe (Ações) e contra uma seleção aleatória do mesmo universo e do mesmo tamanho.
- **PBO (probabilidade de sobreajuste)** sobre as variantes testadas (quais sinais, quantos achados), como no Laboratório; com PBO alto, o garimpo mostra "sem achados confiáveis".
- **Custos:** o resultado já desconta uma estimativa de custo de transação e de impacto pela liquidez.

## 6. O que você vê

- **Página "Garimpo"** (abaixo de Pesquisa), com a lista da semana:
  - cada achado com o motivo em uma frase, por exemplo: "1,8 desvio mais barata que o próprio histórico e o setor; lucro acelerou em dois ITRs; recompra anunciada";
  - os sinais em barras e o selo de confiança;
  - a previsão de preço (Fase 42) quando houver;
  - o botão "Seguir", que manda o ativo para a watchlist e, de lá, para os candidatos, que medem o efeito na sua carteira.
- **Placar:** quantos achados de cada mês passado bateram a classe em 3, 6 e 12 meses, contra o acaso, com intervalo de credibilidade.
- **"Por que não apareceu?":** para um ticker qualquer, quais sinais faltaram.
- **MCP:** `research.mining` (lista e motivos) e `research.mining_record` (placar).

## 7. Dados e processos

| Item | Onde |
|---|---|
| Histórico de preço do universo | `market_series` (Fase 33.1), estendido |
| Sinais por empresa e mês | `mining_signals` (empresa, mês, sinal, z) |
| Achados | `mining_findings` (data, ticker, escore, motivos, versão do modelo), nunca reescritos: são a base do placar |
| Modelo (pesos, portões, PBO) | `forecast_models` (`kind = MINING`) |
| Jobs | `sync_mining_universe` (preços, semanal), `run_mining` (semanal, depois dos balanços) |

A tela só lê tabelas, como em toda a aplicação desde a Fase 39.

## 8. Entregas em etapas

| Item | Entrega |
|---|---|
| 43.0 | Decisões da seção 9 |
| 43.1 | Universo e histórico de preço com desdobramentos de todas as ações líquidas |
| 43.2 | Sinais point-in-time (valor, qualidade, melhora, momentum) e `mining_signals` |
| 43.3 | Pesos bayesianos, portões, PBO e custos; `forecast_models` (`MINING`) |
| 43.4 | Achados semanais, `mining_findings`, página "Garimpo", "Seguir" e MCP |
| 43.5 | Placar dos achados contra a classe e o acaso |
| 43.6 | Eventos e administradores entram como sinais quando 42.4–42.6 estiverem prontos |

## 9. Decisões (aprovadas em 30/10/2026, todas as recomendações)

1. Liquidez mínima: volume médio diário acima de R$ 1 milhão (`MINING_MIN_DAILY_VOLUME`).
2. Até 10 achados por semana.
3. Sinais da primeira versão: valor, qualidade, melhora e momentum.
4. Momentum de preço entra.
5. A Fase 43 vem depois da 42.3 e antes de 42.4–42.7.
6. Alerta de achado novo criado, desligado por padrão.

### Opções que estavam em aberto

1. **Liquidez mínima:** volume médio diário acima de R$ 1 milhão (recomendado), de R$ 5 milhões (só as mais líquidas) ou sem piso.
2. **Quantos achados por semana:** até 10 (recomendado) ou todos acima de um escore.
3. **Sinais da primeira versão:** valor, qualidade, melhora e momentum (recomendado), ou só valor e qualidade.
4. **Momentum de preço:** usar (recomendado; é o sinal com mais evidência) ou deixar de fora por preferir fundamentos.
5. **Ordem:** fazer a Fase 43 depois da 42.3 e antes de 42.4–42.7 (recomendado, porque eventos e administradores entram depois como sinais extras), ou terminar a Fase 42 antes.
6. **Alerta:** avisar quando um achado novo surgir (desligado por padrão, como o alerta da Fase 42).
