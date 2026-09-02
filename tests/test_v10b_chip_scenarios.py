"""``data/chip_scenarios.toml``, derived from the fixture list as published.

v4c shipped the hook and left the file for "around January, when the fixture
projections land". The projections are still not here, and this cycle does not
pretend otherwise — but the *scheduled* doubles need no projection at all. A
gameweek in which some team plays twice, in the list FPL has published, happens
with probability 1.0. That is what the writer writes, and nothing else.

The write *rule* is the part that needs care, and it is three rules:

* doubles → write them;
* no doubles and no file → **write nothing**, which is today's state on every
  machine and the thing the removed ``test_the_scenario_file_is_absent_this_
  cycle`` was really protecting;
* no doubles and an existing file → rewrite it empty, so a reverted
  rearrangement stops standing. ``load_chip_scenarios`` reads a file with no
  ``[dgw]`` table as ``{}``, identical in effect to absence.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from gaffer.data.chip_scenarios import write_chip_scenarios
from gaffer.optimize.chip_policy import load_chip_scenarios


def _with_a_double() -> pd.DataFrame:
    """GW2 doubles team 1; GW1 is ordinary."""
    return pd.DataFrame([
        {"gw": 1, "home_id": 1, "away_id": 2},
        {"gw": 1, "home_id": 3, "away_id": 4},
        {"gw": 2, "home_id": 1, "away_id": 3},
        {"gw": 2, "home_id": 2, "away_id": 1},
    ])


def _ordinary() -> pd.DataFrame:
    return pd.DataFrame([
        {"gw": 1, "home_id": 1, "away_id": 2},
        {"gw": 1, "home_id": 3, "away_id": 4},
        {"gw": 2, "home_id": 1, "away_id": 3},
        {"gw": 2, "home_id": 2, "away_id": 4},
    ])


def test_a_scheduled_double_is_written_at_probability_one(tmp_path):
    """Not a guess: ``chip_policy.py:114-136`` reads the value as P(the double
    happens), and a double already in the published list happens."""
    path = tmp_path / "chip_scenarios.toml"
    assert write_chip_scenarios(_with_a_double(), path=path) == 1
    assert load_chip_scenarios(path) == {2: 1.0}


def test_no_doubles_and_no_file_writes_no_file(tmp_path):
    """Today's state, preserved — and pinned as the writer's *behaviour*
    rather than as the state of the developer's data directory, which is what
    the test this replaces was really about."""
    path = tmp_path / "chip_scenarios.toml"
    assert write_chip_scenarios(_ordinary(), path=path) == 0
    assert not path.exists()


def test_no_doubles_and_an_existing_file_empties_it(tmp_path):
    """The self-heal after a reverted rearrangement. Emptied, not deleted:
    deleting a file a user may have edited is a bigger claim than rewriting
    the table this writer owns."""
    path = tmp_path / "chip_scenarios.toml"
    write_chip_scenarios(_with_a_double(), path=path)
    assert load_chip_scenarios(path) == {2: 1.0}
    assert write_chip_scenarios(_ordinary(), path=path) == 0
    assert path.exists()
    # Asserted, not assumed: an empty [dgw] must be identical in effect to
    # an absent file, or the self-heal changes the chip layer's answer.
    assert load_chip_scenarios(path) == {}


def test_the_two_ends_of_one_file_agree(tmp_path):
    """Writer and reader in one test, so a quoting or int-key mistake cannot
    pass by being made consistently in both."""
    path = tmp_path / "chip_scenarios.toml"
    fixtures = pd.concat([_with_a_double(), pd.DataFrame([
        {"gw": 3, "home_id": 4, "away_id": 2},
        {"gw": 3, "home_id": 4, "away_id": 1},
    ])])
    assert write_chip_scenarios(fixtures, path=path) == 2
    assert load_chip_scenarios(path) == {2: 1.0, 3: 1.0}


def test_the_file_says_where_it_came_from(tmp_path):
    """A reader who finds it must know it was derived and is disposable."""
    path = tmp_path / "chip_scenarios.toml"
    write_chip_scenarios(_with_a_double(), path=path)
    header = path.read_text().splitlines()[0]
    assert header.startswith("#")
    assert "chip_scenarios" in path.read_text()
    assert "refresh-data" in path.read_text()


def test_the_write_is_atomic_and_per_pid(tmp_path, monkeypatch):
    """Two writers sharing one ``.tmp`` each unlink the other's file and the
    loser's ``os.replace`` raises. A nightly job and a manual refresh are
    exactly two writers.

    v12 W1 §2.11: the module's private ``_atomic_write`` is gone and the write
    goes through ``gaffer.io``, so the spy follows it. The claim — this
    writer's temp carries this process's pid — is unchanged."""
    import os

    from gaffer import io as gio

    seen: list[str] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(str(src))
        return real_replace(src, dst)

    monkeypatch.setattr(gio.os, "replace", spy)
    path = tmp_path / "chip_scenarios.toml"
    write_chip_scenarios(_with_a_double(), path=path)
    assert seen and str(os.getpid()) in seen[0]
    assert seen[0] != str(path)


def test_codes_are_used_when_a_map_is_supplied(tmp_path):
    """The gameweek is what the file keys on either way, but the map is what
    the router has in hand and the writer must accept it."""
    path = tmp_path / "chip_scenarios.toml"
    assert write_chip_scenarios(_with_a_double(),
                                {1: 14, 2: 43, 3: 3, 4: 8}, path) == 1


def test_an_unreadable_frame_is_a_zero_not_an_exception(tmp_path):
    """It runs inside ``run_data_refresh``'s body. A chip-planning convenience
    that can fail the weekly data refresh is a bad trade however useful."""
    path = tmp_path / "chip_scenarios.toml"
    assert write_chip_scenarios(None, path=path) == 0
    assert write_chip_scenarios(pd.DataFrame([{"nope": 1}]), path=path) == 0
    assert not path.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores mode bits")
def test_an_unwritable_directory_is_a_zero(tmp_path):
    """The same claim as the test above, on the write rather than the frame:
    a destination this process cannot write to is a zero, not an exception
    that fails the weekly data refresh.

    v12 W1 §2.11: this used to point at a *missing* directory, because the
    module's private ``_atomic_write`` did not create parents and a missing
    one raised. ``gaffer.io.atomic_write`` does create them — deliberately,
    for the twelve other call sites that were doing the mkdir themselves — so
    the unwritable case is made unwritable rather than absent. The claim is
    the one the test was written for either way.
    """
    denied = tmp_path / "denied"
    denied.mkdir()
    denied.chmod(0o500)
    try:
        assert write_chip_scenarios(
            _with_a_double(), path=denied / "deeper" / "x.toml") == 0
    finally:
        denied.chmod(0o700)


def test_run_data_refresh_calls_the_writer():
    """A source inspection, in ``test_v9d_degradation.py:337``'s idiom:
    executing the job body would mean a live API call."""
    import inspect

    from gaffer.web.routers import meta

    source = inspect.getsource(meta.run_data_refresh)
    assert "write_chip_scenarios" in source
