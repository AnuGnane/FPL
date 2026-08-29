# gaffer v7-ui — command centre redesign

Date: 2026-08-29 · Status: approved for planning · Branch: `feat/gaffer-v7-ui`

The web UI becomes the primary daily interface: a full visual redesign onto a
locked design language, thirteen flat pages consolidated into six hubs, a
backend job runner so every everyday CLI action runs from the browser, four
new capabilities (plan timeline, player comparison, fixture matrix, decision
journal), and fully responsive layouts reachable from a phone on the LAN.

Companion cycle: **v7-model** follows separately, grounded in the fresh
`gaffer evaluate` run (2026-08-29: haulers RMSE 5.145 ≈ OpenFPL parity;
zeros 1.063 remains the largest gap). Nothing in this cycle touches model
code, `advise.py` logic, or the optimizer.

## 1. Goals and non-goals

Goals:

- G1: A user never *needs* the terminal in a normal week — advise, review,
  what-if, chip decisions, live tracking, and data refresh all happen in the
  browser.
- G2: Six hubs replace the 13 flat pages; related workflows share a screen.
- G3: A single design language (locked via mockup 2026-08-29) applied
  everywhere through a shared component kit — no per-page ad-hoc styling.
- G4: Every hub fully usable from a phone (responsive-equal, not
  desktop-crippled), served over the LAN on request.
- G5: Existing rails preserved: cold-clone-safe endpoints, explicit empty
  states, protected source-text suites untouched.

Non-goals (rejected for this cycle):

- Model, solver, or advise-logic changes of any kind.
- Authentication / remote (non-LAN) serving.
- Native mobile app or PWA install flow.
- New CLI surfaces for backtest/calibrators in the UI beyond the four listed
  jobs (they remain developer CLI operations).

## 2. Design language (locked)

Approved via the brainstorm hybrid mockup (B density + C cleanliness, dark):

- Base `#101216`; card `#16181d`; border `#23262d`; row divider `#1e2127`.
- Text: primary `#f2f3f5`, secondary `#c8cbd2`, muted `#9ca3af`,
  faint `#6b7280`.
- Meaning colours only — never branding/glow: sage `#86b388` positive,
  rust `#e0876f` negative/risk, blue `#7da7c9` informational. No neon, no
  gradients.
- Type: system sans (`-apple-system, 'Segoe UI', sans-serif`) for UI text;
  `'SF Mono', Menlo, monospace` for **all** numerals in data contexts.
- Shape: 10px card radius, 1px borders, no drop shadows heavier than subtle.
- Cards over chrome: content sits in bordered cards on the dark base;
  labels are 9px letter-spaced uppercase muted.
- Dark-only this cycle (a light theme is future editorial work, not scope).

These become Tailwind theme tokens in `frontend/tailwind.config`
(or `@theme` in CSS for Tailwind v4) — the single source of truth.
`frontend/src/styles/tokens.css` is retired into it.

## 3. Frontend foundation

Stack: keep Vite + React 18 + react-router + vitest. Add:

- **Tailwind CSS v4** — utility styling + the responsive system.
- **Radix UI primitives** — tabs, dialog, tooltip, dropdown-menu (unstyled,
  styled by us with the tokens).
- **Recharts** — line/bar/area charts. The hand-rolled SVG `LineChart` is
  replaced.

### Component kit — `frontend/src/kit/`

Built and tested first; hubs may only compose kit components (plus
hub-specific composition components). Each ships with a vitest file.

- `PageHeader` — title, context line (deadline, staleness), action slot.
- `Card` — the bordered container; optional header row.
- `Stat` — label / big value (mono) / delta line (sage/rust).
- `DataTable` — column defs, client sorting, mono numeral cells, sticky
  header, optional row-expand renderer, responsive collapse mode (§8).
- `Sparkline` — inline 4–8 point trend, sage/rust by direction.
- `ThresholdBar` — value vs threshold (chip gain vs θ), fill colour by state.
- `Badge` — news/pens/captain/chip chips; variants map to meaning colours.
- `PitchView` — restyled port of the existing component.
- `JobButton` + `JobLog` — start a job (§5), disable while running, stream
  progress lines into a scrollback panel, surface failure tail.
- `EmptyState` — icon, explanation, the exact command/button that populates
  this view.

## 4. Information architecture — six hubs

Old pages are deleted as each replacement hub lands (tests migrate with
them). Sidebar (desktop) / bottom tab bar (mobile) lists exactly:

1. **This Week** (`/`) — the approved mockup realised: stat row (expected
   XI, captain + sim% + EO, next chip gain vs θ, league gap + stance λ);
   squad DataTable (xPts, xMin, EO%, sim%, news badge, last-4 sparkline;
   row-expand → full EP component breakdown incl. pen annotation); recommended
   moves with sim%; why-panel run diff; news panel; **Run advise** JobButton.
   Absorbs: ThisWeek, WhyPanel/NewsPanel placements.
2. **Planning** (`/planning`) — Radix tabs: *Timeline* (§6.1), *What-If*
   (current lab restyled), *Chips* (workbench: threshold bars, wildcard diff,
   What-If handoff), *Ticker* (price moves). Absorbs: WhatIf, ChipWorkbench,
   Ticker.
3. **Players** (`/players`) — explorer DataTable over the full player pool
   (column picker, position/team/price filters), *Compare* mode (§6.2),
   *Fixture matrix* tab (§6.3). Absorbs: Players, FixtureTicker component.
4. **League** (`/league`) — race chart (Recharts), rivals table, rival
   detail (route `/league/rival/:id`), EO-vs-you comparison. Absorbs:
   LeagueRace, Rivals, RivalDetail.
5. **Live** (`/live`) — in-GW tracker with auto-poll toggle (existing
   polling endpoint), bonus projection, live rank delta, rivals' live scores
   on the same screen. Absorbs: Live.
6. **Model** (`/model`) — tabs: *Quality* (metrics + reliability charts +
   news-shadow section), *Journal* (§6.4), *History*, *Health*; **Evaluate**
   and **Refresh data** JobButtons. Absorbs: Quality, History, Health.

## 5. Backend job runner

New `src/gaffer/web/jobs.py` + `src/gaffer/web/routers/jobs.py`.

- Registry of allowed kinds: `advise`, `evaluate`, `refresh-data`,
  `news-shadow`. Each kind maps to the **same entry point the CLI calls** —
  the runner wraps, never re-implements. Kind-specific options come from a
  validated Pydantic body (e.g. advise: none needed v1).
- `POST /api/jobs/{kind}` → `{job_id}` (409 `{running_kind, job_id}` if any
  job is running — single-flight globally).
- `GET /api/jobs/{id}` → status: `queued|running|done|failed`, start/end
  times, exit summary.
- `GET /api/jobs/{id}/stream` → SSE; each stdout/stderr line of the wrapped
  run is an event; terminal event carries final status. Client reconnect
  replays from a ring buffer (last 500 lines held in memory).
- `GET /api/jobs/current` → the running job or 204 (lets any page show the
  global "advise running…" indicator and lets a second browser tab attach).
- Execution: `anyio.to_thread` / background thread in-process, stdout
  captured line-by-line via a pipe-like writer. Artifacts land exactly where
  the CLI writes them; pages re-fetch on the job's `done` event.
- Failure surfaces the last 20 lines in `JobLog` + a rust toast. Job state
  is in-memory only (a server restart forgets history; artifacts persist).

## 6. New capabilities

### 6.1 Plan timeline

`GET /api/plan/{gw}` exposes the already-solved horizon from the advice
artifact: per horizon GW — transfers in/out (with prices), hit cost, chip,
captain/vice, expected XI points. UI: one column per GW, moves as in/out
rows (sage/rust), hits as explicit red cost chips, chip as a Badge. Reads
the existing artifact; **no solver changes**. Empty state if no advice run.

### 6.2 Player comparison

Frontend-only over existing endpoints (`/api/components/{gw}`, players
data): select 2–4 players from the explorer → side-by-side panel: EP
component stacked bars (Recharts), next-6 fixture strip (difficulty-coloured
via §6.3 data), form, EO, price, ownership trend if available.

### 6.3 Fixture matrix

`GET /api/fixtures/matrix?from={gw}&n={6}` — for each team × GW: opponent,
home/away, and difficulty from the trained Dixon-Coles team model as
**separate attack-facing and defence-facing scores** (opponent defence
strength for attackers, opponent attack strength for CS), normalised to
[0,1] for colouring. Falls back 200-empty if the team model artifact is
missing. UI: the classic grid, toggle attack/defence view, sage↔rust scale.

### 6.4 Decision journal

Computed join, no manual entry:

- Source A: advice history (`reports/advice_history/`, already written per
  run; the last artifact before each deadline is that GW's "model said").
- Source B: actual picks/transfers from the FPL entry API after each GW.
- Scoring: realized points of the model's recommended XI/captain vs the
  actual XI/captain, per GW and cumulative; transfer deltas listed.
- `GET /api/journal` → per-GW rows + cumulative model-vs-you series; cached
  to `reports/journal.json` by a small builder invoked on request when
  stale (post-GW data changes at most weekly). Empty state until a GW with
  both an advice artifact and a completed GW exists (GW3+).

## 7. LAN / phone access

- `gaffer ui --lan` binds `0.0.0.0` and prints the LAN URL + a QR code
  (`qrcode` pure-python dep, terminal render). Default remains loopback.
- Help text states plainly: no auth — trusted home network only.

## 8. Responsive behaviour

- Breakpoints: Tailwind defaults; `md` is the desktop/mobile line.
- Stat rows wrap 4-up → 2-up; tab bars become swipeable Radix tabs;
  sidebar → fixed bottom tab bar with the six hub icons.
- `DataTable` collapse mode below `md`: each row renders as a card showing
  the 3 columns marked `primary` in the column def; tap expands the rest.
  Sorting moves into a dropdown.
- PitchView scales to viewport width; charts use Recharts responsive
  containers.
- Every hub must pass the phone walkthrough in §10's checklist — this is
  acceptance, not garnish.

## 9. Error handling & rails (unchanged law)

- Every endpoint (including all new ones) is cold-clone safe: 200-empty or
  404-friendly, never 500 on missing artifacts.
- Every hub renders `EmptyState` naming the button/command that populates
  it; no page crashes on partial data (NaN-safe formatters in the kit).
- Job runner: single-flight 409; atomic artifact writes (same paths as
  CLI); SSE reconnect; failures visible, never silent.
- Protected source-text suites (`test_advise.py`, `test_odds.py`, v6
  pins) untouched — this cycle has no reason to edit those files.
- Frontend build output stays gitignored; `npm test -- --run`, `npx tsc -b`,
  `npm run build` all clean at every task boundary.

## 10. Testing & completion

- Kit: one vitest file per component (rendering, sorting, collapse mode,
  JobButton stream states via mocked EventSource).
- Hubs: per-hub tests written as the hub lands; the old page's tests are
  deleted only in the same commit their replacement's tests pass.
- Backend: pytest for the jobs router (fake registered job: success,
  failure, 409 single-flight, SSE line ordering, reconnect replay), plan/
  matrix/journal endpoints (golden artifacts + cold-clone).
- No measurement gate (UI cycle). Completion = smoke checklist, run and
  recorded in this spec's §12:
  1. Browser-only daily workflow: refresh data → run advise → read plan →
     what-if a variant → chip check → live view. Zero terminal.
  2. Phone walkthrough: all six hubs on a phone over `--lan`.
  3. Cold-clone boot: fresh clone, no artifacts, every hub shows empty
     states, no console errors.
- Final adversarial review (Opus) + fix rounds as always, then an editorial
  polish pass with the user before merge.

## 11. Execution order

Foundation first, then hubs shippable one at a time:

1. Tailwind/Radix/Recharts install + tokens; kit components + tests.
2. Jobs backend + JobButton/JobLog.
3. Hub: This Week (flagship, validates the language on real data).
4. Hub: Planning (+ plan endpoint/timeline).
5. Hubs: Players (+ matrix endpoint, compare) and League.
6. Hubs: Live and Model (+ journal endpoint); delete last old pages,
   sidebar/tab-bar final.
7. Responsive pass hardening + LAN/QR + smoke checklist + review.

## 12. Outcome

Recorded 2026-08-29, after Group 7 (Tasks 40-43) on `feat/gaffer-v7-ui`.

**Gates.** Backend `.venv/bin/python -m pytest -q`: green. Frontend
`npm test -- --run`: 46 files / 204 tests green; `npx tsc -b` clean;
`npm run build` succeeds. `git diff --name-only main...HEAD` touches none of
`src/gaffer/advise.py`, `src/gaffer/optimize/`, `src/gaffer/models/`,
`tests/test_advise.py`, `tests/test_odds.py`.

**Smoke 1 — the browser-only week.** Verified at the API level against a real
`uvicorn` process on the working tree's own artifacts: every endpoint the six
hubs read answered 200 — `/api/advice/latest`, `/api/advice/diff`,
`/api/plan/{gw}`, `/api/chips`, `/api/chips/plan`, `/api/players`,
`/api/components/{gw}`, `/api/fixtures/matrix`, `/api/fixtures/ticker`,
`/api/journal`, `/api/live`, `/api/quality`, `/api/history`, `/api/health`,
`/api/league/race`, `/api/league/rivals`, `/api/news/{gw}` — with
`/api/jobs/current` 204 on an idle server, an unknown kind 404, and an unknown
job id 404 on both the status and the stream route. The four job kinds were
**not** started against the live tree: each one writes real artifacts (and
`advise` takes ~30 minutes), so their start → SSE → done → replay behaviour
stands on `tests/test_web_jobs_api.py` instead. The click-through in an actual
browser is the operator's, and is not recorded as passed here.

**Smoke 2 — the phone.** `gaffer ui --lan --no-open-browser` printed the
loopback URL, `On your network: http://10.3.21.156:8927`, a half-block QR of
that URL, and the "no auth — trusted home network only" line; uvicorn reported
`http://0.0.0.0:8927`, so the bind is right. Collapse-mode preconditions were
checked statically rather than by eye: all five `DataTable` call sites
(Players, League, Live, `this-week/SquadTable`, `model/JournalTab`) declare
exactly three `primary` columns, which is what card mode renders, and
`AppShell` renders `data-mode="tabbar"` with `pb-16` clearance under
`useIsMobile`. Scanning the QR from a handset and reading all six hubs on
glass is the operator's, and is not recorded as passed here.

**Smoke 3 — the cold clone.** Run as a `uvicorn` boot in an empty working
directory (no `reports/`, `data/`, `models/`, no `config.toml`) plus a jsdom
sweep of all six hubs against a rejecting client
(`frontend/src/hubs/coldclone.test.tsx`). Two deviations found and fixed:

1. `/api/live`, `/api/league/race` and `/api/league/rivals` returned **500**.
   `load_config` raised `FileNotFoundError` when `config.toml` was absent, and
   a clone never has one — it is gitignored because it carries an odds API
   key. `load_config` now raises `GafferError` naming `config.example.toml`,
   so those routes answer 422 with a sentence. Pinned by
   `tests/test_v7_cold_clone.py::test_a_missing_config_is_a_message_not_a_500`.
2. The Live hub rendered a bare red error line with no header on that path,
   against §9. It now renders its `PageHeader` plus an `EmptyState` naming
   `gaffer refresh-data`, and its loading branch keeps the header too (as
   League's now does).

After both fixes: no 5xx and no traceback on any hub endpoint in an empty
tree, and all six hubs render an `EmptyState` naming their action.
