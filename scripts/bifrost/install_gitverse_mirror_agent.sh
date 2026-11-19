#!/usr/bin/env bash
# Bifrost edition (macOS): run mirror_gitverse.sh every 15 minutes through launchd.
#
#   security add-generic-password -s bifrost-gitverse-mirror -a "$USER" -w   # prompts for the token
#   scripts/bifrost/install_gitverse_mirror_agent.sh            # install / update
#   scripts/bifrost/install_gitverse_mirror_agent.sh --remove
#
# The script is copied out of the repo so the agent keeps working whichever branch is checked out.
# Log: ~/Library/Logs/bifrost-gitverse-mirror.log
set -euo pipefail

label=local.bifrost.gitverse-mirror
dest="$HOME/.local/share/bifrost-gitverse-mirror"
plist="$HOME/Library/LaunchAgents/$label.plist"
log="$HOME/Library/Logs/bifrost-gitverse-mirror.log"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$plist" "$dest/mirror_gitverse.sh"
  echo "removed"
  exit 0
fi

security find-generic-password -s bifrost-gitverse-mirror -w >/dev/null 2>&1 || {
  echo "store the token first: security add-generic-password -s bifrost-gitverse-mirror -a \"\$USER\" -w" >&2
  exit 1
}

mkdir -p "$dest" "$(dirname "$plist")"
cp "$(dirname "$0")/mirror_gitverse.sh" "$dest/mirror_gitverse.sh"
chmod +x "$dest/mirror_gitverse.sh"

cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$dest/mirror_gitverse.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin</string></dict>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$log</string>
  <key>StandardErrorPath</key><string>$log</string>
</dict></plist>
EOF

launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
echo "installed: every 15 minutes, log at $log"
