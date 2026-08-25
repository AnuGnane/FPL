from pathlib import Path
from gaffer.config import load_config


def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[fpl]\nentry_id = 123\nleague_id = 456\n'
        '[optimizer]\nhorizon = 6\ndecay = 0.85\nvice_weight = 0.1\n'
        'bench_weight = 0.1\nft_value = 1.5\nitb_value = 0.05\nhit_cost = 4\n'
        '[data]\ntrain_seasons = ["2022-23"]\ncurrent_season = "2026-27"\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.entry_id == 123
    assert cfg.horizon == 6
    assert cfg.train_seasons == ["2022-23"]


def test_config_defaults_the_new_v4b_switches_on(tmp_path):
    """Both new sources default to enabled and degrade on their own when the
    data is not there — no config edit needed to get the old behaviour."""
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    cfg = load_config(path)
    assert cfg.player_props is True
    assert cfg.understat_enabled is True
    assert cfg.ags_blend_weight == 0.5


def test_config_reads_the_new_v4b_switches(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[odds]\nplayer_props = false\nags_blend_weight = 0.3\n"
                    "[understat]\nenabled = false\n")
    cfg = load_config(path)
    assert cfg.player_props is False
    assert cfg.ags_blend_weight == 0.3
    assert cfg.understat_enabled is False
