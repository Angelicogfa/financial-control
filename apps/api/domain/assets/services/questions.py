"""Fundamentalist checklists (Diagrama do Cerrado, version 2) by instrument profile (item 11.3).

Each question is answered YES (+1), NO (-1) or NA (does not apply). Quantitative questions are
auto-evaluated with evidence, preferring the multi-year statement history (item 11.2) over
point-in-time indicators; manual answers always take precedence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from domain.assets.services.history import HistoricalMetrics
from domain.market.entities import Fundamentals
from domain.shared.enums import AssetType, ChecklistProfile, default_checklist_profile

CHECKLIST_VERSION = 2
# Fewer fiscal years than this and history-based rules fall back to TTM indicators.
MIN_HISTORY_YEARS = 3


@dataclass(frozen=True)
class EvidenceContext:
    """Data available to auto-evaluate questions."""

    fundamentals: Fundamentals | None = None
    history: HistoricalMetrics | None = None

    @property
    def has_history(self) -> bool:
        return self.history is not None and self.history.years >= MIN_HISTORY_YEARS


@dataclass(frozen=True)
class AutoAnswer:
    value: bool
    evidence: str


AutoRule = Callable[[EvidenceContext], AutoAnswer | None]


@dataclass(frozen=True)
class CerradoQuestion:
    """Single quality/risk question of a checklist profile."""

    id: str
    text: str
    category: str
    hint: str = ""
    auto: AutoRule | None = field(default=None, compare=False)

    @property
    def automatable(self) -> bool:
        return self.auto is not None


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%".replace(".", ",")


def _money(value: float) -> str:
    for scale, suffix in ((1e9, "bi"), (1e6, "mi")):
        if abs(value) >= scale:
            return f"{value / scale:.1f} {suffix}".replace(".", ",")
    return f"{value:,.0f}".replace(",", ".")


def _years(history: HistoricalMetrics) -> str:
    return f"{history.years} anos ({history.first_year}-{history.last_year})"


def _fund_gt(attr: str, threshold: float, label: str, fmt: Callable[[float], str]) -> AutoRule:
    def rule(ctx: EvidenceContext) -> AutoAnswer | None:
        value = getattr(ctx.fundamentals, attr, None) if ctx.fundamentals else None
        if value is None:
            return None
        sign = ">" if value > threshold else "<="
        return AutoAnswer(value > threshold, f"{label} {fmt(value)} {sign} {fmt(threshold)}")

    return rule


def _fund_lt(attr: str, threshold: float, label: str, fmt: Callable[[float], str]) -> AutoRule:
    def rule(ctx: EvidenceContext) -> AutoAnswer | None:
        value = getattr(ctx.fundamentals, attr, None) if ctx.fundamentals else None
        if value is None:
            return None
        ok = 0 < value < threshold
        return AutoAnswer(ok, f"{label} {fmt(value)} {'<' if ok else '>='} {fmt(threshold)}")

    return rule


def _ratio(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _roe_above(threshold: float) -> AutoRule:
    def rule(ctx: EvidenceContext) -> AutoAnswer | None:
        if ctx.has_history and ctx.history and ctx.history.roe_average is not None:
            roe = ctx.history.roe_average
            return AutoAnswer(roe > threshold, f"ROE médio {_pct(roe)} em {_years(ctx.history)}")
        return _fund_gt("return_on_equity", threshold, "ROE TTM", _pct)(ctx)

    return rule


def _revenue_growth(ctx: EvidenceContext) -> AutoAnswer | None:
    if ctx.has_history and ctx.history and ctx.history.revenue_cagr is not None:
        cagr = ctx.history.revenue_cagr
        return AutoAnswer(cagr > 0, f"CAGR da receita {_pct(cagr)} em {_years(ctx.history)}")
    return _fund_gt("revenue_growth", 0.0, "Crescimento da receita (12m)", _pct)(ctx)


def _earnings_growth(ctx: EvidenceContext) -> AutoAnswer | None:
    if ctx.has_history and ctx.history and ctx.history.earnings_cagr is not None:
        cagr = ctx.history.earnings_cagr
        return AutoAnswer(cagr > 0, f"CAGR do lucro {_pct(cagr)} em {_years(ctx.history)}")
    return _fund_gt("earnings_growth", 0.0, "Crescimento do lucro (12m)", _pct)(ctx)


def _profitable(ctx: EvidenceContext) -> AutoAnswer | None:
    if ctx.has_history and ctx.history:
        h = ctx.history
        return AutoAnswer(h.always_profitable, f"Lucro em {h.profitable_years} de {h.years} anos")
    return _fund_gt("profit_margin", 0.0, "Margem líquida TTM", _pct)(ctx)


def _dividends(ctx: EvidenceContext) -> AutoAnswer | None:
    if ctx.has_history and ctx.history:
        h = ctx.history
        regular = (h.dividend_regularity or 0.0) >= 0.8
        return AutoAnswer(regular, f"Proventos em {h.dividend_years} de {h.years} anos")
    return _fund_gt("dividend_yield", 0.0, "Dividend yield 12m", _pct)(ctx)


def _net_debt_ok(ctx: EvidenceContext) -> AutoAnswer | None:
    f = ctx.fundamentals
    if f is None:
        return None
    if f.net_debt_to_ebitda is not None:
        ok = f.net_debt_to_ebitda < 2.0
        return AutoAnswer(ok, f"Dív. Líq./EBITDA {_ratio(f.net_debt_to_ebitda)}")
    if f.debt_to_equity is not None:
        ok = f.debt_to_equity < 1.0
        return AutoAnswer(ok, f"Dívida/PL {_ratio(f.debt_to_equity)}")
    return None


def _volume_above(threshold: float) -> AutoRule:
    return _fund_gt("avg_daily_volume", threshold, "Volume financeiro médio", _money)


STOCK_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion(
        "roe",
        "ROE historicamente acima de 5%?",
        "Rentabilidade",
        "Média dos últimos anos; sem histórico usa o ROE TTM.",
        _roe_above(0.05),
    ),
    CerradoQuestion(
        "debt",
        "Dívida controlada (Dív. Líq./EBITDA < 2 ou Dívida/PL < 1)?",
        "Endividamento",
        auto=_net_debt_ok,
    ),
    CerradoQuestion(
        "revenue_growth", "Receita cresceu nos últimos anos?", "Crescimento", auto=_revenue_growth
    ),
    CerradoQuestion(
        "profitable", "Lucro em todos os anos analisados?", "Crescimento", auto=_profitable
    ),
    CerradoQuestion(
        "dividends", "Paga dividendos de forma consistente?", "Proventos", auto=_dividends
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
        "liquidity", "Tem boa liquidez diária (> R$ 2 mi)?", "Liquidez", auto=_volume_above(2e6)
    ),
)

BANK_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion(
        "roe",
        "ROE historicamente acima de 10%?",
        "Rentabilidade",
        "Bancos operam alavancados; o ROE mínimo é maior que o de empresas.",
        _roe_above(0.10),
    ),
    CerradoQuestion(
        "profitable", "Lucro em todos os anos analisados?", "Crescimento", auto=_profitable
    ),
    CerradoQuestion(
        "earnings_growth", "Lucro cresceu nos últimos anos?", "Crescimento", auto=_earnings_growth
    ),
    CerradoQuestion(
        "dividends", "Paga dividendos de forma consistente?", "Proventos", auto=_dividends
    ),
    CerradoQuestion("basel", "Índice de Basileia acima de 11%?", "Solvência"),
    CerradoQuestion("npl", "Inadimplência (NPL 90) controlada e estável?", "Risco"),
    CerradoQuestion("age_30y", "Tem mais de 30 anos de mercado?", "Perenidade"),
    CerradoQuestion("market_leader", "É líder ou referência no seu segmento?", "Qualitativo"),
    CerradoQuestion(
        "governance", "Tem boa governança (Novo Mercado / Tag Along 100%)?", "Governança"
    ),
    CerradoQuestion(
        "no_state_control", "É livre de controle estatal / interferência política?", "Governança"
    ),
    CerradoQuestion(
        "liquidity", "Tem boa liquidez diária (> R$ 2 mi)?", "Liquidez", auto=_volume_above(2e6)
    ),
)

FII_BRICK_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("age_5y", "Tem mais de 5 anos de listagem?", "Perenidade"),
    CerradoQuestion(
        "pvp",
        "P/VP abaixo de 1,05 (sem ágio excessivo)?",
        "Valuation",
        auto=_fund_lt("price_to_book", 1.05, "P/VP", _ratio),
    ),
    CerradoQuestion(
        "dy",
        "Dividend Yield acima de 6% a.a.?",
        "Proventos",
        auto=_fund_gt("dividend_yield", 0.06, "Dividend yield 12m", _pct),
    ),
    CerradoQuestion(
        "liquidity", "Liquidez diária acima de R$ 1 mi?", "Liquidez", auto=_volume_above(1e6)
    ),
    CerradoQuestion("vacancy", "Vacância física/financeira abaixo de 10%?", "Operacional"),
    CerradoQuestion("multi_property", "Possui portfólio multi-imóveis?", "Risco"),
    CerradoQuestion(
        "tenant_diversification",
        "Inquilinos diversificados (nenhum > 30% da receita)?",
        "Diversificação",
    ),
    CerradoQuestion("prime_location", "Ativos bem localizados e de alto padrão?", "Qualitativo"),
    CerradoQuestion("long_contracts", "Contratos longos ou atípicos protegem a renda?", "Risco"),
    CerradoQuestion("management", "Gestora reconhecida e alinhada aos cotistas?", "Governança"),
)

FII_PAPER_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("age_5y", "Tem mais de 5 anos de listagem?", "Perenidade"),
    CerradoQuestion(
        "pvp",
        "P/VP abaixo de 1,02?",
        "Valuation",
        "Fundos de papel valem perto do patrimônio; ágio raramente se justifica.",
        _fund_lt("price_to_book", 1.02, "P/VP", _ratio),
    ),
    CerradoQuestion(
        "dy",
        "Dividend Yield acima de 9% a.a.?",
        "Proventos",
        auto=_fund_gt("dividend_yield", 0.09, "Dividend yield 12m", _pct),
    ),
    CerradoQuestion(
        "liquidity", "Liquidez diária acima de R$ 1 mi?", "Liquidez", auto=_volume_above(1e6)
    ),
    CerradoQuestion("high_grade", "Carteira majoritariamente high grade?", "Crédito"),
    CerradoQuestion("guarantees", "Garantias robustas (alienação fiduciária, cessão)?", "Crédito"),
    CerradoQuestion("debtor_concentration", "Nenhum devedor acima de 15% do PL?", "Risco"),
    CerradoQuestion("ltv", "LTV médio das operações abaixo de 70%?", "Crédito"),
    CerradoQuestion("indexers", "Indexadores coerentes com o objetivo (IPCA/CDI)?", "Risco"),
    CerradoQuestion("management", "Gestora reconhecida e alinhada aos cotistas?", "Governança"),
)

ETF_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("low_fee", "Taxa de administração abaixo de 0,25% a.a.?", "Custo"),
    CerradoQuestion("broad_index", "Replica um índice amplo e diversificado?", "Diversificação"),
    CerradoQuestion("tracking", "Baixo erro de aderência ao índice?", "Qualidade"),
    CerradoQuestion("age_5y", "Tem mais de 5 anos de histórico?", "Perenidade"),
    CerradoQuestion("solid_manager", "Gestora grande e reconhecida?", "Governança"),
    CerradoQuestion(
        "liquidity", "Liquidez diária acima de R$ 1 mi?", "Liquidez", auto=_volume_above(1e6)
    ),
)

INTL_STOCK_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion(
        "roe", "ROE historicamente acima de 10%?", "Rentabilidade", auto=_roe_above(0.10)
    ),
    CerradoQuestion("debt", "Dívida controlada?", "Endividamento", auto=_net_debt_ok),
    CerradoQuestion("revenue_growth", "Receita crescente?", "Crescimento", auto=_revenue_growth),
    CerradoQuestion(
        "profitable", "Lucro em todos os anos analisados?", "Crescimento", auto=_profitable
    ),
    CerradoQuestion("global_leader", "Líder global no setor?", "Qualitativo"),
    CerradoQuestion("age_20y", "Mais de 20 anos de histórico comprovado?", "Perenidade"),
    CerradoQuestion("moat", "Vantagem competitiva clara (moat)?", "Qualitativo"),
    CerradoQuestion(
        "market_cap",
        "Valor de mercado acima de US$ 10 bi?",
        "Tamanho",
        auto=_fund_gt("market_cap", 10e9, "Valor de mercado", _money),
    ),
)

CRYPTO_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("top10", "Está entre as 10 maiores por valor de mercado?", "Tamanho"),
    CerradoQuestion("age_5y", "Existe há mais de 5 anos?", "Perenidade"),
    CerradoQuestion("decentralized", "Rede descentralizada e resiliente?", "Governança"),
    CerradoQuestion("real_adoption", "Possui caso de uso real e adoção institucional?", "Adoção"),
    CerradoQuestion("liquidity", "Alta liquidez global?", "Liquidez"),
)

FIXED_INCOME_QUESTIONS: tuple[CerradoQuestion, ...] = (
    CerradoQuestion("guarantee", "Garantido pelo Tesouro Nacional ou FGC?", "Risco"),
    CerradoQuestion("liquidity", "Liquidez compatível com o objetivo?", "Liquidez"),
    CerradoQuestion("yield_benchmark", "Rende ao menos 100% do CDI ou IPCA+ atrativo?", "Retorno"),
    CerradoQuestion("solid_issuer", "Emissor sólido (rating elevado)?", "Risco"),
)

QUESTIONS_BY_PROFILE: dict[ChecklistProfile, tuple[CerradoQuestion, ...]] = {
    ChecklistProfile.STOCK: STOCK_QUESTIONS,
    ChecklistProfile.BANK: BANK_QUESTIONS,
    ChecklistProfile.FII_BRICK: FII_BRICK_QUESTIONS,
    ChecklistProfile.FII_PAPER: FII_PAPER_QUESTIONS,
    ChecklistProfile.ETF: ETF_QUESTIONS,
    ChecklistProfile.INTL_STOCK: INTL_STOCK_QUESTIONS,
    ChecklistProfile.CRYPTO: CRYPTO_QUESTIONS,
    ChecklistProfile.FIXED_INCOME: FIXED_INCOME_QUESTIONS,
}

# Profiles whose checklist uses yearly statements (the worker stores them weekly).
STATEMENT_PROFILES = frozenset(
    {ChecklistProfile.STOCK, ChecklistProfile.BANK, ChecklistProfile.INTL_STOCK}
)


def resolve_profile(profile_or_type: ChecklistProfile | AssetType) -> ChecklistProfile:
    if isinstance(profile_or_type, ChecklistProfile):
        return profile_or_type
    return default_checklist_profile(AssetType(profile_or_type))


def questions_for(profile_or_type: ChecklistProfile | AssetType) -> tuple[CerradoQuestion, ...]:
    """Questionnaire of a checklist profile (or of the asset type's default profile)."""
    return QUESTIONS_BY_PROFILE[resolve_profile(profile_or_type)]
