# v18e — the loader, finished

**Cycle:** v18e, the fifth sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18e;
design `specs/2026-09-12-v18-polish-design.md`, ruling 7; the review's §2,
first two bullets; `usePageData`'s contract in
`specs/2026-09-09-v17h-page-data-design.md` §2 and §5).
**Branch:** `v18e-loader` off `main` at `52f5a17`. **Date:** 2026-09-14.
**Plan:** five tasks below, the first the orchestrator's and committed
before any conversion.

## 1. Gate, stated before anything runs

Four parts, all four or no merge.

1. **Fetch counts per hub, before and after.** Five rails,
   `frontend/src/hubs/{Planning,Players,League,Live,Model}.fetches.test.tsx`
   beside the v17h one for This Week, each rendering its hub with every
   endpoint answered and asserting the **multiset of GET paths** (each URL,
   how many times). Written and committed first against `main`'s behaviour
   (task 1; committed at `8db1259`, after the kit commit `3e1ddb2` that
   changes no fetch), then flipped by the conversion. **Control multisets
   (`8db1259`):** Planning — Timeline `{advice/latest 1, plan/5 1,
   ticker?weeks=2 1}`, Board `{advice/latest 1, plan/5 1, prices/movers
   1}`, What-If `{advice/latest 1, ladder 1, settings 1, sensitivity 1,
   overrides 1, ticker?weeks=6 1, jobs/current 1}`, Chips `{advice/latest
   1, chips 1}`, Drafts `{advice/latest 1, drafts 1}`, Ticker
   `{advice/latest 1, health 1, ticker?weeks=8 1}`. Players — every tab
   `{advice/latest 1, players?… 1, overrides 1, watchlist 1}` plus: Compare
   `{components/5 1, fixtures/matrix?from=5&n=6 1}`, Matrix
   `{fixtures/matrix?from=1&n=6 1, fixtures/matrix?from=5&n=6 1}` (the
   matrix mounts before the gameweek is known and fetches twice), Watchlist
   `{watchlist +1}` (the hub's star column and the tab each read it).
   League `{advice/latest 1, league/leagues 1, league/race 1,
   league/rivals 1, league/sim 1}`. Live `{live 1}`. Model — Quality
   `{jobs/current 1, quality 1, model/calibration 1, pens 1, review 1,
   misses 1}`, Journal `{jobs/current 1, journal 1}`, Review `{jobs/current
   1, review 1}`, Season `{jobs/current 1, model/calibration 1, review 1}`,
   History `{jobs/current 1, history 1}`, Health `{jobs/current 1, health
   1}`, Settings `{jobs/current 1, settings 1}`; the three-tab walk
   `{jobs/current 1, quality 1, model/calibration 2, pens 1, review 3,
   misses 1}`.
   Verdict rule: on the branch no hub asks for more paths than on `main`,
   no path more often, and the Model hub's three-tab walk (Quality →
   Review → Season, in `Model.fetches.test.tsx`) asks `/api/review`
   **once, not three times**. Both multisets are transcribed into §3.
2. **Twelve screenshot pairs byte-identical.** `frontend/scripts/shots.sh
   v18e-before` on `main` (served from a `main` worktree with
   `PYTHONPATH=<worktree>/src` and that worktree's own `npm run build`, the
   v18c method) and `v18e-after` on the branch, six hubs × two themes; a
   pair that differs is re-shot on the control second before it is read as
   real (programme §2.3). Approved by the orchestrator in the user's
   absence, images kept under `.superpowers/shots/`.
3. **A 500 is an error and a 404 is the named empty state,** for every
   converted component that had synthesised an empty body: one
   table-driven test, `frontend/src/kit/Loaded.status.test.tsx`, rendering
   each row's component with its URL answering `ApiError(500)` and asserting
   a `Callout` with `data-tone="error"` carrying `errorText`; then with
   `ApiError(404)` and asserting the row's named empty text. Rows: the nine
   in §2.3 at minimum.
4. **The raw reads that remain are the liveness reads, by name.**
   `grep -rn "apiGet(" frontend/src/hubs frontend/src/kit` (the call, not
   the import) lists exactly: `hubs/Live.tsx` (the poll). Writes
   (`apiPost`, `apiDelete`) are not reads and stay; `api/useJob.ts` is not
   under either directory. Pasted into §3.

Alongside the gate: `cd frontend && npx tsc --noEmit && npx vitest run`
green (read vitest's `Errors  N error` line as a failure), the Python suite
untouched (no backend change in this cycle; routes 51), `kit/tokens.test.ts`
green (no new colour, radius, shadow or mono face).

## 2. What the cycle must know

### 2.1 `usePageData` gains `status`

`PageData<T>` becomes `{ data, error, status, reload }` with `status:
number | null` — the `ApiError.status` of the failure that set `error`,
`null` when there is none or the failure was not an `ApiError` (a network
throw). Nothing else in the hook changes: the cache, the subscriber set,
the ask counter and the `null`-path contract are v17h's and its tests stay
as they are, plus one for `status`.

### 2.2 `kit/Loaded.tsx`

One component over a `PageData<T>`:

```
<Loaded page={page} empty={<EmptyState … />} loading={…}>
  {(data) => …}
</Loaded>
```

Render order: `error` set and `status !== 404` → `<Callout tone="error">`
with the error sentence (and `page.reload` offered as a "Retry" `Button`);
`error` set and `status === 404` → the `empty` slot (a 404 is "the artifact
is not there yet", the documented cold-clone state); `data === null` and no
error → the `loading` slot (default: nothing, so a card keeps its height
rule; a hub may pass a `Skeleton`-free placeholder line); otherwise the
render prop with `data`. An optional `isEmpty?: (data: T) => boolean` lets
a body that is present but empty (`rows: []`) route to the `empty` slot,
because several artifacts answer 200 with an empty list rather than 404
(`/api/journal`, `/api/review`, `/api/drafts`) — the component decides,
the slot is one. Render props rather than children-as-element, so the
body is typed and never rendered with `null`.

**Corrected during the cycle (`47dd7fe`):** the cold clone does not answer
404. `web/app.py` maps every `GafferError` — "nothing on disk yet, run
`gaffer advise` first" — to **422**; only the plan, chips and components
routes answer 404 by design. So `Loaded`'s empty branch is `status === 404
|| status === 422`, and `empty` may be a function of the server's sentence
for the states that print it. Gate part 3's 404 rows are read as "404 or
422, whichever the route answers". Task 3 found this and, correctly, left
the page-level branches on `error` alone rather than paint the cold clone
red; task 3b converts them under the corrected rule.

### 2.3 What converts, and the nine synthesised empties (ruling 7)

Every `apiGet` in `hubs/` and `kit/` converts to `usePageData` except the
liveness read: `Live.tsx:58` (`/api/live`, polled every `POLL_MS`; a cache
that held it would show the last poll for ever — v17h's trap). The 44 read
sites (by file; the line numbers are `52f5a17`'s):

- **Planning:** `PlannerBoard.tsx:95,103`, `Timeline.tsx:40,60` (the second
  depends on the first: `usePageData(data ? tickerPath(data.weeks.length) :
  null)`), `ChipsTab.tsx:158,364,366`, `DraftsTab.tsx:27`,
  `OverridesCard.tsx:10`, `ConstraintsPanel.tsx:33` (search URL per
  keystroke — converts; the cache is keyed by URL and the hook's counter is
  exactly the stale-response guard the review asked for),
  `SensitivityCard.tsx:70`, `TickerTab.tsx:14`, `FixtureTicker.tsx:19`.
- **Players:** `Players.tsx:62,68,119` (the comment at `:34` that keeps
  `apiGet` for the per-keystroke URL goes with the read, for the reason
  above), `ComparePanel.tsx:115,117`, `WatchlistTab.tsx:147`,
  `FixtureMatrix.tsx:16`.
- **League:** `League.tsx:108,114,117,123` (its comment at `:102-104`
  goes), `RivalDetail.tsx:63`.
- **Model:** `QualityTab.tsx:202,763,860,972,1005`, `HistoryTab.tsx:31`,
  `ReviewTab.tsx:225`, `SeasonTab.tsx:59,131`, `HealthTab.tsx:19`,
  `JournalTab.tsx:53`, `SettingsTab.tsx:137`. The three `/api/review`
  readers stay at their tabs (lazy mount); the cache makes the walk one
  request, which is what part 1 measures.
- **Kit:** `FreshnessStrip.tsx:38`, `ExplainModal.tsx:31`.

The nine places that today render a failure as a healthy page, each of
which becomes `Loaded` with its named `empty` and the default error
callout: `JournalTab.tsx:54`, `ReviewTab.tsx:226`, `SeasonTab.tsx:132`,
`FixtureMatrix.tsx:18`, `FreshnessStrip.tsx:40` (empty: no strip, as
today; error: a one-line callout in the strip's place), `QualityTab.tsx:862`
and `:972`, `DraftsTab.tsx:27`, and `Live.tsx:96-105`, whose "No live data
yet — gaffer refresh-data" is right for a 404 and wrong for a 500
mid-gameweek: it keeps its raw poll and splits its one `error` branch on
the status it now records (a `useState<number | null>` beside `error`,
set from `ApiError`).

`errorText(e)` at every catch that survives (the 17 `.message` sites, all
on writes and job starts).

### 2.4 `kit/ErrorBoundary.tsx`

A class component (React has no hook for it) around `<Routes>` in
`App.tsx`, rendering `<Callout tone="error">` with the error's message and
a "Reload page" `Button` (`location.reload()`); `componentDidCatch` logs
to `console.error`. Keyed on the route path so navigating away resets it.
The comment at `ThisWeek.tsx:126-129` that describes the white screen it
would catch is rewritten to say the boundary exists. Test: a route whose
element throws renders the callout and the nav stays mounted.

### 2.5 Invalidation, the rows that are new

v17h §5's rule holds: every write invalidates exactly the URLs it changes,
and the table test (`api/invalidation.test.tsx`) gains one row per newly
cached URL with a writer.

| Writer | Invalidates | New? |
|---|---|---|
| `Players` watchlist POST/DELETE; `WatchlistTab` POST/DELETE | `/api/watchlist` | yes |
| `OverridesCard` DELETE `/api/overrides/{code}` | `/api/overrides` | yes |
| `DraftsTab` POST/DELETE `/api/drafts` | `/api/drafts` | yes (replaces its `load()`) |
| `League` POST `/api/settings` | `/api/settings`, `/api/league/leagues`, `invalidatePrefix('/api/league/')` | extended |
| `JobButton` `refresh-data` done | `/api/health`, `/api/meta/freshness`, `invalidatePrefix('/api/fixtures/')` | yes |
| `JobButton` `review` done (Model hub's `reviewNonce`) | `/api/review`, `/api/journal` | yes (replaces the nonce remount) |
| `JobButton` `sensitivity` done | `/api/sensitivity` | yes |
| `JobButton` `track-pens` done | `/api/pens` | yes |
| `JobButton` `snapshot` done | `/api/health` | yes |
| `ChipsTab`/`WhatIfTab` POST `/api/whatif` | nothing (a job, read through `useJob`) | — |

The Model hub's `reviewNonce`/`healthNonce` remount trick becomes an
invalidation: the same effect, through the one mechanism.

### 2.6 What does not change

No backend file. No new colour, token, radius or shadow; `Loaded`'s error
is the existing `Callout`, its empty the existing `EmptyState`. No reload
behaviour beyond the table. `useJob` untouched. The six hubs render the
same pixels (part 2) — the cycle changes how they fail, not how they look.

## 3. Outcome

_(filled at the gate)_
