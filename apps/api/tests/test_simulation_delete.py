"""Phase 40.4: deleting a simulation is for good (logical deletion, no restore)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from types import SimpleNamespace

from domain.agentic.services.catalog import CATALOG_BY_NAME
from domain.simulation.entities import SimulationStatus
from domain.simulation.runs import BacktestParams, new_backtest_run

START = date(2024, 1, 2)
END = date(2024, 6, 28)


def test_a_deleted_run_leaves_every_list_lookup_and_reuse(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        kept = uow.simulations.add(new_backtest_run(BacktestParams(START, END, 1.0)))
        gone = uow.simulations.add(
            replace(
                new_backtest_run(BacktestParams(START, END, 2.0)),
                status=SimulationStatus.DONE,
                data_hash="d",
            )
        )
        uow.commit()

    assert api.client.delete(f"/api/v1/simulations/{gone.id}").status_code == 204
    listed = [r["id"] for r in api.client.get("/api/v1/simulations").json()]
    assert listed == [kept.id]
    assert api.client.get(f"/api/v1/simulations/{gone.id}").status_code == 404
    # No way back: a second delete finds nothing, and no route restores it.
    assert api.client.delete(f"/api/v1/simulations/{gone.id}").status_code == 404
    with api.uow_factory() as uow:
        assert uow.simulations.find_done(gone.params_hash, "d", gone.code_version) is None
        assert uow.simulations.mark_deleted(gone.id, deleted_at=gone.created_at) is False  # type: ignore[arg-type]


def test_a_deleted_pending_run_is_never_executed(api: SimpleNamespace) -> None:
    with api.uow_factory() as uow:
        run = uow.simulations.add(new_backtest_run(BacktestParams(START, END, 1.0)))
        uow.commit()
    api.client.delete(f"/api/v1/simulations/{run.id}")
    with api.uow_factory() as uow:
        assert uow.simulations.next_pending() is None


def test_delete_is_an_mcp_command() -> None:
    spec = CATALOG_BY_NAME["simulation.delete"]
    assert spec.kind == "command"
