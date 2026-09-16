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

## 4. Outcome

Filled at the gate.
