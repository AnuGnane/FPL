"""§4.1 on the wire: the request field, the four refusals, the re-solve.

The refusals are the interesting half. Three of the four are combinations that
would otherwise produce a constraint doing nothing at all — a user who ticks
"must sell" on a player he does not own, or on a free hit, gets an answer that
looks like it honoured him. The fourth (lock + force_out) would reach the
solver, which refuses it by name since Task 1; this catches it a layer earlier,
beside the input, which is where ``_fail`` exists to put things.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.web.routers import whatif as wf
from gaffer.web.schemas import WhatIfRequest


class _State:
    """The saved solve state ``_validate`` reads, and nothing more."""

    def __init__(self, owned=(1, 2, 3), pool_codes=(1, 2, 3, 4, 5)):
        self.owned_codes = list(owned)
        self.pool = pd.DataFrame({"code": list(pool_codes)})
        self.gws = [5, 6, 7]
        self.avail_by_gw = {5: ["wildcard", "freehit"]}


def _req(**kw) -> WhatIfRequest:
    return WhatIfRequest(**kw)


def test_the_request_carries_force_out_and_defaults_it_empty():
    assert _req().force_out == []
    assert _req(force_out=[1]).force_out == [1]


def test_an_unknown_code_is_refused_like_every_other_list():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(force_out=[99]), _State())
    assert exc.value.detail["constraint"] == "unknown_player"


def test_forcing_out_a_player_you_do_not_own_is_refused():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(force_out=[4]), _State())
    assert exc.value.detail["constraint"] == "force_out_not_owned"
    assert "use ban" in exc.value.detail["error"]


def test_locking_and_forcing_out_the_same_player_is_refused():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(lock=[1], force_out=[1]), _State())
    assert exc.value.detail["constraint"] == "force_out_and_lock"


def test_banning_and_forcing_out_the_same_player_is_refused():
    with pytest.raises(Exception) as exc:
        wf._validate(_req(ban=[1], force_out=[1]), _State())
    assert exc.value.detail["constraint"] == "force_out_and_ban"


def test_force_out_on_a_free_hit_is_refused_rather_than_ignored():
    """The FH branch builds ``owned_codes=[]``, so the constraint would apply
    to nobody and the user would read an answer that looked like it applied."""
    with pytest.raises(Exception) as exc:
        wf._validate(_req(force_out=[1], chip="fh"), _State())
    assert exc.value.detail["constraint"] == "force_out_on_free_hit"


def test_an_empty_force_out_still_validates_every_pre_existing_way():
    """The degradation direction: nothing above may fire on today's requests."""
    wf._validate(_req(lock=[1], ban=[4], force_in=[5]), _State())


def test_the_router_passes_force_out_and_prints_it_when_infeasible():
    """Two claims in one: the constrained ``SolveInput`` is built with the
    codes, and the sentence a user reads on an infeasible board says which
    lists produced it. Read off the source rather than by stubbing the solver,
    which is how ``tests/test_v8e_degradation.py`` already pins this module's
    board-building idiom."""
    import inspect

    src = inspect.getsource(wf.solve_whatif)
    assert "force_out=list(req.force_out)" in src
    assert "force_out={req.force_out}" in src
    # The free-hit branch must NOT carry it: _validate has already refused the
    # combination, and encoding a forbidden state is how it becomes reachable.
    fh = src[src.index('if chip == "freehit"'):src.index("try:")]
    assert "force_out" not in fh


def test_a_draft_records_the_constraint_it_was_asked_for():
    """A12: the store whose docstring says "what you asked for" is the one that
    has to learn a new way of asking."""
    from gaffer import drafts

    assert "force_out" in drafts.CONSTRAINT_DEFAULTS
    assert drafts.CONSTRAINT_DEFAULTS["force_out"] == []
    assert drafts.normalize({"force_out": ["7"]})["force_out"] == [7]
    # A draft written before the field carries no key at all.
    assert drafts.normalize({"lock": [1]})["force_out"] == []


def test_the_drafts_re_solve_passes_it_and_the_free_hit_branch_does_not():
    import inspect

    from gaffer.web.routers import drafts as dr

    src = inspect.getsource(dr)
    assert "force_out=list(req.force_out)" in src
    fh = src[src.index('elif chip == "freehit"'):src.index("else:", src.index(
        'elif chip == "freehit"'))]
    assert "force_out" not in fh
