"""v17c — the golden board harness.

The second adapter behind ``run_advise(cfg, client)``: a client that replays
recorded FPL responses (spec §2.1), the config the golden was recorded under
(§2.3), the scratch working directory it runs in (§2.4), the input-hash
skip rule (§2.6), and the ``--record`` / ``--write`` entry points (§2.10).
Lives in ``tests/`` because nothing in the package needs it.
"""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

from gaffer.api.client import FPLClient

GOLDEN_DIR = Path(__file__).resolve().parent / "data" / "golden_board"
BUNDLE_NAME = "responses.json.gz"
HEADER_NAME = "header.json"
EXPECTED_DIR = "expected"


def save_bundle(directory: Path, bodies: dict[str, object]) -> Path:
    """One gzip'd JSON object, API path → body, keys sorted so a re-record
    with the same answers is the same bytes (spec §2.2)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / BUNDLE_NAME
    raw = json.dumps(bodies, sort_keys=True, separators=(",", ":")).encode()
    # GzipFile rather than gzip.open: only the former takes ``mtime``, and a
    # zero there keeps the clock out of the header so a re-record with the same
    # answers really is the same bytes (spec §2.2).
    with open(path, "wb") as raw_fh:
        # An empty filename for the same reason: left to itself GzipFile would
        # stamp the absolute path of the file handle into the header.
        with gzip.GzipFile(filename="", fileobj=raw_fh, mode="wb",
                           compresslevel=9, mtime=0) as fh:
            fh.write(raw)
    return path


def load_bundle(directory: Path) -> dict[str, object]:
    with gzip.open(Path(directory) / BUNDLE_NAME, "rb") as fh:
        return json.loads(fh.read())


class RecordedClient(FPLClient):
    """Replays a bundle. Overrides ``_get`` only, so every public method the
    parent has or gains is covered by the one lookup; never opens a socket;
    never writes a ``data/raw`` snapshot (the parent's ``__init__`` is not
    called, so there is no ``raw_dir`` and no ``httpx.Client``)."""

    def __init__(self, directory: Path = GOLDEN_DIR):
        self.directory = Path(directory)
        self._bodies = load_bundle(self.directory)

    def _get(self, path: str, snapshot: str | None = None):
        if path not in self._bodies:
            raise KeyError(f"{path} was not recorded in {self.directory}")
        # A copy per call: the pipeline mutates frames it builds from these
        # dicts, and one caller's edit must not leak into the next replay.
        return copy.deepcopy(self._bodies[path])


class RecordingClient(FPLClient):
    """The same override the other way round: fetch live, bank the body.
    ``_live`` is the one seam a test replaces."""

    def __init__(self, directory: Path, **client_kw):
        super().__init__(**client_kw)
        self.directory = Path(directory)
        self._bodies: dict[str, object] = {}

    def _live(self, path: str):
        return super()._get(path, snapshot=None)

    def _get(self, path: str, snapshot: str | None = None):
        body = self._live(path)
        self._bodies[path] = copy.deepcopy(body)
        return body

    def save(self) -> Path:
        return save_bundle(self.directory, self._bodies)
