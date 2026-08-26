# Gaffer v4d "Compete" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make league mode rank-aware behind its existing seams — a z-dial computed against the whole league, σ estimated from league history, covering computed from rivals' observed squads, EO-aware captaincy, and tier-resolved live EO — with `lam = 0` still byte-identical to v4c.

**Architecture:** `league_mode.py` grows from two functions into the whole dial: `LeagueParams` (config-driven constants), `margin_sigma` (per-rival margin σ with a fallback chain), `compute_strategy` (z → `lam = LAMBDA_CAP·tanh(|z|/Z_SCALE)·sign(z)`), `threat_weights` (softmax over the rivals that matter), `cover_table`/`captain_cover` (observed-squad covering from `fetch_rival_picks`), `tilt_ep` v2 (cover fractions instead of league-EO percent) and `tilted_captaincy`. `data/league.py` gains two cached fetchers (`fetch_rival_history` per GW, `fetch_rival_picks_history` permanent) and `data/tier_eo.py` samples the top 10k for the live tracker. `advise.py` changes only *inside* its existing league block and at the captain-override seam; `backtest.py` gains one optional `tilt` hook so the orchestrator can run gate E1.

**Tech Stack:** Python 3.12, pandas, numpy, PuLP + HiGHS, Typer, httpx (+ `httpx.MockTransport` for every network test), pytest (`uv run pytest`); React 18 + TypeScript + Vite + vitest in `frontend/`, FastAPI + Pydantic in `src/gaffer/web/`.

---

## Hard constraints — read before writing a line of code

1. **TDD, always.** Failing test first, minimal implementation second, both shown in every step below.
2. **No network in tests.** The two new fetchers and the standings sampler are tested through `httpx.MockTransport` wired into the real `FPLClient`, or through a hand-written fake client where the module never touches `httpx` directly.
3. **Never `git add -A`.** Stage only the files each step names. Never stage `config.toml`, `data/`, `reports/`, `models/`, `.claude/`. No task in this plan needs a `config.toml` commit: every `[league]` key defaults in `src/gaffer/config.py` to today's behaviour, and there is no committed example config in this repo (`git ls-files | grep config` → `config.toml`, `src/gaffer/config.py`, `tests/test_config.py`). If a later change *does* need `config.toml` staged, first swap the real key line
   `api_key = "…"` → `# api_key = "get one free at the-odds-api.com (500 requests/month)"`
   (`sed -i '' 's|^api_key = .*|# api_key = "get one free at the-odds-api.com (500 requests/month)"|' config.toml`), stage, commit, then restore the real key line by hand.
4. **Protected source-text suites are sacred.** See the section below.
5. **The `lam = 0` rails are sacred.** `tilt_ep(ep_by, cover, 0.0)` returns a plain copy; `tilted_captaincy(..., lam=0.0)` is argmax raw EP; the printed `advise` block with no league is character-for-character what v4c printed. Task 11 pins all three.
6. **Frequent small commits**, one per task (or per step where a task says so), each ending with:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

Use this exact shape:

```bash
git commit -m "feat: <subject>" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Protected source-text tests — read this before touching `advise.py` or `backtest.py`

These suites assert on the **source text** of `run_advise`, `run_backtest` and
`predict_components`, because there is no cheap end-to-end harness for them.

- `tests/test_advise.py:74-94` — inside `run_advise`:
  `src.index("fetch_rival_entries(") < src.index("tilt_ep(") < src.index("pool = build_pool(")`,
  plus `"compute_strategy(" in src` with `src.index("compute_strategy(") < pool`,
  `"except Exception" in src`, `'summary_overall_points' in src`, and the literal
  `"build_pool(players, pool_ep," in src`.
- `tests/test_advise.py:97-109` — also inside `run_advise`: `"ep_named = ep.merge(" in src`,
  `'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src`,
  **`"pool_ep" not in src[src.index("ep_gw1 ="):]`**, and
  `'_named(first.xi, name_of, pos_of, ep_by, gw)' in src`.
- `tests/test_assemble.py:215` — `"ep_matrix(apply_calibration(assemble_ep("` in **both**
  `run_advise` and `run_backtest`.
- `tests/test_odds.py:315` — inside `run_advise`: `odds_frame(raw_odds, teams, events)` <
  `tg_future = build_team_future(` < `merge_team_odds(tg_future, odds_df)`, plus
  `"if cfg.odds_api_key:" in src`, `"except Exception" in src`, `"drop_duplicates" not in src`.
- `tests/test_backtest.py:520-552` — `run_backtest` keeps the calibration literal,
  `chips` still defaults to `False`, and `"unplayed_chips" in src`.

Consequences for this plan:

- Everything v4d adds to `run_advise` goes **inside** the existing
  `if cfg.league_id:` block (Task 6) or **immediately after** the v4c scenario
  block and before the chips block (Task 7). Both sites are well before
  `ep_gw1 =`.
- **Nothing inserted anywhere in `run_advise` may contain the substring
  `pool_ep`.** The cover table is called `cover`; the captaincy seam reads
  `ep_by`, never the tilted dict. Tasks 6, 7 and 11 restate this and re-run the
  whole suite.
- The one-line `pool_ep = tilt_ep(ep_by, cover, …)` statement at
  `src/gaffer/advise.py:551` keeps its exact left-hand side and the literal
  `build_pool(players, pool_ep,` at `:558` is untouched.

---

## File Structure

**Created:**

| Path | Responsibility |
| --- | --- |
| `src/gaffer/data/tier_eo.py` | `sample_slots`, `fetch_tier_entries`, `binomial_se`, `tier_eo_table`. Uniform (page, slot) sample of the top 10k of league 314, per-GW JSON cache, EO-with-captaincy plus a binomial SE. |
| `tests/test_tier_eo.py` | Sampler uniqueness/determinism, page re-use, SE math, cache round-trip, degradation on a failing page. |
| `tests/test_v4d_degradation.py` | The v4d rails: `lam = 0` tilt identity, `lam = 0` captaincy identity, the pinned `advise` CLI block, the protected orderings re-asserted. |

**Modified:**

| Path | Change |
| --- | --- |
| `src/gaffer/config.py` | New `[league]` section: `z_scale`, `lambda_cap`, `sigma_floor`, `sigma_cap`, `sigma_min_weeks`, `tier_eo`, `tier_sample`. |
| `src/gaffer/league_mode.py` | `LeagueParams`, `margin_sigma`, z-dial `compute_strategy`, `Strategy` v2 (`z`, `sigma_m`, `cover_weights`), `threat_weights`, `cover_table`, `captain_cover`, `cover_from_eo`, `tilt_ep` v2, `tilted_captaincy`, `captaincy_note`. |
| `src/gaffer/data/league.py` | `fetch_rival_history` (per-GW cache), `fetch_rival_picks_history` (permanent per-season cache). |
| `src/gaffer/advise.py` | League block builds history + cover + captain cover; `pool_ep` line feeds `cover`; captain-override seam; two new `Advice` fields. |
| `src/gaffer/backtest.py` | Optional `tilt` hook on `run_backtest`, applied to `ep_by` before `build_pool`. |
| `src/gaffer/cli.py` | Captain line grows an optional note and a demoted-captain line (both absent by default). |
| `src/gaffer/report/templates/report.html.j2` | Same two conditional captain fragments. |
| `src/gaffer/web/routers/live.py` | Tier-EO lookup guarded by `cfg.tier_eo`, degrading to a notice. |
| `src/gaffer/web/schemas.py` | `LivePlayer.tier_eo`, `.tier_eo_se`, `.selected_by_percent`; `LiveState.notice`. |
| `frontend/src/types.ts` | Same three optional fields on `LivePlayer`, `notice` on `LiveState`. |
| `frontend/src/pages/Live.tsx` | Two extra columns on the player table + the notice line. |
| `frontend/src/pages/Live.test.tsx` | Columns present with tier EO, absent without it. |
| `tests/test_config.py` | `[league]` defaults and reads. |
| `tests/test_league_mode.py` | z cases, σ chain, weights, cover, tilt v2, captaincy; the pre-v4d ramp expectations updated deliberately. |
| `tests/test_league.py` | The two new fetchers, through `httpx.MockTransport`. |
| `tests/test_advise.py` | New league-block assertions; protected orderings re-pinned. |
| `tests/test_backtest.py` | `tilt` default-off identity and injected-hook effect. |
| `tests/test_web_live.py` | Tier-EO columns and the degradation notice. |
| `tests/test_cli.py` | Captain note / demoted line. |

---

## Task 1: The `[league]` config section and `LeagueParams`

Every constant the dial uses becomes configurable, and every default is
today's behaviour. `[league]` is a brand-new optional section whose TOML keys
match the field names but which must not be splatted (it is optional and the
dataclass has other sources), so it is read key-by-key exactly as `[odds]` and
`[scenarios]` already are (`src/gaffer/config.py:37-66`).

`league_mode.py` must not import `gaffer.config` (that would invert the
dependency), so `LeagueParams.from_config` is duck-typed on the attributes.

**Files:**
- Modify: `src/gaffer/config.py:8-35` (`Config`), `:37-66` (`load_config`)
- Modify: `src/gaffer/league_mode.py:14-16` (constants block)
- Test: `tests/test_config.py` (append), `tests/test_league_mode.py` (append)

- [ ] **Step 1: Write the failing config test**

Append to `tests/test_config.py`:

```python
# --- v4d league mode -------------------------------------------------------


def _league_cfg(tmp_path, body: str = ""):
    p = tmp_path / "config.toml"
    p.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n' + body)
    return p


def test_league_section_defaults_to_the_spec_values(tmp_path):
    """A fresh clone with no [league] section gets the dial's pinned
    constants, so nobody has to edit config.toml to get v4d behaviour."""
    cfg = load_config(_league_cfg(tmp_path))
    assert cfg.z_scale == 1.5
    assert cfg.lambda_cap == 0.5
    assert cfg.sigma_floor == 8.0
    assert cfg.sigma_cap == 30.0
    assert cfg.sigma_min_weeks == 6
    assert cfg.tier_eo is True
    assert cfg.tier_sample == 300


def test_league_section_is_read(tmp_path):
    cfg = load_config(_league_cfg(tmp_path, """
[league]
z_scale = 2.0
lambda_cap = 0.25
sigma_floor = 5.0
sigma_cap = 40.0
sigma_min_weeks = 3
tier_eo = false
tier_sample = 50
"""))
    assert (cfg.z_scale, cfg.lambda_cap) == (2.0, 0.25)
    assert (cfg.sigma_floor, cfg.sigma_cap) == (5.0, 40.0)
    assert cfg.sigma_min_weeks == 3
    assert cfg.tier_eo is False
    assert cfg.tier_sample == 50
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_config.py -k league -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'z_scale'`.

- [ ] **Step 3: Add the fields and the reader**

In `src/gaffer/config.py`, append to the `Config` dataclass (after
`bench_curve: list[float] | None = None`):

```python
    # --- v4d league mode ---------------------------------------------------
    # The z-dial's constants. Every default is the pinned value from the v4d
    # design, and league mode itself stays gated by league_id — there is no
    # new master switch. tier_eo is live-tracker display only and never
    # reaches the optimizer.
    z_scale: float = 1.5
    lambda_cap: float = 0.5
    sigma_floor: float = 8.0
    sigma_cap: float = 30.0
    sigma_min_weeks: int = 6
    tier_eo: bool = True
    tier_sample: int = 300
```

In `load_config`, after the `scen = raw.get("scenarios", {})` line add:

```python
    league = raw.get("league", {})
```

and add these keyword arguments to the `Config(...)` call, after
`decision_priors=...`:

```python
        z_scale=float(league.get("z_scale", 1.5)),
        lambda_cap=float(league.get("lambda_cap", 0.5)),
        sigma_floor=float(league.get("sigma_floor", 8.0)),
        sigma_cap=float(league.get("sigma_cap", 30.0)),
        sigma_min_weeks=int(league.get("sigma_min_weeks", 6)),
        tier_eo=bool(league.get("tier_eo", True)),
        tier_sample=int(league.get("tier_sample", 300)),
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS — all config tests green, including the pre-existing ones.

- [ ] **Step 5: Write the failing `LeagueParams` test**

Append to `tests/test_league_mode.py`:

```python
# --- v4d: the dial's parameters --------------------------------------------


def test_league_params_default_to_the_module_constants():
    from gaffer.league_mode import (LAMBDA_CAP, SIGMA_CAP, SIGMA_FLOOR,
                                    SIGMA_MIN_WEEKS, Z_SCALE, LeagueParams)

    p = LeagueParams()
    assert (p.z_scale, p.lambda_cap) == (Z_SCALE, LAMBDA_CAP)
    assert (p.sigma_floor, p.sigma_cap) == (SIGMA_FLOOR, SIGMA_CAP)
    assert p.sigma_min_weeks == SIGMA_MIN_WEEKS


def test_league_params_read_a_config_without_importing_it():
    """Duck-typed on the attributes: league_mode must not import config."""
    from types import SimpleNamespace

    from gaffer.league_mode import LeagueParams

    cfg = SimpleNamespace(z_scale=2.0, lambda_cap=0.25, sigma_floor=5.0,
                          sigma_cap=40.0, sigma_min_weeks=3)
    p = LeagueParams.from_config(cfg)
    assert (p.z_scale, p.lambda_cap, p.sigma_floor) == (2.0, 0.25, 5.0)
    assert (p.sigma_cap, p.sigma_min_weeks) == (40.0, 3)


def test_the_old_sigma_pin_is_still_importable_under_both_names():
    """SIGMA is asserted by an existing test and imported elsewhere; the
    renamed SIGMA_FALLBACK is the same number, not a second policy."""
    from gaffer.league_mode import SIGMA, SIGMA_FALLBACK

    assert SIGMA == SIGMA_FALLBACK == 18.0
```

- [ ] **Step 6: Run it and see it fail**

Run: `uv run pytest tests/test_league_mode.py -k params -v`
Expected: FAIL — `ImportError: cannot import name 'LeagueParams' from 'gaffer.league_mode'`.

- [ ] **Step 7: Add the constants and `LeagueParams`**

In `src/gaffer/league_mode.py`, replace lines 14-16:

```python
SIGMA = 18.0        # per-GW score sigma, pinned; later: estimate from tracking
LAMBDA_CAP = 0.5
LAST_GW = 38
```

with:

```python
SIGMA_FALLBACK = 18.0
"""Per-GW margin sigma when the league has no history at all (GW1)."""

SIGMA = SIGMA_FALLBACK
"""Kept name for the pin: existing callers and tests import SIGMA."""

LAMBDA_CAP = 0.5
Z_SCALE = 1.5
SIGMA_FLOOR = 8.0
SIGMA_CAP = 30.0
SIGMA_MIN_WEEKS = 6
LAST_GW = 38


@dataclass(frozen=True)
class LeagueParams:
    """The dial's constants, defaulted to the pins and overridable by
    ``[league]`` in config.toml. Duck-typed on the config object so that
    league_mode never imports gaffer.config."""

    z_scale: float = Z_SCALE
    lambda_cap: float = LAMBDA_CAP
    sigma_floor: float = SIGMA_FLOOR
    sigma_cap: float = SIGMA_CAP
    sigma_min_weeks: int = SIGMA_MIN_WEEKS

    @classmethod
    def from_config(cls, cfg) -> "LeagueParams":
        return cls(z_scale=float(getattr(cfg, "z_scale", Z_SCALE)),
                   lambda_cap=float(getattr(cfg, "lambda_cap", LAMBDA_CAP)),
                   sigma_floor=float(getattr(cfg, "sigma_floor", SIGMA_FLOOR)),
                   sigma_cap=float(getattr(cfg, "sigma_cap", SIGMA_CAP)),
                   sigma_min_weeks=int(getattr(cfg, "sigma_min_weeks",
                                               SIGMA_MIN_WEEKS)))
```

- [ ] **Step 8: Run it and see it pass**

Run: `uv run pytest tests/test_league_mode.py tests/test_config.py -v`
Expected: PASS — every test in both files, including the pre-existing
`assert (SIGMA, LAMBDA_CAP) == (18.0, 0.5)`.

- [ ] **Step 9: Commit**

```bash
git add src/gaffer/config.py src/gaffer/league_mode.py tests/test_config.py tests/test_league_mode.py
git commit -m "feat: [league] config section and LeagueParams" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 2: `fetch_rival_history` with a per-GW raw cache

σ needs the per-GW points series for me and every rival. The FPL entry-history
endpoint (`entry/{id}/history/`, already on the client at
`src/gaffer/api/client.py:61-62`) returns `{"current": [{"event", "points",
"total_points"}, …]}`. One call per entry is expensive enough to cache: the
season's completed weeks are a fact, so a per-GW JSON under `data/raw/league/`
is read back verbatim on the second call.

A rival whose history 404s (joined late, private) is skipped, not fatal — the
same rule `fetch_rival_picks` already follows at `src/gaffer/data/league.py:44-46`.

**Files:**
- Modify: `src/gaffer/data/league.py:1-16` (imports/constants), append at `:59`
- Test: `tests/test_league.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_league.py`:

```python
# --- v4d: entry history for the sigma estimator ----------------------------

import json

from gaffer.api.client import FPLClient
from gaffer.data.league import fetch_rival_history


def _history_transport(points_by_entry: dict[int, list[int]], calls: list):
    """entry/{id}/history/ for a handful of entries; no network."""

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.rstrip("/").split("/")
        entry = int(parts[-2])
        calls.append(entry)
        pts = points_by_entry.get(entry)
        if pts is None:
            return httpx.Response(404, json={"detail": "Not found."})
        current = [{"event": i + 1, "points": p,
                    "total_points": sum(pts[:i + 1])}
                   for i, p in enumerate(pts)]
        return httpx.Response(200, json={"current": current, "past": [],
                                         "chips": []})

    return httpx.MockTransport(handler)


def test_fetch_rival_history_returns_entry_gw_points(tmp_path):
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({1: [50, 60, 70],
                                                     7: [40, 80, 55]}, calls))
    df = fetch_rival_history(client, [1, 7], gw=3,
                             raw_dir=tmp_path / "league")
    assert list(df.columns) == ["entry", "gw", "points"]
    assert len(df) == 6
    assert set(df["entry"]) == {1, 7}
    assert int(df[(df["entry"] == 7) & (df["gw"] == 2)]["points"].iloc[0]) == 80


def test_fetch_rival_history_stops_at_the_requested_gameweek(tmp_path):
    """A GW that is underway must not leak a half-scored week into sigma."""
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({1: [50, 60, 70]}, calls))
    df = fetch_rival_history(client, [1], gw=2, raw_dir=tmp_path / "league")
    assert set(df["gw"]) == {1, 2}


def test_fetch_rival_history_skips_an_entry_with_no_history(tmp_path):
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=_history_transport({1: [50, 60]}, calls))
    df = fetch_rival_history(client, [1, 999], gw=2,
                             raw_dir=tmp_path / "league")
    assert set(df["entry"]) == {1}


def test_fetch_rival_history_caches_per_gameweek(tmp_path):
    calls: list[int] = []
    cache = tmp_path / "league"
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({1: [50, 60]}, calls))
    first = fetch_rival_history(client, [1], gw=2, raw_dir=cache)
    assert calls == [1]
    assert json.loads((cache / "history-gw2.json").read_text())
    second = fetch_rival_history(client, [1], gw=2, raw_dir=cache)
    assert calls == [1]                       # served from disk, no re-fetch
    assert second.equals(first)


def test_fetch_rival_history_of_nobody_is_an_empty_frame(tmp_path):
    calls: list[int] = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_history_transport({}, calls))
    df = fetch_rival_history(client, [], gw=1, raw_dir=tmp_path / "league")
    assert df.empty and list(df.columns) == ["entry", "gw", "points"]
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_league.py -k history -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_rival_history' from 'gaffer.data.league'`.

- [ ] **Step 3: Implement the fetcher**

In `src/gaffer/data/league.py`, replace the import/constant block at lines 8-16:

```python
from __future__ import annotations

import pandas as pd

from gaffer.api.client import FPLClient

STANDINGS_COLS = ["entry", "entry_name", "player_name", "rank",
                  "last_rank", "total", "event_total"]
```

with:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gaffer.api.client import FPLClient

STANDINGS_COLS = ["entry", "entry_name", "player_name", "rank",
                  "last_rank", "total", "event_total"]

HISTORY_COLS = ["entry", "gw", "points"]

RAW_LEAGUE = Path("data/raw/league")
"""Where league payloads are cached, alongside the client's other raw JSON."""
```

Append at the end of the file:

```python
def fetch_rival_history(client: FPLClient, entries: list[int], gw: int,
                        raw_dir: Path | str = RAW_LEAGUE) -> pd.DataFrame:
    """(entry, gw, points) for every entry, this season through ``gw``.

    Cached per gameweek: the completed weeks of a season are facts, and one
    HTTP call per rival per advise run is the most expensive thing league
    mode does. Weeks after ``gw`` are dropped — a gameweek still being played
    would put a half-scored margin into the sigma estimate. An entry whose
    history is not public is skipped, exactly as ``fetch_rival_picks`` skips
    an entry whose picks are not.
    """
    path = Path(raw_dir) / f"history-gw{int(gw)}.json"
    if path.exists():
        return pd.DataFrame(json.loads(path.read_text()), columns=HISTORY_COLS)
    rows: list[dict] = []
    for entry in entries:
        try:
            current = client.get_entry_history(int(entry)).get("current") or []
        except Exception:
            continue        # entry joined late / history private — skip
        for event in current:
            if int(event["event"]) > int(gw):
                continue
            rows.append({"entry": int(entry), "gw": int(event["event"]),
                         "points": int(event["points"])})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    return pd.DataFrame(rows, columns=HISTORY_COLS)
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_league.py -v`
Expected: PASS — five new tests plus the three pre-existing ones.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/league.py tests/test_league.py
git commit -m "feat: fetch_rival_history with a per-gameweek raw cache" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 3: `margin_sigma` — σ from league history, with the fallback chain

σ_m for a rival is the standard deviation of the per-GW margin series
`my_points_gw − rival_points_gw`. Fallbacks in order: fewer than
`sigma_min_weeks` shared completed GWs → the pooled league-wide margin σ; no
usable history at all → `SIGMA_FALLBACK`. Everything is clamped to
`[sigma_floor, sigma_cap]` last, so a fortnight of mirrored squads cannot make
z explode.

**Files:**
- Modify: `src/gaffer/league_mode.py` (append after `LeagueParams`)
- Test: `tests/test_league_mode.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_league_mode.py`:

```python
# --- v4d: sigma from league history ----------------------------------------


def _history(series: dict[int, list[int]]) -> pd.DataFrame:
    """{entry: [gw1 points, gw2 points, ...]} -> the fetcher's frame shape."""
    rows = [{"entry": entry, "gw": i + 1, "points": p}
            for entry, points in series.items()
            for i, p in enumerate(points)]
    return pd.DataFrame(rows, columns=["entry", "gw", "points"])


def test_margin_sigma_is_the_stdev_of_the_margin_series():
    from gaffer.league_mode import margin_sigma

    # Margins: +10, -10, +10, -10, +10, -10 -> stdev ~ 10.95, inside bounds.
    hist = _history({1: [60, 40, 60, 40, 60, 40],
                     2: [50, 50, 50, 50, 50, 50]})
    out = margin_sigma(hist, my_entry=1)
    assert out[2] == pytest.approx(10.954, abs=1e-3)


def test_margin_sigma_floors_a_mirrored_squad():
    """Identical squads produce near-zero margins; without the floor z would
    explode and lam would saturate on noise."""
    from gaffer.league_mode import SIGMA_FLOOR, margin_sigma

    hist = _history({1: [50, 51, 50, 51, 50, 51],
                     2: [50, 51, 50, 51, 50, 50]})
    assert margin_sigma(hist, my_entry=1)[2] == SIGMA_FLOOR


def test_margin_sigma_caps_a_wild_series():
    from gaffer.league_mode import SIGMA_CAP, margin_sigma

    hist = _history({1: [120, 20, 120, 20, 120, 20],
                     2: [20, 120, 20, 120, 20, 120]})
    assert margin_sigma(hist, my_entry=1)[2] == SIGMA_CAP


def test_margin_sigma_falls_back_to_the_pooled_league_sigma():
    """A rival with three weeks of history borrows the league's pooled
    margin spread rather than trusting three points."""
    from gaffer.league_mode import margin_sigma

    hist = pd.concat([
        _history({1: [60, 40, 60, 40, 60, 40],
                  2: [50, 50, 50, 50, 50, 50]}),
        _history({3: [49, 51, 49]}),
    ], ignore_index=True)
    out = margin_sigma(hist, my_entry=1)
    pooled_borrower, established = out[3], out[2]
    assert pooled_borrower != pytest.approx(established, abs=1e-9)
    assert 8.0 <= pooled_borrower <= 30.0


def test_margin_sigma_falls_back_to_the_pin_with_no_history_at_all():
    from gaffer.league_mode import SIGMA_FALLBACK, margin_sigma

    hist = _history({1: [50], 2: [40]})     # one week: nothing poolable
    assert margin_sigma(hist, my_entry=1)[2] == SIGMA_FALLBACK


def test_margin_sigma_of_an_empty_frame_is_empty():
    from gaffer.league_mode import margin_sigma

    assert margin_sigma(pd.DataFrame(columns=["entry", "gw", "points"]),
                        my_entry=1) == {}
    assert margin_sigma(None, my_entry=1) == {}


def test_margin_sigma_only_pairs_gameweeks_we_both_played():
    """A rival who joined at GW3 has no GW1-2 margin; pairing on index
    instead of gameweek would invent two."""
    from gaffer.league_mode import margin_sigma

    hist = pd.concat([_history({1: [50, 60, 70, 80, 90, 100, 55]}),
                      pd.DataFrame([{"entry": 2, "gw": g, "points": p}
                                    for g, p in [(3, 70), (4, 80)]])],
                     ignore_index=True)
    out = margin_sigma(hist, my_entry=1)
    assert out[2] == pytest.approx(18.0)    # 2 shared weeks -> the pin
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_league_mode.py -k margin_sigma -v`
Expected: FAIL — `ImportError: cannot import name 'margin_sigma'`.

- [ ] **Step 3: Implement the estimator**

In `src/gaffer/league_mode.py`, add `import statistics` under `import math`,
and append after `LeagueParams`:

```python
def _bounded(sigma: float, params: LeagueParams) -> float:
    return min(max(float(sigma), params.sigma_floor), params.sigma_cap)


def _stdev(series: list[float]) -> float | None:
    """Sample stdev, or None when there is not enough of a series to have one."""
    if len(series) < 2:
        return None
    return float(statistics.stdev(series))


def margin_sigma(history, my_entry: int,
                 params: LeagueParams | None = None) -> dict[int, float]:
    """rival entry -> sigma of the per-GW margin (my points minus theirs).

    Margin sigma is squad-overlap-aware for free: mirrored squads produce
    small margins, so a small sigma, so the same points gap counts for more.
    That is exactly what the flat 18.0 pin got wrong.

    Fallback chain, in order: the rival's own margin series when it has at
    least ``sigma_min_weeks`` shared gameweeks; the pooled league-wide margin
    series when it does not; :data:`SIGMA_FALLBACK` when there is no poolable
    history either. The result is bounded last, so no branch can escape
    ``[sigma_floor, sigma_cap]``.
    """
    p = params or LeagueParams()
    if history is None or len(history) == 0 or "entry" not in history.columns:
        return {}
    mine = history[history["entry"] == my_entry]
    my_points = {int(g): float(pts)
                 for g, pts in zip(mine["gw"], mine["points"])}
    margins: dict[int, list[float]] = {}
    for entry, group in history[history["entry"] != my_entry].groupby("entry"):
        margins[int(entry)] = [my_points[int(g)] - float(pts)
                               for g, pts in zip(group["gw"], group["points"])
                               if int(g) in my_points]
    pooled = [m for series in margins.values() for m in series]
    pooled_sigma = (_stdev(pooled) if len(pooled) >= p.sigma_min_weeks
                    else None)
    out: dict[int, float] = {}
    for entry, series in margins.items():
        own = _stdev(series) if len(series) >= p.sigma_min_weeks else None
        sigma = own if own is not None else pooled_sigma
        out[entry] = _bounded(sigma if sigma is not None else SIGMA_FALLBACK,
                              p)
    return out
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_league_mode.py -v`
Expected: PASS — the seven new σ tests plus every pre-existing one.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/league_mode.py tests/test_league_mode.py
git commit -m "feat: margin sigma estimated from league history" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 4: The z-dial — `Strategy` v2 and the tanh λ map

`z` is the deficit to the **win condition** in units of remaining-horizon
margin spread. Behind the leader, `z = (leader − me) / (σ_m·√W)`. Ahead of
everyone, the threat is the pack: `z = −min_r (me − them) / (σ_mr·√W)`, i.e.
the rival with the largest P(catch me), which is *not* always the one with the
largest raw total. `lam = lambda_cap · tanh(|z| / z_scale) · sign(z)`.

This deliberately replaces the old clamp ramp (dead zone then hard
saturation), so two existing tests change meaning and are rewritten here. The
two rails — empty rivals and dead heat — keep their exact assertions.

`Strategy` grows three fields, all defaulted and appended last, so the
positional constructions in `tests/test_league_mode.py:104-113` keep compiling.

**Files:**
- Modify: `src/gaffer/league_mode.py:19-41` (`Strategy`, `compute_strategy`)
- Test: `tests/test_league_mode.py:12-28` (rewrite two), append new cases

- [ ] **Step 1: Write the failing tests**

In `tests/test_league_mode.py`, replace the two ramp tests at lines 12-23:

```python
def test_small_gap_is_neutral():
    s = compute_strategy(my_total=495, rivals=RIVALS, current_gw=10)
    assert s.stance == "neutral" and s.lam == 0.0


def test_big_gap_chases_with_positive_lambda():
    s = compute_strategy(my_total=380, rivals=RIVALS, current_gw=30)
    assert s.stance == "chase"
    assert s.lam == pytest.approx(
        0.5 * min(120 / (2 * 18 * 9 ** 0.5) - 0.5, 1.0))
    assert s.rival_name == "Leader"
```

with:

```python
def test_a_small_gap_is_a_small_chase_not_a_dead_zone():
    """v4d replaces the clamp ramp: the dial is smooth in z, so five points
    behind is a small tilt rather than none at all."""
    import math

    s = compute_strategy(my_total=495, rivals=RIVALS, current_gw=10)
    z = 5 / (18.0 * math.sqrt(29))
    assert s.stance == "chase"
    assert s.lam == pytest.approx(0.5 * math.tanh(z / 1.5))
    assert 0.0 < s.lam < 0.02


def test_big_gap_chases_with_positive_lambda():
    import math

    s = compute_strategy(my_total=380, rivals=RIVALS, current_gw=30)
    z = 120 / (18.0 * math.sqrt(9))
    assert s.stance == "chase"
    assert s.lam == pytest.approx(0.5 * math.tanh(z / 1.5))
    assert s.z == pytest.approx(z)
    assert s.sigma_m == 18.0
    assert s.rival_name == "Leader"
    assert s.gap == 120
```

Then append:

```python
# --- v4d: the z-dial -------------------------------------------------------


def test_a_runaway_leader_saturates_below_the_cap():
    """tanh is asymptotic: no gap, however silly, can exceed lambda_cap."""
    s = compute_strategy(my_total=0, rivals=RIVALS, current_gw=37)
    assert 0.49 < s.lam < 0.5


def test_leading_defends_against_the_nearest_threat_in_sigma_units():
    """The threat is the rival most likely to catch me, not the one with the
    largest raw total: a tight rival 30 behind at sigma 8 is further away in
    normalized units than a volatile one 40 behind at sigma 30."""
    from gaffer.league_mode import compute_strategy

    rivals = pd.DataFrame({"entry": [11, 12], "entry_name": ["Volatile",
                                                             "Tight"],
                           "total": [460, 470]})
    history = pd.concat([
        _history({1: [80] * 6, 11: [20, 140, 20, 140, 20, 140],
                  12: [78, 82, 78, 82, 78, 82]}),
    ], ignore_index=True)
    s = compute_strategy(my_total=500, rivals=rivals, current_gw=38,
                         history=history, my_entry=1)
    assert s.stance == "defend" and s.lam < 0
    assert s.rival_name == "Volatile"        # 40 / 30 = 1.33 < 30 / 8 = 3.75
    assert s.sigma_m == 30.0
    assert s.gap == 40


def test_the_dead_heat_z_is_exactly_zero_and_not_negative_zero():
    """-0.0 renders as a typo in the report and would flip the stance test."""
    s = compute_strategy(my_total=500, rivals=RIVALS, current_gw=36)
    assert s.z == 0.0
    assert str(s.z) == "0.0"
    assert s.lam == 0.0 and s.stance == "neutral"


def test_strategy_carries_the_new_fields_with_defaults():
    """Appended last and defaulted: the positional constructions in this file
    and in the report path keep working."""
    from gaffer.league_mode import SIGMA_FALLBACK, Strategy

    s = Strategy(0.4, 84, 30, "chase", "Ten Hag Hive")
    assert s.z == 0.0
    assert s.sigma_m == SIGMA_FALLBACK
    assert s.cover_weights == {}
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_league_mode.py -k "chase or defend or dead_heat or carries or saturat" -v`
Expected: FAIL — `AttributeError: 'Strategy' object has no attribute 'z'`, and
the λ assertions fail against the old clamp ramp.

- [ ] **Step 3: Implement `Strategy` v2 and the dial**

In `src/gaffer/league_mode.py`, replace the module docstring's formula line and
the `Strategy`/`compute_strategy` block (lines 1-41) so that the docstring reads:

```python
"""Rank-aware strategy for the mini-league (spec 2026-08-26 §3-§5).

z is the deficit to the *win condition* in units of remaining-horizon margin
spread, and lam = LAMBDA_CAP * tanh(|z| / Z_SCALE) * sign(z). Positive lam
chases (favor players the threats do not own), negative defends (cover them),
zero leaves the optimizer exactly at v1 points-max.
"""
```

and replace `Strategy` and `compute_strategy` with:

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


def _sign(x: float) -> float:
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


def compute_strategy(my_total: int, rivals: pd.DataFrame, current_gw: int,
                     history=None, my_entry: int | None = None,
                     params: LeagueParams | None = None) -> Strategy:
    """The dial: z against the whole league, then lam = cap * tanh(z / scale).

    Behind the leader, z is the normalized deficit to the one entry standing
    between me and the title. Ahead of everyone, z is minus the *nearest*
    threat in normalized units — the rival with the largest P(catch me),
    which is not always the rival with the largest total.

    ``history`` and ``my_entry`` are optional: without them every sigma is
    the pin, which is exactly the pre-v4d spread.
    """
    p = params or LeagueParams()
    weeks = max(1, LAST_GW - current_gw + 1)
    if rivals.empty:
        return Strategy(0.0, 0, weeks, "neutral", "")
    sigmas = (margin_sigma(history, my_entry, p)
              if history is not None and my_entry is not None else {})
    root = math.sqrt(weeks)
    fallback = _bounded(SIGMA_FALLBACK, p)

    def sigma_of(row) -> float:
        if "entry" not in row.index:
            return fallback
        return sigmas.get(int(row["entry"]), fallback)

    top = rivals.sort_values("total", ascending=False).iloc[0]
    if int(top["total"]) > my_total:
        rival_row = top
        sigma_m = sigma_of(top)
        z = (int(top["total"]) - my_total) / (sigma_m * root)
        gap = int(top["total"]) - my_total
    else:
        rival_row, sigma_m, nearest = None, fallback, None
        for _, row in rivals.iterrows():
            sigma = sigma_of(row)
            norm = (my_total - int(row["total"])) / (sigma * root)
            if nearest is None or norm < nearest:
                rival_row, sigma_m, nearest = row, sigma, norm
        z = -nearest
        gap = my_total - int(rival_row["total"])
    if z == 0.0:
        z = 0.0          # a dead-level league gives -0.0, which reads as a typo
    lam = p.lambda_cap * math.tanh(abs(z) / p.z_scale) * _sign(z)
    stance = "neutral" if lam == 0 else ("chase" if lam > 0 else "defend")
    weights = threat_weights(my_total, rivals, sigmas, weeks, p)
    return Strategy(lam, gap, weeks, stance, str(rival_row["entry_name"]),
                    z=z, sigma_m=sigma_m, cover_weights=weights)
```

Add `field` to the dataclasses import at the top of the file:

```python
from dataclasses import dataclass, field
```

`threat_weights` is defined in Task 5; until then, add this placeholder-free
minimal version immediately above `compute_strategy` so this task's tests pass
on their own, and Task 5 replaces its body:

```python
def threat_weights(my_total: int, rivals: pd.DataFrame,
                   sigmas: dict[int, float], weeks_left: int,
                   params: LeagueParams | None = None) -> dict[int, float]:
    """Rival threat weights; Task 5 gives this its softmax body."""
    return {}
```

- [ ] **Step 4: Run them and see them pass**

Run: `uv run pytest tests/test_league_mode.py -v`
Expected: PASS — including `test_empty_rivals_is_neutral`,
`test_tied_with_leader_is_neutral` and `test_explain_lam_puts_the_tilt_in_words`
untouched.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/league_mode.py tests/test_league_mode.py
git commit -m "feat: z-dial replaces the lambda clamp ramp" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 5: Threat weights and the observed-squad cover table

League EO answers "who does the league own"; covering answers "who do the
rivals *that matter* own". `w_r = softmax_r(−|gap_r| / (σ_mr·√W))` over the
relevant side — the leader when behind, every rival within `3·σ_mr·√W` behind
me when ahead. `cover_p = min(Σ_r w_r · own_{r,p}, 1)` with `own ∈ {0, 1, 2}`
(bench / owned / captained), clamped **after** weighting, exactly as the old
`min(EO%/100, 1)` clamped league EO.

**Files:**
- Modify: `src/gaffer/league_mode.py` (replace the `threat_weights` stub, append three functions)
- Test: `tests/test_league_mode.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_league_mode.py`:

```python
# --- v4d: threat weights and covering --------------------------------------


def test_threat_weights_behind_are_all_on_the_leader():
    """Behind, the win condition is one entry: the leader. Nobody else is
    between me and the title, so nobody else gets weight."""
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12, 13],
                           "entry_name": ["Leader", "Mid", "Tail"],
                           "total": [500, 460, 400]})
    w = threat_weights(my_total=450, rivals=rivals, sigmas={}, weeks_left=9)
    assert w == {11: 1.0}


def test_threat_weights_ahead_favour_the_nearest_and_sum_to_one():
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12],
                           "entry_name": ["Close", "Far"],
                           "total": [495, 460]})
    w = threat_weights(my_total=500, rivals=rivals, sigmas={11: 18.0,
                                                            12: 18.0},
                       weeks_left=9)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w[11] > w[12]


def test_threat_weights_ahead_ignore_a_rival_two_hundred_adrift():
    """A rival beyond 3 sigma-root-W back contributes ~nothing, so covering
    his squad must not shape my pool at all."""
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12],
                           "entry_name": ["Close", "Gone"],
                           "total": [495, 300]})
    w = threat_weights(my_total=500, rivals=rivals,
                       sigmas={11: 18.0, 12: 18.0}, weeks_left=9)
    assert set(w) == {11}
    assert w[11] == pytest.approx(1.0)


def test_threat_weights_with_nobody_in_range_fall_back_to_the_nearest():
    """An empty weight table would make every cover zero, which reads as
    'nobody owns anybody' — the nearest rival is the honest answer."""
    from gaffer.league_mode import threat_weights

    rivals = pd.DataFrame({"entry": [11, 12], "entry_name": ["A", "B"],
                           "total": [100, 50]})
    w = threat_weights(my_total=500, rivals=rivals,
                       sigmas={11: 8.0, 12: 8.0}, weeks_left=1)
    assert w == {11: 1.0}


def test_threat_weights_without_entry_ids_are_empty():
    """The report-only rivals frame in the tests has no entry column; an
    exception there would take the whole advice down."""
    from gaffer.league_mode import threat_weights

    assert threat_weights(500, RIVALS, {}, 9) == {}


PICKS = {11: [{"element": 1, "multiplier": 2},      # captained
              {"element": 2, "multiplier": 1},
              {"element": 3, "multiplier": 0}],     # benched
         12: [{"element": 2, "multiplier": 1},
              {"element": 4, "multiplier": 1}]}


def test_cover_counts_captaincy_double_and_the_bench_zero():
    from gaffer.league_mode import cover_table

    cover = cover_table(PICKS, {11: 0.5, 12: 0.5})
    assert cover[1] == pytest.approx(1.0)      # 0.5 * 2, clamped at 1
    assert cover[2] == pytest.approx(1.0)      # 0.5 + 0.5
    assert cover[4] == pytest.approx(0.5)
    assert 3 not in cover                      # benched: owned by nobody


def test_cover_clamps_after_weighting_not_before():
    """0.6 * 2 = 1.2 must become 1.0 at the end, not 0.6 * min(2, 1)."""
    from gaffer.league_mode import cover_table

    cover = cover_table({11: [{"element": 1, "multiplier": 2}]}, {11: 0.6})
    assert cover[1] == 1.0


def test_cover_ignores_a_rival_with_no_weight():
    from gaffer.league_mode import cover_table

    assert cover_table(PICKS, {11: 1.0}) == {1: 1.0, 2: 1.0}


def test_cover_with_equal_weights_reduces_to_league_eo():
    """The generalization is strict: equal weights and no captaincy give
    exactly effective_ownership / 100."""
    from gaffer.data.league import effective_ownership
    from gaffer.league_mode import cover_from_eo, cover_table

    picks = {11: [{"element": 1, "multiplier": 1},
                  {"element": 2, "multiplier": 1}],
             12: [{"element": 1, "multiplier": 1}],
             13: [{"element": 3, "multiplier": 1}]}
    equal = {e: 1 / 3 for e in picks}
    # effective_ownership rounds to one decimal place of a percent, so the
    # comparison is to that precision — 0.667 against 0.6666..., not exact.
    assert cover_table(picks, equal) == pytest.approx(
        cover_from_eo(effective_ownership(picks)), abs=0.01)


def test_captain_cover_counts_only_armbands():
    from gaffer.league_mode import captain_cover

    caps = captain_cover(PICKS, {11: 0.7, 12: 0.3})
    assert caps == {1: pytest.approx(0.7)}


def test_cover_from_eo_clamps_the_over_hundred_case():
    from gaffer.league_mode import cover_from_eo

    assert cover_from_eo({1: 180.0, 2: 40.0}) == {1: 1.0, 2: 0.4}
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_league_mode.py -k "threat or cover" -v`
Expected: FAIL — `ImportError: cannot import name 'cover_table'`, and the
`threat_weights` stub returns `{}` for every case.

- [ ] **Step 3: Implement the weights and the cover tables**

In `src/gaffer/league_mode.py`, add the constant next to the others:

```python
THREAT_SIGMAS = 3.0
"""Ahead: rivals more than this many sigma-root-W back are not threats."""
```

and replace the `threat_weights` stub with:

```python
def threat_weights(my_total: int, rivals: pd.DataFrame,
                   sigmas: dict[int, float], weeks_left: int,
                   params: LeagueParams | None = None) -> dict[int, float]:
    """rival entry -> threat weight, summing to 1.

    Behind, the relevant side is the leader alone: he is the win condition.
    Ahead, it is every rival within ``THREAT_SIGMAS`` normalized units behind
    me, softmaxed on ``-|gap_r| / (sigma_mr * sqrt(W))`` so a rival 200 points
    adrift contributes nothing. A rivals frame with no ``entry`` column (the
    report-only shape) yields no weights rather than raising.
    """
    p = params or LeagueParams()
    if rivals.empty or "entry" not in rivals.columns:
        return {}
    root = math.sqrt(max(1, weeks_left))
    fallback = _bounded(SIGMA_FALLBACK, p)
    scored = []
    for _, row in rivals.iterrows():
        entry, total = int(row["entry"]), int(row["total"])
        sigma = sigmas.get(entry, fallback)
        scored.append((entry, total, (my_total - total) / (sigma * root)))
    if max(total for _, total, _ in scored) > my_total:
        leader = max(scored, key=lambda s: s[1])
        return {leader[0]: 1.0}
    relevant = [s for s in scored if 0.0 <= s[2] <= THREAT_SIGMAS]
    if not relevant:
        nearest = min(scored, key=lambda s: abs(s[2]))
        return {nearest[0]: 1.0}
    shift = max(-s[2] for s in relevant)          # softmax, numerically safe
    exps = {s[0]: math.exp(-s[2] - shift) for s in relevant}
    total_exp = sum(exps.values())
    return {entry: value / total_exp for entry, value in exps.items()}


def cover_table(rival_picks: dict[int, list[dict]],
                weights: dict[int, float]) -> dict[int, float]:
    """element -> covered fraction in [0, 1] over the rivals that matter.

    ``own`` is 0 (benched or unowned), 1 (owned) or 2 (captained): captaincy
    counts double, and a triple captain is still 2. The sum is clamped to
    [0, 1] *after* weighting, exactly as ``min(EO%/100, 1)`` clamped league EO.
    With equal weights and no armbands this reduces to league EO / 100.
    """
    out: dict[int, float] = {}
    for entry, picks in rival_picks.items():
        weight = weights.get(int(entry))
        if not weight:
            continue
        for pick in picks:
            own = min(int(pick.get("multiplier", 0)), 2)
            if own <= 0:
                continue
            element = int(pick["element"])
            out[element] = out.get(element, 0.0) + weight * own
    return {element: min(value, 1.0) for element, value in out.items()}


def captain_cover(rival_picks: dict[int, list[dict]],
                  weights: dict[int, float]) -> dict[int, float]:
    """element -> weighted share of the threats who captain him."""
    out: dict[int, float] = {}
    for entry, picks in rival_picks.items():
        weight = weights.get(int(entry))
        if not weight:
            continue
        for pick in picks:
            if int(pick.get("multiplier", 0)) >= 2:
                element = int(pick["element"])
                out[element] = out.get(element, 0.0) + weight
    return {element: min(value, 1.0) for element, value in out.items()}


def cover_from_eo(eo_pct: dict[int, float]) -> dict[int, float]:
    """League EO percent -> the v1 cover fraction. The old tilt, one table
    away: it is what ``cover_table`` reduces to under equal weights."""
    return {key: min(float(value) / 100.0, 1.0)
            for key, value in eo_pct.items()}
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_league_mode.py -v`
Expected: PASS — the eleven new cases plus every earlier one, including
`test_leading_defends_against_the_nearest_threat_in_sigma_units` which now
receives real weights.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/league_mode.py tests/test_league_mode.py
git commit -m "feat: threat weights and observed-squad cover tables" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 6: `tilt_ep` v2 and the advise wiring

`tilt_ep`'s second argument becomes the cover table (a fraction in [0, 1])
instead of raw league-EO percent: `ep' = ep · (1 + lam · (1 − cover_p))`. The
call sites in `run_advise` keep their exact positions and their exact
left-hand sides; only what they are *given* changes.

**Files:**
- Modify: `src/gaffer/league_mode.py:44-58` (`tilt_ep`)
- Modify: `src/gaffer/advise.py:41-42` (import), `:525-551` (the league block)
- Test: `tests/test_league_mode.py:52-72` (rewrite four), `tests/test_advise.py` (append)

- [ ] **Step 1: Write the failing tilt tests**

In `tests/test_league_mode.py`, replace lines 52-72 (the four tilt tests) with:

```python
def test_tilt_zero_lambda_is_identity():
    ep_by = {(1, 5): 4.0, (2, 5): 4.0}
    assert tilt_ep(ep_by, {1: 0.9}, 0.0) == ep_by


def test_tilt_chasing_boosts_differentials():
    ep_by = {(1, 5): 4.0, (2, 5): 4.0}
    out = tilt_ep(ep_by, {1: 1.0, 2: 0.0}, 0.4)
    assert out[(1, 5)] == pytest.approx(4.0)          # fully covered: no boost
    assert out[(2, 5)] == pytest.approx(4.0 * 1.4)    # uncovered: full boost


def test_tilt_defending_penalizes_differentials():
    out = tilt_ep({(1, 5): 4.0, (2, 5): 4.0}, {1: 1.0, 2: 0.0}, -0.3)
    assert out[(1, 5)] == pytest.approx(4.0)
    assert out[(2, 5)] == pytest.approx(4.0 * 0.7)


def test_tilt_cover_above_one_is_clamped():
    """cover_table clamps already; tilt_ep clamps again so a hand-built or
    stale table can never invert the sign of the tilt."""
    out = tilt_ep({(1, 5): 4.0}, {1: 1.8}, 0.4)
    assert out[(1, 5)] == pytest.approx(4.0)


def test_tilt_v2_reduces_to_the_old_league_eo_formula():
    """The generalization is strict: cover_from_eo(EO%) through the new tilt
    is the number the v1 tilt produced from the same EO."""
    from gaffer.league_mode import cover_from_eo

    ep_by = {(1, 5): 4.0, (2, 5): 6.0}
    eo = {1: 90.0, 2: 10.0}
    out = tilt_ep(ep_by, cover_from_eo(eo), 0.4)
    assert out[(1, 5)] == pytest.approx(4.0 * (1 + 0.4 * (1 - 0.9)))
    assert out[(2, 5)] == pytest.approx(6.0 * (1 + 0.4 * (1 - 0.1)))
```

Also update `test_zero_lambda_reproduces_v1_solution` (line 82) so the EO map
it builds is a cover fraction:

```python
    # nonzero, non-uniform cover: an identity bug would perturb the pool.
    eo = {int(c): ((i * 37) % 150) / 100.0 for i, c in enumerate(pool["code"])}
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_league_mode.py -k tilt -v`
Expected: FAIL — `test_tilt_chasing_boosts_differentials` gets
`4.0 * (1 + 0.4 * (1 - 0.01))` because the old body divides by 100.

- [ ] **Step 3: Implement `tilt_ep` v2**

Replace `tilt_ep` in `src/gaffer/league_mode.py` with:

```python
def tilt_ep(ep_by: dict, cover: dict, lam: float) -> dict:
    """Tilted EP for MILP pool construction ONLY. Raw ep is what reports show.

    ``cover`` is the observed-squad cover table from :func:`cover_table`: a
    fraction in [0, 1] per player code, where 1 means "the rivals that matter
    all own him, or captain him". It is clamped again here so a stale or
    hand-built table can never invert the tilt. lam=0 returns an equal dict —
    the v1 points-max solution is reproduced exactly (regression-tested).
    """
    if lam == 0.0:
        return dict(ep_by)
    out = {}
    for key, ep in ep_by.items():
        code = key[0]
        covered = min(max(float(cover.get(code, 0.0)), 0.0), 1.0)
        out[key] = ep * (1 + lam * (1 - covered))
    return out
```

- [ ] **Step 4: Run them and see them pass**

Run: `uv run pytest tests/test_league_mode.py -v`
Expected: PASS — every tilt test including the reduction and the MILP
identity.

- [ ] **Step 5: Write the failing advise-wiring test**

Append to `tests/test_advise.py`:

```python
# --- v4d: the league block feeds cover, not raw EO -------------------------


def test_run_advise_builds_the_cover_table_inside_the_league_block():
    """The dial's inputs are assembled between fetch_rival_entries and
    tilt_ep, so the protected ordering is untouched and the pool still eats
    a tilted dict built from observed rival squads."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    strategy = src.index("compute_strategy(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < src.index("fetch_rival_history(") < strategy
    assert strategy < src.index("cover_table(") < tilt < pool
    assert "captain_cover(" in src
    assert "tilt_ep(ep_by, cover," in src


def test_run_advise_still_reports_league_eo_for_the_annotation_tables():
    """Cover drives the optimizer; the captain table, the alternatives and
    the threat board still speak in rival EO percent."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    assert "captain_table(ep_gw1, first.xi, league_eo)" in src
    assert "threat_board(ep_gw1, first.squad, league_eo)" in src
```

- [ ] **Step 6: Run it and see it fail**

Run: `uv run pytest tests/test_advise.py -k cover -v`
Expected: FAIL — `ValueError: substring not found` on `fetch_rival_history(`.

- [ ] **Step 7: Wire the league block**

In `src/gaffer/advise.py`, change the league import at lines 41-42 to:

```python
from gaffer.data.league import (effective_ownership, fetch_rival_entries,
                                fetch_rival_history, fetch_rival_picks)
```

and the `league_mode` import at line 48 to:

```python
from gaffer.league_mode import (LeagueParams, captain_cover, compute_strategy,
                                cover_table, tilt_ep, win_probability)
```

(Task 7 adds `captaincy_note` and `tilted_captaincy` to this same line, once
those two functions exist — importing them now would be an `ImportError`.)

Replace lines 525-551 — from `league_eo: dict[int, float] = {}` through the
`pool_ep = …` line — with:

```python
    league_eo: dict[int, float] = {}
    cover: dict[int, float] = {}
    cap_cover: dict[int, float] = {}
    rival_captains: dict[int, int] = {}
    rival_names: dict[int, str] = {}
    strat = None
    win_probs: list[dict] = []
    if cfg.league_id:
        try:
            rivals = fetch_rival_entries(client, cfg.league_id, cfg.entry_id)
            if not rivals.empty:
                rival_picks = fetch_rival_picks(
                    client, rivals["entry"].tolist(), gw - 1)
                eo_by_element = effective_ownership(rival_picks)
                code_of_element = dict(zip(players["element"], players["code"]))
                league_eo = {code_of_element[el]: v
                             for el, v in eo_by_element.items()
                             if el in code_of_element}
                entry = client.get_entry(cfg.entry_id)
                my_total = int(entry.get("summary_overall_points") or 0)
                history = fetch_rival_history(
                    client, [cfg.entry_id] + rivals["entry"].tolist(), gw - 1)
                strat = compute_strategy(
                    my_total, rivals, gw, history=history,
                    my_entry=cfg.entry_id,
                    params=LeagueParams.from_config(cfg))
                # Covering is computed from the squads the threats actually
                # own, then re-keyed from FPL element ids to player codes,
                # which is what the pool and every downstream table use.
                cover = {code_of_element[el]: v
                         for el, v in cover_table(
                             rival_picks, strat.cover_weights).items()
                         if el in code_of_element}
                cap_cover = {code_of_element[el]: v
                             for el, v in captain_cover(
                                 rival_picks, strat.cover_weights).items()
                             if el in code_of_element}
                rival_names = {int(r.entry): str(r.entry_name)
                               for r in rivals.itertuples()}
                for rival_entry, picks in rival_picks.items():
                    for pick in picks:
                        if int(pick.get("multiplier", 0)) >= 2:
                            element = int(pick["element"])
                            if element in code_of_element:
                                rival_captains[int(rival_entry)] = \
                                    code_of_element[element]
                win_probs = [
                    {"name": str(r.entry_name), "total": int(r.total),
                     "p_win": round(win_probability(my_total, int(r.total),
                                                    strat.weeks_left), 3)}
                    for r in rivals.itertuples()]
        except Exception as e:  # noqa: BLE001 — the league must never block advice
            print(f"league unavailable, continuing without: {e}")
            league_eo, strat, win_probs = {}, None, []
            cover, cap_cover = {}, {}
            rival_captains, rival_names = {}, {}

    pool_ep = tilt_ep(ep_by, cover, strat.lam if strat else 0.0)
```

- [ ] **Step 8: Run the protected suites**

Run: `uv run pytest tests/test_advise.py tests/test_assemble.py tests/test_odds.py -v`
Expected: PASS — the two new tests, the two protected ordering tests at
`tests/test_advise.py:74` and `:97` (nothing inserted contains `pool_ep`, and
everything inserted sits above `ep_gw1 =`), and the odds and calibration pins.

- [ ] **Step 9: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS — no regressions anywhere; `run_advise` is not otherwise
exercised end-to-end, which is why the source pins exist.

- [ ] **Step 10: Commit**

```bash
git add src/gaffer/league_mode.py src/gaffer/advise.py tests/test_league_mode.py tests/test_advise.py
git commit -m "feat: tilt_ep v2 on observed-squad cover, wired into advise" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 7: EO-aware captaincy at the advise captain-override seam

After the v4c-gated plan is fixed, the captain among the XI is re-picked by
tilted score: `cap_score_p = ep_p · (1 + lam · (1 − cap_cover_p))`. Authority
order, explicit: the v4c scenario plurality picks the candidate first; when
league mode is active and `lam ≠ 0` the tilted score over the final XI is the
last word. At `lam = 0` this is argmax raw EP, which is today's behaviour
exactly.

The report and the CLI show both picks whenever they differ, mirroring the
v4c raw-optimum treatment.

**Files:**
- Modify: `src/gaffer/league_mode.py` (append two functions)
- Modify: `src/gaffer/advise.py:20-30` (dataclasses import), `:108-130` (`Advice`), after `:630` (the seam), `:733-735` (the payload)
- Modify: `src/gaffer/cli.py:62-67`
- Modify: `src/gaffer/report/templates/report.html.j2:47`
- Test: `tests/test_league_mode.py`, `tests/test_advise.py`, `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing captaincy test**

Append to `tests/test_league_mode.py`:

```python
# --- v4d: EO-aware captaincy -----------------------------------------------

EP_OF = {1: 9.0, 2: 8.6, 3: 7.0}


def test_tilted_captaincy_at_zero_lambda_is_argmax_raw_ep():
    """The rail: with no tilt the armband is exactly where v4c put it."""
    from gaffer.league_mode import tilted_captaincy

    assert tilted_captaincy([3, 1, 2], EP_OF, {1: 1.0}, 0.0) == (1, 2)


def test_tilted_captaincy_chasing_prefers_the_uncaptained_ceiling():
    """Behind: a captain nobody relevant is captaining scores higher — the
    variance-seeking split the rank payoff implies."""
    from gaffer.league_mode import tilted_captaincy

    captain, vice = tilted_captaincy([1, 2, 3], EP_OF, {1: 1.0, 2: 0.0}, 0.4)
    assert captain == 2          # 8.6 * 1.4 = 12.04 beats 9.0 * 1.0
    assert vice == 1


def test_tilted_captaincy_defending_mirrors_the_threats_armband():
    from gaffer.league_mode import tilted_captaincy

    captain, _ = tilted_captaincy([1, 2, 3], EP_OF, {1: 1.0, 2: 0.0}, -0.3)
    assert captain == 1          # 9.0 * 1.0 beats 8.6 * 0.7


def test_tilted_captaincy_breaks_ties_on_raw_ep_then_code():
    """Determinism matters: two equal tilted scores must not depend on the
    order the XI came out of the MILP."""
    from gaffer.league_mode import tilted_captaincy

    ep = {5: 6.0, 6: 6.0}
    assert tilted_captaincy([6, 5], ep, {}, 0.4) == (5, 6)


def test_tilted_captaincy_of_a_one_man_xi_names_him_twice():
    from gaffer.league_mode import tilted_captaincy

    assert tilted_captaincy([1], EP_OF, {}, 0.4) == (1, 1)


def test_captaincy_note_names_the_threat_being_covered():
    from gaffer.league_mode import captaincy_note

    note = captaincy_note(-0.3, chosen=1, demoted=2,
                          rival_captains={11: 1, 12: 3},
                          weights={11: 0.8, 12: 0.2},
                          names={11: "Ten Hag Hive", 12: "Tail"})
    assert note == "covering Ten Hag Hive's armband"


def test_captaincy_note_names_the_threat_being_differed_from():
    from gaffer.league_mode import captaincy_note

    note = captaincy_note(0.4, chosen=2, demoted=1,
                          rival_captains={11: 1, 12: 1},
                          weights={11: 0.9, 12: 0.1},
                          names={11: "Ten Hag Hive", 12: "Tail"})
    assert note == "differential vs Ten Hag Hive"


def test_captaincy_note_is_empty_when_nothing_changed():
    from gaffer.league_mode import captaincy_note

    assert captaincy_note(0.0, 1, 1, {}, {}, {}) == ""
    assert captaincy_note(0.4, 1, 1, {11: 1}, {11: 1.0}, {11: "A"}) == ""


def test_captaincy_note_degrades_when_no_rival_captains_either_player():
    from gaffer.league_mode import captaincy_note

    assert captaincy_note(0.4, 2, 1, {}, {}, {}) == "differential vs the field"
    assert captaincy_note(-0.3, 2, 1, {}, {}, {}) == \
        "covering the field's armband"
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_league_mode.py -k "captaincy or captain_cover" -v`
Expected: FAIL — `ImportError: cannot import name 'tilted_captaincy'`.

- [ ] **Step 3: Implement the captaincy functions**

Append to `src/gaffer/league_mode.py`:

```python
def tilted_captaincy(xi: list[int], ep_of: dict[int, float],
                     cap_cover: dict[int, float],
                     lam: float) -> tuple[int, int]:
    """(captain, vice) over the final XI by tilted score.

    ``cap_score_p = ep_p * (1 + lam * (1 - cap_cover_p))``. Behind (lam > 0)
    an unowned armband scores higher; ahead (lam < 0) the threats' armband
    does. At lam = 0 this is argmax raw EP, exactly what v4c produced. Ties
    fall back to raw EP and then to the code, so the answer never depends on
    the order the MILP happened to list the XI in.
    """
    def score(code: int) -> float:
        covered = min(max(float(cap_cover.get(code, 0.0)), 0.0), 1.0)
        return float(ep_of.get(code, 0.0)) * (1 + lam * (1 - covered))

    ranked = sorted(xi, key=lambda c: (-score(c), -float(ep_of.get(c, 0.0)),
                                       int(c)))
    return ranked[0], (ranked[1] if len(ranked) > 1 else ranked[0])


def captaincy_note(lam: float, chosen: int, demoted: int,
                   rival_captains: dict[int, int], weights: dict[int, float],
                   names: dict[int, str]) -> str:
    """The half-sentence the report puts after the captain's name.

    Defending, the armband is covering the heaviest threat who owns it;
    chasing, it is a differential against the heaviest threat who captains
    the man we just demoted. Nothing at all when the tilt changed nothing.
    """
    if lam == 0.0 or chosen == demoted:
        return ""
    target = chosen if lam < 0 else demoted
    owners = [entry for entry, code in rival_captains.items()
              if code == target]
    if lam < 0:
        if not owners:
            return "covering the field's armband"
        who = max(owners, key=lambda e: weights.get(e, 0.0))
        return f"covering {names.get(who, 'a rival')}'s armband"
    if not owners:
        return "differential vs the field"
    who = max(owners, key=lambda e: weights.get(e, 0.0))
    return f"differential vs {names.get(who, 'a rival')}"
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_league_mode.py -v`
Expected: PASS — nine new cases plus everything earlier.

- [ ] **Step 5: Write the failing advise-seam test**

Append to `tests/test_advise.py`:

```python
def test_run_advise_re_picks_the_captain_after_the_plan_is_fixed():
    """Authority order: the v4c plurality picks a candidate, then the tilted
    score over the final XI is the last word. The seam therefore sits after
    the scenario block and before the chip block — and, like everything else
    inserted into run_advise, it never mentions the tilted pool."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    seam = src.index("tilted_captaincy(")
    chips = src.index("chip_pool = (build_pool(")   # note the paren: line 640
    assert src.index("coherent_plan(") < seam < chips
    assert "captaincy_note(" in src
    assert "pool_ep" not in src[seam:chips]


def test_advice_carries_the_demoted_captain_and_the_note():
    from gaffer.advise import Advice

    a = _bare_advice()
    assert a.captain_note is None
    assert a.demoted_captain is None
```

(`_bare_advice` is the existing helper at the top of the file.)

- [ ] **Step 6: Run it and see it fail**

Run: `uv run pytest tests/test_advise.py -k "re_picks or demoted" -v`
Expected: FAIL — `ValueError: substring not found` on `tilted_captaincy(`.

- [ ] **Step 7: Implement the seam**

In `src/gaffer/advise.py`, add `replace` to the dataclasses import:

```python
from dataclasses import asdict, dataclass, field, replace
```

and extend the `league_mode` import Task 6 rewrote to:

```python
from gaffer.league_mode import (LeagueParams, captain_cover, captaincy_note,
                                compute_strategy, cover_table, tilt_ep,
                                tilted_captaincy, win_probability)
```

Append two fields to the `Advice` dataclass, after `scenarios: dict | None = None`:

```python
    # --- v4d league mode ---------------------------------------------------
    # Both are None unless the league tilt actually moved the armband, so an
    # Advice built without a league is the object it always was.
    captain_note: str | None = None
    demoted_captain: dict | None = None
```

Insert this block immediately after the v4c scenario block (after the
`scenario_report = {...}` assignment ends, at `src/gaffer/advise.py:630`) and
before the chip comment block:

```python
    # --- EO-aware captaincy (spec 2026-08-26 §6) ---------------------------
    # The plurality above picks a candidate; when the league is live and the
    # dial is off zero, the tilted score over the *final* XI is the last
    # word. At lam = 0 tilted_captaincy is argmax raw EP, so v4c's armband
    # stands untouched and both report fields stay None.
    captain_note: str | None = None
    demoted_captain: dict | None = None
    if strat is not None and strat.lam:
        ep_of_gw = {code: ep_by.get((code, gw), 0.0) for code in first.xi}
        new_captain, new_vice = tilted_captaincy(list(first.xi), ep_of_gw,
                                                 cap_cover, strat.lam)
        if new_captain != first.captain:
            demoted_captain = {"code": int(first.captain),
                               "ep": round(float(ep_of_gw.get(
                                   first.captain, 0.0)), 2)}
            captain_note = captaincy_note(strat.lam, new_captain,
                                          int(first.captain), rival_captains,
                                          strat.cover_weights, rival_names)
            first = replace(first, captain=new_captain, vice=new_vice)
```

The demoted captain needs a name, which is only resolved later; add it right
after `name_of` is built (after `src/gaffer/advise.py:698`, the `pos_of = …`
line):

```python
    if demoted_captain is not None:
        demoted_captain["name"] = name_of.get(demoted_captain["code"],
                                              str(demoted_captain["code"]))
```

Finally add the two fields to the `Advice(...)` construction, after
`scenarios=scenario_report,`:

```python
        captain_note=captain_note,
        demoted_captain=demoted_captain,
```

- [ ] **Step 8: Run the advise suites**

Run: `uv run pytest tests/test_advise.py tests/test_report.py tests/test_web_advice.py -v`
Expected: PASS — the seam test, the field test, and both protected orderings.

- [ ] **Step 9: Write the failing CLI/report test**

Append to `tests/test_cli.py`:

```python
def test_advise_prints_the_captain_note_and_the_demoted_pick(tmp_path,
                                                             monkeypatch):
    """When the dial moves the armband both picks are shown, mirroring the
    v4c raw-optimum treatment."""
    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod
    from tests.test_v4c_degradation import _fixture_advice

    advice = _fixture_advice()
    advice.captain_note = "differential vs Ten Hag Hive"
    advice.demoted_captain = {"code": 9, "name": "Mohamed Salah", "ep": 8.8}

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: advice)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    out = runner.invoke(app, ["advise"]).output
    assert "Captain: Erling Haaland (differential vs Ten Hag Hive)" in out
    assert "Raw-EP captain: Mohamed Salah (8.8 xPts)" in out
```

(`runner` and `app` are already imported at the top of `tests/test_cli.py`.)

- [ ] **Step 10: Run it and see it fail**

Run: `uv run pytest tests/test_cli.py -k captain_note -v`
Expected: FAIL — the output has the plain `Captain: Erling Haaland | Vice: …`
line and no raw-EP line.

- [ ] **Step 11: Implement the CLI and template lines**

In `src/gaffer/cli.py`, replace lines 62-67 (the captain echo) with:

```python
    cap_pct = ""
    if advice.scenarios and advice.scenarios.get("captain_frequency"):
        cap_pct = (f" [{round(advice.scenarios['captain_frequency'] * 100)}"
                   "% of sims]")
    # Both conditional: with no league tilt this is byte-for-byte the v4c
    # line, which tests/test_v4c_degradation.py compares character by
    # character.
    note = f" ({advice.captain_note})" if advice.captain_note else ""
    typer.echo(f"Captain: {advice.captain['name']}{note} | "
               f"Vice: {advice.vice['name']}{cap_pct}")
    if advice.demoted_captain:
        typer.echo(f"Raw-EP captain: {advice.demoted_captain['name']} "
                   f"({advice.demoted_captain['ep']} xPts)")
```

In `src/gaffer/report/templates/report.html.j2`, replace line 47:

```jinja
<li>Captain: <strong>{{ a.captain.name }}</strong>
{%- if a.captain_note %} <span class="diff">{{ a.captain_note }}</span>{% endif %}
 · Vice: <strong>{{ a.vice.name }}</strong></li>
{% if a.demoted_captain %}<li class="muted">Raw-EP captain:
{{ a.demoted_captain.name }} ({{ a.demoted_captain.ep }} xPts)</li>{% endif %}
```

- [ ] **Step 12: Run it and see it pass**

Run: `uv run pytest tests/test_cli.py tests/test_report.py tests/test_v4c_degradation.py -v`
Expected: PASS — the new CLI test, and rail 1 in
`test_advise_prints_exactly_the_pre_v4c_block` still byte-identical because
both new fields are `None` on the fixture.

- [ ] **Step 13: Commit**

```bash
git add src/gaffer/league_mode.py src/gaffer/advise.py src/gaffer/cli.py src/gaffer/report/templates/report.html.j2 tests/test_league_mode.py tests/test_advise.py tests/test_cli.py
git commit -m "feat: EO-aware captaincy at the advise captain-override seam" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 8: `fetch_rival_picks_history` and the backtest tilt seam (gate E1 tooling)

Gate E1 replays 2025-26 GW20-38 with the dial on and off against the rivals'
*recorded* squads. Two pieces of tooling are needed, and only the tooling —
the replay itself is orchestrator-run.

1. `fetch_rival_picks_history(client, entries, season, gws)` — the recorded
   picks per rival per gameweek, cached **permanently** under
   `data/raw/league/{season}/` because they are historical facts.
2. An optional `tilt` hook on `run_backtest`, applied to `ep_by` immediately
   before `build_pool`. Default `None` is today's behaviour, byte-identical.

**Files:**
- Modify: `src/gaffer/data/league.py` (append)
- Modify: `src/gaffer/backtest.py:354-356` (signature), `:380-392` (docstring), `:470` (the hook)
- Test: `tests/test_league.py`, `tests/test_backtest.py` (append)

- [ ] **Step 1: Write the failing fetcher test**

Append to `tests/test_league.py`:

```python
# --- v4d: recorded rival picks for gate E1 ---------------------------------

from gaffer.data.league import fetch_rival_picks_history


def _picks_transport(calls: list):
    """entry/{id}/event/{gw}/picks/ for any entry; GW 3 is never public."""

    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.rstrip("/").split("/")
        entry, gw = int(parts[-4]), int(parts[-2])
        calls.append((entry, gw))
        if gw == 3:
            return httpx.Response(404, json={"detail": "Not found."})
        return httpx.Response(200, json={"picks": [
            {"element": entry * 10 + gw, "position": 1, "multiplier": 2}]})

    return httpx.MockTransport(handler)


def test_fetch_rival_picks_history_keys_on_entry_and_gameweek(tmp_path):
    calls: list = []
    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=_picks_transport(calls))
    out = fetch_rival_picks_history(client, [7, 8], season="2025-26",
                                    gws=[1, 2], raw_dir=tmp_path / "league")
    assert sorted(out) == [(7, 1), (7, 2), (8, 1), (8, 2)]
    assert out[(8, 2)][0]["element"] == 82


def test_fetch_rival_picks_history_skips_a_gameweek_that_is_not_public(
        tmp_path):
    calls: list = []
    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=_picks_transport(calls))
    out = fetch_rival_picks_history(client, [7], season="2025-26",
                                    gws=[2, 3], raw_dir=tmp_path / "league")
    assert sorted(out) == [(7, 2)]


def test_fetch_rival_picks_history_caches_permanently_per_season(tmp_path):
    """Recorded picks are facts: fetched once, then read off disk forever."""
    calls: list = []
    cache = tmp_path / "league"
    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=_picks_transport(calls))
    fetch_rival_picks_history(client, [7], season="2025-26", gws=[1],
                              raw_dir=cache)
    assert (cache / "2025-26" / "7-1.json").exists()
    assert calls == [(7, 1)]
    again = fetch_rival_picks_history(client, [7], season="2025-26", gws=[1],
                                      raw_dir=cache)
    assert calls == [(7, 1)]
    assert again[(7, 1)][0]["element"] == 71
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_league.py -k picks_history -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_rival_picks_history'`.

- [ ] **Step 3: Implement the fetcher**

Append to `src/gaffer/data/league.py`:

```python
def fetch_rival_picks_history(client: FPLClient, entries: list[int],
                              season: str, gws: list[int],
                              raw_dir: Path | str = RAW_LEAGUE
                              ) -> dict[tuple[int, int], list[dict]]:
    """(entry, gw) -> the squad that entry actually played that gameweek.

    Cached permanently under ``{raw_dir}/{season}/{entry}-{gw}.json``: a
    finished gameweek's picks are a historical fact and will never change,
    so a replay re-run costs no API calls at all. A gameweek an entry never
    played (joined late, private) is absent from the result rather than
    fatal.
    """
    base = Path(raw_dir) / season
    out: dict[tuple[int, int], list[dict]] = {}
    for entry in entries:
        for gw in gws:
            key = (int(entry), int(gw))
            path = base / f"{key[0]}-{key[1]}.json"
            if path.exists():
                out[key] = json.loads(path.read_text())
                continue
            try:
                picks = client.get_entry_picks(key[0], key[1])["picks"]
            except Exception:
                continue        # never played / not public — skip
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(picks))
            out[key] = picks
    return out
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_league.py -v`
Expected: PASS — three new tests plus everything from Task 2.

- [ ] **Step 5: Write the failing backtest-seam test**

Append to `tests/test_backtest.py`:

```python
# --- v4d: the league tilt seam gate E1 injects -----------------------------

def test_run_backtest_without_a_tilt_is_the_default_replay(monkeypatch):
    """Default None means today's behaviour, to the point."""
    import inspect

    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    default = run_backtest(season="2025-26", start_gw=1, retrain_every=4)
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    explicit = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                            tilt=None)
    assert explicit == default
    assert inspect.signature(run_backtest).parameters["tilt"].default is None


def test_run_backtest_applies_an_injected_tilt_before_the_pool_is_built(
        monkeypatch):
    """Gate E1 replays the dial by handing the loop a tilt; it has to reach
    the pool, which is what decides *which* players are candidates."""
    _install_stubs(monkeypatch, _season_rows([1, 2, 3]))
    seen: list[int] = []

    def tilt(ep_by, gw):
        seen.append(gw)
        return {key: value * 2 for key, value in ep_by.items()}

    out = run_backtest(season="2025-26", start_gw=1, retrain_every=4,
                       tilt=tilt)
    assert seen == [1, 2, 3]
    assert out["total"] > 0
```

- [ ] **Step 6: Run it and see it fail**

Run: `uv run pytest tests/test_backtest.py -k tilt -v`
Expected: FAIL — `TypeError: run_backtest() got an unexpected keyword argument 'tilt'`.

- [ ] **Step 7: Implement the hook**

In `src/gaffer/backtest.py`, change the signature at lines 354-356 to:

```python
def run_backtest(season: str = "2025-26", start_gw: int = 5,
                 retrain_every: int = 4, horizon: int = 1,
                 chips: bool = False, ep_source: str = "model",
                 tilt=None) -> dict:
```

Replace the docstring sentence at lines 384-388 —
"Two simplifications are worth being explicit about: the replay never applies
league tilt or availability filtering in either mode, …" — with:

```
    explicit about: the replay applies no availability filtering in either
    mode, and no league tilt unless one is injected, so an oracle run is
    clairvoyant about scores and no more privileged than the model run about
    news; and it skips model training altogether, since nothing reads the
    fitted components.

    ``tilt`` is the gate-E1 seam: an optional ``(ep_by, gw) -> ep_by``
    callable applied to the expected-points dict immediately before the pool
    is built, so a replayed league tilt shapes *which* players are candidates
    exactly as it does in ``advise``. ``None`` — the default — leaves the
    replay bit-identical to the pre-v4d one.
```

Immediately after line 470 (`ep_by = {(int(r.code), int(r.gw)): float(r.ep) …}`)
insert:

```python
        if tilt is not None:
            ep_by = tilt(ep_by, gw)
```

- [ ] **Step 8: Run it and see it pass**

Run: `uv run pytest tests/test_backtest.py -v`
Expected: PASS — the two new tests plus the protected pins at
`tests/test_backtest.py:520-552` (the calibration literal, the `chips`
default, `unplayed_chips`), which the edits leave untouched.

- [ ] **Step 9: Commit**

```bash
git add src/gaffer/data/league.py src/gaffer/backtest.py tests/test_league.py tests/test_backtest.py
git commit -m "feat: recorded rival picks and the backtest tilt seam for E1" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 9: `data/tier_eo.py` — the sampled top-10k EO

Sample `TIER_SAMPLE = 300` entries uniformly from the top 10k of the overall
classic league (league 314; standings pages are 50 entries each, so the first
200 pages are the top 10k), fetch each entry's picks for the live gameweek and
compute EO-with-captaincy plus a binomial standard error. Pages are fetched
once and re-used across every slot sampled from them, so one live session
costs at most ~306 calls through the existing throttled client. Cached per GW.

**Files:**
- Create: `src/gaffer/data/tier_eo.py`
- Test: `tests/test_tier_eo.py`

- [ ] **Step 1: Write the failing sampler test**

Create `tests/test_tier_eo.py`:

```python
"""Sampled top-10k effective ownership. No network: every call goes through
httpx.MockTransport wired into the real client."""

import json

import httpx

from gaffer.api.client import FPLClient
from gaffer.data.tier_eo import (MAX_PAGE, PAGE_SIZE, binomial_se,
                                 fetch_tier_entries, sample_slots,
                                 tier_eo_table)


def test_sample_slots_are_distinct_page_slot_pairs():
    slots = sample_slots(300, seed=1)
    assert len(slots) == 300
    assert len(set(slots)) == 300
    assert all(1 <= page <= MAX_PAGE and 0 <= slot < PAGE_SIZE
               for page, slot in slots)


def test_sample_slots_are_deterministic_for_a_seed():
    assert sample_slots(50, seed=7) == sample_slots(50, seed=7)
    assert sample_slots(50, seed=7) != sample_slots(50, seed=8)


def test_sample_slots_are_sorted_so_pages_are_fetched_once():
    slots = sample_slots(40, seed=3)
    assert slots == sorted(slots)


def _tier_transport(calls: list):
    """League 314 standings plus per-entry picks; 50 entries a page."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "leagues-classic" in path:
            page = int(request.url.params.get("page_standings", 1))
            calls.append(("page", page))
            return httpx.Response(200, json={"standings": {
                "has_next": True,
                "results": [{"entry": page * 1000 + slot}
                            for slot in range(PAGE_SIZE)]}})
        parts = path.rstrip("/").split("/")
        entry = int(parts[-4])
        calls.append(("picks", entry))
        # Everyone owns 1; every other entry captains him; nobody owns 2.
        return httpx.Response(200, json={"picks": [
            {"element": 1, "multiplier": 2 if entry % 2 == 0 else 1},
            {"element": 3, "multiplier": 0}]})

    return httpx.MockTransport(handler)


def test_fetch_tier_entries_reuses_a_page_across_its_slots(tmp_path):
    calls: list = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_tier_transport(calls))
    entries = fetch_tier_entries(client, [(1, 0), (1, 5), (2, 3)])
    assert entries == [1000, 1005, 2003]
    assert [c for c in calls if c[0] == "page"] == [("page", 1), ("page", 2)]


def test_tier_eo_table_counts_captaincy_and_reports_a_standard_error(tmp_path):
    calls: list = []
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_tier_transport(calls))
    out = tier_eo_table(client, gw=3, sample=4, seed=11,
                        raw_dir=tmp_path / "tier")
    assert out[1]["n"] == 4
    # Two of the four captain him, two own him: EO = (2*2 + 1*2) / 4 = 150%.
    assert out[1]["eo"] == 150.0
    # Ownership is 4/4, so the binomial SE collapses to zero.
    assert out[1]["se"] == 0.0
    assert 3 not in out                      # benched by everyone


def test_tier_eo_table_caches_per_gameweek(tmp_path):
    calls: list = []
    cache = tmp_path / "tier"
    client = FPLClient(raw_dir=tmp_path / "raw",
                       transport=_tier_transport(calls))
    first = tier_eo_table(client, gw=3, sample=4, seed=11, raw_dir=cache)
    picks_calls = len([c for c in calls if c[0] == "picks"])
    assert json.loads((cache / "3.json").read_text())
    second = tier_eo_table(client, gw=3, sample=4, seed=11, raw_dir=cache)
    assert len([c for c in calls if c[0] == "picks"]) == picks_calls
    assert second == first


def test_tier_eo_table_of_a_sample_nobody_answered_is_empty(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "leagues-classic" in request.url.path:
            return httpx.Response(200, json={"standings": {
                "has_next": True,
                "results": [{"entry": 1} for _ in range(PAGE_SIZE)]}})
        return httpx.Response(404, json={"detail": "Not found."})

    client = FPLClient(raw_dir=tmp_path / "raw", retries=1,
                       transport=httpx.MockTransport(handler))
    assert tier_eo_table(client, gw=3, sample=2, seed=1,
                         raw_dir=tmp_path / "tier") == {}


def test_binomial_se_is_the_textbook_formula():
    assert binomial_se(0.5, 100) == 5.0        # sqrt(.25/100) * 100
    assert binomial_se(0.0, 100) == 0.0
    assert binomial_se(0.5, 0) == 0.0
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_tier_eo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gaffer.data.tier_eo'`.

- [ ] **Step 3: Implement the module**

Create `src/gaffer/data/tier_eo.py`:

```python
"""Tier-resolved effective ownership: what the top 10k actually own.

League EO says what my rivals own; ``selected_by_percent`` says what the
whole game owns. Neither is what a good manager is measured against, which
is the top of the pyramid. This module samples it: 300 entries drawn
uniformly from the first 200 standings pages of the overall classic league
(50 entries a page = the top 10,000), each entry's live picks fetched once.

Display only — the live tracker renders it and nothing else reads it. Every
failure mode (rate limit, page shape change, a private entry) degrades to
fewer samples or to an empty table, never to an exception that would take
the tracker down.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

TIER_LEAGUE = 314
"""The overall classic league every entry is in."""

PAGE_SIZE = 50
MAX_PAGE = 200
"""200 pages x 50 entries = the top 10,000."""

TIER_SAMPLE = 300
TIER_SEED = 20260826
RAW_TIER = Path("data/raw/tier_eo")


def sample_slots(n: int, seed: int, max_page: int = MAX_PAGE,
                 page_size: int = PAGE_SIZE) -> list[tuple[int, int]]:
    """``n`` distinct (page, slot) pairs, uniform over the tier, sorted.

    Sorted so that the caller fetches each page once and reads every slot it
    sampled from it — the difference between ~306 API calls and ~600.
    """
    universe = [(page, slot) for page in range(1, max_page + 1)
                for slot in range(page_size)]
    return sorted(random.Random(seed).sample(universe, min(n, len(universe))))


def fetch_tier_entries(client, slots: list[tuple[int, int]]) -> list[int]:
    """Entry ids at those (page, slot) positions; each page fetched once."""
    by_page: dict[int, list[dict]] = {}
    entries: list[int] = []
    for page, slot in slots:
        if page not in by_page:
            try:
                data = client.get_league_standings(TIER_LEAGUE, page)
                by_page[page] = data["standings"]["results"]
            except Exception:
                by_page[page] = []      # a page that will not load is skipped
        results = by_page[page]
        if slot < len(results):
            entries.append(int(results[slot]["entry"]))
    return entries


def binomial_se(p: float, n: int) -> float:
    """Standard error of an ownership proportion, in percentage points."""
    if n <= 0:
        return 0.0
    return math.sqrt(max(p * (1 - p), 0.0) / n) * 100


def tier_eo_table(client, gw: int, sample: int = TIER_SAMPLE,
                  seed: int = TIER_SEED,
                  raw_dir: Path | str = RAW_TIER) -> dict[int, dict]:
    """element -> {"eo", "se", "n"} for the sampled tier, cached per GW.

    ``eo`` is effective ownership in percent (captaincy counts double, the
    bench counts zero), so it can exceed 100. ``se`` is the binomial standard
    error of plain *ownership* at this sample size — the honest error bar for
    a sample, and the reason the tracker prints it next to the number.
    """
    path = Path(raw_dir) / f"{int(gw)}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        return {int(key): value for key, value in cached.items()}
    entries = fetch_tier_entries(client, sample_slots(sample, seed + int(gw)))
    owners: dict[int, int] = {}
    multipliers: dict[int, int] = {}
    n = 0
    for entry in entries:
        try:
            picks = client.get_entry_picks(int(entry), int(gw))["picks"]
        except Exception:
            continue        # private or missing entry — one fewer sample
        n += 1
        for pick in picks:
            multiplier = int(pick.get("multiplier", 0))
            if multiplier <= 0:
                continue
            element = int(pick["element"])
            owners[element] = owners.get(element, 0) + 1
            multipliers[element] = multipliers.get(element, 0) + multiplier
    if not n:
        return {}
    out = {element: {"eo": round(total / n * 100, 1),
                     "se": round(binomial_se(owners[element] / n, n), 1),
                     "n": n}
           for element, total in multipliers.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): v for k, v in out.items()}))
    return out
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_tier_eo.py -v`
Expected: PASS — all nine tests.

- [ ] **Step 5: Commit**

```bash
git add src/gaffer/data/tier_eo.py tests/test_tier_eo.py
git commit -m "feat: sampled top-10k effective ownership" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 10: Tier-EO columns on the live tracker, with graceful degradation

The live tracker's player table (`src/gaffer/web/routers/live.py:93-109`, the
only per-player table the tracker has) gains two columns: `top10k EO ±se` and
the overall `selected_by_percent` already carried on the players snapshot
(`SNAPSHOT_PLAYER_COLS`, `src/gaffer/artifacts.py:49`). Failure anywhere
degrades to the current table plus a one-line notice; the tracker never blocks
on tier EO.

**Files:**
- Modify: `src/gaffer/web/schemas.py:172-191` (`LivePlayer`, `LiveState`)
- Modify: `src/gaffer/web/routers/live.py:1-20` (imports), `:93-133`
- Modify: `frontend/src/types.ts:251-279`, `frontend/src/pages/Live.tsx:64-86`
- Test: `tests/test_web_live.py`, `frontend/src/pages/Live.test.tsx`

- [ ] **Step 1: Write the failing API test**

Append to `tests/test_web_live.py`:

```python
# --- v4d: tier-resolved EO -------------------------------------------------

def test_live_players_carry_tier_eo_and_overall_ownership(tmp_path,
                                                          monkeypatch):
    """The tracker's player table gains the top-10k sample and the overall
    ownership already on the snapshot."""
    import gaffer.web.routers.live as live_mod

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {
                            7: {"eo": 143.5, "se": 2.1, "n": 300}})

    body = TestClient(create_app()).get("/api/live").json()
    salah = next(p for p in body["players"] if p["element"] == 7)
    assert salah["tier_eo"] == 143.5
    assert salah["tier_eo_se"] == 2.1
    assert salah["selected_by_percent"] == 45.0
    assert body["notice"] is None
    dud = next(p for p in body["players"] if p["element"] == 8)
    assert dud["tier_eo"] is None          # not in the sample: no number


def test_live_degrades_to_a_notice_when_tier_eo_fails(tmp_path, monkeypatch):
    """Rate limit, page shape change, anything: the tracker still renders."""
    import gaffer.web.routers.live as live_mod

    def _boom(client, gw, sample=300):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table", _boom)

    body = TestClient(create_app()).get("/api/live").json()
    assert body["active"] is True
    assert body["players"][0]["tier_eo"] is None
    assert "top-10k EO unavailable" in body["notice"]


def test_live_skips_tier_eo_entirely_when_it_is_switched_off(tmp_path,
                                                             monkeypatch):
    import gaffer.web.routers.live as live_mod

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)                       # writes the players snapshot too
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n[league]\ntier_eo = false\n')

    def _boom(client, gw, sample=300):
        raise AssertionError("tier EO fetched with tier_eo = false")

    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table", _boom)

    body = TestClient(create_app()).get("/api/live").json()
    assert body["notice"] is None
    assert body["players"][0]["tier_eo"] is None
```

`_config(tmp_path)` is the existing helper at `tests/test_web_live.py:60`; it
writes `config.toml` *and* `data/live/players.parquet`, and every test in the
file `monkeypatch.chdir(tmp_path)` first. The third test overwrites only the
config afterwards, so the snapshot survives.

The existing `test_live_between_gameweeks_is_a_quiet_inactive_payload`
(`tests/test_web_live.py:115`) compares the inactive payload as a whole dict,
so it gains the new key deliberately — edit its literal to:

```python
    assert body == {"active": False, "gw": None, "my_points": 0,
                    "matches_in_play": 0, "players": [], "table": [],
                    "notice": None}
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/test_web_live.py -k tier -v`
Expected: FAIL — `AttributeError: module 'gaffer.web.routers.live' has no
attribute 'tier_eo_table'`.

- [ ] **Step 3: Implement the schema, the router and the notice**

In `src/gaffer/web/schemas.py`, replace `LivePlayer` (lines 172-181) with:

```python
class LivePlayer(BaseModel):
    element: int
    code: int
    name: str
    position: str
    multiplier: int
    points: int
    provisional_bonus: int
    minutes: int
    status: Literal["played", "playing", "yet to play"]
    # v4d: display only, and all three optional — a tracker with no tier
    # sample renders exactly the table it rendered before.
    tier_eo: float | None = None
    tier_eo_se: float | None = None
    selected_by_percent: float | None = None
```

and add to `LiveState` (after its existing fields):

```python
    notice: str | None = None
```

In `src/gaffer/web/routers/live.py`, add to the imports:

```python
from gaffer.data.tier_eo import tier_eo_table
```

Insert before the `players = []` loop (after `by_element = {...}` at line 94):

```python
    # Tier EO is a display column, never a blocker: any failure leaves the
    # table exactly as it was plus a one-line notice.
    tier: dict[int, dict] = {}
    notice: str | None = None
    if getattr(cfg, "tier_eo", True):
        try:
            tier = tier_eo_table(client, gw, sample=cfg.tier_sample)
        except Exception as exc:  # noqa: BLE001 — network, JSON, page drift
            notice = f"top-10k EO unavailable ({exc}) — league EO only"
```

Replace the `players.append(LivePlayer(...))` call with:

```python
        sampled = tier.get(element) or {}
        players.append(LivePlayer(
            element=element, code=int(row.code), name=str(row.name),
            position=str(row.position),
            multiplier=int(pick.get("multiplier", 0)),
            points=int(points_of.get(element, 0)),
            provisional_bonus=int(bonus.get(element, 0)),
            minutes=minutes, status=_status(minutes, not team_done),
            tier_eo=sampled.get("eo"), tier_eo_se=sampled.get("se"),
            selected_by_percent=(float(row.selected_by_percent)
                                 if getattr(row, "selected_by_percent", None)
                                 is not None else None)))
```

and the final return with:

```python
    return LiveState(active=True, gw=gw, my_points=my_points,
                     matches_in_play=in_play, players=players, table=table,
                     notice=notice)
```

- [ ] **Step 4: Run it and see it pass**

Run: `uv run pytest tests/test_web_live.py tests/test_web_smoke.py tests/test_web_meta.py -v`
Expected: PASS — the three new tests and every existing live/meta test
(the new schema fields are optional, so the OpenAPI snapshot tests that check
required fields do not move).

- [ ] **Step 5: Write the failing frontend test**

In `frontend/src/pages/Live.test.tsx`, extend `ACTIVE`'s player and add two
cases at the end of the `describe` block:

```tsx
const ACTIVE = {
  active: true, gw: 3, my_points: 66, matches_in_play: 2,
  players: [{ element: 7, code: 100, name: 'Salah', position: 'MID',
              multiplier: 2, points: 9, provisional_bonus: 3, minutes: 90,
              status: 'playing', tier_eo: 143.5, tier_eo_se: 2.1,
              selected_by_percent: 45 }],
  table: [{ entry: 1, name: 'You', pre_total: 106, live: 66, projected: 172,
            delta: 1 }],
  notice: null,
}

const NO_TIER = {
  ...ACTIVE,
  players: [{ ...ACTIVE.players[0], tier_eo: null, tier_eo_se: null,
              selected_by_percent: null }],
  notice: 'top-10k EO unavailable (429) — league EO only',
}
```

```tsx
  it('shows the sampled top-10k EO with its error bar', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('Top 10k EO')).toBeInTheDocument()
    expect(screen.getByText('143.5% ±2.1')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('renders the table and a notice when tier EO is unavailable', async () => {
    apiGet.mockResolvedValue(NO_TIER)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getAllByText('–').length).toBeGreaterThan(0)
    expect(screen.getByText(/top-10k EO unavailable/)).toBeInTheDocument()
  })
```

- [ ] **Step 6: Run it and see it fail**

Run: `cd frontend && npx vitest run src/pages/Live.test.tsx`
Expected: FAIL — `Unable to find an element with the text: Top 10k EO`.

- [ ] **Step 7: Implement the frontend columns**

In `frontend/src/types.ts`, extend `LivePlayer` (lines 251-261):

```ts
export interface LivePlayer {
  element: number
  code: number
  name: string
  position: string
  multiplier: number
  points: number
  provisional_bonus: number
  minutes: number
  status: 'played' | 'playing' | 'yet to play'
  tier_eo?: number | null
  tier_eo_se?: number | null
  selected_by_percent?: number | null
}
```

and add to `LiveState` (the interface holding `players` and `table`):

```ts
  notice?: string | null
```

In `frontend/src/pages/Live.tsx`, replace the player table header and body
(lines 64-85) with:

```tsx
          <thead>
            <tr>
              <th>Player</th><th>Pts</th><th>Bonus</th><th>Mins</th>
              <th>Status</th><th>Top 10k EO</th><th>Owned</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((player) => (
              <tr key={player.element}>
                <td>
                  <PlayerName code={player.code} name={player.name} />
                  {player.multiplier > 1 && ' (C)'}
                </td>
                <td>{player.points}</td>
                <td>{player.provisional_bonus > 0
                  ? `+${player.provisional_bonus}` : '–'}</td>
                <td>{player.minutes}</td>
                <td className="muted">{player.status}</td>
                <td>{player.tier_eo == null ? '–'
                  : `${player.tier_eo}% ±${player.tier_eo_se ?? 0}`}</td>
                <td>{player.selected_by_percent == null ? '–'
                  : `${player.selected_by_percent}%`}</td>
              </tr>
            ))}
          </tbody>
```

and add the notice immediately above that table's `<table>` element:

```tsx
        {data.notice && <p className="muted">{data.notice}</p>}
```

- [ ] **Step 8: Run it and see it pass**

Run: `cd frontend && npx vitest run src/pages/Live.test.tsx`
Expected: PASS — both new cases and the three pre-existing ones.

- [ ] **Step 9: Commit**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/live.py frontend/src/types.ts frontend/src/pages/Live.tsx frontend/src/pages/Live.test.tsx tests/test_web_live.py
git commit -m "feat: top-10k EO columns on the live tracker" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Task 11: The v4d degradation rail

Everything v4d adds has to be *provably invisible* at `lam = 0`, not merely
"off by default". This is the same exercise `tests/test_v4c_degradation.py`
performs for the scenario layer, in its own file so a failure names the cycle
that broke it.

**Files:**
- Create: `tests/test_v4d_degradation.py`

- [ ] **Step 1: Write the rail**

Create `tests/test_v4d_degradation.py`:

```python
"""The v4d degradation rail.

Four things are pinned:

1. ``tilt_ep`` at lam = 0 returns the input values unchanged, whatever the
   cover table says.
2. ``tilted_captaincy`` at lam = 0 is argmax raw EP — the v4c armband.
3. ``gaffer advise``'s printed block with no league is character-for-character
   what v4c printed. This re-runs the v4c rail after the CLI grew two
   conditional lines, which is the whole point.
4. The protected source-text orderings inside ``run_advise`` still hold, and
   nothing v4d inserted mentions the tilted pool.

If a later task legitimately changes one of these, that task's *gate* says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pytest

from gaffer.league_mode import (Strategy, compute_strategy, tilt_ep,
                                tilted_captaincy)


# --- rail 1: the tilt is the identity at lam = 0 ---------------------------

def test_tilt_at_zero_lambda_returns_the_same_values():
    ep_by = {(1, 5): 4.0, (2, 5): 7.25, (3, 6): 0.0}
    cover = {1: 1.0, 2: 0.35, 3: 0.0}
    out = tilt_ep(ep_by, cover, 0.0)
    assert out == ep_by
    assert all(out[key] is ep_by[key] or out[key] == ep_by[key]
               for key in ep_by)


def test_tilt_at_zero_lambda_ignores_a_nonsense_cover_table():
    ep_by = {(1, 5): 4.0}
    assert tilt_ep(ep_by, {1: 17.5}, 0.0) == ep_by
    assert tilt_ep(ep_by, {}, 0.0) == ep_by


# --- rail 2: the armband does not move at lam = 0 --------------------------

def test_captaincy_at_zero_lambda_is_the_raw_ep_argmax():
    ep_of = {1: 9.0, 2: 8.6, 3: 7.0}
    for cover in ({}, {1: 1.0}, {2: 1.0, 3: 0.5}):
        assert tilted_captaincy([3, 2, 1], ep_of, cover, 0.0) == (1, 2)


def test_a_neutral_strategy_leaves_lambda_at_exactly_zero():
    """The dial's own rail: a dead heat is 0.0, not 1e-17."""
    import pandas as pd

    rivals = pd.DataFrame({"entry": [11], "entry_name": ["Level"],
                           "total": [500]})
    s = compute_strategy(500, rivals, 20)
    assert s.lam == 0.0
    assert isinstance(s, Strategy)
    assert tilt_ep({(1, 20): 5.0}, {1: 0.9}, s.lam) == {(1, 20): 5.0}


# --- rail 3: the printed advise block --------------------------------------

def test_the_no_league_advise_output_is_still_byte_identical(tmp_path,
                                                             monkeypatch):
    """Re-run the v4c rail now that the captain line has two conditional
    fragments. With no league both are absent and the block is unchanged."""
    from tests.test_v4c_degradation import (
        test_advise_prints_exactly_the_pre_v4c_block)

    test_advise_prints_exactly_the_pre_v4c_block(tmp_path, monkeypatch)


# --- rail 4: the protected source-text seams -------------------------------

def test_the_advise_seams_still_hold_after_v4d():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    strategy = src.index("compute_strategy(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < strategy < tilt < pool
    assert "build_pool(players, pool_ep," in src
    assert "except Exception" in src
    assert "summary_overall_points" in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]


def test_nothing_v4d_inserted_reads_the_tilted_pool():
    """cover, cap_cover and the captaincy seam all read ep_by. A tilted
    number on a printed table would be a lie, and the pool is the only
    consumer of the tilt."""
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    for marker in ("cover_table(", "captain_cover(", "tilted_captaincy("):
        line_start = src.rindex("\n", 0, src.index(marker)) + 1
        line_end = src.index("\n", src.index(marker))
        assert "pool_ep" not in src[line_start:line_end]
    assert src.count("pool_ep = tilt_ep(") == 1
```

- [ ] **Step 2: Run it and see it fail (or pass for the right reason)**

Run: `uv run pytest tests/test_v4d_degradation.py -v`
Expected: PASS on all eight — every implementation this rail covers landed in
Tasks 4-7. If any fails, the failure is a real v4d regression in that task's
code and must be fixed there, not here.

- [ ] **Step 3: Run the entire suite**

Run: `uv run pytest -q && cd frontend && npx vitest run`
Expected: PASS — the whole Python suite and the whole frontend suite.

- [ ] **Step 4: Commit**

```bash
git add tests/test_v4d_degradation.py
git commit -m "test: the v4d lam=0 degradation rail" \
  -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" \
  -m "Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi"
```

---

## Gate E1 — orchestrator-run, not a task in this plan

Tasks 2, 8 and 6 build everything the gate needs and nothing more:

- `fetch_rival_history(client, entries, gw, raw_dir)` — per-GW cached points
  series, for σ.
- `fetch_rival_picks_history(client, entries, season, gws, raw_dir)` — the
  recorded 2025-26 squads, permanently cached under
  `data/raw/league/2025-26/`.
- `run_backtest(..., tilt=None)` — the injection point; `tilt(ep_by, gw)` is
  applied immediately before `build_pool`, so a replayed dial shapes the
  candidate pool exactly as it does in `advise`.
- `compute_strategy`, `threat_weights`, `cover_table` and `tilt_ep` — the
  dial itself, callable with an arbitrary injected gap.

**The replay is not run by this plan.** The orchestrator runs E1 with a
throwaway driver (as it did for D1): replay 2025-26 GW20-38 dial-ON vs
dial-OFF (`tilt=None`), rivals scoring their recorded actual points, with
injected starting gaps at GW20 of {−60, −30, −10, 0, +10, +30, +60} relative
to the recorded leader, measuring final rank-1 indicator and final margin per
gap. E1 passes when dial-ON wins ≥ dial-OFF wins across the grid, **and**
dial-ON total points at gap 0 are within 15 of dial-OFF, **and** the z = 0
path is byte-identical (Task 11's rail). Per the project rule, a failing half
ships behind `lam = 0` with the negative result recorded in the design doc's
§12.

No implementer subagent should write a replay driver, add a CLI command for
it, or commit anything under `data/`.
