# gaffer v8g — honest uncertainty

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 6 of 7). Lean cycle.
Goal: show the model's uncertainty the way a forecaster would — calibration evidence, EP bands and haul/blank probabilities where decisions happen, confidence framing derived from the record, and radar compare. The trust engine no consumer FPL tool ships.

## 0. Decisions

- **D1 — The calibration dashboard surfaces what evaluate already logs; it computes nothing new at serve time.** `reports/evaluation.json` (evaluate_current: stratified RMSE/MAE, head log-losses, reliability bins) + the news-shadow scores + `meta.py`'s expected-vs-actual per GW are the inputs. New Model-hub Quality section (extend QualityTab, no new tab): reliability curve for P(start)/p_play/CS (the bins are already in the payload — render them as curves, not tables), a predicted-vs-actual EP scatter per finished GW (from advice history `expected_pts` vs official points — both already banked by v8b's ledger), and "biggest misses this GW" (top |actual − ep| from the components vs player_gw join, with position/price context). Absent inputs ⇒ absent cards, never zeros.
- **D2 — EP bands come from the scenario-noise σ table, displayed not simulated.** Everywhere a headline EP appears (This Week squad table, captain options, compare, explorer detail), show `ep ± σ` where σ = `sigma_for(scenario_noise(), ep, xmins)` — the same table the sim uses (import-only from `optimize.scenarios`; the v8c/v8e precedent). Computed serve-side in a small helper (`src/gaffer/uncertainty.py`) reading the components frame; exposed as `ep_lo/ep_hi` (p25/p75 under the normal assumption, labeled as such) + `p_haul`/`p_blank` per player-GW (`P(pts ≥ 10)`, `P(pts ≤ 2)` under the same distribution — crude, labeled crude, but consistent with what the optimizer actually assumes; the honest headline is "what the model's own noise model implies", not a new model).
- **D3 — Confidence framing is derived from the banked record, never asserted.** A `confidence(gw_count, metric)` helper maps the calibration history to three tiers rendered as prose: e.g. captaincy advice carries "the model's captain beat your alternatives in N of M reviewed GWs" once the v8b ledger has ≥4 graded GWs; before that it says "too early to grade — N gameweeks reviewed". No percentage theater: tiers quote the actual counts. Placement: captain card (This Week) + the sensitivity card's margin line (v8e) gains "margin 0.56 EV — smaller than the noise σ on either plan" when true (a one-comparison honesty line, computed from D2's σ).
- **D4 — Radar compare.** ComparePanel gains an overlaid radar (recharts RadarChart — already a dependency) over five axes: attacking EP/90-share, minutes security (p_play), set-piece share, fixture outlook (next-3 DC-derived, already in the fixture matrix data), form (rolling returns). All values already served or one join away; axes normalized 0–100 against the current pool with the normalization stated in a tooltip. Position-mismatched comparisons render with a "different jobs" caption rather than pretending comparability.
- **D5 — No model changes, no new stores, no new jobs, no config.** Pure read-and-render cycle over banked artifacts + one serve-side helper module. `p_haul`/`p_blank`/`ep_lo`/`ep_hi` ride existing payloads additively.

## 1. Gates (orchestrator-run)

- **G1 (live render)** — on the real server: bands visible and plausible on the squad table (σ larger for boom-bust attackers than for keepers at equal EP — spot-check two); calibration cards render from the real evaluation.json; radar renders for two comparable players and captions a GKP-vs-FWD compare; the confidence line quotes the true ledger count (currently 1 reviewed GW ⇒ the "too early" branch — exercise it for real).
- **G2 (rails)** — `tests/test_v8g_degradation.py`: evaluation.json absent ⇒ calibration cards absent (200, no zeros); components absent ⇒ bands absent, EP headline unchanged; ledger empty ⇒ "too early" branch; sigma table asset absent ⇒ bands degrade to the pre-v6 heuristic exactly (the noise asset-optionality pin, copied forward); no new job kinds (pin stays 10); protected-ordering pins forward.
- **G3 (suites + audit)** — full suites, tsc, build, zero protected diffs.

## 2. Constraints

Protected list as prior cycles; journal.py/backtest.py import-only; `optimize.scenarios` import-only (sigma_for/scenario_noise — same imports the sim uses). Additive payload fields only. Never stage data/, reports/, models/, logs/, config.toml.

## 3. Out of scope

Distribution-into-MC for the optimizer (still the protected-seam deferral from v8a); quantile model heads (speculative, parked in the proposal); per-player historical calibration ("this player's EP has run hot") — needs a season of components history, revisit ~Jan; alerting on calibration drift (v8f's watchlist territory).

## 4. Outcome

Implemented across Tasks 1–9 on `feat/gaffer-v8g`. The G1–G3 checklist below is
built and left unticked: CONVENTIONS.md §7 puts the gates with the orchestrator,
not the implementer. The audit commands underneath it are mechanical rather than
gates, so they were run and their actual output is recorded.

### What shipped

Three serve-side modules, three routers, no trained feature, no store, no job
kind, no config key.

- `src/gaffer/uncertainty.py` (219 lines) — `band_for`/`bands_by_player_gw`
  read the scenario sweep's own σ out of `optimize.scenarios` and report
  p25/p75 plus `P(pts ≥ 10)`/`P(pts ≤ 2)` off the *same* clipped normal
  `noise_ep` draws from, recentred mean included. `tests/test_uncertainty.py`
  checks the band against a 20 000-draw Monte Carlo of `noise_ep` itself, which
  is the only assertion that catches the two drifting apart.
- `src/gaffer/confidence.py` (97 lines) — `captain_confidence` over the v8b
  decision ledger: `MIN_GRADED = 4`, three tiers, counts only. No branch in the
  module can emit a percentage, and a test asserts that over three ledgers.
- `src/gaffer/misses.py` (155 lines) — the components-vs-`player_gw` join for
  the largest gameweek that has both (A7), signed so a positive miss is a
  player the model under-rated.
- Payload additions, all nullable and all additive: `ep_lo`/`ep_hi`/`p_haul`/
  `p_blank` on `PlayerRow`; those four plus `ep_gw`/`sigma` on
  `ComponentPlayer`; `decision_sigma` on `SensitivityReport`. New endpoints
  `GET /api/confidence` and `GET /api/misses`.
- Frontend: `Range` column and haul/blank chips on the squad table and the
  explorer, `ConfidenceLine` under the pitch, the σ honesty line on
  `SensitivityCard`, and `CompareRadar` — five axes normalized against the
  listed pool, with the normalization stated in the caption and a "different
  jobs" line on a cross-position compare. `QualityTab` gained the `p_start`
  reliability curve, a y = x reference and bin count on every curve, the
  forecast-vs-outcome scatter, and the biggest-misses table.

### Deviations from the plan, and why

- **`test_v8g_added_no_config_key` (Task 8) was strengthened, not weakened.**
  The plan's rail screened `Config` field names for the substrings `band`,
  `uncertainty` and `confidence`; `z_deadband` is a v7 key that has carried the
  first of those since long before this cycle, so the rail failed on a
  pre-existing field. The screen now excludes that one name by exact match and
  is backed by a pin on the total field count (47), which catches a v8g config
  key whatever it happens to be named — a strictly wider net than the substring
  screen was.
- **Task 9's "Where things live" entries are bullets, not table rows.** The
  plan asked for the file's "existing table style"; that section is a bullet
  list. Matched the file.
- **Task 9's Quality paragraph said "three things" and then listed four.**
  Corrected to four in the README.
- `routers/components.py` gained a `getattr` guard for minutes-less frames
  during Task 2 — a pre-existing latent 500 that the new degraded-frame rail
  surfaced.

### Audit — run, with actual output

```
git diff --stat main...HEAD -- <the 21 protected paths>   → (no output)
git diff --stat main...HEAD -- data reports models logs config.toml
                                                          → (no output)
git diff main...HEAD | grep -iE "api[_-]?key|secret|token|password|Bearer "
                                → 1 line, and it is the plan document quoting
                                  this very grep command. No secret material.
git show main:config.toml                                 → fails (absent)
```

Whole-branch diffstat: 35 files changed, 6387 insertions(+), 32 deletions(-).
The 32 deletions are all replaced lines inside the frontend components and
routers this cycle extends; no protected path appears in the stat.

### Suites — run, with actual counts

| Command | Baseline | After v8g |
| --- | --- | --- |
| `uv run pytest -q` | 2325 (pre-cycle) | **2401 passed** — 2383 after Tasks 1–7, +18 from Task 8's rails |
| `npx vitest run` | 406 passed, 1 skipped, 58 files | **435 passed, 1 skipped, 60 files** |
| `npx tsc --noEmit` | clean | clean |
| `npm run build` | clean | clean (chunk-size advisory only, pre-existing) |

### G1 — live render (orchestrator, on the real server)

- [ ] Bands visible on the This Week squad table, and **plausible**: pick two
      players at comparable EP — one boom-bust attacker, one goalkeeper — and
      confirm the attacker's range is the wider of the two. Record both ranges.
- [ ] A player with no minutes model (or a components file temporarily moved
      aside) shows an em dash in `Range`, not `0.0–0.0`.
- [ ] Model → Quality renders every calibration card off the real
      `reports/evaluation.json`: four reliability curves including `P(starts)`,
      each with the diagonal and an observation count; the forecast-vs-outcome
      scatter with one point per finished gameweek; the biggest-misses table
      naming a real player.
- [ ] The confidence line under the pitch quotes the **true** ledger count.
      With one reviewed gameweek that is the "too early to grade — … in 1 of 1
      reviewed gameweeks" branch. Exercise it for real rather than with a
      fixture, and record the sentence verbatim.
- [ ] The radar renders for two comparable midfielders, and captions a
      GKP-vs-FWD comparison with the "different jobs" line while still drawing.
- [ ] The sensitivity card's margin line: confirm it either carries the noise
      qualifier or does not, and that which one it carries matches the served
      `decision_sigma`.

### G2 — rails

- [ ] `uv run pytest -q tests/test_v8g_degradation.py` green.

### G3 — suites and audit

- [ ] All four suite commands green at the counts recorded above.
- [ ] Both audit commands print nothing.

### Still to record at gate time

- [ ] The two spot-checked ranges from G1.
- [ ] The confidence sentence the live ledger produced.

### Orchestrator gate record (2026-08-31, post-fix-round)

**Shipped after a FIX-FIRST review round (4 blockers, 5 importants, 6 nits).** Suite 2325 → 2468 Python, 406 → 441 frontend. The review's central finding — recorded because it is the cycle's lesson: **the original D2 shipped defensible-pipeline/indefensible-number.** The estimation-σ table (median 0.018; model uncertainty, not outcome variance — the same distinction v8c's fix round established) produced a dead haul chip (0.0 on all 1878 pool rows), a `blank 100%` certainty claim on a goalkeeper, bands that were a monotone relabeling of EP (σ flat in xMins at fixed EP; a nailed CB wider-banded than Haaland by bin accident), a README asserting the inverse, a units-mismatched scatter, and a confidence sentence that indicted the model after four weeks of the user *agreeing* with it.

**Fixes:** bands/chips now price OUTCOME variance (quadrature with `league_sim.OUTCOME_VAR_PER_EP = 3.2`, import-only — the League tab and This Week now give one answer to "how uncertain is this week"); estimation σ retained solely for `decision_sigma` with its meaning stated; live sanity — Haaland ep 5.93 → band 2.79–8.68, p_haul 16.4%, p_blank 19.6%; Dubravka → p_blank 96.4% (recentred mean keeps every band below its own headline — the reviewer's targets assumed mu=ep); certainty ban test-pinned (no rounded 1.0 ever); scatter re-sourced from the v8b ledger (model_points vs official net, like units; n=1 renders "one point is an anecdote, not a scatter"); confidence: graded = wins + losses, aligned quoted separately, early tier claims nothing.

**G1 (redesigned per the review — the original spot-check was unfalsifiable):** equal-EP pair Wan-Bissaka (ep 2.46, xmins 51) vs Horníček (ep 2.47, xmins 84): bands 0.19–3.98 vs 0.20–3.99, σ 2.807 vs 2.813 — at equal EP the outcome term dominates and xMins reaches the band through EP; this is the shipped property and the README says exactly that, not the folk claim. **G2** 18 rails green (heuristic pin deliberately re-shaped to the quadrature — strictly stronger). **G3** suites above, zero protected diffs.

**Residuals:** BLANK_CHIP threshold fires on 80% of the full pool (mostly bench fodder; quiet on real squads) — revisit if noisy; per-player calibration and distribution-into-MC remain deferred as specced; ComparePanel radar fillOpacity flagged as a policy call (not a token violation).
