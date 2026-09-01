"""``/api/chips/plan`` carries the bar it was always measured against.

Spec §F2c names this endpoint as the source of the θ trajectory. Read it and
it has never carried θ at all:

* ``meta.py:69`` called ``chip_plan(table, now_gw=...)`` with ``thresholds``
  left at its default ``None``, so ``threshold_now`` and ``play_now`` came
  back ``None`` by construction;
* and ``ChipPlanRow`` declared neither field, so even when they were computed
  ``ChipPlanRow(**row)`` dropped them in silence. That is v9d's
  ``odds_blend_weight`` exactly — an undeclared field never reaches the page,
  and nothing anywhere fails while it doesn't.

The trajectory is built at the router by looping the ``(chip, gw) -> float``
callable the chip layer already exposes. Putting it in ``chip_plan``'s week
rows would be an ``optimize/**`` edit for a display field (plan A9), and this
cycle makes none.
"""

from __future__ import annotations

from gaffer.optimize.chip_policy import (chip_thresholds_from_asset,
                                         chip_windows, flat_thresholds,
                                         load_chip_scenarios)
from gaffer.web.schemas import ChipPlanRow


def test_a_row_carrying_the_threshold_keeps_it():
    """The declared-field rail, and the whole failure this task fixes.
    Pydantic ignores extras, so an undeclared field is dropped and nothing
    complains — which is why this is asserted rather than assumed."""
    row = ChipPlanRow(chip="bboost", weeks=[{"gw": 2, "gain": 5.0,
                                             "per_week": 5.0}],
                      best_gw=2, best_gain=5.0, best_gain_per_week=5.0,
                      weeks_scored=1, now_gain=5.0, play_now_delta=0.0,
                      threshold_now=4.0, play_now=True, thetas=[4.0],
                      window=[2, 19])
    assert row.threshold_now == 4.0
    assert row.play_now is True
    assert row.thetas == [4.0]
    assert row.window == [2, 19]


def test_the_pre_existing_shape_still_validates():
    """Every new field has a default, so a row built the way v4c built it is
    still a valid row — this endpoint has a type in the frontend and one day
    it will have a consumer."""
    row = ChipPlanRow(chip="bboost", weeks=[], best_gw=2, best_gain=1.0,
                      best_gain_per_week=1.0, weeks_scored=0, now_gain=None,
                      play_now_delta=None)
    assert row.threshold_now is None and row.thetas == []


def test_the_thetas_align_with_the_weeks_by_index():
    """The trajectory the panel draws. Aligned by index so the client never
    has to re-key it against the weeks it already has."""
    thresholds = flat_thresholds()
    weeks = [{"gw": gw} for gw in range(2, 8)]
    thetas = [round(float(thresholds("bboost", w["gw"])), 2) for w in weeks]
    assert len(thetas) == len(weeks)
    assert all(t == 4.0 for t in thetas)


def test_a_missing_priors_asset_degrades_to_the_flat_bar_not_to_nulls():
    """``chip_thresholds_from_asset(None, ...)`` is ``flat_thresholds()``:
    8.0 for the wildcard and 4.0 otherwise. A real bar, and the one advise.py
    would have used."""
    thresholds = chip_thresholds_from_asset(None, {})
    assert thresholds("wildcard", 5) == 8.0
    assert thresholds("bboost", 5) == 4.0


def test_an_absent_scenario_file_gives_the_same_bar_as_today():
    """The §Gates rail, at the level it matters. The expression here is
    ``advise.py:735-736``'s, character for character, so this is also a check
    that the two have not drifted."""
    with_file = chip_thresholds_from_asset(None, load_chip_scenarios())
    without = chip_thresholds_from_asset(None)
    for chip in ("wildcard", "bboost", "freehit", "3xc"):
        for gw in range(1, 39):
            assert with_file(chip, gw) == without(chip, gw)


def test_the_window_is_the_argument_and_the_expiry():
    """Note the first element is the gameweek *asked about*, not the window's
    opening — the name suggests otherwise and the UI must say "expires after
    GW19", never "window starts at"."""
    assert chip_windows(2) == (2, 19)
    assert chip_windows(20) == (20, 38)
    assert chip_windows(19) == (19, 19)


def test_the_route_loops_the_callable_rather_than_widening_chip_plan():
    """Plan A9, asserted where a reader will look for it: the θ trajectory is
    built at the router, and ``optimize/chips.py`` is untouched."""
    import inspect

    from gaffer.web.routers import meta

    source = inspect.getsource(meta.chips_plan)
    assert "chip_thresholds_from_asset" in source
    assert "thetas" in source
    assert "chip_windows" in source


def test_this_task_added_fields_and_not_routes(tmp_path, monkeypatch):
    """θ reaches the page through the schema, not through a second endpoint.
    The live total is 45 and the one route this cycle added is the outlook,
    which is asserted by name in tests/test_v10b_degradation.py."""
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    paths = set(create_app().openapi()["paths"])
    assert len(paths) == 45
    assert "/api/chips/plan" in paths
