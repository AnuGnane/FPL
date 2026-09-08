"""The weekly run, once (v17d §2). Train → advise → render → brief.

Three callers, one body: ``cli.advise`` (``train=False``; the Thursday
plist runs ``gaffer train`` first), ``web.job_kinds.run_train_and_advise``
(``train=True``; the button has no separate train step) and, through the
CLI, the launchd job. Nothing here decides anything about the advice: the
steps are the four functions they always were, in the order the web job
ran them since v16, and the brief is the only step that never raises.

Imports are inside the function for the two reasons ``cli.py`` gives:
``--help`` must not load lightgbm, and every test stubs these steps by
module attribute, which only a call-time import sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from gaffer.advise import Advice
    from gaffer.api.client import FPLClient
    from gaffer.config import Config


@dataclass
class RunResult:
    """What each step produced. ``record()`` is the job runner's dict."""

    advice: "Advice"
    report_path: Path
    brief: dict
    trained: bool
    training_rows: int | None

    def record(self) -> dict:
        """``{"gw", "expected_pts", "brief"}`` — byte-for-byte what the
        v16 web body returned, so the stored job record is unchanged."""
        return {"gw": self.advice.gw, "expected_pts": self.advice.expected_pts,
                "brief": self.brief}


def weekly_run(cfg: "Config", *, client: "FPLClient | None" = None,
               train: bool = True,
               log: Callable[[str], None] = print) -> RunResult:
    """Train (when asked), advise, render, brief.

    Train, advise and render raise as they always have — ``SystemExit`` for
    a missing model before any network call, ``GafferError`` for no next
    gameweek — because a pipeline that swallowed those would turn the
    CLI's one-line exit into silence (spec §2.2). The brief cannot fail the
    run: ``run_brief`` never raises, and its import is inside the same
    guard so an ``ImportError`` in ``brief.py`` is a note, not a failure.
    """
    trained, rows = False, None
    if train:
        from gaffer.models.train import load_training_frame, train_all

        frame, team_frame, _ = load_training_frame()
        train_all(frame, team_frame, save=True)
        # v17d §2.3: the row count is what the frame reports, and a frame that
        # reports nothing (a stubbed train step, as in
        # ``tests/test_web_job_kinds_v7c.py``) is still a run that trained —
        # the count is a log line, never a reason to fail the week.
        rows = len(frame) if hasattr(frame, "__len__") else None
        trained = True
        log(f"Trained on {rows} player-GW rows. Models saved to models/."
            if rows is not None else "Trained. Models saved to models/.")
    from gaffer.advise import run_advise
    from gaffer.report.render import render_report
    from gaffer.tracking import latest_health

    advice = run_advise(cfg, client=client)
    report_path = Path(render_report(advice, model_health=latest_health()))
    # v16 §6.5 (plan R1), now v17d §2.2: the brief is chained here, after
    # the report, with the config in force, and never fails the run.
    try:
        from gaffer.brief import run_brief

        brief = run_brief(advice.gw, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        brief = {"gw": advice.gw, "written": False,
                 "note": f"brief not written: {exc}", "path": None}
        log(brief["note"])
    return RunResult(advice=advice, report_path=report_path, brief=brief,
                     trained=trained, training_rows=rows)
