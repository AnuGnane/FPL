# Holiday queue (6 to 23 October 2026)

Anu is away with a phone and, now and then, the laptop. Scheduled cloud agents work this queue one package a run, and from 6 October 14:00 London they merge their own work: Anu has handed the holiday over and nothing waits for approval. The protections are the gate and a review, not a person (see **Merging**). The playbook is in the private repo `AnuGnane/autopilot`.

`CLAUDE.md` rules, including the pins, the orchestrator-only files, the secrets rule and explicit-path staging. This file only says what a cloud run may do, how it reports, and what is queued. A holiday package is small enough that one agent does it directly: no subagents, no cycle branch, no screenshots gate. The full cycle machinery is for when Anu is back.

## Where you are running

A Linux sandbox cloned from GitHub. `config.toml`, `config.local.toml`, `data/`, `models/`, `reports/` and `logs/` are untracked and do not exist here. So:

- The runnable gates are `uvx ruff check src tests`, `.venv/bin/pytest -q -m "not slow and not golden"` (after `uv sync`) and `cd frontend && npm ci && npm run check`. Tests that need local data skip or fail here; the first package finds out which and records it. The golden gate and every replay run on the Mac in the night shift.
- Never create a `config.toml`. Never write a key or token into any file. There is no odds key here and nothing needs one.
- Do not touch the orchestrator-only files listed in `CLAUDE.md`, do not move a pin, do not add a job kind or a `Config` field. A package that would need any of that stops and says so in its PR instead.
- `git add` explicit paths only.

## One package a run

1. `git fetch origin`. A package is **done** when its box below is ticked on `main`. It is **blocked** when a package it depends on is not done.
2. **Resume first.** A branch `holiday/<id>` (or `claude/holiday-<id>`) on origin that is not merged into `main` and is not a `needs-mac` PR is an unfinished run, most likely cut off by a usage limit. Check it out, read its commits and PR, finish it under **Merging**, and only then consider a new package. Never leave a second unfinished branch behind.
3. Take the first package that is neither done, blocked, nor waiting on the Mac. If there is none, **refill** (below). If the queue is full and nothing is ready, stop; write one line saying so.
4. Branch from `origin/main` as `holiday/<id>` (if the push is refused, `claude/holiday-<id>`). Subject lines `<type>(holiday): ...`, one change per commit.
5. Tick the package's box in this file in the same branch (a `needs-mac` package is ticked by the Mac when it merges).
6. Open the PR with the body below, then follow **Merging**. Do not start a second package.

A ruling is a decision only Anu can make. Do not block on it: pick a default, state it in the PR, and carry on. The default stands; if Anu comments on the PR later, the next run applies the comment as a package.

### Refill

When no package is ready, add up to three new ones, each sized for one run and runnable here, each traced to a numbered candidate in `docs/superpowers/ROADMAP.md` or an "Operational" line there, or to a §-numbered item of the v20 spec that is code rather than a replay. Never a replay, never a model-cycle arm (those are the Mac's), never a pin move, a new job kind, a `Config` field or an orchestrator-only file. Commit the refill on `holiday/refill-<date>`, merge it under **Merging**, and stop; the next run takes the first new package.

## Merging

1. **The gate is green** on the branch's final commit, run here and pasted into the PR: `uvx ruff check src tests`, the inner loop, and `npm run check` when `frontend/` changed.
2. **The golden gate is the Mac's.** Read the imports of `tests/test_golden_board.py` and `tests/test_pipeline.py`. If the diff touches any of those modules under `src/gaffer/`, the PR does not merge here: put `needs-mac` at the start of its title and stop; the Mac lane runs the golden board on the branch, then merges. At most one open `needs-mac` PR at a time; if one is open, take a package that will not need it.
3. **Review before merging.** Reread the whole diff (`git diff origin/main...HEAD`) as a reviewer would, with the Task tool's subagent if it is available: anything the package did not ask for, any test weakened or deleted, any key, config value or data path, any pin moved, anything `CLAUDE.md` forbids. Fix what it finds; rerun the gate.
4. **Rebase on `origin/main`** just before merging. If the rebase touched a file, rerun the gate.
5. **Merge** with the GitHub MCP tool (`merge_pull_request`, method `rebase`, since this repo keeps a linear history). If that is unavailable, `git push origin HEAD:main` after the rebase (a fast-forward); GitHub marks the PR merged. Delete the branch. Never force-push; never rewrite `main`.
6. **Report:** the PR is the record for the phone. Finish with one push notification: the package id, merged or `needs-mac`, the gate line.

### PR body

```
## For the phone
**What:** two or three lines.
**Gate:** each command and its result line (passed, failed, skipped; vitest's Errors line). "No gate: docs only" when that is true.
**Rulings:** numbered; each with a default marked. "None" when there are none.
**Risk:** one line on what could be wrong and how you would know.
```

## Queue

### The one-off spec run (Fable, once)

- [x] **F-S1 The v20 spec.** `docs/superpowers/specs/2026-10-07-v20-model-cycle-design.md`, written the way the v19 design was (`specs/2026-09-15-v19-programme-design.md`): research first (`docs/GUIDE.md` §12.5, `docs/superpowers/ROADMAP.md` "Candidates" 11, 12 and 14, the K ≥ 5 role replay under "One experiment", `CONVENTIONS.md`), then one arm per section with its gate and verdict rule pre-registered before anything runs: the bonus head fed `e_goals`, `e_assists` and `position`; the Dixon-Coles floor on `e_gc_model` measured by removing v19g's xfail mark; the price reading banked minutes before the solve; the role replay at K ≥ 5. Each arm names the seed bases, the control, the spread rule and what withdraws it. The spec is the deliverable; no code. Replays run on the Mac in the night shift, one seed at a time (`CLAUDE.md`'s memory note).

### Implementation (Opus, four runs a day)

- [x] **F-1 CI on pull requests.** `.github/workflows/ci.yml`: `uvx ruff check src tests`, `pytest -q -m "not slow and not golden"` under `uv`, and `cd frontend && npm ci && npm run check`, on every PR and on `main`. Python 3.12 (`.python-version`). The PR records which tests skipped or were deselected for lack of local data, and why, so a green tick on later PRs means what it says. Do not weaken a test to make CI pass; deselect by marker or path and say so.
- [x] **F-2 Tidy for projections.** ROADMAP candidate 7, the residual "`reports/projections/` unpruned": extend `gaffer tidy` so it names and prunes projection reports by the rule the GUIDE gives for `tidy`'s scope, keeping the API snapshots (v19h §1 calls them a corpus). Tests with a temporary tree. Gate: ruff and the inner loop.
- [x] **F-3 The web re-run button banks a price reading first.** ROADMAP candidate 7's second half, and the shape of candidate 14. If the only path runs through an orchestrator-only file (`web/jobs.py`, `advise.py`), stop and write the PR as a design note: the diff you would make, in the PR body, for Anu to apply. Gate: ruff, the inner loop, `npm run check`.
- [x] **F-4 Top-10k threshold scrape.** ROADMAP candidate 3: a scraper for a weekly top-10k score threshold with a recorded fixture under `tests/fixtures/`, parsed and stored like the other live readers in `src/gaffer/`, behind a config flag only if one already exists (no new `Config` field: pin 62). No new job kind: run it as an anonymous JobRegistry job if it runs at all. Gate: ruff and the inner loop with the fixture; a live fetch only if the sandbox's network allows it, recorded either way.
- [x] **F-5 The install box, from the agent's side.** `scripts/install_automation.sh`: a `--status` flag that prints each `com.gaffer.*` job's loaded state and next fire time, and a `README` line under "Operational" in the ROADMAP. The agent never runs `launchctl load`; the flag only reads. Gate: shellcheck if available, otherwise `zsh -n`.
- [x] **F-6 `P(top-10k)` reads the threshold log.** ROADMAP candidate 3's remainder (W4 §5.3's data-gated row). `league_sim.simulate_field_rank` returns `p_top10k: None` beside `TOP10K_WAITING`, a sentence F-4 made false. Compute it from `data.top_threshold.threshold_series(season)`: the chance that my season total after this gameweek, i.e. the banked total plus this week's simulated `mine`, clears the 10,000th total projected for this gameweek. The projection is the last banked threshold plus the mean weekly rise over the banked weeks; state that rule in the docstring. Keep a null with a rewritten `waiting_for` sentence while fewer than two gameweeks are banked or my season total is unknown. Edit `league_sim.py` and `web/routers/league_sim.py` only, with no new route and no schema field (`p_top10k` and `top10k_waiting_for` already exist). Tests use a temporary threshold log. Gate: ruff, the inner loop, and `npm run check` if any frontend copy changes.
- [x] **F-7 v20c step zero, the replay harness sees the team model.** v20 spec §2 v20c "Step zero" and ruling 3. `backtest.py` gains `REPLAY_TEAM_MODEL = False`. When it is on, the weekly loop builds the horizon's club-fixture rows from the player rows (`team_code`, `opp_code`, `was_home`, `gw`), predicts them through `models["team"]` and merges `p_cs`/`e_gc` onto the player rows as `predict.py:152-174` does, with no market and the `DEFAULT_P_CS` fill. It logs the lever line: the min, the max and the count of distinct `p_cs` values. Off is byte-identical to today's path. Tests cover both settings on a synthetic frame. The harness ships **off**. The K = 5 re-baseline pair (`MULTISEED_DONE v20c0-harness-*`) is the Mac's and is not run here. If the merge needs `predict.py` or anything `tests/test_golden_board.py` or `tests/test_pipeline.py` imports, title the PR `needs-mac` under **Merging** step 2, which allows at most one open `needs-mac` PR. Gate: ruff and the inner loop.

- [x] **F-8 Public names for the reaches off the golden path.** ROADMAP candidate 7 (housekeeping from the residuals; GUIDE §12.4's v18d lines). `web/routers/meta.py` reads `tracking.HEALTH_PATH` instead of spelling `REPORTS / "health.json"` (no test patches `meta.REPORTS`; the module keeps `REPORTS` for its artifacts glob); `journal._code_of_element` and `data.cups._cached_get` gain public names that `review.py` and `data/core_insights.py` call. The other two reaches (`artifacts._history_stamp`, `config._source_of`) sit in modules the golden tests import and stay, named in the PR. GUIDE §12.4's lines are updated, and its stale "`FixtureTicker` still has no cold-clone sentence" clause struck (v19b §2.6 gave it one). No behaviour change. Gate: ruff and the inner loop.
- [x] **F-9 The league sim remembers each league.** GUIDE §12.4's v15 residual (a non-focus league's sim shares the focus league's one-entry cache slot), under ROADMAP candidate 7. `web/routers/league_sim.py`'s one-slot cache becomes a small bounded map keyed by `_cache_key` (at most eight entries, oldest evicted), keeping the served-once marking and the one-step store its docstrings describe. Tests: two leagues alternated hit the cache; the ninth key evicts the oldest; `cached_only` still answers `None` on a miss. No route, no schema field. Gate: ruff and the inner loop.
- [x] **F-10 v20c's clip, the code shipped off.** (2026-10-09, the Mac shift: PR #13 gated 62 of 62 on the golden re-recorded after the 2026-10-08 retrain, `-m slow` 137 of 137, merged.) v20 spec §2 v20c "The clip (S)", code only: `MU_BOUNDS: tuple[float, float] | None = None` in `models/dixon_coles.py` (the spec's value when the arm turns it on is `(0.2, 3.5)`, named in the docstring); when set, `DixonColesModel.predict` clips `lam` and `mu` before `fixture_outcomes`, so every derived number comes off one pmf (ruling 6), and logs the lever line `DC_CLIP n=… of …`. Off (`None`) is byte-identical to today. Tests on a fitted toy model, both settings. The head half, the replay, the `xfail` removal and the blend-weight reading stay the Mac's; the clip is not turned on here. If `dixon_coles.py` or anything else the diff touches is imported by `tests/test_golden_board.py` or `tests/test_pipeline.py`, it is `needs-mac` under **Merging** step 2, so take it only when no other `needs-mac` PR is open. Gate: ruff and the inner loop.

- [x] **F-11 The empty state's command, in the ledger's face.** GUIDE §12.4's v14 residual, under ROADMAP candidate 7: `kit/EmptyState.tsx`'s shell command is a bare `<code>`, so it borrows the browser's monospace face, which `kit/tokens.test.ts` cannot see. Give the `<code>` an explicit face from `styles/theme.css`'s tokens; the mono face stays confined to the job log and the plan trace (CLAUDE.md, Frontend rules), so the default is the sans face with tabular figures, the ledger's chip-like box kept. Extend `tokens.test.ts` so a bare `<code>` (no face class) in `hubs/` or `kit/` fails, and fix `hubs/planning/OverridesCard.tsx`'s `<code>` the same way if it is bare. GUIDE §12.4's line struck. No route, no schema field. Gate: ruff, the inner loop, `npm run check` (vitest's Errors line read).
- [ ] **F-12 v20d's price-term Brier, the script.** v20 spec §2 v20d "The term's worth, as a second reading": `scripts/v20d_brier.py` reads `data/live/price_log.parquet` and, over every `(snap_date, code)` with a `drop` reading (`price_change_percent < 0`, the same test `price_timing.py` applies) and a row the next day, prints `V20D_BRIER {...}` with n, the term's Brier of `min(1, |price_change_percent| / 100)` against "fell overnight" (`now_cost` down), the base-rate Brier over the same rows, and both counts the spec's ≥ 30 could mean (drop rows and distinct drop days), the verdict read against drop days. Read-only: it writes nothing and changes no default. A missing or short log prints the line with `n=0` and a reason, never a traceback. Tests on a temporary synthetic log (a fall, a hold, a gap day, a missing next day). The real reading is the Mac's, transcribed into the spec's §6 by the night shift. Gate: ruff and the inner loop.
- [ ] **F-13 v20c's head half, the script.** Depends on F-10. v20 spec §2 v20c "Head half": `scripts/v20c_head.py` re-implements the half-season folds `walk_forward_cs` defines (that function needs an odds file and yields only `p_cs_model`, so it is not called) on both settings of `dixon_coles.MU_BOUNDS` (off, and the spec's `(0.2, 3.5)`), restoring the module value afterwards, and prints `V20C_HEAD {...}`: log-loss and Brier of `p_cs` against realised clean sheets and MAE of `e_gc` against goals against, over all fixtures and over the extreme subset (unclipped `p_cs` outside 0.02–0.85 or `e_gc` outside 0.15–4.0), with the spec's pass rule evaluated in the line. It does not edit `dixon_coles.py` (F-10 owns that), turns nothing on, and the real reading is the Mac's. Tests on a small synthetic match history where the clip bites. Gate: ruff and the inner loop.

## Inbox

Notes from Anu's phone land here, newest last.

- (empty)

## The Mac (not the cloud)

`AnuGnane/autopilot` `NIGHTSHIFT.md`: the golden gate on `needs-mac` branches and then their merge, the golden board on `main` after a day of merges, the K ≥ 5 role replay, the advise run when the laptop is open before a deadline. It runs by itself whenever the laptop is open and on power.
