import pandas as pd

from gaffer.data.entry import compute_free_transfers, fetch_my_team, sell_price


def test_sell_price_half_profit_rounded_down():
    assert sell_price(purchase=55, now=61) == 58   # +6 profit -> +3
    assert sell_price(purchase=55, now=56) == 55   # +1 profit -> +0
    assert sell_price(purchase=55, now=54) == 54   # loss -> current price
    assert sell_price(purchase=55, now=55) == 55


def test_free_transfers_bank_and_cap():
    # transfers_by_gw: {gw: n_transfers}; chips: {gw: chip_name}
    # GW2 start: 1 FT. No transfers GW2-5 -> banks to 5 by GW6, capped.
    assert compute_free_transfers({}, {}, current_gw=7) == 5
    # used 1 in GW2 -> 1 available GW3
    assert compute_free_transfers({2: 1}, {}, current_gw=3) == 1
    # used 2 in GW2 (one was a hit) -> still 1 in GW3 (can't go below 0 + 1)
    assert compute_free_transfers({2: 2}, {}, current_gw=3) == 1
    # A wildcard/free hit week neither consumes nor accrues: the count is
    # carried over unchanged. 1 FT into the chip week -> 1 FT after it.
    assert compute_free_transfers({2: 8}, {2: "wildcard"}, current_gw=3) == 1
    assert compute_free_transfers({2: 5}, {2: "freehit"}, current_gw=3) == 1
    # Two banked before the chip are still two after it: nothing GW2 banks a
    # second FT for GW3, the GW3 wildcard leaves it alone.
    assert compute_free_transfers({3: 8}, {3: "wildcard"}, current_gw=4) == 2
    # ... and the ordinary +1 accrual resumes the week after the chip.
    assert compute_free_transfers({2: 8}, {2: "wildcard"}, current_gw=4) == 2


class _FakeClient:
    """Stands in for FPLClient; no network."""

    def get_entry_picks(self, entry_id, gw):
        assert gw == 4
        return {
            "picks": [{"element": 1}, {"element": 2}],
            "entry_history": {"bank": 13},
        }

    def get_entry_transfers(self, entry_id):
        return [
            {
                "event": 3,
                "time": "2025-09-01T10:00:00Z",
                "element_in": 2,
                "element_in_cost": 70,
                "element_out": 9,
                "element_out_cost": 65,
            }
        ]

    def get_entry_history(self, entry_id):
        return {"chips": [{"event": 3, "name": "wildcard"}]}


def test_fetch_my_team_builds_state():
    players = pd.DataFrame(
        [
            {"element": 1, "code": 101, "name": "Alpha", "position": "MID",
             "team_code": 3, "now_cost": 61, "cost_change_start": 6},
            {"element": 2, "code": 102, "name": "Beta", "position": "FWD",
             "team_code": 7, "now_cost": 76, "cost_change_start": 11},
        ]
    )
    team = fetch_my_team(_FakeClient(), entry_id=99, next_gw=5, players=players)

    picks = team.picks.set_index("element")
    # Transferred in at 70, now 76 -> +6 profit -> keep half -> 73.
    assert picks.loc[2, "purchase"] == 70
    assert picks.loc[2, "sell"] == 73
    # Never transferred -> purchase is season-start price 61 - 6 = 55,
    # now 61 -> +6 profit -> 58.
    assert picks.loc[1, "purchase"] == 55
    assert picks.loc[1, "sell"] == 58
    assert picks.loc[1, "name"] == "Alpha"

    assert team.bank == 13
    assert team.current_gw == 5
    assert team.entry_id == 99
    # GW2: no transfers -> 2; GW3: wildcard, carries 2 over unchanged;
    # GW4: no transfers -> 3.
    assert team.free_transfers == 3
    assert team.chips_by_gw == {3: "wildcard"}
    assert team.chips_used == ["wildcard"]


def test_fetch_my_team_refuses_gw1():
    """Before GW1 there is no completed gameweek to read a squad from; the
    picks endpoint would 404 on GW0."""
    import pytest

    from gaffer.errors import GafferError

    with pytest.raises(GafferError, match="GW1"):
        fetch_my_team(_FakeClient(), entry_id=99, next_gw=1,
                      players=pd.DataFrame())


class _FreeHitClient:
    """GW3 free hit: element 2 was bought under the chip at 90 and reverted.
    The real purchase price is the GW2 transfer at 70."""

    def get_entry_picks(self, entry_id, gw):
        return {"picks": [{"element": 2}], "entry_history": {"bank": 0}}

    def get_entry_transfers(self, entry_id):
        return [
            {"event": 2, "time": "2025-08-25T10:00:00Z", "element_in": 2,
             "element_in_cost": 70, "element_out": 9, "element_out_cost": 65},
            {"event": 3, "time": "2025-09-01T10:00:00Z", "element_in": 2,
             "element_in_cost": 90, "element_out": 8, "element_out_cost": 80},
        ]

    def get_entry_history(self, entry_id):
        return {"chips": [{"event": 3, "name": "freehit"}]}


def test_free_hit_transfers_do_not_overwrite_purchase_price():
    players = pd.DataFrame(
        [{"element": 2, "code": 102, "name": "Beta", "position": "FWD",
          "team_code": 7, "now_cost": 76, "cost_change_start": 11}]
    )
    team = fetch_my_team(_FreeHitClient(), entry_id=99, next_gw=5,
                         players=players)
    picks = team.picks.set_index("element")
    assert picks.loc[2, "purchase"] == 70    # not the reverted FH price of 90
    assert picks.loc[2, "sell"] == 73        # 70 + (76-70)//2
