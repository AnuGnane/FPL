# Gaffer v7-model "Zeros, honest noise, first news verdict" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two measurable model gaps the 2026-08-29 evaluation named. First, the **zeros stratum** — RMSE 1.063 against OpenFPL's 0.818, and worse than the naive last-5 baseline's 1.042 — diagnosed by sub-population and then attacked with an isotonic recalibration of the minutes model's DNP-mode probability, built leak-free and shipped OFF behind a flag until gate Z1 passes. Second, **estimation-only σ** for the scenario sweep: a K=5 seed-bagged ensemble of the minutes and attacking heads, whose spread prices how unsure the *model* is rather than how random football is, fitted offline into the existing 13-cell `scenario_noise.json` shape and measured at gate S2 through the parked opt-in serving path. Plus the first scored N2 news verdict when GW2 closes, and one deferred UI nit.

**Architecture:** Two new backend modules and one new asset shape. `src/gaffer/zeros_diagnostic.py` decomposes the evaluation harness's own holdout frame into strata (fringe, cold-start, recent-absence, p_dnp decile) and writes `reports/zeros_diagnostic.json` — a report, not a gate. `src/gaffer/models/dnp_calibrate.py` holds `DnpCalibrator` (sklearn isotonic, already a dependency) and `fit_dnp_calibrator`, an inner-split fitter modelled exactly on `train.fit_calibration`'s recursion-guarded shape. It hooks **inside `ThreeModeModel`** — `fit` learns it, `predict_modes` applies it and renormalises the trichotomy — so every caller (`predict_components_simple`, `advise.predict_components`, the backtest) gets it for free and **`advise.py` is not touched at all**. `src/gaffer/calibrate_noise.py` gains a second, parallel fitting path: `ensemble_rows` → `fit_estimation_sigmas` → `run_estimation_calibration`, emitting the same `sigma`/`obs`/`ep_marginal`/`global` payload marked `"source": "estimation"`, written through the existing `write_noise` validator. **No new serving code exists anywhere in this cycle** — the estimation table is served, when the gate says so, through v6's already-wired `CALIBRATED_NOISE_DEFAULT` / `noise_ep(..., table=)` / `recentred_mean` path. Two gate drivers land under `scripts/` beside the existing `scripts/eval_milestone.py`. The frontend change is one prop on `kit/Card.tsx` and its use in `hubs/players/ComparePanel.tsx`.

**Tech Stack:** Python 3.12, pandas, LightGBM, scikit-learn (`sklearn.isotonic.IsotonicRegression` — already in `pyproject.toml` dependencies), Typer, pytest (`.venv/bin/python -m pytest`); React 18 + TypeScript + Vite + vitest + @testing-library/react (`npm test -- --run`, `npx tsc -b`, `npm run build` from `frontend/`).

---

## Hard constraints — read before writing a line of code

1. **TDD, always.** Failing test first, minimal implementation second, both shown in every step below.
2. **Never `git add -A`.** Stage only the files each step names. Never stage `config.toml` (it carries a live odds API key), `data/`, `reports/`, `models/`, `.claude/`, `frontend/node_modules/`. `reports/` and `models/` are gitignored; `src/gaffer/assets/` is **not**, so an asset commit is deliberate and named.
3. **Protected suites are sacred.** `tests/test_advise.py` and `tests/test_odds.py` must never be edited. `src/gaffer/advise.py` is **not** edited this cycle either — see Interpretations §I-A; the calibrator hooks below it. `src/gaffer/optimize/` is read-only apart from the one-constant flip in Task 18, which changes a docstring and a boolean and nothing else.
4. **`tests/test_calibrate_noise.py`, `tests/test_minutes.py`, `tests/test_train.py`, `tests/test_scenarios.py` and `tests/test_v6_degradation.py` are not edited.** Every new assertion lands in `tests/test_zeros_diagnostic.py`, `tests/test_dnp_calibrate.py`, `tests/test_estimation_noise.py` or `tests/test_v7_model_degradation.py`. If an existing suite goes red, the change is wrong — not the suite.
5. **Degradation rails are law.** Flag off ⇒ byte-identical serving; asset absent ⇒ the pre-v6 heuristic; a model pickle with no calibrator attribute ⇒ the identity. Each is pinned by a test that would fail if the rail were removed.
6. **Gates are run by the orchestrator, never by an implementer.** Tasks 6, 11 and 16 build machinery and *stop*. Tasks 15, 17, 18, 19, 20 are orchestrator actions and are marked so. No implementer may assert a gate outcome, edit `reports/evaluation.json`, or flip a shipping constant.
7. **Frequent small commits**, one per task, each ending with these two trailers:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

Use this exact shape:

```bash
git commit -m "feat: <subject>" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

8. **Verification commands.** Backend: `.venv/bin/python -m pytest <file> -q` from the repo root. Frontend: `npm test -- --run <file>`, `npx tsc -b`, `npm run build`, all from `frontend/`.

### Post-review note — constraint 4 was breached, deliberately

Commit `3acab85` edited `tests/test_v6_degradation.py`, which constraint 4
above says is not edited and whose red suite constraint 4 says means the
change is wrong. That happened because the plan contradicted itself: Task 18
instructs, in as many words, that v6's two pins on the now-overturned default
"**must be updated in this commit**". The two clauses cannot both be obeyed
once S2 flips the constant, and Task 18 — the later, more specific
instruction, written knowing exactly which two tests it overturns — won.

The adversarial review checked the conversion rather than taking it on trust
and judged it substantively correct: the two pins were rewritten to assert the
new contract, coverage was preserved and expanded (a new flag-off rail was
added), and nothing was deleted to make a failure go away. Recorded here so
the breach is part of the record rather than something a later reader
discovers in the diff: the constraint's *intent* — a red suite means the
change is wrong, not that the suite is wrong — still stands for every other
case in this plan.

---

## Facts established by the survey (do not re-derive)

- **The 2026-08-29 baseline** (`reports/evaluation.json`, key `current`, `git_sha` `0324e03`, `holdout_slots` 10). `stratified.all`: zeros rmse **1.063** / mae 0.499 / n 4929; blanks 1.839 / n 1657; tickers 1.614 / n 417; haulers **5.145** / n 681; all **1.986** / n 7684. `baselines.last5.zeros.rmse` = **1.042**. These are the four numbers gate Z1 is written against.
- **`evaluate_current` is one fit, then a ten-slot holdout** — not a per-slot walk. `holdout_boundary(df, 10)` takes the tenth-from-last `(season_idx, gw)` slot, `train_all` fits on `before_mask` rows, `predict_components_simple` + `assemble_ep` + `apply_calibration` + `ep_matrix` score the rest. Strata are computed from `categorize(actual points)`: zeros ≤ 0, blanks 1-2, tickers 3-4, haulers 5+.
- **The holdout frame today is 2025-26 GW30-38 plus 2026-27 GW1** (`data/live/player_gw.parquet` holds GW1 only, 610 rows, `season_idx` 4; history holds 2022-23 → 2025-26 as `season_idx` 0-3).
- **`MINUTES_FEATURES`** = `minutes_r{1,3,5,10}`, `starts_r{1,3,5,10}`, `days_rest`, `home` + `ROTATION_FEATURES` (`season_start_share`, `days_since_last_start`, `sub_streak`). `season_start_share` is the mean of `starts` over this season's *earlier* matches, shifted — so it is leakage-safe and is the fringe stratum's definition.
- **`ThreeModeModel`** holds `mode_clf` (multiclass over `{0 DNP, 1 sub, 2 start}`), `sixty_clf`, `min_start`, `min_sub`, and `modes_seen`. `predict_modes(df)` returns a `["p_dnp","p_sub","p_start"]` frame; `predict` derives `p_play = p_start + p_sub`, `p60 = p_start * P(60+|start)`, `e_min`. `_binary`/`_regressor` are `@staticmethod`s reading the module-level `LGB_KW` (`n_estimators=300, learning_rate=0.05, num_leaves=31, verbose=-1, random_state=7`). `_ConstantHead` covers single-class slices.
- **`AttackingModel.fit`** constructs `LGBMRegressor(**LGB_KW)` per (position group, target), importing `LGB_KW` from `gaffer.models.minutes`. So one seed constant governs both heads.
- **`apply_availability` is a prediction-time override applied to `mp` (p_play/p60/e_min) after `minutes.predict`** — in `advise.predict_components` at `mp = apply_availability(mp, avail ...)`. A calibrator inside `predict_modes` therefore runs strictly *before* availability, which is correct: live news must still win.
- **The existing calibration layer is `models/calibrate.py::CalibrationModel`** — an additive per-position delta scaled by `p60`, **not** a probability calibrator. Its docstring records that isotonic was tried at gate A on *assembled EP* and failed (plateaus, ties, `captain_pts` 5.33 → 3.67). That failure was about EP ranking; it says nothing about isotonic on a probability. See Interpretations §I-B.
- **`train.fit_calibration` is the recursion-guard pattern to copy**: it splits the last `CALIBRATION_HOLDOUT_GWS = 10` slots off, calls `train_all(..., _fit_cal=False)` on the rows strictly before them, predicts the holdout, and fits on those genuinely out-of-sample predictions.
- **The σ table's shape** (`src/gaffer/calibrate_noise.py`): `EP_EDGES = [0,2,3,4,6]`, `XMINS_EDGES = [0,30,60,80]`, `MIN_CELL_OBS = 100`, `SIGMA_MAX = 10.0`, `REQUIRED_KEYS = ("version","generated_at","season","ep_edges","xmins_edges","sigma","obs","ep_marginal","global")`. `fit_sigmas` emits `sigma` (cells with ≥ `min_obs`), `obs` (every cell), `ep_marginal`, `ep_marginal_obs`, `global`, `rows`, `min_cell_obs`. `write_noise` validates every σ is finite, `> 0` and `< SIGMA_MAX`, and refuses a payload with no σ at all. The shipped v6 asset has 13 populated cells, `global` 0.8284…4.9804, `rows` 26919, `season` "2024-25".
- **Serving reads the edges out of the payload**, not out of the module constants (`sigma_for` → `table["ep_edges"]`), and pools cell → `ep_marginal[str(i)]` → `global` → `None` (heuristic). `SIGMA_MAX` and non-positive σ both fall through to the heuristic.
- **`CALIBRATED_NOISE_DEFAULT = False`** in `optimize/scenarios.py`. With it off, `scenario_noise()` returns `None` **without reading the file**, and `noise_ep(table=None)` is the pre-v6 heuristic value-for-value. `run_scenarios` → `noised_pool(pool, xmins, rng)` passes **no** table, so it resolves through `scenario_noise()` — which is why the S2 driver flips the constant and stubs `load_scenario_noise` rather than threading a `table=` kwarg (Task 11).
- **`scripts/` exists and already carries a Python driver** (`scripts/eval_milestone.py`, plus two plists and an installer shell script) and is tracked in git. `tools/` does not exist. The gate drivers therefore land in `scripts/`.
- **`.gitignore` covers `reports/`, `models/*.joblib`, `data/history/`, `data/live/`, `config.toml`, `.claude/`.** `src/gaffer/assets/*.json` is tracked.
- **The advice artifact's sim-support number** is `advice["scenarios"]["captain_frequency"]` (written in `advise.py` at the `scenario_report` dict), persisted to `reports/gw{N}-advice.json`.
- **`kit/Card.tsx`** takes `{title?, action?, children, className?}` and renders `<h2 className="label">{title}</h2>` inside a header row when `title || action`. `hubs/players/ComparePanel.tsx` renders one `<Card title={player.name} action={<PosBadge pos={player.position} />}>` per compared player — which is why the name currently reads as a 9px uppercase label.
- **vitest style** is `render` + `screen` from `@testing-library/react`, `describe`/`it` from vitest; `Card.test.tsx` asserts through `getByRole('heading', { name })` and `container.firstChild` classes.

---

## Interpretations — spec gaps resolved here (do not relitigate)

- **§I-A — where the I1 calibrator hooks: inside `ThreeModeModel`, not in `advise.py`.** The spec permits a minimal `advise.py` insertion; it is not needed and is therefore not taken. `advise.predict_components` calls `load_model("minutes").predict(pf)`, and `predict_components_simple` calls `models["minutes"].predict(rows)` — both reach `predict_modes`. Putting the calibrator on the fitted model means the weekly refit, the evaluation harness, the backtest and the live advice all get identical treatment with **zero** source-text change to `advise.py`, so every protected `run_advise` ordering pin and the `"pool_ep"` substring rule hold trivially. It also makes the calibrator part of the joblib, so a stale `models/minutes.joblib` degrades to the identity via `getattr(self, "dnp_cal", None)`.
- **§I-B — isotonic, not Platt.** The spec says "whichever the existing calibration layer uses". The existing layer uses *neither* — it is an additive per-position EP delta. `scikit-learn>=1.5` is already a hard dependency, so `IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")` is chosen: it is non-parametric, monotone (so it cannot reorder two players' DNP risk) and is what the module docstring's own rejected experiment used at a different layer. The gate-A failure mode (plateaus creating ties in the EP ranking) does not apply: a plateau in `p_dnp` still multiplies through three attacking heads and a scoring table before it reaches an EP ordering.
- **§I-C — I2 is INFEASIBLE and is not attempted.** Spec §2.2 makes it conditional on the bench-unused/not-in-squad distinction being derivable from stored data. It is not. `data/history/player_gw.parquet` and `data/live/player_gw.parquet` carry a row for **every registered element every gameweek** — 2025-26 GW10 has 747 rows across 20 teams (29-45 per club, i.e. the full registered squad, not a 20-man matchday list), of which 444 have `minutes == 0` and *all* of those carry `bps = 0`, `starts = 0`, `cs = 0`, `gc = 0`. There is no column that separates an unused substitute from a player who was never named. That also kills the second proposed feature: `squad_share_r5` would be identically 1.0 for every player, because every player has a row every week. Spec §2.2 forbids scraping anything new for it, so **I2 is recorded infeasible in §9 and no task is planned for it**. This cycle attempts exactly one intervention, I1.
- **§I-D — the diagnostic's "flagged vs unflagged" stratum is not derivable either, and is reported as such rather than faked.** Official status (`i/s/u/n/d`) is a *live* bootstrap field; the historical frame has no status column, and the only banked snapshots (`reports/availability_gw2.parquet`, `gw3.parquet`) are 2026-27 GW2/GW3, which are not in the training frame at all (live data stops at GW1). Task 2 therefore emits `strata.flagged = {"n": 0, "note": "no availability snapshot covers the holdout slots"}` and substitutes a derivable proxy, **`recent_absence`** (`minutes_r5 == 0` vs `> 0`), which answers the same question — "was he already visibly out of the picture?" — from leakage-safe stored features. The stratum becomes real for free once availability snapshots accumulate over slots that enter the holdout; the builder reads whatever snapshots exist.
- **§I-E — the estimation fit's frame is the 2025-26 season as a held-out test season**, via `benchmark_split(df, max_train_idx=2, test_idx=3)` — train on 2022-23…2024-25, walk every gameweek of 2025-26. This is literally "the 2025-26 walk-forward" the spec asks for, it reuses `residual_rows`' own already-parameterised split helper verbatim, and it yields ~29 700 candidate rows against the ~7 700 a ten-slot holdout would give — enough to populate the 13 cells at `MIN_CELL_OBS = 100`. Scoring is the **unrestated** current table: 2025-26 did award defensive contribution, so `benchmark_scoring`'s 2024-25 restatement must not be applied here.
- **§I-F — K=5 means the shipped fit plus four reseeded siblings.** `ESTIMATION_SEEDS = (7, 17, 27, 37, 47)` and `seeds[0]` is asserted equal to `minutes.LGB_KW["random_state"]`, so member 0 *is* the base bundle and is not refit. Only `minutes` and `attacking` are reseeded (spec §3's wording); the Dixon-Coles team head is a deterministic MLE with no seed, and `calibration` is shared, so the ensemble prices exactly the LightGBM estimation spread and nothing else. Cost: one `train_all` plus four pairs of head fits, not five full refits.
- **§I-G — a cell whose ensemble σ rounds to 0.0000 is omitted, not floored.** `write_noise` refuses a non-positive σ, and inventing `1e-4` to get past it would be a lie about a cell where the five refits genuinely agree. Such cells are dropped from `sigma` (recorded as `dropped_zero_cells`) and pool up to the EP marginal, exactly as a thin cell does. If `global` itself rounds to zero the asset is refused outright and S2 is recorded as unrunnable — which is itself the finding.
- **§I-H — the estimation asset supersedes `scenario_noise.json` either way.** Spec §3 says the v6 residual asset is superseded pass or fail. The fitter's `--out` defaults to `ASSET_PATH`; during the gate the orchestrator fits to `reports/scenario_noise_estimation.json` (gitignored) so nothing is clobbered before the verdict, and Task 18 copies it into `src/gaffer/assets/scenario_noise.json` in the same commit that either flips `CALIBRATED_NOISE_DEFAULT` (pass) or restates its docstring with the S2 negative result (fail). `test_the_fitted_asset_is_present_and_well_shaped` in `tests/test_v6_degradation.py` keeps passing unedited, because the shape is identical.
- **§I-I — the S2 driver is committed, not left in the scratchpad.** `scripts/` is a tracked directory that already holds a Python driver, so committing `scripts/s2_replay.py` contradicts no convention and makes the gate reproducible after the session ends. It is the scratchpad `s1b_driver.py` with three changes: the arm names become `heur`/`estimation`, the calibrated arm takes a payload path on `argv[2]` and installs it through `CALIBRATED_NOISE_DEFAULT` + a stubbed `load_scenario_noise` (which is exactly the shipping path, so the gate measures what shipping would do), and the printed key becomes `S2_ARM_DONE`. `scripts/z1_arms.py` joins it as Z1's driver.
- **§J — the I1 flag ships OFF via a module constant, not asset absence.** `minutes.DNP_CALIBRATION_DEFAULT = False` gates the *fitting* as well as the serving, so with it off `ThreeModeModel.fit` does not even pay for the inner refit and `predict_modes` is byte-identical. The Z1 driver flips the module attribute in-process to build the treated arm — the same technique `tests/test_v6_degradation.py` uses on `CALIBRATED_NOISE_DEFAULT`.
- **§K — N2 is a conditional orchestrator action, not implementer work.** No code changes: `gaffer evaluate --news-shadow` and `evaluate_news_shadow()` already exist and already filter the banked log to `cfg.current_season`. Task 19 is a checklist.

---

## File Structure

**Created — backend:**

| Path | Responsibility |
| --- | --- |
| `src/gaffer/zeros_diagnostic.py` | `ZERO_STRATA`, `stratify`, `dnp_reliability`, `zeros_report`, `DIAGNOSTIC_PATH`, `save_diagnostic`, `format_diagnostic`. |
| `src/gaffer/models/dnp_calibrate.py` | `DNP_MIN_ROWS`, `DNP_HOLDOUT_SLOTS`, `DnpCalibrator`, `fit_dnp_calibrator`. |
| `scripts/z1_arms.py` | Gate Z1's two-arm driver over one memoised training frame. |
| `scripts/s2_replay.py` | Gate S2's gated-replay driver, `heur` / `estimation` arms. |
| `tests/test_zeros_diagnostic.py` | The decomposition helpers on synthetic frames. |
| `tests/test_dnp_calibrate.py` | The calibrator, the renormalisation, and the walk-forward leakage rail. |
| `tests/test_estimation_noise.py` | The seed seam, the ensemble σ builder, the estimation cell fitter. |
| `tests/test_v7_model_degradation.py` | Every v7-model rail restated in one place. |

**Modified:**

| Path | Change |
| --- | --- |
| `src/gaffer/models/minutes.py` | `DNP_CALIBRATION_DEFAULT`, `seed`/`_fit_dnp` on `__init__`, `lgb_kw`, `_binary`/`_regressor` become instance methods, `dnp_cal` fitted in `fit` and applied in `predict_modes` (Tasks 5, 7). |
| `src/gaffer/models/attacking.py` | `AttackingModel(feature_cols, seed=None)` (Task 7). |
| `src/gaffer/calibrate_noise.py` | `ESTIMATION_SEEDS`, `_seeded_bundle`, `ensemble_rows`, `fit_estimation_sigmas`, `run_estimation_calibration`; `"source"` on both payloads (Tasks 8, 9, 10). |
| `src/gaffer/cli.py` | `diagnose-zeros` command (Task 2); `calibrate-noise --estimation --out` (Task 10). |
| `frontend/src/kit/Card.tsx` | Optional `titleSize?: 'sm' \| 'lg'` (Task 12). |
| `frontend/src/hubs/players/ComparePanel.tsx` | Per-player card uses `titleSize="lg"` (Task 13). |
| `src/gaffer/optimize/scenarios.py` | **Orchestrator only, Task 18**: `CALIBRATED_NOISE_DEFAULT` + docstring. |
| `src/gaffer/assets/scenario_noise.json` | **Orchestrator only, Task 18**: replaced by the estimation payload. |
| `docs/superpowers/specs/2026-08-30-gaffer-v7-model-design.md` | **Orchestrator only, Task 20**: §9 outcome. |
| `README.md` | **Orchestrator only, Task 20**: v7-model line. |

**Deleted:** nothing.

---

## Group 1 — M1: the zeros diagnostic and the DNP recalibrator (Tasks 1-6)

One implementer owns this group. Nothing here touches `advise.py`, the optimizer, or the noise machinery. When it is done, the diagnostic runs, the calibrator exists, it is off by default, and gate Z1 has a driver — but no gate has been run and no default has been flipped.

### Task 1 — the stratifiers

- [ ] **Write the failing test** `tests/test_zeros_diagnostic.py`:

```python
import numpy as np
import pandas as pd

from gaffer.zeros_diagnostic import (ZERO_STRATA, dnp_reliability, stratify,
                                     zeros_report)


def _scored() -> pd.DataFrame:
    """One row per (code, gw): what the harness has after its merge."""
    return pd.DataFrame([
        # fringe, cold start, absent for five, actually a zero
        {"code": 1, "gw": 1, "ep": 1.4, "total_points": 0, "minutes": 0,
         "season_start_share": 0.0, "minutes_r5": 0.0, "p_dnp": 0.55},
        # regular, mid-season, absent recently, a zero
        {"code": 2, "gw": 20, "ep": 3.1, "total_points": 0, "minutes": 0,
         "season_start_share": 0.9, "minutes_r5": 0.0, "p_dnp": 0.20},
        # regular, mid-season, playing, a hauler
        {"code": 3, "gw": 20, "ep": 5.0, "total_points": 9, "minutes": 90,
         "season_start_share": 0.95, "minutes_r5": 88.0, "p_dnp": 0.05},
        # fringe, mid-season, playing, a blank
        {"code": 4, "gw": 20, "ep": 2.0, "total_points": 2, "minutes": 30,
         "season_start_share": 0.1, "minutes_r5": 12.0, "p_dnp": 0.45},
    ])


def test_every_documented_stratum_is_produced():
    out = stratify(_scored())
    assert set(out) == set(ZERO_STRATA)


def test_the_fringe_cut_is_the_season_start_share_threshold():
    out = stratify(_scored())
    assert sorted(out["fringe"]["code"]) == [1, 4]
    assert sorted(out["regular"]["code"]) == [2, 3]


def test_the_cold_start_cut_is_the_first_four_gameweeks():
    out = stratify(_scored())
    assert sorted(out["cold_start"]["code"]) == [1]
    assert sorted(out["settled"]["code"]) == [2, 3, 4]


def test_recent_absence_stands_in_for_the_official_flag():
    out = stratify(_scored())
    assert sorted(out["recent_absence"]["code"]) == [1, 2]
    assert sorted(out["recent_presence"]["code"]) == [3, 4]


def test_a_missing_feature_column_leaves_its_strata_empty_not_crashed():
    frame = _scored().drop(columns=["season_start_share"])
    out = stratify(frame)
    assert out["fringe"].empty and out["regular"].empty
    assert not out["settled"].empty


def test_dnp_reliability_bins_predicted_against_observed():
    frame = pd.DataFrame({
        "p_dnp": np.concatenate([np.full(50, 0.05), np.full(50, 0.95)]),
        "minutes": np.concatenate([np.zeros(5), np.full(45, 90.0),
                                   np.zeros(45), np.full(5, 90.0)]),
    })
    curve = dnp_reliability(frame, bins=10)
    assert [row["decile"] for row in curve] == [0, 9]
    assert curve[0]["pred"] == 0.05 and curve[0]["obs"] == 0.1
    assert curve[1]["pred"] == 0.95 and curve[1]["obs"] == 0.9
    assert curve[0]["n"] == 50


def test_zeros_report_scores_each_stratum_on_the_zeros_rows_only():
    payload = zeros_report(_scored())
    zeros = payload["strata"]["fringe"]
    assert zeros["n"] == 1                       # only code 1 is a zero
    assert zeros["rmse"] == 1.4
    assert payload["strata"]["flagged"]["n"] == 0
    assert "no availability snapshot" in payload["strata"]["flagged"]["note"]
    assert payload["overall"]["n"] == 2          # codes 1 and 2
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_zeros_diagnostic.py -q` → `ModuleNotFoundError: No module named 'gaffer.zeros_diagnostic'`.
- [ ] **Implement** `src/gaffer/zeros_diagnostic.py`:

```python
"""Where the zeros-stratum error actually lives (v7-model spec §2.1).

The 2026-08-29 evaluation put zeros RMSE at 1.063 against a naive last-5
baseline's 1.042: the model over-forecasts players who end up playing no
minutes, and it does so badly enough that not modelling them at all would be
better. That is one number over 4929 rows, and it does not say *which* rows.

This decomposes it. Nothing here fits anything or gates anything — it is a
report, and its only job is to decide which intervention in spec §2.2 is
worth attempting. Strata are computed from leakage-safe training-frame
columns only (``season_start_share`` is shifted within the season,
``minutes_r5`` is a shifted rolling mean), so the decomposition is one a live
run could have made about itself.

The official-flag stratum spec §2.1 asks for is not derivable: status is a
live bootstrap field, the historical frame has no column for it, and the
banked ``reports/availability_gw*.parquet`` snapshots do not reach back into
the holdout. It is reported with ``n = 0`` and a note rather than faked, and
``recent_absence`` stands in for it — "was he already visibly out of the
picture" answered from stored features.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.artifacts import REPORTS

FRINGE_SHARE = 0.3
"""``season_start_share`` below which a player is fringe rather than a regular.

Spec §2.1's threshold. The feature is the mean of ``starts`` over this
season's earlier matches, so 0.3 is "started under a third of the season so
far" — a rotation option, not a benchwarmer and not a nailed starter.
"""

COLD_START_GWS = 4
"""Gameweeks at the front of a season that count as a cold start.

Promoted clubs and new signings have no ``season_start_share`` worth reading
and the rolling windows are still full of last season, which is exactly where
a minutes model is expected to be worst.
"""

DNP_DECILES = 10

ZERO_STRATA = ("fringe", "regular", "cold_start", "settled",
               "recent_absence", "recent_presence")
"""The six derivable sub-populations, in complementary pairs.

``flagged``/``unflagged`` would be a fourth pair and is reported separately,
empty, with the reason — see the module docstring.
"""

FLAGGED_NOTE = ("no availability snapshot covers the holdout slots — official "
                "status is a live bootstrap field and is not stored "
                "historically, so this stratum is not derivable")


def _mask(frame: pd.DataFrame, column: str, test) -> pd.Series:
    """``test`` applied to a numeric ``column``, or all-False when it is absent.

    A stratum built on a column the frame does not carry is *unknown*, not
    empty-because-nobody-qualified, and the two have to look different in the
    report. Reporting ``n = 0`` for both is the honest compromise: the count
    is what says whether the numbers mean anything.
    """
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return test(pd.to_numeric(frame[column], errors="coerce"))


def stratify(scored: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The scored holdout frame split into :data:`ZERO_STRATA`."""
    fringe = _mask(scored, "season_start_share", lambda s: s < FRINGE_SHARE)
    regular = _mask(scored, "season_start_share", lambda s: s >= FRINGE_SHARE)
    cold = _mask(scored, "gw", lambda s: s <= COLD_START_GWS)
    absent = _mask(scored, "minutes_r5", lambda s: s <= 0.0)
    present = _mask(scored, "minutes_r5", lambda s: s > 0.0)
    return {
        "fringe": scored[fringe],
        "regular": scored[regular],
        "cold_start": scored[cold],
        "settled": scored[~cold],
        "recent_absence": scored[absent],
        "recent_presence": scored[present],
    }


def dnp_reliability(frame: pd.DataFrame,
                    bins: int = DNP_DECILES) -> list[dict]:
    """Predicted vs observed DNP rate per ``p_dnp`` decile.

    The DNP mode's own calibration curve, which the pooled ``p_play``
    reliability in :func:`gaffer.evaluation.head_metrics` cannot show: a head
    that is right on average and wrong in every bin is exactly the failure a
    recalibration fixes, and it is invisible in a single log loss.

    Empty deciles are omitted rather than emitted as zeros, matching
    :func:`gaffer.evaluation.reliability`.
    """
    if "p_dnp" not in frame.columns or "minutes" not in frame.columns:
        return []
    p = pd.to_numeric(frame["p_dnp"], errors="coerce").to_numpy(dtype=float)
    y = (pd.to_numeric(frame["minutes"], errors="coerce").fillna(0.0)
         .to_numpy(dtype=float) <= 0.0).astype(float)
    ok = np.isfinite(p)
    p, y = p[ok], y[ok]
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    out = []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        out.append({"decile": b, "n": n,
                    "pred": round(float(p[sel].mean()), 4),
                    "obs": round(float(y[sel].mean()), 4)})
    return out


def _error(frame: pd.DataFrame) -> dict:
    """RMSE, MAE, mean EP and row count over the *zeros* rows of ``frame``.

    Zeros are defined on the outcome exactly as
    :func:`gaffer.evaluation.categorize` defines them (``total_points <= 0``),
    so a number here is comparable to the harness's own stratum without any
    translation. ``mean_ep`` is carried because over-forecasting is the whole
    hypothesis and RMSE alone cannot show its sign.
    """
    zeros = frame[pd.to_numeric(frame["total_points"],
                                errors="coerce").fillna(0.0) <= 0.0]
    n = int(len(zeros))
    if n == 0:
        return {"n": 0, "rmse": 0.0, "mae": 0.0, "mean_ep": 0.0}
    err = (pd.to_numeric(zeros["ep"], errors="coerce").fillna(0.0)
           - pd.to_numeric(zeros["total_points"], errors="coerce").fillna(0.0))
    return {"n": n,
            "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
            "mae": round(float(err.abs().mean()), 4),
            "mean_ep": round(float(pd.to_numeric(zeros["ep"],
                                                 errors="coerce").mean()), 4)}


def zeros_report(scored: pd.DataFrame) -> dict:
    """The whole decomposition: overall, per stratum, plus the DNP curve."""
    strata = {name: _error(part) for name, part in stratify(scored).items()}
    strata["flagged"] = {"n": 0, "rmse": 0.0, "mae": 0.0, "mean_ep": 0.0,
                         "note": FLAGGED_NOTE}
    return {
        "overall": _error(scored),
        "strata": strata,
        "dnp_reliability": dnp_reliability(scored),
        "fringe_share": FRINGE_SHARE,
        "cold_start_gws": COLD_START_GWS,
    }


DIAGNOSTIC_PATH = REPORTS / "zeros_diagnostic.json"


def save_diagnostic(payload: dict) -> Path:
    """Write the report. ``reports/`` is gitignored — this never enters git."""
    REPORTS.mkdir(exist_ok=True)
    DIAGNOSTIC_PATH.write_text(json.dumps(payload, indent=1, allow_nan=False))
    return DIAGNOSTIC_PATH


def format_diagnostic(payload: dict) -> str:
    """The report as a table a human reads in a terminal."""
    o = payload["overall"]
    lines = [f"=== zeros diagnostic (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ===",
             f"overall  n {o['n']:6d}  rmse {o['rmse']:7.4f}  "
             f"mae {o['mae']:7.4f}  mean_ep {o['mean_ep']:7.4f}",
             "-- strata (zeros rows only)"]
    for name, m in payload["strata"].items():
        line = (f"   {name:17s} n {m['n']:6d}  rmse {m['rmse']:7.4f}  "
                f"mae {m['mae']:7.4f}  mean_ep {m['mean_ep']:7.4f}")
        if m.get("note"):
            line += f"  [{m['note']}]"
        lines.append(line)
    lines.append("-- p_dnp calibration (all rows)")
    for row in payload["dnp_reliability"]:
        lines.append(f"   decile {row['decile']}  pred {row['pred']:.4f}  "
                     f"obs {row['obs']:.4f}  n {row['n']}")
    return "\n".join(lines)
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_zeros_diagnostic.py -q` → 7 passed.
- [ ] **Commit:**

```bash
git add src/gaffer/zeros_diagnostic.py tests/test_zeros_diagnostic.py
git commit -m "feat: decompose the zeros-stratum error by sub-population" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 2 — the diagnostic runner and its CLI command

- [ ] **Append the failing test** to `tests/test_zeros_diagnostic.py`:

```python
def test_run_diagnostic_scores_the_same_holdout_the_harness_does(monkeypatch):
    """The decomposition has to be of *the* zeros number, not a different one:
    same boundary helper, same components path, same merge."""
    import gaffer.zeros_diagnostic as zd

    calls = {}

    def fake_frame():
        df = pd.DataFrame([
            {"code": c, "season_idx": 3, "gw": g, "minutes": 0,
             "total_points": 0, "season_start_share": 0.1, "minutes_r5": 0.0,
             "position": "MID", "team_code": 3}
            for c in (1, 2) for g in range(1, 20)])
        return df, pd.DataFrame({"season_idx": [3], "gw": [1],
                                 "elo_diff": [0.0]}), {}

    monkeypatch.setattr(zd, "_holdout", lambda slots=10: (
        fake_frame()[0].assign(ep=1.0, p_dnp=0.9)))
    monkeypatch.setattr(zd, "save_diagnostic",
                        lambda payload: calls.setdefault("saved", payload))
    payload = zd.run_diagnostic()
    assert payload["holdout_slots"] == 10
    assert payload["overall"]["n"] == 38
    assert calls["saved"] is payload
    assert payload["git_sha"] and payload["run_at"]


def test_the_cli_exposes_the_diagnostic():
    from typer.main import get_command

    from gaffer.cli import app

    assert "diagnose-zeros" in get_command(app).commands
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_zeros_diagnostic.py -q` → `AttributeError: module 'gaffer.zeros_diagnostic' has no attribute '_holdout'`.
- [ ] **Implement.** Append to `src/gaffer/zeros_diagnostic.py`:

```python
def _holdout(holdout_slots: int = 10) -> pd.DataFrame:
    """The evaluation harness's own holdout rows, scored, with the strata
    features and ``p_dnp`` carried along.

    Deliberately a re-walk of :func:`gaffer.evaluation.evaluate_current`'s
    steps rather than a call into it: the harness returns metrics, and what is
    wanted here is the row-level frame those metrics were computed from, with
    the mode probabilities and the rotation features still attached.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.evaluation import HOLDOUT_SLOTS, before_mask, holdout_boundary
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_matrix)
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    holdout_slots = holdout_slots or HOLDOUT_SLOTS
    df, tg, _ = load_training_frame()
    bs, bg = holdout_boundary(df, holdout_slots)
    before, tg_before = before_mask(df, bs, bg), before_mask(tg, bs, bg)
    models = train_all(df[before], tg[tg_before].dropna(subset=["elo_diff"]),
                       save=False)

    hold = df[~before].reset_index(drop=True)
    comp = predict_components_simple(models, hold)
    ep = ep_matrix(apply_calibration(
        assemble_ep(comp, scoring_table(load_bootstrap_sample())),
        models.get("calibration")))
    truth = hold.groupby(["code", "gw"], as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"))
    # One row per player-fixture becomes one row per player-gameweek, so the
    # strata features are taken from the first fixture of the week: they are
    # player-and-week facts, identical across a double gameweek's two rows.
    modes = models["minutes"].predict_modes(hold)
    carry = hold[["code", "gw"]].copy()
    for col in ("season_start_share", "minutes_r5"):
        if col in hold.columns:
            carry[col] = pd.to_numeric(hold[col], errors="coerce")
    carry["p_dnp"] = modes["p_dnp"].values
    carry = carry.groupby(["code", "gw"], as_index=False).first()
    return ep.merge(truth, on=["code", "gw"], how="inner").merge(
        carry, on=["code", "gw"], how="left")


def run_diagnostic(holdout_slots: int = 10) -> dict:
    """Score the holdout, decompose it, print it, save it."""
    from gaffer.evaluation import git_sha, run_at

    payload = zeros_report(_holdout(holdout_slots))
    payload["run_at"] = run_at()
    payload["git_sha"] = git_sha()
    payload["holdout_slots"] = int(holdout_slots)
    print(format_diagnostic(payload), flush=True)
    save_diagnostic(payload)
    return payload
```

Add to `src/gaffer/cli.py`, immediately above the `@app.command("calibrate-noise")` block:

```python
@app.command("diagnose-zeros")
def diagnose_zeros(holdout_slots: int = typer.Option(
        10, help="Gameweek slots to hold out — the evaluation default.")):
    """Decompose the zeros-stratum error and write reports/zeros_diagnostic.json.

    Slow: one full component refit on everything before the holdout, the same
    fit `gaffer evaluate` pays for. A report, not a gate — spec §2.1.
    """
    from gaffer.zeros_diagnostic import DIAGNOSTIC_PATH, run_diagnostic

    run_diagnostic(holdout_slots)
    typer.echo(f"-> {DIAGNOSTIC_PATH}")
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_zeros_diagnostic.py tests/test_cli.py -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/zeros_diagnostic.py src/gaffer/cli.py tests/test_zeros_diagnostic.py
git commit -m "feat: gaffer diagnose-zeros writes the zeros decomposition" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 3 — `DnpCalibrator`

- [ ] **Write the failing test** `tests/test_dnp_calibrate.py`:

```python
import numpy as np
import pandas as pd

from gaffer.models.dnp_calibrate import DNP_MIN_ROWS, DnpCalibrator


def _modes(p_dnp, p_sub=None, p_start=None) -> pd.DataFrame:
    p_dnp = np.asarray(p_dnp, dtype=float)
    rest = 1.0 - p_dnp
    p_sub = rest * 0.4 if p_sub is None else np.asarray(p_sub, dtype=float)
    p_start = rest * 0.6 if p_start is None else np.asarray(p_start,
                                                            dtype=float)
    return pd.DataFrame({"p_dnp": p_dnp, "p_sub": p_sub, "p_start": p_start})


def _overconfident(n=2000, seed=0):
    """A head that says 0.6 where the truth is 0.3 — v7's hypothesis."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.0, 1.0, n)
    y = (rng.uniform(0.0, 1.0, n) < (p * 0.5)).astype(float)
    return p, y


def test_an_unfitted_calibrator_is_the_identity():
    modes = _modes([0.1, 0.9])
    pd.testing.assert_frame_equal(DnpCalibrator().apply(modes), modes)


def test_too_few_rows_leaves_the_calibrator_unfitted():
    p, y = _overconfident(n=DNP_MIN_ROWS - 1)
    assert DnpCalibrator().fit(p, y).iso is None


def test_a_single_outcome_class_leaves_the_calibrator_unfitted():
    p = np.linspace(0.0, 1.0, DNP_MIN_ROWS + 10)
    assert DnpCalibrator().fit(p, np.zeros_like(p)).iso is None


def test_the_calibrator_pulls_an_over_forecast_down():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes([0.6]))
    assert 0.2 < float(out["p_dnp"].iloc[0]) < 0.45


def test_the_calibrator_is_monotone_so_no_two_players_swap_order():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes(np.linspace(0.01, 0.99, 50)))
    assert (out["p_dnp"].diff().dropna() >= -1e-12).all()


def test_the_three_modes_still_sum_to_one_after_calibration():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes(np.linspace(0.0, 1.0, 21)))
    total = out["p_dnp"] + out["p_sub"] + out["p_start"]
    assert np.allclose(total.to_numpy(), 1.0, atol=1e-9)


def test_the_sub_start_ratio_is_preserved_where_there_is_mass_to_share():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes([0.5]))
    assert np.isclose(float(out["p_start"].iloc[0] / out["p_sub"].iloc[0]),
                      0.6 / 0.4)


def test_a_certain_dnp_row_puts_its_freed_mass_on_the_sub_mode():
    p, y = _overconfident()
    cal = DnpCalibrator().fit(p, y)
    out = cal.apply(_modes([1.0], p_sub=[0.0], p_start=[0.0]))
    freed = 1.0 - float(out["p_dnp"].iloc[0])
    assert np.isclose(float(out["p_sub"].iloc[0]), freed)
    assert float(out["p_start"].iloc[0]) == 0.0


def test_apply_does_not_mutate_its_input():
    p, y = _overconfident()
    modes = _modes([0.3, 0.7])
    before = modes.copy()
    DnpCalibrator().fit(p, y).apply(modes)
    pd.testing.assert_frame_equal(modes, before)
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_dnp_calibrate.py -q` → `ModuleNotFoundError: No module named 'gaffer.models.dnp_calibrate'`.
- [ ] **Implement** `src/gaffer/models/dnp_calibrate.py`:

```python
"""Isotonic recalibration of the minutes model's DNP-mode probability.

The v7-model diagnosis (spec §1): the zeros stratum's RMSE is 1.063 against a
naive last-5 baseline's 1.042, and the direction of the miss is systematic —
players who end up playing nothing are forecast points they were never going
to score. That is a ``p_dnp`` that is too low, and the cheapest honest fix for
a probability that is too low is to learn the map from what the head says to
what actually happens.

Isotonic rather than Platt because the map is not assumed to be a sigmoid and
because monotonicity is the one property that must not be lost: it guarantees
no two players swap places in DNP risk, so nothing the optimizer ranks can be
reordered by a calibration artefact. ``models/calibrate.py`` records an
isotonic failure at gate A, but that was isotonic on *assembled expected
points*, where plateaus collapsed the captaincy ranking into ties. A plateau
in ``p_dnp`` passes through three attacking heads, ``p60`` and a scoring table
before it reaches an EP ordering, so that failure mode does not transfer.

Calibrating one leg of a trichotomy means the other two have to move. The
freed (or claimed) mass is rescaled across ``p_sub`` and ``p_start`` in
proportion, so a player's start-versus-cameo split — which the calibration
says nothing about — is left exactly as the model had it. The single
degenerate case, a row the model priced as a certain DNP, has no ratio to
preserve; its freed mass goes to ``p_sub``, because a fringe player the
calibration has just admitted might play is a substitute, not a starter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

DNP_MIN_ROWS = 500
"""Out-of-sample rows the fit needs before its curve is trusted.

Isotonic is non-parametric and will happily interpolate noise: below this the
curve is a memory of the holdout rather than a calibration of the head, and an
unfitted calibrator (the identity) is the better answer.
"""

DNP_HOLDOUT_SLOTS = 10
"""Gameweek slots held out to fit on, matching
:data:`gaffer.models.train.CALIBRATION_HOLDOUT_GWS` and
:data:`gaffer.evaluation.HOLDOUT_SLOTS` — the same compromise for the same
reason, and it keeps every out-of-sample window in this codebase the same
length."""

_MASS_EPS = 1e-12


class DnpCalibrator:
    """``p_dnp -> calibrated p_dnp``, with the trichotomy renormalised."""

    def __init__(self) -> None:
        self.iso: IsotonicRegression | None = None

    def fit(self, p_dnp, is_dnp) -> "DnpCalibrator":
        """Learn the map on genuinely out-of-sample predictions.

        The caller supplies predictions made by a model that never saw these
        rows (see :func:`fit_dnp_calibrator`). Fitting on in-sample
        predictions would learn the mode classifier's training-set confidence
        rather than the miscalibration a live run actually carries.

        Returns an unfitted (identity) calibrator rather than raising when
        there is too little to learn from: a thin backtest window must still
        produce a usable model.
        """
        p = np.asarray(p_dnp, dtype="float64")
        y = np.asarray(is_dnp, dtype="float64")
        ok = np.isfinite(p) & np.isfinite(y)
        p, y = p[ok], y[ok]
        if p.size < DNP_MIN_ROWS or np.unique(y).size < 2:
            return self
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True,
                                 out_of_bounds="clip")
        iso.fit(p, y)
        self.iso = iso
        return self

    def apply(self, modes: pd.DataFrame) -> pd.DataFrame:
        """A copy of the mode frame with ``p_dnp`` calibrated and the other
        two modes rescaled so the three still sum to one.

        Takes the whole frame rather than a loose column for the same reason
        :meth:`gaffer.models.calibrate.CalibrationModel.apply` does: the three
        probabilities are one object and must not drift apart.
        """
        if self.iso is None:
            return modes
        out = modes.copy()
        raw = pd.to_numeric(out["p_dnp"], errors="coerce").to_numpy(
            dtype="float64")
        finite = np.isfinite(raw)
        cal = np.clip(self.iso.predict(np.where(finite, raw, 0.0)), 0.0, 1.0)
        cal = np.where(finite, cal, raw)
        rest = 1.0 - raw
        wide = rest > _MASS_EPS
        scale = np.divide(1.0 - cal, rest, out=np.ones_like(rest), where=wide)
        # A row with no mass outside p_dnp has no ratio to preserve; the mass
        # the calibration frees goes to the substitute mode.
        freed = np.where(wide, 0.0, 1.0 - cal)
        out["p_dnp"] = cal
        out["p_sub"] = (out["p_sub"].to_numpy(dtype="float64") * scale
                        + freed)
        out["p_start"] = out["p_start"].to_numpy(dtype="float64") * scale
        return out
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_dnp_calibrate.py -q` → 9 passed.
- [ ] **Commit:**

```bash
git add src/gaffer/models/dnp_calibrate.py tests/test_dnp_calibrate.py
git commit -m "feat: isotonic DNP-mode calibrator with a renormalised trichotomy" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 4 — `fit_dnp_calibrator`, and the leakage rail

- [ ] **Append the failing test** to `tests/test_dnp_calibrate.py`:

```python
def _slotted(n_codes=80, n_gws=30, seed=1) -> pd.DataFrame:
    """A frame whose fringe players stop playing entirely after slot 20.

    The leakage rail's whole point: a calibrator that peeked past the boundary
    would learn the late-season DNP rate, and the test can see the difference.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(n_codes):
        fringe = code >= 40
        for gw in range(1, n_gws + 1):
            if fringe and gw > 20:
                minutes = 0
            elif fringe:
                minutes = int(rng.choice([0, 0, 90]))
            else:
                minutes = 90
            rows.append({"code": code, "season_idx": 0, "gw": gw,
                         "minutes": minutes, "starts": int(minutes >= 60),
                         "minutes_r5": float(minutes),
                         "starts_r5": float(minutes >= 60),
                         "home": 1.0})
    return pd.DataFrame(rows)


_FIT_COLS = ["minutes_r5", "starts_r5", "home"]


def test_the_fitter_holds_out_the_last_slots_and_fits_on_them(monkeypatch):
    import gaffer.models.dnp_calibrate as dc

    seen = {}
    real = dc.DnpCalibrator.fit

    def spy(self, p_dnp, is_dnp):
        seen["rows"] = len(np.asarray(p_dnp))
        return real(self, p_dnp, is_dnp)

    monkeypatch.setattr(dc.DnpCalibrator, "fit", spy)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    dc.fit_dnp_calibrator(_slotted(), _FIT_COLS, holdout_slots=10)
    # 80 codes x the last 10 of 30 slots.
    assert seen["rows"] == 800


def test_the_inner_model_never_sees_a_held_out_slot(monkeypatch):
    """Spec §7's walk-forward-leakage rail: the model that produces the
    predictions the calibrator learns from must be fit strictly before them."""
    import gaffer.models.dnp_calibrate as dc
    from gaffer.models.minutes import ThreeModeModel

    seen = {}
    real = ThreeModeModel.fit

    def spy(self, df):
        seen["max_gw"] = int(df["gw"].max())
        return real(self, df)

    monkeypatch.setattr(ThreeModeModel, "fit", spy)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    dc.fit_dnp_calibrator(_slotted(), _FIT_COLS, holdout_slots=10)
    assert seen["max_gw"] == 20        # slots 21-30 are the holdout


def test_a_frame_with_too_few_slots_returns_the_identity():
    from gaffer.models.dnp_calibrate import fit_dnp_calibrator

    thin = _slotted(n_codes=80, n_gws=8)
    assert fit_dnp_calibrator(thin, _FIT_COLS, holdout_slots=10).iso is None


def test_the_fitter_does_not_recurse_into_itself(monkeypatch):
    """The inner ThreeModeModel must be built with the recursion guard, or
    fitting one calibrator would fit an unbounded tower of them."""
    import gaffer.models.dnp_calibrate as dc
    from gaffer.models.minutes import ThreeModeModel

    built = []
    real = ThreeModeModel.__init__

    def spy(self, feature_cols, *args, **kw):
        built.append(kw.get("_fit_dnp", True))
        return real(self, feature_cols, *args, **kw)

    monkeypatch.setattr(ThreeModeModel, "__init__", spy)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    dc.fit_dnp_calibrator(_slotted(), _FIT_COLS, holdout_slots=10)
    assert built == [False]
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_dnp_calibrate.py -q` → `AttributeError: module 'gaffer.models.dnp_calibrate' has no attribute 'fit_dnp_calibrator'`.
- [ ] **Implement, step one: the recursion-guard keyword.** The fitter builds an inner `ThreeModeModel` with the guard set, so `src/gaffer/models/minutes.py`'s constructor has to accept it before this task's tests can go green. Add exactly two lines to `ThreeModeModel.__init__` (Task 5 finishes the rest of that method):

```python
    def __init__(self, feature_cols: list[str], _fit_dnp: bool = True):
        self.feature_cols = feature_cols
        self._fit_dnp = _fit_dnp
```

- [ ] **Implement, step two.** Append to `src/gaffer/models/dnp_calibrate.py`:

```python
def fit_dnp_calibrator(df: pd.DataFrame, feature_cols: list[str],
                       holdout_slots: int = DNP_HOLDOUT_SLOTS
                       ) -> DnpCalibrator:
    """Fit the calibrator on out-of-sample DNP predictions.

    The same shape as :func:`gaffer.models.train.fit_calibration`, and for the
    same reason. The last ``holdout_slots`` ``(season_idx, gw)`` slots are held
    out, an inner :class:`~gaffer.models.minutes.ThreeModeModel` is fit on the
    rows strictly before them, and the calibration learns its map from that
    model's predictions on slots it never saw. Spec §2.2's no-leakage
    requirement — "calibrator for slot t fits on slots < t" — is met by
    construction at the slot boundary, and it composes with the harness: when
    ``evaluate_current`` fits on rows before *its* boundary, this inner split
    sits entirely inside that, so nothing the gate scores can have leaked in.

    ``_fit_dnp=False`` on the inner model is the recursion guard, exactly as
    ``_fit_cal=False`` is in ``train_all``.

    The import is function-local because ``minutes`` imports this module at
    module scope for the flag and the fitter; deferring the reverse edge keeps
    the cycle from ever being real at import time.
    """
    from gaffer.models.minutes import DNP, ThreeModeModel, mode_labels

    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        return DnpCalibrator()
    row = slots.iloc[-holdout_slots]
    bs, bg = int(row["season_idx"]), int(row["gw"])
    before = ((df["season_idx"] < bs)
              | ((df["season_idx"] == bs) & (df["gw"] < bg)))
    inner_df, hold = df[before], df[~before]
    if inner_df.empty or hold.empty:
        return DnpCalibrator()
    inner = ThreeModeModel(feature_cols, _fit_dnp=False).fit(inner_df)
    modes = inner.predict_modes(hold)
    return DnpCalibrator().fit(
        modes["p_dnp"], (mode_labels(hold) == DNP).astype("float64"))
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_dnp_calibrate.py tests/test_minutes.py -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/models/dnp_calibrate.py src/gaffer/models/minutes.py \
        tests/test_dnp_calibrate.py
git commit -m "feat: walk-forward-safe fitter for the DNP calibrator" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 5 — wire it into `ThreeModeModel`, default OFF

- [ ] **Write the failing test** `tests/test_v7_model_degradation.py`:

```python
"""The v7-model degradation rails.

Four things are pinned here; Task 7 adds the seed rail and Task 18's flip is
the only thing allowed to change rail 2:

1. With ``DNP_CALIBRATION_DEFAULT`` off, ``ThreeModeModel`` fits no
   calibrator, pays for no inner refit, and predicts byte-identically.
2. The constant really is off — gate Z1 has not been run by an implementer.
3. A model pickled before the calibrator existed still predicts.
4. The protected ``run_advise`` source-text pins still hold, because nothing
   in this cycle touched ``advise.py`` at all.

If a later task legitimately changes one of these, that task's gate says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.models.minutes import ThreeModeModel


def _frame(n_codes=40, n_gws=30, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(n_codes):
        for gw in range(1, n_gws + 1):
            minutes = 90 if code < 20 else int(rng.choice([0, 0, 0, 20]))
            rows.append({"code": code, "season_idx": 0, "gw": gw,
                         "minutes": minutes, "starts": int(minutes >= 60),
                         "minutes_r5": float(minutes),
                         "starts_r5": float(minutes >= 60), "home": 1.0})
    return pd.DataFrame(rows)


_COLS = ["minutes_r5", "starts_r5", "home"]


# --- rail 1: the flag off is the pre-v7 model, prediction for prediction ---

def test_the_flag_off_fits_no_calibrator():
    import gaffer.models.minutes as mn

    assert mn.DNP_CALIBRATION_DEFAULT is False
    model = ThreeModeModel(_COLS).fit(_frame())
    assert model.dnp_cal is None


def test_the_flag_off_predicts_the_raw_classifier_probabilities():
    """Nothing sits between the mode classifier and the trichotomy: with the
    flag off, predict_modes is predict_proba re-columned and nothing else."""
    df = _frame()
    model = ThreeModeModel(_COLS).fit(df)
    modes = model.predict_modes(df)
    proba = model.mode_clf.predict_proba(df[_COLS])
    for j, mode in enumerate(model.mode_clf.classes_):
        assert np.allclose(modes.iloc[:, int(mode)].to_numpy(), proba[:, j])


def test_the_flag_off_never_pays_for_the_inner_refit(monkeypatch):
    import gaffer.models.minutes as mn

    def boom(*args, **kw):
        raise AssertionError("the default path must not fit a calibrator")

    monkeypatch.setattr(mn, "fit_dnp_calibrator", boom)
    ThreeModeModel(_COLS).fit(_frame())


# --- rail 2: the shipping default has not moved --------------------------

def test_the_dnp_calibration_is_off_by_default():
    """Gate Z1 is the orchestrator's to run. Until it passes, this is False."""
    import gaffer.models.minutes as mn

    assert mn.DNP_CALIBRATION_DEFAULT is False


# --- rail 3: an older pickle still predicts ------------------------------

def test_a_model_without_the_attribute_degrades_to_the_identity():
    """``getattr`` rather than ``self.dnp_cal``: a joblib fitted before this
    cycle has no such attribute, and it must still serve."""
    df = _frame()
    model = ThreeModeModel(_COLS).fit(df)
    modes = model.predict_modes(df)
    del model.dnp_cal
    pd.testing.assert_frame_equal(model.predict_modes(df), modes)


def test_the_flag_on_actually_changes_something(monkeypatch):
    """The opt-in path stays alive for the gate: flipping the constant fits a
    calibrator and moves the DNP column."""
    import gaffer.models.dnp_calibrate as dc
    import gaffer.models.minutes as mn

    monkeypatch.setattr(mn, "DNP_CALIBRATION_DEFAULT", True)
    monkeypatch.setattr(dc, "DNP_MIN_ROWS", 10)
    df = _frame()
    model = ThreeModeModel(_COLS).fit(df)
    assert model.dnp_cal is not None and model.dnp_cal.iso is not None


# --- rail 4: advise.py was not touched -----------------------------------

def test_run_advise_still_pins_every_protected_ordering():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "ep_matrix(apply_calibration(assemble_ep(" in src
    assert src.index("fetch_rival_entries(") < src.index("tilt_ep(")
    assert src.index("tilt_ep(") < src.index("pool = build_pool(")
    assert "build_pool(players, pool_ep," in src
    assert 'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]


def test_predict_components_still_calls_the_minutes_model_once():
    """The calibrator lives inside the model, so the advise seam is unchanged:
    one model call, two availability passes, exactly as v6 left it."""
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.count("minutes.predict(pf)") == 1
    assert src.count("apply_availability(") == 2
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_v7_model_degradation.py -q` → `ImportError: cannot import name 'DNP_CALIBRATION_DEFAULT'`.
- [ ] **Implement.** In `src/gaffer/models/minutes.py`, below `LGB_KW`:

```python
DNP_CALIBRATION_DEFAULT = False
"""Whether :meth:`ThreeModeModel.fit` learns a DNP-mode recalibration.

**Off, pending gate Z1.** Spec §2.3 pre-registers the rule: zeros RMSE must
reach 1.042 or better (a 2% improvement on the 2026-08-29 baseline of 1.063,
i.e. at least to the naive last-5 baseline the model currently loses to)
while haulers RMSE stays at or under 5.171 and all-stratum RMSE at or under
1.996 — half a percent of headroom each. The gate is the orchestrator's to
run, through ``scripts/z1_arms.py``; flipping this constant is a separate,
deliberate commit that names the numbers.

Off means off all the way down: ``fit`` does not pay for the inner refit and
``predict_modes`` does not branch, so a run with this False is the pre-v7
model prediction for prediction.
"""
```

Add the import at the **top** of `minutes.py`, with the other imports and **not** inside `fit` — the degradation test monkeypatches `mn.fit_dnp_calibrator`, which only works if the name is a module global:

```python
from gaffer.models.dnp_calibrate import fit_dnp_calibrator
```

This is safe: `dnp_calibrate` imports `minutes` only inside `fit_dnp_calibrator`'s body, so there is no import-time cycle.

Finish `ThreeModeModel.__init__` (Task 4 already added `_fit_dnp`; this adds the `dnp_cal` slot):

```python
    def __init__(self, feature_cols: list[str], _fit_dnp: bool = True):
        self.feature_cols = feature_cols
        self._fit_dnp = _fit_dnp
        self.mode_clf = LGBMClassifier(objective="multiclass", num_class=3,
                                       **LGB_KW)
        self.sixty_clf = LGBMClassifier(**LGB_KW)
        self.min_start = LGBMRegressor(**LGB_KW)
        self.min_sub = LGBMRegressor(**LGB_KW)
        self.modes_seen: list[int] = []
        self.dnp_cal = None
```

Append to the end of `fit`, replacing its bare `return self`:

```python
        self.min_sub = self._regressor(X[subbed], mins[subbed], default=20.0)
        # The recursion guard, mirroring ``train_all``'s ``_fit_cal``: the
        # calibrator's own inner model is built with it False.
        if self._fit_dnp and DNP_CALIBRATION_DEFAULT:
            self.dnp_cal = fit_dnp_calibrator(df, self.feature_cols)
        return self
```

Restructure `predict_modes` so both branches leave through one tail:

```python
    def predict_modes(self, df: pd.DataFrame) -> pd.DataFrame:
        """``p_dnp``, ``p_sub``, ``p_start``, one row per input row.

        Exposed because it is the honest object: everything ``predict``
        returns is a function of these three, and the shadow log and the
        explainability page both want the trichotomy rather than its
        summaries.

        The DNP recalibration is applied here, at the trichotomy, rather than
        to ``p_play`` downstream — ``p_play`` is a sum of two modes and
        correcting it would leave the start/cameo split incoherent with it.
        ``getattr`` rather than ``self.dnp_cal`` so a model pickled before v7
        still predicts.
        """
        X = df[self.feature_cols]
        out = pd.DataFrame(0.0, index=df.index, columns=MODE_COLS,
                           dtype="float64")
        if isinstance(self.mode_clf, _ConstantHead):
            out[MODE_COLS[int(self.mode_clf.value)]] = 1.0
        else:
            proba = self.mode_clf.predict_proba(X)
            # classes_ holds only the modes the fit actually saw, in
            # LightGBM's own order; a mode absent from training stays at the
            # 0.0 the frame was initialised with rather than shifting the
            # other two along.
            for j, mode in enumerate(self.mode_clf.classes_):
                out[MODE_COLS[int(mode)]] = proba[:, j]
        cal = getattr(self, "dnp_cal", None)
        return out if cal is None else cal.apply(out)
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_v7_model_degradation.py tests/test_dnp_calibrate.py tests/test_minutes.py tests/test_train.py -q` → all passed.
- [ ] **Full backend sweep:** `.venv/bin/python -m pytest -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/models/minutes.py tests/test_v7_model_degradation.py
git commit -m "feat: hook the DNP calibrator into ThreeModeModel, off by default" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 6 — `scripts/z1_arms.py`, the gate driver (build only — do not run it)

- [ ] **Write the failing test.** Append to `tests/test_v7_model_degradation.py`:

```python
def test_the_z1_driver_exists_and_names_both_arms():
    """The gate has to be reproducible after this session ends, so its driver
    is committed rather than left in a scratchpad."""
    from pathlib import Path

    src = Path("scripts/z1_arms.py").read_text()
    assert "DNP_CALIBRATION_DEFAULT" in src
    assert "Z1_ARM_DONE" in src
    assert "load_training_frame" in src      # memoised across the two arms
    assert "1.042" in src and "5.171" in src and "1.996" in src
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_v7_model_degradation.py -q -k z1` → `FileNotFoundError: scripts/z1_arms.py`.
- [ ] **Implement** `scripts/z1_arms.py`:

```python
"""Gate Z1: the zeros stratum with and without the DNP recalibration.

Two runs of ``evaluate_current`` over one training frame. Arm ``off`` is the
shipped model; arm ``on`` flips ``minutes.DNP_CALIBRATION_DEFAULT``, which is
the only difference between them — same slots, same components, same scoring
table, same assemble/calibrate seam.

``load_training_frame`` is memoised across the arms because it is the
expensive half of the run and it cannot differ between them by construction.
It hands back copies, so an arm that mutates its frame cannot poison the next.

Run it, watch it, read the verdict::

    caffeinate -i nohup .venv/bin/python scripts/z1_arms.py \\
        > logs/z1_arms.log 2>&1 &
    grep -e Z1_ARM_DONE -e Z1_VERDICT logs/z1_arms.log

The pre-registered rule (v7-model spec §2.3) against the 2026-08-29 baseline
(zeros 1.063, haulers 5.145, all 1.986): PASS needs zeros <= 1.042 AND
haulers <= 5.171 AND all <= 1.996. This script prints the comparison; the
shipping decision is the orchestrator's.
"""

import json
from pathlib import Path

import gaffer.evaluation as ev
import gaffer.models.minutes as mn
from gaffer.models import train as tr

ZEROS_TARGET = 1.042
HAULERS_CEILING = 5.171
ALL_CEILING = 1.996

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


tr.load_training_frame = _memoised

arms = {}
for name, flag in (("off", False), ("on", True)):
    mn.DNP_CALIBRATION_DEFAULT = flag
    payload = ev.evaluate_current()
    arms[name] = payload
    table = payload["stratified"]["all"]
    print("Z1_ARM_DONE", name, json.dumps({
        "zeros": table["zeros"]["rmse"],
        "haulers": table["haulers"]["rmse"],
        "all": table["all"]["rmse"],
        "zeros_n": table["zeros"]["n"],
        "last5_zeros": payload["baselines"]["last5"]["zeros"]["rmse"],
    }), flush=True)

on = arms["on"]["stratified"]["all"]
verdict = {
    "zeros": on["zeros"]["rmse"],
    "zeros_pass": on["zeros"]["rmse"] <= ZEROS_TARGET,
    "haulers": on["haulers"]["rmse"],
    "haulers_pass": on["haulers"]["rmse"] <= HAULERS_CEILING,
    "all": on["all"]["rmse"],
    "all_pass": on["all"]["rmse"] <= ALL_CEILING,
}
verdict["gate"] = ("PASS" if all(verdict[k] for k in
                                 ("zeros_pass", "haulers_pass", "all_pass"))
                   else "FAIL")
print("Z1_VERDICT", json.dumps(verdict), flush=True)

Path("reports").mkdir(exist_ok=True)
Path("reports/z1_arms.json").write_text(
    json.dumps({"arms": arms, "verdict": verdict}, indent=1))
```

- [ ] **Run the test, not the driver:** `.venv/bin/python -m pytest tests/test_v7_model_degradation.py -q` → all passed. **Do not execute `scripts/z1_arms.py`** — it is the orchestrator's gate (Task 15).
- [ ] **Syntax-check it instead:** `.venv/bin/python -m py_compile scripts/z1_arms.py` → no output.
- [ ] **Commit:**

```bash
git add scripts/z1_arms.py tests/test_v7_model_degradation.py
git commit -m "feat: committed gate Z1 driver for the DNP recalibration" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Group 2 — M2: estimation-only σ (Tasks 7-11)

A second implementer owns this group and may work in parallel with Group 1 — the only shared file is `src/gaffer/models/minutes.py`, and Task 7 touches its constructor while Task 5 touches its `fit`/`predict_modes`. Coordinate by taking Task 7 *after* Task 5 has landed, or expect one trivial merge in `__init__`.

### Task 7 — the seed seam on both LightGBM heads

- [ ] **Write the failing test** `tests/test_estimation_noise.py`:

```python
import numpy as np
import pandas as pd

from gaffer.models.attacking import AttackingModel
from gaffer.models.minutes import LGB_KW, ThreeModeModel


def _frame(n_codes=40, n_gws=25, seed=5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(n_codes):
        for gw in range(1, n_gws + 1):
            minutes = 90 if code < 20 else int(rng.choice([0, 0, 20, 90]))
            rows.append({
                "code": code, "season_idx": 0, "gw": gw, "minutes": minutes,
                "starts": int(minutes >= 60), "position": "MID",
                "goals": int(rng.random() < 0.15),
                "assists": int(rng.random() < 0.12),
                "minutes_r5": float(minutes), "starts_r5": float(minutes >= 60),
                "home": 1.0, "xg_r5": rng.random(), "xa_r5": rng.random()})
    return pd.DataFrame(rows)


_MIN_COLS = ["minutes_r5", "starts_r5", "home"]
_ATK_COLS = ["xg_r5", "xa_r5", "minutes_r5"]


def test_no_seed_is_the_shipped_random_state():
    model = ThreeModeModel(_MIN_COLS)
    assert model.lgb_kw == LGB_KW
    assert model.lgb_kw["random_state"] == 7


def test_a_seed_only_moves_the_random_state():
    model = ThreeModeModel(_MIN_COLS, seed=17)
    assert model.lgb_kw["random_state"] == 17
    assert {k: v for k, v in model.lgb_kw.items() if k != "random_state"} == \
        {k: v for k, v in LGB_KW.items() if k != "random_state"}


def test_no_seed_predicts_exactly_what_the_shipped_model_predicts():
    df = _frame()
    a = ThreeModeModel(_MIN_COLS).fit(df).predict_modes(df)
    b = ThreeModeModel(_MIN_COLS, seed=None).fit(df).predict_modes(df)
    pd.testing.assert_frame_equal(a, b)


def test_two_seeds_disagree_at_least_somewhere():
    df = _frame()
    a = ThreeModeModel(_MIN_COLS, seed=7).fit(df).predict_modes(df)
    b = ThreeModeModel(_MIN_COLS, seed=47).fit(df).predict_modes(df)
    assert not np.allclose(a["p_dnp"].to_numpy(), b["p_dnp"].to_numpy())


def test_the_attacking_head_takes_the_same_seam():
    df = _frame()
    plain = AttackingModel(_ATK_COLS).fit(df).predict(df)
    same = AttackingModel(_ATK_COLS, seed=None).fit(df).predict(df)
    pd.testing.assert_frame_equal(plain, same)
    other = AttackingModel(_ATK_COLS, seed=47).fit(df).predict(df)
    assert not np.allclose(plain["e_goals"].to_numpy(),
                           other["e_goals"].to_numpy())
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_estimation_noise.py -q` → `AttributeError: 'ThreeModeModel' object has no attribute 'lgb_kw'`.
- [ ] **Implement.** In `src/gaffer/models/minutes.py`:

```python
    def __init__(self, feature_cols: list[str], seed: int | None = None,
                 _fit_dnp: bool = True):
        """``seed`` overrides LightGBM's ``random_state`` and nothing else.

        The seam exists for the v7 estimation-σ ensemble (spec §3), which
        prices how much the *model's own estimate* moves by refitting the
        LightGBM heads under K seeds and reading the spread. ``None`` is the
        shipped fit — :data:`LGB_KW` untouched, object for object — so the
        weekly refit, every backtest and every test are byte-identical to
        pre-v7.
        """
        self.feature_cols = feature_cols
        self.seed = seed
        self._fit_dnp = _fit_dnp
        self.lgb_kw = (dict(LGB_KW) if seed is None
                       else {**LGB_KW, "random_state": int(seed)})
        self.mode_clf = LGBMClassifier(objective="multiclass", num_class=3,
                                       **self.lgb_kw)
        self.sixty_clf = LGBMClassifier(**self.lgb_kw)
        self.min_start = LGBMRegressor(**self.lgb_kw)
        self.min_sub = LGBMRegressor(**self.lgb_kw)
        self.modes_seen: list[int] = []
        self.dnp_cal = None
```

`_binary` and `_regressor` stop being `@staticmethod` so they can read `self.lgb_kw` (they are private and have no callers outside this class):

```python
    def _binary(self, X, y, default: float):
        if len(X) == 0:
            return _ConstantHead(default)
        if y.nunique() < 2:
            return _ConstantHead(float(y.iloc[0]))
        clf = LGBMClassifier(**self.lgb_kw)
        clf.fit(X, y)
        return clf

    def _regressor(self, X, y, default: float):
        if len(X) == 0:
            return _ConstantHead(default)
        if y.nunique() < 2:
            return _ConstantHead(float(y.iloc[0]))
        reg = LGBMRegressor(**self.lgb_kw)
        reg.fit(X, y)
        return reg
```

The calibrator's inner model has to be fitted under the *same* seed as the model that will carry it, or an ensemble member's calibration would be learned from a differently-seeded head. In `src/gaffer/models/dnp_calibrate.py`, widen the signature and thread it through:

```python
def fit_dnp_calibrator(df: pd.DataFrame, feature_cols: list[str],
                       holdout_slots: int = DNP_HOLDOUT_SLOTS,
                       seed: int | None = None) -> DnpCalibrator:
```

```python
    inner = ThreeModeModel(feature_cols, seed=seed,
                           _fit_dnp=False).fit(inner_df)
```

and in `minutes.py::fit`:

```python
        if self._fit_dnp and DNP_CALIBRATION_DEFAULT:
            self.dnp_cal = fit_dnp_calibrator(df, self.feature_cols,
                                              seed=self.seed)
```

In `src/gaffer/models/attacking.py`:

```python
    def __init__(self, feature_cols: list[str] = ATTACK_FEATURES,
                 seed: int | None = None):
        """``seed`` overrides LightGBM's ``random_state``; see
        :class:`gaffer.models.minutes.ThreeModeModel`, which owns the seam and
        the reason for it. ``None`` is the shipped fit."""
        self.feature_cols = feature_cols
        self.seed = seed
        self.lgb_kw = (dict(LGB_KW) if seed is None
                       else {**LGB_KW, "random_state": int(seed)})
        self.models: dict[tuple[str, str], LGBMRegressor] = {}
```

and inside `fit`, `model = LGBMRegressor(**self.lgb_kw)`.

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_estimation_noise.py tests/test_minutes.py tests/test_attacking.py tests/test_train.py tests/test_dnp_calibrate.py -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/models/minutes.py src/gaffer/models/attacking.py \
        src/gaffer/models/dnp_calibrate.py tests/test_estimation_noise.py
git commit -m "feat: seed seam on the LightGBM heads, default byte-identical" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 8 — `fit_estimation_sigmas`, the 13-cell table from ensemble spread

- [ ] **Append the failing test** to `tests/test_estimation_noise.py`:

```python
from gaffer.calibrate_noise import (EP_EDGES, MIN_CELL_OBS, XMINS_EDGES,
                                    fit_estimation_sigmas)
from gaffer.optimize.scenarios import sigma_for


def _rows(n_per_cell=120, sigma=0.4) -> pd.DataFrame:
    """Two populated cells: low EP / low xmins, and high EP / nailed."""
    rows = []
    # ep 7.0 lands in EP bin 4 (edges [0,2,3,4,6]); 5.0 would land in bin 3.
    for ep, xmins, s in ((1.0, 10.0, sigma), (7.0, 85.0, sigma * 3)):
        for _ in range(n_per_cell):
            rows.append({"ep": ep, "xmins": xmins, "sigma_est": s})
    return pd.DataFrame(rows)


def test_a_cell_takes_the_mean_ensemble_spread_not_its_spread():
    out = fit_estimation_sigmas(_rows())
    assert out["sigma"]["0_0"] == 0.4
    assert out["sigma"]["4_3"] == 1.2000


def test_the_payload_carries_the_edges_and_the_v6_cell_threshold():
    out = fit_estimation_sigmas(_rows())
    assert out["ep_edges"] == EP_EDGES
    assert out["xmins_edges"] == XMINS_EDGES
    assert out["min_cell_obs"] == MIN_CELL_OBS


def test_a_thin_cell_is_left_out_so_serving_pools_it_up():
    out = fit_estimation_sigmas(_rows(n_per_cell=MIN_CELL_OBS - 1))
    assert out["sigma"] == {}
    assert out["obs"]["0_0"] == MIN_CELL_OBS - 1
    assert out["ep_marginal"]["0"] == 0.4


def test_a_cell_whose_ensemble_agrees_exactly_is_dropped_not_floored():
    """write_noise refuses a non-positive sigma and inventing one would be a
    lie about a cell where the five refits genuinely agree."""
    rows = _rows()
    rows.loc[rows["ep"] == 1.0, "sigma_est"] = 0.0
    out = fit_estimation_sigmas(rows)
    assert "0_0" not in out["sigma"]
    assert "0" not in out["ep_marginal"]
    # The cell and its EP marginal are both zero, and both are dropped.
    assert out["dropped_zero_cells"] == 2


def test_the_global_is_the_pooled_mean_spread():
    out = fit_estimation_sigmas(_rows())
    assert out["global"] == 0.8


def test_the_table_is_readable_by_the_untouched_serving_lookup():
    """Zero new serving code: sigma_for has to read this exactly as it reads
    the v6 residual table."""
    out = fit_estimation_sigmas(_rows())
    assert sigma_for(out, 1.0, 10.0) == 0.4
    assert sigma_for(out, 7.0, 85.0) == 1.2
    # EP bin 2 x xMins bin 1 is unpopulated and bin 2 has no marginal either,
    # so the lookup falls all the way through to the global.
    assert sigma_for(out, 3.5, 45.0) == out["global"]


def test_rows_with_no_xmins_are_dropped_rather_than_binned_at_zero():
    rows = _rows()
    rows.loc[rows.index[:10], "xmins"] = np.nan
    out = fit_estimation_sigmas(rows)
    assert out["rows"] == len(rows) - 10
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_estimation_noise.py -q` → `ImportError: cannot import name 'fit_estimation_sigmas'`.
- [ ] **Implement.** Append to `src/gaffer/calibrate_noise.py`:

```python
def fit_estimation_sigmas(rows: pd.DataFrame,
                          ep_edges: list[float] | None = None,
                          xmins_edges: list[float] | None = None,
                          min_obs: int = MIN_CELL_OBS) -> dict:
    """Ensemble spread -> the same σ table, cell for cell (spec §3).

    The one structural difference from :func:`fit_sigmas`: the per-row
    quantity here is *already* a standard deviation — the spread of one
    player-gameweek's EP across the K seeded refits — so a cell's value is the
    **mean** of its rows, not their standard deviation. Taking a standard
    deviation of standard deviations would price how much the estimation
    uncertainty itself varies within a cell, which is not a thing the sweep
    has any use for.

    Everything else is deliberately identical, because the read side is not
    changing: the same edges, the same ``MIN_CELL_OBS`` threshold, the same
    cell -> EP marginal -> global fallback chain that
    :func:`gaffer.optimize.scenarios.sigma_for` walks.

    A cell whose mean rounds to zero is **dropped** rather than floored at
    some invented epsilon. ``write_noise`` refuses a non-positive σ, and a
    cell where five refits agree to four decimal places has genuinely nothing
    to say; pooling it up to the EP marginal is the honest answer and is the
    same treatment a thin cell gets. The count is reported so the omission is
    visible.
    """
    ep_edges = EP_EDGES if ep_edges is None else list(ep_edges)
    xmins_edges = XMINS_EDGES if xmins_edges is None else list(xmins_edges)
    frame = rows.dropna(subset=["ep", "xmins", "sigma_est"]).copy()
    frame["ep_bin"] = [bin_index(v, ep_edges) for v in frame["ep"]]
    frame["x_bin"] = [bin_index(v, xmins_edges) for v in frame["xmins"]]

    dropped = 0
    marginal: dict[str, float] = {}
    marginal_obs: dict[str, int] = {}
    for i, part in frame.groupby("ep_bin"):
        value = round(float(part["sigma_est"].mean()), 4)
        marginal_obs[str(int(i))] = int(len(part))
        if value > 0.0:
            marginal[str(int(i))] = value
        else:
            dropped += 1

    sigma: dict[str, float] = {}
    obs: dict[str, int] = {}
    for (i, j), part in frame.groupby(["ep_bin", "x_bin"]):
        key = f"{int(i)}_{int(j)}"
        obs[key] = int(len(part))
        if len(part) < int(min_obs):
            continue
        value = round(float(part["sigma_est"].mean()), 4)
        if value > 0.0:
            sigma[key] = value
        else:
            dropped += 1

    return {
        "ep_edges": ep_edges,
        "xmins_edges": xmins_edges,
        "sigma": sigma,
        "obs": obs,
        "ep_marginal": marginal,
        "ep_marginal_obs": marginal_obs,
        "global": round(float(frame["sigma_est"].mean()), 4),
        "rows": int(len(frame)),
        "min_cell_obs": int(min_obs),
        "dropped_zero_cells": int(dropped),
    }
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_estimation_noise.py tests/test_calibrate_noise.py tests/test_scenarios.py -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/calibrate_noise.py tests/test_estimation_noise.py
git commit -m "feat: fit the 13-cell noise table from ensemble spread" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 9 — the K=5 ensemble row builder

- [ ] **Append the failing test** to `tests/test_estimation_noise.py`:

```python
def test_the_first_seed_is_the_shipped_fit_so_member_zero_is_not_refit():
    from gaffer.calibrate_noise import ESTIMATION_SEEDS

    assert len(ESTIMATION_SEEDS) == 5
    assert ESTIMATION_SEEDS[0] == LGB_KW["random_state"]


def test_a_seeded_bundle_only_replaces_the_two_lightgbm_heads():
    from gaffer.calibrate_noise import _seeded_bundle

    base = {"minutes": object(), "attacking": object(), "team": object(),
            "defcon": object(), "saves": object(), "bonus": object(),
            "calibration": object()}

    class _FakeMinutes:
        def __init__(self, cols, seed=None):
            self.seed = seed

        def fit(self, df):
            return self

    class _FakeAttack(_FakeMinutes):
        pass

    import gaffer.calibrate_noise as cn

    out = cn._seeded_bundle(base, pd.DataFrame({"a": [1]}), 17,
                            minutes_cls=_FakeMinutes, attack_cls=_FakeAttack)
    assert out["minutes"].seed == 17 and out["attacking"].seed == 17
    for shared in ("team", "defcon", "saves", "bonus", "calibration"):
        assert out[shared] is base[shared]
    assert base["minutes"] is not out["minutes"]     # base is not mutated


def test_ensemble_sigma_of_identical_members_is_zero():
    from gaffer.calibrate_noise import ensemble_sigma

    eps = [pd.DataFrame({"code": [1, 2], "gw": [5, 5], "ep": [4.0, 1.0]})
           for _ in range(5)]
    out = ensemble_sigma(eps)
    assert list(out["sigma_est"]) == [0.0, 0.0]
    assert list(out["k"]) == [5, 5]


def test_ensemble_sigma_grows_with_member_diversity():
    from gaffer.calibrate_noise import ensemble_sigma

    tight = [pd.DataFrame({"code": [1], "gw": [5], "ep": [4.0 + 0.01 * i]})
             for i in range(5)]
    loose = [pd.DataFrame({"code": [1], "gw": [5], "ep": [4.0 + 0.50 * i]})
             for i in range(5)]
    assert (float(ensemble_sigma(tight)["sigma_est"].iloc[0])
            < float(ensemble_sigma(loose)["sigma_est"].iloc[0]))


def test_ensemble_sigma_is_a_population_std_matching_the_v6_convention():
    from gaffer.calibrate_noise import ensemble_sigma

    eps = [pd.DataFrame({"code": [1], "gw": [5], "ep": [v]})
           for v in (1.0, 2.0, 3.0)]
    assert np.isclose(float(ensemble_sigma(eps)["sigma_est"].iloc[0]),
                      float(np.std([1.0, 2.0, 3.0])))
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_estimation_noise.py -q` → `ImportError: cannot import name 'ESTIMATION_SEEDS'`.
- [ ] **Implement.** Append to `src/gaffer/calibrate_noise.py`:

```python
ESTIMATION_SEEDS = (7, 17, 27, 37, 47)
"""The K=5 ensemble's LightGBM seeds.

``ESTIMATION_SEEDS[0]`` is :data:`gaffer.models.minutes.LGB_KW`'s own
``random_state``, asserted at fit time, so ensemble member zero **is** the
shipped bundle and is not refit. The other four are arbitrary and fixed: the
asset has to be reproducible from the committed constant, not from whatever
the machine's entropy was that afternoon.
"""

ESTIMATION_TRAIN_MAX_IDX = 2
ESTIMATION_TEST_IDX = 3
ESTIMATION_SEASON = "2025-26"
"""The estimation fit's walk-forward: train on 2022-23 to 2024-25, walk every
gameweek of 2025-26.

Spec §3 asks for the 2025-26 walk-forward, and this is the codebase's existing
one — :func:`gaffer.evaluation.benchmark_split` with the indices moved on a
season. A ten-slot holdout would be the other reading and would leave ~7 700
rows against this walk's ~29 700, too thin to populate a 13-cell grid at
:data:`MIN_CELL_OBS`. Scoring stays the **current** table, unrestated:
2025-26 did award defensive contribution, so ``benchmark_scoring``'s 2024-25
surgery would be wrong here.
"""


def _seeded_bundle(base: dict, train_df: pd.DataFrame, seed: int,
                   minutes_cls=None, attack_cls=None) -> dict:
    """``base`` with only the two LightGBM heads refit under ``seed``.

    Spec §3's ensemble is "the attacking heads + minutes model", and that is
    exactly what varies. Dixon-Coles is a deterministic maximum-likelihood fit
    with no seed to move, and the EP calibration, bonus, saves and defcon
    heads are shared so the measured spread is the estimation uncertainty of
    the two heads that carry it — not a wash of everything at once. Sharing
    them also turns five full refits into one plus four pairs.

    The class arguments exist so the unit test can substitute stubs; nothing
    else passes them.
    """
    from gaffer.models.attacking import ATTACK_FEATURES, AttackingModel
    from gaffer.models.minutes import ThreeModeModel
    from gaffer.models.train import MINUTES_FEATURES

    minutes_cls = ThreeModeModel if minutes_cls is None else minutes_cls
    attack_cls = AttackingModel if attack_cls is None else attack_cls
    out = dict(base)
    out["minutes"] = minutes_cls(MINUTES_FEATURES, seed=seed).fit(train_df)
    out["attacking"] = attack_cls(ATTACK_FEATURES, seed=seed).fit(train_df)
    return out


def ensemble_sigma(eps: list[pd.DataFrame]) -> pd.DataFrame:
    """``[code, gw, sigma_est, k]`` from K per-member EP frames.

    ``ddof=0`` to match :func:`fit_sigmas`: this is the spread of the K
    readings that were actually taken, not an estimate of a parameter of some
    population of refits they were drawn from.
    """
    stacked = pd.concat([e[["code", "gw", "ep"]] for e in eps],
                        ignore_index=True)
    out = stacked.groupby(["code", "gw"], as_index=False).agg(
        sigma_est=("ep", lambda s: float(s.std(ddof=0))), k=("ep", "size"))
    return out


def ensemble_rows(max_train_idx: int | None = None,
                  test_idx: int | None = None,
                  seeds: tuple[int, ...] = ESTIMATION_SEEDS) -> pd.DataFrame:
    """``[code, gw, ep, xmins, sigma_est]`` over the estimation walk-forward.

    ``ep`` and ``xmins`` are the **served** model's — member zero's — because
    those are the values the live sweep will bin on. Only ``sigma_est`` comes
    from the ensemble. Binning the ensemble mean instead would put a player in
    a cell the serving path would never look him up in.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.errors import GafferError
    from gaffer.evaluation import benchmark_split
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_matrix)
    from gaffer.models.minutes import LGB_KW
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)
    from gaffer.optimize.scenarios import xmins_by_player_gw

    if int(seeds[0]) != int(LGB_KW["random_state"]):
        raise ValueError(
            f"seeds[0] is {seeds[0]} but the shipped random_state is "
            f"{LGB_KW['random_state']} — member zero must be the served fit")
    max_train_idx = (ESTIMATION_TRAIN_MAX_IDX if max_train_idx is None
                     else max_train_idx)
    test_idx = ESTIMATION_TEST_IDX if test_idx is None else test_idx

    df, tg, _ = load_training_frame()
    train_df, test_df = benchmark_split(df, max_train_idx, test_idx)
    train_tg, _ = benchmark_split(tg, max_train_idx, test_idx)
    base = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                     save=False)
    members = [base] + [_seeded_bundle(base, train_df, s) for s in seeds[1:]]
    print(f"estimation ensemble: {len(members)} members", flush=True)
    scoring = scoring_table(load_bootstrap_sample())

    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        eps, served, xm = [], None, {}
        for member in members:
            comp = predict_components_simple(member, rows)
            ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                             member.get("calibration")))
            if served is None:
                served, xm = ep, xmins_by_player_gw(comp)
            eps.append(ep)
        joined = served.merge(ensemble_sigma(eps), on=["code", "gw"],
                              how="inner")
        joined["xmins"] = [float(xm.get((int(c), int(g)), float("nan")))
                           for c, g in zip(joined["code"], joined["gw"])]
        parts.append(joined[["code", "gw", "ep", "xmins", "sigma_est"]])
        print(f"estimation gw{gw}: {len(parts[-1])} rows", flush=True)

    if not parts:
        raise GafferError(
            "no rows to fit an estimation sigma on — run "
            "`gaffer build-history` and `gaffer train` first")
    return pd.concat(parts, ignore_index=True)
```

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_estimation_noise.py tests/test_calibrate_noise.py -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/calibrate_noise.py tests/test_estimation_noise.py
git commit -m "feat: K=5 seed-bagged ensemble rows for the estimation sigma" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 10 — `run_estimation_calibration` and `gaffer calibrate-noise --estimation`

- [ ] **Append the failing test** to `tests/test_estimation_noise.py`:

```python
def test_the_estimation_payload_is_marked_at_its_source(monkeypatch):
    import gaffer.calibrate_noise as cn

    monkeypatch.setattr(cn, "ensemble_rows", lambda *a, **k: _rows())
    payload = cn.run_estimation_calibration()
    assert payload["source"] == "estimation"
    assert payload["season"] == cn.ESTIMATION_SEASON
    assert payload["k"] == len(cn.ESTIMATION_SEEDS)
    assert payload["seeds"] == list(cn.ESTIMATION_SEEDS)
    assert payload["version"] == 1
    assert payload["generated_at"] and payload["git_sha"]


def test_the_residual_payload_is_marked_too(monkeypatch):
    """The two assets have to be distinguishable on disk, or a future cycle
    cannot tell which σ it is looking at."""
    import gaffer.calibrate_noise as cn

    monkeypatch.setattr(cn, "residual_rows", lambda *a, **k: pd.DataFrame(
        {"ep": [1.0] * 120, "xmins": [10.0] * 120, "points": [1.0] * 120}))
    assert cn.run_calibration()["source"] == "residual"


def test_the_estimation_payload_passes_the_shipped_validator(tmp_path,
                                                             monkeypatch):
    import gaffer.calibrate_noise as cn

    monkeypatch.setattr(cn, "ensemble_rows", lambda *a, **k: _rows())
    dest = cn.write_noise(cn.run_estimation_calibration(),
                          tmp_path / "scenario_noise.json")
    import json

    assert json.loads(dest.read_text())["source"] == "estimation"


def test_the_cli_carries_the_estimation_mode_and_an_out_path():
    import inspect

    from gaffer.cli import calibrate_noise

    params = inspect.signature(calibrate_noise).parameters
    assert "estimation" in params and "out" in params
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_estimation_noise.py -q` → `AttributeError: module 'gaffer.calibrate_noise' has no attribute 'run_estimation_calibration'`.
- [ ] **Implement.** In `src/gaffer/calibrate_noise.py`, add `"source": "residual"` to `run_calibration`'s `payload.update({...})` block, and append:

```python
def run_estimation_calibration(max_train_idx: int | None = None,
                               test_idx: int | None = None,
                               seeds: tuple[int, ...] = ESTIMATION_SEEDS
                               ) -> dict:
    """The estimation-only σ asset (spec §3).

    Same payload shape as :func:`run_calibration`, so the serving path reads
    it without a line of new code — ``"source"`` is the only field that says
    which question the numbers answer. Gate S1 failed because the residual σ
    conflated forecast error with football's irreducible variance; this one
    prices the model's own uncertainty and nothing else, which is what a
    "would this transfer survive my forecast being wrong" sweep is asking.
    """
    from gaffer.evaluation import git_sha, run_at

    rows = ensemble_rows(max_train_idx, test_idx, seeds)
    payload = fit_estimation_sigmas(rows)
    payload.update({
        "version": 1,
        "generated_at": run_at(),
        "git_sha": git_sha(),
        "season": ESTIMATION_SEASON,
        "source": "estimation",
        "k": len(seeds),
        "seeds": list(int(s) for s in seeds),
    })
    return payload
```

Replace the CLI command body in `src/gaffer/cli.py`:

```python
@app.command("calibrate-noise")
def calibrate_noise(
    estimation: bool = typer.Option(
        False, "--estimation",
        help="Fit the estimation-only sigma (K=5 seed-bagged ensemble "
             "spread) instead of the residual sigma — v7-model spec §3."),
    out: Path = typer.Option(
        None, "--out",
        help="Where to write the asset. Defaults to the shipped path; point "
             "it at reports/ to fit a candidate without replacing the asset."),
):
    """Fit src/gaffer/assets/scenario_noise.json.

    Two modes, one asset shape. Without ``--estimation`` this is the v6
    residual σ, fitted on benchmark residuals: slow, refreshed once a season.
    With ``--estimation`` it is the v7 spread of a five-seed LightGBM
    ensemble over the 2025-26 walk-forward — how unsure the *model* is rather
    than how random football is, which is the follow-up gate S1's failure
    pre-registered.

    Either asset ships in git; without one the scenario sweep falls back to
    the (92 - xmins) / 134 heuristic, which is the pre-v6 behaviour.
    """
    from gaffer.calibrate_noise import (ASSET_PATH, run_calibration,
                                        run_estimation_calibration,
                                        write_noise)

    payload = (run_estimation_calibration() if estimation
               else run_calibration())
    dest = write_noise(payload, out or ASSET_PATH)
    typer.echo(f"Fitted {len(payload['sigma'])} cells and "
               f"{len(payload['ep_marginal'])} EP marginals from "
               f"{payload['rows']} rows on {payload['season']} "
               f"(source {payload['source']}, "
               f"global sigma {payload['global']}) -> {dest}")
```

`Path` is already imported in `cli.py` (used by `calibrate-injuries`); confirm with `grep -n "^from pathlib" src/gaffer/cli.py` and add `from pathlib import Path` at the top if it is not there.

- [ ] **Run it and watch it pass:** `.venv/bin/python -m pytest tests/test_estimation_noise.py tests/test_calibrate_noise.py tests/test_cli.py -q` → all passed.
- [ ] **Commit:**

```bash
git add src/gaffer/calibrate_noise.py src/gaffer/cli.py tests/test_estimation_noise.py
git commit -m "feat: gaffer calibrate-noise --estimation writes the ensemble sigma" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 11 — `scripts/s2_replay.py`, the gated-replay driver (build only — do not run it)

- [ ] **Append the failing test** to `tests/test_v7_model_degradation.py`:

```python
def test_the_s2_driver_is_committed_and_uses_the_shipping_path():
    """The gate must measure what shipping would do: the estimation arm flips
    CALIBRATED_NOISE_DEFAULT and stubs the loader, which is exactly what Task
    18 does permanently — not a bespoke table= thread the live path lacks."""
    from pathlib import Path

    src = Path("scripts/s2_replay.py").read_text()
    assert "CALIBRATED_NOISE_DEFAULT" in src
    assert "load_scenario_noise" in src
    assert "scenario_noise.cache_clear()" in src
    assert "S2_ARM_DONE" in src
    assert "20260827 + gw" in src          # the S1 seed, unchanged
    assert "n=40" in src
```

- [ ] **Run it and watch it fail:** `.venv/bin/python -m pytest tests/test_v7_model_degradation.py -q -k s2` → `FileNotFoundError: scripts/s2_replay.py`.
- [ ] **Implement** `scripts/s2_replay.py`:

```python
"""Gate S2: the 2025-26 gated replay, heuristic σ against estimation σ.

The corrected S1 driver, committed. ``run_backtest`` never touches the
scenario machinery — scenario gating is an advise-time feature — so this
injects it the way the v4c gated replay did: stash the component frame the
replay computes each week, derive real xMins from it, and wrap the replay's
BASE solve with ``run_scenarios`` -> ``decide`` -> ``coherent_plan``. Chip
valuation and execution solves (``wildcard_gw`` set, or ``free_transfers ==
15`` for a Free Hit and the opening squad) stay raw, mirroring production.

The arms differ ONLY in the noise scale:

  heur        the pre-v6 (92 - xmins) / 134 heuristic (loader pinned to None)
  estimation  the payload at argv[2], installed through the *shipping* path

The estimation arm deliberately flips ``CALIBRATED_NOISE_DEFAULT`` and stubs
``load_scenario_noise`` rather than threading a ``table=`` kwarg, because
``run_scenarios`` -> ``noised_pool`` passes no table and resolves through
``scenario_noise()``. Flipping the constant is what Task 18 does permanently,
so the gate measures what shipping would actually do.

Usage::

    caffeinate -i nohup .venv/bin/python scripts/s2_replay.py heur \\
        > logs/s2_heur.log 2>&1 &
    caffeinate -i nohup .venv/bin/python scripts/s2_replay.py estimation \\
        reports/scenario_noise_estimation.json > logs/s2_est.log 2>&1 &
    grep S2_ARM_DONE logs/s2_*.log

Ship (spec §3) only if the estimation arm's total is at least the heuristic
arm's minus 5 — a tie is a win for the better-founded noise model — AND
captain sim-support on the current live advise stays at or above 60%.
"""

import json
import sys
from pathlib import Path

import pandas as pd

import gaffer.backtest as bt
import gaffer.optimize.scenarios as sc
from gaffer.optimize.policy import Thresholds, coherent_plan, decide
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)

mode = sys.argv[1]
assert mode in ("heur", "estimation")
if mode == "heur":
    sc.load_scenario_noise = lambda: None
    sc.scenario_noise.cache_clear()
    assert sc.scenario_noise() is None, "heuristic arm must serve no table"
else:
    payload = json.loads(Path(sys.argv[2]).read_text())
    assert payload.get("source") == "estimation", \
        f"argv[2] is a {payload.get('source')!r} table, not an estimation one"
    sc.CALIBRATED_NOISE_DEFAULT = True
    sc.load_scenario_noise = lambda: payload
    sc.scenario_noise.cache_clear()
    assert sc.scenario_noise() is payload, "asset missing — arm invalid"

_stash: dict = {}
_real_pcs = bt.predict_components_simple


def pcs(models, rows):
    comp = _real_pcs(models, rows)
    _stash["xmins"] = xmins_by_player_gw(comp)
    return comp


bt.predict_components_simple = pcs

_real_solve = bt.solve_plan
gated_weeks = held_weeks = 0


def gated(pool, state, **kw):
    global gated_weeks, held_weeks
    plan = _real_solve(pool, state, **kw)
    if (not state.owned_codes or state.wildcard_gw is not None
            or state.free_transfers >= 15):
        return plan
    xm = _stash.get("xmins") or {}
    if not xm:
        return plan
    gw = int(state.gws[0])
    run = run_scenarios(pool, state, xm, n=40, seed=20260827 + gw, **kw)
    if not run.completed:
        return plan
    gated_weeks += 1
    decision = decide(move_frequencies(run.plans), plan, Thresholds())
    if decision.hold:
        held_weeks += 1
    return coherent_plan(pool, state, decision, **kw)


bt.solve_plan = gated

r = bt.run_backtest(season="2025-26", start_gw=5, horizon=3, chips=True)
d = pd.read_parquet("data/live/backtest_log.parquet")
chip_pts = d[d["chip"] != ""].groupby("chip")["points"].sum().to_dict()
print("S2_ARM_DONE", mode, json.dumps({
    "total": r["total"],
    "hits": int(d["hits"].sum()),
    "transfers": int(d["transfers"].sum()),
    "gated_weeks": gated_weeks,
    "held_weeks": held_weeks,
    "chips_played": r["chips_played"],
    "chip_points": {str(k): int(v) for k, v in chip_pts.items()},
}), flush=True)
```

- [ ] **Run the test, not the driver:** `.venv/bin/python -m pytest tests/test_v7_model_degradation.py -q` → all passed. **Do not execute `scripts/s2_replay.py`** — it is the orchestrator's gate (Task 17), and it needs an estimation asset that does not exist yet.
- [ ] **Syntax-check it:** `.venv/bin/python -m py_compile scripts/s2_replay.py` → no output.
- [ ] **Commit:**

```bash
git add scripts/s2_replay.py tests/test_v7_model_degradation.py
git commit -m "feat: committed gate S2 gated-replay driver" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Group 3 — the deferred UI nit (Tasks 12-13)

A third implementer owns this group and can run fully in parallel — it touches no Python at all.

### Task 12 — `Card` gains `titleSize`

- [ ] **Append the failing test** to `frontend/src/kit/Card.test.tsx`:

```tsx
  it('renders the title as a small uppercase label by default', () => {
    render(<Card title="Squad"><p>inside</p></Card>)
    expect(screen.getByRole('heading', { name: 'Squad' }))
      .toHaveClass('label')
  })

  it('renders the title at primary text size when asked', () => {
    render(<Card title="Saka" titleSize="lg"><p>inside</p></Card>)
    const heading = screen.getByRole('heading', { name: 'Saka' })
    expect(heading).toHaveClass('text-lg')
    expect(heading).toHaveClass('text-text')
    expect(heading).not.toHaveClass('label')
  })

  it('keeps the action slot beside a large title', () => {
    render(
      <Card title="Saka" titleSize="lg" action={<span>MID</span>}>
        <p>inside</p>
      </Card>,
    )
    expect(screen.getByText('MID')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Saka' })).toBeInTheDocument()
  })
```

- [ ] **Run it and watch it fail:** from `frontend/`, `npm test -- --run src/kit/Card.test.tsx` → the `titleSize` assertions fail (the heading still carries `label`), and `npx tsc -b` reports `Property 'titleSize' does not exist on type 'CardProps'`.
- [ ] **Implement** `frontend/src/kit/Card.tsx`:

```tsx
import type { ReactNode } from 'react'

/**
 * `titleSize` exists because a card is used for two different things: a
 * section of a page, whose title is chrome and belongs in the 9px uppercase
 * label voice, and a card *about* something — a player, in ComparePanel —
 * whose title is the content and has to read as such.
 */
export interface CardProps {
  title?: string
  titleSize?: 'sm' | 'lg'
  action?: ReactNode
  children: ReactNode
  className?: string
}

const TITLE_CLASS = {
  sm: 'label',
  lg: 'text-lg font-medium text-text',
} as const

export default function Card({
  title, titleSize = 'sm', action, children, className,
}: CardProps) {
  return (
    <section
      className={`rounded-card border border-border bg-card ${className ?? ''}`}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b
                           border-divider px-4 py-3">
          {title && <h2 className={TITLE_CLASS[titleSize]}>{title}</h2>}
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
```

- [ ] **Run it and watch it pass:** from `frontend/`, `npm test -- --run src/kit/Card.test.tsx` → 6 passed; `npx tsc -b` → no output.
- [ ] **Commit:**

```bash
git add frontend/src/kit/Card.tsx frontend/src/kit/Card.test.tsx
git commit -m "feat: Card takes an optional large title size" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

### Task 13 — ComparePanel renders the player's name prominently

- [ ] **Append the failing test** to `frontend/src/hubs/players/ComparePanel.test.tsx`:

```tsx
  it('renders each compared player name at primary text size', async () => {
    render(<ComparePanel gw={5} players={[playerA, playerB]} />)
    const name = await screen.findByRole('heading', { name: playerA.name })
    expect(name).toHaveClass('text-lg')
    expect(name).not.toHaveClass('label')
  })

  it('keeps the position badge beside the name', async () => {
    render(<ComparePanel gw={5} players={[playerA, playerB]} />)
    const card = await screen.findByTestId(`compare-${playerA.code}`)
    expect(within(card).getByRole('heading', { name: playerA.name }))
      .toBeInTheDocument()
    expect(within(card).getByText(playerA.position)).toBeInTheDocument()
  })
```

Add `within` to the existing `@testing-library/react` import in that file, and reuse whatever `playerA`/`playerB` fixtures the suite already defines (rename to match if they are called something else — read the file first).

- [ ] **Run it and watch it fail:** from `frontend/`, `npm test -- --run src/hubs/players/ComparePanel.test.tsx` → `expect(element).toHaveClass("text-lg")` fails.
- [ ] **Implement.** One line in `frontend/src/hubs/players/ComparePanel.tsx`:

```tsx
              <Card title={player.name} titleSize="lg"
                    action={<PosBadge pos={player.position} />}>
```

- [ ] **Run it and watch it pass:** from `frontend/`, `npm test -- --run src/hubs/players/ComparePanel.test.tsx` → all passed.
- [ ] **Full frontend sweep:** from `frontend/`, `npm test -- --run` → all passed; `npx tsc -b` → no output; `npm run build` → built (its output under `src/gaffer/web/static/` is gitignored and is never staged).
- [ ] **Commit:**

```bash
git add frontend/src/hubs/players/ComparePanel.tsx \
        frontend/src/hubs/players/ComparePanel.test.tsx
git commit -m "feat: compare cards lead with the player name, not a label" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Group 4 — gates, shipping decisions and the record (Tasks 14-20)

**Every task in this group is the orchestrator's.** No implementer may run a gate, flip a shipping constant, or write a §9 outcome. Groups 1-3 must be complete and green before Task 14 starts.

### Task 14 — run the diagnostic (orchestrator)

- [ ] Run it, watch it, read it:

```bash
mkdir -p logs
caffeinate -i nohup .venv/bin/gaffer diagnose-zeros \
  > logs/zeros_diagnostic.log 2>&1 &
```

Poll with `grep -e "zeros diagnostic" -e "decile" -e "^   " logs/zeros_diagnostic.log`.

- [ ] Read `reports/zeros_diagnostic.json`. Expected shape: `overall.n` ≈ 4929 (the harness's zeros count), `strata.flagged.n == 0` with its note, and a `dnp_reliability` curve whose `pred` sits **above** `obs` in the mid deciles if the over-forecast hypothesis holds.
- [ ] Record the table verbatim in spec §9 under "M1 diagnostic". If the DNP curve is already well calibrated, I1 is unlikely to clear Z1 — run it anyway (it is cheap, it is pre-registered, and a negative result is a result), and record the diagnostic's disagreement.
- [ ] Record **I2 infeasible** in §9 with the evidence from Interpretations §I-C: every registered element has a row every gameweek (2025-26 GW10: 747 rows, 29-45 per club), all zero-minute rows carry `bps`/`starts`/`cs`/`gc` of 0, and no column separates an unused substitute from a player never named — so neither `unused_sub_r5` nor `squad_share_r5` is derivable, and spec §2.2 forbids scraping for them.
- [ ] Nothing to commit — `reports/` is gitignored.

### Task 15 — gate Z1 (orchestrator)

- [ ] Hand to the orchestrator. Exact command:

```bash
caffeinate -i nohup .venv/bin/python scripts/z1_arms.py \
  > logs/z1_arms.log 2>&1 &
```

Poll with `grep -e Z1_ARM_DONE -e Z1_VERDICT logs/z1_arms.log`.

- [ ] Read `Z1_VERDICT`. The pre-registered rule, against the 2026-08-29 baseline (zeros 1.063, haulers 5.145, all 1.986):
  - `zeros <= 1.042` (≥ 2% better, i.e. at least to the last-5 baseline) **AND**
  - `haulers <= 5.171` (no worse than 0.5%) **AND**
  - `all <= 1.996` (no worse than 0.5%).
- [ ] Sanity-check that the `off` arm reproduces the baseline within rounding (zeros 1.063, haulers 5.145). If it does not, the harness moved for some other reason and the gate is void — investigate before reading the `on` arm.
- [ ] Record both arms and the verdict in spec §9.

### Task 16 — fit the estimation asset (orchestrator)

- [ ] Run it to a scratch path so nothing is clobbered before the verdict:

```bash
caffeinate -i nohup .venv/bin/gaffer calibrate-noise \
  --estimation --out reports/scenario_noise_estimation.json \
  > logs/estimation_noise.log 2>&1 &
```

Poll with `grep -e "estimation ensemble" -e "estimation gw" -e "Fitted" logs/estimation_noise.log`. Expect 5 members, 38 gameweek lines, and a `Fitted ... source estimation` tail.

- [ ] Check the payload before spending a replay on it: `global` well inside `(0, 10)`, `sigma` non-empty, and — the interesting comparison — every cell **smaller** than the v6 residual table's same cell. If the estimation σ is not materially smaller than the residual σ, the ensemble is not measuring what §3 claims and S2 should not be run until that is understood. Record the two tables side by side in §9 either way.
- [ ] If `write_noise` refuses the payload (a global σ that rounds to zero), record S2 as **unrunnable** with that finding and skip Tasks 17-18's flip half; Task 18 still restates the v6 asset's docstring.

### Task 17 — gate S2 (orchestrator)

- [ ] Hand to the orchestrator. Two arms, sequential (each is a full 2025-26 replay with 40 scenario solves a week):

```bash
caffeinate -i nohup .venv/bin/python scripts/s2_replay.py heur \
  > logs/s2_heur.log 2>&1 &
# wait for S2_ARM_DONE, then:
caffeinate -i nohup .venv/bin/python scripts/s2_replay.py estimation \
  reports/scenario_noise_estimation.json > logs/s2_est.log 2>&1 &
```

Poll with `grep S2_ARM_DONE logs/s2_*.log`.

- [ ] Then the live sim-support half:

```bash
cp reports/scenario_noise_estimation.json src/gaffer/assets/scenario_noise.json
.venv/bin/python - <<'PY'
import gaffer.optimize.scenarios as sc
sc.CALIBRATED_NOISE_DEFAULT = True
sc.scenario_noise.cache_clear()
from gaffer.advise import run_advise
from gaffer.config import load_config
advice = run_advise(load_config())
print("S2_LIVE_SUPPORT", advice.scenarios.get("captain_frequency"))
PY
git checkout -- src/gaffer/assets/scenario_noise.json
```

(`advice.scenarios["captain_frequency"]` is also readable from `reports/gw{N}-advice.json` after the run. Restore the asset afterwards so Task 18 is the only commit that changes it.)

- [ ] The pre-registered rule (spec §3): ship — flip `CALIBRATED_NOISE_DEFAULT = True` — only if `estimation_total >= heur_total - 5` **AND** live captain sim-support `>= 0.60`. A tie is a win for the better-founded noise model. Fail → the asset is committed with `"source": "estimation"`, the default stays `False`, and the result is recorded.
- [ ] Record both arms' totals, hits, transfers, `gated_weeks`, `held_weeks`, chip points and the live sim-support number in spec §9.

### Task 18 — the shipping flips (orchestrator, conditional)

Two independent one-line decisions. Each is its own commit and each names the numbers that justified it.

- [ ] **If Z1 PASSED**, flip I1 on. In `src/gaffer/models/minutes.py`, `DNP_CALIBRATION_DEFAULT = True` and replace the docstring's "**Off, pending gate Z1.**" paragraph with the measured result (zeros before → after, haulers before → after, all before → after, and the run's `git_sha`). Then update rails 1, 2 and 4 in `tests/test_v7_model_degradation.py`: `test_the_dnp_calibration_is_off_by_default` becomes `test_the_dnp_calibration_ships_on` asserting `True` and naming the gate; `test_the_flag_off_*` rails keep their coverage by `monkeypatch.setattr(mn, "DNP_CALIBRATION_DEFAULT", False)` at the top of each, which is what a clone-with-the-flag-off must still do. Run `.venv/bin/python -m pytest -q` — the whole suite, because this changes what every model fit does.

```bash
git add src/gaffer/models/minutes.py tests/test_v7_model_degradation.py
git commit -m "feat: ship the DNP recalibration, gate Z1 passed" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

- [ ] **If Z1 FAILED**, change no code. The constant is already `False` and rail 2 already pins it. Extend the constant's docstring with the measured negative result (the v5 N1 / v6 S1 pattern: what was tried, what it scored, why it was not shipped) and commit only `src/gaffer/models/minutes.py` with `docs: record the gate Z1 negative result`.

- [ ] **Either way, ship the estimation asset** (spec §3: the v6 residual asset is superseded pass or fail):

```bash
cp reports/scenario_noise_estimation.json src/gaffer/assets/scenario_noise.json
.venv/bin/python -m pytest tests/test_v6_degradation.py tests/test_scenarios.py -q
```

Both suites must pass **unedited** — that is the proof the estimation table is a drop-in.

- [ ] **If S2 PASSED**, set `CALIBRATED_NOISE_DEFAULT = True` in `src/gaffer/optimize/scenarios.py` and rewrite its docstring: what S1 measured, why the residual σ was the wrong quantity, what S2 measured on the estimation σ, and the two numbers that cleared the rule. Note that `tests/test_v6_degradation.py::test_the_shipped_asset_is_not_served_by_default` and `::test_the_default_path_is_the_pre_v6_heuristic_value_for_value` will now fail and **must be updated in this commit** — they are v6's pins on a decision v7 has overturned, and the update is the deliberate one clause 5 of the hard constraints allows.
- [ ] **If S2 FAILED**, leave `CALIBRATED_NOISE_DEFAULT = False`, append the S2 result to its docstring beneath the S1 paragraph, and change nothing else. Every v6 rail keeps passing unedited.

```bash
git add src/gaffer/assets/scenario_noise.json src/gaffer/optimize/scenarios.py
git commit -m "feat: supersede the residual sigma with the estimation-only asset" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

- [ ] **Full sweep after every flip:** `.venv/bin/python -m pytest -q` → all passed.

### Task 19 — N2, the first news verdict (orchestrator checklist, conditional)

Not implementer work: no code changes are needed. `gaffer evaluate --news-shadow`, `evaluate_news_shadow()` and the current-season filter all already exist and are already tested.

- [ ] Check whether FPL has marked GW2 `data_checked` (the live events snapshot, or simply whether `data/live/player_gw.parquet` carries GW2 rows — today it stops at GW1).
- [ ] **If it has:** `.venv/bin/gaffer evaluate --news-shadow`, which writes `reports/evaluation.json` under the `news_shadow` key and prints the per-gameweek Brier/MAE table. Record the scored verdict in spec §9 — Brier news vs flags and minutes MAE news vs flags, per gameweek and cumulative — and confirm the Model hub's Quality tab renders it (`gaffer ui`, Model → Quality).
- [ ] **If it has not:** record `"pending — run after GW2"` in spec §9 and **do not block the merge decision on it** (spec §4).
- [ ] Nothing to commit — `reports/` is gitignored.

### Task 20 — the record (orchestrator)

- [ ] Write spec §9 "Outcome" in `docs/superpowers/specs/2026-08-30-gaffer-v7-model-design.md`, covering: the M1 diagnostic table; **I2 recorded infeasible** with the stored-data evidence; I3 recorded rejected (unchanged from §2.2); gate Z1's two arms and verdict and what shipped; the estimation-σ asset's cells against v6's; gate S2's two arms, the live sim-support number, the verdict and what shipped; the N2 verdict or its "pending" note; and the UI nit as done.
- [ ] Add one line to `README.md`'s feature list for whichever of I1 / estimation-σ actually shipped on. If neither did, add nothing — a negative result belongs in the spec and the constant's docstring, not in the README.
- [ ] **Full sweep:** `.venv/bin/python -m pytest -q` from the repo root, and `npm test -- --run && npx tsc -b && npm run build` from `frontend/`.
- [ ] **Commit:**

```bash
git add docs/superpowers/specs/2026-08-30-gaffer-v7-model-design.md README.md
git commit -m "docs: v7-model cycle outcome" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

- [ ] Then adversarial review, fix rounds, and the merge decision per spec §0 D3: merge to `main` and push only if **every** gate's shipping decision was clean-cut under its pre-registered rule and the review ends MERGE. Anything ambiguous stays on `feat/gaffer-v7-model` for the user.

---

## Group summary

| Group | Owner | Tasks | Count |
| --- | --- | --- | --- |
| 1 — M1 diagnostic + I1 | Implementer A | 1-6 | 6 |
| 2 — M2 estimation σ | Implementer B | 7-11 | 5 |
| 3 — UI nit | Implementer C | 12-13 | 2 |
| 4 — gates, flips, record | **Orchestrator** | 14-20 | 7 |

Groups 1, 2 and 3 may run in parallel; the only file two groups touch is `src/gaffer/models/minutes.py` (Task 5's `fit`/`predict_modes`, Task 7's `__init__`), so Task 7 should follow Task 5. Group 4 begins only when 1-3 are complete and `.venv/bin/python -m pytest -q` is green.
