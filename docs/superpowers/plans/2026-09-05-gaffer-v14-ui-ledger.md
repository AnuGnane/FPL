# gaffer v14 — the dark ledger: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the web UI's design language becomes the dark ledger the user chose on 2026-09-04 — hairline rules instead of card boxes, one sans face with tabular figures, one blue for interactive chrome, green/rust/amber only where they mean something, bars only where a magnitude is compared, a muted-turf pitch — with no change to information architecture, routes, data or backend.

**Architecture:** four stages, in order, so every page moves at once and the five loudest places are then reworked by hand (spec §2). (1) **Tokens**: `theme.css` gains the new names (`raised`, `input`, `up`/`down`/`warn`/`accent` with `-tint`s, `turf`) and keeps the retired names as one-cycle aliases so nothing breaks mid-branch. (2) **Kit**: five new primitives (`Button`, `Segmented`, `Chip`, `Bar`, `Callout`) plus shared class constants for tables, tabs and inputs; every existing kit component restyled to tokens. (3) **Five reworks**: This Week's stat tiles, the pitch, the moves table and ladder, the nav, the button set. (4) **Sweep**: every hub component checked against spec §4–§5, then a `tokens.test.ts` that pins the rules mechanically. Screenshots of the six hubs in both themes are captured after stages 2, 3 and 4 and shown to the user; the user's approval of the final set is the gate.

**Tech Stack:** React 18.3 + TypeScript 5.5, Tailwind v4 (`@theme` tokens), Radix tabs/dialog/dropdown, Recharts 2, `lucide-react` (new, icons), vitest + testing-library; the Playwright Chromium headless shell already on this machine for screenshots. No Python changes.

**Branch:** all work on `v14-ledger`, cut from `main` at `bb6ae40` (`git switch -c v14-ledger main`). The orchestrator ff-merges after the final review and the user's screenshot approval; nobody pushes to `main` from this plan.

**Spec:** `docs/superpowers/specs/2026-09-04-gaffer-v14-ui-ledger-design.md`. The mockups the user chose from are in `.superpowers/brainstorm/27279-1788630695/content/` (`direction.html`, `colour-reach.html`, `type-accent.html`, `pitch.html`) with "before" screenshots beside them (`../ui_*.png`). Read the spec and look at `pitch.html` and `type-accent.html` before Tasks 6–8.

**Standing rules for every task.** Frontend: `cd frontend && npx tsc --noEmit && npx vitest run` green at every commit — a vitest summary line reading `Errors  N error` is a **failure** even when every test passed; read the tail. Baseline at the branch point: **814 passed, 1 skipped, 80 files**, `tsc` clean. Python: untouched; the orchestrator runs `.venv/bin/pytest` once before the merge (must stay 4110 passed). Pins unchanged: routes 48, `JOB_KINDS` 12, `Config` fields 57 — nothing here can move them. Protected files (`src/gaffer/advise.py`, `set_pieces.py`, `optimize/**`, `web/jobs.py`, `web/routers/whatif.py`, the named tests, `scripts/s2_replay.py`) are not touched; this plan edits only `frontend/**` and `docs/**`. Stage explicit paths only — never `git add -A`, never `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `.superpowers/`, `config.toml`, `config.local.toml`, `src/gaffer/web/static/`. Every commit ends with:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke
```

**Security.** The odds API key lives only in the untracked `config.toml`. Refer to it by name only; never copy its value into any file, prompt, plan or summary. Nothing in this plan reads `config.toml`.

**Tests policy (spec §7).** A test that asserts an *old class name* (`text-sage`, `num`, `rounded-card`, `bg-card`, a `style.borderColor` the lens no longer sets) is updated in the same task as the component. A test that asserts *behaviour* (what is rendered, what a click does, ARIA) is not touched. Every such update is listed in its task.

---

## Rulings: where the code contradicts or under-specifies the spec

Found while reading the tree; each is applied below and is the orchestrator's to overturn.

- **R1 — radius token names.** The spec names `--radius-s` and `--radius-m`. Tailwind v4 already owns `rounded-s-*` (the logical inline-start radius), so a `--radius-s` token would collide. The 2px and 3px values ship as `--radius-chip` and `--radius-ctl` (`rounded-chip`, `rounded-ctl`).
- **R2 — the strip's three tones.** `FreshnessStrip.tone()` returns `text-moss` / `text-amber` — classes no token has ever defined, so today all three ages render in the inherited grey. Under §4: under a day is information (`text-text-muted`), one to three days is doubt (`text-warn`, rule 2), three days and beyond is behind where it should be (`text-down`, rule 1 "ahead/behind"). The strip's own test is rewritten to those three.
- **R3 — the pitch tile's second line is xPts, not price.** Spec §5 says "club · price line". The mockup's "MCI · 7.6" is the player's expected points (Guéhi is 6.0 in the Players table, 7.6 xPts), and the tile has always printed `ep`. Nothing changes meaning: the line stays `TEAM · xPts` in the muted tabular style. The kickoff day/time the current chip prints moves into the chip's `title` — the mockup tile carries none, and the reader chooses no captain from it.
- **R4 — errors.** §4 has no error colour; rule 1 forbids rust for emphasis. A failed job, a refused save and a solver error are stated in `down` ink inside a `down`-tinted callout — the one use of `down` that is not a direction, said here once. Toast's `negative` tone follows the same rule.
- **R5 — informational notices.** The `border-l-2 border-info bg-base` callouts (WhyPanel pins, sensitivity notice, Live, ticker, Quality, the modal's double-GW total) are information, not warnings: grey left bar on the raised surface (rule 4). Blue never carries data (rule 3).
- **R6 — chart series colours.** §8 says charts "take the token colours" and rule 3 retires blue from data. Every multi-series chart (League race, Compare radar and panel, History, Season, Live, Journal) draws from one `SERIES_COLOURS` in kit — text, muted, secondary, faint — with the third and fourth series dashed, and "you" always the first (brightest). Position hues are not used for series (two MIDs would collide). Reversible at the gate if the greys do not read.
- **R7 — chips that were `info`.** `Badge variant="info"` (the moves tag, "recommended", "Pens", chip names, "manual", instrument names) is information: `Chip tone="neutral"`. Availability doubt (`news`/`chanceOfPlaying` badges on the pitch and in the squad table, the pin dialog's warning) moves from `negative` to `warn` (rule 2).
- **R8 — the bar track.** Rule 7's "on the raised surface" names where a bar sits; the track itself is drawn in `border` (`#262a31`), which is the mockup's `#23272e` — on `raised` it would vanish inside a hovered row.
- **R9 — the position filters.** `Players.test.tsx` pins the active position filter to the position's own hue. Spec §5 puts position filters among the segmented toggles whose active segment is accent text. The spec wins; that one assertion is rewritten.
- **R10 — the dark screenshot.** `--force-dark-mode` does not flip `prefers-color-scheme` in the headless shell (probed: byte-identical output). `--blink-settings=preferredColorScheme=0` does (probed: dark). The shots script uses it; nothing in the app changes for the gate.
- **R11 — one-cycle aliases.** `--color-card`, `--color-sage`, `--color-rust`, `--color-info` and `--radius-card` keep their utilities alive during the branch as literal duplicates of the new values; `.num` becomes a synonym of `.tn` (tabular, no face change — the spec's rule from Task 1 on). The `-soft` tokens go in Task 1: only `Badge`, `JobLog` and one banner use them and all three are rebuilt before the first gate. Task 12 removes `card`, `info`, `radius-card`, `.num` and `difficultyBackground`; `sage`/`rust` stay declared but unused, as the spec says, and `tokens.test.ts` forbids their use.
- **R12 — `Section` keeps the `Card` name.** 35 files, 100 call sites. `Card.tsx` becomes the Section rendering; `Section` is exported as a second name; the sweep does not rename call sites (the spec allows the alias for the cycle and renaming 100 sites buys nothing). `Badge` likewise stays exported as a thin alias of `Chip`, and the sweep migrates call sites to `Chip` anyway because the tone names differ.

---

## File map

| File | Responsibility |
|---|---|
| `frontend/scripts/shots.sh` (new) | six hubs × two themes, headless, into `.superpowers/shots/<stage>/` |
| `frontend/src/styles/theme.css`, `theme.test.ts`, `built-theme.test.ts` | the tokens, both themes, `.tn`, `.label`, focus ring |
| `frontend/src/kit/Button.tsx` (new) | primary / secondary / ghost, one height; `buttonClass()` |
| `frontend/src/kit/Segmented.tsx` (new) | toggle groups; `segmentClass()` |
| `frontend/src/kit/Chip.tsx` (new), `Badge.tsx` | tinted chip, four tones; Badge = alias |
| `frontend/src/kit/Bar.tsx` (new) | rule-7 bar with the number beside it; optional mark |
| `frontend/src/kit/Callout.tsx` (new) | note / warn / error strips |
| `frontend/src/kit/table.ts`, `tabs.ts`, `field.ts`, `series.ts` (new) | shared class strings and the chart palette |
| `frontend/src/kit/Card.tsx` | Section rendering, `Card`/`Section` names |
| `frontend/src/kit/Stat.tsx`, `StatRow.tsx` (new) | the one tile shape; the hairline grid around tiles |
| `frontend/src/kit/*` (rest) | restyled to tokens (Task 3–4) |
| `frontend/src/kit/AppShell.tsx` | nav with lucide icons |
| `frontend/src/hubs/ThisWeek.tsx` | tiles, banner, buttons, toggles |
| `frontend/src/kit/PlayerCard.tsx`, `PitchView.tsx`, `hubs/this-week/SquadPitch.tsx` | the pitch |
| `frontend/src/hubs/this-week/MovesCard.tsx`, `LadderCard.tsx`, `planning/SensitivityCard.tsx` | the tables |
| every other `frontend/src/hubs/**` file | the sweep (Tasks 10–11) |
| `frontend/src/kit/tokens.test.ts` (new) | the mechanical rules |
| `docs/GUIDE.md`, `docs/superpowers/ROADMAP.md` | the cycle's record |

---

## The gate: capturing screenshots

The server that serves the built UI is `uv run gaffer ui --no-open-browser --port 8927` (one may already be running from a previous session: `lsof -iTCP:8927 -sTCP:LISTEN`; reuse it — `index.html` is served `no-cache` from disk and the hashed assets are mounted from disk, so a fresh `npm run build` is picked up without a restart). The build lands in `src/gaffer/web/static/` (gitignored). The script below writes twelve PNGs; the implementer looks at each with the Read tool before reporting, and the orchestrator shows them to the user. Three captures: `kit` (after Task 4), `reworks` (after Task 9), `sweep` (after Task 12).

```bash
cd frontend && npm run build && cd .. && frontend/scripts/shots.sh <stage>
```

---

## Task 0 — branch, baseline, the shots script

**Files:**
- Create: `frontend/scripts/shots.sh`

- [ ] **Step 1: Cut the branch and confirm the baseline**

```bash
cd /Users/anugnana/Library/Projects/FPL
git switch -c v14-ledger main
cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -5
```

Expected: `Tests  814 passed | 1 skipped (815)`, no `Errors` line, `tsc` silent.

- [ ] **Step 2: Write the shots script**

Create `frontend/scripts/shots.sh`:

```bash
#!/usr/bin/env bash
# v14 gate (spec §7): the six hubs in both themes, headless, into
# .superpowers/shots/<stage>/<hub>-<theme>.png. Serve a fresh build first:
#   cd frontend && npm run build && cd .. && \
#   (lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || uv run gaffer ui --no-open-browser --port 8927 &)
# Dark is forced through Blink's preferred colour scheme (0 = dark); the
# shell's default is light. --force-dark-mode does NOT flip it (probed).
set -eo pipefail
STAGE="${1:?usage: shots.sh <stage>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/.superpowers/shots/$STAGE"
SHELL_BIN="${CHROME_HEADLESS_SHELL:-$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell}"
BASE="${GAFFER_UI:-http://localhost:8927}"
mkdir -p "$OUT"
HUBS=(
  "this-week:/"
  "planning-whatif:/planning?tab=whatif"
  "planning-board:/planning?tab=board"
  "players:/players"
  "league:/league"
  "settings:/model?tab=settings"
)
for entry in "${HUBS[@]}"; do
  name="${entry%%:*}"; path="${entry#*:}"
  for theme in dark light; do
    if [[ "$theme" == dark ]]; then
      "$SHELL_BIN" --headless --blink-settings=preferredColorScheme=0 \
        --hide-scrollbars --window-size=1400,1600 --virtual-time-budget=12000 \
        --screenshot="$OUT/$name-$theme.png" "$BASE$path" >/dev/null 2>&1
    else
      "$SHELL_BIN" --headless \
        --hide-scrollbars --window-size=1400,1600 --virtual-time-budget=12000 \
        --screenshot="$OUT/$name-$theme.png" "$BASE$path" >/dev/null 2>&1
    fi
    echo "$OUT/$name-$theme.png"
  done
done
```

```bash
chmod +x frontend/scripts/shots.sh
```

- [ ] **Step 3: Prove it captures both themes on the current build**

```bash
cd frontend && npm run build 2>&1 | tail -2 && cd ..
lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || (uv run gaffer ui --no-open-browser --port 8927 &)
frontend/scripts/shots.sh baseline
```

Expected: twelve paths printed. Open `.superpowers/shots/baseline/this-week-dark.png` and `this-week-light.png` with the Read tool: one dark page, one light page, both with the sidebar and the GW header. If both are light, the `--blink-settings` flag did not take — stop and report; do not work around it in the app.

- [ ] **Step 4: Commit**

```bash
git add frontend/scripts/shots.sh
git commit -m "chore(v14): the screenshot gate — six hubs, two themes, headless

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---

## Task 1 — tokens

**Files:**
- Modify: `frontend/src/styles/theme.css` (whole file)
- Modify: `frontend/src/styles/theme.test.ts` (whole file)
- Modify: `frontend/src/styles/built-theme.test.ts` (the constants and one test)

- [ ] **Step 1: Rewrite the theme test to the new contract**

Replace `frontend/src/styles/theme.test.ts` with:

```ts
// @vitest-environment node
// Read as a plain file: under the default jsdom environment `import.meta.url`
// is an http:// URL and readFileSync cannot resolve it.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// v14 (spec §3): the dark ledger. The @theme block is the dark palette and
// the source of every token name; light is an override of the same names.
// Asserted by value, not by presence — these are the contract every kit
// component styles against.
const css = readFileSync(new URL('./theme.css', import.meta.url), 'utf8')

const DARK: Array<[string, string]> = [
  ['--color-base', '#121418'],
  ['--color-raised', '#181b20'],
  ['--color-input', '#1b1f25'],
  ['--color-border', '#262a31'],
  ['--color-divider', '#1c1f25'],
  ['--color-text', '#e4e6ea'],
  ['--color-text-secondary', '#c3c7ce'],
  ['--color-text-muted', '#8a909b'],
  ['--color-text-faint', '#5f6570'],
  ['--color-up', '#5fcf94'],
  ['--color-up-tint', '#5fcf9424'],
  ['--color-down', '#f0876a'],
  ['--color-down-tint', '#f0876a24'],
  ['--color-warn', '#e2b25a'],
  ['--color-warn-tint', '#e2b25a24'],
  ['--color-accent', '#4f8ff7'],
  ['--color-accent-text', '#7fb0ff'],
  ['--color-accent-tint', '#4f8ff724'],
  ['--color-pos-gkp', '#d9b064'],
  ['--color-pos-def', '#7fb4e6'],
  ['--color-pos-mid', '#b39ee8'],
  ['--color-pos-fwd', '#e59ab5'],
  ['--color-turf', '#1b3a2b'],
  ['--color-turf-line', '#ffffff1f'],
]

// Retired names kept for one cycle (spec §3, plan R11): same value as the
// name that replaced them, so a class not yet swept renders identically.
const ALIASES: Array<[string, string]> = [
  ['--color-card', '--color-raised'],
  ['--color-sage', '--color-up'],
  ['--color-rust', '--color-down'],
  ['--color-info', '--color-accent-text'],
]

const TOKENS = [...DARK.map(([name]) => name), ...ALIASES.map(([name]) => name)]

/** The declarations between `opener` and the first `}` that follows it. */
function block(opener: string): string {
  const start = css.indexOf(opener)
  expect(start, `${opener} missing`).toBeGreaterThan(-1)
  const from = start + opener.length
  return css.slice(from, css.indexOf('}', from))
}

function valueOf(source: string, token: string): string {
  const found = new RegExp(
    `${token}:\\s*(#[0-9a-f]{6}(?:[0-9a-f]{2})?);`,
  ).exec(source)
  expect(found, `${token} has no hex value`).not.toBeNull()
  return found![1]
}

// WCAG 2.1 relative luminance and contrast, nine lines rather than a
// dependency, so the test keeps running.
function channel(value: number): number {
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1, 7), 16)
  return 0.2126 * channel(((n >> 16) & 255) / 255)
    + 0.7152 * channel(((n >> 8) & 255) / 255)
    + 0.0722 * channel((n & 255) / 255)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('theme tokens', () => {
  it('imports tailwind and opens a @theme block', () => {
    expect(css).toContain('@import "tailwindcss"')
    expect(css).toContain('@theme {')
  })

  it('defines every dark token by value', () => {
    const theme = block('@theme {')
    for (const [name, value] of DARK) {
      expect(valueOf(theme, name), name).toBe(value)
    }
  })

  it('keeps every retired name as a literal copy of its replacement', () => {
    for (const scope of ['@theme {', '[data-theme="light"] {',
      ':root:not([data-theme="dark"]) {']) {
      const source = block(scope)
      for (const [alias, real] of ALIASES) {
        expect(valueOf(source, alias), `${alias} in ${scope}`)
          .toBe(valueOf(source, real))
      }
    }
  })

  it('defines no soft tier: tints replaced it', () => {
    expect(css).not.toMatch(/--color-[a-z]+-soft/)
  })

  // Identity, not judgement: these four must never collide with the meaning
  // colours, or a position badge starts reading as a verdict.
  it('keeps the position hues distinct from the meaning colours', () => {
    const meaning = ['#5fcf94', '#f0876a', '#e2b25a', '#4f8ff7', '#7fb0ff']
    for (const hue of ['#d9b064', '#7fb4e6', '#b39ee8', '#e59ab5']) {
      expect(meaning).not.toContain(hue)
    }
  })

  it('defines the two radii and no card radius larger than a control', () => {
    expect(css).toContain('--radius-chip: 2px;')
    expect(css).toContain('--radius-ctl: 3px;')
    expect(css).not.toContain('--radius-card: 10px;')
  })

  it('defines the faces, the tabular utility and the 13px base', () => {
    expect(css).toContain("--font-mono: 'SF Mono', Menlo, monospace;")
    expect(css).toMatch(/\.tn\s*\{[^}]*font-variant-numeric:\s*tabular-nums/)
    expect(css).not.toMatch(/\.num[^}]*font-family/)
    expect(css).toMatch(/body\s*\{[^}]*font-size:\s*13px/)
  })

  it('draws the one label style at 10px, .08em, uppercase, muted', () => {
    const label = block('.label {')
    expect(label).toContain('font-size: 10px')
    expect(label).toContain('letter-spacing: 0.08em')
    expect(label).toContain('text-transform: uppercase')
    expect(label).toContain('color: var(--color-text-muted)')
  })

  it('focuses in accent (rule 3)', () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:[^;]*var\(--color-accent\)/)
  })
})

describe('light theme', () => {
  it('overrides every token exactly once for an explicit light choice', () => {
    const light = block('[data-theme="light"] {')
    for (const token of TOKENS) {
      expect(light.split(`${token}:`).length - 1,
             `${token} in [data-theme="light"]`).toBe(1)
    }
  })

  it('mirrors the same tokens under a light system preference', () => {
    expect(css).toContain('@media (prefers-color-scheme: light)')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(mirror.split(`${token}:`).length - 1,
             `${token} in the system mirror`).toBe(1)
    }
  })

  it('lets an explicit dark choice out of the system mirror', () => {
    expect(css).toContain(':root:not([data-theme="dark"])')
  })

  it('agrees with itself: the mirror is the light block', () => {
    const light = block('[data-theme="light"] {')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(valueOf(mirror, token), token).toBe(valueOf(light, token))
    }
  })

  it('keeps the light turf and its markings', () => {
    const light = block('[data-theme="light"] {')
    expect(valueOf(light, '--color-turf')).toBe('#2f6b45')
    expect(valueOf(light, '--color-turf-line')).toBe('#ffffff47')
  })

  // Both surfaces: muted text sits on the page base and on the raised band
  // (table headers, hover rows), and a token that only clears 4.5:1 on one
  // is unreadable on the other.
  it('holds 4.5:1 for every text token on both light surfaces', () => {
    const light = block('[data-theme="light"] {')
    for (const surface of ['--color-base', '--color-raised']) {
      const hex = valueOf(light, surface)
      for (const token of ['--color-text', '--color-text-secondary',
        '--color-text-muted', '--color-up', '--color-down', '--color-warn',
        '--color-accent-text']) {
        expect(contrast(valueOf(light, token), hex),
               `${token} on ${surface}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it('keeps the faint tier at its 3.5:1 floor on the raised surface', () => {
    const light = block('[data-theme="light"] {')
    expect(contrast(valueOf(light, '--color-text-faint'),
                    valueOf(light, '--color-raised')))
      .toBeGreaterThanOrEqual(3.5)
  })

  it('is applied by a boot script before the bundle runs', () => {
    const html = readFileSync(new URL('../../index.html', import.meta.url),
                              'utf8')
    expect(html).toContain("localStorage.getItem('gaffer-theme')")
    expect(html).toContain("setAttribute('data-theme'")
    expect(html).toContain('try {')
    expect(html).toContain('catch')
    expect(html.indexOf("localStorage.getItem('gaffer-theme')"))
      .toBeLessThan(html.indexOf('/src/main.tsx'))
  })
})
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx vitest run src/styles/theme.test.ts`
Expected: FAIL — `--color-raised` has no hex value, and most of the rest.

- [ ] **Step 3: Write the theme**

Replace `frontend/src/styles/theme.css` with:

```css
@import "tailwindcss";

/* v14 — the dark ledger (spec §3). The @theme block is the dark palette and
   the source of every token name; light is an override of the same names,
   so no component knows which one is on.

   Colour rules (spec §4) in one breath: up/down mean a direction relative to
   something the reader cares about; warn means doubt; accent means you can
   click it or it is active; grey is information; the position hues are
   identity; turf is the one non-semantic patch of colour. */
@theme {
  /* Surfaces. */
  --color-base: #121418;
  --color-raised: #181b20;
  --color-input: #1b1f25;
  --color-border: #262a31;
  --color-divider: #1c1f25;

  /* Text. */
  --color-text: #e4e6ea;
  --color-text-secondary: #c3c7ce;
  --color-text-muted: #8a909b;
  --color-text-faint: #5f6570;

  /* Semantic, each with a 14% tint for the cell that carries the signal. */
  --color-up: #5fcf94;
  --color-up-tint: #5fcf9424;
  --color-down: #f0876a;
  --color-down-tint: #f0876a24;
  --color-warn: #e2b25a;
  --color-warn-tint: #e2b25a24;
  --color-accent: #4f8ff7;
  --color-accent-text: #7fb0ff;
  --color-accent-tint: #4f8ff724;

  /* Position hues are IDENTITY, not judgement — kept clear of every meaning
     colour so a violet MID never reads as a verdict. */
  --color-pos-gkp: #d9b064;
  --color-pos-def: #7fb4e6;
  --color-pos-mid: #b39ee8;
  --color-pos-fwd: #e59ab5;

  /* The pitch: deep desaturated turf, hairline markings. */
  --color-turf: #1b3a2b;
  --color-turf-line: #ffffff1f;

  /* Retired names, one cycle (plan R11): literal copies of the token that
     replaced each, so a class the sweep has not reached yet renders the new
     value. No new uses; tokens.test.ts forbids them from Task 12 on. */
  --color-card: #181b20;
  --color-sage: #5fcf94;
  --color-rust: #f0876a;
  --color-info: #7fb0ff;

  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'SF Mono', Menlo, monospace;

  /* Two radii: chips and meters, then buttons, tiles and inputs. Named
     chip/ctl rather than s/m because Tailwind owns `rounded-s-*` for the
     logical inline-start radius (plan R1). `--radius-card` is a one-cycle
     alias of the control radius. */
  --radius-chip: 2px;
  --radius-ctl: 3px;
  --radius-card: 3px;
}

/* Tells the browser to paint its own furniture — scrollbars, form controls,
   the canvas behind an overscroll — to match. Not in @theme, which only
   takes custom properties. */
:root { color-scheme: dark; }

/* An explicit light choice: `data-theme="light"` on <html>, set by
   kit/useTheme.ts and by the boot script in index.html. Position hues are
   darkened rather than re-hued. Muted and faint are darker than the v12
   light palette because they now also sit on the raised band. */
[data-theme="light"] {
  color-scheme: light;
  --color-base: #f4f5f7;
  --color-raised: #eaecef;
  --color-input: #ffffff;
  --color-border: #d6d9df;
  --color-divider: #e6e8ec;
  --color-text: #191c22;
  --color-text-secondary: #3d434e;
  --color-text-muted: #5f6672;
  --color-text-faint: #737a85;
  --color-up: #25703f;
  --color-up-tint: #25703f24;
  --color-down: #a3471f;
  --color-down-tint: #a3471f24;
  --color-warn: #86600f;
  --color-warn-tint: #c9931f24;
  --color-accent: #2f6fd6;
  --color-accent-text: #2458b3;
  --color-accent-tint: #2f6fd624;
  --color-pos-gkp: #96731f;
  --color-pos-def: #2867a5;
  --color-pos-mid: #6f51b8;
  --color-pos-fwd: #b04f78;
  --color-turf: #2f6b45;
  --color-turf-line: #ffffff47;
  --color-card: #eaecef;
  --color-sage: #25703f;
  --color-rust: #a3471f;
  --color-info: #2458b3;
}

/* "System" is the absence of the attribute, so the OS preference speaks
   here. The :not() guard keeps an explicit dark choice dark on a light-set
   machine. Byte-for-byte the block above; theme.test.ts holds them equal. */
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    color-scheme: light;
    --color-base: #f4f5f7;
    --color-raised: #eaecef;
    --color-input: #ffffff;
    --color-border: #d6d9df;
    --color-divider: #e6e8ec;
    --color-text: #191c22;
    --color-text-secondary: #3d434e;
    --color-text-muted: #5f6672;
    --color-text-faint: #737a85;
    --color-up: #25703f;
    --color-up-tint: #25703f24;
    --color-down: #a3471f;
    --color-down-tint: #a3471f24;
    --color-warn: #86600f;
    --color-warn-tint: #c9931f24;
    --color-accent: #2f6fd6;
    --color-accent-text: #2458b3;
    --color-accent-tint: #2f6fd624;
    --color-pos-gkp: #96731f;
    --color-pos-def: #2867a5;
    --color-pos-mid: #6f51b8;
    --color-pos-fwd: #b04f78;
    --color-turf: #2f6b45;
    --color-turf-line: #ffffff47;
    --color-card: #eaecef;
    --color-sage: #25703f;
    --color-rust: #a3471f;
    --color-info: #2458b3;
  }
}

html, body, #root { min-height: 100%; }

body {
  margin: 0;
  background: var(--color-base);
  color: var(--color-text);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.45;
}

/* Every numeral in the app is tabular, in the one sans face: table cells,
   stat values and numbers inside sentences alike (spec §3). `.num` is the
   pre-v14 name and a synonym until Task 12 deletes it. */
.tn, .num { font-variant-numeric: tabular-nums; }

/* 10px letter-spaced uppercase muted — the one label style in the system;
   section titles and table headers are this. */
.label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

/* Focus is accent, like every other "you can act here" (rule 3). */
:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}
```

- [ ] **Step 4: Update the built-stylesheet test's constants**

In `frontend/src/styles/built-theme.test.ts` replace the two constant lines and the two tests that use them:

```ts
// The dark tint values. Each may appear in the compiled sheet ONLY as the
// value of a `--color-*-tint` custom property — never as a literal
// background-color, which is what a re-baked opacity modifier looks like.
const TINT = ['#5fcf9424', '#f0876a24', '#e2b25a24', '#4f8ff724']
const BASE = ['#5fcf94', '#f0876a', '#e2b25a', '#4f8ff7']
```

```ts
  it('keeps the tint tier as variables, not as baked colours', () => {
    for (const value of TINT) {
      for (const at of indexesOf(css!, value)) {
        const from = Math.max(css!.lastIndexOf(';', at),
                              css!.lastIndexOf('{', at)) + 1
        expect(css!.slice(from, at), `${value} outside a variable`)
          .toMatch(/^--color-[a-z-]+-tint:\s*$/)
      }
    }
  })

  it('emits no border-color baked from a dark meaning colour', () => {
    for (const hex of BASE) {
      expect(css!, `border-color baked from ${hex}`)
        .not.toContain(`border-color:${hex}`)
    }
  })
```

- [ ] **Step 5: Run the suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6`
Expected: theme tests pass (if a contrast assertion fails, darken that light value until it clears and keep its alias in step); **everything else still passes** (every old class still resolves through the aliases; `.num` still exists). If `Stat.test`'s mono assertion is the only failure, that is expected only if you removed `.num` — you did not; `.num` is a synonym. Zero failures.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/theme.css frontend/src/styles/theme.test.ts frontend/src/styles/built-theme.test.ts
git commit -m "feat(v14): the ledger tokens — surfaces, up/down/warn/accent with tints, turf, two radii, tabular figures, 13px base

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---
## Task 2 — the new primitives

**Files:**
- Create: `frontend/src/kit/Button.tsx`, `Segmented.tsx`, `Chip.tsx`, `Bar.tsx`, `Callout.tsx`, `table.ts`, `tabs.ts`, `field.ts`, `series.ts`, `StatRow.tsx`
- Create tests: `Button.test.tsx`, `Segmented.test.tsx`, `Chip.test.tsx`, `Bar.test.tsx`, `Callout.test.tsx`, `table.test.ts`
- Modify: `frontend/src/kit/Badge.tsx`, `Badge.test.tsx`, `format.ts`, `format.test.ts`, `scale.ts`, `index.ts`, `index.test.ts`, `Stat.test.tsx`
- Modify: `frontend/package.json`, `frontend/package-lock.json` (lucide-react)

- [ ] **Step 1: Install the icon library**

```bash
cd frontend && npm install lucide-react@^1.41.0 2>&1 | tail -3
grep -n lucide package.json
```

Expected: `"lucide-react": "^1.41.0"` under dependencies. (If `npm view lucide-react version` prints something other than 1.41.x, install that latest and pin its major.)

- [ ] **Step 2: Write the failing tests for the primitives**

Create `frontend/src/kit/Button.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Button, { buttonClass } from './Button'

describe('Button', () => {
  it('is secondary by default: hairline, text colour, one height', () => {
    render(<Button>Rebuild</Button>)
    const b = screen.getByRole('button', { name: 'Rebuild' })
    expect(b).toHaveClass('border-border')
    expect(b).toHaveClass('h-7')
    expect(b).toHaveClass('rounded-ctl')
    expect(b).toHaveAttribute('type', 'button')
  })

  it('fills primary in accent with white text', () => {
    render(<Button variant="primary">Run advise</Button>)
    const b = screen.getByRole('button', { name: 'Run advise' })
    expect(b).toHaveClass('bg-accent')
    expect(b).toHaveClass('text-white')
    expect(b).not.toHaveClass('border-border')
  })

  it('draws ghost as text that goes accent on hover', () => {
    render(<Button variant="ghost">Close</Button>)
    expect(screen.getByRole('button', { name: 'Close' }))
      .toHaveClass('hover:text-accent-text')
  })

  it('passes disabled and aria through', () => {
    render(<Button disabled aria-pressed="true">EO lens</Button>)
    const b = screen.getByRole('button', { name: 'EO lens' })
    expect(b).toBeDisabled()
    expect(b).toHaveAttribute('aria-pressed', 'true')
  })

  it('exposes the class string for elements that are not buttons', () => {
    expect(buttonClass('primary')).toContain('bg-accent')
    expect(buttonClass('secondary', 'mt-2')).toContain('mt-2')
  })
})
```

Create `frontend/src/kit/Segmented.test.tsx`:

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Segmented, { segmentClass } from './Segmented'

const OPTIONS = [
  { value: 'pitch', label: 'Pitch' },
  { value: 'table', label: 'Table' },
] as const

describe('Segmented', () => {
  it('is a labelled group of pressed/unpressed buttons', () => {
    render(<Segmented label="Squad view" options={[...OPTIONS]}
                      value="pitch" onChange={() => {}} />)
    const group = screen.getByRole('group', { name: 'Squad view' })
    expect(within(group).getByRole('button', { name: 'Pitch' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(within(group).getByRole('button', { name: 'Table' }))
      .toHaveAttribute('aria-pressed', 'false')
  })

  it('paints the active segment accent on the raised surface', () => {
    render(<Segmented label="Squad view" options={[...OPTIONS]}
                      value="table" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Table' }))
      .toHaveClass('text-accent-text')
    expect(screen.getByRole('button', { name: 'Table' }))
      .toHaveClass('bg-raised')
    expect(screen.getByRole('button', { name: 'Pitch' }))
      .toHaveClass('text-text-muted')
  })

  it('reports the clicked value', async () => {
    const onChange = vi.fn()
    render(<Segmented label="Squad view" options={[...OPTIONS]}
                      value="pitch" onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
    expect(onChange).toHaveBeenCalledWith('table')
  })

  it('exposes the segment classes for controls with their own ARIA', () => {
    expect(segmentClass(true)).toContain('text-accent-text')
    expect(segmentClass(false)).toContain('text-text-muted')
  })
})
```

Create `frontend/src/kit/Chip.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Chip from './Chip'

describe('Chip', () => {
  it('tints each tone with its own ink (rules 1, 2, 4)', () => {
    const { rerender } = render(<Chip tone="up">IN</Chip>)
    expect(screen.getByText('IN')).toHaveClass('bg-up-tint', 'text-up')
    rerender(<Chip tone="down">OUT</Chip>)
    expect(screen.getByText('OUT')).toHaveClass('bg-down-tint', 'text-down')
    rerender(<Chip tone="warn">75%</Chip>)
    expect(screen.getByText('75%')).toHaveClass('bg-warn-tint', 'text-warn')
    rerender(<Chip>attack</Chip>)
    expect(screen.getByText('attack')).toHaveClass('text-text-muted')
    expect(screen.getByText('attack')).not.toHaveClass('bg-up-tint')
  })

  it('is 2px-cornered and small', () => {
    render(<Chip>BB</Chip>)
    expect(screen.getByText('BB')).toHaveClass('rounded-chip')
    expect(screen.getByText('BB')).toHaveClass('text-[10px]')
  })

  it('exposes a title for hover context', () => {
    render(<Chip tone="warn" title="Knock - 75% chance">75%</Chip>)
    expect(screen.getByTitle('Knock - 75% chance')).toBeInTheDocument()
  })
})
```

Create `frontend/src/kit/Bar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Bar from './Bar'

describe('Bar', () => {
  it('fills the fraction and prints the number beside it', () => {
    render(<Bar fraction={0.74} text="74%" />)
    expect(screen.getByTestId('bar-fill')).toHaveStyle({ width: '74%' })
    expect(screen.getByText('74%')).toHaveClass('tn')
  })

  it('is grey unless a direction is meant', () => {
    const { rerender } = render(<Bar fraction={0.5} />)
    expect(screen.getByTestId('bar-fill')).toHaveClass('bg-text-muted')
    rerender(<Bar fraction={0.5} tone="up" />)
    expect(screen.getByTestId('bar-fill')).toHaveClass('bg-up')
    rerender(<Bar fraction={0.5} tone="down" />)
    expect(screen.getByTestId('bar-fill')).toHaveClass('bg-down')
  })

  it('clamps to the track and draws nothing for a missing value', () => {
    const { rerender } = render(<Bar fraction={3} />)
    expect(screen.getByTestId('bar-fill')).toHaveStyle({ width: '100%' })
    rerender(<Bar fraction={null} text="—" />)
    expect(screen.getByTestId('bar-fill')).toHaveStyle({ width: '0%' })
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('places a mark at a fraction of the ceiling', () => {
    render(<Bar fraction={0.9} mark={0.6} testId="threshold" />)
    expect(screen.getByTestId('threshold-mark')).toHaveStyle({ left: '60%' })
    expect(screen.getByTestId('threshold-fill')).toBeInTheDocument()
  })

  it('has no rounded-full and no gradient', () => {
    const { container } = render(<Bar fraction={0.2} />)
    expect(container.innerHTML).not.toContain('rounded-full')
    expect(container.innerHTML).not.toContain('gradient')
  })
})
```

Create `frontend/src/kit/Callout.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Callout from './Callout'

describe('Callout', () => {
  it('is a grey note by default', () => {
    render(<Callout>Your pins are in this plan</Callout>)
    const box = screen.getByText('Your pins are in this plan').parentElement!
    expect(box).toHaveAttribute('data-tone', 'note')
    expect(box).toHaveClass('border-border', 'bg-raised')
    expect(box.querySelector('svg')).toBeNull()
  })

  it('warns in amber with an icon and passes role through', () => {
    render(<Callout tone="warn" role="alert">model has no data</Callout>)
    const box = screen.getByRole('alert')
    expect(box).toHaveClass('border-warn', 'bg-warn-tint')
    expect(box.querySelector('svg')).not.toBeNull()
    expect(box).toHaveTextContent('model has no data')
  })

  it('states an error in down ink (plan R4)', () => {
    render(<Callout tone="error" data-testid="err">no models on disk</Callout>)
    expect(screen.getByTestId('err')).toHaveClass('border-down', 'text-down')
  })
})
```

Create `frontend/src/kit/table.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { TR_CLASS, TR_SELECTED_CLASS, tdClass, thClass } from './table'

describe('the one table style', () => {
  it('right-aligns and tabularises numeric cells only', () => {
    expect(tdClass(true)).toContain('tn')
    expect(tdClass(true)).toContain('text-right')
    expect(tdClass()).not.toContain('tn')
    expect(thClass(true)).toContain('text-right')
    expect(thClass()).toContain('text-left')
  })

  it('is 32px rows on hairlines, raised on hover, accent-tinted when selected', () => {
    expect(thClass()).toContain('h-8')
    expect(tdClass()).toContain('h-8')
    expect(TR_CLASS).toContain('border-divider')
    expect(TR_CLASS).toContain('hover:bg-raised')
    expect(TR_SELECTED_CLASS).toBe('bg-accent-tint')
  })
})
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd frontend && npx vitest run src/kit/Button.test.tsx src/kit/Segmented.test.tsx src/kit/Chip.test.tsx src/kit/Bar.test.tsx src/kit/Callout.test.tsx src/kit/table.test.ts`
Expected: FAIL — cannot resolve `./Button` etc.

- [ ] **Step 4: Write the primitives**

Create `frontend/src/kit/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'

/** One height (28px), one radius, one text style; three fills (spec §5).
 *  Primary is the one place accent is a fill: the action the page is for. */
const BASE = 'inline-flex h-7 shrink-0 items-center justify-center gap-1.5 '
  + 'whitespace-nowrap rounded-ctl px-3 text-xs font-medium leading-none '
  + 'disabled:cursor-not-allowed disabled:opacity-50'

const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-white hover:opacity-90',
  secondary: 'border border-border text-text hover:bg-raised',
  ghost: 'text-text-secondary hover:text-accent-text',
}

/** The class string alone, for an element that is not a <button> — a Radix
 *  trigger, a router Link — but has to look like one. */
export function buttonClass(variant: ButtonVariant = 'secondary',
                            extra = ''): string {
  return `${BASE} ${VARIANT[variant]} ${extra}`.trim()
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

export default function Button(
  { variant = 'secondary', className = '', type = 'button', ...rest }:
  ButtonProps,
) {
  return <button type={type} className={buttonClass(variant, className)}
                 {...rest} />
}
```

Create `frontend/src/kit/Segmented.tsx`:

```tsx
import type { ReactNode } from 'react'

export interface SegmentedOption<V extends string> {
  value: V
  label: ReactNode
  title?: string
}

export interface SegmentedProps<V extends string> {
  options: ReadonlyArray<SegmentedOption<V>>
  value: V
  onChange: (next: V) => void
  /** The group's accessible name. */
  label: string
  className?: string
}

/** One segment's classes: secondary chrome, accent text on the raised
 *  surface when active (spec §5). Exported so a control that must keep its
 *  own ARIA — the board's plan tabs, the EO lens toggle — matches
 *  class-for-class. */
export function segmentClass(active: boolean): string {
  return 'h-7 whitespace-nowrap px-2.5 text-xs font-medium leading-none '
    + (active ? 'bg-raised text-accent-text'
              : 'text-text-muted hover:text-text')
}

/** A toggle group: Pitch/Table, the position filters, the theme choice.
 *  `aria-pressed` per segment rather than a radio group, because every
 *  existing test and screen reader already reads these as pressed buttons. */
export default function Segmented<V extends string>(
  { options, value, onChange, label, className = '' }: SegmentedProps<V>,
) {
  return (
    <div
      role="group"
      aria-label={label}
      className={'inline-flex divide-x divide-border overflow-hidden '
        + `rounded-ctl border border-border ${className}`}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          title={option.title}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={segmentClass(value === option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
```

Create `frontend/src/kit/Chip.tsx`:

```tsx
import type { ReactNode } from 'react'

/** up/down: a direction (rule 1). warn: doubt (rule 2). neutral: a word
 *  that is information (rule 4). There is deliberately no accent tone —
 *  a chip is never something you click (rule 3). */
export type ChipTone = 'up' | 'down' | 'warn' | 'neutral'

const TONE: Record<ChipTone, string> = {
  up: 'bg-up-tint text-up',
  down: 'bg-down-tint text-down',
  warn: 'bg-warn-tint text-warn',
  neutral: 'border border-border text-text-muted',
}

export interface ChipProps {
  children: ReactNode
  tone?: ChipTone
  title?: string
  className?: string
}

export default function Chip(
  { children, tone = 'neutral', title, className = '' }: ChipProps,
) {
  return (
    <span
      title={title}
      data-tone={tone}
      className={'inline-flex items-center rounded-chip px-1.5 py-px '
        + `text-[10px] font-semibold leading-4 ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  )
}
```

Replace `frontend/src/kit/Badge.tsx` with:

```tsx
import type { ReactNode } from 'react'
import Chip, { type ChipTone } from './Chip'

/** v14: `Badge` is a one-cycle alias of `Chip` (spec §5). The old variant
 *  names map onto tones; new code writes `<Chip tone=…>`. `info` was the
 *  blue "this is a note" badge, and blue no longer carries data (rule 3),
 *  so it lands on neutral. Availability doubt should be `warn`, which this
 *  vocabulary cannot say — one more reason the sweep migrates call sites. */
export type BadgeVariant = 'positive' | 'negative' | 'info' | 'neutral'

export const BADGE_TONE: Record<BadgeVariant, ChipTone> = {
  positive: 'up', negative: 'down', info: 'neutral', neutral: 'neutral',
}

export interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  title?: string
}

export default function Badge(
  { children, variant = 'neutral', title }: BadgeProps,
) {
  return <Chip tone={BADGE_TONE[variant]} title={title}>{children}</Chip>
}
```

Create `frontend/src/kit/Bar.tsx`:

```tsx
export type BarTone = 'up' | 'down' | 'neutral'

const FILL: Record<BarTone, string> = {
  up: 'bg-up', down: 'bg-down', neutral: 'bg-text-muted',
}

export interface BarProps {
  /** 0..1 of a known ceiling. null, undefined or NaN draws an empty track. */
  fraction: number | null | undefined
  /** Printed beside the track, tabular. Omit for a bare track. */
  text?: string
  /** Grey unless the magnitude is a direction relative to something. */
  tone?: BarTone
  /** A mark at this fraction of the ceiling — the chip threshold. */
  mark?: number
  /** Track width in px, or the full width of the parent. */
  width?: number | 'full'
  /** Prefix for the data-testids: `<testId>-fill`, `<testId>-mark`. */
  testId?: string
  'aria-label'?: string
  className?: string
}

function clamp(pct: number): number {
  return Math.min(Math.max(pct, 0), 100)
}

/**
 * The one bar (rule 7): a flat single-colour fill, 6px, no border, no
 * gradient, the number printed beside it. Allowed only where a magnitude
 * between zero and a known ceiling matters and there are several to compare
 * in one view. The track is drawn in `border` rather than `raised` so it is
 * still visible inside a hovered (raised) row (plan R8).
 */
export default function Bar({
  fraction, text, tone = 'neutral', mark, width = 56, testId = 'bar',
  'aria-label': ariaLabel, className = '',
}: BarProps) {
  const finite = typeof fraction === 'number' && Number.isFinite(fraction)
  const pct = finite ? clamp(fraction * 100) : 0
  const full = width === 'full'
  return (
    <span
      role={ariaLabel ? 'img' : undefined}
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-2 ${full ? 'w-full' : ''} `
        + className}
    >
      <span
        aria-hidden
        className={'relative block h-1.5 shrink-0 rounded-chip bg-border '
          + (full ? 'flex-1' : '')}
        style={full ? undefined : { width }}
      >
        <span
          data-testid={`${testId}-fill`}
          className={`block h-1.5 rounded-chip ${FILL[tone]}`}
          style={{ width: `${pct}%` }}
        />
        {mark !== undefined && (
          <span
            data-testid={`${testId}-mark`}
            className="absolute top-0 h-1.5 w-px bg-text"
            style={{ left: `${clamp(mark * 100)}%` }}
          />
        )}
      </span>
      {text !== undefined && <span className="tn shrink-0">{text}</span>}
    </span>
  )
}
```

Create `frontend/src/kit/Callout.tsx`:

```tsx
import { TriangleAlert } from 'lucide-react'
import type { HTMLAttributes, ReactNode } from 'react'

/** note: information (rule 4). warn: doubt — a data warning, a stale feed
 *  (rule 2), the amber strip with the icon spec §5 asks for. error: a job
 *  that failed or a save the server refused, in `down` ink — the one use of
 *  `down` that is not a direction (plan R4). */
export type CalloutTone = 'note' | 'warn' | 'error'

const TONE: Record<CalloutTone, string> = {
  note: 'border-border bg-raised text-text-secondary',
  warn: 'border-warn bg-warn-tint text-text',
  error: 'border-down bg-down-tint text-down',
}

export interface CalloutProps extends HTMLAttributes<HTMLDivElement> {
  tone?: CalloutTone
  children: ReactNode
}

export default function Callout(
  { tone = 'note', children, className = '', ...rest }: CalloutProps,
) {
  return (
    <div
      data-tone={tone}
      className={`flex gap-2 rounded-ctl border-l-2 px-3 py-2 ${TONE[tone]} `
        + className}
      {...rest}
    >
      {tone === 'warn' && (
        <TriangleAlert aria-hidden size={14}
                       className="mt-0.5 shrink-0 text-warn" />
      )}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
```

(If `tsc` reports no export named `TriangleAlert`, the installed lucide names it `AlertTriangle`; import that.)

Create `frontend/src/kit/table.ts`:

```ts
/**
 * The one table style (spec §5): 10px uppercase headers on the raised band,
 * tabular numerals right-aligned, 32px rows on hairline dividers, hover to
 * raised, the selected row accent-tinted. `DataTable` uses these, and every
 * hand-rolled table (the moves card, the ladder, sensitivity, the standings,
 * the modal's components) imports them so it matches class-for-class.
 */
export const TABLE_CLASS = 'w-full border-collapse'
export const THEAD_CLASS = 'bg-raised'
const TH = 'label h-8 whitespace-nowrap border-b border-border px-2.5 '
  + 'align-middle'
const TD = 'h-8 px-2.5 py-1.5 align-middle'

export function thClass(numeric = false): string {
  return `${TH} ${numeric ? 'text-right' : 'text-left'}`
}

export function tdClass(numeric = false): string {
  return numeric ? `${TD} tn text-right` : TD
}

export const TR_CLASS = 'border-b border-divider hover:bg-raised'
export const TR_SELECTED_CLASS = 'bg-accent-tint'
/** The row an expand control opened: raised, so it reads as the row's own. */
export const TR_EXPANDED_CLASS = 'border-b border-divider bg-raised'
```

Create `frontend/src/kit/tabs.ts`:

```ts
/** Radix tab strips (spec §5): 13px muted, the active one in text colour
 *  with a 2px accent underline. `overflow-x-auto` so a trigger scrolls out
 *  of the strip rather than wrapping at 390px (responsive.test.tsx). */
export const TAB_LIST_CLASS = 'mb-4 flex overflow-x-auto border-b border-border'
export const TAB_CLASS = '-mb-px shrink-0 whitespace-nowrap border-b-2 '
  + 'border-transparent px-3 py-2 text-[13px] text-text-muted hover:text-text '
  + 'data-[state=active]:border-accent data-[state=active]:text-text'
```

Create `frontend/src/kit/field.ts`:

```ts
/** Inputs and selects (spec §5): input surface, hairline, 3px radius,
 *  accent border on focus, 28px tall like a button. */
export const INPUT_CLASS = 'h-7 rounded-ctl border border-border bg-input px-2 '
  + 'text-[13px] text-text placeholder:text-text-faint focus:border-accent '
  + 'focus:outline-none disabled:opacity-50'
```

Create `frontend/src/kit/series.ts`:

```ts
/**
 * The chart palette (spec §8, plan R6). Blue is chrome (rule 3) and green/
 * rust are directions (rule 1), so a series that is merely "the second
 * rival" is grey: text, muted, secondary, faint, with the third and fourth
 * dashed so four lines stay tellable. Whoever draws "you" draws them first.
 */
export const SERIES_COLOURS = [
  'var(--color-text)', 'var(--color-text-muted)',
  'var(--color-text-secondary)', 'var(--color-text-faint)',
]

export const SERIES_DASH: Array<string | undefined> = [
  undefined, undefined, '4 3', '4 3',
]
```

Create `frontend/src/kit/StatRow.tsx`:

```tsx
import type { ReactNode } from 'react'

export interface StatRowProps {
  children: ReactNode
  /** Tiles per row at `md` and up; two below it. */
  cols?: 3 | 4
  className?: string
}

/** The hairline grid the stat tiles sit in (mockup A): a 1px `border` gap
 *  between tiles that stays a hairline however the tiles wrap, and no card
 *  box around any of them. */
export default function StatRow(
  { children, cols = 4, className = 'mb-4' }: StatRowProps,
) {
  return (
    <div
      data-testid="stat-row"
      className={'grid grid-cols-2 gap-px border border-border bg-border '
        + `${cols === 4 ? 'md:grid-cols-4' : 'md:grid-cols-3'} `
        + `[&>*]:bg-base ${className}`}
    >
      {children}
    </div>
  )
}
```

- [ ] **Step 5: Retone the formatters and the difficulty scale**

In `frontend/src/kit/format.ts` replace the `TONE_CLASS` block with:

```ts
export const TONE_CLASS: Record<Tone, string> = {
  positive: 'text-up',
  negative: 'text-down',
  neutral: 'text-text-muted',
}

/** Rule 6: a tint may sit behind a *cell* that carries a direction. */
export const TONE_TINT_CLASS: Record<Tone, string> = {
  positive: 'bg-up-tint text-up',
  negative: 'bg-down-tint text-down',
  neutral: 'text-text-muted',
}
```

Append to `frontend/src/kit/format.test.ts`:

```ts
describe('tone classes (v14)', () => {
  it('speak up/down, never sage/rust', () => {
    expect(TONE_CLASS.positive).toBe('text-up')
    expect(TONE_CLASS.negative).toBe('text-down')
    expect(TONE_TINT_CLASS.positive).toContain('bg-up-tint')
    expect(TONE_TINT_CLASS.neutral).not.toContain('bg-')
  })
})
```

(Add `TONE_CLASS, TONE_TINT_CLASS` to that file's import from `./format`.)

Replace `frontend/src/kit/scale.ts` with:

```ts
import type { ChipTone } from './Chip'

/**
 * Fixture difficulty, on the meaning scale (rule 1: easy/hard is a
 * direction relative to the player). The server sends [0, 1]; the chip is
 * `up` below 0.35, `down` above 0.65, grey between — three words the eye
 * can tell apart at 10px, rather than a continuous ramp nobody could read.
 */
export function difficultyTone(score: number | null | undefined): ChipTone {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 'neutral'
  if (score < 0.35) return 'up'
  if (score > 0.65) return 'down'
  return 'neutral'
}

/** Pre-v14 continuous ramp. Kept until the sweep has moved every fixture
 *  cell onto `difficultyTone` (Tasks 7, 10, 11); deleted in Task 12. */
export function difficultyBackground(score: number): string {
  const eased = Math.min(Math.max(score, 0), 1)
  return eased < 0.5
    ? `color-mix(in srgb, var(--color-up) ${
        Math.round((0.5 - eased) * 160)}%, var(--color-base))`
    : `color-mix(in srgb, var(--color-down) ${
        Math.round((eased - 0.5) * 160)}%, var(--color-base))`
}
```

Append to `frontend/src/kit/scale.test.ts` (import `difficultyTone` beside `difficultyBackground`):

```ts
describe('difficultyTone', () => {
  it('is up below .35, down above .65, grey between and for no rating', () => {
    expect(difficultyTone(0.1)).toBe('up')
    expect(difficultyTone(0.5)).toBe('neutral')
    expect(difficultyTone(0.9)).toBe('down')
    expect(difficultyTone(null)).toBe('neutral')
    expect(difficultyTone(NaN)).toBe('neutral')
  })
})
```

- [ ] **Step 6: Export from the barrel and update the tests that pinned old names**

Add to `frontend/src/kit/index.ts`:

```ts
export { default as Button, buttonClass } from './Button'
export type { ButtonProps, ButtonVariant } from './Button'
export { default as Segmented, segmentClass } from './Segmented'
export type { SegmentedOption, SegmentedProps } from './Segmented'
export { default as Chip } from './Chip'
export type { ChipProps, ChipTone } from './Chip'
export { default as Bar } from './Bar'
export type { BarProps, BarTone } from './Bar'
export { default as Callout } from './Callout'
export type { CalloutProps, CalloutTone } from './Callout'
export { default as StatRow } from './StatRow'
export type { StatRowProps } from './StatRow'
export { default as Section } from './Card'
export {
  TABLE_CLASS, THEAD_CLASS, TR_CLASS, TR_EXPANDED_CLASS, TR_SELECTED_CLASS,
  tdClass, thClass,
} from './table'
export { TAB_CLASS, TAB_LIST_CLASS } from './tabs'
export { INPUT_CLASS } from './field'
export { SERIES_COLOURS, SERIES_DASH } from './series'
export { difficultyTone } from './scale'
export { TONE_TINT_CLASS } from './format'
```

In `frontend/src/kit/index.test.ts` extend the first list with `'Button', 'Segmented', 'Chip', 'Bar', 'Callout', 'StatRow', 'Section'` and add:

```ts
  it('exports the shared class strings and the chart palette', () => {
    expect(kit.TAB_CLASS).toContain('data-[state=active]:border-accent')
    expect(kit.INPUT_CLASS).toContain('bg-input')
    expect(kit.SERIES_COLOURS).toHaveLength(4)
    expect(kit.thClass(true)).toContain('text-right')
  })
```

In `frontend/src/kit/Badge.test.tsx` replace the first test's expectations: `'C'` → `toHaveClass('text-up')`, `'Doubt'` → `toHaveClass('text-down')`, `'Pens'` → `toHaveClass('text-text-muted')` (the info variant is neutral now), `'WC'` unchanged.

In `frontend/src/kit/Stat.test.tsx` the delta test: `text-sage` → `text-up`, `text-rust` → `text-down`. Leave the `num` assertion for Task 3.

- [ ] **Step 7: Run the suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6`
Expected: all green — the new files' tests, the retargeted Badge/Stat tests, and every hub test (hub components still emit `text-sage` literals themselves; only `TONE_CLASS` consumers changed, and `JournalTab.test`'s `+7`/`-3` assertions use TONE_CLASS through `JournalTab`… so **update** `src/hubs/model/JournalTab.test.tsx:59-60` to `text-up`/`text-down`, `src/hubs/this-week/LadderCard.test.tsx` if it asserts a tone on "vs bank" (it does not), and `src/hubs/model/ReviewTab.test.tsx` if it asserts `text-sage` on a delta (check with `grep -n "text-sage\|text-rust" src/hubs/model/ReviewTab.test.tsx src/hubs/this-week/WhyPanel.test.tsx src/hubs/planning/PlanDiffTable.test.tsx src/hubs/model/SeasonTab.test.tsx` and retarget any hit). The `JournalTab.test.tsx:82` `late run` badge assertion stays `text-rust`-free? It asserts `text-rust` on a `Badge variant="negative"` → now `text-down`; update it.

- [ ] **Step 8: Commit**

```bash
cd /Users/anugnana/Library/Projects/FPL
git add frontend/package.json frontend/package-lock.json \
  frontend/src/kit/Button.tsx frontend/src/kit/Button.test.tsx \
  frontend/src/kit/Segmented.tsx frontend/src/kit/Segmented.test.tsx \
  frontend/src/kit/Chip.tsx frontend/src/kit/Chip.test.tsx \
  frontend/src/kit/Bar.tsx frontend/src/kit/Bar.test.tsx \
  frontend/src/kit/Callout.tsx frontend/src/kit/Callout.test.tsx \
  frontend/src/kit/table.ts frontend/src/kit/table.test.ts \
  frontend/src/kit/tabs.ts frontend/src/kit/field.ts frontend/src/kit/series.ts \
  frontend/src/kit/StatRow.tsx frontend/src/kit/Badge.tsx frontend/src/kit/Badge.test.tsx \
  frontend/src/kit/format.ts frontend/src/kit/format.test.ts \
  frontend/src/kit/scale.ts frontend/src/kit/scale.test.ts \
  frontend/src/kit/index.ts frontend/src/kit/index.test.ts frontend/src/kit/Stat.test.tsx \
  frontend/src/hubs/model/JournalTab.test.tsx
git commit -m "feat(v14): kit primitives — Button, Segmented, Chip, Bar, Callout, the table/tab/input classes, the grey chart palette

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

(Add any other test file Step 7 made you retarget to the `git add` list.)

---
## Task 3 — restyle the kit, part A: Section, Stat, header, empty, skeleton, toast, job log, job button

**Files:**
- Modify: `frontend/src/kit/Card.tsx`, `Card.test.tsx`, `Stat.tsx`, `Stat.test.tsx`, `PageHeader.tsx`, `EmptyState.tsx`, `Skeleton.tsx`, `Toast.tsx`, `Toast.test.tsx` (only if it asserts `shadow-lg`/`border-rust`), `JobLog.tsx`, `JobLog.test.tsx`, `JobButton.tsx`

- [ ] **Step 1: Retarget the tests that pin the old rendering**

`frontend/src/kit/Card.test.tsx`, first test becomes:

```tsx
  it('renders its children under a label band, with no card box', () => {
    const { container } = render(<Card title="Squad"><p>inside</p></Card>)
    expect(screen.getByText('inside')).toBeInTheDocument()
    const root = container.firstChild as HTMLElement
    expect(root).toHaveAttribute('data-kit', 'section')
    expect(root.className).not.toMatch(/bg-card|border-border|rounded/)
    expect(root.querySelector('header')).toHaveClass('border-b')
  })
```

Add to the same file:

```tsx
  it('is also exported as Section (v14)', async () => {
    const kit = await import('./index')
    expect(kit.Section).toBe(kit.Card)
  })
```

`frontend/src/kit/Stat.test.tsx` — replace the whole file:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Bar from './Bar'
import Stat from './Stat'

describe('Stat', () => {
  it('renders label and value, the value tabular at 22px', () => {
    render(<Stat label="Expected XI" value="61.5" />)
    expect(screen.getByText('Expected XI')).toHaveClass('label')
    expect(screen.getByText('61.5')).toHaveClass('tn')
    expect(screen.getByText('61.5').parentElement).toHaveClass('text-[22px]')
  })

  it('prints the unit beside the value and one context line under it', () => {
    render(<Stat label="Expected XI" value="61.5" unit="pts"
                 context="raw model points" />)
    expect(screen.getByText('pts')).toHaveClass('text-text-muted')
    expect(screen.getByText('raw model points')).toHaveClass('text-xs')
  })

  it('takes a name as a value like any other', () => {
    render(<Stat label="Captain" value="Guéhi" context="55% of sims · vice Semenyo" />)
    expect(screen.getByText('Guéhi')).toHaveClass('tn')
  })

  it('mounts a meter under the context line', () => {
    render(<Stat label="Next chip" value="BB" unit="GW5"
                 meter={<Bar fraction={0.9} mark={0.5} testId="threshold" />} />)
    expect(screen.getByTestId('threshold-fill')).toBeInTheDocument()
  })

  it('colours a positive delta up and a negative delta down', () => {
    const { rerender } = render(
      <Stat label="Gap" value="12" delta={2.4} deltaLabel="vs last run" />,
    )
    expect(screen.getByTestId('stat-delta')).toHaveClass('text-up')
    expect(screen.getByTestId('stat-delta')).toHaveTextContent('+2.4')
    rerender(<Stat label="Gap" value="12" delta={-2.4} deltaLabel="vs last run" />)
    expect(screen.getByTestId('stat-delta')).toHaveClass('text-down')
  })

  it('omits the delta line when there is no delta', () => {
    render(<Stat label="Gap" value="12" />)
    expect(screen.queryByTestId('stat-delta')).toBeNull()
  })

  it('renders a missing value as an em dash rather than NaN', () => {
    render(<Stat label="Gap" value={NaN} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('draws no card box of its own', () => {
    const { container } = render(<Stat label="Gap" value="12" />)
    expect((container.firstChild as HTMLElement).className)
      .not.toMatch(/border|rounded|bg-card/)
  })
})
```

`frontend/src/kit/JobLog.test.tsx:15`: `toHaveClass('num')` → `toHaveClass('font-mono')`.

Check `frontend/src/kit/Toast.test.tsx` with `grep -n "shadow\|border-rust\|rounded" src/kit/Toast.test.tsx`; retarget any hit to `border-down` / no `rounded-card`.

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/kit/Card.test.tsx src/kit/Stat.test.tsx src/kit/JobLog.test.tsx`
Expected: FAIL on the new assertions.

- [ ] **Step 3: Write the components**

Replace `frontend/src/kit/Card.tsx` with:

```tsx
import type { ReactNode } from 'react'

/**
 * A section of the page (spec §5): a label band with a hairline under it and
 * an optional right-aligned action; the content sits on the page surface.
 * No border box, no fill, no radius — the ledger separates sections with
 * rules, not cards.
 *
 * Still named `Card` (and also exported as `Section`) because 35 files
 * compose it under that name and the spec allows the alias for one cycle.
 *
 * `titleSize` exists because a section is used for two different things: a
 * region of a page, whose title is chrome and belongs in the label voice,
 * and a panel *about* something — a player, in ComparePanel — whose title
 * is the content and has to read as such. The title is an `h3` regardless:
 * several sections side by side would otherwise emit a row of sibling `h2`s.
 */
export interface CardProps {
  title?: string
  /** Rich heading content; `title` stays the string form of the same thing. */
  heading?: ReactNode
  titleSize?: 'sm' | 'lg'
  action?: ReactNode
  children: ReactNode
  className?: string
}

const TITLE_CLASS = {
  sm: 'label',
  lg: 'text-lg font-semibold text-text',
} as const

export default function Card({
  title, heading, titleSize = 'sm', action, children, className,
}: CardProps) {
  const shown = heading ?? title
  return (
    <section data-kit="section" className={`min-w-0 ${className ?? ''}`}>
      {(shown || action) && (
        <header className="mb-3 flex min-h-8 items-center justify-between
                           gap-3 border-b border-border pb-1.5">
          {shown && <h3 className={TITLE_CLASS[titleSize]}>{shown}</h3>}
          {action}
        </header>
      )}
      <div>{children}</div>
    </section>
  )
}
```

Replace `frontend/src/kit/Stat.tsx` with:

```tsx
import type { ReactNode } from 'react'
import { TONE_CLASS, fmtDelta, fmtNum, toneOf } from './format'

/**
 * The one stat tile shape (spec §5): label; value at 22px with the unit in
 * 12px muted beside it; one 12px muted context line; an optional meter
 * (rule 7 — the chip threshold only). A name (the captain) is a value like
 * any other. It draws no box: `StatRow` puts the hairlines between tiles.
 */
export interface StatProps {
  label: string
  /** A pre-formatted string, or a raw number that goes through fmtNum. */
  value: ReactNode | number
  unit?: ReactNode
  context?: ReactNode
  meter?: ReactNode
  /** Pre-v14 shape, still honoured: rendered as a toned context line. */
  delta?: number | null
  deltaLabel?: string
}

export default function Stat(
  { label, value, unit, context, meter, delta, deltaLabel }: StatProps,
) {
  const shown = typeof value === 'number' ? fmtNum(value) : value
  return (
    <div className="min-w-0 px-4 py-3">
      <p className="label">{label}</p>
      <p className="mt-1 flex items-baseline gap-1.5 text-[22px] font-semibold
                    leading-tight text-text">
        <span className="tn truncate">{shown}</span>
        {unit !== undefined && unit !== null && (
          <span className="text-xs font-normal text-text-muted">{unit}</span>
        )}
      </p>
      {context !== undefined && context !== null && (
        <p className="mt-0.5 text-xs text-text-muted">{context}</p>
      )}
      {delta !== undefined && delta !== null && (
        <p data-testid="stat-delta"
           className={`tn mt-0.5 text-xs ${TONE_CLASS[toneOf(delta)]}`}>
          {fmtDelta(delta)}
          {deltaLabel ? <span className="ml-1 text-text-faint">{deltaLabel}</span> : null}
        </p>
      )}
      {meter && <div className="mt-2">{meter}</div>}
    </div>
  )
}
```

Replace `frontend/src/kit/PageHeader.tsx` with:

```tsx
import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: string
  /** Deadline, staleness, run stamp — whatever situates the page. */
  context?: ReactNode
  action?: ReactNode
}

/** Title 18px, context line muted, actions right (spec §5). */
export default function PageHeader({ title, context, action }: PageHeaderProps) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold leading-tight text-text">{title}</h1>
        {context !== undefined && context !== null && (
          <p data-testid="page-context" className="mt-1 text-text-muted">
            {context}
          </p>
        )}
      </div>
      {action}
    </header>
  )
}
```

Replace `frontend/src/kit/EmptyState.tsx` with:

```tsx
import { CircleDashed } from 'lucide-react'
import Button from './Button'

export interface EmptyStateProps {
  title: string
  detail: string
  /** The exact button label or shell command that populates this view. */
  action: string
  /** Present when the action is something the UI itself can do. */
  onAction?: () => void
}

export default function EmptyState(
  { title, detail, action, onAction }: EmptyStateProps,
) {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center gap-2 border-y border-border
                 px-6 py-10 text-center"
    >
      <CircleDashed aria-hidden size={20} className="text-text-faint" />
      <p className="text-[15px] font-medium text-text">{title}</p>
      <p className="max-w-md text-text-muted">{detail}</p>
      {onAction
        ? <Button className="mt-2" onClick={onAction}>{action}</Button>
        : (
          <code className="tn mt-2 rounded-ctl border border-border bg-input
                           px-2 py-1 text-text-secondary">
            {action}
          </code>
          )}
    </div>
  )
}
```

In `frontend/src/kit/Skeleton.tsx` change the bar class to `"block h-3 animate-pulse rounded-chip bg-raised"`. Nothing else.

In `frontend/src/kit/Toast.tsx` replace the per-toast `className` with:

```tsx
          className={'pointer-events-auto max-w-md rounded-ctl border '
            + 'bg-raised px-3 py-2 '
            + (t.tone === 'negative'
              ? 'border-down text-down' : 'border-border text-text')}
```

Replace `frontend/src/kit/JobLog.tsx`'s returned JSX with:

```tsx
  return (
    <div className="mt-3">
      {error && (
        <Callout tone="error" role="alert" className="mb-2">{error}</Callout>
      )}
      {shown.length > 0 && (
        <pre
          ref={box}
          data-testid="job-log-lines"
          className="tn max-h-56 overflow-auto rounded-ctl border border-border
                     bg-input p-3 font-mono text-xs text-text-secondary"
        >
          {shown.map((line, i) => <div key={`${i}-${line}`}>{line}</div>)}
        </pre>
      )}
    </div>
  )
```

with `import Callout from './Callout'` at the top. (This file and the planner trace are the only two places `font-mono` is allowed — spec §3.)

In `frontend/src/kit/JobButton.tsx`: add `import Button, { type ButtonVariant } from './Button'`; add to `JobButtonProps`:

```ts
  /** `primary` for the action the page is for (Run advise); secondary
   *  otherwise. */
  variant?: ButtonVariant
```

destructure `variant = 'secondary'` and replace the `<button …>` with:

```tsx
      <Button variant={variant} disabled={busy} onClick={() => job.start(kind)}>
        {busy ? `${label ?? JOB_KIND_LABEL[kind]} — running…`
              : label ?? JOB_KIND_LABEL[kind]}
      </Button>
```

- [ ] **Step 4: Run the suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6`
Expected: green. A hub test that asserted `bg-card` on a Card root would fail — none does (`grep -rn "bg-card" src --include='*.test.tsx'` is only `Card.test.tsx`, retargeted above).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/kit/Card.tsx frontend/src/kit/Card.test.tsx frontend/src/kit/Stat.tsx \
  frontend/src/kit/Stat.test.tsx frontend/src/kit/PageHeader.tsx frontend/src/kit/EmptyState.tsx \
  frontend/src/kit/Skeleton.tsx frontend/src/kit/Toast.tsx frontend/src/kit/Toast.test.tsx \
  frontend/src/kit/JobLog.tsx frontend/src/kit/JobLog.test.tsx frontend/src/kit/JobButton.tsx
git commit -m "feat(v14): kit part A — Section instead of Card, the one Stat shape, header, empty, skeleton, toast, job log and button on tokens

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---

## Task 4 — restyle the kit, part B: DataTable, modal, strip, theme toggle, badges, bars

**Files:**
- Modify: `frontend/src/kit/DataTable.tsx`, `DataTable.test.tsx`, `ExplainModal.tsx`, `FreshnessStrip.tsx`, `FreshnessStrip.test.tsx`, `ThemeToggle.tsx`, `PosBadge.tsx`, `PlayerName.tsx`, `ThresholdBar.tsx`, `ThresholdBar.test.tsx`, `Sparkline.tsx`

- [ ] **Step 1: Retarget the tests**

`DataTable.test.tsx:24`: `toHaveClass('num')` → `toHaveClass('tn')`. Add:

```tsx
  it('tints the selected row accent and raises the header band', () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.code}
                 collapse={false} selected={(r) => r.code === 2} />)
    expect(container.querySelector('thead')).toHaveClass('bg-raised')
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[1]).toHaveClass('bg-accent-tint')
    expect(rows[0]).not.toHaveClass('bg-accent-tint')
  })
```

`FreshnessStrip.test.tsx`, the colouring block becomes:

```tsx
  it('is grey under a day, amber under three, down beyond (plan R2)', () => {
    expect(tone(0.5)).toBe('text-text-muted')
    expect(tone(23.9)).toBe('text-text-muted')
    expect(tone(24)).toBe('text-warn')
    expect(tone(71.9)).toBe('text-warn')
    expect(tone(72)).toBe('text-down')
  })
```

`ThresholdBar.test.tsx`: `bg-sage` → `bg-up`, `bg-rust` → `bg-down`; the test ids stay `threshold-fill`.

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/kit/DataTable.test.tsx src/kit/FreshnessStrip.test.tsx src/kit/ThresholdBar.test.tsx`
Expected: FAIL.

- [ ] **Step 3: DataTable**

In `frontend/src/kit/DataTable.tsx`: add `import { buttonClass } from './Button'` and `import { TABLE_CLASS, THEAD_CLASS, TR_CLASS, TR_EXPANDED_CLASS, TR_SELECTED_CLASS, tdClass, thClass } from './table'`. Add to `DataTableProps<T>`:

```ts
  /** The row to draw accent-tinted — the one the reader has chosen. */
  selected?: (row: T) => boolean
```

and destructure it. Then replace the two render branches:

```tsx
  if (cards) {
    const primary = columns.filter((c) => c.primary).slice(0, 3)
    const rest = columns.filter((c) => !primary.includes(c))
    return (
      <div className="flex flex-col gap-2">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger className={buttonClass('secondary', 'self-start')}>
            Sort
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="rounded-ctl border border-border
              bg-raised p-1 text-text-secondary">
              {columns.map((column) => (
                <DropdownMenu.Item
                  key={column.key}
                  onSelect={() => toggleSort(column.key)}
                  className="cursor-pointer rounded-chip px-2 py-1 outline-none
                             data-[highlighted]:bg-base data-[highlighted]:text-text"
                >
                  {column.header}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        {sorted.map((row) => {
          const key = String(rowKey(row))
          const isOpen = open.has(key)
          return (
            <div key={key} data-testid={`row-card-${key}`}
                 className={'rounded-ctl border border-border p-3 '
                   + (selected?.(row) ? TR_SELECTED_CLASS : 'bg-base')}>
              <div className="flex items-baseline justify-between gap-2">
                {primary.map((column) => (
                  <span key={column.key}
                        className={column.numeric ? 'tn text-text' : 'text-text'}>
                    {column.render ? column.render(row) : column.value(row)}
                  </span>
                ))}
              </div>
              <button type="button" onClick={() => toggleOpen(key)}
                      className="mt-2 text-text-muted hover:text-accent-text">
                {isOpen ? 'Less' : 'More'}
              </button>
              {isOpen && (
                <dl className="mt-2 grid grid-cols-2 gap-1">
                  {rest.map((column) => (
                    <div key={column.key} className="contents">
                      <dt className="label">{column.header}</dt>
                      <dd className={column.numeric ? 'tn text-text' : 'text-text'}>
                        {column.render ? column.render(row) : column.value(row)}
                      </dd>
                    </div>
                  ))}
                  {expand && <div className="col-span-2">{expand(row)}</div>}
                </dl>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className={TABLE_CLASS}>
        <thead className={`sticky top-0 ${THEAD_CLASS}`}>
          <tr>
            {expand && <th className={`${thClass()} w-8`} />}
            {columns.map((column) => (
              <th key={column.key} className={thClass(column.numeric)}>
                <button type="button" onClick={() => toggleSort(column.key)}
                        className="label hover:text-text">
                  {column.header}
                  {sortKey === column.key ? (desc ? ' ▾' : ' ▴') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const key = String(rowKey(row))
            const isOpen = open.has(key)
            return [
              <tr key={key}
                  className={`${TR_CLASS} ${selected?.(row) ? TR_SELECTED_CLASS : ''}`}>
                {expand && (
                  <td className={tdClass()}>
                    <button type="button" onClick={() => toggleOpen(key)}
                            aria-label={`expand ${label(row)}`}
                            className="text-text-muted hover:text-accent-text">
                      {isOpen ? '▾' : '▸'}
                    </button>
                  </td>
                )}
                {columns.map((column) => (
                  <td key={column.key}
                      className={`${tdClass(column.numeric)} text-text`}>
                    {column.render ? column.render(row) : column.value(row)}
                  </td>
                ))}
              </tr>,
              isOpen && expand
                ? (
                  <tr key={`${key}-expand`} className={TR_EXPANDED_CLASS}>
                    <td colSpan={columns.length + 1} className="px-2.5 py-3">
                      {expand(row)}
                    </td>
                  </tr>
                  )
                : null,
            ]
          })}
        </tbody>
      </table>
    </div>
  )
```

Update the `Column.numeric` doc comment to `/** Right-aligned, tabular figures. */`.

- [ ] **Step 4: ExplainModal**

In `frontend/src/kit/ExplainModal.tsx`:
- imports: replace `Badge` with `Chip`, add `Bar`, `Button`, `Callout`, and `{ TABLE_CLASS, TR_CLASS, tdClass }` from `./table`.
- delete `TermBar`; the components table body becomes:

```tsx
                      {fixture.components.map((component) => (
                        <tr key={component.label} className={TR_CLASS}>
                          <td className={`${tdClass()} text-text-secondary`}>
                            {component.label}
                          </td>
                          <td className={`${tdClass(true)} w-16 text-text`}>
                            {fmtNum(component.points)}
                          </td>
                          <td className={`${tdClass()} w-1/2`}>
                            {/* Against a fixed 12-point scale so bars compare
                                between two players, not only within one. */}
                            <Bar width="full"
                                 fraction={Math.abs(component.points) / 12}
                                 tone={component.points < 0 ? 'down' : 'up'} />
                          </td>
                        </tr>
                      ))}
```

  and the `<table className="w-full">` above it becomes `<table className={TABLE_CLASS}>`.
- the dialog frame: `"w-full max-w-2xl rounded-card border border-border bg-card"` → `"w-full max-w-2xl rounded-ctl border border-border bg-base"`; the photo's class → `"rounded-ctl border border-border bg-raised"`; the Close `<button>` → `<Button ref={closeRef} variant="ghost" onClick={onClose}>Close</Button>` — `Button` does not forward refs, so instead keep the `<button ref={closeRef} …>` and give it `className={buttonClass('ghost')}` (import `buttonClass`).
- the double-gameweek `<p key={gw} className="num rounded-card border-l-2 border-info …">` → `<Callout key={gw} className="tn">GW{gw} total: … fixtures</Callout>`.
- next-fixture `<li>` → `<li key=…><Chip>… GW{fixture.gw} {home ? 'vs' : 'at'} {opponent}</Chip></li>` (the `<span className="num">` inside becomes `<span className="tn">`).
- `<Badge variant="info" …>manual</Badge>` → `<Chip title=…>manual</Chip>`.
- every remaining `className="num …"` → `"tn …"`; `text-rust` → `text-down`.

- [ ] **Step 5: The rest of part B**

`FreshnessStrip.tsx` — `tone()`:

```ts
export function tone(age: number | null): string {
  if (age === null) return 'text-text-faint'
  if (age < 24) return 'text-text-muted'
  if (age < 72) return 'text-warn'
  return 'text-down'
}
```

and the strip's class `text-xs` → `text-[11px]`. Update the doc comment above `tone` to: "Grey under a day (information), amber under three (doubt, rule 2), down beyond (behind where it should be, rule 1), faint for never."

`ThemeToggle.tsx` — replace the whole file:

```tsx
import { Monitor, Moon, Sun } from 'lucide-react'
import Segmented from './Segmented'
import { THEMES, type Theme, useTheme } from './useTheme'

const LABEL: Record<Theme, string> = {
  system: 'System', dark: 'Dark', light: 'Light',
}

const ICON: Record<Theme, typeof Monitor> = {
  system: Monitor, dark: Moon, light: Sun,
}

export interface ThemeToggleProps {
  /** The tab-bar form: one icon-only button that cycles the three states. */
  compact?: boolean
}

/**
 * The theme control, in the two shapes the shell has room for: a segmented
 * row in the sidebar footer, one cycling icon button in the phone's bottom
 * bar, its state carried by the aria-label.
 */
export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const [theme, choose] = useTheme()

  if (compact) {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]
    const Icon = ICON[theme]
    return (
      <button
        type="button"
        aria-label={`Theme: ${theme}`}
        onClick={() => choose(next)}
        className="flex flex-col items-center gap-0.5 px-3 py-2 text-[11px]
                   text-text-muted hover:text-text"
      >
        <Icon aria-hidden size={16} />
      </button>
    )
  }

  return (
    <Segmented
      label="Theme"
      value={theme}
      onChange={choose}
      className="w-full [&>button]:flex-1"
      options={THEMES.map((option) => ({ value: option, label: LABEL[option] }))}
    />
  )
}
```

`PosBadge.tsx`: the dot's class → `` `inline-block h-1.5 w-1.5 shrink-0 rounded-chip ${className ?? ''}` ``; the label's class → `` `tn text-[10px] font-semibold tracking-[0.06em] ${colour ? '' : 'text-text-muted'} ${className ?? ''}` ``.

`PlayerName.tsx`: the button class `"text-text hover:underline"` → `"text-text hover:text-accent-text"`.

`ThresholdBar.tsx` — replace the whole file:

```tsx
import Bar from './Bar'
import { fmtNum } from './format'

export interface ThresholdBarProps {
  label: string
  value: number | null | undefined
  threshold: number
  /** Bar full scale; defaults to twice the threshold. */
  max?: number
}

/** The chip meter: the one bar allowed inside a stat tile (rule 7). Over the
 *  threshold is `up`, under it `down` — a direction relative to θ. */
export default function ThresholdBar(
  { label, value, threshold, max }: ThresholdBarProps,
) {
  const scale = max ?? Math.max(threshold * 2, 1)
  const finite = typeof value === 'number' && Number.isFinite(value)
  const over = finite && value >= threshold
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="label">{label}</span>
        <span className="tn text-text">{finite ? fmtNum(value) : '—'}</span>
      </div>
      <div className="mt-1">
        <Bar width="full" testId="threshold"
             fraction={finite ? value / scale : null}
             mark={Math.min(threshold / scale, 1)}
             tone={over ? 'up' : 'down'} />
      </div>
      <p className="tn mt-1 text-xs text-text-faint">θ {fmtNum(threshold)}</p>
    </div>
  )
}
```

`Sparkline.tsx`: `'var(--color-sage)' : 'var(--color-rust)'` → `'var(--color-up)' : 'var(--color-down)'`.

- [ ] **Step 6: Run the suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6`
Expected: green. `ThemeToggle.test` still passes (group named Theme, three pressed buttons whose `textContent` is the bare label). `AppShell.test` still finds the group.

- [ ] **Step 7: Commit, build, capture the first gate**

```bash
git add frontend/src/kit/DataTable.tsx frontend/src/kit/DataTable.test.tsx frontend/src/kit/ExplainModal.tsx \
  frontend/src/kit/FreshnessStrip.tsx frontend/src/kit/FreshnessStrip.test.tsx frontend/src/kit/ThemeToggle.tsx \
  frontend/src/kit/PosBadge.tsx frontend/src/kit/PlayerName.tsx frontend/src/kit/ThresholdBar.tsx \
  frontend/src/kit/ThresholdBar.test.tsx frontend/src/kit/Sparkline.tsx
git commit -m "feat(v14): kit part B — DataTable on the one table style, modal on hairlines, strip tones, segmented theme toggle, bars on tokens

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
cd frontend && npm run build 2>&1 | tail -2 && cd ..
lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || (uv run gaffer ui --no-open-browser --port 8927 &)
frontend/scripts/shots.sh kit
```

Look at all twelve PNGs with the Read tool. Report what you see, plainly: what already reads as the ledger and what still shouts (expected at this stage: the pitch is still bright green, the nav still has glyphs, hubs still carry `rounded-card` boxes that now render as 3px-radius hairline boxes). 🛑 **STOP: the orchestrator shows these to the user before Task 5.**

---
## Task 5 — rework 4: the nav

**Files:**
- Modify: `frontend/src/kit/AppShell.tsx`, `AppShell.test.tsx`

- [ ] **Step 1: Add the failing assertions**

Append to `frontend/src/kit/AppShell.test.tsx`:

```tsx
  it('draws an icon, not a glyph character, beside every hub (v14)', () => {
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    for (const label of ['This Week', 'Planning', 'Players', 'League', 'Live',
      'Model']) {
      const link = screen.getByRole('link', { name: label })
      expect(link.querySelector('svg')).not.toBeNull()
      expect(link.textContent).toBe(label)
    }
  })

  it('marks the active hub in accent with a left bar, never a white card', () => {
    stubMatchMedia(false)
    render(
      <MemoryRouter initialEntries={['/planning']}>
        <AppShell><p>page</p></AppShell>
      </MemoryRouter>,
    )
    const active = screen.getByRole('link', { name: 'Planning' })
    expect(active).toHaveClass('text-accent-text', 'border-accent')
    expect(active.className).not.toMatch(/bg-card|rounded-card/)
    expect(screen.getByRole('link', { name: 'Players' }))
      .toHaveClass('border-transparent')
  })
```

- [ ] **Step 2: Run to see them fail**

Run: `cd frontend && npx vitest run src/kit/AppShell.test.tsx` — Expected: FAIL (no svg; `bg-card`).

- [ ] **Step 3: Rewrite the shell**

Replace `frontend/src/kit/AppShell.tsx` with:

```tsx
import {
  Activity, CalendarCheck, type LucideIcon, Radio, Route, Trophy, Users,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import FreshnessStrip from './FreshnessStrip'
import ThemeToggle from './ThemeToggle'
import ToastOutlet from './Toast'
import { useIsMobile } from './useMediaQuery'

/** The six hubs, in the order the spec lists them, each with its icon
 *  (spec §5: calendar-check, route, users, trophy, radio, activity). */
const HUBS: Array<[string, string, LucideIcon]> = [
  ['/', 'This Week', CalendarCheck],
  ['/planning', 'Planning', Route],
  ['/players', 'Players', Users],
  ['/league', 'League', Trophy],
  ['/live', 'Live', Radio],
  ['/model', 'Model', Activity],
]

export default function AppShell({ children }: { children: ReactNode }) {
  const mobile = useIsMobile()

  // Active: accent text and a 2px accent bar on the left edge (sidebar) —
  // rule 3, "blue means it is active". No fill, no card.
  const links = HUBS.map(([path, label, Icon]) => (
    <NavLink
      key={path}
      to={path}
      end={path === '/'}
      className={({ isActive }) => (mobile
        ? `flex flex-col items-center gap-0.5 px-3 py-1.5 text-[11px] ${isActive
            ? 'text-accent-text' : 'text-text-muted hover:text-text'}`
        : `flex items-center gap-2.5 border-l-2 py-1.5 pl-2.5 pr-3 text-[13px]
           ${isActive
             ? 'border-accent text-accent-text'
             : 'border-transparent text-text-muted hover:text-text'}`)}
    >
      <Icon aria-hidden size={16} className="shrink-0" />
      {label}
    </NavLink>
  ))

  if (mobile) {
    return (
      <div className="min-h-screen bg-base pb-16">
        {/* Mounted here rather than in each hub or in PageHeader (A12):
            AppShell wraps <Routes> and stays mounted across every navigation,
            so this is one mount and one fetch, and it covers /league/rival/:id
            which has no hub wrapper at all. */}
        <main className="p-4"><FreshnessStrip />{children}</main>
        <nav
          data-testid="nav"
          data-mode="tabbar"
          className="fixed inset-x-0 bottom-0 flex justify-around border-t
                     border-border bg-base py-1"
        >
          {links}
          {/* The seventh slot. Six hubs already fill this row, so the theme
              control gets an icon and carries its state in the label. */}
          <ThemeToggle compact />
        </nav>
        {/* One outlet per layout: it is `position: fixed`, so where it sits
            in the tree does not matter visually — but it must exist in both
            branches or a phone silently loses every acknowledgement. */}
        <ToastOutlet />
      </div>
    )
  }

  return (
    <div className="grid min-h-screen grid-cols-[200px_1fr] bg-base">
      <nav
        data-testid="nav"
        data-mode="sidebar"
        className="flex flex-col gap-0.5 border-r border-border py-4 pr-3"
      >
        <p className="mb-3 pl-5 text-[15px] font-semibold text-text">gaffer</p>
        {links}
        {/* Footer, under the nav: chrome about the app rather than a place
            in it, so it sits below every destination and off the tab order
            of the six. */}
        <div className="mt-auto pl-3 pt-3">
          <ThemeToggle />
        </div>
      </nav>
      <main className="max-w-[1180px] p-6"><FreshnessStrip />{children}</main>
      <ToastOutlet />
    </div>
  )
}
```

- [ ] **Step 4: Run the suite, commit**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6` — Expected: green (`responsive.test.tsx` reads `data-mode` only).

```bash
git add frontend/src/kit/AppShell.tsx frontend/src/kit/AppShell.test.tsx
git commit -m "feat(v14): nav — lucide icons, accent bar for the active hub, no card

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---

## Task 6 — rework 1 (and 5, on this page): This Week's tiles, banner, buttons, toggles

**Files:**
- Modify: `frontend/src/hubs/ThisWeek.tsx`, `ThisWeek.test.tsx`

- [ ] **Step 1: Retarget the tests**

In `frontend/src/hubs/ThisWeek.test.tsx`:
- line 145: `expect(screen.getByText('61.5 pts'))` → `expect(screen.getByText('61.5'))` and add `expect(screen.getByText('pts')).toBeInTheDocument()`.
- lines 154–159, the chip test becomes:

```tsx
  it('draws the chip gain against its threshold, as a meter with the need stated', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await waitFor(() =>
      expect(screen.getByTestId('threshold-fill')).toBeInTheDocument())
    expect(screen.getByTestId('threshold-mark')).toBeInTheDocument()
    expect(screen.getByText('BB')).toBeInTheDocument()
    expect(screen.getByText('GW7')).toBeInTheDocument()
    expect(screen.getByText('8.2 of 6.0 needed')).toBeInTheDocument()
  })
```

- add, beside it:

```tsx
  it('states the league gap as a number with the side of it as the unit', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    const league = (await screen.findByText('League')).closest('div')!
    expect(within(league).getByText('84')).toBeInTheDocument()
    expect(within(league).getByText('behind')).toBeInTheDocument()
    expect(within(league).getByText(/chase · tilt \+0\.25/)).toBeInTheDocument()
  })

  it('states the captain with the sims share and the vice as context', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    const captain = (await screen.findByText('Captain')).closest('div')!
    expect(within(captain).getByText(/of sims · vice/)).toBeInTheDocument()
  })

  it('renders a data warning as an amber strip, not rust text', async () => {
    serve({ ...LATEST, staleness: { ...LATEST.staleness,
      data_warning: 'model has no data for GW5' } })
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveAttribute('data-tone', 'warn')
    expect(alert).toHaveTextContent('model has no data for GW5')
  })

  it('makes Run advise the primary action and Fast advise secondary', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Run advise' }))
      .toHaveClass('bg-accent')
    expect(screen.getByRole('button', { name: 'Fast advise' }))
      .toHaveClass('border-border')
  })
```

  (`LATEST` and `serve` are whatever that file already calls its fixture and its mock helper — read the top of the file and use its names; the fixture at line 44 has `strategy.gap: 84, lam: 0.25, stance: 'chase'` and `chip_table[0]` = bboost GW7 gain 8.2 threshold 6.0.)

- [ ] **Step 2: Run to see them fail**

Run: `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx` — Expected: the new ones FAIL.

- [ ] **Step 3: Rewrite the page's chrome**

In `frontend/src/hubs/ThisWeek.tsx`:

Imports become:

```tsx
import {
  Bar, Button, Callout, Card, EmptyState, JobButton, Loading, PageHeader,
  Segmented, Stat, StatRow, fmtNum, fmtPct,
} from '../kit'
```

Add under `nextChip`:

```tsx
/** The chip's two-letter code, as the mockup prints it. */
const CHIP_CODE: Record<string, string> = {
  bboost: 'BB', wildcard: 'WC', freehit: 'FH', '3xc': 'TC',
}

/** Which side of the gap you are on; `gap` is signed by the stance
 *  (league_mode.py:271-280): points behind the leader when chasing, points
 *  ahead of the nearest rival when defending. */
function gapUnit(stance: string): string {
  if (stance === 'chase') return 'behind'
  if (stance === 'defend') return 'ahead'
  return 'gap'
}
```

Replace the `<PageHeader … action=…/>` block, the data-warning `<p role="alert">`, and the four-tile `<div className="mb-4 grid …">` with:

```tsx
      <PageHeader
        title={`GW${data.gw}`}
        context={data.staleness.stale
          ? data.staleness.reason
          : `deadline ${new Date(data.deadline).toLocaleString()}`}
        action={(
          // Two runs, one lane: the full solve is the page's primary action;
          // the same solve with the sweep off (~5 min cheaper) is secondary.
          <div className="flex flex-wrap gap-2">
            <JobButton kind="advise-fast" onDone={load} />
            <JobButton kind="advise" variant="primary" onDone={load} />
          </div>
        )}
      />
      {data.staleness.data_warning && (
        <Callout tone="warn" role="alert" className="mb-4">
          {data.staleness.data_warning}
        </Callout>
      )}
      <StatRow>
        <Stat label="Expected XI" value={fmtNum(advice.expected_pts)}
              unit="pts" context="raw model points" />
        <Stat
          label="Captain"
          value={advice.captain.name}
          context={(advice.scenarios?.captain_frequency !== undefined
            ? `${fmtPct(advice.scenarios.captain_frequency)} of sims · `
            : '') + `vice ${advice.vice.name}`}
        />
        {chip
          ? (
            <Stat
              label="Next chip"
              value={CHIP_CODE[chip.chip] ?? chip.chip.toUpperCase()}
              unit={`GW${chip.gw}`}
              context={chip.threshold == null
                ? `${fmtNum(chip.gain)} expected gain`
                : `${fmtNum(chip.gain)} of ${fmtNum(chip.threshold)} needed`}
              meter={(
                // Rule 7: the one bar inside a tile. Scale is twice θ, as
                // ThresholdBar has always drawn it.
                <Bar
                  width="full"
                  testId="threshold"
                  fraction={chip.gain / Math.max((chip.threshold ?? 0) * 2, 1)}
                  mark={chip.threshold == null ? undefined : 0.5}
                  tone={chip.gain >= (chip.threshold ?? 0) ? 'up' : 'down'}
                />
              )}
            />
            )
          : <Stat label="Next chip" value="—" context="No chips available." />}
        <Stat
          label="League"
          value={strategy ? fmtNum(Math.abs(strategy.gap), 0) : '—'}
          unit={strategy ? gapUnit(strategy.stance) : undefined}
          context={strategy
            ? `${strategy.stance} · tilt ${strategy.lam >= 0 ? '+' : ''}${fmtNum(strategy.lam, 2)}`
            : undefined}
        />
      </StatRow>
```

Replace the EO lens `<button …>` and the Pitch/Table `<span className="flex overflow-hidden rounded-card …">…</span>` inside the Squad card's `action` with:

```tsx
            {view === 'pitch' && (
              <Button
                aria-pressed={lens}
                onClick={() => setLens((on) => !on)}
                className={lens ? 'bg-raised text-accent-text' : ''}
              >
                EO lens
              </Button>
            )}
            <Segmented
              label="Squad view"
              value={view}
              onChange={setView}
              options={[
                { value: 'pitch', label: 'Pitch' },
                { value: 'table', label: 'Table' },
              ]}
            />
```

Remove `ThresholdBar` from the imports (no longer used here). Delete nothing else; the rest of the page is untouched.

- [ ] **Step 4: Run the suite, commit**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6` — Expected: green. The existing Pitch/Table tests find buttons named `Pitch`/`Table` with `aria-pressed` inside the Segmented group; the EO lens test finds a button named `EO lens` with `aria-pressed`.

```bash
git add frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx
git commit -m "feat(v14): This Week — one tile shape for XI/captain/chip/league, amber data warning, primary Run advise, segmented squad view

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---

## Task 7 — rework 2: the pitch

**Files:**
- Modify: `frontend/src/kit/PlayerCard.tsx`, `PlayerCard.test.tsx`, `PitchView.tsx`, `hubs/this-week/SquadPitch.tsx`, `SquadPitch.test.tsx`

Read `.superpowers/brainstorm/27279-1788630695/content/pitch.html` (option A) first: 92px tiles on `base` with a hairline, 26px shirt, 11.5px/600 name, `TEAM · xPts` muted tabular, fixture chip in the tint language, C as a white square tag after the name and V grey, turf with a hairline inner rectangle, bench as a labelled row under the turf.

- [ ] **Step 1: Retarget the tests**

`frontend/src/kit/PlayerCard.test.tsx`:
- the fixture chip tests at lines ~75–105 assert `style.backgroundColor` for difficulty. Rewrite those two assertions to the tone: an easy fixture (`difficulty: 0.31`) → `expect(chip).toHaveAttribute('data-tone', 'up')`; a hard one (`0.9`) → `'down'`; unrated (`difficulty: null`) → `'neutral'`. The `MUN (H)` text assertions stay; the "some rendered kickoff" `toMatch(/\d/)` assertion (line 80) becomes `expect(chip).toHaveAttribute('title', expect.stringMatching(/\d/))` and the TBC test (line 93) becomes `expect(chip).toHaveAttribute('title', expect.stringContaining('TBC'))`.
- the field-class tests at lines ~188–207: rename the describe to the EO lens and rewrite:

```tsx
  it('draws no inline background without a lens ownership', () => {
    card()
    expect(frame().style.backgroundColor).toBe('')
  })

  it('tints the tile background by lens ownership', () => {
    card({ lensEo: 80 })
    expect(frame().style.backgroundColor).not.toBe('')
  })

  it('mixes more of the text colour in the more he is owned', () => {
    expect(lensBackground(80)).not.toBe(lensBackground(10))
    expect(lensBackground(80)).toContain('var(--color-text)')
  })

  it('names the field class in the title, never as a colour', () => {
    card({ lensEo: 45.7, fieldClass: 'shield' })
    expect(frame()).toHaveAttribute('title', expect.stringContaining('shield'))
  })
```

  (`card()` and `frame()` are that file's own helpers; keep their names. Import `lensBackground` from `./PlayerCard` beside the default import.)
- add:

```tsx
  it('is a 92px tile with a 26px shirt at pitch size', () => {
    card()
    expect(frame().className).toContain('w-[92px]')
    expect(screen.getByRole('img')).toHaveAttribute('width', '26')
  })

  it('tags the captain after the name as a square C, the vice as a grey V', () => {
    card({ armband: 'C' })
    expect(screen.getByTitle('Captain')).toHaveTextContent('C')
    expect(screen.getByTitle('Captain').className).not.toContain('rounded-full')
    card({ armband: 'V' })
    expect(screen.getByTitle('Vice-captain')).toHaveTextContent('V')
  })

  it('flags doubt in amber (rule 2)', () => {
    card({ news: 'Knock', chanceOfPlaying: 75 })
    expect(screen.getByText('75%')).toHaveAttribute('data-tone', 'warn')
  })
```

`frontend/src/hubs/this-week/SquadPitch.test.tsx`, the lens block: `tinted()` reads `style.borderColor` → change to `style.backgroundColor`; `lensXi`/`lensBench` set `fieldClass` → set `fieldEo: 45` (and keep `fieldClass` if you like; the tint keys off `fieldEo`). Add:

```tsx
  it('draws the turf with hairline markings and the bench on the page surface', () => {
    pitch()
    expect(screen.getByTestId('turf')).toHaveClass('bg-turf')
    expect(screen.getByTestId('turf').querySelectorAll('[data-turf-line]'))
      .toHaveLength(2)
    expect(screen.getByTestId('bench-strip').className)
      .not.toMatch(/border|bg-/)
    expect(screen.getByTestId('turf').getAttribute('style') ?? '')
      .not.toContain('gradient')
  })
```

- [ ] **Step 2: Run to see them fail**

Run: `cd frontend && npx vitest run src/kit/PlayerCard.test.tsx src/hubs/this-week/SquadPitch.test.tsx` — Expected: FAIL.

- [ ] **Step 3: Rewrite PlayerCard**

Replace `frontend/src/kit/PlayerCard.tsx` from the `FIELD_TINT` constant to the end with (keep the file's header comment, `PlayerCardSize`, `PlayerCardProps` — add the prop below — `PLAIN_SHIRT`, `shirtSrc`, `kickoffLabel`):

Add to `PlayerCardProps`, after `fieldClass`:

```ts
  /** v14: the EO lens. Field effective ownership, 0–100, when the lens is
   *  on; the tile background is tinted by it (rule 7 as a tint, not a bar).
   *  Null or absent draws no tint. `fieldClass` then only names the class in
   *  the title — never a colour, because a colour would be a verdict. */
  lensEo?: number | null
```

Then:

```tsx
/** The lens tint: more owned, more of the text colour mixed into the base.
 *  A token mix rather than a hex so it is right in both themes. */
export function lensBackground(eo: number): string {
  const pct = Math.round(Math.min(Math.max(eo, 0), 100) * 0.28)
  return `color-mix(in srgb, var(--color-text) ${pct}%, var(--color-base))`
}

function FixtureChip({ fixture }: { fixture: NextFixture | null }) {
  // A blank gameweek is a word, not an empty box: the reader has to be able
  // to tell "he does not play" from "we failed to load his fixture".
  if (!fixture) {
    return (
      <span data-testid="fixture-chip" data-tone="neutral"
            className="mt-1 inline-flex rounded-chip border border-border
                       px-1.5 text-[10px] leading-4 text-text-muted">
        Blank
      </span>
    )
  }
  const side = fixture.home ? 'H' : 'A'
  const tone = difficultyTone(fixture.difficulty)
  const rating = fixture.difficulty === null
    ? 'No difficulty rating available for this fixture'
    : `Fixture difficulty ${fixture.difficulty.toFixed(2)} — the ticker's `
      + 'odds-implied rating, not FPL\'s FDR'
  return (
    <span data-testid="fixture-chip">
      {/* The kickoff moved into the title (plan R3): the tile is not where
          a captain is chosen, and the mockup's tile carries none. */}
      <Chip tone={tone} className="mt-1"
            title={`${kickoffLabel(fixture.kickoff_utc)} · ${rating}`}>
        {`${fixture.opponent_short ?? '???'} (${side})`}
      </Chip>
    </span>
  )
}

export default function PlayerCard({
  code, name, position, teamShort, teamCode, ep, fixture = null,
  armband = null, multiplier = null, news = '', chanceOfPlaying = null,
  size = 'pitch', fieldClass = null, lensEo = null, onSelect,
}: PlayerCardProps) {
  const pitch = size === 'pitch'
  const shirtPx = pitch ? 26 : 20

  const shirt = (
    <img
      src={shirtSrc(teamCode, position)}
      alt={teamShort ? `${teamShort} shirt` : 'shirt'}
      width={shirtPx}
      height={shirtPx}
      // A request that fails on the wire falls back to the same plain shirt
      // a missing team code gets. The guard stops the swap retriggering if
      // the data URI itself somehow fails.
      onError={(e) => {
        if (e.currentTarget.getAttribute('src') !== PLAIN_SHIRT) {
          e.currentTarget.setAttribute('src', PLAIN_SHIRT)
        }
      }}
      className={pitch ? 'mx-auto mb-1 block' : 'block shrink-0'}
    />
  )

  // C: a white square tag after the name; V: the same tag in grey (spec §5).
  const tag = armband && (
    <span
      title={armband === 'C' ? 'Captain' : 'Vice-captain'}
      className="ml-1 inline-flex h-3 min-w-3 shrink-0 items-center
                 justify-center rounded-chip px-0.5 text-[9px] font-bold
                 leading-none"
      style={{
        background: armband === 'C' ? 'var(--color-text)'
                                    : 'var(--color-text-muted)',
        color: 'var(--color-base)',
      }}
    >
      {armband}
    </span>
  )

  const nameLine = (
    <span className={'flex min-w-0 items-center text-[11.5px] font-semibold '
      + `text-text ${pitch ? 'justify-center' : ''}`}>
      <span className="truncate">{name}</span>
      {tag}
      {news && (
        <Chip tone="warn" title={news} className="ml-1">
          {chanceOfPlaying === null ? 'News' : `${chanceOfPlaying}%`}
        </Chip>
      )}
    </span>
  )

  const metaLine = (
    <span className={'tn flex items-center gap-1 text-[10.5px] text-text-muted '
      + (pitch ? 'justify-center' : '')}>
      {teamShort && <span>{teamShort}</span>}
      {teamShort && <span aria-hidden>·</span>}
      <span>{fmtNum(ep)}</span>
      {/* Drawn only when the payload already named a chip (D3). */}
      {multiplier !== null && multiplier > 1 && (
        <span className="text-up">{`×${multiplier}`}</span>
      )}
    </span>
  )

  const body = pitch
    ? <>{shirt}{nameLine}{metaLine}<FixtureChip fixture={fixture} /></>
    : (
      <>
        {shirt}
        <span className="flex min-w-0 flex-col">{nameLine}{metaLine}</span>
      </>
      )

  const className = pitch
    ? 'flex w-[92px] flex-col items-center rounded-ctl border border-border '
      + 'bg-base px-1.5 py-1.5 text-center'
    // No fixed width: a chip sits in a table cell, a list row and a wrapping
    // strip, and each of those knows its own width better than the card does.
    : 'inline-flex max-w-full items-center gap-1.5 rounded-ctl border '
      + 'border-border bg-base px-1.5 py-1 text-left'

  // `undefined` rather than an empty object so an untinted card carries no
  // inline style at all.
  const style = lensEo !== null && lensEo !== undefined
    ? { backgroundColor: lensBackground(lensEo) }
    : undefined
  const title = lensEo !== null && lensEo !== undefined
    ? `field EO ${fmtNum(lensEo, 1)}%${fieldClass ? ` · ${fieldClass}` : ''}`
    : undefined

  // A div unless something is listening: a button nothing responds to is a
  // focus stop that lies about being interactive.
  return onSelect
    ? (
      <button type="button" data-code={code} className={className}
              style={style} title={title} onClick={() => onSelect(code)}>
        {body}
      </button>
      )
    : (
      <div data-code={code} className={className} style={style} title={title}>
        {body}
      </div>
      )
}
```

Imports at the top become `import Chip from './Chip'`, `import { fmtNum } from './format'`, `import { difficultyTone } from './scale'`, `import type { NextFixture } from '../types'`. Delete `FIELD_TINT` (grep for other importers: `grep -rn FIELD_TINT src` — only this file and possibly its test; drop from the test if so).

- [ ] **Step 4: Rewrite SquadPitch's frame**

In `frontend/src/hubs/this-week/SquadPitch.tsx`, the `card` helper passes `lensEo={lens ? player.fieldEo ?? null : null}` instead of `fieldClass={lens ? … : null}` (keep `fieldClass={player.fieldClass ?? null}` so the title can name it), and the returned JSX becomes:

```tsx
  return (
    <div>
      <div
        data-testid="turf"
        className="relative flex flex-col justify-between gap-3 rounded-ctl
                   bg-turf px-2 py-4"
      >
        {/* Hairline markings: an inner rectangle and the halfway line, in
            the turf-line token — no texture, no gradient (spec §5). */}
        <div aria-hidden data-turf-line
             className="pointer-events-none absolute inset-2 rounded-chip
                        border border-turf-line" />
        <div aria-hidden data-turf-line
             className="pointer-events-none absolute inset-x-2 top-1/2
                        border-t border-turf-line" />
        {rows.map(([line, players]) => (
          <div key={line} data-testid={`pitch-row-${line}`}
               className="relative flex flex-wrap justify-center gap-2">
            {players.map(card)}
          </div>
        ))}
      </div>
      {bench.length > 0 && (
        <div data-testid="bench-strip" className="mt-3">
          <p className="label mb-1.5">Bench · in order</p>
          <div className="flex flex-wrap gap-2">
            {bench.map(card)}
          </div>
        </div>
      )}
    </div>
  )
```

Update the file's header comment: the bench is "a labelled row on the page surface under the turf". Delete the gradient comment.

- [ ] **Step 5: PitchView**

`frontend/src/kit/PitchView.tsx` (the kit's bare pitch, exported and tested, used by no hub): the tile `className` → `'flex w-[92px] flex-col items-center rounded-ctl border bg-base px-1.5 py-1.5'`, the wrapper → `'relative flex w-full flex-col gap-3 rounded-ctl bg-turf px-2 py-4'`, the C span → `className="rounded-chip px-0.5 text-[9px] font-bold leading-none" style={{ background: 'var(--color-text)', color: 'var(--color-base)' }}`, the V span the same with `var(--color-text-muted)`, and `"num text-xs text-text-muted"` → `"tn text-[10.5px] text-text-muted"`. Its test asserts titles and rows only.

- [ ] **Step 6: Run the suite, commit**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6` — Expected: green. `Live.test`, `RivalDetail.test`, `ReviewTab.test` render chip-size cards and assert names/ep only; if one asserted the old kickoff text inside a chip, retarget it to the title.

```bash
git add frontend/src/kit/PlayerCard.tsx frontend/src/kit/PlayerCard.test.tsx frontend/src/kit/PitchView.tsx \
  frontend/src/hubs/this-week/SquadPitch.tsx frontend/src/hubs/this-week/SquadPitch.test.tsx
git commit -m "feat(v14): the pitch — muted turf with hairline markings, 92px tiles on base, tint-language fixture chips, C/V tags, bench on the page, EO lens as a tint

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---
## Task 8 — rework 3: the moves table, the ladder, the sensitivity table

**Files:**
- Modify: `frontend/src/hubs/this-week/MovesCard.tsx`, `MovesCard.test.tsx`, `LadderCard.tsx`, `LadderCard.test.tsx`, `hubs/planning/SensitivityCard.tsx`, `SensitivityCard.test.tsx` (only if it pins a class)

- [ ] **Step 1: Retarget the tests**

`MovesCard.test.tsx` — the colour test becomes:

```tsx
  it('marks IN as an up chip and OUT as a down chip, with sims as a bar', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.getByText('IN')).toHaveAttribute('data-tone', 'up')
    expect(screen.getByText('OUT')).toHaveAttribute('data-tone', 'down')
    expect(screen.getAllByTestId('sims-fill')[0]).toHaveStyle({ width: '82%' })
  })
```

  and the hits test's `'-8 pts'` → `'−8 pts'` (a real minus, U+2212, as the ladder already prints).

`LadderCard.test.tsx:113-117`: `text-text-muted` → `text-text-faint` (both lines). Add after it:

```tsx
  it('tints the cap rung accent and draws the odds as bars with the percent beside', async () => {
    mount()
    const cap = (await screen.findByText('2 hits')).closest('tr')!
    expect(cap).toHaveClass('bg-accent-tint')
    const rec = screen.getByText('1 hit').closest('tr')!
    expect(within(rec).getByTestId('p-beats-bank-fill')).toHaveStyle({ width: '74%' })
    expect(within(rec).getByTestId('p-best-fill')).toHaveStyle({ width: '50%' })
    expect(rec).toHaveTextContent('74%')
  })

  it('prints the horizon cost in down ink beside the cost now', async () => {
    mount()
    const row = (await screen.findByText('1 hit')).closest('tr')!
    const horizon = within(row).getByText(/over \d+ GWs?/)
    expect(horizon).toHaveClass('text-down')
  })
```

  (The fixture in that file gives the 1-hit rung `cost: 4` and a larger `horizon_cost`; if its `horizon_cost` equals `cost`, the second test finds no `over … GWs` — read the fixture and, if so, set `horizon_cost: 12` on that rung.)

- [ ] **Step 2: Run to see them fail**

Run: `cd frontend && npx vitest run src/hubs/this-week/MovesCard.test.tsx src/hubs/this-week/LadderCard.test.tsx` — Expected: FAIL.

- [ ] **Step 3: MovesCard**

Replace `frontend/src/hubs/this-week/MovesCard.tsx` with:

```tsx
import {
  Bar, Card, Chip, PosBadge, TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum,
  fmtPct, tdClass, thClass,
} from '../../kit'

export interface Move {
  code: number
  name: string
  ep: number
  /** Advice written before v3.1 carries no position; the dot then hides. */
  position?: string | null
  frequency?: number | null
  tag?: string | null
}

export interface MovesCardProps {
  buys: Move[]
  sells: Move[]
  hits: number
  /** v13: "1 free transfer · cap 2 hits", from the ladder payload. */
  capLine?: string | null
}

export default function MovesCard(
  { buys, sells, hits, capLine }: MovesCardProps,
) {
  const rows: Array<['IN' | 'OUT', Move]> = [
    ...buys.map((m) => ['IN', m] as ['IN', Move]),
    ...sells.map((m) => ['OUT', m] as ['OUT', Move]),
  ]
  return (
    <Card title="Recommended moves">
      {capLine && (
        <p className="mb-2 text-text-secondary" data-testid="moves-cap-line">
          {capLine}
        </p>
      )}
      {rows.length === 0
        ? <p className="text-text-muted">No transfers — bank the free transfer.</p>
        : (
          <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>Move</th>
                <th className={thClass()}>Player</th>
                <th className={thClass(true)}>xPts</th>
                <th className={thClass()}>Sims</th>
                <th className={thClass()} />
              </tr>
            </thead>
            <tbody>
              {rows.map(([side, move]) => (
                <tr key={`${side}-${move.code}`} className={TR_CLASS}>
                  <td className={tdClass()}>
                    {/* In/out is a direction (rule 1). */}
                    <Chip tone={side === 'IN' ? 'up' : 'down'}>{side}</Chip>
                  </td>
                  <td className={`${tdClass()} text-text`}>
                    <span className="inline-flex items-center gap-1.5">
                      <PosBadge pos={move.position} variant="dot" />
                      {move.name}
                    </span>
                  </td>
                  <td className={`${tdClass(true)} text-text`}>
                    {fmtNum(move.ep)}
                  </td>
                  <td className={tdClass()}>
                    {/* Scenario support: several rows, one ceiling (rule 7). */}
                    <Bar testId="sims" fraction={move.frequency ?? null}
                         text={fmtPct(move.frequency ?? null)} />
                  </td>
                  <td className={`${tdClass()} text-right`}>
                    {move.tag && <Chip>{move.tag}</Chip>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          )}
      {hits > 0 && (
        <p className="mt-3 text-text-secondary">
          {hits} hit{hits === 1 ? '' : 's'}:{' '}
          <span className="tn text-down">{`−${hits * 4} pts`}</span>
        </p>
      )}
    </Card>
  )
}
```

- [ ] **Step 4: LadderCard**

In `frontend/src/hubs/this-week/LadderCard.tsx`:

Imports become:

```tsx
import {
  Bar, Button, Callout, Card, Chip, INPUT_CLASS, PlayerName, Skeleton,
  TABLE_CLASS, THEAD_CLASS, TONE_TINT_CLASS, TR_CLASS, TR_EXPANDED_CLASS,
  TR_SELECTED_CLASS, fmtNum, tdClass, thClass, toneOf,
} from '../../kit'
```

Delete the local `FIELD` constant; both `<select className={FIELD}>` become `className={INPUT_CLASS}`.

Replace `rungCost` with a component that keeps the same words:

```tsx
/** The cost cell.
 *
 *  `max_hits` is a *per-week* cap, so a rung that takes one hit takes it in
 *  every horizon week: the decision on the table costs 4, the plan behind it
 *  costs 12. Printing only one of those misprices the row, so both go in
 *  whenever they differ — the horizon figure in `down`, because it is the
 *  bill the reader is being warned about (spec §6.3). */
function RungCost({ rung, weeks }: { rung: LadderRung; weeks: number }) {
  if (rung.horizon_cost === rung.cost) return <>{costText(rung.cost)}</>
  return (
    <>
      <span>{costText(rung.cost)} now</span>
      <span className="text-text-muted"> · </span>
      <span className="text-down">
        {`${costText(rung.horizon_cost)} over ${weeks} GW${weeks === 1 ? '' : 's'}`}
      </span>
    </>
  )
}
```

The Rebuild button becomes `<Button onClick={rebuild} disabled={busy || !data?.gw}>{busy ? 'Rebuilding…' : 'Rebuild'}</Button>`.

`{failed && <p className="mb-3 text-rust">{failed}</p>}` → `{failed && <Callout tone="error" className="mb-3">{failed}</Callout>}`; the `job.status === 'error'` line likewise.

The table: `<table className="w-full">` → `<table className={TABLE_CLASS}>`; `<thead>` → `<thead className={THEAD_CLASS}>`; each `<th className="label text-left">` → `<th className={thClass()}>` and `text-right` ones → `thClass(true)`. The row:

```tsx
                const rowClass = [
                  'cursor-pointer', TR_CLASS,
                  isCap ? TR_SELECTED_CLASS : '',
                  beyond ? 'text-text-faint' : 'text-text',
                ].join(' ')
```

The cells:

```tsx
                      <td className={tdClass()}>
                        <span className="inline-flex items-center gap-1.5">
                          {label}
                          {r.key === data?.recommended && <Chip>recommended</Chip>}
                        </span>
                      </td>
                      {r.same_as
                        ? (
                          <td className={`${tdClass()} text-text-muted`} colSpan={7}>
                            solver would not spend it — same as{' '}
                            {(below ? rungLabel(below) : r.same_as).toLowerCase()}
                          </td>
                          )
                        : (
                          <>
                            <td className={tdClass()}>{movesText(r)}</td>
                            <td className={tdClass(true)}><RungCost rung={r} weeks={weeks} /></td>
                            <td className={tdClass(true)}>{fmtNum(r.week_pts)}</td>
                            <td className={tdClass(true)}>{fmtNum(r.mean_pts)}</td>
                            <td className={`${tdClass(true)} ${vsBank === null || r.key === 'bank' ? '' : TONE_TINT_CLASS[toneOf(vsBank)]}`}>
                              {vsBank === null || r.key === 'bank' ? '—'
                                : `${vsBank >= 0 ? '+' : '−'}${fmtNum(Math.abs(vsBank), 1)}`}
                            </td>
                            <td className={tdClass()}>
                              <Bar testId="p-beats-bank" fraction={r.p_beats_bank ?? null}
                                   text={pct(r.p_beats_bank)} />
                            </td>
                            <td className={tdClass()}>
                              <Bar testId="p-best" fraction={r.p_best ?? null}
                                   text={pct(r.p_best)} />
                            </td>
                          </>
                          )}
```

(The two P(…) headers become `thClass()` — left-aligned, since the cell is a bar.) The expanded row: `<tr className="border-t border-divider">` → `<tr className={TR_EXPANDED_CLASS}>` and its `<td colSpan={8}>` gets `className="px-2.5 py-3"`. In `Expanded`, `text-rust` → `text-down`.

- [ ] **Step 5: SensitivityCard**

In `frontend/src/hubs/planning/SensitivityCard.tsx`: import `Bar, Callout, TABLE_CLASS, THEAD_CLASS, TR_CLASS, tdClass, thClass` from the kit; the notice `<p className="mb-3 rounded-card border-l-2 border-info …">{data.notice}</p>` → `<Callout className="mb-3">{data.notice}</Callout>`; the table takes `TABLE_CLASS`/`THEAD_CLASS`/`thClass`/`tdClass`/`TR_CLASS` as above; the Share cell becomes `<td className={tdClass()}><Bar testId="share" fraction={r.frequency} text={pct(r.frequency)} /></td>` with its header `thClass()`; the failures line `text-rust` → `text-down`. Check `SensitivityCard.test.tsx` for a `getByText('80%')`-style assertion — the percent is still printed, inside the Bar's text span, so it holds.

- [ ] **Step 6: Run the suite, commit**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6` — Expected: green. `ThisWeek.test`'s `'-8 pts'`-style assertion, if any (`grep -n "pts'" src/hubs/ThisWeek.test.tsx`), moves to the real minus.

```bash
git add frontend/src/hubs/this-week/MovesCard.tsx frontend/src/hubs/this-week/MovesCard.test.tsx \
  frontend/src/hubs/this-week/LadderCard.tsx frontend/src/hubs/this-week/LadderCard.test.tsx \
  frontend/src/hubs/planning/SensitivityCard.tsx frontend/src/hubs/planning/SensitivityCard.test.tsx
git commit -m "feat(v14): moves, ladder and sensitivity on the one table style — IN/OUT chips, support and odds as bars, the horizon cost in down, the cap rung accent-tinted

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

(Drop `SensitivityCard.test.tsx` from the add list if it did not change.)

---

## Task 9 — rework 5: buttons, toggles, tabs and inputs in every other hub

**Files:**
- Modify: `frontend/src/hubs/Planning.tsx`, `Players.tsx`, `Players.test.tsx`, `League.tsx`, `Model.tsx`, `hubs/planning/WhatIfTab.tsx`, `ConstraintsPanel.tsx`, `PlannerBoard.tsx`, `DraftsTab.tsx`, `hubs/players/PinDialog.tsx`, `WatchlistTab.tsx`, `hubs/league/RivalDetail.tsx`, `hubs/model/SettingsTab.tsx`, `hubs/Live.tsx`

Mechanical, file by file. Every `<button className="rounded-card border border-border …">` becomes a kit `Button`; every `<input>`/`<select>` takes `INPUT_CLASS`; every Radix tab strip takes the kit classes; every toggle group becomes `Segmented` or `segmentClass`.

- [ ] **Step 1: Retarget the one test that pins the old toggle colour**

`frontend/src/hubs/Players.test.tsx:88-95` (plan R9) becomes:

```tsx
  it('paints the active position filter in accent (v14)', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await screen.findByText('Salah')
    const filters = screen.getByRole('group', { name: 'Position' })
    const def = within(filters).getByRole('button', { name: 'DEF' })
    expect(def).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(def)
    expect(def).toHaveAttribute('aria-pressed', 'true')
    expect(def).toHaveClass('text-accent-text')
  })
```

- [ ] **Step 2: The four tab strips**

In `Planning.tsx`, `Players.tsx`, `League.tsx`, `Model.tsx`: delete the local `TAB_CLASS` constant and its comment; add `TAB_CLASS, TAB_LIST_CLASS` to the kit import; `<Tabs.List className="mb-4 flex overflow-x-auto border-b border-divider">` → `<Tabs.List className={TAB_LIST_CLASS}>`. The triggers already use `TAB_CLASS`.

- [ ] **Step 3: Planning**

`WhatIfTab.tsx`: import `Button, Callout`; the Re-solve `<button …>` → `<Button className="mb-4" onClick={solve} disabled={busy}>{busy ? 'Solving…' : 'Re-solve'}</Button>`; inside the Infeasible card `text-rust` → `text-down`; the Solver failed card's `<p className="text-rust">` → `<Callout tone="error">{job.error}</Callout>`.

`ConstraintsPanel.tsx`: `const FIELD = …` → delete; import `INPUT_CLASS` and use it for the four inputs and four selects; the chip for a picked player (`rounded border border-border px-1.5 py-0.5 text-[11px]`) → `rounded-chip border border-border px-1.5 py-px text-[10px] font-semibold leading-4 text-text-secondary`; its `×` button `hover:text-rust` → `hover:text-down`; the suggestions dropdown `rounded-card border border-border bg-card p-1` → `rounded-ctl border border-border bg-raised p-1`, each suggestion `rounded px-2 py-1 … hover:bg-base` → `rounded-chip px-2 py-1 … hover:bg-base`; `num` → `tn`.

`PlannerBoard.tsx`: import `Button, segmentClass`; the plan tab buttons at ~235–250 keep `role="tab"`, `aria-selected`, `tabIndex`, `id`, `aria-controls` and take `className={segmentClass(pick === i)}` with the wrapping `<div role="tablist" …>` given `className="mb-4 inline-flex divide-x divide-border overflow-hidden rounded-ctl border border-border"` (keep whatever other attributes it has); the "Try these changes" `<button>` → `<Button data-testid={…} onClick={…}>Try these changes</Button>`.

`DraftsTab.tsx`: the two form buttons at ~93 and ~100 → `<Button …>` (keep `disabled`, `onClick`, labels); the Delete button at ~147 → `<Button variant="ghost" aria-label=… onClick=…>Delete</Button>`; the name `<input>` → `INPUT_CLASS`.

- [ ] **Step 4: Players**

`Players.tsx`: the position `<button>`s (~287–304) → keep `aria-pressed`, `onClick`, `key`; `className={segmentClass(active)}` with the wrapping `role="group"` div given `className="inline-flex divide-x divide-border overflow-hidden rounded-ctl border border-border"`; delete the hue `style` and the `posColor` import if now unused; the search `<input>` → `INPUT_CLASS`; the Pin button (~235–244) → `<Button variant="ghost" aria-label={…} onClick={…}>{pinned… ? 'Pinned' : 'Pin'}</Button>`; the star button's class → `"px-1 text-text-muted hover:text-accent-text disabled:cursor-not-allowed disabled:opacity-40"`.

`PinDialog.tsx`: the dialog frame `rounded-card border border-border bg-card` → `rounded-ctl border border-border bg-base`; Close → `<button ref={closeRef} type="button" onClick={onClose} className={buttonClass('ghost')}>Close</button>`; the Pin button → `<Button variant="primary" className="self-end" onClick={save}>Pin</Button>`; `const FIELD` → `INPUT_CLASS`; `{error && <p className="text-rust">}` → `<Callout tone="error">`; `{warning && <p className="text-info">}` → `<Callout tone="warn">` (rule 2).

`WatchlistTab.tsx:121`: the `<button className="rounded-card border border-border bg-base px-2 py-1 …">` → `<Button variant="ghost" …>`; any `<input>` → `INPUT_CLASS`; `num` → `tn`.

- [ ] **Step 5: League, Model, Live**

`RivalDetail.tsx:72`: the `<button className="mt-3 rounded-card …">` → `<Button className="mt-3" …>`.

`SettingsTab.tsx`: the field `<input className="w-32 rounded-card border border-border bg-base px-2 py-1">` → `className={`${INPUT_CLASS} w-32`}`; the Save `<button>` → `<Button disabled={busy} onClick={…}>{`Save ${label(row)}`}</Button>`; the Reset `<button className="self-start text-text-muted hover:text-text">` → `<Button variant="ghost" className="self-start" …>`; the overlay-error `<p … className="rounded-card border border-rust bg-card px-3 py-2 text-rust">` → `<Callout tone="error" data-testid="settings-overlay-error" role="status" aria-live="polite">`; per-row error `<p className="text-rust">` → `text-down`.

`Live.tsx`: find every `<button` (`grep -n "<button" src/hubs/Live.tsx`) and convert as above; the two `border-l-2 border-info` notices (~152, ~204) → `<Callout className="mb-3">`; the safety boxes at ~299 (`rounded-card border border-border bg-card px-4 py-3`) → `border-l-2 border-border pl-3` (a ruled item, not a box); `text-rust`/`text-sage` there → `text-down`/`text-up`; `num` → `tn`; the sparkline stroke `var(--color-info)` at ~189 → `var(--color-text)`.

- [ ] **Step 6: Run the suite, commit, capture the second gate**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6` — Expected: green. Tests that find buttons by role and name are unaffected; `PlannerBoard.test.tsx:338-339` reads the tablist's `flex-wrap` — if it fails, add `flex-wrap` to that tablist's class (it is the strip that wraps at 390px).

```bash
git add frontend/src/hubs/Planning.tsx frontend/src/hubs/Players.tsx frontend/src/hubs/Players.test.tsx \
  frontend/src/hubs/League.tsx frontend/src/hubs/Model.tsx frontend/src/hubs/Live.tsx \
  frontend/src/hubs/planning/WhatIfTab.tsx frontend/src/hubs/planning/ConstraintsPanel.tsx \
  frontend/src/hubs/planning/PlannerBoard.tsx frontend/src/hubs/planning/DraftsTab.tsx \
  frontend/src/hubs/players/PinDialog.tsx frontend/src/hubs/players/WatchlistTab.tsx \
  frontend/src/hubs/league/RivalDetail.tsx frontend/src/hubs/model/SettingsTab.tsx
git commit -m "feat(v14): one button set, segmented toggles, accent-underlined tabs and input surfaces in every hub

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
cd frontend && npm run build 2>&1 | tail -2 && cd ..
lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || (uv run gaffer ui --no-open-browser --port 8927 &)
frontend/scripts/shots.sh reworks
```

Look at all twelve PNGs. Report plainly. 🛑 **STOP: the orchestrator shows these to the user before Task 10.**

---
## The sweep (Tasks 10–11): the replacement table

Every file under `frontend/src/hubs/**` not already rewritten is checked against spec §4–§5. The mechanical part is this table; the judgement part is listed per file underneath. `tokens.test.ts` (Task 12) enforces the outcome, so nothing may be left "for later".

| Old | New | Why |
|---|---|---|
| `num` (class) | `tn` | one face, tabular figures (§3) |
| `text-sage` / `text-rust` | `text-up` / `text-down` — **only where it is a direction** (rule 1); otherwise `text-text` / `text-text-muted` | |
| `bg-sage` / `bg-rust` (bars) | `<Bar>` with `tone` | rule 7 |
| `border-sage` / `border-rust` (outlines) | a `Chip` or `Callout`, or the plain hairline | rule 1: never chrome |
| `text-info` (links) | `text-accent-text` | rule 3 |
| `text-info` / `Badge variant="info"` (words) | `<Chip>` neutral | R7 |
| `border-l-2 border-info bg-base` callouts | `<Callout>` (note) | R5 |
| `border-rust` / `bg-card text-rust` error boxes | `<Callout tone="error">` | R4 |
| `Badge variant="negative"` on availability / news | `<Chip tone="warn">` | rule 2 |
| `Badge variant="positive"` / `"negative"` on a direction | `<Chip tone="up">` / `"down"` | rule 1 |
| `Badge` / `Badge variant="neutral"` | `<Chip>` | |
| `rounded-card border border-border bg-card …` boxes | no box: `Card` (Section) already has none; an inner box becomes `border-l-2 border-border pl-3` or plain | §5 |
| `rounded-card` on an input/button/dialog/dropdown | `rounded-ctl` | R1 |
| `rounded`, `rounded-sm`, `rounded-l`, `rounded-r` on chips/meters | `rounded-chip` | R1 |
| `rounded-full` | `rounded-chip` (dots), `<Bar>` (meters) | §3 |
| `bg-card` (fill) | `bg-raised` where a band is meant; nothing where it was a box | |
| `shadow-*`, `bg-gradient-*`, `linear-gradient(` | removed | §3 |
| `difficultyBackground(x)` inline style | `<Chip tone={difficultyTone(x)}>` | rule 1, R3 |
| `var(--color-sage/rust/info/card)` in inline styles / SVG | `var(--color-up/down/text/raised)` or `SERIES_COLOURS` | |
| local `SERIES_COLOURS` / `COLOURS` / `HEAD_COLOURS` arrays | the kit's `SERIES_COLOURS` (+ `SERIES_DASH` as `strokeDasharray`) | R6 |
| `text-xl` / `text-2xl` stat-like numbers | `text-[22px] font-semibold tn` | §3 |
| `text-xs` on a table's numbers | inherit (13px) | §3 |
| hand-rolled `<table className="w-full">` with `label` headers | `TABLE_CLASS` / `THEAD_CLASS` / `thClass()` / `tdClass()` / `TR_CLASS` | §5 |
| `<button className="rounded-card border …">` | `<Button>` | §5 |
| `<input className="rounded-card …">` | `INPUT_CLASS` | §5 |
| `text-moss`, `text-amber`, `bg-surface` (phantom classes) | the token that was meant | never existed |

Commands to find the work (run in `frontend/`):

```bash
grep -rn "\bnum\b" src/hubs --include='*.tsx' | grep -v test | grep -c className
grep -rnE "text-(sage|rust|info)|border-(sage|rust|info)|bg-(sage|rust|info|card)|rounded-(card|full)|rounded\b|shadow|gradient|difficultyBackground|var\(--color-(sage|rust|info|card)\)|<Badge|text-(moss|amber)|bg-surface" src/hubs --include='*.tsx' | grep -v "\.test\." | cut -d: -f1 | sort | uniq -c | sort -rn
```

---

## Task 10 — sweep, part 1: This Week and Planning

**Files:**
- Modify: `frontend/src/hubs/this-week/SquadTable.tsx`, `WhyPanel.tsx`, `DigestCard.tsx`, `NewsPanel.tsx`; `frontend/src/hubs/planning/Timeline.tsx`, `Timeline.test.tsx`, `PlannerBoard.tsx`, `DraftsTab.tsx`, `ChipsTab.tsx`, `TickerTab.tsx`, `FixtureTicker.tsx`, `PlanDiffTable.tsx`, `OverridesCard.tsx`, `ConstraintsPanel.tsx` (leftovers)

- [ ] **Step 1: Apply the table to every file above**

Per file, beyond the mechanical rows:

- `SquadTable.tsx`: `Badge variant="negative"` on `r.news` → `<Chip tone="warn">`; `Pens` → `<Chip>`; the `positive`/`negative` badges at ~90/~99 — read what they say: if they are a direction relative to the plan (e.g. "in"/"out", better/worse) → `up`/`down`; if availability → `warn`. The breakdown table in the expand → the table constants. The Field% column: several rows, one ceiling → `<Bar fraction={r.fieldEo / 100} text={fmtNum(r.fieldEo, 1)} />` (rule 7 names ownership and effective ownership in the Players table; the squad table's Field% is the same column and takes the same bar). Own%/EO% columns likewise if present.
- `WhyPanel.tsx:183`: the pins box → `<Callout className="mb-4">` with the `label` and lines inside; any `text-rust` that is an error → `Callout tone="error"`; a delta → `TONE_CLASS` (already up/down).
- `DigestCard.tsx`, `NewsPanel.tsx`: `<Badge>` → `<Chip>`; `num` → `tn`; any box → none.
- `Timeline.tsx:15-16`: in/out is a direction → `text-up`/`text-down`; `Timeline.test.tsx:49-50` retargets to `text-up`/`text-down`. `:101` chip badge → `<Chip>`; `:120` hit cost → `<Chip tone="down">`; `:104` `num text-xl` → `tn text-[22px] font-semibold`; `:151-152` the fixture cell → `<Chip tone={difficultyTone(cell.difficulty)}>…</Chip>`; the week `Card`s in the `flex gap-3 overflow-x-auto` strip keep `min-w-[220px]` and gain `border-l border-border pl-3` on every column after the first so the strip still reads as columns without boxes.
- `PlannerBoard.tsx`: `:294` chip badge → `<Chip>`; `:314` hit badge → `<Chip tone="down">`; `:333` `num text-xl` → `tn text-[22px] font-semibold`; the week cards side by side take the same `border-l` rule as the timeline; the trace block (`:340-420`) is the **one place besides JobLog allowed `font-mono`**: give the formula lines (`week.trace.moves` entries and the `hit charge`/`bank`/`θ`/`price` lines) `font-mono tn text-xs`, and nothing else in the file mono. Plan A/B/C already segmented (Task 9).
- `DraftsTab.tsx`, `TickerTab.tsx`: table constants, `tn`, `Chip`.
- `ChipsTab.tsx:38-58` `GainBar` → `<Bar fraction={bar > 0 ? gain / bar : 0} tone={gain >= bar ? 'up' : 'neutral'} width={96} aria-label={…} />` — over the bar is a direction, under it is information; `:505-522` the θ track chips → `<Chip tone={over ? 'up' : 'neutral'} title=…>`; `ChipsTab.test.tsx:380` asserts `aria-pressed` on something — read it; if it is a toggle group, it becomes `Segmented`/`segmentClass` and the assertion holds.
- `FixtureTicker.tsx:64` notice → `<Callout>`; `:108` cell → `<Chip tone={difficultyTone(cell.difficulty)}>`; the grid keeps its layout.
- `PlanDiffTable.tsx:67` the changed-row dot `text-info` → `text-text` (changed is information, not a click); `:64` changed rows `text-text`, unchanged `text-text-muted`; `:104` delta → `TONE_CLASS` (already); table constants.
- `OverridesCard.tsx:35` "saved but not applied" → `<Callout tone="warn">` (doubt about whether your pins act — rule 2).
- `ConstraintsPanel.tsx`: whatever Task 9 left.

- [ ] **Step 2: Run the suite; retarget any test that pinned an old class**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -8`. For each failure that is a class-name assertion, retarget it to the new class in the same spirit (`text-sage` → `text-up`, `num` → `tn`, a `style.background` on a fixture cell → `data-tone`). For each failure that is behaviour, you broke something — fix the component, not the test.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hubs/this-week frontend/src/hubs/planning
git commit -m "style(v14): sweep — This Week and Planning components on the ledger rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

(`git add` of those two directories is explicit enough: they contain only tracked `.tsx` sources and tests. Do not add anything outside `frontend/src`.)

---

## Task 11 — sweep, part 2: Players, League, Live, Model

**Files:**
- Modify: `frontend/src/hubs/Players.tsx` (leftovers), `hubs/players/ComparePanel.tsx`, `CompareRadar.tsx`, `FixtureMatrix.tsx`, `PinDialog.tsx`, `WatchlistTab.tsx`; `hubs/League.tsx`, `hubs/league/FieldPanel.tsx`, `RivalDetail.tsx`, `WhatIfSim.tsx`; `hubs/Live.tsx` (leftovers); `hubs/model/QualityTab.tsx`, `HealthTab.tsx`, `HistoryTab.tsx`, `SeasonTab.tsx`, `ReviewTab.tsx`, `JournalTab.tsx`, `SettingsTab.tsx` (leftovers); their tests where a class was pinned

- [ ] **Step 1: Apply the table to every file above**

Per file, beyond the mechanical rows:

- `Players.tsx`: Own% and EO% columns → `<Bar fraction={r.ownership / 100} text={fmtNum(r.ownership)} width={48} />` (rule 7 names both); Field% keeps its arrow-and-word cell but the number becomes a bar too; the range cell `num` → `tn`; the explorer's `<Card>` wrapper stays.
- `ComparePanel.tsx`: `SERIES_COLOURS` local → kit's; `SignedBar` (~60–80) → two `<Bar>`s is wrong (it is a signed bar about a centre) — keep it, restyled: track `rounded-chip bg-border`, fills `bg-up`/`bg-down`, the centre mark `bg-text`; `:405` info badge → `<Chip>`; `:435` fixture cell → `<Chip tone={difficultyTone(score)}>`; the four player cards (`titleSize="lg"`, `PosBadge` in the action slot — rule 5 says the compare panel's header carries the position hue, and it does) sit in `grid gap-3 md:grid-cols-2 lg:grid-cols-4` and gain `border-l border-border pl-3` on every column after the first (same device as the timeline); `num` → `tn`.
- `CompareRadar.tsx`: local colours → kit `SERIES_COLOURS`, each `<Radar>`/`<Line>` also gets `strokeDasharray={SERIES_DASH[i]}`; grid/axis strokes `var(--color-divider)` / `var(--color-text-muted)`.
- `FixtureMatrix.tsx:84`: cell → `<Chip tone={difficultyTone(score(cell))} className="w-full justify-center">` (a matrix of chips reads as the FPL fixture grid in the tint language).
- `PinDialog.tsx`, `WatchlistTab.tsx`: leftovers.
- `League.tsx`: `SERIES_COLOURS` local → kit's, with "you" moved to index 0 (sort `race.trajectory` so `isYou` is first before assigning colours; the standings swatch reads `seriesColour`, so it follows); `:241` swatch `rounded-full` → `rounded-chip`; `:175` rival link `text-info underline` → `text-accent-text hover:underline`; the standings, per-rival and legacy tables → table constants; the "you" standing row → `TR_SELECTED_CLASS` (it is the row the reader is); `MarginFan`: the race gap is rule 7's named bar — track `rounded-chip bg-border`, the p25–p75 fill `bg-up` when p50 ≥ 0 else `bg-down`, the p50 mark `bg-text`, the zero mark `bg-text-muted`, `rounded-sm` gone; the three `num text-2xl` sim numbers → a `<StatRow cols={3}>` of `<Stat>`s (`P(win)`, `P(top 3)`, `Expected finish`; keep the `data-testid`s by putting them on a `<span data-testid=…>` inside `value`); Recharts `Tooltip contentStyle` → `background: var(--color-raised)`.
- `FieldPanel.tsx`, `WhatIfSim.tsx`, `RivalDetail.tsx`: `Badge` → `Chip` (`you` → `<Chip>`; chips played → `<Chip>`); tables → constants; `num` → `tn`.
- `Live.tsx`: leftovers from Task 9; the auto-sub badges: `projected_out` is a direction relative to your XI → `<Chip tone="down">`, `projected_in` → `<Chip tone="up">`.
- `QualityTab.tsx` (1056 lines — the biggest): `:456-467` and `:534-545` the paired bars → two `<Bar>`s each (`news`/`started` in `up`? no — these compare two instruments, neither a direction: both `neutral`, widths 112/128 as now, `aria-label` kept); `:477` notice → `<Callout>`; `:726` `floor` badge → `<Chip tone="warn">` (a floor is doubt about the count); `:733` instrument → `<Chip>`; `Stat`s at `:804-815` → wrap in `<StatRow>`; every table → constants; `num` → `tn`; any `text-rust`/`text-sage` on a verdict word (better/worse) stays a direction → `down`/`up`.
- `HealthTab.tsx:37` season mismatch → `<Callout tone="error" data-testid="season-mismatch">` with the two `<p>`s inside (`font-semibold` title stays; `num` → `tn`); any freshness ages → the strip's own `tone()` from the kit.
- `HistoryTab.tsx:10` `COLOURS` → kit `SERIES_COLOURS`.
- `SeasonTab.tsx:46` `HEAD_COLOURS` → kit `SERIES_COLOURS`; `:259` stroke `var(--color-info)` → `var(--color-text)`.
- `ReviewTab.tsx:23-28` `LABEL_VARIANT` → `Record<ReviewLabel, ChipTone>` with Brilliant/Good `up`, Aligned `neutral`, Inaccuracy/Blunder `down` (a grade is a direction relative to the plan); `:74` `not graded` → `<Chip>`; `:106-109` `late run` → `<Chip tone="warn">` (doubt about the grade); `Stat`s at `:136-139` → `<StatRow>`.
- `JournalTab.tsx:26` `late run` → `<Chip tone="warn">` and `JournalTab.test.tsx:82` → `data-tone` `warn`; `:86` stroke `var(--color-info)` → `var(--color-text-muted)` (the model's line; "you" is `var(--color-text)`).
- `SettingsTab.tsx`: leftovers.

- [ ] **Step 2: Run the suite; retarget class assertions, fix behaviour**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -8`. Same rule as Task 10. Then confirm nothing is left:

```bash
grep -rnE "text-(sage|rust|info)|border-(sage|rust|info)|bg-(sage|rust|info|card)|rounded-(card|full)|shadow-|gradient|difficultyBackground|var\(--color-(sage|rust|info|card)\)|<Badge|text-(moss|amber)|bg-surface|\bnum\b" src/hubs src/kit --include='*.tsx' --include='*.ts' | grep -v "\.test\." | grep -v "src/kit/Badge.tsx" | grep -v "src/kit/scale.ts"
```

Expected: no output (Badge.tsx and scale.ts are the aliases Task 12 deals with).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hubs
git commit -m "style(v14): sweep — Players, League, Live and Model on the ledger rules; one grey chart palette

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---

## Task 12 — the rules, pinned; the aliases, retired

**Files:**
- Create: `frontend/src/kit/tokens.test.ts`
- Modify: `frontend/src/styles/theme.css`, `theme.test.ts`, `kit/scale.ts`, `scale.test.ts`, `kit/index.ts`

- [ ] **Step 1: Write the rules test**

Create `frontend/src/kit/tokens.test.ts`:

```ts
// @vitest-environment node
// v14 (spec §7): the design rules that can be pinned mechanically. Reads the
// sources rather than rendering anything, so a class that drifts back in is
// caught wherever it lands.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return walk(path)
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
  })
}

const FILES = [...walk(join(SRC, 'hubs')), ...walk(join(SRC, 'kit'))]
const rel = (path: string) => path.slice(SRC.length)

function offenders(pattern: RegExp, allow: string[] = []): string[] {
  return FILES
    .filter((path) => !allow.some((a) => rel(path).endsWith(a)))
    .flatMap((path) => readFileSync(path, 'utf8').split('\n')
      .map((line, i) => (pattern.test(line) ? `${rel(path)}:${i + 1}` : null))
      .filter((hit): hit is string => hit !== null))
}

describe('the ledger rules (spec §3–§5)', () => {
  it('has no rounded-full, no card radius, no shadow, no gradient', () => {
    expect(offenders(/rounded-full|rounded-card|shadow-|gradient/)).toEqual([])
  })

  it('has no raw hex outside theme.css and the bundled plain shirt', () => {
    // The plain shirt is an inline SVG data URI whose two greys are part of
    // the drawing, not of the palette.
    expect(offenders(/#[0-9a-fA-F]{6}\b/, ['kit/PlayerCard.tsx'])).toEqual([])
  })

  it('uses the mono face only in the job log and the plan trace', () => {
    expect(offenders(/font-mono/, ['kit/JobLog.tsx',
      'hubs/planning/PlannerBoard.tsx'])).toEqual([])
  })

  it('uses tabular figures, never the retired num class', () => {
    expect(offenders(/["'` ]num["'` ]/)).toEqual([])
  })

  it('never names a retired colour', () => {
    expect(offenders(
      /(text|bg|border|from|to|ring)-(sage|rust|info|card)\b|--color-(sage|rust|info|card)\)/,
    )).toEqual([])
  })

  it('never names a class no token defines', () => {
    expect(offenders(/text-moss|text-amber|bg-surface/)).toEqual([])
  })

  it('composes Chip, not Badge, everywhere but the alias itself', () => {
    expect(offenders(/<Badge\b|\bBadge,|\{ Badge\b/, ['kit/Badge.tsx',
      'kit/index.ts'])).toEqual([])
  })

  it('draws fixture difficulty as a tone, never a ramp', () => {
    expect(offenders(/difficultyBackground/)).toEqual([])
  })
})
```

- [ ] **Step 2: Run it to see what is left**

Run: `cd frontend && npx vitest run src/kit/tokens.test.ts`
Expected: the only failures are `difficultyBackground` (still defined in `scale.ts`) and anything the sweep missed. Fix the misses in their files now.

- [ ] **Step 3: Retire the aliases**

- `frontend/src/kit/scale.ts`: delete `difficultyBackground`; `scale.test.ts`: delete its tests; `kit/index.ts`: drop its export.
- `frontend/src/styles/theme.css`: delete `--color-card`, `--color-info` and `--radius-card` from all three blocks; delete `.num` from the `.tn, .num` rule and the sentence about it in the comment above (leave `.tn`); leave `--color-sage` and `--color-rust` declared (spec §3: one cycle) with the comment reduced to "retired, unused, deleted next cycle".
- `frontend/src/styles/theme.test.ts`: `ALIASES` becomes `[['--color-sage', '--color-up'], ['--color-rust', '--color-down']]`; the radius test adds `expect(css).not.toContain('--radius-card')`; the faces test adds `expect(css).not.toMatch(/\.num\b/)`.

- [ ] **Step 4: Run everything, commit, build, capture the final gate**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6` — Expected: green, `tokens.test.ts` included, no `Errors` line.

```bash
git add frontend/src/kit/tokens.test.ts frontend/src/kit/scale.ts frontend/src/kit/scale.test.ts \
  frontend/src/kit/index.ts frontend/src/styles/theme.css frontend/src/styles/theme.test.ts
git commit -m "test(v14): the ledger rules pinned — no rounded-full, no shadow, no gradient, no raw hex, mono in two files, no retired colour; card/info/radius-card/num retired

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
cd frontend && npm run build 2>&1 | tail -2 && cd ..
lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || (uv run gaffer ui --no-open-browser --port 8927 &)
frontend/scripts/shots.sh sweep
```

Look at all twelve PNGs against the spec's §5 and the four mockups. Report plainly what matches and what does not. 🛑 **STOP: the orchestrator shows these to the user; the user's approval is the gate.**

---

## Task 13 — the documentation

**Files:**
- Modify: `docs/GUIDE.md`, `docs/superpowers/ROADMAP.md`

Read `docs/superpowers/CONVENTIONS.md`'s preamble and the v13 entries in both files first (`grep -n "v13" docs/GUIDE.md docs/superpowers/ROADMAP.md`) and match their register: the GUIDE is written for a reader, the ROADMAP for an auditor.

- [ ] **Step 1: GUIDE**

In `docs/GUIDE.md`, in the section that describes the web UI (find it with `grep -n "theme\|design language\|kit/" docs/GUIDE.md`), replace the description of the design language with a short subsection titled **The dark ledger (v14)** that says, for a reader: dark by default with light as an override of the same tokens; what each colour means (the eight rules of spec §4, in prose, one sentence each); the components a page is made of (Section, Stat, Button/Segmented, Chip, Bar, Callout, DataTable, the pitch); where the tokens live (`frontend/src/styles/theme.css`) and that `frontend/src/kit/tokens.test.ts` is the rule-book a contributor's change is held to; how to take the gate screenshots (`frontend/scripts/shots.sh <stage>`, the dark flag, the server on 8927). Add a line to the v14 row of whatever version table the GUIDE keeps (§11/§12 per the v13 commit).

- [ ] **Step 2: ROADMAP**

In `docs/superpowers/ROADMAP.md`: add a **v14 — the dark ledger** block under Shipped in the same shape as v13's (what was decided and where — the spec commit `bb6ae40`; what shipped — the token set, the primitives, the five reworks, the sweep, the rules test; the gate — "screenshot approval by the user, no replay"; the rulings R1–R12 by number with one line each; the suite counts after the branch, read from the final `vitest run` line; pins unchanged 48/12/57). Refresh the **Where things stand** paragraph: v14 merged (leave the commit hash as `<merge>` for the orchestrator to fill), the open security incident unchanged, next the §6 replay and the model cycle from the 2026-09-04 review.

- [ ] **Step 3: Commit**

```bash
git add docs/GUIDE.md docs/superpowers/ROADMAP.md
git commit -m "docs: v14 in the GUIDE (the dark ledger, the rules, the gate) and the ROADMAP (block, rulings, position)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke"
```

---

## After the plan (orchestrator only)

1. Final whole-branch review; `.venv/bin/pytest -q 2>&1 | tail -3` must read 4110 passed; `cd frontend && npx tsc --noEmit && npx vitest run`.
2. The user's approval of the `sweep` screenshots.
3. `git switch main && git merge --ff-only v14-ledger`; fill the ROADMAP's `<merge>` hash in a follow-up docs commit.
4. Security ritual before the push. The TOML field is `api_key` inside the `[odds]` table (the dataclass field is `odds_api_key`; grepping for that name extracts an empty pattern, which matches every file): `V="$(sed -n '/^\[odds\]/,/^\[/p' config.toml | grep '^api_key' | cut -d'"' -f2)"`, require `${#V}` ≥ 8, then `git grep -c "$V" HEAD` must print nothing and `git show main:config.toml` must fail. Then `git push`.
5. Memory: the project file's v14 line.

## Self-review

- **Spec coverage.** §3 tokens → Task 1 (R1 for the radius names). §5 components: Section (T3), Stat (T3/T6), Buttons + JobButton + toggles (T2/T3/T6/T9), Tabs (T2/T9), Chip (T2, sweep), DataTable (T4), Nav (T5), PageHeader (T3), FreshnessStrip (T4, R2), Pitch (T7, R3), Warning banner (T2/T6), Inputs (T2/T9), Toast/Skeleton/EmptyState/ExplainModal (T3/T4). §6 reworks: 1 → T6, 2 → T7, 3 → T8, 4 → T5, 5 → T6/T9. §7: branch, order, screenshots (T0 + three gates), tests policy, `tokens.test.ts` (T12), pins untouched. §8: charts take token colours (R6, T10–T11).
- **Placeholders.** The sweep tasks list files and the exact replacement per site rather than full code for 25 files; the outcome is enforced by `tokens.test.ts`, and the judgement calls (which `negative` is a direction and which is doubt) are named per file. No "TBD".
- **Type consistency.** `Bar` props (`fraction`, `text`, `tone`, `mark`, `width`, `testId`) are used identically in T3 (ThresholdBar), T4 (ExplainModal), T6 (chip meter), T8 (moves, ladder, sensitivity) and the sweep. `Chip` `tone` values `up|down|warn|neutral` throughout; `Badge` maps onto them. `Callout` `tone` `note|warn|error`. `Segmented` takes `options/value/onChange/label`; `segmentClass(active)` for controls with their own ARIA. `Stat` props `unit/context/meter` from T3 are what T6 passes. `DataTable.selected` (T4) is what League's standings use (T11). `difficultyTone` (T2) is what T7/T10/T11 call; `difficultyBackground` dies in T12 after its last caller dies in T11.
