# NEXUS 26

Portable 480×320 landscape theme for TURZX/Turing/UsbMonitor 3.5-inch displays
using VID/PID `1a86:5722`.

## What is portable

- No user name, home directory, Python path, USB port, interface, or endpoint is hard-coded.
- macOS defaults to direct `libusb` writes for smoother partial updates.
- Windows defaults to the normal serial/COM device, so Zadig/WinUSB is not required.
- The process stays alive when the screen is unplugged and reconnects after it is attached again.
- Assets, fonts, config, tests, and installers are contained in this directory.
- CPU, RAM, disk, network, uptime, and system identity are detected at runtime.
- On Apple Silicon, the installer uses the MIT-licensed `macmon` backend for
  CPU/GPU temperature, fan RPM, and Activity Monitor-style RAM usage without
  `sudo`. GPU load uses the Apple driver's `Device Utilization %` from `ioreg`
  (with macmon effective usage only as fallback); the theme never invents values.
- APFS storage uses container size/free space instead of the read-only system
  snapshot, so used/total values match the physical SSD container.

## Supported hardware

The layout is intentionally limited to a 480×320 landscape 3.5-inch panel.
The default serial number check (`USB35INCHIPSV2`) prevents accidentally sending
the 3.5-inch frame format to a 5-inch or 7-inch display with the same VID/PID.

If a genuine 3.5-inch clone has a different serial number, set
`allow_unverified_device: true` only after confirming its resolution and protocol.

## Quick preview

From this directory:

```bash
python3 -m pip install -r requirements-portable.txt
python3 -m nexus26 --preview preview.png
```

## Install on macOS

Python 3.10 or newer is required.

```bash
chmod +x installers/install-macos.sh installers/uninstall-macos.sh
./installers/install-macos.sh
```

The installer copies the theme to
`~/Library/Application Support/NEXUS26`, creates a private virtual environment,
and registers `com.nexus26.display` as a per-user LaunchAgent.

To remove autostart without deleting config or logs:

```bash
./installers/uninstall-macos.sh
```

## Install on Windows

Install Python 3.10 or newer and make sure the launcher `py` is available. Open
PowerShell in this directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\installers\install-windows.ps1
```

The installer copies the theme to `%LOCALAPPDATA%\NEXUS26`, creates a private
virtual environment, and registers a per-user Scheduled Task named
`NEXUS26 Display`.

To remove autostart:

```powershell
.\installers\uninstall-windows.ps1
```

## Configuration

Edit `config.yaml` before installing, or edit the installed copy afterward.

- `device.transport`: `auto`, `libusb`, or `serial`
- `device.port`: `AUTO` or a specific port such as `COM4`
- `display.fps`: capped at 15 because this is a USB full-speed display, not an
  ordinary HDMI/DisplayPort monitor
- `device.chunk_size`: `4096` is stable through typical shared USB hubs
- `weather.location`: optional city/location used by wttr.in
- `metrics.network_interface`: `auto` or a specific interface such as `en1`
- `logging.file`: rotating log file (1 MB × 4 files including the active log)

See [METRICS.md](METRICS.md) for the audited source, definition, unit, refresh
rate, and caveats of every displayed value.

Run once without reconnecting:

```bash
python3 -m nexus26 --config config.yaml --once
```

## Test

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

The tests do not require a connected display.

## Distribution notes

The renderer code is distributed under GPL-3.0-or-later because it derives from
the surrounding `turing-smart-screen-python` project. Roboto's Apache 2.0 license
is included at `fonts/LICENSE-Roboto.txt`.

Apple and Windows names/logos are trademarks of their respective owners and are
included only as platform-identification artwork. They are not endorsements.
Review the trademark rules that apply to your distribution channel before
publishing the package.
