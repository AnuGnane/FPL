import pandas as pd
from gaffer.prices import price_alerts

PLAYERS = pd.DataFrame([
    {"code": 1, "name": "Riser", "price_change_percent": 94.0,
     "price_change_calibrating": False},
    {"code": 2, "name": "Faller", "price_change_percent": -91.0,
     "price_change_calibrating": False},
    {"code": 3, "name": "Stable", "price_change_percent": 10.0,
     "price_change_calibrating": False},
    {"code": 4, "name": "NewSigning", "price_change_percent": 99.0,
     "price_change_calibrating": True},
])


def test_price_alerts_flags_imminent_and_relevant():
    alerts = price_alerts(PLAYERS, watch_codes=[1, 2, 3, 4], threshold=90.0)
    flagged = dict(zip(alerts["code"], alerts["direction"]))
    assert flagged[1] == "rise" and flagged[2] == "drop"
    assert 3 not in flagged
    assert alerts[alerts.code == 4]["calibrating"].iloc[0]  # shown but labeled


def test_nan_never_alerts_and_empty_watchlist_returns_empty_frame():
    with_nan = pd.concat([
        PLAYERS,
        pd.DataFrame([{"code": 5, "name": "NoData",
                       "price_change_percent": float("nan"),
                       "price_change_calibrating": False}]),
    ], ignore_index=True)

    for threshold in (0.0, 90.0, 100.0):
        alerts = price_alerts(with_nan, watch_codes=[1, 2, 3, 4, 5],
                              threshold=threshold)
        assert 5 not in set(alerts["code"])

    empty = price_alerts(with_nan, watch_codes=[], threshold=90.0)
    assert empty.empty
    assert list(empty.columns) == ["code", "name", "price_change_percent",
                                   "direction", "calibrating"]
