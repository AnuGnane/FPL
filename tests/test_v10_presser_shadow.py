"""§F2b: the presser classifier's would-be factor, banked beside the rest.

The classifier stays off. This is the evidence that would let it be turned on
— ``p_play_news x would_factor(verdict)`` written into the shadow log every
week, scored as a third side once rows accrue.

The route is a join from the presser log rather than a column on ``comp``,
and that is forced rather than chosen (plan A10): ``apply_availability``
returns ``out.drop(columns=[...] + news_cols)``, so ``llm_verdict`` is gone
before ``predict_components`` builds ``comp``, and ``advise.py`` — which names
the columns it carries — is protected. The route that exists is better anyway:
``write_presser`` runs *inside* ``apply_availability``, one line before
``write_shadow`` is called, so this run's verdicts are on disk by the time the
shadow row is written.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.news.presser_log import (PRESSER_COLS, PRESSER_DAMP,
                                          PRESSER_PATH)
from gaffer.evaluation import score_news_shadow
from gaffer.news_shadow import (SHADOW_COLS, SHADOW_PATH, load_shadow,
                                shadow_rows, write_shadow)

SEASON = "2025-26"


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _comp(codes=(1, 2), gw: int = 5) -> pd.DataFrame:
    n = len(codes)
    return pd.DataFrame({
        "code": list(codes), "gw": [gw] * n,
        "p_play": [0.9, 0.5][:n] or [0.9],
        "p_play_flags": [0.8, 0.4][:n] or [0.8],
        "e_min": [80.0, 40.0][:n] or [80.0],
        "e_min_flags": [70.0, 30.0][:n] or [70.0],
    })


def _bank_presser(rows: list[dict]):
    frame = pd.DataFrame(rows, columns=PRESSER_COLS)
    store.save(frame, PRESSER_PATH)


def _verdict(code: int, verdict: str, gw: int = 5, season: str = SEASON):
    return {"season": season, "gw": gw, "code": code, "verdict": verdict,
            "confidence": 0.9, "p_play_before": 0.9,
            "p_play_would": 0.72, "run_at": "t"}


# --- the join -------------------------------------------------------------

def test_a_banked_verdict_reaches_the_shadow_row():
    _bank_presser([_verdict(1, "rotation_risk")])
    rows = shadow_rows(_comp(), 5, season=SEASON).set_index("code")
    assert rows.loc[1, "p_play_presser"] == pytest.approx(
        rows.loc[1, "p_play_news"] * PRESSER_DAMP)


def test_a_code_with_no_verdict_keeps_p_play_news():
    """Not a null: the scorer's join must not lose rows for players the
    classifier never saw, and "no opinion" is arithmetically "no change"."""
    _bank_presser([_verdict(1, "rotation_risk")])
    rows = shadow_rows(_comp(), 5, season=SEASON).set_index("code")
    assert rows.loc[2, "p_play_presser"] == rows.loc[2, "p_play_news"]
    assert rows["p_play_presser"].notna().all()


def test_an_informational_verdict_changes_nothing():
    """Only rotation_risk moves a number; the codebase's standing rule is
    that news lowers a number and never raises one."""
    _bank_presser([_verdict(1, "confirmed_starter")])
    rows = shadow_rows(_comp(), 5, season=SEASON).set_index("code")
    assert rows.loc[1, "p_play_presser"] == rows.loc[1, "p_play_news"]


def test_the_join_is_keyed_on_all_three_of_season_gw_and_code():
    """Gameweek 5 comes round every year. A verdict banked for last season's
    GW5 must not reach this season's."""
    _bank_presser([_verdict(1, "rotation_risk", season="2024-25"),
                   _verdict(2, "rotation_risk", gw=6)])
    rows = shadow_rows(_comp(), 5, season=SEASON).set_index("code")
    assert rows.loc[1, "p_play_presser"] == rows.loc[1, "p_play_news"]
    assert rows.loc[2, "p_play_presser"] == rows.loc[2, "p_play_news"]


def test_a_missing_presser_parquet_is_not_an_error(capsys):
    rows = shadow_rows(_comp(), 5, season=SEASON)
    assert (rows["p_play_presser"] == rows["p_play_news"]).all()
    assert "not joined" not in capsys.readouterr().out


def test_a_corrupt_presser_parquet_does_not_stop_the_shadow_row(tmp_path):
    """Instrumentation does not block instrumentation."""
    path = tmp_path / "data" / PRESSER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a parquet file at all")
    rows = shadow_rows(_comp(), 5, season=SEASON)
    assert (rows["p_play_presser"] == rows["p_play_news"]).all()
    assert write_shadow(_comp(), 5) is not None


# --- the schema -----------------------------------------------------------

def test_shadow_cols_gained_exactly_one_entry_before_run_at():
    assert SHADOW_COLS == ["season", "gw", "code", "p_play_news",
                           "p_play_flags", "e_min_news", "e_min_flags",
                           "p_play_presser", "run_at"]


def test_a_pre_v10_parquet_reads_back():
    """Save a frame with no p_play_presser at all, then append to it."""
    old = pd.DataFrame({
        "season": [SEASON], "gw": [4], "code": [9], "p_play_news": [0.7],
        "p_play_flags": [0.6], "e_min_news": [60.0], "e_min_flags": [50.0],
        "run_at": ["t"]})
    store.save(old, SHADOW_PATH)
    # ``write_shadow`` reads the season from ``_current_season()``, and a
    # tmp_path with no config.toml gives "" — so the banked verdict is keyed
    # the same way. The three-part key is asserted on its own above.
    _bank_presser([_verdict(1, "rotation_risk", season="")])
    assert write_shadow(_comp(), 5) is not None
    raw = load_shadow()
    assert list(raw.columns) == SHADOW_COLS
    back = raw.set_index(["gw", "code"])
    assert pd.isna(back.loc[(4, 9), "p_play_presser"])       # the old row
    assert back.loc[(5, 1), "p_play_presser"] == pytest.approx(0.9 * 0.8)


# --- the scorer -----------------------------------------------------------

def _actuals():
    return pd.DataFrame({"gw": [5, 5], "code": [1, 2],
                         "minutes": [90.0, 0.0]})


def _shadow(presser=None) -> pd.DataFrame:
    frame = pd.DataFrame({
        "season": [SEASON, SEASON], "gw": [5, 5], "code": [1, 2],
        "p_play_news": [0.9, 0.5], "p_play_flags": [0.8, 0.4],
        "e_min_news": [80.0, 40.0], "e_min_flags": [70.0, 30.0],
        "run_at": ["t", "t"]})
    if presser is not None:
        frame["p_play_presser"] = presser
    return frame


def test_a_pre_v10_log_scores_exactly_as_it_did_on_main():
    """Plan A15. No ``brier_presser`` key at all — not a ``None`` one."""
    out = score_news_shadow(_shadow(), _actuals())
    assert set(out["overall"]) == {"brier_news", "brier_flags", "mae_news",
                                   "mae_flags", "rows"}
    assert list(out["overall"]) == ["brier_news", "brier_flags", "mae_news",
                                    "mae_flags", "rows"]
    assert all("presser" not in k for row in out["by_gw"] for k in row)


def test_the_third_side_is_scored_when_it_differs():
    out = score_news_shadow(_shadow([0.72, 0.5]), _actuals())
    assert "brier_presser" in out["overall"]
    assert "mae_presser" not in out["overall"]     # a p_play factor, no e_min
    assert out["by_gw"][0]["brier_presser"] == pytest.approx(
        ((0.72 - 1.0) ** 2 + (0.5 - 0.0) ** 2) / 2, abs=1e-4)
    assert "cum_brier_presser" in out["by_gw"][0]


def test_an_all_one_factor_is_not_scored():
    """Every p_play_presser == p_play_news means the classifier said nothing,
    and a third line identical to the first is worse than no line."""
    out = score_news_shadow(_shadow([0.9, 0.5]), _actuals())
    assert "brier_presser" not in out["overall"]


def test_an_all_null_column_is_not_a_side_at_all():
    """A parquet whose column exists only because ``write_shadow`` back-filled
    it. It is not equal to ``p_play_news`` — it is not equal to anything — and
    gating on inequality alone would score a column of NaN."""
    out = score_news_shadow(_shadow([float("nan")] * 2), _actuals())
    assert all("presser" not in k for k in out["overall"])
    assert all("presser" not in k for row in out["by_gw"] for k in row)


def _mixed_vintage() -> pd.DataFrame:
    """One pre-v10 row (back-filled NaN) and one post-v10 row, same gameweek."""
    frame = _shadow()
    frame["p_play_presser"] = [float("nan"), 0.25]
    return frame


def test_the_presser_side_is_scored_on_its_own_rows_only():
    out = score_news_shadow(_mixed_vintage(), _actuals())
    # Code 2 is the row that has a verdict: p_play_presser 0.25, minutes 0.
    assert out["overall"]["brier_presser"] == pytest.approx(0.25 ** 2,
                                                            abs=1e-4)
    assert out["overall"]["rows_presser"] == 1
    # The other two sides still score both rows, and say so.
    assert out["overall"]["rows"] == 2


def test_the_presser_row_count_is_labelled_to_the_presser_side():
    """The N2 verdict is read off these two numbers together: a Brier over
    one row and a Brier over two hundred are not the same evidence."""
    out = score_news_shadow(_mixed_vintage(), _actuals())
    assert out["by_gw"][0]["rows_presser"] == 1
    assert out["by_gw"][0]["rows"] == 2
    assert out["by_gw"][0]["cum_brier_presser"] == pytest.approx(
        out["overall"]["brier_presser"], abs=1e-9)


def test_a_gameweek_with_no_verdicts_carries_no_presser_keys():
    """The column exists and has values — in another week. This week's entry
    must be absent, never NaN: ``save_evaluation`` serialises with
    ``allow_nan=False`` and a NaN here would take the whole artifact down."""
    frame = pd.concat([_mixed_vintage(),
                       _shadow().assign(gw=6, p_play_presser=float("nan"))],
                      ignore_index=True)
    actuals = pd.concat([_actuals(), _actuals().assign(gw=6)],
                        ignore_index=True)
    out = score_news_shadow(frame, actuals)
    gw6 = next(r for r in out["by_gw"] if r["gw"] == 6)
    assert "brier_presser" not in gw6
    assert "rows_presser" not in gw6
    # The cumulative line still carries GW5's verdict, which is the point of a
    # cumulative line.
    assert gw6["cum_brier_presser"] == pytest.approx(0.25 ** 2, abs=1e-4)
