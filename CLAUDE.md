# CLAUDE.md

gaffer: an advisor-only Fantasy Premier League tool. Python (`src/gaffer`)
predicts points with LightGBM component models and plans transfers with a
MILP; a React app (`frontend/`) serves the advice at `gaffer ui`. It never
logs into FPL and never makes transfers.

Read `docs/GUIDE.md` for how everything works and `docs/superpowers/ROADMAP.md`
for what is open. This file holds the rules for working in the repo.

## Commands

```
uv run gaffer advise                     # the weekly solve (needs models/); since
                                         # v17d it chains the brief, as the web job does
uv run gaffer brief                      # rewrite the LLM brief alone
uv run gaffer ui --no-open-browser --port 8927
.venv/bin/pytest -q                      # Python suite (~4400 tests)
.venv/bin/pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py
                                         # the golden gate (~15 min); -rs so a stale
                                         # board's skip names the file; 0 skipped is a pass
cd frontend && npx tsc --noEmit && npx vitest run   # types + ~990 tests
cd frontend && npm run dev               # Vite on :5173, proxies /api to :8927
cd frontend && npm run build             # emits src/gaffer/web/static/ (untracked)
```

Read vitest's `Errors  N error` line as a failure; an unhandled rejection does
not change its exit code.

One `gaffer ui` process at a time. The job runner is per-instance, so a second
worker breaks job polling silently.

### Regenerating types after a change to `src/gaffer/web/schemas.py`

```
cd frontend && npm run types              # writes src/schemas.json and src/types.generated.ts
cd frontend && npm run types -- --check   # exits 1 naming any file that drifted
```

Commit `schemas.json` and `types.generated.ts` together. `frontend/src/types.ts`
is hand-written and must never be regenerated.

## Layout

- `src/gaffer/` — `advise.py` (`gather_inputs` then `build_advice`, v17g),
  `inputs.py` (the frozen `Inputs`/`Outputs` seam), `served.py` (the
  `ServedPlan` the advice JSON *is*, v17f), `pipeline.py` (`weekly_run`, the
  one weekly path, v17d), `config.py` (`config_in_force()`, the one cached
  view, v17e), `ladder.py` (rungs and restraint), `brief.py` (LLM prose with
  a truth check), `decisions.py`, `review.py`, `optimize/` (MILP), `models/`,
  `features/`, `web/` (FastAPI: `app.py`, `jobs.py`, `routers/`,
  `schemas.py`).
- `frontend/src/` — `hubs/` (This Week, Planning, Players, League, Live,
  Model), `kit/` (shared components and tokens), `api/`, `styles/theme.css`.
- `tests/` — pytest. The rails that pin counts and honesty rules live in
  `tests/test_v*_degradation.py` (v4c to v13), in `tests/test_v16_restraint.py`
  (the CLI's restraint lines; its source-order pins moved to
  `tests/test_served_plan.py` in v17f and became behaviour in v17g), in
  `tests/test_web_job_kinds*.py`, in `tests/test_golden_board.py` with
  `tests/test_pipeline.py` (the golden board, v17c), and for the frontend in
  `frontend/src/kit/tokens.test.ts`.
- `scripts/` — replay drivers (`v7b_replay.py`, `replay_pair.sh`,
  `seed_stats.py`), launchd plists, `install_automation.sh`, `gen_types.py`
  (the Python half of `npm run types`; the node half is
  `frontend/scripts/gen_types.ts`).
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
git grep -c "$V" HEAD                          # must print nothing
git log -p origin/main..HEAD | grep -c "$V"    # must print 0
git show main:config.toml                      # must fail
```

The second grep exists because the tip can be clean while an intermediate
commit is not. That is the shape of the open incident: the value reached a
plan document in commit dd47c0a, was removed at the tip, and was pushed. The
rotation and any history rewrite are the user's decision, not the agent's.

## Git

- Stage explicit paths only. Never `git add -A` or `git add .`. Never stage
  `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `.superpowers/`,
  `config.toml`, `config.local.toml`, `src/gaffer/web/static/`.
- Work on a branch per cycle (`v16-restraint` style); merge to `main`
  fast-forward only, after the gates pass and the user approves screenshots.
- Subject line: `<type>(<cycle>): what changed and why`, with `type` one of
  feat, fix, test, style, chore, refactor, perf, docs; `docs:` may be
  unscoped. Body: the trailers the session asks for (Co-Authored-By and
  Claude-Session).

## Pins and protected files

The rails pin counts that a change must not move silently. The headline pins
are bare asserts, so a failure prints the numbers and the test name; the
provenance is in the docstring. Do not edit a rail to make it pass; change a
pin only when the plan says so, in its own commit.

| Pin | Value | Where |
|---|---|---|
| API routes | 51 | `tests/test_v11_degradation.py` |
| `JOB_KINDS` | 12 | `tests/test_web_job_kinds*.py` and several rails; never add a kind, run new work as an anonymous JobRegistry job |
| `Config` fields | 62 | `tests/test_v13_degradation.py` |

`tests/test_v12_w1_degradation.py` is the meta-rail: it asserts the route
total is pinned only in the v11 file and the Config total only in the v13
file. A new cycle bumps those two files, never a new home for the number.

Orchestrator-only files, which subagent implementers must not touch:
`src/gaffer/advise.py`, `set_pieces.py`, `optimize/**`, `web/jobs.py`,
`web/routers/whatif.py`, `tests/test_advise.py`, `test_odds.py`,
`test_web_jobs.py`, every pre-existing `tests/test_v*_degradation.py`,
`tests/test_v16_restraint.py`, `tests/test_web_job_kinds*.py`, and
`scripts/s2_replay.py`. A plan that needs a change there records the ruling and
the orchestrator makes the diff.

## How a cycle runs

Research → spec (`docs/superpowers/specs/`, gate and verdict rule written
before anything runs) → plan (`docs/superpowers/plans/`) → subagent-driven
implementation on a branch (fresh implementer per task, spec review then code
review between tasks) → gates → screenshot approval → ff-merge → push →
security ritual → GUIDE, ROADMAP and memory updated.

The measurement rules in `docs/superpowers/CONVENTIONS.md` are house rules.
The short form: every replay gate runs K >= 3 seed bases and quotes the
spread, and K >= 5 when the arm touches a head the backtest refits (K = 3
there supports only a paired sign test); every comparison carries its raw
control arm; gates are pre-registered; the orchestrator runs them, never the
implementer; a failing arm ships off behind its flag with the result recorded;
the `*_ARM_DONE` and `MULTISEED_DONE` lines are transcribed into the spec
because `logs/` is gitignored.

Replay: `scripts/v7b_replay.py --arm <arm> --tag <tag> --seed-bases a,b,c`
runs the trio in one process and prints the aggregate `seed_stats.py` and the
spec appendix are built around; `--seed-base <n>` is a single draw.
`scripts/replay_pair.sh` runs an arm against its control. On this machine the
restraint arm takes about 1.6 GB and 20 minutes per seed, and two of those
seeds run concurrently were OOM-killed, so run them one at a time and treat
`CONCURRENT=1` as safe only for lighter arms.

## Frontend rules

Tailwind v4 with tokens in `styles/theme.css`. `kit/tokens.test.ts` scans
`hubs/` and `kit/` for the ledger style: no `rounded-full`, no card radius, no
shadow, no gradient, no six-digit hex outside `theme.css` and the bundled
plain shirt, mono face only in the job log and plan trace, no retired `num`
class, colour or token, `Chip` not `Badge`, fixture difficulty as a tone. The
same rules apply by hand to `App.tsx`, `api/` and anything the scan misses,
and to short hex forms. Use tabular figures for numbers. Charts use the one
grey palette. Pages render in dark and light; screenshots for a gate come from
`frontend/scripts/shots.sh <stage>`.

## Writing style in code and docs

Comments and docstrings cite the cycle and section that introduced a rule
(`v16 §4`), and say why, not what. Test names are sentences
(`test_an_agreeing_objective_is_not_repeated`). Docs go in the GUIDE and
ROADMAP at the end of a cycle, not scattered in new files.
