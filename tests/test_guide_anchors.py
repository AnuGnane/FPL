"""Every in-page link in the GUIDE resolves to a heading (holiday F-59).

The contents line for §11 pointed at ``#11-the-version-history-v1-to-v19f``
for two cycles after the heading moved to v19h, so the link went nowhere and
nothing failed. Each ``](#…)`` link is checked against the GitHub slug of
every heading, so the next renumbering fails the gate instead of the reader.
"""

from __future__ import annotations

import re
from pathlib import Path

GUIDE = Path("docs/GUIDE.md")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower-case, punctuation dropped
    (backticks and commas included; hyphens and underscores kept), each
    space a hyphen."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def _anchors(text: str) -> set[str]:
    """Each heading's slug, outside fenced code, with GitHub's ``-1``,
    ``-2`` suffix on a repeated one."""
    seen: dict[str, int] = {}
    anchors = set()
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        match = re.match(r"#{1,6} (.+)", line)
        if fenced or not match:
            continue
        slug = _slug(match.group(1))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def test_the_slug_rule_drops_punctuation_and_hyphenates_spaces():
    assert _slug("11. The version history, v1 to v19h") == (
        "11-the-version-history-v1-to-v19h")
    assert _slug("The `tidy` scope, by kind") == "the-tidy-scope-by-kind"
    assert _slug("12.0 First: reload the seven launchd jobs") == (
        "120-first-reload-the-seven-launchd-jobs")


def test_a_repeated_heading_takes_a_numbered_suffix():
    assert _anchors("## Gate\n\n## Gate\n") == {"gate", "gate-1"}


def test_every_in_page_link_resolves_to_a_heading():
    text = GUIDE.read_text()
    links = re.findall(r"\]\(#([^)]+)\)", text)
    assert links
    anchors = _anchors(text)
    assert [link for link in links if link not in anchors] == []
