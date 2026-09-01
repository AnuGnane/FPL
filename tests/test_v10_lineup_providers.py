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
