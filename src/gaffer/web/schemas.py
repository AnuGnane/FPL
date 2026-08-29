"""Request and response models.

Every router declares its response model, so the shape the frontend types
against is defined in exactly one place and FastAPI enforces it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JobAccepted(BaseModel):
    job_id: str


class JobStarted(BaseModel):
    """The v7 runner's accept body. ``JobAccepted`` above still serves the v6
    queue endpoints, whose clients read only ``job_id``."""

    job_id: str
    kind: str


class JobRunView(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    started_at: str
    line_count: int
    finished_at: str | None = None
    error: str | None = None
    summary: str | None = None


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
    # v4d: display only, and all three optional — a tracker with no tier
    # sample renders exactly the table it rendered before.
    tier_eo: float | None = None
    tier_eo_se: float | None = None
    selected_by_percent: float | None = None


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
    notice: str | None = None


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
    last4: list[int] = Field(default_factory=list)
    """Points from the last four *finished* gameweeks, oldest first.

    Empty when ``data/live/player_gw.parquet`` has not been written — the
    sparkline then renders an em dash rather than a flat line at zero.
    """


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


class ChipWorkbenchRow(BaseModel):
    """One (chip, gameweek) cell of the advice run's own chip table.

    ``threshold`` is the θ bar that week — the surplus the best remaining week
    is expected to offer — so the workbench can draw the gain against the bar
    rather than against an arbitrary axis. Both it and ``play_now`` are
    optional because an advice payload written before the chip policy landed
    carries neither.
    """

    chip: str
    gw: int
    gain: float
    per_week: float | None = None
    threshold: float | None = None
    play_now: bool = False
    note: str | None = None


class SquadPlayerRef(BaseModel):
    code: int
    name: str
    position: str
    price: float
    ep: float


class SquadDiff(BaseModel):
    """A candidate squad against the one you own, resolved server-side."""

    gain_over_horizon: float
    recommend: bool
    kept: list[SquadPlayerRef]
    dropped: list[SquadPlayerRef]
    added: list[SquadPlayerRef]


class ChipsWorkbench(BaseModel):
    gw: int
    chips: list[ChipWorkbenchRow]
    wildcard: SquadDiff | None = None


class ComponentFixture(BaseModel):
    """One player-fixture's additive terms.

    Deliberately shaped like :class:`FixtureExplain` (the explain modal's
    per-fixture row) without being it: this one is read from the saved
    components parquet with no model loading at all, and carries only what a
    why-panel renders.
    """

    gw: int
    opponent: str
    home: bool
    kickoff_time: str | None
    components: list[Component]
    pen_taker: float | None = None
    """How much of the Goals term is penalty duty, when any of it is.

    Not a component: the increment was folded into ``e_goals`` before
    ``assemble_ep`` ran, so it is already inside ``components``' Goals row and
    listing it beside them would stop them summing to ``ep``. It rides along
    as an annotation the panel prints under Goals, and is ``None`` — not 0.0 —
    for the great majority of rows that have no penalty duty at all, so the
    panel can tell "no term" from "a term that rounded to zero".
    """
    minutes: MinutesOutput
    ep: float


class ComponentPlayer(BaseModel):
    code: int
    name: str
    position: str
    team_name: str
    ep: float
    """Summed over the player's fixtures in this gameweek."""
    fixtures: list[ComponentFixture]


class ComponentsBreakdown(BaseModel):
    gw: int
    players: list[ComponentPlayer]


class AdvicePlayer(BaseModel):
    code: int
    name: str


class AdviceDiff(BaseModel):
    """What changed between the two newest runs of one gameweek.

    ``available`` is false on a first run of the week — the ordinary case, not
    an error — and everything else is then empty, so the client renders
    nothing without having to special-case a status code.
    """

    gw: int
    available: bool
    changed: bool = False
    previous_at: str | None = None
    current_at: str | None = None
    buys_added: list[AdvicePlayer] = Field(default_factory=list)
    buys_dropped: list[AdvicePlayer] = Field(default_factory=list)
    sells_added: list[AdvicePlayer] = Field(default_factory=list)
    sells_dropped: list[AdvicePlayer] = Field(default_factory=list)
    captain_from: AdvicePlayer | None = None
    captain_to: AdvicePlayer | None = None
    chip_from: str | None = None
    chip_to: str | None = None
    expected_pts_delta: float = 0.0


class NewsRow(BaseModel):
    """One player the news layer moved, with the evidence that moved him.

    Both sides of every number, because the panel's claim is a *difference*:
    "we think 5%, the official flag says 75%" is the sentence, and either half
    on its own is not.
    """

    code: int
    name: str
    team_name: str
    p_play_news: float
    p_play_flags: float
    e_min_news: float
    e_min_flags: float
    # Official flag, from the bootstrap snapshot.
    status: str | None = None
    chance_of_playing: float | None = None
    official_note: str | None = None
    # The availability frame this run predicted on.
    injury_type: str | None = None
    expected_return_gw: int | None = None
    p_start_hint: float | None = None
    lineup_hint: str | None = None
    """``xi`` / ``doubt`` / ``out`` — ``p_start_hint`` named, because a
    probability in a caption reads as a forecast rather than as a listing."""
    source: str | None = None
    fetched_at: str | None = None


class NewsPanelData(BaseModel):
    gw: int
    moved: int
    rows: list[NewsRow]


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


class CategoryMetrics(BaseModel):
    rmse: float
    mae: float
    n: int


class ReferenceMetrics(BaseModel):
    """A published number: no row count, because we did not measure it."""

    rmse: float
    mae: float


class ReliabilityBin(BaseModel):
    n: int
    pred: float
    obs: float


class HeadMetrics(BaseModel):
    log_loss: float | None
    """``None`` for a head with nothing to score — see
    :func:`gaffer.evaluation.head_metrics`. Nullable rather than NaN because
    NaN is not JSON."""
    reliability: list[ReliabilityBin]


class CurrentEvaluation(BaseModel):
    run_at: str
    git_sha: str
    holdout_slots: int
    stratified: dict[str, dict[str, CategoryMetrics]]
    """cut ("all" / "starters") -> return category -> metrics."""
    heads: dict[str, HeadMetrics]
    baselines: dict[str, dict[str, CategoryMetrics]]


class BenchmarkEvaluation(BaseModel):
    run_at: str
    git_sha: str
    test_season: str
    stratified: dict[str, dict[str, CategoryMetrics]]
    references: dict[str, dict[str, ReferenceMetrics]]
    caveat: str


class DecompositionCell(BaseModel):
    total: int
    per_gw: float
    hits: int


class Decomposition(BaseModel):
    run_at: str
    git_sha: str
    season: str
    start_gw: int
    cells: dict[str, DecompositionCell]
    """``{model,oracle}_h{1,3}`` -> that replay's outcome."""
    forecast_gap_h3: float
    """oracle_h3 - model_h3: what better forecasting could still win."""
    planning_ceiling: float
    """oracle_h3 - oracle_h1: the ceiling on multi-week planning."""


class NewsShadowSummary(BaseModel):
    """Both sides of gate N2's two metrics over one slice of the log."""

    brier_news: float
    brier_flags: float
    mae_news: float
    mae_flags: float
    rows: int


class NewsShadowGw(BaseModel):
    gw: int
    brier_news: float
    brier_flags: float
    mae_news: float
    mae_flags: float
    rows: int
    cum_brier_news: float
    cum_brier_flags: float
    cum_mae_news: float
    cum_mae_flags: float


class NewsShadow(BaseModel):
    """Gate N2's standing readout.

    ``rows`` is the field that says whether any of it means anything: the log
    is written every week and scored only once a gameweek has been played, so
    a fresh install carries a payload with ``rows: 0``, an empty ``overall``
    and no gameweeks. That is not an error state — it is "come back Monday".
    """

    run_at: str
    git_sha: str
    rows: int
    overall: NewsShadowSummary | dict = Field(default_factory=dict)
    by_gw: list[NewsShadowGw] = Field(default_factory=list)


class Quality(BaseModel):
    """Whichever modes have been run. Each is independent and may be absent."""

    current: CurrentEvaluation | None = None
    benchmark: BenchmarkEvaluation | None = None
    decomposition: Decomposition | None = None
    # v6: `gaffer evaluate --news-shadow` has written this key since v5, but
    # nothing declared it here, so it never reached the page.
    news_shadow: NewsShadow | None = None


class PlanMove(BaseModel):
    code: int
    name: str
    position: str
    ep: float
    price: float | None = None
    """Buy price for an in, sell value for an out — in millions."""


class PlanGw(BaseModel):
    gw: int
    buys: list[PlanMove]
    sells: list[PlanMove]
    hits: int
    hit_cost: int
    chip: str | None = None
    captain: PlanMove | None = None
    vice: PlanMove | None = None
    expected_pts: float


class PlanTimeline(BaseModel):
    gw: int
    generated_at: str
    weeks: list[PlanGw]


class MatrixCell(BaseModel):
    gw: int
    opponent: str
    home: bool
    attack: float
    """Difficulty for your attackers, 0 easiest to 1 hardest.

    Driven by the opponent's *defence* strength: a mean defence is a hard
    fixture to score in.
    """
    defence: float
    """Difficulty of keeping a clean sheet, 0 easiest to 1 hardest.

    Driven by the opponent's *attack* strength.
    """


class MatrixTeam(BaseModel):
    code: int
    name: str
    short_name: str
    cells: list[MatrixCell]
    mean_attack: float
    mean_defence: float


class FixtureMatrix(BaseModel):
    gws: list[int]
    teams: list[MatrixTeam]
    source: Literal["dixon_coles", "none"]
