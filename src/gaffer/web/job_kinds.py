"""The job kinds the browser may start (spec §5, v7c F1, v7d F1/F2).

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


def run_snapshot_job() -> dict:
    """``gaffer snapshot`` — the daily availability log (v7c F1).

    ``run_snapshot`` prints its own result line and answers ``None`` on any
    failure, so the only work here is turning that into the row count the
    job record carries.
    """
    from gaffer.snapshot import SNAPSHOT_PATH, run_snapshot

    rows = int(run_snapshot() or 0)
    print(f"Wrote {rows} availability rows to {SNAPSHOT_PATH}.")
    return {"rows": rows}


def run_train_and_advise_fast() -> dict:
    """``gaffer advise --fast`` — the same run with the scenario sweep off.

    Not a second implementation: it is the advise kind's own body under a
    config with ``scenarios_n=0``, which is the byte-pinned pre-v4c rail
    (``tests/test_v4c_degradation.py``). Roughly five minutes cheaper on a
    Thursday when the sweep's answer is not what is being asked for.
    """
    import dataclasses

    from gaffer.config import load_config

    return run_train_and_advise(
        dataclasses.replace(load_config(), scenarios_n=0))


def run_track_pens() -> dict:
    """``gaffer track-pens`` — the standing penalty-term report (v7d F2).

    ``track_pens`` never raises: a missing live season comes back as an empty
    report carrying a note, which is a finished job with zero gameweeks, not
    a failed one. The printed table is ``format_tracker``'s, character for
    character the same thing the CLI prints.
    """
    from gaffer.pen_tracker import (format_tracker, save_tracker,
                                    track_pens)

    report = track_pens()
    path = save_tracker(report)
    print(format_tracker(report))
    print(f"Wrote {path}")
    return {"gws": len(report.get("gws", []))}


JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "advise-fast": run_train_and_advise_fast,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
    "snapshot": run_snapshot_job,
    "track-pens": run_track_pens,
}
"""The allow-list. A kind not in here is a 404, never an exec of user input."""
