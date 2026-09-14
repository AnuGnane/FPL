"""The write routers' shared 422 and the three number readers (v18d §2).

A table over the six inputs that told the six copies of these helpers apart —
``None``, NaN, an unparseable string, a parseable one, an int and a float —
because the whole point of one module is that every caller now gets the same
answer for each of them, and only a table says so.
"""

from __future__ import annotations

import math

import pytest

from gaffer.web.coerce import fail, finite, opt_float, opt_int

NAN = float("nan")


@pytest.mark.parametrize("value,expected", [
    (None, None),
    (NAN, None),
    ("x", None),
    ("3.5", 3.5),
    (3, 3.0),
    (3.0, 3.0),
])
def test_opt_float_reads_a_number_or_says_there_is_none(value, expected):
    assert opt_float(value) == expected


def test_opt_float_rounds_only_when_it_is_asked_to():
    assert opt_float(1 / 3) == pytest.approx(0.3333333333333333)
    assert opt_float(1 / 3, 4) == 0.3333
    assert opt_float(2.71828, 1) == 2.7
    assert opt_float(None, 4) is None


@pytest.mark.parametrize("value,expected", [
    (None, None),
    (NAN, None),
    ("x", None),
    ("3.5", None),
    (3, 3),
    (3.0, 3),
])
def test_opt_int_reads_a_whole_number_or_says_there_is_none(value, expected):
    assert opt_int(value) == expected


@pytest.mark.parametrize("value,expected", [
    (None, 0.0),
    (NAN, 0.0),
    ("x", 0.0),
    ("3.5", 3.5),
    (3, 3.0),
    (3.0, 3.0),
])
def test_finite_reads_a_number_or_falls_back_to_the_default(value, expected):
    assert finite(value) == expected


@pytest.mark.parametrize("value", [None, NAN, "x"])
def test_finite_honours_a_default_that_is_not_zero(value):
    assert finite(value, -1.0) == -1.0


def test_finite_never_returns_a_nan():
    assert not math.isnan(finite(NAN))


def test_the_refusal_carries_the_constraint_the_error_and_the_players():
    exc = fail("force_out_on_free_hit", "there is nothing to force out", [12])
    assert exc.status_code == 422
    assert exc.detail == {"constraint": "force_out_on_free_hit",
                          "error": "there is nothing to force out",
                          "players": [12]}


def test_a_refusal_over_something_that_is_not_a_player_carries_an_empty_list():
    exc = fail("unknown_reason", "the reason is one of a, b")
    assert exc.detail == {"constraint": "unknown_reason",
                          "error": "the reason is one of a, b",
                          "players": []}


def test_an_explicit_none_for_players_reads_as_the_empty_list():
    assert fail("c", "e", None).detail["players"] == []
