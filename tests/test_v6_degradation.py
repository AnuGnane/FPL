"""The v6 degradation rails.

Three things are pinned here; Task 3 adds the noise rail and Task 14 restates
the lot:

1. No penalty history, or no taker orders, leaves the component frame exactly
   as it was — column for column, not merely in the numbers EP happens to
   read.
2. The penalty term never escapes its clamp, whatever the inputs.
3. The protected source-text orderings in ``run_advise`` and
   ``predict_components`` still hold after everything v6 inserted.

If a later task legitimately changes one of these, that task's gate says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pandas as pd

from gaffer.set_pieces import (EP_CLAMP, PenPriors, add_pen_ep,
                               attack_multipliers)


def _comp() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "gw": 5, "position": "MID", "team_code": 3,
         "p_play": 0.95, "p60": 0.9, "e_goals": 0.42, "e_assists": 0.3},
        {"code": 2, "gw": 5, "position": "GKP", "team_code": 8,
         "p_play": 1.0, "p60": 1.0, "e_goals": 0.01, "e_assists": 0.01},
    ])


def _players(order=None) -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "name": "A", "position": "MID", "team_code": 3,
         "penalties_order": order},
        {"code": 2, "name": "B", "position": "GKP", "team_code": 8,
         "penalties_order": None},
    ])


# --- rail 1: no taker data == today's components ---------------------------

def test_no_priors_is_byte_identical_components():
    comp = _comp()
    out = add_pen_ep(comp, _players(order=1), None, {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)
    assert (out["ep_pen_taker"] == 0.0).all()


def test_no_taker_orders_is_byte_identical_components():
    comp = _comp()
    priors = PenPriors(share_hist={1: 0.0}, league_pens_pg=0.13,
                       team_games=760)
    out = add_pen_ep(comp, _players(order=None), priors, {})
    pd.testing.assert_frame_equal(out.drop(columns=["ep_pen_taker"]), comp)
    assert (out["ep_pen_taker"] == 0.0).all()


def test_a_team_model_with_no_attack_strengths_still_prices_the_term():
    """The multiplier degrades to flat, not to zero: a missing Dixon-Coles
    fit is no reason to unlearn who takes the penalties."""
    priors = PenPriors(share_hist={}, league_pens_pg=0.13, team_games=760)
    out = add_pen_ep(_comp(), _players(order=1), priors,
                     attack_multipliers(object()))
    assert out["ep_pen_taker"].iloc[0] > 0.0


# --- rail 2: the clamp holds ------------------------------------------------

def test_the_clamp_holds_against_absurd_inputs():
    priors = PenPriors(share_hist={1: 0.0}, league_pens_pg=99.0,
                       team_games=1)
    out = add_pen_ep(_comp(), _players(order=1), priors, {3: 99.0})
    assert out["ep_pen_taker"].max() <= EP_CLAMP[1]
    assert out["ep_pen_taker"].min() >= EP_CLAMP[0]


# --- rail 3: the protected orderings, restated -----------------------------

def test_run_advise_still_orders_every_protected_seam():
    import inspect

    from gaffer.advise import run_advise

    src = inspect.getsource(run_advise)
    league = src.index("fetch_rival_entries(")
    tilt = src.index("tilt_ep(")
    pool = src.index("pool = build_pool(")
    assert league < tilt < pool
    assert src.index("compute_strategy(") < pool
    assert "build_pool(players, pool_ep," in src

    comp = src.index("comp = predict_components(")
    blend = src.index("blend_attacking_odds(")
    assemble = src.index("ep_matrix(apply_calibration(assemble_ep(")
    assert comp < blend < assemble
    assert "except Exception" in src[blend - 600:blend + 600]

    assert 'ep_gw1 = ep_named[ep_named["gw"] == gw]' in src
    assert "pool_ep" not in src[src.index("ep_gw1 ="):]

    assert src.index("avail = news_availability(") < comp
    assert comp < src.index("write_shadow(comp, gw)") < blend
    assert src.index("pens = pen_priors(hist)") < comp


def test_predict_components_still_blends_before_merging_onto_players():
    import inspect

    from gaffer.advise import predict_components

    src = inspect.getsource(predict_components)
    assert src.index("blend_team_odds(") < src.index("comp.merge(tp")
    assert 'tp["p_cs_model"] = tp["p_cs"].values' in src
    assert 'tp["e_gc_model"] = tp["e_gc"].values' in src
    assert "odds_blend_weight()" in src
    for col in ["was_home", "kickoff_time", "pen_taker", "setpiece_taker"]:
        assert f'"{col}"' in src


# --- rail 4: no noise asset == the pre-v6 heuristic, value for value -------

def test_no_noise_asset_is_the_pre_v6_heuristic_exactly(monkeypatch):
    """``table=None`` means "load the shipped asset", so the absent asset is
    simulated at the loader rather than by the repository happening not to
    carry one yet — the rail is about a clone without the file, and it has to
    hold just as firmly once the file is committed."""
    import numpy as np

    import gaffer.optimize.scenarios as sc

    monkeypatch.setattr(sc, "scenario_noise", lambda: None)
    ep = {(1, 5): 4.0, (2, 5): 1.0}
    xmins = {(1, 5): 88.0, (2, 5): 20.0}
    out = sc.noise_ep(ep, xmins, np.random.default_rng(42))

    rng = np.random.default_rng(42)
    for key, value in ep.items():
        scale = (sc.NOISE_FLOOR_XMINS - xmins[key]) / sc.NOISE_DENOM
        want = max(0.0, value + value * scale * float(rng.standard_normal()))
        assert out[key] == want


def test_an_unreadable_noise_asset_degrades_to_the_heuristic(monkeypatch):
    import gaffer.optimize.scenarios as sc

    def boom():
        raise ValueError("not JSON")

    monkeypatch.setattr(sc, "load_scenario_noise", boom)
    sc.scenario_noise.cache_clear()
    try:
        assert sc.scenario_noise() is None
    finally:
        sc.scenario_noise.cache_clear()


def test_the_shipped_asset_is_optional_by_construction():
    """A clone with no scenario_noise.json must load, not raise."""
    from gaffer.assets import load_scenario_noise, scenario_noise_exists

    if not scenario_noise_exists():
        assert load_scenario_noise() is None
    else:
        payload = load_scenario_noise()
        assert set(payload) >= {"ep_edges", "xmins_edges", "sigma"}


def test_the_fitted_asset_is_present_and_well_shaped():
    """The orchestrator fitted and committed the real table mid-cycle. It has
    to be loadable, globally sane, and non-empty -- the rails above cover the
    clone that lacks it."""
    from gaffer.assets import load_scenario_noise

    payload = load_scenario_noise()
    assert isinstance(payload, dict)
    assert isinstance(payload["global"], float)
    assert 0.0 < payload["global"] < 10.0
    assert payload["sigma"]


def test_the_shipped_asset_serves_whatever_edge_list_it_carries():
    """XMINS_EDGES moved after the committed asset was fitted, and the asset
    is refitted on its own schedule. bin_index reads the edges *out of the
    payload*, so serving must not care whether the file has four edges or the
    five it was written with — a read side that assumed today's constant
    would silently index into the wrong cell of yesterday's table."""
    import numpy as np

    from gaffer.assets import load_scenario_noise
    from gaffer.optimize.scenarios import noise_ep, sigma_for

    payload = load_scenario_noise()
    for xmins in (0.0, 45.0, 70.0, 85.0, 90.0, 92.0):
        for ep in (0.1, 2.5, 5.0, 9.0):
            sigma = sigma_for(payload, ep, xmins)
            assert sigma is None or 0.0 < sigma < 10.0
    out = noise_ep({(1, 5): 4.0}, {(1, 5): 88.0}, np.random.default_rng(0),
                   table=payload)
    assert out[(1, 5)] >= 0.0


# --- rail 5: a cold clone serves every new endpoint without artifacts -------

def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.data import store
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_every_new_endpoint_answers_on_an_empty_disk(tmp_path, monkeypatch):
    """No reports/, no data/, no models/. The two artifact-backed endpoints
    say what to run; the two panel-backed ones say nothing at all. None of
    them 500s, and none of them is a blank page with a stack trace behind
    it."""
    client = _client(tmp_path, monkeypatch)

    chips = client.get("/api/chips")
    assert chips.status_code == 404
    assert "gaffer advise" in chips.json()["detail"]

    components = client.get("/api/components/5")
    assert components.status_code == 404
    assert "gaffer advise" in components.json()["detail"]

    diff = client.get("/api/advice/diff")
    assert diff.status_code == 200
    assert diff.json()["available"] is False

    news = client.get("/api/news/5")
    assert news.status_code == 200
    assert news.json() == {"gw": 5, "moved": 0, "rows": []}


def test_the_quality_page_still_answers_without_a_news_shadow_run(tmp_path,
                                                                 monkeypatch):
    import json

    client = _client(tmp_path, monkeypatch)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "evaluation.json").write_text(json.dumps(
        {"current": None, "benchmark": None, "decomposition": None}))
    assert client.get("/api/quality").json()["news_shadow"] is None


# --- rail 6: the artifacts are instrumentation, never a blocker ------------

def test_the_v6_writers_all_swallow_their_own_failures(tmp_path,
                                                       monkeypatch):
    """Every artifact v6 added is for a UI panel. An advise run that died of
    one would be a strictly worse trade than a hidden panel."""
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(art, "REPORTS", tmp_path / "nope" / "\0" / "bad")
    monkeypatch.setattr(art, "ADVICE_HISTORY",
                        tmp_path / "nope" / "\0" / "bad" / "advice_history")
    assert art.save_availability(pd.DataFrame([{"code": 1, "status": "a",
                                                "chance_of_playing": None}]),
                                 5) is None
    assert art.append_advice_history({"gw": 5}, 5) is None
