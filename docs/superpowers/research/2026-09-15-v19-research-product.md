# v19 product research — what the user does, where it hurts, what to take

## 1. The weekly journey (hub by hub)

1. **Thu 18:00** `com.gaffer.advise` (plist: Weekday 4, 18:00) runs `prices; train && advise`; since v17d advise chains the brief (GUIDE:429-430, 512).
2. **Thu evening** the user opens **This Week** and reads the pitch, the moves card, the restraint line ("free transfers only; the step to 1 hit was refused, 44%"), the ladder and **The week** brief (GUIDE:271-303).
3. **Fri 17:00** `digest-friday` fires a macOS notification (`digest.py:677`); the user reads the **This Week** digest/brief card (GUIDE:431-433).
4. **Fri–Sat** if a presser moves something: **Players → Explorer**, Pin the player, back to **This Week**, re-run (GUIDE:434-438).
5. **Or** **Planning → What-If**: lock/ban/force-in/must-sell, cap hits, re-solve, read the diff and sensitivity card (GUIDE:322-334).
6. **Deadline** the user applies the transfers by hand in the FPL app; gaffer never logs in (CLAUDE.md, GUIDE:438).
7. **Post-deadline** **This Week → "What I did and why"** opens: one of eight reason codes plus a line, only when the user deviated (GUIDE:345-349).
8. **Sat/Sun** **Live** hub polls (Live.tsx:83) for projected autosubs, provisional bonus, the race chart and the places above/below (GUIDE:386-390).
9. **Sat/Sun 12:30** `com.gaffer.field` banks ~300 top-10k squads; **League → Field** prices next week against them (GUIDE:375-384).
10. **Tue 09:00/09:30** `review` grades the ledger, `digest-tuesday` summarises it; the user reads **Model → Review** (deviation note + Deviations-by-reason) and **Model → Season** (GUIDE:442-445, 396-404).

## 2. Friction points (ranked by weekly exposure)

| # | Step | What is awkward | Smallest fix | Size | Where |
|---|---|---|---|---|---|
| 1 | Every step | Seven of nine launchd jobs are not loaded (GUIDE:1111-1135); `logs/advise.log` last written 2026-09-10, `prices.log` 09-11, `field.log` 09-12. The UI's freshness strip shows *file* age, not *job* health, so a dead collector reads as "old data" not "the job stopped". | Model → Health gains a row per plist: schedule, last log write, overdue flag. | M | both |
| 2 | Fri re-run | The web re-run button does not bank a same-day price reading the way the plist does, so a browser solve sees an empty price table and an untimed sale (GUIDE:1247-1250; v12 spec:343-348). | Chain `gaffer prices` in the advise job as an anonymous JobRegistry step, or warn on the button. | S | both |
| 3 | Pin → re-run | Pin lives on **Players → Explorer**, the re-run button on **This Week**; nothing on This Week says "n pins are live, re-run to apply". v17h also records a wasted cold fetch on the path change (v17h spec:465-468). | A pin count + re-run affordance on the This Week moves card. | S | UI |
| 4 | Tue debrief | The Tuesday digest re-emitted GW3 on 2026-09-15 and the card does not say the week it graded is not last week. | Digest card names its graded GW and says "GW4 not finalised yet". | S | both |
| 5 | Phone | Layout is one JS switch (`AppShell.tsx:24`); 17 Tailwind breakpoint utilities in the whole app. Every wide table is a horizontal scroller on a phone (pinned by `hubs/responsive.test.tsx`), and **Model** has zero breakpoints. | Card-per-row fallback for the three tables read on a phone: ladder rungs, moves, board. | M | UI |
| 6 | Phone writes | A bare `--lan` URL 403s on every write; the remedy is re-scan the QR or hand-append `?token=` (GUIDE:545-550, 1358-1361). | On 403, render a token input instead of only the sentence. | S | UI |
| 7 | Set pieces | The correction file is keyed by **code**, shown in exactly one place (the explain panel header), and one bad TOML header discards the whole file (GUIDE:470-483). | Copy-code button in the explain panel. | S | UI |
| 8 | First run | `FixtureTicker` has no cold-clone empty state and shows a raw callout for the 422 (v18e spec:254-257; v18f:199). | One sentence, as v18f said it was a wording decision. | S | UI |
| 9 | Live | The race trajectory is built client-side by polling, so closing the tab loses it (Live.tsx:178). | Bank the polled points server-side. | M | both |
| 10 | League | A non-focus league's sim shares the focus league's one-entry cache slot, so switching re-runs the Monte Carlo (GUIDE:1267-1270). | Key the cache by league id. | S | backend |

## 3. Deferred features worth taking in v19

| # | Source | What | Why deferred | Does the reason hold? | Size | Served number? |
|---|---|---|---|---|---|---|
| 1 | ROADMAP c.10; v16 spec:318, :43 | **In-app chat** on This Week — a question box over the brief's own facts document, the same no-tools command, the same truth check on every answer. | "next cycle, gated on briefs read" | Largely lapsed — briefs have been writing since GW4 (`advise.log` last line "Brief GW4: …"). Needs an anonymous JobRegistry job, not a new `JOB_KINDS` entry. | L | No |
| 2 | ROADMAP c.7; GUIDE:1247 | Web re-run **banks prices first**. | "a fetch on the advise path is a new job kind and W2 adds none" (v12 spec:346-348) | Reason is gone: anonymous JobRegistry jobs are the house pattern since v17/v18. | S | Restores the plist's behaviour; not a model change, but worth a before/after board diff |
| 3 | GUIDE:1251 | **Chip pair's "Try it" card gets a What-If arm** (the board's other Try-it cards already prefill). | Scope, v12 W3 | Holds no longer; it is one prefill handoff. | S | No |
| 4 | GUIDE:1243; ROADMAP c.7 | **`gaffer tidy` over `reports/projections/` and the 557 timestamped API snapshots (52 MB) in `data/raw/`**. | "deliberately not invented here" (v12 residual 5) | Still true that it was out of W5's scope; the 52 MB is the one that matters now. | S | No |
| 5 | GUIDE:1252; ROADMAP c.7 | **`schemas.py` field docstrings** so `types.generated.ts` carries the client's field comments (119 of 891 recovered; 772 missing). | v17a lost them in the generator rewrite | Holds; pure DX, one file, mechanical. | M | No |
| 6 | GUIDE:1241; v12 residual 6 | **`starred_at`** on the watchlist so the column can read "watching since" rather than "noted". | "fixing it means a second store field" | Holds but is tiny. | S | No |
| 7 | v18e spec:254; v18f:199 | **Players matrix double fetch** (a `null` path until the gameweek is known) and **FixtureTicker's** missing sentence. | Recorded as residuals, not risen from the control | Hold; both are one-liners and both are visible on a cold clone. | S | No |
| 8 | v18f spec:161-163, :199 | The eight **`set-state-in-effect`** warnings (`ExplainModal`, `DecisionPanel`, `Players`, `WhatIfSim`, `SettingsTab`, `PlannerBoard`, `Toast`, `pageData`). | "each fix is a behaviour change on a page under part 1" | Holds as a risk, but v19 is the UI cycle where those pages are open anyway. | M | No |

## 4. Deferred features to keep deferred

- **ROADMAP c.11-13, C1 news ablation, the K≥5 role replay** — every one moves a served number and needs its own replay gate; the model cycle, not v19.
- **ROADMAP c.9 blended league stance** — touches protected solver code and needs a replay to justify.
- **ROADMAP c.3 `P(top-10k)` scrape** — needs a source that does not exist; a data cycle, not a UI one.
- **Attributing the trace's squad-side terms** (GUIDE:1233) — a share assigned to one transfer would be invented; the caption already says so.
- **Re-scoring Plans B/C under Plan A's coefficients** (GUIDE:1235) and **freezing the trace's price line into the solve state** (v12 residual 1) — both need `advise.py`, which is orchestrator-only, for a decoration.
- **Light-theme turf saturation** (GUIDE:1257) — the shipped value is the spec's; changing it is a design decision, not a fix.

## 5. Broken or noisy in the logs

- `logs/field.log` (09-12, twice): `field sample for gw3 already banked (300 entries) — nothing fetched.` — the Sat/Sun scrape ran but never banked **GW4**; the Field panel's EO is two gameweeks stale, not one.
- `logs/digest-tuesday.log` (written 2026-09-15 09:30): `Tuesday digest: GW3: you 70, model 63. (5 sections)` — the Tuesday debrief repeated GW3; `logs/review.log` the same morning: `review: all 3 finished gameweeks are already reviewed — nothing to do.`
- `logs/advise.log` last write **2026-09-10 18:05** (GW4); `logs/prices.log` last **09-11 23:15** — the price-timing data gate (GUIDE:1178 table) stays blocked.
- `logs/advise.log` prints 24 `set pieces: Greaves -0.19 xPts (share now 0.00, history 0.33)`-style lines before the plan on every solve; that stream is what Model → Health surfaces as `last_line`.
- `logs/backup.log`: `Wrote /Users/…/gaffer-20260914-224506.tar.gz (7.4 MB)` vs GUIDE:519 "~16 MB" — doc drift. Also: `launchctl list | grep com.gaffer` shows only `backup` and `core-insights`, yet `review`, `snapshot` and `digest-tuesday` logs carry today's timestamps — those three are being run by hand.
- `scripts/com.gaffer.core-insights.plist` passes `plutil -lint` despite `--refresh` inside an XML comment (line 20) — Python's expat rejects it; harmless to launchd, but any tooling that parses the plists will choke.

## 6. The mobile / LAN story

- **GUIDE:545-550** — `gaffer ui --lan` serves the whole network and prints a QR. Reads open, writes need `[web] token`; the QR carries it, a typed URL needs `?token=` once. **GUIDE:1358-1361** — a refusal is a 403 with a sentence naming the header.
- **The only phone-specific layout is `kit/AppShell.tsx:24`**: `useIsMobile()` (a `matchMedia` hook, not a Tailwind breakpoint) swaps the 200px sidebar for a `fixed inset-x-0 bottom-0` tab bar with the six hubs plus a compact ThemeToggle in the seventh slot, and re-parents `ToastOutlet` so a phone still sees acknowledgements.
- **Tailwind breakpoints, non-test `.tsx`, 17 occurrences in 10 files**: this-week 1 (`RungRow`), planning 5 (`PlanDiffTable`, `ChipsTab`, `ConstraintsPanel`), players 3 (`PinDialog`, `ComparePanel`), league 1 (`RivalDetail`), live 2 (`Live.tsx`), **model 0**, kit 3 (`StatRow`, `ExplainModal`, `Card`).
- **The contract is pinned, not the design**: `frontend/src/hubs/responsive.test.tsx` asserts each of the five tabbed hubs renders an empty state with no console error at phone width against a rejecting fetch, the freshness strip `flex-wrap`s rather than scrolling the body, every `<table>` sits inside an `.overflow-x-auto`, and Model/Players/Planning tab strips scroll or wrap in their own bounds. `index.html:5` has the viewport meta.
- Net: nothing scrolls the page sideways, but **wide content is delegated to per-table horizontal scrollers** (26 files use `overflow-x`), which is the weak spot for the Thursday-evening read on a phone.
