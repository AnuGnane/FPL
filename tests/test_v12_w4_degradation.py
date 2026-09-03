"""v12 W4's degradation rails and its three pins.

Every rail is a state a real machine reaches, and the first four are the state
*every* machine is in today: no collection on a fresh clone, an archive whose
2026-27 Elo column is blank, a season (2022-23, 2023-24) the archive has never
published, and a player-match schema that differs between the seasons it has
(``defensive_contributions`` is in two of three).

The schema-drift rails are not hypothetical. They were written from the live
archive, measured 2026-09-02 and transcribed in the W4 plan's Appendix A.
"""

from __future__ import annotations

import dataclasses

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import Config
from gaffer.data import store
from gaffer.data.core_insights import (CI_ELO_COLS, CI_FIXTURE_COLS,
                                       CI_PLAYER_COLS, ci_path,
                                       download_core_insights,
                                       load_core_insights,
                                       season_table_stats)
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS

PLAYERS_CSV = ("player_code,player_id,first_name,second_name,web_name,"
               "team_code,position\n208706,452,Bruno,G,Bruno G.,3,Midfielder\n")

PMS_CSV = ("player_id,match_id,minutes_played,accurate_crosses,"
           "touches_opposition_box,final_third_passes,tackles_won,"
           "interceptions,blocks,clearances,recoveries,start_min,finish_min,"
           "defensive_contributions\n"
           "452,m1,90,2,4,11,3,1,0,2,7,0,90,6\n")

FIXTURES_CSV = ("gameweek,kickoff_time,home_team,home_team_elo,home_score,"
                "away_score,away_team,away_team_elo,finished,match_id,"
                "tournament\n"
                "2,2026-08-30T13:00:00,2.0,1801.5,1,1,94.0,1750.25,True,"
                "m1,prem\n")

ARCHIVE = {"data/2026-2027/players.csv": PLAYERS_CSV,
           "data/2026-2027/By Gameweek/GW2/playermatchstats.csv": PMS_CSV,
           "data/2026-2027/By Gameweek/GW2/fixtures.csv": FIXTURES_CSV}


def _tree(paths) -> dict:
    return {"tree": [{"path": p, "type": "blob"} for p in sorted(paths)]}


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeHTTP:
    def __init__(self, files):
        self.files = dict(files)

    def get(self, url, **_kw):
        path = url.split("/main/", 1)[-1]
        if path not in self.files:
            raise httpx.HTTPError(f"404 {path}")
        return _Resp(self.files[path])


class _DeadHTTP:
    def get(self, *_a, **_kw):
        raise httpx.ConnectError("no route to host")


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    """A machine with nothing collected."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    return tmp_path


# --- Block 1: the collector ----------------------------------------------

def test_an_unreachable_repo_is_a_printed_line_and_no_write(clone, capsys):
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 client=_DeadHTTP())
    assert out == {"2026-27": {"players": 0, "fixtures": 0, "elo": 0}}
    assert not store.exists(ci_path("2026-27", "players"))
    assert "unavailable" in capsys.readouterr().out


def test_an_unreachable_repo_never_truncates_a_previous_collection(clone):
    """The rail that matters most: a network blip must not delete data."""
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=_tree(ARCHIVE), client=_FakeHTTP(ARCHIVE))
    before = load_core_insights("2026-27", "players")
    assert len(before) == 1
    download_core_insights(["2026-27"], {"2026-27": 3}, client=_DeadHTTP())
    assert len(load_core_insights("2026-27", "players")) == 1


def test_an_unknown_column_added_upstream_changes_nothing(clone):
    drifted = dict(ARCHIVE)
    drifted["data/2026-2027/By Gameweek/GW2/playermatchstats.csv"] = (
        PMS_CSV.replace("player_id,", "brand_new_metric,player_id,")
        .replace("452,m1", "0.5,452,m1"))
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=_tree(drifted), client=_FakeHTTP(drifted))
    frame = load_core_insights("2026-27", "players")
    assert list(frame.columns) == CI_PLAYER_COLS
    assert len(frame) == 1
    # Not merely "the column list is unchanged": the unknown column was
    # *prepended*, so a parser that carried it through would also have shifted
    # every value one place and still produced a right-looking header. The
    # known columns have to still read what the file says.
    assert "brand_new_metric" not in frame.columns
    row = frame.iloc[0]
    assert (row["minutes_played"], row["accurate_crosses"],
            row["defensive_contributions"]) == (90.0, 2.0, 6.0)


def test_an_expected_column_removed_upstream_is_null_not_a_crash(clone,
                                                                capsys):
    """A3: the 2024-2025 layout genuinely lacks defensive_contributions."""
    drifted = dict(ARCHIVE)
    drifted["data/2026-2027/By Gameweek/GW2/playermatchstats.csv"] = (
        PMS_CSV.replace(",defensive_contributions", "").replace(",6\n", "\n"))
    download_core_insights(["2026-27"], {"2026-27": 3},
                           tree=_tree(drifted), client=_FakeHTTP(drifted))
    frame = load_core_insights("2026-27", "players")
    assert list(frame.columns) == CI_PLAYER_COLS
    assert frame["defensive_contributions"].isna().all()
    assert "does not publish" in capsys.readouterr().out


def test_a_key_column_removed_upstream_drops_the_file_not_the_run(clone):
    drifted = dict(ARCHIVE)
    drifted["data/2026-2027/By Gameweek/GW2/playermatchstats.csv"] = \
        PMS_CSV.replace("player_id,match_id,", "match_id,")
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 tree=_tree(drifted),
                                 client=_FakeHTTP(drifted))
    assert out["2026-27"]["players"] == 0
    assert out["2026-27"]["fixtures"] == 2   # the fixture file is untouched


def test_an_empty_season_writes_empty_tables_with_the_right_columns(clone):
    tree = _tree(["data/2026-2027/players.csv"])
    files = {"data/2026-2027/players.csv": PLAYERS_CSV}
    out = download_core_insights(["2026-27"], {"2026-27": 3}, tree=tree,
                                 client=_FakeHTTP(files))
    assert out["2026-27"] == {"players": 0, "fixtures": 0, "elo": 0}
    assert list(load_core_insights("2026-27", "fixtures").columns) == \
        CI_FIXTURE_COLS
    assert list(load_core_insights("2026-27", "elo").columns) == CI_ELO_COLS
    # The existence of the file *is* the "we looked and there was nothing"
    # signal — it is the only thing that separates this state from "we never
    # looked", and it is what the health line reads to say so. An empty frame
    # from load_core_insights is both states at once; the file is not.
    for table in ("players", "fixtures", "elo"):
        assert store.exists(ci_path("2026-27", table))


def test_a_season_whose_elo_column_is_blank_collects_no_elo(clone):
    """A3c: 2026-27's live archive, today."""
    blank = dict(ARCHIVE)
    blank["data/2026-2027/By Gameweek/GW2/fixtures.csv"] = \
        FIXTURES_CSV.replace("1801.5", "").replace("1750.25", "")
    out = download_core_insights(["2026-27"], {"2026-27": 3},
                                 tree=_tree(blank), client=_FakeHTTP(blank))
    assert out["2026-27"]["fixtures"] == 2
    assert out["2026-27"]["elo"] == 0
    assert season_table_stats("2026-27")["elo"] == {"rows": 0, "latest": None}


def test_another_seasons_rows_are_never_returned(clone):
    """The season guard. Element ids remap every season; a reader that
    borrowed 2025-26's rows for 2026-27 would attach one footballer's
    defensive numbers to another."""
    frame = pd.DataFrame([{**{c: 0 for c in CI_PLAYER_COLS},
                           "season": "2025-26", "code": 1}])
    store.save(frame, ci_path("2026-27", "players"))
    assert load_core_insights("2026-27", "players").empty


def test_a_torn_parquet_is_a_missing_one(clone):
    path = store.DATA_DIR / ci_path("2026-27", "players")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a parquet")
    assert load_core_insights("2026-27", "players").empty


def test_the_health_line_on_a_cold_clone_is_a_200_that_says_why(clone):
    body = TestClient(create_app()).get("/api/health").json()
    assert body["core_insights"]["collected"] is False
    assert body["core_insights"]["tables"] == []
    assert body["core_insights"]["waiting_for"]


# --- Pins (CONVENTIONS §7; the v11 values, unmoved) ----------------------

def test_the_job_kinds_are_still_twelve():
    assert len(JOB_KINDS) == 12


def test_the_config_gained_no_field():
    """By absence, not by a total. The single absolute ``fields(Config)`` pin
    lives in tests/test_v12_w3_degradation.py and a rail in
    tests/test_v12_w1_degradation.py asserts it is the only one — W4 adds no
    key, so what it owes the suite is the *claim*, not a second copy of the
    number that would have to be edited twice from now on."""
    names = {f.name for f in dataclasses.fields(Config)}
    assert not [n for n in names
                if "core_insight" in n or "set_piece" in n
                or "role_wb" in n or "density" in n]


def test_the_collector_took_no_route_of_its_own():
    """The other half, and the same reasoning: the absolute route pin is
    tests/test_v11_degradation.py's. W4's health block and its Field panel are
    additive response fields, so the claim here is that no path appeared."""
    paths = create_app().openapi()["paths"]
    assert not [p for p in paths
                if p.startswith("/api/core-insights")
                or p.startswith("/api/field")
                or p.startswith("/api/setpieces")]
