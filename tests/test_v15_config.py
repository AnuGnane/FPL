"""v15 §3.1 / §4.1 — the focus league and the stance, in config."""

import dataclasses

import pytest

from gaffer.config import LOCAL_OVERLAY, Config, load_config
from gaffer.errors import GafferError

BASE = "[fpl]\nentry_id = 1\nleague_id = 5\n"


def _load(tmp_path, monkeypatch, base: str = BASE, local: str | None = None):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(base)
    if local is not None:
        (tmp_path / LOCAL_OVERLAY).write_text(local)
    return load_config()


def test_stance_is_a_config_field_defaulting_to_auto():
    assert "stance" in {f.name for f in dataclasses.fields(Config)}
    assert Config(entry_id=1, league_id=5).stance == "auto"


def test_no_focus_means_fpl_league_id(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch)
    assert cfg.league_id == 5 and cfg.stance == "auto"


def test_a_focus_in_the_overlay_is_the_effective_league_id(tmp_path,
                                                            monkeypatch):
    cfg = _load(tmp_path, monkeypatch, local="[league]\nfocus = 77\n")
    assert cfg.league_id == 77


def test_a_zero_focus_falls_back_to_fpl_league_id(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, local="[league]\nfocus = 0\n")
    assert cfg.league_id == 5


def test_a_focus_in_config_toml_itself_is_honoured(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, base=BASE + "[league]\nfocus = 9\n")
    assert cfg.league_id == 9


def test_stance_is_read_from_the_league_table(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch, local='[league]\nstance = "defend"\n')
    assert cfg.stance == "defend"


def test_a_bad_stance_fails_load_by_name(tmp_path, monkeypatch):
    with pytest.raises(GafferError, match="stance"):
        _load(tmp_path, monkeypatch, local='[league]\nstance = "attack"\n')


def test_the_other_league_knobs_still_load_beside_them(tmp_path, monkeypatch):
    cfg = _load(tmp_path, monkeypatch,
                local='[league]\nfocus = 77\nstance = "chase"\nlambda_cap = 0.3\n')
    assert (cfg.league_id, cfg.stance, cfg.lambda_cap) == (77, "chase", 0.3)
