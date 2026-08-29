"""POST/GET /api/jobs — the v7 runner's HTTP surface."""

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app
from gaffer.web.jobs import JobRunner
from gaffer.web.routers import jobs as jobs_router
from gaffer.web.schemas import JobRunView, JobStarted


def test_job_started_carries_the_id_and_the_kind():
    started = JobStarted(job_id="abc", kind="advise")
    assert started.model_dump() == {"job_id": "abc", "kind": "advise"}


def test_job_run_view_defaults_the_optional_tail_fields():
    view = JobRunView(id="abc", kind="advise", status="running",
                      started_at="2026-08-29T09:00:00+00:00", line_count=3)
    assert view.error is None
    assert view.summary is None
    assert view.finished_at is None


@pytest.fixture()
def app_and_runner(tmp_path, monkeypatch):
    """A real app whose runner executes test bodies instead of the pipeline."""
    monkeypatch.chdir(tmp_path)
    release = threading.Event()

    def slow():
        print("working")
        release.wait(5.0)
        print("finished")
        return {"gw": 5}

    def boom():
        print("about to fall over")
        raise RuntimeError("no models on disk")

    app = create_app()
    app.state.job_runner = JobRunner({"advise": slow, "evaluate": boom,
                                      "refresh-data": lambda: None,
                                      "news-shadow": lambda: None})
    return app, release


def _wait_for(client, job_id, statuses=("done", "failed"), timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in statuses:
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached {statuses}")


def test_starting_a_job_returns_its_id_and_kind(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    resp = client.post("/api/jobs/advise")
    assert resp.status_code == 202
    assert resp.json()["kind"] == "advise"
    release.set()
    _wait_for(client, resp.json()["job_id"])


def test_an_unknown_kind_is_a_404_not_a_500(app_and_runner):
    app, _ = app_and_runner
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/jobs/rm-rf")
    assert resp.status_code == 404
    assert "rm-rf" in resp.json()["detail"]


def test_a_second_job_while_one_runs_is_a_409_naming_the_holder(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    first = client.post("/api/jobs/advise").json()["job_id"]
    resp = client.post("/api/jobs/evaluate")
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"running_kind": "advise", "job_id": first}
    release.set()
    _wait_for(client, first)


def test_current_is_204_when_idle_and_the_run_when_busy(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    assert client.get("/api/jobs/current").status_code == 204
    job_id = client.post("/api/jobs/advise").json()["job_id"]
    body = client.get("/api/jobs/current").json()
    assert body["id"] == job_id and body["kind"] == "advise"
    release.set()
    _wait_for(client, job_id)
    assert client.get("/api/jobs/current").status_code == 204


def test_a_finished_job_reports_done_with_its_summary(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    job_id = client.post("/api/jobs/advise").json()["job_id"]
    release.set()
    body = _wait_for(client, job_id)
    assert body["status"] == "done"
    assert body["summary"] == "{'gw': 5}"
    assert body["line_count"] == 2


def test_a_failed_job_reports_failed_with_the_message(app_and_runner):
    app, _ = app_and_runner
    client = TestClient(app)
    job_id = client.post("/api/jobs/evaluate").json()["job_id"]
    body = _wait_for(client, job_id)
    assert body["status"] == "failed"
    assert body["error"] == "no models on disk"


def test_an_unknown_job_id_is_a_404(app_and_runner):
    app, _ = app_and_runner
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/nope")
    assert resp.status_code == 404


def test_the_v6_queue_is_still_reachable_through_the_same_path(tmp_path,
                                                               monkeypatch):
    """The what-if lab polls /api/jobs/{id} for a JobRegistry job."""
    monkeypatch.chdir(tmp_path)
    app = create_app()
    client = TestClient(app)
    job_id = app.state.jobs.submit(lambda: {"ok": True}, timeout_s=5.0)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            break
        time.sleep(0.01)
    assert body["status"] == "done"
    assert body["result"] == {"ok": True}


def _events(text: str) -> list[tuple[str, str]]:
    """SSE text -> [(event name, data)] in wire order."""
    out = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        out.append((name, data))
    return out


def test_the_stream_replays_every_line_in_order_then_ends(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    job_id = client.post("/api/jobs/advise").json()["job_id"]
    release.set()
    _wait_for(client, job_id)
    events = _events(client.get(f"/api/jobs/{job_id}/stream").text)
    assert [name for name, _ in events] == ["line", "line", "end"]
    assert [data for _, data in events[:2]] == ["working", "finished"]
    assert '"status": "done"' in events[-1][1]


def test_a_reconnect_replays_only_what_the_client_missed(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    job_id = client.post("/api/jobs/advise").json()["job_id"]
    release.set()
    _wait_for(client, job_id)
    events = _events(client.get(f"/api/jobs/{job_id}/stream?from=1").text)
    assert [data for name, data in events if name == "line"] == ["finished"]


def test_the_last_event_id_header_is_honoured_like_from(app_and_runner):
    app, release = app_and_runner
    client = TestClient(app)
    job_id = client.post("/api/jobs/advise").json()["job_id"]
    release.set()
    _wait_for(client, job_id)
    events = _events(client.get(f"/api/jobs/{job_id}/stream",
                                headers={"Last-Event-ID": "0"}).text)
    assert [data for name, data in events if name == "line"] == ["finished"]


def test_a_failed_jobs_stream_ends_with_the_error(app_and_runner):
    app, _ = app_and_runner
    client = TestClient(app)
    job_id = client.post("/api/jobs/evaluate").json()["job_id"]
    _wait_for(client, job_id)
    events = _events(client.get(f"/api/jobs/{job_id}/stream").text)
    assert events[-1][0] == "end"
    assert '"status": "failed"' in events[-1][1]
    assert "no models on disk" in events[-1][1]


def test_streaming_an_unknown_job_is_a_404(app_and_runner):
    app, _ = app_and_runner
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/jobs/nope/stream").status_code == 404


def _frames(app, job_id, from_=0):
    """The endpoint's own response iterator, one frame at a time.

    TestClient buffers a streaming response until the generator ends, which is
    the exact wait a heartbeat exists to avoid.
    """
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "headers": [],
             "query_string": b"", "path": f"/api/jobs/{job_id}/stream",
             "app": app}
    return jobs_router.stream(job_id, Request(scope), from_=from_).body_iterator


def test_a_quiet_stream_still_writes_a_heartbeat(app_and_runner, monkeypatch):
    """A silent job used to mean no write for up to the idle hour, so a client
    that had gone away was noticed an hour late and its worker sat pinned."""
    app, release = app_and_runner
    monkeypatch.setattr(jobs_router, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(jobs_router, "POLL_S", 0.01)
    client = TestClient(app)
    job_id = client.post("/api/jobs/advise").json()["job_id"]

    async def pull():
        frames = _frames(app, job_id)
        line = await frames.__anext__()     # the one line the job printed
        beat = await frames.__anext__()     # then quiet, so: a heartbeat
        await frames.aclose()
        return line, beat

    line, beat = asyncio.run(pull())
    release.set()
    _wait_for(client, job_id)

    assert "event: line" in line
    # An SSE comment: a real write on the socket, and ignored by EventSource.
    assert beat.startswith(":")
    assert beat.endswith("\n\n")
    assert "event:" not in beat and "data:" not in beat


def test_a_heartbeat_does_not_disturb_the_line_numbering(app_and_runner,
                                                         monkeypatch):
    app, release = app_and_runner
    monkeypatch.setattr(jobs_router, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(jobs_router, "POLL_S", 0.01)
    client = TestClient(app)
    job_id = client.post("/api/jobs/advise").json()["job_id"]

    async def pull():
        frames = _frames(app, job_id)
        await frames.__anext__()
        await frames.__anext__()            # a heartbeat in the middle
        release.set()
        return [chunk async for chunk in frames]

    rest = "".join(asyncio.run(pull()))
    _wait_for(client, job_id)

    assert "id: 1\nevent: line\ndata: finished" in rest
    assert "event: end" in rest
