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
