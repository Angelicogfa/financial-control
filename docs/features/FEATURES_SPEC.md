# Especificação de Funcionalidades (MVP)

## 1. Gestão de Ativos e Termos de Renda Fixa
- Cadastro de ativos de renda variável (`STOCK_BR`, `ETF_BR`, `FII`, `BDR`, `STOCK_INTL`, `ETF_INTL`, `REIT`, `CRYPTO`) e renda fixa/caixa (`FIXED_INCOME`, `TREASURY`, `CASH`).
- Associação automática à classe ARCA com opção de alteração manual.
- Para renda fixa: definição de indexador (`CDI`, `IPCA`, `PRE`, `SELIC`), taxa contratada (ex.: `110% do CDI` ou `IPCA + 6,5% a.a.`), data de emissão/vencimento e isenção de IR (`LCI`/`LCA`).

## 2. Lançamentos de Compras, Vendas e Proventos
- Registro de compras (`BUY`) e vendas (`SELL`) com quantidade, preço unitário, taxas e câmbio na data.
- Cálculo automático de posição por preço médio ponderado e apuração do lucro/prejuízo realizado em cada venda.
- Registro de proventos (`DIVIDEND`, `JCP`, `FII_YIELD`, `FIXED_INCOME_COUPON`) com valor bruto, imposto retido e valor líquido.

## 3. Acompanhamento da Carteira e Consolidação de Ganho/Perda
- Exibição por ativo, por classe ARCA e para a carteira total:
  - **Valor Investido** (custo de aquisição das posições abertas);
  - **Valor Atual** (cotação atualizada em BRL ou valor líquido na curva da renda fixa);
  - **Estimativa de Rendimento até o Momento** (calculada conforme o tipo de ativo: variação de preço + proventos acumulados + *Yield on Cost* / curva contratada de RF);
  - **Consolidação de Ganho / Perda / Rendimento Obtido**: soma de ganho/perda não realizado + ganho/perda realizado em vendas encerradas/parciais + proventos líquidos recebidos, com filtro por período e por classe.

## 4. Alocação ARCA, Diagrama do Cerrado Opcional e Simulador de Aporte
- Comparativo visual e numérico entre percentual atual e meta de cada classe ARCA.
- Questionário do Diagrama do Cerrado por ativo (com respostas automáticas via fundamentos e override manual), **totalmente opcional** (`use_cerrado`).
- Simulador de novo aporte em 2 níveis (Classes ARCA $\rightarrow$ Ativos da classe via Cerrado, Peso Manual ou Peso Igual), sem venda de ativos.

## 5. Indicadores de Mercado, Valuation e Métricas Estatísticas
- Cotações, múltiplos fundamentalistas (`P/L`, `P/VP`, `DY`, `ROE`, `Margem Líquida`, `Dívida/EBITDA`, `Crescimento`) e Valuation auxiliar (**Graham** e **Bazin**).
- Métricas quantitativas: **TWR**, **CAGR**, **Volatilidade**, **Sharpe**, **Sortino**, **Max Drawdown**, **Calmar**, **VaR/CVaR 95%**, **Beta**, **Alpha de Jensen** e **Matriz de Correlação**.
- Comparação com **IBOV**, **IFIX**, **S&P 500**, **CDI** e **IPCA**.
