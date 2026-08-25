"""One normalizer for player names, shared by every source that has to match
on them.

Understat writes "Ødegaard", the odds feed writes "Martin Odegaard", the FPL
bootstrap writes "M.Ødegaard" depending on the season. Every one of those has
to collapse to the same key, and the collapse has to be identical in the
Understat id mapping and the AGS name match — two normalizers that disagree
by a hyphen would match different sets of players and nobody would notice.
"""

from __future__ import annotations

import re
import unicodedata

# Apostrophes elide rather than separate: "N'Golo" is one word, and the FPL
# bootstrap writes it "Ngolo". Everything else non-alphanumeric becomes a
# space, so "Heung-Min" and "Heung Min" agree.
_ELIDED = re.compile(r"['‘’ʼ`´]+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_name(name) -> str:
    """Casefolded, accent-stripped, punctuation-free, single-spaced.

    Punctuation becomes a space rather than nothing, so "Heung-Min" and
    "Heung Min" agree; a missing or non-string name is the empty string,
    which matches nothing rather than raising in the middle of a join.
    """
    if name is None or not isinstance(name, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed
                       if not unicodedata.combining(c))
    lowered = stripped.casefold()
    # Ø and ß survive NFKD as themselves; map the few that matter by hand.
    lowered = lowered.replace("ø", "o").replace("ß", "ss").replace("đ", "d")
    lowered = _ELIDED.sub("", lowered)
    return _SPACES.sub(" ", _PUNCT.sub(" ", lowered)).strip()
