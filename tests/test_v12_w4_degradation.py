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
import subprocess

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


# --- Block 2: §5.2's features on a machine with no collection ------------

def test_the_arms_are_all_missing_and_never_zero_without_a_collection(clone):
    """The state every machine is in until `gaffer core-insights` runs.
    Missing, not zero: zero would claim we know the defender never crosses and
    the club plays nothing that week."""
    from gaffer.features.engineer import add_density_pub, add_role_wb_share

    rows = pd.DataFrame({"season_idx": [3], "gw": [6], "code": [1],
                         "team_code": [8], "position": ["DEF"],
                         "kickoff_time": [pd.Timestamp("2026-10-10T14:00Z")]})
    out = add_density_pub(add_role_wb_share(rows, None), None)
    assert out["role_wb_share"].isna().all()
    assert out["density_pub_7d"].isna().all()
    assert out["role_wb_missing"].tolist() == [1.0]
    assert out["density_pub_missing"].tolist() == [1.0]


def test_role_is_fed_to_the_minutes_head_and_density_is_not(clone):
    """CONVENTIONS §2: pre-registered means off until the gate says on, and
    the §5.2 gate said on for one arm of the two (run 2026-09-03, window
    ``train_max_idx=2`` / ``test_idx=3``).

    Half (a): baseline starters ``p_start`` log-loss 0.43723 / zeros 0.917;
    ``role`` 0.42889 (−1.907%) / zeros 0.919 (+0.002) — keep; ``density``
    0.43584 (−0.318%) / zeros 0.923 (+0.006) — withdraw. Half (b), over the
    15 autosub weeks of 38: role +0.133, density +0.333, both passing. Role
    holds both halves; density fails (a). **Role ships on, density is
    withdrawn** and stays built on both seams, fed to no head.

    The degradation claim is the one this file exists for: on a clone that
    has never collected, ``role_wb_share`` is all-missing and
    ``role_wb_missing`` is 1.0, so a *shipped* column changes nothing about
    what a cold machine can answer.
    """
    from gaffer.features.engineer import (DENSITY_FEATURES, ROLE_FEATURES,
                                          feature_columns)
    from gaffer.models.train import MINUTES_FEATURES

    for name in ROLE_FEATURES + DENSITY_FEATURES:
        assert name in feature_columns()
    for name in ROLE_FEATURES:
        assert name in MINUTES_FEATURES
    for name in DENSITY_FEATURES:
        assert name not in MINUTES_FEATURES


# --- Block 2: §5.3 on a cold clone ---------------------------------------

def test_the_field_panel_on_a_cold_clone_is_nulls_with_reasons(clone):
    from gaffer.league_sim import Entry, SimInputs, simulate_field_rank

    ins = SimInputs(entries=[Entry(entry=1, name="me", total=0, picks=[],
                                   is_me=True)],
                    ep_by_element={}, sigma_by_element={}, weeks_left=10)
    out = simulate_field_rank(ins, {}, n=100, seed=1, gw=6)
    assert out["p_green"] is None and out["waiting_for"]
    assert out["p_top10k"] is None and out["top10k_waiting_for"]


def test_the_rank_slope_on_a_cold_clone_names_its_condition(clone):
    from gaffer.league_sim import rank_slope

    out = rank_slope([])
    assert out["slope"] is None
    assert "0 of 5 graded gameweeks" in out["waiting_for"]


def test_the_field_simulation_reaches_no_solver_and_no_advice(clone):
    """league_sim's standing rail (its module docstring, spec D4): nothing
    here is part of advice."""
    import inspect

    from gaffer import league_sim

    src = inspect.getsource(league_sim.simulate_field_rank)
    for forbidden in ("solve_plan", "run_advise", "coherent_plan", "milp"):
        assert forbidden not in src


def test_the_existing_league_simulation_is_untouched_by_the_new_one(clone):
    """§5.3 extends the module and changes nothing in it."""
    import numpy as np

    from gaffer.league_sim import Entry, SimInputs, simulate_league

    picks = [{"element": e, "position": i + 1, "multiplier": 1,
              "is_captain": i == 0, "is_vice_captain": i == 1}
             for i, e in enumerate(range(1, 12))]
    ins = SimInputs(
        entries=[Entry(entry=1, name="me", total=100, picks=picks,
                       is_me=True),
                 Entry(entry=2, name="rival", total=90, picks=picks)],
        ep_by_element={e: 4.0 for e in range(1, 12)},
        sigma_by_element={e: 3.0 for e in range(1, 12)}, weeks_left=5)
    a = simulate_league(ins, n=500, seed=42)
    b = simulate_league(ins, n=500, seed=42)
    assert a.p_win == b.p_win
    assert np.isfinite(a.exp_finish)


# --- Block 2: §5.4's byte-identical no-file rail -------------------------

def test_no_override_file_leaves_the_penalty_term_exactly_as_it_was(clone):
    import pandas as pd

    from gaffer.set_pieces import PenPriors, pen_table

    comp = pd.DataFrame({"code": [1], "team_code": [3], "position": ["MID"],
                         "p_play": [0.9]})
    players = pd.DataFrame({"code": [1], "name": ["A"],
                            "penalties_order": [1]})
    table = pen_table(comp, players,
                      PenPriors(share_hist={}, league_pens_pg=0.13,
                                team_games=100))
    assert table["share_now"].tolist() == [1.0]


def test_a_half_edited_override_file_is_no_override_at_all(clone):
    """A hand-edited file is exactly the kind of thing that is half-edited at
    11pm on a Friday, and half a file must never be half a model."""
    import pandas as pd

    from gaffer.data.set_piece_overrides import penalty_order_overrides

    (clone / "data" / "set_pieces.toml").write_text("[Arsenal]\npenalties = [1,")
    assert penalty_order_overrides() == {}


def test_the_badge_is_empty_without_a_file(clone):
    from gaffer.web.routers.players import set_piece_manual

    assert set_piece_manual() == {}


# =====================================================================
# Block 3 — the protected-diff audit
# =====================================================================

# v12 W4 (orchestrator ruling 2026-09-03, carried from W3's). A workstream's
# audit rail measures that workstream's own range and nobody else's. The base
# is pinned rather than computed from ``merge-base(HEAD, main)``, which moves
# the moment W4 merges and would start auditing whatever is cut next; the end
# is ``HEAD`` while the cycle runs and the gate commit pins ``W4_TIP`` at
# close, exactly as W3's rail was closed at f903959 once W4 was cut from it.
W3_TIP = "f903959"
"""W3's merge tip on main — W4's point of departure."""

W4_AUTHORIZED = {
    # The one STOP this workstream enumerates (plan header; spec §5.4).
    "src/gaffer/set_pieces.py",                 # T17 — the pen_table read hook
    # The orchestrator's 2026-09-03 ruling: W3's rail had an open-ended range
    # and was auditing W4's diff under W3's name, so W4 re-pinned its end.
    "tests/test_v12_w3_degradation.py",
}


def _protected(path: str) -> bool:
    return (path in {"src/gaffer/advise.py", "src/gaffer/set_pieces.py",
                     "src/gaffer/web/jobs.py",
                     "src/gaffer/web/routers/whatif.py",
                     "tests/test_advise.py", "tests/test_odds.py",
                     "tests/test_web_jobs.py", "scripts/s2_replay.py"}
            or path.startswith("src/gaffer/optimize/")
            or (path.startswith("tests/test_") and path.endswith(
                "_degradation.py")
                and path != "tests/test_v12_w4_degradation.py"))


def test_every_protected_file_w4_touched_was_authorized():
    """The audit, as a test rather than as a step somebody remembers to run.

    W4 enumerates exactly one protected edit — ``set_pieces.py``'s read hook —
    plus the one re-pin the orchestrator authorized on W3's rail, so a hit on
    ``advise.py``, ``optimize/**``, ``web/jobs.py``, ``routers/whatif.py``,
    ``test_advise.py``, ``test_odds.py``, ``test_web_jobs.py``,
    ``s2_replay.py`` or any other cycle's degradation file fails here.

    Either end unreachable — a shallow clone, an export, a tree with no git at
    all — and the audit is skipped rather than answered from a range that does
    not exist.
    """
    probe = subprocess.run(["git", "cat-file", "-e", f"{W3_TIP}^{{commit}}"],
                           capture_output=True, check=False)
    if probe.returncode:
        pytest.skip(f"{W3_TIP} unreachable — W4's range is not in this tree")
    changed = subprocess.run(["git", "diff", "--name-only", W3_TIP, "HEAD"],
                             capture_output=True, text=True,
                             check=False).stdout.split()
    touched = {p for p in changed if _protected(p)}
    assert not touched - W4_AUTHORIZED
    # And not vacuous: the STOP is supposed to have moved that file, so a
    # range that comes back empty — a rebase, a squash, a mis-typed SHA —
    # fails here rather than passing as "clean".
    assert "src/gaffer/set_pieces.py" in touched


def test_the_branch_banks_no_data_and_no_config():
    """CONVENTIONS §8: a staged ``config.toml`` or a parquet under ``data/``
    is a private tree in a public branch, and every one of them got there by
    an ``add -A`` somebody was in a hurry to type. W4 collects an archive into
    ``data/core_insights/`` and reads a hand-edited ``data/set_pieces.toml``,
    so this cycle has two more ways than usual to commit one by accident."""
    probe = subprocess.run(["git", "cat-file", "-e", f"{W3_TIP}^{{commit}}"],
                           capture_output=True, check=False)
    if probe.returncode:
        pytest.skip(f"{W3_TIP} unreachable — W4's range is not in this tree")
    changed = subprocess.run(["git", "diff", "--name-only", W3_TIP, "HEAD"],
                             capture_output=True, text=True,
                             check=False).stdout.split()
    assert not [p for p in changed
                if p == "config.toml" or p.startswith("data/")
                or p.startswith("reports/") or p.startswith("logs/")
                or p.startswith("models/")]
