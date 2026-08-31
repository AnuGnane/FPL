"""The eleventh and twelfth kinds: ``digest-friday`` and ``digest-tuesday``.

``run_sensitivity_job``'s shape, twice: the module owns the work and the
printing, the wrapper owns the one-line job record. The one thing these two
add over that pattern is the config read — ``run_digest`` takes ``notify`` as
an argument and has no opinion about whether it should fire, and this is the
seam where the opinion comes from (plan A7).
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from gaffer.config import Config
from gaffer.web import job_kinds


def test_both_digest_kinds_are_registered():
    assert job_kinds.JOB_KINDS["digest-friday"] is job_kinds.run_digest_friday
    assert job_kinds.JOB_KINDS["digest-tuesday"] \
        is job_kinds.run_digest_tuesday


def test_the_registry_is_exactly_twelve_kinds():
    assert sorted(job_kinds.JOB_KINDS) == [
        "advise", "advise-fast", "digest-friday", "digest-tuesday",
        "evaluate", "field-scrape", "news-shadow", "refresh-data", "review",
        "sensitivity", "snapshot", "track-pens"]


def test_every_kind_is_still_a_zero_argument_callable():
    """The runner calls these with no arguments; a wrapper that grew a
    parameter would be a 500 at press-the-button time."""
    for kind, fn in job_kinds.JOB_KINDS.items():
        params = inspect.signature(fn).parameters
        assert all(p.default is not inspect.Parameter.empty
                   for p in params.values()), kind


def test_the_wrapper_returns_the_record_the_runner_shows(monkeypatch,
                                                         capsys):
    """The module prints and the wrapper counts.

    The stand-in prints the way :func:`gaffer.digest.run_digest` does — one
    ``format_digest`` line — because that division is the thing under test:
    the wrapper adds no second copy of the headline to the job log, it turns
    the payload into the three fields the job record carries.
    """
    from gaffer.digest import format_digest

    payload = {"kind": "friday", "gw": 5,
               "headline": "GW5: captain Haaland.",
               "sections": [{"key": "move", "title": "t", "bits": ["b"]}]}

    def stand_in(kind, notify=True):
        print(format_digest(payload))
        return payload

    monkeypatch.setattr("gaffer.digest.run_digest", stand_in)
    assert job_kinds.run_digest_friday() == {"kind": "friday", "gw": 5,
                                             "sections": 1}
    assert "captain Haaland" in capsys.readouterr().out


def test_a_degraded_digest_is_still_a_finished_job(monkeypatch):
    """``run_digest`` answers ``None`` on a bad Friday — no advice, no
    network, an unwritable disk. The job reports zero sections rather than
    failing the run, which is ``run_field_scrape_job``'s trade exactly."""
    monkeypatch.setattr("gaffer.digest.run_digest",
                        lambda kind, notify=True: None)
    assert job_kinds.run_digest_tuesday() == {"kind": "tuesday", "gw": None,
                                              "sections": 0}


def test_the_notify_switch_reaches_the_module(monkeypatch):
    seen = {}

    def spy(kind, notify=True):
        seen["kind"], seen["notify"] = kind, notify
        return None

    monkeypatch.setattr("gaffer.digest.run_digest", spy)
    monkeypatch.setattr("gaffer.web.job_kinds._notify_enabled", lambda: False)
    job_kinds.run_digest_friday()
    assert seen == {"kind": "friday", "notify": False}


def test_the_switch_defaults_on_with_no_config_at_all(monkeypatch, tmp_path):
    """A clone with no config.toml still gets its notification: the key is a
    way to turn a working thing off, not a thing to find before it works."""
    from gaffer.config import serving_config

    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    try:
        assert job_kinds._notify_enabled() is True
    finally:
        serving_config.cache_clear()


def test_the_config_carries_exactly_one_new_key():
    names = {f.name for f in dataclasses.fields(Config)}
    assert "digest_notify" in names
    assert not [n for n in names if "digest" in n and n != "digest_notify"]


def test_the_key_reads_from_its_own_toml_section(tmp_path, monkeypatch):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[digest]\nnotify = false\n")
    assert load_config(path).digest_notify is False


def test_an_absent_digest_section_leaves_the_default(tmp_path):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).digest_notify is True
