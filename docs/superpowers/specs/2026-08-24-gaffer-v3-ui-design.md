# Gaffer v3 — Local Web UI Design

Date: 2026-08-24
Status: approved design, pre-implementation
Predecessors: `2026-08-23-fpl-ml-advisor-design.md` (v1), `2026-08-24-gaffer-v2-design.md` (v2)

## 1. Goal

Give gaffer a local web UI so the tool is usable without the terminal, and add four
features that the CLI could not carry well: EP explainability, a chip timing planner,
rival squad intel, and a fixture ticker. The advisor remains advisor-only: it never
logs into FPL and never submits anything. Phase 2 (a later, separate cycle) wraps the
same local server in a macOS menu-bar app; this spec only requires that nothing here
precludes that.

Decisions locked during brainstorming:

- Local web app now; macOS shell later.
- Full what-if cockpit: user constraints trigger a real MILP re-solve.
- Layout A — sidebar cockpit with pages: This Week / What-If Lab / League Race /
  Live / Players / History / Runs & Health.
- Stack: FastAPI JSON API + React/Vite SPA, frontend built to static assets so
  `gaffer ui` is a single command with no node at runtime.
- Both core-screen mockups approved (preserved under `.superpowers/brainstorm/`).

## 2. Architecture

### 2.1 Backend — `src/gaffer/web/`

A FastAPI app with thin routers that wrap existing modules (`advise`, `live_gw`,
`league_mode`, `optimize`, `data`, `models`). No logic moves out of those modules;
routers call the same functions the CLI calls and serialize results to JSON via
Pydantic response models.

Layout:

```
src/gaffer/web/
  app.py         # create_app(), static mounting, lifespan
  jobs.py        # background job runner (threads), job registry
  schemas.py     # Pydantic response/request models
  routers/
    advice.py    # this-week, components, chip planner
    whatif.py    # constraint re-solve
    league.py    # race, rival intel
    live.py      # live GW
    players.py   # player browser, EP explainability
    meta.py      # history, runs & health, fixtures ticker
  static/        # built frontend (generated, packaged; gitignored except .gitkeep)
```

**Long operations** (advise re-run, what-if solve) run in a background thread via a
small in-process job registry: `POST` returns `{job_id}`; `GET /api/jobs/{id}`
returns `{status: queued|running|done|error, result?, error?}`. The UI polls. One
worker thread; concurrent solve requests queue (FIFO), and the registry caps the
queue (reject with 429 beyond ~5 pending). Jobs carry a timeout (default 120 s for
what-if, 30 min for full advise+train) after which they report `error`. No
websockets in v3 — polling is sufficient at localhost latency.

**Server lifecycle**: `gaffer ui` (new CLI command) starts uvicorn bound to
`127.0.0.1` on a default port (8927, overridable `--port`), opens the browser, and
runs until Ctrl-C. Localhost-only bind is the security model; no auth.

### 2.2 Frontend — `frontend/`

React + Vite + TypeScript at the repo top level. `npm run build` emits into
`src/gaffer/web/static/` (Vite `outDir`), which ships in the wheel via the same
`importlib.resources` packaging pattern as the v1 report assets. FastAPI mounts it
and serves `index.html` for unknown non-`/api` paths (SPA routing).

Frontend conventions: React Router for the seven pages, TanStack Query (or a thin
fetch hook — implementer's choice, kept consistent) for API calls and job polling,
no global state library, CSS via a single design-token stylesheet (dark-friendly,
matches the mockups' pitch-green aesthetic). Recharts (or lightweight SVG) for the
few charts. No component library dependency unless the implementer justifies one in
the plan.

Dev workflow: `npm run dev` proxies `/api` to the local FastAPI (documented in
README). End users never need node.

### 2.3 Data flow

The server reads the same on-disk artifacts the CLI produces (latest advice,
live snapshots, price history, health, odds parquets) and can trigger fresh runs.

**New persistence requirement (the only model-side change):** `advise` additionally
writes a per-run **components file** — `reports/components_gw{N}.parquet` — with one
row per (player, fixture) in the candidate pool: minutes p60/p1, each component EP
(attacking, CS, bonus, defcon, set-piece contribution), calibration delta, odds
blend inputs and weight actually applied, opponent, home/away, and the final
per-fixture EP. This powers EP explainability and costs nothing extra: it is the
data `advise` already computes, persisted before aggregation.

Baseline for the What-If Lab is the most recent advise run's saved solve inputs
(EP matrix, prices, squad state), which `advise` also persists
(`reports/solve_state_gw{N}.parquet`/json). What-if re-solves therefore never
retrain or refetch — they are pure MILP re-runs and complete in seconds.

## 3. Pages and API

All endpoints under `/api`. GETs are read-only; POSTs create jobs or mutate nothing
outside the job registry.

### 3.1 This Week (home)

`GET /api/advice/latest` → the current recommendation: GW, deadline, mode
(normal/GW1), league context line (gap to leader, λ, win probability), XI + bench
with EP and captain/vice, transfer plan (in/out, hits, expected gain over horizon,
attack/cover tags), chip evaluations (raw), staleness metadata (advice GW vs
current GW, generated-at). `POST /api/advice/rerun` → job that runs train+advise
(equivalent to the CLI); on completion the page refetches.

### 3.2 What-If Lab

`POST /api/whatif` body:

```json
{
  "lock": [player_ids],      // must be in final squad
  "ban": [player_ids],       // must not be in final squad
  "force_in": [player_ids],  // must be transferred in this GW
  "max_hits": 0,
  "chip": "none|wc|bb|fh|tc",
  "horizon": null            // optional override, defaults to config
}
```

Returns `{job_id}`. Result: the constrained plan in the same shape as
`/api/advice/latest` **plus** a diff against the baseline: xPts over horizon
(both, delta), transfers changed, hits, captain, XI membership changes, and a
one-line verdict ("your version costs 2.8 expected points"). Infeasible constraint
sets (e.g. lock+ban same player, force_in over budget) return a structured
`error` with the violated constraint named — the UI shows it inline, no job crash.
Chip choices respect availability (`avail_by_gw`); an unavailable chip is rejected
with the reason.

### 3.3 League Race

`GET /api/league/race` → standings with live-season trajectory (rank/points by GW
per rival, from tracked history), gap chart data, win-probability panel, current
λ tilt and what it means in words.

### 3.4 Rival intel

`GET /api/league/rivals/{entry_id}` → that rival's current squad (from the league
picks fetch already used for EO), captain, chips used/remaining, team value, and
computed overlap vs the user: shared players, their differentials, your
differentials, plus live GW points when a GW is active. `GET /api/league/rivals`
lists all with summary rows.

### 3.5 Live

`GET /api/live` → wraps `live_gw`: active GW state, user's live points with
provisional bonus, league live table, per-player status (played/playing/left).
Page auto-polls every 60 s while a GW is active; returns `{active: false}`
otherwise and the page says so quietly.

### 3.6 Players

`GET /api/players?position=&team=&search=&sort=` → candidate-pool browser: EP next
GW and over horizon, price, ownership, EO in the mini-league, availability flag,
set-piece roles. `GET /api/players/{id}/explain` → EP explainability from the
components file: component breakdown per fixture, minutes model outputs,
calibration delta applied, odds influence (blend weight and both team-strength
estimates), next-3-fixtures mini-table. This endpoint backs the "why 6.8?" modal
reachable from every player name on every page.

### 3.7 Chip timing planner

`GET /api/chips/plan` → for each available chip, its evaluated gain in each GW of
the horizon window (extending `evaluate_chips` to score chip×GW combinations it
already enumerates via `avail_by_gw`), rendered as a chip×GW heat-strip with the
best week highlighted and a "play now vs best week" delta. This is display-level
guidance attacking the fire-on-unlock weakness recorded in v2 spec §9; changing
the optimizer's chip policy remains a model-backlog item, not v3 scope.

### 3.8 History

`GET /api/history` → past advice runs (GW, headline plan, expected vs — once the
GW resolves — actual points), price-change history charts, backtest summaries if
present on disk.

### 3.9 Runs & Health

`GET /api/health` → data freshness per source (history, live, odds, league),
model training timestamps and holdout metrics, launchd job last-run status
(parsed from logs), odds key present/absent, disk artifact inventory. Buttons for
`POST /api/advice/rerun` and a data-refresh job.

### 3.10 Fixture ticker

`GET /api/fixtures/ticker?weeks=8` → teams × next N GWs, each cell carrying
opponent, home/away, and a difficulty score in [0,1] from odds-implied win
probability when the odds key is configured, else Elo-implied. Rendered as the
sortable colored grid; also embedded (read-only) in the What-If Lab as planning
context.

## 4. Error handling and staleness

- **Staleness**: every page shows the generating run's timestamp; if advice GW <
  current GW (or deadline passed), a banner offers re-run. The server computes
  staleness; the client only displays it.
- **Solver**: job timeouts surface as `error` with a message; the UI keeps the
  last good result visible. The job runner never lets an exception escape a
  thread silently — all failures land in the job record.
- **No odds key**: ticker and explainability show Elo-based values with a small
  dismissable "add an odds key for market-implied numbers" notice — mirroring the
  CLI's silent degradation, but visible once.
- **FPL API down / offline**: all artifact-backed pages render from disk; live
  and rival pages show a retriable error state.
- **Domain errors** reuse `GafferError` and map to HTTP 422 with the message;
  unexpected exceptions map to 500 with a generic message and full server-side
  log.

## 5. Testing

- **Backend**: pytest + FastAPI `TestClient` against fixture artifacts (same
  fixture style as the existing 241-test suite). Every endpoint gets: happy path,
  missing-artifact path, and (where applicable) stale-data path. What-if gets a
  real small-pool MILP solve test (lock, ban, infeasible, chip-unavailable).
  Job runner gets unit tests for queueing, timeout, and error capture.
- **Frontend**: Vitest + React Testing Library for the core components — pitch
  view, plan diff table, constraints panel, explainability modal — mocking the
  API. No browser e2e suite in v3.
- **Packaging smoke test**: a pytest that asserts built static assets are
  importable via `importlib.resources` and that `create_app()` serves
  `index.html` (skipped with a clear message when `static/` hasn't been built,
  so the Python suite doesn't require node).

## 6. Out of scope for v3

- macOS menu-bar app (phase 2, own spec).
- Optimizer chip-timing policy, calibration hit-appetite, multi-season replay,
  odds training backfill, SIGMA from tracking (model backlog, v2 spec §9).
- Auth, remote access, multi-user anything (localhost-only by design).
- Websockets/streaming (polling suffices locally).
