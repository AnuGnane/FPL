"""The provider seam under ``fetch_lineups`` (v10 §F2a).

Task 3 adds a shape and moves no number: with ``providers=["ffs"]`` the frame
that comes out is the pre-v10 frame, and the whole value of the task is that
the second provider is then an addition rather than a rewrite.

Task 5's merge rules are appended below, at ``--- the merge ---``.
"""

from __future__ import annotations

import httpx
import pandas as pd

from gaffer.config import DEFAULT_LINEUP_PROVIDERS
from gaffer.data.news.lineups import LINEUP_COLS, PROVIDERS, fetch_lineups


def _players() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [100, 101, 102, 103],
        "name": ["Bukayo Saka", "Gabriel Magalhaes", "Declan Rice",
                 "Kai Havertz"],
        "team_code": [3, 3, 3, 3],
        "starts": [20, 20, 20, 20],
        "status": ["a", "a", "a", "a"],
        "chance_of_playing": [None, None, None, None],
    })


def _teams() -> pd.DataFrame:
    return pd.DataFrame({"code": [3], "name": ["Arsenal"],
                         "short_name": ["ARS"]})


def _ffs_html() -> str:
    """One club, two predicted starters by photo code, one printed Out."""
    return (
        '<h2>Arsenal</h2>'
        '<ul class="row-1">'
        '<li title="Saka (Bukayo)">'
        '<img src="/photos/players/110x140/100.png"></li>'
        '<li title="Rice (Declan)">'
        '<img src="/photos/players/110x140/102.png"></li>'
        '</ul>'
        '<strong>Out:</strong><ul class="players">'
        '<li>Gabriel Magalhaes</li></ul>')


def _transport(calls: list[str], body_for):
    """A transport that answers each provider URL with its own markup."""
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=body_for(str(request.url)))
    return httpx.MockTransport(handler)


def _client(calls, mapping: dict[str, str]):
    def body_for(url: str) -> str:
        for key, body in mapping.items():
            if key in url:
                return body
        return ""
    return httpx.Client(transport=_transport(calls, body_for))


# --- the seam -------------------------------------------------------------

def test_a_provider_is_a_name_a_url_a_parser_and_a_capability():
    """The registry is keyed by the names ``[news] lineup_providers`` uses:
    a provider nobody can name is a provider nobody can kill. The
    completeness of the registry against ``DEFAULT_LINEUP_PROVIDERS`` is
    asserted in ``tests/test_v10_rotowire.py``, once the second provider
    exists to complete it."""
    assert set(PROVIDERS) <= set(DEFAULT_LINEUP_PROVIDERS)
    assert "ffs" in PROVIDERS
    for name, provider in PROVIDERS.items():
        assert provider.name == name
        assert provider.url.startswith("https://")
        assert callable(provider.parse)


def test_ffs_is_absence_capable():
    """Plan A7: the absence rule's safety is XI_SIZE, and XI_SIZE only means
    something for a source that identifies its XI outright. FFS lifts the FPL
    code straight out of a photo URL, so its resolved eleven really is eleven
    identified players."""
    assert PROVIDERS["ffs"].absence_capable is True


def test_a_single_ffs_provider_returns_the_pre_v10_frame(tmp_path):
    """The no-op proof. Written longhand rather than diffed against a
    captured copy of the old code path, because a hand-written expectation is
    the one a reviewer can check."""
    calls: list[str] = []
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client(calls, {"fantasyfootballscout":
                                               _ffs_html()}),
                        providers=["ffs"], absence=False)
    assert list(out.columns) == LINEUP_COLS
    assert list(out["code"]) == [100, 101, 102]
    assert list(out["p_start_hint"]) == [1.0, 0.0, 1.0]
    assert out["absence_damp"].isna().all()
    assert len(calls) == 1


def test_the_source_column_is_still_the_literal_lineups(tmp_path):
    """``normalize.availability_frame`` writes that value and LINEUP_COLS is
    unchanged; a provider name in that column would be a schema change with
    no consumer and a rail to break."""
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client([], {"fantasyfootballscout":
                                            _ffs_html()}),
                        providers=["ffs"])
    assert set(out["source"]) == {"lineups"}


def test_each_provider_has_its_own_cache_file(tmp_path):
    """Two providers sharing one cache file would serve one site's markup to
    the other's parser."""
    fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                  client=_client([], {"fantasyfootballscout": _ffs_html()}),
                  providers=["ffs"])
    names = [p.name for p in tmp_path.iterdir()]
    assert any("lineups-ffs" in n for n in names)
    assert not any(n.startswith("lineups-2") or n == "lineups" for n in names)


def test_a_provider_with_no_markup_contributes_nothing(tmp_path):
    calls: list[str] = []
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client(calls, {}), providers=["ffs"])
    assert out.empty
    assert list(out.columns) == LINEUP_COLS


def test_an_unknown_provider_name_is_skipped_not_fatal(tmp_path, capsys):
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client([], {"fantasyfootballscout":
                                            _ffs_html()}),
                        providers=["opta", "ffs"], absence=False)
    assert list(out["code"]) == [100, 101, 102]
    assert "opta" in capsys.readouterr().out


# --- the merge ------------------------------------------------------------
#
# Spec §F2a's agreement rules. The pleasant discovery is that the module
# already implemented most of them for one source: "lowest hint per code" is
# both the within-provider dedupe and, unchanged, the between-provider merge.

def _rotowire_html(slot_of: dict[str, str] | None = None) -> str:
    """One Arsenal team sheet, each named player in whichever half is asked."""
    slot_of = slot_of or {}
    xi, hurt = [], []
    for name in ("Bukayo Saka", "Gabriel Magalhaes", "Declan Rice"):
        slot = slot_of.get(name, "start")
        li = (f'<li class="lineup__player"><div class="lineup__pos">DC</div>'
              f'<a title="{name}" href="/soccer/player/x-1">x</a>'
              + ("" if slot == "start"
                 else f'<span class="lineup__inj">'
                      f'{"OUT" if slot == "out" else "QUES"}</span>')
              + '</li>')
        (xi if slot == "start" else hurt).append(li)
    body = "".join(xi)
    if hurt:
        body += ('<li class="lineup__title is-middle">Injuries</li>'
                 + "".join(hurt))
    return ('<div class="lineup__box">'
            '<div class="lineup__mteam is-home">Arsenal</div>'
            f'<ul class="lineup__list is-home">{body}</ul></div>')


def _both(ffs: str | None, rw: str | None, calls=None):
    mapping = {}
    if ffs is not None:
        mapping["fantasyfootballscout"] = ffs
    if rw is not None:
        mapping["rotowire"] = rw
    return _client(calls if calls is not None else [], mapping)


def _fetch(tmp_path, ffs, rw, calls=None, **kw):
    return fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                         client=_both(ffs, rw, calls),
                         providers=["ffs", "rotowire"],
                         absence=kw.pop("absence", False), **kw)


def test_both_agreeing_keeps_the_hint_and_one_row(tmp_path):
    out = _fetch(tmp_path, _ffs_html(), _rotowire_html()).set_index("code")
    assert out.loc[100, "p_start_hint"] == 1.0
    assert len(out) == len(set(out.index))


def test_disagreement_resolves_to_the_more_conservative_hint(tmp_path):
    """FFS starts Rice; RotoWire says he is out. 0.0 wins."""
    out = _fetch(tmp_path, _ffs_html(),
                 _rotowire_html({"Declan Rice": "out"})).set_index("code")
    assert out.loc[102, "p_start_hint"] == 0.0


def test_a_doubt_beats_a_start_and_loses_to_an_out(tmp_path):
    out = _fetch(tmp_path, _ffs_html(),
                 _rotowire_html({"Declan Rice": "doubt"})).set_index("code")
    assert out.loc[102, "p_start_hint"] == 0.25
    assert out.loc[101, "p_start_hint"] == 0.0     # FFS Out, RotoWire silent


def test_one_silent_provider_leaves_the_other_alone(tmp_path):
    """Both directions, and byte-identical to the single-provider frame."""
    alone = fetch_lineups(_players(), _teams(), cache_dir=tmp_path / "a",
                          client=_both(_ffs_html(), None),
                          providers=["ffs"], absence=False)
    merged = _fetch(tmp_path / "b", _ffs_html(), None)
    pd.testing.assert_frame_equal(alone, merged)

    rw_alone = fetch_lineups(_players(), _teams(), cache_dir=tmp_path / "c",
                             client=_both(None, _rotowire_html()),
                             providers=["rotowire"], absence=False)
    rw_merged = _fetch(tmp_path / "d", None, _rotowire_html())
    pd.testing.assert_frame_equal(rw_alone, rw_merged)


def test_both_silent_is_the_flags_only_path(tmp_path):
    out = _fetch(tmp_path, None, None)
    assert out.empty
    assert list(out.columns) == LINEUP_COLS


def test_a_starter_named_by_any_provider_carries_no_damp(tmp_path):
    """FFS omits Havertz and damps him; RotoWire starts him. This is the
    ``claimed`` rule that already protects a player within one provider, said
    across two: an omission from one XI is not news when another team sheet
    has him in it."""
    # A full eleven, so XI_SIZE is satisfied and the absence rule actually
    # fires — with two names on the pitch it never does, and the assertion
    # below would pass for the wrong reason.
    squad = pd.DataFrame({
        "code": list(range(200, 213)),
        "name": [f"Player {i}" for i in range(13)],
        "team_code": [3] * 13, "starts": [20] * 13,
        "status": ["a"] * 13, "chance_of_playing": [None] * 13})
    ffs = ('<h2>Arsenal</h2><ul class="row-1">'
           + "".join(f'<li title="Player {i}">'
                     f'<img src="/photos/players/110x140/{200 + i}.png">'
                     f'</li>' for i in range(11))
           + '</ul>')
    # 211 and 212 are regulars FFS left out; RotoWire names 211 a starter.
    rw = ('<div class="lineup__box">'
          '<div class="lineup__mteam is-home">Arsenal</div>'
          '<ul class="lineup__list is-home">'
          '<li class="lineup__player"><div class="lineup__pos">FW</div>'
          '<a title="Player 11" href="/soccer/player/x-1">P</a></li>'
          '</ul></div>')

    damped = fetch_lineups(squad, _teams(), cache_dir=tmp_path / "a",
                           client=_both(ffs, None), providers=["ffs"],
                           absence=True).set_index("code")
    assert damped.loc[211, "absence_damp"] == 0.75    # the rule really fires
    assert damped.loc[212, "absence_damp"] == 0.75

    merged = fetch_lineups(squad, _teams(), cache_dir=tmp_path / "b",
                           client=_both(ffs, rw),
                           providers=["ffs", "rotowire"],
                           absence=True).set_index("code")
    assert merged.loc[211, "p_start_hint"] == 1.0     # RotoWire started him
    assert pd.isna(merged.loc[211, "absence_damp"])   # so the damp is dropped
    assert merged.loc[212, "absence_damp"] == 0.75    # nobody named him


def test_two_damps_for_one_code_take_the_lower(tmp_path):
    """Symmetry with the hint rule: pessimism resolves both columns."""
    import gaffer.data.news.lineups as mod

    frames = [
        pd.DataFrame({"code": [1], "p_start_hint": [float("nan")],
                      "absence_damp": [0.75], "source": ["lineups"],
                      "fetched_at": ["t"]}),
        pd.DataFrame({"code": [1], "p_start_hint": [float("nan")],
                      "absence_damp": [0.5], "source": ["lineups"],
                      "fetched_at": ["t"]}),
    ]
    out = mod._merge(frames)
    assert len(out) == 1
    assert out.loc[0, "absence_damp"] == 0.5


def test_the_output_is_one_row_per_code_sorted_and_lineup_cols_shaped(
        tmp_path):
    out = _fetch(tmp_path, _ffs_html(),
                 _rotowire_html({"Declan Rice": "doubt"}))
    assert list(out.columns) == LINEUP_COLS
    assert list(out["code"]) == sorted(set(out["code"]))
    assert LINEUP_COLS == ["code", "p_start_hint", "absence_damp", "source",
                           "fetched_at"]


def test_a_provider_that_raises_does_not_take_the_others_down(
        tmp_path, monkeypatch, capsys):
    import gaffer.data.news.lineups as mod

    def boom(_markup):
        raise ValueError("markup went sideways")

    monkeypatch.setitem(
        mod.PROVIDERS, "rotowire",
        mod.Provider("rotowire", mod.ROTOWIRE_URL, boom,
                     absence_capable=False))
    out = _fetch(tmp_path, _ffs_html(), _rotowire_html())
    assert list(out["code"]) == [100, 101, 102]
    assert "markup went sideways" in capsys.readouterr().out


def test_an_empty_provider_list_fetches_nothing_at_all(tmp_path):
    """A6's kill switch, end to end."""
    calls: list[str] = []
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_both(_ffs_html(), _rotowire_html(), calls),
                        providers=[])
    assert out.empty
    assert calls == []
