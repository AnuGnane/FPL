# Gaffer v12 W5 Implementation Plan — the interface

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** six interface items from spec §6 — tab state in the URL, a Settings
tab that edits an overlay file the UI owns, a watchlist list view and the
captain's own note, frozen projection snapshots, a "why this move" trace, and a
generated half of `types.ts`. Nothing on the training path moves. Nothing on
the decision path moves. **No view solves, and the trace is accounting, not a
counterfactual.**

**Architecture:** the honest shape is smaller than the spec in two places,
larger in two others, and one item cannot be built the way the spec describes
it at all.

- **§6.1 (Task 1)** is four hubs, not six. `Live` and `ThisWeek` have no
  `Tabs.Root`; `Model`, `Players` and `League` are uncontrolled
  (`defaultValue`), and `Planning` was already made controlled by v11 (A1).
- **§6.2 (Tasks 2–4)** is the big one and it is bigger than the spec's
  paragraph: an overlay loader in `config.py`, a route (`/api/settings`, the
  cycle's **only** new path, and therefore this plan's **one protected edit** —
  A3), a whitelist that has to survive three of its own nine keys not existing
  yet (A4), a TOML writer, and a tab. Four of the nine whitelist names in the
  spec do not name anything in this tree (A4).
- **§6.3 (Tasks 5–6)** is two unrelated things. The watchlist list view is a
  new tab over an endpoint that is already complete — and it is the only place
  `WatchRow.note` can ever be read, because the star toggle writes `note: ''`
  every time (A5). `captain_note` needs **no server change at all**: it is
  already on the wire inside `AdviceLatest.advice`, which is `dict[str, Any]`
  (A6).
- **§6.4 (Tasks 7–8)** is smaller than it looks and needs **no protected
  edit**. The EP table advise acts on is already persisted, twice, and the
  writer that persists it — `artifacts.save_solve_state` — is unprotected and
  has exactly one call site, on the advise path (A7).
- **§6.5 (Tasks 9–10)** needs **no protected edit either**, and the spec's
  chosen location for it is the one location it must not be in (A8). Every
  input the trace needs is already on disk in `SolveState`; the byte-identity
  gate becomes three tests that are strictly stronger than the one the spec
  asked for.
- **§6.6 (Tasks 11–12)** cannot be built as written. `types.ts` is **not** a
  mirror of `schemas.py`: 28 of its 118 exports have no pydantic source and 15
  more are renames, and `AdviceLatest.advice` is `dict[str, Any]` on the server
  and a hand-written `Advice` interface on the client. A generator that emitted
  `frontend/src/types.ts` would delete a third of the file and break every
  consumer of `advice` (A9). The buildable version splits the file.

**This cycle adds exactly one route** (`/api/settings`, GET + POST — one path
key), one job kind: none, one Config field: none.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, tomllib +
`tomli-w` (already a dependency), pytest; **React 18.3** + TypeScript + vitest +
recharts. (The spec's brief says React 19. `frontend/package.json` pins
`"react": "^18.3.1"`. Nothing in this plan depends on the difference, but no
task may assume a React 19 API.)

**Branch:** `feat/gaffer-v12`, cut at `27f7933` (the spec commit). Authoritative
spec: `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md`.
Measurement rules: `docs/superpowers/CONVENTIONS.md`.

```bash
git rev-parse --abbrev-ref HEAD      # feat/gaffer-v12
git rev-parse HEAD                   # 27f7933...  (the v12 spec commit)
```

**W5 runs last.** W1–W4 merge to `main` before it and this plan's base is
whatever they left, not `27f7933`. Every pin below is therefore stated as
"measured at `27f7933`" **and** "re-measure at W5's base" — Task 0 does the
re-measure and stops if a number moved in a way a task depends on.

**Protected — must show zero diffs at the end (Task 15 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`. This cycle
imports from neither. It *does* import from `src/gaffer/optimize/` — read-only,
for `SEASON_LAST_GW`, `MAX_FREE_TRANSFERS` and `LambdaLookup` — which is not an
edit and needs no authorization.

**This plan contains exactly one STOP: Task 3.** It edits
`tests/test_v11_degradation.py`, which is a pre-existing
`test_*_degradation.py` and therefore protected, because that file is **the
only place in the suite where the absolute route count may be pinned** — v11
made it so deliberately, and a meta-test in the same file enforces it
(`test_only_one_file_pins_the_absolute_route_count`, `:388-404`). §6.2's route
cannot be added without moving that number, and the number cannot be moved
anywhere else. Task 3 enumerates the exact line-groups and does not run until
the orchestrator authorizes it.

Four other candidates looked like they might need a protected edit and none
does:

1. §6.4's snapshot looks like it belongs in `advise.py:1000`. It does not:
   `artifacts.save_solve_state` is unprotected, receives the same pool, and is
   called from exactly one place — that line (A7).
2. §6.5's trace is placed by the spec inside `optimize/milp.py`, protected. It
   does not belong there and does not need to be there: every input is on disk
   (A8).
3. §6.3's `captain_note` looks like it needs a schema field. It does not: the
   payload is served as `dict[str, Any]` (A6).
4. §6.2's whitelist looked like it needed new `Config` fields. It does not:
   `top_n` and `draw_availability` arrive from W1 and W3 as real fields, and
   `price_timing` is never a field at all — it is read through W2's own
   module-level reader, which is why each whitelist entry declares *how* to
   read itself rather than assuming `getattr` (A4).

**If a task nonetheless concludes a further protected edit is required, it
STOPs and reports rather than widening the diff.**

**Staging rule:** every `git add` below names exact files. Never `git add -A`.
Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml`,
`config.local.toml` or `src/gaffer/web/static/`.

**Gate rule (CONVENTIONS §7):** implementers build and never run the gates.
Task 15 is the checklist with G1/G2/G3 unfilled.

**Frontend test runner: `npx vitest run`** from `frontend/`. `npm test` maps to
bare `vitest`, which is watch mode, and it hangs an agent forever.
**Python: `.venv/bin/pytest`.** There is no bare `python` on PATH; use
`.venv/bin/python`.

**Pins, measured at `27f7933`:**

| Pin | At `27f7933` | After W5 |
| --- | --- | --- |
| `len(JOB_KINDS)` | 12 | **unchanged by W5** — no new job kind |
| `len(dataclasses.fields(Config))` | 48 | **unchanged by W5** — `config.local.toml` is a *loader* change, not a field |
| `len(create_app().openapi()["paths"])` | 45 | **+1** — `/api/settings` (GET and POST share one path key) |

```bash
# how all three were measured; Task 0 re-runs this at W5's base
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# 45 12 48   at 27f7933
```

**Where each pin lives after this cycle.** The route total stays pinned in
`tests/test_v11_degradation.py:348` and **nowhere else** — Task 3 changes the
number there and Task 13's own degradation file pins W5's routes **by name**,
never by total, or it trips v11's meta-test. `JOB_KINDS` and `fields(Config)`
are pinned in Task 13's file as "W5 added none", asserted against the value
Task 0 measured, not against 12/48 — W1–W3 will have moved the Config count.

**Suite baselines, re-measured at `27f7933`: 3193 Python tests collected; 655
frontend passed + 1 skipped (68 files).** Task 0 re-measures both at W5's base
and writes the numbers into this header, because every task's final run is
judged against them.

```bash
.venv/bin/pytest -q --collect-only | tail -1   # 3193 tests collected
cd frontend && npx vitest run                  # 655 passed | 1 skipped (68 files)
```

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Twelve. Four of them are findings that change the size of an item, and one
(A9) says an item cannot be built as specified.

### A1 — §6.1 is four hubs, not six, and three of them have to stop being uncontrolled.

Measured, not assumed. `grep -n "Tabs.Root" frontend/src/hubs/*.tsx`:

| Hub | File:line | Today | Tabs |
| --- | --- | --- | --- |
| Model | `Model.tsx:57` | `defaultValue="quality"` | quality, journal, review, season, history, health |
| Players | `Players.tsx:214` | `defaultValue="explorer"` | explorer, compare, matrix |
| League | `League.tsx:181` | `defaultValue="race"` | race, rivals, whatif |
| Planning | `Planning.tsx:85` | **already controlled** — `value={tab} onValueChange={setTab}` over `useState('timeline')` (v11 A6) | timeline, board, whatif, drafts, chips, ticker |
| Live | — | no tabs | — |
| This Week | — | no tabs; it has a pitch/table toggle, which is a *view preference* and explicitly not persisted (`ThisWeek.tsx:31-34`) | — |

**Settled: one hook, `kit/useTabParam.ts`, wired into all four hubs, and This
Week's pitch/table toggle is left alone.** The hook returns
`[tab, setTab]` exactly like `useState`, reads `?tab=` on first render, falls
back to a caller-supplied default when the parameter is absent *or names a tab
the hub does not have*, and writes with `replace: true` so six clicks through a
tab strip do not put six entries in the browser's history.

Two consequences to hold on to. Planning's `onTry` handoff (`Planning.tsx:102`)
calls `setTab('whatif')` and must keep working through the hook, which means
the hook's setter has the same signature. And every hub test already renders
inside `MemoryRouter` (`Model.test.tsx` 11 uses, `Players.test.tsx` 22,
`League.test.tsx` 18, `Planning.test.tsx` 9, `responsive.test.tsx` 12,
`coldclone.test.tsx`), so `useSearchParams` has a router in every existing test.
A hub rendered without one would throw, and Task 1's first verify run is the
check for that.

The unknown-tab fallback is not decoration: `?tab=board` on the Model hub would
otherwise render a Radix root whose value matches no `Tabs.Content`, which is a
blank hub with no error.

### A2 — the overlay is a sibling of `config.toml`, not a fixed path, and an unknown key in a splatted section is the failure that has to be caught.

`load_config(path="config.toml")` takes a path (`config.py:117`) and every test
in the tree passes a `tmp_path` file. An overlay hard-coded to
`Path("config.local.toml")` would be read from the process's working directory
while the base config was read from somewhere else — which under pytest means
the developer's own overlay leaking into a fixture.

**Settled: the overlay is `file.parent / "config.local.toml"`.**

The second half is sharper. `load_config` **splats** two sections into the
dataclass constructor (`config.py:146-147`):

```python
        **raw.get("optimizer", {}),
        **raw.get("data", {}),
```

So a key in `[optimizer]` that is not a `Config` field is a `TypeError` out of
`Config(...)`, which `load_config` does not catch — and `serving_config`
*does* catch it, by falling all the way back to `Config(entry_id=0,
league_id=0)`, silently discarding the user's whole real config. One typo in a
hand-edited overlay would therefore not raise: it would quietly make the news
layer serve against entry 0.

**Settled: `_overlay` drops any key in a splatted section that is not a
`Config` field name, with a printed line naming the key and the file.** Every
other section is read key-by-key by `load_config` and ignores what it does not
recognise already, so no guard is needed there. A malformed overlay — a file
that will not parse — is also ignored with a printed line rather than raised
on, for the same reason: a bad write from the UI must not take every job down.
The Settings payload carries that line so the tab can show it; an overlay that
is being ignored and says nothing is worse than no overlay.

### A3 — the route pin is protected, and §6.2 cannot avoid it.

`tests/test_v11_degradation.py:333-351` is the only absolute route pin in the
suite, and `:388-404` is a meta-test that greps every `tests/test_*.py` for a
`len(paths) == N` pattern and asserts the hit list is exactly
`["test_v11_degradation.py"]`. v11's docstring says the next cycle moves the
number "here, and nowhere else".

The file matches `tests/test_*_degradation.py`, so under this program's rules
it is protected and the edit needs authorization even though v11 pre-authorised
it in prose. **Task 3 is the STOP.** It is the only one.

Note what does *not* need to move in that file: the absence assertion at
`:349-351` forbids paths starting with `/api/board`, `/api/season` or
`/api/compare`. `/api/settings` starts with none of them, so that assertion
stays true and stays untouched.

### A4 — three of §6.2's nine whitelist names are renames, one names a key that cannot exist, one is not a `Config` field at all, and there is no `[solver]` section.

The spec's list is `horizon, decay, lambda_tilt, chip θ priors path, top_n,
bench_weights, itb_value, price_timing, draw_availability`. Against the tree,
**as the orchestrator ruled on 2026-09-02** (rulings 1 and 3, and the
program-wide one):

| Spec name | Real `Config` field | TOML | Type | Where it comes from |
| --- | --- | --- | --- | --- |
| `horizon` | `horizon` | `[optimizer] horizon` | int | shipped (`config.py:41`) |
| `decay` | `decay` | `[optimizer] decay` | float | shipped (`config.py:42`) |
| `itb_value` | `itb_value` | `[optimizer] itb_value` | float | shipped (`config.py:47`) |
| `bench_weights` | **`bench_curve`** | `[optimizer] bench_curve` | `list[float] \| None`, length 3 | shipped (`config.py:62`) |
| `lambda_tilt` | **`lambda_cap`** | `[league] lambda_cap` | float | shipped (`config.py:70`) |
| `chip θ priors path` | **no such key** — the asset is a packaged resource with no path (`assets/__init__.py:53-64`); the only related switch is `decision_priors` | `[scenarios] decision_priors` | bool | shipped (`config.py:60`) |
| `top_n` | `top_n` | **`[optimizer] top_n`** | table `{GKP,DEF,MID,FWD} -> int`, `default_factory` | W1 §2.6 — a real `Config` field, splatted |
| `price_timing` | **not a `Config` field** — popped from `[optimizer]` before the splat and read by a module-level reader (grep `NON_FIELD_OPTIMIZER_KEYS`) | **`[optimizer] price_timing`** | bool | W2 §3.4 |
| `draw_availability` | `draw_availability` | `[scenarios] draw_availability` | bool, default `False` | W3 §4.4 — a real `Config` field |

**There is no `[solver]` section anywhere in this program.** The spec writes
`[solver] top_n` and `[solver] price_timing`; the tree has `[optimizer]` and
nothing else, and W1/W2 put both keys there. Every `[solver]` in the spec reads
`[optimizer]` here.

Three renames, one name for a key that cannot exist (there is no path to
configure — `load_decision_priors` reads
`files("gaffer.assets").joinpath("decision_priors.json")`), and one — the one
that matters most for the implementation — that is **live but invisible to
`dataclasses.fields(Config)`**.

**Settled: the whitelist is a table in `web/settings_keys.py`, every entry
declares how to *read* its current value, and an entry whose reader cannot find
it is dropped at serve time and named.** Two reader kinds, because
`price_timing` forced the distinction:

* `source="config"` — the value is `getattr(load_config(), field)`, and the
  entry is live iff `field in {f.name for f in dataclasses.fields(Config)}`.
  Seven of the nine.
* `source="reader"` — the value comes from a module-level function W2 owns,
  because the key is popped out of `[optimizer]` before the splat and never
  becomes a field. `price_timing` alone. The entry is live iff that function
  imports; the whitelist holds its dotted path and imports it lazily, so a W5
  that lands before W2 drops the row instead of failing to import.

Four things follow and all four are tested:

1. W5 lands green whether or not W1–W3 shipped their keys. A missing key is not
   a bug and not an empty row — it is **absent** from the payload, and the tab
   renders only what it was sent, with the name in `unavailable`.
2. `price_timing` is never looked for in `dataclasses.fields(Config)`, so the
   "is it live" check cannot silently drop a key that is in fact configurable.
   A test asserts exactly one whitelist entry is `source="reader"` and that its
   field name is **not** a `Config` field — if W2 later promotes it, that test
   fails and says so rather than serving a stale reader.
3. The spec's names are recorded as *labels* and the real field names as the
   wire keys, so the tab reads "λ tilt cap" over `lambda_cap` and nobody has to
   guess which one the file wants.
4. `chip θ priors path` becomes `decision_priors`, a boolean, with the label
   "Use calibrated θ/λ priors" and a caption saying the asset ships with the
   package and has no path. Inventing a path key so the spec's word could be
   honoured would be adding a `Config` field for a sentence.

**Writing `price_timing` is unaffected by any of this.** The overlay is a TOML
file and the write goes to `[optimizer] price_timing` exactly as it would for a
field; only the *read-back* differs, which is the whole reason the two kinds
exist.

### A5 — the watchlist note is unreachable today, and the list view is the only thing that can reach it.

`WatchRow` carries `note` and `set_at` (`routers/watchlist.py:47-51`), and
`watchlist.watch(code, note=...)` stores both. The only client is
`Players.tsx:78`, which posts `{ code, note: '' }` for every star. So `note` is
written empty, every time, and rendered nowhere.

**Settled: the list view renders the note and can edit it, through the same
`POST /api/watchlist` the star already uses.** The alternative — a read-only
list — leaves a served field that no code path can ever populate, which is
v9d's `odds_blend_weight` lesson exactly.

One wart is inherited and must be printed rather than hidden:
`watchlist.watch`'s docstring says *"Re-starring replaces the note and the
timestamp"* (`watchlist.py:113`), so saving a note **resets `set_at`**. The
column is therefore labelled **"noted"** and not "watching since", because the
second would be a claim the data does not support.

The star toggle in the explorer is left exactly as it is. Making it preserve an
existing note would mean a GET before every star on a six-hundred-row table,
which is the round trip `Players.tsx:41-44` was written to avoid — but the list
view says so under the table, so a manager who writes a note and then unstars
and re-stars from the explorer knows where it went.

### A6 — `captain_note` is already on the wire and needs no server change.

`Advice.captain_note` exists (`advise.py:147`), is written
(`advise.py:979`), and is serialized into the artifact by
`asdict(advice)`. `AdviceLatest.advice` is `dict[str, Any]`
(`schemas.py:55`), so the whole payload reaches the client untyped and the
field is already there. `cli.py:81` and `report.html.j2:48` both render it; the
web UI does not.

**Settled: one optional field on the hand-written `Advice` interface in
`types.ts`, and one span on This Week.** Zero backend diff.

Two things about the value. It is `""` — not `None` — when the league tilt
changed nothing (`league_mode.py:424-425`), so the render must test
truthiness and not `!= null`, exactly as `cli.py:81` does. And it is a
half-sentence in the server's voice ("covering Dave's last armband"), so it is
rendered verbatim beside `captain_field.note`, which is the convention
`ThisWeek.tsx:256-259` already states for a server sentence.

### A7 — the EP table is already persisted; the snapshot needs no protected edit, and what is actually missing is *versioning*.

The spec asks whether the EP table advise acts on is persisted anywhere. It is,
twice:

* `reports/solve_state_gw{N}.parquet` — the MILP candidate pool, one row per
  `(code, gw)` with **raw** `ep_raw`, plus `cost`, `sell`, `owned`
  (`artifacts.py:52`, `pool_rows` at `:172-188`). This is literally the table
  the solver optimised over.
* `reports/components_gw{N}.parquet` — the per-fixture component breakdown
  including `ep` (`artifacts.py:33-50`).

Both are written on every advise run, and **both are single-slot per gameweek**:
`solve_state_paths(gw)` returns one fixed filename, and `save_solve_state`
overwrites it. Advise runs several times a week — Tuesday, Thursday, again
after Friday's press conferences, sometimes after kickoff — so the file that
exists when Review runs on Tuesday is the **last** run, which may be the
post-deadline one.

The advice *payload* does not have this problem: `ADVICE_HISTORY` keeps 20 runs
and `journal.latest_run_per_gw` (`journal.py:54-95`) already picks *"the newest
one whose filename stamp predates the payload's deadline"* and marks the
payload `post_deadline` when every run is late. `review.model_decisions` reads
through it (`review.py:173`).

**So §6.4 is not "start persisting the EP table". It is "give the EP table the
versioning the advice payload has had since v9c."** Stated that way the work
is:

1. `artifacts.save_solve_state` — **unprotected**, one call site
   (`advise.py:1000`) and that call site is the advise path — also writes
   `reports/projections/<season>-GW<gw>-<stamp>.parquet`. `advise.py` does not
   move.
2. A reader, `artifacts.projection_snapshots(season, gw)` and
   `latest_projection_before(season, gw, deadline)`, applying **journal's own
   rule**: newest stamp strictly before the deadline; if none, newest overall
   plus a `post_deadline` flag.
3. `review.grade_gw` (unprotected) stamps the row; `ReviewGw` gains
   `projection_snapshot`; `ReviewTab` renders it.

`season` is not on `SolveState` and `artifacts.py` does not import
`gaffer.config`. **Settled: the writer reads `serving_config().current_season`**
— the never-raising reader that exists for exactly this problem
(`config.py:250-273`) — and falls back to writing no snapshot, with a printed
line, if it comes back empty. A snapshot filed under the wrong season is worse
than no snapshot, because element ids remap every season and a cross-season read
would silently join the wrong players.

**Retention is stated rather than discovered.** A snapshot is the pool: ~700
codes × horizon weeks × 9 columns, ~40–80 KB of parquet. At four runs a week
over 38 gameweeks that is roughly 6–12 MB a season, in a gitignored directory.
**They are kept for the season and never pruned by this cycle.** W1's
`gaffer tidy` (§2.7) explicitly names its targets and this is not one of them;
adding a pruner here would mean deciding which snapshot Review will want before
Review has ever wanted one.

### A8 — the trace needs no solver edit, and `_decision_scales` is the one place it must not live.

The spec puts the trace "in `_decision_scales`' neighbourhood (authorized edit,
read-only accounting)". Two things are wrong with that.

`_decision_scales` (`milp.py:325-368`) computes autosub frailty weights for
pass two of the minutes-aware solve. It has nothing to do with transfers: it
never sees `buys`, `sells`, `hits` or a price. Its neighbourhood is a solver
internal that runs *between* two solves, and a "read-only accounting" function
placed inside the module that builds the objective is one refactor away from
being read by the objective. The spec's own gate — *"must not change any
decision"* — is best served by making it impossible rather than testing for it.

And it is unnecessary. Every input is already on disk, in the same two files
`routers/plan.py` already loads (`plan.py:145-146`):

| Trace term | Source | Where |
| --- | --- | --- |
| EP over the horizon | `SolveState.pool.ep_raw` per `(code, gw)` | `artifacts.py:52,172-188` |
| decay | `SolveState.opt["decay"]` | `advise.py:737`, serialized at `:1009` |
| hit cost | `SolveState.opt["hit_cost"]`, and the week's `hits` from `plan_by_gw` | `plan.py:155,175` |
| FT terminal value | `SolveState.opt["ft_value"]`, or the λ table rebuilt from the shipped asset when `opt["decision_priors"]` | `ft_value.lambda_from_priors`, `artifacts.py:295-297` does this already |
| θ | `chip_table[].threshold` on the advice payload for a week that plays a chip | `plan.py:127-137` reads the same rows |
| λ tilt | `league_mode.tilt_ep(ep_by, cover, lam)` against `SolveState.lam` / `.cover` | `league_mode.py:295-323`; `artifacts.py:9-20` says this is what the pair is *for* |
| price-timing charge | W2's `owned_price_falls(owned_codes)`, gated on `[optimizer] price_timing` | unprotected reader off the nightly price log; `milp.py` imports it lazily (orchestrator ruling 1) |

**Settled: a new pure module `src/gaffer/trace.py`, called from
`routers/plan.py`. `optimize/**` is not touched, and a test asserts the trace
module is imported by nothing under `src/gaffer/optimize/` and not by
`advise.py`.**

Three things about the numbers, and the third is the one that decides how they
are captioned.

**The EP gain is a slot-swap difference, not a counterfactual.** For a week at
horizon index `i`, a buy `b` paired with a sell `s`:

```
ep_gain = Σ_{k=i..n-1}  decay**k * (ep_raw[b][T[k]] - ep_raw[s][T[k]])
```

`decay**k` with `k` indexing the whole horizon from 0 is the objective's own
`d = decay ** t_i` (`milp.py:598`). What it is *not* is "the plan is this much
better than not doing the transfer" — that is a re-solve, and a re-solve is
exactly what §6.5 forbids. The caption says so in one sentence, because a
reader who sees "+3.2" and is not told will read the stronger claim.

**Hit cost, FT charge and θ are week-level, not per-move.** A week with two
transfers and one hit cannot attribute the hit to one of them; splitting it
would be arithmetic dressed as a finding. They sit on the week and the moves
carry only what is genuinely per-move: the EP gain and the λ tilt.

**The FT number reported is the terminal shadow price, and it is labelled by
its basis.** The objective prices free transfers only at the end of the horizon
(`milp.py:645-660`): flat `ft_value * ftv[T[-1]]`, or, with a λ table,
`Σ_j λ(j, weeks_left) * ftge[j]` with `weeks_left = max(1, SEASON_LAST_GW -
T[-1])`. The trace runs the FT count forward across the plan's own weeks —
`ft_after = min(MAX_FREE_TRANSFERS, prev - n + hits + 1)`, and on a wildcard
week `min(MAX_FREE_TRANSFERS, prev + 1)` with no transfers charged, both read
straight off `milp.py:556-563` — and reports, per week, how many were spent and
what one is worth at the terminal margin (`ft_basis` is `"lambda"` or
`"flat"`). It does **not** claim to have priced the intra-horizon consumption,
because the model does not price it either.

### A9 — §6.6 cannot generate `types.ts`, and the honest version splits the file.

`frontend/src/types.ts` has 118 exported interfaces/types.
`src/gaffer/web/schemas.py` has 127 `BaseModel` classes. They are not the same
set and the divergence is not drift — it is deliberate:

* **28 TS exports have no pydantic source at all.** `Advice`, `AdviceChipRow`,
  `AdvicePlayerRef`, `CaptainField`, `ChipSquadPlayer`, `JobKind`,
  `LeagueWhatIfEvent`, `MoveFrequency`, `ReviewLabel`, `ReviewLaneName`,
  `ScenarioReport`, `Strategy`, `StratifiedTable` — thirteen of them type the
  *inside* of payloads the server declares as `dict[str, Any]` — plus fifteen
  that are renames of pydantic models (see below).
* **15 are renames**: `Calibration`**`Report`**→`CalibrationData`,
  `Confidence`→`ConfidenceData`, `Decomposition`→`DecompositionData`,
  `FixtureMatrix`→`FixtureMatrixData`, `Health`→`HealthData`,
  `History`→`HistoryData`, `Journal`→`JournalData`,
  `LeagueRace`→`LeagueRaceData`, `Misses`→`MissesData`,
  `NewsShadow`→`NewsShadowData`, `PenTracker`→`PenTrackerData`,
  `Quality`→`QualityData`, `Review`→`ReviewData`,
  `RivalDetail`→`RivalDetailData`, `Ticker`→`TickerData`.
* **22 pydantic models have no TS export**, because TS inlines them as object
  literals or never needs them: `AdvicePlayer`, `ArtifactItem`, `ChipWeek`,
  `GapPoint`, `GwPoint`, `HistoryRun`, `JobAccepted`, `JobStarted`,
  `LaunchdHealth`, `LeagueWhatIfPin`, `MinutesOutput`, `ModelHealth`,
  `OddsInfluence`, `PricePoint`, `PriceSeries`, `ReviewAccuracyPoint`,
  `SourceHealth`, `SquadPlayerRef`, `TickerCell`, `TickerTeam`, `Trajectory`,
  `WatchRequest`.
* **Six models carry `Any`** — `AdviceLatest.advice`, `History.backtests`,
  `ModelHealth.metrics`, `Health.model_health`, `CalibrationReport.excluded`,
  `ReviewSummary.best/worst` — and the client narrows every one of them by
  hand. Generated, `AdviceLatest.advice` becomes `{[k: string]: unknown}`, and
  every `advice.captain.name` in the tree stops compiling.

A generator that emitted `frontend/src/types.ts` and a test that asserted
equality would therefore fail on its first run and keep failing until a third
of the file and every consumer of `advice` had been rewritten. That is not
§6.6's cost; it is a different cycle.

**Settled — the file splits, and both halves are checked:**

* `frontend/src/types.generated.ts` — emitted, committed, never hand-edited.
  Every pydantic model except the six `Any`-carrying overrides, under the
  rename map above.
* `frontend/src/types.ts` — keeps the 28 hand-written exports and the six
  overrides, and re-exports the generated file, so **every existing
  `import ... from '../types'` in the tree keeps working unchanged.**
* `frontend/src/schemas.json` — the JSON Schema, emitted by
  `scripts/gen_types.py`, committed. Two tests, each in its own language and
  each in-process:
  * `tests/test_v12_w5_gen_types.py` regenerates the JSON Schema from the live
    models and asserts it equals the committed `schemas.json`;
  * `frontend/src/types.generated.test.ts` runs `json-schema-to-typescript`'s
    `compile()` **as a library** over the committed `schemas.json`, applies the
    rename map, and asserts the result equals the committed
    `types.generated.ts`.

`json-schema-to-typescript` is **not** in `frontend/package.json` today
(checked: it is absent from both dependency blocks, and
`frontend/node_modules/json-schema-to-typescript` does not exist). It is added
to `devDependencies` **pinned exactly, `"json-schema-to-typescript":
"16.0.0"`** — no caret, because a generator whose output can drift between
patch releases turns a diff test into a Tuesday-morning failure nobody caused.
`16.0.0` is the version resolved at planning time (`npm view
json-schema-to-typescript version`); Task 12 re-runs that command, and **if it
returns anything other than 16.0.0, the plan's pin still stands** — this is a
pin, not a "latest".

Calling `compile()` from vitest rather than shelling to `npx` is deliberate: it
needs no network, no `npx` resolution, and no cross-language subprocess inside
a pytest. And the third test is the one that makes the split safe:
`types.test.ts` gains an assertion that the hand-written and generated export
sets are **disjoint**, and that their union contains every name exported today.
A rename that dropped a type would otherwise be a green suite and a red build.

### A10 — the Settings write clears one cache and cannot clear the others, and the notice says which.

`serving_config()` is `@lru_cache(maxsize=1)` and its docstring already warns
that *"editing `[news]` while the web app is up changes nothing until it is
restarted"* (`config.py:262-267`). `load_config()` is not cached, so anything
that calls it per run — the job bodies, `run_advise` — picks up an overlay
immediately.

**Settled: the write calls `serving_config.cache_clear()`, and the payload
carries one server-written sentence the tab renders verbatim.** The sentence
says what is true: a job started after the save reads the new value; a job
already running keeps the one it started with; and a page already rendered
keeps the numbers it fetched. No per-key "restart required" flag, because there
is no key in the whitelist whose reader is bound at import.

### A11 — the settings writer writes TOML by hand for the whitelist's five value shapes, and `tomli-w` does the general case.

`tomli-w>=1.0` is already a project dependency (`pyproject.toml:16`), so there
is no new dependency and no hand-rolled serializer. The overlay is written with
`tomli_w.dump` over a dict the router builds from validated values only — the
whitelist's shapes are `int`, `float`, `bool`, `list[float]` and a
`dict[str, int]` (`top_n`), all of which `tomli-w` writes natively.

**Settled: `tomli_w.dump` through `gaffer.io.atomic_write`, unconditionally**
(orchestrator ruling 2, 2026-09-02: W1 ships it). No inline fallback and no
second copy of the pid-temp + `os.replace` idiom — W1 §2.11 exists precisely so
that the seventh copy is never written. Two writers racing on a settings file
is not a hypothetical: the tab saves per field.

Task 0 still greps for the helper, but as a **stop condition** rather than a
branch: if `gaffer/io.py::atomic_write` is not there, W1 did not land what W5
was told it would, and that is a report to the orchestrator, not a thing for
Task 3 to work around.

### A12 — every new reader in this cycle is season-guarded or explicitly season-free, and the plan says which.

Spec §1: *"Every new element-id-keyed read takes `season` and filters on it."*

* Projection snapshots (§6.4) are **keyed by code, not element** —
  `POOL_COLS` starts `["code", "name", ...]` and carries no `element` — but the
  filename carries the season anyway and the reader takes `season` as a
  required keyword, because a directory of parquet files that spans seasons and
  is selected by a glob is the exact shape of the mistake.
* The trace (§6.5) reads codes out of a solve state that is already one
  gameweek's own file. No season key is needed and none is invented.
* Settings (§6.2) and the watchlist list view (§6.3) read no player-keyed data
  at all — the watchlist is code-keyed and its name resolution goes through
  `routers/watchlist.py:33-45`, unchanged.

---

## Orchestrator rulings, 2026-09-02 — answered, and where each one landed

These were this plan's three open questions plus one program-wide correction.
All four are **settled**; nothing here is still open. They are kept as a record
of what was assumed versus what was ruled, because three tasks were written
against the assumption and rewritten against the ruling.

1. **The price-fall probability has a reader.** W2 ships an unprotected
   `owned_price_falls(owned_codes) -> dict[code, p_fall]`, built from the
   nightly price log plus the official predictor reading, which `milp.py`
   imports lazily. **The trace calls the same reader** and computes
   `price_charge = p_fall × 0.1 × itb_value` **only when `[optimizer]
   price_timing` is on**; otherwise `None` with the note, which is also what
   happens when the reader has no entry for a sold code. **Its module is not
   guessed here — Task 10 greps for it at execution** (`grep -rn "def
   owned_price_falls" src/gaffer`), because a plan that hard-codes an import
   path it never saw is a plan that fails on its first run. Lands in Tasks 9
   (the `price_fall` and `price_timing` parameters) and 10 (the call site).
2. **`gaffer/io.py::atomic_write` ships in W1** and is used unconditionally.
   The inline fallback is deleted. Lands in A11 and Task 3.
3. **The three W1–W3 keys, by name.** `top_n` is a real `Config` field under
   `[optimizer]` with a `default_factory`. `draw_availability` is a real
   `Config` field under `[scenarios]`, default `False`. **`price_timing` is
   not a `Config` field at all** — it is popped out of `[optimizer]` before the
   splat and read by a module-level reader (grep `NON_FIELD_OPTIMIZER_KEYS`),
   so the whitelist reads it through that reader rather than through
   `dataclasses.fields(Config)`. Lands in A4 and Task 3's `settings_keys.py`.
4. **Program-wide: there is no `[solver]` section.** Everywhere the spec writes
   `[solver]`, the tree has `[optimizer]`. Applied throughout this plan.

One thing deliberately **not** done: `review.py:38`'s unused
`load_components` import (`# noqa: F401 — Task 5's import`) is left alone —
recorded, out of scope, and not touched by any task here.

---

## Task 0 — measure the base before writing a line

**Files:** none. Nothing is created, modified or committed. This task produces
numbers that Tasks 3, 13 and 15 depend on, and three stop conditions.

- [ ] **Record the base commit and the three pins.**

```bash
git rev-parse --abbrev-ref HEAD          # expect feat/gaffer-v12
git rev-parse HEAD                       # record: <W5 base sha>
git log --oneline -1

.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print('paths', len(create_app().openapi()['paths']))
print('job_kinds', len(JOB_KINDS))
print('config_fields', len(dataclasses.fields(Config)))"
```

Record all three. At `27f7933` they were `45 12 48`. W1–W4 will have moved
`paths` and `config_fields`; that is expected and is not a stop condition.
**Task 3's new route total is `paths + 1`.**

- [ ] **Confirm the orchestrator's four rulings against the tree.** These are
      **stop conditions**, not questions: each one was ruled on 2026-09-02 and
      three tasks are written against the answer. A grep that comes back empty
      means an earlier workstream did not land what W5 was told it would —
      **stop and report**, do not work around it.

```bash
# Ruling 2 — the atomic-write helper. Required, no fallback.
grep -n "def atomic_write" src/gaffer/io.py

# Ruling 1 — the price-fall reader, and the module it actually lives in.
# Record the dotted path; Tasks 9 and 10 import it by that name and nothing
# in this plan guesses it.
grep -rn "def owned_price_falls" src/gaffer
grep -rn "owned_price_falls" src/gaffer/optimize/milp.py

# Ruling 3 — the non-field optimizer keys, and the reader price_timing needs.
grep -rn "NON_FIELD_OPTIMIZER_KEYS" src/gaffer
.venv/bin/python -c "
import dataclasses
from gaffer.config import Config
have = {f.name for f in dataclasses.fields(Config)}
for name in ['horizon','decay','itb_value','bench_curve','lambda_cap',
             'decision_priors','top_n','draw_availability']:
    print(f'{name:20} {\"field\" if name in have else \"MISSING — stop\"}')
print('price_timing        ',
      'unexpectedly a field — stop and report' if 'price_timing' in have
      else 'not a field, as ruled')"

# Program-wide ruling — there is no [solver] section.
grep -rn "\[solver\]\|raw.get(\"solver\")\|raw.get('solver')" \
  src/gaffer config.example.toml
# expect: no hits. A hit means the program-wide ruling was not applied
# upstream and Task 3's whitelist sections are wrong.
```

Record the price-fall reader's dotted path and the name of the reader that
serves `price_timing` in this plan's rulings section, as a dated line each.
Task 3 and Task 10 both need them written down.

- [ ] **Confirm the protected route pin is where this plan says it is.** If any
      of these three greps disagrees with the expected output, **stop and
      report** — Task 3's enumeration is written against these exact lines.

```bash
grep -n "assert len(paths) ==" tests/test_v11_degradation.py
# expect exactly one hit around line 348

grep -rn "len(paths) ==\|openapi()\[.paths.\]" tests/ | grep -v test_v11
# expect NO hits — v11's meta-test enforces this

grep -rn "fields(Config)) ==" tests/ | wc -l
# record the count; W5 changes none of them
```

- [ ] **Re-measure both suites and write the numbers into this plan's header.**

```bash
.venv/bin/pytest -q --collect-only | tail -1
# at 27f7933: 3193 tests collected
cd frontend && npx vitest run 2>&1 | tail -5
# at 27f7933: Test Files 68 passed (68) / Tests 655 passed | 1 skipped (656)
```

Both must be green **before** any task runs. A red base is a stop-and-report:
this plan cannot tell a failure it caused from one it inherited.

No commit. Task 0 writes nothing.

---

## Task 1 — the open tab is in the URL

**Files:**
- Create: `frontend/src/kit/useTabParam.ts`
- Create: `frontend/src/kit/useTabParam.test.tsx`
- Modify: `frontend/src/kit/index.ts` (one export line)
- Modify: `frontend/src/hubs/Model.tsx` (`:1-2`, `:57`)
- Modify: `frontend/src/hubs/Players.tsx` (`:214`, imports)
- Modify: `frontend/src/hubs/League.tsx` (`:181`, imports)
- Modify: `frontend/src/hubs/Planning.tsx` (`:2`, `:42`, `:85`)
- Create: `frontend/src/hubs/taburl.test.tsx`

Spec §6.1. Four hubs (A1). Nothing here touches the server.

- [ ] **Write the hook's failing test.** `frontend/src/kit/useTabParam.test.tsx`:

```tsx
/**
 * v12 W5 §6.1 — `?tab=` is the open tab.
 *
 * The unknown-tab case is the one that matters: a Radix root whose value
 * matches no `Tabs.Content` renders a blank hub with no error, so a link
 * carrying another hub's tab name has to land on the default instead.
 */
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { useTabParam } from './useTabParam'

const TABS = ['quality', 'journal', 'health'] as const

function wrapper(initial: string) {
  return ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
  )
}

describe('useTabParam', () => {
  it('opens the default when the parameter is absent', () => {
    const { result } = renderHook(() => useTabParam(TABS, 'quality'),
      { wrapper: wrapper('/model') })
    expect(result.current[0]).toBe('quality')
  })

  it('opens the tab the link names', () => {
    const { result } = renderHook(() => useTabParam(TABS, 'quality'),
      { wrapper: wrapper('/model?tab=health') })
    expect(result.current[0]).toBe('health')
  })

  it('falls back to the default for a tab this hub does not have', () => {
    const { result } = renderHook(() => useTabParam(TABS, 'quality'),
      { wrapper: wrapper('/model?tab=board') })
    expect(result.current[0]).toBe('quality')
  })

  it('writes the new tab into the query string', () => {
    const { result } = renderHook(
      () => [useTabParam(TABS, 'quality'), useLocation()] as const,
      { wrapper: wrapper('/model') })
    act(() => { result.current[0][1]('journal') })
    expect(result.current[0][0]).toBe('journal')
    expect(result.current[1].search).toBe('?tab=journal')
  })

  it('keeps every other query parameter', () => {
    const { result } = renderHook(
      () => [useTabParam(TABS, 'quality'), useLocation()] as const,
      { wrapper: wrapper('/model?gw=7') })
    act(() => { result.current[0][1]('journal') })
    expect(result.current[1].search).toContain('gw=7')
    expect(result.current[1].search).toContain('tab=journal')
  })

  it('replaces rather than pushes, so a tab strip is not a history trail', () => {
    const { result } = renderHook(
      () => [useTabParam(TABS, 'quality'), useLocation()] as const,
      { wrapper: wrapper('/model') })
    act(() => { result.current[0][1]('journal') })
    act(() => { result.current[0][1]('health') })
    // MemoryRouter's index does not advance under a replace. Three renders,
    // one entry: the back button leaves the hub rather than walking the tabs.
    expect(result.current[1].key).toBeDefined()
    expect(result.current[1].search).toBe('?tab=health')
  })
})
```

Run it: `cd frontend && npx vitest run src/kit/useTabParam.test.tsx` — it fails
on the missing module (`Failed to resolve import "./useTabParam"`).

- [ ] **Implement the hook.** `frontend/src/kit/useTabParam.ts`:

```ts
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * v12 W5 §6.1 — the open tab, in the query string.
 *
 * A drop-in for the `useState` a controlled `Tabs.Root` needs, so a hub reads
 * `const [tab, setTab] = useTabParam(TABS, 'quality')` and changes one line.
 *
 * Three decisions worth knowing:
 *
 * - An unknown `?tab=` opens the default rather than being honoured. Radix
 *   renders a root whose value matches no `Tabs.Content` as an empty panel
 *   with no error, so `/model?tab=board` — a Planning tab name on the Model
 *   hub — would otherwise be a blank page nobody could diagnose.
 * - The write is `replace: true`. Clicking six tabs is one navigation, not
 *   six: the back button should leave the hub, not walk backwards through the
 *   strip.
 * - Other parameters survive. The hub is not the only thing that may ever put
 *   something in the query string, and a setter that rebuilt the whole search
 *   would silently drop it.
 *
 * Requires a router in scope. Every hub is rendered inside one (App.tsx's
 * `Routes`, and `MemoryRouter` in every hub test).
 */
export function useTabParam(
  tabs: readonly string[], fallback: string,
): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams()
  const asked = params.get('tab')
  const tab = asked !== null && tabs.includes(asked) ? asked : fallback
  const setTab = useCallback((next: string) => {
    setParams((prev) => {
      const out = new URLSearchParams(prev)
      out.set('tab', next)
      return out
    }, { replace: true })
  }, [setParams])
  return [tab, setTab]
}
```

Export it from the kit — `frontend/src/kit/index.ts`, after the
`useMediaQuery` line:

```ts
export { useTabParam } from './useTabParam'
```

Run: `cd frontend && npx vitest run src/kit/useTabParam.test.tsx src/kit/index.test.ts`
— six pass. `index.test.ts` asserts the kit's export surface; if it pins a
count, update that count and say so in the commit.

- [ ] **Write the hubs' failing test.** `frontend/src/hubs/taburl.test.tsx`:

```tsx
/**
 * v12 W5 §6.1 — the four hubs that have tabs, deep-linked.
 *
 * One file rather than four additions, because the claim is about all four at
 * once: every hub with a `Tabs.Root` reads `?tab=` and writes it back. Live
 * and This Week have no tabs and are deliberately absent.
 *
 * Every fetch is rejected. The hubs' *tab strips* are what is under test, and
 * a hub whose strip only renders when its data loads would fail here — which
 * is the right answer, because a deep link has to work on a cold clone too.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import League from './League'
import Model from './Model'
import Planning from './Planning'
import Players from './Players'

const { apiGet, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  errorText: (e: unknown) => String(e),
}))

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

function Search() {
  return <span data-testid="search">{useLocation().search}</span>
}

function show(node: React.ReactNode, at: string) {
  render(
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="*" element={<>{node}<Search /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockRejectedValue(new ApiError('cold'))
})

describe('the tab in the URL', () => {
  it.each([
    ['Model', <Model key="m" />, '/model', 'Health', 'health'],
    ['Players', <Players key="p" />, '/players', 'Fixture matrix', 'matrix'],
    ['League', <League key="l" />, '/league', 'Rivals', 'rivals'],
    ['Planning', <Planning key="n" />, '/planning', 'Chips', 'chips'],
  ])('%s opens the tab the link names', async (_n, node, at, label, value) => {
    show(node, `${at}?tab=${value}`)
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: label }))
        .toHaveAttribute('data-state', 'active')
    })
  })

  it.each([
    ['Model', <Model key="m" />, '/model', 'Health', 'health'],
    ['Players', <Players key="p" />, '/players', 'Fixture matrix', 'matrix'],
    ['League', <League key="l" />, '/league', 'Rivals', 'rivals'],
    ['Planning', <Planning key="n" />, '/planning', 'Chips', 'chips'],
  ])('%s writes the tab it was clicked to', async (_n, node, at, label, value) => {
    show(node, at)
    await userEvent.click(await screen.findByRole('tab', { name: label }))
    await waitFor(() => {
      expect(screen.getByTestId('search').textContent).toBe(`?tab=${value}`)
    })
  })

  it.each([
    ['Model', <Model key="m" />, '/model', 'Quality'],
    ['Players', <Players key="p" />, '/players', 'Explorer'],
    ['League', <League key="l" />, '/league', 'Race'],
    ['Planning', <Planning key="n" />, '/planning', 'Timeline'],
  ])('%s ignores a tab it does not have', async (_n, node, at, first) => {
    show(node, `${at}?tab=not-a-tab`)
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: first }))
        .toHaveAttribute('data-state', 'active')
    })
  })
})
```

Run: `cd frontend && npx vitest run src/hubs/taburl.test.tsx` — the first two
blocks fail for Model, Players and League (uncontrolled roots ignore the URL
and write nothing) and pass for Planning's *third* block only.

- [ ] **Wire the three uncontrolled hubs.** Each is the same three edits.

`frontend/src/hubs/Model.tsx` — import at `:3`, a tab list constant beside
`TAB_CLASS`, and `:57`:

```tsx
import { JobButton, PageHeader, useTabParam } from '../kit'
```

```tsx
// The strip's values, in strip order. Named so `useTabParam` can reject a
// `?tab=` this hub does not have rather than rendering an empty panel.
const TABS = ['quality', 'journal', 'review', 'season', 'history',
              'health'] as const
```

```tsx
  const [tab, setTab] = useTabParam(TABS, 'quality')
```

```tsx
      <Tabs.Root value={tab} onValueChange={setTab}>
```

`frontend/src/hubs/Players.tsx` — the same, with
`const TABS = ['explorer', 'compare', 'matrix'] as const`, default
`'explorer'`, at `:214`. Add `useTabParam` to the existing `../kit` import.

`frontend/src/hubs/League.tsx` — the same, with
`const TABS = ['race', 'rivals', 'whatif'] as const`, default `'race'`, at
`:181`. Add `useTabParam` to the existing `../kit` import.

- [ ] **Move Planning's existing state onto the hook.** `Planning.tsx:42`
      becomes the hook call and `:2` drops nothing else it uses:

```tsx
  const [tab, setTab] = useTabParam(TABS, 'timeline')
```

with, beside `EMPTY_WHATIF`:

```tsx
const TABS = ['timeline', 'board', 'whatif', 'drafts', 'chips',
              'ticker'] as const
```

and `useTabParam` added to the `../kit` import at `:4`. `useState` stays
imported — `gw`, `teamByCode`, `missing` and `whatif` all still use it.
**`Tabs.Root` at `:85` does not change**; it is already
`value={tab} onValueChange={setTab}` and the hook's setter has `useState`'s
signature for the one argument Planning passes. `onTry` at `:102` is untouched
and now moves the URL as well as the tab, which is the point.

Update the comment at `Planning.tsx:22-27`, which currently says the selection
is "Not persisted": it is now in the URL. Replace the last sentence with:

```tsx
// `Tabs.Root` gives no way to do. Since v12 W5 §6.1 the selection lives in
// `?tab=` rather than in a bare `useState`, so the handoff is linkable and a
// reload keeps the reader where he was. Still not a stored *preference* —
// nothing is written to localStorage (`ThisWeek.tsx:31-34`).
```

- [ ] **Verify.**

```bash
cd frontend && npx vitest run
```

All twelve new hub assertions pass and the baseline is unchanged apart from the
additions. **A pre-existing hub test that now fails means a hub was rendered
without a router** — find it, wrap it in `MemoryRouter`, and say so in the
commit rather than loosening the hook.

- [ ] **Commit.**

```bash
git add frontend/src/kit/useTabParam.ts frontend/src/kit/useTabParam.test.tsx \
  frontend/src/kit/index.ts frontend/src/hubs/Model.tsx \
  frontend/src/hubs/Players.tsx frontend/src/hubs/League.tsx \
  frontend/src/hubs/Planning.tsx frontend/src/hubs/taburl.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: the open tab is in the URL, so a hub can be linked to

Four hubs have tabs — Model, Players, League and Planning — and three of them
were uncontrolled. One hook does all four: it reads ?tab= on load, writes it on
change with replace:true so a tab strip is not a history trail, and keeps every
other query parameter.

An unknown ?tab= opens the hub's default rather than being honoured. Radix
renders a root whose value matches no Content as an empty panel with no error,
so /model?tab=board — a Planning tab name on the Model hub — would otherwise be
a blank page with nothing to diagnose.

Planning was already controlled (v11 A6) and only swaps its useState for the
hook, which means the board's "Try these changes" handoff now moves the URL too.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — `config.local.toml` is an overlay `config.py` loads after `config.toml`

**Files:**
- Modify: `src/gaffer/config.py` (`:1-6` imports, a new constant and
  `_overlay` above `load_config`, and `:129` inside `load_config`)
- Create: `tests/test_v12_w5_config_overlay.py`
- Modify: `config.example.toml` (a commented block at the end)
- Modify: `.gitignore` (one line after `:24`)

Spec §6.2, A2. The loader only. Nothing reads or writes it from the web yet —
that is Task 3.

- [ ] **Write the failing test.** `tests/test_v12_w5_config_overlay.py`:

```python
"""v12 W5 §6.2 — config.local.toml overlays config.toml.

The file the Settings tab owns. Everything here is about what happens when it
is absent, malformed, or carries a key `Config` has never heard of — because
the third one is a `TypeError` out of a splatted section, and `serving_config`
catches that by discarding the user's entire real config (config.py:250-273).
"""
from __future__ import annotations

import pytest

from gaffer.config import LOCAL_OVERLAY, Config, load_config

BASE = """
[fpl]
entry_id = 111
league_id = 222

[optimizer]
horizon = 3
decay = 0.85

[league]
lambda_cap = 0.5
"""


@pytest.fixture()
def tree(tmp_path):
    """A config.toml on disk and a writer for its overlay."""
    base = tmp_path / "config.toml"
    base.write_text(BASE)

    def overlay(text: str):
        (tmp_path / LOCAL_OVERLAY).write_text(text)

    return base, overlay


def test_no_overlay_is_the_config_exactly_as_it_was(tree):
    base, _ = tree
    cfg = load_config(base)
    assert (cfg.horizon, cfg.decay, cfg.lambda_cap) == (3, 0.85, 0.5)


def test_the_overlay_wins_key_by_key(tree):
    base, overlay = tree
    overlay("[optimizer]\nhorizon = 5\n")
    cfg = load_config(base)
    assert cfg.horizon == 5
    # decay was not overlaid and must survive: a section-level replace would
    # drop it back to the dataclass default and nothing on the page would say.
    assert cfg.decay == 0.85


def test_it_reaches_a_section_config_toml_never_declared(tree):
    base, overlay = tree
    overlay("[scenarios]\ndecision_priors = false\n")
    assert load_config(base).decision_priors is False


def test_it_overlays_more_than_one_section_at_a_time(tree):
    base, overlay = tree
    overlay("[optimizer]\nhorizon = 6\n\n[league]\nlambda_cap = 0.2\n")
    cfg = load_config(base)
    assert (cfg.horizon, cfg.lambda_cap) == (6, 0.2)


def test_the_overlay_is_a_sibling_of_the_config_it_overlays(tree, tmp_path,
                                                            monkeypatch):
    """Not of the working directory. A hard-coded relative path would let the
    developer's own overlay leak into every fixture that passes a tmp_path."""
    base, _ = tree
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / LOCAL_OVERLAY).write_text("[optimizer]\nhorizon = 99\n")
    monkeypatch.chdir(elsewhere)
    assert load_config(base).horizon == 3


def test_an_unparseable_overlay_is_ignored_and_says_so(tree, capsys):
    """Ignored, not raised on: one bad write from the UI must not take every
    job down, and `serving_config` would swallow the raise by falling back to
    Config(entry_id=0) — the user's whole config, silently gone."""
    base, overlay = tree
    overlay("[optimizer\nhorizon = 5")
    cfg = load_config(base)
    assert cfg.horizon == 3
    out = capsys.readouterr().out
    assert LOCAL_OVERLAY in out and "ignored" in out


def test_an_unknown_key_in_a_splatted_section_is_dropped_not_fatal(tree,
                                                                   capsys):
    """[optimizer] and [data] are splatted into Config(...), so an unknown key
    there is a TypeError. This is the guard that keeps a typo from becoming a
    silent Config(entry_id=0)."""
    base, overlay = tree
    overlay("[optimizer]\nhorizon = 4\nhorzion = 9\n")
    cfg = load_config(base)
    assert cfg.horizon == 4
    assert "horzion" in capsys.readouterr().out


def test_an_unknown_key_in_a_read_by_key_section_is_simply_unread(tree):
    """[league] is read key-by-key, so an unknown key there was never a
    problem and no guard is invented for it."""
    base, overlay = tree
    overlay("[league]\nlambda_cap = 0.3\nnot_a_key = 1\n")
    assert load_config(base).lambda_cap == 0.3


def test_an_empty_overlay_changes_nothing(tree):
    base, overlay = tree
    overlay("")
    assert load_config(base).horizon == 3


def test_the_overlay_cannot_conjure_a_config_without_a_base(tmp_path):
    """The loud "copy config.example.toml" error is the base file's, and an
    overlay beside a missing base does not answer it."""
    from gaffer.errors import GafferError

    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer]\nhorizon = 5\n")
    with pytest.raises(GafferError, match="config.example.toml"):
        load_config(tmp_path / "config.toml")


def test_every_splatted_section_is_guarded_not_just_optimizer():
    """[data] is splatted too (config.py:147). If a third splatted section is
    ever added, this test is where it is noticed."""
    import inspect

    from gaffer import config as mod

    source = inspect.getsource(mod.load_config)
    splatted = {line.split("raw.get(")[1].split(",")[0].strip("\"' ")
                for line in source.splitlines() if "**raw.get(" in line}
    assert splatted == set(mod.SPLATTED_SECTIONS)
```

Run it: `.venv/bin/pytest -q tests/test_v12_w5_config_overlay.py` — every test
fails on `ImportError: cannot import name 'LOCAL_OVERLAY'`.

- [ ] **Implement the overlay.** `src/gaffer/config.py`, immediately above
      `def load_config` (`:117`):

```python
LOCAL_OVERLAY = "config.local.toml"
"""The overlay the Settings tab owns (v12 W5 §6.2).

Read *after* ``config.toml`` and merged over it key by key. It exists so the
UI has a file it may write without ever touching ``config.toml``, which
carries the odds API key and is gitignored for that reason. Spec §8 forbids a
UI that edits ``config.toml``; this is the file it edits instead.
"""

SPLATTED_SECTIONS = ("optimizer", "data")
"""Sections :func:`load_config` splats straight into ``Config(...)``.

A key here that is not a dataclass field is a ``TypeError``, and
:func:`serving_config` catches that by falling all the way back to
``Config(entry_id=0, league_id=0)`` — discarding the user's real config
without a word. So the overlay drops unknown keys in these sections rather
than letting one typo silently re-point the news layer at entry 0. Every other
section is read key-by-key and ignores what it does not recognise already.
"""


def _overlay(raw: dict, base: Path) -> dict:
    """``config.toml``'s tables with ``config.local.toml``'s merged over them.

    A sibling of ``base``, never of the working directory: every test in this
    tree passes a ``tmp_path`` config, and a relative path would read the
    developer's own overlay into the fixture.

    Never raises. A missing overlay is the normal case; an unparseable one is
    ignored with a printed line, because one bad write from the Settings tab
    must not stop every job on the machine. The line is the only signal there
    is, so it names the file and says the word "ignored" — the settings
    endpoint greps for exactly that when it reports the overlay's health.
    """
    local = Path(base).parent / LOCAL_OVERLAY
    if not local.exists():
        return raw
    try:
        extra = tomllib.loads(local.read_text())
    except Exception as exc:  # noqa: BLE001 — a bad overlay is not a crash
        print(f"config: {local} is not readable TOML ({exc}) — ignored, "
              f"using {base} alone")
        return raw
    fields = {f.name for f in dataclasses.fields(Config)}
    out = dict(raw)
    for section, values in extra.items():
        if not isinstance(values, dict) or not isinstance(out.get(section),
                                                          (dict, type(None))):
            out[section] = values
            continue
        merged = dict(out.get(section) or {})
        for key, value in values.items():
            if section in SPLATTED_SECTIONS and key not in fields:
                print(f"config: {local} sets [{section}] {key}, which is not "
                      f"a config field — ignored")
                continue
            merged[key] = value
        out[section] = merged
    return out
```

Add `import dataclasses` to the import block at the top of the file (it
already imports `tomllib`, `dataclass`, `field`, `lru_cache` and `Path`).

Then the one line inside `load_config`, replacing `:129`:

```python
    raw = _overlay(tomllib.loads(file.read_text()), file)
```

- [ ] **Document the file where a user will look.** Append to
      `config.example.toml`:

```toml
# ---------------------------------------------------------------------------
# config.local.toml (v12 W5 §6.2)
#
# An optional file beside this one. Every table in it is merged over the same
# table here, key by key, after this file is read — so it can override one
# setting without restating the section, and it can add a section this file
# never declared.
#
# The Settings tab in the web UI writes it. It never reads or writes
# config.toml, which holds the odds API key.
#
# A key in [optimizer] or [data] that is not a config field is ignored with a
# printed line rather than crashing the run; the same is true of a file that
# will not parse.
# ---------------------------------------------------------------------------
```

And `.gitignore`, after the `config.toml` line at `:24`:

```gitignore
config.local.toml
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_config_overlay.py
.venv/bin/pytest -q tests/ -k "config"
.venv/bin/pytest -q
```

The whole suite, because `load_config` is called by nearly everything. Any
pre-existing config test that fails means the merge is not additive: **stop and
report** rather than adjusting the pre-existing test.

- [ ] **Commit.**

```bash
git add src/gaffer/config.py tests/test_v12_w5_config_overlay.py \
  config.example.toml .gitignore && git commit -m "$(cat <<'EOF'
feat: config.local.toml overlays config.toml, key by key

The file the Settings tab will own. Spec §8 forbids a UI that edits
config.toml — it carries the odds API key — so the UI gets a second file that
is merged over the first after it is read, per table and per key, and can
introduce a section config.toml never declared.

The guard worth reading is the one on [optimizer] and [data]. Those two are
splatted straight into Config(...), so an unknown key there is a TypeError —
and serving_config catches TypeError by falling back to Config(entry_id=0,
league_id=0), which discards the user's entire real config without a word. One
typo in a hand-edited overlay would have quietly re-pointed the news layer at
entry 0. Unknown keys in those sections are now dropped with a printed line.

The overlay is a sibling of the config it overlays, not of the working
directory: every test here passes a tmp_path config, and a relative path would
have read the developer's own overlay into the fixtures.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — 🛑 STOP — `GET/POST /api/settings`, and the one protected line it moves

> **STOP. Do not begin this task until the orchestrator has read the
> enumeration below and authorized it.** It is the only protected edit in this
> plan.

**Protected file touched:** `tests/test_v11_degradation.py` — a pre-existing
`tests/test_*_degradation.py`.

**Why it cannot be avoided.** §6.2 adds a route. The absolute route count is
pinned in exactly one place in the suite, by v11's design, and a meta-test in
the same file (`test_only_one_file_pins_the_absolute_route_count`, `:388-404`)
greps every `tests/test_*.py` for a `len(paths) == N` pattern and asserts the
hit list is `["test_v11_degradation.py"]`. Pinning the new total anywhere else
turns that test red. Not pinning it at all leaves `:348` asserting the old
number, which turns *that* test red. There is no third option.

**The enumeration, as the file stands at `27f7933`.** W1 also adds a route
(`/api/meta/freshness`, spec §2.9) and will have moved this number first, so
**Task 3 re-reads the file before editing and re-states the actual before/after
to the orchestrator if the text differs from what is quoted here.**

*Line-group 1 — `tests/test_v11_degradation.py:333-337`, the docstring's first
sentence.*

Before:

```python
def test_the_route_total_did_not_move_and_this_is_where_it_is_pinned(
        tmp_path, monkeypatch):
    """45 at the branch point (3404fc3) and 45 now: every serve-side change
    this cycle made is an additive field on a model that already existed.
```

After (`<N>` is Task 0's measured total, `<N+1>` the new one):

```python
def test_the_route_total_did_not_move_and_this_is_where_it_is_pinned(
        tmp_path, monkeypatch):
    """<N+1> routes. 45 at v11's branch point (3404fc3); v12 added the rest.

    # v12 W5 §6.2 (specs/2026-09-01-gaffer-v12-program-design.md)
    W5 adds exactly one path key, ``/api/settings`` — GET and POST share it —
    and this is the one place in the suite that number may be written down.
```

*Line-group 2 — `tests/test_v11_degradation.py:348`, the assertion.*

Before:

```python
    assert len(paths) == 45
```

After:

```python
    assert len(paths) == <N+1>   # v12 W5 §6.2
    assert "/api/settings" in paths
```

**What is deliberately not touched.** The absence assertion at `:349-351`
forbids paths beginning `/api/board`, `/api/season` or `/api/compare`.
`/api/settings` begins with none of them, so it stays true and stays as it is.
The meta-test at `:388-404` is untouched and must stay green — **W5 writes no
`len(paths) == N` anywhere else, including in its own degradation file
(Task 13).**

**Files:**
- Create: `src/gaffer/web/settings_keys.py`
- Create: `src/gaffer/web/routers/settings.py`
- Modify: `src/gaffer/web/schemas.py` (three models, appended)
- Modify: `src/gaffer/web/app.py` (`:70-94` import + one `include_router`)
- Modify: `tests/test_v11_degradation.py` (**protected**, two line-groups above)
- Create: `tests/test_v12_w5_settings.py`

- [ ] **Write the failing test.** `tests/test_v12_w5_settings.py`:

```python
"""v12 W5 §6.2 — the Settings endpoint.

Each whitelist entry declares how to read its own current value (plan A4):
seven from `dataclasses.fields(Config)`, one — `price_timing` — from a
module-level reader W2 owns, because that key is popped out of `[optimizer]`
before the splat and never becomes a field. Three of the nine arrive from W1,
W2 and W3, so absence is a first-class answer here, not a fixture problem.
"""
from __future__ import annotations

import json

import pytest
import tomllib
from fastapi.testclient import TestClient

from gaffer.config import LOCAL_OVERLAY, serving_config
from gaffer.web.app import create_app
from gaffer.web.settings_keys import WHITELIST, live_keys

BASE = """
[fpl]
entry_id = 111
league_id = 222

[optimizer]
horizon = 3
decay = 0.85
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(BASE)
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


def overlay(tmp_path) -> dict:
    path = tmp_path / LOCAL_OVERLAY
    return tomllib.loads(path.read_text()) if path.exists() else {}


def test_the_panel_names_every_live_key_and_no_dead_one(client):
    body = client.get("/api/settings").json()
    served = {row["key"] for row in body["rows"]}
    assert served == set(live_keys())
    assert served <= {entry.field for entry in WHITELIST}


def test_exactly_one_entry_is_read_through_a_reader_and_it_is_price_timing():
    """Orchestrator ruling 3, 2026-09-02. price_timing is popped out of
    [optimizer] before the splat, so it never becomes a Config field and a
    getattr-based liveness check would drop the one key that is in fact
    configurable."""
    import dataclasses

    from gaffer.config import Config

    readers = [e for e in WHITELIST if e.source == "reader"]
    assert [e.field for e in readers] == ["price_timing"]
    fields = {f.name for f in dataclasses.fields(Config)}
    assert "price_timing" not in fields, (
        "price_timing became a Config field — move it to source='config' and "
        "delete its reader rather than serving a stale one")
    assert ":" in readers[0].reader


def test_every_config_kind_entry_names_a_real_config_field():
    import dataclasses

    from gaffer.config import Config

    fields = {f.name for f in dataclasses.fields(Config)}
    absent = [e.field for e in WHITELIST
              if e.source == "config" and e.field not in fields]
    # Empty at W5's base: W1 ships top_n and W3 ships draw_availability. A
    # non-empty list here is a workstream that did not land, and the panel
    # reports it in `unavailable` rather than crashing — which the next test
    # covers. This one exists to make the difference visible.
    assert absent == [] or set(absent) <= {"top_n", "draw_availability"}


def test_no_entry_writes_to_a_solver_section():
    """Program-wide ruling: there is no [solver] table. The spec writes
    `[solver] top_n` and `[solver] price_timing`; both are [optimizer]."""
    assert {e.section for e in WHITELIST} == {"optimizer", "league",
                                              "scenarios"}


def test_price_timing_is_written_into_optimizer_like_any_other_key(client,
                                                                   tmp_path):
    """The read is special; the write is not. The overlay is TOML either way."""
    if "price_timing" not in set(live_keys()):
        pytest.skip("W2's price_timing reader is not in this build")
    assert client.post("/api/settings",
                       json={"key": "price_timing",
                             "value": True}).status_code == 200
    assert overlay(tmp_path)["optimizer"]["price_timing"] is True


def test_a_key_this_build_does_not_have_is_reported_not_hidden(client):
    """W1/W2/W3 supply three of the nine. If one of them did not ship, the
    tab has to say so — a silently shorter form is a setting nobody can find
    and nobody knows is missing."""
    body = client.get("/api/settings").json()
    missing = set(body["unavailable"])
    assert missing == {e.field for e in WHITELIST} - set(live_keys())
    for name in missing:
        assert name in json.dumps(body)


def test_every_row_carries_the_value_the_config_actually_has(client):
    rows = {r["key"]: r for r in client.get("/api/settings").json()["rows"]}
    assert rows["horizon"]["value"] == 3
    assert rows["decay"]["value"] == 0.85


def test_a_row_says_where_its_value_came_from(client, tmp_path):
    rows = {r["key"]: r for r in client.get("/api/settings").json()["rows"]}
    # horizon is in config.toml; lambda_cap is in neither file.
    assert rows["horizon"]["source"] == "base"
    assert rows["lambda_cap"]["source"] == "default"


def test_a_write_lands_in_the_overlay_and_never_in_config_toml(client,
                                                               tmp_path):
    before = (tmp_path / "config.toml").read_text()
    body = client.post("/api/settings", json={"key": "horizon", "value": 5})
    assert body.status_code == 200
    assert overlay(tmp_path) == {"optimizer": {"horizon": 5}}
    assert (tmp_path / "config.toml").read_text() == before


def test_the_written_value_comes_back_on_the_same_response(client):
    rows = {r["key"]: r for r in
            client.post("/api/settings",
                        json={"key": "horizon", "value": 5}).json()["rows"]}
    assert rows["horizon"]["value"] == 5
    assert rows["horizon"]["source"] == "local"


def test_two_writes_do_not_overwrite_each_other(client, tmp_path):
    client.post("/api/settings", json={"key": "horizon", "value": 5})
    client.post("/api/settings", json={"key": "decay", "value": 0.7})
    assert overlay(tmp_path) == {"optimizer": {"horizon": 5, "decay": 0.7}}


def test_a_null_value_removes_the_key_and_falls_back(client, tmp_path):
    """The only way out of a bad edit without hand-editing the file the UI
    owns."""
    client.post("/api/settings", json={"key": "horizon", "value": 5})
    rows = {r["key"]: r for r in
            client.post("/api/settings",
                        json={"key": "horizon", "value": None}).json()["rows"]}
    assert rows["horizon"]["value"] == 3
    assert rows["horizon"]["source"] == "base"
    assert overlay(tmp_path).get("optimizer", {}) == {}


def test_a_key_outside_the_whitelist_is_refused_in_the_lab_shape(client,
                                                                 tmp_path):
    body = client.post("/api/settings",
                       json={"key": "odds_api_key", "value": "hunter2"})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "unknown_setting"
    assert not (tmp_path / LOCAL_OVERLAY).exists()


def test_a_value_out_of_bounds_is_refused_and_writes_nothing(client, tmp_path):
    body = client.post("/api/settings", json={"key": "decay", "value": 4.0})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "out_of_range"
    assert "0" in body.json()["detail"]["error"]
    assert not (tmp_path / LOCAL_OVERLAY).exists()


def test_a_value_of_the_wrong_type_is_refused(client):
    body = client.post("/api/settings", json={"key": "horizon", "value": "5"})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "wrong_type"


def test_a_bool_is_not_an_int(client):
    """`isinstance(True, int)` is True in Python and `horizon = true` would be
    written to the overlay as a boolean, which tomllib reads back as one."""
    body = client.post("/api/settings", json={"key": "horizon", "value": True})
    assert body.status_code == 422


def test_the_bench_curve_needs_exactly_three_weights(client):
    body = client.post("/api/settings",
                       json={"key": "bench_curve", "value": [0.3, 0.2]})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "wrong_type"


def test_the_write_clears_the_serving_config_cache(client):
    """serving_config is lru_cached for the life of the process (config.py
    :262-267). A save that did not clear it would leave the news layer on the
    old value with nothing on the page to say so."""
    assert serving_config().horizon == 3
    client.post("/api/settings", json={"key": "horizon", "value": 6})
    assert serving_config().horizon == 6


def test_the_panel_carries_the_sentence_about_what_a_save_reaches(client):
    note = client.get("/api/settings").json()["apply_note"]
    assert "already running" in note


def test_an_unreadable_overlay_is_reported_rather_than_thrown(client,
                                                              tmp_path):
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer\nhorizon = 5")
    body = client.get("/api/settings")
    assert body.status_code == 200
    assert LOCAL_OVERLAY in body.json()["overlay_error"]
    assert body.json()["rows"]


def test_a_healthy_overlay_reports_no_error(client, tmp_path):
    client.post("/api/settings", json={"key": "horizon", "value": 5})
    assert client.get("/api/settings").json()["overlay_error"] is None


def test_a_cold_clone_with_no_config_is_a_200_that_says_so(tmp_path,
                                                           monkeypatch):
    """Every other read endpoint degrades rather than 500s and this one is
    the endpoint a new user reaches first."""
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/settings")
    assert body.status_code == 200
    assert body.json()["rows"] == []
    assert "config.toml" in body.json()["overlay_error"]
    serving_config.cache_clear()
```

Run it: `.venv/bin/pytest -q tests/test_v12_w5_settings.py` — every test fails
on `ModuleNotFoundError: gaffer.web.settings_keys`.

- [ ] **Implement the whitelist.** `src/gaffer/web/settings_keys.py`:

```python
"""The nine settings the UI may edit (v12 W5 §6.2).

A whitelist, not a schema dump. Everything in ``Config`` that is not here is
untouchable from the web: the odds API key above all, but also the entry and
league ids, the training seasons, and every news switch whose failure mode is
a silently degraded availability pass.

Four of the spec's nine names do not name anything in this tree and are
mapped here rather than in prose (plan A4):

* ``bench_weights`` is ``bench_curve``;
* ``lambda_tilt`` is ``lambda_cap`` — λ itself is *computed* per gameweek and
  stored on the solve state, so there is nothing to configure but its cap;
* ``chip θ priors path`` is not a path. ``load_decision_priors`` reads a
  resource packaged with ``gaffer.assets`` (``assets/__init__.py:53-64``) and
  there is no filesystem location to point at; the only related knob is
  ``decision_priors``, which decides whether the asset is consulted at all;
* the spec's ``[solver]`` section does not exist. ``top_n`` and
  ``price_timing`` are ``[optimizer]`` keys (orchestrator ruling, 2026-09-02).

And one entry is not a ``Config`` field at all. ``price_timing`` is popped out
of ``[optimizer]`` before the splat and read by a module-level reader in W2
(grep ``NON_FIELD_OPTIMIZER_KEYS``), so its current value cannot come from
``getattr(cfg, ...)``. That is what :data:`SettingKey.source` exists for:
``"config"`` reads the dataclass, ``"reader"`` imports a dotted path lazily.
Writing is identical either way — the overlay is a TOML file and the write
goes to ``[optimizer] price_timing`` exactly as it would for a field.

An entry whose reader cannot find it is dropped by :func:`live_keys` and named
in the panel's ``unavailable`` list, because a form that is quietly a field
shorter is a setting nobody can find and nobody knows is gone.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from gaffer.config import Config


@dataclass(frozen=True)
class SettingKey:
    field: str
    """The wire key. Also the ``Config`` field where ``source`` is
    ``"config"``."""
    section: str
    """The TOML table the overlay writes it into. ``optimizer``, ``league`` or
    ``scenarios`` — there is no ``solver`` table in this tree."""
    toml_key: str
    """The key inside that table. Not always the field name — ``[scenarios]``
    deliberately shortens its keys (``n``, ``seed``), so this is stated per
    entry rather than assumed."""
    label: str
    kind: str
    """``int`` | ``float`` | ``bool`` | ``floats3`` | ``pool``."""
    lo: float | None
    hi: float | None
    help: str
    source: str = "config"
    """``"config"`` — the value is ``getattr(load_config(), field)``, live iff
    ``field`` is a dataclass field. ``"reader"`` — the value comes from
    :attr:`reader`, because the key never becomes a field."""
    reader: str = ""
    """``"module.path:function"`` for a ``"reader"`` entry, called with no
    arguments. Imported lazily and per call, so a W5 that somehow lands before
    W2 drops the row rather than failing to import at start-up."""


WHITELIST: tuple[SettingKey, ...] = (
    SettingKey("horizon", "optimizer", "horizon", "Horizon (gameweeks)",
               "int", 1, 8,
               "How many gameweeks the solver plans over."),
    SettingKey("decay", "optimizer", "decay", "Decay per gameweek",
               "float", 0.0, 1.0,
               "How much less a point in week two is worth than one in week "
               "one."),
    SettingKey("itb_value", "optimizer", "itb_value", "Value of money in the bank",
               "float", 0.0, 1.0,
               "Points per £1m held back. Priced in points, like the hit cost."),
    SettingKey("bench_curve", "optimizer", "bench_curve", "Bench weights",
               "floats3", 0.0, 1.0,
               "Three weights, first to third outfield substitute. Empty "
               "falls back to one flat bench weight."),
    SettingKey("lambda_cap", "league", "lambda_cap", "λ tilt cap",
               "float", 0.0, 2.0,
               "The most the league tilt may push the pool. λ itself is "
               "computed each week; this is its ceiling."),
    SettingKey("decision_priors", "scenarios", "decision_priors",
               "Use calibrated θ/λ priors", "bool", None, None,
               "Off falls back to the flat pre-v4c thresholds. The asset "
               "ships with the package and has no path to configure."),
    SettingKey("top_n", "optimizer", "top_n", "Candidate pool per position",
               "pool", 1, 200,
               "How many players per position reach the solver. A smaller "
               "pool solves faster and can exclude a player you own."),
    # Not a Config field: W2 pops it out of [optimizer] before the splat. The
    # dotted path below is what Task 0 recorded from
    # `grep -rn NON_FIELD_OPTIMIZER_KEYS src/gaffer` — verify it before
    # committing rather than trusting this line.
    SettingKey("price_timing", "optimizer", "price_timing",
               "Charge price timing", "bool", None, None,
               "Charges a sell that is scheduled for a later week by the "
               "chance the player drops tonight. Never rewards a rise.",
               source="reader", reader="gaffer.optimize.policy:price_timing"),
    SettingKey("draw_availability", "scenarios", "draw_availability",
               "Draw availability in the sweep", "bool", None, None,
               "Each scenario draws whether each player is available, so "
               "\"bought in N%\" reflects availability risk."),
)

BY_FIELD = {entry.field: entry for entry in WHITELIST}


def _call_reader(entry: SettingKey):
    """A ``"reader"`` entry's current value, or ``KeyError`` if it has none.

    Imported per call rather than at module scope: the reader lives in a
    workstream that may not have landed, and a settings page that cannot be
    imported is worse than one that is a row shorter.
    """
    module, _, name = entry.reader.partition(":")
    try:
        import importlib

        return getattr(importlib.import_module(module), name)()
    except Exception as exc:  # noqa: BLE001 — an absent reader is a dropped row
        raise KeyError(entry.field) from exc


def current_value(entry: SettingKey, cfg):
    """One entry's value, however it has to be read. ``KeyError`` if absent."""
    if entry.source == "reader":
        return _call_reader(entry)
    if entry.field not in {f.name for f in dataclasses.fields(Config)}:
        raise KeyError(entry.field)
    return getattr(cfg, entry.field)


def live_keys(cfg=None) -> list[str]:
    """The whitelist entries this build can actually read a value for.

    Introspected per call rather than at import, for two reasons: the module is
    imported once per process and the answer must not be cached across a hot
    reload, and ``price_timing``'s reader lives in W2 — asking at import time
    would make an absent workstream a start-up failure instead of a missing
    row.

    ``cfg`` is the already-loaded config when the caller has one; ``None``
    loads it, and a config that will not load leaves only the ``"reader"``
    entries live, which is the honest answer rather than an empty page.
    """
    if cfg is None:
        try:
            from gaffer.config import load_config

            cfg = load_config()
        except Exception:  # noqa: BLE001 — a read is never worth a 500
            cfg = None
    out = []
    for entry in WHITELIST:
        if entry.source == "config" and cfg is None:
            continue
        try:
            current_value(entry, cfg)
        except KeyError:
            continue
        out.append(entry.field)
    return out
```

**The `reader` dotted path above is a placeholder for Task 0's measurement.**
`gaffer.optimize.policy:price_timing` is this plan's best guess at where W2 put
it, and `optimize/**` is protected — so if the reader really does live there,
**nothing about that is a problem** (importing from a protected module is not
editing it), but the *name* must come from Task 0's
`grep -rn "NON_FIELD_OPTIMIZER_KEYS" src/gaffer` and not from this line.
Correct it before running the tests.

- [ ] **Implement the schemas.** Append to `src/gaffer/web/schemas.py`:

```python
class SettingRow(BaseModel):
    """One editable setting, as the Settings tab receives it (v12 W5 §6.2)."""

    key: str
    label: str
    kind: Literal["int", "float", "bool", "floats3", "pool"]
    value: Any
    """Whatever the merged config holds. ``None`` only for ``bench_curve``,
    where it means "no curve — one flat bench weight", which is a real
    setting and not an absent one."""
    lo: float | None = None
    hi: float | None = None
    section: str
    help: str
    source: Literal["local", "base", "default"]
    """Which file this value came from. ``local`` is ``config.local.toml``,
    ``base`` is ``config.toml``, ``default`` is the dataclass — and the three
    are different facts: only a ``local`` value can be reset."""


class SettingsPanel(BaseModel):
    rows: list[SettingRow] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)
    """Whitelisted settings this build's ``Config`` does not have. Named
    rather than dropped: a form that is quietly shorter is a setting nobody
    can find and nobody knows is missing."""
    overlay_error: str | None = None
    """Why ``config.local.toml`` is being ignored, or ``None``. Also carries
    the "no config.toml at all" case, which is the state a cold clone is in."""
    apply_note: str


class SettingWrite(BaseModel):
    key: str
    value: Any = None
    """``None`` removes the key from the overlay, so the value falls back to
    ``config.toml`` or the dataclass default."""
```

- [ ] **Implement the router.** `src/gaffer/web/routers/settings.py`:

```python
"""GET/POST ``/api/settings`` — the nine settings the UI may edit.

Writes ``config.local.toml`` and **never** ``config.toml`` (spec §8: a UI that
edits ``config.toml`` is out of scope, and that file carries the odds API key).
The overlay is merged over the base by ``config.load_config`` — see
``config.py``'s ``_overlay``.

Refusals use the what-if lab's ``{constraint, error, players}`` shape so the
client has one error shape for every write endpoint, exactly as
``routers/watchlist.py:26-30`` does. ``players`` is always empty here; a
setting is not a player, and inventing a second refusal shape for one endpoint
is how a UI ends up with two error renderers.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from fastapi import APIRouter, HTTPException

from gaffer.config import LOCAL_OVERLAY, load_config, serving_config
from gaffer.io import atomic_write
from gaffer.web.schemas import SettingRow, SettingsPanel, SettingWrite
from gaffer.web.settings_keys import (BY_FIELD, WHITELIST, current_value,
                                      live_keys)

router = APIRouter(prefix="/api", tags=["settings"])

APPLY_NOTE = (
    "Saved to config.local.toml. A job started after this save reads the new "
    "value; a job already running keeps the one it started with, and a page "
    "already open keeps the numbers it fetched. Reload to see them change.")

BASE = "config.toml"


def _fail(constraint: str, error: str) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": []})


def _read(path: Path) -> tuple[dict, str | None]:
    """A TOML file as a dict, plus why it could not be read."""
    if not path.exists():
        return {}, None
    try:
        return tomllib.loads(path.read_text()), None
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        return {}, f"{path.name} is not readable TOML ({exc}) — ignored"


def _panel() -> SettingsPanel:
    base_raw, base_err = _read(Path(BASE))
    local_raw, local_err = _read(Path(LOCAL_OVERLAY))
    if not Path(BASE).exists():
        return SettingsPanel(
            rows=[], unavailable=[e.field for e in WHITELIST],
            overlay_error=("no config.toml — copy config.example.toml to "
                           "config.toml and set fpl.entry_id and "
                           "fpl.league_id"),
            apply_note=APPLY_NOTE)
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — the tab must still render
        return SettingsPanel(rows=[], unavailable=[e.field for e in WHITELIST],
                             overlay_error=f"config.toml unreadable ({exc})",
                             apply_note=APPLY_NOTE)
    live = set(live_keys(cfg))
    rows = []
    for entry in WHITELIST:
        if entry.field not in live:
            continue
        if entry.toml_key in (local_raw.get(entry.section) or {}):
            source = "local"
        elif entry.toml_key in (base_raw.get(entry.section) or {}):
            source = "base"
        else:
            source = "default"
        rows.append(SettingRow(
            key=entry.field, label=entry.label, kind=entry.kind,
            # Through `current_value`, never `getattr(cfg, ...)`:
            # `price_timing` is not a Config field and never becomes one, so
            # a getattr here would drop the one row the reader kind exists for.
            value=current_value(entry, cfg), lo=entry.lo, hi=entry.hi,
            section=entry.section, help=entry.help, source=source))
    return SettingsPanel(
        rows=rows,
        unavailable=[e.field for e in WHITELIST if e.field not in live],
        overlay_error=local_err or base_err, apply_note=APPLY_NOTE)


def _checked(entry, value):
    """The value as it will be written, or a refusal.

    ``bool`` is checked before ``int`` throughout: ``isinstance(True, int)``
    is True in Python, so ``horizon = true`` would otherwise reach the overlay
    as a boolean and come back out of tomllib as one.
    """
    kind = entry.kind
    if kind == "bool":
        if not isinstance(value, bool):
            raise _fail("wrong_type", f"{entry.label} is on or off")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _fail("wrong_type", f"{entry.label} is a whole number")
        number = value
    elif kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _fail("wrong_type", f"{entry.label} is a number")
        number = float(value)
    elif kind == "floats3":
        if value is None:
            return None
        if (not isinstance(value, list) or len(value) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       for v in value)):
            raise _fail("wrong_type",
                        f"{entry.label} is exactly three numbers, first to "
                        f"third outfield substitute")
        for v in value:
            if not entry.lo <= float(v) <= entry.hi:
                raise _fail("out_of_range",
                            f"each of {entry.label} is between {entry.lo} "
                            f"and {entry.hi}")
        return [float(v) for v in value]
    elif kind == "pool":
        wanted = ("GKP", "DEF", "MID", "FWD")
        if (not isinstance(value, dict) or set(value) != set(wanted)
                or any(isinstance(v, bool) or not isinstance(v, int)
                       for v in value.values())):
            raise _fail("wrong_type",
                        f"{entry.label} is a whole number for each of "
                        f"{', '.join(wanted)}")
        for v in value.values():
            if not entry.lo <= v <= entry.hi:
                raise _fail("out_of_range",
                            f"each of {entry.label} is between "
                            f"{int(entry.lo)} and {int(entry.hi)}")
        return {k: int(value[k]) for k in wanted}
    else:  # pragma: no cover — a kind with no branch is a wiring bug
        raise _fail("wrong_type", f"{entry.label} cannot be edited here")
    if entry.lo is not None and not entry.lo <= number <= entry.hi:
        raise _fail("out_of_range",
                    f"{entry.label} is between {entry.lo} and {entry.hi}")
    return number


def _write(raw: dict) -> None:
    """The overlay, atomically. Two saves in flight must not interleave.

    Through ``gaffer.io.atomic_write`` (W1 §2.11) rather than a seventh copy of
    the pid-temp + ``os.replace`` idiom — the helper exists so that copy is
    never written again. The tab saves one field at a time, so two writers
    racing on this file is a click, not a hypothetical.

    ``tomli_w.dumps`` rather than ``dump``: the helper owns the file handle,
    and the header comment has to go in front of the tables.
    """
    body = ("# Written by the gaffer web UI (v12 W5 §6.2).\n"
            "# Merged over config.toml, key by key. Safe to hand-edit; a key\n"
            "# that is not a config field is ignored with a printed line.\n\n"
            + tomli_w.dumps(raw))
    atomic_write(Path(LOCAL_OVERLAY), body)


@router.get("/settings", response_model=SettingsPanel)
def settings() -> SettingsPanel:
    return _panel()


@router.post("/settings", response_model=SettingsPanel)
def save(req: SettingWrite) -> SettingsPanel:
    entry = BY_FIELD.get(req.key)
    if entry is None or entry.field not in set(live_keys()):
        raise _fail("unknown_setting",
                    f"{req.key} is not a setting this page may change")
    raw, err = _read(Path(LOCAL_OVERLAY))
    if err:
        # Overwriting a file we could not read would discard whatever else the
        # user had put in it. Refuse and say where to look.
        raise _fail("overlay_unreadable", err)
    section = dict(raw.get(entry.section) or {})
    if req.value is None and entry.kind != "floats3":
        section.pop(entry.toml_key, None)
    else:
        section[entry.toml_key] = _checked(entry, req.value)
    if section:
        raw[entry.section] = section
    else:
        raw.pop(entry.section, None)
    _write(raw)
    # config.py:250-273 caches this for the life of the process, so a save
    # that did not clear it would leave every serve-time seam on the old value
    # with nothing on the page to say so.
    serving_config.cache_clear()
    return _panel()
```

**Read `gaffer/io.py::atomic_write`'s signature before calling it.** The call
above assumes `atomic_write(path, text)` with a `str` body. If W1 shipped it
taking bytes, or as a context manager yielding a handle, adapt *this* call —
do not add an overload to the shared helper, and do not fall back to a local
copy of the idiom.

**A note the implementer must not skip:** `bench_curve` is the one whitelist
entry whose `None` is a *value* ("no curve") rather than a reset. The branch
above sends `None` through `_checked` for `floats3` and writes it — but TOML
has no null, so `tomli_w.dump` would raise. **Settled: for `bench_curve`,
`None` is written as the empty list `[]`, and `config.py` already treats a
`bench_curve` of the wrong length as an error at solve time
(`milp.py:461-465`), so the whitelist's `floats3` branch must reject `[]` as
well.** Change the two lines: `if value is None: return None` becomes a
`raise _fail("wrong_type", ...)` naming that a bench curve is three numbers and
that removing it means resetting the row. Reset (`value: None`) then does the
right thing for every kind through the one `pop` branch, and the `!=
"floats3"` guard above is deleted.

- [ ] **Register the router.** `src/gaffer/web/app.py` — add the import beside
      its siblings and, keeping the list alphabetical, after
      `app.include_router(review.router)` at `:91`:

```python
    app.include_router(settings.router)
```

- [ ] **Move the protected pin** — the two line-groups enumerated at the top of
      this task, and nothing else in that file.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_settings.py
.venv/bin/pytest -q tests/test_v11_degradation.py
.venv/bin/pytest -q

.venv/bin/python -c "
import os, tempfile
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
paths = create_app().openapi()['paths']
print(len(paths)); print('/api/settings' in paths)"
# expect <N+1> and True

git diff --stat -- tests/ | cat
# expect exactly one protected file touched: tests/test_v11_degradation.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/settings_keys.py src/gaffer/web/routers/settings.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py \
  tests/test_v11_degradation.py tests/test_v12_w5_settings.py \
  && git commit -m "$(cat <<'EOF'
feat: GET/POST /api/settings edits the overlay, never config.toml

Nine settings, whitelisted by name in web/settings_keys.py. Everything else in
Config is untouchable from the web — the odds API key first, but also the entry
id, the training seasons, and every news switch whose failure mode is a quietly
degraded availability pass.

Four of the spec's nine names did not name anything in this tree and are mapped
in the module rather than in prose: bench_weights is bench_curve, lambda_tilt is
lambda_cap, "chip θ priors path" is not a path at all — the asset is a packaged
resource with no filesystem location, so the knob is decision_priors — and there
is no [solver] section anywhere, so top_n and price_timing are [optimizer] keys.

The entry worth reading is price_timing. It is not a Config field and never
becomes one: W2 pops it out of [optimizer] before the splat and serves it from a
module-level reader. So each whitelist entry declares *how* to read its current
value — the dataclass, or a lazily imported reader — and a getattr-only liveness
check would have silently dropped the one key that is in fact configurable.
Writing is identical either way; only the read differs.

An entry this build cannot read is named in the panel's `unavailable` list
rather than dropped from the form, because a form that is quietly a field
shorter is a setting nobody can find and nobody knows is gone.

AUTHORIZED PROTECTED EDIT: tests/test_v11_degradation.py, the route-total pin.
v11 made that file the only place in the suite where the absolute route count
may be written down and enforces it with a meta-test, so a cycle that adds a
route has to move the number there and cannot move it anywhere else. One path
key was added and the pin says so by name as well as by count.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the Settings tab

**Files:**
- Create: `frontend/src/hubs/model/SettingsTab.tsx`
- Create: `frontend/src/hubs/model/SettingsTab.test.tsx`
- Modify: `frontend/src/types.ts` (two interfaces, appended)
- Modify: `frontend/src/hubs/Model.tsx` (`TABS`, one trigger, one content)
- Modify: `frontend/src/api/client.ts` — **no.** `apiPost` already covers it.

Spec §6.2, A4, A10. Seventh tab on the Model hub.

**These two interfaces move again in Task 12.** `SettingRow` and
`SettingsPanel` are pydantic models, so the generator emits them; Task 12's
disjointness test is what catches the duplicate, and Task 12 deletes the
hand-written pair. Written by hand here so Task 4 compiles on its own.

- [ ] **Add the types.** Append to `frontend/src/types.ts`:

```ts
/** One editable setting (v12 W5 §6.2). `value` is `unknown` because the five
 *  kinds carry five shapes; `kind` is what narrows it. */
export interface SettingRow {
  key: string
  label: string
  kind: 'int' | 'float' | 'bool' | 'floats3' | 'pool'
  value: unknown
  lo: number | null
  hi: number | null
  section: string
  help: string
  /** Which file the value came from. Only a `local` value can be reset. */
  source: 'local' | 'base' | 'default'
}

export interface SettingsPanel {
  rows: SettingRow[]
  /** Whitelisted settings this build does not have — named, never hidden. */
  unavailable: string[]
  overlay_error: string | null
  apply_note: string
}
```

- [ ] **Write the failing test.** `frontend/src/hubs/model/SettingsTab.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsTab from './SettingsTab'
import type { SettingsPanel } from '../../types'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e),
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

const PANEL: SettingsPanel = {
  rows: [
    { key: 'horizon', label: 'Horizon (gameweeks)', kind: 'int', value: 3,
      lo: 1, hi: 8, section: 'optimizer', help: 'How far it plans.',
      source: 'base' },
    { key: 'decision_priors', label: 'Use calibrated θ/λ priors', kind: 'bool',
      value: true, lo: null, hi: null, section: 'scenarios',
      help: 'Off falls back to flat thresholds.', source: 'local' },
  ],
  unavailable: ['price_timing'],
  overlay_error: null,
  apply_note: 'A job already running keeps the value it started with.',
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockResolvedValue(PANEL)
  apiPost.mockResolvedValue(PANEL)
})

describe('SettingsTab', () => {
  it('renders a control per served row, labelled', async () => {
    render(<SettingsTab />)
    expect(await screen.findByLabelText('Horizon (gameweeks)'))
      .toHaveValue(3)
    expect(screen.getByLabelText('Use calibrated θ/λ priors')).toBeChecked()
  })

  it('names a setting this build does not have', async () => {
    render(<SettingsTab />)
    expect(await screen.findByTestId('settings-unavailable'))
      .toHaveTextContent('price_timing')
  })

  it('saves one key at a time and says so', async () => {
    render(<SettingsTab />)
    const field = await screen.findByLabelText('Horizon (gameweeks)')
    await userEvent.clear(field)
    await userEvent.type(field, '5')
    await userEvent.click(screen.getByRole('button', { name: 'Save Horizon (gameweeks)' }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
        { key: 'horizon', value: 5 })
    })
  })

  it('saves a boolean on the toggle itself, with no second click', async () => {
    render(<SettingsTab />)
    await userEvent.click(await screen.findByLabelText('Use calibrated θ/λ priors'))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
        { key: 'decision_priors', value: false })
    })
  })

  it('offers a reset only where the overlay is what set the value', async () => {
    render(<SettingsTab />)
    await screen.findByLabelText('Horizon (gameweeks)')
    expect(screen.queryByRole('button', { name: /Reset Horizon/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Reset Use calibrated/ }))
      .toBeInTheDocument()
  })

  it('resets by sending a null value', async () => {
    render(<SettingsTab />)
    await userEvent.click(await screen.findByRole('button',
      { name: /Reset Use calibrated/ }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
        { key: 'decision_priors', value: null })
    })
  })

  it('shows the refusal beside the field that caused it', async () => {
    const boom = Object.assign(new Error('bad'),
      { detail: { error: 'Horizon (gameweeks) is between 1 and 8' } })
    apiPost.mockRejectedValueOnce(boom)
    render(<SettingsTab />)
    const field = await screen.findByLabelText('Horizon (gameweeks)')
    await userEvent.clear(field)
    await userEvent.type(field, '9')
    await userEvent.click(screen.getByRole('button', { name: 'Save Horizon (gameweeks)' }))
    expect(await screen.findByTestId('settings-error-horizon'))
      .toHaveTextContent('between 1 and 8')
  })

  it('renders the apply note verbatim', async () => {
    render(<SettingsTab />)
    expect(await screen.findByTestId('settings-apply-note'))
      .toHaveTextContent('A job already running keeps the value it started with.')
  })

  it('renders an overlay error where it cannot be missed', async () => {
    apiGet.mockResolvedValue({ ...PANEL, overlay_error: 'config.local.toml is not readable TOML' })
    render(<SettingsTab />)
    expect(await screen.findByTestId('settings-overlay-error'))
      .toHaveTextContent('not readable')
  })

  it('has an honest empty state on a cold clone', async () => {
    apiGet.mockResolvedValue({
      rows: [], unavailable: ['horizon'], apply_note: 'x',
      overlay_error: 'no config.toml — copy config.example.toml to config.toml',
    })
    render(<SettingsTab />)
    expect(await screen.findByTestId('empty-state')).toHaveTextContent(
      'config.example.toml')
  })

  it('does not blank the form while a save is in flight', async () => {
    render(<SettingsTab />)
    await userEvent.click(await screen.findByLabelText('Use calibrated θ/λ priors'))
    expect(screen.getByLabelText('Horizon (gameweeks)')).toBeInTheDocument()
  })
})
```

Run: `cd frontend && npx vitest run src/hubs/model/SettingsTab.test.tsx` —
fails on the missing module.

- [ ] **Implement the tab.** `frontend/src/hubs/model/SettingsTab.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiGet, apiPost, errorText } from '../../api/client'
import { Card, EmptyState, Loading } from '../../kit'
import type { SettingRow, SettingsPanel } from '../../types'

/**
 * v12 W5 §6.2 — the nine settings the UI may edit.
 *
 * It writes `config.local.toml` through `/api/settings` and never touches
 * `config.toml`, which carries the odds API key. The server owns the
 * whitelist, the bounds, the refusal text and the sentence about what a save
 * reaches; this file renders them and adds no rule of its own. A second
 * statement of a bound here would be a second thing to keep in step with the
 * dataclass.
 *
 * One save per field, deliberately: a form with one Save button has to decide
 * what to do when the third of five writes is refused, and the honest answers
 * are all worse than never being in that state.
 */

function label(row: SettingRow): string {
  return row.label
}

function Field(
  { row, onSave, error, busy }: {
    row: SettingRow
    onSave: (value: unknown) => void
    error: string | null
    busy: boolean
  },
) {
  const [draft, setDraft] = useState(() => JSON.stringify(row.value))

  // Re-seed when the server sends a new value — after a save, or after a
  // reset. Keyed on the serialized value so a re-render with the same answer
  // does not stamp on what the user is typing.
  useEffect(() => { setDraft(JSON.stringify(row.value)) },
    [JSON.stringify(row.value)])

  if (row.kind === 'bool') {
    return (
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={row.value === true}
          disabled={busy}
          onChange={(e) => onSave(e.target.checked)}
        />
        <span>{label(row)}</span>
      </label>
    )
  }

  const numeric = row.kind === 'int' || row.kind === 'float'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2">
        <span>{label(row)}</span>
        <input
          className="w-32 rounded-card border border-border bg-base px-2 py-1"
          type={numeric ? 'number' : 'text'}
          step={row.kind === 'float' ? 0.01 : 1}
          value={numeric ? draft.replace(/"/g, '') : draft}
          disabled={busy}
          onChange={(e) => setDraft(numeric ? e.target.value : e.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={busy}
        className="rounded-card border border-border bg-base px-2 py-1
                   text-text-secondary hover:text-text"
        onClick={() => {
          if (numeric) {
            const n = Number(draft)
            // NaN is sent as the raw string so the *server* refuses it and
            // says why. A client-side "that is not a number" would be a
            // second validator saying almost the same thing.
            onSave(draft.trim() === '' || Number.isNaN(n) ? draft : n)
          } else {
            try {
              onSave(JSON.parse(draft))
            } catch {
              onSave(draft)
            }
          }
        }}
      >
        {`Save ${label(row)}`}
      </button>
    </div>
  )
}

export default function SettingsTab() {
  const [panel, setPanel] = useState<SettingsPanel | null>(null)
  const [failed, setFailed] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    apiGet<SettingsPanel>('/api/settings')
      .then(setPanel)
      .catch(() => setFailed(true))
  }, [])

  function save(key: string, value: unknown) {
    setBusy(key)
    setErrors((prev) => ({ ...prev, [key]: '' }))
    apiPost<SettingsPanel>('/api/settings', { key, value })
      // The response is the whole panel, so a save re-seeds every row's
      // `source` as well as its value — which is what turns the Reset button
      // on for the field that was just written.
      .then((body) => setPanel(body))
      .catch((e) => setErrors((prev) => ({ ...prev, [key]: errorText(e) })))
      .finally(() => setBusy(null))
  }

  if (failed) {
    return (
      <EmptyState
        title="Settings unavailable"
        detail="The server could not be asked what is configurable."
        action="Check that the app is running"
      />
    )
  }
  if (!panel) return <Loading />
  if (panel.rows.length === 0) {
    return (
      <EmptyState
        title="Nothing to configure yet"
        detail={panel.overlay_error
          ?? 'This build exposes none of the editable settings.'}
        action="cp config.example.toml config.toml"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {panel.overlay_error && (
        <p
          data-testid="settings-overlay-error"
          className="rounded-card border border-rust bg-card px-3 py-2
                     text-rust"
        >
          {panel.overlay_error}
        </p>
      )}
      <Card title="Settings">
        <div className="flex flex-col gap-4">
          {panel.rows.map((row) => (
            <div key={row.key} className="flex flex-col gap-1">
              <Field
                row={row}
                busy={busy === row.key}
                error={errors[row.key] || null}
                onSave={(value) => save(row.key, value)}
              />
              <p className="text-text-faint">{row.help}</p>
              {row.source === 'local' && (
                <button
                  type="button"
                  className="self-start text-text-muted hover:text-text"
                  onClick={() => save(row.key, null)}
                >
                  {`Reset ${label(row)}`}
                </button>
              )}
              {errors[row.key] && (
                <p data-testid={`settings-error-${row.key}`}
                   className="text-rust">
                  {errors[row.key]}
                </p>
              )}
            </div>
          ))}
        </div>
      </Card>
      {panel.unavailable.length > 0 && (
        <p data-testid="settings-unavailable" className="text-text-muted">
          {`Not in this build: ${panel.unavailable.join(', ')}. `
           + 'These arrive with the workstreams that introduce them.'}
        </p>
      )}
      {/* The server's own sentence, verbatim — the same convention This Week
          uses for the captain's field note. */}
      <p data-testid="settings-apply-note" className="text-text-muted">
        {panel.apply_note}
      </p>
    </div>
  )
}
```

- [ ] **Add the tab to the Model hub.** `frontend/src/hubs/Model.tsx`: import
      `SettingsTab`, add `'settings'` to `TABS` (last), and add the trigger
      after Health at `:65` and the content after `:76`:

```tsx
          <Tabs.Trigger value="settings" className={TAB_CLASS}>Settings</Tabs.Trigger>
```

```tsx
        <Tabs.Content value="settings"><SettingsTab /></Tabs.Content>
```

- [ ] **Verify.**

```bash
cd frontend && npx vitest run src/hubs/model/SettingsTab.test.tsx \
  src/hubs/Model.test.tsx src/hubs/taburl.test.tsx src/types.test.ts
cd frontend && npx vitest run && npx tsc -b --noEmit
```

`Model.test.tsx` may pin the tab count; if it does, update that number and say
so in the commit.

- [ ] **Commit.**

```bash
git add frontend/src/hubs/model/SettingsTab.tsx \
  frontend/src/hubs/model/SettingsTab.test.tsx frontend/src/types.ts \
  frontend/src/hubs/Model.tsx && git commit -m "$(cat <<'EOF'
feat: a Settings tab that edits the overlay and nothing else

Seventh tab on the Model hub. Every rule lives on the server — the whitelist,
the bounds, the refusal text and the sentence about what a save actually
reaches — and this renders them. A bound restated here would be a second thing
to keep in step with the dataclass.

One save per field. A form with one Save button has to decide what to do when
the third of five writes is refused, and every honest answer to that is worse
than never being in the state.

A setting this build does not have is named under the form, not dropped from
it: three of the nine arrive with W1, W2 and W3, and a form that is quietly
three fields shorter is three settings nobody can find.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — the watchlist is a list, and the note is finally readable

**Files:**
- Create: `frontend/src/hubs/players/WatchlistTab.tsx`
- Create: `frontend/src/hubs/players/WatchlistTab.test.tsx`
- Modify: `frontend/src/hubs/Players.tsx` (`TABS`, one trigger, one content, and
  the `starred` state passed down)

Spec §6.3 first half, A5. No server change: `GET /api/watchlist`,
`POST /api/watchlist` and `DELETE /api/watchlist/{code}` are complete
(`routers/watchlist.py:55-83`), and `WatchRow`/`WatchlistPanel` are already in
`types.ts:1271-1280`.

- [ ] **Write the failing test.** `frontend/src/hubs/players/WatchlistTab.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistTab from './WatchlistTab'
import type { WatchlistPanel } from '../../types'

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  apiDelete: (p: string) => apiDelete(p),
  errorText: (e: unknown) => String(e),
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

const PANEL: WatchlistPanel = {
  rows: [
    { code: 100, name: 'Salah', note: 'if he starts', set_at: '2026-09-01T10:00:00+00:00' },
    { code: 200, name: 'Haaland', note: '', set_at: '2026-08-30T10:00:00+00:00' },
  ],
}

beforeEach(() => {
  apiGet.mockReset(); apiPost.mockReset(); apiDelete.mockReset()
  apiGet.mockResolvedValue(PANEL)
  apiPost.mockResolvedValue(PANEL)
  apiDelete.mockResolvedValue({ rows: [PANEL.rows[1]] })
})

describe('WatchlistTab', () => {
  it('lists every starred player with his note', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByText('Salah')).toBeInTheDocument()
    expect(screen.getByDisplayValue('if he starts')).toBeInTheDocument()
  })

  it('renders an empty note as an empty field, never as a placeholder value',
    async () => {
      render(<WatchlistTab onChange={vi.fn()} />)
      const field = await screen.findByLabelText('note for Haaland')
      expect(field).toHaveValue('')
    })

  it('saves a note through the same POST the star uses', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    const field = await screen.findByLabelText('note for Haaland')
    await userEvent.type(field, 'DGW target')
    await userEvent.click(screen.getByRole('button', { name: 'Save note for Haaland' }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/watchlist',
        { code: 200, note: 'DGW target' })
    })
  })

  it('unstars through DELETE and tells the hub', async () => {
    const onChange = vi.fn()
    render(<WatchlistTab onChange={onChange} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Unstar Salah' }))
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/watchlist/100')
      expect(onChange).toHaveBeenCalledWith([200])
    })
  })

  it('labels the date "noted", because saving a note resets it', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByText(/Noted/)).toBeInTheDocument()
    expect(screen.queryByText(/Watching since/)).toBeNull()
  })

  it('says what re-starring from the explorer does to a note', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('watchlist-caveat'))
      .toHaveTextContent(/replaces the note/)
  })

  it('has an honest empty state', async () => {
    apiGet.mockResolvedValue({ rows: [] })
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('empty-state'))
      .toHaveTextContent('star')
  })

  it('has an empty state when the list cannot be read at all', async () => {
    apiGet.mockRejectedValue(new Error('cold'))
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
  })

  it('shows a failed save beside the row and keeps the typing', async () => {
    apiPost.mockRejectedValueOnce(Object.assign(new Error('nope'),
      { detail: { error: 'note is longer than 200 characters' } }))
    render(<WatchlistTab onChange={vi.fn()} />)
    const field = await screen.findByLabelText('note for Haaland')
    await userEvent.type(field, 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Save note for Haaland' }))
    expect(await screen.findByTestId('watchlist-error-200'))
      .toHaveTextContent('longer than 200')
    expect(field).toHaveValue('x')
  })
})
```

Run: `cd frontend && npx vitest run src/hubs/players/WatchlistTab.test.tsx` —
fails on the missing module.

- [ ] **Implement the tab.** `frontend/src/hubs/players/WatchlistTab.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPost, errorText } from '../../api/client'
import { Card, EmptyState, Loading, PlayerName } from '../../kit'
import type { WatchRow, WatchlistPanel } from '../../types'

/**
 * v12 W5 §6.3 — the starred players, with their notes.
 *
 * The endpoint has carried `note` and `set_at` since v8e and nothing has ever
 * rendered either, because the explorer's star posts `{ code, note: '' }` for
 * every click (`Players.tsx:78`). This is the only surface from which a note
 * can be written or read.
 *
 * `set_at` is labelled "noted" and not "watching since", and the caveat under
 * the table says why: `watchlist.watch` replaces *both* the note and the
 * timestamp on every star (`watchlist.py:113`), so re-starring from the
 * explorer wipes a note and resets the date. That is the store's behaviour,
 * not this view's to change — but a column headed "watching since" would be a
 * claim the data does not support.
 */

function stamp(iso: string): string {
  const at = new Date(iso)
  return Number.isNaN(at.getTime()) ? '—' : at.toISOString().slice(0, 10)
}

function Row(
  { row, onSaved, onRemoved }: {
    row: WatchRow
    onSaved: (panel: WatchlistPanel) => void
    onRemoved: (panel: WatchlistPanel) => void
  },
) {
  const [draft, setDraft] = useState(row.note)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  return (
    <div className="flex flex-col gap-1 border-b border-divider py-2">
      <div className="flex flex-wrap items-center gap-2">
        <PlayerName code={row.code} name={row.name} />
        <span className="text-text-faint">{`Noted ${stamp(row.set_at)}`}</span>
        <button
          type="button"
          className="ml-auto text-text-muted hover:text-text"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            apiDelete<WatchlistPanel>(`/api/watchlist/${row.code}`)
              .then(onRemoved)
              .catch((e) => setError(errorText(e)))
              .finally(() => setBusy(false))
          }}
        >
          {`Unstar ${row.name}`}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label={`note for ${row.name}`}
          className="min-w-0 flex-1 rounded-card border border-border bg-base
                     px-2 py-1"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="button"
          className="rounded-card border border-border bg-base px-2 py-1
                     text-text-secondary hover:text-text"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            setError(null)
            apiPost<WatchlistPanel>('/api/watchlist',
              { code: row.code, note: draft })
              .then(onSaved)
              .catch((e) => setError(errorText(e)))
              .finally(() => setBusy(false))
          }}
        >
          {`Save note for ${row.name}`}
        </button>
      </div>
      {error && (
        <p data-testid={`watchlist-error-${row.code}`} className="text-rust">
          {error}
        </p>
      )}
    </div>
  )
}

export default function WatchlistTab(
  { onChange }: { onChange: (codes: number[]) => void },
) {
  const [panel, setPanel] = useState<WatchlistPanel | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    apiGet<WatchlistPanel>('/api/watchlist')
      .then(setPanel)
      .catch(() => setFailed(true))
  }, [])

  // Every write returns the whole panel, so the hub's star column and this
  // table are re-seeded from the same answer rather than from two guesses.
  function adopt(next: WatchlistPanel) {
    setPanel(next)
    onChange(next.rows.map((r) => r.code))
  }

  if (failed) {
    return (
      <EmptyState
        title="Watchlist unavailable"
        detail="The starred list could not be read. It lives in the tool's
                own store, not in FPL."
        action="Check that the app is running"
      />
    )
  }
  if (!panel) return <Loading />
  if (panel.rows.length === 0) {
    return (
      <EmptyState
        title="Nobody starred yet"
        detail="Star a player from the Explorer tab and he appears here with
                room for a note."
        action="Explorer → star"
      />
    )
  }

  return (
    <Card title="Watchlist">
      <div className="overflow-x-auto">
        {panel.rows.map((row) => (
          <Row key={row.code} row={row} onSaved={adopt} onRemoved={adopt} />
        ))}
      </div>
      <p data-testid="watchlist-caveat" className="mt-2 text-text-faint">
        {'Starring a player again from the Explorer replaces the note and the '
         + 'date, so edit notes here rather than re-starring.'}
      </p>
    </Card>
  )
}
```

- [ ] **Wire the tab into Players.** `frontend/src/hubs/Players.tsx`:
      `TABS` gains `'watchlist'`; a trigger after `matrix` at `:219`; and the
      content after `:299`:

```tsx
          <Tabs.Trigger value="watchlist" className={TAB_CLASS}>Watchlist</Tabs.Trigger>
```

```tsx
        <Tabs.Content value="watchlist">
          {/* The hub already owns `starred` for the explorer's star column
              (`:44`), and every write here returns the whole panel — so the
              two surfaces are re-seeded from one answer instead of drifting. */}
          <WatchlistTab onChange={setStarred} />
        </Tabs.Content>
```

with `import WatchlistTab from './players/WatchlistTab'` beside the other
`./players/` imports.

- [ ] **Verify.**

```bash
cd frontend && npx vitest run src/hubs/players/WatchlistTab.test.tsx \
  src/hubs/Players.test.tsx src/hubs/taburl.test.tsx \
  src/hubs/coldclone.test.tsx
cd frontend && npx vitest run
```

- [ ] **Commit.**

```bash
git add frontend/src/hubs/players/WatchlistTab.tsx \
  frontend/src/hubs/players/WatchlistTab.test.tsx \
  frontend/src/hubs/Players.tsx && git commit -m "$(cat <<'EOF'
feat: the watchlist is a list, and its note is finally readable

WatchRow has carried note and set_at since v8e and nothing rendered either —
the explorer's star posts note:'' on every click, so the field was written
empty every time and shown nowhere. This tab is the only surface from which a
note can be written or read, which is why it edits as well as lists: a served
field no code path can populate is a field that rots.

The date column says "noted", not "watching since". watchlist.watch replaces
both the note and the timestamp on every star, so re-starring from the explorer
resets it — the caveat under the table says so rather than letting a reader
infer a start date the store does not keep.

No server change: the three endpoints were already complete.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — the captain's own note reaches This Week

**Files:**
- Modify: `frontend/src/types.ts` (one optional field on `Advice`, `:91-108`)
- Modify: `frontend/src/hubs/ThisWeek.tsx` (one span in the Squad card action,
  after `:265`)
- Modify: `frontend/src/hubs/ThisWeek.test.tsx` (two cases)

Spec §6.3 second half, A6. **Zero backend diff** — the field is already served.

- [ ] **Write the failing test.** Append to
      `frontend/src/hubs/ThisWeek.test.tsx`, inside its existing describe
      block and using its existing advice fixture builder:

```tsx
  it('renders the captain note the advice run wrote', async () => {
    // v12 W5 §6.3. `captain_note` is written by advise.py:979 and served
    // inside AdviceLatest.advice, which is dict[str, Any] — so it has been on
    // the wire since v4d and rendered only by the CLI and the HTML report.
    renderWith({ ...ADVICE, captain_note: "covering Dave's last armband" })
    expect(await screen.findByTestId('captain-note'))
      .toHaveTextContent("covering Dave's last armband")
  })

  it('draws nothing for the empty note the tilt writes when it changed nothing',
    async () => {
      // league_mode.captaincy_note returns "" — not null — when lam is 0 or
      // the armband did not move (league_mode.py:424-425). An empty chip is
      // worse than no chip.
      renderWith({ ...ADVICE, captain_note: '' })
      await screen.findByText(/Captain/)
      expect(screen.queryByTestId('captain-note')).toBeNull()
    })

  it('draws nothing for a payload written before the field existed', async () => {
    renderWith({ ...ADVICE })
    await screen.findByText(/Captain/)
    expect(screen.queryByTestId('captain-note')).toBeNull()
  })
```

`renderWith` and `ADVICE` are this file's existing helpers; if they are named
differently, use the names in the file and do not rename them.

Run: `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx` — the first
case fails (no such testid).

- [ ] **Add the field to the type.** `frontend/src/types.ts`, in `Advice`
      after `captain_field?: CaptainField`:

```ts
  /** The half-sentence the league tilt puts after the captain's name
   *  ("covering Dave's last armband"). Written by `advise.py:979` and served
   *  inside `AdviceLatest.advice`, which the server declares as
   *  `dict[str, Any]` — so it needs no schema field and has none.
   *
   *  Empty string, not null, when the tilt changed nothing
   *  (`league_mode.py:424-425`). Test it for truthiness, exactly as
   *  `cli.py:81` does. */
  captain_note?: string | null
```

- [ ] **Render it.** `frontend/src/hubs/ThisWeek.tsx`, immediately after the
      `captain_field` span that ends at `:265`:

```tsx
            {/* v12 W5 §6.3 — the run's own half-sentence about why the
                armband moved, rendered verbatim beside the field note for the
                same reason that one is: the claim is made where the data is,
                and a second wording here would be one number in two voices.
                Truthy, not `!= null`: the tilt writes "" when it changed
                nothing. */}
            {advice.captain_note && (
              <span className="text-text-muted" data-testid="captain-note">
                {advice.captain_note}
              </span>
            )}
```

- [ ] **Verify.**

```bash
cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx src/types.test.ts
cd frontend && npx vitest run && npx tsc -b --noEmit
git diff --stat -- src/ | cat     # expect: no Python file touched
```

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/hubs/ThisWeek.tsx \
  frontend/src/hubs/ThisWeek.test.tsx && git commit -m "$(cat <<'EOF'
feat: This Week renders the captain note the advice run already wrote

captain_note has been written by advise.py and served inside
AdviceLatest.advice — dict[str, Any] — since v4d, and only the CLI and the HTML
report have ever rendered it. One optional field on the hand-written Advice
interface and one span; no schema field, no router change, no Python diff.

Truthy rather than != null: league_mode.captaincy_note returns "" when the tilt
changed nothing, and an empty chip beside the captain's name is worse than none.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — every advise run freezes the EP table it acted on

**Files:**
- Modify: `src/gaffer/artifacts.py` (a constant block and four functions,
  appended after `prune_advice_history` at `:549`; and four lines inside
  `save_solve_state`, `:191-217`)
- Create: `tests/test_v12_w5_projections.py`
- Create: `tests/test_v12_w5_projections_degradation.py`

Spec §6.4, A7, A12. **`advise.py` does not move.** `save_solve_state` is
unprotected and its only call site is `advise.py:1000`, on the advise path.

- [ ] **Write the failing test.** `tests/test_v12_w5_projections.py`:

```python
"""v12 W5 §6.4 — the EP table advise acted on, frozen and dated.

The table is already persisted at reports/solve_state_gw{N}.parquet, but that
is one slot per gameweek and advise runs several times a week — Tuesday,
Thursday, after Friday's pressers, sometimes after kickoff. What Review reads
on Tuesday is therefore the *last* run, which may be the post-deadline one.

The advice payload has not had this problem since v9c: ADVICE_HISTORY keeps 20
runs and journal.latest_run_per_gw picks the newest one written before the
deadline. This gives the EP table the same treatment and, deliberately, the
same rule.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import (POOL_COLS, SolveState, latest_projection_before,
                              projection_snapshots, save_solve_state)


def _pool(codes=(100, 200), gws=(5, 6)) -> pd.DataFrame:
    rows = [{"code": c, "name": f"P{c}", "position": "MID", "team_code": 1,
             "cost": 80, "sell": 80, "owned": c == 100, "gw": g,
             "ep_raw": 4.0 + c / 100} for c in codes for g in gws]
    return pd.DataFrame(rows, columns=POOL_COLS)


def _state(gw=5, at="2026-09-01T09:00:00+00:00", pool=None) -> SolveState:
    return SolveState(
        gw=gw, gws=[5, 6], deadline="2026-09-04T17:30:00+00:00",
        generated_at=at, mode="weekly", bank=15, free_transfers=1,
        owned_codes=[100], lam=0.0, league_eo={}, avail_by_gw={},
        opt={"decay": 0.85, "hit_cost": 4},
        pool=_pool() if pool is None else pool)


@pytest.fixture(autouse=True)
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.config.serving_config",
                        lambda: type("C", (), {"current_season": "2026-27"})())
    return tmp_path


def test_saving_a_solve_state_also_freezes_the_pool(here):
    save_solve_state(_state())
    snaps = projection_snapshots("2026-27", 5)
    assert len(snaps) == 1
    frame = pd.read_parquet(snaps[0].path)
    assert list(frame.columns) == POOL_COLS
    assert len(frame) == 4


def test_a_second_run_does_not_overwrite_the_first(here):
    save_solve_state(_state(at="2026-09-01T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-03T18:00:00+00:00"))
    assert len(projection_snapshots("2026-27", 5)) == 2


def test_snapshots_come_back_oldest_first(here):
    save_solve_state(_state(at="2026-09-03T18:00:00+00:00"))
    save_solve_state(_state(at="2026-09-01T09:00:00+00:00"))
    stamps = [s.stamp for s in projection_snapshots("2026-27", 5)]
    assert stamps == sorted(stamps)


def test_another_season_is_not_this_seasons(here, monkeypatch):
    """Element ids remap every season and codes do not, but a directory
    selected by a glob is exactly the shape of that mistake."""
    save_solve_state(_state())
    monkeypatch.setattr("gaffer.config.serving_config",
                        lambda: type("C", (), {"current_season": "2027-28"})())
    save_solve_state(_state())
    assert len(projection_snapshots("2026-27", 5)) == 1
    assert len(projection_snapshots("2027-28", 5)) == 1


def test_another_gameweek_is_not_this_one(here):
    save_solve_state(_state(gw=5))
    save_solve_state(_state(gw=6))
    assert len(projection_snapshots("2026-27", 5)) == 1


def test_the_newest_run_before_the_deadline_wins(here):
    save_solve_state(_state(at="2026-09-01T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-04T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-05T09:00:00+00:00"))   # after
    chosen = latest_projection_before("2026-27", 5,
                                      "2026-09-04T17:30:00+00:00")
    assert chosen.stamp.startswith("20260904T09")
    assert chosen.post_deadline is False


def test_all_runs_late_gives_the_newest_and_flags_it(here):
    """journal.latest_run_per_gw's rule, verbatim: a flagged comparison is
    worth more than a missing row as long as it cannot pass itself off as
    foresight."""
    save_solve_state(_state(at="2026-09-05T09:00:00+00:00"))
    save_solve_state(_state(at="2026-09-06T09:00:00+00:00"))
    chosen = latest_projection_before("2026-27", 5,
                                      "2026-09-04T17:30:00+00:00")
    assert chosen.stamp.startswith("20260906T09")
    assert chosen.post_deadline is True


def test_no_snapshot_at_all_is_None_and_not_an_exception(here):
    assert latest_projection_before("2026-27", 5,
                                    "2026-09-04T17:30:00+00:00") is None


def test_an_unparseable_deadline_takes_the_newest_and_flags_it(here):
    save_solve_state(_state())
    chosen = latest_projection_before("2026-27", 5, "not a date")
    assert chosen is not None
    assert chosen.post_deadline is True


def test_the_solve_state_itself_is_written_exactly_as_before(here):
    """The snapshot is a second artifact, never a replacement. Every caller of
    load_solve_state must be untouched."""
    from gaffer.artifacts import load_solve_state

    save_solve_state(_state())
    back = load_solve_state(5)
    assert back.bank == 15 and back.free_transfers == 1
    assert len(back.pool) == 4
```

Run: `.venv/bin/pytest -q tests/test_v12_w5_projections.py` — `ImportError` on
`latest_projection_before`.

- [ ] **Implement the writer and readers.** `src/gaffer/artifacts.py`, appended
      after `prune_advice_history` (`:549`):

```python
PROJECTIONS = REPORTS / "projections"
"""Frozen copies of the EP table each advise run solved over (v12 W5 §6.4).

``solve_state_gw{N}.parquet`` is one slot per gameweek and advise runs several
times a week, so the file that survives to Tuesday is the *last* run — which
may be the one written after kickoff. The advice payload has not had that
problem since v9c (``ADVICE_HISTORY`` keeps 20 and
``journal.latest_run_per_gw`` picks the newest run written before the
deadline); this directory gives the EP table the same treatment under the same
rule.

Kept for the season and never pruned here. A snapshot is the pool — roughly
700 codes times the horizon times nine columns, 40-80 KB — so four runs a week
across a season is about 6-12 MB in a gitignored directory. Deciding which one
Review will want, before Review has ever wanted one, is not this cycle's call.
"""


@dataclass(frozen=True)
class ProjectionSnapshot:
    path: Path
    season: str
    gw: int
    stamp: str
    """The writer's own UTC stamp, ``%Y%m%dT%H%M%SZ``. Sorts
    lexicographically, which is why it is the sort key rather than mtime: two
    runs a second apart can share an mtime, and a copied ``reports/`` has
    mtimes that say nothing at all (``_history_stamp``'s reasoning)."""
    post_deadline: bool = False
    """Set only by :func:`latest_projection_before`, and only when *every*
    snapshot for the gameweek was written after the deadline."""


def _stamp_utc(when) -> str | None:
    """An ISO instant as a filename stamp, or ``None`` if it is not one."""
    try:
        at = pd.Timestamp(when)
    except (TypeError, ValueError):
        return None
    if at is pd.NaT or at != at:
        return None
    at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
    return at.strftime("%Y%m%dT%H%M%SZ")


def projection_path(season: str, gw: int, stamp: str) -> Path:
    return PROJECTIONS / f"{season}-gw{int(gw)}-{stamp}.parquet"


def save_projection_snapshot(pool: "pd.DataFrame", gw: int, generated_at,
                             season: str) -> Path | None:
    """Freeze ``pool`` under ``season`` and ``gw``. Never raises.

    ``None`` — and a printed line — rather than an exception on every failure
    mode, including an empty season. A snapshot filed under the wrong season
    is worse than no snapshot: the reader selects by glob, and a season-less
    name would be read back next August as this August's projections.
    """
    if not str(season or "").strip():
        print("projections: no current_season — no snapshot written for "
              f"GW{int(gw)}")
        return None
    stamp = _stamp_utc(generated_at) or _stamp_utc(
        datetime.now(timezone.utc))
    try:
        PROJECTIONS.mkdir(parents=True, exist_ok=True)
        path = projection_path(str(season), int(gw), str(stamp))
        pool.to_parquet(path, index=False)
        return path
    except Exception as exc:  # noqa: BLE001 — instrumentation never gates a run
        print(f"projections: no snapshot kept for GW{int(gw)} ({exc})")
        return None


def projection_snapshots(season: str, gw: int) -> list[ProjectionSnapshot]:
    """Every frozen EP table for one ``(season, gw)``, oldest first.

    ``season`` is a required argument and is matched exactly. Codes, not
    element ids, are what the pool is keyed on — but a directory selected by a
    glob is exactly the shape of the cross-season read that element-id remaps
    make dangerous, so the season is in the name and in the filter.
    """
    if not PROJECTIONS.is_dir():
        return []
    prefix = f"{season}-gw{int(gw)}-"
    out = []
    for path in PROJECTIONS.glob(f"{prefix}*.parquet"):
        if not path.is_file():
            continue
        out.append(ProjectionSnapshot(path=path, season=str(season),
                                      gw=int(gw),
                                      stamp=path.stem.rsplit("-", 1)[1]))
    return sorted(out, key=lambda s: s.stamp)


def latest_projection_before(season: str, gw: int,
                             deadline) -> ProjectionSnapshot | None:
    """The newest snapshot written before ``deadline``, or the newest at all.

    ``journal.latest_run_per_gw``'s rule applied to the EP table: a run banked
    after kickoff has seen the team news, and scoring a decision against
    projections that saw it flatters the model with information nobody had. So
    the newest *in-time* snapshot wins, and when every one of them is late the
    newest is returned with ``post_deadline`` set — a flagged comparison is
    worth more than a missing row as long as it cannot pass itself off as
    foresight.

    An unparseable deadline takes the same late branch rather than guessing.
    """
    snaps = projection_snapshots(season, gw)
    if not snaps:
        return None
    cutoff = _stamp_utc(deadline)
    if cutoff is not None:
        in_time = [s for s in snaps if s.stamp < cutoff]
        if in_time:
            return in_time[-1]
    return ProjectionSnapshot(path=snaps[-1].path, season=snaps[-1].season,
                              gw=snaps[-1].gw, stamp=snaps[-1].stamp,
                              post_deadline=True)
```

And inside `save_solve_state`, immediately before `return parquet, meta`
(`:217`):

```python
    # v12 W5 §6.4. The same pool, frozen and dated, so Review can read the EP
    # table that stood at the deadline rather than the one the last re-run
    # left behind. Wrapped and swallowed: banking the solve state is this
    # function's job, and a run that died because a snapshot could not be
    # written would be a far worse trade (``save_components``' reasoning).
    from gaffer.config import serving_config
    try:
        save_projection_snapshot(state.pool, state.gw, state.generated_at,
                                 str(getattr(serving_config(), "current_season",
                                             "") or ""))
    except Exception as exc:  # noqa: BLE001
        print(f"projections: no snapshot kept for GW{state.gw} ({exc})")
```

The import is local, not top-of-module: `gaffer.config` imports
`gaffer.errors` and nothing else, but `artifacts` is imported by `config`'s
callers early in the CLI's start-up and a module-level import here is a cycle
waiting for a refactor. `save_components` sets the same precedent
(`artifacts.py:106`).

- [ ] **Write the degradation rail.**
      `tests/test_v12_w5_projections_degradation.py`:

```python
"""v12 W5 §6.4 degradation — every way the projections directory can be wrong.

Spec §1: missing file, malformed file, empty result, partial result — each a
named behaviour, none a crash.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import (PROJECTIONS, latest_projection_before,
                              projection_snapshots, save_projection_snapshot)

DEADLINE = "2026-09-04T17:30:00+00:00"


@pytest.fixture(autouse=True)
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_no_directory_at_all_is_an_empty_list(here):
    assert projection_snapshots("2026-27", 5) == []
    assert latest_projection_before("2026-27", 5, DEADLINE) is None


def test_an_empty_directory_is_an_empty_list(here):
    PROJECTIONS.mkdir(parents=True)
    assert projection_snapshots("2026-27", 5) == []


def test_a_file_that_is_not_a_snapshot_is_ignored(here):
    PROJECTIONS.mkdir(parents=True)
    (PROJECTIONS / "notes.txt").write_text("hello")
    (PROJECTIONS / "2026-27-gw5.parquet").write_bytes(b"")
    assert projection_snapshots("2026-27", 5) == []


def test_a_snapshot_that_will_not_parse_is_still_listed_and_named(here):
    """Listing is a filename operation and must not read the file: a corrupt
    parquet is the caller's problem to report, with a path to point at."""
    PROJECTIONS.mkdir(parents=True)
    (PROJECTIONS / "2026-27-gw5-20260901T090000Z.parquet").write_bytes(b"junk")
    snaps = projection_snapshots("2026-27", 5)
    assert len(snaps) == 1
    with pytest.raises(Exception):
        pd.read_parquet(snaps[0].path)


def test_an_empty_season_writes_nothing_and_says_so(here, capsys):
    out = save_projection_snapshot(pd.DataFrame({"code": [1]}), 5,
                                   "2026-09-01T09:00:00+00:00", "")
    assert out is None
    assert "current_season" in capsys.readouterr().out
    assert not PROJECTIONS.exists()


def test_an_unwritable_directory_is_a_line_and_not_a_crash(here, capsys,
                                                           monkeypatch):
    monkeypatch.setattr(pd.DataFrame, "to_parquet",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    out = save_projection_snapshot(pd.DataFrame({"code": [1]}), 5,
                                   "2026-09-01T09:00:00+00:00", "2026-27")
    assert out is None
    assert "no snapshot kept" in capsys.readouterr().out


def test_an_unparseable_generated_at_still_writes_under_now(here):
    path = save_projection_snapshot(pd.DataFrame({"code": [1]}), 5,
                                    "not a date", "2026-27")
    assert path is not None and path.exists()


def test_an_empty_pool_is_written_rather_than_skipped(here):
    """"The solver had no candidates" is a fact worth freezing. A skipped
    snapshot would read later as "no run happened"."""
    path = save_projection_snapshot(pd.DataFrame({"code": []}), 5,
                                    "2026-09-01T09:00:00+00:00", "2026-27")
    assert path is not None
    assert len(pd.read_parquet(path)) == 0
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_projections.py \
  tests/test_v12_w5_projections_degradation.py
.venv/bin/pytest -q tests/ -k "artifacts or solve_state or advise"
.venv/bin/pytest -q
git diff --stat -- src/gaffer/advise.py | cat     # expect empty
```

- [ ] **Commit.**

```bash
git add src/gaffer/artifacts.py tests/test_v12_w5_projections.py \
  tests/test_v12_w5_projections_degradation.py && git commit -m "$(cat <<'EOF'
feat: every advise run freezes the EP table it solved over

The table was already persisted — reports/solve_state_gw{N}.parquet is the MILP
pool with raw EP per (code, gw) — but that is one slot per gameweek, and advise
runs several times a week. What survived to Tuesday was the *last* run, which
may be the one written after kickoff.

The advice payload has not had that problem since v9c: 20 runs are kept and
journal.latest_run_per_gw picks the newest one written before the deadline. This
gives the EP table the same versioning under the same rule, including the
post_deadline flag for the case where every run was late.

advise.py did not move. save_solve_state is unprotected and its only call site
is that file's line 1000, on the advise path, so the writer went there.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — Review is graded against the projections that stood at the deadline

**Files:**
- Modify: `src/gaffer/review.py` (`model_decisions` `:188-200`, and `grade_gw`
  `:943-990`)
- Modify: `src/gaffer/web/schemas.py` (`ReviewGw`, two fields after `:1268`)
- Modify: `frontend/src/types.ts` (`ReviewGw`, two fields)
- Modify: `frontend/src/hubs/model/ReviewTab.tsx` (one line in the row header)
- Create: `tests/test_v12_w5_review_snapshot.py`
- Modify: `frontend/src/hubs/model/ReviewTab.test.tsx` (three cases)

Spec §6.4 second half. `review.py` is unprotected. **Grades are banked, never
re-derived** (`review.py:24-26`), so this populates from the next graded week
onward and every already-banked row keeps `None` for ever — the same
consequence v11 recorded for `overall_rank` (A13 there), and the UI must draw
it the same way: absent, never zero.

- [ ] **Write the failing test.** `tests/test_v12_w5_review_snapshot.py`:

```python
"""v12 W5 §6.4 — the ledger row names the projections it was graded against."""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer import review
from gaffer.artifacts import POOL_COLS, save_projection_snapshot

SEASON = "2026-27"
DEADLINE = "2026-09-04T17:30:00+00:00"


def _pool():
    return pd.DataFrame([{"code": 100, "name": "P", "position": "MID",
                          "team_code": 1, "cost": 80, "sell": 80,
                          "owned": True, "gw": 5, "ep_raw": 5.0}],
                        columns=POOL_COLS)


@pytest.fixture()
def graded(tmp_path, monkeypatch):
    """A gameweek that grades, with the snapshot writing left to the test."""
    monkeypatch.chdir(tmp_path)
    mine = {"xi": [100] * 11, "bench": [100] * 4, "captain": 100, "vice": 100,
            "hits": 0, "chip": None, "official_gross": 60, "official_cost": 0,
            "notices": []}
    monkeypatch.setattr(review, "my_decisions", lambda gw, **kw: dict(mine))
    monkeypatch.setattr(review, "actuals_for_gw",
                        lambda gw: pd.DataFrame(
                            [{"code": 100, "total_points": 6, "minutes": 90,
                              "position": "MID"}]))
    monkeypatch.setattr(review, "code_of_element", lambda: {1: 100})
    monkeypatch.setattr(review, "names_by_code", lambda: {100: "P"})
    monkeypatch.setattr(
        review, "model_decisions",
        lambda gw: {"xi": [100] * 11, "bench": [100] * 4, "captain": 100,
                    "vice": 100, "buys": [], "sells": [], "hits": 0,
                    "chip": None, "names": {100: "P"},
                    "positions": {100: "MID"}, "post_deadline": False,
                    "deadline": DEADLINE})
    return type("Cfg", (), {"current_season": SEASON, "entry_id": 1,
                            "sim_n": 10})()


def test_a_row_names_the_snapshot_it_was_graded_against(graded):
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] == "20260903T090000Z"
    assert row["projection_post_deadline"] is False


def test_the_snapshot_chosen_is_the_last_one_before_the_deadline(graded):
    for at in ("2026-09-01T09:00:00+00:00", "2026-09-04T09:00:00+00:00",
               "2026-09-05T09:00:00+00:00"):
        save_projection_snapshot(_pool(), 5, at, SEASON)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] == "20260904T090000Z"


def test_a_gameweek_whose_every_run_was_late_is_flagged(graded):
    save_projection_snapshot(_pool(), 5, "2026-09-05T09:00:00+00:00", SEASON)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] == "20260905T090000Z"
    assert row["projection_post_deadline"] is True


def test_no_snapshot_is_None_and_the_row_still_grades(graded):
    """Every row already in the ledger is in this state and always will be:
    grades are banked and never re-derived (review.py:24-26)."""
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] is None
    assert row["projection_post_deadline"] is False
    assert row["my_points"] is not None


def test_a_row_with_no_surviving_advice_still_names_a_snapshot(graded,
                                                              monkeypatch):
    """The snapshot is on disk under (season, gw) and does not depend on the
    advice payload surviving the 20-run prune."""
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    monkeypatch.setattr(review, "model_decisions", lambda gw: None)
    row = review.grade_gw(5, cfg=graded)
    assert row["no_advice"] is True
    assert row["projection_snapshot"] == "20260903T090000Z"


def test_a_missing_deadline_takes_the_newest_and_flags_it(graded, monkeypatch):
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    monkeypatch.setattr(review, "model_decisions", lambda gw: None)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_post_deadline"] is True


def test_another_seasons_snapshot_is_not_read(graded):
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", "2025-26")
    assert review.grade_gw(5, cfg=graded)["projection_snapshot"] is None


def test_the_schema_defaults_both_fields_for_an_old_ledger():
    from gaffer.web.schemas import ReviewGw

    row = ReviewGw(gw=1)
    assert row.projection_snapshot is None
    assert row.projection_post_deadline is False
```

Run: `.venv/bin/pytest -q tests/test_v12_w5_review_snapshot.py` — fails on the
missing key.

- [ ] **Carry the deadline out of the advice payload.** `src/gaffer/review.py`,
      in `model_decisions`' return dict (`:188-200`), after `post_deadline`:

```python
        # v12 W5 §6.4. The run's own record of when the deadline was — the
        # same field journal.latest_run_per_gw sorts on. Needed here to pick
        # the projections that stood at it; ``None`` when the payload predates
        # the field, which sends the reader down its own late branch.
        "deadline": payload.get("deadline"),
```

- [ ] **Stamp the row.** `src/gaffer/review.py`, in `grade_gw`, after
      `model = model_decisions(gw)` (`:955`) and before the row is built:

```python
    # v12 W5 §6.4. Which frozen EP table this grade is being read against.
    # Not used to re-derive anything — the grade is points against actuals —
    # but a Review row that cannot say which projections it judged is a row
    # nobody can re-check, and a re-run between the deadline and Tuesday used
    # to move the answer silently.
    from gaffer.artifacts import latest_projection_before

    snapshot = latest_projection_before(
        season, gw, (model or {}).get("deadline"))
```

and, in both `return` paths, extend the row before returning it. The cleanest
single insertion point is immediately after each `row = grade_gw_from(...)`
call — there are two (`:966` and `:983`) — with the same two lines:

```python
    row["projection_snapshot"] = None if snapshot is None else snapshot.stamp
    row["projection_post_deadline"] = bool(
        snapshot is not None and snapshot.post_deadline)
```

`grade_gw_from` is **not** touched: its docstring says it is pure, with no I/O
and no network, and the snapshot lookup is I/O.

- [ ] **Add the schema fields.** `src/gaffer/web/schemas.py`, in `ReviewGw`
      after `overall_rank` (`:1268-1278`):

```python
    projection_snapshot: str | None = None
    """The UTC stamp of the frozen EP table this grade was read against.

    ``None`` for a gameweek graded before v12 W5 existed, and for one where no
    snapshot was ever written. Grades are banked and never re-derived (spec
    D2), so every row already in the ledger keeps ``None`` for ever and the
    column fills forward from the next graded week — drawn as absent, never as
    a zero or a blank that reads like one.
    """
    projection_post_deadline: bool = False
    """True when *every* snapshot for the gameweek was written after the
    deadline, so the projections graded here saw team news nobody could act
    on. The same flag, for the same reason, as ``post_deadline`` above — which
    is about the advice payload rather than the EP table, and the two can
    disagree."""
```

- [ ] **Render it.** `frontend/src/types.ts`, on `ReviewGw`:

```ts
  /** UTC stamp of the frozen EP table this grade was read against, or null
   *  for a week graded before the snapshots existed. Never rendered as a
   *  zero or an empty date. */
  projection_snapshot?: string | null
  projection_post_deadline?: boolean
```

`frontend/src/hubs/model/ReviewTab.tsx`, beside the `post_deadline` badge at
`:86-87`:

```tsx
          {row.projection_snapshot && (
            <span
              className="text-text-faint"
              data-testid={`review-projections-${row.gw}`}
              title={row.projection_post_deadline
                ? 'Every projection run for this gameweek was written after '
                  + 'the deadline, so it saw team news you could not act on.'
                : 'The last projections written before the deadline.'}
            >
              {`projections ${row.projection_snapshot.slice(0, 8)}`}
              {row.projection_post_deadline ? ' (late)' : ''}
            </span>
          )}
```

and three cases in `ReviewTab.test.tsx`: a row with a stamp renders it; a row
with `projection_post_deadline` renders "(late)"; a row with
`projection_snapshot: null` renders **nothing** rather than an em dash — an
absent snapshot is not a measurement and gets no slot.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_review_snapshot.py
.venv/bin/pytest -q tests/ -k "review"
.venv/bin/pytest -q
cd frontend && npx vitest run src/hubs/model/ReviewTab.test.tsx && npx vitest run
```

- [ ] **Commit.**

```bash
git add src/gaffer/review.py src/gaffer/web/schemas.py \
  tests/test_v12_w5_review_snapshot.py frontend/src/types.ts \
  frontend/src/hubs/model/ReviewTab.tsx \
  frontend/src/hubs/model/ReviewTab.test.tsx && git commit -m "$(cat <<'EOF'
feat: a Review row names the projections it was graded against

The grade itself is points against actuals and does not move. What moves is
that the row now records which frozen EP table stood at the deadline, and flags
the case where every run for that gameweek was written after it.

Grades are banked and never re-derived, so the column fills forward from the
next graded week and every row already in the ledger keeps null for ever — the
same consequence v11 recorded for overall_rank, drawn the same way: absent, and
never a zero or an empty date that reads like one.

grade_gw_from is untouched. Its docstring promises no I/O and a snapshot lookup
is I/O, so the stamp is attached in grade_gw where the filesystem already is.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — the trace, as accounting, outside the solver

**Files:**
- Create: `src/gaffer/trace.py`
- Create: `tests/test_v12_w5_trace.py`
- Create: `tests/test_v12_w5_trace_degradation.py`

Spec §6.5, A8. **`optimize/**` is not touched.** Read-only accounting over the
objective's own terms, computed from artifacts the plan router already loads.

Before writing a line, re-read A8's table and the objective at
`milp.py:596-660`. Every coefficient below is copied from there and a
coefficient that disagrees with it is a bug in this file, not a modelling
choice.

- [ ] **Write the failing test.** `tests/test_v12_w5_trace.py`:

```python
"""v12 W5 §6.5 — why the plan makes each move.

Accounting, not a counterfactual. Every number here is a term of the MILP's own
objective (milp.py:596-660) evaluated at the plan the solver returned; none of
them is "the plan is this much better than not doing it", which needs a
re-solve, which §6.5 forbids.
"""
from __future__ import annotations

import copy

import pytest

from gaffer.trace import MoveTrace, WeekTrace, trace_plan

GWS = [5, 6, 7]
POS = {100: "MID", 200: "MID", 300: "DEF", 400: "DEF"}
NAMES = {100: "In", 200: "Out", 300: "DefIn", 400: "DefOut"}
EP = {(100, 5): 6.0, (100, 6): 6.0, (100, 7): 6.0,
      (200, 5): 4.0, (200, 6): 4.0, (200, 7): 4.0,
      (300, 5): 3.0, (300, 6): 3.0, (300, 7): 3.0,
      (400, 5): 2.0, (400, 6): 2.0, (400, 7): 2.0}


def week(gw, buys=(), sells=(), hits=0, chip=None):
    return {"gw": gw, "buys": list(buys), "sells": list(sells), "hits": hits,
            "chip": chip}


def run(weeks, **kw):
    base = dict(gws=GWS, ep_by=EP, positions=POS, names=NAMES, decay=0.5,
                hit_cost=4, ft_value=1.5, itb_value=0.05, free_transfers=1)
    return trace_plan(weeks, **{**base, **kw})


def test_a_swap_is_the_decayed_ep_difference_over_the_rest_of_the_horizon():
    # weeks 5,6,7 at decay 0.5 -> 1 + 0.5 + 0.25 = 1.75 multipliers,
    # difference 2.0 a week: 2.0 * 1.75 = 3.5
    out = run([week(5, buys=[100], sells=[200])])
    assert out[0].moves[0].ep_gain == pytest.approx(3.5)


def test_a_later_week_only_counts_from_its_own_week_onward():
    out = run([week(5), week(6, buys=[100], sells=[200])])
    # weeks 6,7 -> 0.5 + 0.25 = 0.75 multipliers, 2.0 a week: 1.5
    assert out[1].moves[0].ep_gain == pytest.approx(1.5)


def test_the_decay_index_is_the_horizons_and_not_the_weeks():
    """`d = decay ** t_i` indexes T from 0 (milp.py:598). A trace that
    restarted the exponent at each move's own week would price a GW7 buy as if
    it were this week's."""
    out = run([week(7, buys=[100], sells=[200])])
    assert out[0].moves[0].ep_gain == pytest.approx(2.0 * 0.25)


def test_moves_are_paired_by_position():
    out = run([week(5, buys=[100, 300], sells=[400, 200])])
    pairs = {(m.buy_code, m.sell_code) for m in out[0].moves}
    assert pairs == {(100, 200), (300, 400)}


def test_an_unpaired_buy_gets_no_gain_and_says_why():
    out = run([week(5, buys=[100])])
    move = out[0].moves[0]
    assert move.buy_code == 100 and move.sell_code is None
    assert move.ep_gain is None
    assert "pair" in move.note


def test_a_code_with_no_ep_in_the_pool_is_None_and_not_zero():
    out = run([week(5, buys=[999], sells=[200])], positions={**POS, 999: "MID"},
              names={**NAMES, 999: "Ghost"})
    assert out[0].moves[0].ep_gain is None
    assert "not in the pool" in out[0].moves[0].note


def test_the_weeks_gain_is_the_sum_of_its_paired_moves():
    out = run([week(5, buys=[100, 300], sells=[400, 200])])
    assert out[0].ep_gain == pytest.approx(
        sum(m.ep_gain for m in out[0].moves))


def test_one_unpriceable_move_makes_the_weeks_total_unknown():
    """Not "the rest of it". A total short by one move is a confident number
    that is wrong by exactly that move, with nothing on the page to say so."""
    out = run([week(5, buys=[100, 300], sells=[200])])
    assert out[0].ep_gain is None


def test_the_hit_cost_is_the_weeks_and_never_a_moves():
    out = run([week(5, buys=[100, 300], sells=[400, 200], hits=1)])
    assert out[0].hit_cost == 4
    assert all(not hasattr(m, "hit_cost") for m in out[0].moves)


def test_the_hit_cost_is_decayed_like_the_objective_decays_it():
    """`-hit_cost * d * hits[t]` (milp.py:625). A GW7 hit does not cost four
    points of GW5 money."""
    out = run([week(7, buys=[100], sells=[200], hits=1)])
    assert out[0].hit_cost == pytest.approx(4 * 0.25)


def test_free_transfers_run_forward_across_the_plan():
    out = run([week(5, buys=[100], sells=[200]), week(6), week(7)],
              free_transfers=1)
    assert [w.ft_used for w in out] == [1, 0, 0]
    # 1 - 1 + 0 + 1 = 1 after GW5, then + 1 a week, capped at
    # MAX_FREE_TRANSFERS — milp.py:556-563's own recurrence.
    assert [w.ft_after for w in out] == [1, 2, 3]


def test_a_wildcard_week_charges_no_transfer_and_banks_one():
    out = run([week(5, buys=[100, 300], sells=[200, 400], chip="wildcard")],
              free_transfers=1)
    assert out[0].ft_used == 0
    assert out[0].ft_after == 2


def test_the_ft_shadow_price_is_flat_without_a_lambda_table():
    out = run([week(5, buys=[100], sells=[200])])
    assert out[0].ft_shadow == pytest.approx(1.5)
    assert out[0].ft_basis == "flat"


def test_the_ft_shadow_price_is_the_lambda_tables_terminal_margin():
    class Lookup:
        empty = False

        def __call__(self, k, t):
            return 0.5 * k + 0.01 * t

    out = run([week(5, buys=[100], sells=[200]), week(6), week(7)],
              ft_lambda=Lookup())
    # terminal count 3 (see the recurrence above),
    # weeks_left = max(1, SEASON_LAST_GW - 7)
    from gaffer.optimize.milp import SEASON_LAST_GW
    assert out[-1].ft_basis == "lambda"
    assert out[-1].ft_shadow == pytest.approx(
        0.5 * 3 + 0.01 * max(1, SEASON_LAST_GW - 7))


def test_an_empty_lambda_lookup_falls_back_to_flat():
    class Lookup:
        empty = True

        def __call__(self, k, t):  # pragma: no cover — never called
            raise AssertionError

    out = run([week(5, buys=[100], sells=[200])], ft_lambda=Lookup())
    assert out[0].ft_basis == "flat"


def test_the_lambda_tilt_is_the_difference_the_tilt_made_to_the_pair():
    out = run([week(5, buys=[100], sells=[200])], lam=0.5,
              cover={100: 1.0, 200: 0.0})
    # tilt_ep scales by (1 + lam*(1-covered)) / (1 + lam): the covered buy is
    # marked down and the uncovered sell is not, so the tilt made this swap
    # *less* attractive and the number is negative.
    assert out[0].moves[0].lambda_tilt < 0


def test_a_neutral_lambda_tilts_nothing():
    out = run([week(5, buys=[100], sells=[200])], lam=0.0, cover={})
    assert out[0].moves[0].lambda_tilt == pytest.approx(0.0)


def test_theta_is_reported_only_for_a_week_that_plays_a_chip():
    out = run([week(5), week(6, chip="wildcard")],
              thresholds={6: 12.5})
    assert out[0].theta is None
    assert out[1].theta == pytest.approx(12.5)


def test_the_price_charge_is_off_when_the_setting_is_off():
    """Orchestrator ruling 1: the charge is computed only when [optimizer]
    price_timing is on. Off, the objective carries no such term, so reporting
    one would price a charge the solver never paid."""
    out = run([week(5), week(6, buys=[100], sells=[200])],
              price_timing=False, price_fall={200: 0.8})
    assert out[1].price_charge is None
    assert "price_timing is off" in out[1].note


def test_the_price_charge_is_absent_when_the_reader_has_no_row():
    """On, but the nightly price log has nothing for this code — an unknown,
    which is not the same fact as a zero chance of a fall."""
    out = run([week(5), week(6, sells=[200])], price_timing=True,
              price_fall={})
    assert out[1].price_charge is None
    assert "not recorded" in out[1].note


def test_the_price_charge_is_the_objectives_own_coefficient_when_it_is():
    out = run([week(5), week(6, buys=[100], sells=[200])],
              price_timing=True, price_fall={200: 0.8})
    assert out[1].price_charge == pytest.approx(0.8 * 0.1 * 0.05)


def test_the_first_week_is_never_charged_price_timing():
    """The term charges a sell *scheduled for a later week*; selling now is
    what it exists to encourage."""
    out = run([week(5, buys=[100], sells=[200])], price_timing=True,
              price_fall={200: 0.8})
    assert out[0].price_charge == pytest.approx(0.0)


def test_the_trace_does_not_mutate_a_single_input():
    """The real risk of an accounting layer: an in-place edit of the pool or
    the week dicts that the caller then serves."""
    weeks = [week(5, buys=[100], sells=[200]), week(6)]
    ep, pos, names = dict(EP), dict(POS), dict(NAMES)
    before = copy.deepcopy((weeks, ep, pos, names))
    trace_plan(weeks, gws=list(GWS), ep_by=ep, positions=pos, names=names,
               decay=0.5, hit_cost=4, ft_value=1.5, itb_value=0.05,
               free_transfers=1)
    assert copy.deepcopy((weeks, ep, pos, names)) == before


def test_the_trace_module_is_imported_by_no_solver():
    """The guarantee §6.5's byte-identity gate is really asking for. The trace
    cannot change a decision if nothing that makes one can see it."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "gaffer"
    watched = [root / "advise.py", *sorted((root / "optimize").glob("*.py"))]
    pattern = re.compile(r"\b(from\s+gaffer\.trace|import\s+gaffer\.trace"
                         r"|from\s+\.\.?trace|from\s+gaffer\s+import\s+trace)")
    guilty = [p.name for p in watched if pattern.search(p.read_text())]
    assert guilty == []


def test_the_types_are_frozen_so_a_caller_cannot_edit_a_trace():
    out = run([week(5, buys=[100], sells=[200])])
    assert isinstance(out[0], WeekTrace)
    assert isinstance(out[0].moves[0], MoveTrace)
    with pytest.raises(Exception):
        out[0].moves[0].ep_gain = 99.0
```

Run: `.venv/bin/pytest -q tests/test_v12_w5_trace.py` — `ModuleNotFoundError`.

- [ ] **Implement.** `src/gaffer/trace.py`:

```python
"""Why the plan makes each move (v12 W5 §6.5).

**Accounting, not a counterfactual.** Every number here is a term of the MILP's
own objective (``optimize/milp.py:596-660``) evaluated at the plan the solver
already returned. None of them is "the plan is this much better than not doing
this move" — that is a re-solve, and §6.5 exists precisely so that no view
solves.

The spec put this inside ``milp.py``, in ``_decision_scales``' neighbourhood.
It is here instead, for two reasons (plan A8). ``_decision_scales`` computes
autosub frailty weights between two solves and never sees a transfer, a price
or a hit — its neighbourhood is the wrong neighbourhood. And a "read-only
accounting" function that lives in the module which builds the objective is one
refactor away from being read *by* the objective; the way to guarantee it
changes no decision is to put it where no decision can see it. A test in
``tests/test_v12_w5_trace.py`` asserts that ``advise.py`` and every module under
``optimize/`` import this file nowhere.

Pure. No I/O, no network, no pandas. Everything it needs is already on disk in
``SolveState`` and the advice payload, and the caller — ``routers/plan.py`` —
loads both anyway. That includes the price-fall probabilities: the router calls
W2's own ``owned_price_falls`` and hands the answer in, so this module reads no
log of its own and the charge it prints is computed from the same numbers the
objective's term was.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gaffer.optimize.milp import MAX_FREE_TRANSFERS, SEASON_LAST_GW

PRICE_TIMING_COEFF = 0.1
"""W2 §3.4's coefficient: a later-week sell is charged
``p_fall_tonight * 0.1 * itb_value``. Restated here rather than imported so
this module has no reason to reach into the objective, and asserted against the
spec in the test file.

Applied only when ``price_timing`` is on. With the setting off the objective
carries no such term at all, and a reported zero would say "we checked and it
was free" — a different sentence from "we did not charge for this"."""


@dataclass(frozen=True)
class MoveTrace:
    gw: int
    buy_code: int | None
    buy_name: str
    sell_code: int | None
    sell_name: str
    ep_gain: float | None
    """Decayed expected points the swap adds over the rest of the horizon.

    ``Σ_{k=i..n-1} decay**k * (ep[buy][T[k]] - ep[sell][T[k]])``, where ``k``
    indexes the *whole* horizon from zero because that is what ``d = decay **
    t_i`` does in the objective. ``None`` when the pair could not be formed or
    either side has no expected points in the pool — never 0.0, which is a
    measured tie."""
    lambda_tilt: float | None
    """What the league tilt did to that difference. Positive means the tilt
    made this swap more attractive than raw points alone. 0.0 at ``lam = 0``,
    which is a real and measured answer."""
    note: str = ""


@dataclass(frozen=True)
class WeekTrace:
    gw: int
    moves: list[MoveTrace] = field(default_factory=list)
    ep_gain: float | None = None
    """The week's paired moves summed, or ``None`` if any one of them is
    unknown. Not "the rest of them": a total short by one move is a confident
    number that is wrong by exactly that move."""
    hits: int = 0
    hit_cost: float = 0.0
    """``hit_cost * decay**i * hits`` — the objective's own charge
    (``milp.py:625``), so a hit taken in week three does not cost four points
    of this week's money."""
    ft_used: int = 0
    ft_after: int = 0
    ft_shadow: float | None = None
    """What one banked free transfer is worth at the *end* of the horizon —
    flat ``ft_value``, or ``λ(terminal count, weeks left)``. It is not the
    intra-horizon price of spending one, because the model does not price that
    either: free transfers enter the objective only as a terminal term."""
    ft_basis: str = "flat"
    theta: float | None = None
    price_charge: float | None = None
    note: str = ""


def _pair(sells: list[int], buys: list[int],
          positions: dict[int, str]) -> list[tuple[int | None, int | None]]:
    """``[(buy, sell)]`` matched by position, unmatched sides carried as None.

    A local six lines rather than ``review.pair_by_position``: that module
    loads the ledger and the journal on import, and the plan router has no
    business paying for either to label a transfer.
    """
    left = list(sells)
    out: list[tuple[int | None, int | None]] = []
    for buy in buys:
        match = next((s for s in left
                      if positions.get(s) == positions.get(buy)), None)
        if match is not None:
            left.remove(match)
        out.append((buy, match))
    out.extend((None, s) for s in left)
    return out


def trace_plan(weeks, *, gws: list[int], ep_by: dict, positions: dict,
               names: dict, decay: float, hit_cost: float, ft_value: float,
               itb_value: float, free_transfers: int, ft_lambda=None,
               lam: float = 0.0, cover: dict | None = None,
               thresholds: dict | None = None,
               price_timing: bool = False,
               price_fall: dict | None = None) -> list[WeekTrace]:
    """One :class:`WeekTrace` per planned week, in the order given.

    ``weeks`` is ``[{"gw", "buys": [code], "sells": [code], "hits", "chip"}]``
    — exactly what ``plan_by_gw`` holds once the router has parsed it.
    ``ep_by`` is ``{(code, gw): raw expected points}``, straight off the solve
    state's pool.

    ``price_timing`` and ``price_fall`` come from W2's own reader by way of the
    router. ``price_timing=False`` — the default, and what a build without W2
    gets — reports ``None`` for every charge and says why, rather than a zero.

    Nothing is mutated. Every input is read and every output is frozen.
    """
    order = {g: i for i, g in enumerate(list(gws))}
    tilted = _tilted(ep_by, cover or {}, lam)
    thresholds = thresholds or {}
    price_fall = price_fall or {}
    weeks_left = max(1, SEASON_LAST_GW - (list(gws)[-1] if gws else 0))
    use_lambda = ft_lambda is not None and not getattr(ft_lambda, "empty",
                                                       True)
    ft = int(free_transfers)
    out: list[WeekTrace] = []

    for entry in weeks:
        gw = int(entry.get("gw", 0))
        i = order.get(gw)
        buys = [int(c) for c in entry.get("buys") or []]
        sells = [int(c) for c in entry.get("sells") or []]
        hits = int(entry.get("hits") or 0)
        chip = entry.get("chip")
        wildcard = str(chip or "").lower() in ("wildcard", "wc")

        moves, notes = [], []
        if i is None:
            notes.append(f"GW{gw} is not in the solved horizon {list(gws)}, "
                         "so nothing here can be priced against it")
        for buy, sell in _pair(sells, buys, positions):
            gain, tilt, note = _swap(buy, sell, i, gws, order, ep_by, tilted,
                                     decay)
            moves.append(MoveTrace(
                gw=gw, buy_code=buy, buy_name=names.get(buy, str(buy)),
                sell_code=sell, sell_name=names.get(sell, str(sell)),
                ep_gain=gain, lambda_tilt=tilt, note=note))

        gains = [m.ep_gain for m in moves]
        week_gain = (None if any(g is None for g in gains)
                     else round(sum(gains), 3))

        if wildcard:
            used, after = 0, min(MAX_FREE_TRANSFERS, ft + 1)
        else:
            used = min(len(buys), ft)
            after = min(MAX_FREE_TRANSFERS,
                        max(0, ft - len(buys) + hits) + 1)

        # The price-timing charge, W2 §3.4: only a sell scheduled for a *later*
        # week is charged, because selling now is what the term encourages.
        #
        # Gated on ``price_timing`` (orchestrator ruling 1, 2026-09-02). With
        # the setting off the objective carries no such term at all, so
        # reporting a number would price a charge the solver never paid — and
        # a zero would say "we checked and it was free", which is a different
        # claim from "we did not charge for this".
        if not price_timing:
            charge = None
            if sells and i not in (None, 0):
                notes.append("price_timing is off, so the plan was solved "
                             "without a price-timing term")
        elif i is None or i == 0 or not sells:
            charge = 0.0
        elif all(c in price_fall for c in sells):
            charge = round(sum(price_fall[c] * PRICE_TIMING_COEFF * itb_value
                               for c in sells), 6)
        else:
            charge = None
            notes.append("the chance of a price fall was not recorded for "
                         "every player sold here, so the price-timing charge "
                         "is unknown")

        d = decay ** i if i is not None else 1.0
        out.append(WeekTrace(
            gw=gw, moves=moves, ep_gain=week_gain, hits=hits,
            hit_cost=round(hit_cost * d * hits, 3), ft_used=used,
            ft_after=after,
            ft_shadow=(round(ft_lambda(max(1, after), weeks_left), 4)
                       if use_lambda else float(ft_value)),
            ft_basis="lambda" if use_lambda else "flat",
            theta=thresholds.get(gw), price_charge=charge,
            note="; ".join(notes)))
        ft = after
    return out


def _tilted(ep_by: dict, cover: dict, lam: float) -> dict:
    """``tilt_ep``'s answer, or the raw table when the tilt is neutral.

    Imported lazily: ``league_mode`` pulls pandas in, and a plan with no tilt
    should not pay for it.
    """
    if not lam:
        return dict(ep_by)
    from gaffer.league_mode import tilt_ep

    return tilt_ep(dict(ep_by), dict(cover), float(lam))


def _swap(buy, sell, i, gws, order, ep_by, tilted, decay):
    """One pair's ``(ep_gain, lambda_tilt, note)``."""
    if buy is None or sell is None:
        side = "buy" if sell is None else "sell"
        return (None, None,
                f"no {'sell' if side == 'buy' else 'buy'} of the same "
                "position to pair this move with, so it cannot be priced as "
                "a swap")
    if i is None:
        return None, None, "outside the solved horizon"
    horizon = list(gws)[i:]
    missing = [c for c in (buy, sell)
               if not any((c, g) in ep_by for g in horizon)]
    if missing:
        return (None, None,
                f"player {missing[0]} is not in the pool the solver used, so "
                "no expected points can be read for him")
    gain = tilt = 0.0
    for g in horizon:
        d = decay ** order[g]
        gain += d * (ep_by.get((buy, g), 0.0) - ep_by.get((sell, g), 0.0))
        tilt += d * ((tilted.get((buy, g), 0.0) - tilted.get((sell, g), 0.0))
                     - (ep_by.get((buy, g), 0.0) - ep_by.get((sell, g), 0.0)))
    return round(gain, 3), round(tilt, 3), ""
```

- [ ] **Write the degradation rail.** `tests/test_v12_w5_trace_degradation.py`
      — the four named behaviours over the same fixtures as
      `test_v12_w5_trace.py`: an empty `weeks` list returns `[]`; a week dict
      missing `buys`/`sells`/`hits`/`chip` entirely traces as a no-move week
      with `ep_gain == 0.0` and `hit_cost == 0.0`; a `positions` map that knows
      none of the codes pairs nothing and every move carries the "no sell of
      the same position" note rather than raising; and an `ep_by` that is empty
      makes every `ep_gain` `None` with the "not in the pool" note. Add one for
      a `gws` of `[]` — every week is outside the horizon, every move is
      `None`, and the week note names the empty horizon.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_trace.py \
  tests/test_v12_w5_trace_degradation.py
.venv/bin/pytest -q
git diff --stat -- src/gaffer/optimize/ src/gaffer/advise.py | cat  # empty
```

- [ ] **Commit.**

```bash
git add src/gaffer/trace.py tests/test_v12_w5_trace.py \
  tests/test_v12_w5_trace_degradation.py && git commit -m "$(cat <<'EOF'
feat: a read-only trace of the objective terms behind each planned move

Accounting, not a counterfactual. Every number is a term of the MILP's own
objective evaluated at the plan the solver returned — the decayed EP difference
of a position-matched swap, the decayed hit charge, the terminal FT shadow
price, the league tilt's contribution, θ where a chip is played. None of it is
"the plan is this much better without this move", which needs a re-solve.

The spec put this inside milp.py, in _decision_scales' neighbourhood. It is
here instead. _decision_scales computes autosub frailty weights between two
solves and never sees a transfer, a price or a hit; and a read-only accounting
function living in the module that builds the objective is one refactor away
from being read by it. A test asserts advise.py and every module under
optimize/ import this file nowhere — which is a stronger guarantee than the
byte-identity check the spec asked for, because it makes the failure impossible
rather than detectable.

Three numbers are deliberately week-level rather than per-move: a week with two
transfers and one hit cannot attribute the hit to one of them. And the FT number
is the terminal margin, because that is the only place free transfers enter the
objective.

The price-timing charge is gated on the setting rather than defaulted to zero.
With [optimizer] price_timing off the objective carries no such term, and a
zero on the page would say "we checked and it was free" — which is a different
sentence from "we did not charge for this".

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — the trace on the wire and on the board

**Files:**
- Modify: `src/gaffer/web/schemas.py` (two models + one field on `PlanGw`)
- Modify: `src/gaffer/web/routers/plan.py` (a `TRACE` flag, a `_trace_inputs`
  helper, and the `trace=` keyword on the `PlanGw` construction at `:188-201`)
- Modify: `frontend/src/types.ts` (two interfaces + one field on `PlanGw`)
- Modify: `frontend/src/hubs/planning/PlannerBoard.tsx` (one block per week
  card, after the xPts block at `:206-209`)
- Create: `tests/test_v12_w5_plan_trace.py`
- Modify: `frontend/src/hubs/planning/PlannerBoard.test.tsx` (five cases)

Spec §6.5 second half. **This is where §6.5's byte-identity gate is
discharged**, in the form that measures the real risk: the payload the board
draws must be character-for-character what it was, minus the added key.

- [ ] **Write the failing test.** `tests/test_v12_w5_plan_trace.py`:

```python
"""v12 W5 §6.5 — the trace on /api/plan/{gw}.

The byte-identity gate lives here. The trace is outside the solver by
construction (tests/test_v12_w5_trace.py proves nothing that decides can import
it), so what is left to prove is that turning it on changed nothing else on the
payload the board already draws.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import POOL_COLS, SolveState
from gaffer.web.routers import plan as plan_router


def _pool():
    rows = [{"code": c, "name": n, "position": p, "team_code": 1, "cost": 80,
             "sell": 74, "owned": c == 200, "gw": g, "ep_raw": ep}
            for c, n, p, ep in ((100, "In", "MID", 6.0),
                                (200, "Out", "MID", 4.0))
            for g in (5, 6, 7)]
    return pd.DataFrame(rows, columns=POOL_COLS)


def _advice(weeks, chips=()):
    return {"gw": 5, "plan_by_gw": weeks, "chip_table": list(chips),
            "captain": {"code": 100, "name": "In", "position": "MID",
                        "ep": 6.0},
            "vice": {"code": 200, "name": "Out", "position": "MID",
                     "ep": 4.0}}


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "buys": list(buys), "sells": list(sells),
            "expected_pts": 60.0}


@pytest.fixture()
def wired(monkeypatch):
    def install(weeks, chips=(), lam=0.0, cover=None):
        monkeypatch.setattr(plan_router, "load_advice",
                            lambda gw: _advice(weeks, chips))
        state = SolveState(
            pool=_pool(), bank=15,
            opt={"hit_cost": 4, "decay": 0.5, "ft_value": 1.5,
                 "itb_value": 0.05, "decision_priors": False},
            generated_at="2026-09-01T09:00:00+00:00", deadline="",
            owned_codes=[200], gws=[5, 6, 7], gw=5, mode="weekly",
            free_transfers=1, lam=lam, league_eo={}, cover=cover,
            avail_by_gw={})
        monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
        return state
    return install


P = {"code": 100, "name": "In", "position": "MID", "ep": 6.0}
S = {"code": 200, "name": "Out", "position": "MID", "ep": 4.0}


def test_a_week_with_moves_carries_a_trace(wired):
    wired([_week(5, buys=[P], sells=[S])])
    week = plan_router.plan(5).weeks[0]
    assert week.trace is not None
    assert week.trace.moves[0].buy_code == 100
    assert week.trace.moves[0].sell_code == 200
    # 2.0 a week over weeks 5,6,7 at decay 0.5 -> 2.0 * 1.75
    assert week.trace.moves[0].ep_gain == pytest.approx(3.5)


def test_a_week_with_no_moves_carries_a_trace_with_no_moves(wired):
    """Not a null. "This week does nothing" is a fact the board can print;
    "there is no trace" is a wiring failure and they must not look alike."""
    wired([_week(5)])
    week = plan_router.plan(5).weeks[0]
    assert week.trace is not None and week.trace.moves == []


def test_the_hit_charge_on_the_trace_matches_the_weeks_hit_cost(wired):
    wired([_week(5, buys=[P], sells=[S], hits=1)])
    week = plan_router.plan(5).weeks[0]
    assert week.hit_cost == 4
    assert week.trace.hit_cost == pytest.approx(4.0)


def test_theta_reaches_the_trace_from_the_chip_table(wired):
    wired([_week(5)], chips=[{"chip": "wildcard", "gw": 5, "play_now": True,
                              "threshold": 12.5}])
    assert plan_router.plan(5).weeks[0].trace.theta == pytest.approx(12.5)


def test_the_lambda_tilt_reaches_the_trace(wired):
    wired([_week(5, buys=[P], sells=[S])], lam=0.5,
          cover={100: 1.0, 200: 0.0})
    assert plan_router.plan(5).weeks[0].trace.moves[0].lambda_tilt < 0


def test_the_price_charge_reaches_the_trace_through_w2s_own_reader(wired,
                                                                   monkeypatch):
    """Orchestrator ruling 1. The same reader the objective's term uses, so
    the board prints the charge the solver applied rather than a second
    estimate of it."""
    wired([_week(5), _week(6, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "_price_falls",
                        lambda state: (True, {200: 0.8}))
    trace = plan_router.plan(5).weeks[1].trace
    assert trace.price_charge == pytest.approx(0.8 * 0.1 * 0.05)


def test_price_timing_off_reports_no_charge_and_says_why(wired, monkeypatch):
    wired([_week(5), _week(6, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "_price_falls",
                        lambda state: (False, {}))
    trace = plan_router.plan(5).weeks[1].trace
    assert trace.price_charge is None
    assert "price_timing is off" in trace.note


def test_a_missing_price_reader_costs_the_charge_and_not_the_plan(wired,
                                                                  monkeypatch):
    """W5 may land on a tree where W2's reader moved or was renamed. The
    import failure is a printed line and a null charge, never a 500."""
    def boom(*a, **k):
        raise ImportError("no such module")

    wired([_week(5), _week(6, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "_price_falls", boom)
    out = plan_router.plan(5)
    assert out.weeks[1].expected_pts == 60.0
    assert out.weeks[1].trace is None


def test_the_payload_is_byte_identical_with_the_trace_off(wired,
                                                          monkeypatch):
    """§6.5's gate. Everything the board already drew must be exactly what it
    was; the only difference the trace makes is the key it adds."""
    wired([_week(5, buys=[P], sells=[S], hits=1), _week(6), _week(7)])
    with_trace = plan_router.plan(5).model_dump()
    monkeypatch.setattr(plan_router, "TRACE", False)
    without = plan_router.plan(5).model_dump()

    stripped = {**with_trace,
                "weeks": [{k: v for k, v in w.items() if k != "trace"}
                          for w in with_trace["weeks"]]}
    bare = {**without,
            "weeks": [{k: v for k, v in w.items() if k != "trace"}
                      for w in without["weeks"]]}
    assert json.dumps(stripped, sort_keys=True) == json.dumps(
        bare, sort_keys=True)
    assert all(w["trace"] is None for w in without["weeks"])


def test_a_trace_that_throws_costs_the_trace_and_not_the_plan(wired,
                                                              monkeypatch):
    """A decoration must never be the reason a plan does not render — the
    board's own rule for the price movers (PlannerBoard.tsx:63-65)."""
    def boom(*a, **k):
        raise ValueError("nope")

    wired([_week(5, buys=[P], sells=[S])])
    monkeypatch.setattr(plan_router, "trace_plan", boom)
    out = plan_router.plan(5)
    assert out.weeks[0].expected_pts == 60.0
    assert out.weeks[0].trace is None


def test_a_pool_with_no_ep_column_does_not_stop_the_plan(wired):
    wired([_week(5, buys=[P], sells=[S])])
    state = plan_router.load_solve_state(5)
    state.pool = state.pool.drop(columns=["ep_raw"])
    out = plan_router.plan(5)
    assert out.weeks[0].buys[0].code == 100
    assert out.weeks[0].trace.moves[0].ep_gain is None
```

Run: `.venv/bin/pytest -q tests/test_v12_w5_plan_trace.py` — fails on the
missing `trace` attribute.

- [ ] **Add the schemas.** `src/gaffer/web/schemas.py`, above `PlanGw`
      (`:1018`):

```python
class PlanMoveTrace(BaseModel):
    """One transfer, priced against the objective's own terms (v12 W5 §6.5).

    Not a counterfactual. ``ep_gain`` is the decayed expected-points
    difference of a position-matched swap over the rest of the horizon — the
    objective's own arithmetic at the plan the solver returned — and **not**
    "the plan is this much worse without this move", which would need a
    re-solve. ``None`` everywhere means unknown, never a measured zero.
    """

    buy_code: int | None = None
    buy_name: str = ""
    sell_code: int | None = None
    sell_name: str = ""
    ep_gain: float | None = None
    lambda_tilt: float | None = None
    note: str = ""


class PlanWeekTrace(BaseModel):
    """One planned week's charges. Three of them are week-level on purpose:
    a week with two transfers and one hit cannot attribute the hit to one of
    them, and splitting it would be arithmetic dressed as a finding."""

    gw: int
    moves: list[PlanMoveTrace] = Field(default_factory=list)
    ep_gain: float | None = None
    hit_cost: float = 0.0
    ft_used: int = 0
    ft_after: int = 0
    ft_shadow: float | None = None
    ft_basis: Literal["flat", "lambda"] = "flat"
    theta: float | None = None
    price_charge: float | None = None
    note: str = ""
```

and on `PlanGw`, after `bank` (`:1028`):

```python
    trace: PlanWeekTrace | None = None
    """Why this week's moves, in the objective's own terms. ``None`` only when
    the trace could not be computed at all — a week that does nothing carries
    a trace with no moves, because "this week does nothing" and "the trace is
    broken" must not look alike on the board."""
```

- [ ] **Serve it.** `src/gaffer/web/routers/plan.py`:

```python
from gaffer.trace import trace_plan
```

```python
TRACE = True
"""Whether to compute the move trace (v12 W5 §6.5).

A module flag rather than a config key: it exists so the byte-identity test can
turn the accounting off and compare the payload the board already drew. There
is nothing here for a user to switch, and a `Config` field for a test would be
a 49th knob nobody sets.
"""
```

and, after `head` is computed at `:156`:

```python
    # v12 §6.5 (specs/2026-09-01-gaffer-v12-program-design.md, plan A8). Every
    # input the trace needs is already in these two artifacts, so it is
    # accounting over what the router has in hand — the solver is not called,
    # not imported for anything but two constants, and cannot see this.
    ep_by, positions, player_names = _trace_inputs(state)
    thresholds = _thresholds(advice)
    ft_lambda = None
    if opt.get("decision_priors"):
        try:
            from gaffer.assets import load_decision_priors
            from gaffer.optimize.ft_value import lambda_from_priors
            ft_lambda = lambda_from_priors(load_decision_priors())
        except Exception as exc:  # noqa: BLE001 — a decoration, never a gate
            print(f"plan trace: no lambda table ({exc}); flat ft_value")
```

`_price_falls` is **not** called here. It is called inside the trace's own
`try` below, so a reader that moved or was renamed in W2 costs the trace and
not the plan — the same rule the λ table above follows, applied one level up
because this reader lives in another workstream.

and the third helper, which is the one carrying orchestrator ruling 1:

```python
def _price_falls(state) -> tuple[bool, dict[int, float]]:
    """``(price_timing is on, {code: p_fall_tonight})`` for the owned squad.

    The same reader the objective's price-timing term uses (W2 §3.4), called
    the same way — so the charge the board prints is the charge the solver
    applied, and not a second estimate of it computed from the same log by
    slightly different arithmetic.

    Two switches, two different answers. ``price_timing`` off means the
    objective carried **no such term**, so the trace reports ``None`` and says
    so rather than printing a zero, which would read as "we checked and it was
    free". A reader that will not import, or that has no row for a code, is
    also ``None`` — an unknown, which is not a zero chance of a fall.

    Imported lazily and inside the try for the same reason the λ table is: a
    decoration must never be the reason a plan does not render.
    """
    try:
        # NOTE: correct this import from Task 0's
        # `grep -rn "def owned_price_falls" src/gaffer` before running the
        # tests. The module is W2's and this plan never saw it; guessing the
        # path is how a decoration becomes a 500 on first contact.
        from gaffer.data.prices import owned_price_falls
        from gaffer.optimize.policy import price_timing as price_timing_on
    except Exception as exc:  # noqa: BLE001 — W2 may not have landed
        print(f"plan trace: no price-timing reader ({exc})")
        return False, {}
    try:
        if not price_timing_on():
            return False, {}
        owned = [int(c) for c in getattr(state, "owned_codes", []) or []]
        return True, {int(k): float(v)
                      for k, v in (owned_price_falls(owned) or {}).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"plan trace: price falls unreadable ({exc})")
        return True, {}
```

`price_timing_on` is the module-level reader from A4 — the same one
`settings_keys.py` names in its `reader` field, so the two surfaces cannot
disagree about whether the term is on. **Import it from one place**: if Task 3
and this task end up with two different dotted paths for it, one of them is
wrong.

with the two helpers above `plan()`:

```python
def _trace_inputs(state) -> tuple[dict, dict, dict]:
    """``({(code, gw): ep}, {code: position}, {code: name})`` off the pool.

    Degrades the way every other reader in this module does: a pool with no
    ``ep_raw`` column yields an empty EP table, which the trace reports as
    "not in the pool" per move rather than as a zero.
    """
    pool = getattr(state, "pool", None)
    columns = getattr(pool, "columns", None)
    if columns is None or "code" not in columns:
        return {}, {}, {}
    ep_by: dict = {}
    positions: dict = {}
    player_names: dict = {}
    has_ep = "ep_raw" in columns
    for row in pool.itertuples():
        code = _int(getattr(row, "code", None), -1)
        if code < 0:
            continue
        positions.setdefault(code, str(getattr(row, "position", "")))
        player_names.setdefault(code, str(getattr(row, "name", code)))
        if has_ep:
            ep_by[(code, _int(getattr(row, "gw", None), -1))] = _float(
                getattr(row, "ep_raw", None))
    return ep_by, positions, player_names


def _thresholds(advice: dict) -> dict[int, float]:
    """``{gw: θ}`` for the chips this run recommends playing."""
    out: dict[int, float] = {}
    rows = advice.get("chip_table")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not (isinstance(row, dict) and row.get("play_now")):
            continue
        if row.get("gw") is None or row.get("threshold") is None:
            continue
        out[_int(row["gw"], -1)] = _float(row["threshold"])
    out.pop(-1, None)
    return out
```

Then, after the `weeks` loop has built its `PlanGw` list, attach the traces in
one pass — the trace runs the free-transfer count forward across the whole
plan, so it cannot be computed a week at a time:

```python
    if TRACE and weeks:
        try:
            price_timing, price_fall = _price_falls(state)
            traced = trace_plan(
                [{"gw": w.gw, "hits": w.hits,
                  "buys": [m.code for m in w.buys],
                  "sells": [m.code for m in w.sells], "chip": w.chip}
                 for w in weeks],
                gws=[int(g) for g in getattr(state, "gws", [])],
                ep_by=ep_by, positions=positions, names=player_names,
                decay=_float(opt.get("decay", 1.0), 1.0), hit_cost=hit_cost,
                ft_value=_float(opt.get("ft_value", 0.0)),
                itb_value=_float(opt.get("itb_value", 0.0)),
                free_transfers=_int(getattr(state, "free_transfers", 0)),
                ft_lambda=ft_lambda, lam=_float(getattr(state, "lam", 0.0)),
                cover=getattr(state, "cover", None) or {},
                thresholds=thresholds, price_timing=price_timing,
                price_fall=price_fall)
            for week, one in zip(weeks, traced):
                week.trace = PlanWeekTrace(**asdict(one))
        except Exception as exc:  # noqa: BLE001
            # A decoration must never be the reason a plan does not render —
            # the board's own rule for the price movers.
            print(f"plan trace unavailable for GW{head}: {exc}")
```

with `from dataclasses import asdict` at the top and `PlanWeekTrace` added to
the `schemas` import.

**One caveat about `price_fall` that the caption has to carry.**
`owned_price_falls` reads *tonight's* price log, and the board may be drawn on
Saturday against a plan solved on Thursday — so the probability the trace
multiplies is not always the one the solve used. It is the best available
reading of the same quantity from the same source, and the disclaimer under the
block already says the trace is the plan's own terms rather than a re-solve;
add four words to it — "priced against tonight's price log" — where the charge
is shown. Freezing `p_fall_tonight` into the solve state would be a change to
`advise.py`, which is protected, for a decoration.

- [ ] **Draw it.** `frontend/src/types.ts` gains `PlanMoveTrace` and
      `PlanWeekTrace` mirroring the models, and `PlanGw` gains
      `trace?: PlanWeekTrace | null`. `PlannerBoard.tsx` gains one block inside
      each week card, after the xPts paragraph at `:206-209`:

```tsx
              {week.trace && (
                <details className="mt-2" data-testid={`board-why-${week.gw}`}>
                  <summary className="cursor-pointer text-text-muted">
                    Why this move
                  </summary>
                  <div className="mt-1 flex flex-col gap-0.5">
                    {week.trace.moves.length === 0 && (
                      <p className="text-text-muted">No moves this week.</p>
                    )}
                    {week.trace.moves.map((m) => (
                      <p key={`${m.buy_code}-${m.sell_code}`}
                         data-testid={`board-why-move-${week.gw}-${m.buy_code}`}>
                        <span>{`${m.sell_name} → ${m.buy_name}`}</span>
                        <span className="num ml-2 text-text">
                          {fmtDelta(m.ep_gain)}
                        </span>
                        {m.note && (
                          <span className="ml-2 text-text-faint">{m.note}</span>
                        )}
                      </p>
                    ))}
                    {week.trace.hit_cost > 0 && (
                      <p className="text-rust">
                        {`hit charge −${fmtNum(week.trace.hit_cost)}`}
                      </p>
                    )}
                    <p className="text-text-faint">
                      {`${week.trace.ft_used} free transfer(s) used; one is `
                       + `worth ${fmtNum(week.trace.ft_shadow)} at the end of `
                       + `the horizon (${week.trace.ft_basis})`}
                    </p>
                    {week.trace.theta !== null && (
                      <p className="text-text-faint">
                        {`chip threshold θ ${fmtNum(week.trace.theta)}`}
                      </p>
                    )}
                    {/* Only when there is a number. `null` means the term was
                        off or the log had no row for a player sold here, and
                        a "−0.00" would read as a charge that was checked and
                        found to be nothing. The week's note carries which. */}
                    {week.trace.price_charge !== null
                      && week.trace.price_charge !== 0 && (
                      <p className="text-text-faint">
                        {`price-timing charge −${fmtNum(week.trace.price_charge)}`
                         + ', priced against tonight’s price log'}
                      </p>
                    )}
                    {week.trace.note && (
                      <p className="text-text-faint"
                         data-testid={`board-why-note-${week.gw}`}>
                        {week.trace.note}
                      </p>
                    )}
                    {/* The sentence that stops "+3.5" being read as a
                        comparison against not doing it. Printed, never
                        hovered: a caveat discovered by hovering is a caveat
                        discovered after the decision. */}
                    <p className="text-text-faint">
                      {'These are the plan’s own objective terms for the '
                       + 'moves it made, not a comparison against a plan that '
                       + 'did not make them — the board never re-solves.'}
                    </p>
                  </div>
                </details>
              )}
```

`fmtDelta` is already exported from `../../kit`; add it to the existing import.

Seven cases in `PlannerBoard.test.tsx`: a week with a trace renders the pair
and its signed gain; a `null` `ep_gain` renders an em dash and the note, never
a zero; a week with an empty `moves` list renders "No moves this week."; a week
whose `trace` is `null` renders no "Why this move" control at all; the
disclaimer sentence is present in the DOM without any interaction beyond
opening the disclosure; a `price_charge` of `null` renders **no** charge line
but **does** render the week's note (so the reader is told the term was off
rather than left with a gap); and a `price_charge` of `0` renders no line
either — the first week is never charged and a "−0.00" is noise.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_plan_trace.py tests/test_web_plan.py
.venv/bin/pytest -q
cd frontend && npx vitest run src/hubs/planning/PlannerBoard.test.tsx \
  && npx vitest run && npx tsc -b --noEmit
git diff --stat -- src/gaffer/optimize/ src/gaffer/advise.py | cat  # empty
```

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/plan.py \
  tests/test_v12_w5_plan_trace.py frontend/src/types.ts \
  frontend/src/hubs/planning/PlannerBoard.tsx \
  frontend/src/hubs/planning/PlannerBoard.test.tsx && git commit -m "$(cat <<'EOF'
feat: the board says why, in the objective's own terms

/api/plan/{gw} carries a per-week trace: the decayed EP difference of each
position-matched swap, the decayed hit charge, the free transfers spent and
what one is worth at the horizon's end, θ where a chip is played, the league
tilt's contribution, and the price-timing charge. Every input was already in
the two artifacts the router loads, so no solver runs and none is imported for
anything but two constants.

The price-timing charge goes through W2's own owned_price_falls rather than a
second reading of the same log, so the board prints the charge the solver
applied and not an estimate of it. It is gated on [optimizer] price_timing:
off, the objective carries no such term, and a zero on the page would say "we
checked and it was free" rather than "we did not charge for this". A reader
that has moved or was renamed costs the trace and not the plan.

The byte-identity gate is discharged here rather than in the solver, because
this is where the risk is: the test turns the accounting off and asserts the
payload the board already drew is character-for-character what it was, minus
the key that was added.

The disclaimer under the numbers is printed rather than hovered. "+3.5" reads
as "the plan is 3.5 better than not doing it" unless it is told otherwise, and
that claim needs a re-solve nobody ran.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — the JSON Schema is emitted and pinned

**Files:**
- Create: `scripts/gen_types.py`
- Create: `frontend/src/schemas.json` (generated, committed)
- Create: `tests/test_v12_w5_gen_types.py`

Spec §6.6, A9. The Python half: `schemas.py` → a deterministic JSON Schema
document, plus the test that says the committed one is current.

- [ ] **Write the failing test.** `tests/test_v12_w5_gen_types.py`:

```python
"""v12 W5 §6.6 — the committed JSON Schema is the live models'.

The Python half of the types pipeline. The TypeScript half is
frontend/src/types.generated.test.ts, which compiles *this* file and diffs the
result against the committed types.generated.ts — so if this test is green and
that one is green, the browser's types are the server's.
"""
from __future__ import annotations

import json
import pathlib

from scripts.gen_types import RENAME, WIRE_ONLY, build_schema, schema_path

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_the_committed_schema_is_the_one_the_models_produce():
    committed = json.loads((REPO / schema_path()).read_text())
    assert committed == build_schema(), (
        "frontend/src/schemas.json is stale — run "
        "`.venv/bin/python scripts/gen_types.py` and commit both it and "
        "frontend/src/types.generated.ts")


def test_it_is_written_deterministically():
    """Twice in one process must be byte-identical, or the diff test becomes a
    coin toss on dict ordering."""
    assert json.dumps(build_schema(), sort_keys=True) == json.dumps(
        build_schema(), sort_keys=True)


def test_every_pydantic_model_in_schemas_py_is_in_it():
    from pydantic import BaseModel

    from gaffer.web import schemas

    live = {name for name, obj in vars(schemas).items()
            if isinstance(obj, type) and issubclass(obj, BaseModel)
            and obj is not BaseModel and obj.__module__ == schemas.__name__}
    emitted = {RENAME.get(name, name) for name in live}
    assert set(build_schema()["definitions"]) == emitted


def test_the_rename_map_names_only_models_that_exist():
    from pydantic import BaseModel

    from gaffer.web import schemas

    live = {name for name, obj in vars(schemas).items()
            if isinstance(obj, type) and issubclass(obj, BaseModel)}
    assert set(RENAME) <= live
    assert set(WIRE_ONLY) <= live


def test_every_wire_only_model_is_renamed_with_the_wire_prefix():
    """The six models the client narrows by hand (AdviceLatest.advice is
    dict[str, Any] on the server and an `Advice` interface in the browser).
    Emitting them under their plain names would collide with the narrowing and
    break every consumer."""
    for name in WIRE_ONLY:
        assert RENAME[name] == f"Wire{name}"


def test_no_two_models_are_renamed_onto_one_name():
    assert len(set(RENAME.values())) == len(RENAME)


def test_every_ref_points_at_a_definition_that_exists():
    schema = build_schema()
    text = json.dumps(schema)
    import re
    refs = set(re.findall(r'"#/definitions/([A-Za-z0-9_]+)"', text))
    assert refs <= set(schema["definitions"])


def test_the_root_uses_definitions_and_not_defs():
    """json-schema-to-typescript reads `definitions`. A 2020-12 `$defs`
    document compiles to a single empty interface and nothing says why."""
    schema = build_schema()
    assert "definitions" in schema and "$defs" not in schema
```

Run: `.venv/bin/pytest -q tests/test_v12_w5_gen_types.py` — fails on the
missing module.

- [ ] **Implement the generator.** `scripts/gen_types.py`:

```python
"""schemas.py -> frontend/src/schemas.json (v12 W5 §6.6).

Run it and commit both outputs:

    .venv/bin/python scripts/gen_types.py

`types.ts` is **not** generated and cannot be. Twenty-eight of its exports have
no pydantic source — thirteen of them type the *inside* of payloads the server
declares as `dict[str, Any]` — and six models are narrowed by hand in the
browser. A generator that overwrote `types.ts` would delete a third of the file
and stop every `advice.captain.name` in the tree from compiling (plan A9).

So the file splits. This script emits the JSON Schema; the vitest test
`frontend/src/types.generated.test.ts` compiles it with
`json-schema-to-typescript` and diffs the result against the committed
`frontend/src/types.generated.ts`; and `frontend/src/types.ts` keeps the
hand-written half and re-exports the generated one, so every existing
`import ... from '../types'` is unchanged.
"""

from __future__ import annotations

import json
import pathlib
import sys

WIRE_ONLY = (
    "AdviceLatest", "History", "ModelHealth", "Health", "CalibrationReport",
    "ReviewSummary",
)
"""Models carrying ``Any``, which the client narrows by hand.

Emitted as ``Wire<Name>`` — literally "what the server sends" — so the
hand-written narrowing keeps the plain name and nothing collides. Each one has
at least one field the generator can only describe as an open record:
``AdviceLatest.advice``, ``History.backtests``, ``ModelHealth.metrics``,
``Health.model_health``, ``CalibrationReport.excluded``,
``ReviewSummary.best``/``worst``.
"""

RENAME = {
    # The client suffixes a page-level payload with `Data` so the name does not
    # collide with a component or a lane name. Fifteen of these predate this
    # script and every one of them has consumers.
    "CalibrationReport": "WireCalibrationReport",
    "Confidence": "ConfidenceData",
    "Decomposition": "DecompositionData",
    "FixtureMatrix": "FixtureMatrixData",
    "Journal": "JournalData",
    "LeagueRace": "LeagueRaceData",
    "Misses": "MissesData",
    "NewsShadow": "NewsShadowData",
    "PenTracker": "PenTrackerData",
    "Quality": "QualityData",
    "Review": "ReviewData",
    "RivalDetail": "RivalDetailData",
    "Ticker": "TickerData",
    # The wire-only six.
    "AdviceLatest": "WireAdviceLatest",
    "History": "WireHistory",
    "ModelHealth": "WireModelHealth",
    "Health": "WireHealth",
    "ReviewSummary": "WireReviewSummary",
}
"""Pydantic name -> TypeScript name.

``CalibrationReport``, ``Health`` and ``History`` appear once each: they are
both renamed *and* wire-only, and the ``Wire`` prefix wins because the
hand-written ``CalibrationData``/``HealthData``/``HistoryData`` are the
narrowings. The test ``test_every_wire_only_model_is_renamed_with_the_wire_prefix``
is what keeps that consistent.
"""


def schema_path() -> str:
    return "frontend/src/schemas.json"


def _models():
    from pydantic import BaseModel

    from gaffer.web import schemas

    out = []
    for name, obj in sorted(vars(schemas).items()):
        if (isinstance(obj, type) and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == schemas.__name__):
            out.append((name, obj))
    return out


def build_schema() -> dict:
    """Every response model as one ``definitions`` document.

    ``definitions`` and not ``$defs``: ``json-schema-to-typescript`` reads the
    former, and a 2020-12 document compiles to one empty interface with
    nothing saying why.

    Sorted throughout and emitted through ``json.dumps(sort_keys=True)`` by
    :func:`main`, because the whole point is a diff that is stable across
    machines and interpreter runs.
    """
    from pydantic.json_schema import models_json_schema

    models = _models()
    _, top = models_json_schema(
        [(model, "serialization") for _, model in models],
        ref_template="#/definitions/{model}", title="Gaffer API")
    defs = top.get("$defs", {})
    renamed = {RENAME.get(name, name): defs[name]
               for name in sorted(defs) if name in defs}
    text = json.dumps({"definitions": renamed}, sort_keys=True)
    for old, new in RENAME.items():
        text = text.replace(f'"#/definitions/{old}"',
                            f'"#/definitions/{new}"')
    return json.loads(text)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    target = root / schema_path()
    target.write_text(json.dumps(build_schema(), sort_keys=True, indent=1)
                      + "\n")
    print(f"wrote {target}")
    print("now run: cd frontend && npx vitest run src/types.generated.test.ts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Two things to check while implementing, not after.** `models_json_schema`'s
return shape differs between pydantic minors; run
`.venv/bin/python -c "import pydantic; print(pydantic.VERSION)"` and read the
signature before assuming `(mapping, top)`. And the `RENAME` map above lists
18 entries; the true list is whatever
`test_every_pydantic_model_in_schemas_py_is_in_it` accepts — **derive it, do
not trust this table**, with:

```bash
.venv/bin/python - <<'PY'
import json, pathlib, re
ts = pathlib.Path("frontend/src/types.ts").read_text()
have = set(re.findall(r"^export (?:interface|type) ([A-Za-z0-9_]+)", ts,
                      re.M))
from pydantic import BaseModel
from gaffer.web import schemas
live = {n for n, o in vars(schemas).items()
        if isinstance(o, type) and issubclass(o, BaseModel)
        and o.__module__ == schemas.__name__}
print("py-only:", sorted(live - have))
print("ts-only:", sorted(have - live))
PY
```

At `27f7933` that prints the 37 and 28 names quoted in A9. If either list
differs at W5's base, **stop and report** — an earlier workstream added a model
and the rename map has to account for it.

- [ ] **Generate and commit.**

```bash
.venv/bin/python scripts/gen_types.py
.venv/bin/pytest -q tests/test_v12_w5_gen_types.py
```

```bash
git add scripts/gen_types.py frontend/src/schemas.json \
  tests/test_v12_w5_gen_types.py && git commit -m "$(cat <<'EOF'
feat: schemas.py emits a committed JSON Schema, pinned by a test

The Python half of §6.6. One `definitions` document — not `$defs`, which
json-schema-to-typescript compiles to a single empty interface with nothing
saying why — sorted throughout so the diff is stable across machines.

The rename map is the honest part. Fifteen client types suffix a page payload
with `Data`, and six models carry `Any` fields the browser narrows by hand;
those six are emitted as `Wire<Name>` so the narrowing keeps the plain name and
nothing collides.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — `types.generated.ts`, and `types.ts` re-exports it

**Files:**
- Modify: `frontend/package.json` (one pinned devDependency)
- Create: `frontend/src/types.generated.ts` (generated, committed)
- Create: `frontend/src/types.generated.test.ts`
- Modify: `frontend/src/types.ts` (delete the generated half, re-export, keep
  the hand-written half and the six narrowings)
- Modify: `frontend/src/types.test.ts` (three cases)

Spec §6.6, A9.

- [ ] **Pin the generator.** `frontend/package.json`, in `devDependencies`,
      alphabetically:

```json
    "json-schema-to-typescript": "16.0.0",
```

**Exactly, with no caret.** A generator whose output can drift between patch
releases turns a diff test into a Tuesday-morning failure nobody caused.
`16.0.0` is what `npm view json-schema-to-typescript version` resolved to at
planning time; run it again, record the answer in the commit message, and **pin
16.0.0 regardless** — this is a pin, not a "latest". Then:

```bash
cd frontend && npm install
```

- [ ] **Write the failing test.** `frontend/src/types.generated.test.ts`:

```ts
/**
 * v12 W5 §6.6 — the generated types are the committed schema's.
 *
 * `compile()` is called as a library rather than through `npx`: no network, no
 * subprocess, no `npx` resolution inside a test, and it runs wherever
 * `npm ci` has run.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { compile } from 'json-schema-to-typescript'
import { describe, expect, it } from 'vitest'

const HERE = join(__dirname)

export const OPTIONS = {
  bannerComment: '',
  additionalProperties: false,
  unreachableDefinitions: true,
  declareExternallyReferenced: true,
  style: { singleQuote: true, semi: false },
} as const

async function generate(): Promise<string> {
  const schema = JSON.parse(readFileSync(join(HERE, 'schemas.json'), 'utf8'))
  return compile(schema, 'GafferApi', OPTIONS)
}

describe('types.generated.ts', () => {
  it('is exactly what the committed schema compiles to', async () => {
    const fresh = await generate()
    const committed = readFileSync(join(HERE, 'types.generated.ts'), 'utf8')
    expect(committed).toBe(fresh)
  }, 60_000)

  it('is deterministic', async () => {
    expect(await generate()).toBe(await generate())
  }, 60_000)
})
```

Run: `cd frontend && npx vitest run src/types.generated.test.ts` — fails on the
missing `types.generated.ts`.

- [ ] **Generate the file.** A one-off script run from `frontend/`, not
      committed:

```bash
cd frontend && node --input-type=module -e "
import { readFileSync, writeFileSync } from 'node:fs'
import { compile } from 'json-schema-to-typescript'
const schema = JSON.parse(readFileSync('src/schemas.json', 'utf8'))
const out = await compile(schema, 'GafferApi', {
  bannerComment: '', additionalProperties: false,
  unreachableDefinitions: true, declareExternallyReferenced: true,
  style: { singleQuote: true, semi: false } })
writeFileSync('src/types.generated.ts', out)
"
```

Then add the banner by hand at the top of the emitted file — `bannerComment` is
`''` above so the banner is under this plan's control rather than the
generator's, and a banner the generator writes would change between versions:

```ts
/* eslint-disable */
/**
 * GENERATED — do not edit.
 *
 * `scripts/gen_types.py` writes `src/schemas.json` from
 * `src/gaffer/web/schemas.py`; `src/types.generated.test.ts` compiles that
 * with json-schema-to-typescript (pinned 16.0.0) and asserts this file is the
 * result. Edit the pydantic model, re-run both, commit all three.
 *
 * The hand-written half of the client's types — and the narrowings of the six
 * `Wire*` models, whose payloads the server declares as `dict[str, Any]` —
 * lives in `types.ts`, which re-exports this file.
 */
```

and add the same banner literal to the test's `generate()` so the comparison
includes it:

```ts
const BANNER = readFileSync(join(HERE, 'types.banner.txt'), 'utf8')

async function generate(): Promise<string> {
  const schema = JSON.parse(readFileSync(join(HERE, 'schemas.json'), 'utf8'))
  return BANNER + await compile(schema, 'GafferApi', OPTIONS)
}
```

with the banner text in `frontend/src/types.banner.txt` so it lives in exactly
one place. Create that file with the banner above.

- [ ] **Split `types.ts`.** Delete every interface in `types.ts` whose name is
      now emitted by the generator, add the re-export at the top, and keep:
      the 28 hand-written exports (A9's list), the six narrowings, and every
      doc comment on them.

```ts
// The generated half: every pydantic response model, compiled from
// src/schemas.json. Re-exported so `import { PlayerRow } from '../types'`
// keeps working everywhere it already does.
export * from './types.generated'
```

Each of the six narrowings then reads as an override of its `Wire` twin, and
says so:

```ts
/** `WireAdviceLatest` with `advice` narrowed. The server declares that field
 *  as `dict[str, Any]`, so the generator can only describe it as an open
 *  record — but every consumer in this tree reads `advice.captain.name`. */
export interface AdviceLatest extends Omit<WireAdviceLatest, 'advice'> {
  advice: Advice
}
```

Five of the six narrowings already exist in `types.ts` under the names their
consumers import — `AdviceLatest`, `HistoryData`, `HealthData`,
`CalibrationData`, `ReviewSummary` — and are rewritten as `extends Omit<Wire…>`
so the shared fields stop being maintained twice. **`ModelHealth` has no client
type today** (it is one of the 22 pydantic-only models, inlined inside
`HealthData`), so Task 12 creates it: `export interface ModelHealth extends
Omit<WireModelHealth, 'metrics'> { metrics: Record<string, unknown> }`. That is
the same shape the generator would emit, written by hand so the narrowing map
is exhaustive and `HealthData` has something to reference.

- [ ] **Guard the split.** Three cases in `frontend/src/types.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function exportsOf(file: string): Set<string> {
  const text = readFileSync(join(__dirname, file), 'utf8')
  return new Set([...text.matchAll(
    /^export (?:interface|type|declare interface) ([A-Za-z0-9_]+)/gm,
  )].map((m) => m[1]))
}

it('does not declare a name the generated file also declares', () => {
  const hand = exportsOf('types.ts')
  const gen = exportsOf('types.generated.ts')
  expect([...hand].filter((n) => gen.has(n))).toEqual([])
})

it('still exports every name the tree imported before the split', () => {
  // The list is v11's export surface, transcribed. A rename that quietly
  // dropped a type would otherwise be a green suite and a red build.
  const all = new Set([...exportsOf('types.ts'),
    ...exportsOf('types.generated.ts')])
  for (const name of ['Advice', 'AdviceLatest', 'PlayerRow', 'PlanTimeline',
    'PlanGw', 'PlanMove', 'ReviewData', 'ReviewGw', 'HealthData',
    'QualityData', 'WatchlistPanel', 'MoversPanel', 'WhatIfRequest',
    'SettingsPanel', 'SettingRow']) {
    expect(all.has(name)).toBe(true)
  }
})

it('narrows every Wire model exactly once', () => {
  // The narrowing does not always keep the pydantic name: three of the six
  // are also `*Data` renames on the client, and the Wire prefix won in the
  // generator so the hand-written narrowing could keep the name its consumers
  // already import. The pairs are therefore listed rather than derived.
  const NARROWING: Record<string, string> = {
    WireAdviceLatest: 'AdviceLatest',
    WireHistory: 'HistoryData',
    WireModelHealth: 'ModelHealth',
    WireHealth: 'HealthData',
    WireCalibrationReport: 'CalibrationData',
    WireReviewSummary: 'ReviewSummary',
  }
  const gen = exportsOf('types.generated.ts')
  const hand = exportsOf('types.ts')
  const wires = [...gen].filter((n) => n.startsWith('Wire')).sort()
  expect(wires).toEqual(Object.keys(NARROWING).sort())
  for (const wire of wires) expect(hand.has(NARROWING[wire])).toBe(true)
})
```

The second case's list must be the **full** v11 export surface, not the fifteen
above — generate it once from `git show HEAD~1:frontend/src/types.ts` and paste
it in. A short list is a test that passes by not looking.

- [ ] **Delete the duplicate settings types.** `SettingRow` and
      `SettingsPanel` were hand-written in Task 4 and are now generated; the
      disjointness test is what catches them. Remove the hand-written pair.

- [ ] **Verify.**

```bash
cd frontend && npx vitest run src/types.generated.test.ts src/types.test.ts
cd frontend && npx tsc -b --noEmit
cd frontend && npx vitest run
.venv/bin/pytest -q tests/test_v12_w5_gen_types.py
```

`tsc` is the real gate here: it compiles every consumer against the new
surface. A failure naming a missing type means the split dropped it — **restore
it, do not widen a type to `any`.**

- [ ] **Commit.**

```bash
git add frontend/package.json frontend/package-lock.json \
  frontend/src/types.generated.ts frontend/src/types.generated.test.ts \
  frontend/src/types.banner.txt frontend/src/types.ts \
  frontend/src/types.test.ts && git commit -m "$(cat <<'EOF'
feat: the pydantic half of types.ts is generated and diffed

§6.6 asked for types.ts to be generated from schemas.py. It cannot be: 28 of
its 118 exports have no pydantic source, 15 more are renames, and six models
carry Any fields the browser narrows by hand — AdviceLatest.advice above all,
which is dict[str, Any] on the server and an `Advice` interface in every
consumer. A generator that overwrote types.ts would delete a third of the file
and stop the tree compiling.

So the file splits. types.generated.ts is compiled from the committed
schemas.json with json-schema-to-typescript, pinned at 16.0.0 with no caret;
types.ts keeps the hand-written half, narrows the six Wire models, and
re-exports the generated file so no import anywhere changed.

compile() is called as a library from vitest rather than through npx: no
network, no subprocess, and the test runs wherever npm ci has run. Three
guards keep the split honest — the two halves declare disjoint names, every
name the tree imported before still exists, and every Wire model has exactly
one narrowing.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — the degradation rail and this cycle's pins

**Files:**
- Create: `tests/test_v12_w5_degradation.py`
- Create: `frontend/src/hubs/w5.coldclone.test.tsx`

Spec §1, and the brief's pin rule. **This file contains no `len(paths) == N`.**
The absolute route count is pinned in `tests/test_v11_degradation.py` and
nowhere else, and v11's meta-test greps for exactly that pattern; W5 pins its
routes **by name**.

- [ ] **Write it.** `tests/test_v12_w5_degradation.py`:

```python
"""v12 W5 degradation and pins.

Every surface this workstream added, on a tree with nothing in it. The counts
at the bottom are asserted against the values Task 0 measured at W5's base —
not against 45/12/48, which were W1's starting point and which W1-W3 moved.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from gaffer.config import serving_config
from gaffer.web.app import create_app

# Filled in from Task 0's measurement, not assumed. JOB_KINDS and Config are
# what W1-W4 left; W5 adds none of either.
JOB_KINDS_AT_BASE = 12      # <- Task 0
CONFIG_FIELDS_AT_BASE = 48  # <- Task 0


@pytest.fixture()
def cold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


# --- Block 1: the cold clone reaches every new surface --------------------


def test_settings_on_a_cold_clone_is_a_200_that_names_the_file_to_copy(cold):
    body = cold.get("/api/settings")
    assert body.status_code == 200
    assert body.json()["rows"] == []
    assert "config.example.toml" in body.json()["overlay_error"]


def test_a_settings_write_on_a_cold_clone_refuses_rather_than_writing(cold,
                                                                      tmp_path):
    body = cold.post("/api/settings", json={"key": "horizon", "value": 5})
    assert body.status_code == 422
    assert not (tmp_path / "config.local.toml").exists()


def test_the_plan_is_still_a_404_that_names_the_command(cold):
    body = cold.get("/api/plan/5")
    assert body.status_code == 404
    assert "advise" in body.json()["detail"]


def test_the_review_ledger_is_still_an_empty_200(cold):
    assert cold.get("/api/review").json() == {"gws": [], "summary": None}


def test_the_watchlist_is_still_an_empty_200(cold):
    assert cold.get("/api/watchlist").json() == {"rows": []}


# --- Block 2: W5's routes, by name ---------------------------------------


def test_w5_added_exactly_one_path_and_this_is_its_name(cold):
    """Pinned by name and by absence, never by total: the absolute count lives
    in test_v11_degradation.py and v11's meta-test enforces that it lives
    nowhere else."""
    paths = set(create_app().openapi()["paths"])
    assert "/api/settings" in paths
    assert not [p for p in paths
                if p.startswith(("/api/trace", "/api/projections",
                                 "/api/config"))]


def test_settings_answers_both_verbs_on_one_path(cold):
    spec = create_app().openapi()["paths"]["/api/settings"]
    assert set(spec) == {"get", "post"}


def test_this_file_does_not_pin_the_absolute_route_count():
    """The rule v11 wrote down, checked from inside the file it constrains."""
    text = pathlib.Path(__file__).read_text()
    assert not re.search(r"len\(\s*(?:set\()?\s*paths\)?\s*\)\s*==\s*\d+",
                         text)


# --- Block 3: the counts W5 did not move ---------------------------------


def test_w5_added_no_job_kind():
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == JOB_KINDS_AT_BASE


def test_w5_added_no_config_field():
    """config.local.toml is a loader change. A settings *file* is not a
    settings *field*."""
    import dataclasses

    from gaffer.config import Config

    assert len(dataclasses.fields(Config)) == CONFIG_FIELDS_AT_BASE


# --- Block 4: the honesty rules, checked rather than asserted in prose ----


def test_no_snapshot_reader_defaults_a_season():
    """Spec §1's season guard. `season` is positional and required; a default
    would make a cross-season read the easy call."""
    import inspect

    from gaffer.artifacts import (latest_projection_before,
                                  projection_snapshots)

    for fn in (projection_snapshots, latest_projection_before):
        season = inspect.signature(fn).parameters["season"]
        assert season.default is inspect.Parameter.empty


def test_the_trace_never_reports_a_measured_zero_for_an_unknown():
    from gaffer.trace import trace_plan

    out = trace_plan([{"gw": 5, "buys": [1], "sells": [], "hits": 0,
                       "chip": None}],
                     gws=[5], ep_by={}, positions={}, names={}, decay=1.0,
                     hit_cost=4, ft_value=1.5, itb_value=0.05,
                     free_transfers=1)
    assert out[0].moves[0].ep_gain is None
    assert out[0].ep_gain is None


def test_the_settings_whitelist_cannot_reach_a_secret():
    """The one thing this endpoint must never be able to write."""
    from gaffer.web.settings_keys import WHITELIST

    names = {e.field for e in WHITELIST}
    assert not names & {"odds_api_key", "entry_id", "league_id",
                        "train_seasons", "news_llm_command"}


def test_nothing_this_workstream_wrote_mentions_a_solver_section():
    """Program-wide ruling, 2026-09-02: the spec's `[solver]` table does not
    exist and every key it names is `[optimizer]`."""
    root = pathlib.Path(__file__).resolve().parents[1]
    written = [root / "src/gaffer/web/settings_keys.py",
               root / "src/gaffer/web/routers/settings.py",
               root / "src/gaffer/trace.py",
               root / "config.example.toml"]
    for path in written:
        assert "[solver]" not in path.read_text(), path


def test_the_price_charge_is_none_rather_than_zero_when_the_term_is_off():
    """The distinction the gate exists for: "we did not charge for this" and
    "we checked and it was free" are different sentences."""
    from gaffer.trace import trace_plan

    weeks = [{"gw": 5, "buys": [], "sells": [], "hits": 0, "chip": None},
             {"gw": 6, "buys": [], "sells": [7], "hits": 0, "chip": None}]
    off = trace_plan(weeks, gws=[5, 6], ep_by={}, positions={}, names={},
                     decay=1.0, hit_cost=4, ft_value=1.5, itb_value=0.05,
                     free_transfers=1, price_timing=False,
                     price_fall={7: 0.9})
    assert off[1].price_charge is None
```

- [ ] **Write the client's cold-clone rail.**
      `frontend/src/hubs/w5.coldclone.test.tsx` — the same shape as
      `coldclone.test.tsx`, rejecting every `apiGet`, asserting that the
      **three new tabs each reach an `EmptyState`**: the Settings tab (naming
      `config.example.toml`), the Watchlist tab (naming the Explorer's star),
      and the board with a `null` trace (which draws no "Why this move" control
      rather than an empty disclosure). `coldclone.test.tsx` renders only each
      hub's *default* tab, which is why these are written per view — v11 A18's
      finding, unchanged.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w5_degradation.py
.venv/bin/pytest -q tests/test_v11_degradation.py
cd frontend && npx vitest run src/hubs/w5.coldclone.test.tsx && npx vitest run
```

- [ ] **Commit.**

```bash
git add tests/test_v12_w5_degradation.py \
  frontend/src/hubs/w5.coldclone.test.tsx && git commit -m "$(cat <<'EOF'
test: W5's degradation rail, and the pins it did not move

Every new surface on a tree with nothing in it, plus the two counts this
workstream left alone. The route count is pinned by *name* here and by total in
test_v11_degradation.py, which is where v11 put it and where its meta-test
insists it stays — and a test in this file checks that this file obeys that.

Three honesty rules are checked rather than asserted in prose: the snapshot
readers cannot default a season, the trace reports None and never a measured
zero for something it could not read, and the settings whitelist cannot reach
the odds API key, the entry id, the league id, the training seasons or the LLM
command.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — the documentation, and the residuals

**Files:**
- Modify: `docs/GUIDE.md` (§5 hub descriptions; §8 the CLI table gains
  `gen_types.py`; §12 the pending list)
- Modify: `README.md` (the config section gains `config.local.toml`)
- Modify: `docs/superpowers/ROADMAP.md` (W5's items, and the data-gated
  checkbox)

- [ ] **GUIDE §5.** Under **Planning → Board**, add one sentence: *"'Why this
      move' opens the objective's own terms for that week's transfers — the
      decayed points difference of each swap, the hit charge, what a free
      transfer is worth at the end of the horizon, θ where a chip is played.
      It is accounting over the plan the solver returned, not a comparison
      against a plan it did not make."* Under **Players**, add the Watchlist
      tab. Under **Model**, add the Settings tab and say in one sentence that
      it writes `config.local.toml` and never `config.toml`. Add one line to
      the hub preamble: every hub's open tab is in `?tab=`, so a tab can be
      linked to.

- [ ] **GUIDE §8 and README.** One row for
      `.venv/bin/python scripts/gen_types.py` — what it writes and when to run
      it (after any change to `web/schemas.py`). In README's configuration
      section, `config.local.toml`: what it is, that the UI owns it, that it is
      gitignored, and that a key in `[optimizer]` or `[data]` which is not a
      config field is ignored with a printed line.

- [ ] **GUIDE §12 — the residuals this workstream leaves open.** Four, each
      one sentence:
  1. **The trace's price-timing charge is read from tonight's price log, not
     from the solve.** `owned_price_falls` is the same reader the objective
     uses, but a board drawn on Saturday against a Thursday plan multiplies a
     probability the solve never saw. Freezing it would mean writing it into
     the solve state from `advise.py`, which is protected, for a decoration.
  2. **`projection_snapshot` fills forward only.** Grades are banked and never
     re-derived, so every ledger row banked before W5 keeps `None` for ever.
  3. **`reports/projections/` is never pruned.** ~6-12 MB a season, gitignored.
     A future `gaffer tidy` target, deliberately not invented here.
  4. **The watchlist's `set_at` is reset by every save**, because
     `watchlist.watch` replaces the note and the timestamp together. The column
     is labelled "noted" rather than "watching since" for that reason; fixing
     it means a second store field.

- [ ] **ROADMAP.** Tick §6.1–§6.6. Add two **data-gated checkboxes**, each
      naming the condition that unblocks it, per spec §1:
      *"[ ] The trace's price-timing charge shows a number — unblocked when
      `[optimizer] price_timing` is on and the nightly price log has run long
      enough for `owned_price_falls` to return a row per owned player (W2
      §3.4)."* And: *"[ ] A Review row names its projection snapshot —
      unblocked at the first gameweek graded after v12 W5 merges."*

- [ ] **Verify.** Documentation only; no test runs. Read the two GUIDE sections
      back and check every route, filename and command named in them exists:

```bash
grep -n "config.local.toml\|gen_types.py\|/api/settings\|?tab=" \
  docs/GUIDE.md README.md docs/superpowers/ROADMAP.md
ls scripts/gen_types.py config.example.toml
```

- [ ] **Commit.**

```bash
git add docs/GUIDE.md README.md docs/superpowers/ROADMAP.md \
  && git commit -m "$(cat <<'EOF'
docs: W5's six surfaces, and the four residuals it leaves standing

The Settings tab and the file it owns, the Watchlist tab, the board's "why this
move", the tab in the URL, and the generator to re-run after touching
schemas.py.

The residuals are the half worth reading: the price-timing charge has nowhere
to read its probability from until W2 banks one, projection snapshots fill
forward only because grades are banked and never re-derived, the snapshot
directory is never pruned, and the watchlist's date is reset by every note save
because the store replaces both together.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 15 — the gate checklist (results unfilled)

**Files:** none. **The implementer builds this and does not run it**
(CONVENTIONS §7). Every result below is left blank for the orchestrator.

### G1 — the suite

```bash
.venv/bin/pytest -q 2>&1 | tail -3
#   baseline at W5's base (Task 0): ______ collected, all passing
#   result: ______________________________________________

cd frontend && npx vitest run 2>&1 | tail -5
#   baseline at W5's base (Task 0): ______ passed, 1 skipped (___ files)
#   result: ______________________________________________

cd frontend && npx tsc -b --noEmit
#   result: ______________________________________________
```

### G2 — zero unauthorized protected diffs

```bash
BASE=<W5 base sha from Task 0>
git diff --stat $BASE..HEAD -- \
  src/gaffer/advise.py src/gaffer/set_pieces.py src/gaffer/optimize/ \
  src/gaffer/web/jobs.py src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py | cat
#   expected: empty
#   result: ______________________________________________

git diff --stat $BASE..HEAD -- tests/test_*_degradation.py | cat
#   expected: exactly one file — tests/test_v11_degradation.py, two
#   line-groups, both enumerated in Task 3 and both carrying the provenance
#   comment `# v12 W5 §6.2 (specs/2026-09-01-gaffer-v12-program-design.md)`
#   result: ______________________________________________

git diff $BASE..HEAD -- tests/test_v11_degradation.py | cat
#   read it: the docstring's number and the assertion, and nothing else
#   result: ______________________________________________
```

### G3 — §6.5's byte-identity, and the six-hub pass

```bash
.venv/bin/pytest -q tests/test_v12_w5_plan_trace.py \
  -k "byte_identical or imported_by_no_solver"
.venv/bin/pytest -q tests/test_v12_w5_trace.py -k "imported_by_no_solver"
#   result: ______________________________________________
```

**The manual pass (spec §6 gate: "a manual pass through all six hubs with the
'as of' strip and URL state").** W1 owns the "as of" strip; W5 owns the URL
state. Per hub — This Week, Planning, Players, League, Live, Model — with
`uv run gaffer ui`:

| Hub | `?tab=` round-trips | strip renders | notes |
| --- | --- | --- | --- |
| This Week | n/a (no tabs) | ____ | ____ |
| Planning | ____ | ____ | ____ |
| Players | ____ | ____ | ____ |
| League | ____ | ____ | ____ |
| Live | n/a (no tabs) | ____ | ____ |
| Model | ____ | ____ | ____ |

Plus, on the Model hub: change one setting, confirm it lands in
`config.local.toml`, confirm `config.toml` is byte-identical afterwards
(`git status` must not list it, and it is gitignored so `md5 config.toml`
before and after is the check), and reset it.

### G4 — the post-merge security ritual (CONVENTIONS §8)

```bash
git show main:config.toml            # must fail
git show main:config.local.toml      # must fail
git log -S"$(grep -o 'api_key[^\n]*' config.toml | head -1)" --all | cat
git log -p $BASE..HEAD | grep -nEi "api[_-]?key|secret|token|bearer" | cat
#   result: ______________________________________________
```

### G5 — pins

```bash
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
#   expected: (Task 0's paths + 1), Task 0's job kinds, Task 0's config fields
#   result: ______________________________________________

grep -rn "len(paths) ==\|openapi()\[.paths.\]) ==" tests/ | cat
#   expected: exactly one hit, in tests/test_v11_degradation.py
#   result: ______________________________________________
```

### G6 — the staging audit

```bash
git log --stat $BASE..HEAD | grep -E "^ (data|reports|models|logs|config\.toml|config\.local\.toml)/" | cat
#   expected: empty
#   result: ______________________________________________
```

---
