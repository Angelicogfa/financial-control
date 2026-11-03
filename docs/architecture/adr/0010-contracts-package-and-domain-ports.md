# ADR 0010 — Pacote `contracts` e portas do domínio

- **Status:** Aceito
- **Data:** 2026-11-01
- **Evolui:** ADR 0009 (os DTOs saem de `controllers/<ctx>/{requests,responses}`)
- **Fase:** 48.R1 ([REFACTORING_PLAN.md](../REFACTORING_PLAN.md))

## Contexto

O levantamento da Fase 48.R0 encontrou 29 módulos e 118 imports que quebravam o fluxo de camadas. Os principais:

- 25 módulos de `domain` importavam `controllers.*`: os use cases recebiam DTOs de request e devolviam DTOs de response do Pydantic, e o catálogo do MCP dependia deles;
- 10 módulos de `domain` importavam `infra.*`: `CachedMarketGateway`, `infra.providers.stored`/`batch` e `infra.data.health.DatabaseStatus`;
- `infra.mcp.server` importava providers de `controllers`, `infra.cache.job_lock` importava `worker.runner` e `core.helpers.units` importava `domain`.

O plano propunha read models em dataclass para todas as respostas. Seriam cerca de 224 classes espelhadas, com mapeadores no controller e no MCP: milhares de linhas novas para entregar o mesmo contrato.

## Decisão

1. **`apps/api/contracts/<ctx>/{requests,responses,serializers}.py`** guarda os schemas Pydantic e os serializadores entidade → schema. Controllers, use cases e MCP importam daí. `contracts` só importa `core`, `domain` e `contracts`, nunca FastAPI, `controllers`, `infra` ou `worker`. Os nomes das classes não mudaram, então o OpenAPI ficou idêntico, conferido pelo snapshot.
2. **Read models em dataclass só onde há forma nova**, como o `InstrumentView` da R2, e quando um handler for reescrito. Ficou registrado o desvio do §2.1 do plano: o domínio depende dos schemas, mas não da camada HTTP.
3. **Portas no domínio:** `domain/shared/gateways.py` define a `MarketDataGateway` (Protocol), que o `CachedMarketGateway` implementa, e `domain/shared/unit_of_work.py` define o `UoWFactory`. A leitura de mercado guardada (`stored`) e a busca em lote (`batch`) passaram para `domain/market/services/`. O registro de timeout do lote virou o método `report_fetch_timeout` da porta. `DatabaseStatus` foi para `domain/system/entities`.
4. **Raiz de composição:** `get_portfolio_service` mora em `composition.py`, que é usado pelos controllers e pelo MCP.
5. **Infra e core:** os locks de job passaram para `infra/cache/job_lock.py`, que o worker importa, e a conversão de unidades das séries foi para `domain/shared/units.py`.
6. **Contrato verificado por teste:** `tests/test_architecture_contracts.py`, com a allowlist vazia.

| Camada | Não pode importar |
|---|---|
| `core` | `contracts`, `domain`, `infra`, `controllers`, `worker` |
| `contracts` | `controllers`, `infra`, `worker`, `fastapi` |
| `domain` | `controllers`, `infra`, `worker`, `fastapi` |
| `controllers` | `infra.data`, `worker` (a infraestrutura chega por `composition.py`) |
| `infra` | `controllers`, `worker` |
| `worker` | `controllers` |

## Consequências

- A violação não volta: o teste falha no primeiro import proibido.
- `health.py` (1.660 linhas) virou o pacote `domain/portfolio/services/health/` (`model`, `common`, `diagnosis` e um módulo por pilar em `pillars/`), com a mesma API pública.
- Os testes que simulam o gateway implementam `report_fetch_timeout` quando exercitam o lote.
