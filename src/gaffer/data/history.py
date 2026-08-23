"""Historical training corpus from the vaastav/Fantasy-Premier-League archive.

Produces per-player per-GW rows in the same ``CANONICAL_COLS`` shape as the
live ingestion, so feature engineering can run over ``concat(history, live)``.
``element`` ids reset each season — ``code`` (joined from ``players_raw``) is
the stable cross-season player key.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd

from gaffer.data import store
from gaffer.data.live import CANONICAL_COLS, RENAME, XG_FIELDS

VAASTAV = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
POS_NORM = {"GK": "GKP", "GKP": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}


def _download_csv(url: str, dest: Path) -> pd.DataFrame:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    try:
        return pd.read_csv(dest)
    except UnicodeDecodeError:  # some vaastav seasons are latin-1
        return pd.read_csv(dest, encoding="latin-1")


def merged_gw_to_canonical(
    merged: pd.DataFrame,
    players_raw: pd.DataFrame,
    teams: pd.DataFrame,
    season: str,
    season_idx: int,
) -> pd.DataFrame:
    """Map one season's ``merged_gw.csv`` to the canonical ``player_gw`` shape."""
    df = merged.rename(columns=RENAME)
    for api_key, col in XG_FIELDS.items():
        if api_key in df.columns:
            df[col] = pd.to_numeric(df[api_key], errors="coerce")
    # 2024-25 carries "AM" rows: Assistant-Manager chip entries, not players.
    # Anything that does not normalise to a real FPL position is dropped.
    df["position"] = df["position"].map(POS_NORM)
    df = df[df["position"].notna()].copy()
    df["season"], df["season_idx"] = season, season_idx
    gw = df["gw"] if "gw" in df.columns else df["GW"]
    df["gw"] = pd.to_numeric(gw, errors="coerce")
    df = df.merge(
        players_raw[["id", "code"]].rename(columns={"id": "element"}),
        on="element",
        how="left",
    )
    df = df.merge(
        teams[["id", "code"]].rename(columns={"id": "opponent_team", "code": "opp_code"}),
        on="opponent_team",
        how="left",
    )
    if "team_code" in players_raw.columns:
        team_of_element = players_raw.set_index("id")["team_code"]
        df["team_code"] = df["element"].map(team_of_element)
    for c in CANONICAL_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    out = df[CANONICAL_COLS].copy()
    numeric = [
        c
        for c in CANONICAL_COLS
        if c not in ("season", "name", "position", "was_home", "kickoff_time")
    ]
    out[numeric] = out[numeric].apply(pd.to_numeric, errors="coerce")
    return out


def build_history(
    seasons: list[str],
    cache_dir: Path = Path("data/raw/vaastav"),
) -> pd.DataFrame:
    """Download + concatenate seasons -> data/history/player_gw.parquet."""
    frames = []
    for idx, season in enumerate(seasons):
        merged = _download_csv(
            f"{VAASTAV}/{season}/gws/merged_gw.csv",
            cache_dir / season / "merged_gw.csv",
        )
        players_raw = _download_csv(
            f"{VAASTAV}/{season}/players_raw.csv",
            cache_dir / season / "players_raw.csv",
        )
        teams = _download_csv(
            f"{VAASTAV}/{season}/teams.csv", cache_dir / season / "teams.csv"
        )
        frames.append(
            merged_gw_to_canonical(merged, players_raw, teams, season, idx)
        )
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["code", "gw"])
    store.save(df, "history/player_gw.parquet")
    return df


def build_history_fixtures(
    seasons: list[str],
    cache_dir: Path = Path("data/raw/vaastav"),
) -> pd.DataFrame:
    """Historical fixtures with results, team codes mapped — feeds Elo (Task 6)."""
    frames = []
    for idx, season in enumerate(seasons):
        fx = _download_csv(
            f"{VAASTAV}/{season}/fixtures.csv", cache_dir / season / "fixtures.csv"
        )
        teams = _download_csv(
            f"{VAASTAV}/{season}/teams.csv", cache_dir / season / "teams.csv"
        )
        code = dict(zip(teams["id"], teams["code"]))
        fx = fx.dropna(subset=["team_h_score"])
        frames.append(
            pd.DataFrame(
                {
                    "season": season,
                    "season_idx": idx,
                    "gw": pd.to_numeric(fx["event"], errors="coerce"),
                    "kickoff_time": fx["kickoff_time"],
                    "home_code": fx["team_h"].map(code),
                    "away_code": fx["team_a"].map(code),
                    "home_goals": fx["team_h_score"],
                    "away_goals": fx["team_a_score"],
                }
            )
        )
    df = pd.concat(frames, ignore_index=True).dropna(subset=["gw"])
    store.save(df, "history/fixtures.parquet")
    return df
