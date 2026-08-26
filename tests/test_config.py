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


# --- v4c decision layer ----------------------------------------------------


def _write(tmp_path, body: str):
    p = tmp_path / "config.toml"
    p.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n' + body)
    return p


def test_scenario_count_defaults_to_zero(tmp_path):
    """n = 0 is the degradation rail: until the gates pass, a fresh clone
    must solve exactly once and print exactly what v4b printed."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.scenarios_n == 0


def test_scenario_thresholds_default_to_the_spec_bars(tmp_path):
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.transfer_threshold == 0.60
    assert cfg.irreversible_threshold == 0.75


def test_scenario_seed_defaults_to_a_fixed_value(tmp_path):
    """Reproducibility is a stated requirement: the same seed must give the
    same advice, and the seed is logged in the report."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert isinstance(cfg.scenarios_seed, int)
    assert cfg.scenarios_seed == 20260825


def test_scenarios_section_is_read(tmp_path):
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, """
[scenarios]
n = 40
seed = 7
transfer_threshold = 0.5
irreversible_threshold = 0.9
"""))
    assert cfg.scenarios_n == 40
    assert cfg.scenarios_seed == 7
    assert cfg.transfer_threshold == 0.5
    assert cfg.irreversible_threshold == 0.9


def test_decision_priors_default_to_enabled(tmp_path):
    """The asset is the thing that may be missing, not the switch. The switch
    exists so a gate failure can be turned off without deleting the file."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.decision_priors is True

    off = load_config(_write(tmp_path, "\n[scenarios]\ndecision_priors = false\n"))
    assert off.decision_priors is False


def test_ft_use_penalty_and_bench_curve_default_to_the_old_objective(tmp_path):
    """Gate D2 flips these. Until then the objective must be term-for-term
    what it was, or the replay comparison measures two changes at once."""
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.ft_use_penalty == 0.0
    assert cfg.bench_curve is None


def test_optimizer_section_carries_the_new_knobs(tmp_path):
    from gaffer.config import load_config

    cfg = load_config(_write(tmp_path, """
[optimizer]
ft_use_penalty = 0.2
bench_curve = [0.21, 0.06, 0.002]
"""))
    assert cfg.ft_use_penalty == 0.2
    assert cfg.bench_curve == [0.21, 0.06, 0.002]


# --- v4d league mode -------------------------------------------------------


def _league_cfg(tmp_path, body: str = ""):
    p = tmp_path / "config.toml"
    p.write_text('[fpl]\nentry_id = 1\nleague_id = 2\n' + body)
    return p


def test_league_section_defaults_to_the_spec_values(tmp_path):
    """A fresh clone with no [league] section gets the dial's pinned
    constants, so nobody has to edit config.toml to get v4d behaviour."""
    cfg = load_config(_league_cfg(tmp_path))
    assert cfg.z_scale == 1.5
    assert cfg.lambda_cap == 0.5
    assert cfg.sigma_floor == 8.0
    assert cfg.sigma_cap == 30.0
    assert cfg.sigma_min_weeks == 6
    assert cfg.z_deadband == 0.25
    assert cfg.tier_eo is True
    assert cfg.tier_sample == 300


def test_league_section_is_read(tmp_path):
    cfg = load_config(_league_cfg(tmp_path, """
[league]
z_scale = 2.0
lambda_cap = 0.25
sigma_floor = 5.0
sigma_cap = 40.0
sigma_min_weeks = 3
z_deadband = 0.4
tier_eo = false
tier_sample = 50
"""))
    assert (cfg.z_scale, cfg.lambda_cap) == (2.0, 0.25)
    assert (cfg.sigma_floor, cfg.sigma_cap) == (5.0, 40.0)
    assert cfg.sigma_min_weeks == 3
    assert cfg.z_deadband == 0.4
    assert cfg.tier_eo is False
    assert cfg.tier_sample == 50


def test_news_section_defaults_to_shipped_behaviour_on(tmp_path):
    """v5's news layer ships enabled. Nobody has to edit config.toml to get
    it, and every source degrades on its own when the site is down."""
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    cfg = load_config(path)
    assert cfg.news_enabled is True
    assert cfg.news_injuries is True
    assert cfg.news_lineups is True
    assert cfg.news_cache_hours == 6
    assert cfg.news_min_coverage == 0.5


def test_news_section_is_read(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[news]\nenabled = false\ninjuries = false\n"
                    "lineups = false\ncache_hours = 24\nmin_coverage = 0.8\n")
    cfg = load_config(path)
    assert cfg.news_enabled is False
    assert cfg.news_injuries is False
    assert cfg.news_lineups is False
    assert cfg.news_cache_hours == 24
    assert cfg.news_min_coverage == 0.8


def test_news_sources_can_be_switched_off_individually(tmp_path):
    """The master switch and the per-source switches are independent: a
    broken line-ups page must not cost the injury feed."""
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    "[news]\nlineups = false\n")
    cfg = load_config(path)
    assert cfg.news_enabled is True
    assert cfg.news_injuries is True
    assert cfg.news_lineups is False
