#!/bin/zsh
# Installer for APEX 01 Theme (macOS launchd service)
set -eu

THEME_NAME="APEX_01"
PLIST_NAME="com.apex01.display"
SCRIPT_DIR="${0:A:h}"
THEME_DIR="${SCRIPT_DIR:h}"
INSTALL_DIR="${HOME}/Library/Application Support/APEX01"
PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_NAME}.plist"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

mkdir -p "${INSTALL_DIR}" "${HOME}/Library/LaunchAgents"
/usr/bin/ditto "${THEME_DIR}" "${INSTALL_DIR}"

"${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/.venv/bin/python" -m pip install -r "${INSTALL_DIR}/requirements-portable.txt" 2>/dev/null || "${INSTALL_DIR}/.venv/bin/python" -m pip install Pillow psutil pyserial PyUSB PyYAML certifi

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_DIR}/.venv/bin/python</string>
        <string>-m</string>
        <string>apex01</string>
        <string>--config</string>
        <string>${INSTALL_DIR}/theme.yaml</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>/dev/null</string>
</dict>
</plist>
EOF

# Disable and bootout all competing theme daemons
/bin/launchctl bootout "gui/$(id -u)/${PLIST_NAME}" 2>/dev/null || true
for other_label in com.trueview26.display com.nexus26.display com.nexusminimal.display com.nova01.display; do
  /bin/launchctl bootout "gui/$(id -u)/${other_label}" 2>/dev/null || true
  other_plist="${HOME}/Library/LaunchAgents/${other_label}.plist"
  if [[ -f "${other_plist}" ]]; then
    /bin/mv -f "${other_plist}" "${other_plist}.disabled-by-apex01" 2>/dev/null || true
  fi
done

loaded=false
for attempt in 1 2 3 4 5; do
  if /bin/launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}" 2>/dev/null; then
    loaded=true
    break
  fi
  /bin/sleep 1
done

if [[ "${loaded}" != true ]]; then
  echo "Could not register ${PLIST_NAME} after 5 attempts." >&2
  exit 1
fi

echo "✅ ${THEME_NAME} installed and running isolated!"
