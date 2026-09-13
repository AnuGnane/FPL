"""The one UTC day key the daily logs share.

``snapshot``, ``price_log``, ``price_timing`` and ``data/field.py`` each
bank one row per player per day and each needs the same answer to "which
day is this?". It lived in ``gaffer.snapshot`` until v18d §2, which made
every other log's import of ``snapshot`` an edge it did not want: the
price reader took the whole availability log — and, through it,
``artifacts`` and ``served`` — to learn a date string. A leaf module owns
the key instead, and nothing that wants the date pulls a log in with it.
"""

from __future__ import annotations

from datetime import datetime, timezone


def snap_date(now: datetime | None = None) -> str:
    """Today in UTC, ``YYYY-MM-DD``. The log's idempotency key.

    UTC rather than local time so a machine that travels, or one running the
    job either side of a clock change, cannot bank two "days" for one.
    """
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
