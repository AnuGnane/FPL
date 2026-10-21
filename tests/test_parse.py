"""v1 — the parse helpers for FPL's string-typed API fields.

The API sends numbers as strings and sometimes as null; these helpers are
the one place that is turned into floats and ints with a default.
"""
from gaffer.api.parse import to_float, to_int


def test_to_float_parses_api_strings():
    assert to_float("4.5") == 4.5
    assert to_float("") is None
    assert to_float(None) is None
    assert to_float("abc") is None
    assert to_float(3) == 3.0


def test_to_int_parses_a_string_and_defaults_a_none():
    assert to_int("7") == 7
    assert to_int(None, default=0) == 0
