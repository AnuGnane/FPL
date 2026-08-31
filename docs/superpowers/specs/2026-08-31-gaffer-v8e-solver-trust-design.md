# gaffer v8e — solver trust

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 5 of 7). Lean cycle.
Goal: stop the solver being an oracle — let the user blend their own judgement in (editable xMins, FPL Review's most-loved feature), show how robust the plan is (sensitivity re-solves), compare named drafts, and sanity-rail the chip valuations.

## 0. Decisions

- **D1 — Overrides enter through the availability seam, because an override IS manual team news.** `advise.py` and `optimize/**` are protected; the sanctioned serve-time seam is `apply_availability` (v8a's F4/F5 precedent). New store `reports/overrides.json`: `{code: {p_play: float|null, e_min: float|null, note: str, set_at: iso}}` (atomic, pen-tracker idiom). Applied in the news pass as a final, *authoritative* adjustment (after feed/lineup/classifier logic — the user outranks every automated source), first-GW-only like the other passes, behind `[news] overrides = true`. The availability frame carries an `override` marker column so the why-panel and the snapshot log show exactly what the user pinned (train/serve anti-skew rule holds: overrides are serve-time only, logged for a future season's features like everything else).
- **D2 — Scope: p_play and e_min only.** Attacking-EP overrides would need a protected seam; xMins-style overrides are the high-value feature anyway. Values are clamped ([0,1] / [0,90]); an override on an unknown code is rejected at write time with a readable message.
- **D3 — Sensitivity re-solves ride the what-if machinery, serve-side.** New `POST /api/sensitivity` (or a mode on the whatif router — planner's choice): load the current solve state, perturb the pool EP K=20 times with the scenario-noise σ table (import-only from `optimize.scenarios`: `sigma_for`/`scenario_noise`, the v8c precedent), re-solve each (`solve_kw_from_state` + `milp_pool` + `solve_plan`, the `whatif.py` pattern), and report: buy/sell/captain/chip pick frequencies, the modal plan, and the EV margin between plan A and the best differing plan ("Salah-in appears in 17/20 solves; the hold plan is within 0.4 EV"). Seeded, deterministic; ~7s/solve × 20 runs as a job (`sensitivity` job kind, 10th) writing `reports/sensitivity_gw{N}.json`, served by GET. Never inside the advise path.
- **D4 — Drafts are named what-if constraint sets.** `reports/drafts.json`: `[{name, created_at, constraints: {lock[], ban[], force_in[], max_hits, chip}}]` (CRUD via a small router; cap 12 drafts). "Compare" re-solves each draft's constraints on the current solve state (whatif machinery) and renders a side-by-side table: horizon EV, week-1 moves, hits, chip — with the unconstrained optimum as the reference row. Drafts are constraint sets, not frozen squads, so they stay meaningful as the state moves; the compare row shows solved-at provenance.
- **D5 — Chip-EV rails are recorded sanity checks, not gates.** A pytest module (`tests/test_chip_sanity.py`) with WIDE bands asserting the served `chip_table` valuations are not absurd (BB gain within [0, 40]; TC within [0, 25]; a chip `play_now=True` only when `gain ≥ threshold` — internal-consistency pins), plus a script `scripts/chip_baserates.py` that prints our current chip_table against the community base-rate bands (SGW BB 8–12, DGW BB 15–25, optimal-vs-random ≈ 20–30/season) for the outcome record. The community numbers are context, not assertions — our model may legitimately disagree; the rails only catch broken arithmetic.
- **D6 — UI.** Planning hub gains a "Drafts" tab (list, add-from-current-whatif, compare table) and a sensitivity card on the Chips-or-What-if tab (frequencies + margin line, "run sensitivity" job button). This Week's why-panel shows active overrides ("you pinned Saka p_play 1.0 — model had 0.82"); the Players explorer row menu gets "pin availability…" (small dialog writing the override). Overrides editor also lives in Planning (single list with delete).

## 1. Gates (orchestrator-run)

- **G1 (overrides live)** — set a real override via the API, run `gaffer advise --fast`: the served advice reflects it (p_play pinned, why-panel marker present), the snapshot/availability artifacts carry the `override` marker; delete it, re-run, byte-identical to no-override baseline.
- **G2 (sensitivity live)** — one real sensitivity job on the current solve state: K=20 completes, frequencies sum sanely, deterministic re-run same seed, wall clock recorded (~2-3 min expected).
- **G3 (rails)** — `tests/test_v8e_degradation.py`: overrides file absent/corrupt ⇒ availability identical to v8d behaviour (byte pin); `[news] overrides=false` ⇒ no read, no marker; sensitivity/draft stores absent ⇒ empty states, 200s; job-kind pins (10); unknown-code override rejected; protected-ordering pins forward.
- **G4 (suites + audit)** — full suites, tsc, build, zero protected diffs.

## 2. Constraints

Protected list as prior cycles (advise.py, set_pieces.py, optimize/**, pre-v8e degradation files, test_advise/test_odds/test_web_jobs, s2_replay.py, web/jobs.py, routers/jobs.py); journal.py/backtest.py import-only. `optimize.scenarios`/`optimize.milp` import-only (solve_plan, sigma_for, scenario_noise — the whatif router already imports solve machinery; follow its imports exactly). Never stage data/, reports/, models/, logs/, config.toml. Config: `[news] overrides = true` only.

## 3. Out of scope

Attacking-EP overrides (protected seam); grading overrides in the v8b ledger ("your overrides cost X" — natural follow-up once overrides accrue); persisting sensitivity history; draft-vs-draft Δwin% (compare is EV-based; win% pricing later); feeding sensitivity into the served plan.

## 4. Outcome

(Filled at cycle end.)
