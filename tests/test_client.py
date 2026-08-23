import json

import httpx

import gaffer.api.client as client_mod
from gaffer.api.client import FPLClient


def _transport(payload):
    def handler(request):
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_get_bootstrap_returns_json_and_snapshots(tmp_path):
    client = FPLClient(raw_dir=tmp_path, transport=_transport({"events": []}))
    data = client.get_bootstrap()
    assert data == {"events": []}
    snaps = list(tmp_path.glob("bootstrap-*.json"))
    assert len(snaps) == 1
    assert json.loads(snaps[0].read_text()) == {"events": []}


def test_retries_then_raises(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500)

    client = FPLClient(raw_dir=tmp_path, transport=httpx.MockTransport(handler),
                       retries=3, backoff=0.0)
    try:
        client.get_fixtures()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert calls["n"] == 3


def test_no_retry_on_404(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404)

    client = FPLClient(raw_dir=tmp_path, transport=httpx.MockTransport(handler),
                       retries=3, backoff=0.0)
    try:
        client.get_fixtures()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert calls["n"] == 1


def test_retries_on_429(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429)

    client = FPLClient(raw_dir=tmp_path, transport=httpx.MockTransport(handler),
                       retries=3, backoff=0.0)
    try:
        client.get_fixtures()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert calls["n"] == 3


def test_no_sleep_after_final_attempt(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(client_mod.time, "sleep", sleeps.append)

    def handler(request):
        return httpx.Response(500)

    client = FPLClient(raw_dir=tmp_path, transport=httpx.MockTransport(handler),
                       retries=3, backoff=0.001)
    try:
        client.get_fixtures()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert len(sleeps) == 2
