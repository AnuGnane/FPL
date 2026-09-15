# v19 — the surface and the week (programme design)

**Cycle:** v19, a programme of eight sub-cycles, v19a … v19h.
**Source:** the three research reports of 2026-09-15 under
`docs/superpowers/research/` (`2026-09-15-v19-research-frontend.md`,
`-backend.md`, `-product.md`); every finding below cites one by name and
item. The 2026-09-04 review's model items are costed in §4 and deferred to
v20.
**Plan:** `docs/superpowers/plans/2026-09-15-v19-programme.md` (to be
written after this design is approved); tracker
`docs/superpowers/plans/2026-09-15-v19-tracker.md`.
**Branches:** `v19<letter>-<slug>` off `main`, one at a time, ff-merged.
**Date:** 2026-09-15. **Status:** draft, awaiting the user's review.

---

## 0. What this is, and the three ways it could have been done

The user asked for a cycle aimed mostly at the website's UI, UX and
functionality, with general improvements to model and behaviour, and a
review of current and future code and design choices, on a budget: the
orchestrator plans and reviews, opus implementers write the code.

The research found a tool whose numbers are honest and whose surface is
correct but unhelpful in the places a weekly reader looks first. The
week's single most wanted number, the deadline countdown, is not on This
Week (frontend 1). The freshness strip cannot show the two inputs that
silently degrade the objective, prices and the availability snapshot
(backend §3.1), and nothing on the site says a launchd job has stopped
(product §2.1). The phone layout is one JavaScript switch and thirty-odd
horizontal scrollers (frontend 4–6, product §6). The pin-then-re-run loop
spans two hubs with no cue (product §2.3). Nothing compares this week's
advice with last week's, and nothing lets the reader act on a squad player
without retyping the name (frontend §2.1–2). On the model side, one of the
three candidates (the GKP calibration delta) has closed itself by data
accrual, and the most valuable one (bounding `e_gc_model`) has a free
diagnostic half and a replay-gated half (backend §1).

Three shapes were considered.

- **A. One UI branch.** Everything on `v19-ui`, one screenshot gate at the
  end. Fastest, but a single pixel gate over forty changes attributes
  nothing, and the backend pieces (freshness, price banking, health rows)
  would ride an unrelated gate. Rejected, as it was for v18.
- **B. A programme of gated sub-cycles, v17/v18-style.** Eight sub-cycles,
  each with its own spec, branch and gate: screenshot pairs and fetch rails
  for the frontend, the inner loop, ruff and the golden board for the
  backend. Each merge is a fact. **Chosen.**
- **C. The model cycle first.** Run the four replay-gated arms (§4) now, on
  the grounds that they move points. Rejected for this cycle: each arm is
  three and a half to five hours of serial replay during which the tree
  cannot be edited, the user asked for the surface first, and the ungated
  halves of the model work fit in v19g.

**The rule for the whole programme, as in v17 and v18: no sub-cycle changes
a number the advice serves.** Two sub-cycles change an *input's timing*
(v19b banks a price reading before the solve; v19a may bank the field
sample a week earlier) and each carries a ruling in §1 and a before/after
board diff in its gate, because "no served number moved" is not the same
claim as "the same inputs were read". The replay-gated arms are v20.

---

## 1. Rulings proposed for the user's review

Each is the orchestrator's recommendation. The user confirms, changes or
strikes them before the plan is written.

1. **Order and the droppable one.** v19a → v19h in the order of §2:
   clock and health first because every later sub-cycle's screenshots
   should show a live countdown; the question box (v19f) last of the
   feature sub-cycles and the one to drop if the budget runs short. v19g
   (the model's free half) and v19h (code health and docs) are cheap and
   close the programme.
2. **The route pin moves twice**, 51 → 52 in v19e (`GET
   /api/advice/diff`) and 52 → 53 in v19f (`POST /api/ask`), each in its
   own commit to `tests/test_v11_degradation.py` with the docstring
   naming the route. Nothing else adds a route; health and freshness
   changes are new fields on existing responses.
3. **`JOB_KINDS` stays 12.** The question box and the price step run as
   anonymous `JobRegistry` jobs or as steps inside the advise job's body.
   No new kind.
4. **`weekly_run` banks a price reading before the solve** (v19b). Ruling:
   this is an input refresh the Thursday plist already performs, so it is
   not a served-number change; the golden gate stubs the step (the golden
   inputs are recorded) and the sub-cycle's gate includes one real
   before/after board diff read by the orchestrator. `advise.py` is not
   touched; the step lives in `pipeline.py`, which is not orchestrator-only.
5. **The field job banks the current gameweek once its deadline has
   passed** (v19a), not the previous finished one. Ruling: the served EO
   moves a week earlier, so League → Field's `eo_gw` caption must say which
   gameweek it names (it already does, W4) and the change is recorded as
   an input-timing change with a before/after Field panel read. If the
   user prefers the one-week lag, strike this item; nothing else depends on
   it.
6. **`field_sample` is dropped from `Config`** (v19h), the only field
   never read outside `config.py` (backend §4). The Config pin moves 62 →
   61 in its own commit to `tests/test_v13_degradation.py`. If the user
   would rather wire it, say where.
7. **Screenshots.** The desktop gate stays byte-for-byte at 1400 wide in
   both themes for every hub a sub-cycle does not name. v19c adds phone
   (375) and tablet (820) shots to `frontend/scripts/shots.sh`; those are
   approved by eye, not compared, and every later sub-cycle takes them
   too. Control shots are taken at the same time as the arm's (v18f).
8. **The question box's model command is the brief's** (`[brief]` command
   and timeout, no tools), its facts document is `build_facts(gw)`, and
   every answer passes `check_brief`'s number-and-name check before it is
   shown; a failed check shows the answer struck through with the check's
   line, as the brief does. No new `Config` field. Answers are not
   persisted beyond a log line.
9. **Orchestrator-only files.** Nothing in v19 needs `advise.py`,
   `optimize/**` or `set_pieces.py`. `web/jobs.py` is touched once (v19f,
   the anonymous ask job) and the orchestrator makes that diff. The
   residuals that need `advise.py` (the trace's price line, Plan B/C
   re-scoring) stay deferred (§4).
10. **Usage.** Fable orchestrates, reviews diffs and runs gates; opus
    implementers write code from written briefs, one committing agent at a
    time; sonnet for mechanical sweeps (docstrings, the noqa convention).
    No reviewer agents. At most three implementer briefs per sub-cycle.
11. **The open security incident** (`dd47c0a`) is not part of v19. It
    stays with the user.

---

## 2. The sub-cycles

Sizes are implementer effort: S under a day, M one to two days, L more.
"Pixels" names the hubs whose 1400-wide first paint may change; every
other hub's pair must be byte-identical.

### v19a — the week's clock and health

*What the reader sees first is when the deadline is and whether the
machine that feeds the page is alive.*

- **Deadline countdown, always.** `hubs/ThisWeek.tsx:180-182` prints the
  deadline *or* the staleness reason. Print both: "2d 4h to the GW5
  deadline · Sat 20 Sep 11:00", ticking each minute, and leave staleness
  to the Callout at `:192`. The countdown reads the served deadline; no
  new fetch (frontend 1). S.
- **Freshness rows for `prices` and `snapshot`**, each with its job's
  cadence so a 90-hour age reads red for a daily job and normal for odds
  (`web/routers/meta.py:255-261`; backend §3.1). A stale cell links to
  Model → Health and carries the stamp in its title (frontend 9). S.
- **Health knows the jobs.** Model → Health gains one row per plist:
  label, schedule (parsed from `scripts/com.gaffer.*.plist`), last write
  of its log under `logs/`, and an overdue flag when the last write is
  older than the schedule allows (product §2.1). A field on the existing
  `/api/health` response, not a route. M.
- **Live says when it last polled** and offers a manual refresh
  (`hubs/Live.tsx:79-84`; frontend 12). S.
- **The Tuesday digest names its gameweek** and says when the last
  finished gameweek is not yet graded, instead of re-emitting GW3
  (product §5, `logs/digest-tuesday.log` 2026-09-15). S, backend.
- **The field job banks the current gameweek after its deadline** (ruling
  5; product §5 `field.log`). S, backend.

Gate: inner loop, ruff, `npm run check`; screenshot pairs with **This
Week, Live and Model** named; fetch rails unchanged; the golden gate,
because the digest and field changes sit beside the pipeline it records.
No pin moves.

### v19b — the loop closed

*Pin, re-run, apply: the three steps the reader takes on a Friday, on one
hub, with the same inputs the Thursday job had.*

- **`weekly_run` banks a price reading first** (`pipeline.py:56-68` has
  no price step; ruling 4). The web re-run button, the CLI and the plist
  share the body, so all three see a same-day price table and a timed
  sale (product §2.2, §3.2; GUIDE §12.4's first residual). S.
- **"n pins live" on the moves card** with the re-run affordance beside
  it, so the reader does not leave This Week to learn whether a pin took
  (product §2.3). S.
- **Pin from a news line on This Week**, the same `PinDialog`
  (`players/PinDialog.tsx`; frontend §2.6). S.
- **The chip pair's Try-it card gets its What-If arm**, the same prefill
  hand-off the board's other Try-it cards use (GUIDE §12.4; product §3.3).
  S.
- **The empty state is the action**: `kit/EmptyState.tsx:25-32` takes the
  job's start as `onAction` on This Week instead of rendering a second
  button below (frontend 10). S.
- **On a 403 over LAN, a token field**, not only the sentence (product
  §2.6). S.
- **FixtureTicker's cold-clone sentence and the Players matrix's double
  fetch**, the two v18e/v18f residuals (product §3.7). S.

Gate: inner loop, ruff, `npm run check`; the golden gate with the price
step stubbed; one real before/after board diff for the price step, read
by the orchestrator and pasted into the spec; screenshot pairs with **This
Week and Planning** named; the fetch rail for Players changes by exactly
the removed null-path fetch. No pin moves.

### v19c — the phone

*The Thursday-evening read on a phone over LAN, designed rather than
merely not broken.*

- **A stacked row variant for tables read on a phone.** `kit/table.ts`
  gains a card-per-row mode, or the four This Week tables move to
  `DataTable`'s existing one (`kit/DataTable.tsx:104-166`): ladder rungs
  (`LadderCard.tsx:181`), moves (`MovesCard.tsx:60`), the squad table and
  the board's plan columns (frontend 4; product §2.5). M.
- **Six items in the tab bar, the theme control in the shell header, and
  `env(safe-area-inset-bottom)`** under the bar (`kit/AppShell.tsx:45-68`;
  frontend 5). S.
- **An icon-only rail between 768 and 1023 px** so a landscape phone or an
  iPad does not double-scroll (`kit/useMediaQuery.ts:26`,
  `AppShell.tsx:73`; frontend 6). M.
- **Wide tables may opt out of the 1180 px column** on screens above 1400
  (`AppShell.tsx:88`; frontend 7). S.
- **Landmarks:** a skip link in `index.html`, `id="main"` on the main
  element, a heading-level prop on `Card` so the ladder does not jump from
  h1 to h3 (frontend 8). S.
- **`hubs/responsive.test.tsx` extended**: the four named tables render
  stacked at 375 with no `overflow-x-auto` ancestor; the tab bar has six
  items; the rail is icon-only at 900.

Gate: `npm run check`; desktop pairs at 1400 byte-identical for all six
hubs (nothing on the desktop first paint changes; the max-width opt-out
shows only above 1400); phone and tablet shots for all six hubs in both
themes, approved by the user (ruling 7); `tokens.test.ts` unchanged
unless a rule is added, and any added rule fails on a planted fault.

### v19d — This Week, readable

*The words stay; they stop standing between the reader and the numbers.*

- **A sticky context strip** on This Week (gameweek · captain · moves ·
  countdown) with section anchors under the header
  (`hubs/ThisWeek.tsx:176-353`; frontend 3). M.
- **The board's caveat printed once**, under the column row, keeping the
  per-week button (`planning/PlannerBoard.tsx:434-460`; frontend 2). S.
- **"How to read this" disclosures** for the ladder's five lines
  (`LadderCard.tsx:147-155`) and the board's two paragraphs
  (`PlannerBoard.tsx:221-248`), open on first visit and collapsed after,
  the state in `localStorage` wrapped in try/catch (frontend 11). S.
- **Something to take away:** copy-the-moves as text, a print stylesheet
  for This Week, and a link to the gameweek's rendered report under
  `reports/` (frontend §2.5). S.

Gate: `npm run check`; screenshot pairs with **This Week and Planning**
named; the disclosures' first-visit state is the one photographed, so the
pair is taken with storage cleared; fetch rails unchanged.

### v19e — compare and act

*Two things a reader wants to do and cannot: see what changed since last
week, and act on a player they are looking at.*

- **`GET /api/advice/diff?a=<gw>&b=<gw>`** returning the two served plans'
  moves, captain, chip and expected points side by side with the delta,
  built from the `ServedPlan` files the History tab already lists
  (`model/HistoryTab.tsx:48`; frontend §2.1). The History tab gains the
  comparison beneath its list, defaulting to the newest two runs. Route
  pin 51 → 52 (ruling 2). M.
- **Act from the squad.** `this-week/SquadTable.tsx` and `SquadPitch.tsx`
  gain a row menu (lock, ban, must-sell) that lands on Planning → What-If
  with the constraint prefilled, the same `?tab=` and prefill path the
  Try-it cards use (frontend §2.2). M.
- **"What moved since I last looked"**: the freshness strip's stale cell
  already links to Health (v19a); here the diff endpoint gives This Week
  a one-line "since GW4: captain unchanged, one move swapped" under the
  moves card when a previous run exists (frontend §2.8). S.

Gate: inner loop, ruff, `npm run check`; the golden gate (the diff reads
served plans, so `tests/test_served_plan.py` gains the diff's rail, an
orchestrator diff); screenshot pairs with **This Week, Planning and
Model** named; the route pin commit alone in its own commit.

### v19f — the question box

*The brief answers the week's question once. The reader has a second one.*

- **A question box on `this-week/BriefCard.tsx`**: one line of input, one
  answer at a time, the last three answers of the session shown beneath.
- **`POST /api/ask`** starts an anonymous `JobRegistry` job that builds a
  prompt from `build_facts(gw)` and the question, runs the brief's
  `run_command`, and returns the answer with the `check_brief` verdict
  (ruling 8). The job hook is the one v17h left; no new kind (ruling 3).
  Route pin 52 → 53. The `web/jobs.py` diff is the orchestrator's
  (ruling 9). L overall.
- **Deferred at v16 §11 "gated on briefs read"**: briefs have been written
  since GW4 (product §3.1); whether enough have been read is the user's
  to say, and ruling 1 makes this the droppable sub-cycle. The gate here
  includes the user reading three answers, one of them a question the
  facts cannot answer, and seeing the check refuse it.

Gate: inner loop, ruff, `npm run check`; the golden gate; screenshot
pairs with **This Week** named; three answers read by the user and pasted
into the spec with their check lines. This sub-cycle is the one to drop if
the budget runs short (ruling 1).

### v19g — the model's free half

*What the model cycle can ship without a replay, and the two readings the
data now allows.*

- **C13 closed by accrual**: `models/calibration.joblib` carries four
  `by_pos` keys, the GKP row among them. A rail asserts four keys and a
  Model → Health line reads "not fitted (n < 200)" when one drops out
  (backend §1 C13). S.
- **C12's diagnostic half**: a degradation test asserting served `p_cs`
  stays inside a stated band, and a Health row naming the week's minimum
  `e_gc_model` and the count of horizon fixtures with `odds_weight = 0`
  (backend §1 C12: all twenty GW6 fixtures had none). The clip itself is
  v20. S.
- **Bank the pre-blend `e_goals_model`** in `artifacts.py:46` beside
  `p_cs_model`, so evaluations stop reading the `AGS_EG_CAP` artifact
  (backend §1, 25 rows all with `p_play < 0.1`). No served number moves.
  S.
- **Two readings, run by the orchestrator and transcribed into the spec**:
  the W2 §3.1 flag-latency report (14 snapshot days, GW1–3 graded) and the
  W5 §6.5 price-timing line (11 price days, 656 codes). Each is a reading,
  not a change; if either points at a change, that change is v20's.
- **`threshold_source` rendered** as a caption on the chip rows, or the
  field deleted; served at `advise.py:1017` and typed three times in
  `schemas.py`, read nowhere in `frontend/src` (backend §3.7). Caption it;
  deleting touches `advise.py`. S.

Gate: inner loop, ruff, the golden gate (the artifact column is new, so
the golden's `strip_volatile` list is checked, not re-recorded), `npm run
check`; screenshot pairs with **Model and Planning** named. No pin moves.

### v19h — code health and the docs

*The choices the research said to revisit, and the docs true as of v19.*

Frontend (frontend §3): delete `kit/PitchView.tsx` (exported, imported
only by its test); move `QualityTab.tsx`'s remaining prop-taking sections
out (546 lines); fold `api/useJob.ts`'s two mount-only effects into one
and drop the two `eslint-disable` lines; close the eight
`set-state-in-effect` warnings by key-reset or `useSyncExternalStore`
(they are on pages v19b–v19e open anyway); give `usePageData` a
`refreshMs` and move `hubs/Live.tsx:49-84` onto it; audit the rest of
`types.ts` against the generated shapes.

Backend (backend §3–4): `tidy` gains a third target for the 557
timestamped API snapshots under `data/raw/` (184 MB), keep-newest-N;
`starred_at` on the watchlist (`watchlist.py:143`); the ledger's season
key (`review.py:1091,1110`) with its migration, before a rollover makes
GW1 ambiguous; `schemas.py` field docstrings, mechanical per router, a
sonnet sweep in three commits (149 of 1,000 documented today); the
`# noqa: BLE001` convention written into CLAUDE.md (name what you catch)
and applied to `digest.py`, `ladder.py` and `cli.py` (41 of the 210);
`field_sample` dropped (ruling 6).

Docs: GUIDE §3 (the phone), §5 (the hubs as of v19), §11 (a v19 entry),
§12 (state, residuals closed and left); ROADMAP's v19 ledger and open
rows; CLAUDE.md's pins table and the noqa convention; README's front door
where a hub changed.

Gate: full suite, ruff, `npm run check` with zero warnings; the golden
gate; screenshot pairs with **Model** named (the health lines) and every
other hub byte-identical; the Config pin commit alone.

---

## 3. What every sub-cycle does the same way

As v18 §3, with the usage rule added.

- A spec under `docs/superpowers/specs/2026-09-1x-v19<letter>-<slug>-
  design.md` with the gate written before anything runs; briefs to the
  implementer as scratchpad files, at most three per sub-cycle; a fresh
  opus implementer per brief; one committing agent at a time; the
  orchestrator reviews every diff itself and makes every diff to an
  orchestrator-only file.
- Never edit the tree while pytest, the golden or the shots run; write
  docs meanwhile.
- Gates the orchestrator runs: the inner loop (`-m "not slow and not
  golden"`), `uvx ruff check src tests`, `cd frontend && npm run check`,
  the golden gate when a backend path changed, screenshot pairs
  (`frontend/scripts/shots.sh v19<letter>-before` and `-after`, same
  time, both themes, 1400 wide, plus 375 and 820 from v19c on), the fetch
  rails.
- Pins: routes 51 → 52 (v19e) → 53 (v19f); `JOB_KINDS` 12; `Config`
  62 → 61 (v19h). Each move in its own commit to the file that holds the
  pin; the meta-rail keeps the homes.
- Merge: ff-only after the gate and the user's screenshot approval; the
  docs commit on `main` names the merge hash; the security ritual before
  every push; the tracker's row, checklist and hand-off note; the memory
  line.

---

## 4. Out of scope, by name

- **The replay-gated model arms, v20.** Costed by backend §1: every arm
  refits every head per fold (`backtest.py:455`), so each is K ≥ 5 and
  about 3.5–4 h serial with its raw control. In value per replay-hour:
  C12's clip on `e_gc_model` (`ep_cs` is 29.8 % of DEF/GKP points and a
  third of the horizon had no market); C11's bonus head with goals,
  assists and position (7.2 % of the objective; Rúben's `e_bonus` above
  Haaland's with `e_goals` 0.000); the K ≥ 5 role replay (decides what
  ships); the C1 news ablation (4–5 h; `news_shadow` already leans to the
  plain flag). v19g ships their free halves.
- The blended league stance (ROADMAP 9), `P(top-10k)` (no source), the
  trace's squad-side attribution and price-line freeze, Plan B/C
  re-scoring (all need `advise.py` for a decoration), the light-theme
  turf value.
- "Why not him?" for a refused pool player (frontend §2.3): needs a
  solver-side term; a v20 candidate once the model arms are in.
- A global search or command palette (frontend §2.4): not for a six-hub
  site with a tab strip; revisit if v19e's row menu proves the pattern.
- Banking Live's race trajectory server-side (product §2.9): M for a
  weekend curiosity.
- Any change to the MILP, the ladder, the restraint policy, the fitted
  odds blend weight, or the ledger style.

---

## 5. Self-review

- **Placeholders:** none; every item has a file, a size and a gate.
- **Consistency:** the route pin moves exactly twice and the Config pin
  once, and §1, §2 and §3 agree on where. Two input-timing changes carry
  rulings (4, 5) and a before/after read; no sub-cycle changes a served
  number.
- **Scope:** eight sub-cycles, each one branch and at most three briefs;
  v19f is the one to drop. Frontend research counted 14,169 source lines
  and no TODOs, so the code-health list in v19h is the whole of what the
  research found, not a sample.
- **Ambiguity:** "pixels named" means the 1400-wide pair may differ only
  for the hubs listed; phone and tablet shots are approved, not compared;
  "no served number" excludes input timing, which is why rulings 4 and 5
  exist.
