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
    units: str = "metric"
    update_interval_sec: int = 1800


@dataclass(frozen=True)
class AppConfig:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    fonts_dir: Path = field(default_factory=lambda: THEME_ROOT / "fonts")
    assets_dir: Path = field(default_factory=lambda: THEME_ROOT.parent.parent / "assets")

    @classmethod
    def load(cls, path: Path | str | None = None) -> AppConfig:
        config_path = Path(path) if path else THEME_ROOT / "theme.yaml"
        if not config_path.exists():
            return cls()

        with config_path.open("r", encoding="utf-8") as file:
            raw: dict[str, Any] = yaml.safe_load(file) or {}

        display_raw = raw.get("display", {})
        device_raw = raw.get("device", {})
        weather_raw = raw.get("weather", {})

        return cls(
            display=DisplayConfig(
                width=int(display_raw.get("width", 480)),
                height=int(display_raw.get("height", 320)),
                brightness=int(display_raw.get("brightness", 100)),
                fps=float(display_raw.get("fps", 10.0)),
                stats_interval=float(display_raw.get("stats_interval", 0.8)),
                reconnect_interval=float(display_raw.get("reconnect_interval", 3.0)),
                clean_on_startup=bool(display_raw.get("clean_on_startup", True)),
            ),
            device=DeviceConfig(
                transport=str(device_raw.get("transport", "auto")),
                port=str(device_raw.get("port", "AUTO")),
                vendor_id=int(device_raw.get("vendor_id", 0x1A86)),
                product_id=int(device_raw.get("product_id", 0x5722)),
                serial_number=str(device_raw.get("serial_number", "USB35INCHIPSV21")),
                interface=device_raw.get("interface"),
                endpoint=device_raw.get("endpoint"),
                chunk_size=int(device_raw.get("chunk_size", 4096)),
                allow_unverified_device=bool(device_raw.get("allow_unverified_device", False)),
            ),
            weather=WeatherConfig(
                enabled=bool(weather_raw.get("enabled", True)),
                location=str(weather_raw.get("location", "")),
                units=str(weather_raw.get("units", "metric")),
                update_interval_sec=int(weather_raw.get("update_interval_sec", 1800)),
            ),
        )
