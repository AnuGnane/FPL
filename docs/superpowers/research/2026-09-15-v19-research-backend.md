# v19 backend/model research — 2026-09-15 (read-only)

Numbers from the live tree: `reports/components_gw4.parquet` (1,965 rows, GW4–6),
`models/*.joblib`, `data/live/*.parquet`.

## 1. The model cycle, costed

**Replay mechanics.** `--seed-base` feeds the noise draw (`scripts/v7b_replay.py:313,374`),
not a head's `random_state` — `LGB_KW` sets `random_state=7` and samples neither rows
nor columns, so a refit alone has zero spread (`models/minutes.py:26-40`).
`backtest.py:455` calls `train_all(save=False)` per fold, so **every** arm below is
refit → CONVENTIONS §9 puts all three at K ≥ 5. At CLAUDE.md's ~20 min/seed, serial:
10 seeds (arm + raw control) ≈ **3.5–4 h** per arm.
### C12 — bound `e_gc_model`/`p_cs_model` · **rank 1**
`DixonColesModel.predict` (`models/dixon_coles.py:290-320`) exponentiates unbounded
attack/defence (`PARAM_BOUNDS = (-3,3)`, `:122`) into `lam`/`mu` with no floor;
`fixture_outcomes` (`:96`) turns that into `p_cs`/`e_gc`. `predict.py:158-166` keeps the
raw pair and overlays market at the fitted **w = 0.8** (`models/blend.params.json`).
**Live, not hypothetical.** Over GW4–6's 60 club-fixtures `p_cs_model` spans
0.085 → 0.957, 6 have `e_gc_model < 0.3` (min **0.044**), and **all 20 GW6 fixtures
carry `odds_weight = 0`** — a third of the MILP's horizon is priced on the raw model
with no market to launder it. `ep_cs` is **29.8%** of DEF/GKP `ep_uncalibrated`.
Change: floor/ceiling on `lam`/`mu` inside `predict`, flagged. Refit → K ≥ 5.
**Ships without a replay:** the diagnostic half — a degradation test asserting served
`p_cs` stays in band, and a Model→Health row naming the week's min `e_gc_model` and
the zero-odds fixture count. Only the clip itself is gated.
### C11 — bonus head sees goals/assists/position · **rank 2**
`BONUS_FEATURES` is still the eight of 09-04 (`models/components.py:111-112`); the fitted
`bonus.joblib` `cols_` confirms it. `predict.py:140-146` runs attacking and bonus as
independent predictions over one frame, so `e_goals` never reaches bonus. On GW4 the
board's **top `e_bonus` is Rúben, DEF, `e_goals 0.000`, `e_bonus 1.551` — above
Haaland's 1.437**; Ndiaye (`e_goals 0.028`) is 6th at 1.192. Change: add the three
features, order bonus after attacking in `predict.py:140`, flagged. Refit → K ≥ 5.
Tempering: `ep_bonus` is only **7.2%** of `ep_uncalibrated` at `p_play > 0.5`, so this
redistributes 7% of the objective — less per replay-hour than C12.
### C13 — GKP calibration delta · **rank 3, already free**
`models/calibration.joblib` now reads `{GKP 0.428, DEF 1.062, MID 1.147, FWD 0.993}` —
**the GKP row exists**; the 200-row floor (`models/calibrate.py:41`) was met by accrual.
The candidate as written is closed. What remains costs no replay: a rail that `by_pos`
has four keys, and a health line rendering "not fitted (n < 200)" when one drops out.
**Do it first; it is an hour.**
### Role replay (K ≥ 5) · rank 4
`ROLE_FEATURES` out of `MINUTES_FEATURES` on the off-side branch; ~1 h per three seeds a
side → ≈ 3.5 h at K = 5 both sides. Decides what already ships; the post-hoc K=3 (−27)
was inside its spread. Cheapest of the gated four.
### C1 news ablation · rank 5
Buckets + K ≥ 5, ≈ 4–5 h plus analysis, and the payoff is "retire or keep the v5/v6
subsystem", not points this season. `news_shadow` already leans that way (Brier 0.1276
news vs 0.1191 plain flags).
**Also free: bank the pre-blend `e_goals`.** `artifacts.py:46` banks
`p_cs_model`/`e_gc_model` but no `e_goals_model`. 25 of 1,965 GW4 rows still carry
`e_goals > 0.9` and **all 25 have `p_play < 0.1`** — the `AGS_EG_CAP` artifact
(`data/odds.py:692`) is intact and still biases every evaluation reading the components
file. Banking the column changes no served number; skipping the blend would.

## 2. Data-gated rows — what can be read now

| Row | Reading today | Verdict |
|---|---|---|
| W2 §3.1 flag latency | `availability_log.parquet` **14** distinct `snap_date` (08-30 → 09-15, gaps 09-07/13/14); GW1–3 graded | **unblocked** |
| W2 §3.2 presser grading | GW3 graded | met |
| W2 §3.3 EO trend | `field_eo_log.parquet` GWs {2, 3} | met |
| W3 §4.5 WC+BB pair | `data/chip_scenarios.toml` **does not exist** | blocked |
| W4 §5.3 P(top-10k) | no source | blocked |
| W4 §5.3 rank change | ledger 3 GW rows, **2** with both `my_points` and `overall_rank` (GW2 2,562,053; GW3 989,795; GW1 null) | blocked, ~GW7 |
| W4 §5.1 Elo | publisher | out of our hands |
| W5 §6.5 price-timing line | `price_log.parquet` **11 days, 656 codes, median 11 rows/code, 1 calibrating row** | **unblocked** |
| W5 §6.4 review snapshot | GW3 row | met |
**Operational:** `price_log.parquet` last written **2026-09-11 23:15**, `player_gw.parquet`
09-11 13:41 — prices and refresh have not run in four days, consistent with "2 of 9
launchd jobs loaded".

## 3. Not replay-gated, ranked (file:line · change · size)

1. **Add `prices` and `snapshot` to the freshness strip** (`web/routers/meta.py:255-261`
   lists only refresh/odds/field/advise/backup). The one input that silently degrades the
   objective is the one the strip cannot show; give each row its job's cadence so 90 h
   reads red for a daily job and normal for odds. **S**
2. **Bank `e_goals_model`** (`artifacts.py:46`, `models/predict.py:158`) — removes the
   +0.05 `e_goals` evaluation bias without touching `ep`. **S**
3. **`weekly_run` banks a price reading first** (`pipeline.py:56-68` has no price step).
   Closes the web re-run residual *and* the stale installed advise plist at once, since
   all three callers share the body. Arguably an input refresh rather than a
   served-number change — record the ruling; remember CONVENTIONS §10. **S**
4. **`tidy` for the API snapshots** (`tidy.py:9-12` scopes them out). `data/raw/` is
   **184 MB**: 51 MB in 557 top-level timestamped JSONs, 89 MB under `data/raw/news/`.
   A third target with keep-newest-N. **M**
5. **Freeze the trace's price line at solve time** (`trace.py:255-285`: switch and charge
   are read when the board is drawn because nothing on `SolveState` records what the solve
   saw). Touches `advise.py` → needs a ruling. **M**
6. **`schemas.py` field docstrings**: 1,000 annotated fields, 161 classes, **149
   documented (15%)** — the whole lost-`types.ts`-comment residual, mechanical per
   router. **L**
7. **Render `threshold_source`**: served at `advise.py:1017` and `optimize/chips.py:349`,
   typed at `web/schemas.py:765,807,838`, greps to nothing in `frontend/src`. Caption it
   or delete the field. **S**
8. **Ledger season key**: `review.py:1091,1110` key on `gw` alone; one migration plus a
   reader filter, before a rollover makes GW1 ambiguous. **M**
9. **`starred_at`**: `watchlist.py:143` writes `set_at` as the note's stamp and `:110`
   preserves it, so the column can only read "noted". **S**
10. **210 `# noqa: BLE001`** of 223 — all `except Exception` swallows; `digest.py` 19,
    `ladder.py` 11, `cli.py` 11. A convention (name what you catch), not a sweep. **M**
**Smells worth a ruling, not a task:** `build_advice` 513 lines (`advise.py:733-1246`)
and `gather_inputs` 271 (`:461-732`), both pinned by source-order rails so they can only
grow; `_solve_once` 360 lines (`optimize/milp.py:615-975`) with `solve_plan` taking 12
keyword args (`:468-478`); `web/schemas.py` 2,414 lines, 161 classes, no owner.

## 4. Code health numbers

`web/schemas.py` 2414 · `features/engineer.py` 1870 · `evaluation.py` 1361 · `review.py`
1301 · `advise.py` 1280 · `league_sim.py` 1225 · `artifacts.py` 1086 ·
`optimize/milp.py` 1028 · `ladder.py` 1020 · `cli.py` 928 (44,573 total).
`# noqa` **223** (BLE001 210, F401 11, E731 1, E402 1) · `type: ignore` **0** ·
`TODO/FIXME/XXX` **1**.
`Config` fields **62** (matches the pin). Scanning each for a `.field` read in
`src/gaffer` outside `config.py`: exactly one is never read — **`field_sample`**
(`config.py:199`, parsed at `:619`). Wire it or drop it; dropping moves the pin, so it
needs its own commit.

## 5. What I would leave alone

The MILP and the ladder — protected, heavily railed, and nothing here points at a defect
in either. The odds blend weight: 0.8 is fitted under a 1-SE rule whose reasoning
(`models/team.py:200-226`) beats any guess a cycle would substitute. The restraint policy
and the walk's hit asymmetry: v16 measured it over a season; re-litigating costs 4 h to
confirm a recorded result.
