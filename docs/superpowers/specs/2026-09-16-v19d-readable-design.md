# v19d — This Week, readable (design)

**Cycle:** v19d, the fourth sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19d; plan
`plans/2026-09-15-v19-programme.md` §3 v19d; research
`research/2026-09-15-v19-research-frontend.md` items 2, 3, 11 and §2.5).
**Branch:** `v19d-readable` off `main` at v19c's merge.
**Date:** 2026-09-16. **Status:** drafted; starts after v19c merges.

---

## 1. What this changes, and what it does not

This Week is one long page: header, stats, squad, moves, decision,
ladder, brief, why, news (`hubs/ThisWeek.tsx:224-405`), about 4,000 px at
1400 wide, with nothing sticky and nothing to jump with. The ladder
carries a five-line paragraph above its rows every week
(`this-week/LadderCard.tsx:147-155`) and the board two paragraphs above
its columns (`planning/PlannerBoard.tsx:221-248`) plus a nine-line
caveat repeated under every week column that has moves
(`PlannerBoard.tsx:434-460`). The words are right and stop a number being
misread; they also stand between the reader and the numbers on every
visit. Nothing on the page can be taken away: no copy of the moves, no
print layout, no link to the rendered report under `reports/`.

No served number changes; no fetch changes except the report link, which
is a static mount and not an API route (the route pin counts OpenAPI
paths). This Week's and Planning's 1400-wide first paints change and are
named; the other four hubs' pairs must be identical below the strip.

## 2. The changes

### 2.1 The context strip and anchors (This Week)

A new `this-week/ContextStrip.tsx`: one line, `sticky top-0 z-10
bg-base border-b border-border`, showing `GW5 · 2d 4h · captain Haaland ·
1 move · 58.2 pts` (the countdown from `kit/Countdown` in its short form,
a `short` prop that drops the absolute stamp) and, on the right, anchor
links for the page's sections (Squad, Moves, Ladder, Brief, Why, News)
that scroll to `id`s set on the existing `Card`s (`Card` gains `id?:
string`). The strip renders below the `PageHeader` and becomes sticky
once the header scrolls away; at 1400 the first paint gains one line
under the header, which is the named change. On a phone the anchors wrap
to a second line. Tests: the strip names the gameweek, captain and move
count; each anchor's `href` matches a section `id` on the page.

### 2.2 The caveat printed once (Planning → board)

`PlannerBoard.tsx:434-460`'s per-week note moves to one paragraph under
the column row, keeping the per-week `Try these changes` button in its
column. The sentence that names the week (`starts now at GW n over m
weeks`) is the only per-week fact in it; the hoisted paragraph says it
once for the horizon ("each button prefills a solve that starts now at
GW5; a later week's buys may need earlier sells first …") and the
`Hits capped at 3` clause is appended when any shown week exceeds three.
`data-testid="board-try-note"` once; the per-week testids go. Tests
updated to the one note.

### 2.3 "How to read this" disclosures

A new `kit/Disclosure.tsx`: `summary` text in `text-text-muted`, a
chevron, `aria-expanded`, children in the same muted prose; `storageKey`
optional, and when given the open state is read from `localStorage`
(wrapped in try/catch; absent or throwing storage means open) and written
on toggle. The ladder's paragraph (`LadderCard.tsx:147-155`) and the
board's two paragraphs (`PlannerBoard.tsx:221-248`) go behind
`<Disclosure summary="How to read this" storageKey="…">`, open on first
visit so the first-paint pairs are taken with storage cleared and show the
prose, collapsed after the reader closes it once. Tests: open by default;
closes and remembers; a throwing storage still renders open.

### 2.4 Something to take away

- **Copy the moves.** A `Button` on the moves card, "Copy", writing the
  moves as plain text (`OUT Palmer → IN Bruno Fernandes · 1 hit · captain
  Haaland`) to the clipboard via `navigator.clipboard.writeText`, with a
  toast through the existing `ToastOutlet` on success and the text shown
  in a `<pre>` fallback when the clipboard API is absent (LAN over http
  has no clipboard on some phones).
- **A print stylesheet.** `@media print` in `styles/theme.css`: the nav,
  the freshness strip, the context strip, every `JobButton` and the
  disclosures' chevrons hidden; disclosures forced open; page breaks
  avoided inside cards; the light tokens used. Tested by a rule in
  `tokens.test.ts` that the print block exists and names `nav` and
  `[data-testid="freshness-strip"]`.
- **The report link.** `web/app.py` mounts `reports/` at `/reports`
  (`StaticFiles`, read-only, existing directory or nothing mounted); the
  moves card's footer links to `/reports/gw{gw}-report.html` when the
  served plan's gameweek has one (`GET /api/advice/latest` already says
  the gameweek; the link is rendered unconditionally and a 404 is the
  browser's, not the page's). Not an OpenAPI path; the route pin stays 51.

## 3. Gate, written before anything runs

1. Inner loop green; ruff clean (`app.py` changes).
2. The golden gate → 62 passed, 0 skipped.
3. `npm run check` green; fetch rails untouched.
4. Screenshot pairs `v19d-before`/`-after` at 1400, both themes, storage
   cleared: **This Week and Planning → board** named; Planning → what-if,
   Players, League and Model identical below the strip. Phone shots at
   375 for This Week, approved by eye.
5. New rails mutation-tested: the one-note rail (add a second note), the
   disclosure's storage read (invert the default), the print rule (drop
   `nav` from the block).

## 4. Outcome (2026-09-16, gate run by the orchestrator)

Commits on `v19d-readable`: `35bea43` spec; `5344769` the reports mount
(orchestrator; three tests, the route pin untouched at 51); `6b8cad9`
the frontend (`ContextStrip`, `Disclosure`, `Countdown short`, `Card id`,
the board's one note, copy, the report link, the print block).

| Gate line | Result |
|---|---|
| 1 inner loop | `4390 passed, 148 deselected, 4 warnings in 71.69s`; ruff `All checks passed!` |
| 2 golden | `62 passed in 1096.21s (0:18:16)`, 0 skipped |
| 3 npm run check | exit 0, `Tests 1172 passed \| 1 skipped (1173)`, `0 errors, 8 warnings`; fetch rails untouched |
| 4 screenshots | twelve desktop pairs 15:22:55–15:23:13, storage clear: Players, League, Model identical whole-image; This Week rows 113–1599 and the board rows 27–666 as named; **Planning → what-if rows 561–1599 unnamed but explained** — the What-If tab renders the same `LadderCard`, so the ladder's new disclosure line appears there too (a page the spec should have named); phone shots at 375 approved with the desktop pair by the user |
| 5 mutations | a second `board-try-note` (five tests fail); the disclosure's `'closed'` branch dropped (its test fails); `nav` dropped from the print block (the tokens rule fails) |

**Judgement calls kept:** no negative margins on the sticky strip (three
paddings to track); the board's "Starting bank" line stays outside the
disclosure because it prints a served number; `Disclosure` renders its
content `hidden` rather than as `<details>` so the print block can force
it open; `Countdown short` carries its own testid.

**Residual, recorded:** the What-If tab's ladder prose is behind the same
disclosure as This Week's, sharing `storageKey="ladder-help"`, so closing
it on one page closes it on both — intended, but worth a sentence in the
GUIDE.
