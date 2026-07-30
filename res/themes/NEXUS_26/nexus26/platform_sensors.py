from __future__ import annotations

import json
import logging
from pathlib import Path
import plistlib
import shutil
import subprocess
import threading

LOG = logging.getLogger(__name__)


class MacSensorSampler:
    """Read Apple Silicon metrics from macmon, with an ioreg GPU fallback."""

    def __init__(self, interval_ms: int = 500):
        self.interval_ms = max(250, interval_ms)
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: dict = {}
        self._macmon = self._find_macmon()

    @staticmethod
    def _find_macmon() -> str | None:
        detected = shutil.which("macmon")
        if detected:
            return detected
        for path in (Path("/opt/homebrew/bin/macmon"), Path("/usr/local/bin/macmon")):
            if path.is_file():
                return str(path)
        return None

    @property
    def enhanced_available(self) -> bool:
        return self._macmon is not None

    def start(self) -> None:
        if not self._macmon or (self._thread and self._thread.is_alive()):
            return
        try:
            self._process = subprocess.Popen(
                [self._macmon, "pipe", "-i", str(self.interval_ms)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            LOG.warning("Could not start macmon: %s", exc)
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, name="nexus26-macmon", daemon=True)
        self._thread.start()
        LOG.info("Apple Silicon sensors enabled using %s", self._macmon)

    def stop(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._thread:
            self._thread.join(timeout=2)
        self._process = None

    def _read_loop(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        for line in self._process.stdout:
            if self._stop.is_set():
                break
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self._lock:
                self._latest = value

    def snapshot(
        self,
    ) -> tuple[
        float | None,
        float | None,
        float | None,
        int | None,
        int | None,
        int | None,
    ]:
        with self._lock:
            data = dict(self._latest)
        if data:
            gpu_ratio = data.get("gpu_usage_ratio")
            temperatures = data.get("temp") or {}
            fans = data.get("fans") or []
            memory = data.get("memory") or {}
            fan_rpm = None
            if fans:
                valid_rpm = [int(fan["rpm"]) for fan in fans if fan.get("rpm") is not None]
                fan_rpm = round(sum(valid_rpm) / len(valid_rpm)) if valid_rpm else None
            driver_gpu_percent = self._ioreg_gpu_percent()
            return (
                (
                    driver_gpu_percent
                    if driver_gpu_percent is not None
                    else (
                        None
                        if gpu_ratio is None
                        else max(0.0, min(100.0, float(gpu_ratio) * 100))
                    )
                ),
                _optional_float(temperatures.get("cpu_temp_avg")),
                _optional_float(temperatures.get("gpu_temp_avg")),
                fan_rpm,
                _optional_int(memory.get("ram_usage")),
                _optional_int(memory.get("ram_total")),
            )
        return self._ioreg_gpu_percent(), None, None, None, None, None

    @staticmethod
    def _ioreg_gpu_percent() -> float | None:
        try:
            output = subprocess.check_output(
                ["/usr/sbin/ioreg", "-r", "-c", "AGXAccelerator", "-a"],
                timeout=2,
            )
            entries = plistlib.loads(output)
            for entry in entries:
                statistics = entry.get("PerformanceStatistics") or {}
                value = statistics.get("Device Utilization %")
                if value is not None:
                    return max(0.0, min(100.0, float(value)))
        except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
            return None
        return None


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


def _optional_int(value) -> int | None:
    return None if value is None else int(value)
