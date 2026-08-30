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
                       curves: dict | None = None,
                       start_floor: float | None = None) -> pd.DataFrame:
    """avail: the normalized availability frame, or the bare bootstrap slice.

    ``status`` i/s/u/n (injured/suspended/unavailable/not in squad) -> factor
    from ``chance_of_playing`` (None means 0). 'd' (doubtful) ->
    ``chance_of_playing``. 'a' -> 1.0.

    If ``pred`` carries a ``gw`` column the factor is applied in full to the
    horizon's first gameweek and relaxes after it: on the injury-type curve
    when the news layer supplied one, otherwise geometrically (see
    :data:`RECOVERY`). An ``expected_return_gw`` floors every gameweek before
    it at zero — he is out until the date — and changes nothing from the
    return gameweek on. Without a ``gw`` column the factor is applied
    uniformly and neither rule runs.

    ``p_start_hint``, when the frame carries one, gates the **first gameweek
    only**: ``p_play <- min(p_play, hint)``, with ``p60`` and ``e_min`` scaled
    by the same ratio so the three stay coherent. A predicted line-up is
    evidence *against* a player it omits and no evidence at all for one it
    names, so a 1.0 hint can never raise the model's own number — and a
    prediction about Saturday says nothing about the Wednesday after.

    ``curves`` defaults to the shipped asset, which may be absent: with no
    asset the horizon decay is exactly the pre-v5 geometric, and the whole
    function is byte-identical to v4's.

    ``absence_damp``, when the frame carries one, multiplies the horizon's
    first gameweek: a regular the predicted XI left out without naming him
    (v8a F4). It composes with the hint ceiling and obeys the same
    one-row-per-player rule.

    ``start_floor`` defaults to the ``[news] lineup_start_floor`` config key,
    read here because ``advise`` is protected and cannot forward it. At its
    shipped ``0.0`` the pass is a no-op and this function is arithmetically
    identical to v7's.
    """
    curves = curves if curves is not None else load_injury_curves()
    news_cols = [c for c in ("injury_type", "expected_return_gw",
                             "p_start_hint", "absence_damp", "llm_verdict",
                             "llm_confidence")
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
        factor = _relax(factor, h, out.get("injury_type"), curves,
                        gw=out["gw"], return_gw=out.get("expected_return_gw"))
    for col in ["p_play", "p60"]:
        out[col] = out[col] * factor
    out["e_min"] = out["e_min"] * factor
    if "p_start_hint" in out.columns:
        out = _gate_first_gw(out)
        if start_floor is None:
            from gaffer.config import serving_config
            start_floor = serving_config().news_lineup_start_floor
        out = _floor_first_gw(out, float(start_floor))
    if "absence_damp" in out.columns:
        out = _damp_first_gw(out)
    return out.drop(columns=["status", "chance_of_playing"] + news_cols)


def _relax(factor: pd.Series, h: pd.Series, injury_type,
           curves: dict | None, gw: pd.Series | None = None,
           return_gw=None) -> pd.Series:
    """``1 - (1 - f) * (1 - P(returned by h))``, per row.

    Row-wise because the curve depends on the row's own injury type, and a
    frame in a double gameweek carries several rows per player. Rows the chain
    cannot type fall back to ``(1 - f) * RECOVERY ** h``, which is the whole
    of the pre-v5 rule.

    ``expected_return_gw``, where the news layer supplied one, is a hard zero
    floor and nothing else: every gameweek strictly before it is a 0.0, and
    from the return gameweek onward the curve chain answers exactly as it
    would with no date at all. Deliberately *not* re-anchored — ``h`` stays
    measured from the start of the horizon — because the date already says
    everything it knows about when he is back, and re-basing the curve on it
    would count the same claim twice. Both columns are absolute gameweeks.
    """
    types = (injury_type if injury_type is not None
             else pd.Series(None, index=factor.index))
    weeks = gw if gw is not None else pd.Series(None, index=factor.index)
    backs = (return_gw if return_gw is not None
             else pd.Series(None, index=factor.index))
    relaxed = []
    for f, steps, itype, week, back in zip(factor, h, types, weeks, backs):
        if (week is not None and back is not None and not pd.isna(week)
                and not pd.isna(back) and int(week) < int(back)):
            relaxed.append(0.0)
            continue
        if steps <= 0:
            # The horizon's first gameweek is *this* one, and this one's
            # number is the official flag — no curve, however malformed, gets
            # to relax it. ``write_curves`` already refuses a curve that does
            # not start at zero; this is the second lock on the same door,
            # because an asset can reach a clone without passing that gate.
            relaxed.append(f)
            continue
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


def _first_rows(out: pd.DataFrame) -> pd.Series:
    """The horizon's first row per player — a boolean mask.

    At most **one row per player**, even in a double gameweek: a predicted
    line-up is one team sheet for one match, and applying it to both of a
    double's fixtures claims the site predicted a tie it never wrote about.
    The row taken is the first in frame order, which is the earliest fixture
    (``predict_components`` builds the frame in fixture order), and that is
    the match the published XI is about.

    Factored out of :func:`_gate_first_gw` because v8a's damp and floor have
    to bite on exactly the same rows the ceiling does — three copies of this
    rule would be three chances for them to drift apart.
    """
    first = ((out["gw"] == out["gw"].min()) if "gw" in out.columns
             else pd.Series(True, index=out.index))
    if "code" in out.columns:
        extra = out.loc[first, "code"].duplicated()
        first = first & ~out.index.isin(extra.index[extra])
    return first


def _gate_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply ``p_start_hint`` as a ceiling on the horizon's first gameweek.

    The ratio is applied to all three outputs rather than clipping ``p_play``
    alone: an untouched ``p60`` beside a halved ``p_play`` is the incoherence
    the three-mode model was built to remove, and ``e_min`` feeds the
    scenario sweep's nailedness score.
    """
    hint = pd.to_numeric(out["p_start_hint"], errors="coerce")
    first = _first_rows(out)
    bites = first & hint.notna() & (hint < out["p_play"])
    if not bites.any():
        return out
    ratio = (hint[bites] / out.loc[bites, "p_play"]).where(
        out.loc[bites, "p_play"] > 0, 0.0)
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * ratio
    return out


def _damp_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply ``absence_damp`` to the horizon's first gameweek (v8a F4).

    A regular the predicted XI silently left out. Weaker evidence than a
    printed "Out", so it multiplies rather than clipping: the model's own view
    survives it, scaled. Same one-row-per-player rule and the same
    three-outputs-together discipline as the ceiling above, and it composes
    with the ceiling by construction — a player who is both named as a doubt
    and a notable absentee cannot exist, because the absence rule skips every
    code the page named.
    """
    damp = pd.to_numeric(out["absence_damp"], errors="coerce")
    bites = _first_rows(out) & damp.notna() & (damp < 1.0)
    if not bites.any():
        return out
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * damp[bites]
    return out


def _floor_first_gw(out: pd.DataFrame, floor: float) -> pd.DataFrame:
    """Raise a *predicted starter* to ``floor`` on the first gameweek.

    Shipped as a capability at ``0.0`` — off — and deliberately so. The hint
    has only ever been a ceiling, on the argument that a predicted omission is
    strong evidence and a predicted start is none; a floor reverses that for
    the one case where the page is unambiguous, and reversing it without
    evidence is how a fringe player becomes a captain. It is enabled only if
    the shadow log supports a value (spec §4).

    ``p_play`` of exactly zero is left alone: there is no ratio to carry
    ``p60`` and ``e_min`` up with, and a model that has ruled a player out
    entirely is not being contradicted by a website's guess.
    """
    if floor <= 0.0:
        return out
    hint = pd.to_numeric(out["p_start_hint"], errors="coerce")
    bites = (_first_rows(out) & (hint >= 1.0) & (out["p_play"] < floor)
             & (out["p_play"] > 0))
    if not bites.any():
        return out
    ratio = floor / out.loc[bites, "p_play"]
    for col in ["p_play", "p60", "e_min"]:
        out.loc[bites, col] = out.loc[bites, col] * ratio
    return out
