# Holiday queue (6 to 23 October 2026)

Anu is away with a phone and, now and then, the laptop. Scheduled cloud agents work this queue one package a run and open a PR; Anu approves from the phone. Nothing reaches `main` without that approval. The playbook is in the private repo `AnuGnane/autopilot`.

`CLAUDE.md` rules, including the pins, the orchestrator-only files, the secrets rule and explicit-path staging. This file only says what a cloud run may do, how it reports, and what is queued. A holiday package is small enough that one agent does it directly: no subagents, no cycle branch, no screenshots gate. The full cycle machinery is for when Anu is back.

## Where you are running

A Linux sandbox cloned from GitHub. `config.toml`, `config.local.toml`, `data/`, `models/`, `reports/` and `logs/` are untracked and do not exist here. So:

- The runnable gates are `uvx ruff check src tests`, `.venv/bin/pytest -q -m "not slow and not golden"` (after `uv sync`) and `cd frontend && npm ci && npm run check`. Tests that need local data skip or fail here; the first package finds out which and records it. The golden gate and every replay run on the Mac in the night shift.
- Never create a `config.toml`. Never write a key or token into any file. There is no odds key here and nothing needs one.
- Do not touch the orchestrator-only files listed in `CLAUDE.md`, do not move a pin, do not add a job kind or a `Config` field. A package that would need any of that stops and says so in its PR instead.
- `git add` explicit paths only.

## One package a run

1. `git fetch origin`. A package is **done** when its box below is ticked on `main`. It is **in review** when a branch `holiday/<id>` (or `claude/holiday-<id>`) exists on origin and is not merged into `main`; leave it alone. It is **blocked** when a package it depends on is not done.
2. Take the first package that is neither done, in review nor blocked. If there is none, stop; write one line saying so.
3. Branch from `origin/main` as `holiday/<id>` (if the push is refused, `claude/holiday-<id>`). Subject lines `<type>(holiday): ...`, one change per commit.
4. Tick the package's box in this file in the same branch.
5. Open the PR with the body below. Then stop. Do not start a second package.

A ruling is a decision only Anu can make. Do not block on it: pick a default, state it in the PR, and carry on. If Anu merges without comment, the default stands.

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

- [ ] **F-S1 The v20 spec.** `docs/superpowers/specs/2026-10-07-v20-model-cycle-design.md`, written the way the v19 design was (`specs/2026-09-15-v19-programme-design.md`): research first (`docs/GUIDE.md` §12.5, `docs/superpowers/ROADMAP.md` "Candidates" 11, 12 and 14, the K ≥ 5 role replay under "One experiment", `CONVENTIONS.md`), then one arm per section with its gate and verdict rule pre-registered before anything runs: the bonus head fed `e_goals`, `e_assists` and `position`; the Dixon-Coles floor on `e_gc_model` measured by removing v19g's xfail mark; the price reading banked minutes before the solve; the role replay at K ≥ 5. Each arm names the seed bases, the control, the spread rule and what withdraws it. The spec is the deliverable; no code. Replays run on the Mac in the night shift, one seed at a time (`CLAUDE.md`'s memory note).

### Implementation (Opus, 12:00 London)

- [ ] **F-1 CI on pull requests.** `.github/workflows/ci.yml`: `uvx ruff check src tests`, `pytest -q -m "not slow and not golden"` under `uv`, and `cd frontend && npm ci && npm run check`, on every PR and on `main`. Python 3.12 (`.python-version`). The PR records which tests skipped or were deselected for lack of local data, and why, so a green tick on later PRs means what it says. Do not weaken a test to make CI pass; deselect by marker or path and say so.
- [ ] **F-2 Tidy for projections.** ROADMAP candidate 7, the residual "`reports/projections/` unpruned": extend `gaffer tidy` so it names and prunes projection reports by the rule the GUIDE gives for `tidy`'s scope, keeping the API snapshots (v19h §1 calls them a corpus). Tests with a temporary tree. Gate: ruff and the inner loop.
- [ ] **F-3 The web re-run button banks a price reading first.** ROADMAP candidate 7's second half, and the shape of candidate 14. If the only path runs through an orchestrator-only file (`web/jobs.py`, `advise.py`), stop and write the PR as a design note: the diff you would make, in the PR body, for Anu to apply. Gate: ruff, the inner loop, `npm run check`.
- [ ] **F-4 Top-10k threshold scrape.** ROADMAP candidate 3: a scraper for a weekly top-10k score threshold with a recorded fixture under `tests/fixtures/`, parsed and stored like the other live readers in `src/gaffer/`, behind a config flag only if one already exists (no new `Config` field: pin 62). No new job kind: run it as an anonymous JobRegistry job if it runs at all. Gate: ruff and the inner loop with the fixture; a live fetch only if the sandbox's network allows it, recorded either way.
- [ ] **F-5 The install box, from the agent's side.** `scripts/install_automation.sh`: a `--status` flag that prints each `com.gaffer.*` job's loaded state and next fire time, and a `README` line under "Operational" in the ROADMAP. The agent never runs `launchctl load`; the flag only reads. Gate: shellcheck if available, otherwise `zsh -n`.

## Inbox

Notes from Anu's phone land here, newest last.

- (empty)

## Night shift (the Mac, not the cloud)

`AnuGnane/autopilot` `NIGHTSHIFT.md`: the golden gate on open holiday branches, the K ≥ 5 role replay, the Thursday advise run when the laptop is open before a deadline.
