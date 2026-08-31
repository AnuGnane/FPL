# Gaffer v8c Field Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** make gaffer's advice *relative*. Persist the top-10k squads the tier-EO scraper already samples and throws away, schedule that scrape, and stand a real mini-league Monte Carlo on top of it — replacing the parametric pairwise `win_probability` (fixed σ=18, `league_mode.py:326`) that currently underpins the league card, and adding a league what-if panel that answers "what does this captaincy actually do to my title odds".

**Architecture:** Four features on seams that are all new or already open.
`src/gaffer/data/tier_eo.py` grows a shared fetch (`fetch_sample_picks` / `eo_from_picks` / the three tier-cache helpers) and `tier_eo_table` becomes a five-line consumer of it — same cache file, same bytes, same `/api/live` payload. `src/gaffer/data/field.py` is new and owns the two stores: `data/raw/field/{season}/gw{N}.json` (the sampled squads, entry ids replaced by sample indices) and `data/live/field_eo_log.parquet` (the snapshot.py append-by-rewrite idiom), plus `run_field_scrape` — the never-raising body behind `gaffer field-scrape`, the `field-scrape` job kind and `scripts/com.gaffer.field.plist`. `src/gaffer/league_sim.py` is new and pure: `SimInputs` in, `LeagueSim` out, one seeded numpy draw per entry per simulation, σ read through `gaffer.optimize.scenarios`' public names (`scenario_noise`, `sigma_for`, `xmins_by_player_gw`, `NOISE_FLOOR_XMINS`, `NOISE_DENOM`) with zero diffs inside `optimize/**`. Two new routers serve it — `GET /api/league/sim` and `POST /api/league/whatif` — and neither touches `league.py`, so `/api/league/race` keeps emitting the old parametric list as the `legacy` fallback the UI degrades to.

`advise.py`, `optimize/**` and the tilt's λ machinery are untouched. The MC is measurement and display; feeding its win-EV back into λ is a later cycle with its own gate (spec §7).

**Tech Stack:** Python 3.12, uv, pandas/pyarrow/numpy, FastAPI + pydantic, pytest; React 19 + TypeScript + vitest + Radix tabs + Recharts.

**Prerequisite:** work on branch `feat/gaffer-v8c` cut from `main` **after v8a merges**. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v8c-field-intelligence-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 17 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`.
`src/gaffer/league_mode.py` is **not** on the list but is not edited by any task below either: the MC is a new module and `win_probability` keeps its callers. The v4d λ rails must stay green untouched.
If a task appears to need an edit inside a protected file, the plan is wrong — stop and report rather than editing.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/` or `config.toml`. v8c commits **no** data asset — both new stores are runtime artifacts under `data/`.

**Gate rule (CONVENTIONS.md §7):** implementers build the drivers and never run the gates. Task 17 is the checklist, unfilled.

**Anonymisation rule (spec §6):** the stored field sample keys entries by their index in the sample, never by their FPL entry id. No task may write an entry id to disk, and Task 1 pins that with a test that greps the payload.

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/data/field.py` | Create | F1: both field stores, the scrape body, the sword/shield read helper. |
| `tests/test_field_store.py` | Create | Store suite: schema, idempotence, atomic rewrite, anonymisation. |
| `src/gaffer/data/tier_eo.py` | Modify (docstring; new `fetch_sample_picks`, `eo_from_picks`, `tier_cache_path`, `read_tier_cache`, `write_tier_cache`; `tier_eo_table` becomes their consumer) | F1: one fetch path, shared with the field scrape. |
| `tests/test_tier_eo_v8c.py` | Create | The byte-compat rails for the refactor: same cache file, same numbers, same trickle. |
| `tests/test_field_scrape.py` | Create | `scrape_gw`, the D7 reuse guard, idempotence, never-raises. |
| `src/gaffer/config.py` | Modify (`Config` fields ~L69; `[league]` block ~L143) | Four new `[league]` keys. |
| `config.example.toml` | Modify (new `[league]` section) | Documents the four new keys **and** the eight pre-existing undocumented ones. |
| `tests/test_config_v8c.py` | Create | Key-by-key defaults and overrides. |
| `src/gaffer/cli.py` | Modify (two new commands after `snapshot`, ~L233) | `gaffer field-scrape`, `gaffer league-sim`. |
| `src/gaffer/web/job_kinds.py` | Modify (`run_field_scrape_job`; `JOB_KINDS` L95) | The eighth job kind. |
| `tests/test_web_job_kinds_v8c.py` | Create | Allow-list, row count, degradation, lazy import. |
| `scripts/com.gaffer.field.plist` | Create | Sat 12:30 + Sun 12:30 UK. |
| `scripts/install_automation.sh` | Modify (loop + echo) | Installs it. |
| `src/gaffer/league_sim.py` | Create | F2: `SimInputs`, `simulate_league`, `multi_seed`, the history JSON. |
| `tests/test_league_sim.py` | Create | Determinism, the `rival_drift=0` degenerate case, pins, quantiles. |
| `tests/test_league_sim_inputs.py` | Create | `build_inputs` over fake artifacts + a fake client. |
| `src/gaffer/web/schemas.py` | Modify (append the v8c models) | `LeagueSimData`, `LeagueWhatIfRequest`, `LeagueWhatIfResult`. |
| `src/gaffer/web/routers/league_sim.py` | Create | `GET /api/league/sim`, `POST /api/league/whatif`. |
| `src/gaffer/web/app.py` | Modify (import L26; `include_router` ~L74) | Registers it. |
| `tests/test_web_league_sim.py` | Create | Both endpoints over the `test_web_league.py` FakeClient pattern. |
| `src/gaffer/web/routers/players.py` | Modify (`field_class` + `PlayerRow` construction ~L95) | F4: `field_eo` / `field_class` from the log. |
| `tests/test_web_players_v8c.py` | Create | F4 suite: the classification, and the absent-log rail. |
| `frontend/src/types.ts` | Modify (`JOB_KINDS` L570; `JOB_KIND_LABEL` L575; new interfaces) | Lockstep with the router. |
| `frontend/src/types.test.ts` | Modify (the count pin) | Eight kinds. |
| `frontend/src/hubs/League.tsx` | Modify (tabs L106-110; win-prob card L172-195) | The upgraded card + the What-if tab. |
| `frontend/src/hubs/league/WhatIfSim.tsx` | Create | F3: the league what-if panel. |
| `frontend/src/hubs/league/WhatIfSim.test.tsx` | Create | Its suite. |
| `frontend/src/hubs/League.test.tsx` | Modify (append) | The upgraded card's suite. |
| `frontend/src/hubs/ThisWeek.tsx` | Modify (the Starting XI card action, ~L162-179) | The Δwin% chip. |
| `frontend/src/hubs/ThisWeek.test.tsx` | Modify (append) | Chip present / absent. |
| `frontend/src/hubs/Players.tsx` | Modify (`columns` ~L79) | F4: the field-EO column. |
| `frontend/src/hubs/Players.test.tsx` | Modify (append) | F4: unknown renders as an em dash, never a nought. |
| `frontend/src/hubs/players/ComparePanel.tsx` | Modify (the header rows) | F4: the field-EO row. |
| `frontend/src/hubs/Model.tsx` | Modify (the button row ~L41) | The Field scrape button. |
| `tests/test_v8c_degradation.py` | Create | G3 rails. |
| `README.md` | Modify (Configuration ~L61; Where things live ~L255; Automation ~L274) | The new keys, stores and job. |

---

## Task 1 — F1: the field stores

**Files:**
- Create `src/gaffer/data/field.py`
- Create `tests/test_field_store.py`

- [ ] **Write the failing test.** Create `tests/test_field_store.py`:

```python
"""The two field stores: what they hold, and what they refuse to hold.

The sample store is a permanent per-gameweek fact (the precedent is
``fetch_rival_picks_history``); the EO log is the growing instrument
(``snapshot.py``'s append-by-rewrite). The one hard rule across both is
anonymity: an entry id may never reach disk.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.field import (FIELD_EO_COLS, FIELD_EO_PATH, RAW_FIELD,
                               append_field_eo, field_eo_rows,
                               field_sample_path, latest_field_eo,
                               load_field_eo, load_field_sample,
                               save_field_sample)

PICKS = [
    [{"element": 7, "position": 1, "multiplier": 2},
     {"element": 8, "position": 12, "multiplier": 0}],
    [{"element": 7, "position": 1, "multiplier": 1},
     {"element": 9, "position": 2, "multiplier": 1}],
]

TABLE = {7: {"eo": 150.0, "se": 3.2, "n": 2},
         9: {"eo": 50.0, "se": 2.1, "n": 2}}


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return tmp_path


def test_the_sample_lands_at_the_documented_path(here):
    save_field_sample(PICKS, 3, "2026-27")
    assert field_sample_path("2026-27", 3).is_file()
    assert field_sample_path("2026-27", 3) == RAW_FIELD / "2026-27" / "gw3.json"


def test_the_stored_sample_carries_no_entry_id(here):
    """Spec §6: sample indices replace entry ids, and we keep no register of
    who was sampled. The test greps the raw bytes rather than the parsed
    object so a stray key cannot hide inside a nested dict."""
    save_field_sample(PICKS, 3, "2026-27")
    raw = field_sample_path("2026-27", 3).read_text()
    assert "entry" not in raw
    payload = json.loads(raw)
    assert [e["i"] for e in payload["entries"]] == [0, 1]


def test_the_sample_round_trips_as_the_picks_it_was_given(here):
    save_field_sample(PICKS, 3, "2026-27")
    assert load_field_sample("2026-27", 3) == PICKS


def test_an_absent_sample_is_none_not_an_empty_list(here):
    """``None`` is "never scraped"; ``[]`` would be "scraped and nobody was
    readable", and the scrape's idempotence check reads the difference."""
    assert load_field_sample("2026-27", 3) is None


def test_saving_twice_does_not_rewrite_the_first_answer(here):
    save_field_sample(PICKS, 3, "2026-27")
    before = field_sample_path("2026-27", 3).read_text()
    save_field_sample([[{"element": 1, "position": 1, "multiplier": 1}]],
                      3, "2026-27")
    assert field_sample_path("2026-27", 3).read_text() == before


def test_the_eo_rows_carry_the_log_schema_with_settled_dtypes(here):
    rows = field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12")
    assert list(rows.columns) == FIELD_EO_COLS
    assert rows["element"].dtype == "int64"
    assert rows["n"].dtype == "int64"
    assert rows["eo"].dtype == "float64"
    assert set(rows["element"]) == {7, 9}


def test_an_empty_table_is_zero_rows_not_a_raise(here):
    assert len(field_eo_rows({}, 3, "2026-27", day="2026-09-12")) == 0


def test_the_log_appends_and_reads_back(here):
    n = append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    assert n == 2
    assert len(load_field_eo()) == 2
    assert store.exists(FIELD_EO_PATH)


def test_a_second_scrape_of_the_same_day_replaces_rather_than_doubles(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    assert len(load_field_eo()) == 2


def test_a_later_day_accumulates_beside_the_first(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows(TABLE, 4, "2026-27", day="2026-09-19"))
    log = load_field_eo()
    assert len(log) == 4
    assert set(log["gw"]) == {3, 4}


def test_the_rewrite_leaves_no_temp_file_behind(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    assert not (store.DATA_DIR / (FIELD_EO_PATH + ".tmp")).exists()


def test_an_absent_log_reads_as_an_empty_frame_with_the_columns(here):
    out = load_field_eo()
    assert out.empty
    assert list(out.columns) == FIELD_EO_COLS


def test_the_latest_read_answers_the_newest_gameweek(here):
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows({7: {"eo": 10.0, "se": 1.0, "n": 2}},
                                  4, "2026-27", day="2026-09-19"))
    latest = latest_field_eo()
    assert set(latest) == {7}
    assert latest[7]["eo"] == 10.0
    assert latest[7]["gw"] == 4


def test_the_latest_read_of_an_absent_log_is_an_empty_dict(here):
    assert latest_field_eo() == {}


def test_two_scrapes_of_one_gameweek_keep_only_the_later_day(here):
    """The log is per (gw, snap_date); the *latest* view is one row per
    element, so a Saturday and a Sunday scrape of one gameweek must not both
    reach the sword/shield column."""
    append_field_eo(field_eo_rows(TABLE, 3, "2026-27", day="2026-09-12"))
    append_field_eo(field_eo_rows({7: {"eo": 99.0, "se": 1.0, "n": 2}},
                                  3, "2026-27", day="2026-09-13"))
    assert len(load_field_eo()) == 3
    assert latest_field_eo()[7]["eo"] == 99.0
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_field_store.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.data.field'`.

- [ ] **Write the implementation.** Create `src/gaffer/data/field.py`:

```python
"""The sampled field: the top-10k squads, kept, and their EO over time.

``tier_eo`` has sampled ~300 top-10k entries on every live poll since v7a and
thrown the squads away the moment it had an average. v8c keeps them. Two
stores, deliberately different in kind:

``data/raw/field/{season}/gw{N}.json``
    the sampled squads for one finished gameweek. A permanent per-gameweek
    fact, cached exactly like :func:`gaffer.data.league.fetch_rival_picks_history`
    caches a rival's played squad — it will never change, so a re-run costs no
    API calls at all. **Anonymous by construction**: the entry ids are dropped
    at the fetch boundary and replaced by the entry's index in the sample, so
    the file records what the field owned and not who owned it.

``data/live/field_eo_log.parquet``
    one row per (gameweek, scrape day, element). The growing instrument: EO
    with its standard error and its sample size, so "Haaland was 62% owned in
    the top 10k in GW7" is answerable in December. ``snapshot.py``'s
    append-by-rewrite idiom, keyed on (gw, snap_date) so a hand re-run is free.

Nothing here raises for a caller that is scheduled. :func:`run_field_scrape`
is the launchd body and swallows everything, exactly as
:func:`gaffer.snapshot.run_snapshot` does.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd

from gaffer.data import store
from gaffer.data.tier_eo import (RAW_TIER, TIER_SAMPLE, TIER_SEED,
                                 eo_from_picks, fetch_sample_picks,
                                 read_tier_cache, tier_cache_path,
                                 write_tier_cache)
from gaffer.snapshot import snap_date

RAW_FIELD = Path("data/raw/field")
"""Beside ``data/raw/league`` and ``data/raw/tier_eo``, not under ``live/``:
these are raw API payloads, not derived frames."""

FIELD_EO_PATH = "live/field_eo_log.parquet"

FIELD_EO_COLS = ["season", "gw", "snap_date", "element", "eo", "se", "n"]
"""``element``, not ``code``: the sample is picks straight off the API and a
pick names a season-scoped element. Joining to ``code`` is the *reader's* job
(``players.parquet`` carries both), because a code lookup at write time would
silently drop every player who left the game since the scrape."""

SAMPLE_PICK_KEYS = ("element", "position", "multiplier")
"""The only fields copied out of a pick. Everything else the API sends — and
in particular anything that could identify the entry — is dropped here."""

FIELD_REUSE_HOURS = 1.0
"""D7's courtesy window. A tier-EO cache file younger than this was written by
the live tracker minutes ago; the scrape reuses its numbers for the EO log
rather than firing another ~455 requests at the same endpoint in the same
hour. See :func:`run_field_scrape`."""


def field_sample_path(season: str, gw: int,
                      raw_dir: Path | str = RAW_FIELD) -> Path:
    return Path(raw_dir) / str(season) / f"gw{int(gw)}.json"


def save_field_sample(picks: list[list[dict]], gw: int, season: str,
                      raw_dir: Path | str = RAW_FIELD) -> Path:
    """Bank one gameweek's sampled squads. Idempotent, atomic, anonymous.

    A file that already exists is left exactly as it was rather than
    rewritten: the sample is drawn from a seeded slot list against a *live*
    standings page, so a second draw a day later is a different 300 people,
    and quietly replacing the banked one would rewrite history to match
    whenever the job last happened to run.
    """
    path = field_sample_path(season, gw, raw_dir)
    if path.exists():
        return path
    payload = {
        "season": str(season), "gw": int(gw), "n": len(picks),
        "entries": [
            {"i": i,
             "picks": [{k: int(p.get(k, 0)) for k in SAMPLE_PICK_KEYS}
                       for p in entry]}
            for i, entry in enumerate(picks)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def load_field_sample(season: str, gw: int,
                      raw_dir: Path | str = RAW_FIELD
                      ) -> list[list[dict]] | None:
    """The banked squads, or ``None`` when the gameweek was never scraped.

    ``None`` rather than ``[]`` because the scrape's idempotence check reads
    the difference: an empty list is "we sampled and nobody was readable",
    which is a fact worth not re-fetching.
    """
    path = field_sample_path(season, gw, raw_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt bank is a missing bank
        return None
    return [list(entry.get("picks") or [])
            for entry in payload.get("entries") or []]


def field_eo_rows(table: dict[int, dict], gw: int, season: str,
                  day: str | None = None) -> pd.DataFrame:
    """A tier-EO table -> dated log rows, one per element.

    Dtypes are forced here rather than left to pyarrow's inference, the same
    trade :func:`gaffer.snapshot.snapshot_rows` makes: a gameweek where every
    ``se`` came back 0.0 and one where they are floats would otherwise write
    two incompatible schemas into one growing file.
    """
    rows = [{"season": str(season or ""), "gw": int(gw),
             "snap_date": str(day or snap_date()),
             "element": int(element), "eo": float(cell.get("eo", 0.0)),
             "se": float(cell.get("se", 0.0)), "n": int(cell.get("n", 0))}
            for element, cell in sorted(table.items())]
    out = pd.DataFrame(rows, columns=FIELD_EO_COLS)
    for col in ("season", "snap_date"):
        out[col] = out[col].astype("object").astype("string")
    for col in ("gw", "element", "n"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0) \
            .astype("int64")
    for col in ("eo", "se"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
    return out[FIELD_EO_COLS]


def append_field_eo(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing the same (gw, snap_date) keys.

    :func:`gaffer.snapshot.append_snapshot`'s trade, one key wider: parquet
    has no append, a few hundred rows a week is cheap to re-emit, and
    replacement rather than accumulation is what makes a hand re-run free. The
    key is the *pair* because two gameweeks are scraped on two days but a
    Saturday and a Sunday pass over one gameweek are two rows for one fact and
    only the later one should stand.

    ``store.DATA_DIR`` is read here, not bound at import, so a test that
    redirects the data directory redirects both paths together.
    """
    if rows.empty:
        return 0
    existing = (store.load(FIELD_EO_PATH) if store.exists(FIELD_EO_PATH)
                else pd.DataFrame(columns=FIELD_EO_COLS))
    for col in FIELD_EO_COLS:
        if col not in existing.columns:
            existing[col] = None
    keys = set(zip(rows["gw"].astype(int).tolist(),
                   rows["snap_date"].astype(str).tolist()))
    kept = existing[[(int(g), str(d)) not in keys
                     for g, d in zip(existing["gw"], existing["snap_date"])]]
    frames = [f[FIELD_EO_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[FIELD_EO_COLS])
    tmp_rel = FIELD_EO_PATH + ".tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(merged, tmp_rel)
        os.replace(tmp, store.DATA_DIR / FIELD_EO_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    return int(len(rows))


def load_field_eo() -> pd.DataFrame:
    """Every banked row, or an empty frame with the right columns."""
    if not store.exists(FIELD_EO_PATH):
        return pd.DataFrame(columns=FIELD_EO_COLS)
    return store.load(FIELD_EO_PATH)


def latest_field_eo(gw: int | None = None) -> dict[int, dict]:
    """``element -> {"eo", "se", "n", "gw"}`` for the newest scrape.

    One row per element, from the latest ``snap_date`` of the latest gameweek
    (or of ``gw`` when one is named). The sword/shield column reads this, and
    a column that showed a Saturday number beside a Sunday one would be a
    column nobody could reason about.

    Empty dict on any failure at all — no log, an unreadable log, a log with
    no rows. F4 is display, and a missing display column is the documented
    degradation (spec §4).
    """
    try:
        log = load_field_eo()
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}
    if log.empty:
        return {}
    frame = log.copy()
    frame["gw"] = pd.to_numeric(frame["gw"], errors="coerce")
    frame = frame.dropna(subset=["gw"])
    if frame.empty:
        return {}
    want = int(gw) if gw is not None else int(frame["gw"].max())
    frame = frame[frame["gw"].astype(int) == want]
    if frame.empty:
        return {}
    day = max(str(d) for d in frame["snap_date"])
    frame = frame[frame["snap_date"].astype(str) == day]
    return {int(r.element): {"eo": float(r.eo), "se": float(r.se),
                             "n": int(r.n), "gw": want}
            for r in frame.itertuples()}
```

The scrape body arrives in Task 3; the imports it needs (`time`, `RAW_TIER`, `TIER_SAMPLE`, `TIER_SEED`, the five `tier_eo` names) are written now so Task 3 adds functions only. They come from Task 2, so this file does not import cleanly until Task 2 lands — run Task 1's tests with the placeholder import block below and replace it in Task 2's step, or run Tasks 1 and 2 back to back.

- [ ] **Unblock the import for this task only.** Until Task 2 adds the shared fetch, replace the `from gaffer.data.tier_eo import (...)` block above with:

```python
from gaffer.data.tier_eo import RAW_TIER, TIER_SAMPLE, TIER_SEED
```

Task 2's final step restores the full import.

- [ ] **Run to pass.** `uv run pytest -q tests/test_field_store.py`
  Expected: `15 passed`.

- [ ] **Commit.**

```bash
git add src/gaffer/data/field.py tests/test_field_store.py && git commit -m "$(cat <<'EOF'
feat: the field sample store and the top-10k EO log

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — F1: one fetch path, shared with `tier_eo_table`

**Files:**
- Modify `src/gaffer/data/tier_eo.py` (module docstring; new `tier_cache_path`, `read_tier_cache`, `write_tier_cache`, `fetch_sample_picks`, `eo_from_picks`; `tier_eo_table` rewritten over them)
- Modify `src/gaffer/data/field.py` (restore the full import)
- Create `tests/test_tier_eo_v8c.py`

The contract for this task is *no behaviour change*: same cache path, same JSON, same numbers, same sleep pattern, same `/api/live` payload. The refactor exists so the field scrape and the live tracker cannot drift apart, and the tests below are the rails that say so.

- [ ] **Write the failing test.** Create `tests/test_tier_eo_v8c.py`:

```python
"""The v8c refactor's rails: one fetch path, and the old one unchanged.

``tier_eo_table`` is now a five-line consumer of ``fetch_sample_picks`` and
``eo_from_picks``. Every assertion here is about that being invisible: the
cache file, the numbers in it, the trickle, and the empty-cached behaviour the
live tracker depends on.
"""

from __future__ import annotations

import json

import pytest

from gaffer.data.tier_eo import (eo_from_picks, eo_se, fetch_sample_picks,
                                 read_tier_cache, tier_cache_path,
                                 tier_eo_table, write_tier_cache)

PICKS = {
    101: [{"element": 7, "multiplier": 2}, {"element": 8, "multiplier": 1},
          {"element": 9, "multiplier": 0}],
    102: [{"element": 7, "multiplier": 1}, {"element": 8, "multiplier": 1}],
}


class FakeClient:
    """Two entries at page 1, and picks for both. Counts every call."""

    def __init__(self, picks=None, fail=()):
        self.picks = PICKS if picks is None else picks
        self.fail = set(fail)
        self.pages, self.fetched = [], []

    def get_league_standings(self, league_id, page=1):
        self.pages.append(page)
        return {"standings": {"results": [
            {"entry": 100 + slot} for slot in range(50)]}}

    def get_entry_picks(self, entry_id, gw):
        self.fetched.append((entry_id, gw))
        if entry_id in self.fail:
            raise RuntimeError("private entry")
        return {"picks": self.picks.get(entry_id, [])}


def test_the_shared_fetch_returns_squads_without_their_entry_ids(monkeypatch):
    """The anonymisation boundary is here, at the fetch: nothing downstream
    ever sees which entry a squad came from, so nothing downstream can leak
    it."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    out = fetch_sample_picks(FakeClient(), 3, sample=2)
    assert out == [PICKS[101], PICKS[102]]


def test_a_private_entry_is_one_fewer_sample_not_a_failure(monkeypatch):
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    out = fetch_sample_picks(FakeClient(fail=(101,)), 3, sample=2)
    assert out == [PICKS[102]]


def test_each_page_is_fetched_once_however_many_slots_it_serves(monkeypatch):
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2), (1, 3)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient()
    fetch_sample_picks(client, 3, sample=3)
    assert client.pages == [1]


def test_the_trickle_sleeps_between_entries_and_not_before_the_first(
        monkeypatch):
    """The anti-429 pause is the reason 455 requests are polite rather than
    rude. It has to survive the refactor, and it has to not cost a sleep on a
    one-entry sample."""
    slept = []
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.time.sleep", slept.append)
    fetch_sample_picks(FakeClient(), 3, sample=2)
    assert len(slept) == 1


def test_the_eo_estimator_is_the_one_the_tracker_has_always_shown():
    out = eo_from_picks([PICKS[101], PICKS[102]])
    # element 7: multipliers 2 and 1 over two entries -> 150%.
    assert out[7]["eo"] == 150.0
    assert out[7]["n"] == 2
    assert out[7]["se"] == round(eo_se(3.0, 5.0, 2), 1)
    # element 9 is benched by the only entry that owns him: EO contributions
    # are zero, so he is not in the table at all.
    assert 9 not in out


def test_no_readable_entry_is_an_empty_table_not_a_division_by_zero():
    assert eo_from_picks([]) == {}


def test_the_cache_helpers_round_trip_through_the_documented_path(tmp_path):
    assert tier_cache_path(3, tmp_path) == tmp_path / "3.json"
    write_tier_cache({7: {"eo": 1.0, "se": 0.1, "n": 2}}, 3, tmp_path)
    assert read_tier_cache(3, tmp_path) == {7: {"eo": 1.0, "se": 0.1, "n": 2}}


def test_the_cached_json_still_has_string_keys_on_disk(tmp_path):
    """The on-disk shape is a compatibility surface: a cache written by a
    v8a build must still load in a v8c one and vice versa."""
    write_tier_cache({7: {"eo": 1.0, "se": 0.1, "n": 2}}, 3, tmp_path)
    raw = json.loads((tmp_path / "3.json").read_text())
    assert list(raw) == ["7"]


def test_reading_an_absent_cache_is_none(tmp_path):
    assert read_tier_cache(3, tmp_path) is None


def test_the_table_writes_the_cache_and_serves_it_next_time(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient()
    first = tier_eo_table(client, 3, sample=2, raw_dir=tmp_path)
    calls = len(client.fetched)
    second = tier_eo_table(client, 3, sample=2, raw_dir=tmp_path)
    assert first == second
    assert len(client.fetched) == calls        # the second call fetched nothing


def test_an_empty_gameweek_is_cached_like_any_other(tmp_path, monkeypatch):
    """v7a's deliberate choice, unchanged: a gameweek where nobody's picks
    are readable is a fact about that gameweek, and re-sampling 300 entries on
    every tracker poll to rediscover it is the expensive way to learn it."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient(fail=(101,))
    assert tier_eo_table(client, 3, sample=1, raw_dir=tmp_path) == {}
    assert tier_cache_path(3, tmp_path).is_file()
    assert tier_eo_table(client, 3, sample=1, raw_dir=tmp_path) == {}
    assert len(client.fetched) == 1


def test_the_table_is_exactly_the_estimator_over_the_shared_fetch(
        tmp_path, monkeypatch):
    """The single-code-path claim, asserted rather than asserted-in-prose."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1), (1, 2)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)
    client = FakeClient()
    assert tier_eo_table(client, 3, sample=2, raw_dir=tmp_path) \
        == eo_from_picks([PICKS[101], PICKS[102]])
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_tier_eo_v8c.py`
  Expected: collection error — `ImportError: cannot import name 'eo_from_picks'`.

- [ ] **Write the implementation.** In `src/gaffer/data/tier_eo.py`, replace the module docstring's third paragraph (the "Display only" one) with:

```
v8c retired the display-only contract: ``gaffer field-scrape`` calls the same
fetch on a schedule, keeps the sampled squads in ``data/raw/field`` and logs
the EO to ``data/live/field_eo_log.parquet`` (see :mod:`gaffer.data.field`).
This module still owns the *fetch* and the *estimator*; it owns no store
beyond its own per-gameweek cache. Every failure mode (rate limit, page shape
change, a private entry) still degrades to fewer samples or to an empty table,
never to an exception that would take the tracker down.
```

Add the three cache helpers immediately after `eo_se` (~line 84):

```python
def tier_cache_path(gw: int, raw_dir: Path | str = RAW_TIER) -> Path:
    """The per-gameweek cache file. One definition, three callers.

    The field scrape reads this path's *mtime* to answer D7's question —
    "did the live tracker already pay for this fetch in the last hour?" — so
    the path has to be constructed in exactly one place.
    """
    return Path(raw_dir) / f"{int(gw)}.json"


def read_tier_cache(gw: int,
                    raw_dir: Path | str = RAW_TIER) -> dict[int, dict] | None:
    """The cached table with int keys, or ``None`` when there is no cache.

    ``None`` rather than ``{}``: an empty *table* is a cached fact ("nobody's
    picks were readable that gameweek"), and an empty *cache* is no fact at
    all. :func:`tier_eo_table` reads the difference and so does the scrape.
    """
    path = tier_cache_path(gw, raw_dir)
    if not path.exists():
        return None
    try:
        cached = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt cache is a missing cache
        return None
    return {int(key): value for key, value in cached.items()}


def write_tier_cache(table: dict[int, dict], gw: int,
                     raw_dir: Path | str = RAW_TIER) -> Path:
    """Persist the table. JSON object keys are strings by definition, so the
    ints go out stringly and :func:`read_tier_cache` converts them back."""
    path = tier_cache_path(gw, raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in table.items()}))
    return path
```

Add the shared fetch and the estimator after them:

```python
def fetch_sample_picks(client, gw: int, sample: int = TIER_SAMPLE,
                       seed: int = TIER_SEED) -> list[list[dict]]:
    """The sampled tier's squads for ``gw``, in sample order, ids dropped.

    The anonymisation boundary (spec §6). An entry id is needed to make the
    request and is needed for nothing afterwards, so it stops here: the result
    is a list, and an entry's identity is its index in that list. Nothing
    downstream can leak what it was never handed.

    The seed is offset by the gameweek exactly as v7a wrote it, so each week
    draws a different 300 and a season's logs are not one cohort's opinion.
    A page that will not load contributes no entries; an entry whose picks are
    private contributes no squad. Both are one fewer sample, never a raise.
    """
    entries = fetch_tier_entries(client, sample_slots(sample, seed + int(gw)))
    out: list[list[dict]] = []
    for i, entry in enumerate(entries):
        if i:
            time.sleep(FETCH_PAUSE_S)
        try:
            out.append(list(client.get_entry_picks(int(entry),
                                                   int(gw))["picks"]))
        except Exception:
            continue        # private or missing entry — one fewer sample
    return out


def eo_from_picks(picks_by_entry: list[list[dict]]) -> dict[int, dict]:
    """element -> {"eo", "se", "n"} over a list of sampled squads.

    Effective ownership in percent: captaincy counts double and the bench
    counts zero, so a value can exceed 100. A player nobody in the sample
    *started* is absent from the table rather than present at zero — the
    table is a sparse view of ~700 elements and the tracker reads a miss as
    "no sampled entry started him", which is the same statement.
    """
    n = len(picks_by_entry)
    if not n:
        return {}
    totals: dict[int, float] = {}
    sum_sq: dict[int, float] = {}
    for picks in picks_by_entry:
        for pick in picks:
            multiplier = int(pick.get("multiplier", 0))
            if multiplier <= 0:
                continue
            element = int(pick["element"])
            totals[element] = totals.get(element, 0.0) + multiplier
            sum_sq[element] = sum_sq.get(element, 0.0) + multiplier ** 2
    return {element: {"eo": round(total / n * 100, 1),
                      "se": round(eo_se(total, sum_sq[element], n), 1),
                      "n": n}
            for element, total in totals.items()}
```

Replace `tier_eo_table`'s body (keeping its docstring, with the sentence below appended to it) with:

```python
    cached = read_tier_cache(gw, raw_dir)
    if cached is not None:
        return cached
    out = eo_from_picks(fetch_sample_picks(client, gw, sample, seed))
    write_tier_cache(out, gw, raw_dir)
    return out
```

and append to that docstring, before the closing quotes:

```
    Since v8c this is a consumer of :func:`fetch_sample_picks` and
    :func:`eo_from_picks` rather than a second implementation of them, so the
    live tracker and ``gaffer field-scrape`` cannot compute two different
    numbers from one sample. The cache file and every value in it are
    unchanged — ``tests/test_tier_eo_v8c.py`` pins that.
```

- [ ] **Restore the full import in `field.py`.** Replace the placeholder line from Task 1 with:

```python
from gaffer.data.tier_eo import (RAW_TIER, TIER_SAMPLE, TIER_SEED,
                                 eo_from_picks, fetch_sample_picks,
                                 read_tier_cache, tier_cache_path,
                                 write_tier_cache)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_tier_eo_v8c.py tests/test_tier_eo.py tests/test_web_live.py tests/test_field_store.py`
  Expected: `12 passed` in the new file, and the pre-existing tier-EO quartet and live-router suite green and unmodified. If `tests/test_tier_eo.py` fails, the refactor changed behaviour — fix the refactor, never the test.

- [ ] **Commit.**

```bash
git add src/gaffer/data/tier_eo.py src/gaffer/data/field.py tests/test_tier_eo_v8c.py && git commit -m "$(cat <<'EOF'
refactor: one tier-EO fetch path, shared with the field scrape

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — F1: the scrape body

**Files:**
- Modify `src/gaffer/data/field.py` (append `fetch_field_sample`, `scrape_gw`, `run_field_scrape`)
- Create `tests/test_field_scrape.py`

- [ ] **Write the failing test.** Create `tests/test_field_scrape.py`:

```python
"""``gaffer field-scrape``: what it fetches, what it refuses to fetch twice,
and the one thing it must never do — raise."""

from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.field import (field_sample_path, load_field_eo,
                               load_field_sample, run_field_scrape, scrape_gw)
from gaffer.data.tier_eo import tier_cache_path, write_tier_cache

EVENTS = pd.DataFrame([
    {"gw": 1, "deadline_time": "2026-08-14T17:30:00Z", "is_current": False,
     "is_next": False, "finished": True, "data_checked": True},
    {"gw": 2, "deadline_time": "2026-08-21T17:30:00Z", "is_current": True,
     "is_next": False, "finished": True, "data_checked": False},
    {"gw": 3, "deadline_time": "2026-09-11T17:30:00Z", "is_current": False,
     "is_next": True, "finished": False, "data_checked": False},
])

PICKS = [[{"element": 7, "position": 1, "multiplier": 2},
          {"element": 8, "position": 2, "multiplier": 1}],
         [{"element": 7, "position": 1, "multiplier": 1},
          {"element": 9, "position": 2, "multiplier": 1}]]

CFG = Config(entry_id=1, league_id=5, current_season="2026-27")


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    monkeypatch.setattr("gaffer.data.field.RAW_TIER",
                        tmp_path / "data/raw/tier_eo")
    return tmp_path


@pytest.fixture()
def wired(here, monkeypatch):
    """Bootstrap, events and the shared fetch, all faked. Counts fetches."""
    calls = {"fetch": 0}

    def _fetch(client, gw, sample=300, seed=0):
        calls["fetch"] += 1
        calls["gw"] = int(gw)
        calls["sample"] = int(sample)
        return PICKS

    monkeypatch.setattr("gaffer.api.client.FPLClient",
                        lambda *a, **kw: object())
    monkeypatch.setattr("gaffer.data.bootstrap.build_events",
                        lambda raw: EVENTS)
    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks", _fetch)
    return calls


def test_the_target_is_the_last_gameweek_whose_deadline_has_passed():
    assert scrape_gw(EVENTS, now="2026-08-25T12:30:00Z") == 2
    assert scrape_gw(EVENTS, now="2026-09-12T12:30:00Z") == 3


def test_before_any_deadline_there_is_nothing_to_scrape():
    assert scrape_gw(EVENTS, now="2026-08-01T12:30:00Z") is None


def test_an_events_frame_with_no_deadlines_is_none():
    assert scrape_gw(pd.DataFrame(columns=["gw", "deadline_time"]),
                     now="2026-09-12T12:30:00Z") is None


def test_a_scrape_banks_the_squads_and_the_eo_rows(here, wired):
    rows = run_field_scrape(CFG, gw=2)
    assert rows == 3          # elements 7, 8, 9
    assert load_field_sample("2026-27", 2) == PICKS
    log = load_field_eo()
    assert set(log["element"]) == {7, 8, 9}
    assert set(log["gw"]) == {2}


def test_the_scrape_populates_the_tier_cache_the_tracker_reads(here, wired):
    """One fetch serves both readers: after a scrape the live tracker finds
    the gameweek already cached and fires nothing."""
    run_field_scrape(CFG, gw=2)
    raw = json.loads(tier_cache_path(2, here / "data/raw/tier_eo").read_text())
    assert raw["7"]["eo"] == 150.0


def test_a_second_run_of_the_same_gameweek_fetches_nothing(here, wired,
                                                           capsys):
    run_field_scrape(CFG, gw=2)
    capsys.readouterr()
    assert run_field_scrape(CFG, gw=2) == 0
    assert wired["fetch"] == 1
    assert "already banked" in capsys.readouterr().out


def test_force_re_runs_a_banked_gameweek(here, wired):
    run_field_scrape(CFG, gw=2)
    run_field_scrape(CFG, gw=2, force=True)
    assert wired["fetch"] == 2


def test_a_fresh_tier_cache_is_reused_rather_than_re_fetched(here, wired,
                                                             capsys):
    """D7. The live tracker paid for this gameweek's 455 requests minutes
    ago; the scrape logs its EO and fires nothing at the same endpoint in the
    same hour. No squads are banked, so the next run still has work to do."""
    write_tier_cache({7: {"eo": 12.0, "se": 1.0, "n": 300}}, 2,
                     here / "data/raw/tier_eo")
    rows = run_field_scrape(CFG, gw=2)
    assert wired["fetch"] == 0
    assert rows == 1
    assert load_field_sample("2026-27", 2) is None
    assert "reused" in capsys.readouterr().out


def test_a_stale_tier_cache_does_not_block_the_scrape(here, wired):
    path = tier_cache_path(2, here / "data/raw/tier_eo")
    write_tier_cache({7: {"eo": 12.0, "se": 1.0, "n": 300}}, 2,
                     here / "data/raw/tier_eo")
    old = time.time() - 7200
    import os
    os.utime(path, (old, old))
    assert run_field_scrape(CFG, gw=2) == 3
    assert wired["fetch"] == 1


def test_the_switch_off_fetches_nothing_at_all(here, wired, capsys):
    off = Config(entry_id=1, league_id=5, current_season="2026-27",
                 field_scrape=False)
    assert run_field_scrape(off, gw=2) is None
    assert wired["fetch"] == 0
    assert "field_scrape is off" in capsys.readouterr().out


def test_the_sample_size_comes_from_the_config(here, wired):
    run_field_scrape(Config(entry_id=1, league_id=5,
                            current_season="2026-27", field_sample=120), gw=2)
    assert wired["sample"] == 120


def test_a_gameweek_where_nobody_is_readable_writes_nothing(here, wired,
                                                            monkeypatch,
                                                            capsys):
    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks",
                        lambda *a, **kw: [])
    assert run_field_scrape(CFG, gw=2) is None
    assert load_field_sample("2026-27", 2) is None
    assert "no sampled entry" in capsys.readouterr().out


def test_a_dead_api_prints_one_line_and_never_raises(here, monkeypatch,
                                                     capsys):
    def _boom(*a, **kw):
        raise RuntimeError("FPL is down")

    monkeypatch.setattr("gaffer.api.client.FPLClient", _boom)
    assert run_field_scrape(CFG) is None
    out = capsys.readouterr().out
    assert "field scrape not written" in out
    assert "FPL is down" in out


def test_no_gameweek_yet_is_a_printed_line_not_a_failure(here, wired, capsys):
    monkeypatch_now = "2026-08-01T12:30:00Z"
    assert run_field_scrape(CFG, now=monkeypatch_now) is None
    assert "no gameweek deadline" in capsys.readouterr().out
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_field_scrape.py`
  Expected: `ImportError: cannot import name 'run_field_scrape'`.

- [ ] **Write the implementation.** Append to `src/gaffer/data/field.py`:

```python
def fetch_field_sample(client, gw: int, *, sample: int = TIER_SAMPLE,
                       seed: int = TIER_SEED, season: str = "",
                       raw_dir: Path | str = RAW_FIELD
                       ) -> tuple[list[list[dict]], dict[int, dict]]:
    """``(squads, eo_table)`` for one gameweek, from the bank or from the API.

    The bank is consulted first, so calling this twice for one gameweek costs
    nothing — which is what makes the scrape idempotent and what makes a
    replay over banked weeks free. The EO table is recomputed from the squads
    rather than stored beside them: it is a five-line reduction of data we
    already have, and two copies of a derived number is two copies to get out
    of step.
    """
    banked = load_field_sample(season, gw, raw_dir)
    if banked is not None:
        return banked, eo_from_picks(banked)
    picks = fetch_sample_picks(client, gw, sample, seed)
    return picks, eo_from_picks(picks)


def scrape_gw(events: pd.DataFrame, now=None) -> int | None:
    """The gameweek to scrape: the last one whose deadline has passed.

    Post-deadline is the whole point — picks are 404 before it and public
    after it — so this is deliberately *not*
    :func:`gaffer.snapshot.next_unfinished_gw`, which answers a question about
    the news cycle. A Saturday 12:30 run lands on the gameweek being played
    right now, which is exactly the squad we want a record of.

    ``None`` before the season's first deadline, or for an events frame with
    no readable deadline at all.
    """
    if "deadline_time" not in events.columns or events.empty:
        return None
    when = pd.to_datetime(now, errors="coerce", utc=True) if now is not None \
        else pd.Timestamp.now(tz="UTC")
    deadlines = pd.to_datetime(events["deadline_time"], errors="coerce",
                               utc=True)
    passed = events[deadlines.notna() & (deadlines <= when)]
    if passed.empty:
        return None
    return int(pd.to_numeric(passed["gw"], errors="coerce").max())


def _tier_cache_age_s(gw: int, raw_dir: Path | str = RAW_TIER) -> float | None:
    """Seconds since the live tracker last wrote this gameweek's tier cache,
    or ``None`` when it never has."""
    path = tier_cache_path(gw, raw_dir)
    if not path.exists():
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def run_field_scrape(cfg=None, gw: int | None = None, *, force: bool = False,
                     now=None) -> int | None:
    """Bank one gameweek's field sample and its EO. Rows logged, or ``None``.

    The launchd body, and therefore held to ``run_snapshot``'s contract: one
    printed line whatever happens, and no exception ever leaves this function.
    A missed Saturday is a far cheaper failure than a job that dies loudly at
    12:30 every weekend until somebody uninstalls it.

    Four early exits, each with its own sentence, because "nothing happened"
    has four different meanings here and a scheduled job's log is the only
    place anybody will read them:

    * the switch is off;
    * no deadline has passed yet (pre-season, or a scheduled run in an
      international break);
    * the gameweek is already banked — the idempotence line, and the one the
      Sunday run prints every week the Saturday run worked;
    * D7's courtesy: the live tracker paid for this gameweek's ~455 requests
      inside the last :data:`FIELD_REUSE_HOURS`, so its numbers are logged and
      *nothing is fetched*. No squads are banked on that path, deliberately —
      the tier cache holds an aggregate and the sample store holds squads, and
      inventing the latter from the former is not available. The next run
      finds no bank and does the real work.

    Imports are local for ``cli.py --help``'s sake, the same reason
    :func:`gaffer.snapshot.run_snapshot` gives.
    """
    try:
        from gaffer.api.client import FPLClient
        from gaffer.config import load_config
        from gaffer.data.bootstrap import build_events

        cfg = cfg or load_config()
        if not getattr(cfg, "field_scrape", True) and not force:
            print("field scrape skipped: league.field_scrape is off")
            return None
        season = str(getattr(cfg, "current_season", "") or "")
        client = FPLClient()
        if gw is None:
            gw = scrape_gw(build_events(client.get_bootstrap()), now=now)
        if gw is None:
            print("field scrape skipped: no gameweek deadline has passed yet")
            return None
        gw = int(gw)

        if not force and load_field_sample(season, gw, RAW_FIELD) is not None:
            banked = load_field_sample(season, gw, RAW_FIELD) or []
            print(f"field sample for gw{gw} already banked "
                  f"({len(banked)} entries) — nothing fetched.")
            return 0

        age = _tier_cache_age_s(gw, RAW_TIER)
        if not force and age is not None and age < FIELD_REUSE_HOURS * 3600:
            table = read_tier_cache(gw, RAW_TIER) or {}
            day = snap_date()
            rows = append_field_eo(field_eo_rows(table, gw, season, day))
            print(f"Field scrape: reused the live tracker's tier-EO fetch "
                  f"for gw{gw} ({rows} EO rows at {day}); no squads sampled.")
            return rows

        picks, table = fetch_field_sample(
            client, gw, sample=int(getattr(cfg, "field_sample", TIER_SAMPLE)),
            season=season, raw_dir=RAW_FIELD)
        if not picks:
            print(f"field scrape not written: no sampled entry had readable "
                  f"picks for gw{gw}")
            return None
        save_field_sample(picks, gw, season, RAW_FIELD)
        write_tier_cache(table, gw, RAW_TIER)
        day = snap_date()
        rows = append_field_eo(field_eo_rows(table, gw, season, day))
        print(f"Field scrape: {len(picks)} entries, {rows} EO rows for "
              f"gw{gw} at {day}.")
        return rows
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"field scrape not written: {exc}")
        return None
```

Note the two module-level `Path` constants are read through the module globals (`RAW_FIELD`, `RAW_TIER`) rather than defaulted into the signature, so a test that monkeypatches them redirects the scrape too — the same reason `snapshot.py` reads `store.DATA_DIR` at call time.

- [ ] **Run to pass.** `uv run pytest -q tests/test_field_scrape.py tests/test_field_store.py`
  Expected: `14 passed` in the new file, `15 passed` in the store file.

- [ ] **Commit.**

```bash
git add src/gaffer/data/field.py tests/test_field_scrape.py && git commit -m "$(cat <<'EOF'
feat: the field-scrape body, idempotent and courteous to the live tracker

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the four config keys, and the eight that were never documented

**Files:**
- Modify `src/gaffer/config.py` (`Config` fields after `tier_sample` ~L70; the `[league]` reads ~L144)
- Modify `config.example.toml` (new `[league]` section, after `[odds]`)
- Create `tests/test_config_v8c.py`

- [ ] **Write the failing test.** Create `tests/test_config_v8c.py`:

```python
"""v8c's `[league]` keys: their defaults, and that they are really read."""

from __future__ import annotations

import tomllib
from pathlib import Path

from gaffer.config import Config, load_config

BASE = '[fpl]\nentry_id = 1\nleague_id = 5\n'


def _cfg(tmp_path, extra=""):
    path = tmp_path / "config.toml"
    path.write_text(BASE + extra)
    return load_config(path)


def test_every_new_key_has_a_shipping_default(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.field_scrape is True
    assert cfg.field_sample == cfg.tier_sample
    assert cfg.sim_n == 2000
    assert cfg.rival_drift == 0.5


def test_the_dataclass_defaults_match_the_loader_defaults():
    """A Config built in a test must be the same object the loader builds
    from an empty section, or every router test lies about production."""
    plain = Config(entry_id=1, league_id=5)
    assert (plain.field_scrape, plain.sim_n, plain.rival_drift) \
        == (True, 2000, 0.5)


def test_the_sample_size_defaults_to_the_tier_sample_it_shares(tmp_path):
    """One scrape serves both readers, so one number sizes it. Setting
    tier_sample alone must move the field scrape with it."""
    cfg = _cfg(tmp_path, "\n[league]\ntier_sample = 120\n")
    assert cfg.field_sample == 120


def test_the_sample_size_can_still_be_set_apart(tmp_path):
    cfg = _cfg(tmp_path, "\n[league]\ntier_sample = 120\nfield_sample = 400\n")
    assert cfg.tier_sample == 120
    assert cfg.field_sample == 400


def test_every_key_is_read_from_the_file(tmp_path):
    cfg = _cfg(tmp_path, "\n[league]\nfield_scrape = false\nsim_n = 50\n"
                         "rival_drift = 0.0\n")
    assert cfg.field_scrape is False
    assert cfg.sim_n == 50
    assert cfg.rival_drift == 0.0


def test_the_example_file_documents_every_league_key():
    """config.example.toml is the only documentation most of these keys have
    ever had — spec §6 says the section arrives complete or not at all."""
    raw = tomllib.loads(Path("config.example.toml").read_text())
    league = raw.get("league") or {}
    for key in ("z_scale", "lambda_cap", "sigma_floor", "sigma_cap",
                "sigma_min_weeks", "z_deadband", "tier_eo", "tier_sample",
                "field_scrape", "field_sample", "sim_n", "rival_drift"):
        assert key in league, f"[league] {key} is undocumented"


def test_the_example_file_still_loads(tmp_path):
    """A documented default that the loader rejects is worse than no
    documentation: it is a config file that looks copy-pasteable and is not."""
    text = Path("config.example.toml").read_text()
    path = tmp_path / "config.toml"
    path.write_text(text.replace("entry_id = 0", "entry_id = 1"))
    cfg = load_config(path)
    assert cfg.sim_n == 2000
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_config_v8c.py`
  Expected: `AttributeError: 'Config' object has no attribute 'field_scrape'`.

- [ ] **Write the implementation.** In `src/gaffer/config.py`, add the four fields immediately after `tier_sample: int = 300`:

```python
    # v8c. field_scrape schedules the tier sample the live tracker already
    # takes lazily; field_sample defaults to tier_sample rather than to a
    # number of its own, because one scrape serves both readers and two
    # sample sizes for one sample is a bug waiting for a Saturday. ``None``
    # here means "not set" and is resolved against tier_sample by the loader.
    field_scrape: bool = True
    field_sample: int = 300
    sim_n: int = 2000
    rival_drift: float = 0.5
```

and add the four reads to the `[league]` block, immediately after `tier_sample=`:

```python
        field_scrape=bool(league.get("field_scrape", True)),
        field_sample=int(league.get("field_sample",
                                    league.get("tier_sample", 300))),
        sim_n=int(league.get("sim_n", 2000)),
        rival_drift=float(league.get("rival_drift", 0.5)),
```

- [ ] **Document the section.** In `config.example.toml`, insert after the `[odds]` block and before `[data]`:

```toml
[league]
# League mode is gated by fpl.league_id, not by a switch here: set that and
# the tilt turns on. These are its dials, and every one of them ships at the
# value below — this section exists to name them, not to change them.
z_scale = 1.5             # points of gap per unit of z before the tilt moves
lambda_cap = 0.5          # the most the tilt may ever bend the board
sigma_floor = 8.0         # weekly points sigma the gap is measured in...
sigma_cap = 30.0          # ...clamped both ends, because a short season
sigma_min_weeks = 6       # gameweeks of history before sigma is estimated
z_deadband = 0.25         # |z| under this is noise: no tilt at all

# The top-10k sample. tier_eo is the live tracker's EO column; field_scrape
# is v8c's scheduled version of the same fetch, which also keeps the sampled
# squads (anonymously) so the league Monte Carlo has a field to drift toward.
tier_eo = true
tier_sample = 300
field_scrape = true
field_sample = 300        # defaults to tier_sample when unset

# The mini-league Monte Carlo behind /api/league/sim.
sim_n = 2000              # simulations per run; 2000 is ~1s at league size 50
# How far a rival's squad drifts toward the field template over the run.
# 0.0 freezes every rival's current squad — the analytic sanity case.
rival_drift = 0.5
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_config_v8c.py tests/test_config.py`
  Expected: `7 passed` in the new file, no regression in the existing config suite.

- [ ] **Commit.**

```bash
git add src/gaffer/config.py config.example.toml tests/test_config_v8c.py && git commit -m "$(cat <<'EOF'
feat: v8c [league] config keys, and the eight that were never documented

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — D6: the CLI command, the job kind and the launchd plist

**Files:**
- Modify `src/gaffer/cli.py` (new `field_scrape` command after `snapshot`, ~L233)
- Modify `src/gaffer/web/job_kinds.py` (`run_field_scrape_job`; `JOB_KINDS`)
- Create `tests/test_web_job_kinds_v8c.py`
- Create `scripts/com.gaffer.field.plist`
- Modify `scripts/install_automation.sh`

- [ ] **Write the failing test.** Create `tests/test_web_job_kinds_v8c.py`:

```python
"""v8c's eighth job kind: field-scrape.

The pattern is ``tests/test_web_job_kinds_v7c.py``'s, because the contract is
the snapshot kind's contract — a body that never raises, a wrapper that turns
its answer into a row count, and a lazy import so ``gaffer --help`` does not
pay for pandas."""

from __future__ import annotations

from gaffer.web import job_kinds


def test_the_field_scrape_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["field-scrape"] \
        is job_kinds.run_field_scrape_job


def test_the_allow_list_is_the_eight_kinds_the_frontend_knows():
    """Lockstep with ``frontend/src/types.ts``'s JOB_KINDS: the browser sends
    one of these strings and a kind the router does not know is a 404."""
    assert sorted(job_kinds.JOB_KINDS) == [
        "advise", "advise-fast", "evaluate", "field-scrape", "news-shadow",
        "refresh-data", "snapshot", "track-pens"]


def test_the_job_reports_the_rows_it_logged(monkeypatch, capsys):
    monkeypatch.setattr("gaffer.data.field.run_field_scrape",
                        lambda: 512)
    assert job_kinds.run_field_scrape_job() == {"rows": 512}
    assert "512" in capsys.readouterr().out


def test_a_degraded_scrape_is_still_a_finished_job(monkeypatch):
    """``run_field_scrape`` answers ``None`` on any bad Saturday — a dead
    API, a switch that is off, a gameweek that has not kicked off. The job
    reports zero rows rather than failing the run."""
    monkeypatch.setattr("gaffer.data.field.run_field_scrape", lambda: None)
    assert job_kinds.run_field_scrape_job() == {"rows": 0}


def test_an_already_banked_gameweek_is_a_zero_row_success(monkeypatch):
    monkeypatch.setattr("gaffer.data.field.run_field_scrape", lambda: 0)
    assert job_kinds.run_field_scrape_job() == {"rows": 0}


def test_the_wrapper_imports_lazily():
    import inspect

    source = inspect.getsource(job_kinds)
    assert "from gaffer.data.field import" not in source.split("def ")[0]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_job_kinds_v8c.py`
  Expected: `AttributeError: module 'gaffer.web.job_kinds' has no attribute 'run_field_scrape_job'`.

- [ ] **Write the job kind.** In `src/gaffer/web/job_kinds.py`, add after `run_track_pens`:

```python
def run_field_scrape_job() -> dict:
    """``gaffer field-scrape`` — the top-10k field sample (v8c F1).

    ``run_field_scrape`` prints its own result line and answers ``None`` on
    every failure, so the only work here is turning that into the row count
    the job record carries. Zero rows is a success, not a failure: it is what
    an already-banked gameweek looks like, which is what the Sunday run sees
    every week the Saturday run worked.
    """
    from gaffer.data.field import FIELD_EO_PATH, run_field_scrape

    rows = int(run_field_scrape() or 0)
    print(f"Logged {rows} field-EO rows to {FIELD_EO_PATH}.")
    return {"rows": rows}
```

and add the entry to `JOB_KINDS`, after `"snapshot"`:

```python
    "field-scrape": run_field_scrape_job,
```

- [ ] **Write the CLI command.** In `src/gaffer/cli.py`, add after the `snapshot` command:

```python
@app.command()
def field_scrape(
        gw: int = typer.Option(0, help="Gameweek to scrape (default: the "
                                       "last one whose deadline has passed)."),
        force: bool = typer.Option(False, "--force",
                                   help="Re-scrape a gameweek already "
                                        "banked.")):
    """Bank the top-10k field sample and its EO for a gameweek (v8c F1).

    The launchd job's body, and held to ``snapshot``'s contract: it prints its
    own line and never fails. A scheduled command that exits non-zero on a bad
    Saturday is a command that gets uninstalled.
    """
    try:
        from gaffer.data.field import run_field_scrape

        run_field_scrape(gw=gw or None, force=force)
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # run_field_scrape swallows its own failures; the import cannot, and
        # an ImportError here would be the one traceback the launchd job
        # still emits every weekend.
        typer.echo(f"field scrape not written: {exc}")
```

Typer turns the underscore into a hyphen, so the command is `gaffer field-scrape` and matches the job kind's name exactly.

- [ ] **Write the plist.** Create `scripts/com.gaffer.field.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.field</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer field-scrape &gt;&gt; logs/field.log 2&gt;&amp;1</string>
  </array>
  <!-- Saturday and Sunday at 12:30, an hour after the 11:30 deadline: picks
       are public post-deadline and 404 before it. Two slots rather than one
       because a Sunday-only gameweek has no Saturday squad to sample and a
       Saturday run that failed gets a second chance the next day. Both are
       no-ops in seconds when the gameweek is already banked. -->
  <key>StartCalendarInterval</key><array>
    <dict><key>Weekday</key><integer>6</integer>
          <key>Hour</key><integer>12</integer>
          <key>Minute</key><integer>30</integer></dict>
    <dict><key>Weekday</key><integer>0</integer>
          <key>Hour</key><integer>12</integer>
          <key>Minute</key><integer>30</integer></dict>
  </array>
</dict></plist>
```

- [ ] **Wire the installer.** In `scripts/install_automation.sh`, change the loop line and the echo:

```sh
for name in advise prices snapshot field; do
```

```sh
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot + Sat/Sun 12:30 field scrape."
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_job_kinds_v8c.py tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py tests/test_web_jobs_api.py`
  Expected: `6 passed` in the new file, no regression in the three existing job suites. `tests/test_web_jobs.py` is protected and must not be touched.

- [ ] **Check the CLI registers.** `uv run gaffer --help | grep field-scrape`
  Expected: one line naming `field-scrape`. This shells out to typer only — no network, no data.

- [ ] **Validate the plist.** `plutil -lint scripts/com.gaffer.field.plist`
  Expected: `scripts/com.gaffer.field.plist: OK`.

- [ ] **Commit.**

```bash
git add src/gaffer/cli.py src/gaffer/web/job_kinds.py tests/test_web_job_kinds_v8c.py scripts/com.gaffer.field.plist scripts/install_automation.sh && git commit -m "$(cat <<'EOF'
feat: gaffer field-scrape, its job kind and its weekend launchd job

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — F2: the mini-league Monte Carlo

**Files:**
- Create `src/gaffer/league_sim.py`
- Create `tests/test_league_sim.py`

The engine is deliberately *simple arithmetic under a seeded draw*, not a squad simulator: each entry gets a mean and a standard deviation for the rest of the season, and the season is one multivariate-normal draw per simulation. That is what makes 2,000 runs of a 50-entry league a fraction of a second, what makes `rival_drift=0` an exactly-checkable degenerate case, and what makes the what-if panel's pins a closed-form edit to two numbers rather than a re-simulation of a squad.

- [ ] **Write the failing test.** Create `tests/test_league_sim.py`:

```python
"""The mini-league Monte Carlo: its arithmetic, its seed, and its floor.

Every number this module produces is published in the UI, so CONVENTIONS.md
applies: the router serves one fixed seed and the CLI reports a spread. What
is pinned here is that the seed *works* — same seed, same answer — and that
the degenerate cases are exactly what they claim to be.
"""

from __future__ import annotations

import pytest

from gaffer.league_sim import (Entry, Pins, SimInputs, WEEKLY_SIGMA_FLOOR,
                               entry_rate, entry_sigma, multi_seed,
                               simulate_league)

EP = {7: 6.0, 8: 4.0, 9: 1.0}
SIGMA = {7: 3.0, 8: 2.0, 9: 1.0}


def _me(total=200, picks=None):
    return Entry(entry=1, name="You FC", total=total, is_me=True,
                 picks=picks or [{"element": 7, "multiplier": 2},
                                 {"element": 8, "multiplier": 1}])


def _rival(entry=2, total=150, picks=None):
    return Entry(entry=entry, name=f"Rival {entry}", total=total,
                 picks=picks or [{"element": 9, "multiplier": 1}])


def _inputs(entries=None, weeks_left=10, field_rate=None):
    return SimInputs(entries=entries or [_me(), _rival()],
                     ep_by_element=EP, sigma_by_element=SIGMA,
                     weeks_left=weeks_left, field_rate=field_rate)


def test_an_entrys_rate_counts_the_captain_twice():
    assert entry_rate(_me(), EP) == pytest.approx(6.0 * 2 + 4.0)


def test_a_benched_pick_contributes_nothing():
    entry = _me(picks=[{"element": 7, "multiplier": 1},
                       {"element": 8, "multiplier": 0}])
    assert entry_rate(entry, EP) == pytest.approx(6.0)


def test_an_unknown_element_contributes_nothing_rather_than_raising():
    """A rival owning a player who is not in this week's component frame — a
    new signing, a player removed from the game — must not take the league
    card down."""
    entry = _rival(picks=[{"element": 999, "multiplier": 1}])
    assert entry_rate(entry, EP) == 0.0


def test_the_sigma_adds_in_quadrature_and_doubles_with_the_armband():
    """Variances add; a captain's *variance* is four times his own, because
    his points are doubled before they are added."""
    expected = (4 * 3.0 ** 2 + 2.0 ** 2) ** 0.5
    assert entry_sigma(_me(), SIGMA) == pytest.approx(
        max(expected, WEEKLY_SIGMA_FLOOR))


def test_an_entry_of_unknown_players_still_has_the_floor():
    """Zero variance would make a squad's season a certainty. Nothing in FPL
    is, and a league where one entry cannot vary is a league whose win
    probabilities are all 0 or 1."""
    entry = _rival(picks=[{"element": 999, "multiplier": 1}])
    assert entry_sigma(entry, SIGMA) == pytest.approx(WEEKLY_SIGMA_FLOOR)


def test_the_same_seed_gives_the_identical_answer():
    a = simulate_league(_inputs(), n=500, seed=7)
    b = simulate_league(_inputs(), n=500, seed=7)
    assert a.p_win == b.p_win
    assert a.per_rival == b.per_rival
    assert a.margin_quantiles == b.margin_quantiles


def test_a_different_seed_gives_a_different_draw():
    a = simulate_league(_inputs(), n=500, seed=7)
    b = simulate_league(_inputs(), n=500, seed=8)
    assert (a.p_win, a.exp_finish) != (b.p_win, b.exp_finish)


def test_a_dominant_leader_wins_almost_every_time():
    """The ``rival_drift=0`` sanity case: a rival with a strictly dominated
    squad and a huge deficit cannot catch up, and the number has to say so."""
    out = simulate_league(_inputs(entries=[_me(total=400), _rival(total=100)]),
                          n=2000, seed=11, rival_drift=0.0)
    assert out.p_win > 0.99
    assert out.per_rival[0]["p_beat"] > 0.99


def test_a_dominated_manager_wins_almost_never():
    out = simulate_league(_inputs(entries=[_me(total=100), _rival(total=400)]),
                          n=2000, seed=11, rival_drift=0.0)
    assert out.p_win < 0.01


def test_with_no_weeks_left_the_table_is_the_table():
    """Nothing is left to play: the standings *are* the result, and a Monte
    Carlo over them must be unanimous rather than merely confident."""
    out = simulate_league(_inputs(entries=[_me(total=300), _rival(total=200)],
                                  weeks_left=0), n=100, seed=3)
    assert out.p_win == 1.0
    assert out.exp_finish == 1.0
    assert out.margin_quantiles["p50"] == 100.0


def test_drift_zero_leaves_every_rival_on_his_own_squad():
    """The degenerate case has to be exact, not approximate: at drift 0 the
    field template is not consulted at all, so passing one changes nothing."""
    frozen = simulate_league(_inputs(field_rate=999.0), n=500, seed=5,
                             rival_drift=0.0)
    none = simulate_league(_inputs(field_rate=None), n=500, seed=5,
                           rival_drift=0.0)
    assert frozen.p_win == none.p_win


def test_drift_moves_a_weak_rival_toward_the_field_and_costs_me_odds():
    """A rival on a 1-point-a-week squad who is allowed to transfer toward a
    50-point-a-week field is a bigger threat than one who is not."""
    entries = [_me(total=300), _rival(total=280)]
    frozen = simulate_league(SimInputs(entries=entries, ep_by_element=EP,
                                       sigma_by_element=SIGMA, weeks_left=20,
                                       field_rate=60.0),
                             n=2000, seed=5, rival_drift=0.0)
    drifting = simulate_league(SimInputs(entries=entries, ep_by_element=EP,
                                         sigma_by_element=SIGMA,
                                         weeks_left=20, field_rate=60.0),
                               n=2000, seed=5, rival_drift=1.0)
    assert drifting.p_win < frozen.p_win


def test_my_own_squad_never_drifts():
    """The field template is a model of what *rivals* do. Drifting my own
    squad toward it would be modelling gaffer as an average manager, which is
    the one thing the whole project disputes."""
    entries = [_me(total=300), _rival(total=300)]
    ins = SimInputs(entries=entries, ep_by_element=EP, sigma_by_element=SIGMA,
                    weeks_left=20, field_rate=0.0)
    # A field rate of zero drags every drifting entry toward nothing. If mine
    # drifted too, both would fall together and p_win would not move.
    frozen = simulate_league(ins, n=2000, seed=5, rival_drift=0.0)
    drifting = simulate_league(ins, n=2000, seed=5, rival_drift=1.0)
    assert drifting.p_win > frozen.p_win


def test_the_top_three_probability_is_never_below_the_win_probability():
    entries = [_me()] + [_rival(entry=i, total=190 + i) for i in range(2, 8)]
    out = simulate_league(_inputs(entries=entries), n=1000, seed=4)
    assert out.p_top3 >= out.p_win
    assert 1.0 <= out.exp_finish <= len(entries)


def test_a_small_league_reports_top_three_as_a_certainty():
    """Three entries: everybody is in the top three, and the headline must
    not imply otherwise."""
    out = simulate_league(_inputs(entries=[_me(), _rival(2), _rival(3)]),
                          n=200, seed=4)
    assert out.p_top3 == 1.0


def test_every_rival_gets_a_row_in_league_order():
    entries = [_me(), _rival(2, total=300), _rival(3, total=100)]
    out = simulate_league(_inputs(entries=entries), n=200, seed=4)
    assert [r["entry"] for r in out.per_rival] == [2, 3]
    assert out.per_rival[0]["p_beat"] < out.per_rival[1]["p_beat"]


def test_the_margin_fan_is_ordered_and_named():
    out = simulate_league(_inputs(), n=1000, seed=4)
    keys = ["p05", "p25", "p50", "p75", "p95"]
    assert list(out.margin_quantiles) == keys
    values = [out.margin_quantiles[k] for k in keys]
    assert values == sorted(values)


def test_the_result_records_how_it_was_produced():
    """A published probability with no seed and no n beside it is a number
    nobody can reproduce — CONVENTIONS.md §1's whole complaint."""
    out = simulate_league(_inputs(), n=250, seed=9, rival_drift=0.25)
    assert (out.n, out.seed, out.rival_drift, out.weeks_left) \
        == (250, 9, 0.25, 10)


def test_a_league_of_one_is_a_win(monkeypatch):
    out = simulate_league(_inputs(entries=[_me()]), n=50, seed=1)
    assert out.p_win == 1.0
    assert out.per_rival == []
    assert out.margin_quantiles["p50"] == 0.0


# --- pins ------------------------------------------------------------------


def test_a_blank_pin_removes_that_players_week_from_every_owner():
    """The what-if primitive: pinning element 7 to a blank costs me twelve
    points of week-one mean (he is my captain) and costs the rival nothing,
    because the rival does not own him."""
    plain = simulate_league(_inputs(), n=2000, seed=6)
    blanked = simulate_league(_inputs(), n=2000, seed=6,
                              pins=Pins(scores={7: 0.0}))
    assert blanked.p_win < plain.p_win


def test_a_haul_pin_moves_the_other_way():
    plain = simulate_league(_inputs(), n=2000, seed=6)
    hauled = simulate_league(_inputs(), n=2000, seed=6,
                             pins=Pins(scores={7: 20.0}))
    assert hauled.p_win > plain.p_win


def test_pinning_a_player_nobody_owns_changes_nothing():
    plain = simulate_league(_inputs(), n=500, seed=6)
    pinned = simulate_league(_inputs(), n=500, seed=6,
                             pins=Pins(scores={999: 20.0}))
    assert pinned.p_win == plain.p_win


def test_no_pins_at_all_is_the_unpinned_run():
    """G3's rail, asserted at the engine rather than only at the router."""
    assert simulate_league(_inputs(), n=500, seed=6, pins=Pins()) \
        == simulate_league(_inputs(), n=500, seed=6)


def test_a_captain_override_re_points_my_armband_for_the_week():
    """Element 8 captained instead of 7 costs me (6 - 4) points of week-one
    mean, so the odds fall."""
    plain = simulate_league(_inputs(), n=2000, seed=6)
    swapped = simulate_league(_inputs(), n=2000, seed=6,
                              pins=Pins(captain_override=8))
    assert swapped.p_win < plain.p_win


def test_overriding_to_the_incumbent_captain_changes_nothing():
    assert simulate_league(_inputs(), n=500, seed=6,
                           pins=Pins(captain_override=7)) \
        == simulate_league(_inputs(), n=500, seed=6)


def test_a_captain_override_on_a_player_i_do_not_own_is_ignored():
    """The panel offers my own XI, but a stale tab could send anything, and a
    router that armbanded a player I do not own would be answering a
    different question than the one on screen."""
    assert simulate_league(_inputs(), n=500, seed=6,
                           pins=Pins(captain_override=999)) \
        == simulate_league(_inputs(), n=500, seed=6)


def test_a_rival_captain_blank_helps_me():
    rival = _rival(picks=[{"element": 9, "multiplier": 2}])
    ins = _inputs(entries=[_me(total=250), rival])
    plain = simulate_league(ins, n=2000, seed=6)
    blanked = simulate_league(ins, n=2000, seed=6,
                              pins=Pins(rival_captain_blanks=2))
    assert blanked.p_win >= plain.p_win


def test_pins_only_touch_the_first_week():
    """A pin is an event in the gameweek being played, not a season-long
    change of ability. With one week left it is the whole run; with twenty it
    is a twentieth of it, and the effect has to shrink accordingly."""
    short = _inputs(weeks_left=1)
    long = _inputs(weeks_left=20)
    d_short = (simulate_league(short, n=3000, seed=6).p_win
               - simulate_league(short, n=3000, seed=6,
                                 pins=Pins(scores={7: 0.0})).p_win)
    d_long = (simulate_league(long, n=3000, seed=6).p_win
              - simulate_league(long, n=3000, seed=6,
                                pins=Pins(scores={7: 0.0})).p_win)
    assert d_short > d_long


def test_pins_with_no_weeks_left_are_inert():
    out = simulate_league(_inputs(weeks_left=0), n=100, seed=6,
                          pins=Pins(scores={7: 0.0}))
    assert out.p_win == 1.0


# --- multi-seed ------------------------------------------------------------


def test_the_multi_seed_report_carries_a_mean_and_a_spread():
    """CONVENTIONS.md §1: a published claim reads mean +/- spread, never one
    draw. The CLI prints this and the spec's G2 records it."""
    out = multi_seed(_inputs(), seeds=[1, 2, 3], n=400)
    assert out["seeds"] == [1, 2, 3]
    assert len(out["p_win"]) == 3
    assert out["p_win_mean"] == pytest.approx(sum(out["p_win"]) / 3)
    assert out["p_win_spread"] == pytest.approx(max(out["p_win"])
                                                - min(out["p_win"]))


def test_a_single_seed_reports_a_spread_of_zero_rather_than_hiding_it():
    out = multi_seed(_inputs(), seeds=[1], n=100)
    assert out["p_win_spread"] == 0.0
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_league_sim.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.league_sim'`.

- [ ] **Write the implementation.** Create `src/gaffer/league_sim.py`:

```python
"""The mini-league Monte Carlo: who actually wins this thing.

``league_mode.win_probability`` answers one pairwise question with a fixed
sigma of 18 and a normal approximation: "do I finish above *him*". That is not
the question the league card is asking. Winning a ten-team league is not
beating the leader — it is beating all nine at once, with everyone's squad,
everyone's captain and everyone's transfers in play, and no product of pairwise
normals gets there.

So: simulate the thing. Every entry gets a mean and a standard deviation for
the remaining season, the season is one seeded draw per entry per simulation,
and the answers fall out of counting. What the engine deliberately is *not*:

* not a squad simulator. Rival transfer *prediction* is parked (spec §7); what
  is modelled is drift — over a season a rival's squad converges on the field
  template, and ``rival_drift`` says how far. At 0 nobody transfers at all,
  which is an exactly-checkable degenerate case rather than a rhetorical one.
* not week-correlated. Player noise is independent week to week, the same
  assumption ``optimize.scenarios.noise_ep`` documents and for the same
  reason: minutes risk really is close to independent once the fixture is
  known.
* not part of advice. Nothing here reaches the tilt or the MILP. ``advise.py``
  and ``optimize/**`` are zero-diff this cycle; the sigma table is read
  through ``scenarios``' public names and nothing else (spec D4).

Every published number carries its ``n``, its ``seed`` and its
``rival_drift``, because a probability nobody can reproduce is a decoration.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from gaffer import artifacts
from gaffer.optimize.scenarios import (NOISE_DENOM, NOISE_FLOOR_XMINS,
                                       scenario_noise, sigma_for,
                                       xmins_by_player_gw)

SIM_N = 2000
SIM_SEED = 20260831
"""The router's fixed seed. One seed serves the card so a page refresh does
not reshuffle the headline; the CLI's ``--seeds`` is where the honesty label
comes from (CONVENTIONS.md §1)."""

WEEKLY_SIGMA_FLOOR = 6.0
"""Points of weekly standard deviation no entry falls below.

An entry whose players are all missing from the component frame — a rival on a
squad of new signings, or a league read before the first advise run — would
otherwise have zero variance and a season that is a certainty. Six points is
about a third of the ~18 the old parametric model used for a whole squad, so
it is a floor rather than a second model."""

HAUL_SIGMA = 2.0
"""How many player-sigmas above his mean a "haul" pin puts a player. Two is
the conventional two-sigma event, and it is a *stated* convention rather than
a fitted one — the panel's job is to price a scenario the user names, not to
tell him how likely it was."""

MARGIN_QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
MARGIN_KEYS = ["p05", "p25", "p50", "p75", "p95"]

SIM_HISTORY = "league_sim_history.json"
"""Under ``artifacts.REPORTS``. Read at call time, not bound at import."""


@dataclass
class Entry:
    """One manager in the race, with the squad he last played."""

    entry: int
    name: str
    total: int
    picks: list[dict] = field(default_factory=list)
    is_me: bool = False


@dataclass
class SimInputs:
    """Everything the simulation needs, and nothing that fetches anything.

    ``ep_by_element`` and ``sigma_by_element`` are *per gameweek* — a player's
    expected points and estimation sigma for one week, averaged over whatever
    horizon the component frame covers. ``field_rate`` is the sampled field's
    mean weekly rate under the same numbers, or ``None`` when the field store
    has nothing for this gameweek; drift is then off whatever ``rival_drift``
    says, which is the documented degradation.
    """

    entries: list[Entry]
    ep_by_element: dict[int, float]
    sigma_by_element: dict[int, float]
    weeks_left: int
    field_rate: float | None = None


@dataclass
class Pins:
    """Events pinned into the first simulated week (spec D5).

    ``scores`` maps an element to the points he is *declared* to score that
    week, for every entry that owns him — which is the whole point: a blank
    from a 60%-owned captain is not a blank for me, it is a blank for
    everybody who owns him and a free hit for everybody who does not.
    """

    scores: dict[int, float] = field(default_factory=dict)
    captain_override: int | None = None
    rival_captain_blanks: int | None = None


@dataclass
class LeagueSim:
    """What one seeded run of the league says."""

    p_win: float
    p_top3: float
    exp_finish: float
    per_rival: list[dict]
    margin_quantiles: dict[str, float]
    n: int
    seed: int
    weeks_left: int
    rival_drift: float


def entry_rate(entry: Entry, ep_by: dict[int, float]) -> float:
    """One entry's expected points in one gameweek.

    Multiplier-weighted, so the bench (multiplier 0) contributes nothing and
    the captain contributes twice — which is exactly how FPL scores it, and
    exactly what ``effective_ownership`` already assumes. A pick whose element
    the component frame does not carry contributes nothing rather than raising:
    a rival who bought a player gaffer has never modelled must not take the
    league card down.
    """
    return float(sum(int(p.get("multiplier", 0))
                     * float(ep_by.get(int(p["element"]), 0.0))
                     for p in entry.picks))


def entry_sigma(entry: Entry, sigma_by: dict[int, float]) -> float:
    """One entry's weekly standard deviation, floored.

    Variances add and the captain's points are doubled before they are added,
    so his *variance* enters four times. The floor is
    :data:`WEEKLY_SIGMA_FLOOR` — see its docstring for why zero is not an
    acceptable answer.
    """
    var = sum((int(p.get("multiplier", 0))
               * float(sigma_by.get(int(p["element"]), 0.0))) ** 2
              for p in entry.picks)
    return max(math.sqrt(max(var, 0.0)), WEEKLY_SIGMA_FLOOR)


def _week_one(entry: Entry, ins: SimInputs, pins: Pins) -> tuple[float, float]:
    """``(mean, variance)`` for the first simulated week under ``pins``.

    A pinned player's contribution stops being a random variable: his mean
    becomes the declared score times his multiplier and his variance leaves
    the sum entirely. That is what makes "if Haaland blanks" a *pin* rather
    than a re-weighting — the scenario is asserted, not sampled.
    """
    captain = pins.captain_override
    swap_captain = (entry.is_me and captain is not None
                    and any(int(p["element"]) == int(captain)
                            for p in entry.picks)
                    and any(int(p.get("multiplier", 0)) >= 2
                            for p in entry.picks))
    blank_captain = (not entry.is_me
                     and pins.rival_captain_blanks is not None
                     and int(pins.rival_captain_blanks) == int(entry.entry))
    mean, var = 0.0, 0.0
    for pick in entry.picks:
        element = int(pick["element"])
        mult = int(pick.get("multiplier", 0))
        if swap_captain:
            # One armband, moved: the incumbent drops to a single share and
            # the named player takes the double. A bench player named as
            # captain is not offered by the panel and is not honoured here.
            if mult >= 2:
                mult = 1
            elif element == int(captain):
                mult = 2
        if mult <= 0:
            continue
        if blank_captain and mult >= 2:
            continue          # his armband scored nothing; his XI still plays
        if element in pins.scores:
            mean += mult * float(pins.scores[element])
            continue
        mean += mult * float(ins.ep_by_element.get(element, 0.0))
        var += (mult * float(ins.sigma_by_element.get(element, 0.0))) ** 2
    return mean, var


def _mu_sd(entry: Entry, ins: SimInputs, rival_drift: float,
           pins: Pins) -> tuple[float, float]:
    """The entry's mean and standard deviation over every remaining week.

    Week one is :func:`_week_one` — pinned, and the only week any event can
    reach. Weeks two onward are the entry's plain rate, plus, for a rival with
    a field template to converge on, a linear drift: in week ``w`` his rate is
    ``rate + (field - rate) * drift * w / W``. Summing that closed form rather
    than looping is what keeps a 50-entry league instant.

    My own entry never drifts. The template models *rivals* muddling toward
    the crowd; drifting gaffer's squad toward it would model gaffer as an
    average manager, which is the proposition the whole project disputes.
    """
    weeks = max(int(ins.weeks_left), 0)
    if weeks == 0:
        return 0.0, 0.0
    rate = entry_rate(entry, ins.ep_by_element)
    sd_week = entry_sigma(entry, ins.sigma_by_element)
    mean1, var1 = _week_one(entry, ins, pins)
    rest = weeks - 1
    mu = mean1 + rate * rest
    if (not entry.is_me and rest > 0 and rival_drift > 0.0
            and ins.field_rate is not None):
        # sum over w = 2..W of drift * (field - rate) * w / W
        weight = (weeks * (weeks + 1) / 2.0 - 1.0) / weeks
        mu += rival_drift * (float(ins.field_rate) - rate) * weight
    var = var1 + rest * sd_week ** 2
    return mu, math.sqrt(max(var, 0.0))


def simulate_league(inputs: SimInputs, *, n: int = SIM_N, seed: int = SIM_SEED,
                    rival_drift: float = 0.5,
                    pins: Pins | None = None) -> LeagueSim:
    """``n`` seeded seasons of this league, counted.

    One normal draw per entry per simulation, taken as a single
    ``(n, entries)`` array so the whole run is a handful of numpy calls.
    Deterministic per seed by construction — the generator is created here and
    used once — which is what gate G2 checks and what lets the router cache an
    answer without it changing under the user.

    Ties go to the higher current total, which is FPL's own rule and, when two
    draws land on the same float, the only tie-break available that is not a
    coin.
    """
    pins = pins or Pins()
    entries = list(inputs.entries)
    if not entries:
        return LeagueSim(p_win=0.0, p_top3=0.0, exp_finish=0.0, per_rival=[],
                         margin_quantiles={k: 0.0 for k in MARGIN_KEYS},
                         n=int(n), seed=int(seed),
                         weeks_left=int(inputs.weeks_left),
                         rival_drift=float(rival_drift))
    me = next((i for i, e in enumerate(entries) if e.is_me), 0)
    mus, sds, totals = [], [], []
    for entry in entries:
        mu, sd = _mu_sd(entry, inputs, float(rival_drift), pins)
        mus.append(mu)
        sds.append(sd)
        totals.append(float(entry.total))
    rng = np.random.default_rng(int(seed))
    draws = (np.asarray(totals) + np.asarray(mus)
             + rng.standard_normal((int(n), len(entries)))
             * np.asarray(sds))
    # A hair of the current total breaks exact ties in the leader's favour
    # without moving any real comparison: totals are integers, so 1e-6 of one
    # can never outrank a genuine point.
    scored = draws + np.asarray(totals) * 1e-9
    mine = scored[:, me:me + 1]
    better = (scored > mine).sum(axis=1)
    rank = better + 1
    rivals = [i for i in range(len(entries)) if i != me]
    if rivals:
        best_rival = scored[:, rivals].max(axis=1)
        margin = draws[:, me] - draws[:, rivals].max(axis=1)
    else:
        best_rival = mine[:, 0]
        margin = np.zeros(int(n))
    per_rival = [{"entry": int(entries[i].entry), "name": str(entries[i].name),
                  "p_beat": round(float((mine[:, 0] > scored[:, i]).mean()), 4)}
                 for i in rivals]
    quantiles = np.quantile(margin, MARGIN_QUANTILES)
    return LeagueSim(
        p_win=round(float((rank == 1).mean()), 4),
        p_top3=round(float((rank <= 3).mean()), 4),
        exp_finish=round(float(rank.mean()), 3),
        per_rival=per_rival,
        margin_quantiles={k: round(float(v), 1)
                          for k, v in zip(MARGIN_KEYS, quantiles)},
        n=int(n), seed=int(seed), weeks_left=int(inputs.weeks_left),
        rival_drift=float(rival_drift))


def multi_seed(inputs: SimInputs, seeds: list[int], *, n: int = SIM_N,
               rival_drift: float = 0.5, pins: Pins | None = None) -> dict:
    """The same league under several seed bases, with the spread reported.

    CONVENTIONS.md §1, applied to an instrument rather than to a replay: this
    is a new number and nobody knows yet how much of it is the seed. The
    spread is its published honesty label, printed by ``gaffer league-sim``
    and transcribed into the spec's G2 (spec §5) — there is no pass bar.
    """
    runs = [simulate_league(inputs, n=n, seed=int(s), rival_drift=rival_drift,
                            pins=pins) for s in seeds]
    values = [r.p_win for r in runs]
    return {"seeds": [int(s) for s in seeds], "n": int(n),
            "rival_drift": float(rival_drift), "p_win": values,
            "p_win_mean": round(sum(values) / len(values), 4) if values else 0.0,
            "p_win_spread": round(max(values) - min(values), 4) if values
            else 0.0,
            "p_top3_mean": round(sum(r.p_top3 for r in runs) / len(runs), 4)
            if runs else 0.0,
            "exp_finish_mean": round(sum(r.exp_finish for r in runs)
                                     / len(runs), 3) if runs else 0.0}


def history_path() -> Path:
    return artifacts.REPORTS / SIM_HISTORY


def load_sim_history() -> list[dict]:
    """Every gameweek's headline, oldest first. ``[]`` on any failure."""
    path = history_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt history is a missing one
        return []
    rows = payload.get("gws") if isinstance(payload, dict) else payload
    return sorted([r for r in (rows or []) if "gw" in r],
                  key=lambda r: int(r["gw"]))


def append_sim_history(sim: LeagueSim, gw: int, run_at: str) -> Path:
    """Bank one gameweek's headline, replacing any earlier row for that week.

    ``pen_tracker.save_tracker``'s atomic single-JSON idiom: a reader sees the
    whole previous file or the whole new one, never the half-written middle.
    Replacement rather than accumulation because a gameweek is re-simulated
    every time the advice changes, and a sparkline of six runs of GW7 is not a
    season.
    """
    rows = [r for r in load_sim_history() if int(r["gw"]) != int(gw)]
    rows.append({"gw": int(gw), "p_win": sim.p_win, "p_top3": sim.p_top3,
                 "exp_finish": sim.exp_finish, "run_at": str(run_at),
                 "n": sim.n, "seed": sim.seed})
    rows.sort(key=lambda r: int(r["gw"]))
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = history_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"gws": rows}, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def element_sigmas(comp: pd.DataFrame) -> dict[int, float]:
    """``element -> weekly estimation sigma``, from the component frame.

    The scale is the sweep's own: :func:`gaffer.optimize.scenarios.sigma_for`
    over the shipped estimation table, falling back — cell by cell, exactly as
    ``noise_ep`` does — to the pre-v6 multiplicative heuristic
    ``ep * (92 - xmins) / 134``. Both are imported by name; nothing in
    ``optimize/**`` is edited or reached into (spec D4).

    A player with no minutes prediction gets no sigma here, deliberately: "we
    cannot predict his minutes" is not "his minutes are certain", and
    :data:`WEEKLY_SIGMA_FLOOR` catches the entry-level consequence.
    """
    if comp is None or comp.empty or "element" not in comp.columns:
        return {}
    table = scenario_noise()
    xmins = xmins_by_player_gw(comp)
    ep_col = pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)
    weeks = max(int(pd.to_numeric(comp["gw"], errors="coerce").nunique()), 1)
    totals: dict[int, float] = {}
    for row, ep_value in zip(comp.itertuples(), ep_col):
        element = int(row.element) if not pd.isna(row.element) else None
        if element is None:
            continue
        xm = xmins.get((int(row.code), int(row.gw)))
        if xm is None:
            continue
        sigma = sigma_for(table, float(ep_value), float(xm))
        if sigma is None:
            sigma = float(ep_value) * (NOISE_FLOOR_XMINS - float(xm)) \
                / NOISE_DENOM
        totals[element] = totals.get(element, 0.0) + max(float(sigma), 0.0)
    return {element: value / weeks for element, value in totals.items()}
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_league_sim.py`
  Expected: `30 passed`.

- [ ] **Time it.** Gate G2's wall-clock claim is the orchestrator's to make, but the driver must be fast enough to be worth running:

```bash
uv run python -c "
import time
from gaffer.league_sim import Entry, SimInputs, simulate_league
ep = {i: 4.0 for i in range(1, 700)}
sig = {i: 3.0 for i in range(1, 700)}
entries = [Entry(entry=e, name=f'E{e}', total=100 + e, is_me=(e == 1),
                 picks=[{'element': (e * 15 + i) % 699 + 1,
                         'multiplier': 2 if i == 0 else (1 if i < 11 else 0)}
                        for i in range(15)])
           for e in range(1, 51)]
ins = SimInputs(entries=entries, ep_by_element=ep, sigma_by_element=sig,
                weeks_left=25, field_rate=55.0)
t = time.time(); simulate_league(ins, n=2000, seed=1); print(round(time.time() - t, 3), 's')"
```

Expected: well under a second. Anything over 30s means the implementation looped where it should have vectorised — stop and fix.

- [ ] **Commit.**

```bash
git add src/gaffer/league_sim.py tests/test_league_sim.py && git commit -m "$(cat <<'EOF'
feat: the mini-league Monte Carlo engine

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — F2: assembling the inputs from what advise already wrote

**Files:**
- Modify `src/gaffer/league_sim.py` (append `element_eps`, `field_rate_from_sample`, `build_inputs`)
- Create `tests/test_league_sim_inputs.py`

`build_inputs` is the only part of F2 that touches disk or the network, and it is deliberately separate from `simulate_league` so the engine's whole test suite is pure arithmetic. It reads what advise already writes (`reports/gw{N}-components.parquet` via `load_components`, `reports/solve_state_gw{N}.json` via `load_solve_state`) plus fresh standings and picks — it never re-solves and never re-trains (spec D4).

- [ ] **Write the failing test.** Create `tests/test_league_sim_inputs.py`:

```python
"""``build_inputs``: what the simulation is fed, and what it does without.

The seam between artifacts on disk and the pure engine. Everything here is
about degradation — a missing field store, a rival whose picks are private, a
gameweek nobody has advised — because every one of those is a Tuesday, not an
outage.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import COMPONENT_COLS
from gaffer.config import Config
from gaffer.data import store
from gaffer.errors import GafferError
from gaffer.league_sim import (build_inputs, element_eps,
                               field_rate_from_sample)

STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 2,
     "last_rank": 2, "total": 106, "event_total": 55},
    {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
     "rank": 1, "last_rank": 1, "total": 190, "event_total": 60}]}}

MY_PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                      {"element": 8, "position": 2, "multiplier": 1}]}
RIVAL_PICKS = {"picks": [{"element": 8, "position": 1, "multiplier": 2}]}


class FakeClient:
    def __init__(self, private=()):
        self.private = set(private)

    def get_league_standings(self, league_id, page=1):
        return STANDINGS

    def get_entry_picks(self, entry_id, gw):
        if entry_id in self.private:
            raise RuntimeError("private entry")
        return MY_PICKS if entry_id == 1 else RIVAL_PICKS


def _comp() -> pd.DataFrame:
    rows = []
    for gw in (3, 4):
        for code, element, ep, p_play, p60 in ((100, 7, 6.0, 0.95, 0.9),
                                               (101, 8, 3.0, 0.8, 0.6)):
            row = {c: float("nan") for c in COMPONENT_COLS}
            row.update({"code": code, "element": element, "gw": gw, "ep": ep,
                        "p_play": p_play, "p60": p60, "name": "x",
                        "position": "MID", "team_code": 1, "team_name": "T",
                        "opp_code": 2, "opp_name": "O", "was_home": True,
                        "kickoff_time": "2026-09-12T14:00:00Z"})
            rows.append(row)
    return pd.DataFrame(rows, columns=COMPONENT_COLS)


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    return tmp_path


def test_the_ep_per_element_is_the_mean_over_the_horizon():
    """Two gameweeks in the frame, so a player's per-*week* rate is his total
    over two. A sum here would make a three-week horizon look like a
    three-times-better squad."""
    out = element_eps(_comp())
    assert out[7] == pytest.approx(6.0)
    assert out[8] == pytest.approx(3.0)


def test_a_double_gameweek_counts_twice_in_one_week():
    comp = pd.concat([_comp(), _comp().head(1)], ignore_index=True)
    assert element_eps(comp)[7] == pytest.approx(9.0)


def test_an_empty_component_frame_is_an_empty_map():
    assert element_eps(pd.DataFrame(columns=COMPONENT_COLS)) == {}


def test_the_field_rate_is_the_mean_squad_over_the_sample():
    """One entry captains a 6.0 player (12) plus a 3.0 (15); the other plays
    the 3.0 alone (3). The template is the average manager, so 9."""
    sample = [[{"element": 7, "multiplier": 2},
               {"element": 8, "multiplier": 1}],
              [{"element": 8, "multiplier": 1}]]
    assert field_rate_from_sample(sample, {7: 6.0, 8: 3.0}) \
        == pytest.approx(9.0)


def test_no_sample_is_none_rather_than_zero():
    """``None`` turns drift off; 0.0 would tell every rival to converge on a
    squad that scores nothing, which is the opposite claim."""
    assert field_rate_from_sample(None, {7: 6.0}) is None
    assert field_rate_from_sample([], {7: 6.0}) is None


def test_the_inputs_name_me_and_every_rival(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5), FakeClient())
    assert [e.entry for e in ins.entries] == [1, 2]
    assert [e.is_me for e in ins.entries] == [True, False]
    assert ins.entries[1].total == 190


def test_the_squads_are_the_last_scored_gameweeks(here, monkeypatch):
    """Picks are public for finished gameweeks only, so the plan gameweek
    minus one — the same rule ``league.py::_last_scored_gw`` uses."""
    seen = []

    class _Client(FakeClient):
        def get_entry_picks(self, entry_id, gw):
            seen.append(gw)
            return super().get_entry_picks(entry_id, gw)

    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    build_inputs(Config(entry_id=1, league_id=5), _Client())
    assert set(seen) == {4}


def test_weeks_left_counts_the_season_out_from_the_plan_gameweek(here,
                                                                 monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5), FakeClient())
    assert ins.weeks_left == 34          # gameweeks 5 through 38


def test_a_private_rival_keeps_his_place_with_an_empty_squad(here,
                                                             monkeypatch):
    """He is still in the league and his total still counts; he simply has no
    modellable squad, and the sigma floor gives him a season anyway."""
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5),
                       FakeClient(private=(2,)))
    assert [e.entry for e in ins.entries] == [1, 2]
    assert ins.entries[1].picks == []


def test_no_field_sample_turns_drift_off(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5), FakeClient())
    assert ins.field_rate is None


def test_a_banked_field_sample_becomes_the_template(here, monkeypatch):
    from gaffer.data.field import save_field_sample

    save_field_sample([[{"element": 7, "position": 1, "multiplier": 2}]],
                      4, "2026-27")
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())
    ins = build_inputs(Config(entry_id=1, league_id=5,
                              current_season="2026-27"), FakeClient())
    assert ins.field_rate == pytest.approx(12.0)


def test_no_advice_at_all_is_a_readable_refusal(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: None)
    with pytest.raises(GafferError, match="gaffer advise"):
        build_inputs(Config(entry_id=1, league_id=5), FakeClient())


def test_no_league_id_is_a_readable_refusal(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    with pytest.raises(GafferError, match="league_id"):
        build_inputs(Config(entry_id=1, league_id=0), FakeClient())
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_league_sim_inputs.py`
  Expected: `ImportError: cannot import name 'build_inputs'`.

- [ ] **Write the implementation.** Append to `src/gaffer/league_sim.py`:

```python
SEASON_GWS = 38
"""Gameweeks in a season. The remaining-weeks count is ``38 - gw + 1``: the
gameweek being planned is still to be played."""


def element_eps(comp: pd.DataFrame) -> dict[int, float]:
    """``element -> expected points per gameweek`` over the horizon.

    The *mean* over the distinct gameweeks the frame covers, not the sum: a
    three-week horizon would otherwise read as a squad three times as good,
    and the simulation multiplies this by the weeks left itself. A double
    gameweek stays doubled, because two fixtures in one week really are twice
    the points in that week.
    """
    if comp is None or comp.empty or "element" not in comp.columns:
        return {}
    frame = pd.DataFrame({
        "element": pd.to_numeric(comp["element"], errors="coerce"),
        "gw": pd.to_numeric(comp["gw"], errors="coerce"),
        "ep": pd.to_numeric(comp["ep"], errors="coerce").fillna(0.0)})
    frame = frame.dropna(subset=["element", "gw"])
    if frame.empty:
        return {}
    weeks = max(int(frame["gw"].nunique()), 1)
    grouped = frame.groupby("element", as_index=False)["ep"].sum()
    return {int(r.element): float(r.ep) / weeks for r in grouped.itertuples()}


def field_rate_from_sample(sample: list[list[dict]] | None,
                           ep_by: dict[int, float]) -> float | None:
    """The sampled field's mean weekly rate, or ``None`` with no sample.

    The template a drifting rival converges on: what the average top-10k
    manager's squad is worth per week under gaffer's own expected points. That
    it is scored with *our* EP and not with theirs is the point — the question
    is "how much better than the crowd is this squad, by the only yardstick we
    have".

    ``None`` rather than 0.0 for an absent or empty sample: zero would tell
    every rival to converge on a squad that scores nothing, which is not a
    degradation of the model but an inversion of it.
    """
    if not sample:
        return None
    rates = [sum(int(p.get("multiplier", 0))
                 * float(ep_by.get(int(p["element"]), 0.0)) for p in squad)
             for squad in sample]
    return float(sum(rates) / len(rates)) if rates else None


def build_inputs(cfg, client, *, gw: int | None = None) -> SimInputs:
    """Assemble a :class:`SimInputs` from artifacts on disk plus fresh league
    data.

    Reads only what ``advise`` already wrote — the component frame for EP and
    sigma — and fetches only what is not an artifact: standings, and each
    entry's squad from the last *scored* gameweek (picks are 404 before a
    deadline, the same rule ``league.py::_last_scored_gw`` follows). Nothing
    is re-solved and nothing is re-trained: spec D4's whole point is that the
    MC is a reader.

    The field template comes from the banked sample for that same scored
    gameweek; when there is none — a fresh clone, a week the scrape missed —
    it is ``None`` and drift is off however the config is set. That is the
    documented degradation and one of G3's rails.
    """
    if not getattr(cfg, "league_id", 0):
        raise GafferError(
            "set fpl.league_id in config.toml to use the league simulation")
    plan_gw = int(gw) if gw is not None else artifacts.latest_gw()
    if plan_gw is None:
        raise GafferError("no saved advice — run `gaffer advise` first")
    comp = artifacts.load_components(plan_gw)
    ep_by = element_eps(comp)
    sigma_by = element_sigmas(comp)
    squad_gw = max(1, int(plan_gw) - 1)

    rows, page = [], 1
    while True:
        data = client.get_league_standings(cfg.league_id, page)
        rows.extend(data["standings"]["results"])
        if not data["standings"].get("has_next") or len(rows) >= 50:
            break
        page += 1
    rows.sort(key=lambda r: -int(r["total"]))

    entries: list[Entry] = []
    for row in rows:
        entry_id = int(row["entry"])
        try:
            picks = list(client.get_entry_picks(entry_id, squad_gw)["picks"])
        except Exception:  # noqa: BLE001 — joined late / private / 404
            picks = []      # still in the league, simply unmodellable
        entries.append(Entry(entry=entry_id, name=str(row["entry_name"]),
                             total=int(row["total"]), picks=picks,
                             is_me=entry_id == int(cfg.entry_id)))

    sample = load_field_sample(str(getattr(cfg, "current_season", "") or ""),
                               squad_gw)
    return SimInputs(entries=entries, ep_by_element=ep_by,
                     sigma_by_element=sigma_by,
                     weeks_left=max(0, SEASON_GWS - int(plan_gw) + 1),
                     field_rate=field_rate_from_sample(sample, ep_by))
```

and extend the module's import block with the two names it now needs:

```python
from gaffer.data.field import load_field_sample
from gaffer.errors import GafferError
```

`gaffer.data.field` imports `gaffer.snapshot`, which imports `gaffer.artifacts` — no cycle, because nothing in that chain imports `league_sim`.

- [ ] **Run to pass.** `uv run pytest -q tests/test_league_sim_inputs.py tests/test_league_sim.py`
  Expected: `13 passed` in the new file, `30 passed` in the engine file.

- [ ] **Commit.**

```bash
git add src/gaffer/league_sim.py tests/test_league_sim_inputs.py && git commit -m "$(cat <<'EOF'
feat: assemble the league-sim inputs from advise's own artifacts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — F2: `gaffer league-sim --seeds`

**Files:**
- Modify `src/gaffer/cli.py` (new `league_sim` command, after `field_scrape`)
- Modify `src/gaffer/league_sim.py` (append `format_multi_seed`)
- Modify `tests/test_league_sim.py` (append)

The CLI is where CONVENTIONS.md §1 lives for this cycle: the router serves one seed so the card is stable, and this command is the only place a *recorded* claim comes from.

- [ ] **Write the failing test.** Append to `tests/test_league_sim.py`:

```python
# --- the printed report ----------------------------------------------------

from gaffer.league_sim import format_multi_seed  # noqa: E402


def test_the_report_names_every_seed_and_the_spread():
    text = format_multi_seed(multi_seed(_inputs(), seeds=[1, 2, 3], n=200),
                             league_id=5)
    assert "league 5" in text
    assert "seed 1" in text and "seed 3" in text
    assert "spread" in text


def test_the_report_says_out_loud_that_a_spread_is_not_a_verdict():
    """A number printed without its caveat is a number that ends up in a
    commit message as a finding. CONVENTIONS.md §5."""
    text = format_multi_seed(multi_seed(_inputs(), seeds=[1, 2], n=100),
                             league_id=5)
    assert "instrument" in text.lower()
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_league_sim.py -k report`
  Expected: `ImportError: cannot import name 'format_multi_seed'`.

- [ ] **Write the implementation.** Append to `src/gaffer/league_sim.py`:

```python
def format_multi_seed(report: dict, league_id: int) -> str:
    """The printed multi-seed table. One line per seed, then the aggregate."""
    lines = [f"League simulation — league {league_id}, "
             f"n={report['n']} per seed, drift={report['rival_drift']}",
             f"{'seed':>10}  {'P(win)':>8}"]
    for seed, value in zip(report["seeds"], report["p_win"]):
        lines.append(f"{'seed ' + str(seed):>10}  {value:>8.3f}")
    lines.append(f"{'mean':>10}  {report['p_win_mean']:>8.3f}   "
                 f"spread {report['p_win_spread']:.3f}")
    lines.append(f"{'P(top 3)':>10}  {report['p_top3_mean']:>8.3f}   "
                 f"expected finish {report['exp_finish_mean']:.2f}")
    lines.append("")
    lines.append("The spread is this instrument's honesty label, not a "
                 "verdict: it says how much of the headline is the seed. "
                 "There is no pass bar (spec §5, G2).")
    return "\n".join(lines)
```

- [ ] **Write the CLI command.** In `src/gaffer/cli.py`, add after `field_scrape`:

```python
@app.command()
def league_sim(
        seeds: str = typer.Option("", help="Comma-separated seed bases; "
                                           "default is the shipped seed."),
        n: int = typer.Option(0, help="Simulations per seed (default: "
                                      "league.sim_n)."),
        drift: float = typer.Option(-1.0, help="Rival drift 0-1 (default: "
                                              "league.rival_drift).")):
    """Simulate the mini-league to the end of the season (v8c F2).

    With several seeds it prints mean +/- spread, which is the only form a
    recorded claim about this number may take (CONVENTIONS.md §1).
    """
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.league_sim import (SIM_SEED, build_inputs, format_multi_seed,
                                   multi_seed)

    cfg = load_config()
    bases = [int(s) for s in seeds.split(",") if s.strip()] or [SIM_SEED]
    report = multi_seed(
        build_inputs(cfg, FPLClient()), seeds=bases,
        n=int(n or cfg.sim_n),
        rival_drift=(cfg.rival_drift if drift < 0 else float(drift)))
    typer.echo(format_multi_seed(report, cfg.league_id))
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_league_sim.py`
  Expected: `32 passed`.

- [ ] **Check the CLI registers.** `uv run gaffer --help | grep league-sim`
  Expected: one line naming `league-sim`.

- [ ] **Commit.**

```bash
git add src/gaffer/cli.py src/gaffer/league_sim.py tests/test_league_sim.py && git commit -m "$(cat <<'EOF'
feat: gaffer league-sim, with the multi-seed spread it publishes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — F3: `GET /api/league/sim`

**Files:**
- Modify `src/gaffer/web/schemas.py` (append the v8c models, after `LeagueRace`)
- Create `src/gaffer/web/routers/league_sim.py`
- Modify `src/gaffer/web/app.py` (import + `include_router`)
- Create `tests/test_web_league_sim.py`

- [ ] **Write the failing test.** Create `tests/test_web_league_sim.py`:

```python
"""``/api/league/sim`` and ``/api/league/whatif``.

The pattern is ``tests/test_web_league.py``'s: a FakeClient, artifacts written
into a tmp path, and every failure a readable 422 rather than a 500.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, SolveState, pool_rows,
                              save_components, save_solve_state)
from gaffer.data import store
from gaffer.web.app import create_app

STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 2,
     "last_rank": 2, "total": 106, "event_total": 55},
    {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
     "rank": 1, "last_rank": 1, "total": 190, "event_total": 60}]}}

MY_PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                      {"element": 8, "position": 2, "multiplier": 1}]}
RIVAL_PICKS = {"picks": [{"element": 8, "position": 1, "multiplier": 2}]}


class FakeClient:
    def __init__(self, dead=False):
        self.dead = dead

    def get_league_standings(self, league_id, page=1):
        if self.dead:
            raise RuntimeError("FPL is down")
        return STANDINGS

    def get_entry_picks(self, entry_id, gw):
        if self.dead:
            raise RuntimeError("FPL is down")
        return MY_PICKS if entry_id == 1 else RIVAL_PICKS


def _comp() -> pd.DataFrame:
    rows = []
    for code, element, ep in ((100, 7, 6.0), (101, 8, 3.0)):
        row = {c: float("nan") for c in COMPONENT_COLS}
        row.update({"code": code, "element": element, "gw": 3, "ep": ep,
                    "p_play": 0.9, "p60": 0.8, "name": "x", "position": "MID",
                    "team_code": 1, "team_name": "T", "opp_code": 2,
                    "opp_name": "O", "was_home": True,
                    "kickoff_time": "2026-09-12T14:00:00Z"})
        rows.append(row)
    return pd.DataFrame(rows, columns=COMPONENT_COLS)


def _artifacts(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n\n[league]\nsim_n = 200\n')
    players = pd.DataFrame([
        {"code": 100, "element": 7, "name": "Salah", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 130, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 45.0,
         "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": 1.0, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 101, "element": 8, "name": "Dud", "position": "DEF",
         "team_id": 2, "team_code": 301, "now_cost": 45, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 5.0,
         "form": 1.0, "points_per_game": 2.0, "ep_next": 2.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None}])
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    players.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    save_components(_comp(), 3)
    save_solve_state(SolveState(
        gw=3, gws=[3], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=0.0, league_eo={100: 62.5},
        avail_by_gw={3: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool_rows(
            pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                           "cost": 130, "sell": 128}]),
            players, [100], {(100, 3): 6.4}, [3])))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    _artifacts(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    return TestClient(create_app())


def test_the_sim_endpoint_answers_a_league_shaped_payload(client):
    body = client.get("/api/league/sim").json()
    assert body["gw"] == 3
    assert 0.0 <= body["p_win"] <= 1.0
    assert body["p_top3"] >= body["p_win"]
    assert [r["entry"] for r in body["per_rival"]] == [2]
    assert list(body["margin_quantiles"]) == ["p05", "p25", "p50", "p75",
                                              "p95"]


def test_the_payload_says_how_it_was_produced(client):
    body = client.get("/api/league/sim").json()
    assert body["n"] == 200          # from [league] sim_n in the fixture
    assert body["seed"] > 0
    assert body["rival_drift"] == 0.5
    assert body["entries"] == 2


def test_the_field_is_reported_as_absent_when_nothing_is_banked(client):
    body = client.get("/api/league/sim").json()
    assert body["field_rate"] is None
    assert "field" in (body["notice"] or "").lower()


def test_a_repeat_call_is_served_from_the_cache(client, monkeypatch):
    """The MC is cheap but not free, and the League hub, the What-if tab and
    This Week's chip all want the same answer within a second of each other."""
    calls = {"n": 0}

    def _counting():
        calls["n"] += 1
        return FakeClient()

    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client", _counting)
    first = client.get("/api/league/sim").json()
    second = client.get("/api/league/sim").json()
    assert calls["n"] == 1
    assert first["p_win"] == second["p_win"]


def test_the_run_is_banked_in_the_history_the_sparkline_reads(client):
    from gaffer.league_sim import load_sim_history

    body = client.get("/api/league/sim").json()
    banked = load_sim_history()
    assert [r["gw"] for r in banked] == [3]
    assert banked[0]["p_win"] == body["p_win"]
    assert [h["gw"] for h in body["history"]] == [3]


def test_the_legacy_parametric_numbers_ride_along(client):
    """Spec §3: the old ``win_probability`` output stays in the payload,
    marked legacy, until the UI has fully switched."""
    body = client.get("/api/league/sim").json()
    assert [p["name"] for p in body["legacy_win_probability"]] \
        == ["Ten Hag Hive"]


def test_a_dead_api_is_a_422_not_a_500(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = client.get("/api/league/sim")
    assert res.status_code == 422
    assert "retry" in res.json()["detail"].lower()


def test_no_league_id_is_a_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 0\n')
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = TestClient(create_app()).get("/api/league/sim")
    assert res.status_code == 422
    assert "league_id" in res.json()["detail"]


def test_no_advice_on_disk_is_a_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 5\n')
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = TestClient(create_app()).get("/api/league/sim")
    assert res.status_code == 422
    assert "advise" in res.json()["detail"]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_league_sim.py`
  Expected: `ModuleNotFoundError: No module named 'gaffer.web.routers.league_sim'`.

- [ ] **Write the schemas.** In `src/gaffer/web/schemas.py`, append after `LeagueRace`:

```python
class RivalBeat(BaseModel):
    entry: int
    name: str
    p_beat: float


class SimPoint(BaseModel):
    """One banked gameweek of the headline, for the card's sparkline."""

    gw: int
    p_win: float
    p_top3: float
    exp_finish: float
    run_at: str


class LeagueSimData(BaseModel):
    gw: int
    entries: int
    weeks_left: int
    n: int
    seed: int
    rival_drift: float
    p_win: float
    p_top3: float
    exp_finish: float
    per_rival: list[RivalBeat]
    margin_quantiles: dict[str, float]
    history: list[SimPoint]
    field_rate: float | None = None
    """The sampled field's weekly rate, or ``None`` when nothing is banked —
    in which case rivals do not drift however ``rival_drift`` is set."""
    notice: str | None = None
    legacy_win_probability: list[WinProb] = Field(default_factory=list)
    """``league_mode.win_probability``'s parametric answer, kept beside the
    simulated one until the UI has fully switched (spec §3)."""


class LeagueWhatIfPin(BaseModel):
    code: int
    """A gaffer player *code*, not a season element id — the explorer, the
    squad table and the compare panel all speak codes, and the router maps to
    elements against the same snapshot they were rendered from."""
    event: str = "blank"          # "haul" | "blank" | "score"


class LeagueWhatIfRequest(BaseModel):
    pins: list[LeagueWhatIfPin] = Field(default_factory=list)
    captain_override: int | None = None
    rival_captain_blanks: int | None = None


class LeagueWhatIfRow(BaseModel):
    entry: int
    name: str
    is_you: bool
    total: int
    p_win: float
    exp_finish: float


class LeagueWhatIfResult(BaseModel):
    baseline_p_win: float
    p_win: float
    delta_p_win: float
    baseline_exp_finish: float
    exp_finish: float
    delta_rank: float
    table: list[LeagueWhatIfRow]
    unknown_codes: list[int] = Field(default_factory=list)
```

- [ ] **Write the router.** Create `src/gaffer/web/routers/league_sim.py`:

```python
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
```

- [ ] **Register the router.** In `src/gaffer/web/app.py`, add `league_sim` to the routers import (alphabetically, after `league`) and add the line after `app.include_router(league.router)`:

```python
    app.include_router(league_sim.router)
```

Both routers carry the `/api/league` prefix; FastAPI matches `/sim` on the second only, so ordering does not matter — but keeping them adjacent keeps the file readable.

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_league_sim.py tests/test_web_league.py`
  Expected: `9 passed` in the new file, and `test_web_league.py` green and unmodified.

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/league_sim.py src/gaffer/web/app.py tests/test_web_league_sim.py && git commit -m "$(cat <<'EOF'
feat: GET /api/league/sim over the mini-league Monte Carlo

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — F3: `POST /api/league/whatif`

**Files:**
- Modify `src/gaffer/web/routers/league_sim.py` (append the endpoint)
- Modify `tests/test_web_league_sim.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_web_league_sim.py`:

```python
# --- the what-if panel -----------------------------------------------------


def test_no_pins_at_all_reproduces_the_sim_endpoint(client):
    """G3's rail: an empty what-if is the baseline, exactly, or the panel's
    deltas are measuring the panel rather than the pins."""
    base = client.get("/api/league/sim").json()
    body = client.post("/api/league/whatif", json={"pins": []}).json()
    assert body["p_win"] == base["p_win"]
    assert body["baseline_p_win"] == base["p_win"]
    assert body["delta_p_win"] == 0.0
    assert body["delta_rank"] == 0.0


def test_blanking_my_captain_costs_me_title_odds(client):
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 100, "event": "blank"}]}).json()
    assert body["delta_p_win"] < 0.0
    assert body["p_win"] < body["baseline_p_win"]


def test_a_haul_by_my_captain_pays(client):
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 100, "event": "haul"}]}).json()
    assert body["delta_p_win"] > 0.0


def test_scoring_a_player_at_his_forecast_is_close_to_no_event(client):
    """"score" means "he does what we already expect", so the delta is the
    variance removed and nothing else — a small number, not a swing."""
    base = client.get("/api/league/sim").json()
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 100, "event": "score"}]}).json()
    assert abs(body["p_win"] - base["p_win"]) < 0.2


def test_the_table_names_every_entry_and_marks_me(client):
    body = client.post("/api/league/whatif", json={"pins": []}).json()
    assert [r["entry"] for r in body["table"]] == [2, 1]
    assert [r["is_you"] for r in body["table"]] == [False, True]
    assert sum(r["p_win"] for r in body["table"]) == pytest.approx(1.0,
                                                                  abs=0.01)


def test_a_captain_override_is_priced(client):
    body = client.post("/api/league/whatif",
                       json={"captain_override": 101}).json()
    assert body["delta_p_win"] < 0.0


def test_a_rival_captain_blank_helps(client):
    body = client.post("/api/league/whatif",
                       json={"rival_captain_blanks": 2}).json()
    assert body["delta_p_win"] >= 0.0


def test_an_unknown_code_is_reported_rather_than_silently_dropped(client):
    """A stale tab pinning a transferred-out player must be told, not
    humoured: a panel that answers a question it did not understand is worse
    than one that refuses."""
    body = client.post("/api/league/whatif",
                       json={"pins": [{"code": 999, "event": "blank"}]}).json()
    assert body["unknown_codes"] == [999]
    assert body["delta_p_win"] == 0.0


def test_an_unknown_event_name_is_a_422(client):
    res = client.post("/api/league/whatif",
                      json={"pins": [{"code": 100, "event": "hattrick"}]})
    assert res.status_code == 422
    assert "hattrick" in res.json()["detail"]


def test_the_whatif_reuses_the_cached_inputs_and_fetches_nothing(client,
                                                                 monkeypatch):
    calls = {"n": 0}

    def _counting():
        calls["n"] += 1
        return FakeClient()

    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client", _counting)
    client.get("/api/league/sim")
    client.post("/api/league/whatif",
                json={"pins": [{"code": 100, "event": "blank"}]})
    assert calls["n"] == 1


def test_the_whatif_does_not_bank_a_history_row(client):
    """The sparkline is a record of the league, not of the user's fiddling."""
    from gaffer.league_sim import load_sim_history

    client.get("/api/league/sim")
    client.post("/api/league/whatif",
                json={"pins": [{"code": 100, "event": "blank"}]})
    assert len(load_sim_history()) == 1


def test_a_dead_api_is_a_422_here_too(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    res = client.post("/api/league/whatif", json={"pins": []})
    assert res.status_code == 422
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_league_sim.py -k whatif`
  Expected: `405 Method Not Allowed` — there is no POST handler yet.

- [ ] **Write the implementation.** Append to `src/gaffer/web/routers/league_sim.py`:

```python
EVENT_POINTS = {"blank": BLANK_POINTS, "haul": HAUL_POINTS}
"""``score`` is absent on purpose: it means "his forecast, pinned", which is a
per-player number rather than a constant, and is resolved below."""


def _elements_by_code() -> dict[int, int]:
    """``code -> element`` from the live players snapshot.

    The panel speaks codes because everything else in the UI does; the picks
    speak elements because the API does. One mapping, read from the same
    snapshot the explorer rendered from, so a code the user can see is a code
    this endpoint can resolve.
    """
    try:
        snapshot = load_snapshot("live/players.parquet")
    except Exception:  # noqa: BLE001 — no snapshot means no mapping
        return {}
    return {int(r.code): int(r.element) for r in snapshot.itertuples()}


def _entry_probabilities(sim, inputs) -> list[LeagueWhatIfRow]:
    """The projected table under one run: every entry, my odds beside theirs.

    ``p_win`` for a rival is ``1 - p_beat`` folded through the same run — not
    a second simulation, because two simulations of one league produce two
    tables that do not sum to one and a panel whose column does not add up is
    a panel nobody believes. My own row carries the run's ``p_win`` and the
    remainder is split by each rival's share of the losing mass.
    """
    me = next((e for e in inputs.entries if e.is_me), None)
    beats = {int(r["entry"]): float(r["p_beat"]) for r in sim.per_rival}
    losing = sum(1.0 - beats.get(int(e.entry), 0.0)
                 for e in inputs.entries if not e.is_me) or 1.0
    rows = []
    for entry in inputs.entries:
        if entry.is_me:
            p_win = sim.p_win
        else:
            share = (1.0 - beats.get(int(entry.entry), 0.0)) / losing
            p_win = (1.0 - sim.p_win) * share
        rows.append(LeagueWhatIfRow(
            entry=int(entry.entry), name=str(entry.name),
            is_you=bool(entry.is_me), total=int(entry.total),
            p_win=round(p_win, 4),
            exp_finish=(sim.exp_finish if entry.is_me else 0.0)))
    rows.sort(key=lambda r: -r.total)
    return rows


@router.post("/whatif", response_model=LeagueWhatIfResult)
def whatif(req: LeagueWhatIfRequest) -> LeagueWhatIfResult:
    """Re-run the league with this week's events pinned.

    Different mechanism from the squad What-If Lab and deliberately kept
    apart (spec D5): that one re-solves the MILP under constraints, this one
    re-counts a Monte Carlo under declared events. No solve happens here and
    no transfer is proposed — the question is "what would that week do to my
    title odds", and the answer is a difference of two counted runs.

    An empty request is exactly the baseline. That is a rail rather than a
    nicety: every delta the panel shows is a difference against a run this
    endpoint produced itself, so a baseline that drifted would make the whole
    panel measure itself.
    """
    cfg = load_config()
    gw = latest_gw()
    baseline, inputs = _run(cfg, gw)
    by_code = _elements_by_code()

    scores: dict[int, float] = {}
    unknown: list[int] = []
    for pin in req.pins:
        if pin.event not in EVENT_POINTS and pin.event != "score":
            raise GafferError(
                f"unknown what-if event {pin.event!r} — expected haul, blank "
                f"or score")
        element = by_code.get(int(pin.code))
        if element is None:
            unknown.append(int(pin.code))
            continue
        scores[element] = (float(inputs.ep_by_element.get(element, 0.0))
                           if pin.event == "score"
                           else EVENT_POINTS[pin.event])

    captain = by_code.get(int(req.captain_override)) \
        if req.captain_override is not None else None
    if req.captain_override is not None and captain is None:
        unknown.append(int(req.captain_override))
    pins = Pins(scores=scores, captain_override=captain,
                rival_captain_blanks=(int(req.rival_captain_blanks)
                                      if req.rival_captain_blanks is not None
                                      else None))
    pinned = simulate_league(inputs, n=int(cfg.sim_n), seed=baseline.seed,
                             rival_drift=float(cfg.rival_drift), pins=pins)
    return LeagueWhatIfResult(
        baseline_p_win=baseline.p_win, p_win=pinned.p_win,
        delta_p_win=round(pinned.p_win - baseline.p_win, 4),
        baseline_exp_finish=baseline.exp_finish,
        exp_finish=pinned.exp_finish,
        delta_rank=round(pinned.exp_finish - baseline.exp_finish, 3),
        table=_entry_probabilities(pinned, inputs),
        unknown_codes=sorted(set(unknown)))
```

Note the pinned run uses `baseline.seed` deliberately: the same draws under two sets of means is a *paired* comparison, and an unpaired one at n=2000 would bury a two-point captaincy difference under seed noise.

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_league_sim.py`
  Expected: `21 passed`.

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/league_sim.py tests/test_web_league_sim.py && git commit -m "$(cat <<'EOF'
feat: POST /api/league/whatif — this week's events, priced in title odds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — F3: the frontend types, in lockstep

**Files:**
- Modify `frontend/src/types.ts` (`JOB_KINDS` L570, `JOB_KIND_LABEL` L575; new interfaces appended)
- Modify `frontend/src/types.test.ts` (the count pin)
- Modify `frontend/src/hubs/Model.tsx` (the button row)

- [ ] **Update the pin first.** In `frontend/src/types.test.ts`, change the first case:

```ts
  it('lists exactly the eight kinds the backend allows', () => {
    expect([...JOB_KINDS]).toEqual(
      ['advise', 'advise-fast', 'evaluate', 'refresh-data', 'news-shadow',
       'snapshot', 'track-pens', 'field-scrape'])
  })
```

and append a case that pins the two payload shapes the League hub reads:

```ts
describe('league sim types', () => {
  it('types the sim payload the way the router serialises it', () => {
    const sim: LeagueSimData = {
      gw: 7, entries: 8, weeks_left: 32, n: 2000, seed: 20260831,
      rival_drift: 0.5, p_win: 0.21, p_top3: 0.55, exp_finish: 2.9,
      per_rival: [{ entry: 2, name: 'Ten Hag Hive', p_beat: 0.61 }],
      margin_quantiles: { p05: -80, p25: -20, p50: 12, p75: 44, p95: 110 },
      history: [{ gw: 6, p_win: 0.18, p_top3: 0.5, exp_finish: 3.1,
                  run_at: '2026-09-05T09:00:00+00:00' }],
      field_rate: 54.2, notice: null, legacy_win_probability: [],
    }
    expect(sim.per_rival[0].p_beat).toBeGreaterThan(0)
  })

  it('types the what-if result', () => {
    const out: LeagueWhatIfResult = {
      baseline_p_win: 0.21, p_win: 0.14, delta_p_win: -0.07,
      baseline_exp_finish: 2.9, exp_finish: 3.4, delta_rank: 0.5,
      table: [{ entry: 1, name: 'Mine', is_you: true, total: 300,
                p_win: 0.14, exp_finish: 3.4 }],
      unknown_codes: [],
    }
    expect(out.delta_p_win).toBeLessThan(0)
  })
})
```

with the two names added to the file's import at the top.

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/types.test.ts`
  Expected: the count case fails on the missing `'field-scrape'`, and the two new cases fail to compile on `LeagueSimData`.

- [ ] **Write the types.** In `frontend/src/types.ts`, extend the two job constants:

```ts
export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens', 'field-scrape'] as const
```

```ts
export const JOB_KIND_LABEL: Record<JobKind, string> = {
  advise: 'Run advise',
  'advise-fast': 'Fast advise',
  evaluate: 'Evaluate',
  'refresh-data': 'Refresh data',
  'news-shadow': 'Score news shadow',
  snapshot: 'Snapshot news',
  'track-pens': 'Track pens',
  'field-scrape': 'Field scrape',
}
```

and append the v8c interfaces at the end of the file:

```ts
/** GET /api/league/sim — see web/schemas.py::LeagueSimData. */
export interface RivalBeat {
  entry: number
  name: string
  p_beat: number
}

export interface SimPoint {
  gw: number
  p_win: number
  p_top3: number
  exp_finish: number
  run_at: string
}

export interface LeagueSimData {
  gw: number
  entries: number
  weeks_left: number
  /** Simulations per run, and the seed they were drawn under. Rendered next
   *  to the headline: a probability with no n beside it is a decoration. */
  n: number
  seed: number
  rival_drift: number
  p_win: number
  p_top3: number
  exp_finish: number
  per_rival: RivalBeat[]
  margin_quantiles: Record<string, number>
  history: SimPoint[]
  /** null when no field sample is banked — rivals then do not drift. */
  field_rate: number | null
  notice: string | null
  legacy_win_probability: WinProb[]
}

export type LeagueWhatIfEvent = 'haul' | 'blank' | 'score'

export interface LeagueWhatIfRequest {
  pins: { code: number, event: LeagueWhatIfEvent }[]
  captain_override?: number | null
  rival_captain_blanks?: number | null
}

export interface LeagueWhatIfRow {
  entry: number
  name: string
  is_you: boolean
  total: number
  p_win: number
  exp_finish: number
}

export interface LeagueWhatIfResult {
  baseline_p_win: number
  p_win: number
  delta_p_win: number
  baseline_exp_finish: number
  exp_finish: number
  delta_rank: number
  table: LeagueWhatIfRow[]
  /** Codes the server could not resolve — a stale tab pinning a player who
   *  has left the game. Shown, never swallowed. */
  unknown_codes: number[]
}
```

- [ ] **Add the button.** In `frontend/src/hubs/Model.tsx`, after the snapshot button:

```tsx
            <JobButton kind="field-scrape" label="Field scrape"
```

matching the surrounding buttons' props exactly (copy the `onDone` handler from the `snapshot` line if it has one).

- [ ] **Run to pass.** `cd frontend && npx vitest run src/types.test.ts src/hubs/Model.test.tsx && npx tsc --noEmit`
  Expected: green, and `tsc` silent.

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/types.test.ts frontend/src/hubs/Model.tsx && git commit -m "$(cat <<'EOF'
feat: field-scrape job kind and the league-sim types, frontend side

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — F3: the League hub's upgraded card and its What-if tab

**Files:**
- Create `frontend/src/hubs/league/WhatIfSim.tsx`
- Create `frontend/src/hubs/league/WhatIfSim.test.tsx`
- Modify `frontend/src/hubs/League.tsx` (fetch the sim; the win-probability card; a third tab)
- Modify `frontend/src/hubs/League.test.tsx` (append)

- [ ] **Write the failing tests.** Append to `frontend/src/hubs/League.test.tsx`:

```tsx
const SIM = {
  gw: 7, entries: 2, weeks_left: 31, n: 2000, seed: 20260831,
  rival_drift: 0.5, p_win: 0.42, p_top3: 1.0, exp_finish: 1.6,
  per_rival: [{ entry: 2, name: 'Ten Hag Hive', p_beat: 0.58 }],
  margin_quantiles: { p05: -60, p25: -12, p50: 18, p75: 50, p95: 120 },
  history: [
    { gw: 5, p_win: 0.3, p_top3: 1, exp_finish: 1.8,
      run_at: '2026-09-05T09:00:00+00:00' },
    { gw: 6, p_win: 0.36, p_top3: 1, exp_finish: 1.7,
      run_at: '2026-09-12T09:00:00+00:00' },
  ],
  field_rate: 54.2, notice: null, legacy_win_probability: [],
}

describe('the simulated win-probability card', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') return Promise.resolve(SIM)
      return Promise.reject(new Error(`unexpected ${path}`))
    })
  })

  it('leads with the simulated title odds, not the pairwise ones', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-p-win')).toHaveTextContent('42%')
    expect(screen.getByTestId('sim-p-top3')).toHaveTextContent('100%')
  })

  it('says how many simulations produced the number', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-provenance'))
      .toHaveTextContent('2,000')
  })

  it('lists every rival with the odds of beating him', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('beat-2')).toHaveTextContent('58%')
  })

  it('draws the sparkline once two gameweeks are banked', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-sparkline')).toBeInTheDocument()
  })

  it('falls back to the parametric table when the sim will not load',
     async () => {
       apiGet.mockImplementation((path: string) => {
         if (path === '/api/league/race') return Promise.resolve(RACE)
         if (path === '/api/league/rivals') return Promise.resolve([])
         return Promise.reject(new Error('422'))
       })
       render(<MemoryRouter><League /></MemoryRouter>)
       expect(await screen.findByTestId('legacy-win-probability'))
         .toBeInTheDocument()
       expect(screen.queryByTestId('sim-p-win')).not.toBeInTheDocument()
     })

  it('shows the notice when no field sample is banked', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') {
        return Promise.resolve({ ...SIM, field_rate: null,
                                 notice: 'no field sample banked' })
      }
      return Promise.reject(new Error('x'))
    })
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByText(/no field sample banked/))
      .toBeInTheDocument()
  })

  it('offers the What if tab', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByRole('tab', { name: 'What if' }))
      .toBeInTheDocument()
  })
})
```

Create `frontend/src/hubs/league/WhatIfSim.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WhatIfSim from './WhatIfSim'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const SQUAD = [
  { code: 100, name: 'Salah', position: 'MID' },
  { code: 101, name: 'Dud', position: 'DEF' },
]

const RESULT = {
  baseline_p_win: 0.42, p_win: 0.31, delta_p_win: -0.11,
  baseline_exp_finish: 1.6, exp_finish: 2.1, delta_rank: 0.5,
  table: [
    { entry: 1, name: 'Mine', is_you: true, total: 300, p_win: 0.31,
      exp_finish: 2.1 },
    { entry: 2, name: 'Ten Hag Hive', is_you: false, total: 290, p_win: 0.69,
      exp_finish: 0 },
  ],
  unknown_codes: [],
}

describe('WhatIfSim', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    apiPost.mockResolvedValue(RESULT)
  })

  it('asks for nothing until an event is pinned', () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    expect(apiPost).not.toHaveBeenCalled()
    expect(screen.getByText(/pick an event/i)).toBeInTheDocument()
  })

  it('prices a blank as a change in title odds', async () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/league/whatif',
      { pins: [{ code: 100, event: 'blank' }], captain_override: null,
        rival_captain_blanks: null }))
    expect(await screen.findByTestId('delta-p-win')).toHaveTextContent('-11')
  })

  it('shows the re-scored table', async () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    expect(await screen.findByTestId('whatif-row-2')).toHaveTextContent('69%')
  })

  it('clears back to no pins', async () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    await screen.findByTestId('delta-p-win')
    await userEvent.click(screen.getByRole('button', { name: /clear/i }))
    expect(screen.getByText(/pick an event/i)).toBeInTheDocument()
  })

  it('reports a code the server could not resolve', async () => {
    apiPost.mockResolvedValue({ ...RESULT, unknown_codes: [999] })
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    expect(await screen.findByText(/999/)).toBeInTheDocument()
  })

  it('shows a retriable message when the endpoint is down', async () => {
    apiPost.mockRejectedValue(new Error('422'))
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    expect(await screen.findByText(/could not be run/i)).toBeInTheDocument()
  })

  it('is an empty state without a squad', () => {
    render(<WhatIfSim squad={[]} rivals={[]} />)
    expect(screen.getByText(/run advise/i)).toBeInTheDocument()
  })
})
```

- [ ] **Run them, expecting failure.** `cd frontend && npx vitest run src/hubs/League.test.tsx src/hubs/league/WhatIfSim.test.tsx`
  Expected: `WhatIfSim` fails to resolve; the League cases fail on the missing test ids.

- [ ] **Write the panel.** Create `frontend/src/hubs/league/WhatIfSim.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiPost } from '../../api/client'
import { Badge, Card, EmptyState, Loading, fmtPct } from '../../kit'
import type {
  LeagueWhatIfEvent, LeagueWhatIfRequest, LeagueWhatIfResult,
} from '../../types'

export interface WhatIfSquadPlayer {
  code: number
  name: string
  position: string
}

export interface WhatIfRival {
  entry: number
  name: string
}

export interface WhatIfSimProps {
  squad: WhatIfSquadPlayer[]
  rivals: WhatIfRival[]
}

const EVENTS: LeagueWhatIfEvent[] = ['haul', 'score', 'blank']

/**
 * "What would that week do to my title odds?"
 *
 * Deliberately not the squad What-If Lab. That one re-solves the MILP under
 * constraints and answers "what should I do"; this one pins events into the
 * coming gameweek and answers "what would happen" — no transfer is proposed
 * and no solve is run. Keeping them apart is spec D5.
 *
 * Nothing is requested until something is pinned: an empty panel and the
 * league card would otherwise ask the same question twice on every page load.
 */
export default function WhatIfSim({ squad, rivals }: WhatIfSimProps) {
  const [pins, setPins] = useState<Record<number, LeagueWhatIfEvent>>({})
  const [captain, setCaptain] = useState<number | null>(null)
  const [rivalBlank, setRivalBlank] = useState<number | null>(null)
  const [result, setResult] = useState<LeagueWhatIfResult | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  const empty = Object.keys(pins).length === 0 && captain === null
    && rivalBlank === null

  useEffect(() => {
    if (empty) { setResult(null); setFailed(false); return }
    const body: LeagueWhatIfRequest = {
      pins: Object.entries(pins).map(([code, event]) => (
        { code: Number(code), event })),
      captain_override: captain,
      rival_captain_blanks: rivalBlank,
    }
    let cancelled = false
    setBusy(true)
    apiPost<LeagueWhatIfResult>('/api/league/whatif', body)
      .then((out) => { if (!cancelled) { setResult(out); setFailed(false) } })
      .catch(() => { if (!cancelled) { setResult(null); setFailed(true) } })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [pins, captain, rivalBlank, empty])

  if (squad.length === 0) {
    return (
      <EmptyState
        title="No squad to play with"
        detail="The league what-if prices events against your saved squad, so
                it needs one. Run advise and come back."
        action="Run advise"
      />
    )
  }

  const toggle = (code: number, event: LeagueWhatIfEvent) => {
    setPins((prev) => {
      const next = { ...prev }
      if (next[code] === event) delete next[code]
      else next[code] = event
      return next
    })
  }

  return (
    <>
      <Card title="Pin an event" className="mb-4">
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Player</th>
              {EVENTS.map((e) => (
                <th key={e} className="label pb-1 text-right capitalize">{e}</th>
              ))}
              <th className="label pb-1 text-right">Captain</th>
            </tr>
          </thead>
          <tbody>
            {squad.map((player) => (
              <tr key={player.code} className="border-t border-divider">
                <td className="py-1 text-text-secondary">{player.name}</td>
                {EVENTS.map((event) => (
                  <td key={event} className="py-1 text-right">
                    <button
                      type="button"
                      data-testid={`pin-${player.code}-${event}`}
                      aria-pressed={pins[player.code] === event}
                      onClick={() => toggle(player.code, event)}
                      className={`px-2 py-0.5 text-xs ${
                        pins[player.code] === event
                          ? 'text-text underline' : 'text-text-muted'}`}
                    >
                      {event}
                    </button>
                  </td>
                ))}
                <td className="py-1 text-right">
                  <button
                    type="button"
                    data-testid={`captain-${player.code}`}
                    aria-pressed={captain === player.code}
                    onClick={() => setCaptain(
                      captain === player.code ? null : player.code)}
                    className={`px-2 py-0.5 text-xs ${
                      captain === player.code
                        ? 'text-text underline' : 'text-text-muted'}`}
                  >
                    (C)
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rivals.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="label">Rival captain blanks</span>
            {rivals.map((rival) => (
              <button
                key={rival.entry}
                type="button"
                data-testid={`rival-blank-${rival.entry}`}
                aria-pressed={rivalBlank === rival.entry}
                onClick={() => setRivalBlank(
                  rivalBlank === rival.entry ? null : rival.entry)}
                className={`px-2 py-0.5 text-xs ${
                  rivalBlank === rival.entry
                    ? 'text-text underline' : 'text-text-muted'}`}
              >
                {rival.name}
              </button>
            ))}
          </div>
        )}
        <div className="mt-3">
          <button type="button" className="text-xs text-text-muted underline"
                  onClick={() => {
                    setPins({}); setCaptain(null); setRivalBlank(null)
                  }}>
            Clear
          </button>
        </div>
      </Card>

      {empty && (
        <Card>
          <p className="text-text-muted">
            Pick an event above — a haul, a blank, a different armband — and
            the league is re-simulated with it pinned into this gameweek.
          </p>
        </Card>
      )}
      {!empty && failed && (
        <Card>
          <p className="text-text-muted">
            The simulation could not be run. Untick something and try again,
            or check the server.
          </p>
        </Card>
      )}
      {!empty && busy && !result && <Loading />}
      {!empty && result && (
        <Card title="If that happened">
          <div className="mb-3 flex items-baseline gap-3">
            <span className="num text-2xl text-text" data-testid="delta-p-win">
              {`${result.delta_p_win >= 0 ? '+' : ''}${
                (result.delta_p_win * 100).toFixed(1)} pp`}
            </span>
            <span className="text-text-muted">
              {`title odds ${fmtPct(result.baseline_p_win)} → `}
              {fmtPct(result.p_win)}
              {`, expected finish ${result.baseline_exp_finish.toFixed(2)} → `}
              {result.exp_finish.toFixed(2)}
            </span>
          </div>
          {result.unknown_codes.length > 0 && (
            <p className="mb-2 text-text-muted">
              {`Not in this week's squad data, so ignored: ${
                result.unknown_codes.join(', ')}.`}
            </p>
          )}
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Team</th>
                <th className="label pb-1 text-right">Total</th>
                <th className="label pb-1 text-right">P(win)</th>
              </tr>
            </thead>
            <tbody>
              {result.table.map((row) => (
                <tr key={row.entry} data-testid={`whatif-row-${row.entry}`}
                    className="border-t border-divider">
                  <td className="py-1 text-text-secondary">
                    {row.name}
                    {row.is_you && <Badge className="ml-2">you</Badge>}
                  </td>
                  <td className="num py-1 text-right text-text-muted">
                    {row.total}
                  </td>
                  <td className="num py-1 text-right text-text">
                    {fmtPct(row.p_win)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  )
}
```

If `Badge` does not take a `className` prop, drop it and render the word plainly — check `frontend/src/kit/Badge.tsx` before writing the line rather than after `tsc` complains.

- [ ] **Wire the hub.** In `frontend/src/hubs/League.tsx`:

Extend the imports:

```tsx
import { Sparkline } from '../kit'
import type { LeagueSimData } from '../types'
import WhatIfSim from './league/WhatIfSim'
```

Add the state and the fetch beside the existing two:

```tsx
  const [sim, setSim] = useState<LeagueSimData | null>(null)
```

```tsx
    // The simulated card degrades to the parametric one rather than to an
    // error: /api/league/race already carries those numbers, and a league
    // page with no win-probability panel at all is a worse answer than an
    // older one.
    apiGet<LeagueSimData>('/api/league/sim').then(setSim).catch(() => setSim(null))
```

Replace the whole `<Card title="Win probability">` block with:

```tsx
          {sim ? (
            <Card title="Win probability">
              <div className="mb-3 flex flex-wrap items-baseline gap-4">
                <div>
                  <div className="label">P(win)</div>
                  <div className="num text-2xl text-text"
                       data-testid="sim-p-win">{fmtPct(sim.p_win)}</div>
                </div>
                <div>
                  <div className="label">P(top 3)</div>
                  <div className="num text-2xl text-text"
                       data-testid="sim-p-top3">{fmtPct(sim.p_top3)}</div>
                </div>
                <div>
                  <div className="label">Expected finish</div>
                  <div className="num text-2xl text-text">
                    {fmtNum(sim.exp_finish, 2)}
                  </div>
                </div>
                {sim.history.length > 1 && (
                  <div data-testid="sim-sparkline">
                    <div className="label">Trend</div>
                    <Sparkline values={sim.history.map((h) => h.p_win)} />
                  </div>
                )}
              </div>
              {/* A probability with no n and no seed beside it is a
                  decoration: this is the line that makes it a measurement. */}
              <p className="mb-3 text-text-muted" data-testid="sim-provenance">
                {`${sim.n.toLocaleString()} simulations, seed ${sim.seed}, `}
                {`rival drift ${sim.rival_drift}, ${sim.weeks_left} `}
                {'gameweeks left.'}
              </p>
              {sim.notice && (
                <p className="mb-3 text-text-muted">{sim.notice}</p>
              )}
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="label pb-1 text-left">Rival</th>
                    <th className="label pb-1 text-right">P(I beat him)</th>
                  </tr>
                </thead>
                <tbody>
                  {sim.per_rival.map((rival) => (
                    <tr key={rival.entry} data-testid={`beat-${rival.entry}`}
                        className="border-t border-divider">
                      <td className="py-1 text-text-secondary">{rival.name}</td>
                      <td className="num py-1 text-right text-text">
                        {fmtPct(rival.p_beat)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ) : (
            <Card title="Win probability"
                  data-testid="legacy-win-probability">
              {/* The pre-v8c parametric pairwise numbers, kept as the
                  fallback until the simulated card is always available. */}
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="label pb-1 text-left">Team</th>
                    <th className="label pb-1 text-right">P(win)</th>
                    <th className="label pb-1 text-right">Projected</th>
                  </tr>
                </thead>
                <tbody>
                  {race.win_probability.map((prob) => (
                    <tr key={prob.name} className="border-t border-divider">
                      <td className="py-1 text-text-secondary">{prob.name}</td>
                      <td className="num py-1 text-right text-text">
                        {fmtPct(prob.p_win)}
                      </td>
                      <td className="num py-1 text-right text-text-muted">
                        {fmtNum(prob.total, 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
```

If `Card` does not forward `data-testid`, wrap the legacy card in a `<div data-testid="legacy-win-probability">` instead — check `frontend/src/kit/Card.tsx` first.

Add the third tab trigger and its content:

```tsx
          <Tabs.Trigger value="whatif" className={TAB_CLASS}>What if</Tabs.Trigger>
```

```tsx
        <Tabs.Content value="whatif">
          <WhatIfSim
            squad={squad}
            rivals={race.standings.filter((s) => !s.is_you)
              .map((s) => ({ entry: s.entry, name: s.name }))}
          />
        </Tabs.Content>
```

The panel pins events against my own XI, which the League hub does not currently fetch. Add the state beside the other three:

```tsx
  const [squad, setSquad] = useState<WhatIfSquadPlayer[]>([])
```

and the fetch beside the others in the same `useEffect`. An empty squad is a working empty state in the panel, so the failure path is `[]` rather than an error:

```tsx
    apiGet<AdviceData>('/api/advice')
      .then((body) => setSquad(body.xi.map((p) => (
        { code: p.code, name: p.name, position: p.position ?? '' }))))
      .catch(() => setSquad([]))
```

`AdviceData` and `WhatIfSquadPlayer` join the type imports. Read `ThisWeek.tsx`'s `/api/advice` call before writing this and reuse the interface it already names — if the payload type is called something else in `types.ts`, use that name; two interfaces for one endpoint is how the two pages end up disagreeing about it.

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/League.test.tsx src/hubs/league/WhatIfSim.test.tsx && npx tsc --noEmit`
  Expected: green, `tsc` silent.

- [ ] **Commit.**

```bash
git add frontend/src/hubs/League.tsx frontend/src/hubs/League.test.tsx frontend/src/hubs/league/WhatIfSim.tsx frontend/src/hubs/league/WhatIfSim.test.tsx && git commit -m "$(cat <<'EOF'
feat: the simulated win-probability card and the league What-if tab

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — F3: This Week's captaincy chip

**Files:**
- Modify `frontend/src/hubs/ThisWeek.tsx` (the Starting XI card's `action`)
- Modify `frontend/src/hubs/ThisWeek.test.tsx` (append)

The constraint from the spec is the interesting part: the chip appears *only when the sim cache is fresh*, and This Week never blocks on it. So the fetch is fire-and-forget, its failure is silence, and nothing on the page waits for it.

- [ ] **Write the failing test.** Append to `frontend/src/hubs/ThisWeek.test.tsx`:

```tsx
describe('the captaincy title-odds chip', () => {
  it('prices the armband against the alternative when the sim answers',
     async () => {
       // apiPost is the what-if call; the chip asks for the captain swap the
       // vice would have been.
       apiPost.mockResolvedValue({
         baseline_p_win: 0.42, p_win: 0.39, delta_p_win: -0.03,
         baseline_exp_finish: 1.6, exp_finish: 1.7, delta_rank: 0.1,
         table: [], unknown_codes: [],
       })
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       expect(await screen.findByTestId('captain-odds-chip'))
         .toHaveTextContent('+3.0%')
     })

  it('is simply absent when the simulation is not available', async () => {
    apiPost.mockRejectedValue(new Error('422'))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText(/Starting XI/)).toBeInTheDocument()
    expect(screen.queryByTestId('captain-odds-chip')).not.toBeInTheDocument()
  })

  it('never blocks the page on it', async () => {
    apiPost.mockReturnValue(new Promise(() => {}))     // never resolves
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText(/Starting XI/)).toBeInTheDocument()
  })
})
```

Match the file's existing mock setup — if `ThisWeek.test.tsx` does not already hoist `apiPost`, add it to the same `vi.hoisted`/`vi.mock` block the file already has rather than writing a second one.

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx -t chip`
  Expected: the chip test id is not found.

- [ ] **Write the implementation.** In `frontend/src/hubs/ThisWeek.tsx`, add the state and the effect near the other hooks:

```tsx
  // The armband priced in title odds. Deliberately fire-and-forget: This Week
  // is the page the user opens on a Thursday evening and it must render at
  // the same speed whether or not a league simulation is available. A failure
  // — no league configured, no field sample, a cold cache — is silence, not
  // an error state.
  const [capOdds, setCapOdds] = useState<number | null>(null)
  useEffect(() => {
    if (!advice?.vice?.code) return
    let cancelled = false
    apiPost<LeagueWhatIfResult>('/api/league/whatif',
                                { pins: [],
                                  captain_override: advice.vice.code,
                                  rival_captain_blanks: null })
      .then((out) => { if (!cancelled) setCapOdds(-out.delta_p_win) })
      .catch(() => { if (!cancelled) setCapOdds(null) })
    return () => { cancelled = true }
  }, [advice?.vice?.code])
```

The sign flip is the whole point of the chip: the endpoint prices *switching to the vice*, and the sentence on screen is what keeping the captain is worth.

Extend the Starting XI card's `action`:

```tsx
        action={(
          <span className="text-text-muted">
            Captain {advice.captain.name}
            {advice.scenarios?.captain_frequency !== undefined
              && ` · ${fmtPct(advice.scenarios.captain_frequency)} of sims`}
            {' · vice '}{advice.vice.name}
            {capOdds !== null && (
              <span className="ml-2" data-testid="captain-odds-chip">
                {`· ${capOdds >= 0 ? '+' : ''}${(capOdds * 100).toFixed(1)}% `}
                {'title odds vs vice'}
              </span>
            )}
          </span>
        )}
```

with `apiPost` and `LeagueWhatIfResult` added to the file's imports.

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx && npx tsc --noEmit`
  Expected: green.

- [ ] **Commit.**

```bash
git add frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx && git commit -m "$(cat <<'EOF'
feat: the captaincy title-odds chip on This Week

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — F4: sword, shield and threat

**Files:**
- Modify `src/gaffer/web/schemas.py` (`PlayerRow`: two new optional fields)
- Modify `src/gaffer/web/routers/players.py` (fill them from the log)
- Create `tests/test_web_players_v8c.py`
- Modify `frontend/src/types.ts` (`PlayerRow`)
- Modify `frontend/src/hubs/Players.tsx` (the column)
- Modify `frontend/src/hubs/players/ComparePanel.tsx` (the row)
- Modify `frontend/src/hubs/Players.test.tsx` (append)

The classification is three words for the position a player puts you in against the field, and it only makes sense next to *ownership*: a highly-owned player you own is a shield (he cannot hurt you, and he cannot help), a lowly-owned player you own is a sword, and a highly-owned player you do not own is a threat. Everything else is noise and gets no label.

- [ ] **Write the failing test.** Create `tests/test_web_players_v8c.py`:

```python
"""F4: the field-EO column and its sword/shield reading.

Pure display over ``field_eo_log``. The rail that matters is that an absent
log leaves the column *absent* — null on every row — rather than zero, because
"the top 10k do not own him" and "we have never scraped the top 10k" are
opposite statements and a nought would print the wrong one.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.data.field import append_field_eo, field_eo_rows
from gaffer.web.app import create_app
from gaffer.web.routers.players import field_class

# Reuse the artifact fixture the league-sim suite builds; codes 100 (owned,
# element 7) and 101 (not owned, element 8).
from tests.test_web_league_sim import _artifacts


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    _artifacts(tmp_path)
    return TestClient(create_app())


def _log(gw=2, table=None):
    append_field_eo(field_eo_rows(
        table or {7: {"eo": 78.0, "se": 2.0, "n": 300},
                  8: {"eo": 4.0, "se": 1.0, "n": 300}},
        gw, "2026-27", day="2026-09-12"))


@pytest.mark.parametrize("owned,eo,expected", [
    (True, 78.0, "shield"),
    (True, 4.0, "sword"),
    (False, 78.0, "threat"),
    (False, 4.0, None),
    (True, None, None),
])
def test_the_classification_is_ownership_crossed_with_the_field(owned, eo,
                                                                expected):
    assert field_class(owned, eo) == expected


def test_the_column_is_absent_without_a_log(client):
    rows = client.get("/api/players").json()
    assert all(r["field_eo"] is None for r in rows)
    assert all(r["field_class"] is None for r in rows)


def test_the_column_carries_the_latest_scrape(client):
    _log()
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[100]["field_eo"] == 78.0
    assert rows[101]["field_eo"] == 4.0


def test_a_player_i_own_that_the_field_owns_is_a_shield(client):
    _log()
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[100]["field_class"] == "shield"


def test_a_player_the_field_ignores_that_i_do_not_own_gets_no_label(client):
    _log()
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[101]["field_class"] is None


def test_a_player_missing_from_the_scrape_is_null_not_zero(client):
    """Absent from a sparse table means "no sampled entry started him", which
    the log records by omission. The column has to say "unknown" rather than
    invent a 0.0 the user would read as a differential."""
    _log(table={7: {"eo": 78.0, "se": 2.0, "n": 300}})
    rows = {r["code"]: r for r in client.get("/api/players").json()}
    assert rows[101]["field_eo"] is None


def test_a_corrupt_log_does_not_take_the_explorer_down(client, monkeypatch):
    """The router must call the log read inside a guard. A parquet file that
    was half-written when a laptop slept is a bad afternoon for one column,
    not for the whole player explorer."""
    def _boom():
        raise RuntimeError("corrupt parquet")

    monkeypatch.setattr("gaffer.web.routers.players.latest_field_eo", _boom)
    res = client.get("/api/players")
    assert res.status_code == 200
    assert all(r["field_eo"] is None for r in res.json())
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_players_v8c.py`
  Expected: `ImportError: cannot import name 'field_class'`.

- [ ] **Write the schema fields.** In `src/gaffer/web/schemas.py`, add to `PlayerRow`, after `league_eo`:

```python
    field_eo: float | None = None
    """Top-10k effective ownership from the latest banked scrape.

    ``None`` means *unknown*, and it means it in two different situations
    that the UI renders identically and correctly: no field log at all, or a
    log that does not carry this player because no sampled entry started him.
    Neither is 0.0, which the reader would take as a measured differential."""
    field_class: str | None = None
    """``shield`` | ``sword`` | ``threat``, or ``None`` for the quadrant with
    nothing to say."""
```

- [ ] **Write the router side.** In `src/gaffer/web/routers/players.py`, add the import and the helper above the endpoint:

```python
from gaffer.data.field import latest_field_eo

FIELD_HIGH = 40.0
FIELD_LOW = 15.0
"""Effective-ownership percent that counts as the field being *on* a player,
and the level below which it is not.

Two thresholds rather than one so the middle of the distribution — the third
of the game that is neither a template pick nor a punt — carries no label at
all. Labelling everything is how a classification stops meaning anything."""


def field_class(owned: bool, eo: float | None) -> str | None:
    """Where this player puts you against the field.

    * ``shield`` — you own him and so does the field: he cannot cost you rank.
    * ``sword`` — you own him and the field does not: every point is a gain.
    * ``threat`` — the field owns him and you do not: his good week is your
      bad one.

    The fourth quadrant (nobody owns him) is not a position, it is the rest of
    the game, and it gets no label.
    """
    if eo is None:
        return None
    if owned:
        if eo >= FIELD_HIGH:
            return "shield"
        return "sword" if eo <= FIELD_LOW else None
    return "threat" if eo >= FIELD_HIGH else None
```

and in the row construction, add the two fields — reading the log once, outside the loop:

```python
    # Pure display: an unreadable log is a missing column, never a 500. The
    # explorer must render on a clone that has never run a scrape.
    try:
        field_eo = latest_field_eo()
    except Exception:  # noqa: BLE001
        field_eo = {}
```

```python
            field_eo=(field_eo.get(int(element)) or {}).get("eo"),
            field_class=field_class(
                code in owned_codes,
                (field_eo.get(int(element)) or {}).get("eo")),
```

Use whatever local names the function already has for the player's element and for the owned-code set — read the surrounding twenty lines before writing this rather than assuming `element` and `owned_codes`.

- [ ] **Write the frontend side.** In `frontend/src/types.ts`, add to `PlayerRow`:

```ts
  /** Top-10k EO from the latest field scrape; null = never scraped, or no
   *  sampled entry started him. Never 0 for "unknown". */
  field_eo: number | null
  field_class: 'shield' | 'sword' | 'threat' | null
```

In `frontend/src/hubs/Players.tsx`, add the column after `league_eo`:

```tsx
    { key: 'field_eo', header: 'Field%', numeric: true,
      value: (r) => (r.field_eo === null ? '—' : fmtNum(r.field_eo, 1)),
      // The label is the reason the column is here: a number is ownership, a
      // word is a position.
      sub: (r) => r.field_class ?? '' },
```

matching the `Column` type's actual optional members — read `frontend/src/kit/DataTable.tsx` first and drop `sub` if there is no such member, rendering the word inside `value` instead.

In `frontend/src/hubs/players/ComparePanel.tsx`, add a row to the header comparison block:

```tsx
          <tr>
            <th className="label pb-1 text-left">Field EO</th>
            {players.map((p) => (
              <td key={p.code} className="num py-1 text-right text-text">
                {p.field_eo === null ? '—' : `${fmtNum(p.field_eo, 1)}%`}
                {p.field_class && (
                  <span className="ml-1 text-text-muted">{p.field_class}</span>
                )}
              </td>
            ))}
          </tr>
```

placing it inside whatever table the panel already uses for its per-player header facts — if it has none, put the same content in a small `<Card title="Field EO">` above the components chart.

- [ ] **Append the frontend test.** In `frontend/src/hubs/Players.test.tsx`:

```tsx
  it('shows an em dash rather than a nought when the field is unknown',
     async () => {
       // A 0 here would read as "the top 10k have written him off", which is
       // a claim, and we have not measured it.
       render(<MemoryRouter><Players /></MemoryRouter>)
       expect(await screen.findByText('—')).toBeInTheDocument()
     })
```

adapting the surrounding fixture so at least one row carries `field_eo: null` and one carries a number with a `field_class`.

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_players_v8c.py tests/test_web_players.py && cd frontend && npx vitest run src/hubs/Players.test.tsx src/hubs/players/ComparePanel.test.tsx && npx tsc --noEmit`
  Expected: green throughout.

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/players.py tests/test_web_players_v8c.py frontend/src/types.ts frontend/src/hubs/Players.tsx frontend/src/hubs/Players.test.tsx frontend/src/hubs/players/ComparePanel.tsx && git commit -m "$(cat <<'EOF'
feat: F4 sword/shield field EO in the explorer and compare panel

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 15 — G3: the degradation rails

**Files:**
- Create `tests/test_v8c_degradation.py`

This is the file the orchestrator's G3 runs. It is a *new* file: every existing `tests/test_*_degradation.py` is protected and must show a zero diff.

- [ ] **Write it.** Create `tests/test_v8c_degradation.py`:

```python
"""v8c's rails: what the machine does when the field is not there.

Gate G3 (spec §5). Every case here is a real Tuesday — a fresh clone, a switch
turned off, an FPL outage, a gameweek nobody scraped — and the claim is that
each of them degrades to v8a behaviour rather than to an error.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.field import (FIELD_EO_PATH, latest_field_eo,
                               load_field_sample, run_field_scrape)
from gaffer.data.tier_eo import tier_eo_table
from gaffer.web import job_kinds
from gaffer.web.app import create_app
from tests.test_web_league_sim import FakeClient, _artifacts, _comp


@pytest.fixture()
def bare(tmp_path, monkeypatch):
    """A clone that has never run a scrape."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    monkeypatch.setattr("gaffer.data.field.RAW_TIER",
                        tmp_path / "data/raw/tier_eo")
    _artifacts(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    return tmp_path


# --- the field store absent ------------------------------------------------


def test_the_league_hub_answers_without_any_field_store(bare):
    """v8a behaviour, unchanged: /race is what it always was and /sim runs
    with drift off rather than refusing."""
    client = TestClient(create_app())
    assert client.get("/api/league/race").status_code == 200
    body = client.get("/api/league/sim").json()
    assert body["field_rate"] is None
    assert 0.0 <= body["p_win"] <= 1.0


def test_the_explorer_column_is_absent_rather_than_zero(bare):
    rows = TestClient(create_app()).get("/api/players").json()
    assert all(r["field_eo"] is None for r in rows)


def test_the_latest_read_of_a_missing_log_is_empty(bare):
    assert latest_field_eo() == {}
    assert not store.exists(FIELD_EO_PATH)


def test_a_missing_sample_is_none_not_a_crash(bare):
    assert load_field_sample("2026-27", 3) is None


# --- the scrape switch off -------------------------------------------------


def test_the_switch_off_makes_no_api_calls_at_all(bare, monkeypatch):
    """Spied rather than asserted in prose: an off switch that still fetches
    is the failure mode that costs a rate limit."""
    calls = []
    monkeypatch.setattr("gaffer.api.client.FPLClient",
                        lambda *a, **kw: calls.append("client"))
    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks",
                        lambda *a, **kw: calls.append("fetch") or [])
    off = Config(entry_id=1, league_id=5, current_season="2026-27",
                 field_scrape=False)
    assert run_field_scrape(off) is None
    assert calls == []


def test_the_job_kind_reports_a_switched_off_scrape_as_zero_rows(bare,
                                                                 monkeypatch):
    monkeypatch.setattr("gaffer.data.field.run_field_scrape", lambda: None)
    assert job_kinds.run_field_scrape_job() == {"rows": 0}


# --- a dead API ------------------------------------------------------------


def test_every_new_endpoint_is_a_422_when_the_api_is_dead(bare, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    client = TestClient(create_app())
    assert client.get("/api/league/sim").status_code == 422
    assert client.post("/api/league/whatif",
                       json={"pins": []}).status_code == 422


def test_a_dead_api_never_reaches_a_500(bare, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    client = TestClient(create_app())
    for path in ("/api/league/sim",):
        assert client.get(path).status_code != 500


def test_a_dead_api_leaves_the_scrape_printing_one_line(bare, monkeypatch,
                                                         capsys):
    def _boom(*a, **kw):
        raise RuntimeError("FPL is down")

    monkeypatch.setattr("gaffer.api.client.FPLClient", _boom)
    assert run_field_scrape(Config(entry_id=1, league_id=5)) is None
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


# --- the tier-EO contract --------------------------------------------------


def test_the_tier_table_is_byte_compatible_with_v8a(bare, monkeypatch,
                                                     tmp_path):
    """The live tracker's cache file is a compatibility surface: its shape,
    its keys and its rounding are what v8a wrote, and the field store's
    existence changes none of them."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)

    class _One:
        def get_league_standings(self, league_id, page=1):
            return {"standings": {"results": [{"entry": 100 + s}
                                              for s in range(50)]}}

        def get_entry_picks(self, entry_id, gw):
            return {"picks": [{"element": 7, "multiplier": 2}]}

    out = tier_eo_table(_One(), 3, sample=1, raw_dir=tmp_path / "tier")
    assert out == {7: {"eo": 200.0, "se": 0.0, "n": 1}}
    raw = json.loads((tmp_path / "tier" / "3.json").read_text())
    assert raw == {"7": {"eo": 200.0, "se": 0.0, "n": 1}}


def test_the_live_endpoint_still_answers_with_no_field_store(bare):
    """``/api/live`` reads ``tier_eo_table`` and nothing else v8c added. The
    live suite pins its payload; this pins that v8c did not change which
    module it reaches."""
    import inspect

    from gaffer.web.routers import live

    assert "field" not in inspect.getsource(live)


# --- the what-if identity --------------------------------------------------


def test_an_empty_whatif_equals_the_sim_endpoint(bare):
    client = TestClient(create_app())
    base = client.get("/api/league/sim").json()
    out = client.post("/api/league/whatif", json={"pins": []}).json()
    assert out["p_win"] == base["p_win"]
    assert out["delta_p_win"] == 0.0


# --- the pins --------------------------------------------------------------


def test_the_job_kind_count_is_pinned():
    """Lockstep with ``frontend/src/types.ts``. A kind added on one side only
    is a button that 404s."""
    assert len(job_kinds.JOB_KINDS) == 8
    assert "field-scrape" in job_kinds.JOB_KINDS


def test_the_protected_seam_is_imported_not_edited():
    """Spec D4: the sigma table is read through ``scenarios``' public names.
    A reach into a private one would survive review and break on the next
    ``optimize`` change."""
    import inspect

    from gaffer import league_sim

    source = inspect.getsource(league_sim)
    assert "from gaffer.optimize.scenarios import" in source
    assert "scenarios._" not in source


def test_league_mode_win_probability_still_has_its_caller():
    """v8c supersedes it in the *card*, not in the codebase: /api/league/race
    still serves it and the UI still falls back to it."""
    import inspect

    from gaffer.web.routers import league

    assert "win_probability" in inspect.getsource(league)
```

- [ ] **Run it.** `uv run pytest -q tests/test_v8c_degradation.py`
  Expected: `16 passed`.

- [ ] **Commit.**

```bash
git add tests/test_v8c_degradation.py && git commit -m "$(cat <<'EOF'
test: v8c degradation rails for gate G3

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 16 — the documentation

**Files:**
- Modify `README.md` (Configuration ~L61; League strategy ~L125; Where things live ~L255; Automation ~L274)

- [ ] **Write it.** In `README.md`:

Under **Configuration**, after the `[news]` block, add:

```markdown
### `[league]`

| Key | Default | What it does |
| --- | --- | --- |
| `z_scale` | 1.5 | Points of gap per unit of z before the tilt moves. |
| `lambda_cap` | 0.5 | The most the tilt may bend the candidate board. |
| `sigma_floor` / `sigma_cap` | 8 / 30 | Bounds on the weekly-points sigma the gap is measured in. |
| `sigma_min_weeks` | 6 | Gameweeks of history before sigma is estimated rather than assumed. |
| `z_deadband` | 0.25 | `|z|` under this is noise: no tilt at all. |
| `tier_eo` | true | The live tracker's top-10k EO column. |
| `tier_sample` | 300 | Entries sampled from the top 10k. |
| `field_scrape` | true | v8c: the scheduled version of the same sample, which also keeps the squads. |
| `field_sample` | = `tier_sample` | Sample size for the scheduled scrape. |
| `sim_n` | 2000 | Simulations per mini-league Monte Carlo run. |
| `rival_drift` | 0.5 | How far a rival's squad drifts toward the field template over the rest of the season. 0 freezes every squad. |
```

Under **League strategy**, append:

```markdown
### The simulated league (v8c)

The League hub's win-probability card is a Monte Carlo, not a formula: 2,000
seeded seasons of your actual mini-league, every rival on the squad he last
played, per-player noise from the same sigma table the scenario sweep uses,
and rivals drifting toward the top-10k template at `rival_drift`. It reports
P(win), P(top 3), expected finish, per-rival P(beat) and a fan of final
margins — with its `n` and its seed printed underneath, because a probability
nobody can reproduce is a decoration.

```
uv run gaffer league-sim --seeds 1,2,3
```

prints the same headline under three seed bases with the spread, which is the
only form a *recorded* claim about this number may take
(`docs/superpowers/CONVENTIONS.md` §1).

The **What if** tab prices a week: pin a haul, a blank or a different armband
and the league is re-simulated with that event fixed. It is not the squad
What-If Lab — no MILP is re-solved and no transfer is proposed. The question
is "what would that week do to my title odds".

None of this feeds the optimizer. The λ tilt remains the only thing that
shapes advice; the simulation is measurement and display.
```

Under **Where things live**, add the two stores:

```markdown
- `data/raw/field/{season}/gw{N}.json` — the top-10k squads sampled for that
  gameweek. Permanent, and anonymous: entries are keyed by their index in the
  sample, never by entry id.
- `data/live/field_eo_log.parquet` — one row per (gameweek, scrape day,
  element): effective ownership in the top 10k with its standard error and
  its sample size.
- `reports/league_sim_history.json` — one banked headline per gameweek, which
  is what the league card's sparkline draws.
```

Under **Automation**, extend the list:

```markdown
- **Saturday and Sunday 12:30** — `gaffer field-scrape`, an hour after the
  11:30 deadline: samples ~300 top-10k entries, banks their squads and logs
  their EO. A gameweek already banked is a no-op in milliseconds, and a run
  that finds the live tracker has just done the same fetch reuses it rather
  than asking the API twice in an hour.
```

and add `field` to whatever list of installed jobs the section names.

- [ ] **Check the tables render.** `uv run python -c "print(open('README.md').read().count('| Key |'))"`
  Expected: one more than before the edit. (A markdown table that lost its header separator renders as a paragraph, and nobody notices for a year.)

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: v8c field intelligence — the [league] keys, the stores and the schedule

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 17 — the final audit and the orchestrator's gate checklist

**Files:** none created; this task produces a report and a hand-off.

- [ ] **Run the whole Python suite.** `uv run pytest -q`
  Expected: green, and roughly 1,880 tests — about 110 more than the ~1,773 v8c started from. The exact number is not a target and is not pinned anywhere; a *drop* is.

- [ ] **Run the whole frontend suite and the type-check.**

```bash
cd frontend && npx vitest run && npx tsc --noEmit && npx eslint src
```

Expected: green, roughly 320 tests (~302 at the start plus this cycle's), `tsc` silent, no new lint errors.

- [ ] **Audit the protected list.** Every path below must show no diff against the branch point:

```bash
git diff --stat main...HEAD -- \
  src/gaffer/advise.py src/gaffer/set_pieces.py 'src/gaffer/optimize/**' \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py
git diff --stat main...HEAD -- 'tests/test_*_degradation.py' \
  ':!tests/test_v8c_degradation.py'
```

Expected: both commands print nothing. Anything listed is a plan violation — report it, do not "fix" it by amending the file.

- [ ] **Audit `league_mode.py`.** It is not protected but was not meant to change:

```bash
git diff --stat main...HEAD -- src/gaffer/league_mode.py
uv run pytest -q tests/test_league_mode.py tests/test_v4d_degradation.py
```

Expected: no diff, and both suites green.

- [ ] **Audit what was staged.**

```bash
git diff --name-only main...HEAD | grep -E '^(data|reports|models|logs)/|config\.toml' || echo "clean"
```

Expected: `clean`. v8c commits no runtime artifact.

- [ ] **Security ritual (CONVENTIONS.md §8).**

```bash
git diff main...HEAD | grep -iE 'api[_-]?key|secret|token|password' || echo "no keys"
git show main:config.toml && echo "LEAK" || echo "config.toml is not tracked"
```

Expected: `no keys`, and `config.toml is not tracked`.

- [ ] **Confirm the anonymisation claim end to end.** After the orchestrator's G1 run there will be a real sample on disk; before it, confirm the code path cannot write an id:

```bash
grep -n '"entry"' src/gaffer/data/field.py || echo "no entry key written"
```

Expected: `no entry key written`.

- [ ] **Hand the gates over, unfilled.** Paste this into the cycle's hand-off. CONVENTIONS.md §7: the implementer builds the drivers and does not run them.

```markdown
### v8c gate checklist (orchestrator runs these)

**G1 — scrape live.** One real run: `uv run gaffer field-scrape`
- [ ] ≥ 250 sampled entries in `data/raw/field/{season}/gw{N}.json`
- [ ] EO-log row count == distinct elements seen in the sample
- [ ] every stored entry has 15 picks and exactly one multiplier ≥ 2
- [ ] no `entry` key anywhere in the stored JSON
- [ ] `/api/live` payload shape unchanged on the running server (diff against a v8a capture)
- [ ] idempotent re-run: second run adds 0 rows and prints the "already banked" line
- Evidence: ______

**G2 — sim sanity.**
- [ ] `uv run gaffer league-sim --seeds a,b,c` — 3-seed p_win spread recorded (no pass bar; this is the instrument's honesty label)
- [ ] determinism: same seed twice, identical p_win
- [ ] `rival_drift=0` degenerate case reproduced against a frozen-squad hand calculation
- [ ] wall clock ≤ 30s at `n=2000`, league size ≤ 50
- Recorded spread: ______

**G3 — degradation rails.**
- [ ] `uv run pytest -q tests/test_v8c_degradation.py` green
- [ ] field store absent ⇒ league hub identical to v8a
- [ ] scrape switch off ⇒ zero fetch calls (spy)
- [ ] dead API ⇒ 422s, never 500s
- [ ] `/api/live` tier EO byte-compatible with v8a
- [ ] what-if with no pins == `/api/league/sim`
- [ ] job-kind count pinned on both sides

**G4 — suite + protected audit.**
- [ ] full Python suite green (______ tests)
- [ ] full frontend suite green (______ tests), `tsc --noEmit` silent
- [ ] zero diffs on every protected path
- [ ] `league_mode.py` unchanged; v4d λ rails green
- [ ] nothing under `data/`, `reports/`, `models/`, `logs/` or `config.toml` staged

**Spec §8 (Outcome)** is filled at cycle end with the G2 spread transcribed verbatim (CONVENTIONS.md §4).
```

- [ ] **Report.** Summarise: tasks completed, suite counts before and after, any arm or rail that had to be relaxed and why, and the unfilled gate checklist above. Do not run the gates.
