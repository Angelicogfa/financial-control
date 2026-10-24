# Arquitetura e Visão Sistêmica — Financial Control

> Solução para controle, acompanhamento e análise de carteira de investimentos baseada na distribuição **ARCA** (Thiago Nigro) e no **Diagrama do Cerrado** opcional (Raul Sena), com cálculo automático de renda fixa por indexador, controle de proventos, consolidação de ganhos/perdas e métricas quantitativas de mercado.

---

## 1. Visão Geral do Domínio

### 1.1 Distribuição ARCA (Macroalocação)
A carteira é dividida em quatro classes com metas percentuais configuráveis (soma = 100%, padrão 25% cada):

| Letra | Classe (`ArcaClass`) | Tipos de Ativo (`AssetType`) | Meta Padrão |
|---|---|---|---|
| **A** | `ACOES` (Ações Brasil) | `STOCK_BR`, `ETF_BR` | 25% |
| **R** | `REAL_ESTATE` (Imobiliário) | `FII`, `REIT` | 25% |
| **C** | `CAIXA` (Caixa / Renda Fixa) | `FIXED_INCOME`, `TREASURY`, `CASH` | 25% |
| **A** | `ATIVOS_INTERNACIONAIS` | `STOCK_INTL`, `ETF_INTL`, `BDR`, `CRYPTO` | 25% |

### 1.2 Seleção Intra-Classe: Diagrama do Cerrado (Opcional)
O **Diagrama do Cerrado** **não é obrigatório**. O sistema oferece três modos de distribuição intra-classe (`IntraClassStrategy`):
1. **`CERRADO`** (padrão quando avaliado): peso proporcional à pontuação positiva do questionário ($\max(\text{score}, 0)$). Ativos com nota $\le 0$ ficam com status `REVISAR` e peso $0$.
2. **`MANUAL_WEIGHT`**: o investidor define manualmente o peso-alvo do ativo dentro da classe (`custom_class_weight`).
3. **`EQUAL_WEIGHT`**: peso igualitário ($1/N$) entre os ativos ativos da classe (fallback automático quando o usuário não usa o Cerrado nem pesos manuais).

### 1.3 Valores da Carteira, Rendimento Estimado e Consolidação de Ganho/Perda
Para cada ativo cadastrado e para o consolidado da carteira (por classe ARCA e geral), o sistema calcula:

```mermaid
flowchart LR
    TX["Transações<br/>(BUY / SELL)"] --> INV["Valor Investido<br/>(invested_value)"]
    TX --> REAL["Ganho/Perda Realizado<br/>(realized_pnl)"]
    MKT["Cotação de Mercado /<br/>Curva de Renda Fixa"] --> CUR["Valor Bruto Atual<br/>(gross_current_value)"]
    CUR --> TAX["IR / IOF Estimado (RF)<br/>(estimated_tax)"]
    CUR --> UNR["Valorização de Capital<br/>(unrealized_pnl = atual - investido)"]
    PROV["Proventos Recebidos<br/>(DIVIDEND, JCP, RENDIMENTO)"] --> EARN["Rendimento de Proventos<br/>(total_earnings)"]
    UNR --> EST["Estimativa de Rendimento até o Momento<br/>(estimated_yield_by_type)"]
    EARN --> EST
    UNR --> CONS["Resultado Consolidado Total<br/>(consolidated_pnl = unrealized + realized + earnings)"]
    REAL --> CONS
    EARN --> CONS
```

#### Estimativa de rendimento até o momento por tipo de ativo (`AssetType`)
| Tipo de Ativo | Como é calculada a Estimativa de Rendimento até o momento |
|---|---|
| **`STOCK_BR` / `STOCK_INTL` / `BDR`** | Valorização da cotação sobre o preço médio $(\text{Preço Atual} - \text{PM}) \times \text{Qtd}$ **+** Dividendos e JCP líquidos recebidos + Dividend Yield estimado para os próximos 12m (*Yield on Cost* = $\text{Proventos 12m} / \text{Custo Investido}$). |
| **`FII` / `REIT`** | Valorização das cotas **+** Rendimentos isentos distribuídos no período + estimativa de renda mensal recorrente baseada no DY de 12 meses. |
| **`ETF_BR` / `ETF_INTL` / `CRYPTO`** | Ganho de capital pela cotação atual em BRL (considerando câmbio USD/BRL) sobre o custo investido. |
| **`FIXED_INCOME` / `TREASURY`** | Marcação na curva contratada desde a data de aplicação até hoje: acumulação diária do **CDI** ($\prod (1 + \text{CDI}_d \times \%_{\text{contratado}})$), **IPCA + taxa real** ($\prod (1 + \text{IPCA}_m) \times (1 + r_{\text{anual}})^{\text{du}/252}$) ou **Prefixado** ($(1 + r_{\text{anual}})^{\text{du}/252}$), demonstrando **Rendimento Bruto**, **Alíquota Regressiva de IR / IOF** e **Rendimento Líquido**. |
| **`CASH`** | Saldo disponível / remuneração automática parametrizada (ex.: 100% CDI diário). |

#### Consolidação de Ganho / Perda / Rendimento Obtido (`ConsolidatedPerformance`)
Visão que permite auditar o resultado fechado e aberto por ativo, por classe ARCA, por mês/ano ou de toda a carteira:
- **Capital Investido Atual (`current_invested`)**: Custo das posições abertas.
- **Patrimônio Atual (`current_value`)**: Valor de mercado / curva líquida das posições abertas.
- **Ganho/Perda Não Realizado (`unrealized_pnl`)**: $\text{Patrimônio Atual} - \text{Capital Investido Atual}$.
- **Ganho/Perda Realizado em Vendas (`realized_pnl`)**: Soma de $\text{Qtd Vendida} \times (\text{Preço Venda} - \text{PM}) - \text{Taxas}$.
- **Proventos Recebidos (`received_earnings`)**: Soma líquida de Dividendos, JCP, Rendimentos de FII e Cupons recebidos.
- **Resultado Consolidado Total (`total_consolidated_pnl`)**:
  $$\text{Resultado Consolidado} = \text{Ganho/Perda Não Realizado} + \text{Ganho/Perda Realizado} + \text{Proventos Recebidos}$$
- **Retorno Total sobre o Capital (`total_return_pct`)** e **TWR (`time_weighted_return`)** comparados contra **CDI**, **IPCA**, **IBOV**, **IFIX** e **S&P 500**.

---

## 2. Diagrama de Contexto e Containers (C4)

```mermaid
flowchart LR
    U(("Investidor"))
    subgraph compose["Docker Compose (financial-control)"]
        WEB["apps/web<br/>React + Vite + Nginx :8080"]
        API["apps/api<br/>FastAPI :8000"]
        WK["apps/worker<br/>APScheduler"]
        MIG["migrate<br/>alembic upgrade head"]
        PG[("postgres:16<br/>vol: fincontrol_pgdata")]
        RD[("redis:7<br/>vol: fincontrol_redisdata")]
    end
    BRAPI["brapi.dev<br/>(Ações B3, FIIs, ETFs, BDRs)"]
    YF["Yahoo Finance<br/>(EUA, Cripto, IBOV, IFIX, S&P500, USD/BRL)"]
    BCB["Banco Central SGS<br/>(CDI série 12, SELIC 11, IPCA 433)"]

    U --> WEB
    WEB -->|"/api/v1/*"| API
    API --> PG
    API --> RD
    WK --> PG
    WK --> RD
    MIG --> PG
    API --> BRAPI
    API --> YF
    API --> BCB
    WK --> BRAPI
    WK --> YF
    WK --> BCB
```

---

## 3. Modelo de Dados (ER)

Todas as tabelas e colunas são definidas em **inglês** e versionadas via migrations Alembic (`script_00001`, `script_00002`, ...):

```mermaid
erDiagram
    ASSETS ||--o{ TRANSACTIONS : has
    ASSETS ||--o{ EARNINGS : distributes
    ASSETS ||--o| FIXED_INCOME_TERMS : configures
    ASSETS {
        int id PK
        string ticker UK
        string name
        string asset_type
        string arca_class
        string currency
        decimal manual_price
        decimal custom_class_weight
        bool use_cerrado
        json cerrado_answers
        bool is_active
        text notes
        timestamp created_at
        timestamp updated_at
    }
    FIXED_INCOME_TERMS {
        int id PK
        int asset_id FK
        string instrument_kind "CDB, LCI, LCA, TESOURO_SELIC, TESOURO_IPCA, TESOURO_PRE, DEBENTURE"
        string indexer "CDI, IPCA, PRE, SELIC"
        decimal contracted_rate "e.g. 1.10 for 110% CDI or 0.065 for IPCA+6.5%"
        date issue_date
        date maturity_date
        bool tax_exempt "true for LCI/LCA/CRA/CRI"
        string liquidity "DAILY, AT_MATURITY"
        string issuer
    }
    TRANSACTIONS {
        int id PK
        int asset_id FK
        string kind "BUY, SELL"
        date trade_date
        decimal quantity
        decimal unit_price
        decimal fees
        decimal fx_rate "1.0 for BRL, USD/BRL on trade date"
        text notes
    }
    EARNINGS {
        int id PK
        int asset_id FK
        string kind "DIVIDEND, JCP, FII_YIELD, FIXED_INCOME_COUPON, RESTITUTION"
        date payment_date
        date ex_date
        decimal gross_amount
        decimal withholding_tax
        decimal net_amount
        text notes
    }
    ARCA_TARGETS {
        string arca_class PK
        decimal target_pct
        string intra_class_strategy "CERRADO, MANUAL_WEIGHT, EQUAL_WEIGHT"
    }
    MARKET_SERIES {
        string symbol PK "Ticker or Benchmark: ^BVSP, IFIX.SA, ^GSPC, CDI, IPCA, USDBRL"
        date reference_date PK
        float value
    }
    PORTFOLIO_SNAPSHOTS {
        date snapshot_date PK
        float invested_value
        float market_value
        float unrealized_pnl
        float realized_pnl_cum
        float earnings_cum
        float consolidated_pnl
        float net_flow
        json by_class
    }
```

---

## 4. Fluxos Principais

### 4.1 Cálculo Automático de Renda Fixa
```mermaid
sequenceDiagram
    participant S as PortfolioService
    participant DB as Postgres
    participant BCB as BCBIndexProvider (Redis + SGS)
    participant FI as FixedIncomeCalculator (core)

    S->>DB: Carrega ativo FIXED_INCOME + FIXED_INCOME_TERMS + TRANSACTIONS
    S->>BCB: Busca série CDI diário (série 12) e/ou IPCA mensal (série 433) desde trade_date
    S->>FI: calculate_position(transactions, terms, cdi_series, ipca_series, as_of_date)
    FI->>FI: Acumula fator bruto pro-rata die por lote de compra
    FI->>FI: Calcula dias corridos e aplica tabela regressiva de IR (22.5% a 15%) se !tax_exempt
    FI-->>S: gross_value, estimated_tax, net_value, gross_yield_pct, net_yield_pct
```

### 4.2 Consolidação de Ganho / Perda / Rendimento
```mermaid
sequenceDiagram
    actor U as Investidor
    participant W as Web
    participant A as API (/portfolio/consolidated)
    participant C as Core (ConsolidationEngine)

    U->>W: Acessa Carteira / Consolidação (filtro por período ou classe ARCA)
    W->>A: GET /api/v1/portfolio/consolidated?from=...&to=...
    A->>C: Consolida compras/vendas (preço médio + lucro realizado)
    A->>C: Valoriza posições abertas (cotação B3/US/Cripto ou curva líquida RF)
    A->>C: Soma proventos líquidos recebidos (EARNINGS) por ativo e por mês
    C-->>A: Por ativo e por classe: Investido, Atual, Estimativa Rendimento, Realizado, Proventos, Total Consolidado
    A-->>W: JSON estruturado para cards, tabelas e gráficos empilhados
```

### 4.3 Simulação de Aporte (com Cerrado Opcional)
```mermaid
flowchart TD
    IN["POST /portfolio/contribution<br/>{amount, use_cerrado?}"] --> N1["Nível 1: Distribuir aporte entre as 4 classes ARCA<br/>proporcional ao déficit vs meta"]
    N1 --> MODE{"Estratégia intra-classe?"}
    MODE -->|"CERRADO (se ativo e houver notas > 0)"| W1["Pesos = max(score, 0) / soma"]
    MODE -->|"MANUAL_WEIGHT (se definido)"| W2["Pesos = custom_class_weight normalizado"]
    MODE -->|"EQUAL_WEIGHT (ou Cerrado desativado)"| W3["Pesos = 1 / N ativos elegíveis"]
    W1 --> N2["Nível 2: Distribuir valor da classe pelo déficit dos ativos"]
    W2 --> N2
    W3 --> N2
    N2 --> QTY["Converter em quantidade (inteira p/ B3, fracionária p/ EUA, Cripto e RF)"]
```

---

## 5. Benchmarks e Indicadores Analíticos

| Código | Descrição | Fonte | Uso Principal |
|---|---|---|---|
| **`^BVSP`** | Ibovespa | brapi / yfinance | Benchmark de `ACOES` e carteira geral (Beta, Alpha, gráfico comparativo) |
| **`IFIX.SA`** | Índice de Fundos Imobiliários | brapi / yfinance | Benchmark da classe `REAL_ESTATE` (FIIs) |
| **`^GSPC`** | S&P 500 | yfinance | Benchmark da classe `ATIVOS_INTERNACIONAIS` |
| **`CDI`** | Taxa DI diária acumulada | BCB SGS (série 12) | Taxa livre de risco ($R_f$ para Sharpe/Sortino) e benchmark de `CAIXA` |
| **`IPCA`** | Inflação oficial mensal | BCB SGS (série 433) | Cálculo de ganho real acima da inflação e indexação de títulos IPCA+ |
