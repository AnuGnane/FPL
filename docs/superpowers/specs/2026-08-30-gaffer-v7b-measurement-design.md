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

### Q2 probe (Task 6, 2026-08-30)

`V7B_PROBE_FRAME {"identical": true}` — the v5 frame additions
(congestion, shrunken modes) are inert to the replay; `--frame v4c` arms
never ran. `V7B_PROBE_XMINS`: current vs legacy mean noise scale 0.4818
vs 0.4809 (0.2%) — the xMins-*scale* mechanism (plan F2) is wrong.

### Q2 control + ablation — attributed, single-seed (see §6) (4 runs, D1-matched harness:
no chips, no priors, seed base 20260825)

| minutes head | gated (heur) | raw | gating delta |
|---|---|---|---|
| current (ThreeModeModel) | 1786 | 1847 | **−61** |
| legacy (pre-v5 MinutesModel) | 1827 | 1800 | **+27** |

- The harness does NOT explain the reversal (delta_ctrl −61 under D1's
  own conditions, where v4c measured +75).
- **The v5 ThreeModeModel swap is the leading (and only surviving) candidate** — single-seed, see §6. Flip the head back and
  gating's sign flips back. Note the interaction is via noise
  *placement*, not scale (probe above): sharper p_play/p60 changes which
  players the xMins-derived heuristic σ perturbs, not how much.
- The swap itself remains justified: current head beats legacy by +47
  ungated (1847 vs 1800). v5 improved the model and silently broke the
  gate — nobody re-ran D1 after the swap until now.
- Free evidence: raw-ctrl 1847 vs v4c's raw 1743 = +104, consistent with model
  improvement (uncontrolled — see §6) on the ungated side since v4c.

### Q1 — error bars (Task 9, full harness, 3 seed bases)

| arm | 20260827 | 20260901 | 20260915 | mean | spread |
|---|---|---|---|---|---|
| heuristic | 1785 | 1876 | 1901 | 1854.0 | **116** |
| estimation | 1908 | 1847 | 1883 | 1879.3 | 61 |
| raw (deterministic) | 1914 | — | — | 1914 | 0 |

The verdict-rule spread is 116 (the larger arm). Q1's answer: the
single-seed −129 heuristic-vs-raw gap is NOT distinguishable from seed
noise — the S1/S2 series was reading one draw. Raw beats the estimation
mean by 34.7 and the heuristic mean by 60, both inside the spread. The
arm ordering flips between seeds (est wins A by 123, heur wins B by 29
and C by 18).

### Q3 — composite-σ floor sweep (Task 10, seed base 20260827)

| floor | global σ | total |
|---|---|---|
| 0 (= pure estimation) | 0.069 | 1908 |
| 0.3 | 0.308 | 1887 |
| 0.6 | 0.604 | 1869 |
| 1.0 | 1.002 | 1862 |
| (heuristic reference) | — | 1785 |
| (raw reference) | — | 1914 |

Monotone decline: every unit of added noise costs points on this seed;
no floor approaches raw, let alone beats it by the spread. There is no
re-noised gate worth shipping.

### Verdict (spec §2's mechanical rule) — KEEP AS-IS (option b)

- No composite floor beats raw's mean by > spread (116): all floors are
  BELOW raw. Re-noise: ruled out.
- Raw (1914) beats the best gated arm's mean (estimation, 1879.3) by
  34.7 < 116. Remove: not justified — the difference is inside seed
  noise.
- → Keep as-is. The estimation-σ default shipped in v7-model stands;
  its ~5-minute scenario cost buys plan-stability information (the sim%
  labels) and costs ≈35 replay points relative to raw, a difference
  indistinguishable from draw luck.

Open question this cycle deliberately leaves: whether to expose a
config switch to skip the sweep entirely (raw mode) for speed — a UX
choice, not a points choice, on this evidence.

### N2 — still pending at cycle close

GW2 not `data_checked` (checked repeatedly through 2026-08-30; final
check at close). The watcher pipeline stands: on data_checked →
`gaffer refresh` → `gaffer evaluate --news-shadow` → record here and
verify the Model-hub scoreboard.

### Cycle summary

11 replay runs + 1 probe, exactly the plan's mandatory+conditional
matrix. Q2 answered (v5 minutes-head swap reversed gating's sign; swap
still justified, +47 ungated), Q1 answered (seed spread 116 swamps every
arm difference), Q3 answered (no composite floor helps). The v7-model
three-way decision is now error-barred and the user's option (b) stands
confirmed as within-noise of the best available configuration.

## 6. Review corrections (pre-merge, 2026-08-30)

The pre-merge review recomputed every §5 figure from the raw logs (all
correct) but required these corrections to the *claims*:

- **Q2 downgraded from "answered" to "attributed with a named residual".**
  The two Q2 deltas (−61 and +27) are one seed base each, and Q1 measured
  the heuristic arm's seed spread at 116 — the 88-point delta-vs-delta
  swing sits inside it. The minutes-head attribution is *consistent with*
  the evidence and is the only surviving candidate (frame ruled inert,
  harness ruled out, scoring unchanged since v4c), but it is not
  error-barred; treat it as the named residual, not settled fact. The
  "noise placement" mechanism sentence is a post-hoc story no arm tested —
  the probe falsified the pre-registered scale mechanism (0.2% apart) and
  no replacement mechanism was measured.
- **Scope**: one season (2025-26), one replay harness; three seed bases
  buy an error bar on the seed, not on the season. The §2 rule compares
  point differences against a 3-sample range — a deliberately lenient,
  low-power test; "within noise" is a failure to distinguish, not a
  demonstration of equality.
- **Q1 provenance**: the 20260827 column reuses the v7-model S2 runs
  (scripts/s2_replay.py, pre-_ArmStore — totals sound, hits/transfers
  from a shared parquet); 20260901/20260915 ran through v7b_replay.py
  (defaults pinned equal by test). A same-seed raw arm re-run through
  v7b_replay.py (`verdict-raw`, appendix) anchors the cross-driver and
  raw-provenance questions empirically.
- **Verdict sensitivity**: keep-as-is survives raw ∈ [1771, 1995], so the
  recommendation does not turn on the anchor's exact value.
- **"+104 model improvement since v4c" softened to "consistent with"** —
  the v4c raw figure came from a deleted driver on an older data snapshot.
- **Frame inertness** rests on the static argument (a0f314f withdrew the
  columns; no feature list names them), with the one-GW probe as
  corroboration only.
- Deferred nit: the driver's asset-guard SystemExits (source/floor
  refusals) are untested; the argparse layer is.

## 7. Evidence appendix — every arm's log line (logs/ is gitignored;
this is the durable record)

Q2 (chips off, priors off, seed base 20260825):
```
V7B_ARM_DONE q2-ctrl-heur   {"total": 1786, "hits": 17, "transfers": 49, "gated_weeks": 33, "held_weeks": 4}
V7B_ARM_DONE q2-ctrl-raw    {"total": 1847, "hits": 12, "transfers": 45, "gated_weeks": 0,  "held_weeks": 0}
V7B_ARM_DONE q2-legacy-heur {"total": 1827, "hits": 20, "transfers": 51, "gated_weeks": 33, "held_weeks": 8, "minutes": "legacy"}
V7B_ARM_DONE q2-legacy-raw  {"total": 1800, "hits": 20, "transfers": 52, "gated_weeks": 0,  "held_weeks": 0, "minutes": "legacy"}
```
Q1 (chips on, priors current):
```
S2_ARM_DONE  heur     seed 20260827 {"total": 1785, "hits": 15, "transfers": 69, "held_weeks": 8}   (v7-model run, reused)
S2_ARM_DONE  est      seed 20260827 {"total": 1908, "hits": 11, "transfers": 64, "held_weeks": 2}   (v7-model run, reused)
V7B_ARM_DONE q1b-heur seed 20260901 {"total": 1876, "hits": 9,  "transfers": 61, "held_weeks": 6}
V7B_ARM_DONE q1b-est  seed 20260901 {"total": 1847, "hits": 13, "transfers": 66, "held_weeks": 2}
V7B_ARM_DONE q1c-heur seed 20260915 {"total": 1901, "hits": 9,  "transfers": 63, "held_weeks": 7}
V7B_ARM_DONE q1c-est  seed 20260915 {"total": 1883, "hits": 9,  "transfers": 62, "held_weeks": 4}
```
Q3 (chips on, priors current, seed base 20260827):
```
V7B_ARM_DONE q3-f03 {"total": 1887, "hits": 9,  "transfers": 62, "composite_floor": 0.3, "global": 0.307878}
V7B_ARM_DONE q3-f06 {"total": 1869, "hits": 14, "transfers": 66, "composite_floor": 0.6, "global": 0.603977}
V7B_ARM_DONE q3-f10 {"total": 1862, "hits": 17, "transfers": 67, "composite_floor": 1.0, "global": 1.002391}
```
Raw anchor (v7b_replay.py, chips on, priors current, seed base 20260827):
```
V7B_ARM_DONE verdict-raw {"total": 1914, "hits": 11, "transfers": 64, "gated_weeks": 0, "held_weeks": 0, "config": {"arm": "raw", "seed_base": 20260827, "n": 40, "chips": true, "priors": "current", "minutes": "current"}}
# = the review's previously-unlogged anchor, reproduced exactly through v7b_replay.py:
# raw provenance, raw determinism, and cross-driver equivalence all confirmed in one run.
```
