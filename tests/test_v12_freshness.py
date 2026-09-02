"""When each of the five things last happened, in one place.

Every hub in this app can be read as if it were current. A page of ownership
figures from a scrape that has not run since Saturday looks exactly like a page
of ownership figures from an hour ago, and the only cure is a line at the top of
every page saying which it is.

All five rows are file mtimes, and that is a decision rather than a shortcut: each
of these artifacts is rewritten whole by the job that produces it, so the mtime is
the run stamp. A timestamp parsed out of a file's *contents* can be stale inside a
file that was just rewritten, which is a subtler lie than a stale mtime.

`age_hours` is computed here and not on the client, so the colouring rule is one
implementation rather than two — and `None` means "never", which the strip draws
in grey. Never 0.0: a zero age is "just now", which is the exact opposite.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _get(path="/api/meta/freshness"):
    return TestClient(create_app()).get(path).json()


def test_a_cold_clone_is_five_rows_of_never(clone):
    """The honest empty state, and the main case on a fresh install. Five
    rows, not zero: a strip that renders nothing teaches the reader that its
    absence means everything is fine."""
    body = _get()
    assert [r["source"] for r in body["rows"]] == [
        "refresh", "odds", "field", "advise", "backup"]
    assert all(r["modified_at"] is None for r in body["rows"])
    assert all(r["age_hours"] is None for r in body["rows"])


def test_an_age_is_never_zero_for_a_missing_file(clone):
    """0.0 hours is "just now", which is the strongest possible claim and the
    opposite of the truth."""
    assert all(r["age_hours"] != 0.0 for r in _get()["rows"])


def test_a_refreshed_clone_reports_the_live_frame(clone):
    store.save(pd.DataFrame({"code": [1]}), "live/player_gw.parquet")
    row = next(r for r in _get()["rows"] if r["source"] == "refresh")
    assert row["modified_at"] is not None
    assert row["age_hours"] is not None and row["age_hours"] < 1


def test_the_odds_row_reads_the_newest_gameweek_file(clone):
    store.save(pd.DataFrame({"gw": [2]}), "live/odds/gw2.parquet")
    store.save(pd.DataFrame({"gw": [3]}), "live/odds/gw3.parquet")
    row = next(r for r in _get()["rows"] if r["source"] == "odds")
    assert row["path"].endswith("gw3.parquet")


def test_the_advise_row_reads_the_newest_advice_artifact(clone):
    (clone / "reports").mkdir()
    (clone / "reports" / "gw2-advice.json").write_text("{}")
    (clone / "reports" / "gw3-advice.json").write_text("{}")
    row = next(r for r in _get()["rows"] if r["source"] == "advise")
    assert row["path"].endswith("gw3-advice.json")


def test_the_backup_row_reads_the_configured_directory(clone, monkeypatch):
    (clone / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        f'[backup]\ndir = "{clone / "bk"}"\n')
    (clone / "bk").mkdir()
    (clone / "bk" / "gaffer-20260901-2345.tar.gz").write_text("x")
    row = next(r for r in _get()["rows"] if r["source"] == "backup")
    assert row["modified_at"] is not None


def test_a_broken_config_leaves_the_backup_row_at_never(clone):
    """The endpoint is on every page load. It degrades one row rather than
    500ing the strip, which would take the freshness line off every hub the
    moment a config key was mistyped."""
    (clone / "config.toml").write_text("[backup\n")
    row = next(r for r in _get()["rows"] if r["source"] == "backup")
    assert row["age_hours"] is None


def test_the_endpoint_never_errors(clone):
    """Same contract as /api/review. This is drawn on every page in the app,
    so a 500 here is a 500 everywhere."""
    assert TestClient(create_app()).get(
        "/api/meta/freshness").status_code == 200


def test_this_cycle_added_exactly_this_route(clone):
    paths = set(create_app().openapi()["paths"])
    assert "/api/meta/freshness" in paths


def test_a_file_that_vanishes_between_the_glob_and_the_stat_greys_one_row(
        clone, monkeypatch):
    """The window is real: `_newest` lists a directory and then stats what it
    found, and the job that owns that directory rewrites its output on a
    timer. A file deleted in between used to be an unhandled `OSError` — that
    is, a 500 on the one endpoint every page in the app calls."""
    from pathlib import Path

    (clone / "reports").mkdir()
    (clone / "reports" / "gw3-advice.json").write_text("{}")
    (store.DATA_DIR / "live").mkdir(parents=True)
    (store.DATA_DIR / "live" / "player_gw.parquet").write_text("x")

    real_stat = Path.stat

    def stat(self, *args, **kwargs):
        # By name: `resolve()` here would re-enter `Path.stat` and recurse.
        if self.name == "gw3-advice.json":
            raise FileNotFoundError(2, "No such file or directory")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    payload = TestClient(create_app()).get("/api/meta/freshness")
    assert payload.status_code == 200
    rows = {r["source"]: r for r in payload.json()["rows"]}
    assert rows["advise"]["age_hours"] is None       # grey, not a crash
    assert rows["advise"]["path"] is None
    assert rows["refresh"]["age_hours"] is not None  # the others are intact


def test_health_survives_the_same_vanished_file(clone, monkeypatch):
    """`/api/health` reads the same `_stat`, so the guard belongs in the
    helper rather than in the strip's row builder. Same window, same file,
    same answer: one absent source rather than a 500 on the page a user opens
    precisely because something is wrong."""
    from pathlib import Path

    # A real parquet, not the placeholder byte the strip's rows are happy
    # with: `/api/health` also reads this file for `data_through_gw`.
    (store.DATA_DIR / "live").mkdir(parents=True)
    pd.DataFrame({"code": [1], "gw": [3], "total_points": [5]}).to_parquet(
        store.DATA_DIR / "live" / "player_gw.parquet")

    real_stat = Path.stat

    def stat(self, *args, **kwargs):
        # By name, as above: `resolve()` would re-enter `Path.stat`. And only
        # for the bare call, because `Path.exists()` is itself a stat — it
        # passes `follow_symlinks=` — and a file that fails *both* is simply
        # absent, which `exists()` reports without ever reaching the guard.
        # The window this test is about is the one where the existence check
        # succeeds and the stat behind it does not.
        if self.name == "player_gw.parquet" and not kwargs:
            raise FileNotFoundError(2, "No such file or directory")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    sources = {s["source"]: s for s in response.json()["data"]}
    assert sources["player_gw"]["present"] is False
    assert sources["player_gw"]["modified_at"] is None
    assert sources["player_gw"]["age_hours"] is None
