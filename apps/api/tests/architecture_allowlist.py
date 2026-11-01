"""Layer violations that predate the import contract (Phase 48.R0).

This list can only shrink: Phase 48.R1 removes each entry as it fixes the import
(`test_architecture_contracts.py`). Never add an entry; fix the import instead.
"""

from __future__ import annotations

ALLOWED_VIOLATIONS: dict[str, frozenset[str]] = {
    # domain -> controllers (DTOs) and domain -> infra (providers, data)
    "domain.accounts.services.use_cases": frozenset(
        {
            "controllers.accounts.requests",
            "controllers.accounts.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.agentic.services.catalog": frozenset(
        {
            "controllers.accounts.requests",
            "controllers.accounts.responses",
            "controllers.alerts.requests",
            "controllers.alerts.responses",
            "controllers.assets.requests",
            "controllers.assets.responses",
            "controllers.contributions.requests",
            "controllers.contributions.responses",
            "controllers.disclosures.requests",
            "controllers.disclosures.responses",
            "controllers.ledger.requests",
            "controllers.ledger.responses",
            "controllers.market.responses",
            "controllers.policy.requests",
            "controllers.policy.responses",
            "controllers.portfolio.requests",
            "controllers.portfolio.responses",
            "controllers.recommendation.responses",
            "controllers.research.requests",
            "controllers.research.responses",
            "controllers.shared.dependencies",
            "controllers.shared.responses",
            "controllers.simulation.requests",
            "controllers.simulation.responses",
            "controllers.tax.requests",
            "controllers.tax.responses",
            "infra.providers.stored",
        }
    ),
    "domain.agentic.services.use_cases": frozenset(
        {
            "controllers.agentic.requests",
            "controllers.agentic.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.alerts.services.use_cases": frozenset(
        {
            "controllers.alerts.requests",
            "controllers.alerts.responses",
            "controllers.shared.dependencies",
            "infra.providers.stored",
        }
    ),
    "domain.assets.services.use_cases": frozenset(
        {
            "controllers.assets.requests",
            "controllers.assets.responses",
            "controllers.assets.serializers",
            "controllers.shared.dependencies",
            "controllers.shared.responses",
            "controllers.shared.serializers",
        }
    ),
    "domain.auth.services.use_cases": frozenset(
        {
            "controllers.auth.requests",
        }
    ),
    "domain.contributions.services.use_cases": frozenset(
        {
            "controllers.contributions.requests",
            "controllers.contributions.responses",
            "controllers.portfolio.requests",
            "controllers.portfolio.serializers",
            "controllers.shared.dependencies",
            "infra.providers.stored",
        }
    ),
    "domain.disclosures.services.statements_view": frozenset(
        {
            "controllers.disclosures.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.disclosures.services.use_cases": frozenset(
        {
            "controllers.disclosures.requests",
            "controllers.disclosures.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.forecast.services": frozenset(
        {
            "controllers.assets.responses",
            "controllers.shared.dependencies",
            "infra.providers.stored",
        }
    ),
    "domain.ledger.services.use_cases.b3_import": frozenset(
        {
            "controllers.ledger.requests",
            "controllers.ledger.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.ledger.services.use_cases.corporate_events": frozenset(
        {
            "controllers.ledger.requests",
            "controllers.ledger.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.ledger.services.use_cases.earnings": frozenset(
        {
            "controllers.ledger.requests",
            "controllers.ledger.responses",
            "controllers.ledger.serializers",
            "controllers.shared.dependencies",
            "controllers.shared.responses",
            "controllers.shared.serializers",
        }
    ),
    "domain.ledger.services.use_cases.transactions": frozenset(
        {
            "controllers.ledger.requests",
            "controllers.ledger.responses",
            "controllers.ledger.serializers",
            "controllers.shared.dependencies",
            "controllers.shared.responses",
            "controllers.shared.serializers",
        }
    ),
    "domain.market.services.use_cases": frozenset(
        {
            "controllers.market.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.mining.services": frozenset(
        {
            "controllers.research.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.policy.services.use_cases": frozenset(
        {
            "controllers.policy.requests",
            "controllers.policy.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.portfolio.services.service": frozenset(
        {
            "infra.providers.gateway",
            "infra.providers.stored",
        }
    ),
    "domain.portfolio.services.use_cases": frozenset(
        {
            "controllers.portfolio.requests",
            "controllers.portfolio.responses",
            "controllers.portfolio.serializers",
            "controllers.shared.dependencies",
        }
    ),
    "domain.recommendation.services": frozenset(
        {
            "controllers.recommendation.responses",
            "controllers.shared.dependencies",
        }
    ),
    "domain.research.services.service": frozenset(
        {
            "controllers.shared.dependencies",
            "infra.providers.gateway",
        }
    ),
    "domain.research.services.use_cases": frozenset(
        {
            "controllers.research.requests",
            "controllers.research.responses",
            "controllers.research.serializers",
            "controllers.shared.dependencies",
            "infra.providers.stored",
        }
    ),
    "domain.simulation.services.studies": frozenset(
        {
            "controllers.shared.dependencies",
            "controllers.simulation.requests",
            "controllers.simulation.responses",
        }
    ),
    "domain.simulation.services.use_cases": frozenset(
        {
            "controllers.shared.dependencies",
            "controllers.simulation.requests",
            "controllers.simulation.responses",
            "infra.providers.stored",
        }
    ),
    "domain.system.services.use_cases": frozenset(
        {
            "controllers.system.responses",
            "infra.data.health",
            "infra.providers.gateway",
        }
    ),
    "domain.tax.services.use_cases": frozenset(
        {
            "controllers.shared.dependencies",
            "controllers.tax.requests",
            "controllers.tax.responses",
            "controllers.tax.serializers",
            "infra.providers.stored",
        }
    ),
    # infra -> worker (job lock re-export) and infra -> controllers (MCP reuses API dependencies)
    "infra.cache.job_lock": frozenset(
        {
            "worker.runner",
        }
    ),
    "infra.mcp.server": frozenset(
        {
            "controllers.portfolio.dependencies",
            "controllers.shared.dependencies",
        }
    ),
    # core -> domain (unit helpers use domain entities)
    "core.helpers.units": frozenset(
        {
            "domain.shared.entities",
            "domain.shared.enums",
        }
    ),
}
