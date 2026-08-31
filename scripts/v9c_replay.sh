#!/usr/bin/env bash
# v9c G3: the replay delta, branch against a re-run main.
#
# Not an equality check. D1 and D2 change EP deliberately, so a gap is the
# expected result and CONVENTIONS §1 applies: three seed bases a side, read as
# mean +/- spread. The banked number from an earlier cycle is not a valid
# comparison and never was (v8a spec §9, G5) — the banked 1876 that cost an
# investigation was stale for exactly this reason.
#
# Run from the branch worktree. Creates a main worktree beside it if absent.
# data/ is untracked and shared, so both sides read byte-identical inputs and
# the only thing that differs is the code.
#
#   caffeinate -i nohup bash scripts/v9c_replay.sh > logs/v9c_replay.log 2>&1 &
#   grep -e V7B_ARM_DONE -e MULTISEED_DONE logs/v9c_replay.log
#
# CONCURRENT=1 runs the two sides at once. It changes no number — the runs
# share no state and data/ is read-only to both — but they contend for cores,
# so the saving is less than half.
set -euo pipefail

SEEDS="${SEEDS:-1876,1901,20260827}"
MAIN_WT="${MAIN_WT:-../gaffer-main-v9c}"
CONCURRENT="${CONCURRENT:-0}"

[ -d "$MAIN_WT" ] || git worktree add "$MAIN_WT" main

mkdir -p logs
HERE="$PWD"

# A fresh worktree carries only what git tracks, and every input this replay
# reads is untracked: config.toml, the parquet store, the fitted models. Link
# rather than copy, so both sides read literally the same bytes — that is what
# makes "the only thing that differs is the code" true rather than hopeful.
# The links are what a *shared* data/ actually means on disk.
for shared in config.toml data models; do
    [ -e "$HERE/$shared" ] || continue
    if [ -L "$MAIN_WT/$shared" ]; then continue; fi
    # data/ exists in the worktree because one file under it is tracked, so
    # the tracked copy is moved aside before the link goes in.
    [ -e "$MAIN_WT/$shared" ] && rm -rf "$MAIN_WT/$shared.tracked" \
        && mv "$MAIN_WT/$shared" "$MAIN_WT/$shared.tracked"
    ln -s "$HERE/$shared" "$MAIN_WT/$shared"
done

branch_side() {
    # Byte-identical flags on both sides. Only --tag differs, which is what
    # scripts/seed_stats.py checks before it will aggregate.
    "$HERE/.venv/bin/python" scripts/v7b_replay.py --arm heur \
        --tag v9c-branch --seed-bases "$SEEDS" --n 40 --chips
}

main_side() {
    ( cd "$MAIN_WT" && "$HERE/.venv/bin/python" scripts/v7b_replay.py \
        --arm heur --tag v9c-main --seed-bases "$SEEDS" --n 40 --chips )
}

if [ "$CONCURRENT" = "1" ]; then
    branch_side > logs/v9c_replay_branch.log 2>&1 &
    b=$!
    main_side > logs/v9c_replay_main.log 2>&1 &
    m=$!
    wait "$b"; wait "$m"
    cat logs/v9c_replay_branch.log logs/v9c_replay_main.log
else
    branch_side
    main_side
fi

# The branch worktree writes reports/ locally; the main worktree writes its
# own. Aggregate each where it landed.
"$HERE/.venv/bin/python" scripts/seed_stats.py reports/v7b_v9c-branch.json
"$HERE/.venv/bin/python" scripts/seed_stats.py \
    "$MAIN_WT/reports/v7b_v9c-main.json"
