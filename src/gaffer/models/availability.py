"""Live availability as a prediction-time override.

The seam between a model trained on what happened and a world that knows what
is about to. Nothing in here is ever a trained feature: flags, injury news and
predicted line-ups have no historical record, and training on them would be
train/serve skew of the worst kind. They are applied *after* the model, to its
output, which is also what lets the whole layer be switched off without
retraining anything.
"""

from __future__ import annotations

import pandas as pd

from gaffer.assets import load_injury_curves

RECOVERY = 0.7
"""Per-gameweek decay of an availability flag over the planning horizon.

A status flag describes *this* gameweek: a one-match ban or a knock is spent
by the next one, so applying the raw factor across the whole horizon would
zero a player for six gameweeks and make the MILP sell fully-fit assets. The
damping is therefore relaxed geometrically — ``1 - (1 - f) * 0.7**h`` at h
gameweeks past the first — full strength where it matters most (the imminent
gameweek, the least decayed term in the objective) and fading toward available
later on.

Since v5 this is the *terminal* fallback rather than the only rule: where the
news layer knows the injury type, :func:`return_prob` supplies a real recovery
curve and this constant is what answers when it does not — an unflagged knock,
a ban running out, or a clone with no calibrated asset.
"""


def return_prob(curves: dict | None, injury_type, h: int) -> float | None:
    """``P(returned by h gameweeks | injury_type)`` from the asset.

    The three-deep chain of spec §5, one step per line: the typed curve, then
    the pooled curve, then ``None`` — which is the caller's instruction to use
    :data:`RECOVERY`. Past the end of a curve the last value stands, because a
    curve that has reached 1.0 stays there and one that has not is saying the
    injury outlasts the horizon.
    """
    if not curves:
        return None
    typed = (curves.get("curves") or {}).get(str(injury_type or ""))
    curve = typed if typed else curves.get("pooled")
    if not curve:
        return None
    return float(curve[min(int(h), len(curve) - 1)])


def apply_availability(pred: pd.DataFrame, avail: pd.DataFrame,
                       curves: dict | None = None) -> pd.DataFrame:
    """avail: the normalized availability frame, or the bare bootstrap slice.

    ``status`` i/s/u/n (injured/suspended/unavailable/not in squad) -> factor
    from ``chance_of_playing`` (None means 0). 'd' (doubtful) ->
    ``chance_of_playing``. 'a' -> 1.0.

    If ``pred`` carries a ``gw`` column the factor is applied in full to the
    horizon's first gameweek and relaxes after it: on the injury-type curve
    when the news layer supplied one, otherwise geometrically (see
    :data:`RECOVERY`). Without a ``gw`` column it is applied uniformly.

    ``p_start_hint``, when the frame carries one, gates the **first gameweek
    only**: ``p_play <- min(p_play, hint)``, with ``p60`` and ``e_min`` scaled
    by the same ratio so the three stay coherent. A predicted line-up is
    evidence *against* a player it omits and no evidence at all for one it
    names, so a 1.0 hint can never raise the model's own number — and a
    prediction about Saturday says nothing about the Wednesday after.

    ``curves`` defaults to the shipped asset, which may be absent: with no
    asset the horizon decay is exactly the pre-v5 geometric, and the whole
    function is byte-identical to v4's.
    """
    curves = curves if curves is not None else load_injury_curves()
    news_cols = [c for c in ("injury_type", "p_start_hint")
                 if c in avail.columns]
    out = pred.merge(
        avail[["code", "status", "chance_of_playing"] + news_cols],
        on="code", how="left")
    cop = out["chance_of_playing"].astype("float") / 100.0
    factor = pd.Series(1.0, index=out.index)
    flagged = out["status"].isin(["i", "s", "u", "n", "d"])
    factor[flagged] = cop[flagged].fillna(0.0)
    if "gw" in out.columns and len(out):
        horizon_start = out["gw"].min()
        h = (out["gw"] - horizon_start).astype(float)
        factor = _relax(factor, h, out.get("injury_type"), curves)
    for col in ["p_play", "p60"]:
        out[col] = out[col] * factor
    out["e_min"] = out["e_min"] * factor
    if "p_start_hint" in out.columns:
        out = _gate_first_gw(out)
    return out.drop(columns=["status", "chance_of_playing"] + news_cols)


def _relax(factor: pd.Series, h: pd.Series, injury_type,
           curves: dict | None) -> pd.Series:
    """``1 - (1 - f) * (1 - P(returned by h))``, per row.

    Row-wise because the curve depends on the row's own injury type, and a
    frame in a double gameweek carries several rows per player. Rows the chain
    cannot type fall back to ``(1 - f) * RECOVERY ** h``, which is the whole
    of the pre-v5 rule.
    """
    types = (injury_type if injury_type is not None
             else pd.Series(None, index=factor.index))
    relaxed = []
    for f, steps, itype in zip(factor, h, types):
        # A missing type is not an unseen one: an unflagged knock or an ending
        # ban has no injury behind it to pool with, so it never reaches the
        # curve chain at all.
        p_back = (None if itype is None or pd.isna(itype)
                  else return_prob(curves, itype, int(steps)))
        if p_back is None:
            relaxed.append(1 - (1 - f) * RECOVERY ** steps)
        else:
            relaxed.append(1 - (1 - f) * (1 - p_back))
    return pd.Series(relaxed, index=factor.index, dtype="float64")


def _gate_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply ``p_start_hint`` as a ceiling on the horizon's first gameweek.

    The ratio is applied to all three outputs rather than clipping ``p_play``
    alone: an untouched ``p60`` beside a halved ``p_play`` is the incoherence
    the three-mode model was built to remove, and ``e_min`` feeds the
    scenario sweep's nailedness score.

    At most **one row per player** is gated, even in a double gameweek: a
    predicted line-up is one team sheet for one match, and applying it to both
    of a double's fixtures claims the site predicted a tie it never wrote
    about. The row taken is the first in frame order, which is the earliest
    fixture — ``predict_components`` builds the frame in fixture order — and
    that is the match the published XI is about.
    """
    hint = pd.to_numeric(out["p_start_hint"], errors="coerce")
    first = (out["gw"] == out["gw"].min()) if "gw" in out.columns \
        else pd.Series(True, index=out.index)
    if "code" in out.columns:
        extra = out.loc[first, "code"].duplicated()
        first = first & ~out.index.isin(extra.index[extra])
    bites = first & hint.notna() & (hint < out["p_play"])
    if not bites.any():
        return out
    ratio = (hint[bites] / out.loc[bites, "p_play"]).where(
        out.loc[bites, "p_play"] > 0, 0.0)
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * ratio
    return out
