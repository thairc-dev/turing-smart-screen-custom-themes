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

from .platform_sensors import create_platform_sensor_sampler


@dataclass(frozen=True)
class SystemInfo:
    kind: str
    model: str
    os_version: str


@dataclass(frozen=True)
class MetricsSnapshot:
    cpu_percent: float = 0.0
    per_core: tuple[float, ...] = ()
    cpu_frequency_ghz: float | None = None
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
    load_average_1m: float | None = None
    process_count: int = 0
    fan_rpm: int | None = None
    uptime_seconds: int = 0
    warning: bool = False
    health_status: str = "GOOD"
    health_line1: str = "All systems"
    health_line2: str = "operational"


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


def classify_health(
    cpu_percent: float,
    gpu_percent: float | None,
    ram_percent: float,
    disk_percent: float,
    cpu_temp_c: float | None,
    gpu_temp_c: float | None,
) -> tuple[str, str, str]:
    hottest = max(value for value in (cpu_temp_c, gpu_temp_c, 0.0) if value is not None)
    if hottest >= 95:
        return "HOT", "Thermal limit", "approaching"
    if cpu_percent >= 95 or (gpu_percent is not None and gpu_percent >= 95):
        return "HEAVY", "Resource load", "elevated"
    if ram_percent >= 95:
        return "MEMORY", "Memory use", "critically high"
    if disk_percent >= 90:
        return "DISK", "Free space", "running low"
    return "GOOD", "All systems", "operational"


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
        self._platform_sensors = create_platform_sensor_sampler(round(self.interval * 1000))
        self._configured_network_interface = network_interface
        self._network_interface = self._detect_network_interface()
        self._disk_cache = (0.0, 0.0, 0.0)
        self._last_disk_refresh = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)
        self._stop.clear()
        if self._platform_sensors:
            self._platform_sensors.start()
        self._thread = threading.Thread(target=self._run, name="nexus26-metrics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._platform_sensors:
            self._platform_sensors.stop()

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return replace(self._snapshot)

    @staticmethod
    def _disk_root() -> str:
        anchor = Path.home().anchor
        return anchor or "/"

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
                frequency = psutil.cpu_freq()
                frequency_ghz = None
                if frequency and frequency.current > 0:
                    # psutil reports MHz on most platforms, but recent macOS
                    # builds expose Apple Silicon frequency directly in GHz.
                    frequency_ghz = (
                        float(frequency.current)
                        if frequency.current <= 20
                        else float(frequency.current) / 1000
                    )
                gpu_percent = cpu_temp = gpu_temp = None
                fan_rpm = None
                sensor_ram_used = sensor_ram_total = None
                if self._platform_sensors:
                    (
                        gpu_percent,
                        cpu_temp,
                        gpu_temp,
                        fan_rpm,
                        sensor_ram_used,
                        sensor_ram_total,
                    ) = self._platform_sensors.snapshot()
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
                health_status, health_line1, health_line2 = classify_health(
                    cpu,
                    gpu_percent,
                    ram_percent,
                    disk_percent,
                    cpu_temp,
                    gpu_temp,
                )
                try:
                    load_average_1m = float(psutil.getloadavg()[0])
                except (AttributeError, OSError):
                    load_average_1m = None
                try:
                    process_count = len(psutil.pids())
                except psutil.Error:
                    process_count = 0
                snapshot = MetricsSnapshot(
                    cpu_percent=cpu,
                    per_core=per_core,
                    cpu_frequency_ghz=frequency_ghz,
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
                    load_average_1m=load_average_1m,
                    process_count=process_count,
                    fan_rpm=fan_rpm,
                    uptime_seconds=max(0, int(time.time() - psutil.boot_time())),
                    warning=health_status != "GOOD",
                    health_status=health_status,
                    health_line1=health_line1,
                    health_line2=health_line2,
                )
                with self._lock:
                    self._snapshot = snapshot
                if current_net is not None:
                    previous_net = current_net
                previous_time = current_time
            except (OSError, psutil.Error):
                continue
