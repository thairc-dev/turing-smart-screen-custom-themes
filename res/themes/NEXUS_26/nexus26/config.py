from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


THEME_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class DisplayConfig:
    width: int = 480
    height: int = 320
    brightness: int = 100
    fps: float = 10.0
    stats_interval: float = 0.8
    reconnect_interval: float = 3.0
    clean_on_startup: bool = True


@dataclass(frozen=True)
class DeviceConfig:
    transport: str = "auto"
    port: str = "AUTO"
    vendor_id: int = 0x1A86
    product_id: int = 0x5722
    serial_number: str = "USB35INCHIPSV2"
    interface: int | None = None
    endpoint: int | None = None
    chunk_size: int = 4096
    allow_unverified_device: bool = False


@dataclass(frozen=True)
class WeatherConfig:
    enabled: bool = True
    location: str = ""
    refresh_seconds: int = 600
    timeout_seconds: int = 5


@dataclass(frozen=True)
class MetricsConfig:
    interval: float = 0.5
    network_interface: str = "auto"


@dataclass(frozen=True)
class AppConfig:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    assets_dir: Path = THEME_ROOT
    fonts_dir: Path = THEME_ROOT / "fonts"
    log_level: str = "INFO"
    log_file: Path | None = None


def _int_value(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, str):
        return int(value, 0)
    return int(value)


def _resolve_path(value: str | None, base: Path, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path).expanduser().resolve() if path else THEME_ROOT / "config.yaml"
    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream) or {}
    base = config_path.parent

    display_raw = raw.get("display", {})
    device_raw = raw.get("device", {})
    weather_raw = raw.get("weather", {})
    metrics_raw = raw.get("metrics", {})
    logging_raw = raw.get("logging", {})

    display = DisplayConfig(
        width=int(display_raw.get("width", 480)),
        height=int(display_raw.get("height", 320)),
        brightness=max(0, min(100, int(display_raw.get("brightness", 100)))),
        fps=max(1.0, min(15.0, float(display_raw.get("fps", 10.0)))),
        stats_interval=max(0.2, float(display_raw.get("stats_interval", 0.8))),
        reconnect_interval=max(1.0, float(display_raw.get("reconnect_interval", 3.0))),
        clean_on_startup=bool(display_raw.get("clean_on_startup", True)),
    )
    if (display.width, display.height) != (480, 320):
        raise ValueError("NEXUS 26 currently supports only the 480x320 landscape 3.5-inch panel")

    device = DeviceConfig(
        transport=str(device_raw.get("transport", "auto")).lower(),
        port=str(device_raw.get("port", "AUTO")),
        vendor_id=_int_value(device_raw.get("vendor_id"), 0x1A86),
        product_id=_int_value(device_raw.get("product_id"), 0x5722),
        serial_number=str(device_raw.get("serial_number", "USB35INCHIPSV2")),
        interface=None if device_raw.get("interface") is None else _int_value(device_raw["interface"], 1),
        endpoint=None if device_raw.get("endpoint") is None else _int_value(device_raw["endpoint"], 0x03),
        chunk_size=max(64, int(device_raw.get("chunk_size", 4096))),
        allow_unverified_device=bool(device_raw.get("allow_unverified_device", False)),
    )
    if device.transport not in {"auto", "libusb", "serial", "preview"}:
        raise ValueError("device.transport must be auto, libusb, serial, or preview")

    weather = WeatherConfig(
        enabled=bool(weather_raw.get("enabled", True)),
        location=str(weather_raw.get("location", "")).strip(),
        refresh_seconds=max(60, int(weather_raw.get("refresh_seconds", 600))),
        timeout_seconds=max(1, int(weather_raw.get("timeout_seconds", 5))),
    )
    metrics = MetricsConfig(
        interval=max(0.2, float(metrics_raw.get("interval", 0.5))),
        network_interface=str(metrics_raw.get("network_interface", "auto")).strip() or "auto",
    )
    log_file_value = logging_raw.get("file")
    return AppConfig(
        display=display,
        device=device,
        weather=weather,
        metrics=metrics,
        assets_dir=_resolve_path(raw.get("assets_dir"), base, THEME_ROOT),
        fonts_dir=_resolve_path(raw.get("fonts_dir"), base, THEME_ROOT / "fonts"),
        log_level=str(logging_raw.get("level", "INFO")).upper(),
        log_file=_resolve_path(log_file_value, base, base / "nexus26.log") if log_file_value else None,
    )
