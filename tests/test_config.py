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
