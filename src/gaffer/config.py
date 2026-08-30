from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from gaffer.errors import GafferError


@dataclass
class Config:
    entry_id: int
    league_id: int
    horizon: int = 3
    decay: float = 0.85
    vice_weight: float = 0.1
    bench_weight: float = 0.10
    ft_value: float = 1.5
    itb_value: float = 0.05
    hit_cost: int = 4
    train_seasons: list[str] = field(default_factory=list)
    current_season: str = "2026-27"
    odds_api_key: str = ""
    player_props: bool = True
    ags_blend_weight: float = 0.5
    understat_enabled: bool = True
    # --- v4c decision layer ------------------------------------------------
    # Every one of these defaults to the pre-v4c behaviour. n = 0 means "solve
    # once, deterministically"; the two objective knobs are neutral elements.
    scenarios_n: int = 0
    scenarios_seed: int = 20260825
    transfer_threshold: float = 0.60
    irreversible_threshold: float = 0.75
    decision_priors: bool = True
    ft_use_penalty: float = 0.0
    bench_curve: list[float] | None = None
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
    z_deadband: float = 0.25
    tier_eo: bool = True
    tier_sample: int = 300
    # --- v5 news layer -----------------------------------------------------
    # Defaults are shipped-behaviour-ON, individually switchable. Every source
    # degrades to the official-flags path by itself (spec §7), so these exist
    # to turn off a *working* source, not to survive a broken one.
    # The Transfermarkt return curves are a committed asset rather than a
    # runtime source, so they carry no flag here.
    news_enabled: bool = True
    news_injuries: bool = True
    news_lineups: bool = True
    news_cache_hours: int = 6
    news_min_coverage: float = 0.5
    # --- v8a news layer ----------------------------------------------------
    # Two serve-time upgrades and one classifier, all readable by the news
    # seams themselves because ``advise`` is protected and cannot learn to
    # pass them. Defaults are the pre-v8a behaviour with one exception: the
    # notable-absence damp is ON, because it can only ever lower a number and
    # the case it catches — a regular quietly left out of the predicted XI —
    # is the one the layer exists for.
    news_llm_classifier: bool = False
    news_llm_shadow: bool = True
    news_llm_command: str = "claude -p --output-format json"
    news_llm_timeout_s: int = 120
    news_lineup_absence: bool = True
    news_lineup_absence_damp: float = 0.75
    news_lineup_start_floor: float = 0.0


def load_config(path: Path | str = "config.toml") -> Config:
    file = Path(path)
    if not file.exists():
        # A fresh clone has no config.toml: it carries an API key, so it is
        # gitignored. Say what to do instead of raising FileNotFoundError,
        # which the web app would have turned into a 500.
        raise GafferError(
            f"no {file} — copy config.example.toml to config.toml and set "
            "fpl.entry_id and fpl.league_id")
    raw = tomllib.loads(file.read_text())
    odds = raw.get("odds", {})
    # [scenarios] is optional and its TOML keys are deliberately shorter than
    # the field names (n, seed), so it is read key-by-key like [odds] rather
    # than splatted. [optimizer] keeps splatting, so ft_use_penalty and
    # bench_curve need no line here.
    scen = raw.get("scenarios", {})
    league = raw.get("league", {})
    news = raw.get("news", {})
    return Config(
        entry_id=raw["fpl"]["entry_id"],
        league_id=raw["fpl"]["league_id"],
        **raw.get("optimizer", {}),
        **raw.get("data", {}),
        # Read explicitly rather than splatted: [odds] is optional and its
        # TOML keys do not all match the dataclass field names. Both new
        # switches default on and degrade by themselves when the data or the
        # key is missing, so nobody has to edit config.toml to keep the old
        # behaviour.
        odds_api_key=odds.get("api_key", ""),
        player_props=bool(odds.get("player_props", True)),
        ags_blend_weight=float(odds.get("ags_blend_weight", 0.5)),
        understat_enabled=bool(
            raw.get("understat", {}).get("enabled", True)),
        scenarios_n=int(scen.get("n", 0)),
        scenarios_seed=int(scen.get("seed", 20260825)),
        transfer_threshold=float(scen.get("transfer_threshold", 0.60)),
        irreversible_threshold=float(
            scen.get("irreversible_threshold", 0.75)),
        decision_priors=bool(scen.get("decision_priors", True)),
        z_scale=float(league.get("z_scale", 1.5)),
        lambda_cap=float(league.get("lambda_cap", 0.5)),
        sigma_floor=float(league.get("sigma_floor", 8.0)),
        sigma_cap=float(league.get("sigma_cap", 30.0)),
        sigma_min_weeks=int(league.get("sigma_min_weeks", 6)),
        z_deadband=float(league.get("z_deadband", 0.25)),
        tier_eo=bool(league.get("tier_eo", True)),
        tier_sample=int(league.get("tier_sample", 300)),
        # Read key-by-key like [odds] and [league]: the TOML keys are
        # deliberately shorter than the dataclass fields (enabled, injuries)
        # so the section reads as prose in config.toml.
        news_enabled=bool(news.get("enabled", True)),
        news_injuries=bool(news.get("injuries", True)),
        news_lineups=bool(news.get("lineups", True)),
        news_cache_hours=int(news.get("cache_hours", 6)),
        news_min_coverage=float(news.get("min_coverage", 0.5)),
        news_llm_classifier=bool(news.get("llm_classifier", False)),
        news_llm_shadow=bool(news.get("llm_shadow", True)),
        news_llm_command=str(news.get("llm_command",
                                      "claude -p --output-format json")),
        news_llm_timeout_s=int(news.get("llm_timeout_s", 120)),
        news_lineup_absence=bool(news.get("lineup_absence", True)),
        news_lineup_absence_damp=float(news.get("lineup_absence_damp", 0.75)),
        news_lineup_start_floor=float(news.get("lineup_start_floor", 0.0)),
    )


@lru_cache(maxsize=1)
def serving_config() -> Config:
    """The config as the *serve-time seams* read it — never raising.

    ``advise.py`` is protected, so v8a's fetcher- and availability-level
    switches cannot arrive as arguments; they are read here instead. Two
    consequences are deliberate. It is cached, because a fetcher must not
    re-read a TOML file per call. And it degrades to the dataclass defaults
    rather than raising, because a clone with no ``config.toml`` still has to
    predict — the loud "copy config.example.toml" error belongs to the CLI's
    own :func:`load_config` call, not to a news source.

    Tests that change ``config.toml`` under a running process call
    ``serving_config.cache_clear()``.
    """
    try:
        return load_config()
    except Exception:  # noqa: BLE001 — serving never blocks on config
        return Config(entry_id=0, league_id=0)
