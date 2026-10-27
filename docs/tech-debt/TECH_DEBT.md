# Registro de Débitos Técnicos e Evoluções Futuras

## Abertos

| ID | Título | Impacto | Plano de resolução |
|---|---|---|---|
| **TD-02** | Renda fixa marcada na curva (sem marcação a mercado do Tesouro) | Títulos IPCA+/Pré mostram o valor acumulado na curva contratada, que pode divergir do preço de venda antecipada no Tesouro Direto | Integrar os preços unitários diários do Tesouro Transparente como marcação a mercado opcional. |
| **TD-04** | Apuração mensal de IR (DARF) sobre vendas | O lucro realizado é consolidado, mas a isenção de R$ 20 mil/mês em ações e a compensação de prejuízos por categoria não são aplicadas | Módulo de apuração mensal de IR. |
| **TD-05** | Sem limite de tentativas no login | Ferramenta pessoal atrás de rede doméstica; um ataque de força bruta não é contido pela API | Limitar tentativas por IP no `/auth/login` (Redis) quando a stack for exposta fora da rede local. |
| **TD-06** | Provedores gratuitos limitados | Sem `BRAPI_TOKEN`, a brapi responde 429/401 para a maioria dos tickers e o Yahoo vira a fonte; indicadores do Yahoo às vezes vêm em escala inesperada (ex.: margem de holdings) | Configurar `BRAPI_TOKEN`; validar faixas plausíveis dos indicadores no adaptador e marcar dados suspeitos. |
| **TD-07** | Desempenho por classe sem TWR próprio | Desempenho compara o resultado consolidado de cada classe (desde o início) com a referência da classe no período escolhido. Desde a Fase 29, a Saúde da carteira mostra um TWR aproximado por classe com o valor e o custo gravados no retrato (a variação do custo faz as vezes do fluxo; proventos por classe ficam de fora) | Gravar o valor e o fluxo por classe no retrato diário e calcular o TWR por classe. |
| **TD-09** | Demonstrativos pós-cadastro sem fila durável | A API busca os demonstrativos de um ativo recém-cadastrado em `BackgroundTasks`: se o container reiniciar antes de terminar, a busca se perde até a rotina semanal do worker | Fila no Redis (API publica, worker consome) quando houver mais trabalho sob demanda. |
| **TD-10** | CI do GitHub sem execução | `.github/workflows/ci.yml` existe, mas os jobs não iniciam por falta de crédito de Actions na conta; a validação de cada PR é o `scripts/check.sh --smoke` local (e o hook de pre-push) | Regularizar o billing do GitHub Actions ou usar um runner self-hosted. |
| **TD-11** | Tipo `ImportNewAssetRequest` mantido à mão no frontend | Vai como JSON dentro de um campo multipart, então não entra no OpenAPI nem no `types.ts` gerado; mudar o schema no backend exige ajustar `endpoints.ts` | Publicar o schema em `components` do OpenAPI (modelo extra) para que `gen_web_types.py` o gere. |
| **TD-08** | Data ex dos eventos importados aproximada | A Movimentação da B3 traz a data do crédito das ações (dias após a data ex); negócios entre as duas datas podem ficar com a quantidade defasada | Cruzar com a agenda de eventos da B3 ou permitir ajustar a data ex na pré-visualização. |

## Encerrados

| ID | Título | Como foi resolvido |
|---|---|---|
| **TD-01** | Autenticação | Decisão: ferramenta pessoal de um usuário. Login com senha em Argon2 e JWT em cookie httpOnly SameSite=Strict (Fase 9); o limite de tentativas segue em TD-05. |
| **TD-03** | Eventos corporativos manuais | `corporate_events` com desdobramento, grupamento e bonificação aplicados por data no motor de posições, e importação pela Movimentação B3 (Fase 12). |
