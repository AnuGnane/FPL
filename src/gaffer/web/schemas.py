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


class NextFixture(BaseModel):
    """One team's next game in the advised gameweek.

    Resolved at serve time from the banked fixture list, never solved for.
    Two of the four fields are independently optional and mean different
    things when null: ``kickoff_utc`` is null while FPL still has the date as
    TBC, and ``difficulty`` is null when the ticker could rate nothing — a
    chip in a neutral colour rather than a chip that is not drawn.

    A team with *no* game gets ``next_fixture: null`` on the player instead of
    this model with empty fields, because "he does not play" and "he plays and
    we know less than usual about it" are different sentences.
    """

    opponent_short: str | None = None
    home: bool
    kickoff_utc: str | None = None
    difficulty: float | None = None


class PlayerRef(BaseModel):
    code: int
    name: str
    position: str
    ep: float
    # v9a: identity, resolved at serve time by ``gaffer.web.identity`` and
    # never written into the advice artifact — ``advise.py`` is protected, so
    # the fields are a decoration on the way out of the route. All three
    # default to None, so a plan payload built without the enrichment (the
    # what-if lab, ``/api/plan``) types exactly as it did.
    team_short: str | None = None
    team_code: int | None = None
    next_fixture: NextFixture | None = None


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


class RivalBeat(BaseModel):
    entry: int
    name: str
    p_beat: float | None = None
    """``None`` when the entry's squad could not be read at all (private, or
    joined after the gameweek). Such an entry is listed but not simulated —
    see ``league_sim.is_readable`` — and the card renders a dash."""


class SimPoint(BaseModel):
    """One banked gameweek of the headline, for the card's sparkline."""

    gw: int
    p_win: float
    p_top3: float
    exp_finish: float
    run_at: str


class LeagueSimData(BaseModel):
    gw: int
    entries: int
    weeks_left: int
    n: int
    seed: int
    rival_drift: float
    p_win: float
    p_top3: float
    exp_finish: float
    per_rival: list[RivalBeat]
    margin_quantiles: dict[str, float]
    history: list[SimPoint]
    field_rate: float | None = None
    """The sampled field's weekly rate, or ``None`` when nothing is banked —
    in which case rivals do not drift however ``rival_drift`` is set."""
    notice: str | None = None
    legacy_win_probability: list[WinProb] = Field(default_factory=list)
    """``league_mode.win_probability``'s parametric answer, kept beside the
    simulated one until the UI has fully switched (spec §3)."""


class LeagueWhatIfPin(BaseModel):
    code: int
    """A gaffer player *code*, not a season element id — the explorer, the
    squad table and the compare panel all speak codes, and the router maps to
    elements against the same snapshot they were rendered from."""
    event: str = "blank"          # "haul" | "blank" | "score"


class LeagueWhatIfRequest(BaseModel):
    pins: list[LeagueWhatIfPin] = Field(default_factory=list)
    captain_override: int | None = None
    rival_captain_blanks: int | None = None
    cached_only: bool = False
    """Answer from the cache or not at all (204).

    This Week's captaincy chip sets it. That page is the one opened on a
    Thursday evening, the chip is decoration, and a cold cache means fifty
    entry-picks requests at the FPL API fired by a page load — at the hour
    every FPL manager in the country is loading pages. The League What-if tab
    leaves it false: there the simulation *is* the page."""


class LeagueWhatIfRow(BaseModel):
    entry: int
    name: str
    is_you: bool
    total: int
    p_win: float | None = None
    """This entry's win frequency in the same run as the headline, or ``None``
    when its squad could not be read (``league_sim.is_readable``)."""
    exp_finish: float


class LeagueWhatIfResult(BaseModel):
    baseline_p_win: float
    p_win: float
    delta_p_win: float
    baseline_exp_finish: float
    exp_finish: float
    delta_rank: float
    table: list[LeagueWhatIfRow]
    unknown_codes: list[int] = Field(default_factory=list)


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
    # v8d: the auto-sub projection and what this player still owes. All
    # defaulted — a payload built without a component file carries the same
    # row it always did.
    projected_out: bool = False
    projected_in: bool = False
    sub_partner: int | None = None
    """The other half of a projected substitution, so a chip can name him."""
    sub_reason: str | None = None
    """``"played"`` or ``"yet to play"``: how certain the incoming man is."""
    remaining_ep: float | None = None


class LiveTableRow(BaseModel):
    entry: int
    name: str
    pre_total: int
    live: int
    projected: int
    delta: int
    # v8d. ``live`` stays the no-autosub figure ``entry_live_points`` returns;
    # ``projected_live`` is the same gameweek with the projected subs applied,
    # and is what ``projected`` (the season total) is now built from.
    projected_live: int | None = None
    remaining_ep: float | None = None
    race: float | None = None
    """``projected_live + remaining_ep``: where this gameweek is heading."""


class LiveSafety(BaseModel):
    """One league place worth watching, priced in points."""

    entry: int
    name: str
    role: Literal["above", "below", "leader"]
    margin: int
    """Their projected total minus mine. Positive means they are ahead."""
    need: int
    """What I must add beyond my projection to pass them; 0 when I lead."""


class LiveRacePoint(BaseModel):
    """One poll's snapshot of the race, held in memory for this session only."""

    at: str
    you: float
    rival: float | None = None
    """The tracked rival's race value — the entry pinned in ``rival_name``,
    which is the top entry in the league that is not me. He is the leader
    only when I am not; when I am leading he is the man in second."""


class LiveState(BaseModel):
    active: bool
    gw: int | None
    my_points: int
    matches_in_play: int
    players: list[LivePlayer]
    table: list[LiveTableRow]
    notice: str | None = None
    my_projected_points: int = 0
    my_race: float | None = None
    race_reference: float | None = None
    """This gameweek's saved ``advice.expected_pts``, when there is one."""
    race_series: list[LiveRacePoint] = Field(default_factory=list)
    safety: list[LiveSafety] = Field(default_factory=list)
    rival_name: str | None = None
    """The entry the trajectory follows: the highest-placed entry that is not
    me, picked on the gameweek's first poll and then pinned for the rest of it
    so the line cannot change whose points it is plotting mid-afternoon."""
    race_notice: str | None = None
    """The race's own degradation line. Deliberately not ``notice``, which is
    the tier-EO line and belongs to a different card."""


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
    field_eo: float | None = None
    """Top-10k effective ownership from the latest banked scrape.

    ``None`` means *unknown*, and it means it in two different situations
    that the UI renders identically and correctly: no field log at all, or a
    log that does not carry this player because no sampled entry started him.
    Neither is 0.0, which the reader would take as a measured differential."""
    field_se: float | None = None
    """The standard error on ``field_eo``, in percentage points.

    ``None`` for exactly the situations ``field_eo`` is ``None`` for, and — the
    part worth stating — **never 0.0**. Zero here would be a claim of perfect
    precision drawn from a sample of a few hundred entries, which is a stronger
    statement than any number on this row is entitled to make.
    """
    field_n: int | None = None
    """How many sampled entries the figure was measured over.

    ±2.8 from three hundred entries and ±2.8 from thirty are different claims
    and the page is entitled to say which one it is showing.
    """
    field_class: str | None = None
    """``shield`` | ``sword`` | ``threat``, or ``None`` for the quadrant with
    nothing to say."""
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
    ep_lo: float | None = None
    """p25 of the noise model's distribution for ``ep_next`` — see
    :mod:`gaffer.uncertainty`. Deliberately **not** ``ep_next`` minus
    something: the calibrated path recentres, so the pair is quartiles rather
    than a symmetric interval, and the UI labels it that way.

    ``None`` — never ``ep_next`` — when the components frame carries no
    minutes model for him, or is absent altogether. A zero-width band on the
    least-known player in the pool would read as certainty."""
    ep_hi: float | None = None
    p_haul: float | None = None
    """``P(points >= 10)`` under the same distribution. Crude by construction:
    it prices *forecast* error, not football's own variance.

    This is ``uncertainty.Band.p_haul``, the whole-forecast tail — *not*
    ``models.assemble.p_haul``, which is P(2+ attacking returns) under a
    Poisson and is served on the advice payload as ``p_attacking_haul``. Two
    quantities, one page, one name until v9c (spec D3)."""
    p_blank: float | None = None
    """``P(points <= 2)`` under the same distribution."""


class Component(BaseModel):
    label: str
    points: float


class MinutesOutput(BaseModel):
    p_play: float | None = None
    """``None`` — never 0.0 — for a frame banked without a minutes model. Zero
    here reads as "expected not to play", which is the strongest claim this
    payload can make about a player, and the compare radar drew it as a
    zero-length spoke on the minutes axis."""
    p60: float
    xmins: float | None = None
    """Expected minutes, ``p_play * (45 + 45 * p60)``. ``None`` when either
    probability is missing: an un-modelled player is not a player expected to
    play no minutes."""


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

    threshold_now: float | None = None
    """θ for this chip in the current gameweek: the surplus the best remaining
    week is expected to offer. ``chip_plan`` has always computed it and this
    model has never declared it, so until v10b it was computed and dropped —
    the ``odds_blend_weight`` failure, repeated. An undeclared field never
    reaches the page and nothing fails while it doesn't."""

    play_now: bool | None = None

    thetas: list[float] = []
    """θ per week, aligned by index with ``weeks``. Built at the router by
    looping the same ``(chip, gw) -> float`` callable, because putting it in
    ``chip_plan``'s week rows would be an ``optimize/**`` edit for a display
    field (plan A9)."""

    window: list[int] = []
    """``[from_gw, last_gw]`` from ``chip_policy.chip_windows``. Note the first
    element is the gameweek asked about, not the window's opening — the UI says
    "expires after GW19" and never "window starts at"."""


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
    ep_gw: float | None = None
    """Expected points for the *requested* gameweek alone.

    ``ep`` above is a horizon sum — the components parquet carries every
    gameweek in the solve horizon — so it is not a number the σ table has ever
    seen. The band brackets this one instead (plan A2)."""
    sigma: float | None = None
    """The scenario sweep's own σ for this player-gameweek, in points."""
    ep_lo: float | None = None
    """p25 / p75 of the distribution ``noise_ep`` draws from. ``None``, never
    zero, when the frame carries no minutes model for him."""
    ep_hi: float | None = None
    p_haul: float | None = None
    """``uncertainty.Band.p_haul``: P(total points >= 10) in the tail of the
    whole forecast. The advice payload's attacking quantity is a different
    number on a different scale and is served as ``p_attacking_haul``
    (spec D3)."""
    p_blank: float | None = None


class ComponentsBreakdown(BaseModel):
    gw: int
    players: list[ComponentPlayer]


class AdvicePlayer(BaseModel):
    code: int
    name: str


class EpMover(BaseModel):
    """One player the newest retrain moved, in the gameweek being decided."""

    code: int
    name: str
    ep_prev: float
    ep_now: float
    delta: float


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
    ep_movers: list[EpMover] = Field(default_factory=list)
    """Players whose expected points moved between the two newest component
    breakdowns. Independent of ``available``: a first run of the week has no
    plan to diff and may still have a retrain to report (plan A10)."""
    ep_movers_count: int | None = None
    """How many moved, or ``None`` when there is no predecessor breakdown to
    compare against. ``None`` and ``0`` are different claims — "we have not
    retrained since you looked" against "the retrain changed nothing" — and
    the strip renders only the second."""


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


class CalibrationHead(BaseModel):
    """One probability head's calibration for one gameweek, or a refusal.

    ``status`` rather than a missing key: a head under
    ``evaluation.MIN_CALIBRATION_SAMPLES`` has the same shape as a scored one
    with nulls in it, so the card renders "not enough data" from a field
    instead of branching on absence.
    """

    status: str
    n: int
    brier: float | None = None
    log_loss: float | None = None
    reliability: list[ReliabilityBin] = []


class CalibrationGw(BaseModel):
    gw: int
    n: int
    heads: dict[str, CalibrationHead] = {}


class CalibrationReport(BaseModel):
    """The banked report, or the honest empty one.

    ``available`` is what the card branches on. The route answers 200 either
    way (spec §4) because this card sits beside populated ones and a 422 there
    is indistinguishable from a broken endpoint.
    """

    available: bool = False
    run_at: str | None = None
    git_sha: str | None = None
    season: str | None = None
    gameweeks: list[CalibrationGw] = []
    cumulative: dict[str, CalibrationHead] = {}
    omitted: dict[str, str] = {}
    #: Heads that *are* graded but not per gameweek — p_cs, whose club-fixture
    #: grain supplies about twenty rows a week against a thirty-row floor. The
    #: card prints the reason under the table rather than a column of refusals.
    per_gw_omitted: dict[str, str] = {}
    excluded: list[dict[str, Any]] = []
    missing: list[int] = []
    note: str | None = None


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
    bank: float | None = None
    """What is left in the bank after this week's moves, in millions.

    ``None`` means *unknown*, and it means it for one reason: some move in
    this week or an earlier one had no price, so the running total is broken
    and stays broken. Never 0.0 — that is "fully invested", which is a real
    and different state a manager can be in.
    """


class PlanTimeline(BaseModel):
    gw: int
    generated_at: str
    weeks: list[PlanGw]
    bank: float | None = None
    """What is in the bank before the horizon's first move, in millions.

    ``SolveState.bank`` in tenths, through the same conversion every price on
    this payload takes. ``None`` means the solve state carried no usable
    figure — never 0.0, which is "fully invested".
    """


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


class OutlookTeam(BaseModel):
    """A club in the outlook. ``short_name`` is null when the teams snapshot
    could not be read — the counts are still true, only the label is missing,
    and losing the whole answer over a cosmetic join is the wrong trade."""

    code: int
    short_name: str | None = None


class OutlookWeek(BaseModel):
    gw: int
    fixtures: int
    doubles: list[OutlookTeam] = Field(default_factory=list)
    blanks: list[OutlookTeam] = Field(default_factory=list)


class FixtureOutlook(BaseModel):
    """Doubles and blanks in the season ahead (v10b §F2a).

    Every failure is a 200 with a ``note`` rather than an error: this renders
    as one card beside populated cards, and a 422 there is indistinguishable
    from a broken endpoint.
    """

    from_gw: int | None = None
    weeks: list[OutlookWeek] = Field(default_factory=list)
    has_doubles: bool = False
    has_blanks: bool = False
    """A claim about the **served slice**, not the season: both flags are
    computed over the same ``weeks`` this response carries, so a ``from_gw``
    narrows them together with the rows.

    Declared rather than derived on the client, for the reason v9d's
    ``available`` exists: the empty state is the common case for months, and a
    client branching on ``weeks.every(w => !w.doubles.length)`` is a client
    that will one day branch on ``weeks.length`` by mistake."""

    teams_known: bool = False
    """False when the teams snapshot was unreadable and the codes above are
    raw team ids. The counts hold; the names do not."""

    note: str | None = None


class JournalRow(BaseModel):
    gw: int
    model_pts: int
    actual_pts: int
    delta: int
    model_captain: str | None = None
    actual_captain: str | None = None
    model_buys: list[str] = Field(default_factory=list)
    model_sells: list[str] = Field(default_factory=list)
    post_deadline: bool = False
    """Every banked run of this gameweek was written after its deadline, so
    the model's side of the comparison had the team news the user did not."""


class JournalPoint(BaseModel):
    gw: int
    model: int
    actual: int
    delta: int


class Journal(BaseModel):
    rows: list[JournalRow] = Field(default_factory=list)
    cumulative: list[JournalPoint] = Field(default_factory=list)
    built_at: str | None = None


class PenTrackerGw(BaseModel):
    """One finished gameweek of the penalty tracker.

    Every field but ``gw`` is optional because ``pen_tracker.safe_gw_block``
    writes one of two shapes: the full block, or ``{"gw": N, "error": ...}``
    when that week would not read. One optional-field model rather than a
    union — a union would make the client discriminate before it can render
    a row that is a row either way.
    """

    gw: int
    instrument: str | None = None
    rows: int | None = None
    covered_rows: int | None = None
    team_games: int | None = None
    component_rows: int | None = None
    predicted_ep_pen_taker: float | None = None
    predicted_takers: int | None = None
    pens_taken: float | None = None
    pens_by_first_choice: float | None = None
    taker_hit_rate: float | None = None
    pens_per_team_game: float | None = None
    realized_pen_points: float | None = None
    error: str | None = None


class PenTrackerTotals(BaseModel):
    """The season line. All optional: a report that degraded before it
    reached a single finished gameweek writes ``{}`` here."""

    gws: int | None = None
    instruments: list[str] = Field(default_factory=list)
    team_games: int | None = None
    predicted_ep_pen_taker: float | None = None
    pens_taken: float | None = None
    pens_by_first_choice: float | None = None
    taker_hit_rate: float | None = None
    pens_per_team_game: float | None = None
    league_pens_pg_served: float | None = None
    realized_pen_points: float | None = None


class PenTracker(BaseModel):
    """``reports/pen_tracker.json``, as written by ``gaffer track-pens``."""

    season: str = ""
    gws: list[PenTrackerGw] = Field(default_factory=list)
    season_totals: PenTrackerTotals = Field(default_factory=PenTrackerTotals)
    notes: list[str] = Field(default_factory=list)


class ReviewLane(BaseModel):
    """One graded decision lane (spec D5).

    ``delta_pts`` and ``label`` are ``None`` — never zero — for a lane that
    could not be built: the model's captain was not in my eleven, the model
    sold a player I never owned, either side played a wildcard. "The model had
    no opinion I could have acted on" and "the model agreed with me" are
    different facts and the UI colours them differently.
    """

    lane: Literal["transfers", "captaincy", "bench", "chip"]
    delta_pts: float | None = None
    delta_pwin: float | None = None
    """My choice minus the model's, in percentage points of P(win the
    league). ``0.0`` on the bench and chip lanes by construction — the
    simulation normalises every squad to its eleven and one armband."""
    label: Literal["Brilliant", "Good", "Aligned", "Inaccuracy",
                   "Blunder"] | None = None
    aligned: bool = False
    mine: str | None = None
    model: str | None = None
    note: str | None = None


class ReviewMiss(BaseModel):
    """A move the model flagged, I did not make, and that returned anyway."""

    code: int
    name: str
    over: str
    gain: int


class ReviewHindsight(BaseModel):
    """The best legal eleven out of the fifteen I owned, by actual points.

    ``points`` and ``gap`` are ``None`` — never zero — when no legal eleven
    could be built at all, which is what a fifteen the results frame does not
    cover looks like. A zero there would bank a *negative* gap.
    """

    points: int | None = None
    xi: list[int] = Field(default_factory=list)
    captain: int | None = None
    gap: int | None = None


class ReviewGw(BaseModel):
    """One gameweek's banked grade. Every field but ``gw`` has a default, so
    a ledger written by an older build still renders."""

    gw: int
    reviewed_at: str | None = None
    no_advice: bool = False
    post_deadline: bool = False
    my_points: int | None = None
    official_points: int | None = None
    official_gross: int | None = None
    hits: int = 0
    reconciled: bool | None = None
    chip: str | None = None
    model_chip: str | None = None
    points_on_bench: int | None = None
    overall_rank: int | None = None
    """My overall FPL rank at the end of this gameweek.

    ``None`` for two situations the reader must not see merged: a gameweek
    whose entry history was never banked, and — for the whole of this season's
    existing ledger — **a gameweek graded before the field existed.** Grades
    are banked and never re-derived (spec D2), so the trajectory begins empty
    and fills forward from the next graded week. A chart drawing this must
    show a gap, never a zero and never a line through it: zero is the best
    rank in the game.
    """
    our_bench_points: int | None = None
    model_points: int | None = None
    accuracy: int | None = None
    pwin_n: int | None = None
    pwin_seed: int | None = None
    pwin_granularity_pp: float | None = None
    lanes: list[ReviewLane] = Field(default_factory=list)
    misses: list[ReviewMiss] = Field(default_factory=list)
    hindsight: ReviewHindsight = Field(default_factory=ReviewHindsight)
    notices: list[str] = Field(default_factory=list)


class ReviewLaneTotal(BaseModel):
    pts: float = 0.0
    pwin: float = 0.0
    graded: int = 0
    """How many gameweeks this lane was gradeable in. ``pts`` of zero over
    ``graded`` of zero is "never measured", not "never wrong"."""
    wins: int = 0
    losses: int = 0
    """Graded weeks this lane gained / lost points, counted strictly.

    A zero delta is neither, so ``wins + losses <= graded`` with slack — the
    difference is the weeks I did exactly what the model did. A UI that
    rendered ``wins / (wins + losses)`` would silently drop those weeks; the
    denominator is ``graded``.
    """


class ReviewAccuracyPoint(BaseModel):
    gw: int
    accuracy: int


class ReviewSummary(BaseModel):
    gws: list[int] = Field(default_factory=list)
    lanes: dict[str, ReviewLaneTotal] = Field(default_factory=dict)
    accuracy: list[ReviewAccuracyPoint] = Field(default_factory=list)
    points_on_bench: int = 0
    points_on_bench_gws: int = 0
    """How many gameweeks that total covers. A season of unbanked histories
    sums to zero over zero gameweeks, which is not an empty bench."""
    hindsight_gap: int = 0
    hindsight_gap_gws: int = 0
    reconciled_gws: int = 0
    unreconciled_gws: int = 0
    best: dict[str, Any] | None = None
    worst: dict[str, Any] | None = None


class Review(BaseModel):
    gws: list[ReviewGw] = Field(default_factory=list)
    summary: ReviewSummary | None = None


class OverrideRequest(BaseModel):
    """One pin. At least one of the two values must be present."""

    code: int
    p_play: float | None = None
    e_min: float | None = None
    note: str = ""


class OverrideRow(BaseModel):
    code: int
    name: str
    p_play: float | None = None
    e_min: float | None = None
    note: str = ""
    set_at: str = ""
    model_p_play: float | None = None
    """What the served pipeline had for him when the pin was made, so the
    why-panel can say "the model had 0.82" without re-deriving anything."""
    model_e_min: float | None = None


class OverridesPanel(BaseModel):
    active: bool = True
    """``[news] overrides``. False means the pins are stored and *not* being
    applied, which the panel says out loud rather than showing nothing."""
    rows: list[OverrideRow] = Field(default_factory=list)
    warning: str | None = None
    """Accepted, and worth a second look. Set on a write whose two numbers
    disagree with each other — expected minutes implying a player starts,
    beside a probability of playing that says he probably does not. A refusal
    would be wrong (the manager is allowed to mean it) and silence would be
    worse, so the dialog shows this and stays open."""


class NamedPlayer(BaseModel):
    """A player a report names but does not price."""

    code: int
    name: str
    position: str = ""


class SensitivityMove(BaseModel):
    kind: str
    code: int
    gw: int
    label: str
    name: str = ""
    count: int
    frequency: float


class SensitivityPlan(BaseModel):
    count: int
    buys: list[NamedPlayer] = Field(default_factory=list)
    sells: list[NamedPlayer] = Field(default_factory=list)
    captain: NamedPlayer | None = None
    hits: int = 0
    value: float = 0.0
    """Horizon expected points on the **true** EP table, so two signatures are
    compared on the board the manager faces rather than on their own draws."""


class SensitivityReport(BaseModel):
    available: bool = False
    gw: int | None = None
    k: int = 0
    completed: int = 0
    failures: int = 0
    seed: int | None = None
    horizon: int = 0
    wall_s: float | None = None
    generated_at: str | None = None
    notice: str | None = None
    frequencies: list[SensitivityMove] = Field(default_factory=list)
    modal: SensitivityPlan | None = None
    runner_up: SensitivityPlan | None = None
    margin: float | None = None
    decision_sigma: float | None = None
    """The scenario sweep's own *estimation* noise on the players that
    separate the two plans, in quadrature (plan A6).

    Not the σ behind the EP bands, and the difference is the point. A band
    answers "what might he score" and is dominated by football's own variance.
    This answers "how wrong might my forecast be" — the only question a margin
    between two plans solved off the same board can be threatened by — and so
    it stays on ``optimize.scenarios``' calibrated table alone.

    Computed at serve time from the banked components frame rather than stored
    in the report, so a report swept before this field existed still gets the
    line. ``None`` when there is no runner-up, no components frame, or nothing
    in the symmetric difference — the card then prints its margin unqualified,
    which is what it did before."""
    verdict: str | None = None


class DraftRow(BaseModel):
    name: str
    created_at: str = ""
    constraints: WhatIfRequest


class DraftList(BaseModel):
    drafts: list[DraftRow] = Field(default_factory=list)


class DraftSaveRequest(BaseModel):
    name: str
    constraints: WhatIfRequest = Field(default_factory=WhatIfRequest)


class DraftCompareRequest(BaseModel):
    names: list[str] = Field(default_factory=list)


class DraftCompareRow(BaseModel):
    name: str
    is_reference: bool = False
    """The unconstrained optimum, so every other row has a "worse than what"."""
    solved_at: str = ""
    horizon_pts: float | None = None
    expected_pts: float | None = None
    delta_xpts: float | None = None
    hits: int | None = None
    chip: str | None = None
    horizon: int | None = None
    """Gameweeks this row's plan actually covers, which is not always the
    comparison's. A free hit is a one-week squad; ``DraftCompare.weeks`` is
    the shorter shared window every row was then *scored* over."""
    buys: list[PlayerRef] = Field(default_factory=list)
    sells: list[PlayerRef] = Field(default_factory=list)
    captain: PlayerRef | None = None
    error: str | None = None
    """Why this row is empty. An infeasible draft is a row with a reason, not
    a failed comparison."""


class DraftCompare(BaseModel):
    gw: int
    weeks: int
    rows: list[DraftCompareRow] = Field(default_factory=list)


class ConfidenceTier(BaseModel):
    """One record-derived claim, with the counts that back it.

    ``text`` is the whole product — a sentence quoting counts. The counts are
    carried beside it so a caller can style the tier without re-parsing prose,
    never so it can compute a rate: the absence of a percentage anywhere in
    this model is the point of it (spec D3).
    """

    tier: Literal["early", "mixed", "backed"] = "early"
    reviewed: int = 0
    graded: int = 0
    """Reviewed gameweeks where the lane was actually comparable. The gap
    between this and ``reviewed`` is the weeks the model's captain was not in
    the eleven, which is not evidence either way."""
    wins: int = 0
    losses: int = 0
    aligned: int = 0
    text: str = ""


class Confidence(BaseModel):
    captain: ConfidenceTier = Field(default_factory=ConfidenceTier)


class MissRow(BaseModel):
    """One player-gameweek the forecast got most wrong.

    ``miss`` is ``actual - ep``, so it is signed: a positive one is a player
    the model under-rated and a negative one is a transfer it may have talked
    somebody into. Both directions are shown, which is why the card sorts on
    the absolute value and prints the sign.
    """

    code: int
    name: str
    position: str = ""
    price: float | None = None
    ep: float
    actual: int
    minutes: int = 0
    miss: float


class Misses(BaseModel):
    gw: int | None = None
    """``None`` when no gameweek has both a banked forecast and a banked
    result. That is an absent card, not a card of zeros (spec D1)."""
    rows: list[MissRow] = Field(default_factory=list)


class WatchRequest(BaseModel):
    """A star, and optionally a sentence about why."""

    code: int
    note: str = ""


class WatchRow(BaseModel):
    code: int
    name: str
    note: str
    set_at: str


class WatchlistPanel(BaseModel):
    """Every starred player, name-resolved.

    ``rows`` is empty on a fresh clone and on a broken store alike — the
    distinction is a printed line on the server, not a field here, because a
    client that rendered "your watchlist may be corrupt" would be showing the
    user a problem they cannot act on.
    """

    rows: list[WatchRow] = Field(default_factory=list)


class MoverRow(BaseModel):
    """One watched player FPL's predictor has near a threshold tonight."""

    code: int
    name: str
    now_cost: float
    """In millions, the way the UI shows a price — not the 0.1m integer the
    bootstrap carries."""
    price_change_percent: float
    direction: str
    """``rise`` or ``drop``. Never ``flat``: this list is only ever rows past
    the alert threshold, where the price log (which sees everyone) has a third
    value."""
    calibrating: bool
    """FPL is still fitting this player's price model — an early-season caveat
    the row carries rather than a reason to hide it."""
    source: str
    """``squad`` / ``plan`` / ``watchlist``, resolved in that order. The
    answer to "why is he on this list?", on the row itself."""


class MoversPanel(BaseModel):
    """Tonight's likely price changes among players the manager cares about.

    ``as_of`` is the age of the *reading*, not of the request: this is served
    off ``data/live/players.parquet`` and never off the network, so a panel
    that did not say how stale it was would be a panel claiming to know
    something about tonight when it might be quoting Tuesday.
    """

    available: bool
    as_of: str | None = None
    rows: list[MoverRow] = Field(default_factory=list)


class DigestSection(BaseModel):
    """One block of a digest. ``bits`` is prose the client joins.

    The DiffStrip idiom: clauses assembled server-side, rendered by joining
    them, so there is no markdown dependency anywhere in the client. A section
    with no bits never reaches here — the builder drops it (plan A5).
    """

    key: str
    title: str
    bits: list[str] = Field(default_factory=list)


class Digest(BaseModel):
    kind: str
    generated_at: str = ""
    gw: int | None = None
    headline: str
    sections: list[DigestSection] = Field(default_factory=list)
    error: str | None = None
    """Set only on a digest that failed to build. A run that crashes still
    banks an artifact so the card can say "Friday's briefing did not build"
    rather than falling back to the never-run empty state."""


class DigestPanel(BaseModel):
    """The newest digest, or a stated absence.

    ``available`` false covers all three ways there is nothing to show — never
    run, deleted, unparseable — because the card's empty state says the same
    sentence for each of them: press the button, or wait for Friday.
    """

    available: bool
    digest: Digest | None = None
