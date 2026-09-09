"""A board small enough to read, and a solver that does not solve (v17g §5).

``tests/test_advise.py`` asserts what ``build_advice`` did with its inputs.
Those claims are about wiring — which pool was built, which plan was served,
which value reached the state — so the plan itself can be scripted, and the
golden board is what proves the real solver is wired the same way.

Three things a user of this module has to know, because all three are ways a
test can end up asserting something other than what it says.

*It runs somewhere.* ``build_advice`` writes nothing, but ``gather_inputs``
and the savers do, against ``reports/`` under the working directory. Import
:func:`a_scratch_working_directory` into any module that builds; it is
autouse wherever it is imported.

*The ladder still solves, and it is what gets served.* ``ladder_payload``
calls ``solve_plan`` directly rather than through the
:class:`~gaffer.inputs.Solver` protocol, so every build costs the ladder's six
small MILPs whatever solver is passed — and the plan the advice serves is the
chosen rung's, not the scripted one, which reaches the payload as the
``objective`` block. :func:`without_the_ladder` is how a claim about the
served plan gets made.

*The chips are outside the protocol.* ``inputs.Solver`` leaves chip pricing
out on purpose, so ``solver.calls`` never sees it; :func:`recording` does.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer import advise
from gaffer.config import Config
from gaffer.data.entry import MyTeam
from gaffer.errors import GafferError
from gaffer.inputs import Inputs
from gaffer.optimize.milp import GwPlan, Plan

GW = 7
GWS = [7, 8]

SQUAD = [("GKP", 2, 45, 5.6), ("DEF", 5, 50, 6.4), ("MID", 5, 65, 8.0),
         ("FWD", 3, 70, 7.2)]
"""Position, squad count, price of the cheapest one in 0.1m units, EP of the
best one.

The counts are ``milp.SQUAD_COMPOSITION`` — the plan for this task said
2/6/7/5, which sums to twenty and is not a squad the MILP can build.

The four EP bases keep the positions apart in the order FPL puts them, so
that the highest-scoring player on the board is a midfielder. Flat descent
by row would have made him a goalkeeper, and every captaincy claim would
have been read against a fixture that looks broken.
"""

SPARES = 2
"""Extra players per position, so there is somewhere to transfer to."""

XI = {"GKP": 1, "DEF": 3, "MID": 5, "FWD": 2}
"""A legal starting eleven inside ``milp.XI_BOUNDS`` — and the one the real
solve picks off this board, so the scripted default and a real solve start
the same eleven."""


def tiny_players() -> pd.DataFrame:
    """One row per player, with every column the build half reads: the pool
    (code, position, team_code, now_cost), the alerts (price_change_percent,
    price_change_calibrating) and the name maps.

    ``price_change_percent`` is zero, which is below ``price_alerts``'
    threshold, so the default board raises no alert; a test about the alert
    table moves one player's figure past 90.
    """
    rows, code = [], 101
    for pos, n, cost, _ in SQUAD:
        for i in range(n + SPARES):
            rows.append({"code": code, "element": code - 100,
                         "name": f"{pos}{i}", "position": pos,
                         "team_code": code % 12, "now_cost": cost + i,
                         "price_change_percent": 0.0,
                         "price_change_calibrating": False,
                         "status": "a", "chance_of_playing": 100})
            code += 1
    return pd.DataFrame(rows)


def codes_by_position() -> dict[str, list[int]]:
    """``{position: codes, best first}`` — the board's own order."""
    players = tiny_players()
    return {pos: [int(c) for c in players[players["position"] == pos]["code"]]
            for pos, _, _, _ in SQUAD}


def tiny_squad() -> list[int]:
    """The fifteen the real solve picks, in position order.

    Deliberately the same fifteen: EP falls and price rises with the index
    inside a position, so the best player of every position is also the
    cheapest and the budget never binds. That makes the scripted plan and a
    real solve agree on the squad, and it means a test *about* money has to
    raise a price or drop the bank rather than assume the board supplies the
    tension.
    """
    by_pos = codes_by_position()
    return [c for pos, n, _, _ in SQUAD for c in by_pos[pos][:n]]


def tiny_ep(players: pd.DataFrame) -> dict[tuple[int, int], float]:
    """Descending EP inside each position, from that position's base, so the
    best fifteen are predictable and no two players tie."""
    base = {pos: ep for pos, _, _, ep in SQUAD}
    seen: dict[str, int] = {}
    out = {}
    for r in players.itertuples():
        i = seen.get(r.position, 0)
        seen[r.position] = i + 1
        for g in GWS:
            out[(int(r.code), g)] = round(base[r.position] - 0.1 * i, 2)
    return out


def tiny_comp(players: pd.DataFrame) -> pd.DataFrame:
    """The component frame: what p_play, xmins and the σ bands are read from.

    ``p60`` is on it because ``xmins_by_player_gw`` returns ``{}`` without one
    — and an empty xMins map takes the σ bands and the captain's ceiling with
    it, so the ladder would silently fall back to outcome-only σ.
    """
    return pd.DataFrame([{"code": int(r.code), "gw": g, "p_play": 0.9,
                          "p60": 0.8, "xmins": 76.5, "ep": 5.0,
                          "position": r.position}
                         for r in players.itertuples() for g in GWS])


def tiny_ep_named(ep_by: dict[tuple[int, int], float],
                  players: pd.DataFrame) -> pd.DataFrame:
    """One row per player-week for the captain, threat and alternative
    tables. ``p_haul`` is on it because ``captain_table`` reads it as the
    ceiling whenever the component bands cover none of the shortlist."""
    pos_of = dict(zip(players["code"], players["position"]))
    name_of = dict(zip(players["code"], players["name"]))
    return pd.DataFrame([{"code": c, "gw": g, "ep": v, "p_haul": 0.2,
                          "name": name_of[c], "position": pos_of[c]}
                         for (c, g), v in ep_by.items()])


def tiny_my(**over) -> MyTeam:
    """The squad :func:`tiny_squad` names, owned, with money in the bank.

    Every chip is spent, because the chip block costs a baseline solve plus a
    solve per available chip per week: a test about the chip table passes
    ``chips_by_gw={}`` and pays for it, and every other weekly test does not.
    """
    squad, players = tiny_squad(), tiny_players()
    cost = dict(zip(players["code"], players["now_cost"]))
    picks = pd.DataFrame([{"element": c - 100, "code": c,
                           "purchase": int(cost[c]), "now": int(cost[c]),
                           "sell": int(cost[c])} for c in squad])
    fields = dict(entry_id=1, bank=50, free_transfers=1, current_gw=GW,
                  picks=picks, chips_used=[],
                  chips_by_gw={1: "wildcard", 2: "freehit", 3: "bboost",
                               4: "3xc"})
    fields.update(over)
    return MyTeam(**fields)


def tiny_inputs(**over) -> Inputs:
    """A complete Inputs over the tiny board. ``**over`` replaces any field,
    which is how a test says what it is actually about.

    ``my=None`` by default, which is the initial-squad mode: no sweep, no
    chips, no alternative plans, because all three are gated on owning a
    squad. A test about any of them passes ``my=tiny_my()``.
    """
    players = tiny_players()
    ep_by = tiny_ep(players)
    comp = tiny_comp(players)
    fields = dict(
        gw=GW, gws=list(GWS), deadline="2026-10-01T17:30:00Z", through=GW - 1,
        gap_warning=None, players=players, comp=comp, components=comp.copy(),
        ep_named=tiny_ep_named(ep_by, players), ep_by=ep_by, my=None,
        league_eo={}, cover={}, cap_cover={}, rival_captains={},
        rival_names={}, strategy=None, win_probs=[], priors=None,
        dgw_probs={}, prior_advice=None, price_timing=False, price_fall={},
        difficulty={(int(t), g): 0.5
                    for t in players["team_code"].unique() for g in GWS})
    fields.update(over)
    return Inputs(**fields)


def tiny_cfg(**over) -> Config:
    """The knobs the build reads. The sweep and the alternatives are off by
    default: a test that wants either says so, and pays for it."""
    fields = dict(entry_id=1, league_id=0, horizon=len(GWS), scenarios_n=0,
                  alt_plan_max_gap=0.0, decision_priors=False,
                  price_timing=False)
    fields.update(over)
    return Config(**fields)


def a_plan(*, buys=(), sells=(), hits=0, squad=None, xi=None, bench=None,
           captain=None, vice=None, objective=60.0, gap=None) -> Plan:
    """A scripted Plan over the tiny board: fifteen owned, eleven starting.

    The default squad and XI are legal ones — ``SQUAD_COMPOSITION`` and
    ``XI_BOUNDS`` — because the served plan is rendered from them and a
    second keeper in the XI would be a fixture nobody could read.

    ``gap`` is for a plan handed to ``ScriptedSolver(alternatives=...)``: the
    advice rounds it onto the alternative's row, and ``None`` there is the
    only other thing that row can say.
    """
    by_pos = codes_by_position()
    squad = list(squad if squad is not None else tiny_squad())
    owned = {pos: [c for c in by_pos[pos] if c in squad] for pos in XI}
    xi = list(xi if xi is not None else
              [c for pos in XI for c in owned[pos][:XI[pos]]])
    bench = list(bench if bench is not None else [c for c in squad
                                                 if c not in set(xi)])
    weeks = [GwPlan(gw=g, buys=list(buys) if g == GW else [],
                    sells=list(sells) if g == GW else [],
                    hits=hits if g == GW else 0, squad=squad, xi=xi,
                    bench=bench, captain=captain or xi[0],
                    vice=vice or xi[1],
                    # The solver's own objective, in tilted units. Nothing on
                    # the build path reads it — ``advise.raw_xi_pts`` re-sums
                    # the untilted ep_by over ``xi`` — and ``xi_rows`` has no
                    # reader outside optimize/milp.py at all.
                    xi_rows=[], expected_pts=objective) for g in GWS]
    return Plan(gw_plans=weeks, objective=objective, gap=gap)


class ScriptedSolver:
    """Answers every call from a script and records what it was asked.

    The recording is the point: a claim like "the chips are priced on an
    untilted pool" is a claim about the pool a call *received*, and this is
    where a test can see it.

    The parameter names are ``optimize/``'s own — ``incumbent`` and not
    ``plan`` — so that a keyword read off ``calls`` is the keyword the
    shipped :class:`~gaffer.inputs.MilpSolver` would have passed on.
    """

    def __init__(self, *, plan=None, coherent=None, scenarios=None,
                 alternatives=()):
        self._plan = plan
        self._coherent = coherent
        self._scenarios = scenarios
        self._alternatives = list(alternatives)
        self.calls: list[tuple[str, dict]] = []

    @property
    def names(self) -> list[str]:
        """The call order, which is what an ordering pin used to assert by
        reading the source."""
        return [name for name, _ in self.calls]

    def _record(self, name, **kw):
        self.calls.append((name, kw))

    def solve(self, pool, state, **kw) -> Plan:
        self._record("solve", pool=pool, state=state, **kw)
        return self._plan if self._plan is not None else a_plan()

    def coherent(self, pool, state, decision, **kw) -> Plan:
        self._record("coherent", pool=pool, state=state, decision=decision,
                     **kw)
        for plan in (self._coherent, self._plan):
            if plan is not None:
                return plan
        return a_plan()

    def scenarios(self, pool, state, xmins, **kw):
        self._record("scenarios", pool=pool, state=state, xmins=xmins, **kw)
        if self._scenarios is None:
            # Said here rather than left to `run.completed` two lines into
            # advise.py, where the symptom is an AttributeError on None and
            # the cause is a missing constructor argument in the test.
            raise AssertionError(
                "the sweep ran and this solver has no scenarios scripted: "
                "pass ScriptedSolver(scenarios=ScenarioRun(...)), or leave "
                "scenarios_n at 0")
        return self._scenarios

    def alternatives(self, pool, state, incumbent, **kw) -> list[Plan]:
        self._record("alternatives", pool=pool, state=state,
                     incumbent=incumbent, **kw)
        return self._alternatives


def recording(monkeypatch, name: str) -> list[tuple[tuple, dict]]:
    """Record every call ``build_advice`` makes to one of ``advise``'s own
    module-level names, and let the real one run. Returns the list.

    :class:`ScriptedSolver` sees the four calls the
    :class:`~gaffer.inputs.Solver` protocol covers, and the chip pricers are
    deliberately not among them (``inputs.Solver``: "Chip pricing is
    deliberately not here"). So a claim about what ``chip_baseline``,
    ``evaluate_chips`` or ``wildcard_now_assessment`` were priced on — the
    untilted pool, above all — is read here rather than off ``solver.calls``.
    """
    real = getattr(advise, name)
    calls: list[tuple[tuple, dict]] = []

    def spy(*args, **kw):
        calls.append((args, kw))
        return real(*args, **kw)

    monkeypatch.setattr(advise, name, spy)
    return calls


def without_the_ladder(monkeypatch) -> None:
    """Serve the scripted plan itself.

    ``ladder_payload`` re-solves every rung with the real ``solve_plan`` off
    the state it is handed, so with a :class:`ScriptedSolver` the plan the
    advice *serves* is the ladder's own and not the scripted one — v16 §4's
    restraint walk, working as designed, and the scripted plan reaches the
    payload as the ``objective`` block instead. A test whose claim is about
    the served plan turns the ladder off here, which is the path a ladder
    that will not build already takes: one printed line, and
    ``serve_rung(None, ...)`` serving the objective's plan.

    It is also six MILP solves cheaper, which is the other reason a test with
    no claim on the ladder should use it.
    """
    def refuses(*args, **kw):
        raise GafferError("the ladder is off for this test (v17g §5)")

    monkeypatch.setattr(advise, "ladder_payload", refuses)


@pytest.fixture(autouse=True)
def a_scratch_working_directory(tmp_path, monkeypatch):
    """Run every build somewhere that is not the user's own ``reports/``.

    ``build_advice`` itself writes nothing — gate part 4 pins that — but
    ``gather_inputs`` banks the components and availability frames, and a
    test that drives ``run_advise`` or calls a saver directly would land them
    on the user's real week. Autouse in whichever module imports the name,
    because the cost of forgetting is silent and the cost of having it is a
    ``chdir``.
    """
    monkeypatch.chdir(tmp_path)
