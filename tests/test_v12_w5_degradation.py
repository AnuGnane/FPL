"""v12 W5 degradation and pins.

Every surface this workstream added, on a tree with nothing in it. The counts
at the bottom are asserted against the values measured at W5's base (Task 0,
5bb7d0e) — not against 45/12/48, which were W1's starting point and which
W1-W4 moved.

Block 5 is the audit rail: the protected-diff check for W5's own range, in the
same shape W3 and W4 wrote theirs, and closed at the same two ends.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from gaffer.config import serving_config
from gaffer.web.app import create_app

# Filled in from Task 0's measurement, not assumed. JOB_KINDS is what W1-W4
# left; W5 adds none. There is no companion constant for the `Config` field
# count on purpose — see `test_w5_added_no_config_field` below.
JOB_KINDS_AT_BASE = 12      # <- Task 0, measured at 5bb7d0e


@pytest.fixture()
def cold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


@pytest.fixture()
def configured(tmp_path, monkeypatch):
    """A tree with a real ``config.toml`` and nothing else.

    The example file, copied — not a hand-written stub: the sections the
    whitelist writes into are the ones a manager actually has, and a stub that
    happened to omit ``[league]`` would make the write test pass by writing a
    table nobody ever has.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    shutil.copy(root / "config.example.toml", tmp_path / "config.toml")
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


# --- Block 1: the cold clone reaches every new surface --------------------


def test_settings_on_a_cold_clone_is_a_200_that_names_the_file_to_copy(cold):
    body = cold.get("/api/settings")
    assert body.status_code == 200
    assert body.json()["rows"] == []
    assert "config.example.toml" in body.json()["overlay_error"]


def test_a_settings_write_on_a_cold_clone_refuses_rather_than_writing(cold,
                                                                      tmp_path):
    body = cold.post("/api/settings", json={"key": "horizon", "value": 5})
    assert body.status_code == 422
    assert not (tmp_path / "config.local.toml").exists()


def test_the_plan_is_still_a_404_that_names_the_command(cold):
    body = cold.get("/api/plan/5")
    assert body.status_code == 404
    assert "advise" in body.json()["detail"]


def test_the_review_ledger_is_still_an_empty_200(cold):
    assert cold.get("/api/review").json() == {"gws": [], "summary": None}


def test_the_watchlist_is_still_an_empty_200(cold):
    assert cold.get("/api/watchlist").json() == {"rows": []}


# --- Block 2: W5's routes, by name ---------------------------------------


def test_w5_added_exactly_one_path_and_this_is_its_name(cold):
    """Pinned by name and by absence, never by total: the absolute count lives
    in test_v11_degradation.py and v11's meta-test enforces that it lives
    nowhere else."""
    paths = set(create_app().openapi()["paths"])
    assert "/api/settings" in paths
    assert not [p for p in paths
                if p.startswith(("/api/trace", "/api/projections",
                                 "/api/config"))]


def test_settings_answers_both_verbs_on_one_path(cold):
    spec = create_app().openapi()["paths"]["/api/settings"]
    assert set(spec) == {"get", "post"}


def test_this_file_does_not_pin_the_absolute_route_count():
    """The rule v11 wrote down, checked from inside the file it constrains.

    v11's own pattern, character for character (``test_v11_degradation.py``'s
    ``test_only_one_file_pins_the_absolute_route_count``). A looser regex here
    would pass on a pin that v11's sweep still catches, which is a green file
    and a red suite.
    """
    text = pathlib.Path(__file__).read_text()
    pin = re.compile(r"len\(\s*(?:set\()?\s*(?:paths"
                     r"|create_app\(\)\.openapi\(\)\[[\"']paths[\"']\])"
                     r"\)?\s*\)\s*==\s*\d+")
    assert not pin.search(text)


# --- Block 3: the counts W5 did not move ---------------------------------


def test_w5_added_no_job_kind():
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == JOB_KINDS_AT_BASE


def test_w5_added_no_config_field():
    """By absence, not by a total — W4's shape, and for W4's reason.

    ``config.local.toml`` is a loader change: a settings *file* is not a
    settings *field*, and ``price_timing`` — the one whitelist entry that is
    not a dataclass field and is not meant to become one — is named here
    because that is the field this workstream would have grown if it had grown
    any.

    There is deliberately no number. The suite's single absolute
    ``fields(Config)`` pin lives in ``tests/test_v12_w3_degradation.py`` and
    ``tests/test_v12_w1_degradation.py``'s
    ``test_only_one_file_pins_the_absolute_config_field_count`` asserts it
    lives nowhere else; a second copy here — even one reached through a
    constant, which is the blind spot that rail's own docstring names — is a
    number that would have to be edited twice from now on. What W5 owes the
    suite is the claim.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert not [n for n in names
                if "price_timing" in n or "overlay" in n or "settings" in n
                or "local" in n or "trace" in n or "snapshot" in n]


# --- Block 4: the honesty rules, checked rather than asserted in prose ----


def test_no_snapshot_reader_defaults_a_season():
    """Spec §1's season guard. `season` is positional and required; a default
    would make a cross-season read the easy call."""
    import inspect

    from gaffer.artifacts import (latest_projection_before,
                                  projection_snapshots)

    for fn in (projection_snapshots, latest_projection_before):
        season = inspect.signature(fn).parameters["season"]
        assert season.default is inspect.Parameter.empty


def test_the_trace_never_reports_a_measured_zero_for_an_unknown():
    from gaffer.trace import trace_plan

    out = trace_plan([{"gw": 5, "buys": [1], "sells": [], "hits": 0,
                       "chip": None}],
                     gws=[5], ep_by={}, positions={}, names={}, decay=1.0,
                     hit_cost=4, ft_value=1.5, itb_value=0.05,
                     free_transfers=1)
    assert out[0].moves[0].ep_gain is None
    assert out[0].ep_gain is None


def test_the_settings_whitelist_cannot_reach_a_secret():
    """The one thing this endpoint must never be able to write.

    ``web_token`` is in the list beside the odds key: an endpoint that could
    rewrite the app's own front door would be worse than no settings page.
    """
    from gaffer.web.settings_keys import WHITELIST

    names = {e.field for e in WHITELIST}
    assert not names & {"odds_api_key", "entry_id", "league_id",
                        "train_seasons", "news_llm_command", "web_token"}


def test_no_file_this_workstream_wrote_declares_a_solver_table():
    """Program-wide ruling, 2026-09-02: the spec's `[solver]` table does not
    exist and every key it names is `[optimizer]`.

    Checked as a TOML *table header* — a line that is exactly ``[solver]`` —
    rather than as the four characters anywhere in the text, because
    ``settings_keys.py`` says in its own docstring that the section does not
    exist and a substring grep would fail on the sentence that records the
    ruling.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    written = [root / "src/gaffer/web/settings_keys.py",
               root / "src/gaffer/web/routers/settings.py",
               root / "src/gaffer/trace.py",
               root / "config.example.toml"]
    for path in written:
        lines = [ln.strip() for ln in path.read_text().splitlines()]
        assert "[solver]" not in lines, path


def test_no_settings_write_lands_in_a_solver_table(configured, tmp_path):
    """The behavioural half of the rule above.

    A grep for a section header says the word is not written down. This says
    the *writer* cannot produce one: every whitelist entry goes into the table
    it declares, and the three tables W5 writes are the three this tree has.
    """
    from gaffer.web.settings_keys import WHITELIST

    assert {e.section for e in WHITELIST} == {"optimizer", "league",
                                              "scenarios"}
    assert configured.post("/api/settings",
                           json={"key": "horizon", "value": 5}).status_code \
        == 200
    assert configured.post("/api/settings",
                           json={"key": "lambda_cap",
                                 "value": 0.5}).status_code == 200
    written = (tmp_path / "config.local.toml").read_text()
    tables = [ln.strip() for ln in written.splitlines()
              if ln.strip().startswith("[")]
    assert tables == ["[optimizer]", "[league]"]


def test_the_price_charge_is_none_rather_than_zero_when_the_term_is_off():
    """The distinction the gate exists for: "we did not charge for this" and
    "we checked and it was free" are different sentences."""
    from gaffer.trace import trace_plan

    weeks = [{"gw": 5, "buys": [], "sells": [], "hits": 0, "chip": None},
             {"gw": 6, "buys": [], "sells": [7], "hits": 0, "chip": None}]
    off = trace_plan(weeks, gws=[5, 6], ep_by={}, positions={}, names={},
                     decay=1.0, hit_cost=4, ft_value=1.5, itb_value=0.05,
                     free_transfers=1, price_timing=False,
                     price_fall={7: 0.9})
    assert off[1].price_charge is None


# =====================================================================
# Block 5 — the protected-diff audit
# =====================================================================

# v12 W5 (orchestrator ruling 2026-09-03, carried from W3's and W4's). A
# workstream's audit rail measures that workstream's own range and nobody
# else's. The base is pinned rather than computed from
# ``merge-base(HEAD, main)``, which moves the moment W5 merges and would start
# auditing whatever is cut next; the end was ``HEAD`` while this cycle ran and
# is pinned at the program close, exactly as W4 closed W3's rail at f903959.
W4_TIP = "5bb7d0e"
"""W4's merge tip on main — W5's point of departure."""

# v12 program close (orchestrator ruling 2026-09-03): W5's rail audits W5's
# range, 5bb7d0e..470234e, not everyone's. W5 is v12's last workstream, so
# there was no next cycle to pin this; the close did.
W5_TIP = "470234e"
"""W5's merge tip on main — the end of the range this rail audits."""

W5_AUTHORIZED = {
    # The one STOP this plan enumerates (plan header A3; Task 3). The absolute
    # route count may be written down in exactly one file, and 46 -> 47 is
    # this cycle's.
    "tests/test_v11_degradation.py",
    # The orchestrator's 2026-09-03 ruling: W4's rail was left open at ``HEAD``
    # and would have started measuring W5's diff under W4's name, so W5 closed
    # its end at W4_TIP before writing a line of its own.
    "tests/test_v12_w4_degradation.py",
}


def _protected(path: str) -> bool:
    """Protected under this program's rules, for the purpose of this audit.

    W5's own degradation files are excluded by prefix rather than by name:
    this cycle writes three of them — the rail below, plus the projections and
    trace files — and a rule that named only one would fail on the two it
    forgot rather than on an unauthorized edit.
    """
    return (path in {"src/gaffer/advise.py", "src/gaffer/set_pieces.py",
                     "src/gaffer/web/jobs.py",
                     "src/gaffer/web/routers/whatif.py",
                     "tests/test_advise.py", "tests/test_odds.py",
                     "tests/test_web_jobs.py", "scripts/s2_replay.py"}
            or path.startswith("src/gaffer/optimize/")
            or (path.startswith("tests/test_") and path.endswith(
                "_degradation.py")
                and not path.startswith("tests/test_v12_w5_")))


def _range(*ends: str) -> list[str] | None:
    """The files changed across W5's range, or ``None`` if it is not here.

    Either end unreachable — a shallow clone, an export, a tree with no git at
    all — and the audit is skipped rather than answered from a range that does
    not exist.
    """
    for end in ends:
        if end == "HEAD":
            continue
        probe = subprocess.run(["git", "cat-file", "-e", f"{end}^{{commit}}"],
                               capture_output=True, check=False)
        if probe.returncode:
            return None
    out = subprocess.run(["git", "diff", "--name-only", *ends],
                         capture_output=True, text=True, check=False)
    if out.returncode:
        return None
    return out.stdout.split()


def test_every_protected_file_w5_touched_was_authorized():
    """The audit, as a test rather than as a step somebody remembers to run.

    W5 enumerates exactly one protected edit — v11's route pin — plus the one
    re-pin the orchestrator authorized on W4's rail, so a hit on ``advise.py``,
    ``optimize/**``, ``web/jobs.py``, ``routers/whatif.py``, ``test_advise.py``,
    ``test_odds.py``, ``test_web_jobs.py``, ``s2_replay.py`` or any other
    cycle's degradation file fails here.
    """
    changed = _range(W4_TIP, W5_TIP)
    if changed is None:
        pytest.skip(f"{W4_TIP} or {W5_TIP} unreachable — W5's range is not "
                    "in this tree")
    touched = {p for p in changed if _protected(p)}
    assert not touched - W5_AUTHORIZED
    # And not vacuous: the STOP is supposed to have moved that file, so a
    # range that comes back empty — a rebase, a squash, a mis-typed SHA —
    # fails here rather than passing as "clean".
    assert "tests/test_v11_degradation.py" in touched


def test_the_branch_banks_no_data_and_no_config():
    """CONVENTIONS §8: a staged ``config.toml`` or a parquet under ``data/``
    is a private tree in a public branch, and every one of them got there by
    an ``add -A`` somebody was in a hurry to type.

    ``config.local.toml`` joins the list this cycle, and it is the one with
    the new way of getting there: the Settings tab writes it on every save, so
    a developer testing the tab has an untracked file in the tree at the exact
    moment he commits the tab.

    ``src/gaffer/web/static`` is on the standing list too and was missing from
    this rail: it is the built frontend bundle, regenerated by every ``npm run
    build``, and W5 is the cycle that touches the frontend most.
    """
    changed = _range(W4_TIP, W5_TIP)
    if changed is None:
        pytest.skip(f"{W4_TIP} or {W5_TIP} unreachable — W5's range is not "
                    "in this tree")
    assert not [p for p in changed
                if p in ("config.toml", "config.local.toml")
                or p.startswith("data/") or p.startswith("reports/")
                or p.startswith("logs/") or p.startswith("models/")
                or p.startswith("src/gaffer/web/static")]
