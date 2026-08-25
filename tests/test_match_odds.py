import pandas as pd
import pytest

from gaffer.data.match_odds import (FOOTBALL_DATA_ALIASES, PRICE_TRIPLES,
                                    TOTALS_PAIRS, parse_football_data,
                                    resolve_fd_team)
from gaffer.errors import GafferError


def _csv_rows(extra: dict | None = None) -> pd.DataFrame:
    """Two matches in football-data's own column vocabulary."""
    base = {
        "Date": ["16/08/2024", "17/08/2024"],
        "HomeTeam": ["Man United", "Nott'm Forest"],
        "AwayTeam": ["Wolves", "Bournemouth"],
        "AvgCH": [1.80, 2.30], "AvgCD": [3.80, 3.30], "AvgCA": [4.50, 3.20],
        "AvgC>2.5": [1.90, 2.05], "AvgC<2.5": [1.95, 1.80],
    }
    base.update(extra or {})
    return pd.DataFrame(base)


def test_resolve_fd_team_maps_football_data_short_names():
    assert resolve_fd_team("Man United") == "Man Utd"
    assert resolve_fd_team("Nott'm Forest") == "Nott'm Forest"
    assert resolve_fd_team("Wolves") == "Wolves"
    assert resolve_fd_team("Spurs") == "Spurs"


def test_resolve_fd_team_raises_on_an_unknown_name():
    """A silently mismatched club attaches one team's odds to another, which
    is far worse than losing the odds for a season."""
    with pytest.raises(GafferError) as exc:
        resolve_fd_team("Barnsley Athletic")
    assert "FOOTBALL_DATA_ALIASES" in str(exc.value)


def test_every_alias_target_is_an_fpl_bootstrap_name():
    from gaffer.data.odds import TEAM_ALIASES

    fpl_names = set(TEAM_ALIASES.values())
    unknown = sorted(set(FOOTBALL_DATA_ALIASES.values()) - fpl_names)
    assert unknown == []


def test_parse_football_data_devigs_the_closing_triple_with_shin():
    from gaffer.data.odds import shin_devig

    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    want = shin_devig([1.80, 3.80, 4.50])
    assert abs(out.loc[0, "p_home"] - want[0]) < 1e-12
    assert abs(out.loc[0, "p_draw"] - want[1]) < 1e-12
    assert abs(out.loc[0, "p_away"] - want[2]) < 1e-12
    assert abs(out.loc[0, "p_home"] + out.loc[0, "p_draw"]
               + out.loc[0, "p_away"] - 1.0) < 1e-12


def test_parse_football_data_devigs_the_totals_pair():
    from gaffer.data.odds import devig

    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    assert abs(out.loc[0, "p_over25"] - devig([1.90, 1.95])[0]) < 1e-12


def test_parse_football_data_maps_names_and_dates():
    out = parse_football_data(_csv_rows(), season="2024-25", season_idx=2)
    assert list(out["home_name"]) == ["Man Utd", "Nott'm Forest"]
    assert list(out["away_name"]) == ["Wolves", "Bournemouth"]
    assert list(out["date"]) == [pd.Timestamp("2024-08-16").date(),
                                 pd.Timestamp("2024-08-17").date()]
    assert set(out["season"]) == {"2024-25"} and set(out["season_idx"]) == {2}


def test_parse_football_data_accepts_four_digit_years_too():
    """Older seasons use dd/mm/yy, newer ones dd/mm/yyyy; both appear in the
    same archive."""
    rows = _csv_rows({"Date": ["16/08/24", "17/08/24"]})
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert out.loc[0, "date"] == pd.Timestamp("2024-08-16").date()


def test_parse_football_data_falls_back_down_the_price_chain():
    """Closing averages are the first choice; a season that predates them
    still has to parse."""
    rows = _csv_rows().drop(columns=["AvgCH", "AvgCD", "AvgCA"])
    rows["B365H"], rows["B365D"], rows["B365A"] = [1.80, 2.30], [3.80, 3.30], [4.50, 3.20]
    out = parse_football_data(rows, season="2020-21", season_idx=0)
    assert len(out) == 2
    assert out["p_home"].notna().all()


def test_parse_football_data_takes_the_first_fully_present_triple():
    """A partially-populated preferred triple must not win over a complete
    later one — half a market is not a market."""
    rows = _csv_rows()
    rows.loc[0, "AvgCH"] = float("nan")
    rows["AvgH"], rows["AvgD"], rows["AvgA"] = [1.70, 2.20], [3.90, 3.40], [4.60, 3.30]
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    from gaffer.data.odds import shin_devig
    assert abs(out.loc[0, "p_home"] - shin_devig([1.70, 3.90, 4.60])[0]) < 1e-12


def test_parse_football_data_without_any_price_triple_returns_empty():
    rows = _csv_rows().drop(columns=["AvgCH", "AvgCD", "AvgCA"])
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert out.empty
    assert list(out.columns) == ["season", "season_idx", "date", "home_name",
                                 "away_name", "p_home", "p_draw", "p_away",
                                 "p_over25"]


def test_parse_football_data_without_a_totals_pair_uses_the_neutral_prior():
    from gaffer.data.odds import NEUTRAL_P_OVER25

    rows = _csv_rows().drop(columns=["AvgC>2.5", "AvgC<2.5"])
    out = parse_football_data(rows, season="2024-25", season_idx=2)
    assert (out["p_over25"] == NEUTRAL_P_OVER25).all()


def test_parse_football_data_drops_blank_trailing_rows():
    """football-data ships trailing all-empty rows in most season files."""
    rows = _csv_rows()
    blank = pd.DataFrame([{c: float("nan") for c in rows.columns}])
    blank["HomeTeam"] = None
    out = parse_football_data(pd.concat([rows, blank], ignore_index=True),
                              season="2024-25", season_idx=2)
    assert len(out) == 2


def test_price_and_totals_preference_chains_are_ordered_closing_first():
    assert PRICE_TRIPLES[0] == ("AvgCH", "AvgCD", "AvgCA")
    assert TOTALS_PAIRS[0] == ("AvgC>2.5", "AvgC<2.5")
