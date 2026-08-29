"""GET /api/components/{gw} — the per-player EP decomposition."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import COMPONENT_COLS, save_components
from gaffer.web.app import create_app


def _row(code: int, name: str, gw: int = 5, opp: str = "ARS",
         ep: float = 6.4, pen: float = 0.0) -> dict:
    row = {c: 0.0 for c in COMPONENT_COLS}
    row.update({"code": code, "element": code, "name": name,
                "position": "MID", "team_code": 14, "team_name": "Liverpool",
                "gw": gw, "opp_code": 3, "opp_name": opp, "was_home": 1.0,
                "kickoff_time": "2026-09-05T14:00:00Z",
                "p_play": 0.96, "p60": 0.9, "ep_minutes": 1.9,
                "ep_goals": 2.6, "ep_assists": 1.0, "ep_bonus": 0.6,
                "ep_cards": -0.05, "ep_pen_taker": pen, "ep": ep})
    return row


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def _write(tmp_path, rows):
    (tmp_path / "reports").mkdir(exist_ok=True)
    save_components(pd.DataFrame(rows)[COMPONENT_COLS], 5)


def test_components_without_a_run_is_a_friendly_404(client):
    response = client.get("/api/components/5")
    assert response.status_code == 404
    assert "gaffer advise" in response.json()["detail"]


def test_components_returns_one_entry_per_player(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah"), _row(101, "Wirtz", ep=5.2)])
    body = client.get("/api/components/5").json()
    assert body["gw"] == 5
    by_code = {p["code"]: p for p in body["players"]}
    assert by_code[100]["name"] == "Salah"
    assert by_code[100]["ep"] == 6.4
    assert by_code[101]["ep"] == 5.2


def test_a_double_gameweek_sums_its_fixtures_and_keeps_both(client, tmp_path):
    """The decomposition is per fixture; the headline number is the sum, and
    the page shows both because "why 11 points?" is answered by the two
    opponents as much as by the terms."""
    _write(tmp_path, [_row(100, "Salah", opp="ARS", ep=6.4),
                      _row(100, "Salah", opp="EVE", ep=4.6)])
    player = client.get("/api/components/5").json()["players"][0]
    assert player["ep"] == 11.0
    assert [f["opponent"] for f in player["fixtures"]] == ["ARS", "EVE"]


def test_each_fixture_carries_its_additive_terms(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah", pen=0.31)])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    labels = {c["label"]: c["points"] for c in fixture["components"]}
    assert labels["Goals"] == 2.6
    assert labels["Minutes"] == 1.9
    assert fixture["minutes"]["p_play"] == 0.96
    assert fixture["home"] is True


def test_the_listed_terms_sum_to_the_expected_points(client, tmp_path):
    """The panel's whole promise. Penalty duty was listed as a thirteenth
    additive row while already sitting inside Goals, so the one player anyone
    would check was the one whose terms did not add up."""
    # 1.9 + 2.6 + 1.0 + 0.6 - 0.05, with the 0.31 of penalty duty already
    # inside the 2.6 of goals.
    _write(tmp_path, [_row(100, "Salah", pen=0.31, ep=6.05)])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    total = sum(c["points"] for c in fixture["components"])
    assert total == pytest.approx(fixture["ep"], abs=0.01)


def test_penalty_duty_rides_along_as_an_annotation_not_a_term(client,
                                                              tmp_path):
    """It is already folded into e_goals, so it is reported beside the terms
    rather than among them — the panel prints it under Goals."""
    _write(tmp_path, [_row(100, "Salah", pen=0.31)])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    assert fixture["pen_taker"] == 0.31
    assert all(c["label"] != "Penalty duty"
               for c in fixture["components"])


def test_a_player_with_no_penalty_duty_carries_no_annotation(client,
                                                             tmp_path):
    """None rather than 0.0: 700 of 750 players have no term at all, and the
    panel has to tell that from a term that rounded away."""
    _write(tmp_path, [_row(100, "Salah", pen=0.0)])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    assert fixture["pen_taker"] is None


def test_a_zero_term_is_left_out_of_the_breakdown(client, tmp_path):
    """A row of zeroes is noise in a panel whose whole job is showing what
    moved."""
    _write(tmp_path, [_row(100, "Salah")])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    assert all(c["points"] != 0.0 for c in fixture["components"])


def test_a_missing_opponent_or_club_reads_as_blank_not_as_nan(client,
                                                              tmp_path):
    """A float NaN is truthy, so ``str(value or "")`` printed the word "nan"
    at the reader. The row is right to survive a failed join; it has to
    survive it as an empty string."""
    row = _row(100, "Salah")
    row["opp_name"] = float("nan")
    row["team_name"] = float("nan")
    _write(tmp_path, [row])
    player = client.get("/api/components/5").json()["players"][0]
    assert player["team_name"] == ""
    assert player["fixtures"][0]["opponent"] == ""


def test_components_can_be_filtered_to_the_codes_the_page_shows(client,
                                                                tmp_path):
    """This Week expands XI, bench, buys and sells — about twenty players out
    of a 750-row file."""
    _write(tmp_path, [_row(100, "Salah"), _row(101, "Wirtz"),
                      _row(102, "Nobody")])
    body = client.get("/api/components/5?codes=100,102").json()
    assert sorted(p["code"] for p in body["players"]) == [100, 102]


def test_an_unknown_code_in_the_filter_is_simply_absent(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah")])
    body = client.get("/api/components/5?codes=100,999").json()
    assert [p["code"] for p in body["players"]] == [100]


# --- expected minutes -------------------------------------------------------
#
# The This Week squad table has an xMin column and the payload had nothing to
# fill it with, so every row printed an em dash. Derived here rather than in
# the browser: it is a statement about the minutes model, not a display choice.


def test_a_fixture_carries_derived_expected_minutes(client, tmp_path):
    _write(tmp_path, [_row(100, "Salah")])
    fixture = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]
    # p_play * (45 + 45 * p60): 45 minutes for turning up, 45 more for the
    # hour he is likely to see out.
    assert fixture["minutes"]["xmins"] == round(0.96 * (45 + 45 * 0.9), 1)


def test_expected_minutes_span_the_bench_and_the_nailed_on(client, tmp_path):
    rows = [_row(100, "Nailed"), _row(101, "Doubt")]
    rows[0].update(p_play=1.0, p60=1.0)
    rows[1].update(p_play=0.0, p60=0.0)
    _write(tmp_path, rows)
    by_code = {p["code"]: p for p in client.get("/api/components/5").json()[
        "players"]}
    assert by_code[100]["fixtures"][0]["minutes"]["xmins"] == 90.0
    assert by_code[101]["fixtures"][0]["minutes"]["xmins"] == 0.0


def test_a_missing_minutes_probability_is_no_estimate_at_all(client, tmp_path):
    """An un-modelled player is not a player expected to play zero minutes,
    and the column should say nothing rather than something false."""
    row = _row(100, "Salah")
    row.update(p_play=None, p60=None)
    _write(tmp_path, [row])
    minutes = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]["minutes"]
    assert minutes["xmins"] is None


def test_a_half_missing_minutes_model_still_declines_to_guess(client, tmp_path):
    row = _row(100, "Salah")
    row.update(p60=None)
    _write(tmp_path, [row])
    minutes = client.get("/api/components/5").json()["players"][0][
        "fixtures"][0]["minutes"]
    assert minutes["xmins"] is None
    # The probabilities themselves still read as the zeroes they degrade to.
    assert minutes["p_play"] == 0.96
