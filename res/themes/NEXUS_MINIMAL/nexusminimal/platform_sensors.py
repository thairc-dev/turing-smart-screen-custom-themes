from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import threading

import psutil

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
        self._thread = threading.Thread(target=self._read_loop, name="macmon-sampler", daemon=True)
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


class WindowsSensorSampler:
    """Read Windows GPU load, CPU temp, GPU temp, Fan RPM using LibreHardwareMonitor or Python fallbacks."""

    def __init__(self):
        self._lhm_computer = None
        self._lhm_active = False
        self._nvml_active = False
        self._wmi_handle = None
        self._lock = threading.Lock()
        self.start()

    def start(self) -> None:
        # 1. Try LibreHardwareMonitorLib.dll via pythonnet / clr
        try:
            import clr
            dll_dir = Path(__file__).resolve().parents[3] / "external" / "LibreHardwareMonitor"
            lhm_dll = str(dll_dir / "LibreHardwareMonitorLib.dll")
            hid_dll = str(dll_dir / "HidSharp.dll")
            if os.path.exists(lhm_dll):
                clr.AddReference(hid_dll)
                clr.AddReference(lhm_dll)
                from LibreHardwareMonitor import Hardware
                computer = Hardware.Computer()
                computer.IsCpuEnabled = True
                computer.IsGpuEnabled = True
                computer.IsMotherboardEnabled = True
                computer.IsControllerEnabled = True
                computer.IsMemoryEnabled = True
                computer.Open()
                self._lhm_computer = computer
                self._lhm_active = True
                LOG.info("Windows hardware sensors enabled using LibreHardwareMonitorLib")
                return
        except Exception as exc:
            LOG.debug("LibreHardwareMonitor initialization skipped: %s", exc)

        # 2. Try NVML / GPUtil fallback for NVIDIA GPU
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_active = True
            LOG.info("Windows GPU sensors enabled using pynvml")
        except Exception:
            pass

        # 3. Try WMI for OpenHardwareMonitor
        try:
            import wmi
            self._wmi_handle = wmi.WMI()
        except Exception:
            pass

    def stop(self) -> None:
        if self._lhm_computer:
            try:
                self._lhm_computer.Close()
            except Exception:
                pass
            self._lhm_computer = None
        self._lhm_active = False

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
        if self._lhm_active and self._lhm_computer:
            return self._snapshot_lhm()
        return self._snapshot_python_fallback()

    def _snapshot_lhm(
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
            try:
                from LibreHardwareMonitor import Hardware
                cpu_temps = []
                gpu_temps = []
                gpu_loads = []
                fan_rpms = []

                for hardware in self._lhm_computer.Hardware:
                    hardware.Update()
                    for subhw in hardware.SubHardware:
                        subhw.Update()
                    htype = hardware.HardwareType

                    for sensor in hardware.Sensors:
                        if sensor.Value is None:
                            continue
                        stype = sensor.SensorType
                        sname = sensor.Name.lower()
                        val = float(sensor.Value)

                        if htype == Hardware.HardwareType.Cpu:
                            if stype == Hardware.SensorType.Temperature and ("package" in sname or "average" in sname or "core" in sname):
                                cpu_temps.append(val)
                        elif htype in (Hardware.HardwareType.GpuNvidia, Hardware.HardwareType.GpuAmd, Hardware.HardwareType.GpuIntel):
                            if stype == Hardware.SensorType.Temperature and ("core" in sname or "gpu" in sname):
                                gpu_temps.append(val)
                            elif stype == Hardware.SensorType.Load and ("core" in sname or "gpu" in sname):
                                gpu_loads.append(val)
                        elif stype == Hardware.SensorType.Fan and val > 0:
                            fan_rpms.append(int(val))

                cpu_temp = float(sum(cpu_temps) / len(cpu_temps)) if cpu_temps else None
                gpu_temp = float(sum(gpu_temps) / len(gpu_temps)) if gpu_temps else None
                gpu_load = float(sum(gpu_loads) / len(gpu_loads)) if gpu_loads else None
                fan_rpm = int(sum(fan_rpms) / len(fan_rpms)) if fan_rpms else None

                return gpu_load, cpu_temp, gpu_temp, fan_rpm, None, None
            except Exception as exc:
                LOG.warning("LHM snapshot error: %s", exc)
                return None, None, None, None, None, None

    def _snapshot_python_fallback(
        self,
    ) -> tuple[
        float | None,
        float | None,
        float | None,
        int | None,
        int | None,
        int | None,
    ]:
        gpu_load = None
        gpu_temp = None
        cpu_temp = None
        fan_rpm = None

        # GPU via pynvml
        if self._nvml_active:
            try:
                import pynvml
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_load = float(rates.gpu)
                gpu_temp = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
            except Exception:
                pass

        # GPU via GPUtil
        if gpu_load is None:
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_load = float(gpus[0].load * 100)
                    gpu_temp = float(gpus[0].temperature)
            except Exception:
                pass

        # CPU Temp via psutil or WMI
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                all_t = [t.current for entry in temps.values() for t in entry if t.current is not None and t.current > 0]
                if all_t:
                    cpu_temp = float(sum(all_t) / len(all_t))
        except Exception:
            pass

        if cpu_temp is None and self._wmi_handle:
            try:
                ohm_temps = self._wmi_handle.Sensor(SensorType="Temperature")
                c_t = [float(s.Value) for s in ohm_temps if "cpu" in s.Name.lower() and s.Value is not None]
                if c_t:
                    cpu_temp = sum(c_t) / len(c_t)
            except Exception:
                pass

        # Fan RPM via psutil
        try:
            fans = psutil.sensors_fans()
            if fans:
                rpms = [f.current for entry in fans.values() for f in entry if f.current is not None and f.current > 0]
                if rpms:
                    fan_rpm = int(sum(rpms) / len(rpms))
        except Exception:
            pass

        return gpu_load, cpu_temp, gpu_temp, fan_rpm, None, None


class LinuxSensorSampler:
    """Read Linux GPU load, CPU temp, GPU temp, Fan RPM using sysfs / lm-sensors / nvidia-smi."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

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
        cpu_temp = None
        gpu_temp = None
        gpu_load = None
        fan_rpm = None

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                cpu_t = []
                gpu_t = []
                for name, entries in temps.items():
                    name_l = name.lower()
                    for entry in entries:
                        if entry.current is not None and entry.current > 0:
                            if any(k in name_l for k in ("coretemp", "k10temp", "zenpower", "cpu")):
                                cpu_t.append(entry.current)
                            elif any(k in name_l for k in ("amdgpu", "nouveau", "nvidia", "gpu")):
                                gpu_t.append(entry.current)
                if cpu_t:
                    cpu_temp = float(sum(cpu_t) / len(cpu_t))
                if gpu_t:
                    gpu_temp = float(sum(gpu_t) / len(gpu_t))
        except Exception:
            pass

        try:
            fans = psutil.sensors_fans()
            if fans:
                rpms = [f.current for entry in fans.values() for f in entry if f.current is not None and f.current > 0]
                if rpms:
                    fan_rpm = int(sum(rpms) / len(rpms))
        except Exception:
            pass

        if gpu_load is None:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=1,
                )
                parts = [p.strip() for p in out.strip().split(",")]
                if len(parts) >= 1 and parts[0].isdigit():
                    gpu_load = float(parts[0])
                if len(parts) >= 2 and parts[1].isdigit() and gpu_temp is None:
                    gpu_temp = float(parts[1])
            except Exception:
                pass

        return gpu_load, cpu_temp, gpu_temp, fan_rpm, None, None


def create_platform_sensor_sampler(interval_ms: int = 500):
    system = platform.system()
    if system == "Darwin":
        return MacSensorSampler(interval_ms)
    if system == "Windows":
        return WindowsSensorSampler()
    if system == "Linux":
        return LinuxSensorSampler()
    return None


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


def _optional_int(value) -> int | None:
    return None if value is None else int(value)
