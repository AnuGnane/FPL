#!/bin/zsh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$PROJECT_DIR/logs" ~/Library/LaunchAgents
for name in advise prices snapshot; do
  sed "s|__PROJECT_DIR__|$PROJECT_DIR|" \
      "$PROJECT_DIR/scripts/com.gaffer.$name.plist" \
      > ~/Library/LaunchAgents/com.gaffer.$name.plist
  launchctl unload ~/Library/LaunchAgents/com.gaffer.$name.plist 2>/dev/null || true
  launchctl load ~/Library/LaunchAgents/com.gaffer.$name.plist
done
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot."
