"""The N2 shadow log: what the news layer changed, banked for scoring."""

from __future__ import annotations

import pandas as pd

from gaffer.news_shadow import (SHADOW_COLS, SHADOW_PATH, load_shadow,
                                shadow_rows, write_shadow)


def _comp() -> pd.DataFrame:
    """A component frame in predict_components' v5 shape: one row per
    player-fixture, carrying both the news and the flags-only minutes."""
    return pd.DataFrame({
        "code": [1, 1, 2], "gw": [5, 6, 5],
        "p_play": [0.25, 0.80, 0.90], "p_play_flags": [0.90, 0.90, 0.90],
        "e_min": [20.0, 70.0, 85.0], "e_min_flags": [80.0, 80.0, 85.0],
        "p60": [0.1, 0.7, 0.8]})


def test_shadow_rows_keep_only_the_first_gameweek():
    """The scorer joins against completed gameweeks; a GW+1 row would be
    scored against the wrong week's minutes."""
    rows = shadow_rows(_comp(), gw=5)
    assert list(rows.columns) == SHADOW_COLS
    assert set(rows["gw"]) == {5}
    assert sorted(rows["code"]) == [1, 2]


def test_shadow_rows_carry_both_sides_of_the_comparison():
    rows = shadow_rows(_comp(), gw=5).set_index("code")
    assert rows.loc[1, "p_play_news"] == 0.25
    assert rows.loc[1, "p_play_flags"] == 0.90
    assert rows.loc[1, "e_min_news"] == 20.0
    assert rows.loc[1, "e_min_flags"] == 80.0
    assert rows["run_at"].notna().all()


def test_shadow_rows_average_a_double_gameweek_rather_than_duplicating():
    """One row per (gw, code): a double gameweek is two fixtures and one
    Brier outcome, and two rows would weight that player twice."""
    dgw = pd.DataFrame({
        "code": [1, 1], "gw": [5, 5],
        "p_play": [0.4, 0.6], "p_play_flags": [0.9, 0.9],
        "e_min": [30.0, 50.0], "e_min_flags": [80.0, 80.0]})
    rows = shadow_rows(dgw, gw=5)
    assert len(rows) == 1
    assert abs(rows["p_play_news"].iloc[0] - 0.5) < 1e-9


def test_write_shadow_appends_across_runs(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    write_shadow(_comp(), gw=5)
    write_shadow(_comp(), gw=5)
    out = load_shadow()
    assert len(out) == 4
    assert (tmp_path / SHADOW_PATH).exists()


def test_write_shadow_never_raises_on_a_frame_it_cannot_read(tmp_path,
                                                             monkeypatch):
    """Instrumentation must never cost advice. A component frame with no
    flags columns (news off) writes nothing and returns None."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    assert write_shadow(pd.DataFrame({"code": [1]}), gw=5) is None
    assert write_shadow(None, gw=5) is None


def test_write_shadow_skips_a_run_where_news_changed_nothing(tmp_path,
                                                             monkeypatch):
    """Every row identical means the news layer was inert — a source was
    down, or nobody was flagged. Banking thousands of tied rows would drown
    the signal the cumulative table is looking for."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    tied = pd.DataFrame({"code": [1], "gw": [5], "p_play": [0.9],
                         "p_play_flags": [0.9], "e_min": [80.0],
                         "e_min_flags": [80.0]})
    assert write_shadow(tied, gw=5) is None


def _shadow() -> pd.DataFrame:
    """Two gameweeks. In GW5 the news layer is right about code 1 (it said
    0.1, he did not play; flags said 0.9). In GW6 it is wrong about code 2."""
    return pd.DataFrame({
        "gw": [5, 5, 6, 6],
        "code": [1, 2, 1, 2],
        "p_play_news": [0.1, 0.9, 0.9, 0.2],
        "p_play_flags": [0.9, 0.9, 0.9, 0.9],
        "e_min_news": [10.0, 85.0, 85.0, 20.0],
        "e_min_flags": [85.0, 85.0, 85.0, 85.0],
        "run_at": ["2026-09-04T09:00:00+00:00"] * 4})


def _actuals() -> pd.DataFrame:
    return pd.DataFrame({
        "gw": [5, 5, 6, 6], "code": [1, 2, 1, 2],
        "minutes": [0.0, 90.0, 90.0, 90.0]})


def test_score_news_shadow_scores_brier_and_mae_on_both_sides():
    from gaffer.evaluation import score_news_shadow

    out = score_news_shadow(_shadow(), _actuals())
    assert out["rows"] == 4
    assert set(out["overall"]) == {"brier_news", "brier_flags", "mae_news",
                                   "mae_flags", "rows"}
    # GW5's code 1 is the whole story: news said 0.1 and he played 0 minutes.
    assert out["overall"]["brier_news"] < out["overall"]["brier_flags"]
    assert out["overall"]["mae_news"] < out["overall"]["mae_flags"]


def test_score_news_shadow_reports_per_gameweek_and_cumulative():
    from gaffer.evaluation import score_news_shadow

    out = score_news_shadow(_shadow(), _actuals())
    gws = {row["gw"]: row for row in out["by_gw"]}
    assert set(gws) == {5, 6}
    assert gws[5]["brier_news"] < gws[5]["brier_flags"]   # news was right
    assert gws[6]["brier_news"] > gws[6]["brier_flags"]   # news was wrong
    # The cumulative column is the running total, not the weekly number.
    assert gws[6]["cum_brier_news"] == out["overall"]["brier_news"]


def test_score_news_shadow_ignores_gameweeks_with_no_actuals_yet():
    from gaffer.evaluation import score_news_shadow

    out = score_news_shadow(_shadow(), _actuals()[_actuals()["gw"] == 5])
    assert out["rows"] == 2
    assert [row["gw"] for row in out["by_gw"]] == [5]


def test_score_news_shadow_on_an_empty_log_says_so_rather_than_dividing():
    from gaffer.evaluation import score_news_shadow

    out = score_news_shadow(pd.DataFrame(columns=SHADOW_COLS),
                            _actuals())
    assert out["rows"] == 0
    assert out["by_gw"] == []


def test_format_report_renders_the_shadow_table():
    from gaffer.evaluation import format_report, score_news_shadow

    text = format_report("news_shadow", score_news_shadow(_shadow(),
                                                          _actuals()))
    assert "news" in text and "flags" in text
    assert "GW5" in text
