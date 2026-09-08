"""v17e — the config in force behind one read and one invalidation
(specs/2026-09-08-v17e-config-in-force-design.md).

The four private readers are fields (§2.1), ``config_in_force()`` is the
one cached view and ``invalidate()`` the one clearing (§2.2), the bounds
and the refusal sentence are stated once (§2.3), and nothing outside
``config.py`` opens either TOML file (§1.2a).

The three field-read tests below deliberately restate facts the moved v12
and v10 files also assert. That is the point: this file is the cycle's one
readable rail, and a reader who opens it should not have to go and find
four other files to learn what the interface promises."""
from __future__ import annotations

import dataclasses

import pytest

from gaffer.config import (BOUNDS, DEFAULT_LINEUP_PROVIDERS, DEFAULT_TOP_N,
                           HIT_BAR_HI, HIT_BAR_LO, LOCAL_OVERLAY, NO_CAP,
                           Config, base_exists, config_in_force, invalidate,
                           load_config, out_of_range, read_overlay,
                           value_source, write_overlay)
from gaffer.errors import GafferError

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


def _cfg(tmp_path, body: str = "", local: str | None = None):
    (tmp_path / "config.toml").write_text(BASE + body)
    if local is not None:
        (tmp_path / LOCAL_OVERLAY).write_text(local)
    return tmp_path / "config.toml"


# --- §2.1 the four readers as fields -------------------------------------

def test_the_three_new_fields_exist_with_the_shipped_defaults():
    cfg = Config(entry_id=1, league_id=5)
    assert cfg.price_timing is True
    assert cfg.xg_per_shot is False
    assert cfg.news_lineup_providers == list(DEFAULT_LINEUP_PROVIDERS)
    names = {f.name for f in dataclasses.fields(Config)}
    assert {"price_timing", "xg_per_shot", "news_lineup_providers"} <= names


def test_price_timing_is_read_from_the_optimizer_table(tmp_path):
    assert load_config(_cfg(tmp_path, "[optimizer]\nprice_timing = false\n")).price_timing is False


def test_xg_per_shot_is_read_from_the_model_table(tmp_path):
    assert load_config(_cfg(tmp_path, "[model]\nxg_per_shot = true\n")).xg_per_shot is True


def test_lineup_providers_are_cleaned_by_the_loader(tmp_path, capsys):
    cfg = load_config(_cfg(tmp_path, '[news]\nlineup_providers = [" FFS ", "nope"]\n'))
    assert cfg.news_lineup_providers == ["ffs"]
    assert "nope" in capsys.readouterr().out


def test_a_non_list_of_providers_falls_back_with_a_line(tmp_path, capsys):
    cfg = load_config(_cfg(tmp_path, '[news]\nlineup_providers = "ffs"\n'))
    assert cfg.news_lineup_providers == list(DEFAULT_LINEUP_PROVIDERS)
    assert "not a list" in capsys.readouterr().out


def test_an_empty_provider_list_is_the_kill_switch(tmp_path):
    assert load_config(_cfg(tmp_path, "[news]\nlineup_providers = []\n")).news_lineup_providers == []


def test_a_typo_under_optimizer_still_raises_loudly(tmp_path):
    """The pop list is gone; the splat is still a splat, so a typo is a
    ``TypeError`` and not a season of quietly wrong advice."""
    with pytest.raises(TypeError):
        load_config(_cfg(tmp_path, "[optimizer]\nhorizen = 6\n"))


def test_solver_top_n_merges_over_the_shipped_default(tmp_path):
    cfg = load_config(_cfg(tmp_path, "[optimizer]\ntop_n = {DEF = 30, XYZ = 4, MID = 0, FWD = true}\n"))
    assert cfg.solver_top_n() == {**DEFAULT_TOP_N, "DEF": 30}


def test_solver_top_n_hands_out_a_fresh_dict():
    cfg = Config(entry_id=1, league_id=5)
    cfg.solver_top_n()["GKP"] = 1
    assert cfg.solver_top_n()["GKP"] == DEFAULT_TOP_N["GKP"]


def test_solver_top_n_survives_a_table_that_is_not_a_table():
    cfg = Config(entry_id=1, league_id=5, top_n=7)  # type: ignore[arg-type]
    assert cfg.solver_top_n() == DEFAULT_TOP_N


# --- §2.2 one read, one invalidation --------------------------------------

def test_config_in_force_reads_the_cwd_and_is_cached(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, "[optimizer]\nhorizon = 4\n")
    assert config_in_force().horizon == 4
    _cfg(tmp_path, "[optimizer]\nhorizon = 7\n")
    assert config_in_force().horizon == 4          # the trade, documented
    invalidate()
    assert config_in_force().horizon == 7


def test_config_in_force_never_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = config_in_force()
    assert (cfg.entry_id, cfg.league_id) == (0, 0)
    assert cfg.price_timing is True


def test_invalidate_drops_the_price_fall_table(tmp_path, monkeypatch):
    """Behaviour, not a mock: seeding the table under a config-less cwd
    caches an empty answer, and ``invalidate()`` has to drop that entry too
    or a flipped switch would be read against a stale table (v17e §2.2)."""
    from gaffer.price_timing import owned_price_falls

    monkeypatch.chdir(tmp_path)
    owned_price_falls([1])
    assert owned_price_falls.cache_info().currsize == 1
    invalidate()
    assert owned_price_falls.cache_info().currsize == 0


def test_focus_league_reads_the_effective_id_through_the_view(tmp_path, monkeypatch):
    from gaffer.config import focus_league

    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, local="[league]\nfocus = 77\n")
    assert focus_league() == 77


# --- §2.3 bounds stated once ----------------------------------------------

def test_the_bounds_table_names_every_numeric_setting():
    assert set(BOUNDS) == {"horizon", "decay", "itb_value", "bench_curve",
                           "lambda_cap", "top_n", "max_hits", "max_transfers",
                           "hit_bar", "focus"}
    assert BOUNDS["max_hits"] == (0, NO_CAP)
    assert (HIT_BAR_LO, HIT_BAR_HI) == BOUNDS["hit_bar"] == (0.5, 0.95)


def test_out_of_range_is_one_sentence_with_the_section_and_the_bounds():
    assert out_of_range("hit_bar", 1.2, "optimizer") == (
        "[optimizer] hit_bar = 1.2 — must be a number between 0.5 and 0.95")
    assert out_of_range("max_hits", 16) == (
        "[optimizer] max_hits = 16 — must be a whole number between 0 and 15 "
        "(15 means no cap)")
    assert out_of_range("horizon", 9) == (
        "[optimizer] horizon = 9 — must be a whole number between 1 and 8")
    assert out_of_range("decay", 4.0, "optimizer") == (
        "[optimizer] decay = 4.0 — must be a number between 0.0 and 1.0")


def test_the_loader_refuses_with_the_same_sentence(tmp_path):
    with pytest.raises(GafferError, match=r"\[optimizer\] max_hits = 16 — must be a whole number between 0 and 15 \(15 means no cap\)"):
        load_config(_cfg(tmp_path, "[optimizer]\nmax_hits = 16\n"))


# --- §2.8 the overlay's file access ----------------------------------------

def test_read_overlay_is_empty_when_absent_and_names_a_bad_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert read_overlay() == ({}, None)
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer\nhorizon = 2")
    raw, err = read_overlay()
    assert raw == {}
    assert LOCAL_OVERLAY in err and "ignored" in err


def test_write_overlay_round_trips_with_the_header(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_overlay({"optimizer": {"horizon": 2}})
    text = (tmp_path / LOCAL_OVERLAY).read_text()
    assert text.startswith("# Written by the gaffer web UI")
    assert read_overlay() == ({"optimizer": {"horizon": 2}}, None)


def test_value_source_says_which_file_a_value_came_from(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, "[optimizer]\nhorizon = 4\n", local="[optimizer]\ndecay = 0.5\n")
    assert value_source("optimizer", "decay") == "local"
    assert value_source("optimizer", "horizon") == "base"
    assert value_source("optimizer", "hit_bar") == "default"


def test_value_source_ignores_a_section_that_is_not_a_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, local="optimizer = 5\n")
    assert value_source("optimizer", "horizon") == "default"


def test_base_exists_is_the_cwd_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert base_exists() is False
    _cfg(tmp_path)
    assert base_exists() is True


# --- §0 the deletion test ---------------------------------------------------

def test_the_old_readers_and_serving_config_are_gone():
    """v17e §0: a name that survives is a name someone keeps reading
    through, so the four private readers and the old view are deleted
    rather than aliased."""
    import gaffer.config as mod

    for name in ("serving_config", "price_timing", "xg_per_shot",
                 "lineup_providers", "optimizer_top_n",
                 "NON_FIELD_OPTIMIZER_KEYS", "_optimizer_top_n"):
        assert not hasattr(mod, name), name


# --- §2.3–§2.5 the registry -------------------------------------------------

SETTINGS_BASE = "[fpl]\nentry_id = 111\nleague_id = 222\n[optimizer]\nhorizon = 3\n"


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(SETTINGS_BASE)
    # The chdir is what the view is keyed on, so the cache is dropped on both
    # sides of it (v17e §2.2).
    invalidate()
    yield TestClient(create_app())
    invalidate()


def test_every_whitelist_bound_is_the_config_bound():
    from gaffer.web.settings_keys import WHITELIST

    for entry in WHITELIST:
        if entry.field in BOUNDS:
            assert (entry.lo, entry.hi) == BOUNDS[entry.field], entry.field
        else:
            assert (entry.lo, entry.hi) == (None, None), entry.field


def test_every_whitelist_entry_reads_and_writes_through_the_one_interface(settings_client):
    """Written through the endpoint, read back changed through
    config_in_force() with no cache_clear in this test: the save's
    invalidate() is the only clearing there is."""
    from gaffer.web.settings_keys import WHITELIST, current_value

    samples = {"int": 2, "float": 0.3, "bool": False, "floats3": [0.5, 0.4, 0.3],
               "pool": {"GKP": 2, "DEF": 3, "MID": 4, "FWD": 5}, "choice": "chase"}
    samples_by_field = {"hit_bar": 0.7, "focus": 222, "max_hits": 1,
                        "max_transfers": 1, "horizon": 2}
    for entry in WHITELIST:
        value = samples_by_field.get(entry.field, samples[entry.kind])
        before = current_value(entry, config_in_force())
        resp = settings_client.post("/api/settings", json={"key": entry.field, "value": value})
        assert resp.status_code == 200, (entry.field, resp.text)
        after = current_value(entry, config_in_force())
        assert after == value, entry.field
        assert after != before or entry.field == "focus", entry.field


def test_the_three_select_rows_carry_labelled_options(settings_client):
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    assert rows["max_hits"]["options"][-1] == {"value": 15, "label": "no cap"}
    assert rows["max_transfers"]["options"][0] == {"value": 0, "label": "bank"}
    assert [o["label"] for o in rows["hit_bar"]["options"]][:3] == ["50%", "55%", "60%"]
    assert rows["horizon"]["options"] == []


def test_a_saved_value_the_select_does_not_offer_is_inserted_in_order(settings_client, tmp_path):
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer]\nmax_hits = 5\nhit_bar = 0.62\n")
    invalidate()
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    hits = [o["value"] for o in rows["max_hits"]["options"]]
    assert hits == [0, 1, 2, 3, 5, 15]
    bar = rows["hit_bar"]["options"]
    assert {"value": 0.62, "label": "62%"} in bar
    assert [o["value"] for o in bar] == sorted(o["value"] for o in bar)


def test_the_router_refuses_with_the_config_sentence(settings_client):
    resp = settings_client.post("/api/settings", json={"key": "hit_bar", "value": 0.99})
    assert resp.status_code == 422
    assert resp.json()["detail"] == {
        "constraint": "out_of_range",
        "error": out_of_range("hit_bar", 0.99, "optimizer"), "players": []}
    resp = settings_client.post("/api/settings", json={"key": "max_hits", "value": 16})
    assert resp.json()["detail"]["error"] == out_of_range("max_hits", 16, "optimizer")


def test_the_settings_router_imports_no_toml_library():
    import gaffer.web.routers.settings as mod

    assert not hasattr(mod, "tomllib") and not hasattr(mod, "tomli_w")
