# v19h — code health and the docs (design)

**Cycle:** v19h, the eighth and last sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19h and ruling 6; plan
`plans/2026-09-15-v19-programme.md` §3 v19h; research
`research/2026-09-15-v19-research-frontend.md` §3 and §5,
`research/2026-09-15-v19-research-backend.md` §3–§4).
**Branch:** `v19h-health` off `main` at v19g's merge.
**Date:** 2026-09-16. **Status:** in progress on the branch.

---

## 1. What this changes, and what it does not

The research's code-health list, closed on both sides, and the docs made
true as of v19. No served number changes; no route, job kind or Config
field moves. Every hub's screenshot pair must be identical below the
strip, including the `health` and `chips` shots v19g added to the stage:
the Quality tab is refactored, not redrawn, and the watchlist column that
changes is on a tab the stage does not shoot.

Four rulings taken here, before anything runs:

- **Ruling 6 amended: `field_sample` stays.** The research read it as
  the one `Config` field never read outside `config.py`; it is read by
  `getattr` at `data/field.py:548` as the field scrape's sample size,
  clamped at `:229` of its test file, and covered by four tests. The grep
  for `.field_sample` missed the `getattr`. The field is wired, the
  Config pin stays **62**, and no pin commit is made. The tracker's v19h
  row is corrected from 61.
- **Live stays off `usePageData`.** Research frontend §3.5 asked for a
  `refreshMs` so Live's hand-rolled five-state read could move onto the
  loader. `usePageData` is a request cache that holds a body until it is
  invalidated (v17h's trap, restated in v18e §2.3), and Live's `active`
  flag is a liveness question: a remount would paint the cached
  scoreboard first. Live's read stays raw; the loader gains nothing.
  Recorded as a closed residual, not carried.
- **No `tidy` target for the API snapshots.** Backend research §3.4
  counted 577 timestamped files at the top of `data/raw/` and asked for
  keep-newest-N. Read again: `api/client.py:80` already prunes each FPL
  kind to `KEEP_DUMPS` (20; bootstrap, fixtures and the entry sit at 20
  today), and the other 518 are `odds-*` and `ags-*`, the odds snapshots
  `data/odds.py:663` says are kept until a season of them can fit the
  anytime-scorer weight that is a bare prior today. A sweep would delete
  a corpus or nothing. The target is dropped; `tidy.py`'s scope paragraph
  says so; the 90 MB under `data/raw/news/` stays out of scope as that
  paragraph already rules.
- **`# noqa: BLE001` narrows only where the try body's raisers are
  evident.** A `json.loads` catches `ValueError`, a file read `OSError`;
  anything else keeps `Exception` and gains the reason on the line. A
  swallow that changes what is caught is a behaviour change, and this
  cycle ships none.

## 2. The changes

### 2.1 Frontend health (one opus brief)

1. `kit/PitchView.tsx` and its test deleted; the two exports at
   `kit/index.ts:29-30` and the name in `kit/index.test.ts:10` go with
   them. This Week draws `this-week/SquadPitch.tsx`; nothing else imports
   it (checked by grep, and the build would say).
2. `hubs/model/QualityTab.tsx` (546 lines, seven hand tables at `:54,
   165, 196, 267, 361, 394, 436`): the prop-taking sections move to
   sibling files under `hubs/model/quality/`, one section per file, with
   `QualityTab.tsx` left as the layout that composes them, under 250
   lines. Pixel-identical: the Model pair is the proof.
3. `api/useJob.ts:238-288`: the two mount-only effects (the kind probe
   and the slot probe), each carrying an `exhaustive-deps` disable, fold
   into one effect keyed on a derived spec id, and the two
   `eslint-disable` lines go. The recovery paths are kept as they are
   (a 404 on the slot probe forgets the id; a probe that cannot reach the
   server leaves the button alone). `useJob.test.tsx` green, unchanged
   except where a test named the two effects.
4. The eight `react-hooks/set-state-in-effect` warnings closed:
   `api/pageData.ts:154`, `hubs/Players.tsx:74`,
   `hubs/league/WhatIfSim.tsx:56`, `hubs/model/SettingsTab.tsx:56`,
   `hubs/planning/PlannerBoard.tsx:99`,
   `hubs/this-week/DecisionPanel.tsx:36`, `kit/ExplainModal.tsx:36`,
   `kit/Toast.tsx:105`. Each by the mechanism that fits the site: a
   key-reset where the state re-seeds from a prop, a guarded render-phase
   set where the state mirrors a value already in hand (v19f's pattern in
   `QuestionBox`), `useSyncExternalStore` where the source is outside
   React. No `eslint-disable`. The rail: `frontend/package.json`'s `check`
   script runs eslint with `--max-warnings 0`, so the count is pinned at
   zero from here and `npm run check` fails on the first new warning.
5. `types.ts` (308 lines, hand-written) audited interface by interface
   against `types.generated.ts`: an interface identical to its generated
   shape is deleted and its importers repointed; a narrowing is kept with
   one line saying what it narrows and why. `tsc` is the proof.

### 2.2 Backend health (one opus brief)

6. `tidy.py`'s module docstring: the scope paragraph rewritten under
   §1's ruling — the FPL client prunes its own kinds, the odds snapshots
   are a corpus, the news cache is out of scope — so the next reader does
   not propose the sweep a fourth time. No code change; `test_v12_tidy.py`
   unchanged.
7. `starred_at` on the watchlist (`watchlist.py:143`): the row gains
   `starred_at`, written when the row is created and preserved on every
   later write, so `set_at` can go back to meaning the note's stamp. A
   row loaded without `starred_at` reads it as its `set_at` (the best
   known date; the ledger has no other). The watchlist schema gains
   `starred_at: str | None`; the Watchlist tab's date column reads
   "starred {date}" for a row with no note and "noted {date}" otherwise
   (read the tab for the column). Tests: created once, preserved through
   a note edit, migrated on read; the column's two readings.
8. The ledger's season key (`review.py:1091,1110`): `append_ledger`
   writes `season` on every row from the config in force, and replaces
   by `(season, gw)`; `load_ledger()` returns the season in force alone
   (a row without `season` is read as the current season, because the
   ledger has only ever held one, and is rewritten with the key on the
   next append). The nine readers call `load_ledger()` unchanged. Tests:
   two seasons' rows, the reader returns the current; a legacy row reads
   as current; an append rewrites the legacy rows with the key.
9. The BLE001 convention applied to `digest.py` (20 sites), `ladder.py`
   (11) and `cli.py` (10) under §1's ruling: every `# noqa: BLE001` ends
   with `— <what is swallowed and why that is safe>`, or the `except`
   narrows to the class the try body can raise. The suite is the proof
   that nothing narrowed too far. The convention itself is written into
   `CLAUDE.md` by the orchestrator (§2.4).

### 2.3 The schema docstrings (one sonnet brief, three commits)

10. `web/schemas.py`: 1,023 annotated fields on 166 classes, 149 with a
    sentence under them. Every field gets one, in the file's attribute-
    docstring style (the sentence on the line after the field, in triple
    quotes), saying what the value means and its unit or vocabulary, and
    where a router computes it, from what — read the router that fills
    the class. Never a restatement of the type. A field whose filler
    cannot be found gets no sentence and is listed in the report. The
    sentences reach `frontend/src/schemas.json` and `types.generated.ts`
    through `scripts/gen_types.py`'s `_field_sentences`, so each commit
    regenerates and commits both. Three commits by section: (a) jobs and
    health, This Week; (b) Planning, Players; (c) League, Live, Model.

### 2.4 The docs (orchestrator)

11. `CLAUDE.md`: the pins table (routes 51 → 52, stale since v19f), the
    layout paragraph and the orchestrator-only list naming
    `tests/test_v19_degradation.py`, the `noqa` convention under writing
    style, the frontend gate's zero-warning line. `docs/GUIDE.md`: §5 the
    hubs as of v19 (the phone, This Week readable, compare and act, the
    question box, the two Health lines), §11 the v19h entry and a
    one-paragraph v19 summary, §12 the state with the residuals closed
    here and the ones carried to v20. `docs/superpowers/ROADMAP.md`: the
    v19 ledger closed, the open rows, the candidates for v20 gathered
    (the `e_gc`/`p_cs` clip against the v19 rail's band; the price
    reading banked minutes before the solve; the bonus head; the v19b
    price line when the Thursday run lands). `README.md` where a hub
    changed.

## 3. Gate, written before anything runs

1. The **full** suite `.venv/bin/pytest -q` green (the slow fit files
   included, once for the programme); ruff clean.
2. `npm run check` → exit 0, `0 errors, 0 warnings`, with
   `--max-warnings 0` in the script; `npm run types -- --check` clean.
3. The golden gate → 62 passed, 0 skipped.
4. Screenshot pairs at 1400, both themes: **every** hub identical below
   the strip, `health` and `chips` included; nothing named.
5. Pins unchanged: routes 52, `JOB_KINDS` 12, `Config` 62 (ruling 6
   amended, §1).
6. New rails mutation-tested: the season filter (drop it → its test fails);
   `starred_at` preserved (stamp it on every write → its test fails); the
   zero-warning line (reintroduce one synchronous set in an effect →
   `npm run check` exits 1).
7. The three docstring commits each leave `npm run types -- --check`
   clean and name in their report every field left without a sentence.

## 4. Outcome (2026-09-16, gate run by the orchestrator)

Commits on `v19h-health`: `a03c707` spec; `de9bbad` tidy's scope paragraph;
`ed264aa` `starred_at` and the season-keyed ledger (with the types);
`e40a250` the BLE001 reasons; `d626816`, `f43fe21`, `9ab55c3` the three
docstring commits (sonnet); `87101b5` PitchView deleted; `5a0695d` the
Quality tab in eight files; `835712c` useJob's one probe effect and the
eight warnings closed, pinned with `--max-warnings 0`; `7bbc8a6` types.ts;
`4018ca6` the v19h shots stage (orchestrator).

| Gate line | Result |
|---|---|
| 1 full suite | `4581 passed, 1 xfailed, 4 warnings in 1284.02s (0:21:24)`, 0 skipped (the slow fit files included); ruff `All checks passed!` |
| 2 npm run check | exit 0, `Tests 1201 passed \| 1 skipped (1202)`; `eslint . --max-warnings 0` printed nothing; `npm run types -- --check` clean |
| 3 golden | inside the full run: 62 collected, 62 passed, 0 skipped |
| 4 screenshots | eighteen pairs at 1400, both themes (the six, quality, health, chips; the stage added in `4018ca6` and the branch's script run against main for the before set): seventeen identical below the strip; Health's age column ticked 128.03h → 128.04h between the two shoots, the clock and nothing else |
| 5 pins | routes 52, `JOB_KINDS` 12, `Config` 62 (ruling 6 amended: `field_sample` stays) — the three rails in the full run |
| 6 mutations | implementers': `starred_at` stamped on every write (three watchlist tests fail); the season filter dropped (two ledger tests fail); a synchronous set in an effect (`npm run lint` exits 1); the slot-probe branch short-circuited (two useJob tests fail). Orchestrator's own: a set-in-effect injected into `Toast.tsx` → lint exit 1, restored → 0 |
| 7 docstrings | 178 → 1024 of 1031 fields with a sentence; seven left with reasons (five `PlayerRef`-typed captain/vice fields, whose sibling description would split the shared wire type and fail `types.test.ts`; two fields that are the generator's own no-sentence fixtures in `test_v12_w5_gen_types.py`); `npm run types -- --check` clean after each commit |

**Judgement calls kept:** `starred_at` is `str`, not `str | None`, because
`load_watchlist` fills it from `set_at` and the router always has one; the
season is read through a private `review._ledger_season()` with a
function-local config import, as `served.py` and `brief.py` do; two
BLE001 sites narrowed to `(OSError, ValueError)` (a file read and a JSON
parse), every launchd body and pandas loader kept `Exception` with a
reason; the `pageData` warning closed by a guarded render-phase set, not
`useSyncExternalStore`, because the store holds one body per URL while
`error` and `status` are the reader's own; `Toast` did move to
`useSyncExternalStore`; no `key` reset anywhere, because keying
`PlannerBoard` or `ExplainModal` would remount them; useJob's one effect
carries the honest dependency list `[kind, slot, watch, poll]`; `types.ts`
lost nothing, since no interface had a generated twin, and two review
unions now derive from `ReviewLane`. The preserved-through-edit watchlist
test first passed under its own mutation because two stamps landed in the
same second; it now ages the dates on disk.
