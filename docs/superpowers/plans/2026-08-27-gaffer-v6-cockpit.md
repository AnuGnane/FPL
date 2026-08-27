# Gaffer v6 "Cockpit" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two small, gate-measurable model pieces plus a four-piece UI half that makes the advisor's decisions inspectable. M2 prices the increment a new penalty taker adds over what his own history already priced in. M3 replaces the never-fitted scenario-noise heuristic with an empirical residual-σ table. U1–U4 turn the artifacts `advise` already writes — plus two new ones — into a chip workbench, a why-this-plan panel, a news-transparency panel and an N2 scoreboard. Every piece degrades to today's behaviour when its input is missing, and the degradation rails are part of the deliverable.

**Architecture:** A new `src/gaffer/set_pieces.py` owns the whole penalty term: `pen_priors(hist)` (trailing share of his club's penalties per player), `attack_multipliers(team_model)` (Dixon-Coles attack strength vs league mean), `pen_table` / `add_pen_ep` / `pen_notices`. `advise.predict_components` gains a fifth optional argument and one call at the very end of the function, after the availability passes and after the protected `blend_team_odds(` → `comp.merge(tp` seam; `run_advise` gains one line above the `avail =` line and two lines at the very bottom, after `save_solve_state(`. `optimize/scenarios.noise_ep` grows a σ-lookup path behind an `lru_cache`d `scenario_noise()` reading a new committed asset `src/gaffer/assets/scenario_noise.json`, written by a new `src/gaffer/calibrate_noise.py` driven by `gaffer calibrate-noise`, which reuses `evaluation.benchmark_split` / `models.train.predict_components_simple` / `scenarios.xmins_by_player_gw` rather than re-deriving the walk-forward. `artifacts.py` grows the availability snapshot and the pruned advice-history log beside the solve state it already persists. Four read-only endpoints (`/api/chips`, `/api/components/{gw}`, `/api/advice/diff`, `/api/news/{gw}`) serve those artifacts to a new `ChipWorkbench` page and two new `ThisWeek` panels, plus a "News layer" section on `Quality`.

**Tech Stack:** Python 3.12, pandas, numpy, LightGBM, PuLP + HiGHS, FastAPI + Pydantic, Typer, pytest (`uv run pytest`); React 18 + TypeScript + Vite + vitest + @testing-library/react (`npx vitest run`, `npx tsc -b`, `npm run build` from `frontend/`).

---

## Hard constraints — read before writing a line of code

1. **TDD, always.** Failing test first, minimal implementation second, both shown in every step below.
2. **Never `git add -A`.** Stage only the files each step names. Never stage `config.toml` (it carries a live odds API key), `data/`, `reports/`, `models/`, `.claude/`. `src/gaffer/web/static/` is **gitignored** — `npm run build` output is never staged, and the build step below exists to prove the page compiles, not to commit anything.
3. **The real `src/gaffer/assets/scenario_noise.json` is NOT written by this plan.** Task 4 ships the calibration code, the CLI, the validator and a *fixture* asset under `tests/data/scenario_noise.json`. The orchestrator runs `gaffer calibrate-noise` later and commits the real asset then. Until it exists, `load_scenario_noise()` returns `None` and every sweep uses today's heuristic — which is exactly the rail Task 3 pins.
4. **The degradation rails are sacred.** All taker fields None ⇒ components unchanged column for column; no Understat/xG history ⇒ `pen_priors` returns `None` ⇒ the term is identically zero; no noise asset ⇒ the pre-v6 heuristic, value for value; no components / availability / history / shadow artifact ⇒ the panel hides and `advise` is unaffected. Task 14 restates all of them.
5. **Protected source-text suites are sacred.** See the next section.
6. **No new config.** Every v6 feature is on by default and degrades silently. Nothing in this plan touches `src/gaffer/config.py`.
7. **`reports/` stays untracked.** The only asset this cycle will ever commit is `scenario_noise.json`, and not in this plan.
8. **Frequent small commits**, one per task, each ending with:

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

---

## Protected source-text tests — read this before touching `advise.py`

These suites assert on the **source text** of `run_advise` and `predict_components`, because there is no cheap end-to-end harness for either. Verified against the tree at the time of writing:

- `tests/test_advise.py:74-94` — inside `run_advise`:
  `src.index("fetch_rival_entries(") < src.index("tilt_ep(") < src.index("pool = build_pool(")`,
  `src.index("compute_strategy(") < pool`, `"except Exception" in src`,
  `'summary_overall_points' in src`, and the literal `"build_pool(players, pool_ep," in src`.
- `tests/test_advise.py:97-109` — also inside `run_advise`: `"ep_named = ep.merge(" in src`,
  `'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src`,
  **`"pool_ep" not in src[src.index("ep_gw1 ="):]`**, and
  `'_named(first.xi, name_of, pos_of, ep_by, gw)' in src`.
- `tests/test_advise.py:251-266` — inside `predict_components`:
  `'tp["p_cs_model"] = tp["p_cs"].values' in src`, `'tp["e_gc_model"] = tp["e_gc"].values' in src`,
  `'tp["odds_weight"]' in src`, and each of `"was_home"`, `"kickoff_time"`, `"pen_taker"`,
  `"setpiece_taker"` present as a quoted literal.
- `tests/test_advise.py:268-280` — inside `run_advise`: `"save_components("`, `"save_solve_state("`,
  `"save_snapshots(players, teams, events, fx)"`, `"pool_rows(pool, players, owned_now, ep_by, gws)"`.
- `tests/test_odds.py:355-362` — inside `run_advise`: `'store.save(odds_df, f"live/odds/gw{gw}.parquet")' in src`.
- `tests/test_odds.py:365-378` and `tests/test_odds.py:595-604` — inside `predict_components`:
  `src.index("blend_team_odds(") < src.index("comp.merge(tp")`, plus `"odds_blend_weight()" in src`.
- `tests/test_odds.py:981-995` — inside `run_advise`:
  `src.index("comp = predict_components(") < src.index("blend_attacking_odds(") <
  src.index("ep_matrix(apply_calibration(assemble_ep(")`, plus `"cfg.player_props" in src`
  and **`"except Exception" in src[blend - 600:blend + 600]`**.
- `tests/test_assemble.py:215` — `"ep_matrix(apply_calibration(assemble_ep("` in **both** `run_advise` and `run_backtest`.
- `tests/test_v5_degradation.py:264-302` — rail 4 restates all of the above plus
  `src.index("avail = news_availability(") < comp` and
  `comp < src.index("write_shadow(comp, gw)") < blend`.

**Consequences for this plan, restated as rules:**

- **`run_advise` gains exactly three lines in this whole cycle.**
  - Task 2: `pens = pen_priors(hist)` — one line, immediately **above** the existing
    `avail = news_availability(cfg, players, teams, events, gw)` line, and the existing
    `comp = predict_components(pred_frame, tg_future, players, avail)` call grows a
    **fifth positional argument** (`, pens`). The literal `comp = predict_components(`
    survives; the call never becomes a tuple unpack.
  - Task 5: `save_availability(avail, gw)` and `append_advice_history(asdict(advice), gw)`,
    both at the **very bottom** of the function, after the `save_solve_state(SolveState(...))`
    call closes. That region is below `ep_gw1 =`, so **neither line may contain the substring
    `pool_ep`** — they do not, and no other v6 insertion goes anywhere near the pool.
- Each inserted line is well under 70 characters, so the `src[blend - 600:blend + 600]`
  window around `blend_attacking_odds(` still contains the player-props `except Exception`
  block. Tasks 2 and 5 both re-run `tests/test_odds.py` to prove it.
- **All the real work lives in helper functions outside `run_advise`** — `pen_priors`,
  `save_availability`, `append_advice_history` — which is what keeps the source text stable.
- **`predict_components` gains one optional keyword and one statement.** The keyword is
  `pens: PenPriors | None = None` (fifth parameter, defaulted, so every existing four-argument
  call site still works). The statement is a single `comp = add_pen_ep(...)` line placed
  **after** `comp["e_gc"] = comp["e_gc"].fillna(DEFAULT_E_GC)` and immediately before
  `return comp`. That is after both availability passes and after the pinned
  `blend_team_odds(` → `comp.merge(tp` ordering, so no pinned index moves. All four quoted
  carried-column literals (`"was_home"`, `"kickoff_time"`, `"pen_taker"`, `"setpiece_taker"`)
  and all three `tp[...]` assignment literals stay exactly where they are.
- One further line in `predict_components` changes shape without changing a pinned literal:
  `tp = load_model("team").predict(tg_future)` becomes two lines,
  `team_model = load_model("team")` then `tp = team_model.predict(tg_future)`, so the fitted
  team model is in hand for `attack_multipliers`. No protected test mentions that line.

---

## Facts established by the survey (do not re-derive)

- **The components parquet already exists.** `run_advise:899` calls
  `save_components(components_frame(comp, scoring, cal, players, teams), gw)` and
  `artifacts.components_path(gw)` is already `reports/components_gw{N}.parquet`, with
  `load_components(gw)` beside it. Spec §4's first bullet is therefore **already shipped**:
  U2's per-player breakdown needs an *endpoint*, not a new writer. The only change to the
  file is one new column (Task 2).
- **`pen_taker` / `setpiece_taker` already ride on `comp`** as *features*
  (`features/engineer.add_setpiece`, `_order_score`: order 1 → 1.0, order 2 → 0.5, ≥3 → 0.0,
  absent → NaN) and are already in `COMPONENT_COLS`. They are NaN on every historical row, so
  the attacking model has effectively never learned from them — which is exactly why an
  explicit prediction-time term is worth adding.
- **`ep_breakdown` carries unknown columns through.** `components_frame` builds `out` from
  `ep_breakdown(assemble_ep(comp, scoring), scoring)`, and both start with
  `df = <input>.copy()`. A new column on `comp` therefore reaches `out` untouched, and
  `components_frame`'s final `out[COMPONENT_COLS]` is the only gate on it.
- **`assemble_ep` prices goals as `p_play * e_goals * s("goals_scored")`.** Folding the
  penalty increment into `e_goals` therefore multiplies it by `p_play` and by the position's
  goal points automatically — which is precisely spec §1's formula. Task 2 rescales the goals
  increment so the resulting EP change equals the clamped term exactly.
- **Understat carries no `goals`/`npg` columns.** `data/understat.PLAYER_PARQUET_COLS` is
  `[season, season_idx, understat_id, code, player_name, team, date, minutes, us_shots,
  us_key_passes, us_npxg, us_xgchain, us_xgbuildup]`. Spec §1's `pens_taken ≈ goals − npg`
  is not computable from it. What **is** computable: `models.train.attach_understat` joins
  `us_npxg` (Understat non-penalty xG, penalties explicitly excluded in
  `understat.match_player_rows`) onto FPL rows that already carry `xg` (FPL's
  `expected_goals`, penalties **included**). Task 1 estimates penalties taken as
  `max(0, xg − us_npxg) / 0.79` per player-match — the same subtraction the spec intends, in
  xG space instead of goal space. Because the number is used only as a **ratio** of the
  club's own total, the systematic offset between two xG models largely cancels.
- **The Dixon-Coles model is the shipped team head.** `models/train.TEAM_MODEL ==
  "dixon_coles"`, and `DixonColesModel.fit` sets `self.attack_ = {code: log-attack}` plus
  `fallback_attack_`. `attack_mult(t)` is `exp(attack_[t]) / mean(exp(attack_))`. A
  `TeamModel` (the alternative head) has no `attack_`, so `getattr(model, "attack_", None)`
  is the degradation seam and yields a flat multiplier of 1.0.
- **Asset loading** lives in `src/gaffer/assets/__init__.py` (`files(__package__)`, an
  `_exist()` predicate, a loader returning `None` when absent — `decision_priors` at 39-64
  and `injury_curves` at 67-92 are the precedents). **Asset writing** lives in a calibration
  module with an `ASSET_PATH` constant and a validating `write_*` function
  (`calibrate_decisions.py:39,200-223`), driven by a Typer command (`cli.py:252-268`).
- **`/api/chips/plan` already exists** in `web/routers/meta.py:52`, and `ThisWeek.tsx:25`
  already calls it. The new `GET /api/chips` is a *different* endpoint on a *new* router and
  does not touch it.
- **Error style.** `create_app` maps `GafferError` → 422 app-wide, which is what
  `whatif.py` and `quality.py` lean on. The four new endpoints raise
  `HTTPException(404, detail=...)` for a **missing artifact** specifically, because the
  frontend panels hide on 404 and must not be confused with the 422 "re-run advise" state.
  Structured 422s stay `_fail`-shaped where a constraint is at fault.
- **Frontend build output is gitignored** (`.gitignore`: `src/gaffer/web/static/`), so
  `npm run build` is a verification step, never a staged one.
- **vitest style** is `vi.hoisted` + `vi.mock('../api/client', ...)` with `apiGet`/`apiPost`
  spies — no msw, no fetch-mock. `Quality.test.tsx:6-24` and `WhatIf.test.tsx:9-26` are the
  two templates; components under `frontend/src/components/` use the same `'../api/client'`
  specifier because they sit at the same depth as pages.

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `src/gaffer/set_pieces.py` | `PEN_CONVERSION`, `PEN_XG`, `GOAL_POINTS`, `EP_CLAMP`, `PenPriors`, `share_now`, `pen_estimate`, `pen_priors`, `attack_multipliers`, `pen_table`, `set_piece_ep`, `add_pen_ep`, `pen_notices`. |
| `src/gaffer/calibrate_noise.py` | `ASSET_PATH`, `EP_EDGES`, `XMINS_EDGES`, `bin_index`, `residual_rows`, `fit_sigmas`, `run_calibration`, `write_noise`. |
| `src/gaffer/web/routers/chips.py` | `GET /api/chips` — chip table, wildcard squad diff. |
| `src/gaffer/web/routers/components.py` | `GET /api/components/{gw}` — the per-player EP decomposition. |
| `src/gaffer/web/routers/news.py` | `GET /api/news/{gw}` — what the news layer moved, with per-source evidence. |
| `frontend/src/pages/ChipWorkbench.tsx` | The Chips page: gain-vs-threshold bars, wildcard diff, What-If front door. |
| `frontend/src/pages/ChipWorkbench.test.tsx` | Its vitest suite. |
| `frontend/src/components/WhyPanel.tsx` | Per-player EP breakdown + "since last run" strip. |
| `frontend/src/components/WhyPanel.test.tsx` | Its vitest suite. |
| `frontend/src/components/NewsPanel.tsx` | "News moved N players" with per-source evidence. |
| `frontend/src/components/NewsPanel.test.tsx` | Its vitest suite. |
| `tests/test_set_pieces.py` | Estimator, shares, multipliers, clamp, notices, byte-identical rail. |
| `tests/test_calibrate_noise.py` | Binning, σ fitting, pooling chain, validator. |
| `tests/data/scenario_noise.json` | A small committed fixture asset — never the real one. |
| `tests/test_web_chips.py` | `/api/chips`. |
| `tests/test_web_components.py` | `/api/components/{gw}`. |
| `tests/test_web_news.py` | `/api/news/{gw}`. |
| `tests/test_v6_degradation.py` | The v6 rails. |

**Modified:**

| Path | Change |
| --- | --- |
| `src/gaffer/advise.py` | `predict_components(..., pens=None)` + `add_pen_ep` + `team_model` split; one `pens = pen_priors(hist)` line and two persistence lines in `run_advise` (Tasks 2, 5). |
| `src/gaffer/artifacts.py` | `COMPONENT_COLS` gains `ep_pen_taker` (Task 2); `AVAILABILITY_COLS`, `availability_path`, `save_availability`, `load_availability`, `ADVICE_HISTORY`, `append_advice_history`, `advice_history_files`, `prune_advice_history`, `diff_advice` (Task 5). |
| `src/gaffer/assets/__init__.py` | `SCENARIO_NOISE`, `scenario_noise_exists`, `load_scenario_noise` (Task 3). |
| `src/gaffer/optimize/scenarios.py` | `SIGMA_MAX`, `scenario_noise`, `bin_index`, `sigma_for`, `noise_ep(..., table=None)`, `noised_pool` threading the table (Task 3). |
| `src/gaffer/cli.py` | `calibrate-noise` command (Task 4). |
| `src/gaffer/web/app.py` | Three new routers registered (Tasks 6, 7, 9). |
| `src/gaffer/web/schemas.py` | `ChipWorkbenchRow`, `SquadDiff`, `ChipsWorkbench`, `ComponentRow`, `ComponentsBreakdown`, `AdviceDiff`, `NewsSource`, `NewsRow`, `NewsPanelData`, `NewsShadowGw`, `NewsShadowSummary`, `NewsShadow`, `Quality.news_shadow` (Tasks 6-9, 13). |
| `src/gaffer/web/routers/advice.py` | `GET /api/advice/diff` (Task 8). |
| `frontend/src/App.tsx` | `/chips` route (Task 10). |
| `frontend/src/components/Sidebar.tsx` | "Chips" nav entry (Task 10). |
| `frontend/src/types.ts` | The new response types (Tasks 10-13). |
| `frontend/src/pages/ThisWeek.tsx` | Mounts `WhyPanel` and `NewsPanel` (Tasks 11, 12). |
| `frontend/src/pages/ThisWeek.test.tsx` | Its `apiGet` mock learns the new paths (Tasks 11, 12). |
| `frontend/src/pages/Quality.tsx` | "News layer" section (Task 13). |

---

## Task 1 — `set_pieces.py`: the penalty term, as a pure module

**Files:** `src/gaffer/set_pieces.py` (new), `tests/test_set_pieces.py` (new).

Nothing in this task touches `advise.py`. The module is pure: no I/O, no model loading, no network.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_set_pieces.py`:

```python
"""The v6 penalty-taker term (spec §1).

Pure arithmetic over three inputs — the bootstrap taker order, the player's
trailing share of his club's penalties, and the club's attack strength — with
a hard clamp round the outside because no backtest can validate it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.set_pieces import (ATTACK_MULT_CLAMP, EP_CLAMP, GOAL_POINTS,
                               LEAGUE_PENS_PG_FALLBACK, PEN_CONVERSION,
                               PEN_XG, PenPriors, add_pen_ep,
                               attack_multipliers, pen_estimate, pen_notices,
                               pen_priors, pen_table, set_piece_ep, share_now)


def _players(order_1=1, order_2=2) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "name": "First Choice", "position": "MID",
         "team_code": 3, "penalties_order": order_1},
        {"code": 2, "name": "Backup", "position": "FWD",
         "team_code": 3, "penalties_order": order_2},
        {"code": 3, "name": "Nobody", "position": "DEF",
         "team_code": 8, "penalties_order": None},
    ])


def _comp() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "position": "MID", "team_code": 3,
         "p_play": 1.0, "e_goals": 0.5},
        {"code": 2, "gw": 5, "position": "FWD", "team_code": 3,
         "p_play": 0.8, "e_goals": 0.3},
        {"code": 3, "gw": 5, "position": "DEF", "team_code": 8,
         "p_play": 1.0, "e_goals": 0.1},
    ])


def _priors(**shares) -> PenPriors:
    return PenPriors(share_hist={int(k): float(v) for k, v in shares.items()},
                     league_pens_pg=0.13, team_games=760)


# --- share_now --------------------------------------------------------------

def test_share_now_reads_the_bootstrap_queue_position():
    """Order 1 takes them all; order 2 is a hedge against rotation and
    absence, not a claim that he takes 15% of them; below that, nothing."""
    out = share_now(pd.Series([1, 2, 3, None, 0]))
    assert out.tolist() == [1.0, 0.15, 0.0, 0.0, 0.0]


# --- the historical share ---------------------------------------------------

def test_pen_estimate_reads_the_gap_between_fpl_xg_and_understat_npxg():
    """FPL's expected_goals includes penalties; Understat's npxG excludes
    them. The gap is a penalty, priced at PEN_XG."""
    frame = pd.DataFrame({"xg": [1.0, 0.4, 0.2],
                          "us_npxg": [0.21, 0.4, 0.5]})
    out = pen_estimate(frame)
    assert out.iloc[0] == pytest.approx(0.79 / PEN_XG)
    assert out.iloc[1] == 0.0
    # A negative gap is two xG models disagreeing, not a negative penalty.
    assert out.iloc[2] == 0.0


def test_pen_estimate_is_none_without_both_columns():
    assert pen_estimate(pd.DataFrame({"xg": [1.0]})) is None
    assert pen_estimate(pd.DataFrame({"us_npxg": [1.0]})) is None


def _hist() -> pd.DataFrame:
    """Two clubs, three seasons. Player 1 took every one of club 3's
    penalties; player 2 took none; club 8 had one, from player 3."""
    rows = []
    for season in (0, 1, 2):
        for gw in range(1, 11):
            rows += [
                {"season_idx": season, "gw": gw, "code": 1, "team_code": 3,
                 "opp_code": 8, "xg": 0.5 + (PEN_XG if gw == 1 else 0.0),
                 "us_npxg": 0.5},
                {"season_idx": season, "gw": gw, "code": 2, "team_code": 3,
                 "opp_code": 8, "xg": 0.3, "us_npxg": 0.3},
                {"season_idx": season, "gw": gw, "code": 3, "team_code": 8,
                 "opp_code": 3, "xg": 0.2 + (PEN_XG if gw == 2 else 0.0),
                 "us_npxg": 0.2},
            ]
    return pd.DataFrame(rows)


def test_pen_priors_gives_the_sole_taker_the_whole_share():
    priors = pen_priors(_hist())
    assert priors is not None
    assert priors.share_hist[1] == pytest.approx(1.0)
    assert priors.share_hist.get(2, 0.0) == pytest.approx(0.0)
    assert priors.share_hist[3] == pytest.approx(1.0)


def test_pen_priors_falls_back_when_the_league_rate_is_implausible():
    """Three penalties per team-game is a broken estimator, not a wild
    season. The rate is bounded, and the shares are still usable."""
    hist = _hist()
    hist["xg"] = hist["xg"] + 3.0 * PEN_XG
    priors = pen_priors(hist)
    assert priors.league_pens_pg == LEAGUE_PENS_PG_FALLBACK


def test_pen_priors_returns_none_without_the_xg_columns():
    """The rail spec §1 names: no Understat frame -> share_hist = 0 for
    everybody, expressed as no priors at all."""
    hist = _hist().drop(columns=["us_npxg"])
    assert pen_priors(hist) is None
    assert pen_priors(pd.DataFrame()) is None
    assert pen_priors(None) is None


# --- attack multipliers -----------------------------------------------------

class _DC:
    def __init__(self, attack):
        self.attack_ = attack


def test_attack_multipliers_are_a_ratio_to_the_league_mean():
    mult = attack_multipliers(_DC({3: 0.2, 8: 0.0, 14: -0.2}))
    assert mult[3] > 1.0 > mult[14]
    assert mult[8] == pytest.approx(1.0, abs=0.02)


def test_attack_multipliers_are_clamped_both_ways():
    mult = attack_multipliers(_DC({3: 5.0, 8: -5.0}))
    assert mult[3] == ATTACK_MULT_CLAMP[1]
    assert mult[8] == ATTACK_MULT_CLAMP[0]


def test_a_team_model_without_attack_strengths_is_a_flat_multiplier():
    assert attack_multipliers(object()) == {}
    assert attack_multipliers(None) == {}


# --- the term itself --------------------------------------------------------

def test_the_term_prices_the_increment_over_history_not_the_penalty():
    """A first-choice taker whose history already says he takes them all is
    worth nothing extra — that is the whole double-count argument."""
    term = set_piece_ep(_comp(), _players(), _priors(**{"1": 1.0}), {})
    assert term.iloc[0] == pytest.approx(0.0)


def test_a_brand_new_taker_is_where_the_term_is_biggest():
    """Zero history, order 1: the model is blind exactly here."""
    term = set_piece_ep(_comp(), _players(), _priors(), {})
    expected = 1.0 * 0.13 * 1.0 * PEN_CONVERSION * GOAL_POINTS["MID"] * 1.0
    assert term.iloc[0] == pytest.approx(expected)


def test_a_demoted_taker_gets_a_negative_term():
    """History says he took them; the bootstrap says he no longer does."""
    players = _players(order_1=None)
    term = set_piece_ep(_comp(), players, _priors(**{"1": 1.0}), {})
    assert term.iloc[0] < 0.0


def test_the_term_scales_with_p_play_and_the_attack_multiplier():
    term = set_piece_ep(_comp(), _players(), _priors(), {3: 1.5})
    expected = (0.15 * 0.13 * 1.5 * PEN_CONVERSION
                * GOAL_POINTS["FWD"] * 0.8)
    assert term.iloc[1] == pytest.approx(expected)


def test_the_term_is_clamped_both_ways():
    """No backtest can validate this term, so the clamp is the safety."""
    priors = PenPriors(share_hist={}, league_pens_pg=0.35, team_games=760)
    comp = _comp()
    comp.loc[0, "position"] = "GKP"          # 10 points a goal
    term = set_piece_ep(comp, _players(), priors, {3: ATTACK_MULT_CLAMP[1]})
    assert term.iloc[0] == EP_CLAMP[1]
    demoted = set_piece_ep(comp, _players(order_1=None),
                           PenPriors(share_hist={1: 1.0},
                                     league_pens_pg=0.35, team_games=760),
                           {3: ATTACK_MULT_CLAMP[1]})
    assert demoted.iloc[0] == EP_CLAMP[0]


def test_players_with_no_order_at_all_get_exactly_zero():
    term = set_piece_ep(_comp(), _players(), _priors(), {})
    assert term.iloc[2] == 0.0


# --- folding into the components frame --------------------------------------

def test_add_pen_ep_moves_e_goals_by_exactly_the_clamped_points():
    """assemble_ep prices goals as p_play * e_goals * goal_points, so the
    goals increment has to be the clamped EP divided back through both."""
    out = add_pen_ep(_comp(), _players(), _priors(), {})
    row = out.iloc[0]
    delta_goals = row["e_goals"] - _comp().iloc[0]["e_goals"]
    assert (delta_goals * GOAL_POINTS["MID"] * row["p_play"]
            == pytest.approx(row["ep_pen_taker"]))


def test_no_priors_leaves_the_frame_untouched_column_for_column():
    """The rail: no penalty history -> the components are what they were."""
    comp = _comp()
    out = add_pen_ep(comp, _players(), None, {})
    assert (out["ep_pen_taker"] == 0.0).all()
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)


def test_all_none_taker_orders_leave_the_frame_untouched_column_for_column():
    """The other half of the same rail: the bootstrap stopped publishing
    orders, or every value is null."""
    comp = _comp()
    players = _players(order_1=None, order_2=None)
    out = add_pen_ep(comp, players, _priors(), {})
    assert (out["ep_pen_taker"] == 0.0).all()
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)


def test_a_players_frame_without_the_order_column_is_the_same_rail():
    comp = _comp()
    players = _players().drop(columns=["penalties_order"])
    out = add_pen_ep(comp, players, _priors(), {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)


# --- the audit log (gate P1) ------------------------------------------------

def test_pen_notices_name_every_term_worth_reading():
    notices = pen_notices(_comp(), _players(), _priors(), {})
    assert any("First Choice" in line for line in notices)
    assert all("Nobody" not in line for line in notices)
    joined = "\n".join(notices)
    assert "share now" in joined and "history" in joined


def test_pen_notices_are_silent_when_nothing_moved():
    assert pen_notices(_comp(), _players(), None, {}) == []


def test_the_goal_points_table_matches_the_shipped_scoring_table():
    """GOAL_POINTS is a module constant so predict_components does not have
    to thread the scoring table down. It has to agree with the real one."""
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table

    real = scoring_table(load_bootstrap_sample())["goals_scored"]
    assert {k: float(v) for k, v in real.items()} == GOAL_POINTS
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_set_pieces.py -x -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'gaffer.set_pieces'`.

- [ ] **Step 3: Write the module**

Create `src/gaffer/set_pieces.py`:

```python
"""Penalty-taker expected points, priced at prediction time (spec §1).

FPL's bootstrap publishes ``penalties_order`` per element, and the number is
serve-time-only: there is no archive of who was on penalties in October 2023,
so this term can never be backtested. That shapes everything here. The term is
small, bounded by a hard clamp, and instrumented — :func:`pen_notices` prints
every nonzero term worth reading so gate P1 can audit the live distribution
instead of replaying one.

**Scope: penalties only.** Direct free kicks and corners are surfaced in the
UI as context and get no EP term: the xA features already price established
takers, and a corner-taker delta is too small to validate.

**The double-count problem.** A player's xG features already contain the
penalties he historically took, so a naive additive term overpays the Salahs.
What is added is only the *increment* over what history priced in::

    ep_pen(p) = (share_now(p) - share_hist(p)) * team_pens_pg(t)
                * PEN_CONVERSION * goal_points(position) * p_play(p)

**How ``share_hist`` is measured, and why it is not what the spec says.** The
spec asks for ``pens_taken ~= goals - npg`` from Understat. Understat's
player-match parquet carries no goals and no npg — only ``us_npxg``, from
which :func:`gaffer.data.understat.match_player_rows` explicitly excludes
penalty shots. But ``models.train.attach_understat`` joins that column onto
FPL rows that *do* carry ``xg``, and FPL's ``expected_goals`` includes
penalties. The gap between them is a penalty, priced at :data:`PEN_XG`. Two
different xG models disagree by a few hundredths on open play, so the raw gap
is noisy — which is why it is only ever used as a **ratio** of the club's own
total, where a systematic offset largely cancels, and why a negative gap is
floored at zero rather than being read as a negative penalty.

Nothing here does I/O, loads a model or touches the network. Everything is
handed in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PEN_CONVERSION = 0.78
"""Share of penalties that are scored. A constant, not a fitted number."""

PEN_XG = 0.79
"""xG a penalty is worth in both public models, near enough.

Used only as the divisor turning an xG gap back into a count of penalties, so
a few percent of error here is a few percent of error on a ratio's numerator
and denominator alike.
"""

SHARE_ORDER_2 = 0.15
"""What the second name on the list is worth.

Not a claim that he takes 15% of his club's penalties. It is a hedge against
the first taker being rotated, subbed or injured, which is the only way the
second name ever steps up.
"""

EP_CLAMP = (-0.3, 0.8)
"""Hard bound on the term, in expected points.

A safety bound rather than a modelling choice: taker orders are serve-time
data of the same class as news, no historical backtest can validate the term,
and an unbounded term multiplied by a 10-point keeper goal would be the one
place this could do real damage.
"""

ATTACK_MULT_CLAMP = (0.6, 1.6)
"""Bound on a club's attack strength relative to the league mean."""

LEAGUE_PENS_PG_BOUNDS = (0.05, 0.35)
"""Plausible range for league penalties per team-game.

The real number is around 0.13 (roughly 100 penalties across 760 team-games).
An estimate outside this range means the xG-gap estimator has gone wrong —
a season with no Understat coverage, say — and the fallback is used instead.
"""

LEAGUE_PENS_PG_FALLBACK = 0.13

MAX_PENS_PER_MATCH = 2.0
"""Per-match cap on the estimator. Three penalties in a match happens about
once a decade; an estimate above two is model disagreement, not a hat-trick
of spot kicks."""

PEN_SEASONS = 3
"""Seasons of history the share is measured over: the last two plus the
current one, as spec §1 asks."""

GOAL_POINTS = {"GKP": 10.0, "DEF": 6.0, "MID": 5.0, "FWD": 4.0}
"""Points per goal by position.

A module constant rather than a threaded-through scoring table, because
``predict_components`` does not have the scoring table in hand and giving it
one would mean moving a line in ``run_advise`` for no gain. A test pins it
against ``scoring_table(load_bootstrap_sample())["goals_scored"]``, so a rule
change breaks the suite rather than drifting silently.
"""

NOTICE_MIN_EP = 0.05
"""Terms below this are not worth a line in the log (gate P1)."""

ZERO_COLS = ("share_now", "share_hist", "goals", "ep")


@dataclass
class PenPriors:
    """A season-scale reading of who takes his club's penalties.

    ``share_hist`` is ``{code: share in [0, 1]}`` and is deliberately *sparse*
    — a player with no history is absent, which reads as zero, which is where
    the term is maximal. That is the intent: the model is blindest about a
    taker it has never seen take one.
    """

    share_hist: dict[int, float] = field(default_factory=dict)
    league_pens_pg: float = LEAGUE_PENS_PG_FALLBACK
    team_games: int = 0


def share_now(order) -> pd.Series:
    """Bootstrap queue position -> share of his club's penalties, today."""
    v = pd.to_numeric(pd.Series(order), errors="coerce")
    out = pd.Series(0.0, index=v.index, dtype="float64")
    out[v == 1] = 1.0
    out[v == 2] = SHARE_ORDER_2
    return out


def pen_estimate(frame: pd.DataFrame) -> pd.Series | None:
    """Per player-match estimate of penalties taken, or ``None``.

    ``None`` — not an all-zero series — when either column is absent, so the
    caller can tell "no data" from "no penalties" and decline to build priors
    at all.
    """
    if frame is None or not {"xg", "us_npxg"}.issubset(frame.columns):
        return None
    total = pd.to_numeric(frame["xg"], errors="coerce")
    open_play = pd.to_numeric(frame["us_npxg"], errors="coerce")
    gap = (total - open_play).where(total.notna() & open_play.notna())
    return (gap / PEN_XG).clip(lower=0.0,
                               upper=MAX_PENS_PER_MATCH).fillna(0.0)


def pen_priors(hist: pd.DataFrame | None) -> PenPriors | None:
    """Trailing penalty shares and the league rate, from the training frame.

    ``hist`` is ``load_training_frame()``'s player frame — the one that has
    already been through ``attach_understat``, so it carries ``us_npxg``
    beside FPL's ``xg``.

    ``None`` on anything that would make the answer a fiction: no frame, no
    columns, no estimated penalties at all. Never raises: this feeds a
    prediction-time term and an advice run must not die of it.
    """
    try:
        if hist is None or len(hist) == 0:
            return None
        need = {"code", "team_code", "season_idx", "gw", "opp_code"}
        if not need.issubset(hist.columns):
            return None
        seasons = sorted(pd.to_numeric(hist["season_idx"], errors="coerce")
                         .dropna().unique())[-PEN_SEASONS:]
        window = hist[hist["season_idx"].isin(seasons)]
        pens = pen_estimate(window)
        if pens is None or float(pens.sum()) <= 0.0:
            return None
        frame = pd.DataFrame({
            "code": pd.to_numeric(window["code"], errors="coerce"),
            "team_code": pd.to_numeric(window["team_code"], errors="coerce"),
            "pens": pens.to_numpy()}).dropna(subset=["code", "team_code"])
        by_player = frame.groupby(["code", "team_code"],
                                  as_index=False)["pens"].sum()
        by_team = (frame.groupby("team_code", as_index=False)["pens"].sum()
                   .rename(columns={"pens": "team_pens"}))
        joined = by_player.merge(by_team, on="team_code", how="left")
        joined["share"] = np.where(joined["team_pens"] > 0.0,
                                   joined["pens"] / joined["team_pens"], 0.0)
        # A player who changed clubs mid-window keeps his best club's share
        # rather than an average diluted by a club he no longer plays for.
        share = joined.groupby("code")["share"].max().clip(0.0, 1.0)
        games = window[["season_idx", "gw", "team_code",
                        "opp_code"]].drop_duplicates()
        per_game = float(pens.sum()) / max(1, len(games))
        if not (LEAGUE_PENS_PG_BOUNDS[0] <= per_game
                <= LEAGUE_PENS_PG_BOUNDS[1]):
            print(f"set pieces: league penalty rate {per_game:.3f}/game is "
                  f"outside {LEAGUE_PENS_PG_BOUNDS} — using "
                  f"{LEAGUE_PENS_PG_FALLBACK}")
            per_game = LEAGUE_PENS_PG_FALLBACK
        return PenPriors(
            share_hist={int(k): float(v) for k, v in share.items()},
            league_pens_pg=float(per_game), team_games=int(len(games)))
    except Exception as exc:  # noqa: BLE001 — never blocks a prediction
        print(f"set pieces: no penalty history ({exc})")
        return None


def attack_multipliers(team_model) -> dict[int, float]:
    """``{team_code: attack strength / league mean}``, clamped.

    Reads ``DixonColesModel.attack_`` (log attack strengths from the fitted
    scoreline model). A ``TeamModel`` has no such attribute and yields ``{}``,
    which every caller reads as a flat multiplier of 1.0 — the degradation
    seam, and the reason this is a ``getattr`` rather than an isinstance.
    """
    attack = getattr(team_model, "attack_", None)
    if not attack:
        return {}
    strengths = {int(c): math.exp(float(a)) for c, a in attack.items()}
    mean = sum(strengths.values()) / len(strengths)
    if not mean > 0.0:
        return {}
    lo, hi = ATTACK_MULT_CLAMP
    return {c: min(max(s / mean, lo), hi) for c, s in strengths.items()}


def pen_table(comp: pd.DataFrame, players: pd.DataFrame,
              priors: PenPriors | None = None,
              attack_mult: dict[int, float] | None = None) -> pd.DataFrame:
    """``[share_now, share_hist, goals, ep]``, aligned to ``comp``'s index.

    ``goals`` is the increment to add to ``e_goals``; it is already rescaled
    so that ``p_play * goals * goal_points`` equals the **clamped** ``ep``
    exactly, which is what makes the clamp mean what it says once
    ``assemble_ep`` has multiplied everything back out.

    Every path that cannot produce a real number produces an all-zero table
    rather than a partial one: no priors, no order column, an order column
    that is entirely null. That is the byte-identical rail.
    """
    zeros = pd.DataFrame({c: pd.Series(0.0, index=comp.index,
                                       dtype="float64") for c in ZERO_COLS})
    if priors is None or len(comp) == 0:
        return zeros
    if players is None or "penalties_order" not in players.columns:
        return zeros
    order_of = dict(zip(players["code"],
                        pd.to_numeric(players["penalties_order"],
                                      errors="coerce")))
    now = share_now(comp["code"].map(order_of))
    now.index = comp.index
    if float(now.abs().sum()) == 0.0:
        return zeros
    hist = (comp["code"].map(priors.share_hist)
            .astype("float64").fillna(0.0))
    lo, hi = ATTACK_MULT_CLAMP
    mult = (comp["team_code"].map(attack_mult or {})
            .astype("float64").fillna(1.0).clip(lo, hi))
    p_play = pd.to_numeric(comp["p_play"], errors="coerce").fillna(0.0)
    goal_pts = comp["position"].map(GOAL_POINTS).astype("float64").fillna(0.0)
    goals = ((now - hist) * priors.league_pens_pg * mult * PEN_CONVERSION)
    raw = goals * goal_pts * p_play
    ep = raw.clip(EP_CLAMP[0], EP_CLAMP[1])
    raw_v = raw.to_numpy(dtype="float64")
    scale = np.where(raw_v != 0.0, ep.to_numpy(dtype="float64")
                     / np.where(raw_v != 0.0, raw_v, 1.0), 0.0)
    return pd.DataFrame({"share_now": now, "share_hist": hist,
                         "goals": goals * scale, "ep": ep})


def set_piece_ep(comp: pd.DataFrame, players: pd.DataFrame,
                 priors: PenPriors | None = None,
                 attack_mult: dict[int, float] | None = None) -> pd.Series:
    """The clamped expected-points term, one value per component row."""
    return pen_table(comp, players, priors, attack_mult)["ep"]


def add_pen_ep(comp: pd.DataFrame, players: pd.DataFrame,
               priors: PenPriors | None = None,
               attack_mult: dict[int, float] | None = None) -> pd.DataFrame:
    """``comp`` with ``ep_pen_taker`` recorded and ``e_goals`` moved.

    The increment lands on ``e_goals`` rather than on ``ep`` directly because
    ``assemble_ep`` is the only place expected points are ever assembled, and
    a second addition site would be a second thing to keep in step with the
    scoring table, the calibration and ``ep_breakdown``.

    When the term is identically zero, ``e_goals`` is not touched at all —
    ``x + 0.0`` is bit-identical for a float, but not for every dtype pandas
    might be holding, and the rail is stated as *column for column*.
    """
    out = comp.copy()
    table = pen_table(out, players, priors, attack_mult)
    out["ep_pen_taker"] = table["ep"].to_numpy(dtype="float64")
    moved = table["goals"].to_numpy(dtype="float64")
    if "e_goals" in out.columns and bool((moved != 0.0).any()):
        out["e_goals"] = (out["e_goals"].to_numpy(dtype="float64") + moved)
    return out


def pen_notices(comp: pd.DataFrame, players: pd.DataFrame,
                priors: PenPriors | None = None,
                attack_mult: dict[int, float] | None = None,
                min_ep: float = NOTICE_MIN_EP) -> list[str]:
    """One line per term worth reading — gate P1's whole instrument.

    Deduplicated by player: a double gameweek prices the term twice, but the
    audit is about *who* the term moved and by how much, and two identical
    lines say nothing the first one did not.
    """
    table = pen_table(comp, players, priors, attack_mult)
    if float(table["ep"].abs().sum()) == 0.0:
        return []
    name_of = dict(zip(players["code"], players["name"])) \
        if "name" in players.columns else {}
    frame = pd.DataFrame({"code": comp["code"].to_numpy(),
                          "ep": table["ep"].to_numpy(),
                          "share_now": table["share_now"].to_numpy(),
                          "share_hist": table["share_hist"].to_numpy()})
    frame = frame[frame["ep"].abs() >= float(min_ep)]
    frame = (frame.reindex(frame["ep"].abs().sort_values(ascending=False)
                           .index).drop_duplicates(subset=["code"]))
    return [f"set pieces: {name_of.get(int(r.code), int(r.code))} "
            f"{r.ep:+.2f} xPts (share now {r.share_now:.2f}, "
            f"history {r.share_hist:.2f})" for r in frame.itertuples()]
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_set_pieces.py -q
```

Expected: all pass (21 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/set_pieces.py tests/test_set_pieces.py
git commit -m "feat: penalty-taker EP term as a pure module" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 2 — wire the penalty term into `predict_components`

**Files:** `src/gaffer/advise.py` (imports at `:29-76`; `predict_components` signature at `:369-371`, team block at `:412`, return at `:434`; `run_advise` at `:559-560`), `src/gaffer/artifacts.py` (`COMPONENT_COLS` at `:34-43`), `tests/test_advise.py` (append), `tests/test_v6_degradation.py` (new).

**Protected-test constraints for this task, restated:**

- `run_advise` gains **one** line, `pens = pen_priors(hist)`, immediately above
  `avail = news_availability(cfg, players, teams, events, gw)`. It does not contain the
  substring `pool_ep`, and it sits far above `ep_gw1 =`.
- `comp = predict_components(pred_frame, tg_future, players, avail)` becomes
  `comp = predict_components(pred_frame, tg_future, players, avail, pens)`. **The literal
  `comp = predict_components(` must survive**; the call never becomes a tuple unpack.
- Inside `predict_components`, the new statement goes **after**
  `comp["e_gc"] = comp["e_gc"].fillna(DEFAULT_E_GC)` and immediately before `return comp`, so
  `src.index("blend_team_odds(") < src.index("comp.merge(tp")` is untouched and all four
  quoted carried-column literals stay where they are.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_advise.py`:

```python
# --- v6 set pieces ----------------------------------------------------------


def test_predict_components_prices_penalties_after_the_availability_passes():
    """Source-level seam: the term multiplies by p_play, so it has to land
    after the news pass has had its say about whether he plays at all — and
    after the protected team-odds merge, so no pinned index moves."""
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    avail = src.index("mp = apply_availability(mp, avail")
    merge = src.index("comp.merge(tp")
    pen = src.index("add_pen_ep(")
    assert avail < merge < pen
    assert src.index("blend_team_odds(") < merge
    assert "pens" in inspect.signature(predict_components).parameters


def test_run_advise_builds_the_penalty_priors_before_predicting():
    """One line, above the news line, and nowhere near the pool."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    priors = src.index("pens = pen_priors(hist)")
    avail = src.index("avail = news_availability(")
    comp = src.index("comp = predict_components(")
    assert priors < avail < comp
    assert "predict_components(pred_frame, tg_future, players, avail, pens)" \
        in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]


def test_the_components_file_records_the_penalty_term():
    from gaffer.artifacts import COMPONENT_COLS

    assert "ep_pen_taker" in COMPONENT_COLS
```

Create `tests/test_v6_degradation.py`:

```python
"""The v6 degradation rails.

Three things are pinned here; Task 3 adds the noise rail and Task 14 restates
the lot:

1. No penalty history, or no taker orders, leaves the component frame exactly
   as it was — column for column, not merely in the numbers EP happens to
   read.
2. The penalty term never escapes its clamp, whatever the inputs.
3. The protected source-text orderings in ``run_advise`` and
   ``predict_components`` still hold after everything v6 inserted.

If a later task legitimately changes one of these, that task's gate says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pandas as pd

from gaffer.set_pieces import (EP_CLAMP, PenPriors, add_pen_ep,
                               attack_multipliers)


def _comp() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "position": "MID", "team_code": 3,
         "p_play": 0.95, "p60": 0.9, "e_goals": 0.42, "e_assists": 0.3},
        {"code": 2, "gw": 5, "position": "GKP", "team_code": 8,
         "p_play": 1.0, "p60": 1.0, "e_goals": 0.01, "e_assists": 0.01},
    ])


def _players(order=None) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "name": "A", "position": "MID", "team_code": 3,
         "penalties_order": order},
        {"code": 2, "name": "B", "position": "GKP", "team_code": 8,
         "penalties_order": None},
    ])


# --- rail 1: no taker data == today's components ---------------------------

def test_no_priors_is_byte_identical_components():
    comp = _comp()
    out = add_pen_ep(comp, _players(order=1), None, {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)
    assert (out["ep_pen_taker"] == 0.0).all()


def test_no_taker_orders_is_byte_identical_components():
    comp = _comp()
    priors = PenPriors(share_hist={1: 0.0}, league_pens_pg=0.13,
                       team_games=760)
    out = add_pen_ep(comp, _players(order=None), priors, {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)
    assert (out["ep_pen_taker"] == 0.0).all()


def test_a_team_model_with_no_attack_strengths_still_prices_the_term():
    """The multiplier degrades to flat, not to zero: a missing Dixon-Coles
    fit is no reason to unlearn who takes the penalties."""
    priors = PenPriors(share_hist={}, league_pens_pg=0.13, team_games=760)
    out = add_pen_ep(_comp(), _players(order=1), priors,
                     attack_multipliers(object()))
    assert out["ep_pen_taker"].iloc[0] > 0.0


# --- rail 2: the clamp holds ------------------------------------------------

def test_the_clamp_holds_against_absurd_inputs():
    priors = PenPriors(share_hist={1: 0.0}, league_pens_pg=99.0,
                       team_games=1)
    out = add_pen_ep(_comp(), _players(order=1), priors, {3: 99.0})
    assert out["ep_pen_taker"].max() <= EP_CLAMP[1]
    assert out["ep_pen_taker"].min() >= EP_CLAMP[0]


# --- rail 3: the protected orderings, restated -----------------------------

def test_run_advise_still_orders_every_protected_seam():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < tilt < pool
    assert src.index("compute_strategy(") < pool
    assert "build_pool(players, pool_ep," in src

    comp = src.index("comp = predict_components(")
    blend = src.index("blend_attacking_odds(")
    assemble = src.index("ep_matrix(apply_calibration(assemble_ep(")
    assert comp < blend < assemble
    assert "except Exception" in src[blend - 600:blend + 600]

    assert 'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]

    assert src.index("avail = news_availability(") < comp
    assert comp < src.index("write_shadow(comp, gw)") < blend
    assert src.index("pens = pen_priors(hist)") < comp


def test_predict_components_still_blends_before_merging_onto_players():
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.index("blend_team_odds(") < src.index("comp.merge(tp")
    assert 'tp["p_cs_model"] = tp["p_cs"].values' in src
    assert 'tp["e_gc_model"] = tp["e_gc"].values' in src
    assert "odds_blend_weight()" in src
    for col in ["was_home", "kickoff_time", "pen_taker", "setpiece_taker"]:
        assert f'"{col}"' in src
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_v6_degradation.py tests/test_advise.py -x -q
```

Expected: `ValueError: substring not found` on `add_pen_ep(` / `pens = pen_priors(hist)`, and
`assert "ep_pen_taker" in COMPONENT_COLS` failing.

- [ ] **Step 3: Record the new column**

In `src/gaffer/artifacts.py`, change the `COMPONENT_COLS` entry ending
`"ep_uncalibrated", "cal_delta", "ep",` so the list reads:

```python
COMPONENT_COLS = [
    "code", "element", "name", "position", "team_code", "team_name",
    "gw", "opp_code", "opp_name", "was_home", "kickoff_time",
    "p_play", "p60", "e_goals", "e_assists", "p_defcon", "e_saves",
    "e_bonus", "e_cards", "p_cs", "e_gc", "p_cs_model", "e_gc_model",
    "odds_e_goals_against", "odds_weight", "pen_taker", "setpiece_taker",
    "ep_minutes", "ep_goals", "ep_assists", "ep_cs", "ep_gc", "ep_saves",
    "ep_defcon", "ep_bonus", "ep_cards", "ep_pensave",
    # v6: the penalty-taker increment, already folded into ep_goals above.
    # Recorded separately because "why is he suddenly worth 0.4 more?" has no
    # other answer once the term is inside e_goals — and because gate P1's
    # audit reads it back off the file.
    "ep_pen_taker",
    "ep_uncalibrated", "cal_delta", "ep",
]
```

- [ ] **Step 4: Import and thread the term**

In `src/gaffer/advise.py`, add to the import block (alphabetically, after the
`from gaffer.prices import price_alerts` line):

```python
from gaffer.set_pieces import add_pen_ep, attack_multipliers, pen_notices, \
    pen_priors
```

Change `predict_components`'s signature and docstring tail:

```python
def predict_components(pred_frame: pd.DataFrame, tg_future: pd.DataFrame,
                       players: pd.DataFrame,
                       avail: pd.DataFrame | None = None,
                       pens=None) -> pd.DataFrame:
    """Every component prediction on one row per player-fixture.

    Assembled positionally (see the module docstring): each ``predict``
    returns one row per input row in input order, so ``.values`` lines up
    exactly while a merge on ``(code, season_idx, gw)`` would fan a double
    gameweek out.

    ``pens`` is the :class:`~gaffer.set_pieces.PenPriors` bundle, or ``None``
    for the pre-v6 behaviour: without it the penalty term is identically zero
    and this function returns exactly the frame it always did, plus a zero
    column.
    """
```

Split the team-model load so the fitted model survives (replace the single
`tp = load_model("team").predict(tg_future)` line):

```python
    # The fitted model itself, not only its predictions: the penalty term
    # reads Dixon-Coles' attack strengths off it at the bottom of this
    # function, and loading it twice would be two deserialisations of the
    # same file.
    team_model = load_model("team")
    tp = team_model.predict(tg_future)
```

Replace the function's last three lines (`comp["p_cs"] = ...` through
`return comp`) with:

```python
    comp["p_cs"] = comp["p_cs"].fillna(DEFAULT_P_CS)
    comp["e_gc"] = comp["e_gc"].fillna(DEFAULT_E_GC)
    # Set pieces last, and deliberately so. The term multiplies by p_play, so
    # it has to see the availability passes above; it reads the club's attack
    # strength, so it has to see the team model; and it folds into e_goals
    # rather than into ep, so it has to land before assemble_ep ever runs.
    # With no priors it is identically zero and this is a no-op.
    for line in pen_notices(comp, players, pens,
                            attack_multipliers(team_model)):
        print(line)
    return add_pen_ep(comp, players, pens, attack_multipliers(team_model))
```

- [ ] **Step 5: The one line in `run_advise`**

In `src/gaffer/advise.py`, immediately **above** the existing
`avail = news_availability(cfg, players, teams, events, gw)` line, insert:

```python
    pens = pen_priors(hist)
```

and change the line below it from
`comp = predict_components(pred_frame, tg_future, players, avail)` to:

```python
    comp = predict_components(pred_frame, tg_future, players, avail, pens)
```

- [ ] **Step 6: Run, expect pass**

```bash
uv run pytest tests/test_v6_degradation.py tests/test_set_pieces.py \
  tests/test_advise.py tests/test_odds.py tests/test_artifacts.py \
  tests/test_assemble.py tests/test_v5_degradation.py -q
```

Expected: all pass. `tests/test_odds.py` is in the list specifically to prove the
`src[blend - 600:blend + 600]` window still contains the player-props `except Exception`
block after the insertion.

- [ ] **Step 7: Whole suite**

```bash
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/gaffer/advise.py src/gaffer/artifacts.py \
  tests/test_advise.py tests/test_v6_degradation.py
git commit -m "feat: price the penalty-taker increment at prediction time" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 3 — calibrated scenario noise: the serving half

**Files:** `src/gaffer/assets/__init__.py` (append after `load_injury_curves`, `:92`), `src/gaffer/optimize/scenarios.py` (`noise_ep` at `:81-109`, `noised_pool` at `:112-131`), `tests/test_scenarios.py` (append), `tests/test_v6_degradation.py` (append).

The asset itself does not exist yet and this task must not invent one. Everything here is written against a table handed in as an argument, plus a loader that returns `None` today and will return the real table once the orchestrator runs Task 4's CLI.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scenarios.py`:

```python
# --- v6 calibrated noise ----------------------------------------------------

def _sigma_table() -> dict:
    """Five EP bins x five xMins bins, only some cells populated — which is
    the realistic shape: nobody has 100 observations of a 6+ xPts player who
    was expected to play 20 minutes."""
    return {
        "version": 1,
        "ep_edges": [0.0, 2.0, 3.0, 4.0, 6.0],
        "xmins_edges": [0.0, 30.0, 60.0, 80.0, 90.1],
        "sigma": {"0_0": 0.90, "0_3": 1.40, "4_3": 5.00},
        "obs": {"0_0": 4000, "0_3": 9000, "4_3": 300},
        "ep_marginal": {"0": 1.10, "2": 2.60, "4": 4.80},
        "global": 2.00,
    }


def test_bin_index_places_a_value_in_its_half_open_bin():
    from gaffer.optimize.scenarios import bin_index

    edges = [0.0, 2.0, 3.0, 4.0, 6.0]
    assert bin_index(0.0, edges) == 0
    assert bin_index(1.99, edges) == 0
    assert bin_index(2.0, edges) == 1
    assert bin_index(5.9, edges) == 3
    assert bin_index(9.0, edges) == 4
    # Below the first edge is still the first bin: an EP cannot be negative,
    # and a stray -0.0 must not index off the front of the table.
    assert bin_index(-1.0, edges) == 0


def test_sigma_for_reads_the_cell_then_the_marginal_then_the_global():
    from gaffer.optimize.scenarios import sigma_for

    table = _sigma_table()
    assert sigma_for(table, 1.0, 10.0) == 0.90        # cell 0_0
    assert sigma_for(table, 1.0, 85.0) == 1.40        # cell 0_3
    assert sigma_for(table, 3.5, 85.0) == 2.60        # no cell -> ep bin 2
    assert sigma_for(table, 5.0, 85.0) == 2.00        # no cell, no marginal
    assert sigma_for(None, 1.0, 10.0) is None
    assert sigma_for({}, 1.0, 10.0) is None


def test_sigma_for_refuses_an_implausible_sigma():
    """A table that says a 3-point forecast has a standard deviation of 40
    is corrupt, and the heuristic is a better answer than that."""
    from gaffer.optimize.scenarios import SIGMA_MAX, sigma_for

    table = _sigma_table() | {"sigma": {"0_0": SIGMA_MAX + 1.0},
                              "ep_marginal": {}, "global": None}
    assert sigma_for(table, 1.0, 10.0) is None


def test_the_calibrated_draw_is_absolute_not_relative():
    """The heuristic scales by the EP itself; the fitted table is a residual
    standard deviation in points, so it does not."""
    import numpy as np

    from gaffer.optimize.scenarios import noise_ep

    ep = {(1, 5): 1.0}
    xmins = {(1, 5): 10.0}
    draw = float(np.random.default_rng(7).standard_normal())
    out = noise_ep(ep, xmins, np.random.default_rng(7),
                   table=_sigma_table())
    assert out[(1, 5)] == pytest.approx(max(0.0, 1.0 + 0.90 * draw))


def test_the_calibrated_draw_still_floors_at_zero():
    import numpy as np

    from gaffer.optimize.scenarios import noise_ep

    out = noise_ep({(1, 5): 0.1}, {(1, 5): 10.0},
                   np.random.default_rng(1), table=_sigma_table())
    assert out[(1, 5)] >= 0.0


def test_the_table_keeps_nailed_players_nailed():
    """The heuristic's nailedness scaling exists so a 90-minute starter does
    not flip between sims. The empirical table has to keep that property, and
    it does it through the xMins axis rather than through an assumption."""
    import numpy as np

    from gaffer.optimize.scenarios import sigma_for

    table = _sigma_table() | {
        "sigma": {"0_0": 2.50, "0_3": 0.40}, "ep_marginal": {}, "global": None}
    assert sigma_for(table, 1.0, 85.0) < sigma_for(table, 1.0, 10.0)


def test_a_cell_with_no_xmins_entry_still_passes_through_untouched():
    import numpy as np

    from gaffer.optimize.scenarios import noise_ep

    out = noise_ep({(1, 5): 4.0}, {}, np.random.default_rng(3),
                   table=_sigma_table())
    assert out[(1, 5)] == 4.0


def test_noised_pool_uses_the_table_when_one_is_given():
    import numpy as np
    import pandas as pd

    from gaffer.optimize.scenarios import noised_pool

    pool = pd.DataFrame({"code": [1], "ep": [{5: 1.0}]})
    draw = float(np.random.default_rng(11).standard_normal())
    out = noised_pool(pool, {(1, 5): 10.0}, np.random.default_rng(11),
                      table=_sigma_table())
    assert out["ep"].iloc[0][5] == pytest.approx(max(0.0, 1.0 + 0.90 * draw))
```

Append to `tests/test_v6_degradation.py`:

```python
# --- rail 4: no noise asset == the pre-v6 heuristic, value for value -------

def test_no_noise_asset_is_the_pre_v6_heuristic_exactly(monkeypatch):
    """``table=None`` means "load the shipped asset", so the absent asset is
    simulated at the loader rather than by the repository happening not to
    carry one yet — the rail is about a clone without the file, and it has to
    hold just as firmly once the file is committed."""
    import numpy as np

    import gaffer.optimize.scenarios as sc

    monkeypatch.setattr(sc, "scenario_noise", lambda: None)
    ep = {(1, 5): 4.0, (2, 5): 1.0}
    xmins = {(1, 5): 88.0, (2, 5): 20.0}
    out = sc.noise_ep(ep, xmins, np.random.default_rng(42))

    rng = np.random.default_rng(42)
    for key, value in ep.items():
        scale = (sc.NOISE_FLOOR_XMINS - xmins[key]) / sc.NOISE_DENOM
        want = max(0.0, value + value * scale * float(rng.standard_normal()))
        assert out[key] == want


def test_an_unreadable_noise_asset_degrades_to_the_heuristic(monkeypatch):
    import gaffer.optimize.scenarios as sc

    def boom():
        raise ValueError("not JSON")

    monkeypatch.setattr(sc, "load_scenario_noise", boom)
    sc.scenario_noise.cache_clear()
    try:
        assert sc.scenario_noise() is None
    finally:
        sc.scenario_noise.cache_clear()


def test_the_shipped_asset_is_optional_by_construction():
    """A clone with no scenario_noise.json must load, not raise."""
    from gaffer.assets import load_scenario_noise, scenario_noise_exists

    if not scenario_noise_exists():
        assert load_scenario_noise() is None
    else:
        payload = load_scenario_noise()
        assert set(payload) >= {"ep_edges", "xmins_edges", "sigma"}
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_scenarios.py tests/test_v6_degradation.py -x -q
```

Expected: `ImportError: cannot import name 'bin_index' from 'gaffer.optimize.scenarios'`.

- [ ] **Step 3: Add the asset loader**

Append to `src/gaffer/assets/__init__.py`:

```python
SCENARIO_NOISE = "scenario_noise.json"


def scenario_noise_exists() -> bool:
    """Whether the calibrated scenario-noise table is shipped.

    Optional like :data:`DECISION_PRIORS` and :data:`INJURY_CURVES`, and for
    the same reason: spec §2's degradation rail says a clone without it falls
    back to the ``(92 - xmins) / 134`` heuristic, which is the pre-v6
    behaviour exactly. It is also genuinely absent for part of v6's own life —
    the code ships before the calibration run does.
    """
    return files(__package__).joinpath(SCENARIO_NOISE).is_file()


def load_scenario_noise() -> dict | None:
    """The residual-σ table, or ``None`` when the asset is absent.

    ``None`` rather than an empty dict, so a caller cannot mistake "not
    calibrated" for "calibrated, and the answer is no noise at all" — the two
    are opposite instructions to the scenario sweep.
    """
    if not scenario_noise_exists():
        return None
    return json.loads(
        files(__package__).joinpath(SCENARIO_NOISE).read_text(
            encoding="utf-8"))
```

- [ ] **Step 4: Teach `noise_ep` the table**

In `src/gaffer/optimize/scenarios.py`, add to the imports at the top (after
`from dataclasses import dataclass`):

```python
from functools import lru_cache
```

and after the `from gaffer.optimize.milp import Plan, SolveInput, solve_plan` line:

```python
from gaffer.assets import load_scenario_noise
```

Add, immediately after the `NOISE_DENOM` docstring block:

```python
SIGMA_MAX = 10.0
"""Refusal bound on a fitted σ.

A residual standard deviation of ten points on a weekly FPL forecast is not a
volatile player, it is a broken table — and the heuristic is a better answer
than a broken table. Matches the validator in
:mod:`gaffer.calibrate_noise`, deliberately: the write side refuses to
produce one and the read side refuses to use one.
"""


@lru_cache(maxsize=1)
def scenario_noise() -> dict | None:
    """The shipped residual-σ table, read once per process.

    Cached because a scenario sweep calls :func:`noise_ep` once per player per
    gameweek per scenario — tens of thousands of times — and re-reading a JSON
    file for each of them would cost more than the solves.

    Every failure is the same failure: no asset, unreadable asset, asset that
    is not JSON. All of them return ``None``, which every caller reads as "use
    the heuristic".
    """
    try:
        return load_scenario_noise()
    except Exception as exc:  # noqa: BLE001 — never blocks a sweep
        print(f"scenario noise asset unreadable, using the heuristic: {exc}")
        return None


def bin_index(value: float, edges: list[float]) -> int:
    """Which half-open bin ``value`` falls in, given the left edges.

    ``edges`` are left edges only — ``[0, 2, 3, 4, 6]`` is five bins, the last
    of which runs to infinity. A value below the first edge lands in bin 0
    rather than at -1: expected points cannot be negative, and a stray -0.0
    indexing off the front of the table would silently read the *last* cell.
    """
    idx = 0
    for i, edge in enumerate(edges):
        if float(value) >= float(edge):
            idx = i
    return idx


def sigma_for(table: dict | None, ep_value: float,
              xmins: float) -> float | None:
    """σ for one (EP bin, xMins bin) cell, or ``None`` to use the heuristic.

    Three deep, exactly as the calibration writes it: the cell if it was
    populated (100+ observations), else the EP bin's marginal, else the global
    residual σ. ``None`` at the end of that chain — or for a σ that fails the
    :data:`SIGMA_MAX` sanity bound — hands the caller back to the heuristic
    rather than inventing a scale.
    """
    if not table:
        return None
    ep_edges = [float(e) for e in table.get("ep_edges") or []]
    x_edges = [float(e) for e in table.get("xmins_edges") or []]
    if not ep_edges or not x_edges:
        return None
    i = bin_index(float(ep_value), ep_edges)
    j = bin_index(float(xmins), x_edges)
    cell = (table.get("sigma") or {}).get(f"{i}_{j}")
    if cell is None:
        cell = (table.get("ep_marginal") or {}).get(str(i))
    if cell is None:
        cell = table.get("global")
    if cell is None:
        return None
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return value if 0.0 < value < SIGMA_MAX else None
```

Replace `noise_ep` entirely:

```python
def noise_ep(ep: dict[tuple[int, int], float],
             xmins: dict[tuple[int, int], float],
             rng: np.random.Generator,
             table: dict | None = None) -> dict[tuple[int, int], float]:
    """One noised copy of an EP table.

    Two scales, one draw. Where the calibrated table has something to say,
    ``ep_noised = max(0, ep + σ(ep bin, xMins bin) * N(0, 1))`` — σ is an
    empirical residual standard deviation in *points*, so it is absolute and
    is not multiplied by the EP again. Where it has nothing to say (no asset,
    an unpopulated cell with no fallback, a σ that fails the sanity bound) the
    pre-v6 heuristic stands: ``ep + ep * (92 - xmins) / 134 * N(0, 1)``.

    The draw is taken **before** the branch on purpose. Both paths consume
    exactly one standard normal per cell, so a seed produces the same sequence
    of draws either way and the two arms of gate S1 differ in the scale
    applied to them and in nothing else.

    No cross-gameweek correlation: a player's *minutes* risk really is close
    to independent week to week once the fixture is known, and spec §10 lists
    correlation as YAGNI until the simple version proves insufficient.

    Clipped at zero because a negative EP is not a worse player, it is an
    incoherent one — the MILP would want to leave a squad slot empty, which it
    cannot do, so it would distort the whole board instead.

    Cells with no xMins entry pass through untouched: "we have no minutes
    prediction for this player" is not the same claim as "his minutes are
    certain", and inventing a scale for him would be the worse error.

    ``table`` of ``None`` means "read the shipped asset"; pass one explicitly
    to price a whole sweep off a single load.
    """
    if table is None:
        table = scenario_noise()
    out: dict[tuple[int, int], float] = {}
    for key, value in ep.items():
        xm = xmins.get(key)
        if xm is None:
            out[key] = value
            continue
        draw = float(rng.standard_normal())
        sigma = sigma_for(table, value, xm)
        if sigma is None:
            scale = (NOISE_FLOOR_XMINS - xm) / NOISE_DENOM
            out[key] = max(0.0, value + value * scale * draw)
        else:
            out[key] = max(0.0, value + sigma * draw)
    return out
```

Replace `noised_pool`'s signature and body head so the table is loaded once:

```python
def noised_pool(pool: pd.DataFrame, xmins: dict[tuple[int, int], float],
                rng: np.random.Generator,
                table: dict | None = None) -> pd.DataFrame:
    """A copy of the candidate pool with every ``ep`` dict noised.

    The *pool* is noised rather than rebuilt from noised EP, and that is a
    deliberate choice rather than a shortcut: ``build_pool`` applies a top-N
    filter per position, so rebuilding it per scenario would change which
    players are even candidates from one scenario to the next, and a move
    frequency computed across scenarios with different candidate sets is
    counting incomparable things. Fixing the board and varying only the values
    on it is what makes the frequencies mean something.

    The σ table is resolved once here rather than once per player: the loader
    is cached, but the lookup through it is not free at pool scale.
    """
    if table is None:
        table = scenario_noise()
    out = pool.copy()
    cells = []
    for code, cell in zip(pool["code"], pool["ep"]):
        keyed = {(int(code), int(gw)): float(v) for gw, v in cell.items()}
        noised = noise_ep(keyed, xmins, rng, table=table)
        cells.append({gw: noised[(int(code), int(gw))] for gw in cell})
    out["ep"] = cells
    return out
```

- [ ] **Step 5: Run, expect pass**

```bash
uv run pytest tests/test_scenarios.py tests/test_v6_degradation.py \
  tests/test_policy.py tests/test_v4c_degradation.py -q
```

Expected: all pass. `test_v4c_degradation.py` is in the list because it pins the
`[scenarios] n = 0` CLI output character for character, and a changed noise path must not
have disturbed it.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/assets/__init__.py src/gaffer/optimize/scenarios.py \
  tests/test_scenarios.py tests/test_v6_degradation.py
git commit -m "feat: scenario noise reads a calibrated sigma table when one ships" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 4 — `gaffer calibrate-noise`: the fitting half

**Files:** `src/gaffer/calibrate_noise.py` (new), `src/gaffer/cli.py` (new command after `calibrate_injuries`, `:298`), `tests/test_calibrate_noise.py` (new), `tests/data/scenario_noise.json` (new fixture), `tests/test_cli.py` (append).

**This task does not write `src/gaffer/assets/scenario_noise.json`.** It writes the code that
can, a fixture that proves the loader reads the shape, and a CLI the orchestrator runs later.
Do not run the real calibration and do not commit an asset.

- [ ] **Step 1: Commit the fixture asset**

Create `tests/data/scenario_noise.json` — a small, obviously-fake table in the exact shape
the writer produces:

```json
{
  "version": 1,
  "generated_at": "2026-08-27T09:00:00+00:00",
  "git_sha": "fixture",
  "season": "2024-25",
  "rows": 12000,
  "ep_edges": [0.0, 2.0, 3.0, 4.0, 6.0],
  "xmins_edges": [0.0, 30.0, 60.0, 80.0, 90.1],
  "sigma": {"0_0": 0.9, "0_3": 1.4, "1_3": 2.1, "2_3": 2.8, "3_3": 3.6},
  "obs": {"0_0": 4000, "0_3": 5000, "1_3": 1500, "2_3": 900, "3_3": 400},
  "ep_marginal": {"0": 1.1, "1": 2.2, "2": 2.9, "3": 3.7, "4": 4.8},
  "ep_marginal_obs": {"0": 9000, "1": 1600, "2": 950, "3": 420, "4": 30},
  "global": 2.0,
  "min_cell_obs": 100
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_calibrate_noise.py`:

```python
"""Offline calibration of the scenario-noise σ table (spec §2).

No network and no training here: the expensive half (``residual_rows``) is
exercised by the orchestrator's real run, and everything this suite touches is
the arithmetic that turns residuals into an asset.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gaffer.calibrate_noise import (EP_EDGES, MIN_CELL_OBS, REQUIRED_KEYS,
                                    SIGMA_MAX, XMINS_EDGES, fit_sigmas,
                                    write_noise)

FIXTURE = Path(__file__).parent / "data" / "scenario_noise.json"


def _rows(n_per_cell: int = 200, seed: int = 0) -> pd.DataFrame:
    """Synthetic residuals: two EP bins x two xMins bins, with a deliberately
    thin cell that has to pool up to its EP marginal."""
    rng = np.random.default_rng(seed)
    rows = []
    for ep, x, sigma, n in ((1.0, 10.0, 3.0, n_per_cell),
                            (1.0, 85.0, 0.5, n_per_cell),
                            (5.0, 85.0, 4.0, n_per_cell),
                            (5.0, 10.0, 4.0, 5)):
        for _ in range(n):
            rows.append({"code": 1, "gw": 5, "ep": ep, "xmins": x,
                         "points": ep + float(rng.normal(0.0, sigma))})
    return pd.DataFrame(rows)


def test_fit_sigmas_fits_a_sigma_per_populated_cell():
    out = fit_sigmas(_rows())
    assert out["sigma"]["0_0"] == pytest.approx(3.0, abs=0.6)
    assert out["sigma"]["0_3"] == pytest.approx(0.5, abs=0.2)
    assert out["sigma"]["3_3"] == pytest.approx(4.0, abs=0.9)


def test_a_thin_cell_is_left_out_so_serving_pools_it_up():
    """Five observations is not a standard deviation. The cell is recorded in
    ``obs`` — the count is evidence — but not in ``sigma``, so
    ``sigma_for`` falls through to the EP marginal."""
    out = fit_sigmas(_rows())
    assert out["obs"]["3_0"] == 5
    assert "3_0" not in out["sigma"]
    assert "3" in out["ep_marginal"]


def test_the_nailedness_property_survives_the_fit():
    """The heuristic's whole purpose was that nailed players do not flip
    between sims. The table has to reproduce it from the data rather than be
    assumed to."""
    out = fit_sigmas(_rows())
    assert out["sigma"]["0_3"] < out["sigma"]["0_0"]


def test_the_global_sigma_is_always_there_as_the_last_resort():
    out = fit_sigmas(_rows())
    assert out["global"] > 0.0
    assert out["rows"] == len(_rows())


def test_fit_sigmas_carries_the_edges_it_was_fitted_on():
    out = fit_sigmas(_rows())
    assert out["ep_edges"] == EP_EDGES
    assert out["xmins_edges"] == XMINS_EDGES
    assert out["min_cell_obs"] == MIN_CELL_OBS


def test_rows_with_no_xmins_are_dropped_rather_than_binned_at_zero():
    """A player with no minutes prediction is not a player expected to play
    zero minutes, and binning him as one would poison the 0-30 cell."""
    rows = _rows()
    rows.loc[:9, "xmins"] = float("nan")
    out = fit_sigmas(rows)
    assert out["rows"] == len(rows) - 10


# --- the asset writer -------------------------------------------------------

def _payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_write_noise_round_trips_the_fixture(tmp_path):
    dest = write_noise(_payload(), tmp_path / "scenario_noise.json")
    assert json.loads(dest.read_text())["sigma"]["0_0"] == 0.9


def test_write_noise_refuses_a_payload_missing_a_required_key(tmp_path):
    for key in REQUIRED_KEYS:
        payload = _payload()
        payload.pop(key)
        with pytest.raises(ValueError, match=key):
            write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_a_non_finite_sigma(tmp_path):
    payload = _payload()
    payload["sigma"]["0_0"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_a_non_positive_sigma(tmp_path):
    payload = _payload()
    payload["sigma"]["0_0"] = 0.0
    with pytest.raises(ValueError, match="positive"):
        write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_an_absurd_sigma(tmp_path):
    payload = _payload()
    payload["sigma"]["0_0"] = SIGMA_MAX + 1.0
    with pytest.raises(ValueError, match="below"):
        write_noise(payload, tmp_path / "x.json")


def test_write_noise_refuses_a_table_with_no_sigmas_at_all(tmp_path):
    """An empty table is worse than none: the loader would read it, find
    nothing, and fall through cell by cell for the whole sweep."""
    payload = _payload()
    payload["sigma"] = {}
    payload["ep_marginal"] = {}
    with pytest.raises(ValueError, match="no fitted"):
        write_noise(payload, tmp_path / "x.json")


def test_the_fixture_is_readable_by_the_serving_lookup():
    """The write side and the read side agree about the shape. This is the
    only place they meet before the orchestrator's real run."""
    from gaffer.optimize.scenarios import sigma_for

    table = _payload()
    assert sigma_for(table, 1.0, 10.0) == 0.9
    assert sigma_for(table, 4.5, 85.0) == 3.6
    assert sigma_for(table, 7.0, 85.0) == 4.8      # marginal
    assert sigma_for(table, 7.0, 20.0) == 4.8      # marginal again
```

Append to `tests/test_cli.py`:

```python
def test_calibrate_noise_is_registered():
    from typer.testing import CliRunner

    from gaffer.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "calibrate-noise" in result.output
```

- [ ] **Step 3: Run them, expect failure**

```bash
uv run pytest tests/test_calibrate_noise.py tests/test_cli.py -x -q
```

Expected: `ModuleNotFoundError: No module named 'gaffer.calibrate_noise'`.

- [ ] **Step 4: Write the calibration module**

Create `src/gaffer/calibrate_noise.py`:

```python
"""Offline calibration of the scenario sweep's noise scale (spec §2).

``optimize/scenarios.noise_ep`` shipped with ``ep * (92 - xmins) / 134`` —
a community-standard formula that was never fitted to anything. It has the
right *shape* (almost all of FPL's forecast error is "did he play", not "how
well did he play") and an unknown *scale*, and the scale is what decides
whether a transfer surviving 32 of 40 noised worlds means anything.

So it is measured. On the walk-forward benchmark's own predictions — the same
train-on-2022-24, predict-every-week-of-2024-25 protocol ``evaluate --mode
benchmark`` runs — residuals ``points - ep`` are binned by predicted EP and by
expected minutes, and a standard deviation is fitted per cell. Cells too thin
to fit pool up to their EP bin's marginal, and that to the global residual σ.

The result ships as ``assets/scenario_noise.json``, in git, so a fresh clone
noises sensibly without ever running this. Absent, ``noise_ep`` uses the
heuristic and nothing else changes.

Like :mod:`gaffer.calibrate_decisions`, this module is deliberately isolated
from the advise path: nothing in ``advise.py`` imports it and it does no work
at import time.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ASSET_PATH = Path("src/gaffer/assets/scenario_noise.json")

EP_EDGES = [0.0, 2.0, 3.0, 4.0, 6.0]
"""Left edges of the predicted-EP bins.

Five bins: the great mass of bench fodder under 2, then a bin per point up to
6, then everything above. Finer at the top because that is where the squad
decisions actually are, and where a mis-stated σ costs a captaincy.
"""

XMINS_EDGES = [0.0, 30.0, 60.0, 80.0, 90.1]
"""Left edges of the expected-minutes bins.

60 and 80 are the two thresholds the game itself cares about (the appearance
step, and "nailed"). 90.1 exists so the handful of rows that ``xmins_by_
player_gw`` clips to just under 92 have somewhere to go.
"""

MIN_CELL_OBS = 100
"""Observations a cell needs before its σ is trusted.

Below this the cell is *recorded* in ``obs`` — the count is evidence about
where the data is thin — but left out of ``sigma``, so serving falls through
to the EP bin's marginal.
"""

SIGMA_MAX = 10.0
"""Refusal bound, matching ``optimize.scenarios.SIGMA_MAX``."""

REQUIRED_KEYS = ("version", "generated_at", "season", "ep_edges",
                 "xmins_edges", "sigma", "obs", "ep_marginal", "global")


def bin_index(value: float, edges: list[float]) -> int:
    """Which half-open bin ``value`` falls in. See
    :func:`gaffer.optimize.scenarios.bin_index` — the same rule, restated
    here so the fitting side does not import the serving side."""
    idx = 0
    for i, edge in enumerate(edges):
        if float(value) >= float(edge):
            idx = i
    return idx


def residual_rows(max_train_idx: int | None = None,
                  test_idx: int | None = None) -> pd.DataFrame:
    """``[code, gw, ep, xmins, points]`` over the benchmark's test season.

    Deliberately the *benchmark* protocol and not a fresh one: it is already
    the codebase's honest out-of-sample walk (a hard season split, features
    leakage-safe within the season, one gameweek at a time), and a second
    walk-forward here would be a second thing to keep in step with it.

    ``xmins`` comes from :func:`gaffer.optimize.scenarios.xmins_by_player_gw`
    — the same function the live sweep bins on, so a cell fitted here is the
    cell that will be read there.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.errors import GafferError
    from gaffer.evaluation import (BENCHMARK_TEST_IDX,
                                   BENCHMARK_TRAIN_MAX_IDX,
                                   benchmark_scoring, benchmark_split)
    from gaffer.models.assemble import (apply_calibration, assemble_ep,
                                        ep_matrix)
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)
    from gaffer.optimize.scenarios import xmins_by_player_gw

    max_train_idx = (BENCHMARK_TRAIN_MAX_IDX if max_train_idx is None
                     else max_train_idx)
    test_idx = BENCHMARK_TEST_IDX if test_idx is None else test_idx

    df, tg, _ = load_training_frame()
    train_df, test_df = benchmark_split(df, max_train_idx, test_idx)
    train_tg, _ = benchmark_split(tg, max_train_idx, test_idx)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    # The bundled scoring table is the current season's; the test season is
    # not — the same restatement evaluate_benchmark makes, and for the same
    # reason: a residual measured against points the season never awarded is
    # not a residual.
    scoring = benchmark_scoring(scoring_table(load_bootstrap_sample()))

    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        xm = xmins_by_player_gw(comp)
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            points=("total_points", "sum"))
        joined = ep.merge(truth, on=["code", "gw"], how="inner")
        joined["xmins"] = [float(xm.get((int(c), int(g)), float("nan")))
                           for c, g in zip(joined["code"], joined["gw"])]
        parts.append(joined[["code", "gw", "ep", "xmins", "points"]])
        print(f"noise gw{gw}: {len(parts[-1])} rows", flush=True)

    if not parts:
        raise GafferError(
            "no benchmark rows to calibrate scenario noise on — run "
            "`gaffer build-history` and `gaffer train` first")
    return pd.concat(parts, ignore_index=True)


def fit_sigmas(rows: pd.DataFrame, ep_edges: list[float] | None = None,
               xmins_edges: list[float] | None = None,
               min_obs: int = MIN_CELL_OBS) -> dict:
    """Residuals -> the σ table, its observation counts and its fallbacks.

    ``ddof=0``: this is the standard deviation of the residuals that were
    actually observed, not an estimate of a parameter of some population they
    were drawn from, and at the cell sizes involved the difference is in the
    fourth decimal anyway.

    Rows with no ``xmins`` are dropped rather than binned at zero. A player
    the minutes model said nothing about is not a player expected to play no
    minutes, and folding him into the 0-30 cell would hand the sweep a σ built
    from a different question.
    """
    ep_edges = EP_EDGES if ep_edges is None else list(ep_edges)
    xmins_edges = XMINS_EDGES if xmins_edges is None else list(xmins_edges)
    frame = rows.dropna(subset=["ep", "xmins", "points"]).copy()
    frame["resid"] = (frame["points"].astype(float)
                      - frame["ep"].astype(float))
    frame["ep_bin"] = [bin_index(v, ep_edges) for v in frame["ep"]]
    frame["x_bin"] = [bin_index(v, xmins_edges) for v in frame["xmins"]]

    marginal: dict[str, float] = {}
    marginal_obs: dict[str, int] = {}
    for i, part in frame.groupby("ep_bin"):
        marginal[str(int(i))] = round(float(part["resid"].std(ddof=0)), 4)
        marginal_obs[str(int(i))] = int(len(part))

    sigma: dict[str, float] = {}
    obs: dict[str, int] = {}
    for (i, j), part in frame.groupby(["ep_bin", "x_bin"]):
        key = f"{int(i)}_{int(j)}"
        obs[key] = int(len(part))
        if len(part) >= int(min_obs):
            sigma[key] = round(float(part["resid"].std(ddof=0)), 4)

    return {
        "ep_edges": ep_edges,
        "xmins_edges": xmins_edges,
        "sigma": sigma,
        "obs": obs,
        "ep_marginal": marginal,
        "ep_marginal_obs": marginal_obs,
        "global": round(float(frame["resid"].std(ddof=0)), 4),
        "rows": int(len(frame)),
        "min_cell_obs": int(min_obs),
    }


def run_calibration(max_train_idx: int | None = None,
                    test_idx: int | None = None) -> dict:
    """Replay the benchmark season and assemble the asset payload."""
    from gaffer.evaluation import BENCHMARK_TEST_SEASON, git_sha, run_at

    rows = residual_rows(max_train_idx, test_idx)
    payload = fit_sigmas(rows)
    payload.update({
        "version": 1,
        "generated_at": run_at(),
        "git_sha": git_sha(),
        "season": BENCHMARK_TEST_SEASON,
    })
    return payload


def write_noise(payload: dict, path: Path | str = ASSET_PATH) -> Path:
    """Validate and write the asset.

    Validated before writing because a hollow σ table is worse than none at
    all: an absent asset degrades honestly to the heuristic, while a table of
    zeroes tells the sweep every forecast is certain and hands the MILP forty
    identical boards — forty scenarios agreeing 100% of the time about a
    transfer nobody tested.
    """
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(
            f"scenario noise payload is missing {missing[0]} (of {missing}) "
            "— refusing to write a partial asset")
    sigmas = dict(payload.get("sigma") or {})
    sigmas.update({f"marginal_{k}": v
                   for k, v in (payload.get("ep_marginal") or {}).items()})
    if payload.get("global") is not None:
        sigmas["global"] = payload["global"]
    if not sigmas:
        raise ValueError(
            "scenario noise payload carries no fitted sigmas — every cell "
            "would fall through to the heuristic anyway")
    for key, value in sigmas.items():
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"sigma {key} is not finite ({value})")
        if number <= 0.0:
            raise ValueError(f"sigma {key} is not positive ({value})")
        if number >= SIGMA_MAX:
            raise ValueError(
                f"sigma {key} is not below {SIGMA_MAX} ({value}) — a residual "
                "standard deviation that large is a broken fit, not a "
                "volatile player")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest
```

- [ ] **Step 5: Register the CLI command**

In `src/gaffer/cli.py`, after the `calibrate_injuries` command body (before `@app.command()
def evaluate`), add:

```python
@app.command("calibrate-noise")
def calibrate_noise():
    """Fit src/gaffer/assets/scenario_noise.json from benchmark residuals.

    Slow — one full benchmark fit and a walk of the test season — and
    refreshed rarely: once a season, or when the components move materially.
    The asset it writes ships in git; without it the scenario sweep falls back
    to the (92 - xmins) / 134 heuristic, which is the pre-v6 behaviour.
    """
    from gaffer.calibrate_noise import (ASSET_PATH, run_calibration,
                                        write_noise)

    payload = run_calibration()
    dest = write_noise(payload, ASSET_PATH)
    typer.echo(f"Fitted {len(payload['sigma'])} cells and "
               f"{len(payload['ep_marginal'])} EP marginals from "
               f"{payload['rows']} residuals on {payload['season']} "
               f"(global sigma {payload['global']}) -> {dest}")
```

- [ ] **Step 6: Run, expect pass**

```bash
uv run pytest tests/test_calibrate_noise.py tests/test_cli.py \
  tests/test_scenarios.py tests/test_v6_degradation.py -q
```

Expected: all pass.

- [ ] **Step 7: Prove the asset is still absent**

```bash
test ! -f src/gaffer/assets/scenario_noise.json && echo "asset absent, as planned"
```

Expected: `asset absent, as planned`. If it exists, something ran the calibration — delete it
and tell the orchestrator; this plan does not ship it.

- [ ] **Step 8: Commit**

```bash
git add src/gaffer/calibrate_noise.py src/gaffer/cli.py \
  tests/test_calibrate_noise.py tests/test_cli.py \
  tests/data/scenario_noise.json
git commit -m "feat: gaffer calibrate-noise fits the residual sigma table" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 5 — U2's artifacts: availability snapshot and pruned advice history

**Files:** `src/gaffer/artifacts.py` (append after `load_advice`, `:350`), `src/gaffer/advise.py` (`run_advise`'s tail, after `save_solve_state(SolveState(...))` closes at `:911`), `tests/test_artifacts.py` (append), `tests/test_advise.py` (append).

**The components parquet already exists** — `run_advise:899` writes
`reports/components_gw{N}.parquet` through `save_components` and `load_components` reads it
back. Spec §4's first bullet is already shipped; this task adds only the two artifacts that
are genuinely missing.

**Protected-test constraint:** both new lines go at the very bottom of `run_advise`, after the
`save_solve_state(SolveState(...))` call closes and before `return advice`. That region is
**below** `ep_gw1 =`, so neither line may contain the substring `pool_ep` — neither does.
`save_components(`, `save_solve_state(`, `save_snapshots(players, teams, events, fx)` and
`pool_rows(pool, players, owned_now, ep_by, gws)` all stay exactly as they are.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_artifacts.py`:

```python
# --- v6: the availability snapshot -----------------------------------------

def _avail() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "status": "d", "chance_of_playing": 75,
         "injury_type": "hamstring", "expected_return_gw": 6,
         "p_start_hint": 0.0, "source": "premierinjuries|lineups",
         "fetched_at": "2026-09-04T09:00:00Z"},
        {"code": 2, "status": "a", "chance_of_playing": None,
         "injury_type": None, "expected_return_gw": None,
         "p_start_hint": None, "source": None, "fetched_at": None},
    ])


def test_save_availability_round_trips_through_parquet(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    path = art.save_availability(_avail(), 5)
    assert path == art.availability_path(5)
    back = art.load_availability(5)
    assert list(back.columns) == art.AVAILABILITY_COLS
    assert back.loc[back["code"] == 1, "injury_type"].iloc[0] == "hamstring"
    assert float(back.loc[back["code"] == 1, "expected_return_gw"].iloc[0]) == 6


def test_save_availability_fills_columns_a_flags_only_frame_lacks(
        tmp_path, monkeypatch):
    """With news off, ``news_availability`` returns the bare official slice.
    The snapshot still has to be readable by the news endpoint."""
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    official = pd.DataFrame([{"code": 1, "status": "a",
                              "chance_of_playing": None}])
    art.save_availability(official, 5)
    back = art.load_availability(5)
    assert list(back.columns) == art.AVAILABILITY_COLS
    assert back["injury_type"].isna().all()


def test_save_availability_never_raises(tmp_path, monkeypatch):
    """It is a snapshot for a UI panel. An advise run must not die of it."""
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    assert art.save_availability(None, 5) is None
    assert art.save_availability(pd.DataFrame(), 5) is None
    assert art.save_availability(pd.DataFrame({"nope": [1]}), 5) is None


def test_load_availability_is_none_when_nothing_was_written(tmp_path,
                                                            monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    assert art.load_availability(5) is None


# --- v6: the advice history log --------------------------------------------

def _advice(gw=5, captain=("Salah", 100), buys=(), sells=(), pts=61.5,
            chip=None) -> dict:
    return {
        "gw": gw, "deadline": "2026-09-05T10:00:00Z",
        "captain": {"code": captain[1], "name": captain[0]},
        "buys": [{"code": c, "name": n} for n, c in buys],
        "sells": [{"code": c, "name": n} for n, c in sells],
        "expected_pts": pts,
        "chip_table": ([] if chip is None
                       else [{"chip": chip, "gw": gw, "gain": 9.0,
                              "threshold": 8.0, "play_now": True}]),
    }


def test_append_advice_history_writes_one_file_per_run(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    first = art.append_advice_history(_advice(), 5,
                                      now=datetime(2026, 9, 4, 9, 0,
                                                   tzinfo=timezone.utc))
    second = art.append_advice_history(_advice(pts=63.0), 5,
                                       now=datetime(2026, 9, 4, 10, 0,
                                                    tzinfo=timezone.utc))
    assert first != second
    assert first.parent == art.ADVICE_HISTORY
    assert len(art.advice_history_files(5)) == 2
    assert json.loads(second.read_text())["expected_pts"] == 63.0


def test_advice_history_is_pruned_to_the_newest_twenty(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    for minute in range(25):
        art.append_advice_history(
            _advice(pts=float(minute)), 5,
            now=datetime(2026, 9, 4, 9, minute, tzinfo=timezone.utc))
    files = art.advice_history_files()
    assert len(files) == art.ADVICE_HISTORY_KEEP
    newest = json.loads(files[-1].read_text())
    assert newest["expected_pts"] == 24.0


def test_advice_history_files_filter_by_gameweek(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    art.append_advice_history(_advice(gw=5), 5,
                              now=datetime(2026, 9, 4, 9, 0,
                                           tzinfo=timezone.utc))
    art.append_advice_history(_advice(gw=6), 6,
                              now=datetime(2026, 9, 11, 9, 0,
                                           tzinfo=timezone.utc))
    assert len(art.advice_history_files(5)) == 1
    assert len(art.advice_history_files(6)) == 1
    assert len(art.advice_history_files()) == 2


def test_append_advice_history_never_raises(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(art, "ADVICE_HISTORY",
                        tmp_path / "nope" / "\0" / "bad")
    assert art.append_advice_history(_advice(), 5) is None


# --- v6: the run-to-run diff ------------------------------------------------

def test_diff_advice_reports_what_changed_between_two_runs():
    from gaffer.artifacts import diff_advice

    previous = _advice(captain=("Salah", 100), buys=[("Isak", 200)],
                       sells=[("Watkins", 300)], pts=61.5)
    current = _advice(captain=("Haaland", 101), buys=[("Wirtz", 201)],
                      sells=[("Watkins", 300)], pts=64.0, chip="bboost")
    out = diff_advice(previous, current)
    assert out["captain_from"]["name"] == "Salah"
    assert out["captain_to"]["name"] == "Haaland"
    assert [b["name"] for b in out["buys_added"]] == ["Wirtz"]
    assert [b["name"] for b in out["buys_dropped"]] == ["Isak"]
    assert out["sells_added"] == [] and out["sells_dropped"] == []
    assert out["expected_pts_delta"] == 2.5
    assert out["chip_from"] is None and out["chip_to"] == "bboost"


def test_diff_advice_of_two_identical_runs_is_empty_but_present():
    from gaffer.artifacts import diff_advice

    out = diff_advice(_advice(), _advice())
    assert out["buys_added"] == [] and out["buys_dropped"] == []
    assert out["captain_from"] is None and out["captain_to"] is None
    assert out["expected_pts_delta"] == 0.0
    assert out["changed"] is False


def test_diff_advice_tolerates_a_payload_missing_every_optional_key():
    """History written by an older build is still worth diffing."""
    from gaffer.artifacts import diff_advice

    out = diff_advice({}, {"expected_pts": 3.0})
    assert out["expected_pts_delta"] == 3.0
    assert out["changed"] is True
```

Add to the imports at the top of `tests/test_artifacts.py` (beside the existing ones):

```python
import json
from datetime import datetime, timezone
```

Append to `tests/test_advise.py`:

```python
def test_run_advise_persists_the_availability_and_history_artifacts():
    """Source-level seam: the news panel and the "since last run" strip both
    read files nothing else writes, and both are written at the very bottom
    of the run — below ep_gw1, so neither line may name the pool."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    state = src.index("save_solve_state(")
    avail = src.index("save_availability(avail, gw)")
    history = src.index("append_advice_history(asdict(advice), gw)")
    assert state < avail < history
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_artifacts.py tests/test_advise.py -x -q
```

Expected: `AttributeError: module 'gaffer.artifacts' has no attribute 'save_availability'`.

- [ ] **Step 3: Write the artifact helpers**

In `src/gaffer/artifacts.py`, add to the imports at the top:

```python
from datetime import datetime, timezone
```

and append at the end of the file:

```python
AVAILABILITY_COLS = ["code", "status", "chance_of_playing", "injury_type",
                     "expected_return_gw", "p_start_hint", "source",
                     "fetched_at"]
"""The availability frame's columns, in the order
:func:`gaffer.data.news.normalize.availability_frame` produces them.

A flags-only run (news disabled, every source down) produces the first three
and nothing else, so the missing five are filled with nulls on the way to
disk: the news endpoint reads one shape whatever the week did.
"""


def availability_path(gw: int) -> Path:
    return REPORTS / f"availability_gw{gw}.parquet"


def save_availability(avail, gw: int) -> Path | None:
    """Snapshot the availability frame this run predicted on.

    The only record of *why* the news layer moved a player: the shadow log
    banks what changed, and this banks the evidence that changed it. Nothing
    else reads the frame after ``predict_components`` consumes it.

    Never raises and returns ``None`` when there is nothing worth keeping —
    it is instrumentation for a UI panel, and an advise run that died of its
    own snapshot would be a much worse trade than a hidden panel.
    """
    try:
        if avail is None or len(avail) == 0:
            return None
        if "code" not in avail.columns:
            return None
        out = avail.copy()
        for col in AVAILABILITY_COLS:
            if col not in out.columns:
                out[col] = None
        out = out[AVAILABILITY_COLS].copy()
        # Parquet wants a settled dtype per column and an all-None object
        # column has none. Strings become nullable strings and the three
        # numeric columns become floats, so a flags-only week and a
        # news-heavy one write the same schema.
        for col in ("status", "injury_type", "source", "fetched_at"):
            out[col] = out[col].astype("object").where(
                out[col].notna(), None).astype("string")
        for col in ("chance_of_playing", "expected_return_gw",
                    "p_start_hint"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out["code"] = pd.to_numeric(out["code"], errors="coerce").astype(
            "int64")
        REPORTS.mkdir(exist_ok=True)
        path = availability_path(gw)
        out.to_parquet(path, index=False)
        return path
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"availability snapshot not written: {exc}")
        return None


def load_availability(gw: int) -> pd.DataFrame | None:
    """The snapshot for ``gw``, or ``None``.

    ``None`` rather than a domain error, unlike :func:`load_components`: an
    absent snapshot means the panel hides, and there is nothing for the user
    to go and run.
    """
    path = availability_path(gw)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        print(f"availability snapshot unreadable: {exc}")
        return None


ADVICE_HISTORY = REPORTS / "advice_history"

ADVICE_HISTORY_KEEP = 20
"""Runs kept on disk.

Enough to see a week's worth of re-runs and the two or three weeks before it,
few enough that the directory never becomes an archive nobody prunes. The diff
only ever reads the newest two of one gameweek.
"""


def _history_stamp(path: Path) -> str:
    """The ISO timestamp out of ``gw{N}-{stamp}.json``.

    Sorting on this rather than on mtime: two runs a second apart can share an
    mtime on a coarse filesystem, and a copied ``reports/`` directory has
    mtimes that say nothing at all. The stamp is written by the writer and
    sorts lexicographically because ISO-8601 does.
    """
    _, _, stamp = path.stem.partition("-")
    return stamp


def advice_history_files(gw: int | None = None) -> list[Path]:
    """Every banked run, oldest first; ``gw`` filters to one gameweek."""
    if not ADVICE_HISTORY.is_dir():
        return []
    files = [p for p in ADVICE_HISTORY.glob("gw*-*.json") if p.is_file()]
    if gw is not None:
        files = [p for p in files if p.name.startswith(f"gw{int(gw)}-")]
    return sorted(files, key=_history_stamp)


def prune_advice_history(keep: int = ADVICE_HISTORY_KEEP) -> int:
    """Drop everything but the newest ``keep`` runs. Returns how many went."""
    files = advice_history_files()
    doomed = files[:-keep] if len(files) > keep else []
    for path in doomed:
        path.unlink(missing_ok=True)
    return len(doomed)


def append_advice_history(payload: dict, gw: int,
                          now: datetime | None = None) -> Path | None:
    """Bank this run's advice payload and prune the log.

    One file per *run*, not per gameweek: re-running on Friday morning after
    the Thursday press conferences is the case the "since last run" strip
    exists for, and overwriting would destroy exactly the comparison the user
    wants. Pruned on write so nothing has to remember to.

    Never raises, for the same reason :func:`save_availability` does not.
    """
    try:
        ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
        stamp = (now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds")
        path = ADVICE_HISTORY / f"gw{int(gw)}-{stamp}.json"
        path.write_text(json.dumps(payload, indent=1, default=str))
        prune_advice_history()
        return path
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"advice history not written: {exc}")
        return None


def _players_by_code(payload: dict, key: str) -> dict[int, dict]:
    rows = payload.get(key) or []
    return {int(r["code"]): {"code": int(r["code"]),
                             "name": str(r.get("name", r["code"]))}
            for r in rows if isinstance(r, dict) and "code" in r}


def _recommended_chip(payload: dict) -> str | None:
    """The chip this run said to play now, or ``None``.

    Reads ``play_now`` — the flag ``run_advise`` sets by comparing each row's
    gain against its own θ threshold — rather than re-deriving it, so the diff
    cannot disagree with the report about what was recommended.
    """
    for row in payload.get("chip_table") or []:
        if isinstance(row, dict) and row.get("play_now"):
            return str(row.get("chip"))
    return None


def diff_advice(previous: dict, current: dict) -> dict:
    """What changed between two runs of the same gameweek.

    Structural, not textual: the UI renders "Wirtz in place of Isak", and a
    string diff of two JSON files could never say that. Everything is
    tolerant of a missing key, because the log outlives the shape of the
    payload it stores.
    """
    out: dict = {}
    for key in ("buys", "sells"):
        before = _players_by_code(previous, key)
        after = _players_by_code(current, key)
        out[f"{key}_added"] = [after[c] for c in sorted(set(after) - set(before))]
        out[f"{key}_dropped"] = [before[c]
                                 for c in sorted(set(before) - set(after))]
    prev_cap = previous.get("captain") or {}
    curr_cap = current.get("captain") or {}
    changed_cap = (prev_cap.get("code") != curr_cap.get("code")
                   and (prev_cap or curr_cap))
    out["captain_from"] = dict(prev_cap) if changed_cap and prev_cap else None
    out["captain_to"] = dict(curr_cap) if changed_cap and curr_cap else None
    prev_chip = _recommended_chip(previous)
    curr_chip = _recommended_chip(current)
    out["chip_from"] = prev_chip if prev_chip != curr_chip else None
    out["chip_to"] = curr_chip if prev_chip != curr_chip else None
    out["expected_pts_delta"] = round(
        float(current.get("expected_pts") or 0.0)
        - float(previous.get("expected_pts") or 0.0), 2)
    out["changed"] = bool(out["buys_added"] or out["buys_dropped"]
                          or out["sells_added"] or out["sells_dropped"]
                          or out["captain_to"] or out["chip_to"]
                          or out["chip_from"]
                          or out["expected_pts_delta"] != 0.0)
    return out
```

- [ ] **Step 4: The two lines in `run_advise`**

In `src/gaffer/advise.py`, extend the artifacts import to pull in the two new writers:

```python
from gaffer.artifacts import (SolveState, append_advice_history,
                              components_frame, data_warning,
                              ingested_through, pool_rows, save_availability,
                              save_components, save_snapshots,
                              save_solve_state)
```

and insert, after the `save_solve_state(SolveState(...))` call closes (the line
`        pool=pool_rows(pool, players, owned_now, ep_by, gws)))`) and before
`    return advice`:

```python
    # Two artifacts nothing in the pipeline reads: the availability frame this
    # run predicted on, and the payload itself, appended to a pruned log. Both
    # exist so the UI can answer "why?" and "what changed since Tuesday?"
    # offline, and both swallow their own failures.
    save_availability(avail, gw)
    append_advice_history(asdict(advice), gw)
```

- [ ] **Step 5: Run, expect pass**

```bash
uv run pytest tests/test_artifacts.py tests/test_advise.py \
  tests/test_odds.py tests/test_v5_degradation.py \
  tests/test_v6_degradation.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/artifacts.py src/gaffer/advise.py \
  tests/test_artifacts.py tests/test_advise.py
git commit -m "feat: bank the availability snapshot and a pruned advice history" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 6 — `GET /api/chips`

**Files:** `src/gaffer/web/routers/chips.py` (new), `src/gaffer/web/schemas.py` (append after `ChipPlan`, `:301`), `src/gaffer/web/app.py` (import at `:25-26`, register at `:71-77`), `tests/test_web_chips.py` (new).

Disk-only: the chip table and the wildcard squad are both *already computed* by
`run_advise` and sit in the advice JSON. This endpoint resolves them to names, prices and
expected points through the saved solve state and computes the squad diff server-side. It
solves nothing — `/api/chips/plan` in `meta.py` is the endpoint that re-solves, and it stays
exactly where it is.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_chips.py`:

```python
"""GET /api/chips — the workbench's read model."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import POOL_COLS, SolveState, save_solve_state
from gaffer.web.app import create_app

ADVICE = {
    "gw": 5,
    "deadline": "2026-09-05T10:00:00Z",
    "expected_pts": 61.5,
    "chip_table": [
        {"chip": "wildcard", "gw": 5, "gain": 9.4, "per_week": 3.1,
         "threshold": 8.0, "play_now": True},
        {"chip": "bboost", "gw": 6, "gain": 2.0, "per_week": 2.0,
         "threshold": 4.0, "play_now": False},
        {"chip": "freehit", "gw": 7, "gain": 5.0, "per_week": 5.0,
         "threshold": 4.0, "play_now": True, "note": "conservative lower "
                                                     "bound"},
    ],
    "wildcard_now": {"gain_over_horizon": 9.4, "wc_squad": [100, 102],
                     "recommend": True},
}


def _pool() -> pd.DataFrame:
    rows = [
        {"code": 100, "name": "Salah", "position": "MID", "team_code": 14,
         "cost": 130, "sell": 130, "owned": True, "gw": 5, "ep_raw": 6.4},
        {"code": 101, "name": "Watkins", "position": "FWD", "team_code": 7,
         "cost": 90, "sell": 90, "owned": True, "gw": 5, "ep_raw": 4.1},
        {"code": 102, "name": "Wirtz", "position": "MID", "team_code": 14,
         "cost": 85, "sell": 85, "owned": False, "gw": 5, "ep_raw": 5.2},
    ]
    return pd.DataFrame(rows, columns=POOL_COLS)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def _write(tmp_path, advice=None, owned=(100, 101)):
    (tmp_path / "reports").mkdir(exist_ok=True)
    save_solve_state(SolveState(
        gw=5, gws=[5, 6, 7], deadline="2026-09-05T10:00:00Z",
        generated_at="2026-09-04T09:00:00+00:00", mode="weekly", bank=5,
        free_transfers=1, owned_codes=list(owned), lam=0.0, league_eo={},
        avail_by_gw={5: ["wildcard"], 6: [], 7: []},
        opt={"decay": 0.9, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "itb_value": 0.1, "hit_cost": 4,
             "horizon": 3},
        pool=_pool()))
    (tmp_path / "reports" / "gw5-advice.json").write_text(
        json.dumps(advice if advice is not None else ADVICE))


def test_chips_without_an_advice_run_is_a_friendly_404(client):
    response = client.get("/api/chips")
    assert response.status_code == 404
    assert "gaffer advise" in response.json()["detail"]


def test_chips_returns_the_table_with_its_thresholds(client, tmp_path):
    _write(tmp_path)
    body = client.get("/api/chips").json()
    assert body["gw"] == 5
    rows = {(r["chip"], r["gw"]): r for r in body["chips"]}
    assert rows[("wildcard", 5)]["gain"] == 9.4
    assert rows[("wildcard", 5)]["threshold"] == 8.0
    assert rows[("wildcard", 5)]["play_now"] is True
    assert rows[("bboost", 6)]["play_now"] is False
    assert rows[("freehit", 7)]["note"] == "conservative lower bound"


def test_chips_resolves_the_wildcard_squad_into_a_three_way_diff(client,
                                                                 tmp_path):
    """Kept / out / in, computed server-side: the page renders columns, it
    does not do set arithmetic over codes."""
    _write(tmp_path)
    wildcard = client.get("/api/chips").json()["wildcard"]
    assert wildcard["recommend"] is True
    assert wildcard["gain_over_horizon"] == 9.4
    assert [p["name"] for p in wildcard["kept"]] == ["Salah"]
    assert [p["name"] for p in wildcard["dropped"]] == ["Watkins"]
    assert [p["name"] for p in wildcard["added"]] == ["Wirtz"]
    added = wildcard["added"][0]
    assert added["price"] == 8.5 and added["ep"] == 5.2
    assert added["position"] == "MID"


def test_chips_without_a_wildcard_assessment_is_a_null_not_an_error(client,
                                                                    tmp_path):
    """GW1, or a half where the wildcard is already spent."""
    advice = dict(ADVICE, wildcard_now=None)
    _write(tmp_path, advice)
    body = client.get("/api/chips").json()
    assert body["wildcard"] is None
    assert len(body["chips"]) == 3


def test_chips_tolerates_a_squad_code_the_pool_no_longer_knows(client,
                                                               tmp_path):
    """A saved state and an advice file can disagree after a partial re-run.
    An unknown code is shown by its number rather than 500ing the page."""
    advice = dict(ADVICE, wildcard_now={"gain_over_horizon": 1.0,
                                        "wc_squad": [100, 999],
                                        "recommend": False})
    _write(tmp_path, advice)
    added = client.get("/api/chips").json()["wildcard"]["added"]
    assert [p["code"] for p in added] == [999]
    assert added[0]["name"] == "999" and added[0]["price"] == 0.0


def test_chips_with_an_empty_table_is_an_empty_list(client, tmp_path):
    _write(tmp_path, dict(ADVICE, chip_table=[], wildcard_now=None))
    body = client.get("/api/chips").json()
    assert body["chips"] == [] and body["wildcard"] is None
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_web_chips.py -x -q
```

Expected: every test 404s with the SPA fallback's detail, or fails on the missing router.

- [ ] **Step 3: Add the schemas**

In `src/gaffer/web/schemas.py`, append after the `ChipPlan` class:

```python
class ChipWorkbenchRow(BaseModel):
    """One (chip, gameweek) cell of the advice run's own chip table.

    ``threshold`` is the θ bar that week — the surplus the best remaining week
    is expected to offer — so the workbench can draw the gain against the bar
    rather than against an arbitrary axis. Both it and ``play_now`` are
    optional because an advice payload written before the chip policy landed
    carries neither.
    """

    chip: str
    gw: int
    gain: float
    per_week: float | None = None
    threshold: float | None = None
    play_now: bool = False
    note: str | None = None


class SquadPlayerRef(BaseModel):
    code: int
    name: str
    position: str
    price: float
    ep: float


class SquadDiff(BaseModel):
    """A candidate squad against the one you own, resolved server-side."""

    gain_over_horizon: float
    recommend: bool
    kept: list[SquadPlayerRef]
    dropped: list[SquadPlayerRef]
    added: list[SquadPlayerRef]


class ChipsWorkbench(BaseModel):
    gw: int
    chips: list[ChipWorkbenchRow]
    wildcard: SquadDiff | None = None
```

- [ ] **Step 4: Write the router**

Create `src/gaffer/web/routers/chips.py`:

```python
"""The chip workbench's read model (spec §3).

Disk-only and cheap: everything here was computed by ``gaffer advise`` and
written to ``reports/``. The workbench's *interactive* half re-solves through
the existing ``/api/whatif`` job flow, so no solver code lives here either —
this endpoint's whole job is to resolve codes into names, prices and expected
points, and to do the squad set arithmetic once, on the server, instead of in
three places in the page.

``/api/chips/plan`` in ``meta.py`` is a different endpoint and stays where it
is: that one *re-runs* ``evaluate_chips`` against the saved pool, and This
Week has called it since v3.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import latest_gw, load_advice, load_solve_state
from gaffer.errors import GafferError
from gaffer.web.schemas import (ChipsWorkbench, ChipWorkbenchRow, SquadDiff,
                                SquadPlayerRef)

router = APIRouter(prefix="/api", tags=["chips"])

NO_RUN = "no advice on disk yet — run `gaffer advise` first"


def _refs(codes, meta: dict[int, dict]) -> list[SquadPlayerRef]:
    """Codes -> rendered players, in code order.

    A code the saved pool no longer knows is shown by its number rather than
    dropped or raised on: a solve state and an advice file can disagree after
    a partial re-run, and a workbench that 500s because one player moved club
    is worse than one that says "999".
    """
    out = []
    for code in sorted(int(c) for c in codes):
        row = meta.get(code)
        out.append(SquadPlayerRef(
            code=code,
            name=str(row["name"]) if row else str(code),
            position=str(row["position"]) if row else "",
            price=round(float(row["cost"]) / 10, 1) if row else 0.0,
            ep=round(float(row["ep"]), 2) if row else 0.0))
    return out


@router.get("/chips", response_model=ChipsWorkbench)
def chips() -> ChipsWorkbench:
    gw = latest_gw()
    if gw is None:
        raise HTTPException(status_code=404, detail=NO_RUN)
    try:
        advice = load_advice(gw)
        state = load_solve_state(gw)
    except GafferError as exc:
        # 404 rather than the app-wide 422: the page hides its panels on a
        # missing artifact, and must not confuse that with a state it could
        # fix by re-running something.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    first_gw = state.gws[0] if state.gws else gw
    meta: dict[int, dict] = {}
    for row in state.pool.itertuples():
        code = int(row.code)
        # The pool carries one row per (candidate, gameweek); the first
        # gameweek's is the one the workbench prices against, and the rest
        # differ only in ep_raw.
        if code not in meta or int(row.gw) == first_gw:
            meta[code] = {"name": row.name, "position": row.position,
                          "cost": row.cost,
                          "ep": row.ep_raw if int(row.gw) == first_gw
                          else meta.get(code, {}).get("ep", row.ep_raw)}

    rows = [ChipWorkbenchRow(chip=str(r.get("chip", "")),
                             gw=int(r.get("gw", first_gw)),
                             gain=float(r.get("gain", 0.0)),
                             per_week=(None if r.get("per_week") is None
                                       else float(r["per_week"])),
                             threshold=(None if r.get("threshold") is None
                                        else float(r["threshold"])),
                             play_now=bool(r.get("play_now", False)),
                             note=(None if r.get("note") is None
                                   else str(r["note"])))
            for r in advice.get("chip_table") or []
            if isinstance(r, dict)]

    wildcard = None
    wc = advice.get("wildcard_now")
    if isinstance(wc, dict) and wc.get("wc_squad") is not None:
        squad = {int(c) for c in wc["wc_squad"]}
        owned = {int(c) for c in state.owned_codes}
        wildcard = SquadDiff(
            gain_over_horizon=round(float(wc.get("gain_over_horizon", 0.0)),
                                    2),
            recommend=bool(wc.get("recommend", False)),
            kept=_refs(squad & owned, meta),
            dropped=_refs(owned - squad, meta),
            added=_refs(squad - owned, meta))
    return ChipsWorkbench(gw=gw, chips=rows, wildcard=wildcard)
```

- [ ] **Step 5: Register the router**

In `src/gaffer/web/app.py`, change the router import to:

```python
from gaffer.web.routers import (advice, chips, league, live, meta, players,
                                quality, whatif)
```

and add, immediately after `app.include_router(advice.router)`:

```python
    app.include_router(chips.router)
```

- [ ] **Step 6: Run, expect pass**

```bash
uv run pytest tests/test_web_chips.py tests/test_web_meta.py \
  tests/test_web_app.py -q
```

Expected: all pass. `test_web_meta.py` is in the list to prove `/api/chips/plan` still
resolves beside the new `/api/chips`.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/routers/chips.py src/gaffer/web/schemas.py \
  src/gaffer/web/app.py tests/test_web_chips.py
git commit -m "feat: GET /api/chips serves the workbench read model" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 7 — `GET /api/components/{gw}`

**Files:** `src/gaffer/web/routers/components.py` (new), `src/gaffer/web/schemas.py` (append after `ChipsWorkbench`), `src/gaffer/web/app.py` (import + register), `tests/test_web_components.py` (new).

The parquet already exists (`artifacts.load_components`). This is the endpoint over it, keyed
by player so the ThisWeek rows can expand without a second request per player.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_components.py`:

```python
"""GET /api/components/{gw} — the per-player EP decomposition."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import COMPONENT_COLS, save_components
from gaffer.web.app import create_app


def _row(code: int, name: str, gw: int = 5, opp: str = "ARS",
         ep: float = 6.4, pen: float = 0.0) -> dict:
    row = {c: 0.0 for c in COMPONENT_COLS}
    row.update({"code": code, "element": code, "name": name,
                "position": "MID", "team_code": 14, "team_name": "Liverpool",
                "gw": gw, "opp_code": 3, "opp_name": opp, "was_home": 1.0,
                "kickoff_time": "2026-09-05T14:00:00Z",
                "p_play": 0.96, "p60": 0.9, "ep_minutes": 1.9,
                "ep_goals": 2.6, "ep_assists": 1.0, "ep_bonus": 0.6,
                "ep_cards": -0.05, "ep_pen_taker": pen, "ep": ep})
    return row


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def _write(tmp_path, rows):
    (tmp_path / "reports").mkdir(exist_ok=True)
    save_components(pd.DataFrame(rows)[COMPONENT_COLS], 5)


def test_components_without_a_run_is_a_friendly_404(client):
    response = client.get("/api/components/5")
    assert response.status_code == 404
    assert "gaffer advise" in response.json()["detail"]


def test_components_returns_one_entry_per_player(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah"), _row(101, "Wirtz", ep=5.2)])
    body = client.get("/api/components/5").json()
    assert body["gw"] == 5
    by_code = {p["code"]: p for p in body["players"]}
    assert by_code[100]["name"] == "Salah"
    assert by_code[100]["ep"] == 6.4
    assert by_code[101]["ep"] == 5.2


def test_a_double_gameweek_sums_its_fixtures_and_keeps_both(client, tmp_path):
    """The decomposition is per fixture; the headline number is the sum, and
    the page shows both because "why 11 points?" is answered by the two
    opponents as much as by the terms."""
    _write(tmp_path, [_row(100, "Salah", opp="ARS", ep=6.4),
                      _row(100, "Salah", opp="EVE", ep=4.6)])
    player = client.get("/api/components/5").json()["players"][0]
    assert player["ep"] == 11.0
    assert [f["opponent"] for f in player["fixtures"]] == ["ARS", "EVE"]


def test_each_fixture_carries_its_additive_terms(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah", pen=0.31)])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    labels = {c["label"]: c["points"] for c in fixture["components"]}
    assert labels["Goals"] == 2.6
    assert labels["Minutes"] == 1.9
    assert labels["Penalty duty"] == 0.31
    assert fixture["minutes"]["p_play"] == 0.96
    assert fixture["home"] is True


def test_a_zero_term_is_left_out_of_the_breakdown(client, tmp_path):
    """A row of zeroes is noise in a panel whose whole job is showing what
    moved. Penalty duty is the common case: 700 of 750 players have none."""
    _write(tmp_path, [_row(100, "Salah", pen=0.0)])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    assert all(c["label"] != "Penalty duty"
               for c in fixture["components"])


def test_components_can_be_filtered_to_the_codes_the_page_shows(client,
                                                                tmp_path):
    """This Week expands XI, bench, buys and sells — about twenty players out
    of a 750-row file."""
    _write(tmp_path, [_row(100, "Salah"), _row(101, "Wirtz"),
                      _row(102, "Nobody")])
    body = client.get("/api/components/5?codes=100,102").json()
    assert sorted(p["code"] for p in body["players"]) == [100, 102]


def test_an_unknown_code_in_the_filter_is_simply_absent(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah")])
    body = client.get("/api/components/5?codes=100,999").json()
    assert [p["code"] for p in body["players"]] == [100]
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_web_components.py -x -q
```

Expected: 404 with the SPA detail, or a missing-module import error.

- [ ] **Step 3: Add the schemas**

In `src/gaffer/web/schemas.py`, append after `ChipsWorkbench`:

```python
class ComponentFixture(BaseModel):
    """One player-fixture's additive terms.

    Deliberately shaped like :class:`FixtureExplain` (the explain modal's
    per-fixture row) without being it: this one is read from the saved
    components parquet with no model loading at all, and carries only what a
    why-panel renders.
    """

    gw: int
    opponent: str
    home: bool
    kickoff_time: str | None
    components: list[Component]
    minutes: MinutesOutput
    ep: float


class ComponentPlayer(BaseModel):
    code: int
    name: str
    position: str
    team_name: str
    ep: float
    """Summed over the player's fixtures in this gameweek."""
    fixtures: list[ComponentFixture]


class ComponentsBreakdown(BaseModel):
    gw: int
    players: list[ComponentPlayer]
```

- [ ] **Step 4: Write the router**

Create `src/gaffer/web/routers/components.py`:

```python
"""GET /api/components/{gw} — the saved EP decomposition (spec §4).

``run_advise`` has written ``reports/components_gw{N}.parquet`` since v3; this
serves it. No model is loaded and nothing is recomputed, which is what makes
it cheap enough for a row to expand on click.

The terms are the ones ``ep_breakdown`` produced, in the order a human reads
them (what he gets for turning up, then what he might do, then what might be
done to him), with zeroes dropped: a panel whose job is showing what moved
should not print nine zeroes to get to the one number that did.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from gaffer.artifacts import load_components
from gaffer.errors import GafferError
from gaffer.web.schemas import (Component, ComponentFixture, ComponentPlayer,
                                ComponentsBreakdown, MinutesOutput)

router = APIRouter(prefix="/api", tags=["components"])

TERMS: list[tuple[str, str]] = [
    ("ep_minutes", "Minutes"),
    ("ep_goals", "Goals"),
    ("ep_pen_taker", "Penalty duty"),
    ("ep_assists", "Assists"),
    ("ep_cs", "Clean sheet"),
    ("ep_gc", "Goals conceded"),
    ("ep_saves", "Saves"),
    ("ep_defcon", "Defensive contribution"),
    ("ep_bonus", "Bonus"),
    ("ep_pensave", "Penalty saves"),
    ("ep_cards", "Cards"),
    ("cal_delta", "Calibration"),
]
"""Component column -> the label the panel prints.

``ep_pen_taker`` sits directly under Goals because it *is* part of the goals
term — it was folded into ``e_goals`` before ``assemble_ep`` ever ran — and
showing it anywhere else would imply it is a separate line of the scoring
table, which it is not.
"""


def _num(value) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out


@router.get("/components/{gw}", response_model=ComponentsBreakdown)
def components(gw: int,
               codes: str | None = Query(
                   None, description="Comma-separated player codes; all "
                                     "players when omitted.")
               ) -> ComponentsBreakdown:
    try:
        frame = load_components(gw)
    except GafferError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if codes:
        wanted = {int(c) for c in codes.split(",") if c.strip().isdigit()}
        frame = frame[frame["code"].astype(int).isin(wanted)]

    players: list[ComponentPlayer] = []
    for code, rows in frame.groupby("code", sort=True):
        # mergesort because it is stable: a double gameweek's two fixtures
        # can share a kickoff time in a fixture file, and the order they were
        # written in is the order the opponents should read in.
        rows = rows.sort_values("kickoff_time", na_position="last",
                                kind="mergesort")
        fixtures = []
        for row in rows.itertuples():
            terms = [Component(label=label, points=round(_num(
                getattr(row, col, 0.0)), 2))
                for col, label in TERMS
                if round(_num(getattr(row, col, 0.0)), 2) != 0.0]
            fixtures.append(ComponentFixture(
                gw=int(row.gw), opponent=str(row.opp_name or ""),
                home=bool(_num(row.was_home)),
                kickoff_time=(None if pd.isna(row.kickoff_time)
                              else str(row.kickoff_time)),
                components=terms,
                minutes=MinutesOutput(p_play=round(_num(row.p_play), 3),
                                      p60=round(_num(row.p60), 3)),
                ep=round(_num(row.ep), 2)))
        head = rows.iloc[0]
        players.append(ComponentPlayer(
            code=int(code), name=str(head["name"]),
            position=str(head["position"]),
            team_name=str(head["team_name"] or ""),
            ep=round(float(sum(f.ep for f in fixtures)), 2),
            fixtures=fixtures))
    return ComponentsBreakdown(gw=int(gw), players=players)
```

- [ ] **Step 5: Register the router**

In `src/gaffer/web/app.py`, change the router import to:

```python
from gaffer.web.routers import (advice, chips, components, league, live, meta,
                                players, quality, whatif)
```

and add, after `app.include_router(chips.router)`:

```python
    app.include_router(components.router)
```

- [ ] **Step 6: Run, expect pass**

```bash
uv run pytest tests/test_web_components.py tests/test_web_app.py \
  tests/test_web_players.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/routers/components.py src/gaffer/web/schemas.py \
  src/gaffer/web/app.py tests/test_web_components.py
git commit -m "feat: GET /api/components/{gw} serves the saved EP breakdown" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 8 — `GET /api/advice/diff`

**Files:** `src/gaffer/web/routers/advice.py` (append after `latest`, `:99`), `src/gaffer/web/schemas.py` (append after `ComponentsBreakdown`), `tests/test_web_advice.py` (append).

**Why this one is a 200 and not a 404.** Spec §4: "ThisWeek shows a 'since last run' strip
when a previous run exists; nothing otherwise (**no error state**)." A first run of the week
is the ordinary case, not a missing artifact, so the endpoint answers
`{"available": false, ...}` and the strip hides. `/api/chips` and `/api/components/{gw}` keep
their 404s, because there the artifact really is missing and the user has something to run.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_advice.py`:

```python
# --- v6: the since-last-run diff -------------------------------------------

def _history(tmp_path, gw, stamp, **overrides):
    from gaffer.artifacts import append_advice_history

    payload = {"gw": gw, "expected_pts": 61.5,
               "captain": {"code": 100, "name": "Salah"},
               "buys": [], "sells": [], "chip_table": []}
    payload.update(overrides)
    return append_advice_history(payload, gw, now=stamp)


def test_advice_diff_without_a_previous_run_is_not_an_error(client, tmp_path):
    from datetime import datetime, timezone

    _advice_on_disk(tmp_path)
    _history(tmp_path, 5, datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc))
    body = client.get("/api/advice/diff").json()
    assert body["available"] is False
    assert body["gw"] == 5
    assert body["changed"] is False


def test_advice_diff_with_nothing_on_disk_at_all_is_not_an_error(client):
    body = client.get("/api/advice/diff").json()
    assert body["available"] is False


def test_advice_diff_compares_the_two_newest_runs_of_the_same_gw(client,
                                                                 tmp_path):
    from datetime import datetime, timezone

    _advice_on_disk(tmp_path)
    _history(tmp_path, 5, datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
             buys=[{"code": 200, "name": "Isak"}], expected_pts=61.5)
    _history(tmp_path, 5, datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc),
             buys=[{"code": 201, "name": "Wirtz"}], expected_pts=64.0,
             captain={"code": 101, "name": "Haaland"})
    body = client.get("/api/advice/diff").json()
    assert body["available"] is True
    assert body["changed"] is True
    assert [b["name"] for b in body["buys_added"]] == ["Wirtz"]
    assert [b["name"] for b in body["buys_dropped"]] == ["Isak"]
    assert body["captain_from"]["name"] == "Salah"
    assert body["captain_to"]["name"] == "Haaland"
    assert body["expected_pts_delta"] == 2.5
    assert body["previous_at"] < body["current_at"]


def test_advice_diff_ignores_runs_of_a_different_gameweek(client, tmp_path):
    """Last week's advice is not "the previous run" — the strip says what
    changed about *this* decision."""
    from datetime import datetime, timezone

    _advice_on_disk(tmp_path)
    _history(tmp_path, 4, datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc),
             expected_pts=50.0)
    _history(tmp_path, 5, datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc))
    body = client.get("/api/advice/diff").json()
    assert body["available"] is False


def test_advice_diff_can_be_asked_for_an_explicit_gameweek(client, tmp_path):
    from datetime import datetime, timezone

    _advice_on_disk(tmp_path)
    _history(tmp_path, 4, datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc),
             expected_pts=50.0)
    _history(tmp_path, 4, datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc),
             expected_pts=52.0)
    body = client.get("/api/advice/diff?gw=4").json()
    assert body["available"] is True
    assert body["expected_pts_delta"] == 2.0
```

If `tests/test_web_advice.py` has no `_advice_on_disk` helper and no module-level `client`
fixture, add them beside the existing fixtures — the file already writes a solve state and an
advice JSON for its other tests; reuse that helper under this name rather than writing a
second one.

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_web_advice.py -x -q
```

Expected: 404 from the SPA fallback on `/api/advice/diff`.

- [ ] **Step 3: Add the schema**

In `src/gaffer/web/schemas.py`, append after `ComponentsBreakdown`:

```python
class AdvicePlayer(BaseModel):
    code: int
    name: str


class AdviceDiff(BaseModel):
    """What changed between the two newest runs of one gameweek.

    ``available`` is false on a first run of the week — the ordinary case, not
    an error — and everything else is then empty, so the client renders
    nothing without having to special-case a status code.
    """

    gw: int
    available: bool
    changed: bool = False
    previous_at: str | None = None
    current_at: str | None = None
    buys_added: list[AdvicePlayer] = Field(default_factory=list)
    buys_dropped: list[AdvicePlayer] = Field(default_factory=list)
    sells_added: list[AdvicePlayer] = Field(default_factory=list)
    sells_dropped: list[AdvicePlayer] = Field(default_factory=list)
    captain_from: AdvicePlayer | None = None
    captain_to: AdvicePlayer | None = None
    chip_from: str | None = None
    chip_to: str | None = None
    expected_pts_delta: float = 0.0
```

- [ ] **Step 4: Write the endpoint**

In `src/gaffer/web/routers/advice.py`, extend the artifacts import:

```python
from gaffer.artifacts import (advice_history_files, data_warning,
                              diff_advice, ingested_through, latest_gw,
                              load_advice, load_solve_state, upcoming_gw)
```

extend the schemas import:

```python
from gaffer.web.schemas import (AdviceDiff, AdviceLatest, JobAccepted,
                                Staleness)
```

add `import json` to the top-level imports, and append after the `latest()` handler:

```python
@router.get("/diff", response_model=AdviceDiff)
def diff(gw: int | None = None) -> AdviceDiff:
    """The "since last run" strip: this run against the one before it.

    Same gameweek only. Re-running on Friday after the press conferences is
    the case this exists for, and comparing Friday's GW5 plan with last week's
    GW4 plan would answer a question nobody asked.

    Never an error. A first run of the week, a wiped ``reports/`` directory
    and a history file that will not parse all land in the same place: the
    strip is not shown, and the rest of This Week renders exactly as it did.
    """
    target = gw if gw is not None else latest_gw()
    if target is None:
        return AdviceDiff(gw=0, available=False)
    files = advice_history_files(int(target))
    if len(files) < 2:
        return AdviceDiff(gw=int(target), available=False)
    previous_path, current_path = files[-2], files[-1]
    try:
        previous = json.loads(previous_path.read_text())
        current = json.loads(current_path.read_text())
    except ValueError as exc:
        print(f"advice history unreadable, no diff shown: {exc}")
        return AdviceDiff(gw=int(target), available=False)
    out = diff_advice(previous, current)
    return AdviceDiff(
        gw=int(target), available=True,
        previous_at=previous_path.stem.partition("-")[2],
        current_at=current_path.stem.partition("-")[2], **out)
```

- [ ] **Step 5: Run, expect pass**

```bash
uv run pytest tests/test_web_advice.py tests/test_artifacts.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/web/routers/advice.py src/gaffer/web/schemas.py \
  tests/test_web_advice.py
git commit -m "feat: GET /api/advice/diff compares the two newest runs" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 9 — `GET /api/news/{gw}`

**Files:** `src/gaffer/web/routers/news.py` (new), `src/gaffer/web/schemas.py` (append after `AdviceDiff`), `src/gaffer/web/app.py` (import + register), `tests/test_web_news.py` (new).

Joins three artifacts that already exist by the time this runs: the shadow log
(`data/live/news_shadow.parquet`, written by `news_shadow.write_shadow`), the availability
snapshot (`reports/availability_gw{N}.parquet`, Task 5), and the bootstrap players snapshot
(`data/live/players.parquet`, written by `save_snapshots`).

**One thing the spec asks for that does not exist.** Spec §5 wants the injury feed's "raw
reason text" among the evidence. `availability_frame` does not carry it — its output is
`code, status, chance_of_playing, injury_type, expected_return_gw, p_start_hint, source,
fetched_at`, and the fetcher's own `news_status` is consumed by the precedence rules rather
than passed through. The closest real text is the **bootstrap's own `news` string**, which
`save_snapshots` already persists, so that is what the panel shows, labelled as the official
note. Recorded here rather than fixed: threading the feed's reason text through
`availability_frame` is a change to v5's precedence code and is not worth it for a caption.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_news.py`:

```python
"""GET /api/news/{gw} — what the news layer moved, and on what evidence."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import save_availability
from gaffer.data import store
from gaffer.news_shadow import SHADOW_COLS, SHADOW_PATH
from gaffer.web.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return TestClient(create_app(), raise_server_exceptions=False)


def _shadow(rows) -> None:
    store.save(pd.DataFrame(rows, columns=SHADOW_COLS), SHADOW_PATH)


def _players() -> None:
    store.save(pd.DataFrame([
        {"code": 1, "element": 11, "name": "Gibbs-White", "position": "MID",
         "team_id": 17, "team_code": 17, "now_cost": 70, "status": "d",
         "news": "Knock - 75% chance of playing", "chance_of_playing": 75.0,
         "selected_by_percent": 12.0, "form": 4.0, "points_per_game": 4.2,
         "ep_next": 4.0, "price_change_percent": 0.0,
         "price_change_calibrating": False, "penalties_order": 1.0,
         "direct_freekicks_order": 1.0,
         "corners_and_indirect_freekicks_order": 2.0},
        {"code": 2, "element": 12, "name": "Fit Lad", "position": "DEF",
         "team_id": 3, "team_code": 3, "now_cost": 45, "status": "a",
         "news": "", "chance_of_playing": None,
         "selected_by_percent": 3.0, "form": 2.0, "points_per_game": 3.0,
         "ep_next": 3.0, "price_change_percent": 0.0,
         "price_change_calibrating": False, "penalties_order": None,
         "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
    ]), "live/players.parquet")
    store.save(pd.DataFrame([{"code": 17, "team_id": 17,
                              "name": "Nott'm Forest", "short_name": "NFO"},
                             {"code": 3, "team_id": 3, "name": "Arsenal",
                              "short_name": "ARS"}]), "live/teams.parquet")


def test_news_with_no_shadow_log_is_an_empty_panel_not_an_error(client):
    body = client.get("/api/news/5").json()
    assert body["gw"] == 5 and body["moved"] == 0 and body["rows"] == []


def test_news_lists_only_the_players_the_layer_actually_moved(client,
                                                              tmp_path):
    _players()
    _shadow([
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
         "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
         "run_at": "2026-09-04T09:00:00"},
        {"season": "2026-27", "gw": 5, "code": 2, "p_play_news": 0.9,
         "p_play_flags": 0.9, "e_min_news": 80.0, "e_min_flags": 80.0,
         "run_at": "2026-09-04T09:00:00"},
    ])
    body = client.get("/api/news/5").json()
    assert body["moved"] == 1
    row = body["rows"][0]
    assert row["name"] == "Gibbs-White"
    assert row["team_name"] == "Nott'm Forest"
    assert row["p_play_news"] == 0.05 and row["p_play_flags"] == 0.75
    assert row["e_min_news"] == 4.0 and row["e_min_flags"] == 62.0


def test_news_carries_the_official_flag_as_evidence(client, tmp_path):
    _players()
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    row = client.get("/api/news/5").json()["rows"][0]
    assert row["status"] == "d"
    assert row["chance_of_playing"] == 75.0
    assert row["official_note"] == "Knock - 75% chance of playing"


def test_news_carries_the_availability_snapshot_as_evidence(client, tmp_path):
    """The Gibbs-White case reads: official 75% · FFS out · news 0%."""
    _players()
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    save_availability(pd.DataFrame([
        {"code": 1, "status": "d", "chance_of_playing": 75,
         "injury_type": "knock", "expected_return_gw": 6,
         "p_start_hint": 0.0, "source": "premierinjuries|lineups",
         "fetched_at": "2026-09-04T08:00:00Z"}]), 5)
    row = client.get("/api/news/5").json()["rows"][0]
    assert row["injury_type"] == "knock"
    assert row["expected_return_gw"] == 6
    assert row["p_start_hint"] == 0.0
    assert row["lineup_hint"] == "out"
    assert row["source"] == "premierinjuries|lineups"


def test_the_lineup_hint_is_named_not_left_as_a_probability(client, tmp_path):
    _players()
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.5,
              "p_play_flags": 0.9, "e_min_news": 40.0, "e_min_flags": 80.0,
              "run_at": "2026-09-04T09:00:00"}])
    for hint, want in ((1.0, "xi"), (0.5, "doubt"), (0.0, "out"),
                       (None, None)):
        save_availability(pd.DataFrame([
            {"code": 1, "status": "a", "chance_of_playing": None,
             "injury_type": None, "expected_return_gw": None,
             "p_start_hint": hint, "source": "lineups",
             "fetched_at": "x"}]), 5)
        assert client.get("/api/news/5").json()["rows"][0]["lineup_hint"] \
            == want


def test_only_the_latest_run_of_the_gameweek_is_read(client, tmp_path):
    """The log is appended every run. Two rows for one player are two
    readings of the same week, and the newest is the one that shipped."""
    _players()
    _shadow([
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
         "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
         "run_at": "2026-09-03T09:00:00"},
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.60,
         "p_play_flags": 0.75, "e_min_news": 50.0, "e_min_flags": 62.0,
         "run_at": "2026-09-04T09:00:00"},
    ])
    rows = client.get("/api/news/5").json()["rows"]
    assert len(rows) == 1 and rows[0]["p_play_news"] == 0.60


def test_rows_are_ordered_by_how_far_the_layer_moved_them(client, tmp_path):
    _players()
    _shadow([
        {"season": "2026-27", "gw": 5, "code": 2, "p_play_news": 0.80,
         "p_play_flags": 0.90, "e_min_news": 70.0, "e_min_flags": 80.0,
         "run_at": "2026-09-04T09:00:00"},
        {"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
         "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
         "run_at": "2026-09-04T09:00:00"},
    ])
    assert [r["code"] for r in client.get("/api/news/5").json()["rows"]] \
        == [1, 2]


def test_a_gameweek_with_no_shadow_rows_is_an_empty_panel(client, tmp_path):
    _players()
    _shadow([{"season": "2026-27", "gw": 4, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    assert client.get("/api/news/5").json()["moved"] == 0


def test_news_survives_a_missing_players_snapshot(client, tmp_path):
    """Names are a nicety; the numbers are the panel. A player the snapshot
    does not know is shown by his code."""
    _shadow([{"season": "2026-27", "gw": 5, "code": 1, "p_play_news": 0.05,
              "p_play_flags": 0.75, "e_min_news": 4.0, "e_min_flags": 62.0,
              "run_at": "2026-09-04T09:00:00"}])
    row = client.get("/api/news/5").json()["rows"][0]
    assert row["name"] == "1" and row["team_name"] == ""
```

- [ ] **Step 2: Run them, expect failure**

```bash
uv run pytest tests/test_web_news.py -x -q
```

Expected: 404 from the SPA fallback on `/api/news/5`.

- [ ] **Step 3: Add the schemas**

In `src/gaffer/web/schemas.py`, append after `AdviceDiff`:

```python
class NewsRow(BaseModel):
    """One player the news layer moved, with the evidence that moved him.

    Both sides of every number, because the panel's claim is a *difference*:
    "we think 5%, the official flag says 75%" is the sentence, and either half
    on its own is not.
    """

    code: int
    name: str
    team_name: str
    p_play_news: float
    p_play_flags: float
    e_min_news: float
    e_min_flags: float
    # Official flag, from the bootstrap snapshot.
    status: str | None = None
    chance_of_playing: float | None = None
    official_note: str | None = None
    # The availability frame this run predicted on.
    injury_type: str | None = None
    expected_return_gw: int | None = None
    p_start_hint: float | None = None
    lineup_hint: str | None = None
    """``xi`` / ``doubt`` / ``out`` — ``p_start_hint`` named, because a
    probability in a caption reads as a forecast rather than as a listing."""
    source: str | None = None
    fetched_at: str | None = None


class NewsPanelData(BaseModel):
    gw: int
    moved: int
    rows: list[NewsRow]
```

- [ ] **Step 4: Write the router**

Create `src/gaffer/web/routers/news.py`:

```python
"""GET /api/news/{gw} — what the news layer moved (spec §5).

Three artifacts, joined on the player code:

* ``data/live/news_shadow.parquet`` — both sides of every prediction, banked
  by ``news_shadow.write_shadow`` on every advise run. The newest ``run_at``
  per code wins: the log is appended, not overwritten, and Friday's reading is
  the one that shipped.
* ``reports/availability_gw{N}.parquet`` — the frame that run predicted on,
  which is the only record of *why* the layer moved him.
* ``data/live/players.parquet`` — names, clubs and the official flag.

Nothing here is an error. A missing shadow log, a missing snapshot and a
gameweek nobody has advised on all produce an empty panel, because "the news
moved nobody this week" and "we have not looked" render the same way and
neither is worth a red box on This Week.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter

from gaffer.artifacts import load_availability
from gaffer.data import store
from gaffer.news_shadow import SHADOW_PATH, load_shadow
from gaffer.web.schemas import NewsPanelData, NewsRow

router = APIRouter(prefix="/api", tags=["news"])

MOVED_EPSILON = 1e-9
"""Below this the two sides are the same number, not a disagreement."""

HINT_XI = 0.75
HINT_OUT = 0.25
"""Cuts turning ``p_start_hint`` back into the listing it came from.

The fetcher writes 1.0 for a named starter, 0.0 for a named absence and
something in between for a doubt; these are generous either side so a source
that hedges at 0.9 still reads as "in the XI".
"""


def _opt(value):
    """A pandas cell as a plain Python value, or ``None``."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _hint_name(value) -> str | None:
    hint = _opt(value)
    if hint is None:
        return None
    hint = float(hint)
    if hint >= HINT_XI:
        return "xi"
    return "out" if hint <= HINT_OUT else "doubt"


def _snapshot(rel: str) -> pd.DataFrame:
    if not store.exists(rel):
        return pd.DataFrame()
    try:
        return store.load(rel)
    except Exception as exc:  # noqa: BLE001 — a panel is not worth a 500
        print(f"news panel: {rel} unreadable ({exc})")
        return pd.DataFrame()


@router.get("/news/{gw}", response_model=NewsPanelData)
def news(gw: int) -> NewsPanelData:
    empty = NewsPanelData(gw=int(gw), moved=0, rows=[])
    if not store.exists(SHADOW_PATH):
        return empty
    shadow = load_shadow()
    if shadow is None or shadow.empty or "gw" not in shadow.columns:
        return empty
    rows = shadow[pd.to_numeric(shadow["gw"], errors="coerce") == int(gw)]
    if rows.empty:
        return empty
    # One reading per player: the newest run of this gameweek.
    rows = (rows.sort_values("run_at").groupby("code", as_index=False).last())
    moved = (rows["p_play_news"].astype(float)
             - rows["p_play_flags"].astype(float)).abs() > MOVED_EPSILON
    rows = rows[moved]
    if rows.empty:
        return empty

    players = _snapshot("live/players.parquet")
    teams = _snapshot("live/teams.parquet")
    name_of, team_of, status_of, chance_of, note_of = {}, {}, {}, {}, {}
    if not players.empty:
        team_name = (dict(zip(teams["code"], teams["name"]))
                     if not teams.empty else {})
        for row in players.itertuples():
            code = int(row.code)
            name_of[code] = str(row.name)
            team_of[code] = str(team_name.get(int(row.team_code), ""))
            status_of[code] = _opt(getattr(row, "status", None))
            chance_of[code] = _opt(getattr(row, "chance_of_playing", None))
            note_of[code] = _opt(getattr(row, "news", None))

    avail = load_availability(int(gw))
    evidence: dict[int, dict] = {}
    if avail is not None and not avail.empty:
        for row in avail.itertuples():
            evidence[int(row.code)] = {
                "injury_type": _opt(getattr(row, "injury_type", None)),
                "expected_return_gw": _opt(
                    getattr(row, "expected_return_gw", None)),
                "p_start_hint": _opt(getattr(row, "p_start_hint", None)),
                "source": _opt(getattr(row, "source", None)),
                "fetched_at": _opt(getattr(row, "fetched_at", None)),
            }

    out: list[NewsRow] = []
    for row in rows.itertuples():
        code = int(row.code)
        ev = evidence.get(code, {})
        note = note_of.get(code)
        out.append(NewsRow(
            code=code,
            name=name_of.get(code, str(code)),
            team_name=team_of.get(code, ""),
            p_play_news=round(float(row.p_play_news), 3),
            p_play_flags=round(float(row.p_play_flags), 3),
            e_min_news=round(float(row.e_min_news), 1),
            e_min_flags=round(float(row.e_min_flags), 1),
            status=(None if status_of.get(code) is None
                    else str(status_of[code])),
            chance_of_playing=(None if chance_of.get(code) is None
                               else float(chance_of[code])),
            official_note=(None if not note else str(note)),
            injury_type=(None if ev.get("injury_type") is None
                         else str(ev["injury_type"])),
            expected_return_gw=(None if ev.get("expected_return_gw") is None
                                else int(float(ev["expected_return_gw"]))),
            p_start_hint=(None if ev.get("p_start_hint") is None
                          else float(ev["p_start_hint"])),
            lineup_hint=_hint_name(ev.get("p_start_hint")),
            source=(None if ev.get("source") is None else str(ev["source"])),
            fetched_at=(None if ev.get("fetched_at") is None
                        else str(ev["fetched_at"]))))
    # Biggest disagreement first: the panel is read top-down and stopped at
    # the first name the manager recognises.
    out.sort(key=lambda r: abs(r.p_play_news - r.p_play_flags), reverse=True)
    return NewsPanelData(gw=int(gw), moved=len(out), rows=out)
```

- [ ] **Step 5: Register the router**

In `src/gaffer/web/app.py`, change the router import to:

```python
from gaffer.web.routers import (advice, chips, components, league, live, meta,
                                news, players, quality, whatif)
```

and add, after `app.include_router(components.router)`:

```python
    app.include_router(news.router)
```

- [ ] **Step 6: Run, expect pass**

```bash
uv run pytest tests/test_web_news.py tests/test_web_app.py \
  tests/test_news_shadow.py -q
```

Expected: all pass.

- [ ] **Step 7: Whole backend suite**

```bash
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/gaffer/web/routers/news.py src/gaffer/web/schemas.py \
  src/gaffer/web/app.py tests/test_web_news.py
git commit -m "feat: GET /api/news/{gw} joins the shadow log to its evidence" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 10 — U1: the Chip Workbench page

**Files:** `frontend/src/types.ts` (append), `frontend/src/pages/ChipWorkbench.tsx` (new), `frontend/src/pages/ChipWorkbench.test.tsx` (new), `frontend/src/App.tsx` (import + route), `frontend/src/components/Sidebar.tsx` (`PAGES`).

No new solver code: the interactive half posts to the existing `/api/whatif` job flow with
`chip` prefilled, exactly as `WhatIf.tsx` does, and renders the same `PlanDiffTable`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/ChipWorkbench.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChipWorkbench from './ChipWorkbench'

const { FakeApiError, apiGet, apiPost } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn(), apiPost: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const CHIPS = {
  gw: 5,
  chips: [
    { chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1, threshold: 8.0,
      play_now: true, note: null },
    { chip: 'bboost', gw: 6, gain: 2.0, per_week: 2.0, threshold: 4.0,
      play_now: false, note: null },
    { chip: 'freehit', gw: 7, gain: 5.0, per_week: 5.0, threshold: 4.0,
      play_now: true, note: 'conservative lower bound' },
  ],
  wildcard: {
    gain_over_horizon: 9.4,
    recommend: true,
    kept: [{ code: 100, name: 'Salah', position: 'MID', price: 13,
             ep: 6.4 }],
    dropped: [{ code: 101, name: 'Watkins', position: 'FWD', price: 9,
                ep: 4.1 }],
    added: [{ code: 102, name: 'Wirtz', position: 'MID', price: 8.5,
              ep: 5.2 }],
  },
}

const PLAYERS = [
  { code: 100, name: 'Salah', position: 'MID', price: 13.0, ep_next: 6.4 },
  { code: 102, name: 'Wirtz', position: 'MID', price: 8.5, ep_next: 5.2 },
]

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
    if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
    return Promise.resolve({})
  })
  apiPost.mockResolvedValue({ job_id: 'job-1' })
})

describe('ChipWorkbench', () => {
  it('shows every chip week against its own threshold', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /chips/i }))
      .toBeInTheDocument()
    // Two matches on purpose: the tab button and the table row.
    expect(screen.getAllByText(/wildcard/i).length).toBeGreaterThan(1)
    expect(screen.getByText('9.4')).toBeInTheDocument()
    expect(screen.getAllByLabelText(/against a bar of 8/i).length)
      .toBeGreaterThan(0)
  })

  it('marks the weeks worth playing now', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await screen.findAllByText(/wildcard/i)
    const rows = screen.getAllByRole('row')
    const playNow = rows.filter((r) => r.className.includes('changed'))
    expect(playNow).toHaveLength(2)
  })

  it('lays the wildcard squad out as kept, out and in', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /wildcard/i }))
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('Watkins')).toBeInTheDocument()
    expect(screen.getByText('Wirtz')).toBeInTheDocument()
    expect(screen.getByText(/9.4 expected points/)).toBeInTheDocument()
  })

  it('submits the constrained re-solve with the chip prefilled', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    const [path, body] = apiPost.mock.calls[0]
    expect(path).toBe('/api/whatif')
    expect((body as { chip: string }).chip).toBe('wc')
  })

  it('shows an empty state when no advice has been run', async () => {
    apiGet.mockRejectedValue(new FakeApiError(
      404, 'no advice on disk yet — run `gaffer advise` first'))
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    expect(await screen.findByText(/run `gaffer advise` first/))
      .toBeInTheDocument()
  })

  it('says so when there is no wildcard left to assess', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/chips')
        ? Promise.resolve({ ...CHIPS, wildcard: null })
        : Promise.resolve(PLAYERS)))
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /wildcard/i }))
    expect(screen.getByText(/no wildcard available/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it, expect failure**

```bash
cd frontend && npx vitest run src/pages/ChipWorkbench.test.tsx
```

Expected: `Failed to resolve import "./ChipWorkbench"`.

- [ ] **Step 3: Add the types**

Append to `frontend/src/types.ts`:

```ts
export interface ChipWorkbenchRow {
  chip: string
  gw: number
  gain: number
  per_week: number | null
  /** The θ bar for that chip in that week — the surplus the best remaining
   *  week is expected to offer. Null on advice written before the chip
   *  policy landed. */
  threshold: number | null
  play_now: boolean
  note: string | null
}

export interface ChipSquadPlayer {
  code: number
  name: string
  position: string
  price: number
  ep: number
}

export interface SquadDiff {
  gain_over_horizon: number
  recommend: boolean
  kept: ChipSquadPlayer[]
  dropped: ChipSquadPlayer[]
  added: ChipSquadPlayer[]
}

export interface ChipsWorkbench {
  gw: number
  chips: ChipWorkbenchRow[]
  wildcard: SquadDiff | null
}
```

- [ ] **Step 4: Write the page**

Create `frontend/src/pages/ChipWorkbench.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../api/client'
import { useJob } from '../api/useJob'
import ConstraintsPanel from '../components/ConstraintsPanel'
import PlanDiffTable from '../components/PlanDiffTable'
import PlayerName from '../components/PlayerName'
import type {
  ChipsWorkbench, ChipSquadPlayer, SquadDiff, WhatIfRequest, WhatIfResult,
} from '../types'

const LABELS: Record<string, string> = {
  wildcard: 'Wildcard',
  bboost: 'Bench Boost',
  freehit: 'Free Hit',
  '3xc': 'Triple Captain',
}

// A chip's gain is only ever read against its own threshold, so the bar is
// scaled to the threshold rather than to the largest gain on the table: a
// wildcard worth 9 against a bar of 8 and a bench boost worth 3 against a bar
// of 4 are two different answers, and a shared axis would draw them as the
// same one.
function GainBar({ gain, threshold }: { gain: number
                                        threshold: number | null }) {
  const bar = threshold ?? gain
  const width = bar > 0 ? Math.min(100, (gain / bar) * 100) : 0
  return (
    <span
      className="bar"
      style={{ display: 'inline-block', width: `${Math.max(2, width)}%`,
               background: gain >= bar ? 'var(--good)' : 'var(--line)' }}
      aria-label={`${gain} against a bar of ${bar}`}
    />
  )
}

function SquadColumn({ title, players }: { title: string
                                           players: ChipSquadPlayer[] }) {
  return (
    <div>
      <h3>{title} ({players.length})</h3>
      <ul>
        {players.map((p) => (
          <li key={p.code}>
            <PlayerName code={p.code} name={p.name} />{' '}
            <span className="muted">
              {p.position} · £{p.price}m · {p.ep} xPts
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function WildcardTab({ wildcard }: { wildcard: SquadDiff | null }) {
  if (wildcard === null) {
    return (
      <div className="card">
        <p className="muted">
          No wildcard available in this half of the season.
        </p>
      </div>
    )
  }
  return (
    <div className="card">
      <h2>Wildcard now</h2>
      <p className={wildcard.recommend ? 'good' : 'muted'}>
        Worth {wildcard.gain_over_horizon} expected points over the horizon —
        {wildcard.recommend ? ' worth playing.' : ' not worth it yet.'}
      </p>
      <div className="pitch-row" style={{ alignItems: 'flex-start' }}>
        <SquadColumn title="Kept" players={wildcard.kept} />
        <SquadColumn title="Out" players={wildcard.dropped} />
        <SquadColumn title="In" players={wildcard.added} />
      </div>
    </div>
  )
}

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'wc', horizon: null,
}

export default function ChipWorkbench() {
  const [data, setData] = useState<ChipsWorkbench | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'table' | 'wildcard'>('table')
  const [request, setRequest] = useState<WhatIfRequest>(EMPTY)
  const [invalid, setInvalid] = useState<string | null>(null)
  const job = useJob()

  useEffect(() => {
    apiGet<ChipsWorkbench>('/api/chips').then(setData).catch((e: Error) => {
      // 404 is the ordinary "nothing has been advised yet" state, and the
      // server's own sentence says what to run.
      if (e instanceof ApiError && e.status === 404) setEmpty(e.message)
      else setError(e.message)
    })
  }, [])

  const solve = async () => {
    setInvalid(null)
    job.reset()
    try {
      // Posted here rather than through useJob.start so a structured 422
      // renders next to the inputs, exactly as the What-If Lab does it.
      const { job_id } = await apiPost<{ job_id: string }>('/api/whatif',
        request)
      job.attach(job_id)
    } catch (e) {
      setInvalid(e instanceof ApiError && typeof e.detail === 'object'
        && e.detail !== null
        ? (e.detail as { error: string }).error
        : e instanceof Error ? e.message : String(e))
    }
  }

  if (error) return <p className="bad">{error}</p>
  if (empty) {
    return (
      <>
        <h2>Chips</h2>
        <div className="card"><p className="muted">{empty}</p></div>
      </>
    )
  }
  if (!data) return <p className="muted">Loading…</p>

  const busy = job.status === 'queued' || job.status === 'running'
  const diff = job.result as WhatIfResult | null

  return (
    <>
      <h2>Chips · GW{data.gw}</h2>
      <div className="chips">
        <button onClick={() => setTab('table')} disabled={tab === 'table'}>
          Chip table
        </button>
        <button onClick={() => setTab('wildcard')}
                disabled={tab === 'wildcard'}>
          Wildcard
        </button>
      </div>
      {tab === 'table' && (
        <div className="card">
          <h2>Gain against the bar</h2>
          {data.chips.length === 0 && (
            <p className="muted">No chips available.</p>
          )}
          <table>
            <thead>
              <tr>
                <th>Chip</th><th>GW</th><th>Gain</th><th>Bar</th>
                <th>Per week</th><th />
              </tr>
            </thead>
            <tbody>
              {data.chips.map((row) => (
                <tr key={`${row.chip}-${row.gw}`}
                    className={row.play_now ? 'changed' : undefined}>
                  <td>{LABELS[row.chip] ?? row.chip}</td>
                  <td>GW{row.gw}</td>
                  <td>{row.gain}</td>
                  <td>{row.threshold ?? '—'}</td>
                  <td>{row.per_week ?? '—'}</td>
                  <td>
                    <GainBar gain={row.gain} threshold={row.threshold} />
                    {row.note && (
                      <span className="muted"> {row.note}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab === 'wildcard' && <WildcardTab wildcard={data.wildcard} />}
      <div className="card">
        <h2>Try it</h2>
        <p className="muted">
          A front door onto the What-If Lab with the chip prefilled — the
          same solver, the same baseline.
        </p>
        <ConstraintsPanel value={request} onChange={setRequest} />
        <button onClick={solve} disabled={busy}>
          {busy ? 'Solving…' : 'Re-solve'}
        </button>
        {invalid && <p className="bad">{invalid}</p>}
        {job.status === 'error' && <p className="bad">{job.error}</p>}
      </div>
      {diff && <PlanDiffTable diff={diff} />}
    </>
  )
}
```

- [ ] **Step 5: Route and navigation**

In `frontend/src/App.tsx`, add the import (alphabetically, after
`import Health from './pages/Health'`):

```tsx
import ChipWorkbench from './pages/ChipWorkbench'
```

and the route, after the `/whatif` one:

```tsx
          <Route path="/chips" element={<ChipWorkbench />} />
```

In `frontend/src/components/Sidebar.tsx`, add to `PAGES` after the What-If Lab entry:

```tsx
  ['/chips', 'Chips'],
```

- [ ] **Step 6: Run, expect pass**

```bash
cd frontend && npx vitest run src/pages/ChipWorkbench.test.tsx src/App.test.tsx
```

Expected: all pass. `App.test.tsx` is in the list because it renders the sidebar and would
catch a broken route.

- [ ] **Step 7: Typecheck**

```bash
cd frontend && npx tsc -b
```

Expected: clean, no output.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ChipWorkbench.tsx \
  frontend/src/pages/ChipWorkbench.test.tsx frontend/src/App.tsx \
  frontend/src/components/Sidebar.tsx frontend/src/types.ts
git commit -m "feat: chip workbench page" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 11 — U2: the why-this-plan panel

**Files:** `frontend/src/types.ts` (append), `frontend/src/components/WhyPanel.tsx` (new), `frontend/src/components/WhyPanel.test.tsx` (new), `frontend/src/pages/ThisWeek.tsx` (import + mount), `frontend/src/pages/ThisWeek.test.tsx` (extend the mock).

One component, two parts, because they answer the same question from two sides: the
decomposition says *why this number*, the diff says *why a different number from Tuesday*.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/WhyPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WhyPanel from './WhyPanel'

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const COMPONENTS = {
  gw: 5,
  players: [
    {
      code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
      ep: 6.4,
      fixtures: [{
        gw: 5, opponent: 'ARS', home: true,
        kickoff_time: '2026-09-05T14:00:00Z',
        components: [
          { label: 'Minutes', points: 1.9 },
          { label: 'Goals', points: 2.6 },
          { label: 'Penalty duty', points: 0.31 },
        ],
        minutes: { p_play: 0.96, p60: 0.9 },
        ep: 6.4,
      }],
    },
  ],
}

const DIFF = {
  gw: 5, available: true, changed: true,
  previous_at: '2026-09-03T09:00:00+00:00',
  current_at: '2026-09-04T09:00:00+00:00',
  buys_added: [{ code: 201, name: 'Wirtz' }],
  buys_dropped: [{ code: 200, name: 'Isak' }],
  sells_added: [], sells_dropped: [],
  captain_from: { code: 100, name: 'Salah' },
  captain_to: { code: 101, name: 'Haaland' },
  chip_from: null, chip_to: 'bboost',
  expected_pts_delta: 2.5,
}

const CODES = [100]

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => (
    path.startsWith('/api/components')
      ? Promise.resolve(COMPONENTS)
      : Promise.resolve(DIFF)))
})

describe('WhyPanel', () => {
  it('asks only for the players the plan actually shows', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(apiGet).toHaveBeenCalledWith('/api/components/5?codes=100')
  })

  it('expands a player into his additive terms', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /salah/i }))
    expect(screen.getByText('Goals')).toBeInTheDocument()
    expect(screen.getByText('2.6')).toBeInTheDocument()
    expect(screen.getByText('Penalty duty')).toBeInTheDocument()
    expect(screen.getByText(/vs ARS/)).toBeInTheDocument()
  })

  it('shows what changed since the previous run', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/since last run/i)).toBeInTheDocument()
    expect(screen.getByText(/Wirtz/)).toBeInTheDocument()
    expect(screen.getByText(/Isak/)).toBeInTheDocument()
    expect(screen.getByText(/Salah → Haaland/)).toBeInTheDocument()
    expect(screen.getByText(/\+2.5/)).toBeInTheDocument()
  })

  it('shows no strip at all when there is no previous run', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components')
        ? Promise.resolve(COMPONENTS)
        : Promise.resolve({ gw: 5, available: false, changed: false })))
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText(/since last run/i)).not.toBeInTheDocument()
  })

  it('hides itself when no components file exists', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components')
        ? Promise.reject(new FakeApiError(404, 'no component breakdown'))
        : Promise.resolve({ gw: 5, available: false, changed: false })))
    const { container } = render(
      <MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})
```

- [ ] **Step 2: Run it, expect failure**

```bash
cd frontend && npx vitest run src/components/WhyPanel.test.tsx
```

Expected: `Failed to resolve import "./WhyPanel"`.

- [ ] **Step 3: Add the types**

Append to `frontend/src/types.ts`:

```ts
export interface ComponentFixture {
  gw: number
  opponent: string
  home: boolean
  kickoff_time: string | null
  components: Component[]
  minutes: { p_play: number; p60: number }
  ep: number
}

export interface ComponentPlayer {
  code: number
  name: string
  position: string
  team_name: string
  ep: number
  fixtures: ComponentFixture[]
}

export interface ComponentsBreakdown {
  gw: number
  players: ComponentPlayer[]
}

export interface AdvicePlayerRef {
  code: number
  name: string
}

export interface AdviceDiff {
  gw: number
  /** False on a first run of the week — the ordinary case, not an error. */
  available: boolean
  changed: boolean
  previous_at: string | null
  current_at: string | null
  buys_added: AdvicePlayerRef[]
  buys_dropped: AdvicePlayerRef[]
  sells_added: AdvicePlayerRef[]
  sells_dropped: AdvicePlayerRef[]
  captain_from: AdvicePlayerRef | null
  captain_to: AdvicePlayerRef | null
  chip_from: string | null
  chip_to: string | null
  expected_pts_delta: number
}
```

- [ ] **Step 4: Write the component**

Create `frontend/src/components/WhyPanel.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import type { AdviceDiff, ComponentPlayer, ComponentsBreakdown } from '../types'

function DiffStrip({ diff }: { diff: AdviceDiff }) {
  const bits: string[] = []
  if (diff.buys_added.length || diff.buys_dropped.length) {
    const inNames = diff.buys_added.map((p) => p.name).join(', ') || 'nobody'
    const outNames = diff.buys_dropped.map((p) => p.name).join(', ')
      || 'nobody'
    bits.push(`buying ${inNames} instead of ${outNames}`)
  }
  if (diff.sells_added.length || diff.sells_dropped.length) {
    const inNames = diff.sells_added.map((p) => p.name).join(', ') || 'nobody'
    const outNames = diff.sells_dropped.map((p) => p.name).join(', ')
      || 'nobody'
    bits.push(`selling ${inNames} instead of ${outNames}`)
  }
  if (diff.captain_to) {
    bits.push(`captain ${diff.captain_from?.name ?? 'none'} → `
      + `${diff.captain_to.name}`)
  }
  if (diff.chip_to) bits.push(`now recommending ${diff.chip_to}`)
  if (diff.chip_from && !diff.chip_to) {
    bits.push(`no longer recommending ${diff.chip_from}`)
  }
  const delta = diff.expected_pts_delta
  return (
    <div className="banner">
      <span>
        <strong>Since last run</strong>{' '}
        <span className="muted">({diff.previous_at})</span>:{' '}
        {bits.length === 0 ? 'the same plan' : bits.join('; ')}.{' '}
        <span className={delta >= 0 ? 'good' : 'bad'}>
          {delta >= 0 ? '+' : ''}{delta} xPts
        </span>
      </span>
    </div>
  )
}

function PlayerRow({ player }: { player: ComponentPlayer }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr>
        <td>
          <button className="player-link" onClick={() => setOpen(!open)}>
            {player.name}
          </button>
        </td>
        <td>{player.position}</td>
        <td>{player.team_name}</td>
        <td>{player.ep}</td>
      </tr>
      {open && player.fixtures.map((fixture, i) => (
        <tr key={`${player.code}-${i}`}>
          <td colSpan={4}>
            <p className="muted">
              {fixture.home ? 'vs' : 'at'} {fixture.opponent} — plays{' '}
              {Math.round(fixture.minutes.p_play * 100)}%, 60+{' '}
              {Math.round(fixture.minutes.p60 * 100)}% · {fixture.ep} xPts
            </p>
            <table>
              <tbody>
                {fixture.components.map((c) => (
                  <tr key={c.label}>
                    <td>{c.label}</td>
                    <td>{c.points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      ))}
    </>
  )
}

/**
 * Why this plan: the EP decomposition behind every player it names, and what
 * changed since the previous run of the same gameweek.
 *
 * Both halves fail quietly and separately. A missing components parquet hides
 * the whole panel (there is nothing to explain with); a first run of the week
 * hides only the strip, because "no previous run" is not a fault.
 */
export default function WhyPanel({ gw, codes }: { gw: number
                                                  codes: number[] }) {
  const [data, setData] = useState<ComponentsBreakdown | null>(null)
  const [diff, setDiff] = useState<AdviceDiff | null>(null)

  useEffect(() => {
    if (codes.length === 0) return
    const query = `?codes=${codes.join(',')}`
    apiGet<ComponentsBreakdown>(`/api/components/${gw}${query}`)
      .then(setData).catch(() => setData(null))
    apiGet<AdviceDiff>('/api/advice/diff').then(setDiff).catch(() => setDiff(null))
  }, [gw, codes.join(',')])

  if (!data || data.players.length === 0) return null

  return (
    <>
      {diff?.available && diff.changed && <DiffStrip diff={diff} />}
      <div className="card">
        <h2>Why this plan</h2>
        <p className="muted">
          Click a name for the terms that produced his expected points.
        </p>
        <table>
          <thead>
            <tr><th>Player</th><th>Pos</th><th>Club</th><th>xPts</th></tr>
          </thead>
          <tbody>
            {data.players.map((player) => (
              <PlayerRow key={player.code} player={player} />
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
```

- [ ] **Step 5: Mount it on This Week**

In `frontend/src/pages/ThisWeek.tsx`, add the import after the `StalenessBanner` one:

```tsx
import WhyPanel from '../components/WhyPanel'
```

and mount it immediately after the Transfers card's closing `</div>` and before the Chips
card, deriving the codes from the plan itself:

```tsx
      <WhyPanel
        gw={data.gw}
        codes={[...advice.xi, ...advice.bench, ...advice.buys,
                ...advice.sells].map((p) => p.code)}
      />
```

- [ ] **Step 6: Teach the This Week test about the new calls**

In `frontend/src/pages/ThisWeek.test.tsx`, the `apiGet` mock must answer the two new paths.
Wherever the file sets `apiGet.mockImplementation` (or `mockResolvedValue`), replace it with a
path-aware implementation that keeps the existing behaviour and adds:

```tsx
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/advice/diff')) {
      return Promise.resolve({ gw: 5, available: false, changed: false })
    }
    if (path.startsWith('/api/components')) {
      return Promise.resolve({ gw: 5, players: [] })
    }
    if (path.startsWith('/api/chips/plan')) return Promise.resolve(CHIPS)
    return Promise.resolve(ADVICE)
  })
```

using whatever the file already calls its advice and chip fixtures. An empty `players` list
makes `WhyPanel` render nothing, so every existing assertion in that file stands unchanged.

- [ ] **Step 7: Run, expect pass**

```bash
cd frontend && npx vitest run src/components/WhyPanel.test.tsx \
  src/pages/ThisWeek.test.tsx
```

Expected: all pass.

- [ ] **Step 8: Typecheck**

```bash
cd frontend && npx tsc -b
```

Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/WhyPanel.tsx \
  frontend/src/components/WhyPanel.test.tsx \
  frontend/src/pages/ThisWeek.tsx frontend/src/pages/ThisWeek.test.tsx \
  frontend/src/types.ts
git commit -m "feat: why-this-plan panel on This Week" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 12 — U3: the news transparency panel

**Files:** `frontend/src/types.ts` (append), `frontend/src/components/NewsPanel.tsx` (new), `frontend/src/components/NewsPanel.test.tsx` (new), `frontend/src/pages/ThisWeek.tsx` (import + mount), `frontend/src/pages/ThisWeek.test.tsx` (extend the mock).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/NewsPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NewsPanel from './NewsPanel'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const MOVED = {
  gw: 5,
  moved: 2,
  rows: [
    {
      code: 1, name: 'Gibbs-White', team_name: "Nott'm Forest",
      p_play_news: 0.0, p_play_flags: 0.75,
      e_min_news: 0.0, e_min_flags: 62.0,
      status: 'd', chance_of_playing: 75,
      official_note: 'Knock - 75% chance of playing',
      injury_type: 'knock', expected_return_gw: 6, p_start_hint: 0.0,
      lineup_hint: 'out', source: 'premierinjuries|lineups',
      fetched_at: '2026-09-04T08:00:00Z',
    },
    {
      code: 2, name: 'Fit Lad', team_name: 'Arsenal',
      p_play_news: 0.8, p_play_flags: 0.9,
      e_min_news: 70.0, e_min_flags: 80.0,
      status: 'a', chance_of_playing: null, official_note: null,
      injury_type: null, expected_return_gw: null, p_start_hint: 0.5,
      lineup_hint: 'doubt', source: 'lineups', fetched_at: 'x',
    },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(MOVED)
})

describe('NewsPanel', () => {
  it('counts the players the layer moved', async () => {
    render(<MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    expect(await screen.findByText(/news moved 2 players/i))
      .toBeInTheDocument()
  })

  it('shows both sides of each prediction', async () => {
    render(<MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await screen.findByText('Gibbs-White')
    expect(screen.getByText('0% / 75%')).toBeInTheDocument()
    expect(screen.getByText('0 / 62')).toBeInTheDocument()
  })

  it('spells out the sources that fired', async () => {
    render(<MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await screen.findByText('Gibbs-White')
    expect(screen.getByText(/official 75%/i)).toBeInTheDocument()
    expect(screen.getByText(/knock, back GW6/i)).toBeInTheDocument()
    expect(screen.getByText(/line-up: out/i)).toBeInTheDocument()
  })

  it('says nothing at all when the layer moved nobody', async () => {
    apiGet.mockResolvedValue({ gw: 5, moved: 0, rows: [] })
    const { container } = render(
      <MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })

  it('says nothing at all when the endpoint fails', async () => {
    apiGet.mockRejectedValue(new Error('nope'))
    const { container } = render(
      <MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})
```

- [ ] **Step 2: Run it, expect failure**

```bash
cd frontend && npx vitest run src/components/NewsPanel.test.tsx
```

Expected: `Failed to resolve import "./NewsPanel"`.

- [ ] **Step 3: Add the types**

Append to `frontend/src/types.ts`:

```ts
export interface NewsRow {
  code: number
  name: string
  team_name: string
  p_play_news: number
  p_play_flags: number
  e_min_news: number
  e_min_flags: number
  status: string | null
  chance_of_playing: number | null
  official_note: string | null
  injury_type: string | null
  expected_return_gw: number | null
  p_start_hint: number | null
  /** 'xi' | 'doubt' | 'out', or null when no line-up named him. */
  lineup_hint: string | null
  source: string | null
  fetched_at: string | null
}

export interface NewsPanelData {
  gw: number
  moved: number
  rows: NewsRow[]
}
```

- [ ] **Step 4: Write the component**

Create `frontend/src/components/NewsPanel.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import PlayerName from './PlayerName'
import type { NewsPanelData, NewsRow } from '../types'

const pct = (value: number) => `${Math.round(value * 100)}%`

// The evidence, in the order the layer weighed it: what the game says, what
// the injury feed says, what the predicted line-up says. Missing sources are
// left out rather than printed as "unknown" — a source that said nothing is
// not a source that said "no".
function evidence(row: NewsRow): string[] {
  const bits: string[] = []
  if (row.chance_of_playing !== null) {
    bits.push(`official ${row.chance_of_playing}%`)
  } else if (row.status) {
    bits.push(`official ${row.status}`)
  }
  if (row.injury_type) {
    bits.push(row.expected_return_gw !== null
      ? `${row.injury_type}, back GW${row.expected_return_gw}`
      : row.injury_type)
  }
  if (row.lineup_hint) bits.push(`line-up: ${row.lineup_hint}`)
  return bits
}

/**
 * What the news layer changed this week, and on whose word.
 *
 * Hidden whenever there is nothing to show — no shadow log, no artifacts, a
 * week where every source agreed with the official flags. "The news moved
 * nobody" and "we have not looked" render identically on purpose: neither is
 * something the manager has to act on.
 */
export default function NewsPanel({ gw }: { gw: number }) {
  const [data, setData] = useState<NewsPanelData | null>(null)

  useEffect(() => {
    apiGet<NewsPanelData>(`/api/news/${gw}`).then(setData)
      .catch(() => setData(null))
  }, [gw])

  if (!data || data.moved === 0) return null

  return (
    <div className="card">
      <h2>
        News moved {data.moved} player{data.moved === 1 ? '' : 's'}
      </h2>
      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>P(plays) news / flags</th>
            <th>xMins news / flags</th>
            <th>Why</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => (
            <tr key={row.code}>
              <td>
                <PlayerName code={row.code} name={row.name} />{' '}
                <span className="muted">{row.team_name}</span>
              </td>
              <td className={row.p_play_news < row.p_play_flags
                ? 'bad' : 'good'}>
                {pct(row.p_play_news)} / {pct(row.p_play_flags)}
              </td>
              <td>
                {Math.round(row.e_min_news)} / {Math.round(row.e_min_flags)}
              </td>
              <td className="muted">{evidence(row).join(' · ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 5: Mount it on This Week**

In `frontend/src/pages/ThisWeek.tsx`, add the import after the `PlayerName` one:

```tsx
import NewsPanel from '../components/NewsPanel'
```

and mount it directly above `<WhyPanel ... />`:

```tsx
      <NewsPanel gw={data.gw} />
```

- [ ] **Step 6: Extend the This Week mock again**

In `frontend/src/pages/ThisWeek.test.tsx`, add one more branch to the path-aware `apiGet`
implementation added in Task 11, above the fall-through:

```tsx
    if (path.startsWith('/api/news/')) {
      return Promise.resolve({ gw: 5, moved: 0, rows: [] })
    }
```

`moved: 0` hides the panel, so every existing assertion in the file still holds.

- [ ] **Step 7: Run, expect pass**

```bash
cd frontend && npx vitest run src/components/NewsPanel.test.tsx \
  src/pages/ThisWeek.test.tsx
```

Expected: all pass.

- [ ] **Step 8: Typecheck**

```bash
cd frontend && npx tsc -b
```

Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/NewsPanel.tsx \
  frontend/src/components/NewsPanel.test.tsx \
  frontend/src/pages/ThisWeek.tsx frontend/src/pages/ThisWeek.test.tsx \
  frontend/src/types.ts
git commit -m "feat: news transparency panel on This Week" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 13 — U4: the N2 scoreboard on Model Quality

**Files:** `src/gaffer/web/schemas.py` (append after `Decomposition`, and one field on `Quality`), `tests/test_web_quality.py` (append), `frontend/src/types.ts` (append), `frontend/src/pages/Quality.tsx` (new section), `frontend/src/pages/Quality.test.tsx` (extend the payload).

`gaffer evaluate --news-shadow` already writes the `news_shadow` key into
`reports/evaluation.json` (`evaluation.score_news_shadow`), and `/api/quality` already serves
that file — but the `Quality` response model does not declare the key, so FastAPI drops it on
the way out. The backend half of this task is that one declaration.

- [ ] **Step 1: Write the failing backend test**

Append to `tests/test_web_quality.py`:

```python
NEWS_SHADOW = {
    "run_at": "2026-09-12T00:00:00+00:00", "git_sha": "abc1234",
    "rows": 1400,
    "overall": {"brier_news": 0.0910, "brier_flags": 0.1020,
                "mae_news": 12.4, "mae_flags": 14.1, "rows": 1400},
    "by_gw": [
        {"gw": 3, "brier_news": 0.0950, "brier_flags": 0.1100,
         "mae_news": 12.9, "mae_flags": 14.8, "rows": 700,
         "cum_brier_news": 0.0950, "cum_brier_flags": 0.1100,
         "cum_mae_news": 12.9, "cum_mae_flags": 14.8},
        {"gw": 4, "brier_news": 0.0870, "brier_flags": 0.0940,
         "mae_news": 11.9, "mae_flags": 13.4, "rows": 700,
         "cum_brier_news": 0.0910, "cum_brier_flags": 0.1020,
         "cum_mae_news": 12.4, "cum_mae_flags": 14.1},
    ],
}


def test_quality_serves_the_news_shadow_scoreboard(client, tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "evaluation.json").write_text(
        json.dumps({**PAYLOAD, "news_shadow": NEWS_SHADOW}))
    body = client.get("/api/quality").json()
    assert body["news_shadow"]["rows"] == 1400
    assert body["news_shadow"]["overall"]["brier_news"] == 0.0910
    assert body["news_shadow"]["by_gw"][1]["gw"] == 4
    assert body["news_shadow"]["by_gw"][1]["cum_mae_news"] == 12.4


def test_quality_without_a_news_shadow_run_is_a_null(client, tmp_path):
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(PAYLOAD))
    assert client.get("/api/quality").json()["news_shadow"] is None


def test_a_news_shadow_with_nothing_scored_yet_still_serves(client, tmp_path):
    """Before the first gameweek completes the scorer writes rows: 0 and two
    empty containers. The page renders nothing from it, but the endpoint must
    not 500 on it."""
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(
        {**PAYLOAD, "news_shadow": {"run_at": "x", "git_sha": "y",
                                    "rows": 0, "overall": {}, "by_gw": []}}))
    assert client.get("/api/quality").json()["news_shadow"]["rows"] == 0
```

- [ ] **Step 2: Run it, expect failure**

```bash
uv run pytest tests/test_web_quality.py -x -q
```

Expected: `KeyError: 'news_shadow'` on the response body — FastAPI has filtered the key out.

- [ ] **Step 3: Declare the schema**

In `src/gaffer/web/schemas.py`, append after `Decomposition`:

```python
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
```

and add the field to `Quality`:

```python
class Quality(BaseModel):
    """Whichever modes have been run. Each is independent and may be absent."""

    current: CurrentEvaluation | None = None
    benchmark: BenchmarkEvaluation | None = None
    decomposition: Decomposition | None = None
    # v6: `gaffer evaluate --news-shadow` has written this key since v5, but
    # nothing declared it here, so it never reached the page.
    news_shadow: NewsShadow | None = None
```

- [ ] **Step 4: Run the backend half, expect pass**

```bash
uv run pytest tests/test_web_quality.py -q
```

Expected: all pass.

- [ ] **Step 5: Write the failing frontend test**

In `frontend/src/pages/Quality.test.tsx`, add to the `payload` object (after
`decomposition`):

```tsx
  news_shadow: {
    run_at: '2026-09-12T00:00:00+00:00', git_sha: 'abc1234', rows: 1400,
    overall: { brier_news: 0.091, brier_flags: 0.102, mae_news: 12.4,
               mae_flags: 14.1, rows: 1400 },
    by_gw: [
      { gw: 3, brier_news: 0.095, brier_flags: 0.11, mae_news: 12.9,
        mae_flags: 14.8, rows: 700, cum_brier_news: 0.095,
        cum_brier_flags: 0.11, cum_mae_news: 12.9, cum_mae_flags: 14.8 },
      { gw: 4, brier_news: 0.087, brier_flags: 0.094, mae_news: 11.9,
        mae_flags: 13.4, rows: 700, cum_brier_news: 0.091,
        cum_brier_flags: 0.102, cum_mae_news: 12.4, cum_mae_flags: 14.1 },
    ],
  },
```

and append these tests inside the `describe('Quality', ...)` block:

```tsx
  it('scores the news layer against the flags per gameweek', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /news layer/i }))
      .toBeInTheDocument()
    expect(screen.getByText('GW3')).toBeInTheDocument()
    expect(screen.getByText('GW4')).toBeInTheDocument()
    expect(screen.getByText('0.095')).toBeInTheDocument()
    expect(screen.getByText('0.11')).toBeInTheDocument()
  })

  it('states the verdict in a sentence', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText(/news is ahead on both/i))
      .toBeInTheDocument()
  })

  it('hides the section until a gameweek has been scored', async () => {
    apiGet.mockResolvedValue({
      ...payload,
      news_shadow: { run_at: 'x', git_sha: 'y', rows: 0, overall: {},
                     by_gw: [] },
    })
    render(<MemoryRouter><Quality /></MemoryRouter>)
    await screen.findByRole('heading', { name: /model quality/i })
    expect(screen.queryByRole('heading', { name: /news layer/i }))
      .not.toBeInTheDocument()
  })
```

- [ ] **Step 6: Run it, expect failure**

```bash
cd frontend && npx vitest run src/pages/Quality.test.tsx
```

Expected: `Unable to find a heading with the name /news layer/i`.

- [ ] **Step 7: Add the frontend types**

Append to `frontend/src/types.ts`:

```ts
export interface NewsShadowSummary {
  brier_news: number
  brier_flags: number
  mae_news: number
  mae_flags: number
  rows: number
}

export interface NewsShadowGw extends NewsShadowSummary {
  gw: number
  cum_brier_news: number
  cum_brier_flags: number
  cum_mae_news: number
  cum_mae_flags: number
}

export interface NewsShadowData {
  run_at: string
  git_sha: string
  /** Zero until a gameweek the log covers has actually been played. */
  rows: number
  overall: Partial<NewsShadowSummary>
  by_gw: NewsShadowGw[]
}
```

and add the field to `QualityData`:

```ts
export interface QualityData {
  current: CurrentEvaluation | null
  benchmark: BenchmarkEvaluation | null
  decomposition: DecompositionData | null
  news_shadow: NewsShadowData | null
}
```

- [ ] **Step 8: Render the section**

In `frontend/src/pages/Quality.tsx`, extend the type import:

```tsx
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, HeadMetrics,
  NewsShadowData, QualityData, StratifiedTable,
} from '../types'
```

add this component after `DecompositionSection`:

```tsx
// Lower is better for both metrics, so "ahead" means a smaller number. Said
// in a sentence as well as drawn, because a pair of bars two hundredths apart
// is not a verdict anyone should have to squint at.
function verdict(shadow: NewsShadowData): string {
  const o = shadow.overall
  if (o.brier_news === undefined || o.mae_news === undefined) {
    return 'Nothing scored yet.'
  }
  const brier = (o.brier_flags ?? 0) - o.brier_news
  const mae = (o.mae_flags ?? 0) - o.mae_news
  if (brier > 0 && mae > 0) {
    return `News is ahead on both: Brier ${brier.toFixed(4)} better, `
      + `minutes MAE ${mae.toFixed(2)} better, over ${shadow.rows} `
      + 'player-gameweeks.'
  }
  if (brier <= 0 && mae <= 0) {
    return `Flags are ahead on both, over ${shadow.rows} player-gameweeks — `
      + 'the news layer is not earning its place yet.'
  }
  return `Split: Brier ${brier > 0 ? 'news' : 'flags'}, minutes `
    + `${mae > 0 ? 'news' : 'flags'}, over ${shadow.rows} player-gameweeks.`
}

// Paired bars, per gameweek, both metrics. Each pair is scaled to its own
// row's larger value: the two Brier numbers differ in the third decimal and a
// shared axis across gameweeks would draw every pair as one flat line.
function PairedBar({ news, flags }: { news: number; flags: number }) {
  const top = Math.max(news, flags) || 1
  return (
    <span style={{ display: 'inline-flex', gap: 4, width: 120 }}>
      <span className="bar"
            style={{ width: `${(news / top) * 100}%`,
                     background: 'var(--pitch-300)' }}
            aria-label={`news ${news}`} />
      <span className="bar"
            style={{ width: `${(flags / top) * 100}%`,
                     background: 'var(--chalk-dim)' }}
            aria-label={`flags ${flags}`} />
    </span>
  )
}

function NewsShadowSection({ shadow }: { shadow: NewsShadowData }) {
  return (
    <div className="card">
      <h2>News layer</h2>
      <p className="muted">{verdict(shadow)}</p>
      <table>
        <thead>
          <tr>
            <th>GW</th>
            <th>Brier news</th><th>Brier flags</th><th />
            <th>Minutes MAE news</th><th>MAE flags</th><th />
            <th>Rows</th>
          </tr>
        </thead>
        <tbody>
          {shadow.by_gw.map((row) => (
            <tr key={row.gw}>
              <td>GW{row.gw}</td>
              <td>{row.brier_news}</td>
              <td>{row.brier_flags}</td>
              <td>
                <PairedBar news={row.brier_news} flags={row.brier_flags} />
              </td>
              <td>{row.mae_news}</td>
              <td>{row.mae_flags}</td>
              <td>
                <PairedBar news={row.mae_news} flags={row.mae_flags} />
              </td>
              <td>{row.rows}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

and mount it in the page body, after the decomposition line:

```tsx
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
```

- [ ] **Step 9: Run, expect pass**

```bash
cd frontend && npx vitest run src/pages/Quality.test.tsx
```

Expected: all pass.

- [ ] **Step 10: Typecheck**

```bash
cd frontend && npx tsc -b
```

Expected: clean.

- [ ] **Step 11: Commit**

```bash
git add src/gaffer/web/schemas.py tests/test_web_quality.py \
  frontend/src/pages/Quality.tsx frontend/src/pages/Quality.test.tsx \
  frontend/src/types.ts
git commit -m "feat: N2 news-layer scoreboard on the Quality page" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 14 — the v6 rails, the whole suite, and the hand-off

**Files:** `tests/test_v6_degradation.py` (append), plus verification only.

Nothing new is designed here. This task restates every rail in one place, runs both suites end
to end, builds the frontend, and hands the gates to the orchestrator.

- [ ] **Step 1: Write the consolidated rail tests**

Append to `tests/test_v6_degradation.py`:

```python
# --- rail 5: a cold clone serves every new endpoint without artifacts -------

def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.data import store
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_every_new_endpoint_answers_on_an_empty_disk(tmp_path, monkeypatch):
    """No reports/, no data/, no models/. The two artifact-backed endpoints
    say what to run; the two panel-backed ones say nothing at all. None of
    them 500s, and none of them is a blank page with a stack trace behind
    it."""
    client = _client(tmp_path, monkeypatch)

    chips = client.get("/api/chips")
    assert chips.status_code == 404
    assert "gaffer advise" in chips.json()["detail"]

    components = client.get("/api/components/5")
    assert components.status_code == 404
    assert "gaffer advise" in components.json()["detail"]

    diff = client.get("/api/advice/diff")
    assert diff.status_code == 200
    assert diff.json()["available"] is False

    news = client.get("/api/news/5")
    assert news.status_code == 200
    assert news.json() == {"gw": 5, "moved": 0, "rows": []}


def test_the_quality_page_still_answers_without_a_news_shadow_run(tmp_path,
                                                                  monkeypatch):
    import json

    client = _client(tmp_path, monkeypatch)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(
        {"current": None, "benchmark": None, "decomposition": None}))
    assert client.get("/api/quality").json()["news_shadow"] is None


# --- rail 6: the artifacts are instrumentation, never a blocker ------------

def test_the_v6_writers_all_swallow_their_own_failures(tmp_path,
                                                       monkeypatch):
    """Every artifact v6 added is for a UI panel. An advise run that died of
    one would be a strictly worse trade than a hidden panel."""
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(art, "REPORTS", tmp_path / "nope" / "\0" / "bad")
    monkeypatch.setattr(art, "ADVICE_HISTORY",
                        tmp_path / "nope" / "\0" / "bad" / "advice_history")
    assert art.save_availability(pd.DataFrame([{"code": 1, "status": "a",
                                                "chance_of_playing": None}]),
                                 5) is None
    assert art.append_advice_history({"gw": 5}, 5) is None
```

Add `import pandas as pd` to the top of the file if it is not already there (it is — rail 1
uses it).

- [ ] **Step 2: Run the new rails, expect pass**

```bash
uv run pytest tests/test_v6_degradation.py -q
```

Expected: all pass.

- [ ] **Step 3: The whole backend suite**

```bash
uv run pytest -q
```

Expected: all pass, no warnings that were not there before. Every protected suite is in this
run: `test_advise.py`, `test_odds.py`, `test_assemble.py`, `test_train.py`,
`test_v4c_degradation.py`, `test_v4d_degradation.py`, `test_v5_degradation.py`,
`test_v6_degradation.py`.

- [ ] **Step 4: The whole frontend suite**

```bash
cd frontend && npx vitest run
```

Expected: all pass.

- [ ] **Step 5: Typecheck and build**

```bash
cd frontend && npx tsc -b && npm run build
```

Expected: clean typecheck, then a Vite build writing into `src/gaffer/web/static/`. **Nothing
from that directory is staged** — `.gitignore` covers it and the wheel picks it up through
hatch's `artifacts` entry. The build exists to prove the four new pages and panels compile in
production mode.

- [ ] **Step 6: Confirm the tree is clean of anything that must not ship**

```bash
git status --porcelain
```

Expected: no `config.toml`, no `data/`, no `reports/`, no `models/`, no
`src/gaffer/web/static/`, and **no `src/gaffer/assets/scenario_noise.json`** — that asset is
the orchestrator's to produce.

- [ ] **Step 7: Commit the rails**

```bash
git add tests/test_v6_degradation.py
git commit -m "test: consolidate the v6 degradation rails" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

- [ ] **Step 8: Hand off the gates**

Report to the orchestrator, who runs all three:

- **Gate S1 (replay).** Run `gaffer calibrate-noise` — one benchmark fit plus a walk of
  2024-25; launch it under `caffeinate -i`. It writes
  `src/gaffer/assets/scenario_noise.json`, which is the one asset this cycle commits. Then
  replay 2025-26 twice with the same seeds, calibrated against heuristic, comparing total
  points, hits and transfer count. Calibrated ships if the total is not worse by more than 5
  points — noise shapes *robustness*, not EP, so parity is a pass and a win is a bonus. If S1
  fails, the asset still ships and `scenario_noise()` is switched off at the loader with the
  result recorded in spec §9. Also check the nailedness property directly off the written
  table: `sigma["0_3"] < sigma["0_0"]` and the same shape in the higher EP bins.
- **Gate P1 (live audit, not replay).** Taker orders do not exist historically, so there is no
  backtest. Run `gaffer advise` and collect the `set pieces:` lines it prints. Record in spec
  §9: how many nonzero terms ≥ 0.05 xPts, their max and mean. Sanity bounds: established
  first-choice takers (share history ≈ 1) must sit near zero, and the max must respect the
  +0.8 clamp.
- **UI smoke.** `gaffer advise` then `gaffer ui`, and walk all four pieces against real
  artifacts: the Chips page (table, wildcard tab, a constrained re-solve), This Week's why
  panel (expand an XI player, confirm Penalty duty appears for a taker and not for anyone
  else) and news panel, and the Quality page's News layer section once a gameweek has been
  scored with `gaffer evaluate --news-shadow`.

---

## Verification summary

| Level | Command | Expectation |
| --- | --- | --- |
| Per task | the `uv run pytest tests/test_*.py -q` line in that task | that task's tests pass, protected suites still green |
| Backend | `uv run pytest -q` | whole suite green (Tasks 2, 9, 14) |
| Frontend | `cd frontend && npx vitest run` | whole suite green (Task 14) |
| Types | `cd frontend && npx tsc -b` | clean (Tasks 10-14) |
| Build | `cd frontend && npm run build` | writes `src/gaffer/web/static/`, staged by nobody |
| Gates | orchestrator-run | S1 replay, P1 live audit, UI smoke |
