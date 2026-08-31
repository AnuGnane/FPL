"""v8d rails: what the live matchday view does when the inputs are missing.

The Live hub is the page opened at three o'clock on a Saturday, when nothing
can be fixed and every dependency — the component file, the league, the API —
is either there or it is not. Each of these tests is one of those afternoons.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

import gaffer.live_gw as live_gw
import gaffer.web.routers.live as live_mod
from gaffer.web.app import create_app
from tests.test_web_live_v8d import (COMPONENTS, FakeClient, MY_PICKS,
                                     _setup)


@pytest.fixture(autouse=True)
def _clean_series():
    live_mod.RACE_SERIES.clear()
    live_mod.RACE_RIVAL.clear()
    yield
    live_mod.RACE_SERIES.clear()
    live_mod.RACE_RIVAL.clear()


def _client(tmp_path, monkeypatch, standings=True, **kwargs):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path, **kwargs)
    monkeypatch.setattr(live_mod, "fpl_client",
                        lambda: FakeClient(standings=standings))
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    return TestClient(create_app())


# --- no components ----------------------------------------------------


def test_without_components_the_race_is_the_projected_score_and_says_so(
        tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, components=False)
    body = client.get("/api/live").json()
    assert body["active"] is True
    assert body["my_race"] == body["my_projected_points"]
    assert "component breakdown" in body["race_notice"]
    # A6: the race's degradation gets its own field. ``notice`` is the
    # tier-EO line (here, the stubbed-empty sample's own message) and says
    # nothing about components.
    assert "component" not in (body["notice"] or "")
    assert all(p["remaining_ep"] is None for p in body["players"])


def test_a_component_file_for_the_wrong_gameweek_degrades_the_same_way(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path, components=False)
    COMPONENTS[COMPONENTS["gw"] == 4].to_parquet(
        tmp_path / "reports/components_gw3.parquet", index=False)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    body = TestClient(create_app()).get("/api/live").json()
    assert "no GW3 rows" in body["race_notice"]
    assert body["my_race"] == body["my_projected_points"]


def test_an_unreadable_component_file_is_a_notice_not_a_500(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path, components=False)
    (tmp_path / "reports/components_gw3.parquet").write_text("not a parquet")
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    body = TestClient(create_app()).get("/api/live").json()
    assert body["active"] is True and body["race_notice"]


def test_no_saved_advice_leaves_the_reference_line_off(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, advice=False)
    assert client.get("/api/live").json()["race_reference"] is None


# --- no league --------------------------------------------------------


def test_without_a_league_the_strip_is_absent_and_the_players_card_is_fine(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    # 0 is the repo's idiom for "no league configured"; the key itself is
    # required by ``load_config``.
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\nleague_id = 0\n')
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    body = TestClient(create_app()).get("/api/live").json()
    assert body["safety"] == []
    assert body["rival_name"] is None
    assert len(body["table"]) == 1
    assert len(body["players"]) == len(MY_PICKS["picks"])
    assert body["race_series"][0]["rival"] is None


# --- the API is down --------------------------------------------------


def test_a_dead_api_is_still_the_existing_retriable_guard(tmp_path,
                                                          monkeypatch):
    class Dead:
        def get_event_status(self):
            raise RuntimeError("connection reset")

    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: Dead())
    response = TestClient(create_app(), raise_server_exceptions=False) \
        .get("/api/live")
    assert response.status_code == 422
    assert "retry in a moment" in response.json()["detail"]


# --- the pinned contract ----------------------------------------------


def test_entry_live_points_still_applies_no_autosubs(tmp_path):
    """A copy of the pin, restated here so a v8d change to the projection can
    never quietly become a change to the figure three callers rely on."""
    picks = [{"element": 1, "multiplier": 1},      # blanked starter
             {"element": 2, "multiplier": 0}]      # bench player who hauled
    points = {1: 0, 2: 12}
    assert live_gw.entry_live_points(picks, points, {1: 0, 2: 3}) == 0


def test_the_projection_is_a_separate_function_from_the_pinned_one():
    """``projected_points`` composes ``entry_live_points``; it does not
    reimplement it, and ``entry_live_points`` takes no projection argument."""
    assert list(inspect.signature(live_gw.entry_live_points).parameters) == [
        "picks", "points_of", "bonus"]
    assert "entry_live_points" in inspect.getsource(live_gw.projected_points)


def test_nothing_in_the_live_path_writes_to_disk(tmp_path, monkeypatch):
    """The projection is display-only. Three polls, and the tree is byte-for-
    byte what it was."""
    client = _client(tmp_path, monkeypatch)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")
              if p.is_file()}
    for _ in range(3):
        assert client.get("/api/live").status_code == 200
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")
             if p.is_file()}
    assert before == after


def test_the_race_series_never_leaves_the_process(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.get("/api/live")
    assert live_mod.RACE_SERIES                  # in memory
    assert not list(tmp_path.rglob("*race*"))    # and nowhere else


def test_v8d_adds_no_job_kinds(tmp_path, monkeypatch):
    """The whole cycle is a read path: no launchd plist, no queued work."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert "live" not in JOB_KINDS
    assert "race" not in JOB_KINDS
    # 9 -> 10: v8e added the `sensitivity` kind on both sides (deliberate
    # pin update per this file's convention, authorised by the v8e orchestrator).
    assert len(JOB_KINDS) == 10


def test_v8d_adds_no_config_keys(tmp_path, monkeypatch):
    """Nothing in the cycle is switchable, so nothing in the cycle is
    configured (spec §2)."""
    import gaffer.config as config_mod

    source = inspect.getsource(config_mod)
    for key in ("race_", "safety_", "autosub"):
        assert key not in source
