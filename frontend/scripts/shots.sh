#!/usr/bin/env bash
# v14 gate (spec §7): the six hubs in both themes, headless, into
# .superpowers/shots/<stage>/<hub>-<theme>.png. Serve a fresh build first:
#   cd frontend && npm run build && cd .. && \
#   (lsof -iTCP:8927 -sTCP:LISTEN >/dev/null || uv run gaffer ui --no-open-browser --port 8927 &)
# Dark is forced through Blink's preferred colour scheme (0 = dark); the
# shell's default is light. --force-dark-mode does NOT flip it (probed).
set -eo pipefail
STAGE="${1:?usage: shots.sh <stage>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/.superpowers/shots/$STAGE"
SHELL_BIN="${CHROME_HEADLESS_SHELL:-$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell}"
BASE="${GAFFER_UI:-http://localhost:8927}"
mkdir -p "$OUT"
HUBS=(
  "this-week:/"
  "planning-whatif:/planning?tab=whatif"
  "planning-board:/planning?tab=board"
  "players:/players"
  "league:/league"
  "settings:/model?tab=settings"
)
# v15 gate (specs/2026-09-06-gaffer-v15-leagues-design.md §10): the League
# hub's four tabs, a non-focus league open, This Week and Settings. Pass the
# non-focus league id as LEAGUE_OTHER (a small private league keeps the
# history fetch short).
if [[ "$STAGE" == v15* ]]; then
  HUBS=(
    "this-week:/"
    "league-leagues:/league?tab=leagues"
    "league-race:/league?tab=race"
    "league-other:/league?tab=race&league=${LEAGUE_OTHER:?set LEAGUE_OTHER}"
    "league-rivals:/league?tab=rivals"
    "league-whatif:/league?tab=whatif"
    "settings:/model?tab=settings"
  )
fi
# v16 gate (specs/2026-09-06-gaffer-v16-restraint-brief-design.md §8): This
# Week (the restrained moves, the objective line, the decision panel, the
# brief card, the ladder's bar and steps), the Planning board's objective
# block, Review with a note beside a grade, and Settings with the hit bar.
if [[ "$STAGE" == v16* ]]; then
  HUBS=(
    "this-week:/"
    "planning-board:/planning?tab=board"
    "review:/model?tab=review"
    "settings:/model?tab=settings"
  )
fi
# v17b gate (specs/2026-09-07-v17b-restraint-prose-design.md §6.4): This
# Week twice — the moves card's served restraint line at the usual height,
# and the page in a window tall enough to reach the ladder card's labels,
# steps and notes. An entry's optional third field is the window height.
if [[ "$STAGE" == v17b* ]]; then
  HUBS=(
    "this-week:/"
    "this-week-lower:/:3400"
  )
fi
for entry in "${HUBS[@]}"; do
  name="${entry%%:*}"; rest="${entry#*:}"
  path="${rest%%:*}"; height="${rest#*:}"
  [[ "$height" == "$path" ]] && height=1600
  for theme in dark light; do
    if [[ "$theme" == dark ]]; then
      "$SHELL_BIN" --headless --blink-settings=preferredColorScheme=0 \
        --hide-scrollbars --run-all-compositor-stages-before-draw --window-size=1400,$height --virtual-time-budget=15000 \
        --screenshot="$OUT/$name-$theme.png" "$BASE$path" >/dev/null 2>&1
    else
      "$SHELL_BIN" --headless \
        --hide-scrollbars --run-all-compositor-stages-before-draw --window-size=1400,$height --virtual-time-budget=15000 \
        --screenshot="$OUT/$name-$theme.png" "$BASE$path" >/dev/null 2>&1
    fi
    echo "$OUT/$name-$theme.png"
  done
done
