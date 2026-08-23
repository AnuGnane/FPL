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
