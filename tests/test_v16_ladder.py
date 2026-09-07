"""v16 §3 — the restraint walk on the ladder, its reasons, the served rung."""
from __future__ import annotations

import json

import numpy as np
import pytest

from gaffer import ladder as lad
from gaffer.ladder import (StepContext, explain_step, objective_line,
                           recommended_rung, restraint_line, rung_label,
                           serve_rung, served_note, walk)


def _row(key, hits=0, transfers=0, same_as=None, buys=(), sells=(), xi=(),
         captain=None, vice=None, gw=4):
    ref = lambda c: {"code": c, "name": f"P{c}", "position": "MID", "ep": 5.0}  # noqa: E731
    first = {"gw": gw, "hits": hits, "buys": [ref(c) for c in buys],
             "sells": [ref(c) for c in sells], "xi": [ref(c) for c in xi],
             "bench": [], "captain": ref(captain or (xi[0] if xi else 1)),
             "vice": ref(vice or (xi[-1] if xi else 2)), "expected_pts": 60.0}
    return {"key": key, "hits": hits, "transfers": transfers, "cost": hits * 4,
            "horizon_hits": hits, "horizon_cost": hits * 4,
            "same_as": same_as, "plan_by_gw": [] if same_as else [first],
            "vs_below": None}


def _scores(**cols):
    return {k: np.asarray(v, dtype=float) for k, v in cols.items()}


ROWS = [_row("bank"), _row("hits0", transfers=1, buys=[20], sells=[16]),
        _row("hits1", hits=1, transfers=2, buys=[20, 19], sells=[16, 17]),
        _row("hits2", hits=2, transfers=3, buys=[20, 19, 18], sells=[16, 17, 15])]


# --- the walk -------------------------------------------------------------

def test_every_step_earned_reaches_the_top():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 0], hits1=[2, 2, 2, 1],
                     hits2=[3, 3, 3, 2])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits2"
    assert [(s["below"], s["above"], s["taken"]) for s in steps] == [
        ("bank", "hits0", True), ("hits0", "hits1", True),
        ("hits1", "hits2", True)]
    assert steps[0]["share"] == 0.75


def test_the_walk_stops_at_the_first_refusal():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 0], hits1=[2, 0, 0, 0],
                     hits2=[9, 9, 9, 9])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits0"
    assert [s["taken"] for s in steps] == [True, False]
    assert steps[1]["share"] == 0.25


def test_the_free_transfer_step_uses_the_same_bar():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 0, 0], hits1=[5, 5, 5, 5],
                     hits2=[9, 9, 9, 9])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "bank" and len(steps) == 1 and steps[0]["taken"] is False


def test_the_share_is_strictly_greater_and_the_bar_is_inclusive():
    scores = _scores(bank=[0, 0, 0, 0, 0], hits0=[1, 1, 1, 0, 0], hits1=[0, 0, 0, 0, 0],
                     hits2=[0, 0, 0, 0, 0])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert steps[0]["share"] == 0.6 and steps[0]["taken"] is True
    assert chosen == "hits0"


def test_a_collapsed_rung_is_skipped_not_stepped_to():
    rows = [ROWS[0], ROWS[1], _row("hits1", hits=0, transfers=1, same_as="hits0"),
            ROWS[3]]
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 1], hits2=[2, 2, 2, 2])
    chosen, steps = walk(scores, rows, hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits2"
    assert [(s["below"], s["above"]) for s in steps] == [("bank", "hits0"),
                                                         ("hits0", "hits2")]


def test_a_cap_bounds_the_walk_whatever_the_draws_say():
    scores = _scores(bank=[0, 0, 0, 0], hits0=[1, 1, 1, 1], hits1=[2, 2, 2, 2],
                     hits2=[3, 3, 3, 3])
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=1,
                         max_transfers=None)
    assert chosen == "hits1"
    assert steps[-1]["taken"] is False and steps[-1]["reason_kind"] == "cap"
    chosen, steps = walk(scores, ROWS, hit_bar=0.6, max_hits=None,
                         max_transfers=0)
    assert chosen == "bank" and steps[0]["reason_kind"] == "cap"


def test_no_bank_rung_starts_the_walk_on_the_first_distinct_row():
    scores = _scores(hits0=[1, 1, 1, 1], hits1=[2, 2, 2, 2], hits2=[0, 0, 0, 0])
    chosen, steps = walk(scores, ROWS[1:], hit_bar=0.6, max_hits=None,
                         max_transfers=None)
    assert chosen == "hits1" and steps[0]["below"] == "hits0"


def test_no_scored_rung_at_all_chooses_nothing():
    assert walk({}, [], hit_bar=0.6, max_hits=None, max_transfers=None) == (None, [])


# --- the reasons, in precedence order --------------------------------------

def _ctx(**kw):
    base = dict(p_play={}, price_fall={}, difficulty={}, team_of={}, chip_plan=[])
    base.update(kw)
    return StepContext(**base)


def test_flagged_beats_everything():
    kind, text = explain_step(ROWS[0], ROWS[1], _ctx(
        p_play={(16, 4): 0.0}, price_fall={16: 0.96},
        difficulty={(1, 4): 0.9, (2, 4): 0.1}, team_of={16: 1, 20: 2},
        chip_plan=[{"gw": 5, "chip": "bboost"}]), gw=4, gws=[4, 5, 6])
    assert kind == "flagged" and text == "P16 is 0% to play"


def test_price_comes_second():
    kind, text = explain_step(ROWS[0], ROWS[1], _ctx(
        price_fall={16: 0.96}, difficulty={(1, 4): 0.9, (2, 4): 0.1},
        team_of={16: 1, 20: 2}), gw=4, gws=[4, 5, 6])
    assert kind == "price" and text == "P16 is 96% to drop tonight"


def test_fixtures_need_a_grade_of_difference():
    ctx = _ctx(difficulty={(1, 4): 0.7, (1, 5): 0.7, (1, 6): 0.8,
                           (2, 4): 0.5, (2, 5): 0.4, (2, 6): 0.5},
               team_of={16: 1, 20: 2})
    kind, text = explain_step(ROWS[0], ROWS[1], ctx, gw=4, gws=[4, 5, 6])
    assert kind == "fixtures"
    assert text == "P20's next 3 average 2.3 against P16's 3.7"
    close = _ctx(difficulty={(1, 4): 0.5, (2, 4): 0.4}, team_of={16: 1, 20: 2})
    assert explain_step(ROWS[0], ROWS[1], close, gw=4, gws=[4])[0] == "points"


def test_chip_then_points():
    kind, text = explain_step(ROWS[0], ROWS[1], _ctx(
        chip_plan=[{"gw": 5, "chip": "bboost"}]), gw=4, gws=[4, 5, 6])
    assert (kind, text) == ("chip", "a Bench Boost is planned for GW5")
    assert explain_step(ROWS[0], ROWS[1], _ctx(), gw=4, gws=[4]) == \
        ("points", "expected points alone")


def test_a_price_flag_below_half_does_not_count():
    assert explain_step(ROWS[0], ROWS[1], _ctx(price_fall={16: 0.3}), gw=4,
                        gws=[4])[0] == "points"


# --- the served rung --------------------------------------------------------

def _objective():
    ref = lambda c: {"code": c, "name": f"P{c}", "position": "MID", "ep": 5.0}  # noqa: E731
    return {"buys": [ref(20), ref(19)], "sells": [ref(16), ref(17)], "hits": 1,
            "xi": [ref(c) for c in range(1, 12)], "bench": [ref(12)],
            "captain": ref(3), "vice": ref(4), "expected_pts": 61.5,
            "plan_by_gw": [{"gw": 4, "hits": 1, "buys": [ref(20), ref(19)],
                            "sells": [ref(16), ref(17)], "expected_pts": 61.5},
                           {"gw": 5, "hits": 0, "buys": [], "sells": [],
                            "expected_pts": 60.0}]}


def _ladder(chosen="hits0"):
    rows = [_row("bank", xi=list(range(1, 12))),
            _row("hits0", transfers=1, buys=[20], sells=[16],
                 xi=[20] + list(range(2, 12)), captain=3, vice=20),
            _row("hits1", hits=1, transfers=2, buys=[20, 19], sells=[16, 17],
                 xi=[20, 19] + list(range(3, 12)), captain=20, vice=19)]
    rows[1]["plan_by_gw"].append({**rows[1]["plan_by_gw"][0], "gw": 5,
                                  "buys": [], "sells": [], "hits": 0})
    return {"gw": 4, "chosen": chosen, "bar": 0.6, "free_transfers": 1,
            "steps": [{"below": "bank", "above": "hits0", "share": 0.79,
                       "taken": True, "reason": "expected points alone",
                       "reason_kind": "points"},
                      {"below": "hits0", "above": "hits1", "share": 0.46,
                       "taken": False, "reason": "expected points alone",
                       "reason_kind": "points"}],
            "rungs": rows}


def test_the_rungs_plan_replaces_week_one_and_every_horizon_week():
    out = serve_rung(_ladder(), _objective(), hit_cost=4, captain_note=None)
    assert [b["code"] for b in out["buys"]] == [20]
    assert [s["code"] for s in out["sells"]] == [16]
    assert out["hits"] == 0 and len(out["plan_by_gw"]) == 2
    assert out["plan_by_gw"][0]["gw"] == 4 and out["plan_by_gw"][1]["gw"] == 5
    assert set(out["plan_by_gw"][0]) == {"gw", "hits", "buys", "sells", "expected_pts"}
    assert out["expected_pts"] == 55.0            # eleven refs at 5.0
    assert out["objective"] == {"buys": _objective()["buys"], "sells": _objective()["sells"],
                                "hits": 1, "expected_pts": 61.5}
    assert out["restraint"]["chosen"] == "hits0" and out["restraint"]["bar"] == 0.6
    assert out["restraint"]["agrees"] is False and len(out["restraint"]["steps"]) == 2


def test_the_sweeps_captain_stands_when_he_is_in_the_rungs_xi():
    out = serve_rung(_ladder(), _objective(), hit_cost=4, captain_note="covering Dave")
    assert out["captain"]["code"] == 3 and out["captain_note"] == "covering Dave"
    assert out["vice"]["code"] == 20            # the rung's vice


def test_without_a_note_the_rungs_own_captain_is_served():
    """The objective captained its own squad (4, who is in the rung's XI
    too); the rung's plan, solved with its buy in, captained 3 — the GW4
    board's Groß/Palmer case. No note, so the rung's own armband is served."""
    obj = _objective()
    obj["captain"] = {"code": 4, "name": "P4", "position": "MID", "ep": 5.0}
    out = serve_rung(_ladder(), obj, hit_cost=4, captain_note=None)
    assert out["captain"]["code"] == 3 and out["vice"]["code"] == 20
    assert out["captain_note"] is None


def test_a_noted_captain_not_in_the_rung_falls_to_the_rungs_with_a_note():
    obj = _objective()
    obj["captain"] = {"code": 99, "name": "Gone", "position": "FWD", "ep": 9.0}
    out = serve_rung(_ladder(), obj, hit_cost=4, captain_note="covering Dave")
    assert out["captain"]["code"] == 3
    assert out["captain_note"] == ("captain from the restrained plan; the "
                                   "sweep's choice (Gone) is not in it")


def test_the_vice_never_equals_the_captain():
    lad_ = _ladder()
    lad_["rungs"][1]["plan_by_gw"][0]["vice"] = {"code": 3, "name": "P3",
                                                 "position": "MID", "ep": 5.0}
    out = serve_rung(lad_, _objective(), hit_cost=4, captain_note="covering Dave")
    # The noted captain (3) stands; the rung's vice is also 3, so the vice
    # falls to the rung's own captain (20).
    assert out["captain"]["code"] == 3 and out["vice"]["code"] == 20


def test_agreement_is_on_the_moves():
    out = serve_rung(_ladder("hits1"), _objective(), hit_cost=4, captain_note=None)
    assert out["restraint"]["agrees"] is True and out["restraint"]["note"] is None


def test_no_ladder_or_no_chosen_rung_serves_the_objective_with_a_note():
    out = serve_rung(None, _objective(), hit_cost=4, captain_note=None)
    assert out["restraint"]["hit_cost"] == 4
    assert out["buys"] == _objective()["buys"] and out["hits"] == 1
    assert out["restraint"]["chosen"] is None and "ladder" in out["restraint"]["note"]
    out = serve_rung({**_ladder(), "chosen": None}, _objective(), hit_cost=4, captain_note=None)
    assert out["restraint"]["chosen"] is None and out["hits"] == 1


# --- labels, lines, recommended, served note ----------------------------------

def test_rung_labels():
    assert [rung_label(k) for k in ("bank", "hits0", "hits1", "hits3", "open")] == \
        ["bank", "free transfers only", "1 hit", "3 hits", "no cap"]


def test_the_cli_lines():
    r = serve_rung(_ladder(), _objective(), hit_cost=4, captain_note=None)["restraint"]
    assert restraint_line(r) == ("restraint: free transfers only; the step to "
                                 "1 hit was refused, 46% — expected points alone")
    assert objective_line(_objective()) == \
        "the objective wanted: P20, P19 in; P16, P17 out; 1 hit"
    taken = {**r, "steps": [r["steps"][0]]}
    assert restraint_line(taken) == "restraint: free transfers only; every step was taken"


def test_recommended_matches_the_served_moves_and_ignores_the_captain():
    rows = _ladder()["rungs"]
    advice = {"gw": 4, "buys": [{"code": 20}], "sells": [{"code": 16}],
              "captain": {"code": 3}}
    assert recommended_rung(advice, rows) == ("hits0", None)
    advice["captain"] = {"code": 999}
    assert recommended_rung(advice, rows) == ("hits0", None)
    advice["buys"] = [{"code": 55}]
    assert recommended_rung(advice, rows)[0] is None


def test_the_served_note_names_both_bars():
    lad_ = {**_ladder(), "chosen": "bank", "bar": 0.7}
    advice = {"gw": 4, "restraint": {"chosen": "hits0", "bar": 0.6}}
    assert served_note(lad_, advice) == ("the served advice was the free "
                                         "transfers only rung at bar 0.60; this "
                                         "rebuild at 0.70 chooses bank")
    assert served_note(_ladder(), {"gw": 4, "restraint": {"chosen": "hits0", "bar": 0.6}}) is None
    assert served_note(_ladder(), {"gw": 3, "restraint": {"chosen": "bank", "bar": 0.6}}) is None
    assert served_note(_ladder(), {"gw": 4}) is None


# --- on a saved board ---------------------------------------------------------

def test_build_ladder_carries_the_bar_the_chosen_rung_and_the_steps(tmp_path,
                                                                     monkeypatch):
    from tests.test_ladder import save_state

    from gaffer.config import serving_config
    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    save_state({"max_hits": 15, "max_transfers": 15})
    monkeypatch.setattr(lad, "OUTCOME_VAR_PER_EP", 0.0)
    monkeypatch.setattr(lad, "sigma_table", lambda gw: ({}, "outcome_only"))
    out = build_ladder(1, n_draws=20, seed=5)
    serving_config.cache_clear()
    assert out["bar"] == 0.60
    assert out["chosen"] in {r["key"] for r in out["rungs"]}
    keys = {"below", "above", "share", "taken", "reason", "reason_kind"}
    assert out["steps"] and all(set(s) == keys for s in out["steps"])
    # No noise: every share is 0 or 1, and the walk is a prefix of the ladder.
    assert all(s["share"] in (0.0, 1.0) for s in out["steps"])
    taken = [s["taken"] for s in out["steps"]]
    assert taken == sorted(taken, reverse=True)
    banked = json.loads((tmp_path / "reports" / "ladder_gw1.json").read_text())
    assert banked["chosen"] == out["chosen"]


def test_the_get_route_recomputes_recommended_and_adds_the_served_note(tmp_path,
                                                                        monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer import artifacts
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    artifacts.REPORTS.mkdir()
    lad_ = _ladder()
    (artifacts.REPORTS / "ladder_gw4.json").write_text(json.dumps(
        {**lad_, "gws": [4, 5], "cap": {}, "notes": [], "n_draws": 5}))
    (artifacts.REPORTS / "gw4-advice.json").write_text(json.dumps(
        {"gw": 4, "buys": [{"code": 20, "name": "P20"}], "sells": [{"code": 16, "name": "P16"}],
         "captain": {"code": 3}, "restraint": {"chosen": "hits0", "bar": 0.5}}))
    monkeypatch.setattr("gaffer.web.routers.ladder.latest_gw", lambda: 4)
    body = TestClient(create_app()).get("/api/ladder").json()
    assert body["recommended"] == "hits0" and body["chosen"] == "hits0"
    assert body["bar"] == 0.6 and len(body["steps"]) == 2
    assert body["served_note"] == ("the served advice was the free transfers "
                                   "only rung at bar 0.50; this rebuild at 0.60 "
                                   "chooses free transfers only")
