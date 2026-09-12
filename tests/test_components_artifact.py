"""v18c Task 3: the pre-blend ``e_goals`` is banked as ``e_goals_model``
rather than lost when ``blend_attacking_odds`` overwrites ``e_goals`` in
place. Kept out of ``tests/test_odds.py`` (orchestrator-only) and
``tests/test_artifacts.py`` isn't touched either, so this is a new file.
"""
import pandas as pd

from gaffer.artifacts import COMPONENT_COLS, save_components
from gaffer.data.odds import blend_attacking_odds


def _comp():
    return pd.DataFrame({
        "code": [11, 12], "gw": [1, 1], "opp_code": [43, 43],
        "p_play": [0.9, 0.01], "e_goals": [0.20, 0.10],
        "e_assists": [0.15, 0.05]})


def _ags():
    return pd.DataFrame({"code": [11, 12], "gw": [1, 1], "team_code": [3, 3],
                         "opp_code": [43, 43], "lambda_ags": [0.45, 0.02]})


def test_e_goals_model_is_declared_right_after_e_goals():
    i = COMPONENT_COLS.index("e_goals")
    assert COMPONENT_COLS[i + 1] == "e_goals_model"


def test_blend_attacking_odds_banks_the_pre_blend_value():
    comp = _comp()
    out = blend_attacking_odds(comp, _ags(), weight=0.5)
    # e_goals_model is the model's own value, untouched by the blend, for
    # both rows — including the fringe (p_play=0.01) one.
    assert list(out["e_goals_model"]) == [0.20, 0.10]
    # e_goals itself is the blend for both rows: p_play=0.01 still clears the
    # blend's >0 gate, so the fringe row's e_goals is capped/blended too, not
    # left at the model value.
    assert out.loc[0, "e_goals"] != out.loc[0, "e_goals_model"]
    assert out.loc[1, "e_goals"] != out.loc[1, "e_goals_model"]


def test_blend_attacking_odds_leaves_e_goals_model_alone_with_no_odds():
    comp = _comp()
    for absent in (None, pd.DataFrame()):
        out = blend_attacking_odds(comp, absent, weight=0.5)
        assert "e_goals_model" not in out.columns


def test_save_components_backfills_a_missing_e_goals_model_from_e_goals(
        tmp_path, monkeypatch):
    """A frame built before this column existed — or from the no-odds-key
    path, where blend_attacking_odds never ran — still gets a sensible
    e_goals_model rather than a forever-null column."""
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({c: [0.0] for c in COMPONENT_COLS
                          if c != "e_goals_model"})
    frame["e_goals"] = [0.33]
    assert "e_goals_model" not in frame.columns
    save_components(frame, 9)
    from gaffer.artifacts import load_components

    back = load_components(9)
    assert back.loc[0, "e_goals_model"] == 0.33
