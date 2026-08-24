import pandas as pd

from gaffer.tracking import compute_health


def test_compute_health_joins_predictions_with_actuals():
    preds = pd.DataFrame({"code": [1, 2, 3], "gw": [2, 2, 2],
                          "ep": [6.0, 4.0, 2.0]})
    actuals = pd.DataFrame({"code": [1, 2, 3], "gw": [2, 2, 2],
                            "total_points": [8, 3, 2], "minutes": [90, 90, 60]})
    h = compute_health(preds, actuals, captain_code=1, advice_pts=50,
                       actual_pts=45)
    assert h["captain_actual"] == 8
    assert h["mae_starters"] == round((2 + 1 + 0) / 3, 2)
    assert h["advice_pts"] == 50 and h["actual_pts"] == 45


def test_update_health_writes_summary_when_actuals_present(tmp_path, monkeypatch):
    """update_health only produces a summary once the finished GW's rows are in
    the live store — i.e. after refresh_live has run for that gameweek."""
    from gaffer.data import store
    from gaffer import tracking

    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.chdir(tmp_path)

    preds = pd.DataFrame({"code": [1, 2], "gw": [3, 3], "ep": [6.0, 4.0]})
    store.save(preds, "live/predictions/gw3.parquet")

    live = pd.DataFrame({"code": [1, 2], "gw": [3, 3],
                         "total_points": [8, 3], "minutes": [90, 90]})
    store.save(live, "live/player_gw.parquet")

    health = tracking.update_health(3)
    assert health is not None
    assert health["gw"] == 3
    assert health["mae_starters"] == round((2 + 1) / 2, 2)


def test_update_health_returns_none_before_live_refresh(tmp_path, monkeypatch):
    from gaffer.data import store
    from gaffer import tracking

    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.chdir(tmp_path)
    store.save(pd.DataFrame({"code": [1], "gw": [3], "ep": [6.0]}),
               "live/predictions/gw3.parquet")

    assert tracking.update_health(3) is None
