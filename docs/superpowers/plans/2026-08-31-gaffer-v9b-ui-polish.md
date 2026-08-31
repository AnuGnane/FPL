# Gaffer v9b UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spread player identity everywhere a player is named, make waiting and acting feel acknowledged, and survive a phone screen. Nothing trains, nothing solves, nothing is recomputed, and **no Python file changes at all** — every seam this cycle opens is a React component reading an endpoint that already exists.

**Architecture:** two new kit primitives and six wiring passes. `kit/Skeleton.tsx` is the *job*-wait idiom (`Loading` stays the *fetch*-wait idiom), and `kit/Toast.tsx` is a module-level store plus one outlet in `AppShell` — a store rather than a React context because the components that raise toasts (`PinDialog`, `OverridesCard`) are mounted in tests that never render `AppShell`, and a provider they must be wrapped in is a provider every test file has to learn about. Everything else is composition: v9a's `PlayerCard` at `size='chip'` replaces the bare `PlayerName` on three surfaces, `ExplainModal` grows a portrait from v9a's `/api/assets/photo/{code}`, the Planning timeline joins the fixture ticker's own payload client-side, and the empty-state and 390px passes are edits inside components that already exist.

**Tech Stack:** React 19 + TypeScript + vitest + Tailwind. No Python, no uv, no new dependency.

---

## ⚠️ Read this before Task 1 — expectations must be rebased on merged `main`

This cycle **builds on `feat/gaffer-v9a`**, which is merging to `main` as this plan is written, and **a fix round is landing on that branch concurrently with this plan**. Two changes are known to be in flight and both touch files this plan edits:

1. **`frontend/src/kit/PlayerCard.tsx` gains a bundled-fallback path for a null `teamCode`** — instead of requesting `/api/assets/shirt/0` and letting the backend answer the 404-with-a-silhouette, the card short-circuits to the bundled asset client-side.
2. **`src/gaffer/web/routers/assets.py` gains content-type validation** on the fetched bytes.

Therefore: **every line number, every quoted snippet and every "the file currently reads…" in this plan describes the tree as inspected on 2026-08-31 and may be stale by the time you open the file.** Before each task, read the real file on merged `main` and implement against **the contracts stated here**, not against the excerpts. Specifically:

- Task 3 edits `PlayerCard`'s *layout branch*. If the fix round has restructured the render, keep this plan's **contract** — `size='pitch'` renders exactly as it does on merged `main`, `size='chip'` renders horizontally — and re-derive the diff. Do not paste this plan's version of the file over a newer one.
- The `teamCode === null → bundled shirt` behaviour Task 3 relies on may already be implemented by the fix round. If it is, **do not implement it twice**; assert it and move on.
- The frontend and Python suite baselines below are placeholders until you measure them.

```bash
git checkout main && git pull --ff-only && git checkout -b feat/gaffer-v9b
```

**Confirm the prerequisite before Task 1** (v9a must be merged, or nothing in D1 or D6 has anything to consume):

```bash
test -f frontend/src/kit/PlayerCard.tsx \
  && test -f src/gaffer/web/routers/assets.py \
  && test -f src/gaffer/web/identity.py \
  && echo "v9a present"
# If this prints nothing, stop: this cycle has no tree to build on.
```

**Measure the baselines and write them into this file's header before Task 1:**

```bash
uv run pytest -q                      # record: <N> passed
cd frontend && npx vitest run          # record: <N> passed, <M> skipped
```

Baselines (fill in): **python `____` tests; frontend `____` tests + `____` skipped.** Every task's final run must leave both suites green.

---

**Protected — must show zero diffs at the end (Task 9 audits this). This cycle authorizes no exceptions at all:**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`,
`src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py` — v6, v7*, v8a, v8b, v8c, v8d, v8e, v8f, v8g **and `tests/test_v9a_degradation.py`, which is pre-existing the moment v9a merges**,
`scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`, and the whole of `src/gaffer/optimize/`. This cycle imports nothing from any of them.

**Stronger than protected: this cycle changes no Python at all.** `git diff main --stat -- 'src/**/*.py' 'tests/**/*.py' 'scripts/**/*.py'` must be **empty** at Task 9. Every feature below was checked against the endpoints already on disk, and the one that looked like it needed a new field (the `ExplainModal` portrait) does not — see A5. If a task appears to need a Python edit, **the plan is wrong: stop and report** rather than editing.

Zero new job kinds (the count stays 12), zero new plists, **zero new config keys** — a config key would break the field-count pin inside `tests/test_v8f_degradation.py`, which is protected.

**No `tests/test_v9b_degradation.py`.** Spec §1 G2 is explicit: a frontend-only cycle earns no Python rail file, because a rail that pins nothing is a file that has to be maintained for ever. The G2 rails live in vitest and are listed per task.

**Staging rule:** every `git add` below names exact files. **Never `git add -A`.** Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `src/gaffer/web/static/` or `config.toml`. `data/live/assets/` fills with cached shirts and photos the moment you open a page — it is untracked and must stay that way.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 9 is the checklist, unfilled.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Twelve things D1–D6 do not pin — several of them because the spec was written against an assumption the tree does not hold. Each is decided here once so no task decides it twice.

**A1 — `SensitivityCard` lives on Planning, not This Week.** Spec D2 names `hubs/this-week/SensitivityCard.tsx`. There is no such file. The component is `frontend/src/hubs/planning/SensitivityCard.tsx`, rendered by `WhatIfTab`. Task 4 edits the real path. (Spec D5 names `hubs/this-week/DigestCard.tsx`, which *is* correct.)

**A2 — v9a's `chip` size is laid out horizontally by this cycle, because a vertical fixed-width card cannot sit in a table row.** `PlayerCard`'s class list is `flex w-[76px] flex-col items-center …` for both sizes: a 76px-wide vertical stack. That is right on grass and wrong in the first cell of Live's eight-column table, where it would triple the row height and force the table wider than a phone. v9a's own docstring anticipates this — "v9b's Live rows, league compare and review lanes want him small" — so the layout branch is v9b's to add.

Task 3 therefore branches the wrapper: `pitch` keeps the class string, the fixture chip, and the centred stack **exactly as merged `main` has them** (v9a's `SquadPitch.test.tsx` and `PlayerCard.test.tsx` pin that rendering and both must stay green untouched); `chip` becomes an `inline-flex` row — 24px shirt, then name and the team/xPts line stacked beside it, no fixture chip. `PlayerCard.tsx` is not protected, and this is the one edit this cycle makes to it besides A3.

**A3 — `ep` becomes `number | null`, because two of the three new surfaces have no expected-points number for the player.** Live's `LivePlayer.remaining_ep` is `number | null | undefined`; `ReviewMiss` has no EP at all; `SquadPlayer` (RivalDetail) has a price and no EP. v9a declares `ep: number` and prints it through `fmtNum`. Passing `0` for "we do not have this number" would put a confident `0.0` under a player's name, which is the exact failure mode the house `fmtNum` exists to prevent — it already returns `—` for null and undefined, so widening the prop is a one-word type change and no render change. `SquadRow.ep` is a `number`, so the pitch is unaffected.

**A4 — the three new chip surfaces pass `teamShort={null}` and `teamCode={null}`, and that is the honest answer, not a shortcut.** This is the largest thing the spec got wrong and it must not be papered over.

`LivePlayer` (`/api/live`) carries `code, name, position, points, …` and **no team field**. `SquadPlayer` (`/api/league/rivals/{id}`) carries `code, element, name, position, price, is_captain, multiplier` and **no team field**. Neither is enriched by v9a's `identity.py`, which decorates `/api/advice/latest` only. So a chip on Live or RivalDetail cannot name a club or request a real shirt from anything the page already has.

The three options were weighed:

1. Enrich the payloads server-side. **Rejected**: it is a Python diff, and this cycle has none (spec §2).
2. Join client-side from `/api/players` (whose `PlayerRow` *does* carry `team_code` and `team_name`) plus `/api/fixtures/ticker` (whose `teams[]` carry `short_name`), behind a session-cached hook. **Rejected for this cycle**: it is two extra fetches — one of them the ~600-row candidate pool — mounted on a page that polls every sixty seconds, to decorate a 24px image. It is a real feature with a real cost and it deserves its own decision, not a corner of a polish cycle. Recorded as the residual in Task 9.
3. Pass nulls and let v9a's fallback draw the bundled plain shirt. **Chosen.**

So the Live, RivalDetail and ReviewTab chips give the reader the shirt silhouette, the position, the name, the number the surface actually has, and — the thing they have never had — a click that opens the explain modal. They do not give team colours. G1's wording ("shirt + team") should be read as satisfied by the shirt *slot* being present and correct; the orchestrator will see grey shirts on those three surfaces and that is the designed state, not a bug. **Say so in the Task 9 checklist rather than letting the gate discover it.**

**A5 — the `ExplainModal` portrait needs no payload change whatsoever, and this was verified rather than assumed.** `/api/assets/photo/{player_code}` allowlists against the `code` column of `data/live/players.parquet`. `ExplainModal` already receives `code` as a prop — every caller (`PlayerName`, and the three new hosts in Task 3) passes the same `code`, and `routers/players.py:explain(code)` filters `snapshot["code"] == code`, the identical column. The modal therefore has, in hand, exactly the integer the photo endpoint wants.

That is the whole feature: one `<img src={`/api/assets/photo/${code}`}>` in the header. **No payload carries a new field and none needs to.** The other payloads were checked for `code` too, and all three new surfaces have it: `LivePlayer.code`, `SquadPlayer.code`, `ReviewMiss.code`.

**A6 — ReviewTab's chips go on `misses`, not on the four lanes, because the lanes carry no player code.** Spec D1 says the four lanes "currently render raw name strings — no `PlayerName` at all, so no explain affordance either; the chip carries it". The chip cannot: `ReviewLane.mine` and `ReviewLane.model` are `string | null`, built server-side by `review.py` as `", ".join(_name(names, c) for c in …)` — a **comma-joined list of names for a set of players**, with the codes discarded before the payload is built. One string can name two players; there is no code to open a modal with, and matching a name back to a code client-side would be a guess dressed as a link.

`ReviewGw.misses` is `ReviewMiss[]` with `{code, name, over, gain}` — a real code per player. Task 3 puts the chips there: the "Flagged and skipped" line becomes a row of chips, each one clickable into the explain modal. The four lane rows keep their strings, unchanged and uncoloured.

Widening the lanes to carry codes is a `review.py` change and belongs to a cycle that ships Python. Recorded as a residual in Task 9.

**A7 — `Toast` is a module store with one outlet, not a React context.** `toast(tone, text)` is a plain function importable anywhere; `ToastOutlet` subscribes and renders; `AppShell` mounts exactly one outlet. The alternative — a provider — would have to wrap every existing test that renders `PinDialog`, `OverridesCard`, `DraftsTab` or a whole hub, because none of them render `AppShell` (see `hubs/responsive.test.tsx`, which renders bare hubs inside a `MemoryRouter`). A store means `toast()` outside an outlet is a silent no-op rather than a crash, which is the correct behaviour for a component under test.

Module state outlives a test case, exactly as `useJob`'s `remembered` map does, so `resetToasts()` joins `resetJobSlots()` in `frontend/vitest.setup.ts`. The cap is three and it drops the **oldest** (`slice(-3)`): a burst of failures should leave the newest three on screen, not the first three. Auto-dismiss is scheduled inside `toast()` itself rather than in an effect in the outlet, so a toast raised while no outlet is mounted still expires and cannot accumulate.

**A8 — `Skeleton` is the job-wait idiom and `Loading` is untouched.** Same contract as `Loading` — occupy the frame the data will fill, inside a `Card` — but pulsing bars instead of a sentence, because a solve is tens of seconds and a static "Loading…" for that long reads as a hang. `Loading` is not modified, not deprecated, and not re-pointed at `Skeleton`: a fetch that resolves in 80ms must not flash a pulse animation.

**A9 — there is no `JobLog` line to put under three of the four skeletons, and the plan says so rather than rendering an empty one.** Spec D2 asks for "the existing `JobLog` line underneath so long solves show liveness". `JobLog` renders lines from `useJobStream`. `WhatIfTab`, `ChipsTab` and `DraftsTab` use **`useJob`**, the polling hook, which exposes `{status, result, error}` and *no lines at all* — `JobLog` with `lines={[]}` and `error={null}` returns `null` by its own first branch, so wiring it there would add an import that renders nothing. `DraftsTab` already demonstrates the only honest use of it on a polled job: a failure, with `lines={[]}` and the error text.

So: the skeleton's own label carries liveness on the three polled panels, and the one panel with a real stream — `SensitivityCard`, whose `JobButton` owns a `useJobStream` and already renders `JobLog` under itself — gets the skeleton *and* the log, which is what D2 describes. Making that work needs one additive kit prop (A10).

**A10 — `JobButton` gains an optional `onRunning` callback.** `SensitivityCard` renders `<JobButton kind="sensitivity" onDone={load} />` and has no idea whether the job is running, because the button owns the stream. `onRunning?: (running: boolean) => void` is the symmetric partner of the `onDone?: () => void` it already has: additive, optional, no existing caller changes, and it fires from the same effect that already watches `job.status`. The alternative — lifting `useJobStream` out of `JobButton` into every caller — is a refactor of a working kit component in a polish cycle.

**A11 — D6's join is player → team via v9a's advice enrichment, then team → fixture via the ticker.** Spec D6 says the strip is "joined client-side by team + GW", which presumes the timeline payload names a team. It does not: `PlanMove` is `{code, name, position, ep, price}`, and `/api/plan/{gw}` is written by `routers/plan.py`, which this cycle does not touch.

The team comes from the other endpoint Planning already fetches. `Planning.tsx` calls `/api/advice/latest` on mount and keeps only `body.gw`; after v9a that payload's six player keys carry `team_code`. So Planning builds `Map<playerCode, teamCode>` from the same response it already has — no new request — and hands it to `Timeline`, which fetches `/api/fixtures/ticker?weeks=<horizon length>` and indexes it by `` `${teamCode}:${gw}` ``.

**Which players' teams appear on a week card:** the ones that card already names — captain, vice, buys, sells — deduplicated by team, in that order. Not the whole XI: a 220px card cannot carry eleven chips, and a strip of eleven opponents is a fixture ticker, which is one tab away and better at it.

Every link in that chain is allowed to break, and each break is absent rather than guessed (spec D6's own rule): a player the advice payload never named has no team code and no chip; a team code the ticker has no cell for in that gameweek has no chip; a ticker fetch that fails leaves every strip absent and the rest of the timeline unchanged. The shade is `difficultyBackground` from `kit/scale.ts` on the ticker's own `cell.difficulty`, so a chip and the ticker's matching square are the same colour by construction, not by coincidence.

**A12 — the empty-state audit is smaller than D5 implies, because two of its four items are already done and one has no surface.** Verified on 2026-08-31:

- `DigestCard`'s inline "No digest yet" paragraph — **real, fixed in Task 7.**
- `ReviewTab`'s pre-first-review state — **already an `EmptyState`** with `action="gaffer review"` (`ReviewTab.tsx:145`). No change; Task 7 pins it instead so it cannot regress.
- "the watchlist-empty explorer star column hint" — **no such surface exists.** The watchlist has no list view anywhere in the frontend; `/api/watchlist` is read once in `Players.tsx` purely to decide which stars are filled. There is nothing to be empty. Task 7 does not invent one, and Task 9 records it.
- `QualityTab`'s pre-evaluate cards — **mostly already `EmptyState`s** (`No penalty tracker yet`, `Nothing evaluated yet`). The one card-level free-text state left is the points scatter's "No graded gameweek yet — …" paragraph, which Task 7 converts. The `DataTable empty={…}` one-liners (`No finished gameweek yet.`, `Nothing scored yet.`) stay as they are: `EmptyState`'s bordered, centred, icon-topped block inside a table's own empty slot is a card inside a card.

Task 7 adds two genuinely-missing ones the audit turned up — `DraftsTab`'s "No drafts yet." and `SensitivityCard`'s "No sensitivity report yet." — because both are exactly D5's shape: a state with a specific button that fixes it, currently rendered as a shrug.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `frontend/src/kit/Skeleton.tsx` | Create | T1: the job-wait frame. |
| `frontend/src/kit/Skeleton.test.tsx` | Create | T1. |
| `frontend/src/kit/Toast.tsx` | Create | T1: store + outlet. |
| `frontend/src/kit/Toast.test.tsx` | Create | T1. |
| `frontend/src/kit/index.ts` | Modify (append) | T1. |
| `frontend/src/kit/index.test.ts` | Modify | T1: the barrel pin. |
| `frontend/src/kit/AppShell.tsx` | Modify (both branches) | T1: mount the outlet. |
| `frontend/src/kit/AppShell.test.tsx` | Modify | T1. |
| `frontend/vitest.setup.ts` | Modify | T1: `resetToasts()`. |
| `frontend/src/kit/ExplainModal.tsx` | Modify (header) | T2: the portrait. |
| `frontend/src/kit/ExplainModal.test.tsx` | Modify | T2. |
| `frontend/src/kit/PlayerCard.tsx` | Modify (layout branch, `ep` type) | T3: A2, A3. |
| `frontend/src/kit/PlayerCard.test.tsx` | Modify (append) | T3. |
| `frontend/src/hubs/Live.tsx` | Modify (player cell) | T3. |
| `frontend/src/hubs/Live.test.tsx` | Modify | T3. |
| `frontend/src/hubs/league/RivalDetail.tsx` | Modify (`SquadList`) | T3. |
| `frontend/src/hubs/league/RivalDetail.test.tsx` | Create or modify | T3. |
| `frontend/src/hubs/model/ReviewTab.tsx` | Modify (`misses`) | T3. |
| `frontend/src/hubs/model/ReviewTab.test.tsx` | Modify | T3. |
| `frontend/src/kit/JobButton.tsx` | Modify (`onRunning`) | T4: A10. |
| `frontend/src/kit/JobButton.test.tsx` | Modify | T4. |
| `frontend/src/hubs/planning/WhatIfTab.tsx` | Modify | T4. |
| `frontend/src/hubs/planning/ChipsTab.tsx` | Modify | T4. |
| `frontend/src/hubs/planning/DraftsTab.tsx` | Modify | T4, T5, T7. |
| `frontend/src/hubs/planning/SensitivityCard.tsx` | Modify | T4, T7. |
| `frontend/src/hubs/planning/*.test.tsx` | Modify | T4. |
| `frontend/src/hubs/Players.tsx` | Modify (`toggleStar`) | T5. |
| `frontend/src/hubs/Players.test.tsx` | Modify | T5. |
| `frontend/src/hubs/players/PinDialog.tsx` | Modify (`save`) | T5. |
| `frontend/src/hubs/players/PinDialog.test.tsx` | Modify | T5. |
| `frontend/src/hubs/planning/OverridesCard.tsx` | Modify (`drop`) | T5. |
| `frontend/src/hubs/planning/OverridesCard.test.tsx` | Modify | T5. |
| `frontend/src/hubs/planning/Timeline.tsx` | Modify (strip) | T6. |
| `frontend/src/hubs/planning/Timeline.test.tsx` | Modify | T6. |
| `frontend/src/hubs/Planning.tsx` | Modify (team map) | T6. |
| `frontend/src/hubs/this-week/DigestCard.tsx` | Modify | T7. |
| `frontend/src/hubs/this-week/DigestCard.test.tsx` | Modify | T7. |
| `frontend/src/hubs/model/QualityTab.tsx` | Modify (scatter card) | T7. |
| `frontend/src/hubs/model/QualityTab.test.tsx` | Modify | T7. |
| `frontend/src/hubs/Model.tsx`, `League.tsx`, `Players.tsx`, `Planning.tsx` | Modify (tab strips) | T8. |
| `frontend/src/hubs/responsive.test.tsx` | Modify | T8: the 390px rails. |
| `README.md` | Modify | T8. |
| `docs/superpowers/specs/2026-08-31-gaffer-v9b-ui-polish-design.md` | Modify (§5) | T9. |

---

## Task 1 — `Skeleton` and `Toast`: the two things the kit does not have

**Files:**
- Create `frontend/src/kit/Skeleton.tsx`, `frontend/src/kit/Skeleton.test.tsx`
- Create `frontend/src/kit/Toast.tsx`, `frontend/src/kit/Toast.test.tsx`
- Modify `frontend/src/kit/index.ts`, `frontend/src/kit/index.test.ts`
- Modify `frontend/src/kit/AppShell.tsx`, `frontend/src/kit/AppShell.test.tsx`
- Modify `frontend/vitest.setup.ts`

Both primitives ship in one task because they share one barrel edit and one barrel pin, and splitting them would mean touching `kit/index.test.ts` twice for no reason.

- [ ] **Write the failing tests first.** Create `frontend/src/kit/Skeleton.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Skeleton from './Skeleton'

describe('Skeleton', () => {
  it('occupies a card frame and says what is being waited on', () => {
    render(<Skeleton title="Solving" label="Solving the board…" />)
    expect(screen.getByTestId('skeleton')).toBeInTheDocument()
    // The frame is the point (plan A8): the panel that is about to appear has
    // a border, and the wait for it must not collapse the layout.
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Solving')
    expect(screen.getByRole('status')).toHaveTextContent('Solving the board…')
  })

  it('draws the number of bars it was asked for', () => {
    const { container } = render(<Skeleton lines={5} />)
    expect(container.querySelectorAll('[data-testid="skeleton-bar"]'))
      .toHaveLength(5)
  })
})
```

Create `frontend/src/kit/Toast.test.tsx`:

```tsx
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ToastOutlet, {
  DISMISS_MS, MAX_TOASTS, currentToasts, resetToasts, toast,
} from './Toast'

beforeEach(() => { resetToasts(); vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); resetToasts() })

describe('Toast', () => {
  it('announces politely rather than interrupting', () => {
    render(<ToastOutlet />)
    act(() => { toast('positive', 'Pinned Haaland.') })
    // Polite, not assertive: an acknowledgement must not cut across whatever
    // a screen reader is in the middle of saying.
    expect(screen.getByTestId('toast-outlet'))
      .toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('Pinned Haaland.')).toBeInTheDocument()
  })

  it('keeps the newest three and drops the oldest', () => {
    render(<ToastOutlet />)
    act(() => {
      for (const n of [1, 2, 3, 4]) toast('negative', `failure ${n}`)
    })
    expect(screen.getAllByTestId('toast')).toHaveLength(MAX_TOASTS)
    // The oldest goes, not the newest: a burst of failures should leave the
    // three most recent on screen, and the first one is the least useful.
    expect(screen.queryByText('failure 1')).not.toBeInTheDocument()
    expect(screen.getByText('failure 4')).toBeInTheDocument()
  })

  it('dismisses itself', () => {
    render(<ToastOutlet />)
    act(() => { toast('positive', 'Saved.') })
    act(() => { vi.advanceTimersByTime(DISMISS_MS + 1) })
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('is a no-op, not a crash, with no outlet mounted', () => {
    // PinDialog and OverridesCard are rendered bare by their own suites, with
    // no AppShell anywhere (plan A7). A toast raised there must be silent.
    expect(() => toast('negative', 'nobody is listening')).not.toThrow()
    expect(currentToasts()).toHaveLength(1)
  })
})
```

Both fail: neither module exists.

- [ ] **Create `frontend/src/kit/Skeleton.tsx`:**

```tsx
import Card from './Card'

export interface SkeletonProps {
  /** The card's own title, when the frame the data will fill has one. */
  title?: string
  /** How many bars. Roughly the number of rows the answer will have. */
  lines?: number
  /** What is being waited on. Read out; never drawn. */
  label?: string
  className?: string
}

/**
 * The job-wait state.
 *
 * `Loading` is the fetch-wait state and stays exactly what it is (plan A8):
 * a sentence in a card, right for the eighty milliseconds a GET takes. A
 * solve is tens of seconds, and a static sentence held for that long reads as
 * a hang — so the panel a job will fill gets pulsing bars in the shape of the
 * answer instead, and the answer replaces them in the same frame rather than
 * appearing below a line of text that then vanishes.
 *
 * The bars are decorative and hidden from assistive technology; the label is
 * the only thing announced, and it goes through `role="status"` so it is read
 * politely when it appears.
 */
export default function Skeleton({
  title, lines = 3, label = 'Working…', className = 'mb-4',
}: SkeletonProps) {
  return (
    <Card title={title} className={className}>
      <div data-testid="skeleton" role="status" className="flex flex-col gap-2">
        <span className="sr-only">{label}</span>
        {Array.from({ length: lines }, (_, i) => (
          <span
            key={i}
            aria-hidden
            data-testid="skeleton-bar"
            className="block h-3 animate-pulse rounded-card bg-base"
            // Ragged rather than uniform: a stack of identical bars reads as a
            // component, and a stack of unequal ones reads as text about to
            // arrive. The width only ever shrinks, so the block stays a block.
            style={{ width: `${Math.max(40, 100 - i * 12)}%` }}
          />
        ))}
      </div>
    </Card>
  )
}
```

- [ ] **Create `frontend/src/kit/Toast.tsx`:**

```tsx
import { useEffect, useState } from 'react'

export type ToastTone = 'positive' | 'negative'

export interface Toast {
  id: number
  tone: ToastTone
  text: string
}

/** Three, and the oldest goes first (plan A7). */
export const MAX_TOASTS = 3
/** Long enough to read a sentence, short enough not to sit over the page. */
export const DISMISS_MS = 6000

let nextId = 1
let live: Toast[] = []
const listeners = new Set<(toasts: Toast[]) => void>()

function emit(): void {
  for (const listener of listeners) listener(live)
}

/**
 * Raise a toast. Importable anywhere, including where no outlet is mounted.
 *
 * A module store rather than a React context, deliberately (plan A7): the
 * components that acknowledge a write — `PinDialog`, `OverridesCard`,
 * `DraftsTab` — are rendered bare by their own suites and by
 * `hubs/responsive.test.tsx`, none of which mount `AppShell`. A provider they
 * had to be wrapped in would be a provider every test file has to learn
 * about, and forgetting it would be a crash rather than a missing toast.
 *
 * The copy is the caller's job and the contract is spec D3's: say what
 * happened. "Could not save the pin — the server did not answer" is a
 * sentence; "Error!" is a noise.
 */
export function toast(tone: ToastTone, text: string): number {
  const id = nextId++
  // slice(-MAX) keeps the newest: a burst of failures leaves the three most
  // recent on screen rather than the three the user has already read.
  live = [...live, { id, tone, text }].slice(-MAX_TOASTS)
  emit()
  // Scheduled here rather than in an effect inside the outlet, so a toast
  // raised while nothing is mounted still expires instead of accumulating in
  // module state until the tab is closed.
  if (typeof window !== 'undefined') {
    window.setTimeout(() => dismissToast(id), DISMISS_MS)
  }
  return id
}

export function dismissToast(id: number): void {
  const next = live.filter((t) => t.id !== id)
  if (next.length === live.length) return
  live = next
  emit()
}

/** For tests. Module state outlives a test case exactly as `useJob`'s
 *  remembered map does, so `vitest.setup.ts` clears both. */
export function resetToasts(): void {
  live = []
  nextId = 1
  emit()
}

export function currentToasts(): Toast[] {
  return live
}

export function useToasts(): Toast[] {
  const [shown, setShown] = useState<Toast[]>(live)
  useEffect(() => {
    listeners.add(setShown)
    // Re-read on subscribe: a toast raised between render and effect would
    // otherwise never reach this outlet.
    setShown(live)
    return () => { listeners.delete(setShown) }
  }, [])
  return shown
}

/** One outlet, mounted once by `AppShell`. */
export default function ToastOutlet() {
  const shown = useToasts()
  return (
    <div
      data-testid="toast-outlet"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-2 z-[60] flex
                 flex-col items-center gap-2 px-4"
    >
      {shown.map((t) => (
        <div
          key={t.id}
          data-testid="toast"
          data-tone={t.tone}
          className={'pointer-events-auto max-w-md rounded-card border '
            + 'bg-card px-3 py-2 shadow-lg '
            + (t.tone === 'negative'
              ? 'border-rust text-rust' : 'border-border text-text')}
        >
          {t.text}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Export both from the barrel.** Append to `frontend/src/kit/index.ts`, keeping the file's alphabetical-ish grouping:

```ts
export { default as Skeleton } from './Skeleton'
export type { SkeletonProps } from './Skeleton'
export {
  default as ToastOutlet, DISMISS_MS, MAX_TOASTS, currentToasts, dismissToast,
  resetToasts, toast, useToasts,
} from './Toast'
export type { Toast, ToastTone } from './Toast'
```

- [ ] **Extend the barrel pin.** In `frontend/src/kit/index.test.ts`, add the two components to the existing list and pin the raiser:

```ts
    for (const name of ['Badge', 'Card', 'DataTable', 'EmptyState',
      'PageHeader', 'PitchView', 'PlayerCard', 'PosBadge', 'Skeleton',
      'Sparkline', 'Stat', 'ThresholdBar', 'ToastOutlet']) {
```

and a new case:

```ts
  it('exports the toast raiser, so a hub never imports the module directly', () => {
    expect(typeof kit.toast).toBe('function')
    expect(kit.MAX_TOASTS).toBe(3)
  })
```

- [ ] **Mount the outlet in `AppShell`.** One outlet, in both the mobile and the desktop branch — it is `position: fixed`, so where it sits in the tree does not matter visually, but it must exist in both or a phone silently loses every acknowledgement. Import `ToastOutlet from './Toast'` and add `<ToastOutlet />` as the last child of the outer `div` in each branch.

- [ ] **Pin it in `frontend/src/kit/AppShell.test.tsx`:**

```tsx
  it('mounts one polite toast outlet in both layouts', () => {
    // Both, because the phone layout is a separate return and a toast that
    // only exists on a desktop is a write nobody on a phone is told about.
    for (const mobile of [false, true]) {
      stubMatchMedia(mobile)          // the suite's existing helper
      const { unmount } = render(
        <MemoryRouter><AppShell><p>hi</p></AppShell></MemoryRouter>)
      expect(screen.getByTestId('toast-outlet'))
        .toHaveAttribute('aria-live', 'polite')
      unmount()
    }
  })
```

Match the existing suite's helper for stubbing `matchMedia` rather than inventing one — read the file and reuse what is there.

- [ ] **Clear the store between tests.** In `frontend/vitest.setup.ts`, inside the existing `beforeEach`, after `resetJobSlots()`:

```ts
  const { resetToasts } = await import('./src/kit/Toast')
  resetToasts()
```

Dynamically imported for the same reason `useJob` is — a static import at the top of the setup file would pull the module graph in before a test file's own `vi.mock` calls are registered.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

```bash
git add frontend/src/kit/Skeleton.tsx frontend/src/kit/Skeleton.test.tsx \
  frontend/src/kit/Toast.tsx frontend/src/kit/Toast.test.tsx \
  frontend/src/kit/index.ts frontend/src/kit/index.test.ts \
  frontend/src/kit/AppShell.tsx frontend/src/kit/AppShell.test.tsx \
  frontend/vitest.setup.ts && git commit -m "$(cat <<'EOF'
feat: v9b — Skeleton and Toast, the two idioms the kit was missing

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the portrait in the explain modal

**Files:**
- Modify `frontend/src/kit/ExplainModal.tsx`
- Modify `frontend/src/kit/ExplainModal.test.tsx`

One place, every hub inherits it (spec D1). The endpoint is v9a's and the code is already in hand (A5) — this task adds an `<img>` and a failure path, and nothing else.

- [ ] **Write the failing tests.** Append to `frontend/src/kit/ExplainModal.test.tsx`:

```tsx
  it('asks this backend for the portrait, by the code it was opened with', async () => {
    render(<ExplainModal code={223094} onClose={() => {}} />)
    const photo = await screen.findByTestId('explain-photo')
    // Never premierleague.com: the frontend speaks only to this backend, and
    // a hotlinked face is the one request on the page that would tell a third
    // party who is reading it.
    expect(photo).toHaveAttribute('src', '/api/assets/photo/223094')
  })

  it('drops the portrait rather than leaving a broken image', async () => {
    render(<ExplainModal code={223094} onClose={() => {}} />)
    const photo = await screen.findByTestId('explain-photo')
    // The server answers a dead CDN with a bundled silhouette, so this path is
    // only reached when even that fails. A broken-image glyph in the header of
    // a modal about expected points is worse than no picture at all.
    fireEvent.error(photo)
    expect(screen.queryByTestId('explain-photo')).not.toBeInTheDocument()
  })
```

Import `fireEvent` alongside the suite's existing testing-library imports.

- [ ] **Add the portrait.** In `ExplainModal`, add one piece of state beside the others:

```tsx
  // Not a src swap to a local placeholder: the backend already answers a dead
  // upstream with the bundled silhouette (v9a), so reaching this means the
  // *fallback* failed too, and the honest response is no picture.
  const [photoFailed, setPhotoFailed] = useState(false)
```

Reset it in the existing `useEffect` keyed on `code`, next to `setData(null)`:

```tsx
    setPhotoFailed(false)
```

and turn the header's left-hand `<div>` into a row:

```tsx
          <div className="flex items-start gap-3">
            {!photoFailed && (
              <img
                data-testid="explain-photo"
                src={`/api/assets/photo/${code}`}
                // Decorative: the name is beside it in an h2, and a screen
                // reader reading "photo of Haaland" before the heading that
                // says Haaland is one statement too many.
                alt=""
                width={44}
                height={56}
                onError={() => setPhotoFailed(true)}
                className="rounded-card border border-border bg-base"
              />
            )}
            <div>
              {/* the existing h2 / label block, unchanged */}
            </div>
          </div>
```

The image is requested while `data` is still loading, deliberately: the photo depends only on `code`, so it lands before the breakdown and the header stops reflowing when the data arrives.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

```bash
git add frontend/src/kit/ExplainModal.tsx frontend/src/kit/ExplainModal.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: v9b — a face in the explain modal, from the cached asset endpoint

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — identity chips on Live, RivalDetail and ReviewTab

**Files:**
- Modify `frontend/src/kit/PlayerCard.tsx`, `frontend/src/kit/PlayerCard.test.tsx`
- Modify `frontend/src/hubs/Live.tsx`, `frontend/src/hubs/Live.test.tsx`
- Modify `frontend/src/hubs/league/RivalDetail.tsx` and its suite
- Modify `frontend/src/hubs/model/ReviewTab.tsx`, `frontend/src/hubs/model/ReviewTab.test.tsx`

**Re-read `PlayerCard.tsx` on merged `main` first.** The fix round may have restructured it (see the header warning). Implement the *contract*: `pitch` renders as it does on merged `main`; `chip` renders horizontally; `ep` accepts null.

Each host owns its own `ExplainModal`, because `PlayerCard` — unlike `PlayerName` — has no modal inside it. It exposes `onSelect(code)` and the host decides what that means, which is why the pitch can select without opening anything.

- [ ] **Write the failing tests.** Append to `frontend/src/kit/PlayerCard.test.tsx`:

```tsx
  it('lays the chip out along the row, not down it', () => {
    const { container } = render(
      <PlayerCard size="chip" code={1} name="Raya" position="GKP"
                  teamShort={null} teamCode={null} ep={4.2} />)
    const card = container.querySelector('[data-code="1"]')!
    // A 76px vertical stack is right on grass and wrong in the first cell of
    // an eight-column table, where it triples the row height (plan A2).
    expect(card.className).toContain('inline-flex')
    expect(card.className).not.toContain('flex-col')
    // The fixture chip is a pitch affordance: a table row has no space for
    // "MCI (H) Sat 15:00" and the reader is not choosing a captain here.
    expect(screen.queryByTestId('fixture-chip')).not.toBeInTheDocument()
  })

  it('prints an em dash, not a zero, for a player with no expected points', () => {
    // Live has `remaining_ep: null` for a player whose match is over, and
    // ReviewMiss has no EP at all. A confident 0.0 under a name is a lie
    // (plan A3).
    render(<PlayerCard size="chip" code={2} name="Salah" position="MID"
                       teamShort={null} teamCode={null} ep={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('still draws the pitch card exactly as it did', () => {
    render(<PlayerCard code={3} name="Haaland" position="FWD"
                       teamShort="MCI" teamCode={43} ep={7.1} fixture={null} />)
    // The pitch is v9a's and this cycle does not touch it: the fixture chip
    // is present and "Blank" is still the word for no fixture.
    expect(screen.getByTestId('fixture-chip')).toHaveTextContent('Blank')
  })
```

- [ ] **Widen `ep` and branch the layout in `PlayerCard.tsx`.** The prop:

```tsx
  /** `null` where the surface genuinely has no expected-points number for
   *  this player — Live once his match is over, a review miss, a rival's
   *  squad list. `fmtNum` prints an em dash for it (plan A3). */
  ep: number | null
```

Then restructure the render so the two sizes share every piece except their frame:

```tsx
  const pitch = size === 'pitch'

  const shirt = (
    <span className="relative shrink-0">
      <img
        src={shirtSrc(teamCode, position)}
        alt={teamShort ? `${teamShort} shirt` : 'shirt'}
        width={pitch ? 44 : 24}
        height={pitch ? 44 : 24}
        onError={(e) => { e.currentTarget.style.visibility = 'hidden' }}
        className={pitch ? 'mx-auto block' : 'block'}
      />
      {armband && (
        /* unchanged from merged main */
      )}
    </span>
  )

  const nameLine = (
    <span className={`flex items-center gap-1 text-xs text-text ${
      pitch ? 'mt-0.5 justify-center' : ''}`}>
      <span className="truncate">{name}</span>
      {news && (
        <Badge variant="negative" title={news}>
          {chanceOfPlaying === null ? 'News' : `${chanceOfPlaying}%`}
        </Badge>
      )}
    </span>
  )

  const metaLine = (
    <span className={`flex items-center gap-1 text-[10px] text-text-muted ${
      pitch ? 'justify-center' : ''}`}>
      {teamShort && <span>{teamShort}</span>}
      <span className="num">{fmtNum(ep)}</span>
      {multiplier !== null && multiplier > 1 && (
        <span className="num text-sage">{`×${multiplier}`}</span>
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
    ? 'flex w-[76px] flex-col items-center rounded-card border border-border '
      + 'bg-card px-1 py-1 text-center'
    // No fixed width: a chip sits in a table cell, a list row and a wrapping
    // strip, and each of those knows its own width better than the card does.
    : 'inline-flex max-w-full items-center gap-1.5 rounded-card border '
      + 'border-border bg-card px-1.5 py-1 text-left'
```

The `pitch` branch must produce the same elements in the same order with the same classes as merged `main` — v9a's `PlayerCard.test.tsx` and `SquadPitch.test.tsx` pin it, and **both must stay green without being edited**. If they go red, the refactor is wrong, not the test.

- [ ] **Live: the chip in the player cell.** Add state and the modal to `Live()`:

```tsx
  // PlayerCard has no modal inside it (that was PlayerName's bargain), so the
  // host owns one: `onSelect` names a code and the page decides what that
  // means.
  const [explain, setExplain] = useState<number | null>(null)
```

Replace the `<PlayerName …/>` inside the first `<td>` with:

```tsx
                      <PlayerCard
                        size="chip"
                        code={player.code}
                        name={player.name}
                        position={player.position}
                        // /api/live carries no team field and this cycle adds
                        // no server code (plan A4): the bundled plain shirt is
                        // the honest answer, not a guessed crest.
                        teamShort={null}
                        teamCode={null}
                        // What the model still expects from him, which is null
                        // once his matches are over — an em dash, not a zero.
                        ep={player.remaining_ep ?? null}
                        onSelect={setExplain}
                      />
```

and render the modal once, beside the closing fragment:

```tsx
      {explain !== null && (
        <ExplainModal code={explain} onClose={() => setExplain(null)} />
      )}
```

Import `ExplainModal` and `PlayerCard` from `../kit` and drop `PlayerName` from that import **only if nothing else in the file uses it** — check before deleting.

- [ ] **RivalDetail: the chip in the squad lists.** In `SquadList`, replace the `<PlayerName …/>` with a chip and lift the modal to the list (the four lists each render their own, which is fine — only one can be open at a time within a list, and `RivalDetail` renders four independent lists):

```tsx
function SquadList({ title, players }:
  { title: string; players: SquadPlayer[] }) {
  const [explain, setExplain] = useState<number | null>(null)
  return (
    <Card title={`${title} (${players.length})`} className="mb-4">
      {players.length === 0
        ? <p className="text-text-muted">Nobody.</p>
        : (
          <ul className="flex flex-col gap-1">
            {players.map((player) => (
              <li key={player.code} className="flex items-center gap-1.5">
                <PlayerCard
                  size="chip"
                  code={player.code}
                  name={player.name}
                  position={player.position}
                  teamShort={null}
                  teamCode={null}
                  // A rival's squad is priced, not projected: the payload has
                  // his price and no expected points (plan A3).
                  ep={null}
                  onSelect={setExplain}
                />
                <span className="num ml-auto text-text-muted">
                  £{player.price}m
                </span>
              </li>
            ))}
          </ul>
          )}
      {explain !== null && (
        <ExplainModal code={explain} onClose={() => setExplain(null)} />
      )}
    </Card>
  )
}
```

- [ ] **ReviewTab: chips on the misses, and the lanes left alone.** Per A6 the four lanes have no code and cannot carry a chip. Replace the flat "Flagged and skipped" sentence in `GwCard`:

```tsx
      {row.misses.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-sm
                        text-text-muted">
          <span>Flagged and skipped:</span>
          {row.misses.map((m) => (
            <span key={m.code} className="flex items-center gap-1">
              <PlayerCard
                size="chip"
                code={m.code}
                name={m.name}
                // The review payload names no position for a miss; the card
                // needs one only to pick the keeper's kit, and the plain shirt
                // is what a null team code draws anyway.
                position=""
                teamShort={null}
                teamCode={null}
                ep={null}
                onSelect={onSelect}
              />
              <span className="num">{`+${m.gain} over ${m.over}`}</span>
            </span>
          ))}
        </div>
      )}
```

`GwCard` takes an `onSelect` prop; `ReviewTab` owns the state and the modal, and passes it down, so the whole tab has one modal rather than one per gameweek card.

Leave `LaneRow` **exactly** as it is. Add a short comment above it saying why:

```tsx
// The lanes stay text. `mine` and `model` are comma-joined name strings built
// server-side out of a set of players whose codes are discarded before the
// payload is written, so there is no code to open a modal with and matching a
// name back to one client-side would be a guess wearing a link (plan A6).
```

- [ ] **Test each host.** In each suite, assert the chip opens the modal — that is the affordance the surface did not have:

```tsx
  it('opens the explain modal from a player chip', async () => {
    render(/* the hub, with the suite's existing fixture */)
    await userEvent.click(await screen.findByRole('button', { name: /Haaland/ }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })
```

and in ReviewTab's suite, pin A6 so a later cycle does not quietly fabricate lane links:

```tsx
  it('leaves the lane rows as text, because they carry no player code', () => {
    render(<ReviewTab />)
    // Not an oversight: ReviewLane.mine/model are joined name strings.
    expect(within(screen.getByTestId('lane-captaincy'))
      .queryByRole('button')).toBeNull()
  })
```

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

```bash
git add frontend/src/kit/PlayerCard.tsx frontend/src/kit/PlayerCard.test.tsx \
  frontend/src/hubs/Live.tsx frontend/src/hubs/Live.test.tsx \
  frontend/src/hubs/league/RivalDetail.tsx \
  frontend/src/hubs/league/RivalDetail.test.tsx \
  frontend/src/hubs/model/ReviewTab.tsx \
  frontend/src/hubs/model/ReviewTab.test.tsx && git commit -m "$(cat <<'EOF'
feat: v9b — identity chips on Live, rival squads and review misses

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — skeletons where a job fills a panel

**Files:**
- Modify `frontend/src/kit/JobButton.tsx`, `frontend/src/kit/JobButton.test.tsx`
- Modify `frontend/src/hubs/planning/WhatIfTab.tsx`, `ChipsTab.tsx`, `DraftsTab.tsx`, `SensitivityCard.tsx` and their suites

Four panels, one rule: while `queued|running`, the frame the answer will occupy shows a skeleton; on `done` the answer replaces it; on `error` the existing error card is what appears, never a skeleton on top of it.

- [ ] **Write the failing tests.** One per panel, on the same shape; here is the `WhatIfTab` form, to be adapted to each suite's existing mocking of `useJob` / `apiPost`:

```tsx
  it('fills the answer frame while the solve runs', async () => {
    render(<WhatIfTab />)
    await userEvent.click(screen.getByRole('button', { name: 'Re-solve' }))
    expect(await screen.findByTestId('skeleton')).toBeInTheDocument()
  })

  it('shows no skeleton once the job is done, and none when it failed', async () => {
    // The failure has its own card. A pulsing frame above an error message
    // says the thing that already failed is still coming.
    render(/* the tab with the suite's job mocked to 'error' */)
    expect(screen.queryByTestId('skeleton')).not.toBeInTheDocument()
  })
```

- [ ] **Add `onRunning` to `JobButton`** (A10). The prop:

```tsx
  /** Fired on every transition into and out of `running`, so the card that
   *  hosts the button can show a skeleton in the panel the job will fill.
   *  Optional: the button owns the stream, and lifting `useJobStream` into
   *  every caller to answer one question would be a refactor. */
  onRunning?: (running: boolean) => void
```

and inside the existing status effect, alongside the `onDone` branch:

```tsx
  useEffect(() => {
    onRunning?.(job.status === 'running')
  }, [job.status, onRunning])
```

A caller passing an inline arrow re-fires the effect on every render, which is harmless — the callback is idempotent and sets a boolean — but `SensitivityCard` wraps it in `useCallback` anyway.

Pin it:

```tsx
  it('tells its host when the run starts and when it stops', async () => {
    const seen: boolean[] = []
    render(<JobButton kind="sensitivity" onRunning={(r) => seen.push(r)} />)
    /* drive the suite's existing stream mock through running → done */
    expect(seen).toContain(true)
    expect(seen[seen.length - 1]).toBe(false)
  })
```

- [ ] **`WhatIfTab`:** import `Skeleton` and render it in the diff's place:

```tsx
      {busy && (
        <Skeleton title="Re-solving" lines={5}
                  label="Re-solving the board with your constraints…" />
      )}
      {diff && !busy && <PlanDiffTable diff={diff} />}
```

`!busy` on the diff so a *second* solve blanks the stale answer rather than pulsing beneath a result from the previous run — which is the specific lie this task exists to remove.

- [ ] **`ChipsTab`:** the same pair, inside the "Try it" flow, replacing `{diff && <PlanDiffTable diff={diff} />}`:

```tsx
      {busy && (
        <Skeleton title="Re-solving" lines={5}
                  label="Solving with the chip prefilled…" />
      )}
      {diff && !busy && <PlanDiffTable diff={diff} />}
```

- [ ] **`DraftsTab`:** the compare card's frame:

```tsx
      {(job.status === 'queued' || job.status === 'running') && (
        <Skeleton title="Comparing" lines={picked.length || 3}
                  label="Re-solving each draft against today's board…" />
      )}
```

placed above the existing `{result && …}` block, and the result guarded with the same condition so a re-compare clears the old table.

- [ ] **`SensitivityCard`:** it is a single card, so the skeleton replaces the card's *body*, not the card. Track the button's state:

```tsx
  const [running, setRunning] = useState(false)
  const onRunning = useCallback((r: boolean) => setRunning(r), [])
```

pass `onRunning` to the `JobButton` in the card's `action`, and gate the body:

```tsx
      {running
        ? (
          <div data-testid="skeleton" role="status"
               className="flex flex-col gap-2">
            <span className="sr-only">
              Re-solving the board twenty times with knocked expected points…
            </span>
            {[0, 1, 2, 3].map((i) => (
              <span key={i} aria-hidden data-testid="skeleton-bar"
                    className="block h-3 animate-pulse rounded-card bg-base"
                    style={{ width: `${100 - i * 12}%` }} />
            ))}
          </div>
          )
        : (/* the existing !data?.available and data?.available blocks */)}
```

Inline rather than `<Skeleton>` **only because this one lives inside a card that already exists** and `Skeleton` brings its own `Card`. If that duplication bothers you, the cleaner shape is to give `Skeleton` a `bare` prop and use it here; either is acceptable, but do not nest a `Card` inside a `Card`.

The `JobLog` under the button is already rendered by `JobButton` (A9), so this panel gets both the skeleton and the live log without any extra wiring — it is the only one of the four that can.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

```bash
git add frontend/src/kit/JobButton.tsx frontend/src/kit/JobButton.test.tsx \
  frontend/src/hubs/planning/WhatIfTab.tsx \
  frontend/src/hubs/planning/WhatIfTab.test.tsx \
  frontend/src/hubs/planning/ChipsTab.tsx \
  frontend/src/hubs/planning/ChipsTab.test.tsx \
  frontend/src/hubs/planning/DraftsTab.tsx \
  frontend/src/hubs/planning/DraftsTab.test.tsx \
  frontend/src/hubs/planning/SensitivityCard.tsx \
  frontend/src/hubs/planning/SensitivityCard.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: v9b — a skeleton in every panel a job is filling

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — toasts on the writes, and only on the writes

**Files:**
- Modify `frontend/src/hubs/Players.tsx` and its suite
- Modify `frontend/src/hubs/players/PinDialog.tsx` and its suite
- Modify `frontend/src/hubs/planning/OverridesCard.tsx` and its suite
- Modify `frontend/src/hubs/planning/DraftsTab.tsx` and its suite

Spec D3's boundary is the whole point of this task: **the star's success stays silent** — the code comment declaring that deliberate is respected, because the ☆→★ flip *is* the acknowledgement — and its **failure** speaks, because today a swallowed write leaves a star that says the player is on a list he is not on. The other three writes have no acknowledgement at all today beyond a server-side `print`, so both halves speak.

- [ ] **Write the failing tests.** In `Players.test.tsx`:

```tsx
  it('flips the star optimistically and reverts it with one toast on failure', async () => {
    apiPost.mockRejectedValue(new Error('the server did not answer'))
    render(<Players />)
    const star = await screen.findByRole('button', { name: 'star Haaland' })
    await userEvent.click(star)
    // The lie this fixes: a filled star for a write the server refused.
    expect(await screen.findByRole('button', { name: 'star Haaland' }))
      .toBeInTheDocument()
    expect(currentToasts()).toHaveLength(1)
    expect(currentToasts()[0].tone).toBe('negative')
  })

  it('stays silent when the star write succeeds', async () => {
    apiPost.mockResolvedValue({ rows: [{ code: 223094, note: '' }] })
    render(<Players />)
    await userEvent.click(
      await screen.findByRole('button', { name: 'star Haaland' }))
    await screen.findByRole('button', { name: 'unstar Haaland' })
    // Deliberate (spec D3): the filled star is the acknowledgement, and a
    // toast for every bookmark on a six-hundred-row table would be noise.
    expect(currentToasts()).toHaveLength(0)
  })
```

and the mirror pair in each of the other three suites, asserting a `positive` toast on success and a `negative` one on failure.

- [ ] **`Players.toggleStar`:** optimistic, reverting, and named. The row's name has to reach the handler, so pass it:

```tsx
  // A star is a bookmark and its success is the flip itself — no toast (spec
  // D3). Its *failure* is a different matter: the write was swallowed, so the
  // star stayed filled and claimed a player was on a list he was not on.
  const toggleStar = (code: number, name: string) => {
    const on = starred.includes(code)
    const before = starred
    setStarred(on ? starred.filter((c) => c !== code) : [...starred, code])
    const request = on
      ? apiDelete<WatchlistPanel>(`/api/watchlist/${code}`)
      : apiPost<WatchlistPanel>('/api/watchlist', { code, note: '' })
    request
      .then((panel) => setStarred(panel.rows.map((r) => r.code)))
      .catch((e) => {
        setStarred(before)
        toast('negative',
          `Could not ${on ? 'unstar' : 'star'} ${name} — ${errorText(e)}`)
      })
  }
```

with the column's `onClick={() => toggleStar(r.code, r.name)}`. Import `toast` from `../kit` and `errorText` from `../api/client`.

Exactly one toast per failure — the rail in the test — because the `.catch` is the only place that raises and there is no retry.

- [ ] **`PinDialog.save`:** both halves.

```tsx
      const panel = await apiPost<OverridesPanel>('/api/overrides', body)
      onSaved?.(panel)
      toast('positive', `Pinned ${name}. It applies to this gameweek only.`)
      if (panel.warning) setWarning(panel.warning)
      else onClose()
    } catch (e) {
      const text = errorText(e)
      setError(text)
      // Both: the inline line is for the person still looking at the dialog,
      // the toast is for the one whose eyes went back to the table.
      toast('negative', `Could not pin ${name} — ${text}`)
    }
```

The warning path still keeps the dialog up with its sentence — the pin *was* taken, so the positive toast is true.

- [ ] **`OverridesCard.drop`:** the unpin is a delete with no visible confirmation today beyond a row disappearing, which is indistinguishable from a failed delete followed by a refetch.

```tsx
  const drop = async (code: number, name: string) => {
    try {
      setData(await apiDelete<OverridesPanel>(`/api/overrides/${code}`))
      toast('positive', `Unpinned ${name}. The model's own minutes apply again.`)
    } catch (e) {
      toast('negative', `Could not unpin ${name} — ${errorText(e)}`)
      load()
    }
  }
```

with `onClick={() => drop(row.code, row.name)}`.

- [ ] **`DraftsTab.save` and `.remove`:**

```tsx
      setDrafts(await apiPost<DraftList>('/api/drafts', body))
      toast('positive', `Saved "${name}".`)
      setName('')
    } catch (e) {
      const text = errorText(e)
      setError(text)
      toast('negative', `Could not save "${name}" — ${text}`)
    }
```

```tsx
    try {
      setDrafts(await apiDelete<DraftList>(
        `/api/drafts/${encodeURIComponent(draft)}`))
      toast('positive', `Deleted "${draft}".`)
    } catch (e) {
      toast('negative', `Could not delete "${draft}" — ${errorText(e)}`)
      load()
    }
```

Note the copy contract throughout: **the sentence says what happened**, names the thing it happened to, and — on success — says what it means where that is not obvious. No "Success!", no bare "Error".

- [ ] **What does not get a toast, and say so in a comment where each lives.** Fetch failures that already have an `EmptyState` or an error card (`Live`, `Planning`, `Timeline`, `SensitivityCard`, `WhatIfTab`'s infeasible card) keep their existing treatment: spec §3 puts toast-ifying them out of scope, and two reports of one failure is worse than one.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

```bash
git add frontend/src/hubs/Players.tsx frontend/src/hubs/Players.test.tsx \
  frontend/src/hubs/players/PinDialog.tsx \
  frontend/src/hubs/players/PinDialog.test.tsx \
  frontend/src/hubs/planning/OverridesCard.tsx \
  frontend/src/hubs/planning/OverridesCard.test.tsx \
  frontend/src/hubs/planning/DraftsTab.tsx \
  frontend/src/hubs/planning/DraftsTab.test.tsx && git commit -m "$(cat <<'EOF'
feat: v9b — acknowledge the writes, and revert the star that lied

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — difficulty chips on the Planning timeline

**Files:**
- Modify `frontend/src/hubs/planning/Timeline.tsx`, `frontend/src/hubs/planning/Timeline.test.tsx`
- Modify `frontend/src/hubs/Planning.tsx`

The join is A11's: player code → team code (from the advice payload Planning already fetches, enriched by v9a) → ticker cell (from the endpoint the ticker already calls) → `difficultyBackground`. **No new server field, and nothing is guessed** — every missing link is a missing chip.

- [ ] **Write the failing tests.** In `Timeline.test.tsx`:

```tsx
  it('tints each named team by the ticker s own difficulty for that week', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/plan/')) return Promise.resolve(PLAN)
      if (path.startsWith('/api/fixtures/ticker')) return Promise.resolve(TICKER)
      return Promise.reject(new Error('unexpected'))
    })
    render(<Timeline gw={12} teamByCode={new Map([[223094, 43]])} />)
    const chip = await screen.findByTestId('gw-fixture-43-12')
    // The same number and the same function as the ticker square: two ramps
    // for one idea is how two views end up disagreeing about how hard a
    // fixture is, in the same colour scale, on the same page.
    expect(chip).toHaveTextContent('ARS (H)')
    expect(chip.getAttribute('style'))
      .toContain(difficultyBackground(0.7).slice(0, 20))
  })

  it('draws no strip for a gameweek the ticker payload does not cover', async () => {
    // Spec D6: absent, not guessed. A horizon that runs past the ticker's
    // window is the ordinary case in the last weeks of a season.
    render(<Timeline gw={12} teamByCode={new Map([[223094, 43]])} />)
    expect(await screen.findByTestId('plan-week-99')).toBeInTheDocument()
    expect(screen.queryByTestId('gw-strip-99')).not.toBeInTheDocument()
  })

  it('draws no strip at all when the ticker fetch fails', async () => {
    // The timeline is the feature; the tint is a decoration on it. A failed
    // decoration must cost the decoration and nothing else.
    expect(await screen.findByTestId('plan-week-12')).toBeInTheDocument()
    expect(screen.queryByTestId('gw-strip-12')).not.toBeInTheDocument()
  })

  it('draws nothing for a player the advice payload never named', async () => {
    render(<Timeline gw={12} teamByCode={new Map()} />)
    expect(screen.queryByTestId('gw-strip-12')).not.toBeInTheDocument()
  })
```

- [ ] **Build the map in `Planning.tsx`.** It already fetches `/api/advice/latest` and throws away everything but `gw`:

```tsx
  const [gw, setGw] = useState<number | null>(null)
  // code → team code, from the six player keys v9a's identity.py decorates on
  // the way out of /api/advice/latest. Built from the response Planning
  // already makes, so the timeline's fixture chips cost no extra request
  // (plan A11). A player the advice never named is simply absent, and the
  // timeline draws no chip for him.
  const [teamByCode, setTeamByCode] = useState<Map<number, number>>(new Map())

  useEffect(() => {
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((body) => {
        setGw(body.gw)
        const map = new Map<number, number>()
        const a = body.advice
        for (const ref of [...a.xi, ...a.bench, ...a.buys, ...a.sells,
          a.captain, a.vice]) {
          if (ref && typeof ref.team_code === 'number') {
            map.set(ref.code, ref.team_code)
          }
        }
        setTeamByCode(map)
      })
      .catch(() => setMissing(true))
  }, [])
```

and pass it down: `{gw !== null && <Timeline gw={gw} teamByCode={teamByCode} />}`.

`a.captain` and `a.vice` are single `PlayerRef`s, not arrays, and a payload written before v9a's enrichment carries `team_code: undefined` — the `typeof` guard covers both, and `types.ts` already declares the field optional, so nothing there changes.

- [ ] **Fetch the ticker and draw the strip in `Timeline.tsx`:**

```tsx
export default function Timeline(
  { gw, teamByCode }: { gw: number; teamByCode?: Map<number, number> },
) {
  const [data, setData] = useState<PlanTimeline | null>(null)
  const [missing, setMissing] = useState(false)
  // The ticker's own cells, indexed by `${teamCode}:${gw}`. Null while it
  // loads and after any failure — the timeline is the feature and the tint is
  // a decoration on it, so a decoration that cannot load costs nothing else.
  const [cells, setCells] = useState<Map<string, TickerCell> | null>(null)
```

after the plan lands, ask for exactly the window the plan covers:

```tsx
  useEffect(() => {
    if (data === null || data.weeks.length === 0) return
    let live = true
    apiGet<TickerData>(`/api/fixtures/ticker?weeks=${data.weeks.length}`)
      .then((body) => {
        if (!live) return
        const map = new Map<string, TickerCell>()
        for (const team of body.teams) {
          for (const cell of team.cells) map.set(`${team.code}:${cell.gw}`, cell)
        }
        setCells(map)
      })
      .catch(() => { if (live) setCells(null) })
    return () => { live = false }
  }, [data])
```

`TickerCell` is not a named export of `types.ts` — the shape is inline inside `TickerData`. Declare the alias locally rather than editing `types.ts` (which would move `types.test.ts`'s lockstep pin for a type the server never sends):

```tsx
type TickerCell = TickerData['teams'][number]['cells'][number]
```

Then the strip, inside the week card under the captain line:

```tsx
            {(() => {
              // The teams this card already names — captain, vice, buys,
              // sells — deduplicated, in that order. Not the eleven: a 220px
              // card cannot carry eleven chips, and a strip of eleven
              // opponents is a fixture ticker, which is one tab away and
              // better at being one.
              if (!cells || !teamByCode) return null
              const named = [week.captain, week.vice, ...week.buys, ...week.sells]
              const seen = new Set<number>()
              const chips = []
              for (const move of named) {
                if (!move) continue
                const teamCode = teamByCode.get(move.code)
                if (teamCode === undefined || seen.has(teamCode)) continue
                seen.add(teamCode)
                const cell = cells.get(`${teamCode}:${week.gw}`)
                // Absent, not guessed (spec D6): no team, no cell, no chip.
                if (!cell) continue
                chips.push(
                  <span
                    key={teamCode}
                    data-testid={`gw-fixture-${teamCode}-${week.gw}`}
                    className="rounded px-1 text-[10px] text-text"
                    style={{ background: difficultyBackground(cell.difficulty) }}
                    title={`${move.name} — ${cell.home ? 'vs' : 'at'} `
                      + `${cell.opponent} (GW${week.gw}), difficulty `
                      + `${cell.difficulty}`}
                  >
                    {`${cell.opponent} (${cell.home ? 'H' : 'A'})`}
                  </span>,
                )
              }
              if (chips.length === 0) return null
              return (
                <div data-testid={`gw-strip-${week.gw}`}
                     className="mt-2 flex flex-wrap gap-1">
                  {chips}
                </div>
              )
            })()}
```

Import `difficultyBackground` from `../../kit` — the same function `FixtureTicker` and `FixtureMatrix` read, which is what makes the gate's "agreeing with the ticker's shades" check true by construction rather than by coincidence.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

```bash
git add frontend/src/hubs/planning/Timeline.tsx \
  frontend/src/hubs/planning/Timeline.test.tsx \
  frontend/src/hubs/Planning.tsx frontend/src/hubs/Planning.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: v9b — difficulty-tinted opponent chips on the timeline, joined client-side

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the empty-state audit

**Files:**
- Modify `frontend/src/hubs/this-week/DigestCard.tsx` and its suite
- Modify `frontend/src/hubs/model/QualityTab.tsx` and its suite
- Modify `frontend/src/hubs/planning/DraftsTab.tsx` and its suite
- Modify `frontend/src/hubs/planning/SensitivityCard.tsx` and its suite
- Modify `frontend/src/hubs/model/ReviewTab.test.tsx` (pin only)

Read A12 before starting: two of D5's four items are already done and one has no surface. This task converts the states that are genuinely free-text and **pins the ones that are already right** so the audit does not have to be repeated.

The contract, which every conversion must honour: `EmptyState.action` names **the real button label or the real shell command** that fixes the state. Not a description of one.

- [ ] **Write the failing tests.** In `DigestCard.test.tsx`:

```tsx
  it('names the schedule and the buttons when there is no digest', async () => {
    apiGet.mockResolvedValue({ available: false, digest: null })
    render(<DigestCard />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText(/17:00/)).toBeInTheDocument()
    expect(screen.getByText(/09:30/)).toBeInTheDocument()
    // The action names a real button on this very card, not a paraphrase.
    expect(screen.getByText(JOB_KIND_LABEL['digest-friday'])).toBeInTheDocument()
  })
```

and the analogous cases in the other three suites.

- [ ] **`DigestCard`'s no-digest state:**

```tsx
  if (!panel.available || panel.digest === null) {
    return (
      <Card title="Digest" className="mb-4" action={buttons}>
        <EmptyState
          title="No digest yet"
          detail="The Friday briefing is written at 17:00 and the Tuesday
                  debrief at 09:30, by the scheduled jobs. Neither has run
                  since the last artifact was cleared — the two buttons above
                  build one now, from the files already on disk."
          // The label on the card's own Friday button, read from the same
          // table it renders, so a rename cannot make this line stale.
          action={JOB_KIND_LABEL['digest-friday']}
        />
      </Card>
    )
  }
```

Import `EmptyState` from `../../kit` and `JOB_KIND_LABEL` from `../../types`.

- [ ] **`QualityTab`'s points scatter** (the `points.length === 0` half only — the one-graded-gameweek sentence stays prose, because that state is not empty, it is *insufficient*, and the card is telling the reader something true about statistics):

```tsx
  if (points.length === 0) {
    return (
      <Card title="Your points against the model’s" className="mt-4">
        <EmptyState
          title="No graded gameweek yet"
          detail="This compares what you scored against what the model's own
                  squad would have scored, for every gameweek FPL has
                  finalised. None has been graded yet."
          action="gaffer review"
        />
      </Card>
    )
  }
```

keeping the existing `points.length === 1` branch below it, unchanged.

- [ ] **`DraftsTab`'s "No drafts yet.":**

```tsx
        {drafts.drafts.length === 0
          ? (
            <EmptyState
              title="No drafts yet"
              detail="A draft is a set of What-If constraints under a name, so
                      it still means something after Thursday's price changes.
                      Set some constraints on the What-If tab, then name them
                      here."
              action="Save the current What-If"
            />
            )
          : (/* the existing list */)}
```

The action is the exact label on the button three lines above it.

- [ ] **`SensitivityCard`'s no-report state.** Keep the `failed` branch as prose — a server that did not answer is not an empty state and must not send the reader to press a button that is not the problem, which the existing comment says at length — and convert only the "nobody has swept yet" half:

```tsx
      {!data?.available && (failed
        ? (
          <p className="text-text-muted">
            The sensitivity report could not be read — the server did not
            answer.
          </p>
          )
        : (
          <EmptyState
            title="No sensitivity report yet"
            detail={data?.notice ?? 'The sweep re-solves the same board with '
              + 'every expected-points cell knocked by its own plausible '
              + 'error, and nothing has swept this board yet.'}
            action={JOB_KIND_LABEL.sensitivity}
          />
          ))}
```

- [ ] **Pin the two that were already right,** so the next audit does not have to re-derive A12. In `ReviewTab.test.tsx`:

```tsx
  it('already names the command for its pre-first-review state', async () => {
    apiGet.mockResolvedValue({ gws: [], summary: null })
    render(<ReviewTab />)
    // Audited 2026-08-31 and left alone: title, detail and an action that is
    // a real command. Pinned so a later pass does not "fix" it into prose.
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('gaffer review')).toBeInTheDocument()
  })
```

and the equivalent in `QualityTab.test.tsx` for `No penalty tracker yet` / `Nothing evaluated yet`.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

```bash
git add frontend/src/hubs/this-week/DigestCard.tsx \
  frontend/src/hubs/this-week/DigestCard.test.tsx \
  frontend/src/hubs/model/QualityTab.tsx \
  frontend/src/hubs/model/QualityTab.test.tsx \
  frontend/src/hubs/model/ReviewTab.test.tsx \
  frontend/src/hubs/planning/DraftsTab.tsx \
  frontend/src/hubs/planning/DraftsTab.test.tsx \
  frontend/src/hubs/planning/SensitivityCard.tsx \
  frontend/src/hubs/planning/SensitivityCard.test.tsx \
  && git commit -m "$(cat <<'EOF'
feat: v9b — every empty state names the button or command that fills it

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the 390px pass, and the docs

**Files:**
- Modify `frontend/src/hubs/Model.tsx`, `League.tsx`, `Players.tsx`, `Planning.tsx` (tab strips)
- Modify `frontend/src/hubs/planning/SensitivityCard.tsx`, `ChipsTab.tsx`, `DraftsTab.tsx` (unwrapped tables)
- Modify `frontend/src/hubs/responsive.test.tsx`
- Modify `README.md`

Spec D4 is right that this is targeted, not a rebuild: every recharts surface is already `ResponsiveContainer width="100%"`, and `kit/DataTable` already wraps itself in `overflow-x-auto`. The survey found exactly two families of offender.

**Offender 1 — the four tab strips.** `Tabs.List className="mb-4 flex border-b border-divider"` with five triggers at `px-3 py-2` is wider than 390px on Model (Quality / Journal / Review / History / Health) and Planning (Timeline / What-If / Drafts / Chips / Ticker), and `flex` with no wrap and no scroll pushes the body sideways.

**Offender 2 — three hand-rolled `<table className="w-full">` with no wrapper.** `SensitivityCard` (four columns), `ChipsTab`'s chip table and `DraftsTab`'s compare table (six columns) are raw tables outside any `overflow-x-auto`. `Live`'s eight-column table is already wrapped, and every `DataTable` wraps itself.

- [ ] **Write the failing tests.** Extend `frontend/src/hubs/responsive.test.tsx` — the file already renders all five hubs at phone width against a cold clone, which is the right harness. Add a second describe that renders them *with* fixtures:

```tsx
describe('a phone screen scrolls nothing sideways', () => {
  it('lets the tab strip scroll within its own bounds', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    const strip = await screen.findByRole('tablist')
    // Five tabs do not fit in 390px. The strip may scroll or wrap; what it
    // may not do is make the page wider than the phone.
    expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
  })

  it('wraps every wide table in its own scroller', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    for (const table of document.querySelectorAll('table')) {
      // Each table owns its overflow. A page-level scrollbar means one of
      // them is pushing the body, and the reader loses the nav to find out
      // which.
      expect(table.closest('.overflow-x-auto')).not.toBeNull()
    }
  })
})
```

Adapt the fixtures to whatever the suite already mocks; the assertion is what matters, not the data.

- [ ] **Fix the tab strips.** All four hubs share the same two lines. The `Tabs.List`:

```tsx
        <Tabs.List className="mb-4 flex overflow-x-auto border-b
                              border-divider">
```

and `TAB_CLASS` gains a no-shrink and a no-break, so a trigger scrolls rather than compressing into two lines of one word:

```tsx
const TAB_CLASS = 'shrink-0 whitespace-nowrap px-3 py-2 text-text-muted '
  + 'data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'
```

Apply to `Model.tsx`, `League.tsx`, `Players.tsx` and `Planning.tsx` — the constant is duplicated in each file today and this cycle does not consolidate it; four identical three-line constants are a smaller problem than a shared constant nobody can find.

`ChipsTab`'s segmented control (`Chip table` / `Wildcard`) is two buttons and already fits; leave it.

- [ ] **Wrap the three bare tables.** In `SensitivityCard`, `ChipsTab` and `DraftsTab`, put `<div className="overflow-x-auto">…</div>` around each `<table className="w-full">`, exactly as `Live.tsx:205` and `FixtureTicker.tsx:70` already do. Do not change a single cell.

- [ ] **Walk the checklist and fix what it turns up.** Spec D4's list, at 390px, is the acceptance criterion and the fix list is discovered at G1 — but do the desk pass now: the pitch (v9a's `SquadPitch` is `flex-wrap justify-center`, so it should reflow already — verify), `DigestCard`'s sections (a `<dl>` of wrapping prose — verify nothing truncates), and This Week's `Pitch | Table` toggle inside a card header that also carries the captain line (`flex flex-wrap` — verify). Record anything you change here in the commit message; record anything you *cannot* fix without a rebuild as a residual in Task 9 rather than half-fixing it.

- [ ] **Document what shipped.** In `README.md`, in the voice the file already uses:

  - one sentence in the This Week / UI section saying that a player's name is now a card wherever the page has room for one — Live's rows, a rival's squad, the review's flagged-and-skipped list — and that clicking it opens the same expected-points breakdown it always did, now with the player's face from the local asset cache;
  - one sentence saying that a panel a solve is filling shows the shape of the answer while it solves, rather than sitting blank;
  - one sentence saying that saving a pin, an override or a draft now says so, and that a failed star reverts rather than lying;
  - a line in the Planning section on the timeline's opponent chips: the same odds-implied difficulty and the same shades as the fixture ticker, drawn only where the plan names a player whose team the ticker covers.

- [ ] **Verify and commit.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

```bash
git add frontend/src/hubs/Model.tsx frontend/src/hubs/League.tsx \
  frontend/src/hubs/Players.tsx frontend/src/hubs/Planning.tsx \
  frontend/src/hubs/planning/SensitivityCard.tsx \
  frontend/src/hubs/planning/ChipsTab.tsx \
  frontend/src/hubs/planning/DraftsTab.tsx \
  frontend/src/hubs/responsive.test.tsx README.md && git commit -m "$(cat <<'EOF'
fix: v9b — nothing scrolls the body sideways at 390px

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — the gate checklist (orchestrator-run, unfilled)

**Files:**
- Modify `docs/superpowers/specs/2026-08-31-gaffer-v9b-ui-polish-design.md` (§5)

CONVENTIONS.md §7: the implementer builds this and does not run it. Fill in the **measured** G3 numbers from your own final run; leave every G1 box unchecked.

- [ ] **G3 first — suites, types, build, and the audits.**

```bash
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

The Python number must be **exactly the merged-`main` baseline** — this cycle adds no Python test and changes no Python line, so a moved number is a bug, not a result.

Then the audit that matters most this cycle:

```bash
git diff main --stat -- 'src/**/*.py' 'tests/**/*.py' 'scripts/**/*.py' \
  pyproject.toml config.example.toml
# must be empty — this is a frontend-only cycle
```

Then the protected diff, which must be **empty**:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
# must be empty

git diff main --stat -- 'tests/test_*_degradation.py'
# must be empty — including test_v9a_degradation.py, which is now pre-existing
```

And the pin audit, a zero by construction:

```bash
git diff main -- tests/test_web_job_kinds.py tests/test_web_job_kinds_v8b.py \
  tests/test_web_job_kinds_v8c.py tests/test_web_job_kinds_v8f.py \
  src/gaffer/config.py config.example.toml
# must be empty
```

Security ritual (CONVENTIONS.md §8): grep the whole branch diff for keys and tokens, confirm no `data/`, `reports/`, `models/`, `logs/`, `web/static/` or `config.toml` path appears in `git diff main --stat`, confirm no cached asset under `data/live/assets/` was staged, and confirm `git show main:config.toml` fails.

- [ ] **Write §5 into the spec file.** Replace the spec's §5 placeholder with the checklist below, G3 numbers filled in from the run above and every G1 box unchecked.

```markdown
## 5. Gate checklist (built by the implementer, run by the orchestrator)

**G3 — suites, types, build, audit (measured by the implementer):**

- [x] `uv run pytest -q` — <N> passed, identical to the merged-main baseline
      (this cycle changes no Python)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — <N> passed, <M> skipped (merged-main baseline <B> +
      <new> new)
- [x] `npm run build` — clean
- [x] Zero Python diff: `git diff main --stat` names no `src/**/*.py`,
      `tests/**/*.py`, `scripts/**/*.py`, `pyproject.toml` or
      `config.example.toml`
- [x] Protected diff empty: advise.py, set_pieces.py, optimize/**, jobs.py,
      routers/jobs.py, routers/whatif.py, test_advise.py, test_odds.py,
      test_web_jobs.py, every test_*_degradation.py **including v9a's**,
      s2_replay.py
- [x] Pin diff empty: job kinds still 12, no config field added
- [x] Security ritual clean; no data/, reports/, models/, logs/,
      web/static/ or config.toml in the branch diff, and no cached asset
      staged

**G2 — rails (vitest, no Python rail file this cycle):**

- [x] `Toast` renders `aria-live="polite"`, caps at three, drops the oldest,
      auto-dismisses, and is a silent no-op with no outlet mounted
- [x] `Skeleton` appears for `queued|running` on all four job panels and never
      for `done` or `error`
- [x] `ExplainModal` requests `/api/assets/photo/{code}` and removes the
      portrait on an image error rather than showing a broken glyph
- [x] A failed star reverts the optimistic flip and raises exactly one toast;
      a successful star raises none
- [x] `Timeline` renders no difficulty strip for a gameweek the ticker payload
      does not cover, for a player the advice never named, or when the ticker
      fetch fails
- [x] Every `EmptyState` action names a real button label or shell command
      (source-pinned, including the two audited-and-left-alone states)
- [x] Every `<table>` on a hub sits inside an `overflow-x-auto`, and every tab
      strip scrolls or wraps within its own bounds

**G1 — live, real season (orchestrator only):**

- [ ] Live's player rows, a rival's squad list and the review's
      flagged-and-skipped list show identity chips where bare names were, and
      clicking one opens the same explain modal as before.
- [ ] Those three surfaces show the **bundled plain shirt and no club label**
      — by design, not by failure: neither `/api/live` nor
      `/api/league/rivals/{id}` carries a team field and this cycle adds no
      Python (plan A4). Confirm it looks deliberate rather than broken.
- [ ] The explain modal shows the player's portrait. Empty
      `data/live/assets/`, kill the network, reload: the silhouette, with
      **no** broken-image icon and **no** console error.
- [ ] Network tab: every image request goes to `/api/assets/…` and none to
      premierleague.com.
- [ ] Fire a what-if solve: the answer panel shows a skeleton for the whole
      solve and the answer replaces it. No blank panel at any point, and a
      second solve does not pulse over the first one's result.
- [ ] Run a sensitivity sweep from its own card: skeleton **and** the live
      job log underneath.
- [ ] Pull the network mid-star: the star reverts and one failure toast
      appears saying which player and why.
- [ ] Star a player successfully: the star fills and **no** toast appears.
- [ ] Save an override, unpin one, save a draft, delete a draft: each says
      what happened, and each toast clears itself.
- [ ] At 390px (device toolbar) walk all six hubs: no body horizontal scroll
      anywhere, DigestCard readable with no truncated bits, the pitch
      reflowed, every tab strip reachable.
- [ ] Planning → Timeline: week cards show difficulty-tinted opponent chips
      whose shades match the Ticker tab's squares for the same fixtures, and a
      week past the ticker's window shows no strip rather than a grey one.

**Residuals to record in §4 after G1:**

- Live and rival squad chips carry no club identity (plan A4) — the fix is
  either a server-side enrichment of those two payloads or a session-cached
  client join over `/api/players` + the ticker. Neither belongs in a
  frontend-only cycle.
- Review lane rows carry no player code (plan A6), so the four lanes have no
  explain affordance. Widening them is a `review.py` change.
- D5's "watchlist-empty explorer star column hint" was not built: the
  watchlist has no list surface anywhere in the frontend, so there is nothing
  to be empty (plan A12).
```

- [ ] **Fill spec §4 (Outcome)** with what shipped, what did not, and any residual — and, per CONVENTIONS.md §4, transcribe the G1 evidence verbatim rather than summarising it. (Orchestrator, after G1.)

- [ ] **Commit the checklist.**

```bash
git add docs/superpowers/specs/2026-08-31-gaffer-v9b-ui-polish-design.md \
  && git commit -m "$(cat <<'EOF'
docs: v9b gate checklist with the measured G3 numbers, G1 unfilled

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Notes for the implementer

- **Rebase your expectations before every task, not just the first.** The fix round landing on `feat/gaffer-v9a` touches `PlayerCard.tsx` and `routers/assets.py`. Read the real file; implement the contract; never paste this plan's snippets over newer code.
- **Task order.** Task 1 must precede 4, 5 and 7 (they import `Skeleton`, `toast` and the barrel). Task 3 must precede nothing but is easiest after 2 (the modal it opens is already finished). Task 6 is independent of everything. Tasks 8 and 9 need all of the above.
- **There is no stop-point in this cycle, and no Python.** If a task finds itself wanting a server field, a config key or a job kind, the plan is wrong: stop and report. A4, A5, A6 and A11 each record a place where that temptation exists and why it was declined.
- **The star's silence on success is a feature.** `Players.tsx` carries a comment saying so and spec D3 endorses it. Do not "improve" it into a toast; do not remove the comment.
- **`kit/PitchView` and `kit/PlayerName` both stay.** v9a's A1 left `PitchView` exported, tested and pinned and said consolidating was v9b's call with both in front of it — this cycle declines: nothing here renders either pitch component except `SquadPitch`, and deleting kit surface during a polish pass is how the next cycle discovers it needed the thing. `PlayerName` keeps every dense-table caller it has (the explorer, `SquadTable`, `ChipsTab`, `QualityTab`); spec D1 is explicit that the chip is for card-shaped surfaces only.
- **Never stage a cached image.** `data/live/assets/` fills the moment a page with a shirt or a face loads. Every `git add` above names exact files.
