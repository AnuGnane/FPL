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
