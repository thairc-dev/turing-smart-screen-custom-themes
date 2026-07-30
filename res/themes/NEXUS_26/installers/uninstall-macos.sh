#!/bin/zsh
set -eu

PLIST="${HOME}/Library/LaunchAgents/com.nexus26.display.plist"
/bin/launchctl bootout "gui/$(id -u)/com.nexus26.display" 2>/dev/null || true
rm -f "${PLIST}"
echo "Autostart removed. Theme files remain in ~/Library/Application Support/NEXUS26."
