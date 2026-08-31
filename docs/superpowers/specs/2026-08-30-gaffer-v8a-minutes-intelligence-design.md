# gaffer v8a — minutes intelligence

Date: 2026-08-30. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 1 of 7, all approved).
Goal: attack the zeros gap (holdout zeros RMSE 1.053 post-Z1; benchmark references: OpenFPL 0.818, FPL Review 0.689) — the one gap the literature attributes to minutes information, not architecture.

## 0. Decisions

- **D1 — Manager tenure comes from a committed asset.** No head-coach data exists in the repo (verified by exhaustive grep). We ship `data/manager_tenures.toml`: one entry per EPL head-coach spell, `{club_code_name, manager, start_date, end_date?}`, covering 2022-07-01 → present (~60–70 spells; caretakers of <4 league matches may be folded into the successor). Drafted by the implementer from public record and cross-checked club-by-club against a second source; a validation test asserts full coverage (every club-season in the training frame is covered by exactly one spell per date, no gaps/overlaps). The asset is *optional at runtime*: absent/unreadable ⇒ tenure features degrade to club-level windows (season-scoped), never raise.
- **D2 — Congestion is re-tested, not re-litigated.** v5's N1 withdrew `CONGESTION_FEATURES` because cup data spanned one season (season-indicator confound; recorded at `train.py:60-67`). The builders survive and are still wired into `load_training_frame`. Now: (arm A) **league-only congestion** — recompute `days_since_last_match` / `days_to_next_match` / `matches_last_14d` from league fixtures only (100% kickoff coverage 2022-23→now, zero confound); (arm B) cup-inclusive, now that `cup_matches.parquet` spans 2025-26 + 2026-27 (still thin — expected to fail again; testing it costs one arm). Pre-registered N1-style gate; each arm withdraws individually.
- **D3 — Protected seams stay untouched.** `src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**` and the protected test suites: zero diffs. Feeding a minutes *distribution* into the MC scenario layer would edit protected `optimize/scenarios.py` → **deferred** (revisit at v8g with explicit user sanction if evidence warrants). v8a's trichotomy work stays inside `models/` and `features/`: new features feed the existing `mode_clf`, and the DNP calibrator re-fits automatically over them.
- **D4 — Lineup hints stay serve-time.** The codebase's anti-skew rule stands: live availability must never become a trained feature (no historical record). Instead: (a) strengthen the serve-time application (today the FFS hint is only a first-GW *ceiling*, and a player absent from the predicted XI carries **no signal** — the exact "regular quietly benched" case we miss); (b) start logging hints + mode probabilities into the daily snapshot so a future season can train on them.
- **D5 — LLM presser classifier runs via headless `claude -p`** on the user's Claude subscription (verified working on this machine; no API key, no new spend). Shadow-first: it always logs; serving influence sits behind `[news] llm_classifier` default **false**. The invocation command is configurable (`llm_command`, default `claude -p --output-format json`) so the user can swap CLIs later. Every call is cached by text-hash, time-limited, and total-failure-safe (classifier dead ⇒ pipeline identical to today).

## 1. F1 — rotation & tenure features [trained]

New builder `add_rotation_priors(df, tenures)` in `features/engineer.py` + `latest_rotation_priors(...)` for the prediction frame, producing four candidate features (each ablated individually before joining `MINUTES_FEATURES`):

- `tenure_start_share` — player's share of possible league starts under the *current* manager (shrunk toward the club mean with a small-k prior for short tenures; falls back to season-scoped club windows without the asset).
- `manager_tenure_matches` — league matches the current manager has had at the club (capped; a proxy for "settled XI").
- `xi_churn_r5` — team-level: mean number of starting-XI changes over the last 5 league matches under the current manager (the roulette index).
- `started_last_match` — did the player start the club's previous league match (0/1; the interaction with churn is what the trees can exploit: high-churn manager × started-last-match = elevated rest risk).

All computed from `player_gw.parquet` (starts/minutes 100% populated, 2022-23→now) with strictly-past windows (same leakage discipline as `add_rotation`). Serve-time counterparts broadcast the latest value per player/team, wired into `build_prediction_frame`'s drop-and-reattach list and `feature_columns()`.

## 2. F2 — congestion re-test [trained]

- Implement the league-only variant as `add_congestion(df, cups=None)` already supports conceptually — expose it as distinct feature names (`lg_days_since_last_match`, `lg_days_to_next_match`, `lg_matches_last_14d`) so arms A and B are separable columns, or run as config-of-the-arm in the gate driver (planner's choice; the spec requires the two arms be independently attributable).
- Gate reuses the v5 N1 protocol on the 2024-25 walk-forward benchmark (`evaluate_benchmark`), plus the current-season holdout as a sanity read.

## 3. F3 — trichotomy surfacing [measurement]

- Expose `p_start`/`p_sub`/`p_dnp` in the evaluation path: `evaluate_current` gains mode-level head metrics (log loss + reliability for P(start) as a binary, alongside the existing `p_play`/`p60`), and `diagnose-zeros` gains a per-stratum P(start) reliability cut. This makes every F1/F2 arm's effect legible at the mode level, not just via zeros RMSE.
- No serving change; `predict()`'s contract (`p_play, p60, e_min`) is untouched.

## 4. F4 — lineup-hint serve-time upgrade + hint logging [serve-time, config-gated]

- **Notable-absence damp**: after `availability_frame`, compute the set of players whose club has a parsed FFS XI and who (a) are not in it, (b) are not on any absence list, (c) have high recent start share (threshold on `tenure_start_share`/rolling starts). For those, damp first-GW `p_play` by a fixed factor `lineup_absence_damp` (default 0.75, config-overridable) — mirroring `_gate_first_gw`'s ceiling mechanics (one row per player, `p60`/`e_min` scaled by the same ratio). Behind `[news] lineup_absence` default **true** (it's conservative), with a per-source kill switch like every news source.
- **Predicted-starter support**: a `start` hint currently does nothing when the model already says p_play < 1 (min() ceiling only). Add a *floor*: `p_play ← max(p_play, lineup_start_floor)` with default 0.0 (OFF — floors are dangerous; shipped as capability, enabled only if the N2-style shadow evidence supports a value). The shadow log already records news-vs-flags deltas; this rides it.
- **Snapshot enrichment**: `snapshot_rows` gains `p_start_hint` (and the classifier verdict from F5 when present) so `availability_log.parquet` accrues the training history that would let hints become features in a future season. Append-only schema change: new columns nullable; existing 623 rows stay valid; loader tolerates both shapes.

## 5. F5 — presser/quote classifier via `claude -p` [shadow-first]

- **Sources**: (a) premierinjuries "Further Detail" cell — *start parsing it* (kept raw alongside the existing structured fields; today it is explicitly discarded); (b) the FPL bootstrap `news` free-text column (already in `players.parquet`). Both are short strings; volume ≈ 30–80 texts per refresh, most cache-hits.
- **Module** `src/gaffer/data/news/classifier.py`: `classify_news(texts: list[NewsText], *, cmd, cache_dir, timeout) -> pd.DataFrame` with columns `code, verdict, confidence, model, text_hash, fetched_at`. Verdict vocabulary: `confirmed_starter | rotation_risk | knock | assess | ruled_out | irrelevant`. One subprocess call per *batch* (all uncached texts in one prompt, JSON-array out, schema-validated row by row; malformed rows dropped and counted). Cache: one JSON file per `text_hash` under `data/raw/news/llm/`. Timeout default 120s; any failure (CLI missing, non-zero exit, bad JSON, timeout) ⇒ empty frame + one printed line, never raises.
- **Shadow log** `data/live/presser_log.parquet` (append-only, atomic, snapshot.py conventions): `season, gw, code, verdict, confidence, p_play_before, p_play_would, run_at` — where `p_play_would` is what serving *would* do under the mapping (`rotation_risk` → ×0.8 first-GW damp, `confirmed_starter` → informational, `ruled_out`/`knock`/`assess` → cross-check against the structured feed, no additional damp when the feed already covers it). Written on every advise run when the classifier is enabled for shadowing.
- **Serving**: behind `[news] llm_classifier` default **false**. When flipped (a later, evidence-backed decision — same ritual as Z1), the mapping above applies inside `apply_availability`'s news pass. v8a ships the flag OFF.
- **Config**: `[news] llm_classifier = false`, `llm_shadow = true`, `llm_command = "claude -p --output-format json"`, `llm_timeout_s = 120`.

## 6. Gates (pre-registered; orchestrator-run; CONVENTIONS.md rules apply)

- **G1 (features, primary)** — 2024-25 walk-forward benchmark, per-arm ablation over {F1 features individually, F2 arm A, F2 arm B}, each vs the same-code baseline: **keep** a feature iff zeros RMSE improves by ≥ 0.005 AND neither haulers nor all-RMSE regresses by > 0.005. Ties/marginal ⇒ withdraw (v5 discipline). Baselines measured first, numbers recorded in the plan before arms run. Multi-seed (3 seed bases) for any replay-level claim; benchmark itself is deterministic (LGB_KW has no sampling).
- **G2 (holdout sanity)** — `evaluate_current` on the shipped feature set: zeros must not regress vs 1.053; mode-level metrics (F3) reported.
- **G3 (degradation rails)** — new `tests/test_v8a_degradation.py` following the v5 pattern: tenure asset absent ⇒ club-window features, byte-identical output shape; classifier disabled ⇒ zero subprocess calls (spy at the call site); classifier failing ⇒ advise output identical to classifier-absent; `lineup_absence` off ⇒ availability identical to v7 behaviour; per-source switches independent; protected-ordering pins copied forward.
- **G4 (classifier smoke)** — one real `claude -p` batch over live news texts: ≥ 80% schema-valid rows, presser_log written, serving output byte-identical with the flag off. (Runs on the orchestrator's machine; CI/test-suite uses a fake `llm_command` — the suite must never invoke the real CLI.)
- **G5 (replay guard)** — gated S2 replay with the shipped feature set: season total within the banked same-arm seed spread (25 pts on {1876,1901}) of the pre-v8a baseline, 3 seed bases.

## 7. Constraints

- Protected, zero diffs: `src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`, `tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`, all existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`, `src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`. Note `apply_availability` (`models/availability.py`) is NOT protected and is the intended seam for F4/F5 serving logic; `snapshot.py` is not protected.
- Never stage `data/` (the tenure asset is the deliberate exception — it is a committed reference asset like `injury_return_curves.json`; planner must name the exact path in `git add`), `reports/`, `models/`, `logs/`, `config.toml`. Security ritual after merge.
- Train/serve agreement: every new trained feature appears in builder + `latest_*` + `feature_columns()` + `MINUTES_FEATURES` + `tests/test_train.py` synthetic frame, or the cycle fails its own suite.
- The test suite must never shell out to `claude` (G4 is orchestrator-run only).

## 8. Out of scope

Distribution-into-MC (protected seam — v8g candidate with sanction); AGS/prop odds (paywalled); rebuilding congestion archives; training on live availability (anti-skew rule); flipping `llm_classifier` or `lineup_start_floor` on (evidence-first, later decision).

## 9. Outcome (2026-08-31)

**Shipped.** Suite 1636 → 1773 Python (+0 frontend; no UI change this cycle). All 19 plan tasks plus a FIX-FIRST review round (1 blocker, 5 importants, 7 nits — all fixed).

**G1 — ALL SIX ARMS WITHDRAWN.** 2024-25 walk-forward benchmark, keep rule zeros ≥ +0.005 with no >0.005 haulers/all cost (baseline zeros 1.066, haulers 5.179, all 1.968):
- f1_tenure_start_share −0.008 · f1_manager_tenure_matches −0.015 · f1_xi_churn_r5 −0.007 · f1_started_last_match −0.007 · f2_league −0.004 · f2_cups −0.004 (all zeros *regressions*).
- Notes: f2_league ≡ f2_cups on this benchmark structurally (no cup rows ≤2024-25; the arms differ only in `matches_last_14d`, ever). A prediction-level probe confirmed the f1 arms are distinct fits; the xi_churn/started_last_match 3dp tie is rounding. Record lives in `train.py`'s MINUTES_FEATURES docstring beside the v5 N1 withdrawal. Builders + `data/manager_tenures.toml` (89 spells, 27 clubs, coverage-validated) stay shipped for future re-tests.
- The zeros gap is therefore *not* reachable from historical rotation/congestion features at all — reinforcing the v7-model diagnosis that the remaining error is news-shaped and serve-time. v8a's serve-time work (F4/F5) is aimed exactly there; its evidence accrues in the shadow logs.

**G2 — PASS.** Holdout zeros 1.053 (= pre-cycle, feature set unchanged), haulers 5.149; new P(start) head log loss 0.278 now reported alongside p_play 0.302 / p60 0.281.

**G3 — PASS.** 16-rail `tests/test_v8a_degradation.py`; two originally-vacuous rails rewritten against real markup during the fix round.

**G4 — PASS (on retry).** Real `claude -p` batch over live news: 127/131 texts schema-valid (97% ≥ 80% bar), `data/live/presser_log.parquet` written (83 carrier rows; verdicts ruled_out 62 / assess 14 / knock 7; serving deltas zero with the flag off). First attempt returned empty stdout under full-core load — the never-raises degradation path held; hardening followed (chunks of 40, one retry, timeout 300s, PROMPT_VERSION-salted cache, `--disallowedTools` pinned on the default command since scraped news text is untrusted input to an agent CLI).

**G5 — PASS (byte-identical to main).** Replay heur/20260901/n40: branch 1844 = main 1844 (same worktree data). The banked 1876 predates the Z1 flip (`826ff6b`), which deliberately changed minutes predictions — the stale comparison initially read as a 32-pt divergence and cost an investigation that proved the training frame and horizon frames byte-identical to main. Gate lesson recorded: **replay-equality baselines must be re-banked after any serving-default flip.**

**Review round (blocker):** serve-time rotation priors were computed one match stale — `add_rotation_priors` sorted on raw string `kickoff_time` while the serve probe was a Timestamp (mixed-dtype sort put the probe first), and the serve-equivalence rail was accidentally insensitive. Fixed: parse-then-sort, results mapped back in caller row order (`add_rotation_priors(df)[df.columns] == df` now test-pinned), rail rewritten with ISO-string fixtures. Importants: flagged players are no longer double-damped by the absence pass; a club needs ≥11 *resolved* starters before absence damps apply; classifier hardening as above.

**Residuals:** `llm_classifier` serving flag OFF pending shadow evidence (flip ritual = Z1's); `lineup_start_floor` shipped at 0.0 (capability only); presser-log verdict quality unaudited beyond the smoke distribution (first structured audit when a few GWs accrue); `serving_config` is process-cached (config edits need a server restart — commented); zeros_diagnostic DGW starts-vs-minutes incoherence documented, not fixed.
