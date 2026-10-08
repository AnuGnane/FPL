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
- [ ] **F-3 The web re-run button banks a price reading first.** ROADMAP candidate 7's second half, and the shape of candidate 14. If the only path runs through an orchestrator-only file (`web/jobs.py`, `advise.py`), stop and write the PR as a design note: the diff you would make, in the PR body, for Anu to apply. Gate: ruff, the inner loop, `npm run check`.
- [x] **F-4 Top-10k threshold scrape.** ROADMAP candidate 3: a scraper for a weekly top-10k score threshold with a recorded fixture under `tests/fixtures/`, parsed and stored like the other live readers in `src/gaffer/`, behind a config flag only if one already exists (no new `Config` field: pin 62). No new job kind: run it as an anonymous JobRegistry job if it runs at all. Gate: ruff and the inner loop with the fixture; a live fetch only if the sandbox's network allows it, recorded either way.
- [x] **F-5 The install box, from the agent's side.** `scripts/install_automation.sh`: a `--status` flag that prints each `com.gaffer.*` job's loaded state and next fire time, and a `README` line under "Operational" in the ROADMAP. The agent never runs `launchctl load`; the flag only reads. Gate: shellcheck if available, otherwise `zsh -n`.
- [x] **F-6 `P(top-10k)` reads the threshold log.** ROADMAP candidate 3's remainder (W4 §5.3's data-gated row). `league_sim.simulate_field_rank` returns `p_top10k: None` beside `TOP10K_WAITING`, a sentence F-4 made false. Compute it from `data.top_threshold.threshold_series(season)`: the chance that my season total after this gameweek, i.e. the banked total plus this week's simulated `mine`, clears the 10,000th total projected for this gameweek. The projection is the last banked threshold plus the mean weekly rise over the banked weeks; state that rule in the docstring. Keep a null with a rewritten `waiting_for` sentence while fewer than two gameweeks are banked or my season total is unknown. Edit `league_sim.py` and `web/routers/league_sim.py` only, with no new route and no schema field (`p_top10k` and `top10k_waiting_for` already exist). Tests use a temporary threshold log. Gate: ruff, the inner loop, and `npm run check` if any frontend copy changes.
- [x] **F-7 v20c step zero, the replay harness sees the team model.** v20 spec §2 v20c "Step zero" and ruling 3. `backtest.py` gains `REPLAY_TEAM_MODEL = False`. When it is on, the weekly loop builds the horizon's club-fixture rows from the player rows (`team_code`, `opp_code`, `was_home`, `gw`), predicts them through `models["team"]` and merges `p_cs`/`e_gc` onto the player rows as `predict.py:152-174` does, with no market and the `DEFAULT_P_CS` fill. It logs the lever line: the min, the max and the count of distinct `p_cs` values. Off is byte-identical to today's path. Tests cover both settings on a synthetic frame. The harness ships **off**. The K = 5 re-baseline pair (`MULTISEED_DONE v20c0-harness-*`) is the Mac's and is not run here. If the merge needs `predict.py` or anything `tests/test_golden_board.py` or `tests/test_pipeline.py` imports, title the PR `needs-mac` under **Merging** step 2, which allows at most one open `needs-mac` PR. Gate: ruff and the inner loop.

## Inbox

Notes from Anu's phone land here, newest last.

- (empty)

## The Mac (not the cloud)

`AnuGnane/autopilot` `NIGHTSHIFT.md`: the golden gate on `needs-mac` branches and then their merge, the golden board on `main` after a day of merges, the K ≥ 5 role replay, the advise run when the laptop is open before a deadline. It runs by itself whenever the laptop is open and on power.
