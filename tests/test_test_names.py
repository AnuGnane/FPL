"""Holiday F-73: every test name is a sentence.

``CLAUDE.md``'s rule ("Writing style"): test names are sentences
(``test_an_agreeing_objective_is_not_repeated``). A name is a sentence here
when it carries at least three words after ``test_`` (a word holds a letter,
so ``404`` rides along but does not count) and is not a bare parameter stub
(``test_1``, ``test_case2``). Python only; vitest's ``it('…')`` strings are
prose already.

Nothing is renamed: the files that hold shorter names today are an allowlist
pinned at each file's count, in F-69's shape, so a new short name anywhere
fails, and a file that loses its last one fails until it is struck here.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# The short names held at F-73, by file. Value: how many that file holds.
ALLOWED = {
    "tests/test_bootstrap.py": 1,  # test_next_gw
    "tests/test_client.py": 1,  # test_retries_on_429
    "tests/test_components.py": 1,  # test_card_penalty
    "tests/test_config.py": 1,  # test_load_config
    "tests/test_parse.py": 1,  # test_to_int
    "tests/test_store.py": 1,  # test_exists
    "tests/test_v16_brief.py": 1,  # test_first_sentence
}

STUB = re.compile(r"[a-z]*_?\d+")


def is_sentence(name: str) -> bool:
    rest = name.removeprefix("test_")
    words = [w for w in rest.split("_") if re.search(r"[A-Za-z]", w)]
    return len(words) >= 3 and not STUB.fullmatch(rest)


def _short_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
        and not is_sentence(node.name)
    ]


def _census() -> dict[str, list[str]]:
    found = {}
    for path in sorted(TESTS.rglob("*.py")):
        short = _short_names(path)
        if short:
            found[path.relative_to(ROOT).as_posix()] = short
    return found


def test_no_short_test_name_lives_outside_the_allowlist():
    stray = {f: names for f, names in _census().items() if f not in ALLOWED}
    assert stray == {}


def test_each_allowlisted_file_holds_exactly_the_count_it_held_at_f73():
    census = _census()
    counts = {f: len(census.get(f, [])) for f in ALLOWED}
    gone = [f for f, n in counts.items() if n == 0]
    assert counts == ALLOWED, (
        f"strike {gone} from ALLOWED: its short names are gone" if gone
        else "a short name was added or renamed in an allowlisted file"
    )


def test_the_allowlist_names_only_files_that_exist():
    assert [f for f in ALLOWED if not (ROOT / f).is_file()] == []


def test_a_sentence_passes_and_short_names_and_stubs_do_not():
    assert is_sentence("test_an_agreeing_objective_is_not_repeated")
    assert is_sentence("test_a_full_queue_is_a_429")
    for name in ("test_1", "test_case2", "test_case_2", "test_to_int",
                 "test_retries_on_429", "test_exists"):
        assert not is_sentence(name), name
