"""v17g §2.4 — the helper the older ordering rails read through."""
from __future__ import annotations

from tests.advise_source import advise_source


def test_the_helper_reads_the_weekly_pipeline():
    """Whatever the pipeline is split into, this is the text the rails in
    twelve other files match against."""
    src = advise_source()
    assert "client.get_bootstrap()" in src
    assert "pool = build_pool(" in src


def test_the_league_block_still_precedes_the_tilt_and_the_pool():
    """The chain six of those files pin, asserted once here as well.

    It straddles the split — ``fetch_rival_entries`` is a fetch and
    ``build_pool`` is a solve — so it is the assertion that proves the
    concatenation is in pipeline order rather than in any other.
    """
    src = advise_source()
    assert (src.index("fetch_rival_entries(") < src.index("tilt_ep(")
            < src.index("pool = build_pool("))
