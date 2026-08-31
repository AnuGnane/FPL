"""The v8a degradation rails.

Six things are pinned:

1. The tenure asset absent -> club-season windows, the same columns, the same
   frame shape. A clone without ``data/manager_tenures.toml`` predicts.
2. The classifier disabled -> zero subprocess calls, asserted with a spy at
   the ``fetch_injuries`` call site rather than inside the classifier.
3. A classifier that raises, times out or returns nonsense -> availability
   byte-identical to the classifier-absent frame.
4. ``lineup_absence`` off -> the line-up frame and the availability output are
   the pre-v8a ones.
5. Every switch is independent: absence off does not disable the classifier,
   the classifier off does not disable the hint ceiling.
6. The protected source-text orderings still hold, copied forward from v5.

If a later task legitimately changes one of these, that task's *gate* says so
and the pin here is updated deliberately — never quietly.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.data.news.normalize import availability_frame
from gaffer.features.engineer import (ROTATION_PRIOR_FEATURES,
                                      add_rotation_priors,
                                      latest_rotation_priors)
from gaffer.models.availability import apply_availability


# --- rail 1: no tenure asset ----------------------------------------------

def _hist() -> pd.DataFrame:
    rows = []
    for i in range(6):
        when = pd.Timestamp("2023-08-05", tz="UTC") + pd.Timedelta(days=7 * i)
        for code in (1, 2):
            rows.append({"code": code, "team_code": 3, "season_idx": 1,
                         "gw": i + 1, "kickoff_time": when.isoformat(),
                         "starts": 1.0, "minutes": 90.0})
    return pd.DataFrame(rows)


def test_without_the_asset_every_prior_column_still_exists():
    out = add_rotation_priors(_hist(), None)
    assert list(out.columns)[-4:] == ROTATION_PRIOR_FEATURES
    assert out["manager_tenure_matches"].notna().all()


def test_without_the_asset_the_frame_shape_is_unchanged():
    with_asset = add_rotation_priors(_hist(), pd.DataFrame(
        {"team_code": [3], "club": ["X"], "manager": ["M"],
         "start_date": pd.to_datetime(["2023-01-01"], utc=True),
         "end_date": pd.to_datetime([None], utc=True)}))
    without = add_rotation_priors(_hist(), None)
    assert with_asset.shape == without.shape
    assert list(with_asset.columns) == list(without.columns)


def test_a_corrupt_asset_reaches_the_builder_as_none(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod
    from gaffer.data.managers import (MANAGER_TENURES_PATH,
                                      load_manager_tenures)

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    (tmp_path / MANAGER_TENURES_PATH).write_text("not toml [[", "utf-8")
    assert load_manager_tenures() is None
    assert not latest_rotation_priors(_hist(), None).empty


# --- rail 2: the classifier makes no calls when it is off ------------------

def _players() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "name": "A", "first_name": "A",
                          "second_name": "One", "team_code": 3,
                          "starts": 5, "minutes": 450, "news": "A knock",
                          "status": "a", "chance_of_playing": None}])


def _teams() -> pd.DataFrame:
    return pd.DataFrame([{"code": 3, "name": "Arsenal",
                          "short_name": "ARS"}])


# Real markup, not a stub. A rail that feeds the fetcher an empty page
# proves only that an empty page returns early — the flag branch it claims
# to pin sits well past that return, and every one of these tests has to
# reach it before its assertion means anything.
FIXTURES = Path(__file__).parent / "data" / "news"


def _serving(text: str) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=text)
    return httpx.Client(transport=httpx.MockTransport(handle))


def _injury_players() -> pd.DataFrame:
    """The two names the committed injury fixture lists, both carrying free
    text — so ``news_texts`` has something to hand the classifier."""
    return pd.DataFrame([
        {"code": 100, "name": "Saka", "first_name": "Bukayo",
         "second_name": "Saka", "team_code": 3, "starts": 10, "minutes": 900,
         "news": "Knock, assessed daily", "status": "d",
         "chance_of_playing": 75},
        {"code": 101, "name": "Gabriel", "first_name": "Gabriel",
         "second_name": "Magalhaes", "team_code": 3, "starts": 9,
         "minutes": 810, "news": "Out with a thigh problem", "status": "i",
         "chance_of_playing": 0}])


@pytest.mark.parametrize("flags, launched", [((False, False), False),
                                             ((True, False), True),
                                             ((False, True), True)])
def test_the_classifier_is_only_launched_when_a_flag_asks_for_it(
        flags, launched, tmp_path, monkeypatch):
    """Both flags off makes zero calls — and the positive arms are what say
    the page really did reach the branch rather than returning early."""
    from gaffer.data.news import premierinjuries as pi

    calls: list[int] = []
    monkeypatch.setattr(pi, "classify_news",
                        lambda *a, **k: calls.append(1) or pd.DataFrame())
    classifier, shadow = flags
    out = pi.fetch_injuries(
        _injury_players(), _teams(), cache_dir=tmp_path,
        client=_serving((FIXTURES / "premierinjuries.html").read_text()),
        classifier=classifier, shadow=shadow, min_coverage=0.0)
    assert not out.empty, "the rail must reach the flag branch"
    assert bool(calls) is launched
    assert out["llm_verdict"].isna().all()


def test_no_test_in_this_repo_shells_out_to_the_real_cli():
    """G4 is the orchestrator's, on their machine. A suite that invoked the
    real binary would be a suite that fails on a machine nobody logged in.

    The literal string does appear in the suite — in prose, and in the pin on
    the ``[news] llm_command`` default, neither of which launches anything —
    so the rail is on the *use*: no test line hands the real binary to the
    classifier or to a subprocess. Every classifier test drives a fake
    ``cmd``.
    """
    from pathlib import Path

    for path in Path("tests").glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "claude" not in line and "news_llm_command" not in line:
                continue
            for forbidden in ("cmd=", "classify_news(", "subprocess",
                              "shlex", "Popen"):
                assert forbidden not in line, (path, line)


# --- rail 3: a broken classifier changes nothing ---------------------------

def _official() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "status": "a",
                          "chance_of_playing": None}])


def _pred() -> pd.DataFrame:
    return pd.DataFrame([{"code": 1, "gw": g, "p_play": 0.9, "p60": 0.8,
                          "e_min": 80.0} for g in (5, 6, 7)])


@pytest.mark.parametrize("verdicts", [None, pd.DataFrame()])
def test_a_classifier_that_answered_nothing_is_the_classifier_absent_path(
        verdicts, monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    injuries = pd.DataFrame([{"code": 1, "injury_type": None,
                              "news_status": None,
                              "expected_return_date": None,
                              "news_chance_pct": None, "further_detail": "",
                              "llm_verdict": None, "llm_confidence": None,
                              "source": "premierinjuries",
                              "fetched_at": "2026-09-04T09:00:00Z"}])
    frame = availability_frame(_official(), injuries, None, gw=5, events=None)
    with_dead = apply_availability(_pred(), frame, curves=None)
    without = apply_availability(_pred(), _official(), curves=None)
    for col in ("p_play", "p60", "e_min"):
        pd.testing.assert_series_equal(with_dead[col], without[col])


def test_a_verdict_present_but_unserved_is_arithmetically_inert(monkeypatch):
    import gaffer.models.availability as av

    monkeypatch.setattr(av, "write_presser", lambda *a, **k: 0)
    avail = _official().assign(llm_verdict="rotation_risk",
                               llm_confidence=0.9)
    served = apply_availability(_pred(), avail, curves=None,
                                llm_serving=False)
    plain = apply_availability(_pred(), _official(), curves=None)
    pd.testing.assert_frame_equal(served, plain)


# --- rail 4: lineup_absence off is v7 ---------------------------------------

def _xi_squad() -> pd.DataFrame:
    """Twelve equally-nailed-on Arsenal regulars, eleven of whom will be
    printed — so the twelfth is exactly the row the absence rule adds."""
    return pd.DataFrame([
        {"code": 200 + i, "name": f"P{i}", "first_name": "P",
         "second_name": f"Player{i}", "team_code": 3, "starts": 10,
         "minutes": 900, "news": "", "status": "a",
         "chance_of_playing": None} for i in range(12)])


def _xi_page() -> str:
    items = "".join(
        f'<li title="Player{i} (P)">'
        f'<img src="https://resources.premierleague.com/premierleague25'
        f'/photos/players/110x140/{200 + i}.png"></li>' for i in range(11))
    return f'<h2>Arsenal</h2><ul class="row-1">{items}</ul>'


def test_absence_off_leaves_the_line_up_frame_at_its_pre_v8a_content(tmp_path):
    """Fed a page the absence rule *would* act on: eleven printed starters
    and a twelfth regular left out. With the flag off the frame is the
    eleven hint rows and nothing else, and ``absence_damp`` is all-null —
    which is only a rail because the flag-on run below differs from it."""
    from gaffer.data.news import lineups as ln

    squad, page = _xi_squad(), _xi_page()
    off = ln.fetch_lineups(squad, _teams(), cache_dir=tmp_path,
                           client=_serving(page), absence=False)
    on = ln.fetch_lineups(squad, _teams(), cache_dir=tmp_path,
                          client=_serving(page), absence=True,
                          absence_damp=0.75)

    assert list(off.columns) == ln.LINEUP_COLS
    assert off["absence_damp"].isna().all()
    assert list(off["code"]) == list(range(200, 211))
    # The difference is the whole of F4, and it has to be non-empty or the
    # "off is pre-v8a" claim above is a claim about nothing.
    assert list(on["code"]) == list(range(200, 212))
    assert on.set_index("code").loc[211, "absence_damp"] == 0.75
    pd.testing.assert_frame_equal(
        off, on[on["absence_damp"].isna()].reset_index(drop=True))


def test_an_availability_frame_with_no_damp_is_the_v7_arithmetic():
    frame = availability_frame(_official(), None, None, gw=5, events=None)
    with_cols = apply_availability(_pred(), frame, curves=None)
    flags_only = apply_availability(_pred(), _official(), curves=None)
    assert list(with_cols.columns) == list(flags_only.columns)
    pd.testing.assert_frame_equal(with_cols, flags_only)


# --- rail 5: the switches are independent ---------------------------------

def test_absence_off_does_not_turn_the_hint_ceiling_off():
    avail = _official().assign(p_start_hint=0.25, absence_damp=None)
    out = apply_availability(_pred(), avail, curves=None)
    assert out.set_index("gw").loc[5, "p_play"] == pytest.approx(0.25)


def test_the_floor_being_off_does_not_turn_the_ceiling_off():
    avail = _official().assign(p_start_hint=0.0)
    out = apply_availability(_pred(), avail, curves=None, start_floor=0.0)
    assert out.set_index("gw").loc[5, "p_play"] == pytest.approx(0.0)


def test_the_news_master_switch_still_skips_every_fetcher(monkeypatch):
    """v5's rail, restated: v8a added arguments to both fetchers and neither
    may be reached with ``[news] enabled = false``."""
    from gaffer import advise as advise_mod

    calls: list[str] = []
    monkeypatch.setattr(advise_mod, "fetch_injuries",
                        lambda *a, **k: calls.append("injuries"))
    monkeypatch.setattr(advise_mod, "fetch_lineups",
                        lambda *a, **k: calls.append("lineups"))
    cfg = Config(entry_id=1, league_id=2, news_enabled=False)
    events = pd.DataFrame({"gw": [5], "deadline_time": ["2026-09-05T10:00Z"]})
    out = advise_mod.news_availability(cfg, _players(), _teams(), events, gw=5)
    assert calls == []
    assert list(out.columns) == ["code", "status", "chance_of_playing"]


# --- rail 6: the protected orderings, copied forward -----------------------

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
    from gaffer.models import minutes

    assert minutes.apply_availability is apply_availability
