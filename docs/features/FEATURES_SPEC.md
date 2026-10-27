# Especificação de Funcionalidades

Organizadas pelos contextos do menu (ADR 0005 e ADR 0007).

## Visão geral
- **Início (analytics):** manchete gerada dos números, patrimônio com variação sem aportes, resultado consolidado, rentabilidade 12 meses (TWR) contra o CDI, proventos 12 meses e reserva de emergência; alocação ARCA atual × meta com bandas; alertas acionáveis com dispensa; evolução base 100 (carteira, CDI, Ibovespa) e proventos por mês.
- **Desempenho:** base 100 por período contra CDI, Ibovespa, IFIX e S&P 500; retorno acumulado e anualizado, retorno real, volatilidade, Sharpe, Sortino, queda máxima, VaR e CVaR 95%; beta, excesso e correlação por referência; drawdown; resultado por classe ao lado da referência da classe.

## Operação
- **Carteira:** posições por classe ARCA com quantidade, preço médio e atual (cotação, curva, manual ou fallback sinalizado), valor, resultado consolidado (não realizado + realizado + proventos), peso atual × alvo na classe, situação no ciclo de vida e nota do checklist; filtro por conta; composição de cada classe.
- **Detalhe do ativo:** posição e risco; indicadores atuais e histórico anual de demonstrativos com ROE médio, CAGR de receita e lucro, anos com lucro e regularidade de proventos; valuation por perfil (Graham, Bazin, P/L, EV/EBITDA, P/VP justificado, spread de FIIs) com veredito e margem; checklist por perfil com respostas Sim/Não/Não se aplica, evidência, respostas automáticas e histórico da nota; aba **Tributação** (renda fixa: alíquota atual de cada aplicação, IOF ainda devido, data e dias até a próxima faixa, IR estimado resgatando hoje × na próxima faixa e ganho de esperar; renda variável: regime do tipo de ativo com alíquota e base legal); proventos e lançamentos.
- **Pesquisar:** screener do catálogo B3 (tipo, setor, texto, liquidez, valor de mercado, P/L, P/VP, DY, ROE, só classes abaixo da banda, esconder cadastrados) com veredito de valuation; ao observar um ativo, o usuário escolhe o quadrante ARCA (a sugestão pelo tipo vem marcada) e pode reclassificá-lo depois na lista de observação, que mostra classe, situação, checklist e margem; os demonstrativos anuais do ativo observado são buscados logo após o cadastro.
- **Aportar:** sugestão em dois níveis (classes abaixo da banda → ativos elegíveis pela estratégia da classe), quantidades inteiras na B3 e fracionárias no exterior, antes × depois por classe, execução editável e confirmação que registra as compras; planos salvos (rascunho, confirmado, descartado).
- **Lançamentos:** compras e vendas com taxas e câmbio, proventos (dividendo, JCP com IR, rendimento, cupom, restituição) e eventos corporativos (desdobramento, grupamento, bonificação com custo atribuído); toda alteração revalida o livro do ativo; importação das planilhas da B3 com pré-visualização, deduplicação e cadastro de ativos novos pelo mesmo caminho da Pesquisa (catálogo da B3, tipo e quadrante ARCA escolhidos na pré-visualização, demonstrativos buscados em seguida); um ticker de tipo desconhecido é cadastrado quando o tipo é escolhido.

## Ferramentas
- **Comparar renda fixa** (`/tools/fixed-income`): dois a seis títulos, informados à mão (% do CDI, CDI + taxa, IPCA + taxa ou prefixado, prazo, carência, isenção) ou escolhidos da carteira; projeção do valor bruto pelos cenários de juros das premissas da política (CDI e IPCA projetados ou de mercado, com variação para cima e para baixo); IR e IOF sobre o ganho acumulado no resgate; valor e taxa líquidos anualizados no vencimento e na janela comum (o menor prazo, com aviso de carência); taxa equivalente por faixa (`isento = tributado × (1 − alíquota)` e o inverso); ponto de empate em dias.

## Configuração
- **Estratégia:** metas e bandas ARCA, divisão interna (checklist, pesos manuais ou iguais), elegibilidade (nota e cobertura mínimas, checklist obrigatório ou não), premissas de valuation e de projeção (inclusive CDI/IPCA projetados e a variação dos cenários do comparador de renda fixa); cada alteração cria uma versão.
- **Contas:** corretoras, bancos e exchanges; todo lançamento pertence a uma conta.
- **Dados de mercado:** frescor de CDI, SELIC, IPCA e índices; última execução de cada rotina do worker.

## Renda fixa
CDB, LCI, LCA, CRI, CRA, debêntures, Tesouro Selic/IPCA+/Prefixado e contas remuneradas por indexador (`CDI`, `SELIC`, `IPCA`, `PRE`), com taxa contratada, aplicação, vencimento, isenção, IR regressivo, IOF, resgates proporcionais (FIFO), feriados nacionais e projeção em 252 dias úteis.

## Tributação
Alíquotas de IR e IOF são registros com vigência (tabela `tax_rules`, `GET /api/v1/tax/rules`): renda fixa regressiva (22,5% até 180 dias, 20% até 360, 17,5% até 720, 15% acima), isentos (LCI, LCA, CRI, CRA, debêntures incentivadas — a MP 1.303/2025 caducou e não mudou nada), IOF regressivo nos primeiros 29 dias, ações (15%, isenção de R$ 20 mil/mês), ETFs e BDRs (15%), FIIs (20% no ganho, rendimentos isentos), dividendos (10% acima de R$ 50 mil/mês desde 2026, Lei 15.270/2025), JCP (15% até 2025 e 17,5% desde 2026, LC 224/2025), exterior (15% anual, Lei 14.754/2023) e cripto. Cada evento usa a regra vigente na data do resgate, venda ou pagamento; uma mudança legal é um novo registro. MCP: `assets.tax_status`, `tools.fixed_income_compare` e `tools.tax_rules`.

## Operação da stack
- Produção: `docker compose -f docker-compose.prod.yml up -d --build` sobe Postgres, Redis, migrations, API, worker e web, publicando só o web. Desenvolvimento: `docker compose up -d --build` sobe a mesma stack e publica também Postgres, Redis e API em `127.0.0.1`. Os dois usam os mesmos volumes nomeados (`fincontrol_pgdata`, `fincontrol_redisdata`).
- Login único (Argon2 + JWT httpOnly); `/health` e `/ready`; logs JSON com `X-Request-ID`.
- `uv run python -m fincontrol_worker.seed_demo` preenche um banco **vazio** com dois anos de demonstração.
- Portão local: `scripts/check.sh` (`--fast`, `--smoke`, `--e2e`).
