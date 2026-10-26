"""HTTP controllers (routers) of the accounts module; they only delegate to use cases.

Scope: brokers, banks and exchanges that hold the assets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from fincontrol_api.modules.accounts.dependencies import get_account_handler
from fincontrol_api.modules.accounts.schemas import AccountDTO, AccountRequest
from fincontrol_api.modules.accounts.use_cases import AccountHandler

accounts_router = APIRouter(prefix="/accounts", tags=["Accounts"])


@accounts_router.get("", response_model=list[AccountDTO])
def list_accounts(
    active_only: bool = Query(default=False),
    handler: AccountHandler = Depends(get_account_handler),
) -> list[AccountDTO]:
    return handler.list_all(active_only=active_only)


@accounts_router.post("", response_model=AccountDTO, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountRequest,
    handler: AccountHandler = Depends(get_account_handler),
) -> AccountDTO:
    return handler.create(payload)


@accounts_router.put("/{account_id}", response_model=AccountDTO)
def update_account(
    account_id: int,
    payload: AccountRequest,
    handler: AccountHandler = Depends(get_account_handler),
) -> AccountDTO:
    return handler.update(account_id, payload)
