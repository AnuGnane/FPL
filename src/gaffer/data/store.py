"""The shared parquet seam: most tables under ``data/`` are saved and loaded here.

Paths are relative to ``DATA_DIR``, so a test can point the whole store at a
temporary directory by patching that one name.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")


def save(df: pd.DataFrame, rel: str) -> Path:
    """Write ``df`` to ``DATA_DIR / rel`` as parquet, making its directory, and return the path."""
    path = DATA_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def load(rel: str) -> pd.DataFrame:
    """Read the parquet at ``DATA_DIR / rel``; resolved at call time so a test's redirect holds."""
    return pd.read_parquet(DATA_DIR / rel)


def exists(rel: str) -> bool:
    """Whether ``DATA_DIR / rel`` is on disk, so a reader can degrade instead of raising."""
    return (DATA_DIR / rel).exists()
