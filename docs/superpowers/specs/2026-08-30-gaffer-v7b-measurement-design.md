# gaffer v7b — measurement cycle: is scenario gating worth keeping?

Date: 2026-08-30 · Status: approved (user-directed) · Branch: `feat/gaffer-v7b`

A pure measurement cycle — no features, no serving-default changes. Its
product is evidence and a verdict, recorded here, ending in a
keep / re-noise / remove decision on scenario gating that the user makes
on error-barred numbers. Any serving change it justifies ships as its own
follow-up commit with the numbers attached.

## 1. Questions (all on the 2025-26 gated replay harness, scripts/s2_replay.py lineage)

- **Q1 — error bars.** The whole S1/S2 series is one seed. Re-run the
  heuristic and estimation arms at 3 seed bases (the original
  20260827+gw plus two others); raw is deterministic and needs one run
  (1914 stands). Deliverable: mean ± spread per arm; does the
  heuristic-vs-raw gap (−129) survive seed variation?
- **Q2 — bisect the D1 sign reversal.** v4c measured gating +75
  (raw 1743 vs gated 1818); today it is −129 (raw 1914 vs gated 1785).
  Find the cause. The planner must first establish what `run_backtest`
  actually consumes that changed since v4c (candidates: the v5
  ThreeModeModel swap and xmins semantics; the v6 scoring-table bonus
  multiplier; anything else the diff shows) and design the cheapest
  honest bisect — prefer ablation arms on current code where a
  rail/flag/monkeypatch can reproduce the old behaviour byte-identically;
  fall back to git-worktree replays at the v4d/v5/v6 merge points only
  where ablation is impossible. Deliverable: the reversal attributed (or
  explicitly narrowed to a named residual).
- **Q3 — composite σ.** Sweep `σ(cell) = sqrt(σ_est(cell)² + floor²)`
  for floor ∈ {0.3, 0.6, 1.0} (one seed base, the original). Does any
  floor beat BOTH pure estimation (1908) and raw (1914)? That would mean
  a re-noised gate genuinely earns its cost. Deliverable: the floor
  curve alongside heuristic/estimation/raw.

## 2. Verdict rule (pre-registered)

After Q1–Q3, the recommendation to the user is mechanical:
- If some composite floor beats raw's mean by more than Q1's observed
  seed spread → recommend **re-noise** (ship that floor's table).
- Else if raw beats the best gated arm by more than the seed spread →
  recommend **remove** (add a config switch to skip the scenario sweep;
  keep the machinery for chips/UI if the planner finds it entangled).
- Else → recommend **keep as-is** (option (b); differences within noise).
The user makes the final call either way; nothing ships by default.

## 3. Constraints

- No serving-default changes in this cycle; drivers and toggles only.
- Protected files as always; degradation rails sacred; every new toggle
  must have an off-state byte-identical test.
- Replays sequential or max 2 concurrent (they already saturate cores);
  nohup+caffeinate+Monitor; per-arm output paths (the _ArmStore pattern).
- Budget guard: if the full matrix exceeds ~20 replay runs, the planner
  must cut scope (Q1 before Q3 before Q2-worktree-fallback) rather than
  queue more.

## 4. Also in this cycle

- **N2 first verdict** (orchestrator): when GW2 is `data_checked`,
  `gaffer refresh` then `gaffer evaluate --news-shadow`; record the
  scored verdict in §5 and check the Model hub scoreboard renders it.

## 5. Outcome

Recorded at cycle end.
