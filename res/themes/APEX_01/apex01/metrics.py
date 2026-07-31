from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import platform
import plistlib
import socket
import subprocess
import threading
import time

import psutil

from .platform_sensors import MacSensorSampler


@dataclass(frozen=True)
class SystemInfo:
    kind: str
    model: str
    os_version: str


@dataclass(frozen=True)
class MetricsSnapshot:
    cpu_percent: float = 0.0
    cpu_freq_ghz: float = 2.8
    per_core: tuple[float, ...] = ()
    cpu_temp_c: float | None = None
    gpu_percent: float | None = None
    gpu_temp_c: float | None = None
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    net_up_mb_s: float = 0.0
    net_down_mb_s: float = 0.0
    network_interface: str = ""
    ip_address: str = "10.0.0.123"
    wifi_name: str = "WiFi 6"
    fan_rpm: int | None = None
    uptime_seconds: int = 0
    warning: bool = False


def detect_system_info() -> SystemInfo:
    system = platform.system()
    if system == "Darwin":
        try:
            output = subprocess.check_output(
                ["/usr/sbin/system_profiler", "SPHardwareDataType", "-json"],
                text=True,
                timeout=4,
            )
            hardware = json.loads(output)["SPHardwareDataType"][0]
            machine_name = hardware.get("machine_name", "Mac")
            chip_type = hardware.get("chip_type", "")
            model = f"{machine_name} {chip_type.removeprefix('Apple ')}".strip()
        except (OSError, subprocess.SubprocessError, KeyError, IndexError, json.JSONDecodeError):
            model = platform.machine() or "Mac"
        version = platform.mac_ver()[0]
        return SystemInfo("apple", model, f"macOS {version}" if version else "macOS")
    if system == "Windows":
        model = platform.node() or "Windows PC"
        return SystemInfo("windows", model, f"Windows {platform.release()}")
    return SystemInfo("linux", platform.node() or "Linux PC", f"Linux {platform.release()}")


def display_model_name(info: SystemInfo, max_chars: int = 20) -> str:
    model = info.model
    return model if len(model) <= max_chars else model[: max_chars - 1].rstrip() + "…"


def network_rate_mb_s(current_bytes: int, previous_bytes: int, elapsed: float) -> float:
    if elapsed <= 0:
        return 0.0
    return max(0, current_bytes - previous_bytes) / elapsed / 1_000_000


class MetricsCollector:
    def __init__(self, interval: float = 0.5, network_interface: str = "auto"):
        self.interval = max(0.2, interval)
        self._snapshot = MetricsSnapshot(per_core=(0.0,) * (psutil.cpu_count() or 1))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mac_sensors = MacSensorSampler(round(self.interval * 1000)) if platform.system() == "Darwin" else None
        self._configured_network_interface = network_interface
        self._network_interface = self._detect_network_interface()
        self._ip_address = self._detect_ip_address()
        self._wifi_name = self._detect_wifi_name()
        self._disk_cache = (0.0, 0.0, 0.0)
        self._last_disk_refresh = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self._stop.clear()
        if self._mac_sensors:
            self._mac_sensors.start()
        self._thread = threading.Thread(target=self._run, name="apex01-metrics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._mac_sensors:
            self._mac_sensors.stop()

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return replace(self._snapshot)

    @staticmethod
    def _disk_root() -> str:
        anchor = Path.home().anchor
        return anchor or "/"

    def _detect_ip_address(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("1.1.1.1", 80))
                return probe.getsockname()[0]
        except OSError:
            return "10.0.0.123"

    def _detect_wifi_name(self) -> str:
        sys_name = platform.system()
        if sys_name == "Darwin":
            try:
                out = subprocess.check_output(["networksetup", "-listallhardwareports"], text=True, timeout=2)
                wifi_iface = None
                lines = out.splitlines()
                for i, line in enumerate(lines):
                    if "Wi-Fi" in line or "AirPort" in line:
                        if i + 1 < len(lines) and "Device:" in lines[i+1]:
                            wifi_iface = lines[i+1].split(":")[1].strip()
                            break
                if wifi_iface:
                    out2 = subprocess.check_output(["networksetup", "-getairportnetwork", wifi_iface], text=True, timeout=2)
                    match = re.search(r"Current Wi-Fi Network:\s*(.+)", out2)
                    if match:
                        ssid = match.group(1).strip()
                        if ssid and "not associated" not in ssid.lower():
                            return ssid[:12]
            except Exception:
                pass
        elif sys_name == "Windows":
            try:
                out = subprocess.check_output("netsh wlan show interfaces", text=True, timeout=2, shell=True)
                for line in out.splitlines():
                    if "SSID" in line and "BSSID" not in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            ssid = parts[1].strip()
                            if ssid:
                                return ssid[:12]
            except Exception:
                pass
        elif sys_name == "Linux":
            try:
                out = subprocess.check_output(["iwgetid", "-r"], text=True, timeout=2)
                ssid = out.strip()
                if ssid:
                    return ssid[:12]
            except Exception:
                pass
        return "Ethernet" if "en0" in self._network_interface or "eth" in self._network_interface else "WiFi 6"

    def _detect_network_interface(self) -> str:
        if self._configured_network_interface.lower() != "auto":
            return self._configured_network_interface
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("1.1.1.1", 80))
                local_address = probe.getsockname()[0]
            for name, addresses in psutil.net_if_addrs().items():
                if any(address.address == local_address for address in addresses):
                    return name
        except OSError:
            pass
        if platform.system() == "Darwin":
            try:
                output = subprocess.check_output(
                    ["/sbin/route", "-n", "get", "default"],
                    text=True,
                    timeout=2,
                )
                for line in output.splitlines():
                    if line.strip().startswith("interface:"):
                        return line.split(":", 1)[1].strip()
            except (OSError, subprocess.SubprocessError):
                pass
        candidates = {
            name: counters
            for name, counters in psutil.net_io_counters(pernic=True).items()
            if not name.lower().startswith(("lo", "loopback"))
        }
        if not candidates:
            return ""
        return max(candidates, key=lambda name: candidates[name].bytes_recv + candidates[name].bytes_sent)

    def _network_counters(self):
        counters = psutil.net_io_counters(pernic=True)
        value = counters.get(self._network_interface)
        if value is None:
            self._network_interface = self._detect_network_interface()
            value = counters.get(self._network_interface)
        return value

    def _cached_disk_stats(self, now: float) -> tuple[float, float, float]:
        if self._disk_cache[2] <= 0 or now - self._last_disk_refresh >= 30:
            self._disk_cache = self._disk_stats()
            self._last_disk_refresh = now
        return self._disk_cache

    @classmethod
    def _disk_stats(cls) -> tuple[float, float, float]:
        if platform.system() == "Darwin":
            try:
                output = subprocess.check_output(
                    ["/usr/sbin/diskutil", "info", "-plist", cls._disk_root()],
                    timeout=3,
                )
                info = plistlib.loads(output)
                total = int(info.get("APFSContainerSize") or 0)
                free = int(info.get("APFSContainerFree") or 0)
                if total > 0 and 0 <= free <= total:
                    used = total - free
                    return used / total * 100, used / 1_000_000_000, total / 1_000_000_000
            except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
                pass
        disk = psutil.disk_usage(cls._disk_root())
        return float(disk.percent), disk.used / 1_000_000_000, disk.total / 1_000_000_000

    def _run(self) -> None:
        previous_net = self._network_counters()
        previous_time = time.monotonic()
        while not self._stop.wait(self.interval):
            try:
                current_time = time.monotonic()
                elapsed = max(0.001, current_time - previous_time)
                current_net = self._network_counters()
                ram = psutil.virtual_memory()
                disk_percent, disk_used_gb, disk_total_gb = self._cached_disk_stats(current_time)
                cpu = float(psutil.cpu_percent(interval=None))
                per_core = tuple(float(value) for value in psutil.cpu_percent(interval=None, percpu=True))
                
                # CPU Frequency
                freq = psutil.cpu_freq()
                cpu_freq_ghz = round(freq.current / 1000.0, 1) if freq and freq.current > 0 else 2.8

                gpu_percent = cpu_temp = gpu_temp = None
                fan_rpm = None
                sensor_ram_used = sensor_ram_total = None
                if self._mac_sensors:
                    (
                        gpu_percent,
                        cpu_temp,
                        gpu_temp,
                        fan_rpm,
                        sensor_ram_used,
                        sensor_ram_total,
                    ) = self._mac_sensors.snapshot()
                if sensor_ram_used is not None and sensor_ram_total:
                    ram_used_bytes = sensor_ram_used
                    ram_total_bytes = sensor_ram_total
                else:
                    ram_total_bytes = ram.total
                    ram_used_bytes = ram.total - ram.available
                ram_percent = ram_used_bytes / ram_total_bytes * 100
                up = down = 0.0
                if previous_net is not None and current_net is not None:
                    up = network_rate_mb_s(current_net.bytes_sent, previous_net.bytes_sent, elapsed)
                    down = network_rate_mb_s(current_net.bytes_recv, previous_net.bytes_recv, elapsed)

                hottest_temp = max(value for value in (cpu_temp, gpu_temp, 0.0) if value is not None)
                warning = cpu >= 90 or ram_percent >= 90 or disk_percent >= 90 or hottest_temp >= 90

                snapshot = MetricsSnapshot(
                    cpu_percent=cpu,
                    cpu_freq_ghz=cpu_freq_ghz,
                    per_core=per_core,
                    ram_percent=ram_percent,
                    ram_used_gb=ram_used_bytes / 1024**3,
                    ram_total_gb=ram_total_bytes / 1024**3,
                    cpu_temp_c=cpu_temp,
                    gpu_percent=gpu_percent,
                    gpu_temp_c=gpu_temp,
                    disk_percent=disk_percent,
                    disk_used_gb=disk_used_gb,
                    disk_total_gb=disk_total_gb,
                    net_up_mb_s=up,
                    net_down_mb_s=down,
                    network_interface=self._network_interface,
                    ip_address=self._ip_address,
                    wifi_name=self._wifi_name,
                    fan_rpm=fan_rpm,
                    uptime_seconds=max(0, int(time.time() - psutil.boot_time())),
                    warning=warning,
                )
                with self._lock:
                    self._snapshot = snapshot
                if current_net is not None:
                    previous_net = current_net
                previous_time = current_time
            except (OSError, psutil.Error):
                continue
