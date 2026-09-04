"""v13 — the transfer ladder (specs/2026-09-04-gaffer-v13-transfer-ladder-design.md).

The rail: the caps at their defaults, the MILP byte-identical with both
caps ``None``, the routes and job kinds, the ladder's shape. This is the
newest cycle's file, so it holds the one absolute ``fields(Config)`` pin
(W3's ruling, 2026-09-02); the absolute route pin stays in v11's file.
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest

from gaffer.config import NO_CAP, Config, load_config
from gaffer.errors import GafferError


# --- Block 1: the two levers ---------------------------------------------

def test_the_config_gained_exactly_two_fields():
    """55 after v12 W3 (``test_v12_w3_degradation.py``), 57 here. The claim
    is the two names; 57 is the arithmetic. Pinned as a total *and* by name
    so a key cannot be swapped for another in one cycle."""
    names = {f.name for f in dataclasses.fields(Config)}
    assert len(names) == 57
    assert {"max_hits", "max_transfers"} <= names


def test_the_caps_default_to_two_hits_and_no_transfer_cap():
    cfg = Config(entry_id=1, league_id=2)
    assert cfg.max_hits == 2
    assert cfg.max_transfers == NO_CAP == 15


def test_the_caps_are_read_from_the_optimizer_table(tmp_path):
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        "[optimizer]\nmax_hits = 1\nmax_transfers = 0\n")
    cfg = load_config(tmp_path / "config.toml")
    assert (cfg.max_hits, cfg.max_transfers) == (1, 0)


@pytest.mark.parametrize("line", ["max_hits = 16", "max_hits = -1",
                                  "max_transfers = 2.5",
                                  "max_transfers = true"])
def test_a_cap_outside_0_to_15_is_refused_by_name(tmp_path, line):
    (tmp_path / "config.toml").write_text(
        f"[fpl]\nentry_id = 1\nleague_id = 2\n[optimizer]\n{line}\n")
    key = line.split(" =")[0]
    with pytest.raises(GafferError, match=key):
        load_config(tmp_path / "config.toml")


def test_the_two_keys_are_documented():
    root = pathlib.Path(__file__).resolve().parents[1]
    for doc in ("config.example.toml", "README.md"):
        text = (root / doc).read_text(encoding="utf-8")
        assert "max_hits" in text and "max_transfers" in text, doc


# --- Block 2: the MILP ---------------------------------------------------

def test_both_caps_none_build_the_golden_lp_byte_for_byte(tmp_path):
    """``tests/data/v12_w3_milp_golden.lp`` came off the code before
    ``force_out`` existed and is unchanged by this cycle: a defaulted
    ``max_transfers`` emits no constraint."""
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    captured = _capture_lp(tmp_path, _state(max_transfers=None,
                                            max_hits=None))
    assert len(captured) == 1
    assert captured[0] == GOLDEN.read_text()


def test_a_transfer_cap_does_change_the_lp(tmp_path):
    """The counterpart: a cap that *is* set writes a row, so the byte
    equality above is evidence about ``None`` and not about the instrument.

    Two, not one. That fixture's owned 15 is 7 MID and 1 FWD against a
    ``SQUAD_COMPOSITION`` of 5 and 3, so it takes two moves to become a legal
    squad at all and a cap of one is infeasible for a reason that has nothing
    to do with this constraint.
    """
    from tests.test_v12_w3_force_out import GOLDEN, _capture_lp, _state

    captured = _capture_lp(tmp_path, _state(max_transfers=2))
    assert captured[0] != GOLDEN.read_text()
