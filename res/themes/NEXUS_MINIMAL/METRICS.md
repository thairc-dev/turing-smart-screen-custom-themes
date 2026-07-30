# Metrics audit

NEXUS MINIMAL renders only collected operating-system or sensor values. It does
not add decorative utilization, temperature, RPM, throughput or graph points.

| Display | Source | Definition and unit |
|---|---|---|
| CPU load | `psutil.cpu_percent` | Average non-idle time across logical CPUs during the sampling window. |
| CPU graph | CPU load snapshot history | The same real samples shown numerically, retained for up to 60 updates. |
| CPU frequency | `psutil.cpu_freq` | Current frequency normalized to GHz. `N/A` when unavailable. |
| Temperature | `macmon` on Apple Silicon | CPU temperature, then genuine GPU temperature only as a fallback. Never estimated from load. |
| RAM | `macmon` on Apple Silicon | Activity Monitor-style used bytes divided by physical bytes, displayed in GiB. Other platforms consistently use `total - available`. |
| SSD | APFS container via `diskutil` on macOS | Container size minus container free space in decimal GB. Other platforms use the home drive. Cached for 30 seconds. |
| Fan | `macmon` on Apple Silicon | Actual RPM. Multiple fans are averaged because the layout has one value. |
| Network | Default-route interface via `psutil` | Counter delta divided by monotonic elapsed time, in decimal MB/s. |
| Load | `psutil.getloadavg()[0]` | Raw operating-system one-minute load average. It is not a fabricated CPU score. |
| Processes | `psutil.pids()` | Total process count, labelled `TOTAL` rather than incorrectly implying every process is running. |
| Uptime | `psutil.boot_time` | Wall-clock time since boot, including sleep. |
| Clock/date | Local system time | Uses the operating-system timezone. |
| Model/OS | `system_profiler` / platform APIs | Detected at startup; no machine name or OS version is hard-coded. |

## Platform caveats

Apple Silicon enhanced sensors use the optional MIT-licensed `macmon` command.
The macOS installer adds it through Homebrew when Homebrew is available.
Windows and Linux show temperature and fan values only when a genuine platform
sensor backend exposes them; otherwise the theme displays `N/A`.
