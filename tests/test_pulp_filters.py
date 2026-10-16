"""The four PuLP filters stand until PuLP 4, and PuLP 4 says so (holiday F-89).

v18g's "Left open" line (ROADMAP, "the PuLP 4 migration the filters
defer") and GUIDE §12.4: ``pyproject.toml``'s ``filterwarnings`` hides four
PuLP 3.3 deprecations, each with a "Migrate at PuLP 4" comment. Below 4 the
warnings still fire, so a tidy must not drop the filters; at 4 the builders
they hide are gone or changing, so the day ``uv.lock`` moves this file fails
and names the migration rather than letting the suite pass through.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pulp

PYPROJECT = Path("pyproject.toml")

# The messages the four entries match, as pyproject.toml writes them.
PULP_FILTERS = (
    r"ignore:LpVariable\.dicts is deprecated:DeprecationWarning",
    r"ignore:Using LpProblem\.constraints as a dict mapping is deprecated:DeprecationWarning",
    r"ignore:Constructing LpVariable:DeprecationWarning",
    r"ignore:PULP_CBC_CMD is deprecated:DeprecationWarning",
)

# What each comment says to migrate to (pyproject.toml's filter comments).
BUILDERS = (
    "prob.add_variable_dicts",
    "get_constraint_by_name",
    "prob.add_variable",
    "COIN_CMD",
)


def _filters() -> list[str]:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["tool"]["pytest"]["ini_options"]["filterwarnings"]


def _major(version: str) -> int:
    return int(version.split(".", 1)[0])


def _migration_due(version: str) -> str | None:
    """None below PuLP 4; at 4 or above, the message the suite fails with."""
    if _major(version) < 4:
        return None
    return (
        f"PuLP {version} is installed: migrate optimize/ off the four deprecated "
        f"builders ({', '.join(BUILDERS)}) and drop the four filterwarnings "
        f"entries ({'; '.join(PULP_FILTERS)}) from pyproject.toml"
    )


def test_the_four_pulp_filters_stand_while_pulp_is_below_4():
    if _major(pulp.__version__) >= 4:
        return  # the next test carries the verdict
    filters = _filters()
    missing = [f for f in PULP_FILTERS if f not in filters]
    assert missing == [], missing


def test_pulp_4_fails_the_suite_naming_the_migration():
    message = _migration_due(pulp.__version__)
    assert message is None, message


def test_the_migration_message_names_the_four_filters_and_their_builders():
    assert _migration_due("3.3.2") is None
    message = _migration_due("4.0.0")
    assert message is not None
    for needle in (*PULP_FILTERS, *BUILDERS):
        assert needle in message, needle
