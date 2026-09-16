# v19g — the model's free half (design)

**Cycle:** v19g, the seventh sub-cycle of the v19 programme
(`specs/2026-09-15-v19-programme-design.md` §2 v19g and §4; plan
`plans/2026-09-15-v19-programme.md` §3 v19g; research
`research/2026-09-15-v19-research-backend.md` §1 C12–C13 and §2).
**Branch:** `v19g-model-free` off `main` at v19f's merge.
**Date:** 2026-09-16. **Status:** in progress on the branch.

---

## 1. What this changes, and what it does not

The model cycle's three candidates each have a half that needs no replay.
C13 (a GKP calibration delta) closed itself: `models/calibration.joblib`
carries four `by_pos` keys since the 200-row floor
(`models/calibrate.py:12`, `MIN_ROWS`) was met by accrual, but nothing
asserts it and nothing on Health says when a position drops out. C12
(bound `e_gc_model`) is live: over GW4–6's sixty club-fixtures the raw
`p_cs_model` spanned 0.085–0.957 and every GW6 fixture carried
`odds_weight = 0`, so a third of the horizon was priced on the unbounded
model; the clip itself is replay-gated (v20), but a rail on the served
band and a Health row naming the week's minimum and the zero-odds count
are free. C11 (the bonus head) has no free half. The pre-blend goals
column the programme design listed is **already banked**
(`artifacts.py:44`, `data/odds.py:695`, since v18c); recorded, not a
task. `threshold_source` is served on every chip row
(`web/schemas.py:765,807`) and read nowhere in `frontend/src`. Two
data-gated readings are now possible: W2 §3.1 flag latency (fourteen
snapshot days, GW1–3 graded) and W5 §6.5 the price-timing line (eleven
price days).

No served number changes. Model → Health and Planning → Chips change and
are named; the other hubs' pairs must be identical below the strip.

## 2. The changes

### 2.1 Calibration on Health (backend and frontend)

`Health` gains `calibration: CalibrationHealth | None` — `by_pos: dict[str,
float]`, `fitted_positions: list[str]`, `missing: list[str]` (of
`GKP DEF MID FWD`), `min_rows: int`, `saved_at: str | None` — read from
`models/calibration.joblib` through the model's own loader (never raising:
`None` when the file is absent). The Health tab renders one line under
Models: "Calibration by position: GKP 0.43 · DEF 1.06 · MID 1.15 · FWD
0.99" or, for a missing position, "GKP not fitted (n < 200)". Rail (the
orchestrator's, `tests/test_v19_degradation.py`, new): a fitted
calibration carries all four keys, asserted against a `Calibration` fit
on a synthetic 4 × 250-row frame, and `missing` names a position fitted
on 150 rows. Tests: the route with a stub joblib; the tab's line.

### 2.2 The goals-conceded diagnostic (backend and frontend)

`Health` gains `team_model: TeamModelHealth | None` — `gw: int`,
`min_e_gc_model: float`, `max_p_cs_model: float`, `fixtures: int`,
`zero_odds_fixtures: int` — read from the newest banked components
(`reports/components_gw{n}.parquet`, one row per club-fixture after
de-duplication on `team_code, gw`), `None` when there is none. The Health
tab renders: "Team model, GW6: min e_gc 0.044 · max p_cs 0.957 · 20 of 20
fixtures without market odds". Rail (orchestrator's, same file): served
`p_cs` stays inside `[0.02, 0.85]` and `e_gc` inside `[0.15, 4.0]` over
the newest components file — a *reading* rail that skips when no
components file exists and fails loudly when the served band is breached,
so a future clip (v20) has a pre-registered band to be measured against.
The band is the spec's claim; the implementer does not widen it to pass.

*Ruling at the rail (2026-09-16, before the rail was written):* the band
is breached **today** on the working tree's newest file, and only on the
zero-odds week — GW6's Newcastle and Hull City are served at `p_cs` 0.94
and `e_gc` 0.06, the bare model with no market (`odds_weight` 0 on all 20
of GW6's club-fixtures); GW4 and GW5, market-backed, sit inside it. A rail
that fails on every run until v20 is a red inner loop, not a reading, so
the rail is two tests: the market-backed club-fixtures are held to the
band now (a market-priced value outside it is a bug today), and every
served club-fixture is a **strict `xfail`** — it passes as expected while
the bare model breaches, and the day a clip makes the band hold on every
row this test fails by passing, so the mark comes off in that cycle's own
commit. The band itself is unchanged.

### 2.3 `threshold_source` captioned (frontend)

`hubs/planning/ChipsTab.tsx`: each chip row's threshold gets a `title`
and a muted suffix from `threshold_source` ("policy", "learned", or
whatever the served strings are; read `optimize/chips.py:349` and the
schema docstring for the vocabulary) so the bar's scale says where it
came from. Test: the caption per source.

### 2.4 Two readings (orchestrator)

Run once on the branch with the working tree's data, transcribed into §4:
`uv run gaffer evaluate --flag-latency` (W2 §3.1: the flag-latency
report over fourteen snapshot days and three graded gameweeks) and the
served plan's price-timing line (W5 §6.5: `served.py:373`'s reader over
the eleven-day price log, read from the newest served plan's trace via
`/api/advice/latest` or the file). Each is a reading and moves nothing;
if either points at a change, that change is v20's and is written into
the ROADMAP's candidates.

## 3. Gate, written before anything runs

1. Inner loop green; ruff clean.
2. The golden gate → 62 passed, 0 skipped (the components file the rail
   reads is not the golden's; `strip_volatile` unchanged).
3. `npm run check` green; the Model fetch rail unchanged (Health's new
   fields ride the existing read).
4. Screenshot pairs at 1400, both themes: **Model → Health** (a
   `health` shot added to the stage as v19a did) and **Planning → Chips**
   (a `chips:/planning?tab=chips` shot) named; the six default hubs
   identical below the strip.
5. The two readings pasted into §4.
6. New rails mutation-tested: the four-key rail (drop a key), the band
   (narrow it past the served minimum), the caption (blank it).

## 4. Outcome (2026-09-16, gate run by the orchestrator)

**The two readings (§2.4), run on the branch with the working tree's data:**

*Flag latency* (`uv run gaffer evaluate --flag-latency`, W2 §3.1):

```
flag latency (35 status changes over 14 snapshot days)
  lead        started  missed
  1-2d             1      26
  2-3d             0       8
  worst late flags (final status disagreed with the start)
    GW3   code 500058    1d  i->a  did not start
    GW3   code 543968    1d  d->i  started
```

Thirty-four of thirty-five flags with one to three days' lead ended the way
the flag said; two GW3 flags reversed within a day. The flag pipeline is
not the thing to change; nothing for v20's candidates.

*The price-timing line* (W5 §6.5; the newest served plan,
`reports/gw4-advice.json`, written 2026-09-11 12:35 UTC, over a price log
of twelve banked days 2026-08-31 → 2026-09-16): the head week's trace
carries `price_charge 0.0` (Gakpo's fall read and charged nothing); GW5's
carries `None` with the note "the chance of a price fall was not recorded
for every player sold here, so the price-timing charge is unknown"
(Truffert); GW6 `0.0`, no sales. The reading matches W2's finding about
the window: a solve at midday reads a log dated the previous night, so the
term charges nothing or does not know. The candidate for v20's list: bank
the price reading in the same launchd job as the solve, minutes before it
(the v19b price step already runs inside `weekly_run` before `run_advise`,
so the Thursday 18:00 run is the first that can show a non-zero charge —
read its line when it lands).

*The band* (§2.2's ruling), on `reports/components_gw5.parquet` — a
GW5 advise ran on this machine at 16:59 today from the running UI, not
from the gate, so the newest file moved under the rail between the
ruling and the run; the shape did not: GW5 `p_cs` 0.100–0.501, `e_gc`
0.692–2.317; GW6 0.127–0.554, 0.590–2.110; GW7 (all 20 without odds)
0.025–0.946, 0.056–3.696, Spurs and Hull City the two breaches. On the
GW4 file it was GW6's Newcastle and Hull City at 0.94 / 0.06. The breach
is the bare model's alone, on the week the market has not priced.

Commits on `v19g-model-free`: `221fe36` spec; `2d6357f` `CalibrationHealth`
and `TeamModelHealth` on `/api/health`, the two Health lines, the types;
`a8efeed` the chip caption; `cb8eb21` the v19 rail and the two shots in the
stage (orchestrator).

| Gate line | Result |
|---|---|
| 1 inner loop | `4421 passed, 148 deselected, 1 xfailed, 4 warnings in 74.84s`; ruff `All checks passed!` |
| 2 golden | `62 passed in 1091.79s (0:18:11)`, 0 skipped (a first run was cut off mid-way by a session compaction and rerun) |
| 3 npm run check | exit 0, `Tests 1200 passed \| 1 skipped (1201)`, `0 errors, 8 warnings`; the Model fetch rail untouched |
| 4 screenshots | league, planning-board, planning-whatif, players, settings identical below the strip in both themes; **This Week** differed in one 13 px band (x 702–1159, the "title odds vs vice" read), and two same-code control shots of the branch differ from each other in that band while one of them is identical to the after-shot — a live-odds flicker, not this cycle; **Health** and **Chips** named, after-shots only (main's stage has no such pages), sent to the user and approved |
| 5 readings | above |
| 6 mutations | FWD dropped to 150 rows (the four-key rail fails); the band widened to (0.02, 0.99) / (0.01, 4.0) (the strict `xfail` fails by passing); `sourceCaption` blanked (three ChipsTab tests fail); the implementer's two: `missing` over three positions (its test fails), `zero_odds_fixtures` counting `> 0` (its test fails) |

**Judgement calls kept:** the calibration loader is imported inside
`calibration_health()` so the router does not pull the LightGBM stack at
import; the components reduction keys on `(team_code, gw, opp_code)` so a
double gameweek keeps both fixtures; the Health line says "horizon through
GW{n}" rather than naming one week, because the file carries three; the
zero-odds count treats a missing `odds_weight` column as all zero. The GW5
advise at 16:59 (odds fetched 16:59:19) was not the gate's: nothing the
orchestrator ran solves, no launchd job fired, and the only server up was
the UI left on port 8927 after v19f's shots — reported to the user.
