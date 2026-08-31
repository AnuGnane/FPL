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

from fastapi import APIRouter

from gaffer.artifacts import latest_gw, load_snapshot, solve_state_paths
from gaffer.config import load_config
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
    _, meta = solve_state_paths(gw)
    stamp = meta.stat().st_mtime if meta.exists() else 0.0
    return (int(cfg.league_id), int(gw), stamp, int(cfg.sim_n),
            float(cfg.rival_drift))


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except GafferError:
        raise
    except Exception as exc:  # noqa: BLE001 — network, JSON, schema drift
        raise GafferError(f"FPL API unavailable ({exc}) — retry in a moment") \
            from exc


def _run(cfg, gw: int | None = None):
    """``(sim, inputs)`` for the current gameweek, cached per advice run."""
    plan_gw = int(gw) if gw is not None else latest_gw()
    if plan_gw is None:
        raise GafferError("no saved advice — run `gaffer advise` first")
    key = _cache_key(cfg, plan_gw)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
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
    notice = None
    if inputs.field_rate is None:
        notice = ("no field sample banked for this gameweek yet — rivals are "
                  "simulated on their current squads (run `gaffer "
                  "field-scrape`)")
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
