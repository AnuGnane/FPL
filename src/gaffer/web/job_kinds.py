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


def run_field_scrape_job() -> dict:
    """``gaffer field-scrape`` — the top-10k field sample (v8c F1).

    ``run_field_scrape`` prints its own result line and answers ``None`` on
    every failure, so the only work here is turning that into the row count
    the job record carries. Zero rows is a success, not a failure: it is what
    an already-banked gameweek looks like, which is what the Sunday run sees
    every week the Saturday run worked.
    """
    from gaffer.data.field import FIELD_EO_PATH, run_field_scrape

    rows = int(run_field_scrape() or 0)
    print(f"Logged {rows} field-EO rows to {FIELD_EO_PATH}.")
    return {"rows": rows}


def run_review_job() -> dict:
    """``gaffer review`` — grade the finished gameweeks (v8b F2).

    ``run_review`` prints one line per gameweek and answers ``[]`` on every
    failure, so the only work here is turning that into the count the job
    record carries. Zero gameweeks is a success: it is what an already-
    reviewed season looks like, which is what the Tuesday job sees every week
    the previous run worked.
    """
    from gaffer.review import run_review

    gws = list(run_review() or [])
    print(f"Reviewed {len(gws)} gameweeks into reports/decision_ledger.json.")
    return {"gws": len(gws)}


def run_sensitivity_job() -> dict:
    """``sensitivity`` — K noised re-solves of the saved board (v8e F3).

    The zero-argument wrapper pattern ``run_track_pens`` set: the module does
    the work and prints the human-readable verdict, and the wrapper turns it
    into the three numbers the job record carries. Unlike the pen tracker this
    one *can* raise — with no saved solve state there is nothing to sweep —
    and it should: the runner turns a ``GafferError`` into a failed record
    carrying "run `gaffer advise` first", which is the right thing for a
    button to say.

    Seconds, not minutes: twenty solves of a saved board measured about five
    on the real GW3 pool. It is still a job rather than a request because the
    wall time is the *board's*, not the machine's — a full pool with a long
    horizon is a slower solve than a request should wait on — and because a
    job streams its progress.
    """
    from gaffer.sensitivity import run_sensitivity

    payload = run_sensitivity()
    print(payload["verdict"])
    print(f"{payload['completed']}/{payload['k']} scenarios in "
          f"{payload['wall_s']}s")
    return {"gw": payload["gw"], "k": payload["k"],
            "completed": payload["completed"]}


def _notify_enabled() -> bool:
    """``[digest] notify``, read the way every other serve-time switch is.

    Its own function rather than an inline read so the rail that asserts the
    switch reaches the module has one thing to patch, and so a clone with no
    ``config.toml`` — which ``serving_config`` degrades to defaults for — gets
    its notification rather than an exception.
    """
    from gaffer.config import serving_config

    return bool(serving_config().digest_notify)


def _digest_job(kind: str) -> dict:
    """One digest kind's job body. ``run_digest`` does the work and prints.

    ``None`` back from ``run_digest`` is a *finished* job with zero sections,
    not a failed one — ``run_field_scrape_job``'s trade, for the same reason:
    a Friday with no advice on disk is a real and ordinary state, and a red
    job record for it would train the user to ignore red job records.
    """
    from gaffer.digest import run_digest

    payload = run_digest(kind, notify=_notify_enabled()) or {}
    return {"kind": kind, "gw": payload.get("gw"),
            "sections": len(payload.get("sections") or [])}


def run_digest_friday() -> dict:
    """``gaffer digest --kind friday`` — the pre-deadline briefing (v8f D3)."""
    return _digest_job("friday")


def run_digest_tuesday() -> dict:
    """``gaffer digest --kind tuesday`` — the post-review debrief (v8f D3)."""
    return _digest_job("tuesday")


JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "advise-fast": run_train_and_advise_fast,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
    "snapshot": run_snapshot_job,
    "field-scrape": run_field_scrape_job,
    "review": run_review_job,
    "track-pens": run_track_pens,
    "sensitivity": run_sensitivity_job,
    "digest-friday": run_digest_friday,
    "digest-tuesday": run_digest_tuesday,
}
"""The allow-list. A kind not in here is a 404, never an exec of user input."""
