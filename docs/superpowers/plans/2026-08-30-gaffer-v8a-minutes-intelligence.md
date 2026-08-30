# Gaffer v8a Minutes Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attack the zeros gap (holdout zeros RMSE 1.053 post-Z1) with minutes *information* rather than architecture: manager-tenure and rotation-prior features, a clean re-test of congestion, mode-level measurement, a sharper serve-time line-up layer, and a shadow-only LLM presser classifier — every arm pre-registered, every arm individually withdrawable.

**Architecture:** Five features on four seams, none of them protected.
`data/manager_tenures.toml` is a new committed reference asset read by `src/gaffer/data/managers.py`, which turns a (club, date) into a *manager-spell key*. `features/engineer.py` grows `add_rotation_priors`/`latest_rotation_priors` (F1) over that key and a `prefix=` argument on `add_congestion`/`latest_congestion` that makes the league-only congestion columns a separate, separately-attributable arm (F2). Both builders are wired into `load_training_frame` and `build_prediction_frame` and land in `feature_columns()` — but **not** in `MINUTES_FEATURES`: `scripts/v8a_arms.py` patches `train.MINUTES_FEATURES` per arm exactly the way `scripts/z1_arms.py` patches `minutes.DNP_CALIBRATION_DEFAULT`, so a candidate column costs the shipped model nothing until Task 17 adopts the arms the orchestrator's G1 run kept. `evaluation.py` and `zeros_diagnostic.py` grow P(start) readouts (F3). The serve-time layer moves through the news chain, never through protected `advise.py`: `fetch_lineups` emits an `absence_damp` column for notable absentees, `fetch_injuries` parses the "Further Detail" cell and attaches LLM verdicts, `availability_frame` carries all three new columns, and `apply_availability` applies them and writes the presser shadow log (F4/F5). `snapshot.py` inherits the new columns for free because `SNAPSHOT_COLS` is derived from `AVAILABILITY_COLS`.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, LightGBM, pytest, tomllib, subprocess (headless `claude -p`).

**Prerequisite:** work on branch `feat/gaffer-v8a` cut from `main`. Authoritative spec: `docs/superpowers/specs/2026-08-30-gaffer-v8a-minutes-intelligence-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 18 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`.
If a task appears to need an edit inside one of these, the plan is wrong — stop and report rather than editing.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `reports/`, `models/`, `logs/`, `.claude/`, `config.toml`, or anything under `data/` — **with one deliberate exception**, `data/manager_tenures.toml`, which is a committed reference asset like `injury_return_curves.json` and is staged by that exact path in Task 1.

**Gate rule (CONVENTIONS.md §7):** implementers build the drivers and never run the gates. Every gate below says "orchestrator runs X". Task 18 is the checklist, unfilled.

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `data/manager_tenures.toml` | Create (committed asset) | D1: one entry per EPL head-coach spell, 2022-07-01 → present. |
| `src/gaffer/data/managers.py` | Create | Tenure loader and `spell_keys` — (club, date) → manager-spell key, degrading to club-season windows. |
| `tests/test_managers.py` | Create | Loader unit suite: shapes, open spells, absent/corrupt asset, key degradation. |
| `tests/test_manager_tenures.py` | Create | D1 validation: exactly one spell per club-date over the real training frame; skipped when the parquet is absent. |
| `src/gaffer/features/engineer.py` | Modify (new F1 builders; `prefix=` on congestion; `build_prediction_frame`; `feature_columns`) | F1 + F2 feature builders, train and serve sides. |
| `tests/test_engineer_v8a.py` | Create | F1/F2 builder suite: leakage discipline, degradation without the asset, train/serve agreement. |
| `src/gaffer/models/train.py` | Modify (`load_training_frame` L242-247; `MINUTES_FEATURES` in Task 17 only) | Wires the new builders into the training frame; adopts kept arms at the end. |
| `scripts/v8a_arms.py` | Create | G1 driver: baseline + one arm per candidate over `evaluate_benchmark`. |
| `tests/test_v8a_driver.py` | Create | Driver suite: arm table, verdict arithmetic, no side effects on `MINUTES_FEATURES`. |
| `src/gaffer/evaluation.py` | Modify (`evaluate_current` heads block) | F3: P(start) head metrics. |
| `src/gaffer/zeros_diagnostic.py` | Modify (`_holdout`, `zeros_report`, `format_diagnostic`) | F3: per-stratum P(start) reliability. |
| `tests/test_evaluation_v8a.py` | Create | F3 suite over synthetic frames. |
| `src/gaffer/config.py` | Modify (`Config` fields; `[news]` block L113-117) | Seven new `[news]` keys + the cached serving config. |
| `config.example.toml` | Modify (append a `[news]` section) | Documents every new key. |
| `tests/test_config_v8a.py` | Create | Key-by-key defaults and overrides. |
| `src/gaffer/data/bootstrap.py` | Modify (`build_players` row dict) | Carries `starts`/`minutes` so the absence rule has a start share. |
| `src/gaffer/data/news/lineups.py` | Modify (`LINEUP_COLS`, `fetch_lineups`, new `notable_absences`) | F4: notable-absence rows. |
| `src/gaffer/artifacts.py` | Modify (`AVAILABILITY_COLS` L378-380; dtype loops L419-423) | Three new nullable availability columns. |
| `src/gaffer/data/news/normalize.py` | Modify (`AVAIL_COLS` L221; the line-ups and injuries blocks) | Carries the new columns through. |
| `src/gaffer/snapshot.py` | Modify (`snapshot_rows` dtype loops) | F4: the new columns get settled dtypes in the log. |
| `src/gaffer/models/availability.py` | Modify (`apply_availability`, `_gate_first_gw`, new helpers) | F4/F5 serving: absence damp, start floor, presser log. |
| `src/gaffer/data/news/classifier.py` | Create | F5: `classify_news` over headless `claude -p`, cached, never raising. |
| `tests/test_classifier.py` | Create | F5 suite with a fake `llm_command`; never touches the real CLI. |
| `src/gaffer/data/news/premierinjuries.py` | Modify (`INJURY_COLS`, `parse_injury_table`, `fetch_injuries`) | F5: "Further Detail" parsed and retained; classifier hook. |
| `src/gaffer/data/news/presser_log.py` | Create | F5: the append-only shadow log. |
| `tests/test_presser_log.py` | Create | Log suite: schema, atomic rewrite, dedupe. |
| `tests/test_availability_v8a.py` | Create | F4/F5 serving suite. |
| `tests/test_news_sources.py` | Modify (append) | Absence rows, further-detail parsing, verdict attachment. |
| `tests/test_v8a_degradation.py` | Create | G3 rails, including the protected-ordering pins copied forward. |
| `README.md` | Modify (Configuration ~L84; Where things live ~L236) | The `[news]` keys and the committed asset. |

---

## Task 1 — D1: the manager-tenure asset and its loader

**Files:**
- Create `data/manager_tenures.toml`
- Create `src/gaffer/data/managers.py`
- Create `tests/test_managers.py`

- [ ] **Write the failing test.** Create `tests/test_managers.py`:

```python
"""The manager-tenure asset: what it is, and what happens without it."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data.managers import (MANAGER_TENURES_PATH, TENURE_COLS,
                                  load_manager_tenures, spell_keys)

_TOML = """
[[spell]]
club = "Arsenal"
team_code = 3
manager = "Mikel Arteta"
start_date = "2019-12-20"
end_date = ""

[[spell]]
club = "Chelsea"
team_code = 8
manager = "Graham Potter"
start_date = "2022-09-08"
end_date = "2023-04-02"

[[spell]]
club = "Chelsea"
team_code = 8
manager = "Mauricio Pochettino"
start_date = "2023-04-02"
end_date = ""
"""


def _asset(tmp_path):
    dest = tmp_path / MANAGER_TENURES_PATH
    dest.write_text(_TOML, encoding="utf-8")
    return dest


def test_the_asset_reads_as_one_row_per_spell(tmp_path):
    out = load_manager_tenures(_asset(tmp_path))
    assert list(out.columns) == TENURE_COLS
    assert len(out) == 3
    assert out["team_code"].dtype == "int64"


def test_an_open_spell_has_no_end_date(tmp_path):
    out = load_manager_tenures(_asset(tmp_path))
    arteta = out[out["manager"] == "Mikel Arteta"].iloc[0]
    assert pd.isna(arteta["end_date"])


def test_an_absent_asset_is_none_not_an_empty_frame(tmp_path):
    """``None`` and "no spells" are opposite instructions to the builders:
    one says fall back to club-season windows, the other would say every club
    changed manager on every date."""
    assert load_manager_tenures(tmp_path / "nothing.toml") is None


def test_a_corrupt_asset_is_none_rather_than_a_raise(tmp_path):
    dest = tmp_path / MANAGER_TENURES_PATH
    dest.write_text("[[spell]\nbroken = ", encoding="utf-8")
    assert load_manager_tenures(dest) is None


def test_the_key_names_the_spell_the_date_sits_in(tmp_path):
    ten = load_manager_tenures(_asset(tmp_path))
    keys = spell_keys(pd.Series([8, 8]),
                      pd.Series(["2022-10-01T14:00:00Z",
                                 "2023-05-01T14:00:00Z"]),
                      pd.Series([0, 0]), ten)
    assert keys.iloc[0] != keys.iloc[1]
    assert "Potter" in keys.iloc[0]
    assert "Pochettino" in keys.iloc[1]


def test_a_club_date_no_spell_covers_falls_back_to_the_club_season(tmp_path):
    ten = load_manager_tenures(_asset(tmp_path))
    keys = spell_keys(pd.Series([99]), pd.Series(["2023-05-01T14:00:00Z"]),
                      pd.Series([2]), ten)
    assert keys.iloc[0] == "c99s2"


def test_no_asset_at_all_is_the_club_season_window_everywhere():
    keys = spell_keys(pd.Series([3, 3]),
                      pd.Series(["2023-05-01T14:00:00Z",
                                 "2024-05-01T14:00:00Z"]),
                      pd.Series([1, 2]), None)
    assert list(keys) == ["c3s1", "c3s2"]


@pytest.mark.parametrize("bad", [None, ""])
def test_a_row_without_a_team_code_is_dropped(tmp_path, bad):
    dest = tmp_path / MANAGER_TENURES_PATH
    dest.write_text(
        '[[spell]]\nclub = "X"\nmanager = "Y"\nstart_date = "2022-08-01"\n',
        encoding="utf-8")
    assert load_manager_tenures(dest) is None
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_managers.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.data.managers'`.

- [ ] **Write the implementation.** Create `src/gaffer/data/managers.py`:

```python
"""EPL head-coach spells, and the rotation key derived from them.

No head-coach data exists anywhere else in the repo, so v8a ships one: a
committed reference asset (``data/manager_tenures.toml``) in the spirit of
``injury_return_curves.json``. It is *optional at runtime* by design — a clone
without it, or one whose copy is corrupt, gets club-season windows instead of
manager spells and every F1 feature still computes. That degradation is a
rail, not an accident: see ``tests/test_v8a_degradation.py``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

from gaffer.data import store

MANAGER_TENURES_PATH = "manager_tenures.toml"
"""Relative to ``store.DATA_DIR``. Read at call time, not bound at import, so
a test that redirects the data directory redirects this too."""

TENURE_COLS = ["team_code", "club", "manager", "start_date", "end_date"]


def load_manager_tenures(path: Path | str | None = None
                         ) -> pd.DataFrame | None:
    """The tenure asset as a frame, or ``None`` when there isn't one.

    ``None`` rather than an empty frame, so a caller cannot mistake "no asset"
    for "no club ever changed manager" — the two are opposite instructions to
    :func:`spell_keys`. Every failure lands on ``None``: absent file, invalid
    TOML, no ``[[spell]]`` tables, no parseable ``team_code``.
    """
    dest = (Path(path) if path is not None
            else store.DATA_DIR / MANAGER_TENURES_PATH)
    if not dest.is_file():
        return None
    try:
        raw = tomllib.loads(dest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a broken asset degrades, never raises
        return None
    rows = raw.get("spell") or []
    if not rows:
        return None
    out = pd.DataFrame(rows)
    for col in TENURE_COLS:
        if col not in out.columns:
            out[col] = None
    out["team_code"] = pd.to_numeric(out["team_code"], errors="coerce")
    out = out[out["team_code"].notna()].copy()
    if out.empty:
        return None
    out["team_code"] = out["team_code"].astype("int64")
    out["start_date"] = pd.to_datetime(out["start_date"], errors="coerce",
                                       utc=True)
    # An open spell is written as an empty string rather than omitted, so the
    # asset reads as a table; both spellings have to arrive as NaT.
    end = out["end_date"].astype("object").where(
        out["end_date"].astype("object").ne(""), None)
    out["end_date"] = pd.to_datetime(end, errors="coerce", utc=True)
    out = out.dropna(subset=["start_date"])
    if out.empty:
        return None
    return (out[TENURE_COLS].sort_values(["team_code", "start_date"])
            .reset_index(drop=True))


def spell_keys(team_code, kickoff, season_idx,
               tenures: pd.DataFrame | None) -> pd.Series:
    """One string per row naming the manager spell that row's match sits in.

    The key is opaque on purpose — nothing reads it except a ``groupby``. What
    matters is that it changes exactly when the manager does, and that it
    degrades to ``c{club}s{season}`` for any row the asset cannot place: no
    asset at all, a club it does not carry, a date outside every spell, or a
    missing kickoff. A season-scoped club window is the honest fallback,
    because a season boundary is where most managerial change lands anyway.

    Half-open intervals: a spell covers ``start <= t < end``, so a successor
    whose ``start_date`` equals his predecessor's ``end_date`` claims the
    handover date and no match is ever counted twice.
    """
    club = pd.to_numeric(team_code, errors="coerce")
    season = pd.to_numeric(season_idx, errors="coerce")
    fallback = pd.Series(
        [f"c{int(c)}s{int(s)}" if pd.notna(c) and pd.notna(s) else ""
         for c, s in zip(club, season)], index=club.index, dtype="object")
    if tenures is None or tenures.empty:
        return fallback
    when = pd.to_datetime(kickoff, errors="coerce", utc=True)
    by_club: dict[int, list] = {}
    for r in tenures.itertuples():
        by_club.setdefault(int(r.team_code), []).append(
            (r.start_date, r.end_date,
             f"c{int(r.team_code)}m{r.manager}@{r.start_date.date()}"))
    out = []
    for c, t, back in zip(club, when, fallback):
        key = None
        if pd.notna(c) and pd.notna(t):
            for start, end, name in by_club.get(int(c), ()):
                if t >= start and (pd.isna(end) or t < end):
                    key = name
                    break
        out.append(key if key is not None else back)
    return pd.Series(out, index=club.index, dtype="object")
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_managers.py`
  Expected: `9 passed`.

- [ ] **Research and write the asset.** Create `data/manager_tenures.toml`. This step is *research*, not code: every EPL head-coach spell that covers any date from 2022-07-01 to today, for every club that appears in the training seasons `2022-23, 2023-24, 2024-25, 2025-26` plus the live `2026-27` season. Method, in order:

  1. List the clubs and their FPL `team_code`s the frame actually contains:

  ```bash
  uv run python -c "
  import pandas as pd
  from gaffer.data import store
  df = store.load('history/player_gw.parquet')
  live = store.load('live/player_gw.parquet') if store.exists('live/player_gw.parquet') else pd.DataFrame()
  codes = sorted(set(pd.concat([df, live], ignore_index=True)['team_code'].dropna().astype(int)))
  print(len(codes), codes)"
  ```

  2. Name each code from the bundled bootstrap (`teams` carry both `code` and `name`):

  ```bash
  uv run python -c "
  from gaffer.assets import load_bootstrap_sample
  for t in sorted(load_bootstrap_sample()['teams'], key=lambda t: t['code']):
      print(t['code'], t['name'])"
  ```

  Codes not in the current bootstrap (relegated clubs) must be named from the archived fixtures/teams data or from public record; every code printed by step 1 must appear in the asset.

  3. For each club, write its head-coach spells from public record and **cross-check every spell against a second independent source** (e.g. the club's own site and a reference encyclopaedia). Caretakers of fewer than four league matches are folded into the *successor's* spell — start the successor at the predecessor's departure date rather than inventing a two-match key nothing can estimate on.

  Format — one table per spell, `end_date = ""` for the current incumbent:

  ```toml
  # EPL head-coach spells, 2022-07-01 -> present.
  #
  # One [[spell]] per manager per club. Half-open: a spell covers
  # start_date <= match < end_date, so a successor's start_date is his
  # predecessor's end_date and no match is claimed twice. end_date = ""
  # means "still in post". Caretakers of under four league matches are folded
  # into the successor's spell.
  #
  # team_code is the FPL club code (the one player_gw.parquet carries), not
  # the season-scoped team id.

  [[spell]]
  club = "Arsenal"
  team_code = 3
  manager = "Mikel Arteta"
  start_date = "2019-12-20"
  end_date = ""

  [[spell]]
  club = "Aston Villa"
  team_code = 7
  manager = "Steven Gerrard"
  start_date = "2021-11-11"
  end_date = "2022-10-20"

  [[spell]]
  club = "Aston Villa"
  team_code = 7
  manager = "Unai Emery"
  start_date = "2022-10-20"
  end_date = ""
  ```

  A spell that began before 2022-07-01 keeps its real `start_date` — the window the features read is bounded by the data, not by the asset.

- [ ] **Sanity-check the asset before committing.**

```bash
uv run python -c "
from gaffer.data.managers import load_manager_tenures
t = load_manager_tenures()
print(len(t), 'spells across', t['team_code'].nunique(), 'clubs')
print(t.groupby('team_code').size().describe())"
```

Expected: roughly 60-70 spells across every club step 1 printed, at least one spell per club, and no club with only an end-dated spell (every club that is currently in the league needs an open one).

- [ ] **Commit.** The asset is the one deliberate exception to the never-stage-`data/` rule and is named by exact path.

```bash
git add src/gaffer/data/managers.py tests/test_managers.py data/manager_tenures.toml && git commit -m "$(cat <<'EOF'
feat: the committed manager-tenure asset and its loader

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — D1: the coverage validation test

**Files:**
- Create `tests/test_manager_tenures.py`

- [ ] **Write the test.** Create `tests/test_manager_tenures.py`:

```python
"""D1's validation: the asset covers every club-date the frame contains.

Exactly one spell per club per date — no gap, no overlap. A gap silently
degrades a club to its season window and an overlap silently splits a squad
in two, and both look like a working feature right up to the gate.

Skipped where the history parquet is absent (a fresh clone, CI): the asset's
own shape is pinned by ``tests/test_managers.py``, and this file is about the
join between the asset and the data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.managers import load_manager_tenures

HISTORY = "history/player_gw.parquet"


def _club_dates() -> pd.DataFrame:
    frames = [store.load(HISTORY)]
    if store.exists("live/player_gw.parquet"):
        frames.append(store.load("live/player_gw.parquet"))
    df = pd.concat(frames, ignore_index=True)
    out = df[["team_code", "kickoff_time"]].dropna().drop_duplicates()
    out["team_code"] = out["team_code"].astype(int)
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                         utc=True)
    return out.dropna(subset=["kickoff_time"])


@pytest.fixture(scope="module")
def tenures():
    if not store.exists(HISTORY):
        pytest.skip("no history parquet on this machine")
    ten = load_manager_tenures()
    if ten is None:
        pytest.skip("no manager-tenure asset on this machine")
    return ten


def test_every_club_date_is_covered_by_exactly_one_spell(tenures):
    dates = _club_dates()
    by_club: dict[int, list] = {}
    for r in tenures.itertuples():
        by_club.setdefault(int(r.team_code), []).append((r.start_date,
                                                         r.end_date))
    bad: list[tuple] = []
    for club, when in zip(dates["team_code"], dates["kickoff_time"]):
        hits = sum(1 for start, end in by_club.get(club, ())
                   if when >= start and (pd.isna(end) or when < end))
        if hits != 1:
            bad.append((club, str(when), hits))
    assert not bad, f"{len(bad)} club-dates not covered exactly once: {bad[:8]}"


def test_no_two_spells_at_one_club_overlap(tenures):
    for club, part in tenures.groupby("team_code"):
        part = part.sort_values("start_date")
        ends = part["end_date"].tolist()
        starts = part["start_date"].tolist()
        for i in range(len(part) - 1):
            assert pd.notna(ends[i]), (
                f"club {club}: a spell before another has no end date")
            assert ends[i] <= starts[i + 1], (
                f"club {club}: spells overlap at {ends[i]}")


def test_every_club_in_the_frame_has_a_spell(tenures):
    clubs = set(_club_dates()["team_code"])
    have = set(tenures["team_code"].astype(int))
    assert not (clubs - have), f"clubs with no spell at all: {clubs - have}"


def test_every_spell_names_a_manager(tenures):
    assert tenures["manager"].astype(str).str.strip().ne("").all()
```

- [ ] **Run it.** `uv run pytest -q tests/test_manager_tenures.py`
  Expected: `4 passed`. Any failure is an asset error, not a code error: fix `data/manager_tenures.toml` (the failure message names the club and the date) and re-run until green. Do **not** loosen the test.

- [ ] **Commit.**

```bash
git add tests/test_manager_tenures.py data/manager_tenures.toml && git commit -m "$(cat <<'EOF'
test: exactly-one-spell coverage over the real training frame

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — F1: the rotation-prior training builder

**Files:**
- Modify `src/gaffer/features/engineer.py` (new constants + `add_rotation_priors` + `_xi_churn`, after `add_rotation`, ~line 149)
- Create `tests/test_engineer_v8a.py`

- [ ] **Write the failing test.** Create `tests/test_engineer_v8a.py`:

```python
"""F1 and F2's builders: what they compute, and what they refuse to see."""

from __future__ import annotations

import pandas as pd

from gaffer.features.engineer import (ROTATION_PRIOR_FEATURES,
                                      TENURE_SHRINK_K, add_rotation_priors)


def _frame(managers=("A", "A", "A", "B", "B", "B")) -> pd.DataFrame:
    """Six matchdays, two players at one club, one manager change midway."""
    rows = []
    for i, _ in enumerate(managers):
        when = pd.Timestamp("2023-08-05", tz="UTC") + pd.Timedelta(days=7 * i)
        for code, started in ((1, 1.0), (2, 1.0 if i >= 3 else 0.0)):
            rows.append({"code": code, "team_code": 3, "season_idx": 1,
                         "gw": i + 1, "kickoff_time": when.isoformat(),
                         "starts": started,
                         "minutes": 90.0 if started else 0.0})
    return pd.DataFrame(rows)


def _tenures() -> pd.DataFrame:
    return pd.DataFrame({
        "team_code": [3, 3],
        "club": ["Arsenal", "Arsenal"],
        "manager": ["A", "B"],
        "start_date": pd.to_datetime(["2023-01-01", "2023-08-26"], utc=True),
        "end_date": pd.to_datetime(["2023-08-26", None], utc=True)})


def test_every_prior_feature_is_produced():
    out = add_rotation_priors(_frame(), _tenures())
    for col in ROTATION_PRIOR_FEATURES:
        assert col in out.columns


def test_the_first_match_of_a_spell_has_no_prior_evidence():
    """Strictly-past windows: the opening match under a manager has nothing
    before it, so the share and the churn are undefined rather than zero."""
    out = add_rotation_priors(_frame(), _tenures()).sort_values(
        ["code", "gw"]).reset_index(drop=True)
    first = out[(out["code"] == 1) & (out["gw"] == 1)].iloc[0]
    assert pd.isna(first["tenure_start_share"])
    assert pd.isna(first["xi_churn_r5"])
    assert first["manager_tenure_matches"] == 0.0


def test_the_tenure_counter_restarts_when_the_manager_changes():
    out = add_rotation_priors(_frame(), _tenures())
    by_gw = out[out["code"] == 1].set_index("gw")["manager_tenure_matches"]
    # Matches 1-3 under A, 4-6 under B: the count is matches *before* this one.
    assert list(by_gw.loc[[1, 2, 3]]) == [0.0, 1.0, 2.0]
    assert list(by_gw.loc[[4, 5, 6]]) == [0.0, 1.0, 2.0]


def test_the_share_is_shrunk_toward_the_club_mean():
    """Player 2 starts nothing under A. With one prior match his own record
    says 0.0 and the club's says 0.5, and the shrunk value sits between."""
    out = add_rotation_priors(_frame(), _tenures())
    row = out[(out["code"] == 2) & (out["gw"] == 2)].iloc[0]
    expected = (0.0 + TENURE_SHRINK_K * 0.5) / (1.0 + TENURE_SHRINK_K)
    assert row["tenure_start_share"] == pytest.approx(expected)


def test_started_last_match_reads_the_previous_row_only():
    out = add_rotation_priors(_frame(), _tenures())
    by_gw = out[out["code"] == 2].set_index("gw")["started_last_match"]
    assert pd.isna(by_gw.loc[1])
    assert by_gw.loc[4] == 0.0     # gw3 was a benching
    assert by_gw.loc[5] == 1.0     # gw4 was a start


def test_the_churn_index_counts_changes_between_consecutive_xis():
    """Player 2 comes into the XI at match 4, so exactly one name changed."""
    out = add_rotation_priors(_frame(), _tenures())
    row = out[(out["code"] == 1) & (out["gw"] == 6)].iloc[0]
    assert row["xi_churn_r5"] > 0.0


def test_without_the_asset_the_window_is_the_club_season():
    """No asset: one spell per club-season, so the counter never restarts
    inside a season and every column still computes."""
    out = add_rotation_priors(_frame(), None)
    by_gw = out[out["code"] == 1].set_index("gw")["manager_tenure_matches"]
    assert list(by_gw.loc[[1, 4, 6]]) == [0.0, 3.0, 5.0]
    assert out["tenure_start_share"].notna().any()


def test_a_frame_without_starts_yields_all_nan_columns():
    df = _frame().drop(columns=["starts"])
    out = add_rotation_priors(df, _tenures())
    for col in ROTATION_PRIOR_FEATURES:
        assert out[col].isna().all()
```

Add `import pytest` at the top of the file — `pytest.approx` is used above.

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_engineer_v8a.py`
  Expected: collection error — `ImportError: cannot import name 'ROTATION_PRIOR_FEATURES'`.

- [ ] **Write the implementation.** In `src/gaffer/features/engineer.py`, add the import at the top (after `import pandas as pd`):

```python
from gaffer.data.managers import spell_keys
```

Add the constants immediately below `MAX_CONGESTION_GAP`'s docstring (~line 36):

```python
ROTATION_PRIOR_FEATURES = ["tenure_start_share", "manager_tenure_matches",
                           "xi_churn_r5", "started_last_match"]
"""v8a's F1 candidates: how *this* manager has used this player.

:data:`ROTATION_FEATURES` read the season; these read the spell. A nailed-on
starter under the man who was sacked in October is a different bet in
November, and every feature the model currently has blends the two.
"""

TENURE_SHRINK_K = 5.0
"""Prior weight, in matches, for ``tenure_start_share``.

Read as ":data:`SHRINK_K_MODE`, for a shorter denominator". A new manager's
first month is exactly where the player's own record under him is worthless
and the club's own mean is all there is, so the prior is worth five matches
of it — lower than the mode rate's eight because a spell is short by
construction and a k that dominates the whole tenure measures nothing.
"""

MAX_TENURE_MATCHES = 76.0
"""Matches beyond which "settled XI" stops carrying information.

Two seasons. Same reasoning as :data:`MAX_DAYS_SINCE_START`: past that the
number is a tenure length, not a rotation signal, and the model should read
every long reign the same way.
"""

XI_CHURN_WINDOW = 5
"""Club matches the roulette index averages over."""
```

Add the builders after `add_rotation` (before `add_congestion`, ~line 150):

```python
def _xi_churn(spell: pd.Series, kt: pd.Series, code: pd.Series,
              starts: pd.Series) -> pd.Series:
    """Mean starting-XI changes over the last five club matches before this.

    The roulette index. A club match is ``(spell, kickoff)`` rather than a
    gameweek: a double gameweek is two team sheets and a slot key would merge
    them into one impossible XI of twenty-two.

    Strictly past, twice over. A match's value is read *before* its own change
    is folded in, so match ``t`` sees only changes into matches ``t-1`` and
    earlier; and a match whose XI is empty — a future probe row, a club-week
    with no ``starts`` recorded — is scored but never becomes a comparison
    point, so a hole in the data cannot manufacture eleven changes.
    """
    xi: dict[tuple, set] = {}
    for s, when, c, st in zip(spell, kt, code, starts):
        if not s or pd.isna(when):
            continue
        bucket = xi.setdefault((s, when), set())
        if st == 1:
            bucket.add(c)
    churn: dict[tuple, float] = {}
    per_spell: dict[str, list] = {}
    for key in sorted(xi, key=lambda k: (k[0], k[1])):
        per_spell.setdefault(key[0], []).append(key[1])
    for s, whens in per_spell.items():
        recent: list[float] = []
        prev: set | None = None
        for when in whens:
            window = recent[-XI_CHURN_WINDOW:]
            churn[(s, when)] = (sum(window) / len(window) if window
                                else float("nan"))
            now = xi[(s, when)]
            if not now:
                continue
            if prev:
                recent.append(float(len(now - prev)))
            prev = now
    return pd.Series(
        [churn.get((s, when), float("nan")) if s and pd.notna(when)
         else float("nan") for s, when in zip(spell, kt)],
        index=spell.index, dtype="float64")


def add_rotation_priors(df: pd.DataFrame,
                        tenures: pd.DataFrame | None = None) -> pd.DataFrame:
    """v8a F1: rotation signals scoped to the *manager*, not the season.

    ``tenure_start_share``
        the player's share of the club's matches under this manager that he
        started, shrunk toward the club's own mean start share over the same
        matches with a :data:`TENURE_SHRINK_K` prior. NaN before the spell has
        any earlier match at all.
    ``manager_tenure_matches``
        club matches the manager has taken before this one, capped at
        :data:`MAX_TENURE_MATCHES`. Zero on his first.
    ``xi_churn_r5``
        the club's roulette index — see :func:`_xi_churn`.
    ``started_last_match``
        did the player start his own previous match. Read off his own rows
        rather than the club's calendar, because a player with no row for a
        match was not in the squad and "the club's previous match" is only
        ever a proxy for the question the trees want: was he in the XI last
        time out. Its interaction with the churn index is the point — high
        churn *and* started-last-match is elevated rest risk.

    Every window is strictly past, by construction rather than by ``shift``:
    a cumulative sum minus the row's own contribution cannot leak whatever a
    double gameweek does to the sort order. ``tenures`` of ``None`` scopes
    every window to the club's season instead (see
    :func:`gaffer.data.managers.spell_keys`), which is the documented
    degradation and not an error.
    """
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in df.columns]
    out = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    if not {"code", "team_code", "starts", "season_idx"} <= set(out.columns):
        for col in ROTATION_PRIOR_FEATURES:
            out[col] = float("nan")
        return out

    kt = (pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
          if "kickoff_time" in out.columns
          else pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]"))
    spell = spell_keys(out["team_code"], kt, out["season_idx"], tenures)
    starts = pd.to_numeric(out["starts"], errors="coerce")
    code = out["code"]

    # The player's own record under the spell, this match excluded.
    seen = starts.notna().astype("float64")
    own_n = seen.groupby([code, spell]).cumsum() - seen
    own_starts = (starts.fillna(0.0).groupby([code, spell]).cumsum()
                  - starts.fillna(0.0))

    # The club's record under the spell, this *match* excluded — accumulated
    # per (spell, kickoff) rather than per row, because a row's own teammates
    # play the same match and a row-wise cumsum would read them.
    match = pd.DataFrame({"spell": spell, "when": kt,
                          "starts": starts.fillna(0.0), "rows": seen})
    agg = (match.groupby(["spell", "when"], as_index=False, dropna=False)
           [["starts", "rows"]].sum().sort_values(["spell", "when"]))
    g = agg.groupby("spell")
    before_starts = g["starts"].cumsum() - agg["starts"]
    before_rows = g["rows"].cumsum() - agg["rows"]
    club_share = before_starts / before_rows.where(before_rows > 0)
    played_before = g.cumcount().astype("float64")
    share_of = dict(zip(zip(agg["spell"], agg["when"]), club_share))
    count_of = dict(zip(zip(agg["spell"], agg["when"]), played_before))
    keys = list(zip(spell, kt))
    prior = pd.Series([share_of.get(k, float("nan")) for k in keys],
                      index=out.index, dtype="float64")
    tenure_matches = pd.Series([count_of.get(k, float("nan")) for k in keys],
                               index=out.index, dtype="float64")

    feats = {
        "tenure_start_share": ((own_starts + TENURE_SHRINK_K * prior)
                               / (own_n + TENURE_SHRINK_K)),
        "manager_tenure_matches": tenure_matches.clip(0.0,
                                                      MAX_TENURE_MATCHES),
        "xi_churn_r5": _xi_churn(spell, kt, code, starts),
        "started_last_match": starts.groupby(code).shift(1),
    }
    for col, values in feats.items():
        out[col] = values.astype("float64")
    return out
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_engineer_v8a.py`
  Expected: `8 passed`.

- [ ] **Commit.**

```bash
git add src/gaffer/features/engineer.py tests/test_engineer_v8a.py && git commit -m "$(cat <<'EOF'
feat: F1 rotation-prior training builder over manager spells

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — F1: the serve-time counterpart and the wiring

**Files:**
- Modify `src/gaffer/features/engineer.py` (`latest_rotation_priors`; `build_prediction_frame`; `feature_columns`)
- Modify `src/gaffer/models/train.py` (`load_training_frame`, ~line 243)
- Modify `tests/test_engineer_v8a.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_engineer_v8a.py`:

```python
# --- serve side ------------------------------------------------------------

from gaffer.features.engineer import (build_prediction_frame,  # noqa: E402
                                      feature_columns,
                                      latest_rotation_priors)


def _future(gws=(7, 8), team=3) -> pd.DataFrame:
    rows = []
    for i, gw in enumerate(gws):
        when = pd.Timestamp("2023-09-16", tz="UTC") + pd.Timedelta(days=7 * i)
        for code in (1, 2):
            rows.append({"code": code, "season_idx": 1, "gw": gw,
                         "team_code": team, "opp_code": 4, "was_home": True,
                         "position": "MID",
                         "kickoff_time": when.isoformat()})
    return pd.DataFrame(rows)


def test_the_serve_state_is_one_row_per_player():
    out = latest_rotation_priors(_frame(), _tenures())
    assert sorted(out.index) == [1, 2]
    for col in ROTATION_PRIOR_FEATURES:
        assert col in out.columns


def test_the_serve_state_counts_the_last_played_match():
    """As-of-end, like every other ``latest_*``: six matches have been played
    under the two spells, three of them under the current one."""
    out = latest_rotation_priors(_frame(), _tenures())
    assert out.loc[1, "manager_tenure_matches"] == 3.0
    assert out.loc[1, "started_last_match"] == 1.0


def test_the_prediction_frame_carries_every_prior_feature():
    out = build_prediction_frame(_frame(), _future(), tenures=_tenures())
    for col in ROTATION_PRIOR_FEATURES:
        assert col in out.columns
    assert out["manager_tenure_matches"].notna().all()


def test_a_change_of_manager_blanks_the_share_it_no_longer_describes():
    """The state was measured under the manager in post at the last match.
    A future fixture past a change describes a squad nobody has picked yet."""
    later = _tenures().copy()
    later.loc[len(later)] = {"team_code": 3, "club": "Arsenal",
                             "manager": "C",
                             "start_date": pd.Timestamp("2023-09-10",
                                                        tz="UTC"),
                             "end_date": pd.NaT}
    later.loc[1, "end_date"] = pd.Timestamp("2023-09-10", tz="UTC")
    out = build_prediction_frame(_frame(), _future(), tenures=later)
    assert out["tenure_start_share"].isna().all()
    assert (out["manager_tenure_matches"] == 0.0).all()


def test_the_prior_features_are_in_the_canonical_strip_list():
    cols = feature_columns()
    for col in ROTATION_PRIOR_FEATURES:
        assert col in cols
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_engineer_v8a.py -k serve or prediction`
  Expected: `ImportError: cannot import name 'latest_rotation_priors'`.

- [ ] **Write the implementation.** In `src/gaffer/features/engineer.py`, add `latest_rotation_priors` immediately after `add_rotation_priors`:

```python
def latest_rotation_priors(hist: pd.DataFrame,
                           tenures: pd.DataFrame | None = None,
                           when=None) -> pd.DataFrame:
    """Each player's as-of-today rotation-prior state, indexed by ``code``.

    Built by appending one *probe* row per player to history and running
    :func:`add_rotation_priors` over the lot, rather than by restating the
    arithmetic with the exclusions turned off. The probe is a match that has
    not been played — no ``starts``, a kickoff one day past the end of
    history — so "strictly before the probe" is exactly "all of history",
    which is the as-of-end contract every other ``latest_*`` keeps. Sharing
    the code path is what makes train/serve skew impossible here rather than
    merely unlikely.

    ``_prior_spell`` rides along so the caller can tell whether the state
    belongs to the manager who will pick the future team;
    :func:`build_prediction_frame` blanks what a change of manager invalidates.
    """
    cols = ["code"] + ROTATION_PRIOR_FEATURES + ["_prior_spell"]
    if not {"code", "team_code", "season_idx"} <= set(hist.columns):
        return pd.DataFrame(columns=cols).set_index("code")
    sort_cols = [c for c in ("code", "season_idx", "gw", "kickoff_time")
                 if c in hist.columns]
    h = hist.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    kt = (pd.to_datetime(h["kickoff_time"], errors="coerce", utc=True)
          if "kickoff_time" in h.columns
          else pd.Series(pd.NaT, index=h.index, dtype="datetime64[ns, UTC]"))
    stamp = when if when is not None else (
        kt.max() + pd.Timedelta(days=1) if kt.notna().any() else pd.NaT)
    tail = h.groupby("code", sort=False).tail(1)
    probe = pd.DataFrame({
        "code": tail["code"].to_numpy(),
        "team_code": tail["team_code"].to_numpy(),
        "season_idx": tail["season_idx"].to_numpy(),
        "gw": pd.to_numeric(tail["gw"], errors="coerce").to_numpy(),
        "kickoff_time": stamp,
        "starts": float("nan")})
    both = add_rotation_priors(
        pd.concat([h.assign(_probe=False), probe.assign(_probe=True)],
                  ignore_index=True), tenures)
    out = both[both["_probe"].fillna(False).astype(bool)].copy()
    out["_prior_spell"] = spell_keys(out["team_code"], stamp,
                                     out["season_idx"], tenures).to_numpy()
    return out[cols].groupby("code", sort=False).tail(1).set_index("code")
```

- [ ] **Wire the serve side.** In `build_prediction_frame`, add the parameter (after `cups`) and the block. The signature line becomes:

```python
def build_prediction_frame(hist: pd.DataFrame, future: pd.DataFrame,
                           stats: list[str] = ROLL_STATS,
                           windows: list[int] = WINDOWS,
                           elo: pd.DataFrame | None = None,
                           elo_final: dict | None = None,
                           understat_team: pd.DataFrame | None = None,
                           cups: pd.DataFrame | None = None,
                           tenures: pd.DataFrame | None = None
                           ) -> pd.DataFrame:
```

Immediately after the `rot`/`stale` block (the two lines ending
`rot.loc[stale, "season_start_share"] = float("nan")`), insert:

```python
    # v8a F1. The asset is loaded here rather than passed by every caller:
    # ``advise`` builds this frame and must not have to know about a file it
    # is allowed to be missing. ``None`` is the club-season degradation.
    if tenures is None:
        from gaffer.data.managers import load_manager_tenures
        tenures = load_manager_tenures()
    pri = (latest_rotation_priors(hist, tenures)
           .reindex(out["code"]).reset_index(drop=True))
    now_spell = spell_keys(out["team_code"], out.get("kickoff_time"),
                           out["season_idx"], tenures)
    # A state measured under the outgoing manager is not evidence about the
    # incoming one's team sheet: the share and the roulette index describe a
    # squad nobody has picked yet, and the counter genuinely restarts at zero.
    fresh_boss = pri["_prior_spell"].to_numpy() != now_spell.to_numpy()
    pri.loc[fresh_boss, "tenure_start_share"] = float("nan")
    pri.loc[fresh_boss, "xi_churn_r5"] = float("nan")
    pri.loc[fresh_boss, "manager_tenure_matches"] = 0.0
    pri = pri.drop(columns=["_prior_spell"])
```

and add `pri` to the concatenated block — the `frame = pd.concat([...])` call becomes:

```python
    frame = pd.concat(
        [out.drop(columns=list(latest.columns) + ROTATION_FEATURES
                  + ROTATION_PRIOR_FEATURES
                  + list(us.columns) + SHRUNK_FEATURES
                  + SHRUNK_MODE_FEATURES, errors="ignore"),
         latest.reindex(out["code"]).reset_index(drop=True),
         rot.drop(columns=["_rot_season_idx"]),
         pri,
         us.reindex(out["code"]).reset_index(drop=True),
         shrunk.reindex(out["code"]).reset_index(drop=True),
         modes.reindex(out["code"]).reset_index(drop=True)], axis=1)
```

- [ ] **Add them to the canonical strip list.** In `feature_columns`, the return becomes:

```python
    return (cols + ["team_elo", "opp_elo", "elo_diff", "home", "days_rest",
                    "pen_taker", "setpiece_taker"] + ROTATION_FEATURES
            + ROTATION_PRIOR_FEATURES
            + CONGESTION_FEATURES
            + understat_feature_columns() + TEAM_US_FEATURES
            + SHRUNK_FEATURES + SHRUNK_MODE_FEATURES)
```

- [ ] **Wire the training side.** In `src/gaffer/models/train.py`, extend the engineer import block with `ROTATION_PRIOR_FEATURES` and `add_rotation_priors`:

```python
from gaffer.features.engineer import (ROTATION_FEATURES,
                                      ROTATION_PRIOR_FEATURES, US_STATS,
                                      add_congestion, add_context,
                                      add_player_rolling, add_rotation,
                                      add_rotation_priors,
                                      add_setpiece, add_shrunken_modes,
                                      add_shrunken_rates,
                                      add_understat_rolling,
                                      add_understat_team_rolling,
                                      merge_understat_team)
```

and add the builder to the chain, immediately after `df = add_rotation(df)`:

```python
    df = add_rotation_priors(df, manager_tenures())
```

with the shared reader beside `cup_matches` (after it, ~line 178):

```python
def manager_tenures() -> pd.DataFrame | None:
    """The committed tenure asset, shared by training and by ``advise``.

    Same contract as :func:`cup_matches`: both sides of the train/serve
    boundary read it through one function, so neither can end up with a
    differently-scoped rotation window.
    """
    from gaffer.data.managers import load_manager_tenures

    return load_manager_tenures()
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_engineer_v8a.py tests/test_engineer.py tests/test_train.py`
  Expected: green — 13 passed in the new file, and no regression in the two existing suites.

- [ ] **Verify the training frame really carries them** (reads real data, writes nothing):

```bash
uv run python -c "
from gaffer.models.train import load_training_frame
from gaffer.features.engineer import ROTATION_PRIOR_FEATURES
df, _, _ = load_training_frame()
print(df[ROTATION_PRIOR_FEATURES].notna().mean().round(3).to_dict())"
```

Expected: a coverage fraction per column, all well above 0.5 except at season openings; nothing NaN everywhere. A column at 0.0 means the builder never fired — stop and fix before proceeding.

- [ ] **Commit.**

```bash
git add src/gaffer/features/engineer.py src/gaffer/models/train.py tests/test_engineer_v8a.py && git commit -m "$(cat <<'EOF'
feat: F1 serve-time rotation priors and the training-frame wiring

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

Note: `MINUTES_FEATURES` is deliberately **not** touched here. The columns exist in both frames and in `feature_columns()`, and cost the shipped model nothing until Task 17 adopts whichever arms G1 keeps.

---

## Task 5 — F2: league-only congestion as a separable arm

**Files:**
- Modify `src/gaffer/features/engineer.py` (`add_congestion`, `latest_congestion`, `build_prediction_frame`, `feature_columns`)
- Modify `src/gaffer/models/train.py` (`load_training_frame`)
- Modify `tests/test_engineer_v8a.py` (append)

D2's requirement is that arm A (league-only) and arm B (cup-inclusive) be *independently attributable*. The cheapest way to get that is one prefix argument: the two variants become two sets of columns that coexist in one frame, so the gate driver can hand either, both or neither to the model without rebuilding anything.

- [ ] **Write the failing test.** Append to `tests/test_engineer_v8a.py`:

```python
# --- F2: the two congestion arms ------------------------------------------

from gaffer.features.engineer import (CONGESTION_FEATURES,  # noqa: E402
                                      LEAGUE_CONGESTION_FEATURES,
                                      add_congestion)


def _cups() -> pd.DataFrame:
    return pd.DataFrame({"team_code": [3],
                         "date": [pd.Timestamp("2023-08-09", tz="UTC")]})


def test_the_league_arm_has_its_own_column_names():
    assert LEAGUE_CONGESTION_FEATURES == ["lg_days_since_last_match",
                                          "lg_days_to_next_match",
                                          "lg_matches_last_14d"]


def test_the_two_arms_coexist_in_one_frame():
    """Both variants on one frame is what makes them separable arms: the
    driver picks columns, it does not rebuild the features."""
    out = add_congestion(_frame(), _cups())
    out = add_congestion(out, None, prefix="lg_")
    for col in CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES:
        assert col in out.columns


def test_the_cup_tie_lands_only_in_the_cup_inclusive_arm():
    """The whole of D2: with cup ties in, a club's midweek tie raises the
    load; league-only, it cannot, so the arm carries no season indicator."""
    out = add_congestion(_frame(), _cups())
    out = add_congestion(out, None, prefix="lg_")
    row = out[(out["code"] == 1) & (out["gw"] == 2)].iloc[0]
    assert row["matches_last_14d"] > row["lg_matches_last_14d"]


def test_the_league_arm_is_the_no_cups_call_renamed():
    plain = add_congestion(_frame(), None)
    prefixed = add_congestion(_frame(), None, prefix="lg_")
    for a, b in zip(CONGESTION_FEATURES, LEAGUE_CONGESTION_FEATURES):
        pd.testing.assert_series_equal(plain[a], prefixed[b],
                                       check_names=False)


def test_a_frame_without_kickoffs_still_gets_prefixed_columns():
    out = add_congestion(_frame().drop(columns=["kickoff_time"]), None,
                         prefix="lg_")
    for col in LEAGUE_CONGESTION_FEATURES:
        assert col in out.columns and out[col].isna().all()


def test_the_prediction_frame_carries_both_arms():
    out = build_prediction_frame(_frame(), _future(), cups=_cups(),
                                 tenures=_tenures())
    for col in CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES:
        assert col in out.columns


def test_both_arms_are_in_the_canonical_strip_list():
    cols = feature_columns()
    for col in CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES:
        assert col in cols
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_engineer_v8a.py -k congestion`
  Expected: `ImportError: cannot import name 'LEAGUE_CONGESTION_FEATURES'`.

- [ ] **Write the implementation.** In `src/gaffer/features/engineer.py`, add below `MAX_CONGESTION_GAP`'s docstring:

```python
LEAGUE_CONGESTION_PREFIX = "lg_"
LEAGUE_CONGESTION_FEATURES = [LEAGUE_CONGESTION_PREFIX + c
                              for c in CONGESTION_FEATURES]
"""v8a F2 arm A: the same three numbers, league fixtures only.

v5's gate N1 withdrew :data:`CONGESTION_FEATURES` because the cup archive
began in 2025-26 and the feature was therefore partly a season indicator
(``models/train.py``'s ``MINUTES_FEATURES`` docstring records the numbers).
League kickoffs are 100% populated from 2022-23 onward, so this variant has no
confound to be accused of. It carries its own names rather than replacing the
originals so that both can sit in one frame and the gate can attribute the
difference to one arm at a time.
"""
```

Change `add_congestion`'s signature and the two places it names its outputs:

```python
def add_congestion(df: pd.DataFrame,
                   cups: pd.DataFrame | None = None,
                   prefix: str = "") -> pd.DataFrame:
```

Append to its docstring, before the closing quotes:

```
    ``prefix`` renames all three outputs, which is how v8a's two arms coexist
    in one frame: ``prefix=""`` with a cup frame is arm B, ``prefix="lg_"``
    with ``cups=None`` is arm A, and calling it twice adds six columns rather
    than overwriting three.
```

and in the body:

```python
    out = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)
    names = [prefix + c for c in CONGESTION_FEATURES]
    if "kickoff_time" not in out.columns:
        for col in names:
            out[col] = float("nan")
        return out
    kt = pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
    code = out["code"]
    prev = kt.groupby(code).shift(1)
    nxt = kt.groupby(code).shift(-1)
    out[names[0]] = ((kt - prev).dt.days
                     .clip(0, MAX_CONGESTION_GAP).astype("float64"))
    out[names[1]] = ((nxt - kt).dt.days
                     .clip(0, MAX_CONGESTION_GAP).astype("float64"))
    out[names[2]] = _recent_load(out, kt, cups)
    return out
```

and give `latest_congestion` the same pass-through:

```python
def latest_congestion(hist: pd.DataFrame, future: pd.DataFrame,
                      cups: pd.DataFrame | None = None,
                      prefix: str = "") -> pd.DataFrame:
```

with its body's one call becoming:

```python
    both = add_congestion(pd.concat([hist, future], ignore_index=True), cups,
                          prefix)
```

- [ ] **Wire the serve side.** In `build_prediction_frame`, replace the congestion block:

```python
    # Congestion is per-fixture, not a broadcast: each future row has its own
    # date, so it is rebuilt over history+future rather than tailed. Both v8a
    # arms are rebuilt, so the two candidate column sets are populated
    # identically in training and at serve time whichever the model uses.
    cong = latest_congestion(hist, future, cups)[CONGESTION_FEATURES]
    lg = latest_congestion(hist, future, None,
                           LEAGUE_CONGESTION_PREFIX)[LEAGUE_CONGESTION_FEATURES]
    out = out.drop(columns=CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES,
                   errors="ignore")
    out = pd.concat([out, cong.reset_index(drop=True),
                     lg.reset_index(drop=True)], axis=1)
```

- [ ] **Add them to the strip list.** In `feature_columns`, `+ CONGESTION_FEATURES` becomes:

```python
            + CONGESTION_FEATURES + LEAGUE_CONGESTION_FEATURES
```

- [ ] **Wire the training side.** In `src/gaffer/models/train.py`, add `LEAGUE_CONGESTION_FEATURES` and `LEAGUE_CONGESTION_PREFIX` to the engineer import, and put the second call straight after the first in `load_training_frame`:

```python
    df = add_congestion(df, cup_matches())
    df = add_congestion(df, None, prefix=LEAGUE_CONGESTION_PREFIX)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_engineer_v8a.py tests/test_engineer.py tests/test_train.py`
  Expected: green; 20 passed in the new file.

- [ ] **Commit.**

```bash
git add src/gaffer/features/engineer.py src/gaffer/models/train.py tests/test_engineer_v8a.py && git commit -m "$(cat <<'EOF'
feat: F2 league-only congestion as a separately attributable arm

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — G1: the per-arm ablation driver

**Files:**
- Create `scripts/v8a_arms.py`
- Create `tests/test_v8a_driver.py`

The mechanism is `scripts/z1_arms.py`'s exactly: memoise the expensive frame, mutate one module-level name per arm, run the harness, print one `*_ARM_DONE` line per arm. Here the name is `train.MINUTES_FEATURES`, which `train_all` reads as a module global at call time — so an arm is a feature list and nothing in the shipped code moves.

- [ ] **Write the failing test.** Create `tests/test_v8a_driver.py`:

```python
"""The G1 driver's arithmetic and its hygiene.

The run itself is hours long and the orchestrator's job (CONVENTIONS.md §7).
What is testable here is the arm table, the verdict rule and the promise the
driver makes to the rest of the repo: it must not leave ``MINUTES_FEATURES``
mutated behind it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path("scripts/v8a_arms.py")


def _driver():
    """Import the script without running its ``main``."""
    spec = importlib.util.spec_from_file_location("v8a_arms", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_candidate_is_an_arm_of_its_own():
    """G1 ablates each F1 feature individually and each F2 variant as a
    block. Bundling two F1 features into one arm would make a withdrawal
    impossible to target."""
    from gaffer.features.engineer import (LEAGUE_CONGESTION_FEATURES,
                                          ROTATION_PRIOR_FEATURES,
                                          CONGESTION_FEATURES)

    arms = _driver().ARMS
    assert arms["baseline"] == []
    for col in ROTATION_PRIOR_FEATURES:
        assert arms[f"f1_{col}"] == [col]
    assert arms["f2_league"] == LEAGUE_CONGESTION_FEATURES
    assert arms["f2_cups"] == CONGESTION_FEATURES


def test_the_arm_feature_list_is_the_baseline_plus_the_arm():
    from gaffer.models.train import MINUTES_FEATURES

    mod = _driver()
    cols = mod.arm_features("f2_league")
    assert cols[:len(MINUTES_FEATURES)] == list(MINUTES_FEATURES)
    assert cols[len(MINUTES_FEATURES):] == mod.ARMS["f2_league"]


def test_the_driver_does_not_leave_minutes_features_mutated():
    import gaffer.models.train as tr

    before = list(tr.MINUTES_FEATURES)
    mod = _driver()
    mod.arm_features("f1_xi_churn_r5")
    assert list(tr.MINUTES_FEATURES) == before


@pytest.mark.parametrize(
    "zeros,haulers,all_,expect",
    [(1.060, 5.140, 1.980, "keep"),        # clearly better zeros, no cost
     (1.066, 5.140, 1.980, "withdraw"),    # under the 0.005 bar
     (1.050, 5.150, 1.980, "withdraw"),    # haulers regressed too far
     (1.050, 5.140, 1.992, "withdraw")])   # all-RMSE regressed too far
def test_the_verdict_rule_is_the_pre_registered_one(zeros, haulers, all_,
                                                    expect):
    mod = _driver()
    base = {"zeros": 1.070, "haulers": 5.145, "all": 1.986}
    arm = {"zeros": zeros, "haulers": haulers, "all": all_}
    assert mod.verdict(base, arm)["decision"] == expect


def test_a_tie_withdraws():
    """v5 discipline: an arm that measured level did not earn its column."""
    mod = _driver()
    base = {"zeros": 1.070, "haulers": 5.145, "all": 1.986}
    assert mod.verdict(base, dict(base))["decision"] == "withdraw"
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_v8a_driver.py`
  Expected: `FileNotFoundError` / `spec_from_file_location` returning `None` — the script does not exist.

- [ ] **Write the driver.** Create `scripts/v8a_arms.py`:

```python
"""Gate G1: the v8a feature arms on the 2024-25 walk-forward benchmark.

One run of ``evaluate_benchmark`` per arm over one memoised training frame.
An arm is a *feature list*: ``train.MINUTES_FEATURES`` is read as a module
global by ``train_all``, so setting it is the whole of the intervention and
nothing in the shipped code moves. The frame is memoised because it is the
expensive half of the run and cannot differ between arms by construction; it
hands back copies, so an arm that mutates its frame cannot poison the next.

Run it, watch it, read the verdicts::

    caffeinate -i nohup .venv/bin/python scripts/v8a_arms.py \\
        > logs/v8a_arms.log 2>&1 &
    grep -e V8A_ARM_DONE -e V8A_VERDICT logs/v8a_arms.log

The pre-registered rule (v8a spec §6, G1), each arm against the *baseline arm
of this same run* rather than against a banked number: KEEP iff zeros RMSE
improves by at least :data:`ZEROS_MIN_GAIN` AND neither haulers RMSE nor
all-stratum RMSE regresses by more than :data:`GUARD_TOLERANCE`. Ties and
marginals withdraw. This script prints the comparison; the shipping decision
is the orchestrator's, and Task 17 of the plan is where a kept arm lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import gaffer.evaluation as ev
from gaffer.features.engineer import (CONGESTION_FEATURES,
                                      LEAGUE_CONGESTION_FEATURES,
                                      ROTATION_PRIOR_FEATURES)
from gaffer.models import train as tr

ZEROS_MIN_GAIN = 0.005
GUARD_TOLERANCE = 0.005

ARMS: dict[str, list[str]] = {
    "baseline": [],
    **{f"f1_{col}": [col] for col in ROTATION_PRIOR_FEATURES},
    "f2_league": list(LEAGUE_CONGESTION_FEATURES),
    "f2_cups": list(CONGESTION_FEATURES),
}
"""One arm per candidate. F1's four features are ablated individually because
a withdrawal has to be targetable; F2's two variants are blocks because
"congestion" is one claim measured two ways.

``baseline`` is the control arm convention 3 requires: same code, same batch,
same frame, no candidate columns.
"""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    """The feature list this arm trains the minutes model on.

    Reads ``tr.MINUTES_FEATURES`` afresh rather than closing over it, and
    returns a new list, so calling this never mutates the shipped constant.
    """
    return list(tr.MINUTES_FEATURES) + list(ARMS[name])


def scores(payload: dict) -> dict:
    """The three numbers the gate rule reads, off a benchmark payload."""
    table = payload["stratified"]["all"]
    return {"zeros": table["zeros"]["rmse"],
            "haulers": table["haulers"]["rmse"],
            "all": table["all"]["rmse"],
            "zeros_n": table["zeros"]["n"]}


def verdict(base: dict, arm: dict) -> dict:
    """The pre-registered rule, applied to one arm against the control."""
    gain = base["zeros"] - arm["zeros"]
    haulers_cost = arm["haulers"] - base["haulers"]
    all_cost = arm["all"] - base["all"]
    keep = (gain >= ZEROS_MIN_GAIN
            and haulers_cost <= GUARD_TOLERANCE
            and all_cost <= GUARD_TOLERANCE)
    return {"zeros_gain": round(gain, 4),
            "haulers_cost": round(haulers_cost, 4),
            "all_cost": round(all_cost, 4),
            "decision": "keep" if keep else "withdraw"}


def main() -> None:
    tr.load_training_frame = _memoised
    shipped = list(tr.MINUTES_FEATURES)
    results: dict[str, dict] = {}
    try:
        for name in ARMS:
            tr.MINUTES_FEATURES = arm_features(name)
            payload = ev.evaluate_benchmark()
            results[name] = scores(payload)
            print("V8A_ARM_DONE", name, json.dumps(results[name]), flush=True)
    finally:
        tr.MINUTES_FEATURES = shipped
        tr.load_training_frame = _real_load

    base = results["baseline"]
    verdicts = {name: verdict(base, arm)
                for name, arm in results.items() if name != "baseline"}
    for name, v in verdicts.items():
        print("V8A_VERDICT", name, json.dumps(v), flush=True)
    print("V8A_KEEP", json.dumps(
        [n for n, v in verdicts.items() if v["decision"] == "keep"]),
        flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v8a_arms.json").write_text(
        json.dumps({"arms": results, "verdicts": verdicts}, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_v8a_driver.py`
  Expected: `9 passed`. (Importing the script must not start a benchmark — that is what the `main()` guard buys, and the test relies on it.)

- [ ] **Do not run the driver.** G1 is the orchestrator's (CONVENTIONS.md §7). Task 18 lists the command.

- [ ] **Commit.**

```bash
git add scripts/v8a_arms.py tests/test_v8a_driver.py && git commit -m "$(cat <<'EOF'
feat: the G1 per-arm ablation driver for the v8a feature arms

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — F3: P(start) head metrics in `evaluate_current`

**Files:**
- Modify `src/gaffer/evaluation.py` (`evaluate_current`, plus one helper)
- Create `tests/test_evaluation_v8a.py`

- [ ] **Write the failing test.** Create `tests/test_evaluation_v8a.py`:

```python
"""F3: the trichotomy made legible to the measurement layer.

Zeros RMSE says an arm helped. It does not say *where* — whether P(start)
sharpened or the points model absorbed the change downstream. These readouts
are what make every G1 arm's effect attributable at the mode level.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.evaluation import start_truth


def test_the_start_truth_prefers_the_recorded_starts_column():
    hold = pd.DataFrame({"starts": [1.0, 0.0, 1.0], "minutes": [90, 20, 5]})
    assert list(start_truth(hold)) == [1.0, 0.0, 1.0]


def test_a_season_without_starts_falls_back_to_the_sixty_minute_rule():
    """``starts`` predates part of the archive. A hole there would blank the
    metric for a whole season, and 60+ minutes is a start in all but a
    handful of cases — the same inference ``_mode_rate_parts`` makes."""
    hold = pd.DataFrame({"minutes": [90.0, 20.0, 61.0]})
    assert list(start_truth(hold)) == [1.0, 0.0, 1.0]


def test_a_missing_start_is_filled_from_the_minutes_row_by_row():
    hold = pd.DataFrame({"starts": [1.0, np.nan, np.nan],
                         "minutes": [90.0, 90.0, 10.0]})
    assert list(start_truth(hold)) == [1.0, 1.0, 0.0]


def test_the_head_block_names_p_start(monkeypatch):
    """``evaluate_current`` is a full refit and far too slow for a unit test,
    so the contract asserted here is the source's: the heads block scores the
    mode probability, not another function of p_play."""
    import inspect

    from gaffer.evaluation import evaluate_current

    src = inspect.getsource(evaluate_current)
    assert 'predict_modes(hold)' in src
    assert '"p_start": head_metrics(' in src
    assert 'start_truth(hold)' in src
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_evaluation_v8a.py`
  Expected: `ImportError: cannot import name 'start_truth' from 'gaffer.evaluation'`.

- [ ] **Write the implementation.** In `src/gaffer/evaluation.py`, add the helper immediately above `evaluate_current`:

```python
def start_truth(hold: pd.DataFrame) -> pd.Series:
    """Did he start, as a 0/1 float, one value per row.

    ``starts`` where the feed recorded it, and ``minutes >= 60`` where it did
    not — the same inference :func:`gaffer.features.engineer._mode_rate_parts`
    makes for the shrunken start rate, and for the same reason: the column
    postdates part of the archive, and a hole would blank the metric for a
    whole season rather than for the rows that are actually unknown.
    """
    mins = pd.to_numeric(hold.get("minutes"), errors="coerce").fillna(0.0)
    inferred = (mins >= STARTER_MINUTES).astype("float64")
    if "starts" not in hold.columns:
        return inferred
    return (pd.to_numeric(hold["starts"], errors="coerce").fillna(inferred)
            .astype("float64"))
```

In `evaluate_current`, replace the single `mp = models["minutes"].predict(hold)` line with:

```python
    mp = models["minutes"].predict(hold)
    # The trichotomy itself, not another function of it: p_play is a sum of
    # two modes, and an arm that sharpens the start/cameo split while leaving
    # the sum alone is invisible in p_play's log loss (v8a spec §3).
    modes = models["minutes"].predict_modes(hold)
```

and add one entry to the `"heads"` block, after `"p60"`:

```python
            "p_start": head_metrics(modes["p_start"], start_truth(hold)),
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_evaluation_v8a.py tests/test_evaluation.py`
  Expected: green; 4 passed in the new file.

- [ ] **Commit.**

```bash
git add src/gaffer/evaluation.py tests/test_evaluation_v8a.py && git commit -m "$(cat <<'EOF'
feat: F3 P(start) head metrics in the current-season evaluation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — F3: a per-stratum P(start) reliability cut in `diagnose-zeros`

**Files:**
- Modify `src/gaffer/zeros_diagnostic.py` (`start_reliability`, `zeros_report`, `format_diagnostic`, `_holdout`)
- Modify `tests/test_evaluation_v8a.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_evaluation_v8a.py`:

```python
# --- the zeros diagnostic's mode cut ---------------------------------------

from gaffer.zeros_diagnostic import (start_reliability,  # noqa: E402
                                     format_diagnostic, zeros_report)


def _scored() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    n = 200
    p = rng.uniform(0.0, 1.0, n)
    return pd.DataFrame({
        "code": np.arange(n), "gw": 10,
        "ep": p * 4.0, "total_points": (rng.uniform(size=n) < p) * 5.0,
        "minutes": (rng.uniform(size=n) < p) * 90.0,
        "starts": (rng.uniform(size=n) < p).astype(float),
        "season_start_share": rng.uniform(size=n),
        "minutes_r5": rng.uniform(size=n) * 90.0,
        "p_dnp": 1.0 - p, "p_start": p})


def test_the_curve_reports_predicted_against_observed_per_bin():
    out = start_reliability(_scored())
    assert out and all({"decile", "n", "pred", "obs"} <= set(r) for r in out)
    assert all(0.0 <= r["pred"] <= 1.0 for r in out)


def test_a_frame_without_the_mode_probability_reports_no_curve():
    assert start_reliability(_scored().drop(columns=["p_start"])) == []


def test_every_stratum_carries_its_own_curve():
    payload = zeros_report(_scored())
    assert set(payload["start_reliability"]) == set(payload["strata"]) - {
        "flagged"}


def test_the_printed_report_names_the_start_curve():
    payload = zeros_report(_scored())
    payload["run_at"], payload["git_sha"] = "now", "abc"
    text = format_diagnostic(payload)
    assert "p_start calibration" in text
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_evaluation_v8a.py -k start_reliability`
  Expected: `ImportError: cannot import name 'start_reliability'`.

- [ ] **Write the implementation.** In `src/gaffer/zeros_diagnostic.py`, add after `dnp_reliability`:

```python
def start_reliability(frame: pd.DataFrame,
                      bins: int = DNP_DECILES) -> list[dict]:
    """Predicted vs observed start rate per ``p_start`` decile.

    :func:`dnp_reliability`'s twin at the other end of the trichotomy, and the
    cut v8a's F1/F2 arms are actually about: a rotation feature earns its
    column by moving *which* players the model expects to start, and a pooled
    ``p_play`` curve averages that away. Read per stratum, it says whether an
    arm helped the fringe, the regulars or nobody.

    ``starts`` where the feed has it, ``minutes >= 60`` where it does not —
    the same inference :func:`gaffer.evaluation.start_truth` makes. Empty
    deciles are omitted, matching every other reliability curve here.
    """
    if "p_start" not in frame.columns or "minutes" not in frame.columns:
        return []
    from gaffer.evaluation import start_truth

    p = pd.to_numeric(frame["p_start"], errors="coerce").to_numpy(dtype=float)
    y = start_truth(frame).to_numpy(dtype=float)
    ok = np.isfinite(p) & np.isfinite(y)
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
```

In `zeros_report`, add the per-stratum cut:

```python
def zeros_report(scored: pd.DataFrame) -> dict:
    """The whole decomposition: overall, per stratum, plus the two curves."""
    parts = stratify(scored)
    strata = {name: _error(part) for name, part in parts.items()}
    strata["flagged"] = {"n": 0, "rmse": 0.0, "mae": 0.0, "mean_ep": 0.0,
                         "note": FLAGGED_NOTE}
    return {
        "overall": _error(scored),
        "strata": strata,
        "dnp_reliability": dnp_reliability(scored),
        # v8a F3: the same six sub-populations, read at the start mode. A
        # stratum whose zeros RMSE moved and whose start curve did not is an
        # arm that helped somewhere other than where it claimed to.
        "start_reliability": {name: start_reliability(part)
                              for name, part in parts.items()},
        "fringe_share": FRINGE_SHARE,
        "cold_start_gws": COLD_START_GWS,
    }
```

In `format_diagnostic`, append before the `return`:

```python
    lines.append("-- p_start calibration (per stratum, all rows)")
    for name, curve in payload.get("start_reliability", {}).items():
        if not curve:
            continue
        lines.append(f"   {name}")
        for row in curve:
            lines.append(f"     decile {row['decile']}  "
                         f"pred {row['pred']:.4f}  obs {row['obs']:.4f}  "
                         f"n {row['n']}")
```

In `_holdout`, carry the mode and the truth column — the `carry` block becomes:

```python
    modes = models["minutes"].predict_modes(hold)
    carry = hold[["code", "gw"]].copy()
    for col in ("season_start_share", "minutes_r5", "starts"):
        if col in hold.columns:
            carry[col] = pd.to_numeric(hold[col], errors="coerce")
    carry["p_dnp"] = modes["p_dnp"].values
    carry["p_start"] = modes["p_start"].values
    carry = carry.groupby(["code", "gw"], as_index=False).first()
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_evaluation_v8a.py tests/test_zeros_diagnostic.py`
  Expected: green; 8 passed in the new file.

- [ ] **Commit.**

```bash
git add src/gaffer/zeros_diagnostic.py tests/test_evaluation_v8a.py && git commit -m "$(cat <<'EOF'
feat: F3 per-stratum P(start) reliability in the zeros diagnostic

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — Config: the seven new `[news]` keys and the serving reader

**Files:**
- Modify `src/gaffer/config.py`
- Modify `config.example.toml`
- Create `tests/test_config_v8a.py`

`advise.py` is protected, so it cannot learn to pass new flags to the news layer. The serve-time seams therefore read the config themselves, through one cached accessor that never raises — a clone with no `config.toml` (the web app's first run, a test) gets the dataclass defaults rather than an exception.

- [ ] **Write the failing test.** Create `tests/test_config_v8a.py`:

```python
"""v8a's [news] keys: defaults, overrides, and the serving reader."""

from __future__ import annotations

from gaffer.config import Config, load_config, serving_config

_TOML = """
[fpl]
entry_id = 1
league_id = 2

[news]
llm_classifier = true
llm_shadow = false
llm_command = "fake -p"
llm_timeout_s = 7
lineup_absence = false
lineup_absence_damp = 0.5
lineup_start_floor = 0.3
"""


def test_the_shipped_defaults_are_the_pre_v8a_behaviour():
    """Everything that could change a number ships OFF or neutral: the
    classifier does not serve, the floor is a no-op, and the one thing that
    is on by default — the absence damp — is the conservative direction."""
    cfg = Config(entry_id=1, league_id=2)
    assert cfg.news_llm_classifier is False
    assert cfg.news_llm_shadow is True
    assert cfg.news_llm_command == "claude -p --output-format json"
    assert cfg.news_llm_timeout_s == 120
    assert cfg.news_lineup_absence is True
    assert cfg.news_lineup_absence_damp == 0.75
    assert cfg.news_lineup_start_floor == 0.0


def test_every_key_is_read_from_the_news_section(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(_TOML, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.news_llm_classifier is True
    assert cfg.news_llm_shadow is False
    assert cfg.news_llm_command == "fake -p"
    assert cfg.news_llm_timeout_s == 7
    assert cfg.news_lineup_absence is False
    assert cfg.news_lineup_absence_damp == 0.5
    assert cfg.news_lineup_start_floor == 0.3


def test_a_missing_config_gives_the_serving_defaults_not_a_raise(monkeypatch,
                                                                 tmp_path):
    """The serve-time seams read this from inside fetchers that must never
    block advice, and a clone without a config.toml still has to predict."""
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    cfg = serving_config()
    assert cfg.news_lineup_absence is True
    assert cfg.news_llm_classifier is False
    serving_config.cache_clear()


def test_the_example_config_documents_every_new_key():
    text = open("config.example.toml", encoding="utf-8").read()
    for key in ("llm_classifier", "llm_shadow", "llm_command",
                "llm_timeout_s", "lineup_absence", "lineup_absence_damp",
                "lineup_start_floor"):
        assert key in text
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_config_v8a.py`
  Expected: `ImportError: cannot import name 'serving_config'`.

- [ ] **Write the implementation.** In `src/gaffer/config.py`, extend the `Config` dataclass under the v5 news block:

```python
    # --- v8a news layer ----------------------------------------------------
    # Two serve-time upgrades and one classifier, all readable by the news
    # seams themselves because ``advise`` is protected and cannot learn to
    # pass them. Defaults are the pre-v8a behaviour with one exception: the
    # notable-absence damp is ON, because it can only ever lower a number and
    # the case it catches — a regular quietly left out of the predicted XI —
    # is the one the layer exists for.
    news_llm_classifier: bool = False
    news_llm_shadow: bool = True
    news_llm_command: str = "claude -p --output-format json"
    news_llm_timeout_s: int = 120
    news_lineup_absence: bool = True
    news_lineup_absence_damp: float = 0.75
    news_lineup_start_floor: float = 0.0
```

Extend the `[news]` block in `load_config`, key by key like the rest of the section:

```python
        news_min_coverage=float(news.get("min_coverage", 0.5)),
        news_llm_classifier=bool(news.get("llm_classifier", False)),
        news_llm_shadow=bool(news.get("llm_shadow", True)),
        news_llm_command=str(news.get("llm_command",
                                      "claude -p --output-format json")),
        news_llm_timeout_s=int(news.get("llm_timeout_s", 120)),
        news_lineup_absence=bool(news.get("lineup_absence", True)),
        news_lineup_absence_damp=float(news.get("lineup_absence_damp", 0.75)),
        news_lineup_start_floor=float(news.get("lineup_start_floor", 0.0)),
```

and add the cached accessor at the end of the module:

```python
@lru_cache(maxsize=1)
def serving_config() -> Config:
    """The config as the *serve-time seams* read it — never raising.

    ``advise.py`` is protected, so v8a's fetcher- and availability-level
    switches cannot arrive as arguments; they are read here instead. Two
    consequences are deliberate. It is cached, because a fetcher must not
    re-read a TOML file per call. And it degrades to the dataclass defaults
    rather than raising, because a clone with no ``config.toml`` still has to
    predict — the loud "copy config.example.toml" error belongs to the CLI's
    own :func:`load_config` call, not to a news source.

    Tests that change ``config.toml`` under a running process call
    ``serving_config.cache_clear()``.
    """
    try:
        return load_config()
    except Exception:  # noqa: BLE001 — serving never blocks on config
        return Config(entry_id=0, league_id=0)
```

with `from functools import lru_cache` added to the imports.

- [ ] **Document the keys.** Append to `config.example.toml`:

```toml
[news]
# Live availability. Every source degrades to the official FPL flags on its
# own, so these switch off a *working* source rather than rescue a broken one.
enabled = true
injuries = true            # premierinjuries.com injury table
lineups = true             # Fantasy Football Scout predicted XIs
cache_hours = 6
min_coverage = 0.5         # share of a source's rows that must match a player

# v8a: a regular left out of a published predicted XI is evidence against him
# even though the page never names him. Damps the imminent gameweek only.
lineup_absence = true
lineup_absence_damp = 0.75
# A floor under a predicted starter's p_play. 0.0 is off, and it ships off:
# floors can only raise a number, and no evidence supports one yet.
lineup_start_floor = 0.0

# v8a: the presser/quote classifier, run through a headless CLI on your own
# subscription. Shadow-only by default — it logs what it would have done to
# data/live/presser_log.parquet and changes no advice.
llm_classifier = false
llm_shadow = true
llm_command = "claude -p --output-format json"
llm_timeout_s = 120
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_config_v8a.py tests/test_config.py`
  Expected: green; 4 passed in the new file.

- [ ] **Commit.**

```bash
git add src/gaffer/config.py config.example.toml tests/test_config_v8a.py && git commit -m "$(cat <<'EOF'
feat: v8a [news] config keys and the never-raising serving reader

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — F4/F5: widening the availability column contract

**Files:**
- Modify `src/gaffer/artifacts.py` (`AVAILABILITY_COLS`, the dtype loops in `save_availability`)
- Modify `src/gaffer/data/news/normalize.py` (`AVAIL_COLS`, the initialiser loop, the numeric coercions)
- Modify `src/gaffer/snapshot.py` (`snapshot_rows` dtype loops)
- Create `tests/test_availability_v8a.py`

Three columns land at once so the schema moves exactly once: `absence_damp` (F4), `llm_verdict` and `llm_confidence` (F5). The snapshot log inherits all three for free — `SNAPSHOT_COLS` is derived — and the existing 623 banked rows stay valid because `append_snapshot` already fills absent columns with nulls before the rewrite.

- [ ] **Write the failing test.** Create `tests/test_availability_v8a.py`:

```python
"""v8a's serve-time layer: the widened contract, the damp, the floor."""

from __future__ import annotations

import pandas as pd

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.data.news.normalize import AVAIL_COLS, availability_frame
from gaffer.snapshot import SNAPSHOT_COLS, snapshot_rows


def _official() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "status": "a", "chance_of_playing": None},
        {"code": 2, "status": "a", "chance_of_playing": None},
        {"code": 3, "status": "s", "chance_of_playing": 0}])


def test_the_two_column_lists_are_the_same_list():
    """They are written out twice — the artifact's and the normalizer's — and
    a drift between them is a silently dropped column."""
    assert AVAIL_COLS == AVAILABILITY_COLS


def test_the_contract_carries_the_three_new_columns():
    for col in ("absence_damp", "llm_verdict", "llm_confidence"):
        assert col in AVAILABILITY_COLS


def test_an_empty_news_run_still_produces_every_column():
    out = availability_frame(_official(), None, None, gw=5, events=None)
    assert list(out.columns) == AVAIL_COLS
    assert out["absence_damp"].isna().all()
    assert out["llm_verdict"].isna().all()


def test_the_line_up_frame_carries_a_damp_through():
    lineups = pd.DataFrame([
        {"code": 1, "p_start_hint": None, "absence_damp": 0.75,
         "source": "lineups", "fetched_at": "2026-09-04T09:00:00Z"}])
    out = availability_frame(_official(), None, lineups, gw=5, events=None)
    assert out.set_index("code").loc[1, "absence_damp"] == 0.75
    assert pd.isna(out.set_index("code").loc[2, "absence_damp"])


def test_a_banned_player_takes_no_damp():
    """Official s/u/n is authoritative — rule 1 has not moved."""
    lineups = pd.DataFrame([
        {"code": 3, "p_start_hint": None, "absence_damp": 0.75,
         "source": "lineups", "fetched_at": "2026-09-04T09:00:00Z"}])
    out = availability_frame(_official(), None, lineups, gw=5, events=None)
    assert pd.isna(out.set_index("code").loc[3, "absence_damp"])


def test_the_snapshot_log_inherits_the_new_columns_with_settled_dtypes():
    frame = availability_frame(_official(), None, None, gw=5, events=None)
    rows = snapshot_rows(frame, gw=5, season="2026-27", day="2026-09-04")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert str(rows["absence_damp"].dtype).startswith("float")
    assert str(rows["llm_confidence"].dtype).startswith("float")
    assert str(rows["llm_verdict"].dtype) == "string"


def test_a_log_row_from_before_the_widening_still_appends(tmp_path,
                                                          monkeypatch):
    """The banked log predates these columns. Append-by-rewrite has to read
    the old shape and write the new one rather than refusing the file."""
    from gaffer.data import store as store_mod
    from gaffer.snapshot import SNAPSHOT_PATH, append_snapshot, load_snapshot_log

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    old = pd.DataFrame([{"season": "2026-27", "gw": 4, "snap_date":
                         "2026-09-01", "code": 1, "status": "a",
                         "chance_of_playing": None, "injury_type": None,
                         "expected_return_gw": None, "p_start_hint": None,
                         "source": None, "fetched_at": None}])
    store_mod.save(old, SNAPSHOT_PATH)
    frame = availability_frame(_official(), None, None, gw=5, events=None)
    append_snapshot(snapshot_rows(frame, gw=5, season="2026-27",
                                  day="2026-09-04"))
    back = load_snapshot_log()
    assert list(back.columns) == SNAPSHOT_COLS
    assert set(back["snap_date"]) == {"2026-09-01", "2026-09-04"}
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_availability_v8a.py`
  Expected: `AssertionError` on the first test — `absence_damp` is in neither list.

- [ ] **Write the implementation.** In `src/gaffer/artifacts.py`, widen the contract:

```python
AVAILABILITY_COLS = ["code", "status", "chance_of_playing", "injury_type",
                     "expected_return_gw", "p_start_hint", "absence_damp",
                     "llm_verdict", "llm_confidence", "source", "fetched_at"]
```

and extend its docstring with:

```
v8a adds three. ``absence_damp`` is the notable-absence factor a predicted
line-up implies for a player it silently left out; ``llm_verdict`` and
``llm_confidence`` are the presser classifier's reading of the free text.
All three are nullable and all three are logged whether or not they are
served, because the point of banking them is that a future season can train
on what the news said (spec §4).
```

In `save_availability`, extend the two dtype loops:

```python
        for col in ("status", "injury_type", "llm_verdict", "source",
                    "fetched_at"):
            out[col] = out[col].astype("object").where(
                out[col].notna(), None).astype("string")
        for col in ("chance_of_playing", "expected_return_gw", "p_start_hint",
                    "absence_damp", "llm_confidence"):
```

In `src/gaffer/data/news/normalize.py`, mirror the list:

```python
AVAIL_COLS = ["code", "status", "chance_of_playing", "injury_type",
              "expected_return_gw", "p_start_hint", "absence_damp",
              "llm_verdict", "llm_confidence", "source", "fetched_at"]
```

In `availability_frame`, extend the initialiser loop:

```python
    for col in ("injury_type", "expected_return_gw", "p_start_hint",
                "absence_damp", "llm_verdict", "llm_confidence",
                "source", "fetched_at"):
        out[col] = None
```

extend the line-ups block to carry the damp (inside `if not hints.empty:`, after the `p_start_hint` assignment):

```python
            # v8a F4. Carried, not applied: like the hint, a damp is about
            # one team sheet for one match, and ``apply_availability`` is the
            # only place that knows which gameweek that is.
            if "absence_damp" in hints.columns:
                out.loc[got, "absence_damp"] = out.loc[got, "code"].map(
                    hints["absence_damp"])
```

extend the injuries block's carried columns (the `for col in (...)` inside `if not inj.empty:`):

```python
            for col in ("injury_type", "expected_return_gw", "llm_verdict",
                        "llm_confidence", "source", "fetched_at"):
                if col in keyed.columns:
                    out.loc[hit, col] = out.loc[hit, "code"].map(keyed[col])
```

and extend the numeric coercions before the return:

```python
    out["expected_return_gw"] = pd.to_numeric(out["expected_return_gw"],
                                              errors="coerce")
    out["p_start_hint"] = pd.to_numeric(out["p_start_hint"], errors="coerce")
    out["absence_damp"] = pd.to_numeric(out["absence_damp"], errors="coerce")
    out["llm_confidence"] = pd.to_numeric(out["llm_confidence"],
                                          errors="coerce")
    return out[AVAIL_COLS]
```

In `src/gaffer/snapshot.py`, extend `snapshot_rows`'s two dtype loops the same way:

```python
    for col in ("status", "injury_type", "llm_verdict", "source",
                "fetched_at"):
        out[col] = out[col].astype("object").where(
            out[col].notna(), None).astype("string")
    for col in ("chance_of_playing", "expected_return_gw", "p_start_hint",
                "absence_damp", "llm_confidence"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_availability_v8a.py tests/test_artifacts.py tests/test_news_normalize.py tests/test_snapshot.py`
  Expected: green; 7 passed in the new file.

- [ ] **Commit.**

```bash
git add src/gaffer/artifacts.py src/gaffer/data/news/normalize.py src/gaffer/snapshot.py tests/test_availability_v8a.py && git commit -m "$(cat <<'EOF'
feat: widen the availability contract with the damp and the verdict columns

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — F4: notable-absence rows from the predicted line-ups

**Files:**
- Modify `src/gaffer/data/bootstrap.py` (`build_players`)
- Modify `src/gaffer/data/news/lineups.py`
- Modify `tests/test_news_sources.py` (append)

Today a player merely *absent* from a published XI carries no signal at all — the exact "regular quietly benched" case v8a exists to catch. The fetcher is the only non-protected place that has both the parsed XI and a per-player start record, so that is where the rule lives.

- [ ] **Write the failing test.** Append to `tests/test_news_sources.py`:

```python
# --- v8a F4: notable absences ---------------------------------------------

def _absence_players() -> pd.DataFrame:
    """One club, four players: a regular in the XI, a regular left out, a
    fringe player left out, and a listed doubt."""
    return pd.DataFrame([
        {"code": 11, "name": "In XI", "first_name": "A", "second_name": "One",
         "team_code": 3, "starts": 10, "minutes": 900},
        {"code": 12, "name": "Left Out", "first_name": "B",
         "second_name": "Two", "team_code": 3, "starts": 9, "minutes": 800},
        {"code": 13, "name": "Fringe", "first_name": "C",
         "second_name": "Three", "team_code": 3, "starts": 1, "minutes": 90},
        {"code": 14, "name": "Doubtful", "first_name": "D",
         "second_name": "Four", "team_code": 3, "starts": 8, "minutes": 700}])


def test_a_regular_left_out_of_a_parsed_xi_is_damped():
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered={3},
                           claimed={11, 14}, damp=0.75, min_share=0.6)
    assert list(out["code"]) == [12]
    assert out.iloc[0]["absence_damp"] == 0.75


def test_a_fringe_player_left_out_is_not_news():
    """Half a squad is out of every predicted XI. Only a player the manager
    has actually been picking says anything by being missing."""
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered={3},
                           claimed={11, 14}, damp=0.75, min_share=0.6)
    assert 13 not in set(out["code"])


def test_a_club_whose_xi_was_not_parsed_damps_nobody():
    """No team sheet is not the same as a team sheet without him."""
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered=set(),
                           claimed=set(), damp=0.75, min_share=0.6)
    assert out.empty


def test_a_player_already_on_an_absence_list_is_not_damped_twice():
    from gaffer.data.news.lineups import notable_absences

    out = notable_absences(_absence_players(), covered={3},
                           claimed={11, 12, 14}, damp=0.75, min_share=0.6)
    assert out.empty


def test_fetch_lineups_emits_absence_rows_beside_the_hints(tmp_path):
    from gaffer.data.news.lineups import LINEUP_COLS, fetch_lineups

    client = _client(_LINEUP_HTML)
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=client, absence=True, absence_damp=0.75,
                        now=_NOW)
    assert list(out.columns) == LINEUP_COLS
    assert out["p_start_hint"].notna().any()


def test_the_absence_rule_can_be_switched_off(tmp_path):
    from gaffer.data.news.lineups import fetch_lineups

    on = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                       client=_client(_LINEUP_HTML), absence=True,
                       absence_damp=0.75, now=_NOW)
    off = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client(_LINEUP_HTML), absence=False,
                        now=_NOW)
    assert off["absence_damp"].isna().all()
    assert len(off) <= len(on)
```

Reuse the module's existing `_players()`, `_teams()`, `_client()` and line-up HTML fixtures; where the existing `_players()` has no `starts` column, add `starts` and `minutes` to it — a bootstrap frame carries them from this task on. Name the HTML fixture whatever the file already calls it (`_LINEUP_HTML` above stands for that name) and reuse the module's `_NOW` if it has one, otherwise drop the argument.

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_news_sources.py -k absence`
  Expected: `ImportError: cannot import name 'notable_absences'`.

- [ ] **Carry the start record on the bootstrap frame.** In `src/gaffer/data/bootstrap.py`, add two entries to `build_players`'s row dict, beside `chance_of_playing`:

```python
            # v8a F4: the absence rule needs to know who the manager has
            # actually been picking, and this is the only start record that
            # exists at serve time without loading the history frame.
            "starts": to_int(e.get("starts")) or 0,
            "minutes": to_int(e.get("minutes")) or 0,
```

- [ ] **Write the implementation.** In `src/gaffer/data/news/lineups.py`, add the constants beside `P_START_HINT`:

```python
LINEUP_COLS = ["code", "p_start_hint", "absence_damp", "source", "fetched_at"]

ABSENCE_MIN_START_SHARE = 0.6
"""Share of his club's most-started player's starts, above which a player's
omission from a predicted XI is *news*.

Read as "he has started at least 60% as often as the club's most reliable
starter". The bootstrap carries season starts and no fixture count, so the
club's own maximum is the denominator that needs neither: it is the number of
matches a nailed-on starter has played. Below the threshold the omission is
one journalist declining to pick a squad player, which is not evidence about
anything.
"""
```

Add the rule itself before `fetch_lineups`:

```python
def notable_absences(players: pd.DataFrame, covered: set[int],
                     claimed: set[int], damp: float,
                     min_share: float = ABSENCE_MIN_START_SHARE
                     ) -> pd.DataFrame:
    """Regulars a parsed XI silently left out, as ``[code, absence_damp]``.

    Three conditions, all necessary (spec §4). His club must have a parsed XI
    — no team sheet is not the same as a team sheet without him. He must not
    already be *named* by the page, in the XI or on any absence list, because
    that row is the sharper claim and damping it twice would double-count one
    source. And he must be a regular by :data:`ABSENCE_MIN_START_SHARE`, since
    half of every squad is out of every predicted XI and only a player the
    manager has been picking says something by being missing.

    The result is a *damp*, not a ceiling: an omission is weaker evidence than
    a printed "Out", and multiplying is how the model's own view survives it.
    """
    cols = ["code", "absence_damp"]
    if not covered or "starts" not in players.columns:
        return pd.DataFrame(columns=cols)
    frame = players[["code", "team_code", "starts"]].copy()
    frame["code"] = pd.to_numeric(frame["code"], errors="coerce")
    frame["team_code"] = pd.to_numeric(frame["team_code"], errors="coerce")
    frame["starts"] = pd.to_numeric(frame["starts"], errors="coerce").fillna(0.0)
    frame = frame[frame["team_code"].isin(covered)]
    frame = frame[~frame["code"].isin(claimed)]
    if frame.empty:
        return pd.DataFrame(columns=cols)
    best = frame.groupby("team_code")["starts"].transform("max")
    share = frame["starts"] / best.where(best > 0)
    out = frame[share >= min_share].copy()
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["absence_damp"] = float(damp)
    out["code"] = out["code"].astype("int64")
    return out[cols].sort_values("code").reset_index(drop=True)
```

Extend `fetch_lineups`'s signature and tail. The signature:

```python
def fetch_lineups(players: pd.DataFrame, teams: pd.DataFrame,
                  cache_dir: Path = NEWS_CACHE, cache_hours: int = 6,
                  client: httpx.Client | None = None,
                  min_coverage: float = NEWS_MIN_COVERAGE,
                  now: datetime | None = None,
                  absence: bool | None = None,
                  absence_damp: float | None = None) -> pd.DataFrame:
    """Predicted line-ups as ``[code, p_start_hint, absence_damp, …]``.

    ``absence``/``absence_damp`` default to the ``[news]`` config, read here
    rather than passed in: ``advise.py`` is protected and cannot learn to
    forward them. ``False`` reproduces the pre-v8a frame exactly, one extra
    all-null column aside.
    """
    cfg = serving_config()
    absence = cfg.news_lineup_absence if absence is None else bool(absence)
    absence_damp = (cfg.news_lineup_absence_damp if absence_damp is None
                    else float(absence_damp))
```

with `from gaffer.config import serving_config` added to the imports. Every early `return pd.DataFrame(columns=LINEUP_COLS)` is unchanged — the widened list is what they build from.

Replace the function's last three lines with:

```python
    out["absence_damp"] = float("nan")
    # A player named in two blocks (listed as a doubt and on the bench) takes
    # the most pessimistic hint — the same rule availability_frame applies
    # between sources.
    out = (out.sort_values("p_start_hint")
           .groupby("code", as_index=False).head(1))
    if absence:
        # The clubs whose *pitch* parsed. An absence list on its own is not a
        # team sheet, and reading one as though it were would damp everybody
        # at a club whose XI the page never printed.
        covered = set(pd.to_numeric(
            club_codes[parsed["slot"] == "start"], errors="coerce")
            .dropna().astype(int))
        extra = notable_absences(players, covered, set(out["code"]),
                                 absence_damp)
        if not extra.empty:
            extra["p_start_hint"] = float("nan")
            extra["source"] = "lineups"
            extra["fetched_at"] = fetched_at(now)
            out = pd.concat([out, extra], ignore_index=True)
    return out[LINEUP_COLS].sort_values("code").reset_index(drop=True)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_news_sources.py tests/test_bootstrap.py`
  Expected: green. If an existing line-up test asserts a row count, it is asserting the pre-v8a shape: pass `absence=False` in that test rather than weakening the assertion.

- [ ] **Commit.**

```bash
git add src/gaffer/data/bootstrap.py src/gaffer/data/news/lineups.py tests/test_news_sources.py && git commit -m "$(cat <<'EOF'
feat: F4 notable-absence rows from the predicted line-ups

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — F4: applying the damp and shipping the floor

**Files:**
- Modify `src/gaffer/models/availability.py`
- Modify `tests/test_availability_v8a.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_availability_v8a.py`:

```python
# --- the serving side ------------------------------------------------------

from gaffer.models.availability import apply_availability  # noqa: E402


def _pred(codes=(1,), gws=(5, 6, 7), p_play=0.9) -> pd.DataFrame:
    return pd.DataFrame([{"code": c, "gw": g, "p_play": p_play,
                          "p60": p_play * 0.85, "e_min": 80.0}
                         for c in codes for g in gws])


def _avail(**cols) -> pd.DataFrame:
    row = {"code": 1, "status": "a", "chance_of_playing": None,
           "injury_type": None, "expected_return_gw": None,
           "p_start_hint": None, "absence_damp": None, "llm_verdict": None,
           "llm_confidence": None, "source": None, "fetched_at": None}
    row.update(cols)
    return pd.DataFrame([row])


def test_the_damp_bites_on_the_first_gameweek_only():
    out = apply_availability(_pred(), _avail(absence_damp=0.75), curves=None)
    by_gw = out.set_index("gw")
    assert by_gw.loc[5, "p_play"] == pytest.approx(0.9 * 0.75)
    assert by_gw.loc[6, "p_play"] == pytest.approx(0.9)


def test_the_damp_scales_all_three_outputs_together():
    """An untouched p60 beside a damped p_play is the incoherence the
    three-mode model exists to remove."""
    out = apply_availability(_pred(), _avail(absence_damp=0.5), curves=None)
    first = out[out["gw"] == 5].iloc[0]
    assert first["p60"] == pytest.approx(0.9 * 0.85 * 0.5)
    assert first["e_min"] == pytest.approx(80.0 * 0.5)


def test_a_double_gameweek_is_damped_once():
    """One team sheet, one match. Damping both fixtures claims the site
    predicted a tie it never wrote about."""
    pred = pd.DataFrame([{"code": 1, "gw": 5, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0},
                         {"code": 1, "gw": 5, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0}])
    out = apply_availability(pred, _avail(absence_damp=0.5), curves=None)
    assert sorted(round(v, 4) for v in out["p_play"]) == [0.45, 0.9]


def test_no_damp_column_is_the_pre_v8a_arithmetic_exactly():
    with_col = apply_availability(_pred(), _avail(), curves=None)
    without = apply_availability(
        _pred(), _avail().drop(columns=["absence_damp"]), curves=None)
    pd.testing.assert_frame_equal(with_col, without)


def test_the_start_floor_is_off_by_default():
    out = apply_availability(_pred(p_play=0.4), _avail(p_start_hint=1.0),
                             curves=None)
    assert out[out["gw"] == 5].iloc[0]["p_play"] == pytest.approx(0.4)


def test_the_start_floor_raises_a_predicted_starter_when_enabled():
    out = apply_availability(_pred(p_play=0.4), _avail(p_start_hint=1.0),
                             curves=None, start_floor=0.7)
    first = out[out["gw"] == 5].iloc[0]
    assert first["p_play"] == pytest.approx(0.7)
    assert first["p60"] == pytest.approx(0.4 * 0.85 * (0.7 / 0.4))


def test_the_floor_never_touches_a_player_the_page_did_not_start():
    out = apply_availability(_pred(p_play=0.4), _avail(p_start_hint=0.25),
                             curves=None, start_floor=0.7)
    # The ceiling still bites (0.25 < 0.4); the floor never sees the row.
    assert out[out["gw"] == 5].iloc[0]["p_play"] == pytest.approx(0.25)


def test_the_new_columns_do_not_survive_into_the_output():
    out = apply_availability(_pred(), _avail(absence_damp=0.75), curves=None)
    for col in ("absence_damp", "llm_verdict", "llm_confidence"):
        assert col not in out.columns
```

Add `import pytest` to the file's imports.

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_availability_v8a.py -k damp or floor`
  Expected: the damp tests fail — `absence_damp` is carried through untouched and dropped.

- [ ] **Write the implementation.** In `src/gaffer/models/availability.py`, add the shared row selector and the two new passes, and refactor `_gate_first_gw` onto the selector:

```python
def _first_rows(out: pd.DataFrame) -> pd.Series:
    """The horizon's first row per player — a boolean mask.

    At most **one row per player**, even in a double gameweek: a predicted
    line-up is one team sheet for one match, and applying it to both of a
    double's fixtures claims the site predicted a tie it never wrote about.
    The row taken is the first in frame order, which is the earliest fixture
    (``predict_components`` builds the frame in fixture order), and that is
    the match the published XI is about.

    Factored out of :func:`_gate_first_gw` because v8a's damp and floor have
    to bite on exactly the same rows the ceiling does — three copies of this
    rule would be three chances for them to drift apart.
    """
    first = ((out["gw"] == out["gw"].min()) if "gw" in out.columns
             else pd.Series(True, index=out.index))
    if "code" in out.columns:
        extra = out.loc[first, "code"].duplicated()
        first = first & ~out.index.isin(extra.index[extra])
    return first


def _gate_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply ``p_start_hint`` as a ceiling on the horizon's first gameweek.

    The ratio is applied to all three outputs rather than clipping ``p_play``
    alone: an untouched ``p60`` beside a halved ``p_play`` is the incoherence
    the three-mode model was built to remove, and ``e_min`` feeds the
    scenario sweep's nailedness score.
    """
    hint = pd.to_numeric(out["p_start_hint"], errors="coerce")
    first = _first_rows(out)
    bites = first & hint.notna() & (hint < out["p_play"])
    if not bites.any():
        return out
    ratio = (hint[bites] / out.loc[bites, "p_play"]).where(
        out.loc[bites, "p_play"] > 0, 0.0)
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * ratio
    return out


def _damp_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply ``absence_damp`` to the horizon's first gameweek (v8a F4).

    A regular the predicted XI silently left out. Weaker evidence than a
    printed "Out", so it multiplies rather than clipping: the model's own view
    survives it, scaled. Same one-row-per-player rule and the same
    three-outputs-together discipline as the ceiling above, and it composes
    with the ceiling by construction — a player who is both named as a doubt
    and a notable absentee cannot exist, because the absence rule skips every
    code the page named.
    """
    damp = pd.to_numeric(out["absence_damp"], errors="coerce")
    bites = _first_rows(out) & damp.notna() & (damp < 1.0)
    if not bites.any():
        return out
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * damp[bites]
    return out


def _floor_first_gw(out: pd.DataFrame, floor: float) -> pd.DataFrame:
    """Raise a *predicted starter* to ``floor`` on the first gameweek.

    Shipped as a capability at ``0.0`` — off — and deliberately so. The hint
    has only ever been a ceiling, on the argument that a predicted omission is
    strong evidence and a predicted start is none; a floor reverses that for
    the one case where the page is unambiguous, and reversing it without
    evidence is how a fringe player becomes a captain. It is enabled only if
    the shadow log supports a value (spec §4).

    ``p_play`` of exactly zero is left alone: there is no ratio to carry
    ``p60`` and ``e_min`` up with, and a model that has ruled a player out
    entirely is not being contradicted by a website's guess.
    """
    if floor <= 0.0:
        return out
    hint = pd.to_numeric(out["p_start_hint"], errors="coerce")
    bites = (_first_rows(out) & (hint >= 1.0) & (out["p_play"] < floor)
             & (out["p_play"] > 0))
    if not bites.any():
        return out
    ratio = floor / out.loc[bites, "p_play"]
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * ratio
    return out
```

and extend `apply_availability`'s signature, news columns and tail:

```python
def apply_availability(pred: pd.DataFrame, avail: pd.DataFrame,
                       curves: dict | None = None,
                       start_floor: float | None = None) -> pd.DataFrame:
```

with these paragraphs appended to its docstring:

```
    ``absence_damp``, when the frame carries one, multiplies the horizon's
    first gameweek: a regular the predicted XI left out without naming him
    (v8a F4). It composes with the hint ceiling and obeys the same
    one-row-per-player rule.

    ``start_floor`` defaults to the ``[news] lineup_start_floor`` config key,
    read here because ``advise`` is protected and cannot forward it. At its
    shipped ``0.0`` the pass is a no-op and this function is arithmetically
    identical to v7's.
```

the news-column list:

```python
    news_cols = [c for c in ("injury_type", "expected_return_gw",
                             "p_start_hint", "absence_damp", "llm_verdict",
                             "llm_confidence")
                 if c in avail.columns]
```

and the tail:

```python
    if "p_start_hint" in out.columns:
        out = _gate_first_gw(out)
        if start_floor is None:
            from gaffer.config import serving_config
            start_floor = serving_config().news_lineup_start_floor
        out = _floor_first_gw(out, float(start_floor))
    if "absence_damp" in out.columns:
        out = _damp_first_gw(out)
    return out.drop(columns=["status", "chance_of_playing"] + news_cols)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_availability_v8a.py tests/test_availability.py tests/test_v5_degradation.py`
  Expected: green; 15 passed in the new file, and `tests/test_v5_degradation.py` untouched and still passing — its flags-only pins are what prove the no-op.

- [ ] **Commit.**

```bash
git add src/gaffer/models/availability.py tests/test_availability_v8a.py && git commit -m "$(cat <<'EOF'
feat: F4 notable-absence damp and the off-by-default predicted-starter floor

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — F5: the presser classifier module

**Files:**
- Create `src/gaffer/data/news/classifier.py`
- Create `tests/test_classifier.py`

**The suite must never shell out to the real `claude` CLI.** Every test below points `cmd` at a throwaway Python script. G4 — one real batch — is the orchestrator's, and it is in Task 19's checklist.

- [ ] **Write the failing test.** Create `tests/test_classifier.py`:

```python
"""The presser classifier: a subprocess that is allowed to fail.

Every test here runs a *fake* CLI — a two-line Python script printing canned
JSON. The real ``claude -p`` is never invoked from the suite (spec §7): it
costs seconds per call, needs a logged-in machine, and would make a green
suite depend on somebody's subscription.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from gaffer.data.news.classifier import (CLASSIFIER_COLS, VERDICTS, NewsText,
                                         classify_news, text_hash)

_ROWS = [{"code": 1, "verdict": "rotation_risk", "confidence": 0.8},
         {"code": 2, "verdict": "confirmed_starter", "confidence": 0.9}]


def _fake(tmp_path: Path, payload, exit_code: int = 0,
          sleep: float = 0.0) -> str:
    """A CLI that ignores its stdin and prints ``payload``."""
    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys, time, json\n"
        "sys.stdin.read()\n"
        f"time.sleep({sleep})\n"
        f"sys.stdout.write({json.dumps(payload)!r})\n"
        f"sys.exit({exit_code})\n", encoding="utf-8")
    return f"{sys.executable} {script}"


def _texts():
    return [NewsText(code=1, text="Rested, we will see", source="fpl"),
            NewsText(code=2, text="He trained fully", source="pi")]


def test_a_clean_batch_comes_back_as_one_row_per_text(tmp_path):
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(_ROWS)}))
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=10)
    assert list(out.columns) == CLASSIFIER_COLS
    assert sorted(out["code"]) == [1, 2]
    assert set(out["verdict"]) <= VERDICTS


def test_a_bare_json_array_is_accepted_too(tmp_path):
    """``llm_command`` is configurable, so the wrapper shape is not
    guaranteed: a CLI that prints the array itself is read the same way."""
    cmd = _fake(tmp_path, json.dumps(_ROWS))
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=10)
    assert len(out) == 2


def test_a_row_with_an_unknown_verdict_is_dropped_not_guessed(tmp_path):
    rows = _ROWS + [{"code": 3, "verdict": "vibes", "confidence": 1.0}]
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(rows)}))
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=10)
    assert 3 not in set(out["code"])


def test_a_second_call_reads_the_cache_and_never_runs_the_cli(tmp_path):
    cache = tmp_path / "cache"
    cmd = _fake(tmp_path, json.dumps({"result": json.dumps(_ROWS)}))
    classify_news(_texts(), cmd=cmd, cache_dir=cache, timeout=10)
    dead = _fake(tmp_path, "", exit_code=1)
    again = classify_news(_texts(), cmd=dead, cache_dir=cache, timeout=10)
    assert sorted(again["code"]) == [1, 2]


def test_the_cache_key_is_the_text_not_the_player(tmp_path):
    """Twenty players carrying "Knock, assessed daily" is one call."""
    assert text_hash("a") != text_hash("b")
    assert text_hash("a") == text_hash("a")


def test_a_dead_cli_yields_an_empty_frame_and_one_line(tmp_path, capsys):
    out = classify_news(_texts(), cmd=_fake(tmp_path, "", exit_code=3),
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty and list(out.columns) == CLASSIFIER_COLS
    assert "classifier" in capsys.readouterr().out


def test_a_missing_binary_yields_an_empty_frame(tmp_path):
    out = classify_news(_texts(), cmd="definitely-not-a-binary --json",
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty


def test_a_timeout_yields_an_empty_frame(tmp_path):
    cmd = _fake(tmp_path, json.dumps(_ROWS), sleep=2.0)
    out = classify_news(_texts(), cmd=cmd, cache_dir=tmp_path / "cache",
                        timeout=1)
    assert out.empty


def test_unparseable_output_yields_an_empty_frame(tmp_path):
    out = classify_news(_texts(), cmd=_fake(tmp_path, "I'm sorry Dave"),
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty


def test_no_texts_at_all_runs_nothing(tmp_path):
    out = classify_news([], cmd="definitely-not-a-binary",
                        cache_dir=tmp_path / "cache", timeout=10)
    assert out.empty and list(out.columns) == CLASSIFIER_COLS


def test_the_prompt_names_every_verdict_and_every_text(tmp_path):
    from gaffer.data.news.classifier import build_prompt

    prompt = build_prompt(_texts())
    for verdict in VERDICTS:
        assert verdict in prompt
    assert "Rested, we will see" in prompt
    assert "He trained fully" in prompt
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_classifier.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.data.news.classifier'`.

- [ ] **Write the implementation.** Create `src/gaffer/data/news/classifier.py`:

```python
"""The presser/quote classifier — a short free text, read by an LLM.

Two sources say things no structured feed carries: premierinjuries' "Further
Detail" cell (a manager's quote) and the FPL bootstrap's ``news`` column. Both
are one sentence, and both routinely contain the sharpest available claim
about the imminent gameweek — "he's not ready to start", "a knock, we'll
assess" — in prose no regex is going to survive.

Three properties make this safe to run on every advise:

*Shadow-first.* ``[news] llm_classifier`` ships **false**. The verdicts are
logged whatever the flag says; they only reach the numbers when the flag is
flipped, on evidence, the same ritual Z1 got.

*Cached by text.* Twenty players carrying "Knock — assessed daily" is one
text and therefore one call, and a re-run in the same week is none.

*Total-failure-safe.* A missing binary, a non-zero exit, a timeout, prose
where JSON was asked for, a row naming a verdict nobody defined: every one of
them yields an empty frame and one printed line. A dead classifier leaves the
pipeline byte-identical to a classifier that was never enabled.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LLM_CACHE = Path("data/raw/news/llm")
CLASSIFIER_COLS = ["code", "verdict", "confidence", "model", "text_hash",
                   "fetched_at"]

VERDICTS = {"confirmed_starter", "rotation_risk", "knock", "assess",
            "ruled_out", "irrelevant"}
"""The whole vocabulary. A row naming anything else is dropped and counted:
an open vocabulary is a mapping table nobody can write, and the mapping is
the only reason to run this at all."""

DEFAULT_TIMEOUT_S = 120


@dataclass(frozen=True)
class NewsText:
    """One player's free text, and where it came from."""

    code: int
    text: str
    source: str


def text_hash(text: str) -> str:
    """The cache key: the text, not the player.

    Squad-wide boilerplate collapses to one entry, and a player whose quote
    has not changed since Tuesday costs nothing on Friday.
    """
    return hashlib.sha256(str(text or "").strip().encode("utf-8")
                          ).hexdigest()[:16]


def build_prompt(texts: list[NewsText]) -> str:
    """One prompt for the whole uncached batch, answered as a JSON array.

    Batched rather than one call per text because the per-call overhead is the
    cost here, not the tokens: thirty texts are a few hundred words and thirty
    subprocesses are half a minute.
    """
    lines = [
        "You are classifying short Fantasy Premier League team-news texts.",
        "For EACH numbered item below, decide which one verdict best fits:",
        "  confirmed_starter — the text says he will start / is fully fit",
        "  rotation_risk — fit, but the text hints he may be rested/rotated",
        "  knock — a minor problem, likely available",
        "  assess — explicitly to be assessed / a late call",
        "  ruled_out — will not feature",
        "  irrelevant — the text says nothing about his availability",
        "",
        "Reply with ONLY a JSON array, one object per item, no prose:",
        '[{"code": <the item\'s code>, "verdict": "<one of the six>",',
        '  "confidence": <0.0-1.0>}]',
        "",
        "Items:"]
    for t in texts:
        flat = " ".join(str(t.text or "").split())
        lines.append(f"- code {int(t.code)} ({t.source}): {flat}")
    return "\n".join(lines)


def _extract_rows(stdout: str) -> list[dict]:
    """The model's rows, out of whatever the CLI wrapped them in.

    ``claude -p --output-format json`` returns an envelope whose ``result`` is
    the model's own text; a different ``llm_command`` may print the array
    directly. Both are read, and anything else raises here and is caught by
    the one handler in :func:`classify_news`.
    """
    payload = json.loads(stdout)
    if isinstance(payload, dict):
        payload = json.loads(payload["result"])
    if not isinstance(payload, list):
        raise ValueError("classifier output was not a JSON array")
    return payload


def _cached(cache_dir: Path, key: str) -> dict | None:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a corrupt cache entry is a cache miss
        return None


def _store(cache_dir: Path, key: str, row: dict) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(json.dumps(row),
                                               encoding="utf-8")
    except Exception:  # noqa: BLE001 — an unwritable cache is not an outage
        pass


def classify_news(texts: list[NewsText], *, cmd: str,
                  cache_dir: Path = LLM_CACHE,
                  timeout: int = DEFAULT_TIMEOUT_S,
                  now: datetime | None = None) -> pd.DataFrame:
    """``[code, verdict, confidence, model, text_hash, fetched_at]``.

    Never raises, whatever the CLI does. An empty frame is the
    classifier-absent path, which is the shipped behaviour anyway.
    """
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    cache_dir = Path(cache_dir)
    model = shlex.split(cmd)[0] if cmd.strip() else ""
    rows: list[dict] = []
    pending: list[NewsText] = []
    for t in texts:
        key = text_hash(t.text)
        hit = _cached(cache_dir, key)
        if hit is None:
            pending.append(t)
        else:
            rows.append({"code": int(t.code), "verdict": hit["verdict"],
                         "confidence": float(hit.get("confidence", 0.0)),
                         "model": hit.get("model", model), "text_hash": key,
                         "fetched_at": stamp})

    if pending:
        by_code = {int(t.code): t for t in pending}
        try:
            proc = subprocess.run(shlex.split(cmd),
                                  input=build_prompt(pending),
                                  capture_output=True, text=True,
                                  timeout=timeout, check=True)
            parsed = _extract_rows(proc.stdout)
        except Exception as exc:  # noqa: BLE001 — the classifier never blocks
            print(f"news: presser classifier unavailable — no verdicts ({exc})")
            parsed = []
        dropped = 0
        for row in parsed:
            try:
                code = int(row["code"])
                verdict = str(row["verdict"])
                confidence = float(row.get("confidence", 0.0))
            except Exception:  # noqa: BLE001 — one bad row, not a bad batch
                dropped += 1
                continue
            if verdict not in VERDICTS or code not in by_code:
                dropped += 1
                continue
            key = text_hash(by_code[code].text)
            _store(cache_dir, key, {"verdict": verdict,
                                    "confidence": confidence, "model": model})
            rows.append({"code": code, "verdict": verdict,
                         "confidence": confidence, "model": model,
                         "text_hash": key, "fetched_at": stamp})
        if dropped:
            print(f"news: presser classifier dropped {dropped} malformed rows")

    if not rows:
        return pd.DataFrame(columns=CLASSIFIER_COLS)
    out = pd.DataFrame(rows)[CLASSIFIER_COLS]
    return out.drop_duplicates(subset=["code"]).reset_index(drop=True)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_classifier.py`
  Expected: `11 passed`, in a couple of seconds. If any test takes longer than the timeout it asserts, the fake CLI is not being used — stop and fix rather than raising the timeout.

- [ ] **Confirm the suite never names the real CLI.**

```bash
grep -rn "claude -p" tests/ || echo "clean"
```

Expected: `clean`.

- [ ] **Commit.**

```bash
git add src/gaffer/data/news/classifier.py tests/test_classifier.py && git commit -m "$(cat <<'EOF'
feat: F5 presser classifier over a configurable headless CLI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — F5: parsing "Further Detail" and attaching the verdicts

**Files:**
- Modify `src/gaffer/data/news/premierinjuries.py`
- Modify `tests/test_news_sources.py` (append)

`fetch_injuries` is the hook. It is the only non-protected function upstream of `availability_frame` that holds *both* free-text sources: the "Further Detail" cell it currently discards, and the bootstrap `news` column riding on the `players` frame it already receives. Nothing in `advise.py` moves.

- [ ] **Write the failing test.** Append to `tests/test_news_sources.py`:

```python
# --- v8a F5: the free text and the verdicts --------------------------------

_DETAIL_HTML = """
<table><tr>
<td>Player Bukayo Saka</td><td>Reason Hamstring Injury</td>
<td>Further Detail Arteta said he is close but Sunday may come too soon</td>
<td>Potential Return 20/09/2026</td><td>Status Doubtful</td>
</tr></table>
"""


def test_the_further_detail_cell_is_parsed_and_kept():
    """Today it is read only to be thrown away. It is the sharpest sentence
    on the page and the whole input to the classifier."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    out = parse_injury_table(_DETAIL_HTML)
    assert "further_detail" in out.columns
    assert "too soon" in out.iloc[0]["further_detail"]


def test_the_detail_never_reaches_the_injury_type():
    """A quote names body parts belonging to whatever else the sentence is
    about; the Reason column is still the only source of the type."""
    from gaffer.data.news.premierinjuries import parse_injury_table

    out = parse_injury_table(_DETAIL_HTML)
    assert out.iloc[0]["injury_type"] == "hamstring"


def test_a_disabled_classifier_makes_no_subprocess_call(tmp_path,
                                                        monkeypatch):
    from gaffer.data.news import premierinjuries as pi

    calls = []
    monkeypatch.setattr(pi, "classify_news",
                        lambda *a, **k: calls.append(1))
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=False)
    assert calls == []
    assert "llm_verdict" in out.columns and out["llm_verdict"].isna().all()


def test_the_shadow_pass_attaches_verdicts_without_serving_them(tmp_path,
                                                                monkeypatch):
    import pandas as pd

    from gaffer.data.news import premierinjuries as pi

    verdicts = pd.DataFrame([{"code": 1, "verdict": "rotation_risk",
                              "confidence": 0.8, "model": "fake",
                              "text_hash": "h", "fetched_at": "now"}])
    monkeypatch.setattr(pi, "classify_news", lambda *a, **k: verdicts)
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=True)
    assert set(out.columns) >= {"llm_verdict", "llm_confidence"}


def test_a_verdict_for_a_player_with_no_injury_row_still_travels(tmp_path,
                                                                 monkeypatch):
    """The bootstrap ``news`` column speaks about players the injury table
    never lists, and a verdict with no carrier row would be a verdict nobody
    ever logs."""
    import pandas as pd

    from gaffer.data.news import premierinjuries as pi

    verdicts = pd.DataFrame([{"code": 99, "verdict": "rotation_risk",
                              "confidence": 0.6, "model": "fake",
                              "text_hash": "h", "fetched_at": "now"}])
    monkeypatch.setattr(pi, "classify_news", lambda *a, **k: verdicts)
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=True)
    row = out[out["code"] == 99]
    assert len(row) == 1
    assert pd.isna(row.iloc[0]["injury_type"])


def test_a_classifier_that_dies_leaves_the_frame_alone(tmp_path, monkeypatch):
    from gaffer.data.news import premierinjuries as pi

    def boom(*a, **k):
        raise RuntimeError("the CLI is not logged in")

    monkeypatch.setattr(pi, "classify_news", boom)
    out = pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                            client=_client(_DETAIL_HTML), classifier=False,
                            shadow=True)
    assert out["llm_verdict"].isna().all()
```

The existing `_players()` fixture must carry a `news` column for the shadow tests; add `"news": ""` to it if it has none, and give code 99 a row so the verdict has a player to belong to.

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_news_sources.py -k detail or classifier`
  Expected: `KeyError: 'further_detail'`.

- [ ] **Write the implementation.** In `src/gaffer/data/news/premierinjuries.py`:

```python
INJURY_COLS = ["code", "injury_type", "news_status", "expected_return_date",
               "news_chance_pct", "further_detail", "llm_verdict",
               "llm_confidence", "source", "fetched_at"]

PARSE_COLS = ["name", "club", "injury_type", "status",
              "expected_return_date", "news_chance_pct", "further_detail"]
```

In `parse_injury_table`, keep the cell (the `rows.append` block gains one entry):

```python
            "news_chance_pct": pct,
            # Kept raw, and read by nothing but the classifier. The type
            # still comes off Reason alone — a manager's quote names body
            # parts belonging to whatever else the sentence is about.
            "further_detail": fields.get("Further Detail", "").strip(),
```

Add the imports and the hook. At the top:

```python
from gaffer.config import serving_config
from gaffer.data.news.classifier import NewsText, classify_news
```

Add the text-gathering helper before `fetch_injuries`:

```python
def news_texts(matched: pd.DataFrame,
               players: pd.DataFrame) -> list[NewsText]:
    """Every short free text this run has, one entry per player.

    Two sources, in precedence order: the injury table's "Further Detail"
    (a quote, and usually the sharper claim) and the bootstrap's ``news``
    column. A player carrying both contributes the detail only — one verdict
    per player, and two would need a precedence rule nobody has measured.
    """
    out: list[NewsText] = []
    seen: set[int] = set()
    if "further_detail" in matched.columns:
        for code, text in zip(matched["code"], matched["further_detail"]):
            if pd.notna(code) and str(text or "").strip():
                out.append(NewsText(int(code), str(text), "premierinjuries"))
                seen.add(int(code))
    if "news" in players.columns:
        for code, text in zip(players["code"], players["news"]):
            if (pd.notna(code) and int(code) not in seen
                    and str(text or "").strip()):
                out.append(NewsText(int(code), str(text), "bootstrap"))
    return out


def attach_verdicts(out: pd.DataFrame,
                    verdicts: pd.DataFrame) -> pd.DataFrame:
    """Join the classifier's rows on, adding carrier rows where needed.

    A verdict about a player the injury table never listed — most of the
    bootstrap's ``news`` column — has no row to ride on, and a verdict nobody
    logs is a verdict that was never worth running. Such a player gets a row
    whose every structured field is null, which the precedence table in
    :func:`~gaffer.data.news.normalize.availability_frame` reads as "no claim
    about this week" and leaves his official flag exactly where it was.
    """
    keyed = verdicts.drop_duplicates(subset=["code"]).set_index("code")
    out["llm_verdict"] = out["code"].map(keyed["verdict"])
    out["llm_confidence"] = pd.to_numeric(out["code"].map(keyed["confidence"]),
                                          errors="coerce")
    missing = [c for c in keyed.index if c not in set(out["code"])]
    if missing:
        extra = pd.DataFrame({"code": missing})
        for col in INJURY_COLS:
            if col not in extra.columns:
                extra[col] = None
        extra["llm_verdict"] = extra["code"].map(keyed["verdict"])
        extra["llm_confidence"] = pd.to_numeric(
            extra["code"].map(keyed["confidence"]), errors="coerce")
        extra["source"] = "llm"
        out = pd.concat([out, extra[INJURY_COLS]], ignore_index=True)
    return out
```

and extend `fetch_injuries`'s signature and tail:

```python
def fetch_injuries(players: pd.DataFrame, teams: pd.DataFrame,
                   cache_dir: Path = NEWS_CACHE, cache_hours: int = 6,
                   client: httpx.Client | None = None,
                   min_coverage: float = NEWS_MIN_COVERAGE,
                   now: datetime | None = None,
                   classifier: bool | None = None,
                   shadow: bool | None = None) -> pd.DataFrame:
    """The injury table as ``[code, injury_type, news_status, …]``.

    Empty on every failure — dead host, rewritten page, match rate below the
    floor — and an empty frame is what makes the whole layer inert.

    ``classifier``/``shadow`` default to the ``[news]`` config, read here
    because ``advise.py`` is protected and cannot forward them. This is the
    classifier's only call site: it is the one non-protected function holding
    both free-text sources — the "Further Detail" cell and the bootstrap's
    ``news`` column, which arrives on ``players``. With both false the
    subprocess is never launched and the columns come back all-null.
    """
```

with the tail becoming:

```python
    out = (out.sort_values("expected_return_date", na_position="first")
           .groupby("code", as_index=False).tail(1))
    out["further_detail"] = out.get("further_detail")
    out["llm_verdict"] = None
    out["llm_confidence"] = float("nan")
    cfg = serving_config()
    classifier = cfg.news_llm_classifier if classifier is None else classifier
    shadow = cfg.news_llm_shadow if shadow is None else shadow
    if classifier or shadow:
        try:
            texts = news_texts(out, players)
            if texts:
                verdicts = classify_news(texts, cmd=cfg.news_llm_command,
                                         timeout=cfg.news_llm_timeout_s)
                if verdicts is not None and not verdicts.empty:
                    out = attach_verdicts(out, verdicts)
        except Exception as e:  # noqa: BLE001 — the classifier never blocks
            print(f"news: presser classifier skipped ({e})")
    return out[INJURY_COLS].sort_values("code").reset_index(drop=True)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_news_sources.py tests/test_news_normalize.py`
  Expected: green.

- [ ] **Commit.**

```bash
git add src/gaffer/data/news/premierinjuries.py tests/test_news_sources.py && git commit -m "$(cat <<'EOF'
feat: F5 parse the Further Detail cell and attach classifier verdicts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 15 — F5: the presser shadow log

**Files:**
- Create `src/gaffer/data/news/presser_log.py`
- Create `tests/test_presser_log.py`
- Modify `src/gaffer/models/availability.py` (the serving pass)
- Modify `tests/test_availability_v8a.py` (append)

`apply_availability` is where `p_play` exists, so it is where "what serving *would* do" can be computed. It is also not protected. The log is written there and nowhere else.

- [ ] **Write the failing test.** Create `tests/test_presser_log.py`:

```python
"""The presser shadow log: what the classifier would have done."""

from __future__ import annotations

import pandas as pd

from gaffer.data.news.presser_log import (PRESSER_COLS, PRESSER_DAMP,
                                          PRESSER_PATH, append_presser,
                                          load_presser_log, presser_rows,
                                          would_factor)


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "p_play": 0.9, "llm_verdict": "rotation_risk",
         "llm_confidence": 0.8},
        {"code": 2, "gw": 5, "p_play": 0.8, "llm_verdict": "irrelevant",
         "llm_confidence": 0.4},
        {"code": 3, "gw": 5, "p_play": 0.7, "llm_verdict": None,
         "llm_confidence": None}])


def test_only_a_rotation_risk_would_change_a_number():
    """The other five verdicts either duplicate the structured feed or say
    nothing; a second damp on top of a parsed "Ruled Out" is double-counting
    one claim."""
    assert would_factor("rotation_risk") == PRESSER_DAMP
    for verdict in ("confirmed_starter", "knock", "assess", "ruled_out",
                    "irrelevant"):
        assert would_factor(verdict) == 1.0


def test_the_rows_carry_before_and_would():
    rows = presser_rows(_frame(), season="2026-27", gw=5, run_at="now")
    assert list(rows.columns) == PRESSER_COLS
    assert sorted(rows["code"]) == [1, 2]      # the unclassified row is absent
    first = rows.set_index("code").loc[1]
    assert first["p_play_before"] == 0.9
    assert round(first["p_play_would"], 4) == round(0.9 * PRESSER_DAMP, 4)


def test_a_frame_with_no_verdicts_writes_nothing():
    bare = _frame().drop(columns=["llm_verdict", "llm_confidence"])
    assert presser_rows(bare, season="2026-27", gw=5, run_at="now").empty


def test_the_log_appends_and_survives_a_reread(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = presser_rows(_frame(), season="2026-27", gw=5, run_at="t1")
    assert append_presser(rows) == 2
    later = presser_rows(_frame(), season="2026-27", gw=6, run_at="t2")
    assert append_presser(later) == 2
    back = load_presser_log()
    assert len(back) == 4
    assert set(back["gw"]) == {5, 6}
    assert (tmp_path / PRESSER_PATH).is_file()


def test_the_same_run_written_twice_is_banked_once(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = presser_rows(_frame(), season="2026-27", gw=5, run_at="t1")
    append_presser(rows)
    append_presser(rows)
    assert len(load_presser_log()) == 2


def test_an_absent_log_reads_as_an_empty_frame(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    out = load_presser_log()
    assert out.empty and list(out.columns) == PRESSER_COLS
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_presser_log.py`
  Expected: `ModuleNotFoundError: No module named 'gaffer.data.news.presser_log'`.

- [ ] **Write the implementation.** Create `src/gaffer/data/news/presser_log.py`:

```python
"""What the classifier would have done, banked whether or not it did it.

The N2 pattern, applied to F5: the verdicts are logged from the first run,
the serving flag stays off, and a season of "would have" against "did happen"
is what decides whether the flag ever gets flipped. Deleting the log to save
the flip a week of history is how a cycle ends with an unmeasurable feature.

Never raises: instrumentation does not block advice.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from gaffer.data import store

PRESSER_PATH = "live/presser_log.parquet"

PRESSER_COLS = ["season", "gw", "code", "verdict", "confidence",
                "p_play_before", "p_play_would", "run_at"]

PRESSER_DAMP = 0.8
"""What a ``rotation_risk`` verdict would multiply the first gameweek by.

Deliberately blunter than the line-up damp: a quote hinting at rotation is
weaker evidence than a published team sheet omitting him, and a number this
side of the ceiling cannot be the thing that benches a captain even if the
flag is flipped.
"""


def would_factor(verdict) -> float:
    """The factor serving *would* apply for a verdict (spec §5).

    Only ``rotation_risk`` moves a number. ``ruled_out``, ``knock`` and
    ``assess`` are claims the structured feed already carries — premierinjuries
    prints the status and the date, and damping again would count one injury
    twice. ``confirmed_starter`` is informational: the codebase's standing
    rule is that news lowers a number and never raises one.
    """
    return PRESSER_DAMP if str(verdict) == "rotation_risk" else 1.0


def presser_rows(frame: pd.DataFrame, season: str, gw: int,
                 run_at: str | None = None) -> pd.DataFrame:
    """One row per classified player, with before and would side by side."""
    if "llm_verdict" not in frame.columns:
        return pd.DataFrame(columns=PRESSER_COLS)
    part = frame[frame["llm_verdict"].notna()].copy()
    if part.empty:
        return pd.DataFrame(columns=PRESSER_COLS)
    part = part.drop_duplicates(subset=["code"])
    before = pd.to_numeric(part["p_play"], errors="coerce")
    factor = part["llm_verdict"].map(would_factor).astype("float64")
    out = pd.DataFrame({
        "season": str(season or ""),
        "gw": int(gw),
        "code": pd.to_numeric(part["code"], errors="coerce").astype("int64"),
        "verdict": part["llm_verdict"].astype("string"),
        "confidence": pd.to_numeric(part.get("llm_confidence"),
                                    errors="coerce"),
        "p_play_before": before,
        "p_play_would": before * factor,
        "run_at": str(run_at or datetime.now(timezone.utc).isoformat())})
    return out[PRESSER_COLS].reset_index(drop=True)


def append_presser(rows: pd.DataFrame) -> int:
    """Append ``rows``, atomically, deduplicated on the run's own key.

    Append-by-rewrite through a temp file and ``os.replace``, the same trade
    :func:`gaffer.snapshot.append_snapshot` makes: a job killed mid-parquet
    must not cost a season of history to save one afternoon. Two writes of one
    run bank once, so a hand re-run is free.
    """
    if rows is None or rows.empty:
        return 0
    existing = (store.load(PRESSER_PATH) if store.exists(PRESSER_PATH)
                else pd.DataFrame(columns=PRESSER_COLS))
    for col in PRESSER_COLS:
        if col not in existing.columns:
            existing[col] = None
    frames = [f[PRESSER_COLS] for f in (existing, rows) if not f.empty]
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["season", "gw", "code", "run_at"], keep="last")
    tmp_rel = PRESSER_PATH + ".tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(merged, tmp_rel)
        os.replace(tmp, store.DATA_DIR / PRESSER_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    return int(len(rows))


def load_presser_log() -> pd.DataFrame:
    """Every banked verdict, or an empty frame with the right columns."""
    if not store.exists(PRESSER_PATH):
        return pd.DataFrame(columns=PRESSER_COLS)
    return store.load(PRESSER_PATH)


def write_presser(frame: pd.DataFrame, season: str, gw: int) -> int:
    """Bank one run's verdicts. Rows written, or ``0`` on any failure."""
    try:
        return append_presser(presser_rows(frame, season, gw))
    except Exception as exc:  # noqa: BLE001 — instrumentation never blocks
        print(f"news: presser log not written ({exc})")
        return 0
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_presser_log.py`
  Expected: `6 passed`.

- [ ] **Write the failing wiring test.** Append to `tests/test_availability_v8a.py`:

```python
# --- F5: the shadow log and the gated serving damp -------------------------

def test_the_shadow_log_is_written_from_the_availability_pass(monkeypatch):
    banked = {}
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser",
                        lambda frame, season, gw: banked.update(
                            rows=len(frame), gw=gw) or len(frame))
    apply_availability(_pred(), _avail(llm_verdict="rotation_risk",
                                       llm_confidence=0.8), curves=None)
    assert banked["gw"] == 5


def test_the_verdict_changes_no_number_with_the_flag_off(monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    served = apply_availability(_pred(), _avail(llm_verdict="rotation_risk"),
                                curves=None)
    plain = apply_availability(_pred(), _avail(), curves=None)
    pd.testing.assert_frame_equal(served, plain)


def test_the_verdict_damps_the_first_gameweek_when_enabled(monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    out = apply_availability(_pred(), _avail(llm_verdict="rotation_risk"),
                             curves=None, llm_serving=True)
    by_gw = out.set_index("gw")
    assert by_gw.loc[5, "p_play"] == pytest.approx(0.9 * 0.8)
    assert by_gw.loc[6, "p_play"] == pytest.approx(0.9)


def test_a_log_that_fails_never_reaches_the_caller(monkeypatch):
    import gaffer.models.availability as av

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(av, "write_presser", boom)
    out = apply_availability(_pred(), _avail(llm_verdict="assess"),
                             curves=None)
    assert len(out) == 3
```

- [ ] **Wire it.** In `src/gaffer/models/availability.py`, add the import:

```python
from gaffer.data.news.presser_log import (PRESSER_COLS, would_factor,  # noqa: F401
                                          write_presser)
```

add the serving pass beside the others:

```python
def _presser_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply the classifier's verdict to the horizon's first gameweek.

    Only reached with ``[news] llm_classifier`` on, which v8a ships **off**:
    the mapping is measured in the shadow log for a season before it is
    allowed to move a number, the same ritual Z1 got. Same one-row-per-player
    rule as every other first-gameweek pass.
    """
    factor = out["llm_verdict"].map(would_factor).astype("float64")
    bites = _first_rows(out) & factor.notna() & (factor < 1.0)
    if not bites.any():
        return out
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * factor[bites]
    return out
```

and extend `apply_availability`'s signature and tail once more:

```python
def apply_availability(pred: pd.DataFrame, avail: pd.DataFrame,
                       curves: dict | None = None,
                       start_floor: float | None = None,
                       llm_serving: bool | None = None) -> pd.DataFrame:
```

```python
    if "absence_damp" in out.columns:
        out = _damp_first_gw(out)
    if "llm_verdict" in out.columns and out["llm_verdict"].notna().any():
        # Shadow first, always: the log records what serving *would* do
        # before anything is done, so the flag's evidence accrues from the
        # first run whether or not it is ever flipped (spec §5).
        from gaffer.config import serving_config
        cfg = serving_config()
        if "gw" in out.columns and len(out):
            try:
                write_presser(out[out["gw"] == out["gw"].min()],
                              str(cfg.current_season or ""),
                              int(out["gw"].min()))
            except Exception as exc:  # noqa: BLE001 — logging never blocks
                print(f"news: presser log not written ({exc})")
        if (cfg.news_llm_classifier if llm_serving is None else llm_serving):
            out = _presser_first_gw(out)
    return out.drop(columns=["status", "chance_of_playing"] + news_cols)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_availability_v8a.py tests/test_presser_log.py tests/test_availability.py`
  Expected: green; 19 passed in `tests/test_availability_v8a.py`.

- [ ] **Commit.**

```bash
git add src/gaffer/data/news/presser_log.py src/gaffer/models/availability.py tests/test_presser_log.py tests/test_availability_v8a.py && git commit -m "$(cat <<'EOF'
feat: F5 presser shadow log and the flag-gated serving damp

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 16 — G3: the v8a degradation rails

**Files:**
- Create `tests/test_v8a_degradation.py`

Follows `tests/test_v5_degradation.py`'s conventions exactly: byte-identity pins rather than "roughly the same numbers", zero-cost spies at the call site rather than inside the callee, per-source switches asserted independently, and the protected orderings copied forward verbatim so a later cycle that moves one has to move this file too.

- [ ] **Write the rails.** Create `tests/test_v8a_degradation.py`:

```python
"""The v8a degradation rails.

Six things are pinned:

1. The tenure asset absent -> club-season windows, the same columns, the same
   frame shape. A clone without ``data/manager_tenures.toml`` predicts.
2. The classifier disabled -> zero subprocess calls, asserted with a spy at
   the ``fetch_injuries`` call site rather than inside the classifier.
3. A classifier that raises, times out or returns nonsense -> availability
   byte-identical to the classifier-absent frame.
4. ``lineup_absence`` off -> the line-up frame and the availability output are
   the pre-v8a ones.
5. Every switch is independent: absence off does not disable the classifier,
   the classifier off does not disable the hint ceiling.
6. The protected source-text orderings still hold, copied forward from v5.

If a later task legitimately changes one of these, that task's *gate* says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.data.news.normalize import availability_frame
from gaffer.features.engineer import (ROTATION_PRIOR_FEATURES,
                                      add_rotation_priors,
                                      latest_rotation_priors)
from gaffer.models.availability import apply_availability


# --- rail 1: no tenure asset ----------------------------------------------

def _hist() -> pd.DataFrame:
    rows = []
    for i in range(6):
        when = pd.Timestamp("2023-08-05", tz="UTC") + pd.Timedelta(days=7 * i)
        for code in (1, 2):
            rows.append({"code": code, "team_code": 3, "season_idx": 1,
                         "gw": i + 1, "kickoff_time": when.isoformat(),
                         "starts": 1.0, "minutes": 90.0})
    return pd.DataFrame(rows)


def test_without_the_asset_every_prior_column_still_exists():
    out = add_rotation_priors(_hist(), None)
    assert list(out.columns)[-4:] == ROTATION_PRIOR_FEATURES
    assert out["manager_tenure_matches"].notna().all()


def test_without_the_asset_the_frame_shape_is_unchanged():
    with_asset = add_rotation_priors(_hist(), pd.DataFrame(
        {"team_code": [3], "club": ["X"], "manager": ["M"],
         "start_date": pd.to_datetime(["2023-01-01"], utc=True),
         "end_date": pd.to_datetime([None], utc=True)}))
    without = add_rotation_priors(_hist(), None)
    assert with_asset.shape == without.shape
    assert list(with_asset.columns) == list(without.columns)


def test_a_corrupt_asset_reaches_the_builder_as_none(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod
    from gaffer.data.managers import (MANAGER_TENURES_PATH,
                                      load_manager_tenures)

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    (tmp_path / MANAGER_TENURES_PATH).write_text("not toml [[", "utf-8")
    assert load_manager_tenures() is None
    assert not latest_rotation_priors(_hist(), None).empty


# --- rail 2: the classifier makes no calls when it is off ------------------

def _players() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "name": "A", "first_name": "A",
                          "second_name": "One", "team_code": 3,
                          "starts": 5, "minutes": 450, "news": "A knock"}])


def _teams() -> pd.DataFrame:
    return pd.DataFrame([{"code": 3, "name": "Arsenal",
                          "short_name": "ARS"}])


def test_the_classifier_is_never_launched_when_both_flags_are_off(tmp_path,
                                                                  monkeypatch):
    from gaffer.data.news import premierinjuries as pi

    calls: list[int] = []
    monkeypatch.setattr(pi, "classify_news",
                        lambda *a, **k: calls.append(1))
    monkeypatch.setattr(pi, "cached_text", lambda *a, **k: "")
    pi.fetch_injuries(_players(), _teams(), cache_dir=tmp_path,
                      classifier=False, shadow=False)
    assert calls == []


def test_no_test_in_this_repo_shells_out_to_the_real_cli():
    """G4 is the orchestrator's, on their machine. A suite that invoked the
    real binary would be a suite that fails on a machine nobody logged in."""
    from pathlib import Path

    for path in Path("tests").glob("test_*.py"):
        assert "claude -p" not in path.read_text(encoding="utf-8"), path


# --- rail 3: a broken classifier changes nothing ---------------------------

def _official() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "status": "a",
                          "chance_of_playing": None}])


def _pred() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "gw": g, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0} for g in (5, 6, 7)])


@pytest.mark.parametrize("verdicts", [None, pd.DataFrame()])
def test_a_classifier_that_answered_nothing_is_the_classifier_absent_path(
        verdicts, monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    injuries = pd.DataFrame([{"code": 1, "injury_type": None,
                              "news_status": None,
                              "expected_return_date": None,
                              "news_chance_pct": None, "further_detail": "",
                              "llm_verdict": None, "llm_confidence": None,
                              "source": "premierinjuries",
                              "fetched_at": "2026-09-04T09:00:00Z"}])
    frame = availability_frame(_official(), injuries, None, gw=5, events=None)
    with_dead = apply_availability(_pred(), frame, curves=None)
    without = apply_availability(_pred(), _official(), curves=None)
    for col in ("p_play", "p60", "e_min"):
        pd.testing.assert_series_equal(with_dead[col], without[col])


def test_a_verdict_present_but_unserved_is_arithmetically_inert(monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    avail = _official().assign(llm_verdict="rotation_risk",
                               llm_confidence=0.9)
    served = apply_availability(_pred(), avail, curves=None,
                                llm_serving=False)
    plain = apply_availability(_pred(), _official(), curves=None)
    pd.testing.assert_frame_equal(served, plain)


# --- rail 4: lineup_absence off is v7 ---------------------------------------

def test_absence_off_leaves_the_line_up_frame_at_its_pre_v8a_content(tmp_path,
                                                                     monkeypatch):
    from gaffer.data.news import lineups as ln

    monkeypatch.setattr(ln, "cached_text", lambda *a, **k: "")
    out = ln.fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                           absence=False)
    assert out.empty
    assert list(out.columns) == ln.LINEUP_COLS


def test_an_availability_frame_with_no_damp_is_the_v7_arithmetic():
    frame = availability_frame(_official(), None, None, gw=5, events=None)
    with_cols = apply_availability(_pred(), frame, curves=None)
    flags_only = apply_availability(_pred(), _official(), curves=None)
    assert list(with_cols.columns) == list(flags_only.columns)
    pd.testing.assert_frame_equal(with_cols, flags_only)


# --- rail 5: the switches are independent ---------------------------------

def test_absence_off_does_not_turn_the_hint_ceiling_off():
    avail = _official().assign(p_start_hint=0.25, absence_damp=None)
    out = apply_availability(_pred(), avail, curves=None)
    assert out.set_index("gw").loc[5, "p_play"] == pytest.approx(0.25)


def test_the_floor_being_off_does_not_turn_the_ceiling_off():
    avail = _official().assign(p_start_hint=0.0)
    out = apply_availability(_pred(), avail, curves=None, start_floor=0.0)
    assert out.set_index("gw").loc[5, "p_play"] == pytest.approx(0.0)


def test_the_news_master_switch_still_skips_every_fetcher(monkeypatch):
    """v5's rail, restated: v8a added arguments to both fetchers and neither
    may be reached with ``[news] enabled = false``."""
    from gaffer import advise as advise_mod

    calls: list[str] = []
    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: calls.append("injuries"))
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: calls.append("lineups"))
    cfg = Config(entry_id=1, league_id=2, news_enabled=False)
    events = pd.DataFrame({"gw": [5], "deadline_time": ["2026-09-05T10:00Z"]})
    out = advise_mod.news_availability(cfg, _players(), _teams(), events, gw=5)
    assert calls == []
    assert list(out.columns) == ["code", "status", "chance_of_playing"]


# --- rail 6: the protected orderings, copied forward -----------------------

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


def test_the_minutes_module_still_re_exports_the_availability_seam():
    from gaffer.models import minutes

    assert minutes.apply_availability is apply_availability
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_v8a_degradation.py`
  Expected: `17 passed`. Any red here is a real degradation failure, not a test to soften.

- [ ] **Commit.**

```bash
git add tests/test_v8a_degradation.py && git commit -m "$(cat <<'EOF'
test: the v8a degradation rails

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 17 — Adopt the arms G1 kept (orchestrator-directed)

**Files:**
- Modify `src/gaffer/models/train.py` (`MINUTES_FEATURES` and its docstring)

**Do not start this task until the orchestrator has run G1 and told you which arms passed.** The keep/withdraw list is `V8A_KEEP` in the driver's output, and the orchestrator's decision — not the line — is the instruction. If the list is empty, the whole of this task is the docstring: a failed arm ships OFF with its numbers recorded (CONVENTIONS.md §6), and the columns stay in the frame unused, exactly as v5 left congestion.

- [ ] **Write the pin first.** Append to `tests/test_train.py`:

```python
def test_the_minutes_feature_set_is_the_adopted_one():
    """The gate's verdict, pinned. A feature added to the frame is not a
    feature the model uses, and the difference is a whole cycle's measurement:
    this list is the one thing G1 licensed to change."""
    from gaffer.features.engineer import ROTATION_PRIOR_FEATURES

    adopted = [c for c in ROTATION_PRIOR_FEATURES if c in MINUTES_FEATURES]
    assert adopted == ADOPTED_V8A_FEATURES
```

with `ADOPTED_V8A_FEATURES` defined at the top of the test module as the exact list the orchestrator's G1 run kept — `[]` if none.

- [ ] **Run it, expecting failure** if any arm was kept, or **pass** if none was (in which case skip the next step and go straight to the docstring).
  `uv run pytest -q tests/test_train.py -k adopted`

- [ ] **Adopt.** In `src/gaffer/models/train.py`, extend `MINUTES_FEATURES` with exactly the kept columns — nothing else, in the driver's own order:

```python
MINUTES_FEATURES = ["minutes_r1", "minutes_r3", "minutes_r5", "minutes_r10",
                    "starts_r1", "starts_r3", "starts_r5", "starts_r10",
                    "days_rest", "home"] + ROTATION_FEATURES + KEPT_V8A
```

where `KEPT_V8A` is written out literally (e.g. `+ ["tenure_start_share", "xi_churn_r5"]`) rather than imported wholesale — an import would silently adopt a column a later cycle adds to `ROTATION_PRIOR_FEATURES` without a gate.

- [ ] **Record the measurement in the docstring**, whichever way the gate went. Append to `MINUTES_FEATURES`'s docstring:

```
v8a gate G1 ran a per-arm ablation on the 2024-25 walk-forward benchmark
(``scripts/v8a_arms.py``): baseline zeros/haulers/all RMSE <BASELINE>, and per
arm <ARM TABLE, one line each, verbatim from the V8A_ARM_DONE lines>. The rule
(spec §6) kept an arm only where zeros improved by >= 0.005 with neither
haulers nor all-RMSE regressing by > 0.005. Kept: <LIST>. Withdrawn: <LIST>.
The withdrawn arms' builders stay wired into ``load_training_frame`` and
``build_prediction_frame`` — the columns cost a fit nothing and the next cycle
re-measures them rather than rebuilding them.
```

Fill every placeholder from the orchestrator's log lines, transcribed verbatim (CONVENTIONS.md §4). A docstring left with `<LIST>` in it fails this task.

- [ ] **Run the suite.** `uv run pytest -q`
  Expected: green. `tests/test_train.py`'s synthetic frame covers any adopted column automatically — `_PLAYER_FEATURES` is derived from `MINUTES_FEATURES`.

- [ ] **Commit.**

```bash
git add src/gaffer/models/train.py tests/test_train.py && git commit -m "$(cat <<'EOF'
feat: adopt the v8a feature arms gate G1 kept

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 18 — Docs

**Files:**
- Modify `README.md`

- [ ] **Document the news keys.** In the Configuration section's TOML block, after the `[odds]` stanza, add:

```toml
[news]
enabled = true             # live injury / line-up sources
lineup_absence = true      # damp a regular the predicted XI left out
lineup_start_floor = 0.0   # off: never raise a p_play toward a predicted start
llm_classifier = false     # off: the presser classifier logs, never serves
llm_shadow = true          # log what it would have done
llm_command = "claude -p --output-format json"
```

and one line of prose beneath the block:

```markdown
The `[news]` block is optional — every key above is its default. `llm_*` drive
the presser classifier, which runs on your own Claude subscription through
whatever `llm_command` names and, with `llm_classifier = false`, only ever
writes `data/live/presser_log.parquet`.
```

- [ ] **Name the committed asset.** In "Where things live", add a line:

```markdown
- `data/manager_tenures.toml` — EPL head-coach spells; the one file under
  `data/` that is committed, because it is curated knowledge rather than
  fetched data (absent, the rotation features fall back to club-season windows)
```

- [ ] **Verify nothing else drifted.** `git diff --stat README.md`
  Expected: one file, roughly 15 insertions, no deletions.

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: the v8a news keys and the committed tenure asset

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 19 — Full suite, protected audit, and the gate checklist

**Files:** none modified. No frontend change was made this cycle, so `npx tsc --noEmit` is not run.

- [ ] **Run the whole suite.**

```bash
uv run pytest -q
```

Expected: green, with no skips introduced by this cycle other than `tests/test_manager_tenures.py` on a machine with no history parquet.

- [ ] **Audit the protected files — this must print nothing at all.**

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py 'src/gaffer/optimize/*' tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py 'tests/test_v5_degradation.py' 'tests/test_v6_degradation.py' 'tests/test_v7_degradation.py' scripts/s2_replay.py src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py
```

If any line appears, the cycle has failed spec §7: revert that file to `main`'s content and re-run the suite. (Adjust the `test_*_degradation.py` names to the ones the repo actually has — every existing one is protected.)

- [ ] **Audit what the cycle actually touched** — the list must be the files in the File structure table plus this plan and the spec, and must contain nothing under `reports/`, `models/`, `logs/`, `.claude/`, `config.toml`, or `data/` **other than** `data/manager_tenures.toml`.

```bash
git diff main --stat
git diff main --stat -- data/ | grep -v manager_tenures.toml || echo "no other data/ files staged"
```

- [ ] **Security ritual** (CONVENTIONS.md §8, run every time, not only when config was touched):

```bash
git diff main -- . | grep -nEi "api[_-]?key|secret|token|password" || echo "no secrets in the diff"
git show main:config.toml && echo "FAIL: config.toml is tracked" || echo "config.toml correctly untracked"
```

- [ ] **No commit.** This task changes no files; the orchestrator reviews the branch and runs the gates below.

### Gate checklist — run by the orchestrator, not by the implementer

Results are recorded in the spec's §9 Outcome block, transcribed verbatim from the log lines (CONVENTIONS.md §4). Nothing below is pre-filled.

- [ ] **G1 (features, primary).** Per-arm ablation on the 2024-25 walk-forward benchmark. Baseline first, then each arm, same code, same frame.

```bash
mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v8a_arms.py > logs/v8a_arms.log 2>&1 &
grep -e V8A_ARM_DONE -e V8A_VERDICT -e V8A_KEEP logs/v8a_arms.log
```

Verdict rule (pre-registered, spec §6): keep an arm iff zeros RMSE improves by ≥ 0.005 AND neither haulers nor all-stratum RMSE regresses by > 0.005. Ties and marginals withdraw. Record: baseline row, one row per arm, the keep list. **Task 17 does not start until this is done.**

- [ ] **G2 (holdout sanity).** After Task 17, on the shipped feature set:

```bash
caffeinate -i .venv/bin/python -c "
import json
from gaffer.evaluation import evaluate_current
p = evaluate_current()
print(json.dumps({'stratified': p['stratified']['all'],
                  'heads': {k: v['log_loss'] for k, v in p['heads'].items()}}, indent=1))"
```

Verdict: zeros RMSE must not regress against 1.053. Record the stratified table and all four head log losses, `p_start` included (F3).

- [ ] **G3 (degradation rails).**

```bash
uv run pytest -q tests/test_v8a_degradation.py tests/test_v5_degradation.py
```

Verdict: green, with the v5 rails untouched.

- [ ] **G4 (classifier smoke).** One real batch on the orchestrator's machine — the only place the real CLI is ever invoked.

```bash
caffeinate -i .venv/bin/python -c "
from gaffer.api.client import FPLClient
from gaffer.data.bootstrap import build_players, build_teams
from gaffer.data.news.premierinjuries import fetch_injuries
raw = FPLClient().get_bootstrap()
out = fetch_injuries(build_players(raw), build_teams(raw), shadow=True)
print(len(out), 'rows;', out['llm_verdict'].notna().sum(), 'verdicts')
print(out['llm_verdict'].value_counts().to_dict())"
uv run python -c "
from gaffer.data.news.presser_log import load_presser_log
d = load_presser_log(); print(len(d), 'log rows'); print(d.tail())"
uv run gaffer advise > /tmp/v8a_advise_after.txt
```

Verdict: ≥ 80% of returned rows schema-valid (no `dropped N malformed rows` line above 20% of the batch), `data/live/presser_log.parquet` written, and the advice output byte-identical to a run with `llm_classifier = false` — which is the shipped setting, so the second run is the control.

- [ ] **G5 (replay guard).** Gated S2 replay on the shipped feature set, three seed bases (CONVENTIONS.md §1).

```bash
caffeinate -i nohup .venv/bin/python scripts/v7b_replay.py --seed-bases 1876,1901,20260827 > logs/v8a_replay.log 2>&1 &
grep -e ARM_DONE -e MULTISEED_DONE logs/v8a_replay.log
```

Verdict: the season total's mean sits within the banked same-arm seed spread (25 pts on {1876, 1901}) of the pre-v8a baseline. A single draw is a residual, not a conclusion (CONVENTIONS.md §5).

- [ ] **Transcribe the evidence.** Every `*_ARM_DONE`, `*_VERDICT` and `MULTISEED_DONE` line above goes into the spec's §9 Outcome block verbatim — `logs/` is gitignored, and a verdict whose evidence lives on one laptop is a verdict nobody can re-read.
