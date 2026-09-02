# Gaffer v12 W4 Implementation Plan — field

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the one data source that changes what the tool can see. A collector for
`github.com/olbauday/FPL-Core-Insights` (per-match defensive detail, published
cup and European fixtures, club Elo), two pre-registered minutes arms built on
it, a rank-distribution simulation on top of the field EO the scrape already
banks, and a hand-edited set-piece override that beats the bootstrap's
`penalties_order` where the user knows better.

**Architecture.** Four items, and three of them are smaller or larger than
spec §5 assumes. Read this section before Task 1; it is where the spec is
wrong about the code and about the repository.

- **§5.1 is half-built already.** `src/gaffer/data/cups.py` (v8a) already
  targets this exact repository. It owns `CUPS_REPO`, `CUPS_RAW_BASE`,
  `CUPS_TREE_URL`, `repo_season()` (`"2025-26"` → `"2025-2026"`),
  `team_code_map()`, `_team_code()`, `_http()` and `_cached_get()`. The new
  collector **imports those five helpers rather than re-deriving them**
  (A1). What is genuinely new is the per-match player table, the
  all-tournaments fixture table and the Elo table.
- **§5.1's "per-season CSVs" is not one layout, it is two.** Measured live on
  2026-09-02 (A2, evidence below). The 2025-2026 and 2026-2027 folders use
  `data/<season>/By Gameweek/GW<n>/<table>.csv`; the 2024-2025 folder uses
  `data/<season>/<table>/GW<n>/<table>.csv` and puts its `teams.csv` under
  `data/2024-2025/teams/teams.csv` rather than at the season root. **So the
  collector must not build paths by template.** It enumerates them from the
  one recursive git-trees call `cups.py` already makes, keyed on basename and
  season folder, which is layout-agnostic by construction and is the only
  design that survives the split that already exists in the archive.
- **§5.1 says "ClubElo". There is no ClubElo file.** Elo arrives two ways:
  `teams.csv` carries an `elo` column, and every `fixtures.csv`/`matches.csv`
  row carries `home_team_elo` / `away_team_elo`. `elo.parquet` is therefore
  *derived* from those, and **is empty for 2026-27 today** — the current
  season's `teams.csv` has a blank `elo` column and GW1's fixtures have blank
  per-match elo. That is a real empty state the health line must say out
  loud, not a bug to chase.
- **§5.1 says "joins to `code` via the season's element map". The repo ships
  its own map**, better than ours: `data/<season>/players.csv` is
  `player_code,player_id,first_name,second_name,web_name,team_code,position`,
  where `player_code` **is** gaffer's stable `code` and `player_id` is the
  season element id. No name matching, no `season_name_codes` round trip.
- **§5.2's two arms cannot be measured on the shipped benchmark, and saying
  so is the whole point of this workstream's honesty.** `evaluation.py:1003`
  pins `BENCHMARK_TRAIN_MAX_IDX = 1` and `:1006` `BENCHMARK_TEST_IDX = 2`;
  with `config.toml:24`'s `train_seasons = ["2022-23", "2023-24", "2024-25",
  "2025-26"]` that is **train on 2022-23 + 2023-24, test on 2024-25**. The
  archive's earliest season is 2024-2025. So on the shipped window both arms
  would be **100% null in training and populated only in test** — which is
  precisely the confound that withdrew v5's `CONGESTION_FEATURES` and made
  v8a's `f2_league`/`f2_cups` value-identical (`models/train.py`'s
  `MINUTES_FEATURES` docstring records both). The plan therefore
  **pre-registers a shifted window** — train idx ≤ 2, test idx 3 (train
  2022-23…2024-25, test 2025-26) — runs the control arm on that same shifted
  window, and puts a coverage preflight in front of the driver that prints
  per-season non-null share and **refuses** when training coverage is zero.
- **§5.2's `role_wb_share` cannot use `defensive_contributions`.** That column
  exists in the 2025-2026 and 2026-2027 `playermatchstats.csv` and **not** in
  the 2024-2025 one (A3). The wing-back rule is therefore built from the
  columns present in both — `accurate_crosses`, `touches_opposition_box`,
  `start_min`, `finish_min`, `minutes_played` — and is a *stated convention*,
  written down in the docstring, not a fitted classifier.
- **§5.3's three outputs have one data source between them.** `P(green
  arrow)` is real and is built here. `P(top-10k)` needs a top-10k weekly
  score threshold: **no such series exists anywhere in this tree** (A4 —
  `build-history` builds `history/player_gw.parquet` and
  `history/fixtures.parquet` and nothing event-level; `data/live/events.parquet`
  carries `[gw, deadline_time, is_current, is_next, finished, data_checked,
  most_captained, most_selected]` and no score at all; the archive's
  `gameweek_summaries.csv` carries `average_entry_score` and `highest_score`,
  neither of which is a top-10k threshold). It ships as a **named empty
  state** with a ROADMAP checkbox. The "expected overall-rank change" needs a
  points→rank response, which needs several graded `(my_points, overall_rank)`
  pairs; the ledger banks both (`review.py:728,738`) but only GW1 and GW2 are
  `data_checked` today, so that too ships as a named empty state ("N of 5
  graded gameweeks").
- **§5.4 says `data/set_pieces.yaml`. There is no YAML parser in this
  project** — `pyproject.toml:6-20` has no `pyyaml` and `import yaml` fails in
  `.venv`. The override is **TOML** (`data/set_pieces.toml`), read with
  stdlib `tomllib`, which is what `config.py` and `data/manager_tenures.toml`
  already do. Adding a dependency for one hand-edited file is a cost with no
  buyer.
- **§5.4's "one read hook" needs `set_pieces.py` to relax its own no-I/O
  invariant, and there is no way round it without an `advise.py` edit.**
  `pen_table` builds `order_of` from `players["penalties_order"]` at
  `set_pieces.py:295-297`; `advise.py:455,458` is the only caller and is
  protected. Threading a parameter would need an `advise.py` line-group §5.4
  does not authorize. Applying the override in `bootstrap.build_players`
  instead would write manual values into `data/live/players.parquet`, which is
  supposed to record what FPL said. So Task 17 is a **STOP** that adds the
  lazy loader call inside `pen_table` *and amends the module docstring's
  "Nothing here does I/O" sentence in the same edit*, because leaving a
  docstring that the code has stopped obeying is worse than the I/O.

**Tech Stack:** Python 3.12, uv, httpx, pandas/pyarrow, numpy, LightGBM,
FastAPI + pydantic, tomllib, pytest; React 19 + TypeScript + vitest.

**Branch:** `feat/gaffer-v12`, cut at `27f7933` (the v12 spec commit).
Authoritative spec: `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md`.
Measurement rules: `docs/superpowers/CONVENTIONS.md`. Arm protocol:
`docs/superpowers/specs/2026-09-01-gaffer-v10-minutes-design.md` §F3a and
`scripts/v10_shrunk_arm.py` / `scripts/v10_autosub_cf.py`.

```bash
git rev-parse --abbrev-ref HEAD      # feat/gaffer-v12
git rev-parse HEAD                   # 27f793380aa6a399e8a5ac9793e2562ce6045bc5
```

**Protected — must show zero diffs at the end (Task 21 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py` — `test_degradation.py`,
v4c, v4d, v5, v6, v7_model, v8a, v8b, v8c, v8d, v8e, v8f, v8g, v9a, v9c, v9d,
v10, v10b, **v11** — and `scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`. Task 11
imports `backtest.STARTING_BUDGET` and `backtest._players_frame` and modifies
neither.

**This workstream enumerates exactly one protected edit: Task 17**, two
line-groups in `src/gaffer/set_pieces.py`, authorized by spec §5.4. Nothing
else in W4 touches a protected file. Three candidates that looked like they
might were resolved without one:

1. §5.2's features look like they belong in `MINUTES_FEATURES`. They do not
   ship there — they ship **off**, as arm columns the driver composes onto the
   module global exactly as `scripts/v10_shrunk_arm.py:227-228` does, so
   `models/train.py` gains a docstring paragraph and no behaviour.
2. §5.3 looks like it needs `optimize/**` for the player sigmas. It does not:
   `league_sim.py:45-47` already imports `scenario_noise`, `sigma_for`,
   `xmins_by_player_gw`, `NOISE_DENOM`, `NOISE_FLOOR_XMINS` by public name,
   and `element_sigmas` is already in `league_sim.py` (unprotected).
3. §5.4's badge looks like it needs `advise.py` to record which rows were
   overridden. It does not: `web/routers/players.py` (unprotected) reads the
   override file itself and marks the row, so the badge is a display fact and
   never enters an EP.

**If a task nonetheless concludes a further protected edit is required, it
STOPs and reports rather than widening the diff.**

**Staging rule:** every `git add` below names exact files. Never `git add -A`.
Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml`
or `src/gaffer/web/static/`. (`.gitignore` itself is a repo-root file and is
staged in Task 16.)

**Commit trailers.** Every commit message in this plan ends with exactly:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

**Gate rule (CONVENTIONS §7):** implementers build the drivers and never run
them. Task 21 is the checklist with its results unfilled.

**Test runners.** Python: `.venv/bin/pytest` (there is no bare `python` on
PATH — use `.venv/bin/python`). Frontend: `npx vitest run`, never bare
`npm test`, which is watch mode and hangs an agent forever.

**Pins, measured at the branch point rather than assumed:**

| Pin | Value at `27f7933` | v12 W4 |
| --- | --- | --- |
| `len(JOB_KINDS)` | 12 | **12** — the collector is a CLI command and a launchd job, not a web job kind |
| `len(dataclasses.fields(Config))` | 48 | **48** — deliberately no new key; see below |
| `len(create_app().openapi()["paths"])` | 45 | **45** — the health line and the Field panel are additive fields on `Health` and `LeagueSimData` |

```bash
# how all three were measured; re-run before writing Task 19's pins
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# 45 12 48
```

**Why no `[core_insights] enabled` key**, though `understat` has one. Moving
`fields(Config)` 48 → 49 would break assertions inside `tests/test_v8f_degradation.py:301`,
`test_v8g_degradation.py:283`, `test_v9c_degradation.py:323`,
`test_v9d_degradation.py:421`, `test_v10_degradation.py:422`,
`test_v10b_degradation.py:266` — six **protected** files — to buy a kill
switch for a collector that `gaffer cups` has never had either. The collector
is off unless you run it or install its plist. Before Task 1, grep the two
counts that collide most often and **stop and report** if either has moved:

```bash
grep -rn "fields(Config)" tests/ | grep -v test_v12
# expect v8f:301, v8g:283, v9c:323, v9d:421, v10:422, v10b:266,
#        v10_config_providers:86 — all asserting 48
grep -rn "JOB_KINDS) ==" tests/ | grep -v test_v12
# expect v8b, v8c, v8d, v8e, v8f, v8g, v9a, v9c, v9d, v10, v10b, v11,
#        web_job_kinds_v8b — all asserting 12
```

---

## Appendix A — the archive, measured

Recorded here because §5.1 asks for the real layout and because every
degradation test in Task 6 is a transcription of one of these facts. Measured
2026-09-02 against `main` of `olbauday/FPL-Core-Insights` over the GitHub
contents and raw APIs.

**A2 — season folders and the two layouts.**

```
data/2024-2025/            matches/GW<n>/matches.csv
                           playermatchstats/GW<n>/playermatchstats.csv
                           players/…  playerstats/…  teams/teams.csv
data/2025-2026/            players.csv teams.csv playerstats.csv
                           gameweek_summaries.csv team_history.csv
                           supplemental/incidents_quarantined.csv
                           By Gameweek/GW<n>/{fixtures,matches,players,teams,
                               playerstats,playermatchstats,
                               player_gameweek_stats,shots,momentum,
                               xg_by_minute}.csv
                           By Tournament/<Tournament>/GW<n>/…
data/2026-2027/            same as 2025-2026, minus supplemental/
```

`By Tournament` folders present for 2026-2027: `Champions League`,
`Community Shield`, `Conference League`, `EFL Cup`, `Europa League`,
`Friendlies`, `Premier League`, `Uefa Super Cup`.

**A2b — `By Gameweek/GW<n>/fixtures.csv` already contains every tournament.**
GW1 2026-27 is `tournament == "prem"` throughout only because that week had no
cup ties; GW2 mixes `prem` and `efl-cup` in one file. **So the collector reads
`By Gameweek` only and never walks `By Tournament`** — one file per gameweek
instead of one per (tournament, gameweek), and no risk of double-counting a
club that appears in both. `matches.csv` and `fixtures.csv` in a `By Gameweek`
folder are byte-identical in size at GW1 and GW2 2026-27; the collector reads
`fixtures.csv` where present and falls back to `matches.csv` (which is the only
one of the two the 2024-2025 layout has).

**A2c — fixture columns that matter** (116 columns; the collector keeps
eight):

```
gameweek, kickoff_time, home_team, home_team_elo, home_score, away_score,
away_team, away_team_elo, finished, match_id, match_url, …, tournament
```

`home_team` / `away_team` are **stable FPL team codes as floats** and are
**blank for non-league clubs** — `26-27-efl-cup-plymouth-argyle/exeter-city-vs-coventry-city-2026-08-24`
has an empty `home_team` and `away_team == 9.0`. That is the same shape
`cups.py::_team_code` was written for. `gameweek` is an int in 2026-2027 and a
float (`"10.0"`) in 2025-2026 — coerce, never `astype(int)` on the raw column.

**A2d — future fixtures are published.** `By Gameweek/GW6/fixtures.csv` for
2026-27 (a week not yet played) carries real `kickoff_time` values with
`finished == False`. This is what makes §5.2's `density_pub_7d` a
prediction-time feature at all.

**A3 — `playermatchstats.csv` columns, by layout.**

2026-2027 / 2025-2026 (64 columns) begins:

```
player_id, match_id, minutes_played, goals, assists, total_shots, xg, xa,
shots_on_target, successful_dribbles, big_chances_missed,
touches_opposition_box, touches, accurate_passes, accurate_passes_percent,
chances_created, final_third_passes, accurate_crosses, …, tackles_won,
interceptions, recoveries, blocks, clearances, headed_clearances, …,
tackles, start_min, finish_min, team_goals_conceded, penalties_scored,
penalties_missed, top_speed, distance_covered, walking_distance,
running_distance, sprinting_distance, number_of_sprints,
defensive_contributions
```

2024-2025 (53 columns) has **no** `defensive_contributions`, no `corners`, no
`dispossessed`, no `saves_inside_box`, and none of the distance/sprint block.
It does have `tackles_won, interceptions, recoveries, blocks, clearances,
headed_clearances, accurate_crosses, touches_opposition_box,
final_third_passes, start_min, finish_min`.

**A3b — `players.csv` is the element map.** Both layouts:
`player_code,player_id,first_name,second_name,web_name,team_code,position`.
`player_code` is gaffer's `code`; `player_id` is the season element id.
`position` is a word (`"Midfielder"`), not FPL's `element_type`.

**A3c — `teams.csv` carries Elo, and 2026-27's is blank.**
2025-2026 row 1: `3,1,Arsenal,ARS,5,1305,1370,1340,1390,1270,1350,1,2064,Arsenal`
— the `elo` column is `2064`. 2026-2027 row 1:
`3,1,Arsenal,ARS,,4,5,0,0,0,0,1,,` — `elo` is empty, and so are
`home_team_elo`/`away_team_elo` on its GW1 fixtures. **The 2026-27 Elo table
is legitimately empty today.**

**A4 — no top-10k weekly score series exists.** `data/live/events.parquet`
columns are `['gw','deadline_time','is_current','is_next','finished',
'data_checked','most_captained','most_selected']`. `cli.py:112-131`'s
`build-history` writes `history/player_gw.parquet`,
`history/fixtures.parquet` and `history/match_odds.parquet` and nothing
event-level. `grep -rn "average_entry_score\|top_10k\|highest_score"
src/gaffer --include='*.py'` returns nothing outside prose. §5.3's
`p_top10k` therefore has no source.

---

## Task 1 — `core_insights.py`: enumerate the archive's paths from the git tree

**Why first.** Every later task needs to know which files exist for a season,
and A2 says the folder shape differs between 2024-2025 and the two later
seasons. One recursive git-trees call answers it for every season at once and
is layout-agnostic; a path template is not.

**Files**
- Create: `src/gaffer/data/core_insights.py`
- Create: `tests/test_core_insights.py`

### Step 1.1 — failing test

- [ ] Write `tests/test_core_insights.py`:

```python
"""FPL-Core-Insights: path discovery, parsing, and what the archive really is.

Every fixture in this file is a transcription of the live archive, measured
2026-09-02 and recorded in the W4 plan's Appendix A. Where a header looks
arbitrary it is because it is copied, not invented.
"""

from __future__ import annotations

import pandas as pd

from gaffer.data.core_insights import (SEASON_TABLES, ci_paths_from_tree,
                                       repo_season)


def _tree(paths: list[str]) -> dict:
    """The shape ``git/trees?recursive=1`` answers with."""
    return {"tree": [{"path": p, "type": "blob"} for p in paths]}


TREE = _tree([
    # 2024-2025: the flat, one-folder-per-table layout.
    "data/2024-2025/teams/teams.csv",
    "data/2024-2025/players/players.csv",
    "data/2024-2025/matches/GW1/matches.csv",
    "data/2024-2025/matches/GW2/matches.csv",
    "data/2024-2025/playermatchstats/GW1/playermatchstats.csv",
    "data/2024-2025/playermatchstats/GW2/playermatchstats.csv",
    # 2025-2026: the By Gameweek layout, with By Tournament beside it.
    "data/2025-2026/teams.csv",
    "data/2025-2026/players.csv",
    "data/2025-2026/By Gameweek/GW1/fixtures.csv",
    "data/2025-2026/By Gameweek/GW1/matches.csv",
    "data/2025-2026/By Gameweek/GW1/playermatchstats.csv",
    "data/2025-2026/By Gameweek/GW10/fixtures.csv",
    "data/2025-2026/By Gameweek/GW10/playermatchstats.csv",
    "data/2025-2026/By Tournament/EFL Cup/GW2/fixtures.csv",
    "data/2025-2026/supplemental/incidents_quarantined.csv",
    # A season nobody asked for.
    "data/2023-2024/players.csv",
])


def test_repo_season_is_the_archives_folder_naming():
    assert repo_season("2025-26") == "2025-2026"
    assert repo_season("2026-27") == "2026-2027"


def test_the_by_gameweek_layout_is_found():
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert found["2025-26"]["players"] == "data/2025-2026/players.csv"
    assert found["2025-26"]["teams"] == "data/2025-2026/teams.csv"
    assert found["2025-26"]["fixtures"] == {
        1: "data/2025-2026/By Gameweek/GW1/fixtures.csv",
        10: "data/2025-2026/By Gameweek/GW10/fixtures.csv"}
    assert found["2025-26"]["playermatchstats"] == {
        1: "data/2025-2026/By Gameweek/GW1/playermatchstats.csv",
        10: "data/2025-2026/By Gameweek/GW10/playermatchstats.csv"}


def test_by_tournament_is_never_walked():
    """A2b: By Gameweek already carries every tournament, so reading both
    would count an EFL Cup tie twice."""
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert all("By Tournament" not in p
               for p in found["2025-26"]["fixtures"].values())


def test_the_flat_2024_25_layout_is_found_by_the_same_call():
    found = ci_paths_from_tree(TREE, ["2024-25"])
    assert found["2024-25"]["teams"] == "data/2024-2025/teams/teams.csv"
    assert found["2024-25"]["players"] == "data/2024-2025/players/players.csv"
    # It has no fixtures.csv anywhere; matches.csv is the fallback (A2b).
    assert found["2024-25"]["fixtures"] == {
        1: "data/2024-2025/matches/GW1/matches.csv",
        2: "data/2024-2025/matches/GW2/matches.csv"}
    assert set(found["2024-25"]["playermatchstats"]) == {1, 2}


def test_fixtures_beats_matches_when_both_are_published():
    """They are the same bytes in the live archive; picking one keeps the
    reader deterministic rather than dependent on tree order."""
    found = ci_paths_from_tree(TREE, ["2025-26"])
    assert found["2025-26"]["fixtures"][1].endswith("/fixtures.csv")


def test_a_season_the_archive_does_not_publish_is_an_empty_bundle():
    found = ci_paths_from_tree(TREE, ["2021-22"])
    assert found["2021-22"] == {"players": None, "teams": None,
                                "fixtures": {}, "playermatchstats": {}}


def test_an_unreachable_tree_is_empty_bundles_not_an_exception():
    found = ci_paths_from_tree({}, ["2025-26", "2024-25"])
    assert set(found) == {"2025-26", "2024-25"}
    assert all(b["players"] is None and b["fixtures"] == {}
               for b in found.values())


def test_season_tables_is_the_contract_every_bundle_answers():
    assert SEASON_TABLES == ("players", "teams", "fixtures",
                             "playermatchstats")
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: collection error —
#   ModuleNotFoundError: No module named 'gaffer.data.core_insights'
```

### Step 1.2 — implementation

- [ ] Create `src/gaffer/data/core_insights.py`:

```python
"""FPL-Core-Insights: per-match detail, published cup fixtures, club Elo.

``cups.py`` (v8a) already reads this repository for one thing — the *dates*
league clubs played cup ties on — and deliberately leaves everything else on
the floor. This module takes the rest: per-player per-match defensive and
positional detail, the whole published fixture list including ties that have
not been played yet, and the Elo the archive carries per club and per match.

Three facts about the archive shape everything here, all measured 2026-09-02
and recorded in the W4 plan's Appendix A.

**There are two folder layouts, not one.** 2025-2026 and 2026-2027 publish
``data/<season>/By Gameweek/GW<n>/<table>.csv``; 2024-2025 publishes
``data/<season>/<table>/GW<n>/<table>.csv`` and hides its ``teams.csv`` a
folder deeper. So paths are **enumerated from the recursive git tree**, keyed
on basename and season folder, rather than built from a template. A template
would have to be edited every time the publisher reorganises; this does not.

**``By Gameweek`` already contains every tournament.** GW2 of 2026-27 holds
``prem`` and ``efl-cup`` rows in one file. Walking ``By Tournament`` as well
would count a cup tie twice, so it is never walked — which is also why this
module does not replace ``cups.py``: that one reads ``By Tournament``
``matches.csv`` for seasons this one may not cover, and the two parquets are
independent.

**There is no ClubElo file.** Elo is a column on ``teams.csv`` and a pair of
columns on every fixture row. ``elo.parquet`` is derived from both, and for a
season the publisher has not yet filled in — 2026-27, today — it is
legitimately empty. An empty Elo table is a fact about the archive, not a
failure of this collector, and the health line says which.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pandas as pd

from gaffer.data.cups import (CUPS_RAW_BASE, CUPS_TREE_URL, _cached_get,
                              _http, repo_season)

__all__ = ["CI_CACHE", "SEASON_TABLES", "ci_paths_from_tree", "repo_season"]

CI_CACHE = Path("data/raw/core_insights")
"""Where fetched CSVs are cached. Same contract as ``cups.CUPS_CACHE``: a file
on disk is never re-fetched, so a killed run costs only what it had not
reached. A *finished* gameweek's files never change; an unfinished one's do,
which is why :func:`download_core_insights` takes ``refresh_gws``."""

SEASON_TABLES = ("players", "teams", "fixtures", "playermatchstats")
"""The keys every bundle answers, present or absent. ``players`` and ``teams``
are one path or ``None``; ``fixtures`` and ``playermatchstats`` are
``{gw: path}`` and may be empty."""

_GW_RE = re.compile(r"^GW(\d+)$")


def _gw_of(part: str) -> int | None:
    """``"GW10"`` -> ``10``; anything else -> ``None``."""
    hit = _GW_RE.match(part)
    return int(hit.group(1)) if hit else None


def _empty_bundle() -> dict:
    return {"players": None, "teams": None, "fixtures": {},
            "playermatchstats": {}}


def ci_paths_from_tree(tree: dict, seasons: list[str]) -> dict[str, dict]:
    """``{fpl season: bundle}`` from one recursive git-trees payload.

    Layout-agnostic by construction: a path is claimed by what its *basename*
    is and which season folder it sits under, never by how deep it is. That is
    what lets 2024-2025's ``playermatchstats/GW1/playermatchstats.csv`` and
    2025-2026's ``By Gameweek/GW1/playermatchstats.csv`` land in the same slot
    with no branch.

    ``By Tournament`` is skipped outright (see the module docstring), and a
    gameweek that publishes both ``fixtures.csv`` and ``matches.csv`` resolves
    to ``fixtures.csv`` — they are the same bytes in the live archive, and
    picking one deterministically beats depending on the order the tree
    happened to list them in.

    An empty or unreachable tree yields one empty bundle per requested season
    rather than raising: a collector that dies because GitHub is down is a
    collector that gets uninstalled.
    """
    folders = {repo_season(s): s for s in seasons}
    out: dict[str, dict] = {s: _empty_bundle() for s in seasons}
    # ``matches.csv`` is only ever taken where no ``fixtures.csv`` shares the
    # folder, so the two passes cannot race: fixtures are claimed first.
    fallbacks: list[tuple[str, int, str]] = []
    for node in (tree or {}).get("tree", []):
        path = str(node.get("path") or "")
        parts = path.split("/")
        if len(parts) < 3 or parts[0] != "data":
            continue
        season = folders.get(parts[1])
        if season is None or "By Tournament" in parts:
            continue
        name = parts[-1]
        bundle = out[season]
        if name == "players.csv" and bundle["players"] is None:
            bundle["players"] = path
            continue
        if name == "teams.csv" and bundle["teams"] is None:
            bundle["teams"] = path
            continue
        gw = _gw_of(parts[-2]) if len(parts) >= 3 else None
        if gw is None:
            continue
        if name == "playermatchstats.csv":
            bundle["playermatchstats"][gw] = path
        elif name == "fixtures.csv":
            bundle["fixtures"][gw] = path
        elif name == "matches.csv":
            fallbacks.append((season, gw, path))
    for season, gw, path in fallbacks:
        out[season]["fixtures"].setdefault(gw, path)
    return out


def fetch_tree(client: httpx.Client | None = None) -> dict:
    """The repository's recursive git tree, or ``{}`` when it is unreachable.

    One request answers what would otherwise be a listing per season per
    table. ``{}`` is the documented degradation and every caller treats it as
    "the archive published nothing", never as an error.
    """
    http = _http(client)
    try:
        return http.get(CUPS_TREE_URL).json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"core-insights: tree listing unavailable ({exc})")
        return {}


def fetch_csv(path: str, http: httpx.Client,
              cache_dir: Path | str = CI_CACHE) -> str | None:
    """One archive path -> its text, cached forever under ``cache_dir``.

    ``None`` with a printed line on a 404 or a dead connection: a run spanning
    three seasons and a hundred gameweeks must not die on one missing folder.
    """
    return _cached_get(http, f"{CUPS_RAW_BASE}/{path}", Path(cache_dir) / path)
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: 8 passed
```

- [ ] Commit:

```bash
git add src/gaffer/data/core_insights.py tests/test_core_insights.py
git commit -m "$(cat <<'EOF'
feat(w4): enumerate FPL-Core-Insights from the tree, not from a template

The archive publishes two folder layouts — 2024-2025 puts each table in its
own directory, 2025-2026 onward use "By Gameweek" — so paths are claimed by
basename and season folder rather than built. By Tournament is never walked:
By Gameweek already carries every tournament, and reading both would count an
EFL Cup tie twice.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the three parsers, and what schema drift does

**Why.** §5.1's degradation list names "CSV schema drift (unknown column added
/ expected column missing)". In this archive that is not hypothetical: A3 says
`defensive_contributions` exists in two of the three seasons and not the
third, and A2c says `gameweek` is an int in one season and a float in
another. The parsers are written to that reality — an unknown column is
ignored, a missing *optional* column becomes an all-NaN column with a printed
notice, and a missing *key* column drops the file with a printed notice.

**Files**
- Modify: `src/gaffer/data/core_insights.py` (append)
- Modify: `tests/test_core_insights.py` (append)

### Step 2.1 — failing test

- [ ] Append to `tests/test_core_insights.py`:

```python
# --- Task 2: the parsers -------------------------------------------------

from gaffer.data.core_insights import (CI_ELO_COLS, CI_FIXTURE_COLS,
                                       CI_PLAYER_COLS, PMS_KEY_COLS,
                                       PMS_STAT_COLS, elo_rows, fixture_rows,
                                       player_code_map, player_match_rows)

PLAYERS_CSV = (
    "player_code,player_id,first_name,second_name,web_name,team_code,position\n"
    "208706,452,Bruno,Guimaraes,Bruno G.,3,Midfielder\n"
    "232413,266,Eberechi,Eze,Eze,3,Midfielder\n"
    "1,7,Nobody,Nowhere,Nobody,3,Defender\n")

FIXTURES_CSV = (
    "gameweek,kickoff_time,home_team,home_team_elo,home_score,away_score,"
    "away_team,away_team_elo,finished,match_id,tournament\n"
    "2,2026-08-30T13:00:00,2.0,1801.5,1,1,94.0,1750.25,True,"
    "26-27-prem-leeds-united-vs-brentford,prem\n"
    "2,2026-08-25T18:45:00,,,0,3,9.0,,True,"
    "26-27-efl-cup-exeter-city-vs-coventry-city-2026-08-24,efl-cup\n"
    "6,2026-10-10T14:00:00,8.0,,,,91.0,,False,"
    "26-27-prem-chelsea-vs-afc-bournemouth,prem\n")

PMS_CSV = (
    "player_id,match_id,minutes_played,accurate_crosses,"
    "touches_opposition_box,final_third_passes,tackles_won,interceptions,"
    "blocks,clearances,recoveries,start_min,finish_min,"
    "defensive_contributions\n"
    "452,26-27-prem-leeds-united-vs-brentford,90,2,4,11,3,1,0,2,7,0,90,6\n"
    "266,26-27-prem-leeds-united-vs-brentford,63,0,1,4,1,0,1,0,3,0,63,2\n"
    "999,26-27-prem-leeds-united-vs-brentford,12,0,0,0,0,0,0,0,0,78,90,0\n")

PMS_CSV_2024 = (  # A3: no defensive_contributions in the 2024-2025 layout
    "player_id,match_id,minutes_played,accurate_crosses,"
    "touches_opposition_box,final_third_passes,tackles_won,interceptions,"
    "blocks,clearances,recoveries,start_min,finish_min\n"
    "452,24-25-prem-a-vs-b,90,1,3,9,2,2,1,4,6,0,90\n")


def test_player_code_map_reads_the_archives_own_element_map():
    assert player_code_map(PLAYERS_CSV) == {452: 208706, 266: 232413, 7: 1}


def test_player_code_map_of_a_headerless_blob_is_empty_not_a_crash():
    assert player_code_map("") == {}
    assert player_code_map("nothing,useful\n1,2\n") == {}


def test_player_match_rows_join_to_code_and_carry_the_season():
    out = player_match_rows(PMS_CSV, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert list(out.columns) == CI_PLAYER_COLS
    # element 999 is in no map and drops rather than landing on a NaN key.
    assert set(out["code"]) == {208706, 232413}
    assert len(out) == 2
    assert set(out["season"]) == {"2026-27"}
    assert set(out["season_idx"]) == {3}
    assert set(out["gw"]) == {2}
    row = out[out["code"] == 208706].iloc[0]
    assert row["minutes_played"] == 90.0
    assert row["accurate_crosses"] == 2.0
    assert row["defensive_contributions"] == 6.0


def test_a_season_missing_defensive_contributions_gets_an_all_nan_column():
    """A3: the 2024-2025 layout does not publish it. The column still exists,
    so one parquet schema serves every season."""
    out = player_match_rows(PMS_CSV_2024, "2024-25", 2, 1,
                            player_code_map(PLAYERS_CSV))
    assert "defensive_contributions" in out.columns
    assert out["defensive_contributions"].isna().all()
    assert out["accurate_crosses"].iloc[0] == 1.0


def test_an_unknown_column_is_ignored_rather_than_carried():
    drifted = PMS_CSV.replace("player_id,", "brand_new_metric,player_id,") \
        .replace("452,26-27", "1.5,452,26-27") \
        .replace("266,26-27", "1.5,266,26-27") \
        .replace("999,26-27", "1.5,999,26-27")
    out = player_match_rows(drifted, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert "brand_new_metric" not in out.columns
    assert list(out.columns) == CI_PLAYER_COLS
    assert len(out) == 2


def test_a_missing_key_column_drops_the_file_rather_than_guessing():
    headless = PMS_CSV.replace("player_id,match_id,", "match_id,")
    out = player_match_rows(headless, "2026-27", 3, 2,
                            player_code_map(PLAYERS_CSV))
    assert out.empty
    assert list(out.columns) == CI_PLAYER_COLS


def test_pms_column_contracts_are_disjoint_and_complete():
    assert set(PMS_KEY_COLS).isdisjoint(PMS_STAT_COLS)
    assert CI_PLAYER_COLS[:4] == ["season", "season_idx", "gw", "code"]


def test_fixture_rows_emit_one_row_per_league_club_per_match():
    out = fixture_rows(FIXTURES_CSV, "2026-27", 3, 2)
    assert list(out.columns) == CI_FIXTURE_COLS
    # 3 matches: one with two league clubs, one with one, one with two = 5.
    assert len(out) == 5
    leeds = out[(out["team_code"] == 2) & (out["tournament"] == "prem")]
    assert bool(leeds["is_home"].iloc[0]) is True
    assert leeds["opponent_code"].iloc[0] == 94
    cup = out[out["tournament"] == "efl-cup"]
    assert len(cup) == 1 and cup["team_code"].iloc[0] == 9
    # The non-league side is blank in the file and contributes no row and no
    # opponent code.
    assert pd.isna(cup["opponent_code"].iloc[0])


def test_unplayed_fixtures_are_kept_because_that_is_the_whole_point():
    """A2d: density_pub_7d is a prediction-time feature only because the
    archive publishes fixtures before they are played."""
    out = fixture_rows(FIXTURES_CSV, "2026-27", 3, 6)
    future = out[out["gw"] == 6]
    assert len(future) == 2
    assert not future["finished"].any()
    assert future["kickoff"].notna().all()


def test_a_float_gameweek_column_is_coerced_not_astyped():
    """A2c: 2025-2026 writes "10.0" where 2026-2027 writes "10"."""
    floaty = FIXTURES_CSV.replace("\n2,2026-08-30", "\n2.0,2026-08-30")
    out = fixture_rows(floaty, "2025-26", 2, 2)
    assert set(out[out["tournament"] == "prem"]["gw"]) == {2}


def test_a_fixture_file_with_no_kickoff_column_is_dropped():
    out = fixture_rows(FIXTURES_CSV.replace("kickoff_time", "when"),
                       "2026-27", 3, 2)
    assert out.empty
    assert list(out.columns) == CI_FIXTURE_COLS


def test_elo_rows_come_off_the_fixture_file_per_club():
    out = elo_rows(FIXTURES_CSV, "2026-27", 3, 2)
    assert list(out.columns) == CI_ELO_COLS
    assert set(zip(out["team_code"], out["elo"])) == {(2, 1801.5),
                                                      (94, 1750.25)}


def test_a_season_whose_elo_is_blank_yields_no_elo_rows():
    """A3c: 2026-27's archive carries no Elo yet. That is a fact, not a bug."""
    blank = FIXTURES_CSV.replace("1801.5", "").replace("1750.25", "")
    out = elo_rows(blank, "2026-27", 3, 2)
    assert out.empty
    assert list(out.columns) == CI_ELO_COLS
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: collection error —
#   ImportError: cannot import name 'CI_ELO_COLS' from 'gaffer.data.core_insights'
```

### Step 2.2 — implementation

- [ ] Append to `src/gaffer/data/core_insights.py`:

```python
# --- parsers -------------------------------------------------------------

PMS_KEY_COLS = ("player_id", "match_id")
"""Without both of these a player-match row cannot be placed. A file missing
either is dropped whole, because the alternative is inventing a key."""

PMS_STAT_COLS = ("minutes_played", "accurate_crosses",
                 "touches_opposition_box", "final_third_passes",
                 "tackles_won", "interceptions", "blocks", "clearances",
                 "recoveries", "start_min", "finish_min",
                 "defensive_contributions")
"""The columns kept out of the 53-to-64 the archive publishes.

Deliberately a short list. Everything here is either an input to §5.2's
wing-back rule (crosses, box touches, final-third passes, the two minute
bounds) or a component of the CBIT/defcon family (tackles, interceptions,
blocks, clearances, recoveries, and the published ``defensive_contributions``
where the season has it). Shot maps, sprint distances and duel percentages are
left on the floor for the same reason ``cups.py`` leaves cup goals there: they
are not what this collector exists to answer, and a column nobody reads is a
schema nobody can change.

``defensive_contributions`` is absent from the 2024-2025 layout (A3) and is
carried as an all-NaN column there, so one parquet schema serves every season
and a model sees a missing value rather than a missing column."""

CI_PLAYER_COLS = ["season", "season_idx", "gw", "code", "player_id",
                  "match_id"] + list(PMS_STAT_COLS)

CI_FIXTURE_COLS = ["season", "season_idx", "gw", "tournament", "match_id",
                   "kickoff", "team_code", "opponent_code", "is_home",
                   "finished"]

CI_ELO_COLS = ["season", "season_idx", "gw", "kickoff", "team_code", "elo"]


def _read_csv(text: str) -> pd.DataFrame:
    """One CSV blob -> a frame, or an empty one. Never raises.

    A truncated or non-CSV body is a fetch that went wrong, and one bad file
    must cost one file.
    """
    import io

    try:
        return pd.read_csv(io.StringIO(text or ""))
    except Exception as exc:  # noqa: BLE001 — one bad file is not the run
        print(f"core-insights: unreadable CSV ({exc})")
        return pd.DataFrame()


def player_code_map(players_csv: str) -> dict[int, int]:
    """``{season element id: stable FPL code}`` from the archive's own file.

    The archive ships the map we would otherwise have to rebuild by name:
    ``players.csv`` is ``player_code,player_id,…`` and ``player_code`` is
    exactly gaffer's ``code``. That is why nothing in this module does name
    matching, and why the element-id season guard is free — the map is read
    per season folder and never spans two.
    """
    df = _read_csv(players_csv)
    if df.empty or not {"player_id", "player_code"}.issubset(df.columns):
        return {}
    ids = pd.to_numeric(df["player_id"], errors="coerce")
    codes = pd.to_numeric(df["player_code"], errors="coerce")
    return {int(i): int(c) for i, c in zip(ids, codes)
            if pd.notna(i) and pd.notna(c)}


def player_match_rows(pms_csv: str, season: str, season_idx: int, gw: int,
                      codes: dict[int, int]) -> pd.DataFrame:
    """One ``playermatchstats.csv`` -> ``CI_PLAYER_COLS``.

    Three drift behaviours, one per kind of drift, and they are different on
    purpose:

    * an **unknown column** is ignored — the archive adds metrics, and a
      collector that fell over on a new one would break every time the
      publisher improved it;
    * a **missing optional column** becomes all-NaN with a printed line, so
      the parquet schema is constant across seasons and a model sees a missing
      value instead of a missing column (A3's ``defensive_contributions``);
    * a **missing key column** drops the file with a printed line, because a
      row that cannot be keyed cannot be joined and a guessed key is worse
      than no row.

    An element the season's map does not know drops rather than carrying a
    null ``code``: pandas merges null keys as equal, and one NaN-keyed row is
    how a whole club's stats end up on one player.
    """
    empty = pd.DataFrame(columns=CI_PLAYER_COLS)
    df = _read_csv(pms_csv)
    if df.empty:
        return empty
    missing_keys = [c for c in PMS_KEY_COLS if c not in df.columns]
    if missing_keys:
        print(f"core-insights: {season} gw{gw} playermatchstats has no "
              f"{', '.join(missing_keys)} — file dropped")
        return empty
    out = pd.DataFrame({
        "season": str(season), "season_idx": int(season_idx), "gw": int(gw),
        "player_id": pd.to_numeric(df["player_id"], errors="coerce"),
        "match_id": df["match_id"].astype("string")})
    absent = []
    for col in PMS_STAT_COLS:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            out[col] = float("nan")
            absent.append(col)
    if absent:
        print(f"core-insights: {season} gw{gw} playermatchstats does not "
              f"publish {', '.join(absent)} — carried as null")
    out["code"] = out["player_id"].map(
        lambda v: codes.get(int(v)) if pd.notna(v) else None)
    out = out[out["code"].notna() & out["player_id"].notna()]
    if out.empty:
        return empty
    out["code"] = out["code"].astype("int64")
    out["player_id"] = out["player_id"].astype("int64")
    return out[CI_PLAYER_COLS].reset_index(drop=True)


def _fixture_frame(fixtures_csv: str) -> pd.DataFrame | None:
    """Shared preamble of :func:`fixture_rows` and :func:`elo_rows`.

    ``None`` when the file cannot be read as a fixture list at all, which both
    callers turn into their own empty frame.
    """
    df = _read_csv(fixtures_csv)
    if df.empty or "kickoff_time" not in df.columns:
        return None
    if "home_team" not in df.columns or "away_team" not in df.columns:
        return None
    return df


def fixture_rows(fixtures_csv: str, season: str, season_idx: int,
                 gw: int) -> pd.DataFrame:
    """One ``fixtures.csv`` -> one row per *league* club per match.

    Both sides are emitted independently, ``cups.py::cup_match_rows``' rule
    and for its reason: a tie between a Premier League club and an EFL one is
    a fixture for exactly one of them, and the file writes a blank code for
    the other.

    **Unplayed matches are kept.** That is the whole difference between this
    table and the withdrawn cup-archive congestion arm: the archive publishes
    a fixture's kickoff time weeks before it is played (A2d), so a count of
    fixtures in the seven days before a deadline is available *at prediction
    time*. A row with no kickoff time has not been scheduled and carries
    nothing to count, so it drops.
    """
    empty = pd.DataFrame(columns=CI_FIXTURE_COLS)
    df = _fixture_frame(fixtures_csv)
    if df is None:
        print(f"core-insights: {season} gw{gw} fixtures has no kickoff_time "
              f"or no team columns — file dropped")
        return empty
    kickoff = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    tournament = (df["tournament"].astype("string")
                  if "tournament" in df.columns
                  else pd.Series("", index=df.index, dtype="string"))
    match_id = (df["match_id"].astype("string") if "match_id" in df.columns
                else pd.Series("", index=df.index, dtype="string"))
    finished = (df["finished"].astype("string").str.lower().eq("true")
                if "finished" in df.columns
                else pd.Series(False, index=df.index))
    home = pd.to_numeric(df["home_team"], errors="coerce")
    away = pd.to_numeric(df["away_team"], errors="coerce")
    parts = []
    for side, other, is_home in ((home, away, True), (away, home, False)):
        parts.append(pd.DataFrame({
            "season": str(season), "season_idx": int(season_idx),
            "gw": int(gw), "tournament": tournament.values,
            "match_id": match_id.values, "kickoff": kickoff.values,
            "team_code": side.values, "opponent_code": other.values,
            "is_home": bool(is_home), "finished": finished.values}))
    out = pd.concat(parts, ignore_index=True)
    out = out[out["team_code"].notna() & out["kickoff"].notna()]
    if out.empty:
        return empty
    out["team_code"] = out["team_code"].astype("int64")
    return out[CI_FIXTURE_COLS].reset_index(drop=True)


def elo_rows(fixtures_csv: str, season: str, season_idx: int,
             gw: int) -> pd.DataFrame:
    """One ``fixtures.csv`` -> one Elo reading per club per match.

    The archive has no ClubElo file (see the module docstring): the readings
    live on the fixture rows as ``home_team_elo`` / ``away_team_elo``. A row
    whose Elo is blank yields nothing, which is why 2026-27 comes back empty
    today — the publisher has not filled the column in for the new season.
    Empty is the honest answer, and the health line says so rather than
    borrowing last season's number.
    """
    empty = pd.DataFrame(columns=CI_ELO_COLS)
    df = _fixture_frame(fixtures_csv)
    if df is None:
        return empty
    if not {"home_team_elo", "away_team_elo"}.issubset(df.columns):
        return empty
    kickoff = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    parts = []
    for team_col, elo_col in (("home_team", "home_team_elo"),
                              ("away_team", "away_team_elo")):
        parts.append(pd.DataFrame({
            "season": str(season), "season_idx": int(season_idx),
            "gw": int(gw), "kickoff": kickoff.values,
            "team_code": pd.to_numeric(df[team_col], errors="coerce").values,
            "elo": pd.to_numeric(df[elo_col], errors="coerce").values}))
    out = pd.concat(parts, ignore_index=True)
    out = out[out["team_code"].notna() & out["elo"].notna()
              & out["kickoff"].notna()]
    if out.empty:
        return empty
    out["team_code"] = out["team_code"].astype("int64")
    return out[CI_ELO_COLS].reset_index(drop=True)
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: 21 passed
```

- [ ] Commit:

```bash
git add src/gaffer/data/core_insights.py tests/test_core_insights.py
git commit -m "$(cat <<'EOF'
feat(w4): parse the archive's player-match, fixture and Elo tables

Three drift behaviours, one per kind: an unknown column is ignored, a missing
optional column is carried as null so one parquet schema serves every season,
and a missing key column drops the file rather than inventing a key. There is
no ClubElo file — Elo is a pair of columns on every fixture row, and 2026-27's
is blank, which is a fact about the archive rather than a failure here.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — `download_core_insights` and the season-guarded readers

**Files**
- Modify: `src/gaffer/data/core_insights.py` (append)
- Modify: `tests/test_core_insights.py` (append)

### Step 3.1 — failing test

- [ ] Append to `tests/test_core_insights.py`:

```python
# --- Task 3: the collector and its readers -------------------------------

import pytest

from gaffer.data import store
from gaffer.data.core_insights import (ci_path, download_core_insights,
                                       load_core_insights, season_table_stats)


class _FakeHTTP:
    """An httpx.Client stand-in that serves a path -> text dict.

    Anything it is not given 404s the way the real archive does, which is what
    ``_cached_get`` turns into a printed skip.
    """

    def __init__(self, files: dict[str, str]):
        self.files = dict(files)
        self.asked: list[str] = []

    def get(self, url, **_kw):
        self.asked.append(url)
        path = url.split("/main/", 1)[-1]
        if path not in self.files:
            raise httpx.HTTPError(f"404 {path}")
        return _Resp(self.files[path])


class _Resp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        import json as _json
        return _json.loads(self.text)


import httpx  # noqa: E402 — imported after _FakeHTTP for readability


ARCHIVE = {
    "data/2026-2027/players.csv": PLAYERS_CSV,
    "data/2026-2027/teams.csv": "code,id,name,elo\n2,1,Leeds,\n",
    "data/2026-2027/By Gameweek/GW2/fixtures.csv": FIXTURES_CSV,
    "data/2026-2027/By Gameweek/GW2/playermatchstats.csv": PMS_CSV,
}

ARCHIVE_TREE = _tree(sorted(ARCHIVE))


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_collector_writes_three_parquets_per_season(clone):
    http = _FakeHTTP(ARCHIVE)
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 tree=ARCHIVE_TREE, client=http)
    assert out["2026-27"] == {"players": 2, "fixtures": 5, "elo": 2}
    for table in ("players", "fixtures", "elo"):
        assert store.exists(ci_path("2026-27", table))


def test_the_written_players_table_is_season_guarded_by_construction(clone):
    http = _FakeHTTP(ARCHIVE)
    download_core_insights(["2026-27"], {"2026-27": 3}, tree=ARCHIVE_TREE,
                           client=http)
    frame = load_core_insights("2026-27", "players")
    assert set(frame["season"]) == {"2026-27"}
    assert ci_path("2026-27", "players") == \
        "core_insights/2026-27/players.parquet"


def test_a_reader_for_a_season_never_collected_is_an_empty_typed_frame(clone):
    frame = load_core_insights("2019-20", "players")
    assert frame.empty
    assert list(frame.columns) == CI_PLAYER_COLS


def test_an_unreachable_archive_writes_nothing_and_does_not_raise(clone):
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree={},
                                 client=_FakeHTTP({}))
    assert out["2026-27"] == {"players": 0, "fixtures": 0, "elo": 0}
    assert not store.exists(ci_path("2026-27", "players"))


def test_a_season_the_archive_publishes_empty_writes_empty_tables(clone):
    tree = _tree(["data/2026-2027/players.csv", "data/2026-2027/teams.csv"])
    out = download_core_insights(
        ["2026-27"], {"2026-27": 3}, tree=tree,
        client=_FakeHTTP({"data/2026-2027/players.csv": PLAYERS_CSV,
                          "data/2026-2027/teams.csv": "code,id\n2,1\n"}))
    assert out["2026-27"] == {"players": 0, "fixtures": 0, "elo": 0}
    # Written, not skipped: "we looked and there was nothing" is a fact worth
    # banking, and the health line renders 0 rows rather than "never run".
    assert store.exists(ci_path("2026-27", "players"))
    assert load_core_insights("2026-27", "players").empty


def test_a_season_with_no_element_map_collects_no_player_rows(clone):
    """Without players.csv nothing can be joined to a code, so the player
    table is empty while fixtures and elo are unaffected."""
    files = {k: v for k, v in ARCHIVE.items()
             if k != "data/2026-2027/players.csv"}
    tree = _tree(sorted(files))
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree=tree,
                                 client=_FakeHTTP(files))
    assert out["2026-27"]["players"] == 0
    assert out["2026-27"]["fixtures"] == 5


def test_one_bad_gameweek_costs_one_gameweek(clone):
    files = dict(ARCHIVE)
    files["data/2026-2027/By Gameweek/GW3/playermatchstats.csv"] = "gibberish"
    tree = _tree(sorted(files))
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree=tree,
                                 client=_FakeHTTP(files))
    assert out["2026-27"]["players"] == 2


def test_season_table_stats_is_what_the_health_line_renders(clone):
    http = _FakeHTTP(ARCHIVE)
    download_core_insights(["2026-27"], {"2026-27": 3}, tree=ARCHIVE_TREE,
                           client=http)
    stats = season_table_stats("2026-27")
    assert stats["players"]["rows"] == 2
    assert stats["fixtures"]["rows"] == 5
    assert stats["fixtures"]["latest"] == "2026-10-10"
    assert stats["elo"]["rows"] == 2


def test_season_table_stats_on_a_cold_clone_says_never(clone):
    stats = season_table_stats("2026-27")
    assert stats == {"players": {"rows": 0, "latest": None},
                     "fixtures": {"rows": 0, "latest": None},
                     "elo": {"rows": 0, "latest": None}}
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: collection error —
#   ImportError: cannot import name 'ci_path' from 'gaffer.data.core_insights'
```

### Step 3.2 — implementation

- [ ] Append to `src/gaffer/data/core_insights.py`:

```python
# --- the collector and its readers ---------------------------------------

CI_TABLES = {"players": CI_PLAYER_COLS, "fixtures": CI_FIXTURE_COLS,
             "elo": CI_ELO_COLS}
"""``table -> its column contract``. The three names spec §5.1 asks for."""


def ci_path(season: str, table: str) -> str:
    """``store``-relative path of one season's one table.

    Season-partitioned rather than one growing file, and that partition *is*
    the season guard: an element id means nothing without a season, and a
    reader that has to remember to filter is a reader that eventually forgets.
    ``load_core_insights`` takes the season as its first positional argument
    for the same reason.
    """
    return f"core_insights/{season}/{table}.parquet"


def load_core_insights(season: str, table: str) -> pd.DataFrame:
    """One season's one table, or an empty frame with the right columns.

    Never raises and never falls back to another season. "This machine has not
    collected 2024-25" and "2024-25 had no rows" are both an empty frame here,
    and the difference is recoverable from :func:`season_table_stats`, which
    is what the health line reads.
    """
    cols = CI_TABLES.get(table)
    if cols is None:
        raise ValueError(f"unknown core-insights table {table!r}")
    empty = pd.DataFrame(columns=cols)
    rel = ci_path(season, table)
    if not store.exists(rel):
        return empty
    try:
        frame = store.load(rel)
    except Exception as exc:  # noqa: BLE001 — a torn parquet is a missing one
        print(f"core-insights: {rel} unreadable ({exc})")
        return empty
    if "season" not in frame.columns:
        return empty
    # Belt and braces on top of the directory partition: a hand-copied file
    # from another machine must not smuggle another season's element ids in.
    return frame[frame["season"].astype(str) == str(season)]


def season_table_stats(season: str) -> dict[str, dict]:
    """``{table: {"rows": n, "latest": "YYYY-MM-DD" | None}}`` for the health
    line.

    ``rows`` of 0 with ``latest`` of ``None`` is what a machine that has never
    run the collector shows, and it is also what a season the archive publishes
    empty shows. The health line renders "never collected" for the first only
    because it can see the file is absent; both are honest, neither is a zero
    dressed as a measurement.
    """
    out: dict[str, dict] = {}
    for table in CI_TABLES:
        frame = load_core_insights(season, table)
        latest = None
        if not frame.empty:
            if "kickoff" in frame.columns:
                stamps = pd.to_datetime(frame["kickoff"], errors="coerce",
                                        utc=True).dropna()
                if not stamps.empty:
                    latest = str(stamps.max().date())
            elif "gw" in frame.columns:
                latest = f"GW{int(pd.to_numeric(frame['gw']).max())}"
        out[table] = {"rows": int(len(frame)), "latest": latest}
    return out


def download_core_insights(seasons: list[str],
                           season_indexes: dict[str, int],
                           *, tree: dict | None = None,
                           client: httpx.Client | None = None,
                           cache_dir: Path | str = CI_CACHE
                           ) -> dict[str, dict[str, int]]:
    """Collect every requested season -> ``data/core_insights/<season>/``.

    One tree listing, then one cached GET per file. Returns
    ``{season: {table: rows written}}``, which is what the CLI prints.

    A season the archive does not publish writes three empty tables rather
    than nothing at all: "we looked and there was nothing" and "we never
    looked" are different states, the health line distinguishes them by the
    file's existence, and only the first is a state a re-run will not change.

    An unreachable archive writes *nothing* — no empty tables, no truncation
    of what a previous run collected. A network blip must not delete a
    season's data, which is why the write is skipped entirely when the tree
    came back empty.
    """
    http = _http(client)
    tree = fetch_tree(http) if tree is None else tree
    bundles = ci_paths_from_tree(tree, seasons)
    out: dict[str, dict[str, int]] = {}
    for season in seasons:
        bundle = bundles[season]
        idx = int(season_indexes.get(season, 0))
        reachable = bool(bundle["players"] or bundle["teams"]
                         or bundle["fixtures"] or bundle["playermatchstats"])
        if not reachable:
            print(f"core-insights: {season} — the archive published nothing "
                  f"reachable; leaving any previous collection alone")
            out[season] = {t: 0 for t in CI_TABLES}
            continue
        codes: dict[int, int] = {}
        if bundle["players"]:
            text = fetch_csv(bundle["players"], http, cache_dir)
            codes = player_code_map(text or "")
        if not codes:
            print(f"core-insights: {season} has no element map — player rows "
                  f"cannot be joined to a code and are skipped")
        players, fixtures, elos = [], [], []
        for gw in sorted(bundle["playermatchstats"]):
            if not codes:
                break
            text = fetch_csv(bundle["playermatchstats"][gw], http, cache_dir)
            if not text:
                continue
            players.append(player_match_rows(text, season, idx, gw, codes))
        for gw in sorted(bundle["fixtures"]):
            text = fetch_csv(bundle["fixtures"][gw], http, cache_dir)
            if not text:
                continue
            fixtures.append(fixture_rows(text, season, idx, gw))
            elos.append(elo_rows(text, season, idx, gw))
        written: dict[str, int] = {}
        for table, frames in (("players", players), ("fixtures", fixtures),
                              ("elo", elos)):
            cols = CI_TABLES[table]
            kept = [f for f in frames if not f.empty]
            frame = (pd.concat(kept, ignore_index=True)[cols] if kept
                     else pd.DataFrame(columns=cols))
            store.save(frame, ci_path(season, table))
            written[table] = int(len(frame))
        print(f"core-insights: {season} — "
              + ", ".join(f"{n} {t}" for t, n in written.items()))
        out[season] = written
    return out
```

- [ ] Add the `store` import at the top of the module, beside the others:

```python
from gaffer.data import store
```

placed directly under `from gaffer.data.cups import (...)`.

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: 30 passed
```

- [ ] Commit:

```bash
git add src/gaffer/data/core_insights.py tests/test_core_insights.py
git commit -m "$(cat <<'EOF'
feat(w4): collect FPL-Core-Insights into season-partitioned parquets

data/core_insights/<season>/{players,fixtures,elo}.parquet. The partition is
the season guard: element ids mean nothing without a season, and a reader that
has to remember to filter eventually forgets. A season the archive publishes
empty writes empty tables; an unreachable archive writes nothing at all, so a
network blip cannot delete what a previous run collected.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — `gaffer core-insights`, its plist, and the automation table

**Files**
- Modify: `src/gaffer/cli.py` (insert a command after `cups`, which ends at
  `:151`)
- Create: `scripts/com.gaffer.core-insights.plist`
- Modify: `scripts/install_automation.sh:5` (the `for name in …` list) and
  `:13` (the echoed summary)
- Modify: `README.md` (automation table), `docs/GUIDE.md` (automation table)

### Step 4.1 — failing test

- [ ] Append to `tests/test_core_insights.py`:

```python
# --- Task 4: the command and its plist -----------------------------------

from pathlib import Path as _Path


def test_the_cli_exposes_core_insights():
    from typer.main import get_command

    from gaffer.cli import app

    assert "core-insights" in get_command(app).commands


def test_the_plist_runs_the_command_twice_a_day():
    text = _Path("scripts/com.gaffer.core-insights.plist").read_text()
    assert "com.gaffer.core-insights" in text
    assert "uv run gaffer core-insights" in text
    assert text.count("<key>Hour</key><integer>6</integer>") == 1
    assert text.count("<key>Hour</key><integer>18</integer>") == 1
    assert text.count("<key>Minute</key><integer>30</integer>") == 2


def test_the_installer_installs_it():
    text = _Path("scripts/install_automation.sh").read_text()
    assert "core-insights" in text
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_core_insights.py -q -k "cli or plist or installer"
# expected: 3 failed —
#   AssertionError: assert 'core-insights' in {...}
#   FileNotFoundError: scripts/com.gaffer.core-insights.plist
#   AssertionError: assert 'core-insights' in '#!/bin/zsh...'
```

### Step 4.2 — implementation

- [ ] Insert into `src/gaffer/cli.py` immediately after the `cups` command
  (after line 151, before `@app.command()` / `def understat()`):

```python
@app.command("core-insights")
def core_insights_cmd():
    """Ingest FPL-Core-Insights per-match, fixture and Elo tables.

    The launchd job's body, and held to ``snapshot``'s contract: it prints its
    own line and never fails. A twice-daily job that exits non-zero the
    morning GitHub is slow is a job that gets uninstalled.
    """
    try:
        from gaffer.config import load_config
        from gaffer.data.core_insights import download_core_insights

        cfg = load_config()
        # The current season as well as the training ones. The fixture table
        # is a prediction-time input (density_pub_7d reads next week's
        # published ties), so the season being played is the one that matters
        # most, and the training seasons are what makes an arm measurable.
        seasons = list(cfg.train_seasons) + [cfg.current_season]
        written = download_core_insights(
            seasons, {s: i for i, s in enumerate(seasons)})
        total = sum(sum(v.values()) for v in written.values())
        typer.echo(f"Core insights: {total} rows across {len(seasons)} "
                   "seasons -> data/core_insights/.")
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        typer.echo(f"core insights not collected: {exc}")
```

- [ ] Create `scripts/com.gaffer.core-insights.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.core-insights</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer core-insights &gt;&gt; logs/core-insights.log 2&gt;&amp;1</string>
  </array>
  <!-- launchd reads StartCalendarInterval in the machine's LOCAL time, not
       UTC. The archive itself updates twice daily at 07:30 and 17:30 UTC, so
       06:30 and 18:30 local on a UK-set machine sit either side of the later
       push and comfortably after the earlier one. Neither slot is
       deadline-sensitive: nothing here is fetched at serve time, and a missed
       run costs freshness rather than an answer. -->
  <!-- Every fetched file is cached forever (data/raw/core_insights), so the
       second run of a day re-downloads only the gameweeks whose files the
       publisher replaced — usually none. -->
  <key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>6</integer>
          <key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>18</integer>
          <key>Minute</key><integer>30</integer></dict>
  </array>
</dict></plist>
```

- [ ] Edit `scripts/install_automation.sh:5`, replacing

```sh
for name in advise prices snapshot field review digest-friday digest-tuesday; do
```

with

```sh
for name in advise prices snapshot field review digest-friday digest-tuesday core-insights; do
```

- [ ] Edit `scripts/install_automation.sh:13`, replacing

```sh
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot + Sat/Sun 12:30 field scrape + Tuesday 09:00 decision review + Friday 17:00 briefing + Tuesday 09:30 debrief."
```

with

```sh
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot + Sat/Sun 12:30 field scrape + Tuesday 09:00 decision review + Friday 17:00 briefing + Tuesday 09:30 debrief + 06:30/18:30 core-insights collection."
```

- [ ] Add one row to the automation table in `README.md` and the same row to
  the automation table in `docs/GUIDE.md`. Find the table by

```bash
grep -n "com.gaffer.field" README.md docs/GUIDE.md
```

and insert, in the same column order the surrounding rows use, a row reading:

`com.gaffer.core-insights` · `06:30, 18:30 daily` · `gaffer core-insights` ·
"FPL-Core-Insights per-match stats, published cup/European fixtures and club
Elo into `data/core_insights/`."

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_core_insights.py -q
# expected: 33 passed
```

- [ ] Commit:

```bash
git add src/gaffer/cli.py scripts/com.gaffer.core-insights.plist \
        scripts/install_automation.sh README.md docs/GUIDE.md \
        tests/test_core_insights.py
git commit -m "$(cat <<'EOF'
feat(w4): gaffer core-insights, twice daily at 06:30 and 18:30

The archive itself pushes at 07:30 and 17:30 UTC, so the two slots sit either
side of the later push. The command follows snapshot's contract — it prints
its own line and never exits non-zero, because a scheduled job that fails the
morning GitHub is slow is a job that gets uninstalled.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — the health line: rows and latest date per table

**Files**
- Modify: `src/gaffer/web/schemas.py` (append two models; extend `Health`)
- Modify: `src/gaffer/web/routers/meta.py` (extend `health()`)
- Modify: `frontend/src/hubs/model/HealthTab.tsx`
- Create: `tests/test_v12_w4_health.py`

### Step 5.1 — failing test

- [ ] Create `tests/test_v12_w4_health.py`:

```python
"""The core-insights health line: rows and latest date, or an honest never."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.data.core_insights import CI_FIXTURE_COLS, CI_PLAYER_COLS, ci_path
from gaffer.web.app import create_app


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    return tmp_path


def test_a_cold_clone_says_never_collected_and_renders_no_zeros(clone):
    body = TestClient(create_app()).get("/api/health").json()
    ci = body["core_insights"]
    assert ci["season"] == "2026-27"
    assert ci["collected"] is False
    assert ci["tables"] == []
    assert "gaffer core-insights" in ci["waiting_for"]


def test_a_collected_season_reports_rows_and_the_latest_date(clone):
    store.save(pd.DataFrame([{**{c: 0 for c in CI_PLAYER_COLS},
                              "season": "2026-27", "code": 1, "gw": 2}]),
               ci_path("2026-27", "players"))
    store.save(pd.DataFrame([{**{c: None for c in CI_FIXTURE_COLS},
                              "season": "2026-27", "gw": 6,
                              "kickoff": pd.Timestamp("2026-10-10T14:00Z"),
                              "team_code": 8}]),
               ci_path("2026-27", "fixtures"))
    body = TestClient(create_app()).get("/api/health").json()
    ci = body["core_insights"]
    assert ci["collected"] is True
    assert ci["waiting_for"] is None
    by = {t["table"]: t for t in ci["tables"]}
    assert by["players"]["rows"] == 1
    assert by["fixtures"]["latest"] == "2026-10-10"
    # Elo was never written on this clone, so it reports zero rows and says
    # so rather than being omitted — an absent Elo table is the archive's
    # state for 2026-27 today, and hiding it would hide that.
    assert by["elo"]["rows"] == 0


def test_the_route_count_did_not_move(clone):
    assert len(create_app().openapi()["paths"]) == 45
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_health.py -q
# expected: 2 failed, 1 passed —
#   KeyError: 'core_insights'   (twice)
```

### Step 5.2 — implementation

- [ ] Append to `src/gaffer/web/schemas.py`, immediately **above**
  `class Health(BaseModel):` (line 816):

```python
class CoreInsightsTable(BaseModel):
    table: str
    rows: int
    latest: str | None = None
    """Newest kickoff date in the table, ``YYYY-MM-DD``, or ``None`` when the
    table has no dated rows. A table with rows and no date is possible — the
    player table is keyed on gameweek, not on a timestamp — and reads as its
    highest gameweek instead."""


class CoreInsightsHealth(BaseModel):
    season: str
    collected: bool
    tables: list[CoreInsightsTable]
    waiting_for: str | None = None
    """What has to happen before these numbers mean anything, or ``None`` when
    they already do. Spec §1: a view whose data does not exist yet says what
    it is waiting for and never renders zeros as if they were measurements."""
```

- [ ] Extend `class Health` in `src/gaffer/web/schemas.py:816-824` by adding
  one field after `artifacts`:

```python
    core_insights: CoreInsightsHealth | None = None
```

- [ ] In `src/gaffer/web/routers/meta.py`, add to the imports from
  `gaffer.web.schemas` the two new names `CoreInsightsHealth` and
  `CoreInsightsTable`, then insert into `health()` immediately before the
  `return Health(` at `:209`:

```python
    # v12 W4 §5.1. Rows and latest date per table, or an honest "never":
    # the collector is opt-in (a CLI run or its plist), so a clone that has
    # not run it must say what it is waiting for rather than render three
    # zeros that look like a measurement.
    from gaffer.data.core_insights import ci_path, season_table_stats

    try:
        season = str(load_config().current_season)
    except Exception:  # noqa: BLE001 — no config.toml is a valid state here
        season = ""
    stats = season_table_stats(season) if season else {}
    collected = bool(season) and any(
        store.exists(ci_path(season, table)) for table in stats)
    core_insights = CoreInsightsHealth(
        season=season,
        collected=collected,
        tables=[CoreInsightsTable(table=name, rows=int(v["rows"]),
                                  latest=v["latest"])
                for name, v in sorted(stats.items())] if collected else [],
        waiting_for=None if collected else
        "a collector run — `gaffer core-insights`, or install "
        "scripts/com.gaffer.core-insights.plist for 06:30 and 18:30 daily")
```

and pass it on the `Health(...)` call by adding `core_insights=core_insights`
as the last keyword.

- [ ] In `frontend/src/hubs/model/HealthTab.tsx`, render the block. Locate the
  existing data-sources card with

```bash
grep -n "data\b\|Sources\|<Card" frontend/src/hubs/model/HealthTab.tsx | head
```

and add, directly after that card, a `<Card title="Core insights">` whose body
is:

```tsx
{health.core_insights == null || !health.core_insights.collected ? (
  <p className="text-sm text-muted">
    Not collected yet ({health.core_insights?.season ?? '—'}). Waiting for{' '}
    {health.core_insights?.waiting_for ?? 'a collector run'}.
  </p>
) : (
  <div className="overflow-x-auto">
    <table className="w-full text-sm">
      <thead>
        <tr><th className="text-left">Table</th>
            <th className="text-right">Rows</th>
            <th className="text-right">Latest</th></tr>
      </thead>
      <tbody>
        {health.core_insights.tables.map((t) => (
          <tr key={t.table}>
            <td>{t.table}</td>
            <td className="text-right tabular-nums">{t.rows}</td>
            <td className="text-right tabular-nums">
              {t.rows === 0 ? 'the archive publishes none yet' : (t.latest ?? '—')}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)}
```

- [ ] Regenerate the TypeScript types so `health.core_insights` type-checks:

```bash
grep -rn "CoreInsights\|core_insights" frontend/src/types.ts || \
  echo "add the two interfaces by hand — see below"
```

If `frontend/src/types.ts` is hand-maintained (it is, until W5 §6.6 lands),
add to it:

```ts
export interface CoreInsightsTable {
  table: string
  rows: number
  latest: string | null
}

export interface CoreInsightsHealth {
  season: string
  collected: boolean
  tables: CoreInsightsTable[]
  waiting_for: string | null
}
```

and add `core_insights: CoreInsightsHealth | null` to the existing `Health`
interface.

- [ ] Run and watch both suites pass:

```bash
.venv/bin/pytest tests/test_v12_w4_health.py -q
# expected: 3 passed
cd frontend && npx vitest run && cd ..
# expected: the pre-existing frontend suite, still green
```

- [ ] Commit:

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/meta.py \
        frontend/src/hubs/model/HealthTab.tsx frontend/src/types.ts \
        tests/test_v12_w4_health.py
git commit -m "$(cat <<'EOF'
feat(w4): health shows core-insights rows and latest date per table

An additive field on Health, so the route count does not move. A clone that
has never run the collector says what it is waiting for rather than rendering
three zeros; a table the archive publishes empty says that too, which is
2026-27's Elo today.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — `tests/test_v12_w4_degradation.py`, block 1: the collector

**Why a separate file from `tests/test_core_insights.py`.** CONVENTIONS and
spec §1 want a named degradation file per cycle whose every test is a state a
real machine reaches. `test_core_insights.py` is the unit suite; this is the
rail. It is a **new** file, so it is not protected this cycle and Tasks 19
appends to it.

**Files**
- Create: `tests/test_v12_w4_degradation.py`

### Step 6.1 — the test *is* the deliverable

- [ ] Create `tests/test_v12_w4_degradation.py`:

```python
"""v12 W4's degradation rails and its three pins.

Every rail is a state a real machine reaches, and the first four are the state
*every* machine is in today: no collection on a fresh clone, an archive whose
2026-27 Elo column is blank, a season (2022-23, 2023-24) the archive has never
published, and a player-match schema that differs between the seasons it has
(``defensive_contributions`` is in two of three).

The schema-drift rails are not hypothetical. They were written from the live
archive, measured 2026-09-02 and transcribed in the W4 plan's Appendix A.
"""

from __future__ import annotations

import dataclasses

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.core_insights import (CI_ELO_COLS, CI_FIXTURE_COLS,
                                       CI_PLAYER_COLS, ci_path,
                                       download_core_insights,
                                       load_core_insights,
                                       season_table_stats)
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS

PLAYERS_CSV = ("player_code,player_id,first_name,second_name,web_name,"
               "team_code,position\n208706,452,Bruno,G,Bruno G.,3,Midfielder\n")

PMS_CSV = ("player_id,match_id,minutes_played,accurate_crosses,"
           "touches_opposition_box,final_third_passes,tackles_won,"
           "interceptions,blocks,clearances,recoveries,start_min,finish_min,"
           "defensive_contributions\n"
           "452,m1,90,2,4,11,3,1,0,2,7,0,90,6\n")

FIXTURES_CSV = ("gameweek,kickoff_time,home_team,home_team_elo,home_score,"
                "away_score,away_team,away_team_elo,finished,match_id,"
                "tournament\n"
                "2,2026-08-30T13:00:00,2.0,1801.5,1,1,94.0,1750.25,True,"
                "m1,prem\n")

ARCHIVE = {"data/2026-2027/players.csv": PLAYERS_CSV,
           "data/2026-2027/By Gameweek/GW2/playermatchstats.csv": PMS_CSV,
           "data/2026-2027/By Gameweek/GW2/fixtures.csv": FIXTURES_CSV}


def _tree(paths) -> dict:
    return {"tree": [{"path": p, "type": "blob"} for p in sorted(paths)]}


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeHTTP:
    def __init__(self, files):
        self.files = dict(files)

    def get(self, url, **_kw):
        path = url.split("/main/", 1)[-1]
        if path not in self.files:
            raise httpx.HTTPError(f"404 {path}")
        return _Resp(self.files[path])


class _DeadHTTP:
    def get(self, *_a, **_kw):
        raise httpx.ConnectError("no route to host")


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    """A machine with nothing collected."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    return tmp_path


# --- Block 1: the collector ----------------------------------------------

def test_an_unreachable_repo_is_a_printed_line_and_no_write(clone, capsys):
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 client=_DeadHTTP())
    assert out == {"2026-27": {"players": 0, "fixtures": 0, "elo": 0}}
    assert not store.exists(ci_path("2026-27", "players"))
    assert "unavailable" in capsys.readouterr().out


def test_an_unreachable_repo_never_truncates_a_previous_collection(clone):
    """The rail that matters most: a network blip must not delete data."""
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=_tree(ARCHIVE), client=_FakeHTTP(ARCHIVE))
    before = load_core_insights("2026-27", "players")
    assert len(before) == 1
    download_core_insights(["2026-27"], {"2026-27": 3}, client=_DeadHTTP())
    assert len(load_core_insights("2026-27", "players")) == 1


def test_an_unknown_column_added_upstream_changes_nothing(clone):
    drifted = dict(ARCHIVE)
    drifted["data/2026-2027/By Gameweek/GW2/playermatchstats.csv"] = (
        PMS_CSV.replace("player_id,", "brand_new_metric,player_id,")
        .replace("452,m1", "0.5,452,m1"))
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=_tree(drifted), client=_FakeHTTP(drifted))
    frame = load_core_insights("2026-27", "players")
    assert list(frame.columns) == CI_PLAYER_COLS
    assert len(frame) == 1


def test_an_expected_column_removed_upstream_is_null_not_a_crash(clone,
                                                                capsys):
    """A3: the 2024-2025 layout genuinely lacks defensive_contributions."""
    drifted = dict(ARCHIVE)
    drifted["data/2026-2027/By Gameweek/GW2/playermatchstats.csv"] = (
        PMS_CSV.replace(",defensive_contributions", "").replace(",6\n", "\n"))
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=_tree(drifted), client=_FakeHTTP(drifted))
    frame = load_core_insights("2026-27", "players")
    assert list(frame.columns) == CI_PLAYER_COLS
    assert frame["defensive_contributions"].isna().all()
    assert "does not publish" in capsys.readouterr().out


def test_a_key_column_removed_upstream_drops_the_file_not_the_run(clone):
    drifted = dict(ARCHIVE)
    drifted["data/2026-2027/By Gameweek/GW2/playermatchstats.csv"] = \
        PMS_CSV.replace("player_id,match_id,", "match_id,")
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 tree=_tree(drifted),
                                 client=_FakeHTTP(drifted))
    assert out["2026-27"]["players"] == 0
    assert out["2026-27"]["fixtures"] == 2   # the fixture file is untouched


def test_an_empty_season_writes_empty_tables_with_the_right_columns(clone):
    tree = _tree(["data/2026-2027/players.csv"])
    files = {"data/2026-2027/players.csv": PLAYERS_CSV}
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree=tree,
                                 client=_FakeHTTP(files))
    assert out["2026-27"] == {"players": 0, "fixtures": 0, "elo": 0}
    assert list(load_core_insights("2026-27", "fixtures").columns) == \
        CI_FIXTURE_COLS
    assert list(load_core_insights("2026-27", "elo").columns) == CI_ELO_COLS


def test_a_season_whose_elo_column_is_blank_collects_no_elo(clone):
    """A3c: 2026-27's live archive, today."""
    blank = dict(ARCHIVE)
    blank["data/2026-2027/By Gameweek/GW2/fixtures.csv"] = \
        FIXTURES_CSV.replace("1801.5", "").replace("1750.25", "")
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 tree=_tree(blank), client=_FakeHTTP(blank))
    assert out["2026-27"]["fixtures"] == 2
    assert out["2026-27"]["elo"] == 0
    assert season_table_stats("2026-27")["elo"] == {"rows": 0, "latest": None}


def test_another_seasons_rows_are_never_returned(clone):
    """The season guard. Element ids remap every season; a reader that
    borrowed 2025-26's rows for 2026-27 would attach one footballer's
    defensive numbers to another."""
    frame = pd.DataFrame([{**{c: 0 for c in CI_PLAYER_COLS},
                           "season": "2025-26", "code": 1}])
    store.save(frame, ci_path("2026-27", "players"))
    assert load_core_insights("2026-27", "players").empty


def test_a_torn_parquet_is_a_missing_one(clone):
    path = store.DATA_DIR / ci_path("2026-27", "players")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a parquet")
    assert load_core_insights("2026-27", "players").empty


def test_the_health_line_on_a_cold_clone_is_a_200_that_says_why(clone):
    body = TestClient(create_app()).get("/api/health").json()
    assert body["core_insights"]["collected"] is False
    assert body["core_insights"]["tables"] == []
    assert body["core_insights"]["waiting_for"]


# --- Pins (CONVENTIONS §7; the v11 values, unmoved) ----------------------

def test_the_job_kinds_are_still_twelve():
    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    assert len(dataclasses.fields(Config)) == 48


def test_the_route_count_did_not_move(clone):
    assert len(create_app().openapi()["paths"]) == 45
```

- [ ] Run:

```bash
.venv/bin/pytest tests/test_v12_w4_degradation.py -q
# expected: 13 passed
```

- [ ] Commit:

```bash
git add tests/test_v12_w4_degradation.py
git commit -m "$(cat <<'EOF'
test(w4): collector degradation rails and the three unmoved pins

Repo unreachable (and, the rail that matters, a blip that must not truncate a
previous collection), schema drift in both directions, an empty season, a
blank Elo column, a cross-season read, a torn parquet, and a cold clone's
health line. The drift rails were transcribed from the live archive, not
imagined: defensive_contributions really is absent from one of its three
seasons.

# v12 W4 §5.1 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — `role_wb_share`: the wing-back share of a defender's last five starts

**The rule, stated rather than fitted.** A wing-back is a defender who spends
the match in the final third. From the columns present in *every* season the
archive publishes (A3 — so **not** `defensive_contributions`), a start is
classified wing-back when the player recorded **at least one accurate cross**
or **at least three touches in the opposition box**. A start is a match with
`start_min <= 1` or `minutes_played >= 60`. `role_wb_share` is the mean of
that indicator over his **last five starts before this fixture**, defenders
only, `NaN` for everyone else and for a defender with fewer than five prior
starts, with a companion `role_wb_missing` indicator so LightGBM can tell "not
a defender" from "a defender we have not seen enough of".

Like `HAUL_SIGMA` and `LEAGUE_PENS_PG`, this is a **convention written down**,
not a number fitted to an outcome. Task 10's arm is what decides whether it is
worth anything.

**Files**
- Modify: `src/gaffer/features/engineer.py` (append, after
  `add_shrunken_cards` which ends the module)
- Create: `tests/test_v12_w4_features.py`

### Step 7.1 — failing test

- [ ] Create `tests/test_v12_w4_features.py`:

```python
"""v12 W4 §5.2's two feature builders, and the coverage they really have."""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.features.engineer import (ROLE_FEATURES, WB_BOX_TOUCHES,
                                      WB_CROSSES, add_role_wb_share)


def _pms(rows: list[dict]) -> pd.DataFrame:
    base = {"season": "2025-26", "season_idx": 3, "gw": 1, "code": 1,
            "minutes_played": 90.0, "start_min": 0.0, "finish_min": 90.0,
            "accurate_crosses": 0.0, "touches_opposition_box": 0.0}
    return pd.DataFrame([{**base, **r} for r in rows])


def _players(rows: list[dict]) -> pd.DataFrame:
    base = {"season_idx": 3, "gw": 6, "code": 1, "position": "DEF"}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_the_feature_names_are_two_and_stable():
    assert ROLE_FEATURES == ["role_wb_share", "role_wb_missing"]


def test_a_defender_who_crosses_every_week_reads_one():
    stats = _pms([{"gw": g, "accurate_crosses": 2.0} for g in range(1, 6)])
    out = add_role_wb_share(_players([{}]), stats)
    assert out["role_wb_share"].iloc[0] == 1.0
    assert out["role_wb_missing"].iloc[0] == 0.0


def test_a_centre_back_who_never_crosses_reads_zero():
    stats = _pms([{"gw": g} for g in range(1, 6)])
    out = add_role_wb_share(_players([{}]), stats)
    assert out["role_wb_share"].iloc[0] == 0.0
    assert out["role_wb_missing"].iloc[0] == 0.0


def test_box_touches_alone_classify_a_start_as_wing_back():
    stats = _pms([{"gw": g, "touches_opposition_box": float(WB_BOX_TOUCHES)}
                  for g in range(1, 6)])
    assert add_role_wb_share(_players([{}]), stats)["role_wb_share"].iloc[0] \
        == 1.0


def test_the_thresholds_are_the_stated_ones():
    assert (WB_CROSSES, WB_BOX_TOUCHES) == (1, 3)


def test_three_of_five_starts_read_zero_point_six():
    stats = _pms([{"gw": 1, "accurate_crosses": 1.0},
                  {"gw": 2, "accurate_crosses": 1.0},
                  {"gw": 3, "accurate_crosses": 1.0},
                  {"gw": 4}, {"gw": 5}])
    assert add_role_wb_share(_players([{}]),
                             stats)["role_wb_share"].iloc[0] == 0.6


def test_only_the_last_five_starts_count():
    stats = _pms([{"gw": g, "accurate_crosses": 5.0} for g in range(1, 4)]
                 + [{"gw": g} for g in range(4, 9)])
    assert add_role_wb_share(_players([{"gw": 9}]),
                             stats)["role_wb_share"].iloc[0] == 0.0


def test_a_substitute_appearance_is_not_a_start():
    stats = _pms([{"gw": g, "minutes_played": 20.0, "start_min": 70.0,
                   "accurate_crosses": 3.0} for g in range(1, 9)])
    out = add_role_wb_share(_players([{}]), stats)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_fewer_than_five_starts_is_missing_not_a_partial_mean():
    stats = _pms([{"gw": g, "accurate_crosses": 1.0} for g in range(1, 4)])
    out = add_role_wb_share(_players([{}]), stats)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_a_non_defender_is_missing_by_definition():
    stats = _pms([{"gw": g, "accurate_crosses": 4.0} for g in range(1, 6)])
    out = add_role_wb_share(_players([{"position": "MID"}]), stats)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_the_feature_never_looks_forward():
    """A start in the gameweek being predicted must not feed its own
    feature — that is leakage, and it is the whole reason this reads
    ``< gw`` rather than ``<= gw``."""
    stats = _pms([{"gw": g} for g in range(1, 6)]
                 + [{"gw": 6, "accurate_crosses": 9.0}])
    assert add_role_wb_share(_players([{"gw": 6}]),
                             stats)["role_wb_share"].iloc[0] == 0.0


def test_another_seasons_starts_never_leak_across_the_boundary():
    stats = pd.concat([
        _pms([{"gw": g, "accurate_crosses": 4.0} for g in range(1, 9)])
        .assign(season="2024-25", season_idx=2),
        _pms([{"gw": g} for g in range(1, 6)])])
    out = add_role_wb_share(_players([{"gw": 6}]), stats)
    assert out["role_wb_share"].iloc[0] == 0.0


def test_an_empty_stats_frame_is_all_missing_and_not_a_crash():
    out = add_role_wb_share(_players([{}]),
                            pd.DataFrame(columns=["season_idx", "gw", "code"]))
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_the_builder_adds_exactly_two_columns_and_reorders_nothing():
    players = _players([{"code": 1}, {"code": 2}, {"code": 3}])
    out = add_role_wb_share(players, _pms([{"gw": 1}]))
    assert list(out.columns) == list(players.columns) + ROLE_FEATURES
    assert list(out["code"]) == [1, 2, 3]
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q
# expected: collection error —
#   ImportError: cannot import name 'ROLE_FEATURES' from
#   'gaffer.features.engineer'
```

### Step 7.2 — implementation

- [ ] Append to `src/gaffer/features/engineer.py`:

```python
# --- v12 W4 §5.2: role and published-fixture density ---------------------

ROLE_FEATURES = ["role_wb_share", "role_wb_missing"]
"""v12 W4 §5.2 arm 1. **A new arm, not the withdrawn congestion one.**

``role_wb_share`` is the share of a defender's last five starts in which the
per-match profile reads as a wing-back rather than a centre-back. It is built
from FPL-Core-Insights' ``playermatchstats`` and answers a question the FPL
feed cannot: two 5.0m defenders at the same club have very different minutes
risk when one of them is the width in a back three.

**The classification is a stated convention, not a fitted classifier.** A
start is wing-back when the player recorded at least :data:`WB_CROSSES`
accurate crosses **or** at least :data:`WB_BOX_TOUCHES` touches in the
opposition box. Those two columns were chosen because they are the only
positional signal published in *every* season the archive covers — the
2024-2025 layout has no ``defensive_contributions`` at all (W4 plan A3) — and
because a rule that used a column present in two seasons of three would be a
season indicator wearing a role's name, which is exactly what withdrew v5's
:data:`CONGESTION_FEATURES`.

``role_wb_missing`` is 1 for a non-defender, for a defender with fewer than
:data:`WB_MIN_STARTS` prior starts, and on a machine with no collection. Three
different silences, one indicator: LightGBM handles the NaN natively and the
indicator is what lets it separate "we do not know" from "we know it is zero".
"""

WB_CROSSES = 1
WB_BOX_TOUCHES = 3
WB_MIN_STARTS = 5
WB_STARTER_MINUTES = 60
"""Thresholds of the wing-back rule. Conventions, written down here so a later
reader changes them deliberately rather than discovering them in a comprehension."""


def _starts_frame(stats: pd.DataFrame) -> pd.DataFrame:
    """``playermatchstats`` -> one row per *start*, with the wb indicator.

    A start is ``start_min <= 1`` — the archive writes the minute a player came
    on, so 0 is the whistle — or, where that column is null,
    ``minutes_played >= WB_STARTER_MINUTES``, the house ``STARTER_MINUTES``
    definition. A substitute who crossed three times in twenty minutes is not
    evidence about his role in the XI, and counting him would make every
    attacking sub read as a wing-back.
    """
    need = {"season_idx", "gw", "code"}
    if stats is None or stats.empty or not need.issubset(stats.columns):
        return pd.DataFrame(columns=["season_idx", "gw", "code", "_wb"])
    work = pd.DataFrame({
        "season_idx": pd.to_numeric(stats["season_idx"], errors="coerce"),
        "gw": pd.to_numeric(stats["gw"], errors="coerce"),
        "code": pd.to_numeric(stats["code"], errors="coerce")})
    for col in ("minutes_played", "start_min", "accurate_crosses",
                "touches_opposition_box"):
        work[col] = (pd.to_numeric(stats[col], errors="coerce")
                     if col in stats.columns else float("nan"))
    started = np.where(work["start_min"].notna(),
                       work["start_min"] <= 1.0,
                       work["minutes_played"] >= WB_STARTER_MINUTES)
    work = work[pd.Series(started, index=work.index).fillna(False)
                & work["season_idx"].notna() & work["gw"].notna()
                & work["code"].notna()]
    if work.empty:
        return pd.DataFrame(columns=["season_idx", "gw", "code", "_wb"])
    wb = ((work["accurate_crosses"].fillna(0.0) >= WB_CROSSES)
          | (work["touches_opposition_box"].fillna(0.0) >= WB_BOX_TOUCHES))
    work["_wb"] = wb.astype("float64")
    # A double gameweek is two starts, and both of them are evidence; the
    # aggregation below therefore counts matches, not gameweeks.
    return work[["season_idx", "gw", "code", "_wb"]]


def add_role_wb_share(df: pd.DataFrame,
                      stats: pd.DataFrame | None) -> pd.DataFrame:
    """``df`` with :data:`ROLE_FEATURES` appended. Never reorders rows.

    ``stats`` is the concatenation of ``load_core_insights(season, "players")``
    over the seasons in play, or ``None`` on a machine that has not run the
    collector — in which case every row is missing, which is the documented
    degradation and is what the arm's lever guard checks for before it
    measures anything.

    Strictly backward-looking: only starts at a *lower* gameweek in the *same*
    season count. ``<`` rather than ``<=`` because the fixture being predicted
    has not been played, and a season boundary is a hard stop because a role
    under last season's manager is not this season's role.
    """
    out = df.copy()
    starts = _starts_frame(stats if stats is not None else pd.DataFrame())
    share = pd.Series(float("nan"), index=out.index, dtype="float64")
    if not starts.empty and {"season_idx", "gw", "code",
                             "position"}.issubset(out.columns):
        starts = starts.sort_values(["code", "season_idx", "gw"])
        by_key: dict[tuple[int, int], list[tuple[int, float]]] = {}
        for r in starts.itertuples():
            by_key.setdefault((int(r.season_idx), int(r.code)), []).append(
                (int(r.gw), float(r._wb)))
        idx = pd.to_numeric(out["season_idx"], errors="coerce")
        gws = pd.to_numeric(out["gw"], errors="coerce")
        codes = pd.to_numeric(out["code"], errors="coerce")
        values = []
        for si, gw, code, pos in zip(idx, gws, codes, out["position"]):
            if str(pos) != "DEF" or pd.isna(si) or pd.isna(gw) \
                    or pd.isna(code):
                values.append(float("nan"))
                continue
            prior = [v for g, v in by_key.get((int(si), int(code)), [])
                     if g < int(gw)]
            values.append(float(np.mean(prior[-WB_MIN_STARTS:]))
                          if len(prior) >= WB_MIN_STARTS else float("nan"))
        share = pd.Series(values, index=out.index, dtype="float64")
    out["role_wb_share"] = share
    out["role_wb_missing"] = share.isna().astype("float64")
    return out
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q
# expected: 14 passed
```

- [ ] Commit:

```bash
git add src/gaffer/features/engineer.py tests/test_v12_w4_features.py
git commit -m "$(cat <<'EOF'
feat(w4): role_wb_share, a defender's wing-back share of his last five starts

The classification is a stated convention — at least one accurate cross or
three opposition-box touches in a start — chosen from the two positional
columns the archive publishes in every season it covers. A rule built on
defensive_contributions would have been a season indicator wearing a role's
name, which is exactly what withdrew v5's congestion features.

Strictly backward-looking and season-bounded: role under last season's manager
is not this season's role.

# v12 W4 §5.2 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — `density_pub_7d`: published fixtures in the seven days before kickoff

**How this differs from the withdrawn congestion arm, and why it must be said
out loud.** v5's `CONGESTION_FEATURES` and v8a's `f2_cups` counted *played*
matches out of `history/cup_matches.parquet`, whose rows begin in 2025-26 — so
on the 2024-25 benchmark the column was partly a season indicator and the arms
were withdrawn (`models/train.py`'s `MINUTES_FEATURES` docstring, and
`CONGESTION_FEATURES`' own at `engineer.py:112-137`). `density_pub_7d` counts
**published** fixtures — league, EFL Cup, Europe, everything
`By Gameweek/GW<n>/fixtures.csv` carries — from a list the archive publishes
*before* the matches are played (A2d). That makes it available at prediction
time for a gameweek nobody has played, which the played-archive column never
was. **It is a different quantity from a different table and it is a new arm.**
It has its own confound, and Task 10's preflight is what measures it rather
than assuming it away.

**Files**
- Modify: `src/gaffer/features/engineer.py` (append)
- Modify: `tests/test_v12_w4_features.py` (append)

### Step 8.1 — failing test

- [ ] Append to `tests/test_v12_w4_features.py`:

```python
# --- Task 8: density_pub_7d ---------------------------------------------

from gaffer.features.engineer import (DENSITY_FEATURES, DENSITY_WINDOW_DAYS,
                                      add_density_pub)


def _fx(rows: list[dict]) -> pd.DataFrame:
    base = {"season": "2026-27", "season_idx": 4, "gw": 6,
            "tournament": "prem", "match_id": "m", "team_code": 8,
            "opponent_code": 91, "is_home": True, "finished": False}
    out = pd.DataFrame([{**base, **r} for r in rows])
    out["kickoff"] = pd.to_datetime(out["kickoff"], utc=True)
    return out


def _rows(rows: list[dict]) -> pd.DataFrame:
    base = {"season_idx": 4, "gw": 6, "code": 1, "team_code": 8,
            "kickoff_time": "2026-10-10T14:00:00Z"}
    out = pd.DataFrame([{**base, **r} for r in rows])
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], utc=True)
    return out


def test_the_feature_names_are_two_and_stable():
    assert DENSITY_FEATURES == ["density_pub_7d", "density_pub_missing"]
    assert DENSITY_WINDOW_DAYS == 7


def test_a_club_with_a_midweek_tie_reads_one():
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z",
                     "tournament": "efl-cup"},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    out = add_density_pub(_rows([{}]), fixtures)
    assert out["density_pub_7d"].iloc[0] == 1.0
    assert out["density_pub_missing"].iloc[0] == 0.0


def test_the_fixture_being_predicted_is_not_counted_against_itself():
    fixtures = _fx([{"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_a_match_eight_days_earlier_is_outside_the_window():
    fixtures = _fx([{"kickoff": "2026-10-02T14:00:00Z"},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_european_and_league_ties_both_count():
    fixtures = _fx([{"kickoff": "2026-10-06T19:00:00Z",
                     "tournament": "champions-league"},
                    {"kickoff": "2026-10-08T19:00:00Z",
                     "tournament": "prem"},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 2.0


def test_an_unplayed_future_tie_counts_which_is_the_whole_point():
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z", "finished": False,
                     "tournament": "efl-cup"},
                    {"kickoff": "2026-10-10T14:00:00Z", "finished": False}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 1.0


def test_another_clubs_ties_never_count():
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z", "team_code": 3},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_another_seasons_ties_never_count():
    fixtures = pd.concat([
        _fx([{"kickoff": "2026-10-07T19:00:00Z"}]).assign(season_idx=3),
        _fx([{"kickoff": "2026-10-10T14:00:00Z"}])])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_a_duplicated_fixture_row_counts_once():
    """The table emits one row per club per match, and a club can appear in
    both a By Gameweek file and a re-collection; the count is over matches."""
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z", "match_id": "cup1"},
                    {"kickoff": "2026-10-07T19:00:00Z", "match_id": "cup1"},
                    {"kickoff": "2026-10-10T14:00:00Z", "match_id": "lg"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 1.0


def test_no_collection_is_missing_everywhere_not_zero_everywhere():
    out = add_density_pub(_rows([{}]), None)
    assert np.isnan(out["density_pub_7d"].iloc[0])
    assert out["density_pub_missing"].iloc[0] == 1.0


def test_a_row_with_no_kickoff_time_is_missing_not_zero():
    out = add_density_pub(_rows([{"kickoff_time": None}]),
                          _fx([{"kickoff": "2026-10-07T19:00:00Z"}]))
    assert np.isnan(out["density_pub_7d"].iloc[0])


def test_the_builder_adds_exactly_two_columns_and_reorders_nothing():
    rows = _rows([{"code": 1}, {"code": 2}])
    out = add_density_pub(rows, _fx([{"kickoff": "2026-10-07T19:00:00Z"}]))
    assert list(out.columns) == list(rows.columns) + DENSITY_FEATURES
    assert list(out["code"]) == [1, 2]
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q
# expected: collection error —
#   ImportError: cannot import name 'DENSITY_FEATURES'
```

### Step 8.2 — implementation

- [ ] Append to `src/gaffer/features/engineer.py`:

```python
DENSITY_FEATURES = ["density_pub_7d", "density_pub_missing"]
"""v12 W4 §5.2 arm 2. **A new arm, and deliberately not the withdrawn one.**

``density_pub_7d`` counts the club's *published* fixtures — league, EFL Cup,
Champions/Europa/Conference League, everything the archive's
``By Gameweek/GW<n>/fixtures.csv`` carries — with a kickoff in the seven days
before this fixture's own kickoff, excluding this fixture.

The difference from :data:`CONGESTION_FEATURES` and from v8a's withdrawn
``f2_cups`` is the table, not the arithmetic. Those counted *played* matches
out of ``history/cup_matches.parquet``, whose rows begin in 2025-26, so on the
2024-25 benchmark they were partly a season indicator and were withdrawn. This
counts fixtures the publisher lists **before they are played** (the archive
publishes kickoff times for gameweeks nobody has reached), which is what makes
it a prediction-time feature at all: the question "does this club play on
Wednesday" is answerable on Thursday only from a forward list.

It has its own coverage limit — the archive's earliest season is 2024-25 — and
``scripts/v12_w4_arms.py``'s preflight measures that rather than assuming it
away.

``density_pub_missing`` is 1 on a machine with no collection and on a row with
no kickoff time. Zero would be a claim that the club plays nothing that week,
which is a different and much stronger statement than "we do not know".
"""

DENSITY_WINDOW_DAYS = 7


def add_density_pub(df: pd.DataFrame,
                    fixtures: pd.DataFrame | None) -> pd.DataFrame:
    """``df`` with :data:`DENSITY_FEATURES` appended. Never reorders rows.

    ``fixtures`` is the concatenation of
    ``load_core_insights(season, "fixtures")`` over the seasons in play, or
    ``None`` on a machine that has not run the collector.

    ``df`` must carry ``season_idx``, ``team_code`` and a timezone-aware
    ``kickoff_time``; a row missing any of them is missing rather than zero.
    Counting is over distinct ``match_id``, because the fixture table emits one
    row per club per match and a re-collection can leave two.
    """
    out = df.copy()
    count = pd.Series(float("nan"), index=out.index, dtype="float64")
    need_df = {"season_idx", "team_code", "kickoff_time"}
    need_fx = {"season_idx", "team_code", "kickoff", "match_id"}
    if (fixtures is not None and not fixtures.empty
            and need_fx.issubset(fixtures.columns)
            and need_df.issubset(out.columns)):
        fx = pd.DataFrame({
            "season_idx": pd.to_numeric(fixtures["season_idx"],
                                        errors="coerce"),
            "team_code": pd.to_numeric(fixtures["team_code"],
                                       errors="coerce"),
            "kickoff": pd.to_datetime(fixtures["kickoff"], errors="coerce",
                                      utc=True),
            "match_id": fixtures["match_id"].astype("string")})
        fx = fx.dropna(subset=["season_idx", "team_code", "kickoff"])
        fx = fx.drop_duplicates(subset=["season_idx", "team_code",
                                        "match_id"])
        by_club: dict[tuple[int, int], list] = {}
        for r in fx.itertuples():
            by_club.setdefault((int(r.season_idx), int(r.team_code)),
                               []).append(r.kickoff)
        window = pd.Timedelta(days=DENSITY_WINDOW_DAYS)
        idx = pd.to_numeric(out["season_idx"], errors="coerce")
        teams = pd.to_numeric(out["team_code"], errors="coerce")
        kicks = pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
        values = []
        for si, team, when in zip(idx, teams, kicks):
            if pd.isna(si) or pd.isna(team) or pd.isna(when):
                values.append(float("nan"))
                continue
            stamps = by_club.get((int(si), int(team)), [])
            values.append(float(sum(1 for t in stamps
                                    if when - window <= t < when)))
        count = pd.Series(values, index=out.index, dtype="float64")
    out["density_pub_7d"] = count
    out["density_pub_missing"] = count.isna().astype("float64")
    return out


def core_insights_frames(seasons: list[str]
                         ) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """``(player-match stats, fixtures)`` across ``seasons``, or ``(None, None)``.

    ``None`` rather than an empty frame when *nothing at all* is collected, so
    :func:`add_role_wb_share` and :func:`add_density_pub` can tell "this
    machine has no collection" from "this club played nothing" — the same
    distinction :func:`gaffer.data.cups.load_cup_matches` draws and for the
    same reason. Read here rather than passed by every caller, exactly as
    ``build_prediction_frame`` reads the manager-tenure asset.
    """
    from gaffer.data.core_insights import load_core_insights

    stats, fixtures = [], []
    for season in seasons:
        stats.append(load_core_insights(season, "players"))
        fixtures.append(load_core_insights(season, "fixtures"))
    stats = [f for f in stats if not f.empty]
    fixtures = [f for f in fixtures if not f.empty]
    return (pd.concat(stats, ignore_index=True) if stats else None,
            pd.concat(fixtures, ignore_index=True) if fixtures else None)
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q
# expected: 26 passed
```

- [ ] Commit:

```bash
git add src/gaffer/features/engineer.py tests/test_v12_w4_features.py
git commit -m "$(cat <<'EOF'
feat(w4): density_pub_7d, published fixtures in the week before kickoff

A different quantity from the withdrawn congestion arm, from a different
table: those counted played matches out of an archive that began in 2025-26,
this counts fixtures the publisher lists before they are played. That forward
list is what makes it answerable on a Thursday for a Sunday nobody has
reached. Its own coverage limit is measured by the arm driver's preflight
rather than assumed away.

# v12 W4 §5.2 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — wire both builders into the training and prediction frames, **off**

**The shipping decision, stated before the numbers exist (CONVENTIONS §2).**
Both columns are **built** into every frame and neither is added to
`MINUTES_FEATURES`. They ship off. Task 10's driver composes them onto the
module global the way `scripts/v10_shrunk_arm.py:227-228` does, and only Task
21's gate, after the orchestrator has run the driver, decides whether either
is added for real. A feature that arrives already in the model is a feature
nobody measured.

**Files**
- Modify: `src/gaffer/models/train.py` (`load_training_frame`, around `:335-345`)
- Modify: `src/gaffer/features/engineer.py` (`feature_columns` at `:839-855`;
  `build_prediction_frame` at `:730-…`)
- Modify: `tests/test_v12_w4_features.py` (append)

### Step 9.1 — failing test

- [ ] Append to `tests/test_v12_w4_features.py`:

```python
# --- Task 9: wiring ------------------------------------------------------

from gaffer.features.engineer import feature_columns
from gaffer.models import train as tr


def test_the_new_columns_are_canonical_inputs():
    cols = feature_columns()
    for name in ROLE_FEATURES + DENSITY_FEATURES:
        assert name in cols


def test_neither_arm_ships_inside_the_minutes_model():
    """CONVENTIONS §2: the gate is pre-registered and the arm is off until it
    passes. A feature that arrives already in the model is a feature nobody
    measured."""
    for name in ROLE_FEATURES + DENSITY_FEATURES:
        assert name not in tr.MINUTES_FEATURES


def test_the_builders_are_wired_into_the_training_frame():
    import inspect
    src = inspect.getsource(tr.load_training_frame)
    assert "add_role_wb_share" in src and "add_density_pub" in src


def test_the_builders_are_wired_into_the_prediction_frame():
    import inspect

    from gaffer.features.engineer import build_prediction_frame
    src = inspect.getsource(build_prediction_frame)
    assert "add_role_wb_share" in src and "add_density_pub" in src
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q -k "canonical or wired"
# expected: 3 failed —
#   AssertionError: assert 'role_wb_share' in [...]
#   AssertionError: assert 'add_role_wb_share' in '...'  (twice)
```

### Step 9.2 — implementation

- [ ] In `src/gaffer/features/engineer.py:839-855`, extend `feature_columns`'s
  return by adding `+ ROLE_FEATURES + DENSITY_FEATURES` after
  `+ SHRUNK_CARD_FEATURES`, so the tail reads:

```python
            + understat_feature_columns() + TEAM_US_FEATURES
            + SHRUNK_FEATURES + SHRUNK_MODE_FEATURES
            + SHRUNK_CARD_FEATURES
            # v12 W4 §5.2. Listed here because ``feature_columns`` is what a
            # caller strips before re-deriving; the columns are *built* on
            # every frame and fed to no head until an arm passes.
            + ROLE_FEATURES + DENSITY_FEATURES)
```

- [ ] In `src/gaffer/models/train.py`, immediately after the line
  `df = add_congestion(df, None, prefix=LEAGUE_CONGESTION_PREFIX)` (`:344`),
  insert:

```python
    # v12 W4 §5.2. Both builders return the frame they were given with two
    # columns appended and no row moved — row order matters here, see the
    # comment above — and both degrade to all-missing when the collector has
    # never run, which is every machine until `gaffer core-insights` does.
    ci_stats, ci_fixtures = core_insights_frames(seasons)
    df = add_role_wb_share(df, ci_stats)
    df = add_density_pub(df, ci_fixtures)
```

and add `add_density_pub`, `add_role_wb_share`, `core_insights_frames` to the
existing `from gaffer.features.engineer import (…)` block at `:26-30`.

**Check first**: `load_training_frame` must have a `seasons` list in scope at
that point. Read `src/gaffer/models/train.py:273-345` and confirm; if the
local name differs (it may be `cfg.train_seasons` or built from
`season_indexes`), use whatever the function already has and **do not add a
config read**. If no season list is in scope, STOP and report — deriving one
here would be a second source of truth for which seasons are in play.

- [ ] In `src/gaffer/features/engineer.py::build_prediction_frame`, after the
  block that re-attaches congestion (the `out = pd.concat([out, cong…])` line
  at `:775-776`), insert:

```python
    # v12 W4 §5.2. Serve-time halves of the two arms. Rebuilt rather than
    # tailed for the same reason congestion is: each future row has its own
    # kickoff, and ``density_pub_7d`` is a function of that kickoff.
    seasons = sorted({str(s) for s in out.get("season", pd.Series(dtype=str))
                      if isinstance(s, str)})
    ci_stats, ci_fixtures = core_insights_frames(seasons) if seasons \
        else (None, None)
    out = add_role_wb_share(out, ci_stats)
    out = add_density_pub(out, ci_fixtures)
```

**Check first**: `build_prediction_frame`'s `out` must carry `season`,
`kickoff_time`, `team_code` and `position`. Verify with

```bash
grep -n "kickoff_time\|\"season\"\|'season'" src/gaffer/features/engineer.py \
  | sed -n '1,40p'
```

If `kickoff_time` is absent from `out`, use whatever column
`latest_congestion` keys its dates on (`add_congestion` reads it at `:507`)
and **say so in the commit message**; if `season` is absent but `season_idx`
is, map through the caller's season list rather than inventing one, and if
neither is available, STOP and report.

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q
# expected: 30 passed
.venv/bin/pytest tests/ -q -x -k "engineer or train or features"
# expected: the pre-existing feature and training suites, still green —
# both builders append columns and move no row, which is the property
# add_congestion's own comment at train.py:338-344 says the chain depends on
```

- [ ] Commit:

```bash
git add src/gaffer/features/engineer.py src/gaffer/models/train.py \
        tests/test_v12_w4_features.py
git commit -m "$(cat <<'EOF'
feat(w4): build both W4 arms into every frame, and feed them to no head

They ship off. The driver composes them onto MINUTES_FEATURES the way
v10_shrunk_arm.py does, and only the gate decides whether either is added for
real — a feature that arrives already in the model is a feature nobody
measured. Both builders append columns and move no row, which is the property
the add_congestion chain depends on.

# v12 W4 §5.2 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — `scripts/v12_w4_arms.py`: the pre-registered arm driver

**The bar, pre-registered here before any arm runs (CONVENTIONS §2), and it is
v10 §F3a's verbatim:**

> KEEP an arm iff the **starters-slice `p_start` log-loss improves by ≥ 1%
> relative** to the control arm of the same run **and** the **zeros RMSE does
> not get worse by more than 0.005**.

Two arms, one control, all three fit in one run: `role` (`ROLE_FEATURES`),
`density` (`DENSITY_FEATURES`), `baseline` (nothing added). Each is judged
against `baseline` **of this run** and never against a banked number
(CONVENTIONS §1, §3).

**The window is shifted, and that is a pre-registered decision, not a
convenience. Authorized by the orchestrator on 2026-09-02 (Appendix B §1),
with the coverage guard kept as the exit path.**
`evaluation.py:1003,1006` ship `BENCHMARK_TRAIN_MAX_IDX = 1`,
`BENCHMARK_TEST_IDX = 2` — train 2022-23 + 2023-24, test 2024-25. The archive's
earliest season is 2024-2025, so on that window **both arms are null
throughout training** and the fit could only learn "populated ⇒ test season".
That is the confound that withdrew v5's congestion features and made v8a's
`f2_league`/`f2_cups` value-identical. This driver therefore runs at
`max_train_idx = 2`, `test_idx = 3` — train 2022-23…2024-25 (2024-25
populated), test 2025-26 (populated) — and the control is fit on the same
shifted window, so the comparison is like for like even though the absolute
numbers are not comparable to any banked benchmark figure. **The driver prints
the window it used on every line**, because a number whose window is not on
the line is a number somebody will compare against the wrong one.

**Three lever guards, all before any arm is scored** (v9c's and v8a's twice-
learned lesson): the arm's feature list must differ from the control's; every
arm column must exist, be non-null somewhere and be non-constant; and — new
here, and the one that matters for this archive — **training coverage must be
non-zero**, printed per season, or the run exits.

**Files**
- Create: `scripts/v12_w4_arms.py`
- Modify: `tests/test_v12_w4_features.py` (append; the driver's pure parts)

### Step 10.1 — failing test

- [ ] Append to `tests/test_v12_w4_features.py`:

```python
# --- Task 10: the arm driver's pure parts --------------------------------

import importlib.util as _ilu
from pathlib import Path as _P


def _driver():
    spec = _ilu.spec_from_file_location("v12_w4_arms",
                                        _P("scripts/v12_w4_arms.py"))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_window_is_the_shifted_one_and_is_stated():
    d = _driver()
    assert (d.TRAIN_MAX_IDX, d.TEST_IDX) == (2, 3)


def test_the_bar_is_v10s_verbatim():
    d = _driver()
    assert d.LOGLOSS_MIN_RELATIVE_GAIN == 0.01
    assert d.GUARD_TOLERANCE == 0.005


def test_there_are_two_arms_and_one_control():
    d = _driver()
    assert set(d.ARMS) == {"baseline", "role", "density"}
    assert d.ARMS["baseline"] == []


def test_the_verdict_keeps_only_on_both_halves():
    d = _driver()
    base = {"p_start_ll_starters": 0.5, "zeros": 1.0}
    assert d.verdict(base, {"p_start_ll_starters": 0.49,
                            "zeros": 1.002})["decision"] == "keep"
    # gain big enough, zeros cost too big
    assert d.verdict(base, {"p_start_ll_starters": 0.40,
                            "zeros": 1.010})["decision"] == "withdraw"
    # zeros fine, gain too small
    assert d.verdict(base, {"p_start_ll_starters": 0.4975,
                            "zeros": 1.000})["decision"] == "withdraw"


def test_coverage_refuses_a_window_with_no_training_rows():
    d = _driver()
    frame = pd.DataFrame({"season_idx": [3, 3], "role_wb_missing": [0.0, 0.0],
                          "density_pub_missing": [0.0, 0.0]})
    report = d.coverage(frame, ["role_wb_share", "density_pub_7d"])
    assert report["train_covered"] == 0
    with pytest.raises(SystemExit):
        d.check_coverage(report)


def test_coverage_accepts_a_window_with_training_rows():
    d = _driver()
    frame = pd.DataFrame({"season_idx": [2, 2, 3],
                          "role_wb_missing": [0.0, 1.0, 0.0],
                          "density_pub_missing": [0.0, 0.0, 0.0]})
    report = d.coverage(frame, ["role_wb_share", "density_pub_7d"])
    assert report["train_covered"] > 0
    d.check_coverage(report)   # does not raise


def test_the_lever_guard_refuses_an_arm_equal_to_the_control(monkeypatch):
    d = _driver()
    monkeypatch.setitem(d.ARMS, "role", [])
    with pytest.raises(SystemExit):
        d.check_lever(pd.DataFrame({"density_pub_7d": [0.0, 1.0]}))


def test_the_lever_guard_refuses_a_constant_column():
    d = _driver()
    frame = pd.DataFrame({"role_wb_share": [0.5, 0.5],
                          "role_wb_missing": [0.0, 0.0],
                          "density_pub_7d": [0.0, 1.0],
                          "density_pub_missing": [0.0, 0.0]})
    with pytest.raises(SystemExit):
        d.check_lever(frame)
```

Add `import pytest` at the top of `tests/test_v12_w4_features.py` if it is not
already there.

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q -k driver
# expected: 8 errors — FileNotFoundError: scripts/v12_w4_arms.py
```

### Step 10.2 — implementation

- [ ] Create `scripts/v12_w4_arms.py`:

```python
"""v12 W4 §5.2: the two new minutes arms, pre-registered.

**These are new arms and they are not the withdrawn congestion arm.**
``role_wb_share`` is a *positional* reading of a defender's last five starts,
which nothing in this project has ever had. ``density_pub_7d`` is a count of
*published* fixtures — a forward list — where v5's ``CONGESTION_FEATURES`` and
v8a's ``f2_cups`` counted *played* matches out of an archive that began in
2025-26. Different tables, different quantities, and the spec and the model
quality table say so.

The bar, from spec §5.2 ("the v10 rule") and v10 §F3a verbatim, stated before
any arm runs::

    KEEP iff  starters-slice p_start log-loss improves by >= 1% (relative)
              AND zeros RMSE does not get worse by more than GUARD_TOLERANCE

judged against the **control arm of this same run** and never against a banked
number (CONVENTIONS §1, §3).

**The window is shifted, deliberately.** ``evaluation`` ships
``BENCHMARK_TRAIN_MAX_IDX = 1`` / ``BENCHMARK_TEST_IDX = 2`` — train 2022-23 +
2023-24, test 2024-25. FPL-Core-Insights' earliest season is 2024-2025, so on
the shipped window both arms are null through the whole of training and the
only thing a fit could learn is "populated implies test season" — which is the
exact confound that withdrew v5's congestion features and made v8a's
``f2_league`` and ``f2_cups`` value-identical. This driver runs at
:data:`TRAIN_MAX_IDX` = 2 and :data:`TEST_IDX` = 3 (train 2022-23..2024-25,
test 2025-26), with the control on the same window. **The numbers here are
therefore not comparable to any banked benchmark figure**, which is why every
printed line carries the window.

**Four lever guards**, all before any arm is scored, because this repo has
produced a clean meaningless negative twice — v9c's rebound lever that was
bound rather than read, and v8a's ``f2_league``/``f2_cups`` pair that were two
lists with identical values on the window:

1. the arm's feature list differs from the control's;
2. every arm column exists on the training frame;
3. no arm column is entirely null or constant on the window;
4. **training coverage is non-zero**, printed per season — the guard this
   archive specifically needs.

Run it, watch it, read the verdicts::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_w4_arms.py > logs/v12_w4_arms.log 2>&1 &
    grep -e W4_ARM_LEVER -e W4_COVERAGE -e W4_ARM_DONE -e W4_VERDICT \\
        logs/v12_w4_arms.log
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.features.engineer import DENSITY_FEATURES, ROLE_FEATURES
from gaffer.models import train as tr

TRAIN_MAX_IDX = 2
TEST_IDX = 3
"""The shifted window. See the module docstring: the shipped
``BENCHMARK_TEST_IDX = 2`` puts every populated row in the test season and
makes both arms season indicators."""

LOGLOSS_MIN_RELATIVE_GAIN = 0.01
"""v10 §F3a's ">= 1%", read as a *relative* improvement — absolute would be
the wrong scale on a loss that sits around 0.3."""

GUARD_TOLERANCE = 0.005
"""v8a's guard, reused unchanged (``scripts/v8a_arms.py:36``). "Zeros RMSE not
worse" with no tolerance would withdraw an arm on solver noise."""

ARMS: dict[str, list[str]] = {
    "baseline": [],
    "role": list(ROLE_FEATURES),
    "density": list(DENSITY_FEATURES),
}
"""Two arms and one control, each arm's columns going in as a block: the share
and its missing indicator are one claim, and a withdrawal is a withdrawal of
the claim rather than of a column."""

ARM_COLS = ["role_wb_share", "density_pub_7d"]
"""The *value* columns, as opposed to the missing indicators. Coverage is
measured on these — an indicator is never null and would report 100%."""

_cached = None
_real_load = tr.load_training_frame


def _memoised():
    """One ``load_training_frame`` for the whole run, handed out as copies.

    ``scripts/v10_shrunk_arm.py:88-99``, verbatim in intent: the frame is the
    expensive half and cannot differ between arms by construction, and copies
    mean an arm that mutates its frame cannot poison the next one.
    """
    global _cached
    if _cached is None:
        _cached = _real_load()
    df, tg, elo = _cached
    return df.copy(), tg.copy(), elo


def arm_features(name: str) -> list[str]:
    return list(tr.MINUTES_FEATURES) + list(ARMS[name])


def coverage(df: pd.DataFrame, cols: list[str]) -> dict:
    """Non-null share of each arm column, per season, split train vs test.

    The number this archive makes necessary. ``train_covered`` counts rows at
    ``season_idx <= TRAIN_MAX_IDX`` where at least one arm column is
    populated; zero of them means every arm is a season indicator and no
    verdict below would mean anything.
    """
    idx = pd.to_numeric(df.get("season_idx"), errors="coerce")
    present = None
    per_season: dict[str, dict[str, float]] = {}
    for col in cols:
        series = pd.to_numeric(df.get(col), errors="coerce")
        if series is None:
            series = pd.Series(float("nan"), index=df.index)
        ok = series.notna()
        present = ok if present is None else (present | ok)
        for s in sorted(idx.dropna().unique()):
            rows = idx == s
            n = int(rows.sum())
            per_season.setdefault(str(int(s)), {})[col] = (
                round(float((ok & rows).sum()) / n, 4) if n else 0.0)
    if present is None:
        present = pd.Series(False, index=df.index)
    train = idx <= TRAIN_MAX_IDX
    test = idx == TEST_IDX
    return {"train_max_idx": TRAIN_MAX_IDX, "test_idx": TEST_IDX,
            "per_season": per_season,
            "train_rows": int(train.sum()),
            "train_covered": int((present & train).sum()),
            "test_rows": int(test.sum()),
            "test_covered": int((present & test).sum())}


def check_coverage(report: dict) -> None:
    """Lever guard 4. Exits rather than measuring a season indicator."""
    print("W4_COVERAGE", json.dumps(report), flush=True)
    if report["train_covered"] <= 0:
        raise SystemExit(
            "the arms are season indicators on this window: zero training "
            f"rows (season_idx <= {report['train_max_idx']}) carry either arm "
            "column, so every fit could learn is 'populated implies test "
            "season'. Run `gaffer core-insights` first, and if the archive "
            "still publishes nothing before the test season, the arms are not "
            "measurable and must be recorded as such rather than run.")
    if report["test_covered"] <= 0:
        raise SystemExit(
            "zero *test* rows carry either arm column, so both arms would "
            "predict the test season with a column that is null throughout "
            "it — a decorated zero.")


def check_lever(df: pd.DataFrame) -> None:
    """Lever guards 1-3 (``scripts/v10_shrunk_arm.py:107-133``)."""
    base = set(arm_features("baseline"))
    for name, cols in ARMS.items():
        if name == "baseline":
            continue
        if set(arm_features(name)) == base:
            raise SystemExit(
                f"the lever is disconnected: arm {name!r} builds the same "
                f"feature list as the control, so both sides would fit the "
                f"same model and every number below would be a zero with a "
                f"name on it.")
        for col in cols:
            if col not in df.columns:
                raise SystemExit(
                    f"{col} is not on the training frame — feature_columns() "
                    f"lists it but load_training_frame did not produce it.")
            series = pd.to_numeric(df[col], errors="coerce")
            if not series.notna().any():
                raise SystemExit(f"{col} is entirely null on this window.")
            if series.nunique(dropna=True) <= 1:
                raise SystemExit(
                    f"{col} is constant on this window — LightGBM will never "
                    f"split on it and the arm is the control by another name.")
    print("W4_ARM_LEVER ok", flush=True)


def run_arm(name: str) -> dict:
    """One fit, then the benchmark's own walk with the modes captured.

    A re-walk of ``evaluation.evaluate_benchmark``'s loop rather than a call to
    it, for ``v10_shrunk_arm``'s reason: the gate needs a ``p_start`` log-loss
    and a zeros RMSE off the *same* fitted model and the shipped function
    returns only the second. Every number is computed by shipped code; only
    the loop and the window are ours.
    """
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import predict_components_simple, train_all

    df, tg, _ = _memoised()
    train_df, test_df = ev.benchmark_split(df, TRAIN_MAX_IDX, TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, TRAIN_MAX_IDX, TEST_IDX)
    models = train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                       save=False)

    fitted = list(getattr(models["minutes"], "feature_cols", []))
    for col in ARMS[name]:
        if col not in fitted:
            raise SystemExit(
                f"arm {name!r} set MINUTES_FEATURES but the fitted model's "
                f"feature_cols does not contain {col} — the module global is "
                f"no longer the whole of the intervention (v9c's lesson).")

    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))
    ep_parts, mode_parts = [], []
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        rows = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if rows.empty:
            continue
        comp = predict_components_simple(models, rows)
        ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                         models.get("calibration")))
        truth = rows.groupby(["code", "gw"], as_index=False).agg(
            total_points=("total_points", "sum"), minutes=("minutes", "sum"))
        ep_parts.append(ep.merge(truth, on=["code", "gw"], how="inner"))
        modes = models["minutes"].predict_modes(rows)
        mode_parts.append(pd.DataFrame({
            "p_start": pd.to_numeric(modes["p_start"], errors="coerce").values,
            "minutes": pd.to_numeric(rows["minutes"], errors="coerce").values,
            "started": ev.start_truth(rows).values}))
        print(f"{name} (train<={TRAIN_MAX_IDX} test={TEST_IDX}) gw{gw}: "
              f"{len(ep_parts[-1])} rows", flush=True)

    if not ep_parts:
        raise SystemExit(
            f"the test window (season_idx {TEST_IDX}) has no rows — the "
            f"configured train_seasons do not reach it.")
    scored = pd.concat(ep_parts, ignore_index=True)
    heads = pd.concat(mode_parts, ignore_index=True)
    starters = heads[pd.to_numeric(heads["minutes"], errors="coerce")
                     .fillna(0.0) >= ev.STARTER_MINUTES]
    table = ev.stratified_metrics(scored["ep"], scored["total_points"])
    return {
        "train_max_idx": TRAIN_MAX_IDX, "test_idx": TEST_IDX,
        "zeros": table["zeros"]["rmse"], "zeros_n": table["zeros"]["n"],
        "haulers": table["haulers"]["rmse"], "all": table["all"]["rmse"],
        "p_start_ll_starters": round(
            float(ev.log_loss(starters["p_start"], starters["started"])), 5),
        "p_start_ll_all": round(
            float(ev.log_loss(heads["p_start"], heads["started"])), 5),
        "starters_n": int(len(starters)), "rows": int(len(heads)),
    }


def verdict(base: dict, arm: dict) -> dict:
    """The pre-registered rule, applied to one arm against the control."""
    b, a = base["p_start_ll_starters"], arm["p_start_ll_starters"]
    gain = (b - a) / b if b else 0.0
    zeros_cost = arm["zeros"] - base["zeros"]
    keep = gain >= LOGLOSS_MIN_RELATIVE_GAIN and zeros_cost <= GUARD_TOLERANCE
    return {"logloss_relative_gain": round(gain, 5),
            "zeros_cost": round(zeros_cost, 5),
            "decision": "keep" if keep else "withdraw"}


def main() -> None:
    tr.load_training_frame = _memoised
    shipped = list(tr.MINUTES_FEATURES)
    df, _tg, _elo = _memoised()
    check_coverage(coverage(df, ARM_COLS))
    check_lever(df)
    results: dict[str, dict] = {}
    try:
        for name in ARMS:
            # Restore the shipped list before composing: ``arm_features``
            # reads the module global, and without this the second arm would
            # silently inherit the first arm's columns.
            tr.MINUTES_FEATURES = shipped
            tr.MINUTES_FEATURES = arm_features(name)
            results[name] = run_arm(name)
            print("W4_ARM_DONE", name, json.dumps(results[name]), flush=True)
    finally:
        tr.MINUTES_FEATURES = shipped
        tr.load_training_frame = _real_load

    verdicts = {name: verdict(results["baseline"], results[name])
                for name in ARMS if name != "baseline"}
    for name, v in verdicts.items():
        print("W4_VERDICT", name, json.dumps(v), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v12_w4_arms.json").write_text(
        json.dumps({"window": {"train_max_idx": TRAIN_MAX_IDX,
                               "test_idx": TEST_IDX},
                    "arms": results, "verdicts": verdicts}, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] Run and watch the pure parts pass (**the driver itself is not run — that
  is the orchestrator's, CONVENTIONS §7**):

```bash
.venv/bin/pytest tests/test_v12_w4_features.py -q
# expected: 38 passed
```

- [ ] Commit:

```bash
git add scripts/v12_w4_arms.py tests/test_v12_w4_features.py
git commit -m "$(cat <<'EOF'
feat(w4): pre-registered driver for the two new minutes arms

v10 §F3a's bar verbatim, judged against this run's own control. The window is
shifted to train<=2 / test=3 deliberately: the archive's earliest season is
2024-25, which is the shipped benchmark's *test* season, so on the shipped
window both arms would be null through training and could only learn
"populated implies test season" — the confound that withdrew v5's congestion
features. A fourth lever guard measures training coverage per season and exits
rather than reporting a decorated zero.

Implementers do not run this (CONVENTIONS §7).

# v12 W4 §5.2 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — `scripts/v12_w4_autosub_cf.py`: the autosub-week counterfactual

**Why a second driver.** Spec §5.2 asks for "the v10 rule (autosub-week
counterfactual **and** bucket RMSE)". Task 10 is the bucket half. This is the
decision half, and it asks a different question: a better `p_play` is only
worth having if it changes a squad the real week then rewards. It mirrors
`scripts/v10_autosub_cf.py` — same `review.score_squad`, same real autosubs,
same restriction to weeks where an autosub actually fired — with one
difference: v10's two arms were two *solvers* on one model, and these two arms
are two *models* into one solver.

**Files**
- Create: `scripts/v12_w4_autosub_cf.py`

### Step 11.1 — implementation (no unit test; the driver is the instrument)

- [ ] Create `scripts/v12_w4_autosub_cf.py`:

```python
"""v12 W4 §5.2, the decision half: do the new arms earn points on autosub
weeks?

``scripts/v12_w4_arms.py`` measures the arms' *predictions*. This measures
whether a better ``p_play`` changes a squad that the real week then rewards,
which is the question the bucket RMSE cannot answer and the one spec §5.2
means by "the v10 rule … autosub-week counterfactual".

``scripts/v10_autosub_cf.py`` is the template and the differences are two.
There, both arms were the same fitted model into two solvers; here both arms
are two *fitted models* into the same solver, so the fit is inside the arm
loop and the memoised frame is the only thing shared. And the window is
:mod:`v12_w4_arms`' shifted one, for that module's reason — the archive's
earliest season is the shipped benchmark's test season.

The headline is restricted to **weeks where an autosub actually fired**: on
every other week the two arms score the same eleven and the delta is
structurally zero, so pooling would divide the real effect by however many
quiet weeks there were. Both numbers are printed; only the first is the gate.

**The lever guard**: before anything is scored, the driver asserts that the
two arms' ``p_play`` dicts actually differ on the first gameweek. If they do
not, both arms are the same arm and every delta is a decorated zero.

Run it, watch it, read the lines::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_w4_autosub_cf.py > logs/v12_w4_autosub_cf.log 2>&1 &
    grep -e W4_CF_LEVER -e W4_CF_GW -e W4_CF_DONE logs/v12_w4_autosub_cf.log
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import gaffer.evaluation as ev
from gaffer.backtest import STARTING_BUDGET, _players_frame
from gaffer.models import train as tr
from gaffer.optimize.milp import SolveInput, build_pool, solve_plan
from gaffer.review import score_squad

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "v12_w4_arms", Path(__file__).with_name("v12_w4_arms.py"))
arms_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(arms_mod)
"""The arm definitions and the window, loaded from the sibling driver rather
than copied. Two files disagreeing about which columns an arm is, is how a
cycle ends up reporting one arm's numbers under another arm's name."""

OPT_KW = dict(decay=0.9, bench_weight=0.1, vice_weight=0.1, ft_value=0.0,
              itb_value=0.0, hit_cost=4, ft_use_penalty=0.0,
              bench_curve=[0.21, 0.06, 0.002])
"""The solve every arm shares, ``scripts/v10_autosub_cf.py:56-58`` verbatim.

The ``bench_curve`` is required and is not read from ``config.toml``: with no
curve there are no bench-slot indicators and a better ``p_play`` has nothing
to move. ``ft_value``/``itb_value`` are zero and the horizon is one week
because every squad here is built from scratch — there is no next week to bank
a transfer for.
"""


def _p_play_by_code(comp: pd.DataFrame, gw: int) -> dict[int, dict[int, float]]:
    """``comp`` -> ``{code: {gw: p_play}}``.

    Grouped ``mean`` per ``(code, gw)``: "did he turn out at all" is one
    outcome, so a doubled-up player's probability is the mean of his fixtures
    and not their sum — ``news_shadow.shadow_rows``' rule, for its reason, and
    ``scripts/v10_autosub_cf.py:71-86`` verbatim.
    """
    grouped = (comp[comp["gw"] == int(gw)]
               .groupby("code", as_index=False)
               .agg(p_play=("p_play", "mean")))
    out: dict[int, dict[int, float]] = {}
    for row in grouped.itertuples():
        value = float(row.p_play)
        if value == value and 0.0 <= value <= 1.0:
            out[int(row.code)] = {int(gw): value}
    return out


def _autosub_fired(plan_gw, actuals: pd.DataFrame) -> bool:
    """Did at least one XI player record zero minutes with cover behind him?"""
    minutes = (actuals.groupby("code")["minutes"].sum()
               if not actuals.empty else pd.Series(dtype=float))
    blanks = [c for c in plan_gw.xi if float(minutes.get(c, 0.0)) <= 0.0]
    return bool(blanks) and bool(plan_gw.bench)


def _fit(arm: str, train_df, train_tg):
    """One arm's models, with ``MINUTES_FEATURES`` restored afterwards."""
    from gaffer.models.train import train_all

    shipped = list(tr.MINUTES_FEATURES)
    try:
        tr.MINUTES_FEATURES = arms_mod.arm_features(arm)
        return train_all(train_df, train_tg.dropna(subset=["elo_diff"]),
                         save=False)
    finally:
        tr.MINUTES_FEATURES = shipped


def main() -> None:
    from gaffer.assets import load_bootstrap_sample
    from gaffer.data.bootstrap import scoring_table
    from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
    from gaffer.models.train import (load_training_frame,
                                     predict_components_simple)

    df, tg, _ = load_training_frame()
    arms_mod.check_coverage(arms_mod.coverage(df, arms_mod.ARM_COLS))
    arms_mod.check_lever(df)

    train_df, test_df = ev.benchmark_split(df, arms_mod.TRAIN_MAX_IDX,
                                           arms_mod.TEST_IDX)
    train_tg, _ = ev.benchmark_split(tg, arms_mod.TRAIN_MAX_IDX,
                                     arms_mod.TEST_IDX)
    fits = {name: _fit(name, train_df, train_tg) for name in arms_mod.ARMS}
    scoring = ev.benchmark_scoring(scoring_table(load_bootstrap_sample()))

    rows: list[dict] = []
    levered = False
    for gw in sorted(int(g) for g in test_df["gw"].dropna().unique()):
        week = test_df[test_df["gw"] == gw].reset_index(drop=True)
        if week.empty:
            continue
        players = _players_frame(week, gw)
        picks = pd.DataFrame(columns=["code", "sell"])
        state = SolveInput(owned_codes=[], bank=STARTING_BUDGET,
                           free_transfers=15, gws=[gw])
        squads: dict[str, object] = {}
        p_plays: dict[str, dict] = {}
        failed = False
        for name, models in fits.items():
            comp = predict_components_simple(models, week)
            ep = ep_matrix(apply_calibration(assemble_ep(comp, scoring),
                                             models.get("calibration")))
            ep_by = {(int(r.code), int(r.gw)): float(r.ep)
                     for r in ep.itertuples()}
            pool = build_pool(players, ep_by, picks, [gw])
            p_plays[name] = _p_play_by_code(comp, gw)
            try:
                squads[name] = solve_plan(pool, state, **OPT_KW,
                                          p_play=p_plays[name]).gw_plans[0]
            except Exception as exc:  # noqa: BLE001 — one week is not the gate
                print(f"gw{gw}: {name} solve failed ({exc}) — week skipped",
                      flush=True)
                failed = True
                break
        if failed:
            continue

        if not levered:
            # Both arms would be the same arm if their p_play agreed, and
            # every delta below would be a decorated zero.
            same = all(p_plays[n] == p_plays["baseline"]
                       for n in arms_mod.ARMS if n != "baseline")
            if same:
                raise SystemExit(
                    "the lever is disconnected: every arm produced the same "
                    "p_play as the control on the first gameweek, so all "
                    "three squads are one squad.")
            print("W4_CF_LEVER ok", flush=True)
            levered = True

        # score_gw's contract (backtest.py:110): [code, total_points, minutes,
        # position], ONE row per player, double gameweeks already aggregated.
        actuals = (week.groupby("code", as_index=False)
                   .agg(minutes=("minutes", "sum"),
                        total_points=("total_points", "sum"),
                        position=("position", "first")))
        points = {name: score_squad(actuals, xi=plan.xi, bench=plan.bench,
                                    captain=plan.captain, vice=plan.vice,
                                    hits=0)
                  for name, plan in squads.items()}
        row = {"gw": gw, **{f"pts_{n}": points[n] for n in points},
               **{f"delta_{n}": points[n] - points["baseline"]
                  for n in points if n != "baseline"},
               "autosub": any(_autosub_fired(p, actuals)
                              for p in squads.values()),
               **{f"same_xi_{n}": sorted(squads[n].xi)
                  == sorted(squads["baseline"].xi)
                  for n in squads if n != "baseline"},
               **{f"bench_{n}": list(squads[n].bench) for n in squads}}
        rows.append(row)
        print("W4_CF_GW", json.dumps(row), flush=True)

    if not rows:
        raise SystemExit("no gameweek scored — nothing measured.")
    frame = pd.DataFrame(rows)
    fired = frame[frame["autosub"]]
    payload = {"window": {"train_max_idx": arms_mod.TRAIN_MAX_IDX,
                          "test_idx": arms_mod.TEST_IDX},
               "autosub_weeks": int(len(fired)), "all_weeks": int(len(frame))}
    for name in arms_mod.ARMS:
        if name == "baseline":
            continue
        payload[name] = {
            "autosub_mean_delta": (round(float(fired[f"delta_{name}"].mean()), 3)
                                   if not fired.empty else None),
            "all_mean_delta": round(float(frame[f"delta_{name}"].mean()), 3),
            "different_xi_weeks": int((~frame[f"same_xi_{name}"]).sum()),
            "different_bench_weeks": int(
                (frame[f"bench_{name}"].map(tuple)
                 != frame["bench_baseline"].map(tuple)).sum())}
    print("W4_CF_DONE", json.dumps(payload), flush=True)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/v12_w4_autosub_cf.json").write_text(
        json.dumps({"summary": payload, "per_gw": rows}, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] Verify it imports and its lever guard is reachable **without running the
  measurement**:

```bash
.venv/bin/python -c "
import importlib.util as u, pathlib
s = u.spec_from_file_location('cf', 'scripts/v12_w4_autosub_cf.py')
m = u.module_from_spec(s); s.loader.exec_module(m)
print('OPT_KW ok:', sorted(m.OPT_KW))
print('arms:', sorted(m.arms_mod.ARMS))
print('window:', m.arms_mod.TRAIN_MAX_IDX, m.arms_mod.TEST_IDX)"
# expected:
#   OPT_KW ok: ['bench_curve', 'bench_weight', 'decay', 'ft_use_penalty',
#               'ft_value', 'hit_cost', 'itb_value', 'vice_weight']
#   arms: ['baseline', 'density', 'role']
#   window: 2 3
```

- [ ] Commit:

```bash
git add scripts/v12_w4_autosub_cf.py
git commit -m "$(cat <<'EOF'
feat(w4): autosub-week counterfactual for the two new minutes arms

The decision half of spec 5.2's "v10 rule". v10's two arms were one model into
two solvers; these are two models into one solver, so the fit moves inside the
arm loop. Arm definitions and the shifted window are imported from
v12_w4_arms.py rather than copied — two files disagreeing about which columns
an arm is, is how a cycle reports one arm under another's name.

Implementers do not run this (CONVENTIONS §7).

# v12 W4 §5.2 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — `league_sim`: a synthetic field drawn from `deadline_eo`

**The model, and what it deliberately is not.** The field is *not* a set of
legal squads. Each synthetic manager is an **ownership vector**: for each
element, `own ~ Bernoulli(min(eo, 1))` with multiplier 1. That is a portfolio,
not a fifteen-man squad under a budget — no position limits, no three-per-club,
no bank. It is used because it is the object the EO actually describes: field
EO is already *effective* ownership, so the captain's doubling is folded in and
`sum_e eo_e ≈ 16` over a real sample, which is exactly the mass of eleven
starters plus an armband. What it buys is the thing that matters — every
manager's week is a weighted sum of *the same* player draws, so the correlation
between two managers is the shared-ownership correlation and not an assumption,
which is the same argument `field_exposures` (`league_sim.py:815-866`) makes for
the user's own squad.

What it costs is written down rather than papered over: a Bernoulli portfolio's
squad size varies where a real one does not, so the population's week is a
little wider than a real field's, which pushes `p_green` a shade toward 0.5.
Being wrong toward 0.5 is the direction `MEASURED_FIELD_CORRELATION`'s
docstring already argues for.

**`deadline_eo` is handed in, not read.** `league_sim` fetches nothing (its
module docstring is explicit: "not part of advice … the sigma table is read
through `scenarios`' public names and nothing else"). The router does the
reading and passes a `dict[int, float]`, which also means this task does not
depend on W2 §3.3 having landed — Task 14 prefers `field_eo_trend`'s
`deadline_eo` and falls back to `latest_field_eo`.

**Files**
- Modify: `src/gaffer/league_sim.py` (append, after `field_rate_from_sample`
  which ends at `:888`, before `build_inputs`)
- Create: `tests/test_v12_w4_rank.py`

### Step 12.1 — failing test

- [ ] Create `tests/test_v12_w4_rank.py`:

```python
"""v12 W4 §5.3: the synthetic field and what it can honestly report."""

from __future__ import annotations

import numpy as np
import pytest

from gaffer.league_sim import (Entry, FIELD_POP_N, SimInputs, field_population,
                               simulate_field_rank)


def _eo(elements, value=0.5) -> dict[int, float]:
    return {int(e): float(value) for e in elements}


def test_the_population_is_one_row_per_manager_per_element():
    masks = field_population(_eo(range(30)), n_managers=50, seed=1)
    assert masks.shape == (50, 30)
    assert set(np.unique(masks)) <= {0.0, 1.0}


def test_an_eo_of_one_is_owned_by_everybody():
    masks = field_population(_eo(range(10), 1.0), n_managers=20, seed=1)
    assert masks.sum() == 200


def test_an_eo_of_zero_is_owned_by_nobody():
    masks = field_population(_eo(range(10), 0.0), n_managers=20, seed=1)
    assert masks.sum() == 0


def test_an_eo_above_one_is_clamped_rather_than_raising():
    """Effective ownership exceeds 1 for a heavily captained player."""
    masks = field_population(_eo(range(5), 1.7), n_managers=10, seed=1)
    assert masks.sum() == 50


def test_the_population_is_deterministic_per_seed():
    a = field_population(_eo(range(40)), n_managers=30, seed=7)
    b = field_population(_eo(range(40)), n_managers=30, seed=7)
    c = field_population(_eo(range(40)), n_managers=30, seed=8)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_an_empty_eo_table_is_an_empty_population_not_a_crash():
    assert field_population({}, n_managers=50, seed=1).shape == (50, 0)


def test_the_default_population_matches_the_scrapes_sample_size():
    assert FIELD_POP_N == 300


# --- the headline --------------------------------------------------------

def _inputs(picks_elements, ep=4.0, sigma=3.0, elements=range(30)):
    picks = [{"element": int(e), "position": i + 1, "multiplier": 1,
              "is_captain": False, "is_vice_captain": False}
             for i, e in enumerate(picks_elements)]
    return SimInputs(
        entries=[Entry(entry=1, name="me", total=0, picks=picks, is_me=True)],
        ep_by_element={int(e): ep for e in elements},
        sigma_by_element={int(e): sigma for e in elements},
        weeks_left=10)


def test_a_squad_exchangeable_with_the_field_is_a_coin_flip():
    """Spec §5.3's sanity test. Thirty identical players at eo 0.5; the
    field's typical manager holds fifteen of them and so do I, so my week and
    his are the same random variable and P(green) must be a half."""
    out = simulate_field_rank(_inputs(range(11)), _eo(range(30)),
                              n=4000, seed=20260902, gw=6)
    assert 0.45 <= out["p_green"] <= 0.55


def test_owning_only_players_nobody_else_owns_still_answers():
    out = simulate_field_rank(_inputs(range(11)),
                              {int(e): 0.0 for e in range(30)},
                              n=1000, seed=1, gw=6)
    # Nobody in the field owns anything, so every rival scores zero and I do
    # not: a differential squad against an empty field wins every week.
    assert out["p_green"] == 1.0


def test_a_better_squad_is_greener():
    strong = _inputs(range(11))
    strong.ep_by_element = {int(e): (9.0 if e < 11 else 4.0)
                            for e in range(30)}
    out = simulate_field_rank(strong, _eo(range(30)), n=2000, seed=3, gw=6)
    assert out["p_green"] > 0.9


def test_the_run_is_deterministic_per_seed():
    a = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                            seed=11, gw=6)
    b = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                            seed=11, gw=6)
    assert a == b


def test_no_eo_table_is_an_empty_state_and_not_a_probability():
    out = simulate_field_rank(_inputs(range(11)), {}, n=500, seed=1, gw=6)
    assert out["p_green"] is None
    assert "field-scrape" in out["waiting_for"]


def test_a_squad_of_players_the_frame_does_not_carry_is_an_empty_state():
    out = simulate_field_rank(_inputs([900, 901]), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["p_green"] is None
    assert "no player in your squad" in out["waiting_for"]


def test_no_entry_flagged_as_mine_is_an_empty_state():
    ins = _inputs(range(11))
    ins.entries[0].is_me = False
    out = simulate_field_rank(ins, _eo(range(30)), n=500, seed=1, gw=6)
    assert out["p_green"] is None


def test_p_top10k_is_always_none_and_says_what_it_waits_for():
    """No top-10k weekly score series exists anywhere in this tree (plan A4).
    An honest null beats a number nobody can source."""
    out = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["p_top10k"] is None
    assert "top-10k weekly score" in out["top10k_waiting_for"]


def test_the_payload_carries_its_provenance():
    out = simulate_field_rank(_inputs(range(11)), _eo(range(30)), n=500,
                              seed=1, gw=6)
    assert out["n"] == 500 and out["seed"] == 1 and out["gw"] == 6
    assert out["managers"] == FIELD_POP_N
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_rank.py -q
# expected: collection error —
#   ImportError: cannot import name 'FIELD_POP_N' from 'gaffer.league_sim'
```

### Step 12.2 — implementation

- [ ] Insert into `src/gaffer/league_sim.py` immediately after
  `field_rate_from_sample` (which ends at `:888`) and before
  `def build_inputs`:

```python
FIELD_POP_N = 300
"""Synthetic managers in the field population.

The same size as the scrape's own sample (``tier_eo``'s ~300 top-10k entries),
so the Monte Carlo's population is not finer-grained than the measurement it
is drawn from. Three hundred is also enough that the population median moves
by well under a point between draws, which is what ``p_green`` is counted
against."""


def field_population(deadline_eo: dict[int, float], *,
                     n_managers: int = FIELD_POP_N,
                     seed: int = SIM_SEED):
    """``(n_managers, n_elements)`` of 0/1 ownership drawn from EO.

    Each synthetic manager owns element ``e`` with probability ``eo_e``,
    independently. This is a **portfolio, not a squad**: no budget, no
    position limits, no three-per-club, and a manager's holding count varies
    where a real one's does not.

    That is deliberate, and it is what the EO table actually describes. Field
    EO is *effective* ownership — the captain's doubling is already inside it
    — so over a real sample ``sum(eo)`` comes out near 16, which is eleven
    starters plus an armband. Drawing legal squads instead would need a
    solver per manager per gameweek and would buy a second-order correction to
    a first-order quantity.

    The cost, stated: a Bernoulli portfolio's week is a little wider than a
    real manager's, which pushes every probability counted off it a shade
    toward 0.5. That is the direction :data:`MEASURED_FIELD_CORRELATION`'s
    docstring already argues is the right one to be wrong in.

    An EO above 1 — a heavily captained player really does exceed 100%
    effective ownership — is clamped rather than rejected: he is owned by
    everybody, which is what an EO of 1.4 means once the doubling is stripped
    back out.
    """
    elements = sorted(int(e) for e in deadline_eo)
    if not elements:
        import numpy as _np
        return _np.zeros((int(n_managers), 0))
    probs = np.array([min(max(float(deadline_eo[e]), 0.0), 1.0)
                      for e in elements])
    rng = np.random.default_rng([int(seed), 1])
    draws = rng.random((int(n_managers), len(elements)))
    return (draws < probs).astype("float64")


TOP10K_WAITING = (
    "a top-10k weekly score threshold — no such series exists on this "
    "machine or in any source gaffer reads (build-history stores player and "
    "fixture tables only, and the events table carries no scores), so the "
    "probability is not computed rather than guessed")
"""What ``p_top10k`` is waiting for, said in full.

Spec §5.3 asks for ``P(top-10k)`` "using the historical distribution of
top-10k weekly scores by GW from ``build-history``". There is no such
distribution: ``build_history`` writes ``history/player_gw.parquet`` and
``history/fixtures.parquet`` and nothing event-level, and
``data/live/events.parquet`` carries no score column at all. The honest answer
is a null with this sentence beside it (spec §1: never render zeros as if they
were measurements)."""


def simulate_field_rank(inputs: SimInputs, deadline_eo: dict[int, float], *,
                        n: int = SIM_N, seed: int = SIM_SEED,
                        gw: int, n_managers: int = FIELD_POP_N) -> dict:
    """One gameweek against a synthetic field: ``P(green arrow)`` and friends.

    **Green arrow is defined against the population's own median week**, not
    against an absolute score: a green arrow is a rank that improved, and a
    rank improves when you beat the typical manager. Defining it this way is
    also what makes spec §5.3's sanity test exactly true rather than
    approximately — a squad exchangeable with the field's typical manager is
    the same random variable as him, so it beats him half the time.

    **Everybody is drawn off the same player weeks.** One ``(n, elements)``
    matrix of player outcomes serves my squad and all ``n_managers``, so the
    correlation between me and the field is the shared-ownership correlation
    and is not a parameter. Players are independent of one another within a
    week, which is this module's standing assumption
    (:data:`OUTCOME_VAR_PER_EP`'s docstring says what it omits).

    Returns a dict rather than a dataclass because two of its three headline
    numbers are ``None`` today and a dataclass would invite a caller to treat
    the nulls as zeros. Every null carries a ``waiting_for`` sentence.
    """
    elements = sorted(int(e) for e in deadline_eo)
    me = next((e for e in inputs.entries if e.is_me), None)
    base = {"gw": int(gw), "n": int(n), "seed": int(seed),
            "managers": int(n_managers), "p_green": None,
            "p_top10k": None, "top10k_waiting_for": TOP10K_WAITING,
            "waiting_for": None}
    if not elements:
        return {**base, "waiting_for":
                "a banked field EO sample for this gameweek — run "
                "`gaffer field-scrape`"}
    if me is None:
        return {**base, "waiting_for":
                "an entry flagged as yours in this league — set fpl.entry_id "
                "in config.toml"}
    picks = [(element, mult) for element, mult in effective_picks(me.picks)
             if element in deadline_eo]
    if not picks:
        return {**base, "waiting_for":
                "no player in your squad appears in the banked field sample, "
                "so there is nothing to compare against — the sample is from "
                "a different gameweek, or a different season's element ids"}
    index = {element: i for i, element in enumerate(elements)}
    eps = np.array([float(inputs.ep_by_element.get(e, 0.0)) for e in elements])
    sds = np.array([float(inputs.sigma_by_element.get(e, 0.0))
                    for e in elements])
    rng = np.random.default_rng([int(seed), 2])
    # One week of football, drawn n times: the same draws serve me and every
    # synthetic manager, which is what makes the correlation real.
    weeks = eps + sds * rng.standard_normal((int(n), len(elements)))
    masks = field_population(deadline_eo, n_managers=n_managers, seed=seed)
    field = weeks @ masks.T                       # (n, managers)
    mine = np.zeros(int(n))
    for element, mult in picks:
        mine += float(mult) * weeks[:, index[element]]
    median = np.median(field, axis=1)
    return {**base,
            "p_green": round(float((mine > median).mean()), 4),
            "field_median_ep": round(float(median.mean()), 2),
            "my_ep": round(float(mine.mean()), 2)}
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_v12_w4_rank.py -q
# expected: 17 passed
.venv/bin/pytest tests/ -q -k league_sim
# expected: the pre-existing league-sim suite, still green — nothing above
# touches simulate_league, multi_seed or entry_sigma
```

- [ ] Commit:

```bash
git add src/gaffer/league_sim.py tests/test_v12_w4_rank.py
git commit -m "$(cat <<'EOF'
feat(w4): a synthetic field drawn from deadline EO, and P(green arrow)

Each synthetic manager is an ownership portfolio rather than a legal squad,
because effective ownership is what the EO table describes and its mass
already comes out at eleven starters plus an armband. Everybody is drawn off
the same player weeks, so the correlation between me and the field is the
shared-ownership correlation and not a parameter.

Green is defined against the population's own median week, which is what makes
the spec's sanity test exactly true: a squad exchangeable with the typical
manager beats him half the time.

P(top-10k) returns null with the sentence saying why: no top-10k weekly score
series exists in this tree or in any source gaffer reads.

# v12 W4 §5.3 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — expected overall-rank change, and the empty state it ships in

**Why this is an empty state today, not a number.** Spec §5.3 asks for "the
user's expected overall-rank change". Turning a simulated score into a rank
change needs a points→rank response for the whole 11M-entry population, which
this project has never had. What it *does* have is the ledger's
`(my_points, overall_rank)` pair per graded gameweek (`review.py:728,738`) —
enough for a local slope once several rows exist. Two gameweeks are
`data_checked` today, so the honest ship is: compute it when there are at least
`RANK_SLOPE_MIN_ROWS`, and until then say "N of 5 graded gameweeks" out loud.

**Files**
- Modify: `src/gaffer/league_sim.py` (append)
- Modify: `tests/test_v12_w4_rank.py` (append)

### Step 13.1 — failing test

- [ ] Append to `tests/test_v12_w4_rank.py`:

```python
# --- Task 13: the rank slope --------------------------------------------

from gaffer.league_sim import RANK_SLOPE_MIN_ROWS, rank_slope


def test_five_rows_are_the_bar():
    assert RANK_SLOPE_MIN_ROWS == 5


def test_too_few_graded_gameweeks_is_a_named_empty_state():
    out = rank_slope([{"gw": 1, "my_points": 60, "overall_rank": 900000},
                      {"gw": 2, "my_points": 70, "overall_rank": 700000}])
    assert out["slope"] is None
    assert out["rows"] == 2
    assert "2 of 5 graded gameweeks" in out["waiting_for"]


def test_an_empty_ledger_is_a_named_empty_state():
    out = rank_slope([])
    assert out["slope"] is None
    assert "0 of 5 graded gameweeks" in out["waiting_for"]


def test_rows_missing_either_half_do_not_count():
    rows = [{"gw": g, "my_points": 60, "overall_rank": None}
            for g in range(1, 9)]
    assert rank_slope(rows)["rows"] == 0


def test_enough_rows_give_a_negative_slope_because_scoring_more_ranks_you_better():
    rows = [{"gw": g, "my_points": 40 + 10 * g,
             "overall_rank": 1_000_000 - 50_000 * g} for g in range(1, 7)]
    out = rank_slope(rows)
    assert out["slope"] is not None
    assert out["slope"] < 0
    assert out["waiting_for"] is None
    assert out["rows"] == 6


def test_a_ledger_with_no_variation_in_points_is_an_empty_state():
    """A slope through a vertical line is not a slope."""
    rows = [{"gw": g, "my_points": 60, "overall_rank": 900000 - g}
            for g in range(1, 8)]
    out = rank_slope(rows)
    assert out["slope"] is None
    assert "no variation" in out["waiting_for"]
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_rank.py -q -k "slope or graded or bar"
# expected: collection error —
#   ImportError: cannot import name 'RANK_SLOPE_MIN_ROWS'
```

### Step 13.2 — implementation

- [ ] Append to `src/gaffer/league_sim.py` (after `simulate_field_rank`):

```python
RANK_SLOPE_MIN_ROWS = 5
"""Graded gameweeks needed before a points-to-rank slope is worth quoting.

Five, and the number is a judgement rather than a fit: fewer and one
double-gameweek week dominates the line; more and the panel stays empty until
half the season is gone. It is stated here so a later reader moves it
deliberately."""


def rank_slope(ledger_rows: list[dict]) -> dict:
    """Overall-rank places per point, from the graded ledger, or an empty state.

    Spec §5.3 asks for an expected overall-rank change. Turning a simulated
    score into one needs a points-to-rank response over the whole eleven
    million entries, which this project has never had and does not acquire
    here. What the ledger does have is ``my_points`` beside ``overall_rank``
    for every graded gameweek (``review.py:728,738``), and the ordinary
    least-squares slope through those pairs is a **local** response — good
    enough to say "roughly this many places per point, on the weeks we have
    seen", and honest about being nothing more.

    ``None`` with a sentence in three cases, all of which a real machine is in
    today: too few graded gameweeks, rows missing either half, and a ledger
    whose points never vary (a slope through a vertical line is not a slope).
    """
    pairs = [(float(r["my_points"]), float(r["overall_rank"]))
             for r in ledger_rows or []
             if r.get("my_points") is not None
             and r.get("overall_rank") is not None]
    rows = len(pairs)
    if rows < RANK_SLOPE_MIN_ROWS:
        return {"slope": None, "rows": rows,
                "waiting_for": f"{rows} of {RANK_SLOPE_MIN_ROWS} graded "
                               f"gameweeks with both a score and an overall "
                               f"rank — run `gaffer review` as weeks finish"}
    points = np.array([p for p, _ in pairs])
    ranks = np.array([r for _, r in pairs])
    if float(points.std()) <= 0.0:
        return {"slope": None, "rows": rows,
                "waiting_for": "no variation in the graded scores yet, so "
                               "there is no slope to read through them"}
    slope = float(np.polyfit(points, ranks, 1)[0])
    return {"slope": round(slope, 1), "rows": rows, "waiting_for": None}
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_v12_w4_rank.py -q
# expected: 23 passed
```

- [ ] Commit:

```bash
git add src/gaffer/league_sim.py tests/test_v12_w4_rank.py
git commit -m "$(cat <<'EOF'
feat(w4): a local points-to-rank slope, and the empty state it ships in

Turning a simulated score into an overall-rank change needs a response curve
over eleven million entries, which this project has never had. The ledger has
my_points beside overall_rank per graded gameweek, and a least-squares slope
through those is a local response that says what it is. Two gameweeks are
graded today, so it ships saying "2 of 5" rather than saying a number.

# v12 W4 §5.3 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — serve the Field panel as additive fields on `/api/league/sim`

**No new route.** `GET /api/league/sim` already builds `SimInputs` (fifty
entry-picks fetches) and caches per advice run (`league_sim.py:122-138`'s
`_cache_key`, which already invalidates on the field sample's mtime). Adding a
route would mean a second cache and a second fetch storm. Route count stays 45.

**Where `deadline_eo` comes from.** W2 §3.3 lands `field_eo_trend` before this
workstream starts — program order is W1→W2→W3→W4→W5, confirmed by the
orchestrator (Appendix B §2) — so `deadline-trend` is the expected source on
any machine that has scraped, and that is the spec's intent for §5.3.

The fallback to `latest_field_eo` **stays, and is not dead code**: §3.3's own
contract returns no trend when only *one* sample has been banked for the
gameweek (`trend_available=False`), which is the state of every Saturday
before the Sunday scrape. So the three sources are all reachable —
`deadline-trend` with two samples, `last-sample` with one, `none` on a cold
clone. The `ImportError` guard around the import stays for the same reason a
degradation seam always does: it costs one line and it means a panel cannot
500 over a sibling module.

The payload names which source was used, because a trend-extrapolated EO and a
last-sample EO are different numbers and a panel that hid the difference would
be lying quietly.

**Files**
- Modify: `src/gaffer/web/schemas.py` (append one model; extend `LeagueSimData`)
- Modify: `src/gaffer/web/routers/league_sim.py`
- Modify: `tests/test_v12_w4_rank.py` (append)

### Step 14.1 — failing test

- [ ] Append to `tests/test_v12_w4_rank.py`:

```python
# --- Task 14: the payload ------------------------------------------------

from gaffer.web.schemas import FieldRank, LeagueSimData


def test_the_schema_carries_nullable_headlines_and_their_reasons():
    fields = FieldRank.model_fields
    for name in ("p_green", "p_top10k", "rank_slope"):
        assert fields[name].is_required() is False
    payload = FieldRank(gw=6, n=2000, seed=1, managers=300,
                        eo_source="last-sample")
    assert payload.p_green is None
    assert payload.p_top10k is None


def test_league_sim_data_gained_one_optional_field():
    assert "field" in LeagueSimData.model_fields
    assert LeagueSimData.model_fields["field"].is_required() is False


def test_the_route_count_did_not_move(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient  # noqa: F401  (import parity)

    from gaffer.web.app import create_app
    monkeypatch.chdir(tmp_path)
    assert len(create_app().openapi()["paths"]) == 45


def test_the_router_helper_prefers_the_trend_and_says_so(monkeypatch):
    from gaffer.web.routers import league_sim as router

    monkeypatch.setattr(router, "_trend_eo",
                        lambda *_a, **_k: ({7: 0.6}, "deadline-trend"))
    table, source = router.deadline_eo_table("2026-27", 6)
    assert table == {7: 0.6} and source == "deadline-trend"


def test_the_router_helper_falls_back_to_the_last_sample(monkeypatch):
    from gaffer.web.routers import league_sim as router

    monkeypatch.setattr(router, "_trend_eo", lambda *_a, **_k: ({}, ""))
    monkeypatch.setattr(router, "latest_field_eo",
                        lambda gw=None, *, season=None: {
                            9: {"eo": 0.4, "se": 0.0, "n": 300, "gw": 6}})
    table, source = router.deadline_eo_table("2026-27", 6)
    assert table == {9: 0.4} and source == "last-sample"


def test_the_router_helper_on_a_cold_clone_is_empty_and_named(monkeypatch):
    from gaffer.web.routers import league_sim as router

    monkeypatch.setattr(router, "_trend_eo", lambda *_a, **_k: ({}, ""))
    monkeypatch.setattr(router, "latest_field_eo",
                        lambda gw=None, *, season=None: {})
    assert router.deadline_eo_table("2026-27", 6) == ({}, "none")
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_rank.py -q -k "schema or payload or router or route_count"
# expected: collection error —
#   ImportError: cannot import name 'FieldRank' from 'gaffer.web.schemas'
```

### Step 14.2 — implementation

- [ ] Append to `src/gaffer/web/schemas.py`, immediately **above**
  `class LeagueSimData(BaseModel):` (line 199):

```python
class FieldRank(BaseModel):
    """v12 W4 §5.3. One gameweek against a synthetic field drawn from EO.

    Three headline numbers and two of them are ``None`` today. Each null has
    its own sentence rather than a shared one, because they are waiting for
    different things: ``p_green`` for a banked field sample, ``p_top10k`` for
    a score series that does not exist anywhere, ``rank_slope`` for graded
    gameweeks. Spec §1: a view whose data does not exist says what it is
    waiting for and never renders a zero as a measurement.
    """

    gw: int
    n: int
    seed: int
    managers: int
    eo_source: str
    """``"deadline-trend"`` (§3.3's extrapolation), ``"last-sample"`` (the
    newest scrape), or ``"none"``. A trend EO and a last-sample EO are
    different numbers and the panel says which it used."""
    p_green: float | None = None
    waiting_for: str | None = None
    p_top10k: float | None = None
    top10k_waiting_for: str | None = None
    rank_slope: float | None = None
    """Overall-rank places per point, from the graded ledger. Negative: more
    points is a better (smaller) rank."""
    rank_slope_rows: int = 0
    rank_waiting_for: str | None = None
    my_ep: float | None = None
    field_median_ep: float | None = None
```

- [ ] Add one field to `class LeagueSimData` (`schemas.py:199-217`), after
  `legacy_win_probability`:

```python
    field: FieldRank | None = None
    """v12 W4 §5.3's panel. ``None`` only when the simulation itself could not
    be built; an unanswerable question is a ``FieldRank`` full of nulls with
    their reasons, not an absent object."""
```

- [ ] In `src/gaffer/web/routers/league_sim.py`, add to the imports:

```python
from gaffer.data.field import field_sample_path, latest_field_eo
from gaffer.league_sim import (rank_slope, simulate_field_rank,  # noqa: F401
                               FIELD_POP_N)
from gaffer.web.schemas import FieldRank
```

(`field_sample_path` is already imported at `:134`; extend that line rather
than duplicating it.)

- [ ] Add to `src/gaffer/web/routers/league_sim.py`, above `def sim()`:

```python
def _trend_eo(season: str, gw: int) -> tuple[dict[int, float], str]:
    """W2 §3.3's deadline-extrapolated EO, or ``({}, "")`` when it is absent.

    Absent is a *routine* state, not a broken one: §3.3 only extrapolates when
    two samples have been banked for the gameweek, so every Saturday before
    the Sunday scrape lands here and falls back to the last sample. The import
    is inside the function and the except is broad because this is a display
    read on a page that already answers three other questions — a panel that
    500s over a sibling module is a panel nobody can review.
    """
    try:
        from gaffer.data.field import field_eo_trend
    except ImportError:
        return {}, ""
    try:
        frame = field_eo_trend(str(season), int(gw))
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}, ""
    if frame is None or getattr(frame, "empty", True):
        return {}, ""
    if not {"element", "deadline_eo"}.issubset(frame.columns):
        return {}, ""
    table = {int(r.element): float(r.deadline_eo)
             for r in frame.itertuples()
             if pd.notna(r.element) and pd.notna(r.deadline_eo)}
    return (table, "deadline-trend") if table else ({}, "")


def deadline_eo_table(season: str, gw: int) -> tuple[dict[int, float], str]:
    """``(element -> EO, source)`` for the field simulation.

    Prefers §3.3's deadline extrapolation and falls back to the newest banked
    sample. ``("none")`` on a machine that has never run ``field-scrape``,
    which :func:`gaffer.league_sim.simulate_field_rank` turns into its own
    named empty state rather than a probability.
    """
    table, source = _trend_eo(season, gw)
    if table:
        return table, source
    latest = latest_field_eo(int(gw), season=str(season))
    if latest:
        return ({int(e): float(cell.get("eo", 0.0))
                 for e, cell in latest.items()}, "last-sample")
    return {}, "none"


def _field_rank(cfg, inputs, gw: int) -> FieldRank:
    """v12 W4 §5.3's panel payload. Never raises — a display read on a page
    that already answers three other questions."""
    from gaffer.review import load_ledger

    season = str(getattr(cfg, "current_season", "") or "")
    table, source = deadline_eo_table(season, int(gw))
    out = simulate_field_rank(inputs, table, n=int(cfg.sim_n),
                              seed=SIM_SEED, gw=int(gw))
    try:
        slope = rank_slope(load_ledger())
    except Exception:  # noqa: BLE001 — an unreadable ledger is an empty one
        slope = {"slope": None, "rows": 0,
                 "waiting_for": "the decision ledger could not be read"}
    return FieldRank(
        gw=int(out["gw"]), n=int(out["n"]), seed=int(out["seed"]),
        managers=int(out["managers"]), eo_source=source,
        p_green=out["p_green"], waiting_for=out["waiting_for"],
        p_top10k=out["p_top10k"],
        top10k_waiting_for=out["top10k_waiting_for"],
        rank_slope=slope["slope"], rank_slope_rows=int(slope["rows"]),
        rank_waiting_for=slope["waiting_for"],
        my_ep=out.get("my_ep"), field_median_ep=out.get("field_median_ep"))
```

Add `import pandas as pd` and `from gaffer.league_sim import SIM_SEED` to the
module's imports if they are not already there.

- [ ] In `sim()`, add one keyword to the `LeagueSimData(...)` return
  (`league_sim.py:205-215`), as the last argument:

```python
        field=_field_rank(cfg, inputs, int(gw)),
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_v12_w4_rank.py -q
# expected: 29 passed
.venv/bin/pytest tests/ -q -k "league"
# expected: the pre-existing league suites, still green
```

- [ ] Commit:

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/league_sim.py \
        tests/test_v12_w4_rank.py
git commit -m "$(cat <<'EOF'
feat(w4): serve the Field panel on /api/league/sim, no new route

The endpoint already builds SimInputs and caches per advice run on a key that
already invalidates on the field sample's mtime; a second route would mean a
second cache and a second fifty-request fetch storm. The EO source is named in
the payload because a trend-extrapolated EO and a last-sample EO are different
numbers, and the trend reader is imported behind a guard so W4 is correct
whether or not W2 3.3 has landed on this branch.

# v12 W4 §5.3 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 15 — the League hub's Field panel

**Files**
- Create: `frontend/src/hubs/league/FieldPanel.tsx`
- Create: `frontend/src/hubs/league/FieldPanel.test.tsx`
- Modify: `frontend/src/hubs/League.tsx`
- Modify: `frontend/src/types.ts`

### Step 15.1 — failing test

- [ ] Create `frontend/src/hubs/league/FieldPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FieldPanel from './FieldPanel'
import type { FieldRank } from '../../types'

const base: FieldRank = {
  gw: 6, n: 2000, seed: 20260831, managers: 300, eo_source: 'last-sample',
  p_green: null, waiting_for: null,
  p_top10k: null, top10k_waiting_for: null,
  rank_slope: null, rank_slope_rows: 0, rank_waiting_for: null,
  my_ep: null, field_median_ep: null,
}

describe('FieldPanel', () => {
  it('renders the green-arrow probability when there is one', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.62, my_ep: 54.1,
                                field_median_ep: 51.3 }} />)
    expect(screen.getByText('62%')).toBeInTheDocument()
    expect(screen.getByText(/300 simulated managers/)).toBeInTheDocument()
    expect(screen.getByText(/last-sample/)).toBeInTheDocument()
  })

  it('says what it is waiting for instead of rendering a zero', () => {
    render(<FieldPanel field={{ ...base, waiting_for: 'a banked field EO sample for this gameweek — run `gaffer field-scrape`' }} />)
    expect(screen.queryByText('0%')).toBeNull()
    expect(screen.getByText(/gaffer field-scrape/)).toBeInTheDocument()
  })

  it('says why P(top-10k) is absent rather than omitting the row', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5,
                                top10k_waiting_for: 'a top-10k weekly score threshold' }} />)
    expect(screen.getByText(/top-10k weekly score threshold/)).toBeInTheDocument()
  })

  it('says how many graded gameweeks the rank slope still needs', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5, rank_slope_rows: 2,
                                rank_waiting_for: '2 of 5 graded gameweeks' }} />)
    expect(screen.getByText(/2 of 5 graded gameweeks/)).toBeInTheDocument()
  })

  it('renders the rank slope once it exists', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5, rank_slope: -18400,
                                rank_slope_rows: 6 }} />)
    expect(screen.getByText(/18,400 places per point/)).toBeInTheDocument()
  })

  it('renders nothing at all when the simulation could not be built', () => {
    const { container } = render(<FieldPanel field={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
```

- [ ] Run and watch it fail:

```bash
cd frontend && npx vitest run src/hubs/league/FieldPanel.test.tsx; cd ..
# expected: Failed to resolve import "./FieldPanel"
```

### Step 15.2 — implementation

- [ ] Add to `frontend/src/types.ts`:

```ts
export interface FieldRank {
  gw: number
  n: number
  seed: number
  managers: number
  eo_source: string
  p_green: number | null
  waiting_for: string | null
  p_top10k: number | null
  top10k_waiting_for: string | null
  rank_slope: number | null
  rank_slope_rows: number
  rank_waiting_for: string | null
  my_ep: number | null
  field_median_ep: number | null
}
```

and add `field: FieldRank | null` to the existing `LeagueSimData` interface.

- [ ] Create `frontend/src/hubs/league/FieldPanel.tsx`:

```tsx
import { Card } from '../../kit'
import type { FieldRank } from '../../types'

/**
 * v12 W4 §5.3. This gameweek against a synthetic field drawn from EO.
 *
 * Two of the three headline numbers are null today and each says what it is
 * waiting for. They are rendered as rows with their reasons rather than
 * hidden, because a row that vanishes is a question the reader stops asking.
 */
export default function FieldPanel({ field }: { field: FieldRank | null }) {
  if (field == null) return null
  const pct = (v: number) => `${Math.round(v * 100)}%`
  return (
    <Card title="Field">
      {field.p_green == null ? (
        <p className="text-sm text-muted">{field.waiting_for}</p>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl tabular-nums">{pct(field.p_green)}</span>
            <span className="text-sm text-muted">chance of a green arrow</span>
          </div>
          {field.my_ep != null && field.field_median_ep != null && (
            <p className="mt-1 text-sm text-muted tabular-nums">
              your week {field.my_ep.toFixed(1)} pts vs the field&rsquo;s median{' '}
              {field.field_median_ep.toFixed(1)}
            </p>
          )}
        </>
      )}

      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="text-muted">Top 10k this week</dt>
          <dd>
            {field.p_top10k == null
              ? <span className="text-muted">not computed — waiting for{' '}
                  {field.top10k_waiting_for ?? 'a score threshold'}</span>
              : <span className="tabular-nums">{pct(field.p_top10k)}</span>}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Overall rank response</dt>
          <dd>
            {field.rank_slope == null
              ? <span className="text-muted">not computed — waiting for{' '}
                  {field.rank_waiting_for ?? 'graded gameweeks'}</span>
              : <span className="tabular-nums">
                  {Math.abs(Math.round(field.rank_slope)).toLocaleString()}{' '}
                  places per point, over {field.rank_slope_rows} graded
                  gameweeks
                </span>}
          </dd>
        </div>
      </dl>

      <p className="mt-3 text-xs text-muted">
        {field.managers} simulated managers drawn from {field.eo_source} EO,
        n={field.n}, seed {field.seed}. The field is an ownership portfolio,
        not a legal squad.
      </p>
    </Card>
  )
}
```

- [ ] In `frontend/src/hubs/League.tsx`, import the panel and render it inside
  the same column as the win-probability card. Find the insertion point with

```bash
grep -n "Win probability" frontend/src/hubs/League.tsx
```

and add `<FieldPanel field={sim?.field ?? null} />` directly after the first
`<Card title="Win probability">…</Card>` block (the one at `:252`, in the
branch where `sim` is present), plus the import
`import FieldPanel from './league/FieldPanel'` beside the existing
`./league/RivalDetail` import.

- [ ] Run and watch both pass:

```bash
cd frontend && npx vitest run && cd ..
# expected: the pre-existing frontend suite plus 6 new tests, green
```

- [ ] Commit:

```bash
git add frontend/src/hubs/league/FieldPanel.tsx \
        frontend/src/hubs/league/FieldPanel.test.tsx \
        frontend/src/hubs/League.tsx frontend/src/types.ts
git commit -m "$(cat <<'EOF'
feat(w4): the League hub's Field panel

P(green arrow) with the week behind it, and two rows that say what they are
waiting for rather than disappearing — a row that vanishes is a question the
reader stops asking. The provenance line names the EO source, the population
size and the seed, and says out loud that the field is an ownership portfolio
rather than a legal squad.

# v12 W4 §5.3 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 16 — the set-piece override file and its loader

**TOML, not YAML** — see the Architecture note: `pyproject.toml` ships no
`pyyaml` and `import yaml` fails in `.venv`. `data/manager_tenures.toml` is the
existing precedent for a hand-edited override in this project and it is TOML.
**Accepted by the orchestrator on 2026-09-02 (Appendix B §3); `pyyaml` is not
added.**

**File placement.** The live file is `data/set_pieces.toml`, untracked (a new
`.gitignore` line). The example is a **package asset**,
`src/gaffer/assets/set_pieces.example.toml`, which keeps the staging rule
("never stage `data/`") intact and means a fresh clone or an installed wheel
carries the template.

**Files**
- Create: `src/gaffer/data/set_piece_overrides.py`
- Create: `src/gaffer/assets/set_pieces.example.toml`
- Modify: `src/gaffer/assets/__init__.py`
- Modify: `.gitignore`
- Create: `tests/test_set_piece_overrides.py`

### Step 16.1 — failing test

- [ ] Create `tests/test_set_piece_overrides.py`:

```python
"""The hand-edited set-piece override: what it can and cannot say."""

from __future__ import annotations

import pytest

from gaffer.data.set_piece_overrides import (OVERRIDE_PATH, SET_PIECE_KINDS,
                                             load_set_piece_overrides,
                                             penalty_order_overrides)


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def _write(clone, text: str):
    (clone / OVERRIDE_PATH).write_text(text)


def test_the_three_kinds_are_named_and_stable():
    assert SET_PIECE_KINDS == ("penalties", "direct_free_kicks", "corners")


def test_no_file_is_an_empty_override_not_a_crash(clone):
    assert load_set_piece_overrides() == {}
    assert penalty_order_overrides() == {}


def test_ordered_takers_become_one_based_orders(clone):
    _write(clone, """
[Arsenal]
penalties = [123, 456]
corners = [456]
""")
    out = load_set_piece_overrides()
    assert out["Arsenal"]["penalties"] == {123: 1, 456: 2}
    assert out["Arsenal"]["corners"] == {456: 1}
    assert out["Arsenal"]["direct_free_kicks"] == {}


def test_penalty_order_overrides_flattens_across_clubs(clone):
    _write(clone, """
[Arsenal]
penalties = [123, 456]

[Chelsea]
penalties = [789]
""")
    assert penalty_order_overrides() == {123: 1, 456: 2, 789: 1}


def test_a_malformed_file_is_an_empty_override_and_a_printed_line(clone,
                                                                  capsys):
    _write(clone, "this is not toml [[[")
    assert load_set_piece_overrides() == {}
    assert "set pieces:" in capsys.readouterr().out


def test_an_unknown_kind_is_ignored_rather_than_carried(clone):
    _write(clone, """
[Arsenal]
penalties = [1]
throw_ins = [2]
""")
    out = load_set_piece_overrides()
    assert set(out["Arsenal"]) == set(SET_PIECE_KINDS)


def test_a_non_integer_code_is_dropped_not_coerced(clone, capsys):
    _write(clone, """
[Arsenal]
penalties = [123, "Saka", 456]
""")
    assert load_set_piece_overrides()["Arsenal"]["penalties"] == {123: 1,
                                                                 456: 2}
    assert "not a player code" in capsys.readouterr().out


def test_a_duplicate_code_keeps_its_first_position(clone):
    _write(clone, """
[Arsenal]
penalties = [123, 456, 123]
""")
    assert load_set_piece_overrides()["Arsenal"]["penalties"] == {123: 1,
                                                                 456: 2}


def test_a_club_with_an_empty_list_says_nobody_takes_them(clone):
    """An empty list is a statement, not an absence: it is how a user says
    "the published taker has left and nobody has replaced him yet"."""
    _write(clone, """
[Arsenal]
penalties = []
""")
    out = load_set_piece_overrides()
    assert out["Arsenal"]["penalties"] == {}
    assert "Arsenal" in out


def test_the_shipped_example_parses_and_documents_all_three_kinds():
    from gaffer.assets import load_set_pieces_example

    text = load_set_pieces_example()
    for kind in SET_PIECE_KINDS:
        assert kind in text
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_set_piece_overrides.py -q
# expected: collection error —
#   ModuleNotFoundError: No module named 'gaffer.data.set_piece_overrides'
```

### Step 16.2 — implementation

- [ ] Create `src/gaffer/data/set_piece_overrides.py`:

```python
"""Who really takes them: the hand-edited override over FPL's own orders.

FPL's bootstrap publishes ``penalties_order``, ``direct_freekicks_order`` and
``corners_and_indirect_freekicks_order``, and it is often days behind the
manager's press conference and occasionally simply wrong. This is the one
place a user can say so, and the only knowledge in this project that comes
from watching football rather than from a feed.

**TOML rather than the spec's YAML.** ``pyproject.toml`` ships no YAML parser
and ``data/manager_tenures.toml`` is the existing precedent for a hand-edited
override here. ``tomllib`` is stdlib; a dependency for one file is a cost with
no buyer.

**The file is untracked and the example is a package asset.** ``data/`` is
never staged, so the template lives in ``gaffer.assets`` where a fresh clone
and an installed wheel both carry it.

**Only penalties reach expected points.** Free kicks and corners are surfaced
in the UI as context and get no EP term — ``set_pieces.py``'s scope note says
why, and this module does not widen it. What the other two kinds buy is the
"manual" badge, so a user who has corrected a corner taker can see that his
correction took.

Nothing here raises. A missing file, a malformed file and a file naming a club
that does not exist are all "no override", because a hand-edited file is
exactly the kind of thing that is half-edited at 11pm on a Friday.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

OVERRIDE_PATH = Path("data/set_pieces.toml")
"""Relative on purpose: read at call time against the working directory, the
way ``store.DATA_DIR`` is, so a test that redirects the data directory
redirects this too."""

SET_PIECE_KINDS = ("penalties", "direct_free_kicks", "corners")
"""The three tables the file may carry, in the order the UI shows them.

The names are the *user's* vocabulary rather than FPL's column names
(``corners_and_indirect_freekicks_order``): this file is typed by a person,
and a person should not have to spell "indirect" to name a corner."""


def load_set_piece_overrides(path: Path | str | None = None
                             ) -> dict[str, dict[str, dict[int, int]]]:
    """``{club: {kind: {code: 1-based order}}}``, or ``{}``.

    The file lists takers **in order**::

        [Arsenal]
        penalties = [118748, 232413]   # Saka, then Eze

    which is turned into ``{118748: 1, 232413: 2}`` — the same 1-based
    ``*_order`` shape the bootstrap uses, so a reader can substitute one for
    the other without learning a second convention.

    An empty list is a *statement* and is kept: it is how a user says "the
    published taker has left and nobody has replaced him". An unknown kind, a
    non-integer entry and a repeated code are each dropped with a printed
    line, because a silent drop in a file somebody typed by hand is a
    correction that never took and never said so.
    """
    target = Path(path) if path is not None else OVERRIDE_PATH
    if not target.is_file():
        return {}
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        print(f"set pieces: {target} could not be read ({exc}) — no overrides")
        return {}
    out: dict[str, dict[str, dict[int, int]]] = {}
    for club, tables in raw.items():
        if not isinstance(tables, dict):
            print(f"set pieces: {club!r} is not a club table — ignored")
            continue
        club_out: dict[str, dict[int, int]] = {k: {} for k in SET_PIECE_KINDS}
        for kind, takers in tables.items():
            if kind not in SET_PIECE_KINDS:
                print(f"set pieces: {club} names an unknown set piece "
                      f"{kind!r} — ignored (known: "
                      f"{', '.join(SET_PIECE_KINDS)})")
                continue
            if not isinstance(takers, list):
                print(f"set pieces: {club}.{kind} is not a list of player "
                      f"codes — ignored")
                continue
            order: dict[int, int] = {}
            for entry in takers:
                if not isinstance(entry, int) or isinstance(entry, bool):
                    print(f"set pieces: {club}.{kind} entry {entry!r} is not "
                          f"a player code — dropped")
                    continue
                if entry in order:
                    print(f"set pieces: {club}.{kind} names {entry} twice — "
                          f"keeping position {order[entry]}")
                    continue
                order[int(entry)] = len(order) + 1
            club_out[kind] = order
        out[str(club)] = club_out
    return out


def penalty_order_overrides(path: Path | str | None = None
                            ) -> dict[int, int]:
    """``{code: penalty order}`` across every club, for the EP term.

    Flattened across clubs because a player code is globally unique and the EP
    term never asks which club a code belongs to. A code named by two clubs —
    a mid-window transfer typed into both — keeps the first, and the file is
    small enough that a user can see which.
    """
    out: dict[int, int] = {}
    for club, tables in load_set_piece_overrides(path).items():
        for code, order in tables.get("penalties", {}).items():
            if code in out:
                print(f"set pieces: code {code} is named by more than one "
                      f"club ({club} is the later) — keeping the first")
                continue
            out[int(code)] = int(order)
    return out
```

- [ ] Create `src/gaffer/assets/set_pieces.example.toml`:

```toml
# Who really takes them. Copy to data/set_pieces.toml and edit.
#
# One table per club, named exactly as FPL's bootstrap names it ("Arsenal",
# "Man City", "Nott'm Forest", "Spurs"). Inside it, list takers in order by
# their gaffer *code* — the number in the URL of a player's explain panel, not
# his season element id, because element ids are remapped every summer and
# codes are not.
#
# Only `penalties` reaches expected points; `direct_free_kicks` and `corners`
# are context in the UI and are shown with a "manual" badge where you have
# overridden them.
#
# An empty list is a statement, not an absence: it says "the published taker
# has left and nobody has replaced him", and the model will price nobody.

# [Arsenal]
# penalties = [118748, 232413]         # Saka, then Eze
# direct_free_kicks = [232413]
# corners = [232413, 118748]

# [Liverpool]
# penalties = [118748]
# corners = []
```

- [ ] Append to `src/gaffer/assets/__init__.py`:

```python
SET_PIECES_EXAMPLE = "set_pieces.example.toml"


def load_set_pieces_example() -> str:
    """The bundled ``data/set_pieces.toml`` template, as text.

    Shipped in the package rather than under ``data/`` because ``data/`` is
    never staged and a fresh clone must still carry the template. The *live*
    file is ``data/set_pieces.toml``, untracked, because it is one user's
    knowledge about one season and belongs to nobody else's clone.
    """
    return files(__package__).joinpath(SET_PIECES_EXAMPLE).read_text(
        encoding="utf-8")
```

- [ ] Append one line to `.gitignore`, after the `config.toml` line:

```
data/set_pieces.toml
```

- [ ] Run and watch it pass:

```bash
.venv/bin/pytest tests/test_set_piece_overrides.py -q
# expected: 10 passed
```

- [ ] Commit:

```bash
git add src/gaffer/data/set_piece_overrides.py \
        src/gaffer/assets/set_pieces.example.toml \
        src/gaffer/assets/__init__.py .gitignore \
        tests/test_set_piece_overrides.py
git commit -m "$(cat <<'EOF'
feat(w4): a hand-edited set-piece override, in TOML

The spec says YAML; there is no YAML parser in this project and
data/manager_tenures.toml is the existing precedent for a hand-edited override
here, so it is TOML read with stdlib tomllib. The live file is untracked and
the template ships as a package asset, which keeps "never stage data/" intact
while a fresh clone still carries it.

Every rejection prints: a silent drop in a file somebody typed by hand is a
correction that never took and never said so.

# v12 W4 §5.4 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 17 — **STOP.** Protected edit: `set_pieces.py`'s read hook

> ### 🛑 STOP — do not write anything in this task until the orchestrator has
> read the enumeration below and authorized it.
>
> `src/gaffer/set_pieces.py` is protected. Spec §5.4 authorizes "one read
> hook" here. This task is that hook and **nothing else in this file moves**.

**Why an `advise.py` edit is not the alternative.** `pen_table` is the only
place `penalties_order` is read into an EP term (`set_pieces.py:295-297`), and
its only caller is `advise.py:455,458` — protected, and §5.4 authorizes no
line-group there. Threading an `overrides=` parameter would therefore need an
unauthorized `advise.py` edit. Applying the override earlier, in
`bootstrap.build_players`, would write manual values into
`data/live/players.parquet`, which exists to record what FPL said. The hook
inside `pen_table` is the only option that leaves both alone.

**Why the docstring moves too.** `set_pieces.py:40-41` currently reads
"Nothing here does I/O, loads a model or touches the network. Everything is
handed in." After this edit that is false. A protected file whose docstring
has stopped describing it is worse than the I/O, so the sentence is amended in
the same authorized edit rather than left standing. **The orchestrator ruled on
2026-09-02 (Appendix B §4) that this second line-group is inside spec §5.4's
"one read hook" authorization**, on the plan's own reasoning: a hook shipping
under a false docstring would itself be a defect. **Both line-groups are
written together or neither is** — a run that applies only the code half has
left the file in the state the ruling exists to prevent.

### Line-group 1 — `src/gaffer/set_pieces.py:40-41` (the module docstring)

**Before:**

```python
Nothing here does I/O, loads a model or touches the network. Everything is
handed in.
```

**After:**

```python
Nothing here loads a model or touches the network, and everything the caller
knows is handed in. One exception, added in v12: :func:`pen_table` reads
``data/set_pieces.toml`` for the user's manual taker overrides. It is read
here rather than threaded through because the only caller is ``advise.py``,
which is protected, and because writing manual values into
``data/live/players.parquet`` would corrupt a file whose job is to record what
FPL said. The read is lazy, is behind
:func:`gaffer.data.set_piece_overrides.penalty_order_overrides`' own
never-raises contract, and returns ``{}`` on every machine that has not
written the file — which is byte-identical to the pre-v12 behaviour.
```

### Line-group 2 — `src/gaffer/set_pieces.py:295-297` (the read itself)

**Before:**

```python
    order_of = dict(zip(players["code"],
                        pd.to_numeric(players["penalties_order"],
                                      errors="coerce")))
```

**After:**

```python
    order_of = dict(zip(players["code"],
                        pd.to_numeric(players["penalties_order"],
                                      errors="coerce")))
    # v12 W4 §5.4 (specs/2026-09-01-gaffer-v12-program-design.md). The user's
    # hand-edited file beats the bootstrap, per club and per player, and an
    # absent file is an empty dict — so a machine that has never written one
    # takes exactly the branch it took before v12.
    from gaffer.data.set_piece_overrides import penalty_order_overrides

    order_of.update(penalty_order_overrides())
```

**Nothing else in `set_pieces.py` changes.** After the edit,

```bash
git diff --stat src/gaffer/set_pieces.py
# expected: 1 file changed, ~14 insertions(+), 2 deletions(-)
git diff -U0 src/gaffer/set_pieces.py | grep '^[-+]' | grep -v '^[-+][-+]'
# expected: only the two line-groups above
```

### Step 17.1 — failing test

- [ ] Create `tests/test_v12_w4_set_pieces.py`:

```python
"""The set-piece override's one read hook, and the rail it must not break."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.set_pieces import PenPriors, pen_table

COMP = pd.DataFrame({"code": [1, 2], "team_code": [3, 3],
                     "position": ["MID", "MID"], "p_play": [0.9, 0.9]})
PLAYERS = pd.DataFrame({"code": [1, 2], "name": ["A", "B"],
                        "penalties_order": [1, None]})
PRIORS = PenPriors(share_hist={}, league_pens_pg=0.13, team_games=100)


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def test_no_override_file_is_byte_identical_to_before(clone):
    """The rail. Every machine is in this state until someone writes one."""
    table = pen_table(COMP, PLAYERS, PRIORS)
    assert table["share_now"].tolist() == [1.0, 0.0]


def test_an_override_moves_the_armband(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [2, 1]\n")
    table = pen_table(COMP, PLAYERS, PRIORS)
    assert table["share_now"].tolist() == [0.15, 1.0]


def test_an_override_naming_nobody_in_the_frame_changes_nothing(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [999]\n")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]


def test_a_malformed_override_file_changes_nothing(clone):
    (clone / "data" / "set_pieces.toml").write_text("not toml [[[")
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]


def test_an_empty_list_removes_the_published_taker(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = []\n")
    # Nobody is named, so nobody is overridden and the bootstrap stands. An
    # empty list says "the published taker left"; saying so about a player the
    # file does not name is not something this hook can do, and pretending
    # otherwise would need the club column it deliberately does not read.
    assert pen_table(COMP, PLAYERS, PRIORS)["share_now"].tolist() == [1.0, 0.0]
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_set_pieces.py -q
# expected: 1 failed, 4 passed —
#   test_an_override_moves_the_armband:
#   AssertionError: assert [1.0, 0.0] == [0.15, 1.0]
```

### Step 17.2 — implementation

- [ ] Apply line-group 1 and line-group 2 exactly as enumerated above.

- [ ] Run and watch it pass, and confirm the protected file moved only there:

```bash
.venv/bin/pytest tests/test_v12_w4_set_pieces.py -q
# expected: 5 passed
.venv/bin/pytest tests/test_advise.py tests/test_set_pieces.py -q
# expected: green — the no-file path is byte-identical
git diff --stat src/gaffer/set_pieces.py
# expected: 1 file changed, 14 insertions(+), 2 deletions(-)
```

- [ ] Commit:

```bash
git add src/gaffer/set_pieces.py tests/test_v12_w4_set_pieces.py
git commit -m "$(cat <<'EOF'
feat(w4): one authorized read hook in set_pieces.py for manual takers

Authorized by spec 5.4. Two line-groups: the read itself in pen_table, and the
module docstring's no-I/O sentence, amended in the same edit because a
protected file whose docstring has stopped describing it is worse than the I/O.

Threading a parameter instead would need an advise.py line-group 5.4 does not
authorize, and applying the override in build_players would write manual values
into a file whose job is to record what FPL said.

An absent file is an empty dict, so every machine that has not written one
takes exactly the pre-v12 branch.

# v12 W4 §5.4 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 18 — the "manual" badge, on the row and in the explain panel

**Files**
- Modify: `src/gaffer/web/schemas.py` (`PlayerRow` at `:433`; `PlayerExplain`'s
  `set_pieces` at `:523`)
- Modify: `src/gaffer/web/routers/players.py` (`:186-189`, `:340-343`)
- Modify: `frontend/src/hubs/players/ComparePanel.tsx` or wherever the
  set-piece flags render (locate below)
- Modify: `frontend/src/types.ts`
- Create: `tests/test_v12_w4_badge.py`

### Step 18.1 — failing test

- [ ] Create `tests/test_v12_w4_badge.py`:

```python
"""The manual badge: where a set-piece override applied, and only there."""

from __future__ import annotations

import pytest

from gaffer.web.routers.players import set_piece_manual


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    return tmp_path


def test_no_override_file_marks_nobody(clone):
    assert set_piece_manual() == {}


def test_every_named_code_is_marked_with_the_kinds_it_was_named_for(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = [1, 2]\ncorners = [2]\n")
    assert set_piece_manual() == {1: ["penalties"],
                                  2: ["corners", "penalties"]}


def test_a_malformed_file_marks_nobody(clone):
    (clone / "data" / "set_pieces.toml").write_text("[[[")
    assert set_piece_manual() == {}


def test_the_kinds_are_sorted_so_the_badge_is_stable(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\ncorners = [1]\npenalties = [1]\ndirect_free_kicks = [1]\n")
    assert set_piece_manual()[1] == ["corners", "direct_free_kicks",
                                     "penalties"]


def test_an_empty_list_marks_nobody_because_it_names_nobody(clone):
    (clone / "data" / "set_pieces.toml").write_text(
        "[Arsenal]\npenalties = []\n")
    assert set_piece_manual() == {}


def test_the_row_schema_carries_the_kinds(clone):
    from gaffer.web.schemas import PlayerRow

    assert "set_piece_manual" in PlayerRow.model_fields
    assert PlayerRow.model_fields["set_piece_manual"].is_required() is False


def test_the_route_count_did_not_move(clone):
    from gaffer.web.app import create_app

    assert len(create_app().openapi()["paths"]) == 45
```

- [ ] Run and watch it fail:

```bash
.venv/bin/pytest tests/test_v12_w4_badge.py -q
# expected: collection error —
#   ImportError: cannot import name 'set_piece_manual'
```

### Step 18.2 — implementation

- [ ] Add to `src/gaffer/web/routers/players.py`, above the row-building
  function that contains `:186-189`:

```python
def set_piece_manual() -> dict[int, list[str]]:
    """``{code: [kinds the user overrode]}`` — the badge, and nothing else.

    A display fact. It never enters an expected point: only ``penalties``
    reaches EP at all (through ``set_pieces.pen_table``'s hook), and this map
    exists so a user who corrected a corner taker can see that his correction
    took. Kinds are sorted so the badge does not reshuffle between reloads.

    An empty list in the file names nobody and therefore marks nobody — which
    is right: the badge says "this row is your correction", and a row nobody
    was named for is not.
    """
    from gaffer.data.set_piece_overrides import load_set_piece_overrides

    out: dict[int, set[str]] = {}
    for tables in load_set_piece_overrides().values():
        for kind, order in tables.items():
            for code in order:
                out.setdefault(int(code), set()).add(str(kind))
    return {code: sorted(kinds) for code, kinds in sorted(out.items())}
```

- [ ] In `src/gaffer/web/schemas.py`, add to `class PlayerRow` (near `:433`):

```python
    set_piece_manual: list[str] = Field(default_factory=list)
    """Kinds of set piece this player's order came from ``data/set_pieces.toml``
    rather than from FPL. Empty on every machine with no override file."""
```

- [ ] In `src/gaffer/web/routers/players.py`, hoist the map once per request
  above the row loop:

```python
    # v12 W4 §5.4. Once per request, not once per row: the file is small but
    # it is a disk read, and a hundred players is a hundred reads.
    manual = set_piece_manual()
```

and add to the `PlayerRow(...)` construction at `:186-189`, after
`corners_order=…`:

```python
            set_piece_manual=manual.get(code, []),
```

- [ ] In `src/gaffer/web/schemas.py`, change `class PlayerExplain`'s
  `set_pieces` field (`:523`) from

```python
    set_pieces: dict[str, int | None]
```

to

```python
    set_pieces: dict[str, int | None]
    set_pieces_manual: list[str] = Field(default_factory=list)
    """Which of ``set_pieces``' three orders came from the user's override
    file. Additive and default-empty, so a client that does not read it is
    unaffected."""
```

- [ ] In `src/gaffer/web/routers/players.py`, add to the `PlayerExplain(...)`
  return at `:335-343`, after the `set_pieces={…}` argument:

```python
        set_pieces_manual=set_piece_manual().get(code, []))
```

- [ ] Locate where the set-piece flags render on the client and add the badge:

```bash
grep -rn "penalties_order\|corners_order\|free_kicks_order" frontend/src \
  | grep -v test
```

At each row-level render site, add beside the existing pen/set-piece flag:

```tsx
{p.set_piece_manual.length > 0 && (
  <Badge tone="info" title={`Your override: ${p.set_piece_manual.join(', ')}`}>
    manual
  </Badge>
)}
```

using the existing `Badge` import from `../../kit`. Add
`set_piece_manual: string[]` to the `PlayerRow` interface in
`frontend/src/types.ts`, and `set_pieces_manual: string[]` to `PlayerExplain`.

- [ ] Run and watch both pass:

```bash
.venv/bin/pytest tests/test_v12_w4_badge.py -q
# expected: 7 passed
cd frontend && npx vitest run && cd ..
# expected: green
```

- [ ] Commit:

```bash
git add src/gaffer/web/routers/players.py src/gaffer/web/schemas.py \
        frontend/src/types.ts tests/test_v12_w4_badge.py
git add frontend/src/hubs/players/ComparePanel.tsx   # plus any other render
                                                     # site the grep found
git commit -m "$(cat <<'EOF'
feat(w4): a "manual" badge where a set-piece override applied

A display fact and never an expected point — only penalties reach EP, and this
map exists so a user who corrected a corner taker can see that it took. Read
once per request rather than once per row, and empty on every machine with no
override file.

# v12 W4 §5.4 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 19 — degradation rails, block 2: §5.2, §5.3 and §5.4

**Files**
- Modify: `tests/test_v12_w4_degradation.py` (append; the file Task 6 created,
  which is this cycle's own and therefore not protected)

### Step 19.1 — the test is the deliverable

- [ ] Append to `tests/test_v12_w4_degradation.py`:

```python
# --- Block 2: §5.2's features on a machine with no collection ------------

def test_the_arms_are_all_missing_and_never_zero_without_a_collection(clone):
    """The state every machine is in until `gaffer core-insights` runs.
    Missing, not zero: zero would claim we know the defender never crosses and
    the club plays nothing that week."""
    from gaffer.features.engineer import add_density_pub, add_role_wb_share

    rows = pd.DataFrame({"season_idx": [3], "gw": [6], "code": [1],
                         "team_code": [8], "position": ["DEF"],
                         "kickoff_time": [pd.Timestamp("2026-10-10T14:00Z")]})
    out = add_density_pub(add_role_wb_share(rows, None), None)
    assert out["role_wb_share"].isna().all()
    assert out["density_pub_7d"].isna().all()
    assert out["role_wb_missing"].tolist() == [1.0]
    assert out["density_pub_missing"].tolist() == [1.0]


def test_the_arms_are_wired_but_fed_to_no_head(clone):
    """CONVENTIONS §2: pre-registered means off until the gate says on."""
    from gaffer.features.engineer import (DENSITY_FEATURES, ROLE_FEATURES,
                                          feature_columns)
    from gaffer.models.train import MINUTES_FEATURES

    for name in ROLE_FEATURES + DENSITY_FEATURES:
        assert name in feature_columns()
        assert name not in MINUTES_FEATURES


# --- Block 2: §5.3 on a cold clone ---------------------------------------

def test_the_field_panel_on_a_cold_clone_is_nulls_with_reasons(clone):
    from gaffer.league_sim import Entry, SimInputs, simulate_field_rank

    ins = SimInputs(entries=[Entry(entry=1, name="me", total=0, picks=[],
                                   is_me=True)],
                    ep_by_element={}, sigma_by_element={}, weeks_left=10)
    out = simulate_field_rank(ins, {}, n=100, seed=1, gw=6)
    assert out["p_green"] is None and out["waiting_for"]
    assert out["p_top10k"] is None and out["top10k_waiting_for"]


def test_the_rank_slope_on_a_cold_clone_names_its_condition(clone):
    from gaffer.league_sim import rank_slope

    out = rank_slope([])
    assert out["slope"] is None
    assert "0 of 5 graded gameweeks" in out["waiting_for"]


def test_the_field_simulation_reaches_no_solver_and_no_advice(clone):
    """league_sim's standing rail (its module docstring, spec D4): nothing
    here is part of advice."""
    import inspect

    from gaffer import league_sim

    src = inspect.getsource(league_sim.simulate_field_rank)
    for forbidden in ("solve_plan", "run_advise", "coherent_plan", "milp"):
        assert forbidden not in src


def test_the_existing_league_simulation_is_untouched_by_the_new_one(clone):
    """§5.3 extends the module and changes nothing in it."""
    import numpy as np

    from gaffer.league_sim import Entry, SimInputs, simulate_league

    picks = [{"element": e, "position": i + 1, "multiplier": 1,
              "is_captain": i == 0, "is_vice_captain": i == 1}
             for i, e in enumerate(range(1, 12))]
    ins = SimInputs(
        entries=[Entry(entry=1, name="me", total=100, picks=picks,
                       is_me=True),
                 Entry(entry=2, name="rival", total=90, picks=picks)],
        ep_by_element={e: 4.0 for e in range(1, 12)},
        sigma_by_element={e: 3.0 for e in range(1, 12)}, weeks_left=5)
    a = simulate_league(ins, n=500, seed=42)
    b = simulate_league(ins, n=500, seed=42)
    assert a.p_win == b.p_win
    assert np.isfinite(a.exp_finish)


# --- Block 2: §5.4's byte-identical no-file rail -------------------------

def test_no_override_file_leaves_the_penalty_term_exactly_as_it_was(clone):
    import pandas as pd

    from gaffer.set_pieces import PenPriors, pen_table

    comp = pd.DataFrame({"code": [1], "team_code": [3], "position": ["MID"],
                         "p_play": [0.9]})
    players = pd.DataFrame({"code": [1], "name": ["A"],
                            "penalties_order": [1]})
    table = pen_table(comp, players,
                      PenPriors(share_hist={}, league_pens_pg=0.13,
                                team_games=100))
    assert table["share_now"].tolist() == [1.0]


def test_a_half_edited_override_file_is_no_override_at_all(clone):
    """A hand-edited file is exactly the kind of thing that is half-edited at
    11pm on a Friday, and half a file must never be half a model."""
    import pandas as pd

    from gaffer.data.set_piece_overrides import penalty_order_overrides

    (clone / "data" / "set_pieces.toml").write_text("[Arsenal]\npenalties = [1,")
    assert penalty_order_overrides() == {}


def test_the_badge_is_empty_without_a_file(clone):
    from gaffer.web.routers.players import set_piece_manual

    assert set_piece_manual() == {}
```

- [ ] Run:

```bash
.venv/bin/pytest tests/test_v12_w4_degradation.py -q
# expected: 22 passed
```

- [ ] Run the whole suite once, both sides:

```bash
.venv/bin/pytest tests/ -q
# expected: the pre-existing count plus this cycle's new tests, all green
cd frontend && npx vitest run && cd ..
# expected: green
```

- [ ] Commit:

```bash
git add tests/test_v12_w4_degradation.py
git commit -m "$(cat <<'EOF'
test(w4): degradation rails for the arms, the field sim and the override

Every rail is the state a machine is in today: no collection (so both arms are
missing rather than zero), no field sample (so the panel is nulls with their
reasons), no graded gameweeks (so the rank slope says "0 of 5"), and no
override file (so the penalty term is byte-identical to pre-v12). Plus the
standing rail that the field simulation reaches no solver.

# v12 W4 §5.2-5.4 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 20 — ROADMAP, the model quality table, and the docs

**Files**
- Modify: `docs/superpowers/ROADMAP.md`
- Modify: `src/gaffer/models/train.py` (the `MINUTES_FEATURES` docstring only)
- Modify: `docs/GUIDE.md`

### Step 20.1 — implementation

- [ ] Add to `docs/superpowers/ROADMAP.md`, in the data-gated section (find it
  with `grep -n "^- \[ \]" docs/superpowers/ROADMAP.md | head -20` and match
  the surrounding format):

```markdown
- [ ] **W4 §5.3 `P(top-10k)`** — unblocked by a top-10k weekly score
  threshold series. None exists: `build-history` writes player and fixture
  tables only, `data/live/events.parquet` carries no scores, and
  FPL-Core-Insights' `gameweek_summaries.csv` has `average_entry_score` and
  `highest_score` but no tier threshold. Needs either a new scrape of the
  top-10k standings' weekly points, or 38 weeks of banking the field sample's
  own realised scores.
- [ ] **W4 §5.3 expected overall-rank change** — unblocked by 5 graded
  gameweeks carrying both `my_points` and `overall_rank` in
  `reports/decision_ledger.json`. Two are graded today (GW1, GW2).
- [ ] **W4 §5.2 arm verdicts** — unblocked by an orchestrator run of
  `scripts/v12_w4_arms.py` and `scripts/v12_w4_autosub_cf.py` after a
  `gaffer core-insights` collection. The arms are built and fed to no head
  until then.
- [ ] **W4 §5.1 Elo for 2026-27** — unblocked by the publisher filling in the
  archive's `elo` column for the current season; it is blank today, in
  `teams.csv` and on every fixture row, so `elo.parquet` is legitimately
  empty and the health line says so.
```

- [ ] Append to the `MINUTES_FEATURES` docstring in
  `src/gaffer/models/train.py` (the quality-table paragraph, after the v10 G1
  block that ends the docstring):

```
v12 W4 §5.2 adds two arms, **new and distinct from the withdrawn congestion
arm**. ``role_wb_share`` is a positional reading of a defender's last five
starts from FPL-Core-Insights' per-match stats, which nothing in this project
has ever had. ``density_pub_7d`` counts *published* fixtures in the seven days
before kickoff — a forward list — where v5's ``CONGESTION_FEATURES`` and v8a's
``f2_cups`` counted *played* matches out of a cup archive that begins in
2025-26. Different tables, different quantities.

Both are measured on a **shifted window**, ``train_max_idx = 2`` /
``test_idx = 3``, because the archive's earliest season (2024-25) is the
shipped benchmark's *test* season and on the shipped window both columns are
null through the whole of training — the exact confound that withdrew v5's
congestion features. Driver: ``scripts/v12_w4_arms.py`` (bucket half) and
``scripts/v12_w4_autosub_cf.py`` (decision half). Bar (v10 §F3a verbatim, spec
§5.2's "the v10 rule"): keep only if the starters-slice ``p_start`` log-loss
improves by >= 1% relative with zeros RMSE not worse by more than 0.005.
Numbers, ship-or-withdraw, and the coverage report go here when the
orchestrator has run them.
```

- [ ] Add a `docs/GUIDE.md` section documenting `data/set_pieces.toml` — where
  to copy the template from (`src/gaffer/assets/set_pieces.example.toml`),
  that codes are gaffer codes and not element ids, that only penalties reach
  EP, and that the "manual" badge is how you check a correction took. Place it
  beside the existing manual-override / watchlist documentation (find it with
  `grep -n "override\|manual" docs/GUIDE.md | head`).

- [ ] Commit:

```bash
git add docs/superpowers/ROADMAP.md src/gaffer/models/train.py docs/GUIDE.md
git commit -m "$(cat <<'EOF'
docs(w4): four data-gated checkboxes, the arm registration, and the override

Each checkbox names the condition that unblocks it rather than a date: a
top-10k score threshold that exists nowhere, five graded gameweeks against
today's two, an orchestrator arm run, and a publisher filling in an Elo column.

The MINUTES_FEATURES docstring registers both arms as new and distinct from
the withdrawn congestion arm, and records the shifted window and its reason
before any number exists.

# v12 W4 §5.1-5.4 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 21 — the gate checklist (results unfilled)

**Implementers do not run these.** CONVENTIONS §7: the orchestrator runs the
gates. This task writes the checklist into the spec and leaves every result
blank.

**Files**
- Modify: `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md`
  (append a `### W4 gate results` block under §5)

### Step 21.1 — write the checklist

- [ ] Append to the spec, under §5, immediately before `## 6. W5 — interface`:

```markdown
### W4 gate results

**G1 — collector degradation.** `.venv/bin/pytest tests/test_v12_w4_degradation.py
tests/test_core_insights.py -q`. Rails: repo unreachable (and no truncation of
a previous collection), unknown column added, expected column removed, key
column removed, empty season, blank Elo column, cross-season read, torn
parquet, cold-clone health line.

- Result: _(unfilled)_

**G2 — §5.2 arm outcomes, recorded either way (CONVENTIONS §6).** Requires a
`gaffer core-insights` collection first, then

```bash
mkdir -p logs && caffeinate -i nohup .venv/bin/python \
    scripts/v12_w4_arms.py > logs/v12_w4_arms.log 2>&1 &
grep -e W4_COVERAGE -e W4_ARM_LEVER -e W4_ARM_DONE -e W4_VERDICT \
    logs/v12_w4_arms.log
```

Bar (pre-registered, v10 §F3a verbatim): keep an arm iff starters-slice
`p_start` log-loss improves ≥ 1% relative against **this run's control** and
zeros RMSE is not worse by more than 0.005. **The coverage line is part of the
result**: if `train_covered` is 0 the driver exits and the honest record is
"not measurable on any window the archive covers", not a withdrawal.

- Coverage (`W4_COVERAGE`): _(unfilled)_
- `role`: _(unfilled)_
- `density`: _(unfilled)_
- Decision, per arm: _(unfilled)_

**G3 — §5.2 decision half.**

```bash
mkdir -p logs && caffeinate -i nohup .venv/bin/python \
    scripts/v12_w4_autosub_cf.py > logs/v12_w4_autosub_cf.log 2>&1 &
grep -e W4_CF_LEVER -e W4_CF_DONE logs/v12_w4_autosub_cf.log
```

Rule: the mean delta over weeks where an autosub actually fired must not
regress. Read as the small sample it is — one season, fresh squads weekly, a
per-week tendency and not a season total.

- Autosub weeks / mean delta per arm: _(unfilled)_

**G4 — §5.3 sanity.** `.venv/bin/pytest tests/test_v12_w4_rank.py -q`. The
named check is
`test_a_squad_exchangeable_with_the_field_is_a_coin_flip` — spec §5.3's "a
squad identical to the field's modal team has P(green) ≈ 0.5", implemented as
an exchangeability test at n=4000, tolerance ±0.05.

- Result: _(unfilled)_

**G5 — suite green, both sides.**

```bash
.venv/bin/pytest tests/ -q
cd frontend && npx vitest run && cd ..
```

- Python: _(unfilled)_ · Frontend: _(unfilled)_

**G6 — zero unauthorized protected diffs.**

```bash
git diff --stat main...HEAD -- \
  src/gaffer/advise.py src/gaffer/optimize src/gaffer/web/jobs.py \
  src/gaffer/web/routers/whatif.py tests/test_advise.py tests/test_odds.py \
  tests/test_web_jobs.py scripts/s2_replay.py \
  $(git ls-files 'tests/test_*_degradation.py' | grep -v v12_w4)
# expected: empty

git diff -U0 main...HEAD -- src/gaffer/set_pieces.py \
  | grep '^[-+]' | grep -v '^[-+][-+]'
# expected: exactly Task 17's two line-groups, and the provenance comment
#   # v12 W4 §5.4 (specs/2026-09-01-gaffer-v12-program-design.md)
```

- Result: _(unfilled)_

**G7 — pins.**

```bash
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# expected: 45 12 48
```

- Result: _(unfilled)_

**Post-merge ritual (spec §7).**

```bash
git show main:config.toml     # expected: fatal — path does not exist
git log -S"$(grep -o 'odds_api_key.*' config.toml | head -1)" --all
# expected: empty
```

- Result: _(unfilled)_
```

- [ ] Commit:

```bash
git add docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md
git commit -m "$(cat <<'EOF'
docs(w4): the W4 gate checklist, results unfilled

Implementers build the drivers and do not run them (CONVENTIONS §7). G2's
coverage line is part of the result: if the archive covers no training season,
the honest record is "not measurable on any window the archive covers", not a
withdrawal.

# v12 W4 (specs/2026-09-01-gaffer-v12-program-design.md)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Appendix B — orchestrator rulings (2026-09-02), and what they settle

All four questions this plan raised are **answered**. Nothing below is open;
the implementer follows the plan as written and does not re-litigate any of it.

1. **Shifted arm window — AUTHORIZED.** Task 10 runs at `train_max_idx = 2`,
   `test_idx = 3`. The coverage guard (`check_coverage`) is **kept as the exit
   path**: if the archive still covers no training season when the driver runs,
   it exits and G2's honest record is "not measurable on any window the archive
   covers", not a withdrawal. Do not weaken the guard to make the run complete.
2. **W2 lands before W4 — CONFIRMED.** Program order is W1→W2→W3→W4→W5, so
   `field_eo_trend` exists on the branch by the time Task 14 runs and §5.3 uses
   §3.3's `deadline_eo` as the spec intends. Task 14's `ImportError` guard
   **stays** — it is no longer "in case W2 slipped" but a genuine degradation
   seam, because `field_eo_trend` itself returns no trend when only one sample
   has been banked for the gameweek. The expected `eo_source` on a scraped
   machine is `deadline-trend`; `last-sample` is the one-sample fallback and
   `none` is the cold clone.
3. **TOML — ACCEPTED.** No `pyyaml`. `data/set_pieces.toml` and
   `src/gaffer/assets/set_pieces.example.toml` stand as written in Task 16.
4. **Task 17's docstring line-group — COVERED** by spec §5.4's "one read hook"
   authorization. The ruling's reasoning is the plan's own: a hook shipping
   under a docstring that says the module does no I/O would itself be a defect.
   Both line-groups are written together or neither is.

**Program-wide ruling — no new `[solver]` config section.** Any solver knob
goes in the existing `[optimizer]` section, which is splatted into `Config`.
**This does not touch W4**: this workstream adds no config key at all (the
`fields(Config)` pin stays 48 — see "Why no `[core_insights] enabled` key" in
the header), reads no `[solver]` key, and writes nothing to
`config.example.toml`. Recorded here so a later reader can see the ruling was
checked against this plan rather than skipped. If any task somehow grows a
config need during execution, it goes in `[optimizer]` and **STOPs first**,
because the `Config` pin moving is itself a protected-test edit.
