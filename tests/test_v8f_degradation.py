"""v8f degradation rails (gate G2).

Five stores this cycle touches and one schedule it adds to, each asked the
same question: what happens on the day it is not there? The answer has to be
the same every time — a printed line, a smaller payload, an absent card — and
never an exception out of a scheduled job or a 500 out of a page.

The last two rails are pins rather than degradations. The job-kind count and
the config-key count moved this cycle, deliberately and with authorization
(the plan's Task 5 STOP), and asserting the new numbers from this cycle's own
file is what makes the *next* cycle's accidental addition fail in its own
suite rather than in five older ones.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer import artifacts
from gaffer.data import store
from gaffer.web.app import create_app

GW = 5

PLAYERS = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_code": [3, 4],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
    "price_change_percent": [98.0, 1.0],
    "price_change_calibrating": [False, False],
})


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    return tmp_path, TestClient(create_app())


# --- rail 1: an unwritable price log ---------------------------------

def test_an_unwritable_price_log_costs_the_day_and_nothing_else(app,
                                                                capsys):
    """The nightly job at 23:15 has already printed the user's answer by the
    time the bank runs, so a full disk must be a line, not an exception."""
    from gaffer.price_log import bank_prices

    _, _client = app
    assert bank_prices(PLAYERS.drop(columns=["now_cost"])) is None
    assert "price log not written" in capsys.readouterr().out


def test_a_price_log_that_was_never_written_reads_as_empty(app):
    from gaffer.price_log import PRICE_LOG_COLS, load_price_log

    assert load_price_log().empty
    assert list(load_price_log().columns) == PRICE_LOG_COLS


# --- rail 2: the watchlist ------------------------------------------

@pytest.mark.parametrize("payload", ["{not json", "[]", '{"watchlist": 3}'])
def test_a_corrupt_watchlist_is_an_empty_one(app, payload):
    tmp_path, client = app
    (tmp_path / "reports/watchlist.json").write_text(payload)
    assert client.get("/api/watchlist").json() == {"rows": []}


def test_a_corrupt_watchlist_leaves_the_explorer_alone(app):
    """The star column is a bookmark. A broken store must not blank a table
    of six hundred players.

    Asserted as invariance rather than as a 200: the explorer answers a bare
    clone with its own structured 422 ("no candidate pool yet — run `gaffer
    advise` first") whether or not anything is starred, and pinning that
    number would pin somebody else's contract. What this rail owns is that
    corrupting the watchlist changes the explorer's answer *not at all* — and
    that it never turns into a 500.
    """
    tmp_path, client = app
    before = client.get("/api/players")
    (tmp_path / "reports/watchlist.json").write_text("{not json")
    after = client.get("/api/players")
    assert after.status_code == before.status_code
    assert after.status_code < 500
    assert after.json() == before.json()


def test_a_missing_reports_directory_still_serves_the_watchlist(app):
    tmp_path, client = app
    (tmp_path / "reports").rmdir()
    assert client.get("/api/watchlist").json() == {"rows": []}


# --- rail 3: the movers card ----------------------------------------

def test_no_player_snapshot_is_an_unavailable_movers_panel(app):
    tmp_path, client = app
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/prices/movers").json()
    assert body["available"] is False and body["rows"] == []


def test_nothing_watched_is_available_and_empty_not_unavailable(app):
    """"You are watching nobody" is a working card with an empty state; it is
    not a broken one."""
    _, client = app
    body = client.get("/api/prices/movers").json()
    assert body["available"] is True and body["rows"] == []


# --- rail 4: the digests --------------------------------------------

def test_a_friday_with_nothing_on_disk_still_writes_a_briefing(app):
    from gaffer.digest import load_digest, run_digest

    _, _client = app
    payload = run_digest("friday", notify=False)
    assert payload is not None
    assert load_digest("friday") is not None
    # A5: no advice, so no move section, and the headline says what to run.
    assert "move" not in {s["key"] for s in payload["sections"]}
    assert "gaffer advise" in payload["headline"]


def test_a_tuesday_with_no_ledger_says_the_season_is_unreviewed(app):
    from gaffer.digest import run_digest

    _, _client = app
    payload = run_digest("tuesday", notify=False)
    assert payload is not None and payload["gw"] is None
    assert "not been reviewed" in payload["headline"]


def test_a_section_builder_that_raises_still_leaves_a_digest_on_disk(
        app, monkeypatch, capsys):
    """A5's other half. "Never raise" was banked; "never silent" was not — a
    Friday that threw returned ``None`` and wrote nothing, so the card showed
    the never-run empty state and the only record of the crash was a line in
    ``logs/digest-friday.log`` that nobody opens. G1 found the crash by
    hand for exactly that reason. The artifact rail covers the crash path
    now: a raising builder banks a digest whose sections are empty and whose
    ``error`` names what went wrong."""
    from gaffer import digest as mod

    _, client = app
    monkeypatch.setattr(mod, "_flagged_bits",
                        lambda *a: (_ for _ in ()).throw(
                            ValueError("boolean value of NA is ambiguous")))
    assert mod.run_digest("friday", notify=False) is None
    assert "digest not built" in capsys.readouterr().out

    banked = mod.load_digest("friday")
    assert banked is not None and banked["sections"] == []
    assert banked["error"] == "ValueError: boolean value of NA is ambiguous"
    # And the card can say so rather than showing the never-run empty state.
    panel = client.get("/api/digest").json()
    assert panel["available"] is True
    assert panel["digest"]["error"] == banked["error"]


def test_a_null_deadline_costs_the_countdown_and_nothing_else(app, capsys):
    """G1's third defect. A null ``deadline_time`` parses to NaT rather than
    raising, so the guarded parse lets it through and everything downstream
    throws: ``NaT.strftime`` is a ValueError, and so is ``round(nan / 24)``
    once nan has failed both hour guards. Either escapes ``friday_briefing``
    into the run's one ``except``, and the user gets the failure artifact
    instead of a briefing minus one section. The section is what should be
    absent, not the briefing."""
    from gaffer.digest import run_digest

    tmp_path, _client = app
    pd.DataFrame({"gw": [GW], "deadline_time": [None]}).to_parquet(
        tmp_path / "data/live/events.parquet", index=False)
    # ``latest_gw`` is what gives the briefing a gameweek to count down to,
    # and it reads the solve states — without one the section is absent for
    # the wrong reason and the rail proves nothing.
    (tmp_path / f"reports/solve_state_gw{GW}.json").write_text("{}")
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(
        json.dumps({"gw": GW, "buys": [], "sells": []}))

    from gaffer.digest import _deadline_bits
    assert _deadline_bits(GW) == []          # the throwing call, guarded

    payload = run_digest("friday", notify=False)
    assert payload is not None and payload.get("error") is None
    assert "deadline" not in {s["key"] for s in payload["sections"]}
    assert "digest not built" not in capsys.readouterr().out


def test_notify_false_makes_no_osascript_call(app, monkeypatch):
    """The rail that matters: not a suppressed call — no call."""
    from gaffer import digest as mod

    calls = []
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda *a, **k: calls.append(a))
    mod.run_digest("friday", notify=False)
    assert calls == []


def test_a_missing_osascript_binary_is_not_a_failed_job(app, monkeypatch,
                                                        capsys):
    from gaffer import digest as mod

    monkeypatch.setattr(mod.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            FileNotFoundError("osascript")))
    assert mod.run_digest("friday", notify=True) is not None
    assert "notification not shown" in capsys.readouterr().out


def test_the_digest_endpoint_is_never_a_500(app):
    tmp_path, client = app
    (tmp_path / "reports/digest_friday.json").write_text("{not json")
    assert client.get("/api/digest").json()["available"] is False


def test_the_digest_writes_nothing_but_its_own_artifact(app):
    """A6, asserted as a source screen: the review job holds a lock on the
    ledger at 09:00 and the debrief runs at 09:30."""
    import inspect

    import gaffer.digest as mod

    src = inspect.getsource(mod)
    for forbidden in ("append_ledger", "append_sim_history", "run_review",
                      "save_availability", "save_components",
                      "append_snapshot", "save_solve_state"):
        assert forbidden not in src, forbidden


# --- rail 5: the retrain diff ---------------------------------------

def test_no_predecessor_breakdown_is_an_absent_claim_not_a_quiet_one(app):
    """A9. The first advise run after this cycle merges must say nothing."""
    from gaffer.artifacts import COMPONENT_COLS, ep_movers, save_components

    tmp_path, client = app
    frame = pd.DataFrame([{"code": 11, "name": "Saka", "gw": GW, "ep": 5.0}])
    for col in COMPONENT_COLS:
        if col not in frame.columns:
            frame[col] = float("nan")
    save_components(frame[COMPONENT_COLS], GW)
    (tmp_path / f"reports/gw{GW}-advice.json").write_text(
        json.dumps({"gw": GW, "buys": [], "sells": []}))
    assert ep_movers(GW) is None
    assert client.get(f"/api/advice/diff?gw={GW}").json()["ep_movers_count"] \
        is None


def test_a_failed_predecessor_copy_never_fails_an_advise_run(app,
                                                             monkeypatch):
    from gaffer.artifacts import (COMPONENT_COLS, components_path,
                                  save_components)

    frame = pd.DataFrame([{"code": 11, "name": "Saka", "gw": GW, "ep": 5.0}])
    for col in COMPONENT_COLS:
        if col not in frame.columns:
            frame[col] = float("nan")
    save_components(frame[COMPONENT_COLS], GW)
    monkeypatch.setattr("gaffer.artifacts.shutil.copyfile",
                        lambda *a: (_ for _ in ()).throw(OSError("full")))
    assert save_components(frame[COMPONENT_COLS], GW) == components_path(GW)


# --- rail 6: the pins v8f moved, asserted from v8f's own file -------

def test_v8f_adds_exactly_two_job_kinds():
    """The pin six other suites assert, asserted a seventh time from this
    cycle's own file, so a v8h kind fails here rather than in somebody
    else's."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12
    assert "digest-friday" in JOB_KINDS and "digest-tuesday" in JOB_KINDS


def test_v8f_added_exactly_one_config_key():
    """Spec §2: ``[digest] notify`` only. A second key would be a switch
    nobody finds and a degraded state nobody tests."""
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert "digest_notify" in names
    assert not [n for n in names
                if ("watch" in n or "digest" in n or "price_log" in n)
                and n != "digest_notify"]
    # 48 keys as of v8f. Any change to this number is a config key a later
    # cycle had no business adding without moving the pin deliberately.
    assert len(names) == 48


# --- rail 7: protected ordering, forward ----------------------------

def test_the_advice_payloads_watch_set_is_still_squad_plus_plan():
    """advise.py is protected, so the payload's alerts stay narrow and the
    *web* card carries the wider set. A future cycle that widened one without
    the other would give the user two different answers to one question."""
    import inspect

    from gaffer import advise

    src = inspect.getsource(advise.run_advise)
    assert "watch = set(first.buys + first.sells + owned_now)" in src


def test_the_availability_pass_still_ends_with_the_override():
    """v8e's ordering pin, carried forward: v8f touches none of that path and
    the rail says so out loud rather than by omission."""
    import inspect

    from gaffer.models import availability

    assert "_override_first_gw(out)" in inspect.getsource(
        availability.apply_availability)
