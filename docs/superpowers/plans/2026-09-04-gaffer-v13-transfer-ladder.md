# gaffer v13 — Transfer Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two appetite levers (`max_hits`, `max_transfers`) the weekly advice obeys, and a transfer ladder — one row per rung of hits, scored on shared noise draws — served on the This Week hub and the What-If tab.

**Architecture:** The caps are `[optimizer]` config fields that ride into the one `SolveInput` `run_advise` builds, so the sweep, the alternatives and the chip table inherit them through `state`; they are also written into `SolveState.opt` so every re-solve off the saved board (What-If baseline, drafts, the ladder) can read them back. The ladder is a new module `gaffer/ladder.py` that solves five capped variants of the saved board, scores each fixed plan on one matrix of noise draws, and banks `reports/ladder_gw{N}.json`; a router serves it and re-runs it as an anonymous job (no new `JOB_KINDS` entry). The UI is one card, `LadderCard`, self-loading, rendered in two hubs.

**Tech Stack:** Python 3.12, dataclasses, pydantic v2, FastAPI, PuLP MILP, numpy; React + TypeScript, vitest, json-schema-to-typescript.

**Branch:** all work on `v13-ladder`, cut from `main` (`git switch -c v13-ladder main`). The orchestrator ff-merges after the final review; nobody pushes to `main` from this plan.

**Spec:** `docs/superpowers/specs/2026-09-04-gaffer-v13-transfer-ladder-design.md`. Two corrections to it, found in the code and applied below: (1) `GET` and `POST /api/ladder` share **one** OpenAPI path key, so the route pin moves 47 → **48**, not 49 (`/api/settings` moved it 46 → 47 the same way, `tests/test_v11_degradation.py:353-359`); (2) `LadderWeek.xi`/`bench` carry `PlayerRef`s rather than bare codes, because the card has no code → name map of its own.

**Standing rules for every task.** Python tests: `.venv/bin/pytest`. Frontend: `cd frontend && npx vitest run` and `npx tsc --noEmit`; a vitest summary line reading `Errors  N error` is a **failure** even when every test passed. Stage explicit paths only — never `git add -A`, never `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml`, `config.local.toml`, `src/gaffer/web/static/`. Every commit ends with:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

**Pins after this plan:** routes **48** (`tests/test_v11_degradation.py`, the only file allowed to hold that number), `Config` fields **57** (moved to `tests/test_v13_degradation.py`, the newest cycle's file, per the W3 ruling), `JOB_KINDS` **12** unchanged.

---

## File map

| File | Responsibility |
|---|---|
| `src/gaffer/config.py` | `NO_CAP`, the two `Config` fields, `_check_caps` |
| `src/gaffer/optimize/milp.py` | `SolveInput.max_transfers` + one constraint |
| `src/gaffer/advise.py` | caps into the weekly `SolveInput`, `Advice.caps`, `opt` keys, the ladder call |
| `src/gaffer/artifacts.py` | `caps_from_state` |
| `src/gaffer/cli.py` | the `Caps:` line |
| `src/gaffer/web/routers/whatif.py`, `drafts.py` | baseline under the state's caps; `max_transfers` on the request |
| `src/gaffer/drafts.py` | the eighth constraint key |
| `src/gaffer/web/settings_keys.py` | two `WHITELIST` entries |
| `src/gaffer/ladder.py` (new) | rungs, draws, probabilities, save/load |
| `src/gaffer/web/routers/ladder.py` (new) | `GET`/`POST /api/ladder` |
| `src/gaffer/web/schemas.py`, `web/app.py` | models, router registration |
| `frontend/src/hubs/this-week/LadderCard.tsx` (new) | the card |
| `frontend/src/hubs/ThisWeek.tsx`, `this-week/MovesCard.tsx`, `planning/WhatIfTab.tsx`, `planning/ConstraintsPanel.tsx`, `planning/DraftsTab.tsx` | placement, cap line, the `max_transfers` select |
| `tests/test_v13_degradation.py` (new), `tests/test_ladder.py` (new), `tests/test_web_ladder.py` (new) | the rail, the scoring, the routes |

---

### Task 1: Config fields, validation, docs, and the moved config pin

**Files:**
- Modify: `src/gaffer/config.py` (dataclass `Config` ~line 40-58; `load_config` ~line 307-398)
- Modify: `config.example.toml:21`, `README.md:181-185`
- Modify: `tests/test_v12_w3_degradation.py:518-537`, `tests/test_v12_w1_degradation.py:73-105`
- Create: `tests/test_v13_degradation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_v13_degradation.py`:

```python
"""v13 — the transfer ladder (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md).

The rail: the caps at their defaults, the MILP byte-identical with both
caps ``None``, the routes and job kinds, the ladder's shape. This is the
newest cycle's file, so it holds the one absolute ``fields(Config)`` pin
(W3's ruling, 2026-09-02); the absolute route pin stays in v11's file.
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest

from gaffer.config import NO_CAP, Config, load_config
from gaffer.errors import GafferError


# --- Block 1: the two levers ---------------------------------------------

def test_the_config_gained_exactly_two_fields():
    """55 after v12 W3 (``test_v12_w3_degradation.py``), 57 here. The claim
    is the two names; 57 is the arithmetic. Pinned as a total *and* by name
    so a key cannot be swapped for another in one cycle."""
    names = {f.name for f in dataclasses.fields(Config)}
    assert len(names) == 57
    assert {"max_hits", "max_transfers"} <= names


def test_the_caps_default_to_two_hits_and_no_transfer_cap():
    cfg = Config(entry_id=1, league_id=2)
    assert cfg.max_hits == 2
    assert cfg.max_transfers == NO_CAP == 15


def test_the_caps_are_read_from_the_optimizer_table(tmp_path):
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        "[optimizer]\nmax_hits = 1\nmax_transfers = 0\n")
    cfg = load_config(tmp_path / "config.toml")
    assert (cfg.max_hits, cfg.max_transfers) == (1, 0)


@pytest.mark.parametrize("line", ["max_hits = 16", "max_hits = -1",
                                  "max_transfers = 2.5",
                                  "max_transfers = true"])
def test_a_cap_outside_0_to_15_is_refused_by_name(tmp_path, line):
    (tmp_path / "config.toml").write_text(
        f"[fpl]\nentry_id = 1\nleague_id = 2\n[optimizer]\n{line}\n")
    key = line.split(" =")[0]
    with pytest.raises(GafferError, match=key):
        load_config(tmp_path / "config.toml")


def test_the_two_keys_are_documented():
    root = pathlib.Path(__file__).resolve().parents[1]
    for doc in ("config.example.toml", "README.md"):
        text = (root / doc).read_text(encoding="utf-8")
        assert "max_hits" in text and "max_transfers" in text, doc
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_v13_degradation.py -q`
Expected: FAIL — `ImportError: cannot import name 'NO_CAP'`.

- [ ] **Step 3: Add the constant, the fields and the check to `config.py`**

Directly above `@dataclass\nclass Config:` insert:

```python
NO_CAP = 15
"""``[optimizer] max_hits`` / ``max_transfers`` value meaning "no cap".

The tree's idiom for unlimited — ``free_transfers=15`` is how every
from-scratch solve says it — so the two keys share it rather than inventing
a sentinel. ``max_transfers = 0`` is a real cap: bank, no moves at all.
"""
```

In `class Config`, directly after `alt_plan_max_gap: float = 2.0`:

```python
    # v13 §2.1 (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md). The
    # manager's appetite, not a model parameter: the most hits and the most
    # transfers the solver may take in any one non-wildcard gameweek. The
    # Thursday advice, its scenario sweep, its alternative plans and its chip
    # table all solve under them (advise.py builds the one SolveInput they
    # inherit). NO_CAP means uncapped; max_transfers = 0 means bank.
    max_hits: int = 2
    max_transfers: int = NO_CAP
```

Directly above `def load_config(`:

```python
def _check_caps(cfg: "Config") -> None:
    """v13 §2.1: both caps are whole numbers in ``0..NO_CAP``, refused by
    name. Checked here rather than in ``__post_init__`` so a ``Config`` built
    in a test with a deliberate bad value can still exist; the file is where
    a wrong number comes from."""
    for key in ("max_hits", "max_transfers"):
        value = getattr(cfg, key)
        if (isinstance(value, bool) or not isinstance(value, int)
                or not 0 <= value <= NO_CAP):
            raise GafferError(
                f"[optimizer] {key} = {value!r} — must be a whole number "
                f"between 0 and {NO_CAP} ({NO_CAP} means no cap)")
```

In `load_config`, change `    return Config(` to `    cfg = Config(`, and change the end of that call

```python
        web_token=str(web.get("token", "")),
    )
```

to

```python
        web_token=str(web.get("token", "")),
    )
    _check_caps(cfg)
    return cfg
```

- [ ] **Step 4: Document the keys**

`config.example.toml`, directly after the line `alt_plan_max_gap = 2.0` (line 21):

```toml
# v13: your appetite. The most hits and the most transfers the solver may take
# in any one gameweek; the Thursday advice, its sweep, its alternatives and its
# chip table all solve under them. 15 = no cap; max_transfers = 0 = bank.
max_hits = 2
max_transfers = 15
```

`README.md`, directly after the `alt_plan_max_gap` comment block (the line `                     # each alternative costs one more MILP solve.`):

```
max_hits = 2         # v13: most hits in any one gameweek; 15 = no cap. The
                     # weekly advice and everything solved off it obey this.
max_transfers = 15   # v13: most transfers in any one gameweek; 0 = bank.
```

- [ ] **Step 5: Move the absolute config-field pin**

`tests/test_v12_w3_degradation.py`, in `test_the_config_gained_exactly_two_fields` (~line 518): delete the line `    assert len(names) == 55` and append to the docstring, before its closing quotes:

```
    v13 (2026-09-04) moved the absolute total to ``test_v13_degradation.py``
    (57); this file keeps the by-name claim about its own two keys.
```

`tests/test_v12_w1_degradation.py`, in `test_only_one_file_pins_the_absolute_config_field_count` (~line 73): change `    assert hits == ["test_v12_w3_degradation.py"]` to `    assert hits == ["test_v13_degradation.py"]` and append to the docstring: `    v13 moved it again, to ``test_v13_degradation.py``.`

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/test_v13_degradation.py tests/test_v12_w1_degradation.py tests/test_v12_w3_degradation.py tests/test_v12_w4_degradation.py tests/test_v12_w5_degradation.py tests/test_config_v8a.py tests/test_v12_w5_settings.py tests/test_v12_w5_config_overlay.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/config.py config.example.toml README.md tests/test_v13_degradation.py tests/test_v12_w3_degradation.py tests/test_v12_w1_degradation.py
git commit -m "feat(v13): [optimizer] max_hits and max_transfers — the manager's appetite, validated 0..15, config pin 55 -> 57"
```

---

### Task 2: `SolveInput.max_transfers` in the MILP

**Files:**
- Modify: `src/gaffer/optimize/milp.py` (`SolveInput` ~line 140-176; constraint block ~line 744-750)
- Test: `tests/test_milp.py`, `tests/test_v13_degradation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_milp.py`:

```python
# --- v13: max_transfers -------------------------------------------------

KW13 = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
            itb_value=0.05, hit_cost=4)


def _two_star_pool():
    """Codes 19 and 20 (both FWD, neither owned) are worth a free transfer
    each: with two FTs the solver takes both, one hit or none."""
    pool = _pool(star_ep=9.0)
    pool.loc[pool["code"] == 19, "ep"] = pd.Series(
        [{1: 9.0, 2: 9.0}], index=pool.index[pool["code"] == 19])
    return pool


def test_max_transfers_none_is_the_identity():
    from dataclasses import replace as dc_replace

    a = solve_plan(_two_star_pool(), _state(ft=2), **KW13)
    b = solve_plan(_two_star_pool(), dc_replace(_state(ft=2),
                                                max_transfers=None), **KW13)
    assert round(a.objective, 9) == round(b.objective, 9)
    assert sorted(a.gw_plans[0].buys) == sorted(b.gw_plans[0].buys) == [19, 20]


def test_max_transfers_zero_is_bank():
    from dataclasses import replace as dc_replace

    plan = solve_plan(_two_star_pool(),
                      dc_replace(_state(ft=2), max_transfers=0), **KW13)
    assert plan.gw_plans[0].buys == []
    assert plan.gw_plans[0].sells == []
    assert plan.gw_plans[0].hits == 0


def test_max_transfers_one_caps_a_two_move_week():
    from dataclasses import replace as dc_replace

    plan = solve_plan(_two_star_pool(),
                      dc_replace(_state(ft=2), max_transfers=1), **KW13)
    assert len(plan.gw_plans[0].buys) == 1
    assert plan.gw_plans[0].hits == 0
```

Append to `tests/test_v13_degradation.py`:

```python
# --- Block 2: the MILP ---------------------------------------------------

def test_both_caps_none_build_the_golden_lp_byte_for_byte(tmp_path):
    """``tests/data/v12_w3_milp_golden.lp`` came off the code before
    ``force_out`` existed and is unchanged by this cycle: a defaulted
    ``max_transfers`` emits no constraint."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    captured = _capture_lp(tmp_path, _state(max_transfers=None,
                                            max_hits=None))
    assert len(captured) == 1
    assert captured[0] == GOLDEN.read_text()


def test_a_transfer_cap_does_change_the_lp(tmp_path):
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    captured = _capture_lp(tmp_path, _state(max_transfers=1))
    assert captured[0] != GOLDEN.read_text()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_milp.py -k max_transfers tests/test_v13_degradation.py -k lp -q`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'max_transfers'`.

- [ ] **Step 3: Add the field and the constraint**

In `SolveInput`, directly after the `force_out` field's docstring (the line ending `` ``tests/data/v12_w3_milp_golden.lp`` pins that.\n    """ ``), add:

```python
    # v13 §2.2 (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md)
    max_transfers: int | None = None
    """Cap on transfers in a non-wildcard week; ``None`` adds no constraint.

    Appended last and defaulted, like ``force_out``, so the golden LP above
    is byte-identical with it ``None``. ``0`` is "bank": no move at all.
    """
```

In `_solve_once`, directly after

```python
        if state.max_hits is not None and not wc:
            prob += hits[t] <= state.max_hits
```

add:

```python
        # v13 §2.2: the transfer cap, the same shape as the hit cap and exempt
        # on a wildcard week for the same reason.
        if state.max_transfers is not None and not wc:
            prob += nt <= state.max_transfers
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_milp.py tests/test_v13_degradation.py tests/test_v12_w3_force_out.py tests/test_chips.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/optimize/milp.py tests/test_milp.py tests/test_v13_degradation.py
git commit -m "feat(v13): SolveInput.max_transfers — nt <= cap on non-wildcard weeks, golden LP unchanged"
```

---

### Task 3: The caps reach the weekly advice, the saved state, and the CLI

**Files:**
- Modify: `src/gaffer/artifacts.py` (after `OPT_REQUIRED_KEYS` ~line 287-296)
- Modify: `src/gaffer/advise.py` (imports; `Advice` ~line 116-146; the `SolveInput` at ~line 745; the `Advice(` construction ~line 1106; `save_solve_state(` ~line 1159)
- Modify: `src/gaffer/cli.py` (`advise` command, after the `Hits:` line ~line 72)
- Test: `tests/test_advise.py`, `tests/test_v13_degradation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_advise.py`:

```python
# --- v13: the appetite reaches the one SolveInput --------------------------


def test_run_advise_hands_the_caps_to_the_weekly_solve_input():
    """Source-level seam, like the protected orderings above: the caps ride on
    the SolveInput the sweep, the alternatives and the chip table all
    inherit, and on no other. The initial-squad branch builds fifteen
    transfers and must stay uncapped."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "max_hits=_cap(cfg.max_hits)" in src
    assert "max_transfers=_cap(cfg.max_transfers)" in src
    assert src.index("free_transfers=my.free_transfers, gws=gws") \
        < src.index("max_hits=_cap(cfg.max_hits)") \
        < src.index("pool = build_pool(")
    assert '"max_hits": int(cfg.max_hits)' in src
    assert '"max_transfers": int(cfg.max_transfers)' in src


def test_cap_maps_the_no_cap_sentinel_to_none():
    from gaffer.advise import _cap
    from gaffer.config import NO_CAP

    assert _cap(NO_CAP) is None
    assert _cap(99) is None
    assert _cap(2) == 2
    assert _cap(0) == 0


def test_advice_carries_the_caps_with_a_safe_default():
    a = _bare_advice()
    assert getattr(a, "caps", None) is None
```

Append to `tests/test_v13_degradation.py`:

```python
# --- Block 3: the saved state and the CLI --------------------------------

def _state_with(opt_extra: dict):
    import pandas as pd

    from gaffer.artifacts import SolveState

    return SolveState(
        gw=1, gws=[1, 2], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[], lam=0.0, league_eo={},
        avail_by_gw={1: [], 2: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": 2, **opt_extra},
        pool=pd.DataFrame(columns=["code", "name", "position", "team_code",
                                   "cost", "sell", "owned", "gw", "ep_raw"]))


def test_caps_from_state_reads_none_none_off_a_pre_v13_state():
    from gaffer.artifacts import caps_from_state

    assert caps_from_state(_state_with({})) == (None, None)


def test_caps_from_state_maps_the_sentinel_and_keeps_a_real_cap():
    from gaffer.artifacts import caps_from_state

    assert caps_from_state(_state_with({"max_hits": 2, "max_transfers": 15})) \
        == (2, None)
    assert caps_from_state(_state_with({"max_hits": 15, "max_transfers": 0})) \
        == (None, 0)


def test_solve_kw_from_state_ignores_the_two_keys():
    from gaffer.artifacts import solve_kw_from_state

    kw = solve_kw_from_state(_state_with({"max_hits": 2, "max_transfers": 15}))
    assert "max_hits" not in kw and "max_transfers" not in kw


def test_the_cli_prints_the_caps_line_when_the_advice_carries_one(
        tmp_path, monkeypatch):
    """v4c's rail (``test_v4c_degradation.py``) builds its Advice without
    ``caps``, so its output is untouched; a real run sets the field and gets
    one extra line, below the hits."""
    from typer.testing import CliRunner

    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod
    from gaffer.cli import app
    from tests.test_v4c_degradation import _fixture_advice

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\n'
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    advice = _fixture_advice()
    advice.caps = {"max_hits": 2, "max_transfers": 15}
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: advice)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    result = CliRunner().invoke(app, ["advise"])
    assert result.exit_code == 0, result.output
    assert "Caps: 2 hits/week, transfers uncapped\n" in result.output
    assert result.output.index("Caps:") < result.output.index("Captain:")


@pytest.mark.parametrize("caps, line", [
    ({"max_hits": 15, "max_transfers": 15}, "Caps: none"),
    ({"max_hits": 1, "max_transfers": 0}, "Caps: 1 hit/week, no transfers (bank)"),
    ({"max_hits": 15, "max_transfers": 2}, "Caps: hits uncapped, 2 transfers/week"),
])
def test_the_caps_line_wording(caps, line):
    from gaffer.cli import _caps_line

    assert _caps_line(caps) == line
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_advise.py -k "caps or _cap" tests/test_v13_degradation.py -k "caps or cli" -q`
Expected: FAIL — `ImportError` on `caps_from_state`, `_cap`, `_caps_line`.

- [ ] **Step 3: `caps_from_state` in `artifacts.py`**

Directly after the `OPT_REQUIRED_KEYS` docstring (before `def solve_kw_from_state`):

```python
def caps_from_state(state: SolveState) -> tuple[int | None, int | None]:
    """``(max_hits, max_transfers)`` the saved advice solved under.

    v13 §2.3. ``None`` means uncapped — both for a key the state never
    carried (written before v13) and for the ``NO_CAP`` sentinel the config
    stores. A What-If baseline, a draft's reference row and the ladder's
    highlight all read this, so the plan the report served and the plan the
    re-solve calls "original" are the same plan.
    """
    # Local import: this module is imported early by config's own callers
    # (see ``save_solve_state``'s ``serving_config`` import for the cycle).
    from gaffer.config import NO_CAP

    def cap(key: str) -> int | None:
        value = state.opt.get(key)
        if value is None:
            return None
        value = int(value)
        return None if value >= NO_CAP else value

    return cap("max_hits"), cap("max_transfers")
```

- [ ] **Step 4: The caps in `advise.py`**

Add to the imports: `from gaffer.config import NO_CAP` (there is already `from gaffer.config import Config` — extend that line to `from gaffer.config import NO_CAP, Config`).

Add to `class Advice`, after `alternative_plans: list[dict] = field(default_factory=list)`:

```python
    # v13 §2.3: the appetite this advice solved under, for the CLI line and
    # the report. ``None`` for the initial-squad build, which is uncapped.
    caps: dict | None = None
```

Directly above `def run_advise(`:

```python
def _cap(value: int) -> int | None:
    """A config cap as ``SolveInput`` wants it: ``NO_CAP`` and above is
    "no constraint"; anything else is the number."""
    return None if int(value) >= NO_CAP else int(value)
```

Replace the weekly `SolveInput` (the `else:` branch after `state, my_picks = initial_squad_state(gws)`):

```python
    else:
        my_picks = my.picks
        state = SolveInput(owned_codes=my.picks["code"].tolist(), bank=my.bank,
                           free_transfers=my.free_transfers, gws=gws,
                           # v13 §2.3: the manager's appetite, on the one
                           # SolveInput the sweep, the alternative plans and
                           # the chip table inherit through ``state``.
                           max_hits=_cap(cfg.max_hits),
                           max_transfers=_cap(cfg.max_transfers))
```

In the `Advice(` construction, after `alternative_plans=...` (find the keyword; add as the last argument):

```python
        caps=(None if my is None
              else {"max_hits": int(cfg.max_hits),
                    "max_transfers": int(cfg.max_transfers)}),
```

In `save_solve_state(SolveState(...))`, change the `opt=` argument to:

```python
        opt={**opt_kw, "horizon": cfg.horizon,
             "decision_priors": bool(cfg.decision_priors),
             # v13 §2.3: raw config values (15 = no cap); read back through
             # ``artifacts.caps_from_state`` by every re-solve of this board.
             "max_hits": int(cfg.max_hits),
             "max_transfers": int(cfg.max_transfers)},
```

- [ ] **Step 5: The CLI line**

In `src/gaffer/cli.py`, above `@app.command()\ndef advise(` add:

```python
def _caps_line(caps: dict) -> str:
    """'Caps: 2 hits/week, transfers uncapped' — v13 §2.3, one line."""
    from gaffer.config import NO_CAP

    hits = int(caps.get("max_hits", NO_CAP))
    moves = int(caps.get("max_transfers", NO_CAP))
    if hits >= NO_CAP and moves >= NO_CAP:
        return "Caps: none"
    hits_txt = ("hits uncapped" if hits >= NO_CAP
                else f"{hits} hit{'' if hits == 1 else 's'}/week")
    if moves >= NO_CAP:
        moves_txt = "transfers uncapped"
    elif moves == 0:
        moves_txt = "no transfers (bank)"
    else:
        moves_txt = f"{moves} transfer{'' if moves == 1 else 's'}/week"
    return f"Caps: {hits_txt}, {moves_txt}"
```

In `advise`, directly after

```python
    if advice.hits:
        typer.echo(f"Hits: -{advice.hits * 4}")
```

add:

```python
    # v13: absent on an Advice built without the field — which is what keeps
    # tests/test_v4c_degradation.py's character-for-character rail green.
    if getattr(advice, "caps", None):
        typer.echo(_caps_line(advice.caps))
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/test_advise.py tests/test_v13_degradation.py tests/test_v4c_degradation.py tests/test_web_whatif.py tests/test_artifacts.py -q`
Expected: all pass. Also `.venv/bin/python -c "import gaffer.advise, gaffer.cli"` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/advise.py src/gaffer/artifacts.py src/gaffer/cli.py tests/test_advise.py tests/test_v13_degradation.py
git commit -m "feat(v13): the caps ride the weekly SolveInput, the saved state and the CLI line; caps_from_state"
```

---

### Task 4: What-If and drafts — the baseline under the state's caps, `max_transfers` on the request

**Files:**
- Modify: `src/gaffer/web/schemas.py` (`WhatIfRequest` ~line 64-84)
- Modify: `src/gaffer/web/routers/whatif.py` (`_validate` end ~line 111; `solve_whatif` ~line 170-193)
- Modify: `src/gaffer/web/routers/drafts.py` (~line 148-173)
- Modify: `src/gaffer/drafts.py` (`CONSTRAINT_DEFAULTS`, `normalize` ~line 32-59)
- Test: `tests/test_web_whatif.py`, `tests/test_drafts.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_whatif.py`, change `_save_state`'s signature and `opt` so a test can add keys:

```python
def _save_state(gws=(1, 2), star_ep=9.0, lam=0.0, league_eo=None,
                chips=("wildcard", "bboost"), cover=None, opt_extra=None):
```

and the `opt=` argument becomes

```python
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": len(gws), **(opt_extra or {})},
```

Append:

```python
# --- v13: the baseline is the plan the report served -----------------------


def test_the_baseline_solves_under_the_saved_states_caps(tmp_path, monkeypatch):
    """A state that solved with ``max_transfers = 0`` (bank) was served a plan
    with no moves; its What-If baseline must be that plan, not a looser one."""
    monkeypatch.chdir(tmp_path)
    _save_state(opt_extra={"max_hits": 15, "max_transfers": 0})
    client = TestClient(create_app())
    job = _run(client, {"ban": [19]})
    assert job["status"] == "done", job["error"]
    assert job["result"]["baseline"]["buys"] == []


def test_max_transfers_on_the_request_caps_your_version(client):
    job = _run(client, {"max_transfers": 0})
    assert job["status"] == "done", job["error"]
    assert job["result"]["yours"]["buys"] == []
    assert 20 in [p["code"] for p in job["result"]["baseline"]["buys"]]


def test_a_negative_max_transfers_is_a_structured_422(client):
    resp = client.post("/api/whatif", json={"max_transfers": -1})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "max_transfers"
```

In `tests/test_drafts.py`, update the two pinned key sets:

```python
def test_unknown_constraint_keys_are_dropped(tmp_path, monkeypatch):
    """The store is fed by an HTTP body; it keeps the eight keys the solver
    understands and nothing else."""
    monkeypatch.chdir(tmp_path)
    add_draft("odd", {**CONSTRAINTS, "wildcard_everything": True})
    assert set(load_drafts()[0]["constraints"]) == {
        "lock", "ban", "force_in", "force_out", "max_hits", "max_transfers",
        "chip", "horizon"}


def test_missing_constraint_keys_get_their_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("bare", {})
    assert load_drafts()[0]["constraints"] == {
        "lock": [], "ban": [], "force_in": [], "force_out": [], "max_hits": 0,
        "max_transfers": None, "chip": "none", "horizon": None}
```

and change `CONSTRAINTS` at the top of that file to include `"max_transfers": None`:

```python
CONSTRAINTS = {"lock": [11], "ban": [], "force_in": [22], "force_out": [33],
               "max_hits": 1, "max_transfers": None, "chip": "none",
               "horizon": 3}
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_web_whatif.py -k "caps or max_transfers" tests/test_drafts.py -q`
Expected: FAIL (baseline still buys; `max_transfers` dropped by `normalize`).

- [ ] **Step 3: The request field**

`schemas.py`, in `WhatIfRequest`, after `max_hits: int = 0`:

```python
    # v13 §2.3. ``None`` is "no cap" (the baseline's cap is the saved state's,
    # never this); 0 is bank.
    max_transfers: int | None = None
```

- [ ] **Step 4: The routers**

`whatif.py`, `_validate`, after the `max_hits` check:

```python
    if req.max_transfers is not None and req.max_transfers < 0:
        raise _fail("max_transfers", "max_transfers cannot be negative", [])
```

`whatif.py`, `solve_whatif`: add `from gaffer.artifacts import caps_from_state` to the existing `from gaffer.artifacts import (...)` line, then replace the baseline construction:

```python
    # v13 §2.3: the baseline is the plan the report served, so it solves
    # under the caps the advice solved under. The user's version takes only
    # what the request says.
    base_hits, base_transfers = caps_from_state(state)
    base_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                            free_transfers=state.free_transfers, gws=gws,
                            max_hits=base_hits, max_transfers=base_transfers)
```

and in `yours_state` (the non-free-hit one) add `max_transfers=req.max_transfers` after `max_hits=req.max_hits`. The free-hit branch's `SolveInput` is unchanged (`max_hits=None`; `max_transfers` defaults to `None`).

`drafts.py` router, in `solve()`: the `req is None` branch becomes

```python
        if req is None:
            base_hits, base_transfers = caps_from_state(state)
            solve_state = SolveInput(owned_codes=state.owned_codes,
                                     bank=state.bank,
                                     free_transfers=state.free_transfers,
                                     gws=gws, max_hits=base_hits,
                                     max_transfers=base_transfers)
```

(add `caps_from_state` to that file's `from gaffer.artifacts import (...)`), and the ordinary branch adds `max_transfers=req.max_transfers` after `max_hits=req.max_hits`.

`src/gaffer/drafts.py`: `CONSTRAINT_DEFAULTS` gains `"max_transfers": None` after `"max_hits": 0`; the docstring says "eight keys"; `normalize` adds, after the `"max_hits"` line:

```python
        # v13: None is "no cap", so it is kept as None rather than coerced.
        "max_transfers": (None if raw.get("max_transfers") in (None, "")
                          else int(raw["max_transfers"])),
```

and its docstring says "The eight keys".

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/test_web_whatif.py tests/test_drafts.py tests/test_web_drafts.py tests/test_v12_w3_degradation.py tests/test_web_meta.py -q`
Expected: all pass. (If `tests/test_web_drafts.py` does not exist, drop it from the command.)

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/whatif.py src/gaffer/web/routers/drafts.py src/gaffer/drafts.py tests/test_web_whatif.py tests/test_drafts.py
git commit -m "feat(v13): What-If and drafts solve the baseline under the saved caps; max_transfers on the request"
```

---

### Task 5: Settings — two whitelist entries

**Files:**
- Modify: `src/gaffer/web/settings_keys.py` (module docstring line 1; `WHITELIST` ~line 72-116)
- Test: `tests/test_v13_degradation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_v13_degradation.py`:

```python
# --- Block 4: Settings ---------------------------------------------------

SETTINGS_BASE = """
[fpl]
entry_id = 111
league_id = 222

[optimizer]
horizon = 3
"""


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.config import optimizer_top_n, serving_config
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(SETTINGS_BASE)
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()


def test_the_settings_panel_serves_both_caps_with_their_range(settings_client):
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    assert rows["max_hits"]["value"] == 2
    assert rows["max_transfers"]["value"] == 15
    for key in ("max_hits", "max_transfers"):
        assert rows[key]["kind"] == "int"
        assert (rows[key]["lo"], rows[key]["hi"]) == (0, 15)
        assert rows[key]["section"] == "optimizer"
        assert rows[key]["source"] == "default"


def test_a_saved_cap_reaches_load_config(settings_client, tmp_path):
    import tomllib

    from gaffer.config import LOCAL_OVERLAY, load_config

    resp = settings_client.post("/api/settings",
                                json={"key": "max_hits", "value": 1})
    assert resp.status_code == 200, resp.text
    overlay = tomllib.loads((tmp_path / LOCAL_OVERLAY).read_text())
    assert overlay["optimizer"]["max_hits"] == 1
    assert load_config(tmp_path / "config.toml").max_hits == 1


def test_a_cap_above_fifteen_is_refused_at_the_endpoint(settings_client):
    resp = settings_client.post("/api/settings",
                                json={"key": "max_transfers", "value": 16})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "out_of_range"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_v13_degradation.py -k settings -q`
Expected: FAIL — `KeyError: 'max_hits'`.

- [ ] **Step 3: Add the entries**

In `settings_keys.py`, change the docstring's first line from `"""The nine settings the UI may edit (v12 W5 §6.2).` to `"""The eleven settings the UI may edit (v12 W5 §6.2; v13 added the two caps).`, and append to `WHITELIST`, after the `draw_availability` entry:

```python
    # v13 §2.3 (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md). The
    # appetite. Also editable from the ladder card on the This Week hub,
    # which writes through this same endpoint.
    SettingKey("max_hits", "optimizer", "max_hits", "Max hits per week",
               "int", 0, 15,
               "15 = no cap. The Thursday advice, its sweep, its alternatives "
               "and its chip table all solve under this. The transfer ladder "
               "on the This Week hub edits it too."),
    SettingKey("max_transfers", "optimizer", "max_transfers",
               "Max transfers per week", "int", 0, 15,
               "15 = no cap; 0 = bank (no moves at all). Also edited from "
               "the transfer ladder."),
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_v13_degradation.py tests/test_v12_w5_settings.py tests/test_v12_w5_degradation.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/web/settings_keys.py tests/test_v13_degradation.py
git commit -m "feat(v13): max_hits and max_transfers on the Settings whitelist, 0..15"
```

---

### Task 6: `gaffer/ladder.py` — rungs, shared draws, probabilities

**Files:**
- Create: `src/gaffer/ladder.py`
- Create: `tests/test_ladder.py`
- Test: `tests/test_v13_degradation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ladder.py`:

```python
"""v13 §3 — the transfer ladder's arithmetic, on a hand-built saved state."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gaffer.artifacts import SolveState, pool_rows, save_solve_state

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]


def _pool_frame():
    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": 50, "sell": 50})
            code += 1
    return pd.DataFrame(rows)


def save_state(opt_extra=None, star=9.0, second=7.0, gws=(1, 2)):
    """Code 20 is worth a free transfer, code 19 is worth a hit (5 EP/GW over
    two weeks against a 4-point hit), nothing else moves."""
    frame = _pool_frame()
    players = pd.DataFrame({"code": frame["code"],
                            "name": [f"P{c}" for c in frame["code"]]})
    ep = {20: star, 19: second}
    ep_by = {(int(c), g): ep.get(int(c), 2.0)
             for c in frame["code"] for g in gws}
    save_solve_state(SolveState(
        gw=gws[0], gws=list(gws), deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=0.0, league_eo={},
        avail_by_gw={g: [] for g in gws},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": len(gws), **(opt_extra or {})},
        pool=pool_rows(frame, players, OWNED, ep_by, list(gws))))
    return ep_by


@pytest.fixture()
def board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return save_state({"max_hits": 2, "max_transfers": 15})


def _zero_noise(monkeypatch):
    from gaffer import ladder

    monkeypatch.setattr(ladder, "OUTCOME_VAR_PER_EP", 0.0)
    monkeypatch.setattr(ladder, "sigma_table", lambda gw: ({}, "outcome_only"))


def test_with_no_noise_every_probability_is_zero_or_one_and_mean_is_horizon(
        board, monkeypatch):
    from gaffer.ladder import build_ladder

    _zero_noise(monkeypatch)
    out = build_ladder(1, n_draws=25, seed=1)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert len(distinct) >= 2
    for r in distinct:
        assert r["mean_pts"] == pytest.approx(r["horizon_pts"], abs=0.01)
        assert r["p10_pts"] == pytest.approx(r["mean_pts"], abs=0.01)
        for key in ("p_beats_bank", "p_beats_top"):
            assert r[key] in (None, 0.0, 1.0)
    assert out["sigma_source"] == "outcome_only"


def test_the_rungs_come_in_ladder_order_and_coincident_ones_say_so(board):
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=25, seed=1)
    keys = [r["key"] for r in out["rungs"]]
    assert keys[:5] == ["bank", "hits0", "hits1", "hits2", "hits3"]
    by = {r["key"]: r for r in out["rungs"]}
    assert by["bank"]["transfers"] == 0 and by["bank"]["p_beats_bank"] is None
    assert [b["code"] for b in by["hits0"]["plan_by_gw"][0]["buys"]] == [20]
    assert sorted(b["code"] for b in by["hits1"]["plan_by_gw"][0]["buys"]) \
        == [19, 20]
    assert by["hits1"]["hits"] == 1 and by["hits1"]["cost"] == 4
    # Nothing is worth a second hit, so the two upper rungs collapse onto
    # hits1 and carry no numbers of their own.
    assert by["hits2"]["same_as"] == "hits1"
    assert by["hits3"]["same_as"] == "hits1"
    assert by["hits3"]["mean_pts"] is None and by["hits3"]["plan_by_gw"] == []
    assert "open" not in keys


def test_p_best_sums_to_one_over_the_distinct_rungs(board):
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=40, seed=3)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert sum(r["p_best"] for r in distinct) == pytest.approx(1.0, abs=1e-6)
    for r in distinct:
        for key in ("p_beats_bank", "p_beats_top", "p_best"):
            assert r[key] is None or 0.0 <= r[key] <= 1.0


def test_the_cap_rung_and_the_recommended_rung(board, monkeypatch):
    """cap_rung follows the saved caps; recommended matches the served
    advice's first-week buys, sells and captain when an advice is on disk."""
    import json
    from pathlib import Path

    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": 2, "max_transfers": None}
    assert out["cap_rung"] == "hits2"
    assert out["recommended"] is None          # no gw1-advice.json yet

    hits1 = next(r for r in out["rungs"] if r["key"] == "hits1")
    first = hits1["plan_by_gw"][0]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/gw1-advice.json").write_text(json.dumps({
        "buys": [{"code": b["code"]} for b in first["buys"]],
        "sells": [{"code": s["code"]} for s in first["sells"]],
        "captain": {"code": first["captain"]["code"]}}))
    assert build_ladder(1, n_draws=10, seed=1)["recommended"] == "hits1"


def test_a_bank_cap_and_an_uncapped_state_pick_their_rungs(tmp_path,
                                                            monkeypatch):
    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 15, "max_transfers": 0})
    assert build_ladder(1, n_draws=10, seed=1)["cap_rung"] == "bank"
    save_state({})
    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": None, "max_transfers": None}
    assert out["cap_rung"] == out["rungs"][-1]["key"]


def test_the_seed_reproduces_the_payload(board):
    from gaffer.ladder import build_ladder

    a = build_ladder(1, n_draws=30, seed=11)
    b = build_ladder(1, n_draws=30, seed=11)
    for payload in (a, b):
        payload.pop("generated_at"), payload.pop("wall_s")
    assert a == b


def test_the_payload_is_banked_and_reloads(board):
    from gaffer.ladder import build_ladder, ladder_path, load_ladder

    out = build_ladder(1, n_draws=10, seed=1)
    assert ladder_path(1).exists()
    assert load_ladder(1)["rungs"][0]["key"] == out["rungs"][0]["key"]
    assert load_ladder(7) is None


def test_score_plan_uses_one_shared_draw_per_player_week():
    from gaffer.ladder import score_plan

    draws = {(1, 1): np.array([3.0, 5.0]), (2, 1): np.array([1.0, 2.0])}
    plan = SimpleNamespace(gw=1, xi=[1, 2], captain=1, hits=1)
    a = score_plan([plan], draws, hit_cost=4, n_draws=2)
    b = score_plan([plan], draws, hit_cost=4, n_draws=2)
    # XI 4/7, captain again 3/5, minus one hit: 3 and 8, identically twice.
    assert a.tolist() == [3.0, 8.0] and b.tolist() == a.tolist()


def test_p_best_splits_ties():
    from gaffer.ladder import p_best

    shares = p_best({"a": np.array([1.0, 2.0]), "b": np.array([1.0, 1.0])})
    assert shares == {"a": 0.75, "b": 0.25}


def test_vs_below_is_set_arithmetic_on_the_first_week():
    from gaffer.ladder import vs_below

    meta = {19: {"name": "P19", "position": "FWD"},
            20: {"name": "P20", "position": "FWD"},
            16: {"name": "P16", "position": "FWD"},
            17: {"name": "P17", "position": "FWD"}}
    ep_by = {(19, 1): 7.0, (20, 1): 9.0, (16, 1): 2.0, (17, 1): 2.0}
    below = SimpleNamespace(gw=1, buys=[20], sells=[16], hits=0)
    rung = SimpleNamespace(gw=1, buys=[19, 20], sells=[16, 17], hits=1)
    out = vs_below(below, rung, prev_mean=100.0, mean=103.5, hit_cost=4,
                   meta=meta, ep_by=ep_by)
    assert [p["code"] for p in out["extra_buys"]] == [19]
    assert [p["code"] for p in out["extra_sells"]] == [17]
    assert out["dropped_buys"] == [] and out["dropped_sells"] == []
    assert out["delta_mean_pts"] == 3.5 and out["delta_cost"] == 4
```

Append to `tests/test_v13_degradation.py`:

```python
# --- Block 5: the ladder's shape on the golden board ----------------------

def test_build_ladder_on_a_saved_board_has_the_spec_shape(tmp_path,
                                                          monkeypatch):
    from tests.test_ladder import save_state

    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 2, "max_transfers": 15})
    out = build_ladder(1, n_draws=20, seed=5)
    assert out["gw"] == 1 and out["n_draws"] == 20 and out["seed"] == 5
    assert out["free_transfers"] == 1
    assert [r["key"] for r in out["rungs"]][:5] == \
        ["bank", "hits0", "hits1", "hits2", "hits3"]
    assert len(out["rungs"]) in (5, 6)
    for r in out["rungs"]:
        assert set(r) >= {"key", "hits", "transfers", "cost", "same_as",
                          "plan_by_gw", "week_pts", "horizon_pts",
                          "objective", "mean_pts", "p10_pts", "p90_pts",
                          "p_beats_bank", "p_beats_top", "p_best",
                          "vs_below"}
    bank = out["rungs"][0]
    assert bank["p_beats_bank"] is None and bank["vs_below"] is None
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert sum(r["p_best"] for r in distinct) == pytest.approx(1.0, abs=1e-6)
    assert any(r["same_as"] for r in out["rungs"])
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_ladder.py tests/test_v13_degradation.py -k ladder -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.ladder'`.

- [ ] **Step 3: Write `src/gaffer/ladder.py`**

```python
"""The transfer ladder (v13 §3, specs/2026-09-04-gaffer-v13-transfer-ladder-design.md).

One row per rung of appetite — *bank*, then 0, 1, 2 and 3 hits, and an
*open* row only when the uncapped solve spends more than three — each
solved off the saved board exactly as the What-If lab re-solves it, and
every fixed plan then scored on **one** matrix of noise draws. Shared draws
are what make the rows comparable: the players two rungs have in common
score identically in every draw, so P(rung k beats rung j) is a statement
about the players that differ and nothing else.

The noise is the *outcome* distribution the squad table's bands already show
(:func:`gaffer.uncertainty.bands_by_player_gw`), not the sensitivity card's
narrower estimation σ. "Will two hits actually outscore one" is a question
about what the players score, so the probabilities here are closer to a
coin flip than that card's margins, and the spec chose that on purpose.

The board is built as ``sensitivity.run_sensitivity`` builds it — saved
state, raw EP, the cover table converted from ``league_eo`` when the state
predates it, ``tilt_ep``, ``milp_pool``, ``solve_kw_from_state`` — and the
idiom is repeated rather than shared, for the reason that module records:
two tests pin ``solve_whatif``'s own source text.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from gaffer import artifacts
from gaffer.artifacts import (caps_from_state, latest_gw, load_advice,
                              load_components, load_solve_state, milp_pool,
                              raw_ep_by, solve_kw_from_state)
from gaffer.errors import GafferError
from gaffer.io import atomic_write
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.league_sim import OUTCOME_VAR_PER_EP
from gaffer.optimize.milp import GwPlan, Plan, SolveInput, solve_plan
from gaffer.uncertainty import bands_by_player_gw

LADDER_DRAWS = 200
"""Draws per rung. Two hundred resolves a probability to about ±3.5%, which
is the precision the card prints (whole percents) and no finer."""

LADDER_HITS = (0, 1, 2, 3)
"""The hit rungs. Above three the *open* row exists only if the solver wants
it, so the table never lists a rung nobody would take."""

SEED_OFFSET = 2_000_000
"""Two million clear of the advice sweep's ``scenarios_seed + gw`` and one
million clear of the sensitivity sweep's, so the three draw independent
noise rather than replaying each other."""


def ladder_path(gw: int) -> Path:
    return artifacts.REPORTS / f"ladder_gw{gw}.json"


def load_ladder(gw: int) -> dict | None:
    """The banked ladder for ``gw``, or ``None`` — ``load_sensitivity``'s
    contract: a missing report is a card with a rebuild button, not an
    error."""
    path = ladder_path(gw)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — a corrupt report is no report
        print(f"ladder report unreadable: {exc}")
        return None


def save_ladder(payload: dict, gw: int) -> Path:
    """Atomic, like every other banked report."""
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = ladder_path(gw)
    atomic_write(path, json.dumps(payload, indent=1, allow_nan=False))
    return path


def signature(first: GwPlan) -> tuple:
    """First-week buys, sells and captain — the decision a rung represents
    (``sensitivity.plan_signature``'s definition)."""
    return (tuple(sorted(int(c) for c in first.buys)),
            tuple(sorted(int(c) for c in first.sells)),
            int(first.captain))


def plan_points(gw_plans: list[GwPlan], ep_by: dict, hit_cost: int) -> float:
    """XI plus the captain again, minus the hits, on **raw** EP — the
    measure ``routers/whatif._summary`` and ``sensitivity.plan_value`` use."""
    total = 0.0
    for plan in gw_plans:
        def ep(code) -> float:
            return float(ep_by.get((int(code), int(plan.gw)), 0.0))

        total += sum(ep(c) for c in plan.xi) + ep(plan.captain)
        total -= plan.hits * hit_cost
    return round(total, 2)


def sigma_table(gw: int) -> tuple[dict[tuple[int, int], float], str]:
    """``{(code, gw): σ}`` off the banked components frame, and where it
    came from. ``{}`` with ``"outcome_only"`` when no frame is banked, and
    :func:`draw_points` then falls back cell by cell."""
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — a ladder is not worth a crash
        print(f"ladder: no component breakdown ({exc})")
        return {}, "outcome_only"
    bands = bands_by_player_gw(comp)
    if not bands:
        return {}, "outcome_only"
    return {key: float(band.sigma) for key, band in bands.items()}, "bands"


def draw_points(keys, ep_by: dict, sigmas: dict, rng: np.random.Generator,
                n_draws: int) -> dict[tuple[int, int], np.ndarray]:
    """One vector of ``n_draws`` points per player-week, ``max(0, N(ep, σ))``.

    Keys are visited in sorted order so the draw a player-week receives is a
    function of the seed and the set, never of which rung named him first.
    """
    out: dict[tuple[int, int], np.ndarray] = {}
    for key in sorted(keys):
        mu = float(ep_by.get(key, 0.0))
        sigma = sigmas.get(key)
        if sigma is None:
            sigma = math.sqrt(OUTCOME_VAR_PER_EP * max(mu, 0.0))
        out[key] = np.maximum(0.0, mu + float(sigma)
                              * rng.standard_normal(n_draws))
    return out


def score_plan(gw_plans, draws: dict, hit_cost: int,
               n_draws: int) -> np.ndarray:
    """A fixed plan's horizon points in every draw: XI plus the captain
    again, minus the hits, undecayed, the vice and the bench ignored —
    :func:`plan_points` per draw."""
    total = np.zeros(n_draws)
    for plan in gw_plans:
        gw = int(plan.gw)
        for code in plan.xi:
            total += draws[(int(code), gw)]
        total += draws[(int(plan.captain), gw)]
        total -= float(plan.hits * hit_cost)
    return total


def p_best(scores: dict[str, np.ndarray]) -> dict[str, float]:
    """The share of draws each rung is the maximum in, ties split evenly."""
    keys = list(scores)
    matrix = np.stack([scores[k] for k in keys])            # rungs × draws
    winners = (matrix == matrix.max(axis=0)).astype(float)
    share = winners / winners.sum(axis=0)
    return {k: float(share[i].mean()) for i, k in enumerate(keys)}


def _refs(codes, gw: int, meta: dict, ep_by: dict) -> list[dict]:
    return [{"code": int(c),
             "name": str(meta.get(int(c), {}).get("name", c)),
             "position": str(meta.get(int(c), {}).get("position", "")),
             "ep": round(float(ep_by.get((int(c), int(gw)), 0.0)), 2)}
            for c in codes]


def vs_below(below, rung, *, prev_mean: float, mean: float, hit_cost: int,
             meta: dict, ep_by: dict) -> dict:
    """What the extra hit bought: the first-week moves this rung makes that
    the rung below did not (and any it dropped), the mean-points gain and
    the points it cost."""
    below_buys, buys = set(int(c) for c in below.buys), set(int(c) for c in rung.buys)
    below_sells, sells = set(int(c) for c in below.sells), set(int(c) for c in rung.sells)
    return {
        "extra_buys": _refs(sorted(buys - below_buys), rung.gw, meta, ep_by),
        "extra_sells": _refs(sorted(sells - below_sells), rung.gw, meta, ep_by),
        "dropped_buys": _refs(sorted(below_buys - buys), below.gw, meta, ep_by),
        "dropped_sells": _refs(sorted(below_sells - sells), below.gw, meta,
                               ep_by),
        "delta_mean_pts": round(float(mean - prev_mean), 2),
        "delta_cost": int((int(rung.hits) - int(below.hits)) * hit_cost),
    }


def _week(plan: GwPlan, meta: dict, ep_by: dict, hit_cost: int) -> dict:
    return {"gw": int(plan.gw), "hits": int(plan.hits),
            "buys": _refs(plan.buys, plan.gw, meta, ep_by),
            "sells": _refs(plan.sells, plan.gw, meta, ep_by),
            "xi": _refs(plan.xi, plan.gw, meta, ep_by),
            "bench": _refs(plan.bench, plan.gw, meta, ep_by),
            "captain": _refs([plan.captain], plan.gw, meta, ep_by)[0],
            "vice": _refs([plan.vice], plan.gw, meta, ep_by)[0],
            "expected_pts": plan_points([plan], ep_by, hit_cost)}


def _empty_rung(key: str, hits: int, transfers: int, cost: int,
                same_as: str) -> dict:
    return {"key": key, "hits": hits, "transfers": transfers, "cost": cost,
            "same_as": same_as, "plan_by_gw": [], "week_pts": None,
            "horizon_pts": None, "objective": None, "mean_pts": None,
            "p10_pts": None, "p90_pts": None, "p_beats_bank": None,
            "p_beats_top": None, "p_best": None, "vs_below": None}


def _cap_rung(max_hits: int | None, max_transfers: int | None,
              keys: list[str]) -> str:
    if max_transfers == 0:
        return "bank"
    if max_hits is None or max_hits > max(LADDER_HITS):
        return keys[-1]
    return f"hits{int(max_hits)}"


def _recommended(gw: int, solved: list[tuple[str, Plan]]) -> str | None:
    """The rung whose first-week decision is the served advice's, or None."""
    try:
        advice = load_advice(gw)
        wanted = (tuple(sorted(int(b["code"]) for b in advice.get("buys", []))),
                  tuple(sorted(int(s["code"]) for s in advice.get("sells", []))),
                  int(advice["captain"]["code"]))
    except Exception as exc:  # noqa: BLE001 — no advice is no chip, not a crash
        print(f"ladder: no served advice to mark ({exc})")
        return None
    for key, plan in solved:
        if signature(plan.gw_plans[0]) == wanted:
            return key
    return None


def build_ladder(gw: int | None = None, *, n_draws: int = LADDER_DRAWS,
                 seed: int | None = None) -> dict:
    """Solve every rung off the saved board, score them on shared draws,
    bank the payload. The job body and the end of ``advise``'s run.

    Raises :class:`GafferError` when there is no saved state — the job
    runner's cue to say "run `gaffer advise` first" rather than 500.
    """
    gw = latest_gw() if gw is None else int(gw)
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    hit_cost = int(opt["hit_cost"])
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}
    if seed is None:
        from gaffer.config import serving_config
        seed = int(serving_config().scenarios_seed) + SEED_OFFSET + int(gw)
    n_draws = max(1, int(n_draws))
    started = time.perf_counter()

    base = dict(owned_codes=state.owned_codes, bank=state.bank,
                free_transfers=state.free_transfers, gws=gws)
    specs: list[tuple[str, SolveInput]] = [
        ("bank", SolveInput(**base, max_transfers=0))]
    specs += [(f"hits{k}", SolveInput(**base, max_hits=k))
              for k in LADDER_HITS]
    specs.append(("open", SolveInput(**base)))

    solved: list[tuple[str, Plan]] = []
    for key, solve_state in specs:
        plan = solve_plan(pool, solve_state, **opt)
        if key == "open" and plan.gw_plans[0].hits <= max(LADDER_HITS):
            continue
        solved.append((key, plan))

    # Distinct rungs solve and score; a rung whose first-week decision is the
    # rung below's is kept as a row that says so and carries no numbers.
    distinct: list[tuple[str, Plan]] = []
    same_as: dict[str, str] = {}
    for key, plan in solved:
        if distinct and signature(plan.gw_plans[0]) == signature(
                distinct[-1][1].gw_plans[0]):
            same_as[key] = distinct[-1][0]
        else:
            distinct.append((key, plan))

    keys_needed: set[tuple[int, int]] = set()
    for _, plan in distinct:
        for week in plan.gw_plans:
            keys_needed.update((int(c), int(week.gw)) for c in week.xi)
            keys_needed.add((int(week.captain), int(week.gw)))
    sigmas, sigma_source = sigma_table(gw)
    rng = np.random.default_rng(int(seed))
    draws = draw_points(keys_needed, ep_by, sigmas, rng, n_draws)
    scores = {key: score_plan(plan.gw_plans, draws, hit_cost, n_draws)
              for key, plan in distinct}
    best = p_best(scores)
    top_key = distinct[-1][0]

    rows: list[dict] = []
    by_key: dict[str, dict] = {}
    prev: tuple[str, Plan] | None = None
    for key, plan in solved:
        if key in same_as:
            src = by_key[same_as[key]]
            row = _empty_rung(key, src["hits"], src["transfers"],
                              src["cost"], same_as[key])
            rows.append(row)
            by_key[key] = row
            continue
        first = plan.gw_plans[0]
        sc = scores[key]
        mean = float(sc.mean())
        row = {
            "key": key, "hits": int(first.hits),
            "transfers": int(len(first.buys)),
            "cost": int(first.hits * hit_cost), "same_as": None,
            "plan_by_gw": [_week(p, meta, ep_by, hit_cost)
                           for p in plan.gw_plans],
            "week_pts": plan_points(plan.gw_plans[:1], ep_by, hit_cost),
            "horizon_pts": plan_points(plan.gw_plans, ep_by, hit_cost),
            "objective": round(float(plan.objective), 2),
            "mean_pts": round(mean, 2),
            "p10_pts": round(float(np.percentile(sc, 10)), 2),
            "p90_pts": round(float(np.percentile(sc, 90)), 2),
            "p_beats_bank": (None if key == "bank"
                             else round(float((sc > scores["bank"]).mean()), 4)),
            "p_beats_top": (None if key == top_key
                            else round(float((sc > scores[top_key]).mean()), 4)),
            "p_best": round(best[key], 4),
            "vs_below": (None if prev is None else vs_below(
                prev[1].gw_plans[0], first,
                prev_mean=float(scores[prev[0]].mean()), mean=mean,
                hit_cost=hit_cost, meta=meta, ep_by=ep_by)),
        }
        rows.append(row)
        by_key[key] = row
        prev = (key, plan)

    max_hits, max_transfers = caps_from_state(state)
    payload = {
        "gw": int(gw), "gws": [int(g) for g in gws],
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "free_transfers": int(state.free_transfers),
        "cap": {"max_hits": max_hits, "max_transfers": max_transfers},
        "cap_rung": _cap_rung(max_hits, max_transfers,
                              [r["key"] for r in rows]),
        "recommended": _recommended(gw, solved),
        "n_draws": n_draws, "seed": int(seed), "sigma_source": sigma_source,
        "wall_s": round(time.perf_counter() - started, 1),
        "rungs": rows,
    }
    save_ladder(payload, gw)
    return payload
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_ladder.py tests/test_v13_degradation.py -q`
Expected: all pass. If `test_the_rungs_come_in_ladder_order...` reports `hits1` buying only `[20]`, the second star is not worth a hit on this pool at this decay — raise `second=` in `save_state` to `8.0` and re-run; the assertion set is otherwise unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/ladder.py tests/test_ladder.py tests/test_v13_degradation.py
git commit -m "feat(v13): gaffer.ladder — bank/0/1/2/3-hit rungs off the saved board, scored on shared outcome draws"
```

---

### Task 7: `advise` builds the ladder after it saves the state

**Files:**
- Modify: `src/gaffer/advise.py` (imports; the block after `save_solve_state(...)` ~line 1159-1178)
- Test: `tests/test_advise.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_advise.py`:

```python
def test_run_advise_builds_the_ladder_after_the_state_and_never_fails_on_it():
    """v13 §3.2, source-level like the artifact seams above: the ladder is
    solved off the state just saved, sits between the state write and the
    availability write, and is wrapped so its failure is one printed line."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    state = src.index("save_solve_state(")
    ladder = src.index("build_ladder(gw)")
    avail = src.index("save_availability(avail, gw)")
    assert state < ladder < avail
    guard = src[src.rindex("try:", 0, ladder):ladder]
    assert "try:" in guard
    assert 'print(f"ladder: not built for GW{gw} ({exc})")' in src
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/pytest tests/test_advise.py -k ladder -q`
Expected: FAIL — `ValueError: substring not found`.

- [ ] **Step 3: The call**

Add to `advise.py`'s imports: `from gaffer.ladder import build_ladder`.

Directly after the `save_solve_state(SolveState(...))` call and before the comment block that begins `# Two artifacts nothing in the pipeline reads`, insert:

```python
    # v13 §3.2: the transfer ladder, off the state just saved. Never the
    # run's failure — a ladder that could not be built is one printed line
    # and a card with a rebuild button.
    try:
        build_ladder(gw)
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: not built for GW{gw} ({exc})")
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_advise.py tests/test_v4c_degradation.py -q && .venv/bin/python -c "import gaffer.advise"`
Expected: all pass; the import prints nothing (no cycle).

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/advise.py tests/test_advise.py
git commit -m "feat(v13): advise builds the ladder after saving the state, guarded"
```

---

### Task 8: `GET`/`POST /api/ladder`, the schemas, the route pin

**Files:**
- Modify: `src/gaffer/web/schemas.py` (after `SensitivityReport`, before `class DraftRow`)
- Create: `src/gaffer/web/routers/ladder.py`
- Modify: `src/gaffer/web/app.py` (the `from gaffer.web.routers import (...)` list ~line 26; `include_router` block ~line 82-107)
- Modify: `tests/test_v11_degradation.py:368` (and its docstring)
- Create: `tests/test_web_ladder.py`
- Modify: `frontend/src/schemas.json`, `frontend/src/types.generated.ts` (regenerated)
- Test: `tests/test_v13_degradation.py`, `tests/test_v12_w5_gen_types.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_ladder.py`:

```python
"""v13 §3.2 — GET and POST /api/ladder against a hand-built solve state."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app
from gaffer.web.jobs import JobQueueFull
from tests.test_ladder import save_state


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 2, "max_transfers": 15})
    return TestClient(create_app())


def _wait(client, job_id):
    for _ in range(4000):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
    raise AssertionError("job never finished")


def test_get_with_no_state_is_an_empty_payload_with_a_note(tmp_path,
                                                           monkeypatch):
    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/ladder").json()
    assert body["gw"] is None and body["rungs"] == []
    assert "gaffer advise" in body["note"]


def test_get_before_a_build_names_the_gameweek_and_says_rebuild(client):
    body = client.get("/api/ladder").json()
    assert body["gw"] == 1 and body["rungs"] == []
    assert "rebuild" in body["note"]


def test_post_builds_banks_and_get_then_serves_it(client):
    resp = client.post("/api/ladder")
    assert resp.status_code == 202, resp.text
    job = _wait(client, resp.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert job["result"]["rungs"][0]["key"] == "bank"
    body = client.get("/api/ladder").json()
    assert body["gw"] == 1 and body["note"] is None
    assert [r["key"] for r in body["rungs"]][:5] == \
        ["bank", "hits0", "hits1", "hits2", "hits3"]
    assert body["cap"] == {"max_hits": 2, "max_transfers": None}
    assert body["cap_rung"] == "hits2"


def test_a_full_queue_is_a_429(client):
    app = client.app

    def full(fn, timeout_s):
        raise JobQueueFull("queue full")

    app.state.jobs.submit = full
    resp = client.post("/api/ladder")
    assert resp.status_code == 429
    assert "full" in resp.json()["detail"]


def test_post_with_no_state_is_the_advise_first_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resp = TestClient(create_app()).post("/api/ladder")
    assert resp.status_code in (400, 422)
    assert "gaffer advise" in resp.text
```

Append to `tests/test_v13_degradation.py`:

```python
# --- Block 6: routes and kinds -------------------------------------------

def test_the_ladder_route_exists_and_the_job_kinds_did_not_move(tmp_path,
                                                                monkeypatch):
    """By name, never by total: the absolute route count lives in
    ``test_v11_degradation.py`` alone (47 → 48 there; GET and POST share one
    path key, as ``/api/settings`` did). No thirteenth kind: the rebuild is
    an anonymous ``JobRegistry`` submission like What-If."""
    from gaffer.web.app import create_app
    from gaffer.web.job_kinds import JOB_KINDS

    monkeypatch.chdir(tmp_path)
    paths = create_app().openapi()["paths"]
    assert "/api/ladder" in paths
    assert {"get", "post"} <= set(paths["/api/ladder"])
    assert len(JOB_KINDS) == 12
```

In `tests/test_v11_degradation.py`, change `    assert len(paths) == 47` to `    assert len(paths) == 48`, add `    assert "/api/ladder" in paths` after `    assert "/api/settings" in paths`, and append to the docstring before its closing quotes:

```
    # v13 §3.2 (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md)
    47 → 48, and the one is ``/api/ladder`` — GET and POST share one path
    key, like ``/api/settings`` — the transfer ladder.
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_web_ladder.py tests/test_v13_degradation.py -k route tests/test_v11_degradation.py -k route_total -q`
Expected: FAIL — 404s and `47 != 48`.

- [ ] **Step 3: The schemas**

In `schemas.py`, directly after `class SensitivityReport` (before `class DraftRow`):

```python
# --- v13 §3: the transfer ladder ------------------------------------------


class LadderVsBelow(BaseModel):
    """What the extra hit bought, against the previous distinct rung."""

    extra_buys: list[PlayerRef] = Field(default_factory=list)
    extra_sells: list[PlayerRef] = Field(default_factory=list)
    dropped_buys: list[PlayerRef] = Field(default_factory=list)
    dropped_sells: list[PlayerRef] = Field(default_factory=list)
    delta_mean_pts: float
    delta_cost: int


class LadderWeek(BaseModel):
    gw: int
    hits: int
    buys: list[PlayerRef] = Field(default_factory=list)
    sells: list[PlayerRef] = Field(default_factory=list)
    xi: list[PlayerRef] = Field(default_factory=list)
    bench: list[PlayerRef] = Field(default_factory=list)
    captain: PlayerRef
    vice: PlayerRef
    expected_pts: float


class LadderRung(BaseModel):
    """One row. Every number is ``None`` on a ``same_as`` row, which repeats
    the rung below rather than re-solving it."""

    key: str
    hits: int
    transfers: int
    cost: int
    same_as: str | None = None
    plan_by_gw: list[LadderWeek] = Field(default_factory=list)
    week_pts: float | None = None
    horizon_pts: float | None = None
    objective: float | None = None
    mean_pts: float | None = None
    p10_pts: float | None = None
    p90_pts: float | None = None
    p_beats_bank: float | None = None
    p_beats_top: float | None = None
    p_best: float | None = None
    vs_below: LadderVsBelow | None = None


class LadderCap(BaseModel):
    max_hits: int | None = None
    max_transfers: int | None = None


class LadderPayload(BaseModel):
    gw: int | None = None
    gws: list[int] = Field(default_factory=list)
    generated_at: str | None = None
    free_transfers: int | None = None
    cap: LadderCap = Field(default_factory=LadderCap)
    cap_rung: str | None = None
    recommended: str | None = None
    n_draws: int = 0
    seed: int | None = None
    sigma_source: str | None = None
    wall_s: float | None = None
    rungs: list[LadderRung] = Field(default_factory=list)
    note: str | None = None
    """Why ``rungs`` is empty, when it is: no state, or no ladder banked."""
```

- [ ] **Step 4: The router**

Create `src/gaffer/web/routers/ladder.py`:

```python
"""GET and POST /api/ladder — the transfer ladder (v13 §3.2).

GET serves the banked payload for the latest gameweek and is a 200 for every
empty state it knows about. POST re-solves it as an anonymous job through
``app.state.jobs``, exactly as ``/api/whatif`` submits, and the job saves the
result so the next GET reflects it. No ``JOB_KINDS`` entry: a kind would need
an abandon-timeout row and a pin move for a computation that takes seconds.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import latest_gw
from gaffer.errors import GafferError
from gaffer.ladder import build_ladder, load_ladder
from gaffer.web.jobs import WHATIF_TIMEOUT_S, JobQueueFull
from gaffer.web.schemas import JobAccepted, LadderPayload

router = APIRouter(prefix="/api", tags=["ladder"])


@router.get("/ladder", response_model=LadderPayload)
def ladder(gw: int | None = Query(default=None)) -> LadderPayload:
    current = latest_gw()
    wanted = current if gw is None else int(gw)
    if wanted is None:
        return LadderPayload(
            note="no saved solve state — run `gaffer advise` first")
    payload = load_ladder(wanted)
    if payload is None:
        return LadderPayload(
            gw=wanted,
            note=f"no ladder for GW{wanted} — run `gaffer advise` or "
                 f"rebuild it here")
    fields = {k: v for k, v in payload.items()
              if k in LadderPayload.model_fields}
    return LadderPayload(**fields)


@router.post("/ladder", status_code=202, response_model=JobAccepted)
def rebuild(request: Request):
    gw = latest_gw()
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    try:
        job_id = request.app.state.jobs.submit(
            lambda: build_ladder(gw), timeout_s=WHATIF_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
```

In `app.py`, add `ladder` to the `from gaffer.web.routers import (...)` list (alphabetically, after `jobs, journal,`), and add `    app.include_router(ladder.router)` directly after `    app.include_router(journal.router)`.

- [ ] **Step 5: Regenerate the schema and the types**

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
writeFileSync('src/types.generated.ts',
  banner + await compile(schema, 'GafferApi', OPTIONS))
" && npx vitest run src/types.generated.test.ts && npx tsc --noEmit && cd ..
```

Expected: the vitest file passes (`Errors 0`); `tsc` is silent. `git diff --stat frontend/src/types.generated.ts` shows the four new interfaces and `max_transfers` on `WhatIfRequest` (tsc may now complain about the `WhatIfRequest` literals — that is Task 10's job; if it does, run `npx tsc --noEmit` again after Task 10 and note it in the commit).

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/test_web_ladder.py tests/test_v13_degradation.py tests/test_v11_degradation.py tests/test_v12_w1_degradation.py tests/test_v12_w5_degradation.py tests/test_v12_w5_gen_types.py tests/test_web_smoke.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/ladder.py src/gaffer/web/app.py tests/test_web_ladder.py tests/test_v13_degradation.py tests/test_v11_degradation.py frontend/src/schemas.json frontend/src/types.generated.ts
git commit -m "feat(v13): GET/POST /api/ladder, LadderPayload schemas, routes 47 -> 48, types regenerated"
```

---

### Task 9: `LadderCard`

**Files:**
- Create: `frontend/src/hubs/this-week/LadderCard.tsx`
- Create: `frontend/src/hubs/this-week/LadderCard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hubs/this-week/LadderCard.test.tsx`:

```tsx
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LadderPayload } from '../../types'
import LadderCard, { capText } from './LadderCard'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e),
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

const ref = (code: number, name: string, ep = 5.0) =>
  ({ code, name, position: 'MID', ep })

const week = (gw: number, hits: number, buys: ReturnType<typeof ref>[],
              sells: ReturnType<typeof ref>[]) => ({
  gw, hits, buys, sells,
  xi: [ref(1, 'Keeper'), ref(2, 'Back')], bench: [ref(3, 'Sub')],
  captain: ref(2, 'Back'), vice: ref(1, 'Keeper'), expected_pts: 60,
})

const PAYLOAD: LadderPayload = {
  gw: 3, gws: [3, 4, 5], generated_at: '2026-09-04T13:00:00+00:00',
  free_transfers: 1, cap: { max_hits: 2, max_transfers: null },
  cap_rung: 'hits2', recommended: 'hits1', n_draws: 200, seed: 7,
  sigma_source: 'bands', wall_s: 31.2, note: null,
  rungs: [
    { key: 'bank', hits: 0, transfers: 0, cost: 0, same_as: null,
      plan_by_gw: [week(3, 0, [], [])], week_pts: 60, horizon_pts: 180,
      objective: 170, mean_pts: 180, p10_pts: 160, p90_pts: 200,
      p_beats_bank: null, p_beats_top: 0.42, p_best: 0.2, vs_below: null },
    { key: 'hits0', hits: 0, transfers: 1, cost: 0, same_as: null,
      plan_by_gw: [week(3, 0, [ref(20, 'Star')], [ref(16, 'Dud')])],
      week_pts: 63, horizon_pts: 186, objective: 176, mean_pts: 186,
      p10_pts: 165, p90_pts: 207, p_beats_bank: 0.71, p_beats_top: 0.5,
      p_best: 0.3,
      vs_below: { extra_buys: [ref(20, 'Star')], extra_sells: [ref(16, 'Dud')],
                  dropped_buys: [], dropped_sells: [], delta_mean_pts: 6,
                  delta_cost: 0 } },
    { key: 'hits1', hits: 1, transfers: 2, cost: 4, same_as: null,
      plan_by_gw: [week(3, 1, [ref(20, 'Star'), ref(19, 'Second')],
                        [ref(16, 'Dud'), ref(17, 'Filler')])],
      week_pts: 64, horizon_pts: 188, objective: 177, mean_pts: 188,
      p10_pts: 166, p90_pts: 210, p_beats_bank: 0.74, p_beats_top: null,
      p_best: 0.5,
      vs_below: { extra_buys: [ref(19, 'Second')],
                  extra_sells: [ref(17, 'Filler')], dropped_buys: [],
                  dropped_sells: [], delta_mean_pts: 1.9, delta_cost: 4 } },
    { key: 'hits2', hits: 1, transfers: 2, cost: 4, same_as: 'hits1',
      plan_by_gw: [], week_pts: null, horizon_pts: null, objective: null,
      mean_pts: null, p10_pts: null, p90_pts: null, p_beats_bank: null,
      p_beats_top: null, p_best: null, vs_below: null },
    { key: 'hits3', hits: 1, transfers: 2, cost: 4, same_as: 'hits1',
      plan_by_gw: [], week_pts: null, horizon_pts: null, objective: null,
      mean_pts: null, p10_pts: null, p90_pts: null, p_beats_bank: null,
      p_beats_top: null, p_best: null, vs_below: null },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path === '/api/ladder') return PAYLOAD
    if (path.startsWith('/api/jobs/')) {
      return { id: 'j1', status: 'done', result: PAYLOAD, error: null }
    }
    throw new Error(`unexpected GET ${path}`)
  })
  apiPost.mockResolvedValue({ job_id: 'j1' })
})

function mount(props: Parameters<typeof LadderCard>[0] = {}) {
  return render(<MemoryRouter><LadderCard {...props} /></MemoryRouter>)
}

describe('LadderCard', () => {
  it('lists one row per rung with the moves, the cost and the odds', async () => {
    mount()
    const row = (await screen.findByText('1 hit')).closest('tr')!
    expect(row).toHaveTextContent('Star, Second')
    expect(row).toHaveTextContent('−4')
    expect(row).toHaveTextContent('74%')     // P(beats bank)
    expect(row).toHaveTextContent('50%')     // P(best)
    expect(screen.getByText('Bank').closest('tr')).toHaveTextContent('—')
  })

  it('highlights the cap rung and mutes the rungs beyond it', async () => {
    mount()
    const cap = (await screen.findByText('2 hits')).closest('tr')!
    expect(cap).toHaveAttribute('data-cap', 'true')
    const beyond = screen.getByText('3 hits').closest('tr')!
    expect(beyond).toHaveClass('text-text-muted')
    expect(beyond).toHaveAttribute('title', 'beyond your cap')
    expect(cap).not.toHaveClass('text-text-muted')
  })

  it('marks the recommended rung and says when a rung repeats the one below', async () => {
    mount()
    const rec = (await screen.findByText('1 hit')).closest('tr')!
    expect(within(rec).getByText('recommended')).toBeInTheDocument()
    expect(screen.getByText('2 hits').closest('tr'))
      .toHaveTextContent(/solver would not spend it — same as 1 hit/)
  })

  it('names the free transfers and the cap in the heading', async () => {
    mount()
    expect(await screen.findByText(/1 free transfer · cap 2 hits/))
      .toBeInTheDocument()
    expect(capText(PAYLOAD)).toBe('1 free transfer · cap 2 hits')
    expect(capText({ ...PAYLOAD, free_transfers: 2,
                     cap: { max_hits: null, max_transfers: 0 } }))
      .toBe('2 free transfers · hits uncapped · bank')
  })

  it('expands a rung to show what the last hit bought', async () => {
    mount()
    await userEvent.click(await screen.findByText('1 hit'))
    expect(screen.getByText(/\+ Second for Filler/)).toBeInTheDocument()
    expect(screen.getByText(/\+1.9 xPts over 3 GWs, −4 now/))
      .toBeInTheDocument()
    expect(screen.getByText('Back')).toBeInTheDocument()   // the XI
  })

  it('rebuilds through the job endpoint and reloads', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button',
                                                    { name: /rebuild/i }))
    expect(apiPost).toHaveBeenCalledWith('/api/ladder', undefined)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(3))
  })

  it('saves a changed cap through settings and then rebuilds', async () => {
    const onLoaded = vi.fn()
    mount({ onLoaded })
    await screen.findByText('1 hit')
    await userEvent.selectOptions(screen.getByLabelText('Max hits'), '1')
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/settings', { key: 'max_hits', value: 1 }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/ladder',
                                                              undefined))
    expect(onLoaded).toHaveBeenCalled()
  })

  it('offers a rebuild when nothing is banked yet', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/ladder') {
        return { ...PAYLOAD, rungs: [], note: 'no ladder for GW3 — rebuild' }
      }
      throw new Error(path)
    })
    mount()
    expect(await screen.findByText(/no ladder for GW3/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd frontend && npx vitest run src/hubs/this-week/LadderCard.test.tsx`
Expected: FAIL — cannot resolve `./LadderCard`.

- [ ] **Step 3: Write the card**

Create `frontend/src/hubs/this-week/LadderCard.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPost, errorText } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Badge, Card, PlayerName, Skeleton, TONE_CLASS, fmtNum, toneOf }
  from '../../kit'
import type { LadderPayload, LadderRung, PlayerRef } from '../../types'

/** `[optimizer]` value meaning "no cap" — `gaffer.config.NO_CAP`. */
export const NO_CAP = 15

const FIELD = 'rounded-card border border-border bg-base px-2 py-1 text-text'

/** "1 free transfer · cap 2 hits" — the heading, and MovesCard's line. */
export function capText(p: LadderPayload): string {
  const ft = p.free_transfers ?? 0
  const bits = [`${ft} free transfer${ft === 1 ? '' : 's'}`]
  const hits = p.cap.max_hits
  bits.push(hits === null || hits === undefined
    ? 'hits uncapped'
    : `cap ${hits} hit${hits === 1 ? '' : 's'}`)
  const moves = p.cap.max_transfers
  if (moves === 0) bits.push('bank')
  else if (moves !== null && moves !== undefined) {
    bits.push(`max ${moves} transfer${moves === 1 ? '' : 's'}`)
  }
  return bits.join(' · ')
}

function rungLabel(r: LadderRung): string {
  if (r.key === 'bank') return 'Bank'
  if (r.hits === 0) return 'No hits'
  return `${r.hits} hit${r.hits === 1 ? '' : 's'}`
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`
}

function movesText(r: LadderRung): string {
  const first = r.plan_by_gw[0]
  if (!first || first.buys.length === 0) return 'no moves'
  return first.buys.map((b) => b.name).join(', ')
}

function names(players: PlayerRef[]): string {
  return players.map((p) => p.name).join(', ')
}

function Players({ players }: { players: PlayerRef[] }) {
  if (players.length === 0) return <span className="text-text-muted">—</span>
  return (
    <ul className="flex flex-col gap-0.5">
      {players.map((p) => (
        <li key={p.code}>
          <PlayerName code={p.code} name={p.name} pos={p.position} />
        </li>
      ))}
    </ul>
  )
}

function Expanded({ rung, weeks }: { rung: LadderRung; weeks: number }) {
  const vb = rung.vs_below
  return (
    <div className="grid gap-4 py-2 sm:grid-cols-2">
      <div>
        <p className="label mb-1">This rung's squad</p>
        {rung.plan_by_gw.map((w) => (
          <div key={w.gw} className="mb-2">
            <p className="text-text-secondary">GW{w.gw}
              {w.hits > 0 && <span className="text-rust"> · {w.hits} hit{w.hits === 1 ? '' : 's'}</span>}
            </p>
            <div className="grid grid-cols-2 gap-2">
              <div><span className="label">In</span><Players players={w.buys} /></div>
              <div><span className="label">Out</span><Players players={w.sells} /></div>
            </div>
          </div>
        ))}
        {rung.plan_by_gw[0] && (
          <div>
            <p className="label">Starting XI (captain marked)</p>
            <ul className="flex flex-wrap gap-x-2">
              {rung.plan_by_gw[0].xi.map((p) => (
                <li key={p.code} className="text-text">
                  {p.name}{p.code === rung.plan_by_gw[0].captain.code ? ' (C)' : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div>
        <p className="label mb-1">What the last hit bought</p>
        {vb === null || vb === undefined
          ? <p className="text-text-muted">Nothing to compare against.</p>
          : (
            <p className="text-text">
              {vb.extra_buys.length > 0 && `+ ${names(vb.extra_buys)}`}
              {vb.extra_sells.length > 0 && ` for ${names(vb.extra_sells)}`}
              {vb.dropped_buys.length > 0 && ` (drops ${names(vb.dropped_buys)})`}
              {' '}
              <span className={TONE_CLASS[toneOf(vb.delta_mean_pts)]}>
                ({vb.delta_mean_pts >= 0 ? '+' : '−'}{fmtNum(Math.abs(vb.delta_mean_pts), 1)} xPts over {weeks} GWs, {vb.delta_cost > 0 ? `−${vb.delta_cost}` : `${vb.delta_cost}`} now)
              </span>
            </p>
            )}
      </div>
    </div>
  )
}

export interface LadderCardProps {
  /** Called with every payload this card loads, so a parent (This Week) can
   *  print the cap line on the moves card without a second request. */
  onLoaded?: (payload: LadderPayload) => void
}

export default function LadderCard({ onLoaded }: LadderCardProps = {}) {
  const [data, setData] = useState<LadderPayload | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const job = useJob('ladder')

  const load = useCallback(() => {
    apiGet<LadderPayload>('/api/ladder')
      .then((payload) => {
        setFailed(null)
        setData(payload)
        onLoaded?.(payload)
      })
      .catch((e) => { setFailed(errorText(e)); setData(null) })
  }, [onLoaded])
  useEffect(() => { load() }, [load])

  const rebuild = useCallback(() => {
    setOpen(null)
    job.start('/api/ladder')
  }, [job])

  // A finished rebuild is read back from the banked payload rather than the
  // job record, so the card and the next page load agree byte for byte.
  useEffect(() => {
    if (job.status === 'done') load()
  }, [job.status, load])

  const setCap = async (key: 'max_hits' | 'max_transfers', value: number) => {
    try {
      await apiPost('/api/settings', { key, value })
    } catch (e) {
      setFailed(errorText(e))
      return
    }
    rebuild()
  }

  const busy = job.status === 'queued' || job.status === 'running'
  const rungs = data?.rungs ?? []
  const weeks = data?.gws.length ?? 0
  const bank = rungs.find((r) => r.key === 'bank')
  const capIndex = rungs.findIndex((r) => r.key === data?.cap_rung)
  const hitsValue = data?.cap.max_hits ?? NO_CAP
  const movesValue = data?.cap.max_transfers ?? NO_CAP

  return (
    <Card
      title="Transfer ladder"
      className="mb-4"
      action={(
        <button
          type="button"
          onClick={rebuild}
          disabled={busy || !data?.gw}
          className="rounded-card border border-border bg-card px-2 py-1
                     text-text-secondary hover:text-text disabled:text-text-faint"
        >
          {busy ? 'Rebuilding…' : 'Rebuild'}
        </button>
      )}
    >
      {data && data.gw !== null && (
        <p className="mb-2 text-text-secondary">{capText(data)}</p>
      )}
      <p className="mb-3 text-text-muted">
        Every rung of appetite solved on the same board, then every plan
        scored on the same {data?.n_draws || 200} noise draws — so the rows
        are comparable and the players they share cancel out. Your cap is
        highlighted; the rungs beyond it stay visible so you can see what it
        costs.
      </p>
      <div className="mb-3 flex flex-wrap gap-3">
        <label className="flex items-center gap-2">
          <span className="label">Max hits</span>
          <select
            aria-label="Max hits"
            value={hitsValue}
            disabled={busy || !data?.gw}
            onChange={(e) => setCap('max_hits', Number(e.target.value))}
            className={FIELD}
          >
            {[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
            <option value={NO_CAP}>no cap</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="label">Max transfers</span>
          <select
            aria-label="Max transfers"
            value={movesValue}
            disabled={busy || !data?.gw}
            onChange={(e) => setCap('max_transfers', Number(e.target.value))}
            className={FIELD}
          >
            <option value={0}>bank</option>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            <option value={NO_CAP}>no cap</option>
          </select>
        </label>
      </div>
      {failed && <p className="mb-3 text-rust">{failed}</p>}
      {job.status === 'error' && (
        <p className="mb-3 text-rust">{job.error}</p>
      )}
      {busy && (
        <Skeleton bare lines={5}
                  label="Solving every rung and scoring the draws…" />
      )}
      {!busy && data && rungs.length === 0 && (
        <p className="text-text-muted">{data.note ?? 'No ladder yet.'}</p>
      )}
      {!busy && rungs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="label text-left">Rung</th>
                <th className="label text-left">Moves</th>
                <th className="label text-right">Cost</th>
                <th className="label text-right">GW xPts</th>
                <th className="label text-right">{weeks}-GW xPts</th>
                <th className="label text-right">vs bank</th>
                <th className="label text-right">P(beats bank)</th>
                <th className="label text-right">P(best)</th>
              </tr>
            </thead>
            <tbody>
              {rungs.map((r, i) => {
                const isCap = r.key === data?.cap_rung
                const beyond = capIndex >= 0 && i > capIndex
                const vsBank = (r.mean_pts !== null && r.mean_pts !== undefined
                  && bank?.mean_pts !== null && bank?.mean_pts !== undefined)
                  ? r.mean_pts - bank.mean_pts : null
                const label = rungLabel(r)
                const rowClass = [
                  'cursor-pointer border-t border-divider',
                  isCap ? 'bg-card' : '',
                  beyond ? 'text-text-muted' : 'text-text',
                ].join(' ')
                return (
                  <>
                    <tr
                      key={r.key}
                      data-cap={isCap ? 'true' : undefined}
                      title={beyond ? 'beyond your cap' : undefined}
                      className={rowClass}
                      onClick={() => setOpen(open === r.key ? null : r.key)}
                    >
                      <td className="py-1">
                        <span className="inline-flex items-center gap-1.5">
                          {label}
                          {r.key === data?.recommended && (
                            <Badge variant="info">recommended</Badge>
                          )}
                        </span>
                      </td>
                      {r.same_as
                        ? (
                          <td className="py-1 text-text-muted" colSpan={7}>
                            solver would not spend it — same as{' '}
                            {rungLabel(rungs.find((x) => x.key === r.same_as)!)
                              .toLowerCase()}
                          </td>
                          )
                        : (
                          <>
                            <td className="py-1">{movesText(r)}</td>
                            <td className="num py-1 text-right">
                              {r.cost > 0 ? `−${r.cost}` : '0'}
                            </td>
                            <td className="num py-1 text-right">{fmtNum(r.week_pts)}</td>
                            <td className="num py-1 text-right">{fmtNum(r.mean_pts)}</td>
                            <td className={`num py-1 text-right ${vsBank === null ? '' : TONE_CLASS[toneOf(vsBank)]}`}>
                              {vsBank === null || r.key === 'bank' ? '—'
                                : `${vsBank >= 0 ? '+' : '−'}${fmtNum(Math.abs(vsBank), 1)}`}
                            </td>
                            <td className="num py-1 text-right">{pct(r.p_beats_bank)}</td>
                            <td className="num py-1 text-right">{pct(r.p_best)}</td>
                          </>
                          )}
                    </tr>
                    {open === r.key && !r.same_as && (
                      <tr key={`${r.key}-open`} className="border-t border-divider">
                        <td colSpan={8}><Expanded rung={r} weeks={weeks} /></td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 4: Run the test and the type check**

Run: `cd frontend && npx vitest run src/hubs/this-week/LadderCard.test.tsx && npx tsc --noEmit`
Expected: all tests pass, `Errors 0`, tsc silent (except any `WhatIfRequest` literal errors, which Task 10 fixes). If the React key warning on the fragment fires, wrap the two rows in `<Fragment key={r.key}>` (import `Fragment` from `react`) instead of `<>`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hubs/this-week/LadderCard.tsx frontend/src/hubs/this-week/LadderCard.test.tsx
git commit -m "feat(v13): LadderCard — rungs, cap highlight, expand, rebuild, cap selects"
```

---

### Task 10: Placement, the moves-card cap line, `max_transfers` in the What-If panel

**Files:**
- Modify: `frontend/src/hubs/ThisWeek.tsx` (imports; state; the `MovesCard` block ~line 328-331)
- Modify: `frontend/src/hubs/this-week/MovesCard.tsx`, `MovesCard.test.tsx`
- Modify: `frontend/src/hubs/ThisWeek.test.tsx` (mocks)
- Modify: `frontend/src/hubs/planning/WhatIfTab.tsx`, `WhatIfTab.test.tsx`
- Modify: `frontend/src/hubs/planning/ConstraintsPanel.tsx`, `ConstraintsPanel.test.tsx`
- Modify: `frontend/src/hubs/planning/DraftsTab.tsx:226`, `DraftsTab.test.tsx:38,43`
- Modify: the `WhatIfRequest` literals: `frontend/src/hubs/Planning.tsx:37`, `Planning.test.tsx:43`, `responsive.test.tsx:111`, `planning/ChipsTab.tsx:141`, `planning/PlannerBoard.tsx:146`, `planning/PlannerBoard.test.tsx:176`, `planning/WhatIfTab.tsx:13`, `WhatIfTab.test.tsx:100,123`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/hubs/this-week/MovesCard.test.tsx` inside the `describe`:

```tsx
  it('prints the free-transfer and cap line above the moves when given one', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0}
                      capLine="1 free transfer · cap 2 hits" />)
    expect(screen.getByTestId('moves-cap-line'))
      .toHaveTextContent('1 free transfer · cap 2 hits')
  })

  it('prints no cap line without one', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.queryByTestId('moves-cap-line')).not.toBeInTheDocument()
    expect(screen.getByText(/bank the free transfer/i)).toBeInTheDocument()
  })
```

Append to `frontend/src/hubs/planning/ConstraintsPanel.test.tsx` inside its `describe` (read the file's existing `render` helper and `onChange` spy first and follow them):

```tsx
  it('offers a max-transfers cap that reads back as a number or null', async () => {
    const onChange = vi.fn()
    render(<ConstraintsPanel value={EMPTY} onChange={onChange} />)
    await userEvent.selectOptions(screen.getByLabelText('Max transfers'), '0')
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY, max_transfers: 0 })
    await userEvent.selectOptions(screen.getByLabelText('Max transfers'), '')
    expect(onChange).toHaveBeenLastCalledWith({ ...EMPTY, max_transfers: null })
  })
```

In `WhatIfTab.test.tsx`, add beside the two card mocks:

```tsx
vi.mock('../this-week/LadderCard', () => ({
  default: () => <p>ladder card</p>, capText: () => '',
}))
```

and one test:

```tsx
  it('mounts the transfer ladder above the sensitivity card', async () => {
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)
    const ladder = await screen.findByText('ladder card')
    const sensitivity = screen.getByText('sensitivity card')
    expect(ladder.compareDocumentPosition(sensitivity)
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
```

In `ThisWeek.test.tsx`, add beside the `useJobStream` mock:

```tsx
vi.mock('./this-week/LadderCard', () => ({
  default: ({ onLoaded }: { onLoaded?: (p: unknown) => void }) => {
    onLoaded?.({ gw: 5, gws: [5, 6, 7], free_transfers: 1,
                 cap: { max_hits: 2, max_transfers: null }, rungs: [{}] })
    return <p>ladder card</p>
  },
  capText: () => '1 free transfer · cap 2 hits',
}))
```

and one test inside `describe('This Week hub')`:

```tsx
  it('prints the cap line on the moves card once the ladder has loaded', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('moves-cap-line'))
      .toHaveTextContent('1 free transfer · cap 2 hits')
    expect(screen.getByText('ladder card')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npx vitest run src/hubs/this-week/MovesCard.test.tsx src/hubs/planning/ConstraintsPanel.test.tsx src/hubs/planning/WhatIfTab.test.tsx src/hubs/ThisWeek.test.tsx`
Expected: the new tests FAIL.

- [ ] **Step 3: `MovesCard`**

```tsx
export interface MovesCardProps {
  buys: Move[]
  sells: Move[]
  hits: number
  /** v13: "1 free transfer · cap 2 hits", from the ladder payload. */
  capLine?: string | null
}

export default function MovesCard({ buys, sells, hits, capLine }: MovesCardProps) {
```

and as the first child of `<Card title="Recommended moves">`:

```tsx
      {capLine && (
        <p className="mb-2 text-text-secondary" data-testid="moves-cap-line">
          {capLine}
        </p>
      )}
```

- [ ] **Step 4: `ThisWeek`**

Add the import `import LadderCard, { capText } from './this-week/LadderCard'` and `import type { LadderPayload } from '../types'` (extend the existing `import type {...} from '../types'`). Add state `const [capLine, setCapLine] = useState<string | null>(null)` beside `lens`, and a stable callback:

```tsx
  const onLadder = useCallback((p: LadderPayload) => {
    setCapLine(p.rungs.length > 0 ? capText(p) : null)
  }, [])
```

Replace the moves block:

```tsx
      <div className="mb-4">
        <MovesCard buys={advice.buys} sells={advice.sells} hits={advice.hits}
                   capLine={capLine} />
      </div>
      {/* v13: the ladder, directly under the moves it prices. */}
      <LadderCard onLoaded={onLadder} />
```

- [ ] **Step 5: `WhatIfTab`**

Add `import LadderCard from '../this-week/LadderCard'` and render `<LadderCard />` directly above `<SensitivityCard />`.

- [ ] **Step 6: `ConstraintsPanel` and every `WhatIfRequest` literal**

In `ConstraintsPanel.tsx`, change the grid to `sm:grid-cols-4` and add, after the Max hits `<div>`:

```tsx
        <div>
          <label className="flex flex-col gap-1">
            <span className="label">Max transfers</span>
            <select
              value={value.max_transfers ?? ''}
              onChange={(event) => onChange({
                ...value,
                max_transfers: event.target.value === '' ? null
                  : Number(event.target.value),
              })}
              className={FIELD}
            >
              <option value="">no cap</option>
              <option value={0}>bank</option>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <p className="mt-1 text-text-faint">
            Caps the moves in your version; the original solves under the
            caps the advice ran with.
          </p>
        </div>
```

Add `max_transfers: null,` after `max_hits: 0,` (or the literal's own `max_hits` value) in every `WhatIfRequest` object listed in this task's Files (nine files, twelve sites). In `PlannerBoard.tsx:146` add `max_transfers: null,` after the `max_hits:` line. In `DraftsTab.tsx` after the `max_hits` bit (line ~226):

```tsx
  if (c.max_transfers !== null && c.max_transfers !== undefined) {
    bits.push(c.max_transfers === 0 ? 'bank' : `up to ${c.max_transfers} transfers`)
  }
```

- [ ] **Step 7: Run the whole frontend suite and the type check**

Run: `cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -8`
Expected: tsc silent; every test passes; the summary shows `Errors 0` (an `Errors  N error` line is a failure to fix, not a pass).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx frontend/src/hubs/this-week/MovesCard.tsx frontend/src/hubs/this-week/MovesCard.test.tsx frontend/src/hubs/planning/WhatIfTab.tsx frontend/src/hubs/planning/WhatIfTab.test.tsx frontend/src/hubs/planning/ConstraintsPanel.tsx frontend/src/hubs/planning/ConstraintsPanel.test.tsx frontend/src/hubs/planning/DraftsTab.tsx frontend/src/hubs/planning/DraftsTab.test.tsx frontend/src/hubs/Planning.tsx frontend/src/hubs/Planning.test.tsx frontend/src/hubs/responsive.test.tsx frontend/src/hubs/planning/ChipsTab.tsx frontend/src/hubs/planning/PlannerBoard.tsx frontend/src/hubs/planning/PlannerBoard.test.tsx
git commit -m "feat(v13): ladder on This Week and What-If, the cap line on the moves card, max transfers in the constraints panel"
```

---

### Task 11: Full verification and the pre-registered replay command

**Files:** none edited by the implementer. The replay is the orchestrator's to run (CONVENTIONS §7).

- [ ] **Step 1: The whole suite**

```bash
.venv/bin/pytest tests -q -p no:cacheprovider 2>&1 | tail -3
.venv/bin/pytest tests/test_v*_degradation.py -q 2>&1 | tail -1
cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6 && cd ..
```

Expected: Python all green (4044 + the new tests); rails green; frontend green with `Errors 0`.

- [ ] **Step 2: The pins, stated**

```bash
.venv/bin/python - <<'EOF'
import dataclasses
from gaffer.config import Config
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
print("Config", len(dataclasses.fields(Config)), "routes",
      len(create_app().openapi()["paths"]), "kinds", len(JOB_KINDS))
EOF
```

Expected: `Config 57 routes 48 kinds 12`.

- [ ] **Step 3: The security ritual (orchestrator, after the merge)**

```bash
git show main:config.toml >/dev/null 2>&1 && echo "RITUAL FAIL" || echo "ritual clean"
git log -S e87e739977a1e6dfbdc60aa13b2e2d57 --all --oneline | wc -l   # must be 0
```

- [ ] **Step 4: The pre-registered measurement (orchestrator, §6 of the spec) — documented here, not run by an implementer**

Both arms byte-identical in `config.toml` except `[optimizer] max_hits`: the branch arm at `max_hits = 2` (the shipped default), the control at `max_hits = 15`. Three seed bases, the 2025-26 season, `scripts/replay_pair.sh v13-caps` in the shape v12 used. The write-up records mean ± spread of season points and of hits taken, and names the `data/core_insights/` state (present/absent, seasons, collection date). Informational only: the result does not move the default.

---

## Self-review

**Spec coverage.** §2.1 config → Task 1. §2.2 MILP → Task 2. §2.3 advise/state/What-If/drafts/Settings/CLI → Tasks 3, 4, 5. §3.1 ladder → Task 6. §3.2 advise call + routes → Tasks 7, 8. §4.1–4.3 card, placement, controls, types → Tasks 8 (types), 9, 10. §5 tests: rail (Tasks 1, 2, 3, 5, 6, 8), `test_ladder.py` (6), `test_web_ladder.py` (8), What-If baseline (4), advise (3, 7), docs (1), frontend (9, 10); the spec's `SettingsTab.test.tsx` row is covered by the Python settings panel test in Task 5 instead — the tab renders whatever rows are served and needs no code. §6 → Task 11. §7 file list matches the map above plus `drafts.py`, `ThisWeek.test.tsx` and the literal sites the code required.

**Placeholders.** None: every step carries its code or its exact command.

**Type consistency.** `caps_from_state(state) -> (max_hits, max_transfers)` (Task 3) is what Tasks 4 and 6 call. `_cap` lives in `advise.py`; `_caps_line` in `cli.py`; `NO_CAP` in `config.py`, mirrored as `NO_CAP` in `LadderCard.tsx`. `build_ladder(gw, *, n_draws, seed)`, `load_ladder`, `ladder_path`, `save_ladder`, `score_plan(gw_plans, draws, hit_cost, n_draws)`, `p_best`, `vs_below(below, rung, *, prev_mean, mean, hit_cost, meta, ep_by)` are named identically in Task 6's module and tests and Task 8's router. `LadderWeek.xi/bench/captain/vice` are `PlayerRef`s in the schema (Task 8), in the module's `_week` (Task 6) and in the card (Task 9). `LadderCardProps.onLoaded` (Task 9) is what `ThisWeek` passes (Task 10). Route pin 48 in Tasks 8 and 11; config pin 57 in Tasks 1 and 11.
