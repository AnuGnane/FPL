"""The weekly pipeline's source, in pipeline order (v17g §2.4).

Older cycles pinned orderings and wirings in ``run_advise`` by string-matching
its body, because there was no interface to assert them through: the function
took a config and a client and reached the models, the live data, the solver
and ``reports/``, so no test could call it. v17g cuts that body into
``gather_inputs`` and ``build_advice`` with ``run_advise`` composing them. The
rails still ask the same question of the same text, so they ask it here.

Concatenating in **pipeline order** is what keeps an ordering assertion that
straddles the split true — six files pin
``fetch_rival_entries`` < ``tilt_ep`` < ``build_pool``, and the first of those
is now in the gather half while the last two are in the build half.

New rails do not belong here. ``build_advice`` is callable now, on a frozen
``Inputs`` and a scripted solver: assert what the code *did*, the way
``tests/test_advise.py`` does since v17g §5.
"""
from __future__ import annotations

import inspect


def advise_source() -> str:
    """The pipeline's source, whatever it is currently split into.

    Until the split lands this is ``run_advise`` alone, so the commit that
    points eighteen rails here changes not one character of what any of them
    reads — which is the point of doing it first: the split that follows
    cannot be blamed for a rail this commit broke.
    """
    from gaffer.advise import run_advise

    return inspect.getsource(run_advise)
