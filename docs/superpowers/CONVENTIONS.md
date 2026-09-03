# Gaffer measurement conventions

The discipline learned the hard way between v4c and v7b (rules 1–8, written
in v7c) and again in v12 (rules 9–10, and the additions to rule 1). These are
house rules for every cycle that gates a model change on a number, and a plan
that breaks one is wrong even if its code is right.

## 1. Every replay gate runs K >= 3 seed bases

Verdicts read mean +/- spread, never one draw. v7b measured a seed spread of
116 points on the heuristic arm — larger than every arm gap the project has
ever gated on. One draw measures the seed. That 116 is the S2 chips-on
heuristic run (1785 at seed base 20260827) against `q1b-heur` 1876 and
`q1c-heur` 1901: three draws of one arm.

An aggregate is valid only across runs whose config echo differs in nothing but
`seed_base` — mixing a control arm into a seed trio reads its arm gap as a seed
spread — and `scripts/seed_stats.py` enforces that, refusing with exit 2.

`scripts/v7b_replay.py --seed-bases a,b,c` runs the trio and prints the
aggregate; `scripts/seed_stats.py` reads the same aggregate off reports already
banked.

**The pinned set is wider than `config.toml`.** A replay write-up states every
input both sides were held to, and the config echo is only the part a diff can
see. Since v12 W4 that set also names **the state of `data/core_insights/`** —
present or absent, which seasons, and the date they were collected — because
`role` is in `MINUTES_FEATURES`, the backtest refits the minutes head, and that
archive is untracked, machine-local and rewritten twice a day. Two runs of
identical code and byte-identical config over a different archive are two
different runs, and nothing in the repository records which one you had.
The same rule reaches any untracked input a replay reads: name it, or the
verdict is not reproducible even by its author.

**And the replay's levers live in `config.toml`.** The backtest refits through
`train_all → attacking_features()`, so `[model]` flags and `[optimizer]
price_timing` decide what a replay measures. Both sides run with the file
byte-identical and the write-up states the values (v12 W2/W3: `price_timing =
false` pinned, `xg_per_shot = false`, `draw_availability = true`).

## 2. Gates are pre-registered

The spec states the gate and its mechanical verdict rule before any arm runs.
A rule written after the numbers are in is a rationalisation of the numbers.

## 3. Every comparison carries its control arm

Raw / no-op, run in the same batch on the same code. v7-model's S2 lesson: an
arm that beat nothing is an arm that was never compared.

## 4. The evidence appendix is transcribed into the spec

`logs/` is gitignored, so every `*_ARM_DONE` line the cycle produced is copied
into the spec verbatim. A verdict whose evidence lives only on one laptop is a
verdict nobody can re-read.

## 5. Single-seed causal claims are residuals, not conclusions

If only one draw exists, the finding is named a residual and stays open. It may
motivate the next cycle; it may not close one.

## 6. A failing gate ships OFF behind its flag

With the negative result recorded in the spec. Deleting a failed arm loses the
measurement that cost the hours.

## 7. The orchestrator runs the gates

Implementers build the driver and do not run it. Self-certification is how an
arm ends up measured against its own author's expectation.

## 8. Security ritual after any merge or push

Grep the diff for keys, and confirm `git show main:config.toml` fails. Every
time, not only when the cycle touched config.

## 9. An arm rule pre-registers both halves, and the outcome measure decides

A head metric (bucket RMSE, log-loss on a slice) and a season replay, both
written down before the run, with the replay half at K >= 5 where the arm
touches a head the backtest refits. Twice in v12 a head-metric gain lost
replay points: W2's xG-per-shot head (haulers 5.207 → 5.203, then −28 on the
season the same day) and W4's `role` arm (−1.9% starters log-loss, then −27
post-hoc at K=3). A bucket rule with no replay half is under-specified; a
replay half at K=3 can only support a paired sign test.

## 10. A "no diff" is evidence only when the lever was verified live

A replay that finds the branch byte-identical to `main` has proved nothing
unless the run demonstrably exercised the change. W2's first price-timing
replay was vacuous — a stale price log made the term's table empty on both
sides — and read as a pass. Before banking an identical-arms result, show the
lever was on: a row count, a log line, a value that differs between the sides
somewhere upstream of the total.
