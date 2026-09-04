# gaffer v13 — the transfer ladder (design)

*Brainstormed and approved 2026-09-04. One cycle: two appetite levers the
weekly advice obeys, and a ladder that prices every rung of hits so the
manager can see what his cap costs him.*

## 0. Why now

GW3, 2026-09-04. After the free-transfer hotfix (`3c39048`) the regenerated
board still recommended four moves at three hits, −12, with the fourth buy
at 45% scenario support. One solve per hit cap on the same board showed
the shape of the decision the tool never puts in front of the user:

| Cap | GW3 moves | Hits | Objective, 3 GWs | Raw xPts, 3 GWs |
|---|---|---|---|---|
| none | 4 | 3 | 199.0 | 218.4 |
| 2 | 3 | 2 | 198.3 | 217.8 |
| 1 | 2 | 1 | 197.1 | 216.9 |
| 0 | 1 | 0 | 194.1 | 220.2 |

The objective and the raw points point different ways: the hits are bought
by the league-chase tilt and the horizon decay, not by the forecasts of the
players themselves, and the rungs sit a point or two apart over three weeks
— inside forecast noise. Whether that trade is worth −12 is a matter of
appetite. The user's appetite is one or two hits, and today the only place
he can say so is the What-If lab, one solve at a time, with no probability
attached and no effect on the Thursday report.

Out of scope, recorded for the review that follows this cycle: the GW3
captaincy call (Guéhi 7.61 over Haaland 7.46, a 0.3-point captain margin
tipped by the chase tilt) rests on a bonus expectation for Haaland of 0.23
against 1.5 a game this season. That is a model finding, not a UI one.

## 1. Goals and non-goals

**Goals.**

1. Two levers, **max hits** and **max transfers** per gameweek, in
   `config.toml` `[optimizer]`, editable from the Settings tab through the
   local overlay, and obeyed by `gaffer advise` — the Thursday report, its
   scenario sweep, its alternative plans and its chip table all solve under
   them. Default **2 hits**, no transfer cap.
2. A **transfer ladder**: one row per rung — *bank* (no moves), then 0, 1,
   2, 3 hits — each with its best plan, its cost, this week's and the
   horizon's expected points, the objective, and probabilities scored on the
   same noise draws: P(beats banking) and P(beats the top rung). Built at the
   end of every `advise`, re-buildable on demand, served on the This Week
   hub and the What-If tab.
3. **What each hit buys**, visibly: expand a rung to see the squad it
   produces and, against the rung below, exactly which extra move the hit
   paid for and what that move is worth.

**Non-goals.** No change to how the MILP values a hit (`hit_cost`,
`ft_value`, the λ table). No change to the HTML report or the CLI text
beyond one line naming the cap. No per-player or per-week appetite. No
change to the sensitivity sweep or the alternative-plans search. No new
job kind: the on-demand rebuild is an anonymous submission like What-If.

## 2. The levers

### 2.1 Config

Two new `Config` fields, both `[optimizer]` keys (the section is splatted
into `Config`, `config.py:175`), so the pin moves from 55 to 57:

```python
max_hits: int = 2
"""Most hits the solver may take in any one non-wildcard gameweek of the
horizon. The user's appetite, not a model parameter; 15 means no cap (the
tree's idiom for 'unlimited', as in ``free_transfers=15``)."""
max_transfers: int = 15
"""Most transfers in any one non-wildcard gameweek. 15 means no cap; 0 is
'bank' — no moves at all."""
```

Both are validated in `load_config` to `0 <= v <= 15`; anything else is a
`GafferError` naming the key. `NON_FIELD_OPTIMIZER_KEYS` is untouched: they
are fields. They must **not** reach `solve_plan(**opt_kw)` — they are
`SolveInput` attributes — and they do not: `opt_kw` is a curated dict
(`advise.py:787`), not a splat of `Config`, so the two are added to
`SolveState.opt` explicitly at serialisation and nowhere else.

### 2.2 The MILP

`SolveInput` gains one field, appended and defaulted like `force_out`:

```python
max_transfers: int | None = None
"""Cap on transfers in a non-wildcard week; ``None`` adds no constraint."""
```

In `_solve_once`, beside the existing `max_hits` cut (`milp.py:749-750`):

```python
if state.max_transfers is not None and not wc:
    prob += nt <= state.max_transfers
```

`max_hits` already exists (v12 W3) and is unchanged. With both `None` the
model is byte-identical: `tests/data/v12_w3_milp_golden.lp` stays the pin.

### 2.3 Where the levers are applied

* **`advise.py`** — the one `SolveInput` the weekly run builds (`:745`)
  carries `max_hits=cfg.max_hits, max_transfers=cfg.max_transfers`, with 15
  mapped to `None`. Everything downstream inherits it through `state`: the
  scenario sweep (`run_scenarios(pool, state, …)`, `:851`), the alternative
  plans (`:1070`) and the chip table (`:955`). The wildcard week is exempt by
  rule inside the solver; the free-hit from-scratch solve already passes its
  own `max_hits=None`.
* **The saved state** — `SolveState.opt` gains `max_hits` and
  `max_transfers` (the raw config values, 15 for no cap). `OPT_REQUIRED_KEYS`
  is not extended, so a state written before v13 still loads;
  `solve_kw_from_state` ignores the two keys, and a helper
  `caps_from_state(state) -> tuple[int | None, int | None]` reads them
  (absent → `None, None`).
* **What-If** (`routers/whatif.py`) — the *baseline* solve applies
  `caps_from_state`, so the baseline is the plan the report served and not a
  looser one. The user's own solve keeps its explicit `max_hits` from the
  request (semantics unchanged: 0 means no hits) and now also takes an
  optional `max_transfers: int | None = None`. `drafts.py` mirrors both.
* **Settings** — two `WHITELIST` entries in `web/settings_keys.py`:
  `max_hits` ("Max hits per week", int, 0–15, help: "15 = no cap. The
  Thursday advice, its sweep and its alternatives all solve under this.")
  and `max_transfers` ("Max transfers per week", int, 0–15, help: "15 = no
  cap; 0 = bank"). Saved to `config.local.toml` like every other row.
* **CLI** — `gaffer advise` prints one line after the deadline header:
  `Caps: 2 hits/week, transfers uncapped` (or `no caps`).

## 3. The ladder

### 3.1 Module: `src/gaffer/ladder.py`

```python
def build_ladder(gw: int | None = None, *, n_draws: int = LADDER_DRAWS,
                 seed: int | None = None) -> dict
def save_ladder(payload: dict, gw: int) -> Path      # reports/ladder_gw{N}.json
def load_ladder(gw: int) -> dict | None
```

`LADDER_DRAWS = 200`. The board is built exactly as `sensitivity.run_sensitivity`
builds it — saved state, raw EP, cover converted from `league_eo` when the
state predates it, `tilt_ep`, `milp_pool`, `solve_kw_from_state` — and the
idiom is repeated rather than shared, for the reason `sensitivity.py`
records (two tests pin `solve_whatif`'s source text).

**Rungs.** In order:

| key | SolveInput |
|---|---|
| `bank` | `max_transfers=0` |
| `hits0` | `max_hits=0` |
| `hits1` | `max_hits=1` |
| `hits2` | `max_hits=2` |
| `hits3` | `max_hits=3` |
| `open` | no caps — present only when its first-week hits exceed 3 |

Every rung's `SolveInput` otherwise copies the advice's: `owned_codes`,
`bank`, `free_transfers`, `gws`, no chips, no locks. `max_transfers` on the
hit rungs is `None`: the rung *is* the appetite. A rung whose first-week
plan (buys, sells, captain) equals the rung below is kept in the table with
`same_as: "<key>"` and no separate solve output, so the user reads "the
solver would not spend the third hit" rather than a duplicated row.

**Per-rung fields.**

```
key, hits, transfers, cost (4*hits), same_as,
plan_by_gw: [{gw, hits, buys:[PlayerRef], sells:[PlayerRef],
              xi:[code], bench:[code], captain, vice, expected_pts}],
week_pts, horizon_pts,            # raw, as whatif._summary computes them
objective,                        # the solver's, in its own frame
mean_pts, p10_pts, p90_pts,       # the draw distribution of horizon_pts
p_beats_bank, p_beats_top, p_best # from the shared draws
vs_below: {extra_buys, extra_sells, dropped_buys, dropped_sells,
           delta_mean_pts, delta_cost}   # against the previous distinct rung
```

Top-level: `gw, gws, generated_at, free_transfers, cap: {max_hits,
max_transfers}` (from `caps_from_state`), `cap_rung` (the key the cap
selects, e.g. `hits2`), `recommended` (the key whose first-week plan matches
the served advice, or `null`), `n_draws, seed, sigma_source`.

**Scoring under noise.** One matrix of draws shared by every rung, so the
rows are comparable and the common players cancel: for each of `n_draws`,
each `(code, gw)` in the union of the rungs' squads draws points
`max(0, N(ep, σ))` with `ep` the raw EP and σ from
`uncertainty.bands_by_player_gw(load_components(gw))` — the *outcome*
distribution the squad table's bands already show, estimation σ folded in
in quadrature as that module does. When no components frame is banked,
σ² = `league_sim.OUTCOME_VAR_PER_EP × ep` alone, and `sigma_source` says
`"outcome_only"`. Seed: `scenarios_seed + 2_000_000 + gw`, two million
clear of the advice sweep and one million clear of the sensitivity sweep.

A rung's score in a draw is `Σ_weeks (Σ_xi pts + captain pts − 4·hits)`
over the shared horizon, undecayed, the vice ignored, the bench ignored —
the same measure as `horizon_pts`, so `mean_pts` is `horizon_pts` up to the
clipping at zero. `p_beats_bank` is the fraction of draws in which the
rung's score exceeds the `bank` rung's; `p_beats_top` the same against the
last distinct rung; `p_best` the fraction in which the rung is the maximum
(ties split). By construction `bank.p_beats_bank` is `null`, not 0.5.

**Cost.** Five solves at ~7 s and 200 draws over ~40 player-weeks: under a
minute, inside `WHATIF_TIMEOUT_S`.

### 3.2 When it runs

* **At the end of `gaffer advise`**, after `save_solve_state`, inside a
  `try/except Exception` that prints one line and never fails the advice.
  The pinned `scenarios_n = 0` rail output is untouched: the ladder is a
  separate artifact and prints nothing to the report.
* **On demand**: `POST /api/ladder` (202, `JobAccepted`) submits
  `lambda: build_ladder(gw)` through `app.state.jobs.submit` with
  `WHATIF_TIMEOUT_S`, exactly as `/api/whatif` does; the result is also
  saved so the next GET reflects it. `GET /api/ladder` returns the saved
  payload for the latest gameweek or `{"gw": N, "rungs": []}` with a
  `note` ("run `gaffer advise` or rebuild") when none is banked.

Routes 47 → 49. `JOB_KINDS` stays 12.

## 4. The UI

### 4.1 `LadderCard` (frontend/src/hubs/this-week/LadderCard.tsx)

On the This Week hub directly under `MovesCard`; the same component is
rendered on the What-If tab above `SensitivityCard`.

Header: "Transfer ladder — 1 free transfer, cap 2 hits" and a *Rebuild*
button (POST, `useJob`, skeleton while running, stale rows blanked as
`WhatIfTab` does).

Table, one row per rung, in ladder order:

| Rung | Moves | Cost | GW xPts | 3-GW xPts | vs bank | P(beats bank) | P(best) |

* The `cap_rung` row is highlighted; rows above it are rendered in the muted
  text tone with a "beyond your cap" title — visible, never hidden.
* The `recommended` row carries the same "recommended" chip the alternative
  plans strip uses.
* A `same_as` row prints "solver would not spend it — same as *N hits*" in
  place of its numbers.
* `vs bank` is `mean_pts − bank.mean_pts`, signed, in the tone classes
  `PlanDiffTable` uses for `delta_xpts`.
* Probabilities print as whole percents.

Clicking a row expands it (a plain toggled row, one open at a time — no
new dependency; the tree has Radix tabs, dialog, dropdown and tooltip
only):

* **This rung's squad**: buys and sells per horizon week with the
  `PlayerRef` chips the What-If diff uses, the starting XI listed by
  position, captain marked.
* **What the last hit bought**: from `vs_below` — "+ Semenyo for Rice
  (+1.9 xPts over 3 GWs, −4 now)". Absent on `bank` and on `same_as` rows.

### 4.2 Controls

Two selects on the card, `Max hits` (0–3, "no cap") and `Max transfers`
("bank", 1–5, "no cap"), initialised from the payload's `cap`. Changing one
PUTs through the existing `/api/settings` write and then triggers *Rebuild*;
the highlighted row moves. `MovesCard`'s heading gains the line
"1 free transfer · cap 2 hits" from the same payload, and its empty state
"No transfers — bank the free transfer" is unchanged.

The Settings tab shows the two rows automatically (they are WHITELIST
entries), and its label copy says which tab also edits them.

### 4.3 Types

`schemas.py` gains `LadderRung`, `LadderVsBelow`, `LadderPayload`;
`scripts/gen_types.py` regenerates `types.generated.ts`; `schemas.json`
follows.

## 5. Tests and pins

* `tests/test_v13_degradation.py` — the rail: `Config` fields 57 with the
  two names and defaults 2/15; `SolveInput()` with both caps `None` writes
  the golden LP byte-for-byte; a `max_transfers=0` solve makes no move; a
  `max_transfers=1` solve makes at most one; routes 49 with `/api/ladder`
  present; `JOB_KINDS` still 12; `build_ladder` on the golden pool returns
  the six-or-five rungs in order with every probability in `[0, 1]`,
  `bank.p_beats_bank is None`, `p_best` summing to 1 ± 1e-6, `same_as` set
  when two rungs coincide; a state with no `max_hits` in `opt` reads as
  `None, None`.
* `tests/test_ladder.py` — the scoring: with σ forced to 0 every
  probability is exactly 0 or 1 and `mean_pts == horizon_pts`; shared draws
  (two rungs with identical squads score identically in every draw);
  `vs_below` set arithmetic; the seed is reproducible.
* `tests/test_web_ladder.py` — GET empty state, GET after a save, POST 202
  and the saved result, 429 on a full queue, the 404 for an unknown route
  count.
* `tests/test_web_whatif.py` — the baseline now solves under the state's
  caps: a state with `max_hits=1` in `opt` yields a baseline with `hits <= 1`.
* `tests/test_advise.py` — the caps reach the `SolveInput`; the ladder is
  built after the state is saved; a ladder failure does not fail the run.
* `tests/test_config_v8a.py` / README: the two keys documented under
  `[optimizer]` in `config.example.toml` and the README's config table.
* Frontend: `LadderCard.test.tsx` (rows, highlight, muted-above-cap, the
  expand, the rebuild job, `same_as`), `MovesCard.test.tsx` (the cap line),
  `SettingsTab.test.tsx` (two new rows). vitest must end with `Errors 0`.

## 6. Measurement

The caps are a preference, not a model claim, so there is no gate. One
pre-registered measurement is banked anyway because it is cheap and the
user will want the number: `scripts/replay_pair.sh v13-caps` runs the
2025-26 season replay with `max_hits = 2` against `max_hits = 15` at K = 3
seed bases (`CONVENTIONS.md` §1), config otherwise byte-identical, and the
write-up states the mean ± spread of season points and hits taken. The
result is informational: it tells the user what a 2-hit appetite has
historically cost or saved, and it does not change the default. The
`data/core_insights/` state is named in the write-up (§1 of the
conventions).

## 7. Files

New: `src/gaffer/ladder.py`, `src/gaffer/web/routers/ladder.py`,
`frontend/src/hubs/this-week/LadderCard.tsx` (+ test),
`tests/test_ladder.py`, `tests/test_web_ladder.py`,
`tests/test_v13_degradation.py`.

Modified: `config.py`, `config.example.toml`, `optimize/milp.py`
(`max_transfers`), `advise.py` (caps into `SolveInput`, `opt` keys, the
ladder call, the CLI line via `cli.py`), `artifacts.py` (`caps_from_state`),
`web/routers/whatif.py` and `drafts.py` (baseline caps, `max_transfers`),
`web/settings_keys.py`, `web/schemas.py`, `web/app.py` (router),
`frontend/src/hubs/ThisWeek.tsx`, `this-week/MovesCard.tsx`,
`planning/WhatIfTab.tsx`, `planning/ConstraintsPanel.tsx`
(`max_transfers`), `types.generated.ts`, `schemas.json`, README.

Protected files touched, authorized by this spec: `advise.py`,
`optimize/milp.py`, `web/routers/whatif.py`, `tests/test_advise.py`.
Pins after: routes 49, `JOB_KINDS` 12, `Config` 57.
