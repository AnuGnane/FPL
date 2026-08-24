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
