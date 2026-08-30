# Gaffer measurement conventions

The discipline learned the hard way between v4c and v7b. These are house rules
for every cycle that gates a model change on a number, and a plan that breaks
one is wrong even if its code is right.

## 1. Every replay gate runs K >= 3 seed bases

Verdicts read mean +/- spread, never one draw. v7b measured a seed spread of
116 points on the heuristic arm — larger than every arm gap the project has
ever gated on. One draw measures the seed.

`scripts/v7b_replay.py --seed-bases a,b,c` runs the trio and prints the
aggregate; `scripts/seed_stats.py` reads the same aggregate off reports already
banked.

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
