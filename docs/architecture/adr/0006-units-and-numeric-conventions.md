# ADR 0006 — Convenções de Unidades, Escalas e Tipos Numéricos

- **Status:** Aceito
- **Data:** 2026-10-24
- **Achados relacionados:** C-01, I-02, I-10, D-02 (ver `docs/todo/IMPLEMENTATION_PLAN.md`)

## Contexto
O código atual adivinha a escala de taxas e percentuais por heurística de magnitude:

| Local | Heurística | Falha concreta |
|---|---|---|
| `fixed_income._compound_factor` (série diária do CDI) | `> 0,05` → percentual, senão fração | BCB SGS 12 é sempre percentual; com CDI < ~13,4% a.a. o valor diário (ex.: `0,0393`) vira 3,93% ao dia |
| `fixed_income._compound_factor` (`contracted_rate` CDI/SELIC) | `> 5` → divide por 100 | `5` (500% do CDI) e `5,5` são lidos de formas diferentes |
| `fixed_income._compound_factor` (`contracted_rate` PRE/IPCA) | `> 1` → divide por 100 | IPCA + 0,5% digitado como `0.5` vira 50% a.a. |
| `market.models.as_fraction` | `|x| > 1,5` → divide por 100 | ROE de 1,2% (`1.2`) vira 120% |
| `brapi.get_fundamentals` (`debtToEquity`) | `> 5` → divide por 100 | Dívida/PL de 4,0 em percentual (`4.0`) fica 400% |
| Regra de liquidez do Cerrado | compara volume em **quantidade** com limite em **R$** | Ação de R$ 0,50 com 3 mi de papéis (R$ 1,5 mi) é aprovada; ação de R$ 100 com 30 mil papéis (R$ 3 mi) é reprovada |

Heurística de magnitude é indecidível nas faixas de fronteira e falha silenciosamente. A unidade precisa ser **conhecida na origem** e **explícita no tipo**.

## Decisão

### 1. Representação canônica no domínio (`apps/packages/core`)
| Grandeza | Representação | Exemplo |
|---|---|---|
| Taxa anual (PRE, spread real do IPCA+, CDI anual, yield exigido) | fração decimal | `0.065` = 6,5% a.a. |
| Taxa por período (diária, mensal) | fração decimal do período | `0.000551` = 0,0551% ao dia |
| Percentual de indexador (CDI/SELIC) | multiplicador | `1.10` = 110% do CDI |
| Indicadores fundamentalistas percentuais (ROE, DY, margens, crescimento) | fração decimal | `0.18` = 18% |
| Múltiplos (P/L, P/VP, Dív.Líq./EBITDA, Dívida/PL) | razão pura | `1.8` |
| Volume de negociação | **financeiro** em moeda do ativo | `3_000_000.0` |
| Pesos e metas de alocação | percentual 0–100 apenas em `ArcaTargets`/API; fração 0–1 internamente em motores | `25.0` / `0.25` |

Percentuais na escala 0–100 só existem nas bordas de apresentação (API de leitura para a UI e formulários), nunca dentro de cálculos.

### 2. Conversão acontece uma única vez, na fronteira
- Cada adaptador de provedor (`BcbSgsProvider`, `BrapiProvider`, `YFinanceProvider`) **declara a unidade de cada campo** que consome e converte para a representação canônica. Funções genéricas de "normalização por magnitude" (`as_fraction`) são proibidas.
- Séries persistidas guardam a unidade de origem em `market_series.unit` (`PERCENT_PER_DAY`, `PERCENT_PER_MONTH`, `PRICE`, `INDEX_POINTS`); a leitura para o domínio converte explicitamente pela unidade.
- `contracted_rate` tem semântica fixa por indexador: multiplicador para `CDI`/`SELIC`, fração anual para `PRE`/`IPCA`. A API valida faixas plausíveis (`CDI`/`SELIC`: 0,5–3,0; `PRE`/`IPCA`: 0–0,5) e rejeita valores fora delas com mensagem explicando a convenção. A UI recebe percentuais do usuário e converte antes de enviar.

### 3. Tipos numéricos
- **Dinheiro e quantidades:** `Decimal` nas entidades de domínio, `Numeric` no banco e `Decimal` serializado como string/number nos DTOs. Colunas monetárias de `portfolio_snapshots` migram de `Float` para `Numeric(20, 2)`.
- **Estatística e séries de preço/índice:** `float` é permitido (retornos, volatilidade, correlação, cotações históricas).
- **Snapshots diários da carteira** são uma série estatística derivada (insumo do TWR): a entidade usa `float`, mas o banco guarda `Numeric(20, 2)` e o repositório arredonda para centavos na escrita.
- Arredondamento só na borda de saída (DTO/relatório), nunca em resultados intermediários de cálculo.

### 4. Nomenclatura
Campos e parâmetros carregam o sufixo da unidade quando ambígua: `_pct` (0–100, só apresentação), `_rate` (fração), `_multiplier` (percentual de indexador), `_brl`/`_usd` (moeda).

## Consequências
- **Positivas:** elimina a classe inteira de bugs de escala (C-01, I-02, I-10); valores tornam-se auditáveis; testes podem afirmar unidades diretamente.
- **Negativas:** exige migrations de dados (`market_series.unit`, normalização de `contracted_rate`, snapshots em `Numeric`) e revisão de todos os adaptadores de provedores — planejado nos itens 8.1, 8.2, 8.11 e 8.16.

## Situação (Fases 8–14)
Implementado nos itens 8.1, 8.2, 8.11 e 8.16 e seguido pelos módulos novos: demonstrativos e indicadores fundamentalistas em fração, `ValuationPolicy` com limites em fração ou múltiplo, filtros do screener em fração (`min_dy=0.05`) e o frontend convertendo só na apresentação (`pct()` para frações, `points()` para campos `_pct`).
