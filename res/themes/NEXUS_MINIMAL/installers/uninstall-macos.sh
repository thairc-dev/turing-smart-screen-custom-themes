#!/bin/zsh
set -eu

PLIST="${HOME}/Library/LaunchAgents/com.nexusminimal.display.plist"
/bin/launchctl bootout "gui/$(id -u)/com.nexusminimal.display" 2>/dev/null || true
rm -f "${PLIST}"
echo "Autostart removed. Theme files remain in ~/Library/Application Support/NEXUSMINIMAL."
