"""Fitted models on disk, plus a sidecar of how they were made.

joblib ships with scikit-learn, so this costs no new dependency. Every
save writes ``<name>.joblib`` and ``<name>.meta.json``; the meta is the
only record of what a pickle was trained on, so it always gets a
``saved_at`` stamp even when the caller passes nothing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

MODELS_DIR = Path("models")


def save_model(obj, name: str, meta: dict | None = None) -> Path:
    """Pickle ``obj`` to ``models/<name>.joblib`` and write its metadata."""
    MODELS_DIR.mkdir(exist_ok=True)
    path = MODELS_DIR / f"{name}.joblib"
    joblib.dump(obj, path)
    meta = dict(meta or {})
    meta["saved_at"] = datetime.now(timezone.utc).isoformat()
    (MODELS_DIR / f"{name}.meta.json").write_text(json.dumps(meta, indent=1))
    return path


def load_model(name: str):
    """Unpickle a previously saved model. Raises if it was never saved."""
    return joblib.load(MODELS_DIR / f"{name}.joblib")


def model_exists(name: str) -> bool:
    """True when ``name`` has been saved — lets callers skip a refit."""
    return (MODELS_DIR / f"{name}.joblib").exists()


def save_params(name: str, params: dict) -> Path:
    """Write a small JSON artifact to ``models/<name>.params.json``.

    Not everything the training run learns is a pickle. The fitted odds blend
    weight is one float, read at prediction time by code that has no business
    unpickling a model to get it, and worth being able to read with ``cat``
    when a number in a report looks wrong. Same ``saved_at`` stamp as
    :func:`save_model`, for the same reason.
    """
    MODELS_DIR.mkdir(exist_ok=True)
    path = MODELS_DIR / f"{name}.params.json"
    payload = dict(params)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=1))
    return path


def params_exist(name: str) -> bool:
    return (MODELS_DIR / f"{name}.params.json").exists()


def load_params(name: str) -> dict:
    """A previously saved params artifact, or ``{}`` when there is none.

    Empty rather than an exception: a fresh clone has no artifacts, and every
    reader here has a documented default to fall back to.
    """
    path = MODELS_DIR / f"{name}.params.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())
