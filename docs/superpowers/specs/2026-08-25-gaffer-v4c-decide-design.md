# Gaffer v4c "decide" — design

Date: 2026-08-25 · Cycle: v4c of the v4 roadmap (`docs/superpowers/ROADMAP.md`)
· Research basis: `docs/superpowers/research/2026-08-25-improvement-research.md`
findings 1 (scenario re-solving), 4 (chip stopping thresholds), 5 (FT shadow
prices) · Prior cycles: v4a measured (planning_ceiling ≈ 175 pts/season,
chip timing worth 10–25 pts), v4b closed forecast gaps.

## 1. Goal

Improve the *decision* layer around a forecast we now trust: stop acting on
a single estimation-error-maximizing optimum, price free transfers and hits
by their real marginal value, and time chips against the season instead of a
flat threshold. The optimizer's MILP itself barely changes; v4c wraps it.

Decisions locked in brainstorming: **N ≈ 40** noised solves per advise run
(~5 min budget); **frequencies decide** — the advice recommends moves that
survive a sim-share threshold, with a higher bar for irreversible moves, and
the raw optimum demoted to one informational line; **replay-calibrated
tables** feed both the chip thresholds and the FT shadow prices (offline
precompute, shipped as an asset, cheap at advise time).

## 2. What exists today (integration seams)

- `src/gaffer/optimize/milp.py` — `solve_plan(pool, state, *, decay,
  bench_weight, vice_weight, ft_value, itb_value, hit_cost) -> Plan`.
  Multi-period MILP over the horizon: squad/XI/captain/vice/transfers, FT
  banking, hits. Flat `ft_value = 1.5`, uniform `bench_weight = 0.10`,
  `itb_value = 0.05` (config defaults in `src/gaffer/config.py`).
- `src/gaffer/optimize/chips.py` — chips scored *undecayed* against a
  no-chip baseline; flat trigger constants incl. `CHIP_PLAY_THRESHOLD =
  4.0`; `evaluate_chips`, `free_hit_gain`, `wildcard_now_assessment`,
  `chip_plan`.
- `src/gaffer/optimize/differentials.py` — EO-aware tables (v4d's ground;
  untouched this cycle).
- `src/gaffer/advise.py` `run_advise` — one deterministic solve; protected
  source-text orderings: `ep_matrix(apply_calibration(assemble_ep(`
  (test_assemble), `blend_team_odds(` before `comp.merge(tp` (test_odds),
  `fetch_rival_entries(` < `tilt_ep(` < `pool = build_pool(` with literal
  `build_pool(players, pool_ep,` (test_advise). The scenario layer consumes
  the pool EP **after** all three, so every literal survives.
- `src/gaffer/backtest.py` — replay harness (`run_backtest`,
  `run_decomposition`); the source of the calibration tables and the venue
  for this cycle's gates.
- Minutes model outputs `p_play`/`p60` per player-GW — the xMins source for
  noise scaling.

## 3. Workstream 1 — scenario re-solving (`optimize/scenarios.py`)

- `noise_ep(ep_matrix, xmins, rng) -> ep_matrix`: per player-GW cell,
  additive noise `ep × (92 − xmins) / 134 × N(0, 1)` (the community
  standard: nailed-on starters wobble least, rotation risks most).
  `xmins = 90 × p_play × p60 + 45 × p_play × (1 − p60)` clipped to [0, 92],
  computed from the component frame already in scope in `run_advise`.
  Noise is drawn once per scenario per player-GW (no cross-GW correlation —
  YAGNI until measured to matter).
- `run_scenarios(pool_ep, state, n, seed, **solve_cfg) ->
  list[Plan]`: n solves of the existing `solve_plan`, each on a noised
  copy. Deterministic under a fixed seed (seed logged in the report). Runs
  sequentially; ~40 × current solve time fits the ~5 min budget. If a
  scenario solve fails, it is dropped and counted — 39/40 is a report line,
  not an error.
- `move_frequencies(plans) -> DataFrame`: per candidate move, the share of
  scenarios containing it. Move kinds: buy X (first horizon week), sell Y,
  hit taken in week t, chip C in week t, captain Z, and "no transfer this
  week". Keyed to survive plan-shape differences (a buy counts whether it
  happened alone or inside a double move).
- The deterministic solve (seedless, un-noised) still runs first and is
  kept: it anchors the report ("raw optimum") and remains the fallback if
  scenarios are disabled (`[scenarios] n = 0`).

## 4. Workstream 2 — decision policy (`optimize/policy.py`)

- `decide(frequencies, raw_plan, thresholds) -> Advice`: the headline
  recommendation is assembled from moves that clear their threshold:
  - transfers (reversible): ≥ 60% of scenarios,
  - hits, chips, wildcard (irreversible): ≥ 75%,
  - captain: plurality winner (always recommend one).
  Below threshold → the advice is "hold" (roll the FT) with the
  nearest-miss moves listed with their frequencies. Thresholds live in
  config (`[scenarios] transfer_threshold / irreversible_threshold`) with
  those defaults.
- Consistency rail: a recommended buy needs a recommended sell (or free
  slot) — the policy recomposes a *coherent* plan from threshold-passing
  moves by re-solving once with the passing moves fixed as constraints
  (the existing MILP accepts forced moves via bounds on the transfer
  variables; if it does not yet, this cycle adds `fixed_moves` to
  `solve_plan`'s signature as optional, defaulting to none). That re-solve
  is the plan the report shows.
- Report/UI: CLI advice leads with the frequency-gated plan + "% of sims"
  per move; the raw optimum becomes one line ("single-solve optimum
  agreed / differed: …"). Web: frequency column in the advice table, and
  the API schema gains the fields (`frequency`, `gated: bool`,
  `raw_optimum_agrees: bool`).

## 5. Workstream 3 — FT/hit shadow price λ(k,t) (`optimize/ft_value.py`)

- Small DP over states (k = FTs held 1..5, t = GWs remaining): each week an
  FT arrives (cap 5, overflow lost), spending opportunities are draws from
  the *transfer-surplus distribution* (see §7). Value iteration backward
  from season end gives `V(k, t)`; the shadow price is
  `λ(k, t) = V(k, t) − V(k−1, t)` — the marginal value of holding the k-th
  transfer with t weeks left.
- Consumption:
  - `solve_plan`'s flat `ft_value` is replaced by a per-week banked-FT
    value read from the λ table at the solver's (k, t) — implemented as a
    new optional `ft_lambda` argument (a lookup callable/table) with the
    flat `ft_value` retained as fallback when no table is shipped.
  - Hit rule: a hit is worth taking when horizon gain > `hit_cost +
    λ(k, t)`; this lands automatically once the objective prices banked FTs
    by λ, and the policy layer's 75% bar sits on top.
  - `wildcard_now_assessment` subtracts the FT-bank value the wildcard
    destroys (`Σ λ` of the banked transfers reset by playing it).
- λ table shape: `{(k, t): float}`, precomputed offline (§7), shipped as
  `src/gaffer/assets/decision_priors.json`, loaded like other assets.
  Expected shape per the research: `{2: ~2.0, 3: ~1.6, 4: ~1.3, 5: ~1.1}`
  early-season, decaying toward 0 late — the calibration must reproduce
  that *qualitatively* or the gate fails (§9).

## 6. Workstream 4 — chip stopping thresholds θ_t (`optimize/chip_policy.py`)

- Per chip half (WC1/WC2, FH, BB, TC × the GW1–19 / GW20–38 windows):
  `θ_t = E[max over remaining weeks of that chip's surplus]`, computed by
  backward recursion `θ_T = 0; θ_t = E[max(S_{t+1}, θ_{t+1})]` over the
  replay-calibrated per-week surplus distributions (§7), DGW/BGW upweighting
  entering through those distributions.
- Play rule: play the chip in week t iff this week's measured chip surplus
  (the existing `evaluate_chips` machinery, unchanged) ≥ `θ_t` — replacing
  the flat `CHIP_PLAY_THRESHOLD`/`WILDCARD_*` constants. θ_t declines to 0
  at each expiry by construction, so a chip is never stranded.
- Scenario-file hook: `data/chip_scenarios.toml` (optional, absent today) —
  per-GW probability-weighted fixture scenarios (Crellin-style, available
  ~Jan). When present, future-week surplus distributions are shifted by the
  DGW probability mass; when absent, the replay table alone (which already
  contains historical DGW weeks) is the prior. The hook is the mechanism;
  populating it is a January follow-up, out of this cycle's scope.
- Report: the chip table gains "threshold now" and "play iff ≥" columns and
  the UI chip card shows surplus-vs-θ_t as a gauge.

## 7. Calibration: `gaffer calibrate-decisions` (offline command)

- One command produces `assets/decision_priors.json` holding both tables:
  - **Transfer-surplus distribution** per season-phase (early/mid/late
    thirds): from replays of past seasons, the distribution of `best
    single-transfer gain` per week (the existing backtest machinery already
    computes plans; the calibrator replays with 1 FT and records the
    optimal-transfer EP delta per week).
  - **Chip-surplus distributions** per chip per week-of-season: replay
    `evaluate_chips` gains over 2023-24…2025-26 (three seasons, including
    DGW/BGW weeks so the tail is real).
- Runs under `caffeinate -i`, ~one backtest-length job, refreshed rarely
  (per season, or when the model shifts materially). The asset ships in
  git so a fresh clone decides sensibly without ever running it.
- Degradation rail: no asset → flat `ft_value` and flat chip thresholds,
  i.e. exactly today's behaviour (regression-tested, as in v4b).

## 8. Workstream 5 — objective craft (`milp.py` + config defaults)

- Convex bench weights `{GK+1st: 0.21, 2nd: 0.06, 3rd: 0.002}` replacing
  uniform 0.10 (autosub reality: the first bench slot plays often, the
  third almost never). Implemented as ordered bench slots in the objective
  only — no new constraints (bench ORDER is not modelled; the weight
  applies to the 1st/2nd/3rd highest-EP bench players).
- `itb_value` default 0.05 → 0.08 per £1m (O'Brien's measured £1m ≈ +21.8
  pts over half a season).
- `ft_use_penalty = 0.2`: tiny friction per transfer made, discouraging
  EP-neutral churn the noise would otherwise flip weekly. New config knob.
- All three are config-defaulted, overridable, and included in the replay
  gate (§9) rather than taken on faith.

## 9. Evaluation & merge gates

All replays over 2025-26 GW5–38 (the v4a decomposition venue), model EP:

- **Gate D1 (scenarios/policy)**: frequency-gated advice replay total ≥
  raw-optimum replay total. Also report: how often the gate held moves back
  (expected: fewer transfers, fewer hits), and captain agreement rate.
- **Gate D2 (λ + objective craft)**: replay with λ-priced FTs + new
  objective defaults ≥ replay with flat values; hits taken should drop or
  hold with total not worse. λ table must be qualitatively sane
  (monotone decreasing in k, decaying in t).
- **Gate D3 (chip thresholds)**: replay chip timing with θ_t vs the flat
  thresholds; chip-attributed points not worse, and no chip stranded
  unplayed at expiry in any replay. Honest prerequisite: the backtest has
  been chip-free since v1, so this cycle adds chip play to the replay
  harness (`run_backtest(chips=True)`) — that extension is itself part of
  the plan, and D3 is measured on it.
- Wall-clock: `gaffer advise` with N=40 completes ≤ ~6 min on this machine.
- Global: full suites green; the three protected source-text tests
  untouched; `[scenarios] n = 0` path byte-identical to pre-v4c advice
  (degradation rail test).
- Failure handling: any gate failing → that workstream ships behind its
  config flag defaulted off, negative result recorded here.

## 10. Not in this cycle

- Populating the DGW scenario file (needs Crellin data, ~Jan) — hook only.
- EO-aware captaincy / z risk dial / rival covering — v4d.
- Cross-GW-correlated noise, opponent-modeling in scenarios — YAGNI until
  the simple noise proves insufficient.
- Bench-order modelling in the MILP (weights approximate it).

## 11. Testing strategy

TDD throughout. Units: noise scaling (zero for xmins=92, max for 0;
deterministic under seed); frequency aggregation (double moves, DGW weeks,
dropped scenarios); policy thresholds incl. the coherence re-solve and
"hold" fallback; λ DP on hand-checkable toy distributions (k monotonicity,
t decay, cap-5 overflow); θ recursion on toys (θ_T=0, monotone decline,
E[max] ≥ E); calibrator output schema; degradation rails (no asset, n=0).
Integration: replay-based gates above; a full advise run against fixtures
with n=4 in CI-speed tests.

## 12. Outcome

(Filled as gates are measured; completed at cycle end.)

### Gate D1 — scenarios and policy (2026-08-25): PASS

Replay 2025-26 GW5–38, horizon 3, N=40, seed 20260825+gw, thresholds
60%/75%. Driver: throwaway `scripts/d1_gated_replay.py` monkeypatching the
replay's `solve_plan` (deleted after recording, per plan Task 12).

| | raw optimum | gated (flat 60′ xmins) | gated (real xmins) |
| --- | --- | --- | --- |
| replay total | 1743 | 1711 | **1818 (+75)** |
| transfers made | 56 | 58 | 50 |
| hits taken | 23 | 27 | 18 |
| weeks held (gate blocked all moves) | n/a | 6/34 | 4/34 |
| captain agreement rate | n/a | 23/34 | 28/34 |

The first run used the plan's flat 60-minute xmins stub and FAILED (−32,
*more* transfers and hits). Diagnosis: flat 60 gives a nailed-on starter
(92−60)/134 ≈ 24 % EP noise where production advise gives him ~1.5 %, so
captaincy plurality and premium-move frequencies were computed under wildly
inflated noise on exactly the players that decide the total (captain
overridden 11/34 weeks). The driver was amended — zero product-code change —
to stash the component frame the replay already computes each week and derive
xmins exactly as `run_advise` does (`real_xmins_weeks: 34/34`). With honest
noise the gate does what it was designed to do: fewer moves, fewer hits, more
points. `[scenarios] n = 40` set in `config.toml`.

Method caveat: single seed, one season. The flat-stub run doubles as an
unplanned sensitivity check — the gate's value depends on the noise model
being minutes-aware, which production is.

### Calibration (2026-08-26): asset shipped

`gaffer calibrate-decisions` over 2022-23…2025-26: 131 transfer-surplus
samples (medians 3.83 / 4.45 / 6.40 early/mid/late). λ strictly decreasing in
k, decaying in t (λ(1..5, t=33) = 14.06 / 9.14 / 7.17 / 5.83 / 4.51); θ
non-increasing within each half, exactly 0.0 at GW19 and GW38 for all four
chips. Levels run ~4.5× the research sketch because samples are 3-GW-horizon
objective deltas, not single-week gains — recorded, and D2/D3 measured the
levels as shipped. Note: the λ DP is the multi-spend harmonic-value recursion
(the plan's original recursion was degenerate — one spend per week against
one arrival per week means a banked FT beyond the first never binds and
λ(k≥2) ≡ 0; deviation reviewed and accepted).

### Gates D2 and D3 (2026-08-26): both PASS

Replay 2025-26 GW5–38, horizon 3, chips on, four arms (θ/λ isolation via
driver monkeypatch, zero source edits):

| replay | total | hits | transfers | chip points | chips stranded |
| --- | --- | --- | --- | --- | --- |
| flat baseline | 1810 | 18 | 70 | 432 | none |
| λ + objective only | 1814 | 16 | 66 | 428 | none |
| θ only | **1883** | 12 | 64 | **555** | none |
| both | 1796 | 14 | 65 | 479 | none |

**D2 PASS**: λ+objective 1814 ≥ 1810 with hits 16 ≤ 18. **D3 PASS**: θ chip
points 555 ≥ 432 (+123, every chip better-timed: freehit GW19/33, wildcard
GW34+, bboost GW36, 3xc GW38), no chip stranded in any arm. θ is the
cycle's single biggest win: +73 total on its own.

**Recorded anomaly**: the both-on arm (1796) underperformed the baseline and
both isolated halves — λ and θ interact negatively (the suspected mechanism
is the flagged double-count: a non-empty `ft_lambda` re-prices the terminal
FT bank inside the chip-evaluation solves on top of the wildcard's explicit
FT-bank deduction, making chip weeks look worse exactly when θ is willing to
wait for them). Per spec §9's rule both halves ship on (each passed its own
gate); the interaction is a named candidate for the next measurement cycle,
and single-seed noise (±~30 pts) cannot rank 1796 vs 1810 with confidence.
Defaults set: `decision_priors = true`, `itb_value = 0.08`,
`ft_use_penalty = 0.2`, `bench_curve = [0.21, 0.06, 0.002]`.

### After-photo (2026-08-26)

Suites: 923 Python (from 721 at cycle start) + 62 frontend, `npm run build`
clean. Degradation rail green (n=0 CLI output byte-identical; solve_plan
objective identity under all four new arguments at their defaults). All four
protected source-text suites untouched and green. Timed live advise with the
full stack on (n=40, priors, crafted objective): **68 s wall-clock** against
the ≤~6 min budget; 40/40 scenarios solved, frequencies rendered in CLI and
web, raw optimum demoted to one line.

Corrections to this spec discovered during the cycle: (1) §9's D3
prerequisite was wrong — the backtest has accepted `chips=True` since v1
(now pinned by `test_run_backtest_already_accepts_the_chips_flag`); the real
gap was `unplayed_chips` reporting, added in Task 22. (2) §5's λ recursion
was degenerate as sketched (see Calibration note above).

Observed behaviour worth a future look: the coherence re-solve may take hits
the 75 % gate declined when completing forced buys (seen live: two forced
buys → −8 hits with `hit` at 57 %). Measured net-positive inside D1's +75,
but "gate the completion's hits too" is a candidate refinement. Deferred
alongside: per-phase λ states (the DP pools phases, t already implies
phase); DGW `chip_scenarios.toml` population (~Jan, Crellin files).

### Final adversarial review (2026-08-26): FIX-FIRST → fixed → re-measured

The reviewer found 8 blockers; all fixed (commits 4b11dc7..b12d8a1), suite
923 → 944. The material ones, with their measurement consequences:

1. **Production advise never passed `ft_use_penalty`/`bench_curve` to the
   solver** — D2's "λ+objective" arm measured an objective the live tool
   didn't use. Fixed; advise re-timed at 62.8 s with the full objective.
2. **Wildcard was double-charged for its FT bank** — `wildcard_now_assessment`
   subtracted `bank_value` (up to ~40 pts) while the MILP (correctly, per
   post-2024-25 rules) models the bank as surviving. Deduction deleted.
   **This was the λ×θ anomaly's mechanism, confirmed by re-measurement**
   (below): it suppressed replay wildcards exactly when θ was willing to
   wait.
3. **The calibrator was contaminated and mislabeled**: its "single-transfer
   surplus" included multi-transfer hit-taking weeks (a golden-pool case
   sampled 132.0 where the true one-FT gain was 22.0), it fed on its own
   previous asset, and this section's earlier "3-GW-horizon deltas" (**withdrawn**)
   explanation of the ×4.5 λ levels was wrong — `walk_season` replays at
   horizon 1. Fixed (spent solve capped at one transfer/no hits; calibration
   replay blinded to the asset) and regenerated: medians 3.48/4.11/5.64 with
   means now adjacent (3.96/5.01/6.04, max 20.9 vs 55.2); λ(1,33) 14.06 →
   5.84, concave and decaying.
   Also fixed: hold-infeasibility on an empty opening squad; a captain
   frequency printed against the wrong player; the What-If baseline not
   re-pricing with the priors; tautology tests replaced with real pins
   (golden objective 56.34025, `bank_value` concavity, product-code chip
   attribution).

Re-measured D2/D3 (same flat baseline A — none of the fixes touch the
priors-off path):

| replay | total | hits | transfers | chip points | chips stranded |
| --- | --- | --- | --- | --- | --- |
| flat baseline | 1810 | 18 | 70 | 432 | none |
| λ + objective only | 1853 | 12 | 63 | 421 | none |
| θ only | 1883 | 12 | 64 | 555 | none |
| both | 1865 | 10 | 64 | 521 | none |

**D2 PASS with real margin** (+43, hits 12 vs 18 — pre-fix it scraped by at
+4). **D3 PASS unchanged** (θ path had no λ in it). **Anomaly resolved**:
both-on went 1796 → 1865, now +55 over baseline with the fewest hits of any
arm; the residual −18 vs θ-alone is within single-seed noise and stands
recorded. Live advise sanity: 40/40 scenarios, raw optimum agrees, one hit
(−4) with every executed move above its bar, 62.8 s.

Still open (recorded, non-blocking): θ calibrated at horizon 1 but consumed
at horizon 3 (wildcard bar ~⅓ of the compared quantity); ~4 chip-surplus
samples per week make θ_t noisy; the 60/75 % `hit` and `chip` gate outputs
are non-binding on the completion (the chip frequency channel is dead until
scenario plans carry chips); the n=0 byte-identity rail pins the CLI print
block, not the report JSON (chip rows now always carry θ columns).
