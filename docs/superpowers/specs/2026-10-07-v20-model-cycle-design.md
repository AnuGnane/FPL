# v20 — the model cycle (programme design)

**Cycle:** v20, a programme of four gated arms, v20a … v20d, one branch
and one gate each.
**Source:** `docs/GUIDE.md` §12.3 and §12.5; `docs/superpowers/ROADMAP.md`
"One experiment" and candidates 11, 12 and 14;
`research/2026-09-04-current-state-review.md` §1, §3 and items 3–4;
`research/2026-09-15-v19-research-backend.md` §1 (the costing);
`specs/2026-09-16-v19g-model-free-design.md` §2.2 and §4 (the band and the
two readings); `specs/2026-09-01-gaffer-v12-program-design.md` §5.2 (the
role arm's record). Every rule below is held to
`docs/superpowers/CONVENTIONS.md`, cited by section.
**Plan:** `docs/superpowers/plans/2026-10-xx-v20-model-cycle.md`, to be
written after the rulings in §1 are confirmed; tracker beside it.
**Branches:** `v20<letter>-<slug>` off `main`, one at a time, ff-merged.
**Date:** 2026-10-07. **Status:** draft, written unattended on the holiday
queue (`HOLIDAY.md` F-S1). Nothing has run. Every ruling in §1 carries a
default; the user confirms, changes or strikes them from the phone, and a
merge without comment lets the defaults stand.

---

## 0. What this is, and the three ways it could have been done

v19 closed with the model cycle next (ROADMAP "Where things stand"): the
arms that move a served number, each costed in the v19 design's §4 and
each needing its own replay. This document pre-registers them. It is the
spec the full cycle machinery runs when the user is back; no code lands
from it, and the replays run on the Mac in the night shift, one seed at a
time (CLAUDE.md's memory note: two restraint seeds run concurrently were
OOM-killed).

The research found four things, each with a number on it.

- **The bonus head is denied the signal that predicts bonus.** Over the
  banked history (n = 12,120 appearances) `corr(bonus, goals)` is 0.624
  against 0.141 for the head's best feature; a forward who does not score
  earns 0.007 bonus over 1,202 observations. The head sees `bps_r*`,
  `xgi_r5`, `bonus_r*`, `elo_diff` and `home` (`models/components.py:111`),
  no `e_goals`, no `e_assists`, no `position`, and runs independently of
  the attacking head over the same frame (`models/predict.py:140`). On GW4
  the board's top `e_bonus` was Rúben, DEF, `e_goals` 0.000, above
  Haaland's (backend §1 C11). It redistributes 7.2 % of the objective.
- **The team model's extremes are served bare on the week the market has
  not priced.** Dixon-Coles exponentiates attack and defence bounded only
  at ±3 (`models/dixon_coles.py:122`, `:313`) and `fixture_outcomes` turns
  the result into `p_cs` and `e_gc` with no floor. GW7's twenty
  club-fixtures all carried `odds_weight = 0` and the bare model spanned
  `p_cs` 0.025–0.946, `e_gc` 0.056–3.696 (v19g §4). `ep_cs` is 29.8 % of
  DEF/GKP `ep_uncalibrated`. v19g pre-registered the band `p_cs`
  [0.02, 0.85], `e_gc` [0.15, 4.0] as a strict `xfail`
  (`tests/test_v19_degradation.py:88`) that fails by passing the day a
  clip holds it.
- **The `role` minutes feature shipped on its pre-registered rule and lost
  27 points post hoc at K = 3**, `[1813, 1847, 1846]` against `[1798,
  1917, 1872]`, inside a 119-point control spread (v12 §5.2). The read it
  was registered under let the flip stand; the GUIDE queued a K ≥ 5
  replay as the one experiment, and it decides what the minutes head ships
  with.
- **The price-timing term is live only on the UTC day of its bank**
  (`price_timing.py:69-93`), and until v19b the solve read a log dated the
  night before, so the trace said `0.0` or unknown (v19g §4). v19b put the
  bank inside `weekly_run` (`pipeline.py:101`) for all three callers, and
  deferred the reading to the user's Thursday 18:00 run. That line has
  never been read into a spec.

One more thing the research did not say and this document found while
reading the harness: **the season replay never runs the team model.**
`run_backtest` predicts every week through `predict_components_simple`
(`backtest.py:481`), which holds `p_cs` and `e_gc` at the league
constants 0.25 and 1.4 (`models/train.py:224`, `:460-484`; the comment at
`backtest.py:89-93` says why: one refit per window, one less source of
variance). A clip on the team model is therefore invisible to the replay
as it stands; a byte-identical result would prove nothing (CONVENTIONS
§10). Ruling 3 is about that.

Three shapes were considered.

- **A. One model branch, one replay at the end.** All four changes on
  `v20-model`, one K ≥ 5 pair against `main`. Fastest in replay-hours, but
  a single pair over four changes attributes nothing, and a loss would
  withdraw all four or none. Rejected, as the same shape was for v18 and
  v19.
- **B. A programme of gated arms, one branch, one two-half rule and one
  replay pair each**, run in value-per-replay-hour order with the cheapest
  decision first. Each merge is a fact; a failing arm ships off behind its
  switch with its numbers recorded (CONVENTIONS §6). **Chosen.**
- **C. Ship on head metrics, replay later.** Rejected on the record:
  twice in v12 a head-metric gain lost replay points (W2's xG-per-shot
  head, W4's `role` arm), which is why CONVENTIONS §9 demands both halves
  up front, and why this document writes the replay half of every arm
  before any head metric is computed.

**The rule for the whole programme, the inverse of v17–v19's: every arm
moves a served number, so every arm carries a two-half rule written here,
and no arm's verdict is read off a number this document does not name.**
Each arm states its head metric, its replay (season, driver, seeds, control,
spread rule), what ships it on, what ships it off, and the lever check that
makes a "no diff" mean something.

---

## 1. Rulings proposed for the user's review

Each is the orchestrator's recommendation, made unattended; the default is
what runs if nothing is said.

1. **Order.** v20a (the role replay) → v20b (the bonus head) → v20c (the
   clip, with its harness step first) → v20d (the price reading, which
   needs no replay and can be read any week the others run). The role
   replay goes first because it is the cheapest decision (about an hour
   per three seeds a side; backend §1) and it changes what every later
   arm's minutes head is. The droppable arm is v20c's replay half, not
   v20c: if the night shifts run out, the clip ships **off** with its head
   reading recorded (ruling 3). **Default: this order.**
2. **No new `Config` field, no new route, no new job kind.** Pins stay
   routes 52 / `JOB_KINDS` 12 / `Config` 62. Each arm's switch is a
   module-level constant in the file it changes (`BONUS_SEES_ATTACK` in
   `models/components.py`; `MU_BOUNDS` in `models/dixon_coles.py`;
   `REPLAY_TEAM_MODEL` in `backtest.py`), on in the arm's branch and set
   to its off value in the commit that ships a failed arm. A constant is
   what `replay_pair.sh` already compares — branch against `main` on
   byte-identical flags — so the driver needs no new `--arm`. The
   alternative, a `[model]` flag per arm like `xg_per_shot` (pin 62 → 64,
   two commits to `tests/test_v13_degradation.py`), buys a settings-page
   toggle for a change nobody should toggle after its gate. **Default:
   constants.**
3. **The clip's replay half runs on a harness that sees the team model.**
   `predict_components_simple` holds `p_cs`/`e_gc` at constants, so v20c
   has a step zero: `backtest.py` gains a `REPLAY_TEAM_MODEL` path that
   predicts the horizon's club-fixtures through the refit Dixon-Coles
   model (no market: the replay has no odds in the loop, which is exactly
   the degradation path the review's item 4 named and where the clip
   bites). The harness step has **no points criterion** — a harness
   chosen on the points it produces is a harness chosen to flatter — only
   a lever check and a recorded re-baseline (§2.3). If the harness step
   is not done when the night shift reaches v20c, the clip's verdict is
   its head half and the band rail alone, and under CONVENTIONS §9 that
   is under-specified, so the clip ships **off**, flagged, with the arm
   left open. The alternative, gating the clip on the head half plus a
   no-odds board diff and calling that enough, is the shape §9 was
   written against. **Default: the harness step, then the clip.**
4. **The role replay's verdict is a paired test, not a range.** GUIDE
   §12.3 says "negative beyond its own spread withdraws the arm". A
   max-minus-min spread widens with K, so at K = 10 that read gets laxer
   as the evidence grows. The rule here (§2.1) is the paired mean against
   twice its standard error plus a sign count, which tightens with K. If
   the user prefers the GUIDE's literal read, strike this and §2.1 uses
   `mean(on − off) < −spread(on)`. **Default: the paired rule.**
5. **The bonus head's new inputs are the attacking head's own outputs,
   out of fold at fit time.** At serve time the bonus head reads
   `e_goals` and `e_assists` as the attacking head returns them in
   `predict.py:140` — before set pieces fold in at the bottom of
   `predict_components` and before the anytime-scorer blend at
   `advise.py:563` — and `position` as three indicator columns. At fit
   time the same two columns are **out-of-fold** predictions: for each
   season in the bonus window (`bonus_season_floor`), the attacking head
   is refit on every other season and predicts that one. In-sample
   predictions are rejected (a LightGBM head's training-set `e_goals` is
   sharper than anything it serves, so the bonus head would learn a
   dependence the live path never feeds it). The cheaper alternative,
   adding `ATTACK_FEATURES` and `position` to `BONUS_FEATURES` with no
   stacking and no ordering change, is recorded as v20b′ and runs only if
   v20b fails its head half (§2.2). **Default: out-of-fold stacking.**
6. **The clip is on `lam` and `mu`, inside `DixonColesModel.predict`, at
   [0.2, 3.5].** The band is on the outputs, but clipping the outputs
   would leave the scoreline pmf (result probabilities for the ticker,
   the 2+ conceded band) inconsistent with the clean-sheet number
   `fixture_outcomes` exists to keep consistent. Clipping the Poisson
   means at [0.2, 3.5] puts `e_gc` in about [0.2, 3.5] and `p_cs` in
   about [exp(−3.5), exp(−0.2)] = [0.03, 0.82], inside v19g's band with
   margin on every edge, so the strict `xfail` flips by construction on
   the first bare-model week after the clip. The research's tighter floor
   (0.3, the count of fixtures under it) is not a second sub-arm: one
   floor, one replay. **Default: [0.2, 3.5] on both means.**
7. **The v19g `xfail` comes off only when the clip ships on**, in the
   arm's own commit to `tests/test_v19_degradation.py` (orchestrator-only;
   the orchestrator makes the diff, as CLAUDE.md requires). A clip that
   ships off leaves the mark where it is. **Default: as stated.**
8. **An arm that ships on re-records the golden board** (`python -m
   tests.golden_client --write`) in its merge, after its gate, and the
   diff of the expected files is the arm's board diff, read by the
   orchestrator and pasted into the arm's spec. The golden gates
   refactors; an arm is a deliberate change to the numbers it compares,
   so a red golden on an arm's branch is expected and a re-record is the
   honest close, once. The alternative — widening `strip_volatile` to the
   columns an arm moves — would blind the gate to the next refactor.
   **Default: re-record, once, per shipped arm.**
9. **The price arm is a reading with a pre-registered consequence, not a
   code change.** v19b already banks the reading inside `weekly_run`
   (`07107b1`, 2026-09-16), and the web button inherits it through
   `web/job_kinds.py:77`, so GUIDE §12.4's "the web re-run button does
   not bank a same-day price reading" and the ROADMAP's candidate 7
   second half are **stale**; HOLIDAY.md F-3 is a docs change unless
   v20d's reading says otherwise. v20d reads the Thursday 18:00 lines
   since 2026-09-17 and decides by the table in §2.4. **Default: as
   stated.**
10. **Seeds and K.** Every replay pair runs `scripts/replay_pair.sh` with
    `SEEDS` set explicitly (its default is three), `CONCURRENT=0`, one
    seed at a time, `caffeinate -i`. v20a: `20260901` … `20260910`,
    K = 10 planned, read at whatever K ≥ 5 has finished when the night
    shift's window for it closes, the count stated, never read earlier.
    v20b and v20c: `20260901` … `20260905`, K = 5. The first three bases
    reproduce W4's; the control is always re-run on the same night, never
    a banked number (`replay_pair.sh`'s header, CONVENTIONS §3).
    **Default: as stated.**
11. **Usage.** As v19 ruling 10: Fable orchestrates, reviews diffs and
    runs gates; opus implementers write code from written briefs, one
    committing agent at a time; sonnet for mechanical sweeps. At most three
    implementer briefs per arm. The replays are the orchestrator's
    (CONVENTIONS §7) and run on the Mac, never in a cloud session.
12. **The open security incident** (`dd47c0a`) is not part of v20. It
    stays with the user.

---

## 2. The arms

Sizes are implementer effort: S under a day, M one to two days, L more.
"Served numbers move" names what the arm changes on the board when it
ships on; everything else must be byte-identical, and the golden board's
re-record (ruling 8) is where that is read.

Every arm's replay is the same measurement unless its section says
otherwise: `scripts/replay_pair.sh <tag>` from the arm's worktree, which
runs `scripts/v7b_replay.py --arm heur --n 40 --chips` on the branch and
on a fresh `main` worktree over the driver's season
(`run_backtest(season="2025-26", start_gw=5, horizon=3)`,
`scripts/v7b_replay.py:450`), the same `SEEDS`, `config.toml`, `data/` and
`models/` linked so both sides read the same bytes. The write-up names the
two SHAs, the config echo, `data/core_insights/`'s seasons and collection
date (CONVENTIONS §1), and transcribes every `V7B_ARM_DONE` and
`MULTISEED_DONE` line into §6 (CONVENTIONS §4). "Paired delta" means
branch total minus `main` total at the same seed base; "SE" means the
standard deviation of the paired deltas over √K.

### v20a — the role replay, K ≥ 5

*The one experiment the GUIDE queued: does the minutes head's `role`
feature cost season points, or was −27 at K = 3 the seed?*

- **What.** `MINUTES_FEATURES` (`models/train.py:62`) is
  `… + ROTATION_FEATURES + ROLE_FEATURES`. The "off" side is a branch
  `v20a-role-off` with `ROLE_FEATURES` removed from that list and nothing
  else changed: the features are still built (`features/engineer.py:1565`)
  so both sides read the same frame and the same
  `data/core_insights/` archive, and the lever is the head's column list
  alone. The "on" side is `main`. This arm has no implementer: the branch
  is one line, the orchestrator's. S.
- **Head half.** None new. W4 banked it (`W4_ARM_DONE role`: starters
  log-loss 0.43723 → 0.42889, −1.9 % relative) and that gain is not in
  dispute; what is in dispute is whether it reaches the season.
- **Replay half.** `replay_pair.sh v20a-role` with `SEEDS=20260901,…,
  20260910` (ruling 10), the branch side being `v20a-role-off`, so the
  pair's "branch" is role **off** and its "main" is role **on**. Read as
  paired deltas `off − on`.
- **Verdict rule (ruling 4).** Let Δ = mean(off − on), SE as above, and
  `neg` the count of seeds where `on` scored below `off`.
  - **Withdraw `role`** (ship `main` with `ROLE_FEATURES` out of
    `MINUTES_FEATURES`, the features still built; GUIDE §3 and §12.3 and
    the ROADMAP's experiment row updated) iff Δ > 2·SE **and** neg ≥ K − 3.
  - **Keep `role`**, and close the experiment, otherwise. The numbers are
    recorded beside W4's; no further role replay is run in this programme.
  - K < 5 finished → no verdict; the run is rescheduled, never read.
- **Lever check (CONVENTIONS §10).** Each side's first fold logs the
  minutes head's `cols_`; the off side's omits `role_wb_share` and
  `role_wb_missing`, the on side's carries them. Without those two lines
  the pair is not a measurement.
- **Served numbers move** only if `role` is withdrawn, and then every
  `p_play` moves; the golden board is re-recorded (ruling 8).

Gate: the two lever lines; `MULTISEED_DONE v20a-role-branch` and
`-main` transcribed; the verdict written under the rule above before
anything else is changed; inner loop and ruff on the branch that ships.
No pin moves.

### v20b — the bonus head sees goals

*The review's clearest structural defect: bonus for an attacker is
`P(scores) × 1.6`, and the head that prices it has never been shown
`P(scores)`.*

- **What.** `BonusModel` (`models/components.py:115`) gains five inputs
  when `BONUS_SEES_ATTACK` is on: `e_goals`, `e_assists` (ruling 5) and
  `pos_DEF`, `pos_MID`, `pos_FWD` (GKP the base). `train_all`
  (`models/train.py:598`) builds the out-of-fold columns for the bonus
  window's seasons before the bonus fit, one attacking refit per left-out
  season; `predict_components` (`models/predict.py:140`) and
  `predict_components_simple` (`models/train.py:460`) order bonus after
  attacking and hand it `comp`'s `e_goals`/`e_assists`, so the replay
  exercises the same path the solve does. The existing eight features
  stay. `advise.py` is not touched: the anytime-scorer blend at `:563`
  stays after `predict_components`, and the bonus head never sees it, at
  fit or at serve. M.
- **Head half.** On the same ten-slot holdout `fit_calibration` uses
  (`CALIBRATION_HOLDOUT_GWS`, `models/train.py:233`): refit every
  component on the rows strictly before the first held-out slot, predict
  the held-out appearances (`minutes > 0`), and read, on both sides,
  Pearson `corr(e_bonus, bonus)` overall and per position, the level
  `mean(e_bonus) − mean(bonus)`, and `corr` on the subset that scored.
  **Pass** iff overall `corr` rises by ≥ 0.05 absolute, no position's
  `corr` falls by more than 0.02, and the level stays within ±0.02 of the
  control's. The script is the orchestrator's, under `scripts/`, and its
  output line `V20B_HEAD {…}` is transcribed into §6. The review's own
  numbers (GW2 live: MID 0.13, FWD 0.03) are the motivation, not the
  control; the control is `main`'s head on the same holdout.
- **Replay half.** Runs only after the head half passes (CONVENTIONS §9
  pre-registers both; it does not require spending four hours on a head
  that already failed). `replay_pair.sh v20b-bonus`, K = 5, `SEEDS=
  20260901,…,20260905`. Paired delta `branch − main`.
- **Verdict rule.**
  - Head **fails** → ships **off** (`BONUS_SEES_ATTACK = False`), the
    replay is not run, v20b′ (ruling 5) is run through the same two
    halves if the night shift has the hours, else recorded as a candidate.
  - Head passes, replay **not negative** — mean paired delta ≥ −5 (W4's
    tolerance) **or** fewer than 4 of 5 seeds negative — → ships **on**.
  - Head passes, replay **negative** — mean paired delta < −5 **and** at
    least 4 of 5 seeds negative — → ships **off**, and the spec records
    the third head-gain-season-loss in the project's history beside W2's
    and W4's.
  The replay half here is a no-regression bar on purpose: at a 119-point
  seed spread a +10 redistribution of 7 % of the objective is not
  resolvable at K = 5, and pretending otherwise is CONVENTIONS §5. The
  head half carries the claim; the replay guards the failure mode.
- **Lever check.** The branch side logs the bonus head's `cols_` (thirteen
  columns) and the first fold's `corr(e_goals, e_bonus)` on the predicted
  rows; `main` logs eight columns. A branch log with eight columns is a
  disconnected lever and the pair is discarded.
- **Served numbers move:** every `e_bonus` and so every `ep`; the board,
  the ladder and the components file. The Model → Quality page's bonus
  column is read by eye after the first live run; the golden board is
  re-recorded (ruling 8).

Gate: `V20B_HEAD` on both sides; the lever lines; `MULTISEED_DONE` both
sides; the verdict under the rule; inner loop, ruff, the golden gate
re-recorded in the merge; `npm run check` unchanged (no wire type moves).
No pin moves.

### v20c — the Dixon-Coles clip, after the harness learns to see it

*0.035 expected goals conceded is not a football number; the market hides
it at w = 0.8 until the week the market has not priced, and then it is the
number served.*

**Step zero — the replay sees the team model (harness, M).**
`backtest.py` gains `REPLAY_TEAM_MODEL` (default **off**, so every banked
replay to date stays reproducible): when on, the weekly loop builds the
horizon's club-fixture rows from the player rows it already has
(`team_code`, `opp_code`, `was_home`, per `gw`), predicts them through
`models["team"]` — refit per window already by `train_all` and read by
nothing — and merges `p_cs`/`e_gc` onto the player rows the way
`predict.py:152-174` does, with no market (the replay has no odds in the
loop) and the same `DEFAULT_P_CS` fill for a fixture the team frame lacks.
The calibration delta keeps fitting through the simple path, as it does
live (`fit_calibration`'s docstring calls the mismatch an accepted
approximation). Its gate is **not a points number**: a raw pair, harness
off against harness on, K = 5 on the same seeds, is run and recorded as the
programme's re-baseline (`MULTISEED_DONE v20c0-harness-*`), and the lever
check is that the on side's replay log carries a `p_cs` column that varies
across the season's club-fixtures (min, max and count of distinct values
logged) where the off side's is 0.25 everywhere. A pair whose on side logs
0.25 is not a harness.

**The clip (S).** `MU_BOUNDS = (0.2, 3.5)` in `models/dixon_coles.py`;
`DixonColesModel.predict` (`:290`) clips `lam` and `mu` to it before
`fixture_outcomes` (`:96`), so every derived number — `p_cs`, `e_gc`, the
result probabilities, the 2+ band — comes off one consistent pmf
(ruling 6). `None` is the off value. `walk_forward_cs` (`:334`) fits the
same class, so the blend weight refit on the next `gaffer train` sees the
clipped model too; the write-up records the weight before and after
(`models/blend.params.json`), and a move of more than 0.05 is a finding.

- **Head half.** The walk-forward folds `walk_forward_cs` already defines
  (half-season folds, Dixon-Coles fit on every match strictly before,
  predict the fold): on both sides, log-loss and Brier of `p_cs` against
  realised clean sheets and MAE of `e_gc` against realised goals against,
  over all fixtures and over the **extreme subset** (fixtures whose
  unclipped `p_cs` or `e_gc` lies outside v19g's band). **Pass** iff
  overall log-loss is not worse by more than 0.001, the extreme subset's
  log-loss improves, and overall `e_gc` MAE does not worsen. The clip is
  meant to bite only where the model is absurd; a clip that costs
  calibration everywhere is the wrong clip. Script the orchestrator's,
  line `V20C_HEAD {…}` into §6.
- **The band.** With the clip on, `tests/test_v19_degradation.py`'s strict
  `xfail` fails by passing on the first components file that carries a
  bare-model week; that is the pre-registered signal and the mark comes
  off in the arm's commit (ruling 7). The review's item 4 check runs too:
  `gaffer advise --fast` with the odds key absent from the environment —
  on the Mac, by the user, since a real advise spends quota and rewrites
  served advice (v18h) — and the served `p_cs` must lie inside the band on
  every club-fixture; the before/after board diff is read by the
  orchestrator and pasted into the arm's spec.
- **Replay half.** Runs only after step zero is accepted and the head
  half passes. `replay_pair.sh v20c-clip`, K = 5, the same five seeds,
  `REPLAY_TEAM_MODEL` on **both** sides (it is the harness, not the arm;
  `main` carries it merged from step zero). Paired delta `branch − main`.
- **Verdict rule.** The same three rows as v20b: head fails → off, no
  replay; head passes and replay not negative (mean ≥ −5 or fewer than 4
  of 5 negative) → **on**, `xfail` removed; head passes and replay
  negative → off, recorded. Step zero not done → off, the arm left open
  with its head reading recorded (ruling 3).
- **Lever check.** The branch side logs, per season, the count of
  club-fixtures where the clip bit (`DC_CLIP n=… of …`); zero on every
  fold means the replay's fitted model never left the band and the pair
  measured nothing about the clip — recorded as such, no verdict.
- **Served numbers move:** `p_cs`, `e_gc` and so `ep_cs`, `ep_gc` on the
  bare-model week only (market-backed fixtures move by (1 − w) of the
  clip's shift); Model → Health's team-model line reads inside the band.
  Golden re-recorded (ruling 8).

Gate: the harness lever lines and `MULTISEED_DONE v20c0-harness-*`;
`V20C_HEAD` both sides; the band rail flipped and the mark removed in one
commit; the no-odds diff pasted; `MULTISEED_DONE v20c-clip-*`; inner loop,
ruff, golden re-recorded; `npm run check` unchanged. No pin moves.

### v20d — the price term's window, read

*Since v19b the Thursday run banks a reading minutes before it solves.
Nothing has read whether the term then charged anything.*

- **What.** A reading over the Thursday 18:00 runs from 2026-09-17 on
  (GW5's run was the first after v19b's merge; 09-24, 10-01, 10-08, 10-15
  and 10-22 follow inside the holiday), each from three places: the
  advise log's price-step line (`prices_banked` rows, or "price reading
  not banked: …"), the price log's row count for that UTC day, and the
  served plan's head-week trace (`price_charge`, `price_fall` and the
  week note; `reports/gw{n}-advice.json`). No code lands unless the table
  below says so. S, orchestrator.
- **Lever check per run.** The step banked (a row count in the log and a
  `snap_date` equal to the run's UTC day in `data/live/price_log.parquet`)
  **and** the solve ran the same UTC day. A run failing either is not
  evidence about the term; it is evidence about the step, and goes in the
  first row below.
- **Verdict table**, read over every Thursday run that has landed when
  v20d is written up (at least three):
  | Reading | Consequence |
  |---|---|
  | Any run where the step did not bank, or banked on a different UTC day than the solve | A bug in `pipeline.bank_price_reading` or the clock; root-caused and fixed in `pipeline.py` with a test in `tests/test_pipeline.py` (orchestrator-only). This is the only row that lands code. |
  | Every run banked; at least one head week sold a player with a `drop` reading that day, and its trace carries a numeric `price_charge` | The term is live on the scheduled path. Closed, no change; the GUIDE §12.4 residual and ROADMAP candidates 7 (second half) and 14 struck; HOLIDAY F-3 becomes a docs line. |
  | Every run banked; no head week sold a `drop`-flagged player | No evidence either way. The row count and the empty table are transcribed and the arm stays open one more Thursday, up to the end of the holiday; after that, recorded as waiting on data (ROADMAP "Data-gated"). |
  | Every run banked, a `drop`-flagged sale, and the trace still reads `None` or `0.0` | The reader, not the step: `price_falls`'s day match (`price_timing.py:91`) or the owned-codes hand-off. Root-caused; the fix is a v21 item with the trace lines beside it, because `advise.py` or `served.py` is where it would land. |
- **The term's worth, as a second reading.** The log now holds more than
  thirty UTC days (2026-08-31 on, with gaps named). Over every
  `(snap_date, code)` with a `drop` reading and a row the next day:
  Brier of `min(1, |pct| / 100)` against "fell overnight" (`now_cost`
  down), beside the base-rate Brier over the same rows. **If** the term's
  Brier is worse than the base rate's over ≥ 30 drop-days, a ruling to
  change `[optimizer] price_timing`'s default to off (a default, not a
  field; `config.py:180`) goes to the user with the numbers; otherwise the
  line is recorded and the default stands. Script the orchestrator's,
  line `V20D_BRIER {…}` into §6.
- **Served numbers move:** none from this arm as written; only the first
  row's fix would move the trace's price line, and only when a bank had
  silently failed.

Gate: the per-run lever lines and the table's row named; `V20D_BRIER`
transcribed; the docs edits named above when the second row holds. No
pin moves.

---

## 3. What every arm does the same way

As v19 §3, with the replay rules added.

- A spec under `docs/superpowers/specs/2026-10-xx-v20<letter>-<slug>-
  design.md` whose gate copies its section of §2 verbatim before anything
  runs; briefs to the implementer as scratchpad files, at most three per
  arm; a fresh opus implementer per brief; one committing agent at a time;
  the orchestrator reviews every diff and makes every diff to an
  orchestrator-only file (`tests/test_v19_degradation.py` in v20c,
  `tests/test_pipeline.py` if v20d's first row holds, the golden
  re-records).
- The replay is the orchestrator's, on the Mac, in the night shift
  (`AnuGnane/autopilot` `NIGHTSHIFT.md`), `CONCURRENT=0`, one seed at a
  time, `caffeinate -i`, from the arm's worktree; never edit the tree
  while it runs. Both sides every time; a banked number is never a
  control (CONVENTIONS §3). The pinned set for every pair: `config.toml`
  byte-identical with `price_timing`, `xg_per_shot` and
  `draw_availability` stated; `data/core_insights/` present, seasons and
  collection date named; the two SHAs; `REPLAY_TEAM_MODEL`'s value.
- Every `*_ARM_DONE`, `MULTISEED_DONE`, `V20*_HEAD` and `V20D_BRIER` line
  is transcribed into §6 of this document and into the arm's spec the day
  it prints (CONVENTIONS §4).
- A verdict is written under the arm's rule in §2 before any other number
  is looked at; a rule is never edited after its run (CONVENTIONS §2). A
  failing arm ships off behind its constant with the result recorded
  (CONVENTIONS §6).
- Gates the orchestrator runs on the branch that ships: the inner loop
  (`-m "not slow and not golden"`), `uvx ruff check src tests`, `cd
  frontend && npm run check`, the golden gate (re-recorded once in the
  merge when the arm ships on, ruling 8), screenshot pairs with **Model**
  named for v20b and v20c (the Quality and Health lines) and every other
  hub byte-identical below the strip.
- Pins: routes 52, `JOB_KINDS` 12, `Config` 62, unmoved by every arm
  (ruling 2).
- Merge: ff-only after the gate and the user's reading of the verdict;
  the docs commit on `main` names the merge hash; the security ritual
  before every push; the tracker's row; the memory line.

---

## 4. Out of scope, by name

- **C1, the news-layer ablation** (ROADMAP candidate 1; backend §1 rank
  5): buckets plus a K ≥ 5 replay, four to five hours plus analysis, and
  the payoff is "retire or keep the v5/v6 subsystem", not points this
  season; `news_shadow` already leans to the plain flag (Brier 0.1276
  against 0.1191). Costed, deferred to the cycle after this one with the
  same two-half shape; it would be v20e if the night shifts run long.
- C2 (`p_play` top-bin isotonic step), C3 (home/away splits), B1's second
  half (days since status changed), `density_pub_7d`'s re-measure: each a
  minutes- or attacking-head arm with its own K ≥ 5, none costed by the
  research above the four here.
- The top-10k threshold scrape (HOLIDAY F-4), the blended league stance
  (candidate 9), `P(top-10k)`, the trace's squad-side attribution and
  price-line freeze, Plan B/C re-scoring (all `advise.py` decorations).
- A second clip floor, a market blend inside the replay harness, a
  per-two-gameweek `p_cs` calibration window (v18c's candidate): each a
  harness or model change with no number on it yet.
- Any change to the MILP, the ladder, the restraint policy, the fitted
  odds blend weight's method, `horizon`, `decay`, `hit_cost`, or the
  ledger style.
- The open security incident (ruling 12).

---

## 5. Self-review

- **Placeholders:** none in the rules; §6 is empty by design until the
  night shift prints the lines it is for, and says so.
- **Both halves, every arm** (CONVENTIONS §9): v20a's head half is W4's
  banked record and its replay is the arm; v20b and v20c name a head
  metric, a holdout, a pass rule and a K = 5 replay with its control;
  v20d is a reading whose consequence is pre-registered in a table, and
  it moves no served number, which is why it alone has no replay.
- **Lever checks, every pair** (CONVENTIONS §10): the minutes head's
  column list, the bonus head's column list and a correlation, the
  harness's `p_cs` spread, the clip's bite count, the price step's row
  count and day.
- **Consistency:** rulings 2, 7 and 8 agree with §2 and §3 on the pins,
  the `xfail` and the golden; ruling 3 and v20c agree that the clip has no
  replay half without step zero and ships off without it; ruling 10 and
  the arms agree on seeds and K; ruling 9 and v20d agree that the web
  button's residual is stale.
- **Scope:** four arms, one branch and at most three briefs each; the
  droppable piece is v20c's replay half, and dropping it ships the clip
  off rather than untested.
- **Ambiguity:** "not negative" and "negative" are defined by the same
  two numbers (mean −5, 4 of 5 seeds) in v20b and v20c so a reader cannot
  pick the kinder one after the fact; "paired" always means the same seed
  base on both sides; "extreme subset" is defined by v19g's band, not by
  the clip's bounds.
- **What this document could not check from the sandbox:** the Mac's
  current `data/core_insights/` seasons, the price log's day count and
  gaps, the number of Thursday runs that have landed, and whether the
  driver's season label (`2025-26`) and v16 §12's (`2024-25`) name the
  same frame; each is a line the first night shift writes into §6 before
  any arm runs.

---

## 6. Evidence appendix

Transcribed verbatim as the night shift prints them, per CONVENTIONS §4;
`logs/` is gitignored. Empty on 2026-10-07: nothing has run.

```
# pinned set (first night shift): core_insights seasons + date, config echo, SHAs
# v20a: MULTISEED_DONE v20a-role-branch … / v20a-role-main … ; lever lines
# v20b: V20B_HEAD main … / branch … ; MULTISEED_DONE v20b-bonus-branch … / -main …
# v20c0: MULTISEED_DONE v20c0-harness-branch … / -main … ; p_cs spread lines
# v20c: V20C_HEAD … ; DC_CLIP … ; MULTISEED_DONE v20c-clip-branch … / -main …
# v20d: per-Thursday lever lines ; V20D_BRIER …
```
