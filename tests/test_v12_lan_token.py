"""Reads are open; writes need the token, and only when you asked for LAN.

`gaffer ui --lan` binds 0.0.0.0 and the banner has always said, out loud, that
there is no auth. That was an honest description of a loopback tool served to a
home network, and it stops being adequate the moment the network has a guest on
it: every write route here mutates state a person's season depends on — pinned
p_play overrides, watchlist stars, saved drafts, queued jobs.

The shape is a middleware and a keyword-only argument, not a per-route
dependency. There are ten-odd non-GET routes across nine routers and one of them
lives in a protected module, so a `Depends` on each would be a wide diff and an
unauthorized one. `create_app()` with no token enforces nothing, which is every
existing caller and every existing test.

403 rather than 401: a 401 invites the browser's own credential prompt for a
scheme this app does not implement, and the user would have nowhere to type.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_without_a_token_nothing_changes(clone):
    """Loopback, which is the default and the overwhelmingly common case."""
    client = TestClient(create_app())
    assert client.get("/api/ping").status_code == 200
    # A write with no header: it may 404 or 422 on a cold clone, but it must
    # not be refused for a token that was never required.
    assert client.post("/api/watchlist", json={}).status_code != 403


def test_a_get_is_open_even_with_a_token(clone):
    client = TestClient(create_app(token="s3cret"))
    assert client.get("/api/ping").status_code == 200


def test_a_write_without_the_header_is_refused(clone):
    client = TestClient(create_app(token="s3cret"))
    response = client.post("/api/watchlist", json={})
    assert response.status_code == 403
    assert "X-Gaffer-Token" in response.json()["detail"]


def test_a_write_with_the_wrong_token_is_refused(clone):
    client = TestClient(create_app(token="s3cret"))
    assert client.post("/api/watchlist", json={},
                       headers={"X-Gaffer-Token": "nope"}).status_code == 403


def test_a_write_with_the_right_token_reaches_the_route(clone):
    """"Reaches" rather than "succeeds": on a cold clone the route itself may
    still refuse. What matters is that the refusal is the route's and not the
    middleware's."""
    client = TestClient(create_app(token="s3cret"))
    assert client.post("/api/watchlist", json={},
                       headers={"X-Gaffer-Token": "s3cret"}
                       ).status_code != 403


def test_every_write_method_is_covered(clone):
    """POST, PUT, PATCH and DELETE. A DELETE that slipped through would be the
    worst one to miss — /api/jobs/current cancels a running job."""
    client = TestClient(create_app(token="s3cret"))
    for call in (client.post, client.put, client.patch, client.delete):
        assert call("/api/watchlist").status_code == 403


def test_options_and_head_pass_with_get(clone):
    """A preflight that fails closed makes every write look like a network
    error rather than a refusal, and the page would say nothing useful."""
    client = TestClient(create_app(token="s3cret"))
    assert client.options("/api/ping").status_code != 403
    assert client.head("/api/ping").status_code != 403


def test_the_comparison_is_constant_time():
    """Not because a home network is a threat model, but because
    `secrets.compare_digest` costs one import and the alternative is a habit
    that travels to code where it matters."""
    import inspect

    from gaffer.web import app as app_mod

    assert "compare_digest" in inspect.getsource(app_mod)


def test_a_generated_token_is_not_predictable():
    from gaffer.web.app import generate_token

    assert len({generate_token() for _ in range(20)}) == 20
    assert len(generate_token()) >= 16


def test_the_config_key_is_read(tmp_path):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    '[web]\ntoken = "from-config"\n')
    assert load_config(path).web_token == "from-config"


def test_the_token_is_absent_by_default(tmp_path):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).web_token == ""
