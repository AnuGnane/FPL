# v17c — the golden board harness

Programme: `docs/superpowers/plans/2026-09-07-v17-deepening-programme.md`
§v17c. Branch `v17c-golden-board` off `main` at `88707c7` (v17b's docs
commit; merge hash `b1b3b7e`). No review card: this sub-cycle builds the
gate that v17d, v17e, v17f and v17g are measured against.

## 0. Why

Every refactor left in the programme is supposed to change no number the
advice serves. v17b tried to prove that with two live `gaffer advise` runs
minutes apart and found one player's expected points moved by 0.01 between
them, because the FPL feeds moved (tracker, v17b hand-off). A "no diff"
verdict therefore needs an input that cannot move. `run_advise(cfg,
client)` already takes the client as an argument, but only one adapter has
ever been behind that seam, the live `FPLClient`; a second one, a client
that replays recorded responses, makes the seam real and gives the four
refactors a board that is byte-identical run to run.

The recorded client is not the whole story. `run_advise` reads more than
the FPL API: the training archive under `data/history/`, the Core Insights
role tables under `data/core_insights/`, the models under `models/`, and,
through `serving_config()`, the `config.toml` in the working directory —
`ladder.py` takes the hit bar, the caps and the ladder seed from there, not
from the `cfg` it was passed. The harness has to freeze each of these, or
name the ones it cannot and skip honestly when they move.

## 1. Gate, stated before anything runs (CONVENTIONS §2, §7, §10)

Run by the orchestrator on the branch after the suites are green. All five
must hold:

1. **Twice green, same bytes.** `.venv/bin/pytest -q tests/test_golden_board.py`
   passes twice in succession from a clean checkout of the branch with the
   golden files untouched and the same `models/` and `data/history/` on
   disk. The comparison is exact: the advice JSON and the solve-state JSON
   the run wrote, against `tests/data/golden_board/expected/`, after
   `generated_at` is removed from both and every string value that starts
   with the run's working directory is replaced by `<cwd>`. No tolerance
   on any float.
2. **The lever was exercised.** The header's `levers` block, computed from
   the expected advice at record time and re-computed from the run's
   advice at test time, has every count at or above its floor:
   `restraint_steps_taken >= 1`, `restraint_steps_refused >= 1`,
   `objective_hits >= 1`, `chip_rows >= 1`, `league_lam != 0`,
   `bench == 4` with a `vice` present, `plan_weeks == 6`. The test asserts
   these on the run's advice, so a future refactor that empties one of them
   fails here rather than passing an emptier board.
3. **The skip rule is exercised in both directions.** With the `models/` and
   `data/history/` files matching the header's SHA-256 map, the test runs;
   with one hash changed in a copy of the header, the test skips and its
   reason names the file. Both are unit tests in `tests/test_golden_board.py`
   over the helper, not a manual step.
4. **Size.** `du -sk tests/data/golden_board` is under 5 MB (5120 KB).
5. **Security.** The CLAUDE.md extraction of `[odds] api_key` followed by
   `grep -rc "$V" tests/data/golden_board tests/golden_client.py
   tests/test_golden_board.py` prints only zeros; the recorded `config.toml`
   has no `[odds]` table (`grep -c '^\[odds\]' tests/data/golden_board/config.toml`
   prints 0); `python -c` reading the header confirms
   `config.odds_api_key == ""`.

Also required, not part of the verdict rule: `.venv/bin/pytest -q` green
with the new tests counted; `cd frontend && npx tsc --noEmit && npx vitest run`
unchanged (this sub-cycle touches no frontend file); the runtime of one
golden run recorded in §10.

Verdict: pass if all five hold on the first full run after the
implementation is complete. A failure is fixed on the branch and the gate
is rerun in full; §10 records every run. If the levers cannot all be made
to fire on the gameweek available at record time, §4 of the programme
applies: nothing merges, the numbers go in §10, and the tracker's hand-off
note says which lever would not fire and at what caps.

## 2. The decisions the grilling settled

1. **Record at `_get`, not per method.** `FPLClient` funnels its twelve
   endpoints through one private `_get(path, snapshot)`. `RecordedClient`
   subclasses `FPLClient` and overrides only `_get`, so every public method
   the pipeline calls today or gains later is covered by the same
   dictionary lookup, keyed by the API path string. `RecordingClient` is
   the same override the other way round: it calls the parent, then banks
   the body under the path. A path that was not recorded raises
   `KeyError` naming it; the recorded client never opens a socket. Neither
   writes `data/raw/` snapshots (the parent's `snapshot=` is ignored), so a
   golden run leaves no dump behind.
2. **One bundle.** `tests/data/golden_board/responses.json.gz` maps path to
   body for every call the recording made: one bootstrap, one fixtures
   list, 654 element summaries, the entry's picks, transfers and history,
   the league pages, every rival's picks and history. Measured on the live
   API on 2026-09-08: a summary gzips to about 1.6 KB, the bootstrap to
   160 KB, so the bundle is about 1.3 MB. Bodies are stored whole, not
   trimmed to the fields `history_to_rows` reads: the recording is the
   response, and a later reader of `fixtures` or `history_past` must not
   find the golden lying.
3. **`config.toml` is part of the golden.** `serving_config()` is read in
   `ladder.py` (hit bar, caps, seed), `artifacts.py`, `models/availability.py`,
   `news_shadow.py` and `pen_tracker.py`, from whatever `config.toml` sits
   in the working directory, and it is `lru_cache`d for the process. The
   harness therefore runs `run_advise` in a scratch working directory that
   holds a `config.toml` written from `golden_config()` by
   `write_golden_toml`, clears `serving_config`'s cache before and after,
   and asserts `load_config()` in that directory equals `golden_config()`
   field for field. That round trip pins the writer. The file is also
   committed under `tests/data/golden_board/config.toml` so a person can
   `cd` there and read it. It has no `[odds]` table. v17e collapses these
   hidden reads into one interface; until then this is the one honest way
   to hold them still. Patching every module's imported name was rejected
   as a list that goes stale silently.
4. **The scratch tree.** `tmp/models` is a symlink to the repo's `models/`;
   `tmp/data/history` a symlink to the repo's `data/history/`;
   `tmp/data/core_insights` a *copy* of the fixture's; `tmp/data/manager_tenures.toml`
   a copy of the tracked file; `tmp/config.toml` written; `tmp/reports/`
   empty. Nothing else. `data/live/`, `data/snapshots/`, `reports/` are
   created by the run inside `tmp`, so the user's own `data/` and
   `reports/` are never touched by a test.
5. **Core Insights are frozen in the fixture, not hashed.** The current
   season's table under `data/core_insights/2026-27/` is rewritten twice a
   day by the collector (CONVENTIONS §1), so hashing it would make the
   golden skip most of the week. The three season directories are 388 KB
   together and are copied into `tests/data/golden_board/data/core_insights/`
   at record time. `data/history/` (3.3 MB, unchanged since 2026-08-25, and
   over the budget) and `models/` (14 MB) are the two inputs that stay on
   the machine, and they are the two the header hashes.
6. **Skip, never fail, when a hashed input moved.** The header's `inputs`
   map holds the SHA-256 of every file under `models/` and `data/history/`
   at record time. At test time each is re-hashed; a missing file or a
   different digest skips the whole module with a reason naming the first
   such file. This is the programme's rule extended from the models to the
   archive, because a re-ingested `player_gw.parquet` invalidates the
   golden exactly as a retrain does. A file that exists on disk but not in
   the map is ignored: the golden pins what it used, not the directory.
7. **The seed the ladder reads is the seed the config wrote.** Because
   `build_ladder` takes `scenarios_seed` from `serving_config()` and
   `run_scenarios` takes it from `cfg`, the two agree only because both
   read the same value; `golden_config()` sets `scenarios_seed = 20260825`
   (the dataclass default) and the TOML carries it explicitly.
8. **Nothing is monkeypatched inside the pipeline** except
   `gaffer.data.live.time.sleep`, which `refresh_live` calls 654 times for
   politeness to a server the recorded client never contacts. Everything
   else runs as `gaffer advise` would.
9. **The compared files are the advice and the solve state.** The ladder
   JSON is built from the solve state and echoed into `advice.restraint`
   and `advice.objective`, so a change in it is visible in the advice; the
   components parquet and the availability parquet are not compared
   (floats in parquet, and v17g records at the `Inputs` level anyway).
10. **Recording and re-recording are one module with two flags.**
    `python -m tests.golden_client --record` fetches live through
    `RecordingClient`, writes the bundle, then runs the golden once to
    write `expected/` and the header. `python -m tests.golden_client
    --write` reruns the golden over the *existing* bundle and rewrites
    `expected/` and the header's hashes and levers: this is the retrain
    path, and the hand-off note says so. Both refuse to run unless the
    working directory is the repo root.
11. **In the default suite, marked.** The test is collected by
    `.venv/bin/pytest -q`; it is the gate and a hidden gate is not run. It
    carries `@pytest.mark.golden`, registered in `pyproject.toml`, so a
    fast local loop can pass `-m "not golden"`. The runtime is measured at
    record time and written into §10; if it exceeds three minutes the plan
    records that and nothing else changes.

## 3. Approach, and the two rejected

**Chosen: a recorded client plus a frozen working directory.** The seam is
the one `run_advise` has; the working directory is the second, implicit
seam that `serving_config()` and every relative `Path("data")` create, and
the harness treats it as one by building it whole.

**Rejected: record at the `Inputs` level now.** That is v17g's job; it needs
`build_advice` to be a pure function first, and doing it here would touch
`advise.py`, which this sub-cycle may not edit.

**Rejected: hash Core Insights and skip on drift.** Twice-daily skips would
make the gate unrunnable on the days it is needed.

## 4. The interface

All in `tests/golden_client.py`. Nothing under `src/` changes.

```python
GOLDEN_DIR = Path(__file__).parent / "data" / "golden_board"

class RecordedClient(FPLClient):
    """The second adapter behind ``run_advise(cfg, client)`` (v17c §2.1)."""
    def __init__(self, directory: Path = GOLDEN_DIR): ...
    def _get(self, path: str, snapshot: str | None = None): ...
        # returns a deep copy of the recorded body; KeyError(path) if absent

class RecordingClient(FPLClient):
    def __init__(self, directory: Path, **client_kw): ...
    def _get(self, path, snapshot=None): ...   # live fetch, then bank
    def save(self) -> Path: ...                 # writes responses.json.gz

def golden_config() -> Config: ...             # the literal, see below
def write_golden_toml(cfg: Config, path: Path) -> None: ...
def build_scratch_tree(root: Path, repo: Path, golden: Path = GOLDEN_DIR) -> None: ...
def input_hashes(repo: Path) -> dict[str, str]: ...   # models/**, data/history/**
def stale_inputs(header: dict, repo: Path) -> list[str]: ...  # [] when fresh
def strip_volatile(obj, cwd: str): ...          # generated_at out, <cwd> in
def lever_counts(advice: dict) -> dict[str, int | float | bool]: ...
def run_golden(root: Path, repo: Path) -> tuple[dict, dict]: ...  # (advice, state)
```

`golden_config()` returns a `Config` built from literals, never from
`config.toml`: `entry_id = 2210493`, `league_id = 1794743` (public FPL
identifiers, already in the repo's reports), `horizon = 6`,
`decay = 0.85`, `vice_weight = 0.1`, `bench_weight = 0.10`, `ft_value = 1.5`,
`itb_value = 0.08`, `ft_use_penalty = 0.2`, `bench_curve = [0.21, 0.06, 0.002]`,
`hit_cost = 4`, `scenarios_n = 40`, `scenarios_seed = 20260825`,
`decision_priors = True`, `draw_availability` at its default,
`news_enabled = False`, `odds_api_key = ""`, `player_props` at the loader's default (unreachable without a key, and unwritable without an `[odds]` table),
`stance = "auto"`, the league parameters at their defaults,
`train_seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]`,
`current_season = "2026-27"`, and the three lever knobs `max_hits`,
`max_transfers`, `hit_bar`. The knobs start at `2`, `15` and `0.60`, the
values the last live run took a step and refused one under; the
orchestrator moves them at record time only if a lever does not fire, and
the values that shipped are in the header and §10.

The header, `tests/data/golden_board/header.json`:

```json
{
  "recorded_at": "<iso utc>",
  "recorded_by": "python -m tests.golden_client --record",
  "gw": 4,
  "commit": "<hash the recording ran at>",
  "config": { "...asdict(golden_config())..." },
  "inputs": { "models/attacking.joblib": "<sha256>", "...": "...",
              "data/history/player_gw.parquet": "<sha256>" },
  "responses": { "count": 0, "bytes_gz": 0 },
  "levers": { "restraint_steps_taken": 0, "restraint_steps_refused": 0,
              "objective_hits": 0, "chip_rows": 0, "league_lam": 0.0,
              "bench": 0, "vice": false, "plan_weeks": 0 },
  "runtime_s": 0.0
}
```

The test asserts `header["config"] == asdict(golden_config())`, so editing
one without re-recording fails loudly.

## 5. What sits behind the seam

Reads, in `run_advise` order, and how each is held still:

| Input | Held by |
|---|---|
| bootstrap, fixtures, 654 element summaries, entry picks / transfers / history, league standings, rivals' picks and history | the bundle, via `RecordedClient` |
| `data/live/player_gw.parquet` (rebuilt by `refresh_live` from the summaries; `_carry_setpiece_orders` reads the previous one) | absent in the scratch tree, so every run starts from none |
| `data/history/*.parquet` (training frame, Understat team, cups, match odds) | symlink; hashed; skip on drift |
| `data/core_insights/**` | copied into the fixture at record time |
| `data/manager_tenures.toml` | tracked; copied |
| `models/*.joblib`, `*.params.json`, `*.meta.json` | symlink; hashed; skip on drift |
| the packaged assets (`decision_priors.json`, `scenario_noise.json`, …) | tracked source |
| `data/chip_scenarios.toml`, `data/set_pieces.toml` | absent on this machine and absent in the tree; the header's `inputs` records `"absent"` for each so a later presence is a drift, not a surprise |
| `config.toml` through `serving_config()` | written from `golden_config()`; cache cleared |
| the clock | only `generated_at`, stripped |
| news, odds, player props | off in the config; no fetcher runs |

Writes, all inside the scratch tree: `data/live/{player_gw,fixtures,…}.parquet`,
`data/live/predictions/gw4.parquet`, `data/live/news_shadow.parquet` if any,
`data/snapshots/`, `reports/{gw4-advice.json, solve_state_gw4.json,
solve_state_gw4.parquet, components_gw4.parquet, availability_gw4.parquet,
ladder_gw4.json, health.json}` and `reports/advice_history/`.

Determinism, checked rather than assumed by gate item 1: the sweep and the
ladder are seeded from the config; the MILP runs HiGHS with no time limit;
v17b's paired run showed the pipeline itself byte-stable when the input
was. LightGBM prediction is deterministic for a fixed model file.

## 6. Tests (`tests/test_golden_board.py`)

Sentences, as the house writes them:

- `test_the_golden_board_reproduces_the_expected_advice_and_state` — the
  gate's item 1; marked `golden`; skips through `stale_inputs`.
- `test_the_golden_board_still_exercises_every_lever` — item 2, on the
  run's advice; shares the run with the test above through a module-scoped
  fixture so the pipeline runs once per session.
- `test_a_changed_model_hash_skips_with_the_file_named` and
  `test_matching_hashes_do_not_skip` — item 3, over `stale_inputs` with a
  header copy and a temp tree.
- `test_the_recorded_client_serves_every_recorded_path_and_refuses_the_rest`
  — `RecordedClient` over a two-entry bundle in `tmp_path`.
- `test_the_recorded_client_never_writes_a_raw_snapshot`.
- `test_golden_config_round_trips_through_the_toml_writer` — the §2.3 pin.
- `test_the_header_config_is_golden_config` — the §4 pin.
- `test_the_recorded_config_has_no_odds_section_and_no_key`.
- `test_strip_volatile_removes_generated_at_and_rewrites_paths`.
- `test_the_fixture_is_under_the_size_budget` — item 4, in-process.

Existing tests that die: none. `tests/test_client.py` gains nothing; the
recorded client lives in `tests/`, not in the package.

## 7. Pins and protected files

Routes 51, job kinds 12, `Config` fields 59: none move. No new route, kind,
field or schema. `src/gaffer/advise.py` is not touched (programme, and the
user's prompt). `pyproject.toml` gains one `markers` line under
`[tool.pytest.ini_options]`; that is the orchestrator's edit. No other
protected file is touched.

## 8. Process

Orchestrator: this spec, the plan, the branch, the recording (choosing the
gameweek and the caps), every gate run, the `pyproject.toml` line, the
merge, the push, the security ritual, the docs and the tracker.
Implementer (Opus, fresh per task, spec review then code review between
tasks): `tests/golden_client.py` and `tests/test_golden_board.py` against
a two-entry synthetic bundle, so that the module is complete and tested
before any live response is recorded. The implementer never runs
`--record` and never reads `config.toml`.

The recording happens before the GW4 deadline so that GW4 is the next
gameweek in the bootstrap; if the deadline passes first, the golden is GW5
and the header says so. The gameweek is a fact of the recording, not a
choice to defend.

## 9. Out of scope

Any change under `src/`. Recording at the `Inputs` level (v17g). Running the
golden in CI (no CI exists; the skip rule is what makes the test safe to
collect anywhere). Shrinking `data/history/` into the fixture. A golden for
the initial-squad mode or for a chip-played week.

## 10. Outcome

_(filled by the orchestrator after the gate)_
