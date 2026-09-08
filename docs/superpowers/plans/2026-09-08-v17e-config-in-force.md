# v17e — the config in force, one interface: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Spec: `docs/superpowers/specs/2026-09-08-v17e-config-in-force-design.md`. Read CLAUDE.md first. Implementers never open `config.toml`, never run `python -m tests.golden_client --record` or `--write`, never run `tests/test_golden_board.py` or `tests/test_pipeline.py` (the orchestrator's gate), and never touch a file the spec's §7 table marks orchestrator-only.

**Goal:** one cached read of the config in force (`config_in_force()`), one clearing (`invalidate()`), the four private TOML readers as `Config` fields, bounds and offered options stated once on the settings registry, and the ladder card's selects rendered from the settings rows.

**Architecture:** `src/gaffer/config.py` becomes the only module that opens `config.toml` or `config.local.toml`: it gains three fields, `Config.solver_top_n()`, `BOUNDS`/`out_of_range`, `config_in_force`/`invalidate`, and the overlay's read/write/source helpers the settings router used to do itself. `web/settings_keys.py` takes its bounds from `BOUNDS` and gains `options`; `web/schemas.py` serves them; `LadderCard.tsx` renders them. Old names are kept as thin wrappers through Task 2 so the orchestrator can move the protected rails on a green tree, then deleted in Task 3.

**Tech stack:** Python 3 (`tomllib`, `tomli_w`, pydantic, FastAPI), pytest; React 18 + TypeScript + vitest. `npm run types` regenerates the wire types.

---

## File map

| Path | Owner | Responsibility |
|---|---|---|
| `src/gaffer/config.py` | implementer (Tasks 1, 3, 6) | the one module that opens the two files; fields, accessor, bounds, view, invalidation, overlay helpers |
| `tests/test_v17e_config.py` | implementer (Tasks 1, 4, 6) | the cycle's rail and unit tests |
| `tests/test_v12_top_n.py`, `tests/test_v12_price_timing.py`, `tests/test_v12_xg_per_shot.py`, `tests/test_v10_config_providers.py` | implementer (Task 1) | the reader tests become loader/field tests |
| `tests/test_v13_degradation.py`, `tests/test_v10_degradation.py`, `tests/test_v12_w2_degradation.py`, `tests/test_v12_w5_degradation.py`, `tests/test_v8e_degradation.py`, `tests/test_web_job_kinds_v8f.py`, `tests/test_v12_w5_settings.py` (one test), `src/gaffer/optimize/milp.py` | **orchestrator (Task 2)** | the pin, the rails, the solver's one read |
| every other `src/` and `scripts/` site of `serving_config`, `price_timing()`, `xg_per_shot()`, `lineup_providers()`, `optimizer_top_n()`; 18 unprotected test files; `tests/golden_client.py`; `tests/test_golden_board.py` | implementer (Task 3) | renames, deletions, the golden header comparison |
| `src/gaffer/web/settings_keys.py`, `src/gaffer/web/routers/settings.py`, `src/gaffer/web/routers/meta.py`, `src/gaffer/web/schemas.py`, `frontend/src/schemas.json`, `frontend/src/types.generated.ts` | implementer (Task 4) | bounds from `BOUNDS`, options, one refusal sentence, no file access in the router |
| `frontend/src/hubs/this-week/LadderCard.tsx`, `LadderCard.test.tsx`, `frontend/src/hubs/ThisWeek.test.tsx`, `frontend/src/hubs/model/SettingsTab.test.tsx`, `frontend/scripts/shots.sh` | implementer (Task 5) | the card over the rows; the v17e shot stage |
| docs, tracker, memory | orchestrator (Task 7) | after the gate |

Shared names, used identically in every task: `config_in_force()`, `invalidate()`, `Config.solver_top_n()`, `DEFAULT_TOP_N` (now in `gaffer.config`), `BOUNDS`, `out_of_range(field, value, section=None)`, `read_overlay()`, `write_overlay(raw)`, `value_source(section, key)`, `base_exists()`, the fields `price_timing`, `xg_per_shot`, `news_lineup_providers`, `SettingKey.options` / `.label_for`, `SettingOption`, `SettingRow.options`.

Test commands: `.venv/bin/pytest -q <file>` for one file; the whole Python suite is `.venv/bin/pytest -q -m "not golden"` for implementers (the golden-marked tests are the orchestrator's gate and take eight minutes). Frontend: `cd frontend && npx tsc --noEmit && npx vitest run`.

Commit trailers on every commit:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015EooaNubMSmbjz4E7jz2FF
```

---

### Task 1: `config.py` — the fields, the accessor, the bounds, the view, the overlay helpers

**Files:**
- Modify: `src/gaffer/config.py`
- Modify: `tests/test_v12_top_n.py`, `tests/test_v12_price_timing.py:94-135`, `tests/test_v12_xg_per_shot.py:135-165`, `tests/test_v10_config_providers.py`
- Create: `tests/test_v17e_config.py`

After this task the old names (`serving_config`, `price_timing`, `xg_per_shot`, `lineup_providers`, `optimizer_top_n`) still exist as thin wrappers over the new ones, so every unprotected test keeps passing. Five protected files go red on purpose (the pin and the four "not a field" rails); the orchestrator moves them in Task 2. Verify with the exclusion list in Step 12.

- [ ] **Step 1: Write the failing tests for the three fields and the accessor**

Create `tests/test_v17e_config.py`:

```python
"""v17e — the config in force behind one read and one invalidation
(specs/2026-09-08-v17e-config-in-force-design.md).

The four private readers are fields (§2.1), ``config_in_force()`` is the
one cached view and ``invalidate()`` the one clearing (§2.2), the bounds
and the refusal sentence are stated once (§2.3), and nothing outside
``config.py`` opens either TOML file (§1.2a)."""
from __future__ import annotations

import dataclasses

import pytest

from gaffer.config import (BOUNDS, DEFAULT_LINEUP_PROVIDERS, DEFAULT_TOP_N,
                           HIT_BAR_HI, HIT_BAR_LO, LOCAL_OVERLAY, NO_CAP,
                           Config, base_exists, config_in_force, invalidate,
                           load_config, out_of_range, read_overlay,
                           value_source, write_overlay)
from gaffer.errors import GafferError

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


def _cfg(tmp_path, body: str = "", local: str | None = None):
    (tmp_path / "config.toml").write_text(BASE + body)
    if local is not None:
        (tmp_path / LOCAL_OVERLAY).write_text(local)
    return tmp_path / "config.toml"


@pytest.fixture(autouse=True)
def _fresh():
    invalidate()
    yield
    invalidate()


# --- §2.1 the four readers as fields -------------------------------------

def test_the_three_new_fields_exist_with_the_shipped_defaults():
    cfg = Config(entry_id=1, league_id=5)
    assert cfg.price_timing is True
    assert cfg.xg_per_shot is False
    assert cfg.news_lineup_providers == list(DEFAULT_LINEUP_PROVIDERS)
    names = {f.name for f in dataclasses.fields(Config)}
    assert {"price_timing", "xg_per_shot", "news_lineup_providers"} <= names


def test_price_timing_is_read_from_the_optimizer_table(tmp_path):
    assert load_config(_cfg(tmp_path, "[optimizer]\nprice_timing = false\n")).price_timing is False


def test_xg_per_shot_is_read_from_the_model_table(tmp_path):
    assert load_config(_cfg(tmp_path, "[model]\nxg_per_shot = true\n")).xg_per_shot is True


def test_lineup_providers_are_cleaned_by_the_loader(tmp_path, capsys):
    cfg = load_config(_cfg(tmp_path, '[news]\nlineup_providers = [" FFS ", "nope"]\n'))
    assert cfg.news_lineup_providers == ["ffs"]
    assert "nope" in capsys.readouterr().out


def test_a_non_list_of_providers_falls_back_with_a_line(tmp_path, capsys):
    cfg = load_config(_cfg(tmp_path, '[news]\nlineup_providers = "ffs"\n'))
    assert cfg.news_lineup_providers == list(DEFAULT_LINEUP_PROVIDERS)
    assert "not a list" in capsys.readouterr().out


def test_an_empty_provider_list_is_the_kill_switch(tmp_path):
    assert load_config(_cfg(tmp_path, "[news]\nlineup_providers = []\n")).news_lineup_providers == []


def test_a_typo_under_optimizer_still_raises_loudly(tmp_path):
    """The pop list is gone; the splat is still a splat, so a typo is a
    ``TypeError`` and not a season of quietly wrong advice."""
    with pytest.raises(TypeError):
        load_config(_cfg(tmp_path, "[optimizer]\nhorizen = 6\n"))


def test_solver_top_n_merges_over_the_shipped_default(tmp_path):
    cfg = load_config(_cfg(tmp_path, "[optimizer]\ntop_n = {DEF = 30, XYZ = 4, MID = 0, FWD = true}\n"))
    assert cfg.solver_top_n() == {**DEFAULT_TOP_N, "DEF": 30}


def test_solver_top_n_hands_out_a_fresh_dict():
    cfg = Config(entry_id=1, league_id=5)
    cfg.solver_top_n()["GKP"] = 1
    assert cfg.solver_top_n()["GKP"] == DEFAULT_TOP_N["GKP"]


def test_solver_top_n_survives_a_table_that_is_not_a_table():
    cfg = Config(entry_id=1, league_id=5, top_n=7)  # type: ignore[arg-type]
    assert cfg.solver_top_n() == DEFAULT_TOP_N
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_v17e_config.py`
Expected: `ImportError` naming `BOUNDS` (nothing new exists yet).

- [ ] **Step 3: Add the fields, the accessor and `DEFAULT_TOP_N` to `config.py`**

In `src/gaffer/config.py`, directly after `NO_CAP`'s docstring (before `HIT_BAR_LO`), add:

```python
DEFAULT_TOP_N = {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14}
"""The candidate pool per position the solver has used since the first MILP
(v12 W1 §2.6). Here rather than in ``optimize/milp.py`` since v17e §2.1, so
that ``Config.solver_top_n`` can merge over it without ``config`` importing
the optimizer; ``milp`` imports it from here."""
```

Change the `top_n` field's `default_factory` to `lambda: dict(DEFAULT_TOP_N)`.

Add three fields. `price_timing` goes in the `[optimizer]` block of the dataclass, directly after `top_n`:

```python
    # v17e §2.1. Was a module-level reader popped out of [optimizer] before
    # the splat (v12 W2); a field now, splatted like every other key here.
    # Default on since the 2026-09-02 W2 gate: the term is a 0.008-point
    # tie-breaker and the replay with it live was byte-identical to main.
    price_timing: bool = True
```

`xg_per_shot` goes beside the other model/training fields (after `train_seasons` / `current_season`, wherever the `[data]` fields sit):

```python
    # v17e §2.1. ``[model] xg_per_shot``; read key by key because [model] is
    # not a splatted section. Default off: the 2026-09-02 §3.5 season
    # replay with the head on lost 28 points on the mean.
    xg_per_shot: bool = False
```

`news_lineup_providers` goes with the other `news_*` fields, after `news_overrides`:

```python
    # v17e §2.1 (was v10 §F2a's reader). Which predicted-XI providers may
    # speak; ``[]`` is the per-source kill switch. Cleaned by the loader
    # with ``_providers`` so a typo is dropped with a line, never raised on.
    news_lineup_providers: list[str] = field(
        default_factory=lambda: list(DEFAULT_LINEUP_PROVIDERS))
```

Add the accessor as a method on `Config` (after the fields, inside the class):

```python
    def solver_top_n(self) -> dict[str, int]:
        """``top_n`` merged over :data:`DEFAULT_TOP_N` with v12 W1's
        lenience: a position that is missing, non-integer, boolean or
        ≤ 0 keeps the shipped value; an unknown position is dropped; a
        value that is not a table at all is the default whole. A fresh dict
        per call, so a caller that mutates its pool cannot poison anyone
        else's (v17e §2.1). This is what the solver gets; ``top_n`` is
        what the file said."""
        out = dict(DEFAULT_TOP_N)
        table = self.top_n
        if not isinstance(table, dict):
            return out
        for pos in out:
            value = table.get(pos)
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            if value > 0:
                out[pos] = int(value)
        return out
```

In `load_config`, replace the `optimizer = {...}` comprehension and its comment with:

```python
    # v17e §2.1: every [optimizer] key is a field now, price_timing
    # included, so the section splats whole and a typo is still a TypeError.
    optimizer = dict(raw.get("optimizer", {}))
```

and add to the `Config(...)` call, after `news_overrides=...`:

```python
        news_lineup_providers=_providers(news.get("lineup_providers")),
        xg_per_shot=bool(raw.get("model", {}).get("xg_per_shot", False)),
```

`_providers` is defined below `load_config` today; move it above `load_config` (same body) so the name is bound at call time without relying on module order — it is, in Python, but keeping the helper above its caller is the file's convention.

Delete `NON_FIELD_OPTIMIZER_KEYS` and its docstring. In `_overlay`, change

```python
    allowed = ({f.name for f in dataclasses.fields(Config)}
               | set(NON_FIELD_OPTIMIZER_KEYS))
```

to

```python
    allowed = {f.name for f in dataclasses.fields(Config)}
```

and delete the paragraph of `SPLATTED_SECTIONS`'s docstring that begins "One exemption" (it described the pop).

Keep the four old readers for now; make them wrappers so Task 2 can run on a green tree:

```python
def price_timing(path: Path | str = "config.toml") -> bool:
    """Deleted in v17e Task 3; ``config_in_force().price_timing`` is the read."""
    try:
        return bool(load_config(path).price_timing)
    except Exception:  # noqa: BLE001
        return True


def xg_per_shot(path: Path | str = "config.toml") -> bool:
    """Deleted in v17e Task 3; ``config_in_force().xg_per_shot`` is the read."""
    try:
        return bool(load_config(path).xg_per_shot)
    except Exception:  # noqa: BLE001
        return False


def lineup_providers(path: Path | str = "config.toml") -> list[str]:
    """Deleted in v17e Task 3; the field is ``news_lineup_providers``."""
    try:
        return list(load_config(path).news_lineup_providers)
    except Exception:  # noqa: BLE001
        return list(DEFAULT_LINEUP_PROVIDERS)


def optimizer_top_n(path: Path | str = "config.toml") -> dict[str, int]:
    """Deleted in v17e Task 3; ``config_in_force().solver_top_n()`` is the read."""
    try:
        return load_config(path).solver_top_n()
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_TOP_N)


optimizer_top_n.cache_clear = lambda: None
```

Delete `_optimizer_top_n` and the two `optimizer_top_n.cache_*` assignment lines. Note the wrappers read `load_config(path)`, which requires `[fpl]` — the tests that hand a bare `[optimizer]` file to `price_timing(path)` are rewritten in Step 9.

- [ ] **Step 4: Run the field tests**

Run: `.venv/bin/pytest -q tests/test_v17e_config.py`
Expected: the first eleven pass; the file still fails to import? No — the import line names `BOUNDS`, `config_in_force` etc. which do not exist yet, so the whole file still errors. Continue to Step 5 before running again.

- [ ] **Step 5: Write the failing tests for the view, the invalidation, the bounds and the overlay helpers**

Append to `tests/test_v17e_config.py`:

```python
# --- §2.2 one read, one invalidation --------------------------------------

def test_config_in_force_reads_the_cwd_and_is_cached(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, "[optimizer]\nhorizon = 4\n")
    assert config_in_force().horizon == 4
    _cfg(tmp_path, "[optimizer]\nhorizon = 7\n")
    assert config_in_force().horizon == 4          # the trade, documented
    invalidate()
    assert config_in_force().horizon == 7


def test_config_in_force_never_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = config_in_force()
    assert (cfg.entry_id, cfg.league_id) == (0, 0)
    assert cfg.price_timing is True


def test_invalidate_drops_the_price_fall_table(monkeypatch):
    from gaffer import price_timing as pt

    seen = []
    monkeypatch.setattr(pt.owned_price_falls, "cache_clear", lambda: seen.append(1))
    invalidate()
    assert seen == [1]


def test_focus_league_reads_the_effective_id_through_the_view(tmp_path, monkeypatch):
    from gaffer.config import focus_league

    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, local="[league]\nfocus = 77\n")
    assert focus_league() == 77


# --- §2.3 bounds stated once ----------------------------------------------

def test_the_bounds_table_names_every_numeric_setting():
    assert set(BOUNDS) == {"horizon", "decay", "itb_value", "bench_curve",
                           "lambda_cap", "top_n", "max_hits", "max_transfers",
                           "hit_bar", "focus"}
    assert BOUNDS["max_hits"] == (0, NO_CAP)
    assert (HIT_BAR_LO, HIT_BAR_HI) == BOUNDS["hit_bar"] == (0.5, 0.95)


def test_out_of_range_is_one_sentence_with_the_section_and_the_bounds():
    assert out_of_range("hit_bar", 1.2, "optimizer") == (
        "[optimizer] hit_bar = 1.2 — must be a number between 0.5 and 0.95")
    assert out_of_range("max_hits", 16) == (
        "[optimizer] max_hits = 16 — must be a whole number between 0 and 15 "
        "(15 means no cap)")
    assert out_of_range("decay", 4.0, "optimizer").startswith("[optimizer] decay = 4.0")


def test_the_loader_refuses_with_the_same_sentence(tmp_path):
    with pytest.raises(GafferError, match=r"\[optimizer\] max_hits = 16 — must be a whole number between 0 and 15 \(15 means no cap\)"):
        load_config(_cfg(tmp_path, "[optimizer]\nmax_hits = 16\n"))


# --- §2.8 the overlay's file access ----------------------------------------

def test_read_overlay_is_empty_when_absent_and_names_a_bad_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert read_overlay() == ({}, None)
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer\nhorizon = 2")
    raw, err = read_overlay()
    assert raw == {}
    assert LOCAL_OVERLAY in err and "ignored" in err


def test_write_overlay_round_trips_with_the_header(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_overlay({"optimizer": {"horizon": 2}})
    text = (tmp_path / LOCAL_OVERLAY).read_text()
    assert text.startswith("# Written by the gaffer web UI")
    assert read_overlay() == ({"optimizer": {"horizon": 2}}, None)


def test_value_source_says_which_file_a_value_came_from(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, "[optimizer]\nhorizon = 4\n", local="[optimizer]\ndecay = 0.5\n")
    assert value_source("optimizer", "decay") == "local"
    assert value_source("optimizer", "horizon") == "base"
    assert value_source("optimizer", "hit_bar") == "default"


def test_value_source_ignores_a_section_that_is_not_a_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, local="optimizer = 5\n")
    assert value_source("optimizer", "horizon") == "default"


def test_base_exists_is_the_cwd_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert base_exists() is False
    _cfg(tmp_path)
    assert base_exists() is True
```

- [ ] **Step 6: Implement `BOUNDS`, `out_of_range`, the checks over them**

In `config.py`, replace the `HIT_BAR_LO, HIT_BAR_HI = 0.5, 0.95` line and its docstring with:

```python
BOUNDS: dict[str, tuple[float, float]] = {
    "horizon": (1, 8), "decay": (0.0, 1.0), "itb_value": (0.0, 1.0),
    "bench_curve": (0.0, 1.0), "lambda_cap": (0.0, 2.0), "top_n": (1, 200),
    "max_hits": (0, NO_CAP), "max_transfers": (0, NO_CAP),
    "hit_bar": (0.5, 0.95), "focus": (1, 99_999_999),
}
"""The one statement of every numeric setting's range (v17e §2.3). The
settings registry reads its ``lo``/``hi`` from here and the router
enforces all of it on a write; the loader enforces the three it always
did (the two caps and the bar). ``hit_bar``: below 0.5 a step up the
ladder would be taken on a coin toss; above 0.95 no step ever passes
(v16 §3.2). ``focus``'s ceiling is a numeric bound because the range
check needs one."""

HIT_BAR_LO, HIT_BAR_HI = BOUNDS["hit_bar"]

_SECTION = {"max_hits": "optimizer", "max_transfers": "optimizer",
            "hit_bar": "optimizer"}
"""The TOML table of the fields the loader checks, for the sentence. A
router that knows the section passes it instead."""


def out_of_range(field: str, value, section: str | None = None) -> str:
    """The one sentence for a value outside ``BOUNDS[field]`` (v17e §2.3):
    ``[optimizer] hit_bar = 1.2 — must be a number between 0.5 and 0.95``,
    with ``(15 means no cap)`` appended for the two caps. The loader raises
    it as :class:`GafferError`; the settings router returns it as the
    422's ``error``. "whole number" when both bounds are integers."""
    lo, hi = BOUNDS[field]
    section = section or _SECTION.get(field, "optimizer")
    kind = ("a whole number" if isinstance(lo, int) and isinstance(hi, int)
            else "a number")
    tail = f" ({NO_CAP} means no cap)" if field in ("max_hits", "max_transfers") else ""
    return f"[{section}] {field} = {value!r} — must be {kind} between {lo} and {hi}{tail}"
```

Rewrite the two checkers:

```python
def _check_caps(cfg: "Config") -> None:
    """v13 §2.1: both caps are whole numbers in ``0..NO_CAP``, refused by
    name. Checked here rather than in ``__post_init__`` so a ``Config`` built
    in a test with a deliberate bad value can still exist; the file is where
    a wrong number comes from."""
    for key in ("max_hits", "max_transfers"):
        value = getattr(cfg, key)
        lo, hi = BOUNDS[key]
        if (isinstance(value, bool) or not isinstance(value, int)
                or not lo <= value <= hi):
            raise GafferError(out_of_range(key, value))


def _check_hit_bar(cfg: "Config") -> None:
    """v16 §3.2: a real number inside ``BOUNDS["hit_bar"]``, refused by
    name, like the caps."""
    value = cfg.hit_bar
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not HIT_BAR_LO <= float(value) <= HIT_BAR_HI):
        raise GafferError(out_of_range("hit_bar", value))
```

- [ ] **Step 7: Implement `config_in_force`, `invalidate`, and the overlay helpers**

Replace `serving_config` with:

```python
@lru_cache(maxsize=1)
def config_in_force() -> Config:
    """The config in force: the working directory's ``config.toml`` with
    ``config.local.toml`` merged over it, cached for the life of the
    process, never raising (v17e §2.2).

    The one read for everything that is not a person at a terminal — a
    fetcher, the solver's pool, the ladder's bar, a router. Cached because a
    fetcher must not re-read a TOML file per call; degrading to the
    dataclass defaults because a clone with no ``config.toml`` still has to
    predict (the loud "copy config.example.toml" error belongs to the CLI's
    own :func:`load_config` call). :func:`invalidate` is the one clearing,
    and the two places that change or re-read the file under a running
    process — the settings router's save and the health poll — call it.
    """
    try:
        return load_config()
    except Exception:  # noqa: BLE001 — serving never blocks on config
        return Config(entry_id=0, league_id=0)


def invalidate() -> None:
    """Drop every cache keyed on the config file (v17e §2.2): the view, and
    the price-fall table that reads its switch through the view. Tests
    that write a ``config.toml`` under a running process call this; so
    does anything else that edits the file."""
    config_in_force.cache_clear()
    from gaffer.price_timing import owned_price_falls  # circular at import

    owned_price_falls.cache_clear()


def serving_config() -> Config:
    """Deleted in v17e Task 3; :func:`config_in_force` is the read."""
    return config_in_force()


serving_config.cache_clear = invalidate
```

Rewrite `focus_league` to read the view:

```python
def focus_league() -> int:
    """v15 §4.2 (plan R7): the effective focus league id, for the settings
    row's reader. ``[league] focus`` over ``fpl.league_id``, exactly as
    :func:`load_config` resolves ``Config.league_id``, read through the
    view so a cold clone reads 0 by the same path as everything else."""
    return int(config_in_force().league_id)
```

Add the overlay helpers after `LOCAL_OVERLAY` (they need `tomli_w`, `gaffer.io.atomic_write`; add `import tomli_w` beside `import tomllib` and `from gaffer.io import atomic_write` — check `gaffer.io` does not import `gaffer.config`; it does not):

```python
BASE_FILE = "config.toml"


def base_exists() -> bool:
    """Whether the working directory has a ``config.toml`` at all — the
    state a cold clone is in (v17e §2.8)."""
    return Path(BASE_FILE).exists()


def _read_toml(path: Path) -> tuple[dict, str | None]:
    """A TOML file as a dict, plus why it could not be read."""
    if not path.exists():
        return {}, None
    try:
        return tomllib.loads(path.read_text()), None
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        return {}, f"{path.name} is not readable TOML ({exc}) — ignored"


def read_overlay() -> tuple[dict, str | None]:
    """``config.local.toml`` parsed, or ``({}, why)`` when it is unreadable;
    ``({}, None)`` when absent (v17e §2.8). The settings router's read."""
    return _read_toml(Path(LOCAL_OVERLAY))


def write_overlay(raw: dict) -> None:
    """The overlay, atomically, with the header comment (v12 W5 §6.2;
    moved here in v17e §2.8 so no module but this one writes the file).
    Through ``gaffer.io.atomic_write`` rather than another copy of the
    pid-temp + ``os.replace`` idiom; ``tomli_w.dumps`` rather than ``dump``
    because the helper owns the file handle and the comment goes first."""
    body = ("# Written by the gaffer web UI (v12 W5 §6.2).\n"
            "# Merged over config.toml, key by key. Safe to hand-edit; a key\n"
            "# that is not a config field is ignored with a printed line.\n\n"
            + tomli_w.dumps(raw))
    atomic_write(Path(LOCAL_OVERLAY), body)


def _table(raw: dict, section: str) -> dict:
    """One section of a parsed file, or ``{}`` if it is not a table:
    ``optimizer = 5`` parses, and a membership test on an ``int`` was a 500
    on the tab whose job is to say the overlay is wrong."""
    value = raw.get(section)
    return value if isinstance(value, dict) else {}


def value_source(section: str, key: str) -> str:
    """Which file the in-force value of ``[section] key`` comes from:
    ``"local"`` (the overlay), ``"base"`` (``config.toml``) or
    ``"default"`` (the dataclass). Three different facts: only a local
    value can be reset (v17e §2.8)."""
    local, _ = read_overlay()
    if key in _table(local, section):
        return "local"
    base, _ = _read_toml(Path(BASE_FILE))
    if key in _table(base, section):
        return "base"
    return "default"
```

- [ ] **Step 8: Run the new file**

Run: `.venv/bin/pytest -q tests/test_v17e_config.py`
Expected: all pass.

- [ ] **Step 9: Move the reader tests onto the fields**

`tests/test_v12_top_n.py`: change the imports to `from gaffer.config import (DEFAULT_TOP_N, Config, config_in_force, invalidate, load_config)` (drop the `milp` import); replace every `optimizer_top_n(path)` with `load_config(path).solver_top_n()` and every bare `optimizer_top_n()` with `config_in_force().solver_top_n()`; `optimizer_top_n.cache_clear()` becomes `invalidate()`. In `test_no_config_at_all_gives_the_shipped_default`, the read is `config_in_force().solver_top_n()` after `monkeypatch.chdir(tmp_path)` and `invalidate()`. In `test_a_corrupt_toml_gives_the_default`, write the corrupt file as `config.toml` in `tmp_path`, `monkeypatch.chdir(tmp_path)`, `invalidate()`, and assert `config_in_force().solver_top_n() == DEFAULT_TOP_N` (the loader raises; the view degrades). `test_the_health_card_reflects_a_config_edit_because_it_clears_the_cache` keeps both halves through `config_in_force().solver_top_n()` and `invalidate()`. Update the module docstring's last paragraph: "the dataclass carries what the file says, `solver_top_n()` carries what the solver gets (v17e §2.1)."

`tests/test_v12_price_timing.py:94-135`: rewrite the two tests:

```python
def test_the_switch_is_on_by_default_and_lives_under_optimizer(tmp_path):
    """On since the 2026-09-02 W2 gate met the pre-registered §3.4 flip rule.
    Under [optimizer] and not [solver]: program ruling. A field since v17e
    §2.1; an unreadable file degrades through ``config_in_force`` to the
    shipped default, because a solve must not die of a config file."""
    from gaffer.config import config_in_force, invalidate, load_config

    base = "[fpl]\nentry_id = 1\nleague_id = 2\n"
    on = tmp_path / "on.toml"
    on.write_text(base + "[optimizer]\nprice_timing = true\n")
    off = tmp_path / "off.toml"
    off.write_text(base + "[optimizer]\nprice_timing = false\n")
    unset = tmp_path / "unset.toml"
    unset.write_text(base + "[optimizer]\nhorizon = 3\n")
    stale = tmp_path / "stale.toml"
    stale.write_text(base + "[solver]\nprice_timing = false\n")
    assert load_config(on).price_timing is True
    assert load_config(off).price_timing is False
    assert load_config(unset).price_timing is True
    assert load_config(stale).price_timing is True
    invalidate()
    assert config_in_force().price_timing is True   # no config.toml here at all
    invalidate()


def test_the_flag_reaches_the_config_constructor(tmp_path):
    """v12 W2 popped it out of [optimizer] to keep the field count still;
    v17e §2.1 made it a field, so the splat carries it like horizon."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n\n"
                    "[optimizer]\nhorizon = 3\nprice_timing = false\n")
    cfg = load_config(path)
    assert (cfg.horizon, cfg.price_timing) == (3, False)
```

Keep `test_w1s_top_n_still_travels_through_the_splat` and `test_a_typo_under_optimizer_still_raises_loudly` as they are (they still hold). Leave lines 174+ alone for now (Task 3 renames `price_timing_enabled`).

`tests/test_v12_xg_per_shot.py:135-165`: in `test_the_attacking_model_is_told_only_when_the_flag_is_on` replace the two `xg_per_shot(...)` asserts with `load_config(off).xg_per_shot is False` / `load_config(on).xg_per_shot is True` after prefixing both files with `[fpl]\nentry_id = 1\nleague_id = 2\n`; keep the two `monkeypatch.setattr(tr, "xg_per_shot", ...)` lines for now (Task 3 changes them). Rewrite the last test:

```python
def test_the_flag_defaults_off_and_survives_a_missing_file(tmp_path, monkeypatch):
    """Back off on 2026-09-02 (see the field's comment). The default is the
    shipped behaviour and an unreadable file must fall back to it rather
    than to a head nobody chose — through the view, since v17e §2.1."""
    from gaffer.config import config_in_force, invalidate

    monkeypatch.chdir(tmp_path)
    invalidate()
    assert config_in_force().xg_per_shot is False
    (tmp_path / "config.toml").write_text("[model\nxg_per_shot = true")
    invalidate()
    assert config_in_force().xg_per_shot is False
    invalidate()
```

`tests/test_v10_config_providers.py`: rewrite the module docstring's second paragraph to say the deviation was retired by v17e §2.1 (the field is `news_lineup_providers`; the reasons A6 gave are unchanged). Import `load_config, config_in_force, invalidate` instead of `lineup_providers`. Every `lineup_providers(path)` becomes `load_config(path).news_lineup_providers` with `[fpl]` prepended to the written body; a bare `lineup_providers()` becomes `config_in_force().news_lineup_providers` under `monkeypatch.chdir(tmp_path)` with `invalidate()` before and after. `test_the_config_dataclass_did_not_grow` becomes:

```python
def test_the_switch_is_a_field_since_v17e():
    """A6's 49th field, refused in v10 on a protected count and granted in
    v17e §2.1 on the merits: one read interface, no private TOML readers."""
    assert any(f.name == "news_lineup_providers"
               for f in dataclasses.fields(Config))
```

`test_the_two_switches_compose` reads `load_config(path).news_lineup_providers == ["ffs"]` after prepending `[fpl]`. `_providers` tests are unchanged.

- [ ] **Step 10: Run the four moved files**

Run: `.venv/bin/pytest -q tests/test_v12_top_n.py tests/test_v12_price_timing.py tests/test_v12_xg_per_shot.py tests/test_v10_config_providers.py tests/test_v17e_config.py`
Expected: all pass.

- [ ] **Step 11: Point `milp.py`'s import at nothing new yet**

`optimize/milp.py:136` still defines its own `DEFAULT_TOP_N`; leave it — the orchestrator replaces it in Task 2. Both dicts are equal, and `test_the_shipped_default_is_what_it_always_was` in `test_v12_top_n.py` now imports from `gaffer.config`.

- [ ] **Step 12: Run the suite, minus the golden and the five files the orchestrator owns**

Run: `.venv/bin/pytest -q -m "not golden" --deselect tests/test_v13_degradation.py::test_the_config_gained_exactly_two_fields --deselect tests/test_v10_degradation.py::test_the_config_dataclass_did_not_grow --deselect tests/test_v12_w2_degradation.py::test_w2_adds_no_config_field --deselect tests/test_v12_w5_degradation.py::test_w5_added_no_config_field --deselect tests/test_v12_w5_settings.py::test_the_readers_are_price_timing_and_the_focus`
Expected: green. (If `test_w5_added_no_config_field` is named differently, find it with `grep -n "def test_w5_added" tests/test_v12_w5_degradation.py` and deselect that name.) Report any other failure to the orchestrator rather than editing a rail.

- [ ] **Step 13: Commit**

```bash
git add src/gaffer/config.py tests/test_v17e_config.py tests/test_v12_top_n.py tests/test_v12_price_timing.py tests/test_v12_xg_per_shot.py tests/test_v10_config_providers.py
git commit -m "feat(v17e): the four private readers become Config fields; config_in_force, invalidate, BOUNDS, out_of_range and the overlay helpers in config.py (old names kept as wrappers until Task 3)"
```

---

### Task 2 (orchestrator only): the pin, the rails, the solver's one read

**Files:**
- Modify: `tests/test_v13_degradation.py:21-35, 207-216`
- Modify: `tests/test_v10_degradation.py:33, 407-437`
- Modify: `tests/test_v12_w2_degradation.py:186-197`
- Modify: `tests/test_v12_w5_degradation.py:21, 33-52, 129-155`
- Modify: `tests/test_v12_w5_settings.py:58-75`
- Modify: `tests/test_v8e_degradation.py:17, 39-48`
- Modify: `tests/test_web_job_kinds_v8f.py:94-101`
- Modify: `src/gaffer/optimize/milp.py:136, 985-993`

- [ ] **Step 1: The pin, its own commit**

`tests/test_v13_degradation.py::test_the_config_gained_exactly_two_fields`: append to the docstring "62 after v17e (specs/2026-09-08-v17e-config-in-force-design.md §2.1): the three names are `price_timing`, `xg_per_shot` and `news_lineup_providers`, the private readers become fields." and change the asserts to:

```python
    assert len(names) == 62
    assert {"max_hits", "max_transfers"} <= names
    assert "stance" in names
    assert "hit_bar" in names
    assert {"price_timing", "xg_per_shot", "news_lineup_providers"} <= names
```

Commit: `test(v17e): Config pin 59 -> 62 — price_timing, xg_per_shot, news_lineup_providers are fields (spec §2.1, §7)`.

- [ ] **Step 2: The four rails, the renames, the solver read**

`test_v10_degradation.py`: import `Config, DEFAULT_LINEUP_PROVIDERS, config_in_force, invalidate`; the test becomes a presence pin — docstring gains "v17e §2.1 took the question up on the merits: the switch is the field `news_lineup_providers`, the reader is gone." and the body:

```python
    assert any(f.name == "news_lineup_providers" for f in dataclasses.fields(Config))
    monkeypatch.chdir(tmp_path)
    invalidate()
    assert config_in_force().news_lineup_providers == list(DEFAULT_LINEUP_PROVIDERS)
    invalidate()
```

`test_v12_w2_degradation.py::test_w2_adds_no_config_field`: docstring gains "v17e §2.1 made both fields; the claim now is that they are present with W2's defaults." and:

```python
    assert "price_timing" in names and Config(entry_id=1, league_id=2).price_timing is True
    assert "xg_per_shot" in names and Config(entry_id=1, league_id=2).xg_per_shot is False
    assert "top_n" in names
```

`test_v12_w5_degradation.py`: the `serving_config` import and four `cache_clear()` lines become `invalidate` / `invalidate()`; in the no-field test drop the `"price_timing" in n or` clause and add to the docstring "v17e §2.1 made `price_timing` a field; the absence claim keeps every other name."

`test_v12_w5_settings.py::test_the_readers_are_price_timing_and_the_focus` becomes `test_the_one_reader_is_the_focus`: `assert [e.field for e in readers] == ["focus"]`, `assert "price_timing" in fields` with the docstring "v17e §2.1 did what this test's message asked: `price_timing` is a field and its reader is gone."

`test_v8e_degradation.py`, `test_web_job_kinds_v8f.py`, `test_v13_degradation.py:207-216`: `serving_config` → `invalidate`, every `.cache_clear()` → `invalidate()`, drop the `optimizer_top_n` import.

`optimize/milp.py`: line 136 becomes `from gaffer.config import DEFAULT_TOP_N` placed with the imports (keep the name exported from `milp` so nothing else moves); lines 985-993's comment ends "…`config_in_force().solver_top_n()` falls back to `DEFAULT_TOP_N` on anything unreadable (v17e §2.1)." and the two lines become:

```python
        from gaffer.config import config_in_force

        top_n = config_in_force().solver_top_n()
```

Run: `.venv/bin/pytest -q -m "not golden"` — green. Commit: `test(v17e): the v10, v12 W2, v12 W5 rails read the fields; cache clears become invalidate(); build_pool reads solver_top_n() (spec §7 rulings)`.

---

### Task 3: every site reads `config_in_force()`; the old names go

**Files:**
- Modify: `src/gaffer/config.py` (delete the wrappers)
- Modify: `src/gaffer/price_timing.py:64, 168`, `src/gaffer/models/train.py:16, 580`, `src/gaffer/data/news/lineups.py:27, 488-493`, `src/gaffer/artifacts.py:225-229, 498-500`, `src/gaffer/brief.py:399-400`, `src/gaffer/cli.py:425-428`, `src/gaffer/ladder.py:414-415, 720-726, 758-759`, `src/gaffer/snapshot.py:74-76`, `src/gaffer/sensitivity.py:190-198`, `src/gaffer/models/availability.py:112-150`, `src/gaffer/web/job_kinds.py:189-194`, `src/gaffer/web/routers/brief.py:34-36`, `src/gaffer/web/routers/players.py:18, 292`, `src/gaffer/data/news/premierinjuries.py:24, 301`, `src/gaffer/web/routers/overrides.py:155-165`, `src/gaffer/web/routers/settings.py:27-28, 259-261`, `src/gaffer/web/routers/meta.py:27, 300-318`, `scripts/v12_w3_support.py:107-109`
- Modify: `tests/golden_client.py:146-205, 351-365`, `tests/test_golden_board.py:280-286`
- Modify: the unprotected tests that name an old symbol: `tests/test_config_v8a.py`, `tests/test_ladder.py`, `tests/test_sensitivity.py`, `tests/test_v12_price_timing.py:174-360`, `tests/test_v12_xg_per_shot.py:146-149`, `tests/test_v12_w5_projections.py`, `tests/test_v15_settings.py`, `tests/test_v16_ladder.py`, `tests/test_v12_w5_settings.py`, `tests/test_v16_config.py`, `tests/test_v12_w5_config_overlay.py`, `tests/test_web_ladder.py`, `tests/test_web_league_overview.py`, `tests/test_web_league.py`, `tests/test_web_overrides.py`

- [ ] **Step 1: Write the failing test that the old names are gone**

Append to `tests/test_v17e_config.py`:

```python
# --- §0 the deletion test ---------------------------------------------------

def test_the_old_readers_and_serving_config_are_gone():
    import gaffer.config as mod

    for name in ("serving_config", "price_timing", "xg_per_shot",
                 "lineup_providers", "optimizer_top_n",
                 "NON_FIELD_OPTIMIZER_KEYS", "_optimizer_top_n"):
        assert not hasattr(mod, name), name
```

Run: `.venv/bin/pytest -q tests/test_v17e_config.py::test_the_old_readers_and_serving_config_are_gone` — fails on `serving_config`.

- [ ] **Step 2: The `src/` sites**

Mechanical, per file. Every `from gaffer.config import serving_config` becomes `from gaffer.config import config_in_force` and every `serving_config()` becomes `config_in_force()`. Then the four readers:

`price_timing.py:64`: `from gaffer.config import config_in_force`; line 168: `if not config_in_force().price_timing:`. Update the `owned_price_falls` docstring's last paragraph: "The switch is read through `config_in_force()`, so a flipped flag reaches the next solve after `invalidate()` — which the settings save and the health poll call."

`models/train.py:16`: `from gaffer.config import config_in_force`; line 580: `if config_in_force().xg_per_shot else [])`.

`data/news/lineups.py:27`: `from gaffer.config import config_in_force`; line 492: `names = list(cfg.news_lineup_providers) if providers is None else [`.

`ladder.py:720`: `from gaffer.config import NO_CAP, config_in_force`, line 726 `cfg = config_in_force()`; lines 414-415 and 758-759 likewise.

`web/routers/settings.py`: the import becomes `from gaffer.config import LOCAL_OVERLAY, invalidate, load_config` (drop `optimizer_top_n`, `serving_config`; `owned_price_falls` import goes too) and lines 253-261 become:

```python
    # v17e §2.2: every cache keyed on the file, dropped in one call.
    invalidate()
    return _panel()
```

Update `test_v12_w5_settings.py`'s three "clears" tests: `test_the_write_clears_the_serving_config_cache` reads `config_in_force().horizon`; `test_the_write_clears_the_solver_pool_cache` reads `config_in_force().solver_top_n()["GKP"]`; `test_the_write_clears_the_price_fall_cache` patches `gaffer.price_timing.owned_price_falls.cache_clear` (not `mod.owned_price_falls`).

`web/routers/meta.py:27`: `from gaffer.config import Config, config_in_force, invalidate, load_config`; drop the `owned_price_falls` import (line 28) if nothing else in the file uses it (`grep -n owned_price_falls src/gaffer/web/routers/meta.py`); lines 300-318's comment keeps its first two paragraphs, and the code becomes:

```python
        invalidate()
        solver_top_n = config_in_force().solver_top_n()
```

`scripts/v12_w3_support.py:107-109`: `config_in_force`.

- [ ] **Step 3: Delete the wrappers**

In `config.py` delete `serving_config`, the `serving_config.cache_clear = invalidate` line, `price_timing`, `xg_per_shot`, `lineup_providers`, `optimizer_top_n` and the `optimizer_top_n.cache_clear = lambda: None` line. Rewrite `_raw_with_overlay`'s docstring: "`config.toml` parsed, with `config.local.toml` merged over it. The one place the merge happens, and since v17e §2.1 `load_config` is its only caller: the keys that used to need their own readers are fields. Raises whatever reading or parsing `path` raises — `load_config` phrases the missing-file error and `config_in_force` degrades." Rewrite `_overlay`'s docstring paragraph that says "the readers below do not either: `price_timing` and `lineup_providers` reach for `raw.get(section, {})…`" to: "The rule does not ask whether the base declares the section, because `load_config` does `raw.get(section, {})` per table and a scalar there would raise `AttributeError` on the solve path — the one place that must not." Check `grep -n "serving_config\|optimizer_top_n\|price_timing()\|xg_per_shot()\|lineup_providers()\|NON_FIELD" src/gaffer/config.py` prints only the field names and docstring history lines you have read and judged accurate.

- [ ] **Step 4: The golden client and the header comparison**

`tests/golden_client.py`: `golden_cwd` imports `invalidate` and calls `invalidate()` where it called `serving_config.cache_clear()` (both places); its docstring says "The serving cache is cleared" — keep, it still is. `_TOML_LAYOUT`: append `"price_timing"` to the `"optimizer"` list (last, so the written file's line lands where the special case put it), add `"model": [("xg_per_shot", "xg_per_shot")]` after `"data"`, and append `("lineup_providers", "news_lineup_providers")` to `"news"`. Delete the `if section == "optimizer": … lines.append("price_timing = true")` block and its comment. `write_golden_toml`'s docstring stays true.

`tests/test_golden_board.py:280-286`:

```python
def test_the_header_config_is_golden_config():
    """On the keys the header recorded: a field added after the recording
    (v17e §2.7 added three) is not in the header, and the fixture is never
    rewritten by a refactor. The added fields must hold what the recorded
    config.toml implies — price_timing = true is written, the other two are
    absent and so default."""
    header = _header()
    if header is None:
        pytest.skip("golden board not recorded yet")
    golden = asdict(gc.golden_config())
    assert {k: v for k, v in golden.items() if k in header["config"]} == header["config"]
    added = {k: v for k, v in golden.items() if k not in header["config"]}
    assert added == {"price_timing": True, "xg_per_shot": False,
                     "news_lineup_providers": ["ffs", "rotowire"]}
    assert header["config"]["odds_api_key"] == ""
```

Run: `.venv/bin/pytest -q tests/test_golden_board.py -m "not golden"` — the non-golden tests there pass (the round-trip, the written-toml tests).

- [ ] **Step 5: The unprotected tests**

For each file in the list above: `serving_config.cache_clear()` and `optimizer_top_n.cache_clear()` → `invalidate()`; `serving_config()` → `config_in_force()`; imports likewise. `test_v12_price_timing.py:174-360`: `monkeypatch.setattr(price_timing, "price_timing_enabled", lambda: False)` becomes a patched view — add a helper at the top of the file:

```python
def _switch(monkeypatch, on: bool):
    """The price-timing switch as the solve path reads it (v17e §2.2)."""
    from gaffer.config import Config

    monkeypatch.setattr("gaffer.price_timing.config_in_force",
                        lambda: Config(entry_id=1, league_id=2, price_timing=on))
```

and use `_switch(monkeypatch, False)` / `_switch(monkeypatch, True)` where the old setattr lines were. `test_v12_xg_per_shot.py:146-149`: patch `tr.config_in_force` with a lambda returning `Config(entry_id=1, league_id=2, xg_per_shot=False)` / `True`. `test_v16_config.py`: imports `config_in_force, invalidate`; the `settings_client` fixture calls `invalidate()`.

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/pytest -q -m "not golden"` — green. `grep -rn "serving_config\|optimizer_top_n\|price_timing_enabled\|NON_FIELD_OPTIMIZER_KEYS" src scripts tests --include='*.py' | grep -v "^tests/test_v17e_config.py"` — prints only docstring history (a line quoting the old name in a past-tense sentence). If a code line remains, fix it.

- [ ] **Step 7: Commit**

```bash
git add src/gaffer scripts/v12_w3_support.py tests
git commit -m "refactor(v17e): every serve-time read is config_in_force(); the four readers, serving_config and NON_FIELD_OPTIMIZER_KEYS deleted; the golden header compared on its recorded keys"
```

(`git add tests` stages only tracked and new test files; confirm with `git status --short` that nothing under `data/`, `reports/`, `models/` is listed.)

---

### Task 4: the registry — bounds from `BOUNDS`, `options`, one refusal sentence, no file access in the router

**Files:**
- Modify: `src/gaffer/web/settings_keys.py`
- Modify: `src/gaffer/web/routers/settings.py`
- Modify: `src/gaffer/web/schemas.py:2316-2337`
- Regenerate: `frontend/src/schemas.json`, `frontend/src/types.generated.ts`
- Modify: `tests/test_v17e_config.py`, `tests/test_v12_w5_settings.py`, `tests/test_v16_config.py:64-82`, `tests/test_v13_degradation.py` is orchestrator-only (its bounds test still passes: `(0, 15)`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_v17e_config.py`:

```python
# --- §2.3–§2.5 the registry -------------------------------------------------

SETTINGS_BASE = "[fpl]\nentry_id = 111\nleague_id = 222\n[optimizer]\nhorizon = 3\n"


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(SETTINGS_BASE)
    invalidate()
    yield TestClient(create_app())
    invalidate()


def test_every_whitelist_bound_is_the_config_bound():
    from gaffer.web.settings_keys import WHITELIST

    for entry in WHITELIST:
        if entry.field in BOUNDS:
            assert (entry.lo, entry.hi) == BOUNDS[entry.field], entry.field
        else:
            assert (entry.lo, entry.hi) == (None, None), entry.field


def test_every_whitelist_entry_reads_and_writes_through_the_one_interface(settings_client):
    """Written through the endpoint, read back changed through
    config_in_force() with no cache_clear in this test: the save's
    invalidate() is the only clearing there is."""
    from gaffer.web.settings_keys import WHITELIST, current_value

    samples = {"int": 2, "float": 0.3, "bool": False, "floats3": [0.5, 0.4, 0.3],
               "pool": {"GKP": 2, "DEF": 3, "MID": 4, "FWD": 5}, "choice": "chase"}
    samples_by_field = {"hit_bar": 0.7, "focus": 222, "max_hits": 1,
                        "max_transfers": 1, "horizon": 2}
    for entry in WHITELIST:
        value = samples_by_field.get(entry.field, samples[entry.kind])
        before = current_value(entry, config_in_force())
        resp = settings_client.post("/api/settings", json={"key": entry.field, "value": value})
        assert resp.status_code == 200, (entry.field, resp.text)
        after = current_value(entry, config_in_force())
        assert after == value, entry.field
        assert after != before or entry.field == "focus", entry.field


def test_the_three_select_rows_carry_labelled_options(settings_client):
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    assert rows["max_hits"]["options"][-1] == {"value": 15, "label": "no cap"}
    assert rows["max_transfers"]["options"][0] == {"value": 0, "label": "bank"}
    assert [o["label"] for o in rows["hit_bar"]["options"]][:3] == ["50%", "55%", "60%"]
    assert rows["horizon"]["options"] == []


def test_a_saved_value_the_select_does_not_offer_is_inserted_in_order(settings_client, tmp_path):
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer]\nmax_hits = 5\nhit_bar = 0.62\n")
    invalidate()
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    hits = [o["value"] for o in rows["max_hits"]["options"]]
    assert hits == [0, 1, 2, 3, 5, 15]
    bar = rows["hit_bar"]["options"]
    assert {"value": 0.62, "label": "62%"} in bar
    assert [o["value"] for o in bar] == sorted(o["value"] for o in bar)


def test_the_router_refuses_with_the_config_sentence(settings_client):
    resp = settings_client.post("/api/settings", json={"key": "hit_bar", "value": 0.99})
    assert resp.status_code == 422
    assert resp.json()["detail"] == {
        "constraint": "out_of_range",
        "error": out_of_range("hit_bar", 0.99, "optimizer"), "players": []}
    resp = settings_client.post("/api/settings", json={"key": "max_hits", "value": 16})
    assert resp.json()["detail"]["error"] == out_of_range("max_hits", 16, "optimizer")


def test_the_settings_router_imports_no_toml_library():
    import gaffer.web.routers.settings as mod

    assert not hasattr(mod, "tomllib") and not hasattr(mod, "tomli_w")
```

Run: `.venv/bin/pytest -q tests/test_v17e_config.py -k "whitelist or select or inserted or config_sentence or toml_library"` — fails (no `options`, bounds are literals, `tomllib` imported).

- [ ] **Step 2: `settings_keys.py`**

Replace the dataclass:

```python
@dataclass(frozen=True)
class SettingKey:
    field: str
    section: str
    toml_key: str
    label: str
    kind: str
    """``int`` | ``float`` | ``bool`` | ``floats3`` | ``pool`` | ``choice``."""
    help: str
    source: str = "config"
    reader: str = ""
    choices: tuple[str, ...] = ()
    options: tuple[tuple[int | float, str], ...] = ()
    """The values a select offers, with the word for each (v17e §2.4);
    empty for a row that is typed rather than picked. The served row also
    carries the saved value when it is not one of these (§2.5)."""
    label_for: Callable[[int | float], str] = str
    """The word for a value that is not in ``options`` (§2.5)."""

    @property
    def lo(self) -> float | None:
        """From :data:`gaffer.config.BOUNDS`, the one statement (v17e §2.3)."""
        bounds = BOUNDS.get(self.field)
        return None if bounds is None else bounds[0]

    @property
    def hi(self) -> float | None:
        bounds = BOUNDS.get(self.field)
        return None if bounds is None else bounds[1]
```

(keep each field's existing docstring; add `from typing import Callable` and `from gaffer.config import BOUNDS, NO_CAP, Config`.) Every `WHITELIST` entry drops its two bound literals (the positional `lo, hi` after `kind`). Set on the three:

```python
    SettingKey("max_hits", "optimizer", "max_hits", "Max hits per week",
               "int",
               "15 = no cap. ...(unchanged help)...",
               options=((0, "0"), (1, "1"), (2, "2"), (3, "3"), (NO_CAP, "no cap"))),
    SettingKey("max_transfers", "optimizer", "max_transfers",
               "Max transfers per week", "int",
               "...(unchanged help)...",
               options=((0, "bank"), (1, "1"), (2, "2"), (3, "3"), (4, "4"),
                        (5, "5"), (NO_CAP, "no cap"))),
    SettingKey("hit_bar", "optimizer", "hit_bar", "Hit bar", "float",
               "...(unchanged help)...",
               options=tuple((b, f"{round(b * 100)}%") for b in
                             (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.9, 0.95)),
               label_for=lambda v: f"{round(v * 100)}%"),
```

`price_timing`'s entry drops `source="reader", reader="gaffer.config:price_timing"` and its comment becomes "A field since v17e §2.1." Update the module docstring's paragraph beginning "And one entry is not a `Config` field at all" to describe `focus` as the one reader entry and say `price_timing` became a field in v17e. `current_value` is unchanged.

- [ ] **Step 3: `schemas.py`**

Before `SettingRow`:

```python
class SettingOption(BaseModel):
    """One value a select offers and the word for it (v17e §2.4)."""

    value: float | int
    label: str
```

In `SettingRow` after `choices`:

```python
    options: list[SettingOption] = Field(default_factory=list)
    """What a select offers, in order, the saved value included when it is
    not offered (v17e §2.5). Empty for a row the tab types into."""
```

Then `cd frontend && npm run types` and check `git status --short frontend/src` lists `schemas.json` and `types.generated.ts`.

- [ ] **Step 4: `routers/settings.py`**

Imports become:

```python
import math

from fastapi import APIRouter, HTTPException

from gaffer.config import (base_exists, invalidate, load_config, out_of_range,
                           read_overlay, value_source, write_overlay)
from gaffer.web.schemas import (SettingOption, SettingRow, SettingsPanel,
                                SettingWrite)
from gaffer.web.settings_keys import (BY_FIELD, WHITELIST, current_value,
                                      live_keys)
```

Delete `BASE`, `_read`, `_table`, `_write`. `_panel` becomes:

```python
def _options(entry, value) -> list[SettingOption]:
    """The entry's options with the saved value inserted in order when it
    is not offered (v17e §2.5): a hand-edited ``max_hits = 5`` must not
    render a blank select."""
    if not entry.options:
        return []
    offered = [SettingOption(value=v, label=w) for v, w in entry.options]
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_number and value not in {v for v, _ in entry.options}:
        offered.append(SettingOption(value=value, label=entry.label_for(value)))
        offered.sort(key=lambda o: o.value)
    return offered


def _panel() -> SettingsPanel:
    if not base_exists():
        return SettingsPanel(
            rows=[], unavailable=[e.field for e in WHITELIST],
            overlay_error=("no config.toml — copy config.example.toml to "
                           "config.toml and set fpl.entry_id and "
                           "fpl.league_id"),
            apply_note=APPLY_NOTE)
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001 — the tab must still render
        return SettingsPanel(rows=[], unavailable=[e.field for e in WHITELIST],
                             overlay_error=f"config.toml unreadable ({exc})",
                             apply_note=APPLY_NOTE)
    _, local_err = read_overlay()
    live = set(live_keys(cfg))
    rows = []
    for entry in WHITELIST:
        if entry.field not in live:
            continue
        value = current_value(entry, cfg)
        rows.append(SettingRow(
            key=entry.field, label=entry.label, kind=entry.kind,
            value=value, lo=entry.lo, hi=entry.hi,
            choices=list(entry.choices), options=_options(entry, value),
            section=entry.section, help=entry.help,
            source=value_source(entry.section, entry.toml_key)))
    return SettingsPanel(
        rows=rows,
        unavailable=[e.field for e in WHITELIST if e.field not in live],
        overlay_error=local_err, apply_note=APPLY_NOTE)
```

The literal `"config.toml"` inside the two sentences is fine for the grep rail (Task 6): it tests equality with the bare filename, and these are longer strings. In `_checked`, the three range refusals become `raise _fail("out_of_range", out_of_range(entry.field, v, entry.section))` (for `floats3` and `pool` pass the offending element `v`; for the scalar branch pass `number`). `save` reads `raw, err = read_overlay()` and writes `write_overlay(raw)`. The module docstring's first paragraph now says the overlay is read and written through `config.read_overlay` / `config.write_overlay` and that no other module opens either file (v17e §2.8).

- [ ] **Step 5: Existing tests**

`tests/test_v12_w5_settings.py`: `test_a_value_out_of_bounds_is_refused_and_writes_nothing` still passes (`"0" in error`). `test_the_bench_curve_needs_exactly_three_weights` and `test_the_pool_is_a_whole_number_for_each_position` assert the `wrong_type` constraint, unchanged. If a test asserts the old range wording ("is between"), grep: `grep -n "is between\|between 0 and\|each of" tests/test_v12_w5_settings.py tests/test_v15_settings.py tests/test_v16_config.py` and update it to the new sentence via `out_of_range`. `SettingsTab.test.tsx`'s fixture rows gain `options: []` in Task 5; the Python side needs nothing else.

- [ ] **Step 6: Run**

Run: `.venv/bin/pytest -q -m "not golden"` and `cd frontend && npx tsc --noEmit` — green (the frontend type-checks because `options` is additive).

- [ ] **Step 7: Commit**

```bash
git add src/gaffer/web/settings_keys.py src/gaffer/web/routers/settings.py src/gaffer/web/schemas.py frontend/src/schemas.json frontend/src/types.generated.ts tests/test_v17e_config.py tests/test_v12_w5_settings.py tests/test_v15_settings.py tests/test_v16_config.py
git commit -m "feat(v17e): SettingKey bounds from BOUNDS, options with the saved value inserted, one refusal sentence; the settings router reads and writes the overlay through config.py"
```

---

### Task 5: the ladder card renders the settings rows

**Files:**
- Modify: `frontend/src/hubs/this-week/LadderCard.tsx`
- Modify: `frontend/src/hubs/this-week/LadderCard.test.tsx`
- Modify: `frontend/src/hubs/ThisWeek.test.tsx:110-135`
- Modify: `frontend/src/hubs/model/SettingsTab.test.tsx:28-40`
- Modify: `frontend/scripts/shots.sh`

- [ ] **Step 1: Write the failing tests**

In `LadderCard.test.tsx`, add a panel fixture after `PAYLOAD` and serve it from the mock:

```ts
import type { LadderPayload, SettingsPanel } from '../../types'

const ROWS: SettingsPanel = {
  rows: [
    { key: 'max_hits', label: 'Max hits per week', kind: 'int', value: 2,
      lo: 0, hi: 15, choices: [], section: 'optimizer', help: '', source: 'default',
      options: [{ value: 0, label: '0' }, { value: 1, label: '1' },
                { value: 2, label: '2' }, { value: 3, label: '3' },
                { value: 15, label: 'no cap' }] },
    { key: 'max_transfers', label: 'Max transfers per week', kind: 'int',
      value: 15, lo: 0, hi: 15, choices: [], section: 'optimizer', help: '',
      source: 'default',
      options: [{ value: 0, label: 'bank' }, { value: 1, label: '1' },
                { value: 15, label: 'no cap' }] },
    { key: 'hit_bar', label: 'Hit bar', kind: 'float', value: 0.6,
      lo: 0.5, hi: 0.95, choices: [], section: 'optimizer', help: '',
      source: 'default',
      // 0.62 is a value the card could not know: the server inserted it.
      options: [{ value: 0.6, label: '60%' }, { value: 0.62, label: '62%' },
                { value: 0.7, label: '70%' }] },
  ],
  unavailable: [], overlay_error: null, apply_note: 'note',
}
```

and in `beforeEach`'s mock: `if (path === '/api/settings') return ROWS`. Every later `apiGet.mockImplementation` in the file that answers only `/api/ladder` gains the same line. Change every `getByLabelText('Max hits')` to `'Max hits per week'`, `'Max transfers'` to `'Max transfers per week'` (the row's label is the select's label now). Replace `keeps a cap the select does not offer as an option of its own` with:

```ts
  it('renders the three selects from the settings rows the server sends', async () => {
    mount()
    const hits = await screen.findByLabelText('Max hits per week')
    expect(within(hits).getByRole('option', { name: 'no cap' })).toHaveValue('15')
    const moves = screen.getByLabelText('Max transfers per week')
    expect(within(moves).getByRole('option', { name: 'bank' })).toHaveValue('0')
    const bar = screen.getByLabelText('Hit bar')
    expect((bar as HTMLSelectElement).value).toBe('0.6')
    expect(within(bar).getByRole('option', { name: '62%' })).toHaveValue('0.62')
  })

  it('shows no selects until the settings rows arrive, and says so when they never do', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/ladder') return PAYLOAD
      throw new Error('settings down')
    })
    mount()
    await screen.findByText('1 hit')
    expect(screen.queryByLabelText('Hit bar')).toBeNull()
    expect(await screen.findByText(/settings down/)).toBeInTheDocument()
  })
```

Add to the "saves a changed cap" test an assertion that `/api/settings` was fetched again after the rebuild: `await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/settings'))` after the ladder reload, counting two calls: `expect(apiGet.mock.calls.filter(([p]) => p === '/api/settings').length).toBeGreaterThanOrEqual(2)`.

`ThisWeek.test.tsx` route: add `if (path === '/api/settings') return Promise.resolve({ rows: [], unavailable: [], overlay_error: null, apply_note: '' })` before the final reject.

`SettingsTab.test.tsx`: each fixture row gains `options: []`.

Run: `cd frontend && npx vitest run src/hubs/this-week/LadderCard.test.tsx` — fails (labels, options).

- [ ] **Step 2: Rewrite the card's controls**

In `LadderCard.tsx`: delete `NO_CAP`, `HIT_BARS`, `withCurrent` and their comments. Import `SettingRow, SettingsPanel` from `'../../types'`. Add state and a fetch:

```tsx
const SETTING_KEYS = ['max_hits', 'max_transfers', 'hit_bar'] as const
type SettingKeyName = typeof SETTING_KEYS[number]

/** One select over a settings row: the options, the words and the saved
 *  value are the server's (v17e §2.6); the card adds no value of its own. */
function SettingSelect({ row, disabled, onChange }: {
  row: SettingRow
  disabled: boolean
  onChange: (value: number) => void
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="label">{row.label}</span>
      <select
        aria-label={row.label}
        value={String(row.value)}
        disabled={disabled}
        className={INPUT_CLASS}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {row.options.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>{o.label}</option>
        ))}
      </select>
    </label>
  )
}
```

Inside `LadderCard`: `const [rows, setRows] = useState<SettingRow[] | null>(null)`; a `loadRows` callback:

```tsx
  const loadRows = useCallback(() => {
    apiGet<SettingsPanel>('/api/settings')
      .then((panel) => setRows(panel.rows.filter(
        (r) => (SETTING_KEYS as readonly string[]).includes(r.key))))
      .catch((e) => { setFailed(errorText(e)); setRows(null) })
  }, [])
  useEffect(() => { loadRows() }, [loadRows])
```

and in the `job.status === 'done'` effect call `loadRows()` beside `load()`. `setSetting`'s key type becomes `SettingKeyName`. Delete `hitsValue` and `movesValue`. The three `<label>` blocks become:

```tsx
      <div className="mb-3 flex flex-wrap gap-3">
        {(rows ?? []).map((row) => (
          <SettingSelect
            key={row.key}
            row={row}
            disabled={busy || !data?.gw}
            onChange={(value) => setSetting(row.key as SettingKeyName, value)}
          />
        ))}
      </div>
```

Keep `capText` exported and unchanged. Check `grep -n "HIT_BARS\|NO_CAP\|?? 0.6\|withCurrent" frontend/src/hubs/this-week/LadderCard.tsx` prints nothing, and `grep -rn "withCurrent\|HIT_BARS" frontend/src` prints nothing (the test file's imports of them go too).

- [ ] **Step 3: `shots.sh`**

After the v17b block:

```bash
# v17e gate (specs/2026-09-08-v17e-config-in-force-design.md §1.4): This
# Week tall enough to reach the ladder card's selects, and Settings.
if [[ "$STAGE" == v17e* ]]; then
  HUBS=(
    "this-week-lower:/:3400"
    "settings:/model?tab=settings"
  )
fi
```

- [ ] **Step 4: Run**

`cd frontend && npx tsc --noEmit && npx vitest run` — green; read the `Errors` line as a failure if present.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hubs/this-week/LadderCard.tsx frontend/src/hubs/this-week/LadderCard.test.tsx frontend/src/hubs/ThisWeek.test.tsx frontend/src/hubs/model/SettingsTab.test.tsx frontend/scripts/shots.sh
git commit -m "feat(v17e): the ladder card renders its selects from the settings rows; NO_CAP, HIT_BARS and withCurrent leave the card; shots.sh v17e stage"
```

---

### Task 6: the grep rail

**Files:**
- Modify: `tests/test_v17e_config.py`
- Possibly modify: any `src/gaffer` file the rail names

- [ ] **Step 1: Write the rail**

Append to `tests/test_v17e_config.py`:

```python
# --- §1.2(a) nothing outside config.py opens either file --------------------

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "gaffer"


def _offences(path: pathlib.Path) -> list[str]:
    """Code, not prose: the exact string literals ``"config.toml"`` and
    ``"config.local.toml"`` outside a docstring, an import of ``tomli_w``,
    and an import of ``tomllib`` under ``web/``. A sentence that mentions
    the file ("Set fpl.entry_id in config.toml first.") is not an open."""
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                docstrings.add(id(node.body[0].value))
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value in ("config.toml", "config.local.toml")):
            out.append(f"{node.lineno}: {node.value!r}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tomli_w" or (alias.name == "tomllib" and "web" in path.parts):
                    out.append(f"{node.lineno}: import {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module in ("tomli_w", "tomllib"):
            if node.module == "tomli_w" or "web" in path.parts:
                out.append(f"{node.lineno}: from {node.module}")
    return out


def test_no_module_but_config_opens_either_toml_file():
    offenders = {}
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "config.py" and path.parent == SRC:
            continue
        found = _offences(path)
        if found:
            offenders[str(path.relative_to(SRC))] = found
    assert offenders == {}
```

- [ ] **Step 2: Run it and fix what it names**

Run: `.venv/bin/pytest -q tests/test_v17e_config.py::test_no_module_but_config_opens_either_toml_file`. Expected after Tasks 3 and 4: pass. If it names a file, the fix is to route that read through `config.py` (`base_exists`, `read_overlay`, `value_source`, `config_in_force`), never to add an exemption. `data/managers.py`, `data/set_piece_overrides.py` and `optimize/chip_policy.py` import `tomllib` for files under `data/` and are outside `web/`, so they pass as written.

- [ ] **Step 3: Full suite and commit**

`.venv/bin/pytest -q -m "not golden"` green.

```bash
git add tests/test_v17e_config.py
git commit -m "test(v17e): the rail — no module but config.py opens config.toml or config.local.toml (spec §1.2a)"
```

---

### Task 7 (orchestrator only): the gate, the screenshots, the merge, the record

- [ ] `git diff --stat main -- tests/data/golden_board` prints nothing.
- [ ] `.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py` — 44 passed, none skipped (§1.1).
- [ ] `.venv/bin/pytest -q tests/test_v17e_config.py` (§1.2); the two greps of §1.3.
- [ ] `.venv/bin/pytest -q` and `cd frontend && npx tsc --noEmit && npx vitest run`; `npm run types -- --check`.
- [ ] `cd frontend && npm run build`, `uv run gaffer ui --no-open-browser --port 8927`, `frontend/scripts/shots.sh v17e`; the user approves four images (§1.4).
- [ ] Spec §10 with the numbers; ff-merge; push; the security ritual; ROADMAP block, GUIDE §11 line, GUIDE §7/§8 mentions of `serving_config` updated; tracker row, boxes and hand-off note (the Config pin moved to 62); memory.
