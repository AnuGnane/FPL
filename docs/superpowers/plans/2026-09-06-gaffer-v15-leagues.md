# gaffer v15 — leagues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The League hub shows every private league the entry is in, one focus league drives the solver, and a manual stance (auto / chase / defend / neutral) overrides the computed tilt at full cap.

**Architecture:** A pure `apply_stance` in `league_mode.py` and one added call in `advise.py`; `[league] focus` and `[league] stance` in the settings overlay, resolved by the config loader into `Config.league_id` and a new `Config.stance`; a new `GET /api/league/leagues` overview plus a `league_id` parameter on the existing race, rivals, sim and what-if routes; a new Leagues tab in the React hub with a `?league=` URL param, a stance control and a This Week caption.

**Tech Stack:** Python 3.12, dataclasses, pydantic v2, FastAPI, pandas; React 18 + TypeScript, Tailwind v4, Radix Tabs, vitest, json-schema-to-typescript.

**Spec:** `docs/superpowers/specs/2026-09-06-gaffer-v15-leagues-design.md`. Read it once before Task 1.

---

## Standing rules (every task)

- Branch `v15-leagues` off `main`. Never commit on main.
- Python: `.venv/bin/pytest -q` must end with `N passed` and nothing failing, `N > 4110`. Run the touched test files after every step; run the whole suite before the final task.
- Frontend: `cd frontend && npx tsc --noEmit && npx vitest run`. A vitest summary line reading `Errors N error` is a FAILURE even when every test passed. Now 866 passed, 1 skipped; only the count may rise.
- Pins: JOB_KINDS stays 12. Config fields move 57 → 58 and routes 48 → 49, both edited by the orchestrator only (Tasks 2 and 4 say where).
- Protected files (no diff without the orchestrator): `src/gaffer/advise.py` (Task 7 is the orchestrator's), `set_pieces.py`, `optimize/**`, `web/jobs.py`, `web/routers/whatif.py`, `tests/test_advise.py`, `test_odds.py`, `test_web_jobs.py`, pre-existing `tests/test_v*_degradation.py`, `scripts/s2_replay.py`.
- Git: stage explicit paths only; never `git add -A`; never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `.superpowers/`, `config.toml`, `config.local.toml`, `src/gaffer/web/static/`.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Mx6ovTnhpZzdEJpKkmSRke
  ```
- SECURITY: `config.toml` holds an API key. Never open it, never print it, never copy anything from it. Tests write their own `config.toml` under `tmp_path`.
- Ledger rules (`frontend/src/kit/tokens.test.ts`): no `rounded-full`, no `shadow-`, no `gradient`, no raw hex, no `font-mono` outside JobLog/PlannerBoard, no `<Badge`, no `num`/`sage`/`rust`/`info`/`card` token names. Use the kit: `TABLE_CLASS`, `THEAD_CLASS`, `thClass`, `tdClass`, `TR_CLASS`, `TR_SELECTED_CLASS`, `Chip`, `Segmented`, `Callout`, `Button`, `EmptyState`, `PageHeader`, `Loading`, `toast`, `errorText`.
- Regenerating types after a `schemas.py` change (Tasks 3, 4, 5, 6):
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
  " && npx vitest run src/types.generated.test.ts && cd ..
  .venv/bin/pytest -q tests/test_v12_w5_gen_types.py
  ```
  Commit `frontend/src/schemas.json` and `frontend/src/types.generated.ts` with the schema change. `npx tsc --noEmit` may fail between a schema task and the frontend task that consumes it (a required field on a literal); the task that owns the consumer fixes it and says so.

## Rulings (decisions the spec left to the plan)

- **R1 Paging.** `_standings` pages until the user's row is present, capped at 4 pages (200 rows), and does NOT fetch "one more page" as the spec's §5.3 said: the race fetches one history per standings row, so an extra page is fifty more FPL calls for a table the page already shows.
- **R2 Manual stance is visible at once.** `race()` for the focus league applies `apply_stance` to the solve state's λ, so flipping the stance shows on the League page and the overview before the next advise run. The solver itself changes only when advise runs.
- **R3 A focus that is not private is lenient.** `race`/`rivals`/`sim` with no `league_id` serve whatever `cfg.league_id` is, as today, naming it from the entry's classic list when present and "League {id}" otherwise. Only an explicit `league_id` that is not one of the private leagues is refused.
- **R4 The non-focus Strategy uses the histories the race already fetched.** No second history fetch and no cache file: the trajectory rows become the `history` frame.
- **R5 Focus league bound.** The int row needs a numeric `hi` (the range check does `<= hi`); it is 99,999,999.
- **R6 File layout.** New Python tests are new files (`tests/test_league_stance.py`, `tests/test_v15_config.py`, `tests/test_v15_settings.py`, `tests/test_web_league_overview.py`); existing `tests/test_web_league.py` and `tests/test_web_league_sim.py` gain tests and a richer `FakeClient`.

## File map

| File | Change |
|---|---|
| `src/gaffer/league_mode.py` | `Strategy.source`, `STANCES`, `apply_stance` |
| `src/gaffer/config.py` | `stance` field; `[league] focus` resolved into `league_id`; `_check_stance` |
| `src/gaffer/web/settings_keys.py` | `choices` on `SettingKey`; `choice` kind; two rows; docstring |
| `src/gaffer/web/routers/settings.py` | `choice` branch in `_checked`; `choices` on rows |
| `src/gaffer/web/schemas.py` | `SettingRow.kind/choices`; `PrivateLeagueRow`, `PublicLeagueRow`, `LeaguesOverview`; `LeagueRace.league_name/focus/stance_source`; `LeagueWhatIfRequest.league_id` |
| `src/gaffer/web/routers/league.py` | overview route + cache; `_standings` paging; `_league`; `league_id` on race/rivals/rival; non-focus Strategy; manual stance on focus |
| `src/gaffer/league_sim.py` | `build_inputs(..., league_id=None)`; message |
| `src/gaffer/web/routers/league_sim.py` | `_cache_key`/`_run`/`sim`/`whatif` take a league |
| `src/gaffer/cli.py` | one message |
| `src/gaffer/advise.py` | one call (orchestrator) |
| `frontend/src/hubs/model/SettingsTab.tsx` | `choice` → `Segmented` |
| `frontend/src/hubs/league/LeaguesTab.tsx` (new) | the overview table, stance control, public table |
| `frontend/src/hubs/League.tsx` | tabs, `?league=`, overview, writes, header, note |
| `frontend/src/hubs/league/RivalDetail.tsx`, `WhatIfSim.tsx` | carry the league |
| `frontend/src/hubs/ThisWeek.tsx` | caption + manual chip |
| `frontend/src/types.ts` | `Strategy.source?` |

---

### Task 0: Branch

- [ ] **Step 1**

```bash
git checkout main && git pull --ff-only && git checkout -b v15-leagues
```

---

### Task 1: `apply_stance` in league_mode

**Files:**
- Modify: `src/gaffer/league_mode.py` (the `Strategy` dataclass ~line 135, imports at top)
- Test: `tests/test_league_stance.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""v15 §3.2 — the manual stance override, at full tilt."""

from pathlib import Path

import pytest

from gaffer.league_mode import (STANCES, LeagueParams, Strategy,
                                apply_stance)


def _computed() -> Strategy:
    return Strategy(lam=0.31, gap=12, weeks_left=30, stance="chase",
                    rival_name="Ten Hag Hive", z=1.1, sigma_m=14.0,
                    cover_weights={7: 0.6})


def test_the_four_stances_are_named():
    assert STANCES == ("auto", "chase", "defend", "neutral")


def test_auto_returns_the_computed_strategy_untouched():
    s = apply_stance(_computed(), "auto", LeagueParams(lambda_cap=0.5))
    assert (s.lam, s.stance, s.source) == (0.31, "chase", "auto")


def test_chase_pins_lambda_to_plus_cap():
    s = apply_stance(_computed(), "chase", LeagueParams(lambda_cap=0.5))
    assert (s.lam, s.stance, s.source) == (0.5, "chase", "manual")


def test_defend_pins_lambda_to_minus_cap():
    s = apply_stance(_computed(), "defend", LeagueParams(lambda_cap=0.5))
    assert (s.lam, s.stance, s.source) == (-0.5, "defend", "manual")


def test_neutral_is_exactly_zero():
    s = apply_stance(_computed(), "neutral", LeagueParams(lambda_cap=0.5))
    assert s.lam == 0.0 and s.stance == "neutral" and s.source == "manual"


def test_the_cap_is_the_configured_one():
    s = apply_stance(_computed(), "chase", LeagueParams(lambda_cap=0.2))
    assert s.lam == 0.2


def test_no_params_means_the_pinned_cap():
    from gaffer.league_mode import LAMBDA_CAP

    assert apply_stance(_computed(), "defend").lam == -LAMBDA_CAP


def test_manual_keeps_the_computed_gap_rival_and_cover():
    s = apply_stance(_computed(), "defend", LeagueParams(lambda_cap=0.5))
    assert s.gap == 12 and s.weeks_left == 30
    assert s.rival_name == "Ten Hag Hive"
    assert s.z == 1.1 and s.sigma_m == 14.0
    assert s.cover_weights == {7: 0.6}


def test_the_input_is_not_mutated():
    before = _computed()
    apply_stance(before, "neutral")
    assert before.lam == 0.31 and before.stance == "chase"


def test_an_unknown_stance_is_refused_by_name():
    with pytest.raises(ValueError, match="stance"):
        apply_stance(_computed(), "attack")


def test_source_defaults_to_auto_on_a_bare_strategy():
    assert Strategy(0.0, 0, 1, "neutral", "the field").source == "auto"


def test_advise_applies_the_stance_after_computing_it():
    """The one protected-file change of the cycle, pinned by text: the call
    sits after ``compute_strategy`` in the league block."""
    text = Path("src/gaffer/advise.py").read_text()
    assert "apply_stance(" in text
    assert text.index("compute_strategy(") < text.index("apply_stance(")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_league_stance.py`
Expected: ImportError on `STANCES`/`apply_stance`.

- [ ] **Step 3: Implement**

In `src/gaffer/league_mode.py`, extend the dataclasses import to include `replace` (it already imports `dataclass` and `field`). Add `source` to `Strategy`:

```python
@dataclass
class Strategy:
    lam: float
    gap: int
    weeks_left: int
    stance: str          # "chase" | "defend" | "neutral"
    rival_name: str
    # --- v4d, appended last and defaulted so positional callers still work --
    z: float = 0.0
    sigma_m: float = SIGMA_FALLBACK
    cover_weights: dict = field(default_factory=dict)
    # --- v15 §3.2. "auto" when the dial set lam, "manual" when the user's
    # stance did. Appended and defaulted for the same reason as the v4d
    # fields; asdict() in advise.py carries it into the advice payload.
    source: str = "auto"
```

Directly after `_sign`, add:

```python
STANCES = ("auto", "chase", "defend", "neutral")
"""The ``[league] stance`` values (v15 §3.2). ``auto`` is the dial."""


def apply_stance(strategy: Strategy, stance: str,
                 params: LeagueParams | None = None) -> Strategy:
    """The manual override, at full tilt (v15 §3.2).

    ``auto`` returns the computed strategy with ``source="auto"``. ``chase``
    and ``defend`` pin ``lam`` to plus and minus the cap — the sign convention
    :func:`compute_strategy` already uses — and ``neutral`` pins it to exactly
    0.0, which is the points-max path. The gap, the rival, ``z``, ``sigma_m``
    and the cover weights are kept as computed so the reports still say where
    the user stands; only the tilt is overridden. Never mutates its input.
    """
    if stance not in STANCES:
        raise ValueError(
            f"stance must be one of {', '.join(STANCES)}, got {stance!r}")
    if stance == "auto":
        return replace(strategy, source="auto")
    cap = (params or LeagueParams()).lambda_cap
    lam = {"chase": cap, "defend": -cap, "neutral": 0.0}[stance]
    return replace(strategy, lam=lam, stance=stance, source="manual")
```

The last test (`test_advise_applies_the_stance_after_computing_it`) stays red until Task 7. Mark it `@pytest.mark.xfail(strict=True, reason="Task 7 wires advise.py")` for now; Task 7 removes the marker.

- [ ] **Step 4: Run**

Run: `.venv/bin/pytest -q tests/test_league_stance.py tests/test_league_mode.py`
Expected: all pass, one xfail.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/league_mode.py tests/test_league_stance.py
git commit -m "feat(v15): apply_stance — the manual league stance at full tilt; Strategy.source"
```

---

### Task 2: Config — `stance` and `[league] focus`

**Files:**
- Modify: `src/gaffer/config.py` (dataclass ~line 130 after `rival_drift`; loader ~lines 368 and 393-406; `_check_caps` ~line 325)
- Test: `tests/test_v15_config.py` (new)
- Orchestrator only: `tests/test_v13_degradation.py:20-27`

- [ ] **Step 1: Write the failing tests**

```python
"""v15 §3.1 / §4.1 — the focus league and the stance, in config."""

import dataclasses

import pytest

from gaffer.config import LOCAL_OVERLAY, Config, load_config
from gaffer.errors import GafferError

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


def _load(tmp_path, monkeypatch, base: str = BASE, local: str | None = None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(base)
    if local is not None:
        (tmp_path / LOCAL_OVERLAY).write_text(local)
    return load_config()


def test_stance_is_a_config_field_defaulting_to_auto():
    assert "stance" in {f.name for f in dataclasses.fields(Config)}
    assert Config(entry_id=1, league_id=5).stance == "auto"


def test_no_focus_means_fpl_league_id(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch)
    assert cfg.league_id == 5 and cfg.stance == "auto"


def test_a_focus_in_the_overlay_is_the_effective_league_id(tmp_path,
                                                            monkeypatch):
    cfg = _load(tmp_path, monkeypatch, local="[league]\nfocus = 77\n")
    assert cfg.league_id == 77


def test_a_zero_focus_falls_back_to_fpl_league_id(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, local="[league]\nfocus = 0\n")
    assert cfg.league_id == 5


def test_a_focus_in_config_toml_itself_is_honoured(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, base=BASE + "[league]\nfocus = 9\n")
    assert cfg.league_id == 9


def test_stance_is_read_from_the_league_table(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, local='[league]\nstance = "defend"\n')
    assert cfg.stance == "defend"


def test_a_bad_stance_fails_load_by_name(tmp_path, monkeypatch):
    with pytest.raises(GafferError, match="stance"):
        _load(tmp_path, monkeypatch, local='[league]\nstance = "attack"\n')


def test_the_other_league_knobs_still_load_beside_them(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch,
                local='[league]\nfocus = 77\nstance = "chase"\nlambda_cap = 0.3\n')
    assert (cfg.league_id, cfg.stance, cfg.lambda_cap) == (77, "chase", 0.3)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_v15_config.py`
Expected: failures on `stance` and on `league_id == 77`.

- [ ] **Step 3: Implement**

In the `Config` dataclass, directly after `rival_drift: float = 0.5`:

```python
    # --- v15 leagues (specs/2026-09-06-gaffer-v15-leagues-design.md) ------
    # The manual stance: "auto" is the dial, the other three pin λ at the
    # cap (chase +, defend -) or at exactly 0.0 (neutral). Read from [league]
    # stance, which the League page writes through the settings overlay. The
    # focus league itself is not a new field: [league] focus, when set, is
    # resolved by load_config into league_id, so every reader of league_id
    # sees the focus without knowing the word.
    stance: str = "auto"
```

In `load_config`, change the `league_id=` line of the `Config(...)` call and add `stance=` beside the other `[league]` reads:

```python
        entry_id=raw["fpl"]["entry_id"],
        # v15 §3.1: the overlay's [league] focus wins over fpl.league_id when
        # it is set and non-zero. fpl.league_id itself is never rewritten.
        league_id=int(league.get("focus") or 0) or raw["fpl"]["league_id"],
```

```python
        rival_drift=float(league.get("rival_drift", 0.5)),
        stance=str(league.get("stance", "auto")),
```

Add a checker beside `_check_caps` (defined ~line 324) and call it on the line after the existing `_check_caps(cfg)` call in `load_config` (~line 428, the only call):

```python
def _check_stance(cfg: "Config") -> None:
    """v15 §3.2: the stance is one of four words, refused by name."""
    from gaffer.league_mode import STANCES

    if cfg.stance not in STANCES:
        raise GafferError(
            f"[league] stance = {cfg.stance!r} — must be one of "
            f"{', '.join(STANCES)}")
```

- [ ] **Step 4: Run**

Run: `.venv/bin/pytest -q tests/test_v15_config.py tests/test_config.py tests/test_v12_w5_config_overlay.py tests/test_v13_degradation.py`
Expected: all new tests pass; `test_the_config_gained_exactly_two_fields` in `test_v13_degradation.py` FAILS on `57` — that is expected and is the orchestrator's edit in Step 6. Everything else passes.

- [ ] **Step 5: Commit (implementer)**

```bash
git add src/gaffer/config.py tests/test_v15_config.py
git commit -m "feat(v15): Config.stance; [league] focus resolves into league_id"
```

- [ ] **Step 6: Pin (ORCHESTRATOR ONLY)**

In `tests/test_v13_degradation.py`, `test_the_config_gained_exactly_two_fields`: append to the docstring `58 after v15 (specs/2026-09-06-gaffer-v15-leagues-design.md §4.1): the one new name is stance; the focus league reuses league_id.`; change `== 57` to `== 58`; add `assert "stance" in names`. Commit:

```bash
git add tests/test_v13_degradation.py
git commit -m "test(v15): Config field pin 57 -> 58, the one name is stance"
```

---

### Task 3: Settings — the `choice` kind and the two rows

**Files:**
- Modify: `src/gaffer/web/settings_keys.py` (module docstring lines 1-10, `SettingKey` ~46-69, `WHITELIST` ~72-128)
- Modify: `src/gaffer/web/routers/settings.py` (`_checked` ~145-198, `_panel` rows ~118-124, module docstring line 1)
- Modify: `src/gaffer/web/schemas.py` (`SettingRow` ~2172)
- Regenerate: `frontend/src/schemas.json`, `frontend/src/types.generated.ts`
- Test: `tests/test_v15_settings.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""v15 §4.2 — the focus league and the stance rows, and the choice kind."""

import tomllib

import pytest
from fastapi.testclient import TestClient

from gaffer.config import LOCAL_OVERLAY, serving_config
from gaffer.web.app import create_app
from gaffer.web.settings_keys import BY_FIELD, WHITELIST

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(BASE)
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


def _row(client, key):
    return next(r for r in client.get("/api/settings").json()["rows"]
                if r["key"] == key)


def _overlay(tmp_path):
    path = tmp_path / LOCAL_OVERLAY
    return tomllib.loads(path.read_text()) if path.exists() else {}


def test_the_focus_row_reads_the_effective_league_id(client):
    row = _row(client, "league_id")
    assert row["label"] == "Focus league"
    assert row["kind"] == "int" and row["value"] == 5
    assert row["section"] == "league" and row["source"] == "base"


def test_the_stance_row_is_a_choice_with_four_options(client):
    row = _row(client, "stance")
    assert row["kind"] == "choice"
    assert row["choices"] == ["auto", "chase", "defend", "neutral"]
    assert row["value"] == "auto" and row["source"] == "default"


def test_every_other_row_has_no_choices(client):
    for row in client.get("/api/settings").json()["rows"]:
        if row["kind"] != "choice":
            assert row["choices"] == []


def test_a_focus_write_lands_in_league_focus_and_not_in_config_toml(
        client, tmp_path):
    body = client.post("/api/settings",
                       json={"key": "league_id", "value": 77}).json()
    assert _overlay(tmp_path) == {"league": {"focus": 77}}
    assert "focus" not in (tmp_path / "config.toml").read_text()
    row = next(r for r in body["rows"] if r["key"] == "league_id")
    assert row["value"] == 77 and row["source"] == "local"


def test_resetting_the_focus_falls_back_to_fpl_league_id(client, tmp_path):
    client.post("/api/settings", json={"key": "league_id", "value": 77})
    body = client.post("/api/settings",
                       json={"key": "league_id", "value": None}).json()
    assert _overlay(tmp_path) == {}
    row = next(r for r in body["rows"] if r["key"] == "league_id")
    assert row["value"] == 5 and row["source"] == "base"


def test_a_stance_write_is_the_word_itself(client, tmp_path):
    body = client.post("/api/settings",
                       json={"key": "stance", "value": "defend"}).json()
    assert _overlay(tmp_path) == {"league": {"stance": "defend"}}
    row = next(r for r in body["rows"] if r["key"] == "stance")
    assert row["value"] == "defend" and row["source"] == "local"


@pytest.mark.parametrize("value", ["attack", "", 7, True])
def test_a_stance_outside_the_four_is_refused_and_writes_nothing(
        client, tmp_path, value):
    resp = client.post("/api/settings", json={"key": "stance", "value": value})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "wrong_type"
    assert "one of" in resp.json()["detail"]["error"]
    assert _overlay(tmp_path) == {}


def test_a_focus_below_one_is_refused(client, tmp_path):
    resp = client.post("/api/settings", json={"key": "league_id", "value": 0})
    assert resp.status_code == 422
    assert _overlay(tmp_path) == {}


def test_the_whitelist_declares_the_two_rows_in_the_league_table():
    assert BY_FIELD["league_id"].section == "league"
    assert BY_FIELD["league_id"].toml_key == "focus"
    assert BY_FIELD["stance"].toml_key == "stance"
    assert BY_FIELD["stance"].choices == ("auto", "chase", "defend", "neutral")
    assert all(e.choices == () for e in WHITELIST if e.kind != "choice")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_v15_settings.py`
Expected: KeyError on `league_id` / `stance` rows.

- [ ] **Step 3: Implement the whitelist**

In `src/gaffer/web/settings_keys.py`:

1. Module docstring: find the sentence that names the entry and league ids as untouchable and reword it to: `The fpl table — entry_id, league_id — stays untouchable; v15's [league] focus is an overlay override of which league is the focus, read back as the effective Config.league_id.`
2. `SettingKey.kind` docstring: ``` ``int`` | ``float`` | ``bool`` | ``floats3`` | ``pool`` | ``choice``. ```
3. Add after `reader: str = ""` and its docstring:

```python
    choices: tuple[str, ...] = ()
    """For ``kind == "choice"``: the exact strings the value may be. Empty
    for every other kind."""
```

4. Append two rows to `WHITELIST`, after `max_transfers`:

```python
    # v15 §4.2 (specs/2026-09-06-gaffer-v15-leagues-design.md). The focus
    # league. Written as [league] focus, read back as the *effective*
    # Config.league_id, which the loader resolves from the overlay over
    # fpl.league_id — so `field` is league_id and `toml_key` is focus, and
    # fpl.* itself is never written. The League page's "make focus" writes
    # this row; hi is a numeric bound because the range check needs one.
    SettingKey("league_id", "league", "focus", "Focus league",
               "int", 1, 99_999_999,
               "The private league that sets the plan. Pick it on the League "
               "page; reset to fall back to fpl.league_id."),
    SettingKey("stance", "league", "stance", "Stance",
               "choice", None, None,
               "Auto lets the standings set the tilt. Chase and defend force "
               "it at the λ tilt cap; neutral is plain points-max.",
               choices=("auto", "chase", "defend", "neutral")),
```

- [ ] **Step 4: Implement the router and schema**

`src/gaffer/web/routers/settings.py`, in `_checked`, insert before the final `else:  # pragma: no cover` branch:

```python
    elif kind == "choice":
        if not isinstance(value, str) or value not in entry.choices:
            raise _fail("wrong_type",
                        f"{entry.label} is one of {', '.join(entry.choices)}")
        return value
```

In `_panel`, the `SettingRow(...)` call gains `choices=list(entry.choices),`. Update the module docstring's first line from "the eleven settings" to "the thirteen settings".

`src/gaffer/web/schemas.py`, `SettingRow`:

```python
    kind: Literal["int", "float", "bool", "floats3", "pool", "choice"]
```
and after `hi`:
```python
    choices: list[str] = Field(default_factory=list)
    """For ``kind == "choice"`` the allowed strings, in display order (v15
    §4.2). Empty for every other kind."""
```

- [ ] **Step 5: Regenerate types** (standing-rules block). Then `cd frontend && npx tsc --noEmit`: expect errors on `SettingRow` literals in `frontend/src/hubs/model/SettingsTab.test.tsx` and possibly `hubs/w5.coldclone.test.tsx` lacking `choices`. Add `choices: []` to each such literal in those test files now (they are test data, not the component).

- [ ] **Step 6: Run**

Run: `.venv/bin/pytest -q tests/test_v15_settings.py tests/test_v12_w5_settings.py tests/test_v12_w5_gen_types.py && cd frontend && npx tsc --noEmit && npx vitest run src/types.generated.test.ts src/hubs/model && cd ..`
Expected: all pass. If `test_v12_w5_settings.py` pins a row count or the docstring wording, update that assertion with a one-line comment naming v15.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/settings_keys.py src/gaffer/web/routers/settings.py src/gaffer/web/schemas.py frontend/src/schemas.json frontend/src/types.generated.ts frontend/src/hubs/model/SettingsTab.test.tsx frontend/src/hubs/w5.coldclone.test.tsx tests/test_v15_settings.py tests/test_v12_w5_settings.py
git commit -m "feat(v15): settings rows for the focus league and the stance; the choice kind"
```
(Only stage the test files you actually changed.)

---

### Task 4: `GET /api/league/leagues` — the overview

**Files:**
- Modify: `src/gaffer/web/schemas.py` (after `LeagueRace`)
- Modify: `src/gaffer/web/routers/league.py`
- Regenerate types
- Test: `tests/test_web_league_overview.py` (new)
- Orchestrator only: `tests/test_v11_degradation.py:362-378`

- [ ] **Step 1: Write the failing tests**

```python
"""v15 §5.1 — every league the entry is in, private and public."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.config import LOCAL_OVERLAY, serving_config
from gaffer.web.app import create_app
from gaffer.web.routers import league as mod

ME = 1


def _league(id_, name, type_, rank_count, rank, last_rank):
    return {"id": id_, "name": name, "league_type": type_,
            "rank_count": rank_count, "entry_rank": rank,
            "entry_last_rank": last_rank, "scoring": "c"}


ENTRY = {
    "summary_overall_points": 300, "current_event": 5,
    "leagues": {"classic": [
        _league(314, "Overall", "s", 10_409_391, 430_473, 2_562_053),
        _league(261, "England", "s", 2_923_703, 128_302, 762_621),
        _league(5, "Focus FC League", "x", 3, 1, 2),
        _league(9, "NLT", "x", 60, 55, 58),
        _league(99, "Next Season", "x", None, 3, 0),
        _league(77, "Duo", "x", 1, 1, 1),
    ], "h2h": []},
}

# League 5: I lead on 300 over 290. League 9: sixty entries, I am 55th and
# NOT on page 1, so my total comes from the entry payload. League 77: only me.
STANDINGS = {
    5: {"standings": {"has_next": False, "results": [
        {"entry": ME, "entry_name": "Mine", "player_name": "Me", "rank": 1,
         "last_rank": 2, "total": 300, "event_total": 60},
        {"entry": 2, "entry_name": "Second", "player_name": "S", "rank": 2,
         "last_rank": 1, "total": 290, "event_total": 50},
        {"entry": 3, "entry_name": "Third", "player_name": "T", "rank": 3,
         "last_rank": 3, "total": 100, "event_total": 10}]}},
    9: {"standings": {"has_next": True, "results": [
        {"entry": 20, "entry_name": "Leader", "player_name": "L", "rank": 1,
         "last_rank": 1, "total": 412, "event_total": 70}]}},
    77: {"standings": {"has_next": False, "results": [
        {"entry": ME, "entry_name": "Mine", "player_name": "Me", "rank": 1,
         "last_rank": 1, "total": 300, "event_total": 60}]}},
}


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_entry(self, entry_id):
        self.calls.append(("entry", entry_id))
        return ENTRY

    def get_league_standings(self, league_id, page=1):
        self.calls.append(("standings", league_id, page))
        return STANDINGS[league_id]


def _artifacts(tmp_path, league_id=5, lam=0.4):
    (tmp_path / "config.toml").write_text(
        f"[fpl]\nentry_id = {ME}\nleague_id = {league_id}\n")
    players = pd.DataFrame([{"code": 100, "element": 7, "name": "Salah",
                             "position": "MID", "team_id": 1,
                             "team_code": 300, "now_cost": 130}])
    save_solve_state(SolveState(
        gw=6, gws=[6], deadline="2026-09-19T17:30:00Z",
        generated_at="2026-09-18T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=lam, league_eo={},
        avail_by_gw={6: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool_rows(
            pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                           "cost": 130, "sell": 128}]),
            players, [100], {(100, 6): 6.4}, [6])))


@pytest.fixture()
def fake():
    return FakeClient()


@pytest.fixture()
def client(tmp_path, monkeypatch, fake):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    monkeypatch.setattr(mod, "fpl_client", lambda: fake)
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


def test_private_and_public_are_split_by_the_league_type_flag(client):
    body = client.get("/api/league/leagues").json()
    assert [r["name"] for r in body["public"]] == ["Overall", "England"]
    assert {r["name"] for r in body["private"]} == {
        "Focus FC League", "NLT", "Next Season", "Duo"}
    assert body["gw"] == 5


def test_private_rows_are_ordered_by_rank_then_size(client):
    body = client.get("/api/league/leagues").json()
    assert [r["name"] for r in body["private"]] == [
        "Focus FC League", "Duo", "Next Season", "NLT"]


def test_the_focus_row_is_marked_and_named(client):
    body = client.get("/api/league/leagues").json()
    assert body["focus_league_id"] == 5
    assert body["focus_name"] == "Focus FC League"
    assert body["focus_warning"] is None
    focus = [r for r in body["private"] if r["is_focus"]]
    assert [r["league_id"] for r in focus] == [5]


def test_a_leader_is_ahead_of_second_and_would_defend(client):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 5)
    assert (row["rank"], row["last_rank"], row["entries"]) == (1, 2, 3)
    assert row["started"] is True
    assert (row["gap"], row["gap_kind"], row["would"]) == (10, "ahead", "defend")


def test_off_page_one_the_gap_uses_the_entry_payloads_total(client):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 9)
    assert (row["gap"], row["gap_kind"], row["would"]) == (112, "behind", "chase")


def test_a_league_of_one_has_no_gap(client):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 77)
    assert row["started"] and row["gap"] is None and row["would"] is None


def test_a_league_not_started_has_no_gap_and_says_so(client, fake):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 99)
    assert row["started"] is False
    assert row["entries"] is None and row["gap"] is None
    assert ("standings", 99, 1) not in fake.calls


def test_public_rows_carry_rank_last_rank_and_size_only(client):
    row = client.get("/api/league/leagues").json()["public"][0]
    assert row == {"league_id": 314, "name": "Overall", "rank": 430_473,
                   "last_rank": 2_562_053, "entries": 10_409_391}


def test_the_stance_and_the_focus_tilt_come_from_config_and_solve_state(
        client):
    body = client.get("/api/league/leagues").json()
    assert body["stance"] == "auto"
    assert body["focus_stance"] == "chase" and body["focus_lam"] == 0.4


def test_a_manual_stance_shows_at_the_cap_before_any_advise(
        client, tmp_path):
    (tmp_path / LOCAL_OVERLAY).write_text('[league]\nstance = "defend"\n')
    serving_config.cache_clear()
    body = client.get("/api/league/leagues").json()
    assert body["stance"] == "defend"
    assert body["focus_stance"] == "defend" and body["focus_lam"] == -0.5


def test_a_focus_that_is_not_private_is_a_warning_not_a_refusal(
        tmp_path, monkeypatch, fake):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path, league_id=42)
    monkeypatch.setattr(mod, "fpl_client", lambda: fake)
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/league/leagues").json()
    assert body["focus_name"] is None
    assert "42" in body["focus_warning"]
    assert not any(r["is_focus"] for r in body["private"])


def test_no_league_id_at_all_still_lists_the_leagues(tmp_path, monkeypatch,
                                                    fake):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path, league_id=0)
    monkeypatch.setattr(mod, "fpl_client", lambda: fake)
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    resp = TestClient(create_app()).get("/api/league/leagues")
    assert resp.status_code == 200
    assert resp.json()["focus_warning"] is not None
    assert len(resp.json()["private"]) == 4


def test_the_rows_are_cached_for_five_minutes_per_entry(client, fake):
    client.get("/api/league/leagues")
    first = len(fake.calls)
    assert first == 3                # the entry, then leagues 5 and 9; 77 is
                                     # a league of one and 99 has not started
    client.get("/api/league/leagues")
    assert len(fake.calls) == first
    mod._OVERVIEW.clear()
    client.get("/api/league/leagues")
    assert len(fake.calls) == 2 * first


def test_the_cache_does_not_hold_the_focus_or_the_stance(client, tmp_path):
    client.get("/api/league/leagues")
    (tmp_path / LOCAL_OVERLAY).write_text('[league]\nfocus = 9\n')
    serving_config.cache_clear()
    body = client.get("/api/league/leagues").json()
    assert body["focus_league_id"] == 9 and body["focus_name"] == "NLT"


def test_a_dead_api_is_a_retriable_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)

    class Dead(FakeClient):
        def get_entry(self, entry_id):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(mod, "fpl_client", lambda: Dead())
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    resp = TestClient(create_app()).get("/api/league/leagues")
    assert resp.status_code == 422
    assert "retry" in resp.json()["detail"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_web_league_overview.py`
Expected: 404s / AttributeError on `_OVERVIEW`.

- [ ] **Step 3: Schemas**

In `src/gaffer/web/schemas.py`, after `class LeagueRace`:

```python
class PrivateLeagueRow(BaseModel):
    """One private mini-league the entry is in (v15 §5.1)."""

    league_id: int
    name: str
    rank: int | None = None
    last_rank: int | None = None
    entries: int | None = None
    """``rank_count`` from the entry payload; ``None`` before the league has
    a scored gameweek."""
    started: bool
    gap: int | None = None
    gap_kind: Literal["ahead", "behind"] | None = None
    would: Literal["chase", "defend"] | None = None
    """Gap-sign only — what the dial would lean to. The deadband and λ
    appear when the league is opened (``/race?league_id=``)."""
    is_focus: bool


class PublicLeagueRow(BaseModel):
    """A public or system league: rank line only (v15 §1.1)."""

    league_id: int
    name: str
    rank: int | None = None
    last_rank: int | None = None
    entries: int | None = None


class LeaguesOverview(BaseModel):
    focus_league_id: int
    focus_name: str | None = None
    """``None`` when the focus is not one of the private leagues, in which
    case ``focus_warning`` says so."""
    stance: Literal["auto", "chase", "defend", "neutral"]
    """``[league] stance`` as configured."""
    focus_stance: Literal["chase", "defend", "neutral"]
    focus_lam: float
    """The focus league's tilt as the next advise will see it: the solve
    state's λ with a manual stance applied (plan R2)."""
    focus_warning: str | None = None
    private: list[PrivateLeagueRow] = Field(default_factory=list)
    public: list[PublicLeagueRow] = Field(default_factory=list)
    gw: int | None = None
```

- [ ] **Step 4: Router**

In `src/gaffer/web/routers/league.py`:

Imports: add `import threading`, `import time`; extend the `gaffer.league_mode` import with `LeagueParams, apply_stance`; extend the schemas import with `LeaguesOverview, PrivateLeagueRow, PublicLeagueRow`; add `from gaffer.config import load_config` (already there).

After `_guard`, add:

```python
OVERVIEW_TTL_S = 300.0
"""How long the league list and its gaps are served from memory. Roughly
eight FPL calls uncached, asked for by two hubs."""

_OVERVIEW: dict[int, tuple[float, dict]] = {}
"""entry_id -> (monotonic stamp, rows). Holds only what the FPL API said —
never the focus or the stance, which come from config on every request."""
_OVERVIEW_LOCK = threading.Lock()


def _maybe_int(value) -> int | None:
    return None if value is None else int(value)


def _stance_of(lam: float) -> str:
    return "neutral" if lam == 0 else ("chase" if lam > 0 else "defend")


def _league_rows(client, cfg) -> dict:
    """The entry's classic leagues, split by the private flag, with a gap per
    started private league from one standings page. Cached per entry for
    ``OVERVIEW_TTL_S``.

    The gap is the leader's or the runner-up's total against mine: when I am
    not on page 1 my total is the entry payload's own. A league of one, or
    one with no scored gameweek yet, has no gap.
    """
    now = time.monotonic()
    with _OVERVIEW_LOCK:
        hit = _OVERVIEW.get(cfg.entry_id)
        if hit is not None and now - hit[0] < OVERVIEW_TTL_S:
            return hit[1]
    entry = _guard(client.get_entry, cfg.entry_id)
    my_total = int(entry.get("summary_overall_points") or 0)
    private, public = [], []
    for league in (entry.get("leagues") or {}).get("classic") or []:
        base = {"league_id": int(league["id"]), "name": str(league["name"]),
                "rank": _maybe_int(league.get("entry_rank")),
                "last_rank": _maybe_int(league.get("entry_last_rank")),
                "entries": _maybe_int(league.get("rank_count"))}
        if league.get("league_type") != "x":
            public.append(base)
            continue
        started = base["entries"] is not None
        gap = gap_kind = would = None
        if started and (base["entries"] or 0) > 1:
            page = _guard(client.get_league_standings, base["league_id"], 1)
            results = page["standings"]["results"]
            mine = next((r for r in results
                         if int(r["entry"]) == cfg.entry_id), None)
            total = int(mine["total"]) if mine else my_total
            others = sorted((int(r["total"]) for r in results
                             if int(r["entry"]) != cfg.entry_id), reverse=True)
            if others:
                if base["rank"] == 1:
                    gap, gap_kind, would = total - others[0], "ahead", "defend"
                else:
                    gap, gap_kind, would = others[0] - total, "behind", "chase"
        private.append({**base, "started": started, "gap": gap,
                        "gap_kind": gap_kind, "would": would})
    private.sort(key=lambda r: (r["rank"] if r["rank"] is not None else 10**9,
                                -(r["entries"] or 0)))
    public.sort(key=lambda r: -(r["entries"] or 0))
    rows = {"private": private, "public": public,
            "gw": _maybe_int(entry.get("current_event"))}
    with _OVERVIEW_LOCK:
        _OVERVIEW[cfg.entry_id] = (now, rows)
    return rows


def _focus_strategy(cfg) -> Strategy:
    """The focus league's tilt as the next advise will see it (plan R2): the
    solve state's λ, then the manual stance over it."""
    gw = latest_gw()
    state = load_solve_state(gw) if gw is not None else None
    lam = float(state.lam) if state else 0.0
    base = Strategy(lam=lam, gap=0, weeks_left=1, stance=_stance_of(lam),
                    rival_name="the field")
    return apply_stance(base, cfg.stance, LeagueParams.from_config(cfg))


@router.get("/leagues", response_model=LeaguesOverview)
def leagues() -> LeaguesOverview:
    """Every league the entry is in (v15 §5.1). Does not require a focus:
    with none, or a focus that is not private, the page still lists the
    leagues and says so in ``focus_warning``."""
    cfg = load_config()
    rows = _league_rows(fpl_client(), cfg)
    private = [PrivateLeagueRow(**r, is_focus=r["league_id"] == cfg.league_id)
               for r in rows["private"]]
    focus = next((r for r in private if r.is_focus), None)
    strategy = _focus_strategy(cfg)
    if focus is not None:
        warning = None
    elif cfg.league_id:
        warning = (f"focus league {cfg.league_id} is not one of your private "
                   "leagues — make one the focus below, or reset the focus "
                   "in Settings")
    else:
        warning = "no focus league yet — make one the focus below"
    return LeaguesOverview(
        focus_league_id=int(cfg.league_id), focus_name=focus.name if focus else None,
        stance=cfg.stance, focus_stance=strategy.stance,
        focus_lam=round(strategy.lam, 3), focus_warning=warning,
        private=private,
        public=[PublicLeagueRow(**r) for r in rows["public"]],
        gw=rows["gw"])
```

- [ ] **Step 5: Regenerate types** (standing-rules block).

- [ ] **Step 6: Run**

Run: `.venv/bin/pytest -q tests/test_web_league_overview.py tests/test_web_league.py tests/test_v12_w5_gen_types.py tests/test_v11_degradation.py`
Expected: overview and league tests pass; `test_v11_degradation.py`'s route pin FAILS on 48 — expected, orchestrator's Step 8.

- [ ] **Step 7: Commit (implementer)**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/league.py frontend/src/schemas.json frontend/src/types.generated.ts tests/test_web_league_overview.py
git commit -m "feat(v15): GET /api/league/leagues — every league, private with gaps, public as a rank line"
```

- [ ] **Step 8: Pin (ORCHESTRATOR ONLY)**

`tests/test_v11_degradation.py`, the routes test: append to the docstring `# v15 §5.4 (specs/2026-09-06-gaffer-v15-leagues-design.md) 48 → 49, and the one is /api/league/leagues — the overview.`; `== 48` → `== 49`; add `assert "/api/league/leagues" in paths`. Commit:

```bash
git add tests/test_v11_degradation.py
git commit -m "test(v15): route pin 48 -> 49, the one is /api/league/leagues"
```

---

### Task 5: `league_id` on race, rivals and rival; paging; the non-focus Strategy

**Files:**
- Modify: `src/gaffer/web/routers/league.py`
- Modify: `src/gaffer/web/schemas.py` (`LeagueRace`)
- Modify: `src/gaffer/cli.py:453-454`, `src/gaffer/league_sim.py:1156-1158` (messages only)
- Regenerate types
- Test: `tests/test_web_league.py` (extend)

- [ ] **Step 1: Extend the fake and write the failing tests**

In `tests/test_web_league.py`, replace `FakeClient` with one that knows two private leagues and pages, keeping the existing constants:

```python
ENTRY = {"summary_overall_points": 106, "current_event": 2,
         "leagues": {"classic": [
             {"id": 5, "name": "Focus FC League", "league_type": "x",
              "rank_count": 2, "entry_rank": 2, "entry_last_rank": 2},
             {"id": 9, "name": "Other League", "league_type": "x",
              "rank_count": 2, "entry_rank": 1, "entry_last_rank": 1},
             {"id": 314, "name": "Overall", "league_type": "s",
              "rank_count": 10_000_000, "entry_rank": 5, "entry_last_rank": 6},
         ], "h2h": []}}

OTHER_STANDINGS = {"standings": {"has_next": False, "results": [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me", "rank": 1,
     "last_rank": 1, "total": 106, "event_total": 55},
    {"entry": 3, "entry_name": "Slow Coach", "player_name": "Sl",
     "rank": 2, "last_rank": 2, "total": 60, "event_total": 30},
]}}

SLOW_HISTORY = {"current": [{"event": 1, "points": 30, "total_points": 30},
                            {"event": 2, "points": 30, "total_points": 60}],
                "chips": []}


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_entry(self, entry_id):
        return ENTRY

    def get_league_standings(self, league_id, page=1):
        self.calls.append((league_id, page))
        return OTHER_STANDINGS if league_id == 9 else STANDINGS

    def get_entry_history(self, entry_id):
        return {1: HISTORY, 2: RIVAL_HISTORY, 3: SLOW_HISTORY}[entry_id]

    def get_entry_picks(self, entry_id, gw):
        return PICKS

    def get_event_status(self):
        return {"status": [], "leagues": "updated"}
```

Update the `client` fixture to also `monkeypatch.setattr("gaffer.web.routers.league._OVERVIEW", {})` and to call `serving_config.cache_clear()` before and after (import it from `gaffer.config`). Every existing test must keep passing unchanged. Then append:

```python
def test_the_focus_race_names_its_league_and_its_source(client):
    body = client.get("/api/league/race").json()
    assert body["league_name"] == "Focus FC League"
    assert body["focus"] is True and body["stance_source"] == "auto"


def test_a_manual_stance_shows_on_the_focus_race_at_once(client, tmp_path):
    from gaffer.config import LOCAL_OVERLAY, serving_config

    (tmp_path / LOCAL_OVERLAY).write_text('[league]\nstance = "defend"\n')
    serving_config.cache_clear()
    body = client.get("/api/league/race").json()
    assert body["lam"] == -0.5 and body["stance"] == "defend"
    assert body["stance_source"] == "manual"
    assert "ahead" in body["lam_explained"]


def test_another_private_league_computes_its_own_display_strategy(client):
    body = client.get("/api/league/race?league_id=9").json()
    assert body["league_id"] == 9 and body["league_name"] == "Other League"
    assert body["focus"] is False and body["stance_source"] == "auto"
    assert [r["name"] for r in body["standings"]] == ["You FC", "Slow Coach"]
    # 46 ahead of the only rival at GW3: z = 46 / (sigma * sqrt(36)) clears
    # the 0.25 deadband for any sigma the dial allows (8..30), so it defends.
    assert body["stance"] == "defend" and body["lam"] < 0
    assert body["gap"][-1]["gap"] == 46


def test_a_league_that_is_not_private_is_refused_by_id(client):
    resp = client.get("/api/league/race?league_id=314")
    assert resp.status_code == 422
    assert "314" in resp.json()["detail"]
    resp = client.get("/api/league/race?league_id=12345")
    assert resp.status_code == 422


def test_a_focus_that_is_not_private_is_still_served(tmp_path, monkeypatch):
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 314\n')
    monkeypatch.setattr("gaffer.web.routers.league.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league._OVERVIEW", {})
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/league/race").json()
    assert body["league_id"] == 314 and body["league_name"] == "Overall"
    assert body["focus"] is True


def test_standings_page_until_my_row_is_in(tmp_path, monkeypatch):
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')

    def row(entry, rank, total):
        return {"entry": entry, "entry_name": f"T{entry}", "player_name": "P",
                "rank": rank, "last_rank": rank, "total": total,
                "event_total": 1}

    page1 = [row(100 + i, i + 1, 500 - i) for i in range(50)]
    page2 = [row(200 + i, 51 + i, 400 - i) for i in range(49)] + [row(1, 100, 106)]
    page3 = [row(300 + i, 101 + i, 200 - i) for i in range(50)]
    pages = {1: page1, 2: page2, 3: page3}

    class Paged(FakeClient):
        def get_league_standings(self, league_id, page=1):
            self.calls.append((league_id, page))
            return {"standings": {"has_next": page < 3,
                                  "results": pages[page]}}

        def get_entry_history(self, entry_id):
            return HISTORY if entry_id == 1 else RIVAL_HISTORY

    fake = Paged()
    monkeypatch.setattr("gaffer.web.routers.league.fpl_client", lambda: fake)
    monkeypatch.setattr("gaffer.web.routers.league._OVERVIEW", {})
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/league/race").json()
    # The overview asked league 5 for page 1 first; the race's own calls
    # are the last two, and page 3 is never fetched.
    assert fake.calls[-2:] == [(5, 1), (5, 2)]
    assert (5, 3) not in fake.calls
    assert any(r["is_you"] for r in body["standings"])
    assert len(body["standings"]) == 100


def test_rivals_and_rival_take_the_league_too(client):
    rivals = client.get("/api/league/rivals?league_id=9").json()
    assert [r["name"] for r in rivals] == ["Slow Coach"]
    detail = client.get("/api/league/rivals/3?league_id=9").json()
    assert detail["name"] == "Slow Coach"
    assert client.get("/api/league/rivals/3").status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_web_league.py`
Expected: the new tests fail (missing keys / 200 where 422 expected); the old ones pass.

- [ ] **Step 3: Schema**

`LeagueRace` gains, after `lam_explained`:

```python
    league_name: str = ""
    focus: bool = True
    """False when this is another private league opened for display: its
    λ is computed from its own standings and tilts nothing (v15 §3.3)."""
    stance_source: Literal["auto", "manual"] = "auto"
```

- [ ] **Step 4: Router**

Imports: add `import pandas as pd`, `from gaffer.data.league import HISTORY_COLS, STANDINGS_COLS`, and extend the league_mode import with `compute_strategy`.

Replace `_config` and `_standings`:

```python
def _config():
    cfg = load_config()
    if not cfg.league_id:
        raise GafferError("set fpl.league_id in config.toml, or make a "
                          "league the focus on the Leagues tab, to use this "
                          "page")
    return cfg


MAX_STANDINGS_PAGES = 4
"""Two hundred rows. Plan R1: the race fetches one history per row, so the
table stops at the page the user is on rather than one further."""


def _standings(client, league_id: int, entry_id: int) -> list[dict]:
    """Standings pages until the user's own row is in, capped (plan R1)."""
    rows, page = [], 1
    while True:
        data = _guard(client.get_league_standings, league_id, page)
        results = data["standings"]["results"]
        rows.extend(results)
        mine = any(int(r["entry"]) == entry_id for r in results)
        if (mine or not data["standings"].get("has_next")
                or page >= MAX_STANDINGS_PAGES):
            break
        page += 1
    return sorted(rows, key=lambda r: -int(r["total"]))


def _league(cfg, client, league_id: int | None) -> tuple[int, str, bool]:
    """``(id, name, is_focus)`` for the league asked for, or the focus.

    An explicit id must be one of the private leagues. The focus is served
    whatever it is (plan R3) — named from the classic list when it is there,
    "League {id}" otherwise — so today's single-league config keeps working.
    """
    rows = _league_rows(client, cfg)
    if league_id is None or int(league_id) == cfg.league_id:
        wanted = int(cfg.league_id)
        named = {r["league_id"]: r["name"]
                 for r in rows["private"] + rows["public"]}
        return wanted, named.get(wanted, f"League {wanted}"), True
    row = next((r for r in rows["private"] if r["league_id"] == int(league_id)),
               None)
    if row is None:
        raise GafferError(f"league {league_id} is not one of your private "
                          "leagues")
    return int(league_id), row["name"], False
```

Rewrite `race`:

```python
@router.get("/race", response_model=LeagueRace)
def race(league_id: int | None = None) -> LeagueRace:
    cfg = _config()
    client = fpl_client()
    league, league_name, is_focus = _league(cfg, client, league_id)
    rows = _standings(client, league, cfg.entry_id)
    standings = [StandingRow(entry=int(r["entry"]), name=str(r["entry_name"]),
                             player_name=str(r["player_name"]),
                             rank=int(r["rank"]), total=int(r["total"]),
                             event_total=int(r["event_total"]),
                             is_you=int(r["entry"]) == cfg.entry_id)
                 for r in rows]

    trajectory, by_entry = [], {}
    for row in standings:
        history = _guard(client.get_entry_history, row.entry)
        points = [GwPoint(gw=int(h["event"]), points=int(h["points"]),
                          total=int(h["total_points"]))
                  for h in history.get("current", [])]
        by_entry[row.entry] = {p.gw: p.total for p in points}
        trajectory.append(Trajectory(entry=row.entry, name=row.name,
                                     points=points))

    mine = by_entry.get(cfg.entry_id, {})
    leader = max((t for e, t in by_entry.items() if e != cfg.entry_id),
                 key=lambda t: max(t.values(), default=0), default={})
    gap = [GapPoint(gw=gw, gap=int(mine[gw] - leader.get(gw, 0)))
           for gw in sorted(mine)]

    my_total = max(mine.values(), default=0)
    scored_gw = max(mine, default=1)
    weeks_left = max(1, 38 - scored_gw)
    rivals = [row for row in standings if not row.is_you]
    win_probs = [WinProb(name=row.name, total=row.total,
                         p_win=round(win_probability(my_total, row.total,
                                                     weeks_left), 3))
                 for row in rivals]
    top = max(rivals, key=lambda r: r.total, default=None)
    params = LeagueParams.from_config(cfg)
    if is_focus:
        # The solver's own λ, then the manual stance over it (plan R2).
        state = load_solve_state(latest_gw()) if latest_gw() is not None else None
        lam = float(state.lam) if state else 0.0
        strategy = Strategy(lam=lam, gap=abs(my_total - (top.total if top else 0)),
                            weeks_left=weeks_left, stance=_stance_of(lam),
                            rival_name=top.name if top else "the field")
        strategy = apply_stance(strategy, cfg.stance, params)
    else:
        strategy = _display_strategy(cfg, rows, trajectory, my_total,
                                     scored_gw, weeks_left, params)
    return LeagueRace(league_id=league, entry_id=cfg.entry_id,
                      standings=standings, trajectory=trajectory, gap=gap,
                      win_probability=win_probs, lam=strategy.lam,
                      stance=strategy.stance,
                      lam_explained=explain_lam(strategy),
                      league_name=league_name, focus=is_focus,
                      stance_source=strategy.source)


def _display_strategy(cfg, rows, trajectory, my_total, scored_gw, weeks_left,
                      params) -> Strategy:
    """What the dial would say for a league that is not the focus (v15
    §3.3). Its own standings and the histories the race just fetched (plan
    R4); ``apply_stance`` is deliberately not applied — nothing here tilts."""
    rivals = pd.DataFrame([r for r in rows if int(r["entry"]) != cfg.entry_id],
                          columns=STANDINGS_COLS)
    if rivals.empty:
        return Strategy(lam=0.0, gap=0, weeks_left=weeks_left, stance="neutral",
                        rival_name="the field")
    history = pd.DataFrame(
        [{"entry": t.entry, "gw": p.gw, "points": p.points}
         for t in trajectory for p in t.points if p.gw <= scored_gw],
        columns=HISTORY_COLS)
    return compute_strategy(my_total, rivals, scored_gw + 1, history=history,
                            my_entry=cfg.entry_id, params=params)
```

`rivals` and `rival`:

```python
@router.get("/rivals", response_model=list[RivalSummary])
def rivals(league_id: int | None = None) -> list[RivalSummary]:
    cfg = _config()
    client = fpl_client()
    league, _, _ = _league(cfg, client, league_id)
    ...
    for row in _standings(client, league, cfg.entry_id):
```

```python
@router.get("/rivals/{entry_id}", response_model=RivalDetail)
def rival(entry_id: int, league_id: int | None = None) -> RivalDetail:
    ...
    league, _, _ = _league(cfg, client, league_id)
    row = next((r for r in _standings(client, league, cfg.entry_id)
                if int(r["entry"]) == entry_id), None)
    if row is None:
        raise GafferError(f"entry {entry_id} is not in league {league}")
```

`pd.DataFrame(list_of_dicts, columns=STANDINGS_COLS)` keeps only those keys; the standings rows carry all seven.

Messages: `src/gaffer/cli.py:454` → `"Set fpl.league_id in config.toml first, or make a league the focus on the League page."`; `src/gaffer/league_sim.py:1157-1158` → `"set fpl.league_id in config.toml, or make a league the focus on the League page, to use the league simulation"`.

- [ ] **Step 5: Regenerate types** (standing-rules block). `npx tsc --noEmit` may now fail on `RACE` literals in `frontend/src/hubs/League.test.tsx` etc. lacking the three new fields — fine for now, Task 10 owns those; note it in the commit message.

- [ ] **Step 6: Run**

Run: `.venv/bin/pytest -q tests/test_web_league.py tests/test_web_league_overview.py tests/test_web_live.py tests/test_v12_w5_gen_types.py tests/test_cli.py`
Expected: pass (if a test file in that list does not exist, drop it).

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/routers/league.py src/gaffer/web/schemas.py src/gaffer/cli.py src/gaffer/league_sim.py frontend/src/schemas.json frontend/src/types.generated.ts tests/test_web_league.py
git commit -m "feat(v15): race/rivals take a league_id; standings page to your row; a display Strategy for non-focus leagues; manual stance on the focus race"
```

---

### Task 6: The sim and the what-if take a league

**Files:**
- Modify: `src/gaffer/league_sim.py:1140-1170` (`build_inputs`)
- Modify: `src/gaffer/web/routers/league_sim.py` (`_cache_key` ~123-139, `_run` ~152-175, `sim` ~352, `whatif` ~440)
- Modify: `src/gaffer/web/schemas.py` (`LeagueWhatIfRequest` ~302)
- Regenerate types
- Test: `tests/test_web_league_sim.py` (extend), `tests/test_league_sim_inputs.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_league_sim.py` (its `FakeClient` must record standings calls; add `self.calls = []` in `__init__` and `self.calls.append((league_id, page))` in `get_league_standings` if it does not already, then keep a module-level handle by having the fixture build one `fake = FakeClient()` and `monkeypatch.setattr(... fpl_client, lambda: fake)`; expose it via a second fixture `fake` if needed):

```python
def test_the_sim_defaults_to_the_focus_league(client, fake):
    client.get("/api/league/sim")
    assert {c[0] for c in fake.calls if isinstance(c, tuple)} == {5}


def test_the_sim_takes_another_league(client, fake):
    client.get("/api/league/sim?league_id=9")
    assert 9 in {c[0] for c in fake.calls if isinstance(c, tuple)}


def test_the_cache_is_keyed_by_league(client):
    from gaffer.config import load_config
    from gaffer.web.routers.league_sim import _cache_key

    cfg = load_config()
    assert _cache_key(cfg, 3, 5) != _cache_key(cfg, 3, 9)
    assert _cache_key(cfg, 3, None) == _cache_key(cfg, 3, 5)


def test_the_whatif_carries_the_league(client, fake):
    resp = client.post("/api/league/whatif",
                       json={"pins": [], "league_id": 9})
    assert resp.status_code == 200
    assert 9 in {c[0] for c in fake.calls if isinstance(c, tuple)}
```

In `tests/test_league_sim_inputs.py`, add one test in the file's own style (its `FakeClient` and `here` fixture already exist; `_comp()` is the components frame):

```python
def test_build_inputs_takes_a_league_id_over_the_config(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    monkeypatch.setattr("gaffer.artifacts.load_components",
                        lambda gw: _comp())

    class Recording(FakeClient):
        asked = []

        def get_league_standings(self, league_id, page=1):
            self.asked.append(league_id)
            return STANDINGS

    ins = build_inputs(Config(entry_id=1, league_id=5), Recording(),
                       league_id=9)
    assert Recording.asked == [9]
    assert [e.entry for e in ins.entries] == [1, 2]
    build_inputs(Config(entry_id=1, league_id=5), Recording())
    assert Recording.asked == [9, 5]


def test_build_inputs_with_no_league_anywhere_says_so(here, monkeypatch):
    monkeypatch.setattr("gaffer.artifacts.latest_gw", lambda: 5)
    with pytest.raises(GafferError, match="focus"):
        build_inputs(Config(entry_id=1, league_id=0), FakeClient())
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest -q tests/test_web_league_sim.py tests/test_league_sim_inputs.py`
Expected: TypeError on `league_id`, 422/ignored body field.

- [ ] **Step 3: Implement**

`src/gaffer/league_sim.py`, `build_inputs`:

```python
def build_inputs(cfg, client, *, gw: int | None = None,
                 league_id: int | None = None) -> SimInputs:
    """...(existing docstring)...

    ``league_id`` (v15 §5.2) simulates another of the entry's leagues; ``None``
    is the focus, ``cfg.league_id``.
    """
    league = int(league_id) if league_id else int(getattr(cfg, "league_id", 0) or 0)
    if not league:
        raise GafferError(
            "set fpl.league_id in config.toml, or make a league the focus on "
            "the League page, to use the league simulation")
```
and `client.get_league_standings(league, page)` in the loop.

`src/gaffer/web/routers/league_sim.py`:

```python
def _cache_key(cfg, gw: int, league_id: int | None = None) -> tuple:
    ...
    league = int(league_id) if league_id else int(cfg.league_id)
    return (league, int(gw), stamp, field_stamp, int(cfg.sim_n),
            float(cfg.rival_drift))


def _run(cfg, gw: int | None = None, *, cached_only: bool = False,
         league_id: int | None = None):
    ...
    key = _cache_key(cfg, plan_gw, league_id)
    ...
    inputs = _guard(build_inputs, cfg, fpl_client(), gw=plan_gw,
                    league_id=league_id)
```

```python
@router.get("/sim", response_model=LeagueSimData)
def sim(league_id: int | None = None) -> LeagueSimData:
    cfg = load_config()
    gw = latest_gw()
    key = _cache_key(cfg, int(gw), league_id) if gw is not None else None
    result, inputs = _run(cfg, gw, league_id=league_id)
```
(keep the rest of `sim` as it is; if it calls `_cache_key` again, pass `league_id` there too.)

`whatif`: pass `league_id=req.league_id` to every `_run(...)` call inside it. Grep `_run(` across `src/gaffer/web/` — any other caller (This Week's captaincy chip path, `cached_only=True`) keeps the default, which is the focus.

`LeagueWhatIfRequest` gains:
```python
    league_id: int | None = None
    """Which private league to re-count (v15 §5.2); ``None`` is the focus."""
```

- [ ] **Step 4: Regenerate types.**

- [ ] **Step 5: Run**

Run: `.venv/bin/pytest -q tests/test_web_league_sim.py tests/test_league_sim_inputs.py tests/test_league_sim.py tests/test_v12_w5_gen_types.py`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/league_sim.py src/gaffer/web/routers/league_sim.py src/gaffer/web/schemas.py frontend/src/schemas.json frontend/src/types.generated.ts tests/test_web_league_sim.py tests/test_league_sim_inputs.py
git commit -m "feat(v15): the league sim and what-if take a league_id; cache keyed by league"
```

---

### Task 7: The one line in advise.py (ORCHESTRATOR ONLY)

**Files:**
- Modify: `src/gaffer/advise.py` (league_mode import; the league block ~line 715)
- Modify: `tests/test_league_stance.py` (remove the xfail marker)

- [ ] **Step 1:** In the `from gaffer.league_mode import (...)` list add `apply_stance`. After the `strat = compute_strategy(...)` call (the statement ending `params=LeagueParams.from_config(cfg))`), add:

```python
                # v15 §3.2: the manual stance, at full tilt, over the dial.
                strat = apply_stance(strat, cfg.stance,
                                     LeagueParams.from_config(cfg))
```

- [ ] **Step 2:** Remove the `xfail` marker from `test_advise_applies_the_stance_after_computing_it`.

- [ ] **Step 3:** `git diff src/gaffer/advise.py` — show it to the user in the running update. Run `.venv/bin/pytest -q tests/test_league_stance.py tests/test_advise.py`. Expected: pass.

- [ ] **Step 4:** Commit:

```bash
git add src/gaffer/advise.py tests/test_league_stance.py
git commit -m "feat(v15): advise applies the manual stance after computing the dial (one call)"
```

---

### Task 8: Settings tab renders a `choice` as a Segmented

**Files:**
- Modify: `frontend/src/hubs/model/SettingsTab.tsx` (`Field`, ~line 27-60)
- Test: `frontend/src/hubs/model/SettingsTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to the test file's `PANEL.rows` a row:

```ts
    { key: 'stance', label: 'Stance', kind: 'choice', value: 'auto',
      choices: ['auto', 'chase', 'defend', 'neutral'], lo: null, hi: null,
      section: 'league', help: 'Auto lets the standings set the tilt.',
      source: 'default' },
```
and tests:

```ts
  it('renders a choice as a pressed-button group with every option', async () => {
    render(<SettingsTab />)
    const group = await screen.findByRole('group', { name: 'Stance' })
    const buttons = within(group).getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(
      ['auto', 'chase', 'defend', 'neutral'])
    expect(within(group).getByRole('button', { name: 'auto' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('saves a choice on the click itself', async () => {
    render(<SettingsTab />)
    const group = await screen.findByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'defend' }))
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/api/settings',
                                          { key: 'stance', value: 'defend' }))
  })
```
(Import `within` from testing-library if the file does not already; check how the existing tests reference `Segmented` buttons elsewhere — `aria-pressed` is what `Segmented` sets.)

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/hubs/model/SettingsTab.test.tsx`
Expected: the new tests fail; the count of existing rows tests may need `+1` where a test counts controls — adjust that assertion.

- [ ] **Step 3: Implement**

Import `Segmented` from `'../../kit'`. In `Field`, after the `bool` branch:

```tsx
  if (row.kind === 'choice') {
    // v15 §4.2: a word from a fixed list. The save is the click, like the
    // toggle above — a segmented control with a separate Save button would
    // show a state the server does not have.
    return (
      <div className="flex flex-col gap-1">
        <span>{label(row)}</span>
        <Segmented
          label={label(row)}
          options={row.choices.map((c) => ({ value: c, label: c }))}
          value={String(row.value)}
          onChange={(next) => { if (!busy) onSave(next) }}
        />
      </div>
    )
  }
```

- [ ] **Step 4: Run**

Run: `cd frontend && npx tsc --noEmit; npx vitest run src/hubs/model src/kit`
Expected: the model and kit tests pass; `tsc` may still report the `RACE` literal errors from Task 5 (Task 10's), nothing in `model/`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hubs/model/SettingsTab.tsx frontend/src/hubs/model/SettingsTab.test.tsx
git commit -m "feat(v15): the Settings tab renders a choice row as a segmented control"
```

---

### Task 9: `LeaguesTab` — the overview

**Files:**
- Create: `frontend/src/hubs/league/LeaguesTab.tsx`
- Test: `frontend/src/hubs/league/LeaguesTab.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { LeaguesOverview } from '../../types'
import LeaguesTab from './LeaguesTab'

const OVERVIEW: LeaguesOverview = {
  focus_league_id: 5, focus_name: 'Focus FC League', stance: 'auto',
  focus_stance: 'chase', focus_lam: 0.31, focus_warning: null, gw: 5,
  private: [
    { league_id: 5, name: 'Focus FC League', rank: 15, last_rank: 80,
      entries: 138, started: true, gap: 12, gap_kind: 'behind',
      would: 'chase', is_focus: true },
    { league_id: 9, name: 'NLT', rank: 1, last_rank: 3, entries: 7,
      started: true, gap: 9, gap_kind: 'ahead', would: 'defend',
      is_focus: false },
    { league_id: 99, name: 'Next Season', rank: 3, last_rank: 0,
      entries: null, started: false, gap: null, gap_kind: null,
      would: null, is_focus: false },
  ],
  public: [
    { league_id: 314, name: 'Overall', rank: 430473, last_rank: 2562053,
      entries: 10409391 },
  ],
}

function mount(overview = OVERVIEW, props = {}) {
  const onFocus = vi.fn()
  const onStance = vi.fn()
  render(
    <MemoryRouter>
      <LeaguesTab overview={overview} busy={false} onFocus={onFocus}
                  onStance={onStance} {...props} />
    </MemoryRouter>,
  )
  return { onFocus, onStance }
}

describe('LeaguesTab', () => {
  it('lists every private league with rank, size, move and gap', () => {
    mount()
    const focus = screen.getByTestId('league-5')
    expect(within(focus).getByText('15')).toBeInTheDocument()
    expect(within(focus).getByText('138')).toBeInTheDocument()
    expect(within(focus).getByText('▲ 65')).toBeInTheDocument()
    expect(within(focus).getByText('−12 to 1st')).toBeInTheDocument()
    const nlt = screen.getByTestId('league-9')
    expect(within(nlt).getByText('+9 on 2nd')).toBeInTheDocument()
    expect(within(nlt).getByText('would defend')).toBeInTheDocument()
  })

  it('marks the focus row and shows its live stance and tilt', () => {
    mount()
    const focus = screen.getByTestId('league-5')
    expect(focus).toHaveAttribute('data-focus', 'true')
    expect(within(focus).getByText('focus')).toBeInTheDocument()
    expect(within(focus).getByText('chase · λ +0.31')).toBeInTheDocument()
    expect(within(focus).queryByRole('button', { name: /make focus/ }))
      .toBeNull()
  })

  it('links a private league to its race', () => {
    mount()
    expect(screen.getByRole('link', { name: 'NLT' }))
      .toHaveAttribute('href', '/league?tab=race&league=9')
  })

  it('offers make focus on the other started leagues and reports the id', async () => {
    const { onFocus } = mount()
    const nlt = screen.getByTestId('league-9')
    await userEvent.click(within(nlt).getByRole('button', { name: 'make focus' }))
    expect(onFocus).toHaveBeenCalledWith(9)
  })

  it('shows a league that has not started as such, with no action', () => {
    mount()
    const row = screen.getByTestId('league-99')
    expect(within(row).getByText('not started')).toBeInTheDocument()
    expect(within(row).queryByRole('button')).toBeNull()
    expect(within(row).queryByRole('link')).toBeNull()
  })

  it('names the stance control with the live word on auto', () => {
    mount()
    const group = screen.getByRole('group', { name: 'Stance' })
    expect(within(group).getByRole('button', { name: 'Auto · chase' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('reports a stance click', async () => {
    const { onStance } = mount()
    const group = screen.getByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'Defend' }))
    expect(onStance).toHaveBeenCalledWith('defend')
  })

  it('flags a manual stance on the focus row', () => {
    mount({ ...OVERVIEW, stance: 'defend', focus_stance: 'defend',
            focus_lam: -0.5 })
    const focus = screen.getByTestId('league-5')
    expect(within(focus).getByText('manual')).toBeInTheDocument()
    expect(within(focus).getByText('defend · λ −0.50')).toBeInTheDocument()
  })

  it('lists public leagues as a rank line', () => {
    mount()
    const row = screen.getByTestId('public-314')
    expect(within(row).getByText('430,473')).toBeInTheDocument()
    expect(within(row).getByText('10,409,391')).toBeInTheDocument()
    expect(within(row).queryByRole('button')).toBeNull()
  })

  it('shows the focus warning as a warn callout', () => {
    mount({ ...OVERVIEW, focus_name: null,
            focus_warning: 'focus league 42 is not one of your private leagues' })
    const callout = screen.getByTestId('focus-warning')
    expect(callout).toHaveAttribute('data-tone', 'warn')
    expect(callout).toHaveTextContent('42')
  })

  it('has an empty state with no private leagues, and still the public table', () => {
    mount({ ...OVERVIEW, private: [], focus_name: null })
    expect(screen.getByText('You are in no private leagues')).toBeInTheDocument()
    expect(screen.getByTestId('public-314')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/hubs/league/LeaguesTab.test.tsx`
Expected: cannot resolve `./LeaguesTab`.

- [ ] **Step 3: Implement**

```tsx
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Button, Callout, Card, Chip, EmptyState, Segmented, TABLE_CLASS,
  THEAD_CLASS, TR_CLASS, TR_SELECTED_CLASS, fmtNum, tdClass, thClass,
} from '../../kit'
import type { LeaguesOverview, PrivateLeagueRow } from '../../types'

/** The four words `[league] stance` may be (v15 §3.2). */
export const STANCES = ['auto', 'chase', 'defend', 'neutral'] as const
export type Stance = typeof STANCES[number]

export interface LeaguesTabProps {
  overview: LeaguesOverview
  /** A settings write is in flight: the controls stay put until it lands. */
  busy: boolean
  onFocus: (leagueId: number) => void
  onStance: (stance: Stance) => void
}

const n = (value: number) => value.toLocaleString('en-GB')

/** Rank movement since last week. FPL sends 0 for "no last rank". */
function Move({ rank, last_rank }: { rank: number | null
                                     last_rank: number | null }): ReactNode {
  if (!rank || !last_rank) return <span className="text-text-muted">—</span>
  const delta = last_rank - rank
  if (delta === 0) return <span className="text-text-muted">=</span>
  // Up the table is a direction relative to where you were (rule 1).
  return (
    <Chip tone={delta > 0 ? 'up' : 'down'}>
      {`${delta > 0 ? '▲' : '▼'} ${n(Math.abs(delta))}`}
    </Chip>
  )
}

function gapText(row: PrivateLeagueRow): string {
  if (!row.started) return 'not started'
  if (row.gap === null || row.gap_kind === null) return '—'
  return row.gap_kind === 'ahead'
    ? `+${n(row.gap)} on 2nd` : `−${n(row.gap)} to 1st`
}

/** λ with its sign, the minus a real minus like every other number here. */
function lamText(lam: number): string {
  const body = fmtNum(Math.abs(lam), 2)
  return lam < 0 ? `−${body}` : `+${body}`
}

export default function LeaguesTab(
  { overview, busy, onFocus, onStance }: LeaguesTabProps,
) {
  const autoLabel = `Auto · ${overview.focus_stance}`
  const stanceOptions = STANCES.map((s) => ({
    value: s,
    label: s === 'auto' ? autoLabel : s[0].toUpperCase() + s.slice(1),
  }))

  return (
    <>
      {overview.focus_warning && (
        <Callout tone="warn" className="mb-4" data-testid="focus-warning">
          {overview.focus_warning}
        </Callout>
      )}
      <Card title="Private leagues" className="mb-4">
        {overview.private.length === 0 ? (
          <EmptyState
            title="You are in no private leagues"
            detail="Join or create a mini-league on the FPL site; it appears here on the next load."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE_CLASS}>
              <thead className={THEAD_CLASS}>
                <tr>
                  <th className={thClass()}>League</th>
                  <th className={thClass(true)}>Rank</th>
                  <th className={thClass(true)}>Of</th>
                  <th className={thClass(true)}>Move</th>
                  <th className={thClass(true)}>Gap</th>
                  <th className={thClass()}>Would</th>
                  <th className={thClass()}></th>
                </tr>
              </thead>
              <tbody>
                {overview.private.map((row) => (
                  <tr key={row.league_id}
                      data-testid={`league-${row.league_id}`}
                      data-focus={String(row.is_focus)}
                      className={`${TR_CLASS}${row.is_focus
                        ? ` ${TR_SELECTED_CLASS}` : ''}`}>
                    <td className={`${tdClass()} ${row.is_focus
                      ? 'text-text' : 'text-text-secondary'}`}>
                      {row.started ? (
                        <Link to={`/league?tab=race&league=${row.league_id}`}
                              className="text-accent-text hover:underline">
                          {row.name}
                        </Link>
                      ) : row.name}
                    </td>
                    <td className={`${tdClass(true)} text-text`}>
                      {row.rank === null ? '—' : n(row.rank)}
                    </td>
                    <td className={`${tdClass(true)} text-text-muted`}>
                      {row.entries === null ? '—' : n(row.entries)}
                    </td>
                    <td className={tdClass(true)}>
                      <Move rank={row.rank} last_rank={row.last_rank} />
                    </td>
                    <td className={`${tdClass(true)} ${row.started
                      ? 'text-text' : 'text-text-muted'}`}>
                      {gapText(row)}
                    </td>
                    <td className={`${tdClass()} text-text-muted`}>
                      {row.is_focus ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span className="text-text">
                            {`${overview.focus_stance} · λ ${lamText(overview.focus_lam)}`}
                          </span>
                          {overview.stance !== 'auto' && (
                            <Chip tone="warn">manual</Chip>
                          )}
                        </span>
                      ) : row.would ? `would ${row.would}` : '—'}
                    </td>
                    <td className={tdClass()}>
                      {row.is_focus ? (
                        <Chip tone="neutral" className="text-accent-text">focus</Chip>
                      ) : row.started ? (
                        <Button variant="ghost" disabled={busy}
                                onClick={() => onFocus(row.league_id)}>
                          make focus
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {overview.private.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="label">Stance · focus league</span>
            <Segmented
              label="Stance"
              options={stanceOptions}
              value={overview.stance}
              onChange={(next) => { if (!busy) onStance(next) }}
            />
          </div>
        )}
      </Card>
      <Card title="Public leagues">
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass()}>League</th>
                <th className={thClass(true)}>Rank</th>
                <th className={thClass(true)}>Of</th>
                <th className={thClass(true)}>Move</th>
              </tr>
            </thead>
            <tbody>
              {overview.public.map((row) => (
                <tr key={row.league_id}
                    data-testid={`public-${row.league_id}`}
                    className={TR_CLASS}>
                  <td className={`${tdClass()} text-text-secondary`}>{row.name}</td>
                  <td className={`${tdClass(true)} text-text`}>
                    {row.rank === null ? '—' : n(row.rank)}
                  </td>
                  <td className={`${tdClass(true)} text-text-muted`}>
                    {row.entries === null ? '—' : n(row.entries)}
                  </td>
                  <td className={tdClass(true)}>
                    <Move rank={row.rank} last_rank={row.last_rank} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}
```

Check `Button` forwards `disabled` (it extends `ButtonHTMLAttributes`, so it does) and that `Chip` accepts `className` (it does). If `EmptyState` requires an `action` prop, pass `action="fantasy.premierleague.com"`.

- [ ] **Step 4: Run**

Run: `cd frontend && npx vitest run src/hubs/league/LeaguesTab.test.tsx src/kit/tokens.test.ts`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hubs/league/LeaguesTab.tsx frontend/src/hubs/league/LeaguesTab.test.tsx
git commit -m "feat(v15): LeaguesTab — every private league, the focus mark, the stance control, public leagues as a rank line"
```

---

### Task 10: The League hub — tabs, `?league=`, writes, header, note

**Files:**
- Modify: `frontend/src/hubs/League.tsx`
- Modify: `frontend/src/hubs/league/RivalDetail.tsx` (~line 52-60), `frontend/src/hubs/league/WhatIfSim.tsx` (props, body ~line 53)
- Test: `frontend/src/hubs/League.test.tsx`, `frontend/src/hubs/league/RivalDetail.test.tsx`, `frontend/src/hubs/league/WhatIfSim.test.tsx`; retarget `hubs/taburl.test.tsx`, `hubs/responsive.test.tsx`, `hubs/w5.coldclone.test.tsx` where they assume the League default tab is `race`

- [ ] **Step 1: Write the failing tests**

In `League.test.tsx`: add `league_name: 'Focus FC League', focus: true, stance_source: 'auto'` to `RACE`; add an `OVERVIEW` constant (copy the one from `LeaguesTab.test.tsx`, focus id 1234 named 'Focus FC League' plus a second private league 9 'NLT'); make the `apiGet` mock answer `/api/league/leagues` with it and `/api/league/race?league_id=9` with `{ ...RACE, league_id: 9, league_name: 'NLT', focus: false, stance: 'defend', lam: -0.2 }`; mock `apiPost` as a `vi.fn()` resolving `{}`. Existing tests that assert race content on mount must render with `initialEntries={['/league?tab=race']}`. Then add:

```tsx
  it('opens on the Leagues tab and lists the leagues', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('league-9')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Leagues' })).toBeInTheDocument()
  })

  it('fetches the league named in the URL and shows a way back', async () => {
    render(<MemoryRouter initialEntries={['/league?tab=race&league=9']}>
             <League /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'NLT' })).toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/league/race?league_id=9')
    expect(apiGet).toHaveBeenCalledWith('/api/league/rivals?league_id=9')
    expect(apiGet).toHaveBeenCalledWith('/api/league/sim?league_id=9')
    expect(screen.getByRole('link', { name: '‹ Leagues' }))
      .toHaveAttribute('href', '/league?tab=leagues')
  })

  it('says which league sets the plan when this is not it', async () => {
    render(<MemoryRouter initialEntries={['/league?tab=race&league=9']}>
             <League /></MemoryRouter>)
    const note = await screen.findByTestId('focus-note')
    expect(note).toHaveTextContent('Plan is set by Focus FC League (chase)')
    expect(note).toHaveTextContent('Here you would defend, λ −0.20')
  })

  it('has no such note on the focus league', async () => {
    render(<MemoryRouter initialEntries={['/league?tab=race']}>
             <League /></MemoryRouter>)
    await screen.findByText('Cumulative points')
    expect(screen.queryByTestId('focus-note')).toBeNull()
  })

  it('writes the focus through settings and refetches', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    const nlt = await screen.findByTestId('league-9')
    await userEvent.click(within(nlt).getByRole('button', { name: 'make focus' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/settings', { key: 'league_id', value: 9 }))
    await waitFor(() => expect(
      apiGet.mock.calls.filter(([p]) => p === '/api/league/leagues').length)
      .toBeGreaterThan(1))
  })

  it('writes the stance through settings', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    await screen.findByTestId('league-9')
    const group = screen.getByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'Neutral' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/settings', { key: 'stance', value: 'neutral' }))
  })

  it('toasts a refused write and keeps the page', async () => {
    apiPost.mockRejectedValueOnce(new Error('Stance is one of auto, chase, defend, neutral'))
    render(<MemoryRouter><League /></MemoryRouter>)
    await screen.findByTestId('league-9')
    const group = screen.getByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'Chase' }))
    expect(await screen.findByText(/Could not set the stance/)).toBeInTheDocument()
  })
```
(For the toast assertion, check how other hub tests observe toasts — e.g. `frontend/src/hubs/planning/DraftsTab.test.tsx` — and copy that; if they render `ToastOutlet`, do the same.)

`RivalDetail.test.tsx`: one test that with `initialEntries={['/league/rival/2?league=9']}` the fetch is `/api/league/rivals/2?league_id=9`.

`WhatIfSim.test.tsx`: one test that with `leagueId={9}` the posted body carries `league_id: 9`, and without it carries `league_id: null`.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/hubs/League.test.tsx src/hubs/league`
Expected: the new tests fail.

- [ ] **Step 3: Implement League.tsx**

Replace the imports and the component's state/effects/header; keep every existing JSX block for the race, rivals and what-if contents verbatim, moved under the guards shown.

```tsx
import * as Tabs from '@radix-ui/react-tabs'
import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
// (recharts import unchanged)
import { apiGet, apiPost, errorText } from '../api/client'
import {
  type Column, Callout, Card, DataTable, EmptyState, Loading, PageHeader,
  Sparkline, Stat, StatRow, TABLE_CLASS, TAB_CLASS, TAB_LIST_CLASS, THEAD_CLASS,
  TR_CLASS, TR_SELECTED_CLASS, fmtNum, fmtPct, tdClass, thClass, toast,
  useTabParam,
} from '../kit'
import type {
  AdviceLatest, LeagueRaceData, LeagueSimData, LeaguesOverview, RivalSummary,
} from '../types'
import FieldPanel from './league/FieldPanel'
import LeaguesTab, { type Stance } from './league/LeaguesTab'
import WhatIfSim, { type WhatIfSquadPlayer } from './league/WhatIfSim'

// v15 §6.1: the overview first. `race`/`rivals`/`whatif` show the league in
// `?league=`, or the focus when it is absent.
const TABS = ['leagues', 'race', 'rivals', 'whatif'] as const

/** `path?league_id=N` when a league is chosen; the bare path is the focus. */
function withLeague(path: string, leagueId: number | null): string {
  return leagueId === null ? path : `${path}?league_id=${leagueId}`
}
```

Inside `League()`:

```tsx
export default function League() {
  const [tab, setTab] = useTabParam(TABS, 'leagues')
  const [params] = useSearchParams()
  const asked = params.get('league')
  const leagueId = asked !== null && /^\d+$/.test(asked) ? Number(asked) : null
  const [overview, setOverview] = useState<LeaguesOverview | null>(null)
  const [race, setRace] = useState<LeagueRaceData | null>(null)
  const [rivals, setRivals] = useState<RivalSummary[]>([])
  const [missing, setMissing] = useState<string | null>(null)
  const [sim, setSim] = useState<LeagueSimData | null>(null)
  const [squad, setSquad] = useState<WhatIfSquadPlayer[]>([])
  const [busy, setBusy] = useState(false)

  const loadOverview = useCallback(() => {
    apiGet<LeaguesOverview>('/api/league/leagues')
      .then(setOverview).catch(() => setOverview(null))
  }, [])

  const loadLeague = useCallback(() => {
    setRace(null)
    apiGet<LeagueRaceData>(withLeague('/api/league/race', leagueId))
      .then((body) => { setRace(body); setMissing(null) })
      .catch((e) => setMissing(errorText(e)))
    apiGet<RivalSummary[]>(withLeague('/api/league/rivals', leagueId))
      .then(setRivals).catch(() => setRivals([]))
    apiGet<LeagueSimData>(withLeague('/api/league/sim', leagueId))
      .then(setSim).catch(() => setSim(null))
  }, [leagueId])

  useEffect(() => { loadOverview() }, [loadOverview])
  useEffect(() => { loadLeague() }, [loadLeague])
  useEffect(() => {
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((body) => setSquad(body.advice.xi.map((p) => (
        { code: p.code, name: p.name, position: p.position ?? '' }))))
      .catch(() => setSquad([]))
  }, [])

  // Both writes go through the settings endpoint (v15 §4.2), so the Model
  // tab, the CLI and the solve job read the same file. A refusal is a toast
  // and the control stays where the server left it.
  function write(key: 'league_id' | 'stance', value: number | string,
                 what: string) {
    setBusy(true)
    apiPost('/api/settings', { key, value })
      .then(() => { loadOverview(); loadLeague() })
      .catch((e) => toast('negative', `Could not ${what} — ${errorText(e)}`))
      .finally(() => setBusy(false))
  }
  const onFocus = (id: number) => write('league_id', id, 'set the focus league')
  const onStance = (s: Stance) => write('stance', s, 'set the stance')

  if (missing !== null && overview === null) {
    return (
      <>
        <PageHeader title="League" />
        <EmptyState
          title="No league configured"
          detail="Set fpl.league_id to your mini-league, then run advise so the
                  rival ownership table is built."
          action="config.toml"
        />
      </>
    )
  }

  const onLeagues = tab === 'leagues'
  const title = onLeagues ? 'Leagues' : (race?.league_name ?? 'League')
  const back = onLeagues ? undefined : (
    <Link to="/league?tab=leagues" className="text-accent-text hover:underline">
      ‹ Leagues
    </Link>
  )
```

Keep the existing derivations (`chart`, `isYou`, `trajectory`, `you`, `leagueContext`, `rivalColumns`) but guard them: compute them only when `race` is non-null (wrap in `race ? ... : ...` or move into a small `RacePanel` local — simplest is to keep them after an early `const raceReady = race !== null` and use optional chaining; the tab contents below render `<Loading />` when `race` is null). The rival link in `rivalColumns` becomes `` `/league/rival/${r.entry}${leagueId === null ? '' : `?league=${leagueId}`}` ``.

The header and tab list:

```tsx
  return (
    <>
      <PageHeader title={title} context={race ? leagueContext : undefined}
                  action={back} />
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className={TAB_LIST_CLASS}>
          <Tabs.Trigger value="leagues" className={TAB_CLASS}>Leagues</Tabs.Trigger>
          <Tabs.Trigger value="race" className={TAB_CLASS}>Race</Tabs.Trigger>
          <Tabs.Trigger value="rivals" className={TAB_CLASS}>Rivals</Tabs.Trigger>
          <Tabs.Trigger value="whatif" className={TAB_CLASS}>What if</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="leagues">
          {overview ? (
            <LeaguesTab overview={overview} busy={busy}
                        onFocus={onFocus} onStance={onStance} />
          ) : <Loading />}
        </Tabs.Content>
        <Tabs.Content value="race">
          {race === null ? (missing !== null
            ? <Callout tone="error">{missing}</Callout> : <Loading />) : (
            <>
              {overview && !race.focus && (
                <Callout tone="note" className="mb-4" data-testid="focus-note">
                  {`Plan is set by ${overview.focus_name ?? 'the focus league'} `
                   + `(${overview.stance === 'auto'
                        ? overview.focus_stance : `manual ${overview.stance}`}). `
                   + `Here you would ${race.stance === 'neutral'
                        ? 'be neutral' : race.stance}, λ ${lamText(race.lam)}.`}
                </Callout>
              )}
              {/* existing race JSX: chart card, standings card, win
                  probability card(s), FieldPanel — verbatim */}
            </>
          )}
        </Tabs.Content>
        <Tabs.Content value="rivals">
          {/* existing rivals DataTable, verbatim */}
        </Tabs.Content>
        <Tabs.Content value="whatif">
          {race === null ? <Loading /> : (
            <WhatIfSim
              squad={squad}
              leagueId={leagueId}
              rivals={race.standings.filter((s) => !s.is_you)
                .map((s) => ({ entry: s.entry, name: s.name }))}
            />
          )}
        </Tabs.Content>
      </Tabs.Root>
    </>
  )
```

Add a module-level `lamText` identical to `LeaguesTab`'s (or export it from `LeaguesTab.tsx` and import it — prefer the export).

`WhatIfSim.tsx`: add `leagueId?: number | null` to `WhatIfSimProps`, destructure it (default `null`), put `league_id: leagueId` in the request body and add `leagueId` to the effect's dependency list.

`RivalDetail.tsx`: `const [params] = useSearchParams()`; `const league = params.get('league')`; fetch `` `/api/league/rivals/${entryId}${league ? `?league_id=${league}` : ''}` ``; add `league` to the effect deps.

- [ ] **Step 4: Run and retarget**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: `tsc` silent (this task clears the `RACE`-literal errors from Task 5 by adding the three fields wherever a `LeagueRaceData` literal is built in tests). Fix `taburl.test.tsx`, `responsive.test.tsx`, `w5.coldclone.test.tsx` and any other test that assumed the League hub opens on `race` — they now either navigate to `?tab=race` or assert the Leagues tab. Every test must pass and the summary must show no `Errors N error` line.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hubs/League.tsx frontend/src/hubs/League.test.tsx frontend/src/hubs/league/RivalDetail.tsx frontend/src/hubs/league/RivalDetail.test.tsx frontend/src/hubs/league/WhatIfSim.tsx frontend/src/hubs/league/WhatIfSim.test.tsx
# plus any retargeted test files under frontend/src/hubs/
git commit -m "feat(v15): League hub — Leagues tab first, ?league= drives race/rivals/what-if, focus and stance written through settings, the plan note"
```

---

### Task 11: This Week's League tile

**Files:**
- Modify: `frontend/src/hubs/ThisWeek.tsx` (state ~line 60-70, the `Stat label="League"` ~line 255-262)
- Modify: `frontend/src/types.ts` (`Strategy` gains `source?: string`)
- Test: `frontend/src/hubs/ThisWeek.test.tsx`

- [ ] **Step 1: Write the failing tests**

In the test's `apiGet` mock add `if (path === '/api/league/leagues') return Promise.resolve(OVERVIEW)` with an `OVERVIEW` constant (focus_name 'Shocky Supplies', stance 'auto', focus_stance 'chase', focus_lam 0.25, empty lists, gw 5, focus_league_id 1, focus_warning null). Then:

```tsx
  it('captions the league gap with the focus league', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    const league = (await screen.findByText('League')).closest('div')!
    expect(await within(league).findByText(/Shocky Supplies · chase · tilt \+0\.25/))
      .toBeInTheDocument()
    expect(within(league).queryByText('manual')).toBeNull()
  })

  it('flags a manual stance on the tile', async () => {
    apiGet.mockImplementation((path: string) => path === '/api/league/leagues'
      ? Promise.resolve({ ...OVERVIEW, stance: 'defend', focus_stance: 'defend' })
      : defaultMock(path))   // whatever the file's default implementation is named
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    const league = (await screen.findByText('League')).closest('div')!
    expect(await within(league).findByText('manual')).toBeInTheDocument()
  })
```
The existing `states the league gap...` test keeps passing: its regex still matches inside the longer sentence.

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx`

- [ ] **Step 3: Implement**

`types.ts`, `Strategy`: add `source?: string` with a one-line comment (v15: "auto" | "manual", absent on older payloads).

`ThisWeek.tsx`: import `Chip` and `LeaguesOverview`; add state and a fetch beside the advice load (its own effect, failure → `null`):

```tsx
  const [leagues, setLeagues] = useState<LeaguesOverview | null>(null)
  useEffect(() => {
    apiGet<LeaguesOverview>('/api/league/leagues')
      .then(setLeagues).catch(() => setLeagues(null))
  }, [])
```

The tile:

```tsx
        <Stat
          label="League"
          value={strategy ? fmtNum(Math.abs(strategy.gap), 0) : '—'}
          unit={strategy ? gapUnit(strategy.stance) : undefined}
          context={strategy ? (
            <span className="inline-flex items-center gap-1.5">
              {`${leagues?.focus_name ? `${leagues.focus_name} · ` : ''}`
               + `${strategy.stance} · tilt ${strategy.lam >= 0 ? '+' : ''}`
               + fmtNum(strategy.lam, 2)}
              {leagues && leagues.stance !== 'auto' && (
                <Chip tone="warn">manual</Chip>
              )}
            </span>
          ) : undefined}
        />
```

- [ ] **Step 4: Run**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/hubs/ThisWeek.test.tsx src/hubs/this-week src/kit/tokens.test.ts`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx frontend/src/types.ts
git commit -m "feat(v15): This Week's league tile names the focus league and flags a manual stance"
```

---

### Task 12: Full suites, gate, merge (ORCHESTRATOR)

- [ ] **Step 1: Suites**

```bash
.venv/bin/pytest -q 2>&1 | tail -3
cd frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -6 && cd ..
```
Expected: `> 4110 passed`, nothing failing; vitest `> 866 passed`, no `Errors` line.

- [ ] **Step 2: Build and screenshot**

```bash
cd frontend && npm run build && cd ..
uv run gaffer ui --no-open-browser --port 8927 &
```
Extend `frontend/scripts/shots.sh`'s URL list with `league-leagues /league?tab=leagues`, `league-other /league?tab=race&league=<a non-focus private id>`, `settings /model?tab=settings`, then `frontend/scripts/shots.sh v15-gate` and build the companion page with the scratchpad `gate_page.py`. User approves.

- [ ] **Step 3: Security ritual, merge, push**

```bash
V="$(sed -n '/^\[odds\]/,/^\[/p' config.toml | grep '^api_key' | cut -d'"' -f2)"
[ "${#V}" -ge 8 ] || echo "extraction failed"
git grep -c "$V" v15-leagues        # must print nothing
git checkout main && git merge --ff-only v15-leagues && git push
git show main:config.toml           # must fail
```

- [ ] **Step 4: Docs and memory** — GUIDE §5/§11, ROADMAP v15 block, memory `fpl-advisor-project.md`.
