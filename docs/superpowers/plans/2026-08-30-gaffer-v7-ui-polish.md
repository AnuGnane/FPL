# gaffer v7-ui editorial polish

> Part of the v7-ui cycle (spec `2026-08-29-gaffer-v7-ui-design.md`); user
> editorial feedback from the smoke walkthrough, 2026-08-30. One implementer
> group. TDD where behavioural; visual-only changes need a rendering test
> only where a class/token assertion is cheap.

**Goal:** position-coloured identity across the app, and every surface
brought up to the kit standard — the user called out the bottom of This Week
(WhyPanel/NewsPanel) as visibly unpolished vs the top.

**Root cause found in review:** the nine files in `frontend/src/components/`
predate the kit and still use CSS classes (`banner`, `card`, `muted`, `tag`,
`ticker`, `picker`, `matches`, `chips`, `good`, `bad`, `player-link`) whose
definitions died with `tokens.css` — they render as bare unstyled text.
`Countdown`, `StalenessBanner`, `ExplainModal` have zero consumers.

## Task P1 — position tokens + `PosBadge` kit component

- Add four position hues to `frontend/src/styles/theme.css` `@theme`,
  muted to sit on the dark base and distinct from the meaning colours
  (sage/rust/blue) so they read as *identity*, not judgement:
  `--color-pos-gkp: #d4a95c` (amber), `--color-pos-def: #6ea8d8` (sky),
  `--color-pos-mid: #a48fd8` (violet), `--color-pos-fwd: #d88fa8` (rose).
  Extend the theme test's token assertions.
- New `frontend/src/kit/PosBadge.tsx` (+ test, + barrel export):
  `<PosBadge pos="MID" />` → small uppercase mono label in the position
  colour; `variant="dot"` renders just a coloured dot (for tight cells);
  unknown position → muted text, no colour. Colour via a
  `POS_COLOR: Record<string, string>` map exported for reuse (PitchView,
  matrix strips).

## Task P2 — apply position identity everywhere a player appears

- `hubs/this-week/SquadTable.tsx`: Pos column renders `<PosBadge>`;
  collapsed (mobile) card keeps it as the dot variant next to the name.
- `hubs/Players.tsx` explorer: same for its position column; the position
  filter buttons take the position colour when active.
- `hubs/players/ComparePanel.tsx`: player header cards get a `<PosBadge>`.
- `kit/PitchView.tsx`: each disc gets a 2px ring (border) in the position
  colour; name row unchanged.
- `hubs/this-week/MovesCard.tsx`, `hubs/planning/` PlanDiffTable usages,
  `hubs/league/RivalDetail.tsx`, `hubs/Live.tsx`: wherever a position
  string is already available in the row data, show the dot variant beside
  the name. Do NOT add new API fields for this — only use what the payload
  already carries; where position isn't in the payload, skip (note which).

## Task P3 — restyle the six live legacy components onto the kit

For each: keep the data logic and test intent, replace the dead classes
with kit components/Tailwind tokens, and move the file under the hub that
owns it if it has a single consumer (WhyPanel/NewsPanel →
`hubs/this-week/`; PlanDiffTable/ConstraintsPanel/FixtureTicker →
`hubs/planning/`; PlayerName stays shared → move into `kit/` as it is
cross-hub). Update imports and test files (`git mv` preferred).

- `WhyPanel`: wrap in `Card` ("Why this plan"); DiffStrip becomes a proper
  banner row (border-l-2 in blue token, muted timestamp, sage/rust delta);
  the per-player EP breakdown table gets mono numerals and row dividers to
  match SquadTable's expand.
- `NewsPanel`: `Card` ("News"), rows with `Badge` for status/source chips,
  muted secondary text — visually the sibling of the moves card.
- `PlanDiffTable`, `ConstraintsPanel`, `FixtureTicker`: `Card` +
  kit table/typography treatment consistent with their tab siblings.
- `PlayerName`: kit link styling (primary text, hover underline, position
  dot optional prop).

## Task P4 — delete dead components

`git rm` `components/Countdown.tsx`, `components/StalenessBanner.tsx`,
`components/ExplainModal.tsx` (+ their test files). After P3 moves, delete
`frontend/src/components/` entirely if empty.

## Task P5 — page-by-page misfit sweep

Walk every hub file and bring stragglers to the This Week top-half
standard. Checklist per page (fix in place, note each fix in the report):

- One `PageHeader` per hub with a real context line.
- All numerals in data contexts use the mono class; all labels use the
  9px uppercase muted pattern.
- Bare `<p>`/`<div>` content sitting outside any `Card` gets carded or
  deliberately left with a note ("intentional", e.g. tab strips).
- No raw hex colours in hub files — token classes only. `grep -n "#[0-9a-f]\{6\}"
  frontend/src/hubs frontend/src/kit` (excluding theme.css) should end empty
  or justified.
- Empty/loading branches render `EmptyState` or a styled skeleton, not
  bare text ("Loading…" is acceptable only inside a Card with muted class).
- Consistent vertical rhythm: hub root uses the same gap/spacing scale as
  ThisWeek (`space-y-3`/`gap-3` family).

## Task P6 — gates

Full `npm test -- --run`, `npx tsc -b`, `npm run build`,
`.venv/bin/python -m pytest -q` (backend must be untouched — this is a
frontend-only round). Protected paths zero-diff. Commit per task.
