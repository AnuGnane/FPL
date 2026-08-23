import json

import httpx

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
