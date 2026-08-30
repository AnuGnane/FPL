"""v8a's [news] keys: defaults, overrides, and the serving reader."""

from __future__ import annotations

from gaffer.config import Config, load_config, serving_config

_TOML = """
[fpl]
entry_id = 1
league_id = 2

[news]
llm_classifier = true
llm_shadow = false
llm_command = "fake -p"
llm_timeout_s = 7
lineup_absence = false
lineup_absence_damp = 0.5
lineup_start_floor = 0.3
"""


def test_the_shipped_defaults_are_the_pre_v8a_behaviour():
    """Everything that could change a number ships OFF or neutral: the
    classifier does not serve, the floor is a no-op, and the one thing that
    is on by default — the absence damp — is the conservative direction."""
    cfg = Config(entry_id=1, league_id=2)
    assert cfg.news_llm_classifier is False
    assert cfg.news_llm_shadow is True
    assert cfg.news_llm_command == "claude -p --output-format json"
    assert cfg.news_llm_timeout_s == 120
    assert cfg.news_lineup_absence is True
    assert cfg.news_lineup_absence_damp == 0.75
    assert cfg.news_lineup_start_floor == 0.0


def test_every_key_is_read_from_the_news_section(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(_TOML, encoding="utf-8")
    cfg = load_config(path)
    assert cfg.news_llm_classifier is True
    assert cfg.news_llm_shadow is False
    assert cfg.news_llm_command == "fake -p"
    assert cfg.news_llm_timeout_s == 7
    assert cfg.news_lineup_absence is False
    assert cfg.news_lineup_absence_damp == 0.5
    assert cfg.news_lineup_start_floor == 0.3


def test_a_missing_config_gives_the_serving_defaults_not_a_raise(monkeypatch,
                                                                 tmp_path):
    """The serve-time seams read this from inside fetchers that must never
    block advice, and a clone without a config.toml still has to predict."""
    monkeypatch.chdir(tmp_path)
    serving_config.cache_clear()
    cfg = serving_config()
    assert cfg.news_lineup_absence is True
    assert cfg.news_llm_classifier is False
    serving_config.cache_clear()


def test_the_example_config_documents_every_new_key():
    text = open("config.example.toml", encoding="utf-8").read()
    for key in ("llm_classifier", "llm_shadow", "llm_command",
                "llm_timeout_s", "lineup_absence", "lineup_absence_damp",
                "lineup_start_floor"):
        assert key in text
