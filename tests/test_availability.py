"""Availability v2: the GW1 line-up gate and the injury-curve horizon decay.

The three-deep fallback (typed curve -> pooled curve -> flat RECOVERY) is the
degradation contract; each step is pinned here and re-pinned in
tests/test_v5_degradation.py."""

from __future__ import annotations

import json

import pandas as pd

from gaffer.models.availability import RECOVERY, apply_availability, return_prob


_CURVES = {
    "version": 1,
    "generated_at": "2026-08-26T00:00:00+00:00",
    "horizon": 8,
    "curves": {"hamstring": [0.0, 0.1, 0.3, 0.6, 0.8, 0.9, 0.95, 1.0, 1.0],
               "knock": [0.0, 0.7, 0.95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]},
    "pooled": [0.0, 0.4, 0.65, 0.8, 0.9, 0.95, 1.0, 1.0, 1.0],
}


def test_return_prob_prefers_the_typed_curve():
    assert return_prob(_CURVES, "hamstring", 3) == 0.6
    assert return_prob(_CURVES, "knock", 1) == 0.7


def test_return_prob_falls_back_to_pooled_for_an_unseen_type():
    assert return_prob(_CURVES, "unknown", 2) == 0.65
    assert return_prob(_CURVES, None, 2) == 0.65


def test_return_prob_is_none_without_an_asset_at_all():
    """The terminal fallback: no asset means the caller uses RECOVERY, which
    is today's behaviour exactly."""
    assert return_prob(None, "hamstring", 3) is None
    assert return_prob({}, "hamstring", 3) is None


def test_return_prob_clamps_past_the_end_of_the_curve():
    assert return_prob(_CURVES, "knock", 99) == 1.0
    assert return_prob(_CURVES, "knock", 0) == 0.0


def _pred(gws, p_play=0.9, p60=0.8, e_min=80.0) -> pd.DataFrame:
    return pd.DataFrame({"code": [1] * len(gws), "gw": list(gws),
                         "p_play": [p_play] * len(gws),
                         "p60": [p60] * len(gws),
                         "e_min": [e_min] * len(gws)})


def _avail(**kw) -> pd.DataFrame:
    row = {"code": 1, "status": "i", "chance_of_playing": 0,
           "injury_type": None, "expected_return_gw": None,
           "p_start_hint": None, "source": None, "fetched_at": None}
    row.update(kw)
    return pd.DataFrame([row])


def test_a_typed_injury_decays_on_its_own_curve_not_the_flat_constant():
    out = apply_availability(_pred([5, 6, 7]),
                             _avail(injury_type="hamstring"),
                             curves=_CURVES).set_index("gw")
    # 1 - (1 - 0) * (1 - P(returned by h)) = P(returned by h).
    assert abs(out.loc[5, "p_play"] - 0.9 * 0.0) < 1e-9
    assert abs(out.loc[6, "p_play"] - 0.9 * 0.1) < 1e-9
    assert abs(out.loc[7, "p_play"] - 0.9 * 0.3) < 1e-9


def test_an_unseen_injury_type_decays_on_the_pooled_curve():
    out = apply_availability(_pred([5, 6, 7]),
                             _avail(injury_type="hangnail"),
                             curves=_CURVES).set_index("gw")
    assert abs(out.loc[6, "p_play"] - 0.9 * 0.4) < 1e-9


def test_no_injury_type_at_all_falls_back_to_the_flat_geometric():
    """Unflagged knocks and ending suspensions have no type. Their decay is
    the pre-v5 constant, unchanged."""
    out = apply_availability(_pred([5, 6, 7]), _avail(status="s"),
                             curves=_CURVES).set_index("gw")
    for h, gw in enumerate([5, 6, 7]):
        assert abs(out.loc[gw, "p_play"] - 0.9 * (1 - RECOVERY ** h)) < 1e-9


def test_without_the_asset_every_row_uses_the_flat_geometric():
    """The terminal rail: behaviour with no curves is exactly today's."""
    out = apply_availability(_pred([5, 6, 7]),
                             _avail(injury_type="hamstring"),
                             curves=None).set_index("gw")
    for h, gw in enumerate([5, 6, 7]):
        assert abs(out.loc[gw, "p_play"] - 0.9 * (1 - RECOVERY ** h)) < 1e-9


def test_a_bench_hint_gates_the_first_gameweek_only():
    out = apply_availability(_pred([5, 6]),
                             _avail(status="a", chance_of_playing=None,
                                    p_start_hint=0.25),
                             curves=_CURVES).set_index("gw")
    assert abs(out.loc[5, "p_play"] - 0.25) < 1e-9
    assert abs(out.loc[6, "p_play"] - 0.9) < 1e-9      # untouched beyond GW1


def test_a_double_gameweek_hint_gates_one_fixture_not_both():
    """A predicted XI names one team sheet. In a double gameweek both rows
    carry the same gw, and gating both said the site had predicted the
    Wednesday tie as well — it had not."""
    out = apply_availability(_pred([5, 5, 6]),
                             _avail(status="a", chance_of_playing=None,
                                    p_start_hint=0.25),
                             curves=_CURVES).reset_index(drop=True)
    assert abs(out.loc[0, "p_play"] - 0.25) < 1e-9
    assert abs(out.loc[1, "p_play"] - 0.9) < 1e-9
    assert abs(out.loc[2, "p_play"] - 0.9) < 1e-9


def test_a_starter_hint_never_raises_the_model():
    """Line-ups gate, they do not inflate. A 1.0 hint on a player the model
    prices at 0.4 leaves him at 0.4."""
    out = apply_availability(_pred([5], p_play=0.4),
                             _avail(status="a", chance_of_playing=None,
                                    p_start_hint=1.0),
                             curves=_CURVES)
    assert abs(out["p_play"].iloc[0] - 0.4) < 1e-9


def test_the_hint_scales_p60_and_e_min_by_the_same_factor():
    """p60 and e_min must not survive a gate that halved p_play, or the
    appearance points and the xMins nailedness score contradict each other."""
    out = apply_availability(_pred([5]),
                             _avail(status="a", chance_of_playing=None,
                                    p_start_hint=0.45),
                             curves=_CURVES)
    ratio = 0.45 / 0.9
    assert abs(out["p60"].iloc[0] - 0.8 * ratio) < 1e-9
    assert abs(out["e_min"].iloc[0] - 80.0 * ratio) < 1e-9


def test_a_hint_and_a_flag_compose_to_the_more_pessimistic_of_the_two():
    out = apply_availability(_pred([5]),
                             _avail(status="d", chance_of_playing=50,
                                    p_start_hint=0.25),
                             curves=_CURVES)
    # The flag alone gives 0.45; the hint caps p_play at 0.25.
    assert abs(out["p_play"].iloc[0] - 0.25) < 1e-9


def test_a_three_column_bootstrap_frame_still_works():
    """The pre-v5 caller shape. web/routers and every old test pass
    [code, status, chance_of_playing] with none of the news columns."""
    avail = pd.DataFrame({"code": [1], "status": ["d"],
                          "chance_of_playing": [50]})
    out = apply_availability(_pred([5]), avail)
    assert abs(out["p_play"].iloc[0] - 0.45) < 1e-9
    assert "injury_type" not in out.columns


def test_the_news_columns_are_dropped_from_the_output():
    """Downstream stitches positionally off p_play/p60/e_min; a stray
    news column on the component frame would ride into the parquet."""
    out = apply_availability(_pred([5]), _avail(injury_type="knock"),
                             curves=_CURVES)
    assert set(out.columns) == {"code", "gw", "p_play", "p60", "e_min"}


def test_minutes_still_re_exports_the_seam():
    """advise.py:53 imports from gaffer.models.minutes and this task does not
    change that import."""
    from gaffer.models import minutes

    assert minutes.apply_availability is apply_availability
    assert minutes.RECOVERY == RECOVERY


def test_load_injury_curves_is_none_when_the_asset_is_absent(monkeypatch):
    from gaffer import assets

    monkeypatch.setattr(assets, "injury_curves_exist", lambda: False)
    assert assets.load_injury_curves() is None
