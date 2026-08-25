from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


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


def load_config(path: Path | str = "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text())
    odds = raw.get("odds", {})
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
    )
