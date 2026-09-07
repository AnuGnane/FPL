# Current-state review — gaffer, 2026-09-04

Read-only audit against `v13-ladder` at `1956d58` (identical to `main`; tree
clean). Every claim is a `file:line` or a number computed with `.venv/bin/python`
against the banked artifacts. Nothing was modified.

## Executive summary

1. The engineering is genuinely strong: 40,445 lines of Python (132 files),
   25,797 of frontend, ~4,042 Python + ~795 frontend tests (counted and
   confirmed), zero errors in every job log, and three pin counts that all
   verify — routes 47, `JOB_KINDS` 12, `Config` 55.
2. The model is the weak half, and the weakest head is **bonus**. It never sees
   expected goals: on 12,120 banked appearances `corr(bonus, goals in that
   match) = 0.624`, while its strongest actual feature correlates **0.141**.
3. Consequence: Haaland at home to Coventry gets `e_bonus 0.227`; a non-scoring
   City midfielder gets 0.85. A goal-aware estimator moves Haaland **+1.00 xPts**
   and pulls six inflated rotation names down 0.4–0.7.
4. `e_goals ≈ 1.0` on ~27 fringe players a week is not a default — it is
   `lambda_ags / p_play` clipped at 2.0 (`data/odds.py:692`). Harmless to `ep`
   (the divisor cancels), but it lifts the banked `e_goals` mean from 0.096 to
   0.148 and contaminates every evaluation that reads the artifact.
5. Dixon-Coles is producing impossible numbers: `e_gc_model 0.035` for Man City,
   `0.060` for Hull, `p_cs_model 0.125` for Liverpool away where the market says
   0.40. Only the fitted 0.8 odds blend hides it — and the documented "no odds
   key" degradation path would ship it raw.
6. Guéhi's 7.61 vs FPL's 6.0 is `ep_cs 2.83 + ep_minutes 1.84 + ep_goals 1.25 +
   cal_delta 0.92`. The goals line prices a centre-back at the highest DEF
   `e_goals` in the league, 6× the DEF median.
7. **The calibration report has never run on real data.** `cli.py:625` hard-codes
   `season = "2025-26"`; `data/live/player_gw.parquet` holds only 2026-27, so the
   banked block reads `n: 0` for every head. Run correctly it grades 618 rows now.
8. **No backup has ever run.** `~/gaffer-backups` does not exist; 2 of 9 plists
   were never installed and a third installed copy is stale.
9. Decision quality is unmeasurable — **one graded gameweek**. Captain 1/1,
   transfers +3, every other lane Aligned or null. The docs are honest about this.
10. Do next: install automation → fix the calibration season default → feed
    `e_goals` to the bonus model → bound Dixon-Coles.

---

## 1. Bonus model — the clearest structural defect

`BonusModel` (`models/components.py:114`) is one LightGBM regressor over eight
features (`components.py:111`): `bps_r3, bps_r5, bps_r38, xgi_r5, bonus_r5,
bonus_r38, elo_diff, home`, predicted as `.clip(0, 3)` (`components.py:142`).
Fitted importances from `models/bonus.joblib`: `xgi_r5` 1781, `elo_diff` 1493,
`bps_r5` 1396, `bps_r38` 1350, `bps_r3` 1243, `bonus_r38` 1147, `bonus_r5` 408,
`home` 182.

There is **no position feature, no `e_goals`, no `e_assists`, no minutes**. The
only forward-looking attacking signal is `xgi_r5`, a five-match lagged mean.
`advise.py:434-441` runs the attacking and bonus heads as independent predictions
over the same frame; they never meet.

**Why that is fatal for a striker.** From the banked history
(`load_training_frame()`, `minutes > 0`, `season_idx >= 3`, n = 12,120), mean
actual bonus by goals scored in the match: **0 goals → 0.092** (n=11,152),
**1 → 1.447** (n=877), **2 → 2.795** (n=83), **3 → 3.000** (n=8). Split by
position and whether the player scored: FWD no-goal **0.007** (n=1,202) vs
scored **1.687** (n=300); MID 0.064 vs 1.605; DEF 0.123 vs 1.213.

A forward who does not score earns **0.007 bonus points** across 1,202
observations. Bonus for an attacker is essentially `P(scores) × 1.6`. And:

Correlations with actual bonus: goals **0.624**, assists 0.235, `xgi_r5` 0.156,
`bps_r38` 0.141, `bps_r5` 0.128, `bonus_r5` 0.110. The model is fitted on the six
weakest of those and denied the strongest.

**What it costs today.** In `reports/components_gw3.parquet`, Haaland home to
Coventry: `e_goals 0.995`, `e_bonus 0.227`. Same fixture: Semenyo (`e_goals
0.527`) 0.850, Anderson (`e_goals 0.140`) 0.757. League-wide for `p_play > 0.5`,
mean `e_bonus` is 0.325 (FWD) vs 0.233 (MID) vs 0.173 (DEF) — it barely
separates positions. The top of the `e_bonus` table is led by Truffert (DEF,
`e_goals 0.038`, `e_bonus 0.856`) and De Cuyper (DEF, 0.036 → 0.852).

Graded against GW2 actuals (`data/live/player_gw.parquet`, 310 rows that played):

| pos | n | mean `e_bonus` | mean actual | corr |
|---|---|---|---|---|
| DEF | 111 | 0.152 | 0.144 | 0.185 |
| MID | 146 | 0.188 | 0.219 | 0.132 |
| FWD | 33 | 0.289 | 0.424 | 0.034 |
| GKP | 20 | 0.187 | 0.150 | −0.345 |

The **level** is roughly right; **discrimination is near zero**. By `e_goals`
bucket (played, `p_play > 0.3`), predicted vs actual bonus: 0–0.05 → 0.161/0.163
(n=104); 0.05–0.10 → 0.176/0.159 (n=63); 0.10–0.20 → 0.221/0.281 (n=57);
0.20–0.35 → 0.400/0.400 (n=25); 0.35–0.60 → 0.303/**0.667** (n=6); 0.60+ →
0.136/**3.000** (n=1). Players who actually scored in GW2 (n=25): predicted
0.232, actual **1.680**.

**Size of the fix.** Substituting `E[bonus] = Σ_k P(goals=k | λ=e_goals) ·
mean_bonus(position, k)` for the model's `e_bonus` on GW3 (`p_play > 0.5`,
n=335) gives mean Δ = −0.007 xPts (level unchanged) but mean |Δ| = **0.108**.
Pure redistribution: Haaland **+1.00**, Saka +0.55, Szoboszlai +0.37; E.Le Fée
−0.67, De Cuyper −0.66, M.Sangaré −0.61, Truffert −0.49, Mbeumo −0.38.

**Verdict: yes, a goal-dependent striker is structurally underrated — and the
mirror error, inflating non-scoring rotation players, is just as large.**

---

## 2. `e_goals ≈ 1.0` on unknown players — an odds artifact, not a default

27 GW3 rows carry `e_goals > 0.9`; **25 of them have `p_play < 0.05`** (Gittens
1.036, Cherif 1.032, four Hull players at exactly 1.029, Anselmino 1.010). The
identical values within a club give it away.

It is not the attacking model. Reconstructing Gittens' real serve-time feature
row through `build_prediction_frame` and calling `models/attacking.joblib`
directly returns **0.071**; the banked value is 1.036. Nor is it a NaN default —
an all-NaN row returns 0.069 (MID) / 0.216 (FWD).

The source is `blend_attacking_odds` (`data/odds.py:664-696`):

```python
out.loc[has, "e_goals_odds"] = (
    out.loc[has, "lambda_ags"] / p_play[has]).clip(upper=AGS_EG_CAP)   # :692
out.loc[has, "e_goals"] = w * e_goals_odds + (1 - w) * e_goals        # :694
```

`AGS_EG_CAP = 2.0` (`odds.py:404`), `w = 0.5` (`config.py:63`). The market's
per-fixture anytime-goalscorer λ is divided by `p_play` to make it a
per-appearance rate; at `p_play = 0.008` that explodes, hits the cap, and the
blend lands at `0.5 × 2.0 + 0.5 × 0.07 ≈ 1.03`. The docstring at `odds.py:672`
says exactly this is why the cap exists.

**Can it leak?**
- **`ep`: no.** `assemble_ep` multiplies by `p_play` (`assemble.py:100`, `:175`),
  which is the divisor. Gittens contributes 0.10 to a 0.14 xPts total. The clip
  makes the number *smaller*, not larger.
- **`p_haul`: no** — `assemble.py:113-116` multiplies by `p_play` first.
- **Captain options, pool, UI: no.** They rank on `ep`; grep of `src/gaffer/web/`
  and `frontend/src/` finds no raw `e_goals` consumer.
- **Evaluation and calibration: yes.** They read the banked
  `components_gw*.parquet` columns directly. Over GW2's 620 rows the fringe rows
  lift mean `e_goals` from **0.0964 → 0.1475**; the "+0.101 `e_goals` bias" a
  full-frame evaluation reports is more than half this artifact.

**Verdict: harmless to advice, misleading in the artifact.** A bug of the
recorded value, not the served one. The fix is one condition — skip the blend
where `p_play < 0.1`. Worth noting the cap binds on ~5% of rows every week, so
it is not a rare edge case.

---

## 3. Guéhi 7.61 vs FPL's 6.0

Banked GW3 row (code 209036, Man City home to Coventry): `ep_minutes 1.838` ·
`ep_goals` **1.251** (`p_play 0.938 × e_goals 0.2222 × 6`) · `ep_assists 0.074` ·
`ep_cs` **2.829** (`p60 0.900 × p_cs 0.7857 × 4`) · `ep_gc −0.111` ·
`ep_defcon 0.377` · `ep_bonus 0.580` · `ep_cards −0.145` → `ep_uncalibrated
6.693` + `cal_delta` **0.920** = **7.612**.

**(a) `e_goals 0.222` for a centre-back is the league's highest DEF value.** The
GW3 DEF distribution for `p_play > 0.5` (n=104) is mean 0.044, median 0.037,
max 0.222 — Guéhi *is* the max, at **6× the median** and 1.5× the next DEF
(Rúben 0.147). He carries neither `pen_taker` nor `setpiece_taker`. His features
explain it: `goals_r5 0.20`, `xg_r3 0.297`, `xg_r5 0.208`, `goals_r38 0.105` — a
three-match xG run extrapolated into a per-appearance rate. The raw model output
was **0.328**; the AGS blend halved it to 0.222, i.e. the market disagreed by
2.8× and a 0.5 weight only met it halfway. `ep_goals` alone is 1.25 of the 7.61.

**(b) The clean-sheet chain is the biggest term and rests on a broken model.**
`p_cs_model 0.9654`, `e_gc_model 0.0352` — Man City modelled to concede 0.035
goals. Across the 20 GW3 club-fixtures:

| club (GW3) | `p_cs_model` | `e_gc_model` | market xGA | blended `p_cs` |
|---|---|---|---|---|
| Man City v Coventry | **0.965** | **0.035** | 0.30 | 0.786 |
| Hull v Aston Villa | **0.942** | **0.060** | 1.65 | 0.342 |
| Liverpool @ Ipswich | **0.125** | 2.079 | 0.75 | 0.403 |
| Aston Villa @ Hull | 0.196 | 1.628 | 1.00 | 0.334 |

`p_cs_model` spans 0.050 → 0.965, mean 0.315. The three promoted clubs and their
opponents are where it detonates — thin 2026-27 history, attack/defence strengths
saturating. The odds blend is **fitted at w = 0.8** (`models/blend.params.json`,
1,520 rows, `models/team.py:248`), so 80% of `p_cs` is market and the model's
absurdity is laundered away. But `GUIDE.md` §3 still documents "blended 70/30",
and §1's third design principle promises graceful degradation when there is no
odds key. **The layer below currently says Man City keep a clean sheet 96.5% of
the time and Liverpool 12.5%.** If the key expires, the advice silently rots.

Even the blended 0.786 is aggressive: it derives from market
`e_goals_against = 0.30`, i.e. `exp(−0.30) = 0.741`. A real bookmaker line for
City v a promoted side is nearer 0.55–0.60 xGA — the totals→xGA derivation in
`odds_frame` deserves a spot-check against the raw snapshot in `data/raw/`.

**(c) `cal_delta +0.92` is not Guéhi-specific.** `CalibrationModel.by_pos =
{DEF: 1.0217, MID: 1.1869, FWD: 1.2544}`, applied as `p60 × delta[position]`
(`calibrate.py:65,79`). **GKP has no fitted delta at all** (the ≥200-row floor at
`calibrate.py:41` was not met), so keepers get zero correction while every
outfielder gets +0.66 to +0.70 on average. It is a flat level shift that fixes
bias, not dispersion: on GW2 it moved starter bias from −0.922 to −0.171 while
MAE got *worse*, 2.234 → 2.391.

**Verdict:** ~1.25 of the gap is a defender priced as a striker, ~0.6 is an
over-optimistic clean-sheet chain, 0.92 is a blanket positional add-on. FPL's
6.0 is closer to right.

---

## 4. Calibration health — the report has never run on real data

`cli.py:625` declares `season: str = "2025-26"` and passes it through
(`cli.py:642` → `evaluate_calibration(season=season)`), while the function's own
default is `None` (`evaluation.py:823`). `data/live/player_gw.parquet` contains
**only 2026-27** (1,236 rows: GW1 610, GW2 626). The filter empties the frame and
the banked block reads `gameweeks: []`, `n: 0`, `brier: null` for all four heads
with the note "No graded gameweeks yet."

Re-run read-only against `"2026-27"` it grades **618 player-fixture rows**:

| head | n | Brier | log loss | worst bin |
|---|---|---|---|---|
| `p_play` | 618 | 0.1255 | 1.0835 | lowest bin **0.011 predicted → 0.126 observed** (n=246, 11× under) |
| `p60` | 618 | 0.0874 | 0.4906 | 0.753 → 0.970 (n=33) |
| `p_haul` | 618 | 0.0170 | 0.0710 | 0.271 → 0.038 (n=26); 0.309 → 0.000 (n=12) — over-confident |
| `p_cs` | 20 | — | — | under the 30-row floor; raw 0.272 predicted vs 0.200 observed |
| `p_start` | — | — | — | never banked (`artifacts.py:36-51`) |

Component bias on GW2 (all 618 rows / 207 starters ≥60'): `e_goals` 0.148 vs
0.047 (**+0.101**, over half of it the §2 artifact) / 0.088 vs 0.126 (−0.037);
`e_assists` +0.017 / −0.039; `e_bonus` +0.033 / **−0.091** (MAE 0.437); `ep`
+0.242 / −0.171 (MAE 2.391); `ep_uncalibrated` starters **−0.922**. Consistent
story: too much attacking and bonus mass on players who did not start, too little
on those who did.

The **health tab shows less than that.** `reports/health.json` is 100 bytes
entire: `{"gw": 2, "mae_starters": 2.38, "captain_actual": 23, "advice_pts":
null, "actual_pts": null}`. Written by `update_health()` (`tracking.py:55`); the
two nulls are structural — `compute_health` takes them as optional args
(`tracking.py:18-20`) and the only caller passes neither (`tracking.py:53`), so
they can **never** be populated. Served verbatim as `model_health` on
`/api/health` (`web/routers/meta.py:334-337`).

Everything else is older or on another season: `current` (2025-26 holdout,
starters RMSE 3.397 / MAE 2.516, n=1,989), `benchmark` (test season **2024-25**,
n=26,919, all-RMSE 1.966), `decomposition` (2025-26: model_h3 1,931 vs oracle_h3
4,336), `news_shadow` (GW2 only: Brier news 0.1276 vs plain FPL flags **0.1191**
— the news layer is losing), `pen_tracker.json` (GW1: `predicted_ep_pen_taker
0.0` against 2 penalties actually taken, 7.02 points realised).

---

## 5. Operational state

**launchd: 7 of 9 loaded**, all last exit code 0 — `prices` (23:15 daily),
`snapshot` (17:00), `advise` (Thu 18:00), `review` (Tue 09:00), `digest-tuesday`
(Tue 09:30), `digest-friday` (Fri 17:00), `field` (Sat/Sun 12:30). Not loaded,
matching `GUIDE.md:629-644`: `com.gaffer.backup` (23:45, tars ~16 MB of
unrebuildable state) and `com.gaffer.core-insights` (06:30, 18:30).

**A third drift the docs do not record:** the *installed*
`~/Library/LaunchAgents/com.gaffer.advise.plist` (Aug 31) is behind
`scripts/com.gaffer.advise.plist` (Sep 2). The repo version runs `gaffer prices`
before `train && advise`; the installed one does not. So the Thursday run has
been solving with a stale price table — the same residual §12.4 records for the
web re-run button, silently also true of the cron job. The other six installed
plists are byte-identical.

**Backup: never run.** `~/gaffer-backups` does not exist, no `[backup]` section
in `config.toml`, no `logs/backup.log`, zero `gaffer-*.tar.gz` on disk.
`data/raw/field/`, `data/raw/tier_eo/` and `data/live/` cannot be re-fetched from
any API and are unprotected.

**Freshness (2026-09-04):** `data/live` (95 files) and `reports` (122) both
written within the hour; `data/raw` 163M/3,234 files, newest 15:01 today;
`models` 14M, all one run Sep 3 18:56; `data/history` Aug 26 (by design,
rebuildable). The exception is **`data/core_insights` — all 9 files stamped
2026-09-03 02:04, one frozen manual run**, which will never refresh until its job
is installed. `grep -ci 'error\|traceback'` over every job log returns **0**.

---

## 6. Test and code health

`src/gaffer`: **132 files, 40,445 lines** — `web/` 9,505 · `data/` 6,948 ·
`optimize/` 2,902 · `models/` 2,722 · `features/` 2,225 · **root `*.py` 15,847
(39%)**. The root module (`evaluation.py`, `review.py`, `league_sim.py`,
`advise.py`, `artifacts.py`, `cli.py`, `digest.py`, `backtest.py`) is the largest
grouping and is not a package. `frontend/src`: 154 files, 25,797 lines
(`hubs/` 17,497, `kit/` 3,628).

Largest Python: `web/schemas.py` 2,108 · `features/engineer.py` 1,870 ·
`evaluation.py` 1,363 · `review.py` 1,296 · `league_sim.py` 1,214 · `advise.py`
1,177. Largest non-generated frontend: `hubs/model/QualityTab.tsx` 1,056.

Tests: **239 Python files, 57,857 lines, 3,877 `def test_` + 40 `parametrize`**
(consistent with the documented 4,042 at `GUIDE.md:619`); **79 frontend files,
768 `it(`/`test(` + 4 `.each` tables** (consistent with 795). The counts check
out — the docs are not inflated.

**Debt callouts: there are none.** No `GUIDE.md` section names a module as debt.
"debt" appears only as cycle names (`ROADMAP.md:253` v9c, `:263` v9d, both
closed). "refactor" appears almost entirely as a *prohibition* —
`plans/2026-09-02-gaffer-v10b.md:1678` declines a duplicated map because the
refactor "would open a router this cycle otherwise never touches". Defensible,
but it means the two biggest files (`schemas.py` 2,108, `engineer.py` 1,870) have
no owner and no plan.

**Pins — all three verified equal to their documented values:** routes 47
(`tests/test_v11_degradation.py:368`, "the only absolute route pin in the
suite"), `JOB_KINDS` 12 (`tests/test_v12_w3_degradation.py:514`, `w4:210`,
`w5:27,126`), `Config` fields 55 (`tests/test_v12_w3_degradation.py:536`).

**The v13 cycle is a design document with zero implementation.** `v13-ladder` is
byte-identical to `main` (`git log main..v13-ladder` empty, both `1956d58`).
`specs/2026-09-04-gaffer-v13-transfer-ladder-design.md:333` states "Pins after:
routes 49, `JOB_KINDS` 12, `Config` 57" and `:276` names
`tests/test_v13_degradation.py` — that file does not exist and nothing asserts 49
or 57. The target pins are documented; the code is not started.

---

## 7. Decision quality — one graded gameweek, and that is the whole story

`reports/decision_ledger.json` holds **2 rows (GW1, GW2)**; `journal.json` 1;
`league_sim_history.json` 1; `reports/advice_history/` 20 files (2 for GW2, 18
for GW3). GW3's deadline is today and it is ungraded.

**GW1** — `no_advice: true`. You scored 46 (reconciled, 0 hits); hindsight best
XI from your own 15 was 55. All four lanes null, `overall_rank` absent, and no
`components_gw1.parquet` — which is why calibration lists GW1 as `missing`.

**GW2** — the only graded week. You 99 (gross 99, 0 hits, wildcard played; the
model also said wildcard). Lanes: **transfers +3 ("Good")**, captaincy 0
(Aligned), bench 0 (Aligned), chip ungraded. `model_points: 96` is the
*composite counterfactual* — your squad with each comparable lane swapped to the
model's (`review.py:766-790`) — not the model's own team. `accuracy: 100` is
`100 × my/model` **capped at 100** (`review.py:818`); the raw ratio is 103.
`overall_rank 2,562,053`. 17 points on the bench; hindsight best XI 110.
Transfers: the model said Mitchell→Egan, Hughes→Szoboszlai, Wilson→Groß,
Gibbs-White→Gakpo; you made all four incoming moves plus a round-trip
James→Truffert→James, so the ledger marks `aligned: false` but `delta_pts +3`
**in your favour**. Captain: 1 of 1 aligned — both picked B.Fernandes, 23 points,
the gameweek's highest and the hindsight XI's own captain.

Season totals across both gameweeks: transfers +3.0 (1 graded, 1-0), captaincy
0.0 (1 graded), bench 0.0 (1 graded), chip 0.0 (0 graded), `delta_pwin` **null on
every lane** ("your entry is not in the simulated league"), 19 points on the
bench, hindsight gap 20, 2/2 reconciled, `misses: []`.

**A discrepancy worth knowing:** `journal.json` says GW2 model 107 vs actual 99,
**+8 to the model**; the ledger says model 96 vs 99, **+3 to you**. Opposite
signs because they measure different things — the journal scores the model's own
recommended XI gross (`journal.py:33-40,152-155`, no hit cost), the ledger scores
your squad with model lanes applied. Anything reading both looks contradictory.

League sim: one run, GW3, n=2,000, `p_win 0.0005` — one simulated win in 2,000,
indistinguishable from zero at that granularity.

**Verdict: nothing can be concluded.** One graded gameweek, one captain call, one
transfer verdict. The honest statement is "GW2: you scored 99, the composite
counterfactual scored 96, captain aligned and optimal."

---

## What I would do next — ranked

1. **`./scripts/install_automation.sh`.** No backup has ever run and
   `data/raw/field/`, `data/raw/tier_eo/` cannot be re-fetched. It also fixes the
   stale installed `advise` plist that has been skipping `gaffer prices`.
   *Verify:* `launchctl list | grep com.gaffer | wc -l` → 9; tomorrow
   `ls -la ~/gaffer-backups` shows a ~16 MB tarball; `diff` the advise plist
   against `~/Library/LaunchAgents/` and get nothing.

2. **Change `cli.py:625` from `season: str = "2025-26"` to the configured current
   season** (or `None`, letting `evaluation.py:823` decide). The whole calibration
   surface has been reporting `n: 0` on a data-shortage story that is not true.
   *Verify:* `uv run gaffer evaluate --calibration` then
   `jq '.calibration.p_play.n' reports/evaluation.json` → 618, not 0.

3. **Feed `e_goals`/`e_assists` and `position` to the bonus model.** Largest
   measurable model error found: `corr(bonus, goals) = 0.624` vs 0.141 for its
   best current feature; a naive goal-aware estimator moves Haaland +1.00 xPts
   and six others −0.4 to −0.7. The head is small and self-contained
   (`components.py:111-142`); the ordering change is two lines in
   `advise.py:434-441`.
   *Verify:* `corr(e_bonus, actual bonus)` on GW2's 310 played rows must rise
   from 0.13 (MID) / 0.03 (FWD); then a K ≥ 3 seeded season replay via
   `scripts/replay_pair.sh`, per CONVENTIONS §9.

4. **Bound `e_gc_model`.** 0.035 expected goals conceded is not a football
   number, and `p_cs_model` spans 0.05–0.965 with the promoted clubs at both
   extremes. Today the 0.8 odds blend hides it; the documented no-odds
   degradation path would ship it.
   *Verify:* re-run `advise --fast` with `[odds] api_key` blanked and check
   `p_cs` stays inside [0.03, 0.75]; then assert that in a degradation test.

5. **Keep the fringe `e_goals` cap out of the banked artifact** — skip
   `blend_attacking_odds` where `p_play < 0.1`, or store the pre-blend value. It
   removes a +0.05 mean bias from every evaluation reading
   `components_gw*.parquet`.
   *Verify:* `(load_components(N).e_goals > 0.9).sum()` drops from ~27 to ~2
   (Haaland's own rows) and the all-rows mean falls from 0.148 to ~0.10.

6. **Reconcile `journal.json` and `decision_ledger.json`, or caption both.** They
   give opposite signs on the same gameweek (+8 model vs +3 user). One sentence
   on each surface naming which counterfactual it scores costs nothing.
   *Verify:* open Model → Review and This Week side by side; both name their
   counterfactual.

7. **Fit a GKP calibration delta, or say why there isn't one.** `by_pos` has
   DEF/MID/FWD and no GKP (`calibrate.py:41` needs ≥200 rows), so keepers alone
   get zero correction while outfielders get +0.66 to +0.70 — a silent
   per-position asymmetry inside the layer whose job is removing per-position bias.
   *Verify:* `joblib.load('models/calibration.joblib').by_pos` has 4 keys, or the
   health tab renders "GKP: not fitted (n < 200)".

8. **Correct `GUIDE.md` §3's "70/30" to the fitted 80/20.** Small, but §3 is the
   section the user reads to understand the model, and it misstates the most
   influential blend in the pipeline by a fifth.
   *Verify:* `cat models/blend.params.json` → 0.8; the GUIDE sentence matches.

**Deliberately not on this list:** the K ≥ 5 role replay and the C1 news
ablation. Both are worth running and both are already queued (`ROADMAP.md`
*Open*), but each is an overnight job answering a question about a feature that
already shipped — whereas items 1–5 are unshipped defects costing points and
measurement every week.
