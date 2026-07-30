# NEXUS MINIMAL

A clean, focused theme for TURZX/Turing 3.5-inch 480×320 displays, with green,
purple, blue, orange and yellow accents. Every number and graph point comes
from a real system metric; missing sensors are shown as `N/A`.

`LOAD` is the operating system's raw one-minute load average. `PROCS` is the
total process count; it is deliberately labelled `TOTAL`, not `RUNNING`.

## Preview

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-portable.txt
PYTHONPATH=. .venv/bin/python -m nexusminimal --preview preview.png
```

## macOS

```bash
./installers/install-macos.sh
```

The installer creates a private environment in
`~/Library/Application Support/NEXUSMINIMAL` and registers
`com.nexusminimal.display`.

## Windows

Run PowerShell:

```powershell
.\installers\install-windows.ps1
```

This installs under `%LOCALAPPDATA%\NEXUSMINIMAL` and registers the
`NEXUSMINIMAL Display` scheduled task.

## Configuration

- `device.transport: auto` uses libusb on macOS and serial/COM elsewhere.
- `device.port: AUTO` scans compatible Windows/Linux serial devices.
- `metrics.network_interface: auto` follows the default internet route.
- The serial number and USB identifiers prevent unrelated devices from being
  selected by default.

See [METRICS.md](METRICS.md) for definitions, units and fallbacks.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```
