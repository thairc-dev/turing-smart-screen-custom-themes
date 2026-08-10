#!/usr/bin/env zsh
set -euo pipefail

THEME_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$HOME/Library/Application Support/NULLPET01"
PLIST_LABEL="com.nullpet01.display"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

mkdir -p "$APP_DIR"
cp -R "$THEME_DIR/nullpet01" "$APP_DIR/"
cp "$THEME_DIR/requirements-portable.txt" "$APP_DIR/"

# Create dedicated venv
VENV_DIR="$APP_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements-portable.txt"

# Unload competing launchd services to avoid USB port contention
for competing_plist in "$HOME/Library/LaunchAgents"/com.*.display.plist; do
    if [ -f "$competing_plist" ]; then
        label=$(basename "$competing_plist" .plist)
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    fi
done

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_DIR}/bin/python</string>
        <string>-m</string>
        <string>nullpet01</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${APP_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${APP_DIR}/nullpet01.log</string>
    <key>StandardErrorPath</key>
    <string>${APP_DIR}/nullpet01_error.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
print "NULL PET 01 installed and started successfully from ${APP_DIR}"
