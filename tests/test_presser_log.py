"""The presser shadow log: what the classifier would have done."""

from __future__ import annotations

import pandas as pd

from gaffer.data.news.presser_log import (PRESSER_COLS, PRESSER_DAMP,
                                          PRESSER_PATH, append_presser,
                                          load_presser_log, presser_rows,
                                          would_factor)


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "p_play": 0.9, "llm_verdict": "rotation_risk",
         "llm_confidence": 0.8},
        {"code": 2, "gw": 5, "p_play": 0.8, "llm_verdict": "irrelevant",
         "llm_confidence": 0.4},
        {"code": 3, "gw": 5, "p_play": 0.7, "llm_verdict": None,
         "llm_confidence": None}])


def test_only_a_rotation_risk_would_change_a_number():
    """The other five verdicts either duplicate the structured feed or say
    nothing; a second damp on top of a parsed "Ruled Out" is double-counting
    one claim."""
    assert would_factor("rotation_risk") == PRESSER_DAMP
    for verdict in ("confirmed_starter", "knock", "assess", "ruled_out",
                    "irrelevant"):
        assert would_factor(verdict) == 1.0


def test_the_rows_carry_before_and_would():
    rows = presser_rows(_frame(), season="2026-27", gw=5, run_at="now")
    assert list(rows.columns) == PRESSER_COLS
    assert sorted(rows["code"]) == [1, 2]      # the unclassified row is absent
    first = rows.set_index("code").loc[1]
    assert first["p_play_before"] == 0.9
    assert round(first["p_play_would"], 4) == round(0.9 * PRESSER_DAMP, 4)


def test_a_frame_with_no_verdicts_writes_nothing():
    bare = _frame().drop(columns=["llm_verdict", "llm_confidence"])
    assert presser_rows(bare, season="2026-27", gw=5, run_at="now").empty


def test_the_log_appends_and_survives_a_reread(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = presser_rows(_frame(), season="2026-27", gw=5, run_at="t1")
    assert append_presser(rows) == 2
    later = presser_rows(_frame(), season="2026-27", gw=6, run_at="t2")
    assert append_presser(later) == 2
    back = load_presser_log()
    assert len(back) == 4
    assert set(back["gw"]) == {5, 6}
    assert (tmp_path / PRESSER_PATH).is_file()


def test_the_same_run_written_twice_is_banked_once(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = presser_rows(_frame(), season="2026-27", gw=5, run_at="t1")
    append_presser(rows)
    append_presser(rows)
    assert len(load_presser_log()) == 2


def test_an_absent_log_reads_as_an_empty_frame(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    out = load_presser_log()
    assert out.empty and list(out.columns) == PRESSER_COLS
