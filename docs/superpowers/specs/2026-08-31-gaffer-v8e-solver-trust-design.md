# gaffer v8e — solver trust

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 5 of 7). Lean cycle.
Goal: stop the solver being an oracle — let the user blend their own judgement in (editable xMins, FPL Review's most-loved feature), show how robust the plan is (sensitivity re-solves), compare named drafts, and sanity-rail the chip valuations.

## 0. Decisions

- **D1 — Overrides enter through the availability seam, because an override IS manual team news.** `advise.py` and `optimize/**` are protected; the sanctioned serve-time seam is `apply_availability` (v8a's F4/F5 precedent). New store `reports/overrides.json`: `{code: {p_play: float|null, e_min: float|null, note: str, set_at: iso}}` (atomic, pen-tracker idiom). Applied in the news pass as a final, *authoritative* adjustment (after feed/lineup/classifier logic — the user outranks every automated source), first-GW-only like the other passes, behind `[news] overrides = true`. The availability frame carries an `override` marker column so the why-panel and the snapshot log show exactly what the user pinned (train/serve anti-skew rule holds: overrides are serve-time only, logged for a future season's features like everything else).
- **D2 — Scope: p_play and e_min only.** Attacking-EP overrides would need a protected seam; xMins-style overrides are the high-value feature anyway. Values are clamped ([0,1] / [0,90]); an override on an unknown code is rejected at write time with a readable message.
- **D3 — Sensitivity re-solves ride the what-if machinery, serve-side.** New `POST /api/sensitivity` (or a mode on the whatif router — planner's choice): load the current solve state, perturb the pool EP K=20 times with the scenario-noise σ table (import-only from `optimize.scenarios`: `sigma_for`/`scenario_noise`, the v8c precedent), re-solve each (`solve_kw_from_state` + `milp_pool` + `solve_plan`, the `whatif.py` pattern), and report: buy/sell/captain pick frequencies, the modal plan, and the signed EV margin between the modal plan and the best differing plan (chips are not swept: `optimize.milp.Plan` carries no chip field and adding one is outside this cycle's protected boundary) ("Salah-in appears in 17/20 solves; the hold plan is within 0.4 EV"). Seeded, deterministic; ~7s/solve × 20 runs as a job (`sensitivity` job kind, 10th) writing `reports/sensitivity_gw{N}.json`, served by GET. Never inside the advise path.
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

## 4. Outcome (2026-08-31)

**Shipped.** Suite 2189 → 2325 Python, 351 → 406 frontend. 11 plan tasks + a FIX-FIRST review round (2 blockers, 10 importants, ~14 nits — all fixed; one protected-pin update batch authorized: job kinds 9→10 across the v8b/v8c/v8d rails).

**G1 PASS (overrides live)** — real pin on Rice (204480, p_play 0.5): served components pinned exactly, first-GW-only (GW4/5 untouched), p60 ratio-scaled to the fourth decimal, model reading (0.872) banked at pin time, override marker + note in the availability artifact. Byte pin held against a contemporaneous control: two consecutive no-override advise runs byte-identical (the baseline-vs-later mismatch was the premierinjuries 6h cache bucket rolling — evidence on disk; noted as a gate-design lesson: live byte-pins need same-bucket controls).

**G2 PASS (sensitivity live)** — 20/20 solves, 0 failures, wall 5.0s (the ~7s/solve budget was ~28× pessimistic for a saved board — copy corrected everywhere), deterministic same-seed, and a genuinely informative first result: the modal plan appeared in only 5/20 re-solves with the runner-up 0.56 EV away — this week's board is a coin-flip, which is precisely what the feature exists to say.

**G3 PASS** — 19 rails. **G4 PASS** — suites above, tsc/build clean, zero protected diffs (three authorized pin lines only).

**Review round (the trust-cycle irony, both blockers were wrong sentences to the manager):** a negative sensitivity margin — the most interesting case, where the most frequent plan is NOT the best-valued one — was stated backwards ("is within −0.4 points"); free-hit draft rows were scored one week against the reference's three. Both fixed sign-aware/min-horizon with red-first tests. Honesty debts fixed with them: chip frequencies were structurally impossible (milp.Plan has no chip field) yet promised in three places — claim dropped, not faked; the sensitivity seed reused the advice path's own draws (a replay of the evidence, not a check on it) — offset by 1,000,000 and documented; a DGW pin moved one fixture of two — a fitness claim now covers the whole first GW; stale-GW sensitivity reports now say so. UX debts: structured 422s render readably, deleted drafts leave the compare set, the pin dialog validates and caps, the why-panel only claims pins that are in the plan.

**Residuals:** grading overrides in the v8b ledger ("your pins cost/earned X") — natural follow-up as pins accrue; sensitivity history not persisted (per-GW file only); the e_min/p_play coherence check warns, doesn't block; `optimize/scenarios.py`'s own timing docstring (protected) still quotes the old estimate for the full advice sweep — true for that path, unmeasured.

### Gate results (orchestrator-run)

**G1 — overrides live.** Against the real repo, real config, real advice.

- [ ] `POST /api/overrides` sets a real pin on a real player (record the
      body, and the `model_p_play` the store banked).
- [ ] `uv run gaffer advise --fast` — the served advice reflects it: the
      player's `p_play` in `reports/components_gw{N}.parquet` equals the pin,
      and `p60` / expected minutes moved with it on the same ratio.
- [ ] This Week's why-panel names the pin, with "the model had X".
- [ ] `reports/availability_gw{N}.parquet` and
      `data/live/availability_log.parquet` both carry `override = true` for
      that code and null for everyone else.
- [ ] **The byte pin.** `DELETE /api/overrides/{code}`, re-run
      `gaffer advise --fast`, and the component file is byte-identical to a
      no-override baseline taken before the pin was set (`cmp` the two
      parquets, or compare a stable hash of the sorted frame). A difference
      here means the pass is not a no-op when the store is empty.
- [ ] Transcribe the API bodies and the hashes verbatim (CONVENTIONS.md §4).

Output:

```
(paste here)
```

**G2 — sensitivity live.** One real sweep on the current solve state.

- [ ] `POST /api/jobs/sensitivity` completes: K=20, `completed == 20`,
      `failures == 0` (or the failures explained).
- [ ] Frequencies sum sanely — every `count <= completed`, every `frequency`
      in (0, 1], and the modal plan's `count` is the largest group.
- [ ] **Deterministic:** re-run with the same seed (delete the report first,
      or call `run_sensitivity(seed=...)` directly) and the `frequencies` and
      `margin` are identical.
- [ ] Wall clock recorded (expect ~2-3 minutes) along with `wall_s` from the
      report.
- [ ] The verdict sentence is true of the frequency table under it — spot
      check the modal buy's count against its row.
- [ ] Transcribe the report's head verbatim.

Output:

```
(paste here)
```

**G3 — rails.** `uv run pytest -q tests/test_v8e_degradation.py`

- [ ] All passed. Specifically: no override file ⇒ availability identical to
      v8d; corrupt store ⇒ unchanged plus a printed reason; `overrides=false`
      ⇒ no read and no marker; unknown-code override rejected; the pass runs
      last; the two column lists agree; every new endpoint 200s on an empty
      machine; corrupt stores read as empty; job-kind count pinned at 10; the
      four board-building sites agree; one config key added.

**G4 — suites, chip rails and audit.**

- [ ] `uv run pytest -q -rs` green; note which `test_chip_sanity.py` tests
      skipped and why.
- [ ] `uv run python scripts/chip_baserates.py` run against a real week, its
      output transcribed here, and any gap from the community bands noted in
      §4 as an observation rather than a failure.
- [ ] `npx vitest run`, `npx tsc --noEmit`, `npm run build` green.
- [ ] Task 11's protected-file, import-only, availability-diff and
      whatif-untouched checks all as expected, with the three authorised pin
      lines the only protected change in the branch.
