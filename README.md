# 🚀 TURZX 3.5" Smart Display - Ultimate Custom Themes

A collection of high-performance, deduplicated, beautifully designed custom themes for **TURZX / Turing 3.5-inch USB Smart Displays** (480x320 resolution). Built with standalone Python renderers, native Apple Silicon (`macmon` & `ioreg`) sensor integration, and cross-platform support.

Created by [thairc-dev](https://github.com/thairc-dev) (author of [mac-server-mode](https://github.com/thairc-dev/mac-server-mode)).

> 💡 **Compatibility**: Built for and fully compatible with [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python).

---

## ☕ Support & Buy Me a Coffee

If you find these themes useful on your desk, feel free to support future updates! ☕

[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue.svg?style=for-the-badge&logo=paypal)](https://paypal.me/NQT16)

> **Donate via PayPal**: [https://paypal.me/NQT16](https://paypal.me/NQT16)

---

## 🌟 Featured Custom Themes

### 🌌 NOVA 01
A sleek, modern dark-mode dashboard with pure obsidian background, smooth sans-serif clock typography, centered weather widget, and 5-day forecast.
- **Pure Obsidian Aesthetics**: `#000000` pitch black background with `#0A0C12` charcoal card panels.
- **Centered Weather & 5-Day Forecast**: Large weather icon, current temperature, high/low/humidity, and full 5-day forecast row (`THU`, `FRI`, `SAT`, `SUN`, `MON`).
- **Gradient Glow Wave Graphs**: Hardware-accelerated glowing wave graphs for CPU, Temp, Uptime, and Processes.

![NOVA 01 Live GIF Preview](res/themes/NOVA_01/preview_demo.gif)

---

### 📊 TRUE VIEW 26
A zero-duplication, highly balanced system monitoring theme designed for maximum readability.
- **GPU / LOAD 1M / PROCS**: Middle row replaces redundant metrics with genuine GPU utilization, 1-minute OS load average, and active process count.
- **Spacious Typography**: Fine-tuned font spacing preventing text overflow or cramped numbers.
- **Full Card Breakdown**: Dedicated cards for CPU (with 60s history graph), RAM (GiB), SSD (GB), Fan RPM, Temperature, and Network throughput.

![TRUE VIEW 26 Live GIF Preview](res/themes/TRUE_VIEW_26/preview_demo.gif)

---

### ⚡ NEXUS 26
A futuristic Cyberpunk-inspired neon theme featuring real-time visualizers and a dynamic health ring.
- **Quantum Pulse Core**: Central health ring automatically classifies system state (`GOOD`, `HEAVY`, `MEMORY`, `DISK`, `HOT`).
- **Smooth Wave Graphs**: Hardware-accelerated smooth filled gradient graphs for CPU and GPU.
- **Live Dot-Matrix Equalizer**: Real-time per-core CPU load visualizer embedded in the top header.

![NEXUS 26 Live GIF Preview](res/themes/NEXUS_26/preview_demo.gif)

---

### 🍃 NEXUS MINIMAL
A clean, lightweight, minimalist theme focusing on key performance indicators.
- **High Efficiency**: Minimalist aesthetic with ultra-low CPU footprint.
- **Essential Metrics**: Large digital clock, Uptime, CPU 60s history graph, RAM, SSD, Fan, Temp, Load, and Processes.

![NEXUS MINIMAL Live GIF Preview](res/themes/NEXUS_MINIMAL/preview_demo.gif)

---

### 🔷 APEX 01
A premium dark-navy system monitoring dashboard with custom vector hardware icons, 5-column bottom utility bar, and live weather telemetry.
- **100% Concept Pinwheel Fan**: Ultra-sharp concept fan asset with live status indicators.
- **Spacious Weather Telemetry**: High/low temperature range and hollow cyan teardrop humidity stats with generous 8px gap separation.
- **Full Utility Breakdown**: 5-column utility bar with Uptime, Network (MB/s), Wi-Fi SSID / Ethernet auto-detection, Temp history graph, and Fan RPM.

![APEX 01 Live GIF Preview](res/themes/APEX_01/preview_demo.gif)

---

## 💻 System Support & Testing Status

| OS | Status | Notes |
|---|---|---|
| **macOS (Apple Silicon M1/M2/M3/M4)** | ✅ **Fully Tested & Verified** | Uses `macmon` & `ioreg` for real GPU %, Fan RPM, and CPU/GPU °C |
| **macOS (Intel)** | ✅ Supported | Standard sensors via `psutil` |
| **Windows 10/11** | 🧪 **Installer Included** | Windows setup script included (`install-windows.ps1`); community feedback welcome! |
| **Linux** | ✅ Supported | Native `psutil` sensor acquisition |

---

## 📦 Quick Installation

### macOS
1. Open Terminal and clone this repository:
   ```bash
   git clone https://github.com/thairc-dev/turing-smart-screen-custom-themes.git
   cd turing-smart-screen-custom-themes
   ```
2. Run the automated installer script for your desired theme:
   ```bash
   # Install APEX 01 (Theme 5)
   zsh res/themes/APEX_01/installers/install-macos.sh

   # Or install NOVA 01
   zsh res/themes/NOVA_01/installers/install-macos.sh

   # Or install TRUE VIEW 26
   zsh res/themes/TRUE_VIEW_26/installers/install-macos.sh

   # Or install NEXUS 26
   zsh res/themes/NEXUS_26/installers/install-macos.sh

   # Or install NEXUS MINIMAL
   zsh res/themes/NEXUS_MINIMAL/installers/install-macos.sh
   ```

### Windows (Powershell)
Open PowerShell as Administrator:
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force

# Install APEX 01
.\res\themes\APEX_01\installers\install-windows.ps1

# Or install NOVA 01
.\res\themes\NOVA_01\installers\install-windows.ps1

# Or install TRUE VIEW 26
.\res\themes\TRUE_VIEW_26\installers\install-windows.ps1
```

---

## 🙏 Credits & Acknowledgments

- **Core Project**: Built for and compatible with [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python) by [Matthieu Houdebine](https://github.com/mathoudebine).
- **Sensors**: Thanks to `psutil`, `macmon` (Apple Silicon sensor reader by phoboslab), and `Pillow`.

---

## 📄 License

Distributed under the **GPL-3.0 License**. See `LICENSE` for details.
