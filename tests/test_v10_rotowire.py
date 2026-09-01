"""RotoWire as a second predicted-XI source (v10 §F2a).

The markup below is a hand-trimmed two-fixture excerpt of a live fetch made on
2026-09-01 (plan A5: 200, 462KB, ten fixtures). It is written inline rather
than committed as an asset for the reason every other parser test here gives —
a 460KB fixture is not a readable failure message — and it is deliberately two
fixtures, one Premier League tie and one that is not, so the club guard is
exercised by the same fixture that exercises the parse.

RotoWire carries no FPL photo codes, so every row goes through
``normalize.match_codes`` and is subject to ``NEWS_MIN_COVERAGE``. That is the
correct posture for a source that cannot self-identify, and it is why plan A7
keeps this provider out of the absence rule.
"""

from __future__ import annotations

import httpx
import pandas as pd

from gaffer.config import DEFAULT_LINEUP_PROVIDERS
from gaffer.data.news.lineups import (LINEUP_COLS, PARSE_COLS, PROVIDERS,
                                      fetch_lineups, parse_rotowire)

_XI = ["Kjell Scherpen", "Pervis Estupinan", "Lewis Dunk", "Jan Paul van Hecke",
       "Tariq Lamptey", "Carlos Baleba", "Mats Wieffer", "Kaoru Mitoma",
       "Georginio Rutter", "Yankuba Minteh", "Danny Welbeck"]

_FOREST = ["Matz Sels", "Neco Williams", "Nikola Milenkovic", "Murillo",
           "Ola Aina", "Ryan Yates", "Elliot Anderson", "Morgan Gibbs-White",
           "Anthony Elanga", "Callum Hudson-Odoi", "Chris Wood"]


def _player_li(name: str, pos: str = "DC", inj: str | None = None) -> str:
    tag = f'<span class="lineup__inj">{inj}</span>' if inj else ""
    return (f'<li class="lineup__player"><div class="lineup__pos">{pos}</div>'
            f'<a title="{name}" href="/soccer/player/x-1">{name.split()[-1]}'
            f'</a>{tag}</li>')


def _list(side: str, xi: list[str], injuries: list[tuple[str, str]],
          ques: str | None = None) -> str:
    items = [_player_li(n, "GK" if i == 0 else "DC",
                        "QUES" if n == ques else None)
             for i, n in enumerate(xi)]
    body = "".join(items)
    if injuries:
        body += '<li class="lineup__title is-middle">Injuries</li>'
        body += "".join(_player_li(n, "DC", tag) for n, tag in injuries)
    return f'<ul class="lineup__list is-{side}">{body}</ul>'


def _box(home: str, visit: str, home_xi, visit_xi, home_inj=(), visit_inj=(),
         ques=None) -> str:
    return (
        '<div class="lineup__box">'
        f'<div class="lineup__mteam is-home">{home}</div>'
        f'<div class="lineup__mteam is-visit">{visit}</div>'
        '<li class="lineup__status is-expected">Predicted Lineup</li>'
        + _list("home", home_xi, list(home_inj), ques)
        + _list("visit", visit_xi, list(visit_inj))
        + '</div>')


def _rotowire_html(ques: str | None = None) -> str:
    """One Premier League fixture and one that is not."""
    return (
        _box("Nottingham Forest", "Brighton & Hove Albion", _FOREST, _XI,
             home_inj=[("Taiwo Awoniyi", "OUT")],
             visit_inj=[("Solly March", "OUT"), ("Adam Webster", "QUES"),
                        ("James Milner", "SUS")],
             ques=ques)
        + _box("Ipswich Town", "Coventry City",
               [f"Ipswich Player {i}" for i in range(11)],
               [f"Coventry Player {i}" for i in range(11)]))


# --- players / teams ------------------------------------------------------

def _players() -> pd.DataFrame:
    names = _XI + _FOREST + ["Solly March", "Adam Webster", "James Milner",
                             "Taiwo Awoniyi"]
    codes = list(range(100, 100 + len(names)))
    teams = [36] * len(_XI) + [17] * len(_FOREST) + [36, 36, 36, 17]
    return pd.DataFrame({
        "code": codes, "name": names, "team_code": teams,
        "starts": [20] * len(names), "status": ["a"] * len(names),
        "chance_of_playing": [None] * len(names),
    })


def _teams() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [36, 17],
        "name": ["Brighton & Hove Albion", "Nottingham Forest"],
        "short_name": ["BHA", "NFO"]})


def _code_of(name: str) -> int:
    p = _players()
    return int(p.loc[p["name"] == name, "code"].iloc[0])


def _client(calls: list[str], body: str):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200, text=body if "rotowire" in str(request.url) else "")
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- the parse ------------------------------------------------------------

def test_a_predicted_xi_parses_to_eleven_start_rows_a_side():
    rows = parse_rotowire(_rotowire_html())
    forest = rows[(rows["club"] == "Nottingham Forest")
                  & (rows["slot"] == "start")]
    brighton = rows[(rows["club"] == "Brighton & Hove Albion")
                    & (rows["slot"] == "start")]
    assert len(forest) == 11
    assert len(brighton) == 11


def test_names_come_from_the_title_attribute_not_the_anchor_body():
    """The anchor prints an abbreviated name; the title is the full one, and
    the matcher needs the full one."""
    rows = parse_rotowire(_rotowire_html())
    assert "Jan Paul van Hecke" in set(rows["name"])
    assert "Hecke" not in set(rows["name"])


def test_the_club_is_the_mteam_text_and_the_sides_are_not_swapped():
    rows = parse_rotowire(_rotowire_html())
    assert set(rows["club"]) >= {"Nottingham Forest",
                                 "Brighton & Hove Albion"}
    assert "Chris Wood" in set(
        rows.loc[rows["club"] == "Nottingham Forest", "name"])
    assert "Kaoru Mitoma" in set(
        rows.loc[rows["club"] == "Brighton & Hove Albion", "name"])


def test_the_injuries_title_splits_the_list():
    """A parser that read the whole <ul> as an XI would put an injured player
    in the team."""
    rows = parse_rotowire(_rotowire_html()).set_index("name")
    assert rows.loc["Solly March", "slot"] == "out"
    assert rows.loc["Chris Wood", "slot"] == "start"
    assert rows.loc["Taiwo Awoniyi", "slot"] == "out"


def test_out_and_sus_are_out_and_ques_is_a_doubt():
    rows = parse_rotowire(_rotowire_html()).set_index("name")
    assert rows.loc["Solly March", "slot"] == "out"
    assert rows.loc["James Milner", "slot"] == "out"
    assert rows.loc["Adam Webster", "slot"] == "doubt"


def test_an_unknown_availability_tag_is_dropped_not_guessed():
    markup = _box("Nottingham Forest", "Brighton & Hove Albion",
                  _FOREST, _XI, home_inj=[("Taiwo Awoniyi", "PERSONAL")])
    assert "Taiwo Awoniyi" not in set(parse_rotowire(markup)["name"])


def test_code_is_all_na_and_the_frame_is_parse_cols_shaped():
    """RotoWire carries no FPL codes, so the frame is schema-identical to
    parse_lineups' and the matcher does all the work."""
    rows = parse_rotowire(_rotowire_html())
    assert list(rows.columns) == PARSE_COLS
    assert str(rows["code"].dtype) == "Int64"
    assert rows["code"].isna().all()


def test_a_redesign_yields_zero_rows_rather_than_an_exception():
    for markup in ('<h2>Arsenal</h2><ul class="row-1"><li></li></ul>',
                   "", None, "<html><body><p>no lineups today</p></body>"):
        assert parse_rotowire(markup).empty


# --- through the fetch ----------------------------------------------------

def test_the_registry_is_complete_and_rotowire_is_not_absence_capable():
    """A provider nobody can name is a provider nobody can kill (plan A6);
    and plan A7's scope cut, pinned where it is decided."""
    assert set(PROVIDERS) == set(DEFAULT_LINEUP_PROVIDERS)
    assert PROVIDERS["rotowire"].absence_capable is False
    assert "rotowire" in PROVIDERS["rotowire"].url


def test_a_non_premier_league_fixture_contributes_nothing(tmp_path):
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client([], _rotowire_html()),
                        providers=["rotowire"])
    assert not out.empty
    assert len(out) == 22 + 4          # two XIs, four named absences


def test_a_player_in_both_halves_resolves_pessimistically(tmp_path):
    """He is in the XI carrying QUES and again under Injuries. The module's
    existing dedupe must leave him at 0.25, not 1.0."""
    markup = _box("Nottingham Forest", "Brighton & Hove Albion", _FOREST, _XI,
                  visit_inj=[("Kaoru Mitoma", "QUES")], ques="Kaoru Mitoma")
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client([], markup),
                        providers=["rotowire"]).set_index("code")
    assert out.loc[_code_of("Kaoru Mitoma"), "p_start_hint"] == 0.25


def test_coverage_below_the_floor_discards_the_batch_whole(tmp_path):
    """The only guard this provider has, asserted for this provider."""
    strangers = pd.DataFrame({
        "code": [900, 901], "name": ["Nobody One", "Nobody Two"],
        "team_code": [36, 17], "starts": [20, 20], "status": ["a", "a"],
        "chance_of_playing": [None, None]})
    out = fetch_lineups(strangers, _teams(), cache_dir=tmp_path,
                        client=_client([], _rotowire_html()),
                        providers=["rotowire"], min_coverage=0.5)
    assert out.empty


def test_notable_absences_is_never_called_for_rotowire(tmp_path,
                                                       monkeypatch):
    """Plan A7. A name-matched eleven is not a resolved eleven, and one wrong
    match would damp the starter it displaced."""
    import gaffer.data.news.lineups as mod

    calls: list[int] = []
    monkeypatch.setattr(mod, "notable_absences",
                        lambda *a, **k: calls.append(1) or pd.DataFrame(
                            columns=["code", "absence_damp"]))
    out = fetch_lineups(_players(), _teams(), cache_dir=tmp_path,
                        client=_client([], _rotowire_html()),
                        providers=["rotowire"], absence=True)
    assert calls == []
    assert list(out.columns) == LINEUP_COLS
