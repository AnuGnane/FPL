# Gaffer v9c Model Debt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** close the four deferred findings from the 2026-08-31 cross-cutting review — a red-card penalty that has been silently zero since it landed, a `team_code` retro-stamp that rewrites a transferred player's history under his new club, two different quantities served under one name, and a wedged job that 409s every later job until the process restarts. Each behind its own gate. Nothing here ships on an assertion: two of the four change the training frame and are therefore measured before they are believed.

**Architecture:** four independent seams, deliberately sequenced so the two that move numbers land before the two that do not.

- **D1** is one list entry (`rc` into `ROLL_STATS`) plus an arm harness that decides whether it stays. The surprise, established below in A2, is that it changes **no model's inputs** — every model in this repo reads an explicit feature list, so the five new `rc_r*` columns reach exactly one consumer: the deterministic `card_penalty` formula whose `-3` term has never fired.
- **D2** derives an as-of `club_code` in `models/train.py` from machinery that already exists in `features/bps.py`, and switches three feature builders in `features/engineer.py` from the stamped `team_code` to it. The column rides to serve time for free because `feature_columns()` does not name it.
- **D3** renames the attacking `p_haul` at the **web boundary only**, as a third serve-time decoration in `routers/advice.py` beside `with_positions` and `with_identity` — v9a's precedent, and the only option once you discover (A1) that there is no typed schema for that field to rename.
- **D4** is the cycle's single authorized protected breach: an abandon path in `web/jobs.py` and a `DELETE /api/jobs/current` in `routers/jobs.py`, enumerated line by line in Task 7's STOP and applied only after the orchestrator says so in-branch.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, LightGBM, FastAPI + pydantic, pytest; React 19 + TypeScript + vitest (a two-line label change only).

**Prerequisite:** **v9b must be merged to `main` before this branch is cut.** v9b is a frontend-only cycle in flight on `feat/gaffer-v9b`; branching v9c off anything but merged `main` guarantees a conflict in `frontend/src/hubs/this-week/SquadTable.tsx`, which Task 6 edits and which v9b's mobile pass also touches. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

```bash
# only after v9b is merged — confirm before branching
git checkout main && git pull --ff-only
git log --oneline -1 | grep -q v9b || echo "STOP: v9b not merged yet"
git checkout -b feat/gaffer-v9c
```

**Protected — must show zero diffs at the end (Task 11 audits this), except the D4 lines enumerated in Task 7's STOP:**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py` *(D4 exception — Task 7 only)*,
`src/gaffer/web/routers/jobs.py` *(D4 exception — Task 7 only)*,
`src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py` — `test_degradation.py`, v4c, v4d, v5, v6, v7_model, v8a, v8b, v8c, v8d, v8e, v8f, v8g, v9a (and v9b's, if v9b shipped one),
`scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`. This cycle imports nothing from either.

**Zero pin updates.** This is a measured claim, not a hope — see A13. The job-kind count stays 12, the config field count stays 48, no degradation rail names the field D3 renames, and the one route-set pin in the tree filters on `/api/assets` and keys on path rather than method, so `DELETE /api/jobs/current` moves nothing. If a pin nonetheless breaks, **stop and report**: it means this plan mis-read the tree, and a silenced pin is worse than a stalled cycle.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `src/gaffer/web/static/` or `config.toml`. The arm and replay tasks all write into `reports/` and `logs/`; none of it is committed, and the numbers reach the repo only by being transcribed into the spec (CONVENTIONS §4).

**Gate rule (CONVENTIONS §7):** implementers build the drivers and never run the gates. Tasks 2, 5 and 10 hand a driver and an exact command to the orchestrator and stop there. Task 11 is the checklist, unfilled.

**Suite baselines (measured on `main` at `f62080c`, 2026-08-31): 2746 Python tests; 498 frontend tests + 1 skipped.** These predate v9b's merge — **re-measure both on merged `main` and write the numbers into this header before Task 1**, because every task's final run is judged against them.

```bash
uv run pytest -q                       # record: <N> passed
cd frontend && npx vitest run          # record: <N> passed, <M> skipped
```

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Fifteen things D1–D4 do not pin — including three places where the spec's reading of the tree turned out to be wrong. Each is decided once here so no task decides it twice at the keyboard.

### A1 — D3's premise does not hold: there is no alternatives schema to rename.

The spec sends the implementer to "schemas.py's alternative-row model, ~:591 vs the band-sourced ~:411". Both pointers are wrong, and so is the shape they describe. The tree actually reads:

| Site | Model | Source |
| --- | --- | --- |
| `src/gaffer/web/schemas.py:439` | `PlayerRow.p_haul` | `uncertainty.Band.p_haul` (via `routers/players.py:185`) |
| `src/gaffer/web/schemas.py:619` | `ComponentPlayer.p_haul` | `uncertainty.Band.p_haul` (via `routers/components.py:185`) |

**Both** typed fields are the band quantity. `schemas.py:411` is prose inside a `field_eo` docstring. There is **no pydantic model anywhere** for the alternatives or captain rows: `advise.py:903,906` calls `.to_dict("records")` on the frames, `run_advise` writes them to `reports/gw{N}-advice.json`, and `routers/advice.py:112` serves the whole payload as `AdviceLatest.advice`, typed `dict[str, Any]` at `schemas.py:55`. Pydantic never names `p_haul` on that path, and neither does any router.

So the rename has no existing line to edit. It needs a **new** transform, and v9a already built the precedent for exactly this: `routers/advice.py:125` composes `with_identity(with_positions(...))` — two serve-time decorations that exist precisely because `advise.py` is protected. D3 becomes a third, `with_attacking_haul`, applied in the same expression. The on-disk artifact keeps `p_haul`, which is what keeps `digest.py:497` and the "since last run" diff comparing like with like.

The frontend consumes none of it — `grep -rn "captain_options\|alternatives" frontend/src` is empty — so `types.ts` has nothing to rename. What it has is a *label* problem, which is the half of D3 that was always real: the only rendered surface for either quantity is `SquadTable`'s "haul" chip (band-sourced) and the report template's two `<th>P(haul)</th>` headers (attacking-sourced). Both get told which one they are.

### A2 — D1 changes the training frame but no model's inputs, so the arm is an EP-formula arm, not a v8a feature arm.

Every model in this repo takes an **explicit** feature list: `MINUTES_FEATURES` (`train.py:46`), `ATTACK_FEATURES` (`attacking.py:21`), `DEFCON_FEATURES`/`SAVES_FEATURES`/`BONUS_FEATURES` (`components.py:16,80,111`), `TEAM_FEATURES` (`team.py:21`). None of them names an `rc_*` column, and none is derived from `ROLL_STATS`. `feature_columns()` (`engineer.py:753`) *is* derived from it, but its only caller is `advise.py:548`, where it is the list of engineered columns to **strip** before re-deriving them.

Therefore adding `rc` to `ROLL_STATS` adds `rc_r{1,3,5,10,38}` to the frame and hands them to exactly one consumer: `card_penalty` (`components.py:146-157`), a closed-form formula that is not fitted at all. Two consequences the plan is built on:

1. **The model weights do not move.** Task 1 asserts this rather than assuming it (a byte-comparison of `models/` before and after a retrain on the same seed), because the whole design rests on it.
2. **The arm cannot be run v8a-style.** `scripts/v8a_arms.py` memoises one training frame across every arm precisely because the frame is what cannot differ; here the frame *is* the intervention. The v9c driver builds a frame per arm and pays for it (A3's timing).

### A3 — the intervention is an in-place list mutation, because `ROLL_STATS` is a mutable default argument.

`add_player_rolling(df, stats: list[str] = ROLL_STATS)` (`engineer.py:85`), `latest_player_rolling` (`:624`), `build_prediction_frame` (`:652`) and `feature_columns` (`:753`) all bind `ROLL_STATS` as a **default argument at definition time**. Rebinding `engineer.ROLL_STATS = [...]` from a driver therefore changes nothing at all — every one of those defaults still points at the original list object. This is a live trap and it would fail silently, producing a "baseline" and an "arm" with identical frames and an arm gap of exactly zero, which reads like a clean negative result.

So: the shipped code gains `"rc"` in the literal, and the driver's **baseline** arm removes it *in place* (`ROLL_STATS.remove("rc")`) and puts it back in a `finally`. The intervention operates on the exact object every default is bound to. Task 1's driver asserts the frame actually differs between arms before trusting either number.

### A4 — D1's keep rule, pre-registered before any arm runs (CONVENTIONS §2).

v8a's rule was an *improvement* gate (`zeros` RMSE must gain ≥ 0.005) because v8a was hunting a zeros signal. D1 is not hunting anything: it is switching on a term the model has always documented and never applied. A red card is a rare event that removes a player mid-match, so its effect lands in the low tail and in almost no rows. Demanding an improvement would withdraw a correct term for being small.

**Pre-registered rule — SHIP iff no stratum regresses by more than 0.005 RMSE:**

```
ship iff (arm.zeros   - base.zeros)   <= 0.005
     and (arm.haulers - base.haulers) <= 0.005
     and (arm.all     - base.all)     <= 0.005
```

`GUARD_TOLERANCE = 0.005` is v8a's own tolerance, reused so the two cycles' numbers are read on one scale. Any breach withdraws. This rule is written into the driver's docstring and into this plan **before** the run, and it is not revisited after the numbers land.

### A5 — the withdraw branch is a documented zero, and it is a two-file change specified in advance.

If A4's rule breaches, Task 2 (a) reverts the `ROLL_STATS` entry and (b) rewrites `components.py:157` as `return -1.0 * _rate("yc_r38")` with a comment carrying the finding *and the arm numbers that withdrew it*. `models/components.py` is not protected. Either branch ends the silent state, which is the point of D1; the difference is only whether the term is live or explicitly dead. Both branches are fully written out in Task 2 so the orchestrator authorizes a decision, not a diff.

### A6 — `club_code` is a per-row coalesce, never a column-presence switch.

The tempting shape is `col = "club_code" if "club_code" in df.columns else "team_code"`. It is wrong, and it fails in the one place that matters. `build_prediction_frame` (`engineer.py:682`) concatenates history rows (which carry `club_code`) with future rows (which cannot — the fixture has not been played, and for a future row the current club *is* the as-of club). A column-presence check sees the column present on the combined frame and reads `NaN` for every future row; the Elo merge at `:609` would then miss on every serving row and the model would predict against a null opponent strength.

So `engineer.py` gains one small helper and every switched site calls it:

```python
def as_of_club(df: pd.DataFrame) -> pd.Series:
    """The club a row's player actually played for, falling back per row."""
```

`df["club_code"].where(notna, df["team_code"])` when the column exists, `df["team_code"]` when it does not. Per row, always.

### A7 — the derivation runs in `load_training_frame`, where the fixture list is already in hand.

`models/train.py:250-277` loads `history/player_gw.parquet` and `history/fixtures.parquet`, appends the live season to both, and calls `apply_new_bps(player_gw, fixtures=fixtures)` — which already does this exact join for the BPS restatement. The `club_code` derivation goes immediately after that call, before `add_player_rolling` at `:289`. `train.py` is not protected. Every consumer of the training frame — `cli.train`, `evaluation`, `calibrate_noise`, `zeros_diagnostic`, `backtest`, and `advise.py:542` — gets the column for free without one of them being edited.

### A8 — the shared join is factored out of `bps.py`, and `fixture_key` must stay byte-identical.

`bps.fixture_key` (`bps.py:70-119`) already builds exactly the lookup D2 needs, including the semantics the spec asks to inherit: lines `110-112` poison any `(season_idx, gw, kickoff_time, team)` claimed by two different fixtures to `None`, so corruption becomes an unmatched row rather than a mis-keyed one.

Task 3 extracts lines `102-112` verbatim into `_fixture_lookup(fixtures) -> dict`, leaves `fixture_key` as the row-side application at `114-119`, and builds `as_of_club_code(df, fixtures)` on the same dict. **`tests/test_bps.py` must pass completely unmodified** — in particular `test_fixture_key_drops_an_ambiguous_key_instead_of_last_wins` (`:218`), which is the corruption semantics this refactor is not allowed to move. If a single assertion there needs touching, the extraction is wrong.

The club itself comes out of the matched fixture ident, which carries both sides: the player's opponent is `opp_code`, so his club is the *other* code in the pair, and `was_home` cross-checks it. A row whose `was_home` disagrees with the side the join assigned is dropped to the fallback rather than trusted — a disagreement means the fixture list and the player row describe different matches.

### A9 — only the own-team side of the Elo merge switches.

`add_context` (`engineer.py:606-615`) merges Elo twice: on `team_code` and on `opp_code`. `opp_code` is written per row from the fixture at ingest (`data/live.py:106`) and is already correct through a transfer — `bps.py:79-80` says so explicitly. Only the `team_code` side (`:607,609,613`) is stale, so only that side moves to `as_of_club`. Touching the opponent side would be a change with no finding behind it.

### A10 — `club_code` reaches serve time without a protected edit, and that is load-bearing.

`advise.py:548` strips `[c for c in feature_columns() if c in hist.columns]` off the training frame before re-deriving. `feature_columns()` returns rolling means, Understat blocks, shrunken rates and a fixed tail of context columns — it does **not** name `club_code`. So the column survives into `hist_raw`, into `build_prediction_frame`'s `hist`, and into every history-side computation the serving path runs (`latest_shrunken_rates`, `latest_rotation_priors`, the `add_context` merge over the combined frame). Train and serve therefore see the same club for the same historical row, which is the whole point; future rows fall back per A6. No line of `advise.py` changes.

### A11 — D2's eval delta is recorded, not gated.

Spec §0 D2 is explicit: the fix ships whether or not eval improves, because a regression here would mean the old number was flattered by leakage. So there is no keep rule to pre-register — there is a **measurement contract**: the same `evaluate_benchmark()` protocol as D1, run with the derivation off and on, with both stratum tables transcribed into spec §4, plus two numbers that say how much leak there was at all:

- **coverage** — the fraction of history rows for which a fixture matched and a club was derived;
- **divergence** — the fraction of *covered* rows where the derived `club_code` differs from the stamped `team_code`. This is the leak, measured. If it is a handful of rows the eval delta will be noise, and saying so is a result.

### A12 — D4 uses the existing `"failed"` status. A new `"abandoned"` value would cost a second protected edit.

`JobRun.status`'s vocabulary is pinned in a comment at `jobs.py:152`: `queued | running | done | failed`. More sharply, the SSE generator terminates only on `run.status in ("done", "failed")` (`routers/jobs.py:131`); any other value leaves every open stream polling at `POLL_S = 0.25` until `IDLE_TIMEOUT_S = 3600` expires — an hour of a pinned threadpool worker per watcher, which is the adjacent problem the spec explicitly put out of scope.

So abandonment is `status="failed"` with the explanation in `error`. The module's own docstring (`jobs.py:9-12`) supplies the wording:

```
timed out after 1800s — abandoned as a daemon, its thread still running
```

(The spec attributes this phrasing to a "§10" section. There is no §10 in `jobs.py`; the sections it uses are §2.1 and §5, and the abandonment language lives in the module docstring at lines 9-12, describing the v6 `JobRegistry`'s timeout path. The wording is borrowed from there, which is what the spec intended.)

### A13 — zero pin updates, established by inspection rather than assumed.

The spec twice asks the implementer to enumerate any pin the cycle breaks and STOP for authorization. Enumerated, the answer is **none**:

- **The renamed field.** No `tests/test_*_degradation.py` asserts `p_haul` on an alternatives or captain payload. The only degradation references are `test_v8g_degradation.py:102,110` (both `/api/players` and `/api/components`, both band-sourced, both untouched) and `:193` (on the `Band` object). `test_differentials.py:33` and `test_assemble.py:88` pin *internal* column lists, which D3 leaves alone by construction.
- **The new route.** The tree's only route-set assertion is `test_v9a_degradation.py:289-296`, which filters `startswith("/api/assets")`. It is also keyed on OpenAPI *paths*, and `/api/jobs/current` is already a key — adding a method to an existing path could not move it even if the filter were wider.
- **Counts.** No job kind, no config key, no plist. The eight `== 12` pins and the three sorted-list pins stay as they are, which is precisely what `test_v8d_adds_no_job_kinds`, `test_v8g_adds_no_job_kinds` and `test_the_job_kinds_are_still_twelve` exist to hear.

The cycle's protected diff is therefore **exactly** Task 7's D4 lines and nothing else.

### A14 — the abandon must survive `_execute`'s `finally`, which is a fourth authorized line-group.

This is the one place where the spec's enumeration is incomplete, and it is the difference between a fix and a new bug. `_execute`'s `finally` (`jobs.py:319-328`) unconditionally writes `run.status`, `run.error`, `run.summary`, `run.finished_at` and then `self._current = None`. An abandoned job's thread is still alive — abandonment does not kill it — so it eventually reaches that block and:

1. **overwrites** the abandon's `"failed"` + explanation with whatever it finished as, erasing the record that says why the lane was freed; and worse,
2. **clears `self._current`** — which by then may name a *different, newer* job. The wedged run steals the lane out from under its own replacement, and the browser watching the new job is told nothing is running.

So the authorized diff guards both: the lane clear becomes conditional on `self._current == run.id`, and the status write is skipped when the run already holds a terminal status. Task 7's STOP enumerates this as a third edit inside `jobs.py` and **the orchestrator must authorize it explicitly** — it is one line-group beyond what spec D4 listed, and the plan says so rather than smuggling it in under "one small helper".

There is a rail watching this already: `tests/test_web_job_runner.py:208-254` monkeypatches `runner._lock` with a `_WatchingLock` that snapshots state on **every** release and asserts the lane never points at a terminal run. Any new locked block is observed by it. `_abandon_current` therefore writes the status and clears the lane inside **one** locked block, exactly as `_execute` does — for exactly the reason `_execute`'s own comment at `:320-323` gives.

### A15 — replay is a delta this cycle, not an equality, so it needs the seed trio on both sides.

v9a's replay gate was an equality check because v9a changed no number. v9c changes EP deliberately: if D1 ships, `card_penalty` moves; if D2's divergence is non-zero, three feature families move. **Branch ≠ main is the expected result**, and the v8a lesson applies with more force, not less — the banked 1876 that cost an investigation was stale for exactly this reason (a deliberate serving-default flip), and re-running main is the only valid comparison.

Because it is a **gap** reading rather than an equality, CONVENTIONS §1 governs: `K >= 3` seed bases on each side, and an aggregate is valid only across runs whose config echo differs in nothing but `seed_base`. v7b measured a 116-point seed spread on this very arm — larger than any gap this cycle could plausibly produce — so a single-draw "branch is 30 points down" would be a measurement of the seed and nothing else. Task 10 runs `--seed-bases` trios in both worktrees and reads mean ± spread through `scripts/seed_stats.py`.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/features/engineer.py` | Modify (`ROLL_STATS` L14-16) | T1: `rc` joins the rolled stats. |
| `scripts/v9c_rc_arm.py` | Create | T1: the D1 arm driver (baseline vs `+rc`). |
| `tests/test_v9c_cards.py` | Create | T1: `rc_r38` exists, rolls, and reaches `card_penalty`. |
| `src/gaffer/models/components.py` | Modify (L146-157) | T2, **withdraw branch only**: the documented zero. |
| `src/gaffer/features/bps.py` | Modify (extract L102-112; append) | T3: `_fixture_lookup`, `as_of_club_code`. |
| `tests/test_v9c_club_code.py` | Create | T3: derivation, coverage, corruption, fallback. |
| `src/gaffer/models/train.py` | Modify (`load_training_frame` L276-289) | T4: derive the column into the frame. |
| `src/gaffer/features/engineer.py` | Modify (append helper; L299, L607-613, L990) | T4: `as_of_club` + the three consumers. |
| `tests/test_v9c_engineer_club.py` | Create | T4: the three switched builders. |
| `scripts/v9c_club_eval.py` | Create | T5: before/after eval + coverage + the transferred-player demo. |
| `src/gaffer/web/routers/advice.py` | Modify (`latest` L112-127; append transform) | T6: `with_attacking_haul`. |
| `src/gaffer/web/schemas.py` | Modify (docstrings at L439, L619) | T6: say which quantity each is. |
| `src/gaffer/models/assemble.py` | Modify (docstring L39-42) | T6: cross-reference `uncertainty`. |
| `src/gaffer/uncertainty.py` | Modify (docstring near L120-133) | T6: cross-reference `assemble`. |
| `src/gaffer/report/templates/report.html.j2` | Modify (L92, L113) | T6: the two `P(haul)` headers. |
| `frontend/src/hubs/this-week/SquadTable.tsx` | Modify (L48-50, L84) | T6: the chip says which haul. |
| `tests/test_web_advice_haul.py` | Create | T6: both payloads, both directions. |
| `src/gaffer/web/jobs.py` | Modify (**PROTECTED — T7 STOP only**) | T7: `_abandon_current`, `start`, `_execute` guard. |
| `src/gaffer/web/routers/jobs.py` | Modify (**PROTECTED — T7 STOP only**) | T7: `DELETE /api/jobs/current`. |
| `tests/test_v9c_job_timeout.py` | Create | T8: timeout, cancel, 409 recovery. |
| `tests/test_v9c_degradation.py` | Create | T9: G2. |
| `scripts/v9c_replay.sh` | Create | T10: the branch≡main trio pair, one file. |
| `README.md` | Modify | T10: the `club_code` column, the cancel endpoint. |
| `docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md` | Modify (§5) | T11: the checklist. |

---

## Task 1 — `rc` joins `ROLL_STATS`, and the harness that will decide whether it stays

**Files:**
- Modify `src/gaffer/features/engineer.py`
- Create `tests/test_v9c_cards.py`
- Create `scripts/v9c_rc_arm.py`

**Read A2, A3 and A4 before starting.** This task ships the change *and* the instrument that may withdraw it. It does not run the instrument (CONVENTIONS §7).

- [ ] **Write the failing test.** Create `tests/test_v9c_cards.py`:

```python
"""The red-card term, which has been zero since the day it was written.

``card_penalty`` reads ``rc_r38`` and multiplies it by -3. ``ROLL_STATS``
rolled ``yc`` and not ``rc``, so the key never existed, and ``_rate``'s
defensive ``row.get(key, 0.0)`` — written to survive a player with no card
history — turned a missing *column* into a clean zero for every player in
every gameweek. A defence against sparse data absorbed a defect in the
feature list, and nothing failed.

These tests are the ones that would have caught it: not "does the formula
multiply by -3" (it always did) but "is there a number here to multiply".
"""

from __future__ import annotations

import pandas as pd

from gaffer.data.live import CANONICAL_COLS
from gaffer.features.engineer import ROLL_STATS, add_player_rolling
from gaffer.models.components import card_penalty


def _sent_off_then_played(n: int = 6) -> pd.DataFrame:
    """One player, one red card in his first match, five clean ones after."""
    return pd.DataFrame({
        "code": [1] * n,
        "season_idx": [3] * n,
        "gw": list(range(1, n + 1)),
        "rc": [1.0] + [0.0] * (n - 1),
        "yc": [0.0] * n,
        "minutes": [90.0] * n,
    })


def test_rc_is_rolled_like_every_other_disciplinary_stat():
    """The one-line finding. ``yc`` was there; ``rc`` was not."""
    assert "rc" in ROLL_STATS
    assert "yc" in ROLL_STATS


def test_rc_is_stored_so_the_feature_costs_no_new_ingest():
    """``data/live.py`` has renamed ``red_cards -> rc`` and banked it since
    the store was written. This was never a missing *column*, only a missing
    list entry."""
    assert "rc" in CANONICAL_COLS


def test_the_rolling_window_exists_and_is_shifted_off_the_current_row():
    rolled = add_player_rolling(_sent_off_then_played())
    assert "rc_r38" in rolled.columns
    # Row 0 sees no prior match at all.
    assert pd.isna(rolled["rc_r38"].iloc[0])
    # Row 1 sees exactly the sending-off.
    assert rolled["rc_r38"].iloc[1] == 1.0
    # And it decays as clean matches accumulate, rather than sticking.
    assert rolled["rc_r38"].iloc[5] < rolled["rc_r38"].iloc[1]


def test_the_red_term_now_actually_fires():
    """The whole finding, in one assertion. Before this cycle both rows
    returned the same number."""
    sent_off = pd.Series({"yc_r38": 0.0, "rc_r38": 0.2})
    clean = pd.Series({"yc_r38": 0.0, "rc_r38": 0.0})
    assert card_penalty(sent_off) < card_penalty(clean)
    assert card_penalty(sent_off) == -0.6


def test_a_player_with_no_card_history_is_still_a_clean_zero():
    """``_rate``'s NaN guard is still doing its real job — the one it was
    written for — now that it is no longer covering for a missing column."""
    assert card_penalty(pd.Series({"yc_r38": float("nan"),
                                   "rc_r38": float("nan")})) == 0.0


def test_no_model_feature_list_gains_a_card_column(monkeypatch):
    """Plan A2, asserted rather than assumed: the five new columns reach the
    deterministic ``card_penalty`` and nothing that is fitted. If a future
    cycle puts an ``rc_*`` column into a model's inputs, this cycle's whole
    argument for a cheap arm stops holding, and this is where that is
    discovered."""
    from gaffer.models.attacking import ATTACK_FEATURES
    from gaffer.models.components import (BONUS_FEATURES, DEFCON_FEATURES,
                                          SAVES_FEATURES)
    from gaffer.models.team import TEAM_FEATURES
    from gaffer.models.train import MINUTES_FEATURES

    for name, cols in (("minutes", MINUTES_FEATURES),
                       ("attacking", ATTACK_FEATURES),
                       ("defcon", DEFCON_FEATURES),
                       ("saves", SAVES_FEATURES),
                       ("bonus", BONUS_FEATURES),
                       ("team", TEAM_FEATURES)):
        assert not [c for c in cols if c.startswith("rc_")], name


def test_feature_columns_names_the_new_block_so_advise_strips_it():
    """``advise.py:548`` strips ``feature_columns()`` off the training frame
    before re-deriving. A rolled column missing from that list would survive
    the strip and be re-derived beside itself, and pandas would hand every
    later ``df[col]`` a two-column frame."""
    from gaffer.features.engineer import feature_columns

    assert "rc_r38" in feature_columns()
```

Run it: `uv run pytest -q tests/test_v9c_cards.py` — expect four failures, all of them "rc" missing.

- [ ] **Implement — one list entry.** In `src/gaffer/features/engineer.py`, extend `ROLL_STATS` (L14-16) and say why the entry is load-bearing:

```python
ROLL_STATS = ["total_points", "minutes", "starts", "goals", "assists", "xg",
              "xa", "xgi", "xgc", "cs", "gc", "saves", "bonus", "bps",
              "defcon", "tackles", "cbi", "recoveries", "yc", "rc"]
"""Per-match stats rolled into ``{stat}_r{window}`` means.

``rc`` is here because ``models.components.card_penalty`` reads ``rc_r38``
and always has. Until v9c it was not in this list, so the column did not
exist, and ``card_penalty``'s ``row.get(key, 0.0)`` — a guard written for
players with no card history — turned the missing column into 0.0 for every
player in every gameweek. The -3 red-card term was identically dead from the
day it was written, silently, and nothing in the suite could see it.

The entry is one word and the consequence is five columns in the training
frame, so v9c gated it as an arm rather than shipping it as a hotfix (spec
D1). No model's feature list names an ``rc_*`` column — every list in this
repo is explicit — so the only consumer is the closed-form penalty above.
"""
```

- [ ] **Build the arm driver.** Create `scripts/v9c_rc_arm.py`:

```python
"""Gate G1, D1: does switching the red-card term on cost anything?

Two arms on the fixed 2024-25 walk-forward benchmark — ``baseline`` with
``ROLL_STATS`` as it stood before v9c, ``rc`` with the entry added — and the
pre-registered rule below applied to the second against the first.

Run it, watch it, read the verdict::

    mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v9c_rc_arm.py \\
        > logs/v9c_rc_arm.log 2>&1 &
    grep -e V9C_ARM_DONE -e V9C_VERDICT logs/v9c_rc_arm.log

**The pre-registered rule (plan A4), fixed before the first run:** this is a
*non-regression* gate, not an improvement gate. v8a's arms were candidate
signals and had to earn their place with a zeros gain; this is a term the
model has always documented and never applied, so the question is only
whether switching it on costs anything. SHIP iff no stratum's RMSE regresses
by more than :data:`GUARD_TOLERANCE`. Any breach withdraws, and the plan's
Task 2 then zeroes the term explicitly with these numbers in the comment.

Two differences from ``scripts/v8a_arms.py``, both forced (plan A2, A3):

* **The frame is not memoised.** v8a's arms differed in a feature *list* over
  one frame; this arm differs in the frame itself, so each arm pays for its
  own ``load_training_frame``. That is most of the wall clock.
* **The intervention mutates the list in place.** ``ROLL_STATS`` is a mutable
  default argument on four functions in ``engineer`` — rebinding the module
  global would leave every one of those defaults pointing at the original
  object, and both arms would silently build the same frame and report a gap
  of exactly zero. ``_frames_differ`` below refuses to report a verdict
  unless the two frames actually differ.
"""

from __future__ import annotations

import json
from pathlib import Path

import gaffer.evaluation as ev
from gaffer.features import engineer
from gaffer.models import train as tr

GUARD_TOLERANCE = 0.005
"""v8a's own tolerance, reused so the two cycles read on one scale."""

CANDIDATE = "rc"


def scores(payload: dict) -> dict:
    """The three numbers the rule reads, off a benchmark payload.

    Identical to ``v8a_arms.scores`` so the two cycles' arm tables can be put
    beside each other without a footnote.
    """
    table = payload["stratified"]["all"]
    return {"zeros": table["zeros"]["rmse"],
            "haulers": table["haulers"]["rmse"],
            "all": table["all"]["rmse"],
            "zeros_n": table["zeros"]["n"]}


def verdict(base: dict, arm: dict) -> dict:
    """The pre-registered non-regression rule, applied once."""
    costs = {k: round(arm[k] - base[k], 4)
             for k in ("zeros", "haulers", "all")}
    ship = all(c <= GUARD_TOLERANCE for c in costs.values())
    return {**{f"{k}_cost": v for k, v in costs.items()},
            "tolerance": GUARD_TOLERANCE,
            "decision": "ship" if ship else "withdraw"}


def _column_count() -> int:
    """How many rolled columns the current ``ROLL_STATS`` produces.

    The guard against A3's trap: if the in-place mutation did not take, both
    arms build the same frame and this number does not move.
    """
    return len(engineer.feature_columns())


def main() -> None:
    assert CANDIDATE in engineer.ROLL_STATS, (
        "run this on a branch where the candidate has shipped; the baseline "
        "arm is produced by removing it, not by adding it")
    results: dict[str, dict] = {}
    widths: dict[str, int] = {}

    # Baseline first, so a crash leaves the shipped list restored.
    engineer.ROLL_STATS.remove(CANDIDATE)
    try:
        widths["baseline"] = _column_count()
        results["baseline"] = scores(ev.evaluate_benchmark())
        print("V9C_ARM_DONE baseline", json.dumps(results["baseline"]),
              flush=True)
    finally:
        engineer.ROLL_STATS.append(CANDIDATE)

    widths[CANDIDATE] = _column_count()
    results[CANDIDATE] = scores(ev.evaluate_benchmark())
    print("V9C_ARM_DONE", CANDIDATE, json.dumps(results[CANDIDATE]),
          flush=True)

    if widths[CANDIDATE] <= widths["baseline"]:
        # Refuse to report rather than report a zero gap that means nothing.
        raise SystemExit(
            f"the intervention did not take: {widths['baseline']} feature "
            f"columns baseline vs {widths[CANDIDATE]} with the candidate. "
            f"See plan A3 — ROLL_STATS is a mutable default argument.")

    v = verdict(results["baseline"], results[CANDIDATE])
    print("V9C_VERDICT", CANDIDATE, json.dumps(v), flush=True)
    print("V9C_DECISION", v["decision"], flush=True)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/v9c_rc_arm.json").write_text(
        json.dumps({"arms": results, "widths": widths, "verdict": v},
                   indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Verify.** The suite, and a smoke test that the driver imports and the guard is live:

```bash
uv run pytest -q tests/test_v9c_cards.py tests/test_components.py \
  tests/test_engineer.py tests/test_train.py
uv run python -c "import scripts.v9c_rc_arm as a; print(a.verdict(
  {'zeros':1.0,'haulers':5.0,'all':2.0},
  {'zeros':1.02,'haulers':5.0,'all':2.0}))"
# must print decision 'withdraw' — a 0.02 zeros regression breaches 0.005
uv run pytest -q
```

The full run must be the merged-`main` baseline plus this file's tests, all green. If any pre-existing test moves, the one-word change had a consumer this plan did not find: **stop and report**.

- [ ] **Commit.**

```bash
git add src/gaffer/features/engineer.py tests/test_v9c_cards.py \
  scripts/v9c_rc_arm.py && git commit -m "$(cat <<'EOF'
feat: roll rc, so the red-card term has a number to read

card_penalty has multiplied rc_r38 by -3 since it was written, and ROLL_STATS
rolled yc and not rc — so the column never existed and _rate's missing-key
guard returned a clean 0.0 for every player in every gameweek. One list entry
ends that. It adds five columns to the training frame, so it ships behind an
arm (scripts/v9c_rc_arm.py, non-regression rule pre-registered in the driver's
docstring) rather than as a hotfix.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — 🛑 the D1 gate: run the arm, then ship it or zero it

**Files (one branch or the other, never both):**
- *ship branch:* none — Task 1 already shipped it; only the docstring gains the numbers.
- *withdraw branch:* Modify `src/gaffer/features/engineer.py`, Modify `src/gaffer/models/components.py`

### 🛑 STOP — the implementer does not run this arm

CONVENTIONS §7. Hand the orchestrator the command below and wait. Self-certification is how an arm ends up measured against its author's expectation, and this author has just spent a task arguing the term should live.

```bash
mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v9c_rc_arm.py \
    > logs/v9c_rc_arm.log 2>&1 &
grep -e V9C_ARM_DONE -e V9C_VERDICT -e V9C_DECISION logs/v9c_rc_arm.log
```

Expect roughly **10-15 minutes** (two `evaluate_benchmark` runs at ~80 s each, plus one un-memoisable `load_training_frame` per arm — see the estimates at the end of this plan). The run banks `reports/v9c_rc_arm.json`; `reports/` is never staged, and the numbers reach the repo only by being transcribed.

**The rule is A4's and it was fixed before the run.** Do not re-read it against the numbers.

- [ ] **Wait for the verdict.** Then take exactly one of the two branches below.

#### Branch A — `V9C_DECISION ship`

- [ ] **Write the numbers into the docstring** so the next reader finds the measurement rather than a bare list entry. Append to `ROLL_STATS`'s docstring:

```
Measured, v9c G1 (2024-25 walk-forward, transcribed from the
``V9C_ARM_DONE`` lines): baseline zeros/haulers/all RMSE <B>, with ``rc``
<A>. Non-regression rule, tolerance 0.005: <VERDICT>. Shipped.
```

- [ ] **Commit** (`docs: v9c — the rc arm's numbers, in the docstring that owns them`).

#### Branch B — `V9C_DECISION withdraw`

The term ships **off and explicitly dead** (CONVENTIONS §6, spec D1). Two edits.

- [ ] **Revert the list entry** — `ROLL_STATS` loses `"rc"`, and its docstring keeps the finding and gains the reason the column is not there:

```
``rc`` is deliberately absent. ``card_penalty``'s red term read ``rc_r38``
from the day it was written and the column never existed, so the term was
identically zero; v9c added the entry, ran it as an arm, and withdrew it —
<VERDICT NUMBERS>. The finding is closed by the explicit zero in
``models.components.card_penalty``, not by this list.
```

- [ ] **Zero the term where it is read**, in `src/gaffer/models/components.py` (L146-157). The function keeps its shape; the red half becomes a documented constant rather than a live read of a column that is not built:

```python
def card_penalty(row: pd.Series) -> float:
    """Expected points from cards: -1 * yellow rate. The red term is zero.

    Rates are read defensively: a missing key or a NaN (a player with no
    card history in the rolling window) counts as zero, not NaN — note that
    ``NaN or 0.0`` returns NaN, since NaN is truthy.

    **The red-card term is deliberately absent** and this is the whole record
    of why. Until v9c this function read ``-3.0 * _rate("rc_r38")``, and
    ``rc`` was not in ``features.engineer.ROLL_STATS`` — so the column did not
    exist, the guard above returned 0.0, and the term was identically zero
    for every player since it landed. v9c built the column and measured it as
    an arm on the 2024-25 walk-forward benchmark: <ARM NUMBERS, VERBATIM>,
    which breaches the pre-registered 0.005 non-regression tolerance. The
    term is withdrawn.

    A red card is rare, arrives with a sending-off that already collapses the
    player's minutes, and a 38-match mean of it is a very small number
    multiplied by a large coefficient — which is a plausible reason the arm
    cost what it cost. Anyone reopening this should build the arm again
    rather than restoring the read: the point of this comment is that a term
    nobody measured was worth exactly nothing for a season.
    """
    def _rate(key: str) -> float:
        val = row.get(key, 0.0)
        return 0.0 if pd.isna(val) else float(val)

    return -1.0 * _rate("yc_r38")
```

- [ ] **Update `tests/test_v9c_cards.py`** to pin the withdrawn state instead: `"rc" not in ROLL_STATS`, `card_penalty` identical for a sent-off and a clean row, and the docstring naming the arm. Keep `test_rc_is_stored_so_the_feature_costs_no_new_ingest` and `test_no_model_feature_list_gains_a_card_column` — both still true, both still worth pinning.
- [ ] **Verify:** `uv run pytest -q`.
- [ ] **Commit** (`fix: withdraw the rc arm and zero the red-card term explicitly`).

**Either way the silent state ends,** which is what D1 was for. Record the branch taken in spec §4 (Task 11).

---

## Task 3 — the as-of club, derived from the fixture list that already knows

**Files:**
- Modify `src/gaffer/features/bps.py`
- Create `tests/test_v9c_club_code.py`

**Read A8 before starting.** The join already exists; this task extracts it and adds one function on top. `tests/test_bps.py` must pass **unmodified** at the end — if it does not, the extraction changed behaviour it was not allowed to change.

- [ ] **Write the failing test.** Create `tests/test_v9c_club_code.py`:

```python
"""Which club did this player actually play for that week?

``data/live.py`` rebuilds the whole player history each run and stamps the
player's *current* ``team_code`` onto every row of it (``live.py:170``, via
``history_to_rows``'s ``row.update(player_meta)``). So a January transfer
silently rewrites his August rows under his new club, and three feature
builders that key on club — the position-by-club prior, manager-spell
scoping, and the team-Elo merge — read a squad he had not joined yet.

``opp_code`` does not have this problem: it is written per row from the
fixture (``live.py:106``). That asymmetry is the whole derivation. Join the
fixture list on ``(season_idx, gw, kickoff_time)``, find the fixture whose
opponent matches, and the player's club is the *other* side.

``bps.fixture_key`` already does this join for the BPS restatement, including
the semantics that matter when the data is bad, so this is an extraction and
not a second implementation.
"""

from __future__ import annotations

import pandas as pd

from gaffer.features.bps import as_of_club_code, fixture_key


def _fixtures() -> pd.DataFrame:
    """Two seasons. Arsenal (3) host Man Utd (1) in each."""
    return pd.DataFrame({
        "season_idx": [3, 3, 4],
        "gw": [1, 2, 1],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z",
                         "2025-08-16T14:00:00Z"],
        "home_code": [3, 43, 3],
        "away_code": [1, 3, 1],
        "home_goals": [1.0, 2.0, 0.0],
        "away_goals": [0.0, 2.0, 3.0],
    })


def _transferred() -> pd.DataFrame:
    """One player, stamped as Arsenal (3) today, who played GW1 for Man Utd.

    His GW1 row says ``opp_code = 3`` — he faced Arsenal — while ``team_code``
    claims he *was* Arsenal. Both cannot be true, and the fixture list is the
    one that was written at the time.
    """
    return pd.DataFrame({
        "code": [7, 7],
        "season_idx": [3, 3],
        "gw": [1, 2],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
        "team_code": [3, 3],
        "opp_code": [3, 43],
        "was_home": [False, True],
    })


# --- the derivation -------------------------------------------------

def test_a_transferred_players_old_rows_carry_his_old_club():
    """The finding, in one assertion."""
    club = as_of_club_code(_transferred(), _fixtures())
    assert club.iloc[0] == 1        # he was Man Utd in GW1
    assert club.iloc[1] == 3        # and Arsenal by GW2


def test_a_player_who_never_moved_gets_the_same_club_he_is_stamped_with():
    """The overwhelming majority of rows. The column must be a no-op for
    them, or the delta this cycle measures is measuring the join and not the
    leak."""
    stayed = _transferred().assign(team_code=[1, 1], opp_code=[3, 3],
                                   gw=[1, 1], season_idx=[3, 4],
                                   kickoff_time=["2024-08-17T14:00:00Z",
                                                 "2025-08-16T14:00:00Z"])
    club = as_of_club_code(stayed, _fixtures())
    assert club.tolist() == [1, 1]


def test_was_home_cross_checks_the_side_and_a_disagreement_falls_back():
    """A row whose ``was_home`` contradicts the side the join assigned is
    describing a different match from the fixture it matched. Trusting the
    join there would invent a club; the fallback at least says something the
    store already believed."""
    lying = _transferred().assign(was_home=[True, True])
    club = as_of_club_code(lying, _fixtures())
    assert club.iloc[0] == 3        # fell back to team_code


# --- what happens when the join misses ------------------------------

def test_a_row_matching_no_fixture_falls_back_to_the_stamped_club():
    orphan = _transferred().assign(gw=[97, 98])
    assert as_of_club_code(orphan, _fixtures()).tolist() == [3, 3]


def test_a_season_with_no_fixture_list_at_all_falls_back_wholesale():
    """Older seasons in ``history/`` predate the fixture archive. They keep
    the stamped club and the cycle records how many rows that is (spec §3:
    backfilling them is out of scope)."""
    club = as_of_club_code(_transferred(), _fixtures().iloc[0:0])
    assert club.tolist() == [3, 3]


def test_an_ambiguous_fixture_key_falls_back_rather_than_mis_keying():
    """``fixture_key``'s corrupt-duplicate semantics, inherited: a
    ``(season, gw, kickoff, team)`` claimed by two different fixtures is
    poisoned to ``None`` rather than resolved last-wins, so the row falls
    back. A mis-keyed club is worse than a stale one — it is a club the
    player has never played for."""
    dupes = pd.concat([_fixtures(), _fixtures().iloc[[0]].assign(away_code=99)],
                      ignore_index=True)
    assert as_of_club_code(_transferred(), dupes).iloc[0] == 3


def test_the_result_is_never_nan_and_never_a_float():
    """G2's rail. A NaN here would scatter every downstream groupby into a
    silent extra bucket, and a float club code would not compare equal to the
    int one in the Elo frame."""
    club = as_of_club_code(_transferred(), _fixtures())
    assert club.notna().all()
    assert str(club.dtype).startswith("int") or club.map(
        lambda v: float(v).is_integer()).all()


def test_a_frame_missing_the_join_columns_degrades_instead_of_raising():
    thin = _transferred().drop(columns=["kickoff_time"])
    assert as_of_club_code(thin, _fixtures()).tolist() == [3, 3]


# --- the extraction did not move fixture_key ------------------------

def test_fixture_key_still_answers_exactly_what_it_did(monkeypatch):
    """Belt and braces beside ``tests/test_bps.py``, which must pass
    unmodified: the extraction is a refactor, and a refactor that changes an
    answer is a rewrite."""
    keys = fixture_key(_transferred(), _fixtures())
    assert keys.notna().all()
    assert keys.iloc[0] != keys.iloc[1]
```

Run it: `uv run pytest -q tests/test_v9c_club_code.py` — expect `ImportError` on `as_of_club_code`.

- [ ] **Extract the lookup.** In `src/gaffer/features/bps.py`, lift the lookup-build loop (currently `fixture_key`'s L102-112) into a module function, leaving `fixture_key` as the row-side application it already is. The loop body moves **verbatim** — including the `None` poisoning — because that behaviour is what `tests/test_bps.py:218` pins:

```python
def _fixture_lookup(fixtures: pd.DataFrame) -> dict:
    """``{(season_idx, gw, kickoff_time, team_code): ident | None}``.

    Extracted from :func:`fixture_key` in v9c so :func:`as_of_club_code` can
    build on the same join rather than writing a second one that agrees with
    it until the day it does not. The body is unchanged, and that includes the
    clause that matters most: a key claimed by two different fixtures is
    poisoned to ``None`` rather than resolved last-wins, so corrupt data
    becomes an unmatched row instead of a confidently wrong one.
    """
```

`fixture_key` then calls it. Its own docstring gains one line pointing at the new sibling.

- [ ] **Add the derivation** beside it:

```python
def as_of_club_code(df: pd.DataFrame, fixtures: pd.DataFrame) -> pd.Series:
    """The club each row's player actually played for, not the one he is at.

    ``data/live.py`` rebuilds player history every run and stamps today's
    ``team_code`` onto every row of it, so a January transfer rewrites the
    player's August rows under his new club. Three feature builders key on
    club — the position-by-club prior, manager-spell scoping and the own-side
    Elo merge — and every one of them reads a squad the player had not joined
    (spec D2).

    ``opp_code`` survives a transfer because it is written per row from the
    fixture, and that asymmetry is the derivation: match the row to its
    fixture on ``(season_idx, gw, kickoff_time)`` where one side is
    ``opp_code``, and the player's club is the other side. ``was_home``
    cross-checks it; a row that disagrees is describing a different match
    from the fixture it matched, and falls back rather than inventing a club.

    Rows that match no fixture fall back to ``team_code``, and so do whole
    seasons with no archived fixture list (spec §3 puts backfilling those out
    of scope). The fallback is never NaN: a NaN club would scatter every
    downstream ``groupby`` into a silent extra bucket, which is a worse
    failure than the staleness this function exists to fix.
    """
```

Implementation notes for the body, in order: guard the required columns and return `df["team_code"]` if any is missing; build `_fixture_lookup(fixtures)`; zip the row keys exactly as `fixture_key` does (`season_idx`, `gw`, `kickoff_time` as string, `opp_code` numeric); for each matched ident take the side that is not `opp_code`; drop to the fallback when the ident is `None`, when both sides equal `opp_code`, or when `was_home` disagrees with the assigned side; return an integer Series aligned on `df.index`.

- [ ] **Verify — including the untouched original suite.**

```bash
uv run pytest -q tests/test_v9c_club_code.py tests/test_bps.py
git diff --stat -- tests/test_bps.py    # must be empty
uv run pytest -q
```

- [ ] **Commit.**

```bash
git add src/gaffer/features/bps.py tests/test_v9c_club_code.py \
  && git commit -m "$(cat <<'EOF'
feat: derive the club a player actually played for, per row

data/live.py stamps today's team_code over every history row, so a January
transfer rewrites the player's August training rows under his new club.
opp_code is fixture-sourced and survives the move, so the fixture list can say
which side he was on: as_of_club_code joins on (season_idx, gw, kickoff_time),
takes the side opp_code is not, and cross-checks was_home. fixture_key's
lookup is extracted rather than duplicated, corrupt-duplicate poisoning and
all; rows and seasons with no fixture fall back to team_code, never to NaN.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — wire the column into the frame and switch the three consumers

**Files:**
- Modify `src/gaffer/models/train.py`
- Modify `src/gaffer/features/engineer.py`
- Create `tests/test_v9c_engineer_club.py`

**Read A6, A7, A9 and A10 before starting.** The coalesce is per row, the derivation runs where the fixtures already are, only the own-team side of the Elo merge moves, and nothing in `advise.py` changes.

- [ ] **Write the failing test.** Create `tests/test_v9c_engineer_club.py` covering, in this order:

1. **`as_of_club` is a per-row coalesce.** A frame with `club_code` NaN on some rows returns `team_code` on exactly those rows and `club_code` on the others. A frame with no `club_code` column at all returns `team_code` throughout, and does not raise.
2. **The prediction frame's future rows keep their current club.** Build a history frame carrying `club_code` and a future frame that cannot, run `build_prediction_frame`, and assert `team_elo` is populated on every future row — this is the assertion that fails if anyone rewrites A6's coalesce as a column-presence check.
3. **`_shrunk_ratio` groups by the as-of club.** Two players with the same position, one of whom transferred mid-season: his pre-transfer contributions land in the old club's `(pos, team)` bucket, not the new one. Assert the prior differs from the `team_code`-keyed answer.
4. **Manager-spell scoping keys on the as-of club.** A player whose GW1-19 rows belong to a club with one manager and GW20+ to a club with another gets two spells, not one; the pre-transfer rows carry the old manager's spell key.
5. **The Elo merge switches the own side only.** `team_elo` on a pre-transfer row is the old club's Elo; `opp_elo` is identical to what it was before this cycle. A regression here would be silent and expensive, so assert `opp_elo` explicitly.
6. **`club_code` survives the round trip to serve time.** `feature_columns()` does not name `club_code`, so `advise.py`'s strip leaves it on — assert `"club_code" not in feature_columns()` and that a frame stripped by `feature_columns()` still carries it. This is the pin that keeps A10 true without editing a protected file to make it true.
7. **A frame with no `club_code` produces exactly what `main` produced.** The degradation direction: with the column absent everywhere, the three builders' outputs are unchanged from the `team_code` path.

- [ ] **Add the helper** to `src/gaffer/features/engineer.py`, near the top with the other shared readers:

```python
def as_of_club(df: pd.DataFrame) -> pd.Series:
    """The club to key club-scoped features on, per row.

    ``club_code`` is what the player's club actually was that week
    (:func:`gaffer.features.bps.as_of_club_code`); ``team_code`` is what the
    store stamped on him this morning. Historical rows carry the first,
    future rows cannot — and for a future row the current club *is* the as-of
    club, so falling back is not a degradation there, it is the right answer.

    The fallback is deliberately **per row** rather than per frame.
    ``build_prediction_frame`` concatenates history with future rows, so a
    ``"club_code" in df.columns`` check would see the column present and read
    NaN for every serving row — the Elo merge would miss on all of them and
    the model would predict against a null opponent strength. Per row, always.
    """
    if "club_code" not in df.columns:
        return df["team_code"]
    return df["club_code"].where(df["club_code"].notna(), df["team_code"])
```

- [ ] **Derive the column in `load_training_frame`.** In `src/gaffer/models/train.py`, immediately after the `apply_new_bps` call (L276-277) and before the `max_season_idx` truncation:

```python
    # The as-of club, derived once here because this is the only place that
    # holds both the player rows and the fixture list (spec D2). Downstream,
    # ``club_code`` is read through ``engineer.as_of_club``, which falls back
    # to ``team_code`` per row — so every consumer of this frame that has not
    # been switched behaves exactly as it did, and the serving path's future
    # rows, which cannot have a club_code, are correct by that fallback
    # rather than by an exception.
    player_gw = player_gw.assign(
        club_code=as_of_club_code(player_gw, fixtures))
```

Import `as_of_club_code` from `gaffer.features.bps` beside the existing `apply_new_bps` import.

- [ ] **Switch the three consumers** in `src/gaffer/features/engineer.py`. Each is one expression plus a comment naming the spec decision:

| Site | Was | Becomes |
| --- | --- | --- |
| `add_rotation_priors` L299 | `spell_keys(out["team_code"], …)` | `spell_keys(as_of_club(out), …)` — spells are club tenures, so the as-of club is the only key that names the right manager |
| `add_context` L606-613 | `team_elo` merged and filled on `team_code` | merged and filled on a temporary `_club` column from `as_of_club`; **`opp_code` untouched** (A9) |
| `_shrunk_ratio` L990 | `"team": df["team_code"].to_numpy()` | `"team": as_of_club(df).to_numpy()` — a position-by-club prior about a club the player was not at is a prior about the wrong squad |

The guard at `add_rotation_priors` L281 (`{"code", "team_code", "starts", "season_idx"} <= set(df.columns)`) stays as it is: `team_code` is still required, because it is still the fallback.

`build_prediction_frame`'s own `spell_keys` call at L713-717 switches too, for consistency — on a future-rows-only frame `as_of_club` returns `team_code` and the answer is identical, but leaving one call site reading the raw column is how the next reader concludes the switch was partial on purpose.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_v9c_engineer_club.py tests/test_engineer.py \
  tests/test_train.py tests/test_advise.py tests/test_backtest.py
uv run pytest -q
```

`tests/test_advise.py` is protected and must pass **unmodified** — it is the assertion that A10 held and that the serving path needed no edit.

- [ ] **Commit.**

```bash
git add src/gaffer/models/train.py src/gaffer/features/engineer.py \
  tests/test_v9c_engineer_club.py && git commit -m "$(cat <<'EOF'
feat: key the club-scoped features on the club the player was actually at

load_training_frame derives club_code once, where the fixture list is already
in hand, and engineer.as_of_club coalesces it to team_code per row — per row,
because build_prediction_frame concatenates history with future rows and a
frame-level check would null the Elo merge on every serving row. Three
consumers switch: the position-by-club prior, manager-spell scoping, and the
own side of the Elo merge. opp_code is fixture-sourced and already correct, so
it does not move. feature_columns() does not name club_code, so the column
rides to serve time without a line of the protected advise.py changing.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — measure D2: coverage, divergence, and the eval delta

**Files:**
- Create `scripts/v9c_club_eval.py`

**Read A11.** This is not a gate. D2 ships either way; what this task builds is the instrument that says how much leak there was and what closing it cost or bought.

- [ ] **Build the driver.** Create `scripts/v9c_club_eval.py`, which does three things and prints each on its own greppable line:

1. **`V9C_CLUB_COVERAGE`** — over the full training frame: total history rows, rows where a fixture matched, and rows where the derived `club_code` **differs** from the stamped `team_code`, as counts and fractions, broken down by `season_idx`. The divergence fraction is the leak, measured. Everything else in this task is interpreting it.
2. **`V9C_CLUB_DEMO`** — the concrete demonstration G1 asks for. Pick the transferred player with the most diverging rows automatically (`groupby("code")` on the divergence mask, take the max) and print his code, name, and a small table of his season: `gw`, `opp_code`, `team_code`, `club_code`. His pre-transfer rows must show the old club in `club_code` and the new one in `team_code`. Printing the *automatically chosen* player rather than a hardcoded one means the gate cannot be passed by picking a flattering example.
3. **`V9C_CLUB_DONE`** — `scores(evaluate_benchmark())` in the same shape as Task 1's driver, once with the derivation off and once on, then the deltas. The off arm is produced by monkeypatching `bps.as_of_club_code` to return `df["team_code"]` — the smallest possible intervention, and one that exercises the identical code path in both arms.

Bank the whole thing to `reports/v9c_club_eval.json`. Guard the same way Task 1's driver does: if the "off" and "on" frames have the same divergence count, the intervention did not take and the script exits rather than reporting a zero delta.

### 🛑 STOP — the orchestrator runs this

```bash
mkdir -p logs && caffeinate -i nohup .venv/bin/python scripts/v9c_club_eval.py \
    > logs/v9c_club_eval.log 2>&1 &
grep -e V9C_CLUB_COVERAGE -e V9C_CLUB_DEMO -e V9C_CLUB_DONE logs/v9c_club_eval.log
```

Roughly **10-15 minutes**, the same shape as Task 2's run.

- [ ] **Commit the driver** (`test: the D2 instrument — coverage, divergence, and the eval delta`). The numbers it produces go into spec §4 at Task 11, transcribed verbatim (CONVENTIONS §4), **including a regression if that is what it measures** — spec D2 is explicit that the fix ships anyway, because the old number was flattered by leakage.

---

## Task 6 — `p_attacking_haul` at the serving boundary

**Files:**
- Modify `src/gaffer/web/routers/advice.py`
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/models/assemble.py`
- Modify `src/gaffer/uncertainty.py`
- Modify `src/gaffer/report/templates/report.html.j2`
- Modify `frontend/src/hubs/this-week/SquadTable.tsx`
- Create `tests/test_web_advice_haul.py`

**Read A1 first — the spec's map of this territory is wrong and the task is a different shape because of it.** There is no alternatives schema; the field rides through `AdviceLatest.advice: dict[str, Any]` untyped, so the rename is a new serve-time decoration rather than an edit to an existing field.

- [ ] **Write the failing test.** Create `tests/test_web_advice_haul.py`:

```python
"""Two quantities, one name, one page — and which one is which.

``assemble.p_haul`` is P(2 or more attacking returns) under a Poisson on
expected goals plus assists. ``uncertainty.Band.p_haul`` is P(total points
>= 10) in the tail of a normal on the whole forecast. They answer different
questions on different scales, and both were served as ``p_haul``.

The internal names do not move: the attacking one lives inside ``advise.py``
and ``optimize/differentials.py``, both protected, and a rename there would
cost an authorization to buy a label. So the split is resolved where the
payload leaves the process — a third serve-time decoration beside
``with_positions`` and ``with_identity``, which exist for exactly this reason
(v9a plan A2). The artifact on disk keeps ``p_haul``, so ``digest.py`` and
the since-last-run diff go on reading what they always read.
"""

from __future__ import annotations

# ... standard TestClient wiring, an advice artifact on disk carrying
# captain_options and alternatives with p_haul, and a solve state.


def test_the_alternatives_arrive_renamed():
    body = client.get("/api/advice/latest").json()["advice"]
    assert body["alternatives"][0]["p_attacking_haul"] == 0.4
    assert "p_haul" not in body["alternatives"][0]


def test_the_captain_options_arrive_renamed_too():
    body = client.get("/api/advice/latest").json()["advice"]
    assert body["captain_options"][0]["p_attacking_haul"] == 0.55
    assert "p_haul" not in body["captain_options"][0]


def test_the_band_field_keeps_its_name_on_the_players_table():
    """The other direction, and the one that makes the rename mean anything:
    if both fields were renamed the page would be exactly as ambiguous as it
    was, in a new vocabulary."""
    row = client.get("/api/players").json()[0]
    assert "p_haul" in row and "p_attacking_haul" not in row


def test_the_band_field_keeps_its_name_on_the_components_breakdown():
    player = client.get(f"/api/components/{GW}").json()["players"][0]
    assert "p_haul" in player


def test_the_artifact_on_disk_still_says_p_haul():
    """The rename is a decoration on the way out. ``digest.py`` reads this
    file, the since-last-run diff compares it against the previous run, and
    every advice file already banked must go on being readable."""
    before = advice_path.read_bytes()
    client.get("/api/advice/latest")
    assert advice_path.read_bytes() == before
    assert b"p_attacking_haul" not in before


def test_every_other_field_on_an_alternative_row_is_untouched():
    body = client.get("/api/advice/latest").json()["advice"]
    row = body["alternatives"][0]
    assert row["code"] == 11 and row["name"] == "Saka" and row["ep"] == 8.0
    assert row["league_eo"] == 80.0


def test_a_payload_with_no_alternatives_at_all_is_a_no_op():
    """``advise.py:854`` writes an empty frame when there is no buy to find
    an alternative to, and a cold clone has neither key."""
    # payload without 'alternatives'/'captain_options' → 200, unchanged.


def test_a_row_that_never_had_the_field_is_left_alone():
    """Advice files banked before this cycle, and any row where the optimizer
    wrote a partial record. Renaming a key that is not there must not invent
    a null."""
    # row without p_haul → no p_attacking_haul key appears.


def test_the_transform_does_not_mutate_the_loaded_payload():
    """``with_positions``' rule, for ``with_positions``' reason: the route is
    handed ``load_advice``'s dict and anything that cached it would inherit
    the rename."""
```

- [ ] **Implement the transform** in `src/gaffer/web/routers/advice.py`, beside `with_positions`:

```python
HAUL_KEYS = ("alternatives", "captain_options")
"""The two payload keys carrying ``assemble.p_haul``.

Both are written by ``advise.py`` as ``.to_dict("records")`` off frames whose
column list lives in ``optimize/differentials.py`` — two protected files, and
the reason this rename happens here (spec D3).
"""


def with_attacking_haul(payload: dict) -> dict:
    """Rename the *attacking* ``p_haul`` to ``p_attacking_haul`` on the way out.

    Two different quantities are called ``p_haul`` in this codebase.
    ``models.assemble.p_haul`` is P(2+ attacking returns) under a Poisson on
    expected goals plus assists, and it is what the alternatives and captain
    tables carry. ``uncertainty.Band.p_haul`` is P(total points >= 10) in the
    tail of a normal on the whole forecast, and it is what ``/api/players``
    and ``/api/components`` carry. They are not the same number, they are not
    on the same scale, and until v9c they were served under one name on one
    page.

    Renaming the internal column would mean diffs inside ``advise.py`` and
    ``optimize/**``, which are protected — not worth an authorization for a
    label. So the split is resolved here, at the boundary, and this is the
    single site at which it happens. The artifact on disk is untouched:
    ``digest.py`` reads it, the since-last-run diff compares against it, and
    every advice file already banked stays readable.

    Additive and defensive, like its two siblings: a payload with no
    alternatives, a row with no ``p_haul``, a key that is not a list — each
    comes back as it arrived.
    """
```

Implementation: copy the payload shallowly, walk `HAUL_KEYS`, and for each dict row that actually contains `p_haul`, emit a new dict with the key renamed in place (preserving order) and every other key untouched. Non-list values, non-dict entries and rows without the key pass through.

Then compose it at `latest()` (L125), and extend the comment above it from "two serve-time decorations" to three, naming what the third does:

```python
    payload = with_attacking_haul(
        with_identity(with_positions(load_advice(gw), state.pool), gw))
```

- [ ] **Say which is which, at both definitions.** `src/gaffer/models/assemble.py`'s `p_haul` (L39-42) gains a docstring line naming `uncertainty.Band.p_haul` as the other quantity and `p_attacking_haul` as its served name; `src/gaffer/uncertainty.py`'s `Band.p_haul` (near L132) gains the mirror. Two sentences each. Both files are unprotected. This is the half of D3 that survives a reader who never opens the router.

- [ ] **Label the two rendered surfaces.** These are the only places either quantity is drawn:

  - `src/gaffer/report/templates/report.html.j2` L92 and L113: `<th>P(haul)</th>` becomes `<th>P(2+ returns)</th>` in both the captain-options and the differential-alternatives tables. The template reads the on-disk artifact, so the *field* stays `p_haul` — it is the header that was ambiguous.
  - `frontend/src/hubs/this-week/SquadTable.tsx` L84: the chip text `haul ${pct(r.pHaul)}` becomes `10+ pts ${pct(r.pHaul)}`, and the `HAUL_CHIP` comment at L48-50 gains a line saying this is the band quantity and not the attacking one. The tooltip at L80-83 already says "chance of 10+ points" and is left alone — it was the one honest label in the tree.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_advice_haul.py tests/test_web_advice.py \
  tests/test_web_uncertainty.py tests/test_report.py tests/test_digest.py \
  tests/test_differentials.py tests/test_assemble.py
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

`tests/test_differentials.py:33` and `tests/test_assemble.py:88` pin the internal column lists and must pass **unmodified** — they are the assertion that the rename stayed at the boundary.

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/advice.py src/gaffer/web/schemas.py \
  src/gaffer/models/assemble.py src/gaffer/uncertainty.py \
  src/gaffer/report/templates/report.html.j2 \
  frontend/src/hubs/this-week/SquadTable.tsx \
  tests/test_web_advice_haul.py && git commit -m "$(cat <<'EOF'
fix: two quantities called p_haul stop sharing a name at the boundary

assemble.p_haul is P(2+ attacking returns) under a Poisson; Band.p_haul is
P(total points >= 10) in a normal tail. Both were served as "p_haul" on the
same page. The attacking one is renamed to p_attacking_haul by a third
serve-time decoration in routers/advice.py — the internal column keeps its
name inside the protected pipeline, and the artifact on disk is byte-untouched
so digest and the since-last-run diff read what they always read. The two
definitions now cross-reference each other, the report's "P(haul)" headers say
"P(2+ returns)", and This Week's chip says "10+ pts".

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — 🛑 the two protected files: job timeout and cancel

**Files:**
- Modify (**PROTECTED — authorized below only**) `src/gaffer/web/jobs.py`
- Modify (**PROTECTED — authorized below only**) `src/gaffer/web/routers/jobs.py`

---

### 🛑 STOP — the only protected edit in this cycle

**Do not begin Task 7 until the orchestrator has acknowledged the enumeration below in-branch.** Every other task in v9c is additive to unprotected files. This one is the cycle's single authorized breach, and spec D4 grants it — but the enumeration below is **wider than spec D4 describes**, by one line-group, and that difference needs saying out loud rather than discovering at review.

**What spec D4 authorized:** `JobRunner.start` plus "one small `_abandon_current` helper" in `jobs.py`, and one DELETE route in `routers/jobs.py`.

**What the tree actually requires: those, plus a guard inside `_execute`'s `finally`.** Read A14. `_execute`'s `finally` (L319-328) unconditionally writes the run's terminal status and then sets `self._current = None`. An abandoned job's thread is still alive — abandonment frees the lane, it does not kill work — so it reaches that block later and (1) overwrites the record saying why the lane was freed, and (2) clears `_current`, which by then may name a *newer* job. Without the guard, D4 replaces "one wedged job blocks everything until restart" with "one wedged job silently steals the lane from its own replacement", which is a worse bug in a quieter place.

**The four authorized line-groups, verified against the current tree:**

| # | File | Lines | Change |
| --- | --- | --- | --- |
| 1 | `src/gaffer/web/jobs.py` | after L256 (`kinds` property) | **new** `_abandon_current` helper, ~12 lines + docstring |
| 2 | `src/gaffer/web/jobs.py` | L261-264 (`start`'s locked block) | call the helper before the 409 check |
| 3 | `src/gaffer/web/jobs.py` | L319-328 (`_execute`'s `finally`) | guard the status write and the lane clear |
| 4 | `src/gaffer/web/routers/jobs.py` | between L54 and L57 | **new** `DELETE /api/jobs/current` route |

**Nothing else in either file may change.** No import beyond what is already there — `datetime`/`timezone` are imported at `jobs.py:23`, `Response` at `routers/jobs.py:19`. `ADVISE_TIMEOUT_S` (L30) is not moved or renamed; it simply acquires its first reader in five months.

**Every group carries a provenance comment naming this spec**, in the house form: `# v9c D4 (specs/2026-08-31-gaffer-v9c-model-debt-design.md): …`.

**Three design decisions inside the enumeration, each of which could have been a fifth edit and deliberately is not:**

- **The status is `"failed"`, not `"abandoned"`** (A12). `JobRun.status`'s vocabulary is pinned in the comment at L152, and `routers/jobs.py:131` terminates an SSE stream only on `("done", "failed")` — a new value would leave every watching browser polling for the full `IDLE_TIMEOUT_S = 3600`, and fixing *that* would be a fifth authorized line inside the file whose SSE behaviour the spec put out of scope.
- **The helper does not touch the worker thread.** `start` does not keep a handle on it (L268-269) and Python cannot safely kill one anyway — which is what the module docstring has said since v6 (L9-12). Abandonment frees the lane; the thread runs to completion and its result is discarded. Every job kind writes idempotently or writes nothing, which is the v8f constraint that makes the re-run safe.
- **One locked block per state change.** `_abandon_current` writes the status *and* clears the lane inside a single `with self._lock:`, for the reason `_execute`'s own comment gives at L320-323, and because `tests/test_web_job_runner.py:208-254` monkeypatches the lock with a watcher that snapshots state on **every** release and asserts the lane never points at a terminal run.

**The exact edits:**

*Group 1 — `jobs.py`, a new method after the `kinds` property (L256):*

```python
    def _abandon_current(self, older_than: float) -> JobRun | None:
        """Free the lane if the job holding it has been running too long.

        Called with the lock held. Returns the run it abandoned, or ``None``
        if the lane was empty or its holder is younger than ``older_than``.

        v9c D4 (specs/2026-08-31-gaffer-v9c-model-debt-design.md).
        ``ADVISE_TIMEOUT_S`` has had no reader since it was written: this
        runner, unlike the ``JobRegistry`` above it, never enforced a
        deadline, so a job that wedged held the single lane until the process
        restarted and every later job got a 409 naming a run nobody could
        clear.

        The worker thread is **not** killed. It is a daemon, Python has no
        safe way to stop one, and the module has said so since v6 (see the
        docstring at the top of this file). Abandonment frees the lane and
        discards the result; the thread runs on and its writes are harmless
        because every job kind writes its artifacts idempotently or writes
        nothing at all.

        The status is ``"failed"`` rather than a new ``"abandoned"`` value.
        ``JobRun.status``'s vocabulary is fixed, and more to the point the SSE
        generator in ``routers/jobs.py`` ends a stream only on ``done`` or
        ``failed`` — a new value would leave every watching browser polling
        for the full idle hour. The explanation goes in ``error``, where the
        UI already shows it.
        """
        if self._current is None:
            return None
        run = self._runs[self._current]
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(run.started_at)).total_seconds()
        if age < older_than:
            return None
        run.status = "failed"
        run.error = (f"timed out after {older_than:.0f}s — abandoned as a "
                     f"daemon, its thread still running")
        run.finished_at = _now()
        self._current = None
        return run
```

*Group 2 — `jobs.py`, inside `start`'s locked block (L261-264):*

```python
        with self._lock:
            # v9c D4: reap a wedged holder before refusing the new job. Until
            # v9c the 409 below was permanent — the lane was cleared only by
            # _execute's finally, so a job that never returned blocked every
            # later job until the process restarted.
            self._abandon_current(ADVISE_TIMEOUT_S)
            if self._current is not None:
                running = self._runs[self._current]
                raise JobAlreadyRunning(running.kind, running.id)
```

*Group 3 — `jobs.py`, inside `_execute`'s `finally` (L319-328):*

```python
            with self._lock:
                # One locked block for the whole ending. Flipping the status in
                # one and clearing the lane in a later one left a window where
                # a browser that had just been told `done` posted its next job
                # and was answered 409 by a runner with nothing running.
                #
                # v9c D4: both halves are now conditional, because this thread
                # may have been abandoned while it ran. Overwriting the status
                # would erase the record of why the lane was freed, and — far
                # worse — clearing _current unconditionally would clear a lane
                # that by now belongs to a *different*, newer job.
                if run.status == "running":
                    run.status = status
                    run.error = error
                    run.summary = summary
                    run.finished_at = _now()
                if self._current == run.id:
                    self._current = None
```

*Group 4 — `routers/jobs.py`, between L54 and L57:*

```python
@router.delete("/current")
def cancel_current(request: Request):
    """Free the lane held by the job running now. 404 when nothing holds it.

    v9c D4 (specs/2026-08-31-gaffer-v9c-model-debt-design.md). The runner
    takes one job at a time, so a job that wedges 409s every later job; until
    v9c the only way out was restarting the process, and the 409's own
    payload named a run the caller had no way to clear.

    This does **not** stop the work. The worker is a daemon thread and cannot
    be safely killed — the runner has said so since v6. What it does is
    release the lane and mark the run failed with a reason, so the next job
    can start. Every job kind is idempotent by design (a v8f constraint), so
    the re-run that follows is safe even while the abandoned thread is still
    writing.

    Declared before ``GET /{job_id}`` for the reason this module's docstring
    gives about ``GET /current``: the literal must be matched before the path
    parameter can swallow it.
    """
    run = request.app.state.job_runner.abandon_current()
    if run is None:
        raise HTTPException(status_code=404, detail="no job is running")
    return _view(run).model_dump()
```

This needs a public `abandon_current()` on `JobRunner` — a two-line wrapper that takes the lock and calls `_abandon_current(0.0)`, i.e. "however old it is". Fold it into Group 1 as part of the same helper block; it is the same authorization.

---

- [ ] **Wait for authorization.** Then make exactly the four edits above and nothing else.

- [ ] **Confirm the protected diff is exactly what was authorized, before writing any test:**

```bash
git diff --stat -- src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py
git diff -- src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py
# read it: four groups, four provenance comments, nothing else
```

- [ ] **Verify the pre-existing job suites are untouched by it.** All three are protected or pin behaviour this task is not allowed to move:

```bash
uv run pytest -q tests/test_web_jobs.py tests/test_web_job_runner.py \
  tests/test_web_jobs_api.py tests/test_v7_cold_clone.py
```

`tests/test_web_job_runner.py:229-254`'s `_WatchingLock` is the one to watch: it observes every lock release, including the new helper's. If it fails, Group 1 or Group 3 leaves the lane pointing at a terminal run — fix the code, never the rail.

- [ ] **Commit** with the authorization in the message body:

```bash
git add src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py \
  && git commit -m "$(cat <<'EOF'
feat: reap a wedged job and expose DELETE /api/jobs/current

ADVISE_TIMEOUT_S has had no reader since it was written: JobRunner never
enforced a deadline, so a job that wedged held the single lane and 409'd every
later job until the process restarted — and the 409 named a run the caller had
no way to clear. start() now reaps a holder older than the timeout before it
refuses, DELETE /api/jobs/current does the same on demand, and _execute's
finally became conditional so an abandoned thread cannot overwrite the record
or steal the lane back from its own replacement.

Abandonment frees the lane; it does not kill the thread, which is what this
module has said since v6. Status is "failed" with the reason in error, because
the SSE stream ends only on done|failed.

Deliberate orchestrator-authorized protected edit, four enumerated line groups
in two files, each carrying a provenance comment. Spec:
docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md D4.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the rails that pin timeout, cancel, and 409 recovery

**Files:**
- Create `tests/test_v9c_job_timeout.py`

New file, unprotected, so the behaviour Task 7 bought is pinned somewhere that a later cycle cannot quietly undo.

- [ ] **Write it.** `tests/test_v9c_job_timeout.py`, driving `JobRunner` directly for the unit cases and `TestClient` for the route, with a monkeypatched `ADVISE_TIMEOUT_S` so nothing sleeps:

1. **A fresh holder is not reaped.** A job started a second ago still 409s the next one. The timeout is a reaper, not a cancel-everything.
2. **A holder past the timeout is reaped and the next job starts.** Monkeypatch the timeout to 0.05, start a sleeper, wait, start a second job: it gets an id, not a `JobAlreadyRunning`.
3. **The reaped run says why.** `status == "failed"`, and `error` contains both "timed out" and "abandoned".
4. **The abandoned thread cannot steal the lane back.** The reaper's central hazard (A14): abandon a sleeper, start a second job, let the sleeper finish, then assert `runner.current().id` is still the second job's and that the first run's `error` still names the timeout.
5. **The abandoned thread cannot overwrite its own record.** Same setup; assert the first run's `status` is still `"failed"` and its `error` unchanged after the thread completes normally.
6. **`DELETE /api/jobs/current` frees the lane immediately**, regardless of age — a 200 carrying the abandoned run, then a `POST` that would have 409'd succeeds.
7. **`DELETE /api/jobs/current` on an idle runner is a 404**, not a 500 and not a 204. (204 is `GET`'s answer for "nothing running"; the DELETE distinguishes "I freed something" from "there was nothing to free", which is what a UI needs to decide whether to say anything.)
8. **A normal run is unaffected end to end** — start, watch it finish, `status == "done"`, lane free, `error is None`. The rail against a reaper that reaps the living.
9. **The 409 payload still names the holder** — `{"running_kind": ..., "job_id": ...}`, unchanged shape, because `frontend/src/api/useJob.ts` reads it.
10. **The SSE stream still ends on an abandoned run.** Abandon a watched job and assert the generator emits its `end` event rather than polling to the idle hour — the concrete reason A12 chose `"failed"`.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_v9c_job_timeout.py tests/test_web_job_runner.py \
  tests/test_web_jobs_api.py tests/test_web_jobs.py
uv run pytest -q
```

- [ ] **Commit** (`test: v9c rails for job timeout, cancel and 409 recovery`).

---

## Task 9 — the degradation rails (gate G2)

**Files:**
- Create `tests/test_v9c_degradation.py`

Every rail is a state a real machine reaches: a season with no archived fixture list, a corrupt one, an advice file banked before this cycle, a wedged job. The pins at the end are the counts that did **not** move.

- [ ] **Write it.** `tests/test_v9c_degradation.py`, in five blocks:

**Block 1 — the card term (whichever branch Task 2 took).**
- *ship branch:* `rc_r38` is built by `add_player_rolling`, is not all-NaN on a frame with a red card in it, and `card_penalty` separates a sent-off row from a clean one.
- *withdraw branch:* `"rc" not in ROLL_STATS`, `card_penalty` returns the same number for both rows, and `card_penalty.__doc__` names the arm — the pin that stops a later cycle restoring the read without redoing the measurement.

Whichever it is, one rail is common to both: **a frame with no card columns at all still produces a finite `e_cards`**, because `_rate`'s NaN guard is doing its real job again.

**Block 2 — the as-of club.**
- A season with no fixture rows: every row falls back to `team_code`, the column is fully populated, and **nothing is NaN**. (The named G2 clause: a NaN club scatters every downstream `groupby` into a silent extra bucket.)
- A corrupt fixture list — duplicate `(season_idx, gw, kickoff_time, team)` keys claiming different fixtures — drops to the fallback rather than mis-keying, inheriting `fixture_key`'s poisoning.
- A fixture list that is not a parquet at all, and one missing `home_code`: `load_training_frame` still returns a frame, and `club_code` is `team_code` throughout.
- The prediction frame's future rows: `team_elo` is populated on every one of them. This is the rail that catches A6's coalesce being rewritten as a column-presence check, and it is the most valuable single assertion in this file.
- `"club_code" not in feature_columns()`, so `advise.py`'s strip leaves it on — A10, pinned without touching a protected file.

**Block 3 — the boundary rename, both directions.**
- The alternatives and captain rows arrive as `p_attacking_haul` and carry no `p_haul`.
- `/api/players` and `/api/components` rows arrive as `p_haul` and carry no `p_attacking_haul`. Both directions, because renaming both would leave the page exactly as ambiguous in a new vocabulary.
- An advice artifact written before this cycle (no `p_attacking_haul` anywhere in its bytes) serves renamed, and the file on disk is byte-identical afterwards.
- A payload with no `alternatives` key at all is a 200.

**Block 4 — the freed lane.**
- A wedged job past the timeout frees the lane on the next `start`, and the run record says why.
- `DELETE /api/jobs/current` on an idle runner is a 404, and on a busy one frees it.
- A normal run still reaches `done` with `error is None`.

**Block 5 — pins for what did not move** (A13). Each asserts this cycle's own file rather than reaching into an older one, so a future cycle's accidental addition fails here rather than in eight places:

```python
def test_the_job_kinds_are_still_twelve():
    """Spec §2: no new job kinds. A cancel is a DELETE on a lane, not a
    thirteenth thing to run."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    """Spec §2: no new config keys. ADVISE_TIMEOUT_S is a module constant
    that finally acquired a reader, not a knob."""
    import dataclasses

    from gaffer.config import Config

    assert len(dataclasses.fields(Config)) == 48


def test_the_jobs_routes_are_the_four_plus_the_new_delete():
    """The DELETE shares a path with the GET, so the OpenAPI path set does
    not move — which is why no pre-existing route pin needed updating this
    cycle (plan A13). Pinned here so the *methods* are named somewhere."""
    schema = client.app.openapi()["paths"]
    assert set(schema["/api/jobs/current"]) == {"get", "delete"}
```

- [ ] **Verify — the new rails and every pre-existing rail file together.**

```bash
uv run pytest -q tests/test_v9c_degradation.py
uv run pytest -q tests/ -k degradation
git diff main --stat -- 'tests/test_*_degradation.py'
# must name tests/test_v9c_degradation.py and nothing else
```

Every pre-existing `test_*_degradation.py` is protected and must pass **unmodified**. If one fails, this cycle broke something it promised not to: stop and report rather than editing the rail.

- [ ] **Commit** (`test: v9c degradation rails`).

---

## Task 10 — the replay re-bank, branch against a re-run main

**Files:**
- Create `scripts/v9c_replay.sh`
- Modify `README.md`

**Read A15.** This is the cycle's most expensive measurement and the one most easily got wrong, because the obvious shortcut — compare against the banked number — is exactly the mistake v8a's G5 made and paid for.

**The methodology, stated once:**

1. **The comparison is branch against a *re-run* `main`, never against a banked figure.** The v8a lesson, spec §9 G5: the banked 1876 predated the Z1 flip, and reading the branch's 1844 against it looked like a 32-point divergence and cost an investigation that ended by proving the training frame byte-identical. `data/` is untracked and shared between worktrees, so a `main` worktree beside this one reads exactly the same inputs — the *only* thing that differs is the code.

2. **Both sides run the seed trio.** Unlike v9a's, this cycle's replay is a **delta** and not an equality: D1 (if it shipped) moves `card_penalty` and D2 moves three feature families, so branch ≠ main is the *expected* result. A gap reading is governed by CONVENTIONS §1 — `K >= 3` seed bases, verdicts as mean ± spread. v7b measured a 116-point seed spread on this arm, larger than any gap v9c could plausibly produce, so a single draw would measure the seed and nothing else.

3. **The config echo must differ in nothing but `seed_base` and `--tag`.** `scripts/seed_stats.py` enforces this and exits 2 otherwise; mixing a control arm into a seed trio reads an arm gap as a seed spread.

- [ ] **Write the driver.** `scripts/v9c_replay.sh` — one file so the two invocations cannot drift apart by hand:

```bash
#!/usr/bin/env bash
# v9c G3: the replay delta, branch against a re-run main.
#
# Not an equality check. D1 and D2 change EP deliberately, so a gap is the
# expected result and CONVENTIONS §1 applies: three seed bases a side, read as
# mean +/- spread. The banked number from an earlier cycle is not a valid
# comparison and never was (v8a spec §9, G5).
#
# Run from the branch worktree. Creates a main worktree beside it if absent.
#
#   caffeinate -i nohup bash scripts/v9c_replay.sh > logs/v9c_replay.log 2>&1 &
#   grep -e V7B_ARM_DONE -e MULTISEED_DONE logs/v9c_replay.log
set -euo pipefail

SEEDS="1876,1901,20260827"
MAIN_WT="${MAIN_WT:-../gaffer-main-v9c}"

[ -d "$MAIN_WT" ] || git worktree add "$MAIN_WT" main

mkdir -p logs
# Byte-identical flags on both sides. Only --tag differs, which is what
# scripts/seed_stats.py checks before it will aggregate.
.venv/bin/python scripts/v7b_replay.py --arm heur --tag v9c-branch \
    --seed-bases "$SEEDS" --n 40 --chips

( cd "$MAIN_WT" && "$OLDPWD/.venv/bin/python" scripts/v7b_replay.py \
    --arm heur --tag v9c-main --seed-bases "$SEEDS" --n 40 --chips )

.venv/bin/python scripts/seed_stats.py reports/v7b_v9c-branch.json
.venv/bin/python scripts/seed_stats.py reports/v7b_v9c-main.json
```

### 🛑 STOP — the orchestrator runs this

Expect **2.5-3 hours** (six replays at ~23 minutes each, sequential). Running the two worktrees concurrently roughly halves the wall clock and does not change any number — the runs share no state and `data/` is read-only to both — but they contend for the same cores, so the saving is less than half.

- [ ] **Document what shipped.** In `README.md`:
  - the `club_code` column beside the other store columns: what it is, that it is derived at training time from the fixture list, that it falls back to the stamped `team_code` for rows and seasons with no fixture, and that `team_code` remains the serve-time identity the pitch and the bootstrap joins use;
  - one sentence on the two haul quantities and their served names, so a reader of the API does not have to find it in a router docstring;
  - the cancel endpoint in the jobs section: what `DELETE /api/jobs/current` does, and — the part that matters — what it does *not* do, which is stop the work.

- [ ] **Commit** (`docs: v9c — the as-of club column, the haul split, and the cancel endpoint`), staging only `scripts/v9c_replay.sh` and `README.md`.

---

## Task 11 — final verification and the gate checklist (orchestrator-run, unfilled)

**Files:**
- Modify `docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md` (§5)

CONVENTIONS §7: the implementer builds this and does not run it. Fill in the **measured** G3 numbers from your own final run; leave every G1 box unchecked.

- [ ] **G3 — suites, types, build, and the audits.**

```bash
uv run pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Baselines to beat: merged `main`'s counts (re-measured into this plan's header before Task 1) plus this cycle's new tests, all green.

Then the protected diff, which must show **exactly** Task 7's four line-groups and their provenance comments and nothing else:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
# must be empty

git diff main -- src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py
# must be exactly the four authorized groups (Task 7's STOP table)

git diff main --stat -- 'tests/test_*_degradation.py'
# must name tests/test_v9c_degradation.py and nothing else
```

And the pin audit, which is a zero this cycle (A13):

```bash
git diff main -- tests/test_web_job_kinds.py tests/test_web_job_kinds_v8b.py \
  tests/test_web_job_kinds_v8c.py tests/test_web_job_kinds_v8f.py \
  src/gaffer/config.py config.example.toml frontend/src/types.ts
# must be empty
```

Security ritual (CONVENTIONS §8): grep the whole branch diff for keys and tokens, confirm no `data/`, `reports/`, `models/`, `logs/` or `config.toml` path appears in `git diff main --stat`, and confirm `git show main:config.toml` fails.

**No commit at this step.** The numbers go into the checklist below.

- [ ] **Write §5 into the spec file.** Replace the spec's §5 placeholder with the checklist below, G3 filled from the run above and every G1 box unchecked.

```markdown
## 5. Gate checklist (built by the implementer, run by the orchestrator)

**G3 — suites, types, build, audit (measured by the implementer):**

- [x] `uv run pytest -q` — <N> passed (merged-main baseline <B> + <new> new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — <N> passed, 1 skipped (baseline <B> + <new> new)
- [x] `npm run build` — clean
- [x] Protected diff EMPTY except D4's four authorized line groups in
      `web/jobs.py` and `routers/jobs.py`, each provenance-commented:
      `_abandon_current`/`abandon_current`, `start`'s reap, `_execute`'s
      conditional finally, `DELETE /api/jobs/current`
- [x] Pin diff EMPTY: job kinds still 12, config fields still 48,
      `config.example.toml` and `frontend/src/types.ts` job lists untouched;
      no pre-existing degradation rail modified
- [x] `tests/test_bps.py`, `tests/test_advise.py`, `tests/test_differentials.py`,
      `tests/test_assemble.py` pass unmodified — the four rails that say the
      bps extraction, the serving path, and the boundary-only rename each
      stayed inside their lines
- [x] Security ritual clean; no data/, reports/, models/, logs/ or config.toml
      in the branch diff

**G1 — live, real season (orchestrator only):**

*D1 — the red-card arm*
- [ ] `scripts/v9c_rc_arm.py` run; `V9C_ARM_DONE` lines for both arms and the
      `V9C_VERDICT` line transcribed verbatim into §4.
- [ ] The pre-registered non-regression rule (tolerance 0.005) applied as
      written, and the branch taken — shipped, or withdrawn with the term
      explicitly zeroed and the numbers in `card_penalty`'s docstring.

*D2 — the as-of club*
- [ ] `V9C_CLUB_COVERAGE`: total rows, matched rows, and diverging rows with
      the per-season breakdown, transcribed into §4. The divergence fraction
      is the leak, measured.
- [ ] `V9C_CLUB_DEMO`: one real transferred player, chosen by the driver and
      not by hand — his pre-transfer rows show the old club in `club_code`
      while `team_code` shows the new one.
- [ ] `V9C_CLUB_DONE`: before/after stratum tables and the deltas, recorded
      **including a regression** (spec D2: the fix ships either way, because
      the old number was flattered by leakage).

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

*G3's replay evidence (orchestrator)*
- [ ] `bash scripts/v9c_replay.sh`: three seed bases a side, branch and a
      **re-run** `main` worktree, config echoes identical but for `seed_base`
      and `--tag`, aggregates read through `scripts/seed_stats.py`. Mean ±
      spread both sides, and the delta read against the spread — never
      against a banked figure (v8a §9 G5).

**G2 — rails:** `uv run pytest -q tests/test_v9c_degradation.py`, plus every
pre-existing `test_*_degradation.py` unmodified.
```

- [ ] **Fill spec §4 (Outcome)** with what shipped, what was withdrawn, and the residuals — and, per CONVENTIONS §4, transcribe the G1 evidence **verbatim** rather than summarising it. (Orchestrator, after G1.)

- [ ] **Commit the checklist.**

```bash
git add docs/superpowers/specs/2026-08-31-gaffer-v9c-model-debt-design.md \
  && git commit -m "$(cat <<'EOF'
docs: v9c gate checklist with the measured G3 numbers, G1 unfilled

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Wall-clock estimates for the measured tasks

Read off this machine's own logs (`logs/v8a_arms.log`, `logs/v8a_g5*.log`, `logs/v7b_*.log` file birth → mtime), not off prose, because the prose in `docs/` spans two years of a moving codebase and reads high.

| Task | Run | Estimate | Basis |
| --- | --- | --- | --- |
| **T2** | D1 arm: 2 × `evaluate_benchmark` + 2 × un-memoised `load_training_frame` | **10-15 min** | v8a's 7 arms took 9m11s on **one** memoised frame (~80 s/arm); this cycle pays for a frame twice, and a frame build is the expensive half |
| **T5** | D2 eval: same shape, plus the coverage pass over the full frame | **10-15 min** | as above; the coverage pass is one `groupby` over an already-built frame |
| — | full retrain (`gaffer train`) | **3-10 min, unmeasured** | **no wall-clock for a bare retrain is recorded anywhere in this repo.** Bounded above by the 30-minute advise+train job timeout and below by `evaluate_current`'s ~2.5 min, which refits. Worth recording the first time it runs. |
| **T10** | replay, one seed base, one side | **~23 min** | `logs/v8a_g5.log` 00:24:25 → 00:47:21; the other banked replays span 15.5-23 min |
| **T10** | the full trio pair (3 seeds × 2 sides) | **2.5-3 h sequential** | 6 × the above; concurrent worktrees cut it toward ~1.5 h with core contention |
| | **total unattended compute** | **≈ 3.5-4 h** | all three under `caffeinate -i nohup`; none of it blocks the implementer, and none of it is run by the implementer |

A note on the retrain, because it is the one number nobody has: **A2 argues D1 needs no retrain at all** — no model's feature list gains an `rc_*` column, so the fitted weights cannot move — and Task 1's `test_no_model_feature_list_gains_a_card_column` is what turns that argument into something the suite checks. D2 is the opposite: `shrunk_goals90`/`shrunk_assists90` are in `ATTACK_FEATURES` and `team_elo`/`elo_diff` are in four lists, so D2 genuinely refits.

---

## Notes for the implementer

- **Task order is mostly forced.** T1 → T2 (the arm needs the change to remove). T3 → T4 (the wiring needs the derivation) → T5 (the measurement needs the wiring). T7 → T8 (the rails need the behaviour). T9 needs T2's branch decided, because Block 1 differs between them. T6 is independent of everything and can be done at any point. T10 and T11 need all of it.
- **Three of this plan's decisions correct the spec, and each is flagged where it bites.** D3's schema map is wrong (A1) — there is no alternatives model, only an untyped passthrough. D1 does not touch a single model's inputs (A2), which is why its arm is cheap. D4 needs a fourth authorized edit the spec did not enumerate (A14), and Task 7's STOP says so rather than folding it into "one small helper".
- **The mutable-default trap in A3 is the one that would waste a day.** `ROLL_STATS` is bound as a default argument on four functions. Rebinding the module global changes nothing, both arms build the same frame, and the driver reports a gap of exactly zero — which reads exactly like a clean negative result. The driver refuses to report unless the frames actually differ; do not remove that guard to make a run go through.
- **`club_code`'s fallback is per row and the rail that catches a regression is in T9 Block 2** — `team_elo` populated on every future row of a prediction frame. If someone later "simplifies" `as_of_club` to a column-presence check, that assertion is what fails, and it is worth reading the failure rather than adjusting it.
- **Abandonment does not stop work.** Say it in the UI if a cancel button ever ships (it does not this cycle): the lane is freed, the thread runs on, and the re-run is safe only because every job kind writes idempotently. That last clause is a v8f constraint being cashed in, and a future job kind that breaks it breaks this too.
- **Never stage `reports/` or `logs/`.** The arm, the eval and the replay all write there, and the numbers reach the repo only by being transcribed into the spec (CONVENTIONS §4). A banked JSON in a commit is a number nobody can re-read in six months.
