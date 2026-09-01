"""How often a lane went my way, counted where the honesty rule already lives.

Every label is on the wire, so a React component could count them. It must not:
``season_summary``'s docstring is where "an ungraded lane contributes nothing to
the sum *and* nothing to the count" is written, and a win rate computed in a
component would be a second implementation of that rule, in a language with a
different notion of null, drawn on the same page as the first.

Two decisions are under test and neither is obvious:

* a **zero** delta is neither a win nor a loss. It is a week the decision made
  no difference, and counting it as a win would let a lane of perfect agreement
  read as a lane of perfect judgment;
* therefore ``wins + losses <= graded``, with slack, and the assertion is the
  inequality. An equality would forbid the agreement it is meant to allow.
"""

from __future__ import annotations

from gaffer.review import season_summary


def _row(gw, **lanes):
    return {"gw": gw, "lanes": [{"lane": name, "delta_pts": delta,
                                 "delta_pwin": 0.0, "label": None}
                                for name, delta in lanes.items()]}


def test_a_lane_that_gained_points_counts_a_win():
    out = season_summary([_row(1, transfers=4.0)])
    assert out["lanes"]["transfers"]["wins"] == 1
    assert out["lanes"]["transfers"]["losses"] == 0


def test_a_lane_that_lost_points_counts_a_loss():
    out = season_summary([_row(1, captaincy=-6.0)])
    assert out["lanes"]["captaincy"]["losses"] == 1
    assert out["lanes"]["captaincy"]["wins"] == 0


def test_a_zero_delta_is_neither():
    """A week I did what the model did. Counting it as a win would turn
    agreement into judgment."""
    out = season_summary([_row(1, bench=0.0)])
    cell = out["lanes"]["bench"]
    assert (cell["wins"], cell["losses"], cell["graded"]) == (0, 0, 1)


def test_an_ungraded_lane_counts_nothing_at_all():
    """The rule the whole function exists to hold: never measured is not
    never wrong."""
    out = season_summary([_row(1, chip=None)])
    cell = out["lanes"]["chip"]
    assert (cell["wins"], cell["losses"], cell["graded"]) == (0, 0, 0)


def test_the_counts_never_exceed_the_graded_count():
    rows = [_row(1, transfers=4.0), _row(2, transfers=-1.0),
            _row(3, transfers=0.0), _row(4, transfers=None)]
    cell = season_summary(rows)["lanes"]["transfers"]
    assert cell["graded"] == 3
    assert cell["wins"] + cell["losses"] <= cell["graded"]
    assert (cell["wins"], cell["losses"]) == (1, 1)


def test_every_lane_reports_the_pair_even_when_it_never_played():
    """Four lanes, always. A lane missing from the summary is a lane the UI
    would render as absent rather than as unmeasured."""
    out = season_summary([_row(1, transfers=4.0)])
    for name in ("transfers", "captaincy", "bench", "chip"):
        assert {"pts", "pwin", "graded", "wins", "losses"} <= set(
            out["lanes"][name])


def test_an_empty_ledger_is_still_None():
    """``season_summary``'s oldest contract: a season nobody reviewed has no
    summary, and a summary of zeros would read as a season of flawless
    decisions."""
    assert season_summary([]) is None


def test_the_existing_keys_are_untouched():
    out = season_summary([_row(1, transfers=4.0)])
    assert {"gws", "lanes", "accuracy", "points_on_bench",
            "points_on_bench_gws", "hindsight_gap", "hindsight_gap_gws",
            "reconciled_gws", "unreconciled_gws", "best", "worst"} <= set(out)
