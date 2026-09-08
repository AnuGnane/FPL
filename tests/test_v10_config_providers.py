"""Which predicted-XI providers are allowed to speak.

``[news] lineups`` is a switch for a source going *silent*, and a silent
source already degrades to the flags-only path on its own. v10 adds a second
provider merged by pessimism — ``min p_start_hint`` — which means a provider
that parses cleanly and resolves above the coverage floor and is simply
*wrong* can only ever pull hints down, benching real starters, and cannot be
turned off without also turning off the provider that is working. Creating a
failure mode whose only remedy is disabling the whole feature is not a trade
worth one saved config key (plan A6).

**The deviation from plan A6, and its end.** A6 specified a 49th ``Config``
dataclass field. v10 could not have one: ``tests/test_v9c_degradation.py:323``
and ``tests/test_v9d_degradation.py:421`` both pinned
``len(dataclasses.fields(Config)) == 48``, both files were protected, and the
plan's own Task 2 pre-registered that grep as a stop, so the switch shipped as
a module-level reader instead. v17e §2.1 took the question up on the merits
and granted the field: it is ``news_lineup_providers``, cleaned by the loader
with the same tolerant parsing, and every behaviour A6 argued for (a
per-source kill, an empty list as the limit case, a typo that is dropped
rather than raised on) is unchanged. Only the storage moved.
"""

from __future__ import annotations

import dataclasses

from gaffer.config import (DEFAULT_LINEUP_PROVIDERS, Config, _providers,
                           config_in_force, load_config)


def _write(tmp_path, body: str):
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n" + body)
    return path


def test_the_default_is_both_providers():
    assert list(DEFAULT_LINEUP_PROVIDERS) == ["ffs", "rotowire"]
    assert _providers(None) == ["ffs", "rotowire"]


def test_a_toml_list_overrides_the_default(tmp_path):
    path = _write(tmp_path, '[news]\nlineup_providers = ["ffs"]\n')
    assert load_config(path).news_lineup_providers == ["ffs"]


def test_an_unknown_name_is_dropped_with_a_line_not_raised(capsys):
    """A typo in a TOML file must not take advice down."""
    assert _providers(["ffs", "opta"]) == ["ffs"]
    assert "opta" in capsys.readouterr().out


def test_a_non_list_value_falls_back_to_the_default(capsys):
    assert _providers("ffs") == ["ffs", "rotowire"]
    assert "not a list" in capsys.readouterr().out


def test_an_empty_list_is_honoured_as_the_kill_switch():
    """A6's limit case: no provider at all, which behaves exactly like
    ``lineups = false`` and is not a mistake to be corrected."""
    assert _providers([]) == []


def test_names_are_lowercased_and_stripped():
    assert _providers(["  FFS ", "RotoWire"]) == ["ffs", "rotowire"]


def test_a_missing_section_gives_the_default(tmp_path):
    assert load_config(_write(tmp_path, "[news]\n")).news_lineup_providers == [
        "ffs", "rotowire"]


def test_a_config_that_will_not_load_gives_the_default(tmp_path, monkeypatch):
    """The view never raises (v17e §2.2): a broken config must degrade to the
    shipped behaviour, not take the news layer down. The reader used to own
    that fallback; the one view owns it now."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[news\n")
    assert config_in_force().news_lineup_providers == ["ffs", "rotowire"]


def test_the_switch_is_a_field_since_v17e():
    """A6's 49th field, refused in v10 on a protected count and granted in
    v17e §2.1 on the merits: one read interface, no private TOML readers."""
    assert any(f.name == "news_lineup_providers"
               for f in dataclasses.fields(Config))


def test_the_two_switches_compose(tmp_path):
    """``lineups = false`` short-circuits in advise.py before providers are
    ever read, so the coarse switch wins and the fine one is a per-source
    refinement of it."""
    path = _write(tmp_path,
                  '[news]\nlineups = false\nlineup_providers = ["ffs"]\n')
    assert load_config(path).news_lineup_providers == ["ffs"]
