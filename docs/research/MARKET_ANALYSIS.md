# Análise de Mercado, Falhas da Dinâmica Atual e Features Futuras (sem custo)

*Data: 2026-10-27. Escopo: ferramentas brasileiras de análise e controle de carteira comparadas ao Financial Control.*

> Nota de método: o que se afirma sobre concorrentes vem das fontes no fim do documento e do material público de cada empresa (em geral marketing). Os detalhes do Diagrama do Cerrado e do "Método Burro" da AUVP não estão bem indexados na web; a descrição abaixo é a de conhecimento comum dos alunos e deve ser conferida na plataforma.

## 1. Panorama do mercado

O mercado se divide em quatro grupos, e quase nenhum produto cobre mais de dois:

| Grupo | Exemplos | O que entregam | Modelo |
|---|---|---|---|
| **Dados e screener** | AUVP Analítica, Status Invest, Investidor10, Fundamentus | Indicadores, histórico de demonstrativos, rankings, comparador | Freemium / assinatura |
| **Consolidação de carteira** | Kinvo, Gorila, Investidor10 Carteira, Trademap | Integração B3/Open Finance, rentabilidade, proventos | Freemium / assinatura (integração B3 costuma ser paga) |
| **Imposto de renda** | myProfit, planilhas DLP, calculadora ReVar (B3 + Receita) | Apuração mensal, DARF, compensação de prejuízo | Assinatura (ReVar é grátis) |
| **Método / rebalanceamento** | Diagrama do Cerrado (AUVP), planilhas de cursos | Nota por ativo, peso ideal, aporte que rebalanceia | Exclusivo para alunos |

### AUVP em detalhe
- **AUVP Analítica:** base de dados fundamentalista (ações, stocks, FIIs, FIAGROs, REITs, ETFs, renda fixa, índices), comparador de até 5 ativos com indicadores escolhidos em cinco grupos (valuation, endividamento, eficiência, rentabilidade, crescimento), rankings e "selo de viabilidade". Dados de CVM e Morningstar. Comparador exclusivo para assinantes.
- **Diagrama do Cerrado:** ferramenta de rebalanceamento separada, só para alunos. Perguntas Sim/Não por ativo geram uma nota; a nota define o peso ideal dentro da classe; o aporte vai para quem está mais abaixo do ideal ("nunca vender para rebalancear").
- **Ponto fraco estrutural:** são produtos separados. A Analítica não conhece a carteira do aluno, e o Diagrama não lê os dados da Analítica: o aluno copia números e responde perguntas à mão.

### Dores recorrentes do mercado
- **Sincronização frágil com B3/corretoras** (Kinvo: reclamações de 2026 sobre plataforma legada que não sincroniza e histórico anterior a 2026 ausente no Open Finance).
- **Cobrança e cancelamento** (Investidor10: grande volume de reclamações sobre renovação após cancelamento).
- **Paywall sobre o básico** (integração B3, comparador, preço médio com taxas).
- **Dados presos ao fornecedor:** sem exportação completa, migrar de app perde histórico.
- **Método desconectado dos números:** ninguém junta screener + checklist + metas por classe + aporte + ledger num fluxo só.

## 2. Posição do Financial Control

Pontos onde o projeto **já está à frente** do mercado:

1. **Fluxo integrado:** Pesquisar → classificar no quadrante ARCA → checklist do Cerrado com respostas automáticas → elegibilidade → aporte em dois níveis → confirmação que vira lançamento. A AUVP precisa de dois produtos e cópia manual para isso.
2. **Política versionada:** metas, bandas, elegibilidade e premissas de valuation com histórico. Nenhum concorrente oferece.
3. **Renda fixa pela curva contratada** com IR regressivo, IOF e feriados, coisa que consolidadores fazem mal ou só via integração.
4. **Métricas de risco** (Sharpe, Sortino, VaR/CVaR, beta, drawdown), em geral exclusivas de planos pagos.
5. **Dados próprios e auto-hospedados:** sem assinatura, sem risco de "plataforma legada", backup em `pg_dump`.
6. **Servidor MCP:** um agente opera a carteira com as mesmas regras da UI. O Gorila lançou algo parecido (Gorila AI) como produto pago.
7. **Honestidade de dado:** fallback sinalizado em vez de número inventado.

Desvantagens estruturais (aceitáveis para uso pessoal): sem integração automática com a B3 (importação de planilha), dependência de provedores gratuitos e uso só no desktop.

## 3. Falhas e riscos na dinâmica atual

Ordenadas por impacto na decisão de investimento.

### 3.1 Imposto de renda é o maior buraco (TD-04)
O lucro realizado é consolidado, mas não há apuração mensal, isenção de R$ 20 mil em ações, separação swing/day trade/FII, compensação de prejuízo por categoria nem DARF. Dois agravantes:
- **Ativos internacionais** (um quadrante inteiro do ARCA): desde a Lei 14.754/2023 os ganhos e proventos no exterior são apurados **anualmente** a 15%, com regras próprias de câmbio. Sem isso, o retorno líquido do quadrante "I" fica superestimado.
- **Aporte "nunca vender"** é eficiente em imposto, mas quando o usuário vende (ciclo de vida do ativo) a ferramenta não mostra o custo fiscal da venda antes da decisão.

### 3.2 O checklist envelhece em silêncio
A nota do Cerrado define o peso do ativo, mas respostas manuais não têm validade. Um "Sim" de 2 anos atrás pesa igual a um de ontem. Quando chega um demonstrativo novo, as respostas automáticas são recalculadas, mas as manuais não são reabertas para revisão. Resultado: o aporte pode seguir uma tese vencida.

### 3.3 Valuation sensível a dado ruim
- Graham, Bazin e P/VP dependem de LPA, VPA e DY de provedores gratuitos (TD-06). Um dividendo extraordinário infla o DY de 12 meses e o teto Bazin; uma escala errada do Yahoo distorce margens.
- O veredito é pontual: não há faixa de sensibilidade nem aviso quando o indicador está fora de uma faixa plausível ou diverge entre brapi e Yahoo.
- O alerta `PRICE_BELOW_CEILING` herda esse risco: um teto inflado gera um "sinal de compra" falso.

### 3.4 Proventos e eventos com datas aproximadas (TD-08)
A data ex vem da data de crédito; não existe agenda de **proventos anunciados** (data com / pagamento). O usuário não vê a renda futura já declarada nem consegue planejar o aporte em torno da data com.

### 3.5 Renda fixa só na curva (TD-02)
Tesouro IPCA+/Prefixado aparece pelo valor da curva, que pode diferir muito do preço de resgate antecipado. Isso distorce o peso do quadrante **Caixa** e, portanto, a sugestão de aporte (a classe pode parecer acima ou abaixo da banda sem estar).

### 3.6 Desempenho por classe sem TWR (TD-07)
Comparar o resultado consolidado da classe desde o início com o benchmark do período escolhido mistura janelas. Não dá para saber se o quadrante "A" bateu o Ibovespa no último ano.

### 3.7 Aporte: arredondamento e resíduo
Quantidades inteiras na B3 deixam resíduo quando o aporte é pequeno ou o lote caro. O mercado fracionário (ticker com `F`) permite comprar unidades, e o resíduo poderia ir para o próximo ativo da fila ou para o Caixa, de forma explícita.

### 3.8 Alertas sem canal externo
Os alertas (fora da banda, preço abaixo do teto, série velha, job falho) só aparecem quando o usuário abre o app. Para uma ferramenta de aporte mensal, o alerta que importa (classe fora da banda, preço abaixo do teto) chega tarde.

### 3.9 Operação e segurança
- Backup é manual (`pg_dump` no README); um volume perdido apaga todo o histórico.
- CI não roda (TD-10); a validação depende do hook local.
- Sem limite de tentativas de login (TD-05) e sem 2FA, o que pesa se a stack for exposta para uso fora de casa.

## 4. Features futuras sem custo

Todas usam fontes públicas gratuitas, bibliotecas open source ou a infraestrutura que já existe (Postgres, Redis, worker).

### Prioridade alta (resolvem falhas da seção 3)

| # | Feature | Fonte gratuita / como | Resolve |
|---|---|---|---|
| F1 | **Apuração de IR mensal + DARF** (ações, FII, day trade, isenção de R$ 20 mil, compensação de prejuízo) e **apuração anual do exterior** (Lei 14.754) | Regras da Receita; dados já estão no ledger; câmbio PTAX do BCB (SGS/Olinda, grátis) | 3.1 |
| F2 | **Relatório anual para a declaração** (Bens e Direitos com código, rendimentos isentos e exclusivos por CNPJ fonte) | Ledger + cadastro CVM (dados abertos) para CNPJ | 3.1 |
| F3 | **Custo fiscal na tela de venda** ("vender isto gera R$ X de IR; em ações cabe na isenção deste mês") | Reaproveita F1 | 3.1 |
| F4 | **Validade das respostas do checklist**: cada resposta manual expira em N meses (configurável na política) e o ativo entra em revisão; reabrir automaticamente quando chega demonstrativo novo | Já existe `ASSET_IN_REVIEW` | 3.2 |
| F5 | **Sanidade dos dados**: faixas plausíveis por indicador, comparação brapi × Yahoo, DY sem extraordinários (mediana de 3–5 anos no Bazin), selo "dado suspeito" no veredito | Dados que já chegam | 3.3 |
| F6 | **Marcação a mercado do Tesouro** (opcional, ao lado da curva) | Preços e taxas diários do Tesouro Transparente (CSV, já existe `tesouro.py`) | 3.5 |
| F7 | **Agenda de proventos anunciados** (data com, pagamento, valor) e renda futura projetada | brapi (dividendos), dados abertos CVM / B3 | 3.4 |
| F8 | **Notificações externas** dos alertas | Bot do Telegram (grátis), ntfy.sh auto-hospedado ou e-mail SMTP de conta pessoal; disparo pelo worker | 3.8 |
| F9 | **Backup automático** diário com rotação (pg_dump no worker para pasta montada) e restauração testada no `check.sh --smoke` | Ferramentas já presentes | 3.9 |

### Prioridade média (diferenciais frente à AUVP e consolidadores)

| # | Feature | Como |
|---|---|---|
| F10 | **Comparador lado a lado** de até 5 ativos com indicadores escolhidos (o que a AUVP cobra) e destaque de quem passa no checklist/valuation | Dados de demonstrativos já armazenados |
| F11 | **Diário de tese por ativo**: por que comprei, gatilhos de venda, preço/nota de revisão; exibido na revisão do checklist e na venda | Tabela nova, sem dependência externa |
| F12 | **Fatos relevantes e comunicados** dos ativos da carteira e da watchlist | Dados abertos CVM (IPE/ENET), coleta no worker |
| F13 | **TWR por classe** (gravar valor e fluxo por classe no retrato diário) | TD-07 |
| F14 | **Fracionário e destino do resíduo** no aporte | Lógica no domínio de contribuições |
| F15 | **Projeção de independência financeira**: patrimônio e renda passiva futuros com as premissas de projeção que já existem na política, cenários pessimista/base/otimista e "aporte necessário para a meta" | Matemática local; Monte Carlo opcional com retornos históricos já gravados |
| F16 | **Vencimentos e eventos de renda fixa** no calendário (vencimento, cupom, fim da carência de IR) | Contratos já cadastrados |
| F17 | **Rentabilidade e custos por conta/corretora** (taxas, corretagem, custódia acumuladas) | Ledger |

### Prioridade baixa (conforto e alcance)

| # | Feature | Como |
|---|---|---|
| F18 | **PWA** (instalável no celular, leitura offline do último retrato) | `vite-plugin-pwa` |
| F19 | **Acesso remoto seguro** sem expor portas | Tailscale (plano pessoal gratuito) ou Cloudflare Tunnel; junto com TD-05 e TOTP (2FA) via `pyotp` |
| F20 | **Exportação completa** (CSV/JSON do ledger, política e checklists) | Garantia de saída, oposto do lock-in do mercado |
| F21 | **Backtest da estratégia**: "se eu tivesse aportado pelo ARCA desde X", comparado com aporte igual em Ibovespa/CDI | Séries já gravadas |
| F22 | **Rotinas do agente MCP** (revisão mensal guiada: alertas, checklists vencidos, sugestão de aporte, IR do mês) | Prompts/skills sobre o MCP existente |
| F23 | **Runner self-hosted** para o CI (TD-10) | GitHub Actions self-hosted runner é gratuito |

## 5. Sugestão de sequência

1. **F9 (backup)** — protege tudo o que vem depois; pequeno.
2. **F1 + F2 + F3 (IR)** — maior lacuna funcional e o único motivo comum para pagar outra ferramenta (myProfit).
3. **F4 + F5 (checklist e sanidade)** — tornam a sugestão de aporte confiável, que é o núcleo do método.
4. **F6 + F7 + F8** — fecham as distorções de peso (Tesouro) e fazem os alertas chegarem a tempo.
5. Diferenciais (F10–F17) conforme uso.

> **Substituída pela seção 6**, que registra as prioridades definidas pelo usuário em 2026-10-27.

## 6. Prioridades definidas (2026-10-27)

Ordem de execução e fase correspondente no [plano de implementação](../todo/IMPLEMENTATION_PLAN.md):

| Ordem | Prioridade | Itens do relatório | Fase |
|---|---|---|---|
| 1 | Tabela regressiva de IR por ativo | parte de F1/F3, renda fixa | 24 |
| 2 | Comparação de rentabilidade teórica: título tributado × isento | novo | 24 |
| 3 | Confiabilidade do checklist e dos dados | F4 + F5 | 25 |
| 4 | Tesouro a mercado, agenda de proventos e alertas **só dentro do sistema** | F6 + F7 (F8 sem canal externo) | 26 |
| 5 | Comparador de ativos | F10 | 27 |
| 6 | Fatos relevantes pelos dados abertos da CVM | F12 | 28 |
| 7 | Estatísticas e saúde da carteira | seção 7 | 29 |

Ficam fora por ora: apuração mensal completa e DARF (F1/F2), notificações externas (F8), backup automático (F9) e os demais itens das seções 4.

### 6.1 Regras tributárias vigentes (base para as fases 24 e 29)

Verificado em outubro de 2026:
- **A MP 1.303/2025 caducou em 08/10/2025.** Nenhuma das mudanças entrou em vigor: não há alíquota única de 17,5% e LCI/LCA seguem isentas para pessoa física. Muitos guias desatualizados ainda dizem o contrário.
- **Tabela regressiva da renda fixa** (sobre o rendimento): 22,5% até 180 dias; 20% de 181 a 360; 17,5% de 361 a 720; 15% acima de 720. Já implementada em `regressive_ir_rate` (`domain/portfolio/services/fixed_income.py`).
- **IOF regressivo** nos primeiros 29 dias (já implementado).
- **Isentos para PF:** LCI, LCA, CRI, CRA, debêntures incentivadas, rendimentos de FII que cumprem os requisitos legais.
- **JCP:** IR retido passou de 15% para 17,5% em 2026 (conferir na Lei 15.270/2025 antes de implementar).
- **IRPFM (Lei 15.270/2025):** adicional para renda total acima de R$ 600 mil/ano; fora do escopo de uma ferramenta de carteira, mas vale citar na tela de tributação.
- **Exterior (Lei 14.754/2023):** 15% sobre ganhos e rendimentos, apuração anual.

Decisão de projeto: as alíquotas passam a ser **dados com vigência** (início/fim), não constantes soltas, para que uma mudança legal vire um novo registro e não um retrabalho do motor.

### 6.2 Comparação tributado × isento

A equivalência que o mercado usa (e que os simuladores dos bancos mostram de forma incompleta):

- Taxa isenta equivalente a uma tributada: `taxa_isenta = taxa_bruta × (1 − alíquota(prazo))`.
- Taxa bruta necessária para empatar com uma isenta: `taxa_bruta = taxa_isenta / (1 − alíquota(prazo))`.

Essa conta simples erra em três pontos, que a ferramenta deve tratar:
1. **A alíquota incide sobre o rendimento acumulado, não sobre a taxa anual.** Para prazos longos e prefixados/IPCA+, o certo é projetar o valor final bruto, aplicar o IR sobre o ganho e comparar valores líquidos no vencimento.
2. **Prazo e carência diferentes:** LCI/LCA têm carência mínima; comparar um CDB de liquidez diária com uma LCA de 2 anos exige a mesma janela.
3. **Indexadores diferentes:** % do CDI × CDI + spread × IPCA+ × prefixado. A projeção usa as premissas de projeção da política (CDI e IPCA esperados), com cenários.

Saída: valor líquido no vencimento, taxa líquida anualizada, ponto de empate (a partir de quantos dias o tributado passa a ganhar, considerando a queda da faixa) e a tabela de equivalência por faixa.

## 7. Estatísticas e saúde da carteira: métodos e frameworks

### 7.1 O que já existe
`domain/portfolio/services/analytics.py` já calcula TWR, CAGR, retorno real, volatilidade anualizada, Sharpe, Sortino, drawdown e queda máxima, Calmar, VaR histórico e paramétrico, CVaR, beta/alfa, correlação e matriz de correlação. O que falta é **diagnóstico**: transformar números em "está saudável ou não, por quê e o que fazer".

### 7.2 Métodos mais usados (mercado e literatura)

**Concentração e diversificação**
- **HHI** (soma dos quadrados dos pesos) por ativo, setor, emissor e quadrante. Normalizado vai de 0 (pesos iguais) a 1 (um único ativo).
- **Número efetivo de ativos** = 1 / HHI. Uma carteira de 25 ativos com HHI 0,10 se comporta como 10 ativos iguais.
- **Peso do maior ativo e dos 5/10 maiores.**
- **Índice de diversificação de Choueifaty:** média ponderada das volatilidades ÷ volatilidade da carteira. Vale 1 para um ativo só e √N para N ativos independentes; DR² estima o número de fatores de risco independentes.
- **Número efetivo de apostas (ENB, Meucci):** exponencial da entropia da distribuição de risco entre fatores não correlacionados; vai de 1 a N. Estudos indicam que carteiras com mais apostas independentes sofrem menos em mercados de baixa.
- **Score composto da Morningstar:** combina log do número de ativos, peso dos 10 maiores, HHI por ativo, setor e indústria e o índice de diversificação em três blocos de peso igual (ativo, setor, retorno). Serve de modelo para um score de concentração.

**Risco**
- **Contribuição ao risco por ativo/classe (decomposição de Euler):** `RC_i = w_i × (Σw)_i / σ_p`; a soma das contribuições é a volatilidade total. Mostra que um quadrante com 25% do peso pode carregar 60% do risco. É a base do *risk parity*.
- **Drawdown atual, duração do drawdown e tempo de recuperação.**
- **Ulcer Index** (profundidade e duração das quedas) e **Ulcer Performance Index**.
- **Teste de estresse histórico:** aplicar os retornos de crises (ex.: maio/2017, março/2020) aos pesos atuais.

**Desempenho ajustado**
- **Tracking error** e **Information Ratio** contra o benchmark da classe (IR > 0,5 é bom; > 1,0 excelente).
- **Omega ratio** (adequado a retornos assimétricos; > 1 bom).
- **Retornos e Sharpe em janelas móveis de 12 meses**, e **consistência** (% de meses acima do CDI).

**Saúde fundamental dos ativos** (complementa o checklist)
- **Piotroski F-score** (0–9, força financeira), **Altman Z''-score** (versão para mercados emergentes e não industriais; zonas de risco de insolvência), **Beneish M-score** (sinal de manipulação contábil; > −1,78 merece atenção). Um estudo com empresas da Borsa İstanbul (mercado emergente) encontrou o Z-score e o M-score entre os determinantes do F-score. Dependem de linhas de balanço que precisam ser checadas nos demonstrativos já coletados; o M-score exige contas a receber e outras linhas que nem sempre vêm dos provedores gratuitos.

**Cuidados estatísticos** (onde ferramentas de varejo costumam errar)
- **Janela mínima:** não exibir Sharpe, beta ou correlação com menos de ~60 observações; mostrar "dados insuficientes".
- **Covariância com encolhimento (Ledoit-Wolf)** quando há muitos ativos e pouco histórico; a matriz amostral é ruidosa e infla a diversificação aparente.
- **Intervalo de confiança** para Sharpe e retorno (bootstrap), para não tratar diferença de ruído como sinal.
- **Retornos mensais para métricas de longo prazo** e diários só para VaR, evitando misturar frequências.

### 7.3 Frameworks de "saúde da carteira"
Não há um padrão único. Os mais citados combinam: Morningstar Portfolio X-Ray (exposição por classe, setor, região e sobreposição de ativos), o score de concentração da Morningstar, a declaração de política de investimento do CFA Institute (IPS: aderência a metas, restrições e limites) e checagens práticas de planejadores (reserva de emergência, liquidez, limite do FGC, custos, eficiência tributária).

Proposta para o Financial Control: **sete pilares**, cada um com checagens que retornam *ok / atenção / crítico*, uma explicação e a ação sugerida. Os limites ficam na **política versionada**, como as bandas ARCA.

| Pilar | Checagens |
|---|---|
| 1. Aderência à política | desvio de cada quadrante × banda, tempo fora da banda, ativos fora da elegibilidade ainda com peso |
| 2. Concentração | maior ativo, top 5, HHI e número efetivo por ativo/setor/emissor, **exposição por instituição acima do limite do FGC (R$ 250 mil)** |
| 3. Diversificação de risco | índice de Choueifaty, contribuição ao risco por quadrante × peso, pares com correlação > 0,8 |
| 4. Risco | volatilidade × perfil, drawdown atual e duração, VaR/CVaR, estresse histórico |
| 5. Desempenho | TWR × benchmark por classe, tracking error, IR, consistência e Sharpe em janela móvel, retorno real |
| 6. Qualidade dos ativos | nota média ponderada do checklist, % do peso com checklist vencido, F-score/Z''-score, dados suspeitos |
| 7. Liquidez, renda e tributos | reserva em meses de custo, % com liquidez em até D+2, vencimentos em 12 meses, renda passiva, % isento, lotes perto de mudar de faixa de IR |

O resultado geral **não é uma média**: o pilar em pior estado aparece primeiro, para que um "crítico" não seja diluído por seis "ok".

## Fontes

- [AUVP Analítica — comparador de FIIs](https://analitica.auvp.com.br/fiis/comparar)
- [AUVP — escola e ecossistema](https://www.auvp.com.br/) · [Termos AUVP News (Diagrama do Cerrado / Método Burro)](https://auvpnews.com.br/termos-de-uso)
- [AUVP11: ETF de ações por fundamentos](https://renovainvest.com.br/blog/auvp11-etf-acoes-fundamentos/)
- [Investidor10 — ferramentas de controle de investimento 2026](https://investidor10.com.br/conteudo/ferramentas-controle-de-investimento/)
- [Gorila AI](https://gorila.com.br/blog/investidor-podera-perguntar-como-warren-buffet-criticaria-minha-carteira/) · [InfoMoney sobre Gorila AI](https://www.infomoney.com.br/advisor/essa-ia-le-sua-carteira-e-aponta-falhas-como-warren-buffett-faria/)
- [myProfit (loja de apps)](https://mwm.ai/apps/myprofit/1528398229)
- [B3 — ferramentas gratuitas para o IR 2026 (ReVar)](https://borainvestir.b3.com.br/noticias/imposto-de-renda/ir-2026-conheca-ferramentas-disponiveis-na-b3-que-te-ajudam-a-fazer-a-declaracao-de-imposto-de-renda/)
- [Reclame Aqui — Kinvo](https://www.reclameaqui.com.br/empresa/kinvo/lista-reclamacoes/) · [Kinvo: integrações e histórico](https://www.reclameaqui.com.br/kinvo/problemas-com-integracoes-e-historico-de-investimentos-na-kinvo-solicitacao-de-estorno_7DCjctLaP6Oz7WBj/)
- [Reclame Aqui — Investidor10](https://www.reclameaqui.com.br/empresa/investidor10/lista-reclamacoes)
- [InfoMoney — MP 1.303 cai no Congresso](https://www.infomoney.com.br/minhas-financas/mp-1-303-cai-no-congresso-veja-como-fica-a-tributacao-dos-investimentos-agora/) · [Daycoval — MP 1.303 não aprovada](https://blog.daycoval.com.br/mp-1303/) · [Meelion — tabela regressiva 2026](https://www.meelion.com/blog/educacao-financeira/tabela-regressiva-ir-renda-fixa-prazos-e-2026/) · [ValorFinal — guia IR investimentos 2026](https://valorfinal.com.br/guia/imposto-de-renda-sobre-investimentos)
- [CVM Dados Abertos — IPE](https://dados.cvm.gov.br/dataset/groups/cia_aberta-doc-ipe) · [Diretório de arquivos IPE](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/) · [Inventário de bases da CVM](https://dados.cvm.gov.br/misc/InventarioBasesCVM.pdf)
- [Morningstar — score de concentração](https://www.morningstar.com/business/insights/blog/concentrated-equity-funds) · [Risk Without Return (HHI normalizado, risk parity)](https://arxiv.org/pdf/1307.0114)
- [Portfolio Optimizer — Diversification Ratio](https://portfoliooptimizer.io/blog/the-diversification-ratio-measuring-portfolio-diversification) · [Portfolio Optimizer — Effective Number of Bets](https://portfoliooptimizer.io/blog/the-effective-number-of-bets-measuring-portfolio-diversification/)
- [PortfolioMetrics — métricas ajustadas a risco (Omega, UPI, IR)](https://portfoliometrics.net/blog/risk-adjusted-metrics)
- [Determinantes do Piotroski F-score (Borsa İstanbul)](https://acikerisim.balikesir.edu.tr/xmlui/handle/20.500.12462/16614) · [Piotroski × Altman](https://fffinstill.com/learning/comparisons/piotroski-vs-altman)
- Débitos internos: [TECH_DEBT.md](../tech-debt/TECH_DEBT.md)
