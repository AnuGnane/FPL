import pandas as pd
from gaffer.backtest import score_gw


def _actuals():
    """Legal XI: code 1 GKP, 2-6 DEF, 7-10 MID, 11 FWD; bench 12-15 MID."""
    spec = {1: (10, 90, "GKP"),                      # captain, hauled
            2: (2, 90, "DEF"), 3: (2, 90, "DEF"), 4: (2, 90, "DEF"),
            5: (0, 0, "DEF"),                        # starter, didn't play
            6: (2, 90, "DEF"),
            7: (2, 90, "MID"), 8: (2, 90, "MID"),
            9: (2, 90, "MID"), 10: (2, 90, "MID"),
            11: (2, 90, "FWD"),
            12: (6, 90, "MID"),                      # bench, played -> subs in
            13: (2, 90, "MID"), 14: (2, 90, "MID"), 15: (2, 90, "MID")}
    return pd.DataFrame([{"code": c, "total_points": p, "minutes": m,
                          "position": pos} for c, (p, m, pos) in spec.items()])


def test_score_gw_captain_doubles_and_autosub():
    xi = list(range(1, 12))       # includes code 5 (0 mins)
    bench = [12, 13, 14, 15]
    pts = score_gw(_actuals(), xi=xi, bench=bench, captain=1, vice=2, hits=1)
    # XI without 5: 10(GK) + 4*2(DEF) + 4*2(MID) + 2(FWD) = 28
    # sub 12 in for 5 (formation 1-4-5-1, legal): +6 = 34
    # captain 1 played -> +10 = 44 ; one hit -> -4 => 40
    assert pts == 40


def test_score_gw_vice_takes_over_when_captain_blanks():
    actuals = _actuals()
    actuals.loc[actuals.code == 1, ["total_points", "minutes"]] = [0, 0]
    pts = score_gw(actuals, xi=list(range(1, 12)), bench=[12, 13, 14, 15],
                   captain=1, vice=2, hits=0)
    # GK blanked; no GK on the bench so no legal sub for him. Code 5 still
    # subs out for 12: 0 + 4*2 + 8 + 2 + 6 = 24
    # captain 0 mins -> vice code 2 doubles: +2 => 26
    assert pts == 26
