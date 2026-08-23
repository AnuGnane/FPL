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
