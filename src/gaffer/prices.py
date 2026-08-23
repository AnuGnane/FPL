from __future__ import annotations

import pandas as pd

ALERT_COLUMNS = ["code", "name", "price_change_percent", "direction",
                 "calibrating"]


def price_alerts(players: pd.DataFrame, watch_codes: list[int],
                 threshold: float = 90.0) -> pd.DataFrame:
    """Imminent price changes among watched players (owned + planned moves),
    from FPL's official predictor fields. price_change_percent hits +/-100 at
    the nightly 00:00 UK change; `threshold` flags anything close.
    Calibrating players are included but labeled (early-season caveat)."""
    if not watch_codes or players.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    df = players[players["code"].isin(watch_codes)].copy()
    pct = pd.to_numeric(df["price_change_percent"], errors="coerce")
    # NaN means no predictor data (locked / not yet published): never alert.
    df = df[pct.notna() & (pct.abs() >= threshold)]
    if df.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)

    df["direction"] = (df["price_change_percent"] > 0).map(
        {True: "rise", False: "drop"})
    df["calibrating"] = df["price_change_calibrating"].fillna(False)
    return df[ALERT_COLUMNS].sort_values("price_change_percent",
                                         key=abs, ascending=False)
