"""GUIDE §13's job timeouts quote the job kinds' constants (holiday F-141).

ROADMAP candidate 7, in F-110's shape (``tests/test_doc_pins.py``): §13 tells
a reader the runner reaps a wedged holder after "120 s for fast kinds, 30 min
for slow ones", and those numbers live in ``web/job_kinds.py``'s
``ABANDON_TIMEOUT_S`` and in ``web/jobs.py``'s ``ADVISE_TIMEOUT_S``, the
lookup's default. Nothing held the sentence to them, so a retuned timeout
could leave the GUIDE quoting the old one. The test reads both modules and
edits neither (``jobs.py`` is orchestrator-only).
"""

from __future__ import annotations

import re
from pathlib import Path

from gaffer.web.job_kinds import ABANDON_TIMEOUT_S
from gaffer.web.jobs import ADVISE_TIMEOUT_S
from tests.test_guide_commands import _section

GUIDE = Path("docs/GUIDE.md")

_DURATION = re.compile(r"\b\d+ (?:s|min)\b")


def _render(seconds: float) -> str:
    # The GUIDE's own spelling: seconds for the short reap, whole minutes
    # from ten minutes up (F-141 PR ruling 1: the GUIDE reads "120 s", not
    # "2 min", so the package's 60 s threshold could not stand as written).
    if seconds >= 600 and seconds % 60 == 0:
        return f"{int(seconds // 60)} min"
    return f"{int(seconds)} s"


def _stuck_job_sentence(text: str) -> str:
    return _section(_section(text, "## 13. "), "**A job seems stuck", "\n- **")


def _misquoted(sentence: str) -> tuple[list[str], list[str]]:
    wanted = {_render(s) for s in {*ABANDON_TIMEOUT_S.values(), ADVISE_TIMEOUT_S}}
    quoted = set(_DURATION.findall(sentence))
    return sorted(wanted - quoted), sorted(quoted - wanted)


def test_guide_section_thirteen_quotes_every_job_timeout_and_no_other():
    sentence = _stuck_job_sentence(GUIDE.read_text())
    assert _misquoted(sentence) == ([], [])


def test_the_rail_bites_on_a_sentence_quoting_a_stale_timeout():
    stale = (
        "## 13. Troubleshooting\n\n- **A job seems stuck in the UI** — the "
        "runner reaps a wedged holder automatically (120 s for fast kinds, "
        "10 min for slow ones).\n- **Next**\n"
    )
    missing, extra = _misquoted(_stuck_job_sentence(stale))
    assert missing == ["30 min"]
    assert extra == ["10 min"]


def test_the_rendering_matches_the_guide_spelling():
    assert _render(120.0) == "120 s"
    assert _render(1800.0) == "30 min"
