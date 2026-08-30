"""D1's validation: the asset covers every club-date the frame contains.

Exactly one spell per club per date — no gap, no overlap. A gap silently
degrades a club to its season window and an overlap silently splits a squad
in two, and both look like a working feature right up to the gate.

Skipped where the history parquet is absent (a fresh clone, CI): the asset's
own shape is pinned by ``tests/test_managers.py``, and this file is about the
join between the asset and the data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.managers import load_manager_tenures

HISTORY = "history/player_gw.parquet"


def _club_dates() -> pd.DataFrame:
    frames = [store.load(HISTORY)]
    if store.exists("live/player_gw.parquet"):
        frames.append(store.load("live/player_gw.parquet"))
    df = pd.concat(frames, ignore_index=True)
    out = df[["team_code", "kickoff_time"]].dropna().drop_duplicates()
    out["team_code"] = out["team_code"].astype(int)
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                         utc=True)
    return out.dropna(subset=["kickoff_time"])


@pytest.fixture(scope="module")
def tenures():
    if not store.exists(HISTORY):
        pytest.skip("no history parquet on this machine")
    ten = load_manager_tenures()
    if ten is None:
        pytest.skip("no manager-tenure asset on this machine")
    return ten


def test_every_club_date_is_covered_by_exactly_one_spell(tenures):
    dates = _club_dates()
    by_club: dict[int, list] = {}
    for r in tenures.itertuples():
        by_club.setdefault(int(r.team_code), []).append((r.start_date,
                                                         r.end_date))
    bad: list[tuple] = []
    for club, when in zip(dates["team_code"], dates["kickoff_time"]):
        hits = sum(1 for start, end in by_club.get(club, ())
                   if when >= start and (pd.isna(end) or when < end))
        if hits != 1:
            bad.append((club, str(when), hits))
    assert not bad, f"{len(bad)} club-dates not covered exactly once: {bad[:8]}"


def test_no_two_spells_at_one_club_overlap(tenures):
    for club, part in tenures.groupby("team_code"):
        part = part.sort_values("start_date")
        ends = part["end_date"].tolist()
        starts = part["start_date"].tolist()
        for i in range(len(part) - 1):
            assert pd.notna(ends[i]), (
                f"club {club}: a spell before another has no end date")
            assert ends[i] <= starts[i + 1], (
                f"club {club}: spells overlap at {ends[i]}")


def test_every_club_in_the_frame_has_a_spell(tenures):
    clubs = set(_club_dates()["team_code"])
    have = set(tenures["team_code"].astype(int))
    assert not (clubs - have), f"clubs with no spell at all: {clubs - have}"


def test_every_spell_names_a_manager(tenures):
    assert tenures["manager"].astype(str).str.strip().ne("").all()
