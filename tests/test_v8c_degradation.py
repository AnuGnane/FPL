"""v8c's rails: what the machine does when the field is not there.

Gate G3 (spec §5). Every case here is a real Tuesday — a fresh clone, a switch
turned off, an FPL outage, a gameweek nobody scraped — and the claim is that
each of them degrades to v8a behaviour rather than to an error.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.field import (FIELD_EO_PATH, latest_field_eo,
                               load_field_sample, run_field_scrape)
from gaffer.data.tier_eo import tier_eo_table
from gaffer.models.availability import apply_availability
from gaffer.web import job_kinds
from gaffer.web.app import create_app
from tests.test_web_league_sim import FakeClient, _artifacts, _comp


@pytest.fixture()
def bare(tmp_path, monkeypatch):
    """A clone that has never run a scrape."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.field.RAW_FIELD",
                        tmp_path / "data/raw/field")
    monkeypatch.setattr("gaffer.data.field.RAW_TIER",
                        tmp_path / "data/raw/tier_eo")
    _artifacts(tmp_path)
    # The league-sim fixture ships no team table and the explorer names teams,
    # so ``/api/players`` would 422 for a reason that has nothing to do with
    # the field store. The rail below is about ``field_eo``; give it a clone
    # that is bare in exactly one way.
    pd.DataFrame([{"team_id": 1, "code": 300, "name": "LIV"},
                  {"team_id": 2, "code": 301, "name": "ARS"},
                  {"team_id": 3, "code": 302, "name": "MCI"}]).to_parquet(
        tmp_path / "data/live/teams.parquet", index=False)
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient())
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    return tmp_path


# --- the field store absent ------------------------------------------------


def test_the_league_hub_answers_without_any_field_store(bare):
    """v8a behaviour, unchanged: /race is what it always was and /sim runs
    with drift off rather than refusing."""
    client = TestClient(create_app())
    assert client.get("/api/league/race").status_code == 200
    body = client.get("/api/league/sim").json()
    assert body["field_rate"] is None
    assert 0.0 <= body["p_win"] <= 1.0


def test_the_explorer_column_is_absent_rather_than_zero(bare):
    rows = TestClient(create_app()).get("/api/players").json()
    assert rows, "the rail is vacuous if the explorer served no candidate"
    assert all(r["field_eo"] is None for r in rows)
    assert all(r["field_class"] is None for r in rows)


def test_the_latest_read_of_a_missing_log_is_empty(bare):
    assert latest_field_eo() == {}
    assert not store.exists(FIELD_EO_PATH)


def test_a_missing_sample_is_none_not_a_crash(bare):
    assert load_field_sample("2026-27", 3) is None


# --- the scrape switch off -------------------------------------------------


def test_the_switch_off_makes_no_api_calls_at_all(bare, monkeypatch):
    """Spied rather than asserted in prose: an off switch that still fetches
    is the failure mode that costs a rate limit."""
    calls = []
    monkeypatch.setattr("gaffer.api.client.FPLClient",
                        lambda *a, **kw: calls.append("client"))
    monkeypatch.setattr("gaffer.data.field.fetch_sample_picks",
                        lambda *a, **kw: calls.append("fetch") or [])
    off = Config(entry_id=1, league_id=5, current_season="2026-27",
                 field_scrape=False)
    assert run_field_scrape(off) is None
    assert calls == []


def test_the_job_kind_reports_a_switched_off_scrape_as_zero_rows(bare,
                                                                 monkeypatch):
    monkeypatch.setattr("gaffer.data.field.run_field_scrape", lambda: None)
    assert job_kinds.run_field_scrape_job() == {"rows": 0}


# --- a dead API ------------------------------------------------------------


def test_every_new_endpoint_is_a_422_when_the_api_is_dead(bare, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    client = TestClient(create_app())
    assert client.get("/api/league/sim").status_code == 422
    assert client.post("/api/league/whatif",
                       json={"pins": []}).status_code == 422


def test_a_dead_api_never_reaches_a_500(bare, monkeypatch):
    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: FakeClient(dead=True))
    monkeypatch.setattr("gaffer.web.routers.league_sim._CACHE", {})
    client = TestClient(create_app())
    for path in ("/api/league/sim",):
        assert client.get(path).status_code != 500


def test_a_dead_api_leaves_the_scrape_printing_one_line(bare, monkeypatch,
                                                        capsys):
    def _boom(*a, **kw):
        raise RuntimeError("FPL is down")

    monkeypatch.setattr("gaffer.api.client.FPLClient", _boom)
    assert run_field_scrape(Config(entry_id=1, league_id=5)) is None
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


# --- the tier-EO contract --------------------------------------------------


def test_the_tier_table_is_byte_compatible_with_v8a(bare, monkeypatch,
                                                    tmp_path):
    """The live tracker's cache file is a compatibility surface: its shape,
    its keys and its rounding are what v8a wrote, and the field store's
    existence changes none of them."""
    monkeypatch.setattr("gaffer.data.tier_eo.sample_slots",
                        lambda n, seed, **kw: [(1, 1)])
    monkeypatch.setattr("gaffer.data.tier_eo.FETCH_PAUSE_S", 0.0)

    class _One:
        def get_league_standings(self, league_id, page=1):
            return {"standings": {"results": [{"entry": 100 + s}
                                              for s in range(50)]}}

        def get_entry_picks(self, entry_id, gw):
            return {"picks": [{"element": 7, "multiplier": 2}]}

    out = tier_eo_table(_One(), 3, sample=1, raw_dir=tmp_path / "tier")
    assert out == {7: {"eo": 200.0, "se": 0.0, "n": 1}}
    raw = json.loads((tmp_path / "tier" / "3.json").read_text())
    assert raw == {"7": {"eo": 200.0, "se": 0.0, "n": 1}}


def test_the_live_endpoint_still_answers_with_no_field_store(bare):
    """``/api/live`` reads ``tier_eo_table`` and nothing else v8c added. The
    live suite pins its payload; this pins that v8c did not change which
    module it reaches."""
    import inspect

    from gaffer.web.routers import live

    assert "field" not in inspect.getsource(live)


# --- the what-if identity --------------------------------------------------


def test_an_empty_whatif_equals_the_sim_endpoint(bare):
    client = TestClient(create_app())
    base = client.get("/api/league/sim").json()
    out = client.post("/api/league/whatif", json={"pins": []}).json()
    assert out["p_win"] == base["p_win"]
    assert out["delta_p_win"] == 0.0


# --- the pins --------------------------------------------------------------


def test_the_job_kind_count_is_pinned():
    """Lockstep with ``frontend/src/types.ts``. A kind added on one side only
    is a button that 404s."""
    assert len(job_kinds.JOB_KINDS) == 8
    assert "field-scrape" in job_kinds.JOB_KINDS


def test_the_protected_seam_is_imported_not_edited():
    """Spec D4: the sigma table is read through ``scenarios``' public names.
    A reach into a private one would survive review and break on the next
    ``optimize`` change."""
    import inspect

    from gaffer import league_sim

    source = inspect.getsource(league_sim)
    assert "from gaffer.optimize.scenarios import" in source
    assert "scenarios._" not in source


def test_league_mode_win_probability_still_has_its_caller():
    """v8c supersedes it in the *card*, not in the codebase: /api/league/race
    still serves it and the UI still falls back to it."""
    import inspect

    from gaffer.web.routers import league

    assert "win_probability" in inspect.getsource(league)


# --- the protected orderings, copied forward from v8a ----------------------


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


# --- the simulation's lookups ----------------------------------------------


def test_a_squad_the_frame_cannot_resolve_degrades_out_loud(bare,
                                                            monkeypatch):
    """The G2 failure mode, railed at the endpoint.

    Every EP lookup in ``league_sim`` degrades to zero on a miss so that one
    unmodelled signing cannot take the card down. The hazard that buys is an
    id-space mismatch — squads keyed one way against a frame keyed another —
    which zeroes every squad and still renders a perfectly confident
    probability. The rail is that the page still answers *and* says what it
    could not resolve."""
    class _Stranger(FakeClient):
        def get_entry_picks(self, entry_id, gw):
            return {"picks": [{"element": 90001, "position": 1,
                               "multiplier": 2, "is_captain": True}]}

    monkeypatch.setattr("gaffer.web.routers.league_sim.fpl_client",
                        lambda: _Stranger())
    body = TestClient(create_app()).get("/api/league/sim").json()
    assert body["notice"] and "90001" in body["notice"]


def test_a_chip_week_snapshot_is_not_a_permanent_squad(bare, monkeypatch):
    """A rival's stored picks come from the week he played, chips included.
    A bench-boost week carries a multiplier on all fifteen, and read as a
    rate it hands him four extra players for the rest of the season — which
    is what pinned two rivals' ``p_beat`` at exactly 0.0 on league 1794743."""
    from gaffer.league_sim import Entry, entry_rate

    boosted = [{"element": 7, "position": p, "is_captain": p == 1,
                "multiplier": 2 if p == 1 else 1} for p in range(1, 16)]
    ordinary = [dict(p, multiplier=0 if p["position"] > 11
                     else p["multiplier"]) for p in boosted]
    ep = {7: 5.0}
    assert entry_rate(Entry(1, "BB", 0, boosted), ep) == pytest.approx(
        entry_rate(Entry(1, "XI", 0, ordinary), ep))
