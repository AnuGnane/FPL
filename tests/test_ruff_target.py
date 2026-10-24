"""ruff lints for the Python the project runs (holiday F-136).

ROADMAP candidate 7, in F-110's shape (``tests/test_doc_pins.py``, one
number read from its home and held against the lines that quote it). The
floor's home is ``requires-python`` in ``pyproject.toml``; ruff's
``target-version`` and ``.python-version`` must name the same major.minor.
They had drifted: ruff said ``py311`` while the project required 3.12, so
it linted for a Python nothing ran.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


def ruff_target_mismatch(pyproject: str, python_version: str) -> str | None:
    """Return why the three disagree, or None when they name one floor."""
    data = tomllib.loads(pyproject)
    m = re.search(r">=\s*(\d+)\.(\d+)", data["project"]["requires-python"])
    if m is None:
        return "requires-python has no >= bound"
    major, minor = m.groups()
    problems = []
    target = data["tool"]["ruff"]["target-version"]
    if target != f"py{major}{minor}":
        problems.append(f"ruff target-version is {target}, the floor is {major}.{minor}")
    pinned = python_version.strip()
    if pinned != f"{major}.{minor}" and not pinned.startswith(f"{major}.{minor}."):
        problems.append(f".python-version is {pinned}, the floor is {major}.{minor}")
    return "; ".join(problems) or None


def test_ruff_targets_the_python_floor():
    problem = ruff_target_mismatch(
        Path("pyproject.toml").read_text(), Path(".python-version").read_text()
    )
    assert problem is None, problem


def test_a_target_below_the_floor_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nrequires-python = ">=3.12"\n\n[tool.ruff]\ntarget-version = "py311"\n'
    )
    problem = ruff_target_mismatch(pyproject.read_text(), "3.13\n")
    assert problem is not None
    assert "py311" in problem and ".python-version is 3.13" in problem


def test_ruff_selects_the_pyupgrade_family():
    """Holiday F-188 turned ``UP`` on; dropping it from ``select`` would let
    ``timezone.utc`` and quoted annotations creep back without a word."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "UP" in data["tool"]["ruff"]["lint"]["select"]


def test_ruff_selects_the_simplify_family():
    """Holiday F-189 turned ``SIM`` on, in F-188's shape: the family stays
    selected or this fails, so it cannot be dropped silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "SIM" in data["tool"]["ruff"]["lint"]["select"]


def test_ruff_selects_the_c4_pie_ret_and_era_families():
    """Holiday F-201 turned ``C4``, ``PIE``, ``RET`` and ``ERA`` on, in
    F-188's shape: each family stays selected or this fails."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"C4", "PIE", "RET", "ERA"} <= set(select)


def test_ruff_selects_the_ble_family_and_strikes_unused_noqa():
    """Holiday F-204 turned ``BLE`` on, so the ``# noqa: BLE001`` marks
    ``CLAUDE.md`` asks for are read by ruff rather than being comments, and
    ``RUF100`` with it, so a mark that guards nothing fails the gate."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"BLE", "RUF100"} <= set(select)


def test_ruff_selects_the_pytest_style_family_without_the_composite_assert():
    """Holiday F-205 turned ``PT`` on, in F-188's shape, with ``PT018`` ruled
    out: the tests' composite asserts read as one sentence, and splitting 656
    of them names no new failure."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    lint = data["tool"]["ruff"]["lint"]
    assert "PT" in lint["select"]
    assert "PT018" in lint["ignore"]


def test_ruff_selects_the_perf_furb_and_pyi_families():
    """Holiday F-206 turned ``PERF``, ``FURB`` and ``PYI`` on, in F-188's
    shape: each family stays selected or this fails, so a loop that appends
    or a ``re.I`` alias cannot come back silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"PERF", "FURB", "PYI"} <= set(select)


def test_ruff_selects_the_pylint_warning_convention_and_error_families():
    """Holiday F-207 turned ``PLW``, ``PLC`` and ``PLE`` on, in F-188's shape,
    with ``PLC0415`` ruled out: heavy imports sit in the functions that need
    them so ``gaffer --help`` and the web app start without the model stack."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    lint = data["tool"]["ruff"]["lint"]
    assert {"PLW", "PLC", "PLE"} <= set(lint["select"])
    assert "PLC0415" in lint["ignore"]


def test_ruff_selects_the_pep8_naming_family():
    """Holiday F-208 turned ``N`` on, in F-188's shape: the family stays
    selected or this fails, so a camelCase helper or an aliased module
    cannot come back silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert "N" in data["tool"]["ruff"]["lint"]["select"]


def test_ruff_selects_the_string_concatenation_quotes_and_type_checking_families():
    """Holiday F-209 turned ``ISC``, ``Q`` and ``TC`` on, in F-188's shape: a
    missing comma between two strings, a single-quoted literal or an
    annotation-only import at runtime cannot come back silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"ISC", "Q", "TC"} <= set(select)


def test_ruff_selects_the_pathlib_datetimez_and_logging_families():
    """Holiday F-215 turned ``PTH``, ``DTZ`` and ``LOG`` on, in F-188's shape:
    an ``os`` path call beside ``pathlib``, a naive ``datetime`` with no reason
    given or a ``log.exception`` outside an ``except`` cannot come back
    silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    assert {"PTH", "DTZ", "LOG"} <= set(select)


def test_ruff_selects_the_tryceratops_family_without_the_vanilla_message_rule():
    """Holiday F-216 turned ``TRY`` on, in F-205's shape: a ``return`` that
    belongs in the ``try``'s ``else`` or a ``ValueError`` on a type check
    cannot come back silently. ``TRY003`` stays ignored: a message built in
    the ``raise`` call is the repo's idiom (276 sites)."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    lint = data["tool"]["ruff"]["lint"]
    assert "TRY" in lint["select"]
    assert "TRY003" in lint["ignore"]


def test_ruff_selects_the_ruff_family_without_the_unicode_prose_rules():
    """Holiday F-217 turned ``RUF`` on, in F-205's shape: a list built by
    ``+`` on a literal, a mutable class attribute without ``ClassVar`` or an
    unescaped ``pytest.raises(match=)`` cannot come back silently.
    ``RUF001`` to ``RUF003`` stay ignored: the dashes, arrows and
    multiplication signs they flag are the house prose ``CLAUDE.md`` asks
    for. F-218 struck ``RUF046`` from ``ignore``: an ``int()`` around a
    value already an ``int`` cannot come back silently."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    lint = data["tool"]["ruff"]["lint"]
    assert "RUF" in lint["select"]
    assert {"RUF001", "RUF002", "RUF003"} <= set(lint["ignore"])
    assert "RUF046" not in lint["ignore"]


def test_ruff_selects_the_fifteen_families_that_cost_nothing_today():
    """Holiday F-222 turned on the fifteen families with no site on
    2026-10-24 (ruff 0.17.2), in F-215's shape: a ``sys.version``
    comparison, a ``breakpoint()``, a stray shebang, a blocking call in an
    ``async`` route, a ``str.join`` over literal parts, a ``raise X()`` with
    empty parens, an unconventional ``numpy`` alias, a legacy ``np.random``
    call, a blanket ``type: ignore`` or ``noqa``, a missing ``__slots__`` on a
    ``str`` or ``tuple`` subclass, a banned relative import, an f-string in
    ``_()``, an f-string or ``%`` in a ``logging`` call and a shadowed builtin
    cannot come back silently. ``FA`` is inert at ``py312`` and rides along so
    a lowered target would speak."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    select = data["tool"]["ruff"]["lint"]["select"]
    fifteen = {"YTT", "T10", "EXE", "ASYNC", "FLY", "RSE", "ICN", "NPY", "PGH",
               "SLOT", "TID", "INT", "FA", "G", "A"}
    assert fifteen <= set(select)


def test_ruff_selects_the_pandas_family_without_the_scalar_accessor_rule():
    """Holiday F-223 turned ``PD`` on, in F-217's shape: a ``.values`` where
    ``.to_numpy()`` says what comes back, or a ``nunique() == 1`` with no reason
    given, cannot come back silently. ``PD008`` stays ignored: ``.at`` is
    pandas' own scalar accessor and the faster one."""
    data = tomllib.loads(Path("pyproject.toml").read_text())
    lint = data["tool"]["ruff"]["lint"]
    assert "PD" in lint["select"]
    assert "PD008" in lint["ignore"]
