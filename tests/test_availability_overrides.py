"""The override pass: the user's pin, applied last and applied whole.

Ordering is the whole subject. Every automated pass — the flag factor, the
horizon relax, the line-up ceiling, the absence damp, the classifier — runs
first, and then the pin overwrites whatever they concluded, because a manager
who has decided a player is fit is not asking for a weighted average with a
website. These tests are mostly about *last*.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.models.availability import apply_availability
from gaffer.overrides import set_override

CODES = [1, 2]


def _pred(gws=(5,)):
    """One row per (player, gameweek), the shape predict_components hands in."""
    rows = []
    for code in CODES:
        for gw in gws:
            rows.append({"code": code, "gw": gw, "p_play": 0.8, "p60": 0.6,
                         "e_min": 60.0})
    return pd.DataFrame(rows)


def _avail(status="a", chance=None):
    return pd.DataFrame({"code": CODES, "status": [status, "a"],
                         "chance_of_playing": [chance, None]})


def test_with_the_flag_off_nothing_is_read_and_nothing_changes(tmp_path,
                                                               monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(), overrides=False)
    assert out.loc[out["code"] == 1, "p_play"].iloc[0] == pytest.approx(0.8)
    assert not [c for c in out.columns if c.startswith("override")]


def test_an_empty_store_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    on = apply_availability(_pred(), _avail(), overrides=True)
    off = apply_availability(_pred(), _avail(), overrides=False)
    pd.testing.assert_frame_equal(on, off)


def test_a_pin_overrides_the_official_flag(tmp_path, monkeypatch):
    """The case the feature exists for: FPL says 25%, the user saw him train."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(status="d", chance=25.0),
                             overrides=True)
    mine = out[out["code"] == 1].iloc[0]
    # The flag factor is 0.25, so the model reached p_play 0.2, p60 0.15,
    # e_min 15. The pin takes p_play to 1.0 — a ratio of 5 — and A2 carries
    # the other two up with it.
    assert mine["p_play"] == pytest.approx(1.0)
    assert mine["p60"] == pytest.approx(0.75)
    assert mine["e_min"] == pytest.approx(75.0)
    assert out[out["code"] == 2]["p_play"].iloc[0] == pytest.approx(0.8)


def test_a_pin_beats_the_lineup_ceiling(tmp_path, monkeypatch):
    """v8a's hint is a ceiling on the model. The pin is a ceiling on the
    ceiling, and it runs after it."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=0.9, known_codes=CODES)
    avail = _avail()
    avail["p_start_hint"] = [0.0, 1.0]
    out = apply_availability(_pred(), avail, overrides=True)
    assert out[out["code"] == 1]["p_play"].iloc[0] == pytest.approx(0.9)


def test_a_pin_beats_the_absence_damp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    avail = _avail()
    avail["absence_damp"] = [0.75, 1.0]
    out = apply_availability(_pred(), avail, overrides=True)
    assert out[out["code"] == 1]["p_play"].iloc[0] == pytest.approx(1.0)


def test_a_pin_on_a_zeroed_player_is_taken_literally(tmp_path, monkeypatch):
    """A2: there is no ratio to scale by, and the user pinning a suspended
    player to 1.0 is saying he starts and he lasts."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(status="s"), overrides=True)
    mine = out[out["code"] == 1].iloc[0]
    assert mine["p_play"] == pytest.approx(1.0)
    assert mine["p60"] == pytest.approx(1.0)
    assert mine["e_min"] == pytest.approx(90.0)


def test_an_e_min_pin_is_absolute_and_runs_after_the_p_play_ratio(tmp_path,
                                                                  monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, e_min=30.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(), overrides=True)
    mine = out[out["code"] == 1].iloc[0]
    assert mine["p_play"] == pytest.approx(1.0)
    assert mine["e_min"] == pytest.approx(30.0)


def test_a_pin_bites_the_first_gameweek_only(tmp_path, monkeypatch):
    """The same rule every other pass obeys: a claim about Saturday says
    nothing about the Wednesday after."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(gws=(5, 6)), _avail(status="d",
                                                       chance=25.0),
                             overrides=True)
    mine = out[out["code"] == 1].sort_values("gw")
    assert mine["p_play"].iloc[0] == pytest.approx(1.0)
    assert mine["p_play"].iloc[1] < 1.0


def test_a_double_gameweek_is_pinned_once(tmp_path, monkeypatch):
    """_first_rows' one-row-per-player rule: a pin is one claim about the
    player, not one claim per fixture."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    pred = pd.concat([_pred(), _pred()], ignore_index=True).sort_values(
        ["code", "gw"]).reset_index(drop=True)
    out = apply_availability(pred, _avail(status="d", chance=25.0),
                             overrides=True)
    pinned = out[(out["code"] == 1)]["p_play"].tolist()
    assert sum(1 for v in pinned if v == pytest.approx(1.0)) == 1


def test_the_override_columns_never_reach_the_component_frame(tmp_path,
                                                              monkeypatch):
    """Same discipline as every news column: applied, then dropped."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(), overrides=True)
    assert not [c for c in out.columns if c.startswith("override")]


def test_the_artifact_carries_the_marker(tmp_path, monkeypatch):
    from gaffer.artifacts import load_availability, save_availability

    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, note="fit", known_codes=CODES)
    save_availability(_avail(), 5)
    banked = load_availability(5)
    row = banked[banked["code"] == 1].iloc[0]
    assert bool(row["override"]) is True
    assert row["override_p_play"] == 1.0
    assert row["override_note"] == "fit"
    assert not bool(banked[banked["code"] == 2].iloc[0]["override"])


def test_the_daily_snapshot_carries_the_marker(tmp_path, monkeypatch):
    from gaffer.snapshot import SNAPSHOT_COLS, snapshot_rows

    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    rows = snapshot_rows(_avail(), gw=5, season="2026-27", day="2026-08-31")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert bool(rows[rows["code"] == 1].iloc[0]["override"]) is True


def test_a_flags_only_week_still_writes_the_override_schema(tmp_path,
                                                            monkeypatch):
    """A4: the columns exist whether or not a feed ran and whether or not
    anybody pinned anything, so one parquet schema covers every week."""
    from gaffer.artifacts import OVERRIDE_COLS, load_availability, \
        save_availability

    monkeypatch.chdir(tmp_path)
    save_availability(_avail(), 5)
    banked = load_availability(5)
    assert set(OVERRIDE_COLS) <= set(banked.columns)
    assert not banked["override"].fillna(False).any()
