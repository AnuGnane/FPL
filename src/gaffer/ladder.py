"""The transfer ladder (v13 §3, specs/2026-09-04-gaffer-v13-transfer-ladder-design.md).

One row per rung of appetite — *bank*, then 0, 1, 2 and 3 hits, and an
*open* row only when the uncapped solve spends more than three — each
solved off the saved board exactly as the What-If lab re-solves it, and
every fixed plan then scored on **one** matrix of noise draws. Shared draws
are what make the rows comparable: the players two rungs have in common
score identically in every draw, so P(rung k beats rung j) is a statement
about the players that differ and nothing else.

The noise is the *outcome* distribution the squad table's bands already show
(:func:`gaffer.uncertainty.bands_by_player_gw`), not the sensitivity card's
narrower estimation σ. "Will two hits actually outscore one" is a question
about what the players score, so the probabilities here are closer to a
coin flip than that card's margins, and the spec chose that on purpose.

Since v17b the module is also the one author of the ladder's prose: labels,
step lines, the served restraint and objective lines.

The board is built as ``sensitivity.run_sensitivity`` builds it — saved
state, raw EP, the cover table converted from ``league_eo`` when the state
predates it, ``tilt_ep``, ``milp_pool``, ``solve_kw_from_state`` — and the
idiom is repeated rather than shared, for the reason that module records:
two tests pin ``solve_whatif``'s own source text.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from gaffer import artifacts
from gaffer.artifacts import (caps_from_state, latest_gw, load_advice,
                              load_components, load_solve_state, milp_pool,
                              raw_ep_by, solve_kw_from_state)
from gaffer.errors import GafferError
from gaffer.io import atomic_write
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.league_sim import OUTCOME_VAR_PER_EP
from gaffer.optimize.milp import GwPlan, Plan, SolveInput, solve_plan
from gaffer.served import ServedObjective, ServedPlan, ServedRestraint, ServedWeek
from gaffer.uncertainty import bands_by_player_gw

LADDER_DRAWS = 2000
"""Draws per rung. Two hundred resolved a probability only to about ±3.5%,
and the card prints whole percents off differences smaller than that — a
``p_best`` moved 0.09 → 0.15 across seeds. Two thousand holds it to about
±1%. The draws are free next to the six MILP solves, which dominate the wall
time: two thousand normal variates per player-week cost milliseconds."""

LADDER_HITS = (0, 1, 2, 3)
"""The hit rungs. Above three the *open* row exists only if the solver wants
it, so the table never lists a rung nobody would take."""

RUNG_ORDER = ("bank", *(f"hits{k}" for k in LADDER_HITS), "open")
"""The rungs in order of appetite. A cap naming a rung that did not solve
steps back along this to the richest one still on the table."""

SEED_OFFSET = 2_000_000
"""Two million clear of the advice sweep's ``scenarios_seed + gw`` and one
million clear of the sensitivity sweep's, so the three draw independent
noise rather than replaying each other."""

STEP_REASONS = ("flagged", "price", "fixtures", "chip", "points", "cap")
"""Why a step was taken or refused, in precedence order (v16 §3.3); ``cap``
is the one the caps add (plan R12). Descriptive, never a second gate: the
share decides, the reason is what the brief reads."""

FLAGGED_P_PLAY = 0.5
PRICE_FALL_BAR = 0.5
FIXTURE_GRADE = 0.2
"""One grade of five on the ticker's 0..1 difficulty (plan R7)."""

CHIP_LABEL = {"bboost": "Bench Boost", "3xc": "Triple Captain",
              "freehit": "Free Hit", "wildcard": "Wildcard"}
"""The chips as prose spells them; the reason and the brief both read it."""

HIT_BAR_FALLBACK = 0.60
"""What the walk uses when the live config will not read — the field's own
default, so an unreadable config is a ladder at the shipped bar and not no
ladder."""


def _rung_label(key: str) -> str:
    """The rung's name in prose: ``bank``, ``free transfers only``, ``2 hits``,
    ``no cap``. Private since v17b §4: every surface reads the served
    ``label``."""
    if key == "bank":
        return "bank"
    if key == "open":
        return "no cap"
    if key == "hits0":
        return "free transfers only"
    n = int(key[4:]) if key.startswith("hits") else 0
    return f"{n} hit{'' if n == 1 else 's'}"


def _step_line(step: dict) -> str:
    """The step as one sentence (v17b §3.1): ``bank → free transfers only:
    taken, 79% — expected points alone``. What LadderCard's ``stepText``
    composed in the browser, written once here."""
    return (f"{_rung_label(str(step['below']))} → {_rung_label(str(step['above']))}: "
            f"{'taken' if step.get('taken') else 'refused'}, "
            f"{round(float(step.get('share') or 0) * 100)}% — {step.get('reason') or ''}")


def walk(scores: dict[str, np.ndarray], rows: list[dict], *, hit_bar: float,
         max_hits: int | None, max_transfers: int | None
         ) -> tuple[str | None, list[dict]]:
    """The restraint walk (v16 §3.1): from the lowest scored rung, one
    distinct rung at a time, a step is taken when the higher rung beats the
    lower in at least ``hit_bar`` of the shared draws; the walk stops at the
    first refusal. ``rows`` are the ladder's rows in ``RUNG_ORDER``; a row
    with ``same_as`` or no score is never stepped to. A rung above a cap is
    refused with reason ``cap`` whatever the draws say.

    Returns ``(chosen, steps)``; ``steps`` carry ``below/above/share/taken``
    and, for a cap refusal, ``reason``/``reason_kind`` — every other step's
    reason is :func:`explain_step`'s to add.
    """
    order = [r for r in rows if not r.get("same_as") and r["key"] in scores]
    if not order:
        return None, []
    current = order[0]
    steps: list[dict] = []
    for above in order[1:]:
        share = round(float((scores[above["key"]] > scores[current["key"]]).mean()), 4)
        step = {"below": current["key"], "above": above["key"], "share": share,
                "taken": False}
        if max_hits is not None and int(above["hits"]) > int(max_hits):
            step.update(reason_kind="cap",
                        reason=f"above your cap of {int(max_hits)} hit"
                               f"{'' if int(max_hits) == 1 else 's'}")
            steps.append(step)
            break
        if max_transfers is not None and int(above["transfers"]) > int(max_transfers):
            step.update(reason_kind="cap",
                        reason=(f"above your cap of {int(max_transfers)} "
                                f"transfer{'' if int(max_transfers) == 1 else 's'}"
                                if max_transfers else "your cap is bank"))
            steps.append(step)
            break
        step["taken"] = share >= float(hit_bar)
        steps.append(step)
        if not step["taken"]:
            break
        current = above
    return current["key"], steps


@dataclass(frozen=True)
class StepContext:
    """What the reasons read (plan R3). Every map may be empty."""

    p_play: dict = field(default_factory=dict)
    """``{(code, gw): p_play}`` off the banked components frame."""
    price_fall: dict = field(default_factory=dict)
    """``{code: P(drops tonight)}`` off the banked price log."""
    difficulty: dict = field(default_factory=dict)
    """``{(team_code, gw): difficulty}``, the ticker's 0..1 rating."""
    team_of: dict = field(default_factory=dict)
    """``{code: team_code}`` off the saved pool."""
    chip_plan: list = field(default_factory=list)
    """``[{"gw", "chip"}]`` the advice's chip table would play, off the
    saved state's ``opt`` (written by ``advise.py``)."""


def step_context_from(components, state, *, price_fall: dict,
                      difficulty: dict) -> StepContext:
    """The context off values already in hand (v17g §2.3b). ``build_advice``
    holds all three: the components frame it predicted on, the price falls
    the served trace charges from, and the ticker's difficulty, gathered.
    Re-reading them there would answer a replay with the machine's own
    gameweek instead of the recorded one.

    The two maps are keyword-only because they are adjacent dicts whose keys
    are shaped differently — ``code`` against ``(team_code, gw)`` — so a
    transposed pair would raise nothing at all: both lookups would simply
    miss and every step reason would fall through to ``points``.

    ``components`` may be ``None`` — the frame :func:`step_context` could not
    load and has already printed about — and a frame that will not yield a
    ``p_play`` is an empty map, because a reason that cannot be worked out
    falls through to the next one.
    """
    p_play: dict = {}
    if components is not None:
        try:
            p_play = {(int(c), int(g)): float(p) for c, g, p in
                      zip(components["code"], components["gw"],
                          components["p_play"]) if p == p}         # NaN-safe
        except Exception as exc:  # noqa: BLE001
            print(f"ladder: no p_play for the step reasons ({exc})")
    team_of: dict = {}
    try:
        team_of = {int(c): int(t) for c, t in
                   zip(state.pool["code"], state.pool["team_code"])}
    except Exception:  # noqa: BLE001
        pass
    chip_plan = [c for c in (state.opt.get("chip_plan") or [])
                 if isinstance(c, dict) and c.get("gw") is not None]
    return StepContext(p_play=p_play, price_fall=price_fall,
                       difficulty=difficulty, team_of=team_of,
                       chip_plan=chip_plan)


def step_context(gw: int, state, gws: list[int]) -> StepContext:
    """Load the three sources and build the context off them, swallowing
    every failure: a missing source is an empty map, and the reason falls
    through. The loading wrapper over :func:`step_context_from` since v17g
    §2.3b, for the callers that have a gameweek and nothing else."""
    components = None
    try:
        components = load_components(gw)
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: no p_play for the step reasons ({exc})")
    price_fall: dict = {}
    try:
        from gaffer.price_timing import owned_price_falls
        price_fall = {int(c): float(p) for c, p in
                      owned_price_falls(list(state.owned_codes)).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: no price falls for the step reasons ({exc})")
    difficulty: dict = {}
    try:
        from gaffer.web.identity import _difficulty_by_team
        difficulty = _difficulty_by_team([int(g) for g in gws])
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: no fixture difficulty for the step reasons ({exc})")
    return step_context_from(components, state, price_fall=price_fall,
                             difficulty=difficulty)


def _diff(below: dict, above: dict, key: str) -> list[dict]:
    """First-week ``key`` refs on ``above`` that ``below`` does not have."""
    have = {int(p["code"]) for p in (below.get("plan_by_gw") or [{}])[0].get(key, [])}
    return [p for p in (above.get("plan_by_gw") or [{}])[0].get(key, [])
            if int(p["code"]) not in have]


def _mean_difficulty(code: int, ctx: StepContext, gws: list[int]) -> float | None:
    team = ctx.team_of.get(int(code))
    cells = [ctx.difficulty[(team, int(g))] for g in gws
             if team is not None and (team, int(g)) in ctx.difficulty]
    return sum(cells) / len(cells) if cells else None


def explain_step(below: dict, above: dict, ctx: StepContext, *, gw: int,
                 gws: list[int]) -> tuple[str, str]:
    """``(reason_kind, reason)`` for the step ``below`` → ``above`` (v16 §3.3),
    first match in precedence: flagged, price, fixtures, chip, points."""
    extra_sells = _diff(below, above, "sells")
    extra_buys = _diff(below, above, "buys")
    for s in extra_sells:
        p = ctx.p_play.get((int(s["code"]), int(gw)))
        if p is not None and p < FLAGGED_P_PLAY:
            return "flagged", f"{s['name']} is {round(p * 100)}% to play"
    for s in extra_sells:
        f = ctx.price_fall.get(int(s["code"]))
        if f is not None and f >= PRICE_FALL_BAR:
            return "price", f"{s['name']} is {round(f * 100)}% to drop tonight"
    best = None
    for b in extra_buys:
        mb = _mean_difficulty(b["code"], ctx, gws)
        for s in extra_sells:
            ms = _mean_difficulty(s["code"], ctx, gws)
            if mb is None or ms is None:
                continue
            if ms - mb >= FIXTURE_GRADE and (best is None or ms - mb > best[0]):
                best = (ms - mb, b, s, mb, ms)
    if best is not None:
        _, b, s, mb, ms = best
        return "fixtures", (f"{b['name']}'s next {len(gws)} average "
                            f"{mb * 5:.1f} against {s['name']}'s {ms * 5:.1f}")
    for c in ctx.chip_plan:
        if int(c["gw"]) in {int(g) for g in gws}:
            chip = CHIP_LABEL.get(str(c.get("chip")), str(c.get("chip")))
            return "chip", f"a {chip} is planned for GW{int(c['gw'])}"
    return "points", "expected points alone"


def _moves(entry: dict) -> tuple[tuple[int, ...], tuple[int, ...]]:
    return (tuple(sorted(int(p["code"]) for p in entry.get("buys") or [])),
            tuple(sorted(int(p["code"]) for p in entry.get("sells") or [])))


def _week_pts(week: dict) -> float:
    """Raw XI points the way ``advise.raw_xi_pts`` sums them: the eleven's
    EP, no captain doubling, no hits."""
    return round(sum(float(p.get("ep") or 0.0) for p in week.get("xi") or []), 2)


def serve_rung(ladder: dict | None, objective: dict, *, hit_cost: int,
               captain_note: str | None) -> ServedPlan:
    """The served plan from the chosen rung (v16 §4), or the objective's
    own when there is no rung to serve — one typed value (v17f §4), with
    the moves unpriced and the weeks unbanked: ``served.completed`` fills
    those off the solve state.

    ``hit_cost`` is the solve's price per hit (v17b §3.2): the block prices
    the served hits, and a ladder that did not build carries no cost of its
    own.

    ``objective`` is ``{gw, buys, sells, hits, xi, bench, captain, vice,
    expected_pts, plan_by_gw}`` in ``advise._named``'s shape.

    The armband: the rung's own plan captains its own squad, and that is
    what is served — the objective's captain was chosen for the objective's
    squad, and a buy the rung makes (Palmer, GW4) was never on the captain
    table the objective read. The one exception is a captain a note
    explains: the league sweep's cover or attack override (``captain_note``
    set) is a decision about the field, not the squad, so it stands when he
    is in the rung's XI and is replaced with a note when he is not.
    """
    obj = ServedPlan.model_validate(objective)
    # v17b §3.2: the block carries its prose — the chosen rung's ``label``,
    # the one ``line`` the CLI and the moves card print — and the objective
    # block its own line, so no surface composes a sentence of its own.
    objective_block = ServedObjective(
        buys=obj.buys, sells=obj.sells, hits=obj.hits, expected_pts=obj.expected_pts,
        line=_objective_line(objective),
        week=ServedWeek(gw=obj.gw, hits=obj.hits, buys=obj.buys, sells=obj.sells,
                        expected_pts=obj.expected_pts))
    restraint = {"chosen": None, "label": None, "bar": None, "steps": [],
                 "agrees": True, "note": None, "hit_cost": int(hit_cost), "line": None}

    def served(**fields) -> ServedPlan:
        restraint["line"] = _restraint_line(restraint)
        return obj.model_copy(update={
            "captain_note": captain_note, "objective": objective_block,
            "restraint": ServedRestraint.model_validate(restraint), **fields})

    if ladder is None:
        restraint["note"] = "the ladder did not build; this is the objective's plan"
        return served()
    chosen = ladder.get("chosen")
    row = next((r for r in ladder.get("rungs") or [] if r.get("key") == chosen), None)
    if chosen is None or row is None or not row.get("plan_by_gw"):
        restraint.update(bar=ladder.get("bar"), steps=_lined(ladder.get("steps")),
                         note="no rung of the ladder could be served; "
                              "this is the objective's plan")
        return served()
    weeks = row["plan_by_gw"]
    first = weeks[0]
    xi_codes = {int(p["code"]) for p in first["xi"]}
    captain, note = first["captain"], captain_note
    if captain_note:
        captain = objective["captain"]
        if int(captain["code"]) not in xi_codes:
            captain = first["captain"]
            note = (f"captain from the restrained plan; the sweep's choice "
                    f"({objective['captain']['name']}) is not in it")
    vice = first["vice"]
    if int(vice["code"]) == int(captain["code"]):
        vice = first["captain"] if int(first["captain"]["code"]) != int(captain["code"]) \
            else next(p for p in first["xi"] if int(p["code"]) != int(captain["code"]))
    agrees = _moves(first) == _moves(objective)
    restraint.update(
        chosen=chosen, label=_rung_label(str(chosen)), bar=ladder.get("bar"),
        steps=_lined(ladder.get("steps")), agrees=agrees,
        note=None if agrees else
        f"the objective's plan was the {_rung_label(chosen)} rung's "
        f"neighbour; the walk stopped at {_rung_label(chosen)}")
    rung = ServedPlan.model_validate({
        "gw": obj.gw,
        "buys": list(first["buys"]), "sells": list(first["sells"]),
        "hits": int(first["hits"]), "xi": list(first["xi"]),
        "bench": list(first["bench"]), "captain": captain, "vice": vice,
        "expected_pts": _week_pts(first),
        "plan_by_gw": [{"gw": int(w["gw"]), "hits": int(w["hits"]),
                        "buys": list(w["buys"]), "sells": list(w["sells"]),
                        "expected_pts": _week_pts(w)} for w in weeks]})
    return served(captain_note=note, **{k: getattr(rung, k) for k in (
        "buys", "sells", "hits", "xi", "bench", "captain", "vice",
        "expected_pts", "plan_by_gw")})

def _lined(steps) -> list[dict]:
    """The steps as the ladder wrote them, each carrying its ``line``; a
    step from a ladder built before v17b gets one here (§3.2)."""
    return [{**s, "line": s.get("line") or _step_line(s)} for s in steps or []]


def _restraint_line(restraint: dict) -> str:
    """The served block's one sentence (v17b §3.2): the rung, and the refused
    step if there was one; the block's note when no rung was chosen. The CLI
    and the moves card print it verbatim, so the v16 CLI wording is the
    wording everywhere."""
    if restraint.get("chosen") is None:
        return f"restraint: {restraint.get('note') or 'no rung was chosen'}"
    chosen = restraint.get("label") or _rung_label(str(restraint["chosen"]))
    refused = next((s for s in restraint.get("steps") or [] if not s.get("taken")), None)
    if refused is None:
        return f"restraint: {chosen}; every step was taken"
    return (f"restraint: {chosen}; the step to {_rung_label(refused['above'])} was "
            f"refused, {round(float(refused['share']) * 100)}% — {refused['reason']}")


def _objective_line(objective: dict | None) -> str:
    """"the objective wanted: X, Y in; Z out; 1 hit" — the objective block's
    ``line`` (v17b §3.2)."""
    if not objective:
        return "the objective wanted: nothing on record"
    buys = ", ".join(str(p["name"]) for p in objective.get("buys") or []) or "nobody"
    sells = ", ".join(str(p["name"]) for p in objective.get("sells") or []) or "nobody"
    hits = int(objective.get("hits") or 0)
    return (f"the objective wanted: {buys} in; {sells} out; {hits} hit"
            f"{'' if hits == 1 else 's'}")


def recommended_rung(advice: dict | None, rows: list[dict]
                     ) -> tuple[str | None, str | None]:
    """``(rung, note)`` — the rung whose first-week **moves** are the served
    advice's (plan R4: the captain is ignored, the sweep's may stand)."""
    if not advice:
        return None, "no served advice"
    wanted = _moves(advice)
    for row in rows:
        if row.get("same_as") or not row.get("plan_by_gw"):
            continue
        if _moves(row["plan_by_gw"][0]) == wanted:
            return row["key"], None
    return None, "the served advice's moves match no rung"


def served_note(ladder: dict, advice: dict | None) -> str | None:
    """When a rebuild's choice differs from what the advice served (v16 §4)."""
    if not advice or int(advice.get("gw", -1)) != int(ladder.get("gw", -2)):
        return None
    served = advice.get("restraint") or {}
    if served.get("chosen") is None or ladder.get("chosen") is None:
        return None
    if (served.get("chosen"), served.get("bar")) == (ladder.get("chosen"), ladder.get("bar")):
        return None
    return (f"the served advice was the {_rung_label(served['chosen'])} rung at "
            f"bar {float(served.get('bar') or 0):.2f}; this rebuild at "
            f"{float(ladder.get('bar') or 0):.2f} chooses "
            f"{_rung_label(ladder['chosen'])}")


def _hit_bar() -> float:
    try:
        from gaffer.config import config_in_force
        return float(config_in_force().hit_bar)
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: the live config would not read ({exc}); bar {HIT_BAR_FALLBACK}")
        return HIT_BAR_FALLBACK


def ladder_path(gw: int) -> Path:
    return artifacts.REPORTS / f"ladder_gw{gw}.json"


def load_ladder(gw: int) -> dict | None:
    """The banked ladder for ``gw``, or ``None`` — ``load_sensitivity``'s
    contract: a missing report is a card with a rebuild button, not an
    error."""
    path = ladder_path(gw)
    if not path.exists():
        return None
    try:
        return _labelled(json.loads(path.read_text()))
    except Exception as exc:  # noqa: BLE001 — a corrupt report is no report
        print(f"ladder report unreadable: {exc}")
        return None


def narrated(advice: dict) -> dict:
    """The advice's ``restraint`` and ``objective`` blocks with their prose,
    backfilled when the advice was banked before v17b wrote it (§3.3): a
    reader of the file on disk — the brief — never composes a sentence, and
    an advice written by this cycle is served as written. ``hit_cost`` is
    not invented; its readers fall back to the config's default."""
    restraint = advice.get("restraint")
    if isinstance(restraint, dict) and restraint.get("chosen") is not None:
        restraint.setdefault("label", _rung_label(str(restraint["chosen"])))
        restraint["steps"] = _lined(restraint.get("steps"))
        restraint.setdefault("line", _restraint_line(restraint))
    objective = advice.get("objective")
    if isinstance(objective, dict):
        objective.setdefault("line", _objective_line(objective))
    return advice


def _labelled(payload: dict) -> dict:
    """A ladder banked before v17b carries no ``label`` or ``line``; the
    route and the brief read through here, so they never see one (§3.1)."""
    for row in payload.get("rungs") or []:
        row.setdefault("label", _rung_label(str(row.get("key"))))
    for step in payload.get("steps") or []:
        step.setdefault("line", _step_line(step))
    return payload


def _finite(value):
    """The payload with every non-finite float replaced by ``None``.

    ``allow_nan=False`` is the right setting — a ``NaN`` in a JSON report is
    a landmine for the browser — but it made a single degenerate σ abort the
    whole save with a raw ``ValueError``. A missing number is a blank cell
    the card already knows how to draw, so the NaN becomes one.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def save_ladder(payload: dict, gw: int) -> Path:
    """Atomic, like every other banked report."""
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = ladder_path(gw)
    atomic_write(path, json.dumps(_finite(payload), indent=1,
                                  allow_nan=False))
    return path


def signature(first: GwPlan) -> tuple:
    """First-week buys, sells and captain — the decision a rung represents
    (``sensitivity.plan_signature``'s definition)."""
    return (tuple(sorted(int(c) for c in first.buys)),
            tuple(sorted(int(c) for c in first.sells)),
            int(first.captain))


def plan_points(gw_plans: list[GwPlan], ep_by: dict, hit_cost: int) -> float:
    """XI plus the captain again, minus the hits, on **raw** EP — the
    measure ``routers/whatif._summary`` and ``sensitivity.plan_value`` use."""
    total = 0.0
    for plan in gw_plans:
        def ep(code) -> float:
            return float(ep_by.get((int(code), int(plan.gw)), 0.0))

        total += sum(ep(c) for c in plan.xi) + ep(plan.captain)
        total -= plan.hits * hit_cost
    return round(total, 2)


def sigmas_from_components(comp) -> tuple[dict[tuple[int, int], float], str]:
    """``{(code, gw): σ}`` off a components frame already in hand, and where
    it came from. v17g §2.2: ``build_advice`` holds the frame this run
    predicted on, so the ladder no longer round-trips it through parquet."""
    bands = bands_by_player_gw(comp)
    if not bands:
        return {}, "outcome_only"
    return {key: float(band.sigma) for key, band in bands.items()}, "bands"


def sigma_table(gw: int) -> tuple[dict[tuple[int, int], float], str]:
    """:func:`sigmas_from_components` off the banked frame. ``{}`` with
    ``"outcome_only"`` when no frame is banked, and :func:`draw_points` then
    falls back cell by cell."""
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — a ladder is not worth a crash
        print(f"ladder: no component breakdown ({exc})")
        return {}, "outcome_only"
    return sigmas_from_components(comp)


def draw_points(keys, ep_by: dict, sigmas: dict, rng: np.random.Generator,
                n_draws: int) -> dict[tuple[int, int], np.ndarray]:
    """One vector of ``n_draws`` points per player-week, ``N(ep, σ)``.

    **Unclipped, on purpose.** An FPL score can be negative — two yellow
    cards, an own goal, a missed penalty — and what a rung is scored on is
    the sum over eleven players, not one. Clipping each player at zero moved
    every rung's mean up by about six points and squeezed the bank-to-hits3
    gap by three quarters of a point, which is a bias in exactly the
    comparison the table exists to make. With the clip gone ``mean_pts``
    lands on ``horizon_pts`` up to Monte Carlo error.

    Keys are visited in sorted order so the draw a player-week receives is a
    function of the seed and the set, never of which rung named him first.
    """
    out: dict[tuple[int, int], np.ndarray] = {}
    for key in sorted(keys):
        mu = float(ep_by.get(key, 0.0))
        sigma = sigmas.get(key)
        if sigma is None:
            # ``max(mu, 0)`` guards the square root, not the draw.
            sigma = math.sqrt(OUTCOME_VAR_PER_EP * max(mu, 0.0))
        out[key] = mu + float(sigma) * rng.standard_normal(n_draws)
    return out


def score_plan(gw_plans, draws: dict, hit_cost: int,
               n_draws: int) -> np.ndarray:
    """A fixed plan's horizon points in every draw: XI plus the captain
    again, minus the hits, undecayed, the vice and the bench ignored —
    :func:`plan_points` per draw."""
    total = np.zeros(n_draws)
    for plan in gw_plans:
        gw = int(plan.gw)
        for code in plan.xi:
            total += draws[(int(code), gw)]
        total += draws[(int(plan.captain), gw)]
        total -= float(plan.hits * hit_cost)
    return total


def p_best(scores: dict[str, np.ndarray]) -> dict[str, float]:
    """The share of draws each rung is the maximum in, ties split evenly."""
    keys = list(scores)
    matrix = np.stack([scores[k] for k in keys])            # rungs × draws
    winners = (matrix == matrix.max(axis=0)).astype(float)
    share = winners / winners.sum(axis=0)
    return {k: float(share[i].mean()) for i, k in enumerate(keys)}


def _refs(codes, gw: int, meta: dict, ep_by: dict) -> list[dict]:
    return [{"code": int(c),
             "name": str(meta.get(int(c), {}).get("name", c)),
             "position": str(meta.get(int(c), {}).get("position", "")),
             "ep": round(float(ep_by.get((int(c), int(gw)), 0.0)), 2)}
            for c in codes]


def vs_below(below, rung, *, prev_mean: float, mean: float, hit_cost: int,
             meta: dict, ep_by: dict, below_horizon_hits: int,
             horizon_hits: int) -> dict:
    """What the extra hit bought: the first-week moves this rung makes that
    the rung below did not (and any it dropped), the mean-points gain and
    the points it cost.

    The moves are the first week's, because that is the decision a manager
    takes now. ``delta_cost`` is the **horizon** difference, because that is
    what is inside ``delta_mean_pts`` — a rung capped at one hit per week may
    take one every week. ``delta_cost_now`` is the first week's alone.
    """
    below_buys, buys = set(int(c) for c in below.buys), set(int(c) for c in rung.buys)
    below_sells, sells = set(int(c) for c in below.sells), set(int(c) for c in rung.sells)
    return {
        "extra_buys": _refs(sorted(buys - below_buys), rung.gw, meta, ep_by),
        "extra_sells": _refs(sorted(sells - below_sells), rung.gw, meta, ep_by),
        "dropped_buys": _refs(sorted(below_buys - buys), below.gw, meta, ep_by),
        "dropped_sells": _refs(sorted(below_sells - sells), below.gw, meta,
                               ep_by),
        "delta_mean_pts": round(float(mean - prev_mean), 2),
        "delta_cost": int((int(horizon_hits) - int(below_horizon_hits))
                          * hit_cost),
        "delta_cost_now": int((int(rung.hits) - int(below.hits)) * hit_cost),
    }


def _week(plan: GwPlan, meta: dict, ep_by: dict, hit_cost: int) -> dict:
    return {"gw": int(plan.gw), "hits": int(plan.hits),
            "buys": _refs(plan.buys, plan.gw, meta, ep_by),
            "sells": _refs(plan.sells, plan.gw, meta, ep_by),
            "xi": _refs(plan.xi, plan.gw, meta, ep_by),
            "bench": _refs(plan.bench, plan.gw, meta, ep_by),
            "captain": _refs([plan.captain], plan.gw, meta, ep_by)[0],
            "vice": _refs([plan.vice], plan.gw, meta, ep_by)[0],
            "expected_pts": plan_points([plan], ep_by, hit_cost)}


def _empty_rung(key: str, source: dict, same_as: str) -> dict:
    """A collapsed row: the source's four hit numbers and nothing else, so
    the card can print "same as one hit" without re-deriving them."""
    return {"key": key, "label": _rung_label(key), "hits": source["hits"],
            "transfers": source["transfers"], "cost": source["cost"],
            "horizon_hits": source["horizon_hits"],
            "horizon_cost": source["horizon_cost"],
            "same_as": same_as, "plan_by_gw": [], "week_pts": None,
            "horizon_pts": None, "objective": None, "mean_pts": None,
            "p10_pts": None, "p90_pts": None, "p_beats_bank": None,
            "p_beats_top": None, "p_best": None, "vs_below": None}


def collapse(solved: list[tuple[str, Plan]]) -> tuple[list, dict[str, str]]:
    """Split the solved rungs into the distinct ones and the repeats.

    A rung repeats *any* earlier distinct rung, not merely the one directly
    below it: with a cap that binds in the middle, ``hits3`` can land back on
    ``hits0``'s decision while ``hits2`` differs from both, and the row must
    name the rung it actually matches.
    """
    distinct: list[tuple[str, Plan]] = []
    same_as: dict[str, str] = {}
    for key, plan in solved:
        sig = signature(plan.gw_plans[0])
        match = next((k for k, p in distinct
                      if signature(p.gw_plans[0]) == sig), None)
        if match is None:
            distinct.append((key, plan))
        else:
            same_as[key] = match
    return distinct, same_as


def _cap_rung(max_hits: int | None, max_transfers: int | None,
              rows: list[dict]) -> tuple[str, str]:
    """``(highlighted, requested)``.

    The requested row can be a ``same_as`` row with no numbers on it — a cap
    of three hits on a board where the solver will not spend a second one —
    so the highlight follows the ``same_as`` chain to the row that carries
    the plan, and the un-resolved key rides along for the caption.
    """
    keys = [r["key"] for r in rows]
    by = {r["key"]: r for r in rows}
    if max_transfers == 0:
        requested = "bank"
    elif max_hits is None or max_hits > max(LADDER_HITS):
        requested = keys[-1] if keys else "bank"
    else:
        requested = f"hits{int(max_hits)}"
    if requested not in by:
        # The requested rung was dropped for a solve that failed, so naming
        # it would highlight nothing at all. Step down the ladder to the
        # richest appetite that is actually on the table, and if even that is
        # empty take the first row: some row is always the right answer to
        # "where is my cap", and a caption already carries the key asked for.
        below = [k for k in RUNG_ORDER[:RUNG_ORDER.index(requested) + 1]
                 if k in by] if requested in RUNG_ORDER else []
        resolved = below[-1] if below else (keys[0] if keys else requested)
    else:
        resolved = requested
    seen: set[str] = set()
    while resolved in by and by[resolved].get("same_as") \
            and resolved not in seen:
        seen.add(resolved)
        resolved = by[resolved]["same_as"]
    return resolved, requested


def _cap_note(max_transfers: int | None) -> str | None:
    """No rung models a transfer cap between "bank" and "as many as you
    like", so a state carrying one gets a sentence rather than a wrong row."""
    from gaffer.config import NO_CAP

    if max_transfers is None or not 1 <= int(max_transfers) < NO_CAP:
        return None
    return (f"a transfer cap of {int(max_transfers)} has no rung of its own; "
            "the highlight follows the hit cap")


def _caps(state) -> tuple[tuple[int | None, int | None], str]:
    """``((max_hits, max_transfers), source)`` — the caps to highlight under.

    The *live* config, not the caps the saved state was solved with: the card
    changes a cap through ``/api/settings`` and rebuilds, and a highlight
    that only moved at the next ``gaffer advise`` would answer the previous
    question. The saved caps stay the fallback, so a config that will not
    read is a ladder off the state rather than no ladder, and ``cap_source``
    on the payload says which of the two the reader is looking at.

    Local import for the cycle ``caps_from_state`` documents, and the
    ``NO_CAP`` mapping is written out here rather than imported from
    ``advise``: the ladder does not depend on that module.
    """
    try:
        from gaffer.config import NO_CAP, config_in_force

        def cap(value) -> int | None:
            value = int(value)
            return None if value >= NO_CAP else value

        cfg = config_in_force()
        return (cap(cfg.max_hits), cap(cfg.max_transfers)), "config"
    except Exception as exc:  # noqa: BLE001 — an unreadable config is a
        # fallback, not a failed ladder.
        print(f"ladder: the live config would not read ({exc}); "
              "the caps come from the saved state")
        return caps_from_state(state), "state"


def ladder_payload(state, *, gw: int, gws: list[int], hit_bar: float,
                   seed: int, sigmas: dict, sigma_source: str,
                   prior_advice: dict | None,
                   caps: tuple[int | None, int | None], cap_source: str,
                   ctx: StepContext, n_draws: int = LADDER_DRAWS,
                   now: datetime | None = None) -> dict:
    """Solve every rung off ``state``, score them on shared draws, return the
    payload. v17g §2.2: pure of the reads and the one write that used to
    bracket it, so ``build_advice`` can call it on the state it has just
    built in memory and :func:`build_ladder` can call it on one it has just
    loaded.

    ``prior_advice`` is the served advice for this gameweek **as it stood
    before the run** — the previous run's on a Thursday re-run, and ``None``
    when there was none to read.

    ``caps``/``cap_source`` and ``ctx`` are passed rather than derived (v17g
    §2.3b): :func:`_caps` reads the live config and :func:`step_context`
    reads the components parquet, both against the working directory, so a
    build replayed from a recording would otherwise answer with the
    machine's own gameweek and look like agreement.

    One read is left, and named here rather than left to be discovered:
    ``solve_kw_from_state`` rebuilds the free-transfer lambda from the
    shipped decision priors when the board was solved with them on. That is
    a package asset and not a working-directory artifact, so it cannot
    replay anybody's gameweek — it is the same table wherever the code runs.

    ``wall_s`` on the payload is the solving alone since the split: the
    loads it used to include are the caller's now.

    ``now``, like ``build_advice``'s clock (v18b Task 4), stamps
    ``generated_at``; it never touches ``wall_s``, which stays measured
    elapsed time regardless of what clock the caller passed.
    """
    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    hit_cost = int(opt["hit_cost"])
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}
    n_draws = max(1, int(n_draws))
    started = time.perf_counter()

    base = dict(owned_codes=state.owned_codes, bank=state.bank,
                free_transfers=state.free_transfers, gws=gws)
    specs: list[tuple[str, SolveInput]] = [
        ("bank", SolveInput(**base, max_transfers=0))]
    specs += [(f"hits{k}", SolveInput(**base, max_hits=k))
              for k in LADDER_HITS]
    specs.append(("open", SolveInput(**base)))

    solved: list[tuple[str, Plan]] = []
    notes: list[str] = []
    for key, solve_state in specs:
        try:
            # v17g §2.3b: ``price_fall`` is on neither ``OPT_REQUIRED_KEYS``
            # nor the saved state — advise carries it on ``solve_kw`` and the
            # state's ``opt`` is plain JSON — so without this every rung read
            # the price log off the working directory for itself. The map is
            # the one the step reasons already charge from, and it is the same
            # value the read returned: through ``build_ladder`` the context's
            # own ``owned_price_falls(state.owned_codes)``, and through
            # ``build_advice`` the gathered pair, which is that call when the
            # switch is on and ``{}`` when it is off — as the read is too.
            plan = solve_plan(pool, solve_state, **opt,
                              price_fall=ctx.price_fall)
        except (RuntimeError, KeyError, ValueError) as exc:
            # One infeasible or malformed rung is a missing row, not a
            # missing ladder: the others still answer the question.
            note = f"the {key} rung did not solve ({exc}) and was dropped"
            print(f"ladder: {note}")
            notes.append(note)
            continue
        if key == "open" and plan.gw_plans[0].hits <= max(LADDER_HITS):
            continue
        solved.append((key, plan))
    if not solved:
        raise GafferError("no rung of the ladder solved — "
                          + "; ".join(notes))

    # Distinct rungs solve and score; a rung whose first-week decision
    # repeats an earlier rung's is kept as a row that says so and carries no
    # numbers of its own.
    distinct, same_as = collapse(solved)

    keys_needed: set[tuple[int, int]] = set()
    for _, plan in distinct:
        for week in plan.gw_plans:
            keys_needed.update((int(c), int(week.gw)) for c in week.xi)
            keys_needed.add((int(week.captain), int(week.gw)))
    sigma_fallbacks = sum(1 for key in keys_needed if key not in sigmas)
    if sigma_source == "bands" and sigma_fallbacks:
        # Some cell the plans need had no band — a player with no component
        # history — so the row is a mix of the two σ sources and says so.
        sigma_source = "bands+outcome"
    rng = np.random.default_rng(int(seed))
    draws = draw_points(keys_needed, ep_by, sigmas, rng, n_draws)
    scores = {key: score_plan(plan.gw_plans, draws, hit_cost, n_draws)
              for key, plan in distinct}
    best = p_best(scores)
    top_key = distinct[-1][0]
    bank_scores = scores.get("bank")
    if bank_scores is None:
        # Every rung is measured against banking, so without that rung there
        # is nothing to measure against — a blank column and a line saying
        # why, rather than a KeyError that takes the whole ladder down.
        notes.append("the bank rung is missing, so no rung can be compared "
                     "against banking")

    rows: list[dict] = []
    by_key: dict[str, dict] = {}
    prev: tuple[str, Plan, int] | None = None
    for key, plan in solved:
        if key in same_as:
            row = _empty_rung(key, by_key[same_as[key]], same_as[key])
            rows.append(row)
            by_key[key] = row
            continue
        first = plan.gw_plans[0]
        sc = scores[key]
        mean = float(sc.mean())
        horizon_hits = sum(int(p.hits) for p in plan.gw_plans)
        row = {
            "key": key, "label": _rung_label(key), "hits": int(first.hits),
            "transfers": int(len(first.buys)),
            "cost": int(first.hits * hit_cost),
            "horizon_hits": horizon_hits,
            "horizon_cost": int(horizon_hits * hit_cost), "same_as": None,
            "plan_by_gw": [_week(p, meta, ep_by, hit_cost)
                           for p in plan.gw_plans],
            "week_pts": plan_points(plan.gw_plans[:1], ep_by, hit_cost),
            "horizon_pts": plan_points(plan.gw_plans, ep_by, hit_cost),
            "objective": round(float(plan.objective), 2),
            "mean_pts": round(mean, 2),
            "p10_pts": round(float(np.percentile(sc, 10)), 2),
            "p90_pts": round(float(np.percentile(sc, 90)), 2),
            "p_beats_bank": (None if key == "bank" or bank_scores is None
                             else round(float((sc > bank_scores).mean()), 4)),
            "p_beats_top": (None if key == top_key
                            else round(float((sc > scores[top_key]).mean()), 4)),
            "p_best": round(best[key], 4),
            "vs_below": (None if prev is None else vs_below(
                prev[1].gw_plans[0], first,
                prev_mean=float(scores[prev[0]].mean()), mean=mean,
                hit_cost=hit_cost, meta=meta, ep_by=ep_by,
                below_horizon_hits=prev[2], horizon_hits=horizon_hits)),
        }
        rows.append(row)
        by_key[key] = row
        prev = (key, plan, horizon_hits)

    max_hits, max_transfers = caps
    cap_rung, cap_requested = _cap_rung(max_hits, max_transfers, rows)
    # v17g §2.2: the load moved out to the callers, and its note came with
    # it. ``None`` is the advice that would not read, whose note names the
    # gameweek — the sentence the load's own ``except`` wrote, shared by both
    # branches here; an advice that read and matched no rung keeps
    # ``recommended_rung``'s own shorter one.
    unread = f"no served advice for GW{int(gw)}"
    if prior_advice is None:
        recommended, recommended_note = None, unread
    else:
        try:
            recommended, recommended_note = recommended_rung(prior_advice, rows)
        except Exception as exc:  # noqa: BLE001 — a malformed advice is no
            # chip on a row, not a crash.
            print(f"ladder: no served advice to mark ({exc})")
            recommended, recommended_note = None, unread
    # v16 §3.1: the restraint walk on the same draws, with its reasons.
    chosen, steps = walk(scores, rows, hit_bar=hit_bar, max_hits=max_hits,
                         max_transfers=max_transfers)
    for step in steps:
        if "reason_kind" not in step:
            kind, text = explain_step(by_key[step["below"]], by_key[step["above"]],
                                      ctx, gw=gw, gws=gws)
            step.update(reason_kind=kind, reason=text)
    # v17b §3.1: the step's sentence, written once the reason is known.
    for step in steps:
        step["line"] = _step_line(step)
    payload = {
        "gw": int(gw), "gws": [int(g) for g in gws],
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"),
        "free_transfers": int(state.free_transfers),
        "cap": {"max_hits": max_hits, "max_transfers": max_transfers},
        "cap_source": cap_source,
        "cap_rung": cap_rung, "cap_rung_requested": cap_requested,
        "cap_note": _cap_note(max_transfers),
        "recommended": recommended, "recommended_note": recommended_note,
        "bar": hit_bar, "chosen": chosen, "steps": steps,
        "n_draws": n_draws, "seed": int(seed), "sigma_source": sigma_source,
        "sigma_fallbacks": int(sigma_fallbacks),
        "wall_s": round(time.perf_counter() - started, 1),
        "notes": notes,
        "rungs": rows,
    }
    return _finite(payload)


def build_ladder(gw: int | None = None, *, n_draws: int = LADDER_DRAWS,
                 seed: int | None = None) -> dict:
    """Load the saved board, solve the ladder off it, bank the payload. The
    job body, the route's rebuild, and ``advise``'s path before v17g §2.2
    moved the solving into :func:`ladder_payload`. The defaults are the ones
    it computed for itself before, so its callers see no change.

    Raises :class:`GafferError` when there is no saved state — the job
    runner's cue to say "run `gaffer advise` first" rather than 500.
    """
    gw = latest_gw() if gw is None else int(gw)
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    if seed is None:
        from gaffer.config import config_in_force
        seed = int(config_in_force().scenarios_seed) + SEED_OFFSET + int(gw)
    sigmas, sigma_source = sigma_table(gw)
    try:
        prior_advice = load_advice(gw)
    except Exception as exc:  # noqa: BLE001 — no advice is no chip on a row,
        # not a crash; the note the payload carries says so.
        print(f"ladder: no served advice to mark ({exc})")
        prior_advice = None
    caps, cap_source = _caps(state)
    payload = ladder_payload(state, gw=gw, gws=gws, hit_bar=_hit_bar(),
                             seed=int(seed), sigmas=sigmas,
                             sigma_source=sigma_source,
                             prior_advice=prior_advice, caps=caps,
                             cap_source=cap_source,
                             ctx=step_context(gw, state, gws),
                             n_draws=n_draws)
    save_ladder(payload, gw)
    return payload
