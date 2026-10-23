"""Every npm script is named by a doc, CI or another script (holiday F-162).

ROADMAP candidate 7, the converse of F-131 (`tests/test_claude_commands.py`)
as F-151 was F-100's: F-131 checks that every `npm run <key>` a doc names is a
key of `frontend/package.json`'s ``scripts``; this checks that every key is
named somewhere a developer or CI reads it, so a script nobody can find is
either documented or retired. A key is named when `npm run <key>` (or
`npm test` for ``test``) appears in `CLAUDE.md`, the README, the GUIDE, the
CI workflow, a file under `frontend/scripts/`, or another script's command
line. Membership only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGE = Path("frontend/package.json")
READERS = [Path("CLAUDE.md"), Path("README.md"), Path("docs/GUIDE.md"),
           Path(".github/workflows/ci.yml"),
           *sorted(Path("frontend/scripts").iterdir())]


def unnamed(scripts: dict[str, str], texts: list[str]) -> list[str]:
    """The script keys no text and no other script's command line names."""
    def named(key: str, text: str) -> bool:
        pattern = rf"npm run {re.escape(key)}(?![\w:-])"
        if key == "test":
            pattern += r"|npm test(?![\w:-])"
        return re.search(pattern, text) is not None

    return [key for key in scripts
            if not any(named(key, text) for text in texts)
            and not any(named(key, line) for other, line in scripts.items()
                        if other != key)]


def test_every_npm_script_is_named_by_a_doc_ci_or_another_script():
    scripts = json.loads(PACKAGE.read_text())["scripts"]
    assert len(scripts) >= 6, sorted(scripts)
    missing = [str(path) for path in READERS if not path.is_file()]
    assert missing == [], "a reader the rail scans is gone"
    texts = [path.read_text() for path in READERS]
    assert unnamed(scripts, texts) == []


def test_an_unnamed_script_fails_the_check(tmp_path):
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"scripts": {
        "check": "vitest run && npm run lint", "lint": "eslint .",
        "test": "vitest", "stray": "node stray.js", "types": "node gen.ts",
        "self": "npm run self"}}))
    scripts = json.loads(package.read_text())["scripts"]
    docs = [("cd frontend && npm run check\nnpm test\nnpm run types -- --check\n"
             "npm run typescript")]
    assert unnamed(scripts, docs) == ["stray", "self"]
    assert unnamed(scripts, []) == ["check", "test", "stray", "types", "self"]
