import pandas as pd

from gaffer.features.bps import adjust_bps


def _rows(spec):
    """spec: list of (season_idx, bps, cbi)."""
    return pd.DataFrame([{"season_idx": s, "bps": b, "cbi": c,
                          "minutes": 90}
                         for s, b, c in spec])


def test_adjust_bps_applies_the_cbi_rebalance_to_old_seasons():
    # cbi 6 earned 3 BPS under the old per-two rule and earns 2 under the
    # new per-three rule: floor(6/3) - floor(6/2) = -1.
    out = adjust_bps(_rows([(0, 30.0, 6.0)]), current_idx=3)
    assert list(out) == [29.0]


def test_adjust_bps_delta_is_never_positive():
    frame = _rows([(0, 30.0, float(c)) for c in range(0, 25)])
    delta = adjust_bps(frame, current_idx=3) - frame["bps"]
    assert (delta <= 0).all()


def test_adjust_bps_leaves_current_season_rows_untouched():
    # Current-season rows are already scored under the new rules.
    out = adjust_bps(_rows([(3, 30.0, 12.0)]), current_idx=3)
    assert list(out) == [30.0]


def test_adjust_bps_treats_a_missing_cbi_count_as_no_adjustment():
    # cbi only exists from 2025-26 onwards; older rows cannot be corrected.
    out = adjust_bps(_rows([(0, 30.0, float("nan"))]), current_idx=3)
    assert list(out) == [30.0]


def test_adjust_bps_keeps_a_missing_bps_missing():
    out = adjust_bps(_rows([(0, float("nan"), 6.0)]), current_idx=3)
    assert out.isna().all()
