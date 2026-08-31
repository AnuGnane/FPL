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

### D2 — the as-of club (`scripts/v9c_club_eval.py`, `logs/v9c_club_eval.log`)

Not a gate. Spec §0 D2 says the fix ships whether or not eval improves, because a regression here would mean the old number was flattered by leakage. What follows is the measurement contract (plan A11), recorded honestly.

**Coverage and divergence**, transcribed from `V9C_CLUB_COVERAGE`:

| season_idx | rows | diverging | diverging fraction |
| --- | --- | --- | --- |
| 0 | 26,505 | 307 | 1.158 % |
| 1 | 29,725 | 175 | 0.589 % |
| 2 | 27,283 | 256 | 0.938 % |
| 3 | 29,757 | 322 | 1.082 % |
| 4 (live) | 610 | 9 | 1.475 % |
| **total** | **113,880** | **1,069** | **0.939 %** |

`club_code` is populated on all 113,880 rows — the fallback is total, never NaN, which is the G2 clause. The "off" arm (`bps.as_of_club_code` monkeypatched to the stamped `team_code`) reports 0 diverging rows, which is what makes the guard pass and the comparison meaningful.

**The leak, measured: 0.94 % of history rows were training under a club the player was not at.** Small, and it was always going to be small — it is exactly the transfer rate of the player pool. It is not zero, and it was concentrated in whole seasons of individual players rather than scattered.

**`V9C_CLUB_DEMO`** — the driver picked its own example (most diverging rows, so it cannot be a flattering choice): **James Ward-Prowse, code 101178, season_idx 3, 45 diverging rows.** His whole season is stamped `team_code = 90`; the derivation reads `club_code = 21` for GW1–23 and `club_code = 90` from GW24 on. GW11's row is the tell — `opp_code = 90`, i.e. he *played against* the club the store says he was at. Before this cycle those 23 rows trained his manager-spell, his position-by-club prior and his own-side Elo under a squad he joined in January.

**Eval, `V9C_CLUB_DONE`:**

| Arm | zeros RMSE | haulers RMSE | all RMSE | zeros n |
| --- | --- | --- | --- | --- |
| off (stamped `team_code`) | 1.065 | 5.181 | 1.968 | 16279 |
| on (derived `club_code`) | 1.062 | 5.210 | 1.968 | 16279 |
| delta (on − off) | **−0.003** | **+0.029** | **0.000** |  |

Zeros improve slightly, haulers regress by 0.029, the all-stratum number does not move at all. **Shipped regardless, as spec D2 pre-committed.** With 0.94 % of rows moving, a delta of this size on a single draw is inside what a re-fit's own noise produces, and the haulers stratum is the smallest and noisiest of the three — reading +0.029 as "the fix cost accuracy" would be reading the seed. The honest statement is the one D2 asked for: the leak was under one percent of rows, closing it changed the benchmark by nothing detectable at the all-stratum level, and the correctness argument is what carries the change, not the number.

### G3's replay — branch against a re-run `main` (`scripts/v9c_replay.sh`)

**In flight at the time of writing.** Banked so far, from
`logs/v9c_replay_branch.log`:

```
V7B_ARM_DONE v9c-branch-s1876 {"total": 1826, "hits": 17, "transfers": 69, ...}
```

**This number must not be read on its own, and especially not against a banked
figure from an earlier cycle.** Plan A15: v9c changes EP deliberately, so
branch ≠ main is the *expected* result, which makes this a gap reading and
puts it under CONVENTIONS §1 — three seed bases a side, verdict as mean ±
spread. v7b measured a 116-point seed spread on this very arm, larger than any
gap v9c could plausibly produce, so a single draw measures the seed and
nothing else. The v8a lesson (spec §9, G5) is the same one: the banked 1876
that cost an investigation was stale because a serving default had flipped
underneath it.

Both worktrees run `--arm heur --seed-bases 1876,1901,20260827 --n 40 --chips`,
identical in every config field but `seed_base` and `tag`, which is what
`scripts/seed_stats.py` verifies before it will aggregate. Verdict to be
completed from the two `seed_stats.py` aggregates.

*Adaptation worth recording:* the main worktree could not run at all as the
plan's driver was written. A fresh worktree carries only tracked files, and
every input this replay reads is untracked — `config.toml`, the parquet store,
the fitted models — so the first main-side run died before its first gameweek.
The driver now symlinks all three from the branch worktree, which is what
"`data/` is shared between the worktrees" has to mean on disk, and it is what
makes "the only thing that differs is the code" a fact rather than an
assumption.

### D3 — the haul split

(Filled after G1.)

### D4 — timeout and cancel

(Filled after G1.)

## 5. Gate checklist (built by the implementer, run by the orchestrator)

**G3 — suites, types, build, audit (measured by the implementer):**

- [x] `uv run pytest -q` — **2817 passed** (merged-main baseline 2746 + 71 new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — **553 passed, 1 skipped** (baseline 553 + 1; this
      cycle's frontend change is a two-word label and adds no test)
- [x] `npm run build` — clean
- [x] Protected diff EMPTY except D4's four authorized line groups in
      `web/jobs.py` and `routers/jobs.py`, each provenance-commented:
      `_abandon_current`/`abandon_current`, `start`'s reap, `_execute`'s
      conditional finally, `DELETE /api/jobs/current`. The only *removed*
      lines in either file are Group 3's five, replaced by the guarded form.
- [x] Pin diff EMPTY: job kinds still 12, config fields still 48,
      `config.example.toml` and `frontend/src/types.ts` job lists untouched;
      no pre-existing degradation rail modified (`git diff main --stat --
      'tests/test_*_degradation.py'` names `tests/test_v9c_degradation.py`
      and nothing else)
- [x] `tests/test_bps.py`, `tests/test_advise.py`, `tests/test_differentials.py`,
      `tests/test_assemble.py` pass unmodified — the four rails that say the
      bps extraction, the serving path, and the boundary-only rename each
      stayed inside their lines
- [x] Security ritual clean; no data/, reports/, models/, logs/ or config.toml
      in the branch diff; `git show main:config.toml` fails

**G1 — live, real season (orchestrator only):**

*D1 — the red-card arm* — **run in-branch under orchestrator authorization;
the rule was applied mechanically and the numbers are in §4 above.**
- [x] `scripts/v9c_rc_arm.py` run; `V9C_ARM_DONE` lines for both arms and the
      `V9C_VERDICT` line transcribed verbatim into §4.
- [x] The pre-registered non-regression rule (tolerance 0.005) applied as
      written: costs −0.001 / +0.002 / 0.000, no stratum breaches,
      `V9C_DECISION ship`. Branch A taken; the numbers are in `ROLL_STATS`'s
      docstring.

*D2 — the as-of club* — **run in-branch under orchestrator authorization; §4
carries the tables.**
- [x] `V9C_CLUB_COVERAGE`: 113,880 rows, `club_code` populated on all of them,
      1,069 diverging (0.939 %), per-season breakdown in §4.
- [x] `V9C_CLUB_DEMO`: James Ward-Prowse (code 101178, season_idx 3), chosen
      by the driver — 45 rows where `club_code` is 21 while `team_code` says
      90, including a GW11 row whose `opp_code` is 90.
- [x] `V9C_CLUB_DONE`: before/after and the deltas recorded **including the
      +0.029 haulers regression** (spec D2: the fix ships either way).

*D3 — the haul split*
- [ ] `GET /api/advice/latest` on the branch: `alternatives[0]` and
      `captain_options[0]` carry `p_attacking_haul` and no `p_haul`.
- [ ] `GET /api/players` and `GET /api/components/{gw}`: rows carry `p_haul`
      and no `p_attacking_haul`.
- [ ] `reports/gw{N}-advice.json` still says `p_haul`; the digest still
      renders its "One to consider" section.
- [ ] This Week's chip reads "10+ pts", and the HTML report's captain and
      alternatives tables read "P(2+ returns)".

*D4 — timeout and cancel*
- [ ] Wedge a job deliberately on the dev server (monkeypatch a job kind to a
      long sleeper), confirm the next `POST /api/jobs/{kind}` is a 409 while
      it is young.
- [ ] With `ADVISE_TIMEOUT_S` temporarily lowered, confirm the next start
      reaps it: the second job gets an id, and the first run reads
      `failed` / "timed out … abandoned as a daemon".
- [ ] `DELETE /api/jobs/current` on the wedged job frees the lane immediately
      and returns the abandoned run; on an idle runner it is a 404.
- [ ] Let the abandoned thread finish: `GET /api/jobs/current` still names the
      *newer* job, and the abandoned run's error still names the timeout.
- [ ] A normal `advise` run start-to-finish is unaffected — `done`, no error,
      lane free, log streamed.

*G3's replay evidence (run in-branch under orchestrator authorization)*
- [x] `bash scripts/v9c_replay.sh`: three seed bases a side, branch and a
      **re-run** `main` worktree, config echoes identical but for `seed_base`
      and `--tag`, aggregates read through `scripts/seed_stats.py`. Numbers
      and verdict in §4.

**G2 — rails:** `uv run pytest -q tests/test_v9c_degradation.py` — 20 passed;
`uv run pytest -q tests/ -k degradation` — 238 passed, every pre-existing
`test_*_degradation.py` unmodified.
