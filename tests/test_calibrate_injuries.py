"""The offline injury-curve calibration. Network only through MockTransport;
the asset it writes is what live code reads."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from gaffer.calibrate_injuries import (CURVE_HORIZON, MIN_SPELLS, fit_curves,
                                       write_curves)
from gaffer.data.news.transfermarkt import parse_injury_spells

FIXTURES = Path(__file__).parent / "data" / "news"


def _spells_html() -> str:
    return (FIXTURES / "transfermarkt_spells.html").read_text()


def test_parse_injury_spells_reads_type_and_duration():
    rows = parse_injury_spells(_spells_html())
    assert list(rows.columns) == ["season", "injury_type", "days_out",
                                  "games_missed"]
    assert len(rows) == 5
    assert rows["injury_type"].tolist() == ["hamstring", "knock",
                                            "hamstring", "knee", "knock"]
    assert rows["days_out"].tolist() == [21.0, 5.0, 42.0, 91.0, 6.0]


def test_parse_injury_spells_on_a_rewritten_page_returns_empty():
    assert parse_injury_spells("<html><body>nope</body></html>").empty


def _squad_html() -> str:
    return (FIXTURES / "transfermarkt_squad.html").read_text()


def _tm_transport(calls: list):
    """Squad page, player injury page, or a 404 for anything else.

    Routing on the path rather than answering everything, because the whole
    point of the rework is that the two pages are different pages: a mock that
    served the same body to both would have passed against the v5 club URL
    that does not exist.
    """
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if "/kader/verein/" in path:
            return httpx.Response(200, text=_squad_html())
        if "/verletzungen/spieler/" in path:
            return httpx.Response(200, text=_spells_html())
        return httpx.Response(404)
    return httpx.MockTransport(handle)


def test_squad_player_ids_reads_the_profile_links_once_each(tmp_path):
    from gaffer.data.news.transfermarkt import squad_player_ids

    calls: list[str] = []
    client = httpx.Client(transport=_tm_transport(calls))
    squad = squad_player_ids("fc-arsenal", 11, 2026, client=client,
                             cache_dir=tmp_path)
    assert squad == [("david-raya", 262749), ("bukayo-saka", 433177),
                     ("declan-rice", 357662)]
    assert "/fc-arsenal/kader/verein/11/saison_id/2026" in calls[0]


def test_squad_player_ids_is_cached_permanently_per_club_season(tmp_path):
    """A squad list for a season that has already been read is a fact, not a
    feed. The calibration is re-run whenever it fails half way through, and a
    resumed run must not pay for the twenty squad pages again."""
    from gaffer.data.news.transfermarkt import squad_player_ids

    calls: list[str] = []
    client = httpx.Client(transport=_tm_transport(calls))
    squad_player_ids("fc-arsenal", 11, 2026, client=client, cache_dir=tmp_path)
    squad_player_ids("fc-arsenal", 11, 2026, client=client, cache_dir=tmp_path)
    assert len(calls) == 1


def test_squad_player_ids_degrades_to_an_empty_list(tmp_path):
    from gaffer.data.news.transfermarkt import squad_player_ids

    dead = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500)))
    assert squad_player_ids("fc-chelsea", 631, 2026, client=dead,
                            cache_dir=tmp_path) == []


def test_fetch_player_spells_reads_the_player_page_and_caches_it(tmp_path):
    from gaffer.data.news.transfermarkt import fetch_player_spells

    calls: list[str] = []
    client = httpx.Client(transport=_tm_transport(calls))
    first = fetch_player_spells("bukayo-saka", 433177, client=client,
                                cache_dir=tmp_path)
    assert len(first) == 5
    assert "/bukayo-saka/verletzungen/spieler/433177" in calls[0]
    fetch_player_spells("bukayo-saka", 433177, client=client,
                        cache_dir=tmp_path)
    assert len(calls) == 1


def test_fetch_player_spells_degrades_to_empty(tmp_path):
    from gaffer.data.news.transfermarkt import SPELL_COLS, fetch_player_spells

    dead = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500)))
    out = fetch_player_spells("nobody", 1, client=dead, cache_dir=tmp_path)
    assert out.empty
    assert list(out.columns) == SPELL_COLS


def test_the_v5_club_history_page_is_gone():
    """``/verletztespieler/verein/`` was a guess and it 404s. Keeping a
    fetcher for it around is how a re-run silently calibrates on nothing."""
    import gaffer.data.news.transfermarkt as tm

    assert not hasattr(tm, "club_url")
    assert not hasattr(tm, "fetch_club_spells")


def test_run_calibration_walks_clubs_then_squads_then_players(tmp_path,
                                                              capsys):
    from gaffer.calibrate_injuries import run_calibration

    calls: list[str] = []
    client = httpx.Client(transport=_tm_transport(calls))
    payload = run_calibration({"fc-arsenal": 11}, season_year=2026,
                              cache_dir=tmp_path, client=client, pause=0.0)
    # One squad page, then one injury page per player on it.
    assert len(calls) == 4
    assert payload["spells"] == 15          # three players, five spells each
    assert "fc-arsenal" in capsys.readouterr().out


def test_run_calibration_counts_a_dead_player_page_and_carries_on(tmp_path,
                                                                   capsys):
    """A calibration is not worth abandoning over one dead page, and a run
    that quietly dropped players would fit curves on a sample nobody can
    account for. Every failure is skipped *and counted*."""
    from gaffer.calibrate_injuries import run_calibration

    def handle(request: httpx.Request) -> httpx.Response:
        if "/kader/verein/" in request.url.path:
            return httpx.Response(200, text=_squad_html())
        if "bukayo-saka" in request.url.path:
            return httpx.Response(503)
        return httpx.Response(200, text=_spells_html())

    client = httpx.Client(transport=httpx.MockTransport(handle))
    payload = run_calibration({"fc-arsenal": 11}, season_year=2026,
                              cache_dir=tmp_path, client=client, pause=0.0)
    assert payload["spells"] == 10
    assert payload["players_failed"] == 1
    assert payload["players"] == 2
    assert payload["clubs_failed"] == 0


def test_run_calibration_counts_a_dead_club(tmp_path):
    from gaffer.calibrate_injuries import run_calibration

    dead = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500)))
    payload = run_calibration({"fc-arsenal": 11}, season_year=2026,
                              cache_dir=tmp_path, client=dead, pause=0.0)
    assert payload["clubs_failed"] == 1
    assert payload["spells"] == 0


def _many(days: list[float], itype: str) -> pd.DataFrame:
    return pd.DataFrame({"season": ["25/26"] * len(days),
                         "injury_type": [itype] * len(days),
                         "days_out": days,
                         "games_missed": [0] * len(days)})


def test_fit_curves_is_the_empirical_cdf_of_the_spell_lengths():
    # Forty knocks: half last a week, half three weeks.
    spells = _many([7.0] * 20 + [21.0] * 20, "knock")
    out = fit_curves(spells)
    curve = out["curves"]["knock"]
    assert len(curve) == CURVE_HORIZON + 1
    assert curve[0] == 0.0                      # nobody is back same week
    assert abs(curve[1] - 0.5) < 1e-9           # the 7-day half
    assert abs(curve[3] - 1.0) < 1e-9           # the 21-day half


def test_fit_curves_is_monotone_nondecreasing():
    spells = _many([3.0, 9.0, 30.0, 60.0] * 10, "knee")
    curve = fit_curves(spells)["curves"]["knee"]
    assert all(b >= a for a, b in zip(curve, curve[1:]))
    assert all(0.0 <= v <= 1.0 for v in curve)


def test_a_type_with_too_few_spells_is_folded_into_the_pooled_curve():
    """Five samples is not a distribution. A curve fitted on five spells
    would swing a player's whole horizon on noise."""
    spells = pd.concat([_many([7.0] * MIN_SPELLS, "knock"),
                        _many([90.0] * 3, "achilles")])
    out = fit_curves(spells)
    assert "knock" in out["curves"]
    assert "achilles" not in out["curves"]
    assert len(out["pooled"]) == CURVE_HORIZON + 1


def test_the_pooled_curve_uses_every_spell():
    spells = pd.concat([_many([7.0] * 40, "knock"),
                        _many([70.0] * 40, "knee")])
    pooled = fit_curves(spells)["pooled"]
    assert abs(pooled[1] - 0.5) < 1e-9


def test_write_curves_refuses_a_payload_with_no_pooled_curve(tmp_path):
    with pytest.raises(ValueError, match="pooled"):
        write_curves({"version": 1, "generated_at": "x", "horizon": 8,
                      "curves": {}, "pooled": []},
                     tmp_path / "injury_return_curves.json")


def _payload(**curves) -> dict:
    pooled = curves.pop("pooled", [0.0, 0.5, 1.0])
    return {"version": 1, "generated_at": "x", "horizon": 8,
            "curves": curves, "pooled": pooled}


@pytest.mark.parametrize("bad, why", [
    ({"pooled": [0.2, 0.5, 1.0]}, "start at 0"),
    ({"knock": [0.2, 0.5, 1.0]}, "start at 0"),
    ({"pooled": [0.0, 0.7, 0.4]}, "non-decreasing"),
    ({"knock": [0.0, 0.7, 0.4]}, "non-decreasing"),
    ({"pooled": [0.0, 0.5, 1.4]}, r"\[0, 1\]"),
    ({"knock": [0.0, -0.1, 1.0]}, r"\[0, 1\]"),
])
def test_write_curves_refuses_a_curve_that_is_not_a_cdf(bad, why, tmp_path):
    """The asset is read as ``P(returned by h)``. A curve that starts above
    zero says a player was back the week he got injured; one that dips says
    he un-returned; one outside [0, 1] is not a probability at all. Any of
    the three silently rewrites the horizon decay for a whole season."""
    with pytest.raises(ValueError, match=why):
        write_curves(_payload(**bad), tmp_path / "curves.json")


def test_write_curves_accepts_a_well_formed_pair(tmp_path):
    dest = write_curves(_payload(knock=[0.0, 1.0, 1.0]),
                        tmp_path / "curves.json")
    assert Path(dest).exists()


def test_write_curves_round_trips_through_the_asset_loader(tmp_path,
                                                            monkeypatch):
    from gaffer import assets
    from gaffer.models.availability import return_prob

    spells = _many([7.0] * 40, "knock")
    dest = write_curves(fit_curves(spells),
                        tmp_path / "injury_return_curves.json")
    payload = json.loads(Path(dest).read_text())
    monkeypatch.setattr(assets, "injury_curves_exist", lambda: True)
    monkeypatch.setattr(assets, "load_injury_curves", lambda: payload)
    assert return_prob(payload, "knock", 1) == 1.0
