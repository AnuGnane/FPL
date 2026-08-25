# Gaffer v4c "Decide" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing MILP in a decision layer — N noised re-solves whose move frequencies gate the advice, a DP-priced free-transfer shadow price, and per-week chip stopping thresholds — so the tool stops acting on a single estimation-error-maximizing optimum.

**Architecture:** Four new pure-computation modules under `src/gaffer/optimize/` sit *after* the pool is built and *around* `solve_plan`, which itself gains four optional keyword arguments that all default to today's behaviour. `scenarios.py` noises the pool's EP by a minutes-scaled factor and re-solves N times; `policy.py` turns the resulting move frequencies into a gated recommendation and re-solves once with those moves fixed; `ft_value.py` and `chip_policy.py` are offline-calibrated tables (`src/gaffer/assets/decision_priors.json`) that price banked transfers and time chips. Every integration point is conditional: `[scenarios] n = 0` and an absent priors asset each leave the pipeline byte-identical to pre-v4c, and the gate tasks flip the defaults only after replay measurement.

**Tech Stack:** Python 3.12, pandas, numpy, PuLP + HiGHS (CBC fallback), Typer, pytest (`uv run pytest`); React 18 + TypeScript + Vite + vitest in `frontend/`, FastAPI in `src/gaffer/web/`.

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `src/gaffer/optimize/scenarios.py` | `xmins_by_player_gw`, `noise_ep`, `noised_pool`, `ScenarioRun`, `run_scenarios`, `move_frequencies`. Pure computation over a pool frame and a `SolveInput`; no I/O. |
| `src/gaffer/optimize/policy.py` | `Thresholds`, `Decision`, `decide`, `coherent_plan`. Turns a frequency table into a gated recommendation and re-solves it coherently. |
| `src/gaffer/optimize/ft_value.py` | `lambda_table` (the λ(k,t) value-iteration DP), `LambdaLookup`, `lambda_from_priors`. |
| `src/gaffer/optimize/chip_policy.py` | `stopping_thresholds` (θ_t backward recursion), `load_chip_scenarios`, `apply_dgw_scenarios`, `thresholds_from_priors`, `flat_thresholds`. |
| `src/gaffer/calibrate_decisions.py` | The offline replay that produces `assets/decision_priors.json`: transfer-surplus and chip-surplus distributions plus the two derived tables. |
| `src/gaffer/assets/decision_priors.json` | Committed calibration asset. Absent → flat `ft_value` and flat chip thresholds. |
| `tests/test_scenarios.py` | Noise scaling, xmins, determinism, dropped scenarios, frequency aggregation. |
| `tests/test_policy.py` | Threshold gating, captain plurality, hold fallback, coherence re-solve. |
| `tests/test_ft_value.py` | λ DP monotonicity in k, decay in t, cap-5 overflow, hand-checkable toys. |
| `tests/test_chip_policy.py` | θ_T = 0, monotone decline, E[max] ≥ E, DGW scenario shift, flat fallback. |
| `tests/test_calibrate_decisions.py` | Priors schema, asset round-trip, absent-asset fallbacks. |
| `tests/test_v4c_degradation.py` | The degradation rail: `n = 0` CLI output and the `solve_plan` objective identity. |

**Modified:**

| Path | Change |
| --- | --- |
| `src/gaffer/config.py` | `[scenarios]` section; `ft_use_penalty` / `bench_curve` on `[optimizer]`. |
| `src/gaffer/optimize/milp.py` | `FixedMoves`; `fixed_moves`, `ft_lambda`, `ft_use_penalty`, `bench_curve` keyword arguments; ordered bench-slot objective. |
| `src/gaffer/optimize/chips.py` | `ft_bank_value` subtracted in `wildcard_now_assessment`; `threshold_for` and the `thresholds` argument on `chip_plan`. |
| `src/gaffer/advise.py` | Scenario + policy block after the deterministic solve, guarded by `cfg.scenarios_n`; λ and θ resolution; new `Advice` fields. |
| `src/gaffer/backtest.py` | `_pick_chip` takes a threshold lookup; `opt_kw` gains the new knobs; chip-expiry sweep. |
| `src/gaffer/cli.py` | `calibrate-decisions` command; frequency lines in `advise` output. |
| `src/gaffer/assets/__init__.py` | `load_decision_priors` / `decision_priors_exist`. |
| `src/gaffer/report/templates/report.html.j2` | Frequency column and chip θ columns. |
| `frontend/src/types.ts` | `frequency` on `AdvicePlayer`; `move_frequencies`, `raw_optimum_agrees`, `scenarios` on `Advice`. |
| `frontend/src/pages/ThisWeek.tsx` | "% of sims" column on the transfers table. |
| `frontend/src/pages/ThisWeek.test.tsx` | Column presence with and without frequencies. |
| `tests/test_config.py` | New keys and defaults. |
| `tests/test_milp.py` | `fixed_moves`, `ft_lambda`, `ft_use_penalty`, `bench_curve`. |
| `tests/test_chips.py` | Wildcard FT-bank subtraction, θ-aware `chip_plan`. |
| `tests/test_advise.py` | Re-pinned protected orderings plus the scenario-block guard. |
| `tests/test_backtest.py` | Threshold injection, chip-expiry sweep. |
| `tests/test_cli.py` | `calibrate-decisions` in both command lists. |
| `data/chip_scenarios.toml` | Not created — the *hook* is created; the file stays absent this cycle. |

---

## Protected source-text tests — read this before touching `advise.py` or `backtest.py`

Three suites assert on the **source text** of `run_advise`, `run_backtest` and
`predict_components`. They exist because there is no cheap end-to-end harness
for those functions, and they are the reason several tasks below end by running
the whole suite rather than one file.

- `tests/test_assemble.py:215` — `"ep_matrix(apply_calibration(assemble_ep(" in src`
  for **both** `run_advise` and `run_backtest`.
- `tests/test_odds.py:315` — inside `run_advise`:
  `odds_frame(raw_odds, teams, events)` < `tg_future = build_team_future(` <
  `merge_team_odds(tg_future, odds_df)`, plus `"if cfg.odds_api_key:" in src`,
  `"except Exception" in src`, and `"drop_duplicates" not in src`.
- `tests/test_advise.py:73` — inside `run_advise`:
  `fetch_rival_entries(` < `tilt_ep(` < `pool = build_pool(`, plus
  `compute_strategy(` < `pool = build_pool(`, `"except Exception" in src`,
  `'summary_overall_points' in src`, and the literal
  `"build_pool(players, pool_ep," in src`.
- `tests/test_advise.py:97` — also inside `run_advise`: `"ep_named = ep.merge(" in src`,
  `'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src`,
  **`"pool_ep" not in src[src.index("ep_gw1 ="):]`**, and
  `'_named(first.xi, name_of, pos_of, ep_by, gw)' in src`.

The last one is the sharp edge. Everything this plan inserts into `run_advise`
goes **immediately after** `plan = solve_plan(pool, state, **solve_kw)` — which
is well before `ep_gw1 =` — and **nothing inserted anywhere may contain the
substring `pool_ep`**. The scenario layer therefore takes the `pool` frame, not
`pool_ep`. Task 9 restates this; Tasks 10 and 22 re-run the whole suite for the
same reason.

---

## Task 1: The `[scenarios]` config section and the two new optimizer knobs

Every v4c integration point is gated by config, and all four gates default to
today's behaviour. `n = 0` is the master switch for the scenario layer;
`ft_use_penalty = 0.0` and `bench_curve = None` keep the objective term-for-term
identical until Gate D2 measures them.

`[optimizer]` is splatted into `Config` by `load_config`, so its two new keys
need only new dataclass fields. `[scenarios]` is a brand-new optional section
whose TOML names differ from the field names, so it is read explicitly — the
same pattern `[odds]` already uses.

**Files:**
- Modify: `src/gaffer/config.py:8-24` (`Config`), `:27-45` (`load_config`)
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
# --- v4c decision layer ----------------------------------------------------


def _write(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n' + body)
    return p


def test_scenario_count_defaults_to_zero(tmp_path):
    """n = 0 is the degradation rail: until the gates pass, a fresh clone
    must solve exactly once and print exactly what v4b printed."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.scenarios_n == 0


def test_scenario_thresholds_default_to_the_spec_bars(tmp_path):
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.transfer_threshold == 0.60
    assert cfg.irreversible_threshold == 0.75


def test_scenario_seed_defaults_to_a_fixed_value(tmp_path):
    """Reproducibility is a stated requirement: the same seed must give the
    same advice, and the seed is logged in the report."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert isinstance(cfg.scenarios_seed, int)
    assert cfg.scenarios_seed == 20260825


def test_scenarios_section_is_read(tmp_path):
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, """
[scenarios]
n = 40
seed = 7
transfer_threshold = 0.5
irreversible_threshold = 0.9
"""))
    assert cfg.scenarios_n == 40
    assert cfg.scenarios_seed == 7
    assert cfg.transfer_threshold == 0.5
    assert cfg.irreversible_threshold == 0.9


def test_decision_priors_default_to_enabled(tmp_path):
    """The asset is the thing that may be missing, not the switch. The switch
    exists so a gate failure can be turned off without deleting the file."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.decision_priors is True

    off = load_config(_write(tmp_path, "\n[scenarios]\ndecision_priors = false\n"))
    assert off.decision_priors is False


def test_ft_use_penalty_and_bench_curve_default_to_the_old_objective(tmp_path):
    """Gate D2 flips these. Until then the objective must be term-for-term
    what it was, or the replay comparison measures two changes at once."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.ft_use_penalty == 0.0
    assert cfg.bench_curve is None


def test_optimizer_section_carries_the_new_knobs(tmp_path):
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, """
[optimizer]
ft_use_penalty = 0.2
bench_curve = [0.21, 0.06, 0.002]
"""))
    assert cfg.ft_use_penalty == 0.2
    assert cfg.bench_curve == [0.21, 0.06, 0.002]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -k scenario -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'scenarios_n'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/config.py`, add the six fields to `Config` (after
`understat_enabled`):

```python
    # --- v4c decision layer ------------------------------------------------
    # Every one of these defaults to the pre-v4c behaviour. n = 0 means "solve
    # once, deterministically"; the two objective knobs are neutral elements.
    scenarios_n: int = 0
    scenarios_seed: int = 20260825
    transfer_threshold: float = 0.60
    irreversible_threshold: float = 0.75
    decision_priors: bool = True
    ft_use_penalty: float = 0.0
    bench_curve: list[float] | None = None
```

and extend `load_config`'s body — hoist the section next to `odds` and add the
five explicit reads to the `Config(...)` call:

```python
    odds = raw.get("odds", {})
    # [scenarios] is optional and its TOML keys are deliberately shorter than
    # the field names (n, seed), so it is read key-by-key like [odds] rather
    # than splatted. [optimizer] keeps splatting, so ft_use_penalty and
    # bench_curve need no line here.
    scen = raw.get("scenarios", {})
```

```python
        scenarios_n=int(scen.get("n", 0)),
        scenarios_seed=int(scen.get("seed", 20260825)),
        transfer_threshold=float(scen.get("transfer_threshold", 0.60)),
        irreversible_threshold=float(
            scen.get("irreversible_threshold", 0.75)),
        decision_priors=bool(scen.get("decision_priors", True)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (whole file)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/config.py tests/test_config.py
git commit -m "feat: [scenarios] config section and the neutral objective knobs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 2: The degradation rail, pinned before anything else moves

Spec §9 makes this a merge gate: with `[scenarios] n = 0`, `gaffer advise`
output must be byte-identical to today's. Pin it *now*, while "today" is still
what the tree does, so every later task has something to break.

Two rails, because there are two ways to break it. The first pins the CLI's
printed block against a literal expected string, driven by a fixture `Advice`
with `run_advise` monkeypatched — no network, no models, no solver. The second
pins the MILP objective: `solve_plan` is about to grow four keyword arguments,
and with all four at their defaults the objective must be the same expression
it is today, which a fixed-pool golden objective value proves.

**Files:**
- Create: `tests/test_v4c_degradation.py`
- Test: `tests/test_v4c_degradation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_v4c_degradation.py`:

```python
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
    assert result.output == EXPECTED_ADVISE_OUTPUT.lstrip("\n")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_v4c_degradation.py -v`
Expected: FAIL — `test_advise_prints_exactly_the_pre_v4c_block` fails with an
`AssertionError` on the string comparison, because `EXPECTED_ADVISE_OUTPUT`
above was written from the plan rather than from a run.

- [ ] **Step 3: Write minimal implementation**

There is no source change in this task. The "implementation" is capturing the
real output once and pinning it:

Run: `uv run pytest tests/test_v4c_degradation.py -k pre_v4c -v`

The failure prints both strings. Copy the **actual** output verbatim into
`EXPECTED_ADVISE_OUTPUT`, preserving every space and newline (note the leading
blank line the CLI emits before `=== GW7`, which the `.lstrip("\n")` in the
assertion accounts for by stripping it from the *literal*, not the output — if
the real output starts with a newline, drop the `.lstrip("\n")` instead of
editing the literal).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_v4c_degradation.py -v`
Expected: PASS (4 passed)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_v4c_degradation.py
git commit -m "test: pin the v4c degradation rail before anything moves

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 3: `scenarios.py` — xMins and the minutes-scaled noise

Spec §3's first half. The noise on a player-gameweek EP cell is
`ep × (92 − xmins) / 134 × N(0, 1)`: a nailed-on 90-minute starter barely
wobbles, a rotation risk wobbles a lot, and the scale is proportional to the
EP itself so a 9-point captain and a 2-point defender move on the same relative
footing. `xmins = 90 × p_play × p60 + 45 × p_play × (1 − p60)`, clipped to
[0, 92], which are exactly the two columns `predict_components` already puts on
the component frame.

The component frame is one row per player-*fixture*, so a double gameweek has
two rows for the same `(code, gw)`. Those are averaged, not summed: `xmins` is
"how nailed-on is this player", and a nailed-on DGW starter is just as nailed
on as a nailed-on SGW starter. Their EP is already doubled, so the absolute
noise doubles with it, which is the right behaviour.

**Files:**
- Create: `src/gaffer/optimize/scenarios.py`
- Test: `tests/test_scenarios.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scenarios.py`:

```python
import numpy as np
import pandas as pd

from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       noise_ep, noised_pool,
                                       xmins_by_player_gw)


def _comp() -> pd.DataFrame:
    """Component frame in predict_components' shape: one row per fixture."""
    return pd.DataFrame([
        {"code": 1, "gw": 5, "opp_code": 9, "p_play": 1.0, "p60": 1.0},
        {"code": 2, "gw": 5, "opp_code": 9, "p_play": 0.0, "p60": 0.0},
        {"code": 3, "gw": 5, "opp_code": 9, "p_play": 0.8, "p60": 0.5},
    ])


def test_xmins_of_a_nailed_on_starter_is_ninety():
    out = xmins_by_player_gw(_comp())
    assert out[(1, 5)] == 90.0


def test_xmins_of_a_player_who_never_plays_is_zero():
    out = xmins_by_player_gw(_comp())
    assert out[(2, 5)] == 0.0


def test_xmins_matches_the_hand_computed_formula():
    out = xmins_by_player_gw(_comp())
    want = 90 * 0.8 * 0.5 + 45 * 0.8 * (1 - 0.5)
    assert abs(out[(3, 5)] - want) < 1e-12


def test_xmins_is_clipped_to_the_ninety_two_ceiling():
    """The formula cannot exceed 90, but a DGW average of two 90s is still 90
    and a corrupt p_play > 1 must not produce negative noise scale."""
    comp = _comp()
    comp.loc[0, "p_play"] = 1.4
    out = xmins_by_player_gw(comp)
    assert out[(1, 5)] == NOISE_FLOOR_XMINS


def test_xmins_averages_a_double_gameweek_rather_than_summing_it():
    """Two fixtures do not make a player twice as nailed on; their EP is
    already doubled, so the absolute noise doubles on its own."""
    comp = pd.concat([_comp(), pd.DataFrame([
        {"code": 1, "gw": 5, "opp_code": 11, "p_play": 1.0, "p60": 1.0}])],
        ignore_index=True)
    assert xmins_by_player_gw(comp)[(1, 5)] == 90.0


def test_xmins_of_a_frame_without_the_minutes_columns_is_empty():
    """Degradation: no minutes model output means no scenario noise, which
    noise_ep turns into a no-op rather than a crash."""
    assert xmins_by_player_gw(pd.DataFrame({"code": [1], "gw": [5]})) == {}


# --- noise -----------------------------------------------------------------

def test_noise_on_a_ninety_two_minute_player_is_exactly_zero():
    """The point of the scaling: a certainty has no estimation error left to
    simulate."""
    ep = {(1, 5): 6.0}
    out = noise_ep(ep, {(1, 5): 92.0}, np.random.default_rng(0))
    assert out[(1, 5)] == 6.0


def test_noise_on_a_zero_minute_player_is_the_full_scale():
    ep = {(1, 5): 6.0}
    rng = np.random.default_rng(3)
    draw = np.random.default_rng(3).standard_normal()
    out = noise_ep(ep, {(1, 5): 0.0}, rng)
    want = max(0.0, 6.0 + 6.0 * (92.0 - 0.0) / NOISE_DENOM * draw)
    assert abs(out[(1, 5)] - want) < 1e-12


def test_noise_is_deterministic_under_a_fixed_seed():
    ep = {(1, 5): 6.0, (2, 5): 3.0, (1, 6): 5.0}
    xm = {(1, 5): 40.0, (2, 5): 10.0, (1, 6): 70.0}
    a = noise_ep(ep, xm, np.random.default_rng(11))
    b = noise_ep(ep, xm, np.random.default_rng(11))
    assert a == b


def test_noise_differs_between_two_draws_from_the_same_generator():
    """One draw per player-GW per scenario, so consecutive scenarios off the
    same generator must not repeat."""
    ep = {(1, 5): 6.0}
    rng = np.random.default_rng(11)
    assert noise_ep(ep, {(1, 5): 10.0}, rng) != noise_ep(
        ep, {(1, 5): 10.0}, rng)


def test_noise_never_produces_a_negative_expected_score():
    """A large downward draw on a low-xmins player can cross zero; a negative
    EP would make the MILP want to bench a player it cannot bench."""
    ep = {(c, 5): 0.2 for c in range(200)}
    xm = {(c, 5): 0.0 for c in range(200)}
    out = noise_ep(ep, xm, np.random.default_rng(2))
    assert min(out.values()) >= 0.0


def test_noise_leaves_cells_with_no_xmins_untouched():
    """A player with no minutes prediction is not a player with certain
    minutes; leaving the cell alone is the honest degradation."""
    out = noise_ep({(1, 5): 6.0}, {}, np.random.default_rng(0))
    assert out == {(1, 5): 6.0}


def test_noise_does_not_mutate_its_input():
    ep = {(1, 5): 6.0}
    noise_ep(ep, {(1, 5): 0.0}, np.random.default_rng(0))
    assert ep == {(1, 5): 6.0}


# --- pool ------------------------------------------------------------------

def _pool() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "position": "MID", "team_code": 3, "cost": 70, "sell": 70,
         "ep": {5: 6.0, 6: 5.0}},
        {"code": 2, "position": "DEF", "team_code": 4, "cost": 50, "sell": 50,
         "ep": {5: 3.0, 6: 3.5}},
    ])


def test_noised_pool_keeps_every_column_and_row():
    """The candidate set must not change between scenarios, or the move
    frequencies are counting different boards."""
    out = noised_pool(_pool(), {(1, 5): 40.0}, np.random.default_rng(0))
    assert list(out.columns) == list(_pool().columns)
    assert list(out["code"]) == [1, 2]


def test_noised_pool_replaces_the_ep_dicts_without_mutating_the_original():
    pool = _pool()
    out = noised_pool(pool, {(1, 5): 0.0, (1, 6): 0.0, (2, 5): 0.0,
                             (2, 6): 0.0}, np.random.default_rng(4))
    assert pool.loc[0, "ep"] == {5: 6.0, 6: 5.0}
    assert out.loc[0, "ep"] != pool.loc[0, "ep"]
    assert set(out.loc[0, "ep"]) == {5, 6}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scenarios.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.optimize.scenarios'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/optimize/scenarios.py`:

```python
"""Scenario re-solving: N noised optima instead of one certain one.

The MILP is an estimation-error maximizer. Handed a forecast, it finds the
squad whose EP is highest — which, when every EP carries error, means it
systematically finds the players whose error happens to be most positive this
week. v4a measured the cost of that: a planning ceiling ~175 points above what
the tool actually scores, most of it thrown away on transfers that were never
robust to the forecast being slightly wrong.

The fix is not a better forecast; it is refusing to bet the week on one draw
from it. Perturb every EP cell by its own plausible error, re-solve, and count
how often each move survives. A transfer that shows up in 38 of 40 noised
worlds is a real edge; one that shows up in 12 is the optimizer reading tea
leaves.

The error scale is minutes-driven, which is the community-standard choice and
the right one: almost all of FPL's forecast error is *did he play*, not *how
well did he play*. A nailed-on 90-minute starter has very little error left in
his EP; a 60/40 rotation risk has an enormous amount.

Nothing here does I/O and nothing here is random unless a generator says so —
the caller owns the seed, and the seed goes in the report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

NOISE_FLOOR_XMINS = 92.0
"""xMins at which the noise scale reaches zero.

92 rather than 90 because the community formula this follows uses the full
match including stoppage time as the "certain" anchor, which leaves a genuine
90-minute nailed-on starter with a small but non-zero wobble instead of a
mathematically impossible zero.
"""

NOISE_DENOM = 134.0
"""Divisor turning (92 - xmins) into a relative standard deviation.

At xmins = 0 the scale is 92/134 = 0.687, i.e. a player with no expected
minutes has a ~69% relative standard deviation on his EP. At xmins = 90 it is
0.015. Both are about right against observed weekly FPL residuals.
"""


def xmins_by_player_gw(comp: pd.DataFrame) -> dict[tuple[int, int], float]:
    """``{(code, gw): expected minutes}`` from the component frame.

    ``90 * p_play * p60 + 45 * p_play * (1 - p60)``: he plays the whole match
    if he starts and lasts, and half of one if he plays but does not reach 60.

    ``comp`` is one row per player-*fixture*, so a double gameweek contributes
    two rows for the same ``(code, gw)``. They are **averaged**. xMins here is
    a nailedness score feeding a *relative* noise scale, and a nailed-on
    starter with two fixtures is exactly as nailed on as one with a single
    fixture — his EP is already doubled, so his absolute noise doubles without
    any help from this function.

    A frame with no ``p_play``/``p60`` (no minutes model) returns ``{}``, which
    :func:`noise_ep` treats as "leave every cell alone".
    """
    if not {"p_play", "p60", "code", "gw"}.issubset(comp.columns):
        return {}
    p_play = pd.to_numeric(comp["p_play"], errors="coerce").fillna(0.0)
    p60 = pd.to_numeric(comp["p60"], errors="coerce").fillna(0.0)
    xm = 90.0 * p_play * p60 + 45.0 * p_play * (1.0 - p60)
    frame = pd.DataFrame({"code": comp["code"].astype(int),
                          "gw": comp["gw"].astype(int),
                          "xmins": xm.clip(0.0, NOISE_FLOOR_XMINS)})
    grouped = frame.groupby(["code", "gw"], as_index=False)["xmins"].mean()
    return {(int(r.code), int(r.gw)): float(r.xmins)
            for r in grouped.itertuples()}


def noise_ep(ep: dict[tuple[int, int], float],
             xmins: dict[tuple[int, int], float],
             rng: np.random.Generator) -> dict[tuple[int, int], float]:
    """One noised copy of an EP table.

    ``ep_noised = max(0, ep + ep * (92 - xmins) / 134 * N(0, 1))``, one
    independent draw per player-gameweek. No cross-gameweek correlation: spec
    §10 lists it as YAGNI until the simple version proves insufficient, and
    the honest reading is that a player's *minutes* risk really is close to
    independent week to week once the fixture is known.

    Clipped at zero because a negative EP is not a worse player, it is an
    incoherent one — the MILP would want to leave a squad slot empty, which it
    cannot do, so it would distort the whole board instead.

    Cells with no xMins entry pass through untouched: "we have no minutes
    prediction for this player" is not the same claim as "his minutes are
    certain", and inventing a scale for him would be the worse error.
    """
    out: dict[tuple[int, int], float] = {}
    for key, value in ep.items():
        xm = xmins.get(key)
        if xm is None:
            out[key] = value
            continue
        scale = (NOISE_FLOOR_XMINS - xm) / NOISE_DENOM
        out[key] = max(0.0, value + value * scale
                       * float(rng.standard_normal()))
    return out


def noised_pool(pool: pd.DataFrame, xmins: dict[tuple[int, int], float],
                rng: np.random.Generator) -> pd.DataFrame:
    """A copy of the candidate pool with every ``ep`` dict noised.

    The *pool* is noised rather than rebuilt from noised EP, and that is a
    deliberate choice rather than a shortcut: ``build_pool`` applies a top-N
    filter per position, so rebuilding it per scenario would change which
    players are even candidates from one scenario to the next, and a move
    frequency computed across scenarios with different candidate sets is
    counting incomparable things. Fixing the board and varying only the values
    on it is what makes the frequencies mean something.
    """
    out = pool.copy()
    out["ep"] = [
        {gw: v for gw, v in noise_ep(
            {(int(code), int(gw)): float(v) for gw, v in cell.items()},
            xmins, rng).items()}
        for code, cell in zip(pool["code"], pool["ep"])
    ]
    # The comprehension above rekeys to (code, gw) tuples; rebuild the plain
    # {gw: ep} shape solve_plan expects.
    out["ep"] = [{gw: cell[(int(code), int(gw))] if (int(code), int(gw))
                  in cell else v
                  for gw, v in original.items()}
                 for code, cell, original in
                 zip(pool["code"], out["ep"], pool["ep"])]
    return out
```

That double pass is awkward. Replace the two `out["ep"] = ...` blocks with the
single straightforward loop:

```python
    out = pool.copy()
    cells = []
    for code, cell in zip(pool["code"], pool["ep"]):
        keyed = {(int(code), int(gw)): float(v) for gw, v in cell.items()}
        noised = noise_ep(keyed, xmins, rng)
        cells.append({gw: noised[(int(code), int(gw))] for gw in cell})
    out["ep"] = cells
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scenarios.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/scenarios.py tests/test_scenarios.py
git commit -m "feat: minutes-scaled EP noise for scenario re-solving

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 4: `scenarios.py` — `run_scenarios`

N sequential solves on N noised copies of the same board. A scenario that fails
to solve is dropped and counted — spec §3 is explicit that 39/40 is a report
line, not an error, and the reason is real: a noised board can hand the solver
a degenerate objective, and losing one draw out of forty changes a frequency by
2.5 points.

**Files:**
- Modify: `src/gaffer/optimize/scenarios.py` (append)
- Test: `tests/test_scenarios.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scenarios.py`:

```python
# --- run_scenarios ---------------------------------------------------------

from gaffer.optimize.milp import SolveInput
from gaffer.optimize.scenarios import ScenarioRun, run_scenarios

SOLVE_KW = dict(decay=0.85, bench_weight=0.10, vice_weight=0.1,
                ft_value=1.5, itb_value=0.05, hit_cost=4)


def _board() -> tuple[pd.DataFrame, SolveInput]:
    """A legal 15-player board with spares, over one gameweek."""
    rows, code = [], 200
    for pos, count, base in [("GKP", 3, 45), ("DEF", 7, 45),
                             ("MID", 7, 55), ("FWD", 4, 60)]:
        for i in range(count):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": base + i,
                         "sell": base + i, "ep": {5: 2.0 + 0.3 * i}})
            code += 1
    pool = pd.DataFrame(rows)
    state = SolveInput(owned_codes=[], bank=1000, free_transfers=15, gws=[5])
    return pool, state


def test_run_scenarios_returns_one_plan_per_scenario():
    pool, state = _board()
    run = run_scenarios(pool, state, {}, n=3, seed=1, **SOLVE_KW)
    assert isinstance(run, ScenarioRun)
    assert len(run.plans) == 3
    assert run.attempted == 3 and run.completed == 3


def test_run_scenarios_with_n_zero_solves_nothing():
    """The degradation rail's load-bearing case."""
    pool, state = _board()
    run = run_scenarios(pool, state, {}, n=0, seed=1, **SOLVE_KW)
    assert run.plans == [] and run.attempted == 0 and run.completed == 0


def test_run_scenarios_is_reproducible_under_a_seed():
    pool, state = _board()
    xm = {(int(c), 5): 20.0 for c in pool["code"]}
    a = run_scenarios(pool, state, xm, n=3, seed=99, **SOLVE_KW)
    b = run_scenarios(pool, state, xm, n=3, seed=99, **SOLVE_KW)
    assert [p.gw_plans[0].squad for p in a.plans] == \
           [p.gw_plans[0].squad for p in b.plans]


def test_run_scenarios_with_a_different_seed_explores_differently():
    pool, state = _board()
    xm = {(int(c), 5): 0.0 for c in pool["code"]}
    a = run_scenarios(pool, state, xm, n=4, seed=1, **SOLVE_KW)
    b = run_scenarios(pool, state, xm, n=4, seed=2, **SOLVE_KW)
    assert [p.gw_plans[0].captain for p in a.plans] != \
           [p.gw_plans[0].captain for p in b.plans]


def test_run_scenarios_records_the_seed_it_used():
    """The report prints it, and reproducing an old piece of advice is the
    only way to argue with it."""
    pool, state = _board()
    assert run_scenarios(pool, state, {}, n=2, seed=77, **SOLVE_KW).seed == 77


def test_run_scenarios_drops_a_failing_solve_and_counts_it(monkeypatch):
    """39/40 is a report line, not an error."""
    import gaffer.optimize.scenarios as scen

    pool, state = _board()
    calls = {"n": 0}
    real = scen.solve_plan

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("MILP not optimal: Infeasible")
        return real(*a, **kw)

    monkeypatch.setattr(scen, "solve_plan", flaky)
    run = run_scenarios(pool, state, {}, n=3, seed=1, **SOLVE_KW)
    assert run.attempted == 3 and run.completed == 2
    assert len(run.plans) == 2
    assert run.failures == 1


def test_run_scenarios_zero_noise_reproduces_the_deterministic_optimum():
    """With every player pinned at 92 xMins the noise is identically zero, so
    every scenario has to agree with the plain solve. This is the sanity
    check that the noise is the only thing varying."""
    from gaffer.optimize.milp import solve_plan

    pool, state = _board()
    xm = {(int(c), 5): 92.0 for c in pool["code"]}
    run = run_scenarios(pool, state, xm, n=2, seed=5, **SOLVE_KW)
    raw = solve_plan(pool, state, **SOLVE_KW)
    for plan in run.plans:
        assert plan.gw_plans[0].squad == raw.gw_plans[0].squad
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scenarios.py -k run_scenarios -v`
Expected: FAIL — `ImportError: cannot import name 'ScenarioRun' from 'gaffer.optimize.scenarios'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/optimize/scenarios.py` (and add
`from gaffer.optimize.milp import Plan, SolveInput, solve_plan` to the imports
at the top — imported at module scope, not lazily, because the monkeypatch in
the failure test replaces the module attribute):

```python
@dataclass
class ScenarioRun:
    """The outcome of a scenario sweep.

    ``attempted`` and ``completed`` differ when a noised board defeated the
    solver. That difference is printed, not raised: the frequencies are still
    meaningful over the scenarios that did finish, and refusing to give advice
    because 1 solve in 40 went sideways would be the worse failure.
    """
    plans: list[Plan]
    attempted: int
    completed: int
    failures: int
    seed: int


def run_scenarios(pool: pd.DataFrame, state: SolveInput,
                  xmins: dict[tuple[int, int], float], *, n: int, seed: int,
                  **solve_cfg) -> ScenarioRun:
    """``n`` solves of the same board under ``n`` independent EP draws.

    ``solve_cfg`` is the ordinary :func:`~gaffer.optimize.milp.solve_plan`
    keyword bundle — the same ``opt_kw`` the deterministic solve uses, so a
    scenario differs from the raw optimum in the EP values and in nothing
    else.

    Sequential on purpose. At ~7s a solve, 40 scenarios is under five minutes,
    which spec §3 budgets for; a process pool would buy maybe 4x for the cost
    of pickling a PuLP problem per worker and a class of bugs that only ever
    appear on someone else's machine.

    ``n = 0`` returns an empty run without touching the solver at all — that is
    the degradation rail, and it has to be free.
    """
    if n <= 0:
        return ScenarioRun(plans=[], attempted=0, completed=0, failures=0,
                           seed=seed)
    rng = np.random.default_rng(seed)
    plans: list[Plan] = []
    failures = 0
    for _ in range(n):
        board = noised_pool(pool, xmins, rng)
        try:
            plans.append(solve_plan(board, state, **solve_cfg))
        except Exception as exc:  # noqa: BLE001 — one bad draw is not fatal
            failures += 1
            print(f"scenario solve failed, dropping it: {exc}")
    return ScenarioRun(plans=plans, attempted=n, completed=len(plans),
                       failures=failures, seed=seed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scenarios.py -v`
Expected: PASS (23 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/scenarios.py tests/test_scenarios.py
git commit -m "feat: run_scenarios — N noised solves with a logged seed

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 5: `scenarios.py` — `move_frequencies`

Spec §3's third bullet. Per candidate move, the share of scenarios containing
it. Move kinds: `buy`, `sell`, `hit`, `chip`, `captain`, `no_transfer`.

The keying matters more than the counting. A buy is keyed on
`(kind="buy", code, gw)` and counted once per scenario whether it arrived alone
or as half of a double move, because "how often does the optimizer want this
player" is the question, and a plan-shape-sensitive key would answer a
different one. Only the **first horizon week** produces buy/sell rows: weeks 2
and 3 of the horizon are re-planned from scratch next week and their moves are
not decisions anyone is taking now.

**Files:**
- Modify: `src/gaffer/optimize/scenarios.py` (append)
- Test: `tests/test_scenarios.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scenarios.py`:

```python
# --- move_frequencies ------------------------------------------------------

from gaffer.optimize.milp import GwPlan, Plan
from gaffer.optimize.scenarios import FREQ_COLUMNS, move_frequencies


def _plan(buys, sells, captain, hits=0, gw=5, chip=None) -> Plan:
    gp = GwPlan(gw=gw, squad=[], xi=[], xi_rows=[], bench=[], captain=captain,
                vice=0, buys=list(buys), sells=list(sells), hits=hits,
                expected_pts=0.0)
    plan = Plan(objective=0.0, gw_plans=[gp])
    if chip is not None:
        plan.chip, plan.chip_gw = chip, gw     # set by the chip sweep
    return plan


def test_move_frequencies_has_the_documented_columns():
    out = move_frequencies([_plan([1], [2], 9)])
    assert list(out.columns) == list(FREQ_COLUMNS)


def test_a_buy_in_every_scenario_has_frequency_one():
    out = move_frequencies([_plan([1], [2], 9), _plan([1], [3], 9)])
    row = out[(out["kind"] == "buy") & (out["code"] == 1)].iloc[0]
    assert row["frequency"] == 1.0 and row["count"] == 2


def test_a_buy_in_half_the_scenarios_has_frequency_one_half():
    out = move_frequencies([_plan([1], [2], 9), _plan([4], [2], 9)])
    row = out[(out["kind"] == "buy") & (out["code"] == 1)].iloc[0]
    assert row["frequency"] == 0.5


def test_a_buy_inside_a_double_move_counts_the_same_as_one_alone():
    """The key is the player, not the plan shape: 'how often does the model
    want this player' is the question the threshold is answering."""
    out = move_frequencies([_plan([1], [2], 9), _plan([1, 7], [2, 8], 9)])
    row = out[(out["kind"] == "buy") & (out["code"] == 1)].iloc[0]
    assert row["frequency"] == 1.0


def test_a_repeated_buy_within_one_scenario_counts_once():
    out = move_frequencies([_plan([1, 1], [2], 9)])
    assert int(out[(out["kind"] == "buy") & (out["code"] == 1)]
               .iloc[0]["count"]) == 1


def test_no_transfer_is_its_own_counted_move():
    """'Roll the FT' has to compete on the same scale as the transfers, or
    holding could never win."""
    out = move_frequencies([_plan([], [], 9), _plan([1], [2], 9)])
    row = out[out["kind"] == "no_transfer"].iloc[0]
    assert row["frequency"] == 0.5


def test_captain_frequencies_are_a_distribution_over_scenarios():
    out = move_frequencies([_plan([], [], 9), _plan([], [], 9),
                            _plan([], [], 4)])
    caps = out[out["kind"] == "captain"].set_index("code")["frequency"]
    assert abs(caps[9] - 2 / 3) < 1e-12
    assert abs(caps[4] - 1 / 3) < 1e-12


def test_hits_are_counted_per_horizon_week():
    out = move_frequencies([_plan([1], [2], 9, hits=1),
                            _plan([1], [2], 9, hits=0)])
    row = out[out["kind"] == "hit"].iloc[0]
    assert row["frequency"] == 0.5 and row["gw"] == 5


def test_a_week_with_no_hit_in_any_scenario_produces_no_hit_row():
    out = move_frequencies([_plan([1], [2], 9), _plan([1], [2], 9)])
    assert out[out["kind"] == "hit"].empty


def test_only_the_first_horizon_week_produces_buy_and_sell_rows():
    """Weeks two and three are re-planned from scratch next week; counting
    their moves would gate a decision nobody is taking."""
    gp1 = GwPlan(gw=5, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[1], sells=[2], hits=0, expected_pts=0.0)
    gp2 = GwPlan(gw=6, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[5], sells=[6], hits=0, expected_pts=0.0)
    out = move_frequencies([Plan(objective=0.0, gw_plans=[gp1, gp2])])
    assert set(out[out["kind"] == "buy"]["code"]) == {1}
    assert set(out[out["kind"] == "sell"]["code"]) == {2}


def test_hits_in_later_horizon_weeks_are_still_counted():
    """A hit planned for week three is information about this week's decision
    — it says the current squad is about to need surgery."""
    gp1 = GwPlan(gw=5, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[], sells=[], hits=0, expected_pts=0.0)
    gp2 = GwPlan(gw=6, squad=[], xi=[], xi_rows=[], bench=[], captain=9,
                 vice=0, buys=[5], sells=[6], hits=1, expected_pts=0.0)
    out = move_frequencies([Plan(objective=0.0, gw_plans=[gp1, gp2])])
    assert list(out[out["kind"] == "hit"]["gw"]) == [6]


def test_chip_frequencies_are_keyed_by_chip_and_week():
    out = move_frequencies([_plan([], [], 9, chip="bboost"),
                            _plan([], [], 9, chip="bboost"),
                            _plan([], [], 9)])
    row = out[out["kind"] == "chip"].iloc[0]
    assert row["label"] == "bboost" and abs(row["frequency"] - 2 / 3) < 1e-12


def test_move_frequencies_of_no_scenarios_is_an_empty_typed_frame():
    out = move_frequencies([])
    assert out.empty and list(out.columns) == list(FREQ_COLUMNS)


def test_move_frequencies_is_sorted_by_descending_frequency():
    out = move_frequencies([_plan([1, 2], [3], 9), _plan([1], [3], 9)])
    buys = out[out["kind"] == "buy"]["frequency"].tolist()
    assert buys == sorted(buys, reverse=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scenarios.py -k frequenc -v`
Expected: FAIL — `ImportError: cannot import name 'FREQ_COLUMNS' from 'gaffer.optimize.scenarios'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/optimize/scenarios.py`:

```python
FREQ_COLUMNS = ("kind", "code", "gw", "label", "count", "frequency")
"""Move-frequency table schema.

``code`` is the player code for ``buy``/``sell``/``captain`` and ``0`` for the
kinds that are not about a player (``hit``, ``chip``, ``no_transfer``);
``label`` carries the human-readable name (the chip name, or the kind itself),
so the report and the UI never have to reconstruct one.
"""

MOVE_KINDS = ("buy", "sell", "hit", "chip", "captain", "no_transfer")


def move_frequencies(plans: list[Plan]) -> pd.DataFrame:
    """Per candidate move, the share of scenarios containing it.

    Buys and sells are read from the **first** horizon week only: weeks two
    and three are re-planned from scratch next Tuesday, so gating them would
    put a threshold on a decision nobody is taking. Hits and chips are read
    from every week, because "this squad needs a hit in three weeks" is real
    information about *this* week's transfer.

    Within one scenario a move is counted once no matter how many times it
    appears, and a buy counts the same whether it arrived alone or as half of
    a double move — the key is the player, not the plan shape.

    Chips are read off ``plan.chip`` / ``plan.chip_gw`` when the caller has
    attached them (the chip sweep does); a plan without them contributes no
    chip rows rather than an implicit "no chip", because chip *availability*
    is not a per-scenario fact.
    """
    n = len(plans)
    empty = pd.DataFrame(columns=list(FREQ_COLUMNS))
    if n == 0:
        return empty

    counts: dict[tuple[str, int, int, str], int] = {}

    def bump(kind: str, code: int, gw: int, label: str) -> None:
        counts[(kind, code, gw, label)] = counts.get(
            (kind, code, gw, label), 0) + 1

    for plan in plans:
        seen: set[tuple[str, int, int, str]] = set()

        def once(kind: str, code: int, gw: int, label: str) -> None:
            key = (kind, code, gw, label)
            if key not in seen:
                seen.add(key)
                bump(*key)

        first = plan.gw_plans[0]
        for code in first.buys:
            once("buy", int(code), int(first.gw), "buy")
        for code in first.sells:
            once("sell", int(code), int(first.gw), "sell")
        if not first.buys and not first.sells:
            once("no_transfer", 0, int(first.gw), "no_transfer")
        once("captain", int(first.captain), int(first.gw), "captain")
        for gp in plan.gw_plans:
            if gp.hits:
                once("hit", 0, int(gp.gw), "hit")
        chip = getattr(plan, "chip", None)
        if chip:
            once("chip", 0, int(getattr(plan, "chip_gw", first.gw)), str(chip))

    rows = [{"kind": kind, "code": code, "gw": gw, "label": label,
             "count": c, "frequency": c / n}
            for (kind, code, gw, label), c in counts.items()]
    out = pd.DataFrame(rows, columns=list(FREQ_COLUMNS))
    return out.sort_values(["kind", "frequency", "code"],
                           ascending=[True, False, True]).reset_index(
                               drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scenarios.py -v`
Expected: PASS (37 passed)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/scenarios.py tests/test_scenarios.py
git commit -m "feat: move_frequencies over a scenario sweep

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 6: `milp.py` — `FixedMoves` and the `fixed_moves` argument

Spec §4's consistency rail needs the MILP to accept "these buys and these sells
happen in week one, now find the best plan around them". The MILP already does
exactly this shape of thing for `locked_in` and `force_in_gw`; this is the same
mechanism, made explicit and given a sell side and a "make no transfer at all"
setting.

After this task the signature is:

```python
def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int,
               fixed_moves: FixedMoves | None = None) -> Plan:
```

`fixed_moves=None` must leave the problem untouched — Task 2's rail 2 is the
proof.

**Files:**
- Modify: `src/gaffer/optimize/milp.py:74-77` (after `Plan`), `:80-82`
  (signature), `:164-169` (constraint block)
- Test: `tests/test_milp.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_milp.py`:

```python
# --- v4c: fixed moves ------------------------------------------------------

from gaffer.optimize.milp import FixedMoves
from tests.test_v4c_degradation import GOLDEN_KW, golden_pool


def _owned_state(pool, gws=(1, 2)):
    """A legal starting squad drawn off the golden pool, with one FT and
    enough bank to make a swap possible."""
    by_pos = {}
    for r in pool.itertuples():
        by_pos.setdefault(r.position, []).append(int(r.code))
    owned = (by_pos["GKP"][:2] + by_pos["DEF"][:5] + by_pos["MID"][:5]
             + by_pos["FWD"][:3])
    return SolveInput(owned_codes=owned, bank=200, free_transfers=1,
                      gws=list(gws))


def test_fixed_moves_none_is_the_identity():
    """The rail: the new argument at its default cannot move a single float."""
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, fixed_moves=None)
    assert round(a.objective, 9) == round(b.objective, 9)
    assert a.gw_plans[0].squad == b.gw_plans[0].squad


def test_fixed_moves_forces_the_named_buy_in_the_first_week():
    pool = golden_pool()
    state = _owned_state(pool)
    spare = [int(c) for c in pool["code"] if c not in state.owned_codes]
    target = spare[0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[target]))
    assert target in plan.gw_plans[0].buys
    assert target in plan.gw_plans[0].squad


def test_fixed_moves_forces_the_named_sell_in_the_first_week():
    pool = golden_pool()
    state = _owned_state(pool)
    target = state.owned_codes[-1]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(sells=[target]))
    assert target in plan.gw_plans[0].sells
    assert target not in plan.gw_plans[0].squad


def test_fixed_moves_can_force_a_paired_swap():
    pool = golden_pool()
    state = _owned_state(pool)
    out_code = state.owned_codes[-1]
    in_code = [int(c) for c in pool["code"]
               if c not in state.owned_codes][0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[in_code],
                                             sells=[out_code]))
    first = plan.gw_plans[0]
    assert in_code in first.buys and out_code in first.sells


def test_no_transfer_forbids_every_first_week_move():
    """The 'hold, roll the FT' branch of the policy needs this to be
    enforceable, not merely preferred."""
    pool = golden_pool()
    state = _owned_state(pool)
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(no_transfer=True))
    first = plan.gw_plans[0]
    assert first.buys == [] and first.sells == [] and first.hits == 0


def test_no_transfer_leaves_later_horizon_weeks_free():
    """Holding this week is a statement about this week only."""
    pool = golden_pool()
    state = _owned_state(pool)
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(no_transfer=True))
    assert plan.gw_plans[0].buys == []
    assert len(plan.gw_plans) == 2


def test_fixed_moves_targets_the_first_horizon_week_by_default():
    pool = golden_pool()
    state = _owned_state(pool, gws=(3, 4))
    spare = [int(c) for c in pool["code"] if c not in state.owned_codes][0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[spare]))
    assert spare in plan.gw_plans[0].buys


def test_fixed_moves_honours_an_explicit_gameweek():
    pool = golden_pool()
    state = _owned_state(pool, gws=(3, 4))
    spare = [int(c) for c in pool["code"] if c not in state.owned_codes][0]
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      fixed_moves=FixedMoves(buys=[spare], gw=4))
    assert spare in plan.gw_plans[1].buys


def test_fixed_moves_on_an_unknown_code_raises_with_a_useful_message():
    """Same discipline as locked_in: silently ignoring a forced move would
    produce a plan that quietly is not the one the policy chose."""
    pool = golden_pool()
    state = _owned_state(pool)
    with pytest.raises(GafferError) as exc:
        solve_plan(pool, state, **GOLDEN_KW,
                   fixed_moves=FixedMoves(buys=[999999]))
    assert "fixed_moves" in str(exc.value)
    assert "999999" in str(exc.value)


def test_fixed_moves_with_no_transfer_and_a_buy_raises():
    """The two settings contradict each other; resolving it silently would
    hide a policy bug."""
    pool = golden_pool()
    state = _owned_state(pool)
    with pytest.raises(GafferError) as exc:
        solve_plan(pool, state, **GOLDEN_KW,
                   fixed_moves=FixedMoves(buys=[int(pool.loc[0, "code"])],
                                          no_transfer=True))
    assert "no_transfer" in str(exc.value)
```

Ensure the file's imports include `pytest`, `GafferError`, `SolveInput` and
`solve_plan` (the existing suite already imports the last three; add
`from gaffer.errors import GafferError` and `import pytest` if absent).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_milp.py -k fixed_moves -v`
Expected: FAIL — `ImportError: cannot import name 'FixedMoves' from 'gaffer.optimize.milp'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/optimize/milp.py`, add after the `Plan` dataclass:

```python
@dataclass
class FixedMoves:
    """Transfers the caller has already decided on.

    The scenario policy (``optimize/policy.py``) picks a set of moves by how
    often they survive noise, then needs a *coherent* plan built around
    exactly those moves — a recommended buy with no recommended sell is not a
    plan anyone can execute. Rather than assembling one by hand and hoping it
    is legal, it hands the moves back to the MILP as constraints and lets the
    solver fill in the XI, the captain and the bank.

    ``gw`` defaults to the first horizon week, which is the only week the
    policy ever gates. ``no_transfer`` is the "hold and roll the FT" branch:
    it pins *this* week shut and leaves the rest of the horizon free, because
    holding this week says nothing about next week.
    """
    buys: list[int] = field(default_factory=list)
    sells: list[int] = field(default_factory=list)
    gw: int | None = None
    no_transfer: bool = False
```

Extend the signature (line 80):

```python
def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int,
               fixed_moves: FixedMoves | None = None) -> Plan:
```

and add this block immediately after the existing
`for c in state.force_in_gw: prob += tin[c][T[0]] == 1` line:

```python
    # --- forced moves from the decision policy ---------------------------
    # Deliberately after force_in_gw so the two cannot be confused: this one
    # names both sides of the trade and can also pin the week shut entirely.
    if fixed_moves is not None:
        fm_gw = fixed_moves.gw if fixed_moves.gw is not None else T[0]
        if fm_gw not in T:
            raise GafferError(
                f"fixed_moves: gameweek {fm_gw} is not in the horizon {T}")
        if fixed_moves.no_transfer and (fixed_moves.buys
                                        or fixed_moves.sells):
            raise GafferError(
                "fixed_moves: no_transfer cannot be combined with buys or "
                "sells — the policy must choose one or the other")
        missing = [c for c in list(fixed_moves.buys) + list(fixed_moves.sells)
                   if c not in code_set]
        if missing:
            raise GafferError(
                f"fixed_moves: player code {missing[0]} is not in the "
                "candidate pool (it may also be banned)")
        for c in fixed_moves.buys:
            prob += tin[c][fm_gw] == 1
        for c in fixed_moves.sells:
            prob += tout[c][fm_gw] == 1
        if fixed_moves.no_transfer:
            prob += pulp.lpSum(tin[c][fm_gw] for c in codes) == 0
```

`code_set` is whatever local the existing `locked_in` validation uses to check
membership (the block at lines 92-98 that raises
`"player code ... is not in the candidate pool"`). If that check inlines
`pool["code"]` rather than binding a set, add `code_set = set(codes)` next to
`codes = pool["code"].tolist()` and use it in both places.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_milp.py tests/test_v4c_degradation.py -v`
Expected: PASS (whole files)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/milp.py tests/test_milp.py
git commit -m "feat: fixed_moves constraints on solve_plan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 7: `policy.py` — `decide()`

Spec §4's thresholds. Reversible moves (plain transfers) need 60% of scenarios;
irreversible ones (hits, chips, wildcard) need 75%, because a transfer you
regret costs you a transfer and a hit you regret costs you four points you
cannot get back. The captain is always recommended — there is no "hold" option
for the armband — so it is a plurality winner rather than a threshold.

When nothing clears its bar the advice is "hold, roll the FT", and the
nearest-miss moves are listed with their frequencies so the reader can see how
close it was rather than being told nothing happened.

**Files:**
- Create: `src/gaffer/optimize/policy.py`
- Test: `tests/test_policy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_policy.py`:

```python
import pandas as pd

from gaffer.optimize.milp import GwPlan, Plan
from gaffer.optimize.policy import (NEAR_MISS_BAND, Decision, Thresholds,
                                    decide)


def _freq(rows) -> pd.DataFrame:
    """Rows as (kind, code, gw, label, frequency); count is derived."""
    return pd.DataFrame(
        [{"kind": k, "code": c, "gw": g, "label": lab,
          "count": int(round(f * 100)), "frequency": f}
         for k, c, g, lab, f in rows],
        columns=["kind", "code", "gw", "label", "count", "frequency"])


def _raw(buys=(), sells=(), captain=9, hits=0, gw=5) -> Plan:
    gp = GwPlan(gw=gw, squad=[], xi=[], xi_rows=[], bench=[], captain=captain,
                vice=0, buys=list(buys), sells=list(sells), hits=hits,
                expected_pts=0.0)
    return Plan(objective=0.0, gw_plans=[gp])


TH = Thresholds(transfer=0.60, irreversible=0.75)


def test_thresholds_carry_the_spec_defaults():
    assert Thresholds().transfer == 0.60
    assert Thresholds().irreversible == 0.75


def test_a_transfer_above_sixty_percent_is_recommended():
    freq = _freq([("buy", 1, 5, "buy", 0.80), ("sell", 2, 5, "sell", 0.75),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [1] and d.sells == [2]
    assert d.hold is False


def test_a_transfer_exactly_at_the_bar_is_recommended():
    """>= 60%, not > 60%: the bar is a bar, not a strict inequality."""
    freq = _freq([("buy", 1, 5, "buy", 0.60), ("sell", 2, 5, "sell", 0.60),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1], sells=[2]), TH).buys == [1]


def test_a_transfer_below_the_bar_is_held():
    freq = _freq([("buy", 1, 5, "buy", 0.55), ("sell", 2, 5, "sell", 0.55),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [] and d.sells == [] and d.hold is True


def test_a_held_decision_lists_its_near_misses_with_frequencies():
    freq = _freq([("buy", 1, 5, "buy", 0.55), ("sell", 2, 5, "sell", 0.50),
                  ("buy", 7, 5, "buy", 0.05),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    labels = {(m["kind"], m["code"]): m["frequency"] for m in d.near_misses}
    assert labels[("buy", 1)] == 0.55
    # 5% is not a near miss, it is a non-starter.
    assert ("buy", 7) not in labels


def test_the_near_miss_band_is_the_documented_width():
    assert NEAR_MISS_BAND == 0.20


def test_a_hit_needs_the_irreversible_bar():
    below = _freq([("hit", 0, 5, "hit", 0.70),
                   ("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(below, _raw(buys=[1], sells=[2], hits=1), TH).hit is False

    above = _freq([("hit", 0, 5, "hit", 0.80),
                   ("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(above, _raw(buys=[1], sells=[2], hits=1), TH).hit is True


def test_a_chip_needs_the_irreversible_bar():
    below = _freq([("chip", 0, 5, "bboost", 0.70),
                   ("captain", 9, 5, "captain", 1.0)])
    assert decide(below, _raw(), TH).chip is None

    above = _freq([("chip", 0, 5, "bboost", 0.90),
                   ("captain", 9, 5, "captain", 1.0)])
    d = decide(above, _raw(), TH)
    assert d.chip == "bboost" and d.chip_gw == 5


def test_the_wildcard_is_irreversible_like_every_other_chip():
    freq = _freq([("chip", 0, 5, "wildcard", 0.70),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(), TH).chip is None


def test_the_captain_is_the_plurality_winner_even_below_every_bar():
    """There is no 'hold' for the armband: someone wears it."""
    freq = _freq([("captain", 9, 5, "captain", 0.40),
                  ("captain", 4, 5, "captain", 0.35),
                  ("captain", 7, 5, "captain", 0.25)])
    d = decide(freq, _raw(captain=4), TH)
    assert d.captain == 9
    assert d.captain_frequency == 0.40


def test_a_captain_tie_breaks_towards_the_raw_optimum():
    """A coin flip that always lands the same way is better than one that
    lands differently every time the solver is re-run."""
    freq = _freq([("captain", 9, 5, "captain", 0.50),
                  ("captain", 4, 5, "captain", 0.50)])
    assert decide(freq, _raw(captain=4), TH).captain == 4


def test_with_no_captain_rows_the_raw_optimums_captain_survives():
    """Degradation: an empty sweep must not produce a captainless advice."""
    d = decide(_freq([]), _raw(captain=6), TH)
    assert d.captain == 6 and d.hold is True


def test_raw_optimum_agrees_when_the_gated_moves_match_it():
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1], sells=[2]), TH).raw_optimum_agrees


def test_raw_optimum_disagrees_when_it_wanted_a_different_player():
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.90),
                  ("captain", 9, 5, "captain", 1.0)])
    assert not decide(freq, _raw(buys=[7], sells=[2]), TH).raw_optimum_agrees


def test_raw_optimum_disagrees_when_the_gate_held_it_back():
    freq = _freq([("buy", 1, 5, "buy", 0.30), ("sell", 2, 5, "sell", 0.30),
                  ("captain", 9, 5, "captain", 1.0)])
    assert not decide(freq, _raw(buys=[1], sells=[2]), TH).raw_optimum_agrees


def test_a_buy_without_a_passing_sell_still_records_the_buy():
    """decide() reports what cleared the bar; making it *legal* is
    coherent_plan's job, and conflating the two would hide the gap."""
    freq = _freq([("buy", 1, 5, "buy", 0.90), ("sell", 2, 5, "sell", 0.30),
                  ("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(buys=[1], sells=[2]), TH)
    assert d.buys == [1] and d.sells == []


def test_decide_returns_the_frequency_table_it_was_given():
    """The report prints it next to the recommendation, so the decision
    carries its own evidence."""
    freq = _freq([("captain", 9, 5, "captain", 1.0)])
    d = decide(freq, _raw(), TH)
    assert isinstance(d, Decision)
    assert list(d.frequencies["kind"]) == ["captain"]


def test_buys_and_sells_come_back_in_descending_frequency():
    freq = _freq([("buy", 1, 5, "buy", 0.70), ("buy", 3, 5, "buy", 0.95),
                  ("captain", 9, 5, "captain", 1.0)])
    assert decide(freq, _raw(buys=[1, 3]), TH).buys == [3, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.optimize.policy'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/optimize/policy.py`:

```python
"""Frequencies decide.

The scenario sweep produces a distribution over plans; this module turns that
distribution into one recommendation. The rule is deliberately blunt: a move is
recommended when enough of the noised worlds wanted it, and otherwise it is
not made at all.

Two bars rather than one, because the moves are not symmetric in what they cost
when they are wrong. A transfer you regret costs you a transfer — you take it
back next week and you are one FT down. A hit you regret costs four points that
are simply gone, and a chip you regret is gone for half a season. So reversible
moves clear at 60% and irreversible ones at 75%.

The captain is the exception and gets no bar at all: somebody wears the armband
every week, so the question is never "should we captain" but "who", and the
plurality winner is the answer. Ties break towards the raw optimum, which keeps
the advice stable across re-runs instead of coin-flipping.

Nothing here solves anything — :func:`coherent_plan` does that. This module
answers "what do we want", and the MILP answers "what is the best legal plan
that does it".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from gaffer.optimize.milp import Plan

NEAR_MISS_BAND = 0.20
"""How far below its bar a move can sit and still be worth printing.

A move at 55% against a 60% bar is a genuinely close call the reader should
see. One at 5% is noise, and listing it would bury the near misses that matter
in a wall of players the model never seriously wanted.
"""


@dataclass
class Thresholds:
    """The two bars, defaulted to spec §4's numbers."""
    transfer: float = 0.60
    irreversible: float = 0.75


@dataclass
class Decision:
    """What the frequencies say to do, before it is made legal.

    ``buys`` and ``sells`` are what *cleared their bar*, which is not the same
    as what is executable — a passing buy with no passing sell is a real and
    informative state, and flattening it here would hide it from the coherence
    re-solve that has to resolve it.
    """
    buys: list[int] = field(default_factory=list)
    sells: list[int] = field(default_factory=list)
    captain: int = 0
    captain_frequency: float = 0.0
    hit: bool = False
    chip: str | None = None
    chip_gw: int | None = None
    hold: bool = False
    raw_optimum_agrees: bool = False
    near_misses: list[dict] = field(default_factory=list)
    frequencies: pd.DataFrame = field(default_factory=pd.DataFrame)


def _rows(freq: pd.DataFrame, kind: str) -> pd.DataFrame:
    if freq.empty:
        return freq
    return freq[freq["kind"] == kind]


def decide(frequencies: pd.DataFrame, raw_plan: Plan,
           thresholds: Thresholds | None = None) -> Decision:
    """Gate a scenario sweep's move frequencies into one recommendation.

    ``raw_plan`` is the deterministic, un-noised solve. It is used for exactly
    two things: breaking captain ties, and answering "did the single-solve
    optimum agree with the gated advice" — the one line the raw optimum is
    demoted to in the report.
    """
    th = thresholds or Thresholds()
    first = raw_plan.gw_plans[0]

    buy_rows = _rows(frequencies, "buy")
    sell_rows = _rows(frequencies, "sell")
    passing_buys = buy_rows[buy_rows["frequency"] >= th.transfer] \
        if not buy_rows.empty else buy_rows
    passing_sells = sell_rows[sell_rows["frequency"] >= th.transfer] \
        if not sell_rows.empty else sell_rows
    buys = [int(c) for c in passing_buys.sort_values(
        "frequency", ascending=False)["code"]] if not buy_rows.empty else []
    sells = [int(c) for c in passing_sells.sort_values(
        "frequency", ascending=False)["code"]] if not sell_rows.empty else []

    hit_rows = _rows(frequencies, "hit")
    hit = bool(not hit_rows.empty
               and (hit_rows["frequency"] >= th.irreversible).any())

    chip, chip_gw = None, None
    chip_rows = _rows(frequencies, "chip")
    if not chip_rows.empty:
        passing = chip_rows[chip_rows["frequency"] >= th.irreversible]
        if not passing.empty:
            best = passing.sort_values("frequency", ascending=False).iloc[0]
            chip, chip_gw = str(best["label"]), int(best["gw"])

    cap_rows = _rows(frequencies, "captain")
    if cap_rows.empty:
        captain, captain_frequency = int(first.captain), 0.0
    else:
        top = cap_rows["frequency"].max()
        tied = [int(c) for c in cap_rows[cap_rows["frequency"] == top]["code"]]
        # Stability beats arbitrariness: when the sweep cannot separate two
        # candidates, defer to the un-noised solve rather than to whichever
        # order the groupby happened to produce.
        captain = (int(first.captain) if int(first.captain) in tied
                   else min(tied))
        captain_frequency = float(top)

    hold = not buys and not sells and chip is None

    near_misses = []
    if not frequencies.empty:
        for r in frequencies.itertuples():
            bar = (th.irreversible if r.kind in ("hit", "chip")
                   else th.transfer)
            if r.kind == "captain":
                continue
            if bar - NEAR_MISS_BAND <= r.frequency < bar:
                near_misses.append({"kind": r.kind, "code": int(r.code),
                                    "gw": int(r.gw), "label": str(r.label),
                                    "frequency": float(r.frequency)})
        near_misses.sort(key=lambda m: -m["frequency"])

    raw_agrees = (sorted(buys) == sorted(int(c) for c in first.buys)
                  and sorted(sells) == sorted(int(c) for c in first.sells)
                  and captain == int(first.captain)
                  and hit == bool(first.hits))

    return Decision(buys=buys, sells=sells, captain=captain,
                    captain_frequency=captain_frequency, hit=hit, chip=chip,
                    chip_gw=chip_gw, hold=hold, raw_optimum_agrees=raw_agrees,
                    near_misses=near_misses, frequencies=frequencies)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_policy.py -v`
Expected: PASS (18 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/policy.py tests/test_policy.py
git commit -m "feat: threshold-gated decision policy over move frequencies

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 8: `policy.py` — the coherence re-solve

Spec §4's consistency rail. A gated buy with no gated sell is not executable,
and neither is a set of three passing buys when only one FT exists. Rather than
patching the move list until it looks legal, hand what passed to the MILP as
`FixedMoves` and let it produce the best legal plan containing them — that plan
is what the report shows.

**Files:**
- Modify: `src/gaffer/optimize/policy.py` (append)
- Test: `tests/test_policy.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_policy.py`:

```python
# --- coherence re-solve ----------------------------------------------------

from gaffer.optimize.milp import SolveInput, solve_plan
from gaffer.optimize.policy import coherent_plan
from tests.test_milp import _owned_state
from tests.test_v4c_degradation import GOLDEN_KW, golden_pool


def test_a_held_decision_re_solves_with_the_week_pinned_shut():
    pool = golden_pool()
    state = _owned_state(pool)
    d = Decision(hold=True, captain=int(pool.loc[0, "code"]))
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert plan.gw_plans[0].buys == [] and plan.gw_plans[0].sells == []


def test_a_gated_swap_appears_in_the_coherent_plan():
    pool = golden_pool()
    state = _owned_state(pool)
    out_code = state.owned_codes[-1]
    in_code = [int(c) for c in pool["code"]
               if c not in state.owned_codes][0]
    d = Decision(buys=[in_code], sells=[out_code], captain=in_code)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert in_code in plan.gw_plans[0].buys
    assert out_code in plan.gw_plans[0].sells


def test_a_buy_with_no_gated_sell_gets_a_sell_chosen_by_the_solver():
    """The consistency rail: the MILP finds the cheapest way to make room,
    rather than the policy inventing one."""
    pool = golden_pool()
    state = _owned_state(pool)
    in_code = [int(c) for c in pool["code"]
               if c not in state.owned_codes][0]
    d = Decision(buys=[in_code], sells=[], captain=in_code)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    first = plan.gw_plans[0]
    assert in_code in first.buys
    assert len(first.sells) >= 1
    assert len(first.squad) == 15


def test_the_coherent_plan_keeps_the_gated_captain():
    """The armband is decided by plurality, not by whatever the re-solve
    would have picked on its own."""
    pool = golden_pool()
    state = _owned_state(pool)
    wanted = state.owned_codes[0]
    d = Decision(captain=wanted, hold=True)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert plan.gw_plans[0].captain == wanted


def test_the_captain_override_promotes_him_into_the_xi_if_needed():
    """A captain who is not in the re-solve's XI is an illegal armband."""
    pool = golden_pool()
    state = _owned_state(pool)
    d = Decision(captain=state.owned_codes[0], hold=True)
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    first = plan.gw_plans[0]
    assert first.captain in first.xi


def test_an_infeasible_forced_set_falls_back_to_the_raw_plan():
    """A gate that cannot be satisfied must degrade to advice, not to a
    traceback in front of a deadline."""
    pool = golden_pool()
    state = _owned_state(pool)
    # Every spare player forced in at once: no bank, no FTs, not legal.
    spares = [int(c) for c in pool["code"] if c not in state.owned_codes]
    d = Decision(buys=spares, sells=[], captain=state.owned_codes[0])
    plan = coherent_plan(pool, state, d, **GOLDEN_KW)
    assert len(plan.gw_plans[0].squad) == 15


def test_coherent_plan_passes_the_solver_config_through():
    """Same knobs as the deterministic solve, or the re-solve is optimizing a
    different problem than the sweep was."""
    import inspect

    src = inspect.getsource(coherent_plan)
    assert "**solve_cfg" in src
    assert "fixed_moves=" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_policy.py -k coherent -v`
Expected: FAIL — `ImportError: cannot import name 'coherent_plan' from 'gaffer.optimize.policy'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/optimize/policy.py` (and extend the milp import at the
top to `from gaffer.optimize.milp import FixedMoves, Plan, SolveInput, solve_plan`):

```python
def coherent_plan(pool: pd.DataFrame, state: SolveInput, decision: Decision,
                  **solve_cfg) -> Plan:
    """The best legal plan that does what the frequencies decided.

    Threshold-passing moves are not a plan. Two buys can pass at 80% each in
    scenarios that never contained both; a buy can pass with no sell behind
    it; a hold can pass while a chip also does. Rather than reconciling those
    by hand, the passing moves go back to the MILP as
    :class:`~gaffer.optimize.milp.FixedMoves` and the solver does what it is
    for: finds the best legal completion.

    The captain is then overridden to the plurality winner, because the
    re-solve optimizes EP and the armband was decided on robustness. If he is
    not in the re-solved XI he is promoted into it, swapping out the lowest-EP
    XI player who shares his position — an armband on a benched player is not
    a legal team sheet.

    An infeasible forced set degrades to the unconstrained solve. Deadlines do
    not wait for a policy bug, and a slightly-less-robust plan beats no advice.
    """
    if decision.hold:
        fixed = FixedMoves(no_transfer=True)
    else:
        fixed = FixedMoves(buys=list(decision.buys),
                           sells=list(decision.sells))
    try:
        plan = solve_plan(pool, state, **solve_cfg, fixed_moves=fixed)
    except Exception as exc:  # noqa: BLE001 — see docstring
        print(f"coherence re-solve infeasible, using the raw optimum: {exc}")
        return solve_plan(pool, state, **solve_cfg)

    first = plan.gw_plans[0]
    wanted = int(decision.captain)
    if wanted and wanted in first.squad and first.captain != wanted:
        pos = dict(zip(pool["code"], pool["position"]))
        if wanted not in first.xi:
            same = [c for c in first.xi if pos.get(c) == pos.get(wanted)]
            if same:
                ep_of = {int(r.code): float(r.ep.get(first.gw, 0.0))
                         for r in pool.itertuples()}
                drop = min(same, key=lambda c: ep_of.get(c, 0.0))
                first.xi = [c for c in first.xi if c != drop] + [wanted]
                first.bench = [c for c in first.bench if c != wanted] + [drop]
        if wanted in first.xi:
            if first.vice == wanted:
                first.vice = first.captain
            first.captain = wanted
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_policy.py -v`
Expected: PASS (25 passed)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/policy.py tests/test_policy.py
git commit -m "feat: coherence re-solve for threshold-passing moves

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 9: Wire the scenario layer into `run_advise`

**This task edits a protected function. Read the "Protected source-text tests"
section at the top of this plan before starting.** Four literal assertions and
three orderings inside `run_advise` must survive, and one of them —
`"pool_ep" not in src[src.index("ep_gw1 ="):]` — makes the *placement* of the
new block load-bearing.

The block goes immediately after `plan = solve_plan(...)`, which is before
`ep_gw1 =`, and it never mentions `pool_ep`: `noised_pool` takes the `pool`
frame, whose `ep` column already carries the tilted values.

`opt_kw` keeps its current six keys because it is serialized into
`SolveState.opt` at the end of the function. The solver call sites move to a
`solve_kw` derived from it, which is where the non-serializable `ft_lambda`
will land in Task 14.

**Files:**
- Modify: `src/gaffer/advise.py:82-117` (`Advice`), `:537-548` (pool/state/solve)
- Test: `tests/test_advise.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_advise.py`:

```python
# --- v4c: the scenario layer -----------------------------------------------

def test_run_advise_runs_scenarios_after_the_deterministic_solve():
    """Source-level seam again. The raw optimum still runs first — it anchors
    the report and it is the fallback when scenarios are off."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    raw = src.index("plan = solve_plan(pool, state, **solve_kw)")
    sweep = src.index("run_scenarios(")
    gate = src.index("decide(")
    assert raw < sweep < gate


def test_run_advise_guards_the_whole_scenario_block_on_the_config():
    """n = 0 must not merely produce the same answer — it must not run."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "if cfg.scenarios_n > 0:" in src
    assert src.index("if cfg.scenarios_n > 0:") < src.index("run_scenarios(")


def test_the_scenario_block_never_mentions_pool_ep():
    """Protected: tests/test_advise.py:97 asserts pool_ep does not appear
    after 'ep_gw1 =', and the scenario layer takes the pool frame anyway —
    build_pool has already folded the tilted values into it."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    block = src[src.index("if cfg.scenarios_n > 0:"):src.index("ep_gw1 =")]
    assert "pool_ep" not in block
    assert "noised_pool" in block or "run_scenarios(pool" in block


def test_run_advise_still_pins_every_protected_ordering():
    """Belt and braces: this cycle edits run_advise three times, so re-assert
    all four protected literals in one place that fails loudly."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "ep_matrix(apply_calibration(assemble_ep(" in src
    assert src.index("fetch_rival_entries(") < src.index("tilt_ep(")
    assert src.index("tilt_ep(") < src.index("pool = build_pool(")
    assert "build_pool(players, pool_ep," in src
    assert "ep_named = ep.merge(" in src
    assert 'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]
    assert '_named(first.xi, name_of, pos_of, ep_by, gw)' in src
    assert (src.index("odds_frame(raw_odds, teams, events)")
            < src.index("tg_future = build_team_future("))
    assert (src.index("tg_future = build_team_future(")
            < src.index("merge_team_odds(tg_future, odds_df)"))


def test_advice_carries_the_scenario_fields_with_safe_defaults():
    from gaffer.advise import Advice
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(Advice)}
    for name in ("move_frequencies", "raw_optimum_agrees", "scenarios"):
        assert name in fields
        assert (fields[name].default is not dataclasses.MISSING
                or fields[name].default_factory is not dataclasses.MISSING)


def test_solve_state_opt_stays_json_serializable():
    """SolveState.opt is written to disk and read by the What-If page; a
    callable in there would break the round trip."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "opt_kw = dict(" in src
    assert "solve_kw = dict(opt_kw" in src
    # The lambda lookup rides on solve_kw, never on the serialized opt_kw.
    assert "ft_lambda" not in src[src.index("opt_kw = dict("):
                                  src.index("solve_kw = dict(opt_kw")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_advise.py -k scenario -v`
Expected: FAIL — `ValueError: substring not found` raised by
`src.index("plan = solve_plan(pool, state, **solve_kw)")`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/advise.py`, add three defaulted fields to `Advice` (after
`data_warning`):

```python
    # --- v4c decision layer ------------------------------------------------
    # All three default to the pre-v4c shape, so an Advice built without a
    # scenario sweep is exactly the object it always was.
    move_frequencies: list[dict] = field(default_factory=list)
    raw_optimum_agrees: bool | None = None
    scenarios: dict | None = None
```

Replace the `opt_kw` / `solve_plan` lines (currently at `:545-548`) with:

```python
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
    # opt_kw is serialized into SolveState.opt at the end of this function, so
    # it stays plain JSON. solve_kw is the same bundle plus anything that is
    # only meaningful in-process.
    solve_kw = dict(opt_kw)
    plan = solve_plan(pool, state, **solve_kw)
    first = plan.gw_plans[0]

    # --- scenario re-solving and the decision policy ----------------------
    # The raw optimum above still runs, and still anchors the report. What
    # follows only *gates* it: N noised re-solves of the same board, and a
    # recommendation assembled from the moves that survived. With
    # [scenarios] n = 0 none of this executes and `plan` is the advice, which
    # is exactly the pre-v4c behaviour.
    move_freqs: list[dict] = []
    raw_agrees: bool | None = None
    scenario_report: dict | None = None
    if cfg.scenarios_n > 0:
        xmins = xmins_by_player_gw(comp)
        run = run_scenarios(pool, state, xmins, n=cfg.scenarios_n,
                            seed=cfg.scenarios_seed, **solve_kw)
        if run.completed:
            freqs = move_frequencies(run.plans)
            decision = decide(
                freqs, plan,
                Thresholds(transfer=cfg.transfer_threshold,
                           irreversible=cfg.irreversible_threshold))
            plan = coherent_plan(pool, state, decision, **solve_kw)
            first = plan.gw_plans[0]
            move_freqs = freqs.to_dict("records")
            raw_agrees = decision.raw_optimum_agrees
            scenario_report = {
                "n": run.attempted, "completed": run.completed,
                "failures": run.failures, "seed": run.seed,
                "hold": decision.hold,
                "captain_frequency": decision.captain_frequency,
                "near_misses": decision.near_misses,
            }
```

Add the imports at the top of `advise.py`:

```python
from gaffer.optimize.policy import Thresholds, coherent_plan, decide
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)
```

Finally, pass the three new values into the `Advice(...)` construction near the
end of the function:

```python
        move_frequencies=move_freqs,
        raw_optimum_agrees=raw_agrees,
        scenarios=scenario_report,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_advise.py -v`
Expected: PASS (whole file, including the four pre-existing protected tests)

Run: `uv run pytest tests/test_assemble.py tests/test_odds.py -v`
Expected: PASS — the other two protected suites

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/advise.py tests/test_advise.py
git commit -m "feat: gate advice on scenario move frequencies when n > 0

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 10: Report and CLI — frequencies in, raw optimum demoted

Spec §4's last bullet. The CLI advice leads with the gated plan and a "% of
sims" figure per move; the raw optimum becomes one line. Every addition is
conditional on `advice.scenarios` being present, because Task 2's rail asserts
the `n = 0` output character for character.

The buy/sell dicts also gain a `frequency` key here, which is what the web UI
reads in Task 11.

**Files:**
- Modify: `src/gaffer/advise.py` (attach `frequency` to the buy/sell dicts)
- Modify: `src/gaffer/cli.py:15-56` (`advise`)
- Modify: `src/gaffer/report/templates/report.html.j2`
- Test: `tests/test_v4c_degradation.py` (append), `tests/test_report.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_v4c_degradation.py`:

```python
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
```

Append to `tests/test_report.py`:

```python
def test_the_report_template_has_a_frequency_column_guarded_by_scenarios():
    """Guarded, not unconditional: with n = 0 the report is the old one."""
    from pathlib import Path

    src = Path("src/gaffer/report/templates/report.html.j2").read_text()
    assert "% of sims" in src
    assert "advice.scenarios" in src
    assert src.index("advice.scenarios") < src.index("% of sims")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_v4c_degradation.py -k frequencies_when -v`
Expected: FAIL — `AssertionError: assert 'BUY  Bruno Fernandes (6.4 xPts) [85% of sims]' in ...`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/advise.py`, where the buy dicts get their `tag` (around line
616), attach the frequency from the table built in Task 9. Insert directly
after the tagging loop:

```python
    # Frequencies ride on the move dicts as well as on the standalone table:
    # the CLI and the UI both render per-move, and re-joining a DataFrame in
    # a Jinja template is not a thing anyone should have to do.
    freq_of = {(str(r["kind"]), int(r["code"])): float(r["frequency"])
               for r in move_freqs}
    for b in buys:
        if ("buy", b["code"]) in freq_of:
            b["frequency"] = freq_of[("buy", b["code"])]
    for s in sells:
        if ("sell", s["code"]) in freq_of:
            s["frequency"] = freq_of[("sell", s["code"])]
```

(Use whatever the local names for the buy/sell lists are at that point in the
function; they are the same lists passed to `Advice(buys=..., sells=...)`.)

In `src/gaffer/cli.py`, replace the printing block inside `advise` — from the
`for b in advice.buys:` loop down to the `Expected XI points` line — with:

```python
    def _pct(move: dict) -> str:
        """' [85% of sims]' when the scenario sweep ran, '' otherwise.

        Conditional because the n = 0 output is a pinned regression rail:
        tests/test_v4c_degradation.py compares it character for character.
        """
        f = move.get("frequency")
        return "" if f is None else f" [{round(f * 100)}% of sims]"

    for b in advice.buys:
        typer.echo(f"BUY  {b['name']} ({b['ep']} xPts){_pct(b)}")
    for s in advice.sells:
        typer.echo(f"SELL {s['name']} ({s['ep']} xPts){_pct(s)}")
    if not advice.buys:
        typer.echo("No transfers — bank the FT.")
    if advice.hits:
        typer.echo(f"Hits: -{advice.hits * 4}")
    cap_pct = ""
    if advice.scenarios and advice.scenarios.get("captain_frequency"):
        cap_pct = (f" [{round(advice.scenarios['captain_frequency'] * 100)}"
                   "% of sims]")
    typer.echo(f"Captain: {advice.captain['name']} | "
               f"Vice: {advice.vice['name']}{cap_pct}")
    if advice.scenarios:
        s = advice.scenarios
        typer.echo(f"Scenarios: {s['completed']}/{s['n']} solved, "
                   f"seed {s['seed']}")
        agreed = "agreed" if advice.raw_optimum_agrees else "differed"
        typer.echo(f"The single-solve optimum {agreed}.")
        for miss in s.get("near_misses", [])[:3]:
            typer.echo(f"Nearest miss: {miss['label']} {miss['code']} at "
                       f"{round(miss['frequency'] * 100)}%")
    typer.echo(f"Expected XI points: {advice.expected_pts}")
```

In `src/gaffer/report/templates/report.html.j2`, find the transfers table and
add a guarded column. Inside the table's header row:

```jinja
          {% if advice.scenarios %}<th>% of sims</th>{% endif %}
```

and inside each buy/sell row:

```jinja
          {% if advice.scenarios %}
          <td>{{ (row.frequency * 100) | round | int if row.frequency is not none else '—' }}%</td>
          {% endif %}
```

Add a scenario banner above the table, also guarded:

```jinja
      {% if advice.scenarios %}
      <p class="muted">
        {{ advice.scenarios.completed }}/{{ advice.scenarios.n }} scenarios
        solved (seed {{ advice.scenarios.seed }}) — the single-solve optimum
        {{ 'agreed' if advice.raw_optimum_agrees else 'differed' }}.
      </p>
      {% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_v4c_degradation.py tests/test_report.py -v`
Expected: PASS (both files)

Run: `uv run pytest`
Expected: PASS — in particular the three protected suites, which this task's
`advise.py` edit sits near.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/advise.py src/gaffer/cli.py src/gaffer/report/templates/report.html.j2 tests/test_v4c_degradation.py tests/test_report.py
git commit -m "feat: render move frequencies and demote the raw optimum

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 11: The web frequency column

Spec §4: "Web: frequency column in the advice table, and the API schema gains
the fields." The API side needs no schema change — `AdviceLatest.advice` is
`dict[str, Any]`, so the new keys flow through untouched — but that is worth a
test rather than an assumption. The frontend needs types and a column.

The column is conditional on the data being there, same as everywhere else: an
advice built with `n = 0` renders the table it always did.

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/ThisWeek.tsx:83-113`
- Test: `frontend/src/pages/ThisWeek.test.tsx` (append)
- Test: `tests/test_web_advice.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/ThisWeek.test.tsx` (match the file's existing
import and render harness — reuse whatever fixture builder and mock it already
has for the advice payload; the snippets below assume a `renderThisWeek(advice)`
style helper, so adapt the two calls to the file's actual convention):

```tsx
  it('shows a % of sims column when the scenario sweep ran', () => {
    const advice = {
      ...BASE_ADVICE,
      buys: [{ code: 1, name: 'Bruno Fernandes', position: 'MID', ep: 6.4, frequency: 0.85 }],
      sells: [{ code: 2, name: 'Cole Palmer', position: 'MID', ep: 4.1, frequency: 0.9 }],
      scenarios: { n: 40, completed: 39, failures: 1, seed: 20260825, hold: false, captain_frequency: 0.72, near_misses: [] },
      raw_optimum_agrees: true,
    }
    renderThisWeek(advice)
    expect(screen.getByText('% of sims')).toBeInTheDocument()
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
  })

  it('omits the column entirely when scenarios did not run', () => {
    renderThisWeek(BASE_ADVICE)
    expect(screen.queryByText('% of sims')).toBeNull()
  })

  it('renders a dash for a move with no frequency', () => {
    const advice = {
      ...BASE_ADVICE,
      buys: [{ code: 1, name: 'Bruno Fernandes', position: 'MID', ep: 6.4 }],
      sells: [],
      scenarios: { n: 40, completed: 40, failures: 0, seed: 1, hold: false, captain_frequency: 0.5, near_misses: [] },
      raw_optimum_agrees: false,
    }
    renderThisWeek(advice)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('reports whether the single-solve optimum agreed', () => {
    const advice = {
      ...BASE_ADVICE,
      scenarios: { n: 40, completed: 39, failures: 1, seed: 1, hold: false, captain_frequency: 0.5, near_misses: [] },
      raw_optimum_agrees: false,
    }
    renderThisWeek(advice)
    expect(screen.getByText(/39\/40 scenarios/)).toBeInTheDocument()
    expect(screen.getByText(/differed/)).toBeInTheDocument()
  })
```

Append to `tests/test_web_advice.py`:

```python
def test_the_advice_endpoint_passes_scenario_fields_through_untouched():
    """AdviceLatest.advice is dict[str, Any] by design, so the v4c fields need
    no schema change — but 'by design' should be a test, not a belief."""
    from gaffer.web.schemas import AdviceLatest

    payload = {
        "gw": 7, "mode": "weekly", "deadline": "2026-10-03T10:00:00Z",
        "advice": {"gw": 7, "buys": [{"code": 1, "frequency": 0.85}],
                   "move_frequencies": [{"kind": "buy", "code": 1, "gw": 7,
                                         "label": "buy", "count": 34,
                                         "frequency": 0.85}],
                   "raw_optimum_agrees": True,
                   "scenarios": {"n": 40, "completed": 39, "seed": 1}},
        "staleness": {"advice_gw": 7, "current_gw": 7,
                      "generated_at": "2026-10-01T00:00:00Z",
                      "deadline": "2026-10-03T10:00:00Z",
                      "deadline_passed": False, "stale": False,
                      "reason": ""},
    }
    out = AdviceLatest(**payload)
    assert out.advice["raw_optimum_agrees"] is True
    assert out.advice["scenarios"]["completed"] == 39
    assert out.advice["buys"][0]["frequency"] == 0.85
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/pages/ThisWeek.test.tsx`
Expected: FAIL — `Unable to find an element with the text: % of sims`

Run: `uv run pytest tests/test_web_advice.py -k scenario_fields -v`
Expected: PASS already (the untyped dict passes them through) — if it fails,
`AdviceLatest.advice` has been narrowed and must be widened back.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/types.ts`, add `frequency` to the player-move type and the
three fields to the advice type (names must match the file's existing
conventions — if the player type is called `AdvicePlayer` and the advice type
`Advice`, these are the edits):

```ts
export interface AdvicePlayer {
  code: number
  name: string
  position: string
  ep: number
  tag?: string
  /** Share of noised scenarios that contained this move. Absent when the
   *  scenario sweep did not run ([scenarios] n = 0). */
  frequency?: number
}

export interface MoveFrequency {
  kind: 'buy' | 'sell' | 'hit' | 'chip' | 'captain' | 'no_transfer'
  code: number
  gw: number
  label: string
  count: number
  frequency: number
}

export interface ScenarioReport {
  n: number
  completed: number
  failures: number
  seed: number
  hold: boolean
  captain_frequency: number
  near_misses: Array<{ kind: string; code: number; gw: number; label: string; frequency: number }>
}
```

and on the `Advice` interface:

```ts
  move_frequencies?: MoveFrequency[]
  raw_optimum_agrees?: boolean | null
  scenarios?: ScenarioReport | null
```

In `frontend/src/pages/ThisWeek.tsx`, replace the Transfers card body with a
version that grows a header row and a guarded fourth column:

```tsx
      <div className="card">
        <h2>Transfers</h2>
        {advice.scenarios && (
          <p className="muted">
            {advice.scenarios.completed}/{advice.scenarios.n} scenarios solved
            (seed {advice.scenarios.seed}) — the single-solve optimum{' '}
            {advice.raw_optimum_agrees ? 'agreed' : 'differed'}.
          </p>
        )}
        {advice.buys.length === 0 && advice.sells.length === 0 && (
          <p className="muted">No transfers — bank the free transfer.</p>
        )}
        <table>
          {advice.scenarios && (
            <thead>
              <tr>
                <th />
                <th>Player</th>
                <th>xPts</th>
                <th>% of sims</th>
                <th />
              </tr>
            </thead>
          )}
          <tbody>
            {advice.buys.map((player) => (
              <tr key={`in-${player.code}`}>
                <td>IN</td>
                <td><PlayerName code={player.code} name={player.name} /></td>
                <td>{player.ep}</td>
                {advice.scenarios && (
                  <td>
                    {player.frequency === undefined
                      ? '—'
                      : `${Math.round(player.frequency * 100)}%`}
                  </td>
                )}
                <td>
                  {player.tag && (
                    <span className={`tag tag-${player.tag}`}>{player.tag}</span>
                  )}
                </td>
              </tr>
            ))}
            {advice.sells.map((player) => (
              <tr key={`out-${player.code}`}>
                <td>OUT</td>
                <td><PlayerName code={player.code} name={player.name} /></td>
                <td>{player.ep}</td>
                {advice.scenarios && (
                  <td>
                    {player.frequency === undefined
                      ? '—'
                      : `${Math.round(player.frequency * 100)}%`}
                  </td>
                )}
                <td />
              </tr>
            ))}
          </tbody>
        </table>
        {advice.hits > 0 && (
          <p className="bad">{advice.hits} hit(s): -{advice.hits * 4} pts</p>
        )}
      </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npx vitest run`
Expected: PASS (all suites, including the four new cases)

Run (from `frontend/`): `npx tsc -b`
Expected: no output, exit 0

Run (from `frontend/`): `npm run build`
Expected: a clean Vite build into `../src/gaffer/web/static`

Run: `uv run pytest tests/test_web_advice.py tests/test_web_packaging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/ThisWeek.tsx frontend/src/pages/ThisWeek.test.tsx tests/test_web_advice.py
git commit -m "feat: % of sims column on the web transfers table

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

Do **not** stage `src/gaffer/web/static/` — the build output is regenerated and
is not part of this commit.

---

## Task 12: Gate D1 — scenarios and policy, measured

Run-and-record. Nothing is implemented here; the outputs decide whether
`[scenarios] n` gets a non-zero default in `config.toml` or whether the
workstream ships off.

Spec §9's D1: *frequency-gated advice replay total ≥ raw-optimum replay total*,
plus how often the gate held moves back and the captain agreement rate.

`run_backtest` does not consult `[scenarios]` — it solves directly. So D1 is
measured by a small throwaway driver rather than by the CLI. Write it under
`scripts/`, run it, record the numbers, and delete it; it is measurement
apparatus, not product.

**Files:**
- Modify: `config.toml` (`[scenarios] n`, only if D1 passes)
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md` §12 Outcome

- [ ] **Step 1: Confirm the tree is green and the rail holds**

Run: `uv run pytest`
Expected: PASS, and `tests/test_v4c_degradation.py` among the passing files.

- [ ] **Step 2: Capture the raw-optimum baseline**

Run: `caffeinate -i uv run gaffer backtest --season 2025-26 --start-gw 5 --horizon 3`
Expected: a printed dict ending in `'total': N`. Record N as the
**raw-optimum replay total**, and record `data/live/backtest_log.parquet`'s
transfer and hit counts:

Run: `uv run python -c "import pandas as pd; d=pd.read_parquet('data/live/backtest_log.parquet'); print(d['transfers'].sum(), d['hits'].sum(), len(d))"`
Expected: three integers. Record them.

Copy the log aside so the gated run cannot overwrite it:

Run: `cp data/live/backtest_log.parquet data/live/backtest_log-d1-raw.parquet`

- [ ] **Step 3: Write the D1 driver**

Create `scripts/d1_gated_replay.py`:

```python
"""Gate D1: replay 2025-26 GW5-38 with frequency-gated advice.

Throwaway measurement apparatus. It reproduces run_backtest's loop but routes
the weekly decision through the scenario sweep and the policy, so the only
difference from the baseline replay is the gate. Delete after recording.
"""

from __future__ import annotations

import sys

import gaffer.backtest as bt
from gaffer.optimize.milp import solve_plan
from gaffer.optimize.policy import Thresholds, coherent_plan, decide
from gaffer.optimize.scenarios import move_frequencies, run_scenarios

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
SEED = 20260825
STATS = {"weeks": 0, "held": 0, "captain_agreed": 0}


def gated_solve(pool, state, **kw):
    """Drop-in for solve_plan inside the replay.

    xMins are unavailable in the replay's inner loop (the component frame is
    not threaded through), so the noise scale falls back to a flat 60-minute
    assumption for every player. That is a deliberately conservative stand-in:
    it under-noises nailed-on starters and over-noises nobody, so D1 measures
    the gate rather than the minutes model.
    """
    raw = solve_plan(pool, state, **kw)
    xm = {(int(c), int(g)): 60.0 for c in pool["code"] for g in state.gws}
    run = run_scenarios(pool, state, xm, n=N, seed=SEED + state.gws[0], **kw)
    if not run.completed:
        return raw
    d = decide(move_frequencies(run.plans), raw, Thresholds())
    STATS["weeks"] += 1
    STATS["held"] += int(d.hold)
    STATS["captain_agreed"] += int(d.captain == raw.gw_plans[0].captain)
    return coherent_plan(pool, state, d, **kw)


bt.solve_plan = gated_solve
result = bt.run_backtest(season="2025-26", start_gw=5, horizon=3)
print({"total": result["total"], **STATS})
```

- [ ] **Step 4: Run the gated replay**

Run: `caffeinate -i uv run python scripts/d1_gated_replay.py 40`
Expected: a dict with `total`, `weeks`, `held`, `captain_agreed`. This is a
long run — 34 gameweeks × 41 solves — budget several hours.

Run: `uv run python -c "import pandas as pd; d=pd.read_parquet('data/live/backtest_log.parquet'); print(d['transfers'].sum(), d['hits'].sum())"`
Expected: two integers. Record them as the **gated** counts.

- [ ] **Step 5: Evaluate gate D1**

Fill in and record in the spec's §12 Outcome:

| | raw optimum | frequency-gated |
| --- | --- | --- |
| replay total | | |
| transfers made | | |
| hits taken | | |
| weeks held (gate blocked all moves) | n/a | |
| captain agreement rate | n/a | |

**D1 passes when the gated total ≥ the raw total.** Spec §9 also expects fewer
transfers and fewer hits; if the total passes but the counts went *up*, record
that as an anomaly and check that `Thresholds()` was not accidentally
constructed with zeros.

- If D1 passes: set `n = 40` under a new `[scenarios]` table in `config.toml`.
- If D1 fails: leave `n = 0`, record the negative result in the spec, and carry
  on — spec §9's stated fallback. The code ships behind the flag.

- [ ] **Step 6: Wall-clock check**

Run: `caffeinate -i time uv run gaffer advise`
Expected: completes in **≤ ~6 minutes** with `n = 40` (spec §9). Record the
real time. If it is over, drop `n` to whatever fits and record that instead.

- [ ] **Step 7: Clean up and commit**

```bash
rm scripts/d1_gated_replay.py data/live/backtest_log-d1-raw.parquet
git add config.toml docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md
git commit -m "measure: gate D1 for scenario re-solving and the decision policy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

Never stage `data/`, `reports/` or `models/`.

---

## Task 13: `ft_value.py` — the λ(k, t) DP

Spec §5. `ft_value = 1.5` is a flat guess that says a banked transfer is worth
the same in GW6 with one in hand as in GW36 with five. It is not. The value of
holding the k-th transfer is the option value of being able to spend it later,
which falls as k rises (you already have four) and falls as the season runs out
(fewer weeks to spend it in).

The DP is small. State `(k, t)`: k free transfers held, t gameweeks remaining.
Each week: you may spend one FT on the best available transfer, whose surplus
is a draw from a calibrated distribution; then an FT arrives, capped at 5.

```
V(k, 0) = 0                                     for all k
V(0, t) = V(min(1, cap), t - 1)                 nothing to spend
V(k, t) = E_s[ max( s + V(k, t-1),  V(min(k+1, cap), t-1) ) ]    for k >= 1
```

The `V(k, t-1)` on the spend branch is not a typo: spend one (k−1), then next
week's FT arrives (k−1+1 = k). λ(k, t) = V(k, t) − V(k−1, t).

**Files:**
- Create: `src/gaffer/optimize/ft_value.py`
- Test: `tests/test_ft_value.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ft_value.py`:

```python
import pytest

from gaffer.optimize.ft_value import (FT_CAP, LambdaLookup, lambda_table,
                                      value_table)


def test_the_cap_is_five_free_transfers():
    assert FT_CAP == 5


def test_value_at_zero_weeks_remaining_is_zero_for_every_k():
    v = value_table([1.0, 2.0], weeks=3)
    for k in range(FT_CAP + 1):
        assert v[(k, 0)] == 0.0


def test_one_week_left_with_one_ft_is_the_expected_surplus():
    """Hand-checkable: one week, one transfer, no future. Spending beats not
    spending whenever the surplus is positive, so V(1,1) = E[max(s, 0)]."""
    v = value_table([0.0, 2.0], weeks=1)
    assert abs(v[(1, 1)] - 1.0) < 1e-12


def test_one_week_left_with_a_negative_surplus_draw_is_floored_at_zero():
    """Nobody is forced to make a transfer."""
    v = value_table([-3.0, 3.0], weeks=1)
    assert abs(v[(1, 1)] - 1.5) < 1e-12


def test_value_with_zero_fts_this_week_defers_to_next_week():
    v = value_table([2.0], weeks=2)
    assert abs(v[(0, 2)] - v[(1, 1)]) < 1e-12


def test_lambda_is_decreasing_in_k():
    """The core qualitative claim of spec §5: the fifth banked transfer is
    worth less than the second. If this fails the table is not shippable."""
    lam = lambda_table([0.5, 1.5, 3.0, 6.0], weeks=30)
    for t in (10, 20, 30):
        vals = [lam[(k, t)] for k in range(1, FT_CAP + 1)]
        assert vals == sorted(vals, reverse=True), (t, vals)


def test_lambda_decays_towards_zero_as_the_season_runs_out():
    lam = lambda_table([0.5, 1.5, 3.0, 6.0], weeks=30)
    assert lam[(2, 30)] > lam[(2, 10)] > lam[(2, 2)] > lam[(2, 1)]
    assert lam[(2, 1)] >= 0.0


def test_lambda_at_one_week_remaining_is_the_last_chance_value():
    """With one week left an FT is worth exactly what it can buy this week."""
    lam = lambda_table([0.0, 4.0], weeks=1)
    assert abs(lam[(1, 1)] - 2.0) < 1e-12


def test_lambda_is_never_negative():
    lam = lambda_table([-2.0, 0.0, 1.0, 8.0], weeks=20)
    assert min(lam.values()) >= 0.0


def test_the_overflow_cap_makes_the_sixth_transfer_worthless():
    """FPL loses the overflow; the table has to know that."""
    lam = lambda_table([1.0, 2.0], weeks=20)
    assert (FT_CAP + 1, 20) not in lam
    # And the fifth is worth strictly less than the fourth, because banking
    # to five risks losing the next arrival entirely.
    assert lam[(FT_CAP, 20)] < lam[(FT_CAP - 1, 20)]


def test_a_richer_surplus_distribution_raises_every_lambda():
    lean = lambda_table([0.5, 1.0], weeks=20)
    rich = lambda_table([3.0, 6.0], weeks=20)
    for k in range(1, FT_CAP + 1):
        assert rich[(k, 20)] > lean[(k, 20)]


def test_an_empty_surplus_distribution_raises():
    """A table built from nothing would silently price every FT at zero and
    turn the objective into 'always take the hit'."""
    with pytest.raises(ValueError):
        lambda_table([], weeks=10)


# --- the lookup ------------------------------------------------------------

def test_the_lookup_reads_the_table():
    lam = LambdaLookup({(1, 5): 2.0, (2, 5): 1.4})
    assert lam(1, 5) == 2.0 and lam(2, 5) == 1.4


def test_the_lookup_clamps_k_and_t_into_the_table():
    """A horizon can end past GW38 in a boundary week, and k can arrive as 0."""
    lam = LambdaLookup({(1, 1): 2.0, (1, 5): 3.0, (5, 5): 0.4})
    assert lam(1, 99) == 3.0        # clamped to the largest t present
    assert lam(9, 5) == 0.4         # clamped to the largest k present
    assert lam(0, 5) == 0.0         # holding zero transfers is worth zero


def test_the_lookup_on_an_empty_table_is_zero_everywhere():
    """The degradation path: no priors asset means no lambda pricing, and the
    caller falls back to flat ft_value."""
    assert LambdaLookup({})(2, 10) == 0.0
    assert LambdaLookup({}).empty is True


def test_the_lookup_reports_the_bank_value_of_holding_k_transfers():
    """The wildcard destroys a bank of FTs, and the sum of their lambdas is
    what it destroys."""
    lam = LambdaLookup({(1, 5): 2.0, (2, 5): 1.4, (3, 5): 1.0})
    assert abs(lam.bank_value(3, 5) - 4.4) < 1e-12
    assert lam.bank_value(0, 5) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ft_value.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.optimize.ft_value'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/optimize/ft_value.py`:

```python
"""The shadow price of a banked free transfer.

``ft_value = 1.5`` is one number standing in for a function of two variables.
A transfer banked in GW6 with one in hand is an option on thirty-two weeks of
opportunities; the same transfer banked in GW36 with five in hand is an option
on two weeks you were going to spend anyway. Pricing them identically is why
the optimizer banks when it should spend and spends when it should bank, and
why the hit rule — take a hit when the gain beats four points — is wrong in
both directions: the true bar is ``hit_cost + lambda(k, t)``, because a hit
does not only cost four points, it also does not consume the FT you were
holding.

The DP is deliberately tiny. State ``(k, t)``: k free transfers held, t
gameweeks remaining. Each week you may spend one FT on the best available
transfer — a draw from a calibrated surplus distribution — and then one FT
arrives, capped at five with the overflow lost::

    V(k, 0) = 0
    V(0, t) = V(min(1, cap), t - 1)
    V(k, t) = E_s[ max(s + V(k, t-1), V(min(k+1, cap), t-1)) ]

The ``V(k, t-1)`` on the spend branch is right: spend one and the arrival puts
you back to k. The shadow price is the difference between adjacent states,
``lambda(k, t) = V(k, t) - V(k-1, t)``.

The surplus distribution is empirical — a list of per-week best-single-transfer
gains from replay (see ``calibrate_decisions``) — so the expectation is a plain
mean over samples and there is no distributional assumption to be wrong about.
"""

from __future__ import annotations

FT_CAP = 5
"""Maximum banked free transfers. FPL's rule since 2024-25; the overflow is
lost, which is what makes the fifth transfer worth so much less than the
fourth."""


def value_table(surplus: list[float], weeks: int,
                cap: int = FT_CAP) -> dict[tuple[int, int], float]:
    """``V(k, t)`` by backward value iteration.

    ``surplus`` is an empirical sample of the weekly best-single-transfer
    gain; the expectation is the plain mean over it. Negative samples are kept
    rather than filtered — nobody is *forced* to transfer, and the ``max``
    against the not-spending branch is what encodes that, so filtering would
    double-count the option.
    """
    if not surplus:
        raise ValueError(
            "lambda DP needs a non-empty surplus distribution — an empty one "
            "prices every free transfer at zero, which turns the objective "
            "into 'always take the hit'")
    v: dict[tuple[int, int], float] = {(k, 0): 0.0 for k in range(cap + 1)}
    for t in range(1, weeks + 1):
        for k in range(cap + 1):
            if k == 0:
                v[(k, t)] = v[(min(1, cap), t - 1)]
                continue
            hold = v[(min(k + 1, cap), t - 1)]
            spend_base = v[(k, t - 1)]
            v[(k, t)] = sum(max(s + spend_base, hold)
                            for s in surplus) / len(surplus)
    return v


def lambda_table(surplus: list[float], weeks: int,
                 cap: int = FT_CAP) -> dict[tuple[int, int], float]:
    """``lambda(k, t) = V(k, t) - V(k-1, t)`` for k in 1..cap.

    Clamped at zero. The DP is monotone in k by construction, but a
    pathological surplus sample plus floating-point noise can produce a
    negative sliver, and a negative shadow price would tell the MILP to throw
    transfers away.
    """
    v = value_table(surplus, weeks, cap)
    return {(k, t): max(0.0, v[(k, t)] - v[(k - 1, t)])
            for k in range(1, cap + 1) for t in range(1, weeks + 1)}


class LambdaLookup:
    """A ``lambda(k, t)`` table with sane behaviour off its edges.

    Empty means "no calibration shipped", and every lookup is zero — the
    caller's cue to fall back to the flat ``ft_value``. Off-table ``k`` and
    ``t`` clamp to the nearest row rather than raising: a horizon that runs
    past GW38 in the last week of the season is normal, not exceptional.
    """

    def __init__(self, table: dict[tuple[int, int], float]):
        self._t = dict(table)
        self._ks = sorted({k for k, _ in self._t}) if self._t else []
        self._ts = sorted({t for _, t in self._t}) if self._t else []

    @property
    def empty(self) -> bool:
        return not self._t

    def __call__(self, k: int, t: int) -> float:
        if not self._t or k <= 0:
            return 0.0
        kk = min(max(int(k), self._ks[0]), self._ks[-1])
        tt = min(max(int(t), self._ts[0]), self._ts[-1])
        return float(self._t.get((kk, tt), 0.0))

    def bank_value(self, k: int, t: int) -> float:
        """Total value of holding ``k`` transfers — what a wildcard destroys."""
        return sum(self(j, t) for j in range(1, int(k) + 1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ft_value.py -v`
Expected: PASS (17 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/ft_value.py tests/test_ft_value.py
git commit -m "feat: lambda(k,t) DP for the free-transfer shadow price

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 14: `milp.py` — consume λ in the objective

The objective's terminal FT term is `ft_value * ftv[T[-1]]` — linear in the
count, which is exactly the flat-price assumption. λ makes it concave: holding
k transfers is worth `Σ_{j=1..k} λ(j, t)`, and each successive j is worth less.

That is representable without leaving MILP. Introduce indicator variables
`ftge[j]` meaning "the terminal FT count is at least j", linked by
`ftv[T[-1]] == Σ_j ftge[j]` with `ftge[j] <= ftge[j-1]`, and give each one the
coefficient `λ(j, t)`. Because λ is decreasing, maximization fills the cheap
indices first on its own; the ordering constraints are there so a degenerate λ
cannot produce nonsense.

After this task:

```python
def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int,
               fixed_moves: FixedMoves | None = None,
               ft_lambda: LambdaLookup | None = None) -> Plan:
```

**Files:**
- Modify: `src/gaffer/optimize/milp.py` (constants, signature, objective)
- Test: `tests/test_milp.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_milp.py`:

```python
# --- v4c: lambda-priced free transfers -------------------------------------

from gaffer.optimize.ft_value import LambdaLookup
from gaffer.optimize.milp import SEASON_LAST_GW


def test_the_season_end_constant_is_gameweek_thirty_eight():
    assert SEASON_LAST_GW == 38


def test_ft_lambda_none_is_the_identity():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, ft_lambda=None)
    assert round(a.objective, 9) == round(b.objective, 9)


def test_an_empty_lambda_lookup_falls_back_to_the_flat_ft_value():
    """No priors asset must mean 'behave as before', not 'price FTs at 0'."""
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, ft_lambda=LambdaLookup({}))
    assert round(a.objective, 9) == round(b.objective, 9)


def test_a_lambda_table_replaces_the_flat_terminal_term():
    """With lambda in play the flat ft_value must no longer appear in the
    objective — pricing an FT twice is worse than pricing it wrong."""
    import inspect

    src = inspect.getsource(solve_plan)
    assert "ft_lambda is None or ft_lambda.empty" in src
    assert "obj.append(ft_value * ftv[T[-1]])" in src


def test_a_generous_lambda_makes_the_solver_bank_rather_than_spend():
    """The behavioural claim: a high shadow price on banked transfers buys
    fewer transfers, which is the whole point."""
    pool = golden_pool()
    state = _owned_state(pool)
    greedy = solve_plan(pool, state, **GOLDEN_KW)
    stingy = solve_plan(
        pool, state, **GOLDEN_KW,
        ft_lambda=LambdaLookup({(k, t): 50.0 for k in range(1, 6)
                                for t in range(1, 39)}))
    assert len(stingy.gw_plans[0].buys) <= len(greedy.gw_plans[0].buys)


def test_a_zero_lambda_table_makes_banking_worthless():
    """The other end: FTs worth nothing means spend them."""
    pool = golden_pool()
    state = _owned_state(pool)
    plan = solve_plan(
        pool, state, **GOLDEN_KW,
        ft_lambda=LambdaLookup({(k, t): 0.0 for k in range(1, 6)
                                for t in range(1, 39)}))
    assert len(plan.gw_plans[0].squad) == 15


def test_lambda_is_looked_up_at_the_weeks_remaining_in_the_season():
    """t is 'gameweeks left after the horizon ends', not 'horizon length' —
    a GW36 horizon is nearly worthless to bank into and a GW6 one is not."""
    import inspect

    src = inspect.getsource(solve_plan)
    assert "SEASON_LAST_GW - T[-1]" in src


def test_lambda_pricing_is_concave_in_the_banked_count():
    """Each successive banked transfer must be worth less than the last, or
    the objective would prefer hoarding five to using one."""
    pool = golden_pool()
    state = _owned_state(pool)
    table = {(k, t): 4.0 / k for k in range(1, 6) for t in range(1, 39)}
    plan = solve_plan(pool, state, **GOLDEN_KW,
                      ft_lambda=LambdaLookup(table))
    assert len(plan.gw_plans[0].squad) == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_milp.py -k lambda -v`
Expected: FAIL — `ImportError: cannot import name 'SEASON_LAST_GW' from 'gaffer.optimize.milp'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/optimize/milp.py`, add next to `MAX_FREE_TRANSFERS`:

```python
SEASON_LAST_GW = 38
"""Last gameweek of a season.

Needed here rather than imported from ``advise`` so the objective can price a
banked transfer by how many weeks are left to spend it in. A duplicate of
``advise.LAST_GW`` on purpose: ``milp`` must not import ``advise``.
"""
```

Extend the signature:

```python
def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int,
               fixed_moves: FixedMoves | None = None,
               ft_lambda: "LambdaLookup | None" = None) -> Plan:
```

with `from gaffer.optimize.ft_value import LambdaLookup` at the top (a plain
import — `ft_value` imports nothing from `milp`, so there is no cycle).

Replace the single terminal FT line in the objective:

```python
    obj.append(-hit_cost * d * hits[t])
```
...unchanged, then in place of `obj.append(ft_value * ftv[T[-1]])`:

```python
    # Terminal value of the banked free transfers.
    #
    # Flat ft_value says the fifth banked transfer is worth as much as the
    # first, which is the assumption that makes the solver hoard. With a
    # lambda table the value is concave: ftge[j] is "the terminal count is at
    # least j", each priced by its own shadow price, and their sum is the
    # count. Lambda is decreasing in j, so maximization fills the low indices
    # first without being told to; the ordering constraints are insurance
    # against a degenerate table, not the mechanism.
    if ft_lambda is None or ft_lambda.empty:
        obj.append(ft_value * ftv[T[-1]])
    else:
        weeks_left = max(1, SEASON_LAST_GW - T[-1])
        ftge = V("ftge", list(range(1, MAX_FREE_TRANSFERS + 1)),
                 cat="Binary")
        prob += ftv[T[-1]] == pulp.lpSum(
            ftge[j] for j in range(1, MAX_FREE_TRANSFERS + 1))
        for j in range(2, MAX_FREE_TRANSFERS + 1):
            prob += ftge[j] <= ftge[j - 1]
        for j in range(1, MAX_FREE_TRANSFERS + 1):
            obj.append(ft_lambda(j, weeks_left) * ftge[j])
```

Note this block must appear **before** `prob += pulp.lpSum(obj)`, and the two
`prob +=` constraint lines inside it are constraints being added after the main
constraint loop, which PuLP allows.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_milp.py tests/test_v4c_degradation.py -v`
Expected: PASS (both files)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/milp.py tests/test_milp.py
git commit -m "feat: price banked free transfers by lambda(k,t) in the objective

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 15: The wildcard pays for the FT bank it destroys

Spec §5's third consumption point. Playing a wildcard resets the banked
transfers, and `wildcard_now_assessment` currently prices that at zero — so a
wildcard looks free when you are sitting on five banked FTs, which is exactly
when it is most expensive.

**Files:**
- Modify: `src/gaffer/optimize/chips.py:208-226` (`wildcard_now_assessment`)
- Test: `tests/test_chips.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_chips.py`:

```python
# --- v4c: the wildcard destroys a bank of free transfers -------------------

from gaffer.optimize.ft_value import LambdaLookup
from tests.test_v4c_degradation import GOLDEN_KW, golden_pool
from tests.test_milp import _owned_state


def test_wildcard_assessment_without_a_lambda_table_is_unchanged():
    """The rail: no priors, no behaviour change."""
    pool = golden_pool()
    state = _owned_state(pool)
    a = wildcard_now_assessment(pool, state, **GOLDEN_KW)
    b = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=None)
    assert a == b


def test_an_empty_lambda_table_is_also_unchanged():
    pool = golden_pool()
    state = _owned_state(pool)
    a = wildcard_now_assessment(pool, state, **GOLDEN_KW)
    b = wildcard_now_assessment(pool, state, **GOLDEN_KW,
                                ft_lambda=LambdaLookup({}))
    assert a["gain_over_horizon"] == b["gain_over_horizon"]


def test_the_wildcard_gain_is_reduced_by_the_banked_ft_value():
    """Five banked transfers are five options the wildcard throws away."""
    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=5)
    lam = LambdaLookup({(k, t): 1.0 for k in range(1, 6)
                        for t in range(1, 39)})
    plain = wildcard_now_assessment(pool, state, **GOLDEN_KW)
    priced = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=lam)
    assert (abs(priced["gain_over_horizon"]
                - (plain["gain_over_horizon"] - 5.0)) < 0.01)


def test_the_assessment_reports_what_it_deducted():
    """Printing the number is the difference between a defensible decision
    and a mysterious one."""
    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=3)
    lam = LambdaLookup({(k, t): 2.0 for k in range(1, 6)
                        for t in range(1, 39)})
    out = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=lam)
    assert out["ft_bank_cost"] == 6.0


def test_a_bank_of_one_free_transfer_costs_only_its_own_lambda():
    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=1)
    lam = LambdaLookup({(1, t): 2.0 for t in range(1, 39)} |
                       {(k, t): 0.5 for k in range(2, 6)
                        for t in range(1, 39)})
    out = wildcard_now_assessment(pool, state, **GOLDEN_KW, ft_lambda=lam)
    assert out["ft_bank_cost"] == 2.0


def test_the_deduction_can_flip_a_marginal_recommendation_off():
    pool = golden_pool()
    state = replace(_owned_state(pool), free_transfers=5)
    huge = LambdaLookup({(k, t): 100.0 for k in range(1, 6)
                         for t in range(1, 39)})
    assert wildcard_now_assessment(pool, state, **GOLDEN_KW,
                                   ft_lambda=huge)["recommend"] is False
```

Add `from dataclasses import replace` to the file's imports if it is not
already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chips.py -k wildcard_assessment_without -v`
Expected: FAIL — `TypeError: solve_plan() got an unexpected keyword argument 'ft_lambda'`
raised through `**cfg`, or `KeyError: 'ft_bank_cost'` on the later cases.

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/optimize/chips.py`, rewrite `wildcard_now_assessment`'s tail.
`ft_lambda` arrives inside `**cfg` (it is part of the solver bundle), so pull it
out rather than adding a positional argument — that keeps every call site in
`advise.py` and `backtest.py` splatting one dict:

```python
def wildcard_now_assessment(pool: pd.DataFrame, state: SolveInput,
                            base: Plan | None = None, **cfg) -> dict:
```
(unchanged signature) and inside, after `gain` is computed:

```python
    # A wildcard resets the free-transfer bank. Priced at zero, a wildcard
    # looks cheapest exactly when it is most expensive — sitting on five
    # banked transfers is five weeks of options the chip throws away. The
    # lambda table knows what each of them is worth.
    ft_lambda = cfg.get("ft_lambda")
    ft_bank_cost = 0.0
    if ft_lambda is not None and not ft_lambda.empty:
        weeks_left = max(1, SEASON_LAST_GW - state.gws[-1])
        ft_bank_cost = ft_lambda.bank_value(state.free_transfers, weeks_left)
    gain = gain - ft_bank_cost
    return {"gain_over_horizon": round(gain, 2),
            "ft_bank_cost": round(ft_bank_cost, 2),
            "wc_squad": wc.gw_plans[0].squad,
            "recommend": gain > WILDCARD_RECOMMEND_THRESHOLD}
```

Add `from gaffer.optimize.milp import SEASON_LAST_GW` to the module's existing
milp import line.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chips.py -v`
Expected: PASS (whole file)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/chips.py tests/test_chips.py
git commit -m "feat: charge the wildcard for the FT bank it destroys

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 16: Objective craft — convex bench weights and the churn penalty

Spec §8. Three changes, all neutral by default until Gate D2 measures them.

The bench weight is currently uniform 0.10 across four bench players, which
says the third outfield substitute contributes as much expected value as the
first. Autosub reality is nothing like that: the first bench outfielder comes
on often, the third almost never. Spec's weights are `{GK + 1st: 0.21,
2nd: 0.06, 3rd: 0.002}`.

Bench *order* is not modelled and spec §10 says it stays unmodelled. The
weights are applied to the 1st/2nd/3rd highest-EP bench outfielders, which is
representable exactly: three slot indicators per week, each assigned to one
bench outfielder, with strictly decreasing weights. Because the weights
decrease, maximization puts the highest-EP bench player in the highest-weighted
slot without any ordering constraint.

`ft_use_penalty` is a small friction per transfer made, which stops EP-neutral
churn that the scenario noise would otherwise flip weekly. `itb_value` moves
0.05 → 0.08 in `config.toml`, not in the dataclass default, and only at D2.

After this task the **canonical, final** signature is:

```python
def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int,
               fixed_moves: FixedMoves | None = None,
               ft_lambda: "LambdaLookup | None" = None,
               ft_use_penalty: float = 0.0,
               bench_curve: list[float] | None = None) -> Plan:
```

**Files:**
- Modify: `src/gaffer/optimize/milp.py` (signature, variables, objective)
- Test: `tests/test_milp.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_milp.py`:

```python
# --- v4c: objective craft --------------------------------------------------

from gaffer.optimize.milp import DEFAULT_BENCH_CURVE


def test_the_default_bench_curve_is_the_spec_triple():
    assert DEFAULT_BENCH_CURVE == [0.21, 0.06, 0.002]


def test_bench_curve_none_is_the_identity():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, bench_curve=None,
                   ft_use_penalty=0.0)
    assert round(a.objective, 9) == round(b.objective, 9)


def test_a_bench_curve_changes_the_objective():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW,
                   bench_curve=DEFAULT_BENCH_CURVE)
    assert round(a.objective, 6) != round(b.objective, 6)


def test_a_bench_curve_still_produces_a_legal_squad():
    pool = golden_pool()
    state = _owned_state(pool)
    first = solve_plan(pool, state, **GOLDEN_KW,
                       bench_curve=DEFAULT_BENCH_CURVE).gw_plans[0]
    assert len(first.squad) == 15 and len(first.xi) == 11
    assert len(first.bench) == 4


def test_the_bench_curve_must_have_three_weights():
    """Three outfield bench slots; the bench keeper rides on the first
    weight, per spec's '{GK + 1st: 0.21}'."""
    pool = golden_pool()
    state = _owned_state(pool)
    with pytest.raises(GafferError) as exc:
        solve_plan(pool, state, **GOLDEN_KW, bench_curve=[0.2, 0.1])
    assert "three" in str(exc.value)


def test_bench_boost_overrides_the_curve_entirely():
    """Under a bench boost every bench player scores in full; a curve that
    survived would understate the chip by more than the chip is worth."""
    import inspect

    src = inspect.getsource(solve_plan)
    assert "state.bench_boost_gw == t" in src
    pool = golden_pool()
    state = _owned_state(pool)
    boosted = solve_plan(pool, replace(state, bench_boost_gw=1),
                         **GOLDEN_KW, bench_curve=DEFAULT_BENCH_CURVE)
    plain = solve_plan(pool, state, **GOLDEN_KW,
                       bench_curve=DEFAULT_BENCH_CURVE)
    assert boosted.objective > plain.objective


def test_a_convex_curve_prefers_a_stronger_first_bench_slot():
    """The behavioural claim: the curve buys a better first substitute and
    stops paying for the third."""
    pool = golden_pool()
    state = SolveInput(owned_codes=[], bank=1000, free_transfers=15,
                       gws=[1, 2])
    ep_of = {int(r.code): float(r.ep[1]) for r in pool.itertuples()}
    flat = solve_plan(pool, state, **GOLDEN_KW).gw_plans[0]
    curved = solve_plan(pool, state, **GOLDEN_KW,
                        bench_curve=DEFAULT_BENCH_CURVE).gw_plans[0]
    assert (max(ep_of[c] for c in curved.bench)
            >= max(ep_of[c] for c in flat.bench))


def test_ft_use_penalty_zero_is_the_identity():
    pool = golden_pool()
    state = _owned_state(pool)
    a = solve_plan(pool, state, **GOLDEN_KW)
    b = solve_plan(pool, state, **GOLDEN_KW, ft_use_penalty=0.0)
    assert round(a.objective, 9) == round(b.objective, 9)


def test_a_large_ft_use_penalty_stops_marginal_churn():
    pool = golden_pool()
    state = _owned_state(pool)
    busy = solve_plan(pool, state, **GOLDEN_KW).gw_plans[0]
    calm = solve_plan(pool, state, **GOLDEN_KW,
                      ft_use_penalty=50.0).gw_plans[0]
    assert len(calm.buys) <= len(busy.buys)


def test_the_churn_penalty_is_waived_on_a_wildcard_week():
    """Fifteen transfers on a wildcard are the chip working, not churn."""
    import inspect

    src = inspect.getsource(solve_plan)
    penalty = src.index("ft_use_penalty *")
    assert "if not wc:" in src[max(0, penalty - 200):penalty + 200]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_milp.py -k bench_curve -v`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_BENCH_CURVE' from 'gaffer.optimize.milp'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/optimize/milp.py`, add the constant next to the others:

```python
DEFAULT_BENCH_CURVE = [0.21, 0.06, 0.002]
"""Autosub-weighted bench values for the 1st, 2nd and 3rd outfield sub.

Uniform 0.10 says the third substitute is as likely to earn you points as the
first, which is not close to true: the first bench outfielder comes on
regularly, the third essentially never. The bench goalkeeper rides on the
first weight — he plays exactly when your starting keeper does not, which is
about as often as the first outfield sub appears.

Not the default in ``config.toml``: Gate D2 measures it first.
"""

BENCH_SLOTS = 3
"""Outfield bench slots. The fourth bench player is the reserve keeper, who is
priced by the first curve weight rather than by a slot of his own."""
```

Extend the signature to the canonical form quoted above, and add validation
next to the existing `locked_in` checks:

```python
    if bench_curve is not None and len(bench_curve) != BENCH_SLOTS:
        raise GafferError(
            f"bench_curve needs exactly three weights (1st/2nd/3rd outfield "
            f"substitute), got {len(bench_curve)}")
```

Declare the slot variables next to the others (only when a curve is in play,
so the default problem is byte-identical):

```python
    slot = (V("slot", (codes, T, list(range(BENCH_SLOTS))), cat="Binary")
            if bench_curve is not None else None)
```

Add the slot constraints inside the existing `for t_i, t in enumerate(T):`
loop, after the per-code constraints:

```python
        if slot is not None:
            benched = {c: sq[c][t] - xi[c][t] for c in codes}
            outfield = [c for c in codes if pos[c] != "GKP"]
            for s in range(BENCH_SLOTS):
                # Exactly one player fills each outfield bench slot.
                prob += pulp.lpSum(slot[c][t][s] for c in outfield) == 1
            for c in outfield:
                # A player can fill at most one slot, and only if benched.
                prob += pulp.lpSum(slot[c][t][s]
                                   for s in range(BENCH_SLOTS)) <= benched[c]
            for c in codes:
                if pos[c] == "GKP":
                    for s in range(BENCH_SLOTS):
                        prob += slot[c][t][s] == 0
```

And replace the bench term in the objective loop. The current line is:

```python
            obj.append(d * e * bw * (sq[c][t] - xi[c][t]))
```

Replace the whole per-code bench append with:

```python
            if bench_curve is None or state.bench_boost_gw == t:
                # No curve, or a bench boost — under a boost every bench
                # player scores in full, so slot weights would understate the
                # chip.
                obj.append(d * e * bw * (sq[c][t] - xi[c][t]))
            elif pos[c] == "GKP":
                # The reserve keeper is priced by the first curve weight: he
                # plays exactly when the starter does not.
                obj.append(d * e * bench_curve[0] * (sq[c][t] - xi[c][t]))
            else:
                for s in range(BENCH_SLOTS):
                    obj.append(d * e * bench_curve[s] * slot[c][t][s])
```

and add the churn penalty at the end of the same week's block, after
`obj.append(-hit_cost * d * hits[t])`:

```python
        if ft_use_penalty and not wc:
            # A tiny friction per transfer made. EP-neutral churn is what the
            # scenario noise flips week to week, and a fraction of a point of
            # resistance settles it without ever outweighing a real gain.
            # Waived on a wildcard: fifteen transfers there are the chip
            # working as designed.
            obj.append(-ft_use_penalty * d * nt)
```

`nt` is already bound at the top of the loop as
`nt = pulp.lpSum(tin[c][t] for c in codes)`, and `pos` is the existing
`{code: position}` local; bind one next to `codes` if it does not exist yet.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_milp.py tests/test_v4c_degradation.py -v`
Expected: PASS (both files)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/milp.py tests/test_milp.py
git commit -m "feat: convex bench weights and a transfer-churn penalty

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 17: `chip_policy.py` — the θ_t backward recursion

Spec §6. `CHIP_PLAY_THRESHOLD = 4.0` is a flat bar that ignores the calendar: a
bench boost worth 5 points in GW8 clears it and gets played, even though the
December double gameweeks are worth 12 and are still coming. The correct bar is
the *option value of waiting*: play iff this week's surplus beats what you
expect the best remaining week to give you.

That is a classic optimal-stopping recursion:

```
θ_T = 0                       at expiry, anything beats nothing
θ_t = E[ max(S_{t+1}, θ_{t+1}) ]
```

θ declines to zero at expiry by construction, so a chip is never stranded — the
last week's bar is zero and any positive surplus plays it.

**Files:**
- Create: `src/gaffer/optimize/chip_policy.py`
- Test: `tests/test_chip_policy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_chip_policy.py`:

```python
import pytest

from gaffer.optimize.chip_policy import (FIRST_HALF_LAST_GW, chip_windows,
                                         flat_thresholds, stopping_thresholds)


def test_theta_at_the_last_week_of_the_window_is_zero():
    """Nothing beats nothing: at expiry, any positive surplus plays."""
    th = stopping_thresholds({t: [1.0, 5.0] for t in range(5, 20)},
                             last_gw=19)
    assert th[19] == 0.0


def test_theta_declines_monotonically_towards_expiry():
    """More weeks left is more chances at a big one, always."""
    th = stopping_thresholds({t: [0.0, 4.0, 12.0] for t in range(5, 20)},
                             last_gw=19)
    vals = [th[t] for t in range(5, 20)]
    assert vals == sorted(vals, reverse=True), vals


def test_theta_is_at_least_the_mean_of_the_next_weeks_surplus():
    """E[max(S, theta)] >= E[S]: waiting can never be worth less than one
    more draw."""
    samples = [0.0, 4.0, 8.0]
    th = stopping_thresholds({t: samples for t in range(5, 20)}, last_gw=19)
    assert th[18] >= sum(samples) / len(samples) - 1e-12


def test_theta_at_the_second_to_last_week_is_the_next_weeks_mean():
    """Hand-checkable: theta_19 = 0, so theta_18 = E[max(S_19, 0)]."""
    th = stopping_thresholds({19: [-2.0, 2.0, 6.0]}, last_gw=19,
                             first_gw=18)
    assert abs(th[18] - (0.0 + 2.0 + 6.0) / 3) < 1e-12


def test_a_fatter_tail_raises_every_threshold():
    """A chance of a huge double gameweek is exactly what makes waiting
    worth it."""
    lean = stopping_thresholds({t: [2.0, 3.0] for t in range(5, 20)},
                               last_gw=19)
    fat = stopping_thresholds({t: [2.0, 30.0] for t in range(5, 20)},
                              last_gw=19)
    for t in range(5, 19):
        assert fat[t] > lean[t]


def test_a_week_with_no_samples_contributes_nothing_but_does_not_break():
    """A gap in the calibration must not silently zero the whole tail."""
    dist = {t: [4.0] for t in range(5, 20)}
    del dist[12]
    th = stopping_thresholds(dist, last_gw=19)
    assert th[11] > 0.0 and th[19] == 0.0


def test_thresholds_cover_every_week_in_the_window():
    th = stopping_thresholds({t: [3.0] for t in range(20, 39)}, last_gw=38,
                             first_gw=20)
    assert set(th) == set(range(20, 39))


def test_thresholds_are_never_negative():
    th = stopping_thresholds({t: [-5.0, -1.0] for t in range(5, 20)},
                             last_gw=19)
    assert min(th.values()) >= 0.0


def test_an_empty_distribution_gives_a_zero_threshold_everywhere():
    """Degradation: no calibration means no opinion about waiting, which is
    'play it when it is any good', not 'never play it'."""
    th = stopping_thresholds({}, last_gw=19, first_gw=5)
    assert set(th.values()) == {0.0}


# --- chip windows ----------------------------------------------------------

def test_the_first_half_ends_at_gameweek_nineteen():
    assert FIRST_HALF_LAST_GW == 19


def test_a_first_half_chip_expires_at_gameweek_nineteen():
    assert chip_windows(7) == (7, 19)


def test_a_second_half_chip_expires_at_gameweek_thirty_eight():
    assert chip_windows(25) == (25, 38)


def test_the_window_boundary_belongs_to_the_first_half():
    assert chip_windows(19) == (19, 19)
    assert chip_windows(20) == (20, 38)


# --- the flat fallback -----------------------------------------------------

def test_flat_thresholds_reproduce_todays_constants():
    """The degradation rail: no priors asset means exactly the old bars."""
    from gaffer.optimize.chips import (CHIP_PLAY_THRESHOLD,
                                       WILDCARD_RECOMMEND_THRESHOLD)

    flat = flat_thresholds()
    assert flat("bboost", 7) == CHIP_PLAY_THRESHOLD
    assert flat("3xc", 30) == CHIP_PLAY_THRESHOLD
    assert flat("freehit", 12) == CHIP_PLAY_THRESHOLD
    assert flat("wildcard", 7) == WILDCARD_RECOMMEND_THRESHOLD


def test_flat_thresholds_ignore_the_gameweek_entirely():
    """That is the bug this cycle is fixing, stated as a test so the fallback
    is unmistakably the *old* behaviour."""
    flat = flat_thresholds()
    assert flat("bboost", 5) == flat("bboost", 19) == flat("bboost", 38)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chip_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.optimize.chip_policy'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/optimize/chip_policy.py`:

```python
"""When to play a chip: optimal stopping instead of a flat bar.

``CHIP_PLAY_THRESHOLD = 4.0`` asks the wrong question. It asks "is this chip
worth four points this week", when the question is "is this chip worth more
this week than the best week still to come". A bench boost worth five points in
September clears a flat four-point bar and gets burned, three months before the
December doubles it exists for.

The right bar is the option value of waiting, and it has a standard form::

    theta_T = 0
    theta_t = E[max(S_{t+1}, theta_{t+1})]

theta_T = 0 is what guarantees no chip is ever stranded: in the last week of
its window the bar is zero, so any positive surplus plays it. Everywhere else
the bar is the expected value of the best remaining opportunity, so an early
chip has to beat December to get played in September.

The per-week surplus distributions come from replay (``calibrate_decisions``),
so double and blank gameweeks are in the tail as history recorded them rather
than as anyone's guess. ``data/chip_scenarios.toml`` can shift that tail
forward when the season's real double gameweeks become knowable (see
:func:`apply_dgw_scenarios`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

FIRST_HALF_LAST_GW = 19
"""Last gameweek of the first chip half.

2026/27 grants two of every chip; the first set expires after GW19 and a fresh
set arrives for GW20. A chip's stopping problem therefore runs to 19 or to 38,
never across the boundary.
"""

SEASON_LAST_GW = 38

CHIP_SCENARIOS_PATH = Path("data/chip_scenarios.toml")
"""Optional per-gameweek double-gameweek probabilities.

Absent today and expected to stay absent until the Crellin-style fixture
projections land around January. The hook exists so that populating it is a
data change rather than a code change; see spec §6 and §10.
"""

DGW_SURPLUS_MULTIPLIER = 2.0
"""How much a double gameweek is worth relative to a single one, for the
purpose of shifting a future week's surplus distribution.

A chip that plays over two fixtures instead of one roughly doubles its
surplus — a bench boost boosts twice as many bench appearances, a triple
captain triples twice. Deliberately crude: the scenario file supplies the
*probability*, and this supplies the magnitude, and neither is worth
over-fitting until the file actually exists.
"""


def chip_windows(gw: int) -> tuple[int, int]:
    """``(first, last)`` gameweek of the chip window containing ``gw``."""
    if gw <= FIRST_HALF_LAST_GW:
        return (gw, FIRST_HALF_LAST_GW)
    return (gw, SEASON_LAST_GW)


def stopping_thresholds(surplus_by_gw: dict[int, list[float]], last_gw: int,
                        first_gw: int | None = None) -> dict[int, float]:
    """``theta_t`` for every week in ``[first_gw, last_gw]``.

    ``surplus_by_gw`` maps a gameweek to an empirical sample of that week's
    chip surplus. A week with no samples contributes nothing to the
    expectation but does not truncate the recursion — a gap in the calibration
    is missing information, not a claim that the week is worthless.

    Thresholds are clamped at zero: a negative bar would mean "play this chip
    even though it loses points", which is never the recommendation.
    """
    start = first_gw if first_gw is not None else (
        min(surplus_by_gw) if surplus_by_gw else last_gw)
    theta: dict[int, float] = {last_gw: 0.0}
    for t in range(last_gw - 1, start - 1, -1):
        nxt = surplus_by_gw.get(t + 1) or []
        ahead = theta[t + 1]
        if not nxt:
            theta[t] = ahead
            continue
        theta[t] = max(0.0, sum(max(s, ahead) for s in nxt) / len(nxt))
    return {t: theta[t] for t in range(start, last_gw + 1)}


def load_chip_scenarios(path: Path | str = CHIP_SCENARIOS_PATH
                        ) -> dict[int, float]:
    """``{gw: P(double gameweek)}`` from the optional scenario file.

    Expected shape::

        [dgw]
        26 = 0.7
        29 = 0.4

    Returns ``{}`` when the file is absent, which is the normal case for most
    of a season and must never be an error.
    """
    p = Path(path)
    if not p.exists():
        return {}
    raw = tomllib.loads(p.read_text())
    return {int(gw): float(prob)
            for gw, prob in raw.get("dgw", {}).items()}


def apply_dgw_scenarios(surplus_by_gw: dict[int, list[float]],
                        dgw_probs: dict[int, float]
                        ) -> dict[int, list[float]]:
    """Shift future weeks' surplus samples by their double-gameweek mass.

    A week believed to be a double with probability ``p`` gets a mixture: the
    original samples with weight ``1 - p``, and the same samples scaled by
    :data:`DGW_SURPLUS_MULTIPLIER` with weight ``p``. Because the recursion
    consumes the samples as an unweighted empirical distribution, the mixture
    is realized by *duplication* — a 70% belief becomes seven scaled copies
    against three plain ones.

    Weeks not named in the file are untouched. The historical replay
    distribution already contains real double gameweeks, so an empty file
    leaves a perfectly usable prior rather than a fixture-blind one.
    """
    if not dgw_probs:
        return dict(surplus_by_gw)
    out = dict(surplus_by_gw)
    for gw, prob in dgw_probs.items():
        base = surplus_by_gw.get(gw)
        if not base:
            continue
        p = min(max(float(prob), 0.0), 1.0)
        n_dgw = int(round(p * 10))
        mixed = base * (10 - n_dgw)
        mixed += [s * DGW_SURPLUS_MULTIPLIER for s in base] * n_dgw
        out[gw] = mixed
    return out


def flat_thresholds():
    """The pre-v4c bars, as a ``(chip, gw) -> float`` callable.

    This is the degradation rail for the whole workstream: with no priors
    asset, every caller gets exactly the constants it used before, including
    their indifference to the calendar.
    """
    from gaffer.optimize.chips import (CHIP_PLAY_THRESHOLD,
                                       WILDCARD_RECOMMEND_THRESHOLD)

    def lookup(chip: str, gw: int) -> float:
        return (WILDCARD_RECOMMEND_THRESHOLD if chip == "wildcard"
                else CHIP_PLAY_THRESHOLD)

    return lookup


def thresholds_from_priors(chip_surplus: dict[str, dict[int, list[float]]],
                           dgw_probs: dict[int, float] | None = None):
    """A ``(chip, gw) -> theta`` callable built from calibrated distributions.

    ``chip_surplus`` is ``{chip: {gw: [surplus samples]}}``. Each chip is
    solved twice — once over the GW1-19 window and once over GW20-38 — because
    a chip held in the first half cannot be saved for the second.

    An unknown chip, or one with no samples at all, falls through to
    :func:`flat_thresholds` rather than to zero: no calibration is a reason to
    keep the old bar, not a reason to play the chip on any positive surplus.
    """
    flat = flat_thresholds()
    tables: dict[str, dict[int, float]] = {}
    for chip, by_gw in chip_surplus.items():
        shifted = apply_dgw_scenarios(by_gw, dgw_probs or {})
        first = stopping_thresholds(shifted, last_gw=FIRST_HALF_LAST_GW,
                                    first_gw=1)
        second = stopping_thresholds(shifted, last_gw=SEASON_LAST_GW,
                                     first_gw=FIRST_HALF_LAST_GW + 1)
        tables[chip] = {**first, **second}

    def lookup(chip: str, gw: int) -> float:
        table = tables.get(chip)
        if not table:
            return flat(chip, gw)
        return float(table.get(int(gw), 0.0))

    return lookup
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chip_policy.py -v`
Expected: PASS (15 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/chip_policy.py tests/test_chip_policy.py
git commit -m "feat: theta_t chip stopping thresholds by backward recursion

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 18: The `data/chip_scenarios.toml` hook, tested without the file

Spec §6 and §10: the hook ships this cycle, the file does not. That makes the
*absence* the case worth testing hardest — it is the case that will run for the
next five months.

**Files:**
- Modify: `tests/test_chip_policy.py` (append)
- Test: `tests/test_chip_policy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_chip_policy.py`:

```python
# --- the DGW scenario hook -------------------------------------------------

from gaffer.optimize.chip_policy import (CHIP_SCENARIOS_PATH,
                                         DGW_SURPLUS_MULTIPLIER,
                                         apply_dgw_scenarios,
                                         load_chip_scenarios,
                                         thresholds_from_priors)


def test_the_scenario_file_is_absent_this_cycle():
    """Spec §10: the hook ships, the data does not. If this starts failing
    because someone populated it, delete this test — but do it knowingly."""
    assert not CHIP_SCENARIOS_PATH.exists()


def test_loading_an_absent_scenario_file_is_an_empty_dict_not_an_error():
    assert load_chip_scenarios("data/does-not-exist.toml") == {}


def test_loading_a_scenario_file_reads_the_dgw_table(tmp_path):
    p = tmp_path / "chip_scenarios.toml"
    p.write_text("[dgw]\n26 = 0.7\n29 = 0.4\n")
    assert load_chip_scenarios(p) == {26: 0.7, 29: 0.4}


def test_a_scenario_file_with_no_dgw_table_is_empty(tmp_path):
    p = tmp_path / "chip_scenarios.toml"
    p.write_text("[bgw]\n18 = 0.5\n")
    assert load_chip_scenarios(p) == {}


def test_applying_no_scenarios_leaves_the_distributions_alone():
    dist = {26: [4.0, 8.0], 27: [3.0]}
    assert apply_dgw_scenarios(dist, {}) == dist


def test_a_certain_dgw_scales_every_sample():
    out = apply_dgw_scenarios({26: [4.0]}, {26: 1.0})
    assert set(out[26]) == {4.0 * DGW_SURPLUS_MULTIPLIER}


def test_a_probable_dgw_mixes_scaled_and_plain_samples():
    out = apply_dgw_scenarios({26: [4.0]}, {26: 0.7})
    assert out[26].count(8.0) == 7
    assert out[26].count(4.0) == 3


def test_a_dgw_on_a_week_with_no_samples_is_ignored():
    assert apply_dgw_scenarios({26: [4.0]}, {30: 0.9}) == {26: [4.0]}


def test_a_dgw_belief_raises_the_thresholds_before_that_week():
    """The behavioural point of the hook: knowing a double is coming should
    make the tool refuse to burn the chip beforehand."""
    dist = {"bboost": {t: [4.0] for t in range(5, 20)}}
    plain = thresholds_from_priors(dist)
    informed = thresholds_from_priors(dist, {18: 1.0})
    assert informed("bboost", 10) > plain("bboost", 10)


def test_thresholds_from_priors_falls_back_flat_for_an_unknown_chip():
    from gaffer.optimize.chips import CHIP_PLAY_THRESHOLD

    lookup = thresholds_from_priors({"bboost": {10: [4.0]}})
    assert lookup("3xc", 10) == CHIP_PLAY_THRESHOLD


def test_thresholds_from_priors_is_zero_at_each_expiry():
    """No chip stranded — spec §9's D3 condition, expressed as a unit test so
    the replay only has to confirm it."""
    dist = {"bboost": {t: [4.0] for t in range(1, 39)}}
    lookup = thresholds_from_priors(dist)
    assert lookup("bboost", 19) == 0.0
    assert lookup("bboost", 38) == 0.0


def test_the_two_chip_halves_are_solved_independently():
    """A chip held in the first half cannot be saved for the second, so a
    fat GW30 tail must not raise the GW10 bar."""
    dist = {"bboost": {**{t: [1.0] for t in range(1, 20)},
                       **{t: [40.0] for t in range(20, 39)}}}
    lookup = thresholds_from_priors(dist)
    assert lookup("bboost", 10) < 5.0
    assert lookup("bboost", 25) > 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chip_policy.py -k scenario -v`
Expected: PASS already for most cases (Task 17 implemented the functions) —
the two that fail are `test_a_probable_dgw_mixes_scaled_and_plain_samples` and
`test_the_two_chip_halves_are_solved_independently` if the mixture arithmetic
or the window split is off. If everything passes on the first run, that is the
correct outcome for this task: it is a coverage task for a hook whose
implementation landed with the recursion it serves.

- [ ] **Step 3: Write minimal implementation**

Only if a case failed. The two likely fixes:

- Mixture counts: `n_dgw = int(round(p * 10))` and the two list repetitions
  must produce exactly ten samples per original sample. Verify with
  `apply_dgw_scenarios({26: [4.0]}, {26: 0.7})` → seven `8.0`s and three
  `4.0`s.
- Window independence: `thresholds_from_priors` must call
  `stopping_thresholds` twice with `(first_gw=1, last_gw=19)` and
  `(first_gw=20, last_gw=38)`, never once across the whole season.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chip_policy.py -v`
Expected: PASS (27 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/chip_policy.py tests/test_chip_policy.py
git commit -m "test: the DGW scenario hook, exercised without the file

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 19: The `decision_priors.json` asset and its loader

Both calibrated tables live in one committed asset so a fresh clone decides
sensibly without ever running the calibrator. Spec §7 is explicit that the
asset ships in git, and §5/§6 are explicit that its absence degrades to flat
values.

`src/gaffer/assets/__init__.py` currently has no absent-asset pattern — its two
loaders assume the file is a package invariant. This one is different and needs
an existence check, so it gets one.

The file is created here with the **schema and empty distributions**, so the
loader has something to load and the tests have something to read; Task 21's
calibrator fills it with real numbers.

**Files:**
- Create: `src/gaffer/assets/decision_priors.json`
- Modify: `src/gaffer/assets/__init__.py` (append)
- Test: `tests/test_calibrate_decisions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_calibrate_decisions.py`:

```python
import json

import pytest

from gaffer.assets import (DECISION_PRIORS, decision_priors_exist,
                           load_decision_priors)


def test_the_asset_is_shipped_in_the_package():
    assert decision_priors_exist() is True


def test_the_asset_has_the_documented_schema():
    priors = load_decision_priors()
    assert set(priors) >= {"version", "seasons", "transfer_surplus",
                           "chip_surplus"}
    assert priors["version"] == 1


def test_transfer_surplus_is_keyed_by_season_phase():
    priors = load_decision_priors()
    assert set(priors["transfer_surplus"]) == {"early", "mid", "late"}
    for samples in priors["transfer_surplus"].values():
        assert isinstance(samples, list)


def test_chip_surplus_is_keyed_by_chip_then_by_gameweek_string():
    priors = load_decision_priors()
    assert set(priors["chip_surplus"]) == {"wildcard", "bboost", "3xc",
                                           "freehit"}
    for by_gw in priors["chip_surplus"].values():
        assert isinstance(by_gw, dict)
        for key in by_gw:
            assert key.isdigit(), key


def test_the_asset_is_valid_json_on_disk():
    from importlib.resources import files

    raw = files("gaffer.assets").joinpath(DECISION_PRIORS).read_text()
    assert isinstance(json.loads(raw), dict)


def test_loading_when_the_asset_is_absent_returns_none(monkeypatch):
    """The whole degradation rail for lambda and theta hangs off this."""
    import gaffer.assets as assets_mod

    monkeypatch.setattr(assets_mod, "DECISION_PRIORS", "not-a-file.json")
    assert assets_mod.decision_priors_exist() is False
    assert assets_mod.load_decision_priors() is None


# --- what the two consumers do with an absent asset ------------------------

def test_lambda_from_absent_priors_is_an_empty_lookup():
    from gaffer.optimize.ft_value import lambda_from_priors

    lam = lambda_from_priors(None)
    assert lam.empty is True
    assert lam(2, 20) == 0.0


def test_lambda_from_priors_with_no_samples_is_also_empty():
    from gaffer.optimize.ft_value import lambda_from_priors

    assert lambda_from_priors(
        {"transfer_surplus": {"early": [], "mid": [], "late": []}}).empty


def test_lambda_from_priors_builds_a_table_from_real_samples():
    from gaffer.optimize.ft_value import lambda_from_priors

    lam = lambda_from_priors(
        {"transfer_surplus": {"early": [0.5, 2.0, 5.0],
                              "mid": [0.5, 2.0], "late": [1.0]}})
    assert lam.empty is False
    assert lam(1, 30) > lam(5, 30)
    assert lam(2, 30) > lam(2, 3)


def test_thresholds_from_absent_priors_are_the_flat_constants():
    from gaffer.optimize.chip_policy import thresholds_from_priors
    from gaffer.optimize.chips import CHIP_PLAY_THRESHOLD

    from gaffer.optimize.chip_policy import chip_thresholds_from_asset

    lookup = chip_thresholds_from_asset(None)
    assert lookup("bboost", 7) == CHIP_PLAY_THRESHOLD


def test_thresholds_from_a_real_asset_vary_by_week():
    from gaffer.optimize.chip_policy import chip_thresholds_from_asset

    lookup = chip_thresholds_from_asset(
        {"chip_surplus": {"bboost": {str(t): [3.0, 9.0]
                                     for t in range(1, 39)}}})
    assert lookup("bboost", 5) > lookup("bboost", 18)
    assert lookup("bboost", 19) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calibrate_decisions.py -v`
Expected: FAIL — `ImportError: cannot import name 'DECISION_PRIORS' from 'gaffer.assets'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/assets/decision_priors.json`:

```json
{
  "version": 1,
  "generated_at": null,
  "seasons": [],
  "note": "Placeholder shipped with the v4c schema. Empty distributions mean every consumer falls back to flat ft_value and flat chip thresholds. Run `gaffer calibrate-decisions` to fill it.",
  "transfer_surplus": {
    "early": [],
    "mid": [],
    "late": []
  },
  "chip_surplus": {
    "wildcard": {},
    "bboost": {},
    "3xc": {},
    "freehit": {}
  }
}
```

Append to `src/gaffer/assets/__init__.py`:

```python
DECISION_PRIORS = "decision_priors.json"


def decision_priors_exist() -> bool:
    """Whether the calibrated decision priors are shipped.

    Unlike the other two assets in this package, this one is genuinely
    optional: spec §7's degradation rail says a clone without it must fall
    back to a flat ``ft_value`` and flat chip thresholds, which is exactly
    the pre-v4c behaviour.
    """
    return files(__package__).joinpath(DECISION_PRIORS).is_file()


def load_decision_priors() -> dict | None:
    """The calibrated λ and θ inputs, or ``None`` when the asset is absent.

    ``None`` rather than an empty dict, so a caller cannot accidentally treat
    "no calibration" as "calibration says zero" — the two mean opposite things
    to the chip policy.
    """
    if not decision_priors_exist():
        return None
    return json.loads(
        files(__package__).joinpath(DECISION_PRIORS).read_text(
            encoding="utf-8"))
```

Append to `src/gaffer/optimize/ft_value.py`:

```python
SEASON_WEEKS = 38

def lambda_from_priors(priors: dict | None) -> LambdaLookup:
    """Build the λ lookup from a decision-priors payload.

    All three season phases are pooled into one distribution. Splitting the DP
    by phase would need a phase-indexed state, and the phase is already
    implicit in ``t``: an early-season decision *is* a decision with thirty
    weeks left. The phases are kept separate in the asset because the
    calibrator reports them, and because a later cycle may want them.

    ``None``, or an asset with no samples, gives an empty lookup — the caller's
    signal to keep the flat ``ft_value``.
    """
    if not priors:
        return LambdaLookup({})
    pooled: list[float] = []
    for samples in (priors.get("transfer_surplus") or {}).values():
        pooled.extend(float(s) for s in samples)
    if not pooled:
        return LambdaLookup({})
    return LambdaLookup(lambda_table(pooled, weeks=SEASON_WEEKS))
```

Append to `src/gaffer/optimize/chip_policy.py`:

```python
def chip_thresholds_from_asset(priors: dict | None,
                               dgw_probs: dict[int, float] | None = None):
    """``(chip, gw) -> theta`` from a decision-priors payload.

    The asset stores gameweeks as JSON object keys, which are strings; this is
    where they become integers. ``None`` or an empty ``chip_surplus`` gives
    :func:`flat_thresholds`, which is the pre-v4c behaviour exactly.
    """
    if not priors:
        return flat_thresholds()
    raw = priors.get("chip_surplus") or {}
    parsed = {chip: {int(gw): [float(s) for s in samples]
                     for gw, samples in by_gw.items()}
              for chip, by_gw in raw.items() if by_gw}
    if not parsed:
        return flat_thresholds()
    return thresholds_from_priors(parsed, dgw_probs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_calibrate_decisions.py -v`
Expected: PASS (11 passed)

Run: `uv run pytest tests/test_web_packaging.py -v`
Expected: PASS — the wheel already globs `src/gaffer/assets/*.json`, so the new
file is packaged without a `pyproject.toml` change. If this fails, the glob has
been narrowed and needs the new filename adding.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/assets/decision_priors.json src/gaffer/assets/__init__.py src/gaffer/optimize/ft_value.py src/gaffer/optimize/chip_policy.py tests/test_calibrate_decisions.py
git commit -m "feat: decision_priors.json asset with a flat-fallback loader

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 20: `gaffer calibrate-decisions`

Spec §7. One offline command producing both distributions, written into the
asset. It replays past seasons with the existing backtest machinery: for the
transfer surplus, the best single-transfer EP delta per week with one FT in
hand; for the chip surplus, `evaluate_chips` gains per chip per week.

Slow, run rarely, and deliberately kept out of the advise path entirely.

**Files:**
- Create: `src/gaffer/calibrate_decisions.py`
- Modify: `src/gaffer/cli.py` (new command)
- Test: `tests/test_calibrate_decisions.py` (append), `tests/test_cli.py` (modify)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_calibrate_decisions.py`:

```python
# --- the calibrator --------------------------------------------------------

import pandas as pd

from gaffer.calibrate_decisions import (PHASE_BOUNDS, best_single_transfer,
                                        phase_of, run_calibration,
                                        write_priors)


def test_phase_bounds_split_the_season_into_thirds():
    assert PHASE_BOUNDS == {"early": (1, 12), "mid": (13, 25),
                            "late": (26, 38)}


def test_phase_of_maps_a_gameweek_to_its_third():
    assert phase_of(1) == "early" and phase_of(12) == "early"
    assert phase_of(13) == "mid" and phase_of(25) == "mid"
    assert phase_of(26) == "late" and phase_of(38) == "late"


def test_phase_of_clamps_out_of_range_gameweeks():
    assert phase_of(0) == "early" and phase_of(99) == "late"


def test_best_single_transfer_is_the_gain_over_making_none():
    """The surplus the lambda DP consumes: what one free transfer buys."""
    from gaffer.optimize.milp import SolveInput
    from tests.test_milp import _owned_state
    from tests.test_v4c_degradation import GOLDEN_KW, golden_pool

    pool = golden_pool()
    state = _owned_state(pool)
    gain = best_single_transfer(pool, state, **GOLDEN_KW)
    assert gain >= 0.0


def test_best_single_transfer_of_a_perfect_squad_is_zero():
    """No upgrade available, no surplus. A negative number here would poison
    the DP with 'transfers are bad'."""
    from gaffer.optimize.milp import SolveInput
    from tests.test_v4c_degradation import GOLDEN_KW, golden_pool

    pool = golden_pool()
    best = pool.sort_values("code")
    by_pos = {}
    for r in best.itertuples():
        by_pos.setdefault(r.position, []).append(int(r.code))
    # Own the highest-EP legal 15 already.
    owned = (by_pos["GKP"][-2:] + by_pos["DEF"][-5:] + by_pos["MID"][-5:]
             + by_pos["FWD"][-3:])
    state = SolveInput(owned_codes=owned, bank=0, free_transfers=1, gws=[1])
    assert best_single_transfer(pool, state, **GOLDEN_KW) >= 0.0


def test_write_priors_round_trips_through_the_asset_schema(tmp_path):
    payload = {
        "version": 1, "generated_at": "2026-08-25T00:00:00Z",
        "seasons": ["2023-24"],
        "transfer_surplus": {"early": [1.0], "mid": [2.0], "late": [3.0]},
        "chip_surplus": {"wildcard": {"5": [4.0]}, "bboost": {},
                         "3xc": {}, "freehit": {}},
    }
    dest = tmp_path / "decision_priors.json"
    write_priors(payload, dest)
    import json
    assert json.loads(dest.read_text())["transfer_surplus"]["mid"] == [2.0]


def test_write_priors_refuses_a_payload_missing_a_required_key(tmp_path):
    """A half-written asset is worse than none: it would silently produce a
    lambda table from three samples."""
    with pytest.raises(ValueError) as exc:
        write_priors({"version": 1}, tmp_path / "x.json")
    assert "transfer_surplus" in str(exc.value)


def test_write_priors_refuses_an_empty_transfer_distribution(tmp_path):
    with pytest.raises(ValueError):
        write_priors({"version": 1, "generated_at": "x", "seasons": [],
                      "transfer_surplus": {"early": [], "mid": [], "late": []},
                      "chip_surplus": {}}, tmp_path / "x.json")


def test_run_calibration_produces_the_asset_schema(monkeypatch):
    """Driven off a stubbed weekly walk so the schema is tested without a
    multi-hour replay."""
    import gaffer.calibrate_decisions as cal

    def fake_walk(season, **kw):
        return ([{"gw": g, "surplus": 1.0 + g % 3} for g in range(1, 39)],
                [{"gw": g, "chip": c, "gain": 2.0}
                 for g in range(1, 39)
                 for c in ("wildcard", "bboost", "3xc", "freehit")])

    monkeypatch.setattr(cal, "walk_season", fake_walk)
    out = run_calibration(["2023-24", "2024-25"])
    assert out["version"] == 1
    assert out["seasons"] == ["2023-24", "2024-25"]
    assert len(out["transfer_surplus"]["early"]) == 24   # 12 gws x 2 seasons
    assert set(out["chip_surplus"]) == {"wildcard", "bboost", "3xc",
                                        "freehit"}
    assert out["chip_surplus"]["bboost"]["7"] == [2.0, 2.0]


def test_run_calibration_survives_a_season_that_cannot_be_replayed(
        monkeypatch):
    import gaffer.calibrate_decisions as cal

    def flaky(season, **kw):
        if season == "2023-24":
            raise RuntimeError("no history for that season")
        return ([{"gw": 5, "surplus": 2.0}], [])

    monkeypatch.setattr(cal, "walk_season", flaky)
    out = run_calibration(["2023-24", "2024-25"])
    assert out["seasons"] == ["2024-25"]
    assert out["transfer_surplus"]["early"] == [2.0]
```

In `tests/test_cli.py`, add `"calibrate-decisions"` to **both** hardcoded
command lists (at `:8-13` and `:25-32`), and append:

```python
def test_calibrate_decisions_writes_the_shipped_asset():
    """The asset lives in the package, not in data/ — it is curated knowledge
    that has to survive a wiped data directory and reach a fresh clone."""
    import inspect

    from gaffer.cli import calibrate_decisions

    src = inspect.getsource(calibrate_decisions)
    assert "run_calibration(" in src
    assert "write_priors(" in src
    assert "src/gaffer/assets/decision_priors.json" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calibrate_decisions.py -k phase_bounds -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.calibrate_decisions'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/calibrate_decisions.py`:

```python
"""Offline calibration for the v4c decision tables.

Both the free-transfer shadow price and the chip stopping thresholds need to
know the *shape* of the opportunities a season offers: how much a single
transfer is typically worth in a given week, and how much each chip is
typically worth. Neither is guessable — the difference between a 1.5-point and
a 4-point median transfer surplus changes every λ in the table — and both are
stable enough to compute once a season rather than once a week.

So they are replayed offline. The distributions and the two tables derived from
them ship as ``assets/decision_priors.json``, in git, so a fresh clone decides
sensibly without ever running this. Spec §7.

This module is deliberately isolated from the advise path: nothing in
``advise.py`` imports it, and it does no work at import time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer.optimize.milp import SolveInput, solve_plan

PHASE_BOUNDS = {"early": (1, 12), "mid": (13, 25), "late": (26, 38)}
"""Season thirds.

Coarse on purpose. A per-week transfer-surplus distribution would be thirty-
eight samples per season deep, which is noise; thirds are twelve times denser
and the real variation — early-season churn, mid-season fixture swings,
late-season settling — happens on roughly that scale anyway.
"""

CHIPS = ("wildcard", "bboost", "3xc", "freehit")

ASSET_PATH = Path("src/gaffer/assets/decision_priors.json")

REQUIRED_KEYS = ("version", "generated_at", "seasons", "transfer_surplus",
                 "chip_surplus")


def phase_of(gw: int) -> str:
    """Which season third a gameweek belongs to, clamped at both ends."""
    for name, (lo, hi) in PHASE_BOUNDS.items():
        if lo <= gw <= hi:
            return name
    return "early" if gw < PHASE_BOUNDS["early"][0] else "late"


def best_single_transfer(pool: pd.DataFrame, state: SolveInput,
                         **solve_cfg) -> float:
    """EP gain from the best one-transfer move, over making none.

    This is the surplus draw the λ DP consumes: "if I spend a free transfer
    this week, what do I get". Measured as the difference between the
    one-transfer optimum and the no-transfer optimum on the same board, so it
    is a *marginal* number and cannot be inflated by the squad simply being
    good.

    Floored at zero. Nobody is forced to transfer, so a negative surplus is
    not a thing that can happen to a manager; letting one into the DP would
    teach it that transfers are a liability.
    """
    from gaffer.optimize.milp import FixedMoves

    held = solve_plan(pool, state, **solve_cfg,
                      fixed_moves=FixedMoves(no_transfer=True))
    spent = solve_plan(pool, state, **solve_cfg)
    gain = (spent.gw_plans[0].expected_pts - held.gw_plans[0].expected_pts)
    return max(0.0, float(gain))


def walk_season(season: str, start_gw: int = 5,
                horizon: int = 1) -> tuple[list[dict], list[dict]]:
    """One season's per-week transfer and chip surpluses.

    Reuses the backtest's own weekly loop rather than duplicating it: the
    replay already builds the pool, the EP matrix and a legal squad for every
    gameweek, and re-implementing that here would guarantee the calibration
    and the replay eventually disagree about what a week looks like.

    Returns ``([{gw, surplus}], [{gw, chip, gain}])``.
    """
    import gaffer.backtest as bt
    from gaffer.optimize.chips import evaluate_chips

    transfers: list[dict] = []
    chips: list[dict] = []
    real_solve = bt.solve_plan

    def observing_solve(pool, state, **kw):
        plan = real_solve(pool, state, **kw)
        if state.owned_codes:
            one_ft = SolveInput(
                owned_codes=list(state.owned_codes), bank=state.bank,
                free_transfers=1, gws=list(state.gws))
            try:
                transfers.append({
                    "gw": int(state.gws[0]),
                    "surplus": best_single_transfer(pool, one_ft, **kw)})
                table = evaluate_chips(pool, state, list(CHIPS), **kw)
                for r in table.itertuples():
                    if int(r.gw) == int(state.gws[0]):
                        chips.append({"gw": int(r.gw), "chip": str(r.chip),
                                      "gain": float(r.gain)})
            except Exception as exc:  # noqa: BLE001
                print(f"calibration: skipping GW{state.gws[0]} ({exc})")
        return plan

    bt.solve_plan = observing_solve
    try:
        bt.run_backtest(season=season, start_gw=start_gw, horizon=horizon)
    finally:
        bt.solve_plan = real_solve
    return transfers, chips


def run_calibration(seasons: list[str], start_gw: int = 5) -> dict:
    """Replay every season and assemble the priors payload.

    A season that cannot be replayed is skipped with a printed line and drops
    out of ``seasons``: the archive does not go back forever, and a five-season
    calibration must not die on the one with no history.
    """
    transfer_surplus: dict[str, list[float]] = {p: [] for p in PHASE_BOUNDS}
    chip_surplus: dict[str, dict[str, list[float]]] = {c: {} for c in CHIPS}
    used: list[str] = []
    for season in seasons:
        try:
            weeks, chips = walk_season(season, start_gw=start_gw)
        except Exception as exc:  # noqa: BLE001
            print(f"calibration: cannot replay {season} ({exc})")
            continue
        used.append(season)
        for row in weeks:
            transfer_surplus[phase_of(int(row["gw"]))].append(
                float(row["surplus"]))
        for row in chips:
            chip = str(row["chip"])
            key = str(int(row["gw"]))
            chip_surplus.setdefault(chip, {}).setdefault(key, []).append(
                float(row["gain"]))
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": used,
        "transfer_surplus": transfer_surplus,
        "chip_surplus": chip_surplus,
    }


def write_priors(payload: dict, path: Path | str = ASSET_PATH) -> Path:
    """Validate and write the asset.

    Validated before writing because a half-populated priors file is worse
    than none at all: an empty transfer distribution builds a λ table of
    zeroes, which tells the objective that banked transfers are worthless and
    every hit is worth taking. An absent file degrades honestly; a hollow one
    degrades silently.
    """
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(
            f"decision priors payload is missing {missing} — refusing to "
            "write a partial asset")
    pooled = [s for samples in payload["transfer_surplus"].values()
              for s in samples]
    if not pooled:
        raise ValueError(
            "decision priors carry no transfer surplus samples — a lambda "
            "table built from this would price every free transfer at zero")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
```

Add the command to `src/gaffer/cli.py`, after `backtest`:

```python
@app.command("calibrate-decisions")
def calibrate_decisions(start_gw: int = 5):
    """Replay past seasons to rebuild src/gaffer/assets/decision_priors.json.

    Slow (one backtest per season) and refreshed rarely — once a season, or
    when the model shifts materially. The asset it writes ships in git.
    """
    from gaffer.calibrate_decisions import (ASSET_PATH, run_calibration,
                                            write_priors)
    from gaffer.config import load_config

    cfg = load_config()
    payload = run_calibration(cfg.train_seasons, start_gw=start_gw)
    dest = write_priors(payload, "src/gaffer/assets/decision_priors.json")
    n = sum(len(v) for v in payload["transfer_surplus"].values())
    typer.echo(f"Calibrated {n} transfer-surplus samples across "
               f"{len(payload['seasons'])} seasons -> {dest}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_calibrate_decisions.py tests/test_cli.py -v`
Expected: PASS (both files)

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/calibrate_decisions.py src/gaffer/cli.py tests/test_calibrate_decisions.py tests/test_cli.py
git commit -m "feat: gaffer calibrate-decisions builds the priors asset

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 21: Consume θ_t in `chip_plan`, `advise` and the backtest

The tables exist; now the flat constants stop deciding. Three consumers:
`chip_plan` gains "threshold now" and "play iff ≥" columns, `run_advise`
resolves the λ and θ lookups from the asset, and `backtest._pick_chip` takes a
threshold callable instead of importing the constants.

**This task edits `run_advise` and `run_backtest`.** Both carry protected
source-text assertions — `run_backtest` must keep
`ep_matrix(apply_calibration(assemble_ep(`, and `run_advise` keeps all four
literals listed at the top of this plan.

**Files:**
- Modify: `src/gaffer/optimize/chips.py` (`chip_plan`)
- Modify: `src/gaffer/advise.py` (λ/θ resolution, chip block)
- Modify: `src/gaffer/backtest.py:154-173` (`_pick_chip`), `:438-460`
- Test: `tests/test_chips.py`, `tests/test_advise.py`, `tests/test_backtest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_chips.py`:

```python
# --- v4c: theta-aware chip planning ----------------------------------------

def test_chip_plan_without_thresholds_is_unchanged():
    """Rail: the default argument reproduces today's output exactly."""
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0},
        {"chip": "3xc", "gw": 8, "gain": 3.0, "per_week": 3.0}])
    assert chip_plan(table, 7) == chip_plan(table, 7, thresholds=None)


def test_chip_plan_reports_the_threshold_for_the_current_week():
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 4.5)
    assert out[0]["threshold_now"] == 4.5


def test_chip_plan_says_play_when_the_surplus_clears_the_threshold():
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 4.5)
    assert out[0]["play_now"] is True


def test_chip_plan_says_wait_when_a_better_week_is_expected():
    """The whole point: a six-point bench boost in GW7 is not enough when
    December is worth twelve."""
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 12.0)
    assert out[0]["play_now"] is False


def test_chip_plan_at_expiry_plays_on_any_positive_surplus():
    """theta is zero at expiry by construction, so nothing is stranded."""
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 19, "gain": 0.5, "per_week": 0.5}])
    out = chip_plan(table, 19, thresholds=lambda chip, gw: 0.0)
    assert out[0]["play_now"] is True


def test_chip_plan_with_no_row_for_this_week_reports_no_play_decision():
    table = pd.DataFrame([
        {"chip": "bboost", "gw": 9, "gain": 6.0, "per_week": 6.0}])
    out = chip_plan(table, 7, thresholds=lambda chip, gw: 4.0)
    assert out[0]["play_now"] is None
```

Append to `tests/test_advise.py`:

```python
def test_run_advise_resolves_the_decision_priors_before_solving():
    """lambda has to be in the solver bundle for the very first solve, or the
    raw optimum and the scenarios are priced differently."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "load_decision_priors()" in src
    assert "lambda_from_priors(" in src
    assert "chip_thresholds_from_asset(" in src
    assert (src.index("lambda_from_priors(")
            < src.index("plan = solve_plan(pool, state, **solve_kw)"))


def test_the_priors_are_switchable_off_from_config():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "cfg.decision_priors" in src


def test_run_advise_still_pins_every_protected_ordering_after_the_priors():
    """Third and final re-pin. advise.py is edited by Tasks 9, 10 and 21."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "ep_matrix(apply_calibration(assemble_ep(" in src
    assert src.index("fetch_rival_entries(") < src.index("tilt_ep(")
    assert src.index("tilt_ep(") < src.index("pool = build_pool(")
    assert "build_pool(players, pool_ep," in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]
```

Append to `tests/test_backtest.py`:

```python
# --- v4c: theta-aware chip picking -----------------------------------------

def test_pick_chip_defaults_to_the_flat_constants():
    """Rail: no thresholds argument reproduces the pre-v4c choice."""
    from gaffer.backtest import _pick_chip
    from gaffer.optimize.chips import CHIP_PLAY_THRESHOLD

    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": CHIP_PLAY_THRESHOLD + 0.1,
         "per_week": 1.0}])
    assert _pick_chip(table, 7) == "bboost"

    below = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": CHIP_PLAY_THRESHOLD - 0.1,
         "per_week": 1.0}])
    assert _pick_chip(below, 7) == ""


def test_pick_chip_honours_an_injected_threshold_lookup():
    from gaffer.backtest import _pick_chip

    table = pd.DataFrame([
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    assert _pick_chip(table, 7, thresholds=lambda c, g: 5.0) == "bboost"
    assert _pick_chip(table, 7, thresholds=lambda c, g: 7.0) == ""


def test_pick_chip_uses_a_per_chip_threshold():
    from gaffer.backtest import _pick_chip

    table = pd.DataFrame([
        {"chip": "wildcard", "gw": 7, "gain": 9.0, "per_week": 3.0},
        {"chip": "bboost", "gw": 7, "gain": 6.0, "per_week": 6.0}])
    only_bb = _pick_chip(table, 7,
                         thresholds=lambda c, g: 100.0 if c == "wildcard"
                         else 5.0)
    assert only_bb == "bboost"


def test_run_backtest_still_pins_the_calibration_seam():
    """Protected: tests/test_assemble.py asserts this literal on
    run_backtest as well as run_advise."""
    import inspect

    from gaffer.backtest import run_backtest

    assert ("ep_matrix(apply_calibration(assemble_ep("
            in inspect.getsource(run_backtest))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_chips.py -k threshold_for_the_current_week -v`
Expected: FAIL — `TypeError: chip_plan() got an unexpected keyword argument 'thresholds'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/optimize/chips.py`, extend `chip_plan`:

```python
def chip_plan(table: pd.DataFrame, now_gw: int, thresholds=None) -> list[dict]:
```

and inside the per-chip dict construction, add three keys:

```python
        # theta_t: the surplus the best remaining week is expected to offer.
        # Playing now is only right when this week beats waiting — a flat bar
        # cannot express that, which is why a five-point bench boost in
        # September used to get burned three months early.
        theta = None if thresholds is None else float(thresholds(chip, now_gw))
        play_now = None
        if theta is not None and now_gain is not None:
            play_now = bool(now_gain >= theta)
        entry["threshold_now"] = theta
        entry["play_now"] = play_now
```

(using whatever local the function already builds for each chip's dict, and its
existing `now_gain` local).

In `src/gaffer/advise.py`, resolve both lookups **before** the pool block, and
add `ft_lambda` to `solve_kw`:

```python
    # Calibrated decision tables, or the flat pre-v4c values when the asset
    # is absent or switched off. Resolved before the first solve so the raw
    # optimum and every scenario are priced identically.
    priors = load_decision_priors() if cfg.decision_priors else None
    ft_lambda = lambda_from_priors(priors)
    chip_thresholds = chip_thresholds_from_asset(
        priors, load_chip_scenarios())
```

and change the `solve_kw` line written in Task 9 to:

```python
    solve_kw = dict(opt_kw, ft_lambda=ft_lambda)
```

Then in the chip block, pass the thresholds through:

```python
    chip_table = chip_plan(evaluate_chips(pool, state, avail, **solve_kw),
                           gw, thresholds=chip_thresholds)
```

(matching whatever the existing call looks like — the change is adding
`thresholds=chip_thresholds` and switching `**opt_kw` to `**solve_kw`).

Add the imports:

```python
from gaffer.assets import load_decision_priors
from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                         load_chip_scenarios)
from gaffer.optimize.ft_value import lambda_from_priors
```

In `src/gaffer/backtest.py`, change `_pick_chip`:

```python
def _pick_chip(table: pd.DataFrame, gw: int, thresholds=None) -> str:
```

and replace the `floor = ...` line inside it with:

```python
        # thresholds is the theta_t lookup when one is calibrated; without it
        # the flat constants stand, which is the pre-v4c behaviour exactly.
        floor = (flat_thresholds()(str(r.chip), gw) if thresholds is None
                 else float(thresholds(str(r.chip), gw)))
```

with `from gaffer.optimize.chip_policy import flat_thresholds` added to the
module's imports. The `CHIP_PLAY_THRESHOLD` / `WILDCARD_RECOMMEND_THRESHOLD`
import at `:70-71` can stay — `flat_thresholds` reads the same constants and
other code may reference them.

Finally, in `run_backtest`, thread a threshold lookup into the chip pick and
the new knobs into `opt_kw`:

```python
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost,
                  ft_use_penalty=cfg.ft_use_penalty,
                  bench_curve=cfg.bench_curve)
    priors = load_decision_priors() if cfg.decision_priors else None
    opt_kw["ft_lambda"] = lambda_from_priors(priors)
    chip_thresholds = chip_thresholds_from_asset(priors)
```

and at the `_pick_chip` call site:

```python
                chip = _pick_chip(
                    evaluate_chips(pool, state, avail, **opt_kw), gw,
                    thresholds=chip_thresholds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_chips.py tests/test_advise.py tests/test_backtest.py -v`
Expected: PASS (all three files)

Run: `uv run pytest tests/test_assemble.py tests/test_odds.py -v`
Expected: PASS — the other protected suites

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/chips.py src/gaffer/advise.py src/gaffer/backtest.py tests/test_chips.py tests/test_advise.py tests/test_backtest.py
git commit -m "feat: time chips against theta_t instead of a flat bar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 22: `run_backtest(chips=True)` — the D3 prerequisite, verified and closed

Spec §9 states the backtest "has been chip-free since v1" and asks this cycle
to add chip play to the replay harness. **That is not what the tree shows.**
`run_backtest` already takes `chips: bool = False` and implements all four
chips (`backtest.py:450-500`), and `gaffer backtest --chips` is wired.

So this task is not "add it" — it is "verify it is complete enough for D3 to
be a real measurement", and close the two gaps that D3's stated conditions
actually need: a chip must never be *stranded* (unplayed at expiry), and the
per-chip attribution has to be extractable from the log.

Record the spec discrepancy in the spec's §12 Outcome as part of Task 25.

**Files:**
- Modify: `src/gaffer/backtest.py` (`run_backtest` return payload)
- Test: `tests/test_backtest.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest.py`:

```python
# --- v4c: the chip replay, as D3 needs it ----------------------------------

def test_run_backtest_already_accepts_the_chips_flag():
    """Spec §9 claims the harness is chip-free; it is not. Pin the reality so
    the D3 measurement is not built on a false premise."""
    import inspect

    from gaffer.backtest import run_backtest

    sig = inspect.signature(run_backtest)
    assert sig.parameters["chips"].default is False


def test_run_backtest_reports_which_chips_went_unplayed():
    """D3's second condition — 'no chip stranded unplayed at expiry' — needs
    the replay to say so, not the reader to infer it."""
    import inspect

    from gaffer.backtest import run_backtest

    src = inspect.getsource(run_backtest)
    assert "unplayed_chips" in src


def test_unplayed_chips_of_a_replay_with_no_chips_is_every_chip_twice():
    """Both halves: four chips before GW19 and four after."""
    from gaffer.backtest import unplayed_chips

    assert unplayed_chips({}) == {"first_half": ["wildcard", "freehit",
                                                 "bboost", "3xc"],
                                  "second_half": ["wildcard", "freehit",
                                                  "bboost", "3xc"]}


def test_unplayed_chips_accounts_for_the_half_a_chip_was_played_in():
    from gaffer.backtest import unplayed_chips

    out = unplayed_chips({7: "bboost", 25: "bboost"})
    assert "bboost" not in out["first_half"]
    assert "bboost" not in out["second_half"]


def test_a_chip_played_in_one_half_is_still_available_in_the_other():
    from gaffer.backtest import unplayed_chips

    out = unplayed_chips({7: "wildcard"})
    assert "wildcard" not in out["first_half"]
    assert "wildcard" in out["second_half"]


def test_the_boundary_gameweek_counts_as_the_first_half():
    from gaffer.backtest import unplayed_chips

    assert "3xc" not in unplayed_chips({19: "3xc"})["first_half"]
    assert "3xc" in unplayed_chips({20: "3xc"})["first_half"]


def test_chip_points_are_attributable_per_chip_from_the_log():
    """D3 compares 'chip-attributed points'; the log has to carry the chip
    name on the week it was played, which it already does."""
    import pandas as pd

    log = pd.DataFrame([{"gw": 7, "points": 80, "chip": "bboost"},
                        {"gw": 8, "points": 55, "chip": ""}])
    assert log[log["chip"] == "bboost"]["points"].sum() == 80
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backtest.py -k unplayed -v`
Expected: FAIL — `ImportError: cannot import name 'unplayed_chips' from 'gaffer.backtest'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/gaffer/backtest.py`, next to `_pick_chip`:

```python
CHIP_HALVES = ("first_half", "second_half")


def unplayed_chips(played_by_gw: dict[int, str]) -> dict[str, list[str]]:
    """Chips that expired unused, per half.

    2026/27 grants two of every chip; the first set dies after GW19. A chip
    left unplayed at the end of its window is points thrown away for nothing,
    and it is exactly the failure mode a stopping threshold could introduce —
    a bar that never comes down strands the chip. theta_t comes down to zero
    at expiry by construction, and this is how the replay proves it.
    """
    from gaffer.advise import CHIPS, FIRST_HALF_LAST_GW

    first_used = {name for g, name in played_by_gw.items()
                  if g <= FIRST_HALF_LAST_GW}
    second_used = {name for g, name in played_by_gw.items()
                   if g > FIRST_HALF_LAST_GW}
    return {"first_half": [c for c in CHIPS if c not in first_used],
            "second_half": [c for c in CHIPS if c not in second_used]}
```

and extend `run_backtest`'s return dict (line ~536):

```python
    return {"season": season, "from_gw": start_gw, "total": total,
            "per_gw": per_gw, "log": log, "chips_played": played_by_gw,
            "unplayed_chips": unplayed_chips(played_by_gw)}
```

(matching the existing keys exactly; only `unplayed_chips` is new).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_backtest.py -v`
Expected: PASS (whole file)

Run: `uv run pytest`
Expected: PASS — including `tests/test_assemble.py`'s `run_backtest` literal

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/backtest.py tests/test_backtest.py
git commit -m "feat: report chips stranded unplayed at expiry in the replay

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 23: Run the calibration and sanity-check the tables

Run-and-record. This is the first time real numbers enter the priors asset, and
spec §5 sets a *qualitative* bar on the λ table that has to be checked before
D2 is even worth measuring: monotone decreasing in k, decaying in t, and in the
neighbourhood of `{2: ~2.0, 3: ~1.6, 4: ~1.3, 5: ~1.1}` early-season.

**Files:**
- Modify: `src/gaffer/assets/decision_priors.json` (written by the run)
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md` §12 Outcome

- [ ] **Step 1: Run the calibration**

Run: `caffeinate -i uv run gaffer calibrate-decisions`
Expected: `Calibrated N transfer-surplus samples across M seasons -> src/gaffer/assets/decision_priors.json`.
N should be roughly `34 × M` (one per replayed gameweek per season). This is a
multi-hour job — one full backtest per season in `[data] train_seasons`.

Record N, M and the wall-clock time.

- [ ] **Step 2: Inspect the transfer-surplus distributions**

Run:
```bash
uv run python -c "
import json
p = json.load(open('src/gaffer/assets/decision_priors.json'))
import statistics as st
for phase, s in p['transfer_surplus'].items():
    print(phase, len(s), round(st.mean(s),2), round(st.median(s),2), round(max(s),2))
"
```
Expected: three lines. Record them. A median in the 1-4 point range is
plausible; a median near zero means the observing solve never found an upgrade
and the calibration is broken — check that `best_single_transfer` is being
called with `free_transfers=1` and a non-empty squad.

- [ ] **Step 3: Inspect the λ table**

Run:
```bash
uv run python -c "
from gaffer.assets import load_decision_priors
from gaffer.optimize.ft_value import lambda_from_priors
lam = lambda_from_priors(load_decision_priors())
for t in (33, 20, 10, 3, 1):
    print(t, [round(lam(k,t),2) for k in range(1,6)])
"
```
Expected: five rows, each non-increasing left to right, and each row smaller
than the row above it.

**Spec §5's qualitative gate:** the early-season row (t ≈ 33) should read
roughly `{2: ~2.0, 3: ~1.6, 4: ~1.3, 5: ~1.1}`. Record the actual row.

- If it is monotone and decaying but the *levels* differ from the research
  numbers, that is fine — record the difference and continue.
- If it is **not** monotone in k or **not** decaying in t, the gate fails: set
  `decision_priors = false` under `[scenarios]` in `config.toml`, record the
  negative result, and skip the λ half of D2.

- [ ] **Step 4: Inspect the θ tables**

Run:
```bash
uv run python -c "
from gaffer.assets import load_decision_priors
from gaffer.optimize.chip_policy import chip_thresholds_from_asset
th = chip_thresholds_from_asset(load_decision_priors())
for chip in ('wildcard','bboost','3xc','freehit'):
    print(chip, [round(th(chip,g),2) for g in (5,10,15,19,25,30,35,38)])
"
```
Expected: for each chip, a non-increasing sequence within each half, hitting
**exactly 0.0 at GW19 and GW38**. Record all four rows. A non-zero value at
either expiry is a bug in `stopping_thresholds`, not a finding.

- [ ] **Step 5: Commit the calibrated asset**

```bash
git add src/gaffer/assets/decision_priors.json docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md
git commit -m "measure: calibrated decision priors from replay

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

The asset is the one artifact in this cycle that *is* committed. `data/`,
`reports/` and `models/` are still never staged.

---

## Task 24: Gates D2 and D3 — λ, objective craft and chip timing, measured

Run-and-record. Two gates in one task because they share a baseline replay and
the same log-reading commands.

**Gate D2:** replay with λ-priced FTs and the new objective defaults ≥ replay
with flat values; hits taken should drop or hold with the total not worse.
**Gate D3:** replay chip timing with θ_t vs the flat thresholds; chip-attributed
points not worse, and no chip stranded unplayed at expiry in any replay.

**Files:**
- Modify: `config.toml` (the objective defaults, only if D2 passes)
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md` §12 Outcome

- [ ] **Step 1: Baseline — flat everything, chips on**

Turn the priors off for the baseline. In `config.toml`, under `[scenarios]`,
set `decision_priors = false`, and confirm `[optimizer]` has no
`ft_use_penalty` or `bench_curve` and `itb_value = 0.05`.

Run: `caffeinate -i uv run gaffer backtest --season 2025-26 --start-gw 5 --horizon 3 --chips`
Expected: a dict with `total`, `chips_played` and `unplayed_chips`. Record all
three.

Run:
```bash
uv run python -c "
import pandas as pd
d = pd.read_parquet('data/live/backtest_log.parquet')
print('total', d['points'].sum(), 'hits', d['hits'].sum(), 'transfers', d['transfers'].sum())
print(d[d['chip']!='']. groupby('chip')['points'].sum().to_dict())
"
```
Expected: a totals line and a per-chip points dict. Record both.

Run: `cp data/live/backtest_log.parquet data/live/backtest_log-d2-flat.parquet`

- [ ] **Step 2: Treatment — λ, θ and the crafted objective**

In `config.toml`: set `decision_priors = true` under `[scenarios]`, and under
`[optimizer]` set

```toml
itb_value = 0.08          # O'Brien: £1m ~ +21.8 pts over half a season
ft_use_penalty = 0.2
bench_curve = [0.21, 0.06, 0.002]
```

Run: `caffeinate -i uv run gaffer backtest --season 2025-26 --start-gw 5 --horizon 3 --chips`
Expected: the same dict shape. Record `total`, `chips_played`,
`unplayed_chips`.

Run the same log-reading command as Step 1 and record its two lines.

- [ ] **Step 3: Isolate the two halves**

D2 and D3 moved together in Step 2, which is not enough to attribute either.
Run two more replays, each flipping one half back:

**λ + objective only** (flat chip thresholds): temporarily edit
`src/gaffer/backtest.py`'s `chip_thresholds = chip_thresholds_from_asset(priors)`
to `chip_thresholds = flat_thresholds()`, run the replay, record, then revert.

**θ only** (flat FT and objective): set `decision_priors = true`, remove the
three `[optimizer]` lines added in Step 2, and edit `opt_kw["ft_lambda"]` to
`LambdaLookup({})` for the run; record and revert.

Each is a full replay under `caffeinate -i`.

- [ ] **Step 4: Fill in the D2 and D3 tables**

| replay | total | hits | transfers | chip points | chips stranded |
| --- | --- | --- | --- | --- | --- |
| flat baseline | | | | | |
| λ + objective only | | | | | |
| θ only | | | | | |
| both | | | | | |

**D2 passes when** the "λ + objective only" total ≥ the flat baseline total,
**and** its hit count is ≤ the baseline's.

**D3 passes when** the "θ only" chip points ≥ the baseline chip points, **and**
`unplayed_chips` is `{"first_half": [], "second_half": []}` in that replay.

- [ ] **Step 5: Set the defaults according to the result**

- Both pass → leave `config.toml` as it stands after Step 2.
- D2 fails → remove the three `[optimizer]` lines (back to `itb_value = 0.05`,
  no penalty, no curve) and set `decision_priors = false` if the λ half is what
  regressed; record the negative result.
- D3 fails → keep the code but revert `backtest.py`'s
  `chip_thresholds_from_asset(priors)` to `flat_thresholds()` and note that the
  θ workstream ships off; record the negative result.

Spec §9's failure handling is explicit that a failing gate means "ships behind
its flag, negative result recorded" — not "keep tuning until it passes".

- [ ] **Step 6: Clean up and commit**

```bash
rm -f data/live/backtest_log-d2-flat.parquet
git add config.toml src/gaffer/backtest.py docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md
git commit -m "measure: gates D2 and D3 for lambda, objective craft and chip timing

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

Confirm `git status` shows no `data/`, `reports/` or `models/` entries staged
before committing.

---

## Task 25: The cycle's after-photo

Run-and-record. The only place spec §12's Outcome becomes complete.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md` §12 Outcome

- [ ] **Step 1: Confirm everything is green**

Run: `uv run pytest`
Expected: PASS. v4b left the suite around 620 tests; this cycle adds roughly
150, so a total below ~750 means a file was not collected.

Run (from `frontend/`): `npx vitest run`
Expected: PASS

Run (from `frontend/`): `npx tsc -b`
Expected: no output, exit 0

Run (from `frontend/`): `npm run build`
Expected: a clean build into `../src/gaffer/web/static`

- [ ] **Step 2: Confirm the degradation rail one last time**

Set `n = 0` under `[scenarios]` in `config.toml` temporarily and run:

Run: `uv run pytest tests/test_v4c_degradation.py -v`
Expected: PASS — all rails, including the byte-identical CLI block.

Restore whatever value Task 12 decided on.

- [ ] **Step 3: Confirm the protected tests never moved**

Run: `uv run pytest tests/test_assemble.py tests/test_odds.py tests/test_advise.py -v`
Expected: PASS

Run: `git log --oneline -- tests/test_assemble.py`
Expected: **no commit from this cycle**. `tests/test_odds.py` likewise. If
either was touched, the change must be reverted and the source restored to
satisfy the original literal — spec §9 lists "the three protected source-text
tests untouched" as a merge gate.

(`tests/test_advise.py` *is* edited by this plan — Tasks 9 and 21 append to it —
but only by adding tests, never by weakening the four existing ones.)

- [ ] **Step 4: One real advise run**

Run: `caffeinate -i time uv run gaffer advise`
Expected: a full advice block. With `n = 40` it should complete in **≤ ~6
minutes** (spec §9's wall-clock gate). Record the real time and confirm the
output carries the `Scenarios: N/M solved, seed S` line and the single-solve
optimum verdict.

- [ ] **Step 5: Fill in the spec's §12 Outcome**

Replace §12 of
`docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md` with:

- **D1**: the gated-vs-raw table from Task 12, the hold rate, the captain
  agreement rate, and the value `[scenarios] n` ended on.
- **D2**: the four-row replay table from Task 24, and which `[optimizer]`
  values ended in `config.toml`.
- **D3**: chip points per chip, and the `unplayed_chips` result for every
  replay.
- **The λ table**: the t ≈ 33 row against the research's expected
  `{2: ~2.0, 3: ~1.6, 4: ~1.3, 5: ~1.1}`.
- **The θ tables**: the four printed rows, confirming 0.0 at GW19 and GW38.
- **Calibration counts**: samples per phase, seasons that replayed, seasons
  that were skipped.
- **Wall clock**: `gaffer advise` at the chosen `n`.
- **The spec correction**: §9 claimed the backtest has been chip-free since v1.
  It has not — `run_backtest(chips=True)` and all four chips were already
  implemented (`backtest.py:450-500`). What this cycle added was chip-expiry
  reporting (`unplayed_chips`) and threshold injection. Record this so the next
  cycle does not re-plan work that exists.
- **Anything shipped off**: every workstream whose gate failed, with its flag
  and its measured numbers.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-08-25-gaffer-v4c-decide-design.md config.toml
git commit -m "measure: v4c outcome tables for D1-D3

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Execution Notes

- **Python tests:** `uv run pytest` from the repo root. A single file:
  `uv run pytest tests/test_scenarios.py -v`.
- **Frontend:** `npx vitest run`, `npx tsc -b` and `npm run build` from
  `frontend/` (not `web/` — the repo has no `web/` directory; the API server is
  `src/gaffer/web/` and the SPA is `frontend/`). Only Task 11 changes frontend
  source. Never stage `src/gaffer/web/static/`.
- **The full suite must be green before every commit**, not just the file you
  touched.
- **Long runs go under `caffeinate -i`.** Every real measurement in this cycle
  is a multi-hour replay: Task 12's gated replay is 34 gameweeks × 41 solves,
  Task 20's calibration is one backtest per training season, Task 24 is four
  full replays. None of the *coding* tasks need a real run — every test is
  fixture-driven — so the real runs live in Tasks 12, 23, 24 and 25 only.
- **No network in tests, ever.** Nothing in this cycle fetches anything: the
  scenario, DP and threshold code is pure computation, and the calibrator is
  driven by monkeypatched walks in its tests. If a test in this plan would open
  a socket, it is a bug. Where a future test needs HTTP, use
  `httpx.MockTransport` as `tests/test_odds.py` does.
- **Never touch `.claude/`.** It is untracked and must stay untracked.
  `git add -A` and `git add .` are forbidden anywhere in this plan; every
  commit step lists its files explicitly. `data/`, `reports/` and `models/` are
  never staged — the single exception is
  `src/gaffer/assets/decision_priors.json`, which lives in the package, not in
  `data/`, and is committed deliberately in Task 23.
- **Protected source-text tests.** `tests/test_assemble.py`, `tests/test_odds.py`
  and `tests/test_advise.py` assert on the *source text* of `run_advise`,
  `run_backtest` and `predict_components`. The full list is at the top of this
  plan. Tasks 9, 10, 21 and 22 all edit those functions and each ends by running
  the whole suite for exactly this reason. If one fails, the fix is to restore
  the literal, never to relax the test.
- **The `pool_ep` trap.** `tests/test_advise.py:97` asserts
  `"pool_ep" not in src[src.index("ep_gw1 ="):]`. Everything this plan inserts
  into `run_advise` sits before `ep_gw1 =` and never names `pool_ep`. The
  scenario layer takes the `pool` **frame**, whose `ep` column already carries
  the tilted values.
- **The canonical `solve_plan` signature.** It grows across Tasks 6, 14 and 16
  and ends as:

  ```python
  def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
                 bench_weight: float, vice_weight: float, ft_value: float,
                 itb_value: float, hit_cost: int,
                 fixed_moves: FixedMoves | None = None,
                 ft_lambda: "LambdaLookup | None" = None,
                 ft_use_penalty: float = 0.0,
                 bench_curve: list[float] | None = None) -> Plan:
  ```

  Every one of the four new arguments is keyword-only with a default that
  reproduces the pre-v4c objective exactly. `chips.py`'s `**cfg` bundles and
  `advise.py`'s `solve_kw` both pass straight through, so a new argument reaches
  the chip helpers for free — which is why `wildcard_now_assessment` reads
  `ft_lambda` out of `cfg` rather than taking a parameter.
- **`opt_kw` vs `solve_kw`.** `opt_kw` stays JSON-serializable because it is
  written into `SolveState.opt` and read back by the What-If page. `solve_kw`
  is `dict(opt_kw, ft_lambda=...)` and is what actually reaches the solver. Do
  not put a callable in `opt_kw`.
- **Degradation is the default everywhere.** `[scenarios] n = 0`, an absent or
  empty `decision_priors.json`, `bench_curve = None`, `ft_use_penalty = 0.0`,
  and an absent `data/chip_scenarios.toml` each independently reproduce
  pre-v4c behaviour, and each has a test that says so. The gate tasks are the
  only place a default flips.
- **Ordering.** Tasks 1-2 come first and everything depends on them. Tasks 3-5
  are independent of 6, and 7 needs 5, and 8 needs 6+7. Task 9 needs 3-8; 10
  needs 9; 11 needs 10. Task 12 measures 3-11. Tasks 13, 17 and 18 are
  independent of the scenario chain and can be worked in parallel with it if
  two workers are available. Task 14 needs 13; 15 needs 13+14; 16 is
  independent of 13-15. Task 19 needs 13+17. Task 20 needs 19 and Task 6's
  `FixedMoves`. Task 21 needs 19+20. Task 22 is independent of everything after
  Task 1. Tasks 23-25 need all of it.

---

## Self-review

### Spec coverage

| Spec section | Covered by |
| --- | --- |
| §3 noise, xmins formula, `noise_ep` | Task 3 |
| §3 `run_scenarios`, N=40, seed, dropped scenarios | Task 4 |
| §3 `move_frequencies`, move kinds, double moves | Task 5 |
| §3 deterministic solve kept as anchor and fallback | Tasks 2, 9 |
| §4 `decide()`, 60%/75% thresholds, captain plurality | Task 7 |
| §4 hold fallback with near misses | Task 7 |
| §4 coherence re-solve, `fixed_moves` on `solve_plan` | Tasks 6, 8 |
| §4 CLI report: frequencies in, raw optimum demoted | Task 10 |
| §4 web frequency column + API fields | Task 11 |
| §5 λ(k,t) DP, cap-5 overflow, value iteration | Task 13 |
| §5 `ft_lambda` replacing flat `ft_value` in the objective | Task 14 |
| §5 hit rule via λ-priced banked FTs | Task 14 (emergent from the objective) |
| §5 wildcard subtracts the FT bank it destroys | Task 15 |
| §5 λ table shape, shipped as an asset | Tasks 19, 23 |
| §6 θ_t backward recursion, per chip half | Task 17 |
| §6 play rule replacing the flat constants | Task 21 |
| §6 `data/chip_scenarios.toml` hook | Tasks 17 (impl), 18 (coverage) |
| §6 chip table "threshold now" / "play iff ≥" columns | Tasks 10, 21 |
| §7 `gaffer calibrate-decisions`, both distributions | Task 20 |
| §7 asset ships in git; absent → flat | Tasks 19, 20 |
| §8 convex bench weights {0.21, 0.06, 0.002} | Task 16 |
| §8 `itb_value` 0.05 → 0.08 | Task 24 (flipped at the gate) |
| §8 `ft_use_penalty = 0.2` | Tasks 16 (knob), 24 (flipped at the gate) |
| §9 Gate D1 | Task 12 |
| §9 Gate D2 | Task 24 |
| §9 Gate D3 + `run_backtest(chips=True)` prerequisite | Tasks 22, 24 |
| §9 wall-clock ≤ ~6 min | Tasks 12, 25 |
| §9 protected tests untouched; n=0 byte-identical | Tasks 2, 25 |
| §9 failure handling: ship behind the flag | Tasks 12, 23, 24 |
| §11 testing strategy (units + degradation rails) | every task |
| §12 Outcome | Task 25 |
| §10 not-in-cycle items | respected: no DGW data, no EO captaincy, no correlated noise, no bench-order modelling |
| Config additions `[scenarios]` etc. | Task 1 |

### Placeholder scan

Searched the plan for `TBD`, `similar to Task`, `...`, `<fill in>` and
`# implementation here`. The only ellipses are inside quoted docstrings and the
`§12 Outcome` tables that Tasks 12/23/24/25 exist to fill — those are
measurement outputs, not placeholders. Every code block is complete and
runnable as written. Task 18's Step 3 is conditional ("only if a case failed")
by design: it is a coverage task for a hook implemented in Task 17, and it says
so explicitly rather than inventing work.

### Type and signature consistency

- `solve_plan` — the four added arguments are introduced in Tasks 6, 14, 16 and
  the canonical final form is quoted in Task 16 and again in the Execution
  Notes. Checked: identical spelling, order and defaults in all four places.
- `FixedMoves(buys, sells, gw, no_transfer)` — same field names in Task 6
  (definition), Task 8 (`coherent_plan`), Task 20 (`best_single_transfer`).
- `LambdaLookup` — `__call__(k, t)`, `.empty`, `.bank_value(k, t)`. Used with
  those exact members in Tasks 13, 14, 15, 19.
- `ft_lambda` reaches `wildcard_now_assessment` through `**cfg`
  (`cfg.get("ft_lambda")`), never as a named parameter — consistent between
  Task 15's implementation and its tests.
- The threshold lookup is a `(chip: str, gw: int) -> float` callable
  everywhere: `flat_thresholds()`, `thresholds_from_priors()`,
  `chip_thresholds_from_asset()`, `chip_plan(..., thresholds=)`,
  `_pick_chip(..., thresholds=)`.
- `move_frequencies` schema `FREQ_COLUMNS = (kind, code, gw, label, count,
  frequency)` — the same six names in Task 5, Task 7's `_freq` helper, Task 11's
  `MoveFrequency` TS interface, and Task 11's API test.
- `ScenarioRun(plans, attempted, completed, failures, seed)` — Task 4's
  definition matches Task 9's consumption field for field.
- `Advice`'s three new fields (`move_frequencies: list[dict]`,
  `raw_optimum_agrees: bool | None`, `scenarios: dict | None`) match between
  Task 9, Task 10's CLI reads, and Task 11's TS types.
- `SEASON_LAST_GW = 38` is defined in both `milp.py` (Task 14) and
  `chip_policy.py` (Task 17) rather than imported across, because neither
  module may import `advise`. Deliberate duplication, documented at both sites.
