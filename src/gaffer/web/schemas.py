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
    # A different kind of stale: the advice can be current for the upcoming
    # gameweek and still have been built without last gameweek's results.
    data_through_gw: int | None = None
    data_warning: str | None = None


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


class RivalSummary(BaseModel):
    entry: int
    name: str
    player_name: str
    rank: int
    total: int
    event_total: int
    overlap: int
    differentials: int


class SquadPlayer(BaseModel):
    code: int
    element: int
    name: str
    position: str
    price: float
    is_captain: bool
    multiplier: int


class RivalDetail(BaseModel):
    entry: int
    name: str
    player_name: str
    total: int
    team_value: float
    chips_used: list[str]
    captain: SquadPlayer | None
    # The gameweek the squad was picked in — picks are public for finished
    # gameweeks only, so this trails ``live_points`` while one is in play.
    squad_gw: int
    squad: list[SquadPlayer]
    shared: list[SquadPlayer]
    their_differentials: list[SquadPlayer]
    your_differentials: list[SquadPlayer]
    live_points: int | None


class LivePlayer(BaseModel):
    element: int
    code: int
    name: str
    position: str
    multiplier: int
    points: int
    provisional_bonus: int
    minutes: int
    status: Literal["played", "playing", "yet to play"]


class LiveTableRow(BaseModel):
    entry: int
    name: str
    pre_total: int
    live: int
    projected: int
    delta: int


class LiveState(BaseModel):
    active: bool
    gw: int | None
    my_points: int
    matches_in_play: int
    players: list[LivePlayer]
    table: list[LiveTableRow]


class PlayerRow(BaseModel):
    code: int
    element: int
    name: str
    position: str
    team_code: int
    team_name: str
    price: float
    ep_next: float
    ep_horizon: float
    ownership: float
    league_eo: float
    available: bool
    status: str
    news: str
    chance_of_playing: float | None
    penalties_order: int | None
    free_kicks_order: int | None
    corners_order: int | None
    in_squad: bool


class Component(BaseModel):
    label: str
    points: float


class MinutesOutput(BaseModel):
    p_play: float
    p60: float


class OddsInfluence(BaseModel):
    weight: float
    e_goals_against: float | None
    p_cs_model: float
    p_cs_blended: float
    e_gc_model: float
    e_gc_blended: float


class FixtureExplain(BaseModel):
    gw: int
    opponent: str
    home: bool
    kickoff_time: str | None
    components: list[Component]
    minutes: MinutesOutput
    calibration_delta: float
    odds: OddsInfluence
    ep: float


class NextFixture(BaseModel):
    gw: int
    opponent: str
    home: bool


class PlayerExplain(BaseModel):
    code: int
    name: str
    position: str
    team_name: str
    ep_next: float
    fixtures: list[FixtureExplain]
    next_fixtures: list[NextFixture]
    set_pieces: dict[str, int | None]


class ChipWeek(BaseModel):
    gw: int
    gain: float
    per_week: float
    """``gain`` divided by the horizon weeks the chip is credited with — the
    weeks from ``gw`` onwards for a wildcard, one for every other chip."""


class ChipPlanRow(BaseModel):
    chip: str
    weeks: list[ChipWeek]
    best_gw: int
    best_gain: float
    best_gain_per_week: float
    weeks_scored: int
    """How many gameweeks were looked at, so the UI can say how far ahead
    "best" reaches rather than implying the whole season."""
    now_gain: float | None
    play_now_delta: float | None


class ChipPlan(BaseModel):
    gw: int
    chips: list[ChipPlanRow]


class HistoryRun(BaseModel):
    gw: int
    deadline: str
    captain: str
    buys: list[str]
    sells: list[str]
    hits: int
    expected_pts: float
    actual_pts: int | None


class PricePoint(BaseModel):
    gw: int
    price: float


class PriceSeries(BaseModel):
    code: int
    name: str
    points: list[PricePoint]


class History(BaseModel):
    runs: list[HistoryRun]
    prices: list[PriceSeries]
    backtests: list[dict[str, Any]]


class SourceHealth(BaseModel):
    source: str
    path: str
    present: bool
    modified_at: str | None
    age_hours: float | None


class ModelHealth(BaseModel):
    name: str
    saved_at: str | None
    metrics: dict[str, Any]


class LaunchdHealth(BaseModel):
    log: str
    present: bool
    modified_at: str | None
    last_line: str | None


class ArtifactItem(BaseModel):
    name: str
    bytes: int


class Health(BaseModel):
    data: list[SourceHealth]
    # File mtimes say when the ingest ran; this says what it got.
    data_through_gw: int | None = None
    models: list[ModelHealth]
    launchd: LaunchdHealth
    odds_key_present: bool
    model_health: dict[str, Any] | None
    artifacts: list[ArtifactItem]


class TickerCell(BaseModel):
    gw: int
    opponent: str
    home: bool
    difficulty: float


class TickerTeam(BaseModel):
    code: int
    name: str
    short_name: str
    cells: list[TickerCell]
    mean_difficulty: float


class Ticker(BaseModel):
    gws: list[int]
    source: Literal["odds", "elo"]
    teams: list[TickerTeam]
