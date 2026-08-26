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


def test_fetch_club_spells_caches_and_degrades(tmp_path):
    from gaffer.data.news.transfermarkt import fetch_club_spells

    calls: list[str] = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(200, text=_spells_html())

    client = httpx.Client(transport=httpx.MockTransport(handle))
    first = fetch_club_spells("arsenal-fc", 11, cache_dir=tmp_path,
                              client=client)
    assert len(first) == 5
    fetch_club_spells("arsenal-fc", 11, cache_dir=tmp_path, client=client)
    assert len(calls) == 1

    dead = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500)))
    assert fetch_club_spells("chelsea-fc", 631, cache_dir=tmp_path,
                             client=dead).empty


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
