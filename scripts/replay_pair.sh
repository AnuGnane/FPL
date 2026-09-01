#!/usr/bin/env bash
# The replay delta, branch against a re-run main — for any cycle.
#
# v9c's driver, generalized. ``scripts/v9c_replay.sh`` is left byte-identical
# because it is *evidence*: it is the exact script that produced v9c's banked
# verdict, and editing it in place would make that verdict unreproducible. The
# two things it hardcoded — the cycle name and the worktree path — are the only
# things that move here.
#
# Not an equality check. A cycle that changes EP deliberately produces a gap,
# and CONVENTIONS §1 applies: three seed bases a side, read as mean +/- spread.
# The banked number from an earlier cycle is not a valid comparison and never
# was (v8a spec §9, G5) — the banked 1876 that cost an investigation was stale
# for exactly this reason.
#
# Run from the branch worktree. Creates a main worktree beside it if absent.
# data/ is untracked and shared, so both sides read byte-identical inputs and
# the only thing that differs is the code.
#
#   caffeinate -i nohup bash scripts/replay_pair.sh v9d > logs/v9d_replay.log 2>&1 &
#   grep -e V7B_ARM_DONE -e MULTISEED_DONE logs/v9d_replay.log
#
# The tag defaults to the current branch name, so a cycle that forgets the
# argument still gets a name nobody else is using.
#
# CONCURRENT=1 runs the two sides at once. It changes no number — the runs
# share no state and data/ is read-only to both — but they contend for cores,
# so the saving is less than half.
set -euo pipefail

TAG="${1:-$(git rev-parse --abbrev-ref HEAD)}"
SEEDS="${SEEDS:-1876,1901,20260827}"
# Derived from the tag, so two cycles cannot collide in one worktree.
MAIN_WT="${MAIN_WT:-../gaffer-main-$TAG}"
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
        --tag "$TAG-branch" --seed-bases "$SEEDS" --n 40 --chips
}

main_side() {
    ( cd "$MAIN_WT" && "$HERE/.venv/bin/python" scripts/v7b_replay.py \
        --arm heur --tag "$TAG-main" --seed-bases "$SEEDS" --n 40 --chips )
}

if [ "$CONCURRENT" = "1" ]; then
    branch_side > "logs/${TAG}_replay_branch.log" 2>&1 &
    b=$!
    main_side > "logs/${TAG}_replay_main.log" 2>&1 &
    m=$!
    wait "$b"; wait "$m"
    cat "logs/${TAG}_replay_branch.log" "logs/${TAG}_replay_main.log"
else
    branch_side
    main_side
fi

# --seed-bases banks ONE report per seed -- v7b_{tag}-s{seed}.json -- and not
# a single combined v7b_{tag}.json. An earlier version of this script named the
# combined file, so its aggregate step pointed at something that never exists.
# seed_stats.py takes the trio, and taking the trio is also the config-echo
# check: it exits 2 unless the reports differ in nothing but seed_base and tag.
SEED_LIST=$(echo "$SEEDS" | tr ',' ' ')

branch_reports=""; main_reports=""
for sb in $SEED_LIST; do
    branch_reports="$branch_reports reports/v7b_${TAG}-branch-s${sb}.json"
    main_reports="$main_reports $MAIN_WT/reports/v7b_${TAG}-main-s${sb}.json"
done

# The branch worktree writes reports/ locally; the main worktree writes its own.
"$HERE/.venv/bin/python" scripts/seed_stats.py $branch_reports
"$HERE/.venv/bin/python" scripts/seed_stats.py $main_reports

# Teardown. The worktree is disposable: it holds no untracked state of its own
# (config.toml, data/ and models/ are symlinks into the branch worktree, and
# its reports/ has been aggregated above). Set KEEP_WT=1 to inspect it instead.
if [ "${KEEP_WT:-0}" != "1" ]; then
    for shared in config.toml data models; do
        [ -L "$MAIN_WT/$shared" ] && rm -f "$MAIN_WT/$shared"
        # Put the tracked copy back so `git worktree remove` sees a clean tree.
        [ -e "$MAIN_WT/$shared.tracked" ] \
            && mv "$MAIN_WT/$shared.tracked" "$MAIN_WT/$shared"
    done
    git worktree remove --force "$MAIN_WT"
    echo "REPLAY_PAIR_WORKTREE_REMOVED $MAIN_WT"
fi
