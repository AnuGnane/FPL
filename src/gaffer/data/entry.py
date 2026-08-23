"""The manager's own squad: picks, exact sell prices, free transfers."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from gaffer.api.client import FPLClient

FT_CAP = 5
FT_START_GW = 2
FREE_TRANSFER_CHIPS = ("wildcard", "freehit")


def sell_price(purchase: int, now: int) -> int:
    """FPL sell price in 0.1m units: half of profit (rounded down) is kept."""
    if now <= purchase:
        return now
    return purchase + (now - purchase) // 2


def compute_free_transfers(
    transfers_by_gw: dict[int, int],
    chips_by_gw: dict[int, str],
    current_gw: int,
    start_gw: int = FT_START_GW,
) -> int:
    """FTs available at ``current_gw``'s deadline. 1/GW, bank to 5, floor 0.

    Wildcard/Free Hit gameweeks don't consume FTs (and Free Hit transfers
    revert), so transfers made in those weeks are ignored.
    """
    ft = 1
    for gw in range(start_gw, current_gw):
        chip = chips_by_gw.get(gw, "")
        used = 0 if chip in FREE_TRANSFER_CHIPS else transfers_by_gw.get(gw, 0)
        ft = max(0, ft - used)
        ft = min(FT_CAP, ft + 1)
    return ft


@dataclass
class MyTeam:
    entry_id: int
    bank: int                      # 0.1m units
    free_transfers: int
    current_gw: int                # the GW being planned (next deadline)
    picks: pd.DataFrame            # element, code, purchase, now, sell
    chips_used: list[str] = field(default_factory=list)
    chips_by_gw: dict[int, str] = field(default_factory=dict)


def fetch_my_team(
    client: FPLClient,
    entry_id: int,
    next_gw: int,
    players: pd.DataFrame,
) -> MyTeam:
    """Assemble the current squad state ahead of ``next_gw``'s deadline."""
    last_gw = next_gw - 1
    picks_raw = client.get_entry_picks(entry_id, last_gw)
    transfers = client.get_entry_transfers(entry_id)
    history = client.get_entry_history(entry_id)

    # Purchase price per owned element: the most recent transfer-in cost if we
    # ever bought them, otherwise the season-start price (GW1 squad).
    purchase: dict[int, int] = {}
    for t in sorted(transfers, key=lambda t: t["time"]):
        purchase[t["element_in"]] = t["element_in_cost"]
    price_now = dict(zip(players["element"], players["now_cost"]))
    start_price = dict(
        zip(players["element"], players["now_cost"] - players["cost_change_start"])
    )

    rows = []
    for p in picks_raw["picks"]:
        el = p["element"]
        buy = int(purchase.get(el, start_price.get(el, price_now.get(el, 0))))
        now = int(price_now.get(el, buy))
        rows.append(
            {
                "element": el,
                "purchase": buy,
                "now": now,
                "sell": sell_price(buy, now),
            }
        )
    picks = pd.DataFrame(rows).merge(
        players[["element", "code", "name", "position", "team_code"]],
        on="element",
        how="left",
    )

    transfers_by_gw: dict[int, int] = {}
    for t in transfers:
        transfers_by_gw[t["event"]] = transfers_by_gw.get(t["event"], 0) + 1
    chips_by_gw = {c["event"]: c["name"] for c in history.get("chips", [])}
    ft = compute_free_transfers(transfers_by_gw, chips_by_gw, next_gw)

    return MyTeam(
        entry_id=entry_id,
        bank=picks_raw["entry_history"]["bank"],
        free_transfers=ft,
        current_gw=next_gw,
        picks=picks,
        chips_used=list(chips_by_gw.values()),
        chips_by_gw=chips_by_gw,
    )
