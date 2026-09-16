"""Request and response models.

Every router declares its response model, so the shape the frontend types
against is defined in exactly one place and FastAPI enforces it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from gaffer.served import (  # noqa: F401
    PlanMoveTrace,
    PlanWeekTrace,
    ServedAlternative,
    ServedMove,
    ServedObjective,
    ServedPlan,
    ServedRestraint,
    ServedStep,
    ServedWeek,
)

WIRE_EXPORTS = (PlanMoveTrace, PlanWeekTrace, ServedMove, ServedWeek, ServedStep,
                ServedRestraint, ServedObjective, ServedAlternative, ServedPlan)
"""Models defined in :mod:`gaffer.served` and served on the wire (v17f §2.9):
``scripts/gen_types.py`` emits a model named here as if it were defined in
this file, so the served plan is typed once and the frontend takes the
generated names."""


# --- jobs and health: the runner's accept and poll bodies -----------------


class JobAccepted(BaseModel):
    job_id: str
    """The v6 ``JobRegistry`` id the caller polls at ``GET /api/jobs/{job_id}``."""


class JobStarted(BaseModel):
    """The v7 runner's accept body. ``JobAccepted`` above still serves the v6
    queue endpoints, whose clients read only ``job_id``."""

    job_id: str
    """The v7 ``JobRunner`` id, minted by ``JobRunner.start`` in `web/jobs.py`."""
    kind: str
    """The job kind the caller posted to, echoed back from the path parameter."""


class JobRunView(BaseModel):
    id: str
    """The run's id, as minted by ``JobRunner.start``."""
    kind: str
    """Which of the runner's four named kinds this run is."""
    status: Literal["queued", "running", "done", "failed"]
    """The run's lifecycle state, from ``JobRun.status`` in `web/jobs.py`."""
    started_at: str
    """ISO timestamp the run began, from ``JobRun.started_at``."""
    line_count: int
    """Total stdout lines captured so far, including any dropped from the
    500-line ring buffer (``JobRun.first_line_index + len(lines)``)."""
    finished_at: str | None = None
    """ISO timestamp the run ended, or ``None`` while it is still going."""
    error: str | None = None
    """The failure reason, set only when ``status`` is ``"failed"``."""
    summary: str | None = None
    """The one-line result the job wrote for itself on success."""


# --- This Week: the served advice and how old it is -----------------------


class Staleness(BaseModel):
    advice_gw: int
    """The gameweek the saved advice was solved for."""
    current_gw: int | None
    """``upcoming_gw()``'s answer now — the deadline the user is actually
    facing, which can be later than ``advice_gw`` when the advice is old."""
    generated_at: str
    """ISO timestamp the advice was solved, from the saved solve state."""
    deadline: str
    """ISO timestamp of ``advice_gw``'s deadline."""
    deadline_passed: bool
    """Whether ``deadline`` is before now, computed in ``staleness_for``
    (`routers/advice.py`) against ``pd.Timestamp.now(tz="UTC")``."""
    stale: bool
    """``deadline_passed or current_gw > advice_gw``: the advice is behind
    the gameweek the user needs, either way."""
    reason: str
    """The one sentence ``staleness_for`` builds explaining ``stale``, or
    confirming the advice is current."""
    # A different kind of stale: the advice can be current for the upcoming
    # gameweek and still have been built without last gameweek's results.
    data_through_gw: int | None = None
    """The last gameweek ``ingested_through()`` finds fully scored in the
    banked parquet, independent of when the advice itself was solved."""
    data_warning: str | None = None
    """``data_warning(current_gw, data_through_gw)``'s sentence when the
    model's ingested data trails the current gameweek, else ``None``."""


class AdviceLatest(BaseModel):
    gw: int
    """The gameweek this advice was solved for, from ``latest_gw()``."""
    mode: str
    """The solve state's mode (e.g. ``"normal"``, a chip), as saved by
    ``advise.py`` and read back by ``load_solve_state``."""
    deadline: str
    """ISO timestamp of ``gw``'s deadline, from the saved solve state."""
    advice: dict[str, Any]
    """The banked advice payload, enriched at serve time with position,
    identity, the attacking haul rename and the field frame (`latest()` in
    `routers/advice.py`)."""
    staleness: Staleness
    """Whether this advice is still current, from ``staleness_for``."""


CHIP_CODES = {"wc": "wildcard", "bb": "bboost", "fh": "freehit",
              "tc": "3xc"}
"""UI chip codes -> the names ``chips_available_for`` uses."""


# --- Planning: the what-if lab's request and its result -------------------


class WhatIfRequest(BaseModel):
    lock: list[int] = Field(default_factory=list)
    """Owned player codes the solve may not sell."""
    ban: list[int] = Field(default_factory=list)
    """Player codes excluded from the candidate pool entirely, owned or not."""
    force_in: list[int] = Field(default_factory=list)
    """Unowned player codes the solve must buy."""
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md)
    force_out: list[int] = Field(default_factory=list)
    """Owned players the solve must sell in the first horizon gameweek.

    He is then out of the squad **for the whole horizon**: ``milp`` pins squad
    membership to 0 in every week, not only the first, so this is not a sale
    the solver may reverse later. The bank is credited with his selling price.

    Not ``ban``: banning an owned player removes him from the candidate pool
    entirely, so he never enters the squad and — because he leaves the pool
    rather than the squad — the sale money never arrives. This says "sell
    him", which is the instruction the planner board's handoff has been
    approximating with ``ban`` since v11.
    """
    max_hits: int = 0
    """The most hits the solve may take in the first horizon gameweek."""
    # v13 §2.3. ``None`` is "no cap" (the baseline's cap is the saved state's,
    # never this); 0 is bank.
    max_transfers: int | None = None
    """The most transfers the solve may make; ``None`` is no cap, 0 is bank."""
    chip: Literal["none", "wc", "bb", "fh", "tc"] = "none"
    """The chip to play on the first horizon gameweek, if any."""
    horizon: int | None = None
    """How many gameweeks to solve over; ``None`` takes the saved state's."""


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
    """The next opponent's short club name, or ``None`` when he has no game."""
    home: bool
    """Whether the fixture is at home."""
    kickoff_utc: str | None = None
    """ISO kickoff time, or ``None`` while FPL still has it as TBC."""
    difficulty: float | None = None
    """The ticker's 0-1 rating for the fixture, or ``None`` when it could
    not be rated."""


class PlayerRef(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name."""
    position: str
    """His position: GKP, DEF, MID or FWD."""
    ep: float
    """Expected points, as the plan payload carries him."""
    # v9a: identity, resolved at serve time by ``gaffer.web.identity`` and
    # never written into the advice artifact — ``advise.py`` is protected, so
    # the fields are a decoration on the way out of the route. All three
    # default to None, so a plan payload built without the enrichment (the
    # what-if lab, ``/api/plan``) types exactly as it did.
    team_short: str | None = None
    """His club's short name, resolved at serve time by
    ``gaffer.web.identity``."""
    team_code: int | None = None
    """His club's code, resolved at serve time by ``gaffer.web.identity``."""
    next_fixture: NextFixture | None = None
    """His next game, resolved at serve time by ``gaffer.web.identity``."""


class PlanSummary(BaseModel):
    gw: int
    """The gameweek this plan is for."""
    xi: list[PlayerRef]
    """The starting eleven."""
    bench: list[PlayerRef]
    """The bench, in order."""
    captain: PlayerRef
    """The captain."""
    vice: PlayerRef
    """The vice-captain."""
    buys: list[PlayerRef]
    """Players bought into this plan."""
    sells: list[PlayerRef]
    """Players sold out of this plan."""
    hits: int
    """Hits taken to reach this plan."""
    expected_pts: float
    """Raw expected points for ``gw`` alone, net of hits."""
    horizon_pts: float
    """The same measure summed over the gameweeks the two plans share."""


class WhatIfResult(BaseModel):
    baseline: PlanSummary
    """The served advice's own plan."""
    yours: PlanSummary
    """The plan solved under the what-if lab's request."""
    delta_xpts: float
    """``yours``' horizon points minus ``baseline``'s."""
    xi_in: list[PlayerRef]
    """Players in ``yours``' eleven that were not in ``baseline``'s."""
    xi_out: list[PlayerRef]
    """Players in ``baseline``'s eleven that are not in ``yours``'."""
    transfers_changed: bool
    """Whether the two plans buy different players."""
    captain_changed: bool
    """Whether the two plans captain different players."""
    verdict: str
    """The lab's one-line summary of the comparison."""


# --- League: the standings, the race and the rivals -----------------------


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
    league_name: str = ""
    focus: bool = True
    """False when this is another private league opened for display: its
    λ is computed from its own standings and tilts nothing (v15 §3.3)."""
    stance_source: Literal["auto", "manual"] = "auto"


class PrivateLeagueRow(BaseModel):
    """One private mini-league the entry is in (v15 §5.1)."""

    league_id: int
    name: str
    rank: int | None = None
    last_rank: int | None = None
    entries: int | None = None
    """``rank_count`` from the entry payload; ``None`` before the league has
    a scored gameweek."""
    started: bool
    gap: int | None = None
    gap_kind: Literal["ahead", "behind"] | None = None
    would: Literal["chase", "defend"] | None = None
    """Gap-sign only — what the dial would lean to. The deadband and λ
    appear when the league is opened (``/race?league_id=``)."""
    is_focus: bool


class PublicLeagueRow(BaseModel):
    """A public or system league: rank line only (v15 §1.1)."""

    league_id: int
    name: str
    rank: int | None = None
    last_rank: int | None = None
    entries: int | None = None


class LeaguesOverview(BaseModel):
    focus_league_id: int
    focus_name: str | None = None
    """``None`` when the focus is not one of the private leagues, in which
    case ``focus_warning`` says so."""
    stance: Literal["auto", "chase", "defend", "neutral"]
    """``[league] stance`` as configured."""
    focus_stance: Literal["chase", "defend", "neutral"]
    focus_lam: float
    """The focus league's tilt as the next advise will see it: the solve
    state's λ with a manual stance applied (plan R2)."""
    focus_warning: str | None = None
    private: list[PrivateLeagueRow] = Field(default_factory=list)
    public: list[PublicLeagueRow] = Field(default_factory=list)
    gw: int | None = None


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


class FieldRank(BaseModel):
    """v12 W4 §5.3. One gameweek against a synthetic field drawn from EO.

    Three headline numbers and two of them are ``None`` today. Each null has
    its own sentence rather than a shared one, because they are waiting for
    different things: ``p_green`` for a banked field sample, ``p_top10k`` for
    a score series that does not exist anywhere, ``rank_slope`` for graded
    gameweeks. Spec §1: a view whose data does not exist says what it is
    waiting for and never renders a zero as a measurement.
    """

    gw: int
    n: int
    seed: int
    managers: int
    eo_source: str
    """``"deadline-trend"`` (§3.3's extrapolation), ``"last-sample"`` (the
    newest scrape), or ``"none"``. A trend EO and a last-sample EO are
    different numbers and the panel says which it used."""
    eo_gw: int | None = None
    """Which gameweek's sample the EO came from, or ``None`` when none did.

    Not :attr:`gw`. The field sample for plan gameweek N is banked under
    N-1 — picks 404 before a deadline, so the scrape reads the last scored
    week — and §3.3's ``deadline_eo`` extrapolates it one gameweek forward.
    Two different gameweek numbers in one payload is exactly the kind of
    thing a reader has to be told rather than left to infer."""
    field_draws: int = 1
    """Independent field populations the headline was averaged over
    (:data:`gaffer.league_sim.FIELD_DRAWS`). Provenance, like ``n`` and
    ``seed``: which three hundred managers were drawn is a source of noise in
    its own right."""
    unsampled_picks: int = 0
    """Players in my squad the field sample never saw.

    ``eo_from_picks`` omits anyone no sampled entry started, so a genuine
    differential is routinely absent from the EO table. He is simulated at
    ownership 0.0 — nobody in the field has him — and counted here so the
    panel can say how much of my week the sample cannot speak to."""
    p_green: float | None = None
    waiting_for: str | None = None
    p_top10k: float | None = None
    top10k_waiting_for: str | None = None
    rank_slope: float | None = None
    """Overall-rank places per point, from the graded ledger. Negative: more
    points is a better (smaller) rank."""
    rank_slope_rows: int = 0
    rank_waiting_for: str | None = None
    my_ep: float | None = None
    field_median_ep: float | None = None


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
    field: FieldRank | None = None
    """v12 W4 §5.3's panel. ``None`` only when the simulation itself could not
    be built; an unanswerable question is a ``FieldRank`` full of nulls with
    their reasons, not an absent object."""


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
    league_id: int | None = None
    """Which private league to re-count (v15 §5.2); ``None`` is the focus."""
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


# --- Live: the in-play scoreboard -----------------------------------------


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


# --- Players: the browser row and the "why 6.8?" panel --------------------


class PlayerRow(BaseModel):
    code: int
    """FPL player code."""
    element: int
    """FPL's own element id, as the bootstrap snapshot carries him."""
    name: str
    """Player name."""
    position: str
    """GKP, DEF, MID or FWD."""
    team_code: int
    """His club's code."""
    team_name: str
    """His club's name."""
    price: float
    """Current price in £m, from FPL's ``now_cost`` divided by ten."""
    ep_next: float
    """Expected points for the next gameweek alone."""
    ep_horizon: float
    """Expected points summed over the solve horizon."""
    ownership: float
    """FPL's own overall ownership percentage."""
    league_eo: float
    """Effective ownership among the manager's rivals — captaincy weighted
    double — from the saved solve state's ``league_eo``."""
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
    # v12 W2 §3.3 (specs/2026-09-01-gaffer-v12-program-design.md, plan A4/A5).
    field_eo_deadline: float | None = None
    """Field EO projected forward one gameweek, in percent.

    ``None`` means *no trend*, which is what one gameweek of samples buys —
    and never 0.0, which is the different and stronger claim that nobody in
    the top 10k starts him. Same contract as ``field_eo`` above.
    """
    field_eo_delta: float | None = None
    """The observed move between the last two sampled gameweeks, in points of
    EO. ``None`` when there is no earlier sample; ``0.0`` is a measurement —
    the field held steady."""
    field_class: Literal["shield", "sword", "threat"] | None = None
    """``shield`` | ``sword`` | ``threat``, or ``None`` for the quadrant with
    nothing to say.

    A ``Literal`` and not a ``str``, since v12 W5: ``routers.players
    .field_class`` returns exactly these three and ``None``, the client has
    always typed it as those three, and only the schema was saying ``str`` —
    which the generated types then repeated, and the pitch's shirt colours
    stopped compiling against."""
    available: bool
    """Whether his status is outside :data:`UNAVAILABLE_STATUS`."""
    status: str
    """FPL's own status code for the player."""
    news: str
    """FPL's own news text for the player."""
    chance_of_playing: float | None
    """FPL's own chance-of-playing percentage."""
    penalties_order: int | None
    """His club's penalty-taking rank, from ``data/set_pieces.toml`` or FPL."""
    free_kicks_order: int | None
    """His club's free-kick-taking rank, from ``data/set_pieces.toml`` or FPL."""
    corners_order: int | None
    """His club's corner-taking rank, from ``data/set_pieces.toml`` or FPL."""
    set_piece_manual: list[str] = Field(default_factory=list)
    """Kinds of set piece whose order above came from ``data/set_pieces.toml``
    rather than from FPL. Empty on every machine with no override file.

    Includes a *cleared* order: a file that lists his club's queue and leaves
    him out serves him ``None``, and that blank is the file's word as much as
    a rank is. Only ``penalties`` reaches expected points; the other two move
    the numbers on this row and nothing else."""
    in_squad: bool
    """Whether he is currently owned."""
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
    """p75 of ``ep_next``'s distribution, same contract as ``ep_lo``."""
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
    """The scoring category this term covers (e.g. minutes, goals, saves)."""
    points: float
    """Its contribution to ``ep`` for this fixture, summed over the
    category's columns."""


class MinutesOutput(BaseModel):
    p_play: float | None = None
    """``None`` — never 0.0 — for a frame banked without a minutes model. Zero
    here reads as "expected not to play", which is the strongest claim this
    payload can make about a player, and the compare radar drew it as a
    zero-length spoke on the minutes axis."""
    p60: float | None = None
    """The same convention, on the probability beside it. 0.0 here is
    "expected off before the hour", which is a forecast a frame banked
    without a minutes model never made — and it is the number ``xmins``
    weights the second half by, so a zero propagates into a claim about
    minutes as well."""
    xmins: float | None = None
    """Expected minutes, ``p_play * (45 + 45 * p60)``. ``None`` when either
    probability is missing: an un-modelled player is not a player expected to
    play no minutes."""


class OddsInfluence(BaseModel):
    weight: float
    """How much the bookmaker odds blend counts for this fixture, 0-1;
    0.0 for a frame banked before the blend existed."""
    e_goals_against: float | None
    """The odds market's own expected goals against, when priced."""
    p_cs_model: float
    """The team model's own P(clean sheet), before any odds blend."""
    p_cs_blended: float
    """P(clean sheet) after blending with the odds market, or the model's
    own figure when there is no market weight."""
    e_gc_model: float
    """The team model's own expected goals conceded, before any odds blend."""
    e_gc_blended: float
    """Expected goals conceded after blending with the odds market, or the
    model's own figure when there is no market weight."""


class FixtureExplain(BaseModel):
    gw: int
    """The gameweek this fixture falls in."""
    opponent: str
    """The opponent's name."""
    home: bool
    """Whether the fixture is at home."""
    kickoff_time: str | None
    """ISO kickoff time, or ``None`` when not yet known."""
    components: list[Component]
    """The scoring categories that summed to ``ep``, each with nonzero
    columns."""
    minutes: MinutesOutput
    """The minutes model's own prediction for this fixture."""
    calibration_delta: float
    """The fitted EP calibration's adjustment for this position, 0.0 when
    the frame carries no calibration column."""
    odds: OddsInfluence
    """How the bookmaker odds influenced this fixture's team numbers."""
    ep: float
    """Expected points for this fixture, the sum ``components`` explains."""


class UpcomingFixture(BaseModel):
    """One of the next three league games, as the explain panel lists them.

    Deliberately *not* ``NextFixture`` (``:87``), whose name it shadowed until
    v12 W5: that one is the advised gameweek's single game, with an opponent
    short name, a kickoff and a difficulty; this one is a gameweek number and
    an opponent's full name. Two response models under one name gave the
    schema generator two definitions it could only tell apart by mangling
    both, and gave every ``from .schemas import NextFixture`` in the tree the
    second class rather than the first.
    """

    gw: int
    """The gameweek of this upcoming fixture."""
    opponent: str
    """The opponent's full name."""
    home: bool
    """Whether the fixture is at home."""


class PlayerExplain(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name."""
    position: str
    """GKP, DEF, MID or FWD."""
    team_name: str
    """His club's name."""
    ep_next: float
    """Expected points for the first horizon gameweek, summed from
    ``fixtures``."""
    fixtures: list[FixtureExplain]
    """The scoring breakdown for every horizon fixture found in the banked
    components."""
    next_fixtures: list[UpcomingFixture]
    """His next three league games, off the fixtures snapshot."""
    set_pieces: dict[str, int | None]
    """``penalties`` / ``free_kicks`` / ``corners``, each the user's override
    file's word where it has one and FPL's otherwise — the same numbers
    :class:`PlayerRow` serves, from the same loader."""
    set_pieces_manual: list[str] = Field(default_factory=list)
    """Which of ``set_pieces``' three orders came from the user's override
    file, a cleared one included. Additive and default-empty, so a client that
    does not read it is unaffected."""


# --- Planning: the chip plan and the chip workbench -----------------------


class ChipWeek(BaseModel):
    gw: int
    """A gameweek the chip could be played in."""
    gain: float
    """Total expected-points gain from playing the chip in ``gw``, from
    ``optimize/chips.py``'s ``evaluate_chips``."""
    per_week: float
    """``gain`` divided by the horizon weeks the chip is credited with — the
    weeks from ``gw`` onwards for a wildcard, one for every other chip."""


class ChipPlanRow(BaseModel):
    chip: str
    """The chip this row is about: wildcard, bench boost, free hit or triple
    captain."""
    weeks: list[ChipWeek]
    """Every horizon gameweek this chip could be played in, with its gain."""
    best_gw: int
    """The gameweek with the best ``per_week`` gain — not necessarily the
    best total (``optimize.chips.chip_plan``)."""
    best_gain: float
    """The total gain at ``best_gw``."""
    best_gain_per_week: float
    """The per-week gain at ``best_gw`` — the figure ``best_gw`` is chosen on."""
    weeks_scored: int
    """How many gameweeks were looked at, so the UI can say how far ahead
    "best" reaches rather than implying the whole season."""
    now_gain: float | None
    """The gain if played this gameweek, or ``None`` when it cannot be
    played now."""
    play_now_delta: float | None
    """``now_gain`` minus ``best_gain`` — the total-points price of playing
    now rather than waiting, or ``None`` when it cannot be played now."""

    threshold_now: float | None = None
    """θ for this chip in the current gameweek: the surplus the best remaining
    week is expected to offer. ``chip_plan`` has always computed it and this
    model has never declared it, so until v10b it was computed and dropped —
    the ``odds_blend_weight`` failure, repeated. An undeclared field never
    reaches the page and nothing fails while it doesn't."""

    play_now: bool | None = None
    """Whether ``now_gain`` clears ``threshold_now`` — the chip policy's own
    verdict on playing this week rather than waiting."""

    threshold_source: str | None = None
    """See ``ChipWorkbenchRow.threshold_source``. Filled at the router from the
    same lookup ``thetas`` is built from (v12 W3 §4.2)."""

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
    """The gameweek the plan was solved from."""
    chips: list[ChipPlanRow]
    """One row per chip, best gain first."""


class ChipWorkbenchRow(BaseModel):
    """One (chip, gameweek) cell of the advice run's own chip table.

    ``threshold`` is the θ bar that week — the surplus the best remaining week
    is expected to offer — so the workbench can draw the gain against the bar
    rather than against an arbitrary axis. Both it and ``play_now`` are
    optional because an advice payload written before the chip policy landed
    carries neither.
    """

    chip: str
    """The chip this cell prices: wildcard, bench boost, free hit or triple
    captain."""
    gw: int
    """The gameweek this cell is for."""
    gw2: int | None = None
    """The second week of a chip *pair* — the bench boost's, where ``gw`` is
    the wildcard's. ``None`` on every single-chip row, which is every row on
    every payload written before v12 and every row until the fixture list
    carries a double."""

    gain: float
    """Expected-points gain from playing the chip in this cell, as the
    advice run's own chip table priced it."""
    per_week: float | None = None
    """``gain`` divided by the weeks it is credited with."""
    threshold: float | None = None
    """The θ bar this gain is judged against — see the class docstring."""
    threshold_source: str | None = None
    """Where ``threshold`` came from: ``"theta"``, or ``"flat: <reason>"``.

    Three distinct fallbacks produce a flat bar and they are not the same
    news — no asset, no surplus for this chip, a gameweek outside the
    calibrated window — so the reason travels with the number rather than
    being guessed at from it. ``None`` on a payload written before v12
    (v12 W3 §4.2)."""

    play_now: bool = False
    """Whether ``gain`` clears ``threshold`` this cell."""
    note: str | None = None
    """A caveat on this cell, when the advice run's chip table wrote one."""


class SquadPlayerRef(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name."""
    position: str
    """GKP, DEF, MID or FWD."""
    price: float
    """His price in £m — cost to buy or hold, sell price for a squad he is
    leaving (`routers/chips.py`'s ``_refs``)."""
    ep: float
    """Expected points, from the saved pool's first horizon gameweek."""


class SquadDiff(BaseModel):
    """A candidate squad against the one you own, resolved server-side."""

    gain_over_horizon: float
    """Expected-points gain of the candidate squad over the owned one,
    summed across the solve horizon."""
    recommend: bool
    """Whether ``gain_over_horizon`` clears ``threshold``."""
    threshold: float | None = None
    """The bar ``recommend`` was decided against. Until v12 this was always
    the flat 8.0 and was never served, so the card asserted a verdict and
    showed nothing of the rule behind it (v12 W3 §4.2)."""

    threshold_source: str | None = None
    """See ``ChipWorkbenchRow.threshold_source``."""

    kept: list[SquadPlayerRef]
    """Owned players the candidate squad keeps."""
    dropped: list[SquadPlayerRef]
    """Owned players the candidate squad does not keep, priced at sell value."""
    added: list[SquadPlayerRef]
    """Players the candidate squad brings in that were not owned."""


class ChipsWorkbench(BaseModel):
    gw: int
    """The gameweek the workbench is showing."""
    chips: list[ChipWorkbenchRow]
    """Every (chip, gameweek) cell in the advice run's own chip table."""
    wildcard: SquadDiff | None = None
    """The wildcard candidate squad against the owned one, or ``None`` when
    the advice payload carries no ``wildcard_now``."""


# --- Players: the saved EP decomposition ----------------------------------


class ComponentFixture(BaseModel):
    """One player-fixture's additive terms.

    Deliberately shaped like :class:`FixtureExplain` (the explain modal's
    per-fixture row) without being it: this one is read from the saved
    components parquet with no model loading at all, and carries only what a
    why-panel renders.
    """

    gw: int
    """The gameweek of this fixture."""
    opponent: str
    """The opponent's name."""
    home: bool
    """Whether the fixture is at home."""
    kickoff_time: str | None
    """ISO kickoff time, or ``None`` when not yet known."""
    components: list[Component]
    """The scoring categories that summed to ``ep``, from the saved
    components parquet."""
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
    """The minutes model's own prediction for this fixture."""
    ep: float
    """Expected points for this fixture, the sum ``components`` explains."""


class ComponentPlayer(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name."""
    position: str
    """GKP, DEF, MID or FWD."""
    team_name: str
    """His club's name."""
    ep: float
    """Summed over every fixture in this payload — a horizon total, not a
    gameweek's, because the components parquet carries the whole solve
    horizon."""
    fixtures: list[ComponentFixture]
    """Every horizon fixture's breakdown from the saved components parquet."""
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
    """p75 of ``ep_gw``'s distribution, same contract as ``ep_lo``."""
    p_haul: float | None = None
    """``uncertainty.Band.p_haul``: P(total points >= 10) in the tail of the
    whole forecast. The advice payload's attacking quantity is a different
    number on a different scale and is served as ``p_attacking_haul``
    (spec D3)."""
    p_blank: float | None = None
    """``P(points <= 2)`` under the same distribution."""


class ComponentsBreakdown(BaseModel):
    gw: int
    """The gameweek this breakdown was requested for."""
    players: list[ComponentPlayer]
    """Every candidate's EP decomposition for this gameweek."""


# --- This Week: what moved since the last run -----------------------------


class AdvicePlayer(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name, as stored on the advice payload being diffed."""


class EpMover(BaseModel):
    """One player the newest retrain moved, in the gameweek being decided."""

    code: int
    """FPL player code."""
    name: str
    """Player name."""
    ep_prev: float
    """Expected points before the newest retrain."""
    ep_now: float
    """Expected points after the newest retrain."""
    delta: float
    """``ep_now - ep_prev``, points."""


class AdviceDiff(BaseModel):
    """What changed between the two newest runs of one gameweek.

    ``available`` is false on a first run of the week — the ordinary case, not
    an error — and everything else is then empty, so the client renders
    nothing without having to special-case a status code.
    """

    gw: int
    """The gameweek being diffed, or the ``b`` week-against-week path's target."""
    available: bool
    """Whether two runs exist to compare — false on a first run of the week."""
    changed: bool = False
    """Whether anything in the plan moved, from ``diff_advice`` in
    `artifacts.py`: any buy, sell, captain or chip change, or a nonzero
    expected-points delta."""
    previous_at: str | None = None
    """Timestamp stem of the earlier of the two compared files."""
    current_at: str | None = None
    """Timestamp stem of the later of the two compared files."""
    gw_from: int | None = None
    """v19e §2.1: set only on the week-against-week path (``?a=&b=``), so a
    client can tell "last run of this gameweek" from "last gameweek"."""
    gw_to: int | None = None
    """The ``b`` gameweek on the week-against-week path, paired with ``gw_from``."""
    buys_added: list[AdvicePlayer] = Field(default_factory=list)
    """Players in ``buys`` now that were not in the earlier run."""
    buys_dropped: list[AdvicePlayer] = Field(default_factory=list)
    """Players in the earlier run's ``buys`` that dropped out."""
    sells_added: list[AdvicePlayer] = Field(default_factory=list)
    """Players in ``sells`` now that were not in the earlier run."""
    sells_dropped: list[AdvicePlayer] = Field(default_factory=list)
    """Players in the earlier run's ``sells`` that dropped out."""
    captain_from: AdvicePlayer | None = None
    """The earlier run's captain, set only when the captain changed."""
    captain_to: AdvicePlayer | None = None
    """The later run's captain, set only when the captain changed."""
    chip_from: str | None = None
    """The earlier run's recommended chip, set only when it changed."""
    chip_to: str | None = None
    """The later run's recommended chip, set only when it changed."""
    expected_pts_delta: float = 0.0
    """Later run's ``expected_pts`` minus the earlier run's, rounded to 2dp."""
    ep_movers: list[EpMover] = Field(default_factory=list)
    """Players whose expected points moved between the two newest component
    breakdowns. Independent of ``available``: a first run of the week has no
    plan to diff and may still have a retrain to report (plan A10)."""
    ep_movers_count: int | None = None
    """How many moved, or ``None`` when there is no predecessor breakdown to
    compare against. ``None`` and ``0`` are different claims — "we have not
    retrained since you looked" against "the retrain changed nothing" — and
    the strip renders only the second."""


# --- This Week: the team news panel ---------------------------------------


class NewsRow(BaseModel):
    """One player the news layer moved, with the evidence that moved him.

    Both sides of every number, because the panel's claim is a *difference*:
    "we think 5%, the official flag says 75%" is the sentence, and either half
    on its own is not.
    """

    code: int
    """FPL player code."""
    name: str
    """Player name, from the live players snapshot."""
    team_name: str
    """Player's club name, from the live teams snapshot."""
    p_play_news: float
    """This run's P(starts), as predicted from the news-aware availability
    frame, rounded to 3dp."""
    p_play_flags: float
    """P(starts) as it would read off the official flag alone, rounded to
    3dp — the comparison figure ``p_play_news`` disagrees with."""
    e_min_news: float
    """Expected minutes under the news-aware reading, rounded to 1dp."""
    e_min_flags: float
    """Expected minutes under the official-flag-only reading, rounded to 1dp."""
    # Official flag, from the bootstrap snapshot.
    status: str | None = None
    """FPL's own status code for the player (e.g. injured, doubtful), from
    the live players snapshot."""
    chance_of_playing: float | None = None
    """FPL's own percentage chance of playing, from the live players
    snapshot."""
    official_note: str | None = None
    """FPL's own news text for the player, from the live players snapshot."""
    # The availability frame this run predicted on.
    injury_type: str | None = None
    """The injury or absence category this run's availability frame recorded
    for him, when it has one."""
    expected_return_gw: int | None = None
    """The gameweek the availability frame expects him back, when known."""
    p_start_hint: float | None = None
    """The availability frame's own P(starts), separate from the news-model
    figures above."""
    lineup_hint: str | None = None
    """``xi`` / ``doubt`` / ``out`` — ``p_start_hint`` named, because a
    probability in a caption reads as a forecast rather than as a listing."""
    source: str | None = None
    """Where the availability evidence came from (e.g. a news feed name)."""
    fetched_at: str | None = None
    """ISO timestamp the availability evidence was fetched."""


class NewsPanelData(BaseModel):
    gw: int
    """The gameweek the panel is reporting on."""
    moved: int
    """How many players cleared ``MOVED_EPSILON`` between the news-aware and
    flag-only readings — ``len(rows)``."""
    rows: list[NewsRow]
    """The moved players, biggest disagreement first."""


# --- Model: the run history and its price series --------------------------


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


# --- jobs and health: what is fresh, what is stale, what broke ------------


class SourceHealth(BaseModel):
    source: str
    """The ingested source's name, from ``DATA_SOURCES`` or the odds bank."""
    path: str
    """Where it lives under ``data/``, for ``_stat`` in `routers/meta.py`."""
    present: bool
    """Whether the file exists on disk."""
    modified_at: str | None
    """When it was last written, or ``None`` if it never was."""
    age_hours: float | None
    """Hours since ``modified_at``, or ``None`` when the source is absent."""


class ModelHealth(BaseModel):
    name: str
    """The model's filename stem, from its ``.meta.json`` sidecar."""
    saved_at: str | None
    """When the model was fitted, from the sidecar's ``saved_at`` key."""
    metrics: dict[str, Any]
    """The rest of the sidecar's contents — whatever the trainer recorded."""


class CalibrationHealth(BaseModel):
    """The fitted EP calibration, one delta per position group (v19g §2.1).

    A position is fitted only once it has ``min_rows`` 60-minute appearances
    (``models/calibrate.py``, ``MIN_ROWS``), so the GKP row arrived by accrual
    part-way through a season and nothing anywhere said so. Nothing said when
    one dropped back out either, which is the failure this reports: an
    unfitted position is the identity, and identity is indistinguishable from
    "calibrated to zero" unless the absence is named.
    """

    by_pos: dict[str, float]
    """Position group -> the additive correction a nailed starter takes."""

    fitted_positions: list[str]
    """The keys of ``by_pos``, in ``GKP DEF MID FWD`` order."""

    missing: list[str]
    """Which of the four groups carry no fitted delta, in the same order."""

    min_rows: int
    """The floor a group must clear to be fitted at all — the number the tab
    quotes when it says why a position is absent."""

    saved_at: str | None
    """From the model's own ``.meta.json`` sidecar, or ``None`` when there is
    none: an artifact old enough to predate the sidecar still renders."""


class TeamModelHealth(BaseModel):
    """The week's goals-conceded band, read off the banked components.

    v19g §2.2: over GW4-6 the raw ``p_cs_model`` spanned 0.085-0.957 and every
    GW6 club-fixture carried ``odds_weight = 0``, so a third of the horizon
    was priced on the unbounded team model with no market to blend against.
    The clip itself is replay-gated (v20); naming the band and the zero-odds
    count costs nothing and is what makes the drift visible in the meantime.
    """

    gw: int
    """The newest gameweek in the file, which is the week these numbers
    describe."""

    min_e_gc_model: float
    """The lowest expected-goals-conceded the team model reached this week."""
    max_p_cs_model: float
    """The two ends the model actually reached this week. A minimum expected
    goals-conceded near zero and a clean-sheet probability near one are the
    same fixture seen twice."""

    fixtures: int
    """Club-fixtures after de-duplication, not player rows."""

    zero_odds_fixtures: int
    """How many of those were priced with no market at all — ``odds_weight``
    zero or absent."""


class LaunchdHealth(BaseModel):
    log: str
    """Path to the advise job's redirect log."""
    present: bool
    """Whether that log file exists."""
    modified_at: str | None
    """When it was last written, or ``None`` if it never was."""
    last_line: str | None
    """The log's last non-blank line — the advise job's own report of what
    it did."""


class JobHealth(BaseModel):
    """One ``scripts/com.gaffer.*.plist``, read off disk.

    v19a §2.3: the Health tab knew when the *advise* log last moved and
    nothing at all about the other eight jobs, so a launchd agent that had
    stopped being loaded was invisible until a number on another page went
    quietly stale.
    """

    label: str
    """The plist's ``Label`` minus the ``com.gaffer.`` prefix."""
    schedule: str
    """When it is meant to run, as a sentence — "Thu 18:00", "daily 23:15"."""
    log: str
    """The ``logs/<x>.log`` the plist redirects into, or "" when it names
    none. This is the file whose mtime the age below is measured from."""
    modified_at: str | None
    """When that log was last written, or ``None`` when it never was."""
    age_hours: float | None
    """Hours since the last run, or ``None`` for "never" — never 0.0 for an
    absent log, for ``FreshnessRow.age_hours``' reason."""
    interval_hours: float
    """Hours between scheduled runs, from the calendar entries."""
    overdue: bool
    """Has it missed a run? Half an interval of grace, because a job that
    takes a minute to start should not alarm the page that watches it."""


class ArtifactItem(BaseModel):
    name: str
    """The file's path under ``reports/``, e.g. ``reports/health.json``."""
    bytes: int
    """File size in bytes, from ``path.stat().st_size``."""


class FreshnessRow(BaseModel):
    source: Literal["refresh", "odds", "field", "advise", "backup",
                    "prices", "snapshot"]
    """Which of the seven standing jobs this row reports on."""
    path: str | None = None
    """What was actually stat'd, so a surprising age is diagnosable."""
    modified_at: str | None = None
    """When the file was last written, or ``None`` when it never was."""
    age_hours: float | None = None
    """Hours since the file was written, or ``None`` for "never".

    Never 0.0 for an absent file. Zero is "just now", which is the strongest
    claim this row can make and the exact opposite of what an absent file
    means. The client colours on ``None`` first and on the number second.
    """
    cadence_hours: float
    """How often the job that writes this file is meant to run.

    v19a §2.2: the strip used to colour on absolute hours, which called a
    90-hour-old nightly price bank fresh and a 90-hour-old weekly advice
    stale — both backwards. Served rather than hard-coded on the client so
    the rule lives beside the schedule it describes.
    """


class Freshness(BaseModel):
    rows: list[FreshnessRow] = Field(default_factory=list)
    """One row per standing job (v12 W1 §2.9, v19a §2.2)."""


class BackupHealth(BaseModel):
    path: str
    """The newest backup archive's path, from ``gaffer.backup.latest_backup``."""
    modified_at: str
    """When it was written."""
    bytes: int
    """Its size on disk."""


class CoreInsightsTable(BaseModel):
    table: str
    """The core-insights table's name."""
    rows: int
    """How many rows the collector has banked for it."""
    latest: str | None = None
    """Newest kickoff date in the table, ``YYYY-MM-DD``, or ``None`` when the
    table has no dated rows. A table with rows and no date is possible — the
    player table is keyed on gameweek, not on a timestamp — and reads as its
    highest gameweek instead."""


class CoreInsightsHealth(BaseModel):
    season: str
    """The season the collector fetches for, from config or its default."""
    collected: bool
    """Whether any of the collector's tables exist for ``season``."""
    tables: list[CoreInsightsTable]
    """Row counts and latest date per table, when ``collected`` is true;
    empty otherwise."""
    waiting_for: str | None = None
    """What has to happen before these numbers mean anything, or ``None`` when
    they already do. Spec §1: a view whose data does not exist yet says what
    it is waiting for and never renders zeros as if they were measurements."""


class Health(BaseModel):
    data: list[SourceHealth]
    """One row per ingested source, from ``DATA_SOURCES`` plus the odds bank."""
    # File mtimes say when the ingest ran; this says what it got.
    data_through_gw: int | None = None
    """The last gameweek ``ingested_through()`` finds fully scored on disk."""
    models: list[ModelHealth]
    """Every fitted model's ``.meta.json`` under ``MODELS_DIR``."""
    calibration: CalibrationHealth | None = None
    """The fitted EP calibration's deltas, or ``None`` when no calibration
    artifact is on disk (v19g §2.1). Absent is a real state — a clone that has
    never trained — and it is not the same news as a calibration fitted on
    three positions, which is why the four-way ``missing`` list travels with
    the values rather than being inferred from a short dict at the page."""
    team_model: TeamModelHealth | None = None
    """The newest banked components' goals-conceded band (v19g §2.2), or
    ``None`` when nothing has been banked or the file predates the model
    columns."""
    launchd: LaunchdHealth
    """The advise job's own log health, kept separate from ``jobs`` below."""
    jobs: list[JobHealth]
    """Every installed plist and whether it has run lately (v19a §2.3).

    ``launchd`` above stays: it carries the advise log's *last line*, which
    is the one job whose output a reader wants quoted rather than dated.
    """
    odds_key_present: bool
    """Whether ``config.toml``'s ``[odds] api_key`` is set — never the key
    itself."""
    model_health: dict[str, Any] | None
    """``reports/health.json``'s contents, whatever a fit run last wrote
    there, or ``None`` when no such report exists."""
    artifacts: list[ArtifactItem]
    """Every file under ``reports/``, name and size."""
    season_ok: bool | None = None
    """Does the banked data's season match ``config.current_season``?

    Three states, not two. ``None`` is *cannot tell* — no events snapshot, or
    deadlines that will not parse — and it is not an alarm: a cold clone has
    no data to disagree with. The banner draws on ``False`` alone.
    """
    season_config: str | None = None
    """What ``config.toml`` says this season is."""
    season_ingested: str | None = None
    """What the last refresh actually banked, derived from the events' own
    deadlines. Read off disk, never off the API: this endpoint is polled by a
    tab and must not depend on FPL being up."""
    solver_top_n: dict[str, int] | None = None
    """Players per position the solver may consider, on top of the ones you own.

    Named for what it is on the wire — a solver pool — since a schema field
    carries no TOML section with it. The value is
    ``config_in_force().solver_top_n()``'s, so it is what an actual solve
    would get rather than what the file says.
    """
    last_backup: BackupHealth | None = None
    """The newest ``gaffer-*.tar.gz`` in the configured backup directory.

    ``None`` means *never*, and the tab renders it as "never — run `gaffer
    backup`" rather than as a blank cell. A zero-byte dict would have been the
    other option and it is worse: it renders as a backup that happened and was
    empty, which is the one outcome this feature exists to prevent.
    """
    core_insights: CoreInsightsHealth | None = None
    """The core-insights collector's own state (v12 W4 §5.1)."""


# --- Planning: the fixture ticker -----------------------------------------


class TickerCell(BaseModel):
    gw: int
    """The gameweek this cell rates."""
    opponent: str
    """The opponent's short name."""
    home: bool
    """Whether the fixture is at home."""
    difficulty: float
    """The 0-1 rating, from bookmaker odds when available, else Elo."""


class TickerTeam(BaseModel):
    code: int
    """The club's code."""
    name: str
    """The club's full name."""
    short_name: str
    """The club's short name, as shown on ``cells``."""
    cells: list[TickerCell]
    """One cell per rated gameweek."""
    mean_difficulty: float
    """Mean of ``cells``' difficulty, the figure teams are sorted by."""


class Ticker(BaseModel):
    gws: list[int]
    """Every gameweek rated."""
    source: Literal["odds", "elo"]
    """Whether the ratings came from bookmaker odds or the Elo fallback."""
    teams: list[TickerTeam]
    """Every club, sorted by mean difficulty."""


# --- Model: the evaluation, the shadows and the calibration ---------------


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


class LeadBucket(BaseModel):
    """One band of the lead-time histogram, split by what happened."""

    bucket: str
    started: int
    missed: int


class FlagChange(BaseModel):
    """One (gameweek, player) whose status moved before the deadline."""

    gw: int
    code: int
    first_change: str
    """The snapshot day the status first differed from what it had been —
    the first day a manager could have acted, not the last."""
    lead_days: float
    from_status: str
    final_status: str
    """The last status recorded **before** the deadline. A snapshot taken
    afterwards told nobody anything and is not in this window."""
    chance_of_playing: float | None = None
    started: bool


class FlagLatency(BaseModel):
    """v12 §3.1's readout, or its refusal.

    ``available`` is what the card branches on, and ``note`` is the sentence
    it prints when the answer is no. Both are on the payload rather than in
    the page because the CLI prints the same sentence, and two copies of an
    empty state drift.

    The scorer's ``changes`` — every status move it found, one row each — is
    **deliberately not declared here**, so pydantic drops it on the way out.
    It is the evidence behind the histogram and it stays in the artifact for
    anyone who wants their own bands over it, but nothing on the page reads
    it and it is the only field on this payload that grows without bound: one
    row per player per move per gameweek, all season. ``rows`` carries the
    count that the page does show.
    """

    run_at: str
    git_sha: str
    available: bool = False
    rows: int = 0
    note: str | None = None
    snap_dates: int = 0
    min_snap_dates: int = 14
    covered_gws: list[int] = []
    checked_covered_gws: list[int] = []
    histogram: list[LeadBucket] = []
    late_flags: list[FlagChange] = []


class VerdictRow(BaseModel):
    verdict: str
    n: int
    started: int
    not_started: int


class VerdictScore(BaseModel):
    verdict: str
    n: int
    precision: float
    """P(did not start | this verdict). Absence is the event every class
    claims, which is what makes the four numbers comparable."""
    recall: float


class SourceRows(BaseModel):
    source: str
    rows: int


class PresserGrades(BaseModel):
    """v12 §3.2's readout, or its refusal.

    ``recall_population`` is a field rather than a footnote: recall here is
    over the rows that carried a verdict, and the same word over every absent
    player in the gameweek would be a much harsher number about a much larger
    population.
    """

    run_at: str
    git_sha: str
    available: bool = False
    rows: int = 0
    note: str | None = None
    verdicts_banked: int = 0
    graded_gws: list[int] = []
    absent_rows: int = 0
    confusion: list[VerdictRow] = []
    per_class: list[VerdictScore] = []
    by_source: list[SourceRows] = []
    recall_population: str = "verdict-carrying rows"


class Quality(BaseModel):
    """Whichever modes have been run. Each is independent and may be absent."""

    current: CurrentEvaluation | None = None
    benchmark: BenchmarkEvaluation | None = None
    decomposition: Decomposition | None = None
    # v6: `gaffer evaluate --news-shadow` has written this key since v5, but
    # nothing declared it here, so it never reached the page.
    news_shadow: NewsShadow | None = None
    # v12 W2 §3.1/§3.2 (specs/2026-09-01-gaffer-v12-program-design.md). Same
    # trap news_shadow fell into for a cycle: the CLI writes the key, and an
    # undeclared field is dropped here without a word.
    flag_latency: FlagLatency | None = None
    presser_grades: PresserGrades | None = None


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


# --- Planning: the multi-week plan timeline -------------------------------


class PlanMove(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name."""
    position: str
    """GKP, DEF, MID or FWD."""
    ep: float
    """Expected points for the week this move is made in."""
    price: float | None = None
    """Buy price for an in, sell value for an out — in millions."""


class PlanGw(BaseModel):
    gw: int
    """The gameweek this week of the plan is for."""
    buys: list[PlanMove]
    """Players bought this week."""
    sells: list[PlanMove]
    """Players sold this week."""
    hits: int
    """Hits taken this week."""
    hit_cost: int
    """Points those hits cost."""
    chip: str | None = None
    """The chip played this week, if any."""
    captain: PlanMove | None = None
    """The captain this week."""
    vice: PlanMove | None = None
    """The vice-captain this week."""
    expected_pts: float
    """Expected points for this week alone, net of hits."""
    bank: float | None = None
    """What is left in the bank after this week's moves, in millions.

    ``None`` means *unknown*, and it means it for one reason: some move in
    this week or an earlier one had no price, so the running total is broken
    and stays broken. Never 0.0 — that is "fully invested", which is a real
    and different state a manager can be in.
    """
    trace: PlanWeekTrace | None = None
    """Why this week's moves, in the objective's own terms (v12 W5 §6.5).

    ``None`` only when the trace could not be computed at all — a week that
    does nothing carries a trace with no moves, because "this week does
    nothing" and "the trace is broken" must not look alike on the board.

    Always ``None`` on an alternative plan: the trace is the objective's terms
    at the plan the solver *returned*, and Plan B was returned by a different
    solve. The board says so under the strip.
    """


class PlanAlternative(BaseModel):
    """A plan the solver ranked behind the recommended one (v12 W3 §4.3)."""

    label: str
    """``"Plan B"`` / ``"Plan C"``, assigned by position at the router. The
    artifact stores the order and not the name, so a payload written by one
    build reads correctly on another."""
    gap: float | None = None
    """Objective points behind the recommended plan — **signed**.

    Negative means this plan prices *above* the recommendation, which happens
    because the recommendation carries the scenario sweep's moves as
    constraints and this one does not. ``None`` when the artifact's number
    could not be read; never 0.0, which is "exactly level".
    """
    weeks: list[PlanGw]
    """This alternative's plan, one entry per horizon gameweek."""


class PlanTimeline(BaseModel):
    gw: int
    """The gameweek the plan was solved for."""
    generated_at: str
    """ISO timestamp the plan was generated."""
    weeks: list[PlanGw]
    """The recommended plan, one entry per horizon gameweek."""
    bank: float | None = None
    """What is in the bank before the horizon's first move, in millions.

    ``SolveState.bank`` in tenths, through the same conversion every price on
    this payload takes. ``None`` means the solve state carried no usable
    figure — never 0.0, which is "fully invested".
    """

    alternatives: list[PlanAlternative] = []
    """Empty on every artifact written before v12, and on any run with
    ``[optimizer] alt_plan_max_gap = 0``. The board draws no tab strip for an
    empty list rather than a strip with one tab in it (v12 W3 §4.3)."""

    objective: PlanGw | None = None
    """v16 §4: the solver's own week one, traced, when the served plan is a
    different rung of the ladder. ``None`` when they agree or when the
    payload predates the field."""


# --- Players and Planning: the fixture matrix and the outlook -------------


class MatrixCell(BaseModel):
    gw: int
    """The gameweek this cell rates."""
    opponent: str
    """The opponent's short name."""
    home: bool
    """Whether the fixture is at home."""
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
    """The club's code."""
    name: str
    """The club's full name."""
    short_name: str
    """The club's short name, as shown on ``cells``."""
    cells: list[MatrixCell]
    """One cell per rated gameweek."""
    mean_attack: float
    """Mean of ``cells``' attack difficulty."""
    mean_defence: float
    """Mean of ``cells``' defence difficulty."""


class FixtureMatrix(BaseModel):
    gws: list[int]
    """Every gameweek rated."""
    teams: list[MatrixTeam]
    """Every club's attack and defence ratings."""
    source: Literal["dixon_coles", "none"]
    """Whether the ratings came from the Dixon-Coles model or there was
    nothing to rate."""


class OutlookTeam(BaseModel):
    """A club in the outlook. ``short_name`` is null when the teams snapshot
    could not be read — the counts are still true, only the label is missing,
    and losing the whole answer over a cosmetic join is the wrong trade."""

    code: int
    """The club's code, or the raw FPL team id when ``teams_known`` is false."""
    short_name: str | None = None
    """The club's short name, or ``None`` when the teams snapshot could not
    be read."""


class OutlookWeek(BaseModel):
    gw: int
    """The gameweek this row is about."""
    fixtures: int
    """How many fixtures fall in this gameweek."""
    doubles: list[OutlookTeam] = Field(default_factory=list)
    """Clubs with more than one fixture this gameweek."""
    blanks: list[OutlookTeam] = Field(default_factory=list)
    """Clubs with no fixture this gameweek."""


class FixtureOutlook(BaseModel):
    """Doubles and blanks in the season ahead (v10b §F2a).

    Every failure is a 200 with a ``note`` rather than an error: this renders
    as one card beside populated cards, and a 422 there is indistinguishable
    from a broken endpoint.
    """

    from_gw: int | None = None
    """The first gameweek in ``weeks``, or ``None`` when there is nothing to
    show."""
    weeks: list[OutlookWeek] = Field(default_factory=list)
    """The season's remaining gameweeks, doubles and blanks per week."""
    has_doubles: bool = False
    """Whether any served week has a double gameweek."""
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
    """Why the card is empty, when it is — a missing fixture list, an
    unreadable one, or nothing to report."""


# --- Model: the decision journal ------------------------------------------


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


# --- Model: the penalty-taker tracker -------------------------------------


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


# --- Model: the season review ---------------------------------------------


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


class DecisionRef(BaseModel):
    """The deviation note beside a grade (v16 §5)."""

    reason: str | None = None
    text: str = ""
    at: str | None = None


class ReasonTally(BaseModel):
    """One reason code's row in the season tally: how many graded gameweeks
    carried it, and the mean transfers-lane delta over them."""

    reason: str
    count: int
    mean_delta_pts: float | None = None


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
    projection_snapshot: str | None = None
    """The UTC stamp of the frozen EP table this grade was read against.

    ``None`` for a gameweek graded before v12 W5 existed, and for one where no
    snapshot was ever written. Grades are banked and never re-derived (spec
    D2), so every row already in the ledger keeps ``None`` for ever and the
    column fills forward from the next graded week — drawn as absent, never as
    a zero or a blank that reads like one.
    """
    projection_post_deadline: bool = False
    """The snapshot named above cannot be trusted to predate the deadline.

    **Two causes, and the reader must not be told only the first.** Either
    every snapshot for the gameweek was written after the deadline, or the
    run did not record when the deadline was — which is the ordinary state of
    a gameweek graded late, after ``ADVICE_HISTORY_KEEP`` pruned the payload
    the deadline was carried on. In that second case an in-time snapshot may
    well exist on disk; there is simply nothing left to compare its stamp
    against, and guessing would be worse than saying so.

    Either way the claim is the same and it is the weaker one: this table may
    have seen team news nobody could act on. Related to ``post_deadline``
    above — which is about the advice payload rather than the EP table — and
    the two can disagree."""
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
    decision: DecisionRef | None = None
    """Why I did something other than what the advice said. ``None`` is "no
    note was written", which is not the same as a note with no reason."""


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
    by_reason: list[ReasonTally] = Field(default_factory=list)
    """The deviation tally, ``REASONS`` order then ``none``. Codes with no
    graded gameweek are absent — a nought would read as a measurement."""


class Review(BaseModel):
    gws: list[ReviewGw] = Field(default_factory=list)
    summary: ReviewSummary | None = None


# --- Planning: the manager's own team news --------------------------------


class OverrideRequest(BaseModel):
    """One pin. At least one of the two values must be present."""

    code: int
    """FPL player code."""
    p_play: float | None = None
    """The manager's own P(plays), overriding the model's."""
    e_min: float | None = None
    """The manager's own expected minutes, overriding the model's."""
    note: str = ""
    """Why the pin was made, in the manager's own words."""


class OverrideRow(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name, from the bootstrap snapshot."""
    p_play: float | None = None
    """The manager's own pinned P(plays)."""
    e_min: float | None = None
    """The manager's own pinned expected minutes."""
    note: str = ""
    """Why the pin was made, in the manager's own words."""
    set_at: str = ""
    """ISO timestamp the pin was saved."""
    model_p_play: float | None = None
    """What the served pipeline had for him when the pin was made, so the
    why-panel can say "the model had 0.82" without re-deriving anything."""
    model_e_min: float | None = None
    """What the served pipeline had for his expected minutes when the pin
    was made."""


class OverridesPanel(BaseModel):
    active: bool = True
    """``[news] overrides``. False means the pins are stored and *not* being
    applied, which the panel says out loud rather than showing nothing."""
    rows: list[OverrideRow] = Field(default_factory=list)
    """Every pin on record."""
    warning: str | None = None
    """Accepted, and worth a second look. Set on a write whose two numbers
    disagree with each other — expected minutes implying a player starts,
    beside a probability of playing that says he probably does not. A refusal
    would be wrong (the manager is allowed to mean it) and silence would be
    worse, so the dialog shows this and stays open."""


# --- Planning: the sensitivity sweep --------------------------------------


class NamedPlayer(BaseModel):
    """A player a report names but does not price."""

    code: int
    """FPL player code."""
    name: str
    """Player name."""
    position: str = ""
    """GKP, DEF, MID or FWD, when known."""


class SensitivityMove(BaseModel):
    kind: str
    """Which decision this move is: a buy, a sell or the captaincy."""
    code: int
    """FPL player code."""
    gw: int
    """The gameweek the move is made in."""
    label: str
    """The move described in prose, for the frequency table."""
    name: str = ""
    """Player name."""
    count: int
    """How many of the sweep's re-solves made this move."""
    frequency: float
    """``count`` divided by the number of completed re-solves."""


class SensitivityPlan(BaseModel):
    count: int
    """How many of the sweep's re-solves reached this exact plan."""
    buys: list[NamedPlayer] = Field(default_factory=list)
    """Players this plan buys."""
    sells: list[NamedPlayer] = Field(default_factory=list)
    """Players this plan sells."""
    captain: NamedPlayer | None = None
    """This plan's captain."""
    hits: int = 0
    """Hits this plan takes."""
    value: float = 0.0
    """Horizon expected points on the **true** EP table, so two signatures are
    compared on the board the manager faces rather than on their own draws."""


class SensitivityReport(BaseModel):
    available: bool = False
    """Whether a sweep for this gameweek was found and is current."""
    gw: int | None = None
    """The gameweek the report is about."""
    k: int = 0
    """How many re-solves the sweep asked for."""
    completed: int = 0
    """How many re-solves actually finished."""
    failures: int = 0
    """How many re-solves failed."""
    seed: int | None = None
    """The RNG seed the sweep's scenarios were drawn with."""
    horizon: int = 0
    """How many gameweeks the sweep solved over."""
    wall_s: float | None = None
    """Seconds the sweep took."""
    generated_at: str | None = None
    """ISO timestamp the sweep was run."""
    notice: str | None = None
    """A caveat on the sweep, e.g. that expected minutes had to be guessed."""
    frequencies: list[SensitivityMove] = Field(default_factory=list)
    """The first horizon week's moves, ranked by how often the sweep made
    them."""
    modal: SensitivityPlan | None = None
    """The plan the sweep reached most often."""
    runner_up: SensitivityPlan | None = None
    """The next most frequent *distinct* plan, or ``None`` when every
    re-solve agreed."""
    margin: float | None = None
    """``modal``'s value minus ``runner_up``'s, on the true EP table."""
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
    """The sweep's one-line summary of the modal plan and the runner-up."""


# --- This Week: the transfer ladder (v13 §3) ------------------------------


class LadderVsBelow(BaseModel):
    """What the extra hit bought, against the previous distinct rung."""

    extra_buys: list[PlayerRef] = Field(default_factory=list)
    """First-week buys this rung makes that the rung below did not."""
    extra_sells: list[PlayerRef] = Field(default_factory=list)
    """First-week sells this rung makes that the rung below did not."""
    dropped_buys: list[PlayerRef] = Field(default_factory=list)
    """The rung below's first-week buys this rung does not make."""
    dropped_sells: list[PlayerRef] = Field(default_factory=list)
    """The rung below's first-week sells this rung does not make."""
    delta_mean_pts: float
    """This rung's mean simulated points minus the rung below's, from
    ``ladder.vs_below``."""
    delta_cost: int
    """The **horizon** hit cost this rung carries over the rung below.
    ``max_hits`` is a per-gameweek cap, so a rung can pay it every week, and
    it is the horizon figure that ``delta_mean_pts`` is net of."""
    delta_cost_now: int = 0
    """The first week's difference alone."""


class LadderWeek(BaseModel):
    gw: int
    """The gameweek this week of the rung's plan is for."""
    hits: int
    """Hits taken in this week alone."""
    buys: list[PlayerRef] = Field(default_factory=list)
    """Players bought in this week of the plan."""
    sells: list[PlayerRef] = Field(default_factory=list)
    """Players sold in this week of the plan."""
    xi: list[PlayerRef] = Field(default_factory=list)
    """The starting eleven this week of the plan."""
    bench: list[PlayerRef] = Field(default_factory=list)
    """The bench this week of the plan."""
    captain: PlayerRef
    """The captain this week of the plan."""
    vice: PlayerRef
    """The vice-captain this week of the plan."""
    expected_pts: float
    """Expected points for this week alone, net of its hits
    (``ladder.plan_points`` over one week)."""


class LadderRung(BaseModel):
    """One row. Every number is ``None`` on a ``same_as`` row, which repeats
    the rung below rather than re-solving it."""

    key: str
    """The rung's identifier: ``"bank"``, ``"open"``, or ``"hits{n}"``."""
    label: str = ""
    """The rung's name in prose (v17b §3.1): ``bank``, ``free transfers
    only``, ``1 hit``, ``no cap``. Every surface renders this; none composes
    it."""
    hits: int
    """Hits taken in the **first** week — the decision on the table now."""
    transfers: int
    """Number of buys in the first week's plan."""
    cost: int
    """The first week's hits, in points."""
    horizon_hits: int = 0
    """Hits over the whole horizon, which is what ``horizon_pts`` and
    ``mean_pts`` are already net of."""
    horizon_cost: int = 0
    """``horizon_hits`` in points."""
    same_as: str | None = None
    """The distinct rung's key this row repeats, when the solve collapsed
    onto an earlier rung's first-week decision (``ladder.collapse``)."""
    plan_by_gw: list[LadderWeek] = Field(default_factory=list)
    """This rung's plan, one entry per gameweek in the horizon."""
    week_pts: float | None = None
    """Expected points for the first week alone, net of its hits."""
    horizon_pts: float | None = None
    """Expected points summed over the whole horizon, net of hits."""
    objective: float | None = None
    """The MILP's own objective value for this rung's solve."""
    mean_pts: float | None = None
    """Mean simulated points across the ladder's shared draws."""
    p10_pts: float | None = None
    """10th percentile of the rung's simulated points."""
    p90_pts: float | None = None
    """90th percentile of the rung's simulated points."""
    p_beats_bank: float | None = None
    """Share of shared draws this rung outscores the bank rung, or ``None``
    for the bank rung itself or when the bank rung did not solve."""
    p_beats_top: float | None = None
    """Share of shared draws this rung outscores the top (highest-hit)
    rung, or ``None`` for the top rung itself."""
    p_best: float | None = None
    """Share of shared draws this rung scores the maximum among all rungs,
    ties split evenly (``ladder.p_best``)."""
    vs_below: LadderVsBelow | None = None
    """What this rung buys over the previous distinct rung, or ``None`` for
    the lowest rung."""


class LadderStep(BaseModel):
    """One step of the restraint walk (v16 §3.1). ``share`` is the share of
    the shared draws in which ``above`` outscored ``below``."""

    below: str
    """The rung key the walk was standing on."""
    above: str
    """The rung key it considered stepping to."""
    share: float
    """Share of the shared draws in which ``above`` outscored ``below``."""
    taken: bool
    """Whether the walk took this step — ``share >= hit_bar``, unless a
    cap refused it first."""
    reason: str = ""
    """Why the step was or was not taken, in prose (``ladder.explain_step``
    or the cap sentence in ``ladder.walk``)."""
    reason_kind: str = "points"
    """``"cap"`` when a hit or transfer cap refused the step; otherwise
    which kind of evidence ``explain_step`` picked."""
    line: str = ""
    """The step as one sentence (v17b §3.1), composed once by
    ``ladder._step_line``."""


class LadderCap(BaseModel):
    max_hits: int | None = None
    """The hit cap the ladder solved every rung under, or ``None`` for none."""
    max_transfers: int | None = None
    """The transfer cap the ladder solved every rung under, or ``None`` for
    none; 0 means bank."""


class LadderPayload(BaseModel):
    gw: int | None = None
    """The gameweek the ladder was built for."""
    gws: list[int] = Field(default_factory=list)
    """Every gameweek in the solve horizon, first entry ``gw``."""
    generated_at: str | None = None
    """ISO timestamp the ladder was built."""
    free_transfers: int | None = None
    """Free transfers available going into ``gw``, from the saved state."""
    cap: LadderCap = Field(default_factory=LadderCap)
    """The hit and transfer caps every rung solved under."""
    cap_source: str | None = None
    """Where ``cap`` came from: ``"config"``, the live settings the card
    writes, or ``"state"`` when that could not be read and the caps the saved
    solve ran under stood in."""
    cap_rung: str | None = None
    """The highlighted row, resolved through ``same_as`` to a row that
    carries numbers."""
    cap_rung_requested: str | None = None
    """The row the saved cap literally names, before that resolution."""
    cap_note: str | None = None
    """Set when the saved ``max_transfers`` has no rung of its own."""
    recommended: str | None = None
    """The rung key the served advice on disk matches, when it matches one."""
    recommended_note: str | None = None
    """Why ``recommended`` is ``None``, when it is."""
    bar: float | None = None
    """The hit bar the walk used (v16 §3.2)."""
    chosen: str | None = None
    """The rung the walk stopped on — the served advice's plan."""
    steps: list[LadderStep] = Field(default_factory=list)
    """The restraint walk's steps, from the lowest rung up to ``chosen``."""
    served_note: str | None = None
    """Set by the router when a rebuild's choice differs from the advice
    on disk."""
    n_draws: int = 0
    """How many Monte Carlo draws the rungs were scored on."""
    seed: int | None = None
    """The RNG seed the draws were built with."""
    sigma_source: str | None = None
    """``"bands"``, ``"outcome"`` or ``"bands+outcome"`` — where the scoring
    σ came from, the mixed value set when some player-week fell back."""
    sigma_fallbacks: int = 0
    """Player-weeks that fell back to the outcome σ for want of a band."""
    wall_s: float | None = None
    """Seconds the solve took, timed from inside ``ladder.ladder_payload``,
    excluding whatever loaded the state beforehand."""
    notes: list[str] = Field(default_factory=list)
    """Rungs dropped because they would not solve."""
    rungs: list[LadderRung] = Field(default_factory=list)
    """Every rung the ladder solved, in ``RUNG_ORDER``."""
    note: str | None = None
    """Why ``rungs`` is empty, when it is: no state, or no ladder banked."""


# --- Planning: the saved drafts and their comparison ----------------------


class DraftRow(BaseModel):
    name: str
    """The draft's name, as the manager saved it."""
    created_at: str = ""
    """ISO timestamp the draft was saved."""
    constraints: WhatIfRequest
    """The what-if lab request this draft pins."""


class DraftList(BaseModel):
    drafts: list[DraftRow] = Field(default_factory=list)
    """Every saved draft."""


class DraftSaveRequest(BaseModel):
    name: str
    """The name to save this draft under."""
    constraints: WhatIfRequest = Field(default_factory=WhatIfRequest)
    """The what-if lab request to pin."""


class DraftCompareRequest(BaseModel):
    names: list[str] = Field(default_factory=list)
    """Which saved drafts to compare, up to :data:`MAX_COMPARE`."""


class DraftCompareRow(BaseModel):
    name: str
    """The draft's name, or the reference row's own label."""
    is_reference: bool = False
    """The unconstrained optimum, so every other row has a "worse than what"."""
    solved_at: str = ""
    """ISO timestamp this row's re-solve completed."""
    horizon_pts: float | None = None
    """Expected points summed over the comparison's shared window."""
    expected_pts: float | None = None
    """Expected points for the first week alone, net of hits."""
    delta_xpts: float | None = None
    """This row's ``horizon_pts`` minus the reference row's."""
    hits: int | None = None
    """Hits this row's plan takes."""
    chip: str | None = None
    """The chip this row's plan plays, if any."""
    horizon: int | None = None
    """Gameweeks this row's plan actually covers, which is not always the
    comparison's. A free hit is a one-week squad; ``DraftCompare.weeks`` is
    the shorter shared window every row was then *scored* over."""
    buys: list[PlayerRef] = Field(default_factory=list)
    """Players this row's plan buys."""
    sells: list[PlayerRef] = Field(default_factory=list)
    """Players this row's plan sells."""
    captain: PlayerRef | None = None
    """This row's plan's captain."""
    error: str | None = None
    """Why this row is empty. An infeasible draft is a row with a reason, not
    a failed comparison."""


class DraftCompare(BaseModel):
    gw: int
    """The gameweek the comparison was solved from."""
    weeks: int
    """The shared window every row was scored over — the shortest plan's
    horizon."""
    rows: list[DraftCompareRow] = Field(default_factory=list)
    """The reference row and every requested draft's re-solve."""


# --- This Week: the confidence line ---------------------------------------


class ConfidenceTier(BaseModel):
    """One record-derived claim, with the counts that back it.

    ``text`` is the whole product — a sentence quoting counts. The counts are
    carried beside it so a caller can style the tier without re-parsing prose,
    never so it can compute a rate: the absence of a percentage anywhere in
    this model is the point of it (spec D3).
    """

    tier: Literal["early", "mixed", "backed"] = "early"
    """How strong the record is, from ``gaffer.confidence.captain_confidence``:
    ``"early"`` below the graded floor, else split on the win rate."""
    reviewed: int = 0
    """Gameweeks with a captaincy lane worth the name — excludes weeks the
    advice was pruned to nothing."""
    graded: int = 0
    """Reviewed gameweeks where the lane was actually comparable. The gap
    between this and ``reviewed`` is the weeks the model's captain was not in
    the eleven, which is not evidence either way."""
    wins: int = 0
    """Graded weeks the model's captain beat mine."""
    losses: int = 0
    """Graded weeks mine beat the model's."""
    aligned: int = 0
    """Weeks I took the model's own captain — reviewed, but not graded, since
    there is nothing to compare."""
    text: str = ""
    """The one sentence quoting these counts, composed by
    ``captain_confidence``."""


class Confidence(BaseModel):
    captain: ConfidenceTier = Field(default_factory=ConfidenceTier)
    """The captaincy record's own tier and counts — the only lane the card
    reports today."""


# --- Model: the misses table ----------------------------------------------


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


# --- Players: the watchlist -----------------------------------------------


class WatchRequest(BaseModel):
    """A star, and optionally a sentence about why."""

    code: int
    """FPL player code to star or update."""
    note: str | None = None
    """Three requests, not two. ``None`` — the key omitted — is "star him and
    say nothing about the note", which keeps whatever note and star date the
    row already has; ``""`` is "clear the note", which is what a cleared
    textbox on the Watchlist tab sends; text sets it.

    The first two used to be one value, so a star from the explorer destroyed
    a note typed on the Watchlist tab. Only a caller that means to write the
    note sends the key at all."""


class WatchRow(BaseModel):
    code: int
    """FPL player code."""
    name: str
    """Player name, from the bootstrap snapshot."""
    note: str
    """The manager's own note on why he is watched."""
    set_at: str
    """ISO timestamp the note was last written."""
    starred_at: str
    """When the star went on, carried unchanged through every later write, so
    a row with no note can say how long it has been watched rather than when
    its note was last touched (v19h §2.2)."""


class WatchlistPanel(BaseModel):
    """Every starred player, name-resolved.

    ``rows`` is empty on a fresh clone and on a broken store alike — the
    distinction is a printed line on the server, not a field here, because a
    client that rendered "your watchlist may be corrupt" would be showing the
    user a problem they cannot act on.
    """

    rows: list[WatchRow] = Field(default_factory=list)
    """Every starred player, sorted by code."""


# --- Planning: the price movers card --------------------------------------


class MoverRow(BaseModel):
    """One watched player FPL's predictor has near a threshold tonight."""

    code: int
    """FPL player code."""
    name: str
    """Player name."""
    now_cost: float
    """In millions, the way the UI shows a price — not the 0.1m integer the
    bootstrap carries."""
    price_change_percent: float
    """FPL's own predictor reading, how close he is to a change tonight."""
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
    """Whether the players snapshot could be read at all."""
    as_of: str | None = None
    """When the underlying snapshot was written — the reading's own age,
    not the request's."""
    rows: list[MoverRow] = Field(default_factory=list)
    """Watched, squad or planned players near a price change tonight."""


# --- This Week: the digest and the LLM brief ------------------------------


class DigestSection(BaseModel):
    """One block of a digest. ``bits`` is prose the client joins.

    The DiffStrip idiom: clauses assembled server-side, rendered by joining
    them, so there is no markdown dependency anywhere in the client. A section
    with no bits never reaches here — the builder drops it (plan A5).
    """

    key: str
    """The section's identifier, distinguishing it for the client's layout."""
    title: str
    """The section's heading."""
    bits: list[str] = Field(default_factory=list)
    """The section's clauses, joined by the client into prose."""


class Digest(BaseModel):
    kind: str
    """``"friday"`` or ``"tuesday"`` — which of the two banked digests this
    is, from ``DIGEST_KINDS``."""
    generated_at: str = ""
    """ISO timestamp the digest was built."""
    gw: int | None = None
    """The gameweek the digest is about."""
    headline: str
    """The digest's one-line summary — the brief's first sentence when a
    brief exists, else a fact composed in `digest.py`."""
    sections: list[DigestSection] = Field(default_factory=list)
    """The digest's body, one entry per non-empty section."""
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
    """Whether a digest was found — the requested kind, or the newer of
    both when no kind was asked for."""
    digest: Digest | None = None
    """The digest, when ``available`` is true."""


class BriefPanel(BaseModel):
    """The newest brief, or the digest to fall back on (v16 §6.5)."""

    gw: int | None = None
    """The gameweek the brief is about."""
    prose: str | None = None
    """The LLM's written brief, once it has passed the truth check."""
    checked_at: str | None = None
    """ISO timestamp the brief was checked and banked, from ``run_brief``."""
    run_stamp: str | None = None
    """The advice run this brief was written against, for staleness checks."""
    model_command: str | None = None
    """The command name of the LLM the brief was generated with."""
    note: str | None = None
    """Why there is no brief for the newest gameweek, when there is none."""
    fallback: DigestPanel | None = None
    """The newest digest, offered in place of a brief that was never
    written or did not pass its truth check."""


# --- This Week: the deviation note ----------------------------------------


class DecisionGrade(BaseModel):
    lane: str = "transfers"
    """Always ``"transfers"``: the one review lane a deviation note grades
    against."""
    label: str | None = None
    """The review ledger's own label for how the lane graded."""
    delta_pts: int | None = None
    """My points minus the model's on the transfers lane, from the review
    ledger."""


class DecisionNote(BaseModel):
    """v16 §5: one gameweek's deviation note and whether it may be edited."""

    gw: int
    """The gameweek the note is for."""
    reason: str | None = None
    """One of ``decisions.REASONS`` — why the manager deviated, or ``None``
    when no note has been saved."""
    text: str = ""
    """The manager's own words, up to ``decisions.TEXT_MAX`` characters."""
    at: str | None = None
    """ISO timestamp the note was saved."""
    state: Literal["before_deadline", "open", "graded"] = "open"
    """Whether the note may still be written: not yet open, open, or closed
    because the gameweek has been graded (``decisions.note_state``)."""
    deadline: str | None = None
    """The gameweek's deadline, from the advice payload or the events
    snapshot."""
    grade: DecisionGrade | None = None
    """The transfers lane's grade, once the gameweek has been reviewed."""


class DecisionWrite(BaseModel):
    reason: str
    """One of ``decisions.REASONS``; refused with ``unknown_reason`` otherwise."""
    text: str = ""
    """The manager's own words, up to ``decisions.TEXT_MAX`` characters."""


# --- Model: the settings tab ----------------------------------------------


class SettingOption(BaseModel):
    """One value a select offers and the word for it (v17e §2.4).

    Served rather than hard-coded on the client so that the words a manager
    picks between are stated once, beside the bound they live inside."""

    value: float | int
    label: str


class SettingRow(BaseModel):
    """One editable setting, as the Settings tab receives it (v12 W5 §6.2)."""

    key: str
    label: str
    kind: Literal["int", "float", "bool", "floats3", "pool", "choice"]
    value: Any
    """Whatever the merged config holds. ``None`` only for ``bench_curve``,
    where it means "no curve — one flat bench weight", which is a real
    setting and not an absent one."""
    lo: float | None = None
    hi: float | None = None
    choices: list[str] = Field(default_factory=list)
    """For ``kind == "choice"`` the allowed strings, in display order (v15
    §4.2). Empty for every other kind."""
    options: list[SettingOption] = Field(default_factory=list)
    """What a select offers, in order, the saved value included when it is
    not offered (v17e §2.5). Empty for a row the tab types into."""
    section: str
    help: str
    source: Literal["local", "base", "default"]
    """Which file this value came from. ``local`` is ``config.local.toml``,
    ``base`` is ``config.toml``, ``default`` is the dataclass — and the three
    are different facts: only a ``local`` value can be reset."""


class SettingsPanel(BaseModel):
    rows: list[SettingRow] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    """Whitelisted settings this build's ``Config`` does not have. Named
    rather than dropped: a form that is quietly shorter is a setting nobody
    can find and nobody knows is missing."""
    overlay_error: str | None = None
    """Why ``config.local.toml`` is being ignored, or ``None``. Also carries
    the "no config.toml at all" case, which is the state a cold clone is in."""
    apply_note: str


class SettingWrite(BaseModel):
    key: str
    value: Any = None
    """``None`` removes the key from the overlay, so the value falls back to
    ``config.toml`` or the dataclass default."""


# --- This Week: the question box (v19f §2.2) -------------------------------


class AskRequest(BaseModel):
    """The body of ``POST /api/ask`` (v19f §2.2)."""

    question: str
    """The manager's own words, refused over 500 characters."""
    gw: int | None = None
    """The gameweek to answer about; ``None`` is the newest on disk."""


class AskAnswer(BaseModel):
    """The job record's ``result`` for ``POST /api/ask`` (v19f §2.2).

    The answer is never banked, so this shape exists only as the job's
    result: the frontend reads it through ``useJob`` and forgets it.
    """

    gw: int | None = None
    """The gameweek whose facts the answer was drawn from."""
    question: str
    """The question as asked, stripped."""
    answer: str
    """The prose, or ``""`` when the command did not answer."""
    offences: list[str] = Field(default_factory=list)
    """``check_brief``'s verdict; non-empty means the answer is not trusted."""
    model_command: str
    """The command's first word, as the brief records it."""
    at: str
    """When the answer was made, UTC."""
