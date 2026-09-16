# v19c — the phone (design)

**Cycle:** v19c, the third sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19c, ruling 7; plan
`plans/2026-09-15-v19-programme.md` §3 v19c; research
`research/2026-09-15-v19-research-frontend.md` items 4–8 and
`-product.md` §6).
**Branch:** `v19c-phone` off `main` at v19b's merge.
**Date:** 2026-09-16. **Status:** drafted; starts after v19b merges.

---

## 1. What this changes, and what it does not

The phone layout is one JavaScript switch: `useIsMobile()` at
`kit/AppShell.tsx:24` swaps the 200 px sidebar for a bottom tab bar at
767 px and below, and everything else is the desktop page squeezed into
375 px, with each of about thirty-five hand-rolled tables inside its own
`overflow-x-auto` scroller (`hubs/responsive.test.tsx` pins that nothing
scrolls the body sideways, which is correct and undesigned). The tab bar
holds seven items, six hubs and the theme toggle, at 11 px, with a fixed
`pb-16` that ignores the home indicator. Between 768 and 1023 px a
landscape phone or an iPad gets the 200 px rail beside a wide table and
double-scrolls. On a 1440 px laptop the main column stops at 1180 px
while the sixteen-column Players table still scrolls sideways. There is
no skip link, no `id` on `<main>`, and the heading ladder jumps from the
page's `h1` (`kit/PageHeader.tsx:15`) to a card's `h3`
(`kit/Card.tsx:42`).

No served number changes and no fetch changes. The desktop first paint
at 1400 wide does not change on any hub: every change below is either
under 1024 px, above 1400 px, or invisible (a focus-only link, a heading
level).

## 2. The changes

### 2.1 Stacked rows for the four tables read on a phone

Corrected before task 2 ran: `kit/DataTable.tsx`'s desktop mode renders
sortable headers and an expand column, so moving a hand table onto it
would change the 1400-wide paint, which this sub-cycle promises not to.
Instead `kit/StackedRows.tsx` is a small component — a list of rows, each
a heading line and up to four label/value pairs, in the ledger style
(hairline between rows, no card) — and each of the four tables renders it
under `useIsMobile()` and its existing `<table>` otherwise, so the desktop
path is untouched byte for byte. The four, in the order a Thursday reader
meets them: the moves table (`this-week/MovesCard.tsx`), the squad table
(`this-week/SquadTable.tsx`), the ladder's rungs
(`this-week/LadderCard.tsx`, whose `RungRow` toggle becomes the stacked
row's disclosure on a phone), and the board's plan columns
(`planning/PlannerBoard.tsx`). Each component keeps one source of truth
for what a row says: the cells are computed once and handed to either
rendering, so the phone cannot drift from the desktop.

### 2.2 The tab bar

`kit/AppShell.tsx:45-68`: six items, the `ThemeToggle compact` leaves
the bar for a slot at the top right of the mobile `<main>` (beside the
freshness strip's row, `flex` with the strip on the left); the bar's
container gains `pb-[env(safe-area-inset-bottom)]` and the page's `pb-16`
becomes `pb-[calc(4rem+env(safe-area-inset-bottom))]`; the `<meta
name="viewport">` in `index.html:5` gains `viewport-fit=cover`, without
which the inset is zero. Labels stay; icons stay.

### 2.3 The tablet rail

`kit/useMediaQuery.ts` gains `useIsCompact()` for `(min-width: 768px)
and (max-width: 1023px)`. `AppShell` renders, in that band, the sidebar
as an icon-only rail (`grid-cols-[56px_1fr]`, each `NavLink` its icon
with the label as `aria-label` and `title`, the wordmark as a single
letter, the theme toggle compact) so a wide table beside it has 60 px
more and the page never double-scrolls. `data-mode="rail"` on the nav.

### 2.4 Wide tables above 1400

`AppShell.tsx:88`'s `max-w-[1180px]` moves from `<main>` to a `kit/Page`
wrapper every hub already renders through (`PageHeader` is not it; read
`App.tsx` and the hubs' outermost element; if there is no shared wrapper,
`<main>` keeps the cap and a `data-wide` attribute set by the Players
hub lifts it to `max-w-none` for that route alone). Only Players opts
out in this sub-cycle.

### 2.5 Landmarks

`index.html`: a skip link as the first element of `<body>`, `<a
href="#main" class="sr-only focus:not-sr-only …">Skip to content</a>`
styled from the tokens (no new colour). `AppShell`'s `<main>` gets
`id="main"` in both layouts. `Card` gains `level?: 2 | 3` (default 2),
rendering `h2` or `h3`; `PageHeader` stays `h1`. The nested cards that
sit inside another card's body (read `Card` usages inside `Card`
children: the sections under the Health tab, the What-If panel's inner
cards) pass `level={3}`. `TITLE_CLASS` unchanged, so the pixels do not
move.

### 2.6 The rails

`hubs/responsive.test.tsx` gains: the four named tables render no
`<table>` at 375 (`StackedRows`); the tab bar has six
items and no theme toggle; the nav is `data-mode="rail"` at 900 and
`sidebar` at 1400; `<main>` has `id="main"` and the skip link targets it.
`kit/tokens.test.ts` gains one rule: no `pb-16` under `kit/` or `hubs/`
(the inset-aware form is the only allowed bottom padding on a fixed bar).
`frontend/scripts/shots.sh` takes `WIDTHS="1400 820 375"` (an env
override, default `1400`) and names the file `<hub>-<theme>-<width>.png`
when more than one width is asked for, the 1400 name unchanged when not.

## 3. Gate, written before anything runs

1. `cd frontend && npm run check` green; the `Errors` line absent; the
   eight recorded warnings not exceeded.
2. Fetch rails untouched.
3. Desktop pairs `shots.sh v19c-before` on `main` and `v19c-after` on
   the branch at 1400, both themes, all six hubs: **identical below the
   strip on every hub** (no hub is named; this sub-cycle has no desktop
   first-paint change). Measured with the Pillow script from v19a.
4. Phone (375) and tablet (820) shots of all six hubs in both themes on
   the branch, sent to the user and approved by eye (ruling 7). Before
   sets at those widths are taken too, for the record, not compared.
5. New rails mutation-tested: the six-item bar (add the toggle back), the
   rail mode (change the breakpoint), the `pb-16` rule (plant one).
6. `hubs/responsive.test.tsx`'s existing "scrolls nothing sideways"
   rules still pass at 375 with the new layout.

## 4. Outcome (2026-09-16, gate run by the orchestrator)

Commits on `v19c-phone`: `f0aa8e9` spec; `3c3cf3d` the shell (tab bar,
rail, wide Players past 1440, skip link, `Card` levels, the three rails,
`shots.sh` widths and its shell path); `13d8024` the bar's 4 px restored
beside the inset; `189a1e1` §2.1 corrected; `4e2fb8f` `StackedRows` and
the four tables under the mobile switch.

| Gate line | Result |
|---|---|
| 1 npm run check | exit 0, `Tests 1149 passed \| 1 skipped (1150)`, `0 errors, 8 warnings` |
| 2 fetch rails | untouched |
| 3 desktop pairs | twelve pairs at 1400, both themes, 15:07:59–15:08:22: **all byte-identical**, whole image (not only below the strip) |
| 4 phone and tablet | 36 shots per set (six hubs × two themes × three widths), the after set sent to the user for approval; before set kept for the record |
| 5 mutations | the toggle back in the bar (one rail fails); the rail's breakpoint moved (two fail); `pb-16` planted in Live (the tokens rule names the line); the `useIsMobile` switch removed from `MovesCard` (the stacked rail fails alone) |
| 6 existing responsive rules | pass at 375 with the new layout |

**Corrections on the way.** §2.1 was rewritten before task 2 ran:
`DataTable`'s desktop mode carries sortable headers and an expand
column, so the four tables keep their hand markup and render
`StackedRows` under `useIsMobile()` instead. The 1441 px guard on the
Players opt-out was needed (at 1400 the 1180 cap binds by 20 px). The
squad table has no XI/bench grouping to carry: `ThisWeek` hands it one
flat array, so the stacked rows keep the served order. The board's
columns never drew a `<table>`; its 375 rail asserts the stacked list.

**Residuals, recorded:** the skip link's classes are compiled from
`index.html` because Tailwind's Vite plugin scans it; a build that stops
scanning `index.html` would silently lose them (a rule in `tokens.test.ts`
could pin the link's presence, v19h). `responsive.test.tsx`'s `apiPost`
now rejects by default, which the file's older tests relied on
implicitly.
