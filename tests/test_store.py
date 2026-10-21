"""v1 — the parquet store every table is saved to and loaded from.

A save must round-trip and ``exists`` must be true only once a file is
written, since callers branch on it to decide whether to fetch.
"""
import pandas as pd

from gaffer.data import store


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = pd.DataFrame({"a": [1, 2]})
    store.save(df, "live/test.parquet")
    out = store.load("live/test.parquet")
    assert out["a"].tolist() == [1, 2]


def test_exists_is_true_only_once_a_file_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert not store.exists("live/nope.parquet")
    store.save(pd.DataFrame({"a": [1]}), "live/yes.parquet")
    assert store.exists("live/yes.parquet")
