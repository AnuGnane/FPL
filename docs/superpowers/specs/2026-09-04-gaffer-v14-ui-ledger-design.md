# gaffer v14 — the dark ledger (UI design language)

*Brainstormed and approved 2026-09-04 with the visual companion; the four
mockup screens the user chose from are in
`.superpowers/brainstorm/27279-1788630695/content/` (`direction.html`,
`colour-reach.html`, `type-accent.html`, `pitch.html`) and "before"
screenshots of six hubs sit beside them as `ui_*.png`. A refresh of the
web UI's design language only: no information-architecture change, no new
feature, no change to what any number means, no backend change.*

## 0. Why

The user's words: the UI "feels a bit unpolished and lacking a unified
design language"; he wants it "clean, professional … polished and
functional with a hint of colour", and explicitly not "the typical AI
designs with bubble rectangles and gradients with shadows". Looking at the
built app (screenshots above) the diagnoses were: a saturated green pitch
with white photo cards dropped into a muted page; stat tiles whose contents
vary in kind (a number, a name, a progress bar, a mono formula); mono
numerals inside sentences; four button styles and three corner radii; glyph
characters for nav icons; tables that differ in density from card to card;
colour used both for meaning and for chrome.

## 1. The decisions the user made

| Question | Chosen | Rejected |
|---|---|---|
| Direction | **A, Ledger**: hairline rules, no card boxes, dense, near-monochrome — but **dark** | B Panel (flat cards), C Terminal (mono, zebra) |
| Colour reach | **Ink + tint + bars**, bars "only where necessary to better convey the meaning and context makes sense" | Ink only; ink + tint |
| Type and accent | **One sans face, tabular figures, one blue accent** for interactive chrome | Mono numerals everywhere; neutral (white) accent |
| Pitch | **A, muted turf**: deep desaturated green, hairline markings, shirts kept smaller, dark tiles | Schematic (stripe, no shirts); formation rows (no pitch) |

Dark is the default; the light theme stays as an override of the same
tokens (the existing `data-theme` / `prefers-color-scheme` mechanism in
`frontend/src/styles/theme.css` and `kit/useTheme.ts`).

## 2. Approach: hybrid

Token-and-kit refresh first, so every page moves at once; then targeted
rework of the five places that shout; then a consistency sweep.

1. **Tokens** (`frontend/src/styles/theme.css`, the `@theme` block and the
   two light overrides).
2. **Kit** (`frontend/src/kit/*`): Card → Section, Stat, buttons, tabs,
   chips/Badge, DataTable, PageHeader, AppShell nav, PitchView/PlayerCard,
   FreshnessStrip, EmptyState, Skeleton, Toast, ThresholdBar.
3. **Five targeted reworks**: the This Week stat tiles; the pitch and
   player cards; the moves and ladder tables; the sidebar nav; the button
   set (Run/Fast advise, Rebuild, Re-solve, Pin, EO lens/Pitch/Table).
4. **Sweep**: every hub component checked against §4–§5; class names that
   encode the old language (`rounded-card`, `rounded-full`, `shadow*`,
   `font-mono`/`num` outside the allowed places, ad-hoc hex colours,
   `text-sage`/`text-rust` used for chrome) replaced.

## 3. Tokens

Names are the existing ones where they exist; new ones are marked.

**Surfaces** (dark values; light overrides re-declare every name):
- `--color-base` page `#121418`
- `--color-raised` *(new)* table header band, hover row, expanded row `#181b20`
- `--color-input` *(new)* form controls only `#1b1f25`
- `--color-border` hairline `#262a31`; `--color-divider` fainter `#1c1f25`

**Text**: `--color-text` `#e4e6ea`, `-secondary` `#c3c7ce`, `-muted`
`#8a909b`, `-faint` `#5f6570`.

**Semantic** (each with a `-tint` at 14% alpha, *new*):
- `--color-up` `#5fcf94` (replaces `sage` — rename, keep an alias for one
  cycle so tests and classes migrate in the sweep)
- `--color-down` `#f0876a` (replaces `rust`)
- `--color-warn` *(new)* `#e2b25a`
- `--color-accent` *(new)* `#4f8ff7`, `--color-accent-text` `#7fb0ff` for
  text on dark; the old `info` blue is retired into these.
- Position hues unchanged: gkp `#d9b064`, def `#7fb4e6`, mid `#b39ee8`,
  fwd `#e59ab5` (light-theme darkened values unchanged).
- Turf *(new)*: `--color-turf` `#1b3a2b`, `--color-turf-line`
  `rgba(255,255,255,.12)`; light theme `#2f6b45` / `rgba(255,255,255,.28)`.

**Shape**: `--radius-s` 2px (chips, meters), `--radius-m` 3px (buttons,
tiles, inputs). `--radius-card` (10px) and every `rounded-full` are removed.
No `box-shadow` anywhere except the Radix dialog/dropdown overlay, which
gets a 1px border instead.

**Type**: `--font-sans` unchanged (system stack); `--font-mono` kept only
for `JobLog` and the plan trace's formula lines. Base 13px/1.45. Scale:
label 10px uppercase tracked .08em muted; body 13px; secondary 12px; page
title 18px/600; section title = label; stat value 22px/600. Every numeral
in the app is `font-variant-numeric: tabular-nums` via one utility (`.tn`,
replacing `.num`), applied on table cells, stat values and inline numbers
alike — no face change inside prose.

**Space**: 4px grid; named gaps `--gap-s` 8px, `--gap-m` 12px, `--gap-l`
20px. Section padding 12px 16px; table cell padding 6px 10px; row height
32px in every table.

## 4. Colour rules (implementers may not drift from these)

1. **Green and rust mean a direction relative to something the user cares
   about**: price up/down, better/worse than the plan or the baseline, easy/
   hard fixture, in/out, ahead/behind. Never for chrome, never for emphasis.
2. **Amber means doubt**: availability under 100%, a data warning, a stale
   feed. The warning banner is an amber-tinted strip with a warning icon,
   not rust text in a rust outline.
3. **Blue means you can click it or it is active**: primary button, active
   tab underline, active nav item, links, focused input border, the
   selected row. Blue is never used for data.
4. **Grey is information**: labels, units, context lines, neutral values,
   fixture chips of middling difficulty.
5. **Position hues are identity**: the pos badge, the tile stripe, the
   compare panel's header — never a verdict.
6. **A tint** (14% fill) may sit behind a *cell* that carries a rule-1 or
   rule-2 signal; never behind a whole row, never on a heading.
7. **A bar** is allowed only where a magnitude between 0 and a known
   ceiling matters *and there are several to compare in one view*:
   the ladder's `p_beats_bank`/`p_best`, ownership and effective ownership
   in the Players table, scenario support in the moves table and the
   sensitivity table, the chip-threshold meter, the league race gap.
   A bar is a flat single-colour fill on the raised surface, 6px tall, no
   border, no gradient, the number printed beside it. Never on a single
   number, never in a stat tile except the chip meter.
8. **Turf** is the one non-semantic patch of colour on any page.

## 5. Components

- **Section** (replaces `Card`): a label band (10px uppercase) with a
  hairline below and an optional right-aligned action; content sits on the
  page surface, no border box. `Card` stays exported as an alias for one
  cycle with the new rendering, so the 38 call sites migrate in the sweep
  and nothing breaks in between. `titleSize="lg"` keeps its 18px heading
  (ComparePanel).
- **Stat**: label; value 22px with the unit in 12px muted beside it; one
  context line 12px muted; optional meter (rule 7). Every tile the same
  shape; a name (the captain) is a value like any other.
- **Buttons**: `primary` (accent fill, white text), `secondary` (hairline,
  text colour), `ghost` (text only, accent on hover); one height (28px),
  3px radius, 12px/500 text. `JobButton` uses them. Toggle groups (Pitch/
  Table, EO lens, position filters) are a segmented row of `secondary`
  with the active segment in accent text on the raised surface.
- **Tabs** (Radix): text 13px muted, active in text colour with a 2px
  accent underline.
- **Chip** (replaces `Badge` styling): 2px radius, 10px/600, tinted fill
  with the semantic text colour; used for IN/OUT, fixture difficulty,
  attack/cover, recommended, availability.
- **DataTable**: one style for every table — 10px uppercase headers on the
  raised band, `.tn` numerals right-aligned, 32px rows, hairline dividers,
  hover to raised, selected row accent-tinted. The moves table, the ladder,
  the sensitivity table, the Players explorer and the league standings all
  render through it or match it class-for-class.
- **Nav** (`AppShell`): sidebar kept at 200px; glyph characters replaced by
  `lucide-react` icons (16px): This Week `calendar-check`, Planning `route`,
  Players `users`, League `trophy`, Live `radio`, Model `activity`. Active
  item: accent text and a 2px accent bar on the left edge; no white card.
  Mobile bottom bar uses the same icons.
- **PageHeader**: title 18px, context line muted, actions right.
- **FreshnessStrip**: as now, 11px muted; a stale feed goes amber (rule 2).
- **Pitch** (`PitchView`, `PlayerCard`): turf token background, 1px
  `turf-line` outer rectangle and halfway line, no texture; player tile
  92px wide on `--color-base` with a hairline border, shirt image 26px,
  name 11.5px/600, club · price line muted `.tn`, fixture chip (rule 1
  tints for easy/hard, grey for mid), C/V as a 9px white (C) or grey (V)
  square tag after the name; bench as a labelled row beneath the turf on the
  page surface. EO lens tints the tile background by ownership (rule 7
  magnitude, as a tint not a bar).
- **Warning banner**: amber tint, amber left bar, 13px text, warning icon.
- **Inputs/selects**: input surface, hairline border, 3px radius, accent
  border on focus; the player search boxes and the cap selects alike.
- **Toast, Skeleton, EmptyState, ExplainModal**: restyled to tokens; the
  dialog gets a hairline border instead of a shadow.

## 6. The five targeted reworks (what changes beyond inheritance)

1. **This Week stat tiles**: Expected XI (value, unit, "raw model points"),
   Captain (name, "55% of sims · vice Semenyo"), Next chip (value "BB",
   unit "GW5", context "14.0 of 12.8 needed", meter), League ("44",
   "behind", "chase · tilt +0.1"). One shape.
2. **Pitch and bench** per §5.
3. **Moves table and ladder**: DataTable; IN/OUT as chips; sims support as
   a bar (rule 7); the ladder's cost column prints "−4 now · −12 over 3 GWs"
   in one cell with the horizon figure in `down`; `p_best` and
   `p_beats_bank` as bars with the percent beside; the cap row's highlight
   is the selected-row accent tint; rows beyond the cap in `text-faint`.
4. **Nav** per §5.
5. **Buttons and toggles** per §5, everywhere.

## 7. Process and gate

Branch `v14-ledger` off `main`. Order: tokens → kit → the five reworks →
sweep. After each stage the implementer captures headless screenshots of
the six hubs (`/`, `/planning?tab=whatif`, `/planning?tab=board`,
`/players`, `/league`, `/model?tab=settings`) in both themes with the
Playwright headless shell already on this machine
(`~/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell --headless --window-size=1400,1600 --virtual-time-budget=12000 --screenshot=<png> http://localhost:8927<path>`,
with `uv run gaffer ui --no-open-browser` serving a fresh `npm run build`)
and the orchestrator puts them in the visual companion for the user. The
user's approval of the screenshots is the gate; there is no replay.

Tests: `cd frontend && npx tsc --noEmit && npx vitest run` green at every
commit (an `Errors N error` summary line is a failure); tests that assert
old class names are updated with the component, tests that assert
behaviour are untouched. Python suite unaffected. Pins unchanged (routes
48, `JOB_KINDS` 12, `Config` 57). A new `frontend/src/kit/tokens.test.ts`
pins the rules that can be pinned: no `rounded-full`, no `shadow-`, no
`bg-gradient`, no raw hex in `hubs/**` and `kit/**` except `theme.css` and
the shirt/turf tokens; `font-mono` only in `JobLog` and the trace.

## 8. Out of scope

Information architecture, tab names, routes, any new data on any page,
the HTML report, the CLI. Recharts charts keep their data but take the
token colours.
