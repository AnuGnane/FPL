"""The August failure, caught in August rather than in October.

FPL's bootstrap carries no season string. What it carries is 38 events with
deadlines, and GW1's is in August of the season's first year — so the season is
derivable and the config's claim about it is checkable.

The check matters because every downstream failure of a rollover is silent.
`current_season` is written into every row `refresh_live` banks and every model
`train` fits; a stale value does not raise, it labels this season's data as last
season's and trains on the mixture. The first symptom is a model that has
quietly got worse.

Two rules that are not obvious and are the reason this is a whole task:

* the **minimum** deadline year across the events, not GW1's row. A partially
  published season can be missing rows, and `min` degrades to the earliest week
  there is;
* an events table with no parseable deadline yields `None`, and `None` is *not*
  a mismatch. "Cannot tell" and "wrong" are different states, and a red banner
  drawn from the first is a false alarm on every cold clone.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data.bootstrap import season_from_events


def _events(*deadlines):
    return pd.DataFrame([{"gw": i + 1, "deadline_time": d}
                         for i, d in enumerate(deadlines)])


def test_an_august_first_deadline_names_the_season():
    assert season_from_events(
        _events("2026-08-14T17:30:00Z", "2026-08-21T17:30:00Z")) == "2026-27"


def test_the_year_pair_wraps_at_the_century():
    assert season_from_events(_events("2099-08-14T17:30:00Z")) == "2099-00"


def test_the_earliest_deadline_decides_not_the_first_row():
    """Rows out of order, and a season that is only half published: `min`
    answers both without knowing about either."""
    assert season_from_events(
        _events("2027-05-24T15:00:00Z", "2026-08-14T17:30:00Z")) == "2026-27"


def test_an_unparseable_deadline_is_skipped_rather_than_fatal():
    assert season_from_events(
        _events("not a date", "2026-08-14T17:30:00Z")) == "2026-27"


def test_no_parseable_deadline_at_all_is_None_and_not_a_guess():
    assert season_from_events(_events("not a date")) is None
    assert season_from_events(_events()) is None


def test_a_frame_without_the_column_is_None():
    assert season_from_events(pd.DataFrame({"gw": [1]})) is None


# --- the CLI half ---------------------------------------------------------

def test_refresh_refuses_when_the_api_disagrees_with_the_config(
        tmp_path, monkeypatch, capsys):
    """Non-zero exit, and a message naming both values and both keys — the
    two things a user needs in order to fix it without reading the source."""
    import typer

    from gaffer import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2025-26"\n')

    class Client:
        def get_bootstrap(self):
            return {"events": [{"id": 1,
                                "deadline_time": "2026-08-14T17:30:00Z"}]}

    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())
    with pytest.raises(typer.Exit) as exc:
        cli.refresh()
    assert exc.value.exit_code == 1
    out = capsys.readouterr().out
    assert "2025-26" in out and "2026-27" in out
    assert "current_season" in out and "train_seasons" in out


def test_refresh_proceeds_when_they_agree(tmp_path, monkeypatch):
    """The guard is a guard, not a gate: the happy path is unchanged, and
    `refresh_live` is still called exactly once."""
    from gaffer import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')

    class Client:
        def get_bootstrap(self):
            return {"events": [{"id": 1,
                                "deadline_time": "2026-08-14T17:30:00Z"}]}

    calls = []
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())
    monkeypatch.setattr(
        "gaffer.data.live.refresh_live",
        lambda *a, **k: calls.append(1) or pd.DataFrame({"code": [1]}))
    cli.refresh()
    assert calls == [1]


def test_refresh_fetches_the_bootstrap_once_and_hands_it_on(tmp_path,
                                                            monkeypatch):
    """The guard reads the events out of a bootstrap `refresh_live` was about
    to fetch again. Two fetches of a 1.7 MB payload seconds apart is also two
    `data/raw/bootstrap-*.json` snapshots of the same thing, so the payload is
    passed through and `refresh_live` uses it instead of calling out."""
    from gaffer import cli
    from gaffer.data import live

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = []\ncurrent_season = "2026-27"\n')

    payload = {"events": [{"id": 1, "deadline_time": "2026-08-14T17:30:00Z"}]}
    fetches = []

    class Client:
        def get_bootstrap(self):
            fetches.append(1)
            return payload

    seen = {}
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())

    def fake_refresh_live(client, season, season_idx, sleep_s=0.05,
                          bootstrap=None):
        seen["bootstrap"] = bootstrap
        # what the real body does with it, so the assertion below is about the
        # argument actually being used rather than merely accepted
        raw = client.get_bootstrap() if bootstrap is None else bootstrap
        assert raw is payload
        return pd.DataFrame({"code": [1]})

    monkeypatch.setattr("gaffer.data.live.refresh_live", fake_refresh_live)
    cli.refresh()
    assert seen["bootstrap"] is payload
    assert fetches == [1]

    # and the real signature takes it — a fake alone would not prove that
    import inspect
    assert "bootstrap" in inspect.signature(live.refresh_live).parameters


def test_refresh_proceeds_when_the_season_cannot_be_derived(tmp_path,
                                                            monkeypatch):
    """"Cannot tell" never blocks a refresh. A bootstrap FPL has not opened
    for the new season yet is a normal July state, and refusing to ingest in
    July would be the guard causing the outage it exists to prevent."""
    from gaffer import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = []\ncurrent_season = "2026-27"\n')

    class Client:
        def get_bootstrap(self):
            return {"events": []}

    calls = []
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())
    monkeypatch.setattr(
        "gaffer.data.live.refresh_live",
        lambda *a, **k: calls.append(1) or pd.DataFrame({"code": [1]}))
    cli.refresh()
    assert calls == [1]


# --- the served half ------------------------------------------------------

def test_health_reports_both_values_from_the_banked_events(tmp_path,
                                                           monkeypatch):
    """Disk only. `/api/health` is polled by a tab, and a page that goes blank
    when the FPL API is down is the opposite of a health page."""
    from fastapi.testclient import TestClient

    from gaffer.data import store
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = []\ncurrent_season = "2025-26"\n')
    store.save(pd.DataFrame([{"gw": 1,
                              "deadline_time": "2026-08-14T17:30:00Z"}]),
               "live/events.parquet")
    body = TestClient(create_app()).get("/api/health").json()
    assert body["season_ok"] is False
    assert body["season_config"] == "2025-26"
    assert body["season_ingested"] == "2026-27"


def test_health_on_a_clone_with_no_events_says_nothing_rather_than_alarm(
        tmp_path, monkeypatch):
    """No data is not a mismatch. `season_ok` is None — three states, not two,
    and the banner draws on False alone."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/health").json()
    assert body["season_ok"] is None
    assert body["season_ingested"] is None
