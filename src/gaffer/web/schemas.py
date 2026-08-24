"""Request and response models.

Every router declares its response model, so the shape the frontend types
against is defined in exactly one place and FastAPI enforces it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


CHIP_CODES = {"wc": "wildcard", "bb": "bboost", "fh": "freehit",
              "tc": "3xc"}
"""UI chip codes -> the names ``chips_available_for`` uses."""


class WhatIfRequest(BaseModel):
    lock: list[int] = Field(default_factory=list)
    ban: list[int] = Field(default_factory=list)
    force_in: list[int] = Field(default_factory=list)
    max_hits: int = 0
    chip: Literal["none", "wc", "bb", "fh", "tc"] = "none"
    horizon: int | None = None


class PlayerRef(BaseModel):
    code: int
    name: str
    position: str
    ep: float


class PlanSummary(BaseModel):
    gw: int
    xi: list[PlayerRef]
    bench: list[PlayerRef]
    captain: PlayerRef
    vice: PlayerRef
    buys: list[PlayerRef]
    sells: list[PlayerRef]
    hits: int
    expected_pts: float
    """Raw expected points for ``gw`` alone, net of hits."""
    horizon_pts: float
    """The same measure summed over the gameweeks the two plans share."""


class WhatIfResult(BaseModel):
    baseline: PlanSummary
    yours: PlanSummary
    delta_xpts: float
    xi_in: list[PlayerRef]
    xi_out: list[PlayerRef]
    transfers_changed: bool
    captain_changed: bool
    verdict: str


class StandingRow(BaseModel):
    entry: int
    name: str
    player_name: str
    rank: int
    total: int
    event_total: int
    is_you: bool


class GwPoint(BaseModel):
    gw: int
    points: int
    total: int


class Trajectory(BaseModel):
    entry: int
    name: str
    points: list[GwPoint]


class GapPoint(BaseModel):
    gw: int
    gap: int
    """Your total minus the leader's, negative when you are behind."""


class WinProb(BaseModel):
    name: str
    total: int
    p_win: float


class LeagueRace(BaseModel):
    league_id: int
    entry_id: int
    standings: list[StandingRow]
    trajectory: list[Trajectory]
    gap: list[GapPoint]
    win_probability: list[WinProb]
    lam: float
    stance: str
    lam_explained: str
