# gaffer v12 — the polish program (design)

**Date:** 2026-09-01
**Source:** `docs/superpowers/research/2026-09-01-polish-and-improvement-research.md`
**Shape:** one umbrella spec, five workstreams (W1–W5), one implementation
plan per workstream, executed back-to-back in order. Each workstream is
reviewed, gated, ff-merged to `main` and pushed before the next starts, so
`main` is shippable between workstreams and a failed gate withdraws one
stream, not the program.

**Authorization:** protected-file edits are enumerated per plan behind STOPs
in the usual way; the orchestrator holds standing authorization for this
program (user decision, 2026-09-01). Provenance comments `# v12 W<n> §<id>
(specs/2026-09-01-gaffer-v12-program-design.md)` on every authorized edit;
zero unauthorized diffs remains a gate.

**Execution:** Fable subagents for planning and implementation; the
orchestrator reviews and gates only.

## 0. Why this program

Single-GW point prediction is at its public ceiling (research doc, headline).
v12 therefore spends on: correctness of what exists (W1), signal already on
disk (W2), the decisions the solver can express (W3), the one data source
that changes what the tool can see (W4), and the interface (W5). Model work
is limited to gated ablations that ride on training runs already happening.

## 1. Conventions shared by every workstream

- **Empty states are honest.** Any view or report whose data does not exist
  yet renders a sentence saying what it is waiting for and when it will
  exist (a GW being `data_checked`, N snapshot dates, a collector run). It
  never renders zeros as if they were measurements.
- **Data-gated items get a ROADMAP checkbox** naming the condition that
  unblocks them.
- **Degradation.** Every new collector or reader gets a
  `tests/test_<name>_degradation.py` in the existing pattern: missing file,
  malformed file, empty result, partial result — each a named behaviour, none
  a crash.
- **Season guard.** Every new element-id-keyed read takes `season` and
  filters on it.
- **Atomic writes** use one shared helper (`gaffer/io.py::atomic_write`,
  new in W1) instead of the six copies of the idiom. Existing copies are
  migrated only where a workstream already touches the file.
- **Config.** New keys are added to `config.example.toml` with a comment
  and to the Settings whitelist (W5) if they are desk keys.
- **Provenance.** Every authorized edit to a protected file carries the
  provenance comment above.

## 2. W1 — hygiene

### 2.1 `gaffer backup`
- `gaffer backup [--to DIR] [--rsync TARGET]`. Tars `data/live/`,
  `reports/`, `models/` (field EO samples live in `data/live/field_eo_log.parquet`,
  so they are covered) into `<to>/gaffer-<YYYYMMDD-HHMM>.tar.gz`.
  Default `--to` is `[backup] dir` in config, falling back to
  `~/gaffer-backups`. `--rsync` (or `[backup] rsync_target`) copies the
  archive to a remote path with `rsync -a`. Keeps the last `[backup] keep`
  archives (default 14), deleting older ones **only in the local dir**.
- `scripts/com.gaffer.backup.plist` nightly at 23:45 (after prices at
  23:15). Added to the automation table in README and GUIDE.
- Health hub shows "last backup: <ts> (<size>)" from the newest archive's
  mtime, or "never" in the empty state.

### 2.2 One set of EO constants
- Canonical: `optimize/differentials.py` exports `DIFFERENTIAL_EO`,
  `ALTERNATIVE_EO`, `TEMPLATE_EO` in **fraction** units (0.30, 0.20, 0.70).
- `advise.py:461-464` deletes its own definitions and imports the canonical
  ones (authorized edit). The plan lists every reader of the three names
  and states, per reader, which unit the compared quantity is in; any reader
  that compares against a percent quantity is converted at the read site.
- Test: an import-time assertion that the three constants are in (0, 1),
  and a grep-style test that no other module defines a name ending in `_EO`
  with a numeric literal.

### 2.3 Season-guarded field EO
- `data/field.py::latest_field_eo(gw=None, *, season)` — `season` becomes
  required keyword. `load_field_eo()` gains `season` filtering. All callers
  (`routers/players.py:149` and any others the plan finds) pass
  `current_season`.
- Test: two seasons' rows in the log with overlapping element ids; the
  reader returns only the requested season's.

### 2.4 Season rollover guard
- `refresh` compares the API bootstrap's current season (derived from the
  events' deadline year pair) with `config.current_season`; on mismatch it
  exits non-zero with a message naming both values and the two keys to
  change (`current_season`, `train_seasons`).
- `meta` router exposes `season_ok: bool` and both values; Health renders a
  red banner when false.

### 2.5 `track_pens` refusal
- If every fetched row is degraded (the function's existing degraded
  marker), the tracker file is left untouched and the run logs
  `track_pens: refused to overwrite <path>: all N rows degraded`. Mirrors
  the `calibrate_noise` refusal pattern.

### 2.6 `DEFAULT_TOP_N` becomes visible
- `[solver] top_n = {GKP=8, DEF=22, MID=26, FWD=14}` in config; `milp.py`
  reads it (authorized edit, one line-group). Health shows the pool sizes.
  The solver trace (W5 §6.5) names any owned player who fell outside the
  pool.

### 2.7 `gaffer tidy`
- `gaffer tidy [--apply] [--older-than DAYS]` (default dry-run, 30 days).
  Targets: `data/live/backtest_log_*.parquet` not referenced by any
  `reports/*` ledger, and `logs/*.log` older than the cutoff. Dry-run
  prints the list and total size; `--apply` deletes. Never touches
  `availability_log`, `field_eo_log`, price log, or any ledger.

### 2.8 LAN write protection
- When `ui --lan` is used, every non-GET route requires header
  `X-Gaffer-Token: <token>` where token comes from `[web] token` or, if
  unset, is generated at startup and printed once. Localhost without
  `--lan` is unchanged. Front end reads the token from a `?token=` query
  parameter on first load and stores it in `localStorage`.

### 2.9 "As of" strip
- One component rendered at the top of every hub: last refresh, last odds
  fetch, last field scrape, last advise, last backup — each with age
  colouring (green < 1d, amber < 3d, red otherwise, grey for "never"). Data
  from a single `/api/meta/freshness` endpoint (new) that reads file
  mtimes and the ledgers' latest timestamps.

### 2.10 MCP server
- `gaffer mcp` runs a stdio MCP server (python `mcp` package, added to
  dependencies). Tools, each a thin wrapper over the existing router
  function with the same pydantic response models:
  - `projections(gw?, position?, team?, top?)`
  - `explain(code)` — the player explain payload
  - `whatif(transfers_in, transfers_out, chip?)` — read-only solve preview
  - `ledger(gw?)` — the advice ledger rows
  - `freshness()` — §2.9's payload
  - `health()`
- No write tools in v12. A `README` section documents adding the server to
  Claude Code (`claude mcp add gaffer -- gaffer mcp`).
- Test: each tool's schema round-trips and each returns the router's
  payload on a fixture state.

### 2.11 `gaffer/io.py::atomic_write`
- One helper (`tmp` in the same dir, `os.replace`). The six existing copies
  are migrated in W1 (this is the one place the "only where touched" rule
  is waived, so the helper has real callers from day one).

**W1 gate:** suite green; zero unauthorized protected diffs; `gaffer backup`
produces an archive that restores (test extracts and diffs a fixture tree);
`refresh` against the live API passes the rollover guard.

## 3. W2 — mine what we have

### 3.1 Flag-latency report
- Reads `availability_log.parquet` (columns include `season, gw, snap_date,
  code, status, chance_of_playing, llm_verdict, source`). For each
  (code, gw) whose status changed at least once before the deadline,
  compute days between the first change and the deadline, and whether the
  player then started (from the checked GW's minutes). Output: histogram of
  lead days by outcome; a table of the 20 worst "late flags" (started ≠
  final status).
- Surface: Model → Quality, new "Availability signal" section. Empty state
  until `snap_date.nunique() >= 14` **and** at least one covered GW is
  `data_checked`; the state says both numbers.
- CLI: `gaffer evaluate --flag-latency` writes the same payload to
  `reports/evaluate/flag_latency.json`.

### 3.2 Presser-verdict grading
- Same section. For each row with a non-null `llm_verdict` (`source` is
  `llm`; verdict classes today: `ruled_out`, `assess`, `knock`,
  `rotation_risk`), grade against the checked GW's start.
  Output: confusion matrix and precision/recall per verdict class. Shares
  `evaluate_news_shadow`'s actuals loader. Empty state until GW2 is
  `data_checked`.
- ROADMAP checkboxes: news-shadow (existing), flag-latency (14 dates),
  presser grading (GW2 checked).

### 3.3 EO trend
- The field scrape already runs Sat and Sun; the log keeps every sample.
  New reader `field_eo_trend(season, gw)` returns per-code `eo_first`,
  `eo_last`, `delta`, `hours_between`. `deadline_eo` = `eo_last + delta ×
  (hours_to_deadline / hours_between)`, clamped to [0, 1], only when two
  samples exist; otherwise `eo_last` and a `trend_available=False` flag.
- The EO lens on This Week and the captain table use `deadline_eo`; the
  UI shows an arrow (↑/↓/→) with the delta on hover. Rank tilt (λ) is
  unchanged.

### 3.4 Price-timing term
- The nightly price log plus the official predictor reading give, per
  owned player, `p_fall_tonight`. In the objective, a transfer-out of a
  player scheduled for a *later* GW in the horizon is charged
  `p_fall_tonight × 0.1 × itb_value` (authorized edit in `milp.py`,
  one term). No term for rises (rejected: price chasing). Config
  `[solver] price_timing = true`.
- Test: with `p_fall_tonight = 1` and two otherwise-equal sell timings,
  the solver sells this week.

### 3.5 xG-per-shot ablation
- Feature `us_npxg_per_shot = us_npxg90 / us_shots90` (0 when shots = 0,
  with a missing indicator). Added behind `[model] xg_per_shot` (default
  off). Gated ablation on the next `train`: kept (default on) only if the
  hauler bucket RMSE improves and no other bucket worsens by more than its
  seed-spread. Recorded in the model quality table like prior arms.

**W2 gate:** suite green; §3.4 replay tolerance 5 vs main (the S1 rule);
§3.5 pre-registered outcome recorded either way; empty states verified
by test with an empty log.

## 4. W3 — decide

All of W3 is in `optimize/**` and `advise.py` (protected); each item is an
enumerated authorized edit.

### 4.1 `force_out`
- `SolveInput.force_out: list[int]` (codes). Constraint: each listed owned
  player has squad membership 0 from the first GW of the horizon. Distinct
  from `locked_out` (cannot be bought). Schema field on the what-if
  request; What-if and the planner board expose "must sell" on an owned
  player's row; the ledger records it.
- Infeasible (e.g. force_out with no affordable replacement) returns the
  existing infeasibility payload naming the constraint.

### 4.2 θ is the only chip decision
- `chips.py:46,60` flat thresholds are kept only as `flat_thresholds()`'s
  source; `advise.py:735` already uses `chip_thresholds_from_asset`. The
  change: wherever a flat threshold is consulted while θ is available, use
  θ; the chip caption states `threshold: θ (v4c)` or `threshold: flat
  fallback` and why (no priors asset, GW outside window).
- Test: with a priors asset present, no code path reads the flat values.

### 4.3 Top-3 distinct plans
- After the first solve, add a no-good cut on the set of transfer
  (in, out, gw) triples of the incumbent and re-solve; repeat to 3 plans
  or until the EP gap exceeds `[solver] alt_plan_max_gap` (default 2.0 pts
  over the horizon). Returned as `Plan.alternatives: list[Plan]` with
  `gap`. Board shows them as tabs "Plan A / B / C" with the gap and the
  differing moves highlighted. Sweep frequency tables are computed on plan
  A only (unchanged).

### 4.4 Availability-aware sweep
- `run_scenarios` gains a per-scenario availability draw: for each
  (code, gw), `available ~ Bernoulli(p_play)`; unavailable → EP 0 for
  that GW. Noise on EP is then applied as today conditional on available.
  Config `[scenarios] draw_availability = true`. `move_frequencies`
  unchanged; the UI's "bought in N%" now reflects availability risk.
- Gate: scenario support for the live captain must not fall below its
  current value by more than 10 points on the same inputs (S1 recorded a
  collapse 92% → 22% as the failure signature — this is the check).

### 4.5 Chip pairs and a real Free Hit
- `evaluate_chips` evaluates WC+BB (wildcard in GW g, bench boost in
  g+k, k ≤ horizon) as one option whose surplus is the joint solve minus
  baseline; shown as a single row "WC gN + BB gM". Only when a DGW is in
  the horizon (from `load_chip_scenarios`).
- `free_hit_gain` becomes a true re-solve: one-GW unconstrained squad for
  the FH week under the current budget (selling at sell prices), scored
  against the baseline's week. The approximation path is removed.

### 4.6 DGW captain
- Captain choice in a DGW uses the two-fixture point distribution (sum of
  the two fixtures' EP with the existing σ) — the disclaimed "ranking"
  number and its caption are removed.

**W3 gate:** 2025-26 gated replay, identical seeds, vs `main` at the
workstream's base commit: total points within tolerance 5, hits not up by
more than 3. §4.4's support check. Zero unauthorized diffs.

## 5. W4 — field

### 5.1 FPL-Core-Insights collector
- `gaffer core-insights` fetches the repository's per-season CSVs (player
  match stats incl. CBIT/defcon, ClubElo, fixtures incl. cups/Europe)
  keyed on FPL element id, joins to `code` via the season's element map,
  and writes `data/core_insights/<season>/{players,fixtures,elo}.parquet`.
  Twice-daily plist `com.gaffer.core-insights.plist` (06:30, 18:30).
- Degradation tests: repo unreachable, CSV schema drift (unknown column
  added / expected column missing), empty season.
- Health line: rows and latest date per table.

### 5.2 Gated minutes features (new arms)
- `role_wb_share`: share of the last 5 starts in which CBIT/defcon
  profile classifies the defender as wing-back (rule in the plan). DEF only.
- `density_pub_7d`: published fixtures (league + cup + Europe) in the
  seven days before kickoff, from §5.1 — **forward** fixtures from the
  published list, not the withdrawn cup-archive congestion arm; the spec
  and quality table say so.
- Each is a pre-registered arm on the minutes model with the v10 rule
  (autosub-week counterfactual and bucket RMSE); kept only if it clears.

### 5.3 Rank-distribution simulation
- Extend `league_sim`'s correlated sampler: the "field" is a synthetic
  population whose picks are drawn from field EO (§3.3's `deadline_eo`),
  correlated through the same player draws as the user's squad. Output
  per GW: `P(green arrow)`, `P(top-10k)` (needs the top-10k score
  threshold: use the historical distribution of top-10k weekly scores by
  GW from `build-history`, else empty state), and the user's expected
  overall-rank change. League hub → new "Field" panel.
- Test: a squad identical to the field's modal team has P(green) ≈ 0.5.

### 5.4 Set-piece overrides
- `data/set_pieces.yaml` (untracked, example file tracked): per team,
  ordered takers for penalties, direct FKs, corners. `set_pieces.py` reads
  it before inference (authorized edit: one read hook); the UI shows a
  "manual" badge where the override applied.

**W4 gate:** collector degradation tests; §5.2 outcomes recorded; §5.3
sanity test; suite green.

## 6. W5 — interface

### 6.1 Tab state in the URL
- `?tab=` per hub, read on load, written on change; deep links work.
### 6.2 Settings tab (Model hub)
- Whitelist: `horizon, decay, lambda_tilt, chip θ priors path, top_n,
  bench_weights, itb_value, price_timing, draw_availability`. Read from
  the merged config; edits are written to `config.local.toml`, which
  `config.py` loads as an overlay after `config.toml`. The UI never reads
  or writes `config.toml`. A "restart to apply" notice where needed.
### 6.3 Watchlist list view; `captain_note` rendered on This Week beside the
  captain pick.
### 6.4 Frozen projections
- Every `advise` run writes `reports/projections/<season>-GW<gw>-<ts>.parquet`
  (the EP table it acted on). Review compares the ledger against the
  latest snapshot before the deadline, not a re-run; the Review row shows
  the snapshot timestamp.
### 6.5 "Why this move" trace
- Per transfer in the plan: EP gain over the horizon, hit cost, FT shadow
  price consumed, θ (if a chip), λ tilt contribution, price-timing charge.
  Exposed on the ledger row and the board; computed in `_decision_scales`'
  neighbourhood (authorized edit, read-only accounting — must not change
  any decision; test asserts the plan is byte-identical with the trace on
  and off).
### 6.6 `types.ts` generation
- `scripts/gen_types.py` emits `frontend/src/types.ts` from
  `web/schemas.py` (pydantic → JSON schema → TS via
  `json-schema-to-typescript`, pinned). A test regenerates to a temp file
  and asserts equality with the committed file.

**W5 gate:** suite green; §6.5 byte-identity test; a manual pass through
all six hubs with the "as of" strip and URL state.

## 7. Testing and gates, summarized

| Workstream | Gate beyond "suite green + zero unauthorized diffs" |
|---|---|
| W1 | backup restore test; live rollover guard |
| W2 | replay tolerance 5 (price-timing); ablation outcome recorded |
| W3 | replay tolerance 5, hits ≤ +3; captain support drop ≤ 10 pts |
| W4 | collector degradation; arm outcomes recorded; rank-sim sanity |
| W5 | trace byte-identity; manual six-hub pass |

Post-merge ritual after every workstream: `git show main:config.toml` fails;
`git log -S<odds key> --all` is empty.

## 8. Out of scope (do not add during execution)

Referee/weather; transformer news sentiment; Sarmanov/NB Dixon-Coles; price
chasing; per-player finishing multipliers; horizon extension; the withdrawn
minutes arms as-is; write tools on the MCP server; a UI that edits
`config.toml`.
