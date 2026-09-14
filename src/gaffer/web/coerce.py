"""The write routers' one 422 shape, and the three number readers (v18d §2).

Six routers had grown their own copy of the same refusal — the what-if lab's
``{constraint, error, players}`` detail — and six more places re-derived the
same "a pandas cell is not always a number" rule, each with its own answer for
NaN. Two answers are legitimate and both live here: :func:`opt_float` and
:func:`opt_int` say *no reading* with ``None``, which is what a probability or
an ordering needs, and :func:`finite` says *zero* with a default, which is what
an additive EP term needs. Choosing between them at the call site is a
decision; re-implementing the choice six times is how one of the copies ends up
disagreeing with the others about ``float("nan")``.
"""

from __future__ import annotations

import math

from fastapi import HTTPException


def fail(constraint: str, error: str,
         players: list[int] | None = None) -> HTTPException:
    """The what-if lab's structured 422, so the UI has one error shape.

    ``players`` is optional because two of the endpoints that raise this —
    settings and the deviation note — refuse over something that is not a
    player, and an empty list is the honest answer there rather than a second
    refusal shape for the client to learn.
    """
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players or []})


def opt_float(value, digits: int | None = None) -> float | None:
    """``value`` as a float, or ``None`` when it is not a reading at all.

    ``None`` and NaN are the same answer here on purpose: a frame banked
    before a column existed carries no cell, and one banked after carries an
    all-NaN one, and neither is a number the panel may print as 0.0.
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out):
        return None
    return out if digits is None else round(out, digits)


def opt_int(value) -> int | None:
    """``value`` as an int, or ``None`` under :func:`opt_float`'s rule.

    Stricter than ``opt_float`` about a string on purpose: the fields that
    read through here are orderings — a penalty taker is first or second, and
    ``"3.5"`` is not an answer to that question.
    """
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def finite(value, default: float = 0.0) -> float:
    """``value`` as a float, with ``default`` for anything that is not one.

    The other half of the choice :func:`opt_float` makes: an EP term the
    breakdown never scored really is worth zero points, and a panel whose
    promise is that the terms sum to the total cannot carry a ``None`` through
    that sum.
    """
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(out) else out
