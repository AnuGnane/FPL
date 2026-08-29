"""The four job kinds the browser may start (spec §5).

Every entry is the *same* callable the CLI runs. ``advise`` and
``refresh-data`` already existed as job bodies for the v6 rerun buttons and are
reused by reference; ``evaluate`` and ``news-shadow`` are thin wrappers around
``gaffer.evaluation`` that mirror ``cli.py::evaluate`` line for line. Nothing
here decides anything, and nothing here re-implements a pipeline.

The printing is deliberate: the runner captures the job thread's stdout, so a
``print`` reached from here on that thread becomes a streamed progress line.
Work these functions hand to another thread is *not* captured — it prints to
the server's terminal, which is where a background thread's output belongs.
"""

from __future__ import annotations

from typing import Any, Callable

from gaffer.web.routers.advice import run_train_and_advise
from gaffer.web.routers.meta import run_data_refresh


def run_evaluate() -> dict:
    """``gaffer evaluate`` with its default mode."""
    from gaffer.evaluation import (evaluate_current, format_report,
                                   save_evaluation)

    payload = evaluate_current()
    path = save_evaluation("current", payload)
    print(format_report("current", payload))
    print(f"Wrote {path}")
    return {"key": "current", "path": str(path)}


def run_news_shadow() -> dict:
    """``gaffer evaluate --news-shadow`` (gate N2)."""
    from gaffer.evaluation import (evaluate_news_shadow, format_report,
                                   save_evaluation)

    payload = evaluate_news_shadow()
    path = save_evaluation("news_shadow", payload)
    print(format_report("news_shadow", payload))
    print(f"Wrote {path}")
    return {"key": "news_shadow", "path": str(path)}


JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
}
"""The allow-list. A kind not in here is a 404, never an exec of user input."""
