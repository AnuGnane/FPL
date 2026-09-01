"""v9d's degradation rails (gate G3).

Every rail here is a state a real machine reaches: a server started with a
worker count, a parquet refreshed under a warm cache, a job cancelled rather
than timed out, a gameweek graded from an artifact written after the whistle.
The pins at the end are the counts that did *not* move — twelve job kinds,
forty-eight config fields — and the one that moved by exactly one.

The most valuable assertion in the file is
``test_the_ui_serves_an_app_instance_and_never_a_worker_count``. Everything
about the job runner's state — the single lane, the in-memory run records, the
SSE line buffers — lives on one process's ``app.state.job_runner``. Nothing in
the tree says so today, and the day someone "optimises" the serve command into
an import string with ``workers=4`` the failure is not a crash: it is a browser
watching a job that a different worker is running, forever.
"""

from __future__ import annotations

import inspect


# =====================================================================
# Block 1 — §2, the single-process contract
# =====================================================================

def _uvicorn_call() -> str:
    """The text of ``cli.ui``'s ``uvicorn.run(...)`` call.

    Source inspection rather than execution, for the reason plan A6 gives:
    the thing being defended is the *shape of a call*, and actually starting a
    server would be a different test that could pass while the shape was
    wrong. The same idiom guards the protected advice write at
    ``tests/test_v9c_degradation.py:337``.
    """
    import gaffer.cli as cli_mod

    source = inspect.getsource(cli_mod)
    start = source.index("uvicorn.run(")
    return source[start:source.index(")", start) + 1]


def test_the_ui_serves_an_app_instance_and_never_a_worker_count():
    """Spec §2. ``uvicorn`` forks workers only when it is handed an import
    string; handed an app *instance* it cannot, which is the only reason the
    single lane and the SSE buffers on ``app.state.job_runner`` work at all
    today. Both halves are asserted, because either alone can be defeated."""
    call = _uvicorn_call()
    assert "create_app()" in call
    assert '"' not in call.split(",")[0], (
        "the first argument became an import string — uvicorn can fork "
        "workers off one of those, and every job-runner invariant assumes "
        "one process")
    assert "workers" not in call


def test_the_contract_is_stated_where_the_server_starts():
    """A rail that only pins the call shape teaches nobody why. The reason
    has to be readable at the call site, or the next person removes the
    constraint correctly and breaks the product."""
    import gaffer.cli as cli_mod

    source = inspect.getsource(cli_mod)
    window = source[source.index("uvicorn.run(") - 900:
                    source.index("uvicorn.run(")]
    assert "single process" in window


def test_the_job_runner_says_it_is_per_process():
    """The other end of the same contract. ``JobRunner`` is where the state
    lives, so it is where a reader looks first."""
    from gaffer.web.jobs import JobRunner

    assert "single process" in (JobRunner.__doc__ or "")
