"""The Friday briefing and the Tuesday debrief: seven reads, no writes.

Two rules carry almost every test in this file.

A section whose input is missing is **absent**, never present-and-empty (plan
A5). "Last week: no data" is a sentence about the tool; the absence of a
section is a sentence about the season, and only one of those is worth a card.

And the digest is a reader (A6). ``review.append_ledger`` takes a lock and is
the ledger's only writer; a Tuesday digest that re-graded a gameweek in order
to report on it would be a second writer on a locked store, run by a launchd
job, at the same hour as the review job. So there is a test that asserts the
module contains no writer at all beyond its own artifact.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from gaffer import artifacts
from gaffer.digest import (DIGEST_KINDS, friday_briefing, load_digest,
                           run_digest, save_digest, tuesday_debrief)

GW = 5

EVENTS = pd.DataFrame({
    "gw": [4, 5, 6],
    "deadline_time": ["2026-08-24T11:00:00Z", "2026-09-04T17:30:00Z",
                      "2026-09-11T17:30:00Z"],
    "is_current": [True, False, False],
    "is_next": [False, True, False],
    "finished": [True, False, False],
    "data_checked": [True, False, False],
})

ADVICE = {
    "gw": GW, "hits": 0, "expected_pts": 61.4,
    "buys": [{"code": 22, "name": "Haaland", "ep": 7.2}],
    "sells": [{"code": 33, "name": "Rice", "ep": 3.1}],
    "captain": {"code": 22, "name": "Haaland", "ep": 7.2},
    "vice": {"code": 11, "name": "Saka", "ep": 5.4},
    "alternatives": [{"code": 44, "name": "Semenyo", "ep": 6.9,
                      "league_eo": 4.0}],
    "xi": [], "bench": [],
}

AVAILABILITY = pd.DataFrame({
    "code": [11, 22, 33],
    "status": ["d", "a", "i"],
    "chance_of_playing": [50.0, 100.0, 0.0],
    "llm_verdict": ["doubt", "fit", "out"],
    "override": [False, False, False],
})

LEDGER = [{"gw": 4, "my_points": 58, "model_points": 63, "accuracy": 71,
           "points_on_bench": 6,
           "hindsight": {"gap": 9},
           "lanes": [{"lane": "captaincy", "delta_pts": -4,
                      "label": "Blunder", "aligned": False},
                     {"lane": "transfers", "delta_pts": 1,
                      "label": "Brilliant", "aligned": False}]}]

PLAYERS_FOR_PRICES = pd.DataFrame({
    "code": [11, 22], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_code": [3, 4],
    "now_cost": [101, 150], "selected_by_percent": [40.0, 60.0],
    "price_change_percent": [98.0, 1.0],
    "price_change_calibrating": [False, False],
})

SNAPSHOT_MTIME = 1_756_000_000        # 2025-08-24, and its own UTC day
SNAPSHOT_DAY = "2025-08-24"
NIGHT_AFTER = "2025-08-25"

SIM_HISTORY = [{"gw": 3, "p_win": 0.14, "p_top3": 0.4, "exp_finish": 3.1,
                "run_at": "2026-08-20T09:00:00Z", "n": 2000, "seed": 7},
               {"gw": 4, "p_win": 0.19, "p_top3": 0.5, "exp_finish": 2.6,
                "run_at": "2026-08-27T09:00:00Z", "n": 2000, "seed": 7}]


@pytest.fixture()
def bare(tmp_path, monkeypatch):
    """A clone with a reports directory and absolutely nothing in it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "data" / "live").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def furnished(bare, monkeypatch):
    EVENTS.to_parquet(bare / "data/live/events.parquet", index=False)
    (bare / f"reports/gw{GW}-advice.json").write_text(json.dumps(ADVICE))
    artifacts.save_availability(AVAILABILITY, GW)
    (bare / "reports/decision_ledger.json").write_text(
        json.dumps({"gws": LEDGER}))
    (bare / "reports/league_sim_history.json").write_text(
        json.dumps({"gws": SIM_HISTORY}))
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: GW)
    monkeypatch.setattr("gaffer.digest.upcoming_gw", lambda: GW)
    monkeypatch.setattr("gaffer.digest.watch_targets",
                        lambda: {11: "squad", 22: "plan"})
    return bare


def _sections(payload) -> dict[str, dict]:
    return {s["key"]: s for s in payload["sections"]}


def _bank_players(root, mtime: int = SNAPSHOT_MTIME):
    """The bootstrap snapshot, aged deliberately: only ``advise`` and
    ``refresh-data`` rewrite it, so its mtime is the reading's real age."""
    path = root / "data/live/players.parquet"
    PLAYERS_FOR_PRICES.to_parquet(path, index=False)
    os.utime(path, (mtime, mtime))
    return path


def _bank_price_log(root, day: str, percent: dict[int, float]):
    """One day of the nightly bank, in the log's own six columns."""
    codes = sorted(percent)
    pd.DataFrame({
        "snap_date": [day] * len(codes),
        "code": codes,
        "now_cost": pd.array([151] * len(codes), dtype="Int64"),
        "price_change_percent": [float(percent[c]) for c in codes],
        "direction": pd.array(["rise"] * len(codes), dtype="string"),
        "calibrating": [False] * len(codes),
    }).to_parquet(root / "data/live/price_log.parquet", index=False)


# --- the envelope -----------------------------------------------------

def test_both_kinds_answer_the_same_envelope(furnished):
    for payload in (friday_briefing(), tuesday_debrief()):
        assert set(payload) == {"kind", "generated_at", "gw", "headline",
                                "sections"}
        assert payload["kind"] in DIGEST_KINDS
        assert isinstance(payload["headline"], str) and payload["headline"]
        assert all(isinstance(s["bits"], list) for s in payload["sections"])


def test_every_bit_is_a_string_because_the_card_joins_them(furnished):
    """The DiffStrip prose idiom, and the reason there is no markdown
    dependency anywhere in this cycle."""
    for payload in (friday_briefing(), tuesday_debrief()):
        for section in payload["sections"]:
            assert all(isinstance(bit, str) and bit for bit in
                       section["bits"])


# --- Friday -----------------------------------------------------------

def test_the_briefing_counts_down_to_the_deadline(furnished):
    section = _sections(friday_briefing())["deadline"]
    assert "GW5" in section["title"] or "GW5" in " ".join(section["bits"])


def test_the_briefing_names_the_move_and_the_armband(furnished):
    bits = " ".join(_sections(friday_briefing())["move"]["bits"])
    assert "Haaland" in bits and "Rice" in bits
    assert "Haaland" in " ".join(_sections(friday_briefing())["move"]["bits"])


def test_the_briefing_flags_only_watched_players(furnished):
    """Player 33 is injured and neither owned nor planned nor starred, so he
    is somebody else's problem."""
    bits = " ".join(_sections(friday_briefing())["flagged"]["bits"])
    assert "50" in bits or "doubt" in bits
    assert "33" not in bits


def test_a_squad_with_nothing_wrong_with_it_has_no_flagged_section(
        furnished):
    artifacts.save_availability(
        AVAILABILITY.assign(status="a", chance_of_playing=100.0,
                            llm_verdict="fit"), GW)
    assert "flagged" not in _sections(friday_briefing())


def test_a_null_verdict_is_no_verdict_and_not_a_crash(furnished):
    """The real ``reports/availability_gw*.parquet`` stores ``llm_verdict``
    and ``status`` as pandas ``string`` and ``override`` as a nullable
    boolean, so a player nobody has classified arrives as ``pd.NA``. ``NA or
    ""`` calls ``bool(NA)``, which raises, and the whole Friday briefing dies
    on a player the section had nothing to say about anyway."""
    artifacts.save_availability(pd.DataFrame({
        "code": [11, 22, 33],
        "status": pd.array(["d", pd.NA, "i"], dtype="string"),
        "chance_of_playing": [50.0, None, 0.0],
        "llm_verdict": pd.array([pd.NA, pd.NA, "out"], dtype="string"),
        "override": pd.array([pd.NA, False, True], dtype="boolean"),
    }), GW)
    flagged = _sections(friday_briefing()).get("flagged")
    # 11 is watched and 50% to play, so he survives; 22 is all-null and is
    # simply nothing to say.
    assert flagged is not None
    bits = " ".join(flagged["bits"])
    assert "50% to play" in bits


def test_a_null_calibrating_flag_does_not_kill_the_price_section(furnished,
                                                                 monkeypatch):
    """``bool(pd.NA)`` raises just as loudly in the movers loop."""
    alerts = pd.DataFrame({
        "code": [11], "name": ["Saka"], "direction": ["rise"],
        "price_change_percent": [98.0],
        "calibrating": pd.array([pd.NA], dtype="boolean"),
    })
    monkeypatch.setattr("gaffer.prices.price_alerts",
                        lambda players, codes: alerts)
    PLAYERS_FOR_PRICES.to_parquet(furnished / "data/live/players.parquet",
                                  index=False)
    movers = _sections(friday_briefing()).get("movers")
    assert movers is not None
    assert "may rise tonight" in " ".join(movers["bits"])


def test_the_briefing_offers_one_differential(furnished):
    bits = " ".join(_sections(friday_briefing())["differential"]["bits"])
    assert "Semenyo" in bits


def test_no_advice_at_all_is_a_briefing_that_says_to_run_one(bare,
                                                             monkeypatch):
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: None)
    monkeypatch.setattr("gaffer.digest.watch_targets", dict)
    payload = friday_briefing()
    assert "move" not in _sections(payload)
    assert "gaffer advise" in payload["headline"]


def test_the_staleness_warning_rides_the_briefing_when_there_is_one(
        furnished, monkeypatch):
    monkeypatch.setattr("gaffer.digest.data_warning",
                        lambda upcoming, through: "model has no data for GW4")
    assert "GW4" in " ".join(_sections(friday_briefing())["staleness"]
                             ["bits"])


def test_no_staleness_warning_is_no_staleness_section(furnished,
                                                      monkeypatch):
    monkeypatch.setattr("gaffer.digest.data_warning",
                        lambda upcoming, through: None)
    assert "staleness" not in _sections(friday_briefing())


# --- the plan's gameweek against the next deadline --------------------

def test_a_plan_a_week_behind_the_deadline_says_so_first(furnished,
                                                          monkeypatch):
    """The briefing reads the newest *solved* gameweek and warns off the
    *upcoming* one, and used never to compare them: a Friday after the GW5
    deadline with only a GW5 solve briefed last week's plan confidently. The
    web staleness strip has always made this comparison; the digest makes it
    too, and makes it before anything it invalidates."""
    monkeypatch.setattr("gaffer.digest.upcoming_gw", lambda: GW + 1)
    payload = friday_briefing()
    assert payload["sections"][0]["key"] == "stale_plan"
    bits = " ".join(payload["sections"][0]["bits"])
    assert f"GW{GW}" in bits and f"GW{GW + 1}" in bits
    assert "gaffer advise" in bits


def test_a_plan_for_the_upcoming_gameweek_has_no_such_section(furnished):
    """``furnished`` pins both helpers to GW5. Current is not a warning."""
    assert "stale_plan" not in _sections(friday_briefing())


def test_a_missing_gameweek_on_either_side_is_no_claim_at_all(bare,
                                                              monkeypatch):
    """A clone with no solve state and a pre-season with no next event are
    both "nothing is known", and a guess in either direction would be a
    sentence about a gameweek nobody named."""
    monkeypatch.setattr("gaffer.digest.watch_targets", dict)
    for latest, upcoming in ((None, GW + 1), (GW, None), (None, None)):
        monkeypatch.setattr("gaffer.digest.latest_gw", lambda v=latest: v)
        monkeypatch.setattr("gaffer.digest.upcoming_gw", lambda v=upcoming: v)
        assert "stale_plan" not in _sections(friday_briefing())


def test_an_upcoming_gameweek_that_raises_costs_no_briefing(furnished,
                                                            monkeypatch,
                                                            capsys):
    """Same contract as every other read here: the section is absent, the
    briefing is not."""
    monkeypatch.setattr("gaffer.digest.upcoming_gw",
                        lambda: (_ for _ in ()).throw(OSError("no events")))
    payload = friday_briefing()
    assert "stale_plan" not in _sections(payload)
    assert payload["headline"]
    assert "no upcoming gameweek" in capsys.readouterr().out


# --- the movers read the freshest price file --------------------------

def test_the_movers_prefer_the_nightly_price_log_when_it_is_newer(furnished):
    """``data/live/players.parquet`` is only rewritten by ``advise`` and
    ``refresh-data``; the 23:15 job banks the whole league every night. A
    Friday briefing quoting Tuesday's predictor is exactly the thing the
    movers section promises not to be."""
    _bank_players(furnished)
    _bank_price_log(furnished, NIGHT_AFTER, {11: 2.0, 22: 99.0})
    bits = " ".join(_sections(friday_briefing())["movers"]["bits"])
    # 22 sits at 1% in the snapshot and 99% in last night's bank.
    assert "Haaland" in bits
    # And 11, at 98% on Tuesday, has since fallen back to 2%.
    assert "Saka" not in bits


def test_the_name_still_comes_from_the_snapshot(furnished):
    """The log banks no ``name`` on purpose — a code is a stable key and a web
    name is not — so the join has to keep the left side's."""
    _bank_players(furnished)
    _bank_price_log(furnished, NIGHT_AFTER, {22: 99.0})
    assert "Haaland" in " ".join(_sections(friday_briefing())["movers"]
                                 ["bits"])


def test_a_price_log_no_newer_than_the_snapshot_is_not_preferred(furnished):
    """The log's key is a UTC day, so "newer" can only be decided to the day
    and a same-day tie goes to the snapshot the pipeline just wrote."""
    _bank_players(furnished)
    _bank_price_log(furnished, SNAPSHOT_DAY, {11: 1.0, 22: 99.0})
    bits = " ".join(_sections(friday_briefing())["movers"]["bits"])
    assert "Saka" in bits and "Haaland" not in bits


def test_a_corrupt_price_log_leaves_the_snapshot_alone(furnished, capsys):
    (furnished / "data/live/price_log.parquet").write_text("garbage")
    _bank_players(furnished)
    bits = " ".join(_sections(friday_briefing())["movers"]["bits"])
    assert "Saka" in bits
    assert "price log unusable" in capsys.readouterr().out


def test_no_price_log_at_all_is_the_behaviour_that_existed_before_it(
        furnished):
    _bank_players(furnished)
    assert "Saka" in " ".join(_sections(friday_briefing())["movers"]["bits"])


def test_the_freshest_reading_names_the_file_it_came_from(furnished):
    """The picker is shared with the web card, which has one field to say what
    it is showing, so the source is part of the answer rather than a guess the
    caller makes from the timestamp."""
    from gaffer.digest import freshest_prices

    _bank_players(furnished)
    frame, as_of, source = freshest_prices()
    assert source == "players" and as_of.startswith("2025-08-24")

    _bank_price_log(furnished, NIGHT_AFTER, {11: 3.0, 22: 99.0})
    frame, as_of, source = freshest_prices()
    assert source == "price_log"
    pct = dict(zip(frame["code"], frame["price_change_percent"]))
    assert pct[22] == 99.0 and pct[11] == 3.0
    assert list(frame["name"]) == ["Saka", "Haaland"]


def test_no_snapshot_at_all_is_no_frame_and_no_source_claim(bare):
    from gaffer.digest import freshest_prices

    assert freshest_prices() == (None, None, "players")


# --- Tuesday ----------------------------------------------------------

def test_the_debrief_reports_the_newest_reviewed_gameweek(furnished):
    payload = tuesday_debrief()
    assert payload["gw"] == 4
    bits = " ".join(_sections(payload)["verdict"]["bits"])
    assert "58" in bits and "63" in bits and "71" in bits


def test_the_debrief_names_the_worst_lane_with_its_label(furnished):
    bits = " ".join(_sections(tuesday_debrief())["verdict"]["bits"])
    assert "captaincy" in bits and "Blunder" in bits


def test_the_debrief_reports_the_hindsight_gap(furnished):
    assert "9" in " ".join(_sections(tuesday_debrief())["hindsight"]["bits"])


def test_the_debrief_reports_the_p_win_movement_since_the_previous_gw(
        furnished):
    bits = " ".join(_sections(tuesday_debrief())["league"]["bits"])
    assert "19" in bits            # 0.19 as a percentage
    assert "+" in bits             # it went up from 0.14


def test_one_simulated_gameweek_is_a_level_not_a_movement(furnished,
                                                          tmp_path):
    (tmp_path / "reports/league_sim_history.json").write_text(
        json.dumps({"gws": SIM_HISTORY[:1]}))
    bits = " ".join(_sections(tuesday_debrief())["league"]["bits"])
    assert "14" in bits and "+" not in bits and "-" not in bits


def test_a_no_advice_gameweek_says_so_rather_than_reporting_model_none(
        bare, monkeypatch):
    """GW1 of the real season is a ``no_advice`` row: the manager played, the
    model has no surviving plan, and every lane is null. "model None." is the
    Python repr of that leaking into a push notification — and it reads as a
    model that scored nothing rather than one that never spoke."""
    (bare / "reports/decision_ledger.json").write_text(json.dumps({"gws": [
        {"gw": 1, "no_advice": True, "my_points": 46, "model_points": None,
         "accuracy": None, "points_on_bench": 2,
         "hindsight": {"gap": 9}, "lanes": []}]}))
    headline = tuesday_debrief()["headline"]
    assert "None" not in headline
    assert headline == "GW1: you 46 — no advice survived to compare."


def test_an_unreviewed_season_is_a_debrief_that_says_so(bare, monkeypatch):
    monkeypatch.setattr("gaffer.digest.latest_gw", lambda: None)
    payload = tuesday_debrief()
    assert _sections(payload) == {} or "verdict" not in _sections(payload)
    assert "not been reviewed" in payload["headline"]
    assert payload["gw"] is None


def test_a_corrupt_ledger_is_an_unreviewed_season(furnished, tmp_path):
    (tmp_path / "reports/decision_ledger.json").write_text("{not json")
    assert "verdict" not in _sections(tuesday_debrief())


def test_no_sim_history_is_no_league_section(furnished, tmp_path):
    (tmp_path / "reports/league_sim_history.json").unlink()
    assert "league" not in _sections(tuesday_debrief())


# --- the store --------------------------------------------------------

def test_a_digest_round_trips_through_its_artifact(furnished):
    payload = friday_briefing()
    save_digest("friday", payload)
    assert load_digest("friday") == payload


def test_loading_a_digest_that_was_never_written_is_none(bare):
    assert load_digest("friday") is None


def test_a_corrupt_digest_artifact_reads_as_none(bare):
    (artifacts.REPORTS / "digest_friday.json").write_text("{not json")
    assert load_digest("friday") is None


def test_writing_replaces_rather_than_appends(furnished):
    save_digest("friday", friday_briefing())
    save_digest("friday", {**friday_briefing(), "headline": "second"})
    assert load_digest("friday")["headline"] == "second"


def test_the_write_leaves_no_temp_behind(furnished):
    save_digest("friday", friday_briefing())
    assert not list(artifacts.REPORTS.glob("digest_friday.json*.tmp"))


def test_the_temp_file_is_process_scoped(furnished, monkeypatch):
    """A fixed temp name is one file two writers share, and the Friday job at
    17:00 and a hand-run ``gaffer digest`` are two writers: the loser's
    ``finally`` would unlink the winner's write. The pid makes them separate
    files and ``os.replace`` still makes each swap atomic."""
    seen = []
    real = os.replace

    def spy(src, dst):
        seen.append(str(src))
        return real(src, dst)

    monkeypatch.setattr("gaffer.digest.os.replace", spy)
    save_digest("friday", friday_briefing())
    assert seen and str(os.getpid()) in seen[0]
    assert load_digest("friday") is not None


# --- the runner and the notification ---------------------------------

def test_running_writes_the_artifact_and_prints_one_line(furnished, capsys):
    payload = run_digest("friday", notify=False)
    assert load_digest("friday") == payload
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1
    assert payload["headline"] in printed[0]


def test_notify_false_makes_no_osascript_call_at_all(furnished, monkeypatch):
    """A7: not a suppressed call — no call. The spy is the rail."""
    calls = []
    monkeypatch.setattr("gaffer.digest.subprocess.run",
                        lambda *a, **k: calls.append(a))
    run_digest("friday", notify=False)
    assert calls == []


def test_notify_true_sends_the_headline(furnished, monkeypatch):
    calls = []

    def spy(args, **kwargs):
        calls.append(args)
        class R:  # noqa: D401 — a stand-in CompletedProcess
            returncode = 0
        return R()

    monkeypatch.setattr("gaffer.digest.subprocess.run", spy)
    payload = run_digest("friday", notify=True)
    assert calls and calls[0][0] == "osascript"
    assert payload["headline"] in " ".join(calls[0])
    # shell=False throughout: an argv list, never a command string.
    assert isinstance(calls[0], list)


def test_the_title_and_body_travel_as_arguments_not_as_source(furnished,
                                                              monkeypatch):
    """The em dash in ``TITLES`` is the whole bug: escaping the two halves
    into the AppleScript source with ``json.dumps`` writes ``\\u2014``, which
    AppleScript does not decode — it is a syntax error, and every real
    notification this cycle exited 1. So nothing user-controlled is
    interpolated into the script at all; both halves ride ``argv``."""
    from gaffer.digest import _notify

    calls = []

    def spy(args, **kwargs):
        calls.append(args)
        class R:  # noqa: D401 — a stand-in CompletedProcess
            returncode = 0
        return R()

    monkeypatch.setattr("gaffer.digest.subprocess.run", spy)
    body = 'He said "go" — O\'Brien \\ out\nsecond line'
    assert _notify("Gaffer — Friday briefing", body) is True

    argv = calls[0]
    assert isinstance(argv, list) and argv[0] == "osascript"
    script = " ".join(argv[1:-2])
    # The strings are the last two argv entries, verbatim, never in the source.
    assert argv[-2:] == [body, "Gaffer — Friday briefing"]
    assert body not in script and "\\u" not in script
    assert "item 1 of argv" in script and "item 2 of argv" in script


@pytest.mark.parametrize("failure", [
    FileNotFoundError("osascript"), OSError("no such process"),
    TimeoutError("timed out")])
def test_every_notification_failure_is_swallowed(furnished, monkeypatch,
                                                 failure, capsys):
    """A Linux CI box, a refused permission, a hung binary. None of them is a
    reason for a launchd job to fail."""
    def boom(*_a, **_k):
        raise failure

    monkeypatch.setattr("gaffer.digest.subprocess.run", boom)
    assert run_digest("friday", notify=True) is not None
    assert "notification not shown" in capsys.readouterr().out


def test_an_unknown_kind_is_refused_rather_than_guessed(furnished):
    from gaffer.errors import GafferError

    with pytest.raises(GafferError, match="unknown digest kind"):
        run_digest("wednesday")


def test_a_run_that_cannot_write_still_returns_the_payload(furnished,
                                                           monkeypatch,
                                                           capsys):
    monkeypatch.setattr("gaffer.digest.save_digest",
                        lambda kind, payload: (_ for _ in ()).throw(
                            OSError("read-only file system")))
    assert run_digest("friday", notify=False) is not None
    assert "digest not written" in capsys.readouterr().out


def test_a_total_failure_is_none_and_not_a_traceback(furnished, monkeypatch):
    monkeypatch.setattr("gaffer.digest.friday_briefing",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert run_digest("friday", notify=False) is None


def test_a_total_failure_still_banks_an_artifact_that_names_it(furnished,
                                                               monkeypatch):
    """Never-raise was only half the rail. A Friday that died left *nothing*
    on disk, so the card said "no digest yet" — the same thing it says on a
    clone that has never run one — and a crash on a schedule was invisible
    until somebody read a launchd log. The failure is a digest too."""
    monkeypatch.setattr("gaffer.digest.friday_briefing",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    run_digest("friday", notify=False)

    banked = load_digest("friday")
    assert banked is not None
    assert banked["kind"] == "friday" and banked["sections"] == []
    assert banked["error"] == "RuntimeError: boom"
    assert "boom" in banked["headline"]


# --- A6: the digest is a reader --------------------------------------

def test_the_module_writes_nothing_but_its_own_artifact():
    """The rail that keeps a Tuesday morning safe. ``append_ledger`` holds a
    lock and runs at 09:00; a digest at 09:30 that wrote to the same store
    would be the second writer nobody designed for."""
    import inspect

    import gaffer.digest as mod

    src = inspect.getsource(mod)
    for forbidden in ("append_ledger", "append_sim_history", "run_review",
                      "save_availability", "save_components",
                      "append_snapshot", "save_solve_state"):
        assert forbidden not in src, forbidden
