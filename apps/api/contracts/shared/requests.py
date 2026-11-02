"""Shared API request schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AnswerInput(BaseModel):
    question_key: str
    answer: bool | None
    notes: str = ""
