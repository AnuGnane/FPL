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

(Filled at cycle end.)
