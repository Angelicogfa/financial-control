# Registro de Débitos Técnicos e Evoluções Futuras

| ID | Título | Impacto no MVP | Plano de Resolução |
|---|---|---|---|
| **TD-01** | Autenticação apenas single-user (resolvido parcialmente na Fase 9: login Argon2 + JWT em cookie) | Um único usuário configurado no `.env`; sem multiusuário nem limite de tentativas de login | Adicionar tabela `users`, isolamento por `user_id` e rate limiting no login. |
| **TD-02** | Marcação de Renda Fixa na curva (sem marcação a mercado secundária do Tesouro) | Títulos IPCA+/Pré mostram o valor acumulado contratado na curva, que pode divergir do preço de venda antecipada no Tesouro Direto | Integrar planilha/API de preços unitários diários do Tesouro Transparente para marcação a mercado opcional. |
| **TD-03** | Eventos corporativos manuais (grupamentos, desdobramentos, bonificações) | Exigem lançamento de ajuste manual pelo usuário | Criar entidade `corporate_events` com fator de ajuste automático sobre transações históricas. |
| **TD-04** | Apuração fiscal de DARF mensal sobre vendas | O sistema consolida o lucro realizado, mas não aplica automaticamente as regras de isenção de R$ 20 mil/mês em ações nem compensação de prejuízos por categoria | Implementar módulo de apuração de IR mensal no Pós-MVP. |
