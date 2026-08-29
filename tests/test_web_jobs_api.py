"""POST/GET /api/jobs — the v7 runner's HTTP surface."""

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
