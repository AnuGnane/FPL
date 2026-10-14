# The chip pair's What-If arm — design note

**Status:** not applied; a `needs-mac` package for the Mac lane.

**Provenance.** Written in the cloud as holiday F-36 and carried in the body
of PR #45, which merged only its HOLIDAY.md tick. A PR body is not a place
the repo's docs point at, so holiday F-50 files it here verbatim: the
rulings and the three hunks are PR #45's text unchanged. Line references
are to `main` at `ad1c110`, PR #45's base, and want re-reading against the
tree the package lands on.

**Who makes which diff.** Hunk 2 is in `src/gaffer/web/routers/whatif.py`,
which is orchestrator-only (`CLAUDE.md` "Pins and protected files"). A
subagent implementer does not touch it; the orchestrator makes that diff
from this note. Hunk 1 (`src/gaffer/web/schemas.py`) and hunk 3
(`frontend/src/hubs/planning/ChipsTab.tsx`) are not orchestrator-only.

## Gate

- `uvx ruff check src tests`
- `.venv/bin/pytest -q -m "not slow and not golden"`
- `cd frontend && npm run types -- --check && npm run check`, because hunk 1
  regenerates `schemas.json` and `types.generated.ts` and hunk 3 changes
  `ChipsTab.tsx`
- The golden gate on the Mac (`.venv/bin/pytest -q -rs
  tests/test_golden_board.py tests/test_pipeline.py`). `schemas.py` is
  golden-imported. `whatif.py` is on the golden path only by import:
  `tests/golden_client.py:496` builds `create_app()`, which includes the
  What-If router (`web/app.py:136`), but no golden request calls
  `/api/whatif` (the board reads `/api/plan/{gw}`). So the board is not
  expected to move, and the package is `needs-mac` because of that import
  and `schemas.py`.
- Pins unchanged: routes 52, `JOB_KINDS` 12, `Config` 62.

## Rulings (PR #45)

1. The pair is carried as one extra field, `bb_gw` (the gameweek of the bench boost), alongside `chip: "wc"`. There is no second chip enum, because the pair's second chip is always the bench boost. **Default: `bb_gw`.**
2. Only a pair whose wildcard is in this gameweek gets the button, because the lab plays chips in its first gameweek only. A later pair keeps today's disabled button, with a sentence naming its wildcard week. **Default: this week only.**
3. The note found a bug in existing code: `summary()` counts the bench boost and the triple captain in every horizon week, not only the chip's week. It is in the same orchestrator-only file, so it is noted here and not fixed. **Default: fix it in the same package as the arm (hunk 2).**

**Risk (PR #45):** Nobody has run this note. Line references are to `main` at `ad1c110`. Once hunk 2 lands, the lab shows different numbers for a single bench boost or triple captain over a multi-week horizon. The new numbers are the correct ones, but the change should be called out when it lands.

## The design

Today `ChipsTab.tsx` withholds "Try it" on the `wildcard+bboost` row (`armed = CHIP_CODES[chip] !== undefined`, `:204`), because a What-If request has no way to say two chips. The chip table prices the pair in `optimize/chips.py:207-215` as `solve_plan(pool, replace(state, wildcard_gw=g, bench_boost_gw=g2))`. Here g2 is a later week in `dgw_gws`: an entry in `load_chip_scenarios()` with probability at least `chips.PAIR_DGW_MIN_PROB` (`advise.py:994`). The arm runs that same solve with the lab's constraints added.

### Hunk 1 — `src/gaffer/web/schemas.py` (golden-imported, not orchestrator-only)
```python
class WhatIfRequest(BaseModel):
    ...
    chip: Literal["none", "wc", "bb", "fh", "tc"] = "none"
    # holiday F-36: the one chip pair, ``optimize.chip_policy.PAIR_CHIP``.
    bb_gw: int | None = None
    """With ``chip="wc"``, the later gameweek the pair's bench boost is
    played in; ``None`` is a lone chip. The pair's second chip is always the
    bench boost, so a week is all it needs to name."""
```
Then run `cd frontend && npm run types` and commit `schemas.json` and `types.generated.ts` together. No route is added, so the route pin stays at 52. `Config` and `JOB_KINDS` are untouched.

### Hunk 2 — `src/gaffer/web/routers/whatif.py` (orchestrator-only)
Add this validation at the end of `validate()`. Each check returns a 422 naming the field the user typed:
```python
    if req.bb_gw is not None:
        if req.chip != "wc":
            raise fail("pair_needs_wildcard",
                       "a bench boost week pairs with a wildcard only — set "
                       "chip to wc or clear bb_gw", [])
        horizon = req.horizon or state.opt.get("horizon") or len(state.gws)
        gws = state.gws[:max(1, int(horizon))]
        if req.bb_gw not in gws[1:]:
            raise fail("pair_week",
                       f"GW{req.bb_gw} is not a later week of this solve's "
                       f"horizon ({', '.join(f'GW{g}' for g in gws[1:]) or 'none'})",
                       [])
        from gaffer.optimize.chip_policy import load_chip_scenarios
        from gaffer.optimize.chips import PAIR_DGW_MIN_PROB
        doubles = {int(g) for g, p in load_chip_scenarios().items()
                   if p >= PAIR_DGW_MIN_PROB}
        if req.bb_gw not in doubles:
            raise fail("pair_not_a_double",
                       f"GW{req.bb_gw} is not a double gameweek in "
                       f"data/chip_scenarios.toml, so the pair is not one "
                       f"the chip table prices", [])
        if "bboost" not in state.avail_by_gw.get(req.bb_gw, []):
            raise fail("chip_unavailable",
                       f"bboost is not available in GW{req.bb_gw}", [])
```
In `solve_whatif()`, the solve needs one changed keyword on `yours_state`, which makes it the same solve as the chip table's:
```python
        bench_boost_gw=(req.bb_gw if req.bb_gw is not None
                        else gws[0] if chip == "bboost" else None),
```
The scoring fix (ruling 3): `summary()` takes the chip's week instead of a flag, so the bench counts only in that week and the captain is doubled only in the triple captain's week:
```python
def summary(plans, ep_by, meta, weeks, *, hit_cost,
            cap_gw: int | None = None, bench_gw: int | None = None):
    ...
        total = sum(ep(c) for c in plan.xi) + (2.0 if plan.gw == cap_gw else 1.0) * ep(plan.captain)
        if plan.gw == bench_gw:
            total += sum(ep(c) for c in plan.bench)
```
The caller passes `cap_gw=gws[0] if chip == "3xc" else None` and `bench_gw=yours_state.bench_boost_gw`.

Tests go in `tests/test_web_whatif*.py`:
- Each of the four refusals returns a 422 carrying its constraint name.
- The pair's solve receives `wildcard_gw == gws[0]` and `bench_boost_gw == bb_gw`. Stub `solve_plan` and capture its input.
- A single bench boost over a three-week horizon counts the bench in week one only.

### Hunk 3 — `frontend/src/hubs/planning/ChipsTab.tsx` (not orchestrator-only)
- `pick(row)` takes the whole row, not just its name. For `row.chip === 'wildcard+bboost'` it sets `{ chip: 'wc', bb_gw: row.gw2 }`; for a single chip it sets `bb_gw: null`.
- `armed` becomes `CHIP_CODES[chip] !== undefined || (chip === 'wildcard+bboost' && row.gw === thisGw)`, where `thisGw` is the table's first gameweek.
- For a later pair, the withheld sentence reads: "This pair rebuilds in GW{gw}; the lab plays chips in this gameweek only, so it opens when GW{gw} is the one being planned."
- `EMPTY` gains `bb_gw: null`. `chips.ts` is unchanged, because the pair is not a `CHIP_CODES` entry.

Vitest goes in `ChipsTab.test.tsx`, whose pair fixtures at `:117`, `:141` and `:174` already carry `gw2: 7`:
- A pair whose wildcard is this week posts `{chip: 'wc', bb_gw: 7}`.
- A later pair keeps the button disabled and shows the sentence.
- Picking a single chip after the pair posts `bb_gw: null`.

### What stays out
- `optimize/**` is untouched, because `solve_plan` already accepts both weeks.
- No new route and no new job kind.
- `advise.py` is unchanged.
- The golden board does not move, because no served advice number changes; only the lab's re-solve does. `schemas.py` is golden-imported, though, so the package that lands this is `needs-mac`.
