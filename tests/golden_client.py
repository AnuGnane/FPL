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
import hashlib
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from gaffer.api.client import FPLClient
from gaffer.config import NO_CAP, Config

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
    # GzipFile rather than gzip.open: only the former takes ``mtime``, and a
    # zero there keeps the clock out of the header so a re-record with the same
    # answers really is the same bytes (spec §2.2).
    with open(path, "wb") as raw_fh:
        # An empty filename for the same reason: left to itself GzipFile would
        # stamp the absolute path of the file handle into the header.
        with gzip.GzipFile(filename="", fileobj=raw_fh, mode="wb",
                           compresslevel=9, mtime=0) as fh:
            fh.write(raw)
    return path


def load_bundle(directory: Path) -> dict[str, object]:
    """The read side of §2.2's bundle."""
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
        # ensure_ascii=False so an astral character stays itself: escaped, it
        # would come out as a surrogate pair, which tomllib rejects.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    if isinstance(value, dict):
        # Bare keys: the only dict field is ``top_n``, keyed by position code.
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
             # Not spelling the section name here: the test greps the written
             # file for it, and a header mentioning it would pass for the
             # wrong reason (v17c §2.3).
             "# golden_config(). The odds table is absent, by design.", ""]
    for section, keys in _TOML_LAYOUT.items():
        lines.append(f"[{section}]")
        for key, field_name in keys:
            value = values[field_name]
            if value is None:
                continue
            lines.append(f"{key} = {_toml(value)}")
        if section == "optimizer":
            # v17c §2.3: not a Config field (see NON_FIELD_OPTIMIZER_KEYS),
            # read by price_timing() on the solve path; written so a default
            # flip cannot move the golden silently. xg_per_shot is train-time
            # only and lineup_providers is moot with news off, so neither is
            # written.
            lines.append("price_timing = true")
        lines.append("")
    Path(path).write_text("\n".join(lines))


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
