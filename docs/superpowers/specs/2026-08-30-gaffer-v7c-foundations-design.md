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
  - Aggregates: per-team predicted-taker hit rate (did the order-1 taker take the pens),
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
  reproduces v7b's Q1 heuristic numbers from the banked reports
  (`v7b_q2-ctrl-heur` 1786 + `v7b_q1b-heur` 1876 + `v7b_q1c-heur` 1901 → spread **115**;
  the v7b spec's published 116 substituted the reused v7-model S2 run, 1785 at seed
  20260827, which has no v7b-format report JSON on disk). No new
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

(filled at cycle close)
