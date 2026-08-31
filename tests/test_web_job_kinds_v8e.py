"""The tenth kind: ``sensitivity``.

A zero-argument wrapper round ``gaffer.sensitivity.run_sensitivity``, in the
shape ``run_track_pens`` established — the module owns the work and the
printing, the wrapper owns the one-line job record.
"""

from __future__ import annotations

import pytest

from gaffer.errors import GafferError
from gaffer.web import job_kinds


def test_the_sensitivity_kind_is_registered():
    assert "sensitivity" in job_kinds.JOB_KINDS
    assert job_kinds.JOB_KINDS["sensitivity"] is job_kinds.run_sensitivity_job


def test_every_kind_is_a_zero_argument_callable():
    import inspect

    for kind, fn in job_kinds.JOB_KINDS.items():
        params = inspect.signature(fn).parameters
        assert all(p.default is not inspect.Parameter.empty
                   for p in params.values()), kind


def test_the_wrapper_returns_the_record_the_runner_shows(monkeypatch,
                                                         capsys):
    monkeypatch.setattr("gaffer.sensitivity.run_sensitivity",
                        lambda: {"gw": 5, "k": 20, "completed": 20,
                                 "wall_s": 141.2, "margin": 0.4,
                                 "verdict": "Salah appears in 17/20"})
    assert job_kinds.run_sensitivity_job() == {"gw": 5, "k": 20,
                                              "completed": 20}
    printed = capsys.readouterr().out
    assert "17/20" in printed
    assert "141.2" in printed


def test_no_saved_state_fails_the_job_rather_than_the_server(monkeypatch):
    """The runner turns a raised GafferError into a failed job record with
    the message on it, which is what "run advise first" has to look like."""
    def boom():
        raise GafferError("no saved solve state — run `gaffer advise` first")

    monkeypatch.setattr("gaffer.sensitivity.run_sensitivity", boom)
    with pytest.raises(GafferError):
        job_kinds.run_sensitivity_job()
