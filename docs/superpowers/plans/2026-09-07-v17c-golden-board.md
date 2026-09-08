# v17c — the golden board harness: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Spec: `docs/superpowers/specs/2026-09-07-v17c-golden-board-design.md`. Read CLAUDE.md first. Implementers never open `config.toml`, never run `--record`, and never touch `src/`.

**Goal:** a test that runs `run_advise` over recorded FPL responses in a frozen working directory and compares the advice and solve state byte-for-byte with committed expected files, skipping when the models or the archive on disk are not the ones it was recorded under.

**Architecture:** `tests/golden_client.py` holds everything: `RecordedClient` (the second adapter behind `run_advise(cfg, client)`, overriding `FPLClient._get` only), `RecordingClient` (same override, live then bank), `golden_config()` and its TOML writer, the scratch-tree builder, the input-hash skip rule, the volatile-key stripper, the lever counts, `run_golden`, and a `__main__` with `--record` and `--write`. `tests/test_golden_board.py` holds the unit tests over a synthetic two-entry bundle and the two `golden`-marked tests that run the real pipeline. The fixture lives under `tests/data/golden_board/`.

**Tech stack:** Python 3, pytest, gzip + json for the bundle, hashlib for the skip rule. Nothing under `src/` changes.

---

## File map

| Path | Owner | Responsibility |
|---|---|---|
| `tests/golden_client.py` | implementer (Tasks 1–4) | the whole harness |
| `tests/test_golden_board.py` | implementer (Tasks 1–4) | unit tests + the two golden tests |
| `tests/data/golden_board/responses.json.gz` | orchestrator (Task 5) | the recorded bodies, path → body |
| `tests/data/golden_board/header.json` | orchestrator (Task 5) | config echo, input hashes, levers |
| `tests/data/golden_board/config.toml` | orchestrator (Task 5) | `write_golden_toml(golden_config())`, no `[odds]` |
| `tests/data/golden_board/data/core_insights/**` | orchestrator (Task 5) | frozen Core Insights parquet |
| `tests/data/golden_board/expected/advice.json`, `expected/solve_state.json` | orchestrator (Task 5) | the goldens, volatile keys stripped |
| `pyproject.toml` | orchestrator (Task 5) | the `golden` marker |
| `.gitignore` | orchestrator (Task 5) | re-include the fixture's `config.toml` and `data/core_insights/` |

Shared names, used identically in every task: `GOLDEN_DIR`, `BUNDLE_NAME = "responses.json.gz"`, `HEADER_NAME = "header.json"`, `EXPECTED_DIR = "expected"`, `HASHED_ROOTS = ("models", "data/history")`, `ABSENT_INPUTS = ("data/chip_scenarios.toml", "data/set_pieces.toml")`, `LEVER_FLOORS`.

---

### Task 1: the bundle and the two clients

**Files:**
- Create: `tests/golden_client.py`
- Create: `tests/test_golden_board.py`

- [ ] **Step 1: Write the failing tests**

```python
"""v17c — the golden board harness (specs/2026-09-07-v17c-golden-board-design.md).

Unit tests over a synthetic bundle, and the two ``golden``-marked tests that
run the real pipeline over the recorded one."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import golden_client as gc


def _bundle(tmp_path: Path) -> Path:
    gc.save_bundle(tmp_path, {"bootstrap-static/": {"events": [{"id": 4}]},
                              "fixtures/": [{"id": 1}]})
    return tmp_path


def test_the_recorded_client_serves_every_recorded_path_and_refuses_the_rest(tmp_path):
    client = gc.RecordedClient(_bundle(tmp_path))
    assert client.get_bootstrap() == {"events": [{"id": 4}]}
    assert client.get_fixtures() == [{"id": 1}]
    with pytest.raises(KeyError, match="element-summary/7/"):
        client.get_element_summary(7)


def test_the_recorded_client_hands_out_copies_not_the_bundle(tmp_path):
    client = gc.RecordedClient(_bundle(tmp_path))
    client.get_bootstrap()["events"].append({"id": 99})
    assert client.get_bootstrap() == {"events": [{"id": 4}]}


def test_the_recorded_client_never_writes_a_raw_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gc.RecordedClient(_bundle(tmp_path / "golden")).get_bootstrap()
    assert not (tmp_path / "data").exists()


def test_the_recording_client_banks_every_body_under_its_path(tmp_path):
    seen: list[str] = []

    class Fake(gc.RecordingClient):
        def _live(self, path):
            seen.append(path)
            return {"path": path}

    rec = Fake(tmp_path / "out")
    rec.get_bootstrap()
    rec.get_entry_picks(2210493, 3)
    out = rec.save()
    assert out == tmp_path / "out" / gc.BUNDLE_NAME
    assert gc.load_bundle(tmp_path / "out") == {
        "bootstrap-static/": {"path": "bootstrap-static/"},
        "entry/2210493/event/3/picks/": {"path": "entry/2210493/event/3/picks/"}}
    assert seen == ["bootstrap-static/", "entry/2210493/event/3/picks/"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_golden_board.py`
Expected: `ImportError` / `ModuleNotFoundError: tests.golden_client`.

- [ ] **Step 3: Write the module's first half**

```python
"""v17c — the golden board harness.

The second adapter behind ``run_advise(cfg, client)``: a client that replays
recorded FPL responses (spec §2.1), the config the golden was recorded under
(§2.3), the scratch working directory it runs in (§2.4), the input-hash
skip rule (§2.6), and the ``--record`` / ``--write`` entry points (§2.10).
Lives in ``tests/`` because nothing in the package needs it.
"""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

from gaffer.api.client import FPLClient

GOLDEN_DIR = Path(__file__).resolve().parent / "data" / "golden_board"
BUNDLE_NAME = "responses.json.gz"
HEADER_NAME = "header.json"
EXPECTED_DIR = "expected"


def save_bundle(directory: Path, bodies: dict[str, object]) -> Path:
    """One gzip'd JSON object, API path → body, keys sorted so a re-record
    with the same answers is the same bytes (spec §2.2)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / BUNDLE_NAME
    raw = json.dumps(bodies, sort_keys=True, separators=(",", ":")).encode()
    # GzipFile, not gzip.open: only the class takes mtime, and the empty
    # filename keeps the file's own path out of the gzip header, so the same
    # answers are the same bytes wherever they were written.
    with open(path, "wb") as raw_fh, gzip.GzipFile(
            filename="", fileobj=raw_fh, mode="wb", compresslevel=9,
            mtime=0) as fh:
        fh.write(raw)
    return path


def load_bundle(directory: Path) -> dict[str, object]:
    with gzip.open(Path(directory) / BUNDLE_NAME, "rb") as fh:
        return json.loads(fh.read())


class RecordedClient(FPLClient):
    """Replays a bundle. Overrides ``_get`` only, so every public method the
    parent has or gains is covered by the one lookup; never opens a socket;
    never writes a ``data/raw`` snapshot (the parent's ``__init__`` is not
    called, so there is no ``raw_dir`` and no ``httpx.Client``)."""

    def __init__(self, directory: Path = GOLDEN_DIR):
        self.directory = Path(directory)
        self._bodies = load_bundle(self.directory)

    def _get(self, path: str, snapshot: str | None = None):
        if path not in self._bodies:
            raise KeyError(f"{path} was not recorded in {self.directory}")
        # A copy per call: the pipeline mutates frames it builds from these
        # dicts, and one caller's edit must not leak into the next replay.
        return copy.deepcopy(self._bodies[path])


class RecordingClient(FPLClient):
    """The same override the other way round: fetch live, bank the body.
    ``_live`` is the one seam a test replaces."""

    def __init__(self, directory: Path, **client_kw):
        super().__init__(**client_kw)
        self.directory = Path(directory)
        self._bodies: dict[str, object] = {}

    def _live(self, path: str):
        return super()._get(path, snapshot=None)

    def _get(self, path: str, snapshot: str | None = None):
        body = self._live(path)
        self._bodies[path] = copy.deepcopy(body)
        return body

    def save(self) -> Path:
        return save_bundle(self.directory, self._bodies)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q tests/test_golden_board.py`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/golden_client.py tests/test_golden_board.py
git commit -m "test(v17c): RecordedClient and RecordingClient — the second adapter behind run_advise, one _get override over a gzip bundle

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B6YY6dedTdAY7f6FrFtif9"
```

---

### Task 2: `golden_config` and the TOML writer

**Files:**
- Modify: `tests/golden_client.py`
- Modify: `tests/test_golden_board.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_golden_board.py`:

```python
from dataclasses import asdict

from gaffer.config import Config, load_config


def test_golden_config_round_trips_through_the_toml_writer(tmp_path):
    cfg = gc.golden_config()
    gc.write_golden_toml(cfg, tmp_path / "config.toml")
    assert asdict(load_config(tmp_path / "config.toml")) == asdict(cfg)


def test_golden_config_is_a_literal_with_the_levers_the_spec_names():
    cfg = gc.golden_config()
    assert isinstance(cfg, Config)
    assert cfg.horizon == 6
    assert cfg.scenarios_n == 40 and cfg.scenarios_seed == 20260825
    assert cfg.news_enabled is False
    assert cfg.odds_api_key == ""
    assert cfg.train_seasons == ["2022-23", "2023-24", "2024-25", "2025-26"]
    assert cfg.current_season == "2026-27"


def test_the_written_toml_has_no_odds_section_and_no_key(tmp_path):
    gc.write_golden_toml(gc.golden_config(), tmp_path / "config.toml")
    text = (tmp_path / "config.toml").read_text()
    assert "[odds]" not in text
    assert "api_key" not in text
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_golden_board.py -k "golden_config or written_toml"`
Expected: 3 failed, `AttributeError: module 'tests.golden_client' has no attribute 'golden_config'`.

- [ ] **Step 3: Add the config and the writer**

Append to `tests/golden_client.py` (add `from dataclasses import asdict` and `from gaffer.config import NO_CAP, Config` to the imports):

```python
def golden_config() -> Config:
    """The config the golden was recorded under (spec §4). Literals, never
    ``config.toml``: the header echoes ``asdict`` of this and the test
    compares them, so an edit here without a re-record fails loudly.
    Every knob that was a shipped value on 2026-09-08 is written out, and
    the three lever knobs are the ones §4 starts from."""
    return Config(
        entry_id=2210493, league_id=1794743,
        horizon=6, decay=0.85, vice_weight=0.1, bench_weight=0.10,
        ft_value=1.5, itb_value=0.08, hit_cost=4, alt_plan_max_gap=2.0,
        ft_use_penalty=0.2, bench_curve=[0.21, 0.06, 0.002],
        max_hits=2, max_transfers=NO_CAP, hit_bar=0.60,
        train_seasons=["2022-23", "2023-24", "2024-25", "2025-26"],
        current_season="2026-27",
        # No odds: the key is absent, and without a key player_props is
        # unreachable, so it keeps the loader's default (True).
        odds_api_key="",
        scenarios_n=40, scenarios_seed=20260825, decision_priors=True,
        news_enabled=False,
        stance="auto",
    )


def _toml(value) -> str:
    """A TOML literal for the value kinds ``Config`` carries. JSON's string
    escaping is a subset of TOML's basic strings, so ``json.dumps`` is the
    string writer."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"no TOML form for {type(value).__name__}")


# Section → (toml key, Config field). The inverse of ``load_config``'s
# reading, table by table; ``[odds]`` is deliberately not here (spec §2.3).
_TOML_LAYOUT: dict[str, list[tuple[str, str]]] = {
    "fpl": [("entry_id", "entry_id"), ("league_id", "league_id")],
    "optimizer": [(k, k) for k in (
        "horizon", "decay", "vice_weight", "bench_weight", "ft_value",
        "itb_value", "hit_cost", "alt_plan_max_gap", "max_hits",
        "max_transfers", "hit_bar", "ft_use_penalty", "bench_curve", "top_n")],
    "data": [("train_seasons", "train_seasons"),
             ("current_season", "current_season")],
    "understat": [("enabled", "understat_enabled")],
    "scenarios": [("n", "scenarios_n"), ("seed", "scenarios_seed"),
                  ("transfer_threshold", "transfer_threshold"),
                  ("irreversible_threshold", "irreversible_threshold"),
                  ("decision_priors", "decision_priors"),
                  ("draw_availability", "draw_availability")],
    "league": [(k, k) for k in (
        "z_scale", "lambda_cap", "sigma_floor", "sigma_cap",
        "sigma_min_weeks", "z_deadband", "tier_eo", "tier_sample",
        "field_scrape", "field_sample", "sim_n", "rival_drift", "stance")],
    "news": [(k[len("news_"):], k) for k in (
        "news_enabled", "news_injuries", "news_lineups", "news_cache_hours",
        "news_min_coverage", "news_llm_classifier", "news_llm_shadow",
        "news_llm_command", "news_llm_timeout_s", "news_lineup_absence",
        "news_lineup_absence_damp", "news_lineup_start_floor",
        "news_overrides")],
    "digest": [("notify", "digest_notify")],
    "backup": [("dir", "backup_dir"), ("rsync_target", "backup_rsync_target"),
               ("keep", "backup_keep")],
    "web": [("token", "web_token")],
}


def write_golden_toml(cfg: Config, path: Path) -> None:
    """``cfg`` as a ``config.toml`` ``load_config`` reads back field for
    field (pinned by the round-trip test). Every field is written, so the
    file does not depend on the dataclass defaults staying put."""
    values = asdict(cfg)
    lines = ["# v17c golden board: written by tests/golden_client.py from",
             "# golden_config(). No [odds] table, by design.", ""]
    for section, keys in _TOML_LAYOUT.items():
        lines.append(f"[{section}]")
        for key, field_name in keys:
            value = values[field_name]
            if value is None:
                continue
            lines.append(f"{key} = {_toml(value)}")
        lines.append("")
    Path(path).write_text("\n".join(lines))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q tests/test_golden_board.py`
Expected: 7 passed. If the round trip fails, the diff names the field; fix the layout table, never the assertion.

- [ ] **Step 5: Commit**

```bash
git add tests/golden_client.py tests/test_golden_board.py
git commit -m "test(v17c): golden_config and write_golden_toml — the recorded config as literals, round-tripped through load_config, no [odds] table

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B6YY6dedTdAY7f6FrFtif9"
```

---

### Task 3: the scratch tree, the skip rule, the stripper, the levers

**Files:**
- Modify: `tests/golden_client.py`
- Modify: `tests/test_golden_board.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_golden_board.py`:

```python
import hashlib


def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "models").mkdir(parents=True)
    (repo / "models" / "team.joblib").write_bytes(b"model")
    (repo / "data" / "history").mkdir(parents=True)
    (repo / "data" / "history" / "player_gw.parquet").write_bytes(b"rows")
    (repo / "data" / "core_insights" / "2026-27").mkdir(parents=True)
    (repo / "data" / "core_insights" / "2026-27" / "stats.parquet").write_bytes(b"ci")
    (repo / "data" / "manager_tenures.toml").write_text("[x]\n")
    return repo


def test_input_hashes_cover_models_and_history_and_name_absent_optionals(tmp_path):
    repo = _fake_repo(tmp_path)
    hashes = gc.input_hashes(repo)
    assert hashes["models/team.joblib"] == hashlib.sha256(b"model").hexdigest()
    assert hashes["data/history/player_gw.parquet"] == hashlib.sha256(b"rows").hexdigest()
    assert hashes["data/chip_scenarios.toml"] == "absent"
    assert hashes["data/set_pieces.toml"] == "absent"
    assert not any(k.startswith("data/core_insights") for k in hashes)


def test_matching_hashes_do_not_skip(tmp_path):
    repo = _fake_repo(tmp_path)
    header = {"inputs": gc.input_hashes(repo)}
    assert gc.stale_inputs(header, repo) == []


def test_a_changed_model_hash_skips_with_the_file_named(tmp_path):
    repo = _fake_repo(tmp_path)
    header = {"inputs": gc.input_hashes(repo)}
    (repo / "models" / "team.joblib").write_bytes(b"retrained")
    assert gc.stale_inputs(header, repo) == ["models/team.joblib"]
    (repo / "models" / "team.joblib").unlink()
    assert gc.stale_inputs(header, repo) == ["models/team.joblib"]


def test_an_optional_input_that_appears_is_a_drift(tmp_path):
    repo = _fake_repo(tmp_path)
    header = {"inputs": gc.input_hashes(repo)}
    (repo / "data" / "set_pieces.toml").write_text("[pens]\n")
    assert gc.stale_inputs(header, repo) == ["data/set_pieces.toml"]


def test_build_scratch_tree_links_the_heavy_inputs_and_copies_the_frozen_ones(tmp_path):
    repo = _fake_repo(tmp_path)
    golden = tmp_path / "golden"
    (golden / "data" / "core_insights" / "2026-27").mkdir(parents=True)
    (golden / "data" / "core_insights" / "2026-27" / "stats.parquet").write_bytes(b"frozen")
    gc.write_golden_toml(gc.golden_config(), golden / "config.toml")
    root = tmp_path / "scratch"
    gc.build_scratch_tree(root, repo, golden)
    assert (root / "models").is_symlink() and (root / "models" / "team.joblib").read_bytes() == b"model"
    assert (root / "data" / "history").is_symlink()
    assert not (root / "data" / "core_insights").is_symlink()
    assert (root / "data" / "core_insights" / "2026-27" / "stats.parquet").read_bytes() == b"frozen"
    assert (root / "data" / "manager_tenures.toml").read_text() == "[x]\n"
    assert (root / "config.toml").read_text() == (golden / "config.toml").read_text()
    assert (root / "reports").is_dir()
    assert not (root / "data" / "live").exists()


def test_strip_volatile_removes_generated_at_and_rewrites_paths():
    obj = {"generated_at": "2026-09-08T09:17:00", "gw": 4,
           "nested": [{"generated_at": 1, "path": "/tmp/x/reports/a.json"}],
           "other": "/tmp/y/z"}
    assert gc.strip_volatile(obj, "/tmp/x") == {
        "gw": 4, "nested": [{"path": "<cwd>/reports/a.json"}], "other": "/tmp/y/z"}


def test_lever_counts_read_the_served_advice():
    advice = {
        "restraint": {"steps": [{"taken": True}, {"taken": False}, {"taken": False}]},
        "objective": {"hits": 1}, "chip_table": [{}, {}],
        "strategy": {"lam": 0.0958}, "bench": [1, 2, 3, 4], "vice": {"code": 9},
        "plan_by_gw": [{}] * 6}
    counts = gc.lever_counts(advice)
    assert counts == {"restraint_steps_taken": 1, "restraint_steps_refused": 2,
                      "objective_hits": 1, "chip_rows": 2, "league_lam": 0.0958,
                      "bench": 4, "vice": True, "plan_weeks": 6}
    assert gc.levers_below_floor(counts) == []
    assert gc.levers_below_floor({**counts, "league_lam": 0.0, "plan_weeks": 3}) == [
        "league_lam", "plan_weeks"]


def test_lever_counts_survive_a_missing_block():
    counts = gc.lever_counts({"restraint": None, "objective": None, "strategy": None,
                              "chip_table": [], "bench": [], "vice": None,
                              "plan_by_gw": []})
    assert counts["restraint_steps_taken"] == 0 and counts["league_lam"] == 0.0
    assert set(gc.levers_below_floor(counts)) == set(gc.LEVER_FLOORS)


def test_the_fixture_is_under_the_size_budget():
    if not (gc.GOLDEN_DIR / gc.HEADER_NAME).exists():
        pytest.skip("golden board not recorded yet")
    assert gc.fixture_kb(gc.GOLDEN_DIR) < 5120
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_golden_board.py -k "input_hashes or skip or drift or scratch or strip or lever or budget"`
Expected: failures with `AttributeError` on `input_hashes`.

- [ ] **Step 3: Implement**

Append to `tests/golden_client.py` (add `import hashlib`, `import os`, `import shutil` to the imports):

```python
HASHED_ROOTS = ("models", "data/history")
"""The two inputs that stay on the machine and are pinned by digest (spec
§2.5, §2.6): the models (14 MB) and the archive (3.3 MB)."""
ABSENT_INPUTS = ("data/chip_scenarios.toml", "data/set_pieces.toml")
"""Optional inputs the pipeline reads when present. Recorded as ``"absent"``
so a later presence is a drift, not a surprise (spec §5)."""
LEVER_FLOORS: dict[str, object] = {
    "restraint_steps_taken": 1, "restraint_steps_refused": 1,
    "objective_hits": 1, "chip_rows": 1, "league_lam": "nonzero",
    "bench": 4, "vice": True, "plan_weeks": 6}
"""What the golden must carry (spec §1 item 2; CONVENTIONS §10)."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_hashes(repo: Path) -> dict[str, str]:
    """``{relative path: sha256}`` for every file under ``HASHED_ROOTS`` and
    ``"absent"`` or a digest for each ``ABSENT_INPUTS`` entry. Sorted keys,
    so the header is stable."""
    repo = Path(repo)
    out: dict[str, str] = {}
    for root in HASHED_ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for file in sorted(p for p in base.rglob("*") if p.is_file()):
            out[file.relative_to(repo).as_posix()] = _sha256(file)
    for rel in ABSENT_INPUTS:
        file = repo / rel
        out[rel] = _sha256(file) if file.exists() else "absent"
    return dict(sorted(out.items()))


def stale_inputs(header: dict, repo: Path) -> list[str]:
    """The recorded inputs whose file on disk is missing or different, in
    header order. Empty means the golden may run. A file on disk that the
    header never recorded is ignored: the golden pins what it used."""
    repo = Path(repo)
    stale: list[str] = []
    for rel, digest in header.get("inputs", {}).items():
        file = repo / rel
        now = _sha256(file) if file.exists() else "absent"
        if now != digest:
            stale.append(rel)
    return stale


def build_scratch_tree(root: Path, repo: Path, golden: Path = GOLDEN_DIR) -> None:
    """The working directory a golden run executes in (spec §2.4). Symlinks
    for the two hashed roots, copies for the frozen Core Insights, the
    tracked tenures file and the golden ``config.toml``; an empty
    ``reports/``; nothing else, so ``data/live`` and the rest are created by
    the run and the repo's own trees are never written."""
    root, repo, golden = Path(root), Path(repo), Path(golden)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(exist_ok=True)
    os.symlink(repo / "models", root / "models")
    os.symlink(repo / "data" / "history", root / "data" / "history")
    shutil.copytree(golden / "data" / "core_insights",
                    root / "data" / "core_insights")
    shutil.copy(repo / "data" / "manager_tenures.toml",
                root / "data" / "manager_tenures.toml")
    shutil.copy(golden / "config.toml", root / "config.toml")


def strip_volatile(obj, cwd: str):
    """``generated_at`` removed at every depth; every string that starts with
    the run's working directory rewritten to ``<cwd>`` (spec §1 item 1)."""
    if isinstance(obj, dict):
        return {k: strip_volatile(v, cwd) for k, v in obj.items()
                if k != "generated_at"}
    if isinstance(obj, list):
        return [strip_volatile(v, cwd) for v in obj]
    if isinstance(obj, str) and obj.startswith(cwd):
        return "<cwd>" + obj[len(cwd):]
    return obj


def lever_counts(advice: dict) -> dict[str, object]:
    """The counts the header's ``levers`` block carries, off the served
    advice (spec §1 item 2)."""
    steps = ((advice.get("restraint") or {}).get("steps")) or []
    strategy = advice.get("strategy") or {}
    return {
        "restraint_steps_taken": sum(1 for s in steps if s.get("taken")),
        "restraint_steps_refused": sum(1 for s in steps if not s.get("taken")),
        "objective_hits": int((advice.get("objective") or {}).get("hits") or 0),
        "chip_rows": len(advice.get("chip_table") or []),
        "league_lam": float(strategy.get("lam") or 0.0),
        "bench": len(advice.get("bench") or []),
        "vice": bool(advice.get("vice")),
        "plan_weeks": len(advice.get("plan_by_gw") or []),
    }


def levers_below_floor(counts: dict[str, object]) -> list[str]:
    """The lever names that miss ``LEVER_FLOORS``, in floor order."""
    missing: list[str] = []
    for name, floor in LEVER_FLOORS.items():
        value = counts.get(name)
        if floor == "nonzero":
            ok = bool(value)
        elif isinstance(floor, bool):
            ok = bool(value) is floor
        else:
            ok = value is not None and value >= floor
        if not ok:
            missing.append(name)
    return missing


def fixture_kb(directory: Path = GOLDEN_DIR) -> float:
    return sum(p.stat().st_size for p in Path(directory).rglob("*")
               if p.is_file()) / 1024
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q tests/test_golden_board.py`
Expected: 17 passed, 1 skipped (the size test, until the fixture exists).

- [ ] **Step 5: Commit**

```bash
git add tests/golden_client.py tests/test_golden_board.py
git commit -m "test(v17c): the scratch tree, the input-hash skip rule, strip_volatile and the lever counts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B6YY6dedTdAY7f6FrFtif9"
```

---

### Task 4: `run_golden`, the golden tests, and the `--record` / `--write` entry points

**Files:**
- Modify: `tests/golden_client.py`
- Modify: `tests/test_golden_board.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_golden_board.py`:

```python
REPO = Path(__file__).resolve().parents[1]


def _header() -> dict | None:
    path = gc.GOLDEN_DIR / gc.HEADER_NAME
    return json.loads(path.read_text()) if path.exists() else None


@pytest.fixture(scope="module")
def golden_run(tmp_path_factory):
    """One pipeline run per session, shared by the two golden tests. Skips,
    with the file named, when a hashed input moved (spec §2.6), and when the
    board has not been recorded."""
    header = _header()
    if header is None:
        pytest.skip("golden board not recorded (tests/data/golden_board/header.json)")
    stale = gc.stale_inputs(header, REPO)
    if stale:
        pytest.skip(f"golden board recorded under a different {stale[0]} "
                    f"({len(stale)} input(s) differ); re-record with "
                    "python -m tests.golden_client --write")
    root = tmp_path_factory.mktemp("golden")
    gc.build_scratch_tree(root, REPO)
    advice, state = gc.run_golden(root)
    return {"header": header, "cwd": str(root),
            "advice": gc.strip_volatile(advice, str(root)),
            "state": gc.strip_volatile(state, str(root))}


@pytest.mark.golden
def test_the_golden_board_reproduces_the_expected_advice_and_state(golden_run):
    expected = gc.GOLDEN_DIR / gc.EXPECTED_DIR
    assert golden_run["advice"] == json.loads((expected / "advice.json").read_text())
    assert golden_run["state"] == json.loads((expected / "solve_state.json").read_text())


@pytest.mark.golden
def test_the_golden_board_still_exercises_every_lever(golden_run):
    counts = gc.lever_counts(golden_run["advice"])
    assert gc.levers_below_floor(counts) == []
    assert counts == golden_run["header"]["levers"]


def test_the_header_config_is_golden_config():
    header = _header()
    if header is None:
        pytest.skip("golden board not recorded yet")
    assert header["config"] == asdict(gc.golden_config())
    assert header["config"]["odds_api_key"] == ""


def test_the_recorded_config_file_has_no_odds_section():
    path = gc.GOLDEN_DIR / "config.toml"
    if not path.exists():
        pytest.skip("golden board not recorded yet")
    assert "[odds]" not in path.read_text()
    assert "api_key" not in path.read_text()


def test_run_golden_runs_in_the_scratch_tree_and_reads_the_two_files_back(tmp_path, monkeypatch):
    """``run_golden`` over a stub ``run_advise``: it chdirs into the root,
    clears the serving-config cache on both sides, silences the refresh
    sleep, and hands back the two JSON files the run wrote."""
    import gaffer.data.live as live_mod
    from gaffer.config import serving_config

    calls: dict[str, object] = {}
    (tmp_path / "reports").mkdir()

    def fake_run_advise(cfg, client=None):
        calls["cwd"] = Path.cwd()
        calls["cfg"] = cfg
        calls["client"] = client
        calls["sleep"] = live_mod.time.sleep
        (tmp_path / "reports" / "gw4-advice.json").write_text(
            json.dumps({"gw": 4, "generated_at": "x"}))
        (tmp_path / "reports" / "solve_state_gw4.json").write_text(
            json.dumps({"gw": 4, "generated_at": "y"}))

        class A:
            gw = 4
        return A()

    monkeypatch.setattr(gc, "run_advise", fake_run_advise)
    serving_config.cache_clear()
    before = Path.cwd()
    advice, state = gc.run_golden(tmp_path, client=object())
    assert Path.cwd() == before
    assert calls["cwd"] == tmp_path.resolve()
    assert asdict(calls["cfg"]) == asdict(gc.golden_config())
    assert calls["sleep"] is not __import__("time").sleep
    assert live_mod.time.sleep is __import__("time").sleep
    assert advice == {"gw": 4, "generated_at": "x"} and state == {"gw": 4, "generated_at": "y"}
    assert serving_config.cache_info().currsize == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest -q tests/test_golden_board.py -k "run_golden"`
Expected: 1 failed, `AttributeError: ... 'run_golden'`.

- [ ] **Step 3: Implement `run_golden` and the entry points**

Append to `tests/golden_client.py` (add `import argparse`, `import subprocess`, `import sys`, `import time`, `from datetime import datetime, timezone`, `from unittest.mock import patch`, and `from gaffer.advise import run_advise`; the last one is a module-level import so a test can monkeypatch `gc.run_advise`):

```python
def run_golden(root: Path, client: FPLClient | None = None) -> tuple[dict, dict]:
    """``run_advise(golden_config(), client)`` inside ``root`` (spec §2.3,
    §2.8): the working directory is the second, implicit seam
    (``serving_config()`` and every relative ``Path("data")``), so the
    process moves into it for the call and back out after. The serving
    cache is cleared on both sides so neither the repo's ``config.toml``
    nor the golden's leaks into the other; ``refresh_live``'s politeness
    sleep is the one thing patched — 654 calls to a server the recorded
    client never contacts."""
    from gaffer.config import serving_config
    import gaffer.data.live as live_mod

    root = Path(root).resolve()
    client = client if client is not None else RecordedClient()
    before = Path.cwd()
    serving_config.cache_clear()
    try:
        os.chdir(root)
        with patch.object(live_mod.time, "sleep", lambda *_: None):
            advice = run_advise(golden_config(), client)
        gw = int(advice.gw)
        advice_json = json.loads((root / "reports" / f"gw{gw}-advice.json").read_text())
        state_json = json.loads((root / "reports" / f"solve_state_gw{gw}.json").read_text())
    finally:
        os.chdir(before)
        serving_config.cache_clear()
    return advice_json, state_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 — a header without a hash is still a header
        return ""


def write_expected(golden: Path = GOLDEN_DIR, *, scratch: Path | None = None,
                   recorded_at: str | None = None) -> dict:
    """The retrain path (spec §2.10): run the golden over the *existing*
    bundle and rewrite ``expected/`` and the header. Returns the header."""
    import tempfile

    repo = _repo_root()
    golden = Path(golden)
    root = Path(scratch) if scratch else Path(tempfile.mkdtemp(prefix="golden-"))
    build_scratch_tree(root, repo, golden)
    started = time.monotonic()
    advice, state = run_golden(root)
    runtime = round(time.monotonic() - started, 1)
    cwd = str(root.resolve())
    advice, state = strip_volatile(advice, cwd), strip_volatile(state, cwd)
    expected = golden / EXPECTED_DIR
    expected.mkdir(exist_ok=True)
    (expected / "advice.json").write_text(json.dumps(advice, indent=1, sort_keys=True) + "\n")
    (expected / "solve_state.json").write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    bundle = golden / BUNDLE_NAME
    old = json.loads((golden / HEADER_NAME).read_text()) if (golden / HEADER_NAME).exists() else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = {
        "recorded_at": recorded_at or old.get("recorded_at") or now,
        "written_at": now,
        "recorded_by": "python -m tests.golden_client --record; --write after a retrain",
        "gw": int(advice["gw"]),
        "commit": _git_head(repo),
        "config": asdict(golden_config()),
        "inputs": input_hashes(repo),
        "responses": {"count": len(load_bundle(golden)), "bytes_gz": bundle.stat().st_size},
        "levers": lever_counts(advice),
        "runtime_s": runtime,
    }
    (golden / HEADER_NAME).write_text(json.dumps(header, indent=1) + "\n")
    return header


def record(golden: Path = GOLDEN_DIR) -> dict:
    """The live path (spec §2.10): freeze Core Insights into the fixture,
    write the golden ``config.toml``, run the pipeline once through
    ``RecordingClient`` to bank every response, then ``write_expected`` over
    the bundle so the expected files come from the replay path, not the
    live one."""
    import tempfile

    repo = _repo_root()
    golden = Path(golden)
    golden.mkdir(parents=True, exist_ok=True)
    frozen = golden / "data" / "core_insights"
    if frozen.exists():
        shutil.rmtree(frozen)
    shutil.copytree(repo / "data" / "core_insights", frozen)
    write_golden_toml(golden_config(), golden / "config.toml")
    root = Path(tempfile.mkdtemp(prefix="golden-record-"))
    build_scratch_tree(root, repo, golden)
    recorder = RecordingClient(golden, raw_dir=root / "data" / "raw")
    run_golden(root, client=recorder)
    recorder.save()
    recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return write_expected(golden, recorded_at=recorded_at)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v17c golden board: --record fetches live and writes the "
                    "bundle, the expected files and the header; --write reruns "
                    "the existing bundle (after a retrain).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if Path.cwd().resolve() != _repo_root():
        print(f"run from the repo root ({_repo_root()})", file=sys.stderr)
        return 2
    header = record() if args.record else write_expected()
    print(json.dumps({k: header[k] for k in ("gw", "levers", "runtime_s", "responses")},
                     indent=1))
    below = levers_below_floor(header["levers"])
    if below:
        print(f"levers below floor: {', '.join(below)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q tests/test_golden_board.py`
Expected: 18 passed, 5 skipped (the four fixture-dependent tests and the size test, all "not recorded yet"). Then `.venv/bin/pytest -q` for the whole suite: no new failures; note the count.

- [ ] **Step 5: Commit**

```bash
git add tests/golden_client.py tests/test_golden_board.py
git commit -m "test(v17c): run_golden, the two golden tests behind the skip rule, and the --record / --write entry points

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01B6YY6dedTdAY7f6FrFtif9"
```

---

### Task 5 (orchestrator only): the marker, the ignore rules, the recording, the gate

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`)
- Modify: `.gitignore`
- Create: everything under `tests/data/golden_board/`

- [ ] **Step 1: Register the marker**

Under `[tool.pytest.ini_options]` add:

```toml
markers = ["golden: runs the recorded pipeline (v17c); deselect with -m 'not golden'"]
```

- [ ] **Step 2: Re-include the fixture in `.gitignore`**

Append:

```
# v17c: the golden board's frozen copies are fixtures, not the machine's own.
!tests/data/golden_board/config.toml
!tests/data/golden_board/data/core_insights/
```

Check: `git check-ignore -v tests/data/golden_board/config.toml tests/data/golden_board/data/core_insights/x` prints nothing (exit 1).

- [ ] **Step 3: Record**

```bash
.venv/bin/python -m tests.golden_client --record
```

Expected: a JSON block with `gw`, `levers`, `runtime_s`, `responses`, exit 0. If a lever is below its floor, adjust `hit_bar` (within 0.5–0.95) or `max_hits` in `golden_config()`, rerun, and record what moved in spec §10. Runtime and bundle size go in spec §10.

- [ ] **Step 4: Gate items 1–5**

```bash
.venv/bin/pytest -q tests/test_golden_board.py     # run 1
.venv/bin/pytest -q tests/test_golden_board.py     # run 2
du -sk tests/data/golden_board
V="$(sed -n '/^\[odds\]/,/^\[/p' config.toml | grep '^api_key' | cut -d'"' -f2)"; [ "${#V}" -ge 8 ] || echo "extraction failed"
grep -rc "$V" tests/data/golden_board tests/golden_client.py tests/test_golden_board.py | grep -v ':0$'
grep -c '^\[odds\]' tests/data/golden_board/config.toml
.venv/bin/pytest -q
```

- [ ] **Step 5: Commit the fixture, then the marker and ignore rules**

```bash
git add tests/data/golden_board
git commit -m "test(v17c): the golden board — GW<N> recorded <date>, <count> responses, levers <...>"
git add pyproject.toml .gitignore
git commit -m "chore(v17c): the golden marker and the fixture's ignore exceptions"
```

Then spec §10, ff-merge, push, security ritual, ROADMAP, GUIDE §10 and §11, tracker, memory.

---

## Self-review

**Spec coverage.** §1 items 1–2 → Task 4's two golden tests; item 3 → Task 3's skip tests; item 4 → Task 3's size test and Task 5; item 5 → Task 5. §2.1–2.2 → Task 1; §2.3 → Task 2 and `run_golden`; §2.4–2.6 → Task 3; §2.7 → `golden_config` literal; §2.8 → `run_golden`'s one patch; §2.9 → `run_golden` reads the two files; §2.10 → Task 4's `record`/`write_expected`/`main`; §2.11 → Task 5's marker. §4's header keys all appear in `write_expected`. §7: no `src/` file, no pin.

**Placeholders.** None; every step carries its code. Task 5's commit subject has the counts filled at record time by the orchestrator.

**Type consistency.** `save_bundle(directory, bodies)` / `load_bundle(directory)` used the same way in Tasks 1 and 4; `stale_inputs(header, repo)` in Tasks 3 and 4; `run_golden(root, client=None) -> (advice, state)` in Task 4's test, `write_expected` and `record`; `levers_below_floor` in Tasks 3 and 4; `write_golden_toml(cfg, path)` in Tasks 2, 3 and 4.

**One deliberate deviation from the spec's §4 sketch:** `player_props` stays at the loader's default rather than `False`, because without an `[odds]` table `load_config` cannot produce `False` and the round trip would fail; it is unreachable without a key. The spec's §4 sentence is corrected in the docs commit.
