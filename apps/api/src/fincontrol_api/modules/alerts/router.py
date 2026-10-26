"""HTTP controllers (routers) of the alerts module; they only delegate to use cases.

Scope: portfolio, valuation and data alerts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from fincontrol_api.modules.alerts.dependencies import get_alert_handler
from fincontrol_api.modules.alerts.schemas import AlertDismissRequest, AlertsResponseDTO
from fincontrol_api.modules.alerts.use_cases import AlertHandler

alerts_router = APIRouter(prefix="/alerts", tags=["Alerts"])


@alerts_router.get("", response_model=AlertsResponseDTO)
def list_alerts(handler: AlertHandler = Depends(get_alert_handler)) -> AlertsResponseDTO:
    return handler.list_alerts()


@alerts_router.post("/dismissals", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_alert(
    payload: AlertDismissRequest,
    handler: AlertHandler = Depends(get_alert_handler),
) -> Response:
    handler.dismiss(payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@alerts_router.delete("/dismissals", status_code=status.HTTP_204_NO_CONTENT)
def restore_alert(
    key: str = Query(..., min_length=1, max_length=160),
    handler: AlertHandler = Depends(get_alert_handler),
) -> Response:
    handler.restore(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
