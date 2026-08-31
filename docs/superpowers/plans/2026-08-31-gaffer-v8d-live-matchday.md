# Gaffer v8d Live Matchday Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** turn the Live hub into the Saturday-afternoon screen. Three answers it cannot give today — who comes on if my player stays on zero, where my score is *going* rather than where it is, and what I need to add to take or hold each league place.

**Architecture:** no new stores, no new job kinds, no new config keys. Everything is pure arithmetic appended to `src/gaffer/live_gw.py` and composed by `src/gaffer/web/routers/live.py`, which is the only place that touches the API, the parquet artifacts and the process's memory. `live_gw.entry_live_points` — the no-autosub contract three callers pin — is not touched; the projection is a *separate* function that reuses it by handing it a synthetic pick list. `backtest._formation_legal` is imported, not copied, so the projected XI and the replay's scored XI can never drift apart. The race trajectory lives in a module-level dict in the router, capped and keyed by gameweek: live state is ephemeral by definition and nothing here writes a byte to disk.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, pytest; React 19 + TypeScript + vitest + recharts.

**Prerequisite:** work on branch `feat/gaffer-v8d`. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v8d-live-matchday-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 8 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every pre-v8d `tests/test_*_degradation.py`, `scripts/s2_replay.py`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`.

**Import-only (spec §2):** `src/gaffer/journal.py` and `src/gaffer/backtest.py`. `backtest._formation_legal` is *imported* by `live_gw.py` and never moved, renamed or copied — it is module-level and the leading underscore does not stop an import. If a task appears to need an edit inside a protected or import-only file, the plan is wrong: stop and report rather than editing.

**The one deliberate contract change (spec §2):** `live_gw.league_live_table`'s `projected` column becomes auto-sub aware, and the `delta` arrows with it. It changes *additively* — the function reads a new optional `projected_live` key off each row and falls back to `live` when the caller does not supply one — so `run_live` (the CLI) and every existing `league_live_table` test keep their exact behaviour, and only the web router, which does supply it, gets the improvement. Task 3 states this in the docstring. It is never a quiet change.

**`entry_live_points` is byte-identical.** Its body is not edited in any task. Task 6 pins that with a copy of its contract test.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/` or `config.toml`. v8d commits no data asset.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 8 is the checklist, unfilled.

**Suite baselines:** 2117 python tests, 344 frontend tests + 1 skipped. Every task's final run must leave the pre-existing suites green.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

The spec is deliberately lean. Six things it does not pin, decided here once so no task has to decide them twice:

**A1 — `projected_subs`' signature.** The spec sketches
`projected_subs(picks, points_of, minutes_of, finished_by_team, positions)`.
Two changes, both to keep the function pure and honest:

* `points_of` is **dropped**. A sub triggers on minutes, never on points; a starter with points and zero minutes cannot exist, and taking the argument would imply it could.
* `finished_by_team` becomes `finished_of`, keyed by **element**, not team. A team-keyed map forces the pure function to own an element→team lookup it cannot have without the snapshot. The router already reads `team_id` off the snapshot for the status column, so it resolves the map there and hands down `element -> "every fixture this player's team has in the gameweek is over"`.

Final: `projected_subs(picks, minutes_of, finished_of, positions)`.

**A2 — when is a *bench* player a valid sub?** `backtest.score_gw` requires `played(sub)`, because at full time a bench player who did not play cannot come on. Mid-afternoon that rule is too strict: a bench player whose own match kicks off on Sunday is exactly the man who *will* come on. So a bench player is eligible when he has **minutes > 0** (he is definitely on) **or** his own team's fixtures are **not finished** (he may still play), and never when he has finished on zero — he blanked too. The two cases are distinguished in the output's `reason` (`"played"` / `"yet to play"`) and the UI shows it, so a chip never claims more certainty than it has.

**A3 — does the race use live points or projected points?** Spec D3 writes `live_points + Σ remaining_ep` while also saying projected auto-subs substitute their EP. Mixing the no-autosub score with autosub-aware EP would be two different squads added together. The race is therefore **projected points + remaining EP** on both sides, which makes it the same quantity the league table's `projected` column now shows, plus what is still to come.

**A4 — is the race cumulative or gameweek-level?** Gameweek-level. The reference line is `advice.expected_pts`, which is a *gameweek* expectation of roughly sixty points; drawing it against a season total near five hundred would put it off the bottom of the chart. So `race` on a table row is `projected_live + remaining_ep` — this gameweek's projected final score — and the season totals stay where they belong, in the `projected` column and in the safety strip.

**A5 — do rivals get remaining EP, or only live points?** (Spec §3 leaves it to the planner.) **They get the full treatment.** The router already fetches every rival's picks to score them, and the component EPs are one parquet read for the whole gameweek, so a rival's projection and remaining EP cost zero extra API calls. Rival elements missing from the snapshot get no projected subs and no EP, which degrades that rival to live points alone without affecting anyone else.

**A6 — the components notice must not touch `notice`.** `notice` is the tier-EO line and three existing tests pin its exact text. The race's degradation gets its own additive field, `race_notice`, which is also better UI: it belongs on the race card, not on the players card.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/live_gw.py` | Modify (append after `entry_live_points`, L129) | F1 `projected_subs` / `projected_multipliers` / `projected_points`; F2 `remaining_fraction` / `remaining_ep_total` / `race_value`; F3 `safety_margins`; `league_live_table`'s one additive line. |
| `tests/test_live_projection.py` | Create | Task 1: the auto-sub walk and the armband. |
| `tests/test_live_race.py` | Create | Task 2: fractions, remaining EP, race value. |
| `tests/test_live_safety.py` | Create | Task 3: the improved `projected` column and the margins. |
| `src/gaffer/web/schemas.py` | Modify (append to the Live block, L276-309) | `LiveSafety`, `LiveRacePoint`; additive fields on `LivePlayer`, `LiveTableRow`, `LiveState`. |
| `src/gaffer/web/routers/live.py` | Modify | `_started_by_team`, `_ep_by_element`, `_project`, the in-memory series, the wiring. |
| `tests/test_web_live.py` | Modify (the inactive-payload assertion, L117-126) | The one deliberate test edit: new default keys in the quiet payload. |
| `tests/test_web_live_v8d.py` | Create | The endpoint's new fields end to end. |
| `frontend/src/types.ts` | Modify (`LivePlayer` L271, `LiveTableRow` L286, `LiveState` L295) | Lockstep with the schemas. |
| `frontend/src/hubs/Live.tsx` | Modify | The race card, the safety strip, the auto-sub chips, the `Race` column. |
| `frontend/src/hubs/Live.test.tsx` | Modify (fixtures + new cases) | Its suite. |
| `tests/test_v8d_degradation.py` | Create | G2 rails. |
| `README.md` | Modify (Live gameweek ~L212; the seven-pages paragraph ~L242) | What the hub now shows and what it will not claim. |

---

## Task 1 — F1: the auto-sub projection

**Files:**
- Modify `src/gaffer/live_gw.py`
- Create `tests/test_live_projection.py`

- [ ] **Write the failing test.** Create `tests/test_live_projection.py`:

```python
"""The auto-sub projection: the substitution FPL *would* make if the rest of
the afternoon went the way it has gone so far.

The real game applies auto-subs once, at full time. ``entry_live_points``
therefore applies none at all, because mid-gameweek a starter on zero minutes
is indistinguishable from one whose match is on Sunday. The projection splits
that ambiguity on the one fact the payload does give: whether the player's own
fixtures are over. A finished blank is a blank forever; an unfinished one is
still anybody's guess and is left alone.
"""

from __future__ import annotations

from gaffer.live_gw import (entry_live_points, projected_multipliers,
                            projected_points, projected_subs)

POS = {1: "GKP", 2: "DEF", 3: "DEF", 4: "DEF", 5: "MID", 6: "MID",
       7: "MID", 8: "MID", 9: "FWD", 10: "FWD", 11: "FWD",
       12: "GKP", 13: "DEF", 14: "MID", 15: "FWD"}


def _picks(captain=9, vice=10, captain_mult=2):
    """A legal 3-5-2 with a four-man bench, in FPL's own pick order."""
    out = []
    for element in range(1, 16):
        mult = 0 if element > 11 else 1
        if element == captain:
            mult = captain_mult
        out.append({"element": element, "position": element,
                    "multiplier": mult,
                    "is_captain": element == captain,
                    "is_vice_captain": element == vice})
    return out


def _minutes(**overrides):
    mins = {e: 90 for e in range(1, 12)}
    mins.update({e: 0 for e in range(12, 16)})
    mins.update(overrides)
    return mins


def _finished(*elements):
    return {e: (e in elements) for e in range(1, 16)}


def test_a_finished_blank_is_replaced_by_the_first_legal_bench_player():
    # Forward 11 finished on nothing; bench 12 is a keeper (two in an eleven
    # is not a formation), 13 a defender (four at the back is), so 13 comes
    # on, and his own match has not kicked off yet.
    subs = projected_subs(_picks(), _minutes(**{11: 0}),
                          _finished(11), POS)
    assert subs == [{"out_element": 11, "in_element": 13,
                     "reason": "yet to play"}]


def test_the_bench_keeper_only_ever_replaces_a_keeper():
    subs = projected_subs(_picks(), _minutes(**{1: 0, 13: 90, 14: 90}),
                          _finished(1), POS)
    assert [s["in_element"] for s in subs] == [12]


def test_an_outfield_blank_never_takes_the_bench_keeper():
    """13, 14 and 15 all blanked and finished; only the keeper is left, and a
    second keeper in the XI is not a formation."""
    subs = projected_subs(_picks(), _minutes(**{11: 0}),
                          _finished(11, 13, 14, 15), POS)
    assert subs == []


def test_a_starter_whose_match_is_still_to_come_is_left_alone():
    """The whole point of the module's caveat: zero minutes before kick-off
    is not a blank."""
    assert projected_subs(_picks(), _minutes(**{11: 0}), _finished(), POS) == []


def test_a_bench_player_who_also_blanked_is_skipped():
    subs = projected_subs(_picks(), _minutes(**{11: 0}),
                          _finished(11, 13, 14), POS)
    assert [s["in_element"] for s in subs] == [15]


def test_a_bench_player_already_on_is_not_brought_on_twice():
    subs = projected_subs(_picks(), _minutes(**{10: 0, 11: 0, 13: 90}),
                          _finished(10, 11), POS)
    assert [s["in_element"] for s in subs] == [13, 14]
    assert [s["reason"] for s in subs] == ["played", "yet to play"]


def test_a_squad_that_is_not_eleven_and_four_projects_nothing():
    """A chip week (Bench Boost puts fifteen on the pitch) or a payload read
    mid-write: refuse rather than invent a formation."""
    picks = [dict(p, multiplier=1) for p in _picks()]
    assert projected_subs(picks, _minutes(), _finished(), POS) == []


# --- the armband ------------------------------------------------------


def test_the_vice_inherits_the_armband_from_a_finished_blank_captain():
    picks = _picks(captain=9, vice=10)
    subs = projected_subs(picks, _minutes(**{9: 0}), _finished(9), POS)
    mult = projected_multipliers(picks, subs, _minutes(**{9: 0}),
                                 _finished(9))
    assert mult[9] == 0          # subbed off the pitch entirely
    assert mult[10] == 2         # vice doubled


def test_the_triple_captain_armband_moves_at_its_own_multiplier():
    picks = _picks(captain=9, vice=10, captain_mult=3)
    subs = projected_subs(picks, _minutes(**{9: 0}), _finished(9), POS)
    mult = projected_multipliers(picks, subs, _minutes(**{9: 0}),
                                 _finished(9))
    assert mult[10] == 3


def test_the_armband_stays_put_while_the_captain_is_still_to_play():
    picks = _picks(captain=9, vice=10)
    mult = projected_multipliers(picks, [], _minutes(**{9: 0}), _finished())
    assert mult[9] == 2 and mult[10] == 1


def test_the_armband_does_not_pass_to_a_vice_left_on_the_bench():
    """FPL doubles the vice only if he is on the pitch at full time."""
    picks = _picks(captain=9, vice=13)
    subs = projected_subs(picks, _minutes(**{9: 0, 13: 0}),
                          _finished(9, 13), POS)
    mult = projected_multipliers(picks, subs, _minutes(**{9: 0, 13: 0}),
                                 _finished(9, 13))
    assert mult[13] == 0


def test_the_incoming_substitute_never_inherits_the_armband():
    """The armband goes to the vice, not to whoever replaced the captain."""
    picks = _picks(captain=11, vice=10)
    subs = projected_subs(picks, _minutes(**{11: 0}), _finished(11), POS)
    mult = projected_multipliers(picks, subs, _minutes(**{11: 0}),
                                 _finished(11))
    assert mult[13] == 1
    assert mult[10] == 2


def test_picks_without_captaincy_flags_fall_back_to_the_multiplier():
    """The web payload carries ``is_captain``; some fixtures and older caches
    carry only the multiplier. Read the armband off whichever is there."""
    picks = [{"element": e, "position": e,
              "multiplier": (2 if e == 9 else 0 if e > 11 else 1)}
             for e in range(1, 16)]
    mult = projected_multipliers(picks, [], _minutes(**{9: 0}), _finished(9))
    assert mult[9] == 1          # armband cannot move: no vice named
    assert 2 not in set(mult.values())


# --- projected points -------------------------------------------------


def test_projected_points_scores_the_substituted_eleven():
    picks = _picks(captain=9, vice=10)
    minutes = _minutes(**{11: 0})
    finished = _finished(11)
    points = {e: 2 for e in range(1, 16)}
    points[9] = 10          # the captain
    points[11] = 0          # the blank
    bonus = {e: 0 for e in range(1, 16)}
    subs = projected_subs(picks, minutes, finished, POS)
    mult = projected_multipliers(picks, subs, minutes, finished)
    # Nine ordinary starters on 2, the doubled captain, and 13 on for 11.
    assert projected_points(points, bonus, mult) == 9 * 2 + 2 * 10 + 2
    # The pinned figure applies no subs at all, so it is short by exactly the
    # substitute's two points.
    assert entry_live_points(picks, points, bonus) == 9 * 2 + 2 * 10


def test_projected_points_matches_live_points_when_nothing_is_projected():
    picks = _picks()
    points = {e: 3 for e in range(1, 16)}
    bonus = {e: 1 for e in range(1, 16)}
    mult = projected_multipliers(picks, [], _minutes(), _finished())
    assert (projected_points(points, bonus, mult)
            == entry_live_points(picks, points, bonus))
```

Run it: `uv run pytest -q tests/test_live_projection.py` — expect `ImportError`.

- [ ] **Implement.** In `src/gaffer/live_gw.py`, append after `entry_live_points` (which ends at L129) and before `league_live_table`:

```python
def _bench_order(picks: list[dict]) -> list[int]:
    """Bench elements in the order FPL would bring them on.

    ``position`` 12-15 is the substitution order the manager set; sorting by
    it rather than trusting the payload's order is free insurance against a
    client that reordered the list.
    """
    bench = [p for p in picks if int(p.get("multiplier", 0)) < 1]
    bench.sort(key=lambda p: int(p.get("position", 0)))
    return [int(p["element"]) for p in bench]


def _starting_xi(picks: list[dict]) -> list[int]:
    return [int(p["element"]) for p in picks
            if int(p.get("multiplier", 0)) >= 1]


def projected_subs(picks: list[dict], minutes_of: dict[int, int],
                   finished_of: dict[int, bool],
                   positions: dict[int, str]) -> list[dict]:
    """The auto-subs FPL would make if the afternoon ended as it stands.

    ``finished_of`` is per *element*: True when every fixture that player's
    team has in this gameweek is over. That is the whole ambiguity the module
    docstring warns about, resolved: a starter on zero minutes whose matches
    are finished has blanked and will be substituted; a starter on zero
    minutes whose match is still to come is simply not on yet, and is left
    exactly where he is.

    The bench is walked in order and the first *legal* swap wins, under
    :func:`gaffer.backtest._formation_legal` — the same rule the replay scores
    with, imported rather than copied so the projected XI and the scored XI
    cannot drift apart. That rule is what keeps the bench keeper for the
    keeper: two GKPs in an eleven is not a formation, and neither is none.

    A bench player is eligible when he has minutes (he is definitely on) or
    when his own matches are unfinished (he may still play); the ``reason`` on
    each returned row says which, because those two are not equally certain
    and the UI should not pretend they are. A bench player who has finished on
    zero blanked too, and is skipped.

    Returns ``[{"out_element", "in_element", "reason"}]``, empty when the
    squad is not the usual eleven-and-four — a Bench Boost week has nobody
    left to bring on, and a half-read payload should not have a formation
    invented for it.
    """
    from gaffer.backtest import _formation_legal

    xi = _starting_xi(picks)
    bench = _bench_order(picks)
    if len(xi) != 11 or not bench:
        return []

    def blanked(element: int) -> bool:
        return (bool(finished_of.get(element, False))
                and int(minutes_of.get(element, 0) or 0) == 0)

    used = set(xi)
    subs: list[dict] = []
    for slot, starter in enumerate(list(xi)):
        if not blanked(starter):
            continue
        for sub in bench:
            if sub in used or blanked(sub):
                continue
            trial = list(xi)
            trial[slot] = sub
            if not _formation_legal([str(positions.get(c, "MID"))
                                     for c in trial]):
                continue
            xi = trial
            used.discard(starter)
            used.add(sub)
            subs.append({
                "out_element": starter, "in_element": sub,
                "reason": ("played" if int(minutes_of.get(sub, 0) or 0) > 0
                           else "yet to play")})
            break
    return subs


def projected_multipliers(picks: list[dict], subs: list[dict],
                          minutes_of: dict[int, int],
                          finished_of: dict[int, bool]) -> dict[int, int]:
    """element -> the multiplier the projected eleven would score it at.

    Two edits to the picked multipliers. The substitutions from
    :func:`projected_subs` take the outgoing player to 0 and bring the
    incoming one on at 1 — never at the outgoing player's multiplier, because
    FPL hands a blanked captain's armband to the *vice*, not to whoever
    replaced him. Then the armband itself moves, if and only if the captain
    has finished on zero minutes and the vice is on the projected pitch: a
    vice left on the bench is not doubled in the real game either.

    The armband's size is read from the picks, so a Triple Captain week moves
    a 3 rather than a 2.
    """
    mult = {int(p["element"]): int(p.get("multiplier", 0)) for p in picks}
    for sub in subs:
        mult[int(sub["out_element"])] = 0
        mult[int(sub["in_element"])] = 1

    armband = max(mult.values(), default=0)
    if armband < 2:
        return mult                      # no captaincy in this payload

    captain = next((int(p["element"]) for p in picks if p.get("is_captain")),
                   None)
    if captain is None:
        captain = next((int(p["element"]) for p in picks
                        if int(p.get("multiplier", 0)) == armband), None)
    vice = next((int(p["element"]) for p in picks
                 if p.get("is_vice_captain")), None)
    if captain is None:
        return mult
    if not (bool(finished_of.get(captain, False))
            and int(minutes_of.get(captain, 0) or 0) == 0):
        return mult

    # The captain blanked: he scores at most as an ordinary starter from here
    # (zero either way), and the armband goes to the vice if he is on.
    mult[captain] = min(mult.get(captain, 0), 1)
    if vice is not None and mult.get(vice, 0) >= 1:
        mult[vice] = armband
    return mult


def projected_points(points_of: dict[int, int], bonus: dict[int, int],
                     multipliers: dict[int, int]) -> int:
    """The projected eleven's live score, scored by ``entry_live_points``.

    The pinned function is handed a synthetic pick list rather than being
    changed: its no-autosub contract is exactly what its three callers want,
    and the projection is a different question asked of the same arithmetic.
    """
    return entry_live_points(
        [{"element": element, "multiplier": mult}
         for element, mult in multipliers.items()], points_of, bonus)
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_live_projection.py tests/test_live_gw.py
```

Expect the new file green and `test_live_gw.py` unchanged and green.

- [ ] **Commit.**

```bash
git add src/gaffer/live_gw.py tests/test_live_projection.py && git commit -m "$(cat <<'EOF'
feat: project mid-gameweek auto-subs and the inherited armband

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — F2: remaining EP and the race arithmetic

**Files:**
- Modify `src/gaffer/live_gw.py`
- Create `tests/test_live_race.py`

- [ ] **Write the failing test.** Create `tests/test_live_race.py`:

```python
"""The live EP race: where the score is going, not where it is.

Every owned player carries a banked expectation for this gameweek — the same
``ep`` the optimizer picked him on. The race spends it down as his match is
played: none of it before kick-off, all of it by full time. Add what is left
to the projected score and you have the number the afternoon is heading for.
"""

from __future__ import annotations

import pytest

from gaffer.live_gw import race_value, remaining_ep_total, remaining_fraction


def test_a_match_yet_to_kick_off_still_owes_everything():
    assert remaining_fraction(0, started=False, finished=False) == 1.0


def test_a_finished_match_owes_nothing_however_many_minutes_were_played():
    assert remaining_fraction(0, started=True, finished=True) == 0.0
    assert remaining_fraction(90, started=True, finished=True) == 0.0


def test_an_in_play_match_owes_the_minutes_not_yet_played():
    assert remaining_fraction(45, started=True, finished=False) == 0.5
    assert remaining_fraction(30, started=True, finished=False) == pytest.approx(
        2 / 3)


def test_stoppage_time_never_owes_a_negative():
    assert remaining_fraction(96, started=True, finished=False) == 0.0


def test_remaining_ep_scales_by_multiplier_and_skips_the_bench():
    mult = {1: 2, 2: 1, 3: 0}
    ep = {1: 5.0, 2: 4.0, 3: 9.0}
    minutes = {1: 0, 2: 45, 3: 0}
    started = {1: False, 2: True, 3: False}
    finished = {1: False, 2: False, 3: False}
    # 2 x 5.0 x 1.0 + 1 x 4.0 x 0.5, and nothing for the benched 9.0
    assert remaining_ep_total(mult, ep, minutes, started, finished) == 12.0


def test_remaining_ep_is_zero_when_every_match_is_over():
    mult = {1: 2, 2: 1}
    finished = {1: True, 2: True}
    assert remaining_ep_total(mult, {1: 5.0, 2: 4.0}, {1: 90, 2: 90},
                              {1: True, 2: True}, finished) == 0.0


def test_a_player_with_no_banked_ep_contributes_nothing_rather_than_failing():
    """Someone bought after the advice ran, or outside the candidate pool."""
    assert remaining_ep_total({1: 1}, {}, {1: 0}, {1: False}, {1: False}) == 0.0


def test_remaining_ep_with_no_components_at_all_is_zero():
    """The degradation the router turns into a notice: the race becomes the
    projected score, which is still the truth, just less of it."""
    assert remaining_ep_total({1: 2, 2: 1}, {}, {}, {}, {}) == 0.0


def test_race_value_adds_the_projected_score_to_what_is_left():
    assert race_value(41, 12.75) == 53.75


def test_race_value_of_a_spent_gameweek_is_the_score_itself():
    assert race_value(66, 0.0) == 66.0
```

Run it: expect `ImportError`.

- [ ] **Implement.** In `src/gaffer/live_gw.py`, append after `projected_points`:

```python
FULL_MATCH_MINUTES = 90


def remaining_fraction(minutes: int, started: bool, finished: bool) -> float:
    """How much of a player's expectation is still to be earned, in [0, 1].

    Before kick-off he owes all of it; at full time none of it; in between,
    the share of ninety minutes not yet played. Known overstatement: a player
    who is in the squad but has not come on reads as owing everything right up
    to the final whistle, because the live payload carries his minutes and not
    the match clock. That is the same optimism the pre-deadline EP already
    had, and it corrects itself the moment his fixture is marked finished.
    """
    if finished:
        return 0.0
    if not started:
        return 1.0
    played = int(minutes or 0)
    return max(0.0, 1.0 - played / FULL_MATCH_MINUTES)


def remaining_ep_total(multipliers: dict[int, int], ep_of: dict[int, float],
                       minutes_of: dict[int, int],
                       started_of: dict[int, bool],
                       finished_of: dict[int, bool]) -> float:
    """Expected points still to come from a projected eleven.

    ``multipliers`` is :func:`projected_multipliers`' output, so a projected
    substitute contributes his own expectation and the man he replaced
    contributes none. Players with no banked EP — bought after the advice ran,
    or never in the candidate pool — contribute nothing rather than raising:
    an incomplete race is worth more on a Saturday than no race at all.
    """
    total = 0.0
    for element, mult in multipliers.items():
        if int(mult) < 1:
            continue
        ep = float(ep_of.get(element, 0.0) or 0.0)
        if not ep:
            continue
        total += int(mult) * ep * remaining_fraction(
            int(minutes_of.get(element, 0) or 0),
            bool(started_of.get(element, False)),
            bool(finished_of.get(element, False)))
    return round(total, 2)


def race_value(projected: int, remaining: float) -> float:
    """Where a gameweek score is heading: what is banked plus what is owed.

    Gameweek-level, not cumulative — the pre-gameweek plan's ``expected_pts``
    is the reference line this is drawn against, and that is a one-week
    number.
    """
    return round(float(projected) + float(remaining), 2)
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_live_race.py tests/test_live_projection.py tests/test_live_gw.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/live_gw.py tests/test_live_race.py && git commit -m "$(cat <<'EOF'
feat: live remaining-EP and the race arithmetic

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — F3: an auto-sub-aware table, and the safety margins

**Files:**
- Modify `src/gaffer/live_gw.py`
- Create `tests/test_live_safety.py`

This task carries the cycle's one deliberate contract change. Read the plan header's note on it before starting.

- [ ] **Write the failing test.** Create `tests/test_live_safety.py`:

```python
"""The league safety strip, and the table it reads.

``league_live_table``'s ``projected`` column has always been
``pre_total + live``, and ``live`` applies no auto-subs. That understated
every entry with a finished blank in it — including, on a bad Saturday, only
mine. v8d lets a caller supply an auto-sub-aware gameweek score as
``projected_live`` and projects from that instead. The change is additive:
a row without the key behaves exactly as it did, which is why the CLI's
``run_live`` and the original table tests are untouched.
"""

from __future__ import annotations

from gaffer.live_gw import league_live_table, safety_margins


def test_projected_still_falls_back_to_live_when_no_projection_is_given():
    """The pinned behaviour, restated where the change is made."""
    rows = [{"entry": 1, "name": "You", "pre_total": 500, "live": 60}]
    assert league_live_table(rows)[0]["projected"] == 560


def test_projected_prefers_the_autosub_aware_score_when_the_caller_has_one():
    rows = [{"entry": 1, "name": "You", "pre_total": 500, "live": 60,
             "projected_live": 66},
            {"entry": 2, "name": "Rival", "pre_total": 505, "live": 60,
             "projected_live": 60}]
    table = league_live_table(rows)
    assert [r["entry"] for r in table] == [1, 2]      # 566 beats 565
    assert table[0]["projected"] == 566
    assert table[0]["delta"] == 1                     # and the arrow follows


def test_extra_row_keys_survive_the_table():
    """``race`` and ``remaining_ep`` ride along to the response model."""
    rows = [{"entry": 1, "name": "You", "pre_total": 1, "live": 1,
             "projected_live": 1, "remaining_ep": 4.5, "race": 5.5}]
    assert league_live_table(rows)[0]["race"] == 5.5


# --- the margins ------------------------------------------------------

TABLE = [
    {"entry": 4, "name": "Leader", "pre_total": 600, "live": 40,
     "projected": 640, "delta": 0},
    {"entry": 3, "name": "Above", "pre_total": 560, "live": 30,
     "projected": 590, "delta": 0},
    {"entry": 1, "name": "You", "pre_total": 540, "live": 40,
     "projected": 580, "delta": 0},
    {"entry": 2, "name": "Below", "pre_total": 520, "live": 45,
     "projected": 565, "delta": 0},
]


def test_the_strip_names_the_rival_above_the_rival_below_and_the_leader():
    strip = safety_margins(TABLE, entry=1)
    assert [s["role"] for s in strip] == ["above", "below", "leader"]
    assert [s["name"] for s in strip] == ["Above", "Below", "Leader"]


def test_a_rival_ahead_reports_what_it_takes_to_pass_him():
    above = safety_margins(TABLE, entry=1)[0]
    assert above["margin"] == 10          # they are ten in front
    assert above["need"] == 11            # eleven takes the place


def test_a_rival_behind_reports_a_negative_margin_and_needs_nothing():
    below = safety_margins(TABLE, entry=1)[1]
    assert below["margin"] == -15
    assert below["need"] == 0


def test_the_leader_is_not_repeated_when_he_is_the_man_immediately_above():
    table = [TABLE[1], TABLE[2], TABLE[3]]      # Above is now the leader
    strip = safety_margins(table, entry=1)
    assert [s["role"] for s in strip] == ["above", "below"]
    assert [s["entry"] for s in strip] == [3, 2]


def test_the_leader_gets_no_row_of_his_own_when_the_leader_is_me():
    strip = safety_margins(TABLE, entry=4)
    assert [s["role"] for s in strip] == ["below"]
    assert strip[0]["margin"] == -50


def test_the_bottom_of_the_league_has_nobody_below():
    strip = safety_margins(TABLE, entry=2)
    assert [s["role"] for s in strip] == ["above", "leader"]


def test_a_one_entry_table_has_no_margins_at_all():
    """No league configured: the players card still renders, the strip does
    not exist."""
    assert safety_margins([{"entry": 1, "name": "You", "projected": 10}],
                          entry=1) == []


def test_an_entry_not_in_the_table_has_no_margins():
    assert safety_margins(TABLE, entry=99) == []
```

Run it: expect failures on `safety_margins` and on the `projected_live` case.

- [ ] **Implement the table change.** In `src/gaffer/live_gw.py`, in `league_live_table`, replace the `out = [...]` line:

```python
    out = [dict(r, projected=int(r["pre_total"])
                + int(r.get("projected_live", r["live"]))) for r in rows]
```

and extend its docstring — after the paragraph beginning "``rows`` are" — with:

```
    A caller that has projected the auto-subs (``live_gw.projected_points``)
    may add ``projected_live`` to a row, and the projection is taken from
    that instead of from ``live``. It is a deliberate improvement to this
    column: ``live`` applies no auto-subs, so a table built from it
    understates every entry carrying a finished blank. The key is optional
    and the fallback is the old arithmetic exactly, so the CLI tracker and
    every caller that has no projection are unaffected.
```

- [ ] **Implement the margins.** Append after `league_live_table` (before `_arrow`):

```python
def safety_margins(table: list[dict], entry: int) -> list[dict]:
    """The three league places worth watching, from a projected table.

    ``table`` is :func:`league_live_table`'s output, already ordered by
    projected total. Returns at most three rows — the entry immediately
    above me, the one immediately below, and the leader — each carrying
    ``margin`` (their projected total minus mine, so positive means they are
    ahead) and ``need`` (the points I must add beyond my current projection
    to pass them, and 0 when I already have).

    Deduplicated by entry and ordered above, below, leader: when the leader
    *is* the man immediately above me he gets one row, labelled with the
    actionable role rather than the flattering one.

    League-relative only. An overall-rank safety score would need the whole
    field's live scores, and no public endpoint gives them; the card says so
    rather than implying this number is one.
    """
    order = [int(r.get("entry", -1)) for r in table]
    try:
        me = order.index(int(entry))
    except ValueError:
        return []

    mine = int(table[me]["projected"])
    wanted = []
    if me > 0:
        wanted.append(("above", me - 1))
    if me + 1 < len(table):
        wanted.append(("below", me + 1))
    if me != 0:
        wanted.append(("leader", 0))

    out, seen = [], set()
    for role, index in wanted:
        row = table[index]
        rival = int(row.get("entry", -1))
        if rival in seen:
            continue
        seen.add(rival)
        margin = int(row["projected"]) - mine
        out.append({"entry": rival, "name": str(row["name"]), "role": role,
                    "margin": margin, "need": max(margin + 1, 0)})
    return out
```

- [ ] **Verify — and prove the contract change broke nothing.**

```bash
uv run pytest -q tests/test_live_safety.py tests/test_live_gw.py \
  tests/test_live_projection.py tests/test_live_race.py
```

All green, `test_live_gw.py` **unmodified**. If any `league_live_table` test in `tests/test_live_gw.py` needs editing, stop: the change was not additive and the plan is wrong.

- [ ] **Commit.**

```bash
git add src/gaffer/live_gw.py tests/test_live_safety.py && git commit -m "$(cat <<'EOF'
feat: autosub-aware projected totals and the league safety margins

league_live_table's projected column reads an optional projected_live off
each row, falling back to live so the CLI tracker is unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the endpoint: schemas, wiring, and the in-memory race series

**Files:**
- Modify `src/gaffer/web/schemas.py`
- Modify `src/gaffer/web/routers/live.py`
- Modify `tests/test_web_live.py` (one assertion)
- Create `tests/test_web_live_v8d.py`

- [ ] **Write the failing test.** Create `tests/test_web_live_v8d.py`:

```python
"""``GET /api/live``, v8d: the projection, the race and the safety strip.

One real fifteen, and three fixture states chosen so every new number has a
hand-checkable answer. Team 1 has finished and everybody in it played; team 2
is still on the pitch; team 3 has finished and element 11 — a starter — never
came on, which is the one situation that triggers a projected substitution.

Every BPS is zero, so provisional bonus is zero everywhere and the arithmetic
under test is not entangled with v6's.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import gaffer.web.routers.live as live_mod
from gaffer.web.app import create_app

# XI: 1 GKP, 2-4 DEF, 5-8 MID, 9-11 FWD (9 is captain, 10 vice).
# Bench, in order: 12 GKP, 13 DEF, 14 MID, 15 FWD.
POSITION_OF = {1: "GKP", 2: "DEF", 3: "DEF", 4: "DEF",
               5: "MID", 6: "MID", 7: "MID", 8: "MID",
               9: "FWD", 10: "FWD", 11: "FWD",
               12: "GKP", 13: "DEF", 14: "MID", 15: "FWD"}
TEAM_OF = {**{e: 1 for e in range(1, 11)}, 11: 3, 12: 1,
           13: 2, 14: 2, 15: 2}
FIXTURE_OF = {1: 11, 2: 12, 3: 13}                  # team -> fixture id
MINUTES_OF = {**{e: 90 for e in range(1, 11)}, 11: 0, 12: 0, 13: 60,
              14: 0, 15: 0}
POINTS_OF = {**{e: 2 for e in range(1, 11)}, 9: 9, 11: 0, 12: 0, 13: 4,
             14: 0, 15: 0}
EP_OF = {**{e: 1.0 for e in range(1, 16)}, 9: 6.0, 13: 3.0}

LIVE = {"elements": [
    {"id": e,
     "stats": {"total_points": POINTS_OF[e], "bps": 0,
               "minutes": MINUTES_OF[e], "bonus": 0},
     "explain": [{"fixture": FIXTURE_OF[TEAM_OF[e]],
                  "stats": [{"identifier": "bps", "value": 0}]}]}
    for e in range(1, 16)]}

FIXTURES = [
    {"id": 11, "event": 3, "team_h": 1, "team_a": 21,
     "started": True, "finished": True},
    {"id": 12, "event": 3, "team_h": 2, "team_a": 22,
     "started": True, "finished": False},
    {"id": 13, "event": 3, "team_h": 3, "team_a": 23,
     "started": True, "finished": True},
]

MY_PICKS = {"picks": [
    {"element": e, "position": e,
     "multiplier": (2 if e == 9 else 0 if e > 11 else 1),
     "is_captain": e == 9, "is_vice_captain": e == 10}
    for e in range(1, 16)],
    "entry_history": {"total_points": 126, "points": 20}}

# The two figures every assertion below is measured against, computed by hand:
#   live      = nine starters on 2, the captain's 9 doubled, 11 on nothing
#             = 18 + 18 + 0 = 36
#   projected = the same, with 13 (four points, and on the pitch) replacing 11
#             = 40
MY_LIVE = 36
MY_PROJECTED = 40


class FakeClient:
    def __init__(self, standings=True):
        self.standings = standings

    def get_event_status(self):
        return {"status": [{"event": 3, "points": "p", "bonus_added": False}],
                "leagues": "Updating"}

    def get_event_live(self, gw):
        return LIVE

    def get_fixtures(self):
        return FIXTURES

    def get_entry_picks(self, entry_id, gw):
        return MY_PICKS          # the rival fields the same fifteen

    def get_league_standings(self, league_id, page=1):
        if not self.standings:
            raise RuntimeError("no league")
        return {"standings": {"has_next": False, "results": [
            {"entry": 1, "entry_name": "You FC", "player_name": "Me",
             "rank": 1, "last_rank": 1, "total": 106, "event_total": 20},
            {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
             "rank": 2, "last_rank": 2, "total": 100, "event_total": 20}]}}


PLAYERS = pd.DataFrame([
    {"code": 100 + e, "element": e, "name": f"P{e}",
     "position": POSITION_OF[e], "team_id": TEAM_OF[e],
     "team_code": 300 + TEAM_OF[e]}
    for e in range(1, 16)])
for _col, _default in (("now_cost", 50), ("status", "a"), ("news", ""),
                       ("chance_of_playing", None),
                       ("selected_by_percent", 5.0), ("form", 1.0),
                       ("points_per_game", 2.0), ("ep_next", 2.0),
                       ("price_change_percent", 0.0),
                       ("price_change_calibrating", False),
                       ("penalties_order", None),
                       ("direct_freekicks_order", None),
                       ("corners_and_indirect_freekicks_order", None)):
    PLAYERS[_col] = _default

COMPONENTS = pd.DataFrame(
    [{"element": e, "gw": 3, "ep": EP_OF[e]} for e in range(1, 16)]
    + [{"element": 9, "gw": 4, "ep": 9.9}])      # next week: never counted


def _setup(tmp_path, components=True, advice=True):
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    (tmp_path / "reports").mkdir(exist_ok=True)
    if components:
        COMPONENTS.to_parquet(tmp_path / "reports/components_gw3.parquet",
                              index=False)
    if advice:
        (tmp_path / "reports/gw3-advice.json").write_text(
            json.dumps({"gw": 3, "expected_pts": 61.5}))


@pytest.fixture(autouse=True)
def _clean_series():
    """The race series is per process, so it outlives a test unless cleared."""
    live_mod.RACE_SERIES.clear()
    yield
    live_mod.RACE_SERIES.clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    return TestClient(create_app())


def test_the_pinned_live_score_is_unchanged_by_the_projection(client):
    """``entry_live_points`` still scores the XI exactly as picked."""
    assert client.get("/api/live").json()["my_points"] == MY_LIVE


def test_the_projected_score_brings_the_substitute_on(client):
    assert client.get("/api/live").json()["my_projected_points"] == MY_PROJECTED


def test_a_finished_blank_is_chipped_on_both_players(client):
    body = client.get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[11]["projected_out"] is True
    assert by_element[11]["sub_partner"] == 13
    assert by_element[13]["projected_in"] is True
    assert by_element[13]["sub_partner"] == 11
    assert by_element[13]["sub_reason"] == "played"
    assert by_element[12]["projected_in"] is False    # the keeper stays put


def test_each_player_carries_what_he_still_owes(client):
    body = client.get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[9]["remaining_ep"] == 0.0     # team 1 has finished
    assert by_element[11]["remaining_ep"] == 0.0    # team 3 has finished
    assert by_element[13]["remaining_ep"] == 1.0    # 3.0 x (1 - 60/90)
    assert by_element[14]["remaining_ep"] == 1.0    # 1.0 x (not on yet)


def test_the_race_is_the_projection_plus_what_is_left(client):
    """Only 13 is both on the projected pitch and in an unfinished match, so
    the whole of the remaining EP is his one point."""
    body = client.get("/api/live").json()
    assert body["my_race"] == MY_PROJECTED + 1.0


def test_the_reference_line_is_this_gameweeks_saved_plan(client):
    assert client.get("/api/live").json()["race_reference"] == 61.5


def test_the_series_grows_one_point_per_poll_and_is_never_written_to_disk(
        client, tmp_path):
    first = client.get("/api/live").json()
    assert len(first["race_series"]) == 1
    assert first["race_series"][0]["you"] == first["my_race"]
    second = client.get("/api/live").json()
    assert len(second["race_series"]) == 2
    assert not list(tmp_path.glob("**/race*"))


def test_the_series_is_capped(client, monkeypatch):
    monkeypatch.setattr(live_mod, "RACE_SERIES_MAX", 3)
    for _ in range(5):
        body = client.get("/api/live").json()
    assert len(body["race_series"]) == 3


def test_a_new_gameweek_drops_the_previous_ones_trajectory(client):
    live_mod.RACE_SERIES[2] = [{"at": "old", "you": 1.0, "leader": None}]
    client.get("/api/live")
    assert list(live_mod.RACE_SERIES) == [3]


def test_the_safety_strip_prices_the_league_place(client):
    body = client.get("/api/live").json()
    strip = {s["role"]: s for s in body["safety"]}
    assert set(strip) == {"below"}          # I lead this two-entry league
    assert strip["below"]["name"] == "Ten Hag Hive"
    assert strip["below"]["margin"] == -6   # 100 + 40 against my 106 + 40
    assert strip["below"]["need"] == 0
    assert body["leader_name"] == "Ten Hag Hive"


def test_the_table_carries_the_race_beside_the_projection(client):
    body = client.get("/api/live").json()
    me = next(r for r in body["table"] if r["entry"] == 1)
    assert me["live"] == MY_LIVE
    assert me["projected_live"] == MY_PROJECTED
    assert me["race"] == me["projected_live"] + me["remaining_ep"]
    # The deliberate contract change: the season projection is built from the
    # auto-sub-aware gameweek, not from the raw live figure.
    assert me["projected"] == me["pre_total"] + MY_PROJECTED


def test_the_rival_is_projected_on_the_same_terms(client):
    """Spec §3 left rival remaining-EP to the planner; their picks are already
    fetched and the EP table is one read, so they get the full treatment."""
    body = client.get("/api/live").json()
    rival = next(r for r in body["table"] if r["entry"] == 2)
    assert rival["projected_live"] == MY_PROJECTED
    assert rival["remaining_ep"] == 1.0
    assert rival["race"] == MY_PROJECTED + 1.0
```

- [ ] **Add the schemas.** In `src/gaffer/web/schemas.py`, extend the three existing Live models and add two new ones. Every field is optional or defaulted: a client that has not been rebuilt reads the payload exactly as before.

Append to `LivePlayer` (after `selected_by_percent`):

```python
    # v8d: the auto-sub projection and what this player still owes. All
    # defaulted — a payload built without a component file carries the same
    # row it always did.
    projected_out: bool = False
    projected_in: bool = False
    sub_partner: int | None = None
    """The other half of a projected substitution, so a chip can name him."""
    sub_reason: str | None = None
    """``"played"`` or ``"yet to play"``: how certain the incoming man is."""
    remaining_ep: float | None = None
```

Append to `LiveTableRow`:

```python
    # v8d. ``live`` stays the no-autosub figure ``entry_live_points`` returns;
    # ``projected_live`` is the same gameweek with the projected subs applied,
    # and is what ``projected`` (the season total) is now built from.
    projected_live: int | None = None
    remaining_ep: float | None = None
    race: float | None = None
    """``projected_live + remaining_ep``: where this gameweek is heading."""
```

Add after `LiveTableRow`:

```python
class LiveSafety(BaseModel):
    """One league place worth watching, priced in points."""

    entry: int
    name: str
    role: Literal["above", "below", "leader"]
    margin: int
    """Their projected total minus mine. Positive means they are ahead."""
    need: int
    """What I must add beyond my projection to pass them; 0 when I lead."""


class LiveRacePoint(BaseModel):
    """One poll's snapshot of the race, held in memory for this session only."""

    at: str
    you: float
    leader: float | None = None
```

Append to `LiveState`:

```python
    my_projected_points: int = 0
    my_race: float | None = None
    race_reference: float | None = None
    """This gameweek's saved ``advice.expected_pts``, when there is one."""
    race_series: list[LiveRacePoint] = Field(default_factory=list)
    safety: list[LiveSafety] = Field(default_factory=list)
    leader_name: str | None = None
    race_notice: str | None = None
    """The race's own degradation line. Deliberately not ``notice``, which is
    the tier-EO line and belongs to a different card."""
```

- [ ] **Wire the router.** In `src/gaffer/web/routers/live.py`:

Imports — replace the `live_gw` import block and add pandas and `load_advice`:

```python
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter

from gaffer.artifacts import load_advice, load_components, load_snapshot
from gaffer.config import load_config
from gaffer.data.tier_eo import tier_eo_table
from gaffer.errors import GafferError
from gaffer.live_gw import (active_gameweek, entry_live_points,
                            league_live_table, projected_multipliers,
                            projected_points, projected_subs,
                            provisional_bonus, race_value, remaining_ep_total,
                            remaining_fraction, safety_margins)
from gaffer.web.schemas import (LivePlayer, LiveRacePoint, LiveSafety,
                                LiveState, LiveTableRow)
```

After the `INACTIVE` constant, add the series store:

```python
RACE_SERIES: dict[int, list[dict]] = {}
"""gameweek -> this process's poll-by-poll race trajectory.

Deliberately in memory and deliberately per process. Live state is ephemeral;
a restart mid-afternoon losing the last hour's trajectory is a smaller cost
than a file that has to be pruned, versioned and reasoned about between
gameweeks. Only the active gameweek is kept, and it is capped.
"""

RACE_SERIES_MAX = 500
"""Eight hours of minute polling, which outlasts any matchday."""
```

After `_finished_by_team`, add its opposite number and the EP reader:

```python
def _started_by_team(fixtures: list[dict]) -> dict[int, bool]:
    """team id -> "this team has at least one fixture under way or done".

    The mirror of :func:`_finished_by_team`, and deliberately ``any`` rather
    than ``all``: a player in a double gameweek whose first match has kicked
    off is no longer owed the full pre-match expectation.
    """
    out: dict[int, bool] = {}
    for fixture in fixtures:
        started = bool(fixture.get("started"))
        for side in ("team_h", "team_a"):
            team = fixture.get(side)
            if team is None:
                continue
            out[int(team)] = out.get(int(team), False) or started
    return out


def _ep_by_element(gw: int) -> tuple[dict[int, float], str | None]:
    """element -> this gameweek's banked EP, or ``({}, notice)``.

    The race is a nicety on top of a page that already works, so nothing here
    raises: a missing, stale or unreadable component file degrades the race to
    the projected score and says so on its own card. Double gameweeks sum both
    fixtures' EP and then spend it down against the team's aggregate state,
    which is coarse — a team half-way through the first of two matches reads
    as owing rather more than it does. Stated rather than hidden.
    """
    try:
        frame = load_components(gw)
        wanted = frame[pd.to_numeric(frame["gw"], errors="coerce") == gw]
        elements = pd.to_numeric(wanted["element"], errors="coerce")
        eps = pd.to_numeric(wanted["ep"], errors="coerce").fillna(0.0)
        out: dict[int, float] = {}
        for element, ep in zip(elements, eps):
            if pd.isna(element):
                continue
            out[int(element)] = out.get(int(element), 0.0) + float(ep)
    except GafferError as exc:
        return {}, f"{exc} — the race shows live points only"
    except Exception as exc:  # noqa: BLE001 — schema drift, unreadable parquet
        return {}, (f"component breakdown unreadable ({exc}) — "
                    f"the race shows live points only")
    if not out:
        return {}, (f"no GW{gw} rows in the component breakdown — "
                    f"the race shows live points only")
    return out, None


def _race_reference(gw: int) -> float | None:
    """The pre-gameweek plan's expected score, when it is *this* gameweek's."""
    try:
        advice = load_advice(gw)
    except Exception:  # noqa: BLE001 — absent, pruned or half-written
        return None
    if int(advice.get("gw", -1)) != gw:
        return None
    expected = advice.get("expected_pts")
    return None if expected is None else round(float(expected), 2)


def _project(picks: list[dict], points_of: dict[int, int],
             bonus: dict[int, int], minutes_of: dict[int, int],
             started_of: dict[int, bool], finished_of: dict[int, bool],
             positions: dict[int, str],
             ep_of: dict[int, float]) -> tuple[list[dict], int, float]:
    """One entry's projection: ``(subs, projected points, remaining EP)``.

    Used for me and for every rival, on the same terms — their picks are
    already fetched to score them, and the EP table is one read for the whole
    league, so the full treatment costs no extra API call. A rival holding a
    player who is not in the snapshot simply projects no sub for him.
    """
    subs = projected_subs(picks, minutes_of, finished_of, positions)
    multipliers = projected_multipliers(picks, subs, minutes_of, finished_of)
    points = projected_points(points_of, bonus, multipliers)
    remaining = remaining_ep_total(multipliers, ep_of, minutes_of, started_of,
                                  finished_of)
    return subs, points, remaining
```

In the `live()` body, after `finished_by_team = _finished_by_team(fixtures)` (L86) add:

```python
    started_by_team = _started_by_team(fixtures)
    ep_of, race_notice = _ep_by_element(gw)
```

After `by_element` is built (L95), add the element-keyed maps the pure
functions want:

```python
    positions = {int(r.element): str(r.position)
                 for r in snapshot.itertuples()}
    team_of = {int(r.element): int(r.team_id) for r in snapshot.itertuples()}
    finished_of = {element: finished_by_team.get(team, False)
                   for element, team in team_of.items()}
    started_of = {element: started_by_team.get(team, False)
                  for element, team in team_of.items()}
    my_subs, my_projected, my_remaining = _project(
        mine["picks"], points_of, bonus, minutes_of, started_of, finished_of,
        positions, ep_of)
    sub_out = {int(s["out_element"]): s for s in my_subs}
    sub_in = {int(s["in_element"]): s for s in my_subs}
```

Inside the player loop, replace the `players.append(LivePlayer(...))` call's
tail so the new fields are carried (keep every existing argument exactly):

```python
        out_of = sub_out.get(element)
        into = sub_in.get(element)
        players.append(LivePlayer(
            element=element, code=int(row.code), name=str(row.name),
            position=str(row.position),
            multiplier=int(pick.get("multiplier", 0)),
            points=int(points_of.get(element, 0)),
            provisional_bonus=int(bonus.get(element, 0)),
            minutes=minutes, status=_status(minutes, not team_done),
            tier_eo=sampled.get("eo"), tier_eo_se=sampled.get("se"),
            selected_by_percent=(float(row.selected_by_percent)
                                 if getattr(row, "selected_by_percent", None)
                                 is not None else None),
            projected_out=out_of is not None,
            projected_in=into is not None,
            sub_partner=(int(out_of["in_element"]) if out_of
                         else int(into["out_element"]) if into else None),
            sub_reason=((out_of or into or {}).get("reason")
                        if (out_of or into) else None),
            remaining_ep=(round(float(ep_of.get(element, 0.0))
                                * remaining_fraction(
                                    minutes,
                                    started_of.get(element, False),
                                    finished_of.get(element, False)), 2)
                          if ep_of else None)))
```

Note the per-player `remaining_ep` is **unmultiplied** — it is what that
player still owes, not what the armband turns it into. The armband is applied
once, inside `remaining_ep_total`.

Replace the `rows = [...]` / league block and the tail of the function:

```python
    rows = [{"entry": cfg.entry_id, "name": "You", "pre_total": my_pre,
             "live": my_points, "projected_live": my_projected,
             "remaining_ep": my_remaining,
             "race": race_value(my_projected, my_remaining)}]
    if cfg.league_id:
        standings = _guard(client.get_league_standings,
                           cfg.league_id)["standings"]["results"]
        for entry in standings:
            if int(entry["entry"]) == cfg.entry_id:
                continue
            try:
                picks = _guard(client.get_entry_picks, int(entry["entry"]), gw)
            except GafferError:
                continue          # picks not public — skip, as the CLI does
            _, projected, remaining = _project(
                picks["picks"], points_of, bonus, minutes_of, started_of,
                finished_of, positions, ep_of)
            rows.append({"entry": int(entry["entry"]),
                         "name": str(entry["entry_name"]),
                         "pre_total": int(entry["total"]),
                         "live": entry_live_points(picks["picks"], points_of,
                                                   bonus),
                         "projected_live": projected,
                         "remaining_ep": remaining,
                         "race": race_value(projected, remaining)})

    table_rows = league_live_table(rows)
    safety = [LiveSafety(**margin)
              for margin in safety_margins(table_rows, cfg.entry_id)]
    table = [LiveTableRow(**row) for row in table_rows]

    # The trajectory: one point per poll, this process only, this gameweek
    # only. Nothing is written to disk and nothing survives a restart.
    leader = next((r for r in table_rows
                   if int(r.get("entry", -1)) != cfg.entry_id), None)
    my_race = race_value(my_projected, my_remaining)
    for stale in [key for key in RACE_SERIES if key != gw]:
        RACE_SERIES.pop(stale, None)
    series = RACE_SERIES.setdefault(gw, [])
    series.append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "you": my_race,
        "leader": (float(leader["race"]) if leader
                   and leader.get("race") is not None else None)})
    del series[:-RACE_SERIES_MAX]

    in_play = sum(1 for f in fixtures
                  if f.get("started") and not f.get("finished"))
    return LiveState(active=True, gw=gw, my_points=my_points,
                     matches_in_play=in_play, players=players, table=table,
                     notice=notice, my_projected_points=my_projected,
                     my_race=my_race, race_reference=_race_reference(gw),
                     race_series=[LiveRacePoint(**point) for point in series],
                     safety=safety,
                     leader_name=(str(leader["name"]) if leader else None),
                     race_notice=race_notice)
```

- [ ] **Update the one deliberate test edit.** In `tests/test_web_live.py`, the inactive-payload assertion (L124-126) compares the whole body. New defaulted fields appear in it, so extend the expected dict — deliberately, and with the reason on it:

```python
def test_live_between_gameweeks_is_a_quiet_inactive_payload(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.live.fpl_client",
                        lambda: FakeClient(active=False))
    body = TestClient(create_app()).get("/api/live").json()
    # v8d adds six defaulted fields to LiveState. The quiet payload is still
    # quiet: every one of them is its empty value, because nothing between
    # gameweeks is projected, raced or ranked.
    assert body == {"active": False, "gw": None, "my_points": 0,
                    "matches_in_play": 0, "players": [], "table": [],
                    "notice": None, "my_projected_points": 0,
                    "my_race": None, "race_reference": None,
                    "race_series": [], "safety": [], "leader_name": None,
                    "race_notice": None}
```

No other assertion in that file changes. If one does, stop and report: it means a field stopped being additive.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_live_v8d.py tests/test_web_live.py \
  tests/test_live_gw.py tests/test_live_projection.py \
  tests/test_live_race.py tests/test_live_safety.py
uv run pytest -q
```

The last run must show the 2117 baseline plus this cycle's new tests, all passing.

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/live.py \
  tests/test_web_live.py tests/test_web_live_v8d.py && git commit -m "$(cat <<'EOF'
feat: /api/live serves the projection, the race and the safety margins

The race trajectory is per process and in memory: live state is ephemeral, so
nothing here writes to disk. LiveState's new fields are all defaulted, and
the inactive payload's assertion is updated deliberately.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — the Live hub: the race chart, the safety strip, the chips

**Files:**
- Modify `frontend/src/types.ts`
- Modify `frontend/src/hubs/Live.tsx`
- Modify `frontend/src/hubs/Live.test.tsx`

- [ ] **Write the failing tests.** In `frontend/src/hubs/Live.test.tsx`, extend the `ACTIVE` fixture and add the cases. Replace the fixture block (L16-37) with:

```tsx
const ACTIVE = {
  active: true, gw: 3, my_points: 66, matches_in_play: 2,
  players: [{ element: 7, code: 100, name: 'Salah', position: 'MID',
              multiplier: 2, points: 9, provisional_bonus: 3, minutes: 90,
              status: 'playing', tier_eo: 143.5, tier_eo_se: 2.1,
              selected_by_percent: 45, projected_out: false,
              projected_in: false, sub_partner: null, sub_reason: null,
              remaining_ep: 0 },
            { element: 9, code: 102, name: 'Blank', position: 'FWD',
              multiplier: 1, points: 0, provisional_bonus: 0, minutes: 0,
              status: 'played', tier_eo: null, tier_eo_se: null,
              selected_by_percent: 2, projected_out: true, projected_in: false,
              sub_partner: 12, sub_reason: 'played', remaining_ep: 0 },
            { element: 12, code: 103, name: 'Sub', position: 'FWD',
              multiplier: 0, points: 4, provisional_bonus: 0, minutes: 60,
              status: 'playing', tier_eo: null, tier_eo_se: null,
              selected_by_percent: 3, projected_out: false, projected_in: true,
              sub_partner: 9, sub_reason: 'played', remaining_ep: 1.5 }],
  table: [{ entry: 1, name: 'You', pre_total: 106, live: 66, projected: 172,
            delta: 1, projected_live: 66, remaining_ep: 1.5, race: 67.5 }],
  notice: null,
  my_projected_points: 70,
  my_race: 71.5,
  race_reference: 61.5,
  race_series: [
    { at: '2026-08-31T14:00:00+00:00', you: 40, leader: 38 },
    { at: '2026-08-31T14:01:00+00:00', you: 71.5, leader: 44 },
  ],
  safety: [
    { entry: 3, name: 'Above', role: 'above', margin: 10, need: 11 },
    { entry: 2, name: 'Below', role: 'below', margin: -15, need: 0 },
  ],
  leader_name: 'Above',
  race_notice: null,
}

const NO_TIER = {
  ...ACTIVE,
  players: [{ ...ACTIVE.players[0], tier_eo: null, tier_eo_se: null,
              selected_by_percent: null }],
  notice: 'top-10k EO unavailable (429) — league EO only',
}

const NO_COMPONENTS = {
  ...ACTIVE,
  my_race: 70, race_reference: null, race_series: [], safety: [],
  race_notice: 'no component breakdown for GW3 — the race shows live points '
    + 'only',
}

const IDLE = {
  active: false, gw: null, my_points: 0, matches_in_play: 0, players: [],
  table: [], my_projected_points: 0, my_race: null, race_reference: null,
  race_series: [], safety: [], leader_name: null, race_notice: null,
}
```

The existing test `shows points, provisional bonus and the projected table`
asserts `getAllByText('66')` has length 2; with the richer fixture that count
is unchanged (66 appears as the stat and as the table's `live`). If it moves,
adjust that number and nothing else.

Append these cases inside the `describe('Live')` block:

```tsx
  it('heads the score with where it is going, not only where it is',
    async () => {
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      expect(screen.getByText('Projected')).toBeInTheDocument()
      expect(screen.getByText('70')).toBeInTheDocument()
      expect(screen.getByText('71.5')).toBeInTheDocument()
    })

  it('draws the race against the pre-gameweek plan', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText(/race to full time/i)).toBeInTheDocument()
    expect(screen.getByText(/plan 61.5/)).toBeInTheDocument()
  })

  it('waits for a second poll before drawing a trajectory', async () => {
    apiGet.mockResolvedValue({ ...ACTIVE, race_series: [ACTIVE.race_series[0]] })
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText(/builds as the page polls/i)).toBeInTheDocument()
  })

  it('prices each league place it can reach', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('One place above')).toBeInTheDocument()
    expect(screen.getByText(/need \+11/)).toBeInTheDocument()
    expect(screen.getByText('One place below')).toBeInTheDocument()
    expect(screen.getByText(/15 clear/)).toBeInTheDocument()
    expect(screen.getByText(/league places only/i)).toBeInTheDocument()
  })

  it('chips the projected auto-substitution on both players', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('auto-sub out')).toBeInTheDocument()
    expect(screen.getByText('auto-sub in · played')).toBeInTheDocument()
  })

  it('says why the race is only live points when nothing is banked',
    async () => {
      apiGet.mockResolvedValue(NO_COMPONENTS)
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      expect(screen.getByText(/no component breakdown for GW3/))
        .toBeInTheDocument()
      expect(screen.queryByText('One place above')).not.toBeInTheDocument()
    })
```

Run `cd frontend && npx vitest run src/hubs/Live.test.tsx` — expect failures.

- [ ] **Add the types.** In `frontend/src/types.ts`, extend the three Live
interfaces and add two, keeping every new field optional-or-nullable so a
stale payload still typechecks:

```ts
export interface LivePlayer {
  element: number
  code: number
  name: string
  position: string
  multiplier: number
  points: number
  provisional_bonus: number
  minutes: number
  status: 'played' | 'playing' | 'yet to play'
  tier_eo?: number | null
  tier_eo_se?: number | null
  selected_by_percent?: number | null
  // v8d
  projected_out?: boolean
  projected_in?: boolean
  sub_partner?: number | null
  sub_reason?: string | null
  remaining_ep?: number | null
}

export interface LiveTableRow {
  entry: number
  name: string
  pre_total: number
  live: number
  projected: number
  delta: number
  projected_live?: number | null
  remaining_ep?: number | null
  race?: number | null
}

export interface LiveSafety {
  entry: number
  name: string
  role: 'above' | 'below' | 'leader'
  margin: number
  need: number
}

export interface LiveRacePoint {
  at: string
  you: number
  leader?: number | null
}

export interface LiveState {
  active: boolean
  gw: number | null
  my_points: number
  matches_in_play: number
  players: LivePlayer[]
  table: LiveTableRow[]
  notice?: string | null
  my_projected_points?: number
  my_race?: number | null
  race_reference?: number | null
  race_series?: LiveRacePoint[]
  safety?: LiveSafety[]
  leader_name?: string | null
  race_notice?: string | null
}
```

- [ ] **Build the hub.** In `frontend/src/hubs/Live.tsx`:

Imports:

```tsx
import { useCallback, useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../api/client'
import {
  type Column, Badge, Card, DataTable, EmptyState, Loading, PageHeader,
  PlayerName, Stat, fmtNum,
} from '../kit'
import type { LiveState, LiveTableRow } from '../types'
```

Module constants, after `POLL_MS`:

```tsx
const ROLE_LABEL: Record<string, string> = {
  above: 'One place above',
  below: 'One place below',
  leader: 'The leader',
}

/** The series carries ISO instants; the axis wants a wall clock. */
function clock(at: string): string {
  return at.slice(11, 16)
}
```

Add the race column to `TABLE_COLUMNS`, after `projected`:

```tsx
  { key: 'race', header: 'Race', numeric: true,
    value: (r) => (r.race == null ? '–' : fmtNum(r.race, 1)) },
```

In the returned JSX, extend the stat row:

```tsx
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Your points" value={fmtNum(data.my_points, 0)} />
        <Stat label="Projected"
              value={fmtNum(data.my_projected_points ?? data.my_points, 0)} />
        <Stat label="Race"
              value={data.my_race == null ? '–' : fmtNum(data.my_race, 1)} />
        <Stat label="Matches in play" value={fmtNum(data.matches_in_play, 0)} />
      </div>
```

Insert the race card immediately after that row and before the "Your players"
card:

```tsx
      <Card
        title="Race to full time"
        className="mb-4"
        action={(
          <span className="text-text-muted">
            Projected points plus what the model still expects from every
            player whose match is unfinished.
          </span>
        )}
      >
        {data.race_notice && (
          <p className="mb-3 rounded-card border-l-2 border-info bg-base px-3
                        py-2 text-text-muted">
            {data.race_notice}
          </p>
        )}
        {(data.race_series?.length ?? 0) < 2 ? (
          <p className="text-text-muted">
            The trajectory builds as the page polls — one point a minute from
            the moment you opened it, and it starts again when the server
            restarts.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.race_series}>
              <CartesianGrid stroke="var(--color-divider)" vertical={false} />
              <XAxis dataKey="at" tickFormatter={clock}
                     stroke="var(--color-text-muted)" />
              <YAxis stroke="var(--color-text-muted)" />
              <Tooltip
                labelFormatter={clock}
                contentStyle={{
                  background: 'var(--color-card)',
                  border: '1px solid var(--color-border)',
                }} />
              {data.race_reference != null && (
                <ReferenceLine
                  y={data.race_reference}
                  stroke="var(--color-text-muted)"
                  strokeDasharray="4 4"
                  label={{ value: `plan ${data.race_reference}`,
                           position: 'insideTopRight',
                           fill: 'var(--color-text-muted)', fontSize: 11 }} />
              )}
              <Line type="monotone" dataKey="you" name="You" dot={false}
                    strokeWidth={2.5} stroke="var(--color-sage)" />
              <Line type="monotone" dataKey="leader"
                    name={data.leader_name ?? 'Top rival'} dot={false}
                    strokeWidth={1.5} stroke="var(--color-info)" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>
```

Insert the safety strip between the players card and the league card:

```tsx
      {(data.safety?.length ?? 0) > 0 && (
        <div className="mb-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {data.safety?.map((place) => (
              <div key={`${place.role}-${place.entry}`}
                   className="rounded-card border border-border bg-card px-4
                              py-3">
                <p className="label">{ROLE_LABEL[place.role]}</p>
                <p className="text-text">{place.name}</p>
                <p className={`num ${place.margin >= 0
                  ? 'text-rust' : 'text-sage'}`}>
                  {place.margin >= 0
                    ? `${place.margin} ahead · need +${place.need}`
                    : `${-place.margin} clear`}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-text-muted">
            League places only. Overall rank needs the whole field's live
            scores, which no public endpoint gives.
          </p>
        </div>
      )}
```

In the players table, add a "Left" header after "Mins":

```tsx
                <th className="label pb-1 text-right">Left</th>
```

and, in the row, the chips beside the name plus the matching cell:

```tsx
                  <td className="py-1.5">
                    <span className="inline-flex flex-wrap items-center
                                     gap-1.5">
                      <PlayerName code={player.code} name={player.name}
                                  pos={player.position} />
                      {player.multiplier > 1 && ' (C)'}
                      {player.projected_out && (
                        <Badge variant="negative"
                               title="His matches are over and he did not
                                      play, so FPL will substitute him.">
                          auto-sub out
                        </Badge>
                      )}
                      {player.projected_in && (
                        <Badge variant="positive"
                               title="Projected to come on for a starter whose
                                      matches are over.">
                          {`auto-sub in · ${player.sub_reason ?? ''}`}
                        </Badge>
                      )}
                    </span>
                  </td>
```

and after the minutes cell:

```tsx
                  <td className="num py-1.5 text-right text-text-secondary">
                    {player.remaining_ep == null
                      ? '–' : fmtNum(player.remaining_ep, 1)}
                  </td>
```

- [ ] **Verify.**

```bash
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/hubs/Live.tsx \
  frontend/src/hubs/Live.test.tsx && git commit -m "$(cat <<'EOF'
feat: the Live hub gains the race chart, the safety strip and auto-sub chips

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — G2: the degradation rails

**Files:**
- Create `tests/test_v8d_degradation.py`

Every rail the spec's G2 names, in one file, so a single command proves the cycle.

- [ ] **Write it.** Create `tests/test_v8d_degradation.py`:

```python
"""v8d rails: what the live matchday view does when the inputs are missing.

The Live hub is the page opened at three o'clock on a Saturday, when nothing
can be fixed and every dependency — the component file, the league, the API —
is either there or it is not. Each of these tests is one of those afternoons.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

import gaffer.live_gw as live_gw
import gaffer.web.routers.live as live_mod
from gaffer.web.app import create_app
from tests.test_web_live_v8d import (COMPONENTS, FakeClient, MY_PICKS,
                                     _setup)


@pytest.fixture(autouse=True)
def _clean_series():
    live_mod.RACE_SERIES.clear()
    yield
    live_mod.RACE_SERIES.clear()


def _client(tmp_path, monkeypatch, standings=True, **kwargs):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path, **kwargs)
    monkeypatch.setattr(live_mod, "fpl_client",
                        lambda: FakeClient(standings=standings))
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    return TestClient(create_app())


# --- no components ----------------------------------------------------


def test_without_components_the_race_is_the_projected_score_and_says_so(
        tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, components=False)
    body = client.get("/api/live").json()
    assert body["active"] is True
    assert body["my_race"] == body["my_projected_points"]
    assert "component breakdown" in body["race_notice"]
    assert body["notice"] is None          # the tier-EO line is untouched
    assert all(p["remaining_ep"] is None for p in body["players"])


def test_a_component_file_for_the_wrong_gameweek_degrades_the_same_way(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path, components=False)
    COMPONENTS[COMPONENTS["gw"] == 4].to_parquet(
        tmp_path / "reports/components_gw3.parquet", index=False)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    body = TestClient(create_app()).get("/api/live").json()
    assert "no GW3 rows" in body["race_notice"]
    assert body["my_race"] == body["my_projected_points"]


def test_an_unreadable_component_file_is_a_notice_not_a_500(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path, components=False)
    (tmp_path / "reports/components_gw3.parquet").write_text("not a parquet")
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    body = TestClient(create_app()).get("/api/live").json()
    assert body["active"] is True and body["race_notice"]


def test_no_saved_advice_leaves_the_reference_line_off(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, advice=False)
    assert client.get("/api/live").json()["race_reference"] is None


# --- no league --------------------------------------------------------


def test_without_a_league_the_strip_is_absent_and_the_players_card_is_fine(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n')
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    body = TestClient(create_app()).get("/api/live").json()
    assert body["safety"] == []
    assert body["leader_name"] is None
    assert len(body["table"]) == 1
    assert len(body["players"]) == len(MY_PICKS["picks"])
    assert body["race_series"][0]["leader"] is None


# --- the API is down --------------------------------------------------


def test_a_dead_api_is_still_the_existing_retriable_guard(tmp_path,
                                                          monkeypatch):
    class Dead:
        def get_event_status(self):
            raise RuntimeError("connection reset")

    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: Dead())
    response = TestClient(create_app(), raise_server_exceptions=False) \
        .get("/api/live")
    assert response.status_code == 422
    assert "retry in a moment" in response.json()["detail"]


# --- the pinned contract ----------------------------------------------


def test_entry_live_points_still_applies_no_autosubs(tmp_path):
    """A copy of the pin, restated here so a v8d change to the projection can
    never quietly become a change to the figure three callers rely on."""
    picks = [{"element": 1, "multiplier": 1},      # blanked starter
             {"element": 2, "multiplier": 0}]      # bench player who hauled
    points = {1: 0, 2: 12}
    assert live_gw.entry_live_points(picks, points, {1: 0, 2: 3}) == 0


def test_the_projection_is_a_separate_function_from_the_pinned_one():
    """``projected_points`` composes ``entry_live_points``; it does not
    reimplement it, and ``entry_live_points`` takes no projection argument."""
    assert list(inspect.signature(live_gw.entry_live_points).parameters) == [
        "picks", "points_of", "bonus"]
    assert "entry_live_points" in inspect.getsource(live_gw.projected_points)


def test_nothing_in_the_live_path_writes_to_disk(tmp_path, monkeypatch):
    """The projection is display-only. Three polls, and the tree is byte-for-
    byte what it was."""
    client = _client(tmp_path, monkeypatch)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")
              if p.is_file()}
    for _ in range(3):
        assert client.get("/api/live").status_code == 200
    after = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")
             if p.is_file()}
    assert before == after


def test_the_race_series_never_leaves_the_process(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.get("/api/live")
    assert live_mod.RACE_SERIES                  # in memory
    assert not list(tmp_path.rglob("*race*"))    # and nowhere else


def test_v8d_adds_no_job_kinds(tmp_path, monkeypatch):
    """The whole cycle is a read path: no launchd plist, no queued work."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert "live" not in JOB_KINDS
    assert "race" not in JOB_KINDS
    assert len(JOB_KINDS) == 9


def test_v8d_adds_no_config_keys(tmp_path, monkeypatch):
    """Nothing in the cycle is switchable, so nothing in the cycle is
    configured (spec §2)."""
    import gaffer.config as config_mod

    source = inspect.getsource(config_mod)
    for key in ("race_", "safety_", "autosub"):
        assert key not in source
```

Note: `test_v8d_adds_no_job_kinds` pins the count at 9 (v8b's `review` was the
ninth). If the count differs when the task runs, read `JOB_KINDS` and pin what
is there — the assertion that matters is that v8d added none.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_v8d_degradation.py
```

- [ ] **Commit.**

```bash
git add tests/test_v8d_degradation.py && git commit -m "$(cat <<'EOF'
test: v8d degradation rails

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the documentation

**Files:**
- Modify `README.md`

- [ ] **Correct the caveat the CLI section states.** The "no autosubs are applied" sentence is still true of `gaffer live`, and is now only true of the CLI. In the **Live gameweek** section (~L218), replace the closing sentence of the paragraph:

```markdown
Read-only, for while the matches are on. Prints your live points and a
projected league table, with two caveats it states itself: bonus points are
provisional, reconstructed 3/2/1 from the current BPS table until FPL settles
each match, and no autosubs are applied — the XI is scored as picked, so bench
points never count. The web UI's Live page projects the autosubs as well; the
CLI stays the plain read. Between gameweeks it prints "no gameweek in
progress" and exits clean.
```

- [ ] **Describe what the hub now shows.** In the seven-pages paragraph (~L242), replace the **Live** clause:

```markdown
**Live** (in-gameweek points, auto-refreshing: the auto-subs FPL would apply
if the afternoon ended now, a race chart of where your score is heading —
points banked plus the expectation still owed by every unfinished match,
against the pre-gameweek plan — and what you need to take or hold the league
places either side of you)
```

- [ ] **State the two limits.** Immediately after that paragraph's closing
sentence about the theme toggle, add:

```markdown
Two things the Live page will not pretend to know. The race trajectory lives
in the server process and nowhere else — restart `gaffer ui` mid-afternoon and
it starts again from that moment, which is the price of a page that writes
nothing. And the safety numbers are league places only: an overall-rank
cushion would need every one of ten million entries' live scores, and no
public endpoint gives them.
```

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: what the Live page projects, and what it will not claim

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the audit, and the gate checklist (unfilled)

**Files:** none created except the spec appendix. This task runs commands and reports.

- [ ] **Prove the protected files are untouched.**

```bash
git diff --stat main...HEAD -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/*' tests/test_advise.py tests/test_odds.py \
  tests/test_web_jobs.py scripts/s2_replay.py src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py \
  tests/test_degradation.py tests/test_v4c_degradation.py \
  tests/test_v4d_degradation.py tests/test_v5_degradation.py \
  tests/test_v6_degradation.py tests/test_v7_model_degradation.py \
  tests/test_v8a_degradation.py tests/test_v8b_degradation.py \
  tests/test_v8c_degradation.py
```

Expected: **no output at all.** Any line is a plan failure — report it rather than reverting quietly.

- [ ] **Prove the import-only files are untouched.**

```bash
git diff --stat main...HEAD -- src/gaffer/journal.py src/gaffer/backtest.py
```

Expected: no output. `_formation_legal` is imported by `live_gw.py` and lives where it always did.

- [ ] **Prove `entry_live_points` is byte-identical.**

```bash
git diff main...HEAD -- src/gaffer/live_gw.py | grep -n 'entry_live_points' || echo "untouched"
```

Expected: the only hits are *added* lines (`+`) that call it — the new
`projected_points` body and the new import line in the router. No `-` line may
mention it, and no line inside its body may change. Read the diff hunk to
confirm.

- [ ] **Prove the only test file edited is the one the plan named.**

```bash
git diff --name-only main...HEAD -- tests/
```

Expected: `tests/test_web_live.py` (the deliberate inactive-payload edit) plus
the four created files. `tests/test_live_gw.py` must **not** appear.

- [ ] **Prove no runtime data was staged.**

```bash
git diff --name-only main...HEAD | grep -E '^(data|reports|models|logs)/|^config\.toml$' || echo "clean"
```

Expected: `clean`.

- [ ] **Security ritual (CONVENTIONS.md §8).**

```bash
git diff main...HEAD | grep -inE 'api[_-]?key|secret|token|password|bearer ' || echo "no keys"
git show main:config.toml && echo "LEAK" || echo "config.toml is not tracked"
```

Expected: `no keys`, then `config.toml is not tracked`.

- [ ] **Full suites.**

```bash
uv run pytest -q
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```

Expected: the 2117 Python baseline plus this cycle's new tests; the frontend
baseline of 344 + 1 skipped plus this cycle's six Live cases, i.e. **350
passed, 1 skipped**; a clean typecheck; a clean build.

- [ ] **Leave the gate checklist for the orchestrator.** Implementers build the
driver and never run the gates (CONVENTIONS.md §7). Append this block to
`docs/superpowers/specs/2026-08-31-gaffer-v8d-live-matchday-design.md` under
§4, unfilled, and commit it:

```markdown
### Gate results (orchestrator-run)

**G1 — live smoke.** `uv run gaffer ui`, Live page open during or straight
after a real gameweek, against the real API.

- [ ] `/api/live` returns the new fields populated: `my_projected_points`,
      `my_race`, `race_reference`, `race_series`, `safety`, and per-player
      `remaining_ep`.
- [ ] **Projected subs hand-checked.** Every starter in my squad whose team's
      fixtures are finished on 0 minutes is chipped `auto-sub out`, the man
      chipped `auto-sub in` is the first legal bench player in bench order,
      and the resulting eleven is a legal formation. If no starter blanked
      that week, say so and check a rival's row instead, or re-run after the
      next gameweek — an unexercised projection is not a passed gate.
- [ ] **Race arithmetic spot-checked by hand** on one player: his
      `remaining_ep` equals his `reports/components_gw{N}.parquet` `ep` times
      the fraction of his fixture unplayed, and `my_race` equals
      `my_projected_points` plus the multiplier-weighted sum over the XI.
- [ ] **Safety margins consistent with the table below them:** each strip
      row's `margin` equals that entry's `projected` minus mine, read straight
      off the rendered league table.
- [ ] Trajectory grows one point per minute while the page is open, and the
      reference line sits at the gameweek's saved `expected_pts`.
- [ ] Transcribe the `/api/live` body and the hand-check verbatim
      (CONVENTIONS.md §4).

Output:

```
(paste the /api/live body and the hand-check here)
```

**G2 — rails.** `uv run pytest -q tests/test_v8d_degradation.py`

- [ ] All passed. Specifically: components absent ⇒ race equals the projected
      score with a `race_notice`; no league ⇒ `safety` empty and the players
      card intact; dead API ⇒ the existing 422 guard, unchanged;
      `entry_live_points` pin green; no disk writes across three polls; job
      kinds unchanged; no config keys added.

**G3 — suites and audit.**

- [ ] `uv run pytest -q` green.
- [ ] `npx vitest run`, `npx tsc --noEmit`, `npm run build` green.
- [ ] Task 8's protected-file, import-only and `entry_live_points` diffs all
      empty.
- [ ] The `league_live_table` `projected` change is the cycle's only contract
      change, and `tests/test_live_gw.py` is unmodified.
```

```bash
git add docs/superpowers/specs/2026-08-31-gaffer-v8d-live-matchday-design.md \
  && git commit -m "$(cat <<'EOF'
docs: v8d gate checklist, unfilled

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

- [ ] **Report to the orchestrator.** State: the suite counts, the audit
output, and anything a task had to settle differently from this plan. Do not
run G1.
