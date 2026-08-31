"""v8e rails: what solver-trust does when its inputs are not there.

Four stores were added this cycle and every one of them is optional. The
question each test asks is the same one: with this file absent, corrupt, or
switched off, is the tool exactly what it was in v8d?
"""

from __future__ import annotations

import inspect
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import serving_config
from gaffer.models.availability import apply_availability
from gaffer.web.app import create_app

CODES = [1, 2]


def _pred():
    return pd.DataFrame([{"code": c, "gw": 5, "p_play": 0.8, "p60": 0.6,
                          "e_min": 60.0} for c in CODES])


def _avail():
    return pd.DataFrame({"code": CODES, "status": ["d", "a"],
                         "chance_of_playing": [25.0, None]})


def _client(tmp_path, monkeypatch, overrides: bool = True):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        f'[fpl]\nentry_id = 1\nleague_id = 5\n\n[news]\n'
        f'overrides = {"true" if overrides else "false"}\n')
    serving_config.cache_clear()
    (tmp_path / "reports").mkdir(exist_ok=True)
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_config_cache():
    serving_config.cache_clear()
    yield
    serving_config.cache_clear()


# --- overrides absent, corrupt, or off --------------------------------


def test_no_override_file_is_byte_identical_to_v8d(tmp_path, monkeypatch):
    """The pin that pins nothing: with no store, the availability pass is
    arithmetically the function v8d shipped."""
    monkeypatch.chdir(tmp_path)
    with_pass = apply_availability(_pred(), _avail(), overrides=True)
    without = apply_availability(_pred(), _avail(), overrides=False)
    pd.testing.assert_frame_equal(with_pass, without)


def test_a_corrupt_override_file_changes_nothing_and_says_so(tmp_path,
                                                             monkeypatch,
                                                             capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/overrides.json").write_text("{not json")
    out = apply_availability(_pred(), _avail(), overrides=True)
    assert out["p_play"].iloc[0] == pytest.approx(0.2)
    assert "overrides" in capsys.readouterr().out


def test_the_flag_off_means_no_read_and_no_marker(tmp_path, monkeypatch):
    """G3: not "read it and ignore it" — the store is never opened, and the
    artifact carries no marker."""
    from gaffer import overrides as overrides_mod
    from gaffer.artifacts import load_availability, save_availability

    _client(tmp_path, monkeypatch, overrides=False)
    overrides_mod.set_override(1, p_play=1.0, known_codes=CODES)
    reads = []
    monkeypatch.setattr(overrides_mod, "load_overrides",
                        lambda: reads.append(1) or {})
    out = apply_availability(_pred(), _avail())
    assert reads == []
    assert out["p_play"].iloc[0] == pytest.approx(0.2)
    save_availability(_avail(), 5)
    assert not load_availability(5)["override"].any()


def test_an_override_on_an_unknown_code_is_rejected(tmp_path, monkeypatch):
    from gaffer.errors import GafferError
    from gaffer.overrides import set_override

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(4242, p_play=1.0, known_codes=CODES)


def test_a_pin_is_applied_to_both_availability_arms(tmp_path, monkeypatch):
    """A1, stated as a rail. ``predict_components`` runs this function twice —
    news and flags-only — and cannot tell the calls apart, so the pin lands on
    both and the shadow log records no *news* effect for that player. The
    alternative would have the log credit the news layer with a move the user
    made."""
    from gaffer.overrides import set_override

    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    news_frame = _avail().assign(injury_type="knock", p_start_hint=0.3,
                                 absence_damp=0.5, source="news")
    news = apply_availability(_pred(), news_frame, overrides=True)
    flags = apply_availability(_pred(), _avail(), overrides=True)
    assert news["p_play"].iloc[0] == flags["p_play"].iloc[0] == 1.0


def test_the_override_pass_runs_last(tmp_path, monkeypatch):
    """Source-level, because ordering is the whole contract and an
    arithmetic test can only catch the cases somebody thought of."""
    source = inspect.getsource(apply_availability)
    tail = source.index("_override_first_gw(out)")
    for earlier in ("_gate_first_gw", "_damp_first_gw", "_floor_first_gw",
                    "_presser_first_gw"):
        assert source.index(earlier) < tail


def test_the_two_override_column_lists_agree():
    """``artifacts`` restates the names because ``overrides`` imports it;
    this is what stops the restatement drifting."""
    from gaffer.artifacts import AVAILABILITY_COLS, OVERRIDE_COLS
    from gaffer.overrides import OVERRIDE_COLS as SOURCE

    assert OVERRIDE_COLS == SOURCE
    assert AVAILABILITY_COLS[-4:] == SOURCE


def test_the_snapshot_log_carries_the_same_columns():
    from gaffer.artifacts import AVAILABILITY_COLS
    from gaffer.snapshot import SNAPSHOT_COLS

    assert SNAPSHOT_COLS == ["season", "gw", "snap_date"] + AVAILABILITY_COLS


# --- the API with nothing on disk -------------------------------------


def test_every_new_endpoint_is_a_200_on_an_empty_machine(tmp_path,
                                                         monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for path in ("/api/overrides", "/api/sensitivity", "/api/drafts"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_an_empty_machine_serves_empty_states(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/overrides").json()["rows"] == []
    assert client.get("/api/sensitivity").json()["available"] is False
    assert client.get("/api/drafts").json()["drafts"] == []


def test_corrupt_stores_read_as_empty_rather_than_500(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for name in ("overrides.json", "drafts.json", "sensitivity_gw5.json"):
        (tmp_path / "reports" / name).write_text("{not json")
    assert client.get("/api/overrides").json()["rows"] == []
    assert client.get("/api/drafts").json()["drafts"] == []
    assert client.get("/api/sensitivity").json()["available"] is False


def test_comparing_drafts_with_no_solve_state_is_a_422_not_a_500(tmp_path,
                                                                 monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/drafts/compare", json={"names": []})
    assert response.status_code == 422
    assert "advise" in str(response.json()["detail"])


# --- the pins ---------------------------------------------------------


def test_the_job_kind_count_is_pinned():
    """Lockstep with ``frontend/src/types.ts``. 9 -> 10: v8e added the
    ``sensitivity`` kind on both sides."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 10
    assert "sensitivity" in JOB_KINDS


def test_the_protected_seams_are_imported_not_copied():
    """Spec §2: the sweep, the solver and the plan summary are used through
    their public names. A second implementation of any of them would pass
    review and disagree with the advice a week later."""
    from gaffer import sensitivity
    from gaffer.web.routers import drafts

    source = inspect.getsource(sensitivity)
    assert "from gaffer.optimize.scenarios import" in source
    assert "def run_scenarios" not in source
    assert "def move_frequencies" not in source

    drafts_source = inspect.getsource(drafts)
    assert "from gaffer.web.routers.whatif import _summary, _validate" \
        in drafts_source
    assert "def _summary" not in drafts_source


def test_the_board_building_idiom_is_the_same_in_all_four_places():
    """``whatif``, ``meta``, ``sensitivity`` and ``drafts`` all re-solve the
    saved state, and all four must price it identically (plan A7)."""
    from gaffer import sensitivity
    from gaffer.web.routers import drafts, meta, whatif

    for source in (inspect.getsource(whatif.solve_whatif),
                   inspect.getsource(meta.chips_plan),
                   inspect.getsource(sensitivity.run_sensitivity),
                   inspect.getsource(drafts.compare_drafts)):
        assert "solve_kw_from_state(state)" in source


def test_the_sweep_is_seeded_and_reproducible():
    assert "seed" in inspect.signature(
        __import__("gaffer.sensitivity", fromlist=["x"]).run_sensitivity
    ).parameters


def test_nothing_this_cycle_writes_outside_reports(tmp_path, monkeypatch):
    """Every v8e store is a report. Nothing lands in data/, models/ or logs/."""
    from gaffer.drafts import drafts_path
    from gaffer.overrides import overrides_path
    from gaffer.sensitivity import sensitivity_path

    monkeypatch.chdir(tmp_path)
    for path in (overrides_path(), drafts_path(), sensitivity_path(5)):
        assert path.parent.name == "reports"


def test_v8e_adds_exactly_one_config_key():
    import gaffer.config as config_mod

    source = inspect.getsource(config_mod)
    assert "news_overrides" in source
    for absent in ("sensitivity_", "drafts_", "chip_sanity"):
        assert absent not in source


def test_the_v8d_live_path_is_untouched(tmp_path, monkeypatch):
    """The cycle's blast radius, stated: nothing here is in the live path."""
    import gaffer.live_gw as live_gw

    assert "override" not in inspect.getsource(live_gw)
