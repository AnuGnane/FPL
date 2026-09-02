# Gaffer v12 W3 Implementation Plan — decide

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** six changes to what the solver is allowed to express and to how its answer is described — a "must sell" constraint, one chip threshold instead of two, the second- and third-best plans, an availability draw in the scenario sweep, chip pairs and a free hit priced from the right week, and a captain ceiling that is a probability rather than a ranking. Every line of it is in a protected file, so every task below is either an enumerated STOP or a task that touches only the unprotected wire and screen around one.

**Architecture:** the honest shape of W3 is not the shape spec §4 describes, and five of the six items came back different from the spec's sketch.

- **§4.1 `force_out` is small and clean** in the MILP — one dataclass field, one validation entry, one constraint — and the interesting half of it is that it *fixes* a limitation v11 wrote down and shipped: `PlannerBoard`'s handoff carries a planned sell across as `ban`, which also forbids buying the player back (v11 plan A7). `force_out` is the constraint that vocabulary was missing. The regression guard the brief asks for is real: the LP the solver builds is captured to text and compared byte-for-byte against a golden generated from the pre-change code (A1).
- **§4.2's flat threshold is consulted in exactly one live place** and it is not the one the spec names. `advise.py:735` already builds θ and `advise.py:895` already applies it to every chip row. The bar nobody replaced is `chips.py:232` — `wildcard_now_assessment`'s `recommend`, which compares against `WILDCARD_RECOMMEND_THRESHOLD` unconditionally, in the same run that computed θ for the wildcard three lines earlier (A2). The caption the spec asks for needs a *source*, which no lookup can currently report, so `chip_policy` grows one (A3).
- **§4.3 is the largest item in the workstream** and the spec understates it twice: `Plan` has no `alternatives` field, `_solve_once` has no way to exclude a solution, and the "EP gap" the spec names is not a quantity the solver produces — what it produces is an objective, in a decayed frame, and the alternatives must be compared in the frame they were solved in (A4). The alternatives are also solved *without* the coherence `FixedMoves` the recommended plan carries, which means an alternative can score **above** Plan A; the gap is therefore signed (A5).
- **§4.4 costs a protected degradation test.** `tests/test_v10_degradation.py:534` asserts, in as many words, that `advise.py` does not pass `p_play` to `run_scenarios` — it is v10's T10-A rail, and §4.4 exists to overturn exactly the premise it pins. That edit is Task 8's STOP, and it is the one place in this plan where the spec asks for something whose cost it does not name (A6).
- **§4.5's free hit is already a re-solve.** `free_hit_gain` has solved a one-week unconstrained squad since v2 (`chips.py:199-206`). What is approximate is *which week's position it solves from* — today's squad and today's bank, for a chip that might be played three weeks out — and that the baseline's saved hits are not credited. Both are fixable, and fixing the first needs one new number the MILP has never surfaced: the bank per gameweek (A7). The WC+BB pair, meanwhile, is **dead on today's data**: `load_chip_scenarios()` returns `{}` because `data/chip_scenarios.toml` does not exist and `write_chip_scenarios` deliberately refuses to create it while every gameweek has ten fixtures (A8).
- **§4.6's "disclaimed ranking number" is real and the spec points at the wrong table.** It is `ep_matrix`'s `p_haul=("p_haul", "max")` — "takes the best single fixture rather than summing, since it is a probability" — surfacing in the captain table under the header `P(2+ returns)`. The two-fixture point distribution the spec asks for already exists, in `uncertainty.bands_by_player_gw`, keyed `(code, gw)` with EP summed across a double and the sweep's own σ. §4.6 is therefore a re-wiring, not a new statistic (A9).

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, PuLP + HiGHS/CBC, FastAPI + pydantic, tomllib, pytest; React 19 + TypeScript + vitest.

**Branch:** `feat/gaffer-v12` at `27f7933` is where this program's spec was written. **W3 does not branch from there.** W1 and W2 merge to `main` before W3 starts (spec preamble), so W3 is cut from `main` after W2's merge and every pin below is re-measured at that commit (see **Pins**). Authoritative spec: `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` §4 and §1. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

```bash
git rev-parse --abbrev-ref HEAD      # feat/gaffer-v12-w3 (cut from main after W2)
git rev-parse HEAD                   # record it; every pin below is measured here
git log --oneline -1 main            # W2's merge
```

**Protected — must show zero *unauthorized* diffs (Task 14 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`. This cycle imports from `backtest` in no task and edits neither. **`backtest.py` not being edited is load-bearing** — see A10 for what it means for the gate.

**Nine tasks are STOPs.** Every one of them enumerates its line-groups before it runs, and none of them runs until the orchestrator authorizes it:

| Task | Protected file(s) | Spec authority |
| --- | --- | --- |
| 1 | `optimize/milp.py` | §4.1 |
| 2 | `web/routers/whatif.py` | §4.1 |
| 4 | `optimize/chip_policy.py`, `optimize/chips.py`, `advise.py` | §4.2 |
| 5 | `optimize/milp.py` | §4.3 |
| 6 | `advise.py` | §4.3 |
| 8 | `optimize/scenarios.py`, `advise.py`, **`tests/test_v10_degradation.py`** | §4.4 |
| 9 | `optimize/chips.py`, `advise.py` | §4.5 |
| 10 | `optimize/chips.py`, `optimize/milp.py`, `advise.py` | §4.5 |
| 11 | `optimize/differentials.py`, `advise.py` | §4.6 |

Every authorized edit carries the provenance comment
`# v12 W3 §<id> (specs/2026-09-01-gaffer-v12-program-design.md)` on its line-group.

**If a task concludes a further protected edit is required, it STOPs and reports rather than widening the diff.** Three candidates were checked and cleared: the alternatives payload (served from `routers/plan.py`, unprotected — A11), the drafts store's new constraint (`drafts.py` and `routers/drafts.py`, unprotected), and the captain table's caption (`report/templates/report.html.j2`, unprotected).

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml` or `src/gaffer/web/static/`.

**Gate rule (CONVENTIONS §7):** implementers build the drivers and never run them. Task 14 is the checklist with G1 measured and G2/G3 unfilled.

**Frontend test runner: `npx vitest run`.** `npm test` maps to bare `vitest`, which is watch mode and hangs an agent forever. **Python: `.venv/bin/pytest`** — there is no bare `python` on PATH; use `.venv/bin/python`.

**Pins.** Measured at `27f7933` (the spec commit) because that is the only commit that exists while this plan is written. W1 and W2 land between there and W3's base, and both add config keys (§2.6 `top_n`, §2.1 `[backup]`, §2.8 `[web] token`, §3.4 `price_timing`, §3.5 `[model] xg_per_shot`), so the **base** number will be larger. What W3 owns is the *delta*.

**There is no `[solver]` section.** The spec names three keys under one (§2.6 `top_n`, §3.4 `price_timing`, §4.3 `alt_plan_max_gap`) and the program-wide ruling (orchestrator, 2026-09-02) is that every solver knob goes in the existing `[optimizer]` section under its own key name. This plan reads `alt_plan_max_gap` from `[optimizer]`, which is *splatted* into `Config` (`config.py:146`) and so needs no explicit read line at all.

| Pin | At `27f7933` | W3's delta | Expected at the end of W3 |
| --- | --- | --- | --- |
| `len(dataclasses.fields(Config))` | 48 | **+2** (`alt_plan_max_gap`, `draw_availability`) | base + 2 |
| `len(JOB_KINDS)` | 12 | **0** — no new job; alternatives ride the advise run | base |
| `len(create_app().openapi()["paths"])` | 45 | **0** — every serve-side change is an additive field | base |

```bash
# how all three are measured; run this at W3's base commit BEFORE Task 1
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# at 27f7933: 45 12 48
```

**Suite baselines at `27f7933`, measured: 3193 Python tests collected; 655 frontend passed + 1 skipped (68 files).** Re-measure both at W3's base before Task 1 and write the numbers into this header, because every task's final run is judged against them:

```bash
.venv/bin/pytest -q --collect-only | tail -1     # record: <N> tests collected
cd frontend && npx vitest run                    # record: <N> passed, 1 skipped
```

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Preflight — run this before Task 1 and stop if any line surprises you

```bash
# 1. The pins, at the real base commit (see Pins above). If Config is not 48
#    at the base, W1/W2 added keys: the pin in Task 12 becomes base + 2. Write
#    the measured base into this file's header before starting.

# 2. The protected rail §4.4 has to move. Confirm it is still where A6 says:
grep -n "p_play. not in src" tests/test_v10_degradation.py
# expect one hit around L534, inside
# test_the_p_play_seam_follows_the_sweep_and_not_the_solve

# 3. The two counted-source rails in advise.py that this cycle must NOT break:
grep -n "p_play=p_play_by_code" src/gaffer/advise.py     # expect exactly 2
grep -n "wildcard_now_assessment(" src/gaffer/advise.py  # expect 1, at ~900

# 4. The chip-pair feature is data-gated. Confirm it is still gated:
ls data/chip_scenarios.toml     # expect: No such file or directory
```

If (2) has moved, re-read A6 and re-enumerate Task 8's edit against the current
line numbers. If (4) now exists, the WC+BB row is **live** rather than
data-gated and Task 9's empty-state test becomes a populated-path test as well
— say so in the commit message and keep both.

---

## Ambiguities and findings, and how this plan settles them

### A1 — "byte-identical with `force_out=[]`" is checkable at the LP, and this plan checks it there

The brief asks for a regression guard proving a plan is byte-identical with `force_out=[]` against the pre-change code path. Comparing two `Plan` objects would prove the *solution* matched, which is weaker than it sounds: two different LPs routinely have the same optimum, and the failure this guard exists to catch — a constraint accidentally emitted for an empty list, shifting every auto-generated constraint name after it — is invisible in the answer.

PuLP builds the model in `_solve_once` and hands it to `milp._solve(prob)` as one argument. A test can therefore monkeypatch `milp._solve`, call `prob.writeLP(path)`, and read the model back as text. **Measured before this plan was written**: the capture is 37,628 bytes for a two-gameweek fixture pool and is byte-stable across repeated runs on the same code (`a == b` → `True`, PuLP 3.3.2).

**Settled: Task 1 generates `tests/data/v12_w3_milp_golden.lp` from the unmodified `milp.py` as its first step, commits it alongside the change, and the rail asserts the post-change capture equals that file byte for byte.** That is literally "vs the pre-change code path". The same rail is re-run in Task 5 and Task 10, which also add optional parameters to `_solve_once`, so one golden guards all three.

The fixture pool is pinned inside the test rather than imported, because a golden generated from a pool that later changes is a golden that fails for the wrong reason. If PuLP's version changes the LP writer's formatting the rail fails loudly — the fix is to regenerate the golden **from a commit where the LP-building code is unchanged**, never from the branch.

### A2 — §4.2's flat bar is consulted in one live place, and it is `wildcard_now_assessment`

The spec says "wherever a flat threshold is consulted while θ is available, use θ". Grepped, the constants have four readers:

| Reader | Consults the flat bar? | Verdict |
| --- | --- | --- |
| `chip_policy.flat_thresholds()` (`:152-157`) | yes, by construction | **keep** — it is the degradation rail the spec explicitly preserves |
| `advise.py:895-897` | no — it calls `chip_thresholds(...)`, which is θ | already right |
| `backtest.py:214` (`_pick_chip`) | only when `thresholds is None`, and `backtest.py:419` always passes one | already right |
| `chips.py:232` (`wildcard_now_assessment`) | **yes, unconditionally** | **the bug** |

`wildcard_now_assessment` is called from `advise.py:900`, in the same function that built `chip_thresholds` at `:735` and applied it to every chip row at `:895`. So the advice can, today, print a wildcard row whose θ bar says "wait" and a "Wildcard now" verdict whose flat 8.0 says "play it" — two answers to one question, on one page, from one run.

**Settled: `wildcard_now_assessment` gains a `thresholds=None` keyword; `advise.py` passes the lookup it already has.** With no lookup the function is byte-for-byte today's, which is what keeps `tests/test_chips.py`'s existing assertions and the backtest's untouched behaviour valid.

One deliberate asymmetry: the flat path keeps `gain > bar` and the θ path uses `gain >= bar`. That is not sloppiness — `>=` is the rule `chip_plan` (`chips.py:277`) and `advise.py:897` already apply to every other chip, and a wildcard that clears θ exactly should read the same way a bench boost that clears θ exactly does. The flat path keeps `>` because changing it would move a shipped verdict for no reason this cycle can measure. Both are pinned.

### A3 — a threshold cannot say where it came from, so this cycle teaches it to

Spec §4.2 wants the caption to read `threshold: θ (v4c)` or `threshold: flat fallback` **and why**. `chip_thresholds_from_asset` returns a bare `(chip, gw) -> float` closure. Every fallback inside it is silent, and there are three distinct ones (`chip_policy.py:171-174, 186-190, 200-210`): no priors asset at all, a chip absent from the calibrated table, and a gameweek the table does not cover.

**Settled: both factories attach an `explain(chip, gw) -> (bar, source)` attribute to the callable they return, and a module function `threshold_with_source(lookup, chip, gw)` reads it with a `getattr` fallback.** The callable stays a callable, so `backtest.py:214`, `meta.py:79` and every existing test keep working unchanged, and a lookup that predates the attribute degrades to `("unknown")` rather than raising. The source strings are written server-side and rendered verbatim, so the reason lives with the rule instead of being reconstructed in TypeScript.

### A4 — the "EP gap" between plans is an objective gap, and the plan says so rather than converting

Spec §4.3 prices an alternative by "the EP gap ... over the horizon" against `alt_plan_max_gap = 2.0` (the spec says `[solver]`; the section is `[optimizer]` — see **Pins**). `solve_plan` returns `Plan.objective`, which is *not* EP: it is decayed by `decay ** t`, carries the bench curve and the vice hedge, subtracts hit cost and `ft_use_penalty`, and adds the terminal FT and ITB values. `advise.py` already knows the difference and keeps a separate `raw_xi_pts` for anything a manager reads.

Re-scoring the alternatives in raw EP would compare two plans on a quantity **neither of them was selected by**, and would let a plan that is 4 objective points behind read as 0.5 EP ahead because the difference was all banked transfers.

**Settled: the gap is `incumbent.objective - alternative.objective`, in the objective frame both were solved in, and every surface that prints it says so.** The board's caption reads "objective points — the solver's own frame, which discounts later weeks and prices banked transfers", and the per-week xPts on each alternative's card stays `raw_xi_pts` exactly as Plan A's does. The config key keeps the spec's name and its 2.0 default.

### A5 — the gap is signed, because Plan A is not the unconstrained optimum

With a scenario sweep running, the plan the user is shown is `coherent_plan`'s — the best plan *containing the moves the sweep voted for* (`policy.py:191-194`). The alternatives are solved without those `FixedMoves`, because an alternative constrained to make Plan A's moves is not an alternative.

So an alternative can be **worth more** than Plan A, and the gap is then negative. That is not a bug to clamp away: it is the price of the coherence constraint, made visible for the first time, and it is exactly the number a reader deciding whether to override the sweep wants.

**Settled: `gap` is signed, `alt_plan_max_gap` bounds it above only (`gap > max_gap` stops the search), and the UI branches on the sign** — the same rule `sensitivity.rank_plans` already established for its own signed margin (`sensitivity.py:263-281`), and the same words: a negative gap says the alternative is *ahead*.

### A6 — §4.4 cannot be built without moving a protected v10 rail, and the spec does not say so

`tests/test_v10_degradation.py:516-538` is `test_the_p_play_seam_follows_the_sweep_and_not_the_solve`, and its middle assertion is:

```python
    sweep_call = src.index("run_scenarios(")
    assert "p_play" not in src[src.index("run_scenarios("):sweep_call + 300]
```

The rail's stated reason (its own docstring) is that `decide()` compares the raw optimum against the sweep's plurality, so weighting the sweep's *objective* with `p_play` would report `raw_optimum_agrees=False` for a reason that is not instability. §4.4 needs `p_play` inside that call for a different purpose — an availability **draw**, not an objective weight — and the substring test cannot tell the two apart.

Two ways not to take: renaming the variable so the substring does not appear would be gaming a rail whose intent is plain, and skipping §4.4 would drop a spec item over a test. **Settled: Task 8 is a STOP that edits the rail**, narrowing it from "the sweep never sees `p_play`" to the claim T10-A actually needs — *the sweep's solve bundle is still `solve_kw`, so no scenario is solved under §F1's frailty weights, and the raw optimum the gate compares against is still the unweighted one* — and the docstring is rewritten to say which claim moved and why.

**And the consequence has to be stated rather than discovered.** With the draw on, the sweep models availability risk that the raw solve does not, so `raw_optimum_agrees` will read `False` more often. Unlike the objective mismatch T10-A was protecting against, that disagreement is *information*: "did he play" is the largest single source of forecast error (`scenarios.py:16-19`), and a raw optimum that ignores it disagreeing with a sweep that does not is the sweep doing its job. It is recorded as a residual and named in the README line.

### A7 — the free hit is already a re-solve; what is approximate is the week it solves from

`free_hit_gain`'s docstring calls itself "a documented approximation" and lists two understatements. Read the code (`chips.py:195-206`) and the re-solve the spec asks for is already there: a fresh `SolveInput` with no squad, `free_transfers=15`, `gws=[gw]`, and the sell value of the current squad as budget. The approximations are elsewhere:

1. **The baseline's saved hits.** `base_gw_ep` is `GwPlan.expected_pts`, gross of hit cost. A free hit suspends that week's transfers, so the hits the baseline would have paid are *saved* by playing the chip and the gain is short by exactly `hit_cost × hits`.
2. **The position it solves from.** The budget is today's squad and today's bank, for a chip the table may be pricing three weeks out. By then the baseline plan has bought and sold, and its bank is different.

Fixing (2) needs the baseline's bank in that week, and **`GwPlan` has never carried one** — the MILP's `bank[t]` variable is solved and thrown away. That is the one structural addition in §4.5.

**Settled: `GwPlan` gains `bank: float | None` (0.1m units, straight off `bank[t].varValue`), and `free_hit_gain` scores the FH week against `base_week.expected_pts - hit_cost * base_week.hits`, from a budget built out of `base_week.squad` and `base_week.bank`.** When the bank is unreadable — an older `Plan`, a solver that returned no value — it falls back to today's squad and today's bank, which is exactly the current behaviour, and prints one line saying so. The third approximation the docstring names (a free hit leaves transfers and bank untouched for the rest of the horizon) is **not** fixed: pricing it needs a two-branch horizon solve, and spec §4.5 asks for a true re-solve of the FH week, not of the season. It stays in the docstring.

### A8 — the WC+BB pair is dead on today's data, and ships as an honest empty state

Spec §4.5 gates the pair on "a DGW in the horizon (from `load_chip_scenarios`)". Measured: `data/chip_scenarios.toml` does not exist, and `data/chip_scenarios.py::write_chip_scenarios` **deliberately refuses to create it** while no gameweek has a team playing twice — which is every gameweek of the published 2026-27 list ("ten fixtures in every one of thirty-eight gameweeks", its own plan A11). So `load_chip_scenarios()` is `{}` and will stay `{}` until the cup rounds produce a rearrangement.

**Settled: the pair row is built from a `dgw_gws` argument the *caller* supplies, `chips.py` does no I/O, and `advise.py` derives the set from `load_chip_scenarios()` it already loads at `:736`.** Three consequences worth writing down:

- **The replay never sees a pair.** `backtest.py` calls `evaluate_chips` without `dgw_gws` (and is import-only this cycle), so no pair row can reach `_pick_chip` — which matters, because `_pick_chip` would happily return `"wildcard+bboost"` and `backtest.py:542-560`'s chip branch has no arm for it: the replay would record a chip as played and apply nothing. Keeping the argument opt-in is what makes that unreachable rather than merely unlikely.
- **`routers/meta.py`'s chip planner does not pass it either**, for the same reason and one more: `ChipsTab`'s `pick()` maps a chip name through `CHIP_CODES` and a pair has no two-letter code, which the component already handles by leaving the request alone (`ChipsTab.tsx:127-131`).
- **A ROADMAP checkbox** names the unblocking condition: `data/chip_scenarios.toml` carrying a `[dgw]` entry.

### A9 — §4.6's disclaimed number is `ep_matrix`'s `p_haul`, and the replacement already exists

`grep`ped, there is no "ranking" disclaimer anywhere near a captain. There is one on the *bench* order (`milp.py:684-691`) and it is not this — touching it would move v10 §F1b's gated result for a reason §4.6 never asked for. The number §4.6 is actually describing is:

```python
    return (per_fixture.groupby(["code", "gw"], as_index=False)
            .agg(ep=("ep", "sum"), p_haul=("p_haul", "max")))
```

— `models/assemble.py:142-143`, whose docstring is the caption: *"`p_haul` takes the best single fixture rather than summing, since it is a probability."* It reaches the reader through `differentials.captain_table`, which uses it as the ceiling and as half the `differential` rule, and through `report.html.j2:90` under the header **`P(2+ returns)`**. In a double gameweek that column is the better of two fixtures — a ranking number wearing a probability's label.

The quantity §4.6 asks for — the two-fixture point distribution, EP summed with the existing σ — is `uncertainty.bands_by_player_gw`, keyed `(code, gw)`, EP summed across a double and xMins averaged, already serving `/api/players` and `/api/components`.

**Settled: `captain_table` gains an optional `haul` map; `advise.py` fills it from `bands_by_player_gw(comp)`; the column becomes `p_haul_total` and the header becomes `P(10+ pts)`.** `ep_matrix` is **not** touched — it is on the training and backtest hot path and changing its aggregate would move every EP table in the tree for a display column. With no map the function returns exactly today's frame, which is the degradation rail.

One consequence: `routers/advice.py:113`'s `HAUL_KEYS` renames `p_haul` → `p_attacking_haul` on `captain_options`. That rename becomes a no-op by itself (`advice.py:156` only renames dicts that *have* `p_haul`), so no code changes — but the docstring says something that stops being true and is corrected.

### A10 — the W3 replay gate measures §4.5 and no-regresses the other five, and this must be said before it runs

The gate is the 2025-26 gated replay against `main`, three seed bases a side, via `scripts/replay_pair.sh` (v10's G2 driver — `scripts/v10_autosub_cf.py` is the *counterfactual* driver for a different question and is the model for Task 8's support driver, not for this). The replay runs `backtest.run_backtest`, so it sees only what `backtest.py` calls:

| Item | On the replay's path? | Why |
| --- | --- | --- |
| §4.1 `force_out` | **no** | `backtest.py` never sets it; the default-empty path is what the LP golden guards |
| §4.2 θ | **no** | `_pick_chip` already takes θ (`backtest.py:419`); `wildcard_now_assessment` is not called by the replay at all |
| §4.3 alternatives | **no** | computed in `advise.py`, which the replay does not run |
| §4.4 availability draw | **no** | the replay's gate calls `run_scenarios` with no `p_play` (`v7b_replay.py:295-296`) |
| §4.5 free hit | **YES** | `evaluate_chips` → `free_hit_gain` is on the replay's chip path (`backtest.py:540`) |
| §4.5 WC+BB pair | **no** | `dgw_gws` is opt-in and the replay does not pass it (A8) |
| §4.6 captain ceiling | **no** | annotation on the advice payload; the replay scores its own captain |

**So the W3 replay is a measurement of the free hit and a no-regression check on everything else** — the same honest demotion v10's G2 recorded ("G2 therefore cannot see §F1 and is a no-regression check on the seed spread"). Task 14 states it that way, pre-registered, and §4.4's own gate (the captain-support check, Task 8's driver) is the one that judges the sweep.

### A11 — the alternatives reach the board without a route, and without `plan_by_gw` changing shape

`GET /api/plan/{gw}` reads `plan_by_gw` off the advice artifact and joins prices from the saved solve state (`routers/plan.py`, unprotected). An alternative is the same structure with a gap on it, so it rides as a new key on the artifact (`alternative_plans`) and a new field on `PlanTimeline` — no route, no job, and `plan_by_gw` itself untouched, so v11's bank arithmetic and every existing reader are undisturbed. The week-building loop in `plan()` is extracted to a helper and called twice.

### A12 — "the ledger records it" is the drafts store, because no ledger takes a constraint

Spec §4.1 says the ledger records `force_out`. The decision ledger (`reports/decision_ledger.json`, `review.py`) records what the *advice run decided*, and no advice run takes a `force_out` — it is a user constraint, expressible only through the What-If lab and the board's handoff. The store that records "what you asked for" is `drafts.py`, whose module docstring says so in as many words: *"A draft is what you asked for, not what you got."*

**Settled: `drafts.CONSTRAINT_DEFAULTS` and `normalize` learn `force_out`, and `routers/drafts.py`'s re-solve passes it**, so a named draft round-trips the constraint. The decision ledger is left alone. **Question for the orchestrator if this reading is wrong** — see the closing report.

### A13 — a free hit and `force_out` are contradictory, and the lab says so rather than ignoring it

A free hit conjures a squad from scratch (`owned_codes=[]`), so there is nothing to force out of it: the constraint would silently do nothing. `whatif._validate` already refuses four combinations that mean nothing; this is a fifth, with the same 422 shape, rather than a constraint the user sets and never sees applied.

---

## Task 1 — **STOP** — `force_out`: the constraint the vocabulary was missing

**Files:**
- Modify `src/gaffer/optimize/milp.py` — **PROTECTED**
- Create `tests/test_v12_w3_force_out.py`
- Create `tests/data/v12_w3_milp_golden.lp` (generated, committed)

> ### STOP
>
> **Do not start this task.** Report to the orchestrator that Task 1 is ready, paste the enumeration below, and wait for explicit authorization to edit `src/gaffer/optimize/milp.py`. Spec §4.1 orders the field and this plan enumerates it; neither of those is the authorization.

### The complete enumeration — four line-groups in one file

| # | Location (at `27f7933`) | Change |
| --- | --- | --- |
| E1 | `milp.py:14-16` | a third module-docstring bullet, distinguishing `force_out` from `locked_out` |
| E2 | `milp.py:151-155` | `SolveInput.force_out`, appended **after** `max_hits` so every positional construction still works |
| E3 | `milp.py:455-461` | `force_out` joins the pool-membership validation loop; one new refusal for `force_out ∩ locked_in` |
| E4 | `milp.py:564-565` | `sq[c][t] == 0` per forced-out code, per gameweek, immediately after the `locked_in` loop |

**E1 — `milp.py:14-16`, after the `locked_out` bullet.**

```python
* ``locked_out`` removes players from the pool outright, so it is meant for
  players you do *not* own. Locking out an owned player makes them vanish
  from the squad without generating sale proceeds.
* ``force_out`` is the other half of that: the player stays in the pool, so
  squad continuity turns his ownership into a sale in the first horizon
  gameweek and the bank receives his sell price. "I am selling him" and "he
  may not be bought" are different instructions and this module now has both.
```

**E2 — `milp.py`, appended to `SolveInput` after `max_hits`.**

```python
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md)
    force_out: list[int] = field(default_factory=list)
    """Codes that must not be in the squad in any gameweek of the horizon.

    Distinct from :attr:`locked_out`, which deletes the player from the pool
    and so makes an owned player disappear without sale proceeds (module
    note). A forced-out player stays in the pool, so the continuity
    constraint spends his ownership as a transfer out in the first gameweek
    and the budget row receives his ``sell`` price.

    Appended last, and defaulted, so every positional construction of this
    dataclass in the tree still builds — and so an empty list adds not one
    constraint to the model. ``tests/data/v12_w3_milp_golden.lp`` pins that.
    """
```

**E3 — `milp.py:455-461`, inside `_solve_once`.** The loop gains a third entry and a refusal follows it:

```python
    for label, wanted in (("lock", state.locked_in),
                          ("force_in", state.force_in_gw),
                          # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md):
                          # a code that is not in the pool cannot be
                          # constrained, and silently not selling a player the
                          # caller said to sell is the failure worth refusing.
                          ("force_out", state.force_out)):
        missing = [c for c in wanted if c not in known]
        if missing:
            raise GafferError(
                f"{label}: player code {missing[0]} is not in the candidate "
                f"pool (it may also be banned)")
    # v12 W3 §4.1: caught here rather than left to the solver, which would
    # report "MILP not optimal: Infeasible" and name nothing.
    contradiction = sorted(set(state.locked_in) & set(state.force_out))
    if contradiction:
        raise GafferError(
            f"force_out: player code {contradiction[0]} is also locked in — "
            f"a squad cannot both keep and sell him")
```

**E4 — `milp.py:564-565`, inside the `for t_i, t in enumerate(T)` loop, directly after the `locked_in` loop.**

```python
        for c in state.locked_in:
            prob += sq[c][t] == 1
        # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md): squad
        # membership 0 from the first horizon gameweek onward. Continuity
        # (``sq == prev + tin - tout``) turns an owned player's zero into a
        # ``tout`` in the first week, which is what pays the bank.
        for c in state.force_out:
            prob += sq[c][t] == 0
```

### Steps

- [ ] **Write the test file first, with its golden writer.** Create `tests/test_v12_w3_force_out.py`:

```python
"""§4.1: "sell this player", and the proof that saying nothing changes nothing.

Two halves. The first is the constraint: a forced-out player is gone from
every horizon week, the bank receives his sell price (which is what separates
this from ``locked_out``, where he simply vanishes), and a contradiction is
refused by name rather than by the solver's word "Infeasible".

The second is the regression guard the workstream was asked for. Comparing two
solved plans would only prove the *answers* matched, and the failure this
guards against — a constraint emitted for an empty list, shifting every
auto-generated constraint name after it — does not change an answer. So the
LP itself is captured: ``_solve_once`` hands the built problem to
``milp._solve`` as one argument, which a monkeypatch can write out with
``writeLP``. ``tests/data/v12_w3_milp_golden.lp`` was generated from
``milp.py`` **before** this cycle touched it, and the rail is byte equality
against that file.

Regenerating the golden is a deliberate act, not a fix: it is only valid from a
commit whose LP-building code is unchanged. A failure here after a PuLP
upgrade is a formatting change; a failure here after an ``optimize`` edit is
the thing the file exists to catch.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gaffer.errors import GafferError
from gaffer.optimize import milp
from gaffer.optimize.milp import SolveInput, solve_plan

GOLDEN = Path("tests/data/v12_w3_milp_golden.lp")

GWS = [1, 2]
KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
          itb_value=0.05, hit_cost=4, bench_curve=[0.21, 0.06, 0.002])
OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 22, 23, 24]


def _pool() -> pd.DataFrame:
    """A pinned pool, defined here and imported by nothing.

    The golden is a function of these numbers, so a pool that drifts is a
    golden that fails for a reason that has nothing to do with the solver.
    """
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40 + i, "sell": 40 + i,
                         "ep": {1: 1.0 + (code % 7) * 0.3,
                                2: 2.0 + (code % 5) * 0.2}})
            code += 1
    return pd.DataFrame(rows)


def _state(**kw) -> SolveInput:
    base = dict(owned_codes=list(OWNED), bank=0, free_transfers=2, gws=GWS)
    return SolveInput(**{**base, **kw})


def _capture_lp(tmp_path: Path, state: SolveInput, **kw) -> list[str]:
    """Every LP ``solve_plan`` builds for this call, as text."""
    out: list[str] = []
    real = milp._solve

    def spy(prob):
        path = tmp_path / f"model{len(out)}.lp"
        prob.writeLP(str(path))
        out.append(path.read_text())
        real(prob)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(milp, "_solve", spy)
        solve_plan(_pool(), state, **KW, **kw)
    return out


def write_golden() -> None:
    """Regenerate the golden. Run from a commit with milp.py unedited::

        .venv/bin/python -c "import tests.test_v12_w3_force_out as t; \\
            t.write_golden()"
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    text = _capture_lp(tmp, _state())[0]
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(text)
    print(f"wrote {GOLDEN} ({len(text)} bytes)")


# --- the regression guard -------------------------------------------------

def test_the_lp_capture_is_stable_on_one_code_base(tmp_path):
    """Asked first, so a golden mismatch below is never blamed on the
    instrument. Two captures of the same solve on the same code must be the
    same bytes, or nothing else in this file means anything."""
    a = _capture_lp(tmp_path / "a", _state())
    b = _capture_lp(tmp_path / "b", _state())
    assert a == b


def test_an_empty_force_out_builds_the_pre_change_lp_byte_for_byte(tmp_path):
    """The brief's guard. ``tests/data/v12_w3_milp_golden.lp`` came off the
    code as it stood before ``force_out`` existed."""
    captured = _capture_lp(tmp_path, _state())
    assert len(captured) == 1
    assert captured[0] == GOLDEN.read_text()


def test_a_populated_force_out_does_change_the_lp(tmp_path):
    """The other direction, and the reason the test above is not vacuous: if
    the constraint were never emitted at all, both assertions would pass."""
    captured = _capture_lp(tmp_path, _state(force_out=[1]))
    assert captured[0] != GOLDEN.read_text()


# --- the constraint -------------------------------------------------------

def test_a_forced_out_player_is_in_no_gameweek_of_the_horizon():
    plan = solve_plan(_pool(), _state(force_out=[5]), **KW)
    for gp in plan.gw_plans:
        assert 5 not in gp.squad
        assert 5 not in gp.xi


def test_a_forced_out_player_is_sold_in_the_first_week_and_not_later():
    """Continuity spends the ownership immediately; a sale in week two would
    mean he was owned in week one, which the constraint forbids."""
    plan = solve_plan(_pool(), _state(force_out=[5]), **KW)
    assert 5 in plan.gw_plans[0].sells
    assert all(5 not in gp.sells for gp in plan.gw_plans[1:])


def test_the_bank_receives_the_sale_which_is_what_locked_out_never_did():
    """The distinction the module note now carries. ``locked_out`` deletes him
    from the pool, so the squad is a man short and the money never arrives;
    ``force_out`` sells him."""
    banned = solve_plan(_pool(), _state(locked_out=[5]), **KW)
    sold = solve_plan(_pool(), _state(force_out=[5]), **KW)
    assert len(banned.gw_plans[0].squad) == 15
    assert len(sold.gw_plans[0].squad) == 15
    # The forced sale funds a replacement the ban could not: the banned solve
    # never had 5's sell value to spend.
    assert sold.gw_plans[0].buys


def test_forcing_out_a_player_you_do_not_own_is_not_an_error():
    """He is already out. A no-op constraint is the honest answer — refusing
    would make the board's "must sell" button illegal on a row the plan had
    already sold."""
    plan = solve_plan(_pool(), _state(force_out=[40]), **KW)
    assert all(40 not in gp.squad for gp in plan.gw_plans)


def test_a_code_outside_the_pool_is_refused_by_name():
    with pytest.raises(GafferError, match="force_out: player code 9999"):
        solve_plan(_pool(), _state(force_out=[9999]), **KW)


def test_locking_in_and_forcing_out_the_same_player_is_refused_by_name():
    """The solver would say "MILP not optimal: Infeasible" and name nobody."""
    with pytest.raises(GafferError, match="also locked in"):
        solve_plan(_pool(), _state(locked_in=[5], force_out=[5]), **KW)


def test_forcing_out_more_than_the_budget_can_replace_stays_infeasible():
    """Spec §4.1's infeasible case. It is a RuntimeError from ``_solve_once``,
    which ``routers/whatif.py`` already turns into the payload naming the
    constraints — Task 2 adds ``force_out`` to that sentence."""
    poor = _state(bank=0, force_out=[1, 2])      # both keepers, nothing to buy
    with pytest.raises(RuntimeError, match="MILP not optimal"):
        solve_plan(_pool(), poor, **KW)


def test_force_out_survives_a_second_pass(tmp_path):
    """§F1a's re-weighted pass re-solves the same problem with pins taken from
    pass one. A constraint that lived only in pass one would be silently
    dropped by every p_play-carrying caller."""
    pool = _pool()
    p_play = {int(c): {g: 0.5 + (int(c) % 5) * 0.1 for g in GWS}
              for c in pool["code"]}
    plan = solve_plan(pool, _state(force_out=[5]), **KW, p_play=p_play)
    assert all(5 not in gp.squad for gp in plan.gw_plans)
```

- [ ] **Generate the golden — before touching `milp.py`.**

```bash
.venv/bin/python -c "import tests.test_v12_w3_force_out as t; t.write_golden()"
ls -l tests/data/v12_w3_milp_golden.lp   # ~37KB at the fixture above
```

If this errors on `force_out` the file was edited first: `git checkout src/gaffer/optimize/milp.py`, regenerate, then implement.

- [ ] **Run the tests: they fail on the field.** `.venv/bin/pytest -q tests/test_v12_w3_force_out.py` — expect `TypeError: SolveInput.__init__() got an unexpected keyword argument 'force_out'` on every constraint test, and the two golden tests **passing** (they exercise the unedited path).

- [ ] **Implement E1-E4** exactly as enumerated above.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_force_out.py
.venv/bin/pytest -q tests/test_milp.py tests/test_v10_milp_p_play.py \
  tests/test_v4c_degradation.py tests/test_v10_degradation.py \
  tests/test_chips.py tests/test_scenarios.py
.venv/bin/pytest -q
```

The golden test failing after the implementation means a constraint is being emitted for an empty list: **stop and report**, do not regenerate the golden.

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/milp.py tests/test_v12_w3_force_out.py \
  tests/data/v12_w3_milp_golden.lp && git commit -m "$(cat <<'EOF'
feat: force_out — the constraint that says sell him, not ban him

locked_out deletes a player from the pool, which is right for someone you do
not own and wrong for someone you do: an owned player vanishes from the squad
and the sale proceeds never arrive. force_out keeps him in the pool and pins
squad membership to 0, so continuity spends the ownership as a transfer out in
the first horizon week and the budget row receives his sell price.

The regression guard is at the LP rather than at the answer. Two plans can
match while the models behind them differ, and the failure worth catching — a
constraint emitted for an empty list — never changes an answer. So the built
problem is written out with writeLP and compared byte for byte against a golden
captured from this file before the field existed.

v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edit.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — **STOP** — `force_out` on the wire: the lab, the drafts, the refusals

**Files:**
- Modify `src/gaffer/web/routers/whatif.py` — **PROTECTED**
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/drafts.py`
- Modify `src/gaffer/web/routers/drafts.py`
- Create `tests/test_v12_w3_whatif_force_out.py`

> ### STOP
>
> **Do not start this task.** Report that Task 2 is ready, paste the enumeration, and wait for authorization to edit `src/gaffer/web/routers/whatif.py`. Task 1 must be authorized and merged first — the router passes a field that does not otherwise exist.

### The complete enumeration — `routers/whatif.py`, three line-groups

| # | Location (at `27f7933`) | Change |
| --- | --- | --- |
| W1 | `whatif.py:46-51` | `req.force_out` joins the unknown-player check |
| W2 | `whatif.py:56-61` | four new refusals, in the file's existing `_fail` shape |
| W3 | `whatif.py:139-140`, `:153-156` | the constraint reaches `yours_state`; the infeasibility sentence names it |

**W1 — `whatif.py:46-51`.**

```python
    known = {int(c) for c in state.pool["code"]}
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md): force_out is
    # checked against the same pool as the other three — ``_solve_once``
    # refuses an unknown code with a GafferError, which would reach the user as
    # a failed job rather than as a 422 beside the input he typed.
    unknown = sorted({*req.lock, *req.ban, *req.force_in,
                      *req.force_out} - known)
```

**W2 — `whatif.py`, after the `force_in_and_ban` refusal at `:57-61`.**

```python
    # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md). Four
    # combinations that cannot mean anything, each named where the user typed
    # it rather than left to produce a constraint that silently does nothing.
    not_owned = sorted(set(req.force_out) - set(state.owned_codes))
    if not_owned:
        raise _fail("force_out_not_owned",
                    f"you do not own player {not_owned[0]} — use ban to keep "
                    f"him out of the squad", not_owned)
    out_and_lock = sorted(set(req.force_out) & set(req.lock))
    if out_and_lock:
        raise _fail("force_out_and_lock",
                    f"player {out_and_lock[0]} cannot be both kept and sold",
                    out_and_lock)
    out_and_ban = sorted(set(req.force_out) & set(req.ban))
    if out_and_ban:
        raise _fail("force_out_and_ban",
                    f"banning player {out_and_ban[0]} removes him without "
                    f"sale proceeds; force_out sells him — pick one",
                    out_and_ban)
    if req.force_out and req.chip == "fh":
        # A free hit squad is conjured from nothing (``owned_codes=[]``), so
        # there is nobody to sell and the constraint would apply to no one.
        raise _fail("force_out_on_free_hit",
                    "a free hit squad is built from scratch, so there is "
                    "nothing to force out of it", list(req.force_out))
```

**W3 — `whatif.py:139-140` and `:153-156`.**

```python
        locked_out=list(req.ban), locked_in=list(req.lock),
        force_in_gw=list(req.force_in),
        # v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md)
        force_out=list(req.force_out), max_hits=req.max_hits)
```

and

```python
        raise GafferError(
            f"no legal squad satisfies those constraints "
            f"(lock={req.lock}, ban={req.ban}, force_in={req.force_in}, "
            f"force_out={req.force_out}, max_hits={req.max_hits}): {exc}"
        ) from exc
```

The free-hit branch at `:146-149` is **not** changed: W2 has already refused that combination, and adding an argument there would encode a state the validator forbids.

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_whatif_force_out.py`:

```python
"""§4.1 on the wire: the request field, the four refusals, the re-solve.

The refusals are the interesting half. Three of the four are combinations that
would otherwise produce a constraint doing nothing at all — a user who ticks
"must sell" on a player he does not own, or on a free hit, gets an answer that
looks like it honoured him. The fourth (lock + force_out) would reach the
solver, which refuses it by name since Task 1; this catches it a layer earlier,
beside the input, which is where ``_fail`` exists to put things.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.web.routers import whatif as wf
from gaffer.web.schemas import WhatIfRequest


class _State:
    """The saved solve state ``_validate`` reads, and nothing more."""

    def __init__(self, owned=(1, 2, 3), pool_codes=(1, 2, 3, 4, 5)):
        self.owned_codes = list(owned)
        self.pool = pd.DataFrame({"code": list(pool_codes)})
        self.gws = [5, 6, 7]
        self.avail_by_gw = {5: ["wildcard", "freehit"]}


def _req(**kw) -> WhatIfRequest:
    return WhatIfRequest(**kw)


def test_the_request_carries_force_out_and_defaults_it_empty():
    assert _req().force_out == []
    assert _req(force_out=[1]).force_out == [1]


def test_an_unknown_code_is_refused_like_every_other_list():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(force_out=[99]), _State())
    assert exc.value.detail["constraint"] == "unknown_player"


def test_forcing_out_a_player_you_do_not_own_is_refused():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(force_out=[4]), _State())
    assert exc.value.detail["constraint"] == "force_out_not_owned"
    assert "use ban" in exc.value.detail["error"]


def test_locking_and_forcing_out_the_same_player_is_refused():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(lock=[1], force_out=[1]), _State())
    assert exc.value.detail["constraint"] == "force_out_and_lock"


def test_banning_and_forcing_out_the_same_player_is_refused():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(ban=[1], force_out=[1]), _State())
    assert exc.value.detail["constraint"] == "force_out_and_ban"


def test_force_out_on_a_free_hit_is_refused_rather_than_ignored():
    """The FH branch builds ``owned_codes=[]``, so the constraint would apply
    to nobody and the user would read an answer that looked like it applied."""
    with pytest.raises(Exception) as exc:
        wf._validate(_req(force_out=[1], chip="fh"), _State())
    assert exc.value.detail["constraint"] == "force_out_on_free_hit"


def test_an_empty_force_out_still_validates_every_pre_existing_way():
    """The degradation direction: nothing above may fire on today's requests."""
    wf._validate(_req(lock=[1], ban=[4], force_in=[5]), _State())


def test_the_router_passes_force_out_and_prints_it_when_infeasible():
    """Two claims in one: the constrained ``SolveInput`` is built with the
    codes, and the sentence a user reads on an infeasible board says which
    lists produced it. Read off the source rather than by stubbing the solver,
    which is how ``tests/test_v8e_degradation.py`` already pins this module's
    board-building idiom."""
    import inspect

    src = inspect.getsource(wf.solve_whatif)
    assert "force_out=list(req.force_out)" in src
    assert "force_out={req.force_out}" in src
    # The free-hit branch must NOT carry it: _validate has already refused the
    # combination, and encoding a forbidden state is how it becomes reachable.
    fh = src[src.index('if chip == "freehit"'):src.index("try:")]
    assert "force_out" not in fh
```

Run it: `.venv/bin/pytest -q tests/test_v12_w3_whatif_force_out.py` — fails on `WhatIfRequest` having no `force_out`.

- [ ] **Implement the schema.** `schemas.py`, `WhatIfRequest` (`:64-70`):

```python
class WhatIfRequest(BaseModel):
    lock: list[int] = Field(default_factory=list)
    ban: list[int] = Field(default_factory=list)
    force_in: list[int] = Field(default_factory=list)
    force_out: list[int] = Field(default_factory=list)
    """Owned players the solve must sell in the first horizon gameweek.

    Not ``ban``: banning an owned player removes him from the candidate pool
    entirely, which also forbids buying him back and — because he leaves the
    pool rather than the squad — never credits the bank with his sale. This
    says "sell him", which is the instruction the planner board's handoff has
    been approximating with ``ban`` since v11.
    """
    max_hits: int = 0
    chip: Literal["none", "wc", "bb", "fh", "tc"] = "none"
    horizon: int | None = None
```

- [ ] **Implement W1-W3** in `routers/whatif.py` exactly as enumerated.

- [ ] **Implement the drafts store** (A12). `drafts.py:32-56`:

```python
CONSTRAINT_DEFAULTS: dict = {"lock": [], "ban": [], "force_in": [],
                             "force_out": [], "max_hits": 0, "chip": "none",
                             "horizon": None}
"""The seven keys a draft may carry — ``WhatIfRequest``'s fields exactly.

Anything else in the payload is dropped rather than stored: the store is fed
from an HTTP body, and a key the solver does not understand is a key that will
be silently ignored later at a worse moment.
"""
```

and in `normalize`, beside `force_in`:

```python
        # v12 W3 §4.1: a draft written before the field carries no key, and
        # ``or []`` reads that as "no forced sales" rather than as a KeyError.
        "force_out": [int(c) for c in raw.get("force_out") or []],
```

- [ ] **Implement the drafts re-solve.** `routers/drafts.py`, the non-free-hit `solve_state` (`:152-158`) gains `force_out=list(req.force_out),` beside `force_in_gw`. The free-hit branch does not, for W3's reason.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_whatif_force_out.py tests/test_web_whatif.py \
  tests/test_drafts.py tests/test_web_drafts.py tests/test_v8e_degradation.py
.venv/bin/pytest -q
```

A `test_v8e_degradation` failure means the four-place board idiom moved: **stop and report**.

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/whatif.py src/gaffer/web/schemas.py \
  src/gaffer/drafts.py src/gaffer/web/routers/drafts.py \
  tests/test_v12_w3_whatif_force_out.py && git commit -m "$(cat <<'EOF'
feat: the lab can say "sell him" instead of "never own him"

WhatIfRequest gains force_out, the lab passes it, and a draft records it — a
draft is what you asked for, and until now it could not ask for this.

Four refusals rather than a constraint that quietly applies to nobody: a player
you do not own (use ban), a player you also locked, a player you also banned
(the two do different things to the bank, so pick one), and any force_out on a
free hit, whose squad is conjured from an empty one.

v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edit to routers/whatif.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — "must sell" on the screen, and the board's handoff stops approximating

**Files:**
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/planning/ConstraintsPanel.tsx`
- Modify `frontend/src/hubs/planning/PlannerBoard.tsx`
- Modify `frontend/src/hubs/planning/WhatIfTab.tsx`, `ChipsTab.tsx` (the two `EMPTY` request literals)
- Create `frontend/src/hubs/planning/ConstraintsPanel.test.tsx`
- Modify `frontend/src/hubs/planning/PlannerBoard.test.tsx`

No protected file. Depends on Task 2.

**Read v11 plan A7 first.** It is the write-up of the limitation this task removes: *"planned **sells** → `ban` — **not** an exact fit: `ban` forbids buying him back as well, which is a stronger constraint than 'sell him'"*, with a printed sentence under the button admitting it. That sentence is now half wrong and the half that is wrong must go.

- [ ] **Write the failing tests.** Create `frontend/src/hubs/planning/ConstraintsPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConstraintsPanel from './ConstraintsPanel'
import type { WhatIfRequest } from '../../types'

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
  chip: 'none', horizon: null,
}

describe('ConstraintsPanel', () => {
  it('offers a must-sell picker beside the other three', () => {
    render(<ConstraintsPanel value={EMPTY} onChange={vi.fn()} />)
    for (const label of ['Lock', 'Ban', 'Force in', 'Must sell']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('lists a forced-out player as a removable chip', () => {
    const onChange = vi.fn()
    render(<ConstraintsPanel value={{ ...EMPTY, force_out: [7] }}
                             onChange={onChange} />)
    // No name is known until one is picked, so the code stands in — the same
    // fallback the other three lists already use.
    expect(screen.getByLabelText('remove 7')).toBeInTheDocument()
  })

  it('says what a must-sell means, because ban and sell are not the same',
    () => {
      render(<ConstraintsPanel value={EMPTY} onChange={vi.fn()} />)
      expect(screen.getByTestId('force-out-note').textContent)
        .toMatch(/sells him.*bank/i)
    })
})
```

and add to `PlannerBoard.test.tsx`:

```tsx
  it('carries a planned sell as a must-sell rather than as a ban', async () => {
    const onTry = vi.fn()
    renderBoard({ onTry })          // the file's existing helper
    await screen.findByTestId('board-week-5')
    await userEvent.click(screen.getByTestId('board-try-5'))
    const request = onTry.mock.calls[0][0]
    expect(request.force_out).toEqual([200])
    expect(request.ban).toEqual([])
  })

  it('no longer warns about buying a sold player back', async () => {
    renderBoard({ onTry: vi.fn() })
    const note = await screen.findByTestId('board-try-note-5')
    expect(note.textContent).not.toMatch(/rules out buying him back/i)
    expect(note.textContent).toMatch(/sold in the solve's first week/i)
  })
```

Run: `cd frontend && npx vitest run src/hubs/planning` — both files fail.

- [ ] **Implement `types.ts`.** `WhatIfRequest` gains `force_out: number[]` beside `force_in`. (W5 §6.6 will generate this file; until then it is hand-maintained and the field must match `schemas.py` exactly.)

- [ ] **Implement `ConstraintsPanel.tsx`.** Two edits:

```tsx
type ListKey = 'lock' | 'ban' | 'force_in' | 'force_out'

const LABELS: Record<ListKey, string> = {
  lock: 'Lock', ban: 'Ban', force_in: 'Force in', force_out: 'Must sell',
}
```

and the grid becomes four columns with the note under it:

```tsx
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(Object.keys(LABELS) as ListKey[]).map((key) => (
          <PlayerPicker
            key={key}
            label={LABELS[key]}
            codes={value[key]}
            names={names}
            onAdd={add(key)}
            onRemove={remove(key)}
          />
        ))}
      </div>
      {/* Ban and Must sell look alike and do different things to the money.
          Said once, here, rather than discovered in a result. */}
      <p className="mt-1.5 text-text-faint" data-testid="force-out-note">
        Must sell removes an owned player in the first week and sells him, so
        the bank gets his selling price and he may be bought back later. Ban
        takes him out of the candidate pool entirely.
      </p>
```

`sm:grid-cols-3` becomes `sm:grid-cols-2 lg:grid-cols-4` so four pickers do not force a horizontal scroll at 390px — v9b's standing convention, which `responsive.test.tsx` enforces tree-wide.

- [ ] **Implement `PlannerBoard.tsx`.** The request mapping and the sentence:

```tsx
  function request(week: PlanGw): WhatIfRequest {
    return {
      lock: [],
      ban: [],
      // v11 carried a planned sell across as `ban`, which also forbade buying
      // him back — the imprecision plan A7 printed under the button. §4.1 gave
      // the solver the constraint that actually says "sell him".
      force_out: week.sells.map((m) => m.code),
      force_in: week.buys.map((m) => m.code),
      max_hits: Math.max(0, Math.min(3, week.hits)),
      chip: (week.chip && CHIP_CODES[week.chip]) || 'none',
      horizon: horizonFor(week),
    }
  }
```

and inside `board-try-note-{gw}`, the first sentence becomes:

```tsx
                    {'This prefills the lab; it does not solve. A planned sell '
                     + 'is carried across as "must sell": he is sold in the '
                     + 'solve\'s first week and the bank receives his selling '
                     + 'price. The bank itself is still not a constraint the '
                     + 'lab accepts.'}
```

Everything after it — the horizon sentence, the hits cap — is unchanged.

- [ ] **Implement the two request literals.** `WhatIfTab.tsx` and `ChipsTab.tsx:101-103` each build an `EMPTY: WhatIfRequest`; both gain `force_out: []`. Grep to be sure none is missed:

```bash
cd frontend && grep -rn "force_in: \[\]" src/
# every hit must now also carry force_out: []
```

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

`tsc` is the real check here: a `WhatIfRequest` literal missing the new field is a compile error, which is how the grep above is made unnecessary.

- [ ] **Commit.**

```bash
git add frontend/src/types.ts \
  frontend/src/hubs/planning/ConstraintsPanel.tsx \
  frontend/src/hubs/planning/ConstraintsPanel.test.tsx \
  frontend/src/hubs/planning/PlannerBoard.tsx \
  frontend/src/hubs/planning/PlannerBoard.test.tsx \
  frontend/src/hubs/planning/WhatIfTab.tsx \
  frontend/src/hubs/planning/ChipsTab.tsx && git commit -m "$(cat <<'EOF'
feat: the board hands over a sale, not a ban

v11 mapped a planned sell onto `ban` and printed the imprecision under the
button, because the constraint vocabulary had no way to say "sell him". It does
now, so the handoff says it and the sentence loses the half that was an apology
for the missing feature.

The lab gains a fourth picker beside Lock/Ban/Force in, and one line saying what
separates the two that look alike: Must sell pays the bank and allows a buy-back,
Ban removes him from the pool.

v12 W3 §4.1 (specs/2026-09-01-gaffer-v12-program-design.md).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — **STOP** — θ is the only chip decision, and it can say so

**Files:**
- Modify `src/gaffer/optimize/chip_policy.py` — **PROTECTED**
- Modify `src/gaffer/optimize/chips.py` — **PROTECTED**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/routers/chips.py`, `src/gaffer/web/routers/meta.py`
- Modify `frontend/src/hubs/planning/ChipsTab.tsx`
- Create `tests/test_v12_w3_chip_threshold.py`
- Modify `frontend/src/hubs/planning/ChipsTab.test.tsx`

> ### STOP
>
> **Do not start this task.** Report that Task 4 is ready, paste the enumeration, and wait for authorization to edit `chip_policy.py`, `chips.py` and `advise.py`.

**Read A2 and A3 before starting.** The flat bar is consulted in exactly one live place, and it is `wildcard_now_assessment`, not the chip table.

### The complete enumeration

| # | File:lines (at `27f7933`) | Change |
| --- | --- | --- |
| C1 | `chip_policy.py:145-159` | `flat_thresholds` attaches `explain` |
| C2 | `chip_policy.py:186-192` | `thresholds_from_priors` attaches `explain`, naming which of the three fallbacks fired |
| C3 | `chip_policy.py`, after `chip_thresholds_from_asset` | new `threshold_with_source(lookup, chip, gw)` |
| C4 | `chips.py:209-232` | `wildcard_now_assessment(..., thresholds=None)`; θ decides `recommend`; the dict carries `threshold` and `threshold_source` |
| C5 | `advise.py:70-71` | the import gains `threshold_with_source` |
| C6 | `advise.py:895-897` | the chip row records the source beside the bar |
| C7 | `advise.py:900-902` | the wildcard assessment is handed the lookup the run already built |

**C1 — `chip_policy.py:145-159`.**

```python
FLAT_SOURCE = "flat: no calibrated priors asset"
"""Why a bar is the pre-v4c constant. One string, so the caption and the
fallback cannot drift apart."""


def flat_thresholds():
    """The pre-v4c bars, as a ``(chip, gw) -> float`` callable.

    This is the degradation rail for the whole workstream: with no priors
    asset, every caller gets exactly the constants it used before, including
    their indifference to the calendar.
    """
    from gaffer.optimize.chips import (CHIP_PLAY_THRESHOLD,
                                       WILDCARD_RECOMMEND_THRESHOLD)

    def lookup(chip: str, gw: int) -> float:
        return (WILDCARD_RECOMMEND_THRESHOLD if chip == "wildcard"
                else CHIP_PLAY_THRESHOLD)

    # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): a caption
    # cannot say "θ" or "flat fallback" unless the lookup can be asked. An
    # attribute rather than a wrapper type, so every existing caller — which
    # calls this thing — keeps calling it.
    lookup.explain = lambda chip, gw: (lookup(chip, gw), FLAT_SOURCE)
    return lookup
```

**C2 — `chip_policy.py:186-192`**, replacing the returned `lookup`:

```python
    def lookup(chip: str, gw: int) -> float:
        return explain(chip, gw)[0]

    # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): three
    # distinct fallbacks live in this function and every one of them was
    # silent. Named here so the caption can say *why* a bar is flat, which is
    # the half of the spec's sentence a boolean could not carry.
    def explain(chip: str, gw: int) -> tuple[float, str]:
        table = tables.get(chip)
        if not table:
            return (flat(chip, gw),
                    "flat: no calibrated surplus for this chip")
        value = table.get(int(gw))
        if value is None:
            return (flat(chip, gw),
                    "flat: gameweek outside the calibrated window")
        return (float(value), "theta")

    lookup.explain = explain
    return lookup
```

**C3 — `chip_policy.py`, appended after `chip_thresholds_from_asset`.**

```python
UNKNOWN_SOURCE = "unknown"
"""A lookup that predates :func:`threshold_with_source`. Callers print the
bar and say nothing about where it came from, which is honest; inventing
"theta" for it would not be."""


def threshold_with_source(thresholds, chip: str,
                          gw: int) -> tuple[float, str]:
    """``(bar, source)`` for any ``(chip, gw) -> float`` callable.

    ``source`` is ``"theta"`` when the calibrated stopping rule answered, and
    a ``"flat: <reason>"`` string when it did not. A callable with no
    ``explain`` — a test's lambda, a lookup built before v12 — answers
    :data:`UNKNOWN_SOURCE` rather than raising: this is display metadata and
    must never be the reason a chip table fails to render.
    """
    explain = getattr(thresholds, "explain", None)
    if explain is None:
        return (float(thresholds(chip, int(gw))), UNKNOWN_SOURCE)
    bar, source = explain(chip, int(gw))
    return (float(bar), str(source))
```

**C4 — `chips.py:209-232`**, the whole function:

```python
def wildcard_now_assessment(pool: pd.DataFrame, state: SolveInput,
                            base: Plan | None = None,
                            thresholds=None, **cfg) -> dict:
    """The user's 'should I wildcard right now?' number.

    Undecayed like the rest of this module (see the module note), so
    ``gain_over_horizon`` really is expected points over the whole window.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`; pass it to skip re-solving.

    ``thresholds`` is the ``(chip, gw) -> theta`` lookup the caller already
    built (v12 W3 §4.2). Without it the bar is
    :data:`WILDCARD_RECOMMEND_THRESHOLD`, which is what this function used
    unconditionally until v12 — in the same advise run that computed θ for the
    wildcard and printed it on the chip row three lines earlier. Two answers to
    one question, on one page, from one run.

    The comparison is ``>=`` on the θ path and ``>`` on the flat one, and the
    asymmetry is deliberate: ``>=`` is the rule ``chip_plan`` and ``advise``
    already apply to every other chip against θ, and ``>`` is the shipped
    verdict of the flat path, which this cycle has no measurement to move.
    """
    cfg = _eval_cfg(cfg)
    if base is None:
        base = solve_plan(pool, state, **cfg)
    wc = solve_plan(pool, replace(state, wildcard_gw=state.gws[0]), **cfg)
    # No deduction for the banked free transfers. A wildcard does not reset
    # the bank — it has not since 2024-25 — and ``milp`` models that directly
    # (``ftv[t] <= prev_ft + 1`` on a wildcard week), so the lambda value of
    # the bank is already inside ``wc.objective``. Subtracting it again here
    # charged the manager twice for transfers he keeps, and left the two
    # halves of the codebase disagreeing about what a wildcard costs.
    gain = wc.objective - base.objective
    if thresholds is None:
        bar, source = float(WILDCARD_RECOMMEND_THRESHOLD), NO_THRESHOLDS
        recommend = gain > bar
    else:
        bar, source = threshold_with_source(thresholds, "wildcard",
                                            int(state.gws[0]))
        recommend = gain >= bar
    return {"gain_over_horizon": round(gain, 2),
            "wc_squad": wc.gw_plans[0].squad,
            "recommend": recommend,
            "threshold": round(bar, 2),
            "threshold_source": source}
```

with, at the top of `chips.py` beside the existing import:

```python
from gaffer.optimize.chip_policy import threshold_with_source
from gaffer.optimize.milp import (SEASON_LAST_GW, Plan, SolveInput,
                                  solve_plan)

NO_THRESHOLDS = "flat: the caller passed no threshold lookup"
"""Why a bar is flat when the *caller* is the reason. Distinct from
``chip_policy.FLAT_SOURCE``, which is "there is no asset": a caller that never
offered θ and an asset that does not exist are different bugs."""
```

`chips.py` importing `chip_policy` at module level is safe: `chip_policy` imports `chips` only *inside* `flat_thresholds`, so neither import cycle closes at import time. Verified by `python -c "import gaffer.optimize.chips"` in the verify step.

**C5 — `advise.py:70-71`.**

```python
from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                         load_chip_scenarios,
                                         threshold_with_source)
```

**C6 — `advise.py:891-897`**, inside the `for row in chip_rows:` loop:

```python
            # The theta_t bar for that chip in that week: the surplus the best
            # remaining week is expected to offer. Playing is only right when
            # the week on the row beats waiting, which a flat constant cannot
            # say. With no priors asset this is the old flat bar exactly.
            #
            # v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md): and
            # the row now says which of the two it got, so the caption can
            # stop implying θ on a week θ never covered.
            theta, source = threshold_with_source(
                chip_thresholds, str(row["chip"]), int(row["gw"]))
            row["threshold"] = round(theta, 2)
            row["threshold_source"] = source
            row["play_now"] = bool(float(row["gain"]) >= theta)
```

**C7 — `advise.py:900-902`.**

```python
        # "Should I wildcard right now?" is only a question if the wildcard is
        # still available in this half of the season.
        #
        # v12 W3 §4.2: against θ, not against the flat 8.0 this call used
        # while the very same lookup priced the wildcard row above it.
        wc_now = (wildcard_now_assessment(chip_pool, state, base=chip_base,
                                          thresholds=chip_thresholds,
                                          **opt_kw)
                  if "wildcard" in chip_names else None)
```

`tests/test_advise.py:233` indexes on the substring `wildcard_now_assessment(`, which survives; `tests/test_advise.py:435` indexes on `chip_thresholds_from_asset(`, which is untouched. Both are re-run in the verify step.

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_chip_threshold.py`:

```python
"""§4.2: one bar, and it can say where it came from.

The headline test is the spec's own: with a priors asset present, no code path
reads the flat values. It is written as a *sentinel* rather than as a source
grep — both constants are monkeypatched to numbers no calibration could
produce, and any bar that comes back wearing one of them is a flat bar that
should have been θ.

The second half is the caption. A boolean would not do: there are three
distinct reasons a bar can be flat while an asset exists — the chip is not in
the table, the gameweek is outside the calibrated window, the caller passed no
lookup at all — and a UI that printed "flat fallback" for all three would be
telling a user to go and find an asset he already has.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.optimize import chips as chips_mod
from gaffer.optimize.chip_policy import (UNKNOWN_SOURCE, chip_thresholds_from_asset,
                                         flat_thresholds, threshold_with_source,
                                         thresholds_from_priors)
from gaffer.optimize.chips import wildcard_now_assessment
from gaffer.optimize.milp import SolveInput

SENTINEL_WC, SENTINEL_CHIP = 999.0, 998.0

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)


def _priors_covering_everything() -> dict:
    """A calibrated asset with a sample in every week of both chip windows,
    so no lookup has an excuse to fall through."""
    surplus = {str(gw): [3.0, 5.0, 7.0] for gw in range(1, 39)}
    return {"chip_surplus": {chip: dict(surplus)
                             for chip in ("wildcard", "bboost", "3xc",
                                          "freehit")}}


@pytest.fixture()
def sentinels(monkeypatch):
    """Both flat constants replaced by numbers a calibration cannot produce."""
    monkeypatch.setattr(chips_mod, "WILDCARD_RECOMMEND_THRESHOLD",
                        SENTINEL_WC)
    monkeypatch.setattr(chips_mod, "CHIP_PLAY_THRESHOLD", SENTINEL_CHIP)


def test_the_sentinels_reach_the_flat_lookup(sentinels):
    """The instrument first. ``flat_thresholds`` imports the constants inside
    its body, so the monkeypatch is only effective if it is read at call
    time — if this fails, every assertion below is vacuous."""
    flat = flat_thresholds()
    assert flat("wildcard", 7) == SENTINEL_WC
    assert flat("bboost", 7) == SENTINEL_CHIP


def test_with_an_asset_no_bar_is_ever_a_flat_value(sentinels):
    """Spec §4.2's test, over every chip and every gameweek of the season."""
    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    for chip in ("wildcard", "bboost", "3xc", "freehit"):
        for gw in range(1, 39):
            bar, source = threshold_with_source(lookup, chip, gw)
            assert bar not in (SENTINEL_WC, SENTINEL_CHIP)
            assert source == "theta"


def test_a_missing_asset_is_flat_and_says_which_kind_of_flat():
    bar, source = threshold_with_source(chip_thresholds_from_asset(None),
                                        "bboost", 7)
    assert source == "flat: no calibrated priors asset"


def test_a_chip_absent_from_the_asset_names_that_rather_than_the_asset():
    lookup = thresholds_from_priors({"bboost": {10: [4.0]}})
    _, source = threshold_with_source(lookup, "3xc", 10)
    assert source == "flat: no calibrated surplus for this chip"


def test_a_gameweek_outside_the_window_names_that():
    """``stopping_thresholds`` covers ``[first_gw, last_gw]``; a lookup built
    from a table whose windows start later has nothing to say about GW1."""
    lookup = thresholds_from_priors({"bboost": {30: [4.0]}})
    bar, source = threshold_with_source(lookup, "bboost", 1)
    assert source == "flat: gameweek outside the calibrated window"
    assert bar == 4.0 or bar is not None    # the flat bar, whatever it is


def test_a_lookup_with_no_explain_is_unknown_and_never_raises():
    """A test's lambda, or an asset-built lookup from before v12."""
    bar, source = threshold_with_source(lambda chip, gw: 4.5, "bboost", 7)
    assert (bar, source) == (4.5, UNKNOWN_SOURCE)


# --- the wildcard verdict -------------------------------------------------

def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40, "sell": 40,
                         "ep": {1: 1.0 + (code % 7) * 0.5}})
            code += 1
    return pd.DataFrame(rows)


def _state() -> SolveInput:
    return SolveInput(owned_codes=list(range(1, 16)), bank=200,
                      free_transfers=1, gws=[1])


def test_the_wildcard_verdict_reads_theta_when_it_is_handed_one(sentinels):
    """The bug this task exists for: with a priors asset in the run, the
    'Wildcard now' card used the flat 8.0 while the chip row above it used
    θ."""
    lookup = chip_thresholds_from_asset(_priors_covering_everything())
    out = wildcard_now_assessment(_pool(), _state(), thresholds=lookup, **CFG)
    assert out["threshold"] != SENTINEL_WC
    assert out["threshold_source"] == "theta"


def test_the_wildcard_verdict_with_no_lookup_is_the_shipped_one(sentinels):
    """The degradation rail: no lookup, the flat constant, and strictly
    greater — the comparison the function has always used."""
    out = wildcard_now_assessment(_pool(), _state(), **CFG)
    assert out["threshold"] == SENTINEL_WC
    assert out["threshold_source"].startswith("flat:")
    assert out["recommend"] is (out["gain_over_horizon"] > SENTINEL_WC)


def test_a_gain_exactly_on_theta_plays_the_wildcard():
    """``>=`` on the θ path, matching chip_plan and advise for every other
    chip. A wildcard that clears its bar exactly must not read differently
    from a bench boost that clears its bar exactly."""
    out = wildcard_now_assessment(
        _pool(), _state(),
        thresholds=lambda chip, gw: 0.0, **CFG)
    assert out["recommend"] is True
```

Run: `.venv/bin/pytest -q tests/test_v12_w3_chip_threshold.py` — fails on the missing `threshold_with_source` import.

- [ ] **Implement C1-C7** exactly as enumerated (minding the argument-order note on C4).

- [ ] **Implement the schemas.** `schemas.py`:

```python
class ChipWorkbenchRow(BaseModel):
    ...
    threshold: float | None = None
    threshold_source: str | None = None
    """Where ``threshold`` came from: ``"theta"``, or ``"flat: <reason>"``.

    Three distinct fallbacks produce a flat bar and they are not the same
    news — no asset, no surplus for this chip, a gameweek outside the
    calibrated window — so the reason travels with the number rather than
    being guessed at from it. ``None`` on a payload written before v12.
    """
```

```python
class SquadDiff(BaseModel):
    """A candidate squad against the one you own, resolved server-side."""

    gain_over_horizon: float
    recommend: bool
    threshold: float | None = None
    """The bar ``recommend`` was decided against. Until v12 this was always
    the flat 8.0 and was never served, so the card asserted a verdict and
    showed nothing of the rule behind it."""
    threshold_source: str | None = None
    kept: list[SquadPlayerRef]
    dropped: list[SquadPlayerRef]
    added: list[SquadPlayerRef]
```

```python
class ChipPlanRow(BaseModel):
    ...
    threshold_source: str | None = None
    """See ``ChipWorkbenchRow.threshold_source``. Filled at the router from the
    same lookup ``thetas`` is built from."""
```

- [ ] **Implement the two routers.** `routers/chips.py`, in the `ChipWorkbenchRow(...)` construction:

```python
                             threshold_source=(
                                 None if r.get("threshold_source") is None
                                 else str(r["threshold_source"])),
```

and in the `SquadDiff(...)` construction:

```python
            threshold=(None if wc.get("threshold") is None
                       else round(float(wc["threshold"]), 2)),
            threshold_source=(None if wc.get("threshold_source") is None
                              else str(wc["threshold_source"])),
```

`routers/meta.py`, inside the `for row in rows:` loop after `row["thetas"]`:

```python
        # v12 W3 §4.2: the same lookup, asked why rather than only how much.
        row["threshold_source"] = threshold_with_source(
            thresholds, row["chip"], state.gws[0])[1]
```

with `threshold_with_source` added to `meta.py`'s `chip_policy` import.

- [ ] **Implement the caption.** `ChipsTab.tsx` — the "Bar" cell gains the source, and `WildcardTab` gains the sentence:

```tsx
// θ or the pre-v4c constant, in the words the server sent. A bar with no
// source is a payload written before v12 and says nothing rather than
// guessing (v12 W3 §4.2).
function BarSource({ source }: { source?: string | null }) {
  if (!source || source === 'unknown') return null
  return (
    <span className="ml-1 text-text-faint" data-testid="bar-source"
          title={source === 'theta'
            ? 'θ: the surplus the best remaining week is expected to offer '
              + '(v4c stopping rule)'
            : source}>
      {source === 'theta' ? 'θ' : 'flat'}
    </span>
  )
}
```

used in the Bar cell:

```tsx
                  <td className="num py-1.5 text-right text-text-muted">
                    {row.threshold ?? '—'}
                    <BarSource source={row.threshold_source} />
                  </td>
```

and in `WildcardTab`, under the verdict line:

```tsx
      {wildcard.threshold !== null && wildcard.threshold !== undefined && (
        <p className="mt-1 text-text-faint" data-testid="wildcard-bar">
          {`Against a bar of ${wildcard.threshold} `}
          {wildcard.threshold_source === 'theta'
            ? '(θ — the best remaining week’s expected surplus)'
            : `(flat fallback — ${wildcard.threshold_source ?? 'unknown'})`}
        </p>
      )}
```

`types.ts` gains `threshold_source?: string | null` on `ChipWorkbenchRow`, `ChipPlanRow` and `SquadDiff`, plus `threshold?: number | null` on `SquadDiff`.

Add to `ChipsTab.test.tsx`:

```tsx
  it('marks a θ bar as θ and a flat bar as flat', async () => {
    renderChips({ chips: [
      { chip: 'bboost', gw: 4, gain: 5, per_week: 5, threshold: 4.2,
        threshold_source: 'theta', play_now: true, note: null },
      { chip: '3xc', gw: 4, gain: 1, per_week: 1, threshold: 4,
        threshold_source: 'flat: no calibrated priors asset',
        play_now: false, note: null },
    ] })
    const sources = await screen.findAllByTestId('bar-source')
    expect(sources.map((n) => n.textContent)).toEqual(['θ', 'flat'])
  })
```

- [ ] **Verify.**

```bash
.venv/bin/python -c "import gaffer.optimize.chips, gaffer.optimize.chip_policy"
.venv/bin/pytest -q tests/test_v12_w3_chip_threshold.py tests/test_chips.py \
  tests/test_chip_policy.py tests/test_chip_sanity.py tests/test_advise.py \
  tests/test_web_chips.py tests/test_web_meta.py tests/test_v10b_chips_plan.py \
  tests/test_v10b_degradation.py tests/test_calibrate_decisions.py \
  tests/test_backtest.py
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
```

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/chip_policy.py src/gaffer/optimize/chips.py \
  src/gaffer/advise.py src/gaffer/web/schemas.py \
  src/gaffer/web/routers/chips.py src/gaffer/web/routers/meta.py \
  frontend/src/types.ts frontend/src/hubs/planning/ChipsTab.tsx \
  frontend/src/hubs/planning/ChipsTab.test.tsx \
  tests/test_v12_w3_chip_threshold.py && git commit -m "$(cat <<'EOF'
feat: one chip bar, and a caption that says which one it is

advise has built θ since v4c and applied it to every chip row — and then asked
wildcard_now_assessment, which compared the same wildcard against the flat 8.0
it has used since v2. One run, one page, two answers. The assessment now takes
the lookup the run already built.

The caption spec §4.2 asks for needs a source, and a lookup could not report
one: three distinct fallbacks inside thresholds_from_priors all produced a flat
bar silently. Both factories now attach an explain(chip, gw) -> (bar, reason),
read through chip_policy.threshold_with_source, which answers "unknown" rather
than raising for any callable that predates it.

The θ path compares with >= and the flat path keeps >. That is deliberate: >=
is what chip_plan and advise already apply to every other chip against θ, and
the flat path's verdict is shipped behaviour this cycle cannot measure a reason
to move.

v12 W3 §4.2 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edits to chip_policy.py, chips.py and advise.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — **STOP** — the second and third plans: no-good cuts in the MILP

**Files:**
- Modify `src/gaffer/optimize/milp.py` — **PROTECTED**
- Modify `src/gaffer/config.py`, `config.example.toml`
- Create `tests/test_v12_w3_alt_plans.py`

> ### STOP
>
> **Do not start this task.** Report that Task 5 is ready, paste the enumeration, and wait for authorization to edit `src/gaffer/optimize/milp.py`. Task 1 should be merged first: both tasks edit `_solve_once`, and Task 1's golden is the guard this one re-runs.

**Read A4 and A5 before starting.** The gap is an objective gap, and it is signed.

### The complete enumeration

| # | Location | Change |
| --- | --- | --- |
| N1 | `milp.py:173-177` (`Plan`) | `gap` and `alternatives`, both defaulted |
| N2 | `milp.py`, after `Plan` | `ALT_PLAN_MAX`, `move_set()` |
| N3 | `milp.py:369-376`, `:434-445` | `no_good=None` on `solve_plan` and `_solve_once`, threaded through `kw` |
| N4 | `milp.py`, after the `fixed_moves` block (`:596`) | the cuts themselves |
| N5 | `milp.py`, after `solve_plan` | `alternative_plans()` |

**N1 — `milp.py:173-177`.**

```python
@dataclass
class Plan:
    objective: float
    gw_plans: list[GwPlan]
    # v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md). Both
    # defaulted, so every construction in the tree — and every ``Plan`` a
    # scenario sweep builds — is the object it was.
    gap: float | None = None
    """Objective points this plan sits behind the one it is an alternative to.

    **Signed, and the sign matters.** The recommended plan is
    ``policy.coherent_plan``'s, which carries the sweep's moves as
    ``FixedMoves``; an alternative is solved without them and can therefore
    score *above* it, giving a negative gap. That is the price of the
    coherence constraint, and it is the number a reader deciding whether to
    override the sweep wants to see.

    An **objective** gap, not an EP one: ``objective`` is decayed by week,
    carries the bench curve and the vice hedge, and prices banked transfers
    and the bank itself. Re-scoring the alternatives in raw EP would compare
    two plans on a quantity neither was chosen by. ``None`` on any plan that
    is not somebody's alternative.
    """
    alternatives: list["Plan"] = field(default_factory=list)
    """Distinct plans behind this one, best first. Each carries its own
    ``gap``; this list is always empty on them (one level, not a tree)."""
```

**N2 — `milp.py`, after `Plan`.**

```python
ALT_PLAN_MAX = 3
"""Plans in the set, counting the incumbent (spec §4.3's "top-3").

A constant rather than a config key because the cost is a solve each and the
knob the spec exposes is the gap, which is the one that answers "is this
alternative worth reading". Three is also as many tabs as a board column can
carry without becoming a menu.
"""


def move_set(plan: "Plan") -> list[tuple[str, int, int]]:
    """The transfers a plan makes, as ``(direction, code, gameweek)``.

    Sorted, so a cut built from it is stable across runs and two identical
    plans produce identical cuts. Buys and sells are listed separately rather
    than paired: the MILP never pairs them — a week's ``buys`` and ``sells``
    are two lists whose only relationship is the budget row — so pairing them
    here would be inventing a structure to exclude.
    """
    return sorted(
        [("in", int(c), int(gp.gw)) for gp in plan.gw_plans for c in gp.buys]
        + [("out", int(c), int(gp.gw)) for gp in plan.gw_plans
           for c in gp.sells])
```

**N3 — the two signatures.** `solve_plan` gains `no_good: list[list[tuple[str, int, int]]] | None = None` as its last keyword and puts it in the `kw` bundle it already builds (`:412-416`), so both passes of §F1a carry the same cuts:

```python
    kw = dict(decay=decay, bench_weight=bench_weight,
              vice_weight=vice_weight, ft_value=ft_value,
              itb_value=itb_value, hit_cost=hit_cost,
              fixed_moves=fixed_moves, ft_lambda=ft_lambda,
              ft_use_penalty=ft_use_penalty, bench_curve=bench_curve,
              # v12 W3 §4.3: in ``kw`` and not passed separately, so the
              # re-weighted second pass excludes the same plans the first did.
              # A cut that lived only in pass one would let pass two hand back
              # the incumbent as its own alternative.
              no_good=no_good)
```

`_solve_once` gains the same parameter with the same default.

**N4 — `milp.py`, immediately after the `fixed_moves` block.**

```python
    # --- no-good cuts (v12 W3 §4.3) --------------------------------------
    # (specs/2026-09-01-gaffer-v12-program-design.md). Each cut is a plan's
    # complete move set; the constraint forbids making *all* of them at once,
    # which is the standard no-good cut over binaries that are all 1 in the
    # solution being excluded. A plan making those moves and one more is
    # excluded too, deliberately: it is not a distinct decision, it is the
    # same one with a passenger.
    #
    # The empty cut is the hold plan, and it is a real case rather than a
    # corner: ``sum(nothing) <= -1`` is infeasible, so "differ from a plan
    # that made no transfers" has to be spelled as "make at least one".
    for cut in (no_good or []):
        terms = []
        for kind, c, t in cut:
            if c not in known or t not in T:
                raise GafferError(
                    f"no_good: ({kind}, {c}, gw{t}) is not expressible on "
                    f"this board — the cut was built from a different pool "
                    f"or a different horizon")
            terms.append(tin[c][t] if kind == "in" else tout[c][t])
        if terms:
            prob += pulp.lpSum(terms) <= len(terms) - 1
        else:
            prob += pulp.lpSum(tin[c][t] for c in codes for t in T) >= 1
```

**N5 — `milp.py`, after `solve_plan`.**

```python
def alternative_plans(pool: pd.DataFrame, state: SolveInput,
                      incumbent: Plan, *, max_gap: float,
                      max_plans: int = ALT_PLAN_MAX,
                      **solve_cfg) -> list[Plan]:
    """Up to ``max_plans - 1`` distinct plans behind ``incumbent``, best first.

    Each is the best plan that does not make some move of every plan already
    found — one no-good cut per plan, accumulated — and each carries its
    ``gap`` against the incumbent's objective. The search stops at
    ``max_plans``, at a gap wider than ``max_gap``, or when the cuts leave
    nothing legal to find.

    ``max_gap <= 0`` returns immediately **without solving**, which is the off
    switch: a knob that still spent two MILPs to discard their answers would
    be a preference rather than a switch.

    ``solve_cfg`` is the caller's ordinary ``solve_plan`` bundle and must
    **not** carry ``fixed_moves``. An alternative constrained to make the
    incumbent's moves is not an alternative — which is also why a gap can come
    back negative when the incumbent itself was solved under a coherence
    constraint (plan A5).

    A failed solve ends the search rather than raising: two plans are a
    better answer than none, and the caller is an advice run under a deadline.
    """
    if max_gap <= 0 or max_plans <= 1:
        return []
    cuts = [move_set(incumbent)]
    out: list[Plan] = []
    while len(out) < max_plans - 1:
        try:
            alt = solve_plan(pool, state, **solve_cfg, no_good=list(cuts))
        except Exception as exc:  # noqa: BLE001 — see docstring
            print(f"optimize: no further distinct plan ({exc})")
            break
        alt.gap = round(incumbent.objective - alt.objective, 3)
        if alt.gap > max_gap:
            break
        out.append(alt)
        cuts.append(move_set(alt))
    return out
```

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_alt_plans.py`:

```python
"""§4.3: the second- and third-best plans, and what "distinct" means.

A no-good cut over a plan's move set forbids making all of those moves at
once. Three properties follow and all three are asserted here: an alternative
differs from the incumbent in at least one move; a plan that makes the
incumbent's moves *and another* is also excluded (it is the same decision with
a passenger); and the hold plan — whose move set is empty — is excluded by
"make at least one transfer", because a cut over nothing is infeasible rather
than trivially satisfied.

The gap is an objective gap and is signed. Both are pinned: an EP re-score
would compare plans on a quantity neither was chosen by, and clamping the sign
would hide the case where the incumbent's own coherence constraint cost it the
optimum.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.errors import GafferError
from gaffer.optimize.milp import (ALT_PLAN_MAX, FixedMoves, SolveInput,
                                  alternative_plans, move_set, solve_plan)

GWS = [1, 2]
KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
          itb_value=0.05, hit_cost=4)


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40 + i, "sell": 40 + i,
                         "ep": {1: 1.0 + (code % 7) * 0.3,
                                2: 2.0 + (code % 5) * 0.2}})
            code += 1
    return pd.DataFrame(rows)


OWNED = [1, 2, 5, 6, 7, 8, 9, 14, 15, 16, 17, 18, 22, 23, 24]


def _state(**kw) -> SolveInput:
    base = dict(owned_codes=list(OWNED), bank=100, free_transfers=2, gws=GWS)
    return SolveInput(**{**base, **kw})


def test_a_plan_carries_no_gap_and_no_alternatives_by_default():
    """The degradation direction: every Plan in the tree is the object it
    was, including the tens of thousands a scenario sweep builds."""
    plan = solve_plan(_pool(), _state(), **KW)
    assert plan.gap is None
    assert plan.alternatives == []


def test_move_set_is_sorted_and_names_both_directions():
    plan = solve_plan(_pool(), _state(), **KW)
    moves = move_set(plan)
    assert moves == sorted(moves)
    assert all(kind in ("in", "out") for kind, _, _ in moves)


def test_the_cut_excludes_the_incumbents_exact_move_set():
    pool, state = _pool(), _state()
    first = solve_plan(pool, state, **KW)
    second = solve_plan(pool, state, **KW, no_good=[move_set(first)])
    assert move_set(second) != move_set(first)


def test_the_cut_also_excludes_a_superset_of_the_incumbents_moves():
    """"The same decision with a passenger" is not a distinct plan. A
    solution containing every cut move is excluded whatever else it does."""
    pool, state = _pool(), _state()
    first = solve_plan(pool, state, **KW)
    cut = move_set(first)
    second = solve_plan(pool, state, **KW, no_good=[cut])
    assert not set(cut).issubset(set(move_set(second)))


def test_a_cut_over_a_hold_plan_forces_at_least_one_transfer():
    """The empty move set. ``sum(nothing) <= -1`` is infeasible, so the cut
    is spelled the other way round."""
    pool, state = _pool(), _state(free_transfers=0)
    held = solve_plan(pool, state, **KW, fixed_moves=FixedMoves(
        no_transfer=True))
    assert move_set(held) == []
    moved = solve_plan(pool, state, **KW, no_good=[move_set(held)])
    assert move_set(moved) != []


def test_a_cut_naming_a_player_outside_the_pool_is_refused_by_name():
    with pytest.raises(GafferError, match="not expressible on this board"):
        solve_plan(_pool(), _state(), **KW, no_good=[[("in", 9999, 1)]])


def test_a_cut_naming_a_gameweek_outside_the_horizon_is_refused():
    with pytest.raises(GafferError, match="not expressible on this board"):
        solve_plan(_pool(), _state(), **KW, no_good=[[("in", 3, 9)]])


# --- alternative_plans ----------------------------------------------------

def test_it_returns_two_alternatives_at_a_generous_gap():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    alts = alternative_plans(pool, state, plan, max_gap=1e6, **KW)
    assert len(alts) == ALT_PLAN_MAX - 1


def test_every_alternative_is_distinct_from_the_incumbent_and_each_other():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    alts = alternative_plans(pool, state, plan, max_gap=1e6, **KW)
    sets = [tuple(move_set(p)) for p in [plan] + alts]
    assert len(set(sets)) == len(sets)


def test_the_gap_is_the_objective_difference_and_is_ordered():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    alts = alternative_plans(pool, state, plan, max_gap=1e6, **KW)
    for alt in alts:
        assert alt.gap == pytest.approx(plan.objective - alt.objective,
                                        abs=1e-3)
    assert alts[0].gap <= alts[1].gap


def test_a_tight_gap_stops_the_search_early():
    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    assert alternative_plans(pool, state, plan, max_gap=1e-6, **KW) == []


def test_a_gap_of_zero_solves_nothing_at_all(monkeypatch):
    """The off switch has to be free. A knob that spent two MILPs and threw
    the answers away would be a preference, not a switch."""
    import gaffer.optimize.milp as milp_mod

    pool, state = _pool(), _state()
    plan = solve_plan(pool, state, **KW)
    monkeypatch.setattr(milp_mod, "_solve_once",
                        lambda *a, **k: pytest.fail("must not solve"))
    assert alternative_plans(pool, state, plan, max_gap=0.0, **KW) == []


def test_the_gap_can_be_negative_when_the_incumbent_was_constrained():
    """Plan A is ``coherent_plan``'s — the best plan *containing the sweep's
    moves*. An alternative solved without that constraint can beat it, and the
    sign is the only thing that says so."""
    pool, state = _pool(), _state()
    # A deliberately poor forced move, standing in for a sweep that voted for
    # something the raw optimum did not want.
    constrained = solve_plan(pool, state, **KW,
                             fixed_moves=FixedMoves(buys=[4], sells=[1]))
    alts = alternative_plans(pool, state, constrained, max_gap=1e6, **KW)
    assert any(alt.gap < 0 for alt in alts)


def test_the_lp_golden_still_matches_with_no_cuts(tmp_path):
    """Task 1's guard, re-run: ``no_good=None`` must add nothing to the
    model."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state as st

    assert _capture_lp(tmp_path, st())[0] == GOLDEN.read_text()
```

Run: `.venv/bin/pytest -q tests/test_v12_w3_alt_plans.py` — fails on the missing import.

- [ ] **Implement N1-N5** exactly as enumerated.

- [ ] **Implement the config key.** `config.py`, appended to the `[optimizer]` block of `Config` (beside `hit_cost`, before the v4c section):

```python
    # v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md). How far
    # behind the recommended plan an alternative may sit and still be worth
    # showing, in *objective* points — the frame the plans were solved in, not
    # raw EP. 0 turns the search off without spending a solve.
    #
    # An [optimizer] key, not a [solver] one: the spec names a section this
    # tree does not have, and the program-wide ruling is that solver knobs live
    # in [optimizer] under their own names.
    alt_plan_max_gap: float = 2.0
```

**No line in `load_config`.** `[optimizer]` is splatted (`**raw.get("optimizer", {})`, `config.py:146`), so a field on the dataclass with a default *is* the whole wiring — the same way `ft_use_penalty` and `bench_curve` need none. Adding an explicit read would give the key two defaults that can drift.

`config.example.toml`, appended to the existing `[optimizer]` section after `hit_cost`:

```toml
# How far behind the recommended plan an alternative may sit and still be
# shown as Plan B or Plan C, in the solver's own objective points — which
# discount later weeks and price banked transfers, so this is not a raw xPts
# gap. 0 turns the search off; each alternative costs one more MILP solve.
alt_plan_max_gap = 2.0
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_alt_plans.py tests/test_v12_w3_force_out.py \
  tests/test_milp.py tests/test_v10_milp_p_play.py tests/test_scenarios.py \
  tests/test_config.py tests/test_v4c_degradation.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/milp.py src/gaffer/config.py config.example.toml \
  tests/test_v12_w3_alt_plans.py && git commit -m "$(cat <<'EOF'
feat: the plans the solver ranked second and third

A no-good cut per plan found, accumulated: each alternative is the best plan
that does not make every move of any plan already in the set. A superset is
excluded with it, because the same decision carrying a passenger is not a
second opinion — and the hold plan, whose move set is empty, is excluded by
"make at least one transfer", since a cut over nothing is infeasible rather
than trivially true.

The gap is an objective gap and it is signed. Objective, because that is the
frame both plans were chosen in — re-scoring in raw EP would rank them on a
number neither was selected by. Signed, because the recommended plan carries
the sweep's moves as FixedMoves and an alternative does not, so an alternative
can be ahead: that is the price of coherence, and it has never been visible.

[optimizer] alt_plan_max_gap = 2.0, and 0 returns before spending a solve. The
spec called for a [solver] section; this tree has none and the knob belongs
beside the rest of the objective's dials, where [optimizer]'s splat wires it
with no second default to drift.

v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edit to optimize/milp.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — **STOP** — the alternatives reach the artifact and the plan endpoint

**Files:**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/routers/plan.py`
- Create `tests/test_v12_w3_plan_alternatives.py`

> ### STOP
>
> **Do not start this task.** Report that Task 6 is ready, paste the enumeration, and wait for authorization to edit `src/gaffer/advise.py`. Task 5 must be merged first.

**Read A11 before starting.** No route is added: the alternatives ride as a new key on the advice artifact and a new field on `PlanTimeline`, and `plan_by_gw` itself does not change shape — v11's bank arithmetic reads it and must be undisturbed.

### The complete enumeration — `advise.py`, four line-groups

| # | Location (at `27f7933`) | Change |
| --- | --- | --- |
| P1 | `advise.py:73` | the `milp` import gains `alternative_plans` |
| P2 | `advise.py:147-148` | `Advice.alternative_plans`, appended last and defaulted |
| P3 | `advise.py:919-923` | the search, placed after `name_of`/`pos_of` exist and before the payload is built |
| P4 | `advise.py:980` | the field is passed |

**P1 — `advise.py:73`.**

```python
from gaffer.optimize.milp import (SolveInput, alternative_plans, build_pool,
                                  solve_plan)
```

**P2 — `advise.py`, appended to `Advice` after `demoted_captain`.**

```python
    # --- v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md) --------
    # Up to two more distinct plans, each ``{"gap": float, "plan_by_gw": [...]}``
    # with weeks in ``plan_by_gw``'s own shape. Appended last and defaulted, so
    # every payload written before this — and every positional construction —
    # still loads.
    alternative_plans: list[dict] = field(default_factory=list)
```

**P3 — `advise.py`, immediately after the `buys`/`sells` naming block (`:923-924`) and before `for b in buys:`.**

```python
    # v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md): the plans
    # the solver ranked second and third, each excluded from repeating any
    # earlier plan's move set. Here rather than beside the solve because
    # ``name_of``/``pos_of`` are what turn codes into rows, and they are built
    # above.
    #
    # ``plan`` at this point is the plan the user is shown — ``coherent_plan``'s
    # when a sweep ran, the raw solve otherwise. The alternatives are solved
    # *without* the sweep's ``FixedMoves``, so one of them can price above the
    # recommendation and the gap comes back negative; that is the cost of
    # coherence, made visible (plan A5).
    #
    # The cost is two more MILP solves on a weekly run. ``alt_plan_max_gap = 0``
    # returns before spending either, and the initial-squad mode is skipped
    # outright: fifteen opening buys have no second-best worth tabbing through.
    alt_rows: list[dict] = []
    if cfg.alt_plan_max_gap > 0 and state.owned_codes:
        for alt in alternative_plans(pool, state, plan,
                                     max_gap=cfg.alt_plan_max_gap,
                                     **solve_kw, p_play=p_play_by_code):
            alt_rows.append({
                "gap": None if alt.gap is None else round(float(alt.gap), 2),
                "plan_by_gw": [
                    {"gw": p.gw, "hits": p.hits,
                     "buys": _named(p.buys, name_of, pos_of, ep_by, p.gw),
                     "sells": _named(p.sells, name_of, pos_of, ep_by, p.gw),
                     "expected_pts": round(raw_xi_pts(p, ep_by), 2)}
                    for p in alt.gw_plans]})
```

**P4 — `advise.py:980`**, in the `Advice(...)` construction after `demoted_captain=demoted_captain,`:

```python
        alternative_plans=alt_rows,
```

`p_play=p_play_by_code` appears twice in `advise.py` today and `tests/test_v10_degradation.py:549` counts exactly that. **P3 makes it three.** The call above spells it `p_play=p_play_by_code)` inside a multi-line call, so the substring *does* match and the protected count assertion **will fail**.

> **This is a second protected-test consequence and it is handled without editing the rail.** Write P3's call as
>
> ```python
>         for alt in alternative_plans(pool, state, plan,
>                                      max_gap=cfg.alt_plan_max_gap,
>                                      **solve_kw, **weighted):
> ```
>
> with, one line above the `if`:
>
> ```python
>     # Spelled through a bundle rather than inline: v10's T10-A rail counts
>     # the two solves that carry the minutes weights (the coherent plan, and
>     # the raw solve of the modes with no sweep), and this is a third consumer
>     # that is neither of them. The rail's claim is about *which solves are
>     # recommended*, and an alternative to a recommendation is not one of them.
>     weighted = {"p_play": p_play_by_code}
> ```
>
> Run `grep -c "p_play=p_play_by_code" src/gaffer/advise.py` after implementing: it must still print `2`. If it prints `3`, the bundle was not used — **stop and report**; do not edit `tests/test_v10_degradation.py` for this, which is a naming problem rather than a claim that moved.

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_plan_alternatives.py`:

```python
"""§4.3 on the wire: the alternatives ride the artifact and the plan endpoint.

No route is added and ``plan_by_gw`` does not change shape — v11's bank
trajectory reads it week by week and would blank permanently on a key it could
not parse. So the alternatives are a sibling key carrying weeks in the same
shape, and the router builds them through the same loop, which is what keeps
"Plan B's bank" and "Plan A's bank" the same arithmetic rather than two.

Every degradation the timeline already survives, an alternative survives too:
a missing key, a key that is not a list, a week that is not a dict, a gap that
is not a number. A malformed alternative costs the reader a tab, never the
board.
"""

from __future__ import annotations

import pytest

from gaffer.web.routers import plan as plan_router


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "expected_pts": 60.0,
            "buys": [dict(b) for b in buys], "sells": [dict(s) for s in sells]}


def _advice(weeks, alternatives=None):
    out = {"gw": 5, "deadline": "2026-09-18T17:30:00Z", "chip_table": [],
           "captain": None, "vice": None, "plan_by_gw": weeks}
    if alternatives is not None:
        out["alternative_plans"] = alternatives
    return out


@pytest.fixture()
def wired(monkeypatch):
    import pandas as pd

    from gaffer.artifacts import SolveState

    pool = pd.DataFrame({"code": [100, 200, 300],
                         "name": ["In", "Out", "Other"],
                         "cost": [80.0, 75.0, 60.0],
                         "sell": [78.0, 74.0, 59.0]})

    def install(advice, bank=15):
        monkeypatch.setattr(plan_router, "load_advice", lambda gw: advice)
        state = SolveState(pool=pool, bank=bank, opt={"hit_cost": 4},
                           generated_at="2026-09-01T09:00:00+00:00",
                           owned_codes=[200], gws=[5, 6, 7], gw=5,
                           deadline="", mode="weekly", free_transfers=1,
                           lam=0.0, league_eo={}, avail_by_gw={})
        monkeypatch.setattr(plan_router, "load_solve_state", lambda gw: state)
    return install


def test_an_artifact_with_no_alternatives_serves_an_empty_list(wired):
    """Every payload on disk today. The board draws one tab and no strip."""
    wired(_advice([_week(5)]))
    assert plan_router.plan(5).alternatives == []


def test_each_alternative_is_labelled_and_carries_its_gap(wired):
    wired(_advice([_week(5)], [
        {"gap": 0.4, "plan_by_gw": [_week(5, buys=[{"code": 100,
                                                    "name": "In"}])]},
        {"gap": 1.8, "plan_by_gw": [_week(5)]}]))
    alts = plan_router.plan(5).alternatives
    assert [a.label for a in alts] == ["Plan B", "Plan C"]
    assert [a.gap for a in alts] == [0.4, 1.8]


def test_an_alternatives_weeks_are_priced_by_the_same_loop(wired):
    """The board prints Plan B's bank beside Plan A's; two implementations of
    the running total would disagree within a week."""
    wired(_advice([_week(5)], [
        {"gap": 0.4, "plan_by_gw": [
            _week(5, buys=[{"code": 100, "name": "In"}],
                  sells=[{"code": 200, "name": "Out"}])]}]))
    week = plan_router.plan(5).alternatives[0].weeks[0]
    assert week.buys[0].price == 8.0
    assert week.bank == pytest.approx(0.9)      # 1.5 + 7.4 - 8.0


def test_an_unpriced_move_blanks_an_alternatives_bank_too(wired):
    wired(_advice([_week(5)], [
        {"gap": 0.4, "plan_by_gw": [
            _week(5, buys=[{"code": 999, "name": "Ghost"}]), _week(6)]}]))
    banks = [w.bank for w in plan_router.plan(5).alternatives[0].weeks]
    assert banks == [None, None]


def test_an_alternative_carries_no_captain_even_on_the_head_week(wired):
    """The armband belongs to the plan that was recommended. Printing the
    recommendation's captain on an alternative that never chose him would be
    the board's most confident lie."""
    wired(_advice([_week(5)], [{"gap": 0.4, "plan_by_gw": [_week(5)]}]))
    out = plan_router.plan(5)
    assert out.alternatives[0].weeks[0].captain is None


def test_a_negative_gap_survives_to_the_wire(wired):
    """Plan A is the coherent plan; an alternative can be ahead of it."""
    wired(_advice([_week(5)], [{"gap": -1.2, "plan_by_gw": [_week(5)]}]))
    assert plan_router.plan(5).alternatives[0].gap == -1.2


def test_a_gap_that_is_not_a_number_is_None_and_not_zero(wired):
    """0.0 is "exactly level", which is a real and different claim."""
    wired(_advice([_week(5)], [{"gap": "eh", "plan_by_gw": [_week(5)]}]))
    assert plan_router.plan(5).alternatives[0].gap is None


@pytest.mark.parametrize("payload", ["nonsense", {"a": 1}, 7, None])
def test_a_malformed_alternatives_key_costs_a_tab_and_not_the_board(wired,
                                                                    payload):
    wired(_advice([_week(5)], payload))
    out = plan_router.plan(5)
    assert out.alternatives == []
    assert len(out.weeks) == 1


def test_an_alternative_that_is_not_a_dict_is_dropped_and_the_rest_stand(
        wired):
    wired(_advice([_week(5)], ["nonsense",
                               {"gap": 1.0, "plan_by_gw": [_week(5)]}]))
    alts = plan_router.plan(5).alternatives
    assert [a.label for a in alts] == ["Plan B"]
```

- [ ] **Implement the schema.** `schemas.py`, above `PlanTimeline`:

```python
class PlanAlternative(BaseModel):
    """A plan the solver ranked behind the recommended one (v12 W3 §4.3)."""

    label: str
    """``"Plan B"`` / ``"Plan C"``, assigned by position at the router. The
    artifact stores the order and not the name, so a payload written by one
    build reads correctly on another."""
    gap: float | None = None
    """Objective points behind the recommended plan — **signed**.

    Negative means this plan prices *above* the recommendation, which happens
    because the recommendation carries the scenario sweep's moves as
    constraints and this one does not. ``None`` when the artifact's number
    could not be read; never 0.0, which is "exactly level".
    """
    weeks: list[PlanGw]
```

and `PlanTimeline` gains:

```python
    alternatives: list[PlanAlternative] = []
    """Empty on every artifact written before v12, and on any run with
    ``[optimizer] alt_plan_max_gap = 0``. The board draws no tab strip for an
    empty list rather than a strip with one tab in it."""
```

- [ ] **Implement the router.** `routers/plan.py`: the week loop inside `plan()` becomes a nested function so both callers share it verbatim.

```python
    def build(entries: list[dict], *, head_refs: bool) -> list[PlanGw]:
        """``plan_by_gw`` entries -> priced weeks with a running bank.

        v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md): shared by
        the recommended plan and by every alternative, because the board prints
        their banks side by side and two implementations of one running total
        disagree within a week. ``head_refs`` is False for an alternative: the
        armband belongs to the plan that was recommended, and lending it to a
        plan that never chose it is the most confident thing this payload could
        get wrong.
        """
        running = start
        out: list[PlanGw] = []
        for entry in entries:
            week_gw = _int(entry.get("gw"), 0)
            is_head = head_refs and week_gw == head
            hits = _int(entry.get("hits"))
            buys, buys_whole = _moves(entry.get("buys"), buy_price)
            sells, sells_whole = _moves(entry.get("sells"), sell_price)
            if running is not None and buys_whole and sells_whole and all(
                    m.price is not None for m in buys + sells):
                running = round(running
                                + sum(m.price for m in sells)
                                - sum(m.price for m in buys), 1)
            else:
                running = None
            out.append(PlanGw(
                gw=week_gw, buys=buys, sells=sells, hits=hits,
                hit_cost=hits * hit_cost, chip=chips.get(week_gw),
                captain=(_move(advice.get("captain"), buy_price)
                         if is_head else None),
                vice=(_move(advice.get("vice"), buy_price)
                      if is_head else None),
                expected_pts=round(_float(entry.get("expected_pts")), 2),
                bank=running))
        return out

    weeks = build(_weeks_of(advice), head_refs=True)
    return PlanTimeline(gw=head, generated_at=state.generated_at, weeks=weeks,
                        bank=start, alternatives=_alternatives(advice, build))
```

The v11 comment block above `start = _price(...)` stays where it is, unchanged.

```python
LABELS = ("Plan B", "Plan C", "Plan D", "Plan E")
"""Names for the alternatives, by position. Longer than ``ALT_PLAN_MAX``
needs, so an artifact written by a build with a larger set does not fall off
the end of the list and lose its last tab."""


def _gap(value) -> float | None:
    """The signed objective gap, or ``None`` if it is not a number.

    Never 0.0 for unreadable: zero is "exactly level with the recommendation",
    which is a real and different claim — and, on a signed quantity, the
    boundary between "behind" and "ahead".
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else round(out, 2)       # NaN


def _alternatives(advice: dict, build) -> list[PlanAlternative]:
    """``alternative_plans`` off the artifact, however it was written.

    Absent on every payload before v12 and on any run with the search off, so
    the empty list is the main case rather than the degraded one. An entry
    that is not a dict, or whose weeks are not a list, is dropped and the rest
    are drawn: a malformed alternative costs the reader a tab, not the board.
    """
    raw = advice.get("alternative_plans")
    if not isinstance(raw, list):
        return []
    out: list[PlanAlternative] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        weeks = entry.get("plan_by_gw")
        if isinstance(weeks, dict):
            weeks = list(weeks.values())
        if not isinstance(weeks, list):
            continue
        entries = [w for w in weeks
                   if isinstance(w, dict) and w.get("gw") is not None]
        if len(out) >= len(LABELS):
            break
        out.append(PlanAlternative(label=LABELS[len(out)],
                                   gap=_gap(entry.get("gap")),
                                   weeks=build(entries, head_refs=False)))
    return out
```

with `PlanAlternative` added to the module's `schemas` import.

- [ ] **Implement P1-P4** in `advise.py`, using the `weighted` bundle spelled out in the enumeration.

- [ ] **Verify.**

```bash
grep -c "p_play=p_play_by_code" src/gaffer/advise.py     # must print 2
.venv/bin/pytest -q tests/test_v12_w3_plan_alternatives.py tests/test_web_plan.py \
  tests/test_v11_degradation.py tests/test_advise.py tests/test_v10_degradation.py \
  tests/test_v4c_degradation.py
.venv/bin/pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/advise.py src/gaffer/web/schemas.py \
  src/gaffer/web/routers/plan.py tests/test_v12_w3_plan_alternatives.py \
  && git commit -m "$(cat <<'EOF'
feat: Plan B and Plan C reach the timeline

The advice run banks up to two more distinct plans beside the one it
recommends, and /api/plan serves them — no new route, and plan_by_gw keeps its
shape, because v11's bank trajectory reads it week by week and blanks
permanently on anything it cannot parse.

The router builds an alternative's weeks through the *same* loop as the
recommendation's, so their banks are one arithmetic rather than two, and an
alternative carries no captain: the armband belongs to the plan that was
recommended, and lending it to a plan that never chose him is the most
confident thing this payload could get wrong.

The gap is signed on the wire and None — never 0.0 — when it cannot be read,
because zero is "exactly level" and, on a signed quantity, the boundary between
behind and ahead.

v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edit to advise.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — Plan A / B / C on the board

**Files:**
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/planning/PlannerBoard.tsx`
- Modify `frontend/src/hubs/planning/PlannerBoard.test.tsx`

No protected file. Depends on Task 6.

- [ ] **Write the failing tests.** Append to `PlannerBoard.test.tsx`:

```tsx
  it('draws no tab strip when the run banked no alternatives', async () => {
    renderBoard({})            // the file's fixture serves alternatives: []
    await screen.findByTestId('board-week-5')
    expect(screen.queryByTestId('plan-tabs')).toBeNull()
  })

  it('switches to Plan B and draws its weeks', async () => {
    renderBoard({ alternatives: [
      { label: 'Plan B', gap: 0.4, weeks: [
        { gw: 5, buys: [{ code: 300, name: 'Other', position: 'MID',
                          ep: 5.1, price: 6.0 }],
          sells: [], hits: 0, hit_cost: 0, chip: null, captain: null,
          vice: null, expected_pts: 58.2, bank: 0.5 }] },
    ] })
    await userEvent.click(await screen.findByRole('button',
                                                 { name: /Plan B/ }))
    expect(await screen.findByTestId('board-in-300')).toBeInTheDocument()
  })

  it('says an alternative is behind, and by how much, in the right frame',
    async () => {
      renderBoard({ alternatives: [
        { label: 'Plan B', gap: 0.4, weeks: [] }] })
      await userEvent.click(await screen.findByRole('button',
                                                    { name: /Plan B/ }))
      const note = await screen.findByTestId('plan-gap')
      expect(note.textContent).toMatch(/0\.4 objective points behind/)
    })

  it('says AHEAD when the gap is negative, rather than showing a minus sign',
    async () => {
      renderBoard({ alternatives: [
        { label: 'Plan B', gap: -1.2, weeks: [] }] })
      await userEvent.click(await screen.findByRole('button',
                                                    { name: /Plan B/ }))
      expect((await screen.findByTestId('plan-gap')).textContent)
        .toMatch(/1\.2 objective points AHEAD/)
    })

  it('highlights the moves that differ from Plan A', async () => {
    renderBoard({ alternatives: [
      { label: 'Plan B', gap: 0.4, weeks: [
        { gw: 5, buys: [{ code: 300, name: 'Other', position: 'MID',
                          ep: 5.1, price: 6.0 }],
          sells: [{ code: 200, name: 'Out', position: 'DEF',
                    ep: 3.0, price: 7.4 }],
          hits: 0, hit_cost: 0, chip: null, captain: null, vice: null,
          expected_pts: 58.2, bank: 0.5 }] }] })
    await userEvent.click(await screen.findByRole('button',
                                                  { name: /Plan B/ }))
    // 300 is not in Plan A's week; 200 is (the fixture's sell).
    expect(screen.getByTestId('board-in-300').dataset.differs).toBe('true')
    expect(screen.getByTestId('board-out-200').dataset.differs).toBe('false')
  })

  it('offers no handoff from an alternative', async () => {
    renderBoard({ onTry: vi.fn(), alternatives: [
      { label: 'Plan B', gap: 0.4, weeks: [
        { gw: 5, buys: [], sells: [], hits: 0, hit_cost: 0, chip: null,
          captain: null, vice: null, expected_pts: 58.2, bank: 0.5 }] }] })
    await userEvent.click(await screen.findByRole('button',
                                                  { name: /Plan B/ }))
    expect(screen.queryByTestId('board-try-5')).toBeNull()
  })
```

`renderBoard`'s existing helper needs `alternatives` threading through the mocked `/api/plan/{gw}` body; extend it rather than adding a second helper.

Run: `cd frontend && npx vitest run src/hubs/planning/PlannerBoard.test.tsx` — fails.

- [ ] **Implement `types.ts`.** `PlanAlternative` mirroring the schema, and `PlanTimeline.alternatives: PlanAlternative[]`.

- [ ] **Implement `PlannerBoard.tsx`.** Four changes, and the fourth is the one that matters:

```tsx
  // Which plan the strip is on. Plan A is the recommendation and is index 0;
  // an alternative is 1-based into `data.alternatives`. Not persisted, for
  // ThisWeek.tsx:31-34's standing reason: a view preference is a real feature
  // with real questions behind it, and inventing an answer inside a lean cycle
  // is how a preference store gets built by accident.
  const [pick, setPick] = useState(0)
```

The strip, drawn only when there is something to switch to:

```tsx
      {data.alternatives.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1" data-testid="plan-tabs">
          {['Plan A', ...data.alternatives.map((a) => a.label)].map(
            (label, i) => (
              <button
                key={label}
                type="button"
                aria-pressed={pick === i}
                onClick={() => setPick(i)}
                className={`rounded-card border px-3 py-1.5 ${pick === i
                  ? 'border-text text-text' : 'border-border text-text-muted'}`}
              >
                {label}
              </button>
            ))}
        </div>
      )}
```

The gap sentence, which branches on the sign:

```tsx
      {shown !== null && (
        <p className="mb-2 text-text-muted" data-testid="plan-gap">
          {shown.gap === null
            ? 'This plan’s distance from Plan A could not be read.'
            : shown.gap >= 0
              ? `${fmtNum(shown.gap)} objective points behind Plan A.`
              : `${fmtNum(Math.abs(shown.gap))} objective points AHEAD of `
                + 'Plan A — the recommendation is held to the moves the '
                + 'scenario sweep voted for, and this plan is not.'}
          {' Objective points are the solver’s own frame: later weeks are '
           + 'discounted and banked transfers are priced, so this is not a '
           + 'raw xPts gap.'}
        </p>
      )}
```

and the weeks the board maps over become `const weeks = shown ? shown.weeks : data.weeks`, with the handoff button gated on `shown === null` (an alternative is not something the lab can be prefilled from: it was solved without the sweep's constraints, and prefilling it would silently re-impose them).

The difference highlight is a set of Plan A's move codes per gameweek:

```tsx
  // Which of this plan's moves Plan A does not make, per week — the "differing
  // moves highlighted" of spec §4.3. Computed against Plan A's own week rather
  // than against its whole horizon: a buy Plan A makes in GW7 is still a
  // different decision when this plan makes it in GW5.
  const planAMoves = new Map<number, Set<number>>(
    data.weeks.map((w) => [w.gw, new Set([...w.buys, ...w.sells]
      .map((m) => m.code))]))
```

passed into `MoveRow` as `differs={shown !== null
  && !(planAMoves.get(week.gw)?.has(move.code) ?? false)}` and rendered as `data-differs={String(differs)}` plus a left border on the row when true. On Plan A itself `differs` is always false and no row is decorated.

- [ ] **Verify.**

```bash
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

`responsive.test.tsx` covers the hub-level strips; the new one is inside `PlannerBoard`, so add its 390px case to `PlannerBoard.test.tsx` in the shape the file's existing responsive assertions use — a tab strip that wraps rather than scrolls, which is `ChipsTab.tsx:179`'s established answer for the same control.

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/hubs/planning/PlannerBoard.tsx \
  frontend/src/hubs/planning/PlannerBoard.test.tsx && git commit -m "$(cat <<'EOF'
feat: Plan A / B / C on the planner board

A tab per banked plan, drawn only when there is more than one — a strip with a
single tab in it is a control that does nothing. Each alternative says how far
behind Plan A it sits and, when the gap is negative, that it is AHEAD: the
recommendation is held to the moves the scenario sweep voted for and an
alternative is not, so being ahead is a thing that happens and a minus sign is
not how to say it.

The caption names the frame. These are objective points — later weeks
discounted, banked transfers priced — and calling them xPts would invite a
comparison against the xPts printed on the same card.

Moves Plan A does not make are marked, per week rather than per horizon: the
same buy a week earlier is a different decision. And an alternative offers no
handoff into the lab, because prefilling it would silently re-impose the
constraints it was solved without.

v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — **STOP** — the sweep draws availability, and a v10 rail narrows

**Files:**
- Modify `src/gaffer/optimize/scenarios.py` — **PROTECTED**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Modify `tests/test_v10_degradation.py` — **PROTECTED**
- Modify `src/gaffer/config.py`, `config.example.toml`
- Create `scripts/v12_w3_support.py`
- Create `tests/test_v12_w3_availability.py`

> ### STOP
>
> **Do not start this task.** Report that Task 8 is ready, paste the enumeration, and wait for authorization. **Three protected files, one of them a degradation test** — the heaviest authorization in this workstream, and A6 is why.

**Read A6 before starting.** `tests/test_v10_degradation.py:534` pins that `advise.py` does not pass `p_play` to `run_scenarios`. §4.4 exists to overturn the premise behind it. The rail narrows rather than dies, and the claim it keeps is the one T10-A actually needs.

### The complete enumeration

| # | File:lines (at `27f7933`) | Change |
| --- | --- | --- |
| S1 | `scenarios.py:20-23` | a module-docstring paragraph on the availability draw and its separate stream |
| S2 | `scenarios.py`, after `xmins_by_player_gw` | new `availability_draw()` |
| S3 | `scenarios.py:386-411` | `noised_pool(..., unavailable=None)` |
| S4 | `scenarios.py:430-462` | `run_scenarios(..., p_play=None, draw_availability=False)` |
| S5 | `advise.py:789-790` | the sweep is handed the probabilities and the switch |
| S6 | `tests/test_v10_degradation.py:516-538` | the rail's docstring and its middle assertion |

**S1 — `scenarios.py`, appended to the module docstring before the last paragraph.**

```
Since v12 the sweep can also draw *availability*: per scenario, per
(code, gameweek), a Bernoulli on ``p_play``, and a player who does not turn out
scores nothing that week. It is the same claim the noise scale is built on —
almost all of FPL's forecast error is "did he play" — asked as an outcome
rather than as a variance, and it is what makes a rotation risk sometimes
worth zero instead of always worth 60% of something.

The two draws come from **separate generators** (``seed`` and ``seed + 1``),
and the normal is drawn for every cell whether or not the cell survives. That
is deliberate: with the switch off not one draw changes, and with it on the two
arms differ *only* in which cells were zeroed, which is exactly the comparison
the §4.4 gate makes.
```

**S2 — `scenarios.py`, after `xmins_by_player_gw`.**

```python
def availability_draw(pool: pd.DataFrame,
                      p_play: dict[int, dict[int, float]],
                      rng: np.random.Generator) -> frozenset:
    """One scenario's ``{(code, gw)}`` that did not happen.

    ``available ~ Bernoulli(p_play)`` per priced cell. A cell the minutes model
    says nothing about is **always available**: "we have no appearance
    probability for him" is not the claim "he will not play", and inventing one
    would be the same error :func:`noise_ep` refuses to make about his
    variance.

    Iterated over the pool's own ``ep`` cells so a blank gameweek — absent from
    the mapping — is never drawn for. He is not unavailable that week; he has
    no fixture, and the board already prices him at zero.
    """
    out = set()
    for code, cell in zip(pool["code"], pool["ep"]):
        per_gw = p_play.get(int(code)) or {}
        for gw in cell:
            p = per_gw.get(int(gw))
            if p is None:
                continue
            if float(rng.random()) >= float(p):
                out.add((int(code), int(gw)))
    return frozenset(out)
```

**S3 — `scenarios.py:386-411`.** The signature gains `unavailable: frozenset | None = None`, the docstring gains a paragraph, and the cell comprehension gains the override:

```python
    # v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md): the noise is
    # drawn for every cell either way — the draw happens above, in
    # ``noise_ep``, before this line — and a cell this scenario says did not
    # happen is then overwritten with zero. Drawing and discarding rather than
    # skipping is what keeps the noise stream identical between an arm with the
    # availability draw on and one with it off, so the two differ in the
    # zeroing and in nothing else.
    blank = unavailable or frozenset()
    ...
        cells.append({gw: (0.0 if (int(code), int(gw)) in blank
                           else noised[(int(code), int(gw))])
                      for gw in cell})
```

**S4 — `scenarios.py:430-462`.**

```python
def run_scenarios(pool: pd.DataFrame, state: SolveInput,
                  xmins: dict[tuple[int, int], float], *, n: int, seed: int,
                  p_play: dict[int, dict[int, float]] | None = None,
                  draw_availability: bool = False,
                  **solve_cfg) -> ScenarioRun:
```

with, after the `n <= 0` guard:

```python
    rng = np.random.default_rng(seed)
    # v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md): its own
    # stream, a million miles from being interleaved with the noise. Sharing
    # ``rng`` would shift every normal draw by one and make the on/off arms
    # differ in their *noise* as well as in their availability, which is the
    # one thing the gate must not have to disentangle.
    avail_rng = None
    if draw_availability:
        if p_play:
            avail_rng = np.random.default_rng(seed + 1)
        else:
            # The lever guard, in-process. Silence here is how a sweep that
            # believes it models availability ships without modelling any.
            print("scenarios: draw_availability is on but no p_play reached "
                  "the sweep — availability was not drawn, and these "
                  "frequencies are the pre-v12 ones")
```

and inside the loop:

```python
    for _ in range(n):
        unavailable = (availability_draw(pool, p_play, avail_rng)
                       if avail_rng is not None else None)
        board = noised_pool(pool, xmins, rng, unavailable=unavailable)
```

**S5 — `advise.py:789-790`.**

```python
        # v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md): the
        # sweep draws availability from the same probabilities the solver's
        # bench weighting reads — as an *outcome* per scenario, never as an
        # objective weight. ``solve_kw`` is unchanged and carries no p_play, so
        # no scenario is solved under §F1's frailty and the raw optimum this
        # gate compares against is still the unweighted one (v10 T10-A).
        run = run_scenarios(pool, state, xmins, n=cfg.scenarios_n,
                            seed=cfg.scenarios_seed + gw,
                            p_play=(p_play_by_code if cfg.draw_availability
                                    else None),
                            draw_availability=cfg.draw_availability,
                            **solve_kw)
```

**S6 — `tests/test_v10_degradation.py:516-538`.** The function keeps its name. Its docstring gains a third paragraph and its middle assertion is replaced:

```python
def test_the_p_play_seam_follows_the_sweep_and_not_the_solve():
    """The T10-A rewiring, as a rail — and the hole the first cut left.

    ``decide()`` compares the raw optimum against the sweep's plurality, and
    the sweep does not *solve* under ``p_play``. Weighting the raw solve
    *while the sweep runs* would make that comparison a comparison of two
    different objectives — reported to the user as ``raw_optimum_agrees=False``,
    for a reason that is not instability.

    But when the sweep does not run there is no such comparison, and the raw
    solve *is* the advice: fast advice (``scenarios_n = 0``) and the
    initial-squad weeks silently lost the whole of §F1 to a guard that was
    protecting a gate they never reach.

    **v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md) narrowed
    this.** The rail used to assert that the string ``p_play`` did not appear
    near the sweep call at all, which was a proxy for the claim above and not
    the claim itself. §4.4 hands the sweep ``p_play`` for a Bernoulli
    availability draw — an outcome per scenario, not a coefficient — so the
    proxy now forbids the feature. What survives is T10-A's actual claim: the
    sweep's *solve bundle* is still ``solve_kw``, so no scenario is solved
    under §F1's frailty weights and the raw optimum remains the unweighted one.
    The consequence §4.4 accepts, recorded rather than papered over: the sweep
    now models availability risk the raw solve does not, so
    ``raw_optimum_agrees`` reads ``False`` more often — and unlike the
    objective mismatch this rail was written about, that disagreement is
    information.
    """
    src = _advise_src()
    assert "solve_kw = dict(opt_kw, ft_lambda=ft_lambda)" in src
    # The sweep's own bundle is still untouched: it never had p_play.
    assert "scenario_kw" not in src
    sweep = src[src.index("run_scenarios("):src.index("run_scenarios(") + 400]
    # The solve bundle the sweep passes through is still the unweighted one.
    assert "**solve_kw" in sweep
    # p_play reaches the sweep as a draw and only behind its own switch.
    assert "draw_availability=cfg.draw_availability" in sweep
    assert "p_play=(p_play_by_code if cfg.draw_availability" in sweep

    gated, ungated = _raw_solve_branches()
    assert not [k for k in gated.keywords if k.arg == "p_play"]
    assert [k.value.id for k in ungated.keywords if k.arg == "p_play"] == [
        "p_play_by_code"]
```

`test_the_coherent_plan_carries_the_weights_when_the_sweep_ran` (`:543-551`) is **not** edited: it counts `p_play=p_play_by_code`, which the S5 spelling (`p_play=(p_play_by_code`) does not match, so the count stays 2. Verify it after implementing.

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_availability.py`:

```python
"""§4.4: the sweep can ask "did he play", and off is off to the byte.

The rail that matters most here is the negative one. A scenario sweep is the
gate on every transfer the tool recommends, so a change to its draws is a
change to every recommendation — and with ``draw_availability`` off, not one
number may move. That is asserted by re-solving the same seed both ways and
comparing the plans, not by reading the code.

The second rail is the separation of the two streams. Availability is drawn
from ``seed + 1`` and the normal is drawn for every cell whether or not the
cell survives, so the on and off arms differ in which cells were zeroed and in
nothing else. If the availability draw consumed from the noise generator, every
comparison the §4.4 gate makes would be measuring two changes at once.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gaffer.optimize.milp import SolveInput
from gaffer.optimize.scenarios import (availability_draw, noised_pool,
                                       run_scenarios)

SOLVE_KW = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                itb_value=0.05, hit_cost=4)


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40, "sell": 40,
                         "ep": {5: 1.0 + (code % 7) * 0.4}})
            code += 1
    return pd.DataFrame(rows)


def _state() -> SolveInput:
    return SolveInput(owned_codes=[], bank=1000, free_transfers=15, gws=[5])


def _xmins(pool) -> dict:
    return {(int(c), 5): 70.0 for c in pool["code"]}


def _p_play(pool, value=0.5) -> dict:
    return {int(c): {5: value} for c in pool["code"]}


def _signature(run) -> list:
    return [sorted(p.gw_plans[0].squad) for p in run.plans]


def test_with_the_switch_off_the_sweep_is_the_pre_v12_sweep():
    """The whole feature's cost of admission."""
    pool, xm = _pool(), _xmins(_pool())
    before = run_scenarios(pool, _state(), xm, n=3, seed=7, **SOLVE_KW)
    after = run_scenarios(pool, _state(), xm, n=3, seed=7,
                          p_play=_p_play(pool), draw_availability=False,
                          **SOLVE_KW)
    assert _signature(before) == _signature(after)


def test_the_switch_on_with_no_probabilities_is_also_the_pre_v12_sweep(capsys):
    """And says so. A sweep that believes it models availability and models
    none is the failure v10's lever guard was written about."""
    pool, xm = _pool(), _xmins(_pool())
    before = run_scenarios(pool, _state(), xm, n=2, seed=7, **SOLVE_KW)
    after = run_scenarios(pool, _state(), xm, n=2, seed=7, p_play={},
                          draw_availability=True, **SOLVE_KW)
    assert _signature(before) == _signature(after)
    assert "no p_play reached the sweep" in capsys.readouterr().out


def test_the_switch_on_changes_the_boards_it_draws():
    pool, xm = _pool(), _xmins(_pool())
    off = run_scenarios(pool, _state(), xm, n=4, seed=7, **SOLVE_KW)
    on = run_scenarios(pool, _state(), xm, n=4, seed=7, p_play=_p_play(pool),
                       draw_availability=True, **SOLVE_KW)
    assert _signature(off) != _signature(on)


def test_the_noise_stream_is_untouched_by_the_availability_draw():
    """The separation. With every player certain to play, the availability
    draw consumes from its own generator and zeroes nothing, so the boards
    must be identical to the off arm — which is only true if the two draws do
    not share an rng."""
    pool, xm = _pool(), _xmins(_pool())
    off = run_scenarios(pool, _state(), xm, n=3, seed=11, **SOLVE_KW)
    certain = run_scenarios(pool, _state(), xm, n=3, seed=11,
                            p_play=_p_play(pool, 1.0),
                            draw_availability=True, **SOLVE_KW)
    assert _signature(off) == _signature(certain)


def test_a_player_who_did_not_play_scores_nothing_that_week():
    pool = _pool()
    blanked = noised_pool(pool, _xmins(pool), np.random.default_rng(1),
                          unavailable=frozenset({(3, 5)}))
    assert blanked.loc[blanked["code"] == 3, "ep"].iloc[0][5] == 0.0
    assert blanked.loc[blanked["code"] == 4, "ep"].iloc[0][5] > 0.0


def test_a_certain_player_is_never_drawn_out_and_a_doubtful_one_sometimes_is():
    pool, rng = _pool(), np.random.default_rng(3)
    assert availability_draw(pool, _p_play(pool, 1.0), rng) == frozenset()
    coin = _p_play(pool, 0.5)
    drawn = [len(availability_draw(pool, coin, rng)) for _ in range(20)]
    assert min(drawn) > 0 and max(drawn) < len(pool)


def test_a_player_with_no_probability_is_available_and_not_absent():
    """"We have no appearance probability for him" is not "he will not play"
    — noise_ep's own rule about his variance, applied to his outcome."""
    pool = _pool()
    silent = availability_draw(pool, {}, np.random.default_rng(1))
    assert silent == frozenset()


def test_a_blank_gameweek_is_never_drawn_for():
    """A week the pool does not price is not a week he was unavailable in."""
    pool = _pool()
    p_play = {int(c): {5: 0.0, 6: 0.0} for c in pool["code"]}
    drawn = availability_draw(pool, p_play, np.random.default_rng(1))
    assert all(gw == 5 for _, gw in drawn)


def test_the_sweep_is_reproducible_with_the_draw_on():
    pool, xm = _pool(), _xmins(_pool())
    kw = dict(n=3, seed=5, p_play=_p_play(pool), draw_availability=True)
    a = run_scenarios(pool, _state(), xm, **kw, **SOLVE_KW)
    b = run_scenarios(pool, _state(), xm, **kw, **SOLVE_KW)
    assert _signature(a) == _signature(b)


def test_the_config_key_defaults_off_and_reads_from_the_scenarios_section(
        tmp_path, monkeypatch):
    """OFF until its gate passes (CONVENTIONS §6, orchestrator ruling
    2026-09-02). An unmeasured arm that ships on by default is an arm the
    gate is asked to un-ship, which is not how a pre-registered rule works.
    A passing captain-support check flips this one line and this one test."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).draw_availability is False
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[scenarios]\ndraw_availability = true\n")
    assert load_config(path).draw_availability is True


def test_the_shipped_default_leaves_the_advice_path_on_the_pre_v12_sweep():
    """The consequence of the default, asserted where a reader will look for
    it: out of the box, ``advise`` passes ``p_play=None`` and the sweep is the
    one v11 shipped. Nothing about this cycle reaches a user's advice until
    the gate says it may."""
    from gaffer.config import Config

    assert Config(entry_id=1, league_id=2).draw_availability is False
```

- [ ] **Implement S1-S4** in `scenarios.py`, then the config key:

```python
    # v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md). Per
    # scenario, per player-gameweek, a Bernoulli on p_play: the sweep asks
    # "did he turn out" as an outcome rather than only as a variance.
    #
    # Defaults OFF. Spec §4.4 writes the key as ``true``; CONVENTIONS §6 and
    # the orchestrator's ruling (2026-09-02) say an arm ships behind its flag
    # until its gate passes, and this arm's gate — the captain-support check,
    # Task 14 — is run after the merge. A passing gate flips this line, its
    # two config tests and the example file, and records the number.
    draw_availability: bool = False
```

read as `draw_availability=bool(scen.get("draw_availability", False)),` — `[scenarios]` is read key-by-key rather than splatted (`config.py:135-139`), so this line is required, and its default must match the dataclass's or the two disagree about a fresh clone.

`config.example.toml`, under `[scenarios]`:

```toml
# Per scenario, draw whether each player turned out at all (Bernoulli on the
# minutes model's p_play) before the EP noise is applied. "Did he play" is
# most of FPL's forecast error, and a sweep that only widened the EP band was
# asking a softer question. Off — the shipped default — is the pre-v12 sweep
# exactly, and it stays off until the captain-support gate has measured it
# (v12 W3 §4.4; the number to beat is a support drop of 10 points).
draw_availability = false
```

- [ ] **Implement S5**, then **S6** — the protected rail — and immediately verify the *other* v10 rail still holds:

```bash
grep -c "p_play=p_play_by_code" src/gaffer/advise.py   # must still print 2
.venv/bin/pytest -q tests/test_v10_degradation.py
```

- [ ] **Write the §4.4 gate driver.** Create `scripts/v12_w3_support.py`. **The implementer builds it and does not run it** (CONVENTIONS §7).

```python
"""Gate §4.4: does the availability draw collapse the captain's support?

Spec §4.4's rule, pre-registered: scenario support for the live captain must
not fall below its current value by more than 10 points on the same inputs.
The number is what S1 recorded as the failure signature of a sweep gone wrong
— captain support 92% -> 22%, after which the gate found no move that cleared
threshold on its own and advised a plan carrying -20 in hits. So this is not a
generic sanity check; it is that failure, watched for by name.

Two arms on **one board**: the saved solve state, the same seed, the same
noise stream, differing only in whether availability was drawn. The board is
built exactly as ``sensitivity.run_sensitivity`` builds it — saved state, raw
EP, cover, tilt, ``milp_pool``, ``solve_kw_from_state`` — because a support
number measured on a different board than the advice ran on is a number about
nothing.

**The lever guard**, this repo's twice-learned lesson (v10 plan A3): before
anything is measured, the driver checks that p_play covers the pool and that
the on-arm actually blanked at least one cell. If it did not, both arms are
the same arm and the delta below is a decorated zero. It exits rather than
printing one.

Run it, watch it, read the line::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python \\
        scripts/v12_w3_support.py > logs/v12_w3_support.log 2>&1 &
    grep -e W3_SUPPORT_LEVER -e W3_SUPPORT_DONE logs/v12_w3_support.log
"""

from __future__ import annotations

import json
import sys

import numpy as np

from gaffer.artifacts import (latest_gw, load_advice, load_components,
                              load_solve_state, milp_pool, raw_ep_by,
                              solve_kw_from_state)
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.policy import captain_frequency_of
from gaffer.optimize.scenarios import (availability_draw, move_frequencies,
                                       run_scenarios, xmins_by_player_gw)

N = 40
"""The advice path's own sweep size, not sensitivity's twenty. The gate is
about the sweep that decides."""


def _p_play(comp, gws: list[int]) -> dict[int, dict[int, float]]:
    """``advise.py:724-729``'s expression, for the same reason it is a mean:
    "did he turn out at all" is one outcome across a double gameweek."""
    if "p_play" not in comp.columns:
        return {}
    out: dict[int, dict[int, float]] = {}
    grouped = (comp.groupby(["code", "gw"], as_index=False)
               .agg(p_play=("p_play", "mean")))
    for row in grouped.itertuples():
        if int(row.gw) in gws:
            out.setdefault(int(row.code), {})[int(row.gw)] = float(row.p_play)
    return out


def main() -> None:
    gw = latest_gw()
    if gw is None:
        raise SystemExit("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    advice = load_advice(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    comp = load_components(gw)
    xmins = xmins_by_player_gw(comp)
    p_play = _p_play(comp, gws)
    solve_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                             free_transfers=state.free_transfers, gws=gws)

    # --- the lever guard --------------------------------------------------
    if not xmins:
        raise SystemExit(
            "no expected minutes on this board: every scenario draws the same "
            "EP and the support numbers below would be 100% by construction.")
    priced = sum(len(cell) for cell in pool["ep"])
    covered = sum(1 for code, cell in zip(pool["code"], pool["ep"])
                  for g in cell if int(g) in (p_play.get(int(code)) or {}))
    blanked = len(availability_draw(pool, p_play, np.random.default_rng(1)))
    if not covered or not blanked:
        raise SystemExit(
            f"the lever is disconnected: {covered} of {priced} priced cells "
            f"carry a p_play and one draw blanked {blanked} of them, so the "
            f"two arms below are the same arm.")
    print("W3_SUPPORT_LEVER", json.dumps(
        {"priced": priced, "covered": covered, "blanked_one_draw": blanked}),
        flush=True)

    # --- the two arms -----------------------------------------------------
    # The advice path's own per-gameweek seed, not sensitivity's million-clear
    # offset: this gate is about the sweep that decided, so it replays that
    # sweep's draws. ``SolveState.opt`` does not carry the seed — it holds the
    # solver bundle — so it comes from the config, exactly as advise reads it.
    from gaffer.config import serving_config

    seed = int(serving_config().scenarios_seed) + int(gw)
    captain = int(advice["captain"]["code"])
    out = {"gw": int(gw), "captain": captain, "seed": seed, "n": N}
    for arm, draw in (("off", False), ("on", True)):
        run = run_scenarios(pool, solve_state, xmins, n=N, seed=seed,
                            p_play=p_play, draw_availability=draw, **opt)
        freqs = move_frequencies(run.plans)
        support = captain_frequency_of(freqs, captain)
        out[f"support_{arm}"] = None if support is None else round(
            support * 100, 1)
        out[f"completed_{arm}"] = int(run.completed)
    if out["support_off"] is None or out["support_on"] is None:
        # The live captain not appearing in an arm at all is a support of
        # zero for this gate's purpose: he was never chosen.
        out["support_off"] = out["support_off"] or 0.0
        out["support_on"] = out["support_on"] or 0.0
    out["drop_pts"] = round(out["support_off"] - out["support_on"], 1)
    out["passes"] = bool(out["drop_pts"] <= 10.0)
    print("W3_SUPPORT_DONE", json.dumps(out), flush=True)
    sys.exit(0 if out["passes"] else 1)


if __name__ == "__main__":
    main()
```

Add one rail for the driver in `tests/test_v12_w3_availability.py` — imported, never shelled out, which `tests/test_v8a_degradation.py:140` pins for every test in this repo:

```python
def test_the_support_driver_guards_its_lever_before_it_measures():
    """v10's lesson as a rail on the instrument itself: a driver that prints a
    delta without checking that the two arms differ is a driver that reports
    zeros as evidence."""
    from pathlib import Path

    src = Path("scripts/v12_w3_support.py").read_text()
    assert "the lever is disconnected" in src
    assert src.index("W3_SUPPORT_LEVER") < src.index("W3_SUPPORT_DONE")
    # One board, one seed, one noise stream: the arms differ in the draw.
    assert src.count("run_scenarios(") == 1
    assert "solve_kw_from_state(state)" in src
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_availability.py tests/test_scenarios.py \
  tests/test_v6_degradation.py tests/test_v10_degradation.py \
  tests/test_advise.py tests/test_sensitivity.py tests/test_v8e_degradation.py \
  tests/test_v7b_driver.py tests/test_config.py
.venv/bin/pytest -q
```

`tests/test_v7b_driver.py` matters here: it fakes `run_scenarios` with `def fake_run_scenarios(pool, state, xm, n, seed, **kw)`, which still absorbs the two new keywords through `**kw` — but the replay driver passes neither, so a failure means the signature moved in a way the replay can see. **Stop and report** if it does.

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/scenarios.py src/gaffer/advise.py \
  tests/test_v10_degradation.py src/gaffer/config.py config.example.toml \
  scripts/v12_w3_support.py tests/test_v12_w3_availability.py \
  && git commit -m "$(cat <<'EOF'
feat: the sweep asks whether he played, not only how much he might score

Per scenario, per player-gameweek, a Bernoulli on p_play; a player who did not
turn out scores nothing that week and the EP noise is applied to the rest as
before. The sweep's own reasoning has always been that almost all of FPL's
forecast error is "did he play" — it was pricing that as a wider band and never
as an outcome.

Two generators, deliberately: availability draws from seed + 1 and the normal
is drawn for every cell whether the cell survives or not. Off, not one number
moves. On, the two arms differ in which cells were zeroed and in nothing else,
which is the only way the support gate measures one change.

This narrows a protected v10 rail. test_v10_degradation asserted that the
string "p_play" did not appear near the sweep call — a proxy for T10-A's claim
that no scenario is solved under §F1's frailty weights. The proxy now forbids
the feature, so the rail asserts the claim instead: the sweep's solve bundle is
still solve_kw, and the raw optimum the gate compares against is still
unweighted. The consequence is recorded rather than hidden — the sweep now
models availability the raw solve does not, so raw_optimum_agrees reads False
more often, and that disagreement is information.

It ships OFF. The spec writes the key as true; CONVENTIONS §6 says an arm lives
behind its flag until its gate has measured it, and this one's gate — captain
support must not fall by more than 10 points, S1's failure signature by name —
runs after the merge. So W3 lands with no user's advice drawing availability,
and a passing gate flips one default, one example line and two expectations.

The gate driver is built and not run (CONVENTIONS §7), with the lever guard
first: if p_play covers nothing, or a draw blanks nothing, it exits instead of
printing a decorated zero.

v12 W3 §4.4 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edits to scenarios.py, advise.py and
tests/test_v10_degradation.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — **STOP** — the wildcard-and-bench-boost pair

**Files:**
- Modify `src/gaffer/optimize/chips.py` — **PROTECTED**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/routers/chips.py`
- Modify `frontend/src/hubs/planning/ChipsTab.tsx`
- Create `tests/test_v12_w3_chip_pairs.py`

> ### STOP
>
> **Do not start this task.** Report that Task 9 is ready, paste the enumeration, and wait for authorization to edit `chips.py` and `advise.py`.

**Read A8 before starting.** The pair is **data-gated and dead today**: `data/chip_scenarios.toml` does not exist, so `load_chip_scenarios()` is `{}` and no pair row can be produced. That is not a reason to build it differently — it is the reason the empty state is the main case and the ROADMAP gets a checkbox.

**And the reason `dgw_gws` is an argument rather than a file read:** `backtest.py:540` calls `evaluate_chips` and `backtest.py:542-560` has no execution branch for a chip named `wildcard+bboost`. A pair row reaching `_pick_chip` would be recorded as played and applied to nothing. Keeping the parameter opt-in — and not passing it from `backtest.py` (import-only) or from `routers/meta.py` — is what makes that unreachable rather than merely unlikely.

### The complete enumeration

| # | File:lines (at `27f7933`) | Change |
| --- | --- | --- |
| K1 | `chips.py:38-44` | `PAIR_CHIP`, `PAIR_DGW_MIN_PROB` |
| K2 | `chips.py:92-103` | `_weeks_covered` credits any wildcard-carrying option |
| K3 | `chips.py:106-172` | `evaluate_chips(..., dgw_gws=None)`, the `gw2` column, the pair loop |
| K4 | `advise.py:735-736` | the scenario probabilities are kept rather than passed straight through |
| K5 | `advise.py:885-886` | `evaluate_chips` is handed the double gameweeks |

**K1 — `chips.py`, after `CHIP_PLAY_THRESHOLD`.**

```python
# v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md)
PAIR_CHIP = "wildcard+bboost"
"""The one chip *pair* this module evaluates: a wildcard in one week and a
bench boost in a later one, scored as a single option.

Named rather than composed, because everything downstream keys on the chip
string: the workbench row, the UI's label table, the ledger. A name with a
``+`` in it is deliberately not a two-letter code — there is no What-If code
for a pair, and ``ChipsTab``'s mapping already leaves an unknown row alone
rather than re-solving it as no chip at all.
"""

PAIR_DGW_MIN_PROB = 0.5
"""How likely a double gameweek must be before a pair is evaluated for it.

``data/chip_scenarios.toml`` carries probabilities, and today's writer only
ever writes ``1.0`` — a double in the published fixture list, not a guess. The
bar exists for the day the file carries projections: a bench boost planned
around a 30%-likely double is a plan around a rumour, and the extra solves it
costs are spent on every wildcard week in the horizon.
"""
```

**K2 — `chips.py:92-103`.**

```python
def _weeks_covered(chip: str, gw: int, gws: list[int]) -> int:
    """Horizon gameweeks a chip played in ``gw`` is credited with.

    A wildcard rebuilds the squad for the rest of the horizon, so a window of
    six weeks gives a GW1 wildcard six weeks of credit and a GW6 wildcard
    one. Comparing those totals is how "play it now" won by default; dividing
    by this makes the weeks comparable. The other three chips are one-week
    chips and score one week wherever they land.

    v12 W3 §4.5: a pair carrying a wildcard is credited the wildcard's weeks —
    the bench boost inside it is still a one-week chip, but the squad rebuild
    that dominates the option's value runs to the end of the window exactly as
    a lone wildcard's does.
    """
    if not chip.startswith("wildcard"):
        return 1
    return sum(1 for g in gws if g >= gw)
```

**K3 — `chips.py:106-172`.** The signature gains one keyword, `add` gains one optional argument, the pair loop follows the singles, and the frame keeps `gw2` an object column:

```python
def evaluate_chips(pool: pd.DataFrame, state: SolveInput,
                   chips_available: list[str] | None = None,
                   base: Plan | None = None,
                   avail_by_gw: dict[int, list[str]] | None = None,
                   dgw_gws: set[int] | None = None,
                   **cfg) -> pd.DataFrame:
```

with this paragraph appended to its docstring:

```
    ``dgw_gws`` (v12 W3 §4.5) are the horizon gameweeks believed to be doubles.
    Given a non-empty set, the table also carries the wildcard-plus-bench-boost
    *pair*: a wildcard in ``g`` and a bench boost in a later ``g2`` that is one
    of them, scored as one option against the same no-chip baseline, with
    ``gw`` the wildcard's week and ``gw2`` the boost's. Omitted — which is
    every caller but ``advise`` — the table is exactly the table it was, and
    that is not a convenience: ``backtest``'s chip executor has no branch for a
    pair, so a pair row reaching it would be recorded as played and applied to
    nothing.
```

```python
    def add(chip: str, gw: int, gain: float, gw2: int | None = None) -> None:
        weeks = _weeks_covered(chip, gw, state.gws)
        rows.append({"chip": chip, "gw": gw, "gw2": gw2, "gain": gain,
                     "per_week": gain / weeks})
```

after the singles loops and before the `if not rows:` guard:

```python
    # v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md): the pair.
    # Only into a believed double, and only forward — a bench boost in the
    # wildcard's own week is not playable (one chip per gameweek), and a boost
    # before the rebuild is just a bench boost. Bounded by the doubles in the
    # horizon rather than by the horizon squared.
    for g in state.gws:
        if not dgw_gws or "wildcard" not in available(g):
            continue
        for g2 in state.gws:
            if g2 <= g or int(g2) not in dgw_gws:
                continue
            if "bboost" not in available(g2):
                continue
            p = solve_plan(pool, replace(state, wildcard_gw=g,
                                         bench_boost_gw=g2), **cfg)
            add(PAIR_CHIP, g, p.objective - base.objective, gw2=g2)
    if not rows:
        # Every chip spent is a normal late-season state; hand back the empty
        # frame rather than letting the column-less DataFrame blow up below.
        return pd.DataFrame(columns=["chip", "gw", "gw2", "gain", "per_week"])
    frame = pd.DataFrame(rows)
    # ``gw2`` is None on every ordinary row, and pandas turns a column of
    # None-and-int into float64 with NaN — which pydantic's ``int | None`` then
    # refuses, and which json.dumps writes as a bare NaN. Held as an object
    # column so a None stays a None.
    frame["gw2"] = frame["gw2"].astype("object").where(frame["gw2"].notna(),
                                                       None)
    return (frame
            .assign(gain=lambda d: d["gain"].round(2),
                    per_week=lambda d: d["per_week"].round(2))
            .sort_values("gain", ascending=False).reset_index(drop=True))
```

**K4 — `advise.py:735-736`.**

```python
    # v12 W3 §4.5: kept rather than passed straight through — the same
    # probabilities decide θ's tail and which weeks a chip pair is worth
    # solving for, and reading the file twice is two chances to disagree.
    dgw_probs = load_chip_scenarios()
    chip_thresholds = chip_thresholds_from_asset(priors, dgw_probs)
```

**K5 — `advise.py:885-886`.**

```python
        chip_table = evaluate_chips(chip_pool, state, base=chip_base,
                                    avail_by_gw=avail_by_gw,
                                    # v12 W3 §4.5: the weeks a pair is worth
                                    # solving for. Empty until the fixture
                                    # list carries a real double, which is
                                    # every week of the season as published.
                                    dgw_gws={int(g) for g, p
                                             in dgw_probs.items()
                                             if p >= PAIR_DGW_MIN_PROB},
                                    **opt_kw)
```

with `PAIR_DGW_MIN_PROB` added to `advise.py:66-67`'s `chips` import.

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_chip_pairs.py`:

```python
"""§4.5: wildcard plus bench boost, as one option.

The empty state is the main case and is tested first, because it is the state
every machine is in: ``data/chip_scenarios.toml`` does not exist, the writer
refuses to create it while every gameweek has ten fixtures, so ``dgw_gws`` is
empty and the table is exactly the table it was.

The most important assertion in the file is the one about *other* callers.
``backtest.py``'s chip executor branches on the chip name and has no arm for a
pair: a pair row reaching ``_pick_chip`` would be selected, recorded as played
and applied to nothing — a phantom chip in a replay. The parameter is opt-in
and this file pins that no caller but ``advise`` opts in.
"""

from __future__ import annotations

import inspect
from dataclasses import replace

import pandas as pd
import pytest

from gaffer.optimize import chips as chips_mod
from gaffer.optimize.chips import (PAIR_CHIP, PAIR_DGW_MIN_PROB,
                                   _weeks_covered, evaluate_chips)
from gaffer.optimize.milp import SolveInput

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)
GWS = [1, 2, 3]


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1, "cost": 40, "sell": 40,
                         "ep": {g: 1.0 + (code % 7) * 0.3 + g * 0.1
                                for g in GWS}})
            code += 1
    return pd.DataFrame(rows)


def _state() -> SolveInput:
    return SolveInput(owned_codes=list(range(1, 16)), bank=200,
                      free_transfers=1, gws=list(GWS))


def _table(**kw):
    return evaluate_chips(_pool(), _state(),
                          chips_available=["wildcard", "bboost"], **kw, **CFG)


def test_with_no_doubles_the_table_is_the_table_it_was():
    """Today's state on every machine."""
    table = _table()
    assert PAIR_CHIP not in set(table["chip"])
    assert list(table.columns) == ["chip", "gw", "gw2", "gain", "per_week"]


def test_gw2_is_None_on_an_ordinary_row_and_never_nan():
    """pandas turns a column of None-and-int into float64 with NaN, which
    pydantic refuses and json writes as a bare NaN."""
    rows = _table(dgw_gws={3}).to_dict("records")
    singles = [r for r in rows if r["chip"] != PAIR_CHIP]
    assert singles and all(r["gw2"] is None for r in singles)


def test_a_double_in_the_horizon_produces_a_pair_naming_both_weeks():
    rows = [r for r in _table(dgw_gws={3}).to_dict("records")
            if r["chip"] == PAIR_CHIP]
    assert rows
    assert all(r["gw2"] == 3 and r["gw"] < 3 for r in rows)


def test_the_boost_is_never_in_the_wildcards_own_week():
    """One chip per gameweek is the rule of the game."""
    rows = [r for r in _table(dgw_gws={1, 2, 3}).to_dict("records")
            if r["chip"] == PAIR_CHIP]
    assert all(r["gw2"] > r["gw"] for r in rows)


def test_the_pair_is_scored_against_the_same_baseline_as_the_singles():
    """A joint solve minus the no-chip plan, in the same undecayed frame — so
    a pair worth less than its wildcard alone is a readable comparison rather
    than a units bug."""
    table = _table(dgw_gws={3})
    wc = table[(table["chip"] == "wildcard") & (table["gw"] == 1)]
    pair = table[(table["chip"] == PAIR_CHIP) & (table["gw"] == 1)]
    assert not wc.empty and not pair.empty
    # The pair is the same wildcard plus a boost, so it cannot be worth less.
    assert float(pair["gain"].iloc[0]) >= float(wc["gain"].iloc[0]) - 1e-6


def test_a_pair_is_credited_the_wildcards_weeks_not_one():
    assert _weeks_covered(PAIR_CHIP, 1, GWS) == 3
    assert _weeks_covered("bboost", 1, GWS) == 1


def test_a_week_with_no_bench_boost_available_produces_no_pair():
    table = evaluate_chips(_pool(), _state(),
                           avail_by_gw={1: ["wildcard"], 2: [], 3: []},
                           dgw_gws={3}, **CFG)
    assert PAIR_CHIP not in set(table["chip"])


def test_no_caller_but_advise_asks_for_pairs():
    """The rail this file exists for. backtest's chip executor has no branch
    for a pair name, so a pair row reaching _pick_chip would be recorded as
    played and applied to nothing."""
    from gaffer import backtest
    from gaffer.web.routers import meta

    for source in (inspect.getsource(backtest),
                   inspect.getsource(meta.chips_plan)):
        assert "dgw_gws" not in source


def test_advise_derives_the_doubles_from_the_probabilities_it_already_read():
    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "dgw_probs = load_chip_scenarios()" in src
    assert src.count("load_chip_scenarios()") == 1
    assert "dgw_gws={int(g) for g, p" in src
    assert "PAIR_DGW_MIN_PROB" in src


def test_the_probability_bar_excludes_a_rumoured_double():
    assert PAIR_DGW_MIN_PROB == 0.5
    probs = {3: 0.3}
    assert {g for g, p in probs.items() if p >= PAIR_DGW_MIN_PROB} == set()
```

- [ ] **Implement K1-K5** exactly as enumerated.

- [ ] **Implement the schema and router.** `ChipWorkbenchRow` gains:

```python
    gw2: int | None = None
    """The second week of a chip *pair* — the bench boost's, where ``gw`` is
    the wildcard's. ``None`` on every single-chip row, which is every row on
    every payload written before v12 and every row until the fixture list
    carries a double."""
```

`routers/chips.py`'s row construction gains `gw2=(None if r.get("gw2") is None else int(r["gw2"])),`.

- [ ] **Implement the label.** `ChipsTab.tsx`'s `LABELS` gains `'wildcard+bboost': 'Wildcard + Bench Boost'`, and the chip cell prints both weeks when there are two:

```tsx
                  <td className="num py-1.5 text-right text-text-secondary">
                    {row.gw2 == null ? `GW${row.gw}`
                      : `GW${row.gw} + GW${row.gw2}`}
                  </td>
```

with `gw2?: number | null` added to `ChipWorkbenchRow` in `types.ts`, and one test in `ChipsTab.test.tsx` asserting a pair row renders `GW4 + GW7` and its full label. `CHIP_CODES` is **not** extended — there is no What-If code for a pair, and `pick()` already leaves an unmapped row alone rather than re-solving it with no chip.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_chip_pairs.py tests/test_chips.py \
  tests/test_chip_sanity.py tests/test_backtest.py tests/test_web_chips.py \
  tests/test_web_meta.py tests/test_advise.py tests/test_calibrate_decisions.py
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
```

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/chips.py src/gaffer/advise.py \
  src/gaffer/web/schemas.py src/gaffer/web/routers/chips.py \
  frontend/src/types.ts frontend/src/hubs/planning/ChipsTab.tsx \
  frontend/src/hubs/planning/ChipsTab.test.tsx \
  tests/test_v12_w3_chip_pairs.py && git commit -m "$(cat <<'EOF'
feat: wildcard plus bench boost, priced as one decision

A wildcard in one week and a boost in a later double, solved jointly and scored
against the same no-chip baseline as the singles — so "rebuild now and boost in
GW29" is comparable with "rebuild now" instead of being two rows nobody can add
up. Credited the wildcard's weeks, because the squad rebuild is what dominates
the option.

Dead on today's data, and shipped saying so: data/chip_scenarios.toml does not
exist and its writer refuses to create one while every gameweek has ten
fixtures, so dgw_gws is empty and the table is byte-identical to today's.

The doubles arrive as an argument rather than a file read, and only advise
passes them. backtest's chip executor branches on the chip name and has no arm
for a pair: a pair row reaching it would be recorded as played and applied to
nothing. Opt-in is what makes that unreachable rather than unlikely, and a test
pins that no other caller opts in.

v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edits to chips.py and advise.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — **STOP** — a free hit priced from the week it is played in

**Files:**
- Modify `src/gaffer/optimize/milp.py` — **PROTECTED**
- Modify `src/gaffer/optimize/chips.py` — **PROTECTED**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Create `tests/test_v12_w3_free_hit.py`

> ### STOP
>
> **Do not start this task.** Report that Task 10 is ready, paste the enumeration, and wait for authorization. **This is the one item on the replay's path** (A10) — the gate's delta, whatever it is, is this task's.

**Read A7 before starting.** The re-solve the spec asks for already exists. What is wrong is the position it solves from and the hits it does not credit.

### The complete enumeration

| # | File:lines (at `27f7933`) | Change |
| --- | --- | --- |
| F1 | `milp.py:158-171` (`GwPlan`) | `bank`, appended and defaulted |
| F2 | `milp.py:698-710` | the value is read off the solved variable |
| F3 | `chips.py:8-10` | the module note stops calling the free hit an approximation of a re-solve |
| F4 | `chips.py:175-206` | `free_hit_gain` scores from the baseline's own week |
| F5 | `advise.py:889-890` | the freehit row's note says what is still excluded |

**F1 — `milp.py`, appended to `GwPlan`.**

```python
    # v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md)
    bank: float | None = None
    """Money left after this gameweek's transfers, in 0.1m units.

    The MILP has always solved for it and always thrown it away, which is why
    a chip priced three weeks out had to be priced off *today's* bank. ``None``
    when the solver returned no value for the variable — a state believed
    unreachable on an optimal solve, kept because a caller that reads 0.0 as
    "no money" would price a free hit off nothing at all.
    """
```

**F2 — `milp.py:698-710`**, in the `GwPlan(...)` construction:

```python
            hits=int(round(hits[t].varValue or 0)),
            expected_pts=sum(ep[c][t] for c in xi_l)
                         + max((ep[c][t] for c in xi_l), default=0.0),
            # v12 W3 §4.5: not ``or None`` — a bank of exactly zero is a real
            # and common state (fully invested), and reading it as unknown
            # would send ``free_hit_gain`` back to today's figures on the very
            # weeks the plan spends everything.
            bank=(None if bank[t].varValue is None
                  else round(float(bank[t].varValue), 4)),
```

**F3 — `chips.py:8-10`.**

```
Free hit is the exception: it does not change the plan for later gameweeks
(the squad reverts), so it is scored as a single-gameweek swap rather than by
re-solving the horizon. Since v12 that swap is priced from the *baseline's*
position in the week the chip is played — its squad, its bank, its saved hits
— rather than from today's. See :func:`free_hit_gain`.
```

**F4 — `chips.py:175-206`**, the whole function:

```python
def free_hit_gain(pool: pd.DataFrame, state: SolveInput, gw: int,
                  base: Plan | None = None, **cfg) -> float:
    """The best unrestricted one-week squad in ``gw``, against the plan you
    would otherwise have played that week.

    ``base`` is the already-solved no-chip plan and must come from
    :func:`chip_baseline`; pass it to skip re-solving. Both solves are
    undecayed (see the module note) — the free hit is a one-week swap, so the
    discount only ever shrank a later week's chip against an earlier one.

    **v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md).** Two of the
    three understatements this function used to carry are gone:

    * the budget is the baseline's squad and bank *in that week*, not today's.
      Pricing a GW+3 free hit off a squad the plan has already sold out of was
      answering a question about a different team;
    * the baseline's hits in that week are credited back. A free hit suspends
      the week's transfers, so the points those transfers would have cost are
      saved by playing the chip — and ``expected_pts`` is gross of hit cost,
      so leaving them in made the chip look worth nothing exactly when it had
      just saved a -8.

    The third stays, and stays documented: a free hit also leaves your
    transfers and bank untouched for the rest of the horizon, which this
    number does not price. Doing so needs a two-branch horizon solve, and the
    spec asks for a true re-solve of the free hit *week*.

    A baseline whose week carries no readable bank — an older ``Plan``, a
    solver that returned no value — falls back to today's squad and bank,
    which is exactly the pre-v12 number, and says so on stdout rather than
    silently pricing a chip off a position nobody chose.
    """
    cfg = _eval_cfg(cfg)
    if base is None:
        base = solve_plan(pool, state, **cfg)
    base_week = next(g for g in base.gw_plans if g.gw == gw)
    hit_cost = int(cfg.get("hit_cost", 4))
    squad, bank = list(base_week.squad), base_week.bank
    if bank is None:
        print(f"free_hit_gain: the baseline plan carries no bank for GW{gw}; "
              f"pricing the chip off today's squad instead")
        squad, bank = list(state.owned_codes), float(state.bank)
    sell = dict(zip(pool["code"], pool["sell"]))
    budget = int(round(float(bank)
                       + sum(float(sell.get(c, 0.0)) for c in squad)))
    # free_transfers=15 just means "no transfer counts as a hit" when building
    # the squad from scratch; the FH squad is not bought, it is conjured.
    fh_state = SolveInput(owned_codes=[], bank=budget, free_transfers=15,
                          gws=[gw], locked_out=list(state.locked_out))
    fh = solve_plan(pool, fh_state, **cfg)
    baseline_week_net = base_week.expected_pts - hit_cost * base_week.hits
    return fh.gw_plans[0].expected_pts - baseline_week_net
```

**F5 — `advise.py:889-890`.**

```python
        for row in chip_rows:
            if row["chip"] == "freehit":
                # v12 W3 §4.5: no longer a lower bound on two counts — the
                # week's own squad and bank price it, and the hits it saves
                # are credited. What is still excluded is the horizon: a free
                # hit also leaves your transfers and bank untouched afterwards.
                row["note"] = "excludes horizon effects"
```

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_free_hit.py`:

```python
"""§4.5: the free hit is priced from the week it is played in.

Three claims, and the third is the one that moves a replay. The chip is scored
from the baseline's squad and bank *in that week* rather than today's; the
hits the baseline would have paid that week are credited, because a free hit
suspends them; and a baseline that cannot say what its bank was falls all the
way back to the pre-v12 number rather than to zero.

``GwPlan.bank`` is what makes the first possible, and it is a number the MILP
has solved for and discarded since v1.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.optimize.chips import chip_baseline, free_hit_gain
from gaffer.optimize.milp import GwPlan, Plan, SolveInput, solve_plan

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)
GWS = [1, 2]


def _pool() -> pd.DataFrame:
    rows, code = [], 1
    for pos, n in [("GKP", 4), ("DEF", 9), ("MID", 10), ("FWD", 7)]:
        for i in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": (code % 6) + 1,
                         "cost": 40 + i, "sell": 40 + i,
                         "ep": {g: 1.0 + (code % 7) * 0.3 for g in GWS}})
            code += 1
    return pd.DataFrame(rows)


def _state(**kw) -> SolveInput:
    base = dict(owned_codes=list(range(1, 16)), bank=150, free_transfers=1,
                gws=list(GWS))
    return SolveInput(**{**base, **kw})


def test_a_solved_week_now_carries_its_bank():
    plan = solve_plan(_pool(), _state(), **CFG)
    assert all(gp.bank is not None for gp in plan.gw_plans)
    assert plan.gw_plans[0].bank >= 0


def test_a_bank_of_zero_is_zero_and_not_unknown():
    """Fully invested is a real and common state; reading it as unknown would
    send free_hit_gain back to today's figures on the weeks that spend
    everything."""
    plan = solve_plan(_pool(), _state(bank=0), **CFG)
    banks = [gp.bank for gp in plan.gw_plans]
    assert None not in banks


def test_a_gw_plan_built_without_a_bank_still_builds():
    """Every positional and keyword construction in the tree, unchanged."""
    gp = GwPlan(gw=1, squad=[], xi=[], xi_rows=[], bench=[], captain=1,
                vice=2, buys=[], sells=[], hits=0, expected_pts=0.0)
    assert gp.bank is None


def test_the_gain_credits_the_hits_the_baseline_would_have_paid():
    """A free hit suspends the week's transfers, and expected_pts is gross of
    their cost — so leaving them in made the chip look worthless exactly when
    it had just saved a -8."""
    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    week = base.gw_plans[0]
    hit_free = Plan(objective=base.objective,
                    gw_plans=[__import__("dataclasses").replace(week, hits=0)]
                    + list(base.gw_plans[1:]))
    with_hits = Plan(objective=base.objective,
                     gw_plans=[__import__("dataclasses").replace(week, hits=2)]
                     + list(base.gw_plans[1:]))
    a = free_hit_gain(pool, state, 1, base=hit_free, **CFG)
    b = free_hit_gain(pool, state, 1, base=with_hits, **CFG)
    assert b - a == pytest.approx(2 * CFG["hit_cost"], abs=1e-6)


def test_the_budget_comes_from_the_baselines_week_and_not_from_today():
    """A baseline whose week holds a cheaper squad and more bank must price a
    different free hit from one that holds an expensive squad."""
    import dataclasses

    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    poor = dataclasses.replace(base.gw_plans[0],
                               squad=list(range(1, 16)), bank=0.0)
    rich = dataclasses.replace(base.gw_plans[0],
                               squad=list(range(1, 16)), bank=500.0)
    lean = free_hit_gain(pool, state, 1,
                         base=Plan(objective=0.0,
                                   gw_plans=[poor] + list(base.gw_plans[1:])),
                         **CFG)
    flush = free_hit_gain(pool, state, 1,
                          base=Plan(objective=0.0,
                                    gw_plans=[rich] + list(base.gw_plans[1:])),
                          **CFG)
    assert flush > lean


def test_a_baseline_with_no_bank_falls_back_to_todays_position_and_says_so(
        capsys):
    """The pre-v12 number, out loud. Silence here would price a chip off a
    position nobody chose."""
    import dataclasses

    pool, state = _pool(), _state()
    base = chip_baseline(pool, state, **CFG)
    stale = Plan(objective=base.objective,
                 gw_plans=[dataclasses.replace(base.gw_plans[0], bank=None)]
                 + list(base.gw_plans[1:]))
    free_hit_gain(pool, state, 1, base=stale, **CFG)
    assert "carries no bank for GW1" in capsys.readouterr().out


def test_the_lp_golden_still_matches(tmp_path):
    """Task 1's guard. Reading a solved variable adds no constraint."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state as st

    assert _capture_lp(tmp_path, st())[0] == GOLDEN.read_text()
```

- [ ] **Implement F1-F5** exactly as enumerated.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_free_hit.py tests/test_chips.py \
  tests/test_chip_sanity.py tests/test_milp.py tests/test_scenarios.py \
  tests/test_backtest.py tests/test_web_chips.py tests/test_advise.py \
  tests/test_v4c_degradation.py tests/test_v10_degradation.py \
  tests/test_v12_w3_force_out.py
.venv/bin/pytest -q
```

A `test_backtest` failure is **expected to be a value change, not a break**: the replay's chip choices depend on `free_hit_gain`'s number. If a backtest test asserts a specific FH gain, read whether the new number is right before touching the test, and if the test is a *protected* degradation file, **stop and report** — that would be a further authorization, not a fix.

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/milp.py src/gaffer/optimize/chips.py \
  src/gaffer/advise.py tests/test_v12_w3_free_hit.py && git commit -m "$(cat <<'EOF'
feat: the free hit is priced from the week it is played in

The one-week re-solve the spec asks for has been there since v2. What was
approximate is the position it solved from: today's squad and today's bank, for
a chip the table might be pricing three weeks out, by when the plan has already
sold out of half of it. It now solves from the baseline's own week — its squad,
its bank — which needed a number the MILP has solved for and discarded since
v1, so GwPlan carries its bank.

And the hits are credited. A free hit suspends the week's transfers, and
expected_pts is gross of hit cost, so a baseline that bought its way to a good
week made the chip look worth nothing exactly when it had just saved a -8.

One approximation stays and stays documented: a free hit also leaves your
transfers and bank untouched for the rest of the horizon. Pricing that needs a
two-branch horizon solve; the spec asked for a true re-solve of the free hit
week and this is one.

This is the only W3 item on the replay's path — evaluate_chips reaches
free_hit_gain from backtest — so the gate's delta, whatever it is, is this
change's.

v12 W3 §4.5 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edits to milp.py, chips.py and advise.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — **STOP** — the captain's ceiling is a probability again

**Files:**
- Modify `src/gaffer/optimize/differentials.py` — **PROTECTED**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Modify `src/gaffer/report/templates/report.html.j2`
- Modify `src/gaffer/web/routers/advice.py` (docstring only)
- Create `tests/test_v12_w3_dgw_captain.py`

> ### STOP
>
> **Do not start this task.** Report that Task 11 is ready, paste the enumeration, and wait for authorization to edit `differentials.py` and `advise.py`.

**Read A9 before starting.** The disclaimed number is `ep_matrix`'s `p_haul=("p_haul", "max")`, and `ep_matrix` is **not** edited: it is on the training and backtest hot path, and changing its aggregate would move every EP table in the tree for a display column.

### The complete enumeration

| # | File:lines (at `27f7933`) | Change |
| --- | --- | --- |
| D1 | `differentials.py:37-53` | `captain_table(..., haul=None)`; the ceiling column and the differential rule read it |
| D2 | `advise.py:57-58` | the import gains `bands_by_player_gw` |
| D3 | `advise.py:904-905` | the map is built for the advised gameweek and passed |

**D1 — `differentials.py:37-53`**, the whole function:

```python
def captain_table(ep: pd.DataFrame, xi_codes: list[int],
                  league_eo: dict[int, float], top: int = 5,
                  haul: dict[int, float] | None = None) -> pd.DataFrame:
    """Top captain candidates from the recommended XI with EV, ceiling and
    rival ownership.

    ``differential`` = rival EO under :data:`DIFFERENTIAL_EO` *and* an
    above-median ceiling among the shortlisted candidates. Both halves matter:
    a low-owned player with no ceiling is not a differential, it is just a bad
    captain.

    **The ceiling (v12 W3 §4.6,
    specs/2026-09-01-gaffer-v12-program-design.md).** ``haul`` is
    ``{code: P(total points >= 10)}`` from ``uncertainty.bands_by_player_gw``
    — the gameweek's whole point distribution, EP summed across a double
    gameweek's fixtures with the sweep's own sigma. Given one, the table
    carries it as ``p_haul_total`` and drops ``p_haul``.

    Dropping it is the point rather than a tidy-up. ``ep_matrix`` collapses a
    double gameweek with ``p_haul=("p_haul", "max")`` — *"takes the best single
    fixture rather than summing, since it is a probability"* — so on the exact
    week a captain matters most, the ceiling column was the better of two
    fixtures printed under the header ``P(2+ returns)``: a ranking number
    wearing a probability's label, and the number a doubled-up captain is
    chosen *for* was the one it could not show.

    Without a ``haul`` — or with one that covers none of the shortlist — the
    frame is exactly today's, ``p_haul`` and all, and a line says so. That is
    the rail: a component frame with no minutes model produces no bands, and a
    captain table is not worth failing over a ceiling.
    """
    df = _with_eo(ep[ep["code"].isin(xi_codes)], league_eo)
    df = df.nlargest(top, "ep").reset_index(drop=True)
    ceiling_col = "p_haul"
    if haul:
        mapped = df["code"].map(lambda c: haul.get(int(c)))
        if mapped.notna().any():
            df["p_haul_total"] = mapped
            df = df.drop(columns=["p_haul"])
            ceiling_col = "p_haul_total"
        else:
            print("captain_table: no shortlisted captain carries a points "
                  "band, so the ceiling stays P(2+ attacking returns)")
    ceiling = pd.to_numeric(df[ceiling_col], errors="coerce")
    df["differential"] = ((df["league_eo"] < DIFFERENTIAL_EO)
                          & (ceiling >= ceiling.median()))
    return df[["code", "name", "position", "ep", ceiling_col, "league_eo",
               "differential"]]
```

**D2 — `advise.py:57-58`.**

```python
from gaffer.models.assemble import apply_calibration, assemble_ep, ep_matrix
from gaffer.uncertainty import bands_by_player_gw
```

(placed with the other first-party imports, keeping the file's existing ordering).

**D3 — `advise.py:904-905`.**

```python
    ep_gw1 = ep_named[ep_named["gw"] == gw]
    # v12 W3 §4.6 (specs/2026-09-01-gaffer-v12-program-design.md): the ceiling
    # the captain table ranks on is the gameweek's own point distribution —
    # a double's two fixtures summed, under the sweep's sigma — and not
    # ``ep_matrix``'s best-single-fixture ``p_haul``, which in a double is the
    # better of two numbers printed as though it were the week's.
    #
    # ``bands_by_player_gw`` returns ``{}`` for a frame with no minutes model,
    # and ``captain_table`` then keeps today's column. Same frame the sweep
    # noises and the components panel bands: one answer per (code, gw).
    haul_by_code = {code: band.p_haul
                    for (code, band_gw), band in bands_by_player_gw(comp).items()
                    if band_gw == gw}
    cap_tab = captain_table(ep_gw1, first.xi, league_eo,
                            haul=haul_by_code or None)
```

### Steps

- [ ] **Write the failing test.** Create `tests/test_v12_w3_dgw_captain.py`:

```python
"""§4.6: the captain's ceiling is the gameweek's, not the better fixture's.

``ep_matrix`` collapses a double gameweek by summing EP and taking the
**max** p_haul, and says why in its own docstring: it is a probability, so it
cannot be added. That is right for the number it has and wrong for the question
the captain table asks — in a double, the ceiling printed under "P(2+ returns)"
was the better of two fixtures, which is a ranking number wearing a
probability's label, and the thing a doubled-up captain is picked for is
exactly what it could not show.

The replacement is not new arithmetic: ``uncertainty.bands_by_player_gw`` has
keyed on ``(code, gw)`` with EP summed across a double since v8g. This is a
re-wiring, and the tests are mostly about what happens when it is absent.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.optimize.differentials import captain_table


def _ep() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [1, 2, 3, 4, 5],
        "name": ["A", "B", "C", "D", "E"],
        "position": ["MID", "MID", "FWD", "DEF", "GKP"],
        "ep": [9.0, 8.0, 7.0, 6.0, 5.0],
        # The best-single-fixture ceiling: B looks the most explosive.
        "p_haul": [0.10, 0.40, 0.20, 0.05, 0.01]})


XI = [1, 2, 3, 4, 5]
EO = {1: 60.0, 2: 10.0, 3: 10.0, 4: 5.0, 5: 5.0}


def test_with_no_haul_map_the_table_is_the_table_it_was():
    out = captain_table(_ep(), XI, EO)
    assert list(out.columns) == ["code", "name", "position", "ep", "p_haul",
                                 "league_eo", "differential"]


def test_a_haul_map_replaces_the_column_rather_than_adding_one():
    """Two ceilings on one row is the v9c failure — two quantities under one
    heading — with the heading left ambiguous."""
    out = captain_table(_ep(), XI, EO,
                        haul={c: 0.3 for c in XI})
    assert "p_haul_total" in out.columns
    assert "p_haul" not in out.columns


def test_the_differential_rule_reads_the_new_ceiling():
    """A is heavily owned so is never a differential; between B and C the
    rule must follow the band, not the attacking p_haul that ranks B first."""
    haul = {1: 0.01, 2: 0.05, 3: 0.50, 4: 0.02, 5: 0.01}
    out = captain_table(_ep(), XI, EO, haul=haul).set_index("code")
    assert bool(out.loc[3, "differential"]) is True
    assert bool(out.loc[2, "differential"]) is False


def test_a_map_covering_nobody_leaves_the_old_column_and_says_so(capsys):
    """A component frame with no minutes model produces no bands, and a
    captain table is not worth failing over a ceiling."""
    out = captain_table(_ep(), XI, EO, haul={999: 0.4})
    assert "p_haul" in out.columns and "p_haul_total" not in out.columns
    assert "no shortlisted captain carries a points band" in \
        capsys.readouterr().out


def test_a_partially_covered_shortlist_keeps_the_new_column_with_nulls():
    """One player with no band is one blank cell, not a fallback for the
    table: the other four still have the honest number."""
    out = captain_table(_ep(), XI, EO, haul={1: 0.3, 2: 0.2}).set_index("code")
    assert out.loc[1, "p_haul_total"] == 0.3
    assert pd.isna(out.loc[5, "p_haul_total"])


def test_a_double_gameweek_captain_is_ranked_on_both_fixtures():
    """The whole point. Two 0.25 fixtures are a much better bet than one, and
    ``max`` could not say so."""
    ep = _ep()
    # C plays twice: ep_matrix summed his EP and took the better fixture's
    # p_haul (0.20). The band over the summed EP is far higher.
    out = captain_table(ep, XI, EO,
                        haul={1: 0.10, 2: 0.12, 3: 0.55, 4: 0.02, 5: 0.01})
    top_ceiling = out.sort_values("p_haul_total", ascending=False)
    assert int(top_ceiling.iloc[0]["code"]) == 3


def test_advise_builds_the_map_for_the_advised_gameweek_only():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "bands_by_player_gw(comp)" in src
    assert "if band_gw == gw" in src
    assert "haul=haul_by_code or None" in src
```

- [ ] **Implement D1-D3** exactly as enumerated.

- [ ] **Implement the report.** `report/templates/report.html.j2:90-95` — the header and the cell:

```jinja
<h2>Captain options</h2>
<table><tr><th>Player</th><th>Pos</th><th>xPts</th><th>P(10+ pts)</th><th>League EO%</th><th></th></tr>
{% for c in a.captain_options %}
{% set ceiling = c.get('p_haul_total', c.get('p_haul')) %}
<tr><td>{{ c.name }}</td><td>{{ c.position }}</td><td>{{ "%.2f"|format(c.ep) }}</td>
    <td>{{ "%.0f%%"|format(ceiling * 100) if ceiling is not none else "&mdash;"|safe }}</td>
    <td>{{ c.league_eo }}</td>
    <td>{% if c.differential %}<span class="diff">differential</span>{% endif %}</td></tr>
{% endfor %}</table>
<p><small>P(10+ pts) is the whole gameweek's point distribution — both fixtures
of a double, summed, at the model's own spread. An older report shows P(2+
attacking returns) here instead, which in a double gameweek was the better
single fixture's.</small></p>
```

The `<th>P(2+ returns)</th>` on the **differential alternatives** table (`:112`) is *not* changed: that table still carries `ep_matrix`'s attacking `p_haul` (§4.6 is about captaincy), and relabelling it would claim a change that was not made.

- [ ] **Implement the docstring correction.** `routers/advice.py:113-128`'s `HAUL_KEYS` note gains:

```python
    # v12 W3 §4.6: ``captain_options`` no longer carries ``p_haul`` at all —
    # its ceiling is ``p_haul_total``, ``uncertainty.Band.p_haul``, which needs
    # no rename because it was never the attacking one. The key stays in the
    # tuple: a banked payload written before v12 still has the old column, and
    # renaming it on the way out is exactly what this function is for.
```

No code changes: `_renamed` only touches dicts that carry `p_haul`, so a captain row without one passes through untouched.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_dgw_captain.py tests/test_differentials.py \
  tests/test_report.py tests/test_advise.py tests/test_web_advice_haul.py \
  tests/test_v9c_degradation.py
.venv/bin/pytest -q
```

`tests/test_v9c_degradation.py` is protected and builds its own `captain_options` payload carrying `p_haul`, so it pins the *rename*, not the producer, and must stay green. If it fails, the change reached further than the producer: **stop and report**.

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/differentials.py src/gaffer/advise.py \
  src/gaffer/report/templates/report.html.j2 \
  src/gaffer/web/routers/advice.py tests/test_v12_w3_dgw_captain.py \
  && git commit -m "$(cat <<'EOF'
feat: a captain's ceiling is the gameweek's, not the better fixture's

ep_matrix collapses a double gameweek by summing EP and taking the max p_haul,
and its docstring says why: it is a probability, so it cannot be added. Right
for the number it has, wrong for the question the captain table asks — printed
under "P(2+ returns)", the ceiling of a doubled-up captain was the better of
his two fixtures, which is a ranking number wearing a probability's label and
is silent about the exact thing he is being captained for.

The replacement already existed: uncertainty.bands_by_player_gw has keyed on
(code, gw) with a double's fixtures summed, at the sweep's own sigma, since
v8g. So this is a re-wiring, and ep_matrix is not touched — it is on the
training and backtest hot path and moving its aggregate for a display column
would re-price every EP table in the tree.

Absent a band the column stays exactly what it was, out loud. The alternatives
table keeps P(2+ returns), because that one really is still the attacking
number and relabelling it would claim a change nobody made.

v12 W3 §4.6 (specs/2026-09-01-gaffer-v12-program-design.md), orchestrator-
authorized protected edits to differentials.py and advise.py.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — the degradation rails and the pins (gate G1)

**Files:**
- Create `tests/test_v12_w3_degradation.py`

Every rail here is a state a real machine reaches, and three of them are the state *this* machine is in today: no priors asset in a fresh clone, no `chip_scenarios.toml`, no components frame.

- [ ] **Write `tests/test_v12_w3_degradation.py`.**

**Block 1 — §4.1's honesty.**
- An empty `force_out` builds the golden LP (imported from `tests/test_v12_w3_force_out.py`, so there is one golden and not two).
- A `force_out` naming a player outside the pool raises `GafferError` naming the code; the What-If validator refuses the same code with a 422 *before* the job runs.
- A forced-out player's sale credits the bank; a `locked_out` one's does not — the distinction, asserted rather than described.

**Block 2 — §4.2's honesty.**
- No priors asset (a cold clone) → every bar is the flat constant, every source string starts `flat:`, and `wildcard_now_assessment`'s verdict is the pre-v12 one.
- A priors asset covering everything → no bar anywhere is a flat constant (the sentinel sweep from Task 4, re-run here over `chip_plan` as well).
- A lookup with no `explain` → `unknown`, never a raise: an advice payload rendered through a stale lookup must still draw its chip table.

**Block 3 — §4.3's honesty.**
- `alt_plan_max_gap = 0` spends no solve (the monkeypatched `_solve_once` from Task 5).
- An artifact with no `alternative_plans` key serves `alternatives == []` and a full timeline — every payload on disk today.
- A malformed alternative costs a tab, not the board.
- `Plan()` still constructs with two arguments.

**Block 4 — §4.4's honesty.**
- **The shipped default is off**, so a fresh clone's advice run passes `p_play=None` and sweeps exactly as v11 did — the state W3 merges in, until the captain-support gate says otherwise.
- `draw_availability = False` reproduces the pre-v12 sweep on a fixed seed (imported assertion from Task 8, re-run here as a rail).
- `draw_availability = True` with an empty `p_play` prints the lever line and changes nothing.
- A player with no probability is never drawn out.

**Block 5 — §4.5's honesty.**
- No `chip_scenarios.toml` → `load_chip_scenarios()` is `{}` → the chip table carries no pair row and its columns are the five (`chip, gw, gw2, gain, per_week`). **This is the empty state spec §1 asks for**, and it is the state of every machine today.
- `gw2` is `None` and never `NaN` on a single-chip row.
- A `Plan` whose week carries no bank prices a free hit off today's position and says so.

**Block 6 — §4.6's honesty.**
- No components frame → `bands_by_player_gw` is `{}` → `captain_table` keeps `p_haul` and prints the reason; the report renders it through the fallback expression without raising.
- A captain with no band is an em dash in the report, never `0%`.

**Block 7 — the pins.**

```python
def test_the_job_kinds_did_not_move():
    """W3 adds no job. The alternatives are two more solves inside the advise
    run, which already has a kind — and a thirteenth would also need a row in
    ABANDON_TIMEOUT_S and SLOW_ABANDON_KINDS, pinned as jointly exhaustive in
    the protected test_v9d_degradation.py."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_gained_exactly_two_fields():
    """``[optimizer] alt_plan_max_gap`` and ``[scenarios] draw_availability``.

    48 at the program's spec commit (27f7933) and 50 here. **If W1 or W2 added
    keys, this number is their base + 2** — measure at the branch point, write
    it in, and say so in the commit message. Two is the claim; 50 is only the
    arithmetic on a base that may have moved.
    """
    import dataclasses

    from gaffer.config import Config

    assert len(dataclasses.fields(Config)) == 50


def test_the_route_total_did_not_move(tmp_path, monkeypatch):
    """45 at 27f7933 and unchanged by W3: the alternatives ride an existing
    payload and the chip pair rides an existing row. Pinned as a total *and*
    by absence, because a count alone would let a route be added and another
    removed in one cycle.

    **The absolute pin lives in the newest cycle's file** (v11 Task 11), so if
    a v12 W1/W2 file now carries it, this assertion moves here and out of
    there — check with the grep in the verify step below.
    """
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert len(paths) == 45
    assert not [p for p in paths
                if p.startswith(("/api/alternatives", "/api/forceout",
                                 "/api/support"))]
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w3_degradation.py
grep -rn "len(paths) ==" tests/          # exactly one hit, and it is the newest cycle's
.venv/bin/pytest -q
```

- [ ] **Commit** (`test: the W3 rails and the three pins`, staging only `tests/test_v12_w3_degradation.py`, with the standing trailers).

---

## Task 13 — the docs

**Files:**
- Modify `README.md`
- Modify `docs/GUIDE.md`
- Modify `config.example.toml` (if Tasks 5 and 8 left anything unsaid)

- [ ] **README** — five paragraphs, in the file's existing register, and the last two are residuals rather than features:
  1. **Must sell.** What it is, and what it is not (`ban`), and that the board's handoff now uses it.
  2. **Plan A / B / C.** That the gap is in objective points, that it can be negative, and that each alternative costs one MILP solve — with `[optimizer] alt_plan_max_gap = 0` named as the off switch.
  3. **The availability draw.** What it draws, that it ships **off** behind `[scenarios] draw_availability` until the captain-support gate has measured it, and that off is the pre-v12 sweep exactly.
  4. **Residual — `raw_optimum_agrees` reads False more often** (A6). The sweep now models availability the raw solve does not; the disagreement is information rather than instability, and the line on the report should be read that way.
  5. **Residual — the chip pair is data-gated** (A8): no `data/chip_scenarios.toml` means no `wildcard+bboost` row, and today there is no such file on any machine because the published fixture list has ten fixtures in every gameweek.
- [ ] **GUIDE** — one line in the What-If section naming the fourth constraint and its refusals, and one in the Planning section naming the plan tabs. No automation-table change: W3 adds no job and no plist.
- [ ] **Verify** the two config keys are documented where a reader will look:

```bash
grep -n "alt_plan_max_gap\|draw_availability" config.example.toml README.md
```

- [ ] **Commit** (`docs: what W3 changed, and the two things it left open`, staging only `README.md docs/GUIDE.md config.example.toml`).

---

## Task 14 — final verification and the gate checklist (orchestrator-run, unfilled)

**Files:**
- Modify `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` (§4's gate block)

CONVENTIONS §7: the implementer builds this and runs **G1 only**. Fill in the measured G1 numbers from your own final run; leave every G2 and G3 box unchecked.

- [ ] **G1 — suites, types, build, and the audits.**

```bash
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Baselines to beat: the re-measured branch counts from this plan's header (3193 Python and 655 frontend + 1 skipped at `27f7933`; re-measure at W3's base) plus this cycle's new tests, all green.

Then the protected diff — which is **not** expected to be empty in W3, and the point of the audit is that it contains exactly the nine authorized files and nothing else:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/jobs.py \
  src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
# EXPECTED, and nothing else:
#   src/gaffer/advise.py                 (Tasks 4, 6, 8, 9, 10, 11)
#   src/gaffer/optimize/milp.py          (Tasks 1, 5, 10)
#   src/gaffer/optimize/chips.py         (Tasks 4, 9, 10)
#   src/gaffer/optimize/chip_policy.py   (Task 4)
#   src/gaffer/optimize/scenarios.py     (Task 8)
#   src/gaffer/optimize/differentials.py (Task 11)
#   src/gaffer/web/routers/whatif.py     (Task 2)
# set_pieces.py, jobs.py, test_advise.py, test_odds.py, test_web_jobs.py and
# s2_replay.py must show NO diff at all.

git diff main --stat -- 'tests/test_*_degradation.py'
# test_v12_w3_degradation.py (new) and tests/test_v10_degradation.py (Task 8,
# authorized). Nothing else.

git diff main --stat -- 'data/**' 'reports/**' 'models/**' 'logs/**' \
  config.toml 'src/gaffer/web/static/**'
# must be empty
```

Every authorized hunk must carry its provenance comment:

```bash
git diff main -- 'src/gaffer/optimize/**' src/gaffer/advise.py \
  src/gaffer/web/routers/whatif.py tests/test_v10_degradation.py \
  | grep -c "v12 W3 §"
# one per line-group; compare against the enumerations in Tasks 1-11
```

And the pin audit:

```bash
git diff main --stat -- src/gaffer/web/job_kinds.py
# must be empty
git diff main -- src/gaffer/config.py config.example.toml
# exactly two new Config fields and their two documented keys
```

Security ritual (CONVENTIONS §8): grep the whole branch diff for keys and tokens, confirm no `data/`, `reports/`, `models/`, `logs/` or `config.toml` path appears in `git diff main --stat`, and confirm `git show main:config.toml` fails.

**No commit at this step.** The numbers go into the checklist below.

- [ ] **Write the checklist into the spec's §4 gate block**, G1 filled from the run above and every G2/G3 box unchecked:

```markdown
### W3 G1 — suites, rails, pins (measured by the implementer)

- [x] `.venv/bin/pytest -q` — <N> passed (branch baseline <B> + <new> new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — <N> passed, 1 skipped (baseline <B> + <new> new)
- [x] `npm run build` — clean
- [x] Protected diff is exactly the seven authorized source files plus
      `tests/test_v10_degradation.py`; `set_pieces.py`, `web/jobs.py`,
      `test_advise.py`, `test_odds.py`, `test_web_jobs.py` and `s2_replay.py`
      show no diff at all, and every authorized hunk carries `# v12 W3 §…`
- [x] Pins: job kinds 12 → 12, routes 45 → 45, config fields <base> → <base+2>
- [x] LP golden: an empty `force_out` and an absent `no_good` build the
      pre-change model byte for byte
- [x] Rails: no priors asset → every bar flat and every source says so; no
      `chip_scenarios.toml` → no pair row and a five-column table; the
      availability draw off → the pre-v12 sweep on a fixed seed; no components
      frame → the captain ceiling stays `p_haul` and says why; an artifact
      with no `alternative_plans` → an empty tab strip and a full timeline

### W3 G2 — the gates (orchestrator only)

**Pre-registered rules, written before any arm ran.**

- [ ] **The replay.** Three seed bases a side, branch against a re-run `main`
      (CONVENTIONS §1 — a banked number from an earlier cycle is not a valid
      comparison):

      ```bash
      mkdir -p logs
      caffeinate -i nohup bash scripts/replay_pair.sh v12w3 \
        > logs/v12w3_replay.log 2>&1 &
      grep -e V7B_ARM_DONE -e MULTISEED_DONE logs/v12w3_replay.log
      ```

      `SEEDS` defaults to `1876,1901,20260827`; both sides run
      `scripts/v7b_replay.py --arm heur --n 40 --chips`, differing only in
      `--tag`, which `scripts/seed_stats.py` verifies before it will aggregate.
      **Verdict:** the branch mean total is within **5** of the main mean, and
      the branch mean hits are not more than the main mean **+ 3** (spec §4).
      Read against the seed spread, which v7b measured at 116 points on one
      arm — a delta inside the spread is a seed, not a change.

      **What this gate can see, pre-registered so the result is not
      re-interpreted afterwards:** `backtest.py` reaches exactly one W3 change,
      `free_hit_gain` (via `evaluate_chips`). `force_out` is never set, θ was
      already wired into `_pick_chip`, the alternatives are computed in
      `advise`, the availability draw needs a `p_play` the replay's gate does
      not pass, and the chip pair needs a `dgw_gws` no caller but `advise`
      supplies. **So this is a measurement of §4.5 and a no-regression check on
      the other five** — v10's G2, demoted the same way and for the same kind
      of reason.

- [ ] **The captain-support check (§4.4).** On the live board, after an
      `advise` run:

      ```bash
      mkdir -p logs && caffeinate -i nohup .venv/bin/python \
        scripts/v12_w3_support.py > logs/v12_w3_support.log 2>&1 &
      grep -e W3_SUPPORT_LEVER -e W3_SUPPORT_DONE logs/v12_w3_support.log
      ```

      **Verdict:** `drop_pts <= 10`. The number is S1's failure signature —
      captain support 92% → 22%, after which the gate found no move clearing
      threshold and advised a plan carrying −20 in hits — watched for by name.
      A `W3_SUPPORT_LEVER` line must appear first; without it the run measured
      two identical arms and is void.

      **The arm ships OFF and this gate is what turns it on** (CONVENTIONS §6,
      orchestrator ruling 2026-09-02). W3 merges with
      `[scenarios] draw_availability = false` and `Config.draw_availability =
      False`, so no user's advice has drawn availability at the moment this
      runs.

      **If it passes:** flip four things in one commit — the `Config` default,
      the `load_config` default, `config.example.toml`, and the two
      expectations in
      `tests/test_v12_w3_availability.py::test_the_config_key_defaults_off_and_reads_from_the_scenarios_section`
      / `::test_the_shipped_default_leaves_the_advice_path_on_the_pre_v12_sweep`
      — and record the measured `support_off` / `support_on` / `drop_pts` in
      this spec beside the rule.

      **If it fails:** it stays off, and the negative result is recorded here
      anyway. Deleting the arm loses the measurement that cost the hours; the
      feature stays in the tree, stays tested, and stays off.

- [ ] Zero unauthorized protected diffs (G1's audit, re-run on the merge).

### W3 G3 — review and merge (orchestrator only)

- [ ] Adversarial review, fix-first, re-verify.
- [ ] Merge ritual: ff-only, push, `git show main:config.toml` fails, key-grep
      empty.

### Live spot-checks (orchestrator, on the dev server)

- [ ] Planning → Board: "Try these changes" lands on What-If with the week's
      sells in **Must sell** and its buys in Force in, `ban` empty, and the
      sentence under the button no longer says a sell rules out buying him
      back.
- [ ] What-If: a Must sell on a player you do not own is refused inline with
      "use ban"; on a free hit it is refused as "nothing to force out".
- [ ] Planning → Board: with alternatives banked, Plan A / B / C switch, the
      gap sentence names objective points, and the moves that differ from Plan
      A are marked. With none banked, no strip is drawn at all.
- [ ] Planning → Chips: every bar carries θ or `flat`, and "Wildcard now"
      names the bar its verdict was decided against — the two must agree about
      the wildcard, which before this cycle they did not.
- [ ] The chip table shows **no** `Wildcard + Bench Boost` row on today's
      fixture list, which is the correct empty state and not a bug.
- [ ] The HTML report's captain table reads `P(10+ pts)`, a candidate with no
      band reads as an em dash rather than 0%, and the alternatives table below
      still reads `P(2+ returns)`.
```

- [ ] **Commit the checklist** (`docs: v12 W3 gate checklist with the measured G1 numbers, G2/G3 unfilled`, staging only the spec file, with the standing trailers).

---

## Task 15 — the ROADMAP

**Files:**
- Modify `docs/superpowers/ROADMAP.md`

Keep the file's entry style exactly: `### <name> — <summary> (in progress, branch \`<branch>\`)`, a `Spec: … · Plan: …` line, `- [ ]` bullets, a `- Residuals:` line, a `- Pins:` line.

- [ ] **Add the W3 entry** below W2's, in progress:

```markdown
### v12 W3 — decide (in progress, branch `feat/gaffer-v12-w3`)
Spec: `specs/2026-09-01-gaffer-v12-program-design.md` §4 (§W3 gate = G1/G2/G3) · Plan: `plans/2026-09-01-gaffer-v12-w3-decide.md`
- [ ] §4.1 `force_out`: the constraint the vocabulary was missing — v11's board carried a planned sell across as `ban`, which also forbade the buy-back and never credited the bank. Four refusals rather than a constraint that applies to nobody, and an LP-level regression guard: the built model is written out and compared byte for byte against a golden captured before the field existed
- [ ] §4.2 θ is the only chip decision: the flat bar was consulted in exactly one live place, `wildcard_now_assessment`, in the same run that priced the same wildcard against θ three lines earlier. Both threshold factories now report *why* a bar is what it is, which a bare callable could not
- [ ] §4.3 top-3 distinct plans: no-good cuts in the MILP, `Plan.alternatives` on the artifact, tabs on the board. The gap is an **objective** gap (the frame the plans were chosen in) and it is **signed** — the recommendation carries the sweep's moves and an alternative does not, so an alternative can be ahead
- [ ] §4.4 availability-aware sweep: a Bernoulli on `p_play` per scenario, from its own generator, with the normal drawn for every cell either way — so off is off to the byte and the two arms differ in the zeroing alone. **Ships OFF behind `[scenarios] draw_availability`** until the captain-support gate has measured it (CONVENTIONS §6), so W3 merges with nobody's advice drawing availability. **Narrows a protected v10 rail** (T10-A pinned that the sweep never sees `p_play`; the claim it needed was that no scenario is *solved* under §F1's weights)
- [ ] §4.5 chip pairs and a real free hit: WC+BB as one option, **data-gated** — no `data/chip_scenarios.toml` means no pair row, and today no machine has one. The free hit was already a re-solve; what was wrong was solving it from today's squad and bank rather than from the baseline's own week, and not crediting the hits the chip saves. `GwPlan` now carries the bank the MILP has always solved for and thrown away
- [ ] §4.6 DGW captain: the disclaimed ranking number was `ep_matrix`'s best-single-fixture `p_haul`, printed under `P(2+ returns)`; the ceiling is now the gameweek's own point distribution, which `uncertainty.bands_by_player_gw` has computed since v8g. `ep_matrix` untouched — it is on the training path
- [ ] Gate: 2025-26 gated replay, three seeds a side, tolerance 5 and hits ≤ +3 — **which sees §4.5 and no-regresses the other five**, because `backtest.py` reaches only `free_hit_gain`; plus §4.4's captain-support check (drop ≤ 10 points, S1's failure signature by name)
- Pins: job kinds 12 → 12, routes 45 → 45, config fields **+2** (`alt_plan_max_gap`, `draw_availability`)
- Data-gated: `wildcard+bboost` needs `data/chip_scenarios.toml` to carry a `[dgw]` entry — the writer refuses to create one while every published gameweek has ten fixtures, so this unblocks at the first real rearrangement
- Residuals: `raw_optimum_agrees` reads False more often with the availability draw on, because the sweep now models a risk the raw solve does not — information rather than instability, and the README says so; the free hit still excludes horizon effects (pricing them needs a two-branch horizon solve); alternatives cost one MILP solve each on every weekly advise run
```

- [ ] **Verify.**

```bash
grep -n "^### v12 W3" docs/superpowers/ROADMAP.md
```

- [ ] **Commit** (`docs: open v12 W3 on the roadmap`, staging only `docs/superpowers/ROADMAP.md`, with the standing trailers).

---

## Notes for the implementer

- **Task order has six constraints and is otherwise free.** T1 → T2 → T3 (the field, then the wire, then the screen). T5 → T6 → T7 (the cuts, then the artifact and the endpoint, then the tabs). T4 → T9 and T4 → T10 only in the weak sense that all three edit `chips.py` and sequencing them avoids a merge you have to think about. T12 goes last of the code tasks; T13-T15 are docs and go after it. **Nine of the fifteen are STOPs** and each needs its own authorization — batch the enumerations to the orchestrator if that is easier, but do not start any of them on the strength of another's approval.
- **Nine STOPs is not nine chances to widen the diff.** Every one of them names its files and its line-groups. If a task finds it needs a tenth file, that is a STOP of its own and a report — not a hunk added to an approved list.
- **The single most valuable artifact in this cycle is a 37KB text file.** `tests/data/v12_w3_milp_golden.lp` is the only thing standing between "the empty case adds no constraint" and "the empty case appears to add no constraint". Generate it *before* the first edit to `milp.py`, and if it ever fails after an `optimize` change, the change is the suspect — regenerating it is how the guard is thrown away rather than how it is fixed.
- **Two protected source-text rails count things in `advise.py`** and this cycle passes near both. `p_play=p_play_by_code` must still appear exactly twice (Task 6's `weighted` bundle is why), and `test_v10_degradation`'s sweep-call assertion is deliberately rewritten in Task 8 rather than dodged. Run `grep -c "p_play=p_play_by_code" src/gaffer/advise.py` after every `advise.py` edit; if it reads 3, you have re-broken a rail that was never about your change.
- **`backtest.py` is import-only and that is doing real work here.** Two features are safe *because* it does not opt in: the chip pair (whose name its executor has no branch for) and the availability draw (whose `p_play` its gate does not pass). If a later cycle wires either into the replay, both need an execution path first — the pair especially, which would otherwise be recorded as played and applied to nothing.
- **Four null conventions are in play and none is interchangeable.** `GwPlan.bank`'s 0.0-is-fully-invested (Task 10), `PlanAlternative.gap`'s 0.0-is-exactly-level (Task 6), `field_eo`'s never-0.0-for-unknown (v11), and the graded counter's never-measured-is-not-never-wrong (v11). A review comment proposing that any of them default to zero "for the type's sake" is proposing the bug the convention exists to prevent.
- **The empty state is the main case in three of the six items**, and on today's data it is the *only* case for one of them. No `chip_scenarios.toml` means the WC+BB row cannot appear on any machine right now. Build that state first, test it hardest, and if a live check shows a pair row, something is wrong with the fixture list rather than right with the season — check before celebrating. This is v10b's fixture outlook and v11's empty dashboard for the third time.
- **The gate measures one item.** Say so out loud in the G2 write-up rather than letting a green replay read as six features validated. v10's G2 did exactly this and the honesty is why its result is still readable a cycle later.
