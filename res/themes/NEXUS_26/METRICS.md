# Metrics audit

NEXUS 26 keeps acquisition separate from rendering. A snapshot is collected
every 0.5 seconds by default; display cards rotate approximately once per
second to stay within the USB full-speed bandwidth.

| Display | Source | Definition and unit |
|---|---|---|
| CPU % | `psutil.cpu_percent` | Average non-idle time across logical CPUs during the sampling window. |
| CPU °C | `macmon` on Apple Silicon | Average CPU sensor temperature. `N/A` when the platform exposes no real sensor. |
| GPU % | Apple `AGXAccelerator` via `ioreg` | Driver `Device Utilization %`. `macmon` effective GPU usage is the macOS fallback. |
| GPU °C | `macmon` on Apple Silicon | Average GPU sensor temperature. |
| RAM | `macmon` on Apple Silicon | Activity Monitor-style used bytes divided by physical bytes; displayed in GiB. Other platforms use `total - available` consistently for both value and percent. |
| SSD | APFS container via `diskutil` on macOS | Container size minus container free space, in decimal GB. This avoids the sealed system snapshot error. Other platforms use the home drive. Refreshed every 30 seconds. |
| Fan | `macmon` on Apple Silicon | Actual RPM. Multiple fans are averaged because the card has room for one value. |
| Network | Default-route interface via `psutil` | Byte-counter delta divided by elapsed monotonic time, in decimal MB/s. Loopback, AWDL, VPN, and other interfaces are excluded unless selected explicitly. |
| Uptime | `psutil.boot_time` | Wall-clock seconds since system boot, including sleep. |
| Weather | wttr.in | Current Celsius observation. Blank location uses IP geolocation; set `weather.location` for deterministic results. Long descriptions are mapped to compact meaningful conditions. |
| Clock/date | Local system time | Uses the operating system timezone and locale. |
| Model/OS | `system_profiler` / platform APIs | Detected at startup; no model or OS version is hard-coded. |

## Health ring

The ring is an interpretation, not another sensor. Rules are evaluated in this
order:

1. `HOT`: CPU or GPU temperature at least 95°C.
2. `HEAVY`: CPU or GPU utilization at least 95%.
3. `MEMORY`: RAM usage at least 95%.
4. `DISK`: storage usage at least 90%.
5. `GOOD`: none of the above.

The two subtitle lines state the reason, so a nearly full disk is no longer
mislabelled as generic resource load.

## Platform caveats

Apple Silicon enhanced sensors use the optional MIT-licensed `macmon` command.
The macOS installer adds it through Homebrew when Homebrew is available.
Windows and Linux only show temperature/fan values when a genuine platform
sensor backend exposes them; the renderer never derives temperature or RPM
from CPU utilization.
