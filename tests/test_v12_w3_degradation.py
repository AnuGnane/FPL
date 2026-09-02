"""v12 W3's degradation rails, the three pins, and the protected-diff audit.

Every rail here is a state a real machine reaches, and three of them are the
state *this* machine is in today: no calibrated priors asset in a fresh clone,
no ``data/chip_scenarios.toml`` on any machine anywhere, and no components
frame until a refresh has run.

The file also carries **the only absolute config-field count in the suite**.
That pin moved here from ``tests/test_v12_w1_degradation.py`` under the
orchestrator's ruling of 2026-09-02: it is a single number that every cycle
adding a key has to move, so it lives in the newest cycle's file and W1 keeps
the by-name claim about its own five keys. The *route* total does not move with
it — v11 built the single home for that one and W3 adds no route, so
``tests/test_v11_degradation.py`` keeps it and this file pins routes by
absence alone.
"""

from __future__ import annotations

import subprocess

import pandas as pd
import pytest

# =====================================================================
# Block 1 — §4.1: "sell him" is a constraint, and saying nothing says nothing
# =====================================================================


def test_an_empty_force_out_still_builds_the_pre_change_lp(tmp_path):
    """The workstream's regression guard, re-run from the rails file.

    Imported rather than re-fixtured on purpose: one golden and one pool, so a
    failure here is a failure of the solver and never of a second copy of the
    numbers that drifted.
    """
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    assert _capture_lp(tmp_path, _state())[0] == GOLDEN.read_text()


def test_a_code_outside_the_pool_is_refused_by_name_at_both_layers():
    """Once beside the input and once at the solver.

    The lab's refusal is a 422 raised by ``_validate`` *before* the job is
    queued, so the user is told at the form rather than by a failed job he has
    to go and read. The solver's is the backstop for every other caller.
    """
    from gaffer.errors import GafferError
    from gaffer.optimize.milp import solve_plan
    from gaffer.web.routers import whatif as wf
    from gaffer.web.schemas import WhatIfRequest

    from tests.test_v12_w3_force_out import KW, _pool, _state

    with pytest.raises(GafferError, match="force_out: player code 9999"):
        solve_plan(_pool(), _state(force_out=[9999]), **KW)

    class _State:
        owned_codes = [1, 2, 3]
        pool = pd.DataFrame({"code": [1, 2, 3, 4, 5]})
        gws = [5, 6, 7]
        avail_by_gw: dict = {}

    with pytest.raises(Exception) as exc:
        wf._validate(WhatIfRequest(force_out=[9999]), _State())
    assert exc.value.status_code == 422
    assert exc.value.detail["constraint"] == "unknown_player"
    assert 9999 in exc.value.detail["players"]


def test_a_forced_sale_credits_the_bank_and_a_ban_never_did():
    """The distinction, asserted rather than described.

    Both instructions take player 5 out of every horizon week. Only one of
    them pays for the replacement, and on this fixture that is the whole
    difference: ``force_out`` solves, ``locked_out`` is infeasible, and handing
    the banned solve player 5's sell price makes it feasible and lands it on
    the identical squad.
    """
    from gaffer.optimize.milp import solve_plan

    from tests.test_v12_w3_force_out import KW, _pool, _state

    sold = solve_plan(_pool(), _state(force_out=[5]), **KW)
    assert 5 in sold.gw_plans[0].sells
    with pytest.raises(RuntimeError, match="MILP not optimal"):
        solve_plan(_pool(), _state(locked_out=[5]), **KW)
    funded = solve_plan(_pool(), _state(locked_out=[5], bank=40), **KW)
    assert set(funded.gw_plans[0].buys) == set(sold.gw_plans[0].buys)


# =====================================================================
# Block 2 — §4.2: one bar, and it can always say where it came from
# =====================================================================

SENTINEL_WC, SENTINEL_CHIP = 999.0, 998.0

CHIP_CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                itb_value=0.05, hit_cost=4)


@pytest.fixture()
def sentinels(monkeypatch):
    """Both flat constants replaced by numbers no calibration could produce."""
    from gaffer.optimize import chips as chips_mod

    monkeypatch.setattr(chips_mod, "WILDCARD_RECOMMEND_THRESHOLD",
                        SENTINEL_WC)
    monkeypatch.setattr(chips_mod, "CHIP_PLAY_THRESHOLD", SENTINEL_CHIP)


def test_a_cold_clone_is_flat_everywhere_and_says_which_kind_of_flat(
        sentinels):
    """The state of a fresh clone: no priors asset at all.

    Every bar is the flat constant, every source string starts ``flat:``, and
    the wildcard verdict is the pre-v12 one — the strictly-greater comparison
    against the flat bar, unchanged, because no lookup reached it.
    """
    from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                             threshold_with_source)
    from gaffer.optimize.chips import wildcard_now_assessment

    from tests.test_v12_w3_chip_threshold import _pool, _state

    lookup = chip_thresholds_from_asset(None)
    for chip in ("wildcard", "bboost", "3xc", "freehit"):
        for gw in (1, 19, 38):
            bar, source = threshold_with_source(lookup, chip, gw)
            assert bar in (SENTINEL_WC, SENTINEL_CHIP)
            assert source.startswith("flat:")

    out = wildcard_now_assessment(_pool(), _state(), **CHIP_CFG)
    assert out["threshold"] == SENTINEL_WC
    assert out["threshold_source"].startswith("flat:")
    assert out["recommend"] is (out["gain_over_horizon"] > SENTINEL_WC)


def test_with_an_asset_no_bar_anywhere_is_a_flat_value(sentinels):
    """Spec §4.2's own test, swept over the season and over ``chip_plan``.

    ``chip_plan`` is the second half and the reason this is not a copy of
    Task 4's: the chip *table*'s bars and the chip *planner*'s ``threshold_now``
    are two calls to the same lookup from two modules, and a sentinel reaching
    either one is a flat bar that should have been θ.
    """
    from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                             threshold_with_source)
    from gaffer.optimize.chips import chip_plan

    from tests.test_v12_w3_chip_threshold import _priors_covering_everything

    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    for chip in ("wildcard", "bboost", "3xc", "freehit"):
        for gw in range(1, 39):
            bar, source = threshold_with_source(lookup, chip, gw)
            assert bar not in (SENTINEL_WC, SENTINEL_CHIP)
            assert source == "theta"

    table = pd.DataFrame([{"chip": chip, "gw": gw, "gain": 5.0,
                           "per_week": 5.0}
                          for chip in ("wildcard", "bboost")
                          for gw in (7, 8)])
    for row in chip_plan(table, 7, thresholds=lookup):
        assert row["threshold_now"] not in (SENTINEL_WC, SENTINEL_CHIP)


def test_a_lookup_with_no_explain_is_unknown_and_still_draws_the_table():
    """A stale lookup — a test's lambda, or one built before v12 — must cost
    the caption and never the chip table. ``unknown`` is a source string the
    UI knows to print nothing for; a raise here would be a blank Chips tab.
    """
    from gaffer.optimize.chip_policy import UNKNOWN_SOURCE, threshold_with_source
    from gaffer.optimize.chips import chip_plan

    stale = lambda chip, gw: 4.5                             # noqa: E731
    assert threshold_with_source(stale, "bboost", 7) == (4.5, UNKNOWN_SOURCE)

    table = pd.DataFrame([{"chip": "bboost", "gw": 7, "gain": 5.0,
                           "per_week": 5.0}])
    rows = chip_plan(table, 7, thresholds=stale)
    assert rows and rows[0]["threshold_now"] == 4.5
    assert rows[0]["play_now"] is True


# =====================================================================
# Block 3 — §4.3: the alternatives are an addition, never a precondition
# =====================================================================


def test_a_max_gap_of_zero_spends_no_solve(monkeypatch):
    """The off switch has to be free, or it is a preference and not a switch.
    ``[optimizer] alt_plan_max_gap = 0`` is the documented way to turn the
    whole feature off on a slow machine."""
    import gaffer.optimize.milp as milp_mod
    from gaffer.optimize.milp import alternative_plans, solve_plan

    from tests.test_v12_w3_alt_plans import KW, _pool, _state

    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    monkeypatch.setattr(milp_mod, "_solve_once",
                        lambda *a, **k: pytest.fail("must not solve"))
    assert alternative_plans(pool, state, plan, max_gap=0.0, **KW) == []


def _wire(monkeypatch, advice):
    """The plan endpoint over a given advice artifact."""
    from gaffer.artifacts import SolveState
    from gaffer.web.routers import plan as plan_router

    pool = pd.DataFrame({"code": [100, 200], "name": ["In", "Out"],
                         "cost": [80.0, 75.0], "sell": [78.0, 74.0]})
    state = SolveState(pool=pool, bank=15, opt={"hit_cost": 4},
                       generated_at="2026-09-01T09:00:00+00:00",
                       owned_codes=[200], gws=[5, 6, 7], gw=5, deadline="",
                       mode="weekly", free_transfers=1, lam=0.0,
                       league_eo={}, avail_by_gw={})
    monkeypatch.setattr(plan_router, "load_advice", lambda gw: advice)
    monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
    return plan_router


def test_an_artifact_with_no_alternatives_key_serves_an_empty_strip(
        monkeypatch):
    """Every advice payload on disk today, and every one written by a run with
    the feature switched off. An empty list is one tab and no strip — never a
    500 and never a blank board."""
    from tests.test_v12_w3_plan_alternatives import _advice, _week

    router = _wire(monkeypatch, _advice([_week(5), _week(6)]))
    out = router.plan(5)
    assert out.alternatives == []
    assert len(out.weeks) == 2


@pytest.mark.parametrize("payload", ["nonsense", {"a": 1}, 7,
                                     ["nonsense"], [{"gap": 1.0}]])
def test_a_malformed_alternative_costs_a_tab_and_not_the_board(monkeypatch,
                                                               payload):
    """The board is v11's timeline and the reader's main view of the week. A
    key this cycle added must not be able to take it down."""
    from tests.test_v12_w3_plan_alternatives import _advice, _week

    router = _wire(monkeypatch, _advice([_week(5)], payload))
    out = router.plan(5)
    assert len(out.weeks) == 1
    assert all(a.weeks for a in out.alternatives)


def test_a_plan_still_constructs_with_two_arguments():
    """``gap`` and ``alternatives`` are defaulted, so every ``Plan`` in the
    tree is the object it was — including the tens of thousands a scenario
    sweep builds, positionally, in a loop."""
    from gaffer.optimize.milp import Plan

    plan = Plan(0.0, [])
    assert plan.gap is None
    assert plan.alternatives == []


# =====================================================================
# Block 4 — §4.4: the arm ships on, and off is still off to the byte
# =====================================================================


def test_the_shipped_default_is_on_and_the_advice_run_wires_the_flag():
    """The state W3 merges in, now that the captain-support gate has spoken
    (CONVENTIONS §6, orchestrator ruling 2026-09-02).

    The gate ran on the GW3 board (2026-09-02, seed 20260828, n = 40, captain
    209036, 219/219 priced and covered): captain support fell 60.0 → 52.5 with
    the draw on, a drop of 7.5 against the pre-registered ceiling of 10, with
    40/40 scenarios completing in both arms. The rule was written before the
    number, so the number flips the default rather than the rule.

    Asserted three ways because the default is the whole safety argument: the
    dataclass, a config file that does not mention the key, and the one call
    site — the flag is what decides whether the sweep is handed ``p_play`` at
    all, so a later edit cannot rewire that arm to a different switch.

    T8-T11 final review, Important 2: the third of those is **kept** as a rail
    on the call shape. It is not standing in for behaviour — the test directly
    below re-runs the sweep on a fixed seed and proves ``draw_availability =
    False`` is still v11's sweep to the byte.
    """
    import inspect
    import tempfile
    from pathlib import Path

    from gaffer.advise import run_advise
    from gaffer.config import Config, load_config

    assert Config(entry_id=1, league_id=2).draw_availability is True
    path = Path(tempfile.mkdtemp()) / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).draw_availability is True

    src = inspect.getsource(run_advise)
    assert "p_play=(p_play_by_code if cfg.draw_availability" in src
    assert "draw_availability=cfg.draw_availability," in src


def test_the_switch_off_reproduces_the_pre_v12_sweep_on_a_fixed_seed():
    """Task 8's assertion, re-run here as a rail. A scenario sweep gates every
    transfer the tool recommends, so "off changes nothing" is not a property
    to check once — it is the cost of admission for the whole item."""
    from gaffer.optimize.scenarios import run_scenarios

    from tests.test_v12_w3_availability import (SOLVE_KW, _p_play, _pool,
                                                _signature, _state, _xmins)

    pool, xm = _pool(), _xmins(_pool())
    before = run_scenarios(pool, _state(), xm, n=3, seed=7, **SOLVE_KW)
    after = run_scenarios(pool, _state(), xm, n=3, seed=7,
                          p_play=_p_play(pool), draw_availability=False,
                          **SOLVE_KW)
    assert _signature(before) == _signature(after)


def test_the_switch_on_with_no_probabilities_prints_the_lever_line(capsys):
    """v10's lesson: an arm that believes it models something and models
    nothing reports zeros as evidence. The sweep says so out loud and draws
    the boards it always drew."""
    from gaffer.optimize.scenarios import run_scenarios

    from tests.test_v12_w3_availability import (SOLVE_KW, _pool, _signature,
                                                _state, _xmins)

    pool, xm = _pool(), _xmins(_pool())
    before = run_scenarios(pool, _state(), xm, n=2, seed=7, **SOLVE_KW)
    after = run_scenarios(pool, _state(), xm, n=2, seed=7, p_play={},
                          draw_availability=True, **SOLVE_KW)
    assert _signature(before) == _signature(after)
    assert "no p_play reached the sweep" in capsys.readouterr().out


def test_a_player_with_no_probability_is_never_drawn_out():
    """"We have no appearance probability for him" is not "he will not play".
    A missing key drawing a zero would blank every player the minutes model
    has never seen — which on the first weekend of a season is most of them.
    """
    import numpy as np

    from gaffer.optimize.scenarios import availability_draw

    from tests.test_v12_w3_availability import _pool

    pool = _pool()
    assert availability_draw(pool, {}, np.random.default_rng(1)) == frozenset()
    partial = {int(pool["code"].iloc[0]): {5: 0.0}}
    drawn = availability_draw(pool, partial, np.random.default_rng(1))
    assert {code for code, _ in drawn} == {int(pool["code"].iloc[0])}


# =====================================================================
# Block 5 — §4.5: the empty state is the only state on today's fixtures
# =====================================================================


def test_no_chip_scenarios_file_means_no_pair_row_and_five_columns(tmp_path):
    """**This is the empty state spec §1 asks for**, and it is the state of
    every machine today: ``data/chip_scenarios.toml`` does not exist, and the
    writer refuses to create one while every published gameweek has ten
    fixtures. So ``load_chip_scenarios()`` is ``{}``, ``advise`` derives no
    doubles, and the table is exactly the table it was.
    """
    from gaffer.optimize.chip_policy import load_chip_scenarios
    from gaffer.optimize.chips import PAIR_CHIP

    from tests.test_v12_w3_chip_pairs import _table

    assert load_chip_scenarios(tmp_path / "chip_scenarios.toml") == {}
    table = _table()
    assert PAIR_CHIP not in set(table["chip"])
    assert list(table.columns) == ["chip", "gw", "gw2", "gain", "per_week"]


def test_gw2_is_none_on_a_single_chip_row_and_never_nan():
    """pandas turns a column of None-and-int into float64 with ``NaN``, which
    pydantic refuses and ``json.dumps`` writes as a bare ``NaN`` no browser
    will parse. Checked on the mixed table, where the coercion actually
    happens."""
    from gaffer.optimize.chips import PAIR_CHIP

    from tests.test_v12_w3_chip_pairs import _table

    rows = _table(dgw_gws={3}).to_dict("records")
    singles = [r for r in rows if r["chip"] != PAIR_CHIP]
    assert singles and all(r["gw2"] is None for r in singles)


def test_a_plan_whose_week_carries_no_bank_prices_off_today_and_says_so(
        capsys):
    """An older ``Plan`` off disk, or a solver that returned no value for the
    variable. The fallback is the pre-v12 number — today's squad and today's
    bank — printed, because a chip silently priced off a position nobody chose
    is worse than one priced off the wrong week loudly."""
    import dataclasses

    from gaffer.optimize.chips import chip_baseline, free_hit_gain
    from gaffer.optimize.milp import Plan

    from tests.test_v12_w3_free_hit import CFG, _pool, _state

    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    stale = Plan(objective=base.objective,
                 gw_plans=[dataclasses.replace(base.gw_plans[0], bank=None)]
                 + list(base.gw_plans[1:]))
    gain = free_hit_gain(pool, state, 1, base=stale, **CFG)
    assert "carries no bank for GW1" in capsys.readouterr().out
    assert gain is not None


# =====================================================================
# Block 6 — §4.6: no components frame is the first hour of every clone
# =====================================================================


def test_no_components_frame_leaves_the_captain_ceiling_where_it_was(capsys,
                                                                     tmp_path):
    """``bands_by_player_gw`` answers ``{}`` for anything unusable, ``advise``
    passes ``haul=None``, and the table keeps ``p_haul`` — the attacking
    ceiling it has always printed — and says why. The report renders it
    through the same fallback expression rather than raising on a column that
    is not there."""
    from gaffer.optimize.differentials import captain_table
    from gaffer.report.render import render_report
    from gaffer.uncertainty import bands_by_player_gw

    from tests.test_report import _advice
    from tests.test_v12_w3_dgw_captain import EO, XI, _ep

    assert bands_by_player_gw(None) == {}
    assert bands_by_player_gw(pd.DataFrame()) == {}

    out = captain_table(_ep(), XI, EO, haul=None)
    assert "p_haul" in out.columns and "p_haul_total" not in out.columns

    # A map covering nobody is the same degraded answer, and it is loud.
    covered_nobody = captain_table(_ep(), XI, EO, haul={999: 0.4})
    assert "p_haul" in covered_nobody.columns
    assert "no shortlisted captain carries a points band" in \
        capsys.readouterr().out

    # And the header degrades with the column (T8-T11 final review,
    # Important 1). ``_advice``'s captain option carries ``p_haul`` and no
    # ``p_haul_total`` — the degraded artifact — so the report must name the
    # attacking quantity it is actually printing. A fixed "P(10+ pts)" over
    # this table is the v9c failure the split was meant to end: a label
    # claiming a number the row does not hold.
    html = render_report(_advice(), out_dir=tmp_path).read_text()
    assert "P(2+ returns)" in html
    assert "P(10+ pts)" not in html
    assert "both fixtures" not in html      # the note goes with the header


def test_the_banded_captain_table_gets_the_banded_header(tmp_path):
    """The positive half of the pair above: with ``p_haul_total`` on the
    options the header and its note are the gameweek-total ones."""
    from gaffer.report.render import render_report

    from tests.test_report import _advice

    advice = _advice()
    advice.captain_options = [{"code": 1, "name": "P1", "position": "MID",
                               "ep": 8.0, "p_haul_total": 0.4,
                               "league_eo": 80.0, "differential": False}]
    html = render_report(advice, out_dir=tmp_path).read_text()
    assert "P(10+ pts)" in html
    assert "both fixtures" in html
    # This fixture carries no alternatives, so the attacking header is not on
    # the page at all; the count rail is about the captain column alone (the
    # header and its note), and tests/test_report.py holds the two-table case.
    assert html.count("P(10+ pts)") == 2   # the header and its note


def test_a_captain_with_no_band_is_an_em_dash_and_never_a_zero(tmp_path):
    """0% is a claim — "he will not haul" — and the strongest one available.
    The fourth null convention of the cycle, and the one a reviewer is most
    likely to propose defaulting "for the type's sake"."""
    from gaffer.report.render import render_report

    from tests.test_report import _advice

    advice = _advice()
    advice.captain_options = [
        {"code": 1, "name": "Banded", "position": "MID", "ep": 8.0,
         "p_haul_total": 0.4, "league_eo": 80.0, "differential": False},
        {"code": 2, "name": "Bandless", "position": "FWD", "ep": 7.0,
         "p_haul_total": None, "league_eo": 5.0, "differential": True}]
    html = render_report(advice, out_dir=tmp_path).read_text()
    assert "&mdash;" in html
    # The cell, not the string: the stylesheet above the table is full of
    # `width:100%`, and a bare `"0%" not in html` is a rail that passes for a
    # reason that has nothing to do with a captain.
    assert ">0%<" not in html


# =====================================================================
# Block 7 — the pins
# =====================================================================


def test_the_job_kinds_did_not_move():
    """W3 adds no job. The alternatives are two more solves inside the advise
    run, which already has a kind — and a thirteenth would also need a row in
    ABANDON_TIMEOUT_S and SLOW_ABANDON_KINDS, pinned as jointly exhaustive in
    the protected test_v9d_degradation.py."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_gained_exactly_two_fields():
    """``[optimizer] alt_plan_max_gap`` and ``[scenarios] draw_availability``.

    **The only absolute config-field pin in the suite**, and it moves with
    every workstream that adds a key — which is why it lives in the newest
    cycle's file and nowhere else. 48 at the program's spec commit
    (``27f7933``), 53 after W1 and W2, 55 here; the *claim* is the two, and 55
    is only the arithmetic on a base that has already moved twice this
    program. W1's file keeps the by-name claim about its own five keys
    (orchestrator ruling, 2026-09-02).

    Pinned as a total *and* by name: a count alone would let a key be added
    and another removed in one cycle.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert len(names) == 55
    assert {"alt_plan_max_gap", "draw_availability"} <= names


def test_the_route_total_did_not_move(tmp_path, monkeypatch):
    """W3 adds no route: the alternatives ride an existing payload, the chip
    pair rides an existing row, and every serve-side change is an additive
    field on a model that already existed.

    Pinned **by absence only**. The suite's single absolute route count lives
    in ``tests/test_v11_degradation.py``, which is where v11's restructure put
    it and where W1 spent it (45 → 46); a second file asserting the same total
    is the shape both restructures existed to end, and
    ``test_v12_w1_degradation.py`` has a rail that fails if one appears. A
    cycle that adds a route moves it there. This one does not.
    """
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert not [p for p in paths
                if p.startswith(("/api/alternatives", "/api/forceout",
                                 "/api/support"))]


# =====================================================================
# Block 8 — the protected-diff audit
# =====================================================================

# v12 W3 (orchestrator ruling 2026-09-02): a workstream's audit rail measures
# that workstream's own range. Scoped to "everything since main" it would fail
# on the first authorized protected commit of the *next* cycle, which is a
# rail reporting somebody else's diff under W3's name — the W2 rail was
# re-pinned the same way at 7e1645f.
#
# T8-T11 final review, Minor 3: re-pinned from 754e1d1 after this branch was
# rebased onto 865f8dc. 754e1d1 is still an ancestor, so the rail still
# *passed* — but 754e1d1..HEAD had become a superset carrying main's own W2
# gate commits, and a rail that audits three commits nobody on W3 wrote is
# reporting somebody else's diff under W3's name, which is the exact failure
# the pin exists to prevent. (None of those commits touched a protected file,
# so the verdict was unchanged; the range was wrong regardless.) 865f8dc is
# the branch point.
W2_TIP = "865f8dc"

W3_AUTHORIZED = {
    # The STOP enumerations, task by task.
    "src/gaffer/optimize/milp.py",              # T1, T5, T10 — §4.1/§4.3/§4.5
    "src/gaffer/web/routers/whatif.py",         # T2 — §4.1
    "src/gaffer/optimize/chip_policy.py",       # T4 — §4.2
    "src/gaffer/optimize/chips.py",             # T4, T9, T10 — §4.2/§4.5
    "src/gaffer/advise.py",                     # T4, T6, T8, T9, T10, T11
    "src/gaffer/optimize/scenarios.py",         # T8 — §4.4
    "src/gaffer/optimize/differentials.py",     # T11 — §4.6
    "tests/test_v10_degradation.py",            # T8 — the narrowed T10-A rail
    "tests/test_advise.py",                     # the EO rail's spelling (T11)
    "tests/test_v12_w2_degradation.py",         # the W2 rail's range (T2)
    "tests/test_v12_w1_degradation.py",         # the config pin's home (T12)
}


def _protected(path: str) -> bool:
    return (path in {"src/gaffer/advise.py", "src/gaffer/set_pieces.py",
                     "src/gaffer/web/jobs.py",
                     "src/gaffer/web/routers/whatif.py",
                     "tests/test_advise.py", "tests/test_odds.py",
                     "tests/test_web_jobs.py", "scripts/s2_replay.py"}
            or path.startswith("src/gaffer/optimize/")
            or (path.startswith("tests/test_") and path.endswith(
                "_degradation.py")
                and path != "tests/test_v12_w3_degradation.py"))


def test_every_protected_file_w3_touched_was_authorized():
    """The audit, as a test rather than as a step somebody remembers to run.

    Nine of W3's fifteen tasks are STOPs, so unlike most cycles the expected
    protected diff is **not** empty — the claim is that it contains exactly the
    files the STOPs enumerated and nothing else. ``set_pieces.py``,
    ``web/jobs.py``, ``test_odds.py``, ``test_web_jobs.py`` and
    ``scripts/s2_replay.py`` are in the protected list and in no enumeration,
    so a hit on any of them fails here.

    The range is W3's own — ``W2_TIP..HEAD``, this branch's point of departure
    to its head — and not ``merge-base(HEAD, main)..HEAD``: once W3 merges,
    that base moves and this rail would start auditing whatever came next. The
    pin is re-checked after every rebase for the same reason (see ``W2_TIP``).
    If it is unreachable — a shallow clone, an export, a tree with no git at
    all — the audit is skipped rather than answered from a range that does not
    exist.
    """
    probe = subprocess.run(["git", "cat-file", "-e", f"{W2_TIP}^{{commit}}"],
                           capture_output=True, check=False)
    if probe.returncode:
        pytest.skip(f"{W2_TIP} unreachable — W3's range is not in this tree")
    changed = subprocess.run(["git", "diff", "--name-only", W2_TIP, "HEAD"],
                             capture_output=True, text=True,
                             check=False).stdout.split()
    touched = {p for p in changed if _protected(p)}
    assert not touched - W3_AUTHORIZED
    # And not vacuous: the seven source files the STOPs enumerate are all
    # supposed to have moved, so a range that comes back empty — a rebase, a
    # squash, a mis-typed SHA — fails here rather than passing as "clean".
    assert {p for p in W3_AUTHORIZED if p.startswith("src/")} <= touched


def test_the_branch_banks_no_data_and_no_config():
    """CONVENTIONS §8's half that a grep for keys cannot see: a staged
    ``config.toml`` or a parquet under ``data/`` is a private tree in a public
    branch, and every one of them got there by an ``add -A`` somebody was in a
    hurry to type.

    T8-T11 final review, Minor 4: the prefix was ``data/live/``, which is the
    directory the docstring's own sentence does *not* say. ``data/`` is where
    the entry's picks, the league's rivals and every scraped season sit —
    ``data/live/`` is one subdirectory of it, and a banked
    ``data/chip_scenarios.toml`` or ``data/player_gw.parquet`` walked straight
    past the rail that exists to stop it. The one carve-out is the tracked
    ``data/`` fixtures under ``tests/``, which this prefix never matched."""
    probe = subprocess.run(["git", "cat-file", "-e", f"{W2_TIP}^{{commit}}"],
                           capture_output=True, check=False)
    if probe.returncode:
        pytest.skip(f"{W2_TIP} unreachable — W3's range is not in this tree")
    changed = subprocess.run(["git", "diff", "--name-only", W2_TIP, "HEAD"],
                             capture_output=True, text=True,
                             check=False).stdout.split()
    assert not [p for p in changed
                if p == "config.toml"
                or p.startswith(("data/", "reports/", "models/", "logs/",
                                 "src/gaffer/web/static/"))]
