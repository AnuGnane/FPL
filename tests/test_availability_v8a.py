"""v8a's serve-time layer: the widened contract, the damp, the floor."""

from __future__ import annotations

import pandas as pd

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.data.news.normalize import AVAIL_COLS, availability_frame
from gaffer.snapshot import SNAPSHOT_COLS, snapshot_rows


def _official() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "status": "a", "chance_of_playing": None},
        {"code": 2, "status": "a", "chance_of_playing": None},
        {"code": 3, "status": "s", "chance_of_playing": 0}])


def test_the_two_column_lists_are_the_same_list():
    """They are written out twice — the artifact's and the normalizer's — and
    a drift between them is a silently dropped column."""
    assert AVAIL_COLS == AVAILABILITY_COLS


def test_the_contract_carries_the_three_new_columns():
    for col in ("absence_damp", "llm_verdict", "llm_confidence"):
        assert col in AVAILABILITY_COLS


def test_an_empty_news_run_still_produces_every_column():
    out = availability_frame(_official(), None, None, gw=5, events=None)
    assert list(out.columns) == AVAIL_COLS
    assert out["absence_damp"].isna().all()
    assert out["llm_verdict"].isna().all()


def test_the_line_up_frame_carries_a_damp_through():
    lineups = pd.DataFrame([
        {"code": 1, "p_start_hint": None, "absence_damp": 0.75,
         "source": "lineups", "fetched_at": "2026-09-04T09:00:00Z"}])
    out = availability_frame(_official(), None, lineups, gw=5, events=None)
    assert out.set_index("code").loc[1, "absence_damp"] == 0.75
    assert pd.isna(out.set_index("code").loc[2, "absence_damp"])


def test_a_banned_player_takes_no_damp():
    """Official s/u/n is authoritative — rule 1 has not moved."""
    lineups = pd.DataFrame([
        {"code": 3, "p_start_hint": None, "absence_damp": 0.75,
         "source": "lineups", "fetched_at": "2026-09-04T09:00:00Z"}])
    out = availability_frame(_official(), None, lineups, gw=5, events=None)
    assert pd.isna(out.set_index("code").loc[3, "absence_damp"])


def test_the_snapshot_log_inherits_the_new_columns_with_settled_dtypes():
    frame = availability_frame(_official(), None, None, gw=5, events=None)
    rows = snapshot_rows(frame, gw=5, season="2026-27", day="2026-09-04")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert str(rows["absence_damp"].dtype).startswith("float")
    assert str(rows["llm_confidence"].dtype).startswith("float")
    assert str(rows["llm_verdict"].dtype) == "string"


def test_a_log_row_from_before_the_widening_still_appends(tmp_path,
                                                          monkeypatch):
    """The banked log predates these columns. Append-by-rewrite has to read
    the old shape and write the new one rather than refusing the file."""
    from gaffer.data import store as store_mod
    from gaffer.snapshot import SNAPSHOT_PATH, append_snapshot, load_snapshot_log

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    old = pd.DataFrame([{"season": "2026-27", "gw": 4, "snap_date":
                         "2026-09-01", "code": 1, "status": "a",
                         "chance_of_playing": None, "injury_type": None,
                         "expected_return_gw": None, "p_start_hint": None,
                         "source": None, "fetched_at": None}])
    store_mod.save(old, SNAPSHOT_PATH)
    frame = availability_frame(_official(), None, None, gw=5, events=None)
    append_snapshot(snapshot_rows(frame, gw=5, season="2026-27",
                                  day="2026-09-04"))
    back = load_snapshot_log()
    assert list(back.columns) == SNAPSHOT_COLS
    assert set(back["snap_date"]) == {"2026-09-01", "2026-09-04"}
