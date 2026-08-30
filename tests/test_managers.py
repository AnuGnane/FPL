"""The manager-tenure asset: what it is, and what happens without it."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data.managers import (MANAGER_TENURES_PATH, TENURE_COLS,
                                  load_manager_tenures, spell_keys)

_TOML = """
[[spell]]
club = "Arsenal"
team_code = 3
manager = "Mikel Arteta"
start_date = "2019-12-20"
end_date = ""

[[spell]]
club = "Chelsea"
team_code = 8
manager = "Graham Potter"
start_date = "2022-09-08"
end_date = "2023-04-02"

[[spell]]
club = "Chelsea"
team_code = 8
manager = "Mauricio Pochettino"
start_date = "2023-04-02"
end_date = ""
"""


def _asset(tmp_path):
    dest = tmp_path / MANAGER_TENURES_PATH
    dest.write_text(_TOML, encoding="utf-8")
    return dest


def test_the_asset_reads_as_one_row_per_spell(tmp_path):
    out = load_manager_tenures(_asset(tmp_path))
    assert list(out.columns) == TENURE_COLS
    assert len(out) == 3
    assert out["team_code"].dtype == "int64"


def test_an_open_spell_has_no_end_date(tmp_path):
    out = load_manager_tenures(_asset(tmp_path))
    arteta = out[out["manager"] == "Mikel Arteta"].iloc[0]
    assert pd.isna(arteta["end_date"])


def test_an_absent_asset_is_none_not_an_empty_frame(tmp_path):
    """``None`` and "no spells" are opposite instructions to the builders:
    one says fall back to club-season windows, the other would say every club
    changed manager on every date."""
    assert load_manager_tenures(tmp_path / "nothing.toml") is None


def test_a_corrupt_asset_is_none_rather_than_a_raise(tmp_path):
    dest = tmp_path / MANAGER_TENURES_PATH
    dest.write_text("[[spell]\nbroken = ", encoding="utf-8")
    assert load_manager_tenures(dest) is None


def test_the_key_names_the_spell_the_date_sits_in(tmp_path):
    ten = load_manager_tenures(_asset(tmp_path))
    keys = spell_keys(pd.Series([8, 8]),
                      pd.Series(["2022-10-01T14:00:00Z",
                                 "2023-05-01T14:00:00Z"]),
                      pd.Series([0, 0]), ten)
    assert keys.iloc[0] != keys.iloc[1]
    assert "Potter" in keys.iloc[0]
    assert "Pochettino" in keys.iloc[1]


def test_a_club_date_no_spell_covers_falls_back_to_the_club_season(tmp_path):
    ten = load_manager_tenures(_asset(tmp_path))
    keys = spell_keys(pd.Series([99]), pd.Series(["2023-05-01T14:00:00Z"]),
                      pd.Series([2]), ten)
    assert keys.iloc[0] == "c99s2"


def test_no_asset_at_all_is_the_club_season_window_everywhere():
    keys = spell_keys(pd.Series([3, 3]),
                      pd.Series(["2023-05-01T14:00:00Z",
                                 "2024-05-01T14:00:00Z"]),
                      pd.Series([1, 2]), None)
    assert list(keys) == ["c3s1", "c3s2"]


@pytest.mark.parametrize("bad", [None, ""])
def test_a_row_without_a_team_code_is_dropped(tmp_path, bad):
    dest = tmp_path / MANAGER_TENURES_PATH
    dest.write_text(
        '[[spell]]\nclub = "X"\nmanager = "Y"\nstart_date = "2022-08-01"\n',
        encoding="utf-8")
    assert load_manager_tenures(dest) is None
