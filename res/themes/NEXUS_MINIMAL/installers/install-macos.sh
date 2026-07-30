#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
THEME_DIR="${SCRIPT_DIR:h}"
INSTALL_DIR="${HOME}/Library/Application Support/NEXUSMINIMAL"
PLIST="${HOME}/Library/LaunchAgents/com.nexusminimal.display.plist"
LEGACY_PLIST="${HOME}/Library/LaunchAgents/com.antigravity.nexusminimal.plist"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

mkdir -p "${INSTALL_DIR}" "${HOME}/Library/LaunchAgents"
/usr/bin/ditto "${THEME_DIR}" "${INSTALL_DIR}"
if [[ "$(/usr/bin/uname -m)" == "arm64" ]] && ! command -v macmon >/dev/null 2>&1; then
  if [[ -x /opt/homebrew/bin/brew ]]; then
    /opt/homebrew/bin/brew install macmon
  elif [[ -x /usr/local/bin/brew ]]; then
    /usr/local/bin/brew install macmon
  else
    echo "Homebrew/macmon not found: GPU falls back to ioreg; fan and temperature stay unavailable." >&2
  fi
fi
"${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/.venv/bin/python" -m pip install -r "${INSTALL_DIR}/requirements-portable.txt"

cat > "${PLIST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.nexusminimal.display</string>
  <key>ProgramArguments</key>
  <array>
    <string>${INSTALL_DIR}/.venv/bin/python</string>
    <string>-m</string><string>nexusminimal</string>
    <string>--config</string><string>${INSTALL_DIR}/config.yaml</string>
  </array>
  <key>WorkingDirectory</key><string>${INSTALL_DIR}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>/dev/null</string>
</dict>
</plist>
EOF

/bin/launchctl bootout "gui/$(id -u)/com.nexusminimal.display" 2>/dev/null || true
for other_label in com.nexus26.display com.trueview26.display; do
  /bin/launchctl bootout "gui/$(id -u)/${other_label}" 2>/dev/null || true
  other_plist="${HOME}/Library/LaunchAgents/${other_label}.plist"
  if [[ -f "${other_plist}" ]]; then
    /bin/mv -f "${other_plist}" "${other_plist}.disabled-by-nexusminimal"
  fi
done
if [[ -f "${LEGACY_PLIST}" ]]; then
  /bin/launchctl bootout "gui/$(id -u)/com.antigravity.nexusminimal" 2>/dev/null || true
  /bin/mv "${LEGACY_PLIST}" "${LEGACY_PLIST}.disabled-$(/bin/date +%Y%m%d-%H%M%S)"
fi
loaded=false
for attempt in 1 2 3 4 5; do
  if /bin/launchctl bootstrap "gui/$(id -u)" "${PLIST}" 2>/dev/null; then
    loaded=true
    break
  fi
  /bin/sleep 1
done
if [[ "${loaded}" != true ]]; then
  echo "Could not register com.nexusminimal.display after 5 attempts." >&2
  exit 1
fi
echo "NEXUS MINIMAL installed and started from ${INSTALL_DIR}"
