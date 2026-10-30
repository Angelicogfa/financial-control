"""Phase 42.2: statements delivered to the CVM (DFP/ITR), point in time."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.disclosures.entities import IssuerTicker
from domain.disclosures.services.statements_sync import plan_files, sync_statements
from domain.disclosures.statements import (
    COMPANY,
    DEPRECIATION,
    DFP,
    DIVIDENDS_PAID,
    EQUITY,
    FINANCIAL,
    ITR,
    NET_INCOME,
    REVENUE,
    SHARES,
    AccountRow,
    StatementDoc,
    StatementFact,
    extract_facts,
    needed,
    point_in_time,
)
from domain.forecast.valuation_pit import valuation
from domain.market.entities import Quote
from domain.portfolio.services.service import PortfolioApplicationService
from infra.providers.cvm import parse_statements
from tests.conftest import offline_gateway
from worker.jobs import sync_cvm_statements_job

CNPJ = "84429695000111"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def _rows(doc: StatementDoc, accounts, start: date | None = date(2024, 1, 1), order="ÚLTIMO"):
    return [
        AccountRow(
            cnpj=doc.cnpj,
            reference_date=doc.reference_date,
            version=doc.version,
            order=order,
            period_start=start if code.startswith(("3", "6")) else None,
            period_end=doc.reference_date,
            code=code,
            name=name,
            value=value,
        )
        for code, name, value in accounts
    ]


COMPANY_ACCOUNTS = [
    ("1", "Ativo Total", 1000.0),
    ("1.01.01", "Caixa e Equivalentes de Caixa", 50.0),
    ("1.01.02", "Aplicações Financeiras", 30.0),
    ("2.01.04", "Empréstimos e Financiamentos", 100.0),
    ("2.02.01", "Empréstimos e Financiamentos", 200.0),
    ("2.03", "Patrimônio Líquido Consolidado", 600.0),
    ("2.03.09", "Participação dos Acionistas Não Controladores", 40.0),
    ("3.01", "Receita de Venda de Bens e/ou Serviços", 900.0),
    ("3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", 150.0),
    ("3.11", "Lucro/Prejuízo Consolidado do Período", 110.0),
    ("3.11.01", "Atribuído a Sócios da Empresa Controladora", 100.0),
    ("3.11.02", "Atribuído a Sócios Não Controladores", 10.0),
    ("6.01.01.02", "Depreciação e amortização", 40.0),
    ("6.01.01.05", "Amortização de custos de captação de empréstimos", 3.0),
    ("6.03.04", "Dividendos e juros sobre capital próprio pagos", -60.0),
    ("6.03.05", "Dividendos recebidos de controladas", 7.0),
]


# --- extraction ----------------------------------------------------------------------------


def test_company_statement_is_read_by_code_and_by_name() -> None:
    doc = StatementDoc(CNPJ, DFP, date(2024, 12, 31), 1, date(2025, 2, 26))
    facts = {f.metric: f for f in extract_facts(doc, "CON", _rows(doc, COMPANY_ACCOUNTS), 0.2)}
    assert facts[REVENUE].value == 900.0 and facts[REVENUE].template == COMPANY
    assert facts[NET_INCOME].value == 100.0  # the controlling shareholders' part
    assert facts[DEPRECIATION].value == 40.0  # financing costs are not depreciation
    assert facts[DIVIDENDS_PAID].value == 60.0  # paid, not received
    assert facts[EQUITY].value == 600.0 and facts[EQUITY].period_start is None
    assert facts[REVENUE].period_start == date(2024, 1, 1)
    # R$ 3,000 of equity per share: the count can only be in thousands.
    assert facts[SHARES].value == pytest.approx(200.0)


def test_bank_template_keeps_only_what_applies() -> None:
    doc = StatementDoc("60872504000123", DFP, date(2024, 12, 31), 1, date(2025, 2, 5))
    accounts = [
        ("1", "Ativo Total", 3000.0),
        ("2.03", "Provisões", 50.0),
        ("2.07", "Patrimônio Líquido Consolidado", 220.0),
        ("3.01", "Receitas da Intermediação Financeira", 300.0),
        ("3.09", "Lucro ou Prejuízo antes das Participações", 50.0),
        ("3.11", "Lucro ou Prejuízo Líquido Consolidado do Período", 41.0),
    ]
    facts = {f.metric: f for f in extract_facts(doc, "CON", _rows(doc, accounts))}
    assert facts[EQUITY].value == 220.0 and facts[EQUITY].template == FINANCIAL
    assert facts[NET_INCOME].value == 41.0
    assert REVENUE not in facts and "debt_current" not in facts


def test_quarter_rows_keep_the_year_to_date_and_ignore_comparatives() -> None:
    doc = StatementDoc(CNPJ, ITR, date(2024, 9, 30), 1, date(2024, 10, 30))
    rows = (
        _rows(doc, [("3.01", "Receita", 300.0)], start=date(2024, 7, 1))
        + _rows(doc, [("3.01", "Receita", 800.0)], start=date(2024, 1, 1))
        + _rows(doc, [("3.01", "Receita", 999.0)], start=date(2023, 1, 1), order="PENÚLTIMO")
    )
    facts = extract_facts(doc, "CON", rows)
    assert [(f.value, f.period_start) for f in facts if f.metric == REVENUE] == [
        (800.0, date(2024, 1, 1))
    ]


def test_needed_accounts() -> None:
    assert needed("1") and needed("2.03.09") and needed("6.01.01.02") and needed("6.03.04")
    assert not needed("3.04.02.01") and not needed("6.01.02.01") and not needed("6.02.01")


# --- point in time -------------------------------------------------------------------------


def _fact(doc_type, ref, version, delivered, value, start, metric=NET_INCOME):
    return StatementFact(
        CNPJ, doc_type, ref, version, delivered, "CON", COMPANY, metric, start, ref, value
    )


FACTS = [
    _fact(ITR, date(2023, 9, 30), 1, date(2023, 11, 1), 60.0, date(2023, 1, 1)),
    _fact(DFP, date(2023, 12, 31), 1, date(2024, 3, 1), 100.0, date(2023, 1, 1)),
    _fact(ITR, date(2024, 9, 30), 1, date(2024, 11, 1), 90.0, date(2024, 1, 1)),
    _fact(ITR, date(2024, 9, 30), 2, date(2024, 12, 1), 95.0, date(2024, 1, 1)),
    _fact(DFP, date(2023, 12, 31), 1, date(2024, 3, 1), 500.0, None, metric=EQUITY),
]


def test_point_in_time_sees_only_what_was_delivered() -> None:
    assert point_in_time(FACTS, date(2023, 10, 31)) is None
    year_end = point_in_time(FACTS, date(2024, 10, 1))
    assert year_end.reference_date == date(2023, 12, 31) and year_end.get(NET_INCOME) == 100.0
    assert year_end.get(EQUITY) == 500.0
    # Nine months of 2024 + the year 2023 - nine months of 2023.
    quarter = point_in_time(FACTS, date(2024, 11, 15))
    assert quarter.doc_type == ITR and quarter.version == 1
    assert quarter.get(NET_INCOME) == pytest.approx(90.0 + 100.0 - 60.0)
    restated = point_in_time(FACTS, date(2024, 12, 2))
    assert restated.version == 2 and restated.get(NET_INCOME) == pytest.approx(135.0)


def test_valuation_from_the_known_statement() -> None:
    doc = StatementDoc(CNPJ, DFP, date(2024, 12, 31), 1, date(2025, 2, 26))
    pit = point_in_time(
        extract_facts(doc, "CON", _rows(doc, COMPANY_ACCOUNTS), 10_000.0), date(2025, 3, 1)
    )
    found = valuation(pit, 0.12)  # 10 thousand shares: R$ 1,200 of market value
    assert found.market_cap == pytest.approx(1200.0)
    assert found.earnings_yield == pytest.approx(100.0 / 1200.0)
    assert found.dividend_yield == pytest.approx(60.0 / 1200.0)
    assert found.price_to_book == pytest.approx(1200.0 / (600.0 - 40.0))
    net_debt = 100.0 + 200.0 - 50.0 - 30.0
    assert found.ev_to_ebitda == pytest.approx((1200.0 + net_debt) / (150.0 + 40.0))
    assert valuation(pit, 0.0) is None


# --- the yearly archive --------------------------------------------------------------------

HEAD = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA"  # noqa: E501


def _line(cnpj, code, name, value, start="2024-01-01", basis_scale="MIL"):
    return f"{cnpj};2024-12-31;1;CIA;1;DF;REAL;{basis_scale};ÚLTIMO;{start};2024-12-31;{code};{name};{value};S"  # noqa: E501


def _archive() -> bytes:
    weg, other, holding = "84.429.695/0001-11", "11.111.111/0001-11", "22.222.222/0001-22"
    files = {
        "dfp_cia_aberta_2024.csv": "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC\n"  # noqa: E501
        f"{weg};2024-12-31;1;WEG;1;DFP;1;2025-02-26;x\n"
        f"{other};2024-12-31;1;OUTRA;2;DFP;2;2025-03-01;x\n"
        f"{holding};2024-12-31;1;HOLDING;3;DFP;3;2025-03-10;x\n",
        "dfp_cia_aberta_DRE_con_2024.csv": "\n".join(
            [HEAD, _line(weg, "3.01", "Receita", "37986.9"), _line(other, "3.01", "Receita", "1")]
        ),
        "dfp_cia_aberta_BPP_con_2024.csv": "\n".join(
            [HEAD, _line(weg, "2.03", "Patrimônio Líquido Consolidado", "23125.2", start="")]
        ),
        "dfp_cia_aberta_DRE_ind_2024.csv": "\n".join(
            [
                HEAD,
                _line(weg, "3.01", "Receita", "999"),  # consolidated wins
                _line(holding, "3.11", "Lucro/Prejuízo do Período", "5", basis_scale="UNIDADE"),
            ]
        ),
        "dfp_cia_aberta_composicao_capital_2024.csv": "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;QT_ACAO_PREF_CAP_INTEGR;QT_ACAO_TOTAL_CAP_INTEGR;QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO\n"  # noqa: E501
        f"{weg};2024-12-31;1;WEG;0;0;4196000000;0;0;462622\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("latin-1"))
    return buffer.getvalue()


def test_parse_the_yearly_archive() -> None:
    facts = parse_statements(_archive(), DFP, 2024, {CNPJ, "22222222000122"})
    weg = {f.metric: f for f in facts if f.cnpj == CNPJ}
    assert weg[REVENUE].value == pytest.approx(37_986_900.0) and weg[REVENUE].basis == "CON"
    assert weg[REVENUE].delivered_on == date(2025, 2, 26)
    assert weg[SHARES].value == 4196000000 - 462622
    holding = [f for f in facts if f.cnpj == "22222222000122"]
    assert [(f.metric, f.value, f.basis) for f in holding] == [(NET_INCOME, 5.0, "IND")]
    assert not [f for f in facts if f.cnpj == "11111111000111"]  # not wanted
    known = {(CNPJ, date(2024, 12, 31), 1)}
    assert {f.cnpj for f in parse_statements(_archive(), DFP, 2024, {CNPJ}, known)} == set()


# --- incremental load ----------------------------------------------------------------------


def test_plan_checks_recent_years_then_the_oldest_missing() -> None:
    plan = plan_files({("DFP", 2010)}, date(2026, 10, 30), first_year=2010)
    assert plan[:4] == [("DFP", 2026), ("ITR", 2026), ("DFP", 2025), ("ITR", 2025)]
    assert plan[4:6] == [("ITR", 2010), ("DFP", 2011)]
    assert ("DFP", 2010) not in plan


def _map(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        uow.cvm_issuers.replace_all([IssuerTicker("WEGE3", CNPJ, "WEG")])
        uow.commit()


def test_sync_loads_new_files_and_skips_unchanged_ones(api: SimpleNamespace) -> None:
    _map(api)
    calls: list[tuple[str, int]] = []

    def fetch(kind, year, cnpjs, known):
        calls.append((kind, year))
        assert cnpjs == {CNPJ}
        if (kind, year) != (DFP, 2025):
            return []
        doc = StatementDoc(CNPJ, DFP, date(2025, 12, 31), 1, date(2026, 2, 26))
        return (
            []
            if known
            else extract_facts(doc, "CON", _rows(doc, COMPANY_ACCOUNTS, start=date(2025, 1, 1)))
        )

    stamps = {(DFP, 2026): None}
    first = sync_statements(
        api.uow_factory,
        fetch_stamp=lambda k, y: stamps.get((k, y), "v1"),
        fetch_statements=fetch,
        today=date(2026, 10, 30),
        max_files=3,
    )
    assert calls == [(ITR, 2026), (DFP, 2025), (ITR, 2025)]  # the 2026 DFP does not exist yet
    assert first.facts > 0 and first.loaded[1].startswith("DFP 2025:")
    assert first.missing_years == 2 * (2024 - 2010 + 1)
    calls.clear()
    again = sync_statements(
        api.uow_factory,
        fetch_stamp=lambda k, y: stamps.get((k, y), "v1"),
        fetch_statements=fetch,
        today=date(2026, 10, 30),
        max_files=2,
    )
    assert again.unchanged == 3 and calls == [(DFP, 2010), (ITR, 2010)]


def test_sync_without_the_ticker_map_does_nothing(api: SimpleNamespace) -> None:
    result = sync_statements(
        api.uow_factory,
        fetch_stamp=lambda k, y: pytest.fail("no download without companies"),
        fetch_statements=lambda *a: pytest.fail("no download without companies"),
    )
    assert result.companies == 0


# --- API, MCP and the job ------------------------------------------------------------------


def _store(api: SimpleNamespace) -> None:
    doc = StatementDoc(CNPJ, DFP, date(2024, 12, 31), 1, date(2025, 2, 26))
    with api.uow_factory() as uow:
        uow.cvm_statements.add_many(
            extract_facts(doc, "CON", _rows(doc, COMPANY_ACCOUNTS), 10_000.0)
        )
        uow.market_data.save_quotes({"WEGE3": Quote(symbol="WEGE3", price=0.12)}, fetched_at=NOW)
        uow.commit()


def _asset(api: SimpleNamespace, ticker: str, asset_type: str = "STOCK_BR") -> int:
    return api.client.post(
        "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": asset_type}
    ).json()["id"]


def test_statements_through_the_api(api: SimpleNamespace) -> None:
    weg = _asset(api, "WEGE3")
    fii = _asset(api, "HGLG11", "FII")
    url = f"/api/v1/assets/{weg}/statements"
    assert api.client.get(f"/api/v1/assets/{fii}/statements").json()["status"] == "NOT_A_COMPANY"
    assert api.client.get(url).json()["status"] == "NOT_MAPPED"
    _map(api)
    assert api.client.get(url).json()["status"] == "NOT_LOADED"
    _store(api)
    data = api.client.get(url).json()
    assert data["status"] == "OK" and data["template"] == "COMPANY"
    first = data["deliveries"][0]
    assert first["delivered_on"] == "2025-02-26" and first["net_income"] == 100.0
    assert first["ebitda"] == 190.0 and first["net_debt"] == 220.0 and first["equity"] == 560.0
    assert data["valuation"]["price_to_book"] == pytest.approx(1200.0 / 560.0)
    assert api.client.get("/api/v1/assets/999/statements").status_code == 404


def test_statements_mcp(api: SimpleNamespace) -> None:
    weg = _asset(api, "WEGE3")
    _map(api)
    _store(api)
    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    op = CATALOG_BY_NAME["assets.statements"]
    assert op.kind == "query"
    assert op.invoke(handlers, op.input_model(asset_id=weg)).deliveries[0].revenue == 900.0


def test_sync_job_uses_the_gateway(api: SimpleNamespace) -> None:
    _map(api)
    gateway = offline_gateway()
    gateway.get_cvm_statement_stamp = lambda kind, year, **kw: "v1" if year == 2024 else None
    gateway.get_cvm_statements = lambda kind, year, cnpjs, known, **kw: []
    details = sync_cvm_statements_job(api.uow_factory, gateway, as_of_date=date(2025, 6, 1))
    assert details["companies"] == 1 and details["loaded"] == ["DFP 2024: 0", "ITR 2024: 0"]
