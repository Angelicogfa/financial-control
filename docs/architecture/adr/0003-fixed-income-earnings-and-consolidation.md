# ADR 0003 — Valoração de Renda Fixa Calculada, Proventos e Consolidação de Ganho/Perda

- **Status:** Aceito
- **Data:** 2026-10-24

## Contexto
Uma carteira real no Brasil combina renda variável (Ações, FIIs, ETFs, BDRs, Stocks, REITs, Cripto) com títulos de renda fixa (`CDB`, `LCI/LCA`, `Tesouro SELIC`, `Tesouro IPCA+`, `Tesouro Prefixado`, `Debêntures`) e recebe fluxo constante de proventos (Dividendos, JCP, rendimentos de FII). Para acompanhar o patrimônio real, o usuário precisa ver:
1. O valor investido;
2. A estimativa de rendimento até o momento calculada de acordo com a natureza do ativo;
3. A consolidação completa de ganhos/perdas (realizados em vendas + não realizados na carteira aberta + proventos recebidos).

## Decisão
1. **Renda Fixa calculada na curva**:
   - Títulos de renda fixa armazenam seus parâmetros em `fixed_income_terms` (`indexer`: `CDI`, `IPCA`, `PRE`, `SELIC`; `contracted_rate`; `issue_date`; `maturity_date`; `tax_exempt`).
   - O sistema busca as séries oficiais do Banco Central (SGS 12 para CDI, 11 para SELIC, 433 para IPCA) e calcula o valor bruto acumulado, o desconto estimado de IOF/IR regressivo (22,5% a 15%, ou 0% para isentos) e o valor líquido atual. O `manual_price` permanece apenas como override opcional.
2. **Proventos no MVP (`earnings`)**:
   - Lançamento de `DIVIDEND`, `JCP`, `FII_YIELD`, `FIXED_INCOME_COUPON` e `RESTITUTION`, registrando valor bruto, IR retido e valor líquido.
3. **Motor de Consolidação (`ConsolidationEngine`)**:
   - Consolida por ativo, por classe ARCA e no total da carteira:
     - `invested_value` (custo atual em aberto)
     - `current_value` (valor de mercado ou curva líquida de RF)
     - `estimated_yield` (valorização + proventos + projeção de yield conforme o tipo de ativo)
     - `unrealized_pnl`, `realized_pnl` e `received_earnings`
     - `consolidated_pnl = unrealized_pnl + realized_pnl + received_earnings`
4. **Benchmarks completos**:
   - Acompanhamento comparativo contra **IBOV** (`^BVSP`), **IFIX** (`IFIX.SA`), **S&P 500** (`^GSPC`), **CDI** e **IPCA**.

## Consequências
- **Positivas:** Visão fiel do retorno total da carteira (preço + proventos + juros compostos da renda fixa) e comparação justa de cada classe ARCA com seu índice de referência (ex.: FIIs vs IFIX, Caixa vs CDI/IPCA).
