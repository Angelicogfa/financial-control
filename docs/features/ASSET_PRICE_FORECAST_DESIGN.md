# Previsão probabilística do preço dos ativos (bayesiana, com dados da CVM)

> **Status:** proposta para decisão (Fase 42). Nada implementado.
> **Pergunta que responde:** "Qual a faixa provável do preço deste ativo daqui a 3, 6, 12 e 24 meses, e com que chance ele estará acima de um valor que me importa?"
> **O que não é:** preço-alvo ou recomendação de compra. O produto é uma distribuição calibrada, com a confiança medida, nunca um número único.

## 1. Resposta curta: é possível?

Sim, em três camadas, cada uma só entrando no resultado se melhorar a previsão fora da amostra.

| Camada | Fonte | Viável? | O que muda na previsão |
|---|---|---|---|
| **A. Base de mercado** | Histórico diário de preço (Fase 39) e cenários das classes (Fase 33) | Sim, quase tudo existe | A faixa provável: tendência da classe, sensibilidade do ativo (β), desempenho próprio encolhido (α) e volatilidade |
| **B. Fundamentos da CVM (quantitativo)** | DFP e ITR dos dados abertos da CVM, **com a data de entrega** | Sim, falta a carga | O centro da distribuição: ativos caros ou baratos frente ao próprio histórico e ao setor ajustam o retorno esperado, com o peso que os dados justificarem |
| **C. Eventos da CVM (qualitativo)** | IPE (fatos relevantes, comunicados, ofertas, assembleias) já carregado; negociações de administradores (VLMO, a confirmar) | Sim, com limites | Ajustes de curto prazo na tendência e na volatilidade depois de um evento, do tamanho que o histórico de eventos do mesmo tipo justificar |

O que a CVM **não** permite sem custo: ler o texto integral dos documentos. O IPE estruturado traz categoria, tipo, espécie e assunto; o texto está em PDF. A proposta usa uma taxonomia de palavras-chave sobre o assunto (sem custo). Ler os PDFs com um modelo de linguagem fica como opção posterior (decisão 42.0-6).

**Expectativa honesta:** prever a direção do preço é difícil, e a literatura mostra pouco poder preditivo em horizontes curtos. O ganho esperado está em **faixas bem calibradas** e em **probabilidades úteis** ("chance de cair mais de 20%", "chance de passar do preço teto"). Ajustes de valuation e de eventos tendem a ser pequenos, e o modelo deve dizer quando não ajudam, como o Laboratório faz.

## 2. O que já existe e é reaproveitado

| Peça | Onde | Uso aqui |
|---|---|---|
| Modelo fatorial por ativo: retorno = α + β · classe + ruído, com β ~ N(1; 0,5²) e α encolhido pela dispersão da classe | `domain/simulation/candidates.py` (`fit_asset`, `shrink`) | Núcleo da camada A |
| Cenários das classes (bootstrap em blocos, bootstrap bayesiano, normal-inversa-Wishart, combinação calibrada) | `domain/simulation/generators.py`, `bayes.py` | Trajetórias da classe sobre as quais o ativo é projetado |
| Calibração por origem móvel (cobertura, PIT, Brier) | `domain/simulation/calibration.py` | Medir se as faixas do preço se confirmam; selo "Quanto confiar" |
| Portões contra sorte (bayesiano 95%, Sharpe deflacionado, PBO, estabilidade) | `domain/simulation/validation.py`, laboratório | Decidir se valuation e eventos entram |
| Histórico diário de preço persistido | `asset_price_history` (Fase 39) | Retornos do ativo |
| IPE e mapa ticker → CNPJ | `cvm_documents`, `cvm_issuer_tickers` (Fase 28) | Camada C |
| Valuation (Graham, Bazin, P/VP justificado) | `domain/assets/services/valuation.py` | Limiares de probabilidade ("chance de passar do preço teto") |

## 3. O modelo

Retornos mensais em log, já ajustados por proventos e eventos corporativos. Tudo em R$, de hoje.

### 3.1 Camada A: base de mercado

r_ativo,t = α + β · r_classe,t + ε_t, com ε_t ~ t-Student(ν, σ_t)

- **β:** prior N(1; 0,5²), posterior por mínimos quadrados bayesianos, como nos candidatos.
- **α:** prior N(μ_α; τ²). μ_α = 0 na camada A. τ vem da dispersão dos α da mesma classe (bayes empírico, já implementado). O α do ativo é encolhido na proporção da incerteza dele.
- **σ_t:** a volatilidade histórica, ou o modelo de risco aprovado pelo Laboratório (GARCH/EWMA), quando houver um.
- **Cenários da classe:** os da projeção (Fase 33), com a mesma semente, para a previsão do ativo ser coerente com a da carteira.
- **Saída:** milhares de trajetórias do preço. Delas saem percentis e probabilidades em cada horizonte, com o intervalo de credibilidade da própria chance (incerteza dos parâmetros + amostragem).

### 3.2 Camada B: fundamentos da CVM no centro da distribuição

A camada B muda o prior de α: μ_α = γ · z_valuation, onde z_valuation mede o quanto o ativo está caro ou barato **com a informação que existia em cada data**.

- **Indicadores point-in-time, a partir da DFP/ITR:** lucro e EBITDA dos últimos 12 meses, patrimônio, dívida líquida e dividendos pagos, cada um válido a partir da data de entrega à CVM. Combinados com o preço do dia, dão earnings yield, dividend yield, P/VP e EV/EBITDA, comparados com:
  - o próprio histórico do ativo (z temporal);
  - o setor (z transversal).
- **γ:** estimado por regressão bayesiana hierárquica em todo o universo com histórico. A pergunta é: "nos últimos N anos, um z de valuation de +1 foi seguido de quanto retorno a mais em 12 meses?". A estimativa usa:
  - prior N(0; pequeno), cético;
  - agrupamento parcial por setor, ou seja, o setor puxa a estimativa do ativo sem a substituir;
  - validação fora da amostra.

  Se γ não passa nos portões, ele vale 0 e a tela diz: "valuation não melhorou a previsão; não foi usado".
- **Efeito colateral útil:** a mesma base point-in-time tira o look-ahead do Passado da simulação e é exatamente o que as Fases 34.9 e 36.8 esperam.

**O que os arquivos reais mostraram (42.2, DFP e ITR de 2024):**
- o layout é o mesmo para todas as empresas, com as mesmas colunas e os mesmos arquivos por ano;
- as contas de topo são fixas, mas há três modelos de plano de contas: 450 empresas, cerca de 10 bancos e 7 seguradoras. O mesmo código muda de sentido entre eles (2.03 é o patrimônio de uma empresa e as provisões de um banco), por isso patrimônio e lucro são achados pelo nome;
- dívida e caixa estão em contas fixas em cerca de 99% dos casos; depreciação e dividendos pagos ficam em contas livres da DFC e são achados pelo nome (432 de 451 e 383 de 451 empresas);
- os valores vêm em mil ou em unidade, conforme a coluna de escala;
- a quantidade de ações vem em milhares para algumas empresas (Vale, Itaú), sem coluna de escala;
- cerca de 10% dos documentos são reapresentações, com até 6 versões;
- o ITR traz o trimestre e o acumulado do ano; o 4º trimestre sai da DFP, e há empresas com ano fiscal fora do calendário.

### 3.3 Camada C: eventos da CVM (qualitativo transformado em dado)

1. **Taxonomia (feita na 42.4):** cada documento do IPE recebe uma classe, pela categoria e por palavras-chave do assunto. Nos dados reais, o fato relevante não tem tipo nem espécie, só o assunto; com 20 classes, 21% a 23% ficam em "outros", a maior parte com assunto genérico. Classes iniciais:
   - aquisição/fusão;
   - desinvestimento;
   - recompra;
   - dividendos/JCP extraordinários;
   - emissão/oferta (diluição);
   - recuperação judicial/reestruturação de dívida;
   - mudança de administração;
   - guidance/projeções;
   - rebaixamento de rating;
   - litígio/multa;
   - outros.
2. **Estudo de eventos:** para cada documento passado, mede o retorno anormal (ativo − β · classe) e a variação de volatilidade nos 1, 5 e 20 pregões seguintes à entrega.
3. **Efeito por classe, bayesiano hierárquico:**
   - efeito_classe ~ N(0; τ_evento²), cético: a maioria dos eventos não tem efeito sistemático;
   - cada classe é puxada para zero na proporção da própria incerteza;
   - eventos raros quase não movem nada.
4. **Na previsão:** um evento recente soma à tendência e à volatilidade o efeito posterior da sua classe, decaindo no horizonte do estudo (por exemplo, 20 pregões), com a incerteza do efeito propagada nas trajetórias.
5. **Negociações de administradores (VLMO):** a CVM publica as posições dos administradores. Confirmado o conjunto estruturado, a compra ou venda líquida dos últimos 3 meses vira mais um preditor da camada B, com o mesmo tratamento cético.
6. **Portões:** só entra a classe de evento cujo efeito passa fora da amostra. As outras aparecem como "sem efeito comprovado".

**Limite de amostra:** hoje o banco tem 5.636 documentos de 19 empresas desde jan/2025, 315 deles fatos relevantes. Isso basta para mostrar eventos, não para estimar efeitos. A proposta carrega o IPE histórico (a CVM publica desde 2003, um arquivo por ano) para todas as empresas com histórico de preço no universo da estimação.

## 4. Validação e confiança

- **Origem móvel:** em cada mês do passado, o modelo é estimado só com o que existia até ali e prevê 3, 6 e 12 meses à frente. A comparação com o realizado mede:
  - cobertura das faixas de 50% e 90%;
  - PIT, para ver se o centro está viciado;
  - Brier da "chance de subir" e da "chance de cair mais de 20%".
- **Contra quem compete:** a camada A sozinha é a referência. B e C precisam melhorar o log score de forma significativa, descontado o número de tentativas.
- **Selo "Quanto confiar"** na tela, com os mesmos quatro níveis dos estudos (Fase 41), por ativo ou pelo universo quando o ativo tem pouco histórico.
- **Mínimo de histórico:** 36 meses de preço para mostrar a previsão. Abaixo disso, a tela explica e não inventa faixa.

## 5. Como aparece

**Página do ativo, aba "Probabilidades"**, no padrão da Fase 37:

1. **Em resumo:** "Em 12 meses, há 58% de chance de WEGE3 estar acima do preço de hoje (R$ 52,10). A faixa de 90% vai de R$ 38 a R$ 71." Valores ilustrativos.
2. **Indicadores:**
   - chance de subir;
   - chance de cair mais de 20%;
   - chance de passar do preço teto (Bazin/Graham/P/VP justificado, o que se aplicar ao ativo);
   - mediana em 12 meses.
3. **Gráfico:** leque de preço nos horizontes de 3, 6, 12 e 24 meses, com o preço de hoje, o preço médio de compra e o preço teto como linhas de referência.
4. **O que pesou:** a decomposição do centro da distribuição:
   - mercado e classe;
   - valuation da CVM (ou "não usado");
   - eventos recentes, cada um com a sua classe e o efeito estimado, ou "sem efeito comprovado".
5. **Quanto confiar:** o selo, com "Quando o modelo disse 90%, aconteceu em X%".
6. **Calculadora:** "Qual a chance de passar de R$ __ em __ meses?"
7. **Como ler:** distribuição, não preço-alvo; premissas; tamanho da amostra.

**Outras integrações:**
- **Estudos (Fase 41):** os candidatos do capítulo 3 ganham a faixa do preço de cada um.
- **Alertas internos:** opcional; por exemplo, "a chance de cair mais de 20% em 3 meses passou de 25%".
- **MCP:** `assets.forecast` (consulta) e `assets.forecast_quality` (calibração).

## 6. Dados a carregar

| Conjunto | Origem | Frequência | Tabela proposta |
|---|---|---|---|
| DFP e ITR (demonstrações, com `DT_RECEB`) | `dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP` e `/ITR`, um ZIP por ano | Semanal no worker; carga histórica uma vez | `cvm_statements` (CNPJ, período, conta, valor, data de entrega, versão) |
| IPE histórico | O mesmo arquivo anual já usado, anos anteriores a 2025 | Uma vez, depois o diário que já existe | `cvm_documents` (já existe) + `event_class` |
| VLMO (negociações de administradores) | Dados abertos da CVM, **a confirmar** que existe em formato estruturado | Mensal | `cvm_insider_positions` |
| Histórico de preço do universo de estimação | Provedores atuais | Diário (Fase 39) | `asset_price_history` (já existe), estendido aos ativos do catálogo usados na estimação |
| Resultado da previsão | Worker | Diário para a carteira e a observação; sob pedido para os demais | `asset_forecasts` (ativo, data, horizonte, percentis, probabilidades, decomposição, versão do modelo, semente) |

Nada disso depende de serviço pago: são os dados abertos da CVM e os provedores atuais. O cálculo pesado (estimação hierárquica e validação) roda no worker; a tela lê `asset_forecasts`, seguindo a regra da Fase 39.

## 7. Riscos e como são tratados

| Risco | Tratamento |
|---|---|
| Look-ahead: usar um balanço antes de ele existir | Valuation só a partir da `DT_RECEB` da CVM; previsões passadas usam apenas o que existia |
| Viés de sobrevivência: só empresas que existem hoje | Usar o cadastro da CVM com canceladas para o universo de estimação; avisar quando não der |
| Sorte nos achados (muitas classes de eventos × horizontes) | Prior cético, agrupamento parcial, portões com o número de tentativas e PBO, como no Laboratório |
| Eventos confundidos: vários no mesmo dia, ou com resultado trimestral | Janela com controle por divulgação de resultado; um dia com vários documentos conta como um evento de classe mista |
| Saltos de proventos e desdobramentos | Retornos de preço ajustado; eventos corporativos aplicados |
| Pouco histórico do ativo | O agrupamento puxa para a classe e o setor; abaixo de 36 meses, não mostra |
| Ler a previsão como recomendação | Linguagem de probabilidade, selo de confiança e nota fixa "distribuição, não preço-alvo" |

## 8. Encaixe no código

- `domain/forecast/`:
  - `model.py`: camadas A, B e C, puras;
  - `events.py`: taxonomia e estudo de eventos;
  - `valuation_pit.py`: indicadores point-in-time;
  - `validation.py`: reaproveita a calibração e os portões.
- `infra/providers/cvm.py`: DFP/ITR (e VLMO, se confirmado), no mesmo padrão do IPE.
- Worker:
  - `sync_cvm_statements` (semanal);
  - `backfill_cvm_documents` (uma vez);
  - `estimate_forecast_models` (semanal: γ, efeitos de eventos, calibração);
  - `refresh_asset_forecasts` (diário).
- API: `GET /assets/{id}/forecast`, `GET /forecast/quality`, mais as operações MCP.
- Web: aba "Probabilidades" no ativo e o selo; "O que pesou" com a decomposição.

## 9. Entregas em etapas (Fase 42)

| Item | Entrega |
|---|---|
| 42.0 | Decisões da seção 10 |
| 42.1 | Camada A por ativo (reaproveitando o modelo dos candidatos), `asset_forecasts`, aba "Probabilidades", MCP, calibração e selo |
| 42.2 | Carga da DFP/ITR point-in-time (`cvm_statements`) e indicadores com data de entrega; também destrava 34.9 e 36.8 |
| 42.3 | Camada B: valuation no prior de α, hierárquica por setor, com portões |
| 42.4 | Carga histórica do IPE, taxonomia de eventos e estudo de eventos hierárquico |
| 42.5 | Camada C: efeito dos eventos recentes na previsão, com portões e "o que pesou" |
| 42.6 | VLMO (se o conjunto estruturado existir) como preditor da camada B |
| 42.7 | Integração com os estudos (candidatos), alerta opcional, testes de UI e integração, `docker compose build` |

A 42.1 sozinha já entrega a visão probabilística, com faixas calibradas. As demais etapas só mudam o resultado se provarem valor.

## 10. Decisões para você

1. **Horizontes:** 3, 6, 12 e 24 meses (recomendado) ou outros.
2. **Preço ou retorno total:** mostrar o preço (recomendado, é o que se vê na corretora) com o retorno total, incluindo proventos, como indicador ao lado; ou só o retorno total.
3. **Universo da estimação:** carteira + observação + os mais líquidos do catálogo (recomendado; mais dados para o agrupamento) ou só carteira + observação.
4. **Carga histórica da CVM:** desde 2010 (recomendado; cobre ciclos de alta e baixa) ou outra data.
5. **Quem aparece:** só os ativos com selo de pelo menos "Use com cautela" (recomendado), ou todos com o selo à mostra.
6. **Texto dos documentos:** só a taxonomia por palavras-chave do assunto (recomendado; sem custo), ou também ler o PDF dos fatos relevantes com um modelo de linguagem (custo por documento, decisão de privacidade).
7. **Alerta:** criar o alerta interno de "chance de queda forte" (recomendado, desligado por padrão) ou não.
8. **Ordem em relação às Fases 34 e 36:** fazer a 42 antes (como pedido), aproveitando que a 42.2 destrava 34.9 e 36.8.
