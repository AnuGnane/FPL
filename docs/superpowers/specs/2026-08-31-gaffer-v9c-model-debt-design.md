# gaffer v9c — model debt

Date: 2026-08-31. Parent: the 2026-08-31 cross-cutting review (ROADMAP "v9c — model debt"). Evidence-first cycle: two findings change training frames, one is a naming split, one needs protected-file authorization. Sequenced AFTER v9a/v9b merge to avoid cross-branch churn.
Goal: close the four deferred review findings — the dead red-card term, the `team_code` retro-stamp leak, the `p_haul` name split, and job timeout/cancel — each behind its own gate, with nothing shipping on assertion.

## 0. Decisions

- **D1 — `rc` joins `ROLL_STATS`; the term ships only if the arm passes.** `card_penalty` (models/components.py:157) reads `rc_r38`, but `ROLL_STATS` (features/engineer.py:15) rolls `yc` and not `rc`, so the −3 red-card term has been identically zero for every player since the term landed — `_rate` maps the missing key to 0.0, silently. `rc` is already stored (data/live.py RENAME `red_cards → rc`, CANONICAL_COLS), so the fix is one list entry — but it adds `rc_r{1,3,5,10,38}` to the training frame, so it runs as an **arm**, v8a-style (scripts/v8a_arms.py methodology: baseline vs arm on the fixed eval protocol, zeros metric included). Ship if eval does not regress; if it regresses, the arm is withdrawn AND `card_penalty`'s red term is explicitly zeroed with a comment recording the finding + arm result — a documented zero, not a silent broken read. Either way the silent state ends. Replay-pin discipline (the v8a lesson): a changed training frame invalidates banked replay-equality numbers — the valid check is branch≡main re-run in a main worktree, never a stale banked figure.
- **D2 — an as-of `club_code` column replaces `team_code` in the three history-keyed builders.** `refresh_live` (data/live.py:169) stamps the player's *current* `team_code` over every history row and rebuilds the whole parquet each run, so a January transfer silently rewrites his GW1–19 training rows under the new club — `bps.py:79-81` already documents the hazard and `fixture_key` was rebuilt to avoid it. Derivation, from data already stored per row: join the fixture list (data/history.py:129-130 carries `home_code`/`away_code` per `(season_idx, gw, kickoff_time)`) on the row's `(season_idx, gw, kickoff_time)` where `opp_code` matches one side; the player's as-of club is the **other** side (`was_home` cross-checks it). This is exactly `fixture_key`'s machinery — factor the shared join rather than re-implementing, including its corrupt-duplicate-key drop semantics. Rows matching no fixture (and all future/serving rows, where current club IS the as-of club) fall back to `team_code`. Switch the three consumers: `_shrunk_ratio`'s position-by-club prior (engineer.py:989 `slots["team"]`), manager-spell scoping (engineer.py:300 `spell_keys(out["team_code"], …)` — spells are club tenures, so the as-of club is the correct key), and the team-Elo merge (engineer.py:601 `add_context`, own-team side only; `opp_code` is already fixture-sourced and correct). `team_code` itself stays in the store for serve-time identity (v9a's pitch, bootstrap joins). Changed training frames ⇒ same D1 re-bank discipline; eval before/after recorded even though this is a correctness fix — if eval *regresses* the fix still ships (the old number was leakage-flattered) but the delta is recorded in §4.
- **D3 — the `p_haul` split is resolved at the serving boundary, not by touching protected files.** Two quantities share the name: `assemble.p_haul` = P(2+ attacking returns) under Poisson (models/assemble.py:39), flowing through `advise.py:854` (PROTECTED) and `optimize/differentials.py` (PROTECTED) into the alternatives/captain payloads; `uncertainty.Band.p_haul` = P(total points ≥ HAUL_POINTS) (uncertainty.py:264), served by players.py:185 and components.py:185. A full internal rename would require diffs in `advise.py` and `optimize/**` — not worth the authorization for a label. Instead: the **web boundary renames the attacking one to `p_attacking_haul`** — in the unprotected routers/schemas that build the alternatives/captain responses (schemas.py's alternative-row model, ~:591 vs the band-sourced ~:411 — implementer verifies which is which by tracing both), mirrored in types.ts and any UI label ("haul odds" cards must say which quantity they show; the band one keeps `p_haul`). Docstrings in the unprotected `assemble.py` and `uncertainty.py` cross-reference each other and name the split. The internal column keeps its name inside the protected pipeline, with the boundary rename commented at the single site it happens. If a pre-existing degradation rail pins the outbound field name, that is a deliberate orchestrator-authorized pin update (v8e/v8f precedent, provenance comment) — enumerate before editing; STOP for authorization.
- **D4 — job timeout + cancel: a deliberate orchestrator-authorized protected edit.** `ADVISE_TIMEOUT_S = 1800.0` (web/jobs.py:30) has zero readers; `JobRunner._current` is cleared only by `_execute`'s `finally` (jobs.py:328), so a wedged job 409s every later job until process restart, and routers/jobs.py exposes no cancel. Minimal design, mirroring the registry's existing abandon path: (a) in `JobRunner.start` (jobs.py:258-270), when `_current` names a run still marked running whose age exceeds `ADVISE_TIMEOUT_S`, mark it abandoned/error ("timed out — abandoned as a daemon", the module's own §10 wording) and clear the lane before the 409 check; (b) new `DELETE /api/jobs/current` in routers/jobs.py doing the same abandonment on demand, 404 when idle. The worker thread is a daemon and keeps running — abandonment frees the lane, it does not kill work; idempotent job design (a v8f constraint) makes the re-run safe. **STOP — this is the cycle's one orchestrator-authorized protected exception:** exact edits enumerated as `web/jobs.py` `JobRunner.start` + one small `_abandon_current` helper, and `routers/jobs.py` one DELETE route; each carries a provenance comment naming this spec; no other lines in either file. New rails pin the behavior afterwards (G2). Recorded out of scope, adjacent: the SSE stream (routers/jobs.py:116-153) pins a threadpool worker per watched run for up to `IDLE_TIMEOUT_S = 3600` — revisit if worker starvation is ever observed; not this cycle.

## 1. Gates (orchestrator-run)

- **G1 (live/evidence)** — D1: arm result table (baseline vs +rc, fixed protocol, zeros metric) recorded in §4; ship/withdraw decided on it. D2: before/after eval numbers + a concrete demonstration on one real transferred player (his pre-transfer rows carry the old club in `club_code` while `team_code` shows the new one). D3: `GET` the alternatives payload and the players table on the branch — the attacking field arrives as `p_attacking_haul`, the band field still as `p_haul`, UI labels distinguish them. D4: wedge a job deliberately (monkeypatched sleeper via the dev server), confirm the next start abandons it after the timeout, and `DELETE /api/jobs/current` frees the lane immediately; a normal advise run is unaffected.
- **G2 (rails)** — `tests/test_v9c_degradation.py`: `rc_r38` present-and-nonzero-capable (or the explicit-zero branch pinned, whichever D1 decides); `club_code` falls back to `team_code` on missing fixture join, never NaN-scatters; duplicate-fixture corruption drops to fallback rather than mis-keys; boundary rename pinned both directions (attacking field name in the alternatives payload, band field name in the players payload); abandoned-job lane frees + the run record says why; job-kind pins stay 12; protected-ordering pins carried forward. Pre-existing degradation rails that pin a renamed outbound field or job behavior change ONLY via the deliberate orchestrator-authorized update with provenance comments (v8f precedent).
- **G3 (suites + audit)** — full suites, tsc, build; protected diff EMPTY except the enumerated D4 exception (two files, provenance-commented) and any authorized pin updates — nothing else; replay-equality evidence branch≡main re-run per D1/D2 (never a banked stale number); security greps clean.

## 2. Constraints

Protected list as prior cycles — `advise.py`, `set_pieces.py`, `optimize/**`, `web/jobs.py`, `routers/jobs.py`, `routers/whatif.py`, pre-existing test rails, `s2_replay.py`; `journal.py`/`backtest.py` import-only — with D4's enumerated exception as the sole authorized breach (plus authorized pin updates if D3's boundary rename hits a pinned field). Never stage `data/`, `reports/`, `models/`, `logs/`, `config.toml`, `web/static/`. Model changes are evidence-first: an arm that regresses ships OFF with the finding recorded (v8a precedent); D2 ships regardless but records its delta. Retrains use the standard multi-seed discipline (CONVENTIONS.md). No new job kinds, plists, or config keys.

## 3. Out of scope

Killing a wedged job's thread (abandon-only, matching the module's stated design); the SSE worker-pinning rework; renaming `p_haul` inside the protected pipeline; any further card-model sophistication (per-referee, per-position rates); backfilling `club_code` for seasons whose fixture lists are absent (fallback covers them); Season-in-Review.

## 4. Outcome

(Filled at cycle end: arm table for D1, eval delta + transferred-player demo for D2, both payload field names for D3, the wedged-job timeline for D4, and the authorized protected diff enumeration.)

**Suite baselines**, re-measured on the merged-`main` branch point `99baf50`: **2746 Python passed; 553 frontend passed + 1 skipped** (65 files).

### D1 — the red-card arm (`scripts/v9c_rc_arm.py`, `logs/v9c_rc_arm.log`)

Transcribed verbatim from the log:

```
V9C_ARM_DONE baseline {"zeros": 1.066, "haulers": 5.179, "all": 1.968, "zeros_n": 16279}
V9C_ARM_DONE rc {"zeros": 1.065, "haulers": 5.181, "all": 1.968, "zeros_n": 16279}
V9C_VERDICT rc {"zeros_cost": -0.001, "haulers_cost": 0.002, "all_cost": 0.0, "tolerance": 0.005, "decision": "ship"}
V9C_DECISION ship
```

| Arm | zeros RMSE | haulers RMSE | all RMSE | zeros n |
| --- | --- | --- | --- | --- |
| baseline (`ROLL_STATS` without `rc`) | 1.066 | 5.179 | 1.968 | 16279 |
| `+rc` | 1.065 | 5.181 | 1.968 | 16279 |
| cost (arm − base) | −0.001 | +0.002 | 0.000 | — |

The pre-registered non-regression rule (plan A4, tolerance 0.005, fixed in the driver's docstring before the run) is satisfied on all three strata — the largest cost is +0.002 on haulers, well inside tolerance, and zeros actually improves by 0.001. **Branch A: shipped.** The `-3 * rc_r38` term is live for the first time since it was written; the numbers are transcribed into `ROLL_STATS`'s docstring, which is the place a reader of the list will look.

The effect being this small is the expected shape rather than a disappointment: a red card is rare, a 38-match mean of it is a very small number, and D1 was never an improvement hunt — it was a term the model documented and never applied. The measurement says switching it on costs nothing.

### D2 — the as-of club

(Filled after Task 5's run.)

### D3 — the haul split

(Filled after G1.)

### D4 — timeout and cancel

(Filled after G1.)

## 5. Gate checklist (built by the implementer, run by the orchestrator — unfilled)

(Filled by the implementer at the final task, per CONVENTIONS.md §7.)
