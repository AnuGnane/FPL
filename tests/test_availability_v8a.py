"""v8a's serve-time layer: the widened contract, the damp, the floor."""

from __future__ import annotations

import pandas as pd
import pytest

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
    a drift between them is a silently dropped column.

    v8e's four override columns are the one deliberate difference (plan A4):
    ``AVAIL_COLS`` is the contract of what the *news feeds* produce and an
    override is not a feed, so the artifact list is the feed list plus that
    tail and nothing else.
    """
    from gaffer.artifacts import OVERRIDE_COLS

    assert AVAILABILITY_COLS == AVAIL_COLS + OVERRIDE_COLS


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


# --- the serving side ------------------------------------------------------

from gaffer.models.availability import apply_availability  # noqa: E402


def _pred(codes=(1,), gws=(5, 6, 7), p_play=0.9) -> pd.DataFrame:
    return pd.DataFrame([{"code": c, "gw": g, "p_play": p_play,
                          "p60": p_play * 0.85, "e_min": 80.0}
                         for c in codes for g in gws])


def _avail(**cols) -> pd.DataFrame:
    row = {"code": 1, "status": "a", "chance_of_playing": None,
           "injury_type": None, "expected_return_gw": None,
           "p_start_hint": None, "absence_damp": None, "llm_verdict": None,
           "llm_confidence": None, "source": None, "fetched_at": None}
    row.update(cols)
    return pd.DataFrame([row])


def test_the_damp_bites_on_the_first_gameweek_only():
    out = apply_availability(_pred(), _avail(absence_damp=0.75), curves=None)
    by_gw = out.set_index("gw")
    assert by_gw.loc[5, "p_play"] == pytest.approx(0.9 * 0.75)
    assert by_gw.loc[6, "p_play"] == pytest.approx(0.9)


def test_the_damp_scales_all_three_outputs_together():
    """An untouched p60 beside a damped p_play is the incoherence the
    three-mode model exists to remove."""
    out = apply_availability(_pred(), _avail(absence_damp=0.5), curves=None)
    first = out[out["gw"] == 5].iloc[0]
    assert first["p60"] == pytest.approx(0.9 * 0.85 * 0.5)
    assert first["e_min"] == pytest.approx(80.0 * 0.5)


def test_a_double_gameweek_is_damped_once():
    """One team sheet, one match. Damping both fixtures claims the site
    predicted a tie it never wrote about."""
    pred = pd.DataFrame([{"code": 1, "gw": 5, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0},
                         {"code": 1, "gw": 5, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0}])
    out = apply_availability(pred, _avail(absence_damp=0.5), curves=None)
    assert sorted(round(v, 4) for v in out["p_play"]) == [0.45, 0.9]


def test_no_damp_column_is_the_pre_v8a_arithmetic_exactly():
    with_col = apply_availability(_pred(), _avail(), curves=None)
    without = apply_availability(
        _pred(), _avail().drop(columns=["absence_damp"]), curves=None)
    pd.testing.assert_frame_equal(with_col, without)


def test_the_start_floor_is_off_by_default():
    out = apply_availability(_pred(p_play=0.4), _avail(p_start_hint=1.0),
                             curves=None)
    assert out[out["gw"] == 5].iloc[0]["p_play"] == pytest.approx(0.4)


def test_the_start_floor_raises_a_predicted_starter_when_enabled():
    out = apply_availability(_pred(p_play=0.4), _avail(p_start_hint=1.0),
                             curves=None, start_floor=0.7)
    first = out[out["gw"] == 5].iloc[0]
    assert first["p_play"] == pytest.approx(0.7)
    assert first["p60"] == pytest.approx(0.4 * 0.85 * (0.7 / 0.4))


def test_the_floor_never_touches_a_player_the_page_did_not_start():
    out = apply_availability(_pred(p_play=0.4), _avail(p_start_hint=0.25),
                             curves=None, start_floor=0.7)
    # The ceiling still bites (0.25 < 0.4); the floor never sees the row.
    assert out[out["gw"] == 5].iloc[0]["p_play"] == pytest.approx(0.25)


def test_the_new_columns_do_not_survive_into_the_output():
    out = apply_availability(_pred(), _avail(absence_damp=0.75), curves=None)
    for col in ("absence_damp", "llm_verdict", "llm_confidence"):
        assert col not in out.columns


# --- F5: the shadow log and the gated serving damp -------------------------

def test_the_shadow_log_is_written_from_the_availability_pass(monkeypatch):
    banked = {}
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser",
                        lambda frame, season, gw: banked.update(
                            rows=len(frame), gw=gw) or len(frame))
    apply_availability(_pred(), _avail(llm_verdict="rotation_risk",
                                       llm_confidence=0.8), curves=None)
    assert banked["gw"] == 5


def test_the_verdict_changes_no_number_with_the_flag_off(monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    served = apply_availability(_pred(), _avail(llm_verdict="rotation_risk"),
                                curves=None)
    plain = apply_availability(_pred(), _avail(), curves=None)
    pd.testing.assert_frame_equal(served, plain)


def test_the_verdict_damps_the_first_gameweek_when_enabled(monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    out = apply_availability(_pred(), _avail(llm_verdict="rotation_risk"),
                             curves=None, llm_serving=True)
    by_gw = out.set_index("gw")
    assert by_gw.loc[5, "p_play"] == pytest.approx(0.9 * 0.8)
    assert by_gw.loc[6, "p_play"] == pytest.approx(0.9)


def test_a_log_that_fails_never_reaches_the_caller(monkeypatch):
    import gaffer.models.availability as av

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(av, "write_presser", boom)
    out = apply_availability(_pred(), _avail(llm_verdict="assess"),
                             curves=None)
    assert len(out) == 3
