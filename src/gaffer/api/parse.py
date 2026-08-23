from __future__ import annotations


def to_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def to_int(v, default=None):
    f = to_float(v)
    return default if f is None else int(f)
