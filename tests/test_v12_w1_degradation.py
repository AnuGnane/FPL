"""v12 W1's degradation rails, and the rails on the suite's two absolute pins.

Every rail here is a state a real machine reaches, and several are the state
this machine is in today: a write interrupted, a season log carrying two
seasons, a report that would overwrite a good one with a degraded one, a tree
with no backups at all, a phone on the LAN with no token.

The file also holds the rails that keep each of the suite's two absolute
counts in exactly one place. Seven protected degradation files used to assert
the config-field total, which meant every cycle entitled to add a key first had
to buy seven authorizations — and one cycle did not:
``tests/test_v10_config_providers.py``'s docstring records v10 abandoning a
designed dataclass field for a module-level reader because two of them pinned
the number. v12 W1 applied v11's route-pin restructure to the config pin.

**The config total itself is no longer here** (orchestrator ruling,
2026-09-02). One number that every key-adding cycle has to move belongs in the
newest cycle's file, which is now ``tests/test_v12_w3_degradation.py``; what
W1 keeps is the claim it is actually entitled to make — *which five keys* it
added. The route total stays where v11 left it, in
``tests/test_v11_degradation.py``, because W3 adds no route and moving it
would be a protected edit that bought nothing.
"""

from __future__ import annotations


# =====================================================================
# Block 8 — the counts
# =====================================================================

def test_the_config_gained_exactly_five_fields():
    """48 at 27f7933 and 53 at the end of W1 — and the **five** is the claim,
    not the 53.

    Seven protected files used to assert 48. That is not a hypothetical cost:
    ``tests/test_v10_config_providers.py``'s docstring records v10 abandoning
    a designed dataclass field because two of them did, and settling for a
    module-level reader instead. v12 W1 replaced each with the by-name claim
    its own cycle is entitled to make — v11's route-pin restructure, applied
    to the other pin.

    v12 W3 (orchestrator ruling 2026-09-02): the absolute total left this file
    with the same reasoning one step further on. A number every key-adding
    cycle must move is a number that belongs in the newest cycle's file, or
    each workstream re-opens the file before it for arithmetic that has
    nothing to do with W1's five keys. It now lives in
    ``tests/test_v12_w3_degradation.py`` and the rail below points there.
    What stays here is the subset claim, which is W1's own and stays true
    however many keys later cycles add.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert {"backup_dir", "backup_rsync_target", "backup_keep",
            "top_n", "web_token"} <= names


def _suite_files():
    """Anchored to this file's own directory, not the working directory —
    v11's rail learned that the hard way: a ``pytest`` run from anywhere but
    the repo root globbed nothing, and a sweep over an empty list passes by
    saying nothing at all."""
    import pathlib

    files = sorted(pathlib.Path(__file__).parent.glob("test_*.py"))
    assert len(files) > 1
    return files


def test_only_one_file_pins_the_absolute_config_field_count():
    """A rail on the rails, exactly as v11 wrote for routes. Without it the
    eighth pin grows back the next time somebody adds a key and reaches for
    the nearest example.

    v12 W3 (orchestrator ruling 2026-09-02): the single home moved from this
    file to ``test_v12_w3_degradation.py``, so this rail names the newest
    cycle's file rather than its own. "Exactly one, and it is the newest
    cycle's" is the claim; the rail moves with the pin, which is one line and
    is the whole maintenance cost of keeping the count in one place.

    v13 moved it again, to ``test_v13_degradation.py``.
    """
    import re

    # Anchored to `assert` at the start of a line, because seven files now
    # carry a *comment* saying the count used to be here — the restructure's
    # own audit trail must not read as the pin it replaced. And qualified by
    # `fields(Config)` somewhere in the file, because `len(names) == N` is a
    # shape other suites use about other sets (`test_v12_io.py` counts temp
    # files that way).
    #
    # What it cannot see, stated so the next reader does not mistake a pass
    # for proof: the pin bound to any other name (`assert len(keys) == 53`),
    # written the other way round (`assert 53 == len(names)`), inequal
    # (`>= 53`), split across lines, or reached through a variable
    # (`count = len(names)` and an assert below). This rail catches the copy
    # somebody makes from the example above it, which is how the eighth pin
    # actually appears — not an adversary.
    pin = re.compile(r"^\s*assert\s+len\(\s*(?:names"
                     r"|(?:dataclasses\.)?fields\(\s*Config\s*\))\s*\)"
                     r"\s*==\s*\d+", re.M)
    hits = [p.name for p in _suite_files()
            if "fields(Config)" in (text := p.read_text()) and pin.search(text)]
    assert hits == ["test_v13_degradation.py"]


def test_only_one_file_pins_the_absolute_route_count():
    """The other half of the same rail, and the reason this file does not hold
    that number: v11 built the single home for it and W1 spent it there. Two
    files pinning one total is the shape both restructures existed to end, so
    "exactly one, and it is v11's" is the claim rather than "not here".

    Blind in the same places as the config rail, plus one of its own: the
    route total counted through any name but ``paths`` — inline as
    ``len(create_app().openapi()["paths"])``, or bound as ``routes`` — passes
    unseen. The rail is a guard against the copied example, not a proof.
    """
    import re

    pin = re.compile(r"^\s*assert\s+len\(\s*(?:set\()?\s*paths\)?\s*\)"
                     r"\s*==\s*\d+", re.M)
    hits = [p.name for p in _suite_files() if pin.search(p.read_text())]
    assert hits == ["test_v11_degradation.py"]


def test_the_job_kinds_are_still_twelve():
    """W1 adds three CLI commands and no lane. A thirteenth kind would also
    need a row in ABANDON_TIMEOUT_S or SLOW_ABANDON_KINDS, pinned as jointly
    exhaustive in the protected test_v9d_degradation.py."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12


# =====================================================================
# Block 1 — the atomic write (§2.11, §1)
# =====================================================================
#
# A failed write leaves the previous file byte-identical, once per family.
# Three families, three tests, because they fail in three different places:
# text through `write_text`, parquet through `store.save`, raw bytes.

def test_a_failed_text_write_leaves_the_previous_digest_intact(tmp_path,
                                                               monkeypatch):
    import json

    import pytest

    from gaffer import artifacts, digest, io

    monkeypatch.chdir(tmp_path)
    good = digest.save_digest("friday", {"kind": "friday", "n": 1})
    before = good.read_bytes()

    def explode(path, data):
        with io.atomic_path(path):
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(digest, "atomic_write", explode)
    with pytest.raises(OSError):
        digest.save_digest("friday", {"kind": "friday", "n": 2})
    assert good.read_bytes() == before
    assert json.loads(good.read_text())["n"] == 1
    # And no orphan temp left behind — the `finally` this helper exists for.
    assert not list(artifacts.REPORTS.glob("*.tmp"))


def test_a_failed_parquet_write_leaves_the_previous_log_intact(tmp_path,
                                                               monkeypatch):
    import pandas as pd
    import pytest

    from gaffer import io, snapshot
    from gaffer.data import store

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    rows = pd.DataFrame([{c: None for c in snapshot.SNAPSHOT_COLS}])
    rows.loc[0, ["season", "gw", "snap_date"]] = ["2026-27", 1, "2026-08-15"]
    snapshot.append_snapshot(rows)
    banked = store.DATA_DIR / snapshot.SNAPSHOT_PATH
    before = banked.read_bytes()

    def explode(frame, rel):
        with io.atomic_path(store.DATA_DIR / rel):
            raise OSError(28, "No space left on device")

    monkeypatch.setattr(snapshot, "atomic_save", explode)
    later = rows.copy()
    later.loc[0, "snap_date"] = "2026-08-16"
    with pytest.raises(OSError):
        snapshot.append_snapshot(later)
    assert banked.read_bytes() == before
    assert not list(banked.parent.glob("*.tmp"))


def test_a_failed_bytes_write_leaves_the_previous_image_intact(tmp_path,
                                                              monkeypatch):
    import pytest

    from gaffer import io
    from gaffer.web.routers import assets

    path = tmp_path / "shirt-3.png"
    assets._bank(path, b"the good image")

    def explode(dest, data):
        with io.atomic_path(dest):
            raise OSError(5, "Input/output error")

    monkeypatch.setattr(assets, "atomic_write", explode)
    with pytest.raises(OSError):
        assets._bank(path, b"half an image")
    assert path.read_bytes() == b"the good image"
    assert not list(tmp_path.glob("*.tmp"))


def test_the_rename_lives_in_one_place_and_the_exceptions_are_named():
    """A9 and A15. Twenty modules open-coded this idiom; nineteen now call the
    helper. ``journal.py`` keeps its own because it is import-only this cycle
    — a recorded residual rather than tolerated drift, which is why this is an
    equality and not a ``<=``. A twenty-first copy fails here.

    ``backup.py`` is not among them, and the near miss is worth recording: a
    streamed tarball is not handed to ``atomic_write`` as bytes, so it looked
    like a case the helper could not serve. ``atomic_path`` yields the temp
    *path* and serves it exactly — which also buys the archive the helper's
    ``finally``, so a Ctrl-C mid-tar leaves no temp behind.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).parents[1] / "src"
    pattern = re.compile(r"(?<!dataclasses\.)(?<!\.)\bos\.replace\(")
    hits = sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*.py")
                  if pattern.search(p.read_text()))
    assert hits == ["gaffer/io.py", "gaffer/journal.py"]


# =====================================================================
# Block 2 — the EO constants (§2.2)
# =====================================================================

def test_no_other_module_assigns_a_numeric_literal_to_an_EO_name():
    """The grep the spec asks for, and the one that decays silently: the
    range assertions live in ``tests/test_v12_eo_constants.py``, but a second
    module quietly redefining one of these would pass every one of them.

    Written as ``= <number>`` rather than the bare suffix, because
    ``FIELD_EO_PATH`` and ``FIELD_EO_COLS`` in ``data/field.py`` end in
    ``_EO`` in spirit and are neither constants of this kind nor numbers.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).parents[1] / "src"
    pattern = re.compile(r"^\s*([A-Z_]*_EO)\s*(?::[^=]+)?=\s*-?\d", re.M)
    offenders = {p.relative_to(root).as_posix(): pattern.findall(p.read_text())
                 for p in root.rglob("*.py")
                 if pattern.search(p.read_text())}
    assert list(offenders) == ["gaffer/optimize/differentials.py"]
    assert sorted(offenders["gaffer/optimize/differentials.py"]) == [
        "ALTERNATIVE_EO", "DIFFERENTIAL_EO", "TEMPLATE_EO"]


# =====================================================================
# Block 3 — the season guard (§2.3, §2.4)
# =====================================================================

def _field_log(tmp_path, monkeypatch):
    """Two seasons in one log, with overlapping element ids.

    The overlap is the whole point: element ids are remapped every summer, so
    element 411 in 2025-26 and element 411 in 2026-27 are two different
    players and a reader that ignores the season serves one as the other.
    """
    import pandas as pd

    from gaffer.data import store

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    store.save(pd.DataFrame([
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 411, "eo": 90.0, "se": 1.0, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 411, "eo": 12.0, "se": 2.0, "n": 300},
    ]), "live/field_eo_log.parquet")


def test_the_field_reader_returns_only_the_named_seasons_rows(tmp_path,
                                                              monkeypatch):
    """Last season's GW38 is a *larger* gameweek than this season's GW2, so a
    reader that picked "the latest row" without a season would serve May's
    ownership for an element that is now a different player."""
    from gaffer.data.field import latest_field_eo

    _field_log(tmp_path, monkeypatch)
    assert latest_field_eo(season="2026-27")[411]["eo"] == 12.0
    assert latest_field_eo(season="2025-26")[411]["eo"] == 90.0


def test_a_bare_call_is_a_type_error_rather_than_a_wrong_answer(tmp_path,
                                                                monkeypatch):
    """§2.3's whole content. The keyword has existed since v10b and was
    optional, and `routers/players.py` forgot it — twice recorded as a
    residual. Required, the omission is a stack trace at import-test time
    rather than a plausible number on a page."""
    import pytest

    from gaffer.data.field import latest_field_eo

    _field_log(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        latest_field_eo()


def test_a_season_the_log_does_not_carry_is_none_and_never_zero(tmp_path,
                                                                monkeypatch):
    """v11's contract, still holding across §2.3's change: an unknown
    ownership is `None`. Zero would render as "nobody owns him", which is a
    claim, and the strongest possible one."""
    from gaffer.data.field import latest_field_eo

    _field_log(tmp_path, monkeypatch)
    assert latest_field_eo(season="2027-28") == {}


def test_the_explorer_serves_nulls_rather_than_zeroes_for_an_absent_season(
        tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    _field_log(tmp_path, monkeypatch)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\ncurrent_season = "2027-28"\n')
    rows = TestClient(create_app()).get("/api/players")
    # A cold clone has no solve state, so the endpoint may refuse — what it
    # must never do is answer with a zero where it means "unknown".
    if rows.status_code == 200:
        for row in rows.json():
            assert row["field_eo"] is None
            assert row["field_se"] is None
            assert row["field_n"] is None


def test_season_from_events_on_an_empty_frame_is_none_and_never_a_guess():
    import pandas as pd

    from gaffer.data.bootstrap import season_from_events

    assert season_from_events(pd.DataFrame()) is None
    assert season_from_events(
        pd.DataFrame({"deadline_time": [None, "not a date"]})) is None


def test_health_on_a_clone_with_no_events_says_cannot_tell(tmp_path,
                                                           monkeypatch):
    """`season_ok` is three-state and the banner draws on `False` alone. A
    cold clone has nothing to compare, and `None` is what that is — a red
    banner derived from "cannot tell" is a false alarm on every fresh
    install."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 2\ncurrent_season = "2026-27"\n')
    payload = TestClient(create_app()).get("/api/health").json()
    assert payload["season_ok"] is None
    assert payload["season_ingested"] is None


# =====================================================================
# Block 4 — the refusals (§2.5, §2.7, §2.1)
# =====================================================================
#
# The three most valuable things in this cycle are a program declining to do
# something, and every review instinct is to soften one into a warning. A
# warning printed into logs/prices.log at 23:45 is a warning nobody reads.

def _bank_tracker(tmp_path, blocks):
    import json

    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "pen_tracker.json").write_text(
        json.dumps({"season": "2026-27", "gws": blocks}))
    return reports / "pen_tracker.json"


def test_track_pens_refuses_to_overwrite_a_good_report_with_an_all_degraded_one(
        tmp_path, monkeypatch):
    good = _bank_tracker(tmp_path, [{"gw": 1, "pens_taken": 2.0}])
    before = good.read_bytes()
    monkeypatch.chdir(tmp_path)

    from gaffer.pen_tracker import save_tracker_guarded

    path, refusal = save_tracker_guarded(
        {"season": "2026-27",
         "gws": [{"gw": 1, "error": "no such file"},
                 {"gw": 2, "error": "no such file"}]})
    assert path is None
    assert "refused" in refusal and "degraded" in refusal
    assert good.read_bytes() == before


def test_track_pens_refuses_an_empty_report_over_a_good_one_too(tmp_path,
                                                                monkeypatch):
    """The hazard the spec does not name: `track_pens` returns *no* gameweeks
    when the live parquet is missing, which loses a season's tracking to a
    file that a refresh would put back."""
    good = _bank_tracker(tmp_path, [{"gw": 1, "pens_taken": 2.0}])
    before = good.read_bytes()
    monkeypatch.chdir(tmp_path)

    from gaffer.pen_tracker import save_tracker_guarded

    path, refusal = save_tracker_guarded({"season": "2026-27", "gws": []})
    assert path is None and "refused" in refusal
    assert good.read_bytes() == before


def test_track_pens_writes_freely_when_there_is_nothing_banked(tmp_path,
                                                               monkeypatch):
    """A first run on a cold clone must write its empty report, or the file
    never comes into existence and the refusal wedges the command forever."""
    monkeypatch.chdir(tmp_path)

    from gaffer.pen_tracker import save_tracker_guarded

    path, refusal = save_tracker_guarded({"season": "2026-27", "gws": []})
    assert refusal is None and path is not None and path.exists()


def test_a_track_pens_refusal_is_a_non_zero_exit(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import gaffer.cli as cli
    from gaffer import pen_tracker

    _bank_tracker(tmp_path, [{"gw": 1, "pens_taken": 2.0}])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pen_tracker, "track_pens",
                        lambda season=None: {"season": "2026-27", "gws": []})
    result = CliRunner().invoke(cli.app, ["track-pens"])
    assert result.exit_code == 1
    assert "refused" in result.stdout


def _tidy_tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


def test_tidy_never_names_the_files_with_named_readers(tmp_path, monkeypatch):
    """Four exclusions, each with a reader: the shared backtest log
    /api/history reads; the S2 arm logs whose only evidence is in logs/; the
    availability, field EO and price logs, which are the corpus; and
    logs/advise.log, which is /api/health's launchd line and which the default
    30-day cutoff would have swallowed within a week."""
    import os
    import time

    from gaffer.tidy import candidates

    tree = _tidy_tree(tmp_path, monkeypatch)
    live, logs = tree / "data" / "live", tree / "logs"
    protected = ["backtest_log.parquet", "backtest_log_s2_main.parquet",
                 "availability_log.parquet", "field_eo_log.parquet",
                 "price_log.parquet"]
    for name in protected:
        (live / name).write_text("x")
    (live / "backtest_log_v7b_orphan.parquet").write_text("x")
    old = time.time() - 400 * 86400
    for name in ("advise.log", "prices.log"):
        (logs / name).write_text("x")
        os.utime(logs / name, (old, old))

    found = candidates()
    assert [p.name for p in found["backtests"]] == [
        "backtest_log_v7b_orphan.parquet"]
    assert [p.name for p in found["logs"]] == ["prices.log"]


def test_a_tidy_dry_run_deletes_nothing(tmp_path, monkeypatch):
    from gaffer.tidy import run_tidy

    tree = _tidy_tree(tmp_path, monkeypatch)
    doomed = tree / "data" / "live" / "backtest_log_v7b_orphan.parquet"
    doomed.write_text("x")
    run_tidy(apply=False)
    assert doomed.exists()


def test_a_backup_of_a_tree_with_nothing_to_archive_writes_no_file(tmp_path,
                                                                   monkeypatch):
    """An empty tar restores to nothing and looks exactly like a success,
    which makes it the worst of the available outcomes."""
    from gaffer import backup

    monkeypatch.chdir(tmp_path)
    assert backup.run_backup(to=tmp_path / "bk") is None
    assert not list((tmp_path / "bk").glob("*"))


def test_prune_keeps_everything_at_keep_zero_and_ignores_foreign_files(
        tmp_path):
    """`keep <= 0` keeps everything: there is no legitimate reason to ask this
    command to keep nothing, and a misread config key must not empty a backup
    directory. And the glob is never `*` — the destination may be a folder the
    user keeps their own files in."""
    from gaffer.backup import prune

    dest = tmp_path / "bk"
    dest.mkdir()
    for name in ("gaffer-20260901-120000.tar.gz",
                 "gaffer-20260902-120000.tar.gz",
                 "holiday-photos.tar.gz", "gaffer-notes.md"):
        (dest / name).write_text("x")
    assert prune(dest, keep=0) == []
    assert len(list(dest.iterdir())) == 4
    prune(dest, keep=1)
    assert (dest / "holiday-photos.tar.gz").exists()
    assert (dest / "gaffer-notes.md").exists()
    assert len(list(dest.glob("gaffer-*.tar.gz"))) == 1


# =====================================================================
# Block 5 — the LAN token (§2.8)
# =====================================================================

def test_no_token_means_no_middleware_at_all(tmp_path, monkeypatch):
    """Every existing caller and every existing test passes no token, so the
    default app has to be the app that has always shipped. A write may still
    be refused by the route on a cold clone; it must not be refused by a check
    nobody asked for."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.post("/api/watchlist", json={}).status_code != 403


def test_a_token_refuses_every_write_and_no_read(tmp_path, monkeypatch):
    """403 and not 401: a 401 invites the browser's own credential prompt for
    a scheme this app does not implement, and the user has nowhere to type.
    OPTIONS and HEAD pass with GET, because a preflight that fails closed
    makes every write look like a network error rather than a refusal."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(token="s3cret"))
    for read in (client.get, client.head, client.options):
        assert read("/api/ping").status_code != 403
    for write in (client.post, client.put, client.patch, client.delete):
        refused = write("/api/watchlist")
        assert refused.status_code == 403
        assert "X-Gaffer-Token" in refused.json()["detail"]


# =====================================================================
# Block 6 — the strip (§2.9)
# =====================================================================

def test_freshness_on_a_cold_clone_is_five_nevers_and_never_a_zero(
        tmp_path, monkeypatch):
    """`age_hours` of 0.0 means "just now", which is the exact opposite of
    what a cold clone is. Five rows and not zero, because a strip that renders
    nothing teaches the reader that its absence means nothing is stale."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    rows = TestClient(create_app()).get("/api/meta/freshness").json()["rows"]
    assert [r["source"] for r in rows] == ["refresh", "odds", "field",
                                           "advise", "backup"]
    assert all(r["age_hours"] is None for r in rows)
    assert not [r for r in rows if r["age_hours"] == 0.0]


def test_freshness_with_a_broken_config_greys_only_the_backup_row(
        tmp_path, monkeypatch):
    """The backup row is the one that needs a config read to find its
    directory. A mistyped key there must cost that row and not the strip,
    which is drawn on every page in the app."""
    import time

    from fastapi.testclient import TestClient

    from gaffer.data import store
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "config.toml").write_text("[backup\n")
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "data" / "live" / "player_gw.parquet").write_text("x")
    response = TestClient(create_app()).get("/api/meta/freshness")
    assert response.status_code == 200
    rows = {r["source"]: r for r in response.json()["rows"]}
    assert rows["backup"]["age_hours"] is None
    assert rows["refresh"]["age_hours"] is not None
    assert rows["refresh"]["age_hours"] < time.time()


def test_freshness_never_errors_on_any_tree(tmp_path, monkeypatch):
    """It is drawn on every page in the app, so a 500 here is a 500
    everywhere. Three trees: bare, half-built, and one whose reports/ is a
    file where a directory is expected."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.get("/api/meta/freshness").status_code == 200
    (tmp_path / "data").mkdir()
    assert client.get("/api/meta/freshness").status_code == 200
    (tmp_path / "reports").write_text("not a directory")
    assert client.get("/api/meta/freshness").status_code == 200


# =====================================================================
# Block 7 — the MCP tools (§2.10)
# =====================================================================

def test_every_mcp_tool_answers_rather_than_raising_on_a_cold_clone(
        tmp_path, monkeypatch):
    """An exception out of a stdio server is a dead subprocess and a model
    with no idea why, where the domain message is exactly the thing that would
    have told it what to do."""
    from gaffer import mcp_server

    monkeypatch.chdir(tmp_path)
    args = {"explain": {"code": 1},
            "whatif": {"transfers_in": [], "transfers_out": []}}
    for name, fn in mcp_server.TOOLS.items():
        out = fn(**args.get(name, {}))
        assert out is not None, name


def test_freshness_and_health_answer_without_a_tree_at_all(tmp_path,
                                                           monkeypatch):
    """These two are what a model reaches for *because* something is wrong, so
    neither may require a working tree to say so."""
    from gaffer import mcp_server

    monkeypatch.chdir(tmp_path)
    assert len(mcp_server.TOOLS["freshness"]()["rows"]) == 5
    assert "error" not in mcp_server.TOOLS["health"]()


def test_the_tool_set_is_six_reads_and_no_verb_that_writes():
    """Spec §8: no write tools in v12. Asserted by name as well as by count,
    because "read-only" is a property a later cycle can lose in one line."""
    from gaffer import mcp_server

    assert sorted(mcp_server.TOOLS) == [
        "explain", "freshness", "health", "ledger", "projections", "whatif"]
    assert not [n for n in mcp_server.TOOLS
                if any(verb in n for verb in ("save", "set", "add", "delete",
                                              "run", "start", "post",
                                              "write", "bank", "refresh"))]
