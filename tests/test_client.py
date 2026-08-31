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


def _counting_transport(payloads):
    """Answers each call with the next payload, repeating the last one."""
    calls = {"n": 0}

    def handler(request):
        index = min(calls["n"], len(payloads) - 1)
        calls["n"] += 1
        return httpx.Response(200, json=payloads[index])

    return httpx.MockTransport(handler), calls


def test_an_unchanged_payload_does_not_leave_a_second_dump(tmp_path):
    """The commonest case by far: a fixtures list polled through a quiet
    afternoon is byte for byte what the last poll wrote."""
    transport, _ = _counting_transport([{"a": 1}])
    client = FPLClient(raw_dir=tmp_path, transport=transport)
    client.get_fixtures()
    client.get_fixtures()
    client.get_fixtures()
    assert len(list(tmp_path.glob("fixtures-*.json"))) == 1


def test_a_changed_payload_is_dumped_beside_the_old_one(tmp_path):
    transport, _ = _counting_transport([{"a": 1}, {"a": 2}])
    client = FPLClient(raw_dir=tmp_path, transport=transport)
    client.get_fixtures()
    # Same second, different bytes: the stamp collides, so the point is only
    # that a changed payload is never silently dropped.
    client.get_fixtures()
    dumps = sorted(tmp_path.glob("fixtures-*.json"))
    assert json.loads(dumps[-1].read_text()) == {"a": 2}


def test_pruning_keeps_the_newest_dumps_per_kind(tmp_path):
    for i in range(30):
        (tmp_path / f"fixtures-2026081{i:02d}T000000.json").write_text("{}")
    # A different kind in the same directory, which pruning must not touch.
    for i in range(5):
        (tmp_path / f"bootstrap-2026081{i:02d}T000000.json").write_text("{}")

    transport, _ = _counting_transport([{"new": True}])
    client = FPLClient(raw_dir=tmp_path, transport=transport)
    client.get_fixtures()

    kept = sorted(p.name for p in tmp_path.glob("fixtures-*.json"))
    assert len(kept) == client_mod.KEEP_DUMPS
    # Newest kept, oldest gone.
    assert kept[0] > "fixtures-20260810T000000.json"
    assert len(list(tmp_path.glob("bootstrap-*.json"))) == 5


def test_an_entry_dump_prunes_only_its_own_entry(tmp_path):
    for i in range(25):
        (tmp_path / f"entry-7-2026081{i:02d}T000000.json").write_text("{}")
    for i in range(3):
        (tmp_path / f"entry-77-2026081{i:02d}T000000.json").write_text("{}")
    transport, _ = _counting_transport([{"id": 7}])
    FPLClient(raw_dir=tmp_path, transport=transport).get_entry(7)
    assert len(list(tmp_path.glob("entry-7-*.json"))) == client_mod.KEEP_DUMPS
    assert len(list(tmp_path.glob("entry-77-*.json"))) == 3


def test_a_failed_dump_never_fails_the_fetch(tmp_path, monkeypatch, capsys):
    """A full disk is not a failed fetch: the caller already has its data."""
    transport, _ = _counting_transport([{"a": 1}])
    client = FPLClient(raw_dir=tmp_path, transport=transport)

    def boom(self, *args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(client_mod.Path, "write_text", boom)
    assert client.get_fixtures() == {"a": 1}
    assert "No space left on device" in capsys.readouterr().out
