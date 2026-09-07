# CLAUDE.md

gaffer: an advisor-only Fantasy Premier League tool. Python (`src/gaffer`)
predicts points with LightGBM component models and plans transfers with a
MILP; a React app (`frontend/`) serves the advice at `gaffer ui`. It never
logs into FPL and never makes transfers.

Read `docs/GUIDE.md` for how everything works and `docs/superpowers/ROADMAP.md`
for what is open. This file holds the rules for working in the repo.

## Commands

```
uv run gaffer advise                     # the weekly run (needs models/)
uv run gaffer ui --no-open-browser --port 8927
.venv/bin/pytest -q                      # Python suite (~4300 tests)
cd frontend && npx tsc --noEmit && npx vitest run   # types + ~910 tests
cd frontend && npm run dev               # Vite on :5173, proxies /api to :8927
cd frontend && npm run build             # emits src/gaffer/web/static/ (untracked)
.venv/bin/python scripts/gen_types.py    # schemas.py -> frontend/src/schemas.json
```

Read vitest's `Errors  N error` line as a failure; an unhandled rejection does
not change its exit code. After any change to `src/gaffer/web/schemas.py`,
regenerate types, run `frontend/src/types.generated.test.ts`, and commit
`schemas.json` and `types.generated.ts` together. `frontend/src/types.ts` is
hand-written and must not be regenerated.

One `gaffer ui` process at a time. The job runner is per-instance, so a second
worker breaks job polling silently.

## Layout

- `src/gaffer/` — `advise.py` (the weekly run), `ladder.py` (rungs and
  restraint), `brief.py` (LLM prose with a truth check), `decisions.py`,
  `review.py`, `optimize/` (MILP), `models/`, `features/`, `web/` (FastAPI:
  `app.py`, `jobs.py`, `routers/`, `schemas.py`).
- `frontend/src/` — `hubs/` (This Week, Planning, Players, League, Live,
  Model), `kit/` (shared components and tokens), `api/`, `styles/theme.css`.
- `tests/` — pytest; `tests/test_v*_degradation.py` are the rails, one per
  cycle, that pin counts and honesty rules (see below).
- `scripts/` — replay drivers (`v7b_replay.py`, `seed_stats.py`), launchd
  plists, `install_automation.sh`, `gen_types.py`.
- `docs/superpowers/` — `CONVENTIONS.md` (measurement rules), `ROADMAP.md`,
  `research/`, `specs/`, `plans/`.
- Untracked and machine-local: `config.toml`, `config.local.toml`, `data/`
  (except `data/manager_tenures.toml`), `models/`, `reports/`, `logs/`,
  `src/gaffer/web/static/`, `.superpowers/`, `.claude/`.

## Secrets

`config.toml` holds the bookmaker odds key under `[odds] api_key`. Never write
its value into any file, prompt, plan, summary or commit. Refer to it by name
only. Subagents never open `config.toml`. Before every push:

```
V="$(sed -n '/^\[odds\]/,/^\[/p' config.toml | grep '^api_key' | cut -d'"' -f2)"
[ "${#V}" -ge 8 ] || echo "extraction failed"
git grep -c "$V" HEAD          # must print nothing
git show main:config.toml      # must fail
```

## Git

- Stage explicit paths only. Never `git add -A` or `git add .`. Never stage
  `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `.superpowers/`,
  `config.toml`, `config.local.toml`, `src/gaffer/web/static/`.
- Work on a branch per cycle (`v16-restraint` style); merge to `main`
  fast-forward only, after the gates pass and the user approves screenshots.
- Commit messages: `feat(v16): ...`, `fix(v16): ...`, `test(v16): ...`,
  `docs: ...`. One line, present tense, says what changed and why.

## Pins and protected files

The degradation rails pin counts that a change must not move silently. When
one fails, the message names the rule and the file that owns it. Do not edit a
rail to make it pass; change the pin only when the plan says so, in its own
commit.

| Pin | Value | Where |
|---|---|---|
| API routes | 51 | `tests/test_v11_degradation.py` |
| `JOB_KINDS` | 12 | pinned in the degradation rails; never add a kind, run new work as an anonymous JobRegistry job |
| `Config` fields | 59 | `tests/test_v13_degradation.py` |

Orchestrator-only files, which subagent implementers must not touch:
`src/gaffer/advise.py`, `set_pieces.py`, `optimize/**`, `web/jobs.py`,
`web/routers/whatif.py`, `tests/test_advise.py`, `test_odds.py`,
`test_web_jobs.py`, every pre-existing `tests/test_v*_degradation.py`, and
`scripts/s2_replay.py`. A plan that needs a change there records the ruling and
the orchestrator makes the diff.

## How a cycle runs

Research → spec (`docs/superpowers/specs/`, gate and verdict rule written
before anything runs) → plan (`docs/superpowers/plans/`) → subagent-driven
implementation on a branch (fresh implementer per task, spec review then code
review between tasks) → gates → screenshot approval → ff-merge → push →
security ritual → GUIDE, ROADMAP and memory updated.

The measurement rules in `docs/superpowers/CONVENTIONS.md` are house rules:
every replay gate runs at least three seed bases and quotes the spread, every
comparison carries its raw control arm, gates are pre-registered, the
orchestrator runs them (never the implementer), a failing arm ships off behind
its flag with the result recorded, and the `*_ARM_DONE` lines are transcribed
into the spec because `logs/` is gitignored.

Replay: `scripts/v7b_replay.py --arm <arm> --tag <tag> --seed-base <n>`. One
seed takes about 20 minutes and 1.6 GB; run seeds sequentially, two in
parallel have been OOM-killed here.

## Frontend rules

Tailwind v4 with tokens in `styles/theme.css`; `kit/tokens.test.ts` enforces
the ledger style across `frontend/src`: no `rounded-full`, no card radius, no
shadow, no gradient, no raw hex outside `theme.css`, mono face only in the job
log and plan trace, tabular figures, no retired colour or class, `Chip` not
`Badge`, fixture difficulty as a tone. Charts use the one grey palette. Pages
render in dark and light; screenshots for a gate come from
`frontend/scripts/shots.sh <stage>`.

## Writing style in code and docs

Comments and docstrings cite the cycle and section that introduced a rule
(`v16 §4`), and say why, not what. Test names are sentences
(`test_an_agreeing_objective_is_not_repeated`). Docs go in the GUIDE and
ROADMAP at the end of a cycle, not scattered in new files.
