"""Phase 28: relevant facts and notices from the CVM open data (IPE + FCA)."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from domain.agentic.services.catalog import CATALOG_BY_NAME, AgenticRuntimeHandlers
from domain.alerts.services.evaluator import AlertKind, relevant_fact_alerts
from domain.disclosures.entities import CvmDocument, IssuerTicker, normalize_cnpj
from domain.disclosures.services.sync import base_ticker, merge_tickers, sync_documents
from domain.portfolio.services.service import PortfolioApplicationService
from infra.providers import error_tracker
from infra.providers.cvm import CvmOpenDataProvider, parse_fca_tickers, parse_ipe
from tests.conftest import offline_gateway
from worker.jobs import sync_cvm_documents_job

TODAY = date.today()
WEG = "84429695000111"
BB = "00000000000191"

IPE_HEADER = (
    "CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;"
    "Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download"
)
FCA_HEADER = (
    "CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;Valor_Mobiliario;"
    "Sigla_Classe_Acao_Preferencial;Classe_Acao_Preferencial;Codigo_Negociacao;"
    "Composicao_BDR_Unit;Mercado;Sigla_Entidade_Administradora;Entidade_Administradora;"
    "Data_Inicio_Negociacao;Data_Fim_Negociacao;Segmento;Data_Inicio_Listagem;Data_Fim_Listagem"
)


def _ipe_row(cnpj: str, name: str, category: str, delivered: date, protocol: str, **kw: str) -> str:
    return ";".join(
        [
            cnpj,
            name,
            kw.get("code", "1"),
            kw.get("reference", delivered.isoformat()),
            category,
            kw.get("doc_type", ""),
            kw.get("species", ""),
            kw.get("subject", "Assunto"),
            delivered.isoformat(),
            "AP - Apresentação",
            protocol,
            kw.get("version", "1"),
            f"https://www.rad.cvm.gov.br/ENET/doc?p={protocol}",
        ]
    )


def _fca_row(cnpj: str, ticker: str, reference: str = "2026-01-01", name: str = "WEG S.A.") -> str:
    return (
        f"{cnpj};{reference};1;1;{name};Ações Ordinárias;;;{ticker};;Bolsa;B3;B3 S.A.;"
        "2007-06-22;;Novo Mercado;2007-06-22;"
    )


def _zip(member: str, lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, "\r\n".join(lines).encode("latin-1"))
    return buffer.getvalue()


# --- parsers and provider ------------------------------------------------------------------------


def test_parse_ipe_keeps_the_fields_and_skips_incomplete_rows() -> None:
    text = "\n".join(
        [
            IPE_HEADER,
            _ipe_row(
                "84.429.695/0001-11",
                "WEG S.A.",
                "Fato Relevante",
                date(2026, 3, 2),
                "P1",
                subject="Aquisição de controle",
                version="2",
            ),
            _ipe_row("", "SEM CNPJ", "Fato Relevante", date(2026, 3, 2), "P2"),
            _ipe_row("84.429.695/0001-11", "WEG S.A.", "Fato Relevante", date(2026, 3, 2), ""),
        ]
    )
    docs = parse_ipe(text)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.cnpj == WEG and doc.category == "Fato Relevante" and doc.version == 2
    assert doc.subject == "Aquisição de controle" and doc.delivery_date == date(2026, 3, 2)
    assert doc.link.endswith("p=P1") and doc.is_relevant_fact


def test_parse_fca_keeps_the_newest_cnpj_of_each_ticker() -> None:
    text = "\n".join(
        [
            FCA_HEADER,
            _fca_row("11.111.111/0001-11", "ABCD3", "2024-01-01", "ANTIGA"),
            _fca_row("22.222.222/0001-22", "ABCD3", "2026-01-01", "NOVA"),
            _fca_row("84.429.695/0001-11", "WEGE3"),
            _fca_row("84.429.695/0001-11", ""),
        ]
    )
    tickers = {t.ticker: t for t in parse_fca_tickers(text)}
    assert set(tickers) == {"ABCD3", "WEGE3"}
    assert tickers["ABCD3"].cnpj == "22222222000122" and tickers["ABCD3"].company_name == "NOVA"


def test_provider_reads_the_zip_and_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    ipe = _zip(
        "ipe_cia_aberta_2026.csv",
        [
            IPE_HEADER,
            _ipe_row("84.429.695/0001-11", "WEG S.A.", "Fato Relevante", date(2026, 1, 5), "P1"),
        ],
    )
    fca = _zip(
        "fca_cia_aberta_valor_mobiliario_2026.csv",
        [FCA_HEADER, _fca_row("84.429.695/0001-11", "WEGE3")],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("ipe_cia_aberta_2026.zip"):
            return httpx.Response(200, content=ipe)
        if path.endswith("fca_cia_aberta_2026.zip"):
            return httpx.Response(200, content=fca)
        if path.endswith("ipe_cia_aberta_2025.zip"):
            return httpx.Response(200, content=b"<html>manutencao</html>")
        return httpx.Response(500)

    reported: list[str] = []
    monkeypatch.setattr(
        "infra.providers.cvm.report_provider_error",
        lambda **kw: reported.append(f"{kw['operation']}:{kw['target']}"),
    )
    provider = CvmOpenDataProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [d.protocol for d in provider.documents(2026)] == ["P1"]
    assert [t.ticker for t in provider.issuer_tickers(2026)] == ["WEGE3"]
    assert provider.documents(2025) == []  # an error page instead of the archive
    assert provider.documents(2024) == []  # HTTP 500
    assert reported == ["ipe:2025", "ipe:2024"]
    assert error_tracker is not None


def test_helpers() -> None:
    assert normalize_cnpj("84.429.695/0001-11") == WEG
    assert base_ticker("petr4f") == "PETR4" and base_ticker("WEGE3") == "WEGE3"
    assert base_ticker("BOVA11") == "BOVA11"
    old = IssuerTicker("WEGE3", "1", "OLD", date(2024, 1, 1))
    new = IssuerTicker("WEGE3", WEG, "WEG", date(2026, 1, 1))
    assert merge_tickers([[new], [old]]) == [new]


# --- sync, persistence and feed ----------------------------------------------------------------


def _doc(cnpj: str, category: str, days_ago: int, protocol: str, **kw: object) -> CvmDocument:
    return CvmDocument(
        protocol=protocol,
        cnpj=cnpj,
        company_name="WEG S.A." if cnpj == WEG else "BANCO DO BRASIL",
        category=category,
        delivery_date=TODAY - timedelta(days=days_ago),
        subject=str(kw.get("subject", f"Documento {protocol}")),
        version=int(kw.get("version", 1)),  # type: ignore[arg-type]
        link=f"https://cvm/{protocol}",
    )


DOCS = [
    _doc(WEG, "Fato Relevante", 1, "W1", subject="Aquisição"),
    _doc(WEG, "Comunicado ao Mercado", 3, "W2"),
    _doc(WEG, "Assembleia", 40, "W3"),
    _doc(BB, "Fato Relevante", 2, "B1"),  # not followed: never stored
]
MAP = [IssuerTicker("WEGE3", WEG, "WEG S.A.", date(2026, 1, 1)), IssuerTicker("BBAS3", BB, "BB")]


def _seed_assets(api: SimpleNamespace) -> dict[str, int]:
    ids = {}
    for ticker, kind in (("WEGE3", "STOCK_BR"), ("XPML11", "FII"), ("ITSA4", "STOCK_BR")):
        body = api.client.post(
            "/api/v1/assets", json={"ticker": ticker, "name": ticker, "asset_type": kind}
        ).json()
        ids[ticker] = body["id"]
    return ids


def _sync(api: SimpleNamespace, docs: list[CvmDocument] = DOCS, tickers=MAP):  # noqa: ANN001, ANN202
    years: list[int] = []

    def fetch_documents(year: int) -> list[CvmDocument]:
        years.append(year)
        return docs if year == TODAY.year else []

    result = sync_documents(
        api.uow_factory, fetch_tickers=lambda _y: list(tickers), fetch_documents=fetch_documents
    )
    return result, years


def test_sync_keeps_only_followed_companies_and_is_idempotent(api: SimpleNamespace) -> None:
    _seed_assets(api)
    result, years = _sync(api)
    assert result.companies == 2  # WEGE3 and ITSA4; the FII has no IPE filings
    assert result.mapped == 1 and result.unmapped == ["ITSA4"]
    assert years == [TODAY.year, TODAY.year - 1]  # first run also reads last year
    assert result.documents == 3 and result.new == 3

    again, years = _sync(api)
    assert again.new == 0 and (years == [TODAY.year] or TODAY.month == 1)

    # A new version of a protocol replaces it without losing the read mark.
    feed = api.client.get("/api/v1/disclosures").json()
    first = next(i for i in feed["items"] if i["protocol"] == "W1")
    api.client.post("/api/v1/disclosures/read", json={"ids": [first["id"]]})
    revised = [
        *DOCS[1:],
        _doc(WEG, "Fato Relevante", 1, "W1", subject="Aquisição (ret.)", version=2),
    ]
    _sync(api, revised)
    item = next(
        i for i in api.client.get("/api/v1/disclosures").json()["items"] if i["protocol"] == "W1"
    )
    assert item["subject"] == "Aquisição (ret.)" and item["version"] == 2 and item["read"] is True


def test_a_failed_ticker_map_keeps_the_stored_one(api: SimpleNamespace) -> None:
    _seed_assets(api)
    _sync(api)
    result, _ = _sync(api, tickers=[])
    assert result.mapped == 1  # WEGE3 still maps from the stored FCA


def test_feed_filters_and_mark_read(api: SimpleNamespace) -> None:
    ids = _seed_assets(api)
    _sync(api)
    feed = api.client.get("/api/v1/disclosures").json()
    assert [i["protocol"] for i in feed["items"]] == ["W1", "W2", "W3"]
    assert feed["items"][0]["tickers"] == ["WEGE3"] and feed["unread_count"] == 3
    assert feed["category_counts"] == {
        "Fato Relevante": 1,
        "Comunicado ao Mercado": 1,
        "Assembleia": 1,
    }
    assert feed["unmapped"] == ["ITSA4"] and "FIIs" in feed["note"]

    facts = api.client.get("/api/v1/disclosures", params={"category": "Fato Relevante"}).json()
    assert [i["protocol"] for i in facts["items"]] == ["W1"]
    by_asset = api.client.get("/api/v1/disclosures", params={"asset_id": ids["WEGE3"]}).json()
    assert len(by_asset["items"]) == 3 and by_asset["note"] is None
    fii = api.client.get("/api/v1/disclosures", params={"asset_id": ids["XPML11"]}).json()
    assert fii["items"] == [] and "FIIs" in fii["note"]
    assert api.client.get("/api/v1/disclosures", params={"asset_id": 9999}).status_code == 404

    done = api.client.post("/api/v1/disclosures/read", json={"ids": [feed["items"][1]["id"]]})
    assert done.json() == {"updated": 1}
    unread = api.client.get("/api/v1/disclosures", params={"unread": True}).json()
    assert [i["protocol"] for i in unread["items"]] == ["W1", "W3"]
    everything = api.client.post("/api/v1/disclosures/read", json={"all": True}).json()
    assert everything == {"updated": 2}
    assert api.client.get("/api/v1/disclosures").json()["unread_count"] == 0


def test_unread_relevant_facts_raise_an_alert_until_read(api: SimpleNamespace) -> None:
    ids = _seed_assets(api)
    _sync(api)
    alerts = [
        a for a in api.client.get("/api/v1/alerts").json()["alerts"] if a["kind"] == "RELEVANT_FACT"
    ]
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["key"] == "fact:W1" and alert["subject"] == "WEGE3"
    assert alert["route"] == f"/asset/{ids['WEGE3']}?tab=disclosures"
    assert "Aquisição" in alert["detail"]

    api.client.post("/api/v1/disclosures/read", json={"all": True, "asset_id": ids["WEGE3"]})
    after = api.client.get("/api/v1/alerts").json()["alerts"]
    assert not any(a["kind"] == "RELEVANT_FACT" for a in after)


def test_relevant_fact_alerts_ignore_read_and_other_categories() -> None:
    read = CvmDocument("R", WEG, "WEG", "Fato Relevante", TODAY, read_at=datetime.now(UTC))
    notice = CvmDocument("N", WEG, "WEG", "Comunicado ao Mercado", TODAY)
    fact = CvmDocument("F", WEG, "WEG", "Fato Relevante", TODAY)
    alerts = relevant_fact_alerts([read, notice, fact], {WEG: ["WEGE3"]}, {})
    assert [a.key for a in alerts] == ["fact:F"]
    assert alerts[0].kind == AlertKind.RELEVANT_FACT and alerts[0].route == "/home"


def test_worker_job_and_mcp(api: SimpleNamespace) -> None:
    _seed_assets(api)
    gateway = SimpleNamespace(
        get_cvm_issuer_tickers=lambda _y: list(MAP),
        get_cvm_documents=lambda y: DOCS if y == TODAY.year else [],
    )
    details = sync_cvm_documents_job(api.uow_factory, gateway)  # type: ignore[arg-type]
    assert details["new"] == 3 and details["unmapped"] == ["ITSA4"]

    handlers = AgenticRuntimeHandlers(
        uow_factory=api.uow_factory,
        portfolio_service=PortfolioApplicationService(offline_gateway()),
    )
    listing = CATALOG_BY_NAME["disclosures.list"]
    feed = listing.invoke(handlers, listing.input_model(categories=["Fato Relevante"]))
    assert [i.protocol for i in feed.items] == ["W1"]
    mark = CATALOG_BY_NAME["disclosures.mark_read"]
    assert mark.kind == "command"
    assert mark.invoke(handlers, mark.input_model(all=True)).updated == 3
    request = CATALOG_BY_NAME["market.request_job"]
    assert (
        request.invoke(handlers, request.input_model(job_name="sync_cvm_documents")).status
        == "REQUESTED"
    )
