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
    prices_banked: int | None = None
    """v19b §2.1: rows the price step wrote before the solve, ``None`` when
    the step was off or could not bank (a note in the log, never a failure)."""

    def record(self) -> dict:
        """``{"gw", "expected_pts", "brief"}`` — byte-for-byte what the
        v16 web body returned, so the stored job record is unchanged."""
        return {"gw": self.advice.gw, "expected_pts": self.advice.expected_pts,
                "brief": self.brief}


def bank_price_reading(client: "FPLClient | None" = None, *,
                       log: Callable[[str], None] = print) -> int | None:
    """Bank today's price reading, the way the Thursday plist's ``gaffer
    prices`` does, so a browser or CLI solve sees a same-day price table.

    v19b §2.1 (ruling 4). Until v19b only the plist banked prices before the
    solve, so a Friday re-run from the web saw Thursday's table and an
    untimed sale — GUIDE §12.4's first residual. Never raises: the price
    table is an input the solve can do without, which is why the plist
    chained the two commands with ``;`` rather than ``&&``. The bootstrap is
    fetched once more rather than threaded out of ``run_advise``, because a
    same-day re-bank replaces the day's rows (``append_prices``) and a
    second fetch is cheaper than a second seam through the advice path.
    """
    try:
        from gaffer.api.client import FPLClient
        from gaffer.data.bootstrap import build_players
        from gaffer.price_log import bank_prices

        players = build_players((client or FPLClient()).get_bootstrap())
        return bank_prices(players)
    except Exception as exc:  # noqa: BLE001 — an input the solve can do without
        log(f"price reading not banked: {exc}")
        return None


def weekly_run(cfg: "Config", *, client: "FPLClient | None" = None,
               train: bool = True, bank_prices: bool = True,
               log: Callable[[str], None] = print) -> RunResult:
    """Train (when asked), bank prices (unless told not to), advise, render,
    brief.

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
        trained, rows = True, len(frame)
        log(f"Trained on {rows} player-GW rows. Models saved to models/.")
    from gaffer.advise import run_advise
    from gaffer.report.render import render_report
    from gaffer.tracking import latest_health

    # v19b §2.1: before the solve, after training, so the price line the
    # trace reads is today's. A module-level call so the golden harness and
    # the unit tests stub one name (``gaffer.pipeline.bank_price_reading``).
    prices = bank_price_reading(client, log=log) if bank_prices else None
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
                     trained=trained, training_rows=rows, prices_banked=prices)
