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
