"""Integration tests for /policy and the /settings/arca-targets facade (item 10.1)."""

from __future__ import annotations

from types import SimpleNamespace

PAYLOAD = {
    "arca": [
        {"arca_class": "ACOES", "target_pct": 30, "band_pct": 4},
        {"arca_class": "REAL_ESTATE", "target_pct": 20, "band_pct": 4},
        {"arca_class": "CAIXA", "target_pct": 30, "band_pct": 6},
        {"arca_class": "ATIVOS_INTERNACIONAIS", "target_pct": 20, "band_pct": 4},
    ],
    "eligibility": {"require_evaluation": True, "min_score": 3, "min_coverage_pct": 50},
    "valuation": {"bazin_required_yield": 0.07, "graham_multiplier": 22.5},
}


def test_migration_seeds_version_one(api: SimpleNamespace) -> None:
    body = api.client.get("/api/v1/policy").json()
    assert body["version"] == 1
    assert {c["band_pct"] for c in body["arca"]} == {5.0}


def test_update_creates_new_version_and_drives_projections(api: SimpleNamespace) -> None:
    saved = api.client.put("/api/v1/policy", json=PAYLOAD)

    assert saved.status_code == 200
    assert saved.json()["version"] == 2
    assert saved.json()["eligibility"]["min_score"] == 3
    versions = api.client.get("/api/v1/policy/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    report = api.client.get("/api/v1/portfolio").json()
    targets = {a["arca_class"]: a["target_pct"] for a in report["allocations"]}
    assert targets["CAIXA"] == 30.0


def test_invalid_policy_is_rejected(api: SimpleNamespace) -> None:
    bad_sum = {**PAYLOAD, "arca": [{**c, "target_pct": 30} for c in PAYLOAD["arca"]]}
    assert api.client.put("/api/v1/policy", json=bad_sum).json()["code"] == "INVALID_ARCA_TARGETS"
    bad_band = {**PAYLOAD, "arca": [{**c, "band_pct": 60} for c in PAYLOAD["arca"]]}
    assert api.client.put("/api/v1/policy", json=bad_band).status_code == 422


def test_arca_targets_facade_keeps_bands_and_rules(api: SimpleNamespace) -> None:
    api.client.put("/api/v1/policy", json=PAYLOAD)
    targets = [
        {"arca_class": "ACOES", "target_pct": 25, "intra_class_strategy": "EQUAL_WEIGHT"},
        {"arca_class": "REAL_ESTATE", "target_pct": 25},
        {"arca_class": "CAIXA", "target_pct": 25},
        {"arca_class": "ATIVOS_INTERNACIONAIS", "target_pct": 25},
    ]

    resp = api.client.put("/api/v1/settings/arca-targets", json={"targets": targets})

    assert resp.status_code == 200
    policy = api.client.get("/api/v1/policy").json()
    acoes = next(c for c in policy["arca"] if c["arca_class"] == "ACOES")
    assert policy["version"] == 3
    assert acoes == {
        "arca_class": "ACOES",
        "target_pct": 25.0,
        "band_pct": 4.0,
        "intra_class_strategy": "EQUAL_WEIGHT",
    }
    assert policy["eligibility"]["min_score"] == 3
    facade = api.client.get("/api/v1/settings/arca-targets").json()
    assert [t["target_pct"] for t in facade] == [25.0] * 4
