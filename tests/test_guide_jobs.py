"""Every job kind is named in the GUIDE (holiday F-96).

ROADMAP candidate 7, in F-87's shape (``tests/test_guide_scripts.py``): a
kind the GUIDE never names is a button or a POST a reader cannot trace,
which is how ``advise-fast`` and ``refresh-data`` went unnamed. Membership
only: the total is pinned in ``tests/test_v12_w1_degradation.py`` alone (the
meta-rail), so no count here.
"""

from __future__ import annotations

import re
from pathlib import Path

from gaffer.web.job_kinds import JOB_KINDS

GUIDE = Path("docs/GUIDE.md")


def test_every_job_kind_is_named_in_the_guide():
    text = GUIDE.read_text()
    # In backticks, bare or as its CLI command (§8 writes the options inside
    # them, `gaffer field-scrape [--gw N]`): a prose "sensitivity" or the
    # `advise` in `advise-fast` must not stand in for the kind (F-96).
    unnamed = [
        kind
        for kind in JOB_KINDS
        if not re.search(rf"`({re.escape(kind)}|gaffer {re.escape(kind)}( [^`]*)?)`", text)
    ]
    assert unnamed == [], unnamed
