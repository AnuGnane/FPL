"""Lenient coercions for the FPL API's loosely typed fields.

The API sends numbers as strings, empty strings or ``None`` as it pleases, so
a reader asks for a default rather than raising on a field it cannot read.
"""
from __future__ import annotations


def to_float(v, default=None):
    """``v`` as a float, or ``default`` when it is ``None``, empty or not a number."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_int(v, default=None):
    """``v`` as an int through :func:`to_float`, so ``"3.0"`` reads as 3 and a blank as
    ``default``."""
    f = to_float(v)
    return default if f is None else int(f)
