# FPL ML Advisor ("gaffer") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `gaffer` CLI that predicts FPL points with component-based LightGBM models and recommends transfers/captain/chips via a multi-period MILP, per the approved spec at `docs/superpowers/specs/2026-08-23-fpl-ml-advisor-design.md`.

**Architecture:** Five file-connected stages: refresh (FPL API + historical datasets → parquet) → features (leakage-safe rolling windows) → predict (minutes model + per-component models assembled with the official scoring table into an E[pts] matrix) → optimize (multi-period MILP over 6 GWs with FT banking, hits, chips) → report (terminal action list + Jinja2 HTML). Validation is a 2025/26 season replay.

**Tech Stack:** Python 3.12, `uv`, pandas + pyarrow, LightGBM, scikit-learn, PuLP + HiGHS (`highspy`), httpx, Typer, Jinja2, pytest.

---

## Before you begin (one-time, manual)

1. **Rename the project directory** — it currently has a trailing space, which will break tooling:
   ```bash
   mv "/Users/anugnana/Library/Projects/FPL " "/Users/anugnana/Library/Projects/FPL"
   ```
   Then re-open the Claude Code session / terminal in the renamed directory. All paths below assume `/Users/anugnana/Library/Projects/FPL`.
2. **Install uv** if missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. **macOS + LightGBM:** if `import lightgbm` fails with an OpenMP error, run `brew install libomp`.
4. **User inputs needed before Task 20 (advise):** the user's FPL entry ID and mini-league ID for `config.toml`. (Entry ID: visible in the URL on the Points page, `fantasy.premierleague.com/entry/<ID>/event/1`; league ID: in the league page URL.)

## Deviations from the spec (small, deliberate — flag to user at review)

1. **Team strength = our own Elo** computed from historical match results (~30 lines, covers ALL training seasons uniformly) instead of FPL-Core-Insights Elo (which only covers 2024-25+ and adds a fragile dependency). Core-Insights is dropped from v1 entirely; spec §9 already requires the pipeline to run on the FPL API alone.
2. **Set-piece/penalty order** is not a trained feature (only available live, not historically → train/serve skew). The report surfaces penalty-taker info textually instead.
3. **Bench weights in the MILP objective are uniform** (0.10 for all 4 bench slots) rather than per-slot — per-slot requires bench-order assignment variables for marginal gain. Bench *order advice* in the report is simply bench sorted by E[pts] (GK last), which is the actual decision output.
4. **Backtest v1 excludes chips** (conservative — understates the tool's season score) and uses simplified autosubs. Documented in Task 23.

## File structure

```
src/gaffer/
  __init__.py
  config.py                 # Config dataclass ← config.toml
  api/client.py             # FPLClient: all endpoints, retries, snapshots
  api/parse.py              # string→number helpers
  data/store.py             # parquet save/load under data/
  data/bootstrap.py         # bootstrap → players/teams/events/scoring tables
  data/live.py              # element-summary → current-season player_gw
  data/history.py           # vaastav CSVs → historical player_gw (2022-23..2025-26)
  data/elo.py               # team Elo from match results
  data/entry.py             # my team: picks, bank, sell prices, free transfers
  data/league.py            # rival picks, league effective ownership
  features/engineer.py      # rolling-window features + prediction frame
  models/persistence.py     # save/load model artifacts with metadata
  models/minutes.py         # P(play), P(60+), availability overrides
  models/team.py            # team_gw builder, P(CS), E[goals conceded]
  models/attacking.py       # per-position E[goals], E[assists]
  models/components.py      # defcon, saves, bonus, cards
  models/assemble.py        # components + scoring table → EP matrix + P(haul)
  models/train.py           # train-all + benchmark evaluation
  optimize/milp.py          # multi-period MILP (PuLP/HiGHS)
  optimize/chips.py         # WC/BB/TC/FH scenario evaluation
  optimize/differentials.py # captain table, alternatives, threat board
  prices.py                 # price-watch from official predictor fields
  advise.py                 # orchestration → Advice payload + predictions log
  tracking.py               # predicted-vs-actual model health
  backtest.py               # 2025/26 season replay
  report/render.py          # HTML report
  report/templates/report.html.j2
  cli.py                    # Typer app
tests/                      # one test file per module, same stem
scripts/                    # launchd install
```

**Phases & milestone gates** — pause for user review after **Task 15** (model quality vs benchmarks) and after **Task 23** (backtest results):

- Phase A: Foundation (Tasks 1–2)
- Phase B: Data layer (Tasks 3–8)
- Phase C: Prediction (Tasks 9–15) → **gate: model report**
- Phase D: Decisions (Tasks 16–19)
- Phase E: Product (Tasks 20–22)
- Phase F: Validation & ops (Tasks 23–25) → **gate: backtest report**

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `src/gaffer/__init__.py`, `config.toml`, `.gitignore`, `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "gaffer"
version = "0.1.0"
description = "FPL ML advisor: predictions, transfers, captaincy, chips"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pandas>=2.2",
    "pyarrow>=16",
    "lightgbm>=4.3",
    "scikit-learn>=1.5",
    "pulp>=2.8",
    "highspy>=1.7",
    "typer>=0.12",
    "jinja2>=3.1",
    "tomli-w>=1.0",
]

[project.scripts]
gaffer = "gaffer.cli:main"

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gaffer"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package + config template + .gitignore**

`src/gaffer/__init__.py`: empty file. `tests/__init__.py`: empty file.

`config.toml`:
```toml
[fpl]
entry_id = 0        # REQUIRED before `gaffer advise` — user's FPL team ID
league_id = 0       # REQUIRED for rival tracking — mini-league ID

[optimizer]
horizon = 6
decay = 0.85
vice_weight = 0.1
bench_weight = 0.10
ft_value = 1.5
itb_value = 0.05    # points per 1.0m in the bank at horizon end
hit_cost = 4

[data]
train_seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]
current_season = "2026-27"
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
data/raw/
data/history/
data/live/
models/*.joblib
models/*.json
reports/*.html
reports/*.json
.DS_Store
```

- [ ] **Step 3: Create config loader with test.** `tests/test_config.py`:

```python
from pathlib import Path
from gaffer.config import load_config

def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[fpl]\nentry_id = 123\nleague_id = 456\n'
        '[optimizer]\nhorizon = 6\ndecay = 0.85\nvice_weight = 0.1\n'
        'bench_weight = 0.1\nft_value = 1.5\nitb_value = 0.05\nhit_cost = 4\n'
        '[data]\ntrain_seasons = ["2022-23"]\ncurrent_season = "2026-27"\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.entry_id == 123
    assert cfg.horizon == 6
    assert cfg.train_seasons == ["2022-23"]
```

- [ ] **Step 4: Run test to verify it fails.** Run: `uv run pytest tests/test_config.py -v` — Expected: FAIL (`ModuleNotFoundError: gaffer.config`)

- [ ] **Step 5: Implement `src/gaffer/config.py`**

```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Config:
    entry_id: int
    league_id: int
    horizon: int = 6
    decay: float = 0.85
    vice_weight: float = 0.1
    bench_weight: float = 0.10
    ft_value: float = 1.5
    itb_value: float = 0.05
    hit_cost: int = 4
    train_seasons: list[str] = field(default_factory=list)
    current_season: str = "2026-27"

def load_config(path: Path | str = "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text())
    return Config(
        entry_id=raw["fpl"]["entry_id"],
        league_id=raw["fpl"]["league_id"],
        **raw.get("optimizer", {}),
        **raw.get("data", {}),
    )
```

- [ ] **Step 6: Run test to verify it passes.** Run: `uv run pytest tests/test_config.py -v` — Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: project scaffold with uv, config loader"
```

### Task 2: API parsing helpers + FPL client

**Files:**
- Create: `src/gaffer/api/__init__.py` (empty), `src/gaffer/api/parse.py`, `src/gaffer/api/client.py`
- Test: `tests/test_parse.py`, `tests/test_client.py`

- [ ] **Step 1: Write failing tests for parse helpers.** `tests/test_parse.py`:

```python
from gaffer.api.parse import to_float, to_int

def test_to_float_parses_api_strings():
    assert to_float("4.5") == 4.5
    assert to_float("") is None
    assert to_float(None) is None
    assert to_float("abc") is None
    assert to_float(3) == 3.0

def test_to_int():
    assert to_int("7") == 7
    assert to_int(None, default=0) == 0
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_parse.py -v` — Expected: FAIL (module missing)

- [ ] **Step 3: Implement `src/gaffer/api/parse.py`**

```python
from __future__ import annotations

def to_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def to_int(v, default=None):
    f = to_float(v)
    return default if f is None else int(f)
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_parse.py -v` — Expected: PASS

- [ ] **Step 5: Write failing client test** (uses `httpx.MockTransport` — no network). `tests/test_client.py`:

```python
import json
import httpx
from gaffer.api.client import FPLClient

def _transport(payload):
    def handler(request):
        return httpx.Response(200, json=payload)
    return httpx.MockTransport(handler)

def test_get_bootstrap_returns_json_and_snapshots(tmp_path):
    client = FPLClient(raw_dir=tmp_path, transport=_transport({"events": []}))
    data = client.get_bootstrap()
    assert data == {"events": []}
    snaps = list(tmp_path.glob("bootstrap-*.json"))
    assert len(snaps) == 1
    assert json.loads(snaps[0].read_text()) == {"events": []}

def test_retries_then_raises(tmp_path):
    calls = {"n": 0}
    def handler(request):
        calls["n"] += 1
        return httpx.Response(500)
    client = FPLClient(raw_dir=tmp_path, transport=httpx.MockTransport(handler),
                       retries=3, backoff=0.0)
    try:
        client.get_fixtures()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert calls["n"] == 3
```

- [ ] **Step 6: Run.** `uv run pytest tests/test_client.py -v` — Expected: FAIL

- [ ] **Step 7: Implement `src/gaffer/api/client.py`**

```python
from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

BASE = "https://fantasy.premierleague.com/api"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

class FPLClient:
    def __init__(self, raw_dir: Path | str = "data/raw", transport=None,
                 retries: int = 3, backoff: float = 2.0):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.retries = retries
        self.backoff = backoff
        self._http = httpx.Client(headers={"User-Agent": UA}, timeout=30,
                                  transport=transport)

    def _get(self, path: str, snapshot: str | None = None):
        last_exc = None
        for attempt in range(self.retries):
            try:
                resp = self._http.get(f"{BASE}/{path}")
                resp.raise_for_status()
                data = resp.json()
                if snapshot:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                    (self.raw_dir / f"{snapshot}-{ts}.json").write_text(
                        json.dumps(data))
                return data
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                time.sleep(self.backoff ** attempt if self.backoff else 0)
        raise last_exc

    def get_bootstrap(self):
        return self._get("bootstrap-static/", snapshot="bootstrap")

    def get_fixtures(self):
        return self._get("fixtures/", snapshot="fixtures")

    def get_element_summary(self, player_id: int):
        return self._get(f"element-summary/{player_id}/")

    def get_entry(self, entry_id: int):
        return self._get(f"entry/{entry_id}/", snapshot=f"entry-{entry_id}")

    def get_entry_history(self, entry_id: int):
        return self._get(f"entry/{entry_id}/history/")

    def get_entry_transfers(self, entry_id: int):
        return self._get(f"entry/{entry_id}/transfers/")

    def get_entry_picks(self, entry_id: int, gw: int):
        return self._get(f"entry/{entry_id}/event/{gw}/picks/")

    def get_league_standings(self, league_id: int, page: int = 1):
        return self._get(
            f"leagues-classic/{league_id}/standings/?page_standings={page}")

    def get_event_live(self, gw: int):
        return self._get(f"event/{gw}/live/")

    def get_event_status(self):
        return self._get("event-status/")
```

- [ ] **Step 8: Run.** `uv run pytest tests/test_client.py tests/test_parse.py -v` — Expected: PASS (both files)

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: FPL API client with retries, snapshots, parse helpers"
```

### Task 3: Parquet store + bootstrap → canonical tables

**Files:**
- Create: `src/gaffer/data/__init__.py` (empty), `src/gaffer/data/store.py`, `src/gaffer/data/bootstrap.py`
- Create: `tests/fixtures/bootstrap_sample.json` (trimmed real snapshot)
- Test: `tests/test_store.py`, `tests/test_bootstrap.py`

- [ ] **Step 1: Capture a real, trimmed bootstrap sample for tests** (one-time network step; grounds the actual 2026/27 schema, including the `game_config` scoring shape):

```bash
mkdir -p tests/fixtures
uv run python - <<'EOF'
import json, httpx
data = httpx.get("https://fantasy.premierleague.com/api/bootstrap-static/",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=30).json()
trimmed = {
    "events": data["events"][:3],
    "teams": data["teams"],
    "elements": data["elements"][:25],
    "element_types": data["element_types"],
    "game_config": data["game_config"],
    "game_settings": data["game_settings"],
}
json.dump(trimmed, open("tests/fixtures/bootstrap_sample.json", "w"), indent=1)
EOF
```

Then **inspect the scoring shape** — this decides `scoring_table()` below:
```bash
uv run python -c "import json; gc=json.load(open('tests/fixtures/bootstrap_sample.json'))['game_config']; print(json.dumps(gc.get('scoring', gc), indent=1)[:2000])"
```
Expected (per research): a `scoring` mapping where per-position values (goals, clean sheets, goals-conceded, defensive_contribution) are keyed by position id or code, and flat values (assists=3, yellow_cards=-1, ...) are scalars. **Adapt `scoring_table()` in Step 5 to the actual observed shape** — the test in Step 2 uses the real fixture, so a mismatch fails loudly.

- [ ] **Step 2: Write failing tests.** `tests/test_store.py`:

```python
import pandas as pd
from gaffer.data import store

def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = pd.DataFrame({"a": [1, 2]})
    store.save(df, "live/test.parquet")
    out = store.load("live/test.parquet")
    assert out["a"].tolist() == [1, 2]
```

`tests/test_bootstrap.py`:

```python
import json
from pathlib import Path
from gaffer.data.bootstrap import build_players, build_teams, build_events, scoring_table

RAW = json.loads(Path("tests/fixtures/bootstrap_sample.json").read_text())

def test_build_players_parses_numerics():
    players = build_players(RAW)
    assert {"code", "element", "name", "position", "team_code", "now_cost",
            "selected_by_percent", "xg90", "status",
            "price_change_percent"} <= set(players.columns)
    assert players["selected_by_percent"].dtype == "float64"
    assert players["position"].isin(["GKP", "DEF", "MID", "FWD"]).all()

def test_build_teams_and_events():
    teams = build_teams(RAW)
    assert {"team_id", "code", "name"} <= set(teams.columns)
    events = build_events(RAW)
    assert {"gw", "deadline_time", "is_next", "finished"} <= set(events.columns)

def test_scoring_table_has_position_values():
    s = scoring_table(RAW)
    assert s["goals_scored"]["MID"] == 5
    assert s["assists"]["MID"] == 3          # flat values broadcast to all positions
    assert s["clean_sheets"]["DEF"] == 4
    assert s["defensive_contribution"]["DEF"] == 2
    assert s["defensive_contribution"]["GKP"] == 0
```

- [ ] **Step 3: Run.** `uv run pytest tests/test_store.py tests/test_bootstrap.py -v` — Expected: FAIL

- [ ] **Step 4: Implement `src/gaffer/data/store.py`**

```python
from __future__ import annotations
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data")

def save(df: pd.DataFrame, rel: str) -> Path:
    path = DATA_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path

def load(rel: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / rel)

def exists(rel: str) -> bool:
    return (DATA_DIR / rel).exists()
```

- [ ] **Step 5: Implement `src/gaffer/data/bootstrap.py`**

```python
from __future__ import annotations
import pandas as pd
from gaffer.api.parse import to_float, to_int

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
POSITIONS = ["GKP", "DEF", "MID", "FWD"]

FLOAT_FIELDS = [
    "form", "points_per_game", "ep_next", "ep_this", "selected_by_percent",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "expected_goals_per_90", "expected_assists_per_90",
    "ict_index", "price_change_percent", "value_form", "value_season",
    "defensive_contribution_per_90",
]

def build_players(raw: dict) -> pd.DataFrame:
    rows = []
    for e in raw["elements"]:
        if e.get("element_type") not in POS:   # ignore legacy manager type 5
            continue
        row = {
            "code": e["code"],
            "element": e["id"],
            "name": e["web_name"],
            "position": POS[e["element_type"]],
            "team_id": e["team"],
            "team_code": e["team_code"],
            "now_cost": e["now_cost"],
            "status": e.get("status", "a"),
            "news": e.get("news", ""),
            "chance_of_playing": to_int(e.get("chance_of_playing_next_round")),
            "transfers_in_event": e.get("transfers_in_event", 0),
            "transfers_out_event": e.get("transfers_out_event", 0),
            "penalties_order": to_int(e.get("penalties_order")),
            "price_change_calibrating": bool(e.get("price_change_calibrating")),
            "price_change_locked_until": e.get("price_change_locked_until"),
            "price_change_projections": str(e.get("price_change_projections", "")),
        }
        for f in FLOAT_FIELDS:
            row[f] = to_float(e.get(f))
        row["xg90"] = row.pop("expected_goals_per_90")
        row["xa90"] = row.pop("expected_assists_per_90")
        rows.append(row)
    return pd.DataFrame(rows)

def build_teams(raw: dict) -> pd.DataFrame:
    return pd.DataFrame([
        {"team_id": t["id"], "code": t["code"], "name": t["name"],
         "short_name": t["short_name"]}
        for t in raw["teams"]
    ])

def build_events(raw: dict) -> pd.DataFrame:
    return pd.DataFrame([
        {"gw": ev["id"], "deadline_time": ev["deadline_time"],
         "is_current": ev.get("is_current", False),
         "is_next": ev.get("is_next", False),
         "finished": ev.get("finished", False),
         "data_checked": ev.get("data_checked", False)}
        for ev in raw["events"]
    ])

def next_gw(raw: dict) -> int:
    for ev in raw["events"]:
        if ev.get("is_next"):
            return ev["id"]
    raise ValueError("no next gameweek found")

# Scoring identifiers we assemble points from. Values in game_config.scoring
# are either scalars (apply to every position) or per-position mappings keyed
# by element_type id as a string (adapt here if the fixture shows otherwise).
SCORING_KEYS = [
    "goals_scored", "assists", "clean_sheets", "goals_conceded", "saves",
    "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
    "own_goals", "defensive_contribution", "bonus",
    "minutes_0_59", "minutes_60_plus",
]

def scoring_table(raw: dict) -> dict[str, dict[str, float]]:
    """{identifier: {position: points}} using the live rules, never hard-coded.

    Falls back to sensible identifiers if a key is absent (e.g. appearance
    points exposed as `long_play`/`short_play` in game_settings) — adjust the
    ALIASES mapping to the observed schema from the Step 1 inspection.
    """
    scoring = raw["game_config"]["scoring"]
    ALIASES = {"minutes_0_59": "short_play", "minutes_60_plus": "long_play"}
    table: dict[str, dict[str, float]] = {}
    for key in SCORING_KEYS:
        val = scoring.get(key, scoring.get(ALIASES.get(key, ""), 0))
        if isinstance(val, dict):
            table[key] = {POS[int(k)]: v for k, v in val.items() if int(k) in POS}
        else:
            table[key] = {p: val for p in POSITIONS}
    return table
```

- [ ] **Step 6: Run.** `uv run pytest tests/test_store.py tests/test_bootstrap.py -v` — Expected: PASS. If `test_scoring_table_has_position_values` fails, print the fixture's `game_config.scoring` and adjust `scoring_table()`/`ALIASES` — the assertions encode the known-correct 2026/27 values (MID goal = 5, DEF CS = 4, defcon = 2/0), so make the accessor produce them from the real shape.

- [ ] **Step 7: Commit.** `git add -A && git commit -m "feat: parquet store and bootstrap canonical tables with live scoring table"`

### Task 4: Live-season per-GW data (element-summary)

**Files:**
- Create: `src/gaffer/data/live.py`
- Test: `tests/test_live.py`

Canonical `player_gw` columns (used by history, live, features, models — keep in one place, `live.py`, imported elsewhere):
`season, season_idx, gw, code, element, name, position, team_code, opp_code, was_home, kickoff_time, minutes, starts, total_points, goals, assists, xg, xa, xgi, xgc, cs, gc, saves, bonus, bps, yc, rc, og, pens_missed, pens_saved, defcon, tackles, cbi, recoveries, value, selected`

- [ ] **Step 1: Write failing test.** `tests/test_live.py`:

```python
import pandas as pd
from gaffer.data.live import history_to_rows, CANONICAL_COLS

SUMMARY = {"history": [{
    "element": 10, "round": 1, "minutes": 90, "starts": 1, "total_points": 9,
    "goals_scored": 1, "assists": 0, "clean_sheets": 1, "goals_conceded": 0,
    "saves": 0, "bonus": 2, "bps": 30, "yellow_cards": 0, "red_cards": 0,
    "own_goals": 0, "penalties_missed": 0, "penalties_saved": 0,
    "expected_goals": "0.45", "expected_assists": "0.10",
    "expected_goal_involvements": "0.55", "expected_goals_conceded": "0.30",
    "defensive_contribution": 2, "tackles": 3, "recoveries": 6,
    "clearances_blocks_interceptions": 7, "value": 55, "selected": 100000,
    "opponent_team": 3, "was_home": True, "kickoff_time": "2026-08-21T19:00:00Z",
}]}

PLAYER_META = {"code": 999, "name": "Testman", "position": "DEF", "team_code": 8}
TEAM_ID_TO_CODE = {3: 14}

def test_history_to_rows_maps_canonical():
    rows = history_to_rows(SUMMARY, PLAYER_META, TEAM_ID_TO_CODE,
                           season="2026-27", season_idx=4)
    df = pd.DataFrame(rows)
    assert set(CANONICAL_COLS) <= set(df.columns)
    r = df.iloc[0]
    assert r["code"] == 999 and r["gw"] == 1 and r["opp_code"] == 14
    assert r["xg"] == 0.45 and r["defcon"] == 2 and r["cbi"] == 7
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_live.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/data/live.py`**

```python
from __future__ import annotations
import time
import pandas as pd
from gaffer.api.client import FPLClient
from gaffer.api.parse import to_float
from gaffer.data import store
from gaffer.data.bootstrap import build_players, build_teams

CANONICAL_COLS = [
    "season", "season_idx", "gw", "code", "element", "name", "position",
    "team_code", "opp_code", "was_home", "kickoff_time", "minutes", "starts",
    "total_points", "goals", "assists", "xg", "xa", "xgi", "xgc", "cs", "gc",
    "saves", "bonus", "bps", "yc", "rc", "og", "pens_missed", "pens_saved",
    "defcon", "tackles", "cbi", "recoveries", "value", "selected",
]

RENAME = {
    "round": "gw", "goals_scored": "goals", "clean_sheets": "cs",
    "goals_conceded": "gc", "yellow_cards": "yc", "red_cards": "rc",
    "own_goals": "og", "penalties_missed": "pens_missed",
    "penalties_saved": "pens_saved", "defensive_contribution": "defcon",
    "clearances_blocks_interceptions": "cbi",
}
XG_FIELDS = {"expected_goals": "xg", "expected_assists": "xa",
             "expected_goal_involvements": "xgi",
             "expected_goals_conceded": "xgc"}

def history_to_rows(summary: dict, player_meta: dict,
                    team_id_to_code: dict, season: str, season_idx: int) -> list[dict]:
    rows = []
    for h in summary.get("history", []):
        row = {RENAME.get(k, k): v for k, v in h.items()}
        for api_key, col in XG_FIELDS.items():
            row[col] = to_float(h.get(api_key), default=0.0)
        row.update(player_meta)
        row["season"], row["season_idx"] = season, season_idx
        row["opp_code"] = team_id_to_code.get(h.get("opponent_team"))
        rows.append({c: row.get(c) for c in CANONICAL_COLS})
    return rows

def refresh_live(client: FPLClient, season: str, season_idx: int,
                 sleep_s: float = 0.05) -> pd.DataFrame:
    """Fetch element-summary for every current player -> data/live/player_gw.parquet.

    Spec §9: provisional data never enters training — rows for any GW that is
    not yet data_checked (bonus can still change until ~09:00 the morning
    after the last match) are dropped before saving."""
    raw = client.get_bootstrap()
    unchecked = {ev["id"] for ev in raw["events"]
                 if not ev.get("data_checked", False)}
    players = build_players(raw)
    teams = build_teams(raw)
    team_id_to_code = dict(zip(teams["team_id"], teams["code"]))
    all_rows: list[dict] = []
    for p in players.itertuples():
        summary = client.get_element_summary(p.element)
        meta = {"code": p.code, "element": p.element, "name": p.name,
                "position": p.position, "team_code": p.team_code}
        all_rows.extend(history_to_rows(summary, meta, team_id_to_code,
                                        season, season_idx))
        time.sleep(sleep_s)  # politeness: ~600 calls
    df = pd.DataFrame(all_rows, columns=CANONICAL_COLS)
    df = df[~df["gw"].isin(unchecked)]
    store.save(df, "live/player_gw.parquet")
    return df
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_live.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: live-season per-GW ingestion to canonical player_gw"`

### Task 5: Historical training data (vaastav)

**Files:**
- Create: `src/gaffer/data/history.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: Write failing test** for the pure transform (network download tested manually in Step 5). `tests/test_history.py`:

```python
import pandas as pd
from gaffer.data.history import merged_gw_to_canonical

def test_merged_gw_to_canonical_maps_and_joins_code():
    merged = pd.DataFrame([{
        "element": 5, "name": "A. Player", "position": "GK", "team": "Arsenal",
        "round": 3, "GW": 3, "minutes": 90, "starts": 1, "total_points": 6,
        "goals_scored": 0, "assists": 0, "clean_sheets": 1, "goals_conceded": 0,
        "saves": 4, "bonus": 0, "bps": 22, "yellow_cards": 0, "red_cards": 0,
        "own_goals": 0, "penalties_missed": 0, "penalties_saved": 0,
        "expected_goals": 0.0, "expected_assists": 0.0,
        "expected_goal_involvements": 0.0, "expected_goals_conceded": 0.5,
        "value": 50, "selected": 5000, "opponent_team": 2, "was_home": True,
        "kickoff_time": "2022-08-27T14:00:00Z",
    }])
    players_raw = pd.DataFrame([{"id": 5, "code": 777}])
    teams = pd.DataFrame([{"id": 2, "code": 91}, {"id": 1, "code": 3}])
    out = merged_gw_to_canonical(merged, players_raw, teams,
                                 season="2022-23", season_idx=0)
    r = out.iloc[0]
    assert r["code"] == 777 and r["position"] == "GKP" and r["opp_code"] == 91
    assert pd.isna(r["defcon"])   # column absent pre-2025/26 -> NaN, not crash
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_history.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/data/history.py`**

```python
from __future__ import annotations
from pathlib import Path
import httpx
import pandas as pd
from gaffer.data import store
from gaffer.data.live import CANONICAL_COLS, RENAME, XG_FIELDS

VAASTAV = ("https://raw.githubusercontent.com/vaastav/"
           "Fantasy-Premier-League/master/data")
POS_NORM = {"GK": "GKP", "GKP": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}

def _download_csv(url: str, dest: Path) -> pd.DataFrame:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    try:
        return pd.read_csv(dest)
    except UnicodeDecodeError:            # some vaastav seasons are latin-1
        return pd.read_csv(dest, encoding="latin-1")

def merged_gw_to_canonical(merged: pd.DataFrame, players_raw: pd.DataFrame,
                           teams: pd.DataFrame, season: str,
                           season_idx: int) -> pd.DataFrame:
    df = merged.rename(columns=RENAME)
    for api_key, col in XG_FIELDS.items():
        if api_key in df.columns:
            df[col] = pd.to_numeric(df[api_key], errors="coerce")
    df["position"] = df["position"].map(POS_NORM)
    df["season"], df["season_idx"] = season, season_idx
    df["gw"] = pd.to_numeric(df.get("gw", df.get("GW")), errors="coerce")
    df = df.merge(players_raw[["id", "code"]].rename(columns={"id": "element"}),
                  on="element", how="left")
    df = df.merge(teams[["id", "code"]]
                  .rename(columns={"id": "opponent_team", "code": "opp_code"}),
                  on="opponent_team", how="left")
    team_of_element = players_raw.set_index("id")
    if "team_code" in players_raw.columns:
        df["team_code"] = df["element"].map(team_of_element["team_code"])
    for c in CANONICAL_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[CANONICAL_COLS].copy()
    numeric = [c for c in CANONICAL_COLS
               if c not in ("season", "name", "position", "was_home",
                            "kickoff_time")]
    out[numeric] = out[numeric].apply(pd.to_numeric, errors="coerce")
    return out

def build_history(seasons: list[str],
                  cache_dir: Path = Path("data/raw/vaastav")) -> pd.DataFrame:
    frames = []
    for idx, season in enumerate(seasons):
        merged = _download_csv(f"{VAASTAV}/{season}/gws/merged_gw.csv",
                               cache_dir / season / "merged_gw.csv")
        players_raw = _download_csv(f"{VAASTAV}/{season}/players_raw.csv",
                                    cache_dir / season / "players_raw.csv")
        teams = _download_csv(f"{VAASTAV}/{season}/teams.csv",
                              cache_dir / season / "teams.csv")
        frames.append(merged_gw_to_canonical(merged, players_raw, teams,
                                             season, idx))
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["code", "gw"])
    store.save(df, "history/player_gw.parquet")
    return df

def build_history_fixtures(seasons: list[str],
                           cache_dir: Path = Path("data/raw/vaastav")) -> pd.DataFrame:
    """Historical fixtures with results, team codes mapped — feeds Elo (Task 6)."""
    frames = []
    for idx, season in enumerate(seasons):
        fx = _download_csv(f"{VAASTAV}/{season}/fixtures.csv",
                           cache_dir / season / "fixtures.csv")
        teams = _download_csv(f"{VAASTAV}/{season}/teams.csv",
                              cache_dir / season / "teams.csv")
        code = dict(zip(teams["id"], teams["code"]))
        fx = fx.dropna(subset=["team_h_score"])
        frames.append(pd.DataFrame({
            "season": season, "season_idx": idx,
            "gw": pd.to_numeric(fx["event"], errors="coerce"),
            "kickoff_time": fx["kickoff_time"],
            "home_code": fx["team_h"].map(code),
            "away_code": fx["team_a"].map(code),
            "home_goals": fx["team_h_score"], "away_goals": fx["team_a_score"],
        }))
    df = pd.concat(frames, ignore_index=True).dropna(subset=["gw"])
    store.save(df, "history/fixtures.parquet")
    return df
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_history.py -v` — Expected: PASS

- [ ] **Step 5: Manual verification — real download** (network; ~25MB total, cached under `data/raw/vaastav/`):

```bash
uv run python -c "
from gaffer.data.history import build_history, build_history_fixtures
df = build_history(['2022-23','2023-24','2024-25','2025-26'])
fx = build_history_fixtures(['2022-23','2023-24','2024-25','2025-26'])
print(df.groupby('season')['gw'].agg(['count','max']))
print('defcon non-null 2025-26:', df[df.season=='2025-26']['defcon'].notna().mean())
print('fixtures:', len(fx))
"
```
Expected: ~20k–26k rows per season, `max` gw = 38 for each, defcon non-null fraction > 0.9 for 2025-26 only, fixtures ≈ 1520. If a season's column names differ (vaastav schemas drift), fix the mapping in `merged_gw_to_canonical` — the canonical column list is the contract.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: vaastav historical ingestion (player_gw + fixtures, 2022-23..2025-26)"`

### Task 6: Team Elo ratings

**Files:**
- Create: `src/gaffer/data/elo.py`
- Test: `tests/test_elo.py`

- [ ] **Step 1: Write failing test.** `tests/test_elo.py`:

```python
import pandas as pd
from gaffer.data.elo import compute_elo

def test_elo_winner_gains_loser_loses():
    fixtures = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "kickoff_time": "2022-08-06T14:00:00Z",
         "home_code": 1, "away_code": 2, "home_goals": 3, "away_goals": 0},
    ])
    elo = compute_elo(fixtures)
    # pre-match ratings are recorded, both start at 1500
    pre = elo[(elo.code == 1) & (elo.gw == 1)]
    assert pre.iloc[0]["elo_pre"] == 1500
    assert elo.attrs["final"][1] > 1500 > elo.attrs["final"][2]

def test_elo_pre_is_prematch_not_postmatch():
    fixtures = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "kickoff_time": "2022-08-06T14:00:00Z",
         "home_code": 1, "away_code": 2, "home_goals": 3, "away_goals": 0},
        {"season_idx": 0, "gw": 2, "kickoff_time": "2022-08-13T14:00:00Z",
         "home_code": 2, "away_code": 1, "home_goals": 0, "away_goals": 0},
    ])
    elo = compute_elo(fixtures)
    gw2_home = elo[(elo.code == 2) & (elo.gw == 2)].iloc[0]
    assert gw2_home["elo_pre"] < 1500        # team 2 lost gw1 before this match
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_elo.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/data/elo.py`**

```python
from __future__ import annotations
import pandas as pd

K = 20.0
HOME_ADV = 60.0
INIT = 1500.0

def compute_elo(fixtures: pd.DataFrame) -> pd.DataFrame:
    """Per-team pre-match Elo for every (season_idx, gw, team code).

    Input: rows with season_idx, gw, kickoff_time, home_code, away_code,
    home_goals, away_goals — completed matches only. Returns long frame
    [season_idx, gw, code, elo_pre]; df.attrs['final'] maps code -> latest elo
    (used to rate future fixtures).
    """
    fx = fixtures.sort_values(["season_idx", "kickoff_time"]).copy()
    ratings: dict[int, float] = {}
    rows = []
    for m in fx.itertuples():
        rh = ratings.get(m.home_code, INIT)
        ra = ratings.get(m.away_code, INIT)
        rows.append({"season_idx": m.season_idx, "gw": m.gw,
                     "code": m.home_code, "elo_pre": rh})
        rows.append({"season_idx": m.season_idx, "gw": m.gw,
                     "code": m.away_code, "elo_pre": ra})
        exp_home = 1.0 / (1.0 + 10 ** (-((rh + HOME_ADV) - ra) / 400.0))
        if m.home_goals > m.away_goals:
            score = 1.0
        elif m.home_goals < m.away_goals:
            score = 0.0
        else:
            score = 0.5
        ratings[m.home_code] = rh + K * (score - exp_home)
        ratings[m.away_code] = ra + K * ((1 - score) - (1 - exp_home))
    out = pd.DataFrame(rows).drop_duplicates(
        subset=["season_idx", "gw", "code"], keep="first")
    out.attrs["final"] = ratings
    return out
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_elo.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: team Elo ratings from match results"`

### Task 7: My team — picks, sell prices, free transfers

**Files:**
- Create: `src/gaffer/data/entry.py`
- Test: `tests/test_entry.py`

- [ ] **Step 1: Write failing tests** — sell-price and FT rules are exact FPL rules, worth pinning hard. `tests/test_entry.py`:

```python
from gaffer.data.entry import sell_price, compute_free_transfers

def test_sell_price_half_profit_rounded_down():
    assert sell_price(purchase=55, now=61) == 58   # +6 profit -> +3
    assert sell_price(purchase=55, now=56) == 55   # +1 profit -> +0
    assert sell_price(purchase=55, now=54) == 54   # loss -> current price
    assert sell_price(purchase=55, now=55) == 55

def test_free_transfers_bank_and_cap():
    # transfers_by_gw: {gw: n_transfers}; chips: {gw: chip_name}
    # GW2 start: 1 FT. No transfers GW2-5 -> banks to 5 by GW6, capped.
    assert compute_free_transfers({}, {}, current_gw=7) == 5
    # used 1 in GW2 -> 1 available GW3
    assert compute_free_transfers({2: 1}, {}, current_gw=3) == 1
    # used 2 in GW2 (one was a hit) -> still 1 in GW3 (can't go below 0 + 1)
    assert compute_free_transfers({2: 2}, {}, current_gw=3) == 1
    # wildcard GW: transfers don't consume FTs
    assert compute_free_transfers({2: 8}, {2: "wildcard"}, current_gw=3) == 2
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_entry.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/data/entry.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
from gaffer.api.client import FPLClient

def sell_price(purchase: int, now: int) -> int:
    """FPL sell price in 0.1m units: half of profit (rounded down) is kept."""
    if now <= purchase:
        return now
    return purchase + (now - purchase) // 2

def compute_free_transfers(transfers_by_gw: dict[int, int],
                           chips_by_gw: dict[int, str],
                           current_gw: int, start_gw: int = 2) -> int:
    """FTs available at `current_gw` deadline. 1/GW, bank to 5, floor 0.
    Wildcard/Free Hit GWs don't consume FTs (and FH transfers revert)."""
    ft = 1
    for gw in range(start_gw, current_gw):
        chip = chips_by_gw.get(gw, "")
        used = 0 if chip in ("wildcard", "freehit") else transfers_by_gw.get(gw, 0)
        ft = max(0, ft - used)
        ft = min(5, ft + 1)
    return ft

@dataclass
class MyTeam:
    entry_id: int
    bank: int                      # 0.1m units
    free_transfers: int
    current_gw: int                # the GW being planned (next deadline)
    picks: pd.DataFrame            # element, code, purchase, now, sell
    chips_used: list[str] = field(default_factory=list)
    chips_by_gw: dict[int, str] = field(default_factory=dict)

def fetch_my_team(client: FPLClient, entry_id: int, next_gw: int,
                  players: pd.DataFrame) -> MyTeam:
    last_gw = next_gw - 1
    picks_raw = client.get_entry_picks(entry_id, last_gw)
    transfers = client.get_entry_transfers(entry_id)
    history = client.get_entry_history(entry_id)

    # purchase price per owned element: last transfer-in cost, else GW1 start price
    purchase: dict[int, int] = {}
    for t in sorted(transfers, key=lambda t: t["time"]):
        purchase[t["element_in"]] = t["element_in_cost"]
    price_now = dict(zip(players["element"], players["now_cost"]))
    start_price = dict(zip(players["element"],
                           players["now_cost"]))  # fallback; GW1 buys below
    rows = []
    for p in picks_raw["picks"]:
        el = p["element"]
        buy = purchase.get(el, start_price.get(el, price_now.get(el, 0)))
        now = price_now.get(el, buy)
        rows.append({"element": el, "purchase": buy, "now": now,
                     "sell": sell_price(buy, now)})
    picks = pd.DataFrame(rows).merge(
        players[["element", "code", "name", "position", "team_code"]],
        on="element", how="left")

    transfers_by_gw: dict[int, int] = {}
    for t in transfers:
        transfers_by_gw[t["event"]] = transfers_by_gw.get(t["event"], 0) + 1
    chips_by_gw = {c["event"]: c["name"] for c in history.get("chips", [])}
    ft = compute_free_transfers(transfers_by_gw, chips_by_gw, next_gw)

    return MyTeam(
        entry_id=entry_id,
        bank=picks_raw["entry_history"]["bank"],
        free_transfers=ft,
        current_gw=next_gw,
        picks=picks,
        chips_used=list(chips_by_gw.values()),
        chips_by_gw=chips_by_gw,
    )
```

Note: for players bought at GW1 and never transferred, the true purchase price is their season start price. `cost_change_start` on the bootstrap element gives `now_cost - start_cost`, so compute `start_price = now_cost - cost_change_start` — **add `cost_change_start` to `build_players` FLOAT_FIELDS-adjacent int fields in Task 3 if not already present** and use it here instead of the `now_cost` fallback.

- [ ] **Step 4: Run.** `uv run pytest tests/test_entry.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: my-team state with exact sell prices and free-transfer computation"`

### Task 8: Mini-league rivals + effective ownership

**Files:**
- Create: `src/gaffer/data/league.py`
- Test: `tests/test_league.py`

- [ ] **Step 1: Write failing test.** `tests/test_league.py`:

```python
from gaffer.data.league import effective_ownership

RIVAL_PICKS = {
    101: [{"element": 1, "multiplier": 2}, {"element": 2, "multiplier": 1}],
    102: [{"element": 1, "multiplier": 1}, {"element": 3, "multiplier": 0}],
    103: [{"element": 2, "multiplier": 1}],
}

def test_effective_ownership_counts_captaincy_and_bench():
    eo = effective_ownership(RIVAL_PICKS)
    assert eo[1] == 100.0   # (2 + 1) / 3 rivals * 100
    assert eo[2] == round(2 / 3 * 100, 1)
    assert eo[3] == 0.0     # benched (multiplier 0) contributes nothing
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_league.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/data/league.py`**

```python
from __future__ import annotations
import pandas as pd
from gaffer.api.client import FPLClient

def fetch_rival_entries(client: FPLClient, league_id: int,
                        exclude_entry: int, max_rivals: int = 50) -> pd.DataFrame:
    rows, page = [], 1
    while True:
        data = client.get_league_standings(league_id, page)
        results = data["standings"]["results"]
        rows.extend(results)
        if not data["standings"].get("has_next") or len(rows) >= max_rivals:
            break
        page += 1
    df = pd.DataFrame(rows)[["entry", "entry_name", "player_name", "rank",
                             "last_rank", "total", "event_total"]]
    return df[df["entry"] != exclude_entry].head(max_rivals)

def fetch_rival_picks(client: FPLClient, entries: list[int],
                      gw: int) -> dict[int, list[dict]]:
    """Picks for a finished/underway GW (public post-deadline; 404 pre-deadline)."""
    out = {}
    for entry in entries:
        try:
            out[entry] = client.get_entry_picks(entry, gw)["picks"]
        except Exception:
            continue        # rival joined late / endpoint 404 — skip
    return out

def effective_ownership(rival_picks: dict[int, list[dict]]) -> dict[int, float]:
    """element -> EO% across rivals (captain counts double, bench counts 0)."""
    if not rival_picks:
        return {}
    n = len(rival_picks)
    counts: dict[int, float] = {}
    for picks in rival_picks.values():
        for p in picks:
            counts[p["element"]] = counts.get(p["element"], 0) + p["multiplier"]
    return {el: round(c / n * 100, 1) for el, c in counts.items()}
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_league.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: mini-league rival picks and effective ownership"`

### Task 9: Feature engineering (leakage-safe rolling windows)

**Files:**
- Create: `src/gaffer/features/__init__.py` (empty), `src/gaffer/features/engineer.py`
- Test: `tests/test_features.py`

- [ ] **Step 1: Write failing tests — the leakage test is the most important test in the repo.** `tests/test_features.py`:

```python
import pandas as pd
import numpy as np
from gaffer.features.engineer import add_player_rolling, build_prediction_frame

def _frame():
    return pd.DataFrame({
        "code": [1, 1, 1, 1],
        "season_idx": [0, 0, 0, 0],
        "gw": [1, 2, 3, 4],
        "total_points": [2.0, 4.0, 100.0, 6.0],
        "minutes": [90, 90, 90, 90],
    })

def test_rolling_excludes_current_row_no_leakage():
    out = add_player_rolling(_frame(), stats=["total_points"], windows=[3])
    # feature at gw3 must NOT include gw3's 100 points
    assert out.loc[out.gw == 3, "total_points_r3"].iloc[0] == (2 + 4) / 2
    # gw4 sees gw1-3
    assert out.loc[out.gw == 4, "total_points_r3"].iloc[0] == (2 + 4 + 100) / 3
    # gw1 has no history -> NaN
    assert np.isnan(out.loc[out.gw == 1, "total_points_r3"].iloc[0])

def test_prediction_frame_future_rows_get_history_features():
    hist = _frame()
    future = pd.DataFrame({"code": [1, 1], "season_idx": [0, 0], "gw": [5, 6],
                           "opp_code": [10, 11], "was_home": [True, False]})
    pred = build_prediction_frame(hist, future, stats=["total_points"],
                                  windows=[3])
    assert len(pred) == 2
    # gw5 window = gw2-4 actuals; gw6 window skips gw5's NaN
    assert pred.loc[pred.gw == 5, "total_points_r3"].iloc[0] == (4 + 100 + 6) / 3
    assert pred.loc[pred.gw == 6, "total_points_r3"].iloc[0] == (100 + 6) / 2
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_features.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/features/engineer.py`**

```python
from __future__ import annotations
import pandas as pd

ROLL_STATS = ["total_points", "minutes", "starts", "goals", "assists", "xg",
              "xa", "xgi", "xgc", "cs", "gc", "saves", "bonus", "bps",
              "defcon", "tackles", "cbi", "recoveries", "yc"]
WINDOWS = [1, 3, 5, 10, 38]

def add_player_rolling(df: pd.DataFrame, stats: list[str] = ROLL_STATS,
                       windows: list[int] = WINDOWS) -> pd.DataFrame:
    """Rolling means of past matches only. Rows must be one per player-match.
    shift(1) guarantees the current row never leaks into its own features.
    NaNs inside a window (missing stat / future rows) are skipped by mean()."""
    df = df.sort_values(["code", "season_idx", "gw"]).reset_index(drop=True)
    g = df.groupby("code", sort=False)
    for stat in stats:
        if stat not in df.columns:
            df[stat] = float("nan")
        shifted = g[stat].shift(1)
        for w in windows:
            df[f"{stat}_r{w}"] = (
                shifted.groupby(df["code"]).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    return df

def add_context(df: pd.DataFrame, elo: pd.DataFrame | None,
                elo_final: dict | None) -> pd.DataFrame:
    """Team/opponent Elo (own-team via team_code, opponent via opp_code) and
    rest days. Future rows use the latest Elo (elo_final)."""
    if elo is not None:
        team_elo = elo.rename(columns={"code": "team_code",
                                       "elo_pre": "team_elo"})
        df = df.merge(team_elo, on=["season_idx", "gw", "team_code"], how="left")
        opp_elo = elo.rename(columns={"code": "opp_code", "elo_pre": "opp_elo"})
        df = df.merge(opp_elo, on=["season_idx", "gw", "opp_code"], how="left")
        if elo_final:
            df["team_elo"] = df["team_elo"].fillna(df["team_code"].map(elo_final))
            df["opp_elo"] = df["opp_elo"].fillna(df["opp_code"].map(elo_final))
        df["elo_diff"] = df["team_elo"] - df["opp_elo"]
    df["home"] = df["was_home"].astype("float")
    kt = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
    df["days_rest"] = (kt - kt.groupby(df["code"]).shift(1)).dt.days.clip(0, 30)
    return df

def build_prediction_frame(hist: pd.DataFrame, future: pd.DataFrame,
                           stats: list[str] = ROLL_STATS,
                           windows: list[int] = WINDOWS,
                           elo: pd.DataFrame | None = None,
                           elo_final: dict | None = None) -> pd.DataFrame:
    """future: one row per player per upcoming fixture (code, season_idx, gw,
    opp_code, was_home, team_code, position, kickoff_time). Appends to history,
    computes features, returns only the future rows (features from history)."""
    future = future.copy()
    future["_future"] = True
    hist = hist.copy()
    hist["_future"] = False
    combined = pd.concat([hist, future], ignore_index=True)
    combined = add_player_rolling(combined, stats, windows)
    combined = add_context(combined, elo, elo_final)
    out = combined[combined["_future"]].drop(columns=["_future"])
    return out.reset_index(drop=True)

def feature_columns(stats: list[str] = ROLL_STATS,
                    windows: list[int] = WINDOWS) -> list[str]:
    cols = [f"{s}_r{w}" for s in stats for w in windows]
    return cols + ["team_elo", "opp_elo", "elo_diff", "home", "days_rest"]
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_features.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: leakage-safe rolling feature engineering with prediction frame"`

### Task 10: Model persistence + minutes model

**Files:**
- Create: `src/gaffer/models/__init__.py` (empty), `src/gaffer/models/persistence.py`, `src/gaffer/models/minutes.py`
- Test: `tests/test_minutes.py`

- [ ] **Step 1: Write failing tests.** `tests/test_minutes.py`:

```python
import numpy as np
import pandas as pd
from gaffer.models.minutes import MinutesModel, apply_availability
from gaffer.features.engineer import add_player_rolling

def _training_frame(n=400, seed=0):
    """Synthetic: regular starter codes get 90s, fringe codes get 0-20."""
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(20):
        starter = code < 10
        for gw in range(1, 21):
            minutes = int(rng.choice([90, 90, 90, 60, 0] if starter
                                     else [0, 0, 0, 10, 20]))
            rows.append({"code": code, "season_idx": 0, "gw": gw,
                         "minutes": minutes, "starts": int(minutes >= 60),
                         "kickoff_time": None, "was_home": True})
    return pd.DataFrame(rows)

def test_minutes_model_separates_starters_from_fringe():
    df = add_player_rolling(_training_frame(), stats=["minutes", "starts"],
                            windows=[3, 5])
    df["home"] = 1.0
    train = df[df.gw <= 15]
    m = MinutesModel(feature_cols=["minutes_r3", "minutes_r5",
                                   "starts_r3", "starts_r5", "home"])
    m.fit(train)
    pred = m.predict(df[df.gw > 15])
    starters = pred[pred.code < 10]
    fringe = pred[pred.code >= 10]
    assert starters["p_play"].mean() > 0.8
    assert fringe["p_play"].mean() < 0.4
    assert ((pred["p60"] <= pred["p_play"] + 1e-9)).all()

def test_availability_override_zeroes_injured():
    pred = pd.DataFrame({"code": [1, 2], "p_play": [0.9, 0.9],
                         "p60": [0.8, 0.8], "e_min": [80.0, 80.0]})
    avail = pd.DataFrame({"code": [1, 2], "status": ["i", "d"],
                          "chance_of_playing": [None, 50]})
    out = apply_availability(pred, avail)
    assert out.loc[out.code == 1, "p_play"].iloc[0] == 0.0
    assert abs(out.loc[out.code == 2, "p_play"].iloc[0] - 0.45) < 1e-9
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_minutes.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/models/persistence.py`**

```python
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import joblib

MODELS_DIR = Path("models")

def save_model(obj, name: str, meta: dict | None = None) -> Path:
    MODELS_DIR.mkdir(exist_ok=True)
    path = MODELS_DIR / f"{name}.joblib"
    joblib.dump(obj, path)
    meta = dict(meta or {})
    meta["saved_at"] = datetime.now(timezone.utc).isoformat()
    (MODELS_DIR / f"{name}.meta.json").write_text(json.dumps(meta, indent=1))
    return path

def load_model(name: str):
    return joblib.load(MODELS_DIR / f"{name}.joblib")

def model_exists(name: str) -> bool:
    return (MODELS_DIR / f"{name}.joblib").exists()
```

(joblib ships with scikit-learn; no new dependency.)

- [ ] **Step 4: Implement `src/gaffer/models/minutes.py`**

```python
from __future__ import annotations
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor

LGB_KW = dict(n_estimators=300, learning_rate=0.05, num_leaves=31,
              verbose=-1, random_state=7)

class MinutesModel:
    """P(plays), P(60+ minutes), E[minutes]. Trained on historical rows;
    live availability (status / chance_of_playing) is applied as a hard
    override at predict time via apply_availability(), never as a trained
    feature (it doesn't exist historically -> train/serve skew)."""

    def __init__(self, feature_cols: list[str]):
        self.feature_cols = feature_cols
        self.play_clf = LGBMClassifier(**LGB_KW)
        self.sixty_clf = LGBMClassifier(**LGB_KW)
        self.min_reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "MinutesModel":
        X = df[self.feature_cols]
        self.play_clf.fit(X, (df["minutes"] > 0).astype(int))
        self.sixty_clf.fit(X, (df["minutes"] >= 60).astype(int))
        self.min_reg.fit(X, df["minutes"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.feature_cols]
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_play"] = self.play_clf.predict_proba(X)[:, 1]
        out["p60"] = self.sixty_clf.predict_proba(X)[:, 1].clip(0, 1)
        out["p60"] = out[["p60", "p_play"]].min(axis=1)
        out["e_min"] = self.min_reg.predict(X).clip(0, 90)
        return out

def apply_availability(pred: pd.DataFrame, avail: pd.DataFrame) -> pd.DataFrame:
    """avail: code, status, chance_of_playing (from live bootstrap).
    status i/s/u/n (injured/suspended/unavailable/not in squad) -> factor from
    chance_of_playing (None means 0). 'd' (doubtful) -> chance_of_playing.
    'a' -> 1.0."""
    out = pred.merge(avail, on="code", how="left")
    cop = out["chance_of_playing"].astype("float") / 100.0
    factor = pd.Series(1.0, index=out.index)
    flagged = out["status"].isin(["i", "s", "u", "n", "d"])
    factor[flagged] = cop[flagged].fillna(0.0)
    for col in ["p_play", "p60"]:
        out[col] = out[col] * factor
    out["e_min"] = out["e_min"] * factor
    return out.drop(columns=["status", "chance_of_playing"])
```

- [ ] **Step 5: Run.** `uv run pytest tests/test_minutes.py -v` — Expected: PASS

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: minutes model with live availability overrides + model persistence"`

### Task 11: Team model — P(clean sheet), E[goals conceded]

**Files:**
- Create: `src/gaffer/models/team.py`
- Test: `tests/test_team_model.py`

- [ ] **Step 1: Write failing tests.** `tests/test_team_model.py`:

```python
import pandas as pd
import numpy as np
from gaffer.models.team import build_team_gw, TeamModel

def test_build_team_gw_two_rows_per_fixture():
    fixtures = pd.DataFrame([
        {"season_idx": 0, "gw": 1, "kickoff_time": "2022-08-06T14:00:00Z",
         "home_code": 1, "away_code": 2, "home_goals": 2, "away_goals": 0},
    ])
    tg = build_team_gw(fixtures)
    assert len(tg) == 2
    home = tg[tg.code == 1].iloc[0]
    away = tg[tg.code == 2].iloc[0]
    assert home["gf"] == 2 and home["ga"] == 0 and home["cs"] == 1
    assert away["gf"] == 0 and away["ga"] == 2 and away["cs"] == 0
    assert home["home"] == 1.0 and away["home"] == 0.0

def test_team_model_strong_team_higher_cs_prob():
    rng = np.random.default_rng(1)
    rows = []
    for gw in range(1, 60):
        strong_cs = int(rng.random() < 0.6)
        weak_cs = int(rng.random() < 0.1)
        rows.append({"code": 1, "season_idx": 0, "gw": gw, "home": 1.0,
                     "cs": strong_cs, "ga": 0 if strong_cs else 1,
                     "gf": 2, "elo_diff": 200.0})
        rows.append({"code": 2, "season_idx": 0, "gw": gw, "home": 0.0,
                     "cs": weak_cs, "ga": 0 if weak_cs else 2,
                     "gf": 0, "elo_diff": -200.0})
    df = pd.DataFrame(rows)
    m = TeamModel(feature_cols=["elo_diff", "home"])
    m.fit(df[df.gw <= 45])
    pred = m.predict(df[df.gw > 45])
    assert pred[pred.code == 1]["p_cs"].mean() > pred[pred.code == 2]["p_cs"].mean()
    assert pred[pred.code == 2]["e_gc"].mean() > pred[pred.code == 1]["e_gc"].mean()
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_team_model.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/models/team.py`**

```python
from __future__ import annotations
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from gaffer.models.minutes import LGB_KW

def build_team_gw(fixtures: pd.DataFrame) -> pd.DataFrame:
    """fixtures (home/away, goals) -> one row per team per match:
    [season_idx, gw, kickoff_time, code, opp_code, home, gf, ga, cs]."""
    home = pd.DataFrame({
        "season_idx": fixtures["season_idx"], "gw": fixtures["gw"],
        "kickoff_time": fixtures["kickoff_time"],
        "code": fixtures["home_code"], "opp_code": fixtures["away_code"],
        "home": 1.0, "gf": fixtures["home_goals"], "ga": fixtures["away_goals"],
    })
    away = pd.DataFrame({
        "season_idx": fixtures["season_idx"], "gw": fixtures["gw"],
        "kickoff_time": fixtures["kickoff_time"],
        "code": fixtures["away_code"], "opp_code": fixtures["home_code"],
        "home": 0.0, "gf": fixtures["away_goals"], "ga": fixtures["home_goals"],
    })
    tg = pd.concat([home, away], ignore_index=True)
    tg["cs"] = (tg["ga"] == 0).astype(int)
    return tg

def add_team_rolling(tg: pd.DataFrame, windows=(5, 10, 38)) -> pd.DataFrame:
    tg = tg.sort_values(["code", "season_idx", "gw"]).reset_index(drop=True)
    g = tg.groupby("code", sort=False)
    for stat in ["gf", "ga", "cs"]:
        shifted = g[stat].shift(1)
        for w in windows:
            tg[f"team_{stat}_r{w}"] = (
                shifted.groupby(tg["code"]).rolling(w, min_periods=1).mean()
                .reset_index(level=0, drop=True))
    return tg

TEAM_FEATURES = ["elo_diff", "home", "team_gf_r5", "team_ga_r5", "team_cs_r10",
                 "team_gf_r38", "team_ga_r38"]

class TeamModel:
    def __init__(self, feature_cols: list[str] = TEAM_FEATURES):
        self.feature_cols = feature_cols
        self.cs_clf = LGBMClassifier(**LGB_KW)
        self.gc_reg = LGBMRegressor(**LGB_KW)

    def fit(self, tg: pd.DataFrame) -> "TeamModel":
        cols = [c for c in self.feature_cols if c in tg.columns]
        self.cols_ = cols
        self.cs_clf.fit(tg[cols], tg["cs"])
        self.gc_reg.fit(tg[cols], tg["ga"])
        return self

    def predict(self, tg: pd.DataFrame) -> pd.DataFrame:
        out = tg[["code", "season_idx", "gw"]].copy()
        out["p_cs"] = self.cs_clf.predict_proba(tg[self.cols_])[:, 1]
        out["e_gc"] = self.gc_reg.predict(tg[self.cols_]).clip(0, None)
        return out
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_team_model.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: team model for clean sheets and goals conceded"`

### Task 12: Attacking models — E[goals], E[assists]

**Files:**
- Create: `src/gaffer/models/attacking.py`
- Test: `tests/test_attacking.py`

Design note: trained per position group on rows with `minutes > 0` (per-appearance rates); combined with `p_play` at assembly. Targets are raw `goals`/`assists` per match.

- [ ] **Step 1: Write failing test.** `tests/test_attacking.py`:

```python
import numpy as np
import pandas as pd
from gaffer.models.attacking import AttackingModel

def _frame(seed=2):
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(30):
        good = code < 15          # high-xG players score more
        for gw in range(1, 40):
            xg_r5 = 0.6 if good else 0.05
            rows.append({
                "code": code, "season_idx": 0, "gw": gw, "position": "FWD",
                "minutes": 90, "xg_r5": xg_r5, "xa_r5": 0.1, "xgi_r5": xg_r5 + 0.1,
                "minutes_r5": 90.0, "elo_diff": 0.0, "home": 1.0,
                "goals": int(rng.random() < (0.55 if good else 0.05)),
                "assists": int(rng.random() < 0.1),
            })
    return pd.DataFrame(rows)

def test_attacking_model_ranks_high_xg_players_higher():
    df = _frame()
    m = AttackingModel(feature_cols=["xg_r5", "xa_r5", "xgi_r5", "minutes_r5",
                                    "elo_diff", "home"])
    m.fit(df[df.gw <= 30])
    pred = m.predict(df[df.gw > 30])
    assert pred[pred.code < 15]["e_goals"].mean() > \
           pred[pred.code >= 15]["e_goals"].mean() * 2
    assert (pred["e_goals"] >= 0).all()
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_attacking.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/models/attacking.py`**

```python
from __future__ import annotations
import pandas as pd
from lightgbm import LGBMRegressor
from gaffer.models.minutes import LGB_KW

ATTACK_FEATURES = [
    "xg_r1", "xg_r3", "xg_r5", "xg_r10", "xg_r38",
    "xa_r1", "xa_r3", "xa_r5", "xa_r10", "xa_r38",
    "xgi_r5", "xgi_r10", "goals_r5", "goals_r38", "assists_r5", "assists_r38",
    "bps_r5", "minutes_r5", "starts_r5",
    "team_elo", "opp_elo", "elo_diff", "home", "days_rest",
]

class AttackingModel:
    """One goals + one assists regressor per position group, trained on
    appearances only (minutes > 0)."""

    def __init__(self, feature_cols: list[str] = ATTACK_FEATURES):
        self.feature_cols = feature_cols
        self.models: dict[tuple[str, str], LGBMRegressor] = {}

    def _groups(self, df: pd.DataFrame):
        yield "GKP_DEF", df[df["position"].isin(["GKP", "DEF"])]
        yield "MID", df[df["position"] == "MID"]
        yield "FWD", df[df["position"] == "FWD"]

    def fit(self, df: pd.DataFrame) -> "AttackingModel":
        played = df[df["minutes"] > 0]
        self.cols_ = [c for c in self.feature_cols if c in df.columns]
        for grp, sub in self._groups(played):
            for target in ("goals", "assists"):
                model = LGBMRegressor(**LGB_KW)
                model.fit(sub[self.cols_], sub[target])
                self.models[(grp, target)] = model
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["e_goals"] = 0.0
        out["e_assists"] = 0.0
        for grp, sub in self._groups(df):
            if sub.empty:
                continue
            for target, col in (("goals", "e_goals"), ("assists", "e_assists")):
                pred = self.models[(grp, target)].predict(sub[self.cols_])
                out.loc[sub.index, col] = pred.clip(0, None)
        return out
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_attacking.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: per-position attacking models (goals, assists)"`

### Task 13: Auxiliary components — defcon, saves, bonus, cards

**Files:**
- Create: `src/gaffer/models/components.py`
- Test: `tests/test_components.py`

- [ ] **Step 1: Write failing tests.** `tests/test_components.py`:

```python
import numpy as np
import pandas as pd
from gaffer.models.components import DefconModel, SavesModel, BonusModel, card_penalty

def _defcon_frame(seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for code in range(20):
        tackler = code < 10
        for gw in range(1, 40):
            rows.append({
                "code": code, "season_idx": 3, "gw": gw, "position": "DEF",
                "minutes": 90, "tackles_r5": 3.0 if tackler else 0.5,
                "cbi_r5": 6.0 if tackler else 1.0, "recoveries_r5": 5.0,
                "minutes_r5": 90.0, "defcon": 2 if (tackler and rng.random() < .6)
                                             else (2 if rng.random() < .05 else 0),
            })
    return pd.DataFrame(rows)

def test_defcon_model_ranks_tacklers_higher():
    df = _defcon_frame()
    m = DefconModel(feature_cols=["tackles_r5", "cbi_r5", "recoveries_r5",
                                  "minutes_r5"])
    m.fit(df[df.gw <= 30])
    pred = m.predict(df[df.gw > 30])
    assert pred[pred.code < 10]["p_defcon"].mean() > \
           pred[pred.code >= 10]["p_defcon"].mean() * 2

def test_defcon_fit_ignores_rows_without_defcon_data():
    df = _defcon_frame()
    df.loc[df.season_idx < 3, "defcon"] = np.nan   # pre-2025/26 rows
    m = DefconModel(feature_cols=["tackles_r5", "cbi_r5", "recoveries_r5",
                                  "minutes_r5"])
    m.fit(df)     # must not raise on NaN targets

def test_card_penalty():
    row = pd.Series({"yc_r38": 0.2, "rc_r38": 0.0})
    assert card_penalty(row) == -0.2
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_components.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/models/components.py`**

```python
from __future__ import annotations
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from gaffer.models.minutes import LGB_KW

DEFCON_FEATURES = ["tackles_r3", "tackles_r5", "tackles_r38", "cbi_r3",
                   "cbi_r5", "cbi_r38", "recoveries_r5", "recoveries_r38",
                   "minutes_r5", "opp_elo", "home"]

class DefconModel:
    """P(defensive-contribution threshold hit). Trained only on rows where the
    defcon stat exists (2025/26 onwards); older rows have NaN targets."""

    def __init__(self, feature_cols: list[str] = DEFCON_FEATURES):
        self.feature_cols = feature_cols
        self.clf = LGBMClassifier(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "DefconModel":
        sub = df[(df["minutes"] > 0) & df["defcon"].notna()
                 & (df["position"] != "GKP")]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        self.clf.fit(sub[self.cols_], (sub["defcon"] > 0).astype(int))
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["p_defcon"] = self.clf.predict_proba(df[self.cols_])[:, 1]
        out.loc[df["position"] == "GKP", "p_defcon"] = 0.0
        return out

SAVES_FEATURES = ["saves_r3", "saves_r5", "saves_r38", "opp_elo", "elo_diff",
                  "home"]

class SavesModel:
    def __init__(self, feature_cols: list[str] = SAVES_FEATURES):
        self.feature_cols = feature_cols
        self.reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "SavesModel":
        sub = df[(df["position"] == "GKP") & (df["minutes"] > 0)]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        self.reg.fit(sub[self.cols_], sub["saves"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["e_saves"] = 0.0
        gk = df["position"] == "GKP"
        if gk.any():
            out.loc[gk, "e_saves"] = self.reg.predict(
                df.loc[gk, self.cols_]).clip(0, None)
        return out

BONUS_FEATURES = ["bps_r3", "bps_r5", "bps_r38", "xgi_r5", "bonus_r5",
                  "bonus_r38", "elo_diff", "home"]

class BonusModel:
    """E[bonus]. BPS was rebalanced for 2026/27, so train on the most recent
    season only (pass min_season_idx) and expect weekly refits to adapt."""

    def __init__(self, feature_cols: list[str] = BONUS_FEATURES,
                 min_season_idx: int = 3):
        self.feature_cols = feature_cols
        self.min_season_idx = min_season_idx
        self.reg = LGBMRegressor(**LGB_KW)

    def fit(self, df: pd.DataFrame) -> "BonusModel":
        sub = df[(df["minutes"] > 0) & (df["season_idx"] >= self.min_season_idx)
                 & df["bonus"].notna()]
        self.cols_ = [c for c in self.feature_cols if c in sub.columns]
        self.reg.fit(sub[self.cols_], sub["bonus"])
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["code", "season_idx", "gw"]].copy()
        out["e_bonus"] = self.reg.predict(df[self.cols_]).clip(0, 3)
        return out

def card_penalty(row: pd.Series) -> float:
    """Expected points from cards: -1 * yellow rate + -3 * red rate."""
    yc = row.get("yc_r38", 0.0) or 0.0
    rc = row.get("rc_r38", 0.0) or 0.0
    return float(-1.0 * yc - 3.0 * rc)
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_components.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: defcon, saves, bonus, cards component models"`

### Task 14: Assembly — components + scoring table → EP matrix

**Files:**
- Create: `src/gaffer/models/assemble.py`
- Test: `tests/test_assemble.py`

- [ ] **Step 1: Write failing tests** — the maths here is checkable by hand. `tests/test_assemble.py`:

```python
import math
import pandas as pd
from gaffer.models.assemble import assemble_ep, p_haul

SCORING = {
    "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
    "assists": {p: 3 for p in ["GKP", "DEF", "MID", "FWD"]},
    "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
    "goals_conceded": {"GKP": -0.5, "DEF": -0.5, "MID": 0, "FWD": 0},
    "saves": {p: 1 / 3 if p == "GKP" else 0 for p in ["GKP", "DEF", "MID", "FWD"]},
    "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2},
    "minutes_0_59": {p: 1 for p in ["GKP", "DEF", "MID", "FWD"]},
    "minutes_60_plus": {p: 2 for p in ["GKP", "DEF", "MID", "FWD"]},
}

def _components():
    return pd.DataFrame([{
        "code": 1, "season_idx": 4, "gw": 2, "position": "DEF",
        "p_play": 1.0, "p60": 1.0, "e_min": 90.0,
        "e_goals": 0.1, "e_assists": 0.1, "p_cs": 0.5, "e_gc": 0.6,
        "e_saves": 0.0, "p_defcon": 0.5, "e_bonus": 0.4, "e_cards": -0.1,
    }])

def test_assemble_ep_matches_hand_calc():
    ep = assemble_ep(_components(), SCORING)
    # appearance: 1*p_play + 1*p60 = 2.0 ; goals: .1*6=.6 ; assists: .1*3=.3
    # cs: p60*p_cs*4 = 2.0 ; gc: -0.5*e_gc*p60 = -0.3 ; defcon: .5*2=1.0
    # bonus .4 ; cards -.1  => total 5.9
    assert abs(ep.iloc[0]["ep"] - 5.9) < 1e-9

def test_p_haul_poisson():
    lam = 0.5
    expected = 1 - math.exp(-lam) * (1 + lam)
    assert abs(p_haul(0.3, 0.2) - expected) < 1e-9
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_assemble.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/models/assemble.py`**

```python
from __future__ import annotations
import math
import pandas as pd

def p_haul(e_goals: float, e_assists: float) -> float:
    """P(2+ attacking returns) under Poisson(e_goals + e_assists)."""
    lam = max(0.0, (e_goals or 0.0) + (e_assists or 0.0))
    return 1.0 - math.exp(-lam) * (1.0 + lam)

def assemble_ep(components: pd.DataFrame,
                scoring: dict[str, dict[str, float]]) -> pd.DataFrame:
    """One row per player-fixture with all component predictions ->
    ep column + p_haul. Attacking/saves/defcon/bonus components are
    per-appearance rates, so scale by p_play; CS and GC require 60+ mins."""
    df = components.copy()
    pos = df["position"]

    def s(key):
        return pos.map(scoring[key])

    df["ep"] = (
        df["p_play"] * s("minutes_0_59")
        + df["p60"] * (s("minutes_60_plus") - s("minutes_0_59"))
        + df["p_play"] * df["e_goals"] * s("goals_scored")
        + df["p_play"] * df["e_assists"] * s("assists")
        + df["p60"] * df["p_cs"] * s("clean_sheets")
        + df["p60"] * df["e_gc"] * s("goals_conceded")
        + df["p_play"] * df["e_saves"] * s("saves")
        + df["p_play"] * df["p_defcon"] * s("defensive_contribution")
        + df["p_play"] * df["e_bonus"]
        + df["p_play"] * df["e_cards"]
    )
    df["p_haul"] = [
        p_haul(pl * g, pl * a)
        for pl, g, a in zip(df["p_play"], df["e_goals"], df["e_assists"])
    ]
    return df

def ep_matrix(per_fixture: pd.DataFrame) -> pd.DataFrame:
    """Sum fixtures within a GW (double GWs add, blanks give 0 rows -> absent).
    Returns [code, gw, ep, p_haul(max over fixtures)]."""
    return (per_fixture.groupby(["code", "gw"], as_index=False)
            .agg(ep=("ep", "sum"), p_haul=("p_haul", "max")))
```

Note on `goals_conceded` scoring: the API expresses it per position; GKP/DEF lose 1 point per 2 conceded. If the live `game_config.scoring` gives an integer per-2-goals convention (e.g. `-1`), convert to a per-goal rate (`-0.5`) when building the scoring table in Task 3 — add a unit test there pinning `scoring["goals_conceded"]["DEF"] == -0.5` and adjust `scoring_table()` accordingly.

- [ ] **Step 4: Run.** `uv run pytest tests/test_assemble.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: EP assembly from components with live scoring table"`

### Task 15: Training orchestration + benchmark evaluation — **MILESTONE GATE**

**Files:**
- Create: `src/gaffer/models/train.py`
- Test: `tests/test_train.py`

- [ ] **Step 1: Write failing test for the benchmark comparison logic** (pure function; full training run is verified manually in Step 5). `tests/test_train.py`:

```python
import pandas as pd
from gaffer.models.train import evaluate_predictions

def test_evaluate_beats_worse_baseline():
    truth = pd.DataFrame({
        "code": [1, 2, 3, 4], "gw": [10] * 4,
        "total_points": [2.0, 6.0, 12.0, 0.0],
        "minutes": [90, 90, 90, 0],
    })
    good = pd.DataFrame({"code": [1, 2, 3, 4], "gw": [10] * 4,
                         "ep": [2.5, 5.0, 10.0, 0.5]})
    bad = pd.DataFrame({"code": [1, 2, 3, 4], "gw": [10] * 4,
                        "ep": [8.0, 1.0, 2.0, 6.0]})
    m_good = evaluate_predictions(good, truth)
    m_bad = evaluate_predictions(bad, truth)
    assert m_good["mae_starters"] < m_bad["mae_starters"]
    assert m_good["captain_pts"] >= m_bad["captain_pts"]
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_train.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/models/train.py`**

```python
from __future__ import annotations
import json
import pandas as pd
from gaffer.data import store
from gaffer.data.elo import compute_elo
from gaffer.features.engineer import (add_player_rolling, add_context,
                                      feature_columns)
from gaffer.models.persistence import save_model
from gaffer.models.minutes import MinutesModel
from gaffer.models.team import (build_team_gw, add_team_rolling, TeamModel,
                                TEAM_FEATURES)
from gaffer.models.attacking import AttackingModel, ATTACK_FEATURES
from gaffer.models.components import (DefconModel, SavesModel, BonusModel)

MINUTES_FEATURES = ["minutes_r1", "minutes_r3", "minutes_r5", "minutes_r10",
                    "starts_r1", "starts_r3", "starts_r5", "starts_r10",
                    "days_rest", "home"]

def load_training_frame(max_season_idx: int | None = None,
                        max_gw: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """player_gw history (+ live season appended if present) with features,
    plus team_gw with features and final elo map. Optionally truncated for
    backtesting (strictly before max_season_idx/max_gw)."""
    player_gw = store.load("history/player_gw.parquet")
    fixtures = store.load("history/fixtures.parquet")
    if store.exists("live/player_gw.parquet"):
        live = store.load("live/player_gw.parquet")
        live["season_idx"] = player_gw["season_idx"].max() + 1
        player_gw = pd.concat([player_gw, live], ignore_index=True)
    if store.exists("live/fixtures.parquet"):
        lfx = store.load("live/fixtures.parquet")
        fixtures = pd.concat([fixtures, lfx], ignore_index=True)
    if max_season_idx is not None:
        keep = (player_gw["season_idx"] < max_season_idx) | (
            (player_gw["season_idx"] == max_season_idx)
            & (player_gw["gw"] < (max_gw or 99)))
        player_gw = player_gw[keep]
        fixtures = fixtures[(fixtures["season_idx"] < max_season_idx) | (
            (fixtures["season_idx"] == max_season_idx)
            & (fixtures["gw"] < (max_gw or 99)))]

    elo = compute_elo(fixtures)
    elo_final = elo.attrs["final"]
    df = add_player_rolling(player_gw)
    df = add_context(df, elo, elo_final)
    tg = add_team_rolling(build_team_gw(fixtures))
    tg = tg.merge(elo.rename(columns={"elo_pre": "team_elo_own"}),
                  on=["season_idx", "gw", "code"], how="left")
    opp = elo.rename(columns={"code": "opp_code", "elo_pre": "opp_elo"})
    tg = tg.merge(opp, on=["season_idx", "gw", "opp_code"], how="left")
    tg["elo_diff"] = tg["team_elo_own"] - tg["opp_elo"]
    return df, tg, elo_final

def train_all(df: pd.DataFrame, tg: pd.DataFrame, save: bool = True) -> dict:
    minutes = MinutesModel(MINUTES_FEATURES).fit(df)
    team = TeamModel(TEAM_FEATURES).fit(tg.dropna(subset=["elo_diff"]))
    attacking = AttackingModel(ATTACK_FEATURES).fit(df)
    defcon = DefconModel().fit(df)
    saves = SavesModel().fit(df)
    bonus = BonusModel(min_season_idx=int(df["season_idx"].max())).fit(df)
    models = {"minutes": minutes, "team": team, "attacking": attacking,
              "defcon": defcon, "saves": saves, "bonus": bonus}
    if save:
        for name, m in models.items():
            save_model(m, name, meta={"rows": len(df)})
    return models

def evaluate_predictions(pred: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """pred: [code, gw, ep]; truth: [code, gw, total_points, minutes]."""
    j = pred.merge(truth, on=["code", "gw"], how="inner")
    starters = j[j["minutes"] >= 60]
    err = (j["ep"] - j["total_points"]).abs()
    err_st = (starters["ep"] - starters["total_points"]).abs()
    cap = (j.sort_values("ep", ascending=False).groupby("gw").head(1))
    top15 = (j.sort_values("ep", ascending=False).groupby("gw").head(15))
    return {
        "mae_all": round(float(err.mean()), 3),
        "mae_starters": round(float(err_st.mean()), 3),
        "rmse_starters": round(float(((starters["ep"] - starters["total_points"]) ** 2)
                                     .mean() ** 0.5), 3),
        "captain_pts": round(float(cap["total_points"].mean()), 2),
        "top15_pts": round(float(top15.groupby("gw")["total_points"].sum().mean()), 1),
        "n": len(j),
    }
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_train.py -v` — Expected: PASS

- [ ] **Step 5: Manual milestone run — train on 2022-23→2024-25 + 2025-26 GW1-29, evaluate on 2025-26 GW30-38 against baselines.** Create and run `scripts/eval_milestone.py`:

```python
"""Milestone: model quality vs naive baselines on held-out 2025-26 GW30-38."""
import pandas as pd
from gaffer.data import store
from gaffer.models.train import (load_training_frame, train_all,
                                 evaluate_predictions)
from gaffer.models.assemble import assemble_ep, ep_matrix
from gaffer.features.engineer import add_player_rolling, add_context

HOLDOUT_SEASON, HOLDOUT_FROM = 3, 30      # season_idx 3 = 2025-26

df_full, tg_full, elo_final = load_training_frame()
train_df = df_full[(df_full.season_idx < HOLDOUT_SEASON) |
                   ((df_full.season_idx == HOLDOUT_SEASON) &
                    (df_full.gw < HOLDOUT_FROM))]
train_tg = tg_full[(tg_full.season_idx < HOLDOUT_SEASON) |
                   ((tg_full.season_idx == HOLDOUT_SEASON) &
                    (tg_full.gw < HOLDOUT_FROM))]
models = train_all(train_df, train_tg, save=False)

holdout = df_full[(df_full.season_idx == HOLDOUT_SEASON) &
                  (df_full.gw >= HOLDOUT_FROM)]
# Predict components on the holdout rows (features already leakage-safe)
mp = models["minutes"].predict(holdout)
ap = models["attacking"].predict(holdout)
dp = models["defcon"].predict(holdout)
sp = models["saves"].predict(holdout)
bp = models["bonus"].predict(holdout)
tg_holdout = tg_full[(tg_full.season_idx == HOLDOUT_SEASON) &
                     (tg_full.gw >= HOLDOUT_FROM)].dropna(subset=["elo_diff"])
tp = models["team"].predict(tg_holdout)
comp = (holdout[["code", "season_idx", "gw", "position", "team_code"]]
        .merge(mp, on=["code", "season_idx", "gw"])
        .merge(ap, on=["code", "season_idx", "gw"])
        .merge(dp, on=["code", "season_idx", "gw"])
        .merge(sp, on=["code", "season_idx", "gw"])
        .merge(bp, on=["code", "season_idx", "gw"])
        .merge(tp.rename(columns={"code": "team_code"}),
               on=["team_code", "season_idx", "gw"], how="left"))
comp[["p_cs", "e_gc"]] = comp[["p_cs", "e_gc"]].fillna({"p_cs": 0.25, "e_gc": 1.4})
comp["e_cards"] = 0.0
from gaffer.data.bootstrap import scoring_table
import json
scoring = scoring_table(json.load(open("tests/fixtures/bootstrap_sample.json")))
ep = ep_matrix(assemble_ep(comp, scoring))

truth = holdout[["code", "gw", "total_points", "minutes"]]
print("MODEL   :", evaluate_predictions(ep, truth))
# Baselines
last5 = holdout[["code", "gw", "total_points_r5"]].rename(
    columns={"total_points_r5": "ep"}).dropna()
print("LAST-5  :", evaluate_predictions(last5, truth))
ppg = holdout[["code", "gw", "total_points_r38"]].rename(
    columns={"total_points_r38": "ep"}).dropna()
print("SEASON  :", evaluate_predictions(ppg, truth))
```

Run: `uv run python scripts/eval_milestone.py`
Expected: MODEL `mae_starters` < both baselines' (target ≈ 2.0–2.3 vs baselines ≈ 2.4–2.8) and `captain_pts` higher than both. **Record the output, commit the script, and PAUSE — show these numbers to the user before proceeding to Phase D.** (Note: 2025/26 truth includes defcon points and current-ish rules, so this is a fair test. Caveat for the user: bonus model trains on 2025/26 BPS, while 2026/27 BPS is rebalanced — live accuracy will be tracked by Task 24.)

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: training orchestration + milestone evaluation vs baselines"`

### Task 16: Multi-period MILP optimizer

**Files:**
- Create: `src/gaffer/optimize/__init__.py` (empty), `src/gaffer/optimize/milp.py`
- Test: `tests/test_milp.py`

- [ ] **Step 1: Write failing tests** — structural legality + two hand-checkable scenarios. `tests/test_milp.py`:

```python
import pandas as pd
from gaffer.optimize.milp import solve_plan, SolveInput

OWNED = [1, 2,               # GKP x2
         3, 4, 5, 6, 7,      # DEF x5 (of 6 in pool)
         9, 10, 11, 12, 13,  # MID x5 (of 7)
         16, 17, 18]         # FWD x3 (of 5) — a LEGAL 15-man squad

def _pool(star_ep=8.0):
    """20 players: codes 1-2 GKP, 3-8 DEF, 9-15 MID, 16-20 FWD.
    Code 20 (FWD) is the non-owned star."""
    rows = []
    code = 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50, "ep": {1: 2.0, 2: 2.0}})
            code += 1
    rows[-1]["ep"] = {1: star_ep, 2: star_ep}          # code 20, FWD, not owned
    return pd.DataFrame(rows)

def _state(ft=1, bank=0):
    return SolveInput(owned_codes=list(OWNED), bank=bank,
                      free_transfers=ft, gws=[1, 2])

def test_solution_is_legal():
    plan = solve_plan(_pool(), _state(), decay=0.85, bench_weight=0.1,
                      vice_weight=0.1, ft_value=1.5, itb_value=0.05, hit_cost=4)
    gw = plan.gw_plans[0]
    assert len(gw.squad) == 15 and len(gw.xi) == 11
    positions = pd.DataFrame(gw.xi_rows)
    assert (positions["position"] == "GKP").sum() == 1
    assert 3 <= (positions["position"] == "DEF").sum() <= 5
    assert 1 <= (positions["position"] == "FWD").sum() <= 3
    assert gw.captain in gw.xi and gw.vice in gw.xi and gw.captain != gw.vice

def test_transfers_in_star_with_free_transfer():
    plan = solve_plan(_pool(star_ep=9.0), _state(ft=1), decay=0.85,
                      bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                      itb_value=0.05, hit_cost=4)
    assert 20 in plan.gw_plans[0].buys        # +7 EP/GW for a free transfer
    assert plan.gw_plans[0].hits == 0

def test_no_hit_for_marginal_gain():
    # 0 free transfers: +1.5 EP/GW gain over 2 GWs < 4-pt hit -> no transfer
    plan = solve_plan(_pool(star_ep=3.5), _state(ft=0), decay=0.85,
                      bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
                      itb_value=0.05, hit_cost=4)
    assert plan.gw_plans[0].buys == []
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_milp.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/optimize/milp.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
import pulp

SQUAD_COMPOSITION = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_BOUNDS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}

@dataclass
class SolveInput:
    owned_codes: list[int]
    bank: int                    # 0.1m units
    free_transfers: int
    gws: list[int]               # planning horizon, e.g. [3,4,5,6,7,8]
    wildcard_gw: int | None = None
    bench_boost_gw: int | None = None
    triple_captain_gw: int | None = None
    locked_out: list[int] = field(default_factory=list)   # codes banned from squad

@dataclass
class GwPlan:
    gw: int
    squad: list[int]
    xi: list[int]
    xi_rows: list[dict]
    bench: list[int]
    captain: int
    vice: int
    buys: list[int]
    sells: list[int]
    hits: int
    expected_pts: float

@dataclass
class Plan:
    objective: float
    gw_plans: list[GwPlan]

def solve_plan(pool: pd.DataFrame, state: SolveInput, *, decay: float,
               bench_weight: float, vice_weight: float, ft_value: float,
               itb_value: float, hit_cost: int) -> Plan:
    """pool: [code, position, team_code, cost, sell, ep] where ep is a dict
    {gw: expected_points} (missing gw -> 0, e.g. blank GWs).
    Prices are static over the horizon (documented approximation)."""
    pool = pool[~pool["code"].isin(state.locked_out)].reset_index(drop=True)
    codes = pool["code"].tolist()
    pos = dict(zip(pool["code"], pool["position"]))
    club = dict(zip(pool["code"], pool["team_code"]))
    cost = dict(zip(pool["code"], pool["cost"]))
    sell = dict(zip(pool["code"], pool["sell"]))
    ep = {c: {g: pool.loc[pool.code == c, "ep"].iloc[0].get(g, 0.0)
              for g in state.gws} for c in codes}
    owned0 = {c: int(c in state.owned_codes) for c in codes}
    T = state.gws

    prob = pulp.LpProblem("gaffer", pulp.LpMaximize)
    V = pulp.LpVariable.dicts
    sq = V("sq", (codes, T), cat="Binary")
    xi = V("xi", (codes, T), cat="Binary")
    cap = V("cap", (codes, T), cat="Binary")
    vice = V("vc", (codes, T), cat="Binary")
    tin = V("in", (codes, T), cat="Binary")
    tout = V("out", (codes, T), cat="Binary")
    hits = V("hit", T, lowBound=0, cat="Integer")
    ftv = V("ft", T, lowBound=0, upBound=5, cat="Integer")
    bank = V("bank", T, lowBound=0)

    for t_i, t in enumerate(T):
        wc = (state.wildcard_gw == t)
        nt = pulp.lpSum(tin[c][t] for c in codes)
        # squad continuity
        for c in codes:
            prev = owned0[c] if t_i == 0 else sq[c][T[t_i - 1]]
            prob += sq[c][t] == prev + tin[c][t] - tout[c][t]
            prob += tin[c][t] + tout[c][t] <= 1
            prob += xi[c][t] <= sq[c][t]
            prob += cap[c][t] <= xi[c][t]
            prob += vice[c][t] <= xi[c][t]
            prob += cap[c][t] + vice[c][t] <= 1
        # composition
        for p, n in SQUAD_COMPOSITION.items():
            prob += pulp.lpSum(sq[c][t] for c in codes if pos[c] == p) == n
        prob += pulp.lpSum(xi[c][t] for c in codes) == 11
        for p, (lo, hi) in XI_BOUNDS.items():
            n_p = pulp.lpSum(xi[c][t] for c in codes if pos[c] == p)
            prob += n_p >= lo
            prob += n_p <= hi
        prob += pulp.lpSum(cap[c][t] for c in codes) == 1
        prob += pulp.lpSum(vice[c][t] for c in codes) == 1
        for tc in set(club.values()):
            prob += pulp.lpSum(sq[c][t] for c in codes if club[c] == tc) <= 3
        # budget
        inflow = pulp.lpSum(sell[c] * tout[c][t] for c in codes)
        outflow = pulp.lpSum(cost[c] * tin[c][t] for c in codes)
        prev_bank = state.bank if t_i == 0 else bank[T[t_i - 1]]
        prob += bank[t] == prev_bank + inflow - outflow
        # free transfers & hits
        prev_ft = state.free_transfers if t_i == 0 else ftv[T[t_i - 1]]
        if wc:
            prob += hits[t] == 0                 # unlimited free transfers
            prob += ftv[t] <= prev_ft + 1        # banked FTs survive the WC
        else:
            prob += hits[t] >= nt - prev_ft
            prob += ftv[t] <= prev_ft - nt + hits[t] + 1
        prob += ftv[t] <= 5

    obj = []
    for t_i, t in enumerate(T):
        d = decay ** t_i
        cap_mult = 2.0 if state.triple_captain_gw == t else 1.0
        bw = 1.0 if state.bench_boost_gw == t else bench_weight
        for c in codes:
            e = ep[c][t]
            obj.append(d * e * (xi[c][t] + cap_mult * cap[c][t]
                                + vice_weight * vice[c][t]))
            obj.append(d * e * bw * (sq[c][t] - xi[c][t]))
        obj.append(-hit_cost * d * hits[t])
    obj.append(ft_value * ftv[T[-1]])
    obj.append((itb_value / 10.0) * bank[T[-1]])
    prob += pulp.lpSum(obj)

    solver = _solver()
    prob.solve(solver)
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"MILP not optimal: {pulp.LpStatus[prob.status]}")

    def val(v):
        return v.varValue is not None and v.varValue > 0.5

    gw_plans = []
    for t_i, t in enumerate(T):
        squad = [c for c in codes if val(sq[c][t])]
        xi_l = [c for c in codes if val(xi[c][t])]
        bench = sorted((c for c in squad if c not in xi_l),
                       key=lambda c: (pos[c] == "GKP", -ep[c][t]))
        gw_plans.append(GwPlan(
            gw=t, squad=squad, xi=xi_l,
            xi_rows=[{"code": c, "position": pos[c], "ep": ep[c][t]}
                     for c in xi_l],
            bench=bench,
            captain=next(c for c in codes if val(cap[c][t])),
            vice=next(c for c in codes if val(vice[c][t])),
            buys=[c for c in codes if val(tin[c][t])],
            sells=[c for c in codes if val(tout[c][t])],
            hits=int(round(hits[t].varValue or 0)),
            expected_pts=sum(ep[c][t] for c in xi_l)
                         + max((ep[c][t] for c in xi_l), default=0.0),
        ))
    return Plan(objective=pulp.value(prob.objective), gw_plans=gw_plans)

def _solver():
    try:
        return pulp.HiGHS(msg=False)
    except Exception:
        return pulp.PULP_CBC_CMD(msg=False)

def build_pool(players: pd.DataFrame, ep_by_code_gw: dict, my_picks: pd.DataFrame,
               gws: list[int], top_n={"GKP": 8, "DEF": 22, "MID": 26,
                                      "FWD": 14}) -> pd.DataFrame:
    """Candidate pool: owned players + top-N per position by horizon EP.
    Keeps the MILP small (fast) without losing realistic candidates."""
    players = players.copy()
    players["ep"] = players["code"].map(
        lambda c: {g: ep_by_code_gw.get((c, g), 0.0) for g in gws})
    players["h_ep"] = players["ep"].map(lambda d: sum(d.values()))
    owned = set(my_picks["code"])
    keep = []
    for p, n in top_n.items():
        sub = players[players["position"] == p].nlargest(n, "h_ep")
        keep.append(sub)
    pool = pd.concat(keep).drop_duplicates("code")
    pool = pd.concat([pool, players[players["code"].isin(owned)]]) \
             .drop_duplicates("code")
    sell_map = dict(zip(my_picks["code"], my_picks["sell"]))
    pool["cost"] = pool["now_cost"]
    pool["sell"] = pool.apply(
        lambda r: sell_map.get(r["code"], r["now_cost"]), axis=1)
    return pool[["code", "position", "team_code", "cost", "sell", "ep"]]
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_milp.py -v` — Expected: PASS. (If HiGHS is slow in CI-like runs, tests still pass with CBC fallback; both are installed.)

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: multi-period MILP with FT banking, hits, budget, chips hooks"`

### Task 17: Chip scenario evaluation

**Files:**
- Create: `src/gaffer/optimize/chips.py`
- Test: `tests/test_chips.py`

- [ ] **Step 1: Write failing test.** `tests/test_chips.py`:

```python
import pandas as pd
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.chips import evaluate_chips

def _pool():
    rows = []
    code = 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos, "team_code": code % 8,
                         "cost": 50, "sell": 50,
                         "ep": {1: 3.0, 2: 3.0}})
            code += 1
    return pd.DataFrame(rows)

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]  # legal 15

def test_evaluate_chips_returns_delta_per_chip_gw():
    state = SolveInput(owned_codes=list(OWNED), bank=0,
                       free_transfers=1, gws=[1, 2])
    cfg = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
               itb_value=0.05, hit_cost=4)
    table = evaluate_chips(_pool(), state, chips_available=["bboost", "3xc"],
                           **cfg)
    assert {"chip", "gw", "gain"} <= set(table.columns)
    # bench boost on identical 3.0-EP players: gain ≈ 4 players * 3 EP * (1-0.1)
    bb = table[(table.chip == "bboost") & (table.gw == 1)]["gain"].iloc[0]
    assert bb > 8.0
    assert (table["gain"] > -1e-6).all()   # chips never forced to hurt
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_chips.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/optimize/chips.py`**

```python
from __future__ import annotations
from dataclasses import replace
import pandas as pd
from gaffer.optimize.milp import solve_plan, SolveInput, Plan

def evaluate_chips(pool: pd.DataFrame, state: SolveInput,
                   chips_available: list[str], **cfg) -> pd.DataFrame:
    """Objective delta of playing each available chip in each horizon GW vs the
    no-chip plan. Chips: wildcard, bboost, 3xc (freehit separately below).
    Returns [chip, gw, gain] sorted by gain desc."""
    base = solve_plan(pool, state, **cfg)
    rows = []
    for gw in state.gws:
        if "wildcard" in chips_available:
            p = solve_plan(pool, replace(state, wildcard_gw=gw), **cfg)
            rows.append({"chip": "wildcard", "gw": gw,
                         "gain": p.objective - base.objective})
        if "bboost" in chips_available:
            p = solve_plan(pool, replace(state, bench_boost_gw=gw), **cfg)
            rows.append({"chip": "bboost", "gw": gw,
                         "gain": p.objective - base.objective})
        if "3xc" in chips_available:
            p = solve_plan(pool, replace(state, triple_captain_gw=gw), **cfg)
            rows.append({"chip": "3xc", "gw": gw,
                         "gain": p.objective - base.objective})
    if "freehit" in chips_available:
        for gw in state.gws:
            rows.append({"chip": "freehit", "gw": gw,
                         "gain": free_hit_gain(pool, state, gw, **cfg)})
    return (pd.DataFrame(rows)
            .assign(gain=lambda d: d["gain"].round(2))
            .sort_values("gain", ascending=False).reset_index(drop=True))

def free_hit_gain(pool: pd.DataFrame, state: SolveInput, gw: int,
                  **cfg) -> float:
    """FH ≈ (best unrestricted single-GW squad, budget = sell value of current
    squad + bank) minus the baseline plan's EP in that GW. Squad reverts after,
    so other GWs are unchanged — a documented approximation."""
    base = solve_plan(pool, state, **cfg)
    base_gw_ep = next(g.expected_pts for g in base.gw_plans if g.gw == gw)
    budget = state.bank + int(
        pool[pool["code"].isin(state.owned_codes)]["sell"].sum())
    fh_state = SolveInput(owned_codes=[], bank=budget, free_transfers=15,
                          gws=[gw])
    fh = solve_plan(pool, fh_state, **cfg)
    return fh.gw_plans[0].expected_pts - base_gw_ep

def wildcard_now_assessment(pool: pd.DataFrame, state: SolveInput,
                            **cfg) -> dict:
    """The user's 'should I wildcard after bad GW1?' number."""
    base = solve_plan(pool, state, **cfg)
    wc = solve_plan(pool, replace(state, wildcard_gw=state.gws[0]), **cfg)
    return {"gain_over_horizon": round(wc.objective - base.objective, 2),
            "wc_squad": wc.gw_plans[0].squad,
            "recommend": wc.objective - base.objective > 8.0}
```

(`free_transfers=15` in the FH solve just means "no transfer is a hit" for a from-scratch squad build.)

- [ ] **Step 4: Run.** `uv run pytest tests/test_chips.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: chip scenario evaluation incl. wildcard-now assessment"`

### Task 18: Differentials, captain table, threat board

**Files:**
- Create: `src/gaffer/optimize/differentials.py`
- Test: `tests/test_differentials.py`

- [ ] **Step 1: Write failing tests.** `tests/test_differentials.py`:

```python
import pandas as pd
from gaffer.optimize.differentials import captain_table, transfer_alternatives, threat_board

EP = pd.DataFrame({
    "code": [1, 2, 3, 4], "name": ["Salah", "Haaland", "Punt", "Gordon"],
    "position": ["MID", "FWD", "MID", "MID"],
    "ep": [8.0, 7.8, 7.6, 5.0], "p_haul": [0.4, 0.45, 0.5, 0.2],
})
EO = {1: 90.0, 2: 80.0, 3: 5.0, 4: 60.0}

def test_captain_table_flags_differential():
    t = captain_table(EP, xi_codes=[1, 2, 3], league_eo=EO, top=3)
    assert t.iloc[0]["code"] == 1                      # highest EP first
    assert t[t.code == 3]["differential"].iloc[0]      # low EO + high ceiling
    assert not t[t.code == 1]["differential"].iloc[0]

def test_transfer_alternatives_within_margin_low_eo():
    alts = transfer_alternatives(EP, buy_code=1, league_eo=EO, margin=0.5)
    assert alts["code"].tolist() == [3]     # within 0.5 EP, EO<20, same position

def test_threat_board_lists_unowned_high_eo():
    t = threat_board(EP, my_codes=[1], league_eo=EO, min_eo=50.0)
    assert t["code"].tolist() == [2, 4]     # sorted by EP desc
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_differentials.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/optimize/differentials.py`**

```python
from __future__ import annotations
import pandas as pd

def _with_eo(ep: pd.DataFrame, league_eo: dict[int, float]) -> pd.DataFrame:
    df = ep.copy()
    df["league_eo"] = df["code"].map(league_eo).fillna(0.0)
    return df

def captain_table(ep: pd.DataFrame, xi_codes: list[int],
                  league_eo: dict[int, float], top: int = 5) -> pd.DataFrame:
    """Top captain candidates from the recommended XI with EV, ceiling and
    rival ownership. 'differential' = EO < 30% and above-median ceiling."""
    df = _with_eo(ep[ep["code"].isin(xi_codes)], league_eo)
    df = df.nlargest(top, "ep").reset_index(drop=True)
    median_haul = df["p_haul"].median()
    df["differential"] = (df["league_eo"] < 30.0) & (df["p_haul"] >= median_haul)
    return df[["code", "name", "position", "ep", "p_haul", "league_eo",
               "differential"]]

def transfer_alternatives(ep: pd.DataFrame, buy_code: int,
                          league_eo: dict[int, float],
                          margin: float = 0.5) -> pd.DataFrame:
    """Same-position players within `margin` EP of the recommended buy but
    with league EO < 20% — the 'if you want to be brave' list."""
    df = _with_eo(ep, league_eo)
    rec = df[df["code"] == buy_code].iloc[0]
    alts = df[(df["position"] == rec["position"]) & (df["code"] != buy_code)
              & (df["ep"] >= rec["ep"] - margin) & (df["league_eo"] < 20.0)]
    return alts.sort_values("ep", ascending=False)[
        ["code", "name", "ep", "p_haul", "league_eo"]].reset_index(drop=True)

def threat_board(ep: pd.DataFrame, my_codes: list[int],
                 league_eo: dict[int, float], min_eo: float = 50.0) -> pd.DataFrame:
    """High-EO rival players you don't own, by EP — your exposure if they haul."""
    df = _with_eo(ep, league_eo)
    threats = df[(~df["code"].isin(my_codes)) & (df["league_eo"] >= min_eo)]
    return threats.sort_values("ep", ascending=False)[
        ["code", "name", "position", "ep", "league_eo"]].reset_index(drop=True)
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_differentials.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: captain table, differential alternatives, threat board"`

### Task 19: Price watch

**Files:**
- Create: `src/gaffer/prices.py`
- Test: `tests/test_prices.py`

- [ ] **Step 1: Write failing test.** `tests/test_prices.py`:

```python
import pandas as pd
from gaffer.prices import price_alerts

PLAYERS = pd.DataFrame([
    {"code": 1, "name": "Riser", "price_change_percent": 94.0,
     "price_change_calibrating": False},
    {"code": 2, "name": "Faller", "price_change_percent": -91.0,
     "price_change_calibrating": False},
    {"code": 3, "name": "Stable", "price_change_percent": 10.0,
     "price_change_calibrating": False},
    {"code": 4, "name": "NewSigning", "price_change_percent": 99.0,
     "price_change_calibrating": True},
])

def test_price_alerts_flags_imminent_and_relevant():
    alerts = price_alerts(PLAYERS, watch_codes=[1, 2, 3, 4], threshold=90.0)
    flagged = dict(zip(alerts["code"], alerts["direction"]))
    assert flagged[1] == "rise" and flagged[2] == "drop"
    assert 3 not in flagged
    assert alerts[alerts.code == 4]["calibrating"].iloc[0]  # shown but labeled
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_prices.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/prices.py`**

```python
from __future__ import annotations
import pandas as pd

def price_alerts(players: pd.DataFrame, watch_codes: list[int],
                 threshold: float = 90.0) -> pd.DataFrame:
    """Imminent price changes among watched players (owned + planned moves),
    from FPL's official predictor fields. price_change_percent hits +/-100 at
    the nightly 00:00 UK change; `threshold` flags anything close.
    Calibrating players are included but labeled (early-season caveat)."""
    df = players[players["code"].isin(watch_codes)].copy()
    pct = df["price_change_percent"].fillna(0.0)
    df = df[pct.abs() >= threshold]
    df["direction"] = (df["price_change_percent"] > 0).map(
        {True: "rise", False: "drop"})
    df["calibrating"] = df["price_change_calibrating"].fillna(False)
    return df[["code", "name", "price_change_percent", "direction",
               "calibrating"]].sort_values("price_change_percent",
                                           key=abs, ascending=False)
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_prices.py -v` — Expected: PASS

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: price alerts from official predictor fields"`

### Task 20: Advise orchestration

**Files:**
- Create: `src/gaffer/advise.py`
- Test: `tests/test_advise.py`

This module glues everything: refresh → prediction frame → components → EP → pool → MILP → chips → differentials → prices → `Advice` payload (also written to `reports/gw{N}-advice.json` and a predictions log for Task 24).

- [ ] **Step 1: Write failing test for the pure helpers** (`future_fixture_frame`, `predict_components`) — full orchestration is network-bound and validated manually in Step 5. `tests/test_advise.py`:

```python
import pandas as pd
from gaffer.advise import future_fixture_frame

def test_future_fixture_frame_one_row_per_player_fixture():
    fixtures = pd.DataFrame([
        {"gw": 2, "home_id": 1, "away_id": 2, "kickoff_time": "2026-08-28T19:00:00Z"},
        {"gw": 3, "home_id": 2, "away_id": 1, "kickoff_time": "2026-09-04T19:00:00Z"},
    ])
    players = pd.DataFrame([
        {"code": 10, "element": 5, "name": "A", "position": "MID",
         "team_id": 1, "team_code": 100},
        {"code": 11, "element": 6, "name": "B", "position": "DEF",
         "team_id": 2, "team_code": 200},
    ])
    teams = pd.DataFrame([{"team_id": 1, "code": 100}, {"team_id": 2, "code": 200}])
    ff = future_fixture_frame(fixtures, players, teams, gws=[2, 3],
                              season_idx=4)
    assert len(ff) == 4                       # 2 players x 2 fixtures
    row = ff[(ff.code == 10) & (ff.gw == 2)].iloc[0]
    assert row["was_home"] == True and row["opp_code"] == 200
    row3 = ff[(ff.code == 10) & (ff.gw == 3)].iloc[0]
    assert row3["was_home"] == False
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_advise.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/advise.py`**

```python
from __future__ import annotations
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
import pandas as pd

from gaffer.config import Config
from gaffer.api.client import FPLClient
from gaffer.data import store
from gaffer.data.bootstrap import (build_players, build_teams, build_events,
                                   next_gw, scoring_table)
from gaffer.data.live import refresh_live
from gaffer.data.entry import fetch_my_team
from gaffer.data.league import (fetch_rival_entries, fetch_rival_picks,
                                effective_ownership)
from gaffer.features.engineer import build_prediction_frame
from gaffer.models.persistence import load_model, model_exists
from gaffer.models.minutes import apply_availability
from gaffer.models.team import add_team_rolling, build_team_gw
from gaffer.models.assemble import assemble_ep, ep_matrix
from gaffer.models.components import card_penalty
from gaffer.models.train import load_training_frame
from gaffer.optimize.milp import solve_plan, SolveInput, build_pool
from gaffer.optimize.chips import evaluate_chips, wildcard_now_assessment
from gaffer.optimize.differentials import (captain_table,
                                           transfer_alternatives, threat_board)
from gaffer.prices import price_alerts

REPORTS = Path("reports")

@dataclass
class Advice:
    gw: int
    deadline: str
    buys: list[dict]
    sells: list[dict]
    hits: int
    xi: list[dict]
    bench: list[dict]
    captain: dict
    vice: dict
    captain_options: list[dict]
    chip_table: list[dict]
    wildcard_now: dict
    alternatives: list[dict]
    threats: list[dict]
    price_alerts: list[dict]
    expected_pts: float
    plan_by_gw: list[dict] = field(default_factory=list)

def future_fixture_frame(fixtures: pd.DataFrame, players: pd.DataFrame,
                         teams: pd.DataFrame, gws: list[int],
                         season_idx: int) -> pd.DataFrame:
    """One row per player per upcoming fixture in `gws`.
    fixtures: [gw, home_id, away_id, kickoff_time] (team ids)."""
    code_of = dict(zip(teams["team_id"], teams["code"]))
    fx = fixtures[fixtures["gw"].isin(gws)]
    rows = []
    for m in fx.itertuples():
        for side, opp, home in ((m.home_id, m.away_id, True),
                                (m.away_id, m.home_id, False)):
            side_players = players[players["team_id"] == side]
            for p in side_players.itertuples():
                rows.append({"code": p.code, "element": p.element,
                             "name": p.name, "position": p.position,
                             "team_code": p.team_code,
                             "opp_code": code_of[opp], "was_home": home,
                             "gw": m.gw, "season_idx": season_idx,
                             "kickoff_time": m.kickoff_time})
    return pd.DataFrame(rows)

def predict_components(pred_frame: pd.DataFrame, tg_future: pd.DataFrame,
                       players: pd.DataFrame) -> pd.DataFrame:
    pred_frame = pred_frame.copy()
    pred_frame["e_cards"] = pred_frame.apply(card_penalty, axis=1)
    minutes = load_model("minutes").predict(pred_frame)
    avail = players[["code", "status", "chance_of_playing"]]
    minutes = apply_availability(minutes, avail)
    keys = ["code", "season_idx", "gw"]
    comp = (pred_frame[keys + ["position", "team_code", "e_cards"]]
            .merge(minutes, on=keys)
            .merge(load_model("attacking").predict(pred_frame), on=keys)
            .merge(load_model("defcon").predict(pred_frame), on=keys)
            .merge(load_model("saves").predict(pred_frame), on=keys)
            .merge(load_model("bonus").predict(pred_frame), on=keys))
    team_pred = load_model("team").predict(tg_future).rename(
        columns={"code": "team_code"})
    comp = comp.merge(team_pred, on=["team_code", "season_idx", "gw"],
                      how="left")
    comp["p_cs"] = comp["p_cs"].fillna(0.25)
    comp["e_gc"] = comp["e_gc"].fillna(1.4)
    return comp

def run_advise(cfg: Config, client: FPLClient | None = None) -> Advice:
    client = client or FPLClient()
    for name in ["minutes", "team", "attacking", "defcon", "saves", "bonus"]:
        if not model_exists(name):
            raise SystemExit(f"Model '{name}' missing — run `gaffer train` first.")

    raw = client.get_bootstrap()
    players = build_players(raw)
    teams = build_teams(raw)
    events = build_events(raw)
    gw = next_gw(raw)
    deadline = events.loc[events["gw"] == gw, "deadline_time"].iloc[0]
    gws = [g for g in range(gw, min(gw + cfg.horizon, 39))]

    # 1) refresh live data + fixtures
    season_idx_live = len(cfg.train_seasons)          # 4 for 2026-27
    refresh_live(client, cfg.current_season, season_idx_live)
    fx_raw = client.get_fixtures()
    fx = pd.DataFrame([{"gw": f.get("event"), "home_id": f["team_h"],
                        "away_id": f["team_a"],
                        "kickoff_time": f["kickoff_time"],
                        "home_goals": f.get("team_h_score"),
                        "away_goals": f.get("team_a_score"),
                        "finished": f.get("finished", False)}
                       for f in fx_raw if f.get("event")])
    code_of = dict(zip(teams["team_id"], teams["code"]))
    done = fx[fx["finished"]]
    store.save(pd.DataFrame({
        "season_idx": season_idx_live, "gw": done["gw"],
        "kickoff_time": done["kickoff_time"],
        "home_code": done["home_id"].map(code_of),
        "away_code": done["away_id"].map(code_of),
        "home_goals": done["home_goals"], "away_goals": done["away_goals"],
    }), "live/fixtures.parquet")

    # 2) features for future fixtures
    hist, tg, elo_final = load_training_frame()
    future = future_fixture_frame(fx, players, teams, gws, season_idx_live)
    pred_frame = build_prediction_frame(
        hist, future, elo=None, elo_final=elo_final)
    pred_frame["team_elo"] = pred_frame["team_code"].map(elo_final)
    pred_frame["opp_elo"] = pred_frame["opp_code"].map(elo_final)
    pred_frame["elo_diff"] = pred_frame["team_elo"] - pred_frame["opp_elo"]

    tg_future = future[["team_code", "opp_code", "was_home", "gw",
                        "season_idx", "kickoff_time"]].drop_duplicates()
    tg_future = tg_future.rename(columns={"team_code": "code"})
    tg_future["home"] = tg_future["was_home"].astype(float)
    tg_hist_plus = pd.concat([tg, tg_future], ignore_index=True)
    tg_all = add_team_rolling(tg_hist_plus)
    tg_future = tg_all[tg_all["gw"].isin(gws)
                       & (tg_all["season_idx"] == season_idx_live)].copy()
    tg_future["team_elo_own"] = tg_future["code"].map(elo_final)
    tg_future["opp_elo"] = tg_future["opp_code"].map(elo_final)
    tg_future["elo_diff"] = tg_future["team_elo_own"] - tg_future["opp_elo"]

    # 3) predict + assemble
    comp = predict_components(pred_frame, tg_future, players)
    scoring = scoring_table(raw)
    per_fixture = assemble_ep(comp, scoring)
    ep = ep_matrix(per_fixture)
    ep_named = ep.merge(players[["code", "name", "position"]], on="code")
    # predictions log for model-health tracking (Task 24)
    store.save(ep_named[ep_named["gw"] == gw],
               f"live/predictions/gw{gw}.parquet")

    # 4) my team, rivals, optimize
    my = fetch_my_team(client, cfg.entry_id, gw, players)
    ep_by = {(r.code, r.gw): r.ep for r in ep.itertuples()}
    pool = build_pool(players, ep_by, my.picks, gws)
    state = SolveInput(owned_codes=my.picks["code"].tolist(), bank=my.bank,
                       free_transfers=my.free_transfers, gws=gws)
    opt_kw = dict(decay=cfg.decay, bench_weight=cfg.bench_weight,
                  vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                  itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
    plan = solve_plan(pool, state, **opt_kw)
    first = plan.gw_plans[0]

    # 5) chips, rivals, differentials, prices
    # chips reset per half-season (first set expires at GW19 deadline):
    # only chips already used in THIS half are spent
    used_this_half = {name for g, name in my.chips_by_gw.items()
                      if (g <= 19) == (gw <= 19)}
    chip_names = [c for c in ["wildcard", "freehit", "bboost", "3xc"]
                  if c not in used_this_half]
    chip_table = evaluate_chips(pool, state, chip_names, **opt_kw)
    wc_now = wildcard_now_assessment(pool, state, **opt_kw)

    league_eo: dict[int, float] = {}
    if cfg.league_id:
        rivals = fetch_rival_entries(client, cfg.league_id, cfg.entry_id)
        picks = fetch_rival_picks(client, rivals["entry"].tolist(), gw - 1)
        eo_by_element = effective_ownership(picks)
        el_to_code = dict(zip(players["element"], players["code"]))
        league_eo = {el_to_code.get(el): v for el, v in eo_by_element.items()
                     if el_to_code.get(el)}

    ep_gw1 = ep_named[ep_named["gw"] == gw]
    cap_tab = captain_table(ep_gw1, first.xi, league_eo)
    alts = (transfer_alternatives(ep_gw1, first.buys[0], league_eo)
            if first.buys else pd.DataFrame())
    threats = threat_board(ep_gw1, first.squad, league_eo)
    watch = list({*first.buys, *first.sells, *my.picks["code"]})
    alerts = price_alerts(players, watch)

    name_of = dict(zip(players["code"], players["name"]))
    def named(codes, gw_=gw):
        return [{"code": c, "name": name_of.get(c, "?"),
                 "ep": round(ep_by.get((c, gw_), 0.0), 2)} for c in codes]

    advice = Advice(
        gw=gw, deadline=str(deadline),
        buys=named(first.buys), sells=named(first.sells), hits=first.hits,
        xi=named(first.xi), bench=named(first.bench),
        captain=named([first.captain])[0], vice=named([first.vice])[0],
        captain_options=cap_tab.to_dict("records"),
        chip_table=chip_table.head(8).to_dict("records"),
        wildcard_now={k: v for k, v in wc_now.items() if k != "wc_squad"},
        alternatives=alts.to_dict("records") if len(alts) else [],
        threats=threats.head(8).to_dict("records"),
        price_alerts=alerts.to_dict("records"),
        expected_pts=round(first.expected_pts, 1),
        plan_by_gw=[{"gw": g.gw, "buys": named(g.buys, g.gw),
                     "sells": named(g.sells, g.gw), "hits": g.hits}
                    for g in plan.gw_plans],
    )
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"gw{gw}-advice.json").write_text(
        json.dumps(asdict(advice), indent=1, default=str))
    return advice
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_advise.py -v` — Expected: PASS

- [ ] **Step 5: Manual end-to-end smoke test** (requires `config.toml` filled with the user's real `entry_id`/`league_id`, trained models from Task 15, and network):

```bash
uv run python -c "
from gaffer.config import load_config
from gaffer.advise import run_advise
a = run_advise(load_config())
print('GW', a.gw, 'deadline', a.deadline)
print('BUY :', a.buys, 'SELL:', a.sells, 'hits', a.hits)
print('CAP :', a.captain, 'VICE:', a.vice)
print('CHIPS:', a.chip_table[:3])
print('WC now:', a.wildcard_now)
"
```
Expected: a coherent action list for the next GW in under ~5 minutes (600 element-summary calls dominate). Sanity-check by eye: XI is a legal formation, captain is a plausible premium, buys/sells make football sense.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: advise orchestration producing full weekly Advice payload"`

### Task 21: HTML report

**Files:**
- Create: `src/gaffer/report/__init__.py` (empty), `src/gaffer/report/render.py`, `src/gaffer/report/templates/report.html.j2`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write failing test.** `tests/test_report.py`:

```python
from gaffer.advise import Advice
from gaffer.report.render import render_report

def _advice():
    return Advice(
        gw=3, deadline="2026-09-04T17:30:00Z",
        buys=[{"code": 20, "name": "Star", "ep": 7.5}],
        sells=[{"code": 9, "name": "Dud", "ep": 1.2}], hits=0,
        xi=[{"code": i, "name": f"P{i}", "ep": 4.0} for i in range(11)],
        bench=[{"code": i, "name": f"B{i}", "ep": 1.0} for i in range(4)],
        captain={"code": 1, "name": "P1", "ep": 8.0},
        vice={"code": 2, "name": "P2", "ep": 7.0},
        captain_options=[{"code": 1, "name": "P1", "position": "MID",
                          "ep": 8.0, "p_haul": 0.4, "league_eo": 80.0,
                          "differential": False}],
        chip_table=[{"chip": "bboost", "gw": 5, "gain": 6.2}],
        wildcard_now={"gain_over_horizon": 3.1, "recommend": False},
        alternatives=[], threats=[], price_alerts=[],
        expected_pts=61.5, plan_by_gw=[],
    )

def test_render_report_produces_html_with_key_content(tmp_path):
    path = render_report(_advice(), out_dir=tmp_path)
    html = path.read_text()
    assert "GW3" in html and "Star" in html and "Dud" in html
    assert "bboost" in html and "61.5" in html
    assert path.name == "gw3-report.html"
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_report.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/report/render.py`**

```python
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from gaffer.advise import Advice

def render_report(advice: Advice, out_dir: Path | str = "reports",
                  model_health: dict | None = None) -> Path:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=True)
    html = env.get_template("report.html.j2").render(
        a=asdict(advice), health=model_health or {})
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    path = out / f"gw{advice.gw}-report.html"
    path.write_text(html)
    return path
```

- [ ] **Step 4: Create `src/gaffer/report/templates/report.html.j2`**

```html
<!doctype html>
<html><head><meta charset="utf-8">
<title>gaffer — GW{{ a.gw }}</title>
<style>
 body{font:15px/1.5 -apple-system,Helvetica,sans-serif;margin:2rem auto;
      max-width:900px;padding:0 1rem;color:#1a1a2e}
 h1{border-bottom:3px solid #37003c} h2{color:#37003c;margin-top:2rem}
 table{border-collapse:collapse;width:100%;margin:.5rem 0}
 th,td{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}
 th{background:#37003c;color:#fff} tr:nth-child(even){background:#f7f7fb}
 .action{background:#e8f5e9;border-left:4px solid #2e7d32;padding:1rem;
         margin:1rem 0} .warn{background:#fff3e0;border-left:4px solid #ef6c00;
         padding:.6rem;margin:.5rem 0}
 .diff{color:#2e7d32;font-weight:600}
</style></head><body>
<h1>gaffer — Gameweek {{ a.gw }}</h1>
<p>Deadline: <strong>{{ a.deadline }}</strong> ·
   Expected XI points: <strong>{{ a.expected_pts }}</strong></p>

<div class="action"><h2 style="margin-top:0">This week's actions</h2>
<ul>
{% for b in a.buys %}<li>BUY <strong>{{ b.name }}</strong> ({{ b.ep }} xPts)</li>{% endfor %}
{% for s in a.sells %}<li>SELL <strong>{{ s.name }}</strong> ({{ s.ep }} xPts)</li>{% endfor %}
{% if not a.buys %}<li>No transfers — bank the free transfer.</li>{% endif %}
{% if a.hits %}<li class="warn">Taking {{ a.hits }} hit(s): −{{ a.hits * 4 }} pts, maths clears it.</li>{% endif %}
<li>Captain: <strong>{{ a.captain.name }}</strong> · Vice: <strong>{{ a.vice.name }}</strong></li>
</ul></div>

<h2>Starting XI & bench order</h2>
<table><tr><th>#</th><th>XI</th><th>xPts</th></tr>
{% for p in a.xi %}<tr><td>{{ loop.index }}</td><td>{{ p.name }}</td><td>{{ p.ep }}</td></tr>{% endfor %}
</table>
<p>Bench (in order): {% for p in a.bench %}{{ p.name }} ({{ p.ep }}){{ ", " if not loop.last }}{% endfor %}</p>

<h2>Captain options</h2>
<table><tr><th>Player</th><th>xPts</th><th>P(haul)</th><th>League EO%</th><th></th></tr>
{% for c in a.captain_options %}
<tr><td>{{ c.name }}</td><td>{{ "%.2f"|format(c.ep) }}</td>
    <td>{{ "%.0f%%"|format(c.p_haul * 100) }}</td><td>{{ c.league_eo }}</td>
    <td>{% if c.differential %}<span class="diff">differential</span>{% endif %}</td></tr>
{% endfor %}</table>

<h2>Chips</h2>
<table><tr><th>Chip</th><th>GW</th><th>Expected gain</th></tr>
{% for c in a.chip_table %}<tr><td>{{ c.chip }}</td><td>{{ c.gw }}</td><td>{{ c.gain }}</td></tr>{% endfor %}
</table>
<p>Wildcard now: gain {{ a.wildcard_now.gain_over_horizon }} pts over horizon —
<strong>{{ "recommended" if a.wildcard_now.recommend else "not recommended" }}</strong></p>

{% if a.alternatives %}<h2>Differential alternatives</h2>
<table><tr><th>Player</th><th>xPts</th><th>P(haul)</th><th>League EO%</th></tr>
{% for x in a.alternatives %}<tr><td>{{ x.name }}</td><td>{{ "%.2f"|format(x.ep) }}</td>
<td>{{ "%.0f%%"|format(x.p_haul * 100) }}</td><td>{{ x.league_eo }}</td></tr>{% endfor %}
</table>{% endif %}

{% if a.threats %}<h2>Threat board — high-EO players you don't own</h2>
<table><tr><th>Player</th><th>Pos</th><th>xPts</th><th>League EO%</th></tr>
{% for t in a.threats %}<tr><td>{{ t.name }}</td><td>{{ t.position }}</td>
<td>{{ "%.2f"|format(t.ep) }}</td><td>{{ t.league_eo }}</td></tr>{% endfor %}
</table>{% endif %}

{% if a.price_alerts %}<h2>Price alerts (tonight, 00:00 UK)</h2>
{% for p in a.price_alerts %}<p class="warn">{{ p.name }} — projected
{{ p.direction }} ({{ p.price_change_percent }}%)
{% if p.calibrating %}[calibrating — low confidence]{% endif %}</p>{% endfor %}
{% endif %}

{% if a.plan_by_gw %}<h2>Multi-week plan</h2>
<table><tr><th>GW</th><th>Buys</th><th>Sells</th><th>Hits</th></tr>
{% for g in a.plan_by_gw %}<tr><td>{{ g.gw }}</td>
<td>{% for b in g.buys %}{{ b.name }}{{ ", " if not loop.last }}{% endfor %}</td>
<td>{% for s in g.sells %}{{ s.name }}{{ ", " if not loop.last }}{% endfor %}</td>
<td>{{ g.hits }}</td></tr>{% endfor %}</table>{% endif %}

{% if health %}<h2>Model health</h2>
<p>Last GW: MAE (starters) {{ health.mae_starters }} ·
   captain pick scored {{ health.captain_actual }} pts ·
   advice plan {{ health.advice_pts }} vs your actual {{ health.actual_pts }}</p>
{% endif %}
</body></html>
```

- [ ] **Step 5: Run.** `uv run pytest tests/test_report.py -v` — Expected: PASS

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: HTML gameweek report"`

### Task 22: CLI wiring

**Files:**
- Create: `src/gaffer/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test.** `tests/test_cli.py`:

```python
from typer.testing import CliRunner
from gaffer.cli import app

runner = CliRunner()

def test_cli_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["advise", "refresh", "train", "prices", "league", "backtest"]:
        assert cmd in result.output

def test_advise_fails_cleanly_without_models(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 0\n')
    result = runner.invoke(app, ["advise"])
    assert result.exit_code != 0
    assert "gaffer train" in result.output
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_cli.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/cli.py`**

```python
from __future__ import annotations
import typer

app = typer.Typer(help="FPL ML advisor", no_args_is_help=True)

@app.command()
def advise():
    """Full weekly run: refresh -> predict -> optimize -> report."""
    from gaffer.config import load_config
    from gaffer.advise import run_advise
    from gaffer.report.render import render_report
    cfg = load_config()
    if not cfg.entry_id:
        typer.echo("Set fpl.entry_id in config.toml first.")
        raise typer.Exit(1)
    try:
        advice = run_advise(cfg)
    except SystemExit as e:
        typer.echo(str(e))
        raise typer.Exit(1)
    try:                                   # tracking module arrives in Task 24
        from gaffer.tracking import latest_health
        health = latest_health()
    except ImportError:
        health = None
    path = render_report(advice, model_health=health)
    typer.echo(f"\n=== GW{advice.gw} — deadline {advice.deadline} ===")
    for b in advice.buys:
        typer.echo(f"BUY  {b['name']} ({b['ep']} xPts)")
    for s in advice.sells:
        typer.echo(f"SELL {s['name']} ({s['ep']} xPts)")
    if not advice.buys:
        typer.echo("No transfers — bank the FT.")
    if advice.hits:
        typer.echo(f"Hits: -{advice.hits * 4}")
    typer.echo(f"Captain: {advice.captain['name']} | Vice: {advice.vice['name']}")
    typer.echo(f"Expected XI points: {advice.expected_pts}")
    typer.echo(f"Report: {path}")

@app.command()
def refresh():
    """Pull latest FPL data into data/live/."""
    from gaffer.config import load_config
    from gaffer.api.client import FPLClient
    from gaffer.data.live import refresh_live
    cfg = load_config()
    df = refresh_live(FPLClient(), cfg.current_season, len(cfg.train_seasons))
    typer.echo(f"Refreshed {len(df)} player-GW rows.")

@app.command()
def train():
    """(Re)train all models on history + live data."""
    from gaffer.models.train import load_training_frame, train_all
    df, tg, _ = load_training_frame()
    train_all(df, tg, save=True)
    typer.echo(f"Trained on {len(df)} player-GW rows. Models saved to models/.")

@app.command()
def prices():
    """Tonight's likely price changes among relevant players."""
    from gaffer.api.client import FPLClient
    from gaffer.data.bootstrap import build_players
    from gaffer.prices import price_alerts
    players = build_players(FPLClient().get_bootstrap())
    watch = players.nlargest(200, "selected_by_percent")["code"].tolist()
    alerts = price_alerts(players, watch)
    if alerts.empty:
        typer.echo("No imminent price changes among watched players.")
    for r in alerts.itertuples():
        cal = " [calibrating]" if r.calibrating else ""
        typer.echo(f"{r.name}: {r.direction} ({r.price_change_percent}%){cal}")

@app.command()
def league():
    """Mini-league standings and rival ownership."""
    from gaffer.config import load_config
    from gaffer.api.client import FPLClient
    from gaffer.data.league import fetch_rival_entries
    cfg = load_config()
    rivals = fetch_rival_entries(FPLClient(), cfg.league_id, cfg.entry_id)
    typer.echo(rivals.to_string(index=False))

@app.command()
def backtest(season: str = "2025-26", start_gw: int = 5):
    """Replay a past season following the tool's advice."""
    from gaffer.backtest import run_backtest
    result = run_backtest(season, start_gw)
    typer.echo(result)

def main():
    app()
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_cli.py -v` — Expected: PASS. (`run_advise` raises `SystemExit` mentioning `gaffer train` when models are missing, which fires before any network call; `gaffer.tracking` and `gaffer.backtest` are imported lazily/guarded, so the CLI works before Tasks 23–24 exist.)

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat: typer CLI (advise/refresh/train/prices/league/backtest)"`

### Task 23: Backtest harness — **MILESTONE GATE**

**Files:**
- Create: `src/gaffer/backtest.py`
- Test: `tests/test_backtest.py`

Documented v1 simplifications: no chips; captain→vice fallback when captain doesn't play; simplified autosubs (bench players in EP order replace non-playing starters when the resulting formation stays legal); prices static at each GW's actual values from history (`value` column); models retrained every 4 GWs (speed).

- [ ] **Step 1: Write failing tests for the pure scoring helpers.** `tests/test_backtest.py`:

```python
import pandas as pd
from gaffer.backtest import score_gw

def _actuals():
    """Legal XI: code 1 GKP, 2-6 DEF, 7-10 MID, 11 FWD; bench 12-15 MID."""
    spec = {1: (10, 90, "GKP"),                      # captain, hauled
            2: (2, 90, "DEF"), 3: (2, 90, "DEF"), 4: (2, 90, "DEF"),
            5: (0, 0, "DEF"),                        # starter, didn't play
            6: (2, 90, "DEF"),
            7: (2, 90, "MID"), 8: (2, 90, "MID"),
            9: (2, 90, "MID"), 10: (2, 90, "MID"),
            11: (2, 90, "FWD"),
            12: (6, 90, "MID"),                      # bench, played -> subs in
            13: (2, 90, "MID"), 14: (2, 90, "MID"), 15: (2, 90, "MID")}
    return pd.DataFrame([{"code": c, "total_points": p, "minutes": m,
                          "position": pos} for c, (p, m, pos) in spec.items()])

def test_score_gw_captain_doubles_and_autosub():
    xi = list(range(1, 12))       # includes code 5 (0 mins)
    bench = [12, 13, 14, 15]
    pts = score_gw(_actuals(), xi=xi, bench=bench, captain=1, vice=2, hits=1)
    # XI without 5: 10(GK) + 4*2(DEF) + 4*2(MID) + 2(FWD) = 28
    # sub 12 in for 5 (formation 1-4-5-1, legal): +6 = 34
    # captain 1 played -> +10 = 44 ; one hit -> -4 => 40
    assert pts == 40

def test_score_gw_vice_takes_over_when_captain_blanks():
    actuals = _actuals()
    actuals.loc[actuals.code == 1, ["total_points", "minutes"]] = [0, 0]
    pts = score_gw(actuals, xi=list(range(1, 12)), bench=[12, 13, 14, 15],
                   captain=1, vice=2, hits=0)
    # GK blanked; no GK on the bench so no legal sub for him. Code 5 still
    # subs out for 12: 0 + 4*2 + 8 + 2 + 6 = 24
    # captain 0 mins -> vice code 2 doubles: +2 => 26
    assert pts == 26
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_backtest.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/backtest.py`**

```python
from __future__ import annotations
import pandas as pd
from gaffer.config import load_config
from gaffer.data import store
from gaffer.features.engineer import build_prediction_frame
from gaffer.models.train import load_training_frame, train_all
from gaffer.models.assemble import assemble_ep, ep_matrix
from gaffer.models.components import card_penalty
from gaffer.optimize.milp import solve_plan, SolveInput, build_pool

XI_BOUNDS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}

def _formation_legal(positions: list[str]) -> bool:
    from collections import Counter
    c = Counter(positions)
    return (len(positions) == 11
            and all(lo <= c.get(p, 0) <= hi
                    for p, (lo, hi) in XI_BOUNDS.items()))

def score_gw(actuals: pd.DataFrame, xi: list[int], bench: list[int],
             captain: int, vice: int, hits: int) -> int:
    """Actual FPL points for a picked team given real outcomes.
    actuals: [code, total_points, minutes, position]."""
    a = actuals.set_index("code")
    pts_of = a["total_points"].to_dict()
    mins_of = a["minutes"].to_dict()
    pos_of = a["position"].to_dict()

    final_xi = list(xi)
    for starter in xi:
        if mins_of.get(starter, 0) == 0:
            for sub in bench:
                if sub in final_xi or mins_of.get(sub, 0) == 0:
                    continue
                candidate = [c for c in final_xi if c != starter] + [sub]
                if _formation_legal([pos_of.get(c, "MID") for c in candidate]):
                    final_xi = candidate
                    break
    total = sum(pts_of.get(c, 0) for c in final_xi)
    cap_pts = pts_of.get(captain, 0) if mins_of.get(captain, 0) > 0 else None
    if cap_pts is not None:
        total += cap_pts
    elif mins_of.get(vice, 0) > 0:
        total += pts_of.get(vice, 0)
    return int(total - 4 * hits)

def run_backtest(season: str = "2025-26", start_gw: int = 5,
                 retrain_every: int = 4) -> dict:
    cfg = load_config()
    season_idx = cfg.train_seasons.index(season)
    full, tg_full, _ = load_training_frame()
    season_df = full[full["season_idx"] == season_idx]

    # start squad: cheap-ish legal squad picked by the optimizer itself at start_gw
    models = None
    team_state = None
    total_pts = 0
    log = []
    for gw in range(start_gw, 39):
        if models is None or (gw - start_gw) % retrain_every == 0:
            df, tg, _elo = load_training_frame(max_season_idx=season_idx,
                                               max_gw=gw)
            models = train_all(df, tg, save=False)

        gw_rows = season_df[season_df["gw"] == gw]
        if gw_rows.empty:
            continue
        # Predict with features already computed on the truncated frame:
        hist_upto = full[(full["season_idx"] < season_idx)
                         | ((full["season_idx"] == season_idx)
                            & (full["gw"] < gw))]
        future = gw_rows[["code", "season_idx", "gw", "position", "team_code",
                          "opp_code", "was_home", "kickoff_time",
                          "name"]].copy()
        pf = build_prediction_frame(hist_upto, future)
        comp = pf[["code", "season_idx", "gw", "position", "team_code"]].copy()
        mp = models["minutes"].predict(pf)
        comp = comp.merge(mp, on=["code", "season_idx", "gw"])
        for name in ["attacking", "defcon", "saves", "bonus"]:
            comp = comp.merge(models[name].predict(pf),
                              on=["code", "season_idx", "gw"])
        comp[["p_cs", "e_gc"]] = 0.25, 1.4      # team model simplification v1
        comp["e_cards"] = pf.apply(card_penalty, axis=1).values
        import json
        from gaffer.data.bootstrap import scoring_table
        scoring = scoring_table(
            json.load(open("tests/fixtures/bootstrap_sample.json")))
        ep = ep_matrix(assemble_ep(comp, scoring))

        players = gw_rows[["code", "position", "team_code", "name",
                           "value"]].rename(columns={"value": "now_cost"})
        players["element"] = players["code"]
        ep_by = {(r.code, r.gw): r.ep for r in ep.itertuples()}

        if team_state is None:
            picks = pd.DataFrame({"code": [], "sell": []})
            pool = build_pool(players, ep_by, picks, [gw])
            init = solve_plan(pool, SolveInput(owned_codes=[], bank=1000,
                                               free_transfers=15, gws=[gw]),
                              decay=cfg.decay, bench_weight=cfg.bench_weight,
                              vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                              itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
            g = init.gw_plans[0]
            costs = dict(zip(players["code"], players["now_cost"]))
            team_state = {"squad": g.squad, "ft": 1,
                          "bank": 1000 - sum(costs.get(c, 0) for c in g.squad)}
            xi, bench, cap, vc, hits = g.xi, g.bench, g.captain, g.vice, 0
        else:
            picks = pd.DataFrame({
                "code": team_state["squad"],
                "sell": [dict(zip(players["code"], players["now_cost"]))
                         .get(c, 40) for c in team_state["squad"]]})
            pool = build_pool(players, ep_by, picks, [gw])
            plan = solve_plan(pool, SolveInput(
                owned_codes=team_state["squad"], bank=team_state["bank"],
                free_transfers=team_state["ft"], gws=[gw]),
                decay=cfg.decay, bench_weight=cfg.bench_weight,
                vice_weight=cfg.vice_weight, ft_value=cfg.ft_value,
                itb_value=cfg.itb_value, hit_cost=cfg.hit_cost)
            g = plan.gw_plans[0]
            costs = dict(zip(players["code"], players["now_cost"]))
            spent = sum(costs.get(c, 0) for c in g.buys)
            recouped = sum(dict(zip(picks["code"], picks["sell"]))
                           .get(c, 0) for c in g.sells)
            team_state = {"squad": g.squad,
                          "ft": min(5, max(0, team_state["ft"] - len(g.buys)
                                           + g.hits) + 1),
                          "bank": team_state["bank"] + recouped - spent}
            xi, bench, cap, vc, hits = g.xi, g.bench, g.captain, g.vice, g.hits

        actuals = gw_rows[["code", "total_points", "minutes", "position"]]
        pts = score_gw(actuals, xi, bench, cap, vc, hits)
        total_pts += pts
        log.append({"gw": gw, "pts": pts, "total": total_pts,
                    "captain": cap, "hits": hits})
    result = {"season": season, "from_gw": start_gw, "total": total_pts,
              "per_gw": round(total_pts / max(1, len(log)), 1), "log": log}
    store.save(pd.DataFrame(log), "live/backtest_log.parquet")
    return result
```

Note: the backtest optimizes single-GW (`gws=[gw]`) for speed and simplicity in v1 — the live tool plans 6 ahead. This makes backtest numbers *conservative*. Multi-week backtest is a listed future improvement.

- [ ] **Step 4: Run.** `uv run pytest tests/test_backtest.py -v` — Expected: PASS

- [ ] **Step 5: Manual milestone run:**

```bash
uv run gaffer backtest --season 2025-26 --start-gw 5
```
Expected: completes in tens of minutes (retrains every 4 GWs); prints total and per-GW points for GW5–38. **Compare against 2025/26 reference points** (look up the season's average score and top-10k cutoff on the FPL site/community wikis and record them in the report). **PAUSE — show the user before Phase F sign-off.** Success criterion from the spec: clearly above the season average for the covered GWs.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: 2025/26 backtest harness with autosubs and captaincy fallback"`

### Task 24: Live tracking / model health

**Files:**
- Create: `src/gaffer/tracking.py`
- Test: `tests/test_tracking.py`

- [ ] **Step 1: Write failing test.** `tests/test_tracking.py`:

```python
import pandas as pd
from gaffer.tracking import compute_health

def test_compute_health_joins_predictions_with_actuals():
    preds = pd.DataFrame({"code": [1, 2, 3], "gw": [2, 2, 2],
                          "ep": [6.0, 4.0, 2.0]})
    actuals = pd.DataFrame({"code": [1, 2, 3], "gw": [2, 2, 2],
                            "total_points": [8, 3, 2], "minutes": [90, 90, 60]})
    h = compute_health(preds, actuals, captain_code=1, advice_pts=50,
                       actual_pts=45)
    assert h["captain_actual"] == 8
    assert h["mae_starters"] == round((2 + 1 + 0) / 3, 2)
    assert h["advice_pts"] == 50 and h["actual_pts"] == 45
```

- [ ] **Step 2: Run.** `uv run pytest tests/test_tracking.py -v` — Expected: FAIL

- [ ] **Step 3: Implement `src/gaffer/tracking.py`**

```python
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from gaffer.data import store

def compute_health(preds: pd.DataFrame, actuals: pd.DataFrame,
                   captain_code: int, advice_pts: float | None = None,
                   actual_pts: float | None = None) -> dict:
    j = preds.merge(actuals, on=["code", "gw"], how="inner")
    starters = j[j["minutes"] >= 60]
    return {
        "gw": int(j["gw"].iloc[0]) if len(j) else None,
        "mae_starters": round(float(
            (starters["ep"] - starters["total_points"]).abs().mean()), 2),
        "captain_actual": int(j.loc[j["code"] == captain_code,
                                    "total_points"].iloc[0])
                          if (j["code"] == captain_code).any() else None,
        "advice_pts": advice_pts, "actual_pts": actual_pts,
    }

def update_health(finished_gw: int) -> dict | None:
    """After a GW is finalized: join the stored predictions log with actuals
    from data/live/player_gw.parquet; persist to reports/health.json."""
    pred_rel = f"live/predictions/gw{finished_gw}.parquet"
    if not store.exists(pred_rel) or not store.exists("live/player_gw.parquet"):
        return None
    preds = store.load(pred_rel)
    live = store.load("live/player_gw.parquet")
    actuals = live[live["gw"] == finished_gw][
        ["code", "gw", "total_points", "minutes"]]
    advice_file = Path(f"reports/gw{finished_gw}-advice.json")
    captain = 0
    if advice_file.exists():
        captain = json.loads(advice_file.read_text())["captain"]["code"]
    health = compute_health(preds, actuals, captain_code=captain)
    Path("reports").mkdir(exist_ok=True)
    Path("reports/health.json").write_text(json.dumps(health, indent=1))
    return health

def latest_health() -> dict | None:
    p = Path("reports/health.json")
    return json.loads(p.read_text()) if p.exists() else None
```

- [ ] **Step 4: Run.** `uv run pytest tests/test_tracking.py -v` — Expected: PASS

- [ ] **Step 5: Wire into advise flow** — in `src/gaffer/advise.py`, at the top of `run_advise` after `gw = next_gw(raw)`, add:

```python
    from gaffer.tracking import update_health
    if gw > 1:
        update_health(gw - 1)
```

Run full suite: `uv run pytest -q` — Expected: all tests pass.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "feat: model-health tracking wired into weekly advise"`

### Task 25: Automation (launchd) + README

**Files:**
- Create: `scripts/com.gaffer.advise.plist`, `scripts/com.gaffer.prices.plist`, `scripts/install_automation.sh`, `README.md`

- [ ] **Step 1: Create `scripts/com.gaffer.advise.plist`** (Thursday 18:00 local full run):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.advise</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ && uv run gaffer train && uv run gaffer advise >> logs/advise.log 2>&1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>4</integer>
        <key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
</dict></plist>
```

- [ ] **Step 2: Create `scripts/com.gaffer.prices.plist`** (nightly 23:15 local price check):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.prices</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ && uv run gaffer prices >> logs/prices.log 2>&1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>15</integer></dict>
</dict></plist>
```

- [ ] **Step 3: Create `scripts/install_automation.sh`**

```bash
#!/bin/zsh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$PROJECT_DIR/logs" ~/Library/LaunchAgents
for name in advise prices; do
  sed "s|__PROJECT_DIR__|$PROJECT_DIR|" \
      "$PROJECT_DIR/scripts/com.gaffer.$name.plist" \
      > ~/Library/LaunchAgents/com.gaffer.$name.plist
  launchctl unload ~/Library/LaunchAgents/com.gaffer.$name.plist 2>/dev/null || true
  launchctl load ~/Library/LaunchAgents/com.gaffer.$name.plist
done
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check."
```

- [ ] **Step 4: Verify plists parse and install:**

```bash
chmod +x scripts/install_automation.sh
plutil -lint scripts/com.gaffer.advise.plist scripts/com.gaffer.prices.plist
./scripts/install_automation.sh
launchctl list | grep com.gaffer
```
Expected: `OK` for both plists; both jobs listed. (Add `logs/` to `.gitignore`.)

- [ ] **Step 5: Write `README.md`** — short usage doc: what gaffer is, the weekly ritual (`gaffer advise` before Friday deadlines or let the Thursday job run), all six commands with one-line descriptions, config.toml fields, how to retrain, where reports land, the note that price changes hit at 00:00 UK, and the pointer to the spec + plan under `docs/superpowers/`.

- [ ] **Step 6: Final full-suite run and commit:**

```bash
uv run pytest -q
git add -A && git commit -m "feat: launchd automation and README"
```
Expected: all tests pass.

---

## Post-plan improvements (explicitly deferred, do not build now)

- Multi-week (horizon) optimization inside the backtest; chips in the backtest.
- Quantile/distributional EP outputs; bookmaker odds; per-slot bench MILP weights.
- Free-transfer count read from an authenticated endpoint (stays advisor-only regardless).

## Self-review checklist (run after all tasks; fix inline)

1. Spec coverage — every spec §-requirement maps to a task (see traceability below).
2. Placeholder scan — no TBDs; every code step shows the code.
3. Type consistency — canonical `player_gw` columns defined once in `live.py`; `SolveInput`/`Plan`/`GwPlan` shapes used identically in Tasks 16–20; scoring-table shape `{identifier: {position: pts}}` in Tasks 3, 14, 23.

**Traceability:** Spec §4 data → Tasks 2–8; §5 prediction → Tasks 9–15; §6 decisions → Tasks 16–19; §7 interface/automation → Tasks 20–22, 25; §8 testing → per-task TDD + Tasks 23–24 gates; §9 error handling → Tasks 2 (retries/backoff), 20 (models-missing guard), 24 (finalization-gated health); §10 rules → Tasks 3 (live scoring table), 7 (FT/sell rules), 16 (squad rules), 17 (chip halves in Task 20's chip filter).









