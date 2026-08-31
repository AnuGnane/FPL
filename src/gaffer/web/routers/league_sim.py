"""The simulated league: P(win), P(top 3), and what one week would do to them.

Two endpoints, one engine. ``GET /api/league/sim`` runs the Monte Carlo for
the current gameweek and banks the headline; ``POST /api/league/whatif``
re-runs it with events pinned into the coming week and reports the difference.

Neither touches ``league.py``: ``/api/league/race`` keeps serving the
parametric pairwise numbers, which ride along here as
``legacy_win_probability`` so the card can degrade to them without a second
request. And neither touches ``advise`` — the inputs are artifacts advise
already wrote plus league data that was never an artifact (spec D4).

Every failure is a readable 422, the ``test_web_league.py`` contract: the page
shows a retry button, never a stack trace.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response

from gaffer.artifacts import latest_gw, load_snapshot, solve_state_paths
from gaffer.config import load_config
from gaffer.data.field import field_sample_path
from gaffer.errors import GafferError
from gaffer.league_mode import win_probability
from gaffer.league_sim import (Pins, append_sim_history, build_inputs,
                               load_sim_history, simulate_league)
from gaffer.web.schemas import (LeagueSimData, LeagueWhatIfRequest,
                                LeagueWhatIfResult, LeagueWhatIfRow, RivalBeat,
                                SimPoint, WinProb)

router = APIRouter(prefix="/api/league", tags=["league"])

HAUL_POINTS = 12.0
BLANK_POINTS = 0.0
"""What the panel's two headline events mean in points.

Stated rather than fitted, and stated *here* rather than in the engine: the
engine takes a number, and what counts as a haul is a UI convention. Twelve is
a goal, an assist and the appearance — the week a captain "hauls" in ordinary
FPL speech."""

_CACHE: dict = {}
"""``{key: (LeagueSim, SimInputs)}`` for one gameweek and one advice run.

The League hub, the What-if tab and This Week's chip all want the same answer
inside a second of each other, and the what-if panel wants the *inputs* back
so a pinned re-run does not re-fetch fifty squads. Keyed on the solve state's
mtime, so a fresh advise run invalidates it without anybody clearing anything.
"""


def fpl_client():
    """Seam for tests; the real one is the read-only client the CLI uses."""
    from gaffer.api.client import FPLClient

    return FPLClient()


def _cache_key(cfg, gw: int) -> tuple:
    """Everything the cached answer depends on that can change under it.

    The solve state's mtime, so a fresh advise run invalidates it — and the
    *field sample's*, because since the shared gameweek factor landed the
    banked sample is an input to the arithmetic and not merely to the drift.
    Banking one mid-session used to leave the card serving an independent,
    fan-wide run until the next advise, with a provenance line that had
    already stopped being true.
    """
    _, meta = solve_state_paths(gw)
    stamp = meta.stat().st_mtime if meta.exists() else 0.0
    sample = field_sample_path(str(getattr(cfg, "current_season", "") or ""),
                               max(1, int(gw) - 1))
    field_stamp = sample.stat().st_mtime if sample.is_file() else 0.0
    return (int(cfg.league_id), int(gw), stamp, field_stamp, int(cfg.sim_n),
            float(cfg.rival_drift))


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except GafferError:
        raise
    except Exception as exc:  # noqa: BLE001 — network, JSON, schema drift
        raise GafferError(f"FPL API unavailable ({exc}) — retry in a moment") \
            from exc


def _run(cfg, gw: int | None = None, *, cached_only: bool = False):
    """``(sim, inputs)`` for the current gameweek, cached per advice run.

    ``cached_only`` answers only from the cache and returns ``None`` on a
    miss. This Week's captaincy chip asks for it: that page is the one opened
    on a Thursday evening, its chip is decoration, and building the inputs
    means fifty entry-picks requests at the FPL API — a fetch storm fired by a
    page load, at the hour everybody in the country is loading pages.
    """
    plan_gw = int(gw) if gw is not None else latest_gw()
    if plan_gw is None:
        raise GafferError("no saved advice — run `gaffer advise` first")
    key = _cache_key(cfg, plan_gw)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    if cached_only:
        return None
    inputs = _guard(build_inputs, cfg, fpl_client(), gw=plan_gw)
    sim = simulate_league(inputs, n=int(cfg.sim_n),
                          rival_drift=float(cfg.rival_drift))
    _CACHE.clear()          # one gameweek's answer at a time; this is not an LRU
    _CACHE[key] = (sim, inputs)
    return sim, inputs


@router.get("/sim", response_model=LeagueSimData)
def sim() -> LeagueSimData:
    cfg = load_config()
    gw = latest_gw()
    result, inputs = _run(cfg, gw)
    run_at = datetime.now(timezone.utc).isoformat()
    try:
        append_sim_history(result, int(gw), run_at)
    except Exception:  # noqa: BLE001 — the instrument never blocks the page
        pass
    me = next((e for e in inputs.entries if e.is_me), None)
    my_total = int(me.total) if me else 0
    legacy = [WinProb(name=e.name, total=int(e.total),
                      p_win=round(win_probability(my_total, int(e.total),
                                                  max(1, inputs.weeks_left)),
                                  3))
              for e in inputs.entries if not e.is_me]
    notices = list(result.notices)
    if inputs.field_rate is None:
        notices.insert(0, "no field sample banked for this gameweek yet — "
                          "rivals are simulated on their current squads (run "
                          "`gaffer field-scrape`)")
    # One string because the card has one line for it. A degradation the
    # engine counted is worth more than the field-sample note it used to be
    # the only occupant of, so both are said rather than one shadowing the
    # other.
    notice = " · ".join(notices) if notices else None
    return LeagueSimData(
        gw=int(gw), entries=len(inputs.entries),
        weeks_left=int(inputs.weeks_left), n=result.n, seed=result.seed,
        rival_drift=result.rival_drift, p_win=result.p_win,
        p_top3=result.p_top3, exp_finish=result.exp_finish,
        per_rival=[RivalBeat(**r) for r in result.per_rival],
        margin_quantiles=result.margin_quantiles,
        history=[SimPoint(**h) for h in load_sim_history()
                 if {"gw", "p_win", "p_top3", "exp_finish", "run_at"} <= set(h)],
        field_rate=inputs.field_rate, notice=notice,
        legacy_win_probability=legacy)


EVENT_POINTS = {"blank": BLANK_POINTS, "haul": HAUL_POINTS}
"""``score`` is absent on purpose: it means "his forecast, pinned", which is a
per-player number rather than a constant, and is resolved below."""


def _elements_by_code() -> dict[int, int]:
    """``code -> element`` from the live players snapshot.

    The panel speaks codes because everything else in the UI does; the picks
    speak elements because the API does. One mapping, read from the same
    snapshot the explorer rendered from, so a code the user can see is a code
    this endpoint can resolve.
    """
    try:
        snapshot = load_snapshot("live/players.parquet")
    except Exception:  # noqa: BLE001 — no snapshot means no mapping
        return {}
    return {int(r.code): int(r.element) for r in snapshot.itertuples()}


def _entry_probabilities(sim, inputs) -> list[LeagueWhatIfRow]:
    """The projected table under one run: every entry, my odds beside theirs.

    Every cell is a *win frequency* off the run's own ``scored`` matrix
    (``LeagueSim.p_win_by_entry``), so the column is the same measurement my
    headline is and the table sums to one up to rounding.

    It used to be built here, by renormalising each rival's ``1 - p_beat``
    over the losing mass. ``p_beat`` is pairwise: "do I finish above him",
    with the other eight managers absent from the question entirely. Folding
    it produced a number that was not P(win) and did not claim to be measured
    — on league 1794743 the leader's row read 45% where the same matrix, asked
    directly, says 82%. Nothing is renormalised now and nothing is inferred.
    """
    rows = []
    for entry in inputs.entries:
        rows.append(LeagueWhatIfRow(
            entry=int(entry.entry), name=str(entry.name),
            is_you=bool(entry.is_me), total=int(entry.total),
            p_win=sim.p_win_by_entry.get(int(entry.entry)),
            exp_finish=(sim.exp_finish if entry.is_me else 0.0)))
    rows.sort(key=lambda r: -r.total)
    return rows


@router.post("/whatif", response_model=LeagueWhatIfResult,
             responses={204: {"description": "cold cache, cached_only asked"}})
def whatif(req: LeagueWhatIfRequest) -> LeagueWhatIfResult:
    """Re-run the league with this week's events pinned.

    Different mechanism from the squad What-If Lab and deliberately kept
    apart (spec D5): that one re-solves the MILP under constraints, this one
    re-counts a Monte Carlo under declared events. No solve happens here and
    no transfer is proposed — the question is "what would that week do to my
    title odds", and the answer is a difference of two counted runs.

    An empty request is exactly the baseline. That is a rail rather than a
    nicety: every delta the panel shows is a difference against a run this
    endpoint produced itself, so a baseline that drifted would make the whole
    panel measure itself.
    """
    cfg = load_config()
    gw = latest_gw()
    hit = _run(cfg, gw, cached_only=bool(req.cached_only))
    if hit is None:
        # 204, not an error and not a wait: the caller asked for a cached
        # answer, there is not one, and the honest reply is nothing at all.
        return Response(status_code=204)
    baseline, inputs = hit
    by_code = _elements_by_code()

    scores: dict[int, float] = {}
    unknown: list[int] = []
    for pin in req.pins:
        if pin.event not in EVENT_POINTS and pin.event != "score":
            raise GafferError(
                f"unknown what-if event {pin.event!r} — expected haul, blank "
                f"or score")
        element = by_code.get(int(pin.code))
        if element is None:
            unknown.append(int(pin.code))
            continue
        scores[element] = (float(inputs.ep_by_element.get(element, 0.0))
                           if pin.event == "score"
                           else EVENT_POINTS[pin.event])

    captain = by_code.get(int(req.captain_override)) \
        if req.captain_override is not None else None
    if req.captain_override is not None and captain is None:
        unknown.append(int(req.captain_override))
    pins = Pins(scores=scores, captain_override=captain,
                rival_captain_blanks=(int(req.rival_captain_blanks)
                                      if req.rival_captain_blanks is not None
                                      else None))
    pinned = simulate_league(inputs, n=int(cfg.sim_n), seed=baseline.seed,
                             rival_drift=float(cfg.rival_drift), pins=pins)
    return LeagueWhatIfResult(
        baseline_p_win=baseline.p_win, p_win=pinned.p_win,
        delta_p_win=round(pinned.p_win - baseline.p_win, 4),
        baseline_exp_finish=baseline.exp_finish,
        exp_finish=pinned.exp_finish,
        delta_rank=round(pinned.exp_finish - baseline.exp_finish, 3),
        table=_entry_probabilities(pinned, inputs),
        unknown_codes=sorted(set(unknown)))
