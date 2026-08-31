"""v8c's `[league]` keys: their defaults, and that they are really read."""

from __future__ import annotations

import tomllib
from pathlib import Path

from gaffer.config import Config, load_config

BASE = '[fpl]\nentry_id = 1\nleague_id = 5\n'


def _cfg(tmp_path, extra=""):
    path = tmp_path / "config.toml"
    path.write_text(BASE + extra)
    return load_config(path)


def test_every_new_key_has_a_shipping_default(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.field_scrape is True
    assert cfg.field_sample == cfg.tier_sample
    assert cfg.sim_n == 2000
    assert cfg.rival_drift == 0.5


def test_the_dataclass_defaults_match_the_loader_defaults():
    """A Config built in a test must be the same object the loader builds
    from an empty section, or every router test lies about production."""
    plain = Config(entry_id=1, league_id=5)
    assert (plain.field_scrape, plain.sim_n, plain.rival_drift) \
        == (True, 2000, 0.5)


def test_the_sample_size_defaults_to_the_tier_sample_it_shares(tmp_path):
    """One scrape serves both readers, so one number sizes it. Setting
    tier_sample alone must move the field scrape with it."""
    cfg = _cfg(tmp_path, "\n[league]\ntier_sample = 120\n")
    assert cfg.field_sample == 120


def test_the_sample_size_can_still_be_set_apart(tmp_path):
    cfg = _cfg(tmp_path, "\n[league]\ntier_sample = 120\nfield_sample = 400\n")
    assert cfg.tier_sample == 120
    assert cfg.field_sample == 400


def test_every_key_is_read_from_the_file(tmp_path):
    cfg = _cfg(tmp_path, "\n[league]\nfield_scrape = false\nsim_n = 50\n"
                         "rival_drift = 0.0\n")
    assert cfg.field_scrape is False
    assert cfg.sim_n == 50
    assert cfg.rival_drift == 0.0


def test_the_example_file_documents_every_league_key():
    """config.example.toml is the only documentation most of these keys have
    ever had — spec §6 says the section arrives complete or not at all."""
    raw = tomllib.loads(Path("config.example.toml").read_text())
    league = raw.get("league") or {}
    for key in ("z_scale", "lambda_cap", "sigma_floor", "sigma_cap",
                "sigma_min_weeks", "z_deadband", "tier_eo", "tier_sample",
                "field_scrape", "field_sample", "sim_n", "rival_drift"):
        assert key in league, f"[league] {key} is undocumented"


def test_the_example_file_still_loads(tmp_path):
    """A documented default that the loader rejects is worse than no
    documentation: it is a config file that looks copy-pasteable and is not."""
    text = Path("config.example.toml").read_text()
    path = tmp_path / "config.toml"
    path.write_text(text.replace("entry_id = 0", "entry_id = 1"))
    cfg = load_config(path)
    assert cfg.sim_n == 2000
