# ADR 0002 — Alocação ARCA e Diagrama do Cerrado Opcional

- **Status:** Aceito
- **Data:** 2026-10-24

## Contexto
A estratégia principal da carteira segue a metodologia **ARCA** (Ações, Real Estate, Caixa, Ativos Internacionais) para macroalocação e rebalanceamento via novos aportes. Para a escolha de ativos dentro de cada classe, o **Diagrama do Cerrado** (Raul Sena) oferece um sistema de perguntas de risco/qualidade (+1 / -1), porém o investidor não deve ser obrigado a preencher o questionário de todos os ativos para operar a carteira ou simular aportes.

## Decisão
1. **Macroalocação ARCA obrigatória**: todo ativo pertence a uma das 4 classes (`ACOES`, `REAL_ESTATE`, `CAIXA`, `ATIVOS_INTERNACIONAIS`), com sugestão automática pelo `AssetType` e possibilidade de override pelo usuário.
2. **Diagrama do Cerrado opcional**:
   - Cada ativo possui a flag `use_cerrado` (default `true` para renda variável, mas desativável) e o campo opcional `custom_class_weight`.
   - Na distribuição de aportes intra-classe (Nível 2), o motor suporta três estratégias (`IntraClassStrategy`):
     - `CERRADO`: usa os pesos proporcionais às notas positivas ($\max(\text{score}, 0)$). Se parte das perguntas tiver regra automática (ROE, P/VP, DY, Dívida, Liquidez), o sistema pré-avalia com dados dos provedores.
     - `MANUAL_WEIGHT`: usa os pesos definidos manualmente pelo usuário.
     - `EQUAL_WEIGHT`: divide igualmente entre os ativos elegíveis da classe (usado também como fallback automático quando nenhum ativo possui nota positiva no Cerrado).

## Consequências
- **Positivas:** O investidor pode cadastrar rapidamente sua carteira e simular aportes imediatamente sem bloqueio, adotando o questionário do Cerrado de forma progressiva onde fizer sentido.
