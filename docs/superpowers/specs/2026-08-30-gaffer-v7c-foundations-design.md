# gaffer v7c — foundations (design)

Date: 2026-08-30 · Branch: `feat/gaffer-v7c` · Cycle type: infrastructure (no model-quality gates)

## §0 Context and autonomy decisions

GW2 is unfinished (`data_checked: false`), so the two biggest levers (N2 verdicts, news
corrector) are blocked on time passing, not work. This cycle ships three small pieces that
either compound with every passing day or harden the measurement discipline permanently.
The user approved the three-piece scope verbatim ("run the v7c foundations cycle").

Decisions taken without the user (recorded per the standing autonomy protocol):

- **D1** — The daily snapshot captures the *availability input state*, not shadow-log model
  deltas. Shadow rows require `predict_components` (trained models, minutes of compute);
  the corrector's training input is the news state itself, and model deltas are recomputable
  later from logged inputs. The advise-time shadow log is unchanged (it is also pinned by
  protected rail tests).
- **D2** — Multi-seed support goes *into* `scripts/v7b_replay.py` rather than a new driver.
  The driver is not a frozen record (that is `s2_replay.py`); it already threads
  `--seed-base`, has a test suite (`tests/test_v7b_driver.py`), and a second driver would
  drift. The `V7B_ARM_DONE` per-seed line format is preserved byte-compatible.
- **D3** — The pen tracker is read-only over already-banked artifacts. It does not touch
  `set_pieces.py` (protected) or `advise.py` (protected); it imports the pure functions
  `pen_estimate` / `share_now` from `gaffer.set_pieces`.
- **D4** — No new model behaviour anywhere in this cycle. Nothing in `src/gaffer/optimize/`,
  `advise.py`, `set_pieces.py`, or the models changes. Degradation rails untouched.

## §1 F1 — Daily availability snapshot (`gaffer snapshot`)

**Why first:** `reports/availability_gw{N}.parquet` is one file per GW, overwritten on every
advise run (`artifacts.py:390-434`), and the raw HTML cache is bucketed by fetch time only.
Every day without a timestamped availability record is corrector training data lost forever.

**New module `src/gaffer/snapshot.py`:**

- `SNAPSHOT_PATH = "live/availability_log.parquet"` (under `data/` via `gaffer.data.store`,
  same convention as `news_shadow.py`).
- Columns: `AVAILABILITY_COLS` (`code, status, chance_of_playing, injury_type,
  expected_return_gw, p_start_hint, source, fetched_at` — reuse the constant from
  `gaffer.artifacts`) **plus** `season, gw, snap_date` (UTC `YYYY-MM-DD`) prepended.
- `run_snapshot(cfg=None) -> int | None`: fetch bootstrap via `FPLClient`
  (players/teams/events), determine the next unfinished GW from events, call
  `news_availability(cfg, players, teams, events, gw)` (imported from `gaffer.advise` —
  import only, no modification), and append the resulting availability frame to the log.
- Append semantics: load-existing → drop rows with the same `snap_date` (idempotent daily
  re-runs replace that day) → concat → `store.save` (append-by-rewrite, exactly like
  `write_shadow`). Returns row count written, `None` on skip.
- Failure envelope: **never raises** — any exception prints one line to stdout and returns
  `None` (launchd log picks it up). Same posture as `write_shadow` (`news_shadow.py:100`).
- `load_snapshot_log()` loader mirroring `load_shadow()`.

**CLI:** new `gaffer snapshot` subcommand in `cli.py` (lazy imports, prints
`Snapshot: {n} availability rows for gw{N} at {snap_date}.` or the degradation line).

**Scheduling:** new `scripts/com.gaffer.snapshot.plist` — daily `StartCalendarInterval`
at 17:00 local, `uv run gaffer snapshot >> logs/snapshot.log 2>&1`, templated with
`__PROJECT_DIR__` like the two existing plists; `scripts/install_automation.sh` extended to
install it. README automation section gains one line.

**Web job:** new `snapshot` kind in `web/job_kinds.py` (wrapper prints + returns
`{"rows": n}`), so the browser command centre can trigger it. No new frontend surface —
the generic job runner already handles unknown-kind buttons only where wired; adding the
kind to the backend allow-list is enough for this cycle (UI button deferred).

## §2 F2 — Multi-seed gates as the house standard

**Driver change (`scripts/v7b_replay.py`):**

- New `--seed-bases "20260825,20260826,20260827"` (comma list, mutually exclusive with
  `--seed-base`). The driver loops the bases sequentially; each iteration derives tag
  `f"{tag}-s{base}"` with its own `_ArmStore` log/report paths and prints its own
  `V7B_ARM_DONE {tag}-s{base} {json}` line (byte-compatible with the single-seed format).
- After the loop it prints one aggregate line:
  `MULTISEED_DONE {tag} {"totals": [...], "mean": μ, "spread": max-min, "range": [min, max], "seed_bases": [...]}`
  (values from the per-seed `total` fields; mean rounded to 1 decimal).
- `--seed-base` alone behaves exactly as today (single run, no aggregate line).
- Patches are applied once around the whole loop (they are seed-independent); the gate
  closure is rebuilt per base.

**Aggregator (`scripts/seed_stats.py`):** small standalone script:
`uv run python scripts/seed_stats.py reports/v7b_q1b-*.json` → prints per-file totals and
the same mean/spread/range JSON. Lets already-banked single-seed reports be aggregated
without re-running anything.

**Conventions doc (`docs/superpowers/CONVENTIONS.md`):** new, committed, linked from
ROADMAP header. Codifies the measurement discipline learned v4c→v7b:

1. Every replay gate runs K ≥ 3 seed bases; verdicts read mean ± spread, never one draw.
   (v7b measured seed spread 116 pts — larger than every arm gap ever gated on.)
2. Gates are pre-registered in the spec with a mechanical verdict rule before any arm runs.
3. Every comparison includes its control arm (raw/no-op) — v7-model's S2 lesson.
4. Evidence appendix in the spec: every `*_ARM_DONE` line transcribed (logs/ is gitignored).
5. Single-seed causal claims are named residuals, not conclusions.
6. Failing gates ship OFF behind their flag with the negative result recorded.
7. Orchestrator runs gates; implementers never self-certify.
8. Security ritual after any merge/push (key grep + `git show main:config.toml` must fail).

## §3 F3 — Pen-term season tracker (`gaffer track-pens`)

**Why now:** the v6 pen-EP validation was deferred to season end. The prediction side is
already banked per GW (`ep_pen_taker` in `reports/components_gw{N}.parquet`;
`penalties_order` rides along in `data/live/player_gw.parquet` rows). The tracker turns the
May comparison into a standing report that accrues weekly.

**New module `src/gaffer/pen_tracker.py`:**

- `track_pens(season=None) -> dict`: for each **finished** GW of the current season present
  in `live/player_gw.parquet`:
  - *Predicted:* from `reports/components_gw{N}.parquet` (when present): per-player
    `ep_pen_taker` where nonzero; from `player_gw` rows: `share_now(penalties_order)`.
  - *Realized:* pen events per player-match via `pen_estimate` (`xg − us_npxg` instrument)
    when Understat current-season data is joinable; **degrades** to the
    `pens_missed`-only signal with an explicit `"instrument": "pens_missed_only"` marker
    when `us_npxg` is unavailable for the season (never raises, never blocks).
  - Aggregates: league-wide predicted-taker hit rate (did the order-1 taker take the pens),
    league pens/game observed vs the served `LEAGUE_PENS_PG = 0.13` constant, cumulative
    predicted `ep_pen_taker` vs realized pen points proxy
    (`events × PEN_CONVERSION × goal_points`), all with row counts.
- Output: `reports/pen_tracker.json` (atomic tmp+`os.replace`, same as `save_evaluation`),
  plus a printed table. Structure keyed by gw with a `"season_totals"` block.
- Imports from `gaffer.set_pieces`: `pen_estimate`, `share_now`, `PEN_CONVERSION`,
  `GOAL_POINTS`, `LEAGUE_PENS_PG` — read-only; the module itself is untouched.

**CLI:** `gaffer track-pens [--season]` in `cli.py`. Not wired into `evaluate` (keeps
`evaluation.json` schema stable and the Model hub untouched this cycle; a hub card is a
future editorial item).

## §4 Protected files (unchanged this cycle)

`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`, all
`tests/test_*_degradation.py` rails, `scripts/s2_replay.py` (frozen record).
Importing from protected modules is allowed; modifying them is not.

## §5 Gates (functional, orchestrator-run)

- **G1 snapshot:** (a) `gaffer snapshot` on live data writes rows and prints the count;
  (b) a second same-day run leaves the log with no duplicate `snap_date` rows;
  (c) offline/failed-fetch path prints one line and exits 0 (unit-tested, plus a live
  smoke with network unplugged is NOT required — the never-raise test suffices).
- **G2 multi-seed:** unit suite drives `--seed-bases` over a monkeypatched
  `run_backtest` (pattern of `tests/test_v7b_driver.py`) and asserts per-seed
  `V7B_ARM_DONE` lines, per-seed report paths, and correct `MULTISEED_DONE` math;
  single `--seed-base` path proven byte-identical in output shape. `seed_stats.py`
  reads back the one same-arm pair banked on disk: `v7b_q1b-heur` 1876 +
  `v7b_q1c-heur` 1901 → spread **25** over two seeds. `v7b_q2-ctrl-heur` 1786 is a
  chips-off/priors-off **control** arm and must not be averaged in — its 1786 is a
  one-point coincidence with the S2 chips-on heuristic run's 1785, not a redraw of it.
  v7b's published **116** (S2 1785 at seed 20260827 + 1876 + 1901, all one arm) stands
  as the reference spread. The config guard added this cycle is what makes the mix
  impossible in future. Smoke expectations: `seed_stats.py` over q1b + q1c prints
  `{"totals": [1876, 1901], "mean": 1888.5, "spread": 25, "range": [1876, 1901], ...}`;
  over the mixed trio it refuses with exit 2 and prints no aggregate. No new
  multi-hour replay runs this cycle.
- **G3 pens:** `gaffer track-pens` on current data produces `reports/pen_tracker.json`
  covering GW1 (finished) with sane fields; degraded-instrument path unit-tested.
- **G4 suite:** full pytest green; no protected file diffs (`git diff --stat` audited
  against §4).

## §6 Testing

New test modules following house conventions (sentence names, module docstring,
`monkeypatch` + `tmp_path` with `store.DATA_DIR` redirect):
`tests/test_snapshot.py`, `tests/test_pen_tracker.py`, extensions to
`tests/test_v7b_driver.py` for `--seed-bases`, `tests/test_seed_stats.py`
(`sys.path.insert(0, "scripts")` convention). Job-kind allow-list growth covered in the
existing web job tests' companion file only if it does not touch the protected
`tests/test_web_jobs.py` — otherwise a new `tests/test_web_job_kinds_v7c.py`.

## §7 Out of scope

Corrector model itself (needs ~half a season of log); Z1 flip; scenario-sweep skip
switch; Model-hub pen card and snapshot-job UI button (editorial, later); FFS lineups
real-page parse; any change to replay season/start-gw hard-coding.

## §8 Outcome

Cycle closed 2026-08-30. Three implementer groups (Tasks 1–13) + one fix round, all on
Opus; orchestrator ran every gate. Adversarial review: **1 blocker + 4 importants + 9
nits**, all fixed except three recorded residuals (below). Suite **1619 Python** green
(from 1548), protected files zero diffs vs main, no frontend change.

The blocker was in the *evidence*, not the code: this spec's own §5 (as first committed)
averaged `q2-ctrl-heur` (1786, a chips-off/priors-off control arm) with the q1b/q1c
heuristic runs as a "seed trio", because its total sits 1 point from the real S2 chips-on
heuristic 1785. `seed_stats.py` had no config guard and silently aggregated different
arms on its first ever use — proving the guard's necessity. Fixed: the guard now refuses
any aggregate whose config echoes differ in more than `seed_base`/`tag`, and §5/G2 plus
CONVENTIONS §1 carry the provenance (v7b's 116 = S2 1785 + q1b 1876 + q1c 1901, same arm;
the only same-arm banked v7b-format pair is 1876/1901, spread 25).

Other review fixes: `team_games` re-keyed on `(opp_code, kickoff_time)` (`team_code` is
retro-stamped to the player's current club — live GW1 gave 27 phantom team-games vs the
true 20); per-week Understat coverage (`covered_rows` in every gw block, all-NaN join
falls back to `pens_missed_only` instead of reporting zero pens as `xg_gap`); atomic
tmp+`os.replace` rewrite for the availability log; multi-seed loop tests moved onto a
gated arm (per-base seeds observed, mid-loop exception restores all three `bt` hooks);
`--arm raw --seed-bases` refused (raw never reaches the scenario seed).

### Gate evidence (convention 4)

```
G1  $ gaffer snapshot                       (run twice)
    Snapshot: 623 availability rows for gw2 at 2026-08-30.
    Snapshot: 623 availability rows for gw2 at 2026-08-30.
    availability_log.parquet: 623 rows, 1 distinct snap_date, gw [2]
G2  $ python scripts/seed_stats.py reports/v7b_q1b-heur.json reports/v7b_q1c-heur.json
    {"totals": [1876, 1901], "mean": 1888.5, "spread": 25, "range": [1876, 1901],
     "seed_bases": [20260901, 20260915]}                          exit 0
    $ … + reports/v7b_q2-ctrl-heur.json
    refusing to aggregate: chips, priors differ across … — these are different arms,
    not different seeds of one arm                                 exit 2
G3  $ gaffer track-pens
    GW1: instrument xg_gap, covered_rows 256, team_games 20, pens_taken 2.0,
    taker_hit_rate 1.00, pens_per_team_game 0.100 vs served 0.13
    predicted EP 0.00 (component_rows 0 — reports/components_gw1.parquet no longer on
    disk; documented absent-artifact zeros path). Wrote reports/pen_tracker.json.
G4  uv run pytest -q -p no:randomly → 1619 passed, 0 failed (138s)
    git diff main --stat over the protected list → empty
```

### Residuals (recorded, not fixed)

- A fully degraded `track_pens` run still overwrites a previously good
  `pen_tracker.json` with an empty noted report (per-GW poisoning is handled; total
  failure is not preserved-on-disk).
- `MULTISEED_DONE` is not emitted if the final base dies; banked per-seed reports are
  the recovery path via `seed_stats.py` (docstring points there).
- The v7b spec §5/§7 still carries its original "spread 116" table without the
  same-arm provenance note added here; historical record left untouched.

### Activation note

The launchd job is shipped but **not installed** — installing a standing scheduled job
is a user action. Run `scripts/install_automation.sh` to activate the daily 17:00
snapshot (it reinstalls the advise/prices agents too, idempotently).
