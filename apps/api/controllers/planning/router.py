"""HTTP controllers of Planejar: goals and future income (Phase 48.R8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from contracts.planning.requests import GoalCreateRequest, GoalUpdateRequest
from contracts.planning.responses import GoalDTO, IncomeForecastDTO
from contracts.planning.serializers import to_goal_dto, to_income_forecast_dto
from controllers.planning.dependencies import get_goal_handler, get_income_forecast_handler
from domain.planning.goals import Goal
from domain.planning.services import GoalHandler, IncomeForecastHandler

goals_router = APIRouter(prefix="/goals", tags=["Planning"])
income_forecast_router = APIRouter(prefix="/portfolio", tags=["Planning"])


@goals_router.get("", response_model=list[GoalDTO])
def list_goals(handler: GoalHandler = Depends(get_goal_handler)) -> list[GoalDTO]:
    return [to_goal_dto(p) for p in handler.list()]


@goals_router.post("", response_model=GoalDTO, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreateRequest, handler: GoalHandler = Depends(get_goal_handler)
) -> GoalDTO:
    return to_goal_dto(handler.create(Goal(**payload.model_dump())))


@goals_router.put("/{goal_id}", response_model=GoalDTO)
def update_goal(
    goal_id: int, payload: GoalUpdateRequest, handler: GoalHandler = Depends(get_goal_handler)
) -> GoalDTO:
    return to_goal_dto(handler.update(goal_id, payload.model_dump()))


@goals_router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, handler: GoalHandler = Depends(get_goal_handler)) -> Response:
    handler.delete(goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@income_forecast_router.get("/income-forecast", response_model=IncomeForecastDTO)
def get_income_forecast(
    months: int = Query(default=12, description="12, 24 or 36"),
    handler: IncomeForecastHandler = Depends(get_income_forecast_handler),
) -> IncomeForecastDTO:
    return to_income_forecast_dto(handler.forecast(months=months))
