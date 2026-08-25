# Gaffer v4a Measure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the instruments that tell us whether a model change worked — re-derive bonus under the 2026/27 BPS rules, stand up a persistent `gaffer evaluate` harness with stratified and calibration-first metrics benchmarked against OpenFPL's published numbers, decompose replay loss into forecasting error vs optimization headroom with a perfect-foresight replay, and surface all of it on a Model Quality page.

**Architecture:** Four independent workstreams layered bottom-up. A new pure module `src/gaffer/features/bps.py` re-derives BPS and bonus from stored `cbi` counts and the published FPL tie rules, and `load_training_frame` applies it once so training and serving see the same adjusted history. A new `src/gaffer/evaluation.py` owns every metric (stratified RMSE/MAE by OpenFPL return category, log loss, reliability bins), the two evaluation protocols (last-10-slot holdout and a 2024-25 walk-forward benchmark), and the merge-on-write `reports/evaluation.json` artifact. `run_backtest` gains an `ep_source` switch whose `"oracle"` branch feeds actual points through the identical MILP pipeline; the `{model,oracle}×{h1,h3}` 2×2 lands in the same artifact. A read-only `GET /api/quality` router serves the artifact to a new `/quality` React page.

**Tech Stack:** Python 3.12, pandas, numpy, LightGBM, PuLP/HiGHS, FastAPI + pydantic, Typer, pytest (`uv run pytest`); React 18 + TypeScript, React Router, Vite, Vitest + Testing Library.

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `src/gaffer/features/bps.py` | Pure functions: `fixture_pair`, `adjust_bps`, `award_bonus`, `rederive_bonus`, `apply_new_bps`. No I/O, no config reads. |
| `src/gaffer/evaluation.py` | Return categories, stratified metrics, log loss, reliability bins, holdout/benchmark protocols, published reference constants, `reports/evaluation.json` read/merge-write, decomposition runner, CLI table formatter. |
| `src/gaffer/web/routers/quality.py` | `GET /api/quality` — parses the evaluation artifact, `GafferError` → 422 when it is missing. |
| `tests/test_bps.py` | Tie-rule table, adjustment formula, current-season passthrough, sums-to-6 property. |
| `tests/test_evaluation.py` | Metric unit tests, artifact merge, benchmark split/leak assertions, decomposition arithmetic, formatter. |
| `tests/test_web_quality.py` | Endpoint 200/422 contract. |
| `frontend/src/pages/Quality.tsx` | Model Quality page: stratified tables, reliability curves, decomposition card, empty state. |
| `frontend/src/pages/Quality.test.tsx` | Vitest coverage of the above (vi.hoisted mock pattern). |

**Modified:**

| Path | Change |
| --- | --- |
| `src/gaffer/models/train.py:97-133` | `load_training_frame` applies `apply_new_bps` before feature engineering. |
| `src/gaffer/models/train.py:233-261` | `train_all` drops the bonus recency floor when the frame carries re-derived columns. |
| `src/gaffer/models/components.py:111-131` | `BonusModel` docstring: why the recency floor survives re-derivation. |
| `src/gaffer/backtest.py:250-341` | `run_backtest(ep_source=...)` plus a new `oracle_ep` helper. |
| `src/gaffer/cli.py:149-157` | New `evaluate` command after `backtest`. |
| `src/gaffer/web/schemas.py:382` | Quality response models appended. |
| `src/gaffer/web/app.py:25,70-76` | Register the quality router. |
| `frontend/src/types.ts:311` | Mirrored quality types appended. |
| `frontend/src/App.tsx:1-35` | `/quality` route. |
| `frontend/src/components/Sidebar.tsx:3-12` | "Model Quality" sidebar entry. |
| `tests/test_train.py` | Bonus-floor bypass test. |
| `tests/test_train.py` | Floor-survives-re-derivation pin. |
| `tests/test_backtest.py` | `ep_source` regression + oracle dominance tests. |
| `tests/test_cli.py` | `evaluate` added to the command lists. |
| `frontend/src/App.test.tsx` | Sidebar list extended. |

---

## Task 1: `adjust_bps` — the 2026/27 BPS correction

**Files:**
- Create: `src/gaffer/features/bps.py`
- Test: `tests/test_bps.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bps.py`:

```python
import pandas as pd

from gaffer.features.bps import adjust_bps


def _rows(spec):
    """spec: list of (season_idx, bps, cbi)."""
    return pd.DataFrame([{"season_idx": s, "bps": b, "cbi": c,
                          "minutes": 90}
                         for s, b, c in spec])


def test_adjust_bps_applies_the_cbi_rebalance_to_old_seasons():
    # cbi 6 earned 3 BPS under the old per-two rule and earns 2 under the
    # new per-three rule: floor(6/3) - floor(6/2) = -1.
    out = adjust_bps(_rows([(0, 30.0, 6.0)]), current_idx=3)
    assert list(out) == [29.0]


def test_adjust_bps_delta_is_never_positive():
    frame = _rows([(0, 30.0, float(c)) for c in range(0, 25)])
    delta = adjust_bps(frame, current_idx=3) - frame["bps"]
    assert (delta <= 0).all()


def test_adjust_bps_leaves_current_season_rows_untouched():
    # Current-season rows are already scored under the new rules.
    out = adjust_bps(_rows([(3, 30.0, 12.0)]), current_idx=3)
    assert list(out) == [30.0]


def test_adjust_bps_treats_a_missing_cbi_count_as_no_adjustment():
    # cbi only exists from 2025-26 onwards; older rows cannot be corrected.
    out = adjust_bps(_rows([(0, 30.0, float("nan"))]), current_idx=3)
    assert list(out) == [30.0]


def test_adjust_bps_keeps_a_missing_bps_missing():
    out = adjust_bps(_rows([(0, float("nan"), 6.0)]), current_idx=3)
    assert out.isna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.features.bps'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/features/bps.py`:

```python
"""Re-derive BPS and bonus under the 2026/27 rules.

Stored history was scored under the old rules, so the bonus model's target
and its BPS features silently mean two different things either side of the
2026/27 boundary. These are pure functions over a player-match frame — no
I/O, no config reads — so the caller decides which season counts as
"current" and callers in training and serving can share one adjusted
history (no train/serve skew).

The 2026/27 change (premierleague.com/en/news/4679946) has two halves and we
can only reproduce one. Clearances/blocks/interceptions now earn 1 BPS per
*three* actions instead of per two, which the stored ``cbi`` count lets us
correct exactly. The -1 BPS for being tackled was removed, and no public
source carries a times-tackled column — so old-season BPS here slightly
*underestimates* new-rules BPS for players who are dispossessed often. That
is a known, deliberate approximation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def adjust_bps(df: pd.DataFrame, current_idx: int) -> pd.Series:
    """Per-row BPS restated under the 2026/27 CBI rule.

    ``bps + floor(cbi/3) - floor(cbi/2)`` — a non-positive delta — for rows
    older than ``current_idx``. Rows at or after ``current_idx`` were already
    scored under the new rules and come back untouched. A missing ``cbi``
    (every season before 2025/26) means there is nothing to correct, so the
    delta is zero rather than NaN; a missing ``bps`` stays missing.
    """
    bps = pd.to_numeric(df["bps"], errors="coerce")
    if "cbi" in df.columns:
        cbi = pd.to_numeric(df["cbi"], errors="coerce").fillna(0.0)
    else:
        cbi = pd.Series(0.0, index=df.index, dtype="float64")
    delta = np.floor(cbi / 3.0) - np.floor(cbi / 2.0)
    old = pd.to_numeric(df["season_idx"], errors="coerce") < current_idx
    return bps + delta.where(old, 0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bps.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/features/bps.py tests/test_bps.py
git commit -m "feat: adjust historical BPS for the 2026/27 CBI rule"
```

---

## Task 2: `rederive_bonus` — the FPL bonus tie rules

**Files:**
- Modify: `src/gaffer/features/bps.py` (append after `adjust_bps`)
- Test: `tests/test_bps.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bps.py`:

```python
from gaffer.features.bps import award_bonus, fixture_pair, rederive_bonus


def test_award_bonus_standard_three_two_one():
    assert award_bonus([30.0, 25.0, 20.0, 10.0]) == [3, 2, 1, 0]
    assert sum(award_bonus([30.0, 25.0, 20.0, 10.0])) == 6


def test_award_bonus_tie_for_first_among_two_is_three_three_one():
    assert award_bonus([30.0, 30.0, 25.0, 10.0]) == [3, 3, 1, 0]


def test_award_bonus_tie_for_first_among_three_awards_no_two_or_one():
    assert award_bonus([30.0, 30.0, 30.0, 25.0, 10.0]) == [3, 3, 3, 0, 0]


def test_award_bonus_tie_for_second_awards_two_two_and_no_one():
    assert award_bonus([30.0, 25.0, 25.0, 10.0]) == [3, 2, 2, 0]


def test_award_bonus_tie_for_third_gives_every_tied_player_one():
    assert award_bonus([30.0, 25.0, 20.0, 20.0, 10.0]) == [3, 2, 1, 1, 0]


def test_award_bonus_on_an_empty_fixture_awards_nothing():
    assert award_bonus([]) == []


def _fixture(bps_values, gw=1, season_idx=0, team=1, opp=2,
             kickoff="2025-08-16T14:00:00Z"):
    """One side of a match per row — both teams share the fixture key."""
    return pd.DataFrame([
        {"season_idx": season_idx, "gw": gw, "kickoff_time": kickoff,
         "team_code": team if i % 2 == 0 else opp,
         "opp_code": opp if i % 2 == 0 else team,
         "bps": v, "minutes": 90}
        for i, v in enumerate(bps_values)])


def test_fixture_pair_is_the_same_string_for_both_sides():
    pair = fixture_pair(_fixture([30.0, 25.0]))
    assert pair.iloc[0] == pair.iloc[1]


def test_rederive_bonus_awards_six_points_across_a_non_tied_fixture():
    out = rederive_bonus(_fixture([30.0, 25.0, 20.0, 10.0]))
    assert list(out) == [3.0, 2.0, 1.0, 0.0]
    assert out.sum() == 6.0


def test_rederive_bonus_scores_each_fixture_independently():
    one = _fixture([30.0, 25.0, 20.0], gw=1, team=1, opp=2)
    two = _fixture([9.0, 8.0, 7.0], gw=1, team=3, opp=4,
                   kickoff="2025-08-16T16:30:00Z")
    out = rederive_bonus(pd.concat([one, two], ignore_index=True))
    assert list(out) == [3.0, 2.0, 1.0, 3.0, 2.0, 1.0]


def test_rederive_bonus_splits_a_double_gameweek_by_kickoff():
    first = _fixture([30.0, 25.0, 20.0], gw=7,
                     kickoff="2025-10-01T19:00:00Z")
    second = _fixture([12.0, 11.0, 10.0], gw=7,
                      kickoff="2025-10-04T14:00:00Z")
    out = rederive_bonus(pd.concat([first, second], ignore_index=True))
    assert list(out) == [3.0, 2.0, 1.0, 3.0, 2.0, 1.0]


def test_rederive_bonus_ignores_players_who_did_not_appear():
    frame = _fixture([30.0, 25.0, 20.0, 0.0])
    frame.loc[3, "minutes"] = 0
    out = rederive_bonus(frame)
    assert list(out) == [3.0, 2.0, 1.0, 0.0]


def test_rederive_bonus_reads_an_explicit_adjusted_series():
    frame = _fixture([30.0, 25.0, 20.0])
    adjusted = pd.Series([10.0, 40.0, 20.0], index=frame.index)
    out = rederive_bonus(frame, adjusted)
    assert list(out) == [1.0, 3.0, 2.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bps.py -v`
Expected: FAIL — `ImportError: cannot import name 'award_bonus' from 'gaffer.features.bps'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/features/bps.py`:

```python
def fixture_pair(df: pd.DataFrame) -> pd.Series:
    """The unordered ``{team_code, opp_code}`` pair as a stable string.

    Both sides of one match have to land in the same bonus ranking, and they
    carry the pair the other way round, so the key sorts the two codes before
    joining them.
    """
    a = pd.to_numeric(df["team_code"], errors="coerce")
    b = pd.to_numeric(df["opp_code"], errors="coerce")
    lo = np.minimum(a, b)
    hi = np.maximum(a, b)
    return (pd.Series(lo, index=df.index).astype("string") + "-"
            + pd.Series(hi, index=df.index).astype("string"))


def award_bonus(values: list[float]) -> list[int]:
    """FPL bonus for one fixture's BPS values, published tie rules included.

    Ranked descending on distinct values:

    * tie for 1st among two -> ``3, 3`` then the next player takes 1 (the 2
      is skipped, because it would have gone to the second of the two);
    * tie for 1st among three or more -> every tied player takes 3 and
      nothing else is awarded;
    * tie for 2nd -> every tied player takes 2 and no 1 is awarded;
    * tie for 3rd -> every tied player takes 1.

    A fixture with no ties awards exactly 6 points; a tied one awards more,
    which is the real game's behaviour, not a bug.
    """
    out = [0] * len(values)
    distinct = sorted(set(values), reverse=True)
    groups = [[i for i, v in enumerate(values) if v == d] for d in distinct]
    if not groups:
        return out
    for i in groups[0]:
        out[i] = 3
    if len(groups[0]) >= 3:
        return out
    if len(groups[0]) == 2:
        if len(groups) > 1:
            for i in groups[1]:
                out[i] = 1
        return out
    if len(groups) > 1:
        for i in groups[1]:
            out[i] = 2
        if len(groups[1]) >= 2:
            return out
        if len(groups) > 2:
            for i in groups[2]:
                out[i] = 1
    return out


def rederive_bonus(df: pd.DataFrame,
                   bps: pd.Series | None = None) -> pd.Series:
    """Bonus points re-awarded per fixture from (adjusted) BPS.

    Fixtures are ``(season_idx, gw, kickoff_time, fixture_pair)``: the
    kickoff is what separates a double gameweek's two matches, which share
    every other part of the key. ``bps`` defaults to the frame's own column
    so the function is usable on unadjusted history too.

    Only appearances are ranked. A player on zero minutes carries a zero BPS
    that would otherwise tie with every other absentee and, in a fixture
    where nobody scored, could be handed bonus the real game never awarded.
    """
    values = (pd.to_numeric(df["bps"], errors="coerce") if bps is None
              else pd.to_numeric(bps, errors="coerce"))
    if "minutes" in df.columns:
        minutes = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    else:
        minutes = pd.Series(1.0, index=df.index, dtype="float64")
    out = pd.Series(0.0, index=df.index, dtype="float64")
    out[values.isna()] = float("nan")

    eligible = values.notna() & (minutes > 0)
    if not eligible.any():
        return out
    key = pd.Series(
        list(zip(df["season_idx"], df["gw"],
                 df["kickoff_time"].astype("string"), fixture_pair(df))),
        index=df.index)
    for _, idx in values[eligible].groupby(key[eligible]).groups.items():
        awards = award_bonus([float(v) for v in values.loc[idx]])
        out.loc[idx] = [float(a) for a in awards]
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bps.py -v`
Expected: PASS (17 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/features/bps.py tests/test_bps.py
git commit -m "feat: re-derive fixture bonus from adjusted BPS with FPL tie rules"
```

---

## Task 3: `apply_new_bps` wrapper

**Files:**
- Modify: `src/gaffer/features/bps.py` (append after `rederive_bonus`)
- Test: `tests/test_bps.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bps.py`:

```python
from gaffer.features.bps import apply_new_bps


def _two_fixture_frame():
    """One old-season fixture with CBI counts, one current-season fixture."""
    old = _fixture([30.0, 25.0, 20.0, 10.0], season_idx=0)
    old["cbi"] = [6.0, 0.0, 0.0, 0.0]
    old["bonus"] = [3.0, 2.0, 1.0, 0.0]
    new = _fixture([30.0, 25.0, 20.0, 10.0], season_idx=3, team=5, opp=6,
                   kickoff="2026-01-10T14:00:00Z")
    new["cbi"] = [12.0, 0.0, 0.0, 0.0]
    new["bonus"] = [3.0, 2.0, 1.0, 0.0]
    return pd.concat([old, new], ignore_index=True)


def test_apply_new_bps_keeps_the_old_columns_alongside_the_new():
    out = apply_new_bps(_two_fixture_frame(), current_idx=3)
    assert list(out["bps_old"]) == [30.0, 25.0, 20.0, 10.0,
                                    30.0, 25.0, 20.0, 10.0]
    assert list(out["bonus_old"]) == [3.0, 2.0, 1.0, 0.0,
                                      3.0, 2.0, 1.0, 0.0]


def test_apply_new_bps_restates_the_old_season_and_leaves_the_new_alone():
    out = apply_new_bps(_two_fixture_frame(), current_idx=3)
    # Old season: the 6-CBI leader drops a point of BPS but keeps the lead.
    assert list(out["bps"][:4]) == [29.0, 25.0, 20.0, 10.0]
    # Current season: untouched despite a fat CBI count.
    assert list(out["bps"][4:]) == [30.0, 25.0, 20.0, 10.0]
    assert list(out["bonus"]) == [3.0, 2.0, 1.0, 0.0, 3.0, 2.0, 1.0, 0.0]


def test_apply_new_bps_reorders_bonus_when_the_adjustment_changes_the_lead():
    frame = _fixture([30.0, 29.0, 20.0], season_idx=0)
    frame["cbi"] = [6.0, 0.0, 0.0]
    frame["bonus"] = [3.0, 2.0, 1.0]
    out = apply_new_bps(frame, current_idx=3)
    # 30 - 1 = 29 ties the runner-up: tie for first among two -> 3, 3, 1.
    assert list(out["bonus"]) == [3.0, 3.0, 1.0]


def test_apply_new_bps_preserves_every_other_column():
    frame = _two_fixture_frame()
    out = apply_new_bps(frame, current_idx=3)
    assert set(frame.columns) <= set(out.columns)
    assert len(out) == len(frame)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bps.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_new_bps' from 'gaffer.features.bps'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/features/bps.py`:

```python
def apply_new_bps(df: pd.DataFrame, current_idx: int) -> pd.DataFrame:
    """``bps`` and ``bonus`` restated under the 2026/27 rules.

    The originals are kept as ``bps_old`` / ``bonus_old`` — partly so a
    regression can be diffed against the stored truth, partly because their
    presence is how :func:`gaffer.models.train.train_all` knows the frame has
    been re-derived and the bonus model no longer needs its recency floor.

    The index is reset because the fixture grouping addresses rows by label:
    a frame concatenated without ``ignore_index`` would have duplicates.
    """
    out = df.reset_index(drop=True).copy()
    out["bps_old"] = out["bps"]
    out["bonus_old"] = out["bonus"]
    out["bps"] = adjust_bps(out, current_idx)
    out["bonus"] = rederive_bonus(out, out["bps"])
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bps.py -v`
Expected: PASS (21 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/features/bps.py tests/test_bps.py
git commit -m "feat: apply_new_bps wrapper keeping the old-rules columns"
```

---

## Task 4: Feed the adjusted history into `load_training_frame`

**Files:**
- Modify: `src/gaffer/models/train.py:97-133` (`load_training_frame`)
- Test: `tests/test_train.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_train.py`:

```python
# --- re-derived BPS reaches the feature builder ---------------------------

def _bps_history(year=2022, season_idx=0):
    """One season of a single two-team fixture per gameweek."""
    rows = []
    for gw in range(1, 4):
        for i in range(4):
            rows.append({
                "season": f"{year}-{year - 1999}",
                "season_idx": season_idx, "gw": gw, "code": 100 + i,
                "element": 1 + i, "name": f"P{i}",
                "position": ["GKP", "DEF", "MID", "FWD"][i],
                "team_code": 1 if i < 2 else 2,
                "opp_code": 2 if i < 2 else 1,
                "was_home": i < 2, "minutes": 90,
                "kickoff_time": f"{year}-08-{10 + gw:02d}T14:00:00Z",
                "bps": [30.0, 25.0, 20.0, 10.0][i],
                "bonus": [3.0, 2.0, 1.0, 0.0][i],
                "cbi": 6.0 if i == 0 else 0.0,
                "total_points": 5, "starts": 1, "value": 50,
            })
    return pd.DataFrame(rows)


def _bps_fixtures(year=2022, season_idx=0):
    rows = []
    for gw in range(1, 4):
        rows.append({
            "season_idx": season_idx, "gw": gw,
            "kickoff_time": f"{year}-08-{10 + gw:02d}T14:00:00Z",
            "home_code": 1, "away_code": 2,
            "home_goals": 1, "away_goals": 0})
    return pd.DataFrame(rows)


def _stub_store(monkeypatch, train_mod, history, fixtures,
                live=None, live_fixtures=None):
    frames = {"history/player_gw.parquet": history,
              "history/fixtures.parquet": fixtures,
              "live/player_gw.parquet": live,
              "live/fixtures.parquet": live_fixtures}
    monkeypatch.setattr(train_mod.store, "exists",
                        lambda rel: frames.get(rel) is not None)
    monkeypatch.setattr(train_mod.store, "load",
                        lambda rel: frames[rel].copy())


def test_load_training_frame_re_derives_bonus_under_the_new_bps_rules(
        monkeypatch):
    """The bonus target and every bps_r* / bonus_r* feature have to mean the
    same thing on both sides of the 2026/27 rule change, so every *stored*
    season is restated before feature engineering. Only the live season is
    already scored under the new rules and passes through untouched."""
    from gaffer.models import train as train_mod

    live = _bps_history(year=2023).drop(columns=["season_idx"])
    _stub_store(monkeypatch, train_mod,
                history=_bps_history(year=2022, season_idx=0),
                fixtures=_bps_fixtures(year=2022, season_idx=0),
                live=live,
                live_fixtures=_bps_fixtures(year=2023, season_idx=1))

    df, _tg, _elo = train_mod.load_training_frame()
    assert "bps_old" in df.columns and "bonus_old" in df.columns
    old = df[df["season_idx"] == 0]
    new = df[df["season_idx"] == 1]
    # The stored season is restated; the live season is not.
    assert set(old.loc[old["code"] == 100, "bps"]) == {29.0}
    assert set(new.loc[new["code"] == 100, "bps"]) == {30.0}
    # And the rolling features were built from the adjusted column.
    gw3 = old[(old["code"] == 100) & (old["gw"] == 3)]
    assert float(gw3["bps_r38"].iloc[0]) == 29.0


def test_load_training_frame_restates_every_stored_season_when_no_live(
        monkeypatch):
    """Before the first data_checked gameweek of a new season there is no
    live frame yet, and the newest *stored* season is still old-rules — it
    must not be mistaken for the current one and skipped."""
    from gaffer.models import train as train_mod

    _stub_store(monkeypatch, train_mod,
                history=_bps_history(year=2022, season_idx=0),
                fixtures=_bps_fixtures(year=2022, season_idx=0))

    df, _tg, _elo = train_mod.load_training_frame()
    assert set(df.loc[df["code"] == 100, "bps"]) == {29.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_train.py::test_load_training_frame_re_derives_bonus_under_the_new_bps_rules -v`
Expected: FAIL — `AssertionError: assert 'bps_old' in Index([...])`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/models/train.py`, add the import beside the other feature imports (currently lines 19-21):

```python
from gaffer.features.bps import apply_new_bps
from gaffer.features.engineer import (ROTATION_FEATURES, add_context,
                                      add_player_rolling, add_rotation,
                                      add_setpiece)
```

Then in `load_training_frame`, insert the re-derivation directly after the live-fixture concat and before the truncation block, so the whole body reads:

```python
    player_gw = store.load("history/player_gw.parquet")
    fixtures = store.load("history/fixtures.parquet")
    # Everything in the history store predates the 2026/27 rule change; the
    # live season is the only frame already scored under it. Fix the boundary
    # before the concat, so that in the pre-ingestion state (no live frame
    # yet, e.g. before the season's first data_checked gameweek) the newest
    # stored season is still restated rather than mistaken for the current
    # one.
    current_idx = int(player_gw["season_idx"].max()) + 1
    if store.exists("live/player_gw.parquet"):
        live = store.load("live/player_gw.parquet")
        live["season_idx"] = current_idx
        player_gw = pd.concat([player_gw, live], ignore_index=True)
    if store.exists("live/fixtures.parquet"):
        lfx = store.load("live/fixtures.parquet")
        fixtures = pd.concat([fixtures, lfx], ignore_index=True)
    # Restate BPS and bonus under the 2026/27 rules *before* anything reads
    # them, so the bonus target and the bps_r*/bonus_r* rolling features all
    # mean one thing. Re-deriving before truncation rather than after keeps
    # every fixture's ranking whole; truncation only ever drops entire
    # gameweeks, so the two orders agree anyway.
    player_gw = apply_new_bps(player_gw, current_idx=current_idx)
    if max_season_idx is not None:
```

Also extend the docstring's first line to say so:

```python
    """player_gw history (+ live season appended if present) with features,
    plus team_gw with features and final elo map. Optionally truncated for
    backtesting (strictly before max_season_idx/max_gw).

    ``bps``/``bonus`` arrive restated under the 2026/27 rules (see
    :mod:`gaffer.features.bps`); the stored values survive as
    ``bps_old``/``bonus_old``.
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_train.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/train.py tests/test_train.py
git commit -m "feat: re-derive BPS and bonus inside load_training_frame"
```

---

## Task 5: The bonus recency floor stays — and says why

The restatement is *partial*: `cbi` counts only exist from 2025-26, and no
public source records how often a player was tackled. Seasons before
2025-26 therefore keep an old-rules bonus target even after
`apply_new_bps`, and the recency floor is still what keeps those mixed
regimes out of the fit. What this cycle changes is the *data inside the
floor's window* — 2025-26's target corrected for the CBI per-3 change, and
the running season arriving new-rules — not the floor itself. This task
pins that decision so a later cleanup doesn't "simplify" the floor away.

**Files:**
- Modify: `src/gaffer/models/components.py:111-113` (`BonusModel` docstring only)
- Test: `tests/test_train.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_train.py`:

```python
def test_train_all_keeps_the_bonus_floor_even_on_a_re_derived_frame():
    """Restatement is partial — ``cbi`` counts only exist from 2025-26, so
    older seasons keep their old-rules bonus even after ``apply_new_bps``
    (its ``bps_old`` marker is present here). The recency floor is still
    what keeps those regimes out of the fit."""
    df = _player_frame(seasons=(0, 1))
    df["bps_old"] = df["bps_r5"] if "bps_r5" in df.columns else 0.0
    models = train_all(df, _team_frame(seasons=(0, 1)), save=False)
    assert models["bonus"].min_season_idx == bonus_season_floor(df)
```

If `bonus_season_floor` is not yet imported in `tests/test_train.py`, add it
to the existing `from gaffer.models.train import ...` line.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_train.py::test_train_all_keeps_the_bonus_floor_even_on_a_re_derived_frame -v`
Expected: PASS immediately if `train_all` already wires `bonus_season_floor`
unconditionally — in that case this is a pin, not a change; note it and move
on. If it FAILS, the failure means `train_all` special-cases re-derived
frames and that branch must be removed.

- [ ] **Step 3: Update the docstring**

Replace the `BonusModel` docstring in `src/gaffer/models/components.py`:

```python
class BonusModel:
    """E[bonus] per appearance, trained on the newest seasons only.

    The floor survives the 2026/27 re-derivation on purpose:
    :func:`gaffer.features.bps.apply_new_bps` can only restate seasons that
    carry ``cbi`` counts (2025-26 onward), and nothing records how often a
    player was tackled, so older seasons keep an old-rules bonus target.
    :func:`gaffer.models.train.bonus_season_floor` picks the newest window
    with enough rows to fit on — which is exactly the restated-or-new part
    of the history.
    """
```

Leave `__init__`, `fit` and `predict` exactly as they are.

- [ ] **Step 4: Run the full Python suite**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/models/components.py tests/test_train.py
git commit -m "docs+test: pin why the bonus recency floor survives re-derivation"
```

---

## Task 6: Return categories and stratified metrics

**Files:**
- Create: `src/gaffer/evaluation.py`
- Test: `tests/test_evaluation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evaluation.py`:

```python
import numpy as np
import pandas as pd

from gaffer.evaluation import (RETURN_CATEGORIES, categorize,
                               stratified_metrics)


def test_categorize_uses_openfpl_return_buckets():
    points = [0, 1, 2, 3, 4, 5, 12]
    assert list(categorize(points)) == ["zeros", "blanks", "blanks",
                                        "tickers", "tickers", "haulers",
                                        "haulers"]


def test_categorize_counts_a_negative_score_as_a_zero():
    # Own goal plus a red card can push a return below zero; it is still the
    # "nothing came of him" bucket.
    assert list(categorize([-2])) == ["zeros"]


def test_stratified_metrics_reports_every_category_plus_all():
    out = stratified_metrics([0.0, 1.0, 3.0, 6.0], [0, 1, 3, 6])
    assert list(out) == RETURN_CATEGORIES
    for cat in RETURN_CATEGORIES:
        assert out[cat]["rmse"] == 0.0 and out[cat]["mae"] == 0.0
    assert out["all"]["n"] == 4


def test_stratified_metrics_splits_error_by_the_actual_return():
    # Perfect on the zeros, two points out on the single hauler.
    out = stratified_metrics([0.0, 0.0, 3.0], [0, 0, 5])
    assert out["zeros"] == {"rmse": 0.0, "mae": 0.0, "n": 2}
    assert out["haulers"] == {"rmse": 2.0, "mae": 2.0, "n": 1}
    assert out["blanks"]["n"] == 0


def test_stratified_metrics_on_an_empty_category_is_zero_not_nan():
    out = stratified_metrics([0.0], [0])
    assert out["haulers"] == {"rmse": 0.0, "mae": 0.0, "n": 0}
    assert not np.isnan(out["haulers"]["rmse"])


def test_stratified_metrics_accepts_pandas_series():
    pred = pd.Series([2.0, 8.0], index=[7, 9])
    actual = pd.Series([1, 9], index=[3, 4])
    out = stratified_metrics(pred, actual)
    assert out["all"]["n"] == 2
    assert out["blanks"]["mae"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.evaluation'`

- [ ] **Step 3: Write minimal implementation**

Create `src/gaffer/evaluation.py`:

```python
"""The standing evaluation harness: how good is the model, on what yardstick.

Three things live here that nothing else in the codebase had. First, metrics
*stratified by what actually happened* — a single MAE is dominated by the
players who scored nothing, which every model gets right, so it flatters
everything equally and can never tell two models apart where it matters.
Second, calibration-first scoring of the probability heads: a p60 that is
right on average and wrong in every bin is worse than useless to a MILP that
multiplies by it. Third, one persistent artifact (``reports/evaluation.json``)
so a number from three weeks ago is still there to regress against.

Everything expensive is imported inside the function that needs it: the web
layer imports this module just to read the artifact and must not pay for
LightGBM to do it.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer.artifacts import REPORTS
from gaffer.errors import GafferError

RETURN_CATEGORIES = ["zeros", "blanks", "tickers", "haulers", "all"]
"""OpenFPL's return buckets, defined on *actual* points, plus the pooled cut.

Zeros (0), Blanks (1-2), Tickers (3-4), Haulers (5+). Keeping the exact
boundaries is what makes the published numbers in :data:`REFERENCES`
comparable at all.
"""


def categorize(points) -> np.ndarray:
    """Return bucket per row, from actual points."""
    a = np.asarray(points, dtype="float64")
    out = np.full(a.shape, "haulers", dtype=object)
    out[a <= 0] = "zeros"
    out[(a >= 1) & (a <= 2)] = "blanks"
    out[(a >= 3) & (a <= 4)] = "tickers"
    return out


def stratified_metrics(pred, actual) -> dict[str, dict[str, float]]:
    """RMSE and MAE per return category plus ``all``, with row counts.

    An empty category reports zeros rather than NaN: the artifact is JSON and
    a NaN there is neither valid JSON nor readable in the UI. ``n`` is the
    field that says whether the numbers mean anything.
    """
    p = np.asarray(pred, dtype="float64")
    a = np.asarray(actual, dtype="float64")
    cats = categorize(a)
    out: dict[str, dict[str, float]] = {}
    for name in RETURN_CATEGORIES:
        sel = np.ones(a.shape, dtype=bool) if name == "all" else cats == name
        n = int(sel.sum())
        err = p[sel] - a[sel]
        out[name] = {
            "rmse": round(float(np.sqrt((err ** 2).mean())), 3) if n else 0.0,
            "mae": round(float(np.abs(err).mean()), 3) if n else 0.0,
            "n": n,
        }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation.py
git commit -m "feat: stratified RMSE/MAE by OpenFPL return category"
```

---

## Task 7: Log loss and reliability bins

**Files:**
- Modify: `src/gaffer/evaluation.py` (append after `stratified_metrics`)
- Test: `tests/test_evaluation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluation.py`:

```python
from gaffer.evaluation import head_metrics, log_loss, reliability


def test_log_loss_of_a_perfect_confident_prediction_is_about_zero():
    assert log_loss([1.0, 0.0, 1.0], [1, 0, 1]) < 1e-6


def test_log_loss_punishes_a_confident_mistake():
    assert log_loss([0.99], [0]) > log_loss([0.5], [0])


def test_log_loss_of_a_coin_flip_is_ln_two():
    assert abs(log_loss([0.5, 0.5], [1, 0]) - np.log(2)) < 1e-9


def test_log_loss_ignores_rows_with_a_missing_prediction():
    assert abs(log_loss([0.5, float("nan")], [1, 0]) - np.log(2)) < 1e-9


def test_reliability_returns_at_most_ten_bins_with_counts():
    bins = reliability(np.linspace(0.0, 1.0, 200),
                       (np.linspace(0.0, 1.0, 200) > 0.5).astype(int))
    assert 1 <= len(bins) <= 10
    assert sum(b["n"] for b in bins) == 200
    assert set(bins[0]) == {"n", "pred", "obs"}


def test_reliability_of_a_calibrated_head_tracks_the_diagonal():
    rng = np.random.default_rng(4)
    p = rng.random(20000)
    y = (rng.random(20000) < p).astype(int)
    for b in reliability(p, y):
        assert abs(b["pred"] - b["obs"]) < 0.05


def test_reliability_of_an_overconfident_head_sits_below_the_diagonal():
    # Predicts 0.9 everywhere; only half of them happen.
    p = np.full(1000, 0.9)
    y = np.tile([1, 0], 500)
    bins = reliability(p, y)
    assert len(bins) == 1
    assert bins[0]["pred"] > bins[0]["obs"]


def test_reliability_skips_empty_bins():
    bins = reliability([0.05, 0.06], [0, 1])
    assert len(bins) == 1
    assert bins[0]["n"] == 2


def test_head_metrics_packs_log_loss_and_the_curve_together():
    out = head_metrics([0.5, 0.5], [1, 0])
    assert round(out["log_loss"], 4) == round(float(np.log(2)), 4)
    assert isinstance(out["reliability"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: FAIL — `ImportError: cannot import name 'head_metrics' from 'gaffer.evaluation'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/evaluation.py`:

```python
RELIABILITY_BINS = 10
LOG_LOSS_EPS = 1e-15
"""Clip for the log: a head that returns a hard 0 or 1 must not make the
whole metric infinite on a single wrong row."""


def _paired(pred, actual) -> tuple[np.ndarray, np.ndarray]:
    """Prediction/outcome arrays with the incomplete rows dropped.

    Positional, not index-aligned: every ``predict`` in this codebase returns
    one row per input row in input order, and pandas would happily align two
    frames with different indexes into nonsense.
    """
    p = np.asarray(pred, dtype="float64")
    y = np.asarray(actual, dtype="float64")
    ok = ~(np.isnan(p) | np.isnan(y))
    return p[ok], y[ok]


def log_loss(pred, actual) -> float:
    """Mean binary cross-entropy. NaN on an empty input, never an exception."""
    p, y = _paired(pred, actual)
    if p.size == 0:
        return float("nan")
    p = np.clip(p, LOG_LOSS_EPS, 1.0 - LOG_LOSS_EPS)
    return float(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)).mean())


def reliability(pred, actual, bins: int = RELIABILITY_BINS) -> list[dict]:
    """Reliability curve: per equal-width probability bin, ``n``, the mean
    prediction and the observed frequency.

    A head is calibrated when ``pred`` and ``obs`` match bin by bin, which is
    what the optimizer actually depends on — it multiplies by these numbers.
    Empty bins are omitted rather than emitted as zeros, so the curve never
    dives to the origin for a head whose predictions all sit in one place.
    """
    p, y = _paired(pred, actual)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, bins - 1)
    out = []
    for b in range(bins):
        sel = idx == b
        n = int(sel.sum())
        if n == 0:
            continue
        out.append({"n": n, "pred": round(float(p[sel].mean()), 4),
                    "obs": round(float(y[sel].mean()), 4)})
    return out


def head_metrics(pred, actual) -> dict:
    """One probability head's scoreline: log loss plus its reliability curve."""
    return {"log_loss": round(log_loss(pred, actual), 4),
            "reliability": reliability(pred, actual)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: PASS (15 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation.py
git commit -m "feat: log loss and reliability curves for the probability heads"
```

---

## Task 8: The `reports/evaluation.json` artifact

**Files:**
- Modify: `src/gaffer/evaluation.py` (append after `head_metrics`)
- Test: `tests/test_evaluation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluation.py`:

```python
import json

import pytest

from gaffer.errors import GafferError
from gaffer.evaluation import (EVALUATION_PATH, git_sha, load_evaluation,
                               run_at, save_evaluation)


def test_load_evaluation_without_the_artifact_says_how_to_make_one(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        load_evaluation()
    assert "gaffer evaluate" in str(exc.value)


def test_save_evaluation_writes_under_its_mode_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = save_evaluation("current", {"run_at": "now", "holdout_slots": 10})
    assert path == EVALUATION_PATH
    assert json.loads(path.read_text())["current"]["holdout_slots"] == 10


def test_save_evaluation_does_not_clobber_the_other_mode(tmp_path,
                                                         monkeypatch):
    """A benchmark run takes an hour; losing last night's current-mode
    numbers to it would make the artifact useless as a regression baseline."""
    monkeypatch.chdir(tmp_path)
    save_evaluation("current", {"holdout_slots": 10})
    save_evaluation("benchmark", {"test_season": "2024-25"})
    save_evaluation("decomposition", {"season": "2025-26"})
    stored = load_evaluation()
    assert stored["current"]["holdout_slots"] == 10
    assert stored["benchmark"]["test_season"] == "2024-25"
    assert stored["decomposition"]["season"] == "2025-26"


def test_save_evaluation_replaces_its_own_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_evaluation("current", {"holdout_slots": 10})
    save_evaluation("current", {"holdout_slots": 5})
    assert load_evaluation()["current"] == {"holdout_slots": 5}


def test_run_at_is_an_iso_utc_stamp():
    assert run_at().endswith("+00:00")


def test_git_sha_is_a_string_even_outside_a_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert isinstance(git_sha(), str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: FAIL — `ImportError: cannot import name 'EVALUATION_PATH' from 'gaffer.evaluation'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/evaluation.py`:

```python
EVALUATION_PATH = REPORTS / "evaluation.json"
"""One artifact, three independent keys.

``current`` and ``benchmark`` are different protocols and ``decomposition``
is a pair of replays that takes hours; each is written on its own and none of
them may take the others down with it, so writes merge rather than replace.
"""


def run_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_sha() -> str:
    """Short HEAD sha, or ``"unknown"``.

    Which commit produced a number is half of what makes it comparable to the
    next one, and a missing git is never a reason to fail an evaluation.
    """
    try:
        done = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def load_evaluation() -> dict:
    """The whole artifact. Missing file is a domain error, not a crash."""
    if not EVALUATION_PATH.exists():
        raise GafferError(
            "no evaluation on disk — run `gaffer evaluate` first")
    return json.loads(EVALUATION_PATH.read_text())


def save_evaluation(key: str, payload: dict) -> Path:
    """Merge ``payload`` in under ``key``, leaving the other keys alone."""
    stored: dict = {}
    if EVALUATION_PATH.exists():
        stored = json.loads(EVALUATION_PATH.read_text())
    stored[key] = payload
    REPORTS.mkdir(exist_ok=True)
    EVALUATION_PATH.write_text(json.dumps(stored, indent=1))
    return EVALUATION_PATH
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: PASS (21 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation.py
git commit -m "feat: reports/evaluation.json with per-mode merge-on-write"
```

---

## Task 9: current mode — the last-10-slot holdout

**Files:**
- Modify: `src/gaffer/evaluation.py` (append after `save_evaluation`)
- Test: `tests/test_evaluation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluation.py`:

```python
from gaffer.evaluation import baseline_metrics, before_mask, holdout_boundary


def _slot_frame(slots):
    """One row per (season_idx, gw) slot, plus a baseline column."""
    return pd.DataFrame([{"season_idx": s, "gw": g, "code": 1, "ep": 1.0,
                          "total_points_r5": 2.0}
                         for s, g in slots])


def test_holdout_boundary_is_the_tenth_slot_from_the_end():
    frame = _slot_frame([(0, g) for g in range(1, 26)])
    assert holdout_boundary(frame, holdout_slots=10) == (0, 16)


def test_holdout_boundary_crosses_the_season_line():
    frame = _slot_frame([(0, g) for g in range(1, 20)]
                        + [(1, g) for g in range(1, 6)])
    assert holdout_boundary(frame, holdout_slots=10) == (0, 15)


def test_holdout_boundary_refuses_a_frame_with_no_room_for_a_holdout():
    frame = _slot_frame([(0, g) for g in range(1, 6)])
    with pytest.raises(GafferError) as exc:
        holdout_boundary(frame, holdout_slots=10)
    assert "slots" in str(exc.value)


def test_before_mask_keeps_only_strictly_earlier_slots():
    frame = _slot_frame([(0, 14), (0, 15), (0, 16), (1, 1)])
    mask = before_mask(frame, 0, 16)
    assert list(mask) == [True, True, False, False]


def test_baseline_metrics_scores_a_rolling_column_on_the_same_yardstick():
    hold = pd.DataFrame({"code": [1, 2], "gw": [10, 10],
                         "total_points_r5": [2.0, 6.0]})
    truth = pd.DataFrame({"code": [1, 2], "gw": [10, 10],
                          "total_points": [2, 5], "minutes": [90, 90]})
    out = baseline_metrics(hold, "total_points_r5", truth)
    assert out["blanks"] == {"rmse": 0.0, "mae": 0.0, "n": 1}
    assert out["haulers"] == {"rmse": 1.0, "mae": 1.0, "n": 1}


def test_baseline_metrics_collapses_a_double_gameweek_to_one_row():
    """``ep_matrix`` sums a DGW's fixtures, so the truth frame has one row
    per player-gameweek; a per-fixture baseline would otherwise be scored
    twice and go unpenalised for it."""
    hold = pd.DataFrame({"code": [1, 1], "gw": [10, 10],
                         "total_points_r5": [3.0, 3.0]})
    truth = pd.DataFrame({"code": [1], "gw": [10], "total_points": [3],
                          "minutes": [180]})
    out = baseline_metrics(hold, "total_points_r5", truth)
    assert out["all"]["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: FAIL — `ImportError: cannot import name 'baseline_metrics' from 'gaffer.evaluation'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/evaluation.py`:

```python
HOLDOUT_SLOTS = 10
"""Gameweek slots held out in current mode.

The same ten as :data:`gaffer.models.train.CALIBRATION_HOLDOUT_GWS`, and for
the same reason: long enough to say something, short enough that the inner
model still sees nearly all of the newest season. Splitting on slots rather
than seasons also keeps components whose stats only exist in the newest
season (``tackles``/``cbi``) from losing every eligible training row.
"""

STARTER_MINUTES = 60
"""What counts as a start, matching ``evaluate_predictions``."""


def before_mask(frame: pd.DataFrame, season_idx: int, gw: int) -> pd.Series:
    """Rows strictly before the ``(season_idx, gw)`` slot."""
    return ((frame["season_idx"] < season_idx)
            | ((frame["season_idx"] == season_idx) & (frame["gw"] < gw)))


def holdout_boundary(df: pd.DataFrame,
                     holdout_slots: int = HOLDOUT_SLOTS) -> tuple[int, int]:
    """First held-out ``(season_idx, gw)`` slot, counting from the end."""
    slots = (df[["season_idx", "gw"]].drop_duplicates()
             .sort_values(["season_idx", "gw"]))
    if len(slots) <= holdout_slots:
        raise GafferError(
            f"only {len(slots)} gameweek slots in the frame — need more than "
            f"{holdout_slots} to hold one out")
    row = slots.iloc[-holdout_slots]
    return int(row["season_idx"]), int(row["gw"])


def baseline_metrics(hold: pd.DataFrame, col: str,
                     truth: pd.DataFrame) -> dict[str, dict[str, float]]:
    """A naive predictor scored on exactly the model's yardstick.

    ``col`` is a leakage-safe rolling column: ``total_points_r5`` is the
    last-five-match mean and ``total_points_r38`` is the season-to-date
    average, the two predictors a human would actually use. A double
    gameweek's two rows carry a near-identical rolling average, so taking the
    first is right where the truth frame has already summed the fixtures.
    """
    b = (hold[["code", "gw", col]].rename(columns={col: "ep"}).dropna()
         .groupby(["code", "gw"], as_index=False).agg(ep=("ep", "first")))
    j = b.merge(truth, on=["code", "gw"], how="inner")
    return stratified_metrics(j["ep"], j["total_points"])


def evaluate_current(holdout_slots: int = HOLDOUT_SLOTS) -> dict:
    """Score the model on the last ``holdout_slots`` gameweek slots.

    Components are refit on everything strictly before the boundary and the
    held-out slots are predicted through the same assemble/calibrate seam the
    weekly advice uses, so what is measured here is what a live run would
    have produced. The probability heads are read straight off the models
    rather than off the assembled points: ``p_cs`` in the simple component
    path is a constant, so the clean-sheet head has to be scored against the
    team model's own output on the held-out team-gameweeks.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    bs, bg = holdout_boundary(df, holdout_slots)
    df_before, tg_before = before_mask(df, bs, bg), before_mask(tg, bs, bg)
    models = train_all(df[df_before],
                       tg[tg_before].dropna(subset=["elo_diff"]), save=False)

    hold = df[~df_before].reset_index(drop=True)
    scoring = scoring_table(load_bootstrap_sample())
    comp = predict_components_simple(models, hold)
    ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                     models.get("calibration")))
    truth = hold.groupby(["code", "gw"], as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"))
    scored = ep.merge(truth, on=["code", "gw"], how="inner")
    starters = scored[scored["minutes"] >= STARTER_MINUTES]

    mp = models["minutes"].predict(hold)
    hold_tg = tg[~tg_before].dropna(subset=["elo_diff"]).reset_index(drop=True)
    tp = models["team"].predict(hold_tg)
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "holdout_slots": int(holdout_slots),
        "stratified": {
            "all": stratified_metrics(scored["ep"], scored["total_points"]),
            "starters": stratified_metrics(starters["ep"],
                                           starters["total_points"]),
        },
        "heads": {
            "p_play": head_metrics(mp["p_play"],
                                   (hold["minutes"] > 0).astype(float)),
            "p60": head_metrics(
                mp["p60"], (hold["minutes"] >= STARTER_MINUTES).astype(float)),
            "cs": head_metrics(tp["p_cs"], hold_tg["cs"].astype(float)),
        },
        "baselines": {
            "last5": baseline_metrics(hold, "total_points_r5", truth),
            "season_ppg": baseline_metrics(hold, "total_points_r38", truth),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: PASS (27 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation.py
git commit -m "feat: current-mode holdout evaluation with heads and baselines"
```

---

## Task 10: benchmark mode against the published numbers

**Files:**
- Modify: `src/gaffer/evaluation.py` (append after `evaluate_current`)
- Test: `tests/test_evaluation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluation.py`:

```python
from gaffer.evaluation import (BENCHMARK_CAVEAT, BENCHMARK_TEST_IDX,
                               BENCHMARK_TRAIN_MAX_IDX, REFERENCES,
                               benchmark_split)
from gaffer.features.engineer import add_player_rolling


def test_reference_constants_match_the_published_openfpl_table():
    """arXiv:2508.09992, Table 3. Pinned so a typo cannot silently make the
    model look better than the paper it is being compared to."""
    assert REFERENCES["openfpl"] == {
        "zeros": {"rmse": 0.818, "mae": 0.427},
        "blanks": {"rmse": 1.291, "mae": 0.749},
        "tickers": {"rmse": 1.517, "mae": 1.127},
        "haulers": {"rmse": 5.142, "mae": 4.317},
    }
    assert REFERENCES["fplreview"] == {
        "zeros": {"rmse": 0.689, "mae": 0.237},
        "blanks": {"rmse": 1.189, "mae": 0.597},
        "tickers": {"rmse": 1.594, "mae": 1.227},
        "haulers": {"rmse": 5.172, "mae": 4.381},
    }


def test_the_caveat_names_the_training_asymmetry():
    assert "four seasons" in BENCHMARK_CAVEAT
    assert "yardstick" in BENCHMARK_CAVEAT


def test_benchmark_split_trains_on_the_first_two_seasons_only():
    frame = pd.DataFrame({"season_idx": [0, 1, 2, 3], "gw": [1, 1, 1, 1]})
    train, test = benchmark_split(frame)
    assert int(train["season_idx"].max()) <= BENCHMARK_TRAIN_MAX_IDX
    assert set(test["season_idx"]) == {BENCHMARK_TEST_IDX}


def test_benchmark_test_rows_never_reach_the_training_set():
    frame = pd.DataFrame({"season_idx": [0, 1, 2, 3], "gw": [1, 1, 1, 1],
                          "marker": ["a", "b", "leak", "d"]})
    train, _ = benchmark_split(frame)
    assert "leak" not in set(train["marker"])


def test_benchmark_features_for_a_gameweek_use_only_strictly_prior_rows():
    """The walk-forward is not a re-engineering loop: the stored rolling
    columns already shift one match back, so GW g's features cannot contain
    GW g. Pin that, because the whole benchmark rests on it."""
    rows = []
    for gw in range(1, 6):
        rows.append({"code": 1, "season_idx": 2, "gw": gw,
                     "kickoff_time": f"2024-09-{gw:02d}T14:00:00Z",
                     "total_points": 50 if gw == 3 else 2, "minutes": 90})
    frame = add_player_rolling(pd.DataFrame(rows))
    _, test = benchmark_split(frame)
    at_gw3 = test[test["gw"] == 3].iloc[0]
    at_gw4 = test[test["gw"] == 4].iloc[0]
    assert float(at_gw3["total_points_r1"]) == 2.0     # the haul is invisible
    assert float(at_gw4["total_points_r1"]) == 50.0    # ... until next week
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: FAIL — `ImportError: cannot import name 'BENCHMARK_CAVEAT' from 'gaffer.evaluation'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/evaluation.py`:

```python
BENCHMARK_TRAIN_MAX_IDX = 1
"""Newest season the benchmark may train on: season_idx 1 = 2023-24."""

BENCHMARK_TEST_IDX = 2
BENCHMARK_TEST_SEASON = "2024-25"
"""The season OpenFPL published its test numbers on."""

REFERENCES = {
    # OpenFPL, arXiv:2508.09992 — per-return-category RMSE and MAE on
    # 2024-25, the same categories used here. FPL Review's numbers are the
    # ones published alongside them in that paper, not measured by us.
    "openfpl": {
        "zeros": {"rmse": 0.818, "mae": 0.427},
        "blanks": {"rmse": 1.291, "mae": 0.749},
        "tickers": {"rmse": 1.517, "mae": 1.127},
        "haulers": {"rmse": 5.142, "mae": 4.317},
    },
    "fplreview": {
        "zeros": {"rmse": 0.689, "mae": 0.237},
        "blanks": {"rmse": 1.189, "mae": 0.597},
        "tickers": {"rmse": 1.594, "mae": 1.227},
        "haulers": {"rmse": 5.172, "mae": 4.381},
    },
}

BENCHMARK_CAVEAT = (
    "Same test season (2024-25) and the same return categories, but OpenFPL "
    "trained on four seasons (2020-21 to 2023-24) against our two, and the "
    "feature sets differ. Treat these as a yardstick, not a controlled "
    "comparison.")


def benchmark_split(df: pd.DataFrame,
                    max_train_idx: int = BENCHMARK_TRAIN_MAX_IDX,
                    test_idx: int = BENCHMARK_TEST_IDX
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(train, test)`` for the published-numbers benchmark.

    A hard season split, not a slot split: the comparison is only meaningful
    if the model has seen nothing at all from the test season during fitting.
    The test frame's own features are still leakage-safe within the season —
    every rolling column shifts one match back — which is exactly the
    walk-forward the benchmark wants.
    """
    return (df[df["season_idx"] <= max_train_idx],
            df[df["season_idx"] == test_idx])


def evaluate_benchmark(max_train_idx: int = BENCHMARK_TRAIN_MAX_IDX,
                       test_idx: int = BENCHMARK_TEST_IDX) -> dict:
    """Train on the early seasons, predict every gameweek of the test season.

    One fit, then a gameweek at a time at a 1-gameweek horizon. Walking the
    gameweeks rather than predicting the season in one shot is not a
    formality: it is what keeps the loop honest about the horizon it claims,
    and it mirrors the replay's per-gameweek shape.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple, train_all)

    df, tg, _ = load_training_frame()
    train_df, test_df = benchmark_split(df, max_train_idx, test_idx)
    train_tg, _ = benchmark_split(tg, max_train_idx, test_idx)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)
    scoring = scoring_table(load_bootstrap_sample())

    parts = []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"),
            minutes=("minutes", "sum"))
        parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        print(f"benchmark gw{gw}: {len(parts[-1])} rows", flush=True)

    scored = pd.concat(parts, ignore_index=True)
    starters = scored[scored["minutes"] >= STARTER_MINUTES]
    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "test_season": BENCHMARK_TEST_SEASON,
        "stratified": {
            "all": stratified_metrics(scored["ep"], scored["total_points"]),
            "starters": stratified_metrics(starters["ep"],
                                           starters["total_points"]),
        },
        "references": REFERENCES,
        "caveat": BENCHMARK_CAVEAT,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: PASS (32 passed)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation.py
git commit -m "feat: benchmark mode against OpenFPL and FPL Review numbers"
```

---

## Task 11: `gaffer evaluate` command

**Files:**
- Modify: `src/gaffer/evaluation.py` (append `format_report`)
- Modify: `src/gaffer/cli.py:149-157` (add `evaluate` after `backtest`)
- Modify: `tests/test_cli.py:6-13,26-33` (command lists)
- Test: `tests/test_evaluation.py` (append), `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluation.py`:

```python
from gaffer.evaluation import format_report


def _current_payload():
    table = {c: {"rmse": 1.0, "mae": 0.5, "n": 10} for c in RETURN_CATEGORIES}
    return {"run_at": "2026-08-25T00:00:00+00:00", "git_sha": "abc1234",
            "holdout_slots": 10,
            "stratified": {"all": table, "starters": table},
            "heads": {"p_play": {"log_loss": 0.2771,
                                 "reliability": [{"n": 5, "pred": 0.5,
                                                  "obs": 0.4}]}},
            "baselines": {"last5": table, "season_ppg": table}}


def test_format_report_prints_every_category_and_the_baselines():
    text = format_report("current", _current_payload())
    for cat in RETURN_CATEGORIES:
        assert cat in text
    assert "baseline last5" in text
    assert "abc1234" in text
    assert "0.2771" in text


def test_format_report_prints_the_reference_columns_and_the_caveat():
    table = {c: {"rmse": 1.0, "mae": 0.5, "n": 10} for c in RETURN_CATEGORIES}
    text = format_report("benchmark", {
        "run_at": "x", "git_sha": "y", "test_season": "2024-25",
        "stratified": {"all": table}, "references": REFERENCES,
        "caveat": BENCHMARK_CAVEAT})
    assert "openfpl" in text and "fplreview" in text
    assert "5.142" in text
    assert "yardstick" in text


def test_format_report_names_the_two_derived_decomposition_numbers():
    text = format_report("decomposition", {
        "run_at": "x", "git_sha": "y", "season": "2025-26", "start_gw": 5,
        "cells": {"model_h1": {"total": 1800, "per_gw": 52.9, "hits": 4},
                  "model_h3": {"total": 1850, "per_gw": 54.4, "hits": 3},
                  "oracle_h1": {"total": 2600, "per_gw": 76.5, "hits": 2},
                  "oracle_h3": {"total": 2700, "per_gw": 79.4, "hits": 1}},
        "forecast_gap_h3": 850.0, "planning_ceiling": 100.0})
    assert "forecast_gap_h3" in text and "850" in text
    assert "planning_ceiling" in text and "100" in text
    assert "oracle_h3" in text
```

Append to `tests/test_cli.py`:

```python
def test_evaluate_writes_the_artifact_and_prints_the_table(tmp_path,
                                                           monkeypatch):
    import json

    monkeypatch.chdir(tmp_path)
    payload = {"run_at": "now", "git_sha": "abc1234", "holdout_slots": 10,
               "stratified": {"all": {c: {"rmse": 1.0, "mae": 0.5, "n": 3}
                                      for c in ["zeros", "blanks", "tickers",
                                                "haulers", "all"]}},
               "heads": {}, "baselines": {}}
    monkeypatch.setattr("gaffer.evaluation.evaluate_current",
                        lambda *a, **k: payload)
    result = runner.invoke(app, ["evaluate"])
    assert result.exit_code == 0, result.output
    stored = json.loads((tmp_path / "reports" / "evaluation.json").read_text())
    assert stored["current"]["git_sha"] == "abc1234"
    assert "haulers" in result.output


def test_evaluate_rejects_an_unknown_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["evaluate", "--mode", "nonsense"])
    assert result.exit_code != 0
    assert "nonsense" in result.output
```

And extend the two command lists in `tests/test_cli.py` (lines 6-13 and 26-33) to include `"evaluate"`:

```python
    for cmd in ["advise", "refresh", "train", "prices", "league", "live",
                "backtest", "evaluate", "build-history", "ui"]:
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py tests/test_evaluation.py -v`
Expected: FAIL — `assert 'evaluate' in result.output` (the command does not exist) and `ImportError: cannot import name 'format_report'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/evaluation.py`:

```python
def format_report(key: str, payload: dict) -> str:
    """The artifact as a table a human can read in a terminal.

    The JSON is the record; this is what makes a run worth watching while it
    happens. The caveat is printed as well as stored on purpose — a bare
    comparison to somebody else's published numbers invites exactly the wrong
    conclusion.
    """
    lines = [f"=== {key} (run_at {payload.get('run_at')}, "
             f"sha {payload.get('git_sha')}) ==="]
    if key == "decomposition":
        lines.append(f"{payload.get('season')} from GW{payload.get('start_gw')}")
        for name, cell in payload["cells"].items():
            lines.append(f"{name:10s} total {cell['total']:5d}  "
                         f"per_gw {cell['per_gw']:6.2f}  "
                         f"hits {cell['hits']}")
        lines.append(f"forecast_gap_h3   {payload['forecast_gap_h3']:8.1f}  "
                     "points better forecasting could still win")
        lines.append(f"planning_ceiling  {payload['planning_ceiling']:8.1f}  "
                     "most multi-week planning can ever be worth")
        return "\n".join(lines)

    for cut, table in payload.get("stratified", {}).items():
        lines.append(f"-- {cut}")
        for cat in RETURN_CATEGORIES:
            m = table[cat]
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}  n {m['n']}")
    for name, table in payload.get("baselines", {}).items():
        lines.append(f"-- baseline {name}")
        for cat in RETURN_CATEGORIES:
            m = table[cat]
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}  n {m['n']}")
    for source, table in payload.get("references", {}).items():
        lines.append(f"-- {source} (published)")
        for cat, m in table.items():
            lines.append(f"   {cat:9s} rmse {m['rmse']:7.3f}  "
                         f"mae {m['mae']:7.3f}")
    for head, m in payload.get("heads", {}).items():
        lines.append(f"-- head {head}: log loss {m['log_loss']:.4f}, "
                     f"{len(m['reliability'])} reliability bins")
        for b in m["reliability"]:
            lines.append(f"   pred {b['pred']:.3f}  obs {b['obs']:.3f}  "
                         f"n {b['n']}")
    if payload.get("caveat"):
        lines.append(f"CAVEAT: {payload['caveat']}")
    return "\n".join(lines)
```

Add the command to `src/gaffer/cli.py`, directly after `backtest`:

```python
@app.command()
def evaluate(mode: str = typer.Option(
                 "current", help="current (last-10-slot holdout) or "
                                 "benchmark (train <=2023-24, test 2024-25)."),
             decompose: bool = typer.Option(
                 False, "--decompose",
                 help="Run the {model,oracle} x {h1,h3} replay 2x2 instead. "
                      "Hours: launch it under `caffeinate -i`."),
             season: str = "2025-26", start_gw: int = 5):
    """Score the model and write reports/evaluation.json."""
    from gaffer.evaluation import (evaluate_benchmark, evaluate_current,
                                   format_report, run_decomposition,
                                   save_evaluation)

    if decompose:
        key, payload = "decomposition", run_decomposition(season=season,
                                                          start_gw=start_gw)
    elif mode == "benchmark":
        key, payload = "benchmark", evaluate_benchmark()
    elif mode == "current":
        key, payload = "current", evaluate_current()
    else:
        typer.echo(f"unknown mode: {mode} (expected current or benchmark)")
        raise typer.Exit(1)
    path = save_evaluation(key, payload)
    typer.echo(format_report(key, payload))
    typer.echo(f"Wrote {path}")
```

The command's import list names `run_decomposition`, which Task 13 implements. Land a stub for it now — append to `src/gaffer/evaluation.py` — so the command body is written exactly once:

```python
def run_decomposition(season: str = "2025-26", start_gw: int = 5) -> dict:
    # Replaced in full by the decomposition task; the CLI imports it eagerly
    # so it has to exist before --decompose does anything.
    raise GafferError("decomposition is not implemented yet")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py tests/test_evaluation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py src/gaffer/cli.py tests/test_cli.py tests/test_evaluation.py
git commit -m "feat: gaffer evaluate command writing reports/evaluation.json"
```

---

## Task 12: Oracle EP source in the replay

**Files:**
- Modify: `src/gaffer/backtest.py:242-341` (add `oracle_ep`, extend `run_backtest`)
- Test: `tests/test_backtest.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest.py`:

```python
# --- perfect-foresight ("oracle") EP -------------------------------------

def test_oracle_ep_is_the_actual_points_per_player_gameweek():
    rows = _season_rows([1, 2])
    out = bt.oracle_ep(rows, [1, 2])
    assert sorted(out.columns) == ["code", "ep", "gw"]
    assert set(out["ep"]) == {2.0}
    assert len(out) == 40


def test_oracle_ep_sums_a_double_gameweek_and_drops_other_gameweeks():
    rows = pd.concat([_season_rows([1]), _season_rows([1]), _season_rows([2])],
                     ignore_index=True)
    out = bt.oracle_ep(rows, [1])
    assert set(out["gw"]) == {1}
    assert set(out["ep"]) == {4.0}


def test_oracle_ep_scores_a_player_who_did_not_feature_at_zero():
    rows = _season_rows([1])
    rows.loc[rows["code"] == 101, ["total_points", "minutes"]] = [0, 0]
    out = bt.oracle_ep(rows, [1])
    assert float(out.loc[out["code"] == 101, "ep"].iloc[0]) == 0.0


def test_backtest_model_ep_source_is_bit_identical_to_the_default(monkeypatch):
    """The default path must not move: everything measured before this change
    was measured on it."""
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    default = run_backtest(season="2025-26", start_gw=1, retrain_every=4)
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    explicit = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                            ep_source="model")
    assert explicit == default
    assert default["total"] == 72          # 3 gameweeks x (XI 22 + captain 2)


def test_backtest_rejects_an_unknown_ep_source(monkeypatch):
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    with pytest.raises(ValueError) as exc:
        run_backtest(season="2025-26", start_gw=1, ep_source="crystal ball")
    assert "crystal ball" in str(exc.value)


# --- oracle dominance ----------------------------------------------------
#
# The solver and the pool builder stay real here — the point of the check is
# that the oracle's EP actually reaches the MILP — so only the training and
# prediction machinery is stubbed out.

def _scored_season_rows(gws, n=20):
    """Player i scores i points every gameweek, at a flat price.

    A strictly-ranked pool is what makes the comparison meaningful: with the
    model EP flat at 1.0, only the oracle can tell the 19-point player from
    the 0-point one.
    """
    rows = []
    for gw in gws:
        for i in range(n):
            rows.append({
                "season_idx": 0, "gw": gw, "code": 101 + i,
                "element": 1 + i, "name": f"P{i}", "position": POSITIONS[i],
                "team_code": 1 + i % 7, "value": 40,
                "kickoff_time": f"2025-01-{gw:02d}T12:00:00Z",
                "total_points": i, "minutes": 90,
            })
    return pd.DataFrame(rows)


def _install_solver_stubs(monkeypatch, season_rows):
    """Everything except ``build_pool`` and ``solve_plan``, which stay real."""
    monkeypatch.setattr(bt, "load_config", lambda *a, **k: Config(
        entry_id=1, league_id=1, train_seasons=["2025-26"]))
    monkeypatch.setattr(bt, "load_bootstrap_sample", lambda *a, **k: {})
    monkeypatch.setattr(bt, "scoring_table", lambda *a, **k: {})
    monkeypatch.setattr(bt, "load_training_frame",
                        lambda *a, **k: (season_rows, pd.DataFrame(), None))
    monkeypatch.setattr(bt, "train_all", lambda *a, **k: {})
    monkeypatch.setattr(bt, "predict_components_simple",
                        lambda models, rows: rows)
    monkeypatch.setattr(bt, "assemble_ep", lambda comp, scoring: comp)
    monkeypatch.setattr(bt, "apply_calibration", lambda df, cal: df)
    monkeypatch.setattr(bt, "ep_matrix",
                        lambda df: df[["code", "gw"]].assign(ep=1.0))
    monkeypatch.setattr(bt.store, "save", lambda *a, **k: None)


def test_oracle_h1_xi_outscores_the_model_xi_on_the_same_fixture_data(
        monkeypatch):
    rows = _scored_season_rows([1, 2, 3])
    _install_solver_stubs(monkeypatch, rows)
    model = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                         ep_source="model")
    _install_solver_stubs(monkeypatch, rows)
    oracle = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                          ep_source="oracle")
    # GW1 is the squad build: no transfers, no hits either side, so the two
    # XIs are directly comparable.
    assert oracle["log"][0]["points"] >= model["log"][0]["points"]
    assert oracle["total"] >= model["total"]
```

Add `import pytest` to the top of `tests/test_backtest.py`:

```python
import pandas as pd
import pytest
from gaffer import backtest as bt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backtest.py -v`
Expected: FAIL — `AttributeError: module 'gaffer.backtest' has no attribute 'oracle_ep'`

- [ ] **Step 3: Write minimal implementation**

In `src/gaffer/backtest.py`, add the helper directly after `_actuals_frame`:

```python
EP_SOURCES = ("model", "oracle")


def oracle_ep(season_rows: pd.DataFrame, gws: list[int]) -> pd.DataFrame:
    """Perfect-foresight expected points: what each player actually scored.

    Same shape ``ep_matrix`` returns — one row per (code, gw), a double
    gameweek's fixtures summed — so it drops into the pool builder unchanged.
    A player with no fixture simply has no row, which ``build_pool`` already
    reads as 0.0, and a player who did not feature carries his real 0.

    This is the ceiling half of the decomposition, not a model: the gap
    between it and the ordinary replay is what better forecasting could win,
    and the gap between its own h3 and h1 runs is what multi-week planning
    could ever be worth.
    """
    rows = season_rows[season_rows["gw"].isin(gws)]
    return (rows.groupby(["code", "gw"], as_index=False)
            .agg(ep=("total_points", "sum")))
```

Change the `run_backtest` signature and docstring tail:

```python
def run_backtest(season: str = "2025-26", start_gw: int = 5,
                 retrain_every: int = 4, horizon: int = 1,
                 chips: bool = False, ep_source: str = "model") -> dict:
```

Append to its docstring, before the ``Returns`` line:

```
    ``ep_source`` selects where expected points come from. ``"model"`` is the
    ordinary replay and is bit-identical to the pre-oracle behaviour.
    ``"oracle"`` swaps in each player's *actual* points for the gameweek
    (:func:`oracle_ep`) and feeds them through the identical pipeline — same
    pool, same solver, same chip logic. Two simplifications are worth being
    explicit about: the replay never applies league tilt or availability
    filtering in either mode, so an oracle run is clairvoyant about scores
    and no more privileged than the model run about news; and it skips model
    training altogether, since nothing reads the fitted components.
```

Add the guard at the top of the body, right after the docstring:

```python
    if ep_source not in EP_SOURCES:
        raise ValueError(f"unknown ep_source: {ep_source!r} "
                         f"(expected one of {EP_SOURCES})")
    cfg = load_config()
```

Gate the retrain on the model path (replacing the current `if not models or ...`):

```python
        # An oracle run never reads a fitted component, so it skips the
        # refits entirely — the same replay, minutes instead of hours.
        if ep_source == "model" and (not models
                                     or (gw - start_gw) % retrain_every == 0):
            df, tg, _ = load_training_frame(max_season_idx=season_idx,
                                            max_gw=gw)
            models = train_all(df, tg, save=False)
```

And branch the EP computation (replacing the two lines that currently build `comp` and `ep`):

```python
        if ep_source == "oracle":
            ep = oracle_ep(season_rows, gws)
        else:
            comp = predict_components_simple(models, horizon_rows)
            ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                             models.get("calibration")))
        ep_by = {(int(r.code), int(r.gw)): float(r.ep) for r in ep.itertuples()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_backtest.py -v`
Expected: PASS (all existing tests plus 6 new)

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/backtest.py tests/test_backtest.py
git commit -m "feat: perfect-foresight ep_source in the season replay"
```

---

## Task 13: The decomposition 2×2

**Files:**
- Modify: `src/gaffer/evaluation.py` (replace the `run_decomposition` stub)
- Test: `tests/test_evaluation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluation.py`:

```python
from gaffer.evaluation import run_decomposition


def _fake_backtest(totals):
    """Stand in for ``run_backtest``, keyed by (ep_source, horizon)."""
    seen = []

    def fake(season="2025-26", start_gw=5, retrain_every=4, horizon=1,
             chips=False, ep_source="model"):
        seen.append((ep_source, horizon))
        total = totals[(ep_source, horizon)]
        return {"season": season, "from_gw": start_gw, "total": total,
                "per_gw": round(total / 34, 2),
                "log": [{"gw": g, "hits": 1 if g == 6 else 0}
                        for g in range(5, 39)],
                "chips_played": {}}

    return fake, seen


def test_run_decomposition_runs_the_full_two_by_two(monkeypatch):
    fake, seen = _fake_backtest({("model", 1): 1800, ("model", 3): 1850,
                                 ("oracle", 1): 2600, ("oracle", 3): 2700})
    monkeypatch.setattr("gaffer.backtest.run_backtest", fake)
    out = run_decomposition(season="2025-26", start_gw=5)
    assert sorted(seen) == [("model", 1), ("model", 3),
                            ("oracle", 1), ("oracle", 3)]
    assert sorted(out["cells"]) == ["model_h1", "model_h3",
                                    "oracle_h1", "oracle_h3"]
    assert out["cells"]["oracle_h3"] == {"total": 2700, "per_gw": 79.41,
                                         "hits": 1}


def test_run_decomposition_names_the_two_derived_numbers(monkeypatch):
    fake, _ = _fake_backtest({("model", 1): 1800, ("model", 3): 1850,
                              ("oracle", 1): 2600, ("oracle", 3): 2700})
    monkeypatch.setattr("gaffer.backtest.run_backtest", fake)
    out = run_decomposition(season="2025-26", start_gw=5)
    # What better forecasting can win, at the horizon we actually plan on.
    assert out["forecast_gap_h3"] == 850.0
    # The most multi-week planning can ever be worth, forecasting perfect.
    assert out["planning_ceiling"] == 100.0
    assert out["season"] == "2025-26" and out["start_gw"] == 5
    assert out["git_sha"] and out["run_at"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluation.py -v`
Expected: FAIL — `gaffer.errors.GafferError: decomposition is not implemented yet`

- [ ] **Step 3: Write minimal implementation**

Replace the `run_decomposition` stub in `src/gaffer/evaluation.py`:

```python
DECOMPOSITION_HORIZONS = (1, 3)
DECOMPOSITION_SOURCES = ("model", "oracle")


def run_decomposition(season: str = "2025-26", start_gw: int = 5) -> dict:
    """Split the replay's shortfall into forecasting error and headroom.

    Four full replays — {model, oracle} x {h1, h3}. The two numbers that come
    out are the ones worth arguing about:

    ``forecast_gap_h3``
        ``oracle_h3 - model_h3``: everything a perfect forecast would add at
        the horizon the tool actually plans on. This is the size of the prize
        for model work.
    ``planning_ceiling``
        ``oracle_h3 - oracle_h1``: what looking three weeks ahead is worth
        when the forecast is already perfect — the absolute ceiling on
        multi-week planning, and usually a good deal smaller than people
        expect.

    Slow: the two model runs retrain every four gameweeks across a season.
    Run it under ``caffeinate -i``; machine sleep has killed long runs here
    before.
    """
    from gaffer.backtest import run_backtest

    cells: dict[str, dict] = {}
    for source in DECOMPOSITION_SOURCES:
        for horizon in DECOMPOSITION_HORIZONS:
            out = run_backtest(season=season, start_gw=start_gw,
                               horizon=horizon, ep_source=source)
            cells[f"{source}_h{horizon}"] = {
                "total": int(out["total"]),
                "per_gw": float(out["per_gw"]),
                "hits": int(sum(int(r["hits"]) for r in out["log"])),
            }
            print(f"{source} h{horizon}: {out['total']}", flush=True)

    return {
        "run_at": run_at(),
        "git_sha": git_sha(),
        "season": season,
        "start_gw": int(start_gw),
        "cells": cells,
        "forecast_gap_h3": float(cells["oracle_h3"]["total"]
                                 - cells["model_h3"]["total"]),
        "planning_ceiling": float(cells["oracle_h3"]["total"]
                                  - cells["oracle_h1"]["total"]),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluation.py tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation.py
git commit -m "feat: model/oracle x h1/h3 replay decomposition"
```

---

## Task 14: `GET /api/quality`

**Files:**
- Create: `src/gaffer/web/routers/quality.py`
- Modify: `src/gaffer/web/schemas.py:382` (append)
- Modify: `src/gaffer/web/app.py:25,70-76`
- Test: `tests/test_web_quality.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_quality.py`:

```python
import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

CATEGORY_TABLE = {cat: {"rmse": 1.0, "mae": 0.5, "n": 100}
                  for cat in ["zeros", "blanks", "tickers", "haulers", "all"]}

PAYLOAD = {
    "current": {
        "run_at": "2026-08-25T00:00:00+00:00", "git_sha": "abc1234",
        "holdout_slots": 10,
        "stratified": {"all": CATEGORY_TABLE, "starters": CATEGORY_TABLE},
        "heads": {"p_play": {"log_loss": 0.2732,
                             "reliability": [{"n": 40, "pred": 0.9,
                                              "obs": 0.88}]}},
        "baselines": {"last5": CATEGORY_TABLE,
                      "season_ppg": CATEGORY_TABLE},
    },
    "benchmark": {
        "run_at": "2026-08-25T01:00:00+00:00", "git_sha": "abc1234",
        "test_season": "2024-25",
        "stratified": {"all": CATEGORY_TABLE},
        "references": {"openfpl": {"haulers": {"rmse": 5.142, "mae": 4.317}},
                       "fplreview": {"haulers": {"rmse": 5.172,
                                                 "mae": 4.381}}},
        "caveat": "yardstick, not a controlled comparison",
    },
    "decomposition": {
        "run_at": "2026-08-25T02:00:00+00:00", "git_sha": "abc1234",
        "season": "2025-26", "start_gw": 5,
        "cells": {"model_h1": {"total": 1800, "per_gw": 52.94, "hits": 4},
                  "model_h3": {"total": 1850, "per_gw": 54.41, "hits": 3},
                  "oracle_h1": {"total": 2600, "per_gw": 76.47, "hits": 0},
                  "oracle_h3": {"total": 2700, "per_gw": 79.41, "hits": 0}},
        "forecast_gap_h3": 850.0, "planning_ceiling": 100.0,
    },
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_quality_without_an_artifact_tells_you_to_run_evaluate(client):
    response = client.get("/api/quality")
    assert response.status_code == 422
    assert "gaffer evaluate" in response.json()["detail"]


def test_quality_returns_every_stored_mode(client, tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(PAYLOAD))
    body = client.get("/api/quality").json()
    assert body["current"]["holdout_slots"] == 10
    assert body["current"]["stratified"]["all"]["haulers"]["rmse"] == 1.0
    assert body["current"]["heads"]["p_play"]["reliability"][0]["obs"] == 0.88
    assert body["benchmark"]["references"]["openfpl"]["haulers"]["mae"] \
        == 4.317
    assert body["decomposition"]["forecast_gap_h3"] == 850.0


def test_quality_tolerates_a_partial_artifact(client, tmp_path):
    """A benchmark run that has never happened is a null, not a 500."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "evaluation.json").write_text(
        json.dumps({"current": PAYLOAD["current"]}))
    body = client.get("/api/quality").json()
    assert body["benchmark"] is None and body["decomposition"] is None
    assert body["current"]["git_sha"] == "abc1234"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web_quality.py -v`
Expected: FAIL — all three, `assert 404 == 422` (no such route)

- [ ] **Step 3: Write minimal implementation**

Append to `src/gaffer/web/schemas.py`:

```python
class CategoryMetrics(BaseModel):
    rmse: float
    mae: float
    n: int


class ReferenceMetrics(BaseModel):
    """A published number: no row count, because we did not measure it."""

    rmse: float
    mae: float


class ReliabilityBin(BaseModel):
    n: int
    pred: float
    obs: float


class HeadMetrics(BaseModel):
    log_loss: float
    reliability: list[ReliabilityBin]


class CurrentEvaluation(BaseModel):
    run_at: str
    git_sha: str
    holdout_slots: int
    stratified: dict[str, dict[str, CategoryMetrics]]
    """cut ("all" / "starters") -> return category -> metrics."""
    heads: dict[str, HeadMetrics]
    baselines: dict[str, dict[str, CategoryMetrics]]


class BenchmarkEvaluation(BaseModel):
    run_at: str
    git_sha: str
    test_season: str
    stratified: dict[str, dict[str, CategoryMetrics]]
    references: dict[str, dict[str, ReferenceMetrics]]
    caveat: str


class DecompositionCell(BaseModel):
    total: int
    per_gw: float
    hits: int


class Decomposition(BaseModel):
    run_at: str
    git_sha: str
    season: str
    start_gw: int
    cells: dict[str, DecompositionCell]
    """``{model,oracle}_h{1,3}`` -> that replay's outcome."""
    forecast_gap_h3: float
    """oracle_h3 - model_h3: what better forecasting could still win."""
    planning_ceiling: float
    """oracle_h3 - oracle_h1: the ceiling on multi-week planning."""


class Quality(BaseModel):
    """Whichever modes have been run. Each is independent and may be absent."""

    current: CurrentEvaluation | None = None
    benchmark: BenchmarkEvaluation | None = None
    decomposition: Decomposition | None = None
```

Create `src/gaffer/web/routers/quality.py`:

```python
"""The Model Quality page's one endpoint.

Disk-only and deliberately so: `gaffer evaluate` retrains every component and
takes minutes to hours, which is not something a page load may start. The UI
renders the artifact; the CLI makes it.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.evaluation import load_evaluation
from gaffer.web.schemas import Quality

router = APIRouter(prefix="/api", tags=["quality"])


@router.get("/quality", response_model=Quality)
def quality() -> Quality:
    # load_evaluation raises GafferError when the artifact is missing, which
    # the app-wide handler turns into a 422 carrying the "run gaffer
    # evaluate" sentence the empty state prints verbatim.
    return Quality(**load_evaluation())
```

In `src/gaffer/web/app.py`, extend the router import (line 25) and registration:

```python
from gaffer.web.routers import (advice, league, live, meta, players, quality,
                                whatif)
```

```python
    app.include_router(advice.router)
    app.include_router(league.router)
    app.include_router(live.router)
    app.include_router(meta.router)
    app.include_router(players.router)
    app.include_router(quality.router)
    app.include_router(whatif.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_web_quality.py tests/test_web_app.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/web/routers/quality.py src/gaffer/web/schemas.py src/gaffer/web/app.py tests/test_web_quality.py
git commit -m "feat: GET /api/quality serving the evaluation artifact"
```

---

## Task 15: Model Quality page

**Files:**
- Create: `frontend/src/pages/Quality.tsx`, `frontend/src/pages/Quality.test.tsx`
- Modify: `frontend/src/types.ts:311` (append)
- Modify: `frontend/src/App.tsx:1-35`
- Modify: `frontend/src/components/Sidebar.tsx:3-12`
- Modify: `frontend/src/App.test.tsx:19-20`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/Quality.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Quality from './Quality'

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

const table = {
  zeros: { rmse: 0.9, mae: 0.4, n: 900 },
  blanks: { rmse: 1.4, mae: 0.8, n: 400 },
  tickers: { rmse: 1.6, mae: 1.2, n: 200 },
  haulers: { rmse: 5.3, mae: 4.4, n: 100 },
  all: { rmse: 2.1, mae: 1.0, n: 1600 },
}

const payload = {
  current: {
    run_at: '2026-08-25T00:00:00+00:00', git_sha: 'abc1234',
    holdout_slots: 10,
    stratified: { all: table, starters: table },
    heads: {
      p_play: {
        log_loss: 0.2732,
        reliability: [{ n: 40, pred: 0.9, obs: 0.88 },
                      { n: 60, pred: 0.2, obs: 0.25 }],
      },
      p60: { log_loss: 0.2563, reliability: [{ n: 10, pred: 0.5, obs: 0.5 }] },
      cs: { log_loss: 0.5511, reliability: [{ n: 10, pred: 0.3, obs: 0.28 }] },
    },
    baselines: { last5: table, season_ppg: table },
  },
  benchmark: {
    run_at: '2026-08-25T01:00:00+00:00', git_sha: 'abc1234',
    test_season: '2024-25',
    stratified: { all: table },
    references: {
      openfpl: {
        zeros: { rmse: 0.818, mae: 0.427 },
        blanks: { rmse: 1.291, mae: 0.749 },
        tickers: { rmse: 1.517, mae: 1.127 },
        haulers: { rmse: 5.142, mae: 4.317 },
      },
      fplreview: {
        zeros: { rmse: 0.689, mae: 0.237 },
        blanks: { rmse: 1.189, mae: 0.597 },
        tickers: { rmse: 1.594, mae: 1.227 },
        haulers: { rmse: 5.172, mae: 4.381 },
      },
    },
    caveat: 'Treat these as a yardstick, not a controlled comparison.',
  },
  decomposition: {
    run_at: '2026-08-25T02:00:00+00:00', git_sha: 'abc1234',
    season: '2025-26', start_gw: 5,
    cells: {
      model_h1: { total: 1800, per_gw: 52.94, hits: 4 },
      model_h3: { total: 1850, per_gw: 54.41, hits: 3 },
      oracle_h1: { total: 2600, per_gw: 76.47, hits: 0 },
      oracle_h3: { total: 2700, per_gw: 79.41, hits: 0 },
    },
    forecast_gap_h3: 850, planning_ceiling: 100,
  },
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(payload)
})

describe('Quality', () => {
  it('shows the holdout table beside the baselines', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /model quality/i }))
      .toBeInTheDocument()
    expect(screen.getByText(/last-10-slot holdout/i)).toBeInTheDocument()
    expect(screen.getAllByText('Haulers').length).toBeGreaterThan(0)
    expect(screen.getByText(/last-5 mean/i)).toBeInTheDocument()
    expect(screen.getByText(/season ppg/i)).toBeInTheDocument()
  })

  it('puts the published numbers next to ours in the benchmark', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText('OpenFPL')).toBeInTheDocument()
    expect(screen.getByText('FPL Review')).toBeInTheDocument()
    expect(screen.getByText('5.142')).toBeInTheDocument()
    expect(screen.getByText(/yardstick/i)).toBeInTheDocument()
  })

  it('draws a reliability curve per probability head', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByLabelText('P(plays) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(60+ minutes) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(clean sheet) reliability'))
      .toBeInTheDocument()
  })

  it('spells out the two derived decomposition numbers', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText('850')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText(/better forecasting/i)).toBeInTheDocument()
    expect(screen.getByText(/multi-week planning/i)).toBeInTheDocument()
    expect(screen.getByText('2700')).toBeInTheDocument()
  })

  it('shows an empty state when nothing has been evaluated yet', async () => {
    apiGet.mockRejectedValue(new FakeApiError(
      422, 'no evaluation on disk — run `gaffer evaluate` first'))
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText(/run `gaffer evaluate` first/))
      .toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/pages/Quality.test.tsx`
Expected: FAIL — `Failed to resolve import "./Quality"`

- [ ] **Step 3: Write minimal implementation**

Append to `frontend/src/types.ts`:

```ts
export interface CategoryMetrics {
  rmse: number
  mae: number
  n: number
}

export interface ReferenceMetrics {
  rmse: number
  mae: number
}

export interface ReliabilityBin {
  n: number
  pred: number
  obs: number
}

export interface HeadMetrics {
  log_loss: number
  reliability: ReliabilityBin[]
}

export type StratifiedTable = Record<string, CategoryMetrics>

export interface CurrentEvaluation {
  run_at: string
  git_sha: string
  holdout_slots: number
  stratified: Record<string, StratifiedTable>
  heads: Record<string, HeadMetrics>
  baselines: Record<string, StratifiedTable>
}

export interface BenchmarkEvaluation {
  run_at: string
  git_sha: string
  test_season: string
  stratified: Record<string, StratifiedTable>
  references: Record<string, Record<string, ReferenceMetrics>>
  caveat: string
}

export interface DecompositionCell {
  total: number
  per_gw: number
  hits: number
}

export interface DecompositionData {
  run_at: string
  git_sha: string
  season: string
  start_gw: number
  cells: Record<string, DecompositionCell>
  forecast_gap_h3: number
  planning_ceiling: number
}

export interface QualityData {
  current: CurrentEvaluation | null
  benchmark: BenchmarkEvaluation | null
  decomposition: DecompositionData | null
}
```

Create `frontend/src/pages/Quality.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { ApiError, apiGet } from '../api/client'
import LineChart from '../components/LineChart'
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, HeadMetrics,
  QualityData, StratifiedTable,
} from '../types'

// Categories are OpenFPL's, defined on actual points, so the labels have to
// stay recognisable next to their published table.
const CATEGORIES: Array<[string, string]> = [
  ['zeros', 'Zeros'],
  ['blanks', 'Blanks'],
  ['tickers', 'Tickers'],
  ['haulers', 'Haulers'],
  ['all', 'All'],
]

const HEADS: Array<[string, string]> = [
  ['p_play', 'P(plays)'],
  ['p60', 'P(60+ minutes)'],
  ['cs', 'P(clean sheet)'],
]

const SOURCE_LABELS: Record<string, string> = {
  openfpl: 'OpenFPL',
  fplreview: 'FPL Review',
}

const CELLS: Array<[string, string]> = [
  ['model_h1', 'Model, 1-week'],
  ['model_h3', 'Model, 3-week'],
  ['oracle_h1', 'Oracle, 1-week'],
  ['oracle_h3', 'Oracle, 3-week'],
]

function StratifiedTableView(
  { columns }: { columns: Array<[string, StratifiedTable]> },
) {
  return (
    <table>
      <thead>
        <tr>
          <th>Category</th>
          {columns.map(([name]) => (
            <th key={name} colSpan={2}>{name}</th>
          ))}
        </tr>
        <tr>
          <th />
          {columns.map(([name]) => [
            <th key={`${name}-rmse`}>RMSE</th>,
            <th key={`${name}-mae`}>MAE</th>,
          ])}
        </tr>
      </thead>
      <tbody>
        {CATEGORIES.map(([key, label]) => (
          <tr key={key}>
            <td>{label}</td>
            {columns.map(([name, table]) => [
              <td key={`${name}-${key}-rmse`}>
                {table[key] === undefined ? '—' : table[key].rmse}
              </td>,
              <td key={`${name}-${key}-mae`}>
                {table[key] === undefined ? '—' : table[key].mae}
              </td>,
            ])}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Reliability({ label, head }: { label: string; head: HeadMetrics }) {
  return (
    <div>
      <p className="muted">{label} — log loss {head.log_loss}</p>
      <LineChart
        label={`${label} reliability`}
        series={[
          {
            name: 'observed',
            colour: '#4ade80',
            points: head.reliability.map((bin) => ({
              x: bin.pred, y: bin.obs,
            })),
          },
          // The diagonal a perfectly calibrated head would sit on.
          {
            name: 'perfect',
            colour: '#60a5fa',
            points: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
          },
        ]}
      />
    </div>
  )
}

function CurrentSection({ current }: { current: CurrentEvaluation }) {
  return (
    <>
      <div className="card">
        <h2>Holdout</h2>
        <p className="muted">
          Last-10-slot holdout, {current.holdout_slots} gameweeks, sha{' '}
          {current.git_sha}, run {current.run_at}.
        </p>
        <StratifiedTableView
          columns={[
            ['Model (all)', current.stratified.all ?? {}],
            ['Model (starters)', current.stratified.starters ?? {}],
            ['Last-5 mean', current.baselines.last5 ?? {}],
            ['Season PPG', current.baselines.season_ppg ?? {}],
          ]}
        />
      </div>
      <div className="card">
        <h2>Calibration</h2>
        {HEADS.map(([key, label]) => {
          const head = current.heads[key]
          return head === undefined ? null
            : <Reliability key={key} label={label} head={head} />
        })}
      </div>
    </>
  )
}

function BenchmarkSection({ benchmark }: { benchmark: BenchmarkEvaluation }) {
  const references: Array<[string, StratifiedTable]> = Object.entries(
    benchmark.references,
  ).map(([source, table]) => [
    SOURCE_LABELS[source] ?? source,
    Object.fromEntries(Object.entries(table).map(([cat, m]) => [
      cat, { rmse: m.rmse, mae: m.mae, n: 0 },
    ])) as StratifiedTable,
  ])
  return (
    <div className="card">
      <h2>Benchmark — {benchmark.test_season}</h2>
      <StratifiedTableView
        columns={[['Ours', benchmark.stratified.all ?? {}], ...references]}
      />
      <p className="muted">{benchmark.caveat}</p>
    </div>
  )
}

function DecompositionSection(
  { decomposition }: { decomposition: DecompositionData },
) {
  return (
    <div className="card">
      <h2>Decomposition — {decomposition.season} from GW
        {decomposition.start_gw}</h2>
      <table>
        <thead>
          <tr><th>Run</th><th>Total</th><th>Per GW</th><th>Hits</th></tr>
        </thead>
        <tbody>
          {CELLS.map(([key, label]) => {
            const cell = decomposition.cells[key]
            return cell === undefined ? null : (
              <tr key={key}>
                <td>{label}</td>
                <td>{cell.total}</td>
                <td>{cell.per_gw}</td>
                <td>{cell.hits}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <table>
        <tbody>
          <tr>
            <td>Forecast gap (3-week)</td>
            <td>{decomposition.forecast_gap_h3}</td>
            <td className="muted">
              points better forecasting could still win
            </td>
          </tr>
          <tr>
            <td>Planning ceiling</td>
            <td>{decomposition.planning_ceiling}</td>
            <td className="muted">
              the most multi-week planning can ever be worth
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export default function Quality() {
  const [data, setData] = useState<QualityData | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<QualityData>('/api/quality').then(setData).catch((e: Error) => {
      // A 422 here is the ordinary "nothing has been evaluated yet" state,
      // not a failure: the server's own sentence says what to run.
      if (e instanceof ApiError && e.status === 422) setEmpty(e.message)
      else setError(e.message)
    })
  }, [])

  if (error) return <p className="bad">{error}</p>
  if (empty) {
    return (
      <>
        <h2>Model Quality</h2>
        <div className="card"><p className="muted">{empty}</p></div>
      </>
    )
  }
  if (!data) return <p className="muted">Loading…</p>

  return (
    <>
      <h2>Model Quality</h2>
      {data.current && <CurrentSection current={data.current} />}
      {data.benchmark && <BenchmarkSection benchmark={data.benchmark} />}
      {data.decomposition
        && <DecompositionSection decomposition={data.decomposition} />}
    </>
  )
}
```

In `frontend/src/App.tsx`, add the import and the route:

```tsx
import Players from './pages/Players'
import Quality from './pages/Quality'
import RivalDetail from './pages/RivalDetail'
```

```tsx
          <Route path="/history" element={<History />} />
          <Route path="/quality" element={<Quality />} />
          <Route path="/health" element={<Health />} />
```

In `frontend/src/components/Sidebar.tsx`, add the entry:

```tsx
const PAGES: Array<[string, string]> = [
  ['/', 'This Week'],
  ['/whatif', 'What-If Lab'],
  ['/league', 'League Race'],
  ['/live', 'Live'],
  ['/players', 'Players'],
  ['/history', 'History'],
  ['/quality', 'Model Quality'],
  ['/health', 'Runs & Health'],
  ['/ticker', 'Fixture Ticker'],
]
```

In `frontend/src/App.test.tsx`, extend the sidebar assertion (replace the `it` title and label list):

```tsx
  it('lists every page in the sidebar', () => {
    render(<MemoryRouter><App /></MemoryRouter>)
    for (const label of ['This Week', 'What-If Lab', 'League Race', 'Live',
      'Players', 'History', 'Model Quality', 'Runs & Health']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
  })
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `frontend/`): `npx vitest run`
Expected: PASS (every suite, including `Quality.test.tsx` and `App.test.tsx`)

Run (from `frontend/`): `npx tsc -b`
Expected: no output, exit 0

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Quality.tsx frontend/src/pages/Quality.test.tsx frontend/src/types.ts frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat: Model Quality page with reliability curves and decomposition"
```

---

## Execution Notes

- **Python tests:** `uv run pytest` from the repo root. A single file: `uv run pytest tests/test_bps.py -v`.
- **Frontend tests:** `npx vitest run` from `frontend/`. Watch mode (`npx vitest`) is fine locally but never in a task's verification step.
- **Typecheck:** `npx tsc -b` from `frontend/`. Run it after any change to `types.ts`, a page, or a component — vitest does not typecheck.
- **The full suite must be green before every commit**, not just the file you touched: `uv run pytest` and, for a frontend task, `npx vitest run` plus `npx tsc -b`.
- **Long runs go under `caffeinate`.** `gaffer evaluate --decompose` is four season replays and `gaffer evaluate --mode benchmark` is a full refit plus 38 gameweeks of prediction. Launch them as
  `caffeinate -i uv run gaffer evaluate --decompose` and
  `caffeinate -i uv run gaffer evaluate --mode benchmark`.
  Machine sleep has killed long runs in this repo twice. None of the plan's tasks require a real run to finish — every test uses fixtures or stubs — so treat the real runs as the post-merge gate measurement.
- **Never touch `.claude/`.** It is untracked and must stay untracked. `git add -A` and `git add .` are forbidden anywhere in this plan; every commit step lists its files explicitly.
- **Protected source-text tests.** `tests/test_assemble.py`, `tests/test_odds.py` and `tests/test_advise.py` assert on the *source text* of `run_advise` / `predict_components`: the literal `ep_matrix(apply_calibration(assemble_ep(`, `blend_team_odds(` appearing before `comp.merge(tp`, and the ordering `fetch_rival_entries(` < `tilt_ep(` < `pool = build_pool(` with the literal `build_pool(players, pool_ep,`. No task here edits `advise.py`; if one of these fails, the cause is an accidental edit there, not a real regression.
- **Bit-identical default replay.** Task 12 changes `run_backtest`'s body. `ep_source="model"` must produce byte-identical results to today; `test_backtest_model_ep_source_is_bit_identical_to_the_default` is the guard and must never be weakened to accommodate a refactor.
- **Raw-vs-tilted EP discipline is untouched.** Nothing here tilts anything: displayed numbers stay raw, and the oracle replay runs with league tilt off (the replay never applied it in either mode).
- **No train/serve skew, for free.** `advise.run_advise` builds its prediction frame from `load_training_frame` (`src/gaffer/advise.py:426`), so Task 4's single integration point covers both training and serving. No separate change to `advise.py` is needed — and none should be made.
- **The bonus gate is a post-merge measurement, not a task.** Once Tasks 1-5 are merged, run `caffeinate -i uv run gaffer evaluate` and compare against the stored `current` block from before the change: bonus MAE must not regress against the re-derived truth, and `mae_starters` must not regress materially. Record the numbers in the outcome section of `docs/superpowers/specs/2026-08-25-gaffer-v4a-measure-design.md`. Accept on measured improvement or on neutral-with-cleaner-semantics. Capture the pre-change `current` block *first* — run `gaffer evaluate` on the branch point and keep the artifact — or there is nothing to compare to.
- **Ordering.** Tasks 1-5 are the bonus workstream and must land in order. Tasks 6-11 (evaluation) depend only on 1-5 being merged for the numbers to mean anything, not for the code to compile. Task 13 depends on Task 12. Tasks 14-15 depend on Task 8 (the artifact) and Task 13 (the decomposition key). Task 11 deliberately lands a one-line `run_decomposition` stub that Task 13 replaces.
