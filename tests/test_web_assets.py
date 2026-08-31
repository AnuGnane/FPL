"""``/api/assets``: the image cache that must never be an open proxy and must
never break a page.

Three states and their order are the whole contract (plan A9): a hit reads
disk and constructs no HTTP client at all, a miss fetches once and banks the
bytes, and every failure serves a bundled SVG and writes nothing. The last
clause is the one with teeth — a silhouette banked into the cache would be
served as a hit forever, and one bad evening would cost the pitch its shirts
for the season.

The allowlist tests are the security half. The endpoint fetches from a third
party on a caller's say-so, so "which codes may be asked for" is answered by
the banked bootstrap and by nothing else, and the path a code turns into is
built from a parsed integer rather than from anything the caller typed.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app
from gaffer.web.routers import assets

PLAYERS = pd.DataFrame({
    "code": [223094, 154561],
    "name": ["Haaland", "Raya"],
    "position": ["FWD", "GKP"],
    "team_id": [13, 1],
    "team_code": [43, 3],
    "now_cost": [150, 60],
})

TEAMS = pd.DataFrame({
    "team_id": [1, 13],
    "code": [3, 43],
    "name": ["Arsenal", "Man City"],
    "short_name": ["ARS", "MCI"],
})

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-photo-bytes"
WEBP = b"RIFF" + b"fake-shirt-bytes"


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """A clone with a banked bootstrap, an empty cache and a counted CDN."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return WEBP if "shirt" in url else PNG

    monkeypatch.setattr(assets, "_fetch", fetch)
    return tmp_path, TestClient(create_app()), calls


# --- the happy path -------------------------------------------------

def test_a_cold_shirt_is_fetched_once_and_banked(wired):
    tmp_path, client, calls = wired
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.content == WEBP
    assert response.headers["content-type"] == "image/webp"
    assert len(calls) == 1
    assert (tmp_path / "data/live/assets/shirt_43.webp").read_bytes() == WEBP


def test_a_cold_photo_is_fetched_once_and_banked(wired):
    tmp_path, client, calls = wired
    response = client.get("/api/assets/photo/223094")
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert (tmp_path / "data/live/assets/photo_223094.png").read_bytes() == PNG


def test_the_keeper_shirt_is_a_different_file_and_a_different_url(wired):
    """A9: two variants of one team's shirt, so a cached outfield shirt must
    not answer a request for the keeper's."""
    tmp_path, client, calls = wired
    client.get("/api/assets/shirt/43")
    client.get("/api/assets/shirt/43?keeper=true")
    assert (tmp_path / "data/live/assets/shirt_43_1.webp").exists()
    assert len(calls) == 2
    assert calls[1].endswith("shirt_43_1-66.webp")


def test_a_hit_never_constructs_an_http_client(wired, monkeypatch):
    """The rail that matters most on a page drawing fifteen shirts: the
    second load of This Week makes zero outbound requests."""
    _tmp, client, calls = wired
    client.get("/api/assets/shirt/43")

    def forbidden(url: str) -> bytes:
        raise AssertionError(f"a cache hit refetched {url}")

    monkeypatch.setattr(assets, "_fetch", forbidden)
    assert client.get("/api/assets/shirt/43").content == WEBP
    assert len(calls) == 1


def test_a_hit_is_served_with_a_long_immutable_cache_header(wired):
    _tmp, client, _calls = wired
    client.get("/api/assets/shirt/43")
    header = client.get("/api/assets/shirt/43").headers["cache-control"]
    assert "max-age=604800" in header and "immutable" in header


# --- the fallback ---------------------------------------------------

def test_a_dead_upstream_serves_the_bundled_shirt(wired, monkeypatch):
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in response.content


def test_a_dead_upstream_serves_the_bundled_silhouette(wired, monkeypatch):
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    response = client.get("/api/assets/photo/223094")
    assert response.status_code == 200
    assert b"<svg" in response.content


def test_a_fallback_carries_a_short_max_age_and_no_immutable(wired,
                                                             monkeypatch):
    """The failure is the transient one. A week-long silhouette would outlive
    the outage that caused it by six days and twenty-three hours."""
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    header = client.get("/api/assets/shirt/43").headers["cache-control"]
    assert "max-age=60" in header and "immutable" not in header


def test_a_fallback_is_never_banked(wired, monkeypatch):
    """A9's rail: a banked silhouette would be served as a hit forever."""
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    client.get("/api/assets/shirt/43")
    cache = tmp_path / "data/live/assets"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_an_empty_body_from_the_cdn_is_a_fallback_not_a_banked_zero_byte_file(
        wired, monkeypatch):
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: b"")
    assert b"<svg" in client.get("/api/assets/shirt/43").content
    assert not (tmp_path / "data/live/assets/shirt_43.webp").exists()


def test_an_unwritable_cache_still_serves_the_fetched_bytes(wired,
                                                            monkeypatch):
    """The bytes are in hand. A read-only disk costs the *cache*, not the
    shirt — the user gets his pitch and the next load refetches."""
    _tmp, client, _calls = wired
    monkeypatch.setattr(assets, "_bank", lambda path, data: (
        _ for _ in ()).throw(OSError("read-only file system")))
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.content == WEBP


def test_the_write_leaves_no_temp_file_behind(wired):
    tmp_path, client, _calls = wired
    client.get("/api/assets/shirt/43")
    assert list((tmp_path / "data/live/assets").glob("*.tmp")) == []


def test_a_body_that_is_not_an_image_is_a_fallback_and_is_never_banked(
        wired, monkeypatch):
    """The captive-portal case, and the reason banking is guarded by the
    bytes rather than by the status line.

    A hotel wifi splash page is a 200 with an HTML body. Banked, it would be
    served as ``image/webp`` behind a week-long ``immutable`` header, and the
    pitch would stay broken until somebody deleted the cache directory by
    hand — a failure that outlives its cause by six days.
    """
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch",
                        lambda url: b"<!DOCTYPE html><html>Sign in</html>")
    response = client.get("/api/assets/shirt/43")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert not (tmp_path / "data/live/assets/shirt_43.webp").exists()


def test_a_png_body_does_not_satisfy_a_request_for_a_shirt(wired,
                                                            monkeypatch):
    """The magic check is per declared type, not "is this any image"."""
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch", lambda url: PNG)
    assert b"<svg" in client.get("/api/assets/shirt/43").content
    assert not (tmp_path / "data/live/assets/shirt_43.webp").exists()


def test_a_body_over_the_size_cap_is_a_fallback_and_is_never_banked(
        wired, monkeypatch):
    """A 66px shirt is a couple of kilobytes. Two megabytes of anything is
    not the thing we asked for."""
    tmp_path, client, _calls = wired
    monkeypatch.setattr(assets, "_fetch",
                        lambda url: b"RIFF" + b"\0" * (assets.MAX_BYTES + 1))
    assert b"<svg" in client.get("/api/assets/shirt/43").content
    assert not (tmp_path / "data/live/assets/shirt_43.webp").exists()


def test_every_response_refuses_content_type_sniffing(wired, monkeypatch):
    """These bytes came from a third party; the type is ours to declare and
    not the browser's to guess at. Hit, fresh and fallback alike."""
    _tmp, client, _calls = wired
    fresh = client.get("/api/assets/shirt/43")
    hit = client.get("/api/assets/shirt/43")
    monkeypatch.setattr(assets, "_fetch", lambda url: (_ for _ in ()).throw(
        RuntimeError("connection refused")))
    fallback = client.get("/api/assets/photo/223094")
    for response in (fresh, hit, fallback):
        assert response.headers["x-content-type-options"] == "nosniff"


def test_the_fetch_does_not_follow_redirects_off_the_cdn(monkeypatch):
    """``_fetch`` asks for a direct path on a verified host. A 3xx means the
    answer is coming from somewhere else, which belongs in the fallback path
    rather than being chased off-host and banked for a week."""
    seen: dict = {}

    class Reply:
        content = b"RIFF"

        def raise_for_status(self):
            return None

    def spy(url, **kwargs):
        seen.update(kwargs)
        return Reply()

    monkeypatch.setattr(assets.httpx, "get", spy)
    assert assets._fetch("https://example.invalid/x.webp") == b"RIFF"
    assert seen["follow_redirects"] is False
    assert seen["timeout"] == assets.TIMEOUT


# --- the allowlist and the path -------------------------------------

def test_a_team_code_the_bootstrap_does_not_know_is_a_404(wired):
    _tmp, client, calls = wired
    assert client.get("/api/assets/shirt/999").status_code == 404
    assert calls == []


def test_a_player_code_the_bootstrap_does_not_know_is_a_404(wired):
    _tmp, client, calls = wired
    assert client.get("/api/assets/photo/999999").status_code == 404
    assert calls == []


def test_a_clone_with_no_snapshot_refuses_everything_rather_than_proxying(
        wired):
    """An empty allowlist is the right failure: the pitch falls back to
    silhouettes, which is the state a machine with no data should be in."""
    tmp_path, client, calls = wired
    (tmp_path / "data/live/players.parquet").unlink()
    (tmp_path / "data/live/teams.parquet").unlink()
    assert client.get("/api/assets/shirt/43").status_code == 404
    assert client.get("/api/assets/photo/223094").status_code == 404
    assert calls == []


@pytest.mark.parametrize("code", [
    "../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "43/../../secret",
    "43.webp", "-43", "0x2b", "43%00",
])
def test_a_non_integer_code_never_reaches_the_handler(wired, code):
    """A8: the route declares ``int``, so the converter refuses before any
    handler runs and no caller-supplied string can reach a path."""
    tmp_path, client, calls = wired
    assert client.get(f"/api/assets/shirt/{code}").status_code in (404, 422)
    assert calls == []
    assert not (tmp_path / "data/live/assets").exists()


def test_nothing_is_ever_written_outside_the_cache_directory(wired):
    tmp_path, client, _calls = wired
    client.get("/api/assets/shirt/43")
    client.get("/api/assets/photo/223094")
    written = {p.parent for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert written <= {tmp_path / "data/live",
                       tmp_path / "data/live/assets"}


# --- the urls the spec verified -------------------------------------

def test_the_fetched_urls_are_the_ones_the_spec_curled(wired):
    """D1 records these as verified against the live CDN on 2026-08-31. If
    they change, this test is where that is discovered."""
    _tmp, client, calls = wired
    client.get("/api/assets/shirt/43")
    client.get("/api/assets/photo/223094")
    assert calls[0] == ("https://fantasy.premierleague.com/dist/img/shirts/"
                        "standard/shirt_43-66.webp")
    assert calls[1] == ("https://resources.premierleague.com/premierleague/"
                        "photos/players/110x140/p223094.png")
