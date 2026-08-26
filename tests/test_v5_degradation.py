"""The v5 degradation rails.

Four things are pinned:

1. With every news source empty, ``availability_frame`` reproduces the
   official flags exactly and ``apply_availability`` on it is identical to
   the flags-only call — the same numbers, column for column. Two further
   ways of saying nothing are pinned to the same output: news that speaks
   only about suspended players, and a line-up that names everybody.
2. ``[news] enabled = false`` makes zero fetch calls. Asserted with a spy at
   the advise call site, not only inside the fetchers.
3. The asset chain degrades three deep: typed curve -> pooled curve -> the
   flat ``RECOVERY`` constant, with the terminal step byte-identical to v4.
4. The protected source-text orderings in ``run_advise`` and
   ``predict_components`` still hold after everything v5 inserted.

If a later task legitimately changes one of these, that task's *gate* says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.data.news.normalize import availability_frame
from gaffer.models.availability import RECOVERY, apply_availability


# --- rail 1: all sources empty == flags only -------------------------------

def _official() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "status": "a", "chance_of_playing": None},
        {"code": 2, "status": "d", "chance_of_playing": 50},
        {"code": 3, "status": "i", "chance_of_playing": 0},
        {"code": 4, "status": "s", "chance_of_playing": 0},
    ])


def _pred() -> pd.DataFrame:
    codes, gws = [1, 2, 3, 4], [5, 6, 7]
    return pd.DataFrame([{"code": c, "gw": g, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0} for c in codes for g in gws])


@pytest.mark.parametrize("news", [(None, None),
                                  (pd.DataFrame(), pd.DataFrame())])
def test_empty_news_reproduces_the_flags_only_availability_exactly(news):
    injuries, lineups = news
    official = _official()
    frame = availability_frame(official, injuries, lineups, gw=5,
                               events=None)
    with_news = apply_availability(_pred(), frame, curves=None)
    flags_only = apply_availability(_pred(), official, curves=None)
    assert list(with_news.columns) == list(flags_only.columns)
    pd.testing.assert_frame_equal(with_news, flags_only)


def test_an_all_empty_news_frame_carries_no_hints_or_types():
    frame = availability_frame(_official(), pd.DataFrame(), pd.DataFrame(),
                               gw=5, events=None)
    assert frame["p_start_hint"].isna().all()
    assert frame["injury_type"].isna().all()
    assert frame["expected_return_gw"].isna().all()


def test_news_only_about_banned_players_changes_nothing():
    """A full injuries frame every row of which names an s/u/n player. The
    official statuses are authoritative, so the whole batch is inert and the
    output has to be the flags-only one — column for column, not just in the
    numbers the optimizer happens to read."""
    injuries = pd.DataFrame([
        {"code": 4, "injury_type": "hamstring", "news_status": "out",
         "expected_return_date": pd.Timestamp("2026-09-20").date(),
         "source": "premierinjuries", "fetched_at": "2026-09-04T09:00:00Z"}])
    events = pd.DataFrame({"gw": [5, 6, 7, 8],
                           "deadline_time": ["2026-09-05T10:00Z",
                                             "2026-09-12T10:00Z",
                                             "2026-09-19T10:00Z",
                                             "2026-09-26T10:00Z"]})
    frame = availability_frame(_official(), injuries, None, gw=5,
                               events=events)
    with_news = apply_availability(_pred(), frame, curves=None)
    flags_only = apply_availability(_pred(), _official(), curves=None)
    pd.testing.assert_frame_equal(with_news, flags_only)


def test_a_line_up_that_names_everyone_is_inert_and_banks_nothing(tmp_path,
                                                                  monkeypatch):
    """Every hint at 1.0 — the site published a full XI for every club and
    contradicted nobody. Hints gate, they never raise, so the numbers must be
    the flags-only ones, and the shadow log must refuse a run of tied rows
    rather than diluting the cumulative table with them."""
    from gaffer.data import store as store_mod
    from gaffer.news_shadow import write_shadow

    lineups = pd.DataFrame([{"code": c, "p_start_hint": 1.0,
                             "source": "lineups", "fetched_at": "x"}
                            for c in [1, 2, 3, 4]])
    frame = availability_frame(_official(), None, lineups, gw=5, events=None)
    with_news = apply_availability(_pred(), frame, curves=None)
    flags_only = apply_availability(_pred(), _official(), curves=None)
    pd.testing.assert_frame_equal(with_news, flags_only)

    comp = with_news.copy()
    comp["p_play_flags"] = flags_only["p_play"].to_numpy()
    comp["e_min_flags"] = flags_only["e_min"].to_numpy()
    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    assert write_shadow(comp, gw=5) is None


# --- rail 2: enabled = false makes no calls --------------------------------

def _players() -> pd.DataFrame:
    return pd.DataFrame({"code": [1], "name": ["X"], "first_name": ["X"],
                         "second_name": ["Y"], "team_code": [3],
                         "status": ["a"], "chance_of_playing": [None]})


def _teams() -> pd.DataFrame:
    return pd.DataFrame({"code": [3], "name": ["Arsenal"],
                         "short_name": ["ARS"]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [5], "deadline_time": ["2026-09-05T10:00Z"]})


def test_news_disabled_makes_no_fetch_calls_at_all(monkeypatch):
    from gaffer import advise as advise_mod

    calls: list[str] = []
    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: calls.append("injuries"))
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: calls.append("lineups"))
    cfg = Config(entry_id=1, league_id=2, news_enabled=False)
    out = advise_mod.news_availability(cfg, _players(), _teams(), _events(),
                                       gw=5)
    assert calls == []
    assert list(out.columns) == ["code", "status", "chance_of_playing"]


def test_each_source_can_be_disabled_on_its_own(monkeypatch):
    from gaffer import advise as advise_mod

    calls: list[str] = []
    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: (calls.append("injuries"),
                                         pd.DataFrame())[1])
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: (calls.append("lineups"),
                                         pd.DataFrame())[1])
    cfg = Config(entry_id=1, league_id=2, news_lineups=False)
    advise_mod.news_availability(cfg, _players(), _teams(), _events(), gw=5)
    assert calls == ["injuries"]


def test_a_fetcher_that_raises_never_reaches_the_caller(monkeypatch):
    """Advice never blocks on news, and the printed line is the whole of the
    user-visible consequence."""
    from gaffer import advise as advise_mod

    def boom(*a, **k):
        raise RuntimeError("premierinjuries redesigned overnight")

    monkeypatch.setattr(advise_mod, "fetch_injuries", boom)
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: pd.DataFrame())
    cfg = Config(entry_id=1, league_id=2)
    out = advise_mod.news_availability(cfg, _players(), _teams(), _events(),
                                       gw=5)
    assert list(out.columns) == ["code", "status", "chance_of_playing"]


def test_an_enabled_source_that_returns_nothing_is_named(monkeypatch, capsys):
    """A source that comes back empty is as degraded as one that raised, and
    silence about it reads as "the league has no injuries this week"."""
    from gaffer import advise as advise_mod

    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: pd.DataFrame())
    cfg = Config(entry_id=1, league_id=2)
    advise_mod.news_availability(cfg, _players(), _teams(), _events(), gw=5)
    printed = capsys.readouterr().out
    assert "premierinjuries returned nothing" in printed
    assert "line-ups returned nothing" in printed


def test_a_disabled_source_is_not_reported_as_empty(monkeypatch, capsys):
    """Off is not degraded. Only a source we asked and got nothing from."""
    from gaffer import advise as advise_mod

    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: pd.DataFrame())
    cfg = Config(entry_id=1, league_id=2, news_lineups=False)
    advise_mod.news_availability(cfg, _players(), _teams(), _events(), gw=5)
    printed = capsys.readouterr().out
    assert "premierinjuries returned nothing" in printed
    assert "line-ups returned nothing" not in printed


# --- rail 3: the three-deep asset fallback ---------------------------------

_TYPED = {"curves": {"knee": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.0, 1.0, 1.0]},
          "pooled": [0.0, 0.5, 0.7, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0]}


def _flagged(injury_type=None) -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "status": "i", "chance_of_playing": 0,
                          "injury_type": injury_type,
                          "expected_return_gw": None, "p_start_hint": None,
                          "source": None, "fetched_at": None}])


def _one(gws=(5, 6, 7)) -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "gw": g, "p_play": 1.0, "p60": 1.0,
                          "e_min": 90.0} for g in gws])


def test_the_typed_curve_is_used_when_the_asset_has_one():
    # approx, not ==: the rule is 1 - (1 - f) * (1 - p_back), and
    # 1 - (1 - 0.2) is 0.19999999999999996 in binary floating point.
    out = apply_availability(_one(), _flagged("knee"), curves=_TYPED)
    assert out["p_play"].tolist() == pytest.approx([0.0, 0.2, 0.4])


def test_the_pooled_curve_answers_an_unseen_type():
    out = apply_availability(_one(), _flagged("hangnail"), curves=_TYPED)
    assert out["p_play"].tolist() == pytest.approx([0.0, 0.5, 0.7])


def test_no_asset_at_all_is_the_v4_geometric_exactly():
    """The terminal rail. This is the arithmetic v4 shipped, written out."""
    out = apply_availability(_one(), _flagged("knee"), curves=None)
    expected = [1 - RECOVERY ** h for h in range(3)]
    for got, want in zip(out["p_play"], expected):
        assert abs(got - want) < 1e-12


def test_an_asset_with_no_pooled_curve_still_falls_through_to_the_constant():
    out = apply_availability(_one(), _flagged("hangnail"),
                             curves={"curves": {}, "pooled": []})
    expected = [1 - RECOVERY ** h for h in range(3)]
    for got, want in zip(out["p_play"], expected):
        assert abs(got - want) < 1e-12


# --- rail 4: the protected orderings, restated -----------------------------

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

    # v5's two insertions, both above the pool and neither naming it.
    assert src.index("avail = news_availability(") < comp
    assert comp < src.index("write_shadow(comp, gw)") < blend


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


def test_the_minutes_module_still_re_exports_the_availability_seam():
    """advise.py imports apply_availability from gaffer.models.minutes, and
    v5 moved the implementation. The import must not have moved with it."""
    import inspect

    from gaffer import advise

    src = inspect.getsource(advise)
    assert "from gaffer.models.minutes import apply_availability" in src
