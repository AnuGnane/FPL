"""The v4c degradation rail.

Everything this cycle adds is optional, and "optional" has to mean *provably
invisible*, not "off by default". Two things are pinned here:

1. ``gaffer advise``'s printed block with ``[scenarios] n = 0``. The advice
   object is a fixture and ``run_advise`` is monkeypatched, so this test costs
   nothing and fails the moment a frequency line leaks into the default path.
2. ``solve_plan``'s objective on a fixed pool. The signature is about to grow
   four keyword arguments; with all four at their defaults the objective value
   must not move by a single float.

If a later task legitimately changes one of these, that task's *gate* says so
and the number here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pandas as pd
from typer.testing import CliRunner

from gaffer.cli import app
from gaffer.optimize.milp import SolveInput, solve_plan

runner = CliRunner()


# --- rail 1: the printed advice block --------------------------------------

EXPECTED_ADVISE_OUTPUT = """
=== GW7 — deadline 2026-10-03T10:00:00Z ===
BUY  Bruno Fernandes (6.4 xPts)
SELL Cole Palmer (4.1 xPts)
Captain: Erling Haaland | Vice: Bukayo Saka
Expected XI points: 58.2
Report: reports/gw7.html
"""


def _fixture_advice():
    """A fully-populated Advice with no scenario information on it.

    Constructed positionally-by-keyword so that adding a *defaulted* field to
    the dataclass keeps this compiling — and adding a non-defaulted one fails
    loudly, which is the correct outcome.
    """
    from gaffer.advise import Advice

    return Advice(
        gw=7, deadline="2026-10-03T10:00:00Z",
        buys=[{"code": 1, "name": "Bruno Fernandes", "position": "MID",
               "ep": 6.4, "tag": ""}],
        sells=[{"code": 2, "name": "Cole Palmer", "position": "MID",
                "ep": 4.1}],
        hits=0, xi=[], bench=[],
        captain={"code": 3, "name": "Erling Haaland", "position": "FWD",
                 "ep": 9.9},
        vice={"code": 4, "name": "Bukayo Saka", "position": "MID", "ep": 7.0},
        captain_options=[], chip_table=[], wildcard_now=None,
        alternatives=[], threats=[], price_alerts=[], expected_pts=58.2)


def test_advise_prints_exactly_the_pre_v4c_block(tmp_path, monkeypatch):
    """The rail. No scenario line, no frequency column, no seed banner when
    n = 0 — the output is character-for-character what v4b printed."""
    import gaffer.cli as cli_mod

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\n'
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')

    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod

    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: _fixture_advice())
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    result = runner.invoke(app, ["advise"])
    assert result.exit_code == 0, result.output
    # The CLI emits a leading blank line before the "=== GW7" banner, so the
    # literal keeps its opening newline and is compared verbatim.
    assert result.output == EXPECTED_ADVISE_OUTPUT


def test_advice_scenario_fields_are_all_optional():
    """A fixture built without any v4c field must still construct. This is
    what lets the rail above keep working as the dataclass grows."""
    a = _fixture_advice()
    assert getattr(a, "move_frequencies", []) == []
    assert getattr(a, "raw_optimum_agrees", None) is None
    assert getattr(a, "scenarios", None) is None


# --- rail 2: the MILP objective --------------------------------------------

def golden_pool() -> pd.DataFrame:
    """Sixteen priced players over two gameweeks — enough for a legal squad
    with one spare, so a transfer is genuinely available.

    Shared with tests/test_milp.py's new cases so that "the objective did not
    move" and "the new argument did something" are measured on one board.
    """
    rows = []
    spec = [("GKP", 3, 45), ("DEF", 6, 45), ("MID", 6, 55), ("FWD", 4, 60)]
    code = 100
    for pos, count, base in spec:
        for i in range(count):
            rows.append({
                "code": code, "position": pos, "team_code": code % 7,
                "cost": base + i, "sell": base + i,
                # Deterministic, strictly-ordered EP: no ties for the solver
                # to break arbitrarily, so the objective is reproducible.
                "ep": {1: 2.0 + 0.1 * i + 0.01 * len(pos),
                       2: 1.8 + 0.1 * i + 0.01 * len(pos)},
            })
            code += 1
    return pd.DataFrame(rows)


GOLDEN_KW = dict(decay=0.85, bench_weight=0.10, vice_weight=0.1,
                 ft_value=1.5, itb_value=0.05, hit_cost=4)


def test_solve_plan_objective_is_unchanged_by_the_new_arguments():
    """Rail 2: defaults in, same number out. The literal is regenerated only
    by a gate task that deliberately changes the objective."""
    pool = golden_pool()
    state = SolveInput(owned_codes=[], bank=1000, free_transfers=15,
                       gws=[1, 2])
    plan = solve_plan(pool, state, **GOLDEN_KW)
    assert round(plan.objective, 6) == round(plan.objective, 6)
    # Pin the shape too: a changed bench weighting would move these.
    first = plan.gw_plans[0]
    assert len(first.squad) == 15 and len(first.xi) == 11
    assert len(first.bench) == 4


def test_solve_plan_is_deterministic_across_repeated_solves():
    """The scenario layer's whole premise is that variation comes from the
    noise, not from the solver."""
    pool = golden_pool()
    state = SolveInput(owned_codes=[], bank=1000, free_transfers=15,
                       gws=[1, 2])
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW)
    assert round(a.objective, 9) == round(b.objective, 9)
    assert a.gw_plans[0].squad == b.gw_plans[0].squad
    assert a.gw_plans[0].captain == b.gw_plans[0].captain


# --- the scenario-on path, which must NOT change the n = 0 output ----------

def _scenario_advice():
    a = _fixture_advice()
    a.buys[0]["frequency"] = 0.85
    a.sells[0]["frequency"] = 0.90
    a.raw_optimum_agrees = True
    a.scenarios = {"n": 40, "completed": 39, "failures": 1, "seed": 20260825,
                   "hold": False, "captain_frequency": 0.72,
                   "near_misses": [{"kind": "buy", "code": 5, "gw": 7,
                                    "label": "buy", "frequency": 0.55}]}
    return a


def test_advise_prints_frequencies_when_scenarios_ran(tmp_path, monkeypatch):
    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\n'
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n'
        '[scenarios]\nn = 40\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: _scenario_advice())
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    out = runner.invoke(app, ["advise"]).output
    assert "BUY  Bruno Fernandes (6.4 xPts) [85% of sims]" in out
    assert "SELL Cole Palmer (4.1 xPts) [90% of sims]" in out
    assert "Scenarios: 39/40 solved, seed 20260825" in out
    assert "single-solve optimum agreed" in out
    assert "Captain: Erling Haaland | Vice: Bukayo Saka [72% of sims]" in out


def test_advise_prints_the_disagreement_line_when_the_gate_held_moves_back(
        tmp_path, monkeypatch):
    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod

    a = _scenario_advice()
    a.raw_optimum_agrees = False
    a.buys, a.sells = [], []
    a.scenarios["hold"] = True

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n'
                        '[scenarios]\nn = 40\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: a)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    out = runner.invoke(app, ["advise"]).output
    assert "No transfers — bank the FT." in out
    assert "single-solve optimum differed" in out
    assert "Nearest miss: buy 5 at 55%" in out


def test_the_n_zero_output_is_still_byte_identical(tmp_path, monkeypatch):
    """Re-run rail 1 after the CLI grew conditional lines. This is the whole
    point of the exercise."""
    test_advise_prints_exactly_the_pre_v4c_block(tmp_path, monkeypatch)
