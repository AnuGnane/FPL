"""v12 W5 §6.2 — config.local.toml overlays config.toml.

The file the Settings tab owns. Everything here is about what happens when it
is absent, malformed, or carries a key `Config` has never heard of — because
the third one is a `TypeError` out of a splatted section, and `serving_config`
catches that by discarding the user's entire real config (config.py:311-333).

The second half of the file is about *reach*. `config.py` has three
module-level readers — `price_timing`, `xg_per_shot` and `optimizer_top_n` —
that open `config.toml` themselves rather than going through `load_config`,
because the keys they serve are either not `Config` fields or are needed
somewhere no `Config` is in hand. An overlay the loader honoured and those
three did not would be a Settings tab whose price-timing switch saved and did
nothing, so the merge lives in one place they all read through.
"""
from __future__ import annotations

import pytest

from gaffer.config import (LOCAL_OVERLAY, Config, load_config, optimizer_top_n,
                           price_timing, xg_per_shot)

# Every value here is deliberately *different* from the dataclass default, so
# a merge bug that dropped the base file wholesale would change the number
# rather than land on the right one by luck. `decay` defaults to 0.85 and
# `lambda_cap` to 0.5; both are set to something else below, and `top_n`'s
# four pools are one off the shipped 8/22/26/14.
BASE = """
[fpl]
entry_id = 111
league_id = 222

[optimizer]
horizon = 3
decay = 0.7
top_n = { GKP = 9, DEF = 21, MID = 25, FWD = 13 }

[league]
lambda_cap = 0.3
"""


@pytest.fixture()
def tree(tmp_path):
    """A config.toml on disk and a writer for its overlay."""
    base = tmp_path / "config.toml"
    base.write_text(BASE)
    optimizer_top_n.cache_clear()

    def overlay(text: str):
        (tmp_path / LOCAL_OVERLAY).write_text(text)
        optimizer_top_n.cache_clear()

    yield base, overlay
    optimizer_top_n.cache_clear()


def test_no_overlay_is_the_config_exactly_as_it_was(tree):
    base, _ = tree
    cfg = load_config(base)
    assert (cfg.horizon, cfg.decay, cfg.lambda_cap) == (3, 0.7, 0.3)


def test_the_overlay_wins_key_by_key(tree):
    base, overlay = tree
    overlay("[optimizer]\nhorizon = 5\n")
    cfg = load_config(base)
    assert cfg.horizon == 5
    # decay was not overlaid and must survive. A section-level replace would
    # drop it to the dataclass default with nothing on the page to say so —
    # which is why the base file sets 0.7 and not the 0.85 the default already
    # holds: the same bug against 0.85 would have passed this test.
    assert cfg.decay == 0.7
    assert cfg.decay != Config(entry_id=0, league_id=0).decay


def test_it_reaches_a_section_config_toml_never_declared(tree):
    base, overlay = tree
    overlay("[scenarios]\ndecision_priors = false\n")
    assert load_config(base).decision_priors is False


def test_it_overlays_more_than_one_section_at_a_time(tree):
    base, overlay = tree
    overlay("[optimizer]\nhorizon = 6\n\n[league]\nlambda_cap = 0.2\n")
    cfg = load_config(base)
    assert (cfg.horizon, cfg.lambda_cap) == (6, 0.2)


def test_the_overlay_is_a_sibling_of_the_config_it_overlays(tree, tmp_path,
                                                            monkeypatch):
    """Not of the working directory. A hard-coded relative path would let the
    developer's own overlay leak into every fixture that passes a tmp_path."""
    base, _ = tree
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / LOCAL_OVERLAY).write_text("[optimizer]\nhorizon = 99\n")
    monkeypatch.chdir(elsewhere)
    assert load_config(base).horizon == 3


def test_an_unparseable_overlay_is_ignored_and_says_so(tree, capsys):
    """Ignored, not raised on: one bad write from the UI must not take every
    job down, and `serving_config` would swallow the raise by falling back to
    Config(entry_id=0) — the user's whole config, silently gone."""
    base, overlay = tree
    overlay("[optimizer\nhorizon = 5")
    cfg = load_config(base)
    assert cfg.horizon == 3
    out = capsys.readouterr().out
    assert LOCAL_OVERLAY in out and "ignored" in out


def test_an_unknown_key_in_a_splatted_section_is_dropped_not_fatal(tree,
                                                                   capsys):
    """[optimizer] and [data] are splatted into Config(...), so an unknown key
    there is a TypeError. This is the guard that keeps a typo from becoming a
    silent Config(entry_id=0)."""
    base, overlay = tree
    overlay("[optimizer]\nhorizon = 4\nhorzion = 9\n")
    cfg = load_config(base)
    assert cfg.horizon == 4
    assert "horzion" in capsys.readouterr().out


def test_an_unknown_key_in_a_read_by_key_section_is_simply_unread(tree):
    """[league] is read key-by-key, so an unknown key there was never a
    problem and no guard is invented for it."""
    base, overlay = tree
    overlay("[league]\nlambda_cap = 0.3\nnot_a_key = 1\n")
    assert load_config(base).lambda_cap == 0.3


def test_an_empty_overlay_changes_nothing(tree):
    base, overlay = tree
    overlay("")
    assert load_config(base).horizon == 3


def test_the_overlay_cannot_conjure_a_config_without_a_base(tmp_path):
    """The loud "copy config.example.toml" error is the base file's, and an
    overlay beside a missing base does not answer it."""
    from gaffer.errors import GafferError

    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer]\nhorizon = 5\n")
    with pytest.raises(GafferError, match="config.example.toml"):
        load_config(tmp_path / "config.toml")


# ---------------------------------------------------------------------------
# The three module-level readers
# ---------------------------------------------------------------------------
# `load_config` is not the only thing that opens config.toml. `price_timing`,
# `xg_per_shot` and `optimizer_top_n` each read the file directly, and two of
# the nine keys the Settings tab writes are served by two of them. An overlay
# only `load_config` honoured would be a switch that saves and does nothing.


def test_price_timing_in_the_overlay_is_honoured_by_its_reader(tree, capsys):
    """The one whitelist key that is not a Config field at all. It is popped
    out of [optimizer] before the splat (NON_FIELD_OPTIMIZER_KEYS), so the
    unknown-key guard has to *exempt* it — dropping it would leave the Settings
    tab writing a key nothing ever reads."""
    base, overlay = tree
    assert price_timing(base) is True
    overlay("[optimizer]\nprice_timing = false\n")
    assert price_timing(base) is False
    # Exempted, so it is not reported as a typo — and the config still loads,
    # which is the other half of what the exemption buys.
    assert "price_timing" not in capsys.readouterr().out
    assert load_config(base).horizon == 3


def test_top_n_in_the_overlay_reaches_the_field_and_the_solvers_reader(tree):
    """`top_n` is served twice over: `Config.top_n` carries what the file said
    and `optimizer_top_n()` is what `build_pool` actually gets. The Settings
    row edits one key, so both have to move or the tab reports a pool the
    solver never uses."""
    base, overlay = tree
    overlay("[optimizer]\ntop_n = { GKP = 4, DEF = 5, MID = 6, FWD = 7 }\n")
    wanted = {"GKP": 4, "DEF": 5, "MID": 6, "FWD": 7}
    assert load_config(base).top_n == wanted
    assert optimizer_top_n(base) == wanted


def test_xg_per_shot_in_the_overlay_is_honoured_by_its_reader(tree):
    """[model] is not splatted and not on the whitelist, but it is read by the
    third module-level reader — so the merge has to be in one place all three
    read through rather than copied into the two that happened to need it."""
    base, overlay = tree
    assert xg_per_shot(base) is False
    overlay("[model]\nxg_per_shot = true\n")
    assert xg_per_shot(base) is True


def test_a_reader_survives_an_unparseable_overlay(tree):
    """Same posture as the loader's: these three are on the solve and training
    paths, where a config file must never be fatal."""
    base, overlay = tree
    overlay("[optimizer\nprice_timing = false")
    assert price_timing(base) is True
    # The base file's own pool, not the shipped default: an overlay that will
    # not parse falls back to config.toml, not past it.
    assert optimizer_top_n(base)["GKP"] == 9


def test_a_reader_with_no_base_config_still_gives_the_shipped_default(tmp_path):
    base = tmp_path / "config.toml"
    (tmp_path / LOCAL_OVERLAY).write_text("[optimizer]\nprice_timing = false\n")
    # No base file at all: the readers degrade rather than reading the overlay
    # on its own, because an overlay without the file it overlays is a tree in
    # a state nobody configured.
    assert price_timing(base) is True


def test_a_partial_pool_in_the_overlay_keeps_the_positions_it_did_not_name(
        tree):
    """The merge goes one level inside a section as well as across it.

    `top_n` is a table, so a whole-value overwrite would let an overlay naming
    one position drop the other three back to the shipped default — and
    `_optimizer_top_n` starts from DEFAULT_TOP_N, so the drop would look like
    a deliberate 8/22/26/14 rather than like a bug. The Settings tab always
    writes all four; a hand-edited overlay is exactly the file somebody puts
    one line into.
    """
    base, overlay = tree
    overlay("[optimizer]\ntop_n = { GKP = 3 }\n")
    wanted = {"GKP": 3, "DEF": 21, "MID": 25, "FWD": 13}
    assert load_config(base).top_n == wanted
    assert optimizer_top_n(base) == wanted


def test_lineup_providers_in_the_overlay_is_honoured_by_its_reader(tree):
    """The fourth module-level reader. Nothing edits it from the web, which is
    exactly why it is easy to leave behind — and a file that means one thing to
    the loader and another to a reader is worse than a file no reader
    honours."""
    from gaffer.config import DEFAULT_LINEUP_PROVIDERS, lineup_providers

    base, overlay = tree
    assert lineup_providers(base) == list(DEFAULT_LINEUP_PROVIDERS)
    overlay('[news]\nlineup_providers = ["ffs"]\n')
    assert lineup_providers(base) == ["ffs"]
    # And the kill switch survives the merge as itself rather than as "absent".
    overlay("[news]\nlineup_providers = []\n")
    assert lineup_providers(base) == []


def test_the_loader_and_the_endpoint_name_the_same_file_the_same_way(tree,
                                                                     capsys):
    """`config.py` prints one sentence when it ignores a bad overlay and
    `routers/settings.py` builds another for its 422. Neither reads the
    other's, and neither should: a serve-time refusal and a print on the solve
    path are different jobs. What keeps them from drifting into two different
    stories is this — both name the file, and both say the word the user is
    looking for."""
    from gaffer.web.routers import settings as endpoint

    base, overlay = tree
    overlay("[optimizer\nhorizon = 5")
    load_config(base)
    printed = capsys.readouterr().out
    _, served = endpoint._read(base.parent / LOCAL_OVERLAY)
    assert LOCAL_OVERLAY in printed and LOCAL_OVERLAY in served
    assert "ignored" in printed and "ignored" in served


def test_every_splatted_section_is_read_by_key_or_exempt(tree, capsys):
    """The splatted sections are *derived from `load_config` itself*, not read
    off SPLATTED_SECTIONS, because the constant is what could be wrong. A
    section added to the splat and not to the constant is unguarded, and an
    unknown key in it is a TypeError out of `Config(...)` that
    `serving_config` swallows by discarding the user's whole config.

    Note the two splat shapes the source carries: `**raw.get("data", {})` and
    `**optimizer`, the latter a local pre-filtered against
    NON_FIELD_OPTIMIZER_KEYS. Both resolve to a section name here, so a fourth
    written either way is caught.
    """
    import dataclasses
    import inspect
    import re

    from gaffer import config as mod

    source = inspect.getsource(mod.load_config)
    derived = set(re.findall(r"\*\*raw\.get\(\s*[\"']([a-z_]+)[\"']", source))
    for local in re.findall(r"\*\*([a-z_][a-z_0-9]*)\s*,", source):
        bound = re.search(
            rf"^\s*{re.escape(local)}\s*=.*?raw\.get\(\s*[\"']([a-z_]+)[\"']",
            source, re.MULTILINE)
        if bound:
            derived.add(bound.group(1))
    assert derived, "no splat found in load_config — this test went blind"
    assert derived == set(mod.SPLATTED_SECTIONS)

    base, overlay = tree
    fields = {f.name for f in dataclasses.fields(Config)}
    for section in sorted(derived):
        overlay(f"[{section}]\nnot_a_field_anywhere = 1\n")
        # Survives at all: an unguarded splat raises TypeError right here.
        load_config(base)
        assert "not_a_field_anywhere" in capsys.readouterr().out
    # And the exemption is exactly the non-field optimizer keys, not a blanket
    # "anything [optimizer] carries": a typo there is still reported.
    assert not set(mod.NON_FIELD_OPTIMIZER_KEYS) & fields
