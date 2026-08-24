import json
from pathlib import Path

import pytest

from gaffer.advise import Advice
from gaffer.report.render import render_report

REAL_PAYLOAD = Path("reports/gw2-advice.json")


def _advice():
    return Advice(
        gw=3, deadline="2026-09-04T17:30:00Z",
        buys=[{"code": 20, "name": "Star", "ep": 7.5}],
        sells=[{"code": 9, "name": "Dud", "ep": 1.2}], hits=0,
        xi=[{"code": i, "name": f"P{i}", "ep": 4.0} for i in range(11)],
        bench=[{"code": i, "name": f"B{i}", "ep": 1.0} for i in range(4)],
        captain={"code": 1, "name": "P1", "ep": 8.0},
        vice={"code": 2, "name": "P2", "ep": 7.0},
        captain_options=[{"code": 1, "name": "P1", "position": "MID",
                          "ep": 8.0, "p_haul": 0.4, "league_eo": 80.0,
                          "differential": False}],
        chip_table=[{"chip": "bboost", "gw": 5, "gain": 6.2}],
        wildcard_now={"gain_over_horizon": 3.1, "recommend": False},
        alternatives=[], threats=[], price_alerts=[],
        expected_pts=61.5, plan_by_gw=[],
    )


def test_render_report_produces_html_with_key_content(tmp_path):
    path = render_report(_advice(), out_dir=tmp_path)
    html = path.read_text()
    assert "GW3" in html and "Star" in html and "Dud" in html
    assert "bboost" in html and "61.5" in html
    assert path.name == "gw3-report.html"


@pytest.mark.skipif(not REAL_PAYLOAD.exists(),
                    reason="no real advice payload checked out")
def test_render_report_handles_real_payload(tmp_path):
    advice = Advice(**json.loads(REAL_PAYLOAD.read_text()))
    html = render_report(advice, out_dir=tmp_path).read_text()
    verdict = "recommended" if advice.wildcard_now["recommend"] else "not recommended"
    assert f"<strong>{verdict}</strong>" in html
    assert "conservative lower bound" in html


def test_model_health_hides_plan_comparison_when_unknown(tmp_path):
    """advice_pts/actual_pts are not computed yet; the line must stay out of
    the report rather than rendering "advice plan None vs your actual None"."""
    health = {"gw": 2, "mae_starters": 1.4, "captain_actual": 9,
              "advice_pts": None, "actual_pts": None}
    html = render_report(_advice(), out_dir=tmp_path,
                         model_health=health).read_text()
    assert "MAE (starters) 1.4" in html
    assert "advice plan" not in html.lower()

    health = {**health, "advice_pts": 60.0, "actual_pts": 58}
    html = render_report(_advice(), out_dir=tmp_path,
                         model_health=health).read_text()
    assert "Advice plan 60.0 vs your actual 58" in html


def test_report_renders_without_a_wildcard_assessment(tmp_path):
    """The wildcard is already spent this half, so run_advise skips the
    assessment entirely and the payload carries None."""
    advice = _advice()
    advice.wildcard_now = None
    html = render_report(advice, out_dir=tmp_path).read_text()
    assert "already played" in html
    assert "None" not in html


def _league_advice(stance="chase", lam=0.35, gap=42):
    advice = _advice()
    advice.strategy = {"lam": lam, "gap": gap, "weeks_left": 36,
                       "stance": stance, "rival_name": "Klopp on Wood"}
    advice.win_probs = [
        {"name": "Klopp on Wood", "total": 180, "p_win": 0.31},
        {"name": "Xhaka Khan", "total": 120, "p_win": 0.72},
    ]
    advice.buys = [{"code": 20, "name": "Star", "ep": 7.5, "tag": "attack"}]
    return advice


def test_league_panel_shows_stance_standings_and_transfer_tags(tmp_path):
    html = render_report(_league_advice(), out_dir=tmp_path).read_text()
    assert "Klopp on Wood" in html          # the top rival, named
    assert "42" in html and "0.35" in html  # gap and lambda
    assert "differential" in html.lower()   # chase copy
    assert "Xhaka Khan" in html and "72%" in html   # standings + p_win
    assert "attack" in html                 # buy tag


def test_league_panel_defend_copy_never_prints_negative_zero(tmp_path):
    html = render_report(_league_advice("defend", -0.5, 90),
                         out_dir=tmp_path).read_text()
    assert "-0.0" not in html and "−0.0" not in html
    assert "0.50" in html
    html = render_report(_league_advice("neutral", 0.0, 3),
                         out_dir=tmp_path).read_text()
    assert "-0.0" not in html and "−0.0" not in html


def test_report_omits_the_league_panel_without_a_strategy(tmp_path):
    html = render_report(_advice(), out_dir=tmp_path).read_text()
    assert "League strategy" not in html
    assert "P(I finish above" not in html


def _initial_advice():
    advice = _advice()
    advice.gw = 1
    advice.mode = "initial_squad"
    advice.buys = [{"code": i, "name": f"P{i}", "ep": 5.0, "tag": ""}
                   for i in range(15)]
    advice.sells = []
    advice.hits = 0
    advice.chip_table = []
    advice.wildcard_now = None
    return advice


def test_initial_squad_report_builds_a_squad_instead_of_transferring(tmp_path):
    """GW1 has no squad to transfer out of and no chip decision to make; the
    XI, bench and captain still render exactly as they do every other week."""
    html = render_report(_initial_advice(), out_dir=tmp_path).read_text()
    assert "build this squad" in html
    assert "SELL" not in html
    assert "No transfers" not in html
    assert "Chips" not in html and "Wildcard" not in html
    assert "already played" not in html
    # The squad itself is unchanged territory.
    assert "Starting XI" in html and "P1" in html and "B1" in html
    assert "Captain options" in html


def test_weekly_report_is_untouched_by_the_initial_squad_variant(tmp_path):
    html = render_report(_advice(), out_dir=tmp_path).read_text()
    assert "build this squad" not in html
    assert "SELL" in html and "Dud" in html
    assert "Chips" in html and "bboost" in html
