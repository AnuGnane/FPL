"""v13 — the transfer ladder (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md).

The rail: the caps at their defaults, the MILP byte-identical with both
caps ``None``, the routes and job kinds, the ladder's shape. This is the
newest cycle's file, so it holds the one absolute ``fields(Config)`` pin
(W3's ruling, 2026-09-02); the absolute route pin stays in v11's file.
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest

from gaffer.config import NO_CAP, Config, load_config
from gaffer.errors import GafferError


# --- Block 1: the two levers ---------------------------------------------

def test_the_config_gained_exactly_two_fields():
    """55 after v12 W3 (``test_v12_w3_degradation.py``), 57 here. The claim
    is the two names; 57 is the arithmetic. Pinned as a total *and* by name
    so a key cannot be swapped for another in one cycle."""
    names = {f.name for f in dataclasses.fields(Config)}
    assert len(names) == 57
    assert {"max_hits", "max_transfers"} <= names


def test_the_caps_default_to_two_hits_and_no_transfer_cap():
    cfg = Config(entry_id=1, league_id=2)
    assert cfg.max_hits == 2
    assert cfg.max_transfers == NO_CAP == 15


def test_the_caps_are_read_from_the_optimizer_table(tmp_path):
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        "[optimizer]\nmax_hits = 1\nmax_transfers = 0\n")
    cfg = load_config(tmp_path / "config.toml")
    assert (cfg.max_hits, cfg.max_transfers) == (1, 0)


@pytest.mark.parametrize("line", ["max_hits = 16", "max_hits = -1",
                                  "max_transfers = 2.5",
                                  "max_transfers = true"])
def test_a_cap_outside_0_to_15_is_refused_by_name(tmp_path, line):
    (tmp_path / "config.toml").write_text(
        f"[fpl]\nentry_id = 1\nleague_id = 2\n[optimizer]\n{line}\n")
    key = line.split(" =")[0]
    with pytest.raises(GafferError, match=key):
        load_config(tmp_path / "config.toml")


def test_the_two_keys_are_documented():
    root = pathlib.Path(__file__).resolve().parents[1]
    for doc in ("config.example.toml", "README.md"):
        text = (root / doc).read_text(encoding="utf-8")
        assert "max_hits" in text and "max_transfers" in text, doc


# --- Block 2: the MILP ---------------------------------------------------

def test_both_caps_none_build_the_golden_lp_byte_for_byte(tmp_path):
    """``tests/data/v12_w3_milp_golden.lp`` came off the code before
    ``force_out`` existed and is unchanged by this cycle: a defaulted
    ``max_transfers`` emits no constraint."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    captured = _capture_lp(tmp_path, _state(max_transfers=None,
                                            max_hits=None))
    assert len(captured) == 1
    assert captured[0] == GOLDEN.read_text()


def test_a_transfer_cap_does_change_the_lp(tmp_path):
    """The counterpart: a cap that *is* set writes a row, so the byte
    equality above is evidence about ``None`` and not about the instrument.

    Two, not one. That fixture's owned 15 is 7 MID and 1 FWD against a
    ``SQUAD_COMPOSITION`` of 5 and 3, so it takes two moves to become a legal
    squad at all and a cap of one is infeasible for a reason that has nothing
    to do with this constraint.
    """
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    captured = _capture_lp(tmp_path, _state(max_transfers=2))
    assert captured[0] != GOLDEN.read_text()


# --- Block 3: the saved state and the CLI --------------------------------

def _state_with(opt_extra: dict):
    import pandas as pd

    from gaffer.artifacts import SolveState

    return SolveState(
        gw=1, gws=[1, 2], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[], lam=0.0, league_eo={},
        avail_by_gw={1: [], 2: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": 2, **opt_extra},
        pool=pd.DataFrame(columns=["code", "name", "position", "team_code",
                                   "cost", "sell", "owned", "gw", "ep_raw"]))


def test_caps_from_state_reads_none_none_off_a_pre_v13_state():
    from gaffer.artifacts import caps_from_state

    assert caps_from_state(_state_with({})) == (None, None)


def test_caps_from_state_maps_the_sentinel_and_keeps_a_real_cap():
    from gaffer.artifacts import caps_from_state

    assert caps_from_state(_state_with({"max_hits": 2, "max_transfers": 15})) \
        == (2, None)
    assert caps_from_state(_state_with({"max_hits": 15, "max_transfers": 0})) \
        == (None, 0)


def test_solve_kw_from_state_ignores_the_two_keys():
    from gaffer.artifacts import solve_kw_from_state

    kw = solve_kw_from_state(_state_with({"max_hits": 2, "max_transfers": 15}))
    assert "max_hits" not in kw and "max_transfers" not in kw


def test_the_cli_prints_the_caps_line_when_the_advice_carries_one(
        tmp_path, monkeypatch):
    """v4c's rail (``test_v4c_degradation.py``) builds its Advice without
    ``caps``, so its output is untouched; a real run sets the field and gets
    one extra line, below the hits."""
    from typer.testing import CliRunner

    import gaffer.advise as advise_mod
    import gaffer.config as config_mod
    import gaffer.report.render as render_mod
    import gaffer.tracking as tracking_mod
    from gaffer.cli import app
    from tests.test_v4c_degradation import _fixture_advice

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\n'
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')
    real_load = config_mod.load_config
    monkeypatch.setattr(config_mod, "load_config",
                        lambda path="config.toml": real_load(cfg_path))
    advice = _fixture_advice()
    advice.caps = {"max_hits": 2, "max_transfers": 15}
    monkeypatch.setattr(advise_mod, "run_advise",
                        lambda cfg, client=None: advice)
    monkeypatch.setattr(render_mod, "render_report",
                        lambda advice, **kw: "reports/gw7.html")
    monkeypatch.setattr(tracking_mod, "latest_health", lambda: None)

    result = CliRunner().invoke(app, ["advise"])
    assert result.exit_code == 0, result.output
    assert "Caps: 2 hits/week, transfers uncapped\n" in result.output
    assert result.output.index("Caps:") < result.output.index("Captain:")


@pytest.mark.parametrize("caps, line", [
    ({"max_hits": 15, "max_transfers": 15}, "Caps: none"),
    ({"max_hits": 1, "max_transfers": 0}, "Caps: 1 hit/week, no transfers (bank)"),
    ({"max_hits": 15, "max_transfers": 2}, "Caps: hits uncapped, 2 transfers/week"),
])
def test_the_caps_line_wording(caps, line):
    from gaffer.cli import _caps_line

    assert _caps_line(caps) == line


# --- Block 4: Settings ---------------------------------------------------

SETTINGS_BASE = """
[fpl]
entry_id = 111
league_id = 222

[optimizer]
horizon = 3
"""


@pytest.fixture()
def settings_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.config import optimizer_top_n, serving_config
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(SETTINGS_BASE)
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()
    optimizer_top_n.cache_clear()


def test_the_settings_panel_serves_both_caps_with_their_range(settings_client):
    rows = {r["key"]: r for r in settings_client.get("/api/settings").json()["rows"]}
    assert rows["max_hits"]["value"] == 2
    assert rows["max_transfers"]["value"] == 15
    for key in ("max_hits", "max_transfers"):
        assert rows[key]["kind"] == "int"
        assert (rows[key]["lo"], rows[key]["hi"]) == (0, 15)
        assert rows[key]["section"] == "optimizer"
        assert rows[key]["source"] == "default"


def test_a_saved_cap_reaches_load_config(settings_client, tmp_path):
    import tomllib

    from gaffer.config import LOCAL_OVERLAY, load_config

    resp = settings_client.post("/api/settings",
                                json={"key": "max_hits", "value": 1})
    assert resp.status_code == 200, resp.text
    overlay = tomllib.loads((tmp_path / LOCAL_OVERLAY).read_text())
    assert overlay["optimizer"]["max_hits"] == 1
    assert load_config(tmp_path / "config.toml").max_hits == 1


def test_a_cap_above_fifteen_is_refused_at_the_endpoint(settings_client):
    resp = settings_client.post("/api/settings",
                                json={"key": "max_transfers", "value": 16})
    assert resp.status_code == 422
    assert resp.json()["detail"]["constraint"] == "out_of_range"


# --- Block 5: the ladder's shape on the golden board ----------------------

def test_build_ladder_on_a_saved_board_has_the_spec_shape(tmp_path,
                                                          monkeypatch):
    from tests.test_ladder import save_state

    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 2, "max_transfers": 15})
    out = build_ladder(1, n_draws=20, seed=5)
    assert out["gw"] == 1 and out["n_draws"] == 20 and out["seed"] == 5
    assert out["free_transfers"] == 1
    assert [r["key"] for r in out["rungs"]][:5] == \
        ["bank", "hits0", "hits1", "hits2", "hits3"]
    assert len(out["rungs"]) in (5, 6)
    for r in out["rungs"]:
        assert set(r) >= {"key", "hits", "transfers", "cost", "same_as",
                          "plan_by_gw", "week_pts", "horizon_pts",
                          "objective", "mean_pts", "p10_pts", "p90_pts",
                          "p_beats_bank", "p_beats_top", "p_best",
                          "vs_below"}
    bank = out["rungs"][0]
    assert bank["p_beats_bank"] is None and bank["vs_below"] is None
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert sum(r["p_best"] for r in distinct) == pytest.approx(1.0, abs=1e-6)
    assert any(r["same_as"] for r in out["rungs"])


# --- Block 6: routes and kinds -------------------------------------------

def test_the_ladder_route_exists_and_the_job_kinds_did_not_move(tmp_path,
                                                                monkeypatch):
    """By name, never by total: the absolute route count lives in
    ``test_v11_degradation.py`` alone (47 → 48 there; GET and POST share one
    path key, as ``/api/settings`` did). No thirteenth kind: the rebuild is
    an anonymous ``JobRegistry`` submission like What-If."""
    from gaffer.web.app import create_app
    from gaffer.web.job_kinds import JOB_KINDS

    monkeypatch.chdir(tmp_path)
    paths = create_app().openapi()["paths"]
    assert "/api/ladder" in paths
    assert {"get", "post"} <= set(paths["/api/ladder"])
    assert len(JOB_KINDS) == 12
