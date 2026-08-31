"""``reports/overrides.json``: the user's own team news.

The store is the only place in the tool where a human number outranks a model
one, so it is also the only place that has to be paranoid about what it will
accept. Everything here is about refusal: an unknown code, a probability
outside [0, 1], minutes outside [0, 90], a pin that says nothing at all.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.errors import GafferError
from gaffer.overrides import (attach_overrides, delete_override,
                              load_overrides, overrides_path, set_override)

KNOWN = [11, 22, 33]


def test_an_absent_store_is_an_empty_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_overrides() == {}


def test_a_corrupt_store_is_an_empty_one_and_says_so(tmp_path, monkeypatch,
                                                     capsys):
    """A hand-edited file must not take the advise run down with it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    overrides_path().write_text("{not json")
    assert load_overrides() == {}
    assert "overrides" in capsys.readouterr().out


def test_setting_a_pin_round_trips_through_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, note="fit, saw him train",
                 known_codes=KNOWN, model_p_play=0.82)
    stored = load_overrides()
    assert set(stored) == {22}
    assert stored[22]["p_play"] == 1.0
    assert stored[22]["e_min"] is None
    assert stored[22]["note"] == "fit, saw him train"
    assert stored[22]["model_p_play"] == 0.82
    assert stored[22]["set_at"].startswith("20")


def test_the_file_is_json_with_string_keys(tmp_path, monkeypatch):
    """JSON object keys are strings; the loader is what makes them ints
    again, and a caller looking one up by code must never silently miss."""
    monkeypatch.chdir(tmp_path)
    set_override(22, e_min=90.0, known_codes=KNOWN)
    raw = json.loads(overrides_path().read_text())
    assert list(raw["overrides"]) == ["22"]
    assert 22 in load_overrides()


def test_an_unknown_code_is_refused_with_a_readable_message(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        set_override(999, p_play=1.0, known_codes=KNOWN)
    assert "999" in str(exc.value)
    assert not overrides_path().exists()


def test_a_pin_that_claims_nothing_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(22, known_codes=KNOWN)


@pytest.mark.parametrize("kwargs", [
    {"p_play": 1.5}, {"p_play": -0.1}, {"e_min": 91.0}, {"e_min": -1.0},
    {"p_play": float("nan")},
])
def test_values_outside_their_range_are_refused(tmp_path, monkeypatch,
                                                kwargs):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(22, known_codes=KNOWN, **kwargs)


def test_a_long_note_is_refused_rather_than_silently_truncated(tmp_path,
                                                              monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(22, p_play=1.0, note="x" * 500, known_codes=KNOWN)


def test_repinning_keeps_the_first_model_reading(tmp_path, monkeypatch):
    """A3: the second reading is the first pin looking at itself."""
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, known_codes=KNOWN, model_p_play=0.82)
    set_override(22, p_play=0.5, known_codes=KNOWN, model_p_play=1.0)
    stored = load_overrides()[22]
    assert stored["p_play"] == 0.5
    assert stored["model_p_play"] == 0.82


def test_deleting_a_pin_leaves_the_others(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(11, p_play=0.0, known_codes=KNOWN)
    set_override(22, p_play=1.0, known_codes=KNOWN)
    assert delete_override(11) is True
    assert set(load_overrides()) == {22}
    assert delete_override(11) is False


def test_the_store_is_capped(tmp_path, monkeypatch):
    from gaffer.overrides import MAX_OVERRIDES

    monkeypatch.chdir(tmp_path)
    codes = list(range(1, MAX_OVERRIDES + 2))
    for code in codes[:MAX_OVERRIDES]:
        set_override(code, p_play=1.0, known_codes=codes)
    with pytest.raises(GafferError):
        set_override(codes[-1], p_play=1.0, known_codes=codes)


# --- attach_overrides -------------------------------------------------

FRAME = pd.DataFrame({"code": [11, 22, 33], "status": ["a", "d", "a"],
                      "chance_of_playing": [None, 25.0, None]})


def test_attach_adds_the_four_columns_even_with_no_pins(tmp_path,
                                                        monkeypatch):
    """The schema must not depend on whether anybody pinned anything."""
    monkeypatch.chdir(tmp_path)
    out = attach_overrides(FRAME)
    assert list(out.columns[-4:]) == ["override", "override_p_play",
                                      "override_e_min", "override_note"]
    assert not out["override"].any()
    assert out["override_p_play"].isna().all()


def test_attach_marks_only_the_pinned_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, e_min=80.0, note="fit", known_codes=KNOWN)
    out = attach_overrides(FRAME)
    row = out[out["code"] == 22].iloc[0]
    assert bool(row["override"]) is True
    assert row["override_p_play"] == 1.0
    assert row["override_e_min"] == 80.0
    assert row["override_note"] == "fit"
    assert not out[out["code"] == 11].iloc[0]["override"]


def test_attach_is_idempotent(tmp_path, monkeypatch):
    """The availability pass and the artifact writer both call it; the second
    call must not re-read the store or double a column."""
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, known_codes=KNOWN)
    once = attach_overrides(FRAME)
    twice = attach_overrides(once)
    assert list(twice.columns) == list(once.columns)
    pd.testing.assert_frame_equal(once, twice)


def test_attach_leaves_the_callers_frame_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, known_codes=KNOWN)
    attach_overrides(FRAME)
    assert "override" not in FRAME.columns


def test_attach_survives_a_frame_with_no_code_column(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({"element": [1, 2]})
    assert attach_overrides(frame) is frame
