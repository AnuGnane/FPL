# v19e — compare and act (design)

**Cycle:** v19e, the fifth sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19e, ruling 2; plan
`plans/2026-09-15-v19-programme.md` §3 v19e; research
`research/2026-09-15-v19-research-frontend.md` §2.1, §2.2, §2.8).
**Branch:** `v19e-compare` off `main` at v19d's merge.
**Date:** 2026-09-16. **Status:** drafted; starts after v19d merges.

---

## 1. What this changes, and what it does not

Two things a reader wants and cannot do. Nothing compares this week's
served plan with last week's: the History tab lists past runs
(`model/HistoryTab.tsx:48`) and `GET /api/advice/diff` compares the two
newest runs of *one* gameweek for the "since last run" strip
(`web/routers/advice.py:180`, `WhyPanel`). And nothing lets the reader
act on a squad player they are looking at: the What-If lab is reached
from the board's Try-it buttons or by typing names into
`planning/ConstraintsPanel.tsx`.

No served number changes. **Ruling 2, amended:** the programme design
moved the route pin 51 → 52 for a new `GET /api/advice/diff`. The path
exists; it gains two optional query parameters (`a`, `b`) for a
week-against-week comparison and keeps its one-parameter behaviour
unchanged, so the pin stays 51 and `tests/test_v11_degradation.py` is
not touched in this sub-cycle. The 52 → 53 bump for v19f stands as
51 → 52.

## 2. The changes

### 2.1 `GET /api/advice/diff?a=4&b=5` (backend)

`web/routers/advice.py:180`: when both `a` and `b` are given, the diff
is between the newest served plan of gameweek `a` and the newest of
gameweek `b` (`advice_history_files(gw)[-1]` each; the served advice
file when history is empty), through the same comparison the
same-gameweek path uses, with `AdviceDiff.gw = b` and two new fields
`gw_from: int | None` and `gw_to: int | None` set only on this path.
Unavailable (a missing file, an unreadable one) is `available=False`,
never an error, as today. `ep_movers` is computed for `b`. With `gw`
alone, or nothing, behaviour is unchanged byte for byte; the WhyPanel
strip's tests do not change. Tests in `tests/test_web_advice.py` (or the
file that tests `/diff` today; find it): two gameweeks with different
captains and one changed buy; `a` given without `b` is the one-parameter
path; an absent gameweek is `available=False`.

### 2.2 The History comparison (frontend)

`model/HistoryTab.tsx`: beneath the past-runs table, a "Compare" section
with two `select`s (default the two newest gameweeks in the list) and a
read of `/api/advice/diff?a=&b=` through `usePageData` (a new URL, so the
Model fetch rail changes by exactly this entry, declared). Rendered as
the same rows `WhyPanel`'s strip uses (`buys_added`, `buys_dropped`,
`sells_added`, `sells_dropped`, captain, chip, expected points and their
delta), reusing that component if it is separable (read `WhyPanel.tsx`
for the strip's markup; extract `AdviceDiffRows` into
`this-week/AdviceDiffRows.tsx` if it is not already a component, with
`WhyPanel`'s tests unchanged). Empty when `available` is false, with the
sentence "no served plan for one of these gameweeks".

### 2.3 "Since GW4" under the moves card (frontend)

`this-week/MovesCard.tsx` gains one muted line beneath the table when
`ThisWeek` passes a `since` prop from `/api/advice/diff?a=<gw-1>&b=<gw>`
(a second `usePageData` URL on This Week, declared in its rail):
"since GW4: captain unchanged · 1 buy swapped (Palmer → Bruno Fernandes)
· +1.4 pts" built from the diff's fields; nothing when unavailable.

### 2.4 Act from the squad (frontend)

`this-week/SquadTable.tsx` and `SquadPitch.tsx`: each player gets a row
menu (`@radix-ui/react-dropdown-menu`, already a dependency: `kit/
DataTable.tsx` uses it) with three items, *Lock*, *Ban*, *Must sell*,
each navigating to `/planning?tab=whatif` with `location.state.whatif`
set to a `WhatIfRequest` carrying that one code in `lock`, `ban` or
`must_sell`. `hubs/Planning.tsx` initialises its `whatif` state from
`useLocation().state?.whatif` when present (once, on mount). The pitch's
menu trigger is the existing card's click target (read `SquadPitch` for
what a tap does today; if it opens the explain modal, the menu is a
long-press/secondary control: a small `⋯` button in the card's corner,
`aria-label="actions for <name>"`); the table's is a `⋯` cell at the row's
end. Tests: choosing *Ban* navigates with the request; Planning mounts on
the What-If tab with the code in `ban`.

## 3. Gate, written before anything runs

1. Inner loop green; ruff clean.
2. The golden gate → 62 passed, 0 skipped.
3. `npm run check` green; the Model and This Week fetch rails change by
   exactly the two declared URLs; every other rail untouched.
4. Screenshot pairs at 1400, both themes: **This Week and Model** named
   (the since-line only if a previous gameweek's plan exists on the served
   tree; the History comparison); Planning, Players, League identical
   below the strip. Phone shots at 375 for This Week (the row menu) and
   Model, approved by eye.
5. New rails mutation-tested: the two-gameweek path (swap `a` and `b` in
   the assertion), the since-line (unavailable → no line), the row menu's
   navigation state.
6. The route pin: `tests/test_v11_degradation.py` passes unchanged at 51.

## 4. Outcome

Filled at the gate.
