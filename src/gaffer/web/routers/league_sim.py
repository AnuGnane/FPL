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

import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Response

from gaffer.artifacts import latest_gw, load_snapshot, solve_state_paths
from gaffer.config import load_config
from gaffer.data.field import field_sample_path, latest_field_eo
from gaffer.errors import GafferError
from gaffer.league_mode import win_probability
from gaffer.league_sim import (SIM_SEED, TOP10K_WAITING, Pins,
                               append_sim_history, build_inputs,
                               effective_picks, load_sim_history, rank_slope,
                               simulate_field_rank, simulate_league)
from gaffer.web.schemas import (FieldRank, LeagueSimData, LeagueWhatIfRequest,
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


_FRESH: set = set()
"""Keys whose cached entry has not been served yet.

``append_sim_history`` rewrites the whole history file, so running it on
every ``GET /api/league/sim`` meant a page refresh re-wrote the sparkline's
own store with a number that had not changed. It is banked once per run, on
the call that produced it.
"""


_LOCK = threading.Lock()
"""Guards the two containers above, and nothing else.

Uvicorn runs these endpoints on a thread pool, so two page loads a moment
apart really do land here at once. Storing an answer used to be ``clear()``
and then an assignment — two steps, and the second request's clear ran
between the first's, throwing away the entry it had just stored. What the
user saw was a what-if panel that had asked for ``cached_only`` a second
after a sim it had watched succeed, and got a 204 back.

Held across dict and set mutations only: never across ``build_inputs`` or
``simulate_league``, so concurrent requests still fetch and simulate in
parallel — the container is serialised, the work is not.
"""


def _cache_get(key):
    """The cached ``(sim, inputs)`` if there is one, marked as served."""
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _FRESH.discard(key)
        return hit


def _cache_store(key, value) -> None:
    """Make ``key`` the one cached answer, in one indivisible step.

    One gameweek's answer at a time; this is not an LRU. ``_FRESH`` is
    replaced rather than added to, so it never outlives the entry it
    describes.
    """
    with _LOCK:
        _CACHE.clear()
        _CACHE[key] = value
        _FRESH.clear()
        _FRESH.add(key)


def _take_fresh(key) -> bool:
    """True once per stored run: whether *this* call should bank the history."""
    with _LOCK:
        if key in _FRESH:
            _FRESH.discard(key)
            return True
        return False


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
                               eo_gw_for(gw))
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
    hit = _cache_get(key)
    if hit is not None:
        return hit
    if cached_only:
        return None
    inputs = _guard(build_inputs, cfg, fpl_client(), gw=plan_gw)
    sim = simulate_league(inputs, n=int(cfg.sim_n),
                          rival_drift=float(cfg.rival_drift))
    _cache_store(key, (sim, inputs))
    return sim, inputs


EO_PERCENT = 100.0
"""The log's units over the simulation's.

``field_eo_log.parquet`` stores effective ownership in *percent* — the same
units the sword/shield column and the compare panel render, and the units
:data:`gaffer.data.field.EO_CEILING` (200.0) is expressed in. ``league_sim``'s
synthetic field wants a Bernoulli probability and clamps to ``[0, 1]``, so a
percent handed straight over would make every sampled player owned by
everybody and every probability 0.5. The division happens here, at the one
boundary where the log is read, rather than inside the engine, which never
touches the store.
"""


def _trend_eo(season: str, gw: int) -> tuple[dict[int, float], str]:
    """W2 §3.3's deadline-extrapolated EO, or ``({}, "")`` when it is absent.

    Absent is a *routine* state, not a broken one: §3.3 only extrapolates when
    two gameweeks have been sampled, so every machine that has scraped exactly
    once lands here and falls back to the last sample. The import is inside
    the function and the except is broad because this is a display read on a
    page that already answers three other questions — a panel that 500s over a
    sibling module is a panel nobody can review.

    ``field_eo_trend`` returns ``element -> dict``, not a frame, and every
    element it knows about carries a ``deadline_eo`` — including the ones it
    could not extrapolate, where ``deadline_eo`` is just ``eo_last`` and
    ``trend_available`` is ``False``. Reading those as a trend would put a
    last-sample number under a ``deadline-trend`` label, so the gate is
    ``trend_available``, exactly as ``web/field_frame.py`` gates it.
    """
    try:
        from gaffer.data.field import field_eo_trend
    except ImportError:
        return {}, ""
    try:
        table = field_eo_trend(str(season), int(gw))
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}, ""
    out = {int(element): float(cell["deadline_eo"]) / EO_PERCENT
           for element, cell in (table or {}).items()
           if cell.get("trend_available")
           and cell.get("deadline_eo") is not None}
    return (out, "deadline-trend") if out else ({}, "")


def deadline_eo_table(season: str, gw: int) -> tuple[dict[int, float], str]:
    """``(element -> EO, source)`` for the field simulation.

    Prefers §3.3's deadline extrapolation and falls back to the newest banked
    sample. ``"none"`` on a machine that has never run ``field-scrape``, which
    :func:`gaffer.league_sim.simulate_field_rank` turns into its own named
    empty state rather than a probability. EO comes back as a fraction from
    either source — see :data:`EO_PERCENT`.
    """
    table, source = _trend_eo(season, gw)
    if table:
        return table, source
    latest = latest_field_eo(int(gw), season=str(season))
    if latest:
        return ({int(e): float(cell.get("eo", 0.0)) / EO_PERCENT
                 for e, cell in latest.items()}, "last-sample")
    return {}, "none"


def eo_gw_for(gw: int) -> int:
    """Which gameweek's EO sample answers for plan gameweek ``gw``.

    ``gw - 1``, floored at 1, and it is the same arithmetic
    :func:`_cache_key` and :func:`gaffer.league_sim.build_inputs` already use:
    entry picks 404 before a deadline, so the field scrape can only ever have
    banked the **last scored** gameweek. Asking the log for the plan gameweek
    is asking for a sample that cannot exist until the week it is meant to
    inform has already started — on the live log, plan gw 3 answered source
    ``none`` over 0 elements while gw 2 answered ``last-sample`` over 123, and
    the panel rendered its cold-clone empty state on a machine that had
    scraped that morning.

    It is a single read rather than "try ``gw``, fall back to ``gw - 1``".
    A sample banked under the plan gameweek itself is a *post-deadline*
    sample — the field's picks, now frozen and visible — and reading it as if
    it were the pre-deadline projection would make the panel's answer depend
    on what time of week the page was opened. §3.3's ``deadline_eo`` is
    already the one-gameweek-ahead extrapolation of the sample it is given,
    so ``gw - 1``'s sample *is* the number for ``gw``.

    **The floor is the one exception**, and it is the only one: at plan
    gameweek 1 there is no previous gameweek, so ``max(1, ...)`` reads GW1's
    *own* sample. Before that deadline none exists and the panel renders its
    empty state; after it, the sample is the field's frozen opening squads —
    the post-deadline reading the paragraph above refuses everywhere else,
    admitted here because it is the only answer the season has yet.
    """
    return max(1, int(gw) - 1)


def _ledger_upto(rows, gw: int) -> list[dict]:
    """Graded rows no later than the plan gameweek.

    A ledger row records a gameweek but not a *season*
    (``review.py``'s ledger columns), so after an August rollover last
    season's gameweek 30 sits in the same file as this season's gameweek 3 and
    reads as the future. Regressing rank on points over both is regressing
    over two different element spaces, two different fields and a rank that
    reset in between.

    ``gw <= plan gw`` is the cheap guard, and its limits are stated rather
    than papered over: it is *correct* within a season, and at a rollover it
    is merely self-limiting — early in the new season it keeps only the new
    season's weeks (nothing from last season is that low), and by the time the
    plan gameweek climbs past last season's rows they start being admitted
    again. The real fix is a season column on the ledger, which is a change to
    a protected file this cycle.
    """
    out = []
    for row in rows or []:
        try:
            if row.get("gw") is not None and int(row["gw"]) <= int(gw):
                out.append(row)
        except (TypeError, ValueError):
            continue          # a gameweek that is not a number is not a week
    return out


def _field_rank(cfg, inputs, gw: int) -> FieldRank:
    """v12 W4 §5.3's panel payload. Never raises.

    Never raises *by construction* now, rather than by inspection. This is a
    display read on a page that already answers three other questions, and
    the sentence used to be a docstring guarding nothing: an unreadable EO
    log, a schema drift in the sample, a numpy error on a degenerate axis
    would each have taken ``GET /api/league/sim`` down whole. The failure
    renders as the panel's own empty state, naming the exception, which is
    the one place a reader can act on it.
    """
    try:
        return _field_panel(cfg, inputs, int(gw))
    except Exception as exc:  # noqa: BLE001 — a display read never 500s a page
        return FieldRank(
            gw=int(gw), n=0, seed=SIM_SEED, managers=0, eo_source="none",
            eo_gw=None, field_draws=0,
            waiting_for=f"the field panel could not be computed ({exc}) — "
                        f"the rest of this page is unaffected",
            top10k_waiting_for=TOP10K_WAITING,
            rank_waiting_for="the field panel could not be computed")


def _field_panel(cfg, inputs, gw: int) -> FieldRank:
    """The panel, assembled. Wrapped by :func:`_field_rank`."""
    from gaffer.review import load_ledger

    season = str(getattr(cfg, "current_season", "") or "")
    eo_gw = eo_gw_for(gw)
    table, source = deadline_eo_table(season, eo_gw)
    out = simulate_field_rank(inputs, table, n=int(cfg.sim_n),
                              seed=SIM_SEED, gw=int(gw))
    try:
        slope = rank_slope(_ledger_upto(load_ledger(), gw))
    except Exception:  # noqa: BLE001 — an unreadable ledger is an empty one
        slope = {"slope": None, "rows": 0,
                 "waiting_for": "the decision ledger could not be read"}
    return FieldRank(
        gw=int(out["gw"]), n=int(out["n"]), seed=int(out["seed"]),
        managers=int(out["managers"]), eo_source=source,
        eo_gw=(eo_gw if table else None),
        field_draws=int(out["draws"]),
        unsampled_picks=int(out["unsampled_picks"]),
        p_green=out["p_green"], waiting_for=out["waiting_for"],
        p_top10k=out["p_top10k"],
        top10k_waiting_for=out["top10k_waiting_for"],
        rank_slope=slope["slope"], rank_slope_rows=int(slope["rows"]),
        rank_waiting_for=slope["waiting_for"],
        my_ep=out.get("my_ep"), field_median_ep=out.get("field_median_ep"))


@router.get("/sim", response_model=LeagueSimData)
def sim() -> LeagueSimData:
    cfg = load_config()
    gw = latest_gw()
    key = _cache_key(cfg, int(gw)) if gw is not None else None
    result, inputs = _run(cfg, gw)
    run_at = datetime.now(timezone.utc).isoformat()
    if _take_fresh(key):
        try:
            append_sim_history(result, int(gw), run_at)
        except Exception:  # noqa: BLE001 — never blocks the page
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
        legacy_win_probability=legacy,
        field=_field_rank(cfg, inputs, int(gw)))


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
    # A code the snapshot cannot resolve *and* a code that resolves to
    # somebody who is not in my starting eleven both mean the same thing to
    # the user: the armband did not move. The engine only honours an override
    # that names a starter, so a bench player named as captain was accepted,
    # ignored and reported as a delta of zero — a panel answering a question
    # it had not understood.
    if captain is not None:
        me = next((e for e in inputs.entries if e.is_me), None)
        starters = {int(el) for el, _ in effective_picks(me.picks)} if me \
            else set()
        if int(captain) not in starters:
            captain = None
    if req.captain_override is not None and captain is None:
        unknown.append(int(req.captain_override))

    if req.rival_captain_blanks is not None:
        # Not a 204 and not a silent nothing: naming an entry that is not in
        # this league is a request that cannot mean anything, and the panel
        # can only have got there from a stale tab.
        rivals = {int(e.entry) for e in inputs.entries if not e.is_me}
        if int(req.rival_captain_blanks) not in rivals:
            raise GafferError(
                f"entry {int(req.rival_captain_blanks)} is not a rival in "
                f"this league — reload the page and pick again")
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
