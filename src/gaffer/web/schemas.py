"""Request and response models.

Every router declares its response model, so the shape the frontend types
against is defined in exactly one place and FastAPI enforces it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class JobAccepted(BaseModel):
    job_id: str


class Staleness(BaseModel):
    advice_gw: int
    current_gw: int | None
    generated_at: str
    deadline: str
    deadline_passed: bool
    stale: bool
    reason: str


class AdviceLatest(BaseModel):
    gw: int
    mode: str
    deadline: str
    advice: dict[str, Any]
    staleness: Staleness
