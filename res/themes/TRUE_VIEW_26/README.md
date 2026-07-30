# TRUE VIEW 26

A monochrome, information-first theme for TURZX/Turing 3.5-inch 480×320
displays. Every number and graph point comes from a real system metric; missing
sensors are shown as `N/A`.

## Preview

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-portable.txt
PYTHONPATH=. .venv/bin/python -m trueview26 --preview preview.png
```

## macOS

```bash
./installers/install-macos.sh
```

The installer creates a private environment in
`~/Library/Application Support/TRUEVIEW26` and registers
`com.trueview26.display`.

## Windows

Run PowerShell:

```powershell
.\installers\install-windows.ps1
```

This installs under `%LOCALAPPDATA%\TRUEVIEW26` and registers the
`TRUEVIEW26 Display` scheduled task.

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
