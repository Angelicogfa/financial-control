"""API tests for the profile-based checklist with N/A, evidence and history (11.3, 11.4)."""

from __future__ import annotations

from types import SimpleNamespace


def test_checklist_update_records_answers_and_evaluation(api: SimpleNamespace) -> None:
    client = api.client
    created = client.post(
        "/api/v1/assets",
        json={"ticker": "ITUB4", "name": "Itaú", "asset_type": "STOCK_BR"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["checklist_profile"] == "STOCK"
    asset_id = body["id"]

    response = client.put(
        f"/api/v1/assets/{asset_id}/checklist",
        json={
            "use_cerrado": True,
            "checklist_profile": "BANK",
            "cerrado_answers": {"basel": "YES", "npl": "NA", "governance": False, "age_30y": None},
            "evidence": {"basel": "Basileia 14% no 2T"},
        },
    )
    assert response.status_code == 200, response.text
    asset = response.json()
    assert asset["checklist_profile"] == "BANK"
    assert asset["cerrado_answers"] == {"basel": True, "governance": False}
    assert asset["checklist_answers"]["npl"]["value"] == "NA"
    assert asset["checklist_answers"]["basel"]["evidence"] == "Basileia 14% no 2T"
    assert asset["checklist_answers"]["basel"]["source"] == "MANUAL"

    analysis = client.get(f"/api/v1/assets/{asset_id}/analysis")
    assert analysis.status_code == 200, analysis.text
    evaluation = analysis.json()["cerrado"]
    assert evaluation["profile"] == "BANK"
    assert evaluation["not_applicable"] == 1
    assert evaluation["applicable"] == 10
    assert evaluation["score"] == 0
    assert evaluation["coverage_pct"] == 20.0
    basel = next(a for a in evaluation["answers"] if a["question_id"] == "basel")
    assert (basel["value"], basel["answer"], basel["evidence"]) == (
        "YES",
        True,
        "Basileia 14% no 2T",
    )

    with api.uow_factory() as uow:
        history = uow.checklists.evaluation_history(asset_id)
        assert [(r.profile.value, r.answered, r.applicable) for r in history] == [("BANK", 2, 10)]

    # The deprecated route still works; an unchanged outcome adds no evaluation.
    again = client.put(
        f"/api/v1/assets/{asset_id}/cerrado",
        json={"cerrado_answers": {"basel": True, "npl": "NA", "governance": False}},
    )
    assert again.status_code == 200
    with api.uow_factory() as uow:
        assert len(uow.checklists.evaluation_history(asset_id)) == 1
        assert len(uow.checklists.answer_history(asset_id)) == 3


def test_invalid_answer_is_rejected(api: SimpleNamespace) -> None:
    created = api.client.post(
        "/api/v1/assets", json={"ticker": "WEGE3", "name": "WEG", "asset_type": "STOCK_BR"}
    )
    response = api.client.put(
        f"/api/v1/assets/{created.json()['id']}/checklist",
        json={"cerrado_answers": {"roe": "MAYBE"}},
    )
    assert response.status_code == 422
