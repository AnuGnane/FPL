# gaffer v8c — field intelligence

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 2 of 7; runs before v8b so the field history starts accruing at the earliest possible deadline).
Goal: make gaffer's advice *relative* — real top-10k field data, a real mini-league win probability, and a league what-if panel — replacing the parametric pairwise `win_probability` (fixed σ=18, `league_mode.py:326`) that currently underpins the league card.

## 0. Decisions

- **D1 — Build on the existing tier-EO scrape, don't rebuild it.** `src/gaffer/data/tier_eo.py` already samples ~300 entries from the overall league (314) top-10k with page-dedup, an anti-429 trickle, per-GW caching, and an SE estimator. v8c extends it: (a) persist the *sampled squads* (today they're aggregated and discarded), (b) append an EO history log, (c) schedule it. Its "display only" docstring contract is deliberately retired.
- **D2 — Append-only stores follow the snapshot.py idiom.** Two new artifacts: `data/live/field_eo_log.parquet` (per GW × element: eo, se, n, scrape date — idempotent per (gw, snap_date), atomic rewrite) and `data/raw/field/{season}/gw{N}.json` (the raw sampled picks: entry ids anonymized to sample indices, 15 codes + captain/vice/bench order per sampled entry — the sampled-field MC's input, permanent per-GW cache like `fetch_rival_picks_history`).
- **D3 — Win probability is a Monte Carlo over the actual mini-league, not a formula.** New module `src/gaffer/league_sim.py`: simulate the remaining season N times (default 2,000) — my squad + each tracked rival's latest squad, per-player point draws from EP means with the scenario-noise σ table (read via its public seam, no `optimize/**` edit), rival transfer behaviour approximated as "EP-greedy drift toward the field template" (parameter `rival_drift` ∈ [0,1], default 0.5; 0 = frozen squads — must be an exact, testable degenerate case). Outputs: P(win league), P(top-3), expected finish, per-rival P(beat), and a fan of final-margin quantiles. Seeded, deterministic per seed, multi-seed aggregation for any published claim (CONVENTIONS.md).
- **D4 — Protected seams stay untouched; Δwin% is computed serve-side, not in advise.** `advise.py` and `optimize/**` (incl. `scenarios.py`, `policy.py`) are zero-diff. The win-probability engine reads what advise already writes (`reports/solve_state_gw{N}.json`, `reports/gw{N}-advice.json`, rival data fetched fresh) via a new router — it does NOT inject into the pool or the tilt this cycle. The tilt's λ machinery stays authoritative for advice; the MC layer is measurement/display. (Feeding MC win-EV back into λ is a candidate for a later cycle with its own gate.)
- **D5 — The what-if panel is league-mode-only and its own router.** `POST /api/league/whatif`: toggles like "player X scores/blanks", "rival R's captain blanks", "I captain Y instead" → re-scored live/projected table + Δrank + ΔP(win) under the MC engine with those events pinned. No MILP re-solve (that's the existing squad What-If Lab; different mechanism, kept separate).
- **D6 — Scrape scheduling: launchd + job kind, post-deadline.** New CLI `gaffer field-scrape` (never raises, one printed line, idempotent per GW), `field-scrape` job kind + Model-hub button, and `scripts/com.gaffer.field.plist` firing Saturday 12:30 and Sunday 12:30 UK (both no-op fast if the GW is already scraped or no deadline has passed); `install_automation.sh` loop gains `field`. Volume ≈ 455 requests with the existing 0.05s trickle — unchanged from today's lazy fetch, just moved to a schedule.
- **D7 — Rate-limiter courtesy.** No shared limiter this cycle (the callers never overlap in practice: field-scrape post-deadline, refresh post-`data_checked`, live during matches). The field scraper gains one guard: if the live tracker triggered a tier fetch this hour (cache fresh), reuse it rather than re-fetch.

## 1. F1 — field store & EO history [data]

- `src/gaffer/data/field.py`: `fetch_field_sample(client, gw, *, sample, seed, raw_dir)` — extends `tier_eo`'s machinery to ALSO return the per-entry picks; `save_field_sample(picks, gw, season)` → `data/raw/field/{season}/gw{N}.json` (permanent, idempotent); `append_field_eo(table, gw, season)` → `data/live/field_eo_log.parquet` (snapshot.py idiom: dtype-forced, atomic tmp+os.replace, replace-keyed on (gw, snap_date)); `load_field_eo()`, `load_field_sample(season, gw)`.
- `tier_eo_table` becomes a thin consumer of the same fetch (single code path; its per-GW JSON cache and its `/api/live` behaviour must remain byte-compatible — pinned by the existing tier-EO test quartet plus new rails).
- CLI `gaffer field-scrape [--gw N]` + job kind + plist per D6.

## 2. F2 — mini-league Monte Carlo [model]

- `src/gaffer/league_sim.py`: `SimInputs` (my squad + total, rivals' squads + totals from `league.fetch_rival_picks` and standings, EP by player from the latest components frame, σ table via `scenario_noise()`'s public import, weeks left, field template from F1 for drift), `simulate_league(inputs, *, n=2000, seed, rival_drift=0.5) -> LeagueSim` where `LeagueSim` carries `p_win, p_top3, exp_finish, per_rival: [{entry, name, p_beat}], margin_quantiles, n, seed`.
- Determinism: same seed ⇒ identical output (test-pinned). `rival_drift=0` ⇒ frozen-squad analytic sanity case (a rival with a strictly dominated squad and huge deficit ⇒ p_beat ≈ 1 within tolerance — pinned loosely).
- History: `reports/league_sim_history.json` — one appended entry per computed GW `{gw, p_win, p_top3, exp_finish, run_at}` (atomic, pen-tracker idiom) feeding the sparkline.
- Multi-seed honesty: the router reports `p_win` from a fixed default seed; the CLI `gaffer league-sim --seeds a,b,c` prints mean ± spread (CONVENTIONS rule 1 for any recorded claim).

## 3. F3 — league API & UI [functionality/ui]

- `GET /api/league/sim` (new `routers/league_sim.py`): runs/loads the MC (cached per GW + advice mtime), returns `LeagueSim` + history series. Degradation: no league_id / dead API / missing advice artifacts ⇒ readable 422 per the `test_web_league.py` pattern.
- `POST /api/league/whatif` per D5: request schema `{pins: [{code, event: haul|blank|score}], captain_override: code|null, rival_captain_blanks: entry|null}` → re-run the MC with pinned draws → `{delta_rank, delta_p_win, table}`.
- League hub: win-probability card upgraded (P(win)/P(top-3) headline, sparkline of history, per-rival P(beat) table replacing the parametric list — the old `win_probability` output stays in the payload marked `legacy` until the UI fully switches); new "What if" tab under `hubs/league/WhatIfSim.tsx`; This Week gets a one-line chip on the captain card: "Captaincy choice: +x.x% title odds vs alternative" *only when* the sim cache is fresh (absent otherwise — no blocking fetch in This Week).
- `JOB_KINDS` frontend union + labels updated in lockstep (vitest count pin).

## 4. F4 — sword/shield EO context [ui]

- Player explorer and compare cards gain a `field EO` column/row (from `field_eo_log` latest GW) with the sword/shield classification vs the user's own squad: owner+field-high = shield, owner+field-low = sword, non-owner+field-high = threat. Pure display from the log; absent log ⇒ column absent (no fetch from these views).

## 5. Gates (pre-registered; orchestrator-run)

- **G1 (scrape live)** — one real `gaffer field-scrape` run: ≥250 sampled entries, EO log row-count == distinct elements seen, raw sample file valid JSON with 15 codes+captain per entry, `/api/live` tier-EO behaviour unchanged (same payload shape on the running server), idempotent re-run (second run adds 0 rows, prints the idempotence line).
- **G2 (sim sanity)** — deterministic per seed; `rival_drift=0` degenerate case; a 3-seed spread on p_win reported and recorded (no pass bar — this is a new instrument, the spread is its published honesty label); wall-clock ≤ 30s for n=2000 at league size ≤ 50.
- **G3 (degradation rails)** — `tests/test_v8c_degradation.py`: field store absent ⇒ league hub identical to v8a behaviour; scrape switch off ⇒ zero fetch calls (spy); dead API ⇒ 422s, never 500s; `/api/live` tier EO byte-compatible with v8a when the field store is absent; what-if with no pins ⇒ equals `/api/league/sim` output; job-kind count pins.
- **G4 (suite + protected audit)** — full py+frontend suites, tsc, zero protected diffs (same list as v8a; `league_mode.py` is NOT protected but its `lam` behaviour is pinned by v4d rails — they must stay green untouched).

## 6. Constraints

Protected zero-diff list as v8a (advise.py, set_pieces.py, optimize/**, pre-existing degradation tests, test_advise/test_odds/test_web_jobs, s2_replay.py, web/jobs.py, web/routers/jobs.py). Never stage data/, reports/, models/, logs/, config.toml. Scrape anonymizes: raw entry IDs are replaced by sample indices in the stored JSON (we keep no register of who was sampled). config keys: `[league] field_scrape = true`, `field_sample` (default = tier_sample), `sim_n = 2000`, `rival_drift = 0.5`. config.example.toml also gains the pre-existing undocumented `[league]` keys (found during the survey).

## 7. Out of scope

Feeding MC win-EV into the tilt λ (later cycle, gated); rival transfer *prediction* (v8 proposal's parked item); global live rank/safety (needs field-wide live data); EO-aware pool construction changes (protected seam).

## 8. Outcome (2026-08-31)

**Shipped.** Suite 1773 → 1966 Python, 302 → 328 frontend. 17 plan tasks + a live-data G2 fix round (4 root causes) + a FIX-FIRST review round (3 blockers, 5 importants, 7 nits — all fixed).

**G1 PASS** — real scrape banked 300 top-10k squads + 123 EO rows for GW2 (`data/raw/field/2026-27/gw2.json`, `data/live/field_eo_log.parquet`); all entries 15-pick with one captain; anonymized (no entry ids on disk — verified by key-set audit); idempotent re-run; `/api/live` tier-EO byte-compatible. Weekend launchd job installed alongside the existing three (user must re-run `scripts/install_automation.sh` to load it).

**G2 PASS after two fix rounds** — the gate did exactly its job, twice:
1. *Live-data round*: bench-boost pick snapshots read as permanent ability (a BB rival computed at 71.1 pts/wk vs a real 55.0 — `effective_picks()` now rebuilds multipliers from position); the estimation-σ table (median 0.018) is model uncertainty, not football variance — all 50 entries collapsed to the 6.0 sigma floor; replaced with measured `OUTCOME_VAR_PER_EP = 3.2` (within-player Var/mean flat at 2.7–4.1 over 3 seasons); silent zero EP lookups → loud notices; standings-order-dependent RNG → per-entry-id streams.
2. *Review round*: unreadable (private/late-joined) rivals were simulated as scoring nothing, silently → left out of the race with a notice; the what-if table's "P(win)" column was a renormalized pairwise artifact (leader shown 45% where the engine's own scored matrix says 82%) → per-entry win frequencies off the same matrix; and **cross-entry independence was the largest unnamed error** — mean pairwise entry correlation is 0.590 in this league (0.675 in the top-10k sample), making the margin fan 1.58× too wide. Now modeled: one shared weekly factor, entries loading at their covariance-arithmetic correlation with the banked field template (reproduces the analytic shared-owner correlation to 3 decimals; per-entry variance unchanged by construction). No-sample path degrades to independence and says so in the card.

Final live instrument (league 1794743, 50 entries, n=2000, 3 seeds): **P(win) 0.360 ± 0.017, P(top-3) 0.585, expected finish 5.6 of 50, margin p50 −28**. The correlation upgrade alone moved P(win) from 0.195 — the independent model materially understated a title race in a high-overlap league. The 3-seed spread is the instrument's honesty label per CONVENTIONS; MC SE at n=2000 ≈ ±0.9pp.

**G3 PASS** — 22 rails in `tests/test_v8c_degradation.py` (two added in fix rounds). **G4 PASS** — suites above, tsc clean, zero protected diffs, `league_mode.py` untouched (v4d λ rails green).

**Residuals:** rival transfer *behaviour* is a drift heuristic (`rival_drift=0.5`), not a model — the parked rival-prediction idea remains the upgrade path; the shared-factor model couples entries to the field template, not pairwise to each other (adequate at measured correlations, revisit if a two-entry league looks off); `field_sample` clamped at 1000; This Week's chip is cached-only by design (cold caches show nothing until the League hub or a scrape warms them); the legacy parametric win-probability list still rides the /race payload for the card's fallback.
