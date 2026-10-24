"""Questionnaires for the optional Diagrama do Cerrado (Raul Sena / Investidor Sardinha).

Each question is answered with Yes (+1) or No (-1). Quantitative questions can be auto-evaluated
from market fundamentals; manual answers always take precedence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from fincontrol_core.domain.enums import AssetType
from fincontrol_core.market.models import Fundamentals

AutoRule = Callable[[Fundamentals], bool | None]


@dataclass(frozen=True)
class CerradoQuestion:
    """Single quality/risk question for a given asset type."""

    id: str
    text: str
    category: str
    hint: str = ""
    auto: AutoRule | None = field(default=None, compare=False)

    @property
    def automatable(self) -> bool:
        return self.auto is not None


def _gt(attr: str, threshold: float) -> AutoRule:
    def rule(f: Fundamentals) -> bool | None:
        value = getattr(f, attr)
        return None if value is None else value > threshold

    return rule


def _lt(attr: str, threshold: float, *, positive_only: bool = False) -> AutoRule:
    def rule(f: Fundamentals) -> bool | None:
        value = getattr(f, attr)
        if value is None:
            return None
        if positive_only and value <= 0:
            return False
        return value < threshold

    return rule


def _net_debt_ok(f: Fundamentals) -> bool | None:
    if f.net_debt_to_ebitda is not None:
        return f.net_debt_to_ebitda < 2.0
    if f.debt_to_equity is not None:
        return f.debt_to_equity < 1.0
    return None


STOCK_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion(
        "roe",
        "ROE historicamente acima de 5%?",
        "Rentabilidade",
        "Retorno sobre o patrimônio consistente.",
        _gt("return_on_equity", 0.05),
    ),
    CerradoQuestion(
        "debt",
        "Dívida controlada (Dív. Líq./EBITDA < 2 ou Dívida/PL < 1)?",
        "Endividamento",
        auto=_net_debt_ok,
    ),
    CerradoQuestion(
        "revenue_growth",
        "Receita cresceu nos últimos anos?",
        "Crescimento",
        auto=_gt("revenue_growth", 0.0),
    ),
    CerradoQuestion(
        "profitable",
        "Lucro consistente / margem líquida positiva?",
        "Crescimento",
        auto=_gt("profit_margin", 0.0),
    ),
    CerradoQuestion(
        "dividends",
        "Paga dividendos de forma consistente?",
        "Proventos",
        auto=_gt("dividend_yield", 0.0),
    ),
    CerradoQuestion("innovation", "Investe em pesquisa e inovação?", "Qualitativo"),
    CerradoQuestion("age_30y", "Tem mais de 30 anos de mercado?", "Perenidade"),
    CerradoQuestion("market_leader", "É líder ou referência no seu setor?", "Qualitativo"),
    CerradoQuestion(
        "perennial_sector", "O setor é perene (existe há mais de 100 anos)?", "Perenidade"
    ),
    CerradoQuestion(
        "governance", "Tem boa governança (Novo Mercado / Tag Along 100%)?", "Governança"
    ),
    CerradoQuestion(
        "no_state_control", "É livre de controle estatal / interferência política?", "Governança"
    ),
    CerradoQuestion(
        "liquidity",
        "Tem boa liquidez diária (> R$ 2 mi)?",
        "Liquidez",
        auto=_gt("avg_daily_volume", 2_000_000),
    ),
)

REAL_ESTATE_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("age_5y", "Tem mais de 5 anos de listagem?", "Perenidade"),
    CerradoQuestion(
        "pvp",
        "P/VP abaixo de 1,05 (sem ágio excessivo)?",
        "Valuation",
        auto=_lt("price_to_book", 1.05, positive_only=True),
    ),
    CerradoQuestion(
        "dy",
        "Dividend Yield acima de 6% a.a.?",
        "Proventos",
        auto=_gt("dividend_yield", 0.06),
    ),
    CerradoQuestion(
        "liquidity",
        "Liquidez diária acima de R$ 1 mi?",
        "Liquidez",
        auto=_gt("avg_daily_volume", 1_000_000),
    ),
    CerradoQuestion("vacancy", "Vacância física/financeira abaixo de 10%?", "Operacional"),
    CerradoQuestion("multi_property", "Possui portfólio multi-imóveis / multi-crédito?", "Risco"),
    CerradoQuestion(
        "tenant_diversification",
        "Inquilinos diversificados (nenhum > 30% da receita)?",
        "Diversificação",
    ),
    CerradoQuestion("prime_location", "Ativos bem localizados e de alto padrão?", "Qualitativo"),
    CerradoQuestion("long_contracts", "Contratos longos ou atípicos protegem a renda?", "Risco"),
    CerradoQuestion("management", "Gestora reconhecida e alinhada aos cotistas?", "Governança"),
)

INTERNATIONAL_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion(
        "roe", "ROE acima de 10%?", "Rentabilidade", auto=_gt("return_on_equity", 0.10)
    ),
    CerradoQuestion("debt", "Dívida controlada?", "Endividamento", auto=_net_debt_ok),
    CerradoQuestion(
        "revenue_growth", "Receita crescente?", "Crescimento", auto=_gt("revenue_growth", 0.0)
    ),
    CerradoQuestion(
        "profitable", "Margem líquida positiva?", "Crescimento", auto=_gt("profit_margin", 0.0)
    ),
    CerradoQuestion(
        "global_leader", "Líder global no setor ou ETF amplo de baixo custo?", "Qualitativo"
    ),
    CerradoQuestion("age_20y", "Mais de 20 anos de histórico comprovado?", "Perenidade"),
    CerradoQuestion("low_fee", "Se ETF: taxa de administração abaixo de 0,25% a.a.?", "Custo"),
    CerradoQuestion("moat", "Vantagem competitiva clara (moat)?", "Qualitativo"),
    CerradoQuestion(
        "market_cap",
        "Valor de mercado acima de US$ 10 bi?",
        "Tamanho",
        auto=_gt("market_cap", 10_000_000_000),
    ),
)

CRYPTO_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("top10", "Está entre as 10 maiores por valor de mercado?", "Tamanho"),
    CerradoQuestion("age_5y", "Existe há mais de 5 anos?", "Perenidade"),
    CerradoQuestion("decentralized", "Rede descentralizada e resiliente?", "Governança"),
    CerradoQuestion("real_adoption", "Possui caso de uso real e adoção institucional?", "Adoção"),
    CerradoQuestion("liquidity", "Alta liquidez global?", "Liquidez"),
)

CASH_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("guarantee", "Garantido pelo Tesouro Nacional ou FGC?", "Risco"),
    CerradoQuestion("liquidity", "Liquidez compatível com o objetivo?", "Liquidez"),
    CerradoQuestion("yield_benchmark", "Rende ao menos 100% do CDI ou IPCA+ atrativo?", "Retorno"),
    CerradoQuestion("solid_issuer", "Emissor sólido (rating elevado)?", "Risco"),
)

_QUESTIONS_BY_TYPE: dict[AssetType, tuple[CerradoQuestion, ...]] = {
    AssetType.STOCK_BR: STOCK_QUESTIONS,
    AssetType.ETF_BR: STOCK_QUESTIONS,
    AssetType.FII: REAL_ESTATE_QUESTIONS,
    AssetType.REIT: REAL_ESTATE_QUESTIONS,
    AssetType.BDR: INTERNATIONAL_QUESTIONS,
    AssetType.STOCK_INTL: INTERNATIONAL_QUESTIONS,
    AssetType.ETF_INTL: INTERNATIONAL_QUESTIONS,
    AssetType.CRYPTO: CRYPTO_QUESTIONS,
    AssetType.FIXED_INCOME: CASH_QUESTIONS,
    AssetType.TREASURY: CASH_QUESTIONS,
    AssetType.CASH: CASH_QUESTIONS,
}


def questions_for(asset_type: AssetType) -> tuple[CerradoQuestion, ...]:
    """Return the Diagrama do Cerrado questionnaire for a given asset type."""
    return _QUESTIONS_BY_TYPE[asset_type]
