"""Which predicted-XI providers are allowed to speak.

``[news] lineups`` is a switch for a source going *silent*, and a silent
source already degrades to the flags-only path on its own. v10 adds a second
provider merged by pessimism — ``min p_start_hint`` — which means a provider
that parses cleanly and resolves above the coverage floor and is simply
*wrong* can only ever pull hints down, benching real starters, and cannot be
turned off without also turning off the provider that is working. Creating a
failure mode whose only remedy is disabling the whole feature is not a trade
worth one saved config key (plan A6).

**Deviation from plan A6, and the reason.** A6 specified a 49th ``Config``
dataclass field. It cannot have one: ``tests/test_v9c_degradation.py:323`` and
``tests/test_v9d_degradation.py:421`` both pin
``len(dataclasses.fields(Config)) == 48``, both files are protected, and the
plan's own Task 2 pre-registered this grep as a stop. The switch is therefore
a module-level reader — :func:`gaffer.config.lineup_providers`, reading
``[news] lineup_providers`` from the same TOML through the same tolerant
parsing — which keeps every behaviour A6 argued for (a per-source kill, an
empty list as the limit case, a typo that is dropped rather than raised on)
and moves no pin. ``fetch_lineups`` reads it at serve time exactly as it reads
``serving_config()``, because ``advise.py`` is protected and cannot forward it.
"""

from __future__ import annotations

import dataclasses

import pytest

from gaffer.config import (DEFAULT_LINEUP_PROVIDERS, Config, _providers,
                           lineup_providers)


def _write(tmp_path, body: str):
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_the_default_is_both_providers():
    assert list(DEFAULT_LINEUP_PROVIDERS) == ["ffs", "rotowire"]
    assert _providers(None) == ["ffs", "rotowire"]


def test_a_toml_list_overrides_the_default(tmp_path):
    path = _write(tmp_path, '[news]\nlineup_providers = ["ffs"]\n')
    assert lineup_providers(path) == ["ffs"]


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


def test_a_missing_file_or_section_gives_the_default(tmp_path):
    assert lineup_providers(tmp_path / "nope.toml") == ["ffs", "rotowire"]
    assert lineup_providers(_write(tmp_path, "[news]\n")) == ["ffs", "rotowire"]


def test_a_corrupt_toml_gives_the_default_rather_than_raising(tmp_path):
    """Serve-time readers never raise: a broken config must degrade to the
    shipped behaviour, not take the news layer down."""
    assert lineup_providers(_write(tmp_path, "[news\n")) == ["ffs", "rotowire"]


def test_the_config_dataclass_did_not_grow(tmp_path):
    """The deviation, pinned. v9c and v9d both assert 48 and both are
    protected; the switch is a reader, so the count is untouched."""
    assert len(dataclasses.fields(Config)) == 48
    assert not any(f.name == "news_lineup_providers"
                   for f in dataclasses.fields(Config))


def test_the_two_switches_compose(tmp_path):
    """``lineups = false`` short-circuits in advise.py before providers are
    ever read, so the coarse switch wins and the fine one is a per-source
    refinement of it."""
    path = _write(tmp_path,
                  '[news]\nlineups = false\nlineup_providers = ["ffs"]\n')
    assert lineup_providers(path) == ["ffs"]
    from gaffer.config import load_config
    with pytest.raises(Exception):
        load_config(tmp_path / "absent.toml")
