#!/bin/zsh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# --status (holiday F-5): read-only. Prints each shipped job's launchd state
# and its next fire time, so the ROADMAP's install box is one command rather
# than nine plists read by hand. It never loads or unloads anything.
if [[ "${1:-}" == "--status" ]]; then
  PY="$PROJECT_DIR/.venv/bin/python"
  [[ -x "$PY" ]] || PY="python3"
  # Holiday F-84/F-85: next fire is read from the installed copy when there
  # is one, because that is the file launchd runs; the last column says which.
  printf '%-28s %-11s %-25s %s\n' "job" "state" "next fire (local)" "read from"
  for plist in "$PROJECT_DIR"/scripts/com.gaffer.*.plist; do
    label="${${plist:t}:r}"
    installed=~/Library/LaunchAgents/$label.plist
    if [[ -f "$installed" ]]; then
      read_from="$installed"
      copy="installed"
    else
      read_from="$plist"
      copy="repo copy"
    fi
    if launchctl list "$label" >/dev/null 2>&1; then
      state="loaded"
    elif [[ -f "$installed" ]]; then
      state="unloaded"
    else
      state="missing"
    fi
    next="$("$PY" "$PROJECT_DIR/scripts/automation_status.py" "$read_from" 2>/dev/null || print -r -- "?")"
    printf '%-28s %-11s %-25s %s\n' "$label" "$state" "$next" "$copy"
  done
  exit 0
fi

mkdir -p "$PROJECT_DIR/logs" ~/Library/LaunchAgents
for name in advise prices snapshot field review digest-friday digest-tuesday backup core-insights; do
  sed "s|__PROJECT_DIR__|$PROJECT_DIR|" \
      "$PROJECT_DIR/scripts/com.gaffer.$name.plist" \
      > ~/Library/LaunchAgents/com.gaffer.$name.plist
  launchctl unload ~/Library/LaunchAgents/com.gaffer.$name.plist 2>/dev/null || true
  launchctl load ~/Library/LaunchAgents/com.gaffer.$name.plist
done
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot + Sat/Sun 18:30 field scrape + Tuesday 09:00 decision review + Friday 17:00 briefing + Tuesday 09:30 debrief + nightly 23:45 backup + 06:30/18:30 core-insights collection."
