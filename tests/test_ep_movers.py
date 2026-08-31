"""One predecessor components file, and the diff it makes possible.

"Since last run" has always been able to say the plan changed and never able
to say *why*. The why is in the components parquet, which every advise run
overwrites — so the fix is one bounded copy and a join.

Three claims carry the file. The copy is a copy, taken before the overwrite
and never accumulating past one slot. Its failure costs the diff and never the
run, because banking the current components is the function's actual job. And
the diff compares each frame's own first gameweek (plan A9), so a retrain that
also rolled the horizon forward does not report the whole pool as having moved
out of a gameweek that is no longer in the file.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import (COMPONENT_COLS, components_path, ep_movers,
                              load_components, prev_components_path,
                              save_components)

GW = 5


def _frame(rows: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame(rows)
    for col in COMPONENT_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[COMPONENT_COLS]


BEFORE = _frame([
    {"code": 11, "name": "Saka", "gw": GW, "ep": 5.0},
    {"code": 22, "name": "Haaland", "gw": GW, "ep": 7.0},
    {"code": 33, "name": "Rice", "gw": GW, "ep": 3.0},
    {"code": 11, "name": "Saka", "gw": GW + 1, "ep": 4.0},
])

AFTER = _frame([
    {"code": 11, "name": "Saka", "gw": GW, "ep": 6.4},     # +1.4
    {"code": 22, "name": "Haaland", "gw": GW, "ep": 6.1},  # -0.9
    {"code": 33, "name": "Rice", "gw": GW, "ep": 3.2},     # +0.2, below
    {"code": 44, "name": "New", "gw": GW, "ep": 8.0},      # no predecessor
    {"code": 11, "name": "Saka", "gw": GW + 1, "ep": 9.9},
])


@pytest.fixture(autouse=True)
def _reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()


def test_the_first_save_takes_no_copy_because_there_is_nothing_to_copy():
    save_components(BEFORE, GW)
    assert not prev_components_path(GW).exists()


def test_the_second_save_preserves_the_first():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert load_components(GW)["ep"].sum() == pytest.approx(
        AFTER["ep"].sum())
    prev = pd.read_parquet(prev_components_path(GW))
    assert prev["ep"].sum() == pytest.approx(BEFORE["ep"].sum())


def test_a_third_save_keeps_one_slot_not_two():
    """Bounded. The question is "what did tonight's retrain change", and a
    third file answers no question anybody asked."""
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    save_components(BEFORE, GW)
    prev = pd.read_parquet(prev_components_path(GW))
    assert prev["ep"].sum() == pytest.approx(AFTER["ep"].sum())
    assert not (components_path(GW).parent
                / f"components_gw{GW}_prev_prev.parquet").exists()


def test_a_failed_copy_costs_the_diff_and_not_the_run(monkeypatch, capsys):
    save_components(BEFORE, GW)
    monkeypatch.setattr("gaffer.artifacts.shutil.copyfile",
                        lambda *a: (_ for _ in ()).throw(OSError("full")))
    assert save_components(AFTER, GW) == components_path(GW)
    assert load_components(GW)["ep"].sum() == pytest.approx(
        AFTER["ep"].sum())
    assert "no predecessor kept" in capsys.readouterr().out


# --- the diff ---------------------------------------------------------

def test_no_predecessor_is_none_rather_than_an_empty_list():
    """A9: "we have not retrained since you last looked" and "the retrain
    changed nothing" are different sentences, and the payload must be able to
    tell them apart."""
    save_components(BEFORE, GW)
    assert ep_movers(GW) is None


def test_the_movers_come_back_biggest_absolute_change_first():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    movers = ep_movers(GW)
    assert [m["code"] for m in movers] == [11, 22]
    assert movers[0]["ep_prev"] == pytest.approx(5.0)
    assert movers[0]["ep_now"] == pytest.approx(6.4)
    assert movers[0]["delta"] == pytest.approx(1.4)
    assert movers[0]["name"] == "Saka"


def test_a_player_below_the_threshold_is_not_a_mover():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert 33 not in [m["code"] for m in ep_movers(GW)]


def test_the_threshold_is_a_parameter():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert [m["code"] for m in ep_movers(GW, threshold=0.1)] == [11, 22, 33]


def test_a_player_with_no_predecessor_row_is_not_a_mover():
    """He did not *move* — he appeared. Reporting a new pool entrant as
    "+8.0 EP" would be the diff's most eye-catching and least true row."""
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert 44 not in [m["code"] for m in ep_movers(GW)]


def test_only_each_frames_own_first_gameweek_is_compared():
    """A9. Saka's GW6 EP moved by 5.9 and is not reported: the diff is about
    the week being decided, which is the only one both frames must share."""
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    assert all(abs(m["delta"]) < 5.0 for m in ep_movers(GW))


def test_a_double_gameweek_sums_its_fixtures_on_both_sides():
    save_components(_frame([
        {"code": 11, "name": "Saka", "gw": GW, "ep": 2.0},
        {"code": 11, "name": "Saka", "gw": GW, "ep": 2.0}]), GW)
    save_components(_frame([
        {"code": 11, "name": "Saka", "gw": GW, "ep": 3.5},
        {"code": 11, "name": "Saka", "gw": GW, "ep": 3.5}]), GW)
    assert ep_movers(GW)[0]["delta"] == pytest.approx(3.0)


def test_a_horizon_that_rolled_forward_compares_the_two_first_weeks():
    """The case A9 exists for: last night's run decided GW5, tonight's decides
    GW6, and each frame's own opening week is the comparable one."""
    save_components(_frame([{"code": 11, "name": "Saka", "gw": GW,
                             "ep": 5.0}]), GW)
    save_components(_frame([{"code": 11, "name": "Saka", "gw": GW + 1,
                             "ep": 6.2}]), GW)
    assert ep_movers(GW)[0]["delta"] == pytest.approx(1.2)


@pytest.mark.parametrize("payload", ["garbage", ""])
def test_an_unreadable_predecessor_is_none_not_an_exception(payload):
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    prev_components_path(GW).write_text(payload)
    assert ep_movers(GW) is None


def test_a_predecessor_with_no_ep_column_is_none():
    save_components(BEFORE, GW)
    save_components(AFTER, GW)
    BEFORE.drop(columns=["ep"]).to_parquet(prev_components_path(GW),
                                           index=False)
    assert ep_movers(GW) is None


def test_a_missing_current_file_is_none():
    assert ep_movers(999) is None


def test_nothing_moving_is_an_empty_list_not_none():
    """The other half of A9: once there is a predecessor, "nothing moved" is
    a claim the payload is entitled to make."""
    save_components(BEFORE, GW)
    save_components(BEFORE, GW)
    assert ep_movers(GW) == []
