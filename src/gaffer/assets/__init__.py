"""Data files shipped with the package.

``bootstrap_sample.json`` is a real ``bootstrap-static`` payload, kept here
rather than under ``tests/`` so the offline backtest can read the live scoring
rules from an installed wheel instead of a repo-relative path.
"""

from __future__ import annotations

import json
from importlib.resources import files

BOOTSTRAP_SAMPLE = "bootstrap_sample.json"


def load_bootstrap_sample() -> dict:
    """The bundled ``bootstrap-static`` payload."""
    return json.loads(
        files(__package__).joinpath(BOOTSTRAP_SAMPLE).read_text(encoding="utf-8")
    )


UNDERSTAT_OVERRIDES = "understat_overrides.json"


def load_understat_overrides() -> dict:
    """The bundled ``understat_id -> FPL code`` override table.

    Shipped in the package rather than under ``data/`` because it is curated
    knowledge, not fetched data: it belongs in git and in the wheel, and it
    survives a wiped data directory.
    """
    return json.loads(
        files(__package__).joinpath(UNDERSTAT_OVERRIDES).read_text(
            encoding="utf-8")
    )


DECISION_PRIORS = "decision_priors.json"


def decision_priors_exist() -> bool:
    """Whether the calibrated decision priors are shipped.

    Unlike the other two assets in this package, this one is genuinely
    optional: spec §7's degradation rail says a clone without it must fall
    back to a flat ``ft_value`` and flat chip thresholds, which is exactly
    the pre-v4c behaviour.
    """
    return files(__package__).joinpath(DECISION_PRIORS).is_file()


def load_decision_priors() -> dict | None:
    """The calibrated λ and θ inputs, or ``None`` when the asset is absent.

    ``None`` rather than an empty dict, so a caller cannot accidentally treat
    "no calibration" as "calibration says zero" — the two mean opposite things
    to the chip policy.
    """
    if not decision_priors_exist():
        return None
    return json.loads(
        files(__package__).joinpath(DECISION_PRIORS).read_text(
            encoding="utf-8"))


INJURY_CURVES = "injury_return_curves.json"


def injury_curves_exist() -> bool:
    """Whether the calibrated per-injury return curves are shipped.

    Optional like :data:`DECISION_PRIORS` and for the same reason: spec §7's
    degradation rail says a clone without it falls back to the pooled curve
    and then to the flat ``RECOVERY`` geometric, which is the pre-v5
    behaviour exactly.
    """
    return files(__package__).joinpath(INJURY_CURVES).is_file()


def load_injury_curves() -> dict | None:
    """``{"curves": {type: [P(returned by h)]}, "pooled": [...]}``, or None.

    ``None`` rather than an empty dict, so a caller cannot mistake "no
    calibration" for "calibration says he never returns" — the two are
    opposite instructions to the horizon decay.
    """
    if not injury_curves_exist():
        return None
    return json.loads(
        files(__package__).joinpath(INJURY_CURVES).read_text(
            encoding="utf-8"))
