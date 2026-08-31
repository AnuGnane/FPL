"""``GET /api/digest`` — the newest of the two banked digests.

Newest-wins rather than day-of-week-wins (plan A11): the artifact's own
``generated_at`` is a fact, the browser's clock is not, and a user who presses
**Tuesday debrief** on a Saturday should see the thing they just made.

Nothing here builds a digest. Building one reads seven files and can take a
second; a GET on a page load may not. The card renders what the schedule — or
a button — has already banked, and its empty state says so.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.digest import DIGEST_KINDS, load_digest
from gaffer.errors import GafferError
from gaffer.web.schemas import Digest, DigestPanel

router = APIRouter(prefix="/api", tags=["digest"])


@router.get("/digest", response_model=DigestPanel)
def digest(kind: str | None = None) -> DigestPanel:
    if kind is not None and kind not in DIGEST_KINDS:
        raise GafferError(
            f"unknown digest kind {kind!r} — expected one of "
            f"{', '.join(DIGEST_KINDS)}")
    kinds = (kind,) if kind is not None else DIGEST_KINDS
    found = [payload for payload in (load_digest(k) for k in kinds)
             if payload is not None]
    if not found:
        return DigestPanel(available=False)
    # An artifact with no timestamp sorts last rather than raising: a
    # hand-edited or older file is still worth showing when it is the only
    # one there is.
    newest = max(found, key=lambda p: str(p.get("generated_at") or ""))
    try:
        return DigestPanel(available=True, digest=Digest(**newest))
    except Exception as exc:  # noqa: BLE001 — a card is never worth a 500
        print(f"digest panel: artifact does not fit the schema ({exc})")
        return DigestPanel(available=False)
