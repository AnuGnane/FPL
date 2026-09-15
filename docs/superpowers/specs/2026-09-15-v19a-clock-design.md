# v19a — the week's clock and health (design)

**Cycle:** v19a, the first sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19a; plan
`plans/2026-09-15-v19-programme.md` §3 v19a).
**Branch:** `v19a-clock` off `main` at `bfad7fc`.
**Date:** 2026-09-15. **Status:** running.

---

## 1. What this changes, and what it does not

The reader opens This Week and cannot see when the deadline is if the
data is stale, cannot see that prices or the availability snapshot have
stopped arriving, and cannot see that a launchd job has stopped at all.
Live polls without saying when it last succeeded. The Tuesday digest
re-emits the last graded gameweek without saying a later one has
finished. The field scrape's Saturday run fires at 12:30, an hour before
a 15:00-kickoff Saturday's 13:30 deadline, so on 2026-09-12 it found GW3
already banked and GW4's picks not yet public.

No served number changes. One input's timing changes: the field sample
is scraped later on the same day (ruling 5, corrected below).

**Ruling 5, corrected.** The programme design proposed changing the field
job's target gameweek. The code already targets the last gameweek whose
deadline has passed (`data/field.py:403`, `scrape_gw`); the fault is the
schedule in `scripts/com.gaffer.field.plist` (Saturday and Sunday 12:30).
This sub-cycle moves both runs to 18:30 and leaves the logic alone. The
user re-runs `scripts/install_automation.sh` after the merge; the agent
does not touch launchd.

## 2. The changes

### 2.1 The countdown (frontend)

`hubs/ThisWeek.tsx:180-182` prints the deadline *or* the staleness
reason. A new `kit/Countdown.tsx` takes the served ISO `deadline` and
renders "2d 4h to the GW5 deadline · Fri 18 Sep 18:30", re-rendering each
minute (a `setInterval` cleared on unmount; under an hour it reads "42
min"; once passed it reads "deadline passed · Fri 18 Sep 18:30"). The
`PageHeader` `context` slot carries the countdown always; the staleness
reason moves into the existing warn `Callout` at `:192` (rendered when
`staleness.stale` and not only on `data_warning`, the two texts joined
when both exist). Tests: the four states (days, hours, minutes, passed)
on fake timers; the header shows the countdown when stale; the Callout
carries the reason.

### 2.2 The freshness strip knows prices and the snapshot (both)

`web/routers/meta.py:255-262` returns five rows. Two join:
`_row("prices", DATA_DIR / "live" / "price_log.parquet")` and
`_row("snapshot", DATA_DIR / "live" / "availability_log.parquet")` (the
implementer confirms the two paths against `price_log.py` and
`snapshot.py`; the names above are what the research read). `FreshnessRow`
gains `cadence_hours: float` (refresh, odds, field, advise 168; prices,
snapshot, backup 24) and `source`'s `Literal` gains the two names. The
strip's `LABELS` gains `prices: 'prices'` and `snapshot: 'availability'`;
`tone()` takes the ratio of age to cadence (grey under 1, amber under 2,
down beyond, faint for never) instead of absolute hours, so a 90-hour age
reads down for a daily job and grey for a weekly one. A stale cell (amber
or down) is a `Link` to `/model?tab=health` with the stamp in its title.
Rails: `tests/test_v12_freshness.py:38-46` and `tests/test_v12_w1_
degradation.py:609,683` pin five rows; they become seven. The w1 file is
orchestrator-only and is changed ahead of the implementer in its own
commit; the freshness file is the implementer's.

### 2.3 Health knows the jobs (both)

`Health` gains `jobs: list[JobHealth]`, one per `scripts/com.gaffer.*.plist`
read with `plistlib`: `label` (the `Label` minus `com.gaffer.`),
`schedule` (a sentence from `StartCalendarInterval`: "Thu 18:00", "daily
23:15", "Sat, Sun 18:30", "06:30 and 18:30"), `log` (the `>> logs/x.log`
path parsed from `ProgramArguments`), `modified_at` and `age_hours` (via
`_stat`), `interval_hours` (24 for a daily entry, 168 divided by the
number of entries when a `Weekday` is present, 24 divided by the number
of entries when not), and `overdue: bool` (`age_hours > 1.5 ×
interval_hours`, or the log absent). The existing `launchd` field stays
(the Health tab's advise last-line). The Automation card on
`hubs/model/HealthTab.tsx:194-212` renders the jobs as a `DataTable`
(label, schedule, last run, status) above the advise log line, `overdue`
as a `down` tone with the word "overdue" in the cell. The plist directory
is a module constant so tests point it at `tmp_path`. Tests: a plist with
a weekday, one daily, one with two entries; the overdue rule at the
boundary; a missing log; the parse of the log path.

### 2.4 Live says when it last polled (frontend)

`hubs/Live.tsx:63-72` sets no stamp on success. Add `polledAt` set in the
success branch; the `PageHeader` `context` reads "updated 14:32" (or
"not yet") and the `action` gains a "Refresh" `Button` beside the
auto-poll checkbox that calls `load`. Tests on fake timers: the stamp
appears after the first poll and moves after a manual refresh.

### 2.5 The Tuesday digest names its gameweek (backend)

`digest.py:539` (`tuesday_debrief`) takes the ledger's last row. It keeps
that, and adds: the last finished gameweek from the events snapshot
(`load_snapshot("live/events.parquet")`, the `finished` column, the same
read `banked_scrape_gw` makes; `None` when absent). When that gameweek is
later than the graded one, the verdict section's title reads "GW3 (GW4
finished, not yet graded)" and the notification headline says the same.
Tests: graded equals finished; finished ahead; no snapshot.

### 2.6 The field job's schedule (scripts)

`scripts/com.gaffer.field.plist`: both `Hour` values 12 → 18, both
`Minute` 30 unchanged. `scripts/install_automation.sh`'s echo line reads
"Sat/Sun 18:30 field scrape". GUIDE's schedule table follows in v19h.

## 3. Gate, written before anything runs

1. `.venv/bin/pytest -q -m "not slow and not golden"` green;
   `uvx ruff check src tests` → `All checks passed!`.
2. `.venv/bin/pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py`
   → 58 passed, 0 skipped.
3. `cd frontend && npm run check` green, no `Errors` line; `npm run types
   -- --check` clean; `schemas.json` and `types.generated.ts` committed
   together.
4. `src/hubs/*.fetches.test.tsx` unchanged.
5. Screenshot pairs `frontend/scripts/shots.sh v19a-before` on `main` and
   `v19a-after` on the branch, same time, both themes: **This Week, Live
   and Model** may differ; Planning, Players and League byte-identical.
6. New rails mutation-tested: the seven-row pin (drop a row), the overdue
   boundary (flip the factor), the countdown's passed state (invert the
   comparison).
7. Ruling 5's read: the field plist's diff pasted below, and after the
   merge and the user's reinstall, the first Saturday log line.

## 4. Outcome (2026-09-15, gate run by the orchestrator)

Commits on `v19a-clock`: `000d943` spec; `0e66f4e` the seven-row rail
ahead of the change; `bb6deb3` freshness rows, `JobHealth`, types;
`03e0fd3` the digest's label and the field plist; `34320a2` the README's
deny-list string (a v8a rail red on `main` since v18h's `786b24e`);
`33fbca0` the countdown, cadence tones, the jobs table, Live's stamp;
`53e76fc` the screenshot stage.

| Gate line | Result |
|---|---|
| 1 inner loop | `4383 passed, 148 deselected, 4 warnings in 72.10s` |
| 1 ruff | `All checks passed!` |
| 2 golden | `58 passed in 1096.05s (0:18:16)`, 0 skipped |
| 3 npm run check | exit 0, `Tests 1114 passed \| 1 skipped (1115)`, `0 errors, 8 warnings` (the eight recorded at v18f), types check clean |
| 4 fetch rails | untouched |
| 5 screenshots | 16 pairs at 1400, both themes, taken 23:33:05–23:33:51 on the same served data; see below |
| 6 mutations | seven-row rail (a `_row` dropped → 5 failures); `OVERDUE_FACTOR` 1.5 → 2.5 (the 37 h test alone fails, the 35 h side stays green); the countdown's passed comparison inverted (5 of 7 fail); `tone`'s ratio 2 → 3 (the two colouring rails fail) |
| 7 ruling 5 | the field plist's two `Hour` values 12 → 18 (`03e0fd3`); the first Saturday line waits on the user's reinstall |

**Screenshots, measured rather than eyeballed** (Pillow over the pairs):
the five unnamed pages (Planning what-if and board, Players, League,
Model → Settings) differ only in rows 27–38, columns 292–741, in both
themes: the freshness strip's own line, where two cells joined and one
cell's tone moved from absolute hours to the ratio. No row below the
strip moved, so the strip did not wrap. This Week differs in rows 27–137
(the strip, the countdown in the header, the reason joining the
callout); Live in rows 27–335 (the stamp and the Refresh button); Model
→ Health in rows 27–1599 (the jobs table pushes the page down). The
gate's "byte-identical" for unnamed hubs is therefore read as
"identical below the strip", which the programme design should have
said, since the strip is on every page; recorded here and in the
tracker.

**What the jobs table said on its first live reading** (23:33, the
after shot): `prices` daily 23:15, last run 4d, **overdue**; every other
job ok. `launchctl list` from the agent's shell still showed two labels
and the nightly prices job had not fired at 23:15. That reading is the
sub-cycle's point, and the user's to act on.

**Residuals, recorded:** `PLIST_DIR` reads the repo's `scripts/` copies,
not `~/Library/LaunchAgents`, so the table shows the schedule the repo
intends rather than the one installed (they differed today by the field
job's hour); v19h can prefer the installed copy when present.
`scripts/com.gaffer.core-insights.plist` carries `--refresh` inside an
XML comment, which expat rejects; the reader strips comments on retry
rather than the plist being edited (implementer's call, kept). The
countdown's absolute stamp follows the browser's locale.
