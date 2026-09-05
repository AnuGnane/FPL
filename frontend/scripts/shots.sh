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
for entry in "${HUBS[@]}"; do
  name="${entry%%:*}"; path="${entry#*:}"
  for theme in dark light; do
    if [[ "$theme" == dark ]]; then
      "$SHELL_BIN" --headless --blink-settings=preferredColorScheme=0 \
        --hide-scrollbars --window-size=1400,1600 --virtual-time-budget=12000 \
        --screenshot="$OUT/$name-$theme.png" "$BASE$path" >/dev/null 2>&1
    else
      "$SHELL_BIN" --headless \
        --hide-scrollbars --window-size=1400,1600 --virtual-time-budget=12000 \
        --screenshot="$OUT/$name-$theme.png" "$BASE$path" >/dev/null 2>&1
    fi
    echo "$OUT/$name-$theme.png"
  done
done
