"""v17e — the config in force behind one read and one invalidation
(specs/2026-09-08-v17e-config-in-force-design.md).

The four private readers are fields (§2.1), ``config_in_force()`` is the
one cached view and ``invalidate()`` the one clearing (§2.2), the bounds
and the refusal sentence are stated once (§2.3), and nothing outside
``config.py`` opens either TOML file (§1.2a)."""
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


@pytest.fixture(autouse=True)
def _fresh():
    invalidate()
    yield
    invalidate()


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


def test_invalidate_drops_the_price_fall_table(monkeypatch):
    from gaffer import price_timing as pt

    seen = []
    monkeypatch.setattr(pt.owned_price_falls, "cache_clear", lambda: seen.append(1))
    invalidate()
    assert seen == [1]


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
    assert out_of_range("decay", 4.0, "optimizer").startswith("[optimizer] decay = 4.0")


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
