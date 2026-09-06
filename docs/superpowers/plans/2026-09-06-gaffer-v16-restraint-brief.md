# gaffer v16 — restraint and the brief — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The transfer ladder's shared-draw probabilities choose how many changes the advice commits to; the user records why they deviated; a grounded LLM brief replaces the template digest.

**Architecture:** The restraint walk lives in the unprotected `ladder.py` and runs inside `build_ladder`, where the shared draw matrices exist; `advise.py` (protected, one orchestrator diff) saves the solve state first, builds the ladder, and serves the chosen rung's plan through a pure `serve_rung` helper, keeping the objective's own week-one plan beside it. A small `decisions.py` store and router carry the deviation note; `brief.py` writes a facts document, calls the classifier's no-tools `claude -p` command, checks every number and name mechanically, and banks the prose; the web advise job chains the brief; the front end reads all of it through the generated types.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI + pydantic, numpy/pandas, PuLP MILP; React 18 + TypeScript + Tailwind v4 + vitest; `scripts/gen_types.py` + `json-schema-to-typescript` for the wire types.

**Spec:** `docs/superpowers/specs/2026-09-06-gaffer-v16-restraint-brief-design.md`.

---

## Rulings (read before any task)

Each is a decision the plan makes where the spec was silent or its premise did not hold in the tree. The orchestrator owns them; an implementer follows them and does not re-open them.

- **R1 — no thirteenth job kind.** `len(JOB_KINDS) == 12` is pinned absolutely in **sixteen** protected degradation files (`test_v8b/c/d/e/f/g`, `v9a/c/d`, `v10`, `v10b`, `v11`, `v12_w1/w3/w4/w5`, `v13`), not "one number in one file" as the spec assumed. The brief therefore runs the way the ladder rebuild does: `POST /api/brief` submits an anonymous `JobRegistry` job (`routers/ladder.py`'s own docstring records exactly this reason), and the chain after the web advise job is a call at the end of `routers/advice.run_train_and_advise` — the job *body*, never `run_advise`. `JOB_KINDS` stays at twelve; the frontend `JOB_KINDS` table is untouched; the brief button is a `useJob('brief')` + `Button`, LadderCard's Rebuild pattern. The user is told in the plan hand-off.
- **R2 — step keys are `below` / `above`**, not `from` / `to`: `from` is a Python keyword and the pydantic model would need an alias the generator would have to special-case.
- **R3 — the walk runs inside `build_ladder`** (it needs the in-memory draw matrices), reads `hit_bar` through `serving_config()` exactly as `_caps` reads the caps, and the reasons read: `p_play` off the banked components frame, price falls through `gaffer.price_timing.owned_price_falls`, fixture difficulty through `gaffer.web.identity._difficulty_by_team` (the ticker's own rating, 0 easiest … 1 hardest), and the chip plan off `state.opt["chip_plan"]`, which `advise.py` writes from the chip table's `play_now` rows. Every one of those reads is wrapped; a missing source is an empty map and the reason falls through the precedence.
- **R4 — `recommended` matches on moves, not on the captain**, because the sweep's captain may stand on the served rung. It is computed at build time as before *and* recomputed by `GET /api/ladder` from the advice on disk, because the advise-time build now runs before the advice is written. The router also adds `served_note` ("the served advice was the … rung at bar 0.60; this rebuild at 0.70 chooses bank").
- **R5 — advise order:** components and solve state are saved, then `build_ladder(gw)` (the literal call `build_ladder(gw)` is a protected pin and stays), then the payload is assembled from `serve_rung(...)`, then the advice file, availability and history are written. `SolveState.mode` takes the expression the `Advice` used to carry.
- **R6 — `tests/test_advise.py` has no end-to-end harness** (every run_advise test there is source-level). The served-plan assembly is the pure function `serve_rung` in `ladder.py`, tested directly; `tests/test_v16_restraint.py` pins the `advise.py` diff at source level, the way every v13/v15 pin does.
- **R7 — "one grade easier":** the ticker's difficulty is 0..1; one grade is **0.2** (a fifth, the familiar 1–5 scale). The reason sentence prints `difficulty × 5` to one decimal ("Gibbs-White's next 3 average 2.3 against Fernandes's 3.7").
- **R8 — truth check names:** a capitalised token is checked only when it is not the first token of its sentence (English capitalises sentence starts), after stripping punctuation and a possessive; tokens in a fixed allow-list (`GW`, `FPL`, `XI`, `I`, `British`, day and month names, `Premier`, `League`, `Bank`, `Free`, `Hit`) and `GW\d+` are exempt. The prompt forbids starting a sentence with a player's name and naming a club, so a club name mid-sentence bans the brief — that is the design.
- **R9 — `gaffer brief` CLI command** is added: the same body as the job (the tree's job-kinds convention), so R2's real run and a hand run are one command, and a launchd plist can chain it after `gaffer advise` later.
- **R10 — replay arms:** `--arm restraint` (raw solve + rung specs + shared draws + walk) against `--arm raw` (deterministic, one run). Neither carries the sweep gate; the sweep only changes the captain once restraint serves the rung, so raw-vs-restraint isolates the policy. The heur arm's numbers (`reports/v7b_v12w4-main-s2026090[1-3].json`, total 1798 / hits 15 at 20260901) are quoted for context only.
- **R11 — decision note states:** `before_deadline` (the advised gameweek's deadline is in the future), `open`, `graded` (the ledger has the row). `POST` refuses `before_deadline` (`not_open`) and `graded` (`graded`) as well as the spec's three refusals.
- **R12 — cap-blocked steps** are recorded as refused with `reason_kind: "cap"` ("above your cap of 2 hits") rather than silently ending the walk, so the ladder file explains every stop.
- **R13 — facts rounding:** points 1 dp, shares whole percent (`share_pct: 46`), λ 2 dp, gains 1 dp; the prose is checked against those rendered strings.

## File map

| Path | Change |
|---|---|
| `src/gaffer/config.py` | `hit_bar` field, `HIT_BAR_LO/HI`, `_check_hit_bar` |
| `src/gaffer/web/settings_keys.py` | "Hit bar" row |
| `src/gaffer/ladder.py` | `walk`, `StepContext`, `step_context`, `explain_step`, `rung_label`, `serve_rung`, `recommended_rung`, `served_note`, `restraint_line`, `objective_line`; `build_ladder` gains `bar/chosen/steps` |
| `src/gaffer/web/schemas.py` | `LadderStep`, LadderPayload fields; `PlanTimeline.objective`; `DecisionGrade/DecisionNote/DecisionWrite`; `ReviewGw.decision`, `ReasonTally`, `ReviewSummary.by_reason`; `BriefPanel` |
| `src/gaffer/web/routers/ladder.py` | recompute `recommended`, add `served_note` |
| `src/gaffer/advise.py` (**protected, orchestrator**) | `Advice.objective/restraint`; the §4 block |
| `src/gaffer/cli.py` | restraint + objective lines; `brief` command |
| `src/gaffer/web/routers/plan.py` | `objective` week with its trace |
| `src/gaffer/decisions.py` (new) | store, refusals, state, by-reason tally |
| `src/gaffer/web/routers/decisions.py` (new) | `GET/POST /api/decisions/{gw}` |
| `src/gaffer/web/routers/review.py` | join notes, `by_reason` |
| `src/gaffer/brief.py` (new) | facts, prompt, command, truth check, bank |
| `src/gaffer/web/routers/brief.py` (new) | `GET /api/brief`, `POST /api/brief` |
| `src/gaffer/web/routers/advice.py` | chain `run_brief` after a successful web advise |
| `src/gaffer/digest.py` | Friday headline = brief's first sentence |
| `src/gaffer/web/app.py` | include the two routers |
| `scripts/v7b_replay.py` | `--arm restraint`, `--hit-bar`, `--ladder-draws`, `make_restraint_gate` |
| `frontend/src/types.ts` | `RestraintStep`, `Restraint`, `Objective` on `Advice` |
| `frontend/src/hubs/this-week/LadderCard.tsx` | bar select, chosen chip, steps list, served note |
| `frontend/src/hubs/this-week/MovesCard.tsx` | restraint + objective lines |
| `frontend/src/hubs/this-week/DecisionPanel.tsx` (new) | "What I did and why" |
| `frontend/src/hubs/this-week/BriefCard.tsx` (new), `DigestCard.tsx` | the brief, the digest as fallback |
| `frontend/src/hubs/ThisWeek.tsx` | wire the three |
| `frontend/src/hubs/planning/PlannerBoard.tsx` | "The objective wanted" block |
| `frontend/src/hubs/model/ReviewTab.tsx` | note under the transfers lane, by-reason table |
| Tests | `tests/test_v16_config.py`, `test_v16_ladder.py`, `test_v16_restraint.py`, `test_v16_plan_objective.py`, `test_v16_decisions.py`, `test_v16_review_notes.py`, `test_v16_brief.py`, `test_v16_web_brief.py`; frontend `*.test.tsx` beside each component; `tests/test_v7b_driver.py` extended |
| Pins (**orchestrator**) | `tests/test_v13_degradation.py` Config 58→59; `tests/test_v11_degradation.py` routes 49→50 (Task 5) →51 (Task 7) |

## Conventions every task follows

- Branch `v16-restraint`, created from `main` before Task 1: `git checkout -b v16-restraint`.
- Python: `.venv/bin/pytest -q tests/<file>` per task; the whole suite (`.venv/bin/pytest -q`, ~4 min) at the end of Tasks 3, 7 and 11. Frontend: `cd frontend && npx tsc --noEmit && npx vitest run` — an `Errors N error` line is a failure.
- Stage explicit paths only. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `.superpowers/`, `config.toml`, `config.local.toml`, `src/gaffer/web/static/`. **Never open `config.toml`.**
- Every commit message ends with the two trailer lines:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke
  ```
- Protected files an implementer must not touch: `src/gaffer/advise.py`, `set_pieces.py`, `optimize/**`, `web/jobs.py`, `web/routers/whatif.py`, `tests/test_advise.py`, `test_odds.py`, `test_web_jobs.py`, every pre-existing `tests/test_v*_degradation.py`, `scripts/s2_replay.py`. If a task seems to need one, stop and report `BLOCKED`.
- **Type regeneration** after any `schemas.py` change (Tasks 2, 4, 5, 6, 7), run from the repo root and commit all three outputs:
  ```bash
  .venv/bin/python scripts/gen_types.py
  cd frontend && node --input-type=module -e "
  import { readFileSync, writeFileSync } from 'node:fs'
  import { compile } from 'json-schema-to-typescript'
  const OPTIONS = { bannerComment: '', additionalProperties: false,
    unreachableDefinitions: true, declareExternallyReferenced: true,
    style: { singleQuote: true, semi: false } }
  const banner = readFileSync('src/types.banner.txt', 'utf8')
  const schema = JSON.parse(readFileSync('src/schemas.json', 'utf8'))
  compile(schema, 'GafferApi', OPTIONS).then((ts) => writeFileSync('src/types.generated.ts', banner + ts))
  " && npx vitest run src/types.generated.test.ts && cd .. \
    && .venv/bin/pytest -q tests/test_v12_w5_gen_types.py
  ```
  Files to stage: `frontend/src/schemas.json`, `frontend/src/types.generated.ts`.
- Design rules the frontend tests pin (`kit/tokens.test.ts`): no `rounded-full`, `shadow-`, `gradient`, raw hex, `font-mono` (outside JobLog/PlannerBoard), no `<Badge`, no `num` class, no `sage/rust/info/card` colours. Compose from the kit: `Button`, `Segmented`, `Chip`, `Bar`, `Callout`, `Card`, `Stat`, `StatRow`, `EmptyState`, `INPUT_CLASS`, `TABLE_CLASS/THEAD_CLASS/TR_CLASS/tdClass/thClass`, `fmtNum/fmtPct/fmtDelta`, `toast`, `errorText`.

---

### Task 1: `hit_bar` in Config and the Settings whitelist

**Files:**
- Modify: `src/gaffer/config.py` (the `Config` dataclass after `max_transfers`, the checks after `_check_stance`, the call in `load_config`)
- Modify: `src/gaffer/web/settings_keys.py` (one row after `max_transfers`)
- Test: `tests/test_v16_config.py` (new)
- **Orchestrator only:** `tests/test_v13_degradation.py` line 29 `58` → `59` plus a docstring line.

- [ ] **Step 1: Write the failing tests**

```python
"""v16 §3.2 — the hit bar: a Config field, bounded, and a Settings row."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from gaffer.config import (HIT_BAR_HI, HIT_BAR_LO, LOCAL_OVERLAY, Config,
                           load_config, optimizer_top_n, serving_config)
from gaffer.errors import GafferError

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


def _load(tmp_path, monkeypatch, base: str = BASE, local: str | None = None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(base)
    if local is not None:
        (tmp_path / LOCAL_OVERLAY).write_text(local)
    return load_config()


def test_hit_bar_is_a_field_defaulting_to_sixty_percent():
    assert "hit_bar" in {f.name for f in dataclasses.fields(Config)}
    assert Config(entry_id=1, league_id=5).hit_bar == 0.60


def test_the_bounds_are_a_coin_toss_and_never():
    assert (HIT_BAR_LO, HIT_BAR_HI) == (0.5, 0.95)


def test_hit_bar_is_read_from_the_optimizer_table(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, base=BASE + "[optimizer]\nhit_bar = 0.7\n")
    assert cfg.hit_bar == 0.7


def test_the_overlay_wins(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, base=BASE + "[optimizer]\nhit_bar = 0.7\n",
                local="[optimizer]\nhit_bar = 0.55\n")
    assert cfg.hit_bar == 0.55


@pytest.mark.parametrize("line", ["hit_bar = 0.4", "hit_bar = 0.96",
                                  "hit_bar = true", 'hit_bar = "high"'])
def test_a_bar_outside_the_bounds_is_refused_by_name(tmp_path, monkeypatch, line):
    with pytest.raises(GafferError, match=r"\[optimizer\] hit_bar"):
        _load(tmp_path, monkeypatch, base=BASE + f"[optimizer]\n{line}\n")


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(BASE)
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()


def test_the_settings_panel_serves_the_bar_with_its_range(settings_client):
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    row = rows["hit_bar"]
    assert row["value"] == 0.60 and row["kind"] == "float"
    assert (row["lo"], row["hi"]) == (0.5, 0.95)
    assert row["section"] == "optimizer" and row["source"] == "default"


def test_a_saved_bar_reaches_load_config(settings_client, tmp_path):
    resp = settings_client.post("/api/settings", json={"key": "hit_bar", "value": 0.7})
    assert resp.status_code == 200, resp.text
    assert load_config(tmp_path / "config.toml").hit_bar == 0.7


def test_a_bar_above_the_ceiling_is_refused_at_the_endpoint(settings_client):
    resp = settings_client.post("/api/settings", json={"key": "hit_bar", "value": 0.99})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "out_of_range"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_v16_config.py`
Expected: ImportError on `HIT_BAR_HI` (collection fails).

- [ ] **Step 3: Add the field, the bounds and the check**

In `src/gaffer/config.py`, directly after `NO_CAP`'s docstring add:

```python
HIT_BAR_LO, HIT_BAR_HI = 0.5, 0.95
"""``[optimizer] hit_bar`` bounds (v16 §3.2). Below 0.5 a step up the ladder
would be taken on a coin toss; above 0.95 no step ever passes."""
```

In the `Config` dataclass, directly after `max_transfers: int = NO_CAP`:

```python
    # v16 §3.2 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md). The
    # share of the ladder's shared draws in which a rung must beat the rung
    # below it before the served advice steps up to it. A policy knob, not a
    # model parameter: the ladder's probabilities decide, this says how sure
    # they have to be.
    hit_bar: float = 0.60
```

After `_check_stance` add:

```python
def _check_hit_bar(cfg: "Config") -> None:
    """v16 §3.2: a real number inside ``[HIT_BAR_LO, HIT_BAR_HI]``, refused
    by name, like the caps."""
    value = cfg.hit_bar
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not HIT_BAR_LO <= float(value) <= HIT_BAR_HI):
        raise GafferError(
            f"[optimizer] hit_bar = {value!r} — must be a number between "
            f"{HIT_BAR_LO} and {HIT_BAR_HI}")
```

In `load_config`, after `_check_stance(cfg)` add `_check_hit_bar(cfg)`.

In `src/gaffer/web/settings_keys.py`, after the `max_transfers` entry add:

```python
    # v16 §3.2 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md). How
    # sure the ladder has to be before the advice steps up a rung. Also edited
    # from the ladder card, which writes through this same endpoint.
    SettingKey("hit_bar", "optimizer", "hit_bar", "Hit bar",
               "float", 0.5, 0.95,
               "The share of the ladder's draws a rung must win against the "
               "rung below before the advice steps up to it. 0.60 is three "
               "draws in five. The transfer ladder on the This Week hub "
               "edits it too."),
```

- [ ] **Step 4: Run the new tests and the config/settings suites**

Run: `.venv/bin/pytest -q tests/test_v16_config.py tests/test_config.py tests/test_v15_config.py tests/test_v12_w5_settings.py tests/test_v15_settings.py tests/test_v12_w5_degradation.py`
Expected: all pass except `tests/test_v13_degradation.py` is not in this list — it will fail on the count until the orchestrator moves the pin. Report DONE with that note.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/config.py src/gaffer/web/settings_keys.py tests/test_v16_config.py
git commit -m "feat(v16): [optimizer] hit_bar — the ladder's bar, bounded 0.5–0.95, a Settings row"
```

**Orchestrator, after the review:** edit `tests/test_v13_degradation.py` — `assert len(names) == 58` → `59`, add `assert "hit_bar" in names`, and a docstring line `59 after v16 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md §3.2): the one new name is hit_bar.`; run `.venv/bin/pytest -q tests/test_v13_degradation.py tests/test_v12_w1_degradation.py`; commit `test(v16): Config field pin 58 → 59 (hit_bar)`.

---

### Task 2: The restraint walk, its reasons and the served rung (`ladder.py`)

**Files:**
- Modify: `src/gaffer/ladder.py`
- Modify: `src/gaffer/web/schemas.py` (`LadderStep`; `LadderPayload` gains `bar`, `chosen`, `steps`, `served_note`)
- Modify: `src/gaffer/web/routers/ladder.py` (`GET` recomputes `recommended`, adds `served_note`)
- Test: `tests/test_v16_ladder.py` (new)
- Regenerate types (Conventions).

**Context.** `build_ladder` today solves the rung specs, collapses duplicates, draws one shared matrix, scores every distinct rung into `scores: dict[str, np.ndarray]`, builds `rows` (one dict per rung in `RUNG_ORDER`, `same_as` rows carry no numbers, each distinct row's `vs_below` is the diff against the previous *distinct* rung), then resolves the caps and the recommended rung and banks the payload. Every row's `plan_by_gw[0]` carries named `buys/sells/xi/bench/captain/vice` refs of the shape `{code, name, position, ep}` — the same shape `advise._named` produces, which is what lets `serve_rung` hand them straight to the payload.

- [ ] **Step 1: Write the failing tests**

```python
"""v16 §3 — the restraint walk on the ladder, its reasons, the served rung."""
from __future__ import annotations

import json

import numpy as np
import pytest

from gaffer import ladder as lad
from gaffer.ladder import (StepContext, explain_step, objective_line,
                           recommended_rung, restraint_line, rung_label,
                           serve_rung, served_note, walk)


def _row(key, hits=0, transfers=0, same_as=None, buys=(), sells=(), xi=(),
         captain=None, vice=None, gw=4):
    ref = lambda c: {"code": c, "name": f"P{c}", "position": "MID", "ep": 5.0}  # noqa: E731
    first = {"gw": gw, "hits": hits, "buys": [ref(c) for c in buys],
             "sells": [ref(c) for c in sells], "xi": [ref(c) for c in xi],
             "bench": [], "captain": ref(captain or (xi[0] if xi else 1)),
             "vice": ref(vice or (xi[-1] if xi else 2)), "expected_pts": 60.0}
    return {"key": key, "hits": hits, "transfers": transfers, "cost": hits * 4,
            "horizon_hits": hits, "horizon_cost": hits * 4,
            "same_as": same_as, "plan_by_gw": [] if same_as else [first],
            "vs_below": None}


def _scores(**cols):
    return {k: np.asarray(v, dtype=float) for k, v in cols.items()}


ROWS = [_row("bank"), _row("hits0", transfers=1, buys=[20], sells=[16]),
        _row("hits1", hits=1, transfers=2, buys=[20, 19], sells=[16, 17]),
        _row("hits2", hits=2, transfers=3, buys=[20, 19, 18], sells=[16, 17, 15])]


# --- the walk -------------------------------------------------------------

def test_every_step_earned_reaches_the_top():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 0], hits1=[2, 2, 2, 1],
                     hits2=[3, 3, 3, 2])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits2"
    assert [(s["below"], s["above"], s["taken"]) for s in steps] == [
        ("bank", "hits0", True), ("hits0", "hits1", True),
        ("hits1", "hits2", True)]
    assert steps[0]["share"] == 0.75


def test_the_walk_stops_at_the_first_refusal():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 0], hits1=[2, 0, 0, 0],
                     hits2=[9, 9, 9, 9])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits0"
    assert [s["taken"] for s in steps] == [True, False]
    assert steps[1]["share"] == 0.25


def test_the_free_transfer_step_uses_the_same_bar():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 0, 0], hits1=[5, 5, 5, 5],
                     hits2=[9, 9, 9, 9])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "bank" and len(steps) == 1 and steps[0]["taken"] is False


def test_the_share_is_strictly_greater_and_the_bar_is_inclusive():
    scores = _scores(bank=[0, 0, 0, 0, 0], hits0=[1, 1, 1, 0, 0], hits1=[0, 0, 0, 0, 0],
                     hits2=[0, 0, 0, 0, 0])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert steps[0]["share"] == 0.6 and steps[0]["taken"] is True
    assert chosen == "hits0"


def test_a_collapsed_rung_is_skipped_not_stepped_to():
    rows = [ROWS[0], ROWS[1], _row("hits1", hits=0, transfers=1, same_as="hits0"),
            ROWS[3]]
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 1], hits2=[2, 2, 2, 2])
    chosen, steps = walk(scores, rows, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits2"
    assert [(s["below"], s["above"]) for s in steps] == [("bank", "hits0"),
                                                         ("hits0", "hits2")]


def test_a_cap_bounds_the_walk_whatever_the_draws_say():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 1], hits1=[2, 2, 2, 2],
                     hits2=[3, 3, 3, 3])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=1,
                         max_transfers=None)
    assert chosen == "hits1"
    assert steps[-1]["taken"] is False and steps[-1]["reason_kind"] == "cap"
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=0)
    assert chosen == "bank" and steps[0]["reason_kind"] == "cap"


def test_no_bank_rung_starts_the_walk_on_the_first_distinct_row():
    scores = _scores(hits0=[1, 1, 1, 1], hits1=[2, 2, 2, 2], hits2=[0, 0, 0, 0])
    chosen, steps = walk(scores, ROWS[1:], hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits1" and steps[0]["below"] == "hits0"


def test_no_scored_rung_at_all_chooses_nothing():
    assert walk({}, [], hit_bar=0.6, max_hits=None, max_transfers=None) == (None, [])


# --- the reasons, in precedence order --------------------------------------

def _ctx(**kw):
    base = dict(p_play={}, price_fall={}, difficulty={}, team_of={}, chip_plan=[])
    base.update(kw)
    return StepContext(**base)


def test_flagged_beats_everything():
    kind, text = explain_step(ROWS[0], ROWS[1], _ctx(
        p_play={(16, 4): 0.0}, price_fall={16: 0.96},
        difficulty={(1, 4): 0.9, (2, 4): 0.1}, team_of={16: 1, 20: 2},
        chip_plan=[{"gw": 5, "chip": "bboost"}]), gw=4, gws=[4, 5, 6])
    assert kind == "flagged" and text == "P16 is 0% to play"


def test_price_comes_second():
    kind, text = explain_step(ROWS[0], ROWS[1], _ctx(
        price_fall={16: 0.96}, difficulty={(1, 4): 0.9, (2, 4): 0.1},
        team_of={16: 1, 20: 2}), gw=4, gws=[4, 5, 6])
    assert kind == "price" and text == "P16 is 96% to drop tonight"


def test_fixtures_need_a_grade_of_difference():
    ctx = _ctx(difficulty={(1, 4): 0.7, (1, 5): 0.7, (1, 6): 0.8,
                           (2, 4): 0.5, (2, 5): 0.4, (2, 6): 0.5},
               team_of={16: 1, 20: 2})
    kind, text = explain_step(ROWS[0], ROWS[1], ctx, gw=4, gws=[4, 5, 6])
    assert kind == "fixtures"
    assert text == "P20's next 3 average 2.3 against P16's 3.7"
    close = _ctx(difficulty={(1, 4): 0.5, (2, 4): 0.4}, team_of={16: 1, 20: 2})
    assert explain_step(ROWS[0], ROWS[1], close, gw=4, gws=[4])[0] == "points"


def test_chip_then_points():
    kind, text = explain_step(ROWS[0], ROWS[1], _ctx(
        chip_plan=[{"gw": 5, "chip": "bboost"}]), gw=4, gws=[4, 5, 6])
    assert (kind, text) == ("chip", "a bboost is planned for GW5")
    assert explain_step(ROWS[0], ROWS[1], _ctx(), gw=4, gws=[4]) == \
        ("points", "expected points alone")


def test_a_price_flag_below_half_does_not_count():
    assert explain_step(ROWS[0], ROWS[1], _ctx(price_fall={16: 0.3}), gw=4,
                        gws=[4])[0] == "points"


# --- the served rung --------------------------------------------------------

def _objective():
    ref = lambda c: {"code": c, "name": f"P{c}", "position": "MID", "ep": 5.0}  # noqa: E731
    return {"buys": [ref(20), ref(19)], "sells": [ref(16), ref(17)], "hits": 1,
            "xi": [ref(c) for c in range(1, 12)], "bench": [ref(12)],
            "captain": ref(3), "vice": ref(4), "expected_pts": 61.5,
            "plan_by_gw": [{"gw": 4, "hits": 1, "buys": [ref(20), ref(19)],
                            "sells": [ref(16), ref(17)], "expected_pts": 61.5},
                           {"gw": 5, "hits": 0, "buys": [], "sells": [],
                            "expected_pts": 60.0}]}


def _ladder(chosen="hits0"):
    rows = [_row("bank", xi=list(range(1, 12))),
            _row("hits0", transfers=1, buys=[20], sells=[16],
                 xi=[20] + list(range(2, 12)), captain=3, vice=20),
            _row("hits1", hits=1, transfers=2, buys=[20, 19], sells=[16, 17],
                 xi=[20, 19] + list(range(3, 12)), captain=20, vice=19)]
    rows[1]["plan_by_gw"].append({**rows[1]["plan_by_gw"][0], "gw": 5,
                                  "buys": [], "sells": [], "hits": 0})
    return {"gw": 4, "chosen": chosen, "bar": 0.6, "free_transfers": 1,
            "steps": [{"below": "bank", "above": "hits0", "share": 0.79,
                       "taken": True, "reason": "expected points alone",
                       "reason_kind": "points"},
                      {"below": "hits0", "above": "hits1", "share": 0.46,
                       "taken": False, "reason": "expected points alone",
                       "reason_kind": "points"}],
            "rungs": rows}


def test_the_rungs_plan_replaces_week_one_and_every_horizon_week():
    out = serve_rung(_ladder(), _objective(), captain_note=None)
    assert [b["code"] for b in out["buys"]] == [20]
    assert [s["code"] for s in out["sells"]] == [16]
    assert out["hits"] == 0 and len(out["plan_by_gw"]) == 2
    assert out["plan_by_gw"][0]["gw"] == 4 and out["plan_by_gw"][1]["gw"] == 5
    assert set(out["plan_by_gw"][0]) == {"gw", "hits", "buys", "sells", "expected_pts"}
    assert out["expected_pts"] == 55.0            # eleven refs at 5.0
    assert out["objective"] == {"buys": _objective()["buys"], "sells": _objective()["sells"],
                                "hits": 1, "expected_pts": 61.5}
    assert out["restraint"]["chosen"] == "hits0" and out["restraint"]["bar"] == 0.6
    assert out["restraint"]["agrees"] is False and len(out["restraint"]["steps"]) == 2


def test_the_sweeps_captain_stands_when_he_is_in_the_rungs_xi():
    out = serve_rung(_ladder(), _objective(), captain_note="covering Dave")
    assert out["captain"]["code"] == 3 and out["captain_note"] == "covering Dave"
    assert out["vice"]["code"] == 20            # the rung's vice


def test_the_rungs_captain_takes_over_when_the_sweeps_is_not_in_it():
    obj = _objective()
    obj["captain"] = {"code": 99, "name": "Gone", "position": "FWD", "ep": 9.0}
    out = serve_rung(_ladder(), obj, captain_note=None)
    assert out["captain"]["code"] == 3
    assert out["captain_note"] == ("captain from the restrained plan; the "
                                   "sweep's choice (Gone) is not in it")


def test_the_vice_never_equals_the_captain():
    lad_ = _ladder()
    lad_["rungs"][1]["plan_by_gw"][0]["vice"] = {"code": 3, "name": "P3",
                                                 "position": "MID", "ep": 5.0}
    out = serve_rung(lad_, _objective(), captain_note=None)
    # The sweep's captain (3) stands; the rung's vice is also 3, so the vice
    # falls to the rung's own captain (20).
    assert out["captain"]["code"] == 3 and out["vice"]["code"] == 20


def test_agreement_is_on_the_moves():
    out = serve_rung(_ladder("hits1"), _objective(), captain_note=None)
    assert out["restraint"]["agrees"] is True and out["restraint"]["note"] is None


def test_no_ladder_or_no_chosen_rung_serves_the_objective_with_a_note():
    out = serve_rung(None, _objective(), captain_note=None)
    assert out["buys"] == _objective()["buys"] and out["hits"] == 1
    assert out["restraint"]["chosen"] is None and "ladder" in out["restraint"]["note"]
    out = serve_rung({**_ladder(), "chosen": None}, _objective(), captain_note=None)
    assert out["restraint"]["chosen"] is None and out["hits"] == 1


# --- labels, lines, recommended, served note ----------------------------------

def test_rung_labels():
    assert [rung_label(k) for k in ("bank", "hits0", "hits1", "hits3", "open")] == \
        ["bank", "free transfers only", "1 hit", "3 hits", "no cap"]


def test_the_cli_lines():
    r = serve_rung(_ladder(), _objective(), captain_note=None)["restraint"]
    assert restraint_line(r) == ("restraint: free transfers only; the step to "
                                 "1 hit was refused, 46% — expected points alone")
    assert objective_line(_objective()) == \
        "the objective wanted: P20, P19 in; P16, P17 out; 1 hit"
    taken = {**r, "steps": [r["steps"][0]]}
    assert restraint_line(taken) == "restraint: free transfers only; every step was taken"


def test_recommended_matches_the_served_moves_and_ignores_the_captain():
    rows = _ladder()["rungs"]
    advice = {"gw": 4, "buys": [{"code": 20}], "sells": [{"code": 16}],
              "captain": {"code": 3}}
    assert recommended_rung(advice, rows) == ("hits0", None)
    advice["captain"] = {"code": 999}
    assert recommended_rung(advice, rows) == ("hits0", None)
    advice["buys"] = [{"code": 55}]
    assert recommended_rung(advice, rows)[0] is None


def test_the_served_note_names_both_bars():
    lad_ = {**_ladder(), "chosen": "bank", "bar": 0.7}
    advice = {"gw": 4, "restraint": {"chosen": "hits0", "bar": 0.6}}
    assert served_note(lad_, advice) == ("the served advice was the free "
                                         "transfers only rung at bar 0.60; this "
                                         "rebuild at 0.70 chooses bank")
    assert served_note(_ladder(), {"gw": 4, "restraint": {"chosen": "hits0", "bar": 0.6}}) is None
    assert served_note(_ladder(), {"gw": 3, "restraint": {"chosen": "bank", "bar": 0.6}}) is None
    assert served_note(_ladder(), {"gw": 4}) is None


# --- on a saved board ---------------------------------------------------------

def test_build_ladder_carries_the_bar_the_chosen_rung_and_the_steps(tmp_path,
                                                                     monkeypatch):
    from tests.test_ladder import save_state

    from gaffer.config import serving_config
    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    save_state({"max_hits": 15, "max_transfers": 15})
    monkeypatch.setattr(lad, "OUTCOME_VAR_PER_EP", 0.0)
    monkeypatch.setattr(lad, "sigma_table", lambda gw: ({}, "outcome_only"))
    out = build_ladder(1, n_draws=20, seed=5)
    serving_config.cache_clear()
    assert out["bar"] == 0.60
    assert out["chosen"] in {r["key"] for r in out["rungs"]}
    keys = {"below", "above", "share", "taken", "reason", "reason_kind"}
    assert out["steps"] and all(set(s) == keys for s in out["steps"])
    # No noise: every share is 0 or 1, and the walk is a prefix of the ladder.
    assert all(s["share"] in (0.0, 1.0) for s in out["steps"])
    taken = [s["taken"] for s in out["steps"]]
    assert taken == sorted(taken, reverse=True)
    banked = json.loads((tmp_path / "reports" / "ladder_gw1.json").read_text())
    assert banked["chosen"] == out["chosen"]


def test_the_get_route_recomputes_recommended_and_adds_the_served_note(tmp_path,
                                                                        monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer import artifacts
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    lad_ = _ladder()
    (artifacts.REPORTS / "ladder_gw4.json").write_text(json.dumps(
        {**lad_, "gws": [4, 5], "cap": {}, "notes": [], "n_draws": 5}))
    (artifacts.REPORTS / "gw4-advice.json").write_text(json.dumps(
        {"gw": 4, "buys": [{"code": 20, "name": "P20"}], "sells": [{"code": 16, "name": "P16"}],
         "captain": {"code": 3}, "restraint": {"chosen": "hits0", "bar": 0.5}}))
    monkeypatch.setattr("gaffer.web.routers.ladder.latest_gw", lambda: 4)
    body = TestClient(create_app()).get("/api/ladder").json()
    assert body["recommended"] == "hits0" and body["chosen"] == "hits0"
    assert body["bar"] == 0.6 and len(body["steps"]) == 2
    assert body["served_note"] == ("the served advice was the free transfers "
                                   "only rung at bar 0.50; this rebuild at 0.60 "
                                   "chooses free transfers only")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_v16_ladder.py`
Expected: ImportError on `StepContext` (collection fails).

- [ ] **Step 3: Add the walk, the reasons and the helpers to `ladder.py`**

Add these imports at the top of `src/gaffer/ladder.py` (after the existing ones): `from dataclasses import dataclass, field`.

Add after `SEED_OFFSET`'s docstring:

```python
STEP_REASONS = ("flagged", "price", "fixtures", "chip", "points", "cap")
"""Why a step was taken or refused, in precedence order (v16 §3.3); ``cap``
is the one the caps add (plan R12). Descriptive, never a second gate: the
share decides, the reason is what the brief reads."""

FLAGGED_P_PLAY = 0.5
PRICE_FALL_BAR = 0.5
FIXTURE_GRADE = 0.2
"""One grade of five on the ticker's 0..1 difficulty (plan R7)."""

HIT_BAR_FALLBACK = 0.60
"""What the walk uses when the live config will not read — the field's own
default, so an unreadable config is a ladder at the shipped bar and not no
ladder."""


def rung_label(key: str) -> str:
    """The rung's name in prose: ``bank``, ``free transfers only``, ``2 hits``,
    ``no cap``."""
    if key == "bank":
        return "bank"
    if key == "open":
        return "no cap"
    if key == "hits0":
        return "free transfers only"
    n = int(key[4:]) if key.startswith("hits") else 0
    return f"{n} hit{'' if n == 1 else 's'}"


def walk(scores: dict[str, np.ndarray], rows: list[dict], *, hit_bar: float,
         max_hits: int | None, max_transfers: int | None
         ) -> tuple[str | None, list[dict]]:
    """The restraint walk (v16 §3.1): from the lowest scored rung, one
    distinct rung at a time, a step is taken when the higher rung beats the
    lower in at least ``hit_bar`` of the shared draws; the walk stops at the
    first refusal. ``rows`` are the ladder's rows in ``RUNG_ORDER``; a row
    with ``same_as`` or no score is never stepped to. A rung above a cap is
    refused with reason ``cap`` whatever the draws say.

    Returns ``(chosen, steps)``; ``steps`` carry ``below/above/share/taken``
    and, for a cap refusal, ``reason``/``reason_kind`` — every other step's
    reason is :func:`explain_step`'s to add.
    """
    order = [r for r in rows if not r.get("same_as") and r["key"] in scores]
    if not order:
        return None, []
    current = order[0]
    steps: list[dict] = []
    for above in order[1:]:
        share = round(float((scores[above["key"]] > scores[current["key"]]).mean()), 4)
        step = {"below": current["key"], "above": above["key"], "share": share,
                "taken": False}
        if max_hits is not None and int(above["hits"]) > int(max_hits):
            step.update(reason_kind="cap",
                        reason=f"above your cap of {int(max_hits)} hit"
                               f"{'' if int(max_hits) == 1 else 's'}")
            steps.append(step)
            break
        if max_transfers is not None and int(above["transfers"]) > int(max_transfers):
            step.update(reason_kind="cap",
                        reason=(f"above your cap of {int(max_transfers)} "
                                f"transfer{'' if int(max_transfers) == 1 else 's'}"
                                if max_transfers else "your cap is bank"))
            steps.append(step)
            break
        step["taken"] = share >= float(hit_bar)
        steps.append(step)
        if not step["taken"]:
            break
        current = above
    return current["key"], steps


@dataclass(frozen=True)
class StepContext:
    """What the reasons read (plan R3). Every map may be empty."""

    p_play: dict = field(default_factory=dict)
    """``{(code, gw): p_play}`` off the banked components frame."""
    price_fall: dict = field(default_factory=dict)
    """``{code: P(drops tonight)}`` off the banked price log."""
    difficulty: dict = field(default_factory=dict)
    """``{(team_code, gw): difficulty}``, the ticker's 0..1 rating."""
    team_of: dict = field(default_factory=dict)
    """``{code: team_code}`` off the saved pool."""
    chip_plan: list = field(default_factory=list)
    """``[{"gw", "chip"}]`` the advice's chip table would play, off the
    saved state's ``opt`` (written by ``advise.py``)."""


def step_context(gw: int, state, gws: list[int]) -> StepContext:
    """Build the context off the artifacts, swallowing every failure: a
    missing source is an empty map, and the reason falls through."""
    p_play: dict = {}
    try:
        comp = load_components(gw)
        p_play = {(int(c), int(g)): float(p) for c, g, p in
                  zip(comp["code"], comp["gw"], comp["p_play"])
                  if p == p}                                       # NaN-safe
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: no p_play for the step reasons ({exc})")
    price_fall: dict = {}
    try:
        from gaffer.price_timing import owned_price_falls
        price_fall = {int(c): float(p) for c, p in
                      owned_price_falls(list(state.owned_codes)).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: no price falls for the step reasons ({exc})")
    difficulty: dict = {}
    try:
        from gaffer.web.identity import _difficulty_by_team
        difficulty = _difficulty_by_team([int(g) for g in gws])
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: no fixture difficulty for the step reasons ({exc})")
    team_of: dict = {}
    try:
        team_of = {int(c): int(t) for c, t in
                   zip(state.pool["code"], state.pool["team_code"])}
    except Exception:  # noqa: BLE001
        pass
    chip_plan = [c for c in (state.opt.get("chip_plan") or [])
                 if isinstance(c, dict) and c.get("gw") is not None]
    return StepContext(p_play=p_play, price_fall=price_fall,
                       difficulty=difficulty, team_of=team_of,
                       chip_plan=chip_plan)


def _diff(below: dict, above: dict, key: str) -> list[dict]:
    """First-week ``key`` refs on ``above`` that ``below`` does not have."""
    have = {int(p["code"]) for p in (below.get("plan_by_gw") or [{}])[0].get(key, [])}
    return [p for p in (above.get("plan_by_gw") or [{}])[0].get(key, [])
            if int(p["code"]) not in have]


def _mean_difficulty(code: int, ctx: StepContext, gws: list[int]) -> float | None:
    team = ctx.team_of.get(int(code))
    cells = [ctx.difficulty[(team, int(g))] for g in gws
             if team is not None and (team, int(g)) in ctx.difficulty]
    return sum(cells) / len(cells) if cells else None


def explain_step(below: dict, above: dict, ctx: StepContext, *, gw: int,
                 gws: list[int]) -> tuple[str, str]:
    """``(reason_kind, reason)`` for the step ``below`` → ``above`` (v16 §3.3),
    first match in precedence: flagged, price, fixtures, chip, points."""
    extra_sells = _diff(below, above, "sells")
    extra_buys = _diff(below, above, "buys")
    for s in extra_sells:
        p = ctx.p_play.get((int(s["code"]), int(gw)))
        if p is not None and p < FLAGGED_P_PLAY:
            return "flagged", f"{s['name']} is {round(p * 100)}% to play"
    for s in extra_sells:
        f = ctx.price_fall.get(int(s["code"]))
        if f is not None and f >= PRICE_FALL_BAR:
            return "price", f"{s['name']} is {round(f * 100)}% to drop tonight"
    best = None
    for b in extra_buys:
        mb = _mean_difficulty(b["code"], ctx, gws)
        for s in extra_sells:
            ms = _mean_difficulty(s["code"], ctx, gws)
            if mb is None or ms is None:
                continue
            if ms - mb >= FIXTURE_GRADE and (best is None or ms - mb > best[0]):
                best = (ms - mb, b, s, mb, ms)
    if best is not None:
        _, b, s, mb, ms = best
        return "fixtures", (f"{b['name']}'s next {len(gws)} average "
                            f"{mb * 5:.1f} against {s['name']}'s {ms * 5:.1f}")
    for c in ctx.chip_plan:
        if int(c["gw"]) in {int(g) for g in gws}:
            return "chip", f"a {c.get('chip')} is planned for GW{int(c['gw'])}"
    return "points", "expected points alone"


def _moves(entry: dict) -> tuple[tuple[int, ...], tuple[int, ...]]:
    return (tuple(sorted(int(p["code"]) for p in entry.get("buys") or [])),
            tuple(sorted(int(p["code"]) for p in entry.get("sells") or [])))


def _week_pts(week: dict) -> float:
    """Raw XI points the way ``advise.raw_xi_pts`` sums them: the eleven's
    EP, no captain doubling, no hits."""
    return round(sum(float(p.get("ep") or 0.0) for p in week.get("xi") or []), 2)


def serve_rung(ladder: dict | None, objective: dict, *,
               captain_note: str | None) -> dict:
    """The payload's plan fields from the chosen rung (v16 §4), or the
    objective's own when there is no rung to serve.

    ``objective`` is ``{buys, sells, hits, xi, bench, captain, vice,
    expected_pts, plan_by_gw}`` in ``advise._named``'s shape. The result has
    the same keys plus ``captain_note``, ``objective`` and ``restraint``. The
    sweep's captain stands unless he is not in the rung's XI.
    """
    base = {**objective, "captain_note": captain_note,
            "objective": {k: objective[k]
                          for k in ("buys", "sells", "hits", "expected_pts")},
            "restraint": {"chosen": None, "bar": None, "steps": [],
                          "agrees": True, "note": None}}
    if ladder is None:
        base["restraint"]["note"] = ("the ladder did not build; this is the "
                                     "objective's plan")
        return base
    chosen = ladder.get("chosen")
    row = next((r for r in ladder.get("rungs") or [] if r.get("key") == chosen), None)
    if chosen is None or row is None or not row.get("plan_by_gw"):
        base["restraint"].update(bar=ladder.get("bar"), steps=list(ladder.get("steps") or []),
                                 note="no rung of the ladder could be served; "
                                      "this is the objective's plan")
        return base
    weeks = row["plan_by_gw"]
    first = weeks[0]
    xi_codes = {int(p["code"]) for p in first["xi"]}
    captain, note = objective["captain"], captain_note
    if int(captain["code"]) not in xi_codes:
        captain = first["captain"]
        note = (f"captain from the restrained plan; the sweep's choice "
                f"({objective['captain']['name']}) is not in it")
    vice = first["vice"]
    if int(vice["code"]) == int(captain["code"]):
        vice = first["captain"] if int(first["captain"]["code"]) != int(captain["code"]) \
            else next(p for p in first["xi"] if int(p["code"]) != int(captain["code"]))
    agrees = _moves(first) == _moves(objective)
    return {
        **base,
        "buys": list(first["buys"]), "sells": list(first["sells"]),
        "hits": int(first["hits"]), "xi": list(first["xi"]),
        "bench": list(first["bench"]), "captain": captain, "vice": vice,
        "expected_pts": _week_pts(first),
        "plan_by_gw": [{"gw": int(w["gw"]), "hits": int(w["hits"]),
                        "buys": list(w["buys"]), "sells": list(w["sells"]),
                        "expected_pts": _week_pts(w)} for w in weeks],
        "captain_note": note,
        "restraint": {"chosen": chosen, "bar": ladder.get("bar"),
                      "steps": list(ladder.get("steps") or []),
                      "agrees": agrees,
                      "note": None if agrees else
                      f"the objective's plan was the {rung_label(chosen)} rung's "
                      f"neighbour; the walk stopped at {rung_label(chosen)}"},
    }


def restraint_line(restraint: dict) -> str:
    """One CLI line: the rung, and the refused step if there was one."""
    chosen = rung_label(str(restraint.get("chosen") or "bank"))
    refused = next((s for s in restraint.get("steps") or [] if not s.get("taken")), None)
    if refused is None:
        return f"restraint: {chosen}; every step was taken"
    return (f"restraint: {chosen}; the step to {rung_label(refused['above'])} was "
            f"refused, {round(float(refused['share']) * 100)}% — {refused['reason']}")


def objective_line(objective: dict | None) -> str:
    """"the objective wanted: X, Y in; Z out; 1 hit"."""
    if not objective:
        return "the objective wanted: nothing on record"
    buys = ", ".join(str(p["name"]) for p in objective.get("buys") or []) or "nobody"
    sells = ", ".join(str(p["name"]) for p in objective.get("sells") or []) or "nobody"
    hits = int(objective.get("hits") or 0)
    return (f"the objective wanted: {buys} in; {sells} out; {hits} hit"
            f"{'' if hits == 1 else 's'}")


def recommended_rung(advice: dict | None, rows: list[dict]
                     ) -> tuple[str | None, str | None]:
    """``(rung, note)`` — the rung whose first-week **moves** are the served
    advice's (plan R4: the captain is ignored, the sweep's may stand)."""
    if not advice:
        return None, "no served advice"
    wanted = _moves(advice)
    for row in rows:
        if row.get("same_as") or not row.get("plan_by_gw"):
            continue
        if _moves(row["plan_by_gw"][0]) == wanted:
            return row["key"], None
    return None, "the served advice's moves match no rung"


def served_note(ladder: dict, advice: dict | None) -> str | None:
    """When a rebuild's choice differs from what the advice served (v16 §4)."""
    if not advice or int(advice.get("gw", -1)) != int(ladder.get("gw", -2)):
        return None
    served = advice.get("restraint") or {}
    if served.get("chosen") is None or ladder.get("chosen") is None:
        return None
    if (served.get("chosen"), served.get("bar")) == (ladder.get("chosen"), ladder.get("bar")):
        return None
    return (f"the served advice was the {rung_label(served['chosen'])} rung at "
            f"bar {float(served.get('bar') or 0):.2f}; this rebuild at "
            f"{float(ladder.get('bar') or 0):.2f} chooses "
            f"{rung_label(ladder['chosen'])}")


def _hit_bar() -> float:
    try:
        from gaffer.config import serving_config
        return float(serving_config().hit_bar)
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: the live config would not read ({exc}); bar {HIT_BAR_FALLBACK}")
        return HIT_BAR_FALLBACK
```

Then in `build_ladder`, replace

```python
    (max_hits, max_transfers), cap_source = _caps(state)
    cap_rung, cap_requested = _cap_rung(max_hits, max_transfers, rows)
    recommended, recommended_note = _recommended(gw, solved)
```

with

```python
    (max_hits, max_transfers), cap_source = _caps(state)
    cap_rung, cap_requested = _cap_rung(max_hits, max_transfers, rows)
    try:
        recommended, recommended_note = recommended_rung(load_advice(gw), rows)
    except Exception as exc:  # noqa: BLE001 — no advice is no chip, not a crash
        recommended, recommended_note = None, f"no served advice for GW{int(gw)}"
    # v16 §3.1: the restraint walk on the same draws, with its reasons.
    hit_bar = _hit_bar()
    chosen, steps = walk(scores, rows, hit_bar=hit_bar, max_hits=max_hits,
                         max_transfers=max_transfers)
    ctx = step_context(gw, state, gws)
    for step in steps:
        if "reason_kind" not in step:
            kind, text = explain_step(by_key[step["below"]], by_key[step["above"]],
                                      ctx, gw=gw, gws=gws)
            step.update(reason_kind=kind, reason=text)
```

and add to the payload dict, after `"recommended_note": recommended_note,`:

```python
        "bar": hit_bar, "chosen": chosen, "steps": steps,
```

Delete the now-unused `_recommended` function. Adjust `tests/test_ladder.py::test_the_cap_rung_and_the_recommended_rung` if its expected notes changed: the no-advice note is still `"no served advice for GW1"`; the sweep-gated note becomes `"the served advice's moves match no rung"` — update that one string in `tests/test_ladder.py` (unprotected) and nothing else.

- [ ] **Step 4: Schema and router**

In `src/gaffer/web/schemas.py`, before `class LadderCap`:

```python
class LadderStep(BaseModel):
    """One step of the restraint walk (v16 §3.1). ``share`` is the share of
    the shared draws in which ``above`` outscored ``below``."""

    below: str
    above: str
    share: float
    taken: bool
    reason: str = ""
    reason_kind: str = "points"
```

In `LadderPayload`, after `recommended_note`:

```python
    bar: float | None = None
    """The hit bar the walk used (v16 §3.2)."""
    chosen: str | None = None
    """The rung the walk stopped on — the served advice's plan."""
    steps: list[LadderStep] = Field(default_factory=list)
    served_note: str | None = None
    """Set by the router when a rebuild's choice differs from the advice
    on disk."""
```

In `src/gaffer/web/routers/ladder.py`, replace the `fields = ...; return LadderPayload(**fields)` tail of `ladder()` with:

```python
    # v16 (plan R4): the advise-time build ran before the advice was written,
    # so the served rung and the rebuild note are read off the advice *now*.
    advice = None
    try:
        advice = load_advice(wanted)
    except Exception:  # noqa: BLE001 — no advice is no chip
        advice = None
    if advice is not None and int(advice.get("gw", -1)) == int(wanted):
        payload["recommended"], payload["recommended_note"] = recommended_rung(
            advice, payload.get("rungs") or [])
        payload["served_note"] = served_note(payload, advice)
    fields = {k: v for k, v in payload.items()
              if k in LadderPayload.model_fields}
    return LadderPayload(**fields)
```

with `from gaffer.artifacts import latest_gw, load_advice` and `from gaffer.ladder import build_ladder, load_ladder, recommended_rung, served_note`.

- [ ] **Step 5: Regenerate the types** (Conventions block).

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest -q tests/test_v16_ladder.py tests/test_ladder.py tests/test_web_ladder.py tests/test_v13_degradation.py -k "not config_gained"`
Expected: all pass. Then `cd frontend && npx tsc --noEmit && npx vitest run src/types.generated.test.ts src/hubs/this-week/LadderCard.test.tsx`.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/ladder.py src/gaffer/web/schemas.py src/gaffer/web/routers/ladder.py tests/test_v16_ladder.py tests/test_ladder.py frontend/src/schemas.json frontend/src/types.generated.ts
git commit -m "feat(v16): the restraint walk on the ladder — bar, chosen rung, steps with reasons; serve_rung; recommended by moves"
```

---

### Task 3: The advice becomes the chosen rung (`advise.py`, **orchestrator only**) and the CLI lines

**Files:**
- Modify (**protected, orchestrator**): `src/gaffer/advise.py` — the `Advice` dataclass and the tail of `run_advise`
- Modify: `src/gaffer/cli.py` (`advise` command, after the caps line)
- Test: `tests/test_v16_restraint.py` (new; the implementer writes it and the CLI change; the orchestrator applies the `advise.py` diff first and shows it to the user before commit, per spec §8)

- [ ] **Step 1 (orchestrator): the `Advice` fields**

After `caps: dict | None = None` in `class Advice`:

```python
    # v16 §4 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md). The
    # objective's own week-one plan, kept beside the served (restrained) one,
    # and the ladder walk that chose the served rung. Both default to None so
    # a payload written before this — and every positional construction —
    # still loads.
    objective: dict | None = None
    restraint: dict | None = None
```

- [ ] **Step 2 (orchestrator): the import and the tail of `run_advise`**

`from gaffer.ladder import build_ladder` → `from gaffer.ladder import build_ladder, serve_rung`.

Then, in `run_advise`, **insert** the following block directly after the alternative-plans block (the `alt_rows` loop) and before `for b in buys:` (the tag loop):

```python
    # v16 §4 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md): the
    # components and the solve state are banked *before* the payload, because
    # the ladder solves off the state and the payload's plan is the rung the
    # ladder's restraint walk chose. The objective's own plan rides beside it
    # as ``objective`` and the walk as ``restraint``; a ladder that will not
    # build leaves the objective's plan served, with a note.
    REPORTS.mkdir(exist_ok=True)
    # The same frame §4.6 banded above, not a second build of it: one frame
    # means the ceiling on the page and the breakdown on disk cannot disagree.
    save_components(components, gw)
    save_solve_state(SolveState(
        gw=gw, gws=gws, deadline=deadline,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode="weekly" if my is not None else "initial_squad", bank=state.bank,
        free_transfers=state.free_transfers, owned_codes=owned_now,
        lam=lam, league_eo=league_eo, cover=cover, avail_by_gw=avail_by_gw,
        # The lambda lookup is not JSON, but "were the priors on" is, and it
        # is all the web re-solve needs to rebuild the same lookup from the
        # shipped asset and price a What-If baseline exactly like this advice.
        opt={**opt_kw, "horizon": cfg.horizon,
             "decision_priors": bool(cfg.decision_priors),
             # v13 §2.3: raw config values (15 = no cap); read back through
             # ``artifacts.caps_from_state`` by every re-solve of this board.
             "max_hits": int(cfg.max_hits),
             "max_transfers": int(cfg.max_transfers),
             # v16 §3.3: the chips the table would play, for the ladder's
             # ``chip`` step reason. ``solve_kw_from_state`` reads named keys
             # only, so no re-solve sees this.
             "chip_plan": [{"gw": int(r["gw"]), "chip": str(r["chip"])}
                           for r in chip_rows if r.get("play_now")]},
        pool=pool_rows(pool, players, owned_now, ep_by, gws)))
    # v13 §3.2 / v16 §4: the transfer ladder, off the state just saved. Never
    # the run's failure — a ladder that could not be built is one printed
    # line, the objective's plan served, and a card with a rebuild button.
    ladder = None
    try:
        ladder = build_ladder(gw)
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: not built for GW{gw} ({exc})")
    served = serve_rung(ladder, {
        "buys": buys, "sells": sells, "hits": int(first.hits),
        "xi": _named(first.xi, name_of, pos_of, ep_by, gw),
        "bench": _named(first.bench, name_of, pos_of, ep_by, gw),
        "captain": _named([first.captain], name_of, pos_of, ep_by, gw)[0],
        "vice": _named([first.vice], name_of, pos_of, ep_by, gw)[0],
        "expected_pts": round(raw_xi_pts(first, ep_by), 2),
        "plan_by_gw": [{"gw": p.gw, "hits": p.hits,
                        "buys": _named(p.buys, name_of, pos_of, ep_by, p.gw),
                        "sells": _named(p.sells, name_of, pos_of, ep_by, p.gw),
                        "expected_pts": round(raw_xi_pts(p, ep_by), 2)}
                       for p in plan.gw_plans]},
        captain_note=captain_note)
    # The tags and the sweep frequencies below decorate the *served* moves.
    buys, sells = served["buys"], served["sells"]
```

Then **replace** the `advice = Advice(...)` call so that these keyword arguments read from `served`: `buys=buys, sells=sells, hits=served["hits"], xi=served["xi"], bench=served["bench"], captain=served["captain"], vice=served["vice"], expected_pts=served["expected_pts"], plan_by_gw=served["plan_by_gw"], captain_note=served["captain_note"]`, and add `objective=served["objective"], restraint=served["restraint"],` after `caps=(...)`. Every other keyword is unchanged.

Then **delete** from after the `atomic_write(advice_path, ...)` call: the `save_components(components, gw)` line and its comment, the whole `save_solve_state(SolveState(...))` call, and the `try: build_ladder(gw) ... except` block with its v13 comment — all three now live above. `REPORTS.mkdir(exist_ok=True)` before `advice_path` may stay or go (it is idempotent). `save_availability(avail, gw)`, `append_advice_history(asdict(advice), gw)` and `return advice` stay where they are.

Check the protected pins by hand before running anything: `grep -n "build_ladder(gw)\|save_solve_state(\|save_availability(avail, gw)\|append_advice_history(asdict(advice), gw)\|_named(first.xi, name_of, pos_of, ep_by, gw)\|pool_rows(pool, players, owned_now, ep_by, gws)" src/gaffer/advise.py` — the order must be `save_solve_state` < `build_ladder(gw)` < `save_availability` < `append_advice_history`, and `build_ladder(gw)` must be preceded by a `try:` with the exact print line.

- [ ] **Step 3 (implementer): the failing tests**

```python
"""v16 §4 — the advice is the chosen rung: source pins on the protected
diff, the Advice fields, the CLI lines."""
from __future__ import annotations

import inspect

from tests.test_v4c_degradation import _fixture_advice


def test_advice_carries_the_two_blocks_with_safe_defaults():
    from gaffer.advise import Advice

    a = _fixture_advice()
    assert isinstance(a, Advice)
    assert getattr(a, "objective", None) is None
    assert getattr(a, "restraint", None) is None


def test_the_state_is_saved_then_the_ladder_then_the_served_plan():
    """Source-level like every v13/v15 pin (plan R6): the order the spec
    fixes, and the served fields coming from ``serve_rung``."""
    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    state = src.index("save_solve_state(")
    ladder = src.index("build_ladder(gw)")
    served = src.index("served = serve_rung(ladder, {")
    advice = src.index("advice = Advice(")
    written = src.index("atomic_write(advice_path")
    assert state < ladder < served < advice < written
    for key in ("hits", "xi", "bench", "captain", "vice", "expected_pts",
                "plan_by_gw", "captain_note", "objective", "restraint"):
        assert f'served["{key}"]' in src, key
    assert 'buys, sells = served["buys"], served["sells"]' in src
    # The tags and frequencies decorate the served moves, not the objective's.
    assert src.index('buys, sells = served["buys"]') < src.index("transfer_tag(")
    assert '"chip_plan": [{"gw": int(r["gw"]), "chip": str(r["chip"])}' in src


def test_the_objective_dict_is_the_solvers_own_week_one():
    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    block = src[src.index("served = serve_rung(ladder, {"):src.index("captain_note=captain_note)")]
    assert '"hits": int(first.hits)' in block
    assert '"expected_pts": round(raw_xi_pts(first, ep_by), 2)' in block
    assert "for p in plan.gw_plans]" in block


def _cli(tmp_path, monkeypatch, advice):
    from typer.testing import CliRunner

    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod
    from gaffer.cli import app

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\n'
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise", lambda cfg, client=None: advice)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)
    return CliRunner().invoke(app, ["advise"])


def test_the_cli_prints_the_restraint_line_and_the_objective_when_they_differ(
        tmp_path, monkeypatch):
    advice = _fixture_advice()
    advice.restraint = {"chosen": "hits0", "bar": 0.6, "agrees": False, "note": "x",
                        "steps": [{"below": "bank", "above": "hits0", "share": 0.79,
                                   "taken": True, "reason": "expected points alone",
                                   "reason_kind": "points"},
                                  {"below": "hits0", "above": "hits1", "share": 0.46,
                                   "taken": False, "reason": "expected points alone",
                                   "reason_kind": "points"}]}
    advice.objective = {"buys": [{"name": "Isak"}], "sells": [{"name": "Rice"}],
                        "hits": 1, "expected_pts": 60.0}
    out = _cli(tmp_path, monkeypatch, advice)
    assert out.exit_code == 0, out.output
    assert ("restraint: free transfers only; the step to 1 hit was refused, "
            "46% — expected points alone\n") in out.output
    assert "the objective wanted: Isak in; Rice out; 1 hit\n" in out.output
    assert out.output.index("restraint:") < out.output.index("Captain:")


def test_the_cli_prints_no_objective_line_when_they_agree(tmp_path, monkeypatch):
    advice = _fixture_advice()
    advice.restraint = {"chosen": "hits1", "bar": 0.6, "agrees": True, "note": None,
                        "steps": []}
    advice.objective = {"buys": [], "sells": [], "hits": 1, "expected_pts": 60.0}
    out = _cli(tmp_path, monkeypatch, advice)
    assert "restraint: 1 hit; every step was taken\n" in out.output
    assert "the objective wanted" not in out.output


def test_an_advice_without_the_field_prints_nothing_extra(tmp_path, monkeypatch):
    out = _cli(tmp_path, monkeypatch, _fixture_advice())
    assert "restraint:" not in out.output
```

- [ ] **Step 4 (implementer): the CLI lines**

In `src/gaffer/cli.py`'s `advise` command, directly after the `_caps_line` block:

```python
    # v16 §4: the rung the ladder chose, and the objective's own plan when
    # they differ. Absent on an Advice built without the field — which keeps
    # tests/test_v4c_degradation.py's character-for-character rail green.
    restraint = getattr(advice, "restraint", None)
    if restraint:
        from gaffer.ladder import objective_line, restraint_line

        typer.echo(restraint_line(restraint))
        if not restraint.get("agrees", True):
            typer.echo(objective_line(getattr(advice, "objective", None)))
```

- [ ] **Step 5: Run the tests and the whole Python suite**

Run: `.venv/bin/pytest -q tests/test_v16_restraint.py tests/test_advise.py tests/test_v4c_degradation.py tests/test_v13_degradation.py tests/test_cli.py` then `.venv/bin/pytest -q`.
Expected: everything passes.

- [ ] **Step 6: Commit** (orchestrator, after showing the `advise.py` diff to the user)

```bash
git add src/gaffer/advise.py src/gaffer/cli.py tests/test_v16_restraint.py
git commit -m "feat(v16): the advice is the chosen rung — state, ladder, then the served plan; objective and restraint on the payload; CLI lines"
```

---

### Task 4: The objective's trace beside the served plan (`routers/plan.py`, PlannerBoard)

**Files:**
- Modify: `src/gaffer/web/schemas.py` (`PlanTimeline.objective: PlanGw | None`)
- Modify: `src/gaffer/web/routers/plan.py`
- Modify: `frontend/src/hubs/planning/PlannerBoard.tsx` (+ its test)
- Test: `tests/test_v16_plan_objective.py` (new)
- Regenerate types.

**Context.** `routers/plan.py::plan(gw)` builds `weeks` from `advice["plan_by_gw"]` through a local `build(entries, *, head_refs)` closure and traces them with `trace_plan(...)`. Since Task 3 `plan_by_gw` is the served rung's, so the board's "Why this move" already follows the served plan. What is missing is the objective's week one, traced the same way, only when `advice["restraint"]["agrees"]` is false.

- [ ] **Step 1: The failing tests**

```python
"""v16 §4 — the objective's week one on /api/plan/{gw}, traced, when it
differs from the served plan."""
from __future__ import annotations

from tests.test_v12_w5_plan_trace import P, S, _week, wired  # noqa: F401
from gaffer.web.routers import plan as plan_router


def _with_objective(wired, agrees):
    state = wired([_week(5, buys=[P], sells=[S])])
    real = plan_router.load_advice

    def advice(gw):
        out = real(gw)
        out["objective"] = {"buys": [P], "sells": [S], "hits": 1, "expected_pts": 58.0}
        out["restraint"] = {"chosen": "hits0", "bar": 0.6, "agrees": agrees,
                            "steps": [], "note": None}
        return out
    plan_router.load_advice = advice
    return state


def test_a_disagreeing_objective_is_served_with_its_own_trace(wired, monkeypatch):
    _with_objective(wired, agrees=False)
    out = plan_router.plan(5)
    assert out.objective is not None
    assert out.objective.gw == 5 and out.objective.hits == 1
    assert out.objective.hit_cost == 4
    assert out.objective.trace is not None
    assert out.objective.trace.moves[0].buy_code == 100
    assert out.objective.captain is None            # never the armband


def test_an_agreeing_objective_is_not_repeated(wired):
    _with_objective(wired, agrees=True)
    assert plan_router.plan(5).objective is None


def test_a_payload_without_the_block_serves_none(wired):
    wired([_week(5, buys=[P], sells=[S])])
    assert plan_router.plan(5).objective is None
```

Note: `tests/test_v12_w5_plan_trace.py`'s `wired` fixture monkeypatches `plan_router.load_advice`; the helper above wraps that patched function, and pytest's monkeypatch undoes both.

- [ ] **Step 2: Run to see them fail** — `.venv/bin/pytest -q tests/test_v16_plan_objective.py` → AttributeError `objective`.

- [ ] **Step 3: Schema and router**

`PlanTimeline` gains, after `alternatives`:

```python
    objective: PlanGw | None = None
    """v16 §4: the solver's own week one, traced, when the served plan is a
    different rung of the ladder. ``None`` when they agree or when the
    payload predates the field."""
```

In `routers/plan.py::plan`, factor the trace call into a helper so it can run twice. Replace the `if TRACE and weeks: try: ... traced = trace_plan(...) ... for week, one in zip(weeks, traced): ...` block with a nested function `attach_trace(target: list[PlanGw]) -> None` holding exactly the same body (the `price_timing, price_fall = _price_falls(state)` read, the `move_names`, the `trace_plan(...)` call over `target`, the `for week, one in zip(target, traced)` loop, the `except Exception` print), and call `attach_trace(weeks)` where the block was. Then, before the `return`:

```python
    # v16 §4: the objective's week one beside the served rung's, traced the
    # same way, only when the two differ — the board says "the objective
    # wanted" under week one, and an agreeing objective would say it twice.
    objective_week: PlanGw | None = None
    restraint = advice.get("restraint") or {}
    objective = advice.get("objective")
    if isinstance(objective, dict) and restraint.get("agrees") is False:
        built = build([{"gw": head, "hits": objective.get("hits", 0),
                        "buys": objective.get("buys") or [],
                        "sells": objective.get("sells") or [],
                        "expected_pts": objective.get("expected_pts", 0.0)}],
                      head_refs=False)
        if TRACE and built:
            attach_trace(built)
        objective_week = built[0] if built else None
    return PlanTimeline(gw=head, generated_at=state.generated_at, weeks=weeks,
                        bank=start, alternatives=_alternatives(advice, build),
                        objective=objective_week)
```

- [ ] **Step 4: Regenerate types; run** `.venv/bin/pytest -q tests/test_v16_plan_objective.py tests/test_v12_w5_plan_trace.py tests/test_web_plan*.py`.

- [ ] **Step 5: PlannerBoard**

In `frontend/src/hubs/planning/PlannerBoard.tsx`, under week one's card only (inside the `weeks.map((week, i) => ...)` body, after the `{week.trace && (<details ...>)}` block), add:

```tsx
{/* v16 §4: the objective's own week one, when the ladder's restraint
    served a different rung. Its trace is the same accounting over the
    plan the solver returned, so the two "why"s are comparable. */}
{i === 0 && data.objective && (
  <details className="mt-2" data-testid="board-objective">
    <summary className="cursor-pointer text-text-muted">
      The objective wanted
    </summary>
    <div className="mt-1 flex flex-col gap-0.5">
      <p className="text-text">
        {[...data.objective.buys.map((m) => `${m.name} in`),
          ...data.objective.sells.map((m) => `${m.name} out`)].join(', ')
          || 'no moves'}
        {data.objective.hits > 0 && (
          <span className="text-down">
            {` · ${data.objective.hits} hit${data.objective.hits === 1 ? '' : 's'}`}
          </span>
        )}
      </p>
      {data.objective.trace?.moves.map((m) => (
        <p key={`${m.buy_code}-${m.sell_code}`} className="font-mono tn text-xs">
          <span>{`${m.sell_name} → ${m.buy_name}`}</span>
          <span className="ml-2 text-text">{fmtDelta(m.ep_gain)}</span>
        </p>
      ))}
      <p className="text-text-faint">
        The board above draws the plan the ladder's restraint served; this
        is the solver's own choice, traced the same way.
      </p>
    </div>
  </details>
)}
```

`data` is the `PlanTimeline` the board already holds (whatever the local name is — follow the file). Add to `PlannerBoard.test.tsx`:

```tsx
it('shows what the objective wanted under week one when it differs', async () => {
  wire({ ...plan([WEEK]), objective: { ...WEEK, hits: 1, hit_cost: 4,
    trace: { gw: 5, moves: [{ gw: 5, buy_code: 1, buy_name: 'Wirtz', sell_code: 2,
      sell_name: 'Isak', ep_gain: 3.5, lambda_tilt: 0, note: '' }], ep_gain: 3.5,
      hits: 1, hit_cost: 4, ft_used: 1, ft_after: 1, ft_use_penalty: 0,
      ft_shadow: 1.5, ft_basis: 'flat', bank_value: null, theta: null,
      price_charge: null, note: '' } } })
  render(<PlannerBoard />)
  const block = await screen.findByTestId('board-objective')
  expect(block).toHaveTextContent('Wirtz in, Isak out')
  expect(block).toHaveTextContent('1 hit')
  expect(block).toHaveTextContent('Isak → Wirtz')
})

it('draws no objective block when the payload has none', async () => {
  wire(plan([WEEK]))
  render(<PlannerBoard />)
  await screen.findByTestId('board-week-5')
  expect(screen.queryByTestId('board-objective')).toBeNull()
})
```

- [ ] **Step 6: Run** `cd frontend && npx tsc --noEmit && npx vitest run src/hubs/planning` — all pass.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/plan.py tests/test_v16_plan_objective.py frontend/src/hubs/planning/PlannerBoard.tsx frontend/src/hubs/planning/PlannerBoard.test.tsx frontend/src/schemas.json frontend/src/types.generated.ts
git commit -m "feat(v16): the objective's week one traced beside the served plan on the Planning board"
```

---

### Task 5: The deviation note — store and routes

**Files:**
- Create: `src/gaffer/decisions.py`
- Create: `src/gaffer/web/routers/decisions.py`
- Modify: `src/gaffer/web/schemas.py` (`DecisionGrade`, `DecisionNote`, `DecisionWrite`)
- Modify: `src/gaffer/web/app.py` (import + `include_router`)
- Test: `tests/test_v16_decisions.py` (new)
- **Orchestrator only:** `tests/test_v11_degradation.py` route pin 49 → 50 and a docstring paragraph naming `/api/decisions/{gw}`.
- Regenerate types.

- [ ] **Step 1: The failing tests**

```python
"""v16 §5 — the deviation note: store, refusals, the deadline rule, the tally."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.decisions import (REASONS, TEXT_MAX, by_reason, load_decisions,
                              note_for, note_state, save_note)
from gaffer.web.app import create_app

NOW = pd.Timestamp("2026-09-05T12:00:00Z")


@pytest.fixture()
def reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    return artifacts.REPORTS


def _advice(reports, gw, deadline):
    (reports / f"gw{gw}-advice.json").write_text(json.dumps(
        {"gw": gw, "deadline": deadline, "buys": [], "sells": []}))


def _ledger(reports, rows):
    (reports / "decision_ledger.json").write_text(json.dumps({"gws": rows}))


def _row(gw, delta):
    return {"gw": gw, "lanes": [{"lane": "transfers", "delta_pts": delta,
                                 "label": "Good" if delta > 0 else "Blunder"}]}


def test_the_eight_reasons_and_the_text_cap():
    assert REASONS == ("injury", "fixtures", "eye_test", "price", "chip",
                       "rival", "gut", "other")
    assert TEXT_MAX == 280


def test_an_absent_note_is_the_empty_shape(reports):
    assert note_for(4) == {"gw": 4, "reason": None, "text": "", "at": None}


def test_save_round_trips_and_stamps(reports):
    out = save_note(4, "injury", "Rice was 0% to play")
    assert out["reason"] == "injury" and out["text"] == "Rice was 0% to play"
    assert out["at"].endswith("+00:00")
    assert note_for(4) == out
    assert load_decisions() == {4: out}
    save_note(4, "gut", "")
    assert note_for(4)["reason"] == "gut" and len(load_decisions()) == 1


def test_a_corrupt_store_reads_as_empty(reports):
    (reports / "decisions.json").write_text("{not json")
    assert load_decisions() == {}


def test_save_refuses_a_bad_reason_and_long_text(reports):
    with pytest.raises(ValueError, match="reason"):
        save_note(4, "vibes", "")
    with pytest.raises(ValueError, match="280"):
        save_note(4, "gut", "x" * 281)


def test_state_before_the_deadline_open_after_and_graded_once_banked(reports):
    _advice(reports, 4, "2026-09-06T17:30:00Z")
    assert note_state(4, now=NOW)[0] == "before_deadline"
    assert note_state(4, now=pd.Timestamp("2026-09-07T12:00:00Z"))[0] == "open"
    _ledger(reports, [_row(4, -7)])
    state, deadline, grade = note_state(4, now=pd.Timestamp("2026-09-10T12:00:00Z"))
    assert state == "graded" and deadline == "2026-09-06T17:30:00Z"
    assert grade == {"lane": "transfers", "label": "Blunder", "delta_pts": -7}


def test_no_advice_and_no_snapshot_means_open(reports):
    assert note_state(9, now=NOW) == ("open", None, None)


def test_the_by_reason_tally(reports):
    save_note(2, "injury", "")
    save_note(3, "injury", "")
    save_note(4, "gut", "")
    ledger = [_row(1, 0), _row(2, -7), _row(3, 3), _row(4, 5),
              {"gw": 5, "lanes": [{"lane": "transfers", "delta_pts": None}]}]
    assert by_reason(ledger, load_decisions()) == [
        {"reason": "injury", "count": 2, "mean_delta_pts": -2.0},
        {"reason": "gut", "count": 1, "mean_delta_pts": 5.0},
        {"reason": "none", "count": 1, "mean_delta_pts": 0.0}]


# --- the routes -----------------------------------------------------------

@pytest.fixture()
def client(reports, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.decisions.upcoming_gw", lambda: 5)
    monkeypatch.setattr("gaffer.web.routers.decisions._now",
                        lambda: pd.Timestamp("2026-09-07T12:00:00Z"))
    return TestClient(create_app())


def test_get_is_never_a_404(client):
    body = client.get("/api/decisions/4").json()
    assert body == {"gw": 4, "reason": None, "text": "", "at": None,
                    "state": "open", "deadline": None, "grade": None}


def test_post_saves_and_get_reads_it_back(client, reports):
    _advice(reports, 4, "2026-09-06T17:30:00Z")
    resp = client.post("/api/decisions/4", json={"reason": "fixtures", "text": "easier run"})
    assert resp.status_code == 200, resp.text
    body = client.get("/api/decisions/4").json()
    assert body["reason"] == "fixtures" and body["text"] == "easier run"
    assert body["state"] == "open" and body["deadline"] == "2026-09-06T17:30:00Z"


@pytest.mark.parametrize("payload, constraint", [
    ({"reason": "vibes", "text": ""}, "unknown_reason"),
    ({"reason": "gut", "text": "x" * 281}, "text_too_long"),
])
def test_post_refuses_in_the_settings_shape(client, payload, constraint):
    resp = client.post("/api/decisions/4", json=payload)
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == constraint
    assert resp.json()["detail"]["players"] == []


def test_post_refuses_a_gameweek_past_the_next_deadline(client):
    resp = client.post("/api/decisions/6", json={"reason": "gut", "text": ""})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "future_gw"


def test_post_refuses_before_the_deadline_and_after_grading(client, reports):
    _advice(reports, 5, "2026-09-11T17:30:00Z")
    resp = client.post("/api/decisions/5", json={"reason": "gut", "text": ""})
    assert resp.status_code == 422 and resp.json()["detail"]["constraint"] == "not_open"
    _advice(reports, 4, "2026-09-06T17:30:00Z")
    _ledger(reports, [_row(4, 3)])
    resp = client.post("/api/decisions/4", json={"reason": "gut", "text": ""})
    assert resp.status_code == 422 and resp.json()["detail"]["constraint"] == "graded"
    body = client.get("/api/decisions/4").json()
    assert body["state"] == "graded" and body["grade"]["delta_pts"] == 3
```

- [ ] **Step 2: Run to see them fail** — `.venv/bin/pytest -q tests/test_v16_decisions.py` → ModuleNotFoundError `gaffer.decisions`.

- [ ] **Step 3: The store**

`src/gaffer/decisions.py`:

```python
"""The deviation note (v16 §5): why the manager did something other than
what the advice said, one note per gameweek.

A reason code from a fixed list plus up to 280 characters of text. Written
through :func:`gaffer.io.atomic_write` under a module lock — the browser
saves one field at a time and two saves racing on one file is a click, not
a hypothetical. Read by the Review tab (beside the grade), the by-reason
tally and the brief. Nothing here decides anything.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import pandas as pd

from gaffer import artifacts
from gaffer.io import atomic_write

REASONS = ("injury", "fixtures", "eye_test", "price", "chip", "rival",
           "gut", "other")
"""The whole vocabulary. Eight, and the tally is per code — more codes is a
later cycle's question (spec §11)."""

TEXT_MAX = 280

DECISIONS = "decisions.json"

NO_NOTE = "none"
"""The tally's row for graded gameweeks with no note."""

_LOCK = threading.Lock()


def decisions_path():
    return artifacts.REPORTS / DECISIONS


def load_decisions() -> dict[int, dict]:
    """``{gw: {gw, reason, text, at}}``; ``{}`` on any failure."""
    path = decisions_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return {int(gw): {"gw": int(gw), "reason": note.get("reason"),
                          "text": str(note.get("text") or ""),
                          "at": note.get("at")}
                for gw, note in (raw or {}).items()}
    except Exception as exc:  # noqa: BLE001 — a corrupt store is an empty one
        print(f"decisions: store unreadable ({exc})")
        return {}


def note_for(gw: int) -> dict:
    """The note, or the empty shape — never an absence the client has to
    special-case."""
    return load_decisions().get(int(gw)) or {"gw": int(gw), "reason": None,
                                             "text": "", "at": None}


def save_note(gw: int, reason: str, text: str) -> dict:
    """Write one gameweek's note. ``ValueError`` on a bad reason or a long
    text — the router turns those into its refusal shape."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    text = str(text or "")
    if len(text) > TEXT_MAX:
        raise ValueError(f"text is at most {TEXT_MAX} characters")
    note = {"gw": int(gw), "reason": reason, "text": text,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _LOCK:
        notes = load_decisions()
        notes[int(gw)] = note
        artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
        atomic_write(decisions_path(), json.dumps(
            {str(g): n for g, n in sorted(notes.items())}, indent=1))
    return note


def _deadline_for(gw: int) -> str | None:
    """The advised deadline: the advice payload's, else the events
    snapshot's, else ``None``."""
    try:
        deadline = artifacts.load_advice(gw).get("deadline")
        if deadline:
            return str(deadline)
    except Exception:  # noqa: BLE001
        pass
    try:
        events = artifacts.load_snapshot("live/events.parquet")
        row = events[events["gw"] == int(gw)]
        if not row.empty:
            return str(row["deadline_time"].iloc[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def grade_for(gw: int, ledger: list[dict] | None = None) -> dict | None:
    """The transfers lane's grade off the ledger, or ``None``."""
    if ledger is None:
        from gaffer.review import load_ledger
        ledger = load_ledger()
    for row in ledger:
        if int(row.get("gw", -1)) != int(gw):
            continue
        for lane in row.get("lanes") or []:
            if lane.get("lane") == "transfers":
                return {"lane": "transfers", "label": lane.get("label"),
                        "delta_pts": lane.get("delta_pts")}
    return None


def note_state(gw: int, *, now: pd.Timestamp | None = None
               ) -> tuple[str, str | None, dict | None]:
    """``(state, deadline, grade)`` — ``before_deadline`` | ``open`` |
    ``graded`` (plan R11). No deadline on record is ``open``."""
    grade = grade_for(gw)
    deadline = _deadline_for(gw)
    if grade is not None:
        return "graded", deadline, grade
    if deadline is not None:
        stamp = pd.Timestamp(deadline)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        ts = pd.Timestamp.now(tz="UTC") if now is None else now
        if stamp > ts:
            return "before_deadline", deadline, None
    return "open", deadline, None


def by_reason(ledger: list[dict], notes: dict[int, dict]) -> list[dict]:
    """Per reason code: count and mean transfers-lane ``delta_pts`` over the
    graded gameweeks, ``REASONS`` order then ``none``. Rows with no graded
    transfers lane are left out; a graded row with no note counts under
    ``none``. Codes with no rows are omitted."""
    cells: dict[str, list[float]] = {}
    for row in ledger:
        grade = grade_for(int(row["gw"]), [row])
        if grade is None or grade["delta_pts"] is None:
            continue
        reason = (notes.get(int(row["gw"])) or {}).get("reason") or NO_NOTE
        cells.setdefault(reason, []).append(float(grade["delta_pts"]))
    out = []
    for reason in (*REASONS, NO_NOTE):
        deltas = cells.get(reason)
        if deltas:
            out.append({"reason": reason, "count": len(deltas),
                        "mean_delta_pts": round(sum(deltas) / len(deltas), 1)})
    return out
```

- [ ] **Step 4: Schemas, router, app**

`schemas.py`, after `DigestPanel`:

```python
class DecisionGrade(BaseModel):
    lane: str = "transfers"
    label: str | None = None
    delta_pts: int | None = None


class DecisionNote(BaseModel):
    """v16 §5: one gameweek's deviation note and whether it may be edited."""

    gw: int
    reason: str | None = None
    text: str = ""
    at: str | None = None
    state: Literal["before_deadline", "open", "graded"] = "open"
    deadline: str | None = None
    grade: DecisionGrade | None = None


class DecisionWrite(BaseModel):
    reason: str
    text: str = ""
```

`src/gaffer/web/routers/decisions.py`:

```python
"""``GET`` and ``POST /api/decisions/{gw}`` — the deviation note (v16 §5).

GET is 404-free: an absent note is the empty shape with its state. POST
refuses in the settings endpoint's ``{constraint, error, players}`` shape.
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from gaffer.artifacts import upcoming_gw
from gaffer.decisions import (REASONS, TEXT_MAX, note_for, note_state,
                              save_note)
from gaffer.web.schemas import DecisionNote, DecisionWrite

router = APIRouter(prefix="/api", tags=["decisions"])


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _fail(constraint: str, error: str) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": []})


def _view(gw: int) -> DecisionNote:
    state, deadline, grade = note_state(gw, now=_now())
    return DecisionNote(**note_for(gw), state=state, deadline=deadline,
                        grade=grade)


@router.get("/decisions/{gw}", response_model=DecisionNote)
def decision(gw: int) -> DecisionNote:
    return _view(gw)


@router.post("/decisions/{gw}", response_model=DecisionNote)
def save(gw: int, req: DecisionWrite) -> DecisionNote:
    if req.reason not in REASONS:
        raise _fail("unknown_reason",
                    f"the reason is one of {', '.join(REASONS)}")
    if len(req.text or "") > TEXT_MAX:
        raise _fail("text_too_long", f"the note is at most {TEXT_MAX} characters")
    try:
        nxt = upcoming_gw()
    except Exception:  # noqa: BLE001 — no snapshot is no rule
        nxt = None
    if nxt is not None and int(gw) > int(nxt):
        raise _fail("future_gw", f"GW{gw} is past the next deadline (GW{nxt})")
    state, _, _ = note_state(gw, now=_now())
    if state == "before_deadline":
        raise _fail("not_open", f"GW{gw}'s note opens at the deadline")
    if state == "graded":
        raise _fail("graded", f"GW{gw} has been graded; the note is closed")
    save_note(gw, req.reason, req.text or "")
    return _view(gw)
```

`app.py`: add `decisions` to the `from gaffer.web.routers import (...)` list and `app.include_router(decisions.router)` after `confidence`.

- [ ] **Step 5: Regenerate types; run** `.venv/bin/pytest -q tests/test_v16_decisions.py tests/test_web_settings*.py tests/test_v12_w5_settings.py` — pass; `tests/test_v11_degradation.py` fails on `49` until the orchestrator moves it. Report DONE with that note.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/decisions.py src/gaffer/web/routers/decisions.py src/gaffer/web/schemas.py src/gaffer/web/app.py tests/test_v16_decisions.py frontend/src/schemas.json frontend/src/types.generated.ts
git commit -m "feat(v16): the deviation note — reports/decisions.json, GET/POST /api/decisions/{gw}, the deadline rule, the by-reason tally"
```

**Orchestrator, after the review:** `tests/test_v11_degradation.py` — `assert len(paths) == 49` → `50`, add `assert "/api/decisions/{gw}" in paths`, and the docstring paragraph `# v16 §5 (specs/2026-09-06-gaffer-v16-restraint-brief-design.md) 49 → 50, and the one is /api/decisions/{gw} — GET and POST share one path key — the deviation note.`; run `.venv/bin/pytest -q tests/test_v11_degradation.py tests/test_v12_w1_degradation.py tests/test_v12_w5_degradation.py`; commit `test(v16): route pin 49 → 50 (/api/decisions/{gw})`.

---

### Task 6: The note in Review — the lane line and the by-reason table

**Files:**
- Modify: `src/gaffer/web/schemas.py` (`DecisionRef`, `ReviewGw.decision`, `ReasonTally`, `ReviewSummary.by_reason`)
- Modify: `src/gaffer/web/routers/review.py`
- Modify: `frontend/src/hubs/model/ReviewTab.tsx` (+ test)
- Test: `tests/test_v16_review_notes.py` (new)
- Regenerate types.

- [ ] **Step 1: The failing tests**

```python
"""v16 §5 — the note beside the grade on /api/review, and the tally."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import REPORTS
from gaffer.web.app import create_app
from tests.test_web_review import ROW


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    REPORTS.mkdir()
    (REPORTS / "decision_ledger.json").write_text(json.dumps({"gws": [ROW]}))
    return TestClient(create_app(), raise_server_exceptions=False)


def test_a_note_rides_on_its_gameweek_and_the_tally_on_the_summary(client):
    (REPORTS / "decisions.json").write_text(json.dumps(
        {"2": {"gw": 2, "reason": "injury", "text": "Rice was out",
               "at": "2026-09-01T10:00:00+00:00"}}))
    body = client.get("/api/review").json()
    assert body["gws"][0]["decision"] == {"reason": "injury", "text": "Rice was out",
                                          "at": "2026-09-01T10:00:00+00:00"}
    assert body["summary"]["by_reason"] == [
        {"reason": "injury", "count": 1, "mean_delta_pts": -7.0}]


def test_no_note_is_null_and_counts_under_none(client):
    body = client.get("/api/review").json()
    assert body["gws"][0]["decision"] is None
    assert body["summary"]["by_reason"] == [
        {"reason": "none", "count": 1, "mean_delta_pts": -7.0}]


def test_an_empty_ledger_is_still_the_empty_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/review").json()
    assert body == {"gws": [], "summary": None}
```

- [ ] **Step 2: Run to see them fail** — `.venv/bin/pytest -q tests/test_v16_review_notes.py` → KeyError `decision`.

- [ ] **Step 3: Schemas and router**

`schemas.py`, before `class ReviewGw`:

```python
class DecisionRef(BaseModel):
    """The deviation note beside a grade (v16 §5)."""

    reason: str | None = None
    text: str = ""
    at: str | None = None


class ReasonTally(BaseModel):
    reason: str
    count: int
    mean_delta_pts: float | None = None
```

`ReviewGw` gains (after `notices`, or wherever its last field is) `decision: DecisionRef | None = None`; `ReviewSummary` gains `by_reason: list[ReasonTally] = Field(default_factory=list)`.

`routers/review.py`:

```python
from gaffer.decisions import by_reason, load_decisions
...
        ledger = load_ledger()
        if not ledger:
            return EMPTY
        notes = load_decisions()
        gws = [{**row, "decision": ({k: notes[int(row["gw"])][k]
                                     for k in ("reason", "text", "at")}
                                    if int(row["gw"]) in notes else None)}
               for row in ledger]
        summary = season_summary(ledger) or {}
        summary["by_reason"] = by_reason(ledger, notes)
        return Review(gws=gws, summary=summary)
```

- [ ] **Step 4: Regenerate types; run** `.venv/bin/pytest -q tests/test_v16_review_notes.py tests/test_web_review.py tests/test_v11_degradation.py -k "review"`.

- [ ] **Step 5: ReviewTab**

In `ReviewTab.tsx`:

```tsx
const REASON_LABEL: Record<string, string> = {
  injury: 'Injury', fixtures: 'Fixtures', eye_test: 'Eye test', price: 'Price',
  chip: 'Chip', rival: 'Rival', gut: 'Gut', other: 'Other', none: 'No note',
}
```

Inside `GwCard`, after the lanes `<div className="divide-y divide-divider">…</div>` (only when `!row.no_advice`), add:

```tsx
{row.decision?.reason && (
  <p data-testid={`decision-${row.gw}`}
     className="mt-1 flex flex-wrap items-baseline gap-2 text-sm text-text-muted">
    <span>You said:</span>
    <Chip>{REASON_LABEL[row.decision.reason] ?? row.decision.reason}</Chip>
    {row.decision.text && <span className="text-text-secondary">{row.decision.text}</span>}
  </p>
)}
```

In the "Season ledger" card, after the worst-decision paragraph:

```tsx
{data.summary.by_reason.length > 0 && (
  <div className="mt-3 overflow-x-auto" data-testid="by-reason">
    <p className="label mb-1">Deviations by reason</p>
    <table className={TABLE_CLASS}>
      <thead className={THEAD_CLASS}>
        <tr>
          <th className={thClass()}>Reason</th>
          <th className={thClass(true)}>GWs</th>
          <th className={thClass(true)}>Mean vs model</th>
        </tr>
      </thead>
      <tbody>
        {data.summary.by_reason.map((cell) => (
          <tr key={cell.reason} className={TR_CLASS}>
            <td className={tdClass()}>{REASON_LABEL[cell.reason] ?? cell.reason}</td>
            <td className={`${tdClass(true)} tn`}>{cell.count}</td>
            <td className={`${tdClass(true)} tn ${TONE_CLASS[toneOf(cell.mean_delta_pts)]}`}>
              {cell.mean_delta_pts === null ? '—' : `${fmtDelta(cell.mean_delta_pts, 1)} pts`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)}
```

Import `TABLE_CLASS, THEAD_CLASS, TR_CLASS, tdClass, thClass` from the kit. In `ReviewTab.test.tsx` add `decision: null` to the `DATA` row (the generated type now requires it), `by_reason: []` to the summary, and:

```tsx
it('shows the deviation note under the lanes and the by-reason table', async () => {
  mock({ ...DATA,
    gws: [{ ...DATA.gws[0], decision: { reason: 'injury', text: 'Rice was out', at: null } }],
    summary: { ...DATA.summary!, by_reason: [
      { reason: 'injury', count: 1, mean_delta_pts: -7 }] } })
  render(<ReviewTab />)
  const note = await screen.findByTestId('decision-2')
  expect(note).toHaveTextContent('Injury')
  expect(note).toHaveTextContent('Rice was out')
  const table = screen.getByTestId('by-reason')
  expect(within(table).getByText('Injury')).toBeInTheDocument()
  expect(table).toHaveTextContent('−7.0 pts')
})
```

(`fmtDelta` prints the minus sign the kit uses; if the assertion's sign character differs from the kit's, match the kit.)

- [ ] **Step 6: Run** `cd frontend && npx tsc --noEmit && npx vitest run src/hubs/model` — pass.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/review.py tests/test_v16_review_notes.py frontend/src/hubs/model/ReviewTab.tsx frontend/src/hubs/model/ReviewTab.test.tsx frontend/src/schemas.json frontend/src/types.generated.ts
git commit -m "feat(v16): the deviation note beside the grade in Review, and the by-reason tally"
```

---

### Task 7: The brief — facts, prompt, command, truth check, banking, routes, chain, CLI, Friday headline

**Files:**
- Create: `src/gaffer/brief.py`
- Create: `src/gaffer/web/routers/brief.py`
- Modify: `src/gaffer/web/schemas.py` (`BriefPanel`)
- Modify: `src/gaffer/web/app.py` (include the router)
- Modify: `src/gaffer/web/routers/advice.py` (chain after a successful web advise — plan R1)
- Modify: `src/gaffer/cli.py` (`brief` command — plan R9)
- Modify: `src/gaffer/digest.py` (`friday_briefing` headline)
- Test: `tests/test_v16_brief.py`, `tests/test_v16_web_brief.py` (new)
- **Orchestrator only:** `tests/test_v11_degradation.py` route pin 50 → 51 (`/api/brief`).
- Regenerate types.

**Context.** The classifier (`src/gaffer/data/news/classifier.py`) already runs `cfg.news_llm_command` (`claude -p --output-format json --disallowedTools …`) through `subprocess.run(shlex.split(cmd), input=prompt, capture_output=True, text=True, timeout=…, check=True)` and reads the `{"result": "..."}` envelope; its cache lives under `LLM_CACHE = Path("data/raw/news/llm")`. The brief reuses the command and the cache directory, with its own prompt version as the salt. The facts come from the advice payload (`artifacts.load_advice`), the ladder (`ladder.load_ladder`), the trace (`web.routers.plan.plan(gw)` — the one place the trace inputs are assembled), the ledger (`review.load_ledger`), the note (`decisions.note_for`) and the run stamp (`load_solve_state(gw).generated_at`).

- [ ] **Step 1: The failing unit tests** — `tests/test_v16_brief.py`

```python
"""v16 §6 — the brief: facts, the truth check, the command, the cache, the bank."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from gaffer import artifacts
from gaffer.brief import (BRIEF_PROMPT_VERSION, build_facts, build_prompt,
                          cache_key, check_brief, extract_text, fact_names,
                          fact_numbers, first_sentence, load_brief,
                          run_brief)

FACTS = {
    "gw": 4, "horizon": [4, 5, 6], "expected_pts": 61.2, "hits": 0, "hit_points": 0,
    "restraint": {"chosen_label": "free transfers only", "bar_pct": 60,
                  "steps": [{"below_label": "bank", "above_label": "free transfers only",
                             "share_pct": 79, "taken": True, "reason": "expected points alone"},
                            {"below_label": "free transfers only", "above_label": "1 hit",
                             "share_pct": 46, "taken": False,
                             "reason": "Rice is 0% to play"}]},
    "moves": [{"in": "Gibbs-White", "out": "B.Fernandes", "gain": 3.1, "sims_pct": 70}],
    "captain": {"name": "Guéhi", "sims_pct": 55, "note": None},
    "league": {"name": "Shocky Supplies", "stance": "chase", "manual": False,
               "gap": 44, "lam": 0.13, "rival": "palm it down"},
    "chip": None,
    "last_week": {"gw": 3, "you": 61, "model": 68,
                  "lanes": [{"lane": "transfers", "label": "Blunder", "delta_pts": -7}],
                  "note": {"reason": "gut", "text": "fancied Isak"}},
    "data_warning": None,
    "objective": {"agrees": False, "hits": 1,
                  "moves": [{"in": "Gibbs-White", "out": "B.Fernandes"},
                            {"in": "Isak", "out": "Rice"}]},
}


def test_the_numbers_of_the_facts_in_the_forms_the_prose_may_use():
    nums = fact_numbers(FACTS)
    for want in ("4", "5", "6", "61.2", "60", "79", "46", "3.1", "70", "55", "44",
                 "0.13", "61", "68", "-7", "7", "3", "0", "1"):
        assert want in nums, want
    assert "62" not in nums and "0.6" not in nums


def test_the_names_of_the_facts_include_every_token_of_a_name():
    names = fact_names(FACTS)
    for want in ("Gibbs-White", "B.Fernandes", "Guéhi", "Isak", "Rice", "Shocky",
                 "Supplies", "Shocky Supplies", "palm", "down"):
        assert want in names, want


def test_a_true_brief_passes():
    prose = ("The ladder chose free transfers only at a bar of 60%, taking the step "
             "from the bank at 79% and refusing the step to 1 hit at 46% because "
             "Rice is 0% to play. That brings Gibbs-White in for B.Fernandes, "
             "worth 3.1 points over the horizon and made in 70% of the sims. "
             "The armband stays on Guéhi, the sweep's pick in 55% of sims. In "
             "Shocky Supplies you are chasing, 44 behind palm it down, with the "
             "tilt at 0.13. Last week you scored 61 against the model's 68, and "
             "you said the transfers were gut: fancied Isak.")
    assert check_brief(prose, FACTS) == []


def test_a_foreign_number_fails_and_names_the_sentence():
    prose = "The step to 1 hit was refused at 52%. Guéhi keeps the armband."
    offences = check_brief(prose, FACTS)
    assert offences == ["number 52 is not in the facts: The step to 1 hit was refused at 52%."]


def test_a_foreign_name_fails():
    offences = check_brief("This week Haaland is the obvious captain.", FACTS)
    assert offences == ["name Haaland is not in the facts: This week Haaland is the obvious captain."]


def test_sentence_starts_and_the_allow_list_are_exempt():
    prose = "Friday is the deadline. GW4 is a British week. The XI is set, I think."
    assert check_brief(prose, FACTS) == []


def test_a_possessive_and_a_trailing_unit_are_stripped():
    assert check_brief("Guéhi's 55% is solid; 3.1 pts is the gain.", FACTS) == []


def test_first_sentence():
    assert first_sentence("One. Two? Three!") == "One."
    assert first_sentence("  Only one  ") == "Only one"


def test_the_prompt_carries_the_facts_and_the_rules():
    prompt = build_prompt(FACTS)
    assert '"Gibbs-White"' in prompt
    assert "British English" in prompt and "no headings" in prompt.lower()
    assert "never name a club" in prompt.lower()
    assert "do not start a sentence with a player's name" in prompt.lower()


def test_extract_text_reads_the_envelope_a_string_or_plain_text():
    assert extract_text(json.dumps({"result": "The brief."})) == "The brief."
    assert extract_text(json.dumps("The brief.")) == "The brief."
    assert extract_text("The brief.\n") == "The brief."


def test_the_cache_key_is_salted_by_the_prompt_version():
    assert BRIEF_PROMPT_VERSION == 1
    assert cache_key("2026-09-05T09:00:00", 1) != cache_key("2026-09-05T09:00:00", 2)
    assert cache_key("a", 1) == cache_key("a", 1)


# --- run_brief on real-shaped artifacts ---------------------------------------

def _fake(tmp_path: Path, text: str, exit_code: int = 0, sleep: float = 0.0) -> str:
    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys, time, json\n"
        "sys.stdin.read()\n"
        f"time.sleep({sleep})\n"
        f"sys.stdout.write(json.dumps({{'result': {text!r}}}))\n"
        f"sys.exit({exit_code})\n", encoding="utf-8")
    return f"{sys.executable} {script}"


@pytest.fixture()
def artifacts_on_disk(tmp_path, monkeypatch):
    """A GW4 advice, ladder and solve state of the real shape, no trace."""
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    ref = lambda c, n: {"code": c, "name": n, "position": "MID", "ep": 5.0}  # noqa: E731
    (artifacts.REPORTS / "gw4-advice.json").write_text(json.dumps({
        "gw": 4, "deadline": "2026-09-11T17:30:00Z", "hits": 0, "expected_pts": 61.2,
        "buys": [ref(1, "Gibbs-White")], "sells": [ref(2, "B.Fernandes")],
        "captain": ref(3, "Guéhi"), "vice": ref(4, "Semenyo"), "xi": [], "bench": [],
        "move_frequencies": [{"kind": "buy", "code": 1, "gw": 4, "frequency": 0.7}],
        "scenarios": {"captain_frequency": 0.55}, "captain_note": None,
        "strategy": {"lam": 0.1326, "gap": 44, "stance": "chase", "rival_name": "palm it down",
                     "source": "auto"},
        "chip_table": [], "data_warning": None,
        "objective": {"buys": [ref(1, "Gibbs-White"), ref(5, "Isak")],
                      "sells": [ref(2, "B.Fernandes"), ref(6, "Rice")], "hits": 1,
                      "expected_pts": 63.0},
        "restraint": {"chosen": "hits0", "bar": 0.6, "agrees": False, "note": "x",
                      "steps": [{"below": "bank", "above": "hits0", "share": 0.7875,
                                 "taken": True, "reason": "expected points alone",
                                 "reason_kind": "points"},
                                {"below": "hits0", "above": "hits1", "share": 0.46,
                                 "taken": False, "reason": "Rice is 0% to play",
                                 "reason_kind": "flagged"}]}}))
    (artifacts.REPORTS / "ladder_gw4.json").write_text(json.dumps(
        {"gw": 4, "gws": [4, 5, 6], "chosen": "hits0", "bar": 0.6, "rungs": []}))
    monkeypatch.setattr("gaffer.brief.run_stamp", lambda gw: "2026-09-05T09:00:00")
    monkeypatch.setattr("gaffer.brief.move_gains", lambda gw: {1: 3.1})
    monkeypatch.setattr("gaffer.brief.latest_gw", lambda: 4)
    return tmp_path


TRUE = ("The ladder chose free transfers only at a bar of 60%, taking the step from "
        "the bank at 79% and refusing 1 hit at 46% because Rice is 0% to play. "
        "That brings Gibbs-White in for B.Fernandes, worth 3.1 points and made in "
        "70% of sims. The armband stays on Guéhi at 55%. In the league you are "
        "chasing, 44 behind palm it down, tilt 0.13. Expect 61.2 points.")


def test_build_facts_has_the_spec_shape_and_rounding(artifacts_on_disk):
    facts = build_facts(4)
    assert facts["gw"] == 4 and facts["horizon"] == [4, 5, 6]
    assert facts["restraint"]["chosen_label"] == "free transfers only"
    assert facts["restraint"]["bar_pct"] == 60
    assert facts["restraint"]["steps"][0]["share_pct"] == 79
    assert facts["moves"] == [{"in": "Gibbs-White", "out": "B.Fernandes", "gain": 3.1,
                               "sims_pct": 70}]
    assert facts["captain"] == {"name": "Guéhi", "sims_pct": 55, "note": None}
    assert facts["league"]["lam"] == 0.13 and facts["league"]["manual"] is False
    assert facts["objective"]["hits"] == 1 and facts["objective"]["agrees"] is False
    assert facts["last_week"] is None and facts["chip"] is None


def test_a_passing_brief_is_banked_and_the_line_printed(artifacts_on_disk, capsys):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, TRUE),
                         "news_llm_timeout_s": 10})()
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is True and out["note"] is None
    banked = load_brief(4)
    assert banked["prose"] == TRUE and banked["gw"] == 4
    assert banked["prompt_version"] == 1 and banked["run_stamp"] == "2026-09-05T09:00:00"
    assert banked["facts"]["gw"] == 4 and banked["checked_at"]
    assert "Brief GW4: The ladder chose" in capsys.readouterr().out


def test_a_failing_check_writes_nothing_and_leaves_a_note(artifacts_on_disk, capsys):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, "Haaland scores 99."),
                         "news_llm_timeout_s": 10})()
    (artifacts.REPORTS / "brief_gw4.json").write_text("{}")   # a stale one
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is False
    assert "did not pass its check" in out["note"]
    assert not (artifacts.REPORTS / "brief_gw4.json").exists()
    note = json.loads((artifacts.REPORTS / "brief_note.json").read_text())
    assert note["gw"] == 4 and "did not pass" in note["note"]
    assert "Haaland" in capsys.readouterr().out


@pytest.mark.parametrize("kw", [{"exit_code": 3}, {"sleep": 5}])
def test_a_dead_command_is_a_note_not_an_error(artifacts_on_disk, kw):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, TRUE, **kw),
                         "news_llm_timeout_s": 1})()
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is False and "brief not written" in out["note"]


def test_a_missing_command_is_a_note(artifacts_on_disk):
    cfg = type("C", (), {"news_llm_command": "", "news_llm_timeout_s": 1})()
    out = run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is False and "no llm_command" in out["note"]


def test_the_cache_answers_the_second_run_without_the_command(artifacts_on_disk):
    cfg = type("C", (), {"news_llm_command": _fake(artifacts_on_disk, TRUE),
                         "news_llm_timeout_s": 10})()
    run_brief(4, cfg=cfg, cache_dir=artifacts_on_disk / "cache")
    dead = type("C", (), {"news_llm_command": "/nonexistent/claude",
                          "news_llm_timeout_s": 10})()
    out = run_brief(4, cfg=dead, cache_dir=artifacts_on_disk / "cache")
    assert out["written"] is True


def test_no_advice_on_disk_is_a_note(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.brief.latest_gw", lambda: None)
    out = run_brief(None)
    assert out["written"] is False and "no advice" in out["note"]
```

- [ ] **Step 2: Run to see them fail** — `.venv/bin/pytest -q tests/test_v16_brief.py` → ModuleNotFoundError.

- [ ] **Step 3: `src/gaffer/brief.py`**

```python
"""The brief (v16 §6): the week, written by an LLM from a facts document
and checked mechanically before it is banked.

Three properties make this safe to serve:

*Facts first.* :func:`build_facts` gathers everything the prose may say —
the rung, the steps, the moves with the trace's gain and the sweep's
frequency, the captain, the league, a chip, last week's grade and note, a
data warning — rounded to the precision the UI shows (plan R13).

*The classifier's command.* ``cfg.news_llm_command`` is the same no-tools
``claude -p`` the presser classifier runs; the prompt says "from these facts
only". The reply is cached by the advice run's stamp and the prompt
version, so a page rebuild never re-asks.

*The truth check.* Every number and every name in the prose has to be in
the facts (:func:`check_brief`). A failure bans the brief: nothing is
banked, the stale one is removed, the card falls back to the digest with
a note. A dead command is the same event with a different note.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
from gaffer.artifacts import latest_gw, load_advice, load_solve_state
from gaffer.data.news.classifier import LLM_CACHE
from gaffer.io import atomic_write
from gaffer.ladder import load_ladder, rung_label

BRIEF_PROMPT_VERSION = 1
"""Bumped whenever :func:`build_prompt` changes; salts the cache key."""

BRIEF_CACHE = LLM_CACHE / "brief"

NOTE_FILE = "brief_note.json"
"""Why there is no brief for the newest gameweek, for the card."""

ALLOW = frozenset({
    "GW", "FPL", "XI", "I", "British", "Premier", "League", "Bank", "Free",
    "Hit", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday", "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
})
"""Capitalised tokens that are never a name (plan R8)."""

_NUMBER = re.compile(r"[-+−]?\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_POSSESSIVE = re.compile(r"[’']s$")
_STRIP = ".,;:!?()\"'“”‘’%"


def brief_path(gw: int) -> Path:
    return artifacts.REPORTS / f"brief_gw{int(gw)}.json"


def note_path() -> Path:
    return artifacts.REPORTS / NOTE_FILE


def load_brief(gw: int) -> dict | None:
    path = brief_path(gw)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) and payload.get("prose") else None
    except Exception as exc:  # noqa: BLE001 — a corrupt brief is no brief
        print(f"brief GW{gw} unreadable: {exc}")
        return None


def load_note() -> dict | None:
    try:
        return json.loads(note_path().read_text()) if note_path().exists() else None
    except Exception:  # noqa: BLE001
        return None


def first_sentence(prose: str) -> str:
    return _SENTENCE.split(str(prose or "").strip(), maxsplit=1)[0].strip()


# --- the facts --------------------------------------------------------------

def run_stamp(gw: int) -> str:
    """The advice run's own stamp, off the solve state."""
    return str(load_solve_state(gw).generated_at)


def move_gains(gw: int) -> dict[int, float]:
    """``{buy code: decayed gain}`` off the plan trace, or ``{}``."""
    try:
        from gaffer.web.routers.plan import plan as plan_timeline
        week = plan_timeline(gw).weeks[0]
        if week.trace is None:
            return {}
        return {int(m.buy_code): float(m.ep_gain) for m in week.trace.moves
                if m.buy_code is not None and m.ep_gain is not None}
    except Exception as exc:  # noqa: BLE001 — a gain is decoration
        print(f"brief: no trace gains ({exc})")
        return {}


def _pct(value) -> int | None:
    return None if value is None else int(round(float(value) * 100))


def _last_week(gw: int) -> dict | None:
    from gaffer.decisions import note_for
    from gaffer.review import load_ledger

    rows = [r for r in load_ledger() if int(r.get("gw", -1)) < int(gw)]
    if not rows:
        return None
    row = max(rows, key=lambda r: int(r["gw"]))
    note = note_for(int(row["gw"]))
    return {"gw": int(row["gw"]), "you": row.get("my_points"),
            "model": row.get("model_points"),
            "lanes": [{"lane": ln.get("lane"), "label": ln.get("label"),
                       "delta_pts": ln.get("delta_pts")}
                      for ln in row.get("lanes") or [] if ln.get("delta_pts") is not None],
            "note": ({"reason": note["reason"], "text": note["text"]}
                     if note.get("reason") else None)}


def build_facts(gw: int) -> dict:
    """Everything the prose may say, rounded as the UI rounds (§6.2)."""
    advice = load_advice(gw)
    ladder = load_ladder(gw) or {}
    gains = move_gains(gw)
    freq = {(str(r.get("kind")), int(r.get("code"))): float(r.get("frequency"))
            for r in advice.get("move_frequencies") or []
            if r.get("code") is not None and r.get("frequency") is not None}
    restraint = advice.get("restraint") or {}
    steps = [{"below_label": rung_label(s["below"]), "above_label": rung_label(s["above"]),
              "share_pct": _pct(s.get("share")), "taken": bool(s.get("taken")),
              "reason": s.get("reason") or ""}
             for s in restraint.get("steps") or []]
    buys, sells = advice.get("buys") or [], advice.get("sells") or []
    moves = [{"in": b["name"], "out": (sells[i]["name"] if i < len(sells) else None),
              "gain": (None if gains.get(int(b["code"])) is None
                       else round(gains[int(b["code"])], 1)),
              "sims_pct": _pct(freq.get(("buy", int(b["code"]))))}
             for i, b in enumerate(buys)]
    strat = advice.get("strategy") or None
    league = None
    if strat:
        league = {"name": _focus_name(), "stance": strat.get("stance"),
                  "manual": strat.get("source") == "manual",
                  "gap": (None if strat.get("gap") is None else int(round(abs(float(strat["gap"]))))),
                  "lam": (None if strat.get("lam") is None else round(float(strat["lam"]), 2)),
                  "rival": strat.get("rival_name")}
    chip = next(({"chip": r.get("chip"), "gw": int(r["gw"]),
                  "gain": round(float(r.get("gain") or 0), 1),
                  "threshold": (None if r.get("threshold") is None
                                else round(float(r["threshold"]), 1))}
                 for r in advice.get("chip_table") or [] if r.get("play_now")), None)
    objective = advice.get("objective") or None
    obj = None
    if objective is not None:
        osells = objective.get("sells") or []
        obj = {"agrees": bool(restraint.get("agrees", True)),
               "hits": int(objective.get("hits") or 0),
               "moves": [{"in": b["name"],
                          "out": osells[i]["name"] if i < len(osells) else None}
                         for i, b in enumerate(objective.get("buys") or [])]}
    hits = int(advice.get("hits") or 0)
    return {
        "gw": int(gw), "horizon": [int(g) for g in ladder.get("gws") or [int(gw)]],
        "expected_pts": (None if advice.get("expected_pts") is None
                         else round(float(advice["expected_pts"]), 1)),
        "hits": hits, "hit_points": hits * 4,
        "restraint": {"chosen_label": rung_label(str(restraint.get("chosen") or "bank")),
                      "bar_pct": _pct(restraint.get("bar")), "steps": steps},
        "moves": moves,
        "captain": {"name": (advice.get("captain") or {}).get("name"),
                    "sims_pct": _pct((advice.get("scenarios") or {}).get("captain_frequency")),
                    "note": advice.get("captain_note") or None},
        "league": league, "chip": chip, "last_week": _last_week(gw),
        "data_warning": advice.get("data_warning") or None, "objective": obj,
    }


def _focus_name() -> str | None:
    try:
        from gaffer.web.routers.league import _league_rows  # the overview's cache
        from gaffer.config import serving_config
        cfg = serving_config()
        for row in _league_rows(cfg) or []:
            if int(row.get("id", -1)) == int(cfg.league_id):
                return str(row.get("name"))
    except Exception:  # noqa: BLE001 — a name is decoration
        pass
    return None
```

**Note for the implementer:** `_focus_name` above is a sketch — open `src/gaffer/web/routers/league.py`, find how the overview names the focus league (`LeaguesOverview.focus_name` is built from the cached `_league_rows`), and call whatever the smallest existing reader is. If nothing small exists, return `None` and the prose says "your league" — do not add a network call.

```python
# --- the prompt and the command ------------------------------------------

def build_prompt(facts: dict) -> str:
    return "\n".join([
        "You are writing this week's Fantasy Premier League brief for one "
        "manager, from the facts below and nothing else.",
        "",
        "Rules:",
        "- British English. Six to twelve sentences of plain prose in one or "
        "two paragraphs. No headings, no bullet points, no numbered lists.",
        "- Use only numbers that appear in the facts, written exactly as they "
        "appear: a share as a whole percent such as 46%, points to one decimal.",
        "- Name only the players, the league and the rival named in the facts. "
        "Never name a club. Do not start a sentence with a player's name.",
        "- Do not invent a fact, a reason or a caveat. If a field is null, "
        "leave it out.",
        "",
        "Say, in this order: which rung the ladder chose and every step, taken "
        "or refused, with its share and reason; each move with its gain and "
        "its sims share; the captain, his sims share and any note; the league "
        "(name, stance, whether it was set by hand, the gap and the tilt); a "
        "chip if there is one; last week's grade per lane and the manager's "
        "own note, quoted; any data warning. When objective.agrees is false, "
        "say in one sentence what the objective wanted instead.",
        "",
        "Facts (JSON):",
        json.dumps(facts, ensure_ascii=False, indent=1),
        "",
        "Reply with the brief only.",
    ])


def extract_text(stdout: str) -> str:
    """The model's text out of ``claude -p --output-format json``'s envelope,
    a JSON string, or plain text."""
    raw = str(stdout or "").strip()
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(payload, dict):
        return str(payload.get("result") or "").strip()
    if isinstance(payload, str):
        return payload.strip()
    return raw


def run_command(cmd: str, prompt: str, timeout_s: int) -> str:
    """One call. Raises on a non-zero exit, a timeout or an empty reply."""
    proc = subprocess.run(shlex.split(cmd), input=prompt, capture_output=True,
                          text=True, timeout=timeout_s, check=True)
    text = extract_text(proc.stdout)
    if not text:
        raise ValueError("the command returned no text")
    return text


def cache_key(stamp: str, version: int = BRIEF_PROMPT_VERSION) -> str:
    return hashlib.sha256(f"{version}\x00{stamp}".encode("utf-8")).hexdigest()[:16]


# --- the truth check ---------------------------------------------------------

def _leaves(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _leaves(v)
    else:
        yield node


def fact_numbers(facts: dict) -> set[str]:
    """Every number in the facts, in the forms the prose may write it."""
    out: set[str] = set()
    for leaf in _leaves(facts):
        if isinstance(leaf, bool) or not isinstance(leaf, (int, float)):
            continue
        forms = {str(leaf)}
        if isinstance(leaf, float):
            forms |= {f"{leaf:.1f}", f"{leaf:.2f}", f"{leaf:g}"}
            if leaf.is_integer():
                forms.add(str(int(leaf)))
        out |= forms
        out |= {f.lstrip("-") for f in forms}
    return out


def fact_names(facts: dict) -> set[str]:
    """Every name string, whole and token by token (``"Shocky Supplies"``,
    ``"Shocky"``, ``"Supplies"``; a hyphenated name stays whole)."""
    out: set[str] = set()

    def take(value):
        if isinstance(value, str) and value:
            out.add(value)
            out.update(value.split())

    for node in _walk(facts):
        if isinstance(node, dict):
            for k in ("in", "out", "name", "rival"):
                take(node.get(k))
    return out


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def check_brief(prose: str, facts: dict) -> list[str]:
    """The offences, one string each; ``[]`` is a pass (§6.4, plan R8)."""
    numbers, names = fact_numbers(facts), fact_names(facts)
    offences: list[str] = []
    for sentence in _SENTENCE.split(str(prose or "").strip()):
        if not sentence:
            continue
        for tok in _NUMBER.findall(sentence):
            norm = tok.replace("−", "-").replace(",", ".").lstrip("+")
            if norm not in numbers and norm.lstrip("-") not in numbers:
                offences.append(f"number {norm} is not in the facts: {sentence}")
        for i, word in enumerate(sentence.split()):
            clean = _POSSESSIVE.sub("", word.strip(_STRIP))
            if i == 0 or not clean or not clean[0].isupper():
                continue
            if clean in ALLOW or re.fullmatch(r"GW\d+", clean):
                continue
            if clean not in names:
                offences.append(f"name {clean} is not in the facts: {sentence}")
    return offences


# --- the run ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bank_note(gw: int | None, note: str) -> None:
    try:
        artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
        atomic_write(note_path(), json.dumps({"gw": gw, "note": note, "at": _now()}))
    except Exception as exc:  # noqa: BLE001
        print(f"brief note not written: {exc}")


def run_brief(gw: int | None = None, *, cfg=None,
              cache_dir: Path = BRIEF_CACHE) -> dict:
    """Build, check and bank the brief. Never raises.

    Returns ``{"gw", "written", "note", "path"}``. A dead command, a timeout,
    a failed check and a missing advice are all ``written: False`` with a
    note — a finished job, not a failed one (§6.5).
    """
    try:
        gw = latest_gw() if gw is None else int(gw)
    except Exception:  # noqa: BLE001
        gw = None
    if gw is None:
        note = "no advice on disk — run `gaffer advise` first"
        print(f"brief not written: {note}")
        return {"gw": None, "written": False, "note": note, "path": None}
    if cfg is None:
        from gaffer.config import serving_config
        cfg = serving_config()
    cmd = str(getattr(cfg, "news_llm_command", "") or "").strip()
    if not cmd:
        note = "no llm_command configured under [news]"
        _bank_note(gw, note)
        return {"gw": gw, "written": False, "note": note, "path": None}
    try:
        facts = build_facts(gw)
        stamp = run_stamp(gw)
    except Exception as exc:  # noqa: BLE001
        note = f"brief not written: the facts could not be built ({exc})"
        print(note)
        _bank_note(gw, note)
        return {"gw": gw, "written": False, "note": note, "path": None}
    key = cache_key(stamp)
    cache_dir = Path(cache_dir)
    cached = cache_dir / f"{key}.json"
    prose = None
    if cached.is_file():
        try:
            prose = json.loads(cached.read_text(encoding="utf-8")).get("prose")
        except Exception:  # noqa: BLE001 — a corrupt entry is a miss
            prose = None
    if not prose:
        try:
            prose = run_command(cmd, build_prompt(facts),
                                int(getattr(cfg, "news_llm_timeout_s", 300)))
        except Exception as exc:  # noqa: BLE001 — the brief never blocks
            note = f"brief not written: the command did not answer ({exc})"
            print(note)
            _bank_note(gw, note)
            return {"gw": gw, "written": False, "note": note, "path": None}
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps({"prose": prose, "model": shlex.split(cmd)[0],
                                          "at": _now()}), encoding="utf-8")
        except Exception:  # noqa: BLE001 — an unwritable cache is not an outage
            pass
    offences = check_brief(prose, facts)
    if offences:
        for line in offences:
            print(f"brief check: {line}")
        note = f"the brief did not pass its check this week ({offences[0]})"
        brief_path(gw).unlink(missing_ok=True)
        _bank_note(gw, note)
        return {"gw": gw, "written": False, "note": note, "path": None}
    payload = {"gw": gw, "run_stamp": stamp, "prose": prose, "facts": facts,
               "model_command": shlex.split(cmd)[0], "prompt_version": BRIEF_PROMPT_VERSION,
               "checked_at": _now()}
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    atomic_write(brief_path(gw), json.dumps(payload, indent=1, ensure_ascii=False))
    note_path().unlink(missing_ok=True)
    print(f"Brief GW{gw}: {first_sentence(prose)}")
    return {"gw": gw, "written": True, "note": None, "path": str(brief_path(gw))}


def latest_brief() -> dict | None:
    """The newest banked brief by gameweek, or ``None``."""
    try:
        paths = sorted(artifacts.REPORTS.glob("brief_gw*.json"),
                       key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    except Exception:  # noqa: BLE001
        return None
    for path in reversed(paths):
        payload = load_brief(int(re.sub(r"\D", "", path.stem) or 0))
        if payload is not None:
            return payload
    return None
```

Run the unit tests until green.

- [ ] **Step 4: The web tests** — `tests/test_v16_web_brief.py`

```python
"""v16 §6.5 — GET /api/brief, POST /api/brief (an anonymous job, plan R1),
the chain after a web advise, the Friday headline."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.web.app import create_app

BRIEF = {"gw": 4, "run_stamp": "s", "prose": "One sentence. Two.", "facts": {"gw": 4},
         "model_command": "claude", "prompt_version": 1, "checked_at": "2026-09-05T09:00:00+00:00"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    return TestClient(create_app())


def test_no_brief_is_the_fallback_digest_panel_with_no_note(client):
    body = client.get("/api/brief").json()
    assert body["prose"] is None and body["gw"] is None
    assert body["fallback"] == {"available": False, "digest": None}
    assert body["note"] is None


def test_the_newest_brief_is_served(client):
    (artifacts.REPORTS / "brief_gw3.json").write_text(json.dumps({**BRIEF, "gw": 3}))
    (artifacts.REPORTS / "brief_gw4.json").write_text(json.dumps(BRIEF))
    body = client.get("/api/brief").json()
    assert body["gw"] == 4 and body["prose"] == "One sentence. Two."
    assert body["checked_at"] == BRIEF["checked_at"] and body["fallback"] is None


def test_a_banked_failure_note_reaches_the_fallback(client):
    (artifacts.REPORTS / "brief_note.json").write_text(json.dumps(
        {"gw": 4, "note": "the brief did not pass its check this week (x)", "at": "t"}))
    body = client.get("/api/brief").json()
    assert body["prose"] is None and "did not pass" in body["note"]


def test_post_submits_an_anonymous_job_and_the_result_is_the_run_dict(client, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.brief.run_brief",
                        lambda: {"gw": 4, "written": False, "note": "n", "path": None})
    resp = client.post("/api/brief")
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    for _ in range(4000):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
    assert job["status"] == "done" and job["result"]["note"] == "n"


def test_the_web_advise_body_chains_the_brief_on_success(monkeypatch):
    from types import SimpleNamespace

    from gaffer.web.routers import advice as advice_router

    calls = []
    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.config.load_config", lambda: SimpleNamespace())
    monkeypatch.setattr("gaffer.advise.run_advise",
                        lambda cfg: SimpleNamespace(gw=4, expected_pts=60.0))
    monkeypatch.setattr("gaffer.report.render.render_report", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)
    monkeypatch.setattr("gaffer.brief.run_brief",
                        lambda gw: calls.append(gw) or {"gw": gw, "written": True,
                                                         "note": None, "path": "p"})
    out = advice_router.run_train_and_advise()
    assert calls == [4] and out["brief"]["written"] is True


def test_the_chain_does_not_fire_when_advise_fails(monkeypatch):
    from gaffer.web.routers import advice as advice_router

    calls = []
    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.config.load_config", lambda: None)

    def boom(cfg):
        raise RuntimeError("no models")
    monkeypatch.setattr("gaffer.advise.run_advise", boom)
    monkeypatch.setattr("gaffer.brief.run_brief", lambda gw: calls.append(gw))
    with pytest.raises(RuntimeError):
        advice_router.run_train_and_advise()
    assert calls == []


def test_a_brief_that_raises_does_not_fail_the_advise_job(monkeypatch):
    from types import SimpleNamespace

    from gaffer.web.routers import advice as advice_router

    monkeypatch.setattr("gaffer.models.train.load_training_frame", lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.config.load_config", lambda: None)
    monkeypatch.setattr("gaffer.advise.run_advise",
                        lambda cfg: SimpleNamespace(gw=4, expected_pts=60.0))
    monkeypatch.setattr("gaffer.report.render.render_report", lambda *a, **k: None)
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)

    def boom(gw):
        raise RuntimeError("import failed")
    monkeypatch.setattr("gaffer.brief.run_brief", boom)
    out = advice_router.run_train_and_advise()
    assert out["gw"] == 4 and "import failed" in out["brief"]["note"]


def test_the_friday_headline_is_the_briefs_first_sentence(tmp_path, monkeypatch):
    from tests.test_digest import ADVICE, EVENTS, GW  # noqa: F401 — the fixture shapes
    from gaffer.digest import friday_briefing

    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    (artifacts.REPORTS / f"gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    (artifacts.REPORTS / f"brief_gw{GW}.json").write_text(json.dumps(
        {**BRIEF, "gw": GW, "prose": "The ladder chose the bank. More."}))
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: GW)
    monkeypatch.setattr("gaffer.digest.upcoming_gw", lambda: GW)
    out = friday_briefing()
    assert out["headline"] == "The ladder chose the bank."


def test_the_cli_brief_command_prints_the_note_and_never_raises(monkeypatch):
    from typer.testing import CliRunner

    from gaffer.cli import app

    monkeypatch.setattr("gaffer.brief.run_brief",
                        lambda: {"gw": 4, "written": False, "note": "no advice", "path": None})
    out = CliRunner().invoke(app, ["brief"])
    assert out.exit_code == 0 and "no advice" in out.output
```

If `tests/test_digest.py`'s `friday_briefing` needs more monkeypatching than the two names above (it reads several snapshots), copy exactly the patching its own `test_friday_*` tests use — open that file and follow it.

- [ ] **Step 5: Schema, router, app, chain, CLI, headline**

`schemas.py`, after `DigestPanel`:

```python
class BriefPanel(BaseModel):
    """The newest brief, or the digest to fall back on (v16 §6.5)."""

    gw: int | None = None
    prose: str | None = None
    checked_at: str | None = None
    run_stamp: str | None = None
    model_command: str | None = None
    note: str | None = None
    """Why there is no brief for the newest gameweek, when there is none."""
    fallback: DigestPanel | None = None
```

`src/gaffer/web/routers/brief.py`:

```python
"""``GET /api/brief`` — the newest brief or the digest panel to fall back on;
``POST /api/brief`` — write one now, as an anonymous job (plan R1: no
thirteenth ``JOB_KINDS`` entry, exactly as ``/api/ladder`` rebuilds)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gaffer.brief import latest_brief, load_note, run_brief
from gaffer.web.jobs import JobQueueFull
from gaffer.web.routers.digest import digest as digest_panel
from gaffer.web.schemas import BriefPanel, JobAccepted

router = APIRouter(prefix="/api", tags=["brief"])

BRIEF_TIMEOUT_MARGIN_S = 60.0


@router.get("/brief", response_model=BriefPanel)
def brief() -> BriefPanel:
    payload = latest_brief()
    if payload is not None:
        return BriefPanel(gw=payload.get("gw"), prose=payload.get("prose"),
                          checked_at=payload.get("checked_at"),
                          run_stamp=payload.get("run_stamp"),
                          model_command=payload.get("model_command"))
    note = load_note() or {}
    return BriefPanel(note=note.get("note"), fallback=digest_panel())


@router.post("/brief", status_code=202, response_model=JobAccepted)
def write(request: Request):
    from gaffer.config import serving_config

    timeout = float(serving_config().news_llm_timeout_s) + BRIEF_TIMEOUT_MARGIN_S
    try:
        job_id = request.app.state.jobs.submit(lambda: run_brief(), timeout_s=timeout)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
```

`app.py`: import `brief` in the routers tuple and `app.include_router(brief.router)` after `assets`.

`routers/advice.py::run_train_and_advise` — replace the last two lines with:

```python
    advice = run_advise(cfg if cfg is not None else load_config())
    render_report(advice, model_health=latest_health())
    # v16 §6.5 (plan R1): the brief is chained here, in the web job's body —
    # never inside ``run_advise`` — and never fails the run.
    try:
        from gaffer.brief import run_brief

        brief = run_brief(advice.gw)
    except Exception as exc:  # noqa: BLE001
        brief = {"gw": advice.gw, "written": False,
                 "note": f"brief not written: {exc}", "path": None}
        print(brief["note"])
    return {"gw": advice.gw, "expected_pts": advice.expected_pts, "brief": brief}
```

`cli.py`, after the `digest` command:

```python
@app.command()
def brief():
    """Write this week's brief from the banked advice (v16 §6).

    The same body the web button and the advise job run. Never fails: a
    dead LLM command or a brief that did not pass its check is one printed
    line, and the card falls back to the digest.
    """
    try:
        from gaffer.brief import run_brief

        out = run_brief()
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        typer.echo(f"brief not written: {exc}")
        return
    if out.get("note"):
        typer.echo(out["note"])
```

Add `"brief"` to `tests/test_cli.py`'s two command lists (the `--help` render loop) — that file is not protected.

`digest.py::friday_briefing`, directly after the `headline = ...` `if/else`:

```python
    # v16 §6.5: the brief's first sentence is the headline when one exists.
    try:
        from gaffer.brief import first_sentence, load_brief

        banked = load_brief(gw) if gw is not None else None
        if banked and banked.get("prose"):
            headline = first_sentence(banked["prose"])
    except Exception as exc:  # noqa: BLE001 — a headline is decoration
        print(f"digest: no brief headline ({exc})")
```

- [ ] **Step 6: Regenerate types; run** `.venv/bin/pytest -q tests/test_v16_brief.py tests/test_v16_web_brief.py tests/test_digest.py tests/test_web_digest.py tests/test_web_job_kinds*.py tests/test_cli.py tests/test_classifier.py` then the whole Python suite `.venv/bin/pytest -q`. Everything passes except `tests/test_v11_degradation.py`'s route pin at `50` — report DONE with that note.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/brief.py src/gaffer/web/routers/brief.py src/gaffer/web/schemas.py src/gaffer/web/app.py src/gaffer/web/routers/advice.py src/gaffer/cli.py src/gaffer/digest.py tests/test_v16_brief.py tests/test_v16_web_brief.py tests/test_cli.py frontend/src/schemas.json frontend/src/types.generated.ts
git commit -m "feat(v16): the brief — facts, the classifier's command, a mechanical truth check, /api/brief, chained after the web advise, gaffer brief, the Friday headline"
```

**Orchestrator, after the review:** `tests/test_v11_degradation.py` — `50` → `51`, `assert "/api/brief" in paths`, docstring line `50 → 51, and the one is /api/brief — GET and POST share one path key — the brief and its job.`; run the three rail files; commit `test(v16): route pin 50 → 51 (/api/brief)`.

---

### Task 8: LadderCard — the bar, the chosen rung, the steps, the served note

**Files:**
- Modify: `frontend/src/hubs/this-week/LadderCard.tsx`, `LadderCard.test.tsx`

**Context.** The card already has two `<select>`s (`aria-label="Max hits"` / `"Max transfers"`) whose `onChange` calls `setCap(key, value)` → `apiPost('/api/settings', { key, value })` then `rebuild()`. The payload now carries `bar`, `chosen`, `steps[]`, `served_note` (generated `LadderPayload`, `LadderStep`).

- [ ] **Step 1: Failing tests** — add to `LadderCard.test.tsx` (extend `PAYLOAD` with `bar: 0.6, chosen: 'hits0', served_note: null, steps: [ { below: 'bank', above: 'hits0', share: 0.79, taken: true, reason: 'expected points alone', reason_kind: 'points' }, { below: 'hits0', above: 'hits1', share: 0.46, taken: false, reason: 'Filler is 0% to play', reason_kind: 'flagged' } ]`):

```tsx
it('offers the hit bar beside the caps and writes it through settings', async () => {
  mount()
  const bar = await screen.findByLabelText('Hit bar')
  expect((bar as HTMLSelectElement).value).toBe('0.6')
  await userEvent.selectOptions(bar, '0.7')
  await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
    '/api/settings', { key: 'hit_bar', value: 0.7 }))
  expect(apiPost).toHaveBeenCalledWith('/api/ladder', undefined)
})

it('marks the chosen rung and lists every step with its share and reason', async () => {
  mount()
  const chosen = (await screen.findByText('No hits')).closest('tr')!
  expect(within(chosen).getByText('chosen')).toBeInTheDocument()
  const steps = screen.getByTestId('ladder-steps')
  expect(steps).toHaveTextContent('Bank → No hits: taken, 79% — expected points alone')
  expect(steps).toHaveTextContent('No hits → 1 hit: refused, 46% — Filler is 0% to play')
})

it('says when a rebuild chose differently from the served advice', async () => {
  apiGet.mockImplementation(async (path: string) => (path === '/api/ladder'
    ? { ...PAYLOAD, chosen: 'bank',
        served_note: 'the served advice was the free transfers only rung at bar 0.60; this rebuild at 0.70 chooses bank' }
    : { id: 'j1', status: 'done', result: PAYLOAD, error: null }))
  mount()
  expect(await screen.findByTestId('ladder-served-note'))
    .toHaveTextContent('this rebuild at 0.70 chooses bank')
})
```

- [ ] **Step 2: Implement**

In `LadderCard.tsx`:

```tsx
/** The bars the select offers; the saved value is added by `withCurrent`
 *  when it is not one of them (a hand-edited 0.62 must not render blank). */
export const HIT_BARS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9, 0.95]

/** "Bank → No hits: taken, 79% — expected points alone". */
export function stepText(step: LadderStep, rungs: LadderRung[]): string {
  const label = (key: string) => {
    const r = rungs.find((x) => x.key === key)
    return r ? rungLabel(r) : key
  }
  return `${label(step.below)} → ${label(step.above)}: `
    + `${step.taken ? 'taken' : 'refused'}, ${pct(step.share)} — ${step.reason}`
}
```

(`rungLabel` is the file's existing helper; import `LadderStep` from `../../types`.) Generalise `setCap` to `setSetting(key: 'max_hits' | 'max_transfers' | 'hit_bar', value: number)` — same body. Add a third `<label>` after the two selects:

```tsx
<label className="flex items-center gap-2">
  <span className="label">Hit bar</span>
  <select aria-label="Hit bar" value={String(data?.bar ?? 0.6)}
          disabled={busy || !data?.gw} className={INPUT_CLASS}
          onChange={(e) => setSetting('hit_bar', Number(e.target.value))}>
    {withCurrent(HIT_BARS, data?.bar ?? 0.6).map((b) => (
      <option key={b} value={String(b)}>{`${Math.round(b * 100)}%`}</option>))}
  </select>
</label>
```

In the rung cell beside the existing `recommended` chip: `{r.key === data?.chosen && <Chip tone="up">chosen</Chip>}`. Under the table, before `cap_note`:

```tsx
{!busy && (data?.steps ?? []).length > 0 && (
  <ul className="mt-2 flex flex-col gap-0.5 text-text-secondary" data-testid="ladder-steps">
    {data!.steps.map((s) => (
      <li key={`${s.below}-${s.above}`} className={s.taken ? '' : 'text-text-muted'}>
        {stepText(s, rungs)}
      </li>
    ))}
  </ul>
)}
{!busy && data?.served_note && (
  <p className="mt-2 text-text-muted" data-testid="ladder-served-note">{data.served_note}</p>
)}
```

Update the card's explanatory paragraph to end: "The walk steps up one rung at a time and stops at the first rung that does not clear the bar; the rung it stops on is the advice." Update `ThisWeek.test.tsx`'s LadderCard mock if its `onLoaded` payload shape needs `steps: []` (it passes `rungs: [{}]` today — add `bar: 0.6, chosen: 'hits0', steps: []` only if TypeScript complains).

- [ ] **Step 3: Run** `cd frontend && npx tsc --noEmit && npx vitest run src/hubs/this-week/LadderCard.test.tsx src/hubs/ThisWeek.test.tsx src/kit/tokens.test.ts` — pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hubs/this-week/LadderCard.tsx frontend/src/hubs/this-week/LadderCard.test.tsx frontend/src/hubs/ThisWeek.test.tsx
git commit -m "feat(v16): ladder card — hit bar control, chosen chip, the steps with their reasons, the served note"
```

---

### Task 9: This Week — the restraint and objective lines, and "What I did and why"

**Files:**
- Modify: `frontend/src/types.ts` (`RestraintStep`, `Restraint`, `Objective`; `Advice.objective?`, `Advice.restraint?`)
- Modify: `frontend/src/hubs/this-week/MovesCard.tsx` (+ test)
- Create: `frontend/src/hubs/this-week/DecisionPanel.tsx` (+ test)
- Modify: `frontend/src/hubs/ThisWeek.tsx` (+ test)

- [ ] **Step 1: Types** — in `types.ts`, before `export interface Advice`:

```ts
/** One step of the ladder's restraint walk (v16 §3). */
export interface RestraintStep {
  below: string
  above: string
  share: number
  taken: boolean
  reason: string
  reason_kind: string
}

export interface Restraint {
  chosen: string | null
  bar: number | null
  steps: RestraintStep[]
  agrees: boolean
  note: string | null
}

/** The solver's own week one, kept beside the served plan (v16 §4). */
export interface Objective {
  buys: PlayerRef[]
  sells: PlayerRef[]
  hits: number
  expected_pts: number
}
```

and on `Advice`, after `captain_note?`: `objective?: Objective | null` and `restraint?: Restraint | null` with the comment "v16: absent on a payload banked before the restraint walk".

- [ ] **Step 2: MovesCard failing tests** — add to `MovesCard.test.tsx`:

```tsx
it('prints the restraint line and, when they differ, what the objective wanted', () => {
  render(<MovesCard buys={[]} sells={[]} hits={0}
    restraint={{ chosen: 'hits0', bar: 0.6, agrees: false, note: null,
      steps: [{ below: 'bank', above: 'hits0', share: 0.79, taken: true,
                reason: 'expected points alone', reason_kind: 'points' },
              { below: 'hits0', above: 'hits1', share: 0.46, taken: false,
                reason: 'Rice is 0% to play', reason_kind: 'flagged' }] }}
    objective={{ buys: [{ code: 5, name: 'Isak', ep: 6 }], sells: [{ code: 6, name: 'Rice', ep: 2 }],
                 hits: 1, expected_pts: 63 }} />)
  expect(screen.getByTestId('moves-restraint-line')).toHaveTextContent(
    'Free transfers only — the step to 1 hit was refused at 46%: Rice is 0% to play')
  expect(screen.getByTestId('moves-objective-line')).toHaveTextContent(
    'The objective wanted Isak in, Rice out, 1 hit')
})

it('prints neither line on a payload without the walk', () => {
  render(<MovesCard buys={[]} sells={[]} hits={0} />)
  expect(screen.queryByTestId('moves-restraint-line')).toBeNull()
})
```

- [ ] **Step 3: MovesCard** — props gain `restraint?: Restraint | null` and `objective?: Objective | null`; export

```tsx
export function rungLabel(key: string): string {
  if (key === 'bank') return 'Bank'
  if (key === 'open') return 'No cap'
  if (key === 'hits0') return 'Free transfers only'
  const n = Number(key.replace('hits', ''))
  return `${n} hit${n === 1 ? '' : 's'}`
}

export function restraintText(r: Restraint): string {
  const refused = r.steps.find((s) => !s.taken)
  const head = rungLabel(r.chosen ?? 'bank')
  if (!refused) return `${head} — every step up the ladder was taken`
  return `${head} — the step to ${rungLabel(refused.above).toLowerCase()} was refused `
    + `at ${Math.round(refused.share * 100)}%: ${refused.reason}`
}
```

and render, under the `capLine` paragraph:

```tsx
{restraint && restraint.chosen && (
  <p className="mb-2 text-text-secondary" data-testid="moves-restraint-line">
    {restraintText(restraint)}
  </p>
)}
{restraint && !restraint.agrees && objective && (
  <p className="mb-2 text-text-muted" data-testid="moves-objective-line">
    {'The objective wanted '}
    {[...objective.buys.map((m) => `${m.name} in`),
      ...objective.sells.map((m) => `${m.name} out`)].join(', ') || 'no moves'}
    {`, ${objective.hits} hit${objective.hits === 1 ? '' : 's'}`}
  </p>
)}
```

- [ ] **Step 4: DecisionPanel failing tests** — `DecisionPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DecisionPanel from './DecisionPanel'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p), apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e), ApiError: class extends Error {},
}))

const OPEN = { gw: 4, reason: null, text: '', at: null, state: 'open', deadline: null, grade: null }

beforeEach(() => { apiGet.mockReset(); apiPost.mockReset() })

describe('DecisionPanel', () => {
  it('says it opens at the deadline before it', async () => {
    apiGet.mockResolvedValue({ ...OPEN, state: 'before_deadline', deadline: '2099-09-11T17:30:00Z' })
    render(<DecisionPanel gw={4} />)
    expect(await screen.findByText(/opens at the deadline/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })

  it('offers the eight reasons and saves', async () => {
    apiGet.mockResolvedValue(OPEN)
    apiPost.mockResolvedValue({ ...OPEN, reason: 'injury', text: 'Rice out', at: 't' })
    render(<DecisionPanel gw={4} />)
    const group = await screen.findByRole('group', { name: 'Reason' })
    expect(group.querySelectorAll('button')).toHaveLength(8)
    await userEvent.click(screen.getByRole('button', { name: 'Injury' }))
    await userEvent.type(screen.getByLabelText('Note'), 'Rice out')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/decisions/4', { reason: 'injury', text: 'Rice out' }))
    expect(await screen.findByText(/Saved/)).toBeInTheDocument()
  })

  it('is read-only with the grade once graded', async () => {
    apiGet.mockResolvedValue({ ...OPEN, reason: 'gut', text: 'fancied Isak', at: 't',
      state: 'graded', grade: { lane: 'transfers', label: 'Blunder', delta_pts: -7 } })
    render(<DecisionPanel gw={4} />)
    expect(await screen.findByText('Gut')).toBeInTheDocument()
    expect(screen.getByText('fancied Isak')).toBeInTheDocument()
    expect(screen.getByText('Blunder')).toBeInTheDocument()
    expect(screen.getByText(/−7 pts|-7 pts/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })

  it('renders nothing when the request fails', async () => {
    apiGet.mockRejectedValue(new Error('down'))
    const { container } = render(<DecisionPanel gw={4} />)
    await new Promise((r) => { setTimeout(r, 0) })
    expect(container.textContent).toBe('')
  })
})
```

- [ ] **Step 5: DecisionPanel**

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPost, errorText } from '../../api/client'
import {
  Button, Callout, Card, Chip, INPUT_CLASS, Segmented, fmtDelta,
} from '../../kit'
import type { DecisionNote } from '../../types'

export const REASONS = [
  'injury', 'fixtures', 'eye_test', 'price', 'chip', 'rival', 'gut', 'other',
] as const
export type Reason = typeof REASONS[number]

export const REASON_LABEL: Record<Reason, string> = {
  injury: 'Injury', fixtures: 'Fixtures', eye_test: 'Eye test', price: 'Price',
  chip: 'Chip', rival: 'Rival', gut: 'Gut', other: 'Other',
}

const TEXT_MAX = 280

/** "What I did and why" (v16 §5): a reason from eight and one line of text,
 *  editable from the deadline until the gameweek is graded. */
export default function DecisionPanel({ gw }: { gw: number }) {
  const [note, setNote] = useState<DecisionNote | null>(null)
  const [reason, setReason] = useState<Reason | null>(null)
  const [text, setText] = useState('')
  const [saved, setSaved] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  const load = useCallback(() => {
    apiGet<DecisionNote>(`/api/decisions/${gw}`)
      .then((n) => {
        setNote(n)
        setReason((n.reason as Reason | null) ?? null)
        setText(n.text ?? '')
      })
      .catch(() => setNote(null))
  }, [gw])
  useEffect(load, [load])

  if (note === null) return null

  const save = async () => {
    if (!reason) return
    setFailed(null)
    try {
      const out = await apiPost<DecisionNote>(`/api/decisions/${gw}`, { reason, text })
      setNote(out)
      setSaved(true)
    } catch (e) {
      setFailed(errorText(e))
    }
  }

  const grade = note.grade
  return (
    <Card title="What I did and why" className="mb-4" data-testid="decision-panel">
      {note.state === 'before_deadline' && (
        <p className="text-text-muted">
          Opens at the deadline
          {note.deadline ? ` (${new Date(note.deadline).toLocaleString()})` : ''}
          . Record why you did something other than the advice, and the review
          will grade the reason as well as the move.
        </p>
      )}
      {note.state === 'graded' && (
        <div className="flex flex-wrap items-baseline gap-2">
          {note.reason
            ? <Chip>{REASON_LABEL[note.reason as Reason] ?? note.reason}</Chip>
            : <span className="text-text-muted">No note for this gameweek.</span>}
          {note.text && <span className="text-text-secondary">{note.text}</span>}
          {grade?.label && (
            <span className="inline-flex items-center gap-1.5">
              <Chip tone={(grade.delta_pts ?? 0) >= 0 ? 'up' : 'down'}>{grade.label}</Chip>
              <span className="tn text-text-muted">
                {grade.delta_pts === null ? '' : `${fmtDelta(grade.delta_pts, 0)} pts`}
              </span>
            </span>
          )}
        </div>
      )}
      {note.state === 'open' && (
        <div className="flex flex-col gap-2">
          <Segmented
            label="Reason"
            value={reason ?? ''}
            onChange={(v) => { setReason(v as Reason); setSaved(false) }}
            options={REASONS.map((r) => ({ value: r, label: REASON_LABEL[r] }))}
          />
          <label className="flex items-center gap-2">
            <span className="label">Note</span>
            <input
              aria-label="Note"
              className={`${INPUT_CLASS} flex-1`}
              maxLength={TEXT_MAX}
              value={text}
              onChange={(e) => { setText(e.target.value); setSaved(false) }}
              placeholder="one line, optional"
            />
          </label>
          <div className="flex items-center gap-3">
            <Button variant="primary" onClick={save} disabled={!reason}>Save</Button>
            {saved && <span className="text-text-muted">Saved.</span>}
          </div>
          {failed && <Callout tone="error">{failed}</Callout>}
        </div>
      )}
    </Card>
  )
}
```

`Card` does not spread `data-testid` — if the test needs it, wrap the `Card` in a `<div data-testid="decision-panel">`. `Segmented`'s `value` type is the option's `V`; `'' as Reason` is acceptable for "nothing pressed", or type the value as `Reason | ''`.

- [ ] **Step 6: ThisWeek** — pass `restraint={advice.restraint ?? null}` and `objective={advice.objective ?? null}` to `MovesCard`; render `<DecisionPanel gw={data.gw} />` directly under the moves card `<div>`. In `ThisWeek.test.tsx`, add a route for `/api/decisions/` returning `{ gw: 5, reason: null, text: '', at: null, state: 'before_deadline', deadline: '2099-09-18T17:30:00Z', grade: null }` and `/api/brief` returning `{ gw: null, prose: null, note: null, fallback: { available: false, digest: null } }` (Task 10 needs it), and one test: `expect(await screen.findByText(/opens at the deadline/i)).toBeInTheDocument()`.

- [ ] **Step 7: Run** `cd frontend && npx tsc --noEmit && npx vitest run src/hubs/this-week src/hubs/ThisWeek.test.tsx src/kit/tokens.test.ts` — pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types.ts frontend/src/hubs/this-week/MovesCard.tsx frontend/src/hubs/this-week/MovesCard.test.tsx frontend/src/hubs/this-week/DecisionPanel.tsx frontend/src/hubs/this-week/DecisionPanel.test.tsx frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx
git commit -m "feat(v16): This Week — the restraint and objective lines on the moves card, and the What-I-did-and-why panel"
```

---

### Task 10: BriefCard — the prose, or the digest as fallback

**Files:**
- Create: `frontend/src/hubs/this-week/BriefCard.tsx` (+ test)
- Modify: `frontend/src/hubs/this-week/DigestCard.tsx` (two optional props: `extra?: ReactNode`, `note?: string | null`)
- Modify: `frontend/src/hubs/ThisWeek.tsx` (render `BriefCard` where `DigestCard` was)

- [ ] **Step 1: Failing tests** — `BriefCard.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BriefCard from './BriefCard'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p), apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e), ApiError: class extends Error {},
}))
vi.mock('../../api/useJobStream', () => ({
  useJobStream: () => ({ status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn() }),
}))

const BRIEF = { gw: 4, prose: 'The ladder chose free transfers only.\n\nGuéhi keeps the armband.',
  checked_at: '2026-09-05T09:00:00+00:00', run_stamp: 's', model_command: 'claude',
  note: null, fallback: null }
const NONE = { gw: null, prose: null, checked_at: null, run_stamp: null, model_command: null,
  note: 'the brief did not pass its check this week (number 52 is not in the facts)',
  fallback: { available: false, digest: null } }

function serve(panel: unknown) {
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/brief')) return Promise.resolve(panel)
    if (path.startsWith('/api/jobs/')) return Promise.resolve({ id: 'j', status: 'done', result: {}, error: null })
    return Promise.resolve(null)
  })
}
beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPost.mockResolvedValue({ job_id: 'j' }) })

describe('BriefCard', () => {
  it('renders the prose in paragraphs with the stamp and the model', async () => {
    serve(BRIEF)
    render(<BriefCard />)
    expect(await screen.findByText('The ladder chose free transfers only.')).toBeInTheDocument()
    expect(screen.getByText('Guéhi keeps the armband.')).toBeInTheDocument()
    expect(screen.getByText(/GW4 · claude/)).toBeInTheDocument()
  })

  it('falls back to the digest card with the note when there is no brief', async () => {
    serve(NONE)
    render(<BriefCard />)
    expect(await screen.findByText(/No digest yet/)).toBeInTheDocument()
    expect(screen.getByText(/did not pass its check/)).toBeInTheDocument()
  })

  it('writes a brief on the button and reloads', async () => {
    serve(BRIEF)
    render(<BriefCard />)
    await userEvent.click(await screen.findByRole('button', { name: 'Write the brief' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/brief', undefined))
  })
})
```

- [ ] **Step 2: Implement**

`DigestCard.tsx`: add `export interface DigestCardProps { extra?: ReactNode; note?: string | null }`, render `{extra}` inside the `buttons` flex row before the two `JobButton`s, and `{note && <Callout tone="note" className="mb-2">{note}</Callout>}` as the first child of both branches' `Card`.

`BriefCard.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Button, Callout, Card, JobButton } from '../../kit'
import type { BriefPanel } from '../../types'
import DigestCard from './DigestCard'

/** The week, written (v16 §6). A brief that exists replaces the digest's
 *  prose; the two digest buttons stay. The button posts an anonymous job
 *  (plan R1) exactly as the ladder's Rebuild does. */
export default function BriefCard() {
  const [panel, setPanel] = useState<BriefPanel | null>(null)
  const job = useJob('brief')

  const load = useCallback(() => {
    apiGet<BriefPanel>('/api/brief').then(setPanel).catch(() => {})
  }, [])
  useEffect(load, [load])
  useEffect(() => { if (job.status === 'done') load() }, [job.status, load])

  const busy = job.status === 'queued' || job.status === 'running'
  const write = (
    <Button onClick={() => job.start('/api/brief')} disabled={busy}>
      {busy ? 'Writing…' : 'Write the brief'}
    </Button>
  )

  if (panel === null) return null
  if (!panel.prose) return <DigestCard extra={write} note={panel.note} />

  const stamp = panel.checked_at ? new Date(panel.checked_at).toLocaleString() : ''
  return (
    <Card
      title="The week"
      className="mb-4"
      action={(
        <div className="flex flex-wrap items-baseline gap-3">
          <span className="text-text-muted">
            {`GW${panel.gw} · ${panel.model_command ?? 'llm'}${stamp ? ` · ${stamp}` : ''}`}
          </span>
          {write}
          <JobButton kind="digest-friday" onDone={load} />
          <JobButton kind="digest-tuesday" onDone={load} />
        </div>
      )}
    >
      {job.status === 'error' && <Callout tone="error" className="mb-2">{job.error}</Callout>}
      {panel.prose.split(/\n\s*\n/).map((para) => (
        <p key={para.slice(0, 40)} className="mb-2 max-w-prose text-text">{para.trim()}</p>
      ))}
      <p className="text-text-faint">
        Written from the banked facts and checked against them: every number
        and every name above is in the advice, the ladder or the ledger.
      </p>
    </Card>
  )
}
```

`ThisWeek.tsx`: `import BriefCard from './this-week/BriefCard'` and render `<BriefCard />` where `<DigestCard />` was (drop the DigestCard import if unused).

- [ ] **Step 3: Run** `cd frontend && npx tsc --noEmit && npx vitest run` — whole frontend suite green (expect > 893).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hubs/this-week/BriefCard.tsx frontend/src/hubs/this-week/BriefCard.test.tsx frontend/src/hubs/this-week/DigestCard.tsx frontend/src/hubs/ThisWeek.tsx
git commit -m "feat(v16): the brief card — prose with its stamp, the digest as fallback with the check's note, a write button"
```

---

### Task 11: The replay arm (`scripts/v7b_replay.py`)

**Files:**
- Modify: `scripts/v7b_replay.py` (`ArmConfig.hit_bar`, `ArmConfig.ladder_draws`, `--arm restraint`, `--hit-bar`, `--ladder-draws`, `make_restraint_gate`, `run_one`)
- Test: `tests/test_v7b_driver.py` (extend; not protected)

**Context.** `run_one` installs `make_gate` (the sweep gate) whenever `gate_wanted(cfg)`; `make_gate`'s closure stands aside for the opening squad, a wildcard week and a free hit (`not state.owned_codes or state.wildcard_gw is not None or state.free_transfers >= 15`). The replay's `SolveInput` carries the config caps (`max_hits`, `max_transfers`) and `pool["ep"]` is a per-row `{gw: ep}` dict. The seed reaches the restraint arm through the ladder draws, so `--seed-bases` is valid for it (plan R10).

- [ ] **Step 1: Failing tests** — append to `tests/test_v7b_driver.py`:

```python
def test_the_restraint_arm_parses_with_its_bar_and_draws():
    cfg = v7b_replay.arm_config(["--arm", "restraint", "--tag", "t"])
    assert cfg.arm == "restraint" and cfg.hit_bar == 0.6 and cfg.ladder_draws == 2000
    cfg = v7b_replay.arm_config(["--arm", "restraint", "--tag", "t",
                                 "--hit-bar", "0.7", "--ladder-draws", "50"])
    assert (cfg.hit_bar, cfg.ladder_draws) == (0.7, 50)
    assert cfg.echo()["hit_bar"] == 0.7
    configs, bases, _ = v7b_replay.arm_configs(
        ["--arm", "restraint", "--tag", "q", "--seed-bases", "1,2"])
    assert bases == [1, 2]


def test_the_restraint_gate_serves_the_chosen_rung(monkeypatch):
    """Two rung specs that solve to different plans; the draws are zero-noise
    so the higher-scoring plan wins every draw and the walk takes it."""
    from dataclasses import dataclass

    import pandas as pd

    from gaffer.optimize.milp import GwPlan, Plan, SolveInput

    def plan(buys, sells, hits, xi):
        return Plan(objective=0.0, gw_plans=[GwPlan(
            gw=5, squad=xi, xi=xi, xi_rows=[], bench=[], captain=xi[0],
            vice=xi[1], buys=buys, sells=sells, hits=hits, expected_pts=0.0)])

    def fake_solve(pool, state, **kw):
        if state.max_transfers == 0:
            return plan([], [], 0, [1, 2, 3])
        if state.max_hits == 0:
            return plan([9], [3], 0, [1, 2, 9])          # 9 scores more than 3
        return plan([9, 8], [3, 2], 1, [1, 9, 8])          # a hit for 8 over 2

    pool = pd.DataFrame({"code": [1, 2, 3, 8, 9],
                         "ep": [{5: 2.0}, {5: 2.0}, {5: 1.0}, {5: 9.0}, {5: 6.0}]})
    state = SolveInput(owned_codes=[1, 2, 3], bank=0, free_transfers=1, gws=[5])
    monkeypatch.setattr("gaffer.ladder.OUTCOME_VAR_PER_EP", 0.0)
    cfg = v7b_replay.arm_config(["--arm", "restraint", "--tag", "t", "--ladder-draws", "8"])
    gate = v7b_replay.make_restraint_gate(cfg, fake_solve)
    out = gate(pool, state, hit_cost=4)
    # hits1 beats hits0 in every draw (8 adds 7 EP for a 4-point hit).
    assert out.gw_plans[0].buys == [9, 8]
    assert gate.gated_weeks == 1 and gate.steps_taken == 2 and gate.steps_refused == 0
    cfg = v7b_replay.arm_config(["--arm", "restraint", "--tag", "t", "--ladder-draws", "8",
                                 "--hit-bar", "0.95"])
    gate = v7b_replay.make_restraint_gate(cfg, fake_solve)
    assert gate(pool, state, hit_cost=4).gw_plans[0].buys == [9, 8]   # 100% > 95%


def test_the_restraint_gate_stands_aside_where_the_sweep_gate_does():
    from gaffer.optimize.milp import SolveInput

    calls = []

    def fake_solve(pool, state, **kw):
        calls.append(state)
        return "plan"

    cfg = v7b_replay.arm_config(["--arm", "restraint", "--tag", "t"])
    gate = v7b_replay.make_restraint_gate(cfg, fake_solve)
    assert gate(None, SolveInput(owned_codes=[], bank=0, free_transfers=15, gws=[5])) == "plan"
    assert gate(None, SolveInput(owned_codes=[1], bank=0, free_transfers=1, gws=[5],
                                 wildcard_gw=5)) == "plan"
    assert len(calls) == 2
```

- [ ] **Step 2: Implement**

`ArmConfig` gains `hit_bar: float = 0.6` and `ladder_draws: int = 2000` (before the `init=False` fields); `echo()` returns them too. `_parser`: `choices=["raw", "heur", "estimation", "composite", "restraint"]`, `p.add_argument("--hit-bar", type=float, default=0.6)`, `p.add_argument("--ladder-draws", type=int, default=2000)`; `_configs.one` passes `hit_bar=a.hit_bar, ladder_draws=a.ladder_draws`. The `--seed-bases` refusal stays for `raw` only.

Add after `make_gate`:

```python
def make_restraint_gate(cfg: ArmConfig, real_solve):
    """v16 §7 R1 (plan R10): the restraint arm's ``solve_plan``.

    The raw solve is the objective; then the ladder's rung specs are solved
    off the same pool and state, collapsed by their first-week moves, scored
    on one shared matrix of zero-band outcome draws (the replay has no
    component bands, so every cell takes the ladder's σ fallback), and the
    walk picks the rung under ``cfg.hit_bar`` and the state's own caps. The
    chosen rung's plan is returned — the rest of the replay executes its
    first week exactly as it executes the objective's. Stands aside where
    the sweep gate does: the opening squad, a wildcard, a free hit.
    """
    from dataclasses import replace as _replace

    import numpy as np

    from gaffer.ladder import (LADDER_HITS, SEED_OFFSET, collapse,
                               draw_points, score_plan, walk)

    def gate(pool, state, **kw):
        plan = real_solve(pool, state, **kw)
        if (not state.owned_codes or state.wildcard_gw is not None
                or state.free_transfers >= 15):
            return plan
        gw = int(state.gws[0])
        specs = [("bank", _replace(state, max_transfers=0))]
        specs += [(f"hits{k}", _replace(state, max_hits=k)) for k in LADDER_HITS]
        specs.append(("open", state))
        solved = []
        for key, spec in specs:
            try:
                p = real_solve(pool, spec, **kw)
            except (RuntimeError, KeyError, ValueError):
                continue
            if key == "open" and p.gw_plans[0].hits <= max(LADDER_HITS):
                continue
            solved.append((key, p))
        if not solved:
            return plan
        distinct, same_as = collapse(solved)
        ep_by = {(int(r.code), int(g)): float(v)
                 for r in pool.itertuples() for g, v in r.ep.items()}
        keys = set()
        for _, p in distinct:
            for w in p.gw_plans:
                keys.update((int(c), int(w.gw)) for c in w.xi)
                keys.add((int(w.captain), int(w.gw)))
        rng = np.random.default_rng(cfg.seed_base + gw + SEED_OFFSET)
        draws = draw_points(keys, ep_by, {}, rng, cfg.ladder_draws)
        hit_cost = int(kw.get("hit_cost", 4))
        scores = {k: score_plan(p.gw_plans, draws, hit_cost, cfg.ladder_draws)
                  for k, p in distinct}
        rows = [{"key": k, "same_as": same_as.get(k),
                 "hits": int(p.gw_plans[0].hits),
                 "transfers": len(p.gw_plans[0].buys)} for k, p in solved]
        chosen, steps = walk(scores, rows, hit_bar=cfg.hit_bar,
                             max_hits=state.max_hits,
                             max_transfers=getattr(state, "max_transfers", None))
        gate.gated_weeks += 1
        gate.steps_taken += sum(1 for s in steps if s["taken"])
        gate.steps_refused += sum(1 for s in steps if not s["taken"])
        by = dict(solved)
        return by[chosen] if chosen in by else plan

    gate.gated_weeks = 0
    gate.steps_taken = 0
    gate.steps_refused = 0
    return gate
```

In `run_one`, change the gate installation to:

```python
    if cfg.arm == "restraint":
        gate = make_restraint_gate(cfg, real_solve)
        bt.solve_plan = gate
    elif gate_wanted(cfg):
        ... (the existing pcs stash + make_gate block, unchanged)
```

and add to `out`: `"steps_taken": getattr(gate, "steps_taken", 0), "steps_refused": getattr(gate, "steps_refused", 0), "caps": {"max_hits": int(load_config().max_hits), "max_transfers": int(load_config().max_transfers)}` (import `load_config` from `gaffer.config`). `apply_patches` needs no branch for `restraint` (it patches nothing, like `raw`). Check `multiseed_summary` / `scripts/seed_stats.py` still read `total`/`hits`/`transfers` (they do; the new keys are extras).

- [ ] **Step 3: Run** `.venv/bin/pytest -q tests/test_v7b_driver.py tests/test_seed_stats.py tests/test_v7b_composite.py` — pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/v7b_replay.py tests/test_v7b_driver.py
git commit -m "feat(v16): --arm restraint on the v7b replay — rung specs, shared draws, the walk; steps counted per season"
```

---

### Task 12: Gates R1, R2, R3 (**orchestrator**)

- [ ] **R1 — the season replay.** From the repo root, in the background (each run is the raw replay plus five extra solves a week; budget an hour or more):

```bash
.venv/bin/python scripts/v7b_replay.py --arm raw --tag v16-raw > logs/v16-raw.log 2>&1
.venv/bin/python scripts/v7b_replay.py --arm restraint --tag v16-restraint \
    --seed-bases 20260901,20260902,20260903 > logs/v16-restraint.log 2>&1
```

Read `reports/v7b_v16-raw.json` and the three `reports/v7b_v16-restraint-s*.json` (plus the multiseed summary line). **Pass:** `mean(restraint.total) >= raw.total − (max − min of the three restraint totals)` **and** `mean(restraint.hits) < raw.hits`. Record totals, hits, transfers, steps taken/refused, the caps the run used and the per-seed spread in the spec's final section (add `## 12. R1 result`) whatever the verdict; a fail is put to the user before merge.

- [ ] **R2 — the brief on real artifacts.** On the branch, with the tree's real `config.toml` (do not open it; the command reads it):

```bash
uv run gaffer brief
cat reports/brief_gw3.json | .venv/bin/python -c "import json,sys; print(json.load(sys.stdin)['prose'])"
```

If the newest advice on disk predates Task 3 (no `restraint` block), run `uv run gaffer advise --fast` first (writes a fresh GW artifact with the block), then `gaffer brief`. The check must pass; paste the prose to the user and ask them to read it. Wrong prose the check cannot see → change `build_prompt`, bump `BRIEF_PROMPT_VERSION` to 2, rerun, before merge.

- [ ] **R3 — screenshots.** Rebuild and serve from the repo root, then shoot a `v16` stage (add it to `frontend/scripts/shots.sh` beside the `v15*` block):

```bash
if [[ "$STAGE" == v16* ]]; then
  HUBS=(
    "this-week:/"
    "planning-board:/planning?tab=board"
    "review:/model?tab=review"
    "settings:/model?tab=settings"
  )
fi
```

```bash
cd frontend && npm run build && cd .. \
  && (lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || uv run gaffer ui --no-open-browser --port 8927 &) \
  && frontend/scripts/shots.sh v16
```

Publish the eight images through the brainstorming companion's page (`gate_page.py v16 <screen_dir> "v16 gate"`), ask the user to approve This Week (restrained moves, the objective line, the decision panel, the brief card), the ladder card with the bar and steps, Review with a note beside a grade, and Settings. Commit `frontend/scripts/shots.sh`.

---

### Task 13: Merge, security ritual, docs, memory (**orchestrator**)

- [ ] Full suites on the branch tip: `.venv/bin/pytest -q` (strictly above 4170 passed, nothing failing) and `cd frontend && npx tsc --noEmit && npx vitest run` (strictly above 893).
- [ ] Final code review subagent over `git diff main...v16-restraint`.
- [ ] `git checkout main && git merge --ff-only v16-restraint`.
- [ ] Security ritual before the push — must print nothing, then must fail:
  ```bash
  V="$(sed -n '/^\[odds\]/,/^\[/p' config.toml | grep '^api_key' | cut -d'"' -f2)"; [ "${#V}" -ge 8 ] || echo "extraction failed"; git grep -c "$V" HEAD
  git show main:config.toml
  ```
- [ ] `git push origin main`.
- [ ] `docs/GUIDE.md`: §4 (a paragraph on the restraint walk and the bar under the optimizer), §5 This Week (the moves card's two lines, the ladder card's bar/steps, the decision panel, the brief card) and Review (the note, the by-reason table), §8 (`gaffer brief`), §11 a **v16** entry (date, the three pieces, R1's numbers, the pins), §12.4 open notes (the chip reason needs a `chip_plan` on the state, so a state written before v16 gives no chip reason; sentence-initial names escape the truth check; the brief is chained only on the web job — the launchd Thursday `gaffer advise` needs `gaffer brief` added to its plist to have a Friday headline). `docs/superpowers/ROADMAP.md`: "Where things stand", a v16 shipped block (R1 numbers, pins routes 51 / jobs 12 / Config 59, the R1 ruling), candidate: the in-app chat.
- [ ] Memory: update `fpl-advisor-project.md` (v16 merged, hash, suite counts, pins; the open items) and `MEMORY.md`'s hook.

---

## Self-review against the spec

- §3.1 walk, §3.2 bar and settings row, §3.3 reasons in precedence, §3.4 ladder fields — Tasks 1, 2 (R2 renames `from/to`; R12 adds `cap`).
- §4 payload from the rung, captain fallback, `objective` and `restraint` blocks, failure fallback, trace follows the served plan, CLI lines, Rebuild statement — Tasks 2 (`served_note`), 3, 4.
- §5 store, routes, refusal shape, deadline rule, This Week panel states, Review line and tally, the brief quoting the note — Tasks 5, 6, 9, 7 (`_last_week`).
- §6 content order (the prompt), facts rounding (R13), the command and cache salt, the truth check, banking, `GET /api/brief`, chained after the web advise, the card, the Friday headline — Tasks 7, 10. Deviation R1 (no job kind) and addition R9 (`gaffer brief`), both flagged to the user.
- §7 gates — Task 12 (R10 for the arms). §8 pins — Config 59 (Task 1), routes 51 (Tasks 5, 7), job kinds **stay 12** (R1). §9 tests — one file per task above. §10 branch and process — Conventions.

Type consistency checked: `walk(scores, rows, *, hit_bar, max_hits, max_transfers)` is called identically in `build_ladder` (Task 2) and the replay gate (Task 11); `serve_rung(ladder, objective, *, captain_note)` in Task 2 and Task 3; `run_brief(gw=None, *, cfg=None, cache_dir=...)` in Tasks 7's tests, router (`run_brief()`), chain (`run_brief(advice.gw)`) and CLI; `DecisionNote` fields match `_view` and the panel; `LadderStep` keys match `walk`'s dicts.
