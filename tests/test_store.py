import pandas as pd

from gaffer.data import store


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    df = pd.DataFrame({"a": [1, 2]})
    store.save(df, "live/test.parquet")
    out = store.load("live/test.parquet")
    assert out["a"].tolist() == [1, 2]


def test_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    assert not store.exists("live/nope.parquet")
    store.save(pd.DataFrame({"a": [1]}), "live/yes.parquet")
    assert store.exists("live/yes.parquet")
