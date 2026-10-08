"""v20c's clip on the Dixon-Coles means (v20 spec §2 v20c, ruling 6), shipped
off: ``MU_BOUNDS = None`` must leave ``predict`` byte-identical, and a set
bound must clip ``lam`` and ``mu`` before the pmf and print its lever line.

Kept out of ``test_dixon_coles.py`` because that file is marked slow; the toy
fit here is four clubs and a few dozen matches, so it stays in the inner loop.
"""

import math

import numpy as np
import pandas as pd
import pytest

import gaffer.models.dixon_coles as dc
from gaffer.models.dixon_coles import DixonColesModel, fixture_outcomes
from gaffer.models.team import build_team_gw

SPEC_BOUNDS = (0.2, 3.5)


def _toy_model() -> DixonColesModel:
    rng = np.random.default_rng(11)
    attack, defence = [0.3, 0.1, -0.1, -0.3], [-0.2, 0.0, 0.1, 0.2]
    rows, day = [], 0
    for _ in range(3):
        for i in range(4):
            for j in range(4):
                if i == j:
                    continue
                lam = math.exp(attack[i] + defence[j] + 0.25)
                mu = math.exp(attack[j] + defence[i])
                rows.append({
                    "season_idx": 0, "gw": 1 + day // 6,
                    "kickoff_time": (pd.Timestamp("2020-01-01", tz="UTC")
                                     + pd.Timedelta(days=day)).isoformat(),
                    "home_code": i, "away_code": j,
                    "home_goals": int(rng.poisson(lam)),
                    "away_goals": int(rng.poisson(mu))})
                day += 1
    return DixonColesModel(xi=0.0).fit(build_team_gw(pd.DataFrame(rows)))


@pytest.fixture(scope="module")
def toy():
    return _toy_model()


def _rows():
    pairs = [(0, 1, 1.0), (1, 0, 0.0), (2, 3, 1.0), (3, 2, 0.0)]
    return pd.DataFrame([{"code": c, "opp_code": o, "home": h,
                          "season_idx": 1, "gw": 5} for c, o, h in pairs])


def _means(model, code, opp, is_home):
    att, dfn = model._params(code)
    opp_att, opp_dfn = model._params(opp)
    lam = math.exp(att + opp_dfn + model.gamma_ * is_home)
    mu = math.exp(opp_att + dfn + model.gamma_ * (1.0 - is_home))
    return lam, mu


def test_the_clip_ships_off():
    assert dc.MU_BOUNDS is None


def test_off_is_the_unclipped_pmf_and_prints_nothing(toy, capsys):
    out = toy.predict(_rows())
    assert capsys.readouterr().out == ""
    for row, (c, o, h) in zip(out.itertuples(), [(0, 1, 1.0), (1, 0, 0.0),
                                                 (2, 3, 1.0), (3, 2, 0.0)]):
        stats = fixture_outcomes(*_means(toy, c, o, h), toy.rho_, toy.cap)
        assert row.p_cs == stats["p_cs_home"]
        assert row.e_gc == stats["e_gc_home"]


def test_a_band_the_toy_never_leaves_changes_nothing(toy, monkeypatch, capsys):
    off = toy.predict(_rows())
    monkeypatch.setattr(dc, "MU_BOUNDS", SPEC_BOUNDS)
    on = toy.predict(_rows())
    pd.testing.assert_frame_equal(off, on)
    assert capsys.readouterr().out.strip() == "DC_CLIP n=0 of 4"


def test_an_absurd_attack_is_clipped_on_both_means_off_one_pmf(
        monkeypatch, capsys):
    model = _toy_model()
    model.attack_[0] = 2.5  # lam for club 0 at home well above 3.5
    rows = _rows()
    off = model.predict(rows)
    lam, mu = _means(model, 0, 1, 1.0)
    assert lam > SPEC_BOUNDS[1]

    monkeypatch.setattr(dc, "MU_BOUNDS", SPEC_BOUNDS)
    on = model.predict(rows)
    capsys.readouterr()
    clipped = fixture_outcomes(SPEC_BOUNDS[1], min(max(mu, 0.2), 3.5),
                               model.rho_, model.cap)
    # Club 1 concedes club 0's clipped lam: its clean sheet rises and its
    # goals-conceded mean falls to the ceiling's, both from the same pmf.
    assert on.loc[1, "p_cs"] == pytest.approx(clipped["p_cs_away"], abs=1e-12)
    assert on.loc[1, "e_gc"] == pytest.approx(clipped["e_gc_away"], abs=1e-12)
    assert on.loc[1, "p_cs"] > off.loc[1, "p_cs"]
    assert on.loc[1, "e_gc"] < off.loc[1, "e_gc"]
    # The fixtures without club 0 are untouched.
    pd.testing.assert_frame_equal(on.iloc[2:], off.iloc[2:])


def test_the_lever_line_counts_the_fixtures_where_the_clip_bit(
        monkeypatch, capsys):
    model = _toy_model()
    model.attack_[0] = 2.5
    monkeypatch.setattr(dc, "MU_BOUNDS", SPEC_BOUNDS)
    model.predict(_rows())
    assert capsys.readouterr().out.strip() == "DC_CLIP n=2 of 4"


def test_a_floor_lifts_a_mean_below_it(monkeypatch, capsys):
    model = _toy_model()
    model.attack_[3] = -2.5  # club 3 scores almost never: its lam floors
    lam, _ = _means(model, 3, 2, 0.0)
    assert lam < SPEC_BOUNDS[0]
    off = model.predict(_rows())
    monkeypatch.setattr(dc, "MU_BOUNDS", SPEC_BOUNDS)
    on = model.predict(_rows())
    capsys.readouterr()
    # Club 2 keeps a clean sheet against club 3 a little less often once
    # club 3's mean is floored at 0.2.
    assert on.loc[2, "p_cs"] < off.loc[2, "p_cs"]
    assert on.loc[2, "e_gc"] > off.loc[2, "e_gc"]
