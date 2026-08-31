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

### D1 — the red-card arm (`scripts/v9c_rc_arm.py`, `logs/v9c_rc_arm_redterm.log`)

**Measured three times. The first two measurements were wrong, and how they were wrong is the useful part of this section.**

*Run 1 (`logs/v9c_rc_arm.log`)* gated the raw `rc_r38` rate: baseline 1.066 / 5.179 / 1.968, `+rc` 1.065 / 5.181 / 1.968, costs −0.001 / +0.002 / 0.000, decision ship. Correct for what it measured — but adversarial review then found what it was measuring. `rc_r38` is a rolling mean of the rarest event in the model taken with `min_periods=1`, so a player sent off on debut carried a rate of **1.0** and `card_penalty`'s −3 turned that into `e_cards = -3.00` from one observation. 196 rows of the corpus sat below −0.5. The arm had passed a term whose worst case was a fabrication (review I3).

*Run 2 (`logs/v9c_rc_arm_shrunk.log`)*, after shrinking the rate through the `_shrunk_ratio` idiom, reported costs of **exactly 0.000 on all three strata** — with a training frame that genuinely differed by five columns (149 vs 154), so the plan's A3 mutable-default guard passed. It was still measuring nothing. Shrinkage made `card_penalty` read `shrunk_rc_rate`, which `add_shrunken_cards` builds from the **raw** `rc` column in `CANONICAL_COLS`; removing `"rc"` from `ROLL_STATS` no longer switched the term off. A gate whose lever had come loose, reporting ship. That is the same shape of defect D1 exists to close, which is why the driver now refuses to report when both arms score identically.

*Run 3, the one that counts,* puts the lever on the term itself — `models.components.CARD_RATES` with the red row removed:

```
V9C_ARM_WIDTHS {"without_rc": 149, "with_rc": 154}
V9C_ARM_DONE baseline {"zeros": 1.064, "haulers": 5.207, "all": 1.969, "zeros_n": 16279}
V9C_ARM_DONE rc {"zeros": 1.063, "haulers": 5.208, "all": 1.969, "zeros_n": 16279}
V9C_VERDICT rc {"zeros_cost": -0.001, "haulers_cost": 0.001, "all_cost": 0.0, "tolerance": 0.005, "decision": "ship"}
V9C_DECISION ship
```

| Arm | zeros RMSE | haulers RMSE | all RMSE | zeros n |
| --- | --- | --- | --- | --- |
| red term ablated | 1.064 | 5.207 | 1.969 | 16279 |
| red term live (shipped) | 1.063 | 5.208 | 1.969 | 16279 |
| cost (arm − base) | −0.001 | +0.001 | 0.000 | — |

No stratum breaches the pre-registered 0.005 non-regression tolerance. **Branch A: shipped**, on the shrunk rate, with the term live for the first time since it was written.

The effect is small and always was going to be: a red card is rare, and D1 was never an improvement hunt. What the three runs bought is worth more than the delta — the term is now both *live* and *bounded*, where before the review it was live and capable of asserting −3.00 expected points off a single sending-off.

### D2 — the as-of club (`scripts/v9c_club_eval.py`, `logs/v9c_club_eval.log`)

Not a gate. Spec §0 D2 says the fix ships whether or not eval improves, because a regression here would mean the old number was flattered by leakage. What follows is the measurement contract (plan A11), recorded honestly.

**Coverage and divergence**, transcribed from `V9C_CLUB_COVERAGE` (`logs/v9c_club_eval_v2.log`). The match rate is the **fixture-join rate measured before the fallback is applied** — the first version of this script reported `club_code.notna()`, which is 100 % by construction because the fallback fills every row, and a metric that cannot come out below 100 % measures nothing (review I5):

| season_idx | rows | matched | match rate | diverging | diverging % of matched |
| --- | --- | --- | --- | --- | --- |
| 0 | 26,505 | 26,505 | 100.0 % | 307 | 1.158 % |
| 1 | 29,725 | 29,725 | 100.0 % | 175 | 0.589 % |
| 2 | 27,283 | 27,283 | 100.0 % | 256 | 0.938 % |
| 3 | 29,757 | 29,757 | 100.0 % | 322 | 1.082 % |
| 4 (live) | 610 | 610 | 100.0 % | 9 | 1.475 % |
| **total** | **113,880** | **113,880** | **100.0 %** | **1,069** | **0.939 %** |

The match rate comes out at 100 % on this store, and now that is a finding rather than a tautology: every history row the training frame carries resolved to an archived fixture, so the "seasons with no fixture list" fallback that §3 puts out of scope is currently exercising on zero rows. `club_code` is populated on all 113,880 rows and NaN on none, which is the G2 clause. The "off" arm reports 0 diverging rows, which is what makes the guard pass and the comparison meaningful.

**The leak, measured: 0.94 % of matched history rows were training under a club the player was not at.** Small, and it was always going to be small — it is exactly the transfer rate of the player pool. It is not zero, and it was concentrated in whole seasons of individual players rather than scattered.

**`V9C_CLUB_DEMO`** — the driver picked its own example (most diverging rows, so it cannot be a flattering choice): **James Ward-Prowse, code 101178, season_idx 3, 45 diverging rows.** His whole season is stamped `team_code = 90`; the derivation reads `club_code = 21` for GW1–23 and `club_code = 90` from GW24 on. GW11's row is the tell — `opp_code = 90`, i.e. he *played against* the club the store says he was at. Before this cycle those 23 rows trained his manager-spell, his position-by-club prior and his own-side Elo under a squad he joined in January.

**Eval, `V9C_CLUB_DONE`:**

| Arm | zeros RMSE | haulers RMSE | all RMSE | zeros n |
| --- | --- | --- | --- | --- |
| off (stamped `team_code`) | 1.065 | 5.181 | 1.968 | 16279 |
| on (derived `club_code`) | 1.062 | 5.210 | 1.968 | 16279 |
| delta (on − off) | **−0.003** | **+0.029** | **0.000** |  |

Zeros improve slightly, haulers regress by 0.029, the all-stratum number does not move at all. **Shipped regardless, as spec D2 pre-committed.** With 0.94 % of rows moving, a delta of this size on a single draw is inside what a re-fit's own noise produces, and the haulers stratum is the smallest and noisiest of the three — reading +0.029 as "the fix cost accuracy" would be reading the seed. The honest statement is the one D2 asked for: the leak was under one percent of rows, closing it changed the benchmark by nothing detectable at the all-stratum level, and the correctness argument is what carries the change, not the number.

### G3's replay — branch against a re-run `main` (`scripts/v9c_replay.sh`)

Three seed bases a side, branch against a `main` worktree re-run on the same untracked store, `--arm heur --n 40 --chips`. Read through `scripts/seed_stats.py`, which is also the config-echo check: it refuses (exit 2) unless the reports differ in nothing but `seed_base` and `tag`, and it aggregated both trios without complaint.

```
MULTISEED_DONE v9c-branch {"totals": [1853, 1847, 1872], "mean": 1857.3, "spread": 25, "range": [1847, 1872], "seed_bases": [1876, 1901, 20260827]}
MULTISEED_DONE v9c-main   {"totals": [1826, 1933, 1864], "mean": 1874.3, "spread": 107, "range": [1826, 1933], "seed_bases": [1876, 1901, 20260827]}
```

| seed base | branch | main | paired delta |
| --- | --- | --- | --- |
| 1876 | 1853 | 1826 | **+27** |
| 1901 | 1847 | 1933 | **−86** |
| 20260827 | 1872 | 1864 | **+8** |
| **mean** | **1857.3** | **1874.3** | **−17.0** |
| spread | 25 | **107** | — |

**Verdict: within seed noise. The replay gate PASSES.**

The delta has to be read against the spread, and there is no reading on which it survives:

- **Main's own spread is 107 points — more than six times the −17 mean delta.** The same code, the same store, three different seed bases, and the season total moves by over a hundred points. v7b measured a 116-point spread on this exact arm, so 107 is the expected magnitude rather than a surprise.
- **The paired deltas do not agree in sign** (+27, −86, +8). A real effect of −17 would not flip direction twice across three draws. The −86 is entirely accounted for by main's s1901 being the top of its own range (1933); pair the *other* two seeds and the branch is ahead.
- **The branch range sits inside the main range.** 1847–1872 is wholly contained in 1826–1933. The two samples are not distinguishable.

So the cycle's model changes — the live shrunk red-card term (D1) and the as-of club on three feature families (D2) — move the replay by nothing that can be told apart from the seed. That is the honest and expected result: D2 corrected 0.94 % of training rows and D1 switched on a term worth a fraction of a point per player-week, and neither was ever going to show up against a hundred-point seed spread.

**What this run is not.** It is not compared against any banked figure. The banked 1876 that cost v8a an investigation (spec §9, G5) was stale because a serving default had flipped underneath it, and reading a branch against it measured the flip rather than the branch. `main` was re-run here from a worktree symlinked to the same untracked `data/`, `models/` and `config.toml`, so the only thing that differed between the two sides was the code.

**One thing not claimed.** The branch's spread of 25 against main's 107 is *not* evidence that v9c stabilised anything. Three draws say almost nothing about variance, and reading a tighter spread off n=3 as an improvement would be exactly the single-draw error this section exists to avoid.

*Adaptations, recorded because both cost time.* The plan's driver assumed a fresh worktree could run the replay; it carries only tracked files, and every input the replay reads is untracked, so the first main-side run died before its first gameweek and the driver now symlinks `config.toml`, `data/` and `models/`. And `v7b_replay.py --seed-bases` banks one report per seed (`v7b_{tag}-s{seed}.json`), not the single combined `v7b_{tag}.json` the plan's driver named — so the driver's own `seed_stats.py` invocation pointed at files that never exist, and the aggregate was run over the three per-seed reports instead.

*Re-run note.* The branch trio above is the **second** branch run. The first (mean of the pre-review form) was discarded when the review's I3 changed the rate `card_penalty` reads: those draws measured a form that no longer ships. The main side was untouched by that change and its runs stand as banked.

### D3 — the haul split

(Filled after G1.)

### D4 — timeout and cancel

(Filled after G1.)

## 5. Gate checklist (built by the implementer, run by the orchestrator)

**G3 — suites, types, build, audit (measured by the implementer):**

- [x] `uv run pytest -q` — **2825 passed** (merged-main baseline 2746 + 79 new,
      the review round included)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — **554 passed, 1 skipped** (baseline 553 + 1: the
      review's I7 pin on the relabelled haul chip)
- [x] `npm run build` — clean
- [x] Protected diff EMPTY except the **six** authorized line groups, each
      provenance-commented. D4's four (plan T7): `_abandon_current` /
      `abandon_current`, `start`'s reap, `_execute`'s conditional finally, and
      `DELETE /api/jobs/current`. The review round's two: B1's guarded
      stdout/stderr restore in `_execute` (`web/jobs.py`), and I1's atomic
      advice-artifact write in `advise.py` — the cycle's only line in that
      file, and the one that makes the abandonment docstrings' idempotency
      claim actually true.
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
      written, on the third and only valid run: costs −0.001 / +0.001 / 0.000,
      no stratum breaches, `V9C_DECISION ship`. Branch A taken; the numbers
      are in `ROLL_STATS`'s docstring. The first two runs and why they were
      invalid — an unshrunk rate, then a disconnected lever — are recorded in
      §4 rather than quietly replaced.

*D2 — the as-of club* — **run in-branch under orchestrator authorization; §4
carries the tables.**
- [x] `V9C_CLUB_COVERAGE`: 113,880 rows, fixture-join match rate 100.0 %
      (measured pre-fallback, review I5), 1,069 diverging = 0.939 % of matched
      rows; per-season breakdown in §4.
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
- [x] `bash scripts/v9c_replay.sh`: three seed bases a side (1876, 1901,
      20260827), branch against a **re-run** `main` worktree reading the same
      untracked store, config echoes identical but for `seed_base` and
      `--tag` — verified by `scripts/seed_stats.py` accepting both trios,
      which is exactly the check it exits 2 on. Branch mean **1857.3**
      (spread 25), main mean **1874.3** (spread 107), delta **−17.0**; paired
      deltas +27 / −86 / +8. **Within seed noise: the gate passes.** The delta
      is a sixth of main's own spread, the paired deltas flip sign twice, and
      the branch range sits inside the main range. Full reading in §4, read
      against the spread and never against a banked figure (v8a §9 G5).

**G2 — rails:** `uv run pytest -q tests/test_v9c_degradation.py` — 22 passed;
`uv run pytest -q tests/ -k degradation` — 238 passed, every pre-existing
`test_*_degradation.py` unmodified.
