"""v12 W5 §6.2 — the Settings endpoint.

Each whitelist entry declares how to read its own current value (plan A4):
eight from `dataclasses.fields(Config)`, one — `price_timing` — from a
module-level reader W2 owns, because that key is popped out of `[optimizer]`
before the splat and never becomes a field. Absence is a first-class answer
here rather than a fixture problem: an entry whose reader cannot find it is
named in `unavailable` and left out of the form.
"""
from __future__ import annotations

import json
import math

import pytest
import tomllib
from fastapi.testclient import TestClient

from gaffer.config import (LOCAL_OVERLAY, load_config, optimizer_top_n,
                           price_timing, serving_config)
from gaffer.web.app import create_app
from gaffer.web.settings_keys import WHITELIST, live_keys

BASE = """
[fpl]
entry_id = 111
league_id = 222

[optimizer]
horizon = 3
decay = 0.85
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(BASE)
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()


def overlay(tmp_path) -> dict:
    path = tmp_path / LOCAL_OVERLAY
    return tomllib.loads(path.read_text()) if path.exists() else {}


def test_the_panel_names_every_live_key_and_no_dead_one(client):
    body = client.get("/api/settings").json()
    served = {row["key"] for row in body["rows"]}
    assert served == set(live_keys())
    assert served <= {entry.field for entry in WHITELIST}


def test_exactly_one_entry_is_read_through_a_reader_and_it_is_price_timing():
    """Orchestrator ruling 3, 2026-09-02. price_timing is popped out of
    [optimizer] before the splat, so it never becomes a Config field and a
    getattr-based liveness check would drop the one key that is in fact
    configurable."""
    import dataclasses

    from gaffer.config import Config

    readers = [e for e in WHITELIST if e.source == "reader"]
    assert [e.field for e in readers] == ["price_timing"]
    fields = {f.name for f in dataclasses.fields(Config)}
    assert "price_timing" not in fields, (
        "price_timing became a Config field — move it to source='config' and "
        "delete its reader rather than serving a stale one")
    assert ":" in readers[0].reader


def test_every_config_kind_entry_names_a_real_config_field():
    import dataclasses

    from gaffer.config import Config

    fields = {f.name for f in dataclasses.fields(Config)}
    absent = [e.field for e in WHITELIST
              if e.source == "config" and e.field not in fields]
    # Empty at W5's base: W1 shipped top_n and W3 shipped draw_availability.
    # A non-empty list here is a workstream that did not land, and the panel
    # reports it in `unavailable` rather than crashing — which the next test
    # covers. This one exists so the difference is a failure and not a shrug.
    assert absent == []


def test_no_entry_writes_to_a_solver_section():
    """Program-wide ruling: there is no [solver] table. The spec writes
    `[solver] top_n` and `[solver] price_timing`; both are [optimizer]."""
    assert {e.section for e in WHITELIST} == {"optimizer", "league",
                                              "scenarios"}


def test_a_written_overlay_has_no_solver_table_in_it(client, tmp_path):
    """The behavioural half of the claim above. The set assertion is about the
    table; this is about the file — every whitelist key, written, and nothing
    lands under a section this tree does not have."""
    for key, value in [("horizon", 4), ("lambda_cap", 0.3),
                       ("decision_priors", False)]:
        assert client.post("/api/settings",
                           json={"key": key, "value": value}).status_code == 200
    raw = overlay(tmp_path)
    assert "solver" not in raw
    assert set(raw) == {"optimizer", "league", "scenarios"}
    # And the values reach the loader, which is what the sections are for.
    cfg = load_config(tmp_path / "config.toml")
    assert (cfg.horizon, cfg.lambda_cap, cfg.decision_priors) == (4, 0.3, False)


def test_the_secrets_are_not_in_the_whitelist():
    """The whole point of a whitelist. `odds_api_key` is the obvious one;
    `web_token` is the one that would be easy to forget, and handing it out —
    or letting it be rewritten — from an unauthenticated GET would be the
    interface handing over its own front door."""
    named = {e.field for e in WHITELIST}
    assert not named & {"odds_api_key", "web_token", "entry_id", "league_id",
                        "train_seasons", "backup_rsync_target",
                        "news_llm_command"}


def test_price_timing_is_written_into_optimizer_like_any_other_key(client,
                                                                   tmp_path):
    """The read is special; the write is not. The overlay is TOML either way."""
    assert "price_timing" in set(live_keys())
    assert client.post("/api/settings",
                       json={"key": "price_timing",
                             "value": False}).status_code == 200
    assert overlay(tmp_path)["optimizer"]["price_timing"] is False
    # And the reader that serves it sees the write, which is the only reason
    # the row is worth having at all.
    assert price_timing(tmp_path / "config.toml") is False


def test_a_key_this_build_does_not_have_is_reported_not_hidden(client):
    """If a workstream did not ship its key, the tab has to say so — a
    silently shorter form is a setting nobody can find and nobody knows is
    missing."""
    body = client.get("/api/settings").json()
    missing = set(body["unavailable"])
    assert missing == {e.field for e in WHITELIST} - set(live_keys())
    for name in missing:
        assert name in json.dumps(body)


def test_every_row_carries_the_value_the_config_actually_has(client):
    rows = {r["key"]: r for r in client.get("/api/settings").json()["rows"]}
    assert rows["horizon"]["value"] == 3
    assert rows["decay"]["value"] == 0.85


def test_a_row_says_where_its_value_came_from(client, tmp_path):
    rows = {r["key"]: r for r in client.get("/api/settings").json()["rows"]}
    # horizon is in config.toml; lambda_cap is in neither file.
    assert rows["horizon"]["source"] == "base"
    assert rows["lambda_cap"]["source"] == "default"


def test_a_write_lands_in_the_overlay_and_never_in_config_toml(client,
                                                               tmp_path):
    before = (tmp_path / "config.toml").read_text()
    body = client.post("/api/settings", json={"key": "horizon", "value": 5})
    assert body.status_code == 200
    assert overlay(tmp_path) == {"optimizer": {"horizon": 5}}
    assert (tmp_path / "config.toml").read_text() == before


def test_the_written_value_comes_back_on_the_same_response(client):
    rows = {r["key"]: r for r in
            client.post("/api/settings",
                        json={"key": "horizon", "value": 5}).json()["rows"]}
    assert rows["horizon"]["value"] == 5
    assert rows["horizon"]["source"] == "local"


def test_two_writes_do_not_overwrite_each_other(client, tmp_path):
    client.post("/api/settings", json={"key": "horizon", "value": 5})
    client.post("/api/settings", json={"key": "decay", "value": 0.7})
    assert overlay(tmp_path) == {"optimizer": {"horizon": 5, "decay": 0.7}}


def test_a_null_value_removes_the_key_and_falls_back(client, tmp_path):
    """The only way out of a bad edit without hand-editing the file the UI
    owns."""
    client.post("/api/settings", json={"key": "horizon", "value": 5})
    rows = {r["key"]: r for r in
            client.post("/api/settings",
                        json={"key": "horizon", "value": None}).json()["rows"]}
    assert rows["horizon"]["value"] == 3
    assert rows["horizon"]["source"] == "base"
    assert overlay(tmp_path).get("optimizer", {}) == {}


def test_a_key_outside_the_whitelist_is_refused_in_the_lab_shape(client,
                                                                 tmp_path):
    body = client.post("/api/settings",
                       json={"key": "odds_api_key", "value": "hunter2"})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "unknown_setting"
    assert not (tmp_path / LOCAL_OVERLAY).exists()


def test_a_value_out_of_bounds_is_refused_and_writes_nothing(client, tmp_path):
    body = client.post("/api/settings", json={"key": "decay", "value": 4.0})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "out_of_range"
    assert "0" in body.json()["detail"]["error"]
    assert not (tmp_path / LOCAL_OVERLAY).exists()


def test_a_value_of_the_wrong_type_is_refused(client):
    body = client.post("/api/settings", json={"key": "horizon", "value": "5"})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "wrong_type"


def test_a_bool_is_not_an_int(client):
    """`isinstance(True, int)` is True in Python and `horizon = true` would be
    written to the overlay as a boolean, which tomllib reads back as one."""
    body = client.post("/api/settings", json={"key": "horizon", "value": True})
    assert body.status_code == 422


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_a_float_that_is_not_a_number_is_refused(client, tmp_path, literal):
    """tomli_w writes a bare `nan` and tomllib reads it back as one, so a
    `decay = nan` in the overlay would reach the objective and quietly turn
    every score into NaN — guarded parse, unguarded arithmetic, one file
    further out. Refused at the door, where there is still someone to tell.

    Posted as raw body text rather than through `json=`: `NaN` is not JSON and
    the client's own encoder refuses to write it, while Python's decoder — the
    one on the server — accepts it happily. That asymmetry is exactly why the
    server cannot rely on the client to have refused first."""
    body = client.post("/api/settings",
                       content=f'{{"key": "decay", "value": {literal}}}',
                       headers={"content-type": "application/json"})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] in {"wrong_type",
                                                   "out_of_range"}
    assert not (tmp_path / LOCAL_OVERLAY).exists()
    assert not math.isnan(load_config(tmp_path / "config.toml").decay)


def test_the_bench_curve_needs_exactly_three_weights(client):
    body = client.post("/api/settings",
                       json={"key": "bench_curve", "value": [0.3, 0.2]})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "wrong_type"


def test_the_bench_curve_is_reset_rather_than_emptied(client, tmp_path):
    """`None` is a *value* for this one — "no curve, one flat bench weight" —
    but TOML has no null and an empty list is a curve of the wrong length,
    which `milp` treats as an error at solve time. So the row resets like every
    other: the key comes out of the file."""
    client.post("/api/settings",
                json={"key": "bench_curve", "value": [0.3, 0.2, 0.1]})
    assert overlay(tmp_path)["optimizer"]["bench_curve"] == [0.3, 0.2, 0.1]
    assert client.post("/api/settings",
                       json={"key": "bench_curve",
                             "value": None}).status_code == 200
    assert "bench_curve" not in overlay(tmp_path).get("optimizer", {})
    assert client.post("/api/settings",
                       json={"key": "bench_curve",
                             "value": []}).status_code == 422


def test_the_pool_is_a_whole_number_for_each_position(client, tmp_path):
    assert client.post("/api/settings",
                       json={"key": "top_n",
                             "value": {"GKP": 5, "DEF": 6}}).status_code == 422
    assert client.post("/api/settings",
                       json={"key": "top_n",
                             "value": {"GKP": 5, "DEF": 6, "MID": 7,
                                       "FWD": 8}}).status_code == 200
    assert overlay(tmp_path)["optimizer"]["top_n"] == {"GKP": 5, "DEF": 6,
                                                       "MID": 7, "FWD": 8}


def test_the_write_clears_the_serving_config_cache(client):
    """serving_config is lru_cached for the life of the process (config.py
    :311-333). A save that did not clear it would leave the news layer on the
    old value with nothing on the page to say so."""
    assert serving_config().horizon == 3
    client.post("/api/settings", json={"key": "horizon", "value": 6})
    assert serving_config().horizon == 6


def test_the_write_clears_the_solver_pool_cache(client):
    """`optimizer_top_n` is cached on the same terms and is what `build_pool`
    actually reads. A saved pool size the solver never sees is the exact shape
    of the failure this endpoint exists to avoid."""
    assert optimizer_top_n()["GKP"] == 8
    client.post("/api/settings",
                json={"key": "top_n",
                      "value": {"GKP": 3, "DEF": 4, "MID": 5, "FWD": 6}})
    assert optimizer_top_n()["GKP"] == 3


def test_the_write_clears_the_price_fall_cache(client, monkeypatch):
    """The third serve-time cache keyed on `[optimizer]`. Nothing on this
    endpoint can observe its contents, so the claim under test is that the
    save asks for it to be dropped — the same one line meta.py's health poll
    spends (`meta.py:318`)."""
    from gaffer.web.routers import settings as mod

    seen = []
    monkeypatch.setattr(mod.owned_price_falls, "cache_clear",
                        lambda: seen.append(1))
    client.post("/api/settings", json={"key": "price_timing", "value": False})
    assert seen == [1]


def test_the_panel_carries_the_sentence_about_what_a_save_reaches(client):
    note = client.get("/api/settings").json()["apply_note"]
    assert "already running" in note


def test_an_unreadable_overlay_is_reported_rather_than_thrown(client,
                                                              tmp_path):
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer\nhorizon = 5")
    body = client.get("/api/settings")
    assert body.status_code == 200
    assert LOCAL_OVERLAY in body.json()["overlay_error"]
    assert body.json()["rows"]


def test_a_write_onto_an_unreadable_overlay_refuses_rather_than_clobbers(
        client, tmp_path):
    """Overwriting a file we could not read would silently discard whatever
    the user had hand-edited into it."""
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer\nhorizon = 5")
    body = client.post("/api/settings", json={"key": "horizon", "value": 6})
    assert body.status_code == 422
    assert body.json()["detail"]["constraint"] == "overlay_unreadable"
    assert (tmp_path / LOCAL_OVERLAY).read_text() == "[optimizer\nhorizon = 5"


def test_a_healthy_overlay_reports_no_error(client, tmp_path):
    client.post("/api/settings", json={"key": "horizon", "value": 5})
    assert client.get("/api/settings").json()["overlay_error"] is None


def test_a_cold_clone_with_no_config_is_a_200_that_says_so(tmp_path,
                                                           monkeypatch):
    """Every other read endpoint degrades rather than 500s and this one is
    the endpoint a new user reaches first."""
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/settings")
    assert body.status_code == 200
    assert body.json()["rows"] == []
    assert "config.toml" in body.json()["overlay_error"]
    serving_config.cache_clear()
