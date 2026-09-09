# v17h — This Week's data fetched once; one job hook

**Cycle:** v17h, the eighth and last sub-cycle of the v17 deepening programme
(`docs/superpowers/plans/2026-09-07-v17-deepening-programme.md`).
**Card:** `#c7` of `docs/superpowers/research/2026-09-07-architecture-review.html`.
**Branch:** `v17h-page-data` off `main` at `668839c`.
**Date:** 2026-09-09.

---

## 0. The grilling, and its ruling

The card is the only one of the seven marked **Speculative**, and it says why:
*"per-card fetching may be a deliberate choice for cards that reload
independently after a job; the grilling should settle that first."* The
programme's prompt requires the answer here, before any interface is designed.

**It is deliberate, in three respects, and all three survive this cycle
unchanged.**

1. **Failure isolation.** Each card owning its request is what lets each card
   fail alone. `ThisWeek.tsx` says it twice in its own comments — the players
   and components fetches "load behind it and their failure never blanks the
   hub", and the leagues fetch is "its own effect, and a failure is silence,
   not an error state". The precedent is fresh and was paid for: v17e §2.6
   gave the settings rows their **own** error slot in `LadderCard` because a
   shared slot lost the settings failure whenever the ladder resolved second.
2. **Independent reload after the card's own job.** `LadderCard` reloads
   `/api/ladder` *and* `/api/settings` on `job.status === 'done'`; `BriefCard`
   reloads `/api/brief` on its own job and on both digest buttons;
   `ThisWeek.load` reloads its three on `JobButton onDone`. These are three
   different jobs rewriting three different artifacts, and no card refetches
   another card's.
3. **Lazy mount.** Radix leaves an unselected tab unmounted, so a card that
   fetches on mount *is* the fetch-deferral mechanism on Planning and Model.
   A hub-level loader would fetch six tabs' data to render one.

**What is not deliberate is the per-card *transport*** — that each card owns a
raw `apiGet` and therefore its own connection to the server. That is where the
duplication the card complains about actually lives, and it is the only thing
this cycle moves. Counted on This Week's first render, with a brief that has
prose (the ordinary Thursday state):

- `/api/jobs/current` **four times** — once per `JobButton`, two in the page
  header and two in the brief card.
- `/api/components/{gw}` for *every* player (`ThisWeek.tsx:75`) and
  `/api/components/{gw}?codes=…` for the fifteen the page names
  (`WhyPanel.tsx:159`): the same endpoint twice, and the hub's copy is the
  heavier one it does not need.
- `capLine` prop-drilled out of `LadderCard` through `ThisWeek` into
  `MovesCard`, with a comment at `ThisWeek.tsx:57` saying the prop exists "to
  avoid a 13th fetch". The prop is a workaround for the missing cache.
- Across hubs, `/api/advice/latest` refetched in full by This Week, Planning,
  Players and League, once per navigation, for ever.

So: **the cards keep calling for themselves; only the wire underneath them is
shared.** `usePageData` is a subscribed cache, not a loader, and every one of
the three deliberate properties above is preserved by construction rather than
by care.

**Rejected alternatives**, recorded so the next reader does not re-open them:
*hoisting the fetches into the hub* (reverses properties 1 and 3, and
multiplies the prop-drilling the card asks to delete); *caching only the four
cross-hub endpoints* (This Week's own first-render count moves 17 → 16, the
`capLine` prop stays, and gate part 2 would measure almost nothing).

---

## 1. Gate, stated before anything runs (CONVENTIONS §2, §7, §10)

Four parts. The orchestrator runs all four; an implementer runs none
(CONVENTIONS §7). **All four must hold.** Commands are run from
`frontend/` unless the path says otherwise.

### Part 1 — the hub renders from three endpoints

```
grep -n "path === '/api/\|path.startsWith('/api/" src/hubs/ThisWeek.test.tsx
```

**Verdict:** the file's shared fixture table names **at most three
endpoints** — `/api/advice/latest`, `/api/players`, `/api/components/…`.
Two cases seed one datum each of their own and are exempt by name: the cap
line seeds `/api/ladder`, the captaincy odds chip its `apiPost`. Every other
URL the tree asks for is **absent**, and the hub renders anyway, which is the
point: absence is the failure-isolation property of §0.1 under test. No case
is deleted to reach the number — the file's `it(` count does not fall.

### Part 2 — This Week's first render, counted

A new rail, `src/hubs/ThisWeek.fetches.test.tsx`, renders the hub with every
endpoint answered and asserts the **multiset of request paths**, not a total:
each URL exactly once. The control arm (CONVENTIONS §3) is captured **in git,
not in a worktree**: the rail is written and committed *first*, asserting the
counts as they stand on `main`, and the conversion commit flips the expected
multiset. One instrument, two commits, and `git show` on the first is the
control record.

```
npx vitest run src/hubs/ThisWeek.fetches.test.tsx
```

**Verdict:** on the branch every path appears exactly once and the total is
**13 GETs**; on `main` the same instrument reports **17 GETs** with
`/api/jobs/current` four times and `/api/components/5` twice under two URLs.
Both numbers are transcribed into §7 (CONVENTIONS §4). A branch run that
merely *totals* fewer requests without every path being unique fails the part:
the claim is "fetched once", not "fetched less".

This is the part that answers CONVENTIONS §10 — the lever is shown to have
been exercised by naming the two requests that disappeared, not by an empty
diff.

### Part 3 — one job hook

```
grep -rn useJobStream src ; echo "exit $?"
```

**Verdict:** prints nothing (`exit 1` from grep, meaning no match).
`useJobStream.ts` and `useJobStream.test.tsx` are deleted and their cases live
in `useJob.test.tsx`. This is deliberately stronger than the gate the
programme pre-registered, which greps `--include=*.tsx` and so could never
have matched the hook's own `.ts` file; the ruling and the reason are here.

### Part 4 — twelve screenshot pairs, against a control

```
# from the repo root, on main:   (cd frontend && npm run build) && frontend/scripts/shots.sh v17h-before
# from the repo root, on branch: (cd frontend && npm run build) && frontend/scripts/shots.sh v17h-after
```

Six hubs (`this-week`, `planning-whatif`, `planning-board`, `players`,
`league`, `settings`) × two themes, from the **same** `gaffer ui` process over
the same banked artifacts, minutes apart.

**Verdict:** the user approves all twelve pairs as visually identical.
Byte-identity is not the rule and is not expected — `FreshnessStrip` prints
relative times and the league panels read live data — so the comparison is the
user's eye on the pairs, which is what "approved" has meant in every surface
gate of this programme.

The programme pre-registered "identical to v17e's set", but v17e shot only
`this-week-lower` and `settings`; four of the six hubs have no baseline newer
than v14. A control set shot on `main` at the same hour is CONVENTIONS §3
applied to pixels and is the only version of "identical" that can be checked
for those four. Recorded here as a deviation from the programme's wording.

### Suites, alongside the gate

```
npx tsc --noEmit && npx vitest run          # from frontend/
.venv/bin/pytest -q                         # from the repo root
```

Both green. Python is unchanged by this cycle and is run to prove it. The
frontend baseline on `main` at `668839c` is **926 passed, 1 skipped, 91
files**; the branch adds cases and must not lose any.

---

## 2. `usePageData` — a subscribed cache

`frontend/src/api/pageData.ts`, new. One module-level `Map` keyed by URL. An
entry is an in-flight promise, a resolved body, or nothing at all.

```ts
export function usePageData<T>(path: string | null):
  { data: T | null; error: string | null; reload: () => void }

export function invalidate(path: string): void
export function seedPageData(bodies: Record<string, unknown>): void  // tests
export function resetPageData(): void                                // tests
```

**Rules, each with a reason.**

- **`path === null` is inert.** No request, `data` stays `null`. This is how
  `WhyPanel` waits for its codes and `ThisWeek` waits for a gameweek, without
  a card inventing a URL it does not yet mean.
- **One in-flight request per URL.** A second caller mounting while the first
  is in flight subscribes to the same promise. This is what collapses the four
  `/api/jobs/current` probes into one.
- **A resolved body is served until invalidated.** That is what makes the
  cache shared *across hubs* rather than merely within a render: This Week →
  Planning → back issues one `/api/advice/latest`, not three. The lifetime is
  bounded by a page reload, which clears the module.
- **Errors are never cached.** A failed request drops its entry, so a later
  mount retries. A cached error would turn one cold-start failure into a
  permanently dead card — the opposite of the isolation §0.1 protects.
- **`invalidate` refetches, it does not merely forget.** Every mounted
  subscriber of the URL is told to re-request. A card that has already painted
  must not keep a body the job it just ran has replaced.
- **Each caller keeps its own `error`.** The hook returns a per-call-site
  error string (through `errorText`), so the v17e §2.6 lesson holds: two cards
  reading two URLs cannot lose each other's failures.

The hook reads a cached body in its `useState` initialiser, so a remount with
a warm cache paints on the first render with no flash and no effect.

---

## 3. What converts

**This Week's whole tree**, which is the card's subject: `ThisWeek`,
`DecisionPanel`, `LadderCard`, `MovesCard`, `BriefCard`, `DigestCard`,
`WhyPanel`, `NewsPanel`, `ConfidenceLine`, and `JobButton`'s
`/api/jobs/current` probe. **Plus `/api/advice/latest`** in `Planning`,
`Players` and `League`, so the cross-hub claim of §2 is real and not a
promise.

**What does not convert, this cycle:** Model's tabs, Planning's sub-tabs
(`ChipsTab`, `DraftsTab`, `WhatIfTab`, `Timeline`, `PlannerBoard`,
`FixtureTicker`, `TickerTab`, `ConstraintsPanel`, `OverridesCard`,
`SensitivityCard`), `Live`, the league sub-panels (`RivalDetail`,
`WhatIfSim`), `kit/ExplainModal`, `kit/FreshnessStrip`, and the `Players` and
`League` reads other than the advice. They keep `apiGet`. Two exceptions
below in §5 are writes in those files that must invalidate a converted URL.

### Two merges fall out of the conversion

**The inverted data flow behind `capLine` dies.** Today the ladder payload
travels *up* out of `LadderCard` through an `onLoaded` callback into
`ThisWeek` state and back *down* into `MovesCard`. `ThisWeek` instead calls
`usePageData<LadderPayload>('/api/ladder')` itself and shares the request
`LadderCard` already makes; `LadderCardProps.onLoaded`, `ThisWeek`'s
`onLadder` callback and its `capLine` state are all deleted. `capText` moves
from `LadderCard.tsx` to `this-week/ladderText.ts` so neither card imports the
other.

`MovesCard` keeps its `capLine` **prop** and stays a pure presentational
component. Pushing the fetch down into it would trade one inverted flow for a
component that can no longer be rendered from a table of props, and this cycle
is about where the transport lives, not about how far down it can be pushed.
The rendered string is unchanged: the same `capText` over the same payload,
`null` when `rungs` is empty exactly as today.

**One components request.** `ThisWeek` stops asking for every player's
decomposition and asks for the fifteen it names, through a shared

```ts
export function componentsPath(gw: number, codes: number[]): string
```

in `this-week/squadRows.ts`, called by both `ThisWeek` and `WhyPanel` over the
same list in the same order (`[...advice.xi, ...advice.bench]`), so the two
URLs cannot drift into a cache miss. Strictly less data crosses the wire than
today, and the payload the hub reads is the same rows it read before.

---

## 4. `squadRows`, pure

`frontend/src/hubs/this-week/squadRows.ts`, new:

```ts
export function squadRows(advice, players, components): SquadRow[]
export function squadBreakdown(components): Record<number, SquadBreakdown>
export function componentsPath(gw, codes): string
```

The sixty lines currently inline in `ThisWeek`, moved with their comments and
given a table-driven test of their own — including the distinctions those
comments defend: `?? null` for `fieldEo` (the field-EO contract is "never 0
for unknown", and a `NaN` reaching a tint comparison is a silent false),
`?? NaN` for `ownership` and `leagueEo`, `?? null` for `teamShort`/`teamCode`
(a backend that read no snapshot gets a plain shirt, not an invented club),
and a band of `null` rather than width zero when there is no minutes model.
This is the card's "locality: row bugs tested in `squadRows`".

---

## 5. Invalidation, in a table

**Every reload that exists today maps 1:1 onto an invalidation of exactly the
URLs it already refetched. No reload behaviour changes.** A cache is, however,
the first thing in this app that can serve a stale panel after a write, so the
writes are new work and are enumerated. One unit test per row.

| Writer | Invalidates | New? |
|---|---|---|
| `ThisWeek` `JobButton onDone` (advise, advise-fast) | advice, players, components — the three `load` fetched | no |
| `LadderCard` job done | `/api/ladder`, `/api/settings` | no |
| `BriefCard` job done; digest `onDone` | `/api/brief` | no |
| `LadderCard` POST `/api/settings` | `/api/settings` | yes |
| `SettingsTab` POST `/api/settings` | `/api/settings` | yes |
| `League` POST `/api/settings` | `/api/settings`, `/api/league/leagues` | yes |
| `DecisionPanel` POST `/api/decisions/{gw}` | `/api/decisions/{gw}` | yes |
| `PinDialog` POST `/api/overrides`; `Players` DELETE `/api/overrides/{code}` | `/api/overrides` | yes |

`SettingsTab`, `League`, `PinDialog` and `Players` keep `apiGet` for their own
reads; they appear here because their *writes* would otherwise leave a
converted card stale. `ThisWeek`'s `POST /api/league/whatif` invalidates
nothing — it is a simulation, it writes no artifact, and invalidating on it
would refetch the page it was called from.

---

## 6. One `useJob`

`GET /api/jobs/{id}/stream` 404s unless the id belongs to the kind-keyed
runner (`src/gaffer/web/routers/jobs.py:137`), so "streams when a stream
exists" is decided by which argument the caller passes, not by a probe. **No
server change, in this cycle or for this card.**

```ts
useJob({ kind: JobKind })              // POST /api/jobs/{kind}, EventSource,
                                       // recovers via GET /api/jobs/current
useJob({ path: string, slot?: string })// POST {path}, polls /api/jobs/{id},
                                       // recovers via the remembered id
```

One status union, `idle | queued | running | done | error`: the stream's
`failed` folds into `error`, which is the word four of the five call sites
already read. `lines` is empty for polled jobs and `result` is `null` for
streamed ones, both documented on the returned type — the honest cost of one
interface over two transports, and cheaper than the alternative of a
discriminated return every caller must narrow. `JobLog`'s prop type follows
the union. One recovery probe each, as today, and `/api/jobs/current` goes
through `usePageData` so four buttons make one request.

`useJobStream.ts` and `useJobStream.test.tsx` are deleted; their cases —
reconnect, the `CLOSED`-only error rule, the 409 `running_kind` message — move
into `useJob.test.tsx` unchanged in substance.

---

## 7. Outcome

**Gate passed on its first full run, all four parts. Merged to `main` at
`339f5d1`, 2026-09-09.** One part passed at a number other than the one
pre-registered; the reason is §7.2 and it is a finding, not a rationalisation.

### Part 1 — the hub renders from three endpoints. PASS

`ThisWeek.test.tsx`'s shared fixture table is exactly `/api/advice/latest`,
`/api/players`, `/api/components/5?codes=1,2`. Every other URL the tree asks
for is absent and the hub renders anyway. **42 `it(` cases before, 42 after**,
and in the whole file exactly one `expect` line changed — `getByText('ladder
card')` (a stub) became `getByText('Transfer ladder')` (the real card), which
is a strengthening. Four cases seed one datum each of their own: the cap line
(`/api/ladder`), the focus-league caption and the manual-stance flag
(`/api/league/leagues`), and the deviation note (`/api/decisions/5`).

### Part 2 — This Week's first render, counted. PASS at 14, not 13

```
17 GETs  ->  14 GETs
```

Before, recorded in `git show 7ec0e0a` (the control arm, committed against
`main`'s behaviour before anything was converted):

| path | n |
|---|---|
| `/api/jobs/current` | **4** |
| `/api/components/5` | 1 |
| `/api/components/5?codes=1,2` | 1 |
| advice/latest, players, league/leagues, decisions/5, ladder, settings, brief, advice/diff, overrides, news/5, confidence | 1 each |

After, `frontend/src/hubs/ThisWeek.fetches.test.tsx` on the branch: the same
list with the bare `/api/components/5` **gone** and `/api/jobs/current` at
**2**. Every *artifact* endpoint is requested exactly once. The two requests
that disappeared are named rather than inferred (CONVENTIONS §10): the hub
was asking for every player's decomposition in order to read fifteen, and
three of the four liveness probes were duplicates of one question.

**Why 14 and not the pre-registered 13.** The first conversion put
`/api/jobs/current` through `usePageData` and hit 13 — and broke the probe.
A cached 204 arrives as `null`, and `null` is a *held* body, not an absent
one, so after an in-app navigation the probe made no request, `JobButton`
found no run, and it offered a solve that the single-flight runner can only
answer with a 409. That is precisely the bug the probe's own comment was
written to prevent, and it was confirmed executably against a control
worktree of the parent commit (2 probes and a reopened stream before, 1 probe
and an enabled button after).

The ruling: **liveness is not page data.** `usePageData`'s contract is "held
until invalidated", which is right for an artifact — the advice, the ladder
and the brief move only when a job rewrites them — and wrong for "is a run in
flight right now", which has no invalidation event this tab can be sure of:
nine `com.gaffer` launchd jobs start runs this tab never hears about, as can
the CLI. Invalidating on `start()` and on the stream's `end` would have kept
the number and papered over exactly the two transitions this tab happens to
know about. Instead the probe left the cache entirely (`b54695a`): `useJob.ts`
holds a module-level in-flight promise, cleared when it settles, so
simultaneous mounts join one request and any later mount asks again — today's
semantics minus the duplicate. This Week has two mount waves (the header's two
buttons, then `BriefCard`'s two digest buttons once `/api/brief` resolves),
hence two probes and a total of 14.

### Part 3 — one job hook. PASS

`grep -rn useJobStream frontend/src` prints nothing. `useJobStream.ts` and its
test are deleted; all eleven of its cases live in `useJob.test.tsx`, re-mocked
from `vi.mock('./client')` onto the fetch-stubbing idiom that file already
used.

### Part 4 — twelve screenshot pairs. PASS

`shots.sh v17h-before` on `main` and `v17h-after` on the branch, one
`gaffer ui` process, the same banked artifacts, minutes apart. **Ten of the
twelve pairs are byte-identical.** `this-week-dark` and `this-week-light`
differed by one string: the captain line's `+1pp title odds vs vice` chip,
which comes from a fire-and-forget `POST /api/league/whatif` with
`cached_only: true` and therefore renders only when the server's league-sim
cache is warm — and the control run is what warmed it. Re-shooting `main`
afterwards (`v17h-before2`) produced This Week shots **byte-identical to the
branch's**, which settles it: the difference is run order, not code. The
`capOdds` POST is untouched by this cycle. User approved all twelve.

This is v17b's lesson in a new costume — two runs of identical code minutes
apart differ — and the answer was the same: a same-code control, run second.

### Suites

| | before (`main` at `668839c`) | after (`339f5d1`) |
|---|---|---|
| frontend | 926 passed, 1 skipped, 91 files | **986 passed, 1 skipped, 94 files** |
| `tsc --noEmit` | clean | clean |
| Python | 4425 | **4425** (no Python changed) |

**A correction to the ledger, not a change.** The tracker records 4386 Python
tests at v17g. `pytest --collect-only -q` reports **4425 collected**, and
nothing in `[tool.pytest.ini_options]` deselects by default (the `golden`
marker runs unless you ask for `-m "not golden"`). Since v17h changed no
Python, v17g's true figure was also 4425 and the row under-records. The v17h
row states the measured number.

**Pins.** Routes 51, `JOB_KINDS` 12, `Config` fields 62 — none moved, none
touched. No schema change, so `schemas.json` and `types.generated.ts` did not
move and `npm run types` was not run.

### Two findings beyond the plan, both fixed

**The write sweep had a wrong row and a missing class.** §5's table put the
overrides DELETE in `Players.tsx`, where no such call exists — it is in
`planning/OverridesCard.tsx`, and `/api/overrides` is read by `WhyPanel`, so
the invalidation was needed but attributed to the wrong file. Separately,
`SettingsTab` writes `focus` and `stance` — both on the settings whitelist —
and `LeaguesOverview` derives This Week's league tile from exactly those two,
so it must clear `/api/league/leagues` as `League.tsx` does when it writes the
same fields.

**And the sweep's own definition was too narrow.** It was framed over
`apiPost`/`apiDelete`, which misses a second class: **a job that rewrites a
cached artifact from another hub**. `refresh-data` rewrites `live/players.parquet`
and `field-scrape` rewrites `FIELD_EO_PATH`; both feed `/api/players`, whose
body This Week now holds across navigations, and both buttons live on the
Model hub whose `onDone` reloads only its own tab. `refresh-data` also reaches
`/api/news/{gw}`, which joins players.parquet for names, clubs and the official
flag — which is why `invalidatePrefix` earns its place, the gameweek being
unknown to the Model hub. Traced and *excluded* on evidence: `snapshot` writes
the availability log, which nothing cached reads, and `news-shadow` has no
button in the app at all.

### Recorded exceptions to §5's "no reload behaviour changes"

1. `DigestCard`'s given-panel branch no longer refetches `/api/digest` on a
   digest job. The old code fetched a body it then never rendered (`panel`
   resolves to `given` in that branch), so the request was dead. Removed
   deliberately rather than preserved.
2. `ThisWeek`'s `reloadAdvice` invalidates the **pre-run** components URL. If
   a run changes the gameweek or the squad, that is one GET nothing reads, and
   the new key is a cold fetch on the path change — a wasted request, never a
   stale panel. The clean fix needs an effect that waits for the new advice to
   land; left, with the reason written at the call site.

### Residuals

- `WhyPanel` reads `/api/advice/diff` and `/api/overrides` behind the same
  `codes.length > 0` guard as its components read. Unreachable from its only
  call site, where `codes` is never empty.
- The source-scan half of the invalidation rail cannot see a call on the wrong
  branch or after an early return. That limit is stated in the rail's own
  docstring, and it is why the guarded `SettingsTab` case has two behavioural
  tests rather than a cleverer regex.
- `pageData.ts`'s subscriber-set copy is deliberately unpinned: the only test
  that would discriminate pins the wrong half of the invariant, and a test
  that passes either way is worse than none. The reasoning is in the module.

---

## 8. Scope, pins, protected files

**Out of scope.** Any server change. Any visual change — part 4 is the check.
Any change to what an endpoint returns. Converting the hubs listed as not
converting in §3. A general request library: `usePageData` answers exactly the
rules §2 states and nothing else — no retries, no refetch on focus, no TTL,
no mutation helpers.

**Pins.** None move: routes 51, `JOB_KINDS` 12, `Config` fields 62. No job
kind is added — `useJob({path})` posts to the anonymous `JobRegistry` exactly
as `LadderCard` and `BriefCard` do today. No `src/gaffer/web/schemas.py`
change, so `npm run types` is not run and `schemas.json` and
`types.generated.ts` do not move.

**Protected files.** None. `src/gaffer/advise.py`, `set_pieces.py`,
`optimize/**`, `web/jobs.py`, `web/routers/whatif.py` and every pinned test
file are untouched; this cycle changes `frontend/` only. `frontend/src/types.ts`
is hand-written, is not regenerated, and needs no edit: `JobStatus` is
declared in `api/useJob.ts`, and `types.ts` owns only `JobKind` and
`JOB_KIND_LABEL`, which do not move.

**Security.** The odds key lives only in the untracked `config.toml` and is
referred to by name (`[odds] api_key`). No subagent opens that file. The
ritual runs before the push.
