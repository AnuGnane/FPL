"""The four numbers that decide who the solver may consider.

`DEFAULT_TOP_N` has picked the candidate pool since the first MILP and has never
appeared anywhere a user could see. That matters for a reason that is not about
tuning: a plan that never mentions an owned player is indistinguishable from a
plan that considered him and rejected him, unless you can find out whether he was
in the pool at all.

The reader is deliberately forgiving. A missing section, a missing key, a typo, a
string where a number should be — every one of them falls back to the shipped
value, because a config error that silently shrinks the solver's pool is a config
error that changes the advice without saying so.

The key lives in `[optimizer]` beside horizon, decay and bench_curve — orchestrator
ruling, 2026-09-02 — and that section is *splatted* into Config, which is why the
field is named `top_n` after its key and why the forgiveness lives in the reader
rather than in `load_config`. The two are pinned against each other below: the
dataclass carries what the file says, the reader carries what the solver gets.
"""

from __future__ import annotations

import dataclasses

from gaffer.config import Config, load_config, optimizer_top_n
from gaffer.optimize.milp import DEFAULT_TOP_N


def _cfg(tmp_path, body=""):
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n" + body)
    return path


def test_the_shipped_default_is_what_it_always_was():
    assert DEFAULT_TOP_N == {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14}


def test_no_config_at_all_gives_the_shipped_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert optimizer_top_n() == DEFAULT_TOP_N


def test_a_config_without_the_section_gives_the_default(tmp_path):
    assert optimizer_top_n(_cfg(tmp_path)) == DEFAULT_TOP_N


def test_the_section_is_read(tmp_path):
    body = "[optimizer]\ntop_n = {GKP = 4, DEF = 10, MID = 12, FWD = 6}\n"
    assert optimizer_top_n(_cfg(tmp_path, body)) == {"GKP": 4, "DEF": 10,
                                                     "MID": 12, "FWD": 6}


def test_a_missing_position_keeps_its_shipped_value(tmp_path):
    """Merged over the default rather than replacing it: a user tuning one
    position should not have to restate the other three, and a solver with no
    goalkeepers in its pool is infeasible rather than fast."""
    body = "[optimizer]\ntop_n = {DEF = 30}\n"
    assert optimizer_top_n(_cfg(tmp_path, body)) == {
        "GKP": 8, "DEF": 30, "MID": 26, "FWD": 14}


def test_an_unknown_position_is_dropped_rather_than_added(tmp_path):
    """`build_pool` iterates the dict and filters `players["position"]`, so an
    unknown key contributes an empty frame — harmless, and a typo that reads
    as harmless is a typo nobody finds. Dropped, so the pool is exactly the
    four positions that exist."""
    body = '[optimizer]\ntop_n = {GKP = 4, MIDD = 99}\n'
    assert set(optimizer_top_n(_cfg(tmp_path, body))) == {"GKP", "DEF", "MID",
                                                          "FWD"}


def test_a_non_numeric_value_falls_back_for_that_position(tmp_path):
    body = '[optimizer]\ntop_n = {GKP = "lots"}\n'
    assert optimizer_top_n(_cfg(tmp_path, body))["GKP"] == 8


def test_a_zero_or_negative_falls_back(tmp_path):
    """A pool of zero at any position makes the squad constraints infeasible,
    which surfaces as "no plan" — a long way from the config line that caused
    it."""
    body = "[optimizer]\ntop_n = {GKP = 0, DEF = -3}\n"
    out = optimizer_top_n(_cfg(tmp_path, body))
    assert (out["GKP"], out["DEF"]) == (8, 22)


def test_a_corrupt_toml_gives_the_default(tmp_path):
    """The serve-time reader convention (`config.lineup_providers`): a broken
    config degrades to the shipped behaviour rather than taking the solver
    down."""
    path = tmp_path / "config.toml"
    path.write_text("[optimizer\n")
    assert optimizer_top_n(path) == DEFAULT_TOP_N


def test_the_key_is_on_the_dataclass_too(tmp_path):
    """Read twice, deliberately, and they are not the same read.

    `optimizer_top_n` is the serve-time reader `build_pool` calls without a
    Config in hand; it merges over the shipped default and forgives anything
    unreadable. `Config.top_n` comes through `[optimizer]`'s splat, which
    forgives nothing and carries exactly what the file said — and it is what
    W5 §6.2's Settings tab will edit. The next test pins the gap between them
    so it cannot rot into a disagreement nobody notices."""
    body = "[optimizer]\ntop_n = {DEF = 30}\n"
    assert load_config(_cfg(tmp_path, body)).top_n["DEF"] == 30


def test_the_splat_carries_a_partial_table_and_the_reader_completes_it(
        tmp_path):
    """The one consequence of putting this key in a splatted section, made
    visible. `[optimizer]` maps TOML keys straight onto dataclass fields, so a
    table naming one position reaches Config naming one position — while the
    solver, which must have four, gets four. Neither is wrong; they answer
    different questions, and a reviewer who "fixes" one to match the other
    breaks whichever they did not read."""
    body = "[optimizer]\ntop_n = {DEF = 30}\n"
    path = _cfg(tmp_path, body)
    assert load_config(path).top_n == {"DEF": 30}
    assert optimizer_top_n(path) == {"GKP": 8, "DEF": 30, "MID": 26,
                                     "FWD": 14}


def test_a_config_with_no_top_n_key_still_loads(tmp_path):
    """The splat's other edge: the field needs a default_factory or every
    existing config.toml in the world stops loading."""
    assert load_config(_cfg(tmp_path)).top_n == DEFAULT_TOP_N


def test_the_build_pool_default_now_comes_from_the_config(tmp_path,
                                                          monkeypatch):
    """The one protected line-group, asserted through behaviour rather than
    through source."""
    import pandas as pd

    from gaffer.optimize.milp import build_pool

    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, "[optimizer]\n"
                   "top_n = {GKP = 1, DEF = 1, MID = 1, FWD = 1}\n")
    # `now_cost` and `team_code` are columns build_pool projects out at the
    # end and an empty `my_picks` needs a `sell` column for the zip; neither
    # has anything to do with the pool size this test is about.
    players = pd.DataFrame({
        "code": [1, 2, 3, 4, 5, 6, 7, 8],
        "position": ["GKP", "GKP", "DEF", "DEF", "MID", "MID", "FWD", "FWD"],
        "team_code": [1] * 8,
        "now_cost": [50] * 8,
    })
    ep = {(c, 1): float(c) for c in range(1, 9)}
    pool = build_pool(players, ep,
                      pd.DataFrame({"code": [], "sell": []}), [1])
    assert len(pool) == 4


def test_the_config_field_count_moved_deliberately():
    """Named here as well as in the degradation file: this key is one of the
    five that move the pin from 48 to 53, and each one should be findable from
    its own test."""
    assert any(f.name == "top_n" for f in dataclasses.fields(Config))
