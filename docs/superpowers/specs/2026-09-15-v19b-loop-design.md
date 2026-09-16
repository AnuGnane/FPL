# v19b — the loop closed (design)

**Cycle:** v19b, the second sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19b, rulings 3, 4 and 9;
plan `plans/2026-09-15-v19-programme.md` §3 v19b).
**Branch:** `v19b-loop` off `main` at v19a's merge.
**Date:** 2026-09-15. **Status:** drafted; starts after v19a merges.

---

## 1. What this changes, and what it does not

The Friday loop is pin, re-run, apply. Today the pin lives on Players,
the re-run on This Week, and the two do not speak: nothing on This Week
says a pin is waiting for a solve. The web re-run does not bank a price
reading first, so a browser solve on a Friday sees Thursday's price
table and an untimed sale, which the Thursday plist never does. The
empty state on a cold This Week names the job in a code box and then
draws a second button for it. A phone on a bare LAN URL gets a 403
sentence and no way to type the token. The Players explorer fires one
fetch with a null path before the gameweek is known, and the fixture
ticker on a cold clone shows a raw error callout.

No served number changes. One input's timing changes: the web and CLI
advise bank a same-day price reading before the solve, as the plist has
since v12 (ruling 4). The golden gate stubs the step; the sub-cycle's
gate carries one real before/after board diff.

**Not taken, recorded.** The chip pair's Try-it card keeps no What-If arm.
`WhatIfRequest.chip` (`web/schemas.py:114`) is one chip, and a pair is
two chips across two gameweeks, so the arm needs a second field through
`web/routers/whatif.py` and the solver's request, which is orchestrator-
only and protected. The research's "one prefill hand-off" was wrong; the
card's sentence ("a chip pair has no What-If arm") stays true. It goes
back to the ROADMAP's candidate 7 with this reason.

## 2. The changes

### 2.1 `weekly_run` banks prices first (backend, orchestrator)

`pipeline.py:56-80`: before `run_advise`, when `bank_prices` (a new
keyword, default `True`) is on, call `price_log.bank_prices(...)` the way
`cli.prices()` (`cli.py:313`) does, logging its one line; a failure there
is a note, not a failed run, like the brief (the price table is an
input the solve can do without; the plist chained it with `;` for the
same reason). The three callers (CLI `advise`, the `advise` and
`advise-fast` job bodies in `web/job_kinds.py:66-77`, the plist) inherit
it. `tests/test_pipeline.py` (orchestrator-only) gains: the step runs
before advise and logs its line; `bank_prices=False` skips it; a raising
bank is a note. The golden harness passes `bank_prices=False`.
`scripts/com.gaffer.advise.plist`'s command drops its `prices;` prefix
only if it has one (read it; if the plist runs `gaffer prices` first, the
pipeline's step makes it a no-op the same day, so leave the plist alone
and say so).

### 2.2 Pins live on the moves card (frontend)

`this-week/MovesCard.tsx` gains a line under the cap line: "2 pins live
· re-run to apply" when `/api/overrides` (already fetched by This Week or
by Players; check `ThisWeek.tsx`'s reads and reuse the cached
`usePageData` entry rather than adding a fetch — if This Week does not
read it today, the read is a new fetch and the This Week fetch rail
changes by exactly one, declared here) has rows and `active`; "pins are
stored but not applied" when rows exist and `active` is false; nothing
when there are no rows. The line's re-run is the existing `JobButton
kind="advise"` in the header; the text says so, it does not add a
button.

### 2.3 Pin from a news line (frontend)

`this-week/NewsPanel.tsx:56-75`: each row gains the same pin affordance
Players' explorer has (`players/PinDialog.tsx`, opened with the row's
`code` and `name`), rendered as the ☆ Players uses. `PinDialog` moves to
`kit/` if it is imported from two hubs, keeping its tests.

### 2.4 The empty state is the action (frontend)

`hubs/ThisWeek.tsx:145-158`: `EmptyState` takes `onAction` that starts the
advise job through the same hook `JobButton` uses (read `kit/JobButton.tsx`
for `useJob` and pass its `start`), and the separate `JobButton` below it
goes. The header's two buttons stay.

### 2.5 A token field on 403 (frontend)

`api/client.ts:34-47` throws `ApiError(403, ...)`. `kit/Loaded.tsx` or the
mutation path: where a write's 403 is rendered today (grep `403` and
`errorText` in `api/` and `kit/`), render beneath the sentence a
one-line form "paste the token from the terminal" that writes
`TOKEN_KEY` to storage (the same key `readToken` reads) and retries the
write. Reads are open, so nothing else changes.

### 2.6 The two residuals (frontend)

`hubs/planning/FixtureTicker.tsx:31-40`: a 404 or 422 renders an
`EmptyState` ("No fixtures yet · Refresh data") instead of the error
callout; a 500 keeps the callout (v18e ruling 7). `hubs/Players.tsx:129`
and `players/FixtureMatrix.tsx:12`: the fetch fired with a null path
before the gameweek is known (the v18e residual) is removed by passing
`null` to `usePageData` until the gameweek is known; the Players fetch
rail changes by exactly that one fetch, declared.

## 3. Gate, written before anything runs

1. Inner loop green; ruff clean.
2. The golden gate → 58 passed, 0 skipped (with `bank_prices=False`
   in the harness; the recorded inputs are what the board reads).
3. One real run: `uv run gaffer advise --no-train` (or the closest flag;
   read `cli.py`) on the branch after a manual `gaffer prices`, diffed
   against the served plan from `main`'s run the same evening; the diff
   pasted in §4 with the price line the trace shows.
4. `npm run check` green; the This Week and Players fetch rails change by
   the declared fetches only; every other rail unchanged.
5. Screenshot pairs `v19b-before`/`-after` at 1400, both themes, same
   time: **This Week and Planning** named (the pins line, the empty
   state, the ticker's empty state); Players, League and Model
   byte-identical.
6. New rails mutation-tested: the pins line (rows with `active` false),
   the price step's order, the ticker's 500 path.

## 4. Outcome

Filled at the gate.
